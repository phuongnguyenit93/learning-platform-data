# Pilot Light and Warm Standby Strategies

When an AWS Region experiences a severe outage, a workload can lose availability even if its data exists elsewhere. Organizations need a standby environment capable of accepting traffic, holding current data, and activating within committed timelines. Two commonly evaluated strategies are **pilot light** and **warm standby**.

Pilot light keeps core recovery components running or ready—typically data stores or data replicas, networking, IAM, and foundational resources. When an incident occurs, operations deploys or scales out compute and remaining components to bring the application online in the standby Region.

Warm standby maintains a scaled-down yet operational version of the workload in the standby Region. When the primary Region fails, operations scales up standby resources and routes traffic over. Because part of the application is already running, warm standby generally achieves a shorter RTO than pilot light, at the trade-off of higher ongoing costs.

Within the **CLOUD_PROVIDERS_AWS** ecosystem, choosing between these strategies depends on RTO, RPO, data architecture, dependencies, operational maturity, and budget. Because the module aims to design and operate secure, observable, recoverable, and cost-controlled applications, any DR design must be tested end-to-end—covering data, compute, networking, permissions, and verified business resumption.

## 1. When Are Pilot Light or Warm Standby Needed?

A workload may need to recover from incidents such as:

- A Region remaining unavailable for an extended period.
- Misconfigurations or sweeping changes taking down the application in the primary Region.
- Security incidents forcing isolation of a production account or environment.
- Data corruption or dependent service failures forcing a move to another environment.
- Operational incidents or capacity constraints pushing primary-Region recovery beyond RTO.

Pilot light and warm standby are typically used in multi-Region DR. They differ from **high availability (HA)** within a single Region or across multiple Availability Zones. Multi-AZ keeps workloads serving when one AZ fails; multi-Region DR prepares for when the primary Region can no longer serve traffic. Both layers complement each other.

Not every workload needs a continuously running standby environment. If the business accepts hours of RTO and a 24-hour RPO, backup and restore may make more sense. If a system requires an RTO of a few minutes, warm standby may fit. If near-zero interruption is mandatory, evaluate active/active or multi-site architectures, keeping in mind that data complexity and cost increase sharply.

## 2. What Is Pilot Light?

Pilot light maintains a minimal yet critical set of components in the standby Region so the workload can be ignited when needed. The name evokes a small flame kept continuously lit: core elements stay ready, while compute or non-essential components are provisioned or scaled up during failover.

A pilot light architecture typically includes:

- A data store in the standby Region or continuous replication from the primary Region.
- Pre-provisioned VPCs, subnets, routes, security groups, and required endpoints.
- Matching IAM roles, KMS keys, secrets, and security configurations.
- Replicated or accessible AMIs, container images, packages, IaC templates, and deployment artifacts.
- Compute capacity provisioned at failover or held at minimal baseline.
- Automated runbooks to scale, deploy, validate, and shift traffic.

The key distinction is that data and core dependencies must be ready. If you only have snapshots sitting in S3 or an AWS Backup vault without a live/restorable data store standby, the solution resembles backup and restore more than pilot light.

### Example

An Orders application runs on ECS and Amazon Aurora in the primary Region. In the standby Region:

- Aurora Global Database runs a secondary cluster receiving replicated data from primary.
- VPCs, subnets, security groups, KMS keys, and secrets are pre-configured.
- ECR images and task definitions are synchronized.
- ECS clusters can be created or scaled during failover.
- Load balancers, listeners, and DNS routing are defined in IaC.

When the primary Region fails, operations promotes the secondary database, deploys ECS services, runs health checks, and routes traffic to the standby endpoint.

## 3. What Is Warm Standby?

Warm standby maintains a complete, functional deployment of the workload in the standby Region, usually running at reduced capacity compared to primary. Applications, data stores, networking, and essential dependencies are already running. On failover, operations increases instance/task/pod counts or promotes the database to accept writes, then shifts traffic.

A typical warm standby includes:

- Compute running at minimal capacity capable of serving health checks or light traffic.
- Replicated data stores ready to serve traffic via promote/failover procedures.
- Configured networking, load balancers, DNS, certificates, and IAM.
- Application artifacts and configurations matching production versions.
- Monitoring and alerts active in both primary and standby Regions.
- Automation to scale capacity, validate data, and shift traffic.

Warm standby generally cuts the time needed to launch compute and deploy apps. Still, if the database is not ready, secrets are unreadable, quotas fall short, or DNS lags, having a few EC2 instances running will not guarantee RTO.

