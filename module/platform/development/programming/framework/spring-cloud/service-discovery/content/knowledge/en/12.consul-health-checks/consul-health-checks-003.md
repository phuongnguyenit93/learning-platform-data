# When the Address Accessed by the Consul Agent Differs from the Caller's Address

When Consul checks the health of a service, **the Consul agent is the party actively calling the health check endpoint**. When a consumer looks up a service in the catalog, the consumer connects to **the address and port registered for the service**. These two flows may traverse different networks, so the health check address and the address used by consumers do not necessarily match.

For example, an inventory application runs inside a container on port 8080. A Consul agent on the same Docker network can call the container by its internal DNS name:

~~~text
http://inventory-api:8080/actuator/health
~~~

A consumer outside the Docker host accesses the application through the published host address:

~~~text
http://203.0.113.10:18080
~~~

If the internal address is mistakenly registered as the service address for consumers, the health check can still PASS while consumers fail to connect. Conversely, the service address may be reachable from consumers while the Consul agent cannot call the health check endpoint. To diagnose accurately, determine who is making the call, from which network namespace, and which address field is being used.

## 1. Three Address Perspectives to Distinguish

In a Consul environment, there are usually at least three distinct types of addresses:

| Address Type | Who Uses It? | Purpose |
|---|---|---|
| Consul agent address | Other Consul agents or applications connecting to the agent's API/DNS | Cluster communication, accepting requests to the agent, and providing API/DNS |
| Health check address | The Consul agent managing the check itself | Calling HTTP/TCP/gRPC endpoints or running checks in the agent's environment |
| Registered service address | Consumers looking up the service in the catalog | Connecting to the actual application |

Additionally, distinguish among these agent address fields:

- **bind address** is the address the agent uses to listen/communicate on the cluster network.
- **advertise address** is the address the agent advertises for other agents to contact it.
- **client address** is the address on which the agent listens for client interfaces such as HTTP API, DNS, or gRPC according to configuration.

These addresses describe the Consul agent itself. They do not automatically become the address of the application the agent manages. The published service address lives in the service registration, typically consisting of the Address and Port fields.

## 2. Health Check Flow vs. Consumer Request Flow

With an HTTP health check, the Consul agent periodically sends requests to the URL declared in the check. The agent receives the response, evaluates the status, and updates the service's health status in the catalog.

Consumers follow a separate flow:

1. The consumer queries Consul DNS or the HTTP API to find the service.
2. Consul returns matching service instances along with their registered addresses and ports.
3. The consumer selects an instance according to application policy or a load balancer.
4. The consumer opens a connection to that instance's address and port.

The following diagram illustrates the two independent paths:

~~~mermaid
flowchart LR
    subgraph DockerNet["Internal Docker network"]
        Agent["Consul agent"]
        App["inventory-api:8080"]
        Agent -->|"HTTP health check"| App
    end
    Catalog["Consul catalog"]
    Agent -->|"Registration and health status"| Catalog
    Consumer["Consumer on external network"]
    Catalog -->|"Service address: 203.0.113.10:18080"| Consumer
    Consumer -->|"HTTP request"| Host["Docker host :18080"]
    Host -->|"Port mapping 18080 -> 8080"| App
~~~

The agent checks the container via its internal DNS name and port 8080. The consumer receives the host address and published port 18080. The two addresses differ yet lead to the same application.

A service can have a passing health status while its service address is unreachable from certain consumers. Health status only reflects check results from the perspective of the configured check; it does not prove every consumer network has a route to the service address.

## 3. Service Address vs. Address in HTTP Checks

A service registration can declare the address consumers must use:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-node-a",
    "address": "203.0.113.10",
    "port": 18080,
    "checks": [
      {
        "http": "http://inventory-api:8080/actuator/health",
        "method": "GET",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

In this example:

- the service name is inventory-service.
- the service ID inventory-node-a identifies the specific registration.
- Address 203.0.113.10 and Port 18080 form the endpoint published to consumers.
- The HTTP check calls inventory-api:8080/actuator/health from the Consul agent's environment.
- The agent runs the check periodically and updates the service's status.

The address 203.0.113.10 is a documentation example address; replace it with an actual host address or DNS name reachable by consumers. The name inventory-api must resolve from the Consul agent and port 8080 must be open on the Docker network.

If no service address is specified, Consul may use the node address as the service address according to registration rules. When an application runs behind NAT, port mapping, or a proxy, explicitly declare Address and Port to avoid accidentally publishing a node/container address unreachable from callers.

The HTTP field in a health check does not replace the service's Address and Port. The check URL tells the agent where to call to verify health; the service address tells consumers where to connect to use the service.

## 4. Example: Agent Running on the Same Machine as the Application

If the Consul agent and application run directly on the same machine, the agent can check over loopback:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-local-8080",
    "address": "192.0.2.25",
    "port": 8080,
    "check": {
      "http": "http://127.0.0.1:8080/actuator/health",
      "interval": "10s",
      "timeout": "2s"
    }
  }
}
~~~

