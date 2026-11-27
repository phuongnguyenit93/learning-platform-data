# Generating a Unique instanceId When Running Multiple Replicas

When running multiple replicas of the same microservice, the replicas must share the same service name so consumers find them in one group, while each replica needs its own instance identifier. If two processes register with the same `instanceId`, the registry may treat them as the same registration, overwrite their information, or make updates and deregistration unpredictable depending on the implementation.

Spring Cloud represents replica information via `ServiceInstance` and service registration abstractions. For Consul, the commonly used property is `spring.cloud.consul.discovery.instance-id`; for Eureka, the corresponding property is `eureka.instance.instance-id`. This lesson covers how to choose an ID, configure it per registry, run multiple local processes, and verify that instances are registered distinctly.

## 1. Distinguishing Service ID and Instance ID

A service can have multiple instances providing the same functionality. For example, three `order-service` processes may run on three different ports or hosts.

| Property | Example | Purpose |
| --- | --- | --- |
| Service ID / service name | `order-service` | Groups replicas into the same logical service so consumers can look it up by name. |
| Instance ID | `order-service:node-a:8081` | Distinguishes a specific registration from other replicas. |
| Host / IP | `10.0.0.21` | Address reachable by consumers or health checkers. |
| Port | `8081` | Port of the instance. |
| Metadata | `version=v2`, `zone=az-a` | Additional information for observability or filtering instances when supported by the implementation. |

The key principle is **same service name, different instance IDs**. If each replica sets `spring.application.name` to a different value, consumers looking up `order-service` will not automatically group those names together.

Three-instance example:

```text
Service ID: order-service

Instance ID                     Host          Port
order-service:node-a:8081       10.0.0.21     8081
order-service:node-b:8081       10.0.0.22     8081
order-service:node-c:8081       10.0.0.23     8081
```

The registry uses the service ID to group instances and the instance ID to distinguish each registration. The exact uniqueness scope depends on the registry: Consul requires the service ID to be unique within the registering agent/node; Eureka identifies instances within an application by instance ID. Therefore, when designing IDs for multi-node systems, generate values that are unique across the entire scope the registry uses to look up and update instances.

## 2. Choosing an Instance ID Generation Strategy

A good instance ID should be unique within the registry's scope, easy to trace in logs, and stable enough to manage the registration lifecycle. Several common strategies exist.

### 2.1. Combining Hostname and Port

This is a straightforward option for applications running directly on virtual machines or physical hosts:

```text
order-service:<hostname>:<port>
```

For example, `order-service:app-node-02:8081`. On the same host, processes using different ports get different IDs. Across different hosts, the hostname distinguishes instances even when they use the same port.

This strategy works well when hostnames are managed to be stable and unique within the deployment scope. If multiple containers share the same hostname or run in a shared network mode, add another component such as the container ID or a dedicated `INSTANCE_ID` variable.

### 2.2. Using a UUID

A UUID can be generated at application startup:

```text
order-service:550e8400-e29b-41d4-a716-446655440000
```

UUIDs virtually eliminate collision risk, even when multiple instances share the same host and port namespace. However, generating a new UUID on each startup changes the ID after a restart. The old registration may linger for a period until deregistration, health checks, or lease expiration cleans it up. Use UUIDs when instances are ephemeral and the registry has an appropriate registration reclamation mechanism.

### 2.3. Using Deployment Platform Identifiers

In Docker or Kubernetes, the platform can supply a hostname, container ID, pod name, or pod UID. These are usually strong identifier sources because values are generated per replica.

- With Docker, you can pass `INSTANCE_ID` from the container name or a dedicated value in Compose.
- With Kubernetes, the pod UID is a unique identifier for a Pod across the cluster's lifetime; you can inject it into the container via the Downward API.
- With VM platforms, you can use the hostname or an instance ID supplied by the cloud provider.

Do not rely solely on the service name or a shared load balancer hostname. Instances behind a load balancer need separate registrations with addresses directly reachable by consumers or health checkers.

### 2.4. Choosing a Stable vs. Ephemeral ID

| Strategy | Advantages | Limitations | Suitable Cases |
| --- | --- | --- | --- |
| Hostname + port | Readable, stable when a process restarts on the same host/port | May collide if hostnames are not unique or multiple containers share network identity | VMs, physical hosts, multiple local processes |
| UUID on each startup | Extremely low collision probability | ID changes after restart; old registrations must be cleaned up | Ephemeral workers or containers |
| Container ID / Pod UID | Tied to the platform's instance lifecycle | ID changes when a new container/Pod is created; must be injected properly into the app | Docker, Kubernetes |
| `INSTANCE_ID` supplied by deployment | Explicit, easy to control and test | Pipeline or manifests must guarantee no duplicate assignment | Environments with standardized deployment workflows |

For multiple processes running locally, combining service name and port is sufficient if each process has its own port. For production, let the deployment platform assign an explicit, unique ID and decide whether the ID needs to persist across restarts.

