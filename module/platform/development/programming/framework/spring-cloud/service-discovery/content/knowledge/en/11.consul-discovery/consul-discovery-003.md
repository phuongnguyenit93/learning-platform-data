# Initializing Consul Locally and Limitations of Development Mode

Consul provides service discovery through agents and the catalog. In a local environment, you can run a Consul agent in development mode to experiment with service registration, health checks, lookups via the HTTP API, and Spring Cloud Consul integration.

The `consul agent -dev` command quickly starts a single node for learning and testing. This mode uses a minimal configuration, stores ephemeral data, and does not create a high-availability cluster. It is suitable for understanding discovery flows on a personal machine, but it is not a production deployment configuration.

## 1. Consul Agent and Core Components

Consul is not merely a server process receiving a list of services. Each node runs a **Consul agent**. An agent can operate in server mode or client mode:

- **Server agent:** participates in the Consul cluster, maintains the catalog and cluster state, and participates in Raft consensus to manage consistent data.
- **Client agent:** runs on workload nodes, executes health checks, registers services, and forwards queries to servers.
- **Service:** an application or process that Consul advertises so consumers can discover it.
- **Health check:** a check verifying service or node condition, such as HTTP, TCP, TTL, or script checks depending on configuration.
- **Catalog:** the collection of services and nodes known to Consul; consumers can query it via the HTTP API, DNS, or integration libraries.

In a real-world system, client agents typically run close to workloads and connect to one or more server agents. In local dev mode, a single agent combines the server role with client interfaces so testing does not require standing up an entire cluster.

## 2. Installing and Verifying the Consul CLI

You need the Consul binary on your development machine. After installation, open a terminal and verify:

```bash
consul version
```

The command prints the CLI version. If the terminal reports that the command is not found, verify that Consul is installed and the directory containing the binary is in your PATH.

You can run Consul directly from an open terminal. When using a local environment, keep the agent process running while testing; press Ctrl+C in that terminal to stop the agent when finished.

## 3. Starting Consul in Development Mode

Run the command:

```bash
consul agent -dev -ui -client=127.0.0.1
```

Flag meanings:

- `agent`: starts a Consul agent.
- `-dev`: enables single-node development configuration, convenient for learning and local testing.
- `-ui`: enables the web management UI.
- `-client=127.0.0.1`: restricts client interfaces such as the HTTP API/UI to loopback so only the local machine can access them.

In dev mode, Consul automatically initializes a single server and uses ephemeral storage. You do not need to configure cluster bootstrapping or peer servers for this exercise.

Once the agent starts, you can access the UI:

```text
http://127.0.0.1:8500/ui/
```

The default HTTP API typically listens on port `8500`. Consul's DNS interface typically uses port `8600`. Ports and bind addresses can vary depending on configuration; check startup logs if the UI is unreachable.

### Verifying the Agent

Open a second terminal and run:

```bash
consul members
```

The command displays members known to the agent. In single-node dev mode, you typically see only one local member in the alive state.

You can check the leader:

```bash
curl http://127.0.0.1:8500/v1/status/leader
```

In a single-server dev setup, the API returns the current leader address. If the response is empty or unreachable, verify that the agent is still running and inspect startup logs.

## 4. Exploring the UI and HTTP API

The Consul UI helps inspect services, nodes, and health checks. Open the Services tab to view registered services. When no applications have registered yet, the list of business services may be empty; this is normal.

Commonly used APIs:

| API | Purpose |
|---|---|
| `GET /v1/agent/self` | Read local agent configuration and metadata |
| `GET /v1/agent/services` | List services registered on the local agent |
| `GET /v1/catalog/services` | List services in the cluster catalog |
| `GET /v1/health/service/{service}` | Read instances and health checks of a service |
| `GET /v1/status/leader` | Read the leader address of the Consul server cluster |

Example to view services in the catalog:

```bash
curl http://127.0.0.1:8500/v1/catalog/services
```

The result is a JSON map of service names to lists of tags. If no services other than system services have been registered, the desired application service may not appear yet.

Read the health of a specific service:

```bash
curl http://127.0.0.1:8500/v1/health/service/inventory-service
```

The API returns instances and associated check statuses. You can request only passing instances with the `passing=true` parameter:

```bash
curl "http://127.0.0.1:8500/v1/health/service/inventory-service?passing=true"
```

Note: `/v1/agent/services` reflects registrations managed by the local agent; `/v1/catalog/services` is the cluster catalog view. The two APIs have different scopes and should not be used interchangeably when investigating errors.

## 5. Registering a Test Service Directly via the Agent

You can register a simple service using the agent's HTTP API. For example, register a service named `demo-api` on port `8081` with an HTTP health check:

```bash
curl --request PUT \
  --data '{
    "Name": "demo-api",
    "ID": "demo-api-local-1",
    "Address": "127.0.0.1",
    "Port": 8081,
    "Check": {
      "HTTP": "http://127.0.0.1:8081/actuator/health",
      "Interval": "10s",
      "Timeout": "2s"
    }
  }' \
  http://127.0.0.1:8500/v1/agent/service/register
```

This example assumes a demo application is running on port `8081` and exposes the corresponding health endpoint. If the endpoint does not exist or the application is not running, the check will fail and the service will be marked critical.

After registering, verify:

```bash
curl http://127.0.0.1:8500/v1/agent/services
curl http://127.0.0.1:8500/v1/health/service/demo-api
```

To deregister the test registration:

```bash
curl --request PUT \
  http://127.0.0.1:8500/v1/agent/service/deregister/demo-api-local-1
```

The deregister API requires the registration ID on the agent. Do not confuse this ID with the service name; a single service can have multiple distinct registration/instance IDs.

## 6. Connecting Spring Boot to Local Consul

Spring Cloud Consul provides discovery integration so a Spring Boot application can register and look up services through a Consul agent. Your project needs the discovery dependency matching your Spring Cloud version, typically the Consul Discovery starter, along with Spring Boot Actuator if using HTTP health checks.

Example provider configuration:

```yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      host: 127.0.0.1
      port: 8500
      discovery:
        register: true
        service-name: ${spring.application.name}
        health-check-path: /actuator/health
        health-check-interval: 10s

server:
  port: 8081

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

When the application starts, discovery integration can register `inventory-service` with the local Consul agent. The agent runs health checks as configured and updates the status in the catalog.

Values that must match your environment:

- `spring.application.name` defines the logical application name.
- `spring.cloud.consul.host` and `port` point to the Consul agent's HTTP API.
- `service-name` is the registered service name; if overridden, consumers must look up that exact name.
- `health-check-path` must exist and be reachable from the agent.
- `server.port` is the application port advertised by the provider, not the Consul port.

If running the application inside a container, `127.0.0.1` inside the container refers to the container itself, not the host machine. In that case, configure a hostname or address reachable from the container to the Consul agent, and adjust the advertised service address so consumers can connect.

### Health Endpoint Example

With the Spring Boot Actuator dependency, the default health endpoint is typically `/actuator/health`. You can verify it directly:

```bash
curl http://127.0.0.1:8081/actuator/health
```

If the Consul health check cannot reach the endpoint, verify that the application has started, check the port, path, network, and exposure configuration. Do not over-expose management endpoints just to make a test exercise work.

## 7. Looking Up Services from a Consumer Application

The consumer also needs configuration to connect to the Consul agent. Example:

```yaml
spring:
  application:
    name: order-service
  cloud:
    consul:
      host: 127.0.0.1
      port: 8500
      discovery:
        register: true
```

The consumer can use `DiscoveryClient` to retrieve the instance list:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class InventoryLookup {

    private final DiscoveryClient discoveryClient;

    public InventoryLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInventoryInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
```

The result is the list of instances visible to the discovery client. If the list is empty, check the service name, registration, health checks, and catalog view.

To make HTTP calls by service name, you can use a client integrated with Spring Cloud LoadBalancer. Add the corresponding LoadBalancer dependency and configure the client appropriately; the Consul Discovery starter alone does not automatically guarantee that every HTTP client resolves a service hostname as a service ID.

## 8. What Dev Mode Helps You Test

Consul local dev mode is suitable for practicing:

- Starting an agent and inspecting the UI/API.
- Registering services manually or via Spring Cloud Consul.
- Observing service ID, instance ID, address, port, and tags.
- Declaring HTTP/TCP/TTL health checks.
- Querying the catalog and health endpoints.
- Testing service registration, updates, and deregistration.
- Verifying how a consumer uses `DiscoveryClient` and LoadBalancer.

You can try a complete end-to-end flow:

1. Start the Consul agent in dev mode.
2. Start `inventory-service` with Consul configuration.
3. Verify the service appears in the UI or `/v1/catalog/services`.
4. Verify a passing health check via `/v1/health/service/inventory-service?passing=true`.
5. Start `order-service` and invoke a lookup through `DiscoveryClient`.
6. Stop the provider and observe the health check or registration update, depending on shutdown behavior and deregistration settings.

These steps build familiarity with the service lifecycle in a simple environment before working with multi-node clusters.

## 9. Limitations of Development Mode

`-dev` is designed for local testing. Main limitations:

### Ephemeral Data, Not Persistent Storage

Consul dev mode stores data in memory in a temporary environment. When the agent stops, test registrations and state can be lost. Do not use this mode as a persistent catalog for systems that must recover after restarts.

### Single Server, No High Availability

