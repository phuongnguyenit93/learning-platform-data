# Finalizing Runbooks and Operational Readiness Criteria

A compute workload is truly production-ready only when the operations team can deploy, observe, handle incidents, recover, and control costs repeatably. An application running in a test environment does not prove operability: you must know who owns it, what it depends on, what normal looks like, when to alert, how to roll back, and how to recover data during an incident.

A runbook is a step-by-step operational guide for a specific service or operational scenario. Operational readiness is the evidence-based review process confirming that a workload is fit to accept user traffic and be supported by the operations team. The two go hand in hand: runbooks document how to act; readiness reviews verify those procedures are prepared, tested, and owned.

This lesson guides you through building runbooks and readiness gates for workloads running on VMs, containers, or serverless. The emphasis is on verifiable evidence: SLIs/SLOs, dependency maps, deployments and rollbacks, health checks, backup/restore, security, capacity, monitoring, incident response, disaster recovery, and operational handover.

## 1. What Is Operational Readiness?

Operational readiness is the state in which a workload can be deployed and operated to agreed standards of reliability, security, performance, recoverability, and cost. It spans technology, processes, and people.

A ready workload must answer:

- Who and which business workflows does the service support?
- Who are the service owner, technical owner, and on-call responder?
- What is the criticality and business impact of an outage?
- Are SLIs/SLOs, error budgets, and alert thresholds defined?
- Which components are mandatory dependencies?
- How do we deploy, scale, restart, drain, and roll back?
- How do we detect incidents before users report them?
- When data is lost or corrupted, where do we restore from and how fast?
- Who has production access and how is it audited?
- Is capacity sufficient under normal load, peak load, and losing one failure domain?
- Are costs predictable and tracked by an owner?
- Has the operations team rehearsed critical scenarios?

Readiness is not a one-time pre-go-live checkbox. It is a living body of evidence maintained across the service lifecycle and revisited after major changes.

## 2. Distinguishing Runbooks, Playbooks, SOPs, and Architecture

Different operational documents serve distinct purposes:

| Document | Question Answered | Typical Contents |
|---|---|---|
| Architecture overview | What components form the system and how do they connect? | Diagrams, trust boundaries, data flows, dependencies |
| Runbook | How do we execute a specific operational procedure? | Prerequisites, step-by-step commands, verification, rollback |
| Incident playbook | How do we respond to a category of incident? | Triage, containment, escalation, recovery, communication |
| SOP | How is a recurring operational routine performed? | Roles, cadence, control steps, and records |
| DR plan | How do we restore service after a broad outage? | RTO/RPO, failover, restore, failback, decision gates |
| Release/change record | What changed and who approved it? | Version, scope, risk, tests, window, outcome |

A good runbook must be specific enough for an on-call responder to follow under pressure. It should not contain only architectural prose or vague lines like "check logs and fix errors." It must specify where to query logs, which metrics to inspect, conditions to proceed, and when to escalate.

## 3. Scoping and Classifying the Workload

Before authoring runbooks, identify the workload type. Compute models require different operational procedures.

| Model | Operational Objects | Key Focus Areas |
|---|---|---|
| Virtual machine | VM, OS, disk, NIC, agent, process/service | Boot, patching, SSH/RDP, filesystems, backups, host health |
| Containers on orchestrator | Deployment, Pod, node, cluster, image, volume | Readiness, rollouts, scheduling, resource requests/limits, draining |
| Single/managed container | Revision, instance, ingress, scaling config | Startup, concurrency, scale-to-zero, revision routing |
| Serverless function | Function, trigger, event source, execution config | Invocations, timeouts, retries, concurrency, DLQ, cold starts |
| Batch/HPC | Job, scheduler, node allocation, queue, checkpoint | Queue wait, job states, MPI/network, restarts, data staging |

Scoping must also specify:

- Service or workload under review.
- Environments: development, test, staging, production.
- Accounts/projects/subscriptions and regions.
- Components owned by the team versus those managed by the platform team.
- Affected data, APIs, and customers.
- Out-of-scope components that act as dependencies.

Do not fold every shared platform service into the workload's detailed runbook if your team does not own them. Instead, document how to check dependency health and how to reach the owning team.

## 4. Building a Service Profile and Ownership

Every workload needs a concise profile serving as the starting point for operators.

| Field | What to Record |
|---|---|
| Service name | Canonical name used across dashboards, alerts, and change records |
| Business purpose | Business capabilities supported by the service |
| Service owner | Person/team accountable for service outcomes |
| Technical owner | Team accountable for code and architecture |
| On-call | Active channel and rotation schedule |
| Support hours | Coverage window and after-hours escalation |
| Criticality | Criticality tier and outage impact |
| Environments | Active environments and regions |
| Repository/artifacts | Source repo and published images or packages |
| Deployment pipeline | Standard deployment pipeline or workflow |
| Dashboard | Primary dashboard links |
| Logs/traces | Where to query logs and traces |
| Runbooks | Associated operational runbooks |
| Dependencies | Databases, queues, networks, identities, and external services |
| Data classification | Data sensitivity tier and retention requirements |

Owners must be active teams or roles able to respond—never an individual who left the project. On-call channels and escalations must be tested periodically; stale phone numbers or abandoned chat rooms provide zero real support.

## 5. Determining Criticality and Business Impact

