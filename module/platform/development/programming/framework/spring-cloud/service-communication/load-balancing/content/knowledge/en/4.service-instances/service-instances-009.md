# Service Discovery Across Local, Virtual Machine, and Container Environments

Spring Cloud LoadBalancer can select a replica only when the calling application knows the list of reachable `ServiceInstance`s. In local environments, this list is often declared statically for testing. When running on virtual machines or containers, replica addresses and counts change across deployments, so applications usually need a dynamic discovery source or platform-provided discovery mechanism.

What must remain consistent across every environment is the **service ID**. The calling application uses a logical name such as `catalog-service`; discovery resolves that name into instances with concrete network addresses; LoadBalancer selects one instance; the HTTP client sends the request to the chosen address. The differences between local, virtual machine, and container environments lie in how instances are created, how they advertise addresses, and how those addresses stay reachable from the calling application.

## 1. Service ID and instance addresses in each environment

An instance is typically represented by information such as host, port, secure flag, and metadata. For example:

| Attribute | Example | Role |
|---|---|---|
| Service ID | `catalog-service` | Logical name to look up the replica group |
| Host | `10.20.1.15` | Address the calling application can connect to |
| Port | `8081` | Port on which the application is listening |
| Secure | `false` | Indicates whether the instance uses HTTP or HTTPS per instance info |
| Metadata | `zone=az-a`, `version=v2` | Additional info that can be used for filtering or routing |

The service ID stays stable across deployments, whereas host and port can change. An instance may be restarted on another machine, moved to another IP, or replaced by a new container. Therefore, never hardcode a replica's IP address in client source code.

The address published by discovery must be an address reachable by **the calling application**. `localhost` points only to the calling process's own network namespace. If the calling application runs inside a container, `localhost:8081` refers to the caller container's port, not the target service container's port. This is one of the most common reasons a discovery configuration works on a personal machine yet fails once containerized.

## 2. Local environment: starting with a static list

When learning or testing LoadBalancer on a development machine, you can run two processes of the same service on two different ports. For example:

| Replica | Local address |
|---|---|
| `catalog-service` A | `http://localhost:8081` |
| `catalog-service` B | `http://localhost:8082` |

If you only need to test the instance-selection mechanism, `SimpleDiscoveryClient` lets you declare a static list without setting up Eureka or Consul:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

The calling application creates an HTTP client integrated with LoadBalancer. For example, with `RestClient`:

```java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Then the request uses the service ID:

```java
Product findProduct(RestClient.Builder builder, String id) {
    return builder.build()
            .get()
            .uri("http://catalog-service/api/products/{id}", id)
            .retrieve()
            .body(Product.class);
}
```

With a two-address static list, LoadBalancer can choose one of the two addresses according to the configured strategy. To test distribution, have each process return its own identifier such as `instance=A` or `instance=B`, then send multiple requests and observe the responses.

### Running multiple processes on the same machine

Each process needs its own listening port. For example, run the same application with `server.port=8081` and `server.port=8082`. If the application also registers itself with a registry, each process needs a distinct instance ID so the registry can tell them apart.

Example configuration for one process:

```yaml
spring:
  application:
    name: catalog-service

server:
  port: 8081
```

The second process can use the same application configuration while overriding the port to `8082`. With a registry, the instance ID should combine the service name with a distinguishing value such as port or environment variable. If two processes register the exact same instance ID, the registry may treat the later registration as an update to the earlier instance, leaving only one entry in the list.

Static lists fit lab exercises with a rarely changing topology. When adding or removing processes, operators must update configuration and restart or reload the application according to the mechanism in use. For environments with frequently changing replicas, a dynamic registry is more suitable.

## 3. Virtual machines: publishing routable addresses

In a virtual machine environment, each replica typically has its own IP address on an internal network or a DNS-managed hostname. Calling applications and instances must be able to reach one another over the network permitted by the infrastructure.

A registry such as Eureka or Consul can store registered instances. When `catalog-service` starts, it registers its service ID along with host address, port, and metadata. Calling applications query the registry through a discovery client; LoadBalancer receives the list and selects an instance.

Example Eureka configuration for an instance:

```yaml
spring:
  application:
    name: catalog-service

server:
  port: 8081

