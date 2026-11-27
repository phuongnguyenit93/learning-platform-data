# Designing for Resilience Instead of Assuming Infrastructure Always Works

When deploying applications to the cloud, you cannot assume servers, networks, disks, deployment zones, or dependent services will always stay healthy. An instance can be replaced, requests can time out, a database can overload, an availability zone (AZ) can lose connectivity, and a faulty deployment can affect every replica. A reliable architecture must anticipate those scenarios starting right when business requirements are defined.

In the **CLOUD_ARCHITECTURE** module, this principle connects **networking, compute, data, and deployment model** decisions with the ability to guarantee service for users. The goal is not to build a system claiming "it never fails," but to **limit the blast radius, preserve critical flows, protect data, and recover within acceptable timeframes**. These decisions must be balanced against cost, security, scalability, and operations under Well-Architected thinking.

## 1. Why Must We Assume Failures Will Happen?

A business journey typically spans multiple systems:

~~~mermaid
flowchart LR
    U["Users"] --> EDGE["DNS / CDN / WAF"]
    EDGE --> LB["Load balancer"]
    LB --> APP["Application"]
    APP --> DB["Database"]
    APP --> CACHE["Cache"]
    APP --> THIRD["External service"]
~~~

One poorly performing component can trigger cascading failures. For example, a latency spike in a payment API causes application threads to wait; connection pools exhaust; normal lookup requests start timing out even though the database is healthy. Adding more instances may not help if every instance depends on that same API.

Instead of asking "is this instance stable?", an architect needs to ask:

1. If an instance drops abruptly mid-request, what is the transaction outcome?
2. If a dependency stays up but responds ten times slower, does the system bound its wait time?
3. If an AZ becomes isolated, is the remaining capacity and data sufficient to serve core journeys?
4. When a client times out even though the transaction may have succeeded, how do we avoid duplicate processing?
5. If data is accidentally deleted or corrupted via replication, where can we recover from and how long will it take?
6. Who detects the issue, authorizes failover, and verifies recovery?

### Distinguishing Reliability, Availability, and Resilience

| Term | Meaning | Example |
| --- | --- | --- |
| **Reliability** | The system performs its committed function accurately over a specified time and set of conditions | A booking is recorded exactly once with the right state |
| **Availability** | Percentage of time or requests for which the service is usable under a defined measurement | Booking API meets its SLO target |
| **Fault tolerance** | Continuing the defined function when a component fails | Losing one instance while the load balancer routes to healthy instances |
| **Resilience** | Absorbing, adapting to, and recovering from disruptions | Disabling personalized recommendations when a secondary service fails, then re-enabling |
| **Disaster recovery (DR)** | Recovering from major incidents beyond normal fault-tolerance scope | Failing over to a backup region after a widespread outage |

**Redundancy is a tool, not the end result.** Two instances sharing a single database, identical misconfiguration, or the same quota limit can both stop serving simultaneously.

## 2. Starting from Business Impact and Measurable Targets

Not every feature needs to recover at the same speed. A booking application may need to preserve **booking and payment** operations even when **personalized recommendations** or **email sending** fail.

| Journey | When a Dependency Fails | What Must Be Preserved |
| --- | --- | --- |
| Browse availability | Can display cached results labeled with freshness | Never use stale cache as definitive proof of slot availability |
| Create booking | Can return an indeterminate status and allow lookup afterward | No double-booking, no loss of committed state |
| Payment | Temporarily hold a verifying state, reconcile as needed | Never charge twice or falsely report success |
| Personalized recommendations | Hide the feature or fall back to defaults | Booking journey keeps working |
| Confirmation emails | Record an event for asynchronous delivery | Never fail a committed transaction solely because of email |

Product and operations teams must align on:

- **SLI (Service Level Indicator):** a measured quantity, e.g., ratio of valid booking requests returning an accurate result within 2 seconds.
- **SLO (Service Level Objective):** the target for an SLI over a window, e.g., 99.9% of valid requests over 30 days. Must define which requests count, client-side errors, the measurement window, and measurement point.
- **SLA (Service Level Agreement):** a service commitment that may carry contractual terms, not necessarily identical to technical SLOs.
- **RTO (Recovery Time Objective):** the target maximum time to restore service after a defined incident type.
- **RPO (Recovery Point Objective):** the target maximum data loss interval measured in time at the recovery point. A 5-minute RPO means that within the defined incident scope and recovery mechanism, the organization accepts potentially losing changes from up to roughly 5 minutes prior to the incident.

