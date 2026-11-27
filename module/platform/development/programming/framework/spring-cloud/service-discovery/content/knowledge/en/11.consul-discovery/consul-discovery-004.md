# Connecting Spring Cloud Consul Discovery to a Consul Agent

Spring Cloud Consul Discovery enables a Spring Boot application to register service instances and look up instances of other services through Consul. In a typical deployment model, the application communicates with a **Consul agent** over its HTTP API. The agent handles registration, query, and health check requests, then synchronizes state with the Consul server cluster.

The key takeaway is that a Spring Cloud application normally connects to the agent's API rather than participating directly in internal communication among Consul servers. The agent can run on the same machine as the application, in a sidecar container, or on a nearby node. The agent's host, port, scheme, and access permissions must match the actual network topology.

This guide explains how to configure Spring Cloud Consul Discovery to connect to an agent, distinguish client agents from servers, register instances, handle addresses in containerized environments, secure connections, and diagnose common errors.

## 1. Role of the Consul Agent in Service Discovery

Consul is typically deployed with two types of processes:

- **Consul server:** maintains cluster state, participates in consensus, stores the catalog, and coordinates data across servers.
- **Consul agent:** runs on a node or application environment, provides the HTTP/DNS interface, monitors local services and health checks, and exchanges information with the server cluster.

An agent can run in client mode or server mode. A client-mode agent does not hold a server role in the consensus cluster; it accepts requests from applications and forwards relevant updates to servers. A server agent also exposes the agent API on its own node in addition to its server membership role.

~~~mermaid
flowchart TB
    APP["Spring Boot application"]
    API["Spring Cloud Consul Discovery"]
    AGENT["Consul agent<br/>HTTP API :8500"]
    SERVER1[("Consul server A")]
    SERVER2[("Consul server B")]
    SERVER3[("Consul server C")]

    APP --> API
    API -->|"HTTP API: register / query"| AGENT
    AGENT <-->|"Gossip / RPC / catalog sync"| SERVER1
    SERVER1 <--> SERVER2
    SERVER2 <--> SERVER3
    SERVER3 <--> SERVER1
~~~

Spring Cloud applications use the agent API to register services, deregister, or query discovery data. The agent handles participation in the Consul system according to infrastructure configuration.

### Agent API and Consul Ports

Common default ports:

| Port | Protocol | Role |
|---|---|---|
| 8500 | HTTP or HTTPS when TLS is enabled | HTTP API and Consul agent web UI |
| 8600 | DNS or DNS-over-TLS depending on configuration | Consul DNS queries |
| 8300 | TCP | RPC between Consul servers |
| 8301 | TCP/UDP | LAN gossip |
| 8302 | TCP/UDP | WAN gossip across servers/datacenters |

Spring Cloud Consul Discovery connects to the agent's HTTP API, typically port 8500. Do not configure a Spring Cloud application to point at RPC port 8300 or gossip ports for service discovery. Internal cluster ports are managed by the Consul agent and network infrastructure.

Ports can vary depending on Consul configuration. Confirm the actual ports on the running agent, firewall, and container port mappings before configuring applications.

## 2. Why Should Applications Connect to a Nearby Agent?

In production environments, the common model is running one Consul agent on each node or within the same network zone as the workload. Applications connect to the local agent; the agent communicates with the Consul server cluster.

This approach offers several benefits:

- Applications do not need to know the server list, consensus topology, or gossip mechanics.
- The agent can run health checks from a network perspective close to the workload.
- Multiple applications on the same node can share the common agent API.
- Infrastructure can change server counts or clustering layouts with minimal impact on application configuration.
- API access can be scoped and restricted at the agent level or via ACL policies.

Connecting directly to a remote agent is still usable in development or intentionally designed architectures, but you must account for reachability, ACLs, TLS, and blast radius if that agent fails.

A local agent does not imply `localhost` in every environment. If the application and agent run in two separate containers, `localhost` inside the application refers to the application container itself. In that case, use the agent's DNS/service name on the shared Docker network, a published host address, or an address routable from the application container.

