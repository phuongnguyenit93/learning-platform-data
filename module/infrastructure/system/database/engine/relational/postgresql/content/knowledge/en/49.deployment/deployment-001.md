# Choosing Dedicated Servers, Containers, or Managed PostgreSQL Services

## 1. Choosing a PostgreSQL Deployment Model Based on Operational Needs

PostgreSQL can run on dedicated physical servers, virtual machines (VMs), containers, or provider-managed database services. These options can all run the same PostgreSQL engine, but differ in infrastructure control, data storage methods, update procedures, high availability (HA), backup, security, scalability, and the amount of operational work the team must manage themselves.

**Dedicated servers** typically provide extensive control over the OS, filesystem, storage, network, and PostgreSQL configuration. In return, the team is responsible for provisioning, hardening, monitoring, backup, patching, failover, and recovery.

**Containers** package PostgreSQL along with runtime dependencies for consistent deployment across environments. Containers help manage images, versions, and the deployment lifecycle, but do not automatically solve persistence, HA, backup, or data-directory upgrades. A PostgreSQL container still requires durable storage and proper database operational procedures.

**Managed PostgreSQL services** shift part of the infrastructure and database operations work to a cloud provider or platform vendor. The provider may manage provisioning, patching, backups, replicas, failover, and monitoring at the service level. Users trade away some control, depending on the provider's feature set, limits, pricing, and workflows.

There is no single best model for every system. The choice must be based on workload, availability/recovery objectives, compliance, data residency, operational skills, budget, development velocity, and tolerance for vendor dependency.

```text
                 PostgreSQL workload
                         |
                         v
              Define operational needs
                         |
          +--------------+---------------+
          |              |               |
          v              v               v
     Control and      Fast managed     Portable,
     customization    operations       reproducible runtime
          |              |               |
          v              v               v
   Dedicated host    Managed service   Container platform
          |              |               |
          +--------------+---------------+
                         |
                         v
             Validate HA, backup, restore,
             security, cost and portability
```

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish PostgreSQL on dedicated servers, VMs, containers, and managed services.
2. Understand which responsibilities belong to PostgreSQL, the OS, the container platform, and the provider.
3. Choose a model based on workload and production requirements.
4. Evaluate control versus operational burden.
5. Design persistent storage and filesystems for PostgreSQL.
6. Understand why container restart is not database recovery.
7. Evaluate Kubernetes StatefulSets/operators and failure modes.
8. Compare HA, failover, backup, and PITR across models.
9. Plan security, networking, secrets, and access control.
10. Manage minor updates, major upgrades, and extension compatibility.
11. Calculate TCO including compute, storage, backups, network, and staffing.
12. Evaluate performance, limits, scaling, and noisy neighbors.
13. Avoid vendor lock-in and build an exit strategy.
14. Choose models for development, staging, production, and regulated workloads.
15. Build checklists, decision matrices, and runbooks before deployment.

---

## 2. Four Layers to Separate When Evaluating Deployment

A PostgreSQL deployment has at least four layers:

1. **PostgreSQL engine**: SQL, transactions, WAL, MVCC, indexes, extensions, roles, and database configuration.
2. **Compute/operating system**: CPU, RAM, kernel, filesystem, storage drivers, process supervision, time synchronization, and OS security.
3. **Deployment platform**: physical server, hypervisor/VM, container runtime, Kubernetes, or managed database control plane.
4. **Operations**: monitoring, backup, restore, failover, upgrades, incident response, capacity planning, and access management.

### 2.1. PostgreSQL Does Not Manage the Entire Host

PostgreSQL manages data files, WAL, and database processes, but does not automatically patch the OS, replace failed disks, configure firewalls, or protect cloud credentials.

### 2.2. Containers Do Not Replace the Database Engine

A container image provides PostgreSQL binaries and a runtime environment. PostgreSQL still needs a data directory, WAL, durable storage, backups, and lifecycle management.

### 2.3. Managed Does Not Mean Everything Is Automated

The provider may automate certain tasks, but users still need to handle schema design, query tuning, roles, application compatibility, backup policy, restore testing, and capacity decisions.

### 2.4. Clarify Responsibilities Before Signing a Contract

For each control, explicitly document who owns it: the provider, platform team, database team, or application team. Items such as encryption keys, patch windows, failover, restore, and incident escalation need specific owners.

## 3. What Is a Dedicated Server?

In this lesson, dedicated servers include physical machines owned/rented by the organization and VMs directly managed by the team. PostgreSQL is installed as a service on the OS.

A server can:
- Run PostgreSQL directly on Linux/Windows Server.
- Run multiple PostgreSQL clusters/major versions on the same host.
- Use local NVMe, RAID, SAN, or network-attached block storage.
- Combine a primary with standbys on other hosts.
- Use dedicated monitoring, backup, and configuration-management agents.

### 3.1. Bare Metal

Bare metal is a physical server that does not go through a customer-managed hypervisor. It can provide better control over hardware, storage topology, and performance isolation, though provisioning, replacement, and capacity expansion are usually slower.

### 3.2. Virtual Machine

A VM provides virtualized compute/storage/network. It is easier to create snapshots/templates and change instance sizes than with physical hardware, though it may share host resources with other workloads.

### 3.3. Dedicated VM/Instance

A cloud provider may sell dedicated hosts or instances with a certain level of isolation. Read the exact guarantees regarding CPU, memory, storage, and tenancy.

### 3.4. Does Not Mean a Single Server

A self-managed deployment can still consist of a primary, standbys, backup hosts, proxies, and monitoring nodes. "Dedicated server" describes how compute is owned/operated, not the HA topology.

## 4. Advantages of Dedicated Servers

- Control over OS packages, kernel settings, and filesystems.
- Ability to choose storage devices, RAID/layout, and mount options.
- Ability to install extensions or custom PostgreSQL builds as needed.
- Deep tuning of database and OS configuration.
- Customization of networking, firewalls, routing, and security agents.
- Control over maintenance windows and upgrade sequencing.
- Ability to use specialized platforms/hardware for the workload.
- Less dependence on feature limitations of a managed provider.

### 4.1. Extension Flexibility

Some extensions or native libraries are not supported by managed providers. Self-managed deployments can install compatible packages or build according to instructions, but must take responsibility for security and upgrades.

### 4.2. Storage Control

You can choose appropriate local NVMe, RAID, filesystems, and I/O policies. This is useful for latency-sensitive workloads, but requires understanding the durability and failure behavior of each storage layout.

### 4.3. Configuration Control

You have permission to adjust many OS/database parameters. This control requires change management and benchmarking; not every kernel or database tweak improves performance.

### 4.4. Portability

A standard PostgreSQL cluster can be moved between hosts/platforms using backup/restore, replication, or logical migration. Portability still depends on extensions, OS architecture, locale, storage, and operational tooling.

## 5. Costs and Responsibilities of Dedicated Servers

Dedicated servers shift most operational work to the team:

- Provisioning and hardware/VM lifecycle.
- OS installation, hardening, and patching.
- PostgreSQL installation/configuration.
- TLS, certificates, firewalls, and identity.
- Backup, WAL archiving, and restore tests.
- Streaming replication, failover, and fencing.
- Monitoring, logs, alerting, and on-call.
- Capacity planning and storage expansion.
- Minor updates, major upgrades, and extension upgrades.
- Incident response, replacement, and disaster recovery.

### 5.1. Staffing Is Part of the Cost

Server price is not TCO. Account for DBA/SRE time, on-call coverage, maintenance, incident recovery, backup storage, and security reviews.

### 5.2. Every Layer Must Have an Owner

Without someone responsible for OS patching, backup verification, or failover, self-managed production can easily become a system that nobody truly operates.

### 5.3. Hardware Failure Is Your Responsibility

Disks, RAM, NICs, power supplies, or hosts can fail. You need spare capacity, a replacement process, replication, and a recovery plan.

### 5.4. Maintenance Windows

OS kernel updates, firmware updates, storage migrations, or reboots can cause downtime. HA topology and rolling maintenance need to be designed and tested.

## 6. VM or Bare Metal?

