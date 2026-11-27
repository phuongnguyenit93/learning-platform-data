# Designing a Multi-Tier Web Service on Virtual Machine Groups

A production web service typically consists of multiple tiers with distinct responsibilities: the traffic ingestion tier, the web tier, the business logic tier, and the data tier. Deploying everything on a single virtual machine may work for small experiments, but it creates a single point of failure, makes scaling individual components difficult, and blurs security boundaries. A multi-tier design on virtual machine groups allows each tier to be scaled, updated, monitored, and protected according to its own requirements.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, this lesson explains how to design a multi-tier web service running on virtual machine groups (VM groups/instance groups). The content progresses from load and availability requirements to network segmentation, load balancers, multi-Availability Zone VM groups, the data tier, autoscaling, security, deployment, observability, and cost optimization. The running example throughout is an order-processing application with a web frontend, a business logic API, a cache, and a database.

## Learning Objectives

After this lesson, you will be able to:

- Explain the roles of the edge, web tier, application tier, and data tier.
- Diagram request flows and administrative flows between tiers.
- Choose how to lay out subnets, routes, security groups/firewalls, and private access.
- Design VM groups with a consistent template distributed across multiple Availability Zones.
- Configure load balancers, health checks, session handling, and graceful draining.
- Estimate VM counts based on throughput, concurrency, headroom, and target utilization.
- Combine horizontal autoscaling with vertical sizing and capacity planning.
- Decouple session state, files, and data from VMs to support safe instance replacement.
- Design availability, backups, failover, and disaster recovery.
- Apply hardening, IAM, secrets management, TLS, patching, and least privilege.
- Build a rolling/blue-green deployment workflow and monitor service quality.
- Evaluate costs by tier and identify sources of waste.

## 1. Why Design a Web Service into Multiple Tiers?

A web service usually has at least three groups of responsibilities:

1. **Web/entry tier:** accepts connections from users, terminates TLS or forwards requests, serves static content, and routes requests.
2. **Application tier:** authenticates, executes business logic, validates data, and coordinates with other services.
3. **Data tier:** stores persistent data, caches, files/objects, and messages for asynchronous processing.

An edge tier consisting of DNS, CDN, WAF, and a public load balancer can be added. The edge protects and distributes traffic before requests reach the VMs.

### 1.1. Benefits of Tiering

- **Independent scaling:** the web tier may need many VMs due to high connection counts, while the application tier needs more CPU or memory.
- **Reduced blast radius:** a failure in one web VM does not necessarily take down the entire application if the load balancer still has healthy backends.
- **Layered security:** only the necessary tier is permitted to communicate with the next tier; the database does not need to accept direct connections from the Internet.
- **Flexible deployment:** the application tier can be updated via rolling or blue-green deployments without modifying the entire system.
- **Clearer observability:** per-tier metrics help pinpoint whether a bottleneck is in the network, web, application, or database layer.
- **Cost management:** select VM types suited to each tier's characteristics and scale only the part that lacks capacity.

### 1.2. Cost and Complexity

Multiple tiers introduce additional load balancers, subnets, firewall rules, VM groups, endpoints, and deployment pipelines. At low load, an architecture with too many components can be expensive and difficult to operate. The number of tiers should reflect real boundaries of scaling, security, ownership, and failure domains.

Not every application must have a separate VM group for each tier. A web tier and application tier can share a VM group in early stages if their load, access permissions, and deployment lifecycle are similar; when scaling or isolation is needed, they can be separated.

## 2. Reference Architecture

The example below uses an order-processing service. Users access it via DNS and HTTPS. A WAF filters common malicious requests, and a public load balancer distributes traffic to a web VM group. The web tier forwards API requests to an application VM group in private subnets. The application tier accesses the cache and database over a private network.

~~~mermaid
flowchart TB
    U[Browser / Mobile Client] --> DNS[DNS]
    DNS --> EDGE[CDN / WAF]
    EDGE --> LB[Public Load Balancer]
    subgraph VPC["Virtual Network / VPC"]
      subgraph PUB["Public subnets - AZ A and AZ B"]
        LB
        NAT[NAT / Egress Gateway]
      end
      subgraph WEB["Private web subnets - multiple AZs"]
        W1[Web VM A]
        W2[Web VM B]
      end
      subgraph APP["Private application subnets - multiple AZs"]
        A1[API VM A]
        A2[API VM B]
      end
      subgraph DATA["Isolated data subnets"]
        CACHE[(Cache)]
        DB[(Primary Database)]
        REPL[(Standby / Read Replica)]
      end
      LB --> W1
      LB --> W2
      W1 --> A1
      W1 --> A2
      W2 --> A1
      W2 --> A2
      A1 --> CACHE
      A2 --> CACHE
      A1 --> DB
      A2 --> DB
      DB --> REPL
      W1 --> NAT
      W2 --> NAT
      A1 --> NAT
      A2 --> NAT
    end
    OPS[Admin via VPN / Bastion / Session Manager] -.-> W1
    OPS -.-> A1
~~~

The diagram is a logical model. In a real implementation, the load balancer can be a managed service; the cache/database can be managed services or dedicated VM clusters. You do not necessarily have to self-operate every component.

### 2.1. Role of Each Tier