## 3. Adding the Spring Cloud Consul Discovery Dependency

The application needs the appropriate starter so Spring Cloud creates the discovery components and auto-configuration for Consul.

Example Maven dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
~~~

Manage the Spring Cloud version via the Spring Cloud BOM compatible with your project's Spring Boot version. Avoid picking standalone starter versions manually if the project already uses Spring Cloud dependency management.

If you want Consul to check the provider's Actuator endpoint, add Spring Boot Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Actuator is not strictly required just to connect to an agent or look up services, though it is commonly useful to expose a health endpoint for Consul. Ensure the endpoint is exposed and reachable by the agent in accordance with security policy.

## 4. Configuring the Consul Agent Address

Spring Cloud Consul uses common properties to specify the agent endpoint:

| Property | Meaning | Common Default |
|---|---|---|
| spring.cloud.consul.host | Agent hostname or IP | localhost |
| spring.cloud.consul.port | Agent HTTP API port | 8500 |
| spring.cloud.consul.scheme | Protocol used to connect to the agent | http |

Minimal configuration example in application.yml:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: localhost
      port: 8500
      scheme: http
      discovery:
        enabled: true
        register: true
        service-name: inventory-service
~~~

With this configuration, Spring Cloud Consul Discovery connects to the HTTP API at http://localhost:8500. The application registers under the service name inventory-service.

In development environments, the agent typically runs on the same machine, so localhost may work. In Docker Compose, Kubernetes, or multi-node environments, replace host with an agent address that the application can actually reach.

### Separating Configuration by Environment

Avoid hardcoding the same agent address across all environments if topologies differ. You can use Spring profiles:

~~~yaml
# application-dev.yml
spring:
  cloud:
    consul:
      host: localhost
      port: 8500
      scheme: http
~~~

~~~yaml
# application-prod.yml
spring:
  cloud:
    consul:
      host: consul-agent.service.internal
      port: 8500
      scheme: https
~~~

The production example uses HTTPS to an internal agent address. Replace the DNS name and port with your environment's actual endpoint. Secrets, ACL tokens, and trust material should be supplied from a secret manager or secure configuration mechanism, never committed to a repository.

## 5. Connecting to an Agent in Docker and Kubernetes

### Docker Compose

Suppose the application and agent run in two containers on the same Docker network. You can use the agent's service name as the hostname:

~~~yaml
services:
  consul-agent:
    image: hashicorp/consul:latest
    command: agent -dev -client=0.0.0.0
    ports:
      - "8500:8500"

  inventory-service:
    build: .
    environment:
      SPRING_APPLICATION_NAME: inventory-service
      SPRING_CLOUD_CONSUL_HOST: consul-agent
      SPRING_CLOUD_CONSUL_PORT: 8500
      SPRING_CLOUD_CONSUL_SCHEME: http
    depends_on:
      - consul-agent
~~~

This is an illustrative example for a local environment. A dev-mode agent is not suitable for production operations. Within the same Docker network, the application accesses consul-agent:8500; the host port mapping of 8500 serves access from the developer machine, not necessarily what the application container must use.

depends_on only controls container startup order in Compose; it does not guarantee the Consul agent is ready to accept API requests. The application needs appropriate connection retries or orchestration should include health/readiness checks for the agent.

### Kubernetes

In Kubernetes, an agent may run as a DaemonSet per node, a sidecar, or an internal service. Addressing depends on the deployment model:

- If the agent is a sidecar in the same Pod, the application can use localhost and the port shared in the Pod's network namespace.
- If the agent is a DaemonSet, the application needs a reachable node/agent address and a mechanism targeting the corresponding node.
- If the agent is exposed via a Kubernetes Service, the application uses the Service DNS; consider whether requests might land on an agent on a different node.

Do not assume localhost always points to the agent in Kubernetes. Only use localhost when the agent and application share a network namespace, such as a sidecar in the same Pod.

