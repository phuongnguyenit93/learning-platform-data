# Localhost on the Host, in Containers, and in Private Networks

A common mistake when deploying microservices is configuring a provider with localhost and expecting a process on another machine or container to reach it. The reason is that localhost always points to **the caller's own network namespace**. The host, each container, and each machine on a private network has its own loopback; they do not share a single localhost address.

In Spring Cloud Service Discovery, this matters greatly. A provider can register successfully with Eureka or Consul, and a consumer can find the serviceId, yet requests still fail if the registry advertises an address reachable only from another network. To route properly, you must distinguish the application's bind address, the address advertised by the registry, and the address the consumer can actually call.

## 1. What Does Localhost Actually Mean?

Localhost typically resolves to the loopback interface of the current machine or network namespace. IPv4 usually uses 127.0.0.1; IPv6 uses ::1. Packets sent to loopback are processed immediately inside that namespace without traversing a physical network or Docker bridge.

Therefore:

- When running an application directly on the host, localhost is the host.
- When running an application in container A, localhost is container A.
- When running a consumer in container B, localhost is container B.
- When running an application on machine 10.10.0.20, localhost is machine 10.10.0.20; machine 10.10.0.21 has its own localhost.

For example, inventory-service runs in a container on port 8080. A request from that same container to http://localhost:8080 can succeed. However, order-service in another container calling http://localhost:8080 will connect to port 8080 of order-service itself, not inventory-service.

~~~mermaid
flowchart TB
    subgraph Host["Docker Host"]
        HostLoop["Host loopback<br/>127.0.0.1"]
        subgraph A["Container A: inventory"]
            ALoop["Loopback A<br/>127.0.0.1"]
            AApp["Inventory API :8080"]
            ALoop --> AApp
        end
        subgraph B["Container B: order"]
            BLoop["Loopback B<br/>127.0.0.1"]
            BApp["Order API :8080"]
            BLoop --> BApp
        end
    end
    HostLoop -. "Not the same loopback" .-> ALoop
    ALoop -. "Not the same loopback" .-> BLoop
~~~

The three 127.0.0.1 addresses in the diagram have the same numeric value but reside in three different network namespaces. They do not point to the same logical machine.

## 2. Distinguishing Bind Address and Destination Address

A server application needs to listen on an interface. The bind address determines which interface accepts connections; the destination address is the address the client uses to open a connection.

| Address | Meaning | Should it be used as the destination address for consumers? |
|---|---|---|
| 127.0.0.1 or ::1 | Accepts connections only from the current loopback namespace | Only when the consumer is in the same namespace |
| 0.0.0.0 | Binds on all IPv4 interfaces of the namespace | No; this is a bind address, not a destination address |
| Private IP, e.g., 10.10.0.20 | Interface in an internal network | Yes, if the consumer has a route and firewall allows it |
| Container IP, e.g., 172.20.0.5 | Container interface on a Docker network | Yes, if the consumer is on the same network or has a route to that subnet |
| Service DNS name, e.g., inventory-api | Name resolved by the network's DNS | Yes, if the consumer uses that DNS and the name points to the appropriate endpoint |
| Host IP and published port | Host address after Docker publishes the port | Yes, if the consumer can reach the host and port |

In Spring Boot, the server.address property controls the web server's bind address. If a container needs to accept requests from other containers on the same network, the application usually must bind on the container interface:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

If bound only to 127.0.0.1 inside the container, Docker can publish the port to the host, yet forwarded connections still cannot reach a socket listening only on loopback. Check the bind address when port mapping looks right but connections are still refused.

Do not register 0.0.0.0 as a service address. This address means "all interfaces" when binding; it does not specify a destination that consumers can route to.

On a physical host, it is not necessary to bind all interfaces. You can bind to a specific private IP if you only want to receive traffic from one network. When binding 0.0.0.0, restrict the port using a firewall or security group.

## 3. Choosing an Address Based on the Caller's Location

| Caller | Provider | Commonly used address |
|---|---|---|
| Process on the same host | Process on the host | localhost and application port |
| Host | Container with published port | localhost or host IP with published port |
| Container A | Container B on the same Docker network | Compose service name and container port |
| Container | Application on the host | host.docker.internal and host port, if supported by the environment |
| Another machine in private network | Host or VM | Private DNS/IP and open port |
| Machine over VPN | Service in private network | Private DNS/IP routed over VPN |
| External consumer | Internal service | Public endpoint, ingress, or controlled reverse proxy |

Do not choose an address just because it works from the current terminal. Choose based on the actual location of the consumer. A curl command run on the host does not prove another container can reach it; curl run inside a container does not prove a laptop or a machine over VPN has a route to the same address.

