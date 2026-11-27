# Bind address, advertised address, and differences when running in containers

A Spring Boot application may listen on one network address while advertising a different hostname or IP to calling services. This distinction is especially critical when running in Docker or Kubernetes: the address seen by a process inside a container is not necessarily the address reachable by external clients.

In Spring Cloud, separate three concepts:

1. **Bind address:** the address on which the web server opens a socket to accept connections.
2. **Advertised address:** the hostname/IP and port published to the service registry, discovery clients, or calling systems.
3. **Client-reachable address:** the address and port a consumer can actually resolve, route to, and connect to from its own network namespace.

The three values may be identical on a simple VM, yet they frequently diverge when NAT, port mapping, service meshes, ingress, multiple NICs, or multiple network zones are involved. Picking the right addresses avoids the situation where the server is running fine while the service registry returns an unreachable endpoint.

## 1. What is a bind address?

The bind address specifies which machine interface/address the server socket listens on. In Spring Boot, the common properties are:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Here, the server listens on port 8080 across all suitable IPv4 addresses in the current network namespace. 0.0.0.0 is an IPv4 wildcard address, not a concrete IP address for another service to call.

If binding to a specific address:

~~~yaml
server:
  address: 10.20.4.15
  port: 8080
~~~

the server can bind only if 10.20.4.15 exists and is available inside the process's network namespace. If a container is assigned a different dynamic IP, the application may fail to start.

### 1.1. Wildcard addresses vs. specific addresses

| Address | Meaning when binding | Should it be advertised to consumers? |
| --- | --- | --- |
| 0.0.0.0 | Listen on all suitable IPv4 interfaces | No |
| :: | IPv6 wildcard; dual-stack behavior depends on OS/socket configuration | No |
| 127.0.0.1 | Accept only IPv4 loopback connections within the same network namespace | No for consumers in other namespaces |
| ::1 | IPv6 loopback | No for consumers in other namespaces |
| 10.20.4.15 | Listen on a specific IPv4 address if that address exists | Yes, if consumers have a route to it |

Wildcard lets the server accept connections on interfaces the process is permitted to use. It does not represent a routable destination address. When registering a service, advertise an actual hostname/IP or a stable DNS/service name.

### 1.2. Binding to loopback can block external connections to a container

If an application runs in a container and binds:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

only processes in the exact same network namespace can reach that loopback. Another container or the host typically cannot connect via the container's address because the server is not listening on the container's network interface.

For web applications in containers, a common configuration is binding the wildcard inside the container:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

This only opens a listener inside the container's network namespace. Firewalls, port publishing, Kubernetes Services, NetworkPolicies, and security groups still govern who can connect from outside.

## 2. What is an advertised address?

The advertised address is the information an application publishes so consumers know how to call the instance. In discovery architectures, the registry can store hostname/IP, port, scheme, metadata, and instance status.

Example instance registration:

~~~text
serviceId: catalog-service
host: catalog-7f8a
port: 8080
status: UP
~~~

Consumers retrieve a ServiceInstance from the discovery client and send requests to the returned address. If host/port are unreachable from the consumer, discovery may still return structurally valid data while requests fail at the network layer.

A good advertised address must satisfy:
- Consumers can resolve the hostname if DNS is used.
- Consumers have a route to the IP if a numeric address is used.
- The published port is a port consumers can actually connect to.
- Firewalls, NetworkPolicies, and security groups allow the connection flow.
- Scheme, TLS, and context path match the service's protocol.
- The address is not loopback or wildcard unless a deliberately designed proxy/gateway sits in front.

### 2.1. Application name is not a network address

spring.application.name defines the application's logical name across many integrations, such as the service name used in discovery or the application name requested by Config Client.

~~~yaml
spring:
  application:
    name: catalog-service
~~~

The value catalog-service does not automatically reveal an IP or port. The instance's address is determined by server config, discovery client, DNS, or deployment infrastructure.

Distinction:

| Property/concept | Example | Role |
| --- | --- | --- |
| Application name | catalog-service | Logical name of the application |
| Bind address | 0.0.0.0 | Interface/address the server listens on |
| Server port | 8080 | Internal port of the listener |
| Advertised hostname | catalog-7f8a | Name consumers use to access the instance |
| Advertised IP | 10.20.4.15 | Published numeric address |
| Published/Service port | 18080 or 80 | Port mapped or exposed via infrastructure |

## 3. Why do bind address and advertised address often differ?

A server may bind wildcard to accept connections on every interface while advertising only the single interface dedicated to the application network.

For example, a machine has:
- eth0: 10.20.4.15 for the application network.
- tun0: 10.99.0.5 for admin VPN.
- docker0: 172.17.0.1 for Docker bridge.

The server can bind 0.0.0.0:8080, while the registry should advertise 10.20.4.15:8080 if consumers sit on the application network. Advertising 127.0.0.1, 0.0.0.0, or 172.17.0.1 can prevent consumers from connecting.

Diagram:

~~~mermaid
flowchart TD
    APP["Spring Boot process"]
    BIND["Bind: 0.0.0.0:8080"]
    ETH["eth0: 10.20.4.15"]
    VPN["tun0: 10.99.0.5"]
    DOCKER["docker0: 172.17.0.1"]
    REG["Registry: 10.20.4.15:8080"]
    CLIENT["Consumer in application network"]

    APP --> BIND
    BIND --> ETH
    BIND --> VPN
    BIND --> DOCKER
    ETH --> REG
    REG --> CLIENT
~~~

The diagram illustrates the principle. The server can listen on multiple interfaces, yet the application/registry must pick an endpoint reachable by the target consumer group.

## 4. Spring Boot configuration for bind address

Spring Boot uses server.address and server.port to configure the address and port of the embedded web server. Example:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

If server.address is omitted, the embedded server usually binds to a wildcard address per server/OS defaults. Check startup logs and actual sockets instead of guessing from YAML files.

In environments requiring interface restrictions, you can bind a specific address:

~~~yaml
server:
  address: 10.20.4.15
  port: 8080
~~~

This works when the address is stable and already assigned to the network namespace. Inside containers, IPs are typically assigned dynamically; hardcoding a Pod IP or container IP in server.address easily breaks when containers are recreated.

### 4.1. Bind wildcard in containers, enforce access control in infrastructure

A common configuration:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Then restrict access using:
- Docker networks and port publishing.
- Kubernetes Services and NetworkPolicies.
- Firewalls/security groups.
- Ingress or API gateways.
- Application-level authentication and authorization.

Binding wildcard does not mean exposing ports to the public Internet. It only enables the listener on interfaces inside the process's namespace; external reachability still depends on network configuration.

## 5. Spring Cloud InetUtils and host info

Spring Cloud Commons provides InetUtils to resolve host info from network interfaces. Some integrations can use the hostname/IP discovered by InetUtils as default instance info.

Common properties:

| Property | Effect |
| --- | --- |
| spring.cloud.inetutils.ignored-interfaces | Ignore interfaces whose names match regex |
| spring.cloud.inetutils.preferred-networks | Prioritize IP addresses matching regex |
| spring.cloud.inetutils.use-only-site-local-interfaces | Restrict selection per Java's site-local classification |
| spring.cloud.inetutils.default-ip-address | Fallback IP value when no suitable address is found |
| spring.cloud.inetutils.default-hostname | Fallback hostname |

Example ignoring Docker bridge and prioritizing the application network range:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - docker0
        - veth.*
      preferred-networks:
        - '^10\.20\..*'
~~~

Values in preferred-networks are regexes, not CIDR notation. Inspect the actual interface names and IPs seen by the JVM in the real runtime environment.

### 5.1. InetUtils does not configure server binding

This is a critical boundary:

- server.address controls the embedded server's listener address.
- spring.cloud.inetutils.* controls how Spring Cloud discovers host info.
- Discovery clients can have their own properties to override the registered hostname/IP.
- OS routing tables and policy routing determine outbound paths.