Not every workload needs the same readiness bar. Classify based on the impact of downtime, data loss, or incorrect processing.

Typical tiers:

- **Critical:** directly impacts core transactions or essential functions; even brief downtime causes major impact.
- **High:** significantly affects users or internal operations; limited workarounds may exist.
- **Standard:** can tolerate outages within an agreed window.
- **Low/Non-production:** non-production; can be shut down on schedule or rebuilt from artifacts.

Classification must rely on business impact analysis, not VM counts or CPU size. A small function processing payments may be far more critical than a large cluster running internal reports.

For each workload, determine:

- Dependent users or business processes.
- Tolerable outage duration.
- Tolerable data loss.
- Financial, legal, safety, or reputational impact.
- Workarounds and how long they remain viable.
- Peak seasons or critical business windows.

## 6. Establishing SLIs, SLOs, and Error Budgets

An **SLI** measures service quality. An **SLO** sets the target for an SLI over a time window. An **SLA** is an external commitment to users or customers that may carry contractual remedies if missed.

Sample SLIs/SLOs:

| SLI | How It Is Measured | Illustrative SLO |
|---|---|---|
| Availability | Valid requests receiving successful responses | 99.9% over 30 days |
| Latency | Percentage of requests finishing below threshold | 95% under 300 ms |
| Correctness | Percentage of valid business outcomes | 99.99% |
| Queue freshness | Oldest message age or p95 queue age | p95 under 60 seconds |
| Job completion | Percentage of batch jobs finishing within window | 99% before deadline |
| Data recovery | Ability to hit RPO/RTO during rehearsals | Meets approved targets |

Values are illustrative, not universal defaults. SLOs must balance business expectations, architectural capabilities, and the cost of achieving them.

### 6.1. Choosing User-Meaningful SLIs

Never use CPU utilization as an availability SLI. CPU is an internal signal; users care whether requests complete accurately and fast enough.

Combine:

- User-facing SLIs: success rate, latency, correctness.
- Background-processing SLIs: queue age, event processing delay, job completion.
- Data SLIs: replication lag, backup freshness, restore success.
- Platform SLIs: health of instances, nodes, functions, and dependencies.

### 6.2. Error Budgets

The error budget is the allowable amount of failure or disruption within an SLO. If availability SLO is 99.9% over a window, the error budget is the allowed failing fraction of time or requests as defined by the SLI.

Runbooks and release policies can use error budgets to govern:

- Continuing normal releases.
- Increasing test rigor or narrowing rollout scope.
- Freezing high-risk changes.
- Prioritizing reliability debt paydown.
- Scheduling capacity or DR exercises.

Align on calculation formulas and data sources; never compare a time-based error budget in minutes against a request-based error budget without normalizing.

## 7. Defining RTO and RPO

Two primary recovery objectives:

- **RTO (Recovery Time Objective):** target maximum duration to restore service after an incident.
- **RPO (Recovery Point Objective):** maximum acceptable data loss, typically expressed in data age.

For example, a 60-minute RTO targets restoring service within one hour. A 15-minute RPO accepts recovering to a data point up to roughly 15 minutes old, per agreed measurement rules.

RTO/RPO must be approved by the business owner. They drive costs for backups, replication, warm standby, multi-region footprints, and rehearsals.

| Recovery Tier | Sample Targets | Architecture Typically Required |
|---|---|---|
| Very low RTO, near-zero RPO | Mission-critical transactional services | Multi-zone HA, synchronous replication, or specialized data engines |
| Low RTO, few-minute RPO | Critical APIs | Warm standby, monitored asynchronous replication |
| Multi-hour RTO, hourly RPO | Internal systems | Backups/restores and reproducible infrastructure |
| Long RTO, daily RPO | Lower-criticality workloads | Scheduled backups, IaC, and manual recovery workflows |

Never promise RTO/RPO merely because backups are turned on. Measure actual restore times, provisioning times, DNS/failover, data verification, and business validation during drills.

## 8. Mapping Dependencies and Data Flows

Runbooks must tell on-call engineers what must be healthy before the workload can operate.

Typical dependencies include:

- DNS, routing, firewalls, NAT, and private connectivity.
- Identity providers, IAM roles, managed identities, or service accounts.
- Secret managers and certificate authorities.
- Databases, caches, object storage, and filesystems.
- Queues, event buses, streams, and workflow engines.
- Third-party APIs.
- Logging, metrics, tracing, and alerting pipelines.
- Image registries, package repositories, and deployment control planes.
- Backups, replication, and key management.

Dependency diagram:

~~~mermaid
flowchart TD
    U[Client / producer] --> E[Ingress / event source]
    E --> C[Compute workload]
    C --> I[Identity and secrets]
    C --> D[(Database)]
    C --> Q[Queue / event bus]
    C --> O[Object storage]
    C --> X[External API]
    C --> T[Telemetry pipeline]
    D --> B[Backup / replication]
    C --> N[Network / DNS / NAT]
~~~

For each dependency, document:

- Owner and support channel.
- Protocol, endpoint, and port.
- Authentication method.
- Timeout and retry behavior.
- Health signals.
- Failure impact.
- Workaround or fallback.
- Safe connectivity verification method.

Never store real credentials or secrets in runbooks. Record only secret reference names, retrieval locations, and authorized roles.

## 9. Defining Normal State and Baselines