~~~yaml
spring:
  cloud:
    consul:
      host: consul-agent.default.svc.cluster.local
      port: 8500
      scheme: http
~~~

The hostname in the example is an illustrative DNS name. Replace the namespace and Service name according to your cluster. If the agent listens only on loopback, other Services or Pods cannot reach it until the bind address and network policies are configured appropriately.

## 6. Agent Address Differs From Registered Service Instance Address

These two addresses are frequently confused:

| Address | What Is It Used For? | Example |
|---|---|---|
| Consul agent endpoint | Spring Cloud sends API requests to register or query | localhost:8500 |
| Service instance address | Consumers connect to the provider's API | 10.0.2.15:8081 |

The spring.cloud.consul.host and spring.cloud.consul.port properties specify where Spring Cloud talks to the agent. They are not necessarily the host and port that consumers use to call inventory-service.

Service instance address information is configured via discovery properties or inferred from the runtime environment. Example:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        service-name: inventory-service
        prefer-ip-address: true
        health-check-path: /actuator/health
        health-check-interval: 15s
~~~

In the example, localhost:8500 is the agent address; the registered instance address is determined by Spring Cloud Consul Discovery based on instance settings and the environment. If you need to advertise a specific hostname or IP, configure the hostname/ip-address/port properties matching your Spring Cloud Consul version and verify the result in the Consul catalog.

The advertised address must be reachable from both the health check runner and consumers. For example, if a provider runs inside a container but registers 127.0.0.1, an agent in another container will probe its own loopback instead of the provider. This is a common cause of a service being registered while its health check fails.

## 7. Registering Services and Checking Health Through the Agent

When auto registration is enabled, Spring Cloud Consul Discovery sends a registration request to the agent. The agent stores the registration locally and synchronizes the catalog to servers according to Consul's mechanism.

~~~mermaid
sequenceDiagram
    participant A as Spring Boot inventory-service
    participant C as Spring Cloud Consul
    participant G as Consul agent
    participant S as Consul server
    participant O as order-service

    A->>C: Application startup
    C->>G: Register inventory-service
    G->>S: Sync catalog
    S-->>G: Registration recorded
    G-->>C: Registration result
    loop Health check
        G->>A: GET /actuator/health
        A-->>G: UP or error status
        G->>S: Update health/catalog
    end
    O->>G: Query inventory-service
    G-->>O: Instance list
~~~

Discovery configuration example:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: localhost
      port: 8500
      discovery:
        enabled: true
        register: true
        service-name: inventory-service
        instance-id: inventory-service-node-01
        health-check-path: /actuator/health
        health-check-interval: 15s
        prefer-ip-address: true

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Health check properties should be adjusted according to your starter version and environment. The Consul agent performs health checks against the registered service address; therefore, the path, port, scheme, and advertised address must be consistent. The instance ID must be unique within the Consul catalog to avoid duplicate entries or unintended overwrites.

Registering through an agent does not mean consumers must query that exact same agent. A consumer can connect to its own local agent to query the catalog; the agent forwards or serves the data via Consul's normal mechanism.

## 8. Securing Connections to the Consul Agent

The agent API can allow registering, deregistering, reading the catalog, or accessing sensitive data depending on ACLs. Never expose an unauthenticated HTTP API to untrusted networks.

Security layers typically to consider:

- **Network binding:** bind the HTTP API only on interfaces reachable by legitimate applications.
- **Firewall/network policy:** restrict sources allowed to connect to the agent API.
- **ACL:** issue tokens with the minimum privileges needed for discovery or registration operations.
- **TLS:** use HTTPS when traffic traverses untrusted networks or when policy mandates encryption.
- **Secret management:** supply ACL tokens and truststore details from a secrets manager; never store them in Git or logs.

Spring Cloud Consul provides properties to configure ACL tokens per feature such as discovery or config. Property names and scopes depend on the starter version. Consult the property reference for your exact deployed version; avoid using a single full-admin token across all services.

