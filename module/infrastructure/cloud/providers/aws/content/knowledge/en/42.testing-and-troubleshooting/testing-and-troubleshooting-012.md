# Writing Runbooks, Postmortems, and Preventive Actions

## Learning Objectives

A production AWS system cannot avoid incidents altogether. What separates a mature operations team from a team perpetually fighting fires is advance preparation, disciplined response, thorough evidence capture, and turning every incident into verifiable improvements.

A runbook defines a procedure with a predictable outcome, such as rolling back a deployment, restoring a resource, or inspecting a queue backlog. A playbook guides investigation when root cause is unknown: collecting signals, forming hypotheses, testing each hypothesis, isolating impact, and deciding when to escalate. A postmortem documents what happened, impact, contributing factors, and changes required to reduce recurrence.

This lesson belongs to the **Testing and Troubleshooting** chapter of the CLOUD_PROVIDERS_AWS module. It connects operational processes with AWS services such as Amazon CloudWatch, Amazon EventBridge, AWS Systems Manager Automation, OpsCenter, CloudTrail, and CloudWatch Investigations.

After this lesson, learners will be able to:

- Distinguish events, alerts, incidents, and problems.
- Distinguish runbooks, playbooks, incident response plans, and postmortems.
- Design an incident lifecycle with roles, severities, escalation paths, and communications.
- Write runbooks with objectives, prerequisites, execution steps, expected results, and rollbacks.
- Write investigation playbooks with decision points, evidence, and escalation criteria.
- Automate stabilization steps using Systems Manager Automation, Lambda, CloudWatch, and EventBridge.
- Use CloudWatch Investigations and OpsCenter within their appropriate scopes.
- Run blameless postmortems with timelines and multiple contributing factors.
- Create corrective actions with owners, deadlines, priorities, and verification criteria.
- Measure improvement effectiveness using MTTD, time to engage, time to mitigate, recurrence rate, and SLOs.
- Test runbooks, tabletop exercises, and game days before they are needed in anger.

## 1. From Events to Incidents and Problems

Operational terms are related yet not interchangeable.

| Term | Meaning | Example |
|---|---|---|
| Event | Something happening in the system, normal or abnormal | Deployment completes, EC2 instance reboots, S3 object created |
| Alert | Notification generated when a condition warrants attention | CloudWatch alarm reports p95 latency breached threshold |
| Incident | Service disruption or degradation requiring coordinated response | Checkout API returns 5xx to many customers |
| Problem | Underlying cause or set of causes needing long-term remediation | Insufficient connection pool under traffic growth |
| Change | Intentional modification to the system | Deploying a new version, editing policies, or scaling capacity |
| Near miss | Event that nearly caused major impact yet was caught in time | Queue nearly hits retention limit before consumers recover without data loss |

An alert is not automatically an incident. A brief CPU spike while latency and error rates stay within SLO may require only monitoring. Conversely, an incident can begin before an alarm triggers—or without any alarm detecting it.

Problem management looks beyond closing the incident. If restarting a service restores availability while a connection leak remains, the incident is mitigated yet the problem stays unresolved.

~~~mermaid
flowchart TD
    A[Event] --> B{Condition warrants attention?}
    B -->|No| C[Record or ignore per policy]
    B -->|Yes| D[Alert]
    D --> E{Customer / business impact?}
    E -->|No| F[Operational task or investigation]
    E -->|Yes| G[Declare incident]
    G --> H[Mitigate and recover]
    H --> I[Close incident]
    I --> J[Post-incident analysis]
    J --> K[Problem and corrective actions]
    K --> L[Prevent, detect, mitigate better]
~~~

## 2. Runbooks, Playbooks, Incident Plans, and Postmortems

Four document types serve distinct stages.

| Document | Question Answered | When Used |
|---|---|---|
| Incident management plan | Who coordinates, what severity applies, who to contact, and how updates flow? | When an incident is declared |
| Playbook | How to investigate a symptom whose root cause is unknown? | During triage and investigation |
| Runbook | How to execute a known procedure for a specific outcome? | During deployments, checks, or remediation |
| Postmortem | What happened, why, and what must change? | After impact is contained |

Example: CloudWatch alerts on a rising SQS backlog.

- The incident plan identifies the Incident Commander, application team, and communications lead.
- The playbook guides checking arrival rates, consumer concurrency, DLQs, downstream dependencies, and recent deployments.
- The runbook guides raising Lambda reserved concurrency after verifying quotas and dependency capacity, or rolling back a configuration change.
- The postmortem records why the backlog grew, customer impact, contributing factors, and long-term actions.

A runbook should produce a predictable outcome. A playbook should contain branching decision points because root cause is unknown. Never turn a runbook into an endless troubleshooting manual.

## 3. Incident Lifecycle

A common workflow consists of these phases:

1. **Detect:** alarms, customer reports, support tickets, or events surface abnormal behavior.
2. **Declare:** confirm the incident, assign severity, create an incident record, and open coordination channels.
3. **Triage:** determine scope, customer impact, affected services, and initial hypotheses.
4. **Mitigate:** halt or reduce customer impact; prioritize restoring service safely.
5. **Resolve:** fix the underlying cause or replace broken components with healthy versions/configs.
6. **Recover:** verify the system returns to normal state, drain backlogs, and validate data.
7. **Communicate and close:** publish status updates, confirm owners, and verify closing criteria.
8. **Learn:** conduct the postmortem, create corrective actions, and update runbooks/playbooks.

Not every incident requires identical ceremony. A minor error with zero customer impact can be handled as an operational task. Incidents involving data loss, security breaches, or widespread outages require dedicated procedures.

During an active incident, protecting customers and data comes first. Deep root-cause investigation can continue after service restoration, provided evidence is preserved.

