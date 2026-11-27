# Limits of Automation and Manual Intervention Procedures

Automation is a vital part of a High Availability (HA) PostgreSQL system. Health checks, replication monitoring, leader election, failover orchestration, and endpoint routing can shorten incident detection and cutover to a backup node. However, automation acts strictly on the signals, rules, and permissions humans designed. It cannot always know whether the primary is truly dead, which data is freshest, which action is business-safe, or whether a network partition is letting two nodes accept writes simultaneously.

Premature automatic failover can trigger split-brain. Delayed failover prolongs downtime. A system relying solely on ping may promote a standby while the primary stays alive yet unreachable from the monitor. Conversely, a system waiting on excessive confirmations may hang when multiple failure domains lose connectivity. Production HA must therefore define **clear boundaries between automated decisions and human judgment**, paired with fencing, approval authority, runbooks, evidence, and drills.

Manual intervention does not mean running every command by hand. Many steps can still be scripted and controlled. What matters is that high-consequence decisions—choosing the authoritative node, accepting potential data loss, reopening writes, resolving dual-primary conditions, or executing failback—must have explicit criteria, accountable owners, and stop conditions. Automation should execute pre-verified safe decisions; when state is uncertain, it must fail safe and page the right human.

This lesson belongs to the **High Availability** chapter of the **Database Engine Relational PostgreSQL** module. It covers technical and operational limits of HA automation, scenarios requiring a human in the loop, fenced failover/failback procedures, and how to structure runbooks for consistent manual intervention.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain what automation can do and what it cannot infer on its own in HA.
- Distinguish failure detection, failure declaration, leader election, fencing, promotion, and traffic routing.
- Recognize false positives, false negatives, network partitions, and partial failures.
- Explain split-brain, stale primaries, and the risk of divergent writes.
- Evaluate quorum, witnesses, leases, and fencing tokens at an architectural level.
- Understand why replication lag and commit acknowledgments shape failover decisions.
- Establish policies separating auto-failover from manual approval.
- Design break-glass access, incident roles, and change/audit trails.
- Write runbooks for detection, confirmation, fencing, promotion, routing, and validation.
- Handle failback, rejoining, rewinding, and rebuilding old nodes.
- Drill scenarios where automation stalls or lacks sufficient evidence.
- Measure RTO, test alert delivery paths, and drill both automated and manual procedures.

## 2. Layers of Automation in PostgreSQL HA

An HA system consists of multiple cooperating layers. Never view “failover automation” as a single command.

~~~text
                Monitoring / Health checks
                         |
                         v
                 Failure detection
                         |
                         v
              HA manager / Coordinator
                         |
             +-----------+-----------+
             |                       |
             v                       v
       Election / policy          Fencing control
             |                       |
             +-----------+-----------+
                         |
                         v
                 Promote standby
                         |
                         v
             Endpoint / proxy / DNS
                         |
                         v
                  Applications
                         |
                         v
                Validation / alerts
~~~

### 2.1. Monitoring

Collects server availability, replication state, lag, disk/CPU, query health, application errors, and network signals.

### 2.2. Failure Detection

Identifies when a node or service fails health criteria for a defined interval. This is an observation-based signal, not proof that the node died.

### 2.3. Coordination and Election

The HA manager decides which node holds authority to become the new primary based on quorum, priority, timeline/LSN, synchronous state, and policy.

### 2.4. Fencing

Stops the old node from continuing to accept writes via power control, cloud APIs, storage/network isolation, or another independent mechanism.

### 2.5. Promotion

Transitions a standby into a writable primary. Promotion creates a new state/timeline and must execute exactly once under an authoritative decision.

### 2.6. Routing and Validation

Redirects clients to the new primary, refreshes connection pools, verifies application readiness, and confirms only a single writer is active.

## 3. What Automation Does Well

Automation excels at repetitive steps with measurable signals and deterministic outcomes.

### 3.1. Detecting Health Degradation

Can continuously check PostgreSQL processes, SQL connectivity, replication receiver/sender states, disk capacity, WAL archive lag, and service-level probes.

### 3.2. Collecting Evidence

Automatically snapshots metrics, logs, LSNs, timelines, node identities, timestamps, and network state prior to decisions.

### 3.3. Executing Controlled Actions

Can run promotion, update proxy memberships, rotate endpoints, or rebuild standbys once preconditions are satisfied.

### 3.4. Running Repeatable Validation

Can run smoke queries, check writable endpoints, verify replication state, and assert defined business invariants.

### 3.5. Alerting and Incident Creation

Automatically notifies on-call engineers, attaches runbooks, populates incident context, and logs audit events.

## 4. Decisions Automation Cannot Make Alone

Tools know only the signals fed to them. They do not comprehend business meaning or out-of-scope incident context.

### 4.1. Is an Unresponsive Node Truly Dead?

A node may be alive yet isolated by a network partition, CPU starvation, TLS/auth failure, or overload. A health check from one vantage point cannot distinguish every case.

### 4.2. Which Node Holds the Best Data?

A standby with a higher LSN is not automatically valid if timeline divergence, corruption, or logical errors occurred. Lineage and failure timelines must be checked.

### 4.3. Is Data Loss Acceptable?

RPO is a business-approved decision. Automation can measure data gaps, yet cannot unilaterally authorize losing payment or order transactions.

### 4.4. Is a Transaction Valid for Business Logic?

PostgreSQL happily commits syntactically valid `UPDATE`s that are logically wrong. Failover cannot restore correct logic without backups/PITR and investigation.

### 4.5. Should Writes Open Immediately?

The cluster may accept writes while applications, queues, identity providers, payment gateways, or DNS remain unready. Service readiness requires end-to-end checks.

## 5. Failure Detection Is Not Failure Declaration

This is a critical boundary in HA.

### 5.1. Detection

A probe timeout, connection error, or missed heartbeat is a detection signal—meaning the observer did not receive a timely response.

### 5.2. Declaration

Failure declaration is the policy decision to treat a node as unavailable, potentially triggering election or failover.

### 5.3. False Positives

A healthy node is marked down due to network congestion, GC/CPU stalls, overloaded disks, firewalls, or overly tight probe timeouts.

### 5.4. False Negatives

A broken node passes health checks because checks inspect only an open TCP port or running process while queries hang.

### 5.5. Multi-Signal Detection

Combine SQL probes, process/service state, network paths, replication health, host metrics, and application error signals. Always track where each probe originates and which failure domain it covers.

## 6. Partial Failures and Network Partitions

Distributed systems frequently encounter asymmetric states where part of the system sees a node while another part does not.

~~~text
              Network partition
        +----------------+   +----------------+
        | Region A       | X | Region B       |
        | Primary P      |   | Standby S      |
        | App clients    |   | HA observer    |
        +----------------+   +----------------+
~~~

### 6.1. Primary Remains Alive

P can keep serving clients in Region A while losing connectivity to standbys or observers in Region B.

### 6.2. Standby Loses Sight of Primary

S hits timeouts and concludes P is unavailable while P still accepts writes from active clients.

### 6.3. Both Sides May Make Divergent Decisions

If both sides promote or route writes without quorum/fencing, two primaries coexist.

### 6.4. Timeouts Do Not Prove Process Death

