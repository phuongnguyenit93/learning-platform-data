# Designing Runbooks and Incident Response Processes

Cloud systems can fail across many layers: application, network, identity, database, queue, storage, third-party services, or the provider's own control plane. When an incident occurs, the operations team must quickly understand the impact, assign responders, minimize damage, restore service, and preserve evidence for investigation. If every step exists only in the memory of a few engineers, response slows down, actions become inconsistent, and the incident can worsen.

A **Runbook** describes how to perform a specific operational procedure. An **Incident response playbook** describes how to coordinate handling a class of incident. An **Incident management process** defines the incident lifecycle, roles, severity levels, communications, decisions, and closure criteria. These three components complement each other.

In the **CLOUD_ARCHITECTURE** module, this lesson focuses on designing runbooks and incident response processes so cloud service operations are predictable, measurable, and continuously improvable. The goal is to help teams know **when to declare an incident, who commands, what to do first, how to change the system safely, what evidence to preserve, and what criteria prove the service has recovered**.

## 1. Runbooks, Playbooks, and the Incident Process

| Component | Answers the Question | Example |
| --- | --- | --- |
| **Runbook** | How do you execute a specific operational task? | Fail over database, rotate credentials, drain node |
| **Playbook** | In what sequence do you handle a category of scenarios? | Database latency, credential compromise, region outage |
| **Incident process** | How do you organize coordination, decision-making, and notifications? | Severity, incident commander, escalation, closure |
| **Standard operating procedure (SOP)** | What standard must a recurring task follow? | Access review, backup verification, patch window |

A good runbook is not just a list of commands. It must state the objective, scope, entry conditions, required permissions, risks, execution steps, expected output, rollback/stop instructions, and completion evidence.

### When Is a Runbook Needed?

- Operations with high impact or that are difficult to reverse.
- Recurring incidents or those frequently happening after hours.
- Multi-step work or tasks spanning multiple teams.
- Risk of data loss, downtime, security impact, or significant cost.
- Situations where an on-call responder who is not a deep specialist must still execute initial steps safely.
- Compliance or audit evidence requirements.

Not every minor task needs lengthy documentation. Focus runbooks on risky decisions and actions, commonly forgotten steps, and exit paths when outcomes diverge from expectations.

## 2. The Incident Lifecycle

An incident may transition through these states:

~~~mermaid
stateDiagram-v2
    [*] --> Detected
    Detected --> Triaging
    Triaging --> Declared
    Triaging --> Resolved: False positive / transient
    Declared --> Containing
    Containing --> Investigating
    Investigating --> Recovering
    Recovering --> Monitoring
    Monitoring --> Resolved: Recovery criteria met
    Monitoring --> Investigating: Regression
    Resolved --> Closed: Review / evidence complete
    Closed --> [*]
~~~

This is a conceptual model; an organization may merge or rename states. What matters is that everyone knows the current state, who is responsible, what decision is pending, and the criteria to advance.

### Main Phases

1. **Detect:** receive an alert or report from a customer, employee, or provider.
2. **Triage:** determine scope, impact level, and whether an incident must be declared.
3. **Declare/organize:** open the response channel, assign the Incident Commander and supporting roles.
4. **Contain:** limit impact, protect data, and stop the incident from spreading.
5. **Diagnose:** collect evidence, form hypotheses, and test in a controlled manner.
6. **Mitigate/recover:** apply mitigation measures and restore functionality.
7. **Verify/monitor:** confirm SLIs and business behavior are normal, watch for recurrence.
8. **Close/learn:** finalize timeline, communications, post-incident review, and action items.

It is not mandatory to finish root-cause diagnosis before recovering. In many incidents, reduce impact safely first and investigate deeply once the service is stable.

## 3. Severity Classification and Impact Levels

Severity expresses the seriousness of current or projected impact, guiding response speed and mobilization level. Do not classify solely by technical error name.

An example matrix:

| Level | Impact | Sample Response |
| --- | --- | --- |
| **SEV-1 Critical** | Widespread outage of a critical service, severe data loss, active breach, or major safety/compliance impact | Immediate activation, centralized command, continuous cadence updates |
| **SEV-2 High** | Significant degradation of a critical capability, many customers affected, limited workarounds | Mobilize relevant teams, fast escalation |
| **SEV-3 Medium** | Partial impact or small cohort affected, workaround exists, no sign of spreading | Owning team handles within defined response hours |
| **SEV-4 Low** | Minor bug, non-critical degradation, or operational issue without significant impact | Monitor and address via backlog/maintenance |

Exact names, SLAs, and thresholds are defined by the organization. An issue can escalate in severity as scope or risk changes. Declarers should not hesitate to raise severity when impact is unclear; severity can be downgraded once evidence supports it.

### Impact Assessment Criteria

- Number of customers/tenants/users and percentage of traffic affected.
- Business capabilities: login, payment, booking, export, administration.
- Degree of disruption: total failure, latency, incorrect data, single-region only.
- Security risk: unauthorized access, data exposure, credential compromise.
- Integrity/durability: lost writes, duplicate writes, inconsistent data.
- Duration of impact and rate of spread.
- Whether a safe workaround exists and whether customers can self-recover.
- Legal/contractual obligations and reputation.

### Severity Is Not Bug Priority

An incident is an event actively impacting service, whereas a backlog bug is work to be fixed. A bug not yet causing impact may have high priority without being an incident; a tiny configuration mistake causing major downtime may be SEV-1. Separating the two concepts enables proper coordination.

## 4. Roles and Command Structure

Incidents require clear coordination. Do not let everyone edit production simultaneously or allow multiple people to issue conflicting decisions.

