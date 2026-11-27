# Writing Runbooks, Incident Timelines, and Preventive Actions

## 1. Why do we need runbooks and incident timelines?

When compute workloads suffer an incident, operations teams often work under tight time pressure with incomplete information. A VM failing to boot, containers restarting continuously, function timeouts, stalled GPU jobs, or storage/network bottlenecks can all degrade service. If each responder acts on ad-hoc personal experience, the team easily skips critical steps, runs risky commands, or fails to record what happened for later investigation.

A **runbook** is an operational guide for a specific scenario. It describes recognition signals, impact scope, safety checks, procedural steps, stop conditions, recovery options, and how to confirm service stability. A good runbook enables on-call engineers to act consistently even if they did not build the system.

An **incident timeline** is a chronological record of events and decisions during an incident: when it started, when it was detected, when impact was confirmed, mitigation actions, recovery time, and follow-up changes. The timeline provides data to understand how the incident unfolded, evaluate response speed, and pinpoint gaps in monitoring or process.

Once the service recovers, the team must identify causes, contributing factors, and preventive actions. The goal is to lower the likelihood of similar incidents, shorten detection and recovery times, and reduce blast radius. This must rest on evidence and clear ownership rather than ending with a purely descriptive report.

In the **CLOUD_CORE_SERVICES_COMPUTE** module, incidents can arise across VMs, containers, serverless, CPU, memory, GPUs, storage, networking, IAM, or the cloud platform itself. This lesson shows how to turn troubleshooting experience into repeatable, continuously improving processes.

After this lesson, learners will be able to:

- Distinguish incidents, alerts, symptoms, causes, mitigations, and recovery.
- Design runbooks with defined scope, preconditions, checks, safe actions, and exit criteria.
- Build timelines with timestamps, evidence sources, decisions, and actors.
- Coordinate incident response, assign roles, and communicate status.
- Diagnose compute incidents layer by layer from application down to cloud infrastructure.
- Write post-incident reviews and convert findings into preventive actions with owners, due dates, and verification criteria.

## 2. Core concepts to align on

### 2.1. Alerts, events, and incidents

- **Alert:** a notification triggered when a monitoring condition occurs, such as high CPU throttling or a nearly full filesystem.
- **Event:** a timestamped occurrence, such as a Pod eviction, instance reboot, deployment start, or a cloud API quota rejection.
- **Incident:** a situation causing or risking significant impact to services, users, data, security, or business operations that requires coordinated response.

An alert is not automatically an incident. CPU can run high during a batch job without hurting SLOs. Conversely, an incident may trigger no alert if metrics are uncollected or thresholds are misconfigured. Evaluate service impact rather than counting alerts alone.

### 2.2. Symptoms, triggers, and root causes

A **symptom** is an observable manifestation, such as request timeouts, Pod restarts, or growing queue backlogs. A **trigger** is the immediate event that initiated the incident, such as deploying a new release or hitting a quota. A **root cause** is the underlying systemic condition enabling the failure state, such as lacking memory-growth controls or missing capacity headroom.

An incident can have multiple contributing factors. For example, a deployment raises memory usage; container limits are too tight so Pods get `OOMKilled`; replica counts are too low and the autoscaler cannot scale due to quota; meanwhile alerts only track cluster-wide average memory. Patching only the application version eases the symptom yet leaves the quota and monitoring gaps unresolved.

### 2.3. Mitigation, recovery, and resolution

- **Mitigation:** an action that immediately reduces impact, such as shifting traffic, lowering concurrency, disabling a feature, or scaling capacity.
- **Recovery:** returning services and data to a verified operational state.
- **Resolution:** declaring the incident closed per agreed criteria after confirming core functions and monitoring through a stabilization window.

Mitigation does not necessarily fix the root cause. For instance, adding instances may restore throughput temporarily, yet if a retry storm persists, the incident can recur. Timelines and post-incident reviews must clearly separate impact-mitigation time from root-cause remediation time.

### 2.4. Runbooks, playbooks, and post-incident reviews

Runbooks typically focus on technical procedures for a specific scenario. Playbooks cover broader coordination workflows, including roles, communications, decision gates, and multiple linked runbooks. A post-incident review (PIR) or postmortem documents impact, timeline, causes, and improvement actions after an incident.

These artifacts should link together. Alerts link to runbooks; runbooks point to dashboards, log queries, and contacts; incident records store timelines; and PIRs reference incident records to generate action items.

## 3. Compute incident response process

### 3.1. Detection and triage

Upon receiving an alert or user report, verify:

1. Which service, workload, environment, and region are affected?
2. Is the impact a total outage, performance degradation, or an imminent risk?
3. How many users, requests, jobs, or tenants are affected?
4. When did the incident start, and how long has it lasted?
5. Were there recent changes such as deployments, resizes, patches, IAM policies, or network edits?
6. Is data at risk of loss, corruption, or inconsistency?
7. Are there signs of a security incident or unauthorized access requiring separate escalation?

Do not wait for complete information before declaring an incident if severe impact is already clear. Open the incident with initial details and update as fuller evidence arrives.

### 3.2. Severity classification

Severity should reflect user impact and degradation velocity, not merely which resource type failed.

| Level | Reference condition | Coordination approach |
|---|---|---|
| SEV-1 / Critical | Core service down, data loss, or widespread impact; severe SLO breach | Activate incident command, primary and backup on-call, update leadership/customers per policy |
| SEV-2 / High | Major feature significantly degraded, spreading errors, or headroom nearly exhausted | Coordinate relevant teams, post periodic status updates, prioritize mitigation |
| SEV-3 / Medium | Limited impact, workaround available, no major disruption | Assign owner to resolve, track and update per internal SLA |
| SEV-4 / Low | Minor fault, predictive warning, or no direct user impact | Create ticket/runbook improvement, handle in planned work |

Exact severity names and thresholds depend on the organization. Define clearly who has authority to upgrade/downgrade severity and the criteria for closing an incident.

### 3.3. Establish coordination roles

During major incidents, assigning roles keeps engineers focused while preserving context and decisions:

- **Incident Commander (IC):** overall coordination, task prioritization, escalation decisions, and status confirmation.
- **Technical Lead:** leads technical diagnosis, proposes mitigations, and governs changes.
- **Operations/Responders:** execute checks, operational commands, and recovery steps per runbook.
- **Communications Lead:** updates stakeholders, users, or support teams on an agreed cadence.
- **Scribe:** records timeline, decisions, evidence, actors, and outcomes.
- **Service Owner:** validates business behavior and workload recovery criteria.

In minor incidents, one person may wear multiple hats. For SEV-1/2, separate the scribe recording the timeline from responders executing changes to avoid losing context.

### 3.4. Contain, mitigate, and recover

The usual priority order is protecting users and data first, stabilizing the service second, and conducting deep investigation afterward. Mitigation actions may include:

- Shifting traffic to healthy regions or backends.
- Scaling capacity when quotas and dependencies allow.
- Lowering concurrency or enabling backpressure to prevent cascading overload.
- Rolling back a deployment or reverting to a prior image/runtime.
- Cordoning/draining unhealthy nodes and rescheduling workloads.
- Failing over databases per runbook while verifying replication and consistency.
- Pausing non-essential batch jobs or consumers.
- Isolating compromised resources per security incident procedures.

Never perform destructive actions—such as deleting volumes, formatting disks, force-deleting stateful workloads, or making broad IAM edits—without understanding the impact and securing required approvals. If data risks corruption, prioritize halting write streams per data-preservation procedures.

### 3.5. Verify recovery

A service is recovered only when both technical and business checks pass. Verify health endpoints, error rates, latency, throughput, queue backlogs, database replication, sample data, and core user workflows. Monitor throughout an adequate observation period to confirm errors do not return as load builds.

Record mitigation time, core-functionality restoration time, and incident-closure time separately. These three timestamps can differ substantially.

## 4. Designing actionable runbooks

### 4.1. Minimum structure

A runbook should contain:

1. **Title and purpose:** which scenario it addresses and the desired outcome.
2. **Scope:** affected services, environments, regions, compute types, and components.
3. **Owner and escalation:** responsible team, on-call rotation, backup contacts.
4. **Trigger:** alerts, symptoms, or events that invoke the runbook.
5. **Severity guidance:** conditions for escalating severity.
6. **Preconditions:** required access, backups, replicas, capacity, and approvals.
7. **Diagnostic steps:** read-only checks or dashboards ordered from lowest risk.
8. **Mitigation:** impact-reduction actions with authorization criteria.
9. **Recovery/rollback:** restoration steps, stop conditions, and fallbacks.
10. **Validation:** technical checks, business checks, and observation period.
11. **Evidence:** logs, metrics, traces, events, and where to file incident records.
12. **Follow-up:** related documentation and post-incident actions.

### 4.2. Write explicit verification steps

Each step should state its goal, exact action, expected outcome, and what to do if results deviate. Avoid vague instructions like "check server" or "restart if needed," which omit what to inspect and who holds decision authority.

Examples:

| Component | Vague guidance | Actionable guidance |
|---|---|---|
| Disk | Check disk | Identify affected mount point, free percentage and bytes, inodes, and 1-hour growth rate; verify owner and retention before cleanup |
| Memory | Check RAM | Identify processes/containers with rising RSS or working set, check OOM events and memory limits; correlate timestamps with deployments |
| Kubernetes | Check pod | Capture namespace, Pod, node, restart count, last termination reason, and events; check PDBs before draining |
| Network | Check connection | Verify source/destination, port, DNS resolution, routes, security policies, packet loss, and error timestamps |
| Cloud quota | Increase quota | Identify quota name, account/region, current usage, forecasted demand, and approval SLA; prepare fallback if not yet approved |

### 4.3. Distinguish read-only commands from state-changing commands

Runbooks should clearly distinguish read-only diagnostic commands from commands that alter system state. For example, `df -h`, `free -m`, `systemctl status`, and `kubectl get` are typically observational; `systemctl restart`, `kubectl delete`, firewall edits, or database failovers can cause disruption.

For state-changing commands, specify:

- Prerequisites and required permissions.
- Blast radius, resource IDs, and environment.
- Approver or verifier if required.
- Expected outcome and wait timeout.
- Stop or rollback conditions.
- Post-action verification steps.

Never embed tokens, passwords, private keys, or sensitive data in runbooks. Use a secret manager or temporary credential issuance mechanisms.

### 4.4. Runbooks must be tested

An untested runbook in an equivalent environment is merely an assumption. Test periodically via tabletop exercises, staging drills, or game days. Log unclear steps, commands broken by version drift, missing permissions, retired dashboards, and actual execution times to keep documentation accurate.

Every runbook needs a version, owner, last-reviewed date, and next-review schedule. Whenever architecture, alerts, resource names, or access permissions change, update the runbook in the same change.

## 5. Layered compute troubleshooting workflow

### 5.1. Start from impact scope

Before diving into a single machine, establish whether the fault hits one instance, one node, one zone, one region, or the entire service. Compare failing resources against healthy peers of the same type. If multiple unrelated workloads fail together at the same time, suspect shared dependencies such as networking, DNS, IAM, storage services, or the cloud control plane.

Record recent changes: deployments, images, kernel patches, drivers, IAM policies, security groups, routes, volume resizes, autoscaling configs, or quotas. A change near the incident start is a clue, not automatic proof of causality.

### 5.2. VMs and operating systems

Diagnostic questions:

- Is the instance `running`, or stuck `pending`, `stopping`, or `impaired`?
- Do console/system logs show boot, filesystem, kernel panic, or driver errors?
- Are CPU, memory, swap, disk I/O, or network saturated?
- Is the service active, listening on the right port, and bound to the right interface?
- Are DNS, routes, security groups/firewalls, and IAM roles working?
- Were there recent image, package, kernel, or metadata changes?

Read-only Linux commands:

```bash
uptime
free -h
df -h
df -i
ps aux --sort=-%mem | head
ps aux --sort=-%cpu | head
systemctl --failed
systemctl status app.service
journalctl -u app.service --since "30 minutes ago"
ss -s
ip route
```

Run commands with appropriate privileges; exact flags may vary across distributions. Avoid pasting outputs containing secrets or personal data into public tickets. If a reboot is necessary, first check workloads, volumes, replicas, and recovery options.

### 5.3. Containers and Kubernetes

Check Pod status, node status, events, restart counts, termination reasons, image pulls, readiness/liveness probes, resource requests/limits, PVCs, and network policies.

```bash
kubectl get pods -A -o wide
kubectl get nodes
kubectl get events -A --sort-by=.lastTimestamp
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
kubectl top pods -A
kubectl top nodes
```

`get`, `describe`, `logs`, and `top` are primarily diagnostic. `kubectl top` requires Metrics Server or a compatible metrics pipeline. When Pods restart, `--previous` retrieves the prior container instance's logs if still retained by the runtime. Never delete Pods or drain nodes before checking PDBs, local data, and healthy replica counts.

### 5.4. Serverless

For functions or managed compute, inspect:

- Invocation counts, error counts, timeouts, and duration percentiles.
- Throttling, concurrency limits, and cold starts.
- Runtime version, package/image digest, and deployment timestamp.
- IAM permissions, secret access, and KMS decrypt errors.
- VPC/subnet, endpoints, DNS, and downstream dependency connectivity.
- Retry counts, event age, dead-letter queues, and duplicate handling.

If errors occur only on cold starts, inspect initialization duration, boot-time dependency loading, and network setup. If errors scale with concurrency, check quotas, downstream connection pools, and database limits. Before rolling back a function version, verify processed data or events remain compatible with the older version.

### 5.5. Storage

Distinguish full volumes, full filesystems, exhausted inodes, IOPS/throughput ceilings, and rising latency. Check both cloud volume metrics and guest OS metrics. A volume may be resized in the control plane without the filesystem being extended; an application may stall on I/O latency despite ample free space.

