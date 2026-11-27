# Designing Stateless Workloads for Automatic Machine Replacement

In a cloud environment, a virtual machine or container can be replaced during autoscaling, new version rollouts, host maintenance, or incident recovery. If an application depends on data that exists only on that machine, replacing it can lose user sessions, in-flight jobs, or configuration required to start. Stateless design allows compute instances to be provisioned and terminated automatically without losing business state.

Within the scope of CLOUD_CORE_SERVICES_COMPUTE, this lesson places stateless design in the context of cloud compute models, ranging from virtual machines and containers to serverless. When compute is treated as a replaceable resource, systems can scale with load, deploy frequently, and recover from faults with minimal manual intervention. This requires storing state in places with an appropriate lifecycle, re-provisioning identity and configuration securely, and ensuring the application can tolerate interrupted requests, jobs, or connections.

After this lesson, you will be able to:

- Explain statelessness at the compute level and distinguish it from an application having no state at all.
- Determine which data can remain temporarily on an instance and which must live outside the machine's lifecycle.
- Design sessions, files, jobs, and configuration so backends can be replaced.
- Use immutable images, automated bootstrapping, workload identity, and service discovery to create new machines.
- Handle request retries, message redelivery, graceful shutdown, draining, and idempotency.
- Test autoscaling, rolling replacement, and recovery after an instance is abruptly deleted.

## 1. What Does Stateless Mean?

A compute instance is designed to be stateless when replacing the instance does not lose unique data or business state needed for the system to keep operating. An instance may hold temporary data in RAM or on local disk for performance, provided that data can be regenerated or retrieved from a source with an independent lifecycle.

Stateless does not mean the application processes no state. An e-commerce application still needs to know whether a user is logged in, what is in their cart, and what stage an order is in. The difference is that this state does not exist solely in the memory of a specific VM or container.

Examples:

- An API receives a request, reads the session from a shared store, writes the order to a database, and returns a response. The API VM can be replaced while the order remains intact.
- A worker consumes a message from a queue, executes an idempotent transaction, and writes the result to a database. If the worker stops, the message can be redelivered to another worker.
- A web frontend serves content from object storage or a CDN instead of keeping uploaded files solely on a VM's local disk.
- A container is created from a versioned image and retrieves configuration from a configuration management system and secret manager at startup.

### Stateless vs. Stateful

| Criterion | Stateless Compute | Stateful Compute |
|---|---|---|
| Business state | Stored in a database, object storage, queue, or shared store | May reside in an instance's RAM or dedicated disk |
| Instance replacement | New machine can be provisioned and added to service | Requires transferring, synchronizing, or recovering state |
| Autoscaling | Easy to add/remove instances if dependencies have capacity | Requires managing membership, replication, shards, or quorum |
| Rolling deployment | Can replace instances one by one based on health and readiness | Requires state handoff and data compatibility procedures |
| Failover | Another instance can immediately continue processing | May require leader election, replication, or recovery |
| Primary risk | Shared dependencies become critical points | Loss of local data or inconsistent state |

A system can combine both. For example, a stateless API runs across multiple VMs while the database is a stateful service with replication and backups. The goal is choosing the right place to store state, not forcing every component to be stateless at any cost.

## 2. Classifying State Before Designing

The first step is listing every type of data the application reads, creates, or modifies. Not all data requires the same type of storage.

| State Type | Examples | Appropriate Storage | Can Be Lost on Replacement? |
|---|---|---|---|
| Long-lived business data | Orders, payments, profiles | Database or durable data service | No |
| User files | Images, documents, export files | Object storage or shared file storage | No |
| Session | Login, shopping cart, wizard | Shared session store or protected token | No, within session lifetime |
| Pending work | Emails, image processing, sync jobs | Durable queue or workflow engine | No; must be redelivered if worker dies |
| Cache | Query results, refreshable token metadata | Shared cache or local cache | Yes, if safely regenerable |
| Temporary files | Intermediate files, scratch data | Ephemeral disk or temporary volume | Yes |
| Configuration | Endpoints, feature flags, runtime parameters | Config service or versioned config artifact | Not instance-dependent |
| Secrets | DB passwords, API credentials, certificates | Secret manager or key management system | Not baked solely into image |
| Process state | Threads, in-RAM variables, connection pools | Rebuilt on process startup | Yes; must have recovery mechanisms |
| Observability data | Logs, metrics, traces | Centralized telemetry backend | Not kept solely on the machine |

