# Designing a Stateless API with Managed Containers

An API deployed across multiple containers must be able to serve requests from any replica. If login sessions, temporary files, in-progress jobs, or business data exist only in the RAM or local filesystem of a single container, a subsequent request may land on another replica and fail to find the prior state. When a container is replaced, scaled in, or moved to another node, local state can also be lost.

A **stateless API** is an API that does not depend on session state or request state kept solely in a single replica's memory to process subsequent requests. State that needs to persist is stored in external services with independent lifecycles, such as databases, shared caches, object storage, or message queues. Containers become replaceable execution units that can scale with load.

In **CLOUD_CORE_SERVICES_COMPUTE**, managed containers can be workloads running on managed Kubernetes, a container application platform, or a serverless container service. The platform handles scheduling, launching, health checks, service discovery, and scaling; the application team still must design the API, data, security, observability, and request lifecycle so multiple replicas behave consistently.

## 1. What Is a Stateless API?

A stateless API does not require the replica handling a request to remember previous requests in local memory or on local disk. Each request carries sufficient information for authentication, business routing, and processing; shared data is read from independent storage or services.

For example:

- Clients send an access token on every request; every replica verifies the token using the same trust configuration.
- Shopping carts are stored in a database or shared cache; they do not live exclusively in one container's RAM.
- Uploaded files are written to object storage; the API manages only metadata and access permissions.
- Long-running work is pushed to a queue; workers process it independently of the HTTP request lifecycle.
- Idempotency keys are persisted durably so retried requests do not create duplicate transactions.

### 1.1. Stateless Does Not Mean the Application Has No Data

A stateless system still reads and writes business data. The difference is that an API replica does not hold the sole copy of state required for the next request to work.

| State | Where to Store | Reason |
|---|---|---|
| Login session | Signed token or shared session store | Requests can arrive at any replica |
| Profiles and orders | Database | Durable data with transactions and backups |
| Cache | Distributed cache or regenerable cache | Independent of a single container |
| Uploaded files | Object storage or managed persistent storage | Containers can be replaced |
| Pending jobs | Message queue/workflow service | Decouples long processing from HTTP requests |
| Idempotency records | Database or store with atomic operations | Prevents duplicate side effects |
| Request-local data | RAM of the request being processed | Exists only for the duration of the request |

### 1.2. Stateful vs. Stateless Replicas

In a stateful model—meaning local session storage—clients may need to be routed back to the exact same replica. This creates sticky sessions and reduces the ability to replace or scale replicas.

With a stateless API, the load balancer can send requests to any healthy replica. Any replica can be terminated without losing sessions or durably persisted business data.

| Criterion | API Depending on Local State | Stateless API |
|---|---|---|
| Session | Stored in replica RAM/disk | Token or shared store |
| Load balancing | May require sticky sessions | Can distribute to any replica |
| Scale-out | Must handle state synchronization | Add replicas independently |
| Scale-in | Risk of losing sessions or jobs | Replicas can drain and be replaced |
| Recovery | Must restore instance state | Launch new replica and connect to data services |
| Deployment | Difficult to replace state-holding replicas | Smoother rolling updates |

Sticky sessions are sometimes used as a transitional workaround, but they do not replace stateless design. If a replica fails, sessions pinned to that replica may be lost or clients may have to log in again.

## 2. Reference Architecture

A stateless API running on a managed container platform typically consists of these layers:

1. Clients or calling services.
2. DNS, CDN, or WAF as required.
3. Load balancer or ingress/API gateway.
4. Managed container platform and service discovery.
5. Multiple stateless API replicas.
6. Database, cache, object storage, and message queue.
7. Observability, secret management, and identity services.

~~~mermaid
flowchart TD
    C["Client / Service caller"] --> D["DNS / WAF / API Gateway"]
    D --> LB["Load balancer / Ingress"]
    LB --> S["Kubernetes Service / Container endpoint"]
    S --> P1["API replica 1"]
    S --> P2["API replica 2"]
    S --> P3["API replica N"]
    P1 --> DB["Managed database"]
    P2 --> DB
    P3 --> DB
    P1 --> CACHE["Shared cache"]
    P2 --> CACHE
    P3 --> CACHE
    P1 --> OBJ["Object storage"]
    P2 --> Q["Message queue"]
    P3 --> Q
    P1 --> OBS["Logs / metrics / traces"]
    P2 --> OBS
    P3 --> OBS