| Role | Responsibilities |
| --- | --- |
| **Incident Commander (IC)** | Overall coordination, setting objectives, assigning tasks, deciding phase transitions, maintaining the big picture |
| **Technical Lead** | Technical investigation, proposing mitigations/recovery, managing system changes |
| **Operations/Executor** | Executing assigned commands/runbooks, recording output and verifying |
| **Communications Lead** | Updating stakeholders/customers using verified information |
| **Scribe** | Recording timeline, decisions, hypotheses, actions, and evidence |
| **Domain/Service Owner** | Providing system knowledge and business decisions within scope |
| **Security/Privacy/Legal** | Engaging when signs of breach, personal data exposure, or legal obligations arise |

In small teams, one person may wear multiple hats; however, the IC should not both coordinate and perform every technical action in a major incident. Role separation reduces cognitive load and improves situational awareness.

### Command Principles

- One IC at any given time; hand off explicitly during shift changes.
- Every production action has an owner and an executor.
- Technical Lead proposes options; IC confirms priorities/trade-offs during the incident.
- The scribe does not speculate; record events, timestamps, and sources.
- Designate a replacement whenever a primary role steps away from the incident.
- Do not issue commands across fragmented, unsynchronized chat channels.

### RACI for Critical Decisions

Before an incident, define who is Responsible, Accountable, Consulted, and Informed for: failover, feature disabling, release rollback, credential rotation, data restore, customer notification, and incident closure. This is especially important when actions affect security or data.

## 5. Designing a Runbook Structure

A consistent template helps on-call responders find information quickly under pressure.

| Section | Content |
| --- | --- |
| Title/ID/owner | Name, identifier, service owner, review date |
| Purpose | Situation and objective |
| Trigger | Alert, symptom, or entry condition |
| Scope/impact | Related systems, regions, tenants, and data |
| Preconditions | Permissions, tools, access paths, maintenance locks |
| Safety | Risks, blast radius, what not to do |
| Diagnosis | Initial checks, queries/dashboards, hypotheses |
| Actions | Execution steps, expected output, and checkpoints |
| Stop conditions | When to stop, escalate, or roll back |
| Recovery validation | SLIs, business checks, and observation window |
| Evidence | Logs, events, command output, approvals, tickets |
| Rollback | How to reverse or recover |
| Escalation | Contacts and required context to provide |
| Related docs | Architecture diagrams, dashboards, service catalog |

### Writing Verifiable Action Steps

Each step should follow this structure:

1. **Action:** what to do, on which resource, and using which identity.
2. **Expected result:** the state/value that should be observed.
3. **Verify:** which command/query/dashboard confirms it.
4. **If not expected:** where to stop and whom to engage.

Avoid writing “restart service if needed” without stating conditions, replica scope, impact on in-flight requests, concurrency limits, and post-restart checks.

### Dangerous Commands

Commands that delete, restore, fail over, rotate keys, or alter firewall policies must specify the environment, resource ID, pre-checks, and approval requirements. Use clearly named placeholders; never embed credentials/tokens or unbounded wildcard commands. Runbooks should use dry-run/preview modes where tools support them.

## 6. Alert Detection and Triage

An alert is only a signal to investigate, not automatically an incident. Triage must verify the signal, scope, and impact.

### Initial Triage Checklist

1. Is the alert still firing or has it self-recovered?
2. Which SLI is affected: availability, latency, error rate, saturation, correctness?
3. Since when and for how long?
4. All regions or only one AZ/service/tenant?
5. Was there a recent deployment, config change, traffic spike, or provider event?
6. Are there security or data integrity indicators?
7. Is there a safe workaround or customer-visible impact?
8. Is a similar incident already open?

### Correlation

Compare service dashboards against dependencies, deploy timelines, cloud provider health, DNS/certificates, identity providers, and networking. Do not conclude root cause simply because the first alert fired on one service; that service may merely be where symptoms surface.

### Alert Noise Reduction

- Group alerts with the same symptom into one incident.
- Deduplicate by resource/service and time window.
- Alert on user impact/SLOs rather than every resource threshold.
- Keep symptom and cause alerts distinct where useful.
- Include owner, severity, runbook link, and next action on every alert.
- Review false positives after incidents; never silently disable alerts just to cut noise.

## 7. Collecting Evidence and Maintaining a Timeline

Before altering system state, collect enough evidence to understand the incident unless delay causes greater harm. For security incidents, preserving evidence can be a critical requirement.

### Evidence to Record

- UTC timestamps and display timezone.
- Incident ID, request/trace/correlation IDs.
- Affected service, region, AZ, tenant, or resources.
- Relevant alerts, metrics, logs, and traces.
- Deployment/config/policy changes.
- Commands run, executor, target, and output.
- Decisions, approvers, and rationale.
- Snapshots/backups/checkpoints if needed.
- Provider support cases or external dependency details.

### Timeline

| Time | Event/Action | Owner | Result/Evidence |
| --- | --- | --- | --- |
| 10:02 | Alert p99 latency fired | Monitoring | Dashboard link |
| 10:05 | Incident SEV-2 declared | IC | Incident channel |
| 10:10 | Rollout paused | Release owner | Deployment event |
| 10:18 | Traffic routed to healthy pool | Technical lead | Error rate dropped |

This is an illustrative timeline. Record actual timestamps and never rewrite history to make it “look clean”; corrections should be added as annotations with author and timestamp.

### Protecting Sensitive Data

Do not copy secrets, private keys, access tokens, or PII payloads into chat/tickets unnecessarily. Link to access-controlled log stores instead. Security incidents must follow chain-of-custody rules and dedicated evidence storage.

## 8. Containment: Reducing Impact Before Deep Investigation

Containment stops failures from spreading or limits damage. Choose the lowest-risk measure that achieves the goal, understanding blast radius and rollback conditions.

Examples:

- Pause a rollout or roll back a new release.
- Disable a faulty feature flag.
- Drain a problematic node/AZ.
- Limit concurrency/rate or enable load shedding.
- Isolate compromised credentials and revoke sessions/tokens.
- Pause consumers or replication if corrupt data is propagating.
- Shift traffic to a standby region/pool.
- Block specific endpoints/egress per security policy.

### Choosing Containment by Risk Type

| Incident | Containment to Consider | Warning |
| --- | --- | --- |
| Faulty release | Pause rollout/rollback | Verify executed migrations and backward compatibility |
| Database overload | Admission control, throttle heavy queries | Do not mass-kill sessions without understanding transactions |
| Credential compromise | Revoke/rotate, isolate workload | Ensure new credentials and dependencies stay synchronized |
| Data corruption | Stop faulty writers/consumers | Do not restore before identifying a good recovery point |
| Region outage | Fail over routing per plan | Avoid split-brain and check RPO |
| Queue backlog | Throttle producer/consumer concurrency | Do not scale up consumers while downstream is failing |
| DDoS/abuse | WAF/rate limiting/traffic filtering | Protect legitimate traffic and avoid false blocks |

### Containment Is Not Recovery

Shedding load or disabling a feature may shrink impact, but the service is not necessarily fully recovered. Clearly document the degraded state, missing capabilities, and remaining risks; do not close an incident merely because the primary alert stopped firing.

## 9. Disciplined Diagnosis

During an incident, multiple hypotheses may appear equally plausible. Instead of making several changes at once, form a hypothesis, pick a discriminating test, and record the outcome.

### Hypothesis-Driven Troubleshooting

| Field | Example |
| --- | --- |
| Observation | API p99 jumped from 200 ms to 4 seconds |
| Hypothesis | Connection pool exhausted due to slow database |
| Test | Compare pool wait, active connections, DB query latency |
| Expected if true | Pool wait rises before requests time out |
| Result | Pool wait rises, DB CPU is normal |
| Next step | Check for connection leaks/long transactions |

### Change One Variable When Possible

If you simultaneously increase pool size, change timeouts, and restart the database, it becomes very hard to tell which change helped or hurt. Test small changes one at a time with checkpoints and rollback; an exception is an emergency requiring simultaneous actions to stop damage, in which case document the decision clearly.

### Distinguishing Symptom, Trigger, and Root Cause

- **Symptom:** what users or monitoring observe.
- **Trigger:** the event immediately preceding the start of the incident.
- **Root cause/contributing factors:** underlying conditions enabling or amplifying the failure.

A deployment may be the trigger, while the root cause lies in insufficient capacity headroom or a non-backward-compatible schema. Postmortems must examine the system, not stop at the most recent event.

## 10. Recovery and Service Verification

Recovery returns the system to a safe serving state. “Process is running” or “HTTP 200 returned” is insufficient proof of recovery.

### Verification Dimensions

- **Availability:** eligible requests are served successfully.
- **Latency:** p95/p99 return within SLO or agreed degraded thresholds.
- **Correctness:** data and business outcomes are accurate.
- **Durability:** critical writes are committed and recoverable.
- **Security:** credentials, policies, and access paths are controlled.
- **Capacity:** the system sustains current load with reasonable headroom.
- **Backlog:** queues, retries, and pending operations drain steadily.

### Controlled Recovery Process

1. Define the target safe state and authoritative data source.
2. Check preconditions before recovery: backups, replication lag, migrations, credentials, capacity.
3. Apply a small change or canary if possible.
4. Run smoke tests and business transactions.
5. Increase traffic/concurrency in stages.
6. Monitor SLIs, queue age, error budget, and unexpected side effects.
7. Verify there is no retry storm or secondary backlog.
8. Record mitigation/recovery timestamps and verifier.

### Do Not Recover Everything at Once

After a prolonged outage, turning on every worker, consumer, and scheduled job simultaneously can trigger a surge. Ramp up in batches, cap concurrency, and prioritize critical functions. Verify downstream readiness before opening full traffic.

## 11. Runbook: Database Latency or Connection Exhaustion

### Trigger

- API p95/p99 spikes.
- DB connection pool wait/timeouts rise.
- Abnormal database CPU, IOPS, lock wait, or replication lag.
- Rising query error rate or long-running open transactions.

### Triage

1. Identify impact by database/cluster/region and endpoint.
2. Correlate timestamps with deployments, migrations, batch jobs, and traffic spikes.
3. Inspect active connections, pool wait, slow queries, locks, CPU, memory, and I/O.
4. Distinguish database overload from application-side connection leaks.
5. Identify read/write breakdown and which tenants drive most load without exposing sensitive data.

### Containment

- Pause non-critical batch/reporting queries.
- Reduce concurrency or rate-limit heavy endpoints.
- Enable caching/stale serving only for permitted data.
- Cap new pools if total connections approach database quotas.
- If a connection leak exists, drain/restart instances in rolling batches while accounting for in-flight requests.

### Recovery

- Verify connection counts, pool wait, DB latency, and query throughput stabilize.
- Run safe read/write verification transactions.
- Monitor locks/replication lag and backlogs.
- Gradually ramp traffic and re-enable scheduled batches.

**Stop condition:** do not blindly increase pool size when the database is already at its connection limit; do not kill transactions or fail over the database without understanding the impact on consistency/RPO.

## 12. Runbook: Faulty Deployment or Configuration

### Trigger

- Error rate rises immediately after release.
- Health checks fail on the new version.
- Latency or memory/CPU changes abnormally.
- One region/AZ exhibits different behavior due to config drift.

### Triage

1. Record release ID, commit/config version, and rollout start time.
2. Identify affected cohorts/versions/regions.
3. Correlate deployment events with SLIs and error logs.
4. Check schema migrations, secrets, feature flags, and dependency compatibility.
5. Determine whether rollback is safe.

