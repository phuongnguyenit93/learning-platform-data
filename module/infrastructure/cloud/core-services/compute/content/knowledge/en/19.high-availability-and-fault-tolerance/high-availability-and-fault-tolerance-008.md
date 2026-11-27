# Controlled Fault Testing and Verifying Recovery Capability

An architecture designed for high availability can still fail during a real incident. Health checks may detect faults inaccurately, autoscaling may fail to provision enough machines, replicas may lag, applications may lose connectivity when shifting zones, or recovery procedures may depend on a single account and a single operator. Reading design docs is not enough to know how a system reacts when a component disappears.

**Controlled fault testing** proactively induces a bounded failure scenario to observe how workloads detect, isolate, shift load, recover, and preserve data. **Fault injection** is the technique of introducing a fault into a specific component or path. **Chaos engineering** expands this approach into a testing discipline built on hypotheses, bounded scope, observability, risk controls, and continuous learning.

Within **CLOUD_CORE_SERVICES_COMPUTE**, testing may involve stopping a VM, disconnecting an instance, adding latency, simulating storage faults, making a dependency temporarily unavailable, or verifying recovery when a zone is isolated. Results must prove that the system preserves SLOs, recovers within RTO, bounds data loss within RPO, and returns to a steady state once the fault ends.

## 1. Why Is Fault Testing Necessary?

High availability (HA) and fault tolerance are often described using redundant components: multiple VMs, load balancers, database replicas, multiple zones, autoscaling, and backups. Yet the mere presence of those components does not prove failover works properly.

Certain failure modes surface only when faults occur:

- The load balancer keeps routing requests to an incapacitated instance because health checks are too shallow.
- The autoscaler detects missing capacity, yet the subnet runs out of IP addresses and cannot launch replacement VMs.
- A replica holds data, yet the application fails to switch connections to it.
- Unbounded retries amplify load on an already failing dependency.
- A brief disconnect causes messages to be processed twice.
- A new VM launches, yet bootstrapping lacks permission to read secrets and never becomes healthy.
- Backups complete, yet cannot be restored within the required timeframe.
- Failover to another zone works, yet failback overwrites newly written data.

Controlled testing turns assumptions into measurable evidence. It exposes gaps between intended design and actual behavior before an unintended outage hits.

## 2. Distinguishing Fault Injection, Chaos Engineering, and DR Drills

These activities are related yet differ in goal and scope:

| Activity | Goal | Example |
| --- | --- | --- |
| Fault injection | Induce a specific fault to test a component's reaction | Stop a VM or inject network latency |
| Chaos experiment | Test a hypothesis about system behavior under a bounded fault | Lose one instance while the API maintains its SLO |
| Load/stress test | Measure load-handling capacity and find capacity limits | Ramp requests/second up to a defined threshold |
| Failover test | Verify switching to a backup component | Promote a database replica from primary |
| Disaster recovery (DR) drill | Practice restoring service/data after a major disaster | Recover workloads into a standby region |
| Game day | Practice coordination across engineering, operations, and responders | Simulate an outage and execute runbooks |

A single exercise may combine techniques, provided the question under test is explicitly stated. For instance, stopping a VM in a group is fault injection; verifying the whole service keeps its SLO and the group self-heals is a chaos experiment; restoring the full service from backups in another region is a DR drill.

## 3. Defining Hypotheses and Steady State

A good experiment begins with a measurable hypothesis—not with "let's break the system to see what happens."

### 3.1. Writing a Hypothesis

A hypothesis should state:

- The fault event being induced.
- How the system is expected to respond.
- Which metrics prove the service remains operational.
- Desired detection and recovery times.
- Maximum acceptable impact.

Example:

> When one VM in the API group is stopped abruptly, the load balancer will remove that VM from routing, the remaining VMs will keep serving test load with an error rate below the defined threshold, the managed group will launch a replacement member, and healthy capacity will return to target within 5 minutes.

This is a test hypothesis, not a default guarantee from every cloud provider. Teams must set thresholds based on actual SLOs and architecture.

### 3.2. Defining Steady State

**Steady state** is the normal operating condition the system must maintain. Do not use CPU utilization alone as a proxy for stability.

Signals can include:

- Request success rate and error rate.
- p50, p95, and p99 latency.
- Throughput or requests/second.
- Healthy backend count and ready instance count.
- Queue depth and consumer lag.
- Database connections, query latency, and replication lag.
- Transaction completion rate and data integrity.
- Retry rates, timeouts, and open circuit breakers.

Select a small set of critical signals that can be measured continuously and reflect user experience. If a service still returns HTTP 200 while corrupting data or dropping transactions, steady state has not been maintained.

### 3.3. Setting Success Thresholds

An experiment needs explicit pass criteria, for example:

| Signal | Illustrative Criterion |
| --- | --- |
| Request success rate | No lower than 99.5% during the test window |
| p95 latency | Does not exceed 500 ms for more than 2 minutes |
| Healthy backends | Always retains at least 3 instances |
| Detection time | Fault detected within 30 seconds |
| Replacement time | Replacement instance healthy within 5 minutes |
| Data integrity | Zero lost or duplicated committed transactions |

These numbers illustrate how to express criteria. Use your system's real SLOs, RTO, RPO, and load levels to set official thresholds.

## 4. Principles for Designing Safe Experiments

Fault injection can cause real disruption. Limit impact and ensure a reliable way to halt the test.

### 4.1. Start Small

Progress through environments in increasing order:

1. Local or sandbox environment.
2. Test/staging environment closely mirroring production.
3. One explicitly targeted instance or small group.
4. A small traffic slice or test user cohort.
5. Controlled production, only with evidence from prior steps and formal organizational approval.

Never start by shutting down an entire region or disrupting a shared dependency used by many systems.

### 4.2. Limit Blast Radius

Blast radius is the scope of resources or users potentially impacted. Limit it by:

- Selecting targets via explicit tags/labels, instance IDs, or dedicated namespaces.
- Capping affected instance counts, traffic percentages, or worker counts.
- Using dedicated test accounts/projects/subscriptions and test VPCs/VNets.
- Setting fault durations with automatic expiration.
- Excluding shared out-of-scope resources.
- Blocking experiments when healthy capacity falls below a safe threshold.

Validate target selectors before executing. A faulty tag filter can select the entire fleet instead of a single test VM.

### 4.3. Guardrails and Abort Conditions

Guardrails are limits that keep an experiment from exceeding its scope. Examples:

- Abort if the error rate exceeds the threshold across two consecutive windows.
- Abort if healthy backends drop below minimum capacity.
- Abort if database replication lag exceeds limits.
- Abort if queue depth climbs continuously or consumer lag fails to drain.
- Abort if latency breaches SLOs or impacts users outside the test cohort.
- Abort if monitoring/alerting stops working.

Abort conditions must be defined beforehand with a designated person or automated stop trigger. Never wait until the entire system goes down to decide to stop.

### 4.4. Prepare Recovery Before Injecting Faults

Before running a test:

- Assign accountable owners and communication channels.
- Verify backups/snapshots and restore readiness if the test could affect data.
- Prepare rollback or experiment-stop commands and procedures.
- Ensure out-of-band access if networking will be impaired.
- Verify monitoring, logging, tracing, and alert routing.
- Confirm spare capacity and quotas are sufficient for recovery.
- Notify relevant operations teams and test stakeholders.
- Record baselines and the start timestamp.

Never test against production data by deleting or mutating live records. Use synthetic data, test tenants, or appropriate isolation mechanisms.

## 5. Lifecycle of a Chaos Experiment

~~~mermaid
flowchart TD
    A["Select risk and hypothesis"] --> B["Measure steady state and set SLO"]
    B --> C["Select target, blast radius, and duration"]
    C --> D["Check guardrails, rollback, and backups"]
    D --> E{"Pre-check passed?"}
    E -- "No" --> F["Cancel or reschedule"]
    E -- "Yes" --> G["Inject controlled fault"]
    G --> H["Observe metrics, logs, traces, and alerts"]
    H --> I{"Abort threshold breached?"}
    I -- "Yes" --> J["Stop fault and recover"]
    I -- "No" --> K["End after scheduled duration"]
    J --> L["Verify recovery and data integrity"]
    K --> L
    L --> M["Compare against hypothesis and record lessons"]
    M --> N["Create improvement actions and retest"]
~~~