### Example

An API application runs on ECS across two Regions. The standby Region continuously runs a small ECS service with a handful of tasks, an ALB, and connectivity to an Aurora secondary. On failure, operations raises desired counts, promotes the database, updates routing, and validates business flows.

## 4. Comparing Pilot Light and Warm Standby

| Criterion | Pilot Light | Warm Standby |
|---|---|---|
| Compute in standby Region | Idle/absent or only minimal core utilities running | Already running at reduced scale |
| Data store | Typically replicated or ready to promote/restore | Typically replicated and ready to serve per runbook |
| Activation time | Must provision/boot more components | Primarily scales capacity and shifts traffic |
| RTO | Usually longer than warm standby | Usually shorter than pilot light |
| RPO | Depends on replication/backup mechanism | Depends on replication/backup mechanism |
| Ongoing cost | Usually lower | Usually higher due to continuously running compute |
| Complexity | Needs automation to provision and configure many parts during failover | Needs live environment upkeep, version parity, and scaling automation |
| Testing | Must test full provisioning and startup sequence | Easier to probe frequently, yet must still test load scaling and failover |
| Best fit | Important workloads tolerating longer activation times | Important workloads needing faster recovery |

RPO is not automatically better with warm standby. If both designs use the same replication mechanism with identical lag, RPO can be identical. The main difference lies in compute readiness and time to begin serving traffic.

## 5. Where Both Strategies Sit on the DR Spectrum

AWS Well-Architected outlines four common multi-Region DR strategies. They represent a trade-off among readiness, recovery speed, and cost.

| Strategy | Short Description | Operational Profile |
|---|---|---|
| Backup and restore | Recover infrastructure and data from backups after an outage | Few continuous resources; longer restore and rebuild times |
| Pilot light | Keep data and core foundations; deploy compute on demand | Requires provisioning and scaling automation |
| Warm standby | Run a scaled-down, functional workload copy | Scale capacity and shift traffic at failover |
| Multi-site active/active | Multiple Regions serve traffic concurrently | Must manage consistency, conflicts, routing, and dual-Region ops |

No fixed RTO/RPO applies universally to every architecture. AWS whitepapers often describe pilot light achieving RTO in tens of minutes and warm standby in minutes when well-engineered, but actual outcomes depend on workload, data, automation, quotas, and drills. Rely on measured test results before committing.

## 6. Reference Architecture for Pilot Light

~~~mermaid
flowchart TB
    subgraph Primary["Primary Region"]
      P1[Route 53 / Global Accelerator]
      P2[ALB]
      P3[ECS or EC2 Compute]
      P4[Primary Database]
      P1 --> P2 --> P3 --> P4
    end
    subgraph DR["Standby Region - Pilot Light"]
      D1[Pre-provisioned Network and IAM]
      D2[Secondary Database / Replica]
      D3[ECR Images and IaC Artifacts]
      D4[Compute created at failover]
      D5[ALB and standby endpoint]
      D1 --> D4 --> D5
      D2 --> D4
      D3 --> D4
    end
    P4 -. Replication .-> D2
    P1 -. Failover routing .-> D5
~~~

In this diagram, data stores and security foundations are prepared in the standby Region. Compute is deployed upon failover. Depending on the service, the replica may serve read-only traffic or remain standby until promoted during an incident.

### Components to Prepare in Advance

**Network:** non-overlapping VPC CIDRs, per-AZ subnets, route tables, NAT/egress, security groups, NACLs, VPC endpoints, and hybrid connectivity where needed.

**Identity and encryption:** IAM roles, trust policies, KMS keys in the standby Region, key policies, secret replication or creation workflows, certificates, and artifact access permissions.

**Data:** database replicas, snapshot copies, backup vaults, S3 replication, DynamoDB Global Tables, or service-appropriate mechanisms.

**Application:** images, AMIs, task definitions, launch templates, IaC, runtime configurations, parameters, and versions compatible with the data schema.

**Traffic:** ALB/NLB, target groups, health checks, Route 53 records, or AWS Global Accelerator endpoints.

**Operations:** CloudWatch dashboards, alarms, logs, EventBridge, runbooks, approvers, and out-of-band communication channels.

## 7. Reference Architecture for Warm Standby