~~~

The load balancer distributes traffic to healthy endpoints. Service discovery provides a stable address for internal clients. API replicas do not need to know which container handled the previous request.

### 2.1. Request Processing Flow

A request to read an order may go through these steps:

1. The client sends an HTTPS request along with an access token.
2. The gateway checks TLS, rate limits, and edge policies.
3. The load balancer forwards the request to a healthy replica.
4. The replica verifies the token and access permissions.
5. The API reads the order from the database using its workload identity.
6. The API may read from the cache if the data is suitable and cache policy allows.
7. The API returns the response with a request ID and required metadata.
8. Metrics, logs, and traces are sent to the observability system.

All replicas must have compatible configurations and the necessary access permissions. Never rely on global variables or local files created during a prior request.

## 3. Externalize State: Moving State Out of the Container

Stateless design begins by classifying state and choosing the right storage location.

### 3.1. Sessions and Authentication

Common options:

- **Signed tokens:** the client sends a token in every request; the API verifies the signature, issuer, audience, expiry, and claims.
- **Opaque session IDs:** the client sends an ID; the API reads the session from a distributed session store.
- **OAuth/OIDC:** the API verifies access tokens against the identity provider's issuer and key rotation.

Tokens should not contain secrets or frequently changing state. If immediate session revocation is required, short-lived tokens combined with a revocation/session store may be more appropriate than purely self-contained long-lived tokens.

Do not store the sole copy of a session in a pod's local memory. If using a distributed cache as a session store, configure TTLs, replication, access control, and behavior when the cache is unavailable.

### 3.2. Business Data

The database is the authoritative source of truth for business entities. The API should:

- Use transactions aligned with business invariants.
- Set timeouts and connection pool limits.
- Use compatible migrations during rolling deployments.
- Never store database passwords in images.
- Authorize via workload identity or lifecycle-managed secrets.
- Handle controlled retries and idempotency for write operations.

Do not use a container's ephemeral filesystem to store data that must survive restarts or rescheduling.

### 3.3. Shared Cache

A cache can reduce database load and latency, but you must define:

- Whether cached data is regenerable or session state requiring high durability.
- TTL and invalidation strategy.
- Whether cache misses can trigger a database stampede.
- Behavior when the cache is unavailable.
- Consistency between the cache and database.
- Network latency and cross-zone costs.

A cache should not be the sole data source if the data cannot be regenerated. If the cache is only an acceleration layer, the API needs bounded fallback to avoid overloading the database when the cache is lost.

### 3.4. Files and Artifacts

Uploads/downloads should use object storage or a file service with an independent lifecycle:

- The API issues time-limited upload/download URLs or proxies data per design.
- File metadata and ownership are stored in the database.
- Validate content type, size, checksum, and run malware scans as required.
- Files are written to object storage before metadata transitions to a ready state.
- Do not write business files to the container's writable layer.

Local ephemeral storage should only be used for regenerable temporary files and must have size limits.

### 3.5. Long-Running Work and Asynchronous Processing

HTTP requests should not hold connections open for minutes to execute long tasks if they can be decoupled into jobs:

1. The API authenticates and validates the request.
2. The API writes a job record or creates an idempotency record.
3. The API publishes a message to a queue.
4. The API returns `202 Accepted` with the job ID and a status lookup URL.
5. Workers process the message and update the status.
6. The client polls or receives a callback/event upon completion.

Queues and workers have lifecycles separate from API replicas. When the API scales in, jobs remain in the queue and other workers can continue processing.

## 4. Designing API Contracts to Support Multiple Replicas

Statelessness is not just about how sessions are stored. The API contract must also support retries, pagination, and independent requests.

### 4.1. Requests Must Carry Sufficient Context

Every request must carry the required authentication and business identifiers. Avoid requiring clients to hit a specific replica or relying on request ordering over a single connection.

Example headers:

~~~http
POST /v1/orders
Authorization: Bearer <access-token>
Idempotency-Key: 9d9c8f7b-5f9e-4f8e-9dcb-0a9f0d8f1d21
Content-Type: application/json
X-Request-ID: req-20261122-00042
~~~

The idempotency key enables the server to recognize retries of the same business operation. The request ID is for observability and tracing, not necessarily as a deduplication key.