An experiment cycle should cover all of the following steps:

1. Pick a failure mode meaningful to the architecture.
2. Write the hypothesis and steady-state metrics.
3. Define targets and impact bounds.
4. Run pre-checks.
5. Start fault injection and record timestamps.
6. Observe the system over the defined window.
7. Stop the fault or trigger abort.
8. Verify full system recovery.
9. Compare results against the hypothesis.
10. Record findings, owners, deadlines, and retest after fixes.

## 6. Fault Categories to Test in Compute Workloads

You do not need to test every fault type at once. Select scenarios based on risk, architecture, and incident history.

| Fault Category | Simulated Fault | Capabilities to Verify |
| --- | --- | --- |
| Compute/VM | Stop or terminate a VM | Load balancer drops failed backend; group replaces machine |
| CPU | Induce bounded CPU contention | Queuing, latency, autoscaling, and throttling |
| Memory | Increase memory pressure on a test target | OOM handling, restarts, and capacity |
| Network | Inject latency, packet loss, or partitions | Timeouts, retries, circuit breakers, and failover |
| DNS | Fail or delay DNS queries in a test environment | DNS caching, retries, and fallback endpoints |
| Storage | Simulate slow I/O, read-only mounts, or lost mounts | Timeouts, retries, integrity, and recovery |
| Dependency | Make database/cache/queue temporarily unavailable | Degraded mode, fallbacks, and connection recovery |
| Zone | Isolate traffic or capacity of one test zone | Traffic redistribution and surviving capacity |
| Identity | Expire test credentials or remove permissions | Refresh, retries, alerts, and least privilege |
| Process | Kill a process or service | Supervisor, restart policies, and readiness |

### 6.1. Losing One VM in a Managed Group

This is the baseline test for stateless fleets:

- Select a VM holding no unique state.
- Confirm the group retains enough healthy capacity after losing one member.
- Stop or terminate the chosen test VM via an approved mechanism.
- Monitor health checks and when the backend is pulled from traffic.
- Observe the group launching a new VM from the active template.
- Verify the new VM completes bootstrapping, identity setup, and readiness.
- Confirm healthy capacity returns to target.

Success is not merely "a new VM was created." Check whether requests failed, sessions dropped, queues processed duplicates, and the replacement launched from the exact template revision.

### 6.2. CPU Contention

CPU contention simulates a process consuming heavy CPU and starving application threads. It can raise request queuing, latency, and processing times.

On an isolated test VM, you can use a time-bounded stress tool:

~~~bash
# Run only on an isolated test VM
stress-ng --cpu 2 --timeout 60s
~~~

Monitor CPU utilization, run queues, steal time if exposed, request latency, error rates, and autoscaling signals. Never run this command on shared hosts or production VMs outside an approved test scope. Bound worker counts and duration to actual capacity.

### 6.3. Network Latency and Packet Loss

Network faults can be simulated with network emulation tools on a test machine's interface, such as Linux traffic control:

~~~bash
# Illustrative example on a test VM interface
sudo tc qdisc add dev eth0 root netem delay 100ms 20ms loss 1%

# Remove the rule after testing
sudo tc qdisc del dev eth0 root
~~~

This rule affects traffic across the selected interface and can sever management connectivity. Run only in an isolated environment, verify the right interface, and keep out-of-band console access or an auto-cleanup timer ready. For shared environments, prefer chaos tooling with explicit selectors and automatic expiration.

When testing network faults, observe:

- Do timeouts and retries multiply?
- Do retries use backoff and jitter?
- Do connection pools recover once networking returns?
- Do circuit breakers open and close at the right times?
- Does request idempotency prevent duplicate actions?
- Do DNS caches hold stale addresses too long?

### 6.4. Storage Latency or Lost Mounts

Storage faults must be tested on volumes/datasets without critical production data. Simulate I/O latency using appropriate test tooling or platform-supported fault injection capabilities.

Questions to verify:

- Does the application time out when storage responds slowly?
- Do queues or thread pools fill up with blocked I/O?
- Do retries pile extra load onto a struggling volume?
- When a mount disappears, does the app stop writing rather than silently writing into a directory on the root disk?
- After the volume returns, is data consistent and the filesystem cleanly mounted?