Incident runbooks require baselines so responders can spot anomalies.

Capture baselines hourly/daily/weekly and seasonally:

- Request rates or event arrival rates.
- Success/error rates.
- p50/p95/p99 latency.
- CPU, memory, disk, and network usage.
- Container restarts, pending Pods, and node pressure.
- Function concurrency, duration, and throttling.
- Queue depth, oldest-message age, and consumer lag.
- Database connections, query latency, and replication lag.
- Egress, NAT connections, and network transfer.
- Cost per service and environment.

Baselines must cover both steady-state and peak loads. Knowing only averages leaves responders guessing whether 80% CPU is normal for a nightly batch window or signals impending overload.

## 10. Designing Monitoring and Alerting

Good alerts indicate user impact or an actionable risk. Do not generate hundreds of alerts for brief metric blips.

Alert tiers:

- **Page:** requires immediate responder action due to user impact or imminent SLO breach.
- **Ticket:** requires investigation during support hours without waking on-call.
- **Informational:** provides context or trend visibility.

Every alert needs:

- Clear name and description.
- Severity.
- Condition and evaluation window.
- Affected service/environment/region.
- Linked dashboards and log queries.
- Runbook link.
- Owner/escalation path.
- Guidance to confirm false positives.
- Safe first action.

### 10.1. Symptom-Based vs. Cause-Based Alerts

Prioritize user-facing symptom alerts, such as error rates or latency breaching SLOs. Cause-based alerts like high CPU, rising disk usage, or node pressure aid root-cause diagnosis but do not always warrant paging.

Examples:

| Signal | Suggested Alert Type | Action |
|---|---|---|
| Availability SLI drops below threshold | Page | Assess impact and start incident triage |
| p99 latency climbs steadily | Page or ticket per SLO | Inspect dependencies and saturation |
| Queue age exceeds business deadline | Page | Check consumers, downstream services, and scaling |
| Disk nearing capacity | Ticket/page by criticality | Inspect logs, data growth, and capacity |
| Backup job fails | Page or ticket per RPO | Verify latest valid backup |
| Certificate nearing expiration | Time-bound ticket | Renew and verify rollout |
| Sudden spend spike | FinOps alert | Break down volume, duration, and retries |

## 11. Logging, Metrics, and Distributed Tracing

Three telemetry types complement each other:

- **Logs:** discrete events, errors, and per-execution context.
- **Metrics:** time-series aggregations for trend detection and alerting.
- **Traces:** request/event paths spanning services and dependencies.

Standardize fields:

- Service name and environment.
- Release/version or image digest.
- Timestamp with timezone.
- Correlation ID and trace ID.
- Request/event type.
- Outcome/error code.
- Duration.
- Dependency name.
- Region/zone or appropriate instance identifier.

Never log access tokens, passwords, private keys, card data, or sensitive payloads. Apply masking/redaction, sampling, and policy-compliant retention. Avoid high-cardinality metric labels like user IDs or request IDs; keep fine-grained details in controlled logs and traces.

## 12. Deployment and Release Runbook

The release runbook must cover the entire path from artifact to production.

Minimum steps:

1. Verify change ticket or release record.
2. Verify commit, image/package digest, and build provenance.
3. Confirm required security scans and tests passed.
4. Confirm configuration, secret references, and schema compatibility.
5. Check capacity, quotas, and maintenance windows.
6. Confirm dashboards, alerts, and on-call readiness.
7. Deploy via canary, rolling, or blue-green as appropriate.
8. Verify readiness and run smoke tests.
9. Monitor SLIs/SLOs throughout the observation window.
10. Promote the release once criteria are met.
11. Record version, timestamp, operator, and outcome.
12. Retain the prior artifact/revision through the rollback window.

### 12.1. Rollout Stop Criteria

Halt the rollout when:

- Readiness fails or Pods/functions restart repeatedly.
- Error rates or latency breach defined thresholds.
- Business metrics drop abnormally.
- Database migrations prove incompatible with the previous version.
- Queue age or retries spike rapidly.
- Security errors or permission misconfigurations appear.
- Capacity is insufficient for the next rollout step.
- Monitoring stops working, preventing safe evaluation.

Never proceed solely because the pipeline reports deployment success. Infrastructure status does not replace business validation.

## 13. Rollback Runbook

Rollback runbooks must state trigger conditions, decision authority, exact steps, and post-rollback checks.

General procedure:

1. Confirm the new release is the probable cause or that rolling back is the safest option.
2. Halt traffic expansion and close the change window.
3. Verify the previous version's artifacts and capacity remain available.
4. Verify database/schema compatibility.
5. Restore previous routing or deployment revision.
6. Confirm prior replicas are Ready and dependencies operate properly.
7. Inspect in-flight requests, transactions, and queues.
8. Monitor SLIs/SLOs and business metrics.
9. Log timestamps, release IDs, and outcomes.
10. Preserve evidence for root-cause investigation.

### 13.1. Kubernetes Example

~~~bash
kubectl rollout status deployment/api
kubectl rollout history deployment/api
kubectl rollout undo deployment/api
kubectl get pods -l app=api -o wide
kubectl describe deployment api
~~~

Commands are illustrative. Where GitOps is the source of truth, perform rollbacks through the Git repository or release controller; direct cluster edits may be overwritten by reconciliation.

### 13.2. Rollback Does Not Undo Data Changes