## 4. Container Calling Container via Docker Compose Network

Docker Compose creates internal DNS for services on the same network. Containers can use the service name as a hostname instead of depending on a container IP that changes across recreations.

For example:

~~~yaml
services:
  inventory-api:
    image: inventory-service:1.0
    networks:
      - backend
    expose:
      - "8080"

  order-api:
    image: order-service:1.0
    environment:
      INVENTORY_BASE_URL: http://inventory-api:8080
    networks:
      - backend

networks:
  backend:
    driver: bridge
~~~

Order service calls inventory using hostname inventory-api and internal port 8080. Do not use localhost:8080 because localhost in this case is the order-api container.

The expose property only documents the internal port for config readers and tools; it does not publish the port to the host. Containers on the same network can connect to the port the application is listening on even if expose is not declared.

If two services are not on the same network, the service DNS name may not resolve and traffic may have no route. Attach them to a shared network or configure an appropriate gateway. Avoid placing all containers onto one broad network unnecessarily.

A container's IP can change when the container is recreated. Use Docker's service DNS for direct communication on the same network. When using service discovery, the registry must return an instance address that consumers can actually reach; the registered DNS name or IP must match that architecture.

## 5. Host Accessing a Container via Port Mapping

Port mapping forwards a port on the host to a port inside the container:

~~~yaml
services:
  inventory-api:
    image: inventory-service:1.0
    ports:
      - "18080:8080"
~~~

The pair follows host-port:container-port order. In the example, the host accepts connections on port 18080 and Docker forwards them to port 8080 inside the container.

From the host, call:

~~~bash
curl http://localhost:18080/actuator/health
~~~

From another container on the same network, call:

~~~bash
curl http://inventory-api:8080/actuator/health
~~~

Both requests go to the same application but use two different addresses. Consumers inside containers should not loop through the host published port when they can use the internal network; the internal path usually has fewer hops and does not require exposing ports to the host.

You can restrict publishing to host loopback if only applications on the host need access:

~~~yaml
ports:
  - "127.0.0.1:18080:8080"
~~~

When binding a published port to 127.0.0.1, other machines on the LAN cannot access it via the host's LAN IP. If callers on another network need access, publish on the appropriate interface and configure firewall rules matching the access scope.

## 6. Container Calling an Application Running on the Host

A container may need to call a database, mock server, or development tool running directly on the host. In Docker Desktop, the name host.docker.internal is commonly provided for containers to reach the host.

For example:

~~~yaml
services:
  integration-test:
    image: test-runner:1.0
    extra_hosts:
      - "host.docker.internal:host-gateway"
~~~

On Docker Engine on Linux, host.docker.internal may require declaring host-gateway as shown above depending on the version and configuration. Docker Desktop usually provides this name out of the box.

From the container:

~~~bash
curl http://host.docker.internal:9090/health
~~~

The application on the host must listen on an interface reachable through that gateway. If the application binds only to 127.0.0.1 on the host, some bridge setups will not be able to reach it via the gateway address. You can bind to the appropriate host/gateway IP and restrict the firewall so you do not unintentionally broaden access.

Do not replace host.docker.internal with a hardcoded gateway IP without a clear operational reason. The gateway can differ across Docker Desktop, Linux bridge, WSL, and CI environments.

## 7. Communication in Private Networks, LANs, and VPNs

Private networks typically use RFC 1918 address ranges such as:

- 10.0.0.0/8
- 172.16.0.0/12
- 192.168.0.0/16

For example, a provider runs on machine 10.20.1.15, port 8080. A consumer on machine 10.20.1.30 can call this address if:

1. The two machines have routes to each other.
2. The application binds on the appropriate private interface.
3. The firewall/security group allows TCP 8080 from the consumer subnet.
4. No NAT or policy routing diverts traffic to another destination.
5. Internal DNS, if used, resolves to the right address from the consumer network.

A hostname like inventory.internal may resolve to 10.20.1.15. If the environment has split-horizon DNS, the same hostname can return different IPs depending on the caller's network. That can be useful, but you must verify that every consumer receives the appropriate address.

When consumers connect over a VPN, check subnet routes, DNS pushed via VPN, and firewall policies. The VPN showing a connected status does not guarantee that routes to all private subnets are installed.

Do not advertise private IPs to Internet consumers if there is no VPN or private link. External consumers need an intentionally exposed endpoint such as an API gateway, ingress, reverse proxy, or public load balancer.

## 8. Why Does Service Discovery Find the Service Yet Calls Still Fail?

