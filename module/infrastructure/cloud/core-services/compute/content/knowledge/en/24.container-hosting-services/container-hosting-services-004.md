# Container Networking, Service Ports, and Service Discovery

When running applications in containers, each component can be created, replaced, or moved to another machine during deployments and scaling. Consequently, a container's IP address is typically ephemeral. Components need a reliable way to connect, know which port is accepting requests, and locate target services without manually configuring individual IP addresses.

This lesson belongs to the **Container Hosting Services** chapter in the **CLOUD_CORE_SERVICES_COMPUTE** module. It focuses on how containers join networks, how ports are mapped from applications to external consumers, and how services discover one another in cloud container environments. This knowledge is essential for deploying applications, scaling under load, maintaining availability, and controlling operational costs.

After this lesson, you will be able to:

- Distinguish between application port, container port, host port, and service port.
- Choose the appropriate connectivity pattern between containers and between containers and users.
- Explain the roles of DNS, service registries, health checks, and load balancers in service discovery.
- Configure and verify connectivity using Docker Compose or Kubernetes.
- Isolate common errors involving ports, DNS, endpoints, firewalls, and readiness state.

## 1. Path of a Network Request

Containers typically run in an isolated networking environment. The runtime or orchestration platform assigns each container a network interface, IP address, routes, and connectivity rules. Containers on the same network can exchange data via addresses or service names; external traffic usually enters through published ports, a load balancer, or an ingress.

A typical HTTP flow in a cloud environment might look like:

```mermaid
flowchart LR
    U[Users] --> DNS[Public DNS]
    DNS --> LB[Load balancer]
    LB --> IN[Ingress or gateway]
    IN --> SVC[Container service]
    SVC --> APP[Application container]
    APP --> DB[Database container]
```

Each layer has a distinct responsibility:

- **Public DNS** resolves the application's domain name to the entry point's address.
- **Load balancer** receives traffic, checks target health, and distributes requests to healthy instances.
- **Ingress or gateway** applies HTTP/HTTPS routing rules by host, path, or other conditions.
- **Service** provides a stable access point for a dynamic pool of containers that changes over time.
- **Application container** processes requests and calls downstream dependencies, such as databases or message queues.

Not every deployment needs all of the layers above. A small application can use a single load balancer in front of a service; a multi-API system can use an ingress or gateway to consolidate routing rules. Clearly define which layer terminates TLS, performs health checks, and enforces access controls to avoid duplicate or missing configurations.

## 2. Understanding Service Ports Properly

A process inside a container must open a socket on an address and port to accept connections. For web services, the application typically listens on a TCP port such as `8080` or `3000`. Inside a container, the application usually needs to bind to `0.0.0.0` to accept connections arriving on the container's network interface. Binding only to `127.0.0.1` restricts the process to local connections from within that same container, making it unreachable from other containers or published host ports.

Port concepts to distinguish:

| Concept | Meaning | Example |
|---|---|---|
| Application port | The port the process inside the container listens on | API listens on TCP `8080` |
| `containerPort` | Declares the container port in platform configuration; often serves as documentation or a target for other configs to reference | Pod declares `containerPort: 8080` |
| `targetPort` | Target port inside the Pod/container to which the Service forwards traffic | Service receives on `80`, forwards to `8080` |
| Service `port` | Stable port that clients inside the cluster network use to call the Service | `orders:80` |
| `hostPort` | Port bound directly on the host machine running the workload | Host receives on `18080`, forwards to container `8080` |
| Published/mapped port | Maps a host port to a container port, common in Docker | `8080:8080` |

In Docker, `EXPOSE 8080` in a Dockerfile only documents the intended application port; it does not open a port on the host. To allow access from the host or externally, configure port publishing such as `-p 8080:8080`. Containers on the same Docker network can connect directly to each other's application ports by service name without publishing those ports to the host.

In Kubernetes, `containerPort` likewise does not automatically create firewall rules or expose the application to the Internet. A Service is the object that provides a stable address and port for Pods. A `LoadBalancer`-type Service can ask the cloud provider to provision a load balancer; an Ingress requires a running ingress controller to accept and route HTTP/HTTPS traffic.

**Configuration principle:** expose only the ports required for each client group. A public API may receive HTTPS via a load balancer; a database should typically accept connections only from backends on a private network. Never open admin or data ports to the Internet without an explicit requirement and matching safeguards.

## 3. Common Container Networking Models

### Single-Host Bridge Network

Docker creates a bridge network so containers on the same host communicate over a virtual network. Docker Compose typically creates a dedicated network per project; services on the same network can discover each other by service name.

