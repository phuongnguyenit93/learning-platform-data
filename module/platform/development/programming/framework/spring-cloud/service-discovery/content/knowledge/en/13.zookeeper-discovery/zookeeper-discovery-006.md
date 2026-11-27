# Configuring Service Name, instanceId, Address, and Root Directory

Spring Cloud Zookeeper Discovery registers service instances in Apache ZooKeeper so consumers can look up services by name. When configuring a service, four pieces of information must be defined: the logical service name, the instance identifier, the address/port consumers will call, and the root directory in ZooKeeper's znode tree.

These four settings are related but not interchangeable. The service name groups instances that provide the same capability; `instanceId` distinguishes individual running instances; the address and port define the network endpoint; the root path defines the namespace storing the registrations. If a provider and consumer use different root paths, or if a provider advertises an address only reachable from its own machine, service discovery will not work as expected.

In the `SPRING_CLOUD_SERVICE_DISCOVERY` module, Spring Cloud provides the `DiscoveryClient` and `ServiceRegistry` abstractions, and Spring Cloud Zookeeper maps these abstractions to ZooKeeper's znode-based registration and discovery mechanism.

## 1. How ZooKeeper Discovery organizes service registrations

ZooKeeper stores data as a znode tree. Each znode has an absolute path, for example `/services/production/payment-service/payment-01`. Spring Cloud Zookeeper Discovery uses a root path to group services and creates nodes representing instances.

With root path `/services`, service name `payment-service`, and instance ID `payment-01`, the structure can be visualized as:

```text
ZooKeeper ensemble
└── /services
    ├── payment-service
    │   ├── payment-01
    │   └── payment-02
    ├── order-service
    │   ├── order-01
    │   └── order-02
    └── inventory-service
        └── inventory-01
```

This is the conceptual structure of service discovery. Each instance's registration data is stored at its corresponding znode; the implementation may store a payload containing host, port, scheme, and metadata. Instances are typically represented as ephemeral znodes so the registration lifecycle is tied to the client's ZooKeeper session.

When a provider registers, Spring Cloud Zookeeper creates or updates the instance's znode. When the application deregisters or the ZooKeeper session expires, the ephemeral znode is deleted. Consumers use the discovery client to read instances belonging to the service name they need to call.

## 2. Service name: `spring.application.name`

The logical service name is usually declared using `spring.application.name`:

```yaml
spring:
  application:
    name: payment-service
```

Spring Cloud Zookeeper uses this application name as the service ID during registration and lookup, unless the application configures a custom service name via the corresponding discovery property. Instances of the same service must share the same service name so consumers can look them up as a group.

For example, three replicas of `payment-service` can all register under service name `payment-service`, even when running on three different machines or containers. When a consumer calls `DiscoveryClient.getInstances("payment-service")`, the discovery client returns the list of instances the registry currently holds for that service ID.

### 2.1. Naming rules

- Use a stable, functionally meaningful name, such as `payment-service` or `order-service`.
- All replicas of the same service use the same name.
- Do not include hostname, pod name, or IP in the service name; those belong to the instance.
- Avoid `/` in the service name because this name typically becomes a segment of the ZooKeeper path.
- Keep spelling consistent between providers and consumers, including letter casing.
- Change the service name only when changing logical boundaries or the discovery contract, because renaming impacts consumers looking up the old name.

The service name is not a network address. `payment-service` is the logical lookup key; each instance's hostname/IP and port provide the actual connection endpoint.

## 3. Instance ID: distinguishing individual running instances

`spring.cloud.zookeeper.discovery.instance-id` identifies a specific instance within a service. With multiple replicas sharing a service name, each instance ID must be distinct so they can coexist in the znode tree.

Example:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      discovery:
        instance-id: payment-01
```

If two replicas both register `payment-service` with `instance-id: payment-01`, they may operate on the same znode path. One instance may overwrite the other's data or encounter a node-already-exists error, depending on the registration method and implementation version. Ensure the ID is unique within a service name and root path.

### 3.1. Generating instance IDs per environment

You can construct the ID from hostname, port, or a workload identifier:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      discovery:
        instance-id: "${INSTANCE_ID:${HOSTNAME:payment-local}}"
```

In Kubernetes, you can pass the Pod name or Pod UID via environment variables. On VMs, you can use a stably managed hostname. If a single host runs multiple processes of the same service, add a differentiating component such as port or process identifier.

Example of a traceable ID:

```text
payment-service:payments-7f9c8d6b6f-k2m4p:8082
```

