# Failover, Failback, and Cross-Region Traffic Shifting

A multi-region architecture does not automatically become a disaster recovery system. Both regions may have servers and services running fine, yet the application still fails when the database only permits writes in the outage region, DNS points to stale addresses, or authentication fails in the standby location. To keep services running when one deployment region encounters trouble, operations teams must coordinate **traffic shifting**, **data role promotion**, **consistency enforcement**, and **returning to normal operations**.

On Google Cloud, solutions can combine Cloud Load Balancing, Cloud DNS, Cloud Run, GKE, Compute Engine, Cloud SQL, Spanner, Cloud Storage, and data integration services. This lesson focuses on architectural decisions and verifiable runbooks: when to fail over, how to route traffic to a standby region, when data writes may open, how to fail back safely, and how to rehearse to satisfy RTO/RPO. There is no single universal gcloud command that automates this entire flow across all services.

## 1. Distinguishing failover, failback, and traffic shifting

| Concept | Meaning | Example |
| --- | --- | --- |
| Failover | Moving service to a standby component or region when the primary region cannot serve targets | Stop writes in region A, promote writer in B, and route requests to B |
| Failback | Returning service to the original region after fixing the incident, syncing data, and verifying capacity | Replicate valid changes from B back to A, then switch write authority and traffic per plan |
| Traffic shifting | Adjusting request distribution or targets without necessarily having an outage | Shift 5%, 25%, 100% of traffic to region B for validation |
| Disaster recovery (DR) | Combined set of application, data, and dependency recovery plans for severe outages | Operational runbooks, backup mechanisms, recovery, and verification |
| High availability (HA) | Reducing downtime from component or failure-domain faults within design boundaries | Multiple instances/zones, health checks, and automatic replacement |

Failover does not mean data has been accurately recovered. Successful traffic shifting does not mean all write transactions are safe. Failback is not merely resetting traffic weights either: after running in B for a while, B may hold new writes that A does not yet have.

Distinguish **application-tier failover** from **data-tier failover**. Read requests can be routed to B once B is ready, but writes must never open in B before cleanly resolving the old writer, replication state, and data ownership.

## 2. Setting RTO, RPO, and SLO targets

Two foundational metrics:

- **Recovery Time Objective (RTO):** maximum outage duration the business targets to tolerate when restoring a service after an incident.
- **Recovery Point Objective (RPO):** maximum acceptable data loss, expressed as the time skew between recovered data and pre-incident state.

For example, an ordering system has a 15-minute RTO and 5-minute RPO. The team must design so critical functions recover within the target window and lose no more than 5 minutes' worth of data under the chosen scenario. This is a design requirement, not a guarantee that every outage automatically meets those targets.

One way to break down RTO:

\[
\text{Total recovery time} \approx
\text{Detection} +
\text{Decision} +
\text{Data recovery} +
\text{Traffic shifting} +
\text{Verification}
\]

If detection takes 8 minutes and approval takes 10 minutes, a 15-minute RTO cannot be achieved even if switching traffic takes only 30 seconds. Measure each phase in realistic drills and report p50/p95 where enough samples exist.

RPO depends on replication strategy and write semantics. Asynchronous replication can lag; a write just committed in A might not reach B before A goes down. For certain multi-region services with strong consistency and provider-managed failover, RPO behaves differently. Apply targets **per data system**, rather than assuming RPO is met just because both regions host resources.

User-journey SLOs still matter: an API might return HTTP 200 after failover yet read stale data or duplicate transactions. SLIs should cover correctness, availability, latency, and backlog state depending on business needs.

## 3. Choosing active-passive or active-active models

| Model | How it works | Advantages | Trade-offs |
| --- | --- | --- | --- |
| Cold standby | Region B holds infra definitions; most resources are created during an incident | Low ongoing cost | Long RTO; recovery depends on provisioning |
| Warm standby | Region B runs baseline infra/services with replicated data, receiving little or no traffic | Balances cost and RTO | Must scale B before taking full load |
| Hot standby / active-passive | Region B is ready to serve; A takes most traffic while B stays synchronized | Relatively fast switchover if data is ready | High ongoing cost; requires split-brain protection |
| Active-active | Both regions concurrently serve portions of traffic | Utilizes capacity, reduces single-region dependence | Hardest for write data, user sessions, and conflicts |