Rolling back an image does not reverse committed transactions, emitted messages, sent emails, or breaking schema migrations. Runbooks must distinguish:

- Application artifact rollback.
- Configuration rollback.
- Routing/traffic weight rollback.
- Database migration rollback or forward-fix.
- Restoring data from backups.
- Business compensation for external side effects.

If a migration cannot be safely reversed, rolling forward with a compatible patch may be required instead of reverting to an older binary.

## 14. VM Operations Runbook

For VMs, runbooks must cover OS, processes, disks, networking, and the cloud control plane.

### 14.1. Checking VM Health

- Instance state and host/system status checks.
- CPU, memory, and disk utilization.
- Read-only filesystems or inode exhaustion.
- NICs, routes, DNS, and security rules.
- Service/process status.
- Management, monitoring, and backup agents.
- Boot logs and system logs.
- Disk attachments and snapshot status.

Linux example:

~~~bash
systemctl status application.service
journalctl -u application.service --since "30 minutes ago"
df -h
free -m
uptime
ss -tulpn
~~~

Never run mutating commands or delete files before understanding impact and holding proper authorization. When disks fill up, check fast-growing files, log retention, and data owners; never delete business data just to silence an alert.

### 14.2. Restarting and Replacing VMs

Runbooks must specify:

- When to restart a process versus rebooting the VM.
- Whether draining from the load balancer is required first.
- Whether state or active jobs reside on local disks.
- Whether the VM is reproducible from images/IaC.
- Whether IPs/DNS/volumes change upon replacement.
- Who verifies the service post-reboot.
- How to recover if boot or startup scripts fail.

If a VM holds unique stateful data, replacing the instance can cause data loss. Check volumes, replication, and backups before acting.

## 15. Container Operations Runbook

Container workloads need runbooks covering both application controllers and the cluster/nodes.

Items to inspect:

- Deployment/StatefulSet desired, current, and available replicas.
- Pod `Pending`, `CrashLoopBackOff`, and `ImagePullBackOff` states.
- Readiness/liveness/startup probes.
- CPU/memory requests, limits, and throttling.
- Node pressure, taints, affinity, and quotas.
- Service/Ingress/NetworkPolicy configuration.
- Persistent volume attachments and storage latency.
- Image digests, rollout revisions, and registry availability.
- Autoscalers and disruption budgets.

Kubernetes command examples:

~~~bash
kubectl get deploy,rs,pods -n production
kubectl rollout status deployment/api -n production
kubectl describe pod POD_NAME -n production
kubectl logs POD_NAME -n production --since=30m
kubectl get events -n production --sort-by=.lastTimestamp
kubectl top pods -n production
kubectl top nodes
~~~

Substitute your environment's namespace and resources. Never paste secrets or sensitive outputs into public tickets.

### 15.1. Node Draining and Maintenance

Before draining:

- Verify remaining cluster capacity.
- Verify PDBs and replica placement.
- Check stateful workloads and volumes.
- Confirm jobs support checkpoints or safe retries.
- Check autoscaler and maintenance policies.
- Monitor Pod evictions and readiness throughout the drain.

Do not assume a PDB blocks every form of disruption or guarantees sufficient capacity remains. Verify actual controllers, disruption types, and topology.

## 16. Serverless Operations Runbook

Functions/serverless remove direct OS and node management from app teams, yet still require runbooks for events, runtimes, and dependencies.

Items to inspect:

- Invocation counts and p50/p95/p99 duration.
- Errors, timeouts, throttling, and OOMs.
- Concurrency and provisioned/warm capacity.
- Cold-start/init duration.
- Trigger/event source health.
- Queue depth, oldest-message age, and stream lag.
- Retries, duplicates, and DLQs.
- Function versions, aliases/revisions, and traffic routing.
- IAM roles/managed identities/service accounts.
- VPC/VNet, DNS, NAT, and private endpoints.
- Cost per successful operation.

When a function fails, isolate whether failure occurred pre-handler, inside the handler, or in a dependency. For event source mappings, inspect pollers, batches, visibility/ack deadlines, and checkpoints; for push triggers, inspect delivery attempts, response statuses, and retry policies.

### 16.1. Replaying Events

Before replaying events from a DLQ:

1. Identify the root cause.
2. Confirm the fixed handler version is deployed.
3. Inspect event schemas and sensitive data handling.
4. Check whether earlier side effects already succeeded.
5. Verify idempotency keys/deduplication.
6. Replay in small batches.
7. Monitor successes, retries, and downstream load.

Never bulk-replay while a dependency is degraded or consumers lack capacity.

## 17. Scaling and Capacity Runbook

Scaling requires explicit triggers, bounds, and verification steps.

### 17.1. Scale-Out

- Identify the symptom: latency, queue age, saturation, or rejected requests.
- Verify whether the bottleneck is compute or a dependency.
- Check quotas and regional capacity.
- Increase replicas/instances/concurrency per policy.
- Confirm load balancers/triggers distribute work to new capacity.
- Monitor latency, error rates, and downstream saturation.

### 17.2. Scale-In

- Confirm load dropped steadily over a sufficient window.
- Drain active requests, connections, and jobs.
- Check stateful workloads and local data.
- Step capacity down incrementally.
- Monitor SLOs and queue age after each step.
- Halt scale-in if latency or backlogs climb.