| Criterion | Bare Metal | VM |
|---|---|---|
| Hardware control | High | Lower, via hypervisor |
| Provisioning | Usually slower | Faster |
| Isolation | By hardware tenancy | By hypervisor/instance model |
| Storage | Can control devices directly | Depends on virtual/block storage |
| Resize | Usually requires hardware swap | Can change instance class |
| Portability | Hardware-dependent | Easier to template/migrate within platform |
| Noisy neighbor | Lower if dedicated | Depends on tenancy/host guarantees |
| Operations | Hardware lifecycle | Hypervisor/provider + guest OS |

### 6.1. Bare Metal Is Suitable When

The workload requires predictable hardware performance, specialized storage/networking, or the organization has mature data center/hardware operations.

### 6.2. VMs Are Suitable When

You need fast provisioning, capacity flexibility, automation, and the ability to recreate hosts. VMs are a common choice for self-managed PostgreSQL.

### 6.3. Virtualized Storage Needs Benchmarking

Do not assume all VM storage is slow. A cloud block volume can be faster and more durable than local disks depending on configuration. Measure latency, throughput, IOPS, queue depth, and fsync behavior.

### 6.4. Dedicated Tenancy Does Not Guarantee Database HA

A dedicated host can still fail. HA requires separate failure domains and a replication/failover strategy.

## 7. What Is a PostgreSQL Container?

A container packages PostgreSQL server binaries, libraries, configuration defaults, and entrypoint scripts into an image. The runtime launches the container with process isolation and filesystem/network namespaces.

A container typically has:
- Image tag/digest.
- PostgreSQL process as the foreground process.
- Environment/configuration.
- Mounted persistent volume for the data directory.
- Health/readiness checks.
- Network/service endpoint.
- Resource limits/requests if using an orchestrator.

### 7.1. An Image Is Not a Database Backup

An image contains binaries and filesystem layers, not a consistent backup of a running database.

### 7.2. Container Filesystems Can Be Ephemeral

If the data directory only resides in the writable container layer, container removal/replacement can cause data loss. Production requires persistent volumes or properly managed storage.

### 7.3. Container Lifecycle Differs from Database Lifecycle

Containers can be recreated while the database needs graceful shutdown, crash recovery, and durable data. An orchestrator does not understand all database semantics unless configured properly.

### 7.4. Image Tags Do Not Automatically Upgrade Data Formats

Changing an image from PostgreSQL 16 to 17 does not convert a major 16 data directory into major 17 format. A separate major upgrade procedure is required.

## 8. Advantages of Containers

- Consistent runtime environment across developer, CI, and production.
- Image versions/digests can be pinned and promoted.
- Easy to create ephemeral databases for tests.
- Process/filesystem/network isolation at the container level.
- Integration with deployment automation and orchestration.
- Ability to run sidecars/exporters/backup agents.
- Easy to scale applications and database test environments.
- Reduces "works on my machine" issues caused by package differences.

### 8.1. Reproducible Images

Pin a specific image tag and preferably a digest for production releases. Floating tags like `latest` can change contents between deployments.

### 8.2. Build Provenance

Use trusted official/vendor images, verify signatures/provenance if supported by the platform, and scan for vulnerabilities.

### 8.3. Ephemeral Environments

Containers are very useful for testing migrations, extensions, and application integration in CI. Ephemeral environments can be deleted after tests without affecting production data.

### 8.4. Consistent Tooling

You can standardize `psql`, `pg_dump`, exporters, and utility versions in the image/tooling pipeline, while managing client/server version compatibility.

## 9. Risks and Responsibilities of Containers

Containers do not automatically provide:
- Durable storage.
- Database-aware backup.
- Point-in-time recovery.
- Replication/failover.
- Safe major-version upgrades.
- Connection pooling.
- Data integrity validation.
- Disaster recovery across failure zones.

### 9.1. Persistent Volumes

You must mount a volume to the data directory, and define access modes, filesystem, ownership, durability, and behavior when a pod/container moves across nodes.

### 9.2. Graceful Shutdown

The runtime must send signals and allow PostgreSQL sufficient time to shut down. A timeout that is too short can force-kill the process, requiring crash recovery on the next startup.

### 9.3. Resource Limits

CPU throttling, memory limits, and OOM kills affect the database. A container with a low RAM limit can be terminated by the kernel even if the host still has free RAM.

### 9.4. Storage Latency

Containers do not make storage faster. Performance still depends on the underlying volume, network storage, filesystem, and host I/O.

## 10. Docker Compose for Development and Testing

