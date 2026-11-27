# Separating Infrastructure and Database Maintenance Responsibilities

In the **Exadata and Cloud@Customer** chapter of the **CLOUD_PROVIDERS_ORACLE** module, clearly defining who maintains each layer is essential for operating databases safely. Oracle may manage Exadata hardware and service infrastructure, while the customer still has to decide and manage many tasks involving virtual machines, database software, data, and applications.

Therefore, saying "Oracle operates Exadata" is not enough to plan maintenance. Operations teams must know the exact service model in use, which components are changing, who approves the change, who executes it, and who verifies the outcome. For Cloud@Customer, the responsibilities of the on-site data center team must also be included.

This lesson helps learners:

- Distinguish Exadata infrastructure maintenance from VM environment and database maintenance.
- Build a responsibility matrix across Oracle, OCI administrators, DBAs, application teams, and data center teams.
- Organize maintenance windows with testing, monitoring, access controls, and recovery plans.
- Understand the limits of RAC, Data Guard, backups, and automation during maintenance.

## 1. Identify the Service Model Before Dividing Responsibilities

One responsibility matrix cannot fit every product with "Exadata" in its name. Distinguish at least these three models:

| Model | Operational Characteristics | Maintenance Implications |
| --- | --- | --- |
| Exadata Database Service on Dedicated Infrastructure in OCI | Oracle provides Exadata infrastructure in Oracle data centers; customer administers the database environment within service scope | Oracle maintains infrastructure; customer manages the lifecycle of the database environment under their control using supported features |
| Exadata Database Service on Cloud@Customer | Exadata infrastructure sits in the customer's data center, managed by Oracle under the service model | Preserves the boundary between Oracle-managed infrastructure and customer database environment; adds on-site facility and connectivity responsibilities |
| Autonomous Database on Exadata or Cloud@Customer | Oracle automates and manages additional tasks at the database software layer | Do not apply the Exadata Database Service matrix verbatim; determine what Oracle performs and which maintenance schedule choices the service exposes |

The hands-on portion of this lesson focuses on **Exadata Database Service**, including Cloud@Customer deployments. Autonomous Database is referenced to clarify responsibility differences and must not be treated as the same operational model.

Before executing a real change, cross-check the exact resource type, infrastructure generation, software version, and maintenance features supported by the service. Automation options, schedule adjustment rights, and execution mechanisms can vary across models.

## 2. View the System by Layer

The dependency flow can be represented as follows:

```text
Application, connection pool, business transactions
                    ↓
Database / CDB / PDB / Database Home
                    ↓
Grid Infrastructure, Clusterware, ASM
                    ↓
Guest VMs and operating system inside guest VMs
                    ↓
Exadata infrastructure: servers, storage, virtualization layer, internal network
                    ↓
Data center: power, cooling, rack space, external connectivity
```

This is a dependency diagram for impact analysis, not a detailed architectural specification of every Exadata generation.

### 2.1. Oracle-Managed Infrastructure Layer

Within the service scope, Oracle manages infrastructure components such as Exadata hardware, storage servers, the virtualization layer, and the internal system network. Maintenance may include component replacement and updates to infrastructure software, firmware, or related system components.

The customer tracks notifications, prepares workloads, and coordinates maintenance windows. The customer does not log directly into Oracle-managed infrastructure components to patch or repair them as they would with a self-operated Exadata appliance.

### 2.2. VM and Database Environment Layer

With Exadata Database Service, the customer is responsible for managing the database environment within the scope assigned to them. This scope covers software lifecycle planning, application compatibility, configuration, and many maintenance decisions at the guest VM, Grid Infrastructure, and Database Home layers.

These layers may have service-driven operations, Oracle-provided tooling, or configurable automation. That does not absolve the customer from scheduling, preparing the system, and verifying applications after changes. Conversely, it should not be inferred that DBAs must run manual patching commands on every layer.

Distinguish the **guest VM operating system** from the **host OS / virtualization layer of physical infrastructure servers**. Oracle maintaining physical servers does not prove guest VMs were patched during the same event.

### 2.3. Data and Application Layer