Do not call a system active-active just because frontends sit in two regions. If every request ultimately writes to a single database writer in A, A remains a single point of failure for all write paths. You can design an active-active frontend with an active-passive database; the runbook must reflect that explicitly.

Selection must rest on dependency availability, fault tolerance, and cost. A public read-only app can shift traffic flexibly; a payment app requiring exact transactions may require approved failover and data verification before permitting writes.

## 4. Mapping dependencies before choosing a cutover path

Map the path from user requests to every required component:

~~~mermaid
flowchart LR
  U["Users"] --> E["DNS / Global edge"]
  E --> A["Region A: Cloud Run or GKE"]
  E --> B["Region B: Cloud Run or GKE"]
  A --> DA["Database writer A"]
  B --> DB["Standby replica or writer B"]
  DA -. "Replication per service capability" .-> DB
  A --> Q["Pub/Sub / event processing"]
  B --> Q
  A --> S["Secrets, IAM, supporting APIs"]
  B --> S
  S --> X["External / on-prem services"]
~~~

Verify whether each dependency is available in B:

| Dependency | Question to answer before failover |
| --- | --- |
| Artifacts and runtime | Are images/digests, pull permissions, and Cloud Run/GKE configs available in B? |
| Database | Does B hold a valid copy, what is replication lag, and who is the writer? |
| Object storage | Are buckets/data readable from B, and what are the exact replication mechanism and RPO? |
| Secrets/KMS | Do workload identities in B have permission to use secrets/keys, and are they available in the right region? |
| Queues/events | Can consumers in B resume without duplicate processing or dropped events? |
| DNS/ingress | Do routes, TLS certificates, firewalls, WAF, auth, and health signals work in B? |
| Private connectivity | Do VPN/Interconnect/PSC or on-prem endpoints have working bidirectional routes from B? |
| External services | Do callback URLs, IP allowlists, quotas, and API keys accept region B? |

If B lacks critical data or cannot reach third-party payment gateways, shifting 100% of HTTP traffic to B merely turns an infrastructure outage into a business failure.

## 5. Two-region reference architecture on Google Cloud

Suppose a service runs in hypothetical regions A and B using identical container versions and security policies, while the data tier has a corresponding standby mechanism. A global traffic control mechanism in front of both endpoints decides where new requests go.

~~~mermaid
flowchart TD
  C["Client / API caller"] --> LB["Global Load Balancing or DNS steering"]
  LB -->|"Normal"| RA["Region A - application"]
  LB -->|"Standby / load sharing"| RB["Region B - application"]
  RA --> WA["Active write data source"]
  RB --> WB["Data source in B"]
  WA -. "RPO-bounded replication" .-> WB
  CT["DR coordinator + runbook"] --> G["Gate: health, capacity, data readiness"]
  G --> LB
  G --> WA
  G --> WB
  OBS["Monitoring, Logging, Audit"] --> CT
  RA --> OBS
  RB --> OBS
~~~

This diagram shows architectural decisions, not a literal API configuration. Replication paths, write authority, and traffic shifting differ by database type. Never connect two databases to accept writes concurrently unless the product or application layer supports multi-writer conflict resolution.

A practical design must specify when the load balancer shifts automatically on health, when human approval is required, and when cutover is blocked because data is not ready.

## 6. Traffic shifting with global load balancing

A Global external Application Load Balancer can place one global entrypoint in front of backends across multiple regions, with configurable backend selection and routing policies. For backends supporting health checks, health signals and capacity can inform backend selection. Features such as weighted routing, route rules, or failover behavior depend on load balancer and backend types.

For Compute Engine and certain GKE backends, load balancer health checks can signal traffic away from unhealthy endpoints. Understand the boundaries clearly:

- Health checks verify only configured conditions—they do not guarantee data or orders are processed accurately.
- In-flight sessions may be disrupted; not all active connections migrate seamlessly.
- Traffic shifts remain subject to propagation, draining, caching, and backend capacity.
- If a health check only hits a trivial endpoint, the service can report healthy even when the database writer is dead.