A simple configuration can be used for local development:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app_user
      POSTGRES_PASSWORD: local_only_password
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_user -d app"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  pgdata:
```

This is an example for local development; do not use the sample password or this configuration as-is for production.

### 10.1. Named Volumes

Named volumes preserve data across container recreation on the same Docker host, but do not replace backups or off-host recovery.

### 10.2. Bind Mounts

Bind mounts can be convenient for local development, but file permissions, filesystem semantics, and host paths vary across OSes.

### 10.3. Port Binding

Bind the database port to loopback for local access. Avoid exposing PostgreSQL publicly just for development convenience.

### 10.4. Healthchecks

`pg_isready` checks whether the server accepts connections; it does not prove that the schema, replication, backups, or business queries are ready.

### 10.5. Version Pinning

In CI/production, pin major/minor/digest according to release policy. For example, `postgres:17` can still receive minor image updates under that tag; a clear promotion process is needed.

## 11. What Components Does Container Production Need?

A production deployment minimally needs to design:
- Image and release policy.
- Persistent storage.
- Secret injection.
- Network policy/TLS.
- CPU/memory resources.
- Startup/readiness/liveness behavior.
- Graceful shutdown.
- Backup/WAL archive.
- Monitoring/logging.
- HA/failover.
- Upgrade/rollback.
- Restore and disaster recovery.

### 11.1. Image Lifecycle

Patch base images and PostgreSQL minor releases according to policy. Do not rebuild/redeploy automatically without compatibility/release validation.

### 11.2. Runtime Identity

Run the process as an appropriate non-root user. Verify ownership/permissions on the mounted data directory.

### 11.3. Persistent Storage Lifecycle

Ensure volumes are not deleted along with workload objects due to cleanup policies. Define reclaim policies and snapshot retention.

### 11.4. Off-Volume Backups

Backups must reside in an independent failure domain. Snapshots in the same storage account/zone may not be sufficient for disaster recovery.

## 12. Kubernetes StatefulSet and PostgreSQL

Kubernetes provides primitives for running stateful workloads, but a StatefulSet alone is not a PostgreSQL HA solution.

Typical components include:
- StatefulSet with stable pod identity.
- PersistentVolumeClaim for data.
- Headless/ClusterIP Service.
- Secrets/ConfigMaps.
- PodDisruptionBudget.
- Resource requests/limits.
- Probes.
- Operator/controller or external database manager.
- Backup/restore tooling.

### 12.1. StatefulSet

StatefulSet manages pod identity and storage association. It does not inherently understand primary/standby roles or promote a replica properly.

### 12.2. PersistentVolumeClaim

A PVC requests storage from a StorageClass. Verify performance, zone topology, expansion, snapshots, and attach/detach semantics.

### 12.3. Operator

A PostgreSQL operator can orchestrate cluster creation, replicas, failover, backups, and upgrades. Quality and feature sets depend on the project/vendor/version.

### 12.4. Pod Restart Is Not Failover

Restarting the primary pod may just restart PostgreSQL on the same data volume. Failover requires identifying a healthy replica, promoting it safely, fencing the old primary, and updating routing.

### 12.5. PodDisruptionBudget

A PDB limits voluntary disruptions during certain operations; it does not protect against node, power, or network failures.

## 13. Kubernetes Probes and Shutdown Behavior

Misconfigured probes can cause the database to restart repeatedly or receive traffic too early.

### 13.1. Liveness

The liveness probe determines whether the container needs to be restarted. Do not use overly heavy queries or conditions dependent on downstream services that could cause a healthy database to restart under high load.

### 13.2. Readiness

Readiness determines whether the endpoint receives traffic. For a PostgreSQL primary/replica, readiness needs to evaluate the appropriate role and recovery state.

### 13.3. Startup Probe

A startup probe gives the database enough time for crash recovery, WAL replay, or data directory initialization before liveness checks begin.

### 13.4. Termination Grace Period

Give PostgreSQL time to shut down cleanly. Account for active transactions and checkpoint/shutdown time within orchestration limits.

### 13.5. Probes Do Not Replace Monitoring

Probes are health signals for the orchestrator; monitoring requires query latency, locks, replication, storage, backup, and application-level checks.

## 14. Kubernetes Storage and Failure Domains

Storage for PostgreSQL is often more critical than how quickly a container can be rescheduled.

### 14.1. Volume Topology

A zonal block volume may only attach within a single zone. Pod scheduling must respect topology and recovery capabilities if a zone is lost.

### 14.2. StorageClass

Verify IOPS/throughput guarantees, expansion, encryption, snapshots, reclaim policy, and CSI driver behavior.

### 14.3. Access Modes

ReadWriteOnce/ReadWriteMany semantics depend on the CSI/provider. Do not use a multi-writer shared filesystem for the PostgreSQL data directory if the PostgreSQL/storage architecture does not support it.

### 14.4. Filesystem Correctness

PostgreSQL relies on filesystem/storage guarantees for durability and WAL. Use a supported/tested storage class; do not assume every network filesystem is suitable.

### 14.5. Backups and Snapshots

A crash-consistent volume snapshot is not always equivalent to an application-consistent backup. Follow a PostgreSQL-aware backup tool or snapshot coordination procedure.

## 15. PostgreSQL Operator: When Should You Choose One?

An operator can reduce custom automation effort for:
- Cluster bootstrap.
- Replication setup.
- Failover/reconciliation.
- Backup scheduling.
- Restore workflows.
- Rolling minor updates.
- Major upgrade orchestration to the extent supported.
- Monitoring integration.

### 15.1. An Operator Is a Control Plane

The operator observes desired state and reconciles resources. You must understand its custom resources, controller version, upgrade path, and failure behavior.

### 15.2. Read the Support Matrix

Check supported PostgreSQL versions, extension support, storage backends, backup tools, replication modes, and Kubernetes versions.

### 15.3. No Operator Eliminates DBA Responsibilities

Schema design, query tuning, workload capacity, backup restore validation, security, and incident decisions still require database expertise.

### 15.4. Operator Upgrades Also Need Planning

CRD/controller upgrades can change behavior. Test operator upgrades and database upgrades as two separate lifecycles.

## 16. What Is Managed PostgreSQL?

Managed PostgreSQL is a service in which the provider manages part or most of the infrastructure/database operations. The service may be native PostgreSQL or a PostgreSQL-compatible service.

The provider may supply:
- Instance provisioning and storage.
- Automated backups and PITR.
- Managed standby/read replicas.
- Automated failover.
- Minor patching/maintenance.
- Encryption at rest/in transit.
- Monitoring, logs, and metrics.
- Network isolation/private endpoints.
- Scaling operations.
- Snapshot/restore and cross-region DR in certain tiers.

### 16.1. Managed Services Are Still Databases with Limits

There are connection limits, storage limits, IOPS/throughput ceilings, maintenance windows, parameter restrictions, and feature availability constraints.

### 16.2. The Provider Manages the Control Plane

Users interact via console/API/IaC. OS-level access and filesystem control are typically unavailable.

### 16.3. PostgreSQL-Compatible Is Not Always Full PostgreSQL

Some services have a different internal architecture or restrict extensions, SQL features, replication semantics, and connection behavior. Verify compatibility.

### 16.4. Managed Does Not Mean Zero Operations

Applications still need migrations, indexes, roles, query tuning, capacity planning, restore testing, and incident coordination.

## 17. Advantages of Managed PostgreSQL

- Reduces provisioning and hardware maintenance work.
- Built-in backup/PITR in many services.
- HA/read replicas with provider-supported workflows.
- Integrated monitoring/logging.
- Encryption, IAM, and private networking available on some platforms.
- Simpler compute/storage scaling.
- Clearer SLA/support/escalation paths.
- Easy integration with cloud IAM, secrets, monitoring, and deployment tools.

### 17.1. Focus on the Application

Small teams can spend more time on schema, query performance, and product features.

### 17.2. Standardized Operations

Providers can apply consistent patching, backup, and failover procedures.

### 17.3. Managed Backups

Automated backups and PITR reduce the chance of forgetting a backup schedule, though restore drills are still required.

### 17.4. Support Contracts

With an appropriate support tier, you can receive vendor assistance during incidents, hardware issues, or service events. Check scope and response-time commitments.

## 18. Limitations of Managed PostgreSQL

- No root/OS access.
- Only certain extensions/versions are supported.
- Some PostgreSQL parameters are locked or restricted.
- Maintenance windows and failover behavior are partially controlled by the provider.
- Pricing can rise significantly when adding storage, IOPS, replicas, backups, or network egress.
- May depend on proprietary APIs or provider-specific features.
- Export/migration can be time-consuming and costly.
- Observability may be limited compared to a self-managed host.
- SLAs have exclusions and do not guarantee all application-level recovery.

### 18.1. Extension Availability

Check the list of supported extensions and versions before selecting a provider. Do not assume a superuser can install any extension from source.

### 18.2. Parameter Groups

Some settings require a parameter group or reboot. Kernel/filesystem settings may not be adjustable.

### 18.3. Connection/Proxy Layer

Managed services may provide their own proxy/pooler. Understand transaction/session semantics, failover DNS, and connection draining.

### 18.4. Provider-Specific Behavior

Backup retention, replica lag, failover, maintenance, and upgrade workflows vary. Read the documentation for the exact service/tier/region.

## 19. Managed PostgreSQL and Shared Responsibility

Use a shared responsibility matrix:

| Item | What Managed Providers Usually Do | What Users Still Need to Do |
|---|---|---|
| Physical hardware | Procure, replace, operate | Choose tier/region and capacity |
| Host OS | Patch/harden per service | Track maintenance and compatibility |
| PostgreSQL process | Provision/restart per service | Config, query tuning, supported extensions |
| Backups | Automated backup/PITR feature | Retention choice, restore tests, recovery objectives |
| HA | Replicas/failover mechanisms | Choose topology/tier, test application reconnection |
| Network | Managed VPC/private endpoint options | Firewall, routes, TLS/client access |
| Identity | IAM integration options | Least privilege, role/grant design, secret lifecycle |
| Data/schema | Do not understand business semantics | Migrations, constraints, validation |
| Application | Not responsible | Drivers, pools, retries, consistency |
| DR | Some cross-zone/region features | DR design, exercises, and business sign-off |

Specific responsibilities vary by provider and service tier. Request contracts/documentation to confirm rather than relying on assumptions.

## 20. High-Level Comparison of the Three Models

| Criterion | Dedicated Server/VM | Self-Managed Container | Managed PostgreSQL |
|---|---|---|---|
| OS control | High | Host control depends on platform | Low |
| PostgreSQL config | Broad | Broad within image/runtime scope | Per parameter support |
| Extension flexibility | High | High if image/packages fit | Per allowlist/provider |
| Provisioning | Manual or IaC | Image + platform automation | Console/API/IaC |
| Persistence | Designed by team | PVC/volume managed by team/platform | Provider-managed storage |
| HA | Self-designed | Operator/replication tooling | Provider feature/tier |
| Backup | Self-built/selected tool | Self-integrated database-aware backup | Usually built-in |
| Upgrades | Self-operated | Image + database migration plan | Provider workflow/maintenance |
| Portability | High if standardized | Image easy to promote, storage still dependent | May have provider dependency |
| Operational burden | High | High to very high if Kubernetes | Lower, not zero |
| Cost model | Hardware/VM + staffing | Compute/storage/platform + staffing | Instance/storage/IOPS/features + egress |
| Best fit | Control/customization | Reproducibility/orchestration | Reduce self-managed infrastructure |

### 20.1. Containers Are Not a Fourth Option Independent of Servers

Containers run on VMs or bare-metal nodes. Comparing containers means comparing a deployment/runtime model; you still must choose the underlying infrastructure and storage.

### 20.2. Managed Services May Run Containers Internally

A provider may use containers/VMs inside its control plane, but users consume a service abstraction. What matters is the exposed contract and operations.

### 20.3. Models Can Be Combined

For example, a managed primary with self-managed analytics, or Kubernetes for applications alongside managed PostgreSQL for the database.

## 21. Choosing by Workload

### 21.1. Local Development

Containers are usually convenient: fast start/stop, version pinning, and disposable databases. Use dummy data, local secrets, and appropriate volumes.

### 21.2. CI Integration Tests

Containers/ephemeral databases help create a clean environment for each job. Test the exact PostgreSQL major version and extensions required.

### 21.3. Small Production Applications

Managed PostgreSQL often reduces operational burden if the feature set and cost fit. Self-managed VMs can also make sense when the team has operations capability.

### 21.4. High-Throughput OLTP

Benchmark storage, CPU, connection behavior, and latency. Bare metal/VMs can provide control; high-performance managed tiers can also fit if limits are met.

### 21.5. Specialized Extensions

Self-managed hosts/container images can be more flexible. Managed services are only suitable if the provider supports the required extension/version.

### 21.6. Regulated or Data-Residency Workloads

Choose based on jurisdiction, key ownership, auditing, network isolation, backup location, and provider compliance evidence. Self-managed is not automatically compliant; managed also does not automatically satisfy every policy.

## 22. Development, Staging, and Production Can Differ

You do not necessarily need to use the same hosting model for every environment, but compatibility must be maintained.

One pattern:
- Development: local container.
- CI: ephemeral PostgreSQL container/database.
- Staging: managed tier or VM close to production.
- Production: managed PostgreSQL or self-managed HA topology.

### 22.1. Version Parity

Keep PostgreSQL major and extension versions compatible. If production uses an extension missing from the local image, tests may miss behaviors.

### 22.2. Configuration Parity

Resource sizes do not need to be identical, but key settings, locale, encoding, auth, and connection semantics should be controlled.

### 22.3. Staging Data

Use a representative data volume/distribution while respecting privacy. Anonymize/mask production data when needed.

### 22.4. Production-Only Features

If production uses a managed proxy, IAM auth, or failover routing, staging should test these behaviors.

## 23. HA on Dedicated Servers

A self-managed topology typically includes:
- Primary.
- One or more streaming standbys.
- WAL archiving.
- Failover manager/orchestrator.
- Proxy/VIP/DNS routing.
- Fencing to prevent split brain.
- Monitoring and alerting.

### 23.1. Replication

Physical streaming replication sends WAL from the primary to the standby. Standbys can be synchronous or asynchronous depending on policy.

### 23.2. Failover

Promotion must ensure the old primary cannot continue accepting writes (fencing). If two primaries both accept writes, data divergence can occur.

### 23.3. Synchronous vs Asynchronous

Synchronous replication can reduce data loss at the cost of higher commit latency and dependence on synchronous standby availability. Asynchronous replication lowers latency but can lose writes not yet received by the replica during failover.

### 23.4. Failback

After failover, the old primary typically needs to be rewound/rebuilt/rejoined according to procedure; you cannot simply restart it and put it back into the topology.

### 23.5. Realistic Testing

Rehearse node failure, network partition, storage failure, stale replicas, and router updates. An HA diagram does not prove failover works.

## 24. HA in Kubernetes

Kubernetes provides scheduling and orchestration, but database failover requires a PostgreSQL-aware controller/operator.

### 24.1. Primary Election/Promotion

The operator must monitor cluster state, replication health, and select a standby with appropriate data to promote.

### 24.2. Fencing

Prevent the old primary from continuing to write after losing contact with the control plane. Fencing may require storage/network/process-level mechanisms.

### 24.3. Service Routing

Service selectors/endpoints must route to the new primary. Clients must reconnect and handle stale connections.

### 24.4. Pod Anti-Affinity and Topology Spread

Place replicas across different nodes/zones to reduce correlated failures. Storage zone constraints must be considered.

### 24.5. Node/Zone Outages

Test behavior when a node or availability zone fails. Persistent volumes may not immediately attach in another zone.

## 25. HA in Managed Services

Managed services typically provide:
- Multi-AZ standby.
- Automated failover.
- Read replicas.
- Managed proxies/endpoints.
- Automated maintenance/backup.

### 25.1. Failover Time

Failover duration depends on detection, promotion, storage/network, DNS/proxy, and application reconnection. Read the SLA and test it.

### 25.2. Endpoint Behavior

The endpoint may keep the same hostname while changing the IP/target. Connection pools must detect broken connections and reconnect properly.

### 25.3. Replica Lag

Read replicas can lag. Applications need routing policies and stale-read tolerance.

### 25.4. Provider Failover Does Not Replace Application Resilience

In-flight transactions can be disconnected. Applications need proper retry logic, idempotency, and clear transaction boundaries.

## 26. Backup and PITR by Deployment Model

| Model | Backup Strategy |
|---|---|
| Dedicated/VM | pgBackRest, Barman, WAL archive, or supported tool |
| Container/Kubernetes | PostgreSQL-aware backup operator/tool, off-cluster object storage |
| Managed | Automated snapshots/PITR and exports per provider features |

### 26.1. Physical Backup

A base backup plus WAL archive can support PITR. Tooling must ensure backup consistency and WAL continuity.

### 26.2. Logical Backup

`pg_dump`/`pg_dumpall` suits portability and object-level restores, but does not replace all PITR requirements.

### 26.3. Volume Snapshots

Snapshots require database/storage coordination to ensure consistency. Crash-consistent snapshots have recovery implications; do not treat every snapshot as application-consistent.

### 26.4. Backup Location

Keep backups outside the primary failure domain. Consider a separate account/project/region and access isolation.

### 26.5. Restore Tests

Test restoring the full cluster/database/objects, extension availability, roles, permissions, and application connectivity. Record the measured RTO.

## 27. RPO and RTO

Two critical metrics:

- **RPO (Recovery Point Objective)**: the maximum acceptable amount of data loss, measured in time or business events.
- **RTO (Recovery Time Objective)**: the maximum acceptable time to restore service after an incident.

### 27.1. RPO Affects Replication/Backup

Synchronous replication can reduce RPO for certain failure classes; asynchronous replication may have a non-zero data loss window. Backup frequency/WAL archiving also determines recovery points.

### 27.2. RTO Depends on the Restore Path

Restoring several TBs can take many hours even if backups succeeded. Measure restore time, network throughput, and extension/bootstrap steps.

### 27.3. Managed Services Do Not Automatically Guarantee Business RTO

A provider availability SLA is not necessarily a guarantee of data restore duration or application recovery time.

### 27.4. Choose Tiers Based on Objectives

Do not pay for expensive HA/DR tiers if the business does not need them, but do not choose a single-zone deployment when RPO/RTO forbids it.

## 28. Storage Design

Storage affects durability, latency, throughput, capacity, and recovery.

### 28.1. Data and WAL

PostgreSQL uses data files and WAL. They can be placed on the same volume or separated by design; separating volumes does not automatically improve performance if they share the same backend/IOPS pool.

### 28.2. Filesystem

Use a filesystem and mount configuration supported by PostgreSQL/the platform. Avoid arbitrarily choosing filesystem options with unsuitable durability semantics.

### 28.3. IOPS and Throughput

Measure workload random/sequential I/O, fsync latency, and queue depth. Provisioned IOPS can increase cost; choose based on benchmarks.

### 28.4. Capacity Headroom

Reserve headroom for database growth, indexes, WAL, temporary files, vacuum, index builds, and backup staging. A full disk can halt the database.

### 28.5. Encryption at Rest

Verify who manages encryption keys, rotation, snapshots, backups, and replicas. Volume encryption does not replace TLS for network traffic.

## 29. CPU and Memory Sizing

### 29.1. CPU

Size according to peak query concurrency, parallelism, vacuum, replication, and background jobs. More cores do not guarantee a serial query runs faster.

### 29.2. Memory

Consider `shared_buffers`, OS page cache, `work_mem`, `maintenance_work_mem`, and backend concurrency. `work_mem` can be allocated multiple times within a single query.

### 29.3. Container Limits

In a container, PostgreSQL may see memory/CPU limits different from host resources. Check cgroup-aware behavior and runtime configuration by version.

### 29.4. Managed Instance Classes

Compare CPU generation, memory ratio, burst credits (if any), storage bandwidth, and network limits. Do not compare only vCPU counts.

### 29.5. Benchmarking

Use a representative workload, data volume close to production, warm/cold cache scenarios, and realistic concurrency.

## 30. Network and Connection Management

PostgreSQL connections consume backend resources. Many application instances can generate a higher connection count than expected.

### 30.1. Connection Pooling

PgBouncer or a provider pooler can reduce backend connection counts. Choose session/transaction pooling based on application features and semantics.

### 30.2. Pool Limits

Calculate total pool size across all application replicas, workers, migrations, and admin tools. Set `max_connections` and pool caps intentionally.

### 30.3. TLS

Enable TLS per policy, verifying certificates and hostnames. Managed private endpoints may still require TLS depending on threat model/provider.

### 30.4. Network Locality

Place applications close to the database to reduce round-trip latency. Avoid making excessive unnecessary remote calls per request.

### 30.5. Firewall/Private Networking

Allow only authorized application, migration runner, monitoring, and admin networks to access the required ports. Do not expose 5432 publicly when unnecessary.

## 31. Security and Secrets

Regardless of model, database security requires:
- Least-privilege roles.
- TLS in transit.
- Encryption at rest.
- Network segmentation.
- Secrets manager.
- Credential rotation.
- Audit logging.
- Patch/vulnerability management.
- Backup access control.
- Data classification and retention.

### 31.1. Do Not Use Superuser for Applications

The application role only needs `SELECT`/`INSERT`/`UPDATE`/`DELETE` and appropriate execute privileges. A separate migration role handles DDL.

### 31.2. Secret Injection

In containers/Kubernetes, use a secrets manager or Kubernetes Secrets integrated with encryption/access policies. Do not bake passwords into image layers.

### 31.3. Managed IAM

IAM authentication can reduce static password management, but introduces token expiry, driver/proxy requirements, and provider-specific behavior.

### 31.4. Admin Access

Use bastion/VPN/private endpoints/zero-trust access per policy. Log audit trails for privileged actions.

### 31.5. Backup Credentials

Backup jobs need dedicated credentials with minimal permissions to read the database/WAL and write to the storage target.

## 32. Monitoring and Logging

A production deployment needs monitoring at both database and platform layers.

Database metrics:
- Connections/active sessions.
- Query latency and slow queries.
- Transactions/commits/rollbacks.
- Locks/deadlocks.
- Cache hits, buffer reads.
- WAL generation/checkpoints.
- Replication lag.
- Vacuum/XID age/bloat.
- Temp files.
- Backup/archive status.

Platform metrics:
- CPU/RAM/swap.
- Disk capacity/IOPS/latency.
- Network throughput/errors.
- Container restarts/OOM.
- Volume attach errors.
- Node/zone health.
- Provider events/maintenance.

### 32.1. Logs

Centralize PostgreSQL logs and platform events. Redact secrets, personal data, and sensitive query literals.

### 32.2. Alerting

Alert on SLOs/capacity: disk headroom, replica lag, backup failures, connection saturation, long transactions, WAL archive backlog, and repeated restarts.

### 32.3. Managed Metrics

Provider metrics may differ from PostgreSQL internal views. Combine both when permitted.

### 32.4. Observability Ownership

Define who receives alerts and who has authority to act. Alerts without an on-call owner do not create resilience.

## 33. Minor Updates and OS Patching

Minor PostgreSQL releases typically contain bug/security fixes within the same major line. OS/container base images also require security updates.

### 33.1. Self-Managed

The team selects package repositories, tests releases, schedules restarts/failovers, and updates each node.

### 33.2. Container

Build/promote a new image, test extensions, and restart according to the rollout plan. A new image does not automatically perform a major data migration.

### 33.3. Managed

The provider may patch during maintenance windows or via user-initiated actions. Check notifications, reboot behavior, and failover impact.

### 33.4. Change Records

Record before/after versions, release notes, backup evidence, affected nodes, downtime, and post-update checks.

## 34. Major Version Upgrades

Major upgrades change data/catalog compatibility and may require `pg_upgrade`, dump/restore, or a provider workflow.

### 34.1. Self-Managed Host/VM

Install target binaries, verify extension packages, run `pg_upgrade --check`, perform rehearsals, take backups, and execute cutover.

### 34.2. Container

Do not simply change the image tag. You need a target data directory and a migration method. Old/new StatefulSets/volumes or logical migration can be used.

### 34.3. Managed

The provider may offer in-place upgrades or snapshot/restore workflows. Check extension availability, parameter groups, replicas, downtime, and rollback constraints.

### 34.4. Test the Application

Drivers, ORMs, query plans, authentication, extensions, and background jobs must be tested on the target major version.

### 34.5. Rollback

Once the target receives writes, rolling back to the old major version requires reverse sync/reconciliation or a restore strategy. You cannot just swap the image/endpoint.

## 35. Extension Compatibility

Extensions depend on the PostgreSQL major version, shared libraries, OS/architecture, and potentially PROJ/OpenSSL/GDAL or other native libraries.

### 35.1. Self-Managed

You can install appropriate packages/builds, but must manage security patching and upgrade testing.

### 35.2. Container

Build images with extension packages compatible with the PostgreSQL base image. Pin package versions and rebuild for security fixes.

### 35.3. Managed

Use only extensions/provider versions on the supported list. You may have to choose a different service/major version if a needed extension is unavailable.

### 35.4. Upgrade SQL Objects

Installing binaries does not always update the SQL extension version. Use `ALTER EXTENSION UPDATE` as documented and check every database.

## 36. Scaling in Each Model

### 36.1. Dedicated Servers

Scale up via CPU/RAM/storage hardware; scale out via read replicas or sharding. Self-manage replication/failover and capacity.

### 36.2. Container Platform

Scaling application pods is easier than scaling database pods. PostgreSQL stateful scaling requires an operator, storage, and replication-aware workflows. Do not scale replicas by duplicating pods sharing the same data directory.

### 36.3. Managed Service

You can resize compute/storage, add read replicas, or enable HA per tier. Check downtime, limits, replica lag, storage growth, and cost.

### 36.4. Read Scaling Is Not Write Scaling

Read replicas offload reads; write capacity remains concentrated on the primary unless using sharding/multi-writer architectures.

### 36.5. Scale Triggers

Use latency, CPU, I/O, storage, connection pressure, WAL, and growth forecasts. Do not scale based on average CPU alone.

## 37. Availability Zones and Disaster Recovery Regions

### 37.1. Multi-AZ

Placing a replica/standby in another zone helps mitigate a single zone failure. Check storage/network topology and failover time.

### 37.2. Cross-Region DR

A replica/backup in another region protects against a region outage, but increases network cost and latency. Asynchronous replication has a non-zero RPO.

### 37.3. Backup Isolation

Backups should have access isolation and a different failure domain from the primary. Ransomware/credential compromise can affect backups if they share access permissions.

### 37.4. Regional Restore

Test restoring into the target region, including KMS keys, secrets, networking, DNS, application deployment, and extension availability.

### 37.5. Data Residency

Check the location of the primary, replicas, backups, logs, telemetry, and support access. Data residency is not just the primary database region.

## 38. Cost Model and Total Cost of Ownership

TCO must include:

- Compute/instance/host.
- Storage capacity and provisioned IOPS.
- Backup/snapshot/WAL archive storage.
- Network egress/inter-region traffic.
- Read replicas/standby/DR region.
- Monitoring/logging retention.
- Support contracts.
- Licensing if there are platform/vendor fees.
- Engineering/DBA/SRE time.
- On-call and incident costs.
- Migration and exit costs.

### 38.1. Self-Managed Cost

Hardware/VMs may be cheaper per unit, but you must add staffing, HA, backup tooling, replacement, security, and downtime risk.

### 38.2. Container Platform Cost

Add Kubernetes/control plane, worker nodes, persistent volumes, network load balancers, operators, backup tools, and platform engineering.

### 38.3. Managed Cost

Add instance, storage, IOPS, backups, replicas, proxies, cross-zone/region transfers, support, and overprovisioning headroom.

### 38.4. Cost per Workload Unit

Compare cost per transaction, per GB-month, per tenant, or per request under realistic workloads. Do not compare only the list price of a single instance.

### 38.5. Cost of Downtime

A cheap service that takes 12 hours to restore can be more expensive than a managed HA tier if business losses are high.

## 39. Vendor Lock-In and Portability

Managed services can create dependencies on:
- Proprietary APIs.
- IAM authentication.
- Custom extensions.
- Backup/export formats.
- Monitoring agents.
- Replication/CDC features.
- Failover/proxy endpoints.
- Parameter/service behaviors.

### 39.1. PostgreSQL Protocol Compatibility

A service using the PostgreSQL wire protocol does not mean full support for PostgreSQL semantics/extensions.

### 39.2. Portable Schemas

Keep schemas, SQL, and extensions within portable bounds when required. Isolate provider-specific integrations behind abstraction boundaries.

### 39.3. Export Paths

Test `pg_dump`/`pg_restore`, logical replication, or data exports into standard PostgreSQL. Measure duration and network cost.

### 39.4. Exit Strategy

Document target platforms, data export, roles, extensions, sequences, large objects, CDC cutover, and rollback. An untested exit plan may not work when needed.

### 39.5. Lock-In Can Be a Reasonable Trade-Off

Provider features can save significant engineering effort. What matters is understanding the dependency and its acceptable level.

## 40. Compliance and Regulatory Requirements

Verify:
- Data residency/jurisdiction.
- Encryption at rest/in transit.
- Customer-managed keys if required.
- Audit log availability/retention.
- Privileged access records.
- Backup location and retention.
- Data deletion/retention policies.
- Network isolation/private connectivity.
- Vulnerability/patch management.
- Provider certifications and audit reports.
- Subprocessor/support access.
- Incident notification commitments.

### 40.1. Self-Managed Is Not Automatically Compliant

Controlling the server yourself does not prove controls have been implemented or audited.

### 40.2. Managed Is Not Automatically Compliant

Provider certifications do not guarantee that your tenant/database configuration meets policy.

### 40.3. Shared Responsibility

Document provider controls and customer controls, maintain evidence, and review periodically.

### 40.4. Regulated Data in Non-Production

Mask/anonymize data and apply access policies to dev/staging/CI.

## 41. Disaster Recovery and Exit Readiness

A deployment model is only complete when you can recover from failures and exit it.

### 41.1. Restore Drills

Restore into a clean environment, verifying extensions, roles, application connectivity, and data integrity.

### 41.2. Failover Drills

Test primary loss, promotion, routing, application reconnection, and failback/rebuild.

### 41.3. Provider Outages

Define escalation, status channels, alternate regions, and manual recovery options.

### 41.4. Export Rehearsals

Practice exporting schema/data/global objects and importing into target PostgreSQL. Check sequence states, large objects, ownership, and extensions.

### 41.5. Recovery Documentation

Runbooks must include endpoints, service identities, data directories/storage, restore commands, keys, owners, and verification steps.

## 42. Decision Matrix by Requirement

| Requirement | Dedicated Server/VM | Self-Managed Container | Managed PostgreSQL |
|---|---|---|---|
| OS/kernel customization | Very suitable | Depends on host/platform | Limited |
| Custom extensions | Flexible | Flexible if image supports | Per provider |
| Local development parity | Possible | Very suitable | Less convenient |
| Ephemeral CI databases | Possible but heavy | Very suitable | Can be costly |
| Limited DBA/SRE staffing | Difficult | Difficult if self-managed | Usually better fit |
| Custom HA design | Flexible | Needs operator/tooling | Usually available by tier |
| Hardware-level tuning | High | Depends on host | Limited |
| Managed backup/PITR | Self-integrated | Self-integrated | Usually included |
| Data center/on-prem requirement | Suitable | Suitable | Only if provider/on-prem offering meets it |
| Predictable specialized I/O | High control possible | Depends on volume | Per service tier |
| Provider integration | Self-integrated | Self-integrated | Deeply integrated |
| Portability | High if standardized | Image portable, volume not necessarily | Needs evaluation |
| Operational ownership | Team | Team/platform | Shared with provider |

Use this table as a discussion tool, not as absolute scores. Specific features vary by vendor, tier, and version.

## 43. Real-World Selection Scenarios

### Scenario A: Developer Laptop

Choose a PostgreSQL container with a named volume or an ephemeral test database. Pin the major version and do not expose the port to public networks.

### Scenario B: Small Team, Standard Production Application

Managed PostgreSQL can significantly reduce operational burden. Verify extensions, backup/PITR, HA tier, region, and cost before deciding.

### Scenario C: Mandatory On-Premises

Dedicated servers/VMs or on-prem Kubernetes are suitable choices. The team must own hardware/OS, backup, replication, security, and DR.

### Scenario D: Specialized Native Extensions Required

Self-managed VMs/bare metal or custom container images are usually more flexible. Check build compatibility and security maintenance.

### Scenario E: Team Already Operates Kubernetes Well

Can use a well-evaluated operator, tested storage class, backup/restore automation, and on-call database expertise. A standalone StatefulSet is not enough.

### Scenario F: No On-Call DBA/SRE

A managed service is usually a safer starting point if provider SLA/support and features meet requirements. Someone must still own application/database operations.

### Scenario G: Very Latency-Sensitive and Specialized Workload

Benchmark bare metal/VMs, high-performance managed tiers, and storage options. Decide based on measured p95/p99, durability, and recovery behavior.

### Scenario H: Regulated Multi-Region

Compare provider compliance/data residency against self-managed control. Check backups, logs, keys, replicas, and support access as well.

## 44. Checklist Before Choosing a Provider or Platform

### Workload

- [ ] Read/write ratio and peak TPS measured?
- [ ] Data size, working set, and growth forecast established?
- [ ] Query p95/p99 and connection concurrency clear?
- [ ] Extensions, collations, and locale requirements listed?
- [ ] Batch/analytics workloads categorized?

### Availability and Recovery

- [ ] RPO/RTO approved by the business?
- [ ] HA topology/failover behavior clear?
- [ ] Backup retention and PITR window appropriate?
- [ ] Restore drill completed?
- [ ] Cross-zone/region DR needed?

### Security/Compliance

- [ ] Private network access/TLS?
- [ ] Encryption at rest and key ownership?
- [ ] IAM/roles/secret rotation?
- [ ] Audit logs and retention?
- [ ] Data residency/backup locations?
- [ ] Provider compliance evidence if needed?

### Operations

- [ ] Who patches OS/PostgreSQL/extensions?
- [ ] Who runs minor/major upgrades?
- [ ] Who receives alerts/on-call?
- [ ] Are metrics/logs sufficiently detailed?
- [ ] Are capacity and cost alerts in place?
- [ ] Are incident escalation/support paths defined?

### Portability/Cost

- [ ] Are SQL/extensions portable?
- [ ] Export/restore path tested?
- [ ] Does TCO include replicas, storage, egress, and staffing?
- [ ] Are there vendor-specific dependencies?
- [ ] Exit plan and migration duration estimated?

## 45. Runbook: Deploying Self-Managed PostgreSQL on a VM

1. Choose OS/version and VM size based on benchmarks.
2. Create a private network and firewall rules.
3. Create appropriate storage volumes/filesystems.
4. Install PostgreSQL packages from a trusted repository.
5. Create service/data directories with proper ownership.
6. Configure authentication, TLS, and least-privilege roles.
7. Set up WAL archiving and backup tooling.
8. Set up replication/HA if required.
9. Configure monitoring, logs, and alerts.
10. Run load tests and a restore drill.
11. Document versions, configuration, backup policy, and runbooks.
12. Go to production after failover/recovery has been rehearsed.

### 45.1. Do Not Expose the Default Port to the Internet

Open network paths only from authorized app/admin networks. Use private subnets/VPN/bastion per policy.

### 45.2. OS Maintenance

Establish a patch cadence, reboot procedure, and failover plan before applying updates.

### 45.3. Storage Verification

Verify mounts after reboot, filesystem permissions, free space, and alert thresholds.

### 45.4. Restore Test Before Production

Test restoring backups to another host, rather than just checking backup job exit codes.

## 46. Runbook: Deploying Containerized PostgreSQL

1. Choose a trusted image source.
2. Pin PostgreSQL major/minor version or digest.
3. Define data directory and persistent volume.
4. Create secrets outside the image.
5. Set up networking/private services.
6. Configure resources and graceful shutdown.
7. Configure appropriate startup/readiness/liveness probes.
8. Set up PostgreSQL-aware backup and WAL archiving.
9. Integrate monitoring/logging.
10. Test container restart, node loss, and volume reattachment.
11. Rehearse minor/major upgrades separately.
12. Verify restore and disaster recovery.

### 46.1. Do Not Use the Container Writable Layer as the Sole Storage

Container recreation can delete the layer. Use managed persistent storage.

### 46.2. Do Not Scale Replicas by Cloning the Data Directory

Each PostgreSQL instance needs proper cluster identity/data state. Replicas must be created via base backup/replication/operator workflows.

### 46.3. Do Not Change the Major Image Tag to Upgrade

Major upgrades require a migration method. Simple image replacement does not convert the data directory.

### 46.4. Container Health

Healthchecks must reflect required state without continuously restarting the database during recovery or heavy load.

## 47. Runbook: Choosing and Provisioning Managed PostgreSQL

1. Choose provider/service/region and PostgreSQL major version.
2. Check extensions, parameter support, and compatibility.
3. Select compute/storage tier based on benchmarks.
4. Define HA/Multi-AZ and read replicas.
5. Configure private networking, TLS, and identity.
6. Choose backup retention/PITR and encryption keys.
7. Set maintenance windows and patch policies.
8. Create roles/databases/schemas using least privilege.
9. Set up metrics/log exports and alerts.
10. Test application reconnection/failover behavior.
11. Execute a restore drill and measure RTO.
12. Document provider limits, support paths, cost, and exit plan.

### 47.1. Read Service-Specific Documentation

Do not assume details from one provider/tier apply to another. Confirm feature availability in the specific region/version.

### 47.2. Check Limits

Max connections, storage size, IOPS, replica count, backup retention, and maintenance restrictions can vary.

### 47.3. Endpoints and DNS

Understand endpoint behavior during failover/resize/restore. Check DNS caching and pooler reconnection.

### 47.4. Cost Alerts

Set alerts for storage growth, backup usage, replicas, IOPS, and network egress.

## 48. Common Mistakes

- Choosing a server by compute price while ignoring storage/backup/HA.
- Assuming a dedicated host means HA.
- Assuming a container image contains persistent database state.
- Storing the data directory in an ephemeral container layer.
- Using a multi-writer shared volume for multiple PostgreSQL primaries.
- Using only a liveness probe and restarting the database during recovery.
- Treating a StatefulSet as a PostgreSQL failover controller.
- Failing to test volume detach/reattach or zone failure.
- Putting passwords in Docker images or source control.
- Exposing PostgreSQL publicly without network controls.
- Failing to sum connection pools across all application replicas.
- Assuming a managed provider handles schema/query tuning.
- Assuming all extensions exist on a managed service.
- Assuming PostgreSQL-compatible means full compatibility.
- Failing to restore-test managed backups.
- Failing to understand asynchronous replica lag and read-after-write behavior.
- Changing the container image major version without upgrading the data directory.
- Lacking owners for patching, failover, or incidents.
- Omitting egress, backups, replicas, and staffing from TCO.
- Lacking a tested exit strategy from the provider.

## 49. Practice Exercises with Answers

### Exercise 1. What are the three deployment models in this lesson?

**Answer:** PostgreSQL on dedicated servers/VMs, PostgreSQL in containers/platforms, and managed PostgreSQL.

### Exercise 2. Does a dedicated server automatically guarantee HA?

**Answer:** No. HA requires replicas, failover, fencing, routing, and recovery procedures.

### Exercise 3. How does bare metal differ from a VM?

**Answer:** Bare metal runs directly on hardware; a VM runs via a hypervisor and virtualized resources.

### Exercise 4. Can a VM be self-managed PostgreSQL?

**Answer:** Yes. The team remains responsible for the guest OS, PostgreSQL, and operations within their scope.

### Exercise 5. Is a container image a database backup?

**Answer:** No. An image contains runtime/binaries; backups must protect database state and WAL according to the recovery plan.

### Exercise 6. Why do containers need persistent volumes?

**Answer:** A writable container filesystem can be deleted when the container is removed/recreated; volumes preserve the data directory across that lifecycle.

### Exercise 7. Does a named volume replace off-host backups?

**Answer:** No. Volumes only provide persistence within the scope of the storage host/platform; independent backups are needed.

### Exercise 8. What scenario is Docker Compose best suited for?

**Answer:** Local development and integration tests, though it can be used in some small deployments if operations are fully designed.

### Exercise 9. What does a `pg_isready` healthcheck prove?

**Answer:** That the server accepts connections under the check conditions; it does not prove business queries or backups/replication are healthy.

### Exercise 10. Does changing the PostgreSQL 16 image to 17 automatically major-upgrade the data?

**Answer:** No. It requires `pg_upgrade`, dump/restore, logical migration, or a supported workflow.

### Exercise 11. Does a StatefulSet automatically promote a PostgreSQL standby when the primary fails?

**Answer:** No. A PostgreSQL-aware operator/controller or failover tooling is required.

### Exercise 12. Why is a startup probe needed?

**Answer:** To give the database enough time for startup/crash recovery before the liveness probe intervenes.

### Exercise 13. What does an overly aggressive liveness probe cause?

**Answer:** A restart loop when the database is slow or recovering, making the situation worse.

### Exercise 14. Does a PVC guarantee storage suitable for PostgreSQL?

**Answer:** No. You must verify the CSI driver, durability, IOPS, latency, topology, and filesystem semantics.

### Exercise 15. Can a shared ReadWriteMany volume let multiple PostgreSQL primaries use the same data directory?

**Answer:** No. A PostgreSQL cluster data directory is not a shared multi-writer filesystem workload.

### Exercise 16. What does an operator do?

**Answer:** Reconciles desired state and can automate bootstrap, replicas, failover, backups, and upgrades per feature support.

### Exercise 17. Does an operator replace a DBA?

**Answer:** No. Query tuning, schema design, recovery validation, and business decisions still require an owner.

### Exercise 18. What is managed PostgreSQL?

**Answer:** A service where the provider manages part or most of the infrastructure/database operations.

### Exercise 19. Do managed services provide root access?

**Answer:** Usually not. Users interact via service APIs/console and provider-supported database privileges.

### Exercise 20. Does a managed service automatically optimize all SQL queries?

**Answer:** No. Query/schema/index design and workload tuning remain the user's responsibility.

### Exercise 21. Does PostgreSQL-compatible mean full PostgreSQL compatibility?

**Answer:** No. Check SQL semantics, extensions, transactions, replication, and unsupported features.

### Exercise 22. Why is a shared responsibility matrix needed?

**Answer:** To clearly define which controls the provider, platform, DBA, and application team are responsible for.

### Exercise 23. What is RPO?

**Answer:** The maximum acceptable level of data loss at the point of recovery.

### Exercise 24. What is RTO?

**Answer:** The maximum acceptable time to restore service after an incident.

### Exercise 25. Do automated backups replace restore drills?

**Answer:** No. You must actually restore and verify data, extensions, roles, and application connectivity.

### Exercise 26. How does a logical backup differ from a physical backup?

**Answer:** Logical backups export objects/data; physical backups protect cluster files/WAL and can support PITR depending on the tool.

### Exercise 27. Are volume snapshots always application-consistent?

**Answer:** No. They require database/storage coordination or a PostgreSQL-aware backup workflow.

### Exercise 28. Why can an asynchronous replica lose writes during failover?

**Answer:** The standby may not yet have received/replayed all WAL confirmed by the primary.

### Exercise 29. What is the trade-off of synchronous replication?

**Answer:** It can reduce data loss for certain failure classes, but increases commit latency and depends on standby availability.

### Exercise 30. Why must applications reconnect after failover?

**Answer:** Open sessions/transactions may be disconnected; the endpoint may switch to the new primary.

### Exercise 31. What problem does PgBouncer solve?

**Answer:** Connection pooling and reducing backend connection churn/overhead.

### Exercise 32. Why must total pool size be calculated across all app instances?

**Answer:** Each instance creates its own pool; total connections can exceed the database's `max_connections`.

### Exercise 33. Does encryption at rest replace TLS?

**Answer:** No. Encryption at rest protects storage; TLS protects traffic over the network.

### Exercise 34. Should secrets be baked into container images?

**Answer:** No. Use a secrets manager or runtime injection with access controls.

### Exercise 35. Does managed IAM auth completely eliminate credential lifecycle management?

**Answer:** No. Token expiry, IAM policies, driver/proxy support, and identity lifecycles still need management.

### Exercise 36. When is self-managed more suitable than managed?

**Answer:** When OS/storage/extension control, on-prem requirements are needed, or the team has sufficient operational capability.

### Exercise 37. When is managed usually suitable?

**Answer:** When wanting to reduce infrastructure operations and provider features meet compatibility, availability, recovery, compliance, and cost requirements.

### Exercise 38. Why must TCO include staffing?

**Answer:** Provisioning, patching, backups, failover, incidents, and on-call are real costs of self-managed systems.

### Exercise 39. Do read replicas increase write capacity?

**Answer:** No. They primarily offload reads from the primary.

### Exercise 40. Are containers an alternative to underlying VMs/bare metal?

**Answer:** No. Containers still run on host infrastructure; storage/compute failure domains still need design.

### Exercise 41. How do Multi-AZ and cross-region DR differ?

**Answer:** Multi-AZ protects against certain zone failures within a region; cross-region DR provides broader protection but has latency/cost/RPO trade-offs.

### Exercise 42. Why check extension availability before choosing a managed service?

**Answer:** Providers may only support a specific set of extensions/versions.

### Exercise 43. Why are image digests useful?

**Answer:** They pin the exact image artifact, preventing a tag's contents from changing unexpectedly.

### Exercise 44. Does a PodDisruptionBudget protect against all node failures?

**Answer:** No. It mainly limits voluntary disruptions according to policy.

### Exercise 45. Does a managed provider failover guarantee in-flight transactions succeed?

**Answer:** No. Sessions may disconnect; the application needs retry/idempotency handling.

### Exercise 46. Where does vendor lock-in come from?

**Answer:** Proprietary APIs, extensions, auth, backup formats, proxies, monitoring, and provider-specific behavior.

### Exercise 47. What should an exit strategy test?

**Answer:** Exporting/importing schema/data, roles, sequences, extensions, large objects, CDC cutover, timing, and application reconnection.

### Exercise 48. What must a good restore drill verify?

**Answer:** Database startup, existence of roles/extensions, data integrity, application connectivity, and measured RTO.

### Exercise 49. Why should staging resemble production?

**Answer:** To realistically test versions, extensions, configuration, data volume, storage, networking, failover, and migration behavior.

### Exercise 50. What are the most important criteria for choosing a deployment model?

**Answer:** Workload, RPO/RTO, security/compliance, extension/configuration needs, team operational capability, TCO, portability, and provider limits.

## 50. Deployment Decision Closing Checklist

| Group | Questions to Answer |
|---|---|
| Workload | Have CPU, memory, I/O, connections, growth, and latency been measured? |
| Control | How much OS, filesystem, extension, or kernel control is needed? |
| Platform | Physical, VM, container, or managed service? |
| Persistence | Which storage holds Data/WAL and what is its durability? |
| HA | Replica topology, failover, fencing, and routing? |
| Backup | Physical/logical backup, WAL archive, and retention? |
| Recovery | Have RPO/RTO been tested with a restore drill? |
| Upgrade | Who patches OS/PostgreSQL/extensions and major versions? |
| Security | TLS, encryption, keys, secrets, roles, and audit? |
| Network | Private endpoints, firewall, DNS, and connection pooling? |
| Observability | DB/platform metrics, logs, alerts, and on-call owner? |
| Compliance | Data residency, backup location, audit evidence, and support access? |
| Compatibility | Extensions, drivers, tools, and SQL behavior? |
| Cost | Compute, storage, IOPS, replicas, backups, egress, and staffing? |
| Portability | Have export/import and provider exit paths been tested? |
| Ownership | Is RACI clear among provider, platform, DBA, and application? |

## 51. Official References

- [PostgreSQL Documentation](https://www.postgresql.org/docs/current/) — installation, configuration, backup, replication, and administration.
- [PostgreSQL Installation](https://www.postgresql.org/docs/current/installation.html) — installation across platforms.
- [PostgreSQL Runtime Configuration](https://www.postgresql.org/docs/current/runtime-config.html) — server settings.
- [PostgreSQL Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — backup/PITR/recovery.
- [PostgreSQL High Availability](https://www.postgresql.org/docs/current/high-availability.html) — replication and failover concepts.
- [PostgreSQL pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html) — major-version upgrades.
- [Docker Official PostgreSQL Image](https://hub.docker.com/_/postgres) — image usage, environment variables, and persistence guidance.
- [Docker Storage](https://docs.docker.com/engine/storage/) — volumes and container storage.
- [Kubernetes StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/) — stateful workload identity/storage.
- [Kubernetes Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/) — PV/PVC/storage lifecycle.
- [Kubernetes Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/) — startup/readiness/liveness.
- [Kubernetes Pod Disruption Budgets](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/) — voluntary disruption controls.
- [PgBouncer](https://www.pgbouncer.org/) — connection pooling.
- [Cloud Native PostgreSQL](https://cloudnative-pg.io/documentation/) — PostgreSQL operator concepts and operations.
- [AWS RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html) — example managed PostgreSQL service documentation.
- [Azure Database for PostgreSQL](https://learn.microsoft.com/azure/postgresql/) — example managed service features/limits.
- [Google Cloud SQL for PostgreSQL](https://cloud.google.com/sql/docs/postgres) — example managed service operations.

Provider capabilities, service limits, supported extensions, backup semantics, and pricing vary by region/tier/version. Check current documentation and service contracts for your specific deployment before making production decisions.

## 52. Summary: Choosing Where to Run by Responsibility and Recovery

```text
Need full OS/storage control?
       |
   +---+---+
   |       |
  Yes      No
   |       |
   v       v
