# Container Ports, Published Ports, and NAT Mapping

When deploying microservices with Docker or Kubernetes, an application may listen on one port inside a container or Pod, while external clients access it through another port. Network infrastructure maps between those two ports via port publishing, Services, load balancers, or NAT.

With Spring Cloud Service Discovery, it is critical that the registry advertises the right address and port that consumers can reach. An instance might run on port 8081 inside a container yet be published as port 18081 on the host. Consumers on the same Docker network typically call port 8081; consumers traversing host NAT may need to call port 18081. If the provider registers the wrong host/port pair, the service can still appear in Eureka or Consul, but requests will fail.

This article distinguishes port types, explains port mapping and NAT, presents Docker/Kubernetes examples, and shows how to choose a registration address matching the consumer's network location.

## 1. Three Port Concepts to Distinguish

When reading container configurations, distinguish:

| Concept | Meaning | Example |
|---|---|---|
| Container port | Port on which the application process listens inside the container's network namespace | Spring Boot listens on 8081 |
| Published/host port | Port published on the host for clients outside the container to access | Host receives on 18081 |
| Target port | Destination port to which the forwarding layer sends requests into the container or Pod | 8081 |

For example:

~~~text
Spring Boot in container
  server.port = 8081
        |
        v
Container IP:8081
        |
        | Port mapping / DNAT
        v
Host IP:18081
~~~

The application still listens on 8081. Publishing port 18081 does not change server.port inside Spring Boot; it creates an access path from the host or external network to container port 8081.

### EXPOSE Is Not the Same as Publishing a Port

In a Dockerfile:

~~~dockerfile
EXPOSE 8081
~~~

EXPOSE documents the port the container intends to use as image metadata. This instruction does not automatically open a port on the host, create a NAT mapping, or guarantee firewall access.

To publish a port, configure it when running the container, for example:

~~~bash
docker run -p 18081:8081 inventory-service:latest
~~~

The reading convention is host-port:container-port. Docker forwards traffic arriving on host port 18081 to port 8081 of the container.

## 2. Port Publishing and NAT Mapping in Docker

When publishing a port, Docker sets up traffic forwarding from a host address to the container's address and port. Depending on the platform and network mode, this may be implemented using iptables/nftables, a proxy, or an equivalent networking mechanism.

~~~mermaid
flowchart LR
    CLIENT["External client"]
    HOST["Docker host<br/>192.0.2.10:18081"]
    NAT["Port mapping / DNAT<br/>18081 -> 8081"]
    CONTAINER["Container<br/>172.20.0.5:8081"]
    APP["Spring Boot<br/>server.port=8081"]
    CLIENT --> HOST
    HOST --> NAT
    NAT --> CONTAINER
    CONTAINER --> APP
~~~

Docker example:

~~~bash
docker run --name inventory \
  -p 18081:8081 \
  inventory-service:latest
~~~

In the example:

- Spring Boot listens on port 8081 inside the container.
- Docker publishes port 18081 on the host.
- External clients call host-address:18081.
- Docker forwards requests to container-address:8081.

If you declare -p 8081:8081, the host port and container port share the same number, yet they are still two ends of a separate mapping.

### Binding a Specific Host Address

You can restrict the interface on which the host port is published:

~~~bash
docker run -p 127.0.0.1:18081:8081 inventory-service:latest
~~~

This configuration publishes the port only on the host's loopback. Clients from other machines cannot reach it via the host's network address using this mapping.

If you omit the bind address:

~~~bash
docker run -p 18081:8081 inventory-service:latest
~~~

Docker generally publishes on host interfaces by default. Combine this with firewalls and network policies to restrict access sources. Do not publish a port on all interfaces just so other containers can call each other; containers on the same user-defined network can usually communicate directly using service/container DNS and the container port.

### Publishing a Random Port

Docker can choose a dynamic host port:

~~~bash
docker run -P inventory-service:latest
~~~

With -P, EXPOSEd ports are published to automatically chosen host ports. The host port can change across runs. If a registry registers the host address, you must know the actual host port after the container is created. Do not assume the host port always matches the container port.

Check active mappings:

~~~bash
docker port inventory
docker inspect inventory
~~~

## 3. Which Address and Port Should Be Registered in the Service Registry?

The registry needs to store the address consumers will use to call the instance. That address depends on the consumer's location and the designed network path.

Suppose:

~~~text
Docker host:       192.0.2.10
Container IP:      172.20.0.5
Container port:    8081
Published port:    18081
Service ID:        inventory-service
~~~

There may be two different call paths:

| Consumer location | Usable address |
|---|---|
| Another container on the same Docker network | inventory:8081 or container DNS/IP:8081 |
| Client going through the Docker host | 192.0.2.10:18081 |

If order-service and inventory-service are on the same Docker network, order-service should normally call inventory-service:8081. This path does not need to loop through the host published port.

If the consumer is outside the Docker host, it may not be able to route to private IP 172.20.0.5. In that case, you need to advertise a reachable host address with published port 18081, or place a load balancer/reverse proxy with a stable address in front.

There is no single host/port that is always right for every consumer. The provider must register an endpoint suited to the network scope the consumer actually uses. If consumers span different network scopes, design discovery boundaries or a stable intermediary address rather than advertising an address reachable by only one group.

## 4. Registering the Wrong Port Causes Discovery to Succeed but Calls to Fail

A common error is when the provider registers the container port while consumers call via the host port, or vice versa.

For example, the provider listens inside the container on 8081, and Docker publishes 18081. If the provider registers host 192.0.2.10 with port 8081, external consumers will call:

~~~text
http://192.0.2.10:8081
~~~

Whereas the actual mapping only accepts connections on:

~~~text
http://192.0.2.10:18081
~~~

The result can be connection refused or timeout. Eureka/Consul may still show the instance because registration only stores the supplied data; the registry does not necessarily test every network path from each consumer.

Conversely, if a consumer on the same Docker network calls host port 18081 when the host mapping only binds loopback or is not routable from the container, requests can also fail. Identify the network path before choosing the registration address.

~~~mermaid
flowchart TD
    R["Registry returns host:8081"]
    C["Consumer outside Docker host"]
    BAD["Wrong target: host:8081"]
    GOOD["Right target: host:18081"]
    APP["Container app:8081"]
    R --> C
    C --> BAD
    BAD -->|"No matching mapping"| FAIL["Connection refused / timeout"]
    C --> GOOD
    GOOD -->|"DNAT 18081 -> 8081"| APP
~~~

## 5. Spring Boot and Docker Compose Configuration

Suppose inventory-service runs in a container on port 8081 and publishes host port 18081.

Docker Compose:

~~~yaml
services:
  inventory-service:
    image: inventory-service:latest
    environment:
      SERVER_PORT: 8081
    ports:
      - "18081:8081"
    networks:
      - backend

  order-service:
    image: order-service:latest
    networks:
      - backend

networks:
  backend:
    driver: bridge
~~~

Spring Boot inside inventory-service listens on port 8081. From order-service on the same network, the appropriate call address is:

~~~text
http://inventory-service:8081
~~~

From the host machine, the access address is:

~~~text
http://localhost:18081
~~~

These are two different access paths to the same application. If order-service uses service discovery, the provider's registered info must match the network order-service uses. In this example, the provider should advertise DNS name inventory-service and port 8081 for consumers on the same network.

### Eureka Configuration for Consumers on the Same Docker Network

For example, the provider can advertise a hostname resolvable on the Docker network:

~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081

eureka:
  instance:
    hostname: inventory-service
    prefer-ip-address: false
    non-secure-port: 8081
~~~

The hostname is only suitable if consumers can resolve inventory-service and connect to port 8081 on the same network. Inspect the instance record in Eureka to confirm that the actual registered hostname and port match expectations.

If consumers are outside the Docker network and only access via the host published port, the provider must advertise the host address and port 18081 or use a stable gateway/load balancer. A standard Eureka instance does not automatically know that one consumer needs the host port while another needs the container port.

### Avoid Using One Registration Configuration Incorrectly Across Networks

A provider may have multiple access paths, but a Eureka registration typically provides one primary endpoint per instance. If there are consumers both inside and outside the Docker network, consider:

- Routing consumers through an API Gateway or load balancer with a stable address.
- Separating registries or discovery scopes by network if two consumer groups require different endpoints.
- Using DNS routing tailored to each consumer's network when the infrastructure supports split-horizon DNS.
- Placing providers and consumers onto a shared overlay network with uniform routing.

Do not register two fake instances under the same service ID just to represent two ports of one process without clear routing policies and lifecycle management. Doing so can cause LoadBalancer to send duplicate requests or misdistribute traffic.

## 6. Consul Configuration: Agent Port and Service Port Are Two Different Ports

