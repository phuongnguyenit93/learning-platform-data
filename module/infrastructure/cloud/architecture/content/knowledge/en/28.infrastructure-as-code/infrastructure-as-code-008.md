# Immutable Infrastructure Design and Safe Resource Replacement

A virtual machine, Kubernetes node, or database instance that runs for a long time accumulates changes: packages installed manually, configuration files edited in place, security groups opened temporarily, and runtime versions drifting from the original build. When scaling or recovering, operations teams no longer know which exact configuration produced the running resource. In-place fixes may resolve an immediate incident, yet they make the environment progressively harder to reproduce and verify.

**Immutable infrastructure** solves this by provisioning new resources from a tested definition and artifact, shifting workloads onto the new resources, and retiring the old resources after verification. Changes are deployed as new versions rather than manually editing running servers. This approach aligns with Infrastructure as Code (IaC), immutable images, deployment automation, and replacement strategies such as blue-green or canary.

Safe resource replacement requires more than launching a new VM. It must preserve identities, networking, secrets, data, connections, state, DNS, permissions, and rollback capability. For databases or stateful resources, you cannot simply terminate the old instance the moment the new one boots. This lesson explains how to design controlled replacement workflows that avoid downtime, data loss, split-brain, and lingering orphan costs.

This lesson belongs to the **Infrastructure as Code** chapter of the **CLOUD_ARCHITECTURE** module. The focus is designing cloud architectures that can be reproduced, replaced, and recovered safely while balancing reliability, security, scalability, cost, and operations under Well-Architected principles.

## 1. Learning objectives

After this lesson, learners will be able to:

1. Explain immutable infrastructure and contrast it with in-place modification.
2. Distinguish resources suited for replace-on-change from resources requiring dedicated migration strategies.
3. Design IaC modules, artifacts, and pipelines with versioning, reviews, and validation.
4. Safely manage state, resource identities, dependencies, and drift.
5. Choose rolling, blue-green, canary, or replacement strategies based on workload and SLOs.
6. Design cutover, health gates, rollbacks, and controlled cleanup.
7. Protect data, secrets, encryption keys, networking, and workload identities during replacement.
8. Replace VMs, container nodes, load balancers, databases, and stateful resources according to their semantics.
9. Measure replacement effectiveness, detect drift, and rehearse failure scenarios.

## 2. What is immutable infrastructure?

### 2.1. Version-replacement mindset

In a mutable approach, operators log into running machines to install packages, edit files, or upgrade runtimes. Over time, two machines serving the same role diverge because of differing operational histories. In an immutable approach, when a change is needed, the pipeline builds a new image or artifact, provisions a fresh group of resources, verifies them, and shifts traffic.

~~~mermaid
flowchart LR
    OLD[Old image v1] --> OLDVM[Running instances v1]
    CHANGE[Code and config change] --> BUILD[Build image v2]
    BUILD --> TEST[Test and scan]
    TEST --> NEW[Create instances v2]
    NEW --> HEALTH[Health and smoke checks]
    HEALTH --> SWITCH[Switch traffic]
    SWITCH --> RETIRE[Retire v1 after safety window]
~~~

Old resources are retained during a safety window for verification or rollback per policy, then retired afterward. Never patch image v1 in place into v2; v2 is built fresh from a repeatable definition.

### 2.2. Immutable does not mean unchanging

Infrastructure still changes frequently. The difference is that every change is expressed as a new version with provenance and a release workflow. Examples:

- OS package update: build a new image.
- Application code change: build a new artifact and deploy.
- Instance size change: create replacements per rollout policy.
- Network policy change: update IaC/config, review the plan, and apply.
- Database engine version change: follow a dedicated upgrade/migration procedure.

Not every resource can be replaced immediately. A database holding transactional data, a stateful volume, or an allowlisted IP address requires transition procedures that preserve consistency.

### 2.3. Mutable operations still have a place

Certain runtime values naturally need updates: autoscaling desired capacity, secret rotation, certificate renewal, feature flags, routing weights, or business data. Immutable infrastructure does not forbid these operational updates. It requires distinguishing among:

- Managed, controlled configuration changes.
- Data or runtime state intentionally designed to vary.
- Uncontrolled manual edits that cause drift from the canonical definition.

The goal is eliminating snowflake servers and out-of-band edits—not forcing every value in the system to be strictly immutable.

## 3. Why is safe resource replacement necessary?

### 3.1. Snowflake infrastructure