Setting preferred-networks does not automatically change server.address. Ignoring docker0 in InetUtils also does not remove that interface from the OS or alter routing tables.

### 5.2. Discovered host info is not necessarily the final endpoint in the registry

A discovery client can receive default host info and then apply its own configuration. Therefore, when debugging, compare:
1. Interfaces and IPs provided by the OS.
2. Host info discovered by InetUtils.
3. Values used by the discovery client after applying overrides.
4. Actual instance record sent to the registry.
5. Endpoint received by consumers from DiscoveryClient.

Never conclude the registry holds the right address solely from InetUtils logs.

## 6. Advertised address in Eureka

With the Eureka client, common properties controlling instance hostname/IP include:
- eureka.instance.hostname
- eureka.instance.ip-address
- eureka.instance.prefer-ip-address

Example advertising a hostname:

~~~yaml
eureka:
  instance:
    hostname: catalog-service
    prefer-ip-address: false
~~~

The hostname catalog-service must be resolvable by consumers that need to call the instance. In Docker Compose, that may be the service name on the same Docker network. In Kubernetes, that may be Service DNS if registering a stable endpoint rather than individual Pods.

Example advertising an explicit IP:

~~~yaml
eureka:
  instance:
    prefer-ip-address: true
    ip-address: 10.20.4.15
~~~

The address 10.20.4.15 must be provisioned by the deployment environment and reachable from consumers. Never use 0.0.0.0, loopback, or the IP of a bridge that exists only on the host.

When configuring explicitly, verify the final values in Eureka InstanceInfo and the ServiceInstance objects received by consumers. Defaults can vary by Spring Cloud Netflix/Eureka version and application configuration.

### 6.1. Advertised port

Even with the right host address, the wrong port still breaks discovery. For instance, the server listens on port 8080 inside a container while Docker publishes 18080:8080 on the host. Consumers on the same Docker network usually call the container service on port 8080; clients outside the Docker network may need host port 18080 or a load balancer/gateway.

A registry storing only one host/port does not automatically understand every network zone. If consumers exist both inside and outside the container network, pick a shared routable endpoint or design gateways/DNS/registries per zone.

Never assume a discovery client automatically infers Docker's published port. Port mapping is configured at the Docker daemon level; the application inside the container normally knows only the internal port its server listens on.

## 7. Running on a Docker bridge network

A Docker bridge creates a separate network namespace for each container. Applications inside the container typically see an eth0 interface with the Docker network's internal IP. The host and other containers can reach this IP depending on topology and firewalls.

Compose example:

~~~yaml
services:
  catalog-service:
    image: example/catalog-service:1.0
    environment:
      SERVER_PORT: "8080"
    ports:
      - "18080:8080"
    networks:
      - app-net

  order-service:
    image: example/order-service:1.0
    networks:
      - app-net

networks:
  app-net:
    driver: bridge
~~~

In this setup:
- Catalog server binds port 8080 inside the container.
- Docker publishes host port 18080 to container port 8080.
- order-service on the same network can call http://catalog-service:8080 via Compose's DNS/service name.
- Clients from the host can call http://localhost:18080.
- Clients from a network external to the host need a reachable host/LB address and the corresponding published port.

If Eureka runs on the same Docker network and consumers are also on that network, you can advertise hostname catalog-service with internal port 8080. If consumers are outside the Docker network, that hostname may not resolve; a reachable external endpoint and corresponding port are needed.

### 7.1. Do not advertise out-of-scope host addresses

Common mistakes:
- Advertising 127.0.0.1: other consumers will call their own loopback.
- Advertising 0.0.0.0: this is a wildcard bind, not a destination address.
- Advertising 172.17.0.1: the host's bridge address, not necessarily the service container's IP.
- Advertising container IP to consumers outside the bridge: no route may exist.
- Advertising host port 18080 to consumers on the same bridge: consumers may need container port 8080.

Choose the endpoint based on where consumers sit, not based on the first address visible inside the container.

### 7.2. Docker host network

When using host networking on Linux, the container shares the host's network namespace. The server can bind directly to host addresses/ports; bridge-style port publishing no longer has the same meaning as in bridge network configs.