Never detach an actively written production volume to test faults. Use snapshots/clones or test environments with synthetic data.

### 6.5. Dependency Unavailability

A compute service typically depends on databases, caches, message brokers, DNS, identity providers, or secret managers. Test each dependency individually:

- Block connections to a test endpoint for a short window.
- Constrain connection pools to observe queuing and timeouts.
- Make the cache unavailable to verify fallbacks and database load.
- Pause consumers on a test queue to measure backlog growth and catch-up speed.
- Expire test tokens to verify refresh flows.

Configure finite timeouts and retry budgets. An unavailable dependency must never cause the application to spawn unbounded threads or retry storms.

### 6.6. Zone Failure

You do not need to take down an actual availability zone to test fault tolerance. Simulate it by:

- Removing backends belonging to one zone from the load balancer.
- Throttling or stopping test instances in that zone.
- Blocking traffic between test components in a defined direction.
- Running capacity scenarios limited strictly to the remaining zones.

Then verify that the load balancer shifts traffic, the group maintains sufficient capacity, databases/caches retain usable endpoints, and the system has no hidden single dependency in the isolated zone.

## 7. Verifying Recovery Capability

Recovery does not mean simply stopping fault injection. Confirm every layer returns to normal with no lingering side effects.

### 7.1. Detection and Isolation

Verify:

- Did the system detect the fault?
- Did alerts reach the right responders and channels?
- Did health checks remove unhealthy backends from traffic?
- Did circuit breakers stop sending requests to failing dependencies?
- Did autoscalers/auto-healers respond according to policy?

Record the elapsed time from fault onset until detection and isolation of the failing component.

### 7.2. Failover and Continuity

Verify:

- Did traffic shift to healthy components?
- Was surviving capacity sufficient for normal load?
- Were in-flight sessions or requests resumed, retried, or cleanly rejected?
- Did consumers continue processing messages without loss or duplication?
- Did the promoted replica/new primary database accept writes properly?
- Did backup dependencies overload from shifted traffic?

Failover can turn a backup dependency into a hotspot. Observe load across replicas, caches, networks, and surviving zones.

### 7.3. Data Integrity

For write-heavy workloads, build an integrity verification suite:

- Record committed transaction counts before, during, and after the test.
- Use request IDs or idempotency keys to detect duplicates.
- Compare checksums or row counts across source and replicas.
- Inspect uncommitted transactions and in-flight messages.
- Verify event ordering if the system requires strict ordering.
- Confirm new writes are not overwritten during failback.

Never rely solely on HTTP success rates to conclude data is safe. A request can return success while writes remain unreplicated or messages remain unpersisted.

### 7.4. Recovery and Return to Steady State

After the fault ends, verify:

- Test resources are restored or fault rules removed.
- Healthy capacity returns to desired levels.
- Autoscaling does not keep scaling out/in unexpectedly.
- Queue backlogs drain back to normal.
- Caches warm back up if required.
- Database replication lag returns within thresholds.
- Network retries and connection pools stabilize.
- Alerts resolve naturally rather than being manually cleared while faults persist.
- No orphaned VMs, disks, rules, or temporary resources remain incurring charges.

## 8. Measuring RTO, RPO, and Recovery Time

RTO and RPO turn recovery goals into verifiable criteria.

- **RTO (Recovery Time Objective):** maximum outage duration the business accepts before service is restored.
- **RPO (Recovery Point Objective):** maximum acceptable data loss, typically expressed as a time window of data.

For example, a service sets an RTO of 15 minutes and an RPO of 5 minutes. During a zone-loss test, the team measures the time from service impact until service restoration, along with the newest data point recovered. If the service resumes after 7 minutes yet loses 12 minutes of data, RTO passes while RPO fails.

Milestones to record:

| Milestone | Meaning |
| --- | --- |
| T0 | Fault injection starts |
| T1 | Monitoring detects the fault |
| T2 | Failed component isolated from traffic |
| T3 | Failover or replacement begins |
| T4 | Service meets SLO again |
| T5 | Data consistency verified |
| T6 | Entire system returns to steady state |

Depending on goals, recovery time may be measured from T0 to T4 or T6. Document the exact definition in reports so runs remain comparable.

## 9. Metrics and Signals to Monitor