Linux diagnostic commands include `df -h`, `df -i`, `lsblk`, `findmnt`, and `iostat -xz 1`. Never format or run filesystem repairs before checking mount state, backups, and recovery guides. For databases, prioritize engine-native consistent backup/restore procedures.

### 5.6. Networking and service dependencies

Check DNS, routes, security groups, firewalls, network ACLs, NAT, load balancer health, packet drops, retransmissions, and connection pools. Determine whether failures occur at DNS resolution, TCP connect, TLS handshake, authentication, or request timeout; each layer requires a distinct fix.

Common diagnostic commands:

```bash
getent hosts service.internal
ip route
ss -tan
curl -v --connect-timeout 3 https://service.internal/health
```

Do not run load tests or broad port scans against production without approval. `curl -v` can expose headers or sensitive tokens; redact output before sharing logs.

### 5.7. GPUs and distributed workloads

For GPU jobs, check scheduler state, node health, GPU utilization, VRAM, ECC errors, driver/runtime versions, thermal/power limits, and framework logs. Across multiple GPUs or nodes, inspect collective communication, network fabric, RDMA, and per-rank status.

A job may appear GPU-idle because it is waiting on storage, data loaders, or all-reduce barriers. Do not reboot nodes before confirming whether the job has checkpoints and restart capability. For severe driver or ECC failures, cordon/isolate the node per procedure and preserve logs before replacing it.

## 6. Building an incident timeline

### 6.1. Key milestones to record

A timeline should capture at minimum:

- **T0 – Start/first known symptom:** earliest time backed by evidence showing the incident began.
- **Detected:** when monitoring or users noticed the issue.
- **Acknowledged:** when on-call confirmed receipt of the alert.
- **Incident declared:** when the incident was formally opened and severity assigned.
- **Scope confirmed:** when blast radius and user impact were established.
- **Mitigation started/completed:** when impact-reduction actions began and finished.
- **Service restored:** when core functionality resumed operating.
- **Monitoring stable:** when the observation period ended with confirmed stability.
- **Incident resolved/closed:** when the incident was closed.
- **Follow-up created:** when post-incident action items were logged.

Not every incident yields an exact T0. If only a time range is known, record that range and its supporting evidence. Never fabricate an exact timestamp when data does not support it.

### 6.2. Standardize timestamps

Store timestamps in ISO 8601 format and standardize on UTC in incident records, e.g., `2026-11-22T14:20:00Z`. If users or systems report in other timezones, record the offset explicitly and convert only for presentation. Keep NTP/chrony synchronized on hosts and check for clock skew across systems.

Timestamps across alerts, logs, traces, and tickets can diverge due to ingestion lag, buffering, or clock drift. Record each timestamp's source and distinguish event occurrence time from system ingestion time.

### 6.3. Record events and decisions

Each timeline row should include:

| Field | Content |
|---|---|
| Timestamp | Exact time and timezone/UTC |
| Actor | Person, automation, or service taking action |
| Event/decision | What happened or what decision was made |
| Evidence | Alert ID, log query, dashboard, trace, command output, or ticket |
| Impact | Observed impact at that moment |
| Result | Outcome after the action and next step |

Record failed actions and decisions *not* to act as well. For example, noting that the team chose not to reboot because the database lacked a healthy replica is vital context explaining why another path was taken.

### 6.4. Example timeline

Illustrative example of a Kubernetes API incident caused by memory pressure after a deployment:

| Time UTC | Event | Evidence/result |
|---|---|---|
| 09:02 | Started rollout of new release | Deployment event and image digest |
| 09:08 | Restart count rose on new Pod group | Pod events, container termination reason |
| 09:10 | Error rate alert fired | SLO dashboard and alert ID |
| 09:13 | On-call acknowledged, declared SEV-2 incident | Incident record |
| 09:17 | Confirmed new Pods OOMKilled, affecting ~20% of requests | Pod status, memory working set, request metrics |
| 09:21 | Decided to halt rollout and roll back image | Change record and deployment event |
| 09:27 | Old Pods healthy, error rate began dropping | Readiness and error rate |
| 09:34 | Error rate returned to baseline, latency stabilized | SLO dashboard |
| 10:00 | Observation period ended, incident closed | Service owner confirmed core workflows |
| 14:00 | PIR confirmed insufficient memory limit and unrepresentative load tests | Investigation report and action items |

Timestamps in this table are illustrative placeholders showing structure. For real incidents, replace them with verified timestamps and evidence.

### 6.5. Separate facts, hypotheses, and conclusions

Timelines should separate verified facts from hypotheses. For example:

- Fact: "Pod `api-7c...` was OOMKilled at 09:08 per Kubernetes events."
- Hypothesis: "The memory limit may be lower than the new release's demand."
- Post-investigation conclusion: "The new release increased peak working set by 35%; limits were not updated and load tests did not cover that traffic level."