~~~mermaid
flowchart TB
    subgraph Primary["Primary Region"]
      A1[Global routing]
      A2[Load Balancer]
      A3[Compute - full capacity]
      A4[Primary Data Store]
      A1 --> A2 --> A3 --> A4
    end
    subgraph Standby["Standby Region - Warm Standby"]
      B1[Load Balancer]
      B2[Compute - minimum capacity]
      B3[Replica Data Store]
      B1 --> B2 --> B3
      B4[Monitoring and Automation]
      B4 --> B2
    end
    A4 -. Continuous / frequent replication .-> B3
    A1 -. Route traffic after validation .-> B1
~~~

Warm standby must keep an actually runnable version of the application, not just idle running compute. Application versions, configurations, schemas, secrets, and permissions must stay compatible with replicated data. If the primary Region deploys a new release while standby stays on an old build, failover can fail on compatibility mismatches.

Deploy the same release artifact via CI/CD pipelines to both Regions. Capacity differences should be parameterized per environment rather than letting the two Regions drift onto incompatible codebases.

## 8. Designing Data Replication

Data replication drives RPO. Determine whether data replicates synchronously or asynchronously, whether it promotes in place or must be restored, and how in-flight writes behave during cutover.

| Service | Available Mechanisms | Items to Verify |
|---|---|---|
| Amazon Aurora | Aurora Global Database or snapshot/copy as needed | Replication lag, secondary clusters, promotion, and failover |
| Amazon RDS | Cross-Region read replicas or snapshot copies per supported engine | Engine/version, lag, promotion, backups, and connection endpoints |
| DynamoDB | Global Tables or backup/restore | Conflict resolution, consistency modes, replica Regions, and write routing |
| Amazon S3 | Cross-Region Replication (CRR) or Same-Region Replication (SRR) | Replication status, delete markers, versioning, Object Lock, and KMS |
| EBS | Cross-Region snapshot copies | Snapshot frequency, copy duration, encryption keys, and volume creation |
| EFS | AWS Backup or replication solutions matching requirements | File consistency, restore targets, throughput, and metadata |
| OpenSearch Service | Cross-Cluster Replication or snapshot/restore per design | Cluster versions, index mappings, lag, and access permissions |

Not all replicating services guarantee zero data loss. Asynchronous replication incurs lag; data not yet transmitted to the destination Region at failure time can be lost. For tight RPOs, monitor lag and establish procedures to fence writes or reconcile transactions upon promotion.

### Replication and Backups Must Complement Each Other

Replication keeps a fresh copy to minimize cutover time. Backups retain historical recovery points to roll back before deletions, bad writes, or encryption attacks. If an unintended valid deletion replicates immediately, a replica cannot recover the pre-deletion state.

For critical data, combine:

- Replication to hit RTO/RPO for Regional outages.
- Periodic backups or point-in-time recovery for logic errors.
- Cross-account or immutable backup copies to guard against unauthorized deletion.
- Restore tests to prove data integrity and accessibility.

## 9. Synchronizing Non-Data Dependencies

A DR environment only functions when non-database components are ready too.

| Dependency | How to Prepare in the Standby Region |
|---|---|
| VPC and subnets | Manage via IaC; verify CIDRs and routes |
| Security groups/NACLs | Sync policies and audit ingress/egress rules |
| IAM roles | Provision matching roles and trust policies; verify service principals |
| KMS | Create Regional keys in the target Region; sync key policies and grants |
| Secrets Manager | Enable replication or provision secrets via controlled pipelines |
| Parameter Store | Sync parameters via IaC/pipelines; verify SecureStrings and KMS |
| Container images | Enable ECR replication or copy images by digest |
| AMIs | Copy AMIs and backing snapshots to the standby Region |
| Certificates | Issue or import valid certificates in the target Region |
| DNS | Pre-configure records, health checks, TTLs, and update permissions |
| Service quotas | Verify compute, ENI, IP, load balancer, and database quotas |
| Observability | Provision log groups, alarms, dashboards, and log shipping permissions |

KMS keys are Regional resources. A key ARN in the primary Region cannot function as a local key in the standby Region. When copying encrypted snapshots or replicas, specify destination keys and policies for restore services.

## 10. Shifting Traffic During Failover

Once standby data stores and applications are ready, route traffic to the new endpoint. Two common options are Amazon Route 53 and AWS Global Accelerator.

### Route 53

Route 53 supports failover routing policies using primary/secondary records and health checks. When the primary endpoint fails health criteria, DNS can return the secondary endpoint. Watch DNS caching and TTLs: clients or intermediate resolvers may keep caching old addresses for some time.

Health checks must measure real business readiness. An endpoint returning HTTP 200 while the database rejects writes or payment processing fails should not be treated as healthy for routing purposes.