**Special note for Cloud Run:** when connected via serverless network endpoint groups (serverless NEGs), do not assume standard VM/instance-group health checks and failover mechanics apply identically. Traffic management and failure detection for serverless backends depend on the load balancer type and supported features. Test real behavior when B has an application fault, not just when B returns HTTP 200 on one endpoint.

For canaries or planned shifts, configure region-selecting routing policies or traffic weights where backend configuration supports them. Never equate **Cloud Run revision traffic splitting** with **region shifting**: revision splitting within one service only distributes across revisions of that service; coordinating across regions requires a front-end layer or appropriate workflow.

## 7. Traffic shifting with DNS: benefits and limitations

Another option uses DNS to change which IP or endpoint clients receive. Cloud DNS supports record types and routing policies per product scope, yet failover designs must consider record types, TTLs, health mechanisms, and real resolver behavior.

| Consideration | Consequence |
| --- | --- |
| TTL and caching | Clients/resolvers may keep using old answers after updates |
| Keep-alive and connection pools | Existing connections do not migrate merely because DNS returns a new IP |
| DNS propagation | No guarantee all clients observe updates simultaneously |
| Health-aware policies | Use only when policy/record type and health checks are supported |
| Private DNS | Must account for resolvers, forwarding, inbound/peering, and authorized VPCs |
| DNSSEC/TLS/certs | Switching targets must not break validation or endpoint identity |

Lowering TTL prior to a planned switch helps shrink cache delay, but does not guarantee every client honors TTL. You cannot lower TTL mid-outage and expect all stale caches to expire instantly.

For transactional APIs requiring low RTO, consider a stable entrypoint at the load balancer layer and use DNS mainly for naming/discovery. DNS steering can fit certain scenarios, provided it is rehearsed and target-switch lag is accepted. Measure **when clients actually switch successfully**, not just when the Cloud DNS API accepts the new record.

## 8. Shifting traffic in GKE, Cloud Run, and Compute Engine

### GKE

In GKE, use backends supported by Cloud Load Balancing, Gateway, or supported multi-cluster architectures to route across clusters/regions. To shift successfully, B needs node capacity, Ready Pods, ingress policies, certificates, and proper data-layer connectivity.

When ramping traffic to B, monitor:

- Desired/available replicas, readiness, pod startup, and HPA.
- Scheduling/node autoscaler, CPU/memory, and connection pools.
- Ingress upstream errors, TLS, timeouts, and 5xx responses.
- Whether B keeps running if A's control plane or infrastructure becomes unreachable.

Never treat Pod Ready as sufficient to open writes if the database is not ready. Readiness checks should distinguish frontend readiness from write-dependency readiness and DR operational state.

### Cloud Run

Each service deployed in a region has its own endpoint and configuration. B must have matching images, environment variables, IAM, secret access, CPU/memory, concurrency, and max instances. A front-end routing layer can distribute requests to services across regions.

A service running in B with too low a max-instances cap, missing DB connection limits, or missing secret read access cannot handle A's production load. After shifting, monitor latency, error rates, and autoscaling speed rather than checking a single successful request.

### Compute Engine

For VMs or managed instance groups across regions, verify images/templates, health checks, autoscaling, absence of local state, startup scripts, and how load balancer backends distribute traffic. Confirm backend types support intended failover policies; never copy a regional load balancer template directly to a global load balancer without checking semantics.

## 9. Which signals are authorized to trigger failover?

Never trigger regional failover just because one metric spikes for a few seconds. A sound trigger combines customer signals, platform state, and data health:

| Signal type | Examples | What it informs |
| --- | --- | --- |
| User SLIs | Error rate, p95/p99, incomplete transactions | Is service availability truly impacted? |
| Infrastructure | Unhealthy backends, unready instances, region connectivity loss | Incident scope and healthy locations |
| Data state | Replication lag, promotability, consistency checkpoints | Can B safely accept writes? |
| Dependencies | IAM, Secret Manager, payment gateways, DNS, private links | Can B fulfill the full user journey? |
| Capacity | CPU, queues, instance/pod counts, database throughput | Can B sustain load after shifting? |
| People/process | Incident commander, data owner, change approval | Who holds authority to switch or halt? |