Recording an unverified hypothesis as fact prematurely biases the investigation and can produce the wrong action items.

## 7. Root cause investigation and post-incident review

### 7.1. Preserve evidence before making changes

Whenever feasible, save short-lived data prior to restarting or replacing resources:

- Alerts and metrics at the time of the incident.
- Application, OS, container runtime, and cloud control-plane logs.
- Representative traces or request IDs.
- Pod/instance events, deployment history, and image digests.
- Process lists, memory maps, thread dumps, or heap dumps where appropriate.
- Network connections, routes, and dependency health states.
- Database replication status, queue backlogs, and checkpoints.
- Change history for IAM, security groups, quotas, and autoscaling.

Collect only necessary data, redact secrets and personal data, and restrict access and retention. Some dumps can contain tokens, user data, or sensitive payloads; store them in controlled locations per policy.

### 7.2. Construct the causal chain

Ask in sequence:

1. Which conditions changed before symptoms appeared?
2. Which resources or dependencies did that change affect?
3. Why did safeguards—such as limits, retries, autoscaling, replicas, or circuit breakers—fail to contain the impact?
4. Why did monitoring fail to detect it earlier or pinpoint the exact component?
5. Why did operational procedures fail to shorten recovery time?

The goal is an evidence-backed causal chain, rather than stopping at "server overloaded" or "operator mistake."

### 7.3. Five Whys and fault trees

Five Whys drills down from a symptom by asking "why" repeatedly. You do not have to force exactly five questions; stop once you reach an actionable, verifiable root cause. Fault trees help when causes branch—for example, request timeouts can stem from CPU, storage, network, DNS, or downstream services.

Do not force a single root cause when evidence shows multiple contributing factors. Incidents often emerge from interactions among a change, a resource cap, missing redundancy, and a detection gap.

### 7.4. Blameless reviews

Post-incident reviews should focus on system conditions and decisions made given the information available at the time. Avoid blaming individuals or writing comments like "operations was careless." If a manual step caused an error, examine why that step lacked guardrails, validation, automation, or clear documentation.

Blameless does not mean unaccountable. Owners still take action items with due dates, track progress, and verify outcomes. Accountability focuses on improving the system and honoring commitments.

### 7.5. Post-incident review structure

A PIR report may include:

1. **Summary:** a concise paragraph describing what happened and current status.
2. **Impact:** affected services, users, transactions, data, regions, and duration.
3. **Severity and SLO:** severity level and error budget or SLO impact.
4. **Timeline:** key milestones, decisions, and evidence.
5. **Detection:** which alerts fired, which were missing or late.
6. **Root cause and contributing factors:** causal chain and supporting evidence.
7. **Mitigation and recovery:** what reduced impact and what restored full service.
8. **What went well:** safeguards and practices that worked as intended.
9. **What made response harder:** gaps in documentation, permissions, telemetry, capacity, or coordination.
10. **Corrective/preventive actions:** actions with owner, priority, due date, and success criteria.

## 8. Preventive actions

### 8.1. Categorize actions

Post-incident actions should be categorized by intent:

- **Corrective action:** fixes the defect that caused the incident, e.g., raising a memory limit after sizing and verification tests.
- **Preventive action:** reduces the probability of recurrence, e.g., adding load tests and pre-deploy policy checks on resource limits.
- **Detective action:** catches issues earlier, e.g., alerting on OOM events and sustained memory growth.
- **Mitigative action:** shrinks blast radius when failures occur, e.g., adding replicas, circuit breakers, or automated failover.
- **Process/documentation action:** improves runbooks, permissions, approvals, training, or drills.

Not every action requires writing code. It may involve requesting quota increases, adjusting maintenance schedules, tuning retention, improving alert routing, or training on-call teams.

### 8.2. Write measurable action items

An action item should specify:

| Field | Requirement |
|---|---|
| Action | Specific work description; avoid vague goals like "improve monitoring" |
| Owner | A single responsible individual or team |
| Priority | Priority level based on risk and impact |
| Due date | Target completion date or checkpoint |
| Success criteria | Measurable or verifiable outcome |
| Verification | Test, dashboard, drill, or review confirming completion |
| Status | Open, in progress, blocked, or done |

Good example: "Add per-namespace OOMKilled rate alert routed to `platform-api` on-call; due by date X; test with a synthetic failing Pod in staging and confirm alert firing/resolved."

Insufficient example: "Monitor memory better." This lacks metrics, an owner, a due date, and verification criteria.

### 8.3. Prioritize by risk

Prioritize actions based on severity, likelihood of recurrence, number of exposed workloads, risk reduction, and implementation cost. A small change such as adding a quota alert can cut risk across many services; a multi-month refactor may not address the most immediate exposure.