eureka:
  client:
    service-url:
      defaultZone: http://registry.internal:8761/eureka/
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${server.port}:${HOSTNAME:local}
```

This is an illustrative configuration example; registry address, IP resolution, and instance ID must be adjusted to your network and VM provisioning setup. When using Eureka, the application also needs the corresponding Eureka Client dependency and registry connection settings. With Consul, the application uses the Consul Discovery starter and configures the Consul agent/server for the environment.

### Choosing the right registration address

An instance may have multiple network interfaces: management IP, private IP, public IP, or an internal-only interface. The registered address must belong to a network reachable by consumers. For example, if all services communicate over a private subnet, registering the private IP generally makes more sense than the public IP.

Do not register `127.0.0.1` or `localhost` for a service meant to be called from other VMs. Loopback addresses only make sense inside the machine running that process. Also verify:

- Whether security groups, firewalls, and network ACLs allow consumers to connect to the application port.
- Whether DNS resolves hostnames to addresses reachable by consumers.
- Whether the registry is reachable from all applications needing to register or look up services.
- Whether instance IDs are unique when running multiple processes under the same service ID.
- Whether TLS, certificates, and hostnames match if requests use HTTPS.

### Registry, heartbeats, and expired instances

Dynamic registries typically track registration lifecycles using heartbeats, leases, or equivalent health mechanisms. When a process stops abruptly, the registry may not remove its entry immediately; for a period of time, consumers may still receive the address of an inactive instance.

Therefore, distinguish three states:

1. **Registered:** the registry stores the instance information.
2. **Connectable:** the consumer can open a connection to the published host and port.
3. **Ready to serve:** the target application can process requests per business requirements.

These three states are related but not identical. Heartbeats show that the process keeps renewing its registration; health checks or readiness signals help evaluate serving capability; network connectivity checks verify the consumer can reach that address.

## 4. Containers: distinguishing internal addresses from host addresses

Containers have their own network namespaces. Thus, `localhost` inside a container does not point to the host or to another container. When services run on the same Docker network, they usually communicate via service names or internal addresses provided by that network.

For example, a Docker Compose environment with these components:

```yaml
services:
  registry:
    image: example/registry
    ports:
      - "8761:8761"

  catalog-service:
    image: example/catalog-service
    environment:
      SERVER_PORT: 8081
      EUREKA_CLIENT_SERVICEURL_DEFAULTZONE: http://registry:8761/eureka/
    expose:
      - "8081"

  order-service:
    image: example/order-service
    environment:
      EUREKA_CLIENT_SERVICEURL_DEFAULTZONE: http://registry:8761/eureka/
```

In the example, `registry` is a service name on the Docker network and can be resolved via internal DNS by containers on the same network. Environment variables illustrate passing the registry address into the applications; verify property names against Eureka Client configuration and Spring Boot's environment variable binding rules.

### Which address does a container register?

If `order-service` calls `catalog-service` through a registry, the address `catalog-service` registers must be reachable from `order-service`'s network. Within the same Docker network, that is normally the container's address and internal application port, not the port published to the host.

For example, `ports: "18081:8081"` maps port 8081 inside the container to port 18081 on the host. Another container on the same network normally connects to port 8081 of the target container. If the registry advertises `localhost:18081`, the consumer container will try calling itself; if it advertises a host port reachable only from the host machine, the consumer container may fail to connect.

`expose` in Compose only documents the container's internal port and does not replace firewall rules or port publishing. Containers must share a network or have an appropriate network route to communicate.

### Docker DNS and Spring Cloud LoadBalancer

Docker Compose provides DNS for service names on a network. A name like `catalog-service` can resolve to the service's address within the network. However, DNS resolving a name does not mean Spring Cloud LoadBalancer has received a separate `ServiceInstance` list per replica.

If you want the client-side LoadBalancer to pick individual containers, you need a discovery provider publishing separate replicas or an appropriate supplier. If you only call through a DNS name for a multi-replica service, distribution may be handled by DNS or the platform's proxy/network layer; do not assume that is Spring Cloud LoadBalancer's instance selection.

## 5. Kubernetes: Pod-level discovery or platform Service

In Kubernetes, each Pod has its own IP and a relatively short lifecycle. A Kubernetes Service provides a stable address for a group of Pods; kube-proxy or the corresponding dataplane forwards traffic to eligible endpoints.

There are two common approaches:

| Approach | Target selection mechanism | Suitable when |
|---|---|---|
| Call Kubernetes Service DNS | Application calls stable DNS/ClusterIP; Kubernetes network dataplane distributes to Pods | You want to rely on platform load balancing and keep the application simple |
| Use Spring Cloud Kubernetes Discovery with LoadBalancer | Discovery supplies the list of endpoints/Pods; Spring Cloud LoadBalancer selects one instance client-side | You want the application to apply client-side strategies or process instance metadata |

If using Spring Cloud Kubernetes Discovery, add the discovery dependency compatible with your Spring Cloud Kubernetes version, configure permissions to read Kubernetes resources, and specify which endpoint types the application will discover. Service accounts and RBAC must grant only the required operations. Do not grant broader permissions than necessary merely to make discovery work.

A standard Kubernetes Service can hide the Pod list behind a ClusterIP. When an application calls Service DNS, requests go to the Service's virtual IP and the platform picks an endpoint. If the goal is for Spring Cloud LoadBalancer to select individual Pods, configure discovery to return the corresponding instances/endpoints rather than only returning a single ClusterIP address.

A Headless Service is an option when DNS needs to return Pod addresses instead of a single ClusterIP. Even so, headless DNS alone does not guarantee every HTTP client will receive an instance list and apply LoadBalancer algorithms. Verify the exact discovery provider, the data it returns, and how the HTTP client is integrated.

## 6. Comparing service discovery across environments

| Criterion | Local | Virtual machine | Container |
|---|---|---|---|
| Instance address | `localhost` with different ports | Routable private IP or hostname | Container IP/hostname on shared network or platform-published endpoint |
| Common discovery sources | `SimpleDiscoveryClient`, or locally run registry | Eureka, Consul, DNS, or infrastructure platform | Docker DNS, registries like Eureka/Consul, Kubernetes discovery, or Kubernetes Service |
| List updates | Usually manual configuration updates | Registry receives registrations and heartbeats | Follows container/Pod lifecycle or registry |
| Common pitfalls | Port conflicts, duplicate instance IDs | Registering loopback, firewalls, wrong network interface IP | Confusing localhost, confusing host port with container port, changing container IPs |
| How to verify | Call each port directly and call by service ID | Check registry, routes, DNS, and firewalls from consumer | Check network, DNS inside container, and instance address advertised by registry |

There is no single best discovery source for every environment. A local static list keeps lab exercises reproducible; a dynamic registry fits when replicas are created and destroyed independently; container-platform discovery can reduce the need to manage a registry yourself if it already meets routing needs.

## 7. Health checks and readiness in each environment

When discovery returns an instance, LoadBalancer can treat that instance as a candidate. Yet a registered address does not mean the application is ready to handle business traffic. Design readiness checks appropriate to the environment:

- **Local:** verify the process has opened its port and its health endpoint responds before placing the instance into test rotation.
- **Virtual machine:** combine registry status with health endpoints, process monitoring, and connectivity over the private network.
- **Container:** use the platform's readiness/liveness probes and discovery settings so requests are not sent to Pods that are not ready or have been removed from endpoints.

Spring Cloud LoadBalancer health checks, Spring Boot Actuator health indicators, and Kubernetes readiness probes serve different roles. They can work together but do not automatically replace one another. Define which source is the source of truth for instance status, probe frequency, and eviction window for failing instances to avoid routing requests to down replicas or prematurely dropping replicas that are still starting up.

## 8. Hands-on discovery testing from the consumer

You can use the same test script across all three environments:

1. Start at least two replicas of `catalog-service`, each with its own address and instance ID.
2. Confirm each replica can be called directly from the consumer's network environment.
3. Check the registry or discovery source to confirm the right service ID and instance addresses appear.
4. Send requests via an `@LoadBalanced` HTTP client using the URL `http://catalog-service/...`.
5. Have each instance return its own name or ID, then send multiple requests and observe distribution results.
6. Stop one replica or fail its readiness/health check, then measure how long it takes for the instance to drop from the candidate list.
7. Restart the replica and confirm the instance re-registers with a valid address.

