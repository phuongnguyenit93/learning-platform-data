# Configuring instanceId, hostname, and prefer-ip-address

When a Spring Cloud application registers with Eureka Server, the registry needs to distinguish each running instance and know which address consumers must connect to. Three properties commonly configured together are `eureka.instance.instance-id`, `eureka.instance.hostname`, and `eureka.instance.prefer-ip-address`.

`instance-id` identifies a specific instance. `hostname` provides the published host name. `prefer-ip-address` determines whether Eureka prioritizes the hostname or the IP address in the registered instance metadata. Misconfiguration can cause multiple replicas to overwrite each other's records or cause Eureka to show an instance as `UP` while consumers cannot connect to it.

In the `SPRING_CLOUD_SERVICE_DISCOVERY` module, these properties belong to Eureka Client configuration and tie directly into the goal of discovering instances by service name. You must distinguish between the logical service name, the instance identifier, and the network address: they solve three different needs.

## 1. Three Pieces of Information with Distinct Roles

A service may run multiple instances. For example, `payment-service` has three replicas:

| Field | Example | Purpose |
|---|---|---|
| Service name | `payment-service` | Groups instances providing the same logical service; usually taken from `spring.application.name`. |
| Instance ID | `payment-service:pay-02:8082` | Distinguishes one specific running instance within the service group. |
| Hostname/IP | `payment-02.internal.example` or `10.20.0.22` | Host address that consumers use to connect. |
| Port | `8082` | Port on which the instance serves the corresponding protocol. |

In Eureka, instances with the same service name are grouped under one application. Each instance has its own information, typically represented by `InstanceInfo`, including instance ID, hostname, IP, port, status, and metadata.

Consumers look up services by service name, such as `payment-service`. The Eureka client supplies the matching instance list; Spring Cloud LoadBalancer selects one instance and uses its host/port to send the request. `instance-id` helps the registry manage the right record, but it is not the address consumers connect to.

## 2. Configuring `eureka.instance.instance-id`

`eureka.instance.instance-id` is the identifier of an instance in Eureka. Every concurrently running replica of the same application needs its own ID so the registry can tell records apart.

Example:

```yaml
spring:
  application:
    name: payment-service

server:
  port: 8082

eureka:
  instance:
    instance-id: payment-service:payment-02:8082
```

In this example:

- `payment-service` is the application name.
- `payment-02` is the replica identifier.
- `8082` is the port the application uses.

The ID format is not restricted to the example above. You can build the ID from hostname, pod name, container ID, workload UID, or an identifier assigned by your deployment pipeline. What matters is that the ID is unique among active instances of the same application and remains stable over an instance's lifecycle.

### 2.1. Why Must the Instance ID Be Unique?

Eureka uses the combination of application name and instance ID to identify a record during registration, heartbeats, status updates, and deregistration. If multiple replicas register with the same ID under the same application, operations can collide on the same record. The dashboard may show only one instance, or one instance's data may be overwritten by another.

Common mistakes:

- Hardcoding `payment-service` as the instance ID for every replica.
- Using only `server.port` when multiple containers run on the same internal port.
- Setting the same `INSTANCE_ID` environment variable across all pods.
- Generating an ID that changes continuously within a single process, making registration tracking difficult.

### 2.2. Generating IDs by Deployment Environment

For VMs or servers with distinct hostnames, you can build the ID from service name, hostname, and port:

```yaml
eureka:
  instance:
    instance-id: "${spring.application.name}:${spring.cloud.client.hostname}:${server.port}"
```

For containers or Kubernetes, you can pass a unique identifier per workload:

```yaml
eureka:
  instance:
    instance-id: "${spring.application.name}:${INSTANCE_ID:${HOSTNAME:local}}:${server.port}"
```

`INSTANCE_ID` should be supplied by the deployment platform with a unique value per replica. `HOSTNAME` inside a container is typically the container or pod name; verify its actual value rather than assuming it is a DNS name reachable by consumers.

If a single machine runs multiple instances with the same hostname and internal port, include the PID, container ID, pod UID, or replica identifier in the ID. Avoid relying solely on hostname when that hostname is shared across multiple processes.

