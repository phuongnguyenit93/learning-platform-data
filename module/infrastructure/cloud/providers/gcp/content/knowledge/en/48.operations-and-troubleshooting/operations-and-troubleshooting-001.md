# Production Readiness Review for GCP Workloads

A Java application can pass unit tests, deploy successfully to Cloud Run or GKE, and return HTTP 200 in staging—yet still not be ready to serve real users. For example, the API may lack alerts when error rates rise, Cloud SQL may never have been tested for recovery, a service account may have overly broad permissions, containers may not handle SIGTERM, quotas may be insufficient for peak hours, and no one may know who has authority to decide on a rollback.

**Production readiness review (PRR)** is an evidence-based evaluation process to determine whether a workload meets **functional, security, reliability, operability, performance, release process, and cost** requirements before receiving production traffic. A PRR is not just a one-time activity before launch day; major changes to architecture, traffic, data, and processes may also require re-evaluation.

This lesson belongs to the **Operations and Troubleshooting** chapter in the **CLOUD_PROVIDERS_GCP** module. The module explores Google Cloud from project organization, IAM, and VPC to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners know how to select services, protect resources, automate releases, and monitor reliability and costs. This lesson connects those concepts into a verification process before a workload is promoted to production.

## Learning Objectives

After this lesson, learners will be able to:

- Explain the scope and deliverables of a production readiness review.
- Build a **GO / CONDITIONAL GO / NO-GO** criteria matrix based on risk severity.
- Collect configuration evidence, test results, and ownership records.
- Evaluate Cloud Run, GKE, Compute Engine, Cloud SQL workloads, and integrated services.
- Verify SLIs/SLOs, error budgets, alerting, logging, tracing, and incident response.
- Verify IAM, networking, secrets, encryption, supply-chain, and data policies.
- Check capacity, quotas, autoscaling, backup/restore, and disaster recovery.
- Prepare canary, rollback, on-call, runbook, and cost guardrail procedures.
- Conduct a sample PRR for a Java/Spring Boot API on Google Cloud.
- Write a review record, assign remediation tasks, and issue an auditable decision.

## 1. What Is Production Readiness Really?

**Production readiness** is not a label attached to a resource after deployment. It is a demonstrated state proving that the system and operations team **can serve, detect failures, respond, recover, and control changes** under real-world conditions.

The Google Cloud Well-Architected Framework emphasizes the pillars of operational excellence, reliability, security, performance, and cost optimization. In practice, a PRR must link business objectives to technical evidence.

| Review Axis | Core Question | Typical Evidence |
|---|---|---|
| Business and ownership | Who is accountable, and who does the service serve? | Service catalog, RACI, business sign-off |
| Reliability | Are SLOs, failure domains, and HA/DR sufficient? | SLOs, architecture diagrams, failover tests |
| Observability | Can incidents be detected quickly and investigated? | Dashboards, alert tests, logs/traces |
| Security | Can only authorized identities access the right data? | IAM review, network tests, secret scans |
| Data | Can data be recovered and consistency preserved? | Backup policy, restore test, reconciliation |
| Performance | Can the system handle projected load and growth? | Load tests, p95/p99, quota baseline |
| Release | Are deployments safe and is rollback actionable? | CI/CD, artifact digest, canary drill |
| Operations | Are on-call, runbooks, escalation, and incident drills in place? | Rota, runbook, game days / drills |
| Cost | Who monitors and bounds spending? | Budget alerts, billing tags, forecast |

### Required Stakeholders

- **Application owner:** signs off on business outcomes.
- **Technical lead:** architecture, dependencies, compatibility.
- **SRE/on-call:** SLOs, alerting, incident management, and recovery.
- **Cloud platform/network:** project, VPC, quotas, clusters, connectivity.
- **Security/compliance:** IAM, data protection, policies, and exceptions.
- **DBA/data owner:** backups, integrity, database permissions.
- **Release manager:** canary, rollback, change windows.
- **FinOps:** cost, budgets, and cost accountability.

A PRR requires appropriate representation based on risk—not a meeting where every perspective is replaced by a generic checkbox.

## 2. Defining Risk Levels and GO/NO-GO Gates

A checklist without rules for handling failures creates a false sense of security. Before the review, agree on severity levels and approval authority.

### Sample Classification Levels

| Severity | Examples | Default Decision |
|---|---|---|
| P0 / Blocker | No recovery plan for critical data; exposed secret; no on-call owner for incident response | **NO-GO** |
| P1 / Critical | Canary cannot roll back; missing customer-facing error alerts; insufficient quota for known peak | **NO-GO**, unless a formal exception is approved by risk leadership |
| P2 / High | Latency dashboard lacks per-route breakdown; DR rehearsal does not cover every edge case | **CONDITIONAL GO** if risk and mitigation plan are approved |
| P3 / Improvement | Secondary documentation incomplete, resource optimization not yet prioritized | Can be **GO** with backlog item and deadline |

This is an **example matrix**, not a mandatory Google Cloud standard. Systems handling payments or sensitive data may need stricter thresholds; lower-criticality workloads may be accepted with different controls.

### Decision Rules

- **GO:** all mandatory requirements pass; residual risk is within approved thresholds.
- **CONDITIONAL GO:** no blockers remain; exceptions have an owner, deadline, interim mitigation, and risk approver.
- **NO-GO:** blockers remain, critical evidence is missing, or core safety conditions cannot be verified.

Never mark “PASS” without evidence. Use statuses: `PASS`, `FAIL`, `NOT TESTED`, `NOT APPLICABLE`, and `WAIVED WITH APPROVAL`. A `NOT TESTED` item is not equivalent to `PASS`.

## 3. Reference Scenario: Java API on Google Cloud

Consider an order processing service with the following architecture:

~~~mermaid
flowchart LR
  U[Web / Mobile] --> LB[HTTPS Load Balancer / entrypoint]
  LB --> API[Orders API Spring Boot / Cloud Run or GKE]
  API --> DB[(Cloud SQL PostgreSQL)]
  API --> PUB[Pub/Sub topic]
  PUB --> W[Order worker]
  W --> OBJ[(Cloud Storage)]
  API --> SEC[Secret Manager]
  API --> OBS[Logging / Monitoring / Trace]
  W --> OBS
  CICD[CI/CD + Artifact Registry] --> API
  CICD --> W
