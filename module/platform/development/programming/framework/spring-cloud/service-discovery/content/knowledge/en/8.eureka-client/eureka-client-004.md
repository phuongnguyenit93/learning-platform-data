# Running Multiple Instances of the Same Service

In a microservice system, a service typically runs multiple instances to distribute load and maintain availability when a single process fails. These instances fulfill the same business role, yet each instance is an independent process with its own network address and identifier.

With Spring Cloud Netflix Eureka, multiple instances of the same service register under **the same service name**, typically taken from spring.application.name. Eureka stores multiple instance records under that same application. Consumers look up instances by service name, and then Spring Cloud LoadBalancer selects one instance to send the request to.

For example, three inventory-service processes might be registered as follows:

| Service name | Instance ID | Address |
|---|---|---|
| inventory-service | inventory-service:node-a:8081 | 10.20.1.11:8081 |
| inventory-service | inventory-service:node-a:8082 | 10.20.1.11:8082 |
| inventory-service | inventory-service:node-b:8080 | 10.20.1.12:8080 |

The service name identifies the logical service that consumers need to call. The instance ID distinguishes each individual process in the registry. The host and port address indicates where HTTP requests can be sent. These three values are related, but they are not interchangeable.

## 1. Why Run Multiple Instances?

A single instance can become a bottleneck or a single point of failure for a service. Running multiple instances helps the system:

- **Distribute load:** spread requests across multiple processes instead of overloading a single process.
- **Increase availability:** when one instance fails, other healthy instances can continue serving requests.
- **Scale on demand:** increase the number of instances during traffic spikes and scale down when load is low.
- **Roll out updates incrementally:** update one group of instances while the remaining ones continue serving, provided the API remains compatible across versions.
- **Isolate resources:** each instance can run on a separate machine or container.

Running multiple instances does not automatically guarantee high availability. Instances may still share a single database, registry, or network node. If a shared dependency fails, all instances can still become unavailable. Therefore, discovery should be combined with health checks, timeouts, bounded retries, observability, and proper infrastructure design.

## 2. Service Name and Instance ID in Eureka

A provider declares its logical name with spring.application.name:

~~~yaml
spring:
  application:
    name: inventory-service
~~~

Every instance of the same service uses the value inventory-service. When registering with Eureka, the registry groups instances by application name. The Eureka dashboard typically displays application names in uppercase, such as INVENTORY-SERVICE.

Each instance needs a unique eureka.instance.instance-id. If multiple processes register with the same service name and the same instance ID, they can overwrite or update the same registration. When that happens, the dashboard will not accurately reflect the number of running processes.

You can combine hostname and port to form the instance ID:

~~~yaml
eureka:
  instance:
    instance-id: ${spring.application.name}:${HOSTNAME:localhost}:${server.port}
    prefer-ip-address: true
~~~

This configuration works well when processes run on the same machine using different ports, or run in containers/hosts with distinct hostnames. The published address must also be reachable from consumers.

If your environment has its own naming convention, you can pass INSTANCE_ID from deployment configuration:

~~~yaml
eureka:
  instance:
    instance-id: ${INSTANCE_ID:${spring.application.name}:${HOSTNAME:localhost}:${server.port}}
~~~

When running multiple processes, inspect the actual instance IDs on the Eureka dashboard. Never assume changing the port automatically changes the instance ID if the application is overriding the ID with a fixed value.

If the HOSTNAME variable is unset or does not reflect a hostname resolvable from consumers, explicitly pass INSTANCE_ID per machine or container. The instance ID only helps the registry distinguish records; the hostname/IP advertised by the client must still be routable from consumers.

### Distinguishing Service Name, Instance ID, and Metadata

| Property | What Is It Used For? | Example |
|---|---|---|
| spring.application.name | Groups instances into one logical service | inventory-service |
| eureka.instance.instance-id | Distinguishes each process in the registry | inventory-service:node-a:8081 |
| eureka.instance.hostname or IP address | Specifies the published host | node-a, 10.20.1.11 |
| server.port | HTTP port the process listens on | 8081 |
| eureka.instance.metadata-map | Stores additional instance metadata | version=v2, zone=zone-a |

Metadata can assist with observability, filtering, or custom routing policies. Spring Cloud LoadBalancer does not automatically interpret arbitrary metadata and does not automatically prefer only the newest version. If you need routing by version, zone, or deployment group, you must configure the corresponding policy on the consumer side.