| Tier | Components | Responsibilities | Should Not Handle |
|---|---|---|---|
| Edge | DNS, CDN, WAF | Distribution, request filtering, TLS policy, and caching appropriate content | Storing primary transaction state |
| Entry/web | Public load balancer, web VM group | Receiving traffic, reverse proxying, static assets, routing | Accessing the database directly unless necessary |
| Application | API/service VM group | Business logic, authorization, validation, integration | Storing sessions/files only on a single VM's local disk |
| Data | Database, cache, object storage, queue | Storage, querying, buffering, and data exchange | Accepting uncontrolled public connections |
| Operations | Monitoring, logging, deployment, admin access | Administration, observability, patching, and recovery | Sharing broad admin permissions with runtime workloads |

### 2.2. Trust Boundaries

Each tier is a distinct trust boundary. Requests from the Internet must not be treated as trusted merely because they passed through the WAF. The web tier must verify requests and only call permitted application endpoints. The application tier enforces business authorization and uses only the credentials required to access the data tier.

Do not rely on placing VMs in private subnets as the sole security measure. You must combine route tables, firewalls/security groups, IAM, TLS, host hardening, patching, and identity controls.

## 3. Network Design and Subnet Segmentation

The network determines which tier can communicate with whom, over which ports, and in which direction. Clear segmentation reduces the attack surface and aids incident investigation.

### 3.1. Public and Private Subnets

- **Public subnet:** has a route to an Internet Gateway or equivalent public ingress mechanism. Typically hosts public load balancers, NAT gateways, or edge components requiring public reachability.
- **Private subnet:** VMs have no public IP and do not receive direct connections from the Internet. Outbound access requires NAT, an egress gateway, or a private endpoint.
- **Isolated data subnet:** has no direct Internet path; permits traffic only from the application tier and designated administrative/backup systems.

Whether a subnet is public or private depends on its routes and gateways, not merely on whether VMs have public IPs. Inspect the actual route tables to verify traffic paths.

### 3.2. Availability Zone Distribution

Create subnets for each tier in at least two Availability Zones when availability requirements demand surviving a single-zone failure. Place the web VM group and application VM group across multiple zones; the load balancer must have backends in those zones. The data tier needs an appropriate replication/failover topology.

Avoid placing all VMs, NATs, endpoints, or primary databases in the same zone and calling the architecture multi-AZ. Shared dependencies can become single points of failure.

### 3.3. Network Flow Matrix

| Source | Destination | Illustrative Port/Protocol | Purpose |
|---|---|---|---|
| Internet | WAF / public LB | TCP 443 | HTTPS from clients |
| Public LB | Web VM group | TCP 8080 or 443 | Health checks and request forwarding |
| Web VM group | Application VM group | TCP 8443 | Internal API over TLS |
| Application VM group | Database | TCP 5432 or actual DB port | Queries and transactions |
| Application VM group | Cache | TCP 6379 or actual cache port | Cache/session/data lookup |
| Application VM group | Queue/object endpoint | HTTPS 443 | Event publishing and object access |
| Admin network | Bastion/session endpoint | Controlled admin port | Operational access |
| VM | Monitoring/log endpoint | HTTPS 443 or private agent path | Sending metrics/logs |

The ports in the table are examples only. Open only truly necessary ports; use source security groups/identities or narrow subnet CIDRs instead of opening to all addresses.

### 3.4. Egress and Private Endpoints

Private VMs may need to download packages, send logs, or call cloud services. Prefer private endpoints/service endpoints when available to reduce NAT dependency and keep traffic on the private network. If NAT is needed, distribute it across zones so a single NAT gateway does not become a point of failure or cause unnecessary cross-zone data transfer.

Restrict outbound traffic by domain/service/port if the platform supports it. Do not grant unrestricted Internet outbound access to the application tier if the workload only needs to call a few specific APIs.

## 4. Designing Virtual Machine Groups for Each Tier

A VM group (instance group, virtual machine scale set, or autoscaling group depending on the platform) manages multiple machines with similar configurations and lifecycles. Instead of manually modifying individual VMs, create VMs from a tested image/template and let the group manage the instance count.

### 4.1. VM Template/Image

A template should define:

- A hardened and patched OS image.
- CPU, memory, disk type/size, and network interfaces.
- Runtime, monitoring/logging agents, and platform packages.
- An idempotent startup/bootstrap script that can be re-run safely.
- A minimal service identity/instance role.
- Labels/tags for environment, owner, service, tier, and cost center.
- Health check, shutdown behavior, and log configuration.

Do not embed secrets, private keys, database passwords, or long-lived access tokens in images/user-data. Retrieve secrets at runtime via a secret manager using the VM's identity.

### 4.2. Immutable Infrastructure

When OS or application runtime changes are needed, build a new image/template and deploy new instances. This keeps VMs in the group uniform, simplifies rollbacks, and reduces configuration drift.

Avoid making different manual configuration changes on individual VMs. If a temporary change is needed for investigation, document it and fold the validated change into the image or automation afterward.

### 4.3. Grouping by Responsibility

Separate the web VM group and application VM group when they have at least one significant difference:

- Different CPU/memory profiles.
- Need to scale on different metrics.
- Different network/security requirements.
- Different release cycles and ownership.
- Different failure domains or priority levels.

Do not split groups merely to create more administrative components. Each group needs clear capacity targets, health checks, scaling policies, and an owner.

### 4.4. Pets vs. Cattle

VMs in an autoscaling group should be treated as replaceable instances. Persistent data should not exist solely on a single instance's local disk. If a VM fails, the group can create a new VM from the template and the load balancer routes traffic only to healthy instances.

If a workload genuinely requires local state, define how replication, backup, fencing, and recovery work before allowing the autoscaler to delete or replace VMs.