### 4.2. Idempotency for Write Operations

A client may retry after a timeout without knowing whether the server committed the transaction. If the API creates an order twice, duplicates can occur.

One implementation pattern:

1. The client generates a unique idempotency key for the operation.
2. The API stores the key, principal, request hash, and processing status.
3. The API executes the entity-creation transaction and stores the result bound to that key.
4. Repeated requests with the same key and same payload receive the stored result.
5. The same key with a different payload must be rejected or handled per contract.

Idempotency records need a TTL/retention period suited to client retry windows and business requirements. Saving the key and performing the side effect should share a clear transaction boundary.

### 4.3. Pagination and Cursors

Do not store pagination positions in a replica's memory. Use verifiable cursors or continuation tokens that carry enough information for the next request to be independent.

Cursors must avoid leaking sensitive details. Tokens can be signed or encrypted and bound to filters, sort order, tenant, and query version.

### 4.4. Do Not Rely on Request Ordering

Multiple replicas can receive requests concurrently. If business logic requires ordering, enforce it with database transactions, optimistic concurrency, sequence numbers, partitioned queues, or appropriate locking mechanisms. Do not assume the load balancer will route all requests from a client to the same container in exact order.

## 5. Container Images and Runtime Configuration

Containers should be packaged as immutable images that can be deployed repeatedly across nodes and environments.

### 5.1. Reproducible Images

- Pin base image and dependency versions.
- Build images in a CI pipeline.
- Scan for vulnerabilities and generate an SBOM if required by policy.
- Do not embed credentials or environment-specific data in images.
- Attach versions/digests and provenance.
- Prefer small images containing only the necessary runtime.
- Run the exact same artifact across dev, staging, and production; supply environment differences via runtime configuration.

### 5.2. Example Dockerfile

~~~dockerfile
FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production

COPY package*.json ./
RUN npm ci --omit=dev

COPY --chown=node:node dist ./dist
USER node

EXPOSE 8080
CMD ["node", "dist/server.js"]
~~~

This is an example for a Node.js application with a pre-built `dist` directory. A real pipeline should use multi-stage builds when a compiler/toolchain is needed and pin images by digest for production releases. `USER node` reduces process privileges; runtime configuration also needs to restrict filesystem, capabilities, and network access.

### 5.3. Separating Configuration from Images

A ConfigMap or managed platform configuration mechanism suits non-secret values such as:

- Ports and log levels.
- Feature flags.
- Timeouts and concurrency limits.
- Internal service endpoints.
- Queue or bucket names.

A secret manager or Kubernetes Secret integrated with encryption, RBAC, and rotation is suitable for credentials. Never place secrets in Dockerfiles, build arguments, source control, command lines, or logs.

### 5.4. Runtime Filesystem

A stateless API should be able to run with a read-only root filesystem if the framework supports it. Temporary files should use a bounded temp directory and be cleaned up when the process finishes.

Common security settings to consider:

- Run as non-root.
- `allowPrivilegeEscalation: false`.
- Drop unnecessary Linux capabilities.
- Apply an appropriate seccomp profile.
- Read-only root filesystem.
- Resource requests/limits.
- Do not mount `hostPath` arbitrarily.

## 6. Service Discovery, Ingress, and Networking

Replicas change IPs when recreated or moved across nodes. Internal clients should not hardcode pod IPs.

### 6.1. Service Discovery

In Kubernetes, a Service provides a stable endpoint for a group of pods selected by a label selector. EndpointSlices are updated according to endpoint health. Service types and ingress/gateway choices depend on how the workload is exposed.

In other managed container platforms, service discovery may be provided via service names, internal load balancers, or platform-specific endpoint abstractions.

### 6.2. Ingress and API Gateways

An API gateway or ingress may handle:

- TLS termination or TLS passthrough.
- Edge authentication when appropriate.
- Rate limiting and quotas.
- Request size limits.
- Host/path-based routing.
- WAF and policies.
- Access logs and correlation headers.

Security checks and business authorization must still be enforced inside the API. Do not trust client-supplied headers unless the gateway strips and rewrites them under trusted rules.

### 6.3. Network Segmentation

Open only necessary connections:

- Public ingress to gateway/load balancer.
- Gateway to API service.
- API to database/cache/queue/object storage.
- Metrics/logging agents to observability endpoints.