A timeout shows an observer received no reply within its window—not that the host powered off.

### 6.5. Design Around Failure Domains

Place witnesses/quorum members and fencing controls so no single partition allows both sides to claim authority. Account for independent regions, AZs, networks, power, and control planes.

## 7. Split-Brain and Its Consequences

Split-brain occurs when multiple nodes simultaneously claim authoritative primary status and accept independent writes.

### 7.1. Divergent Data

Each primary commits distinct transactions. Physical/logical replication cannot automatically merge divergent histories.

### 7.2. Duplicate Business Operations

Applications may create duplicate orders, charges/payments, or inventory updates across divergent branches.

### 7.3. Never Just Pick the Node with More Rows

A node with more rows may hold corrupt or duplicated transactions. You need timelines, WAL positions, audits, and business reconciliation.

### 7.4. Split-Brain Can Happen Even with One Configured Primary

A proxy or application may keep routing writes to the old node; the control plane recognizes a new primary while old clients remain unfenced.

### 7.5. Fencing Is an Essential Safeguard

Before promoting a standby, enforce a mechanism blocking the old primary from writes or proving it can no longer act as a writer.

## 8. Fencing: Stopping the Old Primary from Writing

Fencing revokes a node's ability to serve writes within an authoritative system.

### 8.1. Power Fencing

Powers off or resets the host via BMC, cloud provider, or hypervisor. Requires a control plane independent of the failing node.

### 8.2. Network Fencing

Blocks application traffic to the old primary via firewalls, security groups, or network policies. Account for pre-existing connections and alternate network paths.

### 8.3. Storage Fencing

Revokes shared storage access or uses storage leases/locking. Never run ad-hoc filesystem hacks that risk corruption.

### 8.4. Process / Service Fencing

Stops PostgreSQL or its OS service on the old node. Reliable only when the control path to the host works and completion is confirmed.

### 8.5. Fencing Tokens / Epochs

The control plane issues monotonically increasing epochs/terms; storage, proxies, or applications accept writes only from leaders holding the current token. Tokens must be enforced directly on the write path.

## 9. Fencing and Leader Election Must Work Together

Leader election answers which node is authorized as primary; fencing guarantees all other nodes stop writing. They complement each other.

### 9.1. Election Does Not Stop the Old Primary Automatically

An HA manager may elect S as the new leader, yet P keeps running and accepting writes if unfenced.

### 9.2. Fence Before Promotion

Safe procedures typically require confirming the old primary is fenced prior to promoting a standby. If fencing cannot be proven, follow explicit partition policies.

### 9.3. Fencing Tokens Must Be Enforced

A token sitting purely in metadata protects nothing unless applications, proxies, or storage validate it before writing.

### 9.4. Fencing Needs Timeouts and Verification

Power-off or firewall APIs can fail or return ambiguous responses. Verify final state from an independent control plane.

### 9.5. Fail-Safe Behavior

When fencing cannot be verified, automation should halt automatic promotion or escalate to manual incident procedures per risk policy. Never treat a fencing timeout as success.

## 10. Quorum, Witnesses, and Authoritative Authority

Quorum prevents two node groups from both believing they hold leadership.

### 10.1. Quorum

Decisions require sufficient votes from eligible members. With majority quorum, at most one partition holds a majority under consistent membership.

### 10.2. Witnesses

A witness is a voting/coordination member that may not store PostgreSQL data. It resolves partition ties in certain architectures, without automatically fencing the old primary.

### 10.3. Odd-Numbered Voters

Odd voter counts prevent ties in majority voting. Count and placement must respect failure domains; three voters in one AZ cannot survive losing that AZ.

### 10.4. Quorum Does Not Prove Latest Data

Quorum governs coordination authority—not whether a candidate holds every transaction committed on the old primary. You still need durability policies and LSN/acknowledgment checks.

### 10.5. Quorum and Synchronous Replication Are Distinct Concepts

Quorum elections pick leaders; synchronous replication governs commit acknowledgments. Both can coexist in one system without substituting for each other.

## 11. Leases and Fencing Tokens

Some HA managers use leases/locks inside a distributed configuration store to track leadership.

### 11.1. Leases

A lease grants leadership for a bounded window and requires periodic renewal. If the leader fails to renew, another node can acquire leadership via the coordinator.

### 11.2. Clock Assumptions

Time-based leases rely on assumptions about clock drift, scheduling stalls, and network delays. Never assume lease expiration at an observer means the old process halted.

### 11.3. Monotonically Increasing Tokens / Epochs

On each leadership change, the coordinator increments a term/epoch. Write-path enforcement rejects requests carrying stale tokens.

### 11.4. Storage Fencing

If storage honors fencing tokens/leases, old nodes with expired tokens cannot write. With local PostgreSQL data directories, pair with service, network, or host fencing per architecture.

### 11.5. Verify Real Implementation Details

Examine how your HA manager stores locks, renews leases, handles stale leaders, and fences. Having a “leader election” feature name does not prove split-brain is prevented.

## 12. How Replication State Shapes Failover Decisions

One node may be healthy yet lagging; another may have a higher LSN yet be ineligible due to timeline divergence.

### 12.1. Asynchronous Replication

The primary returns commit responses without waiting for standbys to flush WAL. On abrupt primary loss, standbys may lack the latest commits.

### 12.2. Synchronous Replication

Commits wait for synchronous standby acknowledgment per `synchronous_commit` and `synchronous_standby_names`. Acknowledgment mode defines actual durability.

### 12.3. Remote Write, Flush, and Apply

`remote_write`, `remote_flush`, and `remote_apply` represent distinct confirmation levels. Candidate selection must evaluate actual acknowledgment levels rather than trusting a generic “synchronous” label.

### 12.4. Candidate Selection

Evaluate timelines, receive/write/flush/replay LSNs, synchronous state, WAL/archive availability, and node health. A higher LSN alone does not guarantee all transactions are valid.

### 12.5. RPO Must Be Explicitly Accepted

If async failover risks losing transactions, the incident commander and business owner need estimated loss and formal approval. Never bury data-loss trade-offs inside silent automation.

## 13. Auto-Failover vs. Manual Failover

No single policy fits every workload. Clearly define what triggers automation versus human approval.

| Scenario | Typical Action Considered |
|---|---|
| Primary process dead, quorum intact, fencing confirmed | Auto-failover may be suitable |
| One standby lost while primary serves writes | Alert and repair; no promotion needed |
| Network partition, unclear if primary still writes | Fence/quorum first; may require manual decision |
| Replication lag breaches RPO | Escalate; assess candidates and data loss |
| Multiple candidates with differing timelines/LSNs | Manual review per policy |
| Logical corruption or accidental deletion | PITR / isolated recovery, not mere failover |
| Ransomware / compromised credentials | Incident response and clean recovery; never blindly promote |
| Region outage, verified DR site | Follow DR runbook; human declaration per policy |

### 13.1. Preconditions for Auto-Failover

Requires quorum/leader authority, verified fencing paths, eligible candidates, defined RPO policies, and testable routing automation.

### 13.2. Triggers for Manual Approval

Use when facing split-brain uncertainty, data divergence, corruption, ambiguous candidates, external dependency issues, or business data loss.