A snowflake is a resource with a bespoke configuration accumulated through ad-hoc edits. It may still run, yet no longer matches current IaC or images. When scaling or rebuilding, the team cannot tell which differences are essential and which were accidental.

### 3.2. Risks of in-place modification

- Changes cannot be reproduced across other environments.
- Rollback is difficult because the prior state is unknown.
- Patches or packages diverge across instances.
- Audit logs fail to capture every manual operation.
- Newly provisioned instances do not match older ones.
- After a security compromise, lingering persistence mechanisms are hard to spot.

### 3.3. Benefits of replacement

Resources provisioned from standard artifacts are easy to test, scale horizontally, replace on failure, and recover after incidents. Batch rollouts limit blast radius. Changes can be measured, approved, and recorded as formal releases.

### 3.4. Trade-offs

An immutable model typically requires temporary headroom to run old and new resources concurrently, artifact registries/storage, pipelines, and automation. Stateful resources require more intricate migrations. DNS, caches, and sessions can prevent instantaneous cutovers. Design must therefore balance safety, transition duration, cost, and recoverability.

## 4. Classifying resources prior to replacement

Do not apply a single replacement strategy to every resource. Classify by replaceability and statefulness:

| Resource group | Example | Typically suitable strategy | Risks to manage |
|---|---|---|---|
| Stateless compute | API VMs, container replicas | Rolling, blue-green, canary | Sessions, connection draining, capacity |
| Cluster nodes | Kubernetes workers, autoscaling group members | Cordon/drain and replace | Pod disruption, local storage, topology |
| Edge/networking | Load balancers, gateways, routes, WAF | Parallel resources and routing cutover | IPs, DNS, allowlists, active connections |
| Stateful storage | Databases, volumes, object stores | Replication, migration, failover | Data consistency, encryption, retention |
| Control plane | IAM roles, registries, IaC state backends | Staged policy/config migration | Lockouts, privilege escalation, state corruption |
| External dependencies | DNS registrars, SaaS integrations | Reconfigure/reissue/reconcile | Ownership, credentials, SLAs |

### 4.1. Stateless compute

Stateless compute is the cleanest candidate for immutable replacement. When request state lives outside the instance, new instances can take traffic right after passing health checks. Still, ensure graceful shutdown, connection draining, session handling, and version compatibility.

### 4.2. Stateful resources

Databases, queues, and volumes cannot be treated like stateless VMs. Creating a new resource does not automatically migrate data. Depending on the service, you need backup/restore, replication, CDC, snapshots, application-level migration, or failover. Explicitly define the authoritative data source and write owner at every phase.

### 4.3. Control-plane resources

IAM policies, DNS zones, KMS keys, and state backends can impact an entire environment. Replacing them requires staged rollouts, break-glass access, and strict dependency ordering. Never delete the old resource before proving the new resource works and access remains intact.

## 5. IaC as the canonical source of definition

### 5.1. Desired state and actual state

IaC declares desired state: resource types, images/versions, networking, identities, scaling, encryption, and dependencies. Providers/APIs materialize real resources from that definition. Pipelines compare desired state against actual state to detect changes.

~~~mermaid
flowchart TD
    CODE[Versioned IaC] --> REVIEW[Review and policy checks]
    REVIEW --> PLAN[Plan / preview]
    PLAN --> APPROVE[Approval]
    APPROVE --> APPLY[Apply to target]
    APPLY --> ACTUAL[Cloud resources]
    ACTUAL --> DRIFT[Drift detection]
    DRIFT --> CODE
~~~

IaC is the canonical source for managed configuration, yet it does not replace real-time inventory. When drift occurs, investigate the cause and reconcile; never auto-apply plans that risk deleting or replacing critical resources.

### 5.2. Modules and interfaces

Modules should have clear inputs/outputs, validation, and safe defaults. Avoid overly generic modules crammed with conflicting flags. Typical inputs include:

- Target environment/region/account.
- Instance class or compute profile.
- Image digest/version.
- Network/subnet/security policies.
- Workload identity/service account.
- Encryption key references.
- Scaling and health check settings.
- Owner, service, cost-center, and lifecycle tags/labels.

Outputs should expose only necessary metadata such as resource IDs, endpoints, or placement—never plaintext secrets.

### 5.3. Versioning modules and providers

Pin module and provider versions so deployments remain reproducible. Update versions via pull requests, review release notes, test in sandbox/canary environments, and inspect plans before production. Avoid floating branches or unbounded version ranges for sensitive infrastructure modules.