Here, 127.0.0.1 is the loopback address the agent calls on the local machine. Consumers on other machines use 192.0.2.25:8080. These two different addresses reach the same process if firewalls and routing permit.

Do not register 127.0.0.1 as the service address if consumers run on other machines. To a consumer, 127.0.0.1 always means the consumer's own machine, not the provider's machine.

If the agent runs on a different machine from the application, the agent's loopback points to the agent's own machine. In that case, the check must use a hostname or IP the agent can actually reach, such as the application host's private IP.

## 5. Example: Application in Docker Behind NAT/Port Mapping

Suppose the environment consists of:

- A Consul agent running in container consul-agent.
- An inventory application running in container inventory-api, listening on port 8080.
- Both containers attached to the discovery network.
- The Docker host publishes port 18080 and forwards it to port 8080 on inventory-api.
- Consumers sit outside the Docker network and access the host at 203.0.113.10.

The service registration configuration can use:

~~~json
{
  "service": {
    "name": "inventory-service",
    "id": "inventory-api-1",
    "address": "203.0.113.10",
    "port": 18080,
    "checks": [
      {
        "http": "http://inventory-api:8080/actuator/health",
        "interval": "10s",
        "timeout": "2s"
      }
    ]
  }
}
~~~

Paths of the two request types:

| Request | Source | Destination | Port |
|---|---|---|---:|
| Health check | consul-agent | inventory-api inside Docker network | 8080 |
| Business request | External consumer | Docker host 203.0.113.10 | 18080 |
| Port forwarding | Docker host | inventory-api | 8080 |

This configuration works only if:

1. The Consul agent can resolve the name inventory-api.
2. Both the Consul agent and inventory-api are connected to the discovery network.
3. The application listens on an interface reachable from the container network, typically 0.0.0.0 inside the container.
4. The Docker host actually publishes 18080 to the right container and port 8080.
5. Consumers have a route to 203.0.113.10 and firewall rules allow the connection.

If the agent runs on the host instead of inside a container, the health check URL might be http://127.0.0.1:18080/actuator/health or a suitable host-local address. Choose the URL based on where the agent runs and the network path the agent can traverse.

Do not blindly use localhost in the check URL. If the Consul agent runs in its own container, localhost is the agent container itself; it does not point to the application container.

## 6. When Agent and Consumers Are in Multiple Different Networks

A service can be visible from multiple network zones:

- Container internal network using DNS service name and internal port.
- Host network using private IP or internal DNS.
- External network using a public address, ingress, or reverse proxy.

No single address is always reachable from every network zone. Selecting the service address must be based on the actual consumer group.

Common deployment models:

| Model | Published Service Address | When Appropriate |
|---|---|---|
| Shared internal network | Private IP or internal DNS | Agent and all consumers share routing |
| Container behind port mapping | Host IP/DNS and published host port | Consumers are outside the Docker network |
| Application behind reverse proxy | Proxy DNS and proxy port | Consumers are only allowed access via a gateway |
| Multiple isolated network zones | Separate registrations per network or intermediate endpoint | Consumer groups cannot reach the same address |

If the same service is used by consumers across different networks, clearly identify which networks are supported access sources. You can register separate service entries with a service name or tag/metadata indicating network/zone, and let consumers query the matching group. Filters or routing policies must be configured on the consumer side; metadata alone does not automatically change the returned address.

If it is impossible to guarantee a single service address reachable from every consumer, place a gateway or load balancer in between and publish the gateway's address. The gateway handles forwarding to internal instances.

## 7. Consul Agent Addresses Are Not Service Addresses

A Consul agent has its own network configuration. Illustrative example configuration:

~~~hcl
bind_addr = "10.10.0.12"
advertise_addr = "10.10.0.12"
client_addr = "127.0.0.1"
~~~

Meaning:

- bind_addr specifies the address the agent uses for cluster communication.
- advertise_addr is the address the agent advertises to other agents.
- client_addr specifies the addresses where the agent listens for client interfaces such as HTTP API and DNS as configured.

These values do not replace service.address in a registration. If a Consul agent runs inside a container, advertise_addr must suit inter-agent connectivity. If a consumer needs to call an application, the consumer must still use the application's service address and port or a published intermediate endpoint.

Common mistakes:

| Misconfigured Setting | Consequence |
|---|---|
| Using advertise_addr as service address | Consumers connect to the Consul agent instead of the application |
| Using the agent's client_addr as provider address | Requests hit the agent's API/DNS rather than the application |
| Using an internal container address for external consumers | Consumers have no route to the container IP |
| Using a public address in an internal health check when firewall blocks hairpin NAT | Agent cannot reach the check even though the app is reachable internally |
| Using localhost in check when agent is in another container | Agent mistakenly calls the agent container itself |

## 8. Diagnosing When Health Check PASSES but Consumers Cannot Connect

This case usually means the agent successfully checked the health endpoint, but the service address returned to consumers is unusable from the consumer's network.

Check step by step:

1. **Inspect registration:** read service Address, Port, ID, and checks in the Consul catalog or Agent API.
2. **Locate the agent:** does the agent run on the host, in a container, or on a separate machine? Identify the agent's network namespace.
3. **Test the health URL from the right place:** run curl from the agent's actual host/container to the check URL. A command run from an operator's laptop does not prove the agent has the same reachability.
4. **Test the service address from the consumer:** from the consumer machine or container, call the exact Address and Port returned by Consul.
5. **Check NAT/proxy/firewall:** verify port mappings, routes, security groups, firewalls, and reverse proxies.
6. **Check DNS:** does the hostname resolve identically across networks? Docker internal DNS may not exist for consumers outside Docker.
7. **Compare HTTP responses:** the health endpoint may return 200 while business APIs, paths, TLS, or authentication at the consumer address still fail.

Example check from the agent's environment:

~~~bash
curl -i --max-time 3 http://inventory-api:8080/actuator/health
~~~

Example check from an external consumer:

~~~bash
curl -i --max-time 3 http://203.0.113.10:18080/api/inventory
~~~

The two commands must be run from their respective environments. Running both from the same machine may fail to reflect actual network paths.

## 9. Diagnosing When Consumers Can Connect but Health Check Is CRITICAL

The opposite situation occurs when consumers reach the service address successfully, yet the agent cannot call the check URL. Possible causes:

- The check URL uses localhost while the agent sits in another container or host.
- The check URL uses a hostname only resolvable by consumers, absent from the agent's DNS.
- A firewall permits the consumer subnet but blocks the Consul agent's subnet.
- The application binds only to loopback and does not listen on the container/private network interface.
- The health endpoint requires headers or certificates not configured on the check.
- The timeout is too short or the endpoint depends on a slow downstream service.
- The check uses HTTPS but the certificate is untrusted by the agent or the hostname mismatches.

Fix the check URL or network/credential configuration so the agent can inspect the endpoint properly. Do not fake a passing check to mask connectivity errors. If the application uses a TTL check instead of an HTTP check, distinguish the mechanism: the agent does not actively poll an HTTP endpoint; an external process must send periodic TTL updates.

## 10. HTTP Health Checks and Service Addresses May Use Different Protocols

Health checks and business requests can use different protocols or endpoints:

- The agent uses internal HTTP to check /actuator/health.
- Consumers use HTTPS through a reverse proxy.
- The agent runs a TCP check against an internal port.
- Consumers call an API through an authenticated gateway.

This can be valid if both addresses accurately represent the same service and the health check genuinely reflects serving capability. However, if the health check only verifies that the process is alive without checking critical dependencies, a passing status may not reflect the ability to process business requests.

When configuring an HTTP check, you can set method, interval, timeout, and headers according to what your Consul version supports. If using TLS, ensure the agent trusts the certificate. Avoid disabling TLS verification in production merely to force a check to pass.

For authenticated health checks, do not place secrets directly in committed config files. Use the environment's secret management mechanism and restrict read permissions on check configurations. Health endpoints should not return internal details or sensitive data.

## 11. Sample Service Registrations for Various Network Topologies

### Agent on the Same Host

~~~json
{
  "service": {
    "name": "payment-service",
    "id": "payment-host-8080",
    "address": "192.0.2.50",
    "port": 8080,
    "check": {
      "http": "http://127.0.0.1:8080/actuator/health",
      "interval": "15s",
      "timeout": "3s"
    }
  }
}
~~~