### 13.3. Never Automate Undefined Decisions

If no rule resolves differing candidate LSNs/timelines, automation cannot invent a business-safe choice.

### 13.4. Manual Does Not Mean Slow and Ad-Hoc

Runbooks, pre-approved thresholds, on-call rosters, and break-glass access enable fast, consistent human decisions.

### 13.5. Post-Incident Policy Review

When a failure pattern repeats with clear signals, steps can graduate from manual to automated once backed by tests, fencing, and rollback plans.

## 14. What to Automate vs. What Needs Approval

| Task | Automation | Human Role |
|---|---|---|
| Collecting metrics/logs | Automated | Verify context |
| Alerting / on-call routing | Automated | Acknowledge and assign |
| Checking replication lag | Automated | Set risk thresholds |
| Checking quorum/locks | Automated | Review anomalous states |
| Pre-designed fencing | Can be automated | Approve per policy; verify |
| Candidate selection | Automated under clear rules | Decide under ambiguity |
| Promotion | Automated once preconditions pass | Manual override/approval |
| Endpoint routing | Automated | Validate clients |
| Business data reconciliation | Assisted by scripts | Owner makes final call |
| Failback / rejoin | Partially automated | Review timeline/data divergence |

### 14.1. Automate Evidence, Not Assumptions

Automatically gather LSNs, timelines, sender states, fencing status, and node identities. Never replace evidence with an opaque `healthy=true` flag.

### 14.2. Approval Gates

Place approval gates before irreversible or lossy steps: promoting ambiguous candidates, accepting RPO breaches, forcing failover without quorum, or reopening writes.

### 14.3. Idempotent Actions

Automation steps must be safely re-runnable or check state before acting. Avoid duplicate promote/route runs causing undefined states.

### 14.4. Dry Runs and Preflights

Before altering topology, display candidate, LSN/timeline, quorum, fencing result, target endpoint, and expected RPO/RTO.

### 14.5. Stop Conditions

If any precondition fails, automation must halt, preserve a safe state, and page operators. Never skip checks just to “push through.”

## 15. HA Tools and Responsibility Boundaries

PostgreSQL typically pairs the database engine with external HA managers, proxies, and service discovery.

### 15.1. Patroni

Patroni manages PostgreSQL HA, leader election via a DCS, and promote/demote transitions per config. Understand its DCS quorum, watchdog/fencing behavior, synchronous mode, and routing integration.

### 15.2. repmgr

repmgr provides replication management/monitoring and assisted switchover/failover. Configure failover policies, witnesses/monitoring, and fencing suitable for your environment.

### 15.3. `pg_auto_failover`

`pg_auto_failover` uses a monitor to orchestrate node states and failovers via a state machine. Understand monitor availability, node roles, and failure transitions.

### 15.4. Managed PostgreSQL Services

Cloud providers manage failovers, endpoints, and replicas. Users still must understand failover semantics, RPO, maintenance behavior, zone/region scope, and tier limits.

### 15.5. No Tool Understands Business Invariants Automatically

Regardless of tooling, applications still require consistency policies, backups/PITR, data validation, fencing assurances, and anomaly runbooks.

## 16. Health Checks: Checking the Right Layer

Every health check should answer a specific question.

### 16.1. Process Health

Is the PostgreSQL process running? A running process does not mean the query path works.

### 16.2. SQL Readiness

Can clients connect and run a lightweight query? Queries can fail due to connection exhaustion, locks, or disk I/O stalls.

### 16.3. Write Readiness

Can the primary commit a policy-approved probe transaction? Never run ad-hoc write probes on business tables.

### 16.4. Replication Health

Does the standby have an active receiver, upstream sender connection, and advancing replay? Check LSNs, lag, and timelines.

### 16.5. Application Health

Does an end-to-end request succeed? Apps can fail on DNS, credentials, pools, queues, or external dependencies even when the database is healthy.

## 17. Health Check Design and Thresholds

Set thresholds around workloads, failure models, and RTO—never one blanket timeout for every layer.

### 17.1. Timeouts Too Short

Short timeouts detect quickly but trigger false positives during network jitter or load spikes—risking dangerous failovers.

### 17.2. Timeouts Too Long

Long timeouts reduce false positives while stretching detection time and RTO. Balance against failure detection needs.

### 17.3. Consecutive Failures

Require N consecutive failed probes before declaring unhealthiness to absorb transient blips, factoring total detection delay into RTO.

### 17.4. Multi-Observer Probing

Probing from multiple network locations separates dead nodes from broken network paths—provided observers sit in independent failure domains.

### 17.5. Thresholds by Service Tier

Payment databases require faster detection than analytics. Define separate health SLOs, alert thresholds, and failover policies per tier.

## 18. Manual Intervention: Roles and Responsibilities

Define decision roles clearly before incidents strike.

### 18.1. Incident Commander

Coordinates the incident, maintains timelines, assigns tasks, and manages escalation per incident policy.

### 18.2. DBA / Recovery Lead

Assesses PostgreSQL state, replication, LSNs/timelines, candidate eligibility, backups/PITR, and technical validation.

### 18.3. Infrastructure / Network Owner

Verifies hosts, power, network partitions, storage, and fencing controls using independent control-plane access.

### 18.4. Application Owner

Verifies application connectivity, retry behavior, queue consumers, background jobs, and smoke tests.

### 18.5. Business / Service Owner

Accepts RPO/data-loss trade-offs, validates business invariants, and prioritizes service options.

## 19. Break-Glass Privileges and Emergency Access

Manual failover may require higher privileges than day-to-day operations. Prepare and test emergency access beforehand.

### 19.1. Separate Identities

Maintain dedicated emergency identities for databases, cloud control planes, networks/firewalls, and secrets. Never depend on a potentially compromised application account.

### 19.2. MFA and Approvals

Protect break-glass credentials with MFA, vaults, approvals, or dual control per policy. Document who may invoke them and when.

### 19.3. Independent Access Paths

If the production identity provider or network fails, maintain a tested emergency access path with strict auditing and scope limits.

### 19.4. Credential Availability

Ensure secrets, certificates, KMS keys, and recovery tokens are accessible in DR regions/accounts. Paper-only permissions are useless during disasters.

### 19.5. Post-Break-Glass Cleanup

Revoke/rotate emergency credentials, review audit logs, verify all changes, and close temporary access immediately afterward.

## 20. Manual Failover Runbook: Confirmation Phase

Before promoting a candidate, operators must understand primary and standby states.

### 20.1. Declare Incident

Record T0, timezone, failure scope, service tier, and commander. Confirm whether this is a true failover event or degradation.

### 20.2. Verify Whether Primary Still Accepts Writes

Check SQL, processes, host, network, proxies, and application paths. Never declare a node dead from a single observer timeout.

### 20.3. Verify Candidate List

Collect replication state from the primary if reachable, receiver state on standbys, replay/flush LSNs, timelines, and synchronous status using `pg_stat_replication` and `pg_stat_wal_receiver`.

### 20.4. Assess Data Loss

Estimate potential lost transaction boundaries from acknowledgment modes and candidate states. Escalate to the business owner if exceeding RPO.

### 20.5. Select Candidate Per Policy