### 5.4. Resource names and identities

Resource names should be stable, namespaced by environment/service, and free of sensitive data. Yet stable logical naming does not mean every replacement must keep the same physical resource ID. With parallel deployments, new resources require distinct physical identities before routing shifts over. Define which resources maintain stable logical identities versus generation-scoped physical identities.

## 6. State files, locking, and lifecycles

### 6.1. Role of IaC state

Some IaC tools store state to bind cloud resources to code declarations. State can hold resource IDs, sensitive attributes, and critical metadata. Losing state can leave the tool blind to existing resources; two pipelines writing state concurrently can corrupt mappings.

### 6.2. Safe state management

- Use a remote backend with encryption and access controls.
- Enable locking/leases where supported by the backend.
- Version state and protect backups.
- Separate state by environment, stack, or ownership boundary.
- Never commit state containing sensitive values to source repos.
- Restrict which users/roles can read or write state.
- Maintain audit logs and a state recovery procedure.

### 6.3. Preventing concurrent applies

Never allow two pipelines to apply the same state scope simultaneously. Locks require timeouts and a stale-lock handling procedure. Never clear a lock manually without confirming the previous pipeline has stopped; doing so can create dual writers.

### 6.4. Importing and reconciling

If a resource already exists outside state, importing/adopting it requires reviewing mappings and ownership. Never let a new module accidentally claim resources owned by another stack. Before importing, verify account, region, resource ID, and lifecycle owner.

## 7. Building immutable artifacts

### 7.1. Machine images and container images

Build standardized images through controlled pipelines:

- Base images from trusted sources, pinned by digest/version.
- Packages installed from lockfiles or approved repositories.
- Configured users, filesystems, agents, and runtimes.
- Vulnerability and secret scanning.
- Attached build metadata/provenance.
- Signed artifacts where required by policy.
- Published with immutable versions/digests.

Never rely on mutable tags like `latest` as the sole production reference. Record exact image IDs/digests in release manifests.

### 7.2. Separating images from runtime configuration

Images contain the application and environment-agnostic base components. Runtime configuration such as endpoints, feature policies, and secrets are injected at deploy time from config/secret managers. Never bake production passwords, private keys, or environment-specific config into images.

### 7.3. Reproducibility

Builds should use pinned versions, lockfiles, and controlled dependency mirrors. Identical source and toolchains should produce verifiable artifacts. Even where bitwise-reproducible builds are impractical, recording commits, builders, dependencies, digests, and provenance enables investigation.

## 8. Designing deployment strategies

### 8.1. Rolling replacement

Gradually replace instances or replicas within the same pool. Remove only a portion of capacity at a time, provision new instances, and wait for health checks before proceeding.

~~~mermaid
flowchart TD
    A[Pool all v1] --> B[Create v2 capacity]
    B --> C[Wait healthy]
    C --> D[Drain subset v1]
    D --> E[Route to v2]
    E --> F{Enough healthy capacity?}
    F -->|Yes| G[Repeat for next subset]
    G --> H[Pool all v2]
    F -->|No| R[Pause / rollback / repair]
~~~

The advantage is requiring less spare capacity than blue-green. The trade-off is running multiple versions simultaneously during the rollout; application and database protocols must stay backward-compatible across that window. If any batch fails, halt the rollout instead of continuing to drain healthy instances.

### 8.2. Blue-green deployment

Provision a new environment (green) alongside the existing environment (blue). Deploy and test green, then switch traffic over to green. Retain blue for a rollback window before retiring it.

~~~mermaid
flowchart LR
    USERS[Users] --> ROUTER[Traffic router]
    ROUTER --> BLUE[Blue v1]
    ROUTER -. after cutover .-> GREEN[Green v2]
    GREEN --> CHECK[Smoke and business validation]
    CHECK --> KEEP[Keep blue during rollback window]
    KEEP --> CLEAN[Retire blue after approval]
~~~

Blue-green offers clean cutovers and rapid routing rollbacks when data remains compatible. Its downside is needing nearly double capacity during parallel operation, which is especially costly for databases or dedicated appliances. Once green accepts new writes, rolling back to blue requires reverse replication or reconciliation; merely flipping routing back risks data loss.

### 8.3. Canary deployment

Release the new version to a small percentage of traffic or a subset of users first. Observe error rates, latency, saturation, and business metrics. Ramp traffic incrementally if thresholds pass; halt or roll back if negative signals appear.