### 2.3. Unique Yet Traceable IDs

A random ID can reduce collision risk, but operators will struggle to map the record back to the workload. Choose an ID structure informative enough to locate the right instance, for example:

```text
payment-service:payments-7f9c8d6b6f-k2m4p:8082
```

Never put passwords, tokens, personal information, or sensitive data into the instance ID. The ID frequently appears in dashboards, logs, and registry APIs.

## 3. Configuring `eureka.instance.hostname`

`eureka.instance.hostname` sets the hostname that the Eureka client advertises for the instance. If not explicitly configured, the client usually infers the hostname from the runtime environment. The auto-detected value may be unsuitable when the machine has multiple network interfaces, runs in a container, or uses private internal DNS.

Example hostname declaration:

```yaml
spring:
  application:
    name: payment-service

server:
  port: 8082

eureka:
  instance:
    hostname: payment-02.internal.example
    prefer-ip-address: false
    instance-id: "${spring.application.name}:payment-02:${server.port}"
```

When hostname is preferred, consumers receive a DNS name address in the instance info. Consumers must be able to resolve this name via DNS or the corresponding name resolution mechanism and must have a network path to the IP address returned by that name.

### 3.1. The Hostname Must Be Visible from the Consumer Side

A hostname might be valid on the provider machine without being reachable by other consumers. For example:

- `localhost` and `127.0.0.1` only point to the consumer's own machine or container.
- A hostname that exists only in the provider's `/etc/hosts` does not automatically exist on consumers.
- A DNS name from one subnet may not resolve from another VPC or cluster.
- A hostname pointing to a management IP might not expose the business port to consumers.

Test DNS resolution from the actual consumer environment. If a service runs in Kubernetes, pod hostnames may only be stable and resolvable when using a StatefulSet/headless Service or appropriately configured DNS records. With a standard Deployment, pods can be recreated with new names and IPs.

### 3.2. Hostname and Bind Address Are Two Separate Things

`server.address` controls the interface on which the Spring Boot web server listens. `eureka.instance.hostname` controls the hostname in the registration record. For example, an application can bind on `0.0.0.0:8082` while advertising `payment-02.internal.example` to consumers.

Never advertise `0.0.0.0` as a target address. It is a wildcard address used for binding on all IPv4 interfaces, not a host that consumers should call.

## 4. Configuring `eureka.instance.prefer-ip-address`

`eureka.instance.prefer-ip-address` determines whether the Eureka client prioritizes publishing the IP address instead of the hostname in instance information.

| Value | General Behavior |
|---|---|
| `false` | Prefers the configured or detected hostname. This is the common default. |
| `true` | Prefers the instance's IP address. If `eureka.instance.ip-address` is set, the explicitly configured value may be used; otherwise, the client relies on the detected IP address. |

Example:

```yaml
eureka:
  instance:
    prefer-ip-address: true
```

When enabling this flag, ensure the selected IP is routable from consumers. A machine can have multiple interfaces such as management, storage, public, and application networks. If the client picks the wrong interface, the registry may contain an IP that is valid on the provider machine but unreachable from other services.

### 4.1. Specifying an IP Explicitly with `eureka.instance.ip-address`

If you know the exact address reachable by consumers, you can configure the IP explicitly:

```yaml
eureka:
  instance:
    ip-address: 10.20.0.22
    prefer-ip-address: true
```

When using an environment variable:

```yaml
eureka:
  instance:
    ip-address: ${EUREKA_INSTANCE_IP:10.20.0.22}
    prefer-ip-address: true
```

Do not hardcode one machine's IP into configuration shared across all replicas. If each pod has its own IP, the deployment platform must inject the right IP per pod or let the client detect it in a controlled manner.

### 4.2. IP Auto-Detection and Selecting Network Interfaces

If `eureka.instance.ip-address` is not set, Spring Cloud can use network information detected from the environment. On machines with multiple interfaces, you can configure `spring.cloud.inetutils` to restrict preferred addresses or ignore unwanted interfaces.

Illustrative example:

```yaml
spring:
  cloud:
    inetutils:
      preferred-networks:
        - '10\.20\..*'
      ignored-interfaces:
        - 'docker0'
        - 'veth.*'

eureka:
  instance:
    prefer-ip-address: true
```

`preferred-networks` and `ignored-interfaces` use regular expressions to select or exclude networks respectively. Specific configuration must match the interface names and IP ranges in your actual environment. After making changes, verify the published IP in the registry; do not infer that the configuration took effect merely because the application started up cleanly.

## 5. Combining All Three Properties in One Configuration

The example below configures a `payment-service` instance using a hostname:

```yaml
spring:
  application:
    name: payment-service

server:
  port: 8082

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
  instance:
    hostname: ${EUREKA_INSTANCE_HOSTNAME:payment-01.internal.example}
    prefer-ip-address: false
    instance-id: "${spring.application.name}:${INSTANCE_ID:payment-01}:${server.port}"
```

If consumers need to connect directly by IP, you can replace the instance section with:

```yaml
eureka:
  instance:
    ip-address: ${EUREKA_INSTANCE_IP:10.20.0.21}
    prefer-ip-address: true
    instance-id: "${spring.application.name}:${INSTANCE_ID:payment-01}:${server.port}"
```

In real configurations, `INSTANCE_ID`, `EUREKA_INSTANCE_HOSTNAME`, or `EUREKA_INSTANCE_IP` values must be supplied per replica. The same configuration file can be reused, but environment values must not be identical for fields that need to distinguish each instance.

`defaultZone` in the example is the Eureka Server address that the client connects to for registration and registry fetching. It differs from the hostname/IP published under `eureka.instance`: one identifies the registry endpoint, while the other identifies the service endpoint.

## 6. Choosing Configuration by Environment

| Environment | Typically Suitable Configuration | Notes |
|---|---|---|
| VM with internal DNS | Set `hostname`, `prefer-ip-address: false`. | DNS must resolve from every consumer. |
| VM with stable private IP | Set `ip-address`, `prefer-ip-address: true`. | IP must be routable and ports open across subnets. |
| Machine with multiple network interfaces | Use `preferred-networks`/`ignored-interfaces` or set IP explicitly. | Avoid selecting a management/storage interface by mistake. |
| Docker Compose on the same network | Use appropriate container DNS/hostname or IP on the shared network. | Do not publish `localhost` or a host-only bridge IP. |
| Kubernetes Deployment | Use Pod IP if the registry tracks individual pods; create a per-pod ID. | Pod IP and hostname can change when a pod is replaced. |
| Kubernetes StatefulSet | Can use stable DNS via ordinal/headless Service. | Ensure consumers can resolve cluster FQDNs. |
| Consumers on another network | Use DNS or IP routable across peered networks or gateways. | Check firewalls, routing, and TLS. |

No single `prefer-ip-address` value fits every system. Choose based on how consumers connect to providers and how your infrastructure manages addresses.

## 7. Common Mistakes

| Symptom | Possible Cause | How to Fix |
|---|---|---|
| Eureka shows only one instance despite running multiple replicas | Replicas share the same `instance-id` within one application. | Generate a distinct ID for each pod/container/process. |
| Instance appears but consumers cannot call it | Hostname does not resolve or IP is not routable from the consumer. | Check DNS, routing, and ports from the consumer environment. |
| Eureka advertises `localhost` or `127.0.0.1` | Client detected loopback or hostname is misconfigured. | Set a hostname/IP reachable by consumers. |
| Eureka advertises `0.0.0.0` | Confusing bind address with advertised address. | Configure a specific hostname/IP; keep wildcard only for binding if needed. |
| Published IP belongs to a management interface | Client auto-detected the wrong interface. | Set `ip-address` explicitly or configure `spring.cloud.inetutils`. |
| Instance ID changes unnecessarily on every restart | Using a random value or unstable identifier source. | Use pod UID/container ID/hostname aligned with the deployment lifecycle. |
| Two pods share the same hostname and port across different workloads | ID consists only of hostname and port. | Add pod UID, container ID, or a unique replica identifier. |
| HTTPS certificate verification error | Consumer connects via hostname/IP that does not match certificate SANs. | Issue a certificate matching the advertised address; keep hostname verification enabled. |