Individual pods or containers do not need public IPs if the architecture has a dedicated ingress. Use private endpoints and network policies/security groups to shrink the attack surface.

### 6.4. Connection Pooling

API scale-out can cause a sudden spike in database connections. If every replica creates a large connection pool, total connections can exceed the database's limit.

Calculate total connections:

~~~text
Max DB connections from API =
    Max API replicas × Pool size per replica
  + Connections from workers and other services
~~~

For example, 20 replicas each with a pool of 15 connections can open up to 300 connections from the API. You must also count workers, migrations, admin sessions, and other services. Use a connection pooler or cap HPA max replicas if the database cannot handle that connection count.

## 7. Health Checks: Startup, Readiness, and Liveness

Health probes tell the platform whether a container has started, can accept traffic, or needs to be restarted.

| Probe | Question | On Failure |
|---|---|---|
| Startup | Has the application finished starting up? | Holds off liveness/readiness until startup succeeds; restarts if threshold exceeded |
| Readiness | Can the replica accept new requests? | Removed from traffic-serving endpoints |
| Liveness | Is the process alive and able to recover on its own? | Restarts container after configured failure threshold |

Readiness should not depend on every auxiliary service in a way that drops all replicas simultaneously when a non-critical dependency fails. Identify which dependencies are truly required to serve requests.

Liveness should not perform deep checks on databases or external APIs. If the database is temporarily unavailable, restarting the entire API fleet can worsen the outage. Liveness should detect deadlocked processes or unrecoverable states.

### 7.1. Example Probes in Kubernetes

~~~yaml
startupProbe:
  httpGet:
    path: /health/startup
    port: http
  periodSeconds: 5
  failureThreshold: 30

readinessProbe:
  httpGet:
    path: /health/ready
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3

livenessProbe:
  httpGet:
    path: /health/live
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Endpoints must have clear semantics. `/health/ready` should return unready when the application has not loaded configuration or finished essential initialization. `/health/live` should reflect the process's ability to continue operating, not simply whether a downstream dependency is responding.

## 8. Graceful Shutdown and Connection Draining

Containers can be stopped during deployments, scale-in, node drains, or evictions. The API needs to stop accepting new requests and finish in-flight requests within the allowed time.

A shutdown sequence:

1. The platform initiates termination and runs lifecycle hooks if configured.
2. The application flips readiness to false.
3. The endpoint is removed from routing for new requests once endpoint updates propagate.
4. The application stops accepting new requests and waits for in-flight requests.
5. The process handles SIGTERM, flushes telemetry, and closes connection pools.
6. The process exits before `terminationGracePeriodSeconds`; if exceeded, the container may be killed.

### 8.1. Avoiding Dropped Requests

- Set request timeouts smaller than the remaining shutdown window.
- Enforce deadlines on in-flight requests.
- Do not start long-running jobs inside an HTTP request without a handoff mechanism.
- Use durable queues for background tasks.
- Flush logs/traces without blocking shutdown indefinitely.
- Check load balancer deregistration delays and propagation times.

A `preStop` hook can call an internal endpoint to switch the application into drain mode. Do not simply add an arbitrary fixed sleep without measuring endpoint and routing propagation times.

## 9. Autoscaling and Capacity Planning

Stateless APIs lend themselves well to horizontal scaling because each replica can serve requests independently. However, scaling the API does not mean every dependency can scale infinitely.

### 9.1. Choosing Scaling Metrics

Metrics you can use:

- CPU utilization.
- Memory utilization if the application has a predictable memory pattern.
- Requests per second or concurrent requests.
- Request queue/worker queue depth.
- p95 latency as a supporting signal.
- Custom metrics reflecting application busyness.

CPU is easy to use, but it may not represent I/O-bound workloads or workloads blocked on the database. Benchmark to determine single-replica capacity and choose appropriate metrics.

### 9.2. HPA and Node Autoscalers

In Kubernetes:

- Horizontal Pod Autoscaler (HPA) increases/decreases pod count based on metrics.
- Cluster Autoscaler or node provisioning controllers add nodes when pods cannot be scheduled due to resource shortages.
- Managed control planes manage control components as part of the service.

HPA does not automatically guarantee nodes or quotas exist. If a node pool hits its max, new pods can stay Pending. Check quotas, subnet IPs, zone capacity, and resource requests.

### 9.3. Example HPA

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
~~~