### AWS Global Accelerator

Global Accelerator provides static anycast IPs routing to endpoints via health checks and traffic dials. It shifts traffic across Regions without changing client-facing public IPs. Pre-provision accelerators, listeners, endpoint groups, and health checks before incidents strike.

### AWS Application Recovery Controller

AWS Route 53 Application Recovery Controller (ARC) provides routing controls and readiness checks to govern multi-Region failover. Routing controls operate via API or console per runbooks; do not treat ARC as an autonomous decision-maker for every incident. Readiness checks verify selected resource quotas and configs, yet never replace full application drills.

### Traffic Cutover Sequence

1. Confirm the primary Region is unfit to serve traffic.
2. Prevent both Regions from accepting concurrent writes unless the architecture supports active/active.
3. Promote the database or verify the replica accepts writes.
4. Scale compute and verify health checks.
5. Verify authentication, secrets, payments, queues, and dependencies.
6. Shift traffic using Route 53, Global Accelerator, or ARC routing controls.
7. Monitor error rates, latency, transactions, and logs post-cutover.

Never flip DNS simply because standby instances booted. Confirm the data plane and critical business flows are genuinely ready.

## 11. Failover Runbook for Pilot Light

A sample runbook can be divided into phases:

| Phase | Action | Exit Criteria |
|---|---|---|
| Declare | Confirm incident and approve DR activation | Incident commander assigned and scope agreed |
| Fence primary | Block writes or incoming traffic to primary Region if needed | No dual-primary split-brain risk |
| Promote data | Promote replica or restore data store | Data store ready to serve |
| Provision | Launch compute, load balancers, and missing dependencies | Required resources provisioned |
| Configure | Attach IAM roles, secrets, KMS, and app configs | Workload reads dependencies cleanly |
| Validate | Run health checks and business smoke tests | Synthetic transactions succeed and data is consistent |
| Route | Cut over traffic | Requests reach the standby Region |
| Observe | Monitor and communicate status | Error rates/latency stable; owner signs off |

Automation can leverage AWS Systems Manager Automation, Step Functions, Lambda, or IaC pipelines. Each step requires timeouts, retries, logging, idempotency, and abort conditions. High-risk steps like database promotion or routing shifts need guardrails to prevent accidental duplicate execution.

## 12. Failover Runbook for Warm Standby

Warm standby skips or compresses compute provisioning because the application already runs at minimal scale. Still, you must scale capacity and verify data stores.

1. Declare incident and decide to fail over.
2. Fence the primary Region or lock write paths if needed.
3. Promote data stores in the standby Region.
4. Scale ECS services, EKS node groups/deployments, or EC2 Auto Scaling groups to target capacity.
5. Adjust connection pools, worker concurrency, and downstream rate limits.
6. Verify ALB target health, application health, and representative transactions.
7. Shift traffic.
8. Monitor load, errors, queue depth, database connections, and replication.

Warm standby must be tested at realistic load. A service running one task can look healthy with zero traffic while collapsing once production users arrive. Verify scaling speed and quotas ahead of incidents.

## 13. Failback: Returning to the Primary Region

Failback restores operations back to the primary Region once repaired. Failback can be riskier than failover if data direction and primary/secondary roles are mishandled.

Before failing back:

- Confirm the original incident root cause is resolved.
- Verify the primary Region holds sufficient capacity and dependencies.
- Synchronize new data from the active DR Region back to the primary Region.
- Check replication lag and consistency.
- Plan write freezes or cutover steps that avoid losing transactions.
- Verify application versions, schemas, and secrets.
- Prepare a rollback plan if failback fails.

A safe failback sequence typically follows:

1. Keep the DR Region as primary while repairing the original Region.
2. Replicate/sync data from DR back to the primary Region.
3. Validate the application in the primary Region against current data.
4. Execute a controlled cutover preventing dual-primary writes.
5. Shift traffic back to the primary Region.
6. Monitor and verify transactions.
7. Re-establish DR replication in the original direction.

Never assume failback is just flipping DNS back. Once a database was promoted in the DR Region, replication topology and endpoints may have inverted.

## 14. Security in the DR Environment

The standby Region sits inside the production security boundary. If the DR environment carries looser permissions or weaker monitoring, attackers may exploit it as a side door.

Key principles:

- Use dedicated least-privilege IAM roles for failover automation.
- Guard database promotion and DNS changes behind proper approvals.
- Keep KMS key policies and secret access in the standby Region strictly least-privilege.
- Protect backup vaults and replication targets from unauthorized deletion or tampering.
- Enable CloudTrail and automation logging in both Regions.
- Ensure security groups, WAF, network firewalls, and endpoint policies match production standards.
- Verify images, packages, and IaC artifacts originate from trusted sources.
- Maintain controlled break-glass access and test it periodically.

If DR activates due to a security breach rather than a Regional outage, never replicate a potentially compromised workload as-is into the new environment. Locate a clean recovery point, rebuild from trusted artifacts, rotate credentials, and investigate persistence before returning to service.

## 15. Monitoring and Readiness of the Standby Region

A warm standby environment can fail silently if it receives no regular traffic. Pilot light can suffer configuration drift or stale images. Continuous monitoring is essential.

Monitor:

- Replication lag, replica health, and promotion readiness.
- Backup/copy job statuses and recovery point ages.
- ECS/EKS/EC2 health and scaling headroom.
- Load balancer health checks and TLS certificates.
- KMS key enabled states, IAM policy drift, and secret availability.
- Route 53 health checks, Global Accelerator endpoint health, or ARC routing control states.
- Service quotas, subnet IP availability, and ENI limits.
- Log delivery, metrics, alarms, and notification pipelines.

Readiness checks never replace failover drills. Only an end-to-end drill proves all steps coordinate within RTO/RPO.

## 16. DR Drills and Validating RTO/RPO

Escalate testing progressively:

1. **Component tests:** restore a database, launch instances from AMIs, replicate images, or verify secrets in the target Region.
2. **Partial failover:** bring up the application in the standby Region without shifting full live traffic.
3. **Traffic-shift tests:** divert a controlled percentage or full traffic per plan.
4. **Regional game days:** simulate primary Region unavailability and execute the full runbook.
5. **Failback drills:** verify moving data and workloads back safely.

Log timestamps for declaration, data readiness, application readiness, traffic switch, and business validation. Compare elapsed time to RTO and data cutoff to RPO. Never count an automation script returning exit code zero as full verification.

### Failures to Deliberately Inject and Test

- Replica lag exceeding RPO.
- KMS key in destination Region disabled or lacking policy permissions.
- Secret not yet replicated.
- Image or AMI missing in destination Region.
- Subnet IP exhaustion or quota shortfall.
- Health check passing HTTP while database rejects writes.
- DNS resolvers caching records longer than expected.
- Automation re-running mid-flight or halting halfway.
- Primary Region returning online while DR is actively taking writes.
- Logs and alerts failing to reach on-call responders.

## 17. Cost and Optimization

Pilot light generally costs less than warm standby because little or no compute runs continuously in the standby Region. However, ongoing expenses still include database replicas, storage, snapshot copies, KMS, networking, artifact replication, load balancers, and monitoring.

Warm standby incurs additional compute, load balancer, database capacity, networking, and telemetry charges from running continuously at reduced scale. On failover, capacity must scale quickly; keeping high baseline capacity to dodge scale delays pushes costs closer to full dual-production.

Cost control practices:

- Distinguish which components must run continuously versus which can spin up at failover.
- Use minimal capacity sufficient for health checks and smoke tests.
- Track data replication, snapshot copy, and cross-Region transfer costs.
- Use IaC to provision test resources cleanly and tear them down promptly.
- Benchmark scale-out speed and verify quotas before trimming baseline capacity.
- Audit backup retention and lifecycles.
- Apply cost-center, environment, and workload tags across both Regions.
- Track DR spend separately to compare standby readiness cost against failover cost.

Never trim standby capacity below what is proven to meet RTO. DR cost is an investment calibrated against the downtime and data loss tolerances approved by the business.

## 18. Selection Example: Orders Requiring a 20-Minute RTO

An e-commerce platform sets a 20-minute RTO and 5-minute RPO for its Orders service. The workload runs on ECS and Aurora; invoices live in S3; configurations reside in Parameter Store and Secrets Manager.

**Pilot light** can be chosen if:

- An Aurora Global Database secondary stays active with lag within limits.
- VPCs, IAM, KMS, secrets, ECR images, and load balancers are pre-provisioned.
- ECS services deploy via pipelines/runbooks during failover.
- Provisioning and warm-up durations are measured well inside the RTO budget.

**Warm standby** can be chosen if:

- ECS services and ALBs already run in the standby Region at minimal capacity.
- The Aurora secondary is ready for promotion.
- Periodic smoke tests confirm connectivity to the database and downstream services.
- Failover requires only promoting, scaling, and shifting traffic within the 20-minute budget.