## 3. Configuring Instance ID for Consul

Spring Cloud Consul Discovery lets you configure the registration ID via `spring.cloud.consul.discovery.instance-id`. Common configuration example in `application.yml`:

```yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      discovery:
        register: true
        instance-id: ${INSTANCE_ID:${spring.application.name}:${HOSTNAME:localhost}:${server.port}}
        health-check-path: /actuator/health
        health-check-interval: 10s

server:
  port: ${SERVER_PORT:8080}
```

In this example:

- `spring.application.name` is always `order-service` for every replica.
- `instance-id` prefers the `INSTANCE_ID` environment variable if provided.
- If `INSTANCE_ID` is not set, the fallback combines the service name, `HOSTNAME`, and port.
- `server.port` can be varied per process using `SERVER_PORT`.

Make sure the fallback values are genuinely unique in your environment. On some local machines, `HOSTNAME` may be unset or set to a generic value; in that case, the `localhost` fallback distinguishes processes only if their ports differ. If there is any chance of running the same port in separate network namespaces with identical hostnames, pass an explicit `INSTANCE_ID`.

`instance-id` only identifies the registration. It does not replace the host address, port, or health check. The Consul Agent must still be able to reach each instance's health endpoint.

## 4. Configuring Instance ID for Eureka

With Eureka Client, the corresponding property is `eureka.instance.instance-id`. You can use the same ID convention:

```yaml
spring:
  application:
    name: order-service

server:
  port: ${SERVER_PORT:8080}

eureka:
  instance:
    instance-id: ${INSTANCE_ID:${spring.application.name}:${HOSTNAME:localhost}:${server.port}}
    prefer-ip-address: true
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:http://localhost:8761/eureka/}
```

`spring.application.name` determines the application/service name in Eureka; `eureka.instance.instance-id` distinguishes instances within that application. `prefer-ip-address` affects the host information Eureka publishes to clients rather than generating a unique instance ID. Ensure the published IP or hostname is reachable from consumers.

If both Consul and Eureka are present in the same application, decide explicitly whether registering with both registries is intentional. Do not copy configuration from one registry to another and assume every property has the same meaning.

## 5. Running Two Local Instances with Different IDs

Assume Consul is running at `localhost:8500` and the JAR has been built to `target/order-service.jar`. Open two separate PowerShell terminals.

First terminal:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SERVER_PORT = "8081"
$env:INSTANCE_ID = "order-service:local:8081"
java -jar target/order-service.jar
```

Second terminal:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:SERVER_PORT = "8082"
$env:INSTANCE_ID = "order-service:local:8082"
java -jar target/order-service.jar
```

Both processes share the same `spring.application.name` and connect to Consul, but have different ports and instance IDs. Once started successfully, the registry should display two registrations for `order-service`.

On Linux or macOS, you can pass environment variables per command:

```bash
SPRING_PROFILES_ACTIVE=local SERVER_PORT=8081 \
INSTANCE_ID=order-service:local:8081 \
java -jar target/order-service.jar

SPRING_PROFILES_ACTIVE=local SERVER_PORT=8082 \
INSTANCE_ID=order-service:local:8082 \
java -jar target/order-service.jar
```

If running multiple instances from an IDE, create two Run Configurations with the same main class and profile, giving each configuration its own `SERVER_PORT` and `INSTANCE_ID`. Avoid leaving stale environment variables in the terminal or IDE that override the values you just set.

## 6. Assigning Instance IDs in Docker and Kubernetes

### 6.1. Docker Compose

Each container can receive a unique ID through environment variables. For example:

```yaml
services:
  order-a:
    image: example/order-service:1.0
    environment:
      SPRING_PROFILES_ACTIVE: docker
      SERVER_PORT: 8080
      INSTANCE_ID: order-service:order-a
      CONSUL_HOST: consul

  order-b:
    image: example/order-service:1.0
    environment:
      SPRING_PROFILES_ACTIVE: docker
      SERVER_PORT: 8080
      INSTANCE_ID: order-service:order-b
      CONSUL_HOST: consul
```

Both containers can listen on port `8080` because each container has its own network namespace. Their instance IDs must still differ. Consul must be able to reach each container's address and port; network settings and registered addresses should match the actual topology.

### 6.2. Kubernetes

Kubernetes can inject the Pod UID into an environment variable using the Downward API:

```yaml
env:
  - name: INSTANCE_ID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
  - name: POD_NAME
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
```

Then configure Spring to use it:

```yaml
spring:
  cloud:
    consul:
      discovery:
        instance-id: ${INSTANCE_ID}
```

The Pod UID is well suited for distinguishing existing Pods in the cluster. When a Pod is recreated, its UID changes; the registry must clean up the old registration via deregistration, health checks, or an appropriate synchronization mechanism. If operators need a more human-readable ID, you can combine the service name and Pod name, keeping in mind that Pod names can be reused over time; the Pod UID remains the element that guarantees uniqueness over the cluster's lifecycle.