Pick a node with valid lineage/timeline, suitable WAL state, and adequate capacity. Never choose solely by hostname priority or an unverified LSN.

## 21. Manual Failover Runbook: Fencing and Promotion

### 21.1. Freeze Writes

Where possible, stop or pause application writers, queue consumers, scheduled jobs, and admin tasks. Preserve request/event state for reconciliation.

### 21.2. Fence Old Primary

Execute power, network, service, or storage fencing per design. Confirm from an independent control plane that the old node cannot accept writes.

### 21.3. Record Fencing Evidence

Save API responses, instance states, firewall rules, service states, or fencing tokens/epochs. If ambiguous, do not mark fencing complete.

### 21.4. Promote Candidate

Once preconditions pass, promote via the HA manager or approved command. Never trigger multiple promotion mechanisms concurrently.

### 21.5. Verify New Primary

Confirm `pg_is_in_recovery()` returns `false`, SQL writes work per policy, timeline incremented, and logs show zero recovery errors. Hold broad traffic until validation passes.

## 22. Manual Failover Runbook: Routing and Validation

### 22.1. Update Endpoints

Switch proxies, service discovery, or DNS per prepared mechanism. Account for DNS TTLs and connection pools holding stale targets.

### 22.2. Refresh Clients

Recycle connection pools or restart application instances per plan. Confirm stale clients no longer connect to the old primary.

### 22.3. Smoke Tests

Run safe business read/write checks, verifying authentication/permissions, commits, and external dependencies during controlled rollout.

### 22.4. Reopen Traffic Gradually

Start with a small canary slice if supported. Monitor error rates, latency, lock waits, replication lag, and business metrics.

### 22.5. Record Actual RPO

Document promoted candidate, recovery LSN/timeline, last confirmed transaction boundary, and required data reconciliation against approved RPO.

## 23. Manual Switchover vs. Manual Failover

Switchover is a planned transition while the system remains healthy; failover responds to an unexpected failure.

### 23.1. Switchover Can Synchronize Cleanly

You can drain writes, wait for standby catch-up, verify LSNs, and swap roles within a maintenance window.

### 23.2. Failover Risks Losing Tail Data

The primary may die before shipping/flushing final WAL, leaving candidates short of recent async commits.

### 23.3. Switchover Still Needs Fencing Logic

Even with a healthy old primary, guarantee it stops accepting writes once roles flip. Never rely on DNS updates alone.

### 23.4. Switchover Needs Abort Criteria

If standby lag exceeds thresholds, replication drops, or prechecks fail, abort and restore the initial state before promotion.

### 23.5. Drill Both Separately

A smooth switchover does not prove failover works when the primary vanishes suddenly. Test both scenarios.

## 24. When Automation Stalls or Reports Conflicting State

HA managers can hit unavailable DCSs, down monitors, stale locks, API timeouts, or incomplete transitions.

### 24.1. Do Not Immediately Run Manual Promote

First determine whether the HA manager is already promoting or elected another node. Two actors promoting concurrently create divergence.

### 24.2. Inspect the State Machine

Read cluster state, leader locks/leases, and node states via your tool's commands. Record timestamps and owner/epoch.

### 24.3. Check Processes and PostgreSQL Roles

On every node, verify primary/standby role, recovery status, active sessions, and timelines. Cross-check against HA manager state.

### 24.4. Check DCS / Quorum

If the DCS lost quorum, avoid mutating leader ownership until control-plane state is understood.

### 24.5. Escalate Per Runbook

When states conflict, escalate to the incident commander and DBA lead. Keep writes closed or nodes fenced per policy until authority is clear.

## 25. Manual Recovery When Old Primary State Is Unknown

Some disasters sever connectivity to the primary without confirming it stopped.

### 25.1. Never Equate “Unreachable” with “Fenced”

The primary may be alive on the far side of a network partition. Promoting a standby without fencing invites split-brain.

### 25.2. Use Independent Control Planes

Inspect cloud/hypervisor power states, network ACLs, storage attachments/leases, or out-of-band management.

### 25.3. When No Fencing Path Exists

Follow pre-approved policies for unprovable primary stoppage—waiting, restoring connectivity, or accepting controlled risk under formal DR declaration.

### 25.4. Document Uncertainty

Explicitly separate verified facts from assumptions and remaining risks. Never log “fenced” based solely on a ping timeout.

### 25.5. When the Old Primary Returns

Keep it isolated and non-writable. Check timeline divergence and select `pg_rewind` or a fresh base backup rebuild.

## 26. Failback: Returning to the Desired Topology

Failback moves workloads back to the original node/site or target topology after resolving a disaster.

### 26.1. Failback Is Not Flipping DNS Back

The old node may have diverged and lacks newer writes. It must rejoin as a standby before considering a switchover.

### 26.2. Maintain One Authoritative Primary

Allow strictly one node to accept writes during rebuild/rejoin. Keep all others fenced.

### 26.3. `pg_rewind` When Eligible

Use `pg_rewind` to align a diverged node onto the new timeline if prerequisites and required WAL hold. Otherwise reseed via base backup.

### 26.4. Verify Catch-Up

Check standby receiver/sender states, replay lag, timeline, and archiving. Schedule a switchover only once caught up and validated.

### 26.5. Failback May Be Unnecessary

If the DR site has adequate capacity and meets SLOs, running on the new site until a clean maintenance window may be safer. Business owners decide based on risk and cost.

## 27. Rejoining Standbys and Rebuilding Old Nodes

After failover, the old primary cannot simply restart and rejoin.

### 27.1. Keep the Old Node Isolated

Block application writes and stray replication connections outside the rejoin workflow. Preserve logs/data needed for investigation.

### 27.2. Check Timeline Divergence

Verify whether the old node sits on an older timeline with unique transactions. Never let it act as a writer just because PostgreSQL starts.

### 27.3. `pg_rewind`

When prerequisites—such as data checksums or `wal_log_hints` and required WAL—hold, `pg_rewind` aligns the old data directory onto the new primary's timeline. Verify versions/compatibility and back up beforehand.

### 27.4. Reseed from Base Backup

If rewind is impossible or data is untrusted, rebuild a fresh standby from the current primary's base backup. This is the cleanest choice for large divergence or missing WAL.

### 27.5. Verify Rejoin

Check sender/receiver states, timelines, replay LSNs, slots, archiving, and monitoring. Resume normal topology only once caught up with zero stale endpoints.

## 28. An HA Manager Does Not Replace Runbooks

Tools automate state transitions, yet runbooks are still needed when tools or dependencies fail.

### 28.1. DCS / Monitor Outages

If the DCS or monitor loses quorum, the HA manager cannot make new decisions. Operators must know who holds locks/leases and current node states.

### 28.2. Watchdog / Fencing Failures

If a watchdog fails or a host fails to fence, automation breaks safety assumptions. Runbooks must halt promotion and page infrastructure owners.

### 28.3. Proxy / Service Discovery Failures

The database may promote while clients hit the old endpoint. Runbooks must inspect proxy health, DNS caches, poolers, and stale connections.

### 28.4. API / Control-Plane Failures

Cloud APIs can time out or rate-limit. Never blindly repeat non-idempotent destructive calls; check actual state before retrying.

### 28.5. Version / Configuration Drift