If a **time-based** SLO is 99.9% over 30 days, the unavailability budget equals:

\[
(1-0.999)\times30\times24\times60=43.2\text{ minutes}.
\]

If the SLO is defined by **good request ratio**, compute the error budget in request counts rather than directly converting to minutes of downtime. A failover finishing in 4 minutes does not automatically prove SLO compliance if it happens too often or if many requests keep failing afterward.

**RTO/RPO must be tied to failure domains.** Restarting an instance may lose zero data; losing an AZ may require database failover; losing an entire region may require restoring elsewhere, longer recovery times, and risk of losing unreplicated writes. Do not pick one generic RTO/RPO pair and apply it to every incident.

## 3. Identifying Failure Domains and Shared Dependencies

A failure domain is a group of components that can be affected simultaneously by a single fault. When designing, mark boundaries from processes up to regions as well as shared logical dependencies.

| Failure Domain | Incident Example | Controls to Evaluate |
| --- | --- | --- |
| Process/container | Crash, deadlock, out-of-memory | Health checks, restarts, resource limits |
| Host/node | Server hardware failure or replacement | Multiple replicas, anti-affinity across nodes |
| Availability zone | Connectivity loss or local infrastructure outage | Multi-AZ, load balancing, HA database |
| Region | Widespread outage or reachability loss | Cross-region DR, replicated data, traffic redirection |
| Dependency | External API, cache, database slow/overloaded | Timeouts, conditional retries, circuit breakers, bulkheads |
| Shared logic fault | Bad release, expired secret, shared misconfiguration | Canary, rollback, feature flags, change control |
| Data/security | Accidental deletion, corruption, malware, compromised account | Independent backups, audits, authorization, point-in-time recovery |

**Multi-AZ is not multi-region, and multi-region does not inherently prevent logical data corruption.** A bad write can replicate rapidly to every region. Replicas used to keep serving and backups used to restore to a valid state serve different purposes.

Beyond the main boxes on a diagram, check shared dependencies such as DNS, identity providers, secret stores, CI/CD, key management systems, queues, payment APIs, and egress networking. Two compute clusters in two AZs can still fail together if both share an invalid credential config.

## 4. Deploying Compute and Data to Tolerate Component Loss

Applications must **be able to replace instances without losing business state**: store critical sessions in an appropriate managed store rather than trusting local container disks; deploy through repeatable configurations; distinguish *ready to receive requests* from *process alive*.

~~~mermaid
flowchart TB
    C["Client"] --> LB["Edge / load balancer"]
    subgraph R["Primary Region"]
      subgraph A["Availability Zone A"]
        APP1["App A"]
        PRIMARY["DB writer"]
      end
      subgraph B["Availability Zone B"]
        APP2["App B"]
        STANDBY["DB standby"]
      end
      QUEUE["Durable queue"]
      WORKER["Worker"]
    end
    LB --> APP1
    LB --> APP2
    APP1 --> PRIMARY
    APP2 --> PRIMARY
    PRIMARY <-->|"Replication / failover"| STANDBY
    APP1 --> QUEUE
    APP2 --> QUEUE
    QUEUE --> WORKER
~~~

This diagram is a **design concept**, not an availability guarantee. You must verify actual failover, quorum, replication lag, how the app discovers the new writer endpoint, whether the queue remains operational, and network paths when an AZ disappears.

Decisions requiring clarification:

1. **Compute distribution:** multiple instances across distinct failure domains; the load balancer routes traffic only to instances passing readiness checks.
2. **Readiness differs from liveness:** failed readiness temporarily stops an instance from receiving requests; failed liveness triggers a restart. Avoid mass-restarting instances just because a dependency is slow.
3. **Graceful shutdown:** stop accepting new requests, drain in-flight work, then close resources within a bounded timeout.
4. **State decoupled from compute:** sessions, background jobs, idempotency keys, and business data reside in stores with appropriate durability, backups, and recoverability.
5. **Capacity after component loss:** autoscaling takes time, so verify the surviving capacity can handle load before replacement capacity comes online.