### 17.3. Failure-Scenario Capacity

Do not size solely for normal peaks. Validate N-1 capacity: if one node, zone, or instance pool is lost, can surviving capacity carry the required load? For serverless, check concurrency/quotas and downstream resilience to bursts when queued backlogs drain.

## 18. Backup, Restore, and Data Protection

Backup runbooks must specify:

- Which data is backed up.
- Backup mechanisms and schedules.
- Retention and storage locations.
- Encryption and key ownership.
- Backup access permissions.
- Integrity verification procedures.
- Restore procedures per data type.
- Who approves production restores.
- How consistency and business correctness are verified.

Job status showing backup success does not prove data restores cleanly. Periodically test restores in an isolated environment and measure real duration.

### 18.1. Restore Procedure

1. Identify the incident and target recovery timestamp.
2. Select a recovery point satisfying RPO.
3. Verify backup and encryption key availability.
4. Provision an isolated restore environment.
5. Restore databases/files/objects.
6. Run integrity checks and reconcile record counts or checksums.
7. Verify the application can read restored data.
8. Obtain business owner confirmation of data validity.
9. Cut over traffic or promote the restored system.
10. Record actual restore duration and achieved RPO/RTO.

Never overwrite production before understanding what newer data will be lost or whether merging is needed. For distributed databases, follow the engine's consistent restore procedures.

## 19. Disaster Recovery, Failover, and Failback

DR runbooks must cover recovery from incidents larger than a single instance or node.

Required elements:

- Disaster declaration criteria and decision authority.
- Standby region/site and readiness status.
- Recovery ordering across networking, identity, data, and compute.
- Database or replica promotion procedures.
- DNS/global routing and cache propagation times.
- Verification of secrets, certificates, quotas, and image availability.
- Handling of event/queue backlogs and in-flight jobs.
- Verification that data meets RPO.
- Verification that service meets RTO.
- Stakeholder communications.
- Failback procedure once the primary region recovers.

### 19.1. Failover Is More Than Flipping DNS

When switching regions, verify authoritative data writers, replication lag, queue ownership, scheduled jobs, and external side effects. If two regions accept writes simultaneously without leader election or fencing, split-brain and conflicting data can occur.

### 19.2. DR Drills

Drills must record:

- Scenario and scope.
- Start timestamp.
- Participants and roles.
- Runbook steps executed.
- Actual RTO/RPO.
- Deviations from documentation.
- Data validation outcomes.
- Action items, owners, and deadlines.

An untested runbook is merely a hypothesis. After every exercise, update documentation and re-verify contacts, permissions, and automation.

## 20. Security Readiness

Security readiness covers workloads, pipelines, identities, networks, and data.

### 20.1. Identity and Permissions

- Workloads use dedicated roles/managed identities/service accounts.
- Permissions follow least privilege and narrowest scope.
- No long-lived access keys embedded in images or source code.
- Secrets come from a secret manager with rotation.
- Deployment permissions are separated from runtime permissions where appropriate.
- Break-glass access is controlled and audited.
- Credential owners and expirations are tracked.

### 20.2. Network

- Public exposure is documented and approved.
- Private endpoints/VPC/VNet integrations are used properly.
- Security groups, firewalls, NSGs, and NetworkPolicies restrict flows.
- Egress is controlled.
- DNS and certificates are monitored.
- NAT capacity and network dependencies are verified.
- Administrative ports are never exposed to the Internet without strong controls.

### 20.3. Images and Supply Chain

- Artifacts originate from governed pipelines/repositories.
- Images/packages are scanned per policy.
- Immutable digests or versions are recorded in release logs.
- Dependencies and base images have an update cadence.
- SBOMs/provenance are retained if policy requires.
- No secrets exist in image layers, build logs, or artifacts.
- Processes exist to revoke/redeploy upon critical vulnerability disclosures.

### 20.4. Data and Auditing

- Explicit data classification exists.
- Encryption at rest and in transit meets requirements.
- Logs never expose secrets or sensitive data.
- Audit logs are protected against tampering or deletion.
- Retention and deletion comply with policy.
- Backups and encryption keys have segregated access controls.

## 21. Change Management and Maintenance

Runbooks must cover routine changes as well as incidents.

Change categories:

- Application releases.
- OS/runtime patching.
- Base image updates.
- Certificate/secret rotations.
- Database schema migrations.
- Network/security policy updates.
- Scaling/capacity adjustments.
- Backup policy updates.
- Region/DR configuration updates.

A change record should capture:

- Objective and scope.
- Affected resources and users.
- Risk and impact.
- Pre-checks and tests.
- Maintenance window.
- Rollback/forward-fix plan.
- Approver and implementer.
- Success criteria.
- Outcome and follow-ups.

Not every change requires the same approval tier. Classify by risk and impact while always preserving an appropriate audit trail.

## 22. Incident Response and Escalation

A clear incident process cuts time wasted finding commanders and first actions.

Standard roles:

- **Incident commander:** coordinates response, sets priorities, drives cadence.
- **Technical lead:** investigates and directs technical remediation.
- **Communications lead:** updates stakeholders and users.
- **Scribe:** logs timeline, decisions, and actions.
- **Service owner:** confirms business impact and recovery criteria.

In smaller teams one person may fill multiple roles, provided role assignments are explicit.

### 22.1. Baseline Incident Workflow