Maintain version/config inventories across the HA manager, PostgreSQL, DCS, proxies, and agents. Unsynchronized edits cause unexpected state transitions.

## 29. Idempotency and Safe Automation Retries

Incidents increase the likelihood of operators or controllers retrying the same step.

### 29.1. Check Current State First

Before promoting, check whether the node is in recovery or already primary, plus timeline and leader ownership. Before routing, inspect current endpoints.

### 29.2. Idempotent APIs / Actions

Automation should return consistent results if retried after a timeout, or issue operation IDs to query prior execution status.

### 29.3. Never Assume Timeout Means Action Failed

An API may have executed fencing or promotion while losing the response. Inspect live state before retrying.

### 29.4. Locks / Serialization

Allow at most one controller or incident action to mutate leadership state at once, enforced via fencing-aware locks/leases and auditing.

### 29.5. Action Logs

Log actor, operation ID, preconditions, command, result, timestamp, and before/after state to support recovery if a workflow aborts mid-way.

## 30. Human-in-the-Loop Must Not Become a Single Point of Failure

Human approvals are essential without depending on one indispensable individual.

### 30.1. Primary and Backup On-Call

Maintain primary and secondary on-call rotations with regularly tested contact paths.

### 30.2. Escalation Timeouts

If the primary responder does not acknowledge within SLA, escalate automatically per policy. Never wait indefinitely.

### 30.3. Delegated Authority

Define explicitly who can approve promotions, accept RPO breaches, and declare DR—including after-hours authority.

### 30.4. Two-Person Control for High-Risk Actions

For forced failovers or lossy actions, consider requiring two independent confirmations, without applying bureaucracy to trivial tasks.

### 30.5. Training and Rotation

Cross-train team members on runbooks to eliminate key-person dependencies. On-call staff must hold matching permissions and skills.

## 31. Incident Communication

Technical recovery can still fail if teams lack shared visibility into state and decisions.

### 31.1. Shared Incident Timeline

Log detection, declaration, fencing, promotion, routing, validation, and restoration times in a single timezone.

### 31.2. Single Coordinator

The incident commander coordinates communications and escalations so DBAs can focus on executing technical recovery.

### 31.3. Structured Status Updates

Report impact, current state, confirmed actions, RPO/data-loss risks, next steps, and next update time.

### 31.4. Separate Facts from Hypotheses

For example, “P is unresponsive from Region B” is a fact; “P is dead” remains a hypothesis until fencing confirms it.

### 31.5. Record Decisions and Approvers

Especially for RPO breaches, forced promotions, data reconciliation, and cutovers, ensuring full post-incident traceability.

## 32. Audit Trails and Operational Evidence

Every failover and manual intervention needs auditable evidence for review and improvement.

### 32.1. State Snapshots

Capture node roles, timelines, LSNs, replication states, quorum, slot states, and endpoints before and after actions.

### 32.2. Command / Audit Logs

Log commands, actors, hosts, timestamps, exit codes, and key outputs while redacting passwords and tokens.

### 32.3. Control-Plane Events

Capture cloud power actions, network policy edits, storage detach/attach events, DCS lease transitions, and proxy pool changes.

### 32.4. Data-Loss Records

Document last recovery point, transaction boundaries, lost/reconciled data, and business sign-off.

### 32.5. Retention

Retain logs per incident/security policies with synced clocks and storage protected against deletion via production credentials.

## 33. Runbooks Must Include Preconditions and Stop Conditions

A runbook listing bare commands is unsafe for operations.

### 33.1. Preconditions

Specify requirements before each step: access rights, node identities, target details, backup/LSN positions, quorum, fencing paths, and approvals.

### 33.2. Expected Results

Document expected output/state for each action—e.g., after promotion, the node exits recovery and starts a new timeline.

### 33.3. Stop Conditions

Halt if fencing is unconfirmed, candidate timelines are unclear, WAL gaps appear, DCS states conflict, or app/data validation fails.

### 33.4. Recovery from Partial Execution

If a runbook halts after fencing yet before promotion, specify which node stays fenced, who decides next steps, and how dual writers stay blocked.

### 33.5. Escalation

Include contacts, approval authorities, vendor support paths, and fallback actions if the control plane is unreachable.

## 34. Change Management and HA Maintenance

Changing HA settings alters failover behavior even while the database looks healthy.

### 34.1. Topology Changes

Adding/removing standbys, changing sync policies, modifying DCS membership, or altering proxy routing require change plans and rollbacks.

### 34.2. Single-Node Maintenance

Drain read traffic, verify remaining standbys hold adequate capacity/quorum, then restart/patch. Never maintain multiple quorum-critical members simultaneously.

### 34.3. PostgreSQL / HA Manager Upgrades

Check compatibility matrices, replication behavior, catalog/slot support, and failover mechanics. Drill in staging first.

### 34.4. Rotating Certificates / Secrets

Confirm all nodes, agents, and proxies load new credentials and reconnect before revoking old credentials.

### 34.5. Configuration Drift

Use configuration management/IaC, version control, and drift detection. Never hand-edit one node without updating automation and inventory.

## 35. Observability: Decision-Oriented Dashboards

Dashboards must answer the exact questions operators face during incidents.

### 35.1. Cluster Role Map

Display primary, standbys, relays, witnesses/monitors, and which endpoints applications actively use.

### 35.2. Replication Freshness

Show receive/flush/replay LSNs, byte/time lag, synchronous status, and WAL archive lag.

### 35.3. Fencing / Authority

Show leader lock/lease owner, epoch/token, quorum state, and fencing confirmation where supported.

### 35.4. Client Routing

Show proxy pool members, active connections, DNS/service discovery targets, and client error rates.

### 35.5. Business Health

Monitor transaction success, queue backlogs, payment/order invariants, and user latency—database process health alone is insufficient.

## 36. Alerting and Escalation

Alerts must tell responders what action is required and who holds authority.

### 36.1. Severity by Impact

Primary down, quorum lost, fencing failure, RPO breach, and split-brain risk carry higher severity than minor read-replica lag.

### 36.2. Alert Fatigue

Correlate related alerts, tune durations/thresholds, and separate transient network jitter from sustained outages.

### 36.3. Contextual Alerts

Include node, region, current leader, candidate, replication lag, LSN/timeline, fencing state, and runbook links.

### 36.4. Escalation Routing

Page DBA on-call, infrastructure/network owners, and incident commanders by failure mode; engage business owners on data-loss/RPO decisions.

### 36.5. Test Alert Paths

Drill alert delivery, paging, acknowledgments, and escalation. An alert that never reaches an authorized responder is an HA failure.

## 37. Security Incidents Differ from Node Failures

If the primary fails due to ransomware or compromised credentials, failing over to a standby can replicate corrupted data or preserve attacker access.

### 37.1. Never Blindly Promote

Assess compromise scope, identities, and backup integrity. A live standby may have replicated malicious changes.

### 37.2. Isolate Identities / Networks

Revoke/rotate exposed credentials, block attacker paths, and operate using clean, independent DR identities.

### 37.3. Choose a Clean Recovery Point

Use immutable/offsite backups and PITR targets prior to compromise if identifiable. Restore into a clean environment to inspect.

### 37.4. Validate Integrity

