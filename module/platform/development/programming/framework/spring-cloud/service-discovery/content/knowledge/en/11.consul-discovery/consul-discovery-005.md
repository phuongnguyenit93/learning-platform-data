# Registering service-name, instance-id, Address, and Port

When an application registers with Consul, the registry needs two pieces of information: which logical service the instance belongs to, and which endpoint consumers must connect to when calling that instance. Spring Cloud Consul represents this information using `service-name`, `instance-id`, `address`, and `port`. If these values are incorrect, a record may still appear in the Consul Catalog, yet consumers will look up the wrong service ID, connect to the wrong host, or fail to reach the application port.

In Spring Cloud, `DiscoveryClient` looks up instances by service name. Consul stores each instance as a service registration attached to a Consul Agent. The service name groups multiple instances; the instance ID distinguishes each registration; address and port form the endpoint consumers use.

## 1. Four Core Fields in a Service Registration

| Field | Meaning | Example |
|---|---|---|
| `Name` / service-name | Logical name of the service; multiple instances can share the same name | `inventory-service` |
| `ID` / instance-id | Unique identifier of a registration on a Consul Agent | `inventory-service:inventory-1` |
| `Address` | Hostname or IP reachable by consumers | `10.20.0.15` or `inventory-1.internal` |
| `Port` | Port the application listens on and consumers can reach | `8081` |

Example with three instances of the same service:

```text
service-name: inventory-service
  ├── instance-id: inventory-1  -> 10.20.0.15:8081
  ├── instance-id: inventory-2  -> 10.20.0.16:8081
  └── instance-id: inventory-3  -> 10.20.0.17:8081
```

The consumer looks up `inventory-service`; Consul returns the list of registered instances for that name. The load balancer then picks an instance to send the request. Do not pass an instance ID as the service name when calling `DiscoveryClient`, unless the application intentionally designs service IDs that way.

## 2. service-name: Logical Name for Consumer Lookups

In Spring Cloud Consul, `spring.cloud.consul.discovery.service-name` defines the registered service name. If not configured, the default value is taken from `spring.application.name`.

Example:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        service-name: inventory-service
```

In typical configurations, `service-name` can be omitted because `spring.application.name` already provides the same value. Declaring it explicitly is useful when the logical name in Consul needs to differ from the Spring application name.

Naming conventions should be stable, readable, and consistent between producers and consumers. For example, if the producer registers `inventory-service` while the consumer looks up `inventory`, `getInstances("inventory")` will find no registrations even though the Consul dashboard shows the service.

The service name is a group name, not a network address, and does not need to contain a host or port. All replicas of the same service should use the same service name; do not register `inventory-1` and `inventory-2` as separate service names if the goal is load balancing across replicas.

## 3. instance-id: Distinguishing Each Registration

`spring.cloud.consul.discovery.instance-id` specifies the ID that Spring Cloud Consul sends to the Consul Agent. Every service registration on the same agent must have a distinct ID. If two processes on the same node register the same service ID, one registration can overwrite or conflict with the other.

If omitted, Spring Cloud Consul generates a default instance ID based on the application name and instance identification details; the default expression typically takes the form:

```text
${spring.application.name}:${vcap.application.instance_id:${spring.application.instance_id:${random.value}}}
```

In containerized or orchestrated environments, consider using the hostname, pod name, or a separately assigned instance identity. The value should remain stable throughout an instance's lifecycle and differ across replicas running on the same agent.

Example:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        instance-id: ${spring.application.name}:${HOSTNAME:${random.value}}
```

In this example, the `HOSTNAME` variable gives each container/pod a unique ID; `${random.value}` acts as a fallback when the environment variable is absent. If multiple processes run on the same host and share a hostname, provide a separate `INSTANCE_ID` variable for each process:

```yaml
spring:
  cloud:
    consul:
      discovery:
        instance-id: ${spring.application.name}:${INSTANCE_ID:${HOSTNAME:${random.value}}}
```

