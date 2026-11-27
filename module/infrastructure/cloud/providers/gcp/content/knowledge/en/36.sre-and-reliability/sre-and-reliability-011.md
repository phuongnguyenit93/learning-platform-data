# Fault Injection and Resilience Verification on GCP

A service is considered reliable when it still meets business objectives under fault conditions, or can recover within accepted time and data-loss bounds. Passing tests while the system operates normally is not enough to prove this. SRE teams must proactively introduce controlled faults, observe system responses, and verify that redundancy, self-healing, and operational procedures actually work.

On Google Cloud, components such as Google Kubernetes Engine (GKE), Compute Engine, Cloud Run, Cloud SQL, Pub/Sub, Cloud Storage, and Cloud Monitoring provide multiple ways to build resilience. **Chaos engineering** is the practice of validating reliability hypotheses through scoped experiments with explicit stop conditions and clear evidence.

This lesson guides you through designing fault experiments on GCP—from defining SLOs and blast radius to simulating Pod or node failures, testing network dependencies, database failover, message backlogs, and verifying recovery.

## 1. Resilience and Chaos Engineering

Resilience is the ability to maintain or rapidly restore critical functionality when a component fails. A resilient system must handle isolated faults, dependency faults, and operational faults alike.

Common failure types:

- **Process failures:** container crashes, application deadlocks, memory leaks, or resource exhaustion.
- **Infrastructure failures:** VM unavailability, GKE node outages, or zonal disruptions.
- **Network failures:** latency spikes, packet loss, DNS failures, dropped connections, or misconfigured firewalls.
- **Dependency failures:** unreachable Cloud SQL, external API timeouts, or stalled Pub/Sub subscribers.
- **Data failures:** corrupted data, overwritten objects, replication lag, or unrecoverable backups.
- **Configuration and identity failures:** IAM changes, expired credentials, or revoked permissions.
- **Process failures:** failed rollouts, autoscaling lagging behind load, or runbooks out of sync with actual state.

Chaos engineering tests a system by injecting an intentional fault into a selected slice of an environment and observing the reaction. The goal is to uncover weaknesses before real outages happen.

| Concept | Meaning |
|---|---|
| Fault injection | Creating a specific fault such as stopping a Pod, adding latency, or rejecting connections |
| Experiment | A test with a hypothesis, scope, execution steps, and stop conditions |
| Blast radius | Scope of services, data, or users potentially affected |
| Steady state | Normal operating state described by measurable metrics |
| Recovery | Process by which the system returns to meeting SLOs after the fault is removed |
| Game day | A structured drill with participants, coordination, and outcome review |

Fault testing is not creating random outages. Every experiment must have a concrete validation goal and prepared stop or recovery mechanisms.

## 2. Starting from SLOs, RTO, and RPO

Before choosing faults to simulate, define what the system must preserve and how much disruption it can tolerate.

### SLIs and SLOs

A Service Level Indicator (SLI) reflects service quality, for example:

- Successful request ratio.
- p95 or p99 latency percentiles.
- Ratio of messages processed within deadline.
- Database connection success ratio.
- Ratio of sessions completing business logic accurately.

A Service Level Objective (SLO) is the target for an SLI over a time window. For instance, an API might target 99.9% of eligible requests completing successfully over a 30-day window. Actual thresholds must derive from business requirements and organizational service agreements.

An error budget is the amount of failure or disruption still acceptable under the SLO. Fault experiments must operate within the team's error budget policy and change-management workflow.

### RTO and RPO

Two common recovery targets:

- **Recovery Time Objective (RTO):** maximum acceptable duration to restore service after an outage.
- **Recovery Point Objective (RPO):** maximum tolerable data loss, typically expressed as a time span of data.

Examples:

| System | Target RTO | Target RPO | Verification Method |
|---|---:|---:|---|
| Order read API | 10 minutes | Zero loss of committed data | Lose a Pod or node and measure time to resume serving |
| Transactional database | 15 minutes | 5 minutes | Perform failover or restore in a test environment |
| Event-processing consumer | 20 minutes | Zero loss of published retained messages | Stop subscriber, restart it, and reconcile messages |
| Analytics reports | 4 hours | 1 hour | Restore from backups or exported data |

The RTO and RPO figures in this table are illustrative examples only. Never treat them as default guarantees for GCP services; define targets based on architecture, tier, region, backup setup, and operational contracts.

An experiment yields strong evidence only when actual recovery time and data loss are measured and compared against agreed targets.