### Inventory Questions

For each piece of data, answer:

1. Is this business data, cache, or temporary data?
2. Where is the authoritative source of truth?
3. If an instance is abruptly lost, can the data be recreated?
4. If it cannot be recreated, what are the RPO and backup/replication mechanisms?
5. Can another instance read it or resume processing?
6. Does the data require transactions, locking, ordering, or special consistency guarantees?
7. Who is authorized to access it and what is the retention period?

If an important file or record exists only on a VM's local disk, that instance is not yet safe to replace.

## 3. Decoupling Compute from Durable Data

Compute should perform processing and remain replaceable; critical data should reside in services whose lifecycle is independent of individual instances.

### Database

Databases hold structured data and transactional state. Multiple API instances can connect to the same database or database cluster according to access policies.

Design requirements:

- Stable database endpoint via DNS or a managed endpoint.
- Bounded connection pools per instance and across the fleet.
- Transactions and isolation levels appropriate to business logic.
- Backups, point-in-time recovery, and restore testing.
- Replication/failover aligned with RPO/RTO targets.
- Schema migrations compatible with concurrently running application versions.

Do not store database files or transaction logs solely on the ephemeral disk of an application VM. For self-managed databases, storage, replication, and recovery procedures must be designed as a separate stateful system.

### Object Storage

Object storage is well suited for uploaded files, images, documents, artifacts, and exports. Backends store objects by key and store metadata in a database rather than writing files solely to a container's filesystem.

Example upload flow:

1. The API authenticates the user and checks permissions.
2. The API issues a temporary upload URL or receives the file and writes the object.
3. Object storage persists the content durably.
4. The database stores the object key, owner, checksum, and processing status.
5. Workers can read the object from any instance.

If the object and database record are written across two separate systems, handle the case where one operation succeeds while the other fails. Pending statuses, outbox/events, retries, and reconciliation jobs can be used.

### Queue and Workflow Engine

Queues decouple job submission time from worker processing time. Workers can stop and be replaced if messages are durably persisted and acknowledgement/redelivery semantics are configured properly.

Define:

- Message visibility timeout or lease.
- Retry policy and backoff.
- Dead-letter queue for repeatedly failing messages.
- Idempotency so redelivered messages do not cause duplicate side effects.
- Ordering and partition keys if ordering is a business requirement.
- Checkpointing for long-running jobs.

### Cache

Caches reduce database load and latency, but you must identify which data can be regenerated. Cache misses after instance replacement can cause sudden load spikes on the database. Implement warm-up, TTLs, eviction, and cache-stampede protection where appropriate.

Do not use a cache as the source of truth if data must survive eviction, restarts, or failover, unless the caching system is explicitly architected as a durable data store under the service's semantics.

## 4. Managing Sessions Without Depending on a Single Machine

A web application might store sessions in backend RAM. When the load balancer routes the next request to a different machine, the new backend cannot find the session. Session affinity can mask symptoms, yet it still depends on the original machine staying alive.

Common options:

### Shared Session Store

Store sessions in Redis or a database with appropriate availability. Each backend reads the session ID from a cookie, fetches state from the store, and writes updates back.

Benefits:

- Backends are interchangeable.
- Rolling deployments and autoscaling are easier.
- Losing an instance does not lose sessions while the shared store remains available.

Points to manage:

- TTL, eviction, and capacity.
- Network latency, timeouts, and connection pools.
- HA, backups, or persistence as required.
- Serialization/schema versioning during rolling deployments.
- Encryption and access control for session data.
- Handling store outages without triggering a retry storm.

### Signed or Encrypted Client-Side Tokens

A signed or encrypted token can carry a small amount of state. Backends verify the signature and expiration without querying a session store on every request.

Caveats:

- Signatures protect integrity but do not hide contents; use encryption to keep contents confidential.
- Tokens are typically hard to revoke immediately before expiration without a deny-list or additional state checks.
- Do not put sensitive data or large payloads into tokens.
- Manage signing keys, rotation, audience, issuer, and expiry.
- Authorization must still be enforced server-side.

### Do Not Rely on Sticky Sessions as the Sole State Store

Sticky sessions can serve as a transitional measure for legacy applications, but backends can still restart, scale in, or suffer host failures. If session persistence is required, externalize state or design appropriate tokens.

## 5. Designing Requests and Jobs for Safe Retries

In distributed systems, a client or queue may retry an operation after a timeout. The server may have already completed the work while the response was lost; a retry can create duplicate transactions if the operation is not idempotent.

**Idempotency** means executing the same request multiple times with the same key has the same business effect as executing it once, within a defined scope and timeframe.

### Idempotency Key

For example, a client sends a payment creation request with a unique idempotency key. The server stores the key along with the transaction status and result. If the request is retried, the server returns the recorded result instead of creating a new payment.

Conceptual flow:

~~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API instance
    participant DB as Durable database
    C->>A: POST /payments + idempotency key
    A->>DB: Check key and create operation
    DB-->>A: Committed result
    A-->>C: Response
    Note over C,A: Response may be lost on the network
    C->>A: Retry with same idempotency key
    A->>DB: Read operation by key
    DB-->>A: Return stored result
    A-->>C: Same result, no new payment created
~~~~

Enforce a unique constraint or transaction so two concurrent requests cannot create the operation simultaneously. Keys should be scoped to the principal/tenant and operation type to avoid collisions or abuse.

### Workers and Message Redelivery

A worker can receive a message, process it, and terminate before acknowledging it. The queue will redeliver the message to another worker. Therefore:

- Record processed message IDs or business operation IDs.
- Use transactions to update business data and processing status together when possible.
- Design external side effects with idempotency keys.
- Acknowledge messages only after results are durably persisted.
- Limit retries and route poison messages to a dead-letter queue.
- Never assume exactly-once delivery unless the specific system and semantics explicitly guarantee it.

### Outbox Pattern

When an application must write to a database and publish an event, two independent operations may not both succeed. The outbox pattern writes the business change and the event inside the same database transaction; a separate publisher reads the outbox and dispatches the message. Because the publisher may send duplicates, consumers must still be idempotent.

## 6. Making Instances Reproducible: Immutable Images and Bootstrapping

A replacement instance must be provisionable from versioned images and configurations without requiring operators to log in to install packages or manually edit files.

### Golden Image or Container Image

An image should contain:

- Base OS or runtime patched according to policy.
- Required dependencies and agents.
- Application or artifact with an explicit version.
- Default users/groups and security hardening.
- Startup, health check, and telemetry hooks.

Never bake secrets, personal private keys, or long-lived credentials into an image. Images should be built in a pipeline, scanned for vulnerabilities, signed or provenance-verified where supported, and released by immutable version or digest.

### Bootstrap

When a VM or container is created:

1. The platform assigns a workload identity.
2. Bootstrap reads environment configuration from authorized sources.
3. Secrets are fetched via the identity and secret manager.
4. The application starts with a deterministic version.
5. Agents register telemetry and health endpoints.
6. The instance receives traffic only after passing readiness checks.

Bootstrapping must be re-runnable or detect already-completed steps. If the script runs twice, it must not create duplicate accounts, overwrite critical data, or cause unintended state changes.

### Infrastructure as Code

Use IaC to define VM templates, launch templates, container deployments, networking, roles, storage, and autoscaling. Reviewed and versioned configurations ensure replacement instances share the same baseline.

Avoid configuration drift from manual edits on live machines. If an emergency fix is needed, record the change and merge it back into the source of truth so newly created machines receive the right configuration.

Conceptual bootstrap example:

~~~~yaml
compute_template:
  image: orders-api:1.8.4
  instance_profile: orders-api-runtime
  user_data:
    config_source: config/orders/production
    secret_source: secret/orders-api
    startup_command: /opt/orders/bin/start
  health:
    startup_path: /health/startup
    readiness_path: /health/ready
  lifecycle:
    replace_on_image_change: true
~~~~