Service discovery solves finding instances by logical name. The registry stores or returns the host/port address of each instance. Spring Cloud LoadBalancer picks an instance and the HTTP client connects to that address.

The registry does not automatically create network routes. If the provider registers localhost, a container IP that exists only inside a private bridge, a hostname that resolves only in one network, or an internal port not open to the consumer, requests will fail even though lookup succeeds.

~~~mermaid
sequenceDiagram
    participant P as Provider
    participant R as Service Registry
    participant C as Consumer
    P->>R: Register serviceId and instance address
    C->>R: Look up serviceId
    R-->>C: Return registered host and port
    C->>C: LoadBalancer selects instance
    C->>P: HTTP request to actual address
    Note over C,P: If address has no route or wrong port, request fails
~~~

Wrong example: a provider inside a container registers 127.0.0.1:8080. The consumer receives that exact address but calls the consumer's own localhost.

Another example: a provider registers 172.20.0.5:8080, an address that only exists in Docker network A. A consumer in private network B has no route to subnet 172.20.0.0/16. The registry still returns a valid result according to stored data, but the address is unusable from the consumer.

Therefore, before concluding that discovery is broken, check the instance address returned by the registry and test connectivity from the consumer's own environment.

## 9. Configuring the Instance Address in Eureka

The Eureka Client registers the application name, instance ID, hostname/IP, and port. Consumers use the serviceId to fetch the instance list; Spring Cloud LoadBalancer selects an instance and sends requests to its URI.

An illustrative provider configuration when provider and consumer are on the same Docker network:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  address: 0.0.0.0
  port: 8080

eureka:
  client:
    service-url:
      defaultZone: http://eureka-server:8761/eureka/
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${HOSTNAME:local}:${server.port}
~~~

In the example, Eureka Server is called via service name eureka-server on the Docker network. The provider listens on all container interfaces. prefer-ip-address instructs the client to advertise the IP instead of the hostname; this is only suitable if that IP is reachable from consumers.

If consumers are outside the Docker network, the container address Eureka advertises may not be usable. In that case, choose an appropriate addressing architecture: place consumers on the same private network, advertise a hostname routable from consumers, or use a gateway/proxy reachable from both sides. Do not just enable prefer-ip-address and assume every client can reach it.

You can configure a specific hostname if internal DNS has a unique name for each instance and consumers can resolve that name. With multiple replicas, avoid having every instance advertise the same single hostname unless that hostname maps properly to each instance; if a single shared address is needed, use a properly designed load balancer or gateway endpoint.

If multiple consumers reside on networks without a shared route, a single service registration may not be enough. You can create separate registrations/endpoints per network or have consumers go through a gateway. Ensure serviceId, metadata, and instance selection policies remain consistent; metadata is only useful when the consumer or LoadBalancer actually filters by it.

## 10. Configuring Consul and Health Checks

Consul service registration also has its own service address. The agent can check the application using an internal URL, while consumers use a service address reachable from their network.