Audit databases, application binaries, extensions, jobs, roles, and secrets before reopening traffic.

### 37.5. Coordinate Incident Response

Align security, DBAs, infrastructure, applications, and business owners. Preserve forensic/legal evidence per policy.

## 38. Backup and HA Are Complementary Layers

Automated failover cuts downtime for node failures; backups/PITR recover from errors that replication propagates.

### 38.1. Standbys Are Not Backups

Standbys replay logical and physical changes from the primary. Accidental `DELETE`s, logical corruption, and ransomware spread to standbys.

### 38.2. PITR Handles History

Base backups + WAL archives reconstruct the cluster at a pre-error recovery point when the chain is intact.

### 38.3. Immutable / Offsite Backups

Isolate backups from the primary/replicas' blast radius using separate identities, keys, and immutable retention.

### 38.4. Restore Drills

Test recovery independently of the live HA manager/primary. Time retrieval, restore, replay, validation, and cutover.

### 38.5. Restoring HA Protection Post-Failover

After promotion, re-establish backup chains, standbys, and WAL archiving on the new timeline. A successful failover that leaves protection un-restored leaves the system exposed.

## 39. Measuring RTO for Automated and Manual Procedures

End-to-end RTO spans multiple phases, not merely promotion duration.

~~~text
T_RTO =
  T_detect
+ T_decide
+ T_fence
+ T_promote
+ T_route
+ T_validate
~~~

### 39.1. `T_detect`

Elapsed time from fault onset until monitoring/alerting detects it.

### 39.2. `T_decide`

Time to confirm failure and pick a candidate. Manual approval adds decision time while reducing ambiguity risk.

### 39.3. `T_fence`

Time to isolate the old primary and verify fencing. Never skip this merely to shrink RTO.

### 39.4. `T_promote` and `T_route`

Duration of promotion, proxy/DNS/service discovery updates, and client pool refreshes.

### 39.5. `T_validate`

Duration of smoke tests/business checks until service-ready. Explicitly define whether RTO ends at application readiness or full traffic restoration.

## 40. Evaluating Automation Against Failure Scenarios

Never test only the happy path. Define expected behavior, stop conditions, and evidence for every scenario.

| Scenario | Behavior to Verify |
|---|---|
| Primary process crash | Detect, fence, promote per policy |
| Network partition | Zero dual writers |
| DCS / witness outage | No unsafe leadership transition |
| High standby lag | Candidate selection honors RPO |
| Fencing API timeout | Never assume fencing succeeded |
| Proxy stale connections | Old primary receives zero writes |
| Two candidates disagree | Escalate to manual decision |
| Backup / WAL unavailable | Never declare DR ready |
| Credential compromise | Isolate identities, clean recovery |
| Old primary failback | Rewind/reseed; never auto-resume as writer |

### 40.1. Bounded Chaos Testing

Fault injection requires clear scope, blast radius, abort paths, and proper environments. Never sever production networks or fence hosts without approved change plans.

### 40.2. Test Partial Failures

Break one network path while keeping the node running—this reliably exposes split-brain flaws.

### 40.3. Test Control-Plane Failures

Simulate losing DCS, monitors, APIs, or credentials to verify how automation fails safe.

### 40.4. Test Manual Overrides

Confirm on-call staff can halt automation, inspect live state, and execute runbooks via break-glass access.

### 40.5. Test Restore Paths

After failover, run independent backup/PITR tests so HA never masks backup gaps.

## 41. Lab: Distinguishing Process Failure from Network Partition

Use two PostgreSQL nodes and an observer in a test network.

### 41.1. Record Baseline

Capture P/S roles, SQL readiness, sender/receiver states, replay LSN, current endpoints, and reachability from each observer.

### 41.2. Simulate PostgreSQL Process Failure

Stop PostgreSQL on P cleanly. Watch process health, SQL probes, alerts, and HA manager state.

### 41.3. Simulate Network Partition

Block a network path between observer/standby and P while keeping P alive. Check whether another observer still reaches P and whether P still accepts writes from the app subnet.

### 41.4. Observe Decisions

Check whether the HA manager holds quorum and valid fencing paths. Use lab-only fencing integration; never touch production nodes.

### 41.5. Compare Outcomes

Record detection time, false-positive behavior, decision state, and actions. Identify which signals distinguish process crashes from partitions.

## 42. Lab: Fencing Before Promotion

### 42.1. Two-Node Setup

Deploy primary and standby alongside a lab control plane able to stop the primary VM or block its network.

### 42.2. Check Preconditions

Record candidate replay LSN, timeline, synchronous state, and current leader ownership.

### 42.3. Simulate Fencing Command

Run lab-only fencing. Save control-plane responses and confirm the old primary rejects application writes.

### 42.4. Test Fencing Failure

Force the fencing API to time out or return an unconfirmed status. Verify automation halts promotion and alerts operators.

### 42.5. Promote After Verification

In the lab only, promote the standby once fencing is confirmed. Verify `pg_is_in_recovery()` and endpoint routing.

## 43. Lab: Manual Failover When HA Manager Is Unavailable

### 43.1. Simulate Control-Plane Outage

In the lab, make the monitor/DCS unreachable while keeping nodes inspectable. Never experiment on production.

### 43.2. Gather State

Check PostgreSQL roles, timelines, LSNs, active sessions, replication links, and network reachability from multiple vantage points.

### 43.3. Determine Authoritative Ownership

Read leader lock/lease/epoch from the control plane if still accessible. If state is unclear, document uncertainty and halt promotion.

### 43.4. Fence via Independent Path

Execute power/network fencing through the independent lab control plane. Confirm the old primary cannot write.

### 43.5. Manual Promote and Route

Follow the runbook to promote the candidate, update endpoints, refresh clients, run smoke tests, and record timeline/RPO/RTO.

## 44. Lab: Handling Failback and Rejoin

### 44.1. Record Timeline

After lab promotion, note the new timeline and LSN of the current primary.

### 44.2. Boot Old Primary Isolated

Keep application traffic blocked. Confirm the old node is not treated as authoritative primary.

### 44.3. Attempt `pg_rewind`

If prerequisites hold in the lab, use `pg_rewind` to align the old node onto the new timeline; otherwise take a fresh base backup.

### 44.4. Rejoin as Standby

Configure upstream connection, replication slot/credentials, and start the node. Monitor receiver/replay progress.

### 44.5. Verify Topology

Check sender/receiver views, timelines, lag, and endpoint routing. Conclude the lab only once the old primary can no longer accept independent writes.

## 45. Failover Decision Record Template

Every significant failover decision should leave a concise, auditable record.

| Field | Details to Record |
|---|---|
| Incident ID | Incident or change ticket ID |
| T0 / timezone | Start timestamp |
| Failure mode | Process, host, network, region, security |
| Primary state | Alive / down / unknown and supporting evidence |
| Quorum / leader | Voter / lease / epoch state |
| Candidate | Node, timeline, replay/flush LSN |
| Fencing | Mechanism, outcome, evidence |
| RPO impact | Potential data loss |
| Approval | Decision-maker and timestamp |
| Action | Promote / route / recovery choice |
| Validation | Checks executed and results |
| Follow-up | Rejoin, backups, reconciliation |