The customer manages data, schemas, application accounts, business authorization, connection settings, and application error handling. A database can be OPEN after maintenance while the application still fails because a connection pool holds stale connections or a driver does not handle session failover.

Therefore, DBAs verify database status while the application team verifies business transactions. Both checks complement each other.

## 3. Separate Accountable Owner, Approver, and Executor

A maintenance task typically involves multiple roles:

| Role | Question to Answer | Example |
| --- | --- | --- |
| Customer-side coordinator | Who ensures the customer's responsibilities are prepared and completed? | DBA lead coordinates the Database Home maintenance cycle |
| Approver | Who accepts the timing, impact, and recovery plan? | Business system owner approves the maintenance window |
| Executor | Who performs the technical change? | Oracle service, Oracle team, or an authorized operator |
| Validator | Who confirms the system is fit to serve traffic? | DBA checks database; app team runs test transactions |

For instance, the customer may configure or request a maintenance schedule through service controls while Oracle executes the infrastructure change. In that case, the customer still prepares applications and runs validation, without becoming the executor of infrastructure patches.

Conversely, having a UI button to update a Database Home does not shift responsibility for checking SQL, driver, and application compatibility onto Oracle.

Every work item needs one clear lead contact. Avoid vague statements like "Oracle and customer are responsible" without specifying who does what and what completion evidence is required.

## 4. Reference Responsibility Matrix

The following matrix applies in principle to **Exadata Database Service**. Service contract terms and actual resource capabilities govern exact execution.

| Item | Oracle's Part | Customer's Part | Evidence to Retain |
| --- | --- | --- | --- |
| Exadata hardware | Maintain, repair, and replace within service scope | Coordinate impact, notify internal teams; support on-site access if needed | Maintenance notices, support cases, completion results |
| Exadata storage, firmware, virtualization, and internal network | Maintain Oracle-managed infrastructure components | Prepare workloads and validate post-maintenance | Task statuses and before/after operational metrics |
| Guest VMs and guest OS | Provide mechanisms, tooling, or automation per service capabilities | Manage lifecycle planning, configuration, and customer-scoped maintenance; coordinate when service-executed | Versions, schedules, precheck results, and task statuses |
| Grid Infrastructure, Clusterware, ASM | Provide supported releases and maintenance mechanisms | Plan, verify compatibility, and coordinate execution per service model | Precheck results and post-maintenance cluster health |
| Database Home and database version | Provide software, patches, and supported update capabilities | Select target path, test, approve, and verify updates | Target version, patch status, and application results |
| Schemas, SQL, data, and business accounts | Assist within service scope during incidents | Administer and protect data; verify business correctness | Change logs, tests, and privilege audits |
| Backup and recovery | Provide capabilities per configuration and service scope | Define policies, monitor outcomes, protect access, and rehearse restores | Backup history, restore drill results, measured RPO/RTO |
| Application availability | Maintain service components within Oracle-managed scope | Architect RAC/Data Guard as needed, configure connections, and test failures | Service transition, reconnect, and test transaction results |
| IAM and resource access | Operate platform IAM mechanisms | Structure compartments, policies, groups, operational roles, and database accounts | Approved policies and layer-appropriate access logs |
| Monitoring and notifications | Expose service-level status and signals | Configure alerts, recipients, on-call rotations, and response runbooks | Alert history and acknowledgment records |
| Cost and capacity | Provide resources and usage data per service | Forecast capacity, manage additional resources, and audit bills | Capacity plans, budgets, and usage decisions |

The matrix must be translated into work items naming real teams or individuals. Generic labels like "DBA" only work when there is a named primary, backup, and clear contact channel.

## 5. Cloud@Customer: On-Premises Hardware, Responsibilities Still Layered

Cloud@Customer places hardware inside the customer's data center. Physical placement introduces on-site coordination, but it does not turn the service into an appliance the customer maintains end-to-end on their own.

### 5.1. What the Customer Must Prepare

Depending on the agreed design and deployment requirements, the customer's data center and network teams handle conditions such as:

- Power, cooling, rack space, and physical access control.
- Customer-network connectivity, routing, name resolution, and required network rules per design.
- Maintaining the management/service connectivity required by the solution so Oracle can operate and support it.
- Procedures allowing technicians physical access, security coordination, and facility incident response.