## 4. Classifying Severity

Severity should reflect real-world impact, not a single isolated metric.

Sample severity matrix:

| Level | Impact | Example | Response |
|---|---|---|---|
| SEV-1 Critical | Critical service down, data loss, or severe security incident | Checkout transactions completely unavailable broadly | Activate incident process immediately, centralized coordination, continuous updates |
| SEV-2 High | Core functionality severely degraded, many customers affected | Payment failure rate spikes sharply | Page owning and dependency teams, high-priority mitigation |
| SEV-3 Medium | Limited impact or workaround available | One user group cannot view reports | Assign owner, monitor, and resolve per SLA |
| SEV-4 Low | No clear customer impact, minor flaw, or near miss | Early-warning alarm fires while SLO remains met | Create operational task or backlog improvement |

When classifying, evaluate:

- Number and percentage of affected customers.
- Impact on revenue, payments, data, and legal/regulatory obligations.
- Scope across services, Regions, Availability Zones, or tenants.
- Availability of a workaround.
- Rate of spread and recoverability.
- Any signs of credential compromise, data exposure, or integrity loss.

Severity can be upgraded or downgraded as new evidence emerges. Record the reason for changes so teams understand decisions in context.

## 5. Roles in Incident Response

Major incidents need clear role assignments so multiple responders do not run conflicting commands or leave tasks unowned.

| Role | Responsibilities |
|---|---|
| Incident Commander (IC) | Coordinates response, sets priorities, assigns owners, drives escalations, keeps cadence |
| Technical Lead / Operations Lead | Leads technical investigation, proposes and coordinates mitigations |
| Subject Matter Expert (SME) | Analyzes specialized domains such as databases, networking, IAM, or applications |
| Communications Lead | Updates stakeholders, support, and customers per plan |
| Scribe | Records timeline, decisions, evidence, actions, and owners |
| Business Owner | Assesses business impact, workarounds, and recovery priorities |

In smaller incidents, one person may wear multiple hats. In major incidents, the IC should avoid performing hands-on technical changes directly so coordination does not break down.

Explicitly designate who holds decision authority and who holds execution authority for remediation. Runbooks must state who is authorized to restart, fail over, roll back, rotate credentials, or shift traffic.

## 6. Building an Incident Management Plan

An incident plan is a service- or organization-level document. It does not hold every technical command; it defines how people coordinate.

A plan should include:

- List of service and business owners.
- Severity definitions and incident declaration criteria.
- Primary and backup incident communication channels.
- On-call paging and escalation paths.
- Roles for IC, technical lead, communications lead, and scribe.
- Internal and customer update cadences and rules.
- Emergency access and break-glass procedures.
- Locations of runbooks, playbooks, architecture diagrams, and dependency maps.
- How to open an AWS Support case when needed.
- Mitigation, recovery, and closure criteria.
- Postmortem requirements and deadlines.

Test contact lists periodically. A stale phone number or outdated contact in a plan wastes precious minutes during real outages.

## 7. Runbooks Should Follow a Consistent Structure

A runbook must contain enough detail for an engineer who did not write it to execute it accurately.

Metadata template:

| Field | Contents |
|---|---|
| Runbook ID | Unique identifier, e.g., `RUN-SQS-001` |
| Title | Procedure name |
| Service / Environment | Applicable service and environment |
| Desired outcome | Target state after execution |
| Trigger | Alarm, request, or start condition |
| Owner | Maintaining team |
| Version | Document/automation version |
| Last validated | Most recent test date |
| Required permissions | Required IAM role and permissions |
| Tools | AWS CLI, Console, CloudWatch, Systems Manager |
| Risk | Impact if executed improperly |
| Approval | Is approval required before mutating steps? |
| Escalation | Person/team to page if unsuccessful |

The procedure section should include columns:

| Step | Action | Expected Result | If Not Met |
|---|---|---|---|
| 1 | Check state and scope | Target resource confirmed | Stop and verify target |
| 2 | Gather metrics/logs | Pre-change evidence captured | Escalate if telemetry missing |
| 3 | Execute remediation | Resource transitions to desired state | Roll back or halt |
| 4 | Verify | SLOs and health return to normal | Continue with playbook |
| 5 | Record | Execution ID and outcome logged | Open action item if runbook failed |

Runbooks need owners and validation schedules. Documentation that drifts from the live system becomes a source of risk.

## 8. Writing Safe, Actionable Runbook Steps

Each step should use specific verbs and name explicit resources.

Good examples:

- Fetch `ApproximateAgeOfOldestMessage` for queue `orders-processing-prod`.
- Inspect `ConcurrentExecutions` and `Throttles` for the Lambda consumer over the last 15 minutes.
- Compare the current deployment version against the pre-incident version.
- Increase reserved concurrency only after confirming downstream database headroom.
- After applying the change, monitor queue age and error rate for 10 minutes.

Vague examples:

- Check the queue.
- Scale up resources if needed.
- Restart the service.
- Watch until it looks fine.

A strong step always answers:

1. Which exact resource is affected?
2. Which tool or API is used?
3. Which inputs/parameters are passed?
4. What is the expected result?
5. What happens if the result differs from expectations?
6. Does the step mutate state?
7. Who approves it or how is it rolled back?

## 9. Investigation Playbooks Need Decision Points

Playbooks start from symptoms when root cause is still unknown.

Example: elevated API latency.