~~~

The diagram is conceptual. A Cloud Run service can be exposed directly with appropriate authentication and ingress settings; adding a load balancer depends on domain, WAF, TLS, traffic routing, and network boundary requirements. If the API runs on GKE, cluster/node/pod readiness and dedicated policies must also be included.

### Sample SLOs and Baseline Data

| Objective | Illustrative Value | Approver |
|---|---|---|
| Availability SLO | 99.9% eligible requests succeed, rolling 30 days | Product + SRE |
| Latency SLO | 99% eligible requests under 400 ms | Product + backend |
| RTO | 1 hour during major incident | Business owner |
| RPO | 15 minutes for order data under DR scenario | Business owner + DBA |
| Peak load | 700 requests/second, with bursts | Performance owner |
| Traffic growth | 30% over six months | Product/FinOps |

All numbers above are **practice assumptions**. RTO/RPO/SLO must reflect actual business needs; they are not automatically guaranteed simply because Cloud SQL or Cloud Run has its own SLA.

## 4. Preparation Phase: Inventory and Boundary

Before the PRR, establish a single source of truth for the workload:

- Project/folder/organization and billing account.
- Environment: production/staging/DR.
- Regions, zones, VPC, subnets, load balancers, and DNS.
- Compute: Cloud Run services, GKE deployments, or Compute Engine instances.
- Data: Cloud SQL, Firestore/Spanner, Cloud Storage, BigQuery, caches.
- Integration: Pub/Sub, Cloud Tasks, external APIs, hybrid connectivity.
- Service accounts, identity providers, and secrets.
- Artifact registry, image digests, CI/CD pipeline, and IaC repository.
- Ownership, on-call, compliance, service criticality, and release window.

### Dependency Graph

~~~mermaid
flowchart TD
  A[Orders API] --> B[Cloud SQL]
  A --> C[Payment provider]
  A --> D[Pub/Sub]
  D --> E[Worker]
  E --> F[Cloud Storage]
  A --> G[Secret Manager]
  A --> H[Identity provider]
  B --> I[Backups / PITR]
  A --> J[Monitoring / Alerts]
  E --> J
~~~

Label dependencies as **required**, **degraded mode**, or **optional**. If the Payment provider is unavailable, the API can either reject order creation or queue orders for later; that behavior must be accepted by the product owner. Do not test resilience by breaking a live production system without an approved plan.

### Minimum Deliverables

| Artifact | Contents | Owner |
|---|---|---|
| Service catalog | ID, criticality, team, and escalation | Application owner |
| Architecture | Diagrams, data flows, failure domains | Architect |
| Dependency register | API, DB, queue, identity, external | Tech lead |
| Security review | IAM, secrets, network, data classification | Security |
| SLO spec | SLI, goal, error budget, data source | Product + SRE |
| Runbook | Diagnose, mitigate, rollback, escalate | On-call |
| DR plan | RPO/RTO, backup/restore/failover | DBA + SRE |
| Test report | Load, resilience, security, functional | QA/Performance |
| Release plan | Canary, metrics gates, rollback | Release manager |
| Cost model | Budget, SKU, owner, forecast | FinOps |

## 5. Landing Zone, Organization, and Project Governance

A workload can run technically well yet fail governance if placed in a project with no billing owner, no organization policies, or Owner permissions granted to everyone.

### Organization/Project Checks

- Project ID follows naming conventions and sits in the correct folder.
- Billing account is attached and cost alert recipients are configured.
- APIs are enabled strictly as needed, not arbitrarily.
- Organization policies are verified for external IPs, service account keys, allowed locations, and resource restrictions.
- Labels/tags support ownership, environment, cost center, and policy enforcement.
- Quotas/limits and a quota increase plan cover peak demand.
- Cloud Audit Logs, log routing/retention, and audit access permissions are properly configured.
- IaC/state is protected and change procedures are recorded.

### Environment Isolation

Production and non-production must be separated by projects, permissions, data, and secrets in accordance with security requirements. Never allow staging tests to share a production database just for “convenient verification.” If using Shared VPC, clearly define the host project/service project, network responsibilities, and IAM boundaries.

### Evidence

Record project/folder IDs, key policy constraints, exception approvers, and verification dates. Do not copy full IAM policies containing personal identities into public documentation.

## 6. IAM and Workload Identity

**Least privilege** is the core principle: a service should receive only the permissions needed to perform its job; deployers, runtimes, and on-call responders should not share a single broad identity.

| Identity | Suggested Role-Based Permissions | What to Avoid |
|---|---|---|
| Runtime Orders API | Read specific secrets, connect to required services | Project Editor/Owner |
| Runtime Worker | Subscribe/publish to specific topics, write to authorized buckets | Organization-wide Storage Admin |
| CI/CD deployer | Deploy service and `actAs` the specific runtime service account | Using personal user accounts in pipelines |
| SRE on-call | View logs/metrics, scoped mitigation permissions | Shared service account keys |
| Security auditor | Read policies and audit logs within scope | Change-management privileges unless required |
| DBA | Manage instances/databases within scope | Broad permissions across all projects |

### Identity Checklist

1. Dedicated service account per workload; avoid default service accounts with historically broad permissions.
2. IAM bindings scoped as narrowly as possible: resource-level or appropriate project-level.
3. Separate **deploy** permissions from **invoke** and **runtime** permissions.
4. Use Workload Identity Federation for GKE/external CI where appropriate.
5. Avoid long-lived service account JSON keys; never embed keys in images or repositories.
6. Define audited emergency break-glass access granting and revocation paths.
7. Periodically audit unused permissions and inactive principals.
8. Use IAM Conditions or policy boundaries where appropriate.

**Network access does not replace authorization.** An API inside a VPC still needs caller authentication; TCP connectivity to Cloud SQL does not mean the database login should have read access to every table.

## 7. Network, Ingress, Egress, and TLS

### Mandatory Questions