### 45.1. Record “Unknown” When Unproven

Never write “down” based only on missed pings. Log unknown/partial and the verification action taken.

### 45.2. Link Evidence References

Attach logs, dashboards, cloud events, or command outputs in your incident tracker—not conclusions alone.

### 45.3. Capture Before and After States

Snapshot state prior to promotion and after routing so transitions remain fully traceable.

### 45.4. Log RPO Breaches Explicitly

When RPO is exceeded, document estimated transaction boundaries, data reconciliation, and business acceptance.

### 45.5. Post-Incident Review

Use records to refine thresholds, automation preconditions, runbooks, and team training.

## 46. Common Operational Mistakes

1. Promoting a standby solely because the primary is unpingable from one subnet.
2. Failing to fence the old primary before opening writes on the new node.
3. Believing leader election automatically shuts down the old node.
4. Checking only process health without verifying SQL or application readiness.
5. Picking candidates by priority without checking timelines, LSNs, or RPO.
6. Treating quorum as proof a candidate holds the latest data.
7. Using a synchronous label without understanding `remote_write`/flush/apply semantics.
8. Running manual `promote` while the HA manager is mid-transition.
9. Retrying fencing APIs after timeouts without checking if the first call succeeded.
10. Updating DNS while leaving old connection pools writing to the old node.
11. Forgetting to pause background jobs and queue consumers during cutover.
12. Accepting data loss without business approval.
13. Using break-glass credentials without auditing or post-incident rotation.
14. Lacking backup on-call coverage or escalation paths.
15. Omitting explicit preconditions and stop conditions in runbooks.
16. Drilling only planned switchovers without testing crashes or partitions.
17. Never testing DCS, monitor, proxy, or control-plane outages.
18. Failing back an old primary simply by starting PostgreSQL and flipping endpoints.
19. Failing to rewind or reseed an old node after timeline divergence.
20. Neglecting to restore backups, WAL archiving, and standby redundancy post-failover.
21. Confusing node failures with logical corruption or ransomware.
22. Never testing manual overrides when automation stalls.
23. Routing alerts to people lacking authority to fence or promote.
24. Applying one blanket health-check threshold to every service tier.
25. Neglecting to record timelines, LSNs, fencing evidence, and actual RPO.

## 47. Practice Exercises

### Exercise 1 — Failure Detection

What does a health-check timeout prove?

**Answer:** The observer did not receive a timely response; it does not prove the host or process died.

### Exercise 2 — False Positives

Name two reasons a healthy node gets marked down.

**Hint:** Network congestion, CPU starvation, overloaded disks, firewalls, or overly short timeouts.

### Exercise 3 — False Negatives

Why is a running process insufficient proof of service health?

**Answer:** The SQL/query path may be wedged by locks, disk stalls, connection exhaustion, or downstream failures.

### Exercise 4 — Split-Brain

What is split-brain?

**Answer:** Multiple nodes simultaneously acting as authoritative primary and accepting independent writes.

### Exercise 5 — Fencing

What is the goal of fencing?

**Answer:** Stopping the old primary from continuing to accept writes before opening writes on a new primary.

### Exercise 6 — DNS

Is changing DNS sufficient fencing?

**Answer:** No; existing clients may retain connections or stale endpoint caches.

### Exercise 7 — Quorum

What does quorum solve?

**Hint:** Ensures at most one partition holds majority under consistent membership to retain coordination authority.

### Exercise 8 — Witnesses

Does a witness automatically shut down the old primary?

**Answer:** No; it assists quorum/decisions, while a separate fencing mechanism is still required.

### Exercise 9 — Synchronous Replication

Does synchronous replication guarantee a candidate holds every transaction on failover?

**Answer:** Depends on acknowledgment mode, selected standby, and failure model; verify specifically.

### Exercise 10 — Candidate Selection

Besides node priority, what must be checked?

**Hint:** Timeline, receive/flush/replay LSN, synchronous state, WAL availability, and node health.

### Exercise 11 — Auto-Failover

List key preconditions.

**Hint:** Quorum/leader authority, verified fencing, eligible candidate, RPO policy, and routing path.

### Exercise 12 — Manual Approval

When should decisions escalate to manual approval?

**Hint:** Network partitions, fencing uncertainty, candidates with differing timelines/LSNs, corruption, or RPO breaches.

### Exercise 13 — Idempotency

Why avoid immediately re-running `promote` after an API timeout?

**Answer:** The command may have succeeded while its response dropped; inspect state first.

### Exercise 14 — HA Managers

Do Patroni, repmgr, or `pg_auto_failover` replace business validation?

**Answer:** No.

### Exercise 15 — Health Layers

Name four health layers to monitor.

**Hint:** Process, SQL readiness, replication, and application/service health.

### Exercise 16 — Break-Glass

Why is an independent access path needed?

**Answer:** The production identity provider or network may be the very component failing.

### Exercise 17 — Incident Commander

What is the primary role of the incident commander?

**Answer:** Coordination, timeline tracking, task assignment, and escalation—not necessarily running every DBA command personally.

### Exercise 18 — Business Owner

Who should accept data loss exceeding RPO?

**Answer:** The authorized business or service owner per policy.

### Exercise 19 — Freezing Writes

Why pause queue consumers and scheduled jobs during cutover?

**Hint:** They may keep writing to the old primary or trigger duplicate side effects.

### Exercise 20 — Manual Failover

List the main sequence of manual failover.

**Hint:** Declare, verify state, pick candidate, freeze writes, fence old primary, promote, route, validate.

### Exercise 21 — Switchover

How does switchover differ from failover?

**Answer:** Switchover is planned while the primary runs; failover responds to unexpected failures.

### Exercise 22 — Fencing Failure

If a fencing command times out, can it be treated as successful?

**Answer:** No; verify via an independent control plane.

### Exercise 23 — Rejoining

Can an old primary simply restart after promotion and accept writes?

**Answer:** No; keep it isolated and rejoin as a standby via rewind or reseed.

### Exercise 24 — `pg_rewind`

When can it be used?

**Hint:** When prerequisites like checksums/`wal_log_hints`, required WAL, and matching versions hold.

### Exercise 25 — Reseeding

When is rebuilding from a base backup appropriate?

**Answer:** When rewind is unavailable, required WAL is missing, or the old node is untrusted.

### Exercise 26 — RTO

Does RTO consist solely of promotion time?

**Answer:** No; it includes detection, decision, fencing, promotion, routing, and validation.

### Exercise 27 — Partial Failures

Why probe from multiple network locations?

**Hint:** To distinguish a dead node from a partitioned network path.

### Exercise 28 — DCS Outages

When the DCS loses quorum, why avoid immediate manual promotion?

**Answer:** The HA manager may still hold uncertain lock/state; verify authority first to prevent dual actors promoting.

### Exercise 29 — Backups

Why don't standbys replace backups/PITR?

**Answer:** Logical corruption and malicious modifications replicate to standbys.

### Exercise 30 — Security Incidents

Why does ransomware require a different procedure from a node crash?

**Hint:** Compromise scope must be assessed, identities isolated, and a clean recovery point chosen.

### Exercise 31 — Approval Gates

Name two actions that should require an approval gate.

**Hint:** Forced promotion without quorum, accepting an RPO breach, or reopening writes after fencing.