Do not assign the same static instance ID to every replica. Conversely, avoid generating a new random ID on every restart if operations require tracking a stable replica identity and deregistration on shutdown is not guaranteed. For containers with distinct identities, hostname/pod name is typically the easiest choice to trace.

Consul scopes service IDs per agent/node. Therefore, the ID must be unique on the agent where the service is registered. In multi-node systems, it is still good practice to design globally distinguishable IDs so logs, dashboards, and operational tools remain unambiguous.

## 4. address: The Address Consumers Actually Reach

`spring.cloud.consul.discovery.address` is the address registered for the service instance. You can configure a hostname or an IP. When `address` is not explicitly set, Spring Cloud Consul uses the host/interface information detected by the application according to configuration.

Related properties:

| Property | Role |
|---|---|
| `spring.cloud.consul.discovery.hostname` | Hostname used when registering the service |
| `spring.cloud.consul.discovery.ip-address` | IP address used when registering the service |
| `spring.cloud.consul.discovery.prefer-ip-address` | Prefer registering an IP instead of a hostname when selecting an address |

Example registering an advertised IP:

```yaml
spring:
  cloud:
    consul:
      discovery:
        prefer-ip-address: true
        ip-address: 10.20.0.15
```

The IP `10.20.0.15` is merely an illustrative private network address. Replace it with an address actually routable from consumers. If your infrastructure has reliable DNS, you can register a hostname instead of an IP:

```yaml
spring:
  cloud:
    consul:
      discovery:
        prefer-ip-address: false
        hostname: inventory-1.internal
```

Critically, the registered address must be reachable from the consumer's network perspective. An address can be valid inside a container yet unreachable for consumers on another network. Common mistakes include:

- Registering `127.0.0.1` or `localhost`: consumers will connect to themselves.
- Registering an internal bridge IP reachable only from the same Docker host while consumers reside on other nodes.
- Registering a hostname that resolves only inside a container while consumers lack the same DNS search domain.
- Registering the IP of an administrative interface or an interface that does not accept application traffic.

Do not confuse the Consul Agent address with the service address. Applications typically send registrations to a local Consul Agent, but `Address` in the registration must be the application address consumers will call, not the agent address unless the agent also acts as the service proxy endpoint.

## 5. port: The Application Port

`spring.cloud.consul.discovery.port` specifies the port recorded in the service registration. If not configured, Spring Cloud Consul derives the application's server port when it can be determined.

Example:

```yaml
server:
  port: 8081

spring:
  cloud:
    consul:
      discovery:
        port: 8081
```

In many Spring Boot applications, the `port` property can be omitted because `server.port` already defines the application port. Setting it explicitly is useful when the advertised port differs from the default HTTP port or when configuring a dedicated endpoint.

With Docker/Kubernetes, distinguish the port inside the workload from the port published on the host:

| Model | Recommended Registered Address/Port |
|---|---|
| Services communicating on the same Docker network | Reachable service/container DNS and container port |
| Consumers calling through a Kubernetes Service | Service DNS/address and service port matching the call path |
| Consumers accessing pods directly | Pod IP and container port if network policy allows |
| Consumers outside the cluster via node port/load balancer | External address and port actually reachable by consumers |

For example: the application listens on port `8081` inside the container, while Docker publishes `18081:8081`. Consumers on the same Docker network usually call the container DNS on port `8081`; consumers outside the host may need the host address on port `18081`. Registering the wrong address/port pair causes Consul to return a valid-looking record that cannot accept connections.

## 6. Complete Configuration in Spring Boot

The example below registers an `inventory-service` instance with a Consul Agent at `localhost:8500`. The advertised service address is configured via environment variables so each environment provides the right endpoint:

```yaml
server:
  port: ${SERVER_PORT:8081}

spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      discovery:
        register: true
        deregister: true
        service-name: ${spring.application.name}
        instance-id: ${spring.application.name}:${INSTANCE_ID:${HOSTNAME:${random.value}}}
        prefer-ip-address: true
        ip-address: ${SERVICE_ADVERTISE_IP:10.20.0.15}
        port: ${SERVER_PORT:8081}
        tags:
          - version=v1
          - zone=ap-southeast-1a
        metadata:
          team: inventory
          environment: development
        health-check-path: /actuator/health
        health-check-interval: 10s
```

In this example:

- `register: true` allows the application to automatically register with Consul when discovery auto-registration is active.
- `deregister: true` allows deregistering on a controlled application shutdown.
- `service-name` is taken from `spring.application.name`, keeping the logical name consistent.
- `instance-id` uses a dedicated variable for the replica; if absent, it uses hostname and finally falls back to a random value.
- `ip-address` is the advertised address of the service, not the Consul Agent address.
- `port` is the port consumers connect to.
- `tags` is a list of string labels; `metadata` holds additional key/value pairs.
- The health check calls the Actuator endpoint so the Consul Agent evaluates instance status.

Replace `10.20.0.15` with the actual address of your runtime environment. Locally, `localhost` works if consumers run on the same machine; in containers, use DNS/IP on the shared network. Ensure the `/actuator/health` endpoint exists, is reachable from the Consul Agent, and has the appropriate Actuator dependency.

To register an HTTP health check via Actuator, add the Actuator dependency to the application:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Do not expose sensitive health details to public networks. If the endpoint requires authentication, configure health-check headers or an access mechanism supported in your Spring Cloud Consul version; ensure the agent can execute the check.

## 7. How Does the Consul Agent Receive Registrations?

Spring Cloud Consul communicates with the Consul Agent via the HTTP API. The agent stores the service registration attached to its node and participates in synchronizing data to the Consul Catalog.

A simplified API payload might look like this:

```json
{
  "ID": "inventory-service:inventory-1",
  "Name": "inventory-service",
  "Address": "10.20.0.15",
  "Port": 8081,
  "Tags": ["version=v1", "zone=ap-southeast-1a"],
  "Meta": {
    "team": "inventory",
    "environment": "development"
  },
  "Check": {
    "HTTP": "http://10.20.0.15:8081/actuator/health",
    "Interval": "10s"
  }
}
```

The Consul Agent receives this payload through its local agent service registration endpoint, such as `PUT /v1/agent/service/register`. Spring Cloud Consul builds the equivalent payload from configured properties; applications normally do not need to invoke this API manually.

To inspect services managed by the local agent:

```bash
curl http://localhost:8500/v1/agent/services
```

To look up a service in the Catalog:

```bash
curl http://localhost:8500/v1/catalog/service/inventory-service
```

To retrieve only instances passing health checks:

```bash
curl "http://localhost:8500/v1/health/service/inventory-service?passing=true"
```

`/v1/agent/services` reflects services managed by the local agent. `/v1/catalog/service/{name}` queries the catalog by service name. `/v1/health/service/{name}?passing=true` combines health check status to filter endpoints. These three APIs serve distinct inspection purposes.

## 8. tags and metadata: Attaching Information to Instances

Service name and instance ID are for identification; tags and metadata attach extra information for operations or instance filtering.

- `tags`: a list of string labels, commonly used for version, role, or deployment group.
- `metadata`: a key/value map; useful for fields like team, environment, build, or zone.

Example:

```yaml
spring:
  cloud:
    consul:
      discovery:
        tags:
          - version=v2
          - canary
        metadata:
          team: inventory
          release: 2026.11
```

Do not use tags to store secrets, tokens, or personal information. Tags and metadata do not automatically create routing rules across all consumers; applications or Consul queries must actively use them. If you want consumers to pick only canary or a specific zone, implement explicit filtering criteria and verify the input instance list seen by LoadBalancer.

## 9. Using DiscoveryClient to Look Up by service-name

Consumers look up instances using the registered logical name. Example:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
class InventoryLocator {