The advantage is ease of setup, making it well suited for single-machine development and testing. The main limitation is that network scope is usually tied to that single host. When an application spans multiple nodes, cluster-level networking and orchestration are required.

### Host Network

The container directly shares the host machine's network namespace. This can eliminate a network forwarding layer and help certain specialized workloads, but reduces isolation. Processes can conflict over the same host ports, and moving workloads between nodes becomes less predictable. Choose this only with a specific technical justification and after evaluating security implications.

### Overlay or Cluster Pod Network

Overlay networks establish logical connectivity across nodes, allowing workloads on different machines to communicate as if they shared the same network. Kubernetes uses a Pod network model implemented by a CNI plugin; depending on the plugin, traffic may be routed directly or encapsulated through an overlay. Never assume every Kubernetes cluster implements networking the same way.

This model fits distributed applications and multi-node scaling. In return, operators must understand network policies, MTU, routes, DNS, and cross-node traffic observability. Misconfigurations can cause bugs that appear only when workloads land on different nodes.

### Cloud Private Networks

In managed container services, workloads typically attach to a VPC or equivalent private network. Subnets, route tables, security groups, or firewall policies determine which traffic flows are permitted inbound and outbound. Some platforms assign network IP addresses directly to Pods/tasks; others use host/node addresses or ports paired with a forwarding layer.

When designing, clearly establish:

1. Which clients need to call the service and from which network segments.
2. Which protocols and destination ports must be permitted.
3. Whether the service requires a public address or internal-only access.
4. Which routes carry return traffic, DNS, and calls to downstream dependencies.
5. Whether network rules remain valid as replica or node counts scale up.

## 4. Service Discovery: Finding Services by Stable Names

A container's IP address can change when the container restarts, gets replaced during a new release, or is rescheduled onto a different node. Hardcoding individual container IPs in application configs easily causes failures after routine operational events.

**Service discovery** solves this by providing a stable name or access endpoint. Clients call services by name; DNS, a service registry, or an orchestration layer resolves the endpoints currently serving that name. Endpoints can be added, removed, or replaced without clients needing to know specific IPs.

A service discovery system typically comprises:

- **Service name:** the logical name used by clients, such as `orders` or `payments`.
- **Registry or DNS:** stores and resolves information about active endpoints.
- **Health checks/readiness:** determines which instances are eligible to receive requests.
- **Distribution mechanism:** selects an endpoint or forwards requests through a load balancer/service proxy.
- **Client:** uses the service name and handles timeouts, retries, and connection errors according to policy.

DNS reduces dependence on raw IPs, but does not fully replace health checks or error handling. Clients may cache DNS records for a period; an endpoint recently removed from the registry can still appear in client caches. Applications need sensible timeouts and reconnection logic when endpoints change.

### Service Discovery in Docker Compose

Within a Compose project, service names act as hostnames on the Compose network. For example, the `api` service can connect to the database using hostname `db` and PostgreSQL port `5432`. Avoid using a container's internal IP because it can change whenever the container is recreated.

Abbreviated configuration example:

```yaml
services:
  api:
    build: .
    environment:
      PORT: "8080"
      DATABASE_URL: postgresql://app_user:${DB_PASSWORD}@db:5432/orders
    ports:
      - "8080:8080"
    depends_on:
      db:
        condition: service_healthy
    networks:
      - backend

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: orders
      POSTGRES_USER: app_user
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U \"$${POSTGRES_USER}\" -d \"$${POSTGRES_DB}\""]
      interval: 5s
      timeout: 3s
      retries: 10
    networks:
      - backend

volumes:
  db_data:

networks:
  backend:
    driver: bridge
```

In this example, `api` calls `db:5432` over the internal network. Only `api` publishes port `8080` to the host; PostgreSQL publishes no ports, so there is no direct access from the host via this configuration. `depends_on` with `condition: service_healthy` tells Compose to wait for the database health check before starting the API, though the application must still handle database disconnects occurring after startup. In real deployments, `DB_PASSWORD` should be supplied from a secret store or proper secrets manager; never commit real passwords to a repository.

### Service Discovery in Kubernetes

A Kubernetes Service provides a stable address in front of a set of Pods selected by labels. Cluster DNS resolves the Service name, while the control plane updates corresponding endpoints whenever Pods are created, replaced, or become unready.

Example internal Service for the `orders` application:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: production
spec:
  type: ClusterIP
  selector:
    app: orders
  ports:
    - name: http
      protocol: TCP
      port: 80
      targetPort: 8080
```

Pods in the `production` namespace can call `http://orders:80`; clients in other namespaces can use the fully qualified name `orders.production.svc.cluster.local`. The Service forwards traffic to port `8080` of Pods matching label `app: orders` that are eligible to receive traffic. If the selector does not match Pod labels, the Service can exist yet have no endpoints to forward traffic to.