- Does the API need public Internet access or only internal VPC/hybrid access?
- Are domain ownership, TLS certificates, DNS ownership, and renewal monitoring in place?
- Are external/internal load balancers, Cloud Armor, IAP, or Private Service Connect used according to requirements?
- Do firewall rules follow least privilege for both ingress and egress?
- Are Cloud NAT, Direct VPC egress/connectors, proxies, and Cloud SQL private IP paths properly routed?
- Are there overlapping CIDRs, routes to on-premises, or vendor IP allowlists?
- Has IPv4/IPv6 been tested when required by the product and clients?
- Do Google APIs require Private Google Access or another supported endpoint?
- Do all ingress/egress paths have logging, metrics, and owners?

### Connectivity Tests by Failure Layer

| Layer | Verification Method | Failure Signal |
|---|---|---|
| DNS | Resolve FQDN from the actual source | NXDOMAIN, wrong IP returned, stale TTL |
| Routing | Connectivity Tests, route table, flow logs | Unreachable or asymmetric path |
| Firewall | Rule evaluation and deny logs | TCP timeout or reset |
| TLS | Certificate chain, hostname, expiry, protocol | Handshake error |
| Identity | OIDC/mTLS/API auth, IAM | 401/403 |
| Application | Health/business endpoint | 5xx, timeout, incorrect data |

Do not use `curl -k` as TLS verification evidence; it bypasses certificate validation. Do not open firewall rules to `0.0.0.0/0` just to make a PRR test pass.

### Cloud SQL Connectivity Readiness

- Select private IP/connector/proxy according to architecture.
- Connect from the exact runtime service account and subnet.
- Verify DB user/role, TLS, connection pool, and query timeout.
- Evaluate pool size multiplied by maximum Cloud Run/GKE instance count, not just the pool size of a single instance.
- Test planned restart/failover scenarios and verify retry behavior.

## 8. Compute Selection and Failure Behavior Checks

### Cloud Run

Cloud Run manages the serverless infrastructure, but the application must be configured properly:

| Check | Meaning |
|---|---|
| CPU/memory | Sufficient for startup, GC, and peak requests |
| Concurrency | Requests/instance that the Java server handles stably |
| Min instances | Reduces cold starts if required by latency; incurs cost |
| Max instances | Caps autoscaling/cost but may reduce capacity |
| Timeout | Aligned with SLO, dependencies, and client retries |
| Startup/liveness probes | Application starts up and recovers properly |
| SIGTERM/shutdown | Completes in-flight requests and releases resources when possible |
| Ingress/auth | Do not expose publicly if unnecessary |
| Traffic splitting | Enables canary deployments and revision rollback |
| Runtime identity | Dedicated service account, no static keys |

Cloud Run documentation notes that min instances are kept warm to reduce cold starts, but they can still be restarted and are not guaranteed never to drop below the target during all failures. Do not treat min instances as a substitute for multi-region DR or load testing.

**Concurrency must be benchmarked.** Java applications have their own thread pools, connection pools, and memory limits; raising concurrency can reduce cost or cause OOMs/degraded p95 latency. Do not copy a fixed value across all services.

### GKE Standard or Autopilot

Check:

- Cluster mode/version/release channel and upgrade plan.
- Node pools or Autopilot compute classes/requests, regional/zone placement.
- Deployment replicas and readiness/liveness/startup probes.
- PodDisruptionBudget (PDB) for multi-replica workloads that must tolerate voluntary disruptions.
- Requests/limits, Horizontal Pod Autoscaler, or appropriate scaling configuration.
- Pod scheduling, topology spread, and anti-affinity when HA is required.
- Graceful termination, `terminationGracePeriodSeconds`, and `preStop` if appropriate.
- Persistent volumes/stateful sets, backups, and DR.
- NetworkPolicy, workload identity, secrets, and image policies.
- DaemonSet/sidecar/logging overhead, quotas, and capacity.
- GKE upgrades, maintenance windows, and maintenance schedules.

A PDB primarily controls **voluntary disruptions** such as evictions during maintenance; it does not provide absolute protection against node failures or regional outages. Readiness probes tell the platform when a Pod can receive traffic; liveness probes should not check every external dependency in a way that restarts all Pods when a database has an outage.

### Compute Engine

Check:

- Managed Instance Groups when autoscaling and self-healing are required.
- Health checks and restart/recreate behavior.
- Shielded VMs, OS patching, and baseline images.
- VM service accounts, metadata, firewalls, and disk encryption.
- Persistent disk snapshots/backups, app state, and graceful shutdown.
- Multi-zone design if required by the SLO.
- Immutable instance templates, rolling updates, and rollbacks.

A VM running steadily in staging does not prove sufficient capacity when a zone fails or during a simultaneous fleet deployment.

## 9. Java/Spring Boot: Startup, Readiness, Liveness, and Shutdown

A Java API must distinguish between **the process is alive** and **the service is ready to receive traffic**. For example, Spring Boot uses Actuator health probes.

### Sample Actuator Configuration

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
      add-additional-paths: true
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s
~~~

This configuration merely illustrates Spring Boot properties in supported versions. It requires the `spring-boot-starter-actuator` dependency; the Prometheus endpoint requires the corresponding registry and protection from public exposure when necessary. Setting `exposure.include` broadly can expose endpoints if network/auth protections are absent. Adjust according to framework version and deployment target.

Commonly used endpoints:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

With `add-additional-paths`, Spring Boot can expose `/livez` and `/readyz` on the main server port depending on version/configuration. **Verify the actual endpoints** before configuring load balancers or Kubernetes probes.

### Readiness Probe on GKE

~~~yaml
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
      terminationGracePeriodSeconds: 30
      containers:
        - name: api
          image: REGION-docker.pkg.dev/PROJECT/REPO/orders-api@sha256:IMAGE_DIGEST
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
            failureThreshold: 3
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
~~~

This is a **practice fragment that must be customized** for your image, CPU/memory, health semantics, and application version. In Kubernetes, `terminationGracePeriodSeconds` is a **Pod spec** property; the example places it under `spec.template.spec` (at the same level as `containers`), not inside a container. Avoid using sample manifests directly in production without schema validation.

A liveness probe that calls an external dependency can cause a restart storm during network or database failures. Design liveness mainly around process health, and readiness around ability to serve traffic; when deciding whether a dependency should affect readiness, avoid taking all replicas out of rotation for a single shared outage.

### Graceful Shutdown

- Stop accepting new requests.
- Complete in-flight requests/transactions within configured limits.
- Flush logging/metrics/traces where appropriate.
- Safely close JDBC pools and HTTP clients.
- Workers acknowledge messages **after** processing completion is confirmed.
- Respect the runtime's timeout/termination window.