## 3. Configuring a Eureka Client to Run Multiple Times

A common configuration for a provider:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: ${SERVER_PORT:8080}

eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
    register-with-eureka: true
    fetch-registry: true
    healthcheck:
      enabled: true
  instance:
    instance-id: ${INSTANCE_ID:${spring.application.name}:${HOSTNAME:localhost}:${server.port}}
    prefer-ip-address: true
    metadata-map:
      version: ${app.version:dev}
      zone: ${APP_ZONE:local}

management:
  endpoints:
    web:
      exposure:
        include: health,info

app:
  version: ${APP_VERSION:dev}
~~~

Key properties:

- spring.application.name: remains identical across all instances of the same service.
- server.port: must differ if multiple processes bind to the same IP address on the same machine.
- eureka.client.service-url.defaultZone: Eureka Server URL where the client registers.
- eureka.client.register-with-eureka: enables instance registration.
- eureka.client.fetch-registry: allows the client to fetch the registry; required if the application also looks up other services.
- eureka.instance.instance-id: must be unique for each process.
- eureka.instance.prefer-ip-address: instructs Eureka to publish the IP address instead of the hostname when appropriate for the deployment network.
- eureka.client.healthcheck.enabled: lets Eureka Client use the application's health status when integrated with Actuator.
- eureka.instance.metadata-map: carries extra attributes such as version or zone.

The corresponding Eureka Client and Actuator dependencies are required. The Spring Cloud starter version must match Spring Boot through the Spring Cloud BOM. Do not mix different starter versions across instances if they are all built from the same application.

## 4. Running Multiple Instances on the Same Machine

When running multiple processes on one machine, each process needs its own port. For example, running the same JAR twice:

**Terminal A — first instance**

~~~bash
java -jar inventory-service.jar --server.port=8081 --eureka.instance.instance-id=inventory-service:localhost:8081 --app.version=v1
~~~

**Terminal B — second instance**

~~~bash
java -jar inventory-service.jar --server.port=8082 --eureka.instance.instance-id=inventory-service:localhost:8082 --app.version=v1
~~~

Both processes share spring.application.name=inventory-service, while using different ports and instance IDs. Both register with the same Eureka Server.

You can pass the same configuration using environment variables:

~~~bash
export SERVER_PORT=8081
export INSTANCE_ID=inventory-service:localhost:8081
export APP_VERSION=v1
~~~

On Windows PowerShell, set the environment variables in each terminal window before running the JAR:

~~~powershell
$env:SERVER_PORT = "8081"
$env:INSTANCE_ID = "inventory-service:localhost:8081"
$env:APP_VERSION = "v1"
java -jar .\inventory-service.jar
~~~

Open another PowerShell window and use a different port and instance ID for the second process. Do not start two processes bound to the same IP address and port, because the operating system will reject binding the second port.

If instances run on separate machines, they can use the same internal port, such as 8080 on all hosts. In that case, the instance ID must distinguish the hostname or address of each machine.

## 5. Running Multiple Instances in Containers

In Docker or Kubernetes, each container or pod has its own network namespace. Multiple containers can all listen on port 8080 internally because each container has its own network address. Providers still use the same service name, while the instance ID and registered address must distinguish each container.

Example services in Compose:

~~~yaml
services:
  inventory-a:
    image: inventory-service:1.0
    environment:
      SPRING_APPLICATION_NAME: inventory-service
      SERVER_PORT: "8080"
      EUREKA_SERVER_URL: http://eureka-server:8761/eureka/
      INSTANCE_ID: inventory-service:inventory-a:8080
      APP_VERSION: "1.0"

  inventory-b:
    image: inventory-service:1.0
    environment:
      SPRING_APPLICATION_NAME: inventory-service
      SERVER_PORT: "8080"
      EUREKA_SERVER_URL: http://eureka-server:8761/eureka/
      INSTANCE_ID: inventory-service:inventory-b:8080
      APP_VERSION: "1.0"
~~~

This is an illustrative service snippet; both containers must also join a network that can reach Eureka Server. Do not assign the same fixed container_name to multiple replicas. When using Docker Compose scaling or a Kubernetes Deployment, derive the instance ID from the hostname or pod name to avoid collisions.

Inside a container, localhost refers to the container itself. Providers must register an address reachable from consumers—usually the container or pod IP or hostname on the shared network. If Eureka shows the instance but the published address is not routable from the consumer, discovery may succeed while HTTP requests fail.