## 3. Designing Experiment Hypotheses

A good experiment starts with a testable hypothesis. For example:

> If one `orders-api` Pod terminates abruptly, the Deployment will spin up a replacement Pod, remaining replicas will continue serving, and the request success rate will not drop below the configured SLO threshold.

The hypothesis should state clearly:

1. **Initial conditions:** replica count, load, dependency health, zones, and autoscaling config.
2. **Injected fault:** Pod stopped, latency added, node drained, or subscriber paused.
3. **Scope:** namespace, cluster, service, project, zone, and affected user segment.
4. **Observed signals:** availability, latency, error rate, restarts, queue backlog, database connections.
5. **Expected outcome:** workload self-heals, traffic shifts, or alerts fire accurately.
6. **Failure criteria:** SLO breached, RTO exceeded, data lost, or out-of-scope errors.
7. **Stop conditions:** which metrics force the team to abort the experiment immediately.
8. **Recovery steps:** removing fault injection, rolling back configs, rescaling, or restoring service.

Sample brief specification:

| Attribute | Value |
|---|---|
| Experiment ID | EXP-GKE-001 |
| Hypothesis | Losing one Pod does not take the API offline |
| Environment | Dedicated project and cluster for the resilience lab |
| Fault | Delete one Pod in a 3-replica Deployment |
| SLI | Request success ratio and p95 latency |
| Pass criteria | Replacement replica becomes Ready; SLO stays intact |
| Stop condition | Error rate crosses threshold or dependencies start cascading failures |
| Coordinator | Incident/experiment lead |
| Observers | SRE and application owner |

Never start with a massive fault like losing an entire region if the team has not yet proven recovery at the Pod, node, and dependency levels.

## 4. Safety Controls and Blast Radius

Fault experiments can disrupt real services. Therefore, controlling scope and abort authority is a mandatory part of the design.

### Choosing the Right Environment

Prioritize in this order:

1. Local or simulated environments.
2. Dedicated sandbox/test project.
3. Staging with synthetic data and controlled dependencies.
4. Small-scope production canary, only with formal approval and proper safeguards.

Avoid using real customer data unless strictly necessary. Never run experiments that risk deleting data, leaking secrets, or impacting projects outside approved scope.

### Limiting Blast Radius

- Explicitly specify project, cluster, namespace, label selectors, instance group, or service.
- Start with one replica, one node, or a small slice of requests.
- Never use overly broad selectors like an entire production namespace when targeting a single application.
- Use a dedicated execution account with least-privilege permissions.
- Isolate fault injection from control planes and monitoring channels.
- Set a maximum duration and automatic expiration for potentially long-running faults.
- Avoid injecting multiple fault types simultaneously on an initial run, as root causes become hard to isolate.

### Stop Conditions

Abort the experiment immediately if any of the following occur:

- Availability or error rate crosses the abort threshold.
- Latency rises enough to harm users or dependencies.
- Queue backlog grows rapidly with no sign of draining.
- Database connections, CPU, or memory hit dangerous thresholds.
- Loss of access to control planes, monitoring systems, or coordination channels.
- Faults bleed into out-of-scope workloads.
- Risk of unintended data loss or corruption is detected.

The coordinator must have authority to terminate the experiment immediately without waiting for the scheduled duration to expire.

### Preparing Rollback

Before starting, know precisely how to remove fault injection, restore replicas, uncordon nodes, roll back revisions, or restore network rules. Document commands and authorized operators. Verify an independent administrative access path so recovery remains possible even if the test workload fails.

## 5. Experiment Execution Workflow

Organize experiments around the following cycle:

~~~mermaid
flowchart TD
    A[Define reliability question] --> B[Set SLO and steady state]
    B --> C[Choose fault and blast radius]
    C --> D[Review permissions and stop conditions]
    D --> E[Capture baseline]
    E --> F[Inject one fault]
    F --> G[Observe system response]
    G --> H{SLO and safety maintained?}
    H -->|Yes| I[Remove fault and verify recovery]
    H -->|No| J[Stop experiment and contain impact]
    J --> K[Restore known-good state]
    I --> L[Compare evidence with hypothesis]
    K --> L
    L --> M[Record findings and actions]
~~~

Each experiment run should include these phases:

**Before the experiment:** verify environment, participants, schedule, SLOs, dashboards, alerts, baseline, and rollback steps. Capture snapshots of key configurations.

**During the experiment:** inject only the single selected fault, log timestamps, and watch metrics. Do not vary multiple variables at once.