`ClusterIP` serves in-cluster access only. To accept external traffic, use `LoadBalancer` or configure an Ingress/Gateway depending on requirements. Load balancers are straightforward and integrate directly with cloud providers, though each entry point can incur cost. An Ingress/Gateway can consolidate many HTTP routes behind one entry point, but requires operating a controller, TLS certificates, and routing rules.

On other cloud container platforms, the same concepts are implemented via service registries, private DNS, service connect features, or provider-managed load balancers. For instance, a container service may register tasks into a registry so other services locate them by name; the platform updates endpoints as tasks change. Always read your platform's exact networking model because IP allocation, port mapping, and DNS scope vary across providers.

## 5. Choosing Entry Points and Segmenting Traffic

A common design divides traffic into two categories:

- **North-south:** traffic entering the application from external users or systems, typically via DNS, load balancers, ingress, or gateways.
- **East-west:** traffic between services inside the system, such as an API calling a database or payment service. This traffic is normally kept on private networks and restricted on a need-to-access basis.

For example, users visit `https://shop.example.com`. DNS points the domain to a public load balancer. The load balancer terminates TLS or passes TLS through to an ingress by design; the ingress routes `/orders` to the `orders` Service. The Service selects ready Pods. When the API needs data, it calls the database or data service's internal hostname over an allowed port on the private network.

This design isolates public entry points from internal services. However, every intermediate layer introduces its own configuration, connection limits, logs, and cost. For small systems, a single load balancer may suffice. When managing many applications or routes, an ingress/gateway can reduce the number of entry points to operate. Weigh service count, TLS requirements, peak traffic, fault tolerance, and fixed costs before choosing.

## 6. Layer-by-Layer Connectivity Troubleshooting

When a client cannot reach a service, troubleshooting from the application outward narrows the root cause faster. First verify the process is listening on the expected port; then check internal networking, DNS/service, endpoints, and finally load balancers and firewalls.

### Checking with Docker

```bash
# List containers and status
docker ps

# View port mappings from host to container
docker port <container-name>

# Inspect containers attached to a network
docker network inspect <network-name>

# Test DNS resolution from the application container
docker exec <api-container> getent hosts db

# Check listening sockets inside the container
docker exec <api-container> sh -c 'ss -lnt || netstat -lnt'

# Test endpoint from the host if the port is published
curl -v http://localhost:8080/health
```

If a minimal image lacks `getent`, `ss`, `netstat`, or `curl`, attach a temporary utility container to the same network to verify DNS and connectivity. When testing from a peer container, call the service hostname and container port—for example `http://api:8080/health`—and do not use the host port unless specifically testing the host access path.

### Checking with Kubernetes

```bash
# View Services and cluster IP addresses
kubectl get svc -n production

# View endpoints selected by a Service
kubectl get endpointslices -n production \
  -l kubernetes.io/service-name=orders

# Inspect Pods, labels, and readiness status
kubectl get pods -n production --show-labels

# View Service selector and port configuration
kubectl describe svc orders -n production

# Test DNS resolution from a Pod with appropriate tools
kubectl exec -n production <debug-pod> -- \
  nslookup orders.production.svc.cluster.local

# Call the Service from inside the cluster
kubectl exec -n production <debug-pod> -- \
  curl -v http://orders:80/health
```

If there are no EndpointSlices or the endpoint list is empty, check the Service selector, Pod labels, and readiness probes. If DNS resolves but connections time out, inspect application ports, NetworkPolicies, routes, and firewalls. If the internal Service works but external users cannot reach it, inspect the Ingress/Gateway, load balancer address, listeners, certificates, and cloud-level network rules.

### Checking on Cloud Platforms

For managed container services, check both platform configuration and application configuration:

1. Are tasks, replicas, or Pods in a running and healthy state?
2. Do container ports, service ports, and target group ports match?
3. Does the health check use the right protocol, port, and path; does the app return a success code within the timeout?
4. Do security groups/firewalls permit the required source, destination, and ports?
5. Do subnets and route tables have a valid route to the destination; does DNS resolve the name within the right network scope?
6. Do application, ingress, and load balancer logs show connection refused errors, timeouts, or missing endpoints?

Load balancer health checks and application readiness checks serve related but distinct purposes. Readiness determines whether an instance should receive traffic; liveness typically detects deadlocked processes so the platform can restart them. Load balancer health checks decide whether a target receives traffic from the load balancer. Misalignment can pull healthy instances out of rotation or route requests to unready instances.

## 7. Common Failures and Remediation