When running in containers, perform connectivity checks from the consumer container itself or a container on the same network. A successful check from the host machine does not prove the consumer container can reach that address.

Network troubleshooting commands depend on which tools are available in the image. If the container lacks `curl`, `wget`, `nslookup`, or `getent`, use a diagnostic container on the same network or platform tools to verify DNS and TCP connectivity. Avoid baking debug tools into production images solely for temporary troubleshooting.

## 9. Diagnosing common errors

| Symptom | Possible cause | How to check |
|---|---|---|
| Works locally but fails in containers | Registry advertises `localhost` or a host port unreachable from containers | Inspect host/port in `ServiceInstance`, test from consumer container |
| Service is in registry but connection fails | Firewall, routing, wrong interface, or port | Try connecting directly from consumer to the registered address |
| Multiple replicas exist but registry shows one entry | Duplicate instance IDs or processes overwriting registrations | Check instance ID, hostname, and port of each replica |
| Requests hit stopped Pod/container | Registry has not removed instance, slow heartbeat/health, or stale cache | Compare registry, supplier cache, and health checks |
| Kubernetes Service works but client-side selection does not see Pods | Discovery returns ClusterIP instead of individual endpoints | Check discovery configuration and returned endpoint types |
| Service name fails to resolve | Mismatched service ID, provider not running, or client lacks LoadBalancer integration | Check service ID, dependencies, discovery client, and `@LoadBalanced` bean |

When investigating, record the service ID, instance ID, host, port, metadata, discovery source, and observation timestamp. Compare the address published by the registry against the address the consumer can actually connect to. This distinguishes discovery bugs from network configuration issues and HTTP client bugs.

## 10. Choosing the right discovery approach

For lab exercises on a single machine, start with `SimpleDiscoveryClient` and two local ports to clearly understand how a service ID maps to instances. When moving to multiple VMs, use a registry or DNS reachable from consumers and publish appropriate private addresses. When packaging with Docker, inspect network namespaces, service DNS, and registered internal addresses. On Kubernetes, decide explicitly whether to use platform Service routing or have Spring Cloud LoadBalancer pick endpoints client-side.

In every environment, the flow still begins with a service ID and ends with a reachable instance address. If requests fail, verify sequentially: the discovery source, the instance list returned by the supplier, readiness status, network addresses from the consumer's perspective, and LoadBalancer's selection result. When these layers are configured consistently, applications can keep calling services the same way even as replica counts and locations change across deployment environments.