## 7. Verifying Registered Instance IDs

After starting multiple replicas, verify the service name, instance ID, address, port, and health status.

### 7.1. Checking Consul

Retrieve the service's instance list via the Catalog API:

```bash
curl http://localhost:8500/v1/catalog/service/order-service
```

The response includes the registrations for `order-service`; inspect the `ServiceID`, `ServiceName`, `Address`, and `ServicePort` fields. When health checks are configured, view each registration's status via:

```bash
curl http://localhost:8500/v1/health/service/order-service
```

Compare `ServiceID` across replicas to make sure there are no duplicates. The Catalog API shows present registrations; the Health API shows check statuses at query time.

### 7.2. Checking Eureka

In the Eureka Dashboard, open the `ORDER-SERVICE` application and inspect the instance list. You can also query the REST API:

```bash
curl http://localhost:8761/eureka/apps/ORDER-SERVICE
```

Check `instanceId`, hostname/IP, port, and instance status. If two processes share the same application name yet only one instance appears or instance details keep flipping, inspect `eureka.instance.instance-id` and registration logs.

### 7.3. Checking from a Consumer Application

A consumer can call `DiscoveryClient` to inspect the instance list:

```java
List<ServiceInstance> instances =
    discoveryClient.getInstances("order-service");

instances.forEach(instance -> System.out.printf(
    "service=%s host=%s port=%d uri=%s%n",
    instance.getServiceId(),
    instance.getHost(),
    instance.getPort(),
    instance.getUri()
));
```

`ServiceInstance` provides the address to call an instance; not all implementations expose the instance ID in the same standard property. If you need to observe the ID, check the metadata or the registry's native API rather than assuming `getServiceId()` is the instance ID.

## 8. Handling Duplicate Registrations and Stale Instances

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Only one replica appears despite running two processes | Both processes use the same instance ID or one registration overwrites the other | Assign distinct IDs and inspect the ID field directly in the registry. |
| Two instances share the same service name and port | Port configuration is shared in the same network namespace or registered address is incorrect | Assign distinct ports when running on the same host; in containers, verify the port and address published to the registry. |
| Old instance still appears after stopping the process | Shutdown did not deregister, agent lost connectivity, or lease/health check has not expired | Check deregistration, health checks, TTL, and registration cleanup intervals in the registry. |
| ID changes after every restart | A UUID or random value is used as the ID | Acceptable if instances are ephemeral and cleanup works; if stability is needed, use hostname/port or a platform-assigned ID. |
| Consumer calls the wrong address | Published host/IP is not reachable from the consumer | Check `ServiceInstance` and the registry client's hostname/IP, port, and network configuration. |
| Instance is registered but never selected | Health check is not passing or consumer filters instances by status | Inspect the health API and discovery/load balancing policies. |

A unique identifier does not replace health checks. Distinct IDs only let the registry tell registrations apart; an instance can still be unhealthy and excluded from the eligible list by consumers.

When an application shuts down gracefully, the registry client typically performs deregistration via the Spring lifecycle. For abruptly killed processes or network-partitioned nodes, health checks, leases, or TTLs help detect stale registrations. Configure detection intervals to match your system's fault tolerance and recovery requirements.

## 9. Instance ID Design Rules

1. Keep `spring.application.name` identical across all replicas of the same service.
2. Generate a unique instance ID within the registry scope using hostname + port, container/Pod identity, or a deployment-provided ID.
3. Never use the same hardcoded string across all replicas.
4. Decide explicitly whether the ID needs to remain stable across restarts or only unique within a process lifecycle.
5. Never place passwords, tokens, personal data, or secrets in the ID or metadata.
6. Keep IDs short, readable, and composed of simple characters such as letters, digits, hyphens, or colons for convenience in logs and APIs.
7. Verify that the published host/port is reachable from both health checkers and consumers.
8. Test registration, health status, and deregistration; do not only verify that the application starts.

## 10. Key Takeaways

- Service ID identifies the service group; instance ID distinguishes each replica within the group.
- Consul uses `spring.cloud.consul.discovery.instance-id`; Eureka uses `eureka.instance.instance-id`.
- Hostname + port suits multiple local/VM processes; container ID or Pod UID suits ephemeral environments; UUIDs are easily unique but change across restarts.
- All replicas of the same service should share `spring.application.name` and have distinct instance IDs.
- Verify registrations via the Consul Catalog/Health API or Eureka Dashboard/REST API, then confirm consumers see the expected instances.
- A unique instance ID does not guarantee instance health; health checks and deregistration still need to be configured properly.

When every replica has its own identifier and an accurate reachable address, the registry can manage each instance's lifecycle cleanly, and `DiscoveryClient` and Spring Cloud LoadBalancer have complete information to locate and select an appropriate replica.