| Symptom | Possible Cause | How to Verify or Fix |
|---|---|---|
| Connection refused immediately | Application not running, wrong port, or bound only to `127.0.0.1` | Inspect logs and listening sockets; bind to `0.0.0.0` when accepting connections over the container interface |
| Connection timed out | Firewall, NetworkPolicy, route, or security group blocking traffic | Check source/destination, protocol, ports, and routes at each layer |
| Works by IP but fails by name | DNS or service discovery out of scope | Verify hostname, namespace, DNS resolver, and registry |
| Service exists with no endpoints | Selector does not match labels or Pods are not Ready | Compare selector with labels; check readiness probes and EndpointSlices |
| Accessible from host but not from other containers | Client using wrong hostname/port or containers on different networks | Verify shared network and connect using service name plus container port |
| Containers reach each other but Internet cannot access | Port not published or load balancer/Ingress unconfigured | Check public entry points, listeners, DNS, and firewalls |
| New deploy causes some request failures | Stale endpoint cached, rollout or health checks out of sync | Check readiness, drain duration, DNS TTL, retries, and client reconnection handling |

Retries must never be unbounded. For transient errors, apply explicit timeouts, capped retry counts, and exponential backoff with jitter; for non-idempotent operations, implement safeguards to prevent unintended duplicate execution. These practices keep service discovery and load balancing resilient when endpoints change or a node fails.

## 8. Operational and Cost Trade-Offs

- **Direct port publishing:** simple for test environments or a single small service, but requires managing host ports, firewalls, and port collisions. Avoid publishing every port on every container.
- **Host network/hostPort:** can remove a forwarding hop, but weakens isolation and couples workloads to node ports. This can restrict scheduling and scaling flexibility.
- **Internal services:** keep backends on private networks and shrink the attack surface. Requires managing DNS, policies, and east-west traffic observability.
- **Load balancers:** deliver stable entry points, health checks, and traffic distribution. In return, they incur hourly, rule-count, or data-processing fees; many separate load balancers also multiply configurations to manage.
- **Shared Ingress/Gateway:** consolidates many routes and certificates into one entry point, potentially saving resources. Requires designing redundancy, resource limits, route-change permissions, and blast-radius controls if the controller fails.
- **Service registry/DNS:** eliminates reliance on static IPs. Requires accounting for caching, TTLs, endpoint propagation delay, and resilience of the DNS/registry component.
- **Network segmentation:** restricts which services can call which, limiting blast radius if a workload is compromised. Overly strict or untested policies can break legitimate traffic flows.

In multi-service systems, standardize service naming, ports, protocols, health endpoints, and access rules. Track metrics such as connection error rates, latency, open connection counts, endpoint health, and DNS resolution failures. During incidents, these signals separate application bugs from network or discovery failures.

## 9. Hands-On Exercise

Deploy an API and a database with Docker Compose, then simulate recreating the database:

1. Place the API and database on the same private network; publish only the API port.
2. Configure the API to connect to the database via hostname `db` and port `5432`.
3. Verify the API resolves `db`, connects successfully, and `/health` returns the expected response.
4. Recreate the database container, observe that its IP may change, and confirm the API still connects via the service name.
5. Temporarily alter the database port or service name to induce a failure; use the logs and diagnostic commands above to pinpoint the cause.
6. Restore the configuration, verify connectivity, and confirm the database port is not published to the host.

If you have a Kubernetes cluster, go further: create a `ClusterIP` Service for a Deployment, call the Service using in-cluster DNS, scale replicas up, and watch EndpointSlices update. Try changing a Pod's label to observe the Service losing its endpoint, then restore the label and verify traffic resumes.

## 10. Pre-Cloud Deployment Checklist

- [ ] Application listens on the correct protocol and port, bound to the appropriate interface.
- [ ] Clear distinction maintained between container port, Service port, host port, and load balancer port.
- [ ] Only required entry points are exposed; backends and databases remain on private networks.
- [ ] Services communicate via stable names rather than static container IPs.
- [ ] DNS/service discovery operates within the right namespace or network scope.
- [ ] Selectors, endpoints, and readiness health checks match application configuration.
- [ ] Security groups, firewalls, NetworkPolicies, and routes allow only required traffic.
- [ ] Connectivity tested from both internal clients and external entry points along real network paths.
- [ ] Application implements timeouts, bounded retries, and graceful handling of endpoint changes.
- [ ] Evaluated load balancer costs, network transfer charges, and operational complexity.

Sound container networking ensures services keep stable access endpoints even as containers and IP addresses churn. Designing ports, discovery, health checks, and network boundaries properly lets operators release new versions, scale replicas, and handle node failures with minimal manual intervention while keeping traffic within intended bounds.