With Consul, the application connects to the agent's HTTP API, typically port 8500. This is the address for registering and querying the catalog. The service port is the provider application's port that consumers will call.

For example:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: consul-agent
      port: 8500
      discovery:
        service-name: inventory-service
        hostname: inventory-service
        port: 8081
        prefer-ip-address: false
~~~

In the example:

- consul-agent:8500 is the Consul agent API endpoint.
- inventory-service:8081 is the registered service address.
- Consumers on the same network call the provider via the service instance address.

Exact property names can vary by Spring Cloud Consul version. Check the properties supported in your release train and verify the actual address in the Consul catalog. Do not use agent port 8500 as the service port of inventory-service.

## 7. NAT, Firewalls, and Multiple Mapping Layers

In a real system, requests may pass through multiple layers:

~~~text
Internet client
  -> Public IP:443
  -> Cloud Load Balancer:443
  -> Node IP:NodePort
  -> Pod IP:8081
  -> Spring Boot
~~~

Each layer can translate the destination address or port. The registry must advertise an endpoint consumers can reach within that architecture. If consumers call through a gateway, it is usually better to use the stable gateway address rather than registering private Pod IPs.

NAT only forwards packets according to mappings. It does not automatically update the service registry or change registered metadata. When a host port, public IP, or mapping changes, the registration or corresponding DNS/gateway must also be updated.

Firewalls and security groups are a separate control layer. A published port can still be blocked by a firewall. Conversely, opening a firewall does not create a mapping if the host port has not been published or the service is not listening on the target port.

### Distinguishing Bind Address and Advertised Address

An application can bind on:

- 127.0.0.1: accepts only loopback connections within the application's network namespace.
- 0.0.0.0: accepts connections on IPv4 interfaces of that network namespace.
- A specific IP: accepts connections only via the corresponding interface.

In a container, binding 127.0.0.1 usually restricts the process to connections from inside that container. Docker port publishing cannot make an application inside a container accept connections on an interface it is not listening on.

The advertised address is the address the provider publishes to the registry. It can differ from the bind address, but it must lead to a real network path to the process. For example, the application binds 0.0.0.0:8081 inside the container, while the registry advertises hostname inventory-service:8081 for consumers on the same Docker network.

## 8. Kubernetes: containerPort, Service Port, and NodePort

Kubernetes has multiple port layers to distinguish:

| Field or port type | Meaning |
|---|---|
| containerPort | Declares the port the container is expected to listen on; does not publish outside the cluster by itself |
| targetPort | Destination port on the Pod to which the Service forwards requests |
| port | Port exposed by the Kubernetes Service inside the cluster |
| nodePort | Port opened on nodes for NodePort or LoadBalancer Services depending on configuration |
| LoadBalancer port | Frontend port provided by the load balancer infrastructure |

Deployment and Service example:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inventory-service
  template:
    metadata:
      labels:
        app: inventory-service
    spec:
      containers:
        - name: inventory
          image: inventory-service:latest
          ports:
            - name: http
              containerPort: 8081
~~~

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: inventory-service
spec:
  selector:
    app: inventory-service
  ports:
    - name: http
      port: 80
      targetPort: 8081
  type: ClusterIP
~~~

Inside the cluster, consumers call:

~~~text
http://inventory-service:80
~~~

The Kubernetes Service forwards requests to an eligible Pod at targetPort 8081. Pod IPs can change when Pods are recreated; Service DNS and virtual IP provide a stable access point.

The containerPort field in a Pod spec is declarative and supports documentation, named ports, or other integrations. It does not automatically open a port on the node. Services, NodePort, LoadBalancer, or Ingress/Gateway determine access paths across different scopes.

### Service Discovery in Kubernetes

If consumers run inside the cluster, Kubernetes Service DNS is usually a stable endpoint to call. If using Eureka or Consul inside the cluster, decide whether providers register Pod IP:8081, Service DNS:80, or a gateway address.

- Pod IP:8081 fits when consumers can route directly to Pods and you want the registry to track each replica.
- Service DNS:80 fits when you want the Kubernetes Service to handle load distribution; the registry then only needs one stable logical endpoint.
- Gateway/Ingress address fits consumers outside the cluster or scenarios requiring centralized access policy.

Do not let Eureka LoadBalancer distribute to Pod IPs while a Kubernetes Service is already load balancing unless there is a clear intent. Two load balancing layers can overlap and complicate diagnostics.

## 9. HTTPS and Published Ports