1. Receive alert or report.
2. Confirm symptoms and blast radius.
3. Assign severity and open an incident record.
4. Designate incident commander/technical lead.
5. Prioritize data protection and containment.
6. Investigate using runbooks and telemetry.
7. Restore service through safe actions.
8. Verify SLIs/SLOs and business operations.
9. Update stakeholders at regular intervals.
10. Close the incident once stability evidence is confirmed.
11. Hold a post-incident review and track action items.

### 22.2. Severity and Escalation

| Level | Examples | Response |
|---|---|---|
| SEV-1 | Critical service down or severe data loss | Immediate page, incident command, stakeholder notification |
| SEV-2 | Major degradation, many users impacted, or SLO at risk | Rapid on-call response, prioritized investigation |
| SEV-3 | Limited impact with workaround available | Ticket/support team during defined hours |
| SEV-4 | Minor bug or informational request | Operational backlog |

Severity definitions and response SLAs must be agreed organization-wide. This table is illustrative; do not override existing incident policies.

## 23. Symptom-Driven Troubleshooting Procedures

### 23.1. Rising Latency

1. Check p95/p99 SLIs and user scope.
2. Compare against baselines and recent releases.
3. Inspect CPU/memory/concurrency and queue age.
4. Inspect traces to pinpoint slow dependencies.
5. Check database pools, queries, and networking.
6. Shed traffic or roll back if a regression is confirmed.
7. Verify latency recovery and monitor across a full window.

### 23.2. Rising Error Rate

1. Group errors by status code and exception.
2. Inspect the most recent release/config changes.
3. Check dependency availability and credentials.
4. Determine whether errors affect data or external side effects.
5. Halt retry storms if occurring.
6. Roll back or shift traffic to healthy backends.
7. Verify success rate and correctness.

### 23.3. Growing Queue Backlog

1. Compare arrival rate against processing rate.
2. Check consumer concurrency, errors, and timeouts.
3. Check downstream rate limits or outages.
4. Check for poison messages and DLQ growth.
5. Scale consumers cautiously if dependencies have capacity.
6. Throttle producers or apply backpressure when needed.
7. Confirm oldest-message age returns to target.

### 23.4. Memory/Disk Near Exhaustion

1. Identify the exact resource and workload.
2. Check trends, leaks, and file growth.
3. Identify files/caches/logs safe to clean per policy.
4. Never delete business data or unverified backups.
5. Scale or expand disks per change policy if needed.
6. Confirm memory/disk headroom post-remediation.

### 23.5. Dependency Connectivity Failure

1. Identify source/destination, port, and protocol.
2. Check DNS resolution.
3. Check routes, security groups/firewalls, and private endpoints.
4. Check identities, certificates, and secret rotations.
5. Check NAT/connection limits.
6. Check dependency health and network paths.
7. Run controlled connectivity tests without dumping credentials.

## 24. Capacity, Performance, and Load Test Readiness

Before production, gather evidence that the workload handles expected demand.

Testing should cover:

- Baseline load.
- Peak load.
- Bursts and ramp-ups.
- Extended soak tests.
- Scale-out and scale-in.
- Loss of one instance/node/zone within design bounds.
- Dependency latency or failures.
- Queue backlogs and recovery.
- Deployments under live load.
- Resource exhaustion in a safe test environment.

Results must record throughput, p50/p95/p99 latency, error rates, CPU/memory, networking, queue age, database saturation, and cost. Define pass/fail thresholds before running tests—never move goalposts afterward just to declare success.

## 25. Cost Readiness and FinOps

A production workload needs cost forecasts and anomaly detection.

Define:

- Owner/cost center and standard tags.
- Compute, storage, network, backup, logging, and dependency costs.
- Unit cost per request, job, user, or business transaction.
- Budgets and forecasts.
- Spend anomaly alerts.
- Idle resource checks and non-production start/stop schedules.
- Commitments/reservations and capacity risks.
- DR, warm standby, and data replication costs.

Cost optimization must never break SLOs or compromise recovery. Validate every capacity reduction under peak load and failure scenarios.

## 26. Reusable Runbook Template

Every operational runbook should follow a consistent structure:

~~~markdown
# Procedure / Scenario Name

## Objective
Describe the target outcome.

## Scope
Affected service, environment, region, and resources.

## Accountable Roles
Owner, on-call, approver, and escalation path.

## Prerequisites
Required permissions, change record, maintenance window,
backups/checkpoints, and dependency health.

## Impact and Risks
Potential user impact, data risks, downtime, and side effects.

## Execution Steps
1. Verify initial state.
2. Execute actions in sequence.
3. Monitor progress.
4. Verify outcome.

## Success Criteria
Specific metrics, health checks, and business validation.

## Rollback / Recovery
Abort conditions, return steps, and recovery limits.

## Escalation
When to hand off to another team and what evidence to provide.

## Audit
Timestamp, operator, resource IDs, and outcome.
~~~

Tailor the template to the specific operation. Include exact commands or dashboard links where needed; never leave unfilled placeholders in production runbooks.

## 27. Example Runbook: Releasing a Container API

**Objective:** release a new API revision while maintaining SLOs.

**Scope:** `production` namespace, `api` Deployment, and `public-api` Service.

**Prerequisites:**