This example requests a minimum of 3 and a maximum of 20 replicas, targeting 65% average CPU utilization against resource requests. Values must be tuned via load testing; `minReplicas: 3` only makes sense if the cluster has capacity distributed across the required failure domains.

### 9.4. Scaling Around Bottlenecks

Before adding replicas, identify the bottleneck:

- API CPU-bound: add replicas or choose a suitable CPU tier.
- Database-bound: reduce queries, cache appropriately, bound concurrency, or scale the database.
- Network-bound: inspect egress, connections, and endpoints.
- Queue-bound: add workers if downstream dependencies have capacity.
- Memory-bound: adjust memory requests/limits and check for leaks.

If the database is already at its connection limit, adding API replicas can increase latency and error rates. HPA must be designed alongside connection budgets and downstream capacity.

## 10. High Availability and Replica Distribution

Production APIs typically require multiple replicas distributed across nodes/zones to reduce concentrated single points of failure.

### 10.1. Topology Spread

Topology spread constraints can distribute replicas across zones and hostnames:

~~~yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: orders-api
  - maxSkew: 1
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: ScheduleAnyway
    labelSelector:
      matchLabels:
        app: orders-api
~~~

`DoNotSchedule` on zone can leave pods Pending if the cluster lacks enough eligible domains or capacity. `ScheduleAnyway` on hostname only prioritizes balance; it does not guarantee only one replica per node.

### 10.2. PodDisruptionBudget

A PodDisruptionBudget limits how many pods can be disrupted during supported voluntary disruptions, such as node drains:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

PDBs do not prevent involuntary disruptions such as node crashes or zone outages. Combine multiple replicas, topology spread, readiness probes, and spare capacity.

### 10.3. Multi-Zone Dependencies

An API may run across multiple zones while its database has only a single primary in one zone. If that zone fails, the API still has healthy pods but cannot serve requests that require the database.

Evaluate end-to-end HA for:

- Database and read replicas.
- Cache and queues.
- DNS, ingress, and load balancers.
- Secret manager, KMS, and identity endpoints.
- Object storage and private endpoints.
- Monitoring/alerting.

Application availability is bounded by the most critical dependency on the request path.

## 11. Example Deployment for a Stateless API

The manifest below brings together key concepts: multiple replicas, resource requests/limits, probes, security context, shutdown grace period, and topology spread. Replace the image, namespace, and endpoints for your actual environment.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  labels:
    app: orders-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 45
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        seccompProfile:
          type: RuntimeDefault
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: orders-api
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: orders-api
      containers:
        - name: api
          image: registry.example.invalid/orders-api:1.8.0
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: PORT
              value: "8080"
            - name: DATABASE_HOST
              value: orders-db.internal
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
          lifecycle:
            preStop:
              httpGet:
                path: /internal/drain
                port: http
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
~~~

The image registry is a placeholder. The application should implement `/internal/drain` with internal authentication or bound only to the appropriate interface, switching readiness to false and stopping acceptance of new requests. If the application needs to write temporary files, add a bounded `emptyDir` mount instead of enabling a writable root filesystem.

`DATABASE_HOST` is only an example of non-secret configuration. Credentials should be fetched via workload identity or the platform's secret integration; never put plaintext passwords in manifests.

### 11.1. Internal Service

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: orders-api
spec:
  selector:
    app: orders-api
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
~~~

The Service creates a stable internal endpoint and selects pods with the label `app=orders-api`. Ingress or a gateway can route external traffic to this Service.

### 11.2. HPA and PDB

The HPA and PDB from earlier examples can be applied alongside the Deployment. Verify:

- HPA does not scale beyond node pool capacity.
- PDB does not block all drain operations when replica counts drop.
- Rolling updates have capacity for `maxSurge`.
- Topology spread has enough eligible zones.
- Resource requests align with the scheduler and HPA CPU utilization targets.

## 12. Security for Container APIs

### 12.1. Identity and Least Privilege

Each workload should have its own identity:

- Read only the exact secrets required.
- Access only the needed databases/schemas or buckets.
- Never use cloud account administrator privileges.
- Separate production identities from dev/test.
- Use short-lived credentials or workload identities whenever possible.

### 12.2. Network Security