## 5. Load Balancers and Traffic Distribution

A load balancer receives client requests and routes them to appropriate backends. It distributes load, removes unhealthy backends from the pool, and provides a stable endpoint in front of VMs that may change.

### 5.1. Layer 4 and Layer 7

- **Layer 4 load balancing:** routes by IP/port/protocol; suitable for TCP/UDP with minimal inspection of application payloads.
- **Layer 7 load balancing:** understands HTTP/HTTPS, host, path, and headers, and can support rule-based routing, TLS termination, redirects, or WAF integration.

Choose the type based on protocol, routing requirements, TLS, WebSocket/gRPC, and observability. A system can use an edge L7 load balancer followed by internal L4/L7 load balancers between tiers.

### 5.2. Health Checks

Health checks determine whether a backend can receive traffic. Distinguish between:

- **Liveness:** the process is alive and not stuck in an unrecoverable state.
- **Readiness:** the instance has sufficient dependencies/configuration to serve requests.
- **Startup:** whether the application has completed initial initialization.

Health endpoints should be lightweight, have short timeouts, and avoid putting heavy load on the database. If readiness depends on every external dependency, a secondary failure can remove all backends from the pool. Identify which dependencies are strictly required to serve requests.

### 5.3. Distribution Algorithms

- Round robin works well when backends have similar capacity and request durations are relatively uniform.
- Least connections is useful when requests hold connections open for a long time and connection count reflects load.
- Weighted distribution allows instances with different capacities to receive different proportions of traffic.
- Consistent hashing can help with affinity/cache locality, but skew and rebalancing must be considered.

Algorithms do not replace autoscaling. Monitor request rate, active connections, backend latency, and errors to detect load imbalance.

### 5.4. Session Affinity and Sticky Sessions

Sticky sessions keep a client bound to one backend for a period of time. This can help legacy applications that store sessions in memory, but introduces risks:

- One VM receives too many sessions and becomes overloaded.
- Replacing a VM loses sessions.
- Scale-in is hard to drain because many clients retain affinity.
- Failover may force clients to log in again.

Prefer storing sessions in a shared cache or persistent store, or using signed stateless tokens. If sticky sessions are unavoidable, define TTLs, behavior when a backend fails, and drain time limits.

### 5.5. Connection Draining

When a VM needs to be updated or scaled in, the load balancer stops sending new requests to that backend, waits for in-flight requests to complete during the drain period, and only then terminates the VM. The application must handle SIGTERM/shutdown signals, close connections, and safely finish or reject in-progress work.

## 6. Designing the Web Tier and Application Tier

### 6.1. Web Tier

Web VMs typically run a reverse proxy/web server such as Nginx, Apache, or an appropriate web runtime. Common responsibilities include:

- Serving static assets or offloading static assets to a CDN/object storage.
- Terminating TLS if the architecture places TLS termination at the web tier.
- Forwarding requests to internal application endpoints.
- Configuring request size limits, timeouts, connection limits, and header policies.
- Writing access logs, correlation IDs, and basic metrics.

The web tier should be stateless. If a VM is replaced, the next request can be served by another VM without losing business data.

### 6.2. Application Tier

Application VMs run APIs or services that execute business logic:

- Authenticating users and authorizing per resource/action.
- Validating inputs, enforcing business rules, and managing transactions.
- Accessing databases/caches through connection pools.
- Publishing events for background work.
- Returning responses with consistent error codes and correlation IDs.

Do not trust client-supplied headers such as user identity or role unless they have been verified and securely signed/forwarded by the gateway/authentication layer.

### 6.3. Separating Configuration by Environment

Images can be identical across dev/staging/production; environment-specific configuration is injected via a parameter/config service or deployment system. Manage endpoints, feature flags, and secrets separately per environment. Never share a single database credential or signing key across all environments.

## 7. Designing the Data Tier and State Management

Stateless VMs can be created and deleted quickly. Data that must persist beyond a VM's lifecycle must reside in storage/services with durable semantics.

### 7.1. Database

Databases store business data and require planning for:

- Transaction isolation and consistency.
- Connection limits/pooling.
- Backups, point-in-time recovery, and restore testing.
- Replication, failover, and read replicas.
- Schema migrations compatible with application versions.
- Encryption at rest/in transit and auditing.

Even when using a managed database, you still must design the schema, indexes, queries, backup policies, and connection management. Managed does not automatically mean all RPO/RTO targets are met.

If self-operating a database on VMs, you must also handle clustering/quorum, disk durability, replication, fencing, backups, patching, failover automation, and on-call operational expertise. This is a stateful workload distinct from web/application VM groups.

### 7.2. Cache

Caches reduce latency and database load for data that is regenerable or has a clear invalidation policy. Define:

- TTL and invalidation strategy.
- Cache-aside, read-through, or write-through patterns.
- Behavior when the cache is unavailable.
- Stampede protection and request coalescing.
- Key design, eviction policies, and memory sizing.
- Which data must not be cached due to sensitivity or freshness requirements.

A cache should not be the sole source of truth for critical transactions unless the caching service is specifically designed and operated as durable storage.

### 7.3. File and Object Storage

Do not store uploaded files or generated reports solely on a web VM's local disk if users may be routed to other VMs. Use object storage/shared file services, metadata in the database, and time-limited URLs when access is needed.

If the application needs local scratch space, treat it as ephemeral, enforce size limits, and clean it up after processing. Do not let a full scratch disk render a VM unable to serve requests.

### 7.4. Queues and Background Workers