This is illustrative YAML, not a schema directly usable on a specific cloud provider. Map it to launch templates, instance groups, VM scale sets, or orchestrator configurations on your target platform.

## 7. Identity and Configuration Must Follow the Workload

A new instance may have a different instance ID, IP address, or hostname. Applications should not rely on fixed machine identities to access services.

### Workload Identity

Use instance roles, managed identities, service accounts, or workload federation to grant permissions to new machines. Permissions should be scoped to the application role and required resources.

Examples:

- `orders-api` only reads database connection secrets and writes order events.
- `invoice-worker` only reads the invoice queue and writes objects to the invoice bucket.
- `reporting-job` only reads aggregated data and writes reports.

Do not copy long-lived access keys from old machines to new ones. Do not grant a broad administrative role to the entire fleet merely for bootstrap convenience.

### Configuration

Configuration may include database endpoints, feature flags, log levels, regions, concurrency limits, and runtime parameters. Distinguish between:

- Environment configuration: development, staging, production.
- Workload-role configuration: API, worker, scheduler.
- Secrets: passwords, tokens, private keys, and credentials.
- Dynamic runtime config: changes that can be reloaded without rebuilding the image.

Configuration must be versioned or audited and validated before rollout. Secrets require encryption, access control, rotation, and access logging.

### Service Discovery

Replacement instances may receive new IP addresses. Other components should locate services via DNS, a service registry, a load balancer, or managed endpoints instead of hardcoding machine addresses.

For outbound allow-lists, use NAT or egress gateways with stable addresses if partners require them. Do not rely on ephemeral per-VM public IPs as long-term identities.

## 8. Health Checks, Readiness, and Instance Lifecycle

A new instance should not receive traffic immediately when the VM enters the running state. The OS may have booted while the application is still loading config, fetching secrets, warming caches, or connecting to dependencies.

### Three States to Distinguish

- **Startup:** has the application finished initial initialization?
- **Readiness:** can the application safely accept new requests?
- **Liveness:** is the process still healthy and able to continue, or does it need a restart?

Readiness should reflect the instance's ability to serve. If an optional dependency fails, marking the entire API not-ready may be unnecessary; if a mandatory database is unreachable, pulling the instance out of traffic may be required depending on application semantics.

### Replacement Lifecycle

~~~~mermaid
flowchart TD
    A[Create new instance from image] --> B[Bootstrap config and identity]
    B --> C[Start application]
    C --> D[Startup probe succeeds]
    D --> E[Readiness succeeds]
    E --> F[Register in backend pool]
    F --> G[Serve traffic]
    G --> H[Receive drain or terminate signal]
    H --> I[Mark not-ready]
    I --> J[Stop accepting new requests]
    J --> K[Complete in-flight requests/jobs]
    K --> L[Flush and close connections]
    L --> M[Terminate instance]
~~~~

### Graceful Shutdown

Upon receiving a termination signal:

1. Stop accepting new requests or new messages.
2. Mark not-ready so the load balancer/orchestrator removes the instance from backends.
3. Wait for connection draining within the allotted grace window.
4. Complete in-flight requests or cancel upon timeout.
5. For workers, stop pulling new messages and finish or release leases.
6. Flush needed data, close connection pools, and emit final logs.
7. Exit before the grace period expires.

You cannot rely exclusively on graceful shutdown because a host can lose power unexpectedly. All critical data must be durably persisted before acknowledging work completion.

## 9. Autoscaling and Automatic Machine Replacement

Autoscaling adds or removes instances based on metrics, schedules, or forecasts. Stateless design lets each new instance join the fleet without migrating local state.

### Scale-Out

When load increases:

- The autoscaler launches instances from a tested template/image.
- Bootstrap provisions identity and configuration.
- Startup/readiness probes verify the application.
- The load balancer adds healthy backends.
- The instance starts serving traffic.
- Dashboards monitor throughput, latency, errors, and saturation.

Account for the time from the scaling decision until the instance is actually ready. If startup takes several minutes, keep headroom or spare capacity to absorb spikes.

### Scale-In

When load decreases:

- The autoscaler selects instances to terminate.
- The instance is deregistered or marked draining.
- No new requests are routed to it.
- In-flight requests/jobs complete or are safely handed off.
- Local caches and temporary data can be discarded.
- The instance is terminated.

Do not select instances solely by low CPU if they hold long-lived connections or critical jobs. Coordinate lifecycle hooks, drain timeouts, and queue/lease mechanisms.

### Avoiding Scale Storms

If all new instances boot simultaneously, they may all load caches, open database connections, or fetch secrets at once, creating a load spike on dependencies. Use jitter, bootstrap concurrency limits, bounded connection pools, and staged warm-up.

## 10. Design Across VMs, Containers, and Serverless

| Model | How Statelessness Is Implemented | Key Considerations |
|---|---|---|
| VM/instance group | Immutable images, launch templates, external database/object storage, load balancer, and autoscaling | Bootstrapping, local disk, changing IPs, instance lifecycle, and capacity |
| Container/orchestrator | Images by digest, reschedulable Pods, persistent data in external services, ConfigMap/Secret or secret manager | Namespaces, volume lifecycle, readiness, termination grace period, requests/limits |
| Serverless function | Each invocation may run on a fresh or reused execution environment; business state in database/queue/object storage | Do not assume RAM/local temp persists across invocations; handle retries, concurrency, and timeouts |
| Managed application platform | Declared artifact and config; platform replaces instances by health and policy | Understand what data the platform retains, lifecycle hooks, and runtime limits |

### VM Example

An API fleet runs on multiple VMs behind a load balancer. Each VM is created from the same image, assumes a dedicated role, loads config and secrets at boot, and connects to a managed database. Uploaded files reside in object storage. When a VM fails, the autoscaling group launches a new VM and the load balancer adds it only after readiness succeeds.

### Container Example

A Kubernetes Deployment runs multiple replicas. Pods do not store business data on their writable layer; sessions live in a shared store, files in object storage, and jobs in a queue. Pods define a readiness probe and termination grace period. When a node is drained, Pods are recreated on other nodes.

Illustrative configuration example:

~~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: api
          image: registry.example/orders-api:1.8.4
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
~~~~

This is a minimal example. Production also needs appropriate startup/liveness probes, `securityContext`, secret injection, disruption budgets, rollout strategies, service accounts, and observability.

### Serverless Example

An image-processing function receives an event containing an object key, reads the file from object storage, processes it, writes the output back to storage, and updates the database. The function does not keep unique results in RAM after the invocation. If the platform retries the event, an idempotency key or job status prevents duplicate processing.

## 11. Handling Temporary Data and Local Disk

Stateless design does not require banning local disk entirely. Local disk is useful for caches, scratch files, temporary extraction, and regenerable data.

Selection rules:

- Temporary data must have a TTL or cleanup routine.
- Files shared across instances must reside in object/shared storage.
- Never store unique uploads, database files, or critical transactions on ephemeral disk.
- For batch jobs, write checkpoints periodically to durable storage.
- Set size limits and monitor disk pressure.
- On termination, do not copy caches if they can be re-warmed from the source of truth.

If a persistent volume must attach to a stateful workload, manage the volume lifecycle independently and define detach/attach, fencing, and recovery procedures. Do not assume a persistent volume can be mounted simultaneously by multiple nodes unless the storage class supports it.

## 12. Synchronization and Coordination Across Multiple Instances

When multiple instances process concurrently, coordinated operations cannot rely on variables in one machine's RAM.

### Distributed Locks and Leases

Distributed locks or leases can elect one worker for a singleton task. Locks require TTLs/leases, renewal mechanisms, and handling of stalled clients. For critical resources, use fencing tokens or monotonically increasing versions to prevent a stale worker from writing after its lease expires and a new worker takes over.

Do not hold locks longer than necessary. If a task can be partitioned and made idempotent, queues/partitions are often simpler than a global lock.

### Leader Election

Tasks such as schedulers or controllers need a single leader at a time. Leader election must use a coordination mechanism with appropriate consistency, lease timeouts, and fencing. Never use an in-process static variable or local file as the sole leader mechanism across multiple instances.

### Cache Invalidation