Priority tiers might look like:

- **P0:** immediately mitigate critical risk or an actively exploited gap.
- **P1:** address a primary root cause or gap capable of causing a major incident.
- **P2:** strengthen detection, self-healing, or reduce time to resolve.
- **P3:** long-term improvements, documentation, and operational polish.

Priority labels and SLAs should follow organizational policy. Never leave P0/P1 action items without an owner or check-in milestone.

### 8.4. Measure effectiveness after improvements

Do not evaluate actions solely by "closed" ticket counts. Verify whether actual risk decreased:

- Has the rate of similar incidents dropped?
- Has MTTD (Mean Time to Detect) shortened?
- Has MTTA (Mean Time to Acknowledge) improved?
- Has MTTR (Mean Time to Restore/Recover) decreased?
- Have rollbacks, OOMs, quota rejections, or failed deployments changed?
- Did runbooks execute cleanly during drills?
- Do new alerts route to the right owner with low false-positive noise?

MTTR definitions vary across organizations. Explicitly state the start and end boundaries used—such as from detection to service restored—so comparisons remain consistent.

## 9. Example runbook: VM fails to serve requests

### 9.1. Goal and trigger conditions

**Goal:** restore an unhealthy backend VM behind a load balancer without disrupting the broader service.

**Trigger:** repeated health check failures, rising error rates, or a backend receiving no requests. Owner is the service operations team; escalate to the cloud/network team if multiple VMs in the same zone are affected.

### 9.2. Initial checks

1. Confirm the load balancer reports the backend unhealthy and record the timestamp.
2. Check whether remaining backends are healthy and have spare capacity.
3. Check instance state, system logs, and cloud maintenance events.
4. Check VM CPU, memory, disk, network, and processes.
5. Check service status, listening ports, and application logs.
6. Check DNS, routes, security groups/firewalls, and dependencies.
7. Correlate recent changes: deployments, patches, images, IAM, or network rules.

### 9.3. Mitigation

If only one backend is failing and remaining backends have sufficient capacity, keep the unhealthy backend out of the target group, gather required logs, and restart the service per the application runbook once the cause is understood. If failures started after a deployment with supporting evidence, consider rolling back the release. If multiple backends fail together, check shared dependencies before replacing individual VMs.

Never reboot the entire fleet. Never delete or replace stateful VMs before verifying where volumes and data reside.

### 9.4. Recovery and closure criteria

Wait for the service to become active, listen on its port, and pass its health endpoint. Return backends to the pool one by one while monitoring error rates, p95/p99 latency, CPU, memory, and request success. Confirm business workflows via smoke tests. Close the incident once backends stay stable across the observation period and the owner signs off.

### 9.5. Post-incident actions

If the cause was a superficial health check, add a proper readiness endpoint. If capacity fell short, adjust autoscaling and quotas. If a patch caused the failure, add canary testing for images/OS updates. Every action needs an owner and verification criteria.

## 10. Example runbook: Pod continuously OOMKilled

### 10.1. Goal and triggers

**Goal:** recover a Kubernetes workload experiencing `OOMKilled` and determine why memory exceeded its limit.

**Trigger:** rising restart count, Pod status showing `OOMKilled`, memory working set nearing its limit, or rising application latency/errors.

### 10.2. Checks

1. Capture namespace, deployment, Pod, node, and restart timestamps.
2. Run `kubectl describe pod` to inspect last termination state and events.
3. Check `kubectl logs --previous` if logs from the prior container remain available.
4. Compare memory limits/requests against actual RSS or working set.
5. Inspect application heap, GC, caches, request sizes, and concurrency.
6. Correlate deployments, traffic, and dependencies at the time memory climbed.
7. Check node memory pressure and neighboring Pods on the same node.

### 10.3. Mitigation

If the limit is clearly below legitimate demand and the node has headroom, raise the limit through an approved change process. If a new release caused abnormal memory growth, halt rollout or roll back. If a memory leak is suspected, reduce traffic/concurrency and capture appropriate profiles/dumps before restarting when feasible.

Never raise limits indefinitely. Check aggregate requests/limits and node capacity so you do not push the node into memory pressure. Never drain a node without evaluating PDBs and co-located workloads.

### 10.4. Recovery and prevention

Wait for Pods to stabilize, confirm restart counts stop rising, verify memory stops climbing abnormally, and verify latency and error rates return to baseline. Follow-up actions may include memory profiling, peak-load testing, namespace-scoped OOM alerts, resource request/limit policies, and capacity reviews.

## 11. Example runbook: Serverless timeout or throttling

### 11.1. Checks