~~~mermaid
flowchart TD
    A[Alert: API latency elevated] --> B[Confirm customer impact]
    B --> C{Error rate also rising?}
    C -->|Yes| D[Inspect 5xx, dependencies, and deployments]
    C -->|No| E[Inspect queues, CPU, DB latency, and traffic]
    D --> F{Recent deployment?}
    F -->|Yes| G[Compare versions and consider rollback]
    F -->|No| H[Investigate dependencies and networking]
    E --> I{Single dependency saturated?}
    I -->|Yes| J[Shed load / scale under control]
    I -->|No| K[Inspect queries, caches, and request profiles]
    G --> L[Verify SLO]
    H --> L
    J --> L
    K --> L
    L --> M{Recovered?}
    M -->|Yes| N[Monitor and record evidence]
    M -->|No| O[Escalate / widen investigation scope]
~~~

Each branch should specify concrete commands or queries, expected outcomes, and stop conditions. Playbooks must never assume the first hypothesis is correct.

## 10. Capturing Evidence Before Remediation

During incidents, quick fixes can destroy diagnostic evidence. Before major mutating changes, capture at minimum:

- Onset time and detection time.
- CloudWatch alarm state/history and metric datapoints.
- Application logs, service logs, and trace IDs.
- CloudTrail events for deployments, policies, or configuration changes.
- Resource ARNs, Region, Availability Zone, and deployment versions.
- Request IDs, error codes, and sanitized sample requests.
- Queue depths, database load, connection counts, or resource utilization.
- Actions already taken and their outcomes.

Never delay urgent customer mitigation solely to collect exhaustive evidence. Capture the highest-value telemetry first if feasible, then collect deeper data once impact is contained.

For security incidents, follow a dedicated security incident response plan: preserve logs and snapshots, avoid unnecessary mutations, record chain of custody, and coordinate with security/legal. Never delete resources or credential evidence before authorized responders evaluate it.

## 11. Escalation and Handoffs

Escalation should trigger on time elapsed, severity, and technical thresholds.

Examples:

| Condition | Action |
|---|---|
| Impact unconfirmed after 10 minutes | Page service owner and IC |
| Two remediation attempts fail | Escalate to technical lead or platform team |
| Signs of data loss | Page database/data owner immediately |
| Signs of credential compromise | Trigger security incident process |
| Incident spans multiple Regions | Page cloud/platform owner and disaster recovery lead |
| Recovery exceeds RTO | Activate approved DR plan |
| No progress after one investigation cycle | Hold checkpoint and bring in fresh SMEs |

Timings above are illustrative. Organizations should set thresholds around SLOs, support coverage, and severity. Escalating does not mean dumping responsibility and leaving; the current role holder must confirm the incoming responder has taken ownership.

A clean handoff covers: current impact, timeline, tested hypotheses, evidence, changes made, remaining risks, next steps, and current owners per action.

## 12. Alerts Must Link to Response Procedures

An alert is valuable only when the recipient knows what to do. Every alarm should include:

- Metric and threshold.
- Evaluation periods and datapoints-to-alarm.
- Severity or priority.
- Owning team.
- Potential customer impact.
- Link to dashboard.
- Link to playbook/runbook.
- Escalation conditions.
- Guidance on identifying false positives and confirming recovery.

Avoid alerting simply because a metric is non-zero. Thresholds must derive from baselines, SLOs, and workload behavior.

For example, high SQS queue depth is not always an incident. `ApproximateAgeOfOldestMessage` often tracks processing delay more directly. For APIs, evaluate latency and error rates alongside request volume and business SLOs.

## 13. Connecting CloudWatch, EventBridge, and Systems Manager Automation

AWS supports automating responses to monitoring events:

1. CloudWatch alarm detects a metric breaching conditions.
2. Alarm transitions to `ALARM` and emits an event.
3. SNS notifies on-call responders or paging systems.
4. EventBridge routes the event to Lambda, Systems Manager Automation, or creates an OpsItem.
5. An Automation runbook gathers diagnostics or runs approved remediation.
6. Outputs are logged to CloudWatch Logs, OpsItems, or incident trackers.

Do not automate every mutating action merely because an alarm enters `ALARM`. Start with read-only diagnostics, and require approval for mutating steps like restarts, failovers, scaling, or rollbacks.

In many cases, CloudWatch alarm actions fire only on state transitions; if an alarm stays in `ALARM` for hours, actions do not repeatedly re-fire on their own. Design explicit retries or periodic re-evaluation if needed.

## 14. AWS Systems Manager Automation Runbooks

Systems Manager Automation executes step-by-step workflows. An Automation document can invoke AWS APIs, wait on resource states, branch, run scripts, or invoke other runbooks.

Common actions:

| Action | Purpose |
|---|---|
| `aws:executeAwsApi` | Invoke an AWS API |
| `aws:assertAwsResourceProperty` | Assert a resource/event matches expected state |
| `aws:waitForAwsResourceProperty` | Wait for a resource to transition states |
| `aws:branch` | Branch based on step outputs |
| `aws:executeScript` | Run Python or PowerShell |
| `aws:runCommand` | Execute commands on managed nodes |
| `aws:approve` | Pause pending manual approval |

The Automation role needs least-privilege permissions for invoked actions. Runbooks should constrain parameters, targets, and concurrency; risky operations require approvals or explicit execution scopes.

### 14.1. Read-Only Runbook Example for Diagnosing an SQS Backlog

The example below fetches queue attributes and CloudWatch alarm state. It makes no modifications to the queue or Lambda.

~~~yaml
---
description: "Read-only diagnostics for an SQS backlog"
schemaVersion: "0.3"
assumeRole: "{{ AutomationAssumeRole }}"
parameters:
  AutomationAssumeRole:
    type: String
    description: "IAM role used by Systems Manager Automation"
  QueueUrl:
    type: String
    description: "URL of the queue to inspect"
  AlarmName:
    type: String
    description: "CloudWatch alarm associated with the queue"