Test shutdown in staging via controlled rolling restarts or scale-downs; inspect retry/idempotency behavior and duplicate messages rather than merely observing that the container exited.

## 10. Data: HA, Backup, PITR, and Restore Are Not the Same Thing

### Cloud SQL

| Capability | Purpose | Does Not Replace |
|---|---|---|
| High availability | Recover from certain zone/instance failures | Backup/restore or regional DR |
| Automated backups | Create recovery points on a schedule/policy | Continuous replication |
| Point-in-time recovery (PITR) | Recover to a point in time within retention window | Prevention against all security errors |
| Read replica | Scale reads; depending on design can support DR | Backups, primary HA, or zero-lag guarantee |
| Cross-region replica/backup | Support DR scenarios per product capabilities | Tested failover/failback runbook |

Cloud SQL HA helps mitigate supported failures but does not automatically provide DR for all regional outages or ransomware. For PostgreSQL, verify backups, PITR, retention, and restore permissions, and **rehearse an actual restore** to a test instance.

### Data Checklist

1. RPO/RTO approved by the business owner.
2. Data volume, growth rate, and transaction volume measured.
3. Backup policy/PITR enabled where needed, with appropriate retention.
4. Backups and encryption keys remain usable during recovery.
5. Test restore from an actual backup and validate data after restoration.
6. DB roles, schema migrations, extensions, sequences, and connection strings verified.
7. Recovery plan exists for accidental database deletion, corruption, or revoked KMS key access.
8. Data migration/cutover validates consistency, avoiding uncoordinated dual-writes.
9. Other services such as Cloud Storage, Firestore, Spanner, and Bigtable have tailored backup/versioning policies.
10. Never treat replication as a backup, since bad writes or deletions replicate to standbys as well.

### Pub/Sub, Cloud Tasks, and Async Processing

- Subscribers have ack/nack, retry, and dead-letter policies.
- Consumers are idempotent because duplicate deliveries can occur.
- Measure queue depth, oldest unacked message age, and processing latency.
- Payload schemas are versioned and backward compatible.
- Ordering requirements and subscription limits are defined.
- Recovery path exists when workers are down or downstream dependencies fail.
- Never ack before processing succeeds and expect Pub/Sub to guarantee business completion.

## 11. SLI, SLO, Error Budget, and Alerting

A CPU dashboard does not directly answer whether users are receiving good service.

### Defining SLIs

Orders API example:

~~~text
Availability SLI = successful eligible requests / total eligible requests

Latency SLI = requests below agreed latency threshold
              / total eligible requests
~~~

**Eligibility** must be clearly defined: whether client 4xx responses are counted, whether health probes are excluded, and how timeouts are recorded. For request-based SLOs, the error budget is the allowable fraction of bad requests within the compliance period.

If the availability SLO is 99.9%, the allowable error ratio is 0.1%. Do not automatically assume 0.1% equals a fixed number of downtime minutes when traffic volume fluctuates.

### Minimum Production Dashboard

| Dashboard/Widget | Question Answered |
|---|---|
| Request rate, errors, latency | How many users is the system serving and at what quality? |
| SLO compliance/error budget | Is the service staying within its targets? |
| Per-route p95/p99 | Which endpoint is degrading? |
| CPU/memory/instance count | Is the service saturated or scaling abnormally? |
| DB connections/CPU/replication/locks | Is the data dependency having issues? |
| Pub/Sub backlog/retries/dead-letter | Is the async pipeline accumulating backlog? |
| External dependency errors | Are errors internal or from a vendor? |
| Deployment/incident markers | Which change preceded the incident? |

### Alerting

You should have:

- **Customer-impacting** alerts: error rate, SLO burn rate, latency, availability.
- **Capacity** alerts: quota/saturation, DB storage, connection pool, queue backlog.
- **Integrity** alerts: failed backups, stuck data pipeline jobs, data discrepancies.
- **Security** alerts: credential misuse, audit anomalies per policy.
- **Operational** alerts: missing telemetry or lost heartbeats on critical services.

Every alert needs a severity, owner, notification channel, and runbook. Test alerting channels before launch; a policy that exists on paper but sends alerts to an unmonitored mailbox is a **FAIL**.

### Synthetic Monitoring

Uptime checks can verify public or private endpoints per product capabilities, but they do not replace transaction-level probes. For authenticated APIs, create a narrowly scoped synthetic test account and avoid embedding production tokens in public configurations.

## 12. Logging, Tracing, Audit, and Sensitive Data

Java applications should emit structured logs to enable filtering by service, event, route, status, and trace context.

~~~json
{
  "severity": "ERROR",
  "service": "orders-api",
  "event": "order.create.failed",
  "route": "/v1/orders",
  "error_type": "DATABASE_TIMEOUT",
  "duration_ms": 870,
  "correlation_id": "synthetic-test-abc"
}
~~~

This example intentionally omits emails, order IDs, bearer tokens, or customer payloads.

### Trace Context

- Attach trace ID and span ID from the active context.
- Propagate W3C `traceparent` over HTTP/gRPC when supported by the framework.
- If logs are emitted via Cloud Run stdout, special fields `logging.googleapis.com/trace` and `logging.googleapis.com/spanId` must follow the required format for Cloud Logging correlation.
- Traces appear complete only when spans are created, sampled/exported, and ingested; a trace ID in logs does not guarantee the trace exists.
- Monitor OTel Collector/exporter errors, sampling rates, and ingestion costs.

### Retention and Security

- Log buckets are placed in appropriate locations with proper retention.
- IAM/log views restrict who can read log data.
- Audit logs are not disabled outside approved policy.
- Log exclusions do not strip logs needed for incident investigation.
- A response procedure exists if secrets or PII leak into logs.
- Do not use request IDs, user IDs, or raw URLs as high-cardinality metric labels.

## 13. CI/CD, IaC, and Supply-Chain Readiness

### Sample Release Pipeline