Example: peak load is **600 RPS**, and benchmarks show each instance sustainably serves **120 RPS** within SLO. Looking strictly at throughput requires at least \(600/120=5\) instances. Placing 3–3 across two AZs gives 6 instances total, yet losing one AZ leaves only **360 RPS** capacity. To maintain the full 600 RPS upon losing an entire AZ, each AZ needs **at least 5 ready instances** under this simplified assumption. Redundancy cost rises, while database, network, and dependencies must still be checked independently; three-AZ architectures may allow different distribution layouts.

## 5. Designing Calls to Withstand Timeouts, Flakiness, and Overload

In distributed systems, **a timeout does not mean the operation failed**. For example, a client submits a payment command, the server deducts funds, and the response is lost on the network. If the client sends a fresh command without duplicate protection, the user may be charged twice.

### Timeouts and Deadlines

Every outbound connection must have **explicit wait limits**. Connect timeout differs from response timeout, and each request must obey an end-to-end deadline. It makes no sense for an API promising a 2-second response to let a dependency take 5 seconds and retry several more times.

Example of a 2-second maximum processing budget for an API:

| Activity | Illustrative Budget |
| --- | ---: |
| Request validation and authentication | 200 ms |
| Database | 450 ms |
| External service, including retries if any | 800 ms |
| Serialization, network, and headroom | 550 ms |
| **Total** | **2,000 ms** |

A budget is only a design tool and does not prove p99 latency meets SLO; queue wait times, tail latency distributions, contention, garbage collection, and actual downstream limits also apply.

Java example using an HTTP client with timeouts:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;

class PaymentClient {
    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofMillis(300))
            .build();

    HttpResponse<String> submitPayment(
            URI paymentUri, String jsonBody, UUID operationId
    ) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(paymentUri)
                .timeout(Duration.ofMillis(800))
                .header("Content-Type", "application/json")
                .header("Idempotency-Key", operationId.toString())
                .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
~~~

To be effective, **`operationId` must be durably persisted and reused for the same transaction**, and the payment service must genuinely support idempotency keys. Adding a header alone does not create idempotency. If the call times out, the application must record an indeterminate state and query or reconcile per the API contract. This Java example only illustrates setting timeouts; real implementations must also handle status codes, exceptions, deadline propagation, logging, and protecting sensitive data.

### Conditional Retries Without Amplifying Failures

Retries can overcome transient errors, provided these rules are followed:

- Only retry operations that are inherently safe to repeat or have **idempotency** guaranteed by the processor.
- Cap attempt counts and use **exponential backoff** with **jitter** to prevent synchronized retry storms across clients.
- Respect the overall deadline, retry-after hints from downstream (if provided), and system load thresholds.
- Place retries at one intentional layer. If three layers each independently retry up to three times, a single top-level request can trigger \(3\times3\times3=27\) calls at the deepest layer in the worst error path.
- Monitor retry counts, post-retry success rates, and wait times; requests "succeeding" after many retries still signal an unhealthy dependency.

Key complementary patterns:

| Pattern | When to Use | Critical Limitations |
| --- | --- | --- |
| **Circuit breaker** | Dependency fails/slows persistently; pause calls briefly then probe recovery | Does not replace timeouts; requires measuring and tuning thresholds |
| **Bulkhead** | Isolate connection pools, threads, and concurrency across flows to stop failure spread | Poor partitioning can still starve critical flows |
| **Rate limiting** | Cap inbound/outbound rates to protect backends | Does not account for calls with vastly different resource costs |
| **Backpressure** | Signal producers when consumers reach processing capacity | Requires rules for queuing, rejecting, or buffering |
| **Load shedding** | Controlled rejection of low-priority requests under overload | Requires request classification and clear signals to clients |
| **Queue** | Decouple execution timing of tasks not strictly synchronous | Introduces backlog, duplicate messages, and queue capacity limits |