### Containment and Recovery

- Pause rollout/canary progression.
- Turn off a feature flag if the defect is isolated and the flag has safe semantics.
- Roll back artifacts/config if schema and data remain compatible.
- If a destructive database migration already ran, use a forward fix or recovery plan; do not mechanically roll back the binary.
- After rollback, verify all instances have converged on the target version/config.
- Run smoke tests covering business journeys, not just liveness endpoints.

**Stop condition:** do not roll back database migrations or secret rotations without understanding bidirectional compatibility. Record old/new versions and applied commands so no instance stays on mismatched config.

## 13. Runbook: Region/AZ Outage and Failover

### Trigger

- Health checks/provider status confirm a failure domain is unavailable.
- Traffic errors/latency concentrate in a region/AZ.
- Control plane or data plane is impaired.

### Triage

1. Determine scope: single AZ, entire region, control plane, or specific service.
2. Check provider health and independent telemetry.
3. Determine replication lag, last known good write, and RPO.
4. Verify the standby region has capacity, key access, networking, and dependencies.
5. Confirm which primary/writer is currently active to prevent split-brain.

### Failover

- Follow a rehearsed runbook/provider procedure.
- Fence/disable the old writer via supported mechanisms before promoting the new writer.
- Check replication/data consistency and make an explicit RPO acceptance decision.
- Shift traffic incrementally and verify DNS/service discovery/client connections.
- Watch for connection storms, cache warm-up, queue backlogs, and downstream quotas.

### Failback

Failback is not simply flipping routing back to the original region. It requires data synchronization, writer identification, verifying replication direction, controlled ownership transfer, and rollback readiness. Do not run active-active if the data design does not support concurrent writes.

**Stop condition:** do not promote a replica without understanding lag/data loss, and never allow two writers to run concurrently outside the designed model.

## 14. Runbook: Credential Compromise or Suspected Data Breach

This incident class requires preserving evidence and coordinating with Security/Privacy/Legal. The runbook should be designed with specialist teams; on-call responders must not guess notification obligations.

### Containment

1. Activate the security incident channel and assign an appropriate incident lead.
2. Identify affected principals/credentials/resources.
3. Revoke/disable credentials or sessions in an order that avoids locking out recovery systems.
4. Isolate suspected compromised workloads/networks/paths.
5. Revoke overly broad permissions and block anomalous egress or sessions per policy.
6. Preserve audits, logs, images/snapshots, and request IDs.
7. Check for persistence, lateral movement, and accessed/exported data.

### Recovery

- Provision new credentials via secret manager/rotation workflows; never reuse old secrets.
- Patch the root cause of permission/secret exposure.
- Re-enable workloads only after verifying images/configs and identity.
- Monitor for anomalous access, data exfiltration, and policy changes.
- Privacy/Legal assesses data scope, obligations, and notification content under applicable regulations.

Do not delete logs or rebuild environments before preserving required evidence. Do not send external notifications outside authorized channels.

## 15. Runbook: Queue Backlog and Consumer Failures

### Trigger

- Oldest message age breaches SLA.
- Queue depth rises continuously.
- DLQ grows.
- Consumer errors/timeouts and dependency load increase.

### Triage and Containment

1. Identify affected topic/partition/subscription and event type.
2. Compare producer rate, consumer throughput, retry/redelivery, and dependency latency.
3. Check for poison messages, schema mismatches, and recent consumer deploys.
4. Throttle producers or consumer concurrency if downstream is overloaded.
5. Route failing messages to DLQ/quarantine to avoid infinite immediate retries.
6. Preserve idempotency/event ordering during replay.

### Recovery

- Restore consumer version/config.
- Check dependency quotas and capacity.
- Replay small batches from DLQ after fixing the root cause.
- Monitor oldest message age and drain rate.
- Check for duplicate side effects and lost or out-of-order events.

**Stop condition:** do not add workers if downstream is the bottleneck; do not bulk-replay DLQ before knowing whether messages can cause duplicate side effects.

## 16. Runbook: Data Corruption or Accidental Deletion

### Trigger

- Checksum mismatches or abnormal drops in record counts.
- Customers report missing or incorrect data.
- Audits record unplanned bulk deletes/overwrites.
- Pipelines produce bad data propagating to replicas/search/analytics.

### Triage

1. Stop or throttle the writer/job corrupting data.
2. Identify data types, tenants, tables/buckets/prefixes, and incident timestamp.
3. Locate the last known good backup/version/transaction log.
4. Check whether replication has propagated the corruption.
5. Preserve audits, manifests, checksums, and evidence.

### Recovery

- Restore into an isolated environment first.
- Compare checksums, counts, versions, and business invariants.
- Apply deletion ledgers/retention/legal holds and required event replays.
- Choose partial restore, point-in-time recovery, or forward correction based on blast radius.
- Cut over traffic only after Data Owner/Technical Lead confirms data accuracy.
- Monitor for recurring corruption and downstream projections.

**Stop condition:** do not overwrite production directly before verifying a clean recovery point, do not delete evidence, and do not treat replication as an independent backup.

## 17. Incident Communications

Clear communication reduces repetitive questions and prevents teams from making decisions based on conflicting assumptions. Incident communications must separate internal coordination channels, technical channels, and stakeholder/customer updates.

### Update Content

Each update should state:

- Incident ID and current severity.
- Summary of verified impact.
- Start time/current estimate, if evidence-backed.
- Affected systems/regions/features.
- Actions underway and results.
- Safe user workaround, if available.
- Active investigations and unknowns.
- Next update timestamp.

Do not speculate on root cause or promise a recovery time without basis. Explicitly stating “currently unknown” is better than giving a confident-sounding but wrong conclusion.