| Category | Metrics |
| --- | --- |
| User experience | Availability, success rate, p95/p99 latency, error rate |
| Compute | Healthy instance count, CPU, memory, restart/replacement count |
| Autoscaling | Desired vs. actual capacity, launch time, scaling events, and cooldowns |
| Network | RTT, packet loss, retransmissions, connection errors, DNS latency |
| Storage | IOPS, throughput, latency, queue depth, I/O errors |
| Database | Connection count, query latency, replication lag, failover state |
| Messaging | Queue depth, consumer lag, redelivery, and duplicate counts |
| Recovery | Detection time, isolation time, failover time, RTO, and RPO |
| Operations | Alert delivery, runbook execution, manual intervention, and cleanup |

Align dashboards to the experiment timeline and annotate fault start/stop markers. This correlates metrics directly with events rather than relying on coarse aggregate charts.

## 10. Practical Example: Losing One VM in an API Group

A stateless API runs on a managed instance group of 4 VMs across 2 zones behind a load balancer. The service has a health endpoint, autoscaling, and centralized logging.

### 10.1. Hypothesis

When one VM is stopped, the load balancer removes it from backends, the remaining three VMs handle test load, the group launches a replacement VM, and healthy capacity returns to 4 within 5 minutes. Error rates stay below test thresholds; transaction data is neither lost nor duplicated.

### 10.2. Pre-Check

1. Pick a test VM from the group and note its instance ID and zone.
2. Confirm no stateful tasks or unique sessions reside on that VM.
3. Confirm the remaining three VMs have sufficient capacity for test load.
4. Check load balancer health, autoscaling, quotas, and subnet IPs.
5. Verify alerts, dashboards, and logs are active.
6. Record baseline metrics over at least one stable interval.
7. Prepare stop-test and rollback steps in case of anomalies.

### 10.3. Execution and Observation

1. Record the start timestamp.
2. Stop the chosen VM using the approved fault-injection action.
3. Watch health checks and when the backend is dropped from routing.
4. Track success rate, latency, healthy backend count, and request distribution.
5. Watch the managed group launch and bootstrap a replacement VM.
6. Verify the new instance uses the right template revision, image, identity, and network.
7. Wait for readiness to pass and confirm the load balancer registers the new instance.
8. Record when healthy capacity returns to 4.

### 10.4. Post-Test Verification

- Reconcile committed transaction counts against source data.
- Check request retries and duplicates.
- Verify the old VM is in its expected state and receives no traffic.
- Confirm no fault rules or test resources remain.
- Measure RTO and replacement duration.
- Verify the group did not launch extra VMs beyond desired capacity.
- Document any deviations from the hypothesis.

If the replacement instance fails to become healthy because a startup script lacks permission to read a secret, the test uncovered a real weakness: auto-healing creates a machine yet fails to restore serving capacity. The next step is fixing identity/bootstrapping, validating the image, and re-running the test.

## 11. Practical Example: Temporary Database Dependency Outage

A compute service calls a database via a connection pool. The team wants to verify the application responds properly when the database temporarily refuses connections.

Hypothesis:

- Requests enforce finite timeouts.
- Retries use exponential backoff and jitter.
- Circuit breakers open once failures cross thresholds.
- The API returns degraded responses or controlled errors.
- Once the database returns, connection pools establish fresh connections and traffic recovers.
- Zero committed transactions are lost and client retries create zero duplicates.

Test steps in a test environment:

1. Create a synthetic dataset and record row counts/checksums.
2. Measure baseline query latency and connection pool metrics.
3. Block the test database endpoint for a bounded duration.
4. Observe thread pools, timeouts, retries, circuit breakers, and API latency.
5. Restore connectivity.
6. Monitor connection pools and query latency returning to normal.
7. Reconcile data and request IDs to check for loss or duplication.

If retries cause a surge in connections and queries the moment the database returns, add retry budgets, jitter, and concurrency limits to prevent a recovery storm.

## 12. Supporting Tools and Platforms

You can use cloud-native services, open-source tools, or dedicated chaos engineering platforms. Choices depend on your environment, required control level, and fault types to simulate.