A well-timed circuit breaker can halt cascading failures. Yet if the application still holds thousands of pending requests in memory, load can keep climbing. Limits must align across layers: timeouts, concurrency, queue depth, retry budgets, and downstream throughput.

## 6. Intentional Graceful Degradation

Resilience does not require every feature to run at full capability under all conditions. When an auxiliary dependency fails, the system can preserve core business journeys:

- Hide recommendations when the recommendation service is unavailable.
- Serve cached responses clearly displaying update timestamps for data tolerant of staleness.
- Offload emails, report generation, or analytics ingestion to queues for deferred processing.
- Restrict expensive search queries when the database is overloaded, reserving capacity for critical transactions.

**Not all data allows fallback.** Never use stale cached availability to guarantee a slot is open, never report a payment successful without confirmation, and never bypass authentication/authorization because a security service is degraded. For sensitive actions, failing closed in a controlled manner or returning a "verifying" status is safer.

Each fallback needs defined trigger conditions, maximum staleness, user-visible behavior, restricted features, recovery deactivation logic, and signals proving health is restored. When everything recovers, prevent returning traffic spikes from triggering another overload.

## 7. Protecting Data When Systems Fail

Adding compute instances only protects processing capacity. In transactional applications, the core goal is also **never losing, duplicating, or corrupting business state**.

### Idempotency and Indeterminate Outcomes

Idempotency means executing the same valid operation multiple times yields **the same final business effect as executing it once**. For example, a booking creation API accepts a client-generated request ID and stores it alongside the processed outcome. When the client retries with the same key, the server returns the matching outcome without creating an extra booking.

To work reliably in practice, define:

1. Key uniqueness scope (e.g., per user and operation), retention duration, and policy for receiving a different payload with the same key.
2. How the key is synchronized with the business commit to prevent race conditions between concurrent requests.
3. Responses for in-progress, succeeded, retryable-failure, or indeterminate states.
4. Reconciliation procedures with external systems, especially when transactions span beyond a single database.

### Transactional Outbox and Queues

Suppose the API creates a booking and then emits an email-sending event. If the database commits and the app crashes before publishing, the booking exists while the notification is lost. The **transactional outbox** pattern writes both the booking and the event into **the same database transaction**, after which a relay reads the outbox and publishes to the queue.

~~~mermaid
sequenceDiagram
    participant Client as User
    participant API as Booking API
    participant DB as Database
    participant Relay as Outbox relay
    participant Q as Queue
    participant W as Notification worker
    Client->>API: POST booking + idempotency key
    API->>DB: Transaction: booking + outbox event
    DB-->>API: Commit
    API-->>Client: Booking accepted
    Relay->>DB: Read unsent outbox
    Relay->>Q: Publish event
    Q-->>W: Deliver (may duplicate)
    W->>W: Dedupe and execute
~~~

The relay can still publish successfully and crash before marking the record sent. Therefore, messages may be **redelivered**, and workers must be idempotent or deduplicate appropriately. Monitor outbox age, queue lag, retries, dead-letter queues, and backlog drain capacity. Do not assume having a queue implies end-to-end "exactly once"; broker semantics may not cover side effects in another database or email provider.

### Replication and Backups Serve Different Purposes

| Mechanism | Benefit | Limits / Trade-Offs |
| --- | --- | --- |
| Synchronous/quorum replication | Reduces risk of losing committed writes under specific failure modes | Increases write latency; losing quorum can halt writes |
| Asynchronous replication | Lowers write wait times and supports wider geographic distance | Lagging replicas; failover risks losing unreplicated writes |
| Multi-primary / active-active | Can serve writes across multiple locations | Conflicts, ordering, network partitions, complex consistency |
| Backups and point-in-time recovery | Restores state prior to accidental deletion or bad writes | Requires restore time, log retention, and backup testing |

**Zero RPO is a demanding requirement:** you must specify incident scope, commit confirmation mechanisms, and data product limits. Never infer zero RPO merely from having replicas. During failover, prevent **split-brain** (two writers accepting writes simultaneously) via leader election, fencing, quorum, or appropriate controls; applications must reconnect cleanly and resolve in-flight transactions.