The ID format is an application convention. The value should remain stable for an instance's lifecycle, contain no `/` characters that alter path structure, and contain no passwords, tokens, or sensitive data.

### 3.2. Instance ID tied to ephemeral node lifecycle

A ZooKeeper ephemeral znode exists as long as the session that created it remains valid. When a client closes its session cleanly or the session expires, ZooKeeper deletes the ephemeral node. If the client only loses connectivity briefly while the session remains valid, the node can continue to exist while ZooKeeper waits for the client to reconnect.

Therefore, do not treat a brief TCP connection drop as proof that the instance has been removed from the registry. Conversely, if the session expires, the provider must establish a new session and re-register the instance. Inspect session state and znode records when investigating registration failures.

## 4. Advertised address and port

ZooKeeper stores information so consumers know an instance's network address. This address must be reachable from the consumer environment, not only from the provider process.

Spring Cloud Zookeeper Discovery provides commonly used properties:

| Property | Role |
|---|---|
| `spring.cloud.zookeeper.discovery.instance-host` | Hostname or host address advertised for the instance. |
| `spring.cloud.zookeeper.discovery.prefer-ip-address` | Prefers advertising an IP address instead of a hostname when auto-detecting addresses. |
| `spring.cloud.zookeeper.discovery.instance-port` | Port advertised for the instance when needing an explicit value. |
| `spring.cloud.zookeeper.discovery.instance-ssl-port` | SSL port advertised if the service exposes a corresponding secure endpoint. |

If not specified explicitly, the integration can infer host and port from the runtime environment. On hosts with multiple network interfaces or inside containers, verify auto-detected values carefully.

### 4.1. Preferring hostname

If consumers can resolve internal DNS, you can advertise a dedicated hostname for the instance:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      discovery:
        instance-host: payment-01.internal.example
        prefer-ip-address: false
        instance-port: 8082
```

Consumers must be able to resolve `payment-01.internal.example` and have network routing to port `8082`. A hostname present only in the provider's `/etc/hosts` or a subnet-local DNS zone will not automatically work for other consumers.

### 4.2. Preferring IP

If consumers can route directly to the instance's IP, you can enable:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      discovery:
        prefer-ip-address: true
        instance-port: 8082
```

When `prefer-ip-address` is enabled, the client prefers the IP address detected from the environment. If the machine has multiple interfaces, verify the actual IP advertised. You can use `instance-host` to specify an explicit host address if endpoint control is needed; after any change, verify the record in ZooKeeper or via a discovery client.

Never advertise `127.0.0.1`, `localhost`, or `0.0.0.0` as the address for consumers on other hosts. `0.0.0.0` is a wildcard bind address for servers, and loopback only points back to the host/container initiating the connection.

### 4.3. Port must match the actual endpoint

If the application listens on port `8082` while the registry advertises `8080`, consumers will call the wrong endpoint. In containers, internal ports and host-published ports may differ; determine whether consumers connect directly over the container network or through the host/gateway.

If using HTTPS, advertise the appropriate SSL port and ensure the scheme, certificate SANs, and hostname/IP used by consumers are compatible. An address may resolve yet TLS will still fail if the certificate does not match.

## 5. ZooKeeper root directory: `spring.cloud.zookeeper.discovery.root`

The `spring.cloud.zookeeper.discovery.root` property specifies the root znode used by Spring Cloud Zookeeper Discovery to store service registrations. The commonly used default is `/services`.

Example:

```yaml
spring:
  cloud:
    zookeeper:
      discovery:
        root: /services
```

With root `/services`, service name `payment-service`, and instance ID `payment-01`, the conceptual path is:

```text
/services/payment-service/payment-01
```

You can change the root to separate namespaces by environment or application group:

```yaml
spring:
  cloud:
    zookeeper:
      discovery:
        root: /services/production
```

Then `payment-service` instances are grouped under:

```text
/services/production/payment-service/payment-01
```

### 5.1. Providers and consumers must share the same root

If a provider registers under `/services/production` while a consumer looks up under `/services/staging`, the consumer will not see the service even though both connect to the same ZooKeeper ensemble.

Therefore, the root path is part of the discovery contract between providers and consumers. Manage it with consistent environment configuration, for example:

```yaml
spring:
  cloud:
    zookeeper:
      discovery:
        root: ${ZK_DISCOVERY_ROOT:/services/production}
```

All services in the same environment must receive the same `ZK_DISCOVERY_ROOT` value. If intentionally separating environments, ensure consumers only query the namespace of their matching environment.