1. Identify the function/version/alias and when errors began.
2. Inspect invocations, p95/p99 duration, timeouts, errors, and throttle counts.
3. Check concurrency limits, account quotas, and downstream rate limits.
4. Check cold starts, runtime version, package/image, and dependency initialization.
5. Check IAM, secrets, KMS, VPC endpoints, DNS, and target service connectivity.
6. Check event age, retries, duplicates, and dead-letter queues.

### 11.2. Mitigation and recovery

If a new version causes timeouts, shift the alias/traffic back to the prior version after verifying compatibility. If downstream systems are overloaded, reduce concurrency or apply backpressure; raising concurrency can worsen the incident. If a quota is hit, identify the exact limit and either request a quota increase or distribute workload.

After mitigation, confirm successful invocations, durations within SLO, falling queue age, and zero dropped or duplicate-corrupted events. Preventive actions include idempotency keys, dependency-aligned timeouts, concurrency guardrails, cold-start testing, and quota alerts.

## 12. Example timeline and post-storage-incident actions

A worker writes output files to a volume. After a batch run, the filesystem fills up and the worker starts failing.

| Time UTC | Event | Evidence |
|---|---|---|
| 02:00 | Batch started; file creation rate exceeded baseline | Scheduler event and application metrics |
| 02:25 | Mount point utilization exceeded 90% | Node exporter metric |
| 02:31 | Warning alert sent to owner | Alert manager event |
| 02:46 | Worker hit write error `No space left on device` | Application logs |
| 02:50 | On-call opened incident and paused new batches | Incident record and scheduler event |
| 03:05 | Identified temp files not cleaned after each batch | Disk usage and file inventory |
| 03:18 | Cleaned temp files per confirmed retention; worker recovered | Runbook action and application health |
| 03:40 | Batch resumed; queue/backlog stabilized | Job status and queue metrics |
| Next day | PIR confirmed missing lifecycle cleanup and late warning alert | PIR and action tracker |

Preventive actions:

| Action | Owner | Priority | Completion criteria |
|---|---|---|---|
| Add safe cleanup after batch completion | Application team | P1 | Tests verify active files are untouched and disk usage returns to baseline |
| Alert on time-to-full based on growth rate | SRE | P1 | Alert fires in staging with enough lead time to remediate |
| Enforce retention and size caps for temp files | Workload owner | P2 | Policy deployed and verified via dashboard |
| Add disk capacity pre-check before accepting batches | Platform team | P2 | Scheduler refuses jobs when headroom falls below safe threshold |

## 13. Runbook and incident record templates

### 13.1. Runbook template

```markdown
# Runbook: <Scenario Name>

## Goal
<Desired outcome>

## Scope and owner
- Service/environment/region:
- Owner/on-call:
- Escalation:

## Trigger and severity
- Alert/event:
- Incident declaration criteria:

## Preconditions
- Access permissions:
- Backup/checkpoint/replicas:
- Capacity and dependencies:
- Required approvals:

## Diagnosis
1. <Check, purpose, expected result>
2. <Next check>

## Mitigation
1. <Action, scope, execution condition>
2. <Expected outcome and stop condition>

## Recovery / rollback
1. <Recovery step>
2. <Rollback criteria>

## Validation
- Health/SLO:
- Business check:
- Observation period:

## Evidence and links
- Dashboard/log/trace:
- Incident record:
- Change/ticket:

## Review
- Runbook owner:
- Last tested:
- Next review:
```

### 13.2. Incident timeline template