The agent checks via loopback; consumers use the host address 192.0.2.50:8080.

### Agent in the Same Docker Network

~~~json
{
  "service": {
    "name": "catalog-service",
    "id": "catalog-container-1",
    "address": "catalog-api",
    "port": 8080,
    "check": {
      "http": "http://catalog-api:8080/actuator/health",
      "interval": "10s",
      "timeout": "2s"
    }
  }
}
~~~

Both agent and consumer must resolve catalog-api and have a route to port 8080. If consumers sit outside the Docker network, this address is unsuitable; publish a host/proxy endpoint reachable by consumers.

### Agent Checks Internally, Consumers Connect via Reverse Proxy

~~~json
{
  "service": {
    "name": "report-service",
    "id": "report-node-1",
    "address": "reports.example.internal",
    "port": 443,
    "checks": [
      {
        "http": "http://report-api:8080/actuator/health",
        "interval": "15s",
        "timeout": "3s"
      }
    ]
  }
}
~~~

The agent checks the internal application via Docker DNS. Consumers access it through the reverse proxy's DNS name and HTTPS. The reverse proxy must route properly to report-api and handle TLS as configured.

Addresses in these examples are illustrative only. Before using them, replace hostnames, IPs, ports, and paths with details from your actual environment; test reachability from both the agent and consumers.

## 12. Impact on Discovery and Load Balancing

Consul health status can be used to filter instances when consumers query passing services. For example, clients can request only instances currently passing. However, health filtering cannot fix an incorrect service address.

Two main outcomes can occur:

| Health Check | Service Address | Outcome |
|---|---|---|
| Passing | Reachable from consumer | Consumer can call the instance |
| Passing | Unreachable from consumer | Discovery returns the instance, but requests fail |
| Critical | Still reachable from consumer | Consumers querying passing instances may skip the instance |
| Critical | Unreachable | Instance is both unhealthy per check and unservable |

A load balancer should use an instance list suited to the consumer's network. If consumers reside in different networks, filter by zone/network or return a shared reachable endpoint. Do not assume every instance in the catalog can be called directly by every client.

Even when checks are passing, addresses can become stale after container recreation, IP changes, or port mapping changes. Update registrations when endpoints change and monitor for stale service records. Deregistration after a period in critical state can be configured to clean up registrations, provided the duration aligns with check intervals and deployment behavior.

## 13. Security and Operational Principles

Service addresses are routing data. If a registration publishes incorrect data or is modified by an untrusted workload, consumers can send requests to an unintended host.

Principles to apply:

- Restrict service registration and update permissions in Consul using ACLs.
- Allow only Consul agents and consumers to access required ports.
- Protect the agent's HTTP API and DNS interface; do not expose client interfaces indiscriminately.
- Use TLS for connections requiring protection and verify certificates properly.
- Keep tokens, passwords, and sensitive data out of metadata and health endpoints.
- Record service ID, node, service address, port, check URL, and status when investigating incidents.
- Keep check and registration configurations consistent with the real network after every deployment.
- When changing addresses, verify both the agent check and the consumer access path before concluding the rollout.

Do not look at a green dashboard alone and conclude a service is ready for every caller. Verify the exact address used by the consumer group and the exact network path requests travel.

## 14. Practical Checklist

Follow this workflow when a service health check runs over one address while consumers call a different address:

1. Record the Consul agent's addresses and ports, including bind/advertise/client if relevant.
2. Identify where the agent runs: host, container, or dedicated machine.
3. Record the check URL executed by the agent and test it from the agent's exact environment.
4. Record Service.Address and Service.Port in the registration.
5. Query the service from the consumer's perspective to see the exact address the consumer receives.
6. Test calling that address from the consumer—do not substitute test results from another host.
7. Inspect Docker DNS, port mappings, NAT, firewalls, routes, and reverse proxies.
8. Fix either the check URL or the service address according to each field's distinct role.
9. Wait for a health check cycle, verify the status, and call again from the consumer.
10. Re-check after restarting containers or agents to catch stale addresses or duplicate registrations.

After this lesson, clearly distinguish: **the Consul agent calls health checks from the agent's network; consumers connect to the service address and port in the catalog; bind/advertise/client addresses describe the agent itself.** Only when both paths match the real network topology is a service simultaneously evaluated as healthy and usable by consumers.