~~~mermaid
flowchart LR
  A[Commit / PR] --> B[Static checks + unit tests]
  B --> C[Dependency + image scan]
  C --> D[Build immutable artifact]
  D --> E[Sign / attest / publish artifact]
  E --> F[Deploy staging]
  F --> G[Integration + load + security tests]
  G --> H[Change approval]
  H --> I[Production canary]
  I --> J{SLO/error gate}
  J -->|Pass| K[Progressive rollout]
  J -->|Fail| L[Rollback]
~~~

Organizations do not have to use the exact tools in the diagram, but **evidence of builds from trusted source, testing, and rollback capability** must be clear.

### Checklist

- Artifacts/images are referenced by digest or immutable version, not just `latest`.
- CI runs tests, SCA/dependency scans, and secret scanning.
- Build, deploy, and runtime accounts have separate scopes.
- IaC (Terraform/GitOps) undergoes review and drift checks.
- Secrets are injected via Secret Manager or an approved secret management mechanism; never committed to Git.
- Database migrations are version-compatible while a canary runs two revisions concurrently.
- Deployment scripts are safe to re-run (idempotent).
- Plans exist for rolling back images/configs and handling data after schema migrations.
- All production changes have an audit trail and owner approval.

### Rolling Updates Are Not Enough

If a new release changes the database schema in a way the previous version cannot read, rolling back the container image can still fail. Use **expand–migrate–contract** or a dual-version compatible migration strategy so canary and rollback remain safe. Identify the point of no return once data is written in the new schema.

## 14. Performance, Capacity, and Quotas

### Load Testing Must Be Representative

Document:

- Requests/second, endpoint distribution, payload size.
- Read/write ratio and dataset size.
- Concurrency and connection pool behavior.
- Peak/burst, ramp-up, soak test, and cooldown.
- Production-like dependencies or clearly bounded stubs.
- p50/p95/p99 latency, CPU, memory, GC pauses, DB locks, error rate.
- Input data and source network region generating the traffic.
- SLOs and test stop criteria.

Do not use load test results against `/health` alone to conclude an API can sustain 700 requests/second.

### Capacity Before Opening Traffic

| Layer | Checks |
|---|---|
| Cloud Run | Min/max instances, concurrency, CPU, memory, quotas |
| GKE | Node/pod resources, autoscaling, image pull, topology |
| Compute Engine | Instance group capacity, quotas, regional availability |
| Cloud SQL | CPU, RAM, connections, storage, IOPS, read replicas |
| Pub/Sub | Throughput/quotas, backlog, subscriber capacity |
| Cloud Storage | Request rate, object layout, transfer costs |
| Network | Load balancer quotas, Cloud NAT ports, egress, DNS |
| Monitoring | Metric cardinality, log ingest quotas, alert delivery |

If a workload scales to 200 instances and each opens a pool of 20 DB connections, the theoretical upper bound can reach **4,000 connections**, excluding admin/worker/replica connections. This is an illustrative calculation, not a prediction of actual connections; configure caps and proxying/pooling within DB limits.

### Degradation Testing

- A dependency returns 5xx/timeouts.
- A database read replica slows down.
- Pub/Sub consumers slow down.
- An instance/pod restarts while serving traffic.
- DNS or an external API degrades.
- Quotas/autoscaling hit their limits.

Failure experiments must run in sandbox/staging with rollback procedures; do not disrupt production to gather PRR evidence without formal approval.

## 15. Backup, Disaster Recovery, and Business Continuity

**High availability** addresses certain infrastructure faults; **backup/PITR** restores data; **disaster recovery** addresses large-scale incidents against RTO/RPO targets. These three mechanisms do not replace one another.

### Scenarios to Evaluate

1. Bad deployment spikes 5xx errors.
2. A zone becomes unavailable.
3. A region suffers severe impact.
4. Database is deleted or corrupted.
5. Secret Manager access or CMEK key is disabled.
6. Ransomware or credential compromise.
7. External payment provider suffers an outage.
8. Loss of logging/monitoring access or network connectivity.
9. IaC accidentally alters firewall or IAM rules.
10. Primary on-call responder is unreachable during an incident.

### Recovery Evidence

- A recent backup exists within the retention window.
- A **completed** restore test exists—not just “backup succeeded.”
- Measured restore duration meets RTO or has an approved interim workaround.
- Data loss observed during testing is verified against RPO.
- Identity/IAM/KMS/secret and network dependencies are also recoverable.
- Documented failover/failback procedures and communication plan exist.
- DR drills are scheduled to repeat periodically.

### Do Not Extrapolate Blindly from SLAs

SLAs for Cloud SQL, GKE, or Cloud Run carry specific scopes and conditions. End-to-end SLOs also depend on application code, databases, identity, DNS, networking, and third parties. A PRR evaluates the **entire transaction path**, rather than arbitrarily multiplying or adding vendor SLA figures.

## 16. Production Security: Defense in Depth

### Common Required Controls

- Threat modeling across data flows and trust boundaries.
- Least-privilege IAM; audit overly broad permissions and service account keys.
- TLS/mTLS where required; monitor certificate expiration and private CAs.
- Network segmentation, firewalls, and ingress/egress restrictions.
- Cloud Armor or WAF aligned with the threat model of public services.
- Secret Manager, rotation, and database credential protection.
- Encryption at rest, CMEK when required by the organization; key rotation/recovery runbooks.
- Vulnerability scanning, patching policies, base image and dependency updates.
- Artifact provenance/signing/attestations and image admission policies if applicable.
- Cloud Audit Logs, threat detection, and incident escalation.
- Data classification, residency, retention, DLP, and backup isolation.
- Negative tests: unauthorized users actually receive 403; services cannot read out-of-scope buckets.

### Practical Verification Questions

- If a service account token leaks, can that principal delete backups or KMS keys?
- If a container is compromised, does network egress allow exfiltrating data to arbitrary Internet hosts?
- If a CI token expires, does the pipeline fail closed and alert?
- If a certificate nears expiration, who gets paged before customers are affected?
- If a CMEK key is disabled, is there a safe recovery runbook?

You do not need to answer “yes” to every Google Cloud security product; you must prove **risks have been addressed** with appropriate controls.

## 17. FinOps and Quota Readiness

A workload can suffer an outage due to hitting quotas or having billing disabled. Conversely, an unbounded autoscaler can trigger runaway costs.

### Items to Review