**At completion:** remove the fault, verify normal steady state, check data and traffic, and record recovery duration.

**After the experiment:** compare telemetry against the hypothesis, document discovered issues, prioritize severity, and create action items with owners and due dates.

If an experiment fails, the result is still valuable. Never hide failures or close an experiment before full recovery is confirmed.

## 6. Verifying Resilience on GKE

GKE provides multiple recovery layers: Kubernetes controllers recreate Pods, the scheduler places Pods, node pools supply compute, cluster autoscaler adds nodes, and regional clusters reduce single-zone dependency. These layers have distinct conditions and limits; test each hypothesis separately.

### Preparing a Multi-Replica Workload

Example Deployment in a test namespace:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: resilience-lab
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: app
          image: REGION-docker.pkg.dev/PROJECT_ID/lab/orders-api:VERSION
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
            failureThreshold: 3
~~~

The application must genuinely implement both health check endpoints properly. Readiness determines whether a Pod receives traffic; liveness lets kubelet restart the container when the process stops functioning properly. Avoid overly sensitive liveness probes that cause cascading restarts simply because the app is under heavy load.

### Using PodDisruptionBudget

A PodDisruptionBudget (PDB) caps how many Pods can be disrupted during certain voluntary eviction operations:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: resilience-lab
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

With three replicas, the PDB above requires at least two Pods ready during PDB-governed evictions. PDBs do not block every failure mode: direct Pod deletion, process crashes, node power loss, or zonal outages can reduce ready Pods below this floor.

### Spreading Pods Across Zones

To avoid all replicas landing in a single zone, use topology spread constraints:

~~~yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule
    labelSelector:
      matchLabels:
        app: orders-api
~~~

Place this inside the Pod template. Ensure the cluster has nodes across enough zones with matching capacity. If nodes are missing in a zone or selectors do not match, the scheduler may leave Pods Pending.

### Testing Loss of One Pod

After confirming all three replicas are Ready, record initial state and pick one Pod in the lab namespace:

~~~bash
kubectl get pods -n resilience-lab -l app=orders-api -o wide
kubectl get pdb -n resilience-lab
~~~

In an approved test environment, delete a specific Pod to verify the controller spins up a replacement:

~~~bash
kubectl delete pod POD_NAME -n resilience-lab
kubectl get pods -n resilience-lab -l app=orders-api -w
~~~

Directly deleting a Pod simulates Pod loss and is not blocked by a PDB like voluntary evictions. Track Ready replica count, successful requests, latency, and time until the replacement Pod becomes Ready.

### Testing Node Drain

Node drain verifies Pod migration during voluntary maintenance. Run only on a node in the lab cluster after verifying PDBs, capacity, and co-located workloads:

~~~bash
kubectl cordon NODE_NAME
kubectl drain NODE_NAME --ignore-daemonsets
~~~

After observing Pod rescheduling and workload stability, mark the node schedulable again:

~~~bash
kubectl uncordon NODE_NAME
~~~

`kubectl drain` can be blocked by PDBs or Pods not managed by a controller. Never add flags that wipe local data just to force the command through. If a node hosts Pods using `emptyDir` or local state, assess impact before draining.

### Checking Node Auto-Repair and Cluster Autoscaler

- Node auto-repair monitors node health and can repair or recreate unhealthy nodes per configuration.
- Cluster autoscaler adjusts node counts when Pods fail to schedule due to capacity shortages and autoscaling conditions are met.
- Node auto-provisioning can create new node pools if configured by the organization.

Test each mechanism individually. Measure node failure detection time, new node provisioning time, Pod Ready time, and traffic impact. Never assume autoscalers fix every situation instantaneously; min/max node bounds, quotas, zonal capacity, and scheduling constraints all apply.

## 7. Testing Network and Dependency Faults

Many incidents do not kill Pods yet still make requests slow or fail. Applications need timeouts, bounded retries, exponential backoff, circuit breakers, and proper dependency error handling.

### Fault Types to Verify

| Fault | Behavior to Check |
|---|---|
| Added latency | Do requests time out on schedule? Do queues grow? |
| Packet loss | Do retries amplify load? |
| DNS failure | Does the app cache DNS too long or fail fast? |
| Dependency unavailable | Does the circuit breaker stop repeated calls? |
| Connection reset | Do clients recover connections and handle idempotent requests? |
| Blocked egress | Do alerts detect it and runbooks point to the right network layer? |

### Using Fault Injection Tools