mainSteps:
  - name: inspectQueue
    action: aws:executeAwsApi
    inputs:
      Service: sqs
      Api: GetQueueAttributes
      QueueUrl: "{{ QueueUrl }}"
      AttributeNames:
        - ApproximateNumberOfMessages
        - ApproximateNumberOfMessagesNotVisible
        - ApproximateNumberOfMessagesDelayed
        - VisibilityTimeout
        - RedrivePolicy
    outputs:
      - Name: VisibleMessages
        Selector: "$.Attributes.ApproximateNumberOfMessages"
        Type: String
      - Name: InFlightMessages
        Selector: "$.Attributes.ApproximateNumberOfMessagesNotVisible"
        Type: String
  - name: inspectAlarm
    action: aws:executeAwsApi
    inputs:
      Service: cloudwatch
      Api: DescribeAlarms
      AlarmNames:
        - "{{ AlarmName }}"
    outputs:
      - Name: AlarmState
        Selector: "$.MetricAlarms[0].StateValue"
        Type: String
~~~

The role needs `sqs:GetQueueAttributes` on the queue and `cloudwatch:DescribeAlarms` for the alarm. In production implementations, handle missing alarms, invalid queue URLs, or responses missing expected fields. Outputs, validation, and notifications can be added. `aws:executeAwsApi` has per-step time limits; do not use a single step for long-running tasks.

### 14.2. Classifying Read-Only vs. Mutating Steps

| Step Class | Examples | Controls |
|---|---|---|
| Read-only | Describe queue, get alarm, query metrics | Can be automated with scoped IAM permissions |
| Low-risk change | Add tag, create ticket, temporarily raise log level | Scope targets, duration, and auditing |
| Mutating | Restart instance, change desired count, roll back deployment | Approvals, pre-checks, post-checks, and rollback |
| High-impact | Fail over database, rotate credentials broadly, alter security policies | Incident Commander/owner approval and dedicated runbook |

Never assume `aws:executeAwsApi` is read-only by default. API actions can mutate resources; classify strictly by the specific API called.

## 15. OpsCenter and CloudWatch Investigations

AWS Systems Manager OpsCenter aggregates operational work items (OpsItems) tied to AWS resources. OpsItems can be created manually, from CloudWatch alarms, or via EventBridge events; operators inspect resource context and launch Systems Manager Automation to investigate/remediate.

CloudWatch Investigations assists operational troubleshooting by gathering signals and offering AI-generated suggestions. Investigators review, accept, or dismiss findings and can trigger remediation through automated runbooks.

Important tool-selection notes:

- AWS Systems Manager Incident Manager stopped onboarding new customers on November 7, 2025 and is no longer receiving new features.
- Accounts that enabled Incident Manager prior to that date can continue using it within those accounts.
- AWS recommends OpsCenter for managing operational issues; OpsCenter does not provide paging or on-call rotations.
- If automated paging, escalations, and on-call schedules are needed for new deployments, evaluate AWS Partner Network solutions or existing incident management systems.
- CloudWatch Investigations assists with analysis and suggestions, yet human investigators must verify evidence and remain accountable for remediation.

Do not design new workflows assuming every account can enable Incident Manager. Check account eligibility and current service capabilities before choosing tooling.

## 16. Incident Communications

Communications should be concise, accurate, timestamped, and state next steps. Never speculate on root cause without evidence.

Internal update template:

~~~text
INCIDENT: INC-2026-042
SEVERITY: SEV-2
STATUS: Investigating
STARTED: 2026-11-20 08:15 UTC

CUSTOMER IMPACT:
A subset of order creation requests are timing out in ap-southeast-1.

CURRENT FINDINGS:
Timeout rate increased alongside rising queue age. Final root cause not yet confirmed.

ACTIONS:
- Incident Commander assigned.
- Consumer team inspecting concurrency and downstream database.
- Holding current deployment steady to preserve evidence.

NEXT UPDATE:
2026-11-20 08:35 UTC
~~~

Customer update template:

~~~text
We are investigating elevated delays affecting some order creation requests.
Some requests may need to be retried. Submitted order data already recorded will continue
processing once service recovers.

We will provide an update once we confirm the full scope and recovery timeline.
~~~

Only the designated communications owner should issue external updates. For security incidents, coordinate with security, legal, and privacy teams before releasing details that could affect investigations.

## 17. When Should an Incident Be Closed?

An incident should never be closed solely because one alarm returned to `OK`.

Typical closure criteria include:

- Customer impact has ceased.
- SLOs and business KPIs remain within acceptable bounds across a defined observation window.
- Queues/backlogs are drained or have an explicit drain plan.
- No unassessed data integrity issues remain.
- Workarounds and residual risks are documented.
- Owners are assigned for remaining follow-up items.
- Stakeholders received a final update.
- Evidence and timelines are archived.
- A postmortem is scheduled with a facilitator if eligible for review.

Mitigation and resolution are two distinct milestones. If a rollback restores customer transactions yet why the deployment broke remains unknown, the incident may close once stable while a problem ticket stays open.

## 18. What Is a Postmortem and When Should One Be Held?

A postmortem (also called a post-incident analysis or Correction of Error — COE in some organizations) is a structured review after an incident. Its goal is to understand how systems and processes allowed the incident to happen, then drive changes reducing recurrence probability or blast radius if it recurs.

Review when:

- Any incident caused significant customer impact.
- Any incident caused data loss or security/compliance impact.
- A near miss could have caused major impact.
- An incident recurs or the same pattern appears repeatedly.
- Detection, escalation, or recovery durations breached targets.
- Fault injection/game days revealed broken runbooks or controls.

You do not need a full postmortem for every minor alert. However, repeated small incidents often signal a larger underlying weakness accumulating.

## 19. Blameless Postmortems

Blameless does not mean abandoning accountability. It means examining actions and decisions in light of the information, tools, pressures, and processes responders had at the time.

Avoid writing:

- "The engineer forgot to check."
- "The operator ran the wrong command."
- "The developer was careless."

Replace with systemic questions:

- Why could the operation run without a pre-check?
- Why did reviews miss the change?
- Why did alarms fail to warn before customer impact?
- Why had rollback never been tested?
- Why could the on-call engineer not locate the right runbook?
- Why were permissions or escalation paths unclear?

When humans make mistakes, identify the conditions that made the error easy and lacked safeguards. Good outcomes add validation, automation, guardrails, training, or architectural improvements.

## 20. Capturing Timelines and Measuring Response Times

Timelines must use consistent UTC timestamps and distinguish key milestones.

| Milestone | Meaning | Example |
|---|---|---|
| T0 - Incident start | Customer impact begins | 08:15 |
| T1 - Detection | Alarm or user detects issue | 08:19 |
| T2 - Engagement | Right responder joins | 08:24 |
| T3 - Mitigation | Impact stops or drops | 08:37 |
| T4 - Resolution | System stabilizes and backlog drains | 09:05 |

From the timeline, compute:

- **Time to detect (TTD):** T1 - T0.
- **Time to engage:** T2 - T1.
- **Time to mitigate:** T3 - T0 or T3 - T2; always state the formula used when reporting.
- **Time to resolve:** T4 - T0.
- **Customer impact duration:** actual period customers experienced impact.

Never report an unqualified MTTR metric without defining repair, recovery, or resolution. Different teams define MTTR differently; publish exact definitions on dashboards.

Timelines can be reconstructed from CloudWatch alarm history, CloudTrail, deployment events, application logs, traces, tickets, and incident chat. Automation can gather raw timestamps; human reviewers must verify timestamps and interpretations.

## 21. Postmortem / COE Template

The template below can structure an incident review document:

~~~text
# POSTMORTEM / CORRECTION OF ERROR

Incident ID:
Service / Environment:
Severity:
Incident start:
Detection:
Mitigation:
Resolution:
Facilitator:
Review date:
Participants:

## 1. Executive summary
What happened in 3-5 sentences?

## 2. Customer and business impact
- Affected users / tenants / Regions:
- Failed request rate or failed transactions:
- Lost, duplicated, or corrupted data:
- Revenue, SLA, or compliance impact:
- Workaround:

## 3. Timeline (UTC)
| Time | Event | Evidence | Decision / Action | Owner |

## 4. Detection and response
- Which alarm detected it?
- Were any alerts missing or noisy?
- Who was paged and when?
- Which runbook/playbook was used?
- Which mitigations worked or failed?

## 5. What happened
Evidence-backed technical sequence.

## 6. Contributing factors
- Trigger:
- Latent conditions:
- Detection gaps:
- Design / capacity gaps:
- Process / communication gaps:
- Dependency factors:

## 7. Root cause analysis
Five Whys / Ishikawa / causal graph.
Distinguish evidence, hypotheses, and conclusions.

## 8. What went well
Controls or actions that limited impact.

## 9. What did not go well
Gaps in detection, response, recovery, or communication.

## 10. Corrective and preventive actions
| Action | Type | Priority | Owner | Due date | Verification |

## 11. Cross-workload learning
Which other workloads/teams share this pattern and need inspection?

## 12. Follow-up
Action review date, facilitator, and effectiveness validation method.
~~~

Postmortems must be discoverable, properly access-controlled, and linked to incident records, code changes, alarms, dashboards, and action tickets.

## 22. Finding Contributing Factors Instead of Stopping at One Cause

Incidents usually arise when multiple conditions align.

Example: a deployment increases database query latency. Consumer connection pools fill up, Lambda concurrency hits its limit, the SQS backlog grows, and order creation requests time out. The deployment is the trigger, yet rarely the sole cause.

Categorizing contributing factors:

- **Trigger:** the immediate event initiating impact.
- **Latent condition:** pre-existing weakness that had not yet caused an outage.
- **Detection gap:** monitoring failed to alert early enough.
- **Mitigation gap:** no mechanism existed to reduce impact quickly.
- **Recovery gap:** rollback or failover had not been tested.
- **Process gap:** unclear ownership, approvals, or escalation paths.
- **External dependency:** third-party service, quotas, or provider behavior.

Use causal graphs or Ishikawa diagrams to examine multiple causal branches. A simplistic single-cause statement hides the systemic conditions that allowed the incident to spread.

## 23. Five Whys and Ishikawa

Five Whys iteratively asks "why" to uncover deeper conditions. Exactly five questions are not mandatory; stop when causes are verifiable and lead to concrete actions.

Example:

1. Why did order processing slow down? Because consumers processed messages slowly.
2. Why were consumers slow? Because Lambda throttled and database connections hit limits.
3. Why did concurrency spike? Because a deployment increased processing time per message.
4. Why did rollout exceed capacity? Because load tests omitted burst traffic and DB connection pressure.
5. Why was that check missing? Because the release checklist tracked only average API response time, omitting queue age and downstream connections.

The conclusion must not be "the deployment team was careless." Valid contributing factors include: missing queue-age alarms, load tests lacking bursts, concurrency uncapped relative to DB capacity, and unrehearsed rollbacks.

Ishikawa diagrams can group causes across:

- People: skills, training, role clarity.
- Process: reviews, change management, escalation.
- Technology: code, architecture, dependencies.
- Data: payloads, schemas, volumes, quality.
- Environment: Regions, AZs, networking, quotas.
- Measurement: metrics, logs, alarms, retention.

## 24. Corrective Actions Must Be Specific and Verifiable

A strong action item answers:

- What changes?
- Which problem does it address?
- Who owns it?
- When is it due?
- How will it be verified?
- Which risks or dependencies must be tracked?

Action categories:

| Type | Objective | Example |
|---|---|---|
| Prevention | Prevent triggers or failure-enabling conditions | Add connection limits and validation |
| Detection | Detect issues earlier | Alert on queue age and error budgets |
| Mitigation | Reduce blast radius | Cap concurrency, add circuit breakers |
| Recovery | Recover faster and more safely | Test rollbacks and restores |
| Process | Improve people/workflows | Clarify owners, escalation, and reviews |
| Learning | Spread knowledge | Update runbooks, training, and readiness reviews |

Weak action: "Improve monitoring."

Strong action: "Platform team adds an `ApproximateAgeOfOldestMessage` alarm exceeding 120 seconds for 3 datapoints, routing to the on-call channel and linking playbook `SQS-Backlog`; due Dec 15; verified via game day."

### 24.1. Action Tracker

| ID | Action | Type | Priority | Owner | Due | Verification | Status |
|---|---|---|---|---|---|---|---|
| ACT-01 | Add queue-age alarm and escalation | Detection | P1 | Platform | Dec 15 | Game day inducing backlog | Open |
| ACT-02 | Cap concurrency per DB capacity | Prevention | P1 | App team | Dec 18 | Burst load test | Open |
| ACT-03 | Add connection pool dashboard | Detection | P2 | DBA | Dec 20 | Metrics displayed properly | Open |
| ACT-04 | Rehearse consumer release rollback | Recovery | P2 | Release team | Dec 22 | Rollback within RTO | Open |

Never close an action merely because code merged. Verify metrics, tests, runbooks, or system behavior actually meet the goal.

## 25. Prioritizing Corrective Actions

Not every action carries equal urgency. Prioritize by:

- Customer impact if the failure recurs.
- Probability of recurrence.
- Breadth of affected workloads.
- Potential to shrink blast radius.
- Implementation complexity and effort.
- Risk of introducing new regressions.

Example:

| Priority | Sample Criteria | Expectation |
|---|---|---|
| P0 | Active data-loss/security vulnerability or widespread outage risk | Address immediately via incident/change process |
| P1 | High recurrence risk with severe impact | Schedule in nearest sprint and track closely |
| P2 | Meaningful resilience/detection improvement | Plan with explicit owner and deadline |
| P3 | Minor optimization or documentation update | Add to backlog and review periodically |

These are sample conventions; organizations should align them with risk appetite. Never use low priority to ignore compliance or security actions.

## 26. Closing the Loop to Prevent Recurrence

A postmortem creates value only when actions are implemented and verified.

Improvement loop:

~~~mermaid
flowchart LR
    A[Incident / Near miss] --> B[Evidence and timeline]
    B --> C[Postmortem / RCA]
    C --> D[Contributing factors]
    D --> E[Corrective action backlog]
    E --> F[Implement change]
    F --> G[Test and verify]
    G --> H[Update runbook / playbook / ORR]
    H --> I[Measure recurrence and SLO]
    I --> A
~~~

Sustaining mechanisms:

- Track actions as issues/tickets with owners and due dates.
- Review P0/P1 actions in operational reviews.
- Require escalation and justification for overdue items.
- Update alarms, dashboards, runbooks, and playbooks.
- Audit other workloads sharing the same pattern.
- Add new questions to Operational Readiness Reviews (ORR).
- Validate improvements via game days or controlled failure tests.
- Measure recurrence rates and response times after completion.

An action marked `Done` without verification evidence has not proven risk reduction.

## 27. Measuring Operational Effectiveness

Useful metrics:

| Metric | Definition | Used For |
|---|---|---|
| MTTD / TTD | Time from incident start to detection | Evaluating monitoring |
| Time to engage | From detection until the right responder joins | Evaluating paging/escalation |
| Time to mitigate | From incident start or engagement until customer impact drops | Evaluating containment |
| Time to resolve | From incident start until full system stability | Evaluating recovery |
| Incident recurrence rate | Share of incidents repeating the same pattern | Evaluating preventive actions |
| Alert precision | Share of alerts genuinely requiring action | Evaluating alert noise |
| Runbook success rate | Share of executions completing with desired outcome | Evaluating docs/automation |
| Action closure on time | Share of actions completed by due date | Evaluating follow-through |
| SLO / error budget | Adherence to reliability targets | Tying operations to customer experience |

Never game metrics mechanically. For instance, lowering time to resolve by closing incidents prematurely hides lingering backlogs or data integrity issues. Pair quantitative metrics with customer impact and qualitative reviews.

## 28. Testing Runbooks Before Publishing

Runbooks should be tested like code:

1. Execute in test environments or on non-production resources.
2. Test valid inputs, malformed inputs, and nonexistent resources.
3. Verify least-privilege IAM permissions.
4. Verify step outputs and final states.
5. Test failure and timeout branches.
6. Verify rollback or recovery paths.
7. Have an engineer who did not write the document execute it end-to-end.
8. Inspect CloudWatch Logs, execution history, and audit trails.
9. Measure execution duration against targets.
10. Update version and `last validated` date.

For mutating runbooks, validate target constraints, concurrency caps, approvals, and stop conditions. An instance-restart runbook can work cleanly at the API level yet cause an outage if its target selector matches the entire fleet.

## 29. Tabletop Exercises and Game Days

A tabletop exercise walks through a scenario verbally without necessarily injecting real faults. A game day actively creates conditions in a controlled environment to verify both system behavior and human response.

Tabletop example:

- CloudWatch alerts on database connection saturation.
- IC declares SEV-2.
- DBA inspects Database Insights.
- App team checks connection pools.
- Team decides to lower consumer concurrency.
- Communications Lead drafts a status update.
- Scribe captures timeline and decisions.

Pre-production game day example:

- Ramp message arrival rate under control.
- Observe queue age and consumer concurrency.
- Verify alarms fire.
- Run diagnostic playbooks and runbooks.
- Test escalation paths.
- Halt the experiment if stop conditions trigger.
- Verify backlog drain and SLO recovery.

Never start with destructive actions in production. Every experiment needs a hypothesis, scope, owner, stop conditions, rollback plan, and approved schedule.

## 30. Automating Postmortem Evidence Collection

Automate telemetry gathering so facilitators can focus on analysis:

- CloudWatch alarm history across the incident window.
- Metric datapoints before/during/after the incident.
- CloudTrail management events and deployment/config changes.
- CloudFormation stack events.
- Lambda/ECS/RDS/SQS logs.
- X-Ray or OpenTelemetry traces.
- Systems Manager Automation execution history.
- Incident ticket/chat timestamps.
- Version and commit SHA of recent releases.

Automation does not decide root cause on its own. Summaries or AI suggestions are merely hypotheses requiring human verification against evidence. Reviewers must still ask which conditions combined to cause impact and why existing controls failed to stop it.

Keep retention long enough to spot historical patterns. Ensure evidence respects access controls, redaction, and retention under security/privacy policies.

## 31. Security Incidents Need Dedicated Playbooks

Security incidents require handling distinct from standard availability outages.

High-level steps:

1. Validate findings and identify affected resources/accounts/Regions.
2. Activate the security incident process and designate an incident lead.
3. Preserve CloudTrail, VPC Flow Logs, service logs, snapshots, and relevant evidence.
4. Identify potentially impacted principals, credentials, resources, and data.
5. Contain per approved plan: revoke/disable credentials, isolate instances, block networking, or restrict access.
6. Coordinate with security, legal, privacy, and compliance owners.
7. Eradicate persistence or insecure configurations.
8. Recover from known-good state and rotate secrets/keys as appropriate.
9. Verify monitoring and access controls.
10. Conduct postmortem and track corrective actions.

Never delete logs, instances, or snapshots before assessing forensic needs. Never broadly rotate or revoke credentials without mapping dependencies and blast radius unless the security incident plan explicitly mandates emergency action.

## 32. Case Study: SQS Backlog Delaying Order Processing

An e-commerce platform uses API Gateway, Lambda, SQS, and DynamoDB. Following a deployment, the `orders-processing` queue accumulates a backlog and customers see delayed order status updates.

**Detection**

- CloudWatch alarm on `ApproximateAgeOfOldestMessage` enters `ALARM`.
- Dashboards show Lambda `Throttles` climbing and `ConcurrentExecutions` hitting limits.
- DynamoDB consumed capacity jumps concurrently.
- The API still accepts orders yet fulfillment updates lag behind.

**Response**

- IC declares SEV-2 and assigns technical lead to the app team.
- Scribe logs the timeline and deployment version.
- Playbook checks queue, DLQ, Lambda concurrency, DynamoDB throttling, and releases.
- Team confirms consumer processing slowed after a query change; rising concurrency pressured the database.
- Mitigation: roll back the consumer release and hold concurrency at a verified safe level.
- Team monitors queue age dropping and backlog draining.
- Once SLOs recover, IC updates stakeholders and closes the incident.

**Postmortem**

- Trigger: deployment increased processing time per message.
- Contributing factor 1: load tests lacked campaign-like burst traffic.
- Contributing factor 2: consumer concurrency was not tied to database capacity.
- Contributing factor 3: alarms watched only queue depth, lacking queue age.
- Contributing factor 4: runbook omitted checking dependencies before raising concurrency.

**Corrective actions**

1. Add a queue-age alarm and link the playbook.
2. Add burst traffic and DB connection pressure to load tests.
3. Cap concurrency based on DynamoDB capacity.
4. Add dashboard panels for per-message processing time and throttling.
5. Update the consumer scaling runbook to require DB checks before raising capacity.
6. Rehearse consumer release rollbacks in pre-production.

Each action has an owner, due date, verification evidence, and status. Once complete, a game day confirms queue age stays within SLO under representative load.

## 33. Production Readiness Checklist for Runbooks and Postmortems

### Incident Process

- [ ] Severities and customer impact criteria are defined.
- [ ] Incident Commander roles and escalation paths exist.
- [ ] Internal channels and customer communication plans exist.
- [ ] Someone is assigned to record timelines and decisions.
- [ ] Mitigation, recovery, and closure criteria are defined.
- [ ] Security incident workflows and break-glass access exist.

### Runbooks / Playbooks

- [ ] Owners, versions, and validation dates are tracked.
- [ ] Desired outcomes and triggers are explicit.
- [ ] Prerequisites, IAM permissions, and tools are listed.
- [ ] Steps include expected results and failure paths.
- [ ] Decision points and escalation criteria exist.
- [ ] Mutating actions require approvals/guardrails.
- [ ] Verification and rollback steps exist.
- [ ] Someone other than the author has tested running it.

### Postmortems / Corrective Actions

- [ ] UTC timeline and customer impact are documented.
- [ ] Evidence from CloudWatch, CloudTrail, and service logs is included.
- [ ] Multiple contributing factors are captured instead of a single trigger.
- [ ] Reviews are conducted blamelessly.
- [ ] Actions have owners, due dates, priorities, and verification criteria.
- [ ] Actions are tracked through completion.
- [ ] Lessons are shared across workloads sharing the same pattern.
- [ ] Runbooks, alarms, ORR checklists, and tests are updated.

### Automation and Learning

- [ ] CloudWatch/EventBridge trigger the right responses.
- [ ] Systems Manager Automation roles follow least privilege.
- [ ] Concurrency limits, approvals, and stop conditions are enforced.
- [ ] Automation outputs are logged and audited.
- [ ] CloudWatch Investigations findings are verified by humans.
- [ ] OpsCenter or incident trackers maintain owners and statuses.
- [ ] Tabletop/game days run on a schedule.
- [ ] Recurrence rates, detection times, and action closure rates are measured.