| Tool / Tool Group | Typical Scope |
| --- | --- |
| AWS Fault Injection Service (FIS) | Fault injection on supported AWS resources with experiment templates and stop conditions |
| Azure Chaos Studio | Fault experiments on supported Azure resources and environments |
| Chaos Mesh | Chaos experiments for Kubernetes workloads such as pods, networking, stress, and other faults |
| Litmus | Policy-driven chaos engineering experiments and workflows for Kubernetes |
| Gremlin or similar platforms | Simulating compute, network, and dependency faults with centralized controls |
| `tc`/`netem`, `stress-ng` | OS-level utilities for simulating network impairment and resource pressure in test environments |

Supported capabilities, action names, limits, and regional availability evolve over time. Before deploying, check current documentation, IAM/RBAC permissions, supported resource types, and cleanup behavior.

### 12.1. Tool Selection Criteria

- Supports the exact VM, container, network, and storage types in use.
- Provides explicit target selectors and pre-run scope validation.
- Supports fault durations, stop conditions, and audit trails.
- Can constrain blast radius and operator privileges.
- Integrates with monitoring/alerting.
- Provides reliable automatic cleanup or rollback.
- Stores experiment definitions and results for repeatability.
- Does not require overly broad permissions.

## 13. Game Days and Operational Drills

Game days test both technology and people. A system might fail over automatically while operators do not know which alerts matter, cannot locate the runbook, or lack clarity on who holds authority to execute recovery.

A game day can include:

1. Selecting a scenario such as losing a VM, a database outage, or isolating a zone.
2. Assigning an incident commander, operators, observers, and a scribe.
3. Publishing scope, schedule, and stop conditions.
4. Inducing the fault per scenario.
5. Letting the on-call team detect and respond using runbooks.
6. Recording decisions, timestamps, and missing information.
7. Stopping the fault and verifying recovery.
8. Holding a retrospective and assigning improvement actions.

Observers should record how long operators spend finding dashboards, identifying owners, requesting access, and locating the right runbook. These delays can make real-world RTO far longer than automated failover times.

## 14. When to Abort an Experiment?

Abort immediately when:

- Error rate, latency, or availability crosses abort thresholds.
- Healthy capacity drops below safe levels.
- Impact spreads to out-of-scope tenants, services, or user groups.
- Data shows signs of loss, corruption, or duplication beyond acceptable bounds.
- Backups, replicas, or critical dependencies fail concurrently.
- Monitoring/alerting stops providing reliable signals.
- Target selectors are wrong or resource scope cannot be verified.
- Rollback actions fail to work as tested.
- The accountable owner decides to end the test.

After aborting, prioritize removing the fault and restoring traffic and data. Preserve logs and timelines for analysis; never keep injecting faults merely to finish a script.

## 15. Analyzing Results and Turning Findings into Improvements

An experiment's outcome falls into one of three categories:

- **Hypothesis confirmed:** the system reacted and recovered within defined thresholds.
- **Hypothesis refuted:** the system failed one or more criteria.
- **Inconclusive:** metrics, logs, or targeting were insufficient to draw a conclusion.

When a hypothesis fails, locate the root cause at the right layer:

- Insufficient redundancy design?
- Health checks failing to detect accurately?
- Timeouts/retries amplifying load?
- Autoscaler lacking quotas or capacity?
- Broken bootstrapping, IAM, or secret dependencies?
- Replication lag exceeding RPO?
- Runbooks or operational permissions slowing recovery?
- Monitoring missing or misconfigured alerts?

Every finding needs an owner, priority, deadline, evidence, and closure criteria. After fixing, re-run the exact same experiment to verify the improvement.

## 16. Experiment Report Template

A concise report can follow this structure:

| Field | Details to Record |
| --- | --- |
| Experiment ID | Identifier and scenario version |
| Objective | Failure mode and hypothesis |
| Environment | Account/project, region, zone, and workload |
| Target | Resource IDs, tags/selectors, and blast radius |
| Preconditions | Baseline, backups, capacity, and guardrails |
| Fault | Fault type, start/end timestamps, and intensity |
| Observations | Metrics, logs, traces, alerts, and automated actions |
| Recovery | Detection, isolation, failover, RTO/RPO, and data integrity |
| Outcome | Pass, fail, or inconclusive |
| Findings | Gaps between expected and actual behavior |
| Actions | Owner, priority, due date, and retest plan |