### Exercise 32 — Observability

What must an HA dashboard display?

**Hint:** Role map, LSN/lag, quorum/leases, fencing, endpoint routing, and business health.

### Exercise 33 — Alert Context

What should a good failover alert include?

**Hint:** Node/region, leader/candidate, lag, LSN/timeline, fencing state, and runbook links.

### Exercise 34 — Maintenance

Why avoid restarting multiple quorum members simultaneously?

**Answer:** It can break majority and render leader coordination unavailable.

### Exercise 35 — Leases

Does lease expiry prove the old process stopped?

**Answer:** No; fencing and write-path enforcement are still needed.

### Exercise 36 — Manual Overrides

What conditions does a manual override require?

**Hint:** Authorized operator, state snapshot, fencing proof, action log, and validation plan.

### Exercise 37 — Incident Records

Why separate facts from hypotheses?

**Answer:** To avoid making destructive decisions based on unverified assumptions.

### Exercise 38 — Failback

After the old primary rejoins as standby, when is it safe to switch back to it?

**Hint:** Once caught up, timeline/replication healthy, validation passed, and within an approved maintenance window.

### Exercise 39 — Automation Testing

Name one non-happy-path scenario to test.

**Hint:** Network partition, DCS outage, fencing timeout, stale proxy connections, or disagreeing candidates.

### Exercise 40 — Comprehensive Design

A PostgreSQL HA cluster has primary P, standby S, and a monitor in another region. The observer loses contact with P while the application region keeps writing to P; S times out and wants to promote. Describe the safe procedure.

**Hint:** Treat this as an unverified network partition rather than node death. Gather signals from multiple observers, check quorum/leases and the app write path; never promote solely on timeout. Fence P via an independent path, verify completion, check S replay/flush LSN and RPO, obtain approval if data loss or authority is unclear, then promote S, update routing, and validate. Keep P fenced upon return, then rewind/reseed and rejoin.

## 48. HA Automation Design Checklist

### 48.1. Failure Detection

- [ ] Do health checks distinguish process, SQL, replication, and application layers?
- [ ] Are multi-observer / cross-failure-domain checks in place?
- [ ] Do timeouts and consecutive failure counts fit RTO and false-positive risk?
- [ ] Do alerts carry context and escalation routes?

### 48.2. Authority and Fencing

- [ ] Are leader election, quorum, and lease semantics clearly understood?
- [ ] Is the fencing control plane independent of the failing node?
- [ ] Are fencing outcomes verified?
- [ ] Are fencing tokens/epochs enforced on the write path if used?
- [ ] Are stop conditions enforced if fencing fails to confirm?

### 48.3. Candidates and Data Loss

- [ ] Does candidate selection evaluate timelines, LSNs, and replication state?
- [ ] Are synchronous acknowledgment semantics explicit?
- [ ] Do RPO breaches require business approval?
- [ ] Does a clean recovery path exist for logical corruption or ransomware?

### 48.4. Promotion and Routing

- [ ] Is strictly one actor authorized to promote?
- [ ] Are actions idempotent or state-checked?
- [ ] Is the old primary fenced prior to shifting traffic?
- [ ] Are proxies, DNS, and connection pools updated?
- [ ] Does application/business validation run before full traffic opens?

### 48.5. Human Operations

- [ ] Are incident commander, DBA, infra, app, and business roles clear?
- [ ] Is break-glass access tested and audited?
- [ ] Are backup on-call and escalation paths ready?
- [ ] Do runbooks define preconditions, expected results, and stop conditions?
- [ ] Are failback, rejoin, rewind, and reseed procedures drilled?

## 49. Drill and Post-Incident Checklist

- [ ] Process crash tested?
- [ ] Network partition / partial failure tested?
- [ ] Quorum / DCS / monitor outage tested?
- [ ] Both fencing success and fencing timeout tested?
- [ ] Stale clients / proxy routing tested?
- [ ] Manual overrides and break-glass access tested?
- [ ] Async data-loss / RPO decisions tested?
- [ ] Old primary rejoin tested?
- [ ] Independent backup/PITR tested?
- [ ] End-to-end RTO measured?
- [ ] Actual RPO and business acceptance recorded?
- [ ] Post-incident action items assigned owners and deadlines?
- [ ] Alerts, runbooks, and configs updated?
- [ ] Re-drilled after major changes?

## 50. Quick Reference Table

| Concept | Meaning |
|---|---|
| HA automation | Automated monitoring and role/routing transitions on failure |
| Failure detection | Detecting signals that a node/service is unresponsive |
| Failure declaration | Classifying a node unavailable per policy |
| False positive | Healthy node mistakenly marked down |
| False negative | Broken node still passing health checks |
| Partial failure | Subset of network, service, or control plane fails |
| Network partition | Node groups unable to communicate with each other |
| Split-brain | Multiple primaries accepting writes concurrently |
| Quorum | Majority/votes needed to hold coordination authority |
| Witness | Member assisting quorum/election decisions |
| Lease | Time-bounded leadership grant |
| Fencing | Stopping the old primary from continuing to accept writes |
| Fencing token | Epoch/token used to reject stale writers |
| Promotion | Converting a standby into a primary |
| Switchover | Planned primary transition |
| Failover | Incident-driven primary transition |
| Failback | Returning workloads to the desired topology |
| Rejoin | Bringing an old node back as a standby |
| `pg_rewind` | Synchronizing a diverged node when prerequisites hold |
| Break-glass | Controlled emergency access privilege |
| Human-in-the-loop | Step requiring human decision or approval |
| Stop condition | Mandatory condition halting automation/runbooks |
| RPO | Maximum acceptable data loss |
| RTO | Maximum acceptable recovery time |
| Incident commander | Person coordinating incident response |
| Audit trail | Evidence of actor, action, state, and timestamp |
| Idempotency | Retrying an action without unintended side effects |

## 51. Summary

**Automation makes HA respond faster, yet cannot replace fencing, data rules, or business judgment.** Health checks observe only part of the system; timeouts never prove the primary died. Quorum and leader election settle coordination authority without automatically guaranteeing a candidate holds the freshest data or the old primary stopped writing. Fencing must be verified before opening writes on a new primary to avoid split-brain.

A sound design automates steps with deterministic signals and outcomes: collecting metrics/logs, alerting, checking preconditions, executing pre-engineered fencing, promoting per policy, updating routing, and running smoke tests. During network partitions, fencing uncertainty, disagreeing candidate timelines/LSNs, corruption, security incidents, or RPO breaches, procedures must involve human approval and business owners. Manual intervention requires break-glass access, clear roles, escalation paths, preconditions, expected outcomes, stop conditions, and audit trails.

After failover, keep the old primary isolated, then rejoin it via `pg_rewind` when eligible or reseed from a base backup. Failback is never simply reversing DNS; it demands a single authoritative writer, validation, and plans for handling intervening writes. Backups and PITR remain an independent layer because standbys faithfully replicate logical corruption and malicious changes.

Operational rule: **automate what can be proven safe, halt when evidence falls short, involve the right human for data-risk decisions, and drill both happy paths and partial failures.** Only a procedure that is measured, audited, and practiced can meet RPO and RTO during real incidents.