Canary fits workloads with sufficient traffic volume, precise routing, and cohort-differentiated metrics. For low-traffic workloads, canary signals may lack statistical significance.

### 8.4. Choosing a strategy

| Criterion | Rolling | Blue-green | Canary |
|---|---|---|---|
| Temporary capacity | Moderate | High | Depends on percentage |
| Isolation of new version | Partial | High | By cohort |
| Rollback | Reverse rollout or redeploy | Switch route if state compatible | Reduce traffic back to old version |
| Mixed versions | Typically present | Avoidable per environment | Intentional |
| Metric requirements | Health checks | Smoke tests and readiness | Cohort-level metrics |
| Best suited for | Stateless, version-compatible services | Major releases needing clean cutover | Risky changes needing live-traffic validation |

## 9. Health gates and readiness conditions

### 9.1. Liveness, readiness, and startup

- Liveness determines whether a process is alive so the runtime knows when to restart it.
- Readiness determines whether an instance can accept traffic.
- Startup probes protect slow-starting apps from premature liveness restarts.

Health endpoints should not blindly return 200 just because a process is running. Readiness should check essential dependencies per policy while avoiding heavy, frequent queries that overload databases.

### 9.2. Smoke tests

Once new resources are healthy, run controlled business checks:

- Authentication and authorization.
- Sample reads or non-mutating health transactions.
- Connectivity to databases, queues, and object storage.
- Certificates and outbound integrations.
- Metrics, logs, and traces actively exporting.
- Schema and configuration version compatibility.

### 9.3. SLO gates

Pre-define rollout halt thresholds: error rates, p95/p99 latency, saturation, restart counts, queue lag, or business failures. Compare against baselines and control groups. Do not rely solely on green health checks.

### 9.4. Stabilization windows

An instance may pass health checks right at startup yet fail minutes later from memory leaks, cache warm-up issues, or background workers. Keep stabilization windows long enough to catch delayed failures before retiring old capacity.

## 10. Safely replacing stateless compute

### 10.1. Workflow

1. Build and verify the new image/version.
2. Confirm capacity, quotas, subnet IPs, and load balancer targets.
3. Provision new instances/pods with proper identities and security policies.
4. Wait for startup/readiness probes and smoke tests.
5. Route a slice of traffic to the new version.
6. Monitor SLOs, business metrics, logs, and traces.
7. Drain connections/sessions from the old version.
8. Continue replacing remaining instances in batches.
9. Retain rollback targets for the defined window.
10. Delete old instances and temporary resources after approval.

### 10.2. Graceful shutdown

Before terminating an instance:

- Stop accepting new requests.
- Drain keep-alive connections and in-flight requests.
- Stop claiming new queue messages.
- Complete or release leases on active jobs.
- Flush telemetry/buffers within a bounded timeout.
- Handle `SIGTERM` and shutdown hooks properly.

Abrupt termination causes retried requests, duplicate message processing, or interrupted transactions.

### 10.3. Sessions and sticky connections

If sessions live in instance memory, replacement drops user sessions or logs users out. Prefer external session stores or stateless tokens with proper rotation. For WebSockets or long-lived TCP connections, allow sufficient connection draining and reconnect timeouts.

## 11. Node and cluster replacement

### 11.1. Kubernetes nodes

Replace nodes using a controlled sequence:

1. Provision new nodes with verified images, kubelet versions, and policies.
2. Verify node `Ready` status, labels, taints, CNI, and storage drivers.
3. Cordon old nodes to prevent scheduling new pods.
4. Drain cleanly while respecting `PodDisruptionBudget` and local state.
5. Verify workloads reschedule and stabilize.
6. Terminate old nodes after confirming no stateful workloads require retention.

### 11.2. Pod disruption

`PodDisruptionBudget` limits how many pods of an eligible workload can be disrupted simultaneously. It does not guarantee the application has sufficient replicas or a healthy database. Check replica counts, topology spread constraints, zone failures, and cluster capacity before draining.

### 11.3. Local storage and daemons

Pods using local ephemeral storage can lose data when nodes are replaced. `DaemonSet` workloads, local PVs, and stateful workloads follow different rules than stateless `Deployment` workloads. Identify data that must be migrated, backed up, or kept pinned before draining.

## 12. Replacing load balancers, IPs, and DNS

### 12.1. Parallel edge resources

When replacing a load balancer or gateway, provision the new resource in parallel and register new targets. Validate TLS, health checks, WAF, header handling, timeouts, and routing policies before switching DNS or frontend references.