Tasks such as sending emails, generating reports, processing images, or slow integrations can be placed in a queue to decouple them from the request path. Worker groups can scale independently based on queue depth/oldest message age. Design idempotency, retries, dead-letter queues, and backpressure so redelivered messages do not cause duplicate side effects.

## 8. Capacity Planning for VM Groups

Capacity planning starts from business load, not from picking a VM type and hoping it is enough. Measure the safe throughput of a single instance at target latency and error rates, then calculate instance counts and headroom.

### 8.1. Calculating Instance Count by Throughput

Given:

- λ: required arrival rate (requests/second).
- μ: safe throughput of one VM (requests/second).
- U: target utilization, less than 1 to preserve headroom.

Minimum number of VMs based on throughput:

\[
N=\left\lceil\frac{\lambda}{\mu\times U}\right\rceil
\]

For example, an API requires 1,200 requests/second. Load testing shows one application VM stably handles 100 requests/second at target latency. Choose a target utilization of 70%:

~~~text
N = ceil(1,200 / (100 × 0.70))
  = ceil(17.14)
  = 18 VMs
~~~

This is the capacity when all VMs are healthy. If the requirement is to survive the loss of one zone or a portion of instances, add extra capacity so sufficient throughput remains after failure.

### 8.2. Calculating Capacity on Loss of One Zone

Suppose 18 VMs are evenly distributed across 3 zones, with 6 VMs per zone. Losing one zone leaves 12 VMs. If the service still needs to handle 1,200 requests/second at 70% utilization:

~~~text
Remaining capacity = 12 × 100 × 0.70
                   = 840 requests/second
~~~

840 is lower than 1,200; the architecture does not yet have N-1 capacity. You can increase baseline VM count, increase per-VM throughput after benchmarking, reduce load via caching/queues, or accept a bounded degraded mode. Never check VM count only under healthy conditions.

### 8.3. CPU and Memory

Monitor CPU usage, run queue, memory working set, swap, disk IOPS/latency, network throughput, and application concurrency. Low CPU does not mean a VM has spare capacity if database pools, thread pools, or the network are saturated.

Memory needs headroom for the runtime, caches, request bursts, and rolling deployments. If a VM begins swapping heavily or hitting OOM, latency can spike before health checks fail.

### 8.4. Vertical and Horizontal Scaling

- **Vertical scaling:** changing a VM to a shape with more CPU/memory. Simple for applications that do not scale out well, but hits hardware ceilings and usually requires restarts/migrations.
- **Horizontal scaling:** adding VMs to a group. Increases capacity and availability, but requires statelessness, load balancing, and shared data.

In practice, both are commonly combined: choose a reasonable instance size first, then scale horizontally within tested min/max bounds.

### 8.5. Autoscaling Policies

Scale on metrics that reflect the actual bottleneck:

- CPU utilization for CPU-bound workloads.
- Request count per target or active connections for the web tier.
- Queue depth/oldest message age for workers.
- Custom metrics such as in-flight requests or thread pool saturation for the application tier.

Do not rely solely on CPU if requests can block waiting on the database while CPU remains low. Likewise, do not scale on a noisy metric without cooldown, stabilization, or min/max guardrails.

## 9. Designing Autoscaling Groups

A VM group needs consistent configuration and clear scale-up/scale-down behavior.

### 9.1. Min, Desired, and Max

- **Min:** the number of VMs always kept running to serve baseline load and maintain availability.
- **Desired:** the target number of VMs the group aims to maintain at the current time.
- **Max:** the scaling ceiling based on quotas, budget, and downstream capacity.

Min should not be 1 for production services requiring HA. Max should not exceed the database's load capacity or cloud quotas.

### 9.2. Scale-out

When load increases:

1. The metric exceeds the threshold for a defined duration.
2. The autoscaling policy increases desired capacity.
3. New VMs are created from the image/template.
4. Bootstrap, agents, and application services start up.
5. Instances register with the target group.
6. Health checks pass and the load balancer begins sending traffic.

Measure the time from trigger to when an instance receives requests. If booting takes several minutes, maintain headroom or use scheduled scaling ahead of predictable traffic spikes.

### 9.3. Scale-in

Scale-in must protect in-flight requests, sessions, and jobs:

1. Select instances eligible for removal according to policy.
2. Mark instances as draining and stop sending new traffic.
3. Wait for in-flight connections/requests to complete within the grace period.
4. The application stops accepting new jobs and finishes/releases work leases.
5. Flush logs/metrics and close connections.
6. Terminate the instance.

Do not scale in too aggressively when traffic is cyclical. Use cooldown/stabilization windows and verify immediately after scale-in that the group still has sufficient capacity.

### 9.4. Warm Pools and Scheduled Scaling

Warm pools keep booted or nearly ready VMs on standby to reduce scale-out latency. Scheduled scaling raises desired capacity ahead of recurring traffic peaks. Both increase idle costs; weigh them against SLOs and p95 startup time.

## 10. Availability and Eliminating Single Points of Failure

High availability requires multiple components working together: load balancers, VM groups, networking, databases, DNS, identity, and observability. Running multiple VMs in a single zone is insufficient if that zone or its network fails.

### 10.1. Multi-Zone

- The load balancer distributes traffic across backends in multiple zones.
- Web and application VM groups spread instances across zones.
- Subnet/IP capacity is sufficient for scale-out in every zone.
- The database has standby/replicas and failover aligned with targets.
- NAT/egress and private endpoints do not create a single point of failure.
- Deployments do not update all zones simultaneously.