Use at least two stages: **detection and evaluation**, then **confirmation of cutover conditions**. A transient health-check blip might come from an ongoing rollout; impulsive region flipping and flapping back can amplify an outage.

Define hysteresis thresholds, minimum observation windows, cooldowns, and override authority. For write data at risk of loss/corruption, favor controlled failover or automation with strict safety gates instead of promoting a writer solely on HTTP health.

## 10. Preventing split-brain and establishing a single write authority

**Split-brain** occurs when both sides believe they are valid writers in a single-writer architecture. For instance, if the network between A and B partitions, both continue taking orders and diverge. Once connectivity heals, data cannot be merged safely without clear rules.

Design measures:

1. Define the **source of truth** and valid writer at every moment.
2. Use supported fencing or write-permission controls to ensure the old writer cannot keep writing once B opens.
3. Promote data in B only after verifying safety conditions per product mechanisms.
4. Track generations/epochs, leader identity, or role transition states if your system uses them.
5. Ensure APIs and jobs carry idempotency keys, especially for retries and message redelivery.
6. Plan reconciliation for transactions near the disruption point.

Never rely solely on DNS updates to stop writes in A. Clients may retain cached addresses or open connections. Fencing must happen at a layer that reliably blocks writes: database roles/permissions, verified network policies, applications, or proper leader election.

True active-active multi-writer requires conflict resolution and business-level consistency design—a very different problem from letting two replicas serve HTTP requests.

## 11. Failover characteristics of each GCP data service

Google Cloud services handle role transitions differently:

| Service / model | DR characteristics to evaluate | Risks to check |
| --- | --- | --- |
| Cloud SQL with cross-region read replica | Cross-region replica can support recovery via proper promotion workflow | Async replication can lag; promotion and updating connection strings do not create reverse replication |
| Cloud SQL regional HA | Handles certain intra-region/zone failures per service HA mechanism | Does not replace DR plans when the whole region is impacted |
| Spanner multi-region | Service manages replication/leadership per instance configuration and Spanner consistency model | Do not apply SQL replica promotion runbooks mechanically to Spanner |
| Cloud Storage dual/multi-region | Data distributed per bucket type and supported replication policy | Do not equate object availability with RPO=0; check replication lag |
| Firestore | Recovery depends on database location, configuration, and supported features | Do not assume manual cross-region replica promotion like Cloud SQL |
| Pub/Sub | Must evaluate message retention, backlog, subscriptions, and producer/consumer flows | Redelivery, duplicate handling, ordering, and data location |
| BigQuery | Dataset location, copies, and DR features per configuration | Queries in B might lack newer datasets/tables or matching access permissions |

**Cloud SQL:** in cross-region replica setups, check replication lag, checkpoints, and replica state before promoting. Promotion breaks the old replication link; never assume A automatically becomes B's replica when A returns. Failback generally requires rebuilding replicas, syncing data, and planning a controlled role switch.

**Spanner:** leverage the product's built-in multi-region and consistency capabilities rather than treating it like two MySQL primaries. Design read/write placement, latency, failover behavior, and test Spanner-specific conditions.

**Storage and analytics:** restoring a database does not automatically restore objects, analytics datasets, or related metadata. If an order transaction writes to the DB and uploads a file to Cloud Storage, plan how to reconcile both stores after an incident.

Backups remain an independent defense layer from replication: app bugs or accidental deletes replicate to region B. Maintain retention, backups, restore tests, and safeguards against logical errors or data deletion.

## 12. Standard failover sequence: never shift traffic too early

An actionable runbook should define stages with **entry criteria**, owners, and **exit criteria**.