- Release passed build, scan, and test gates.
- Image digest and config version recorded.
- Database migrations are backward-compatible.
- Dashboards and alerts are active.
- On-call responder is notified.
- Current replicas have sufficient capacity and no open incidents exist.

**Execution:**

1. Inspect available replicas, error rate, latency, and queue age.
2. Confirm the image digest in the release record.
3. Apply the manifest or promote the revision via the standard pipeline.
4. Monitor rollout status and Pod events.
5. Run smoke tests against the approved production endpoint.
6. Monitor error rates, p95/p99 latency, and business metrics throughout the observation window.
7. If criteria pass, mark the release complete and archive results.
8. If criteria fail, halt the rollout and execute the rollback runbook.

**Success Criteria:**

- All desired replicas are available.
- No abnormal Pod restarts.
- Smoke tests pass.
- SLIs show no regression beyond thresholds.
- Databases and queues show no abnormal backlog.
- Owner confirms business functionality.

**Rollback:** restore the prior stable revision/image digest via the release controller; verify schema compatibility before shifting full traffic back.

## 28. Example Runbook: Event-Processing Function Backlog

**Symptoms:** oldest-message age rises, queue depth climbs, and completed event counts fall.

**Investigation:**

1. Compare event arrival rate against processing rate.
2. Check invocation counts, duration, errors, and throttling.
3. Check function concurrency and quotas.
4. Check dependency latency, connection limits, and rate limits.
5. Check retry counts, poison events, and DLQ state.
6. Determine whether backlog concentrates on specific partitions/keys.

**Remediation:**

- If the function lacks concurrency and downstream has headroom, raise concurrency limits incrementally.
- If the database is overloaded, throttle consumer rate and resolve the bottleneck.
- If poison events appear, isolate them via the DLQ or appropriate policy.
- If a new release caused failures, shift traffic/alias back to the stable version.
- If events are duplicated, verify idempotency before replaying.

**Recovery Criteria:**

- Queue age drops back to target.
- Processing rate exceeds arrival rate long enough to clear the backlog.
- Errors/retries stop climbing abnormally.
- Downstream services remain within healthy limits.
- Business operations are verified accurate.

## 29. Readiness Review and Go/No-Go Gates

A readiness review evaluates evidence before a workload accepts production traffic. Involve business owners, service owners, platform, security, data, and operations as scope dictates.

Primary gates:

| Gate | Question | Required Evidence |
|---|---|---|
| Business | Are scope and impact clear? | Owner, criticality, support expectations |
| Architecture | Are dependencies and failure modes understood? | Architecture/data-flow diagrams, dependency map |
| Reliability | Are SLOs, alerts, and recovery achievable? | SLI dashboards, alert tests, RTO/RPO |
| Deployment | Can we deploy and roll back safely? | Release records, artifact digests, rollback rehearsal |
| Security | Are identities, networks, and data controlled? | IAM review, scans, network rules, secret handling |
| Data protection | Can backups be restored? | Backup policy and restore evidence |
| Performance | Can the workload sustain expected load? | Load/soak/failover test reports |
| Operations | Can on-call handle incidents? | Runbooks, on-call rota, escalations, game day |
| Cost | Are costs owned and bounded? | Forecasts, budgets, tags, anomaly alerts |
| Compliance | Do retention and auditing meet requirements? | Policy mapping and audit evidence |

### 29.1. Go/No-Go Decisions

- **Go:** all mandatory requirements pass, owners accept residual risks, and operations staffing is ready.
- **Conditional Go:** only low-risk items remain with documented workarounds, owners, and deadlines; requires authorized sign-off.
- **No-Go:** critical defects remain in security, data protection, rollback, monitoring, capacity, ownership, or recoverability.

Never downgrade a blocker's severity just to hit a launch date. Never use Conditional Go to wave through unmitigated critical risks.

## 30. Readiness Matrix by Compute Model

| Area | VM | Container | Serverless Function |
|---|---|---|---|
| Health | OS/process/agent | Probes, Pod, and node health | Invocations/errors/throttles |
| Deploy | Images/VM templates/configs | Image digests, rollout strategies | Function versions/aliases/revisions |
| Rollback | Snapshots/images/configs or redeploy | Revisions/images and traffic routing | Versions/aliases/configs |
| Scaling | VM scale sets/ASGs/manual | Replica/node autoscalers | Concurrency/instance scaling |
| Network | NICs, routes, firewalls, DNS | Services, Ingress, NetworkPolicies | VPC/VNet, egress, trigger paths |
| Data | Disks, filesystems, databases | PVCs, volumes, databases | Objects/databases/queues; ephemeral temp storage |
| Backup | Disk/data/DB backups | Persistent data and cluster configs | Data/dependencies; versioned function artifacts |
| Incident | OS, processes, hosts, disks | Pods, nodes, schedulers, images | Triggers, runtime, retries, DLQs, quotas |
| Capacity | CPU/RAM/disk/network | Requests/limits, nodes, replicas | Memory/CPU tiers, concurrency, quotas |
| Cost | Instance hours, disks, network | Nodes/clusters, storage, LBs | Invocations, duration, allocation, dependencies |

The matrix helps audit topic coverage. Detailed runbooks must still reflect the exact services and technologies deployed.

## 31. Operational Handover

Handover is complete only when the receiving operations team understands the system and can execute key workflows.

Handover package should include:

- Service profile and ownership.
- Architecture/dependency/data-flow diagrams.
- SLOs/SLIs and dashboards.
- Alert catalog and routing.
- Deployment/release/rollback runbooks.
- Incident playbooks.
- Backup/restore/DR runbooks.
- Security access model.
- Capacity/performance baselines.
- Cost forecast and cost owner.
- Known issues and accepted risks.
- Maintenance and certificate/secret rotation schedules.
- Links to repositories, artifacts, and change history.
- Rehearsal notes and open action items.

Hold a live walkthrough: the development team explains flows while the operations team performs one routine task and one failure scenario in a safe environment. If the receiving team cannot execute directly from the runbook, documentation or processes are incomplete.

## 32. Runbook Quality and Lifecycle Management

Runbooks decay rapidly without an owner and a review cadence.

Every document needs:

- Owner.
- Version or revision.
- Last reviewed date.
- Next review date.
- Applicable service/environment.
- Related release/config versions if relevant.
- Reviewer or approver.
- Change history.

Trigger reviews upon:

- Architecture or dependency changes.
- Runtime, image, OS, or scheduler changes.
- Network, IAM, or secret flow changes.
- SLO, RTO, or RPO changes.
- Incidents or DR exercises.
- Vendor/service API changes.
- On-call or support model changes.

Do not rely solely on calendar reviews; change events are mandatory triggers to revalidate related runbooks.

## 33. Anti-Patterns to Avoid

**Runbooks containing only a dashboard link.** Responders still do not know what to do. Add preconditions, inspection steps, safe actions, and success criteria.

**Missing explicit ownership.** Alerts ping-pong or go unanswered. Maintain verified owners and tested escalations.

**SLOs existing only on slides.** No matching metrics or alerts exist. Build dashboards and verify underlying data sources.

**Backups never restored.** Zero proof of recoverability. Rehearse restores and measure RTO/RPO.

**Rollbacks that only revert images.** Schemas or external side effects remain incompatible. Design compatible migrations and compensation.

**Raising concurrency while dependencies are overloaded.** Backlogs may dip momentarily while the database collapses. Apply backpressure and scale to the true bottleneck.

**Excessive alerting.** On-call suffers alert fatigue. Consolidate alerts around symptoms, severity, and actionable runbooks.

**Storing real secrets in runbooks.** Documentation becomes a leak vector. Use secret references and controlled retrieval instructions.

**Going live without rehearsals.** Operations discovers missing permissions or broken steps only during a live outage. Run game days before release.

**Ignoring action items.** Post-incident lessons fail to yield improvements. Assign owners, deadlines, and verify completion.

## 34. Pre-Production Readiness Checklist

### Ownership and Business

- [ ] Service owner, technical owner, and on-call are confirmed.
- [ ] Criticality, user impact, and support hours are clear.
- [ ] Dependency map and data-flow diagrams are current.
- [ ] Known risks and workarounds have assigned owners.

### Reliability and Recovery

- [ ] SLIs/SLOs and error budgets are defined and measured.
- [ ] Paging/ticketing alerts have routing and runbooks.
- [ ] RTO/RPO targets are approved by the business owner.
- [ ] Backup policies and restore tests have evidence.
- [ ] DR/failover/failback are rehearsed per criticality tier.
- [ ] Capacity handles peak load and failure scenarios.

### Release and Operations

- [ ] Artifacts/versions/configs are traceable.
- [ ] Deploy, smoke tests, rollback, and verification have been tested.
- [ ] Graceful shutdown, draining, and maintenance procedures are clear.
- [ ] VM/container/serverless runbooks fit the workload.
- [ ] On-call completed a walkthrough and hands-on practice.
- [ ] Incident severities, commanders, and escalations are clear.

### Security and Data

- [ ] IAM/identities follow least privilege.
- [ ] Secrets and certificates have rotation/expiry owners.
- [ ] Network exposure and egress are controlled.
- [ ] Image/dependency scans meet policy.
- [ ] Encryption, auditing, retention, and data classification meet requirements.
- [ ] No secrets or sensitive data appear in runbooks or logs.

### Performance and Cost

- [ ] Load, peak, soak, and failure tests meet defined thresholds.
- [ ] CPU/memory/network/latency/queue baselines are recorded.
- [ ] Quotas and scaling limits are verified.
- [ ] Cost owner, tags, budgets, and anomaly alerts are configured.
- [ ] Cost per request/job/transaction is tracked.

### Governance

- [ ] Readiness review minutes and Go/No-Go decision are recorded.
- [ ] Residual risks are accepted by authorized owners.
- [ ] Runbooks have owners, revisions, and review dates.
- [ ] Open action items have deadlines and accountable owners.

## 35. Conclusion

Runbooks turn operational knowledge into executable, verifiable steps; operational readiness proves a workload has clear ownership, safe deployment and rollback paths, active monitoring, protected data, incident recovery capability, and cost controls. Tailor these requirements to your compute model: VMs require OS and host management; containers require rollout, node, and volume management; serverless requires trigger, concurrency, retry, and event delivery management.

Issue a Go decision only when evidence matches criticality and SLOs: working dashboards/alerts, walked-through runbooks, tested backup restores, rehearsed rollbacks, completed security reviews, and verified capacity and costs. After go-live, update runbooks after every change, incident, and DR exercise so documentation always reflects production reality.