Chaos Mesh is an open-source tool that can run on Kubernetes to inject faults such as Pod failures, network delays, or packet loss. It is not a service enabled automatically by Google Cloud in GKE; teams must deploy, secure, and manage the tool's lifecycle separately.

Example `NetworkChaos` targeting only Pods with label `app: orders-api` in the lab namespace:

~~~yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: orders-api-delay
  namespace: chaos-mesh
spec:
  action: delay
  mode: all
  selector:
    namespaces:
      - resilience-lab
    labelSelectors:
      app: orders-api
  delay:
    latency: "150ms"
    correlation: "25"
    jitter: "30ms"
  direction: to
  duration: "2m"
~~~

This manifest is only an example for a cluster with Chaos Mesh and its CRDs installed. Verify tool version, permissions, schema, and target selection before applying. Never deploy a chaos controller with broad `cluster-admin` permissions unnecessarily.

Apply in the lab:

~~~bash
kubectl apply -f orders-api-delay.yaml
kubectl get networkchaos -n chaos-mesh
~~~

When the timer expires or an early abort is needed, delete the experiment object:

~~~bash
kubectl delete -f orders-api-delay.yaml
~~~

After deletion, verify latency returns to baseline. If the system stays slow, inspect open connections, retry storms, connection pools, and dependency health. Deleting the fault-injection object does not guarantee all side effects vanish immediately.

### Testing Timeouts and Retries

Suppose an API calls an inventory service. Inject latency into the dependency and observe:

- Is client timeout smaller than the overall request timeout?
- Are retries bounded in count and spaced by backoff?
- Do retries use jitter to avoid synchronized waves across clients?
- Do write requests use idempotency keys or deduplication?
- Does the circuit breaker halt new calls while the dependency is failing?
- Do queues and connection pools return to normal after the fault ends?

Unbounded retries can turn a slow dependency into a full-system outage. The experiment aims to verify the app degrades in a controlled way.

## 8. Verifying Recovery on Compute Engine and Cloud Run

### Compute Engine Managed Instance Groups

A Managed Instance Group (MIG) maintains desired VM counts, replaces unhealthy instances, and supports rolling updates. Regional MIGs distribute instances across multiple zones in a region per configuration.

Hypotheses to verify:

- Health checks detect unhealthy instances within expected timeframes.
- Autohealing provisions replacement VMs.
- Load balancers stop routing traffic to unhealthy backends.
- MIGs maintain target instance counts when quotas and capacity allow.
- Rolling updates do not drop serving instances below configured thresholds.

In a dedicated lab MIG, you can list and delete an instance to verify recreation:

~~~bash
gcloud compute instance-groups managed list-instances "MIG_NAME" \
  --region="REGION" \
  --project="PROJECT_ID"
~~~

Delete an instance only after confirming the exact test MIG, ensuring no local data must be preserved, and verifying autohealing is configured. Then observe instance state, health checks, and backend services.

Never confuse autohealing with backups. MIGs recreate VMs from an instance template; data on boot disks or local disks may not persist as expected. Data that must survive VM lifecycles belongs in an appropriate storage service.

### Cloud Run

Cloud Run manages container infrastructure and spins up instances on demand. Experiments can focus on:

- New revisions failing startup or readiness/startup checks.
- Slow dependencies causing request timeouts.
- Instances hitting concurrency limits or max instances.
- A revision exhibiting high error rates after receiving traffic.
- Traffic shifting back to a stable revision on rollback.

You can deploy test revisions and use traffic splitting on a lab service. Record revision names, image digests, concurrency settings, timeouts, min/max instances, and traffic splits beforehand.

Example inspecting revisions and traffic:

~~~bash
gcloud run services describe "SERVICE_NAME" \
  --region="REGION" \
  --project="PROJECT_ID" \
  --format=yaml
~~~

Rollbacks must target a known-good revision and verify actual traffic routing, not merely check that the update command succeeded. If the app has side effects or database migrations, rolling back the container does not automatically undo data changes. Design backward-compatible migrations and separate data-recovery procedures.

## 9. Verifying Cloud SQL, Pub/Sub, and Cloud Storage

### Cloud SQL: HA, Failover, and Data Recovery

Regional Cloud SQL HA uses primary and standby instances with managed failover. During failover, the instance's connection endpoint stays intact by service design, though existing connections drop and applications must reconnect.

HA and disaster recovery serve different goals:

- HA handles in-region failures per instance configuration.
- Backups and point-in-time recovery (PITR) support data recovery.
- Cross-region DR requires backups, replicas, or standby architectures aligned with RTO/RPO targets.