| Stage | Actions | Exit criteria to proceed |
| --- | --- | --- |
| F0. Declare | Confirm incident, blast radius, appoint incident commander | Decision authority and comms channels active |
| F1. Freeze | Pause deploys/schema-changing jobs; restrict writes in A if needed | No ongoing changes drifting state |
| F2. Assess data | Check replication lag, checkpoints, backups, promotability | Estimated RPO and recovery choice clear |
| F3. Fence old writer | Block A from further writes if single-writer is required | Evidence old writer can no longer commit writes |
| F4. Promote/activate B | Activate data writer or data state in B per service runbook | B passes test reads/writes |
| F5. Enable workloads | Verify secrets, IAM, capacity, service endpoints in B | Critical user journeys pass in B |
| F6. Shift traffic | Route new requests per supported policy | Error rates and latency in B within bounds |
| F7. Observe | Monitor backlogs, retries, lingering traffic on A, anomalous transactions | SLOs recovering; zero split-brain |
| F8. Stabilize | Record recovery point, changed resources, and standby status | Runbook updated; failback plan initiated |

Steps do not always follow an inflexible sequence: read-only apps can shift partial traffic before writer promotion; some managed services automate data failover at the platform layer. Still, every skipped step needs an explicit rationale rather than turning the runbook into ad-hoc manual commands.

If cross-region connectivity drops and A's status is unknown, favor data safety over speed. Without proof of exclusive write authority, enter read-only mode or temporarily reject risky writes until safe fencing is verified.

## 13. Example readiness and status checks before cutover

The commands below are strictly **read-only**, performing no failover or traffic changes. Replace projects, regions, and resources with valid test environment values.

Inspect two Cloud Run services:

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --format="value(status.url,status.conditions)"

gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=asia-east1 \
  --format="value(status.url,status.conditions)"
~~~

Inspect global backend services (if used by your architecture):

~~~bash
gcloud compute backend-services list \
  --project=PROJECT_ID \
  --global

gcloud compute backend-services get-health BACKEND_SERVICE_NAME \
  --project=PROJECT_ID \
  --global
~~~

`get-health` applies to supported backend/health-check models and does not guarantee identical health visibility for serverless NEGs. When using Cloud Run via serverless NEGs, combine logs, synthetic probes, and application telemetry rather than inferring from one command.

Inspect the relevant Cloud SQL instance:

~~~bash
gcloud sql instances describe DB_INSTANCE_NAME \
  --project=PROJECT_ID \
  --format="yaml(name,region,state,replicaConfiguration,masterInstanceName)"
~~~

Displayed fields may vary across CLI versions and instance types; `describe` output **does not replace** checking replication lag and transaction state via service-supported metrics/queries. Never promote a database solely because the instance state shows RUNNABLE.

Inspect the DNS zone if DNS sits on the cutover path:

~~~bash
gcloud dns record-sets list \
  --project=PROJECT_ID \
  --zone=APP_DNS_ZONE
~~~

During drills, save auditable snapshots of policies/records/routes and verify live requests actually land in region B. Never log tokens or secrets into recovery logs.

## 14. Phased traffic shifting when data permits

If B is ready to serve and the data model permits both regions to accept partial traffic, shift incrementally to catch issues early:

| Phase | Illustrative split | Gate to verify |
| --- | --- | --- |
| Baseline | A: 100%, B: 0% | B warm; data/identities/endpoints valid |
| Canary | A: 95%, B: 5% | SLIs, error rate, latency, sessions, dependencies |
| Expand | A: 75%, B: 25% | B capacity, database connections, retries/backlogs |
| Majority shift | A: 25%, B: 75% | Zero errors across user cohorts |
| Complete | A: 0%, B: 100% | SLOs stable; no critical requests left on A |

This is a **planned migration flow**, not a mandatory sequence when A is completely down. During a severe A outage, cut straight to B if safety gates pass. Conversely, if only B may write, never send partial write traffic to A during canary steps after A has been fenced.

Traffic splits must respect transaction semantics, session affinity, and data locality. For orders, separate **read canaries**, **write canaries**, partner callbacks, and background tasks. If clients rely on in-memory session state in A, provide a shared session store or stateless token scheme so B can serve continuing requests.

While ramping traffic, observe actual RPS per region rather than configured percentages alone. DNS caches, open connections, or backend selection behavior can skew actual ratios from expectations.

