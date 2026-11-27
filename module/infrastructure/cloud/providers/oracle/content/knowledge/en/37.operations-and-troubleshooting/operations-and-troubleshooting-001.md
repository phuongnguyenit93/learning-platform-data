# Designing OCI Runbooks and Assigning Operational Responsibilities

In the **Operations and Troubleshooting** chapter, an Oracle Cloud Infrastructure (OCI) system is considered operationally ready when the on-call engineer can answer: which service is impacted, who is responsible, what evidence must be collected, what changes are permitted, and what criteria determine that recovery is complete.

This lesson guides you through designing runbooks for OCI infrastructure including tenancy, compartment, IAM, VCN, Compute, storage, and Oracle database services. The focus is on connecting technical documentation with operational permissions, on-call schedules, monitoring, automation, and cost limits, so that procedures can be executed during real on-call shifts.

## 1. Objectives and Prerequisites

After this lesson, learners can:

- Build a runbook with trigger conditions, diagnostic steps, decision branches, recovery actions, and exit criteria.
- Distinguish between Oracle's responsibilities and the organization's workload operational responsibilities.
- Create a RACI matrix and assign primary on-call, backup on-call, and decision-making authorities.
- Link alarms, OCI resources, and incident records to the correct runbook version.
- Design operations with limited scope, rollback procedures, and post-execution evidence.
- Organize drills, handovers, and documentation updates when infrastructure changes.

Learners should know how to identify a tenancy, compartment, region, and OCID; and have basic knowledge of IAM policies, VCN, Network Security Groups (NSG), Compute, and Load Balancing. That knowledge helps read the operational context accurately; this lesson does not require deploying a new tenancy.

Service names, IP addresses, alert thresholds, and response timelines in the examples are illustrative data for a fictional organization. When putting them into use, the operations team must replace them with information approved for their own workload.

## 2. A Runbook Must Help the On-Call Engineer Make Decisions

A **runbook** is a procedure for executing an operational task with a defined scope. The task may be handling unhealthy backends, rotating certificates, restoring backups, or performing post-maintenance checks.

A usable runbook must have inputs, observable step outcomes, and stop conditions. A statement like "check the network and restart the machine" is insufficient because it does not specify which path to check, who is allowed to restart, how it affects users, or what to do if the machine still fails.

Distinguish between related documents:

| Component | Question Answered | Example in OCI |
| --- | --- | --- |
| Service profile | What makes up the workload, who does it serve, who owns it? | Which compartment the order API is in, which database it depends on |
| Response playbook | How is a group of scenarios coordinated? | Incident management process for customer-impacting incidents |
| Runbook | What steps execute a specific task? | Diagnosing an unhealthy backend set and restoring traffic |
| Infrastructure as Code (IaC) | Where is the desired infrastructure state described? | VCN, NSG, Load Balancer configuration in Terraform |
| Incident record | What happened during this execution? | Timeline, evidence, decisions, operators, results |

A runbook may invoke pipelines or IaC tools, but it still must state execution conditions, scope of changes, and verification methods. A script finishing successfully only indicates that the script completed as written; user-facing service status must be verified separately.

A good runbook also clearly states **when it does not apply**. A procedure for handling HTTP backends of an OCI Load Balancer cannot be applied as-is to a Network Load Balancer, OKE, or a database showing signs of data corruption.

## 3. Define Responsibility Boundaries Before Writing Commands

### 3.1. Oracle's Responsibilities vs. the Organization's Responsibilities