When the agent API uses HTTPS, set the appropriate scheme and configure the JVM to trust the agent's CA/certificate. If the system requires mutual TLS, supply client certificates per infrastructure policy. HTTPS only encrypts the connection; ACLs are still required to control permitted operations.

Do not use a Consul dev agent with default ACL/TLS settings for production. Real environments require properly configured agents, servers, ACL bootstrapping, gossip encryption, TLS, and network segmentation following Consul operational guidance.

## 9. Verifying the Agent Before Running the Application

Before starting Spring Boot, verify that the agent's HTTP API is reachable from the application's actual network namespace.

Check agent self:

~~~bash
curl http://127.0.0.1:8500/v1/agent/self
~~~

List services managed by the agent:

~~~bash
curl http://127.0.0.1:8500/v1/agent/services
~~~

Check service health from the catalog:

~~~bash
curl "http://127.0.0.1:8500/v1/health/service/inventory-service?passing=true"
~~~

These commands illustrate the default API without TLS or an ACL token. In secured environments, use HTTPS, authentication, and the appropriate header/token. Never put real tokens into command history or documentation.

After the application starts:

1. Check logs to confirm Spring Cloud connected to the agent.
2. Check the agent services endpoint to confirm the registration appears.
3. Check catalog/health to confirm the instance is passing.
4. Verify the instance address and port are reachable from consumers.
5. Perform a controlled shutdown and verify the registration is removed if deregistration is enabled.

## 10. Common Errors When Connecting to an Agent

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Connection refused on port 8500 | Agent not running, wrong port, or API not bound to suitable interface | Check agent status, listeners, and port mappings |
| Timeout when calling agent | Firewall, route, or network policy blocking connection | Test from inside the application's container/pod |
| 403 or permission denied | ACL token lacks permissions or is not sent | Check token, policy, and starter ACL properties |
| TLS handshake failure | Wrong scheme, untrusted CA, or invalid certificate | Check HTTPS, truststore, hostname, and cert expiration |
| Agent reachable but service missing | Discovery disabled, register=false, or registration error | Check dependencies, config, and startup logs |
| Service appears but health is critical | Agent cannot reach provider address or path is wrong | Check advertised host/port, network, and health-check path |
| Instance has localhost address | Advertised address inferred incorrectly inside container | Configure an IP/hostname reachable from consumers and agent |
| Consumer does not see service | Consumer querying different agent, wrong service name, or catalog not synced | Check agent endpoint, service ID, and catalog state |

### Distinguishing Agent Errors from Server Errors

If the application cannot connect to port 8500, check the agent API on the relevant node or container first. If the agent API works yet the catalog fails to synchronize or the agent logs errors communicating with servers, check membership, RPC, gossip, datacenter settings, and Consul server/agent logs.

Do not attempt to work around HTTP API errors by pointing applications at RPC or gossip ports. Those are distinct internal protocols and do not replace the API used by Spring Cloud Consul.

## 11. Implementation Principles

- Use the Spring Cloud Consul Discovery starter and a BOM version compatible with Spring Boot.
- Configure spring.cloud.consul.host, port, and scheme to point to the agent's HTTP API.
- In production, prefer a local agent or topology-appropriate sidecar instead of having every application depend directly on a single remote agent.
- Only use localhost when the agent genuinely shares the same network namespace as the application.
- Distinguish the agent endpoint from the host/port advertised by the provider to consumers.
- Ensure the agent can reach the provider's advertised address and health-check path.
- Assign unique instance IDs and keep service names consistent between providers and consumers.
- Use least-privilege ACL tokens, TLS, and appropriate network policies.
- Monitor agent status, registration errors, health checks, and catalog synchronization lag.
- Verify services in the catalog from the exact agent used by consumers.

Spring Cloud Consul Discovery connects to the Consul agent over its HTTP API to register and look up services. The agent acts as the integration point close to the application, while Consul servers manage the catalog and cluster state. Proper configuration of the agent endpoint, network namespace, advertised instance address, ACLs, and TLS ensures reliable discovery from development through production.