- Expose only necessary gateways/ingresses publicly.
- APIs accept traffic only from authorized sources.
- Databases/caches/queues accept connections only from appropriate workload identities/network segments.
- Restrict egress to declared dependencies.
- Enable TLS for traffic crossing trust boundaries.
- Do not treat a private network as a substitute for authentication/authorization.

### 12.3. Container Security

- Use images from controlled registries.
- Scan images and keep base images updated.
- Run non-root, drop capabilities, and avoid privileged containers.
- Use a read-only filesystem if supported by the application.
- Do not mount the Docker socket or unnecessary `hostPath` volumes.
- Set CPU/memory requests and limits.
- Update runtimes and nodes according to platform policy.

### 12.4. API Security

- Verify tokens and check issuer, audience, and expiry.
- Enforce authorization at the resource/tenant level, not just authentication.
- Apply rate limiting and quotas per principal.
- Validate inputs and bound request body sizes.
- Prevent replay or duplicate execution for sensitive operations.
- Do not log tokens, passwords, or unnecessary personal data.
- Write audit logs for administrative actions and critical transactions.

## 13. Observability and Operations

When there are multiple replicas, local logs from a single container are not enough to understand an entire request.

### 13.1. Structured Logging

Logs should include:

- UTC timestamp.
- Service name and version.
- Pod/instance identity.
- Request ID and trace ID.
- Route/method/status code.
- Duration.
- Error class.
- Tenant/principal ID handled in accordance with security policy.

Never log tokens, passwords, secrets, or sensitive payloads. Centralized logging makes it possible to find requests regardless of which replica handled them.

### 13.2. Metrics

Monitor:

| Group | Metric |
|---|---|
| Traffic | Request rate, concurrent requests, request size |
| Errors | 4xx/5xx, timeouts, dependency errors |
| Latency | p50, p95, p99 by route |
| Compute | CPU, memory, throttling, restarts, OOMs |
| Scaling | Desired/current replicas, pending pods, scaling events |
| Dependency | DB pool usage, query latency, cache hit ratio, queue age |
| Lifecycle | Startup duration, readiness transitions, drain duration |
| Business | Transaction success, duplicate prevention, jobs accepted/completed |

### 13.3. Distributed Tracing

Trace context must be propagated through the gateway, API, database clients, and queue messages. For asynchronous processing, create linked spans or trace links to connect the initiating request with the worker that processes it later.

## 14. Deployment, Rollout, and Rollback

Stateless containers allow phased replica replacement if the application handles shutdown and compatibility properly.

### 14.1. Rolling Updates

Rolling updates gradually replace old pods with new pods:

- `maxSurge` allows creating extra pods during the update.
- `maxUnavailable` bounds how many pods can be unavailable per rollout strategy.
- Readiness probes prevent unready pods from receiving traffic.
- Graceful shutdown lets old pods finish in-flight requests.

Ensure sufficient capacity for surge. If the node pool is full, new pods can stay Pending and stall the rollout.

### 14.2. Backward-Compatible Changes

Applications and databases are usually not deployed atomically in lockstep. Use the expand-and-contract strategy:

1. Add new schemas/fields in a way that keeps the old version working.
2. Deploy an API version that can read/write compatibly with both old and new schemas.
3. Backfill or migrate data.
4. Shift clients/traffic to the new version.
5. After verification, remove old fields/APIs in a subsequent release.

Never deploy breaking schema changes before all old replicas have stopped.

### 14.3. Canary and Blue-Green

Canary sends a fraction of traffic to the new version to observe errors and latency. Blue-green runs two environments in parallel and switches traffic once the new environment passes criteria.

With a stateless API, two versions can run concurrently if:

- API contracts are compatible.
- Database schemas support both versions.
- Session/token and cache formats do not change incompatibly.
- Queue message schemas are versioned.
- Rollback does not lose data written by the new version.

## 15. Reliability and Handling Dependency Failures

A stateless API can still fail if the database, cache, or queue is unavailable.

### 15.1. Timeouts and Retries

- Every dependency call requires a finite timeout.
- Retry only on transient errors.
- Use exponential backoff and jitter.
- Set retry budgets so retries do not amplify load.
- Use circuit breakers or bulkheads when appropriate.
- Do not retry write operations without idempotency.

### 15.2. Degraded Mode

If the cache is unavailable while the database is still healthy, the API can bypass the cache within bounded concurrency. If a non-essential secondary feature fails, return a partial response per contract.