Example registration:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-node-a",
    "address": "10.20.1.15",
    "port": 8080,
    "checks": [
      {
        "http": "http://127.0.0.1:8080/actuator/health",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

This example is only suitable when the Consul agent runs in the same network namespace as the application or 127.0.0.1 loopback from the agent actually points to the application. If the agent runs in another container, localhost in the check URL is the agent container itself. In that case, use a DNS/IP reachable by the agent, such as inventory-api:8080 on the same Docker network.

Address and Port in the registration are the data consumers receive. The HTTP check URL is the address the agent calls to check health. These two addresses can differ, but both must lead to the right service and be reachable from their respective networks.

When a service is shared by consumers across multiple networks, choose the advertised address according to the consumer group. A passing agent check does not prove every consumer can reach the service address.

## 11. Configurations That Commonly Cause Errors

| Configuration | Why it fails | Fix |
|---|---|---|
| Consumer container calls localhost:8080 to reach provider container | localhost is the consumer's loopback | Use service DNS and container port |
| Provider binds 127.0.0.1 inside container | Accepts connections only inside that container | Bind the container interface, usually 0.0.0.0 |
| Eureka registers 127.0.0.1 | Consumer receives its own loopback | Advertise an IP/DNS reachable from consumers |
| Registry returns bridge IP while consumer is on another network | Consumer has no route to container subnet | Use a shared network, private route, or gateway |
| Consumer uses container port from the host | Container port is not necessarily published | Use the host published port |
| Consumer uses host published port from a container on the same network | Loops through host NAT and may hit hairpin/NAT policies | Use service DNS and container port |
| Container calls host's localhost | Loopback points to the container | Use host.docker.internal or an appropriate host gateway |
| Using 0.0.0.0 as destination | This is a wildcard bind address | Use a specific IP or hostname |
| Health check passes but consumers time out | Agent and consumer have different network views | Test the address from each party's exact namespace |

## 12. Diagnostic Workflow from the Exact Call Site

When requests fail, inspect in order:

1. Identify where the caller runs: host, container, VM, Kubernetes pod, or machine over VPN.
2. Record the exact destination address: hostname/IP, port, and scheme.
3. Identify the provider's bind address and the interface the application is listening on.
4. If using a registry, read the instance address that the consumer actually receives.
5. Check DNS from the caller itself, not just from the operator host.
6. Check routes and firewalls from caller to destination.
7. Check port mapping if the destination goes through a Docker host.
8. Use curl or a TCP tool from the exact caller environment.
9. Cross-check server logs to determine whether requests reach the application.
10. After changing the registration address, wait for the discovery cache to refresh and re-test from the consumer.

Example checking DNS and HTTP from a container:

~~~bash
getent hosts inventory-api
curl -v --connect-timeout 3 http://inventory-api:8080/actuator/health
~~~

Minimal images may not have getent or curl installed. You can use equivalent tools available in the image, or run a temporary debug container on the same network. Results must be captured from the network namespace corresponding to the caller.

On the host, check the published port:

~~~bash
curl -v --connect-timeout 3 http://127.0.0.1:18080/actuator/health
~~~

From another machine on the private network, use the IP or DNS that machine resolves:

~~~bash
curl -v --connect-timeout 3 http://10.20.1.15:8080/actuator/health
~~~

If the host command succeeds while the container command fails, the issue may lie in DNS, network attachment, or container routing. If the container command succeeds while VPN fails, check VPN routes, DNS, and private network firewalls.

## 13. Notes When Running on Kubernetes

Kubernetes also uses a separate network namespace per Pod. localhost in a container points to the Pod network namespace; containers in the same Pod share the network namespace so they can call each other via localhost if using different ports.

Different Pods should communicate via Service DNS, such as inventory-service.default.svc.cluster.local, and the Kubernetes Service port. Do not register localhost as the instance address for consumers in other Pods.

A Kubernetes Service can provide a stable virtual IP and distribute traffic to Pods eligible according to readiness. If combining Spring Cloud Discovery with Kubernetes, clearly decide which layer handles discovery/load balancing to avoid two unintentionally overlapping routing layers.

Pod IPs are usually meaningful only inside the cluster network. Consumers outside the cluster require configured ingress, gateway, load balancer, or VPN routes. Do not advertise Pod IPs to Internet clients.

## 14. Security When Opening Ports and Advertising Addresses

Making an address reachable does not mean opening it to every network. When binding to 0.0.0.0 or publishing a port, restrict source access with firewalls, security groups, or network policies.

Some principles:

- Publish only necessary ports to the host.
- Restrict published ports to loopback if only the host needs access.
- Do not expose registry dashboards/APIs directly to the Internet.
- Use private DNS and private networks for internal communication when appropriate.
- Use TLS for connections across untrusted networks and verify certificates.
- Do not advertise management addresses or debug ports in service registrations used by consumers.
- Check ACLs and service registration permissions to prevent workloads from spoofing instance addresses.
- After changing IPs, port mappings, or gateways, update registrations and clean up old records.

The address advertised in the registry is part of the routing configuration. Treat it as sensitive, controlled, and auditable data.

## 15. Checklist Before Registering a Service

Before enabling auto-registration for a provider, confirm:

1. The provider binds on an interface suitable for the consumer's network.
2. Consumers do not use localhost to call a host/container in a different namespace.
3. The port in the registry is a port consumers can actually connect to.
4. The advertised hostname/IP resolves and is routable from consumers.
5. If using Docker, provider and consumer share a network or have valid gateway/port mappings.
6. If using host.docker.internal, the Docker environment supports that name and the host service listens on the appropriate interface.
7. If using a private network/VPN, routes, DNS, and firewalls allow the required bidirectional connectivity.
8. Health checks are tested from the network namespace of the agent performing the check.
9. HTTP requests are tested from the network namespace of the consumer making the request.
10. After container restarts or IP changes, the registry updates the address and consumers evict stale data.

The key takeaway is: **localhost always belongs to the caller's network namespace; the bind address determines where the server listens; the service address in the registry must be a destination the consumer can reach.** Once you accurately identify the positions of caller and provider, choosing between localhost, service DNS, host gateway, or private IP becomes clear.