### 10.2. Health Checks and Failover

Load balancers remove unhealthy backends from the pool. Autoscaling groups can replace instances that fail health checks. However, process failures must be distinguished from shared dependency failures: if the database goes down, all application VMs could fail readiness simultaneously. Design health checks so a secondary dependency outage does not cascade into removing every backend.

### 10.3. Availability Is More Than VM Count

Evaluate availability in terms of successful requests and recovery capability. A service with 10 VMs all relying on a single non-HA database can still go down when the database fails.

Define:

- RTO: maximum acceptable time to restore the service.
- RPO: maximum acceptable data loss measured in time.
- Failure domains: VM, rack/host, zone, region, network, or dependency.
- Degraded mode: which features can be temporarily disabled to preserve critical flows.
- Runbook: who decides on failover, how data is verified, and how failback works.

### 10.4. Disaster Recovery

Multi-zone typically handles failures within a single region; cross-region disaster recovery is a separate problem. You can choose backup/restore, pilot light, warm standby, or active-active depending on RTO/RPO and cost.

Backups are only valuable once restores have been tested. Rehearse database restores, application deployments, DNS/traffic switching, secrets/identities, and dependency connectivity.

## 11. Layered Security Across Tiers

Security design requires multiple layers: network segmentation, identity, host hardening, application security, encryption, and auditing.

### 11.1. Network Security

- Only the public load balancer accepts inbound traffic from the Internet.
- Web VMs accept inbound traffic only from the load balancer.
- Application VMs accept API traffic only from the web tier or trusted internal callers.
- The database accepts connections only from the application tier and authorized management systems.
- Admin access goes through VPN, bastion, or session manager; avoid exposing SSH/RDP directly to the Internet.
- Egress is opened only for required dependencies.

### 11.2. Identity and Permissions

Each VM/service uses a dedicated identity with least privilege. The web tier does not need database read permissions if it only proxies requests. The application tier is allowed to read/write only the specific secrets, buckets, queues, and database resources it needs.

Separate deploy, runtime, operator, and auditor permissions. Do not use a shared static access key across VMs. Prefer managed identities/instance roles and short-lived credentials.

### 11.3. TLS and Data Protection

- Use HTTPS from clients to the edge.
- Consider TLS/mTLS between tiers when required by security posture and threat models.
- Encrypt disks, database snapshots, objects, and backups.
- Manage certificate rotation and trust chains.
- Do not log tokens, passwords, session cookies, or unnecessary personal data.

### 11.4. Host Hardening and Patching

- Disable unused services and ports.
- Apply OS baselines and security patches.
- Deploy endpoint protection/EDR agents per policy.
- Restrict sudo/admin privileges.
- Synchronize time and collect audit logs.
- Scan images/packages and manage vulnerabilities.
- Replace VMs with new images via a rolling process when patching the base platform.

### 11.5. WAF and Application Protection

A WAF helps filter common attack patterns, but it does not replace authentication, authorization, input validation, parameterized queries, CSRF/XSS protection, and secure coding. Monitor false positives so legitimate traffic is not mistakenly blocked.

## 12. Session and Application State Management

When a load balancer distributes requests across multiple VMs, the application must not assume subsequent requests will reach the same VM as before.

### 12.1. Stateless Applications

Design stateless APIs: each request carries the necessary token/context, while persistent data is read from shared stores. This enables:

- Replacing VMs without losing sessions.
- Scaling out/in without migrating local sessions.
- Deploying multiple versions concurrently.
- Distributing requests across multiple zones.

### 12.2. Session Stores

If server-side sessions are needed, use a cache/shared session store or database with TTLs. Define behavior when the session store is unavailable, TTLs, encryption, key rotation, and logout/revocation.

Sticky sessions are only a compatibility workaround in certain cases. They do not replace shared state when HA is required.

### 12.3. Idempotency and Retries

Clients, load balancers, or service meshes may retry requests on timeout. For operations like creating orders, payments, or state updates, use idempotency keys and transactions/outbox patterns to avoid executing side effects twice.

## 13. Application Deployment and Updates

Deploying across multiple VMs requires ensuring version compatibility during the rolling update window.

### 13.1. Rolling Deployment

1. Build a tested artifact/image.
2. Create a new batch of VMs or update partially via the launch template.
3. Wait for startup and readiness checks to pass.
4. Have the load balancer add the new VMs to the pool.
5. Drain old VMs and wait for in-flight requests to finish.
6. Proceed to the next batch.
7. Halt the rollout if errors/latency exceed thresholds.

Limit the number of simultaneously unavailable instances so capacity never drops below requirements.

### 13.2. Blue-Green Deployment

Create a green group alongside the blue group. Validate green with smoke/integration tests, then shift a portion of traffic and ramp up gradually. Keep blue around for as long as rollback may be needed.

Blue-green temporarily requires nearly double capacity in the duplicated tier and requires verifying database/schema compatibility. Rolling back the application does not automatically roll back data written under a new schema.

### 13.3. Database Migrations

Use expand-and-contract:

1. Add new schema elements compatible with the old version.
2. Deploy application code that reads/writes compatibly.
3. Backfill and verify data.
4. Shift traffic/feature flags.
5. Remove the old schema only after a safe period.

Avoid deploying breaking schema migrations at the same time as a rolling update while instances running the old version are still active.

### 13.4. Rollback

A rollback plan must clearly define:

- Which artifact/image/version to revert to.
- Corresponding configuration and secrets.
- Whether the database schema is compatible.
- Which queues/events were emitted under the new contract.
- Whether feature flags must be disabled or traffic shifted.
- Rollback decision criteria and who has authority to decide.

## 14. Observability and Operations

A multi-tier architecture requires per-tier and per-request observability. Combine metrics, logs, traces, and synthetic checks.

### 14.1. Infrastructure Metrics

- VM count by group/zone and health status.
- CPU, memory, and disk utilization/latency/IOPS.
- Network throughput, packet drops, and connection counts.
- Load balancer request count, active connections, target health, and 4xx/5xx errors.
- Autoscaling desired/current capacity and scaling activities.
- Database connections, replication lag, storage, and query latency.
- Cache hit ratio, evictions, and memory pressure.

### 14.2. Application Metrics

- Request rate, success/error rates.
- p50/p95/p99 latency.
- Thread pools, worker queues, and in-flight requests.
- Connection pool waits and timeouts.
- Business metrics such as successful orders, failed payments, and job backlog.
- Dependency call duration and retry counts.

### 14.3. Logs and Traces

Logs should include timestamp, service, environment, instance ID, trace/correlation ID, severity, and outcome. Avoid logging secrets and sensitive payloads. Use centralized logging so logs persist after VMs are terminated.

Distributed tracing connects a request across the edge, web, application, and database/cache tiers. Sampling should be sufficient to investigate tail latency and rare errors without incurring excessive cost.

### 14.4. Alerts and Runbooks

Alerts should tie to service impact:

- Healthy target count falls below threshold.
- p99 latency or error rate breaches SLO.
- Autoscaling fails to launch instances or the group hits max capacity.
- VM memory/disk nears exhaustion.
- Database connections or replication lag exceed thresholds.
- Queue age grows persistently.
- Certificates nearing expiration or patch compliance dropping.

Each alert should have an owner, severity, dashboard, initial triage steps, and escalation criteria.

## 15. Performance and Cost Optimization

### 15.1. Choosing VM Shapes by Tier

| Tier | Load Characteristics | Resource Selection Approach |
|---|---|---|
| Web/reverse proxy | High connections, TLS, network I/O | Balance CPU, memory, and network; benchmark TLS/connections |
| API/application | Logic, serialization, queries, and concurrency | Size CPU/memory based on profiling and request mix |
| Worker | Batch, CPU-bound, or I/O-bound | Choose compute/memory/network by job type; scale by backlog |
| Cache | Memory capacity and network latency | Prioritize memory/network; measure hit ratio and evictions |
| Database | Memory, IOPS, storage durability, and connections | Size by query/working set, storage latency, and HA topology |

Do not choose VMs based solely on vCPU count. Benchmark with representative workloads and account for licenses, disks, network egress, load balancers, NAT, backups, and observability.

### 15.2. Rightsizing

Collect metrics over a sufficiently long load cycle, including peak periods and batch windows. A VM with low average CPU but high p99 latency may be constrained by single-threading, locks, or downstream dependencies. A VM with high memory usage may need it for caching; reducing memory without understanding the working set can trigger paging.

Change one factor at a time and compare throughput, p95/p99 latency, errors, and cost per transaction.

### 15.3. Reducing Cost Without Losing Headroom

- Set autoscaling min/max based on baseline and peak load.
- Use scheduled scaling for predictable workloads.
- Shut down non-production environments outside working hours where appropriate.
- Use appropriate instance families and committed-use discounts/reservations for steady baselines.
- Use Spot/interruptible VMs for workers that support checkpointing/retries, without placing sole critical state on those instances.
- Cache static content and cacheable data to reduce load on the application/database.
- Reduce debug logging and configure reasonable retention and sampling.
- Optimize NAT, cross-zone transfer, and data egress.

Do not scale in solely because CPU is low over a short window if headroom is needed to survive zone failures or traffic bursts.

## 16. Design Decisions to Document

An Architecture Decision Record (ADR) helps teams understand why a configuration was chosen and under what conditions it should be revisited.

Each decision should document:

- Context and requirements: load, SLO, RTO/RPO, compliance, budget.
- Alternatives considered.
- Chosen option and rationale.
- Trade-offs: cost, complexity, latency, availability, and lock-in.
- Assumptions that must be validated through testing.
- Metrics/thresholds that trigger revisiting the decision.

For example: choose two application VM groups across two zones, minimum 2 instances per zone, scaling on request count and CPU; revisit the decision if p95 startup exceeds 3 minutes or database connections become the bottleneck.

## 17. End-to-End Design Process from Requirements to Deployment

1. **Gather requirements:** baseline/peak traffic, request mix, SLOs, security, RTO/RPO, and budget.
2. **Diagram request flows:** client → edge → load balancer → web → application → data/dependencies.
3. **Identify failure domains:** VM, zone, region, network, and managed services.
4. **Design subnets and firewalls:** open only necessary flows between each tier.
5. **Select VM profiles:** benchmark CPU, memory, disk, and network per tier.
6. **Build images/templates:** hardening, agents, bootstrap, and identity.
7. **Create multi-zone VM groups:** min/desired/max capacity and health checks.
8. **Configure load balancing:** routing, TLS, health checks, and connection draining.
9. **Decouple state:** database, cache, sessions, object storage, and queues.
10. **Design scaling:** metrics, thresholds, cooldowns, headroom, and downstream max capacity.
11. **Design deployment:** rolling/blue-green, schema compatibility, and rollback.
12. **Set up observability:** dashboards, alerts, traces, and runbooks.
13. **Test:** load, spike, failover, zone loss, backup restore, and security validation.
14. **Review costs:** VM hours, storage, networking, managed services, logging, and idle capacity.