Exact port assignments, links, and per-device ownership must be taken from the system's implementation record. Do not assume every network device inside the data center is managed by Oracle.

### 5.2. What Should Not Be Changed Unilaterally

Customers do not swap drives, update firmware, modify internal Exadata networking, or alter Oracle-managed infrastructure software themselves. When faults occur, provide evidence and engage Oracle through support procedures.

Likewise, do not arbitrarily block management connections just because applications can still reach the database. Application traffic paths and management paths serve different purposes; losing one can disrupt operations or supportability.

### 5.3. Incident Triage Examples

| Symptom | Initial Triage Lead | Coordination Path |
| --- | --- | --- |
| Data center power loss or cooling anomaly | Customer facilities team | Restore on-site conditions and coordinate with Oracle to inspect the system |
| Service reports Exadata hardware fault | Oracle per service scope | Customer provides business impact and facilitates access if needed |
| Application cannot connect after customer firewall change | Customer network and application teams | Check routes, firewall rules, and DNS; engage Oracle if service-side evidence appears |
| Database errors after schema change | DBA and application team | Isolate data/SQL change; open Oracle support case if needed |
| Management operations fail | OCI/DBA team and Oracle contact | Check IAM, task state, management connectivity, and service health |

"Initial triage lead" is not a root-cause verdict. Operations teams must hand over evidence whenever the fault boundary shifts.

## 6. Two Maintenance Schedules to Coordinate

### 6.1. Infrastructure Maintenance Schedule

This schedule covers Oracle-managed components. The customer should:

1. Monitor notifications and identify affected resources.
2. Check scheduling or adjustment options actually permitted by the service.
3. Evaluate load tolerance when a component temporarily leaves service.
4. Reschedule heavy jobs such as batch runs, data loads, or backups if conflicts arise.
5. Assign validators during and after the maintenance window.

Do not assume every maintenance event can be deferred at customer discretion. Emergency changes or service mandates may follow separate rules.

### 6.2. Database Environment Maintenance Schedule

This covers guest VM OS, Grid Infrastructure, Database Homes, or database version upgrades within customer-coordinated scope.

Each change type carries different compatibility, testing, and recovery requirements. Applying a patch within a release stream does not carry the same impact as upgrading to a new major version.

Generally avoid overlapping an infrastructure maintenance event with a major database software change. If combining them is unavoidable, establish an explicit sequence, success gates between steps, and a single overall coordinator.

Bundling changes solely to reduce the number of windows can make root-cause isolation and recovery much harder when something breaks.

## 7. Rolling Maintenance and Availability Limits

Rolling maintenance processes components sequentially when the change type and configuration support it. This can let the system keep serving while a portion of resources is under maintenance.

However, rolling does not mean every transaction goes unaffected. Evaluate:

- Whether the change actually supports rolling execution or requires a broader outage.
- Whether surviving nodes have enough CPU, memory, I/O capacity, and session headroom.
- Whether database services are configured and relocated appropriately across instances.
- Whether applications handle dropped connections, timeouts, and reconnection.
- Whether long-running transactions can finish before a node is drained for maintenance.

RAC aids availability at the cluster layer, but it does not automatically resolve application logic flaws or data corruption. Data Guard can support recovery and role-transition plans, though it requires separate configuration, monitoring, and testing.

If a standby exists, the update order between primary and standby must follow the supported change type, version, and procedure. Do not apply a blanket "always patch standby first" rule to every situation.

Also distinguish two groups of signals:

- **Control/management plane:** viewing resources, submitting tasks, tracking maintenance schedules and status.
- **Data plane:** applications connecting and executing transactions.

A control-plane error alone is not proof the database stopped serving. Conversely, a UI showing task completion is not proof business transactions are healthy.

## 8. A Practical Maintenance Procedure

### 8.1. Pre-Maintenance: Establish Scope and Entry Criteria

The change ticket should clearly record:

- Service type, target resources, compartment, VM cluster, and related databases.
- Target layer, current version, target version, and dependencies.
- Coordinator, executor, approver, validators, and communication channels.
- Start time, go/no-go decision deadline, and target service restoration window.
- Expected impact, acceptable thresholds, and abort criteria.
- Separate recovery plans for software, configuration, and data.

Then complete preparation checks:

1. Verify cluster health, database state, storage space, and unresolved alerts.
2. Run prechecks supported by service tooling.
3. Test the change in a suitable environment, including application behavior and reconnection.
4. Verify relevant backups, access paths, and restore drill results.
5. Check standby health, apply lag, and role-transition readiness if Data Guard is part of the plan.
6. Capture baseline metrics for latency, throughput, connection errors, and spare capacity.
7. Confirm Oracle and internal schedules do not conflict; staff appropriate on-call coverage.

If the cluster has already lost redundancy or recoverability is uncertain, the coordinator should resolve those conditions before starting a voluntary change.

### 8.2. During Maintenance: Observe and Control Progress

The executor uses the service-supported maintenance workflow and records task IDs or support case numbers. Monitoring tracks both technical progress and application impact.

Do not re-trigger an operation just because the UI responds slowly. First verify whether the prior request was already accepted. Duplicate requests can complicate orchestration.

If a step fails, capture the timestamp, active step, error message, and observed impact. Do not modify Oracle-managed components directly as a quick fix. For customer-scoped tasks as well, verify status and supported recovery workflows before intervening further.

### 8.3. Post-Maintenance: Confirm Service Readiness

Validate in dependency order:

1. **Task:** completion status and any alerts requiring attention.
2. **Cluster/VMs:** expected components are back online, with no nodes or resources in unexpected states.
3. **Database:** instances, databases, PDBs, and related services operate per design.
4. **Software:** versions and patch states match the intended change.
5. **Application:** new connections, read/write transactions, and critical business flows succeed.
6. **Data protection:** backups and standby continue operating within agreed thresholds.
7. **Operations:** muted maintenance alerts are re-enabled and performance metrics stay within acceptable bounds.

Close the ticket only with sufficient evidence across the change scope. A single successful connection test does not replace validating business transactions.

## 9. Example: Maintaining an ERP System on Cloud@Customer

Suppose an enterprise runs ERP on Exadata Database Service on Cloud@Customer with a two-node RAC cluster and a standby for recovery. Oracle announces weekend infrastructure maintenance. The DBA team also wants to apply a database software update.

### 9.1. Dividing the Work

| Team | Pre-Window Work | During/Post-Window Work |
| --- | --- | --- |
| Oracle | Announce scope and coordinate service-scoped infrastructure work | Execute infrastructure maintenance and report status per service workflow |
| DBA | Check RAC, services, backups, standby, and spare load capacity | Monitor database, verify health, and provide evidence |
| Application team | Test ERP reconnects and transactions; adjust batch jobs | Run test business flows and monitor application errors |
| OCI/IAM team | Verify operational permissions and notification channels | Support access, track tasks, and review admin logs |
| Data center/network team | Check power, cooling, links, and network freeze windows | Maintain site conditions and coordinate physical access if needed |
| ERP system owner | Approve window, impact bounds, and abort criteria | Sign off on returning to service based on technical and business results |

### 9.2. Decision on the Two Changes

Operations reserves a dedicated window for infrastructure maintenance. Only after confirming system stability do they execute the Database Home update in a separate window under a tested plan.

During the infrastructure window, DBAs do not opportunistically apply extra database patches. If scope must change, the coordinator updates the plan and re-confirms entry criteria.

### 9.3. Set Measurable Criteria

The enterprise can set internal thresholds, such as:

- Zero loss of committed transactions.
- Connection error rates and transaction latency stay within tested limits.
- Load with only one node serving leaves sufficient headroom for expected traffic.
- If the standby is part of the recovery plan, its status and lag meet chosen targets.

Thresholds must attach to concrete measurements and observation windows for the system. These are internal example criteria, not Oracle SLA commitments or default RPO/RTO guarantees.

## 10. Backups, Rollback, and Role Transitions Solve Different Problems

Three concepts frequently conflated in change tickets:

| Mechanism | Primary Purpose | What Must Not Be Assumed |
| --- | --- | --- |
| Software change rollback | Return to a prior software/configuration state via supported means | Every patch or upgrade can roll back quickly without affecting data |
| Restore from backup | Recover data or database to an appropriate state | One database backup contains every VM, Grid Infrastructure, and software component needed to recover |
| Switchover/failover | Shift serving role to another system per design | Every standby is valid, independent, and ready to absorb load at any moment |

A successful backup still must be evaluated for timestamp, completeness, access permissions, and ability to restore within required time. If recovery needs encryption keys, passwords, or off-database configurations, the plan must ensure those artifacts are accessible when needed.

RPO is the target for acceptable data loss, often expressed in time; RTO is the target time to restore service capability. Confirming these targets requires measuring detection, decision, recovery execution, and application validation end-to-end.

With Cloud@Customer, also account for facility failures at the equipment site. A standby inside the same fault domain may not meet recovery objectives when the entire site is affected.

## 11. Permissions, Logging, and Alerting

### 11.1. Least-Privilege Separation by Role

In OCI, compartments and IAM organize resource scope and operational permissions. Roles can be separated as needed:

- A group that only views status and receives maintenance notices.
- A group authorized to manage schedules or initiate operations on required resources.
- An IAM admin group independent from daily maintenance work when organizational policy requires it.
- Automation accounts or principals granted scoped permissions for the exact target resources.

OCI permissions do not replace OS or database privileges. Someone able to view a VM cluster in OCI does not automatically have privileges to run administrative SQL inside the database.

For remote support access on Cloud@Customer, follow the approval and auditing controls supported by the service deployment. Do not assume every support session requires the exact same approval step or uses the same access mechanism.

### 11.2. Match Logs to the Right Layer

OCI audit logs trace resource management actions within recorded scope. OS logs, database logs, application logs, and support records answer different questions.

A solid maintenance record correlates timestamp, initiator, resource, task ID, errors, and validation outcomes. Do not rely on one log type to draw conclusions about every activity in the system.

### 11.3. Assign Alert Owners and Actions

| Signal | Primary Recipient | Expected Action |
| --- | --- | --- |
| Infrastructure maintenance schedule notice | OCI contact and maintenance coordinator | Cross-check business calendar and prepare resources |
| Maintenance task failed or unexpectedly prolonged | Executor and on-call engineer | Check status, capture evidence, coordinate support |
| Connection drops or transaction errors | Application team and DBA | Scope impact, inspect database/service/connectivity |
| Backup failure or standby lag | DBA and recovery owner | Restore data protection posture and reassess continuing maintenance |
| On-site power, cooling, or network anomaly | Data center and network teams | Remediate site conditions and coordinate with Oracle based on impact |

If certain alerts are silenced during a maintenance window, define an expiration time and an owner to re-enable them. Retain visibility into incidents beyond the planned scope.

## 12. Controlled Automation

Automation fits status collection, precondition checks, reminders, and evidence aggregation well. Mutating actions must use the supported APIs, tools, or service workflows for the target resource.

The following example is an **internal planning record template**, not an input format for the OCI CLI or an Oracle API:

```yaml
maintenance_plan:
  change_id: CHG-ERP-042
  service_model: Exadata Database Service on Cloud@Customer
  target_layer: infrastructure
  customer_coordinator: dba-lead
  technical_executor: Oracle
  business_approver: erp-owner
  validators:
    - dba-on-call
    - erp-on-call
  prerequisites:
    - cluster_health_accepted
    - backup_recovery_evidence_accepted
    - application_reconnect_test_passed
    - site_and_network_ready
  stop_conditions:
    - unexpected_loss_of_redundancy
    - business_error_threshold_exceeded
  completion_evidence:
    - maintenance_task_result
    - database_health_result
    - erp_transaction_test_result
```

An orchestration system can check the record's preconditions before permitting the next step. However, `technical_executor: Oracle` merely documents responsibility in the plan; it does not submit a maintenance request to Oracle.

If mutating calls are automated, store the task ID, poll status before retrying, and handle cases where the request was accepted but the response connection dropped. Credentials must be managed through secure mechanisms—never write passwords into planning records or logs.