Do not turn all errors into HTTP 200 or return fabricated data. Degraded responses must be explicit, metered, and must not violate business invariants.

### 15.3. Request Deadlines

The overall request deadline must be larger than the sum of mandatory step timeouts, yet smaller than the gateway/client timeout. Never let the API hold connections indefinitely when a dependency hangs.

## 16. Testing Statelessness and Scalability

An API is only considered stateless after testing behavior when replicas are replaced and requests are distributed differently.

Test cases:

1. Send the first request to replica A and the next request to replica B.
2. Restart or terminate a replica under active traffic.
3. Scale from min replicas up to peak replicas.
4. Scale in while requests are in flight.
5. Slow down the cache or database in a test environment.
6. Resend the same idempotency key after a timeout.
7. Perform a rolling update under active traffic.
8. Simulate a node drain or single-zone unavailability.
9. Verify file uploads and jobs do not depend on the local filesystem.
10. Verify no secrets or sensitive session data appear in logs/images.

### 16.1. Test Criteria

| Check | Expected Result |
|---|---|
| Request to any replica | Identical contract and authorization behavior |
| Replica terminated | New requests are routed to healthy replicas |
| Sessions | Not lost due to container restarts |
| Files | Remain accessible via durable storage |
| Long-running jobs | Continue via queue/workers, independent of API process |
| Duplicate requests | Idempotency prevents duplicate side effects |
| Scale-out | New pods pass health checks before receiving traffic |
| Scale-in | In-flight requests drain within the grace period |
| Dependency outage | Bounded timeout/retry/degraded behavior |
| Rollback | Old version remains compatible with written data |

## 17. Troubleshooting

### 17.1. Requests Occasionally Lose Sessions

Check whether sessions live in local memory or the filesystem. If so, migrate to tokens or a shared session store. Sticky sessions can mask symptoms but do not solve failures when a replica is lost.

### 17.2. Pod Is Ready, but the API Returns Errors

The readiness probe may only check that the process is running without verifying essential config or dependencies. Inspect readiness endpoint semantics, startup initialization, and application error logs. Avoid making readiness depend on non-essential auxiliary services.

### 17.3. Scale-Out Overloads the Database

Calculate total connection pools across max replicas, workers, and other services. Cap pool sizes/concurrency, use a connection proxy if suitable, optimize queries, and consider scaling the database.

### 17.4. Rolling Update Stalls

Check for Pending new pods caused by resource shortages, topology constraints, image pulls, secrets, or probes. Check `maxSurge`, `maxUnavailable`, node capacity, and startup time. Do not inflate timeouts indefinitely to mask readiness failures.

### 17.5. Requests Are Dropped During Scale-In

Check readiness flipping to false, `preStop` hooks, SIGTERM handling, load balancer draining, and `terminationGracePeriodSeconds`. Set appropriate request deadlines and offload long tasks to queues.

### 17.6. Cache Loss Causes Database Load Spike

Check for cache miss storms, retries, and unconstrained concurrency. Use request coalescing, rate limiting, TTL jitter, or bounded fallbacks. Do not allow all replicas to reload the same large dataset simultaneously.

## 18. Managed Container Platform Options

Operational models vary by platform:

| Platform Category | Examples | Characteristics |
|---|---|---|
| Managed Kubernetes | Amazon EKS, Azure Kubernetes Service, Google Kubernetes Engine | Provider manages part of the control plane; user manages workloads, policies, and nodes/capacity depending on mode |
| Managed container service | Amazon ECS with capacity providers or Fargate | Task/service orchestration, integrated load balancing and service-level autoscaling |
| Serverless container platform | Google Cloud Run, Azure Container Apps, AWS App Runner | Provider manages most container infrastructure; scales on requests/events with concurrency/minimum instance settings |

Exact feature names and responsibilities vary by service, mode, and region. Managed does not mean the provider is responsible for your API contract, data, IAM, secrets, SLOs, or recovery logic.

### 18.1. When to Choose Managed Kubernetes

Suitable when you need:

- Multiple services sharing a common platform.
- Rich scheduling, policy, and network controls.
- Custom controllers/operators or specialized workloads.
- Granular control over topology, resources, and rollouts.

In exchange, the team needs capability to manage clusters, nodes, ingress, storage, upgrades, and security.