## 18. Practical Example: Three-Tier Order-Processing Service

An order-processing system has the following components:

- Web frontend serving pages and forwarding API requests.
- Application API validating carts, inventory, and creating orders.
- Database storing orders and inventory.
- Cache holding catalog and read-heavy data.
- Queue handling emails/notifications and updating reports.

### 18.1. Order Creation Request Flow

1. Client calls HTTPS on the application domain.
2. DNS points to CDN/WAF and the public load balancer.
3. The load balancer selects a healthy web VM.
4. The web tier forwards the request to the internal application endpoint.
5. The application authenticates the token, checks the idempotency key, and validates the payload.
6. The application reads the cache/catalog and executes a database transaction.
7. The application writes an outbox/event or publishes an event post-commit using a consistency-preserving mechanism.
8. Response returns the order ID.
9. Workers read events from the queue and send notifications.

### 18.2. VM Distribution

| Group | AZ A | AZ B | Scaling Signal |
|---|---:|---:|---|
| Web VM | 2 | 2 | Requests/target, active connections |
| Application VM | 3 | 3 | CPU, request rate, in-flight requests |
| Worker VM | 1 | 1 | Queue depth, oldest message age |

These numbers are illustrative only. Benchmark and verify capacity under single-zone loss. The database and cache are deployed with an appropriate HA topology; do not assume the replica count in the table guarantees database HA.

### 18.3. Handling an Application VM Failure

- Health checks detect the unresponsive VM.
- The load balancer stops sending new requests to that VM.
- The autoscaling group replaces the instance from the standard image.
- In-flight requests are retried per client policy; order creation uses an idempotency key.
- The new VM fetches config/secrets using its instance identity and registers with the target group after readiness passes.
- Dashboards track healthy target count, replacement time, and error rate.

### 18.4. Handling a Slow Database

- Application connection pools are bounded.
- Query timeouts and request deadlines prevent threads from blocking indefinitely.
- Caching offloads part of the read load, though it must never be used to simulate committed writes.
- Rate limiting/backpressure reduces load hitting the database.
- Queues hold tasks that can be processed asynchronously.
- Alerts fire on connection wait times, query latency, locks, and replication lag.

## 19. Logical Configuration Example

The following example describes a conceptual security group/firewall policy. Actual syntax depends on the cloud provider.

~~~yaml
networkPolicy:
  publicLoadBalancer:
    inbound:
      - source: internet
        protocol: TCP
        port: 443
    outbound:
      - destination: web-tier
        protocol: TCP
        port: 8080

  webTier:
    inbound:
      - source: public-load-balancer
        protocol: TCP
        port: 8080
    outbound:
      - destination: application-tier
        protocol: TCP
        port: 8443
      - destination: monitoring-endpoint
        protocol: TCP
        port: 443

  applicationTier:
    inbound:
      - source: web-tier
        protocol: TCP
        port: 8443
    outbound:
      - destination: database
        protocol: TCP
        port: 5432
      - destination: cache
        protocol: TCP
        port: 6379
      - destination: queue-and-secret-endpoints
        protocol: TCP
        port: 443

  dataTier:
    inbound:
      - source: application-tier
        protocol: TCP
        ports: [5432, 6379]
~~~

This illustrates source/destination relationships, not a directly applicable manifest. You must add DNS, health checks, backups, patching, admin access, and specific egress rules. With stateful firewalls, response traffic is generally allowed via connection tracking; with stateless ACLs, corresponding ephemeral port rules are required.

## 20. Pre-Production Architecture Testing

### 20.1. Functional and Integration Tests

- Requests flow properly from the load balancer through web to application.
- The application accesses only authorized dependencies.
- Sessions do not depend on a single VM's local memory.
- Files/objects remain accessible when requests are served by another VM.
- Retries do not create duplicate transactions.
- Health checks distinguish startup, readiness, and liveness.

### 20.2. Load and Performance Tests

- Ramp from baseline to peak and hold steady-state.
- Run spike tests to measure autoscaling delay.
- Monitor p50/p95/p99 latency per tier.
- Increase concurrency until the first bottleneck is identified.
- Test database connection limits and cache misses.
- Verify the load generator itself is not the bottleneck.

### 20.3. Resilience Tests

- Terminate a web VM while traffic is active.
- Terminate an application VM and verify in-flight request handling.
- Simulate a single-zone outage in a test environment.
- Trigger database failover and verify reconnection.
- Make the cache unavailable and verify fallback behavior.
- Drain nodes/VMs during a rolling deployment.
- Restore from backup and measure actual RTO/RPO.

### 20.4. Security Validation

- Scan public IPs/ports to verify only the edge is publicly exposed.
- Verify the web tier cannot reach the database directly.
- Verify the application tier lacks broad admin permissions.
- Validate certificates, TLS, and secret rotation.
- Check OS patches, image vulnerabilities, and audit trails.
- Test revoking an identity/credential and verify safe behavior.

## 21. Common Mistakes