### 5.2. Root path rules

- Use an absolute path starting with `/`, such as `/services` or `/services/production`.
- Avoid a trailing `/` unless necessary.
- Do not allow service names or instance IDs to contain `/` that alters the tree structure.
- Choose a stable namespace; changing the root prevents consumers from seeing registrations under the old root.
- Define ACLs on the root and child nodes so providers can register and consumers have read access as needed.
- Do not share the same root between production and development environments without explicit intent.

Whether the root znode already exists or is created automatically depends on configuration and integration version. In strict-ACL environments, pre-create paths and grant required permissions through ZooKeeper administration procedures rather than granting broad permissions to applications.

## 6. Complete provider configuration

Example of a `payment-service` registering with a ZooKeeper ensemble using a dedicated hostname and root for production:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      discovery:
        enabled: true
        register: true
        root: /services/production
        instance-id: "${INSTANCE_ID:${HOSTNAME:payment-01}}"
        instance-host: "${SERVICE_ADVERTISE_HOST:payment-01.internal.example}"
        prefer-ip-address: false
        instance-port: 8082

server:
  port: 8082
```

In this example:

- `spring.application.name` sets the service ID `payment-service`.
- `connect-string` is the ZooKeeper ensemble endpoint list the application connects to for registration and lookup.
- `root` sets the discovery namespace for the production environment.
- `instance-id` distinguishes the specific running instance.
- `instance-host` advertises the hostname reachable by consumers.
- `instance-port` advertises the business port.
- `register: true` allows the application to register itself.
- `enabled: true` enables discovery integration.

`connect-string` and `instance-host` serve two separate connection flows. `connect-string` points to ZooKeeper for the client to operate on znodes; `instance-host` is the address consumers will call after looking up the service.

## 7. Provider configuration using IP

If consumers reside on the same network with direct IP routing to instances, you can use this configuration:

```yaml
spring:
  application:
    name: payment-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      discovery:
        enabled: true
        register: true
        root: /services/production
        instance-id: "${INSTANCE_ID:${HOSTNAME:payment-01}}"
        prefer-ip-address: true
        instance-port: 8082

server:
  port: 8082
```

In this configuration, the IP detected from the environment is preferred. If the host has multiple interfaces, verify the actual IP and choose an explicit address-override mechanism appropriate for your version. Do not hardcode one shared IP across all replicas.

## 8. Consumer service lookup

A consumer must connect to the same ZooKeeper ensemble and use the same root path as the provider. Example:

```yaml
spring:
  application:
    name: order-service
  cloud:
    zookeeper:
      connect-string: zk-1.internal:2181,zk-2.internal:2181,zk-3.internal:2181
      discovery:
        enabled: true
        register: false
        root: /services/production
```

`register: false` is appropriate when the application only needs to look up services and should not register itself. If `order-service` also needs to be discoverable by other services, enable registration and configure its instance ID/address accordingly.

You can use `DiscoveryClient` to retrieve instances:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class PaymentServiceLookup {

    private final DiscoveryClient discoveryClient;

    public PaymentServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findPaymentInstances() {
        return discoveryClient.getInstances("payment-service");
    }
}
```

The result is a list of instances with host, port, URI, and metadata. Consumers can use Spring Cloud LoadBalancer to select an instance instead of selecting manually. If the list is empty, handle cases where the service is not yet registered, the root path is wrong, instances are not ready, or the session/registry is recovering.

## 9. Inspecting the znode tree and registration records

After the provider starts, you can use the ZooKeeper CLI in an administrative environment to inspect the path tree:

```text
ls /services/production
ls /services/production/payment-service
get /services/production/payment-service/payment-01
```

The first `ls` command shows service names registered under the root. The second lists instance IDs of `payment-service`. The `get` command reads the instance znode data; its contents depend on the serialization format of your Spring Cloud Zookeeper version.

You can also inspect via the discovery API on the consumer side:

```java
for (ServiceInstance instance :
        discoveryClient.getInstances("payment-service")) {
    System.out.println(instance.getInstanceId());
    System.out.println(instance.getHost());
    System.out.println(instance.getPort());
    System.out.println(instance.getUri());
}
```

Checking from the consumer is practically valuable because it shows the exact address the calling application receives after discovery processes ZooKeeper's data.

## 10. Sessions, ephemeral nodes, and deregistration

Service registration in ZooKeeper is typically based on ephemeral znodes. Unlike persistent znodes, an ephemeral znode is bound to the session that created it and deleted by ZooKeeper when the session expires or the client closes the session.