### 12.2. IPs and allowlists

If the provider assigns new IPs, partners or external firewalls may not have allowlisted them yet. Use static/reserved IP addresses, update partner allowlists ahead of cutover, or keep both old and new IPs active during the transition.

### 12.3. DNS TTL is not an exact cutover timer

Clients, resolvers, and applications may cache DNS beyond the published TTL. Lowering TTL before cutover reduces cache duration somewhat, yet never guarantees every client updates immediately. Keep old endpoints running during an overlap window where possible and monitor residual traffic hitting the old endpoint.

### 12.4. Connection draining

DNS cutovers do not migrate already-open TCP connections. Load balancers need connection draining/termination policies; clients need reconnect/backoff logic; in-flight sessions and requests must finish within SLOs.

## 13. Replacing databases and stateful resources

### 13.1. Never apply stateless rolling patterns

Databases hold authoritative state. Creating a new instance does not replicate data automatically. Use one of these approaches:

- Snapshot/restore when downtime is acceptable.
- Native replication or managed database replica promotion.
- Logical replication/CDC to stream deltas.
- Database engine upgrades following compatibility/migration procedures.
- Partition/shard migration by tenant or data range.

### 13.2. Replication and cutover workflow

~~~mermaid
flowchart TD
    SRC[Current primary] --> SNAP[Initial snapshot / replication]
    SNAP --> DEST[New database target]
    SRC --> DELTA[Replicate ongoing changes]
    DELTA --> DEST
    DEST --> VALIDATE[Validate schema and data]
    VALIDATE --> LAG{Replication lag acceptable?}
    LAG -->|No| WAIT[Wait / tune / abort]
    WAIT --> DELTA
    LAG -->|Yes| FREEZE[Quiesce writes]
    FREEZE --> FINAL[Apply final delta]
    FINAL --> PROMOTE[Promote new primary]
    PROMOTE --> ROUTE[Switch application endpoint]
    ROUTE --> VERIFY[Smoke test and reconcile]
~~~

### 13.3. Write ownership and split-brain

At every instant, only one primary/write owner may exist. During cutover:

- Pause or lock writes at the source.
- Drain in-flight transactions.
- Wait for replication lag to drop within acceptable bounds.
- Apply the final delta.
- Fence the old source so it cannot accept writes.
- Promote the target and switch endpoints/secret references.
- Verify application behavior and business invariants.

If two databases accept independent writes concurrently, data diverges. Switching DNS alone without fencing the old primary is never sufficient.

### 13.4. Rolling back after the target database accepts writes

Once the new target accepts live transactions after cutover, switching back to the old source risks losing data. Pre-plan reverse replication, a verified dual-write protocol, or forward recovery. If safe reverse synchronization is impossible, the rollback window closes the moment new writes arrive; fix issues forward on the new primary instead of blindly reverting to the old source.

### 13.5. Schema compatibility

During rolling deployments, old and new application versions run side by side. Use expand-and-contract:

1. Expand the schema in a way backward-compatible with the old app.
2. Deploy the new app reading/writing the expanded schema.
3. Shift all traffic and background workers.
4. Confirm zero consumers rely on the old schema.
5. Contract/drop old columns or constraints in a later release.

Never combine dropping old schema elements with deploying new app code while mixed versions coexist.

## 14. Secrets, identities, and encryption during replacement

### 14.1. Workload identity

New resources need their own identities or properly scoped workload identities. Never clone machines carrying long-lived credentials from old instances without rotation/revocation controls. Once old instances retire, revoke obsolete credentials, sessions, and certificates.

### 14.2. Secret delivery

Runtimes fetch secrets from a secret manager via workload identity; secrets must never be baked into images or plaintext IaC state. Verify network paths, permissions, and secret versions prior to cutover.

### 14.3. Key compatibility

If existing data was encrypted with an older key, new instances need decrypt access to that key version. Never delete a key merely because new instances were created. During key rotation, enforce an overlap period and verify readability of historical data.

### 14.4. Revocation after retirement

Once old resources stop serving traffic:

- Revoke unnecessary roles and credentials.
- Remove obsolete authorized keys and certificates per policy.
- Remove firewall rules or allowlists dedicated solely to old endpoints.
- Check whether old snapshots/images contain secrets.
- Retain audits and evidence per retention policy.

## 15. Drift detection and remediation

### 15.1. What is drift?