This mode alters isolation and can cause port conflicts between processes. Host networking behavior on Docker Desktop also depends on version/platform. Never use host networking merely to dodge choosing an advertised address; first clarify connectivity requirements and security boundaries.

## 8. Running in Kubernetes

In Kubernetes, a Pod has its own network namespace and typically receives a Pod IP. The application inside the container should listen on an interface able to receive traffic from the Pod network, usually:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

A Kubernetes Service provides a stable address and DNS name for a selected group of Pods. Example:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-service
spec:
  selector:
    app: catalog-service
  ports:
    - name: http
      port: 80
      targetPort: 8080
  type: ClusterIP
~~~

In-cluster consumers call Service DNS:

~~~text
http://catalog-service.default.svc.cluster.local:80
~~~

Within the same namespace, the short name catalog-service usually works. The Service forwards to eligible Pod endpoints; consumers do not need to know specific Pod IPs.

### 8.1. Pod IP and Service DNS are two different choices

| Address | Characteristics | Use case |
| --- | --- | --- |
| Pod IP | Tied to one Pod, can change when the Pod is recreated | Per-instance discovery inside the cluster if consumers can route to it |
| ClusterIP | Stable address of a Kubernetes Service | Calling a group of Pods through the service abstraction |
| Service DNS | Stable name resolving to a Service | Standard calling pattern between workloads in a cluster |
| Node IP | Address of the node running the Pod | Not a default endpoint for internal services |
| Ingress/LoadBalancer address | Endpoint exposed to clients outside the cluster | External network access per ingress/LB architecture |

When using Kubernetes Service discovery, registering individual Pods in Eureka is usually unnecessary for internal service-to-service calls; Service DNS and the cluster dataplane already provide discovery/load balancing. If an application still uses Eureka, explicitly decide whether the registry represents individual Pod instances or the stable Service-level endpoint.

### 8.2. Eureka in Kubernetes

If Eureka registers each Pod, Pod IP and container port can work when all consumers are inside the cluster and can route to the Pod network. However, Pod IPs change when Pods are replaced, so clients must refresh the registry and handle instance lifecycles properly.

If publishing ClusterIP/Service DNS for every replica in Eureka, all records may point to the same Service instead of individual instances. That can defeat client-side load balancing or per-instance health tracking. Choose one consistent model:
- Kubernetes Service DNS for service-level discovery.
- Pod IP for in-cluster instance-level discovery.
- Ingress/LoadBalancer/gateway for external consumers.

Never register a Node IP or host IP merely because it is stable if ports/routes to the Pod are not mapped accordingly.

### 8.3. Readiness and registered endpoints

A Pod may have bound its port yet not be ready to handle requests. Kubernetes readiness probes decide whether a Pod is added to EndpointSlice/Service endpoints. If using Eureka alongside it, discovery registration/health must be synchronized with application state.

Binding successfully proves only that the socket is open; it does not prove dependencies are ready, the registry is updated, or requests can complete.

## 9. When a reverse proxy, ingress, or load balancer is present

An application can bind internally to 0.0.0.0:8080 while clients access it through:
- Nginx/Envoy reverse proxy.
- Kubernetes Ingress.
- Cloud Load Balancer.
- API Gateway.
- Service mesh sidecar.

In this case, the public/consumer-facing address may be the proxy/LB's hostname and port, not the Pod's or container's IP.

Determine whether discovery represents:
- Each backend instance.
- One stable service endpoint.
- One shared gateway.
- One internal endpoint used only inside the cluster.

Do not advertise the proxy address to an instance-level registry if clients need direct per-instance connections. Conversely, do not advertise Pod IPs to external clients if only the gateway is reachable.

### 9.1. Host header and forwarded headers do not replace the advertised address

A reverse proxy can pass Host, X-Forwarded-Host, X-Forwarded-Proto, or the standard Forwarded header so the application knows the request's external URL. These headers help the application build proper redirects or links, yet they do not automatically change the address registered by a discovery client.