Test on a non-production instance:

1. Document HA, backup, PITR, maintenance, and connection pool settings.
2. Generate representative business test load.
3. Trigger failover per approved procedures and permissions.
4. Measure connection failure duration, reconnection time, and when business operations stabilize.
5. Inspect transactional data, consistency, and retry errors.
6. Test restoring from backup or PITR onto a separate instance to verify RPO.

Never run failover or restore drills on production instances without an explicit change plan and formal approvals. A successful backup does not prove a successful restore; periodically test restores and verify data integrity.

### Pub/Sub: Stalled Subscribers

A subscriber can stall while publishers keep sending messages. This test validates backlogs, retries, ack deadlines, and dead-letter topics.

Procedure:

1. Record message counts, throughput, oldest unacked message age, and subscription backlog.
2. Stop the subscriber in the lab environment.
3. Continue publishing test messages with tracking IDs.
4. Restart the subscriber and observe backlog drain rate.
5. Check duplicate deliveries, message ordering if ordering is enabled, and idempotency logic.
6. Verify no messages expire past retention limits and the subscriber recovers within RTO.

Pub/Sub provides at-least-once delivery semantics in common configurations; consumers must handle duplicate messages safely. Never assume a message is delivered strictly once. When using dead-letter topics, verify delivery attempt counts, IAM permissions, and message replay procedures.

### Cloud Storage: Access and Object Recovery

Use a lab bucket to verify how the application handles permission errors or missing objects:

- Restrict read permissions for a test service account and verify the app handles `403` properly.
- Attempt reading a missing object and verify `404` handling.
- Enable object versioning in the lab bucket, overwrite a test object, and verify restoring the prior generation.
- Verify retention policies and object recovery workflows.

Never run bulk deletions, overwrite live data, or alter retention on production buckets. If object versioning was not enabled before an object was overwritten or deleted, never assume prior versions can be recovered.

## 10. Observing and Measuring During Experiments

Experiments without observability prove nothing about resilience. Record the baseline, fault injection start time, detection time, system reaction time, and recovery time.

### Metrics to Monitor

| Category | Suggested SLI/Metric | Purpose |
|---|---|---|
| Availability | Request success ratio, uptime checks | Determine whether the service keeps serving |
| Latency | p50, p95, p99 | Detect experience degradation |
| Errors | 4xx/5xx, timeouts, retry counts | Quantify fault impact |
| Saturation | CPU, memory, queue depth, connection pools | Spot resource exhaustion |
| Kubernetes | Pod Ready, restarts, Pending, node conditions | Measure scheduler and controller responses |
| Database | Connection errors, failover duration, replication lag | Verify HA and data recovery |
| Messaging | Backlog, oldest unacked age, dead-letter count | Measure event reprocessing resilience |
| Cost/capacity | Instance counts, node counts, autoscaling events | Spot recovery-driven load or cost spikes |

Cloud Monitoring provides dashboards, alerting, and metrics for many GCP services. For application metrics on GKE, use Managed Service for Prometheus and query with PromQL. Logs from Cloud Logging and Cloud Audit Logs correlate error timestamps with administrative actions.

### Calculating Recovery Time

Record at least these timestamps:

- T0: fault injection starts.
- T1: system or operator detects the anomaly.
- T2: self-healing or mitigation starts.
- T3: workload or dependency returns to ready state.
- T4: SLIs return within SLO bounds.

Calculate:

\[
\text{Detection Time} = T1 - T0
\]

\[
\text{Recovery Time} = T4 - T0
\]

Measure Recovery Time from fault start until the service genuinely returns to its SLO, not merely until a new Pod or VM appears.

### Combining Logs, Metrics, and Traces

- Metrics reveal impact magnitude and duration.
- Logs supply discrete events and root-cause details.
- Traces pinpoint which dependency or processing step added latency.

Use shared correlation IDs or trace context where supported by the app. Synchronize clocks across components and log UTC timestamps in experiment records.

## 11. Evaluating Results and Improving Architecture

After each experiment, classify the outcome:

| Outcome | Interpretation | Action |
|---|---|---|
| Pass | Hypothesis holds, SLO preserved, recovery meets targets | Archive evidence and expand scope incrementally |
| Pass with degradation | Service stays up while latency or errors rise | Review SLO thresholds, optimize capacity and dependencies |
| Fail | SLO or RTO/RPO missed | Create remediation work, fix architecture or processes |
| Invalid experiment | Fault was misconfigured or telemetry was missing | Fix experiment design and re-run safely |
| Aborted | Stop condition triggered | Recover, analyze impact, and refine guardrails |