Drift is divergence between desired state in IaC and actual cloud resource state. Causes include console edits, external automation, provider default changes, or out-of-band resource updates.

### 15.2. Classifying drift

- **Expected operational change:** autoscaling counts, runtime status, or ephemeral addresses designed to fluctuate.
- **Approved change not yet in IaC:** an emergency fix with a ticket whose source of truth has not been updated yet.
- **Unapproved change:** edits made outside authorized permissions or workflows.
- **Provider-managed change:** attributes adjusted by the provider as part of service behavior.

Not every diff warrants resetting back to IaC. Understand resource semantics before remediating.

### 15.3. Remediation workflow

1. Detect drift and identify the resource/attribute.
2. Classify as expected, approved, or suspicious.
3. Identify owner, change record, and blast radius.
4. If legitimate, codify in IaC through review.
5. If unauthorized, isolate/restore via incident procedures.
6. Run `plan`/validation and audit the outcome.

Never auto-apply plans containing destructive replacements without clear policy and approval.

## 16. Rollback, recovery, and cleanup

### 16.1. Rollback decisions

Rollback triggers when health/SLO gates fail, error rates spike, data invariants break, security policies are violated, or business workflows fail. Pre-define metrics, observation windows, thresholds, and decision authorities prior to release.

### 16.2. Stateless rollback

If the application is stateless and schemas remain compatible, shift traffic back to the old pool or redeploy the previous digest. Ensure the old pool retains capacity, secrets, and network access throughout the rollback window.

### 16.3. Stateful rollback

Once writes hit new stateful resources, rollback requires reverse sync/reconciliation or forward-fix. Never overwrite new data by restoring an older snapshot without an explicit business decision accepting data loss.

### 16.4. Cleanup

Clean up only after:

- Zero traffic reaches old resources.
- Connections and in-flight work have drained.
- Background jobs and queue consumers no longer depend on old endpoints.
- Data consistency and business validations pass.
- The rollback window closes or the owner accepts moving forward.
- Backups, retention, and security evidence comply with policy.

Then delete unused old resources, IPs, volumes, temporary snapshots, security rules, and secrets. Cleanup must be idempotent and inventory-driven to avoid deleting active resources.

## 17. Capacity and cost of replacement

### 17.1. Temporary headroom

Rolling and blue-green replacements require temporary headroom for old and new resources to coexist. Plan ahead for compute, subnet IPs, quotas, connection limits, database replicas, storage, load balancer targets, and autoscaling caps.

### 17.2. Cost windows

Parallel-running costs escalate if validation or approvals stall. Set deadlines for rollouts, rollback windows, and cleanup owners. Track costs by release and resource generation.

### 17.3. Rate-limiting replacements

Replacing too many instances simultaneously can starve capacity, cause connection storms, or overload downstream dependencies. Cap batch sizes/max unavailable counts, pause between waves, and monitor saturation.

### 17.4. Quota and IP exhaustion

Parallel environments can exhaust quotas or subnet IPs before deployment even completes. Preflight checks must verify regional quotas, available subnet IPs, registry pull bandwidth, and database connection budgets.

## 18. Observability for replacement workflows

### 18.1. Correlation

Each replacement should carry a deployment ID/release ID and resource generation tag. Attach correlation IDs to logs, events, and audit records to link create, validate, traffic-shift, drain, and delete steps.

### 18.2. Essential metrics

| Metric | Meaning |
|---|---|
| Replacement duration | Time from creating new resources to completion |
| Healthy capacity | Available healthy capacity per generation |
| Traffic share by version | Share of traffic hitting old vs. new versions |
| Error rate and latency by version | SLO comparison across generations |
| Drain duration | Time to close connections and in-flight requests |
| Replication lag | Sync delay on stateful resources |
| Rollback count | Frequency of failed rollouts |
| Orphan resource count | Leftover resources missed during cleanup |
| Drift count/age | Volume and age of unresolved drift |

### 18.3. Audit and change records

Record actor/pipeline identity, commit, IaC plan hash, artifact digest, target account/region, resource IDs, approvals, cutover timestamp, rollback decisions, and cleanup completion. Never log secrets inside change records.

## 19. Example: replacing the Booking API on cloud

### 19.1. Architecture

The Booking API runs three stateless replicas behind a load balancer, backed by a managed database, Redis session/cache, a queue, and object storage. The new release updates the runtime base image and adds a backward-compatible schema field.

### 19.2. Plan