OCI uses the shared responsibility model. Oracle operates the underlying infrastructure; customers are responsible for securing their workloads and configuring the resources they use. Specific scope also depends on the service type, especially when comparing self-managed software on Compute with managed services. [Oracle: Security Overview](https://docs.oracle.com/en-us/iaas/Content/Security/Concepts/security_overview.htm).

The table below is an illustrative internal allocation that must be checked against actual services:

| Layer | Responsibilities Requiring an Owner Within the Organization |
| --- | --- |
| Tenancy, compartment, IAM | Managing identities, access policies, emergency access, and governance scope |
| VCN, subnet, NSG, route | Configuring connectivity, controlling traffic flows, and maintaining management paths |
| Self-managed Compute | Operating the guest OS, applications, configurations, and patches within customer scope |
| Block Volume, Object Storage | Access policies, data lifecycle, backup requirements, and restore testing |
| Oracle Databases | Assigning by specific product: configuration, data, access rights, and customer-required tasks |
| Application | Transaction quality, deployments, dependencies, SLOs, and service recovery |

Do not write a generic statement like "Oracle is responsible for the database" and leave the internal owner blank. For each database, the runbook must clearly state which product is used, who monitors its status, who changes configuration, who opens support requests, and who confirms that the application is working again.

Resiliency is also a shared responsibility: the organization must design and test HA, DR, failover, and business continuity plans for the workload. Having redundancy mechanisms in the underlying platform service does not automatically create a complete recovery plan for the application. [Oracle: Shared Responsibility Model for Resiliency](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/oci-shared-responsibility.htm).

### 3.2. Three Types of Authority to Document Separately

During an incident, the following three types of authority may belong to three different people:

1. **Technical permission:** IAM, OS permissions, database privileges, or pipeline execution rights that allow performing the operation.
2. **Approval authority:** internal governance mechanism authorizing acceptance of the operation's risk.
3. **Verification responsibility:** the person verifying that the result meets service requirements.

For example, a Platform engineer may have permission to update a backend set, but only within the authorized recovery scope. The Incident Commander coordinates decisions according to incident governance, while the application owner verifies business workflows. Incident command authority does not automatically grant IAM permissions and does not replace domain approval for every change.

## 4. Build a Service Profile and Dependency Map

A runbook should reference a maintained service profile. This profile is the single source of truth for workload names, owners, and resources.

| Information | Required Content |
| --- | --- |
| Service identity | Unique name, environment, criticality tier, owner |
| OCI location | Tenancy, compartment OCID, region, standby location if any |
| Resources | OCIDs of Load Balancers, Compute instances, volumes, databases, and related components |
| Traffic flow | DNS, listener, backend set, application port, NSG, path to database |
| Service targets | Agreed SLIs, SLOs, measurement window, RTO, and RPO |
| Observability | Dashboards, log queries, alarms, external synthetic checks |
| Deployment | Pipeline, running version, rollback-eligible version, configuration location |
| Recovery | Backup locations, most recent test, failover and failback conditions |
| Responsibilities | Primary team, backup team, on-call schedule, Security and Oracle Support contacts |
| Constraints | Maintenance windows, change permissions, capacity limits, and recovery budget |

**SLI** is a metric measuring service quality; **SLO** is the target for that metric. **RTO** is the target time to recover; **RPO** is the acceptable level of data loss over time. They must have clear business scope and cannot be inferred merely from an instance being in the RUNNING state.

The dependency map must represent both planes:

- **Data plane:** users → DNS → Load Balancer → application on Compute → database or storage.
- **Control/management plane:** on-call engineer → identity system → OCI API or pipeline → resources.

The management plane may fail while the application continues serving, or the application may fail while the Console remains accessible. Therefore, a successful read API call is not enough to conclude the workload is healthy; conversely, a Console access failure does not prove the application has stopped serving.

For shared VCNs or resources spanning multiple compartments, clearly document which team is responsible for each part. The application team should not have to guess who manages routes or NSGs during an incident.

## 5. Assign Responsibilities Using RACI and On-Call Schedules

### 5.1. Operational Roles

A model can start with the following roles:

- **Service Owner:** ultimately accountable for service quality, service targets, and ensuring adequate operational staffing.
- **Platform/Cloud Operations:** operates OCI resources, observability tools, and management access paths within assigned scope.
- **Application Team:** owns source code, application configuration, deployments, and business behavior.
- **DBA/Data Operations:** owns database operations and data recovery within the organization's scope.
- **Security/IAM:** manages identity controls, access, and handles security issues.
- **Incident Commander (IC):** coordinates the incident, prioritizes actions, manages concurrent changes, and organizes status updates.

One person may hold multiple roles in a small team. Even then, clearly record which responsibility they hold and which independent verification mechanism applies to critical operations.

### 5.2. Sample RACI Matrix

RACI consists of **R — Responsible**: the person who executes; **A — Accountable**: the person ultimately accountable for the deliverable; **C — Consulted**: those consulted; **I — Informed**: those informed.

Each row should have exactly one A. The notation A/R means the same role is both ultimately accountable and executes the work.

| Deliverable | Service Owner | Platform | Application | DBA | Security/IAM | IC |
| --- | --- | --- | --- | --- | --- | --- |
| Maintain service profile and runbook catalog | A | R | C | C | C | I |
| Write and test Load Balancer runbook | A | R | C | I | C | I |
| Maintain application rollback runbook | A | C | R | C | C | I |
| Execute and test database recovery | A | C | C | R | C | I |
| Approve emergency access design | C | R | C | C | A | I |
| Activate coordination during a major incident | I | R | C | C | C | A |
| Execute authorized application rollback | I | C | A/R | C | I | C |
| Execute authorized network change | I | A/R | C | I | C | C |
| Publish internal incident status updates | C | C | C | C | C | A/R |
| Accept service recovery outcome | A | R | R | C | C | C |

This matrix is an example of work organization, not an IAM policy set. Each row involving a change must also be linked to corresponding operational permissions and approval mechanisms.

If investigation shows signs of intrusion, a separate security incident process must be triggered with a pre-defined commander and decision authority. Avoid letting routine recovery runbooks inadvertently destroy necessary evidence.

### 5.3. Turning Roles into Reachable People

A cell reading "Platform: R" does not guarantee someone will respond at midnight. Every critical deliverable must have:

- Primary and backup on-call schedules, including time zones, holidays, and shift handoff times.
- Tested paging channels and an acknowledgment method.
- Escalation timeouts when there is no response.
- Handover rules to specialist teams and confirmation criteria for acceptance.
- Management escalation contacts when no team accepts responsibility.

Reference a maintained on-call schedule rather than copying individual names into multiple runbooks. The current handler retains coordination responsibility until the next recipient confirms; merely sending a message does not complete a handover.

## 6. Impact Classification and Escalation Design

Severity levels must be based on impact to the service, data, and customers. A single resource's state is only one input for assessing impact.

| Illustrative Internal Level | Indicators | Response Organization |
| --- | --- | --- |
| SEV1 | Critical business flow is down broadly, or there is severe risk to data | Page primary on-call and IC immediately, mobilize appropriate specialist teams |
| SEV2 | Service is significantly degraded, a group of users is impacted, or redundancy capacity is sharply reduced | On-call team handles, IC participates per internal process |
| SEV3 | Localized fault, workaround available, and limited impact | Owning team handles via time-bound queue |
| SEV4 | Improvement work or alerts with no immediate impact | Plan and track until completion |

One failing instance while the service retains sufficient serving capacity may have a different severity than all backends losing health simultaneously. Conversely, losing a standby replica may still require high priority even without user-facing errors.

Example timeline policy for a SEV1:

- At T0: open incident record, page primary on-call, begin assigning IC.
- After 5 minutes without acknowledgment: page backup on-call.
- After 10 minutes still without an assignee: escalate to on-call manager.
- After 15 minutes without identifying a safe recovery path: IC gathers specialists and evaluates opening an Oracle Support request.
- During resolution: internal updates every 15 minutes or whenever significant changes occur.

These milestones are hypothetical operational targets of the organization, not Oracle SLAs or response commitments. When there is a risk of data loss or a security issue, escalate immediately according to that condition without waiting for routine timers to expire.

Distinguish between time to **acknowledge**, **begin mitigation**, **mitigate impact**, and **fully recover**. A team may acknowledge very quickly yet still need specialist support to recover.

## 7. Standard Structure of a Runbook

### 7.1. Identification and Entry Conditions

Each runbook should have a short identification block at the top:

| Field | Meaning |
| --- | --- |
| ID and name | Stable identifier to link from alarms or incident tickets |
| Version | Document version and tested tool scope |
| Owner | Team maintaining the document and ultimately accountable person |
| Applicable scope | Service, environment, resources, and architecture type |
| Trigger conditions | Which signals allow starting, and what must be verified first |
| Exclusions | When to switch to another runbook or team |
| Required permissions | Read permissions, change permissions, access paths, and approval authority |
| Data sources | Service profile, dashboards, logs, pipelines, desired configuration |
| Most recent test | Date, environment, results, and known limitations |

Do not include passwords, private keys, wallets, or tokens in documentation. Only instruct how to obtain credentials through the organization's approved identity or secrets management mechanism.

### 7.2. Every Step Must Have an Execution Contract

A step can be written using the following template:

~~~text
Step: 04 - Read backend set health
Executor: On-call Platform engineer
Inputs: Verified region, Load Balancer OCID, backend set name
Permissions: Corresponding API read permissions within resource scope
Action: Run the listed read commands
Observed output: Overall status and unhealthy backends
Evidence: UTC timestamp, output with sensitive data redacted
Next branches:
  - Abnormal health: inspect backend details and recent changes
  - Normal health: continue investigating errors at the application layer
  - Unable to read: verify region, identity, and permissions; do not guess status
Timebox: Initial assessment within 3 minutes, then update IC if blocked
Stop condition: Resource does not match profile or insufficient permissions
Rollback: Not applicable, as this is a read-only operation
~~~

The three-minute mark here is an organizational timebox for evaluating the step, not an OCI CLI default timeout.

For steps that make changes, also include: pre-change state, approver, impact scope, safe execution conditions, wait time, how to handle indeterminate results, and how to revert to the prior state.

"Retries" must be bounded. If a change request times out, first read the status of the resource or related work request to determine whether the previous request was already applied; avoid blind retries.

## 8. Connecting Monitoring to Runbooks and Responders

An alert handling pipeline can be designed as follows:

~~~mermaid
flowchart TD
    A["Configured metric or transaction check"] --> B["OCI Monitoring alarm"]
    B --> C["OCI Notifications topic"]
    C --> D["On-call and incident ticket integration"]
    D --> E["On-call responder acknowledges receipt"]
    E --> F["Verify impact and select runbook"]
    F --> G{"Sufficient evidence and permissions?"}
    G -->|Yes| H["Execute authorized branch"]
    G -->|No| I["Escalate with evidence"]
    H --> J["Verify recovery and hand over"]
    I --> F
~~~

OCI Monitoring provides metrics and alarms; the alarm's notification destination must be configured. Connecting to on-call schedules or incident management systems requires the organization's corresponding integration, testing subscriptions, and confirming recipients. Do not assume that creating an alarm automatically creates incident tickets or assigns an on-call responder. [Oracle: Overview of Monitoring](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Concepts/monitoringoverview.htm), [Oracle: Example Alarm Messages](https://docs.oracle.com/en-us/iaas/Content/Monitoring/alarm-message-examples.htm).

Each notification should provide enough context to select the right procedure:

- Relevant service, environment, region, and compartment.
- Alarm OCID, timestamp, state, and triggering resource or metric stream.
- Description of the impact to verify.
- Owning team, runbook link, dashboard, and where to open the incident record.

Only use fields or dimensions that actually exist in the data; enrich with service profile information at the integration layer if needed. When an alarm groups multiple metric streams, identify all affected resources before taking action. How notifications are grouped and what fields appear depend on the alarm configuration. [Oracle: Alarm Message Format](https://docs.oracle.com/en-us/iaas/Content/Monitoring/alarm-message-format.htm).

Alarm severity labels and internal SEV levels require a mapping rule. An alarm with CRITICAL severity alone is not enough to automatically classify every case as SEV1.

To reduce duplicate alerts, the receiving system should correlate events belonging to the same incident and preserve the timeline. For missing-data alerts, distinguish between a workload not emitting metrics and a healthy workload; metrics disappearing does not by itself prove recovery.

## 9. Illustrative Runbook: Order API Failing Behind OCI Load Balancer

### 9.1. Service Scope and Structure

The hypothetical service has an OCI Load Balancer receiving HTTPS and forwarding to two Java application backends on Compute. The application connects to an Oracle database service over a private network.

| Attribute | Illustrative Value |
| --- | --- |
| Runbook | RB-OCI-ORDER-HTTP-001 |
| Name | Diagnosing HTTP 5xx and abnormal backend health |
| Example version | 1.0, requires test results before production use |
| Owner | Platform, with Service Owner ultimately accountable |
| Environment | Production, compartment ProdApps, a defined region |
| Coordinating teams | Application; Network, DBA, and Security when evidence points to their scope |
| Trigger | HTTP 5xx rate above 5% for 5 minutes with at least 100 requests/minute, or loss of specified backend redundancy |
| Action limits | Collect evidence; restore configuration or roll back via authorized process |
| Exclusions | Signs of intrusion, suspected data loss, database failover request, or region switchover |

The 5xx signal and minimum traffic threshold must come from a defined measurement source with consistent scope and calculation. This is an illustrative design condition, not an MQL expression that can be copied directly into every tenancy.

This runbook applies to **OCI Load Balancer**, using the **oci lb** command group. If the actual resource is a Network Load Balancer or another component, stop and select the appropriate document.

### 9.2. Step 1 — Acknowledge and Confirm Impact

**Executor:** primary on-call; IC coordinates if impact level requires it.

1. Open or claim the incident record, recording the incident ID and start time in UTC.
2. Confirm the service, environment, region, and resource from the alarm against the service profile.
3. Check a user-facing signal: external probe, success rate, or an authorized synthetic transaction.
4. Record affected user groups, endpoints, and business flows.
5. Cross-check deployments, network changes, or maintenance near the time of occurrence.

If the alarm is delayed or the issue has self-resolved, still save evidence to determine whether it was a transient alert, a measurement error, or a real outage. If concurrent changes must be halted, the IC enforces this under agreed coordination authority and records the freeze scope.

**Output:** an evidence-backed impact description, a clear coordinator, and a list of related changes. Do not restart or change configurations in this step.

### 9.3. Step 2 — Verify Resources and Read Status

**Executor:** Platform with appropriate read permissions.

The commands below are for **Bash**, such as an admin host or OCI Cloud Shell with authentication configured. The operator must replace illustrative values, verify that the profile points to the right identity and tenancy, and cross-check the region and OCID against the service profile. The profile in the example is a pre-configured setup, not created by these commands.

~~~bash
RUNBOOK_PROFILE='OPS_READONLY'
RUNBOOK_REGION='ap-singapore-1'
RUNBOOK_LB_OCID='REPLACE_WITH_VERIFIED_LOAD_BALANCER_OCID'
RUNBOOK_BACKEND_SET='orders-backend-set'

date -u '+%Y-%m-%dT%H:%M:%SZ'

oci lb load-balancer get --load-balancer-id "$RUNBOOK_LB_OCID" --region "$RUNBOOK_REGION" --profile "$RUNBOOK_PROFILE" --output json

oci lb backend-set get --load-balancer-id "$RUNBOOK_LB_OCID" --backend-set-name "$RUNBOOK_BACKEND_SET" --region "$RUNBOOK_REGION" --profile "$RUNBOOK_PROFILE" --output json

oci lb backend-set-health get --load-balancer-id "$RUNBOOK_LB_OCID" --backend-set-name "$RUNBOOK_BACKEND_SET" --region "$RUNBOOK_REGION" --profile "$RUNBOOK_PROFILE" --output json
~~~

The three commands respectively read the Load Balancer configuration, backend set configuration, and backend set health. Verify the ID, compartment, backends, ports, and health check against the profile before proceeding. [Oracle CLI: Load Balancer Get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/load-balancer/get.html), [Oracle CLI: Backend Set Get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set/get.html), [Oracle CLI: Backend Set Health Get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-set-health/get.html).

To inspect a specific backend, take the exact IP address and port from the configuration just read:

~~~bash
RUNBOOK_BACKEND_NAME='10.20.10.11:8080'

oci lb backend-health get --load-balancer-id "$RUNBOOK_LB_OCID" --backend-set-name "$RUNBOOK_BACKEND_SET" --backend-name "$RUNBOOK_BACKEND_NAME" --region "$RUNBOOK_REGION" --profile "$RUNBOOK_PROFILE" --output json
~~~

The backend-name parameter takes the form of IP address and port; the address in the example must be replaced if it does not match the actual resource. [Oracle CLI: Backend Health Get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/lb/backend-health/get.html).

If a command fails due to permissions or resource not found, record the error code, request ID if present, timestamp, region, and active identity. Re-verify the OCID, compartment, profile, and permissions through the authorized team. Do not infer that backends are down merely because the API cannot be read.

Do not paste full output into public channels. Store required portions in a controlled incident record and redact sensitive information.

### 9.4. Step 3 — Classify Evidence and Route to the Right Team

| Initial Evidence | Next Investigation Path | Technical Lead Team | Actions to Avoid Without Evidence |
| --- | --- | --- | --- |
| All backends fail health immediately after deployment | Listening port, health path, configuration, and application version | Application, Platform supporting | Mass restarts as a guess |
| One backend fails, remaining backend serves | Process, logs, OS resources, connectivity of failing backend | Platform or Application depending on fault layer | Removing the healthy backend from service |
| Multiple backends time out after NSG or route change | Flow from Load Balancer to backends, network rules, and OS firewall | Assigned Network/Platform team | Opening all ports to the Internet |
| Backend health is good but users still see 5xx | Application logs, dependencies, connection pool, per-endpoint errors | Application, page DBA if evidence points to database | Concluding the service is healthy |
| Simultaneous database connection errors across multiple instances | Database service status, network path, connection limits, and recent changes | DBA coordinating with Application | Failing over the database under a Load Balancer runbook |
| No internal changes, multiple services impacted together | Scope of impact, Oracle service status, and support case | IC with Platform | Claiming Oracle root cause based solely on timing |

Health checks evaluate the configured check condition. OCI Load Balancer can check at the TCP or HTTP level; backends that fail the condition are taken out of traffic rotation and can be restored once they pass again. Therefore, check the exact port, URI, protocol, and expected response code. A successful TCP health check does not fully validate an HTTP business transaction. [Oracle: Health Check Policies for Load Balancers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/load_balancer_health_management.htm).

A test from an admin host is only meaningful for connectivity paths actually permitted from that host. If private backends must be probed, use an authorized management access point and record the test source; do not assume Cloud Shell has connectivity to every private subnet.

### 9.5. Step 4 — Select Mitigation Action

Each mitigation action must have a technical owner, execution authority, and rationale. The IC maintains a shared timeline so teams do not apply two conflicting changes.

**Branch A — Errors appeared after an application deployment**

- Application correlates error onset time with deployment and configuration diffs.
- Identify a known-good version and verify compatibility with the current schema, data, and configuration.
- If rollback has an established process and meets conditions, execute via the approved pipeline; record deployment ID and revision.
- If there is an irreversible migration that cannot be safely rolled back, stop the simple rollback branch and engage DBA along with decision authority.
- Monitor backend health, error rates, and business transactions after each stage.

**Branch B — Proven network or health check misconfiguration**

- The owning team identifies the exact faulty change and the pre-change state.
- Preview the revert scope through the active configuration/IaC workflow.
- Revert only the authorized relevant configuration; verify it does not pull in other pending changes.
- Preserve management paths and verify connectivity after applying.
- If an emergency out-of-band fix is required outside the pipeline, record the drift and assign someone to sync it back to source configuration post-incident.

**Branch C — One instance fails while serving capacity remains**

- Assess load and remaining capacity before isolating the failing backend.
- Verify application requirements for sessions, open connections, and locally stored state.
- Drain or isolate only according to the system's tested procedure.
- Collect necessary logs, then apply the approved instance repair or replacement runbook.
- Return the backend to service after appropriate readiness, health, and canary traffic checks.

**Branch D — No safe action within scope**

- Stop speculative changes.
- Hand over hypotheses, evidence, and actions taken to the next team.
- IC evaluates triggering service-level recovery, DR, or an Oracle Support request.
- Continue monitoring impact and providing status updates while waiting.

Do not use a mitigation branch to bypass security controls or data boundaries. If scaling capacity is an authorized option, specify the maximum increase, quota/capacity checks, time limit, and who is responsible for scaling back down after the incident.

### 9.6. Step 5 — Conditional Rollback and Handling Indeterminate Outcomes

Before every change, record at least:

~~~text
Change ID:
Resource and scope:
Executor / approver:
Selection rationale:
Pre-change state and configuration:
Specific action or pipeline, revision:
Expected result:
Monitoring window:
Stop condition:
Rollback condition and procedure:
Verifier:
~~~

Example stop conditions: error rate increases, remaining healthy backends lose health, data errors appear, or the change affects resources outside scope. The executor notifies the IC and applies the defined revert plan if that plan remains safe.

After an operation times out, re-read the state or monitor the corresponding asynchronous work request before concluding failure. Record "indeterminate outcome" when evidence is insufficient.

For operations such as overwriting data or database failover, reverting may require a separate procedure and simple reversal is not guaranteed. The current runbook must route to the owner of that procedure rather than calling it a generic "undo".

### 9.7. Step 6 — Verify Recovery and Hand Over

Example recovery criteria for the hypothetical service:

1. Authorized synthetic test flows through the actual user endpoint succeed.
2. 5xx rate drops below the illustrative recovery threshold of 1% and stays there for at least 15 minutes, with sufficient traffic to evaluate.
3. Latency and success rate return to acceptable levels per service targets.
4. Healthy backend count and redundancy meet architectural requirements; no remaining backend is overloaded.
5. No abnormal backlog growth or unresolved dependency errors remain.
6. No signs of data inconsistency; all sensitive business checks are confirmed by the application or DBA team.
7. Alarms have returned to the appropriate state and metric sources remain active.

If actual traffic is too low, do not conclude recovery from a zero error rate alone; use approved synthetic checks and note the evidence limitation.

The 15-minute observation window and 1% threshold are examples to provide clear exit criteria. Each service must choose values aligned with its SLO, traffic volume, and failure characteristics.

Distinguish two states:

- **Impact mitigated:** customers can use the service again, but it is still running with reduced redundancy, temporary capacity, or emergency configuration.
- **Fully recovered:** service targets and operational requirements are met, and any remaining follow-up work has clear owners and deadlines.

If running in a degraded state, the Service Owner must accept the temporary state under the organization's governance; maintain monitoring and remediation tickets until redundancy is restored. Before ending the shift, hand over the current revision, temporary changes, silenced alerts, remaining risks, and next actions.

## 10. Link Responsibilities with IAM Permissions and Evidence

### 10.1. Design Permissions Around Required Capabilities

The runbook should describe permissions by actual task, and the IAM team maps them to policies matching the resources and identity mechanisms in use.

| Capability | Who Needs It | Boundary to Define |
| --- | --- | --- |
| Read Load Balancer configuration and health | On-call Platform | Exact resources or compartments requiring support |
| Read metrics and alarms | Diagnostician | Exact metric source and service scope |
| Read application logs and relevant Audit logs | Authorized response team | Data classification, log location, access scope |
| Roll back application | Application or pipeline identity | Only assigned workload and environment |
| Network changes | Authorized Network/Platform team | Assigned VCN, subnet, NSG, or route |
| Database recovery | Authorized DBA | Exact database service and dataset |
| Use emergency access | Designated individual | Granting, logging, revocation, and post-use audit process |

OCI IAM has permission levels with different API scopes. For example, Load Balancer read access must be checked against the service's permission reference and the APIs actually used, rather than granting tenancy-wide admin rights to on-call engineers. [Oracle: Details for Load Balancing](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/lbpolicyreference.htm).

Operations must be tested using the actual on-call role, because testing with an admin account does not prove the role has sufficient permissions. If resources span multiple compartments or another team owns the logs, the runbook must document the coordination path or pre-arranged read access.

Emergency access should have a process to identify the user, record justification, grant or activate via the chosen mechanism, monitor usage, and revoke after completion. Do not assume IAM policies automatically expire unless the organization has implemented such a mechanism.

### 10.2. Evidence Must Link Decisions to Actions

An action log should include:

- Incident ID, UTC timestamp, and executor.
- Identity or role used for the operation, plus target resource.
- Observational data prior to the decision.
- Command or pipeline, revision, and approver if required.
- Request ID, work request ID, or task ID when provided by the service.
- Post-action outcome, next decision, and verifier.

OCI Audit records calls to supported APIs and provides context such as time, operation target, and response. Use Audit to correlate resource changes with the timeline, while collecting application, OS, database, or pipeline logs as needed. Audit does not replace those log sources. [Oracle: Overview of Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm).

Evidence storage must have access controls and retention aligned with organizational policy. Before sending data externally, follow the prescribed classification and sensitive-data redaction process.

## 11. Automate Runbooks in Stages

Automation can be developed in three levels:

| Level | Scope | Conditions for Use |
| --- | --- | --- |
| Automated collection | Fetch health, metrics, changes, and dashboard links | Accurate resource identifiers, appropriate read permissions, protected output data |
| Human-approved remediation | Prepare proposal, owner verifies then triggers | Supporting evidence, scope limits, pre- and post-checks |
| Bounded auto-remediation | Automatically handle a well-understood fault | Strict trigger conditions, safe repeatability, retry caps, and stop mechanisms |

Before automating state-changing operations, design specific controls:

1. **Right target:** verify environment, region, compartment, and OCID; stop if information is missing.
2. **No overlap:** a coordination mechanism prevents multiple processes from modifying the same resource.
3. **Read before write:** confirm the fault and current state still match the hypothesis.
4. **Safe repeatability:** specify whether the operation is idempotent or requires checks to avoid duplicate creation or modification.
5. **Retry limits:** define attempt counts, backoff intervals, and how to handle indeterminate outcomes.
6. **Blast radius limits:** maximum number of resources, capacity increase, and duration of application.
7. **Post-execution verification:** check service quality, not just tool exit codes.
8. **Stop and escalate:** have a recipient when automation fails or encounters an out-of-scope scenario.

The identity running automation must have an owner and task-scoped permissions. Invoking a pipeline does not remove the operations team's accountability for decisions and results.

Do not start with a loop of "if alarm is still FIRING, restart again". That approach can mask the root cause, destroy evidence, and further degrade the service before the failure characteristics are understood.

## 12. Ensure Runbooks Remain Usable During Outages

### 12.1. Availability of Documentation and Tools

Runbooks must remain accessible when a management dependency fails. Evaluate scenarios such as an unavailable identity system, unreachable repository, disrupted management VPN, or documentation hosted solely inside the failing environment.

Solutions depend on the organization, but must define:

- Where an approved copy of documentation can be accessed during an incident.
- How to know which version is in use and the limitations of the backup copy.
- Communication channels if primary chat or paging tools are disrupted.
- Tested and controlled emergency access mechanisms.
- Who updates the backup copy when the runbook changes.

Do not store secrets in offline copies to solve documentation availability.

### 12.2. Cost and Availability in Recovery Actions

Options that scale resources, retain extra copies, or fail over to a standby environment must have explicit operational limits. Before adding them to a runbook, define:

| Decision | Required Agreement |
| --- | --- |
| Scale up capacity | Who decides, maximum scale, how quota and capacity availability are checked |
| Run temporary resources | Owner, purpose, review deadline, and how to scale back down |
| Retain extra logs or snapshots | Investigation purpose, access rights, retention limit, and associated costs |
| Switch to standby system | Trigger conditions, RTO/RPO, dependencies, and risk acceptor |
| Return to primary system | Sync method, data checks, and cutover window |

Do not treat deleting temporary resources as an implicit task for "someone after the incident". Every spawned resource and temporary configuration must have an owner and a due date.

For DR, a successful failover command alone does not prove the application has recovered. The procedure must cover routing, identity, secrets, connectivity, data checks, and failback conditions suitable for the architecture.

## 13. Maintain Runbooks as Part of the Service

### 13.1. Recommended Lifecycle

A runbook should move through internal states: **draft → reviewed → rehearsed → active → needs update → retired**.

The owner tracks document version, reviewer, most recent test, and known limitations. When retiring a runbook, update alarms and service profiles so on-call engineers do not continue accessing outdated docs.

The following changes must trigger a runbook review:

- Moving compartments, regions, or changing resource OCIDs.
- Changing backend sets, ports, health endpoints, NSGs, or routes.
- Changing IAM mechanisms, profiles, pipelines, or deployment tools.
- Upgrading applications, schemas, or changing database products.
- Changing owning teams, on-call schedules, SLOs, RTO, or RPO.
- An execution reveals missing steps, insufficient permissions, or an unsafe rollback.

Periodic review frequency is chosen by the organization based on risk; having a scheduled review does not replace immediate updates when architecture changes.

### 13.2. Drills Must Test Both People and Technology

A drill should be given to someone who did not write the runbook, executed in an appropriate isolated environment. Observers check whether they can locate the right resources, have sufficient permissions, understand branches, and know when to stop.

For the HTTP runbook above, a drill can be structured as:

1. Prepare a test environment with a Load Balancer, two backends, and monitoring.
2. Define scope, duration, cost cap, observers, and how to return the system to normal.
3. Inject a controlled fault on one backend or health configuration within the test scope.
4. Let the on-call engineer receive the alert, acknowledge, and diagnose using the document.
5. Record places where clarification was needed, missing permissions, confusing outputs, and wait times.
6. Restore, fully verify, and tear down test resources according to plan.

Tabletop exercises can be added for scenarios such as no responder available, inaccessible doc repository, denied read APIs, or detected data risk. The goal is to test decision paths and escalation before a real incident occurs.

## 14. Measure Effectiveness and Avoid Common Design Mistakes

### 14.1. Metrics to Track

| Metric | How It Is Used |
| --- | --- |
| Time from signal to acknowledgment | Verifies on-call schedules and paging channels work |
| Time to identify the right owning team | Surfaces gaps in service profiles and RACI |
| Time to mitigation | Evaluates ability to select and execute recovery branches |
| Time to full recovery | Evaluates both service quality and redundancy restoration |
| Rate of execution without asking the author | Detects implicit steps and missing data |
| Rate of rehearsed runbooks still accurate | Tracks practical usability of documentation |
| Number of overdue temporary changes | Surfaces operational debt, risk, and lingering costs |

Each metric must clearly define start and end timestamps. If using terms like MTTA or MTTR, agree on whether they measure acknowledgment, mitigation, repair, or recovery; do not compare numbers when teams use different definitions.

Do not use speed as the sole metric. A fast recovery that skips data checks or leaves emergency permissions active indefinitely still creates risk.

### 14.2. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Writing "Cloud team handles" | No specific person takes ownership | Bind team, primary/backup schedules, and escalation timeout |
| Providing only a list of commands | On-call engineer does not know which branch applies | Add evidence, expected output, stop conditions, and next branches |
| Testing with an admin account | Fails to catch missing permissions on on-call roles | Rehearse using the actual intended identity and scope |
| Hardcoding OCIDs or person names across many docs | Docs quickly go stale after changes | Reference maintained service profiles and on-call schedules |
| Skipping rollback | When a change fails, the engineer must improvise | Define pre-state, limits, and revert plan before acting |
| Treating health checks as full app health | Misses business-logic and dependency errors | Combine health, metrics, and user-facing checks |
| Assuming API timeout means no change happened | Risk of duplicate actions or conflicts | Re-read state or work request before retrying |
| Closing as soon as user errors stop | Leaves redundancy, permissions, and temporary resources unaddressed | Separate impact mitigation from full recovery, assign follow-up items clearly |

After an incident, improvement items need owners and due dates: fixing wrong steps, adding dashboards, tightening permissions, adding tests, or fixing automation. Documentation updates should be tracked to completion like any other engineering change.

## 15. Pre-Production Acceptance Checklist

The Service Owner and relevant teams can use the following checklist to accept a runbook:

- [ ] Problem statement, applicable scope, and exclusions are clear.
- [ ] A service profile exists with verified tenancy, compartment, region, and resources.
- [ ] One person is ultimately accountable for each deliverable in the RACI.
- [ ] Primary on-call, backup on-call, paging channels, and escalation paths have been tested.
- [ ] Required permissions have been tested using the actual role.
- [ ] Every step has inputs, observed outputs, evidence, and next branches.
- [ ] Every change has an approver when needed, blast radius limits, stop conditions, and a recovery plan.
- [ ] Guidance exists for handling API errors, timeouts, missing permissions, or missing evidence.
- [ ] Recovery criteria are based on service quality and data requirements.
- [ ] Mechanisms exist to track emergency permissions, temporary resources, and incurred costs.
- [ ] Contingency plans exist for accessing documentation and communicating when primary tools fail.
- [ ] Rehearsed, limitations recorded, owner assigned, and version update triggers defined.