### Cadence by Severity

Organizations can define different cadences for SEV-1/2/3. For example, severe incidents receive short updates every 15–30 minutes or immediately upon material change; lower-severity incidents may update hourly. Cadence must keep stakeholders informed without pulling the IC away from coordination.

### Status Update Template

~~~text
Incident: INC-2026-042
Severity: SEV-2
Status: Mitigating
Impact: A portion of booking creation requests in region-2 are timing out.
Start: 10:02 UTC (full scope under verification).
Actions: Paused rollout; incrementally shifting traffic to healthy pool.
Known risks: Several operations have undetermined payment states; reconciliation underway.
Next update: 10:30 UTC or sooner upon material change.
~~~

The template above illustrates structure; use verified timestamps, system names, and impact levels for real incidents.

### Customer Communications

Customer notifications must focus on impact and actions they can take:

- Which capabilities are affected?
- Was data lost/corrupted or is it only slow/unavailable?
- Is there a safe workaround?
- Has service recovered or is it still degraded?
- When is the next update?

Communications regarding breaches, personal data, or notification obligations must be approved by Security/Privacy/Legal under applicable policies and regulations.

## 18. Escalation and Engaging the Right Specialists

Runbooks need a clear escalation path:

- Primary on-call and secondary on-call.
- Service owner/domain expert.
- SRE/platform/network/database/security.
- Cloud provider support.
- Third-party vendor/payment provider.
- Incident executive/business owner.
- Privacy/legal/compliance when data or regulatory obligations are involved.

### Context to Provide When Escalating

Do not just send “service is broken.” Provide:

1. Incident ID and severity.
2. Impact/region/tenant/time window.
3. Specific SLIs and symptoms.
4. Steps already taken and results.
5. Current hypotheses and unknowns.
6. Decision needed from the escalated party.
7. Permissioned links to dashboards/logs/traces.

### Escalation When Unresponsive

Define escalation timeouts: after how long without acknowledgment to call backup numbers/managers. For SEV-1, do not wait through multiple chat cycles; use approved paging/phone channels. Avoid sharing secrets or customer data in inappropriate channels.

## 19. Shift Handovers

Incidents can span many hours or days. Handovers must transfer both accountability and context, not merely drop a chat link.

### Handover Checklist

- Incident ID, severity, and status.
- Current impact and start time.
- Current IC/Technical Lead/Communications Lead.
- Tested hypotheses and results.
- Production changes executed and current versions/configs.
- Remaining open risks and undetermined operations.
- Next actions, owners, and deadlines.
- Alerts/dashboards/logs/traces and provider cases.
- Decisions awaiting approval.
- Next stakeholder update schedule.

### Synchronous Handover

For severe incidents, the outgoing IC briefs live and the incoming IC confirms assumption of command. Update the incident channel, ticket, and contact tree. Never leave two ICs each thinking the other is in command.

## 20. Recovery and Incident Closure Criteria

An incident should transition to Resolved only when technical and business criteria are met. An incident moves to Closed after minimum post-incident steps and evidence are complete or converted into owned action items.

### Recovery Acceptance Criteria

- Primary SLIs stay within target thresholds over a sufficient observation window.
- End-to-end business journeys work, not just health endpoints.
- Data integrity/durability is verified or unknown states are actively managed.
- Queue backlogs/retries/pending jobs are draining steadily.
- Security controls/credentials/policies are safely restored.
- No traffic routes unexpectedly to faulty nodes/versions.
- Capacity retains sufficient headroom for current load.
- No signs of regression after traffic ramp-up.

### Resolved vs. Closed

Resolved means the active impact has ended or dropped to an acceptable level. Closed means the incident record contains timeline, impact, communications, evidence, and post-incident review/action items per process. An incident may be Resolved while follow-up work remains open.

### Post-Recovery Monitoring

Set the monitoring period based on failure characteristics. For periodic bugs, observe across at least one full cycle or run synthetic checks. Do not downgrade severity prematurely while queues are still backing up or operations remain unreconciled.

## 21. Post-Incident Reviews and Blameless Postmortems

Postmortems examine how systems and processes allowed an incident to occur, why detection/containment/recovery took time, and how to reduce recurrence. The goal is learning and improvement, not blaming individuals.

### Postmortem Contents

1. Executive summary: what happened and impact.
2. Timeline: events, decisions, and actions in chronological order.
3. Impact: customers, tenants, data, SLOs, financial/contractual impact.
4. Detection: which alerts caught it, which were missing or noisy.
5. Root cause and contributing factors.
6. What went well / what was difficult.
7. Mitigation/recovery effectiveness.
8. Action items with owners, priorities, and due dates.
9. Lessons for architecture, runbooks, testing, monitoring, and training.

### Blameless Does Not Mean Without Accountability

Analysis focuses on system conditions, guardrails, available information, and decision pressure. Concrete owners are still needed to fix defects, track deadlines, and measure outcomes. Avoid framing like “operator forgot step X” when the system lacked automation/checklists to prevent predictable human error.

### Good Action Items

Action items require:

- Concrete action, not merely “improve monitoring.”
- An accountable individual/team owner.
- Priority and due date.
- Verifiable completion criteria.
- Link to the incident/ticket and verification metric.

Example: “Add alert when oldest message age on payment-events exceeds 5 minutes for 3 consecutive windows; owner Payments SRE; verify via backlog test.” Actual thresholds must reflect SLAs.

## 22. Managing Emergency Changes During Incidents

Emergency changes may be necessary to reduce impact but must still remain controlled.

### Guardrails

- Identify who holds approval authority.
- State objective, blast radius, and risk.
- Make the smallest change possible.
- Include pre-checks, verification, and rollback.
- Record who executed it, command/config, timestamp, and result.
- Review post-incident and sync back to IaC/config source to eliminate drift.