This yields important behaviors:

- When a provider shuts down gracefully, the client can close the session and the registration node is removed.
- When a provider is killed abruptly, the ephemeral node may not vanish instantly; ZooKeeper must detect that the session has expired.
- When the network is temporarily disrupted while the session remains valid, the znode may persist.
- When a session expires, the provider must establish a new session and re-register the instance.
- Consumers may take time to receive updates via watchers or discovery data refreshes.

Consequently, a delay exists between the moment a process dies and the moment the instance disappears from every consumer. Consumers still need timeouts, bounded retries, and connection-failure handling.

## 11. Common errors

| Symptom | Possible cause | Verification and resolution |
|---|---|---|
| Consumer cannot find service | Provider and consumer use different root paths. | Compare `spring.cloud.zookeeper.discovery.root` on both sides. |
| Service znode is missing | `register` or `enabled` is off, or application cannot connect to ZooKeeper. | Check configuration, startup logs, and write permissions on the root. |
| Only one instance visible despite multiple replicas | Replicas share the same `instance-id`. | Generate a unique ID from pod, container, hostname, or port. |
| Znode exists but consumer cannot call it | Advertised hostname/IP or port is unreachable from consumer. | Check DNS, routing, firewall, and endpoints from the consumer environment. |
| Consumer looks up the wrong environment | Shared root path or misconfigured namespace. | Separate root paths per environment and distribute consistent configs. |
| Instance still appears after process was killed | ZooKeeper session has not expired yet. | Check session state and timeout duration; do not rely solely on TCP disconnect. |
| Instance disappears during flaky network | Session expired due to prolonged drop or too-short timeout. | Check session timeout, network between client and ensemble, then monitor re-registration. |
| `NodeExists` error on registration | Instance ID znode already exists or registration lifecycle conflict. | Check instance ID, old session, and deregistration procedure. |
| `NoAuth` or `NoNode` error | Missing ACL permissions or root/parent path not yet prepared. | Check ACLs and path creation order per administrative policy. |

## 12. Security and operating the root path

ZooKeeper is shared coordination infrastructure, so broad permissions should not be granted to every application.

- Grant read permissions on discovery paths to consumers that need lookup access.
- Grant create, update, and delete permissions on instance nodes to providers within their own namespace.
- Use ZooKeeper ACLs and authentication according to platform policy.
- Protect client-to-ensemble connections with appropriate security configuration, including TLS/SASL if required by the environment.
- Never place secrets in service names, instance IDs, or metadata.
- Separate root paths by environment or tenant when registry isolation is needed.
- Monitor session expirations, ephemeral node counts, ACL errors, and ensemble response latency.
- Avoid manually deleting an entire root path while services are active, as it can wipe out registrations for many instances.

ACL, TLS, and SASL configuration details can vary by ZooKeeper, Curator, and Spring Cloud Zookeeper versions. Verify against your library versions and cluster policies before deploying.

## 13. Production configuration checklist

- `spring.application.name` is stable and identical across replicas of the same service.
- `instance-id` is unique within the service name and root path.
- Advertised hostname/IP is reachable from every consumer that needs to call the instance.
- Port and SSL port match actual endpoints.
- `root` is an absolute, stable path shared across providers and consumers in the same environment.
- `connect-string` points to the right ZooKeeper ensemble; do not confuse it with service instance addresses.
- Providers have permissions to create/register ephemeral nodes; consumers have permissions to read required paths.
- Session timeout suits network stability and failure-detection requirements.
- Empty instance lists, session expirations, and transient connection failures are handled.
- Znodes and `ServiceInstance` entries are verified from the consumer perspective after deployment.
- Never delete root paths or swap namespaces during active hours without a registration migration plan.

## Conclusion

In Spring Cloud Zookeeper Discovery, `spring.application.name` defines the logical service name, `spring.cloud.zookeeper.discovery.instance-id` distinguishes running instances, `instance-host`/`prefer-ip-address` together with port define the address consumers call, and `root` defines the znode namespace holding registrations. `connect-string` specifies the ZooKeeper ensemble the application connects to for registry operations.

Registrations are typically represented as ephemeral znodes bound to a ZooKeeper session. Therefore, generate unique instance IDs, advertise reachable addresses, share the same root path across providers and consumers, and handle session expirations and re-registration. Inspecting both the znode tree and `DiscoveryClient` results from a consumer confirms that discovery is configured properly.