### 18.2. When to Choose Managed/Serverless Containers

Suitable when you want:

- To reduce node and cluster management overhead.
- HTTP/event workloads that scale on requests.
- Service runtime and networking models that fit the application.
- Acceptance of execution, concurrency, or system configuration limits.

Evaluate cold starts, minimum instances, scale-to-zero, request timeouts, max concurrency, network egress, and regional limits before committing.

## 19. Stateless API Design Checklist

**Application**

- [ ] Requests do not depend on local sessions or memory of a prior replica.
- [ ] Sessions/tokens can be verified by any replica.
- [ ] Business data is stored in databases/storage with independent lifecycles.
- [ ] Files and long jobs do not depend on local filesystems/processes.
- [ ] Write operations have idempotency or deduplication mechanisms.
- [ ] API has clear timeouts, pagination, and contracts.

**Container**

- [ ] Images are immutable, versioned/digested, and scanned.
- [ ] No secrets are embedded in images or manifests.
- [ ] Runs as non-root with reduced privileges.
- [ ] Resource requests/limits are properly configured.
- [ ] Root filesystem is read-only if possible; temp storage is bounded.

**Platform**

- [ ] Service discovery and ingress are configured.
- [ ] Readiness, liveness, and startup probes have distinct semantics.
- [ ] Graceful shutdown and connection draining work properly.
- [ ] HPA/node autoscaling has sufficient capacity and quotas.
- [ ] Replicas are distributed across nodes/zones as required.
- [ ] PDB and rollout strategy do not block deployments.

**Data and Security**

- [ ] Database connection budget fits max replicas.
- [ ] Caches have TTLs, invalidation, and fallbacks.
- [ ] Object storage has policies and lifecycles.
- [ ] Workload identities have least privilege.
- [ ] Network policies, TLS, auditing, and secret rotation are configured.

**Operations**

- [ ] Logs/metrics/traces include request IDs and trace IDs.
- [ ] Latency, errors, saturation, and dependency health are monitored.
- [ ] Alerts exist for Pending pods, restarts, OOMs, and scaling failures.
- [ ] Compatible rollout, rollback, and migration processes exist.
- [ ] Replica termination, scale-out, scale-in, and dependency outages have been tested.

## 20. Implementation Process

1. Classify application state: sessions, business data, files, cache, and background jobs.
2. Move persistent state to databases, shared caches, object storage, or queues.
3. Design request contracts with authentication, authorization, idempotency, and pagination.
4. Package the API into an immutable, non-root image free of secrets.
5. Configure runtime settings, workload identity, and least-privilege network access.
6. Deploy multiple replicas behind a Service/ingress or managed endpoint.
7. Configure startup/readiness/liveness probes and graceful shutdown.
8. Set resource requests/limits, autoscaling, and capacity buffers.
9. Configure multi-zone placement, PDBs, and rollout strategies.
10. Integrate logs, metrics, traces, and alerts.
11. Test replica replacement, retries, scaling, and dependency failures.
12. Release gradually, monitor SLOs/costs, and tune against actual load.

## 21. Operational Principles

1. **Replaceable replicas:** never keep the sole copy of business state in RAM or local filesystem.
2. **Externalize state:** use databases, caches, object storage, and queues in their proper roles.
3. **Independent requests:** every replica authenticates and processes requests under the same contract.
4. **Idempotency for side effects:** retries must not create duplicate transactions or jobs.
5. **Immutable images:** deploy the exact same artifact across environments, injecting config at runtime.
6. **Purpose-built health probes:** distinguish startup, readiness, and liveness.
7. **Controlled shutdown:** drain requests, handle SIGTERM, and close connections before the grace period expires.
8. **Scale around bottlenecks:** protect databases, caches, and queues from excessive API scaling.
9. **End-to-end HA:** distribute replicas across failure domains and evaluate dependencies too.
10. **System-wide observability:** correlation IDs, traces, metrics, and logs must span all replicas.

A stateless API on managed containers lets applications scale with load, replace failed replicas, and roll out new versions with minimal dependency on individual machines. These benefits are achieved only when sessions, data, files, and long-running work are moved out of the container lifecycle; requests are idempotent; health checks and shutdowns accurately reflect serving state; and databases, networks, and dependencies have adequate capacity. When all these pieces are designed together, containers become flexible, resilient execution units in a reliable API architecture.