Do not edit the cloud console directly and forget IaC; the next deployment may overwrite it or leave confusing drift. If a direct change is unavoidable, create a follow-up to reconcile the source of truth.

### Break-Glass Access

Break-glass enables privileged access when normal processes cannot meet response times. It requires MFA/strong authentication, time-bound grants, prior approval or post-hoc review, independent auditing, usage alerts, and revocation after the incident. Never use break-glass accounts for routine operations.

### Risk/Rollback Decisions

A mitigation may reduce downtime while increasing data loss risk. The IC and Technical Lead must document the trade-off, RPO/RTO, approvals, and stop conditions. For security incidents, coordinate with Security/Legal before actions that might destroy evidence.

## 23. Operational Readiness Before Release

A service is not operationally ready if it only has a deployment pipeline and a dashboard. Before production, verify that the on-call team knows how to detect, investigate, roll back, and recover.

### Operational Readiness Review

- Service owner, on-call rotation, and escalation path exist.
- Diagrams exist for dependencies, data flow, trust boundaries, and failure domains.
- SLIs/SLOs, dashboards, alerts, and synthetic checks exist.
- Runbooks cover high-impact failure modes.
- Backup/restore, DR, and RPO/RTO have been tested.
- Capacity limits, quotas, autoscaling, and load shedding exist.
- Deploy/rollback and emergency change procedures exist.
- Credential/secret rotation and security incident paths exist.
- Logging/tracing/auditing are sufficient without exposing secrets/PII.
- Retention, data ownership, and processor contacts exist if needed.
- Status page/customer communication templates exist.
- Known risks, limitations, and dependency SLAs are documented.

### Service Catalog

A service catalog can store:

| Field | Purpose |
| --- | --- |
| Service name/owner | Identify the accountable team |
| Criticality/SLO | Know priority level |
| Dependencies | Engage the right teams during incidents |
| Runtime/region | Know where workloads run |
| Data classification | Understand data risk |
| Dashboard/alerts | Open the right tools |
| Runbooks/playbooks | Locate operational procedures |
| On-call/escalation | Page the right responders |
| Backup/DR | Know recovery plans |
| Change history | Look up recent changes |

The catalog needs an owner and update workflow; stale records can slow response more than having no information.

## 24. SLIs, SLOs, Error Budgets, and Incident Policy

An SLI measures service experience/outcomes; an SLO is the target for an SLI over a window; an error budget is the allowable error/degradation within that target.

Examples:

- Availability: ratio of eligible requests completing successfully.
- Latency: ratio of requests completing below threshold.
- Durability/correctness: ratio of transactions stored accurately or without loss.
- Freshness: lag of projection data.
- Job completion: ratio of jobs finishing before deadline.

### How SLOs Influence Incident Response

When burn rate spikes, the system can trigger high-severity alerts and prioritize reliability work. When the error budget is exhausted, the organization can restrict risky releases or shift changes toward stability. Do not alert solely on 90% CPU if users are unaffected; CPU is a saturation signal, whereas SLIs reflect service outcomes.

### Multi-Window Burn-Rate Alerts

An alert can compare error budget consumption across short and long windows to detect incidents quickly while avoiding noise. Burn-rate thresholds and windows must tie to SLOs, traffic, and impact; do not copy the same configuration blindly across every service.

### Error Budget Policy

Define in advance how the error budget is governed:

- When to pause feature releases.
- When to prioritize reliability tasks.
- Who has authority to grant exceptions.
- When releases may resume.
- How to notify stakeholders and review periodically.

An error budget is a decision-making tool, not a target to “spend down” or an excuse to ignore incidents carrying security or data-integrity risks.

## 25. Backup, Restore, and Disaster Recovery Runbooks

Backups only hold value if they can be restored within acceptable time and data loss bounds.

### Key Terms

- **RPO (Recovery Point Objective):** maximum tolerable data loss, measured as time from recovery point to incident.
- **RTO (Recovery Time Objective):** target time to restore the service.
- **MTTR:** mean time to repair/restore; exact measurement depends on the organization.
- **Failover:** switching operations to a standby system.
- **Failback:** returning operations to the preferred primary environment.

### Restore Runbook

1. Identify dataset/system and incident scope.
2. Select recovery point per RPO and last known good state.
3. Verify backup integrity, encryption keys, and access permissions.
4. Restore into an isolated environment or prepared target.
5. Apply deletion ledgers/legal holds and required migrations.
6. Check row/object counts, checksums, and business invariants.
7. Restore dependencies, networking, secrets, and identity.
8. Run smoke tests/business transactions.
9. Open traffic via canary and monitor.
10. Record actual recovery point, RPO/RTO, and deviations.

### Periodic Restore Testing

Do not just verify that backup jobs report “success.” Conduct timed restore drills verifying data and access permissions. Test representative partial datasets and full recovery according to criticality. Immutable/cross-account backups must also test access paths under a compromised production account scenario.

### DR Is Not Just the Database

Plans must cover networking, DNS, identity, KMS, secrets, container images, IaC, service discovery, queues, object storage, certificates, and on-call. If the database has a replica but keys are unreachable or DNS cannot switch, the service still fails to recover.

## 26. Capacity, Saturation, and Graceful Degradation

Many incidents begin as capacity issues and are then amplified by retries, queues, or traffic shifts.

### What a Capacity Runbook Must Know

- Normal/peak traffic and growth forecasts.
- CPU/memory/network/IOPS per failure domain.
- Connection pools, file descriptors, thread/worker limits.
- Queue throughput and backlog age.
- Autoscaling signals, cooldowns, and cloud quotas.
- Downstream/vendor quotas.
- Headroom when losing an AZ/node/region.

### Graceful Degradation