| Timestamp UTC | Actor | Event/decision | Evidence | Impact/result |
|---|---|---|---|---|
| YYYY-MM-DDThh:mm:ssZ | Monitoring | Alert fired | Alert ID/link | Initial scope |
| YYYY-MM-DDThh:mm:ssZ | On-call | Acknowledge/open incident | Incident ID | Severity and owner |
| YYYY-MM-DDThh:mm:ssZ | Technical lead | Confirm symptom/scope | Dashboard/log/trace | Impact level |
| YYYY-MM-DDThh:mm:ssZ | Responder | Mitigation started/completed | Command/change ID | Outcome |
| YYYY-MM-DDThh:mm:ssZ | Service owner | Confirm recovery | Smoke test/SLO | Service stable |
| YYYY-MM-DDThh:mm:ssZ | IC | Close incident | Incident record | Follow-up assigned |
```

### 13.3. Post-incident action tracker template

| ID | Specific action | Owner | Priority | Due date | Success criteria | Status |
|---|---|---|---|---|---|---|
| ACT-001 | <Work to be done> | <Team/individual> | P1 | YYYY-MM-DD | <How to measure/verify> | Open |
| ACT-002 | <Work to be done> | <Team/individual> | P2 | YYYY-MM-DD | <How to measure/verify> | Open |

Do not close an action item merely because a pull request or ticket was created. Close it only once the change is deployed, tested, and meets its success criteria.

## 14. Measuring incident response quality

### 14.1. MTTD, MTTA, and MTTR

- **MTTD (Mean Time to Detect):** average time from incident start until detection.
- **MTTA (Mean Time to Acknowledge):** time from alert/incident notification until someone acknowledges ownership.
- **MTTR:** may be defined as time to restore or time to repair; state exact start and end points clearly.

For example, if measuring MTTR from detection to service restored, apply that same definition across all incidents in reporting. Never compare figures built from differing definitions.

### 14.2. Additional metrics

- Percentage of incidents with up-to-date, tested runbooks.
- Percentage of action items completed on time.
- Repeat-incident rate from the same root cause.
- Ratio of actionable alerts versus false positives.
- Time from mitigation to full recovery.
- Incident counts attributed to quotas, capacity, patches, deployments, or configuration.
- Percentage of workloads with clear owners, SLOs, dashboards, and escalation paths.

Never use a single metric to judge individual performance or pressure teams into closing incidents prematurely. The goal is improving overall system reliability and response capability.

### 14.3. Drills and readiness checks

Run tabletop exercises for major scenarios, game days for selected failure modes, and scheduled runbook tests. Simulate nearly full disks, Pod OOMs, quota exhaustion, or function timeouts in safe environments. Evaluate whether on-call engineers locate the right dashboards, reach the right owners, and follow safe steps.

After drills, update runbooks, alerts, access permissions, and action trackers. A document is trustworthy only once the team has tested it and knows its limitations.

## 15. Common mistakes

- **Recording only detection time:** omitting start time, mitigation, recovery, and observation windows.
- **Using timestamps without timezones:** makes correlating logs across regions or teams error-prone.
- **Recording hypotheses as facts:** steers investigations and action items in the wrong direction.
- **Omitting decisions not to act:** loses context on risks that were evaluated.
- **Command-only runbooks:** omitting preconditions, blast radius, expected outputs, and stop conditions.
- **Restarting before collecting evidence:** wipes logs, process state, or forensic details.
- **Confusing mitigation with resolution:** closing incidents right as service returns even though failure can recur.
- **Checking only health endpoints:** misses business-logic, data, and backlog failures.
- **Action items without owners or due dates:** nobody is accountable for completion.
- **Vague action items:** impossible to verify whether risk was actually reduced.
- **Blaming individuals:** fails to uncover systemic conditions that made errors easy.
- **Skipping drills:** runbooks go stale or require permissions responders lack.
- **Closing PIRs before verifying actions:** reports exist while risk remains unaddressed.

## 16. Checklist

### When opening an incident

- [ ] Identified affected service, environment, region, owner, and blast radius.
- [ ] Classified severity based on impact and SLOs.
- [ ] Assigned IC, technical lead, responders, and scribe as needed.
- [ ] Created incident record and started a UTC timeline.
- [ ] Recorded symptoms, evidence, and recent changes.
- [ ] Protected data and checked for security incident indicators.

### During response

- [ ] Followed an appropriate runbook and verified preconditions.
- [ ] Separated read-only commands from state-changing operations.
- [ ] Recorded actors, decisions, timestamps, and outcomes.
- [ ] Selected the smallest mitigation that meets recovery goals.
- [ ] Defined stop conditions and rollbacks prior to risky changes.
- [ ] Updated stakeholders on the agreed cadence.

### During recovery and closure

- [ ] Verified health, SLOs, and core business workflows.
- [ ] Monitored across an adequate observation period.
- [ ] Recorded mitigation time, service restored time, and incident closed time.
- [ ] Archived evidence and protected sensitive data.
- [ ] Scheduled the post-incident review.

### Post-incident

- [ ] Identified root causes and contributing factors with evidence.
- [ ] Updated runbooks, dashboards, or alerts as needed.
- [ ] Assigned every action an owner, priority, due date, and success criteria.
- [ ] Tracked actions through deployment and verification.
- [ ] Rehearsed or re-tested preventive measures.
- [ ] Measured trends in MTTD, MTTA, MTTR, and repeat incidents.

## 17. Conclusion

Runbooks guide operations teams through safe, repeatable troubleshooting steps; incident timelines preserve events, decisions, and evidence over time; and post-incident reviews turn lessons learned into concrete improvements. Linking all three shortens detection and recovery times while reducing the likelihood of repeat incidents.

For compute workloads, diagnose from impact scope across the application, VM/container/serverless layer, CPU, memory, storage, networking, and dependent cloud services. Clearly separate verified facts from hypotheses; prioritize protecting users and data; and verify recovery using both technical and business indicators. Every post-incident action must carry an owner, deadline, and verification criteria to measurably improve system reliability.