Never write just "test passed." Attach timelines, dashboards, or reproducible queries.

## 17. Common Mistakes

- Injecting faults without a hypothesis or steady-state metrics.
- Testing multiple failure modes at once, obscuring root causes.
- Selecting targets using unverified tags.
- Starting in production before testing in an isolated environment.
- Lacking abort conditions or an accountable owner authorized to stop the test.
- Watching only CPU while ignoring error rates, latency, and data integrity.
- Treating a replaced VM as proof the service recovered.
- Ignoring retry storms, queue backlogs, and recovery storms.
- Failing to verify RTO/RPO with real data.
- Skipping cleanup verification, leaving fault rules or temporary resources behind.
- Failing to turn findings into tracked actions with owners and deadlines.
- Not re-running the experiment after implementing fixes.
- Assuming backup completion is sufficient without testing restores.
- Simulating a zone failure by breaking out-of-scope shared resources.

## 18. Pre-, During-, and Post-Experiment Checklist

**Before the Experiment**

- [ ] Hypothesis, objective, and pass/fail criteria defined.
- [ ] Steady state and relevant SLOs identified.
- [ ] Specific targets selected and blast radius bounded.
- [ ] Backups/snapshots and test data verified.
- [ ] Guardrails, abort conditions, and rollback ready.
- [ ] Owner, observer, communication channel, and schedule assigned.
- [ ] Monitoring, alerting, and logging verified active.
- [ ] Spare capacity, quotas, and backup dependencies sufficient.

**During the Experiment**

- [ ] Start timestamp recorded when injecting the fault.
- [ ] User-facing metrics and underlying resources monitored.
- [ ] Alerts and automated actions verified.
- [ ] Data integrity, queues, and replication lag monitored.
- [ ] Aborted immediately if any abort threshold is breached.
- [ ] All manual interventions recorded.

**After the Experiment**

- [ ] Fault removed and temporary resources cleaned up.
- [ ] Healthy capacity and steady state verified.
- [ ] Transactions, records, messages, and replicas verified.
- [ ] Detection time, recovery time, RTO, and RPO measured.
- [ ] Results compared against the hypothesis.
- [ ] Owners and deadlines assigned to each finding.
- [ ] Retest scheduled after remediation.

## 19. Process for Building a Continuous Testing Program

1. **Build a risk catalog:** list critical VMs, groups, zones, storage, networks, and dependencies.
2. **Prioritize failure modes:** pick high-likelihood or high-impact faults lacking verified recovery evidence.
3. **Standardize hypotheses:** ground criteria in SLOs, RTO, RPO, and data integrity.
4. **Maintain an experiment catalog:** store scenarios, targets, permissions, guardrails, cleanup, and owners.
5. **Run in isolated environments:** validate mechanics and monitoring quality.
6. **Expand with controls:** widen blast radius in stages through formal approvals.
7. **Run game days:** test coordination, runbooks, alerts, and operational permissions.
8. **Track actions:** manage findings as engineering tasks with owners and deadlines.
9. **Retest:** confirm faults are fixed and recovery meets targets.
10. **Update architecture:** feed results back into templates, autoscaling, health checks, backups, and DR plans.

## 20. Key Principles to Remember

1. Fault testing must start with a hypothesis and measurable steady state.
2. Fault injection creates specific faults; chaos engineering verifies end-to-end system behavior within controlled bounds.
3. Bound blast radius, duration, and targets, and define abort conditions before running.
4. Start in isolated environments and expand scope based on evidence and approval workflows.
5. Test multiple failure modes: VM, CPU, memory, network, storage, dependencies, and zones.
6. Verify detection, isolation, failover, data integrity, and return to steady state.
7. Measure RTO/RPO using timestamps and data checks, not solely resource status.
8. Check retries, queues, replicas, and dependencies to avoid recovery storms.
9. Every finding needs an owner, deadline, and retest criteria.
10. Testing delivers value only when results drive improvements to architecture and runbooks.

Controlled fault testing transforms fault tolerance from a design assumption into verified capability. When each experiment carries a clear hypothesis, safe scope, measurable signals, and post-recovery data checks, operations teams understand how the system behaves under stress and know exactly what to improve to meet high-availability goals.