Local caches can diverge across instances. If data changes must propagate quickly, use appropriate TTLs, event-driven invalidation, or a shared cache. Never assume every machine's cache is always identical.

### Connection Limits

With 20 instances each opening up to 50 database connections, potential connections reach 1,000. The database must have capacity or pools must be bounded across the fleet. Scaling compute can overload dependencies even while individual instances look healthy.

## 13. Rolling Out New Versions and Gradual Replacement

Immutable deployment enables creating new instances with a new image and replacing old instances under a controlled strategy.

### Rolling Replacement

Replace instances in groups:

1. Create new instances.
2. Wait for startup and readiness.
3. Add new instances to the backend pool.
4. Drain old instances.
5. Wait for in-flight requests/jobs to finish.
6. Terminate old instances.
7. Proceed to the next batch.

Ensure sufficient capacity remains while both old and new versions run concurrently.

### Blue/Green

Spin up a green fleet with the new version, validate it, and shift traffic from the blue fleet to the green fleet. Roll back by shifting traffic back to the old fleet while compatibility holds.

### Compatible Schema Migrations

During a rolling deploy, old and new versions may access the database simultaneously. Use the expand-and-contract pattern:

1. Add the new schema/fields in a way that keeps the old version working.
2. Deploy the new application capable of reading/writing the new structure.
3. Migrate or backfill data.
4. Verify all instances are using the new structure.
5. After a safe period, remove the old fields or structures.

Never run a destructive migration before all old instances have stopped using that schema.

## 14. Security in a Stateless Model

Replacement instances must receive the right permissions and secrets without carrying over stale credentials.

- Use workload identities or instance roles instead of long-lived keys in images.
- Scope IAM by action and resource; do not grant account-wide admin permissions.
- Fetch secrets at runtime via a secret manager over secure channels.
- Never write secrets to logs, public user data, image layers, or unprotected metadata.
- Rotate credentials and support multiple secret versions during rollouts.
- Use TLS for connections to databases, caches, queues, and object storage where supported.
- Separate identities by role: API, worker, migration job, and scheduler.
- When an instance is suspected of compromise, revoke its identity/sessions and replace the machine from a trusted image.
- Verify logs/audit trails are shipped off-instance so they are not lost when machines are deleted.

Statelessness makes machine replacement easier, but it does not automatically make a system secure. If every new instance receives an overly broad role or an image containing secrets, automated replacement simply reproduces the same risk.

## 15. Example Architecture: Replaceable API and Workers

An order-processing service consists of an API, workers, a database, a queue, a session store, and object storage.

~~~~mermaid
flowchart TD
    U[Client] --> LB[Load balancer]
    LB --> A1[API instance A]
    LB --> A2[API instance B]
    A1 --> DB[(Orders database)]
    A2 --> DB
    A1 --> SS[(Shared session store)]
    A2 --> SS
    A1 --> Q[(Durable queue)]
    A2 --> Q
    Q --> W1[Worker instance 1]
    Q --> W2[Worker instance 2]
    W1 --> DB
    W2 --> DB
    W1 --> OS[(Object storage)]
    W2 --> OS
    A1 -. workload identity .-> SM[Secret manager]
    A2 -. workload identity .-> SM
    W1 -. workload identity .-> SM
    W2 -. workload identity .-> SM
~~~~

How it works:

- The load balancer distributes requests to healthy API instances.
- Sessions live in a shared store; either API A or B can serve the same user.
- Orders are written to the database and events are emitted via an outbox/queue.
- Workers consume messages, process idempotently, and store output files in object storage.
- Each instance has a dedicated role-based identity.
- Logs, metrics, and traces are shipped to a centralized backend.
- The autoscaler can add or remove API/worker instances without migrating business data from old machines.

### What Happens When a Machine Is Deleted?

If API A is abruptly terminated:

- The load balancer detects failed health checks and stops sending new requests.
- In-flight requests may fail; clients retry with timeouts and idempotency keys.
- API B continues serving and reads sessions from the shared store.
- The autoscaler launches API instance C from the versioned image and config.
- C acquires identity and secrets, registers telemetry, and accepts traffic only when ready.

If Worker 1 is terminated after processing but before acknowledgement:

- The queue redelivers the message.
- Worker 2 or a new worker reprocesses it.
- Idempotency records prevent duplicate side effects.
- The message is acknowledged only after the result is durably persisted.

## 16. Process for Migrating a Stateful Application to Stateless

You do not need to rewrite the entire application at once. State types can be migrated in order of risk.

1. **Inventory state:** locate sessions, files, caches, local databases, jobs, and configs on each machine.
2. **Classify:** mark the source of truth, regenerable data, and data requiring an RPO.
3. **Externalize files:** move uploads and artifacts to object/shared storage; store references in the database.
4. **Externalize sessions:** use a shared store or appropriate tokens; align TTLs and schemas.
5. **Decouple jobs:** move long-running work into a durable queue and make workers idempotent.
6. **Standardize config/secrets:** pull from a config service and secret manager using workload identity.
7. **Package images:** build immutable, versioned images and deploy via IaC.
8. **Add lifecycle hooks:** startup/readiness probes, graceful shutdown, draining, and timeouts.
9. **Test replacement:** perform controlled instance termination in staging and observe recovery.
10. **Roll out gradually:** canary, rolling replacement, and load testing; monitor SLOs, data, and cost.
11. **Remove old local state:** only after verifying no consumers still depend on it.

### Definition of Done

- New instances can be created from images and configs with zero manual steps.
- New instances do not require fixed IPs or hostnames.
- Sessions and business data are not lost when replacing an instance.
- Request/job retries do not create duplicate transactions.
- Instances receive traffic only after passing readiness checks.
- Scale-in drains properly and does not drop in-flight work outside policy.
- Secrets and permissions are provisioned dynamically via identity.
- Centralized metrics/logs/traces and recovery runbooks are in place.

## 17. Testing Automatic Replaceability

A design is only considered stateless once machine replacement has been tested under representative conditions.

| Scenario | How to Test | Expected Outcome |
|---|---|---|
| Terminate an API instance | Delete an instance in staging under traffic | Load balancer removes failed machine; other backends continue serving |
| Scale-out | Increase load to trigger new instances | New machines bootstrap, become ready, and serve traffic without manual action |
| Scale-in | Reduce desired capacity | Instance drains, finishes requests, and terminates on schedule |
| Host/VM reboot | Controlled reboot | Service auto-starts, fetches config/secrets, and reaches readiness |
| Local disk loss | Replace instance or wipe ephemeral storage | Business data is preserved; caches regenerate |
| Slow shared store | Inject latency/failure in test environment | Timeouts and fallbacks are controlled; no retry storm |
| Queue redelivery | Stop worker before acknowledgement | Message is redelivered; business results are not duplicated |
| Database failover | Switch primary in test environment | Clients reconnect, retry safely, and data meets RPO |
| Secret rotation | Rotate secret version | New instances fetch new secret; old version is revoked on schedule |
| Rolling schema change | Run old and new versions concurrently | Both remain compatible throughout the transition |

Fault injection or game days can test losing an instance, node, or dependency. Perform these only in authorized environments and scopes; set blast-radius limits, observers, and abort conditions.

### Metrics to Monitor

- Time from instance creation to readiness.
- Bootstrap success rate and secret/config fetch errors.
- Healthy backend count, request rate, and latency during replacement.
- Session misses, request retries, and idempotency conflicts.
- Queue depth, oldest message age, redelivery rate, and dead-letter count.
- Database connection count, pool wait time, failover duration, and replication lag.
- Error rate, p95/p99 latency, and SLO/error budget.
- Repeated instance replacement rate, crash loops, or readiness failures.

## 18. Common Mistakes

**Moving sessions out while keeping uploaded files on the machine.** Users stay logged in, yet their files disappear when backends are replaced. Inventory the filesystem and temporary data as well.

**Using sticky sessions instead of shared state.** Affinity only routes requests; it does not protect sessions during instance restarts or failovers.

**Letting workers acknowledge messages before persisting results.** If a worker crashes after acknowledgement, work can be lost. Enforce commit-before-ack ordering and use idempotency.

**Retrying all errors indefinitely.** Retry storms can further overload dependencies. Use timeouts, backoff, jitter, retry limits, and circuit breakers.