Backups should have clear schedules and retention, scoped restore permissions, encryption, independent access controls, and immutability where needed. **Replicas do not replace backups**, because accidental deletions replicate immediately. Backups are only trustworthy once restores have succeeded and post-restore data integrity is verified within the target recovery window.

## 8. Choosing a Disaster Recovery Strategy Based on RTO/RPO

When an outage exceeds the redundant failure domain, the system needs a **disaster recovery (DR)** plan. Common approaches:

| Strategy | Standby Infrastructure | Recovery Characteristics | Cost and Risks |
| --- | --- | --- | --- |
| **Backup and restore** | Store backups; rebuild system when needed | Must restore data, provision resources, and verify | Low running cost, typically longer RTO |
| **Pilot light** | Keep core data components and minimal baseline running | Spin up remaining services and switch traffic | Moderate cost, still depends on provisioning time |
| **Warm standby** | Maintain a scaled-down standby environment | Scale up capacity and switch traffic when needed | Higher ongoing cost; scaling must be tested |
| **Active-active** | Multiple sites actively serve traffic | Enables fast traffic shift in suitable scenarios | Complex routing, write conflicts, consistency, cost |

You cannot assign fixed RTO/RPO numbers to each label; actual results depend on data volume, replication lag, available capacity, traffic cutover speed, and operator readiness. DNS cutover is **not instantaneous** due to TTLs, resolver caches, open connections, and client behavior.

A DR runbook should answer:

1. **When to trigger:** which incidents, which SLIs, and who holds authority to fail over regions?
2. **Isolate the old site:** how to stop two database writers from both accepting writes if the old region partially recovers?
3. **Choose recovery point:** how current is replicated data, and which transactions require reconciliation?
4. **Bring up the new site:** how ready must networking, compute, secrets, DNS, databases, queues, and quotas be?
5. **Verify critical flows:** test sign-in, reads, **and transaction writes**, not just opening the home page.
6. **Shift traffic and communicate:** monitor errors, latency, performance; define clear rollback criteria.
7. **Failback:** reconcile new writes made in the backup site before bringing the primary site back into service.

**Security must still be enforced during DR:** least-privilege access, encryption key governance, auditing, preventing data transfer into unauthorized jurisdictions, and backup protection. Opening wide permissions on a standby environment for "fast recovery" can create greater risk than the original outage.

## 9. End-to-End Example: Cloud Booking Platform

Suppose the development team sets **illustrative** targets that must be validated with business stakeholders and load tests before commitment:

| Journey / Incident | Hypothetical Target |
| --- | --- |
| Booking API | 99.9% of valid requests return accurate results within latency threshold over a 30-day window |
| Single app instance loss | Service continues on remaining instances; brief errors stay within error budget |
| Single AZ loss | Target RTO 5 minutes for booking journey; zero data loss within database commitment scope |
| Region loss | Target RTO 60 minutes, target RPO 5 minutes |
| Email service outage | Bookings still commit; events are persisted for processing once email recovers |

One design direction runs compute across multiple AZs behind a load balancer, a database supporting HA/failover, a durable queue for background work, isolated backups with tested restore workflows, and user-journey monitoring. Beyond the diagram, verify network routes, quotas, secrets, identity providers, and operability if part of the control plane is unreachable.

### Scenario A: Instance Crashes Mid-Booking

Health checks and the load balancer detect the unhealthy instance within a verified interval. New traffic shifts to surviving instances; the scheduler launches a replacement if needed. In-flight requests may lose responses. Clients retry with the **same idempotency key** or query the created result. The system tracks error rates, tail latency, and load capacity of remaining instances.

If critical sessions lived only in the crashed instance's RAM, users lose their sessions. If backends held business locks in local memory, two instances could process the same booking. Proper state placement and concurrency controls are required; adding replicas alone will not fix these issues.

### Scenario B: Email Service Down for 30 Minutes

Bookings still persist and events enter the outbox/queue. Workers retry with backoff and caps; the queue is monitored by depth/lag, dead-letter count, and processing rate. When email returns, workers drain the backlog **at a controlled rate** to avoid creating a secondary overload. Consumers must prevent duplicate sends or handle duplicates according to business contracts.

### Scenario C: Payment Gateway Times Out