## 8. Verifying What Eureka Received

After configuring, check both the registry data and connectivity from the consumer side.

### 8.1. Checking on the Eureka Dashboard

Open the Eureka Dashboard in the management network and find the corresponding application, such as `PAYMENT-SERVICE`. Inspect each instance:

- Whether instance IDs differ across replicas.
- Whether the published hostname or IP matches expectations.
- Whether the port matches the port the application actually serves on.
- Whether the instance status matches its health condition.

If the dashboard shows only one replica, check `instance-id` before investigating the load balancer. If the dashboard shows multiple replicas but requests fail, check the host/port and networking.

### 8.2. Checking via the Registry API

In an authorized environment, the Eureka REST API can return application details:

```bash
curl -H "Accept: application/json" \
  http://localhost:8761/eureka/apps/PAYMENT-SERVICE
```

The path and authentication mechanism may vary based on context path and security settings. Inspect the `instanceId`, `hostName`, `ipAddr`, `port`, and `status` fields in the returned payload. Never expose the registry API to the public Internet without proper protection.

### 8.3. Checking from a Consumer

A consumer can use `DiscoveryClient` to see the exact addresses the application receives:

```java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class PaymentDiscoveryInspector {

    private final DiscoveryClient discoveryClient;

    public PaymentDiscoveryInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public void printInstances() {
        for (ServiceInstance instance :
                discoveryClient.getInstances("payment-service")) {
            System.out.printf(
                    "serviceId=%s, instanceId=%s, host=%s, port=%d, uri=%s%n",
                    instance.getServiceId(),
                    instance.getInstanceId(),
                    instance.getHost(),
                    instance.getPort(),
                    instance.getUri()
            );
        }
    }
}
```

`ServiceInstance#getHost()` reveals the host returned by the discovery client to the consumer. Next, test DNS resolution and port connectivity from the exact container, VM, or pod running the consumer. Testing from the provider can yield different results because the two sides have separate network namespaces and DNS resolvers.

## 9. Relationship with Load Balancing and Security

`instance-id` is not the load balancer's selection key in terms of network addressing. The load balancer uses the `ServiceInstance` list and host/port to dispatch requests. If IDs collide, the registry may lose records; if host/port is wrong, requests will fail even when IDs are unique.

The advertised address also affects TLS:

- If consumers call by hostname, the certificate must include a matching DNS SAN.
- If consumers call by IP, the certificate must include a matching IP SAN.
- Never disable hostname verification just to work around a misconfigured address.
- Never store tokens or passwords in the instance ID or metadata.
- Only open application ports to required consumers; protect Eureka's Dashboard and REST API.

When deploying behind NAT or port mapping, ensure both the advertised host and port form an endpoint reachable by consumers. Setting `hostname` or `prefer-ip-address` accurately will not fix broken port mapping.

## 10. Production Configuration Checklist

- `spring.application.name` is stable and identical across replicas of the same service.
- `eureka.instance.instance-id` is unique among concurrently running instances and traceable to a workload.
- `hostname` is a DNS name resolvable from consumers, or `ip-address` is an address with a valid route.
- `prefer-ip-address` reflects the network architecture's hostname/IP choice.
- When multiple network interfaces exist, the preferred IP or interface is configured explicitly.
- The advertised HTTP/HTTPS port matches the endpoint consumers actually call.
- Each replica receives distinct environment values for fields that must be unique.
- Records have been verified in the Eureka Dashboard or REST API after startup.
- Connectivity from the consumer environment has been verified, including DNS, routing, firewall, and TLS.
- Internal registry data and metadata are not exposed outside administrative boundaries.

## Conclusion

`eureka.instance.instance-id` identifies each running instance; `eureka.instance.hostname` specifies the advertised hostname; `eureka.instance.prefer-ip-address` determines whether IP or hostname is preferred in instance metadata. These three properties must be configured according to your network topology and actual deployment lifecycle.

Ensure instance IDs do not collide across replicas, advertised addresses are reachable from consumers, and ports/TLS match the real endpoints. After configuring, verify the data in Eureka and test connectivity from the consumer side to confirm discovery works properly.