**Using a shared store without designing HA.** A session store or cache can become a shared single point of failure. Set availability, capacity, backup, and recovery targets for the store itself.

**Embedding secrets in images or user data.** Images and metadata can be copied or read by many systems. Fetch secrets at runtime using workload identity.

**Provisioning new machines that still require manual setup.** This makes automatic replacement unreliable. Version images/configs and test repeatable bootstrapping.

**Scaling in without draining.** In-flight requests, WebSockets, or jobs can be severed. Coordinate readiness, deregistration delays, termination grace periods, and queue leases.

**Ignoring downstream load on dependencies.** Adding API instances can open hundreds of extra database connections or trigger a cache stampede. Bound pools and scale end-to-end capacity.

**Assuming stateless means backups are unnecessary.** Databases, object storage, queues, and session stores still hold critical state. Backups, replication, and restore tests aligned to RPO/RTO are still required.

## 19. Stateless Design Checklist

### State and Data

- [ ] Inventoried sessions, files, caches, jobs, configs, secrets, and business data.
- [ ] Source of truth resides outside the compute instance lifecycle.
- [ ] Shared files are stored in object/shared storage.
- [ ] Sessions use a shared store or protected token with an explicit lifecycle.
- [ ] Caches are regenerable and have appropriate TTL/eviction policies.
- [ ] Queues/jobs have retry, acknowledgement, idempotency, and dead-letter policies.
- [ ] Backups, replication, RPO/RTO, and restore tests are defined.

### Compute and Bootstrap

- [ ] Images are versioned, scanned, and released immutably.
- [ ] New instances bootstrap automatically from IaC/templates.
- [ ] Configurations are versioned and separated by environment.
- [ ] Secrets are fetched at runtime via workload identity.
- [ ] Instances do not depend on fixed IPs/hostnames.
- [ ] Service discovery or load balancers provide stable endpoints.
- [ ] No manual steps are needed to install or edit configuration after machine creation.

### Lifecycle and Readiness

- [ ] Startup, readiness, and liveness probes have clear semantics.
- [ ] Only ready backends receive traffic.
- [ ] Scale-in uses draining and graceful shutdown.
- [ ] Requests/jobs use timeouts, retries, and idempotency.
- [ ] Shared dependencies have capacity, HA, and monitoring.
- [ ] Headroom is provisioned to cover new instance startup time.

### Testing and Operations

- [ ] Terminated an instance in staging while serving traffic.
- [ ] Tested scale-out, scale-in, reboots, and dependency failures.
- [ ] Tested queue redelivery and duplicate side effects.
- [ ] Tested secret rotation and rolling schema migrations.
- [ ] Metrics/logs/traces are centralized and survive instance deletion.
- [ ] Runbooks, owners, abort conditions, and rollback procedures are documented.

## 20. Self-Check

1. What does statelessness mean at the compute level? Why can a stateless application still use a database and sessions?
2. Which data belongs in a database, object storage, queue, cache, and local ephemeral disk?
3. Why is session affinity insufficient to protect state when an instance is terminated?
4. A worker stops after writing data but before acknowledging the message. How should you design it so redelivery does not create duplicate transactions?
5. Why should idempotency keys be stored durably with a unique constraint?
6. Which components must be included in images and bootstrapping to provision new instances automatically?
7. How does workload identity enable new instances to receive permissions without copying access keys?
8. Distinguish startup, readiness, and liveness during machine replacement.
9. During scale-in, how must load balancer draining, application shutdown, and queue leases be coordinated?
10. Why can autoscaling compute overload a database or session store?
11. Describe a test procedure for terminating an API instance and verifying the service still meets its SLO.
12. Does stateless design eliminate the need for backups and disaster recovery? Explain.

Stateless design turns compute instances into resources that can be provisioned, replaced, or scaled on demand. Achieving this requires keeping business state in services with an appropriate lifecycle; making images, configurations, and identities reproducible; ensuring requests and jobs tolerate retries; and enforcing lifecycle controls with readiness, draining, and graceful shutdown. Once these conditions are verified through real machine-replacement testing, VMs, containers, and serverless workloads can recover resiliently without depending on any specific instance.