If an application listens for HTTPS inside a container on port 8443 and the host publishes 18443:8443, the two corresponding addresses are:

~~~text
Inside Docker network: https://inventory-service:8443
From host:             https://localhost:18443
~~~

The registry must advertise a scheme and port suitable for consumers. With Eureka, you can configure the secure port when the instance actually serves HTTPS:

~~~yaml
eureka:
  instance:
    secure-port-enabled: true
    secure-port: 8443
    non-secure-port-enabled: false
~~~

The example above suits consumers on the same network that can call container port 8443. If consumers outside the network must call host port 18443, advertise the corresponding endpoint or route consumers through a proxy/gateway. Enabling secure-port alone does not configure TLS for the application; Spring Boot must actually enable SSL and have a valid certificate.

If TLS terminates at an ingress/load balancer, the backend port may be HTTP while the frontend is HTTPS. In that case, decide whether consumers call the provider directly or via the frontend. Do not infer the scheme from a single port number; evaluate the TLS termination point and the endpoint advertised by the registry.

## 10. Testing the Network Path from the Consumer's Exact Location

An endpoint reachable from the Docker host is not guaranteed to be reachable from another container or from a Pod. Tests must run from the network namespace corresponding to the consumer.

With Docker:

~~~bash
docker ps
docker port inventory
docker exec order-service sh
~~~

From the shell of order-service, try:

~~~bash
curl --connect-timeout 2 http://inventory-service:8081/actuator/health
~~~

From the host, test the published port:

~~~bash
curl --connect-timeout 2 http://127.0.0.1:18081/actuator/health
~~~

With Kubernetes:

~~~bash
kubectl get svc inventory-service
kubectl get endpointslices -l kubernetes.io/service-name=inventory-service
kubectl exec deploy/order-service -- \
  curl --connect-timeout 2 http://inventory-service:80/actuator/health
~~~

Then inspect the registry:

1. Confirm the service ID and instance ID are correct.
2. Read the registered host, port, and scheme.
3. Compare against an address reachable from the consumer.
4. Call the health endpoint from the exact network path.
5. Check DNS, NAT mappings, firewalls, and TLS if requests still fail.

## 11. Common Errors and Troubleshooting

| Symptom | Possible cause | How to check |
|---|---|---|
| Registry shows instance but requests are refused | Registered wrong host port or container port | Compare published port, target port, and address used by consumer |
| Reachable from host but other containers cannot reach it | Consumer uses localhost or inappropriate host mapping | Call via service DNS and container port from the same network |
| Other containers fail calling container IP | Container is on a different network or IP changed | Check network attachment and use service DNS |
| Docker port is published but requests time out | App binds loopback, firewall blocks, or app is not listening | Check server.address, listener, and firewall |
| Eureka registers unroutable private IP | Consumer is outside the container network | Advertise host/gateway address or separate discovery scopes |
| Port changes after each container run | Using random published port | Fix the host port or update registration from the actual mapping |
| Kubernetes consumer calls wrong port | Confused port with targetPort or containerPort | Read the Service spec and EndpointSlice |
| HTTPS handshake fails | Wrong scheme, port, TLS termination, or certificate | Inspect actual endpoint and trust chain |
| Health check fails while API works from host | Agent/consumer has a different network path | Probe from the exact node/namespace running the health check |

## 12. Design Principles

- Distinguish the port the application listens on, container port, host published port, Service port, and targetPort.
- Understand EXPOSE is only metadata; port publishing or a Service is needed to create a reachable path.
- Identify the consumer's location before choosing an address and port to register.
- For consumers on the same Docker network, prefer service DNS and container port.
- For consumers outside the host, use the host address with published port or a stable gateway.
- Do not advertise a private container IP to consumers that cannot route to the container network.
- Ensure the application binds on the right interface; port mapping cannot fix binding to loopback.
- Separate the Consul agent port from the service instance port.
- In Kubernetes, distinguish containerPort, Service port, targetPort, NodePort, and LoadBalancer port.
- Check host/port/scheme in the registry and test connectivity from the consumer's exact network namespace.
- When NAT mappings or host ports change, update registrations or intermediary endpoints accordingly.

Service discovery is only useful when the registered address is actually reachable from consumers. The container port describes where the application listens; the published port creates an entry point from another network scope; NAT or a Service forwards traffic between them. When configuring Spring Cloud, choose host, port, and scheme according to the consumer's actual network path, then verify with a request from that same environment.