1. Update IaC and image digest via pull request.
2. Run formatting/validation, policy scans, and plan in staging.
3. Apply the backward-compatible expand database schema migration.
4. Build, scan, and sign the new image.
5. Provision a green replica and verify workload identity, secrets, networking, and readiness.
6. Run read/write smoke tests against test data.
7. Shift 5% of traffic to green; monitor error rate, p95 latency, payment events, and DB connections.
8. Ramp traffic through approved increments as canary gates pass.
9. Drain old replicas, shift 100% of traffic, and verify workers/queues.
10. Retain the old pool during the rollback window, then retire and clean up.

### 19.3. Deployment diagram

~~~mermaid
flowchart TD
    IAC[Reviewed IaC + release manifest] --> CREATE[Create green resources]
    CREATE --> VERIFY[Verify identity, config, network]
    VERIFY --> TEST[Smoke test]
    TEST --> CANARY[Route small traffic share]
    CANARY --> GATE{SLO and business gate pass?}
    GATE -->|No| BACK[Route back to blue and investigate]
    GATE -->|Yes| RAMP[Increase traffic gradually]
    RAMP --> FULL[Green receives production traffic]
    FULL --> DRAIN[Drain blue and background workers]
    DRAIN --> WINDOW[Rollback window and monitoring]
    WINDOW --> CLEAN[Approve cleanup of blue]
~~~

### 19.4. Completion criteria

- Green runs the exact approved image digest and config version.
- Health/readiness checks and smoke tests pass.
- Error rates and latency remain within SLO at every traffic step.
- Database schema remains compatible across all versions running during rollout.
- Queues, sessions, and background jobs no longer depend on the old pool.
- Zero active traffic or connections remain on blue.
- Rollback window and cleanup are confirmed by the owner.
- IaC/state accurately reflect live running resources.

## 20. Common mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Editing production servers directly | Snowflakes and accumulating drift | Build new images and replace |
| Using mutable image tags | Deployments cannot verify exact artifacts | Pin immutable digests/versions |
| Replacing a database like a stateless VM | Data loss or split-brain | Replication, quiesce, fencing, and cutover |
| Deleting old resources right after create | No rollback target | Health gates and rollback windows |
| Using only liveness as a health gate | Instance alive yet unable to serve traffic | Readiness, smoke tests, and SLO gates |
| Skipping connection draining | In-flight requests severed | Graceful shutdown and connection draining |
| Ignoring mixed-version windows | Old app breaks on new schema | Expand-and-contract |
| Blindly applying against stale IaC state | Replaces or deletes live resources by mistake | Review plans, reconcile drift, verify backend |
| Two pipelines applying the same state | State corruption or races | Locking and ownership boundaries |
| Failing to fence the old primary | Two nodes accepting writes | Single write owner and epoch/fencing |
| Treating DNS TTL as instant cutover | Clients still hit old endpoints | Overlap windows and traffic observation |
| Leaving old credentials active | Expanded attack surface | Revoke and audit after retirement |
| Ignoring parallel headroom | Quota/IP exhaustion mid-rollout | Preflight capacity checks |
| Cleaning up without an inventory | Orphaned or accidentally deleted resources | Generation tags and dry-runs |

## 21. Well-Architected assessment

| Pillar | Question | Controls and trade-offs |
|---|---|---|
| **Operational Excellence** | Are replacements automated, versioned, owned, and audited? | IaC pipelines, plan reviews, release records, and drift processes |
| **Security** | Are images, identities, secrets, networks, and deploy permissions verified? | Artifact signing, least privilege, workload identity, credential revocation |
| **Reliability** | Are health gates, rollbacks, data consistency, and single write owners enforced? | Rolling/blue-green, replication, fencing, and rehearsals |
| **Performance Efficiency** | Does replacement have headroom without causing connection surges? | Capacity planning, batch sizes, rate limits, and traffic ramps |
| **Cost Optimization** | Are old and temporary resources cleaned up promptly? | Cost tagging, rollback deadlines, and orphan reconciliation |
| **Sustainability** | Are unnecessary builds, redeploys, and idle duplicate resources avoided? | Artifact reuse, right-sized overlap windows, and lifecycle cleanup |

Immutable infrastructure increases reproducibility and reduces drift, yet it is only truly safe when replacement workflows protect state, identities, dependencies, and live traffic. Automation must include gates, audits, and automatic halts when conditions fail.

## 22. Applied exercises

### Exercise A — Manually patched VMs

Three VMs in the same autoscaling group run different package versions because operators patched them directly over time.