Self-managed?   Prefer provider-managed operations?
   |                   |
   v                   v
Bare metal/VM      Managed PostgreSQL
or container host       |
   |                    |
   v                    v
Can team own       Do features, limits,
backup/HA/patch?   RPO/RTO and cost fit?
   |                    |
   +---------+----------+
             |
             v
       Validate storage,
       security, upgrades,
       restore and exit path
             |
             v
       Production readiness
```

Key principles to remember:

1. **Dedicated servers maximize control and responsibility.** The team must own OS, PostgreSQL, storage, backup, HA, patching, and on-call.
2. **VMs and bare metal are compute/hardware choices.** Both can run self-managed PostgreSQL; dedicated hardware does not automatically create HA.
3. **Containers standardize the runtime, not the database lifecycle.** Persistent volumes, backups, failover, and major upgrades still require dedicated design.
4. **A StatefulSet is not a PostgreSQL HA controller.** Use a proven operator/tooling and test fencing, promotion, and storage recovery.
5. **Managed PostgreSQL reduces self-managed infrastructure.** Users remain responsible for schema, queries, permissions, application resilience, and restore validation.
6. **PostgreSQL-compatible does not guarantee full compatibility.** Verify extensions, SQL semantics, parameters, limits, and replication behavior.
7. **RPO/RTO must be rehearsed.** Successful backup jobs or provider SLAs do not prove business recovery has been achieved.
8. **Storage and networking heavily determine database performance.** Benchmark latency, IOPS, throughput, durability, and connection behavior.
9. **Security is required in every model.** TLS, encryption, least privilege, secrets, auditing, and network isolation still need configuration.
10. **TCO includes staffing and downtime.** Compare cost per workload unit, not just instance prices.
11. **Portability must be tested.** Export/restore, extension replacement, global objects, and exit time are real evidence.
12. **Choose based on team capability and business requirements.** A good model is one that meets workload, recovery, and compliance needs at an acceptable operational cost.

**One sentence to remember:** *Dedicated servers for control, containers for consistent runtimes, managed PostgreSQL for shared operations; choose based on workload, responsibility, recovery objectives, and total cost of ownership.*