When capacity runs short, the system can shed non-critical capabilities:

- Drop recommendations/personalization.
- Serve cached data within an approved stale window.
- Defer exports/batches.
- Reduce polling frequency.
- Disable real-time reporting to protect transactions.
- Reject over-quota requests early.

Never degrade security controls, authentication, authorization, or transaction integrity to “preserve availability.” Define a degradation matrix ahead of time.

### Noisy Neighbors and Fairness

When one tenant or workload consumes a disproportionate share of resources, runbooks should apply quotas, per-tenant rate limits, and worker concurrency caps. Throttle only after verifying identity/scope; do not use IP as tenant identity. Monitor throttling effects on other tenants.

## 27. Automation and Self-Healing with Guardrails

Automation reduces repetitive work, but an erroneous automated action can spread faster than manual errors.

### When to Automate?

- Actions have clear conditions and verifiable outputs.
- Risk and blast radius are bounded.
- Actions are idempotent with bounded retries.
- Auditing, alerting, and rollback/stop conditions exist.
- Dry-run or canary mode is available.
- Tested in staging/chaos environments.

### Safe Automation Examples

- Restart an unhealthy replica after draining and verifying quorum/capacity.
- Scale out within quota limits based on validated metrics.
- Retry idempotent jobs with backoff/jitter.
- Route traffic away from unhealthy instances using multi-dimensional health signals.
- Create incident tickets and attach dashboard context when alerts meet criteria.

### Automation Requiring Approval

- Bulk data deletion.
- Database/region failover carrying RPO risk.
- Broad system credential revocation.
- Platform-wide firewall/network access changes.
- Restoring/overwriting production.
- Lifting legal holds or reducing retention.

Automation can prepare plans and run dry-runs; destructive or legally sensitive operations require policy approval.

## 28. Chaos Engineering and Game Days

Chaos engineering tests fault-tolerance hypotheses through controlled failure injection. A game day is a structured rehearsal with participants, goals, roles, and debriefing.

### Experiment Principles

1. Form a specific hypothesis, e.g., “losing one AZ does not breach SLO for more than 5 minutes.”
2. Define blast radius, scope, and stop conditions.
3. Choose a safe environment or approved tenant/canary.
4. Designate a commander, observer, and experiment stopper.
5. Monitor SLIs, data integrity, and dependencies.
6. Restore the environment and verify final state.
7. Record findings, runbook gaps, and action items.

### Game Day Scenarios

| Scenario | What to Prove |
| --- | --- |
| Kill an application instance | Load balancer/health checks redistribute traffic |
| Block dependency network | Timeouts, circuit breakers, bulkheads, and fallbacks work |
| Database failover | RPO/RTO, fencing, and client reconnects |
| Queue backlog | Backpressure, DLQ, and drain rate |
| Expire/rotate credentials | Rotation avoids unexpected outages |
| Lose an AZ | Remaining capacity suffices and traffic shifts cleanly |
| Restore backup | Runbook, keys, data integrity, and recovery time meet targets |
| Alert fatigue drill | On-call spots critical signals amid noise |

Never run chaos experiments in production without proper approvals, impact limits, observability, and stop controls.

## 29. Case Study: Payment Timeout Spike After a Release

A booking platform releases a new version of Booking API. After 8 minutes, alerts show p99 spiking from 350 ms to 4 seconds, timeouts rising on the booking creation endpoint, and requests to the Payment provider tripling. Some customers report uncertainty about whether their bookings succeeded.

### Detection and Organization

1. On-call verifies the alert is still firing and sees rapid error budget burn.
2. Incident is declared SEV-2 because a core journey is degraded across multiple tenants.
3. IC assigns Technical Lead, Communications Lead, and Scribe.
4. Release owner supplies release ID, rollout time, and config diff.
5. Payment owner is engaged due to abnormal downstream attempt volume.

### Triage and Hypotheses

| Observation | Hypothesis | Check |
| --- | --- | --- |
| p99 spiked right after release | New code path increased call count | Compare traces before/after release |
| Payment requests tripled | Retries/chained calls multiplied | Compare original bookings vs payment attempts |
| Pool wait rose | Requests hold connections too long | Inspect thread/connection pools and dependency latency |
| Operations have unknown status | Responses time out after side effects | Query idempotency/operation status |

### Containment

- Pause rollout so no new instances run the faulty version.
- Route traffic back to the prior version if schema/API are compatible.
- Preserve idempotency records; do not retry payments with new keys.
- Cap concurrency to Payment and engage circuit breakers per policy.
- Shed secondary features on the booking path.

### Recovery

After rollback, the team checks p99, error rate, payment attempts/request ratio, pool wait, and database health. Operations with unknown payment outcomes are reconciled via provider references/idempotency keys. Traffic re-opens via canary; reconciliation workers run with bounded concurrency.

### Closing the Incident

Transition to Resolved only when the booking flow stabilizes, duplicate payments stop, pending operations have owners/statuses, queues stop growing, and customer updates are sent per policy. The postmortem identifies retry policy and missing timeout-after-commit testing as contributing factors; action items include fault-injection tests, an attempts-to-original ratio alert, and a retry budget for Payment.

## 30. Case Study: Credentials Exposed in CI/CD Logs

An engineer discovers pipeline logs containing production workload credentials. There is no evidence the credentials were used, but the logs are readable by many users and retained in an artifact store.

### Coordination

- Trigger a security incident, preserve logs/artifacts, and restrict access permissions.
- Assign a security incident lead; notify IAM, platform, and privacy/legal per policy.
- Inventory potentially exposed credentials, accounts, resources, and pipelines.

### Containment

1. Identify still-valid credentials and their current permissions.
2. Prepare replacement credentials/rotations across dependencies.
3. Revoke old credentials once consumers are ready or via emergency rotation strategy.
4. Block unnecessary role access to artifacts/logs.
5. Inspect audit trails for anomalous credential usage.