Do not publish the same fixed host port for multiple containers on the same machine. If you need to debug directly from the host, use separate host port mappings per container or route through a consumer or load balancer.

## 6. Verifying Multiple Registered Instances

After starting the processes, open the Eureka dashboard, usually at:

~~~text
http://localhost:8761
~~~

Look for the INVENTORY-SERVICE application. You should see the number of instances matching the number of started processes. Each row should have a distinct instance ID, the expected host/port address, and its current status.

You can also verify via Eureka's REST endpoint:

~~~bash
curl -H "Accept: application/json" http://localhost:8761/eureka/apps/INVENTORY-SERVICE
~~~

The JSON response contains the application and its instance records. Useful fields to inspect include:

- instanceId: process identifier.
- hostName: hostname published by the instance.
- ipAddr: registered IP address.
- port: HTTP port.
- status: status currently recorded by Eureka.
- metadata: additional attributes registered by the client.

The REST endpoint and dashboard may vary depending on security configuration, content negotiation, and Eureka version. If the endpoint returns 401/403, check registry authentication rather than concluding that no instances exist.

## 7. Consumer Calling by Service Name

The consumer does not need to know the individual port of each instance. It calls the service name and lets Spring Cloud LoadBalancer select an instance from the registry.

Consumer dependencies include Eureka Client and Spring Cloud LoadBalancer. With WebClient, declare a builder annotated with @LoadBalanced:

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

