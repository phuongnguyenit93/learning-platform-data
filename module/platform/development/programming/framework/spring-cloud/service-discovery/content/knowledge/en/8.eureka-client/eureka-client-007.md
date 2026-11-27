# Register-Only, Fetch-Only, or Performing Both Roles

A Spring Cloud application using Eureka can participate in the registry in two independent directions: **registering its own instance** so other services can find it, and **fetching the registry** to look up other services. These two directions are controlled by `eureka.client.register-with-eureka` and `eureka.client.fetch-registry`.

Because the two properties are independent, an application can register only, fetch only, do both, or do neither. Choosing the right combination avoids unnecessary registry downloads while ensuring the application has the discovery data needed for inter-service calls.

## 1. Two Roles of Eureka Client

### Registering an Instance: `register-with-eureka`

When `eureka.client.register-with-eureka=true`, Eureka Client sends the application's instance details to Eureka Server. Registration data typically includes application/service name, instance ID, hostname or IP, port, metadata, and initial status.

Spring Cloud Netflix normally takes the application name from `spring.application.name`. Once the instance is registered, Eureka Client sends periodic heartbeats to renew its lease. When the application shuts down gracefully, the client can send a deregistration request; if heartbeats stop arriving, the server handles lease expiration and eviction according to its configuration.

Example:

```yaml
spring:
  application:
    name: inventory-service

server:
  port: 8084

eureka:
  client:
    register-with-eureka: true
    service-url:
      defaultZone: http://localhost:8761/eureka/
```

The `inventory-service` application registers with Eureka Server at the address above. Other services can discover this instance if they fetch the registry and the instance is in an eligible status.

`register-with-eureka` only determines whether the current application registers itself as a Eureka client. This property does not enable or disable Eureka Server's ability to accept registrations from other applications.

### Querying the Registry: `fetch-registry`

When `eureka.client.fetch-registry=true`, Eureka Client fetches the registry from Eureka Server and maintains local data for lookups. APIs such as `DiscoveryClient.getServices()` and `DiscoveryClient.getInstances(serviceId)` rely on the discovery data provided by that implementation.

Example:

```yaml
eureka:
  client:
    fetch-registry: true
    service-url:
      defaultZone: http://localhost:8761/eureka/
```

The application can use `DiscoveryClient` or Spring Cloud LoadBalancer to find instances of `inventory-service`. A consumer does not need to register itself if it does not expose APIs to other services.

The registry is typically fetched and refreshed periodically, so results can lag slightly behind recent changes on the server. `fetch-registry=true` does not mean every `getInstances()` call makes a synchronous query to the server; the client normally reads from the locally cached registry that is fetched and refreshed at intervals.

## 2. Four Configuration Combinations

The two flags form four modes. Here is a quick reference for choosing each application's configuration:

| `register-with-eureka` | `fetch-registry` | Application Role | Typical Use Case |
| --- | --- | --- | --- |
| `true` | `true` | Register and query | Microservice that both exposes APIs and calls other services |
| `true` | `false` | Register only | Provider that does not need to discover other services |
| `false` | `true` | Query only | Consumer that only calls other services and does not need to be discovered |
| `false` | `false` | Neither register nor fetch registry | Standalone Eureka Server or application not participating in discovery |

These two flags do not replace `@EnableEurekaServer`. They control the Eureka Client role inside the application. An application can enable Eureka Server endpoints while simultaneously configuring its own embedded Eureka Client with one of these four combinations.

## 3. Register Only: Provider That Does Not Need to Find Other Services

Set `register-with-eureka=true` and `fetch-registry=false` when the application only needs to publish its instance to consumers and does not call other services via discovery itself.

Example `application.yml`:

```yaml
spring:
  application:
    name: catalog-service

server:
  port: 8083

eureka:
  client:
    register-with-eureka: true
    fetch-registry: false
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${spring.cloud.client.ip-address}:${server.port}
```

In this configuration:

- `catalog-service` sends registration and heartbeats to Eureka.
- Eureka Server can serve this instance to consumers that have fetched the registry.
- The client does not download the full service list into a local cache.
- Code in `catalog-service` should not expect `DiscoveryClient.getInstances()` to return other services from Eureka because the registry is not fetched.

This mode suits a provider that only handles incoming traffic from external callers or a gateway, with no outbound calls needing service discovery. If the provider later starts calling `pricing-service` or `identity-service` by service ID, enable `fetch-registry` or configure appropriate discovery.

## 4. Query Only: Consumer That Does Not Need to Register Itself

Set `register-with-eureka=false` and `fetch-registry=true` when the application only needs to look up other services and does not need to be called by other applications through Eureka.