- Budgets and alerts by project/environment/cost center.
- Billing export for SKU and unit-cost analysis.
- Designated owners receive alerts and have authority to act.
- Quota headroom for peak traffic and failover.
- Cost of HA, warm standby, min instances, logs, and DR.
- Labels/tags and shared cost allocation rules.
- Storage lifecycle/retention and data transfer egress.
- SKU impact when scaling or deploying across regions.
- Cleanup policies for test resources, old revisions, unattached disks, and idle IPs.

**Budget alerts do not automatically stop spending.** If hard guardrails are needed, design quotas/limits and policies with reliability impact in mind; do not arbitrarily set max instances too low and cause peak traffic rejection.

### Unit Economics

Example:

~~~text
Cost per 1,000 successful requests
  = eligible monthly operating cost
    / successful requests in month
    × 1,000
~~~

Include fair cost allocations: compute, database, networking, logging, and storage—not just Cloud Run CPU. As request rates grow, compare cost/transaction alongside p95 latency.

## 18. On-Call, Incident Response, and Runbooks

### Clear Accountability Is Mandatory

A production service requires:

- Primary and secondary on-call rotations or appropriate escalation paths.
- Tested pager/notification channels.
- Severity definitions (SEV1/SEV2...) and an incident commander role.
- Runbooks for triage, mitigation, rollback, and escalation.
- SLO/status dashboards with links to Logs Explorer/Trace Explorer.
- Change freeze management, incident bridge, and stakeholder communication.
- Blameless retrospectives/postmortems and tracked improvement backlogs.

### Sample Runbook: Orders API Error Rate Spike

~~~text
Trigger: Availability SLO fast-burn alert / HTTP 5xx spike
Owner: orders-oncall
First 5 minutes:
  1. Acknowledge alert; check error dashboard by route/revision.
  2. Check recent deployments and Cloud SQL/Pub/Sub health.
  3. Assess customer impact; declare an incident if severity threshold is met.
Mitigation:
  4. If errors correlate with a new revision, roll back traffic per runbook.
  5. If DB is overloaded, reduce pressure via rate limiting/queuing.
  6. If a third party fails, enable the approved degraded mode.
Verification:
  7. Confirm error rate, p95 latency, and backlog recover.
  8. Reconcile failed or retried transactions.
Communication:
  9. Post regular updates and record timeline/owner.
After incident:
  10. Review root causes, test gaps, and follow-up actions.
~~~

Do not document rollback commands or production data fixes in a runbook as uncontrolled “one-click” actions. Specify authorized operators, safety preconditions, and side effects.

## 19. Read-Only Evidence Checks with gcloud

Below is a set of **read-only configuration inspection** commands for a sample workload. Replace `PROJECT_ID`, `REGION`, `SERVICE`, and other placeholders. These commands are a starting point; they do not replace the full PRR.

### Verify Project and APIs

~~~bash
gcloud config get-value project
gcloud projects describe PROJECT_ID
gcloud services list --enabled --project=PROJECT_ID
~~~

### Cloud Run

~~~bash
gcloud run services describe SERVICE \
  --region=REGION \
  --project=PROJECT_ID \
  --format=yaml

gcloud run revisions list \
  --service=SERVICE \
  --region=REGION \
  --project=PROJECT_ID
~~~

Inspect ingress, runtime identity, min/max instances, concurrency, resource limits, traffic splits, and revision configuration. Verify effective configuration, as CLI flags may vary across versions.

### GKE

~~~bash
gcloud container clusters list --project=PROJECT_ID
gcloud container clusters describe CLUSTER \
  --location=LOCATION --project=PROJECT_ID
kubectl get deployments,pods,pdb -A
kubectl get hpa -A
kubectl describe deployment orders-api -n orders
~~~

`kubectl` commands require the correct kubeconfig/cluster context. Verify your context before running; although these commands are read-only, they may expose internal information and require appropriate permissions.

### Cloud SQL

~~~bash
gcloud sql instances list --project=PROJECT_ID
gcloud sql instances describe SQL_INSTANCE --project=PROJECT_ID
gcloud sql backups list --instance=SQL_INSTANCE --project=PROJECT_ID
~~~

Seeing listed backups **does not** mean a restore has been verified. Evidence from an independent restore drill is required.

### IAM and Networking

~~~bash
gcloud projects get-iam-policy PROJECT_ID --format=json
gcloud compute networks list --project=PROJECT_ID
gcloud compute firewall-rules list --project=PROJECT_ID
~~~

Do not copy output containing principals, emails, or network topology into documents outside authorized scopes. A project-level IAM policy does not show all effective permissions inherited from organization/folder policies, IAM Conditions, or resource-specific bindings; security reviews must evaluate effective access.

### Alerting and Budgets

Cloud Monitoring/Cloud Billing Console can inspect dashboards, SLOs, notification channels, uptime checks, and budget alerts. If using APIs/CLIs, verify resource names/regions and actual permissions; do not treat a list command returning records as proof that alerts actually deliver notifications.

## 20. Conducting a PRR for the Java Orders API

### Step 1: Kick Off the Review

Create the service catalog record: purpose, criticality, owners, region, dependencies, launch date, and PRR ticket. Define the scope: API, Cloud SQL, Pub/Sub, Cloud Storage, plus identity and monitoring.

### Step 2: Verify Entry Criteria

- Architecture and data flows approved.
- Unit/integration tests passing.
- Security threat model has an assigned owner.
- SLOs and RTO/RPO confirmed.
- Staging mirrors production in performance-relevant aspects.
- Read-only access available to inspect configuration and evidence without modifying production.

### Step 3: Collect Configuration Evidence

Use the commands in section 19 and the Console to inspect runtime identity, ingress, concurrency, quotas, DB HA/backup/PITR, logging, and alerting. Every piece of evidence must record **timestamp, project, service, version, and owner**.

### Step 4: Execute the Test Matrix

| Test | PASS Criterion | Evidence |
|---|---|---|
| Functional happy path | Orders created/read successfully | Test report |
| Unauthorized caller | Properly rejected | 401/403 and audit log |
| Synthetic endpoint | Simulated failure detected | Uptime check result |
| 5xx alert | Notification reaches on-call | Alert test |
| Load peak | p95, 5xx, saturation within limits | Load test |
| Deployment canary | Can shift traffic and roll back | Pipeline records |
| Kill one Pod/instance | Disruption stays within SLO | Disruption test |
| DB restore | Sample data recovered within RTO/RPO | Restore log/reconciliation |
| Pub/Sub duplicate | Consumer handles idempotently | Integration test |
| Dependency timeout | Retry/circuit breaker avoids storm | Fault injection logs |
| Secret access | Only authorized service account allowed | IAM/security test |
| Budget alert | Recipients alerted and know how to respond | Billing alert validation |