If a service needs to publish an external endpoint, configure discovery/metadata or the gateway explicitly. Never assume server.forward-headers-strategy will automatically change the Eureka hostname/IP.

## 10. Multiple network zones and multiple consumer types

A service may be called from:
- Containers on the same Docker network.
- Pods inside the same Kubernetes cluster.
- Workloads in another VPC.
- On-premises systems over VPN.
- Internet clients through a gateway.

A single address is not always reachable from every zone. For instance, a Pod IP may work inside the cluster yet lack a route from on-premises. A host port may work from a LAN yet be unreachable from the Pod network.

In multi-zone architectures, consider:
- DNS names with appropriate views/zones.
- Internal/external load balancers.
- Gateways or ingress.
- Registries separated by network zone.
- Centrally managed service mesh or network routing.
- Separate endpoint/port metadata per consumer group if the discovery architecture supports it.

Do not advertise multiple addresses in a single record if clients do not know how to pick the right endpoint. Address selection policy must live in well-designed DNS, gateways, registries, or client routing.

## 11. Inspecting socket bindings and advertised endpoints

When diagnosing, inspect both sides separately.

### 11.1. Inspecting where the server is listening

On Linux/containers:

~~~bash
ss -lntp
ip -br address
~~~

On Windows:

~~~powershell
Get-NetTCPConnection -State Listen
Get-NetIPAddress
~~~

Check:
- Is the process listening on the expected port?
- Is the listener bound to 0.0.0.0, ::, loopback, or a specific IP?
- Does the bind address exist inside the namespace?
- Does the container port match targetPort or Docker mapping?

Commands run on the host do not necessarily reveal listeners inside a container. Inspect from the exact container/Pod or use appropriate debugging tools.

### 11.2. Inspecting the advertised address