    private final DiscoveryClient discoveryClient;

    InventoryLocator(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
```

Each `ServiceInstance` holds endpoint information, service ID, and metadata. The consumer can inspect host/port or URI:

```java
List<ServiceInstance> instances =
        discoveryClient.getInstances("inventory-service");

for (ServiceInstance instance : instances) {
    System.out.println("service=" + instance.getServiceId());
    System.out.println("host=" + instance.getHost());
    System.out.println("port=" + instance.getPort());
    System.out.println("uri=" + instance.getUri());
    System.out.println("metadata=" + instance.getMetadata());
}
```

In real applications, use Spring Cloud LoadBalancer to select an instance instead of always picking the first element. `DiscoveryClient` supplies registration data; LoadBalancer decides which instance serves the request.

## 10. Common Registration Errors

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Consul lists the service, but consumer lookup finds nothing | Producer `service-name` differs from the ID the consumer queries | Check `spring.application.name`, `service-name`, and `getServices()` |
| Multiple replicas overwrite each other or an instance is missing | Processes on the same agent share the same `instance-id` | Check `/v1/agent/services`; generate a unique ID per replica |
| Service appears in Catalog, but requests time out | `address` is unreachable or `port` is wrong | Test connectivity from the consumer's exact network namespace to `address:port` |
| Consumer mistakenly calls localhost | Registration advertises `127.0.0.1`/`localhost` | Configure a hostname/IP routable from consumers |
| Service registers the wrong port after changing server port | `spring.cloud.consul.discovery.port` overrides or is out of sync with `server.port` | Compare effective configuration with the Catalog payload |
| Health check turns critical | Wrong path, port, scheme, auth, or Actuator endpoint | Test URL from the Consul Agent; inspect check output and app logs |
| Restart leaves stale registrations behind | Shutdown does not deregister or ID changes on every run | Check `deregister`, instance ID, and critical timeout cleanup |
| Service exists on only one Consul Agent | Producer registered with a different agent or agent is inactive | Check `spring.cloud.consul.host`, port, and each node's local agent |

### 10.1. Checking Effective Configuration

Spring Boot allows profiles or environment variables to override YAML values. If registration is incorrect, inspect variables such as `SPRING_APPLICATION_NAME`, `SERVER_PORT`, `CONSUL_HOST`, `SERVICE_ADVERTISE_IP`, `INSTANCE_ID`, and `SPRING_CLOUD_CONSUL_DISCOVERY_*`. Never print secrets or ACL tokens to logs.

Actuator can help inspect configuration properties in development if the corresponding endpoint is enabled and secured. Never expose `/actuator/env` or `/actuator/configprops` publicly in production.

## 11. Checklist Before Registering a Service in Consul

- [ ] `spring.application.name` or `service-name` matches the logical name consumers look up.
- [ ] `instance-id` is unique for every replica on the same Consul Agent.
- [ ] `address` is a hostname/IP actually reachable by consumers.
- [ ] `port` is the correct application port from the consumer's network perspective.
- [ ] Service address is clearly distinguished from the Consul Agent address.
- [ ] `register` and `deregister` align with the application lifecycle.
- [ ] Health check targets the right endpoint, scheme, port, and has access permissions.
- [ ] Tags/metadata contain only necessary information, with no secrets.
- [ ] Verified agent services, Consul Catalog, and health API.
- [ ] Consumer uses the exact service name and LoadBalancer receives the expected list.
- [ ] Tested multiple replicas, restarts, shutdowns, and instance disconnect scenarios.

## References

- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Configuration Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Consul — Register a Service](https://developer.hashicorp.com/consul/docs/services/usage/register-services)
- [Consul Agent HTTP API — Service Registration](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [Consul HTTP API — Catalog](https://developer.hashicorp.com/consul/api-docs/catalog)
- [Consul HTTP API — Health](https://developer.hashicorp.com/consul/api-docs/health)