### Step 5: Review Risks and Remediation

Hypothetical example:

| Finding | Severity | Owner | Deadline | Status |
|---|---|---|---|---|
| Cloud SQL backup restore never tested | P0 | DBA | Before launch | FAIL |
| Canary rollback untested after DB schema change | P1 | Backend | Before launch | FAIL |
| Dashboard lacks per-route latency breakdown | P2 | SRE | +7 days if waived | OPEN |
| Old staging artifacts not cleaned up | P3 | Platform | +14 days | OPEN |

In this example, **the decision is NO-GO** until the first two blockers are resolved. Never flip to GO on the assumption that “it will probably work.”

### Step 6: Re-Verify and Approve

After remediation, re-test the exact failure modes. Record updated evidence, artifact digest, config revision, and approver identities. Decisions apply strictly to the reviewed release and scope; major subsequent changes require re-review.

## 21. Reusable PRR Record Template

~~~yaml
review_id: "PRR-orders-api-2026-11"
service:
  id: "orders-api"
  environment: "production"
  project: "PROJECT_ID"
  region: "REGION"
  release: "IMAGE_DIGEST"
owners:
  application: "orders-team"
  oncall: "sre-team"
  security: "security-team"
  data: "dba-team"
objectives:
  availability_slo: "99.9% eligible requests / 30d"
  latency_slo: "99% eligible requests <= 400ms / 30d"
  rto: "60 minutes"
  rpo: "15 minutes"
evidence:
  architecture: "approved-diagram-link"
  load_test: "test-report-link"
  security: "security-review-link"
  restore: "restore-test-link"
  alerts: "pager-test-link"
  rollback: "canary-rollback-log-link"
findings:
  - id: "PRR-001"
    category: "data-recovery"
    severity: "P0"
    status: "FAIL"
    owner: "dba-team"
    action: "Restore rehearsal and data reconciliation"
decision:
  outcome: "NO-GO"
  reason: "P0 restore evidence missing"
  approved_by: []
  reviewed_at: "2026-11-19"
next_review: "after-PRR-001-resolved"
~~~

This is a **record template**, not a Google Cloud API configuration. Links are placeholders and SLO/RTO/RPO values are sample data that must be replaced with approved targets. Evidence documents may be sensitive; store them in an access-controlled repository.

## 22. Go-Live Canary and Rollback Playbook

~~~mermaid
flowchart TD
  A[Freeze config / backup snapshot evidence] --> B[Deploy new revision with zero traffic]
  B --> C[Smoke test + security/auth]
  C --> D{PASS?}
  D -->|No| X[NO-GO / rollback]
  D -->|Yes| E[Shift 5% traffic]
  E --> F[Observe SLO, logs, DB, Pub/Sub]
  F --> G{Gate passed?}
  G -->|No| X
  G -->|Yes| H[25% -> 50% -> 100% upon approval]
  H --> I[Enhanced monitoring / on-call]
  I --> J{Stable for defined window?}
  J -->|No| X
  J -->|Yes| K[Go-live accepted + handover]
~~~

The 5%/25%/50% percentages are illustrative only. With low traffic, 5% may not generate enough requests to draw conclusions. Combine functional tests, observation windows, sample sizes, feature flags, and state/data migration risk assessments.

### Sample Operations Timeline

| Phase | Action | Owner |
|---|---|---|
| Before T-1 day | Verify backup/restore evidence, IAM, quotas, alert channels | DBA + SRE |
| Before T-2 hours | Freeze out-of-scope changes, confirm incident bridge | Release |
| T0 | Deploy revision with safe traffic routing | DevOps |
| T+15 minutes | Verify synthetic checks, SLOs, DB, and logs | SRE |
| T+30 minutes | Increase traffic if gate passes | Release + App |
| T+60 minutes | Check backlog, data integrity, and cost anomalies | App + DBA |
| Post-launch | Handover, log findings, and maintain enhanced monitoring | On-call |

Set timings based on your real system; do not treat the timeline above as a go-live SLA.

### Go-Live Gate

A gate may include:

- Error rate does not exceed SLO-defined thresholds.
- p95 latency does not degrade beyond acceptable bounds.
- No new security/audit anomalies appear.
- Database CPU/connections/locks maintain sufficient headroom.
- Async backlog is not growing continuously.
- Synthetic transactions succeed.
- Capability exists to roll back images **and** handle schema/data safely.
- Active on-call has formally accepted handover.

## 23. Common PRR Failures

| Symptom | Common Root Cause | Remediation |
|---|---|---|
| Cloud Run returns 503 under load | Concurrency, max instances, startup, or dependency limits | Load testing, tuning, quota increase |
| API looks healthy yet transactions fail | Health endpoint does not measure business dependencies | Synthetic transactions, tracing |
| GKE rollout makes 100% of Pods unavailable | Inadequate PDB/probes/replicas/scheduling | Workload disruption readiness |
| Liveness causes restart storm | Probe depends on external DB | Design liveness strictly around process health |
| DB restore takes too long | Unrehearsed, large dataset, missing quota | Restore drills and RTO review |
| Secret exposed in logs | Logger dumps headers/bodies without masking | Redact, revoke/rotate, incident response |
| Canary rollback fails to fix errors | Backward-incompatible schema migration | Expand-contract / data recovery |
| Budget spikes rapidly | High min instances/egress/log volume | Billing export, budget/cost owner |
| SLO dashboard is empty | Wrong metric filter or missing ingestion | Test telemetry pipeline |
| Pager fails to reach the right team | Misconfigured channel/rotation/escalation | Test notifications |
| Cloud SQL exhausts connections | Pool × instance count too high | Pool caps, connection management |
| DNS/TLS fails in production | Cert/hostname/network differs from staging | Preflight FQDN/TLS checks and canary |
| Worker processes duplicate messages | Non-idempotent handling, wrong ack/retry | Idempotency keys and retry policy |
| Unable to fail over region | Only backups exist; missing DR config/IAM/network | End-to-end DR drills |
| No one authorized to trigger rollback | Missing RACI/runbook | PRR owner and escalation chain |