The client receives a **"verifying payment"** status with a tracking reference. The system retains the operation key, reconciles with the payment gateway, and handles late or duplicate callbacks/webhooks. It transitions to "paid" only upon verified confirmation. A timeout does not prove the payment failed, so issuing a new payment command with a different key risks double-charging.

### Scenario D: Total Loss of an AZ

Applications in the surviving AZ must hold real capacity; databases and queues must remain reachable; writer failover, DNS/endpoint resolution, and connection pools must recover. Measure **from the moment the booking journey starts failing until normal service resumes**, because the database may promote a writer in one minute while the app keeps failing for several minutes if holding stale connections and endpoints.

### Scenario E: Primary Region Outage

Operations triggers DR, verifies the latest replicated data timestamp, fences the old writer to avoid split-brain, launches or scales up the backup site, and tests read/write operations. Next, shift traffic and measure **actual RTO/RPO** against the 60/5-minute targets. If missed, revise the design or renegotiate business expectations; never declare success just because the landing page loads.

## 10. Observability and Operations Are Also Components of Resilience

A system with replicas, autoscaling, and backups lacking alert signals, on-call staff, and runbooks can still recover very slowly. Observability must reflect **user experience**, not merely "green" infrastructure indicators.

| Signal | Examples to Measure | Meaning |
| --- | --- | --- |
| **Traffic** | RPS by endpoint, AZ, region, and journey | Is traffic piling onto surviving capacity? |
| **Errors** | 5xx, timeouts, business errors, indeterminate outcomes | How severely are users affected? |
| **Latency** | p50, p95, p99; queue wait times | Is performance degrading prior to hard failure? |
| **Saturation** | CPU/RAM, connection pools, thread pools, IOPS, queue depth | How much headroom remains? |
| **Data health** | Replica lag, backup age, outbox lag, restore success | Is there risk of losing data or events? |
| **Recovery** | Time to detect, failover duration, rollback duration | Are we meeting defined RTO? |

Alerts should prioritize **user impact** and **error budget burn rate**. 80% CPU alone does not prove an incident, whereas a sudden spike in failed booking requests demands immediate attention even at low CPU. Distributed tracing with correlation IDs helps follow requests across APIs, databases, queues, and dependencies. Logs and traces must avoid recording tokens, passwords, or sensitive payment data.

Practical runbooks must help on-call engineers answer: which dashboards to inspect; when to roll back, scale out, or fail over regions; how to verify data integrity; who can authorize changes; and what incident closure criteria apply. Post-incident, a blameless postmortem focused on systemic causes improves processes, alerts, and architecture.

## 11. Deliberate Fault Testing to Verify Assumptions

Load testing answers whether a system has capacity under normal conditions. **Resilience testing** answers which functions survive when a component breaks, how long recovery takes, and whether data stays accurate.

| Test | Expectation to Define Up Front | Measured Evidence |
| --- | --- | --- |
| Kill one instance under representative load | Traffic shifts to healthy instances | Error rate, tail latency, session loss, recovery time |
| Inject multi-second latency on a dependency | Timeouts and circuit breakers prevent resource exhaustion | Thread/connection usage, retries, rejected requests |
| Cut connection to database writer | Failover and reconnect behave as designed | Write recovery duration, indeterminate transactions |
| Stop email worker | Bookings continue; backlog accumulates under control | Queue depth, lag, dead-letter count, drain time |
| Replay duplicate payment callbacks | No duplicate recording or double-charging | Idempotency, transaction state, audit trail |
| Restore from backup | Data is accurate and usable within RTO/RPO | Restore duration, recovery point, integrity checks |
| Lose an AZ or region in a permitted environment | Committed journeys recover on time | Client-side SLI/SLO and measured RTO/RPO |

A sound drill workflow:

1. **Formulate a hypothesis:** "Losing one instance does not disrupt bookings beyond the defined error budget."
2. **Establish steady state:** measure journeys and baseline load before testing.
3. **Select a safe blast radius:** start in staging or a small scope with abort triggers and a rollback plan.
4. **Inject an explicit fault:** process crash, delay, packet loss, resource exhaustion, or controlled failover.
5. **Measure end-to-end impact:** from client to database and background jobs; verify data correctness too.
6. **Fix and retest:** archive evidence, update runbooks, configurations, and standby capacity.