## 15. Handling Cloud DNS, sessions, and long-lived connections

Even after entrypoints switch quickly, older connections can keep hitting A:

- HTTP keep-alive and gRPC streams persist across many requests.
- Java/Spring connection pools may hold stale IPs or sockets.
- DNS resolvers cache inconsistently beyond TTL.
- Mobile clients may drop offline and retry much later.
- External partner webhooks may allowlist old endpoints or IPs.

Regional cutover designs must handle **draining**, safe connection closing/retrying, timeouts, and idempotency. Never return arbitrary errors to force clients elsewhere if clients will retry a payment call lacking an idempotency key.

For DNS, document authoritative zones, current TTLs, routing policies, private/public zones, and rollback paths. For global load balancers, verify certificates, backend mappings, edge security, URL maps, and route rules. In both cases, aim for the most stable user-facing service address possible.

## 16. Queues, jobs, and background tasks during failover

Shifting HTTP requests is only part of the system. Pub/Sub consumers, Cloud Run Jobs, scheduled jobs, and GKE/VM workers may keep running in A even after the frontend moves to B.

Before letting B process side-effecting jobs, verify:

1. Who owns scheduled jobs or acts as periodic task leader?
2. Are consumers in A holding unacknowledged messages?
3. Will messages be redelivered if A dies, and are handlers idempotent?
4. When B uses the new database, can it read accurate reference data to process older messages?
5. Do DLQs, retry policies, and retention still cover the recovery window?

A system may need to pause consumers briefly to ensure B's writer and schema are ready. Monitor backlogs, oldest unacked message age, drain rate, and downstream health after resuming. Never treat a shrinking backlog as business success if workers are merely acking messages while dropping write errors.

## 17. Failback is not simply reversing failover

Once A recovers, B may now be the valid source of truth holding fresh changes. Switching traffic straight back to A before A receives those changes can drop orders, serve stale data, or create dual writers.

Failback is a planned change requiring these conditions:

- A runs stably and the incident root cause is resolved—not merely restarted.
- Data in A is resynchronized from the current source of truth B; verify lag and consistency checkpoints.
- Infrastructure, IAM, secrets, schemas, and artifacts in A match the versions running in B.
- Safe write-authority transfer and fencing for the retiring writer are ready.
- A rollback path back to B exists if A misbehaves and data state permits.
- Users and external partners are notified if a read-only or maintenance window is needed.

Never assume replication automatically reverses after promoting B. With Cloud SQL or other databases, rebuilding replicas or configuring reverse replication must follow supported service workflows; it may require creating a new replica, backup/restore, or significant sync time.

Some organizations choose **not to fail back immediately**, letting B remain primary longer to avoid another risky switchover. This can be the right call if B has full capacity, meets residency/latency rules, and has DR re-established for the next incident.

## 18. Controlled failback runbook

| Stage | Actions | Completion evidence |
| --- | --- | --- |
| B0. Assess A | Verify root cause fix, supporting systems, and A readiness | SLIs and health recovered over observation window |
| B1. Establish source | Confirm B is the valid post-failover data source | Checkpoints and transaction reconciliation table ready |
| B2. Re-seed/re-replicate | Rebuild or sync data back to A per service mechanism | A caught up and passes read verification |
| B3. Dry run | Test A in read-only or non-side-effecting mode | Critical read journeys and capacity PASS |
| B4. Plan write cutover | Pause/throttle writes, drain jobs, clear in-flight transactions | Zero uncontrolled open writes remaining |
| B5. Fence B; activate A | Transfer writer per supported workflow; lock B if single-writer | A is sole writer; consistency verified |
| B6. Shift traffic | Route HTTP/gRPC and workers back to A safely | Error rate, p95, backlog, and data checks PASS |
| B7. Rebuild standby | Reconfigure B back into standby with properly oriented replication | DR topology restored to protected state |
| B8. Close incident | Evaluate RTO/RPO, data discrepancies, and lessons learned | Runbook, dashboards, and decisions archived |

In stage B5, exact execution order depends on the database type and product-supported procedures. Never force manual leader changes outside the managed service's architecture. For platforms with automatic failover, use official semantics instead of promoting a replica with unsupported commands.