### 12.1. Post-Maintenance Database Check Example

DBAs can run the following read-only queries with an account granted read access to the required views:

```sql
-- Observe instances currently visible in the cluster.
SELECT inst_id, instance_name, status, database_status, version
FROM gv$instance
ORDER BY inst_id;

-- Confirm role and open mode of the connected database.
SELECT db_unique_name, database_role, open_mode
FROM v$database;

-- Observe SQL patch application history.
SELECT patch_id, action, status, action_time, description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

These queries provide only partial evidence:

- Compare observed instance count against expected configuration; query output alone does not prove all nodes are present.
- The `version` column in `gv$instance` does not replace verifying full software inventory and patch levels.
- `dba_registry_sqlpatch` reflects SQL patch history within the queried scope; it is not an inventory of firmware, OS, or Grid Infrastructure.
- For CDB/PDB, inspect the target container and changed PDBs using appropriate privileges and methods.
- Concluding the system is healthy still requires checking database services, applications, and operational metrics.

Grant only required read privileges; do not grant broad administrative roles just to run health reports.

## 13. Controlling Cost in Maintenance Planning

Maintainability and budget are directly coupled. If a system only has enough capacity when every node is up, a rolling maintenance pass can cause a capacity shortfall.

Planning should account for:

- Reserve capacity to absorb load when part of the system is temporarily offline.
- Test environments and resources required for recovery drills.
- Extra storage space, old Database Homes, or test data retained during the rollback window.
- Standby costs and additional resources under the actual billing model.
- On-call staffing time and business cost if a window runs long.

Do not assume stopping or deleting resources lowers costs identically across all contracts. For Cloud@Customer, evaluate against the purchased service commitments and configuration.

Once the rollback retention period ends, the owner should review temporary resources and clean them up per the approved plan. Do not delete old environments or software the instant an update task reports success.

## 14. Common Misconceptions to Avoid

| Misconception | Accurate Understanding and Action |
| --- | --- |
| "Oracle manages Exadata, so databases are fully patched automatically" | Check each layer separately; Oracle managing infrastructure does not mean the customer environment is patched |
| "Cloud@Customer sits in our server room, so we can repair hardware ourselves" | Respect service boundaries; coordinate with Oracle for Oracle-managed components |
| "With RAC, applications never experience downtime" | Test rolling behavior, capacity headroom, service setup, and reconnect handling |
| "Having backups means any change can roll back" | Define separate recovery methods for software, configuration, and data; measure actual times |
| "UI task succeeded means everything is done" | Verify versions, database health, and business transaction flows |
| "Losing management connectivity means data serving stopped" | Check management paths and data access paths independently |
| "Both are Exadata, so use one runbook for Autonomous and Exadata Database Service" | Tailor runbooks to the exact service model and customer-managed scope |
| "Automation replaces human accountability" | Automation executes steps and gathers evidence; a human still owns decisions and outcomes |

## 15. Maintenance Shift Handover Checklist

Before taking over a shift, the operator should be able to answer:

- [ ] Which service model is in use, and which layer is changing?
- [ ] Who coordinates, approves, executes, and validates each part?
- [ ] Have Oracle notices been cross-checked against business calendars and other changes?
- [ ] Do the cluster, VMs, database, and applications meet entry criteria?
- [ ] Have degraded-mode capacity and client reconnection behavior been verified?
- [ ] Is there usable evidence for backups and recovery plans?
- [ ] If a standby exists, have its status and usage plan been confirmed?
- [ ] For Cloud@Customer, are power, cooling, networking, and on-site contacts ready?
- [ ] Have operational permissions, alerts, and support channels been verified?
- [ ] Are abort thresholds, decision checkpoints, and layer-specific rollback paths defined?
- [ ] Is the evidence required to close the change ticket defined?

The target outcome is an enforceable responsibility boundary: Oracle executes infrastructure work within the service's managed scope; the customer organizes the database environment lifecycle, data protection, and application validation. With Cloud@Customer, the customer also maintains on-site data center conditions and connectivity within their scope. Every maintenance window must connect these pieces into a plan with clear owners, entry criteria, and completion criteria.