## 34. Self-Check Exercises

### Question 1

How do runbooks and playbooks differ?

**Answer:** Runbooks execute procedures with predictable outcomes; playbooks guide investigations when root cause is unknown using decision points and escalations.

### Question 2

How do events, alerts, incidents, and problems differ?

**Answer:** An event is an occurrence; an alert is a notification needing attention; an incident is a disruption requiring coordinated response; a problem is the underlying cause or weakness needing long-term resolution.

### Question 3

Why should severity not be based solely on CPU or memory?

**Answer:** Severity reflects customer/business impact, scope, data, and recoverability. Resource metrics are merely technical signals.

### Question 4

What is the Incident Commander responsible for?

**Answer:** Coordinating response, setting priorities, assigning owners, managing escalations, making decisions, and maintaining communication cadence.

### Question 5

What components does a runbook need?

**Answer:** Desired outcome, trigger, prerequisites, permissions, tools, steps, expected results, failure paths, escalation, verification, and rollback.

### Question 6

Why do mutating runbooks need approvals and guardrails?

**Answer:** Because operations can modify or disrupt live resources; targets, blast radius, and execution authority must be constrained.

### Question 7

Does a blameless postmortem mean nobody is accountable?

**Answer:** No. It focuses on systems and conditions enabling the failure while still assigning concrete owners to corrective actions.

### Question 8

Which milestones belong on a postmortem timeline?

**Answer:** Incident start, detection, engagement, mitigation, and resolution; milestones require UTC timestamps and evidence.

### Question 9

Must Five Whys always ask exactly five questions?

**Answer:** No. Question count varies by problem; stop once verifiable causes lead to actionable fixes.

### Question 10

Why should a postmortem not stop at blaming a deployment as the trigger?

**Answer:** Because the deployment may merely be the trigger; you must uncover latent conditions like missing tests, alarms, capacity guardrails, or rollback rehearsals.

### Question 11

What does a strong corrective action require?

**Answer:** A concrete change, owner, deadline, priority, dependencies, and how effectiveness will be verified.

### Question 12

Which metric measures how fast incidents are detected?

**Answer:** Time to detect (TTD/MTTD), measured from when customer impact starts until detection.

### Question 13

How do mitigation and resolution differ?

**Answer:** Mitigation halts or reduces customer impact; resolution fully fixes the issue and confirms system stability.

### Question 14

Can CloudWatch and EventBridge trigger Systems Manager Automation?

**Answer:** Yes. CloudWatch alarms emit events/state transitions that EventBridge can route to Automation or other targets per configuration.

### Question 15

Does OpsCenter completely replace Incident Manager?

**Answer:** No. OpsCenter manages OpsItems and integrates with Automation; it does not provide paging or on-call rotations.

### Question 16

Is AWS Systems Manager Incident Manager open to new customers as of November 2025?

**Answer:** No. Onboarding for new customers closed on November 7, 2025; accounts that enabled it beforehand can continue using it.

### Question 17

Can CloudWatch Investigations automatically determine root cause on behalf of humans?

**Answer:** No. AI-generated suggestions are supporting inputs; human investigators must verify evidence and take responsibility for decisions.

### Question 18

Why test runbooks with someone other than the author?

**Answer:** To uncover ambiguous steps, missing permissions, missing tools, or reliance on tribal knowledge.

### Question 19

When should a game day be conducted?

**Answer:** Once the environment, hypothesis, owner, stop conditions, and rollback are prepared; typically in pre-production or approved scopes.

### Question 20

When is a corrective action considered complete?

**Answer:** When the change is deployed and verification evidence proves it met its goal of reducing risk or improving detection/recovery.

## 35. Official References

- [OPS05-BP01: Develop and test runbooks to perform procedures](https://docs.aws.amazon.com/wellarchitected/latest/framework/ops05-bp01.html)
- [REL12-BP01: Use playbooks to investigate failures](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel12-bp01.html)
- [OPS07-BP01: Perform post-incident analysis](https://docs.aws.amazon.com/wellarchitected/latest/framework/ops07-bp01.html)
- [REL12-BP02: Perform post-incident analysis](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel12-bp02.html)
- [OPS10: Manage workload and operations events](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/responding-to-events.html)
- [AWS Well-Architected concepts: Five Whys, COE, RCA, playbook and runbook](https://docs.aws.amazon.com/wellarchitected/latest/framework/concepts.html)
- [AWS Systems Manager Automation](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-automation.html)
- [Systems Manager Automation actions reference](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-actions.html)
- [aws:executeAwsApi action](https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-executeAwsApi.html)
- [AWS Systems Manager OpsCenter](https://docs.aws.amazon.com/systems-manager/latest/userguide/OpsCenter.html)
- [CloudWatch alarm actions](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/alarm-actions.html)
- [Investigate operational issues with CloudWatch Investigations](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Investigations-Investigate.html)
- [Recommended best practices to enhance CloudWatch investigations](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Investigations-RecommendedServices.html)
- [AWS Systems Manager Incident Manager availability change](https://docs.aws.amazon.com/incident-manager/latest/userguide/incident-manager-availability-change.html)
- [Migrating to AWS Systems Manager OpsCenter](https://docs.aws.amazon.com/incident-manager/latest/userguide/migration-opscenter.html)
- [AWS FIS and game day planning](https://docs.aws.amazon.com/fis/latest/userguide/getting-started-planning.html)

Runbook actions, automation limits, service availability and incident tooling change over time. Pin document versions, validate IAM permissions and test every automated action in a controlled environment before connecting it to production alerts.