Check the discovery registry or DiscoveryClient to see what host/port consumers actually receive. Example reading instances:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class CatalogDiscoveryDiagnostics {

    private final DiscoveryClient discoveryClient;

    public CatalogDiscoveryDiagnostics(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> instances() {
        return discoveryClient.getInstances("catalog-service")
                .stream()
                .map(instance -> instance.getHost() + ":" + instance.getPort())
                .collect(Collectors.toList());
    }
}
~~~

This is an internal diagnostic example; never expose internal address lists via public endpoints. Cross-check host/port values here against the registry server and discovery client configuration.

### 11.3. Inspecting from the consumer

The most important test is from the consumer's exact network namespace:

~~~bash
getent hosts catalog-service
nc -vz catalog-service 8080
curl -v http://catalog-service:8080/actuator/health
~~~

In Kubernetes, you can use kubectl exec into a consumer Pod or a debug Pod sharing the namespace/network policies. In Docker, use docker exec or a container on the same network.

Running curl localhost inside the provider container only proves the listener works over that container's own loopback. It does not prove other consumers can connect.

## 12. Testing by environment

| Test | Environment | What to verify |
| --- | --- | --- |
| Bind test | Local JVM/process | Listener opens on the expected address and port |
| Host-info test | OS/VM/container | InetUtils resolves host info per policy |
| Registry test | Discovery server/client | Instance record holds expected hostname/IP/port |
| Docker network test | Two containers on same network | Consumer resolves service name and connects to container port |
| Host-to-container test | Docker host | Published port forwards to the right container port |
| Kubernetes Service test | Consumer Pod | Service DNS and port route to Pod endpoints |
| External ingress test | Client outside cluster | Hostname, TLS, ingress/LB, and backend route work |
| Multi-zone test | Different networks | All target consumers have reachability as designed |

### 12.1. Do not hardcode dynamic IPs in tests

Container IPs and Pod IPs can change across runs. General tests should verify:
- Hostname/port belong to the expected endpoint.
- DNS resolves inside the test network.
- Consumers connect successfully.
- Registry contains no loopback/wildcard or out-of-scope endpoints.

Assert a specific IP only when the test environment is intentionally fixed. In CI using ephemeral Docker or Kubernetes, prefer service names/DNS or endpoints supplied by the test harness.

### 12.2. Test bind configuration separately from advertised address

A configuration test can verify that server.address and discovery overrides bind to the expected properties. However, binding tests do not prove sockets are open or addresses are reachable. Integration tests that start the server and call from a consumer are required.

Never use a YAML-reading unit test as a substitute for verifying the network path.

## 13. Common errors

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Server starts yet other containers cannot call it | Bound to loopback | Check server.address and socket listener |
| Registry advertises 0.0.0.0 | Confused wildcard bind with destination | Configure explicit advertised hostname/IP |
| Registry advertises 127.0.0.1 | InetUtils fallback or wrong discovery override | Check host info and eureka.instance.* |
| Docker consumer calls host port and fails | Consumer on same bridge needs container port | Use service DNS and internal port |
| Client outside Docker cannot reach container IP | No route to bridge IP | Use host/LB address and published port |
| Kubernetes Pod registers Node IP | Selected wrong address layer | Use Pod IP for instance discovery or Service DNS for service discovery |
| Pod binds properly yet Service is unreachable | Wrong selector/targetPort/EndpointSlice/NetworkPolicy | Inspect Service and endpoints |
| Registry returns right address yet TCP times out | Blocked by route/firewall/security group | Test from consumer network namespace |
| Registered hostname is right yet DNS fails to resolve | Different DNS scope/search domain | Check resolver from consumer |
| Port right inside container yet wrong outside | Confused container port with published/Service port | Compare port mapping or Service port/targetPort |
| External URL has wrong scheme/host | Reverse proxy forwarded headers misconfigured | Check proxy and forwarded headers config |
| Some replicas reachable, others not | Different interfaces/IPs or rollout state | Inspect registry record per instance |

## 14. Workflow for choosing bind and advertised addresses

When deploying a Spring Cloud service, follow this sequence:

1. Determine whether the process runs on a host, Docker bridge, host network, or Kubernetes Pod.
2. Determine the port the application listens on inside its namespace.
3. Choose an appropriate bind address; in containers, usually use wildcard and restrict access in infrastructure.
4. Identify which network zones consumers reside in.
5. Choose a hostname/IP consumers can resolve and route to.
6. Determine the port consumers must call: container port, Kubernetes Service port, or host/LB port.
7. Configure the discovery client to advertise the exact endpoint.
8. Use InetUtils filters if automatic host info selection is needed.
9. Verify the registered record and the values returned by DiscoveryClient.
10. Test DNS/TCP/HTTP from a real consumer.
11. Verify readiness, firewalls, TLS, gateways, and NetworkPolicies.
12. Re-verify whenever changing container runtimes, CNI, network interfaces, or release trains.

If a service has both internal and external consumers, design endpoints/gateways/DNS per zone instead of trying to force a single container IP to serve every network.

## 15. Operational and security principles

- Never advertise 0.0.0.0, ::, 127.0.0.1, or ::1 to remote consumers.
- Never hardcode container/Pod IPs if addresses can change upon rescheduling.
- Never confuse bind address with advertised address or outbound source address.
- Wildcard binding in containers must be paired with proper firewalls, network policies, and authentication.
- Expose only necessary ports; never publish management ports externally unless required.
- Never register bridge/VPN/virtual interface addresses if consumers have no route to them.
- Use stable DNS/service names when provided by infrastructure.
- Verify registry records from the consumer side, not only from the provider.
- Manage server.port, Docker published port, and Kubernetes port/targetPort as distinct concepts.
- Re-verify advertised addresses after every topology or deployment platform change.
- Never expose internal interface/IP lists through unprotected diagnostic endpoints.

## Key takeaway

server.address controls where the web server listens; advertised address controls the host/port discovery or consumers receive; actual reachability depends on DNS, routes, NAT, firewalls, and the client's network namespace. In Docker, distinguish container ports from host published ports and use service DNS for containers on the same network. In Kubernetes, distinguish Pod IPs from Service DNS/ClusterIP and ingress endpoints. Verify the listener, the registry record, and connectivity from the consumer before concluding a service's addressing is configured properly.