Create a client that calls the service name:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(@LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<String> getInstanceInfo() {
        return webClient.get()
                .uri("http://inventory-service/api/instance")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

The URI uses inventory-service instead of a specific IP and port. LoadBalancer retrieves candidate instances by service name, selects one instance, and replaces the logical host/port with the actual address before sending the request.

If you use a WebClient builder without @LoadBalanced, the hostname inventory-service may be treated as a regular DNS hostname and will not be resolved through Eureka. Make sure the right bean is injected into the client.

By default, Spring Cloud LoadBalancer typically uses a round-robin algorithm to cycle through instances in the list. You can configure another supplier or algorithm when needed. Round-robin does not guarantee strictly equal distribution over a small number of requests: the instance list, caches, concurrent requests, and error states all affect the outcome.

## 8. Observing the Selected Instance

The provider should expose an endpoint that returns process-identifying details. For example:

~~~java
import java.util.Map;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InstanceInfoController {

    @Value("${spring.application.name}")
    private String serviceName;

    @Value("${eureka.instance.instance-id}")
    private String instanceId;

    @Value("${app.version:dev}")
    private String version;

    @GetMapping("/api/instance")
    public Map<String, String> instance() {
        return Map.of(
                "service", serviceName,
                "instanceId", instanceId,
                "version", version);
    }
}
~~~

When calling the consumer repeatedly, observe instanceId in the response. If requests are routed across multiple instances, responses will show different IDs. If you always receive the same ID, check the instance count in the registry, the list received by the consumer, the LoadBalancer configuration, and caching.

You can log the instance ID on the provider for each request. Logs help correlate consumer requests, the handling instance, and the registry state at that moment. Never log tokens, passwords, or sensitive data.

## 9. Lifecycle of Multiple Instances

Each Eureka Client process has its own registration lifecycle:

1. **Startup:** the process reads the service name, instance ID, hostname/IP, and port.
2. **Registration:** the client sends its instance record to Eureka Server.
3. **Lease renewal:** the client periodically sends heartbeats to signal that the instance is still alive.
4. **Lookup:** consumers retrieve the instance list by service name; data may be cached.
5. **Graceful shutdown:** the client attempts to deregister when the application shuts down.
6. **Abrupt termination:** if heartbeats stop arriving, the registry may retain the instance until the lease expires and eviction cleans it up.

Heartbeat intervals, lease expiration, and registry fetch intervals depend on configuration and version. Never assume a dead instance vanishes immediately from every consumer. Eureka has a self-preservation mechanism to prevent mass eviction of registrations when heartbeat rates drop unexpectedly. This mechanism can keep a failed instance listed in the registry longer than expected.

Application health checks help reflect readiness to serve traffic, but they require proper configuration and an understanding of how status propagates to Eureka. Docker health status, Kubernetes readiness, and Eureka instance status are distinct signals; they do not synchronize automatically across all setups.

## 10. Deploying a New Version and Scaling Down Instances

When deploying a new version, you can run old and new instances concurrently under the same service name if their APIs are compatible. For example:

| Instance | Service name | Metadata version | Status |
|---|---|---|---|
| inventory-v1-a | inventory-service | v1 | UP |
| inventory-v1-b | inventory-service | v1 | UP |
| inventory-v2-a | inventory-service | v2 | UP |

Once the new version is ready, consumers may receive both v1 and v2 instances. This is useful for rolling updates, but it also means requests can land on either the old or new version. If two versions are incompatible, do not let them share a service name without an appropriate routing strategy.

Version metadata is purely informational. For canary or blue/green deployments, you need dedicated routing, filtering, or separate service names such as inventory-service-v1 and inventory-service-v2, depending on your deployment model. Do not rely on metadata alone to assume LoadBalancer will prefer the newer version.

When scaling down instances, stop processes gracefully so clients deregister. In high-traffic systems, drain in-flight requests before shutting down an instance. If a container is killed abruptly, consumers may continue selecting that instance briefly until the registry and caches update.

## 11. Common Issues

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Only one instance visible despite running two processes | Both share the same instance ID or one process failed to register | Compare instance IDs and check registration logs |
| Two processes fail to bind the port | Same host and same port | Choose different ports or run on separate hosts/containers |
| Dashboard shows multiple instances but requests hit only one | Consumer receives only one instance, cache has not refreshed, or bean lacks LoadBalancer | Check discovery list and client bean configuration |
| Instance appears in registry but requests time out | Published address is unreachable from the consumer | Check IP, hostname, port, and network routing |
| Dead instance remains on dashboard | Lease has not expired, heartbeat has not timed out, or self-preservation is active | Check heartbeat settings, eviction, and registry status |
| New instance overwrites old instance | Duplicate instance ID | Generate ID from hostname/pod and port or deployment ID |
| Uneven request distribution | Few requests, concurrent load, caching, or selection algorithm | Log instance IDs and observe across a sufficiently large sample of requests |
| Consumer cannot resolve service name | WebClient not annotated with @LoadBalanced or missing starter | Check dependencies and injected bean |

When diagnosing issues, separate three questions:

- Does Eureka store all expected instance records?
- Does the consumer receive the updated instance list?
- Does LoadBalancer choose an address reachable by the consumer?

Answering each question individually makes it straightforward to pinpoint whether the problem is in provider registration, the registry, discovery caching, LoadBalancer, or networking.

## 12. Security and Operations

Every instance self-registers its address and metadata with the registry. If an untrusted application can register arbitrarily under the service name of a critical service, consumers risk sending data to a spoofed instance. Therefore:

- Restrict network access to Eureka Server.
- Enable authentication and TLS for the registry as required by your environment.
- Allow only authorized workloads to register under corresponding service names.
- Never store secrets or sensitive data in metadata.
- Never treat UP status as proof that a caller is authorized to invoke an API; providers must still enforce authentication and authorization.
- Monitor instance counts, statuses, heartbeats, registration times, and inter-service call errors.
- Configure timeouts and bounded retries; only retry operations that are safe to repeat or already protected by idempotency mechanisms.

In operations, monitor both the expected instance count and the actual instance count. A service configured for three replicas where only one successfully registered can still become a bottleneck. Conversely, stale registrations that have not been cleaned up can cause consumers to send requests to dead addresses.

## 13. Hands-On Verification Procedure

Follow these steps in order to verify multiple instances:

1. Start Eureka Server and verify that the dashboard is ready.
2. Configure two processes with the same spring.application.name=inventory-service.
3. Assign a separate port and instance ID to each process.
4. Start both processes and wait for their registrations to appear in Eureka.
5. Verify that each instance has a host/port address reachable from the consumer.
6. Configure a consumer with Eureka Client and Spring Cloud LoadBalancer.
7. Send multiple requests via the service name and observe the returned instance IDs.
8. Gracefully stop one instance and observe the deregistration process.
9. Abruptly terminate an instance in a lab environment to observe heartbeats, lease expiration, and registry updates.
10. Restart the instance and confirm it re-registers with the appropriate identifier.

Once complete, be clear on the relationship: **multiple processes with the same service name form one logical service; each process has its own instance ID and address; Eureka stores the instance list; consumers look up by service name; and LoadBalancer picks an instance per request.** This is the foundation for scaling replicas and performing rolling updates in Spring Cloud systems.