## 24. Complete Pre-Production Checklist

### Business and Ownership

- [ ] Service catalog, owners, and escalation confirmed.
- [ ] Critical user journeys and dependencies documented.
- [ ] SLOs, RTO, RPO, and compliance obligations approved.
- [ ] GO/NO-GO decision and exception owner confirmed.

### Landing Zone and Security

- [ ] Project/folder/billing/policies aligned with environment.
- [ ] Least-privilege IAM for deploy, runtime, and ops.
- [ ] Secrets excluded from source code, images, and logs.
- [ ] TLS, ingress, egress, IAM auth, and DB privileges tested.
- [ ] Data classification, residency, retention, and backup encryption meet requirements.
- [ ] Audit/security monitoring and incident owner ready.

### Compute and Data

- [ ] Cloud Run/GKE/GCE startup, probes, shutdown, and autoscaling verified.
- [ ] Quotas, capacity, region/zone, and maintenance windows reviewed.
- [ ] DB HA, backups/PITR, connection pools, and schema compatibility verified.
- [ ] Actual restore drill completed with data reconciliation results.
- [ ] Messaging retries, dead-letter queues, and idempotency tested.

### Observability and Operations

- [ ] Dashboards cover SLIs/SLOs, errors, latency, and saturation.
- [ ] Alerting policies, notification channels, and on-call tested.
- [ ] Structured logs/traces correlate requests with dependencies.
- [ ] Incident runbooks and rollback/failover drills completed.
- [ ] Owners, escalation, status communication, and postmortem process defined.

### Release, Performance, and Cost

- [ ] Build artifacts are immutable, scanned, and have appropriate provenance.
- [ ] CI/CD tests and IaC review/drift controls verified.
- [ ] Load/soak/failure tests meet SLOs under projected peak load.
- [ ] Canary/rollout/rollback gates and approvers established.
- [ ] Cost baseline, budget alerts, quota headroom, and cost owner defined.
- [ ] Blockers resolved; waivers have signed risk acceptance.

## Review Questions

1. A service returns HTTP 200 on `/health`, but Cloud SQL has no backup restore test: why is it not production-ready?
2. How do SLOs and SLAs differ, and why does a PRR need an error budget?
3. What damage can a database-dependent liveness probe cause?
4. Why do Cloud Run min instances not replace HA/DR?
5. With 100 Cloud Run instances and a pool of 30 connections/instance, what limit must the team check?
6. What evidence demonstrates that an alerting policy actually delivers notifications to on-call?
7. Why does rolling back a container image not solve every risk after a DB schema migration?
8. How do backup, PITR, HA, and cross-region DR differ?
9. What is the difference between `FAIL`, `NOT TESTED`, and `WAIVED WITH APPROVAL`?
10. Should load tests use representative business traffic rather than only hitting the health endpoint?
11. Is a budget alert a hard cap that automatically stops spending?
12. When does a PRR receive a CONDITIONAL GO instead of GO or NO-GO?

## Conclusion

Production readiness on Google Cloud is the ability to **prove a workload can serve traffic, detect issues, mitigate failures, recover data, and release safely**—not merely confirming resource configs look right. A credible PRR aligns application owners, DBAs, Security, SREs, Platform, and FinOps around SLOs, RTO/RPO, a risk register, and verifiable evidence.

For Java/Spring Boot workloads on Cloud Run or GKE, pay close attention to startup, concurrency, readiness/liveness, graceful shutdown, JDBC connection pools, data backup/restore, messaging idempotency, and rollback capability when multiple revisions/schemas coexist. The Well-Architected Framework provides the principles; the **GO/NO-GO** decision must rest on the service's context, risk level, and empirical evidence.

When criteria are standardized, owners are accountable, tests are executed, and reviews are repeated after major changes, PRRs become a continuous operational practice that reduces incidents and increases release safety.

## References

- [Well-Architected Framework: Operational excellence](https://cloud.google.com/architecture/framework/operational-excellence)
- [Ensure operational readiness and performance using CloudOps](https://cloud.google.com/architecture/framework/operational-excellence/operational-readiness-and-performance-using-cloudops)
- [Well-Architected Framework: Reliability](https://cloud.google.com/architecture/framework/reliability)
- [Well-Architected Framework: Security, privacy and compliance](https://cloud.google.com/architecture/framework/security)
- [Well-Architected Framework: Cost optimization](https://cloud.google.com/architecture/framework/cost-optimization)
- [Cloud Run: General development tips](https://cloud.google.com/run/docs/tips/general)
- [Cloud Run: Configure concurrency](https://cloud.google.com/run/docs/configuring/concurrency)
- [Cloud Run: Configure minimum instances](https://cloud.google.com/run/docs/configuring/min-instances)
- [GKE: Ensure workloads are disruption-ready](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-disruption-readiness)
- [GKE: Manage cluster lifecycle changes](https://cloud.google.com/kubernetes-engine/docs/concepts/managing-clusters)
- [Cloud SQL PostgreSQL: High availability](https://cloud.google.com/sql/docs/postgres/high-availability)
- [Cloud SQL: Configure backups](https://cloud.google.com/sql/docs/postgres/backup-recovery/backups)
- [Cloud Monitoring: Concepts in service monitoring](https://cloud.google.com/stackdriver/docs/solutions/slo-monitoring)
- [Cloud Monitoring: Alerting overview](https://cloud.google.com/monitoring/alerts)
- [Cloud Logging: Structured logging](https://cloud.google.com/logging/docs/structured-logging)
- [Cloud Build: Build provenance](https://cloud.google.com/build/docs/securing-builds/view-build-provenance)
- [Artifact Registry: Vulnerability scanning](https://cloud.google.com/artifact-analysis/docs/on-demand-scanning)
- [Secret Manager: Best practices](https://cloud.google.com/secret-manager/docs/best-practices)
- [Cloud Billing: Budgets and budget alerts](https://cloud.google.com/billing/docs/how-to/budgets)
- [Google SRE Workbook](https://sre.google/workbook/table-of-contents/)