**Question:** How do you restore the environment to a reproducible state?

**Hint:** Inspect drift and establish the desired configuration; update the image pipeline/IaC; build a fresh image; roll out replacements in batches; verify SLOs, then retire old instances. Do not manually patch each VM to match without codifying the build process.

### Exercise B — Blue-green and databases

Green has accepted 10 minutes of live write transactions, yet the new application hits a critical bug. Blue is still running, but its database does not contain the new transactions.

**Question:** Can traffic simply be switched back to blue?

**Hint:** Not without synchronizing the new writes created on green. You need reverse replication/reconciliation or a forward-fix; clarify write ownership and freeze writes before switching. Compute-layer blue-green does not automatically provide safe data-layer rollback.

### Exercise C — Stuck node drain

A Kubernetes node cannot drain because a stateful pod relies on local storage.

**Question:** What must be checked before terminating the node?

**Hint:** Determine whether local data is disposable, inspect the workload/controller, persistent volume mode, PDBs, and state migration procedures. Back up/migrate data or safely handle the stateful workload before deleting the node.

### Exercise D — DNS cutover

DNS TTL was lowered to 30 seconds, yet some clients still hit the old endpoint 10 minutes later.

**Question:** Why, and what should you do?

**Hint:** Resolvers and clients may ignore TTL; already-open connections do not follow DNS updates. Keep the old endpoint up during an overlap window, monitor residual requests, drain connections, and clean up only once traffic meets exit criteria.

### Exercise E — IaC plan proposes replacing the database

An input change causes the plan to propose destroying and recreating the live database because the attribute cannot be updated in place.

**Question:** Should you approve the plan immediately?

**Hint:** No. Check resource lifecycle semantics, backups/PITR, data migration, replicas, downtime, retention, and cutover strategy. Separate database replacement into a planned migration with explicit destructive-action review and approval.

### Exercise F — Hotfix drift

An operator temporarily opened a firewall rule during an incident and forgot to add it to IaC.

**Question:** What should the post-incident workflow include?

**Hint:** Log a change record, evaluate whether the rule is still needed, remove it or codify it in IaC through review, run a drift check, and audit. If no longer needed, delete it through an approved change.

## 23. Checklist before replacing production resources

- [ ] Resources are classified as stateless/stateful/control-plane with clear owners.
- [ ] Desired state lives in versioned IaC with pinned, reviewed modules/providers.
- [ ] State backend is encrypted, backed up, access-controlled, and actively locking.
- [ ] Drift is classified; plans contain no unexpected destructive replacements.
- [ ] Images/artifacts use immutable digests/versions with scans and provenance evidence.
- [ ] Runtime configs, secrets, and keys are injected safely—never baked into images.
- [ ] Capacity, quotas, subnet IPs, connection limits, and dependency headroom are verified.
- [ ] Replacement strategy (rolling, blue-green, canary, or dedicated migration) fits SLOs and state.
- [ ] Readiness probes, smoke tests, SLO gates, and stabilization windows are defined.
- [ ] Graceful shutdown, connection draining, sessions, and queue handling are verified.
- [ ] Databases/stateful resources have backups, replication, validation, and write-owner/fencing plans.
- [ ] Schemas support mixed-version windows or follow expand-and-contract.
- [ ] DNS, IP allowlists, certificates, WAF, and routes have overlap/cutover plans.
- [ ] Workload identities, secret versions, and encryption keys are verified on new resources.
- [ ] Rollback conditions, owners, deadlines, and handling for newly written data are defined.
- [ ] Deployment IDs/resource generations are attached to logs, metrics, and audit trails.
- [ ] Cleanup runs only after draining, validation, rollback window expiry, and approval.
- [ ] Old credentials, network rules, and artifacts are revoked/retired per policy.
- [ ] Reconciliation checks detect orphan resources, drift, and lingering costs.
- [ ] Replacement failures, stateful cutovers, and rollbacks are rehearsed ahead of major releases.

**Key takeaway:** Immutable infrastructure applies changes by creating new resource versions, verifying them, shifting workloads over, and retiring old versions only afterward. Safe workflows classify statefulness, protect IaC state and drift, pin artifacts, enforce health/SLO gates, drain traffic, and maintain a single write owner for data. Blue-green or rolling strategies only address compute replacement; databases, identities, DNS, keys, and dependencies require dedicated plans. Clean up only after proving the new version works, data is consistent, and the rollback window is resolved.