Example `application.yml`:

```yaml
spring:
  application:
    name: batch-report

server:
  port: 8090

eureka:
  client:
    register-with-eureka: false
    fetch-registry: true
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
```

The `batch-report` application fetches the registry and can call `catalog-service`, without registering its own instance. This makes sense for batch jobs, internal workers, or scheduled applications that do not expose endpoints to other services.

If a consumer exposes REST APIs that a gateway or other services need to discover, do not disable registration. In that case, use both roles or split the worker and API into separate applications.

### Using DiscoveryClient for Lookups

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogLookup {

    private final DiscoveryClient discoveryClient;

    public CatalogLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findCatalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }
}
```

This code only works when a discovery implementation is configured and the registry contains data. If `fetch-registry=false` is used, the service list from Eureka is not fetched into the client for regular lookups.

## 5. Both Register and Query: Standard Microservice

Most microservices both expose APIs and call other services. For instance, `checkout-service` exposes endpoints to a gateway while calling `catalog-service` and `payment-service`. In that case, enable both properties:

```yaml
spring:
  application:
    name: checkout-service

server:
  port: 8082

eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${spring.cloud.client.ip-address}:${server.port}
```

With this configuration, `checkout-service`:

1. Registers its instance so the gateway and other services can discover it.
2. Sends heartbeats to renew its lease.
3. Fetches the registry to learn about instances of other services.
4. Uses `DiscoveryClient` or LoadBalancer to locate and call services by name.

For example, with an `@LoadBalanced` `RestTemplate`, the consumer can call `http://catalog-service/api/products/42`. LoadBalancer selects an instance from the fetched discovery data. `DiscoveryClient` and LoadBalancer are two distinct components: discovery provides the instance list, while LoadBalancer picks an instance for the request.

This is the standard choice when an application acts as both provider and consumer within the same microservice system.

## 6. Neither Role: Standalone Eureka Server

A standalone Eureka Server normally does not need to register itself as a client application or fetch a registry from another peer. You can configure the embedded Eureka Client inside the server as follows:

```java
package com.example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class DiscoveryServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryServerApplication.class, args);
    }
}
```

```yaml
spring:
  application:
    name: discovery-server

server:
  port: 8761

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false
    service-url:
      defaultZone: http://localhost:8761/eureka/
```

The two `false` flags here only disable the `discovery-server` application's embedded Eureka Client from registering itself and fetching the registry. `@EnableEurekaServer` still enables the REST API and dashboard so other Eureka Clients can register, send heartbeats, and query.

### When Deploying Eureka Peers

When running multiple Eureka Server peers, each server's configuration typically enables both registration and registry fetching so the servers exchange data with one another. For example, peer 1 knowing peer 2 and peer 3:

```yaml
eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka-2:8761/eureka/,http://eureka-3:8761/eureka/
```

This configuration differs from a standalone Eureka Server. Do not copy the standalone `false` flags into every node of a peer cluster, or the servers will fail to exchange registry state as intended.

## 7. Registration and Query Flow Diagram

```mermaid
flowchart TB
    subgraph APP[Spring Boot Application]
        A[Application context]
        RC[Eureka Client]
        DC[DiscoveryClient]
        LB[Spring Cloud LoadBalancer]
        A --> RC
        A --> DC
        DC --> LB
    end
    E[(Eureka Server)]
    P[Other service provider]
    RC -->|register-with-eureka=true<br/>Register + heartbeat| E
    E -->|Registry response| RC
    RC -->|fetch-registry=true<br/>Fetch / refresh local cache| DC
    DC -->|getInstances(serviceId)| LB
    LB -->|Select instance URI| P
```

The diagram illustrates two independent configuration flows:

- `register-with-eureka=true` activates the flow from the application to the server to register the instance and maintain heartbeats.
- `fetch-registry=true` activates the flow that downloads the service instance list to the client for discovery.

If you disable one flow, the other can still operate. For example, a consumer-only app still fetches the registry without registering itself; a provider-only app still registers and sends heartbeats without fetching the registry.

## 8. Choosing Configuration by Application Role

| Application Type | Register | Fetch registry | Reason |
| --- | --- | --- | --- |
| Inbound-only REST provider | Enabled | Can disable | Needs to be discovered by consumers; does not need to call other services |
| Outbound-only consumer/batch worker | Disabled | Enabled | Needs to find providers; does not need to appear in the registry |
| Microservice exposing APIs and making outbound calls | Enabled | Enabled | Acts as both provider and consumer |
| Standalone Eureka Server | Disabled | Disabled | Server accepts client registrations without joining as a peer |
| Peer Eureka Server in a cluster | Enabled | Enabled | Server exchanges registry updates with peers |
| One-off job that neither registers nor uses discovery | Disabled | Disabled | Neither Eureka Client function is needed |