## 19. Post-cutover data and transaction reconciliation

A ping or health check will not detect lost transactions. To confirm recovery, include these checks:

- **Transaction IDs:** which transactions occurred before/after writer cutover, and are any missing or duplicated?
- **Watermarks/checkpoints:** up to what offset or timestamp did event processors finish?
- **Read-after-write:** can newly created transactions in B be read back from the right source?
- **Object-to-record:** do database records referencing Cloud Storage objects find their corresponding objects?
- **External side effects:** did emails, payments, or callbacks duplicate due to retries?
- **Schema/versions:** does region B have migrations/schemas compatible with current app code?

If RPO is non-zero, transparently document potential data loss bounds and recovery procedures from event logs, partners, or backups where feasible. Never claim RPO was met simply because replication lag looked like 0 at check time: inspect the exact disconnect timestamp and evidence from the real incident.

For workflows prohibiting duplicate transactions, use idempotency keys and durable processing state. Retries should use exponential backoff and bounded attempts; unbounded retries while data is unready will overload region B.

## 20. Observing failover: what to measure?

DR dashboards and alerts should track three signal groups:

| Group | Metrics or evidence |
| --- | --- |
| User experience | Availability, p95/p99 latency, HTTP/gRPC errors, real transaction outcomes |
| Routing and capacity | Backend health per supported type, per-region RPS, instance/pod counts, CPU/RAM, connection pools, queues |
| Data and correctness | Replication lag, writer identity, checkpoints, transaction conflicts, backlog, oldest unacked age |

An incident timeline should capture:

~~~text
T0  Incident begins affecting users
T1  Alert detected and incident opened
T2  Regional failover decision approved
T3  Old writer fenced or writes secured
T4  Data in B ready to serve
T5  Traffic shifted to B
T6  Business journeys and SLOs stabilize
T7  Standby capability restored; failback planned
~~~

Observed RTO must span from loss of business function until function restoration, not merely the runtime of a traffic-cutover script. Log failed request counts, impacted transactions, and potential data loss to evaluate true impact.

Audit trails should record decision makers, before/after configs, source revisions, change timestamps, identities used, and health check outputs. Never record credentials or sensitive payloads in public tickets or logs.

## 21. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Deploying only frontends in two regions | Database writer remains a single point of failure | Design DR across every critical dependency |
| Treating healthy backends as ready data | False-positive successes or corrupted writes | Use separate health and data-readiness gates |
| Opening writer B before fencing A | Risk of split-brain and diverging data | Enforce single writer via supported mechanisms |
| Assuming DNS edits switch all clients instantly | Caches and old connections keep hitting A | Measure real clients; use draining and idempotency |
| Treating Cloud SQL regional HA as cross-region DR | A region outage still halts data | Build a dedicated cross-region plan |
| Equating backups with replication | Backups can be stale; replicas replicate logical bugs | Maintain both DR replication and backup/restore |
| Shifting 100% traffic before B has capacity | Overload, timeouts, cascading failures | Load-test and verify B autoscaling beforehand |
| Shifting HTTP while forgetting workers | Jobs in A and B double-process side effects | Migrate leaders/consumers alongside data |
| Failing back to A while A holds stale data | Loses transactions written while running in B | Reverse replication, fence, reconcile, then cut over |
| Drilling once without measuring RTO/RPO | Misses config drift and dependency breaks | Drill periodically, record metrics, and remediate |
| Skipping IAM/secret checks in B | Standby region boots yet fails to operate | Test identities and critical journeys in B |

## 22. Safe failover and failback drills

Before the first drill, use a test project/app with synthetic data and spend limits. Never cut production traffic or promote a production database without formal approval, on-call staffing, and a concrete rollback plan.

An incremental drill progression:

1. **Tabletop exercise:** teams walk through every runbook step and confirm roles, comms channels, and approvals.
2. **Read-only dry run:** verify connectivity, B configs, IAM, routes/DNS, SLOs, and replication state without changing writers.
3. **Canary traffic:** shift a slice of read requests in a test environment with representative data.
4. **Controlled failure:** simulate an A endpoint failure and verify traffic failover behavior per supported policies.
5. **Data promotion rehearsal:** practice writer promotion and consistency checks on a test database.
6. **Failback rehearsal:** sync back, return write authority, and re-establish B as standby.
7. **Peak-load check:** verify B sustains target load without overloading dependencies.
8. **Postmortem:** record observed RTO/RPO, bugs, manual steps, and safe automation improvements.

You do not necessarily have to destroy resources to test region loss. Traffic controls or scoped fault injection in test environments work, provided the scenario genuinely tests relevant failure modes: network partitions, writer loss, DNS errors, and broken dependencies.

Every drill must define **abort criteria**: if data corrupts, costs spike beyond bounds, or out-of-scope systems are affected, stop and recover immediately per the runbook. Abort criteria must stand independent of the test's success conditions.

## 23. Lab exercise: two-region ordering application

**Context:** a Spring Boot API runs on Cloud Run in region A (`asia-southeast1`) and B (`asia-east1`). The data backend uses a primary database in A and a replica mechanism in B verified by the team to support organizational recovery goals. A global entrypoint fronts both APIs.

Hypothetical targets: 30-minute RTO, 10-minute max RPO, at least 99.5% success rate on critical operations after failover during stabilization. These values are strictly for the exercise and are not default guarantees of GCP services.

Tasks:

1. Build a dependency map covering Cloud Run, database, Secret Manager, IAM, Artifact Registry, Pub/Sub, and partner services.
2. Choose warm standby or hot standby and estimate costs of maintaining B.
3. Design failure detection signals and failover decision thresholds.
4. Write a plan to fence writer A before B accepts writes, aligned with database product capabilities.
5. Prepare read/write, transaction ID, and replication lag verification checks.
6. Describe how the global entrypoint directs new requests to B while handling existing sessions / gRPC connections.
7. Construct a T0–T6 timeline to measure RTO and report actual RPO.
8. Simulate B acting as primary for a period, generating new data, and design reverse replication.
9. Write failback steps back to A without losing new writes committed in B.
10. Create a post-cutover verification checklist covering latency, errors, backlog, and audit trails.

**Deliverables:** diagrams, dependency readiness matrix, data-loss risk table, traffic-shifting policy, failover/failback runbook with named owners, test evidence, and RTO/RPO reconciliation report. Never fabricate latency or replication lag numbers as if measured from a live system.

## 24. Production checklist for safe cross-region cutover

- Approved RTO/RPO, SLIs/SLOs, and incident scope exist for every critical function.
- Inventories exist for apps, data stores, jobs, secrets, IAM, DNS, networking, and external services in both regions.
- B holds required artifacts, capacity, configs, permissions, and dependencies to serve traffic.
- Frontend failover is clearly distinguished from data write-authority failover.
- Evidence exists for replication lag, data checkpoints, backups, and data-loss bounds.
- Split-brain prevention and old-writer fencing mechanisms are in place for role changes.
- Load balancing or DNS steering strategy is supported for the specific backends and tested.
- Sessions, long-lived connections, queue consumers, retries, and idempotency have been tested.
- Traffic shifting is gated on health and data readiness, not a single health endpoint.
- Runbook names the incident commander, data promotion approvers, and abort criteria.
- B is verified to handle expected load, including database connections and autoscaling.
- Dashboards track per-region RPS, errors, latency, writer state, lag, and backlogs.
- Failback covers reverse sync, reconciliation, write cutover, and standby re-establishment.
- Periodic drill schedule and change management exist as architecture evolves.
- Zero secrets appear in deployment code or incident docs; DR permissions follow least privilege.
- Post-drill/incident actual metrics are recorded with remediation items and owners.

Successful failover is not when a DNS record updates or a load balancer picks another backend, but when users can continue transacting accurately in the recovery region within agreed RTO/RPO bounds. Failback completes only when data, write authority, traffic, and standby capacity are verifiably restored. On Google Cloud, pairing suitable traffic shifting with accurate data models, SLO-driven observability, and regular drills turns a multi-region architecture into a dependable DR plan rather than merely two parallel deployments.