A single-node dev agent has no server peers to maintain quorum or continue serving when the node fails. If the agent stops, the local discovery API stops as well. Consumer caches may hold stale data for a short time, but that does not turn a dev agent into an HA cluster.

### Does Not Simulate Real Failure Domains

A local node cannot adequately represent scenarios like inter-server network loss, losing an availability zone, quorum loss, slow replication, or client agents losing connectivity to servers. Those behaviors require a cluster environment and dedicated test scenarios.

### Simplified Configuration Does Not Reflect Production Security

Do not assume dev mode defaults satisfy production requirements for ACLs, TLS, gossip encryption, network segmentation, or token governance. Dev mode is configured to minimize setup steps, so you must proactively configure full security when building real environments.

### Not Shared Across Multiple Users or Environments

Local data can be altered by other exercises, processes, and applications running on the same machine. A test service might collide in name with another service, a health check might point to the wrong port, or someone might stop the agent while another application still depends on it.

### Does Not Accurately Reflect Load and Scale

A single agent does not indicate the capacity of a multi-server cluster when the number of registrations, health checks, and queries scales up. Never use benchmark results from dev mode to draw conclusions about production capacity.

## 10. From Local Dev to Production Configuration

When moving from learning to real environments, deployment practices must change:

| Aspect | Local Dev | Production |
|---|---|---|
| Server count | One dev agent | Multi-server cluster, typically 3 or 5 servers to maintain quorum |
| Data | Ephemeral, in memory | Persistent data directory and backup/snapshot procedures |
| Bootstrap | `consul agent -dev` | Controlled cluster configuration, bootstrap expectation, and peer joining |
| Client agent | Combined in local process | Client agents on nodes/workloads or appropriate connection topology |
| Security | Loopback and minimal setup | ACLs, tokens, TLS, gossip encryption, and network policies |
| Health checks | Local checks for learning | Checks reflecting actual readiness, timeouts, and dependencies |
| Observability | Local UI and CLI | Metrics, logs, auditing, alerts, and quorum monitoring |
| Recovery | Restart and re-register | Snapshot/restore, controlled upgrades, and incident drills |

A Consul server cluster uses Raft consensus and therefore requires quorum for consistent changes. With 3 servers, the cluster tolerates losing one server; with 5 servers, it tolerates losing two servers, provided the remaining nodes can still communicate and reach quorum. Adding too many servers does not automatically make the cluster better; choose an appropriate node count and placement topology.

Do not use `-dev` for production deployments. Create dedicated agent configurations, configure persistent data directories, declare accurate bind/advertise addresses, set server/client roles, enable ACL/TLS/gossip encryption, restrict network access, and test backup/restore.

## 11. Common Errors When Running Consul Locally

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| `consul` command does not run | Binary not installed or PATH incorrect | Verify installation and `consul version` |
| Port 8500 already in use | Another Consul agent or process is listening on the port | Check running processes and port settings |
| Cannot open UI | Agent not running, UI not enabled, or client bound off loopback | Check logs, `-ui`, and client address |
| Service does not appear | Provider not registered or pointing to wrong agent | Check `spring.cloud.consul.host/port` and agent services |
| Health check critical | Wrong endpoint, provider not running, or agent cannot reach it | Check health URL from the agent's perspective and application logs |
| Consumer receives empty list | Wrong service name, service not passing, or catalog not updated | Check catalog, health API, and registered name |
| Containerized app cannot connect | `127.0.0.1` points to the container itself | Use a hostname/host address routable to the agent |
| Data disappears after stopping agent | Running dev mode with ephemeral storage | Expected limitation; do not use dev mode for data that must persist |

When debugging, check sequentially whether the agent is running, whether the local API is reachable, whether the provider registered, whether the health check is passing, and whether the consumer looks up the exact name. This helps pinpoint whether the issue lies in the Consul agent, provider registration, health check, or consumer lookup.

## 12. Practice Checklist

1. `consul version` displays the CLI version.
2. Agent starts with `consul agent -dev -ui -client=127.0.0.1`.
3. UI opens at `http://127.0.0.1:8500/ui/`.
4. `consul members` shows the local agent.
5. `/v1/status/leader` API returns the leader.
6. Spring Boot provider connects to the right Consul host and port.
7. Service appears in the catalog with the expected name.
8. Health check is passing when the application is ready.
9. Consumer retrieves instances via `DiscoveryClient`.
10. Understand that dev mode data is non-persistent and a single agent lacks HA.

Consul local dev mode is a fast way to learn agents, the service catalog, health checks, and Spring Cloud integration. Its value lies in validating registration and lookup flows on a single machine. When persistent data, security, fault tolerance, and production scale are required, transition to a properly designed and operated Consul cluster configuration.