Do not choose configuration solely based on the labels "provider" or "consumer". Look at whether the application needs to be called by other services and whether it needs to look up other services. An application can have both inbound APIs and outbound calls, so it often needs both flags enabled.

## 9. Impact on DiscoveryClient and LoadBalancer

`fetch-registry` determines whether Eureka Client downloads the registry for discovery. When disabled, do not rely on Eureka registry lookup APIs such as `DiscoveryClient.getInstances()` to find other services. Simply being able to inject a `DiscoveryClient` bean does not mean it has instance data to return.

`register-with-eureka` does not determine the ability to call services. An unregistered application can still call providers if `fetch-registry=true`, the registry URL is correct, and the HTTP client integrates with LoadBalancer.

Example consumer needing to call a service by logical name:

```java
@Configuration
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
```

```java
String result = restTemplate.getForObject(
        "http://catalog-service/api/products/42",
        String.class
);
```

This call requires `fetch-registry=true` and a configured Eureka client implementation. Without `@LoadBalanced`, `catalog-service` may be interpreted as a regular DNS hostname rather than a service ID.

## 10. Registry Cache and Update Latency

When `fetch-registry=true`, the client typically keeps a local copy of the registry and refreshes it periodically. This prevents discovery calls from hitting the server on every request, but it also means data can lag:

- Newly registered instances may not appear immediately in a consumer's cache.
- Deregistered instances may remain visible for a period of time.
- Peers or servers may temporarily hold differing states during network disruptions.
- LoadBalancer may maintain its own cache or supplier list depending on configuration.

`eureka.client.registry-fetch-interval-seconds` tunes the registry fetch period in Spring Cloud Netflix versions that support this property. Only lower the interval after weighing the extra load on Eureka Server against the benefit of fresher data. Never treat aggressive polling as a cure-all for stale instances; health checks, leases, deregistration, and request error handling still need proper design.

If a service ID does not show up, check whether the provider has registered, whether the consumer has `fetch-registry=true`, whether the Eureka URL is right, and whether the consumer points to the expected registry/region.

## 11. Common Configuration Errors

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Provider does not appear on dashboard | `register-with-eureka=false`, wrong URL, or connection error | Enable registration; check `defaultZone`, logs, and network |
| Consumer cannot find provider | `fetch-registry=false` or registry has no instance yet | Enable fetch; check service name and registration status |
| Application registers but cannot call other services | Register enabled, fetch disabled | Enable `fetch-registry=true` if making outbound calls |
| Application calls other services but cannot be discovered by others | Fetch enabled, register disabled | Enable `register-with-eureka=true` if exposing APIs |
| Standalone Eureka Server appears as its own client | Embedded Eureka Client is still registering | Set `register-with-eureka=false` for standalone server |
| Eureka peers do not exchange registry as expected | Peer disabled register/fetch or wrong peer URL | Enable both flags and declare reachable peer URLs |
| `DiscoveryClient` returns an empty list | Fetch not completed, wrong service ID, empty registry, or stale cache | Check flags, dashboard, cache, and logs |
| Old instances are still returned | Cache/fetch interval, lease, or incomplete deregistration | Check refresh interval and instance lifecycle |

## 12. Pre-Deployment Checklist

- [ ] Determine whether the application exposes APIs that other services must discover.
- [ ] Determine whether the application calls other services using service discovery.
- [ ] Set `register-with-eureka` according to registration needs.
- [ ] Set `fetch-registry` according to lookup needs.
- [ ] Configure `defaultZone` to point to the appropriate Eureka Server or peers.
- [ ] Verify `spring.application.name`, instance ID, hostname/IP, and advertised port.
- [ ] If calling services by logical name, configure Spring Cloud LoadBalancer on the HTTP client.
- [ ] Check the dashboard and `DiscoveryClient` to confirm registry contents.
- [ ] Account for cache/fetch latency when testing newly started or stopped instances.
- [ ] For standalone Eureka Server and peer clusters, use separate configurations suited to the topology.

The two flags `register-with-eureka` and `fetch-registry` represent two independent needs: publishing the application's own instance and downloading instance information for other services. Provider-only enables registration; consumer-only enables fetching; microservices typically do both; standalone Eureka Servers normally disable both on their embedded Eureka Client. Choosing settings based on actual inbound and outbound flows ensures Eureka Client plays the exact role your application requires.