### Recovery and Evidence

- Update the pipeline to use a secret manager and log masking.
- Delete/rotate active secret copies while preserving evidence per security guidance.
- Check log copies, caches, artifact mirrors, and retention.
- Review log read permissions and secret scanning.
- Do not declare a breach occurred without evidence; equally, do not assert no breach occurred solely because no alert fired.

### Lessons Learned

Runbooks must handle both credential rotation and evidence preservation. Immediate revocation may be necessary to reduce risk, but logs/artifacts must be protected for investigation; external communications must follow authorized personnel.

## 31. Incident Management Quality Metrics

Metrics must be interpreted alongside incident impact and complexity:

| Metric | Meaning | Notes |
| --- | --- | --- |
| MTTD | Mean Time to Detect | Time from impact start to detection |
| Time to acknowledge | From alert/page to responder acknowledgment | Measures paging/on-call health |
| Time to declare | From detection to incident declaration | Reflects triage and severity policy |
| Time to mitigate | Until impact is reduced | Distinct from time to root-cause identification |
| MTTR | Mean Time to Restore/Repair depending on definition | Must standardize start/end timestamps |
| Reopen/regression rate | Incidents reopened or issues recurring | Indicates fragile recovery |
| Runbook success rate | Ratio of procedures achieving expected results | Track deviations |
| Alert precision/noise | Ratio of actionable alerts vs false positives | Do not optimize by muting critical alerts |
| Postmortem action completion | Action items completed on schedule | Tracks improvement quality |
| Repeat incident rate | Incidents recurring with same cause/impact | Requires good taxonomy grouping |

### Do Not Use MTTR as an Individual KPI

MTTR is shaped by architecture, dependencies, incident severity, and mitigation choices. Use metrics to find bottlenecks and improve systems—never incentivize closing incidents prematurely or hiding impact duration.

### Measuring Runbook Maturity

- **Coverage:** do critical failure modes have runbooks?
- **Freshness:** are owners and review dates current?
- **Executability:** can an on-call responder other than the author run it?
- **Safety:** are pre-checks, stop conditions, and rollbacks included?
- **Evidence:** do procedures capture outputs/approvals?
- **Tested:** has the runbook been verified in a game day or restore drill?

## 32. Managing Runbooks as Code

Runbooks evolve alongside architecture, permissions, service names, and dashboards. Store them in version control with a review process:

- Assign owners and reviewers from relevant services/domains.
- Evaluate runbook impact for every significant infrastructure change.
- Use pull requests, versioning, and changelogs.
- Verify dashboard links, contacts, and commands before merging.
- Never store secrets or personal access details.
- Use linting/templates to enforce required sections.
- Record the runbook version in incident records when executed.
- Review after every incident and on a recurring schedule.

### Automated Runbook Testing

Some checks can be automated:

- No broken links.
- Commands/manifests contain no secret patterns.
- Resource names/regions use valid placeholders.
- Scripts support dry-run or confirmation for dangerous actions.
- Alert/runbook URLs resolve.
- Policy-as-code and configuration validation pass.

Never automatically run production commands during a lint step. Structural document checks are distinct from operational execution.

## 33. Incident Process Review Checklist

- Are incident severity levels and triggers defined by impact?
- Are IC, Technical Lead, Scribe, Communications Lead, and escalation backups clear?
- Do runbooks specify owner, trigger, preconditions, safety, actions, verification, and rollback?
- Do alerts include SLI/SLO, context, and runbook links?
- Is there a triage checklist and correlation method for deploys/provider events?
- Are timelines/evidence stored in an access-controlled system?
- Does containment include stop conditions and blast-radius estimates?
- Do database, deployment, region, security, queue, and data-corruption scenarios have playbooks?
- Does recovery verify correctness, backlogs, capacity, and security?
- Do customer/stakeholder communications have templates and approval workflows?
- Do handovers capture state, decisions, owners, and next actions?
- Does incident closure distinguish Resolved from Closed?
- Do blameless postmortems produce action items with owners/deadlines?
- Are emergency changes/break-glass audited and synced back to IaC?
- Are backup/DR tested via restore drills against RPO/RTO?
- Do automation/self-healing have guardrails and kill switches?
- Do chaos/game days define hypotheses, scope, stop conditions, and debriefs?
- Are runbooks version-controlled, reviewed, and checked for freshness?

## 34. Well-Architected Review

| Pillar | Question | Evidence |
| --- | --- | --- |
| **Reliability** | Are incidents detected, contained, and recovered within RTO/SLO? | Alerts, runbooks, DR drills, SLIs, failover tests |
| **Security** | Are security incidents, credential compromises, and evidence handled safely? | IAM, break-glass, audits, evidence handling, escalation |
| **Performance Efficiency** | Does the system sustain performance and graceful degradation under overload? | Capacity plan, load shedding, pool/queue metrics |
| **Cost Optimization** | Do automation, alerting, and recovery reduce repetitive work without causing resource waste? | Cost-aware runbooks, right-sizing, retry/queue metrics |
| **Operational Excellence** | Are roles, processes, runbooks, postmortems, and improvements clear? | Incident timelines, ownership, game days, action completion |
| **Sustainability** | Are resources and batch workloads throttled/coordinated during incidents to avoid waste? | Graceful degradation, bounded retries, controlled recovery |

Effective incident response combines **early detection, clear command, safe containment, evidence-backed investigation, verified recovery, and post-incident learning**. Runbooks must be concrete enough for an on-call responder to execute, while clearly stating when to stop and call specialists. Reliability does not come from never failing; it comes from limiting blast radius, recovering under control, and learning so similar incidents are less likely to recur.