Frequently uncovered issues:

- Overly strict PDBs blocking node drains.
- Replicas concentrated in one zone.
- Readiness probes failing to reflect real request-handling capability.
- HPA failing to scale in time or lacking node capacity.
- Unbounded retries causing retry storms.
- Connection pools failing to recover after database failover.
- Consumers processing duplicate messages and creating duplicate writes.
- Backups existing yet failing to restore within RTO.
- Alerts firing too late or lacking an assigned recipient.
- Runbooks requiring permissions the on-call engineer lacks.

Every finding needs an owner, priority, deadline, and post-fix verification plan. Never close an action item simply because config was edited; re-run the experiment to prove the weakness is resolved.

## 12. Hands-On Scenario: Verifying `orders-api` Resilience

A system consists of:

- `orders-api` running on GKE with three replicas.
- Cloud SQL storing orders.
- Pub/Sub receiving new order events.
- Cloud Monitoring tracking request rate, error rate, and latency.

The objective is to verify the API survives losing one Pod and handles temporary Cloud SQL unresponsiveness gracefully.

### Phase A — Baseline

1. Confirm all three Pods are Ready and placed on appropriate nodes.
2. Verify PDB, topology spread, and HPA settings.
3. Send steady synthetic load long enough to establish a baseline.
4. Record request success ratio, p95 latency, CPU, memory, and database connections.
5. Confirm dashboards and alerts are active.

### Phase B — Losing One Pod

1. Select one Pod in the lab namespace.
2. Record the Pod name, node, UID, and start timestamp.
3. Delete the selected Pod.
4. Watch the Deployment spin up a replacement Pod.
5. Measure time until the new Pod is Ready and SLIs return to baseline.
6. Verify no orders were duplicated or lost.

The hypothesis passes if the remaining two Pods keep serving, a replacement Pod starts, and SLOs remain intact.

### Phase C — Slow Dependency

1. Use the lab fault-injection tool to add bounded latency to the test dependency.
2. Observe timeouts, retries, connection pools, request queues, and error rates.
3. End the fault on schedule or abort immediately if thresholds are breached.
4. Verify connection pools and request latency return to normal.
5. Verify order data and Pub/Sub consumers.

The hypothesis passes if the API degrades gracefully without retry storms or corrupted writes.

### Phase D — Verifying Recovery

- Compare data before and after the experiment.
- Confirm Pub/Sub backlogs return to normal.
- Verify no lingering fault injections or test overrides remain.
- Confirm dashboards, alerts, and logs captured complete records.
- Calculate Recovery Time and compare against RTO.
- Record findings, remediations, and owners.

Do not proceed to the dependency-fault phase until the Pod-loss phase has fully recovered. Evaluate and confirm each phase before continuing.

## 13. Chaos Experiment Checklist

### Before the Experiment

- [ ] Concrete hypothesis and pass/fail criteria are documented.
- [ ] Relevant SLIs, SLOs, error budgets, RTOs, and RPOs are identified.
- [ ] Target project, cluster, namespace, and workload are verified.
- [ ] Coordinator, observers, and abort-authorized operator are assigned.
- [ ] Baseline metrics, dashboards, alerts, and logs are ready.
- [ ] Backups, rollbacks, and administrative access paths are verified.
- [ ] Schedule, blast radius, and stop conditions are approved.

### During the Experiment

- [ ] Inject only one planned fault at a time.
- [ ] Log timestamps and before/after state for every action.
- [ ] Monitor availability, latency, errors, and saturation.
- [ ] Monitor dependencies, queues, and data integrity.
- [ ] Abort immediately if any safety condition is violated.

### After the Experiment

- [ ] Fault injection removed and configuration restored.
- [ ] Workloads, dependencies, and data verified.
- [ ] SLIs returned within SLO bounds.
- [ ] Recovery Time and data loss recorded.
- [ ] Outcomes, logs, and dashboards archived as evidence.
- [ ] Findings have owners, deadlines, and re-verification plans.
- [ ] Runbooks and architecture updated as needed.

Fault testing on GCP turns reliability assumptions into measurable evidence. When every experiment has a clear hypothesis, bounded scope, stop conditions, observability signals, and recovery procedures, teams uncover weaknesses before real outages occur, improve RTO/RPO, and strengthen the resilience of production services.