Testing in staging does not prove production will behave identically because traffic, data, and quotas differ. If drilling in production, enforce strict blast-radius limits, accountable owners, and rapid abort controls. A chaos test that "caused zero errors" is meaningless if the tested component sits outside critical business paths.

## 12. Trade-Offs Across Well-Architected Pillars

| Decision | Resilience Benefit | Cost / Limitation |
| --- | --- | --- |
| Multi-AZ | Reduces dependence on one failure domain | Standby resources, cross-AZ traffic, replication latency |
| Multi-region | Reduces dependence on one geography | Routing, consistency, data residency compliance, operational complexity |
| Synchronous replication | Reduces risk of losing committed writes | Higher write latency; requires quorum to keep writing |
| Retries | Absorbs transient errors | Retry storms, amplified load, duplicate side effects |
| Queues | Decouples task execution timing | Backlogs, duplicate delivery, longer end-to-end completion |
| Caching | Reduces dependency load and latency | Stale data, invalidation, cache stampedes |
| Graceful degradation | Preserves priority journeys when dependencies fail | Reduced functionality; must still protect correctness |
| Warm standby | Can shorten RTO | Continuous standby cost; requires failover drills |
| Independent backups | Recovers from accidental deletion or corruption | Storage cost, restore drills, and periodic verification |

Reliability evaluation must pair with **security**, **performance**, **cost**, **operations**, and **sustainability**. High replica counts only make sense when business value justifies them; conversely, under-provisioning redundancy can cause damages far exceeding the savings. Use SLOs, RTO/RPO, and testing to select a sustainable level of complexity.

### Design Review Question List

- Have critical journeys that must survive been separated from features allowed to degrade?
- Do SLOs, RTOs, and RPOs have clear scope, units, owners, and measurement methods?
- Upon losing an instance or AZ, is surviving capacity genuinely sufficient?
- Are timeouts, retries, circuit breakers, and concurrency limits configured consistently across layers?
- Do write APIs enforce idempotency, and do external integrations have reconciliation?
- Are queues, databases, caches, DNS, secrets, and identity systems included in the dependency map?
- Are backups independent, encrypted, and proven to restore within target timeframes?
- Are user-impact alerts, runbooks, rollbacks, and live drills in place?

## 13. Self-Check Exercises

An application has a peak load of **800 RPS**. Benchmarks show each instance sustainably serves **200 RPS** at the required SLO. The application runs across two AZs and must continue handling **800 RPS** if one AZ is completely lost. Assume the database and network have sufficient capacity, without adding extra headroom factors yet.

**Question 1:** What is the minimum number of instances needed in each AZ?

**Solution:** After one AZ fails, the remaining AZ needs \(800/200=4\) instances. Therefore, at least **4 ready instances are needed in each AZ, totaling 8**, assuming compute is independent per AZ. Autoscaling additional capacity after the outage starts is insufficient to guarantee immediate load handling.

**Question 2:** If the database writer sits in only one AZ, does the setup above guarantee uninterrupted bookings upon losing an AZ?

**Solution:** No. If the AZ hosting the database is lost, compute in the other AZ cannot complete transactions requiring the database. Database HA/failover mechanisms, replication strategies, and full-journey RTO/RPO testing are required.

**Question 3:** The email worker stops for 20 minutes. Should recently committed booking orders be rolled back?

**Solution:** If email is not a mandatory synchronous condition of the transaction, commit the order, persist the event durably via outbox/queue, and send later. Monitor backlog and prevent duplicate sends when the worker recovers.

**Question 4:** A client submits a payment and receives a timeout. Should it create a new command with a different idempotency key?

**Solution:** No. The first command may already have succeeded. Retain the original transaction key, query/reconcile per the API contract, and only confirm status with reliable evidence.

When presenting an architectural proposal, always state **which faults the system tolerates, which faults require recovery, which data must be protected, which measurements prove targets are met, and what operational costs accompany them**. That is how designing for resilience turns into verifiable engineering decisions.