| Mistake | Consequence | Remediation |
|---|---|---|
| Running all tiers on one VM long-term | Single point of failure; difficult to scale and patch | Separate tiers by responsibility and requirements |
| Giving application VMs public IPs | Expanded attack surface | Place in private subnets; accept internal traffic only |
| Exposing the database to the Internet | Risk of unauthorized access | Isolated subnets and firewalls by source identity |
| Storing sessions/files on local disk | State loss when VMs are replaced | Shared session store/object storage |
| Relying on sticky sessions for HA | VM failure can lose sessions | Stateless/tokens/shared sessions |
| Running in a single zone | Zone outage takes down the entire service | Multi-zone deployment and zone-failure testing |
| Scaling web tier on CPU when DB is the bottleneck | Adding VMs overloads the DB further | Monitor dependencies and bound concurrency |
| Unbounded connection pools | Connection storms during scale-out | Calculate total connections from max VMs/concurrency |
| Overly deep health checks | Dependency failure removes all backends | Design readiness around essential serving capability |
| Terminating without draining | In-flight requests/jobs cut off mid-flight | Graceful shutdown and connection draining |
| Hand-editing individual VMs | Configuration drift | Images/templates and immutable rollouts |
| Rolling update all instances at once | Capacity loss during deployment | Batched rollouts, surge, and availability budgets |
| Backing up without restore testing | Unknown whether backups are usable | Regular restore drills |
| Selecting VMs by nominal vCPU | Ignoring memory/network/IO bottlenecks | Benchmark representative workloads |
| Scaling in too fast | Insufficient cold capacity when load returns | Cooldowns, stabilization, and headroom |

## 22. Production Checklist

**Architecture and Networking**

- [ ] Flow client → edge → web → application → data is documented.
- [ ] Each tier has clear responsibilities, owners, and failure boundaries.
- [ ] Web/application VMs are in appropriate subnets; data tier is non-public.
- [ ] Security rules permit only necessary sources, destinations, and ports.
- [ ] Plans exist for egress, private endpoints, DNS, and IP capacity.
- [ ] Critical tiers are distributed across multiple Availability Zones.

**VM Groups and Scaling**

- [ ] Images/templates are hardened, versioned, and contain no secrets.
- [ ] Min/desired/max capacity is backed by load testing and quotas.
- [ ] Health checks and connection draining have been tested.
- [ ] Autoscaling metrics reflect real bottlenecks.
- [ ] Headroom exists to absorb instance/zone failures and boot time.
- [ ] Scale-in protects in-flight requests, sessions, and jobs.

**Data and State**

- [ ] Sessions do not depend on a single VM's local memory.
- [ ] Persistent files reside in shared/object storage.
- [ ] Databases have backups, restore tests, and failover plans.
- [ ] Connection pools are bounded against max application capacity.
- [ ] Caches have TTLs/invalidation and fallback behavior.
- [ ] Queues have retries, idempotency, DLQs, and backpressure.

**Security and Deployment**

- [ ] TLS is configured for public and appropriate internal paths.
- [ ] Runtime identities follow least privilege.
- [ ] Admin access goes through controlled and audited channels.
- [ ] OS/images are patched and scanned for vulnerabilities.
- [ ] Rolling/blue-green deployments include rollback and schema compatibility.
- [ ] Secret/certificate rotation has been tested.

**Operations**

- [ ] Per-tier metrics, logs, traces, and synthetic checks are in place.
- [ ] Dashboards display healthy targets, capacity, and p95/p99 latency.
- [ ] Alerts have owners, severities, and runbooks.
- [ ] Load, failover, zone-loss, and restore drills are conducted.
- [ ] VM, storage, network, database, and observability costs are tracked.

## 23. Conclusion

Designing a multi-tier web service on virtual machine groups is about establishing clear responsibilities and failure boundaries, then connecting tiers with controlled network rules, load balancing, and identities. The web/application tiers should be replaceable and horizontally scalable; persistent state belongs in appropriate data services; VM groups are built from standard templates and distributed across multiple zones.

An architecture is only proven suitable after testing load, autoscaling, health checks, graceful draining, dependency failures, zone loss, and restores. Capacity planning must factor in headroom and downstream limits; security must apply from edge to database; deployments must support rollback; and observability must link infrastructure metrics to user experience. These decisions help the service meet real-world performance, availability, security, and cost requirements in production.

## Key Terminology

| Term | Meaning |
|---|---|
| Multi-tier architecture | Architecture separating web, application, and data into distinct tiers of responsibility. |
| VM group | A group of virtual machines managed via a shared template and capacity policy. |
| Autoscaling group | Mechanism that automatically adjusts VM count based on metrics or schedules. |
| Availability Zone | A relatively independent failure domain within a region. |
| Load balancer | Component that distributes traffic across healthy backends. |
| Reverse proxy | Component that receives requests and forwards them to application backends. |
| Private subnet | Subnet that does not accept direct inbound Internet traffic per route/security design. |
| Security group/firewall | Rules controlling traffic by source, destination, port, and protocol. |
| Stateless service | Service that does not depend on local state persisting across multiple requests. |
| Connection draining | Stopping new requests and waiting for current requests to finish before removing a backend. |
| Headroom | Reserve capacity for bursts, failovers, and load fluctuations. |
| Horizontal scaling | Increasing/decreasing the number of instances. |
| Vertical scaling | Increasing/decreasing the CPU, memory, or configuration of an individual instance. |
| RTO | Maximum target time to restore a service. |
| RPO | Maximum acceptable data loss, measured in time. |
| Immutable infrastructure | Deployment approach replacing instances using new images/templates rather than long-lived manual edits. |
| Blue-green deployment | Maintaining two version groups and shifting traffic between them. |
| Degraded mode | Mode that reduces certain features to preserve critical business flows. |
| Rightsizing | Selecting resources aligned with measured load and operational targets. |