If a pilot light drill takes 35 minutes to spin up compute and verify checkout, it fails the 20-minute RTO. The team can either move to warm standby, increase automation, or renegotiate RTO with the business based on BIA.

| Item | Pilot Light | Warm Standby |
|---|---|---|
| Aurora secondary | Maintained | Maintained |
| ECS service | Created at failover | Running at minimal capacity |
| ALB | Created at failover or pre-provisioned | Already running |
| ECR images | Replicated | Replicated |
| KMS/Secrets | Pre-provisioned | Pre-provisioned |
| Failover actions | Deploy, scale, promote, validate, route | Promote, scale, validate, route |
| Ongoing cost | Lower | Higher |
| Actual RTO | Must measure deploy/warm-up duration | Must measure scale and cutover duration |

Never conclude warm standby meets RTO from a diagram alone. Rehearse both designs with realistic data, load, and operational steps.

## 19. Pilot Light and Warm Standby Implementation Checklist

- [ ] RTO, RPO, and outage scope are approved by the business.
- [ ] Pilot light or warm standby is selected based on BIA and cost.
- [ ] Standby Region has required quotas and capacity.
- [ ] VPCs, subnets, routes, security groups, and endpoints are pre-configured.
- [ ] IAM roles, KMS keys, secrets, certificates, and parameters are ready.
- [ ] Database replication/backups meet RPO with lag alerting.
- [ ] Container images, AMIs, IaC, and deployment artifacts are synchronized.
- [ ] Standby compute can provision or scale within the RTO budget.
- [ ] Load balancers, DNS, Global Accelerator, or ARC are configured.
- [ ] Monitoring, logs, alerts, and access work in the standby Region.
- [ ] Runbooks include preconditions, approvals, timeouts, retries, and idempotency.
- [ ] Mechanisms exist to prevent split-brain and handle writes during cutover.
- [ ] Failback and reverse data-sync plans exist.
- [ ] Independent backups and immutable copies are protected.
- [ ] Component, failover, traffic-shift, and failback drills have been executed.
- [ ] Actual RTO/RPO are measured and reported to owners.
- [ ] Standby readiness costs and failover costs are tracked.

## 20. Key Takeaways

Pilot light keeps data and core foundational pieces ready, provisioning or scaling compute at failover. Warm standby runs a scaled-down yet operational workload continuously, scaling capacity and shifting traffic when needed. Warm standby typically yields shorter RTO at higher ongoing cost.

RPO in both strategies depends primarily on how data is backed up or replicated; running idle compute does not automatically improve RPO. Both approaches require preparing IAM, KMS, networking, secrets, artifacts, quotas, DNS, monitoring, and runbooks. Pair replication with independent backups to guard against replicated corruption or deletions.

Choose a strategy via BIA, RTO/RPO, and cost; monitor readiness continuously; rehearse failover and failback; and measure elapsed time until business operations safely resume. A DR environment has value only when proven capable of taking production load within committed objectives.

## References

- [AWS Well-Architected: Disaster Recovery (DR) Objectives](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/disaster-recovery.html)
- [AWS Well-Architected: Use Defined Recovery Strategies](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_planning_for_recovery_disaster_recovery.html)
- [Disaster Recovery of Workloads on AWS: Pilot Light](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/pilot-light.html)
- [Disaster Recovery of Workloads on AWS: Warm Standby](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/warm-standby.html)
- [Amazon Aurora Global Database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database.html)
- [Amazon RDS Cross-Region Read Replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.XRgn.html)
- [Amazon DynamoDB Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html)
- [Amazon S3 Replication](https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication.html)
- [Amazon ECR Replication](https://docs.aws.amazon.com/AmazonECR/latest/userguide/replication.html)
- [AWS Elastic Disaster Recovery](https://docs.aws.amazon.com/drs/latest/userguide/what-is-drs.html)
- [Amazon Route 53 Failover Routing](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-policy-failover.html)
- [AWS Global Accelerator](https://docs.aws.amazon.com/global-accelerator/latest/dg/what-is-global-accelerator.html)
- [AWS Application Recovery Controller](https://docs.aws.amazon.com/r53recovery/latest/dg/what-is-route53-recovery.html)
- [AWS Backup Cross-Region Backup](https://docs.aws.amazon.com/aws-backup/latest/devguide/cross-region-backup.html)
- [AWS Backup Vault Lock](https://docs.aws.amazon.com/aws-backup/latest/devguide/vault-lock.html)
