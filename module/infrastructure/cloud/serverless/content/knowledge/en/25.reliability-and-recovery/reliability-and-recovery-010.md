# Chaos Testing and Regional Failover Drills

Serverless applications scale automatically and run on cloud-provider-managed infrastructure, yet that does not mean they automatically recover from every outage. A function can still time out when a database slows down, process duplicate messages during retries, get throttled under concurrency spikes, lose connectivity after network faults, or become unavailable when the primary Region fails. Without testing these scenarios proactively, a team only knows how the system behaves under normal conditions.

**Chaos testing** is the practice of deliberately injecting controlled faults to test hypotheses about a system's fault tolerance. **Regional failover drills** validate the ability to shift workloads to a standby region, restore data, and return traffic to a stable state. Both require clear objectives, defined scope, stop conditions, accountable owners, and measurable evidence.

In Java serverless, testing cannot stop at checking whether a function still returns HTTP 200. You must verify the entire pipeline: triggers, runtime, access permissions, queues, databases, partner APIs, committed data, retries, idempotency, routing, and recoverability. A system is considered recovered only when business operations continue accurately and no data is lost or duplicated beyond policy.

## 1. What do chaos testing and failover drills solve?

Chaos testing focuses on how the system reacts when a component fails or degrades. Failover drills focus on the recovery process when workloads must shift to another environment or Region.

| Activity | Question to answer | Example |
|---|---|---|
| Fault injection | How does the system react when a dependency fails? | Database returns 503 or times out |
| Resilience test | Do retries, timeouts, and circuit breakers work properly? | Function stops retrying after max attempts |
| Chaos experiment | Does actual behavior match the hypothesis? | Delay 10% of invocations for 2 minutes |
| Failover drill | Can traffic shift to the standby region? | Shift API from Region A to Region B |
| Recovery test | After failover, are data and business logic intact? | Reconcile orders and replay messages |
| Failback drill | Can the system safely return to the primary region? | Sync data back and shift traffic home |

Chaos testing is not breaking production blindly without a plan. A responsible experiment explicitly defines which fault is injected, which components are targeted, how long it runs, which signals indicate unsafe behavior, and who holds stop authority.

Nor is a failover drill simply flipping DNS. Verify that the standby region holds the code, configuration, permissions, networking, quotas, data, queues, and dependencies needed to handle live traffic.

## 2. HA, resilience, and disaster recovery

These three concepts are related yet pursue distinct goals:

- **High Availability (HA):** Minimizes downtime through redundancy and automated handling of routine failures. Lambda is a managed service designed to run across multiple Availability Zones within a Region, yet dependencies called by the function can still introduce single points of failure.
- **Resilience:** Ability to keep delivering correct business behavior despite faults, performance degradation, or load shifts.
- **Disaster Recovery (DR):** Restoring workloads after severe incidents that take out the primary deployment location, such as a Region outage or data corruption.

A system with HA inside one Region does not necessarily have DR for a full Region outage. Conversely, having a data replica in another Region does not guarantee immediate readiness if functions, APIs, secrets, permissions, and routing have not been deployed.

In serverless, the cloud provider manages much of the infrastructure, yet application teams remain accountable for:

- How functions handle dependency failures.
- Retries, timeouts, duplicates, and idempotency.
- Business state and data integrity.
- Trigger, queue, and event source mapping configurations.
- Deploying matching versions in the standby Region.
- Traffic cutover and post-failover verification.
- Failback procedures and data reconciliation.

## 3. Defining RTO and RPO before testing

The two primary metrics for DR are:

**Recovery Time Objective (RTO)** is the maximum outage duration the business can tolerate. For example, if RTO is 30 minutes, the team must restore transaction processing within at most 30 minutes from incident declaration per agreed measurement rules.

**Recovery Point Objective (RPO)** is the maximum acceptable data loss, typically expressed as a time window of data. If RPO is 5 minutes, the recovered system must not lose more than 5 minutes of data already confirmed per business criteria.

Examples:

| Workload | Target RTO | Target RPO | Meaning |
|---|---:|---:|---|
| Catalog lookup API | 60 minutes | 15 minutes | Can tolerate slower recovery and losing a small window of recent changes |
| Order creation | 15 minutes | 1 minute | Needs rapid recovery and minimal transaction loss |
| Payment processing | 5 minutes | Near 0 per business commitment | Requires durable transaction state, idempotency, and reconciliation |
| Internal reporting | 4 hours | 1 hour | Can use a more economical backup/restore strategy |

These figures are examples illustrating how to set targets, not cloud service SLAs.

Measure RTO from organizational incident start until business operations are verified working again. Measure RPO by comparing confirmed transactions in the primary region against data present in the recovery region. Never measure only when the API starts returning 200; verify transactions can be read back, updated, and completed cleanly.

## 4. DR strategies by cost and recovery time

A multi-Region workload generally selects one of four models:

| Strategy | Standby environment | Relative recovery time | Cost and complexity |
|---|---|---|---|
| Backup and restore | Backups exist; environment built during incident | Longest | Lowest |
| Pilot light | Core infrastructure and critical data exist; scaled/completed on failover | Medium to long | Moderate |
| Warm standby | Pre-running scaled-down environment ready to absorb traffic after scaling | Shorter | Higher |
| Multi-site active/active | Multiple Regions serve live traffic concurrently | Potentially near-continuous if designed properly | Highest |

**Backup and restore:** Suits workloads with generous RTO/RPO. Back up data, code, configs, and IaC; during an incident, deploy the stack and restore data.

**Pilot light:** Keeps core foundations like data replicas or essential services running. On failover, deploy or scale remaining components.

**Warm standby:** Standby environment already runs and can handle partial load. On incident, scale up capacity and shift traffic.

**Multi-site active/active:** Multiple Regions process requests concurrently. Reduces dependency on environment spin-up, yet requires solving concurrent writes, write conflicts, routing, and consistency.

Faster strategies carry higher infrastructure and operational costs. Select based on RTO/RPO and business value—never pick active/active merely because it sounds safer.

## 5. Classifying serverless failure modes

Before designing experiments, list failure modes by layer:

| Layer | Failure mode | Symptoms |
|---|---|---|
| Trigger | API Gateway or event source fails to invoke function | 5xx requests, growing queue backlog |
| Runtime | JVM startup error, function timeout, or out of memory | Init errors, rising duration, failed invocations |
| Capacity | Concurrency quota or reserved concurrency hit | Throttles, retries, and backlogs |
| Network | DNS, NAT, route, or private endpoint failure | Connection timeouts, name resolution failures |
| Dependency | Database, cache, or partner API slow/down | Rising latency, 5xx, pool exhaustion |
| Identity | IAM role, token, or secret expired/misconfigured | `AccessDenied`, authentication failures |
| Messaging | Duplicates, poison messages, DLQ, or event ordering | Duplicate processing, backlogs, out-of-order state |
| Data | Replica lag, corrupted data, or consistency loss | Missing records, conflicts, stale reads |
| Region | API, function, or data service unavailable in primary Region | Unable to serve traffic in that Region |
| Release/config | Faulty new version or misconfiguration | Error spike post-deploy, disabled trigger |

Do not test every failure mode simultaneously. Pick one hypothesis, one primary fault, and an observable scope. When multiple faults overlap, teams struggle to isolate root causes.

## 6. Writing a hypothesis for every chaos experiment

A solid experiment starts with a testable hypothesis:

> When 10% of requests to the payment dependency receive HTTP 503 for 2 minutes, the Java function performs bounded retries, preserves the idempotency key, creates zero duplicate transactions, and keeps the business error rate below the agreed threshold.

A hypothesis must specify:

1. **Steady state:** Which metrics define normal system behavior?
2. **Fault:** Which fault will be injected?
3. **Target:** Which component or slice of invocations is impacted?
4. **Expected behavior:** How should the application react?
5. **Success criteria:** Which metrics prove the hypothesis holds?
6. **Stop conditions:** What forces the experiment to abort?
7. **Recovery:** How is the fault removed and normal operation restored?

Other examples:

- If a function receives database timeouts, the circuit breaker must prevent new requests from overloading the database.
- If a consumer processes the same event twice, only one business transaction commits.
- If the primary Region becomes unavailable, traffic shifts to the standby Region within RTO and data loss stays within RPO.
- If queue backlog grows, consumers recover and drain work without triggering duplicate side effects.

Avoid vague goals like "the app keeps working fine." Define concrete thresholds for latency, error rate, backlog, duplicate count, and business success rate.

## 7. Designing guardrails and limiting blast radius

Before injecting faults, bound the maximum blast radius. Standard guardrails include:

- Target only resources tagged explicitly for experiments.
- Start in dev or staging using synthetic data.
- Cap target resources by small counts or percentages.
- Bound fault duration.
- Attach CloudWatch alarms or equivalent monitors as automatic stop conditions.
- Assign an active operator with immediate manual abort authority.
- Keep recovery runbooks and dependency owners on standby.
- Avoid running concurrently with deployments, migrations, or major campaigns.
- Verify backups and recovery paths work beforehand.
- Capture baseline state for post-experiment comparison.

AWS Fault Injection Service (FIS) uses experiment templates defining actions, targets, stop conditions, and an experiment role. Stop conditions can reference CloudWatch alarms; when triggered, FIS halts the experiment. Each template requires an IAM role scoped to permitted actions. See [FIS experiment templates](https://docs.aws.amazon.com/fis/latest/userguide/experiment-templates.html) and [stop conditions](https://docs.aws.amazon.com/fis/latest/userguide/stop-conditions.html).

A core safety principle is bounding both **technical scope** and **business scope**. For instance, injecting faults only into a staging function still threatens production if that function shares a production database or queue. Inspect actual dependencies rather than trusting environment names.

## 8. Preparing steady-state metrics and stop conditions

Stop conditions must be defined before starting. Key metrics to consider:

| Metric | Potential stop signal |
|---|---|
| HTTP 5xx/error rate | Exceeds threshold across consecutive windows |
| p95/p99 latency | Breaches latency budget |
| Lambda Throttles | Climbs past permitted limit |
| Queue age | Oldest message exceeds SLA |
| DLQ message count | Unexpected poison messages outside test scope |
| Database connections | Pool or connection limit nears saturation |
| Replication lag | Exceeds RPO |
| Business success rate | Business completion drops below threshold |
| Duplicate transactions | Unblocked duplicate transactions appear |
| Customer impact | Errors affect real users beyond approved bounds |

Stop conditions are not just for protecting CPU or infrastructure. An experiment is still dangerous if technical metrics look green while duplicate orders are created, transactions are dropped, or payments record incorrect states.

Layer your protections: automated alarms, live observers, and a manual kill switch. In AWS FIS, safety levers stop running experiments and block new experiments in that Region. See [AWS FIS Safety Levers](https://docs.aws.amazon.com/fis/latest/userguide/safety-lever.html).

## 9. AWS FIS for Lambda: invocation fault injection

AWS FIS provides Lambda-specific actions to inject invocation faults. Current documentation lists:

- **aws:lambda:invocation-add-delay:** Injects latency before function code runs.
- **aws:lambda:invocation-error:** Marks invocations as failed; optionally runs function code before returning the error.
- **aws:lambda:invocation-http-integration-response:** Simulates an HTTP integration response.

These actions use the AWS FIS managed extension. To use them, attach the extension layer to your function, configure an S3 bucket for fault configuration exchange, and grant required IAM permissions. Each Region requires its own bucket for extension configs. The extension does not support Lambda response streaming; documentation warns it can suppress streaming configuration even when no fault is actively injected.

Consult [AWS FIS Lambda actions](https://docs.aws.amazon.com/fis/latest/userguide/use-lambda-actions.html) before configuring. Do not simply attach the extension and launch experiments: verify the layer version, S3 policies, environment variables, execution role, and experiment role.

The two required extension environment variables are:

~~~text
AWS_FIS_CONFIGURATION_LOCATION=arn:aws:s3:::fis-config-bucket/FisConfigs/
AWS_LAMBDA_EXEC_WRAPPER=/opt/aws-fis/bootstrap
~~~

The Lambda execution role needs read access to the configuration bucket/prefix; the experiment role needs write and delete permissions for fault configs plus permissions for FIS to inspect functions. Keep buckets and policies isolated per Region per AWS guidance. When the extension polls for configuration, default polling can create up to roughly 60 seconds of ramp-up; after the fault ends, ramp-down can take around 20 seconds. Factor these windows into experiment timing.

Notable operational details:

- Extension polling for fault configuration can create a ramp-up window before faults affect all invocations.
- With SnapStart, initial fault config pickup may be delayed because snapshots capture polling state.
- Very fast or infrequently invoked functions may require tailored poll behavior configuration.
- Fault injection can increase billed duration when delays are added.
- Test the extension in staging to confirm it does not alter normal behavior outside intended bounds.

## 10. Example Lambda experiment design

Suppose function **orders-api** calls **payment-service**. The goal is testing how the handler copes with transient errors.

| Attribute | Illustrative value |
|---|---|
| Hypothesis | Function retries up to 2 times with backoff without creating duplicate payments |
| Target | Specific ARN of the staging function |
| Fault | Invocation error or added delay |
| Percentage | 10% of invocations |
| Duration | 2 minutes |
| Success criteria | Zero duplicate payments; p99 and error rates within thresholds |
| Stop condition | Sharp drop in business success or abnormal DLQ spike |
| Recovery | Stop experiment, confirm extension clears faults, safely replay messages |

Before running, build a dashboard tracking invocation counts, errors, duration, retries, DLQs, payment transaction IDs, and idempotency keys. Use a sandbox payment provider or stub so real financial charges never occur.

Never start at 100% of invocations in production. Ramp percentages from small to larger only after prior runs prove steady state holds.

## 11. Testing slow or unavailable dependencies

Dependency failures are among the most common serverless incidents. Rapid function scale-out can hammer a degrading database or partner API.

Faults to test:

- HTTP 503 or 429 responses.
- Connect timeouts.
- Read timeouts.
- Elevated latency while still returning 200.
- DNS resolution failures.
- TLS handshake failures.
- Mid-stream connection resets.
- Database connection refusals or connection limit exhaustion.

Expected outcomes:

- Explicit connect and read timeouts are enforced.
- Retries apply only to transient errors on safe operations.
- Exponential backoff with jitter prevents retry storms.
- Circuit breakers halt repeated calls to failing dependencies.
- Bulkheads cap concurrency or connection pools.
- Callers receive actionable errors or contract-compliant degraded responses.
- Logs/traces carry correlation IDs linking requests to dependency faults.

Never retry infinitely. Once a dependency is overloaded, aggressive retries worsen load and prolong outages. Return transient errors, re-queue work, or serve stale cache data if business rules allow.

## 12. Testing retries, duplicates, and idempotency

Many serverless triggers provide at-least-once delivery or retry on function failure. Consequently, an event can reprocess after a timeout, missed acknowledgment, or transient fault.

Chaos experiments should proactively trigger:

- Delivering the exact same event twice.
- Function committing to the database then timing out before returning.
- Function successfully calling a partner API without receiving the response.
- Message redelivered after visibility timeout expiry.
- Two concurrent invocations processing the same business key.
- Older events arriving after newer events.

A safe handler requires a stable idempotency key, typically the event ID or business operation ID. Persist the key via atomic/conditional writes alongside outcome state. If the event is already completed, return the prior result or skip repeated side effects per contract.

Example logic:

~~~java
public Result handle(OrderEvent event) {
    String key = event.eventId();

    IdempotencyRecord existing = store.find(key);
    if (existing != null && existing.isCompleted()) {
        return existing.result();
    }

    // reserveIfAbsent must be an atomic operation in the persistent store.
    boolean reserved = store.reserveIfAbsent(key);
    if (!reserved) {
        return store.waitForOrReadResult(key);
    }

    try {
        Result result = orderService.process(event);
        store.markCompleted(key, result);
        return result;
    } catch (TransientDependencyException error) {
        store.markRetryableFailure(key, safeErrorCode(error));
        throw error;
    } catch (RuntimeException error) {
        store.markPermanentFailure(key, safeErrorCode(error));
        throw error;
    }
}
~~~

This is illustrative pseudocode; the repository must guarantee atomicity, handle leases/timeouts for in-progress records, and prevent a crashed invocation from locking a key forever. Never use a static `HashSet` or in-memory map as an idempotency store because execution environments recycle and run concurrently.

`TransientDependencyException` is an application exception representing retryable errors. Validation, authorization, or business rule failures must take the permanent failure branch; for queue triggers, route permanent errors to a DLQ/quarantine rather than retrying endlessly. Adapt pseudocode to your actual trigger semantics and transactional store.

## 13. Testing timeouts, concurrency, and backpressure

A function can run smoothly at low load yet fail when many invocations execute concurrently. Test:

- Stepping up concurrency gradually.
- Lowering reserved concurrency to simulate throttling limits.
- Building large queue backlogs.
- Slowing down the database to saturate connection pools.
- Sending request bursts to API Gateway.
- Returning 429/503 from dependencies at defined rates.
- Submitting messages that take longer than the visibility timeout.

Observe:

- `ConcurrentExecutions` and `Throttles`.
- Queue age, visible/in-flight messages, and DLQs.
- Database connection counts, CPU, lock waits, and query latency.
- Retry counts and average attempts per event.
- End-to-end p95/p99 latency.
- Business success and duplicate rates.

Apply backpressure by capping concurrency, batch sizes, or consumption rates. As queue backlog climbs, systems need mechanisms to throttle producers, cap consumer concurrency, or route failing messages to DLQs to shield dependencies.

Never raise concurrency unboundedly to clear a backlog. If downstream sustains only 100 concurrent requests, scaling functions to 1,000 will worsen the outage.

## 14. Testing network and DNS failures

Serverless functions commonly connect to private databases, caches, partner APIs, or cloud services over DNS and network paths. A DNS or routing glitch can time out functions even when runtimes are healthy.

Scenarios:

- Unresponsive DNS resolver.
- Hostname resolving to stale IP addresses.
- Private DNS zone detached from VPC/VNet.
- Failing NAT gateway or broken route.
- Security group/firewall blocking required ports.
- Expired TLS certificate or hostname mismatch.
- Connection pool holding sockets closed by the peer.

Test in isolated environments and inject faults only against test endpoints. Monitor DNS lookup latency, connect timeouts, TLS handshake failures, and reconnect counts.

In Java, never cache connections or IP addresses indefinitely. Enforce timeouts, bounded pool lifetimes, and limited retries. For SnapStart or snapshot-restored runtimes, re-verify socket and DNS caching behavior post-restore.

## 15. Testing IAM, token, and secret failures

A function may pass tests yet break when credentials expire or policies change.

Experiments to run in staging:

- Role missing permission to read objects or publish messages.
- Secret rotated while execution environments remain warm.
- Partner API token expired.
- KMS decrypt permission denied.
- Managed identity/service role unable to reach dependencies.
- TLS certificate or trust bundle updated.

Expected behavior:

- Functions return diagnosable errors without leaking secrets.
- Credentials refresh via SDK/provider mechanisms.
- Permission errors are not retried continuously like transient faults.
- Secret rotation does not require code redeployment if designed for safe refresh.
- Audit logs record the denied principal and action.

Never inject deny policies into shared production roles. Create dedicated roles, secrets, or resources for experiments to bound blast radius.

## 16. Testing poison messages and DLQs

A poison message consistently fails due to invalid data, incompatible schemas, or unrecoverable business errors. If retried indefinitely, it consumes capacity and inflates backlogs.

Chaos drills should inject messages with:

- Missing required fields.
- Unsupported schema versions.
- Oversized payloads.
- References to non-existent resources.
- Out-of-range business values.
- Payloads triggering parser exceptions.

Consumers must classify errors:

- Transient errors: retry per policy.
- Permanent errors: route to DLQ or quarantine.
- Unknown errors: cap retries, log context, and escalate for investigation.

After fixing the bug, replay messages from the DLQ in small batches with idempotency and watch outcomes. Never replay an entire DLQ straight to production without identifying the root cause and verifying side effects.

## 17. Testing single Availability Zone failures

A Region typically contains multiple Availability Zones. When workloads use managed multi-AZ services, the provider handles many infrastructure failures automatically. Still, applications may depend on single-AZ resources, subnets, NATs, database endpoints, or non-redundant service endpoints.

AZ tests should verify:

- Are function VPC subnets distributed across multiple AZs?
- Does the database have a replica/failover node in another AZ?
- Do network routes or NATs contain single points of failure?
- Does any private dependency exist in only one AZ?
- Do queues/event sources continue delivering messages when one AZ goes down?
- Does the application survive connection resets and reconnect cleanly?

Do not assume a Lambda function is pinned to a fixed AZ. Lambda manages execution environments; when VPC-attached, examine subnets, ENIs, and network dependencies. Fault injection should target controllable, measurable components rather than trying to break a physical AZ.

After testing, verify functions continue processing, database failover completes, connection pools recover, and no messages were lost or duplicated outside policy.

## 18. Multi-Region strategies for serverless

A multi-Region DR architecture typically includes:

~~~mermaid
flowchart TD
    U["Clients"] --> R["Global DNS / routing control"]
    R --> P["Primary Region"]
    R -. "Failover" .-> S["Recovery Region"]
    subgraph PR["Primary Region"]
      P --> PF["API Gateway"]
      PF --> PL["Java Lambda functions"]
      PL --> PD[("Primary data store")]
      PL --> PQ["Queue / event bus"]
    end
    subgraph DR["Recovery Region"]
      S --> SF["API Gateway"]
      SF --> SL["Java Lambda functions"]
      SL --> SD[("Replicated data store")]
      SL --> SQ["Recovery queue / event bus"]
    end
    PD -. "Replication / backup" .-> SD
~~~

Components required in the recovery Region:

- Identical Java function artifacts and versions.
- API Gateway, custom domain mappings, and authorizers.
- IAM roles, resource policies, and managed identities.
- Appropriate environment variables, secrets, and KMS keys.
- VPC, subnets, security groups, routes, and private DNS.
- Queues, event buses, DLQs, and event source mappings.
- Database replicas or restore mechanisms.
- Alarms, dashboards, log groups, and tracing.
- Service quotas, concurrency limits, and deployment pipelines.
- DNS/routing controls and regional cutover runbooks.

Never treat a recovery Region as merely a database replica host. If function code, secrets, KMS keys, queues, or IAM are missing, shifting traffic there still leaves the business down.

## 19. Verifying data replication and consistency

Replication usually introduces lag. With asynchronous replication, a transaction just committed in the primary Region may not yet appear in the standby Region.

During failover:

- Identify the timestamp of the latest replicated data.
- Reconcile transaction IDs or sequence numbers.
- Check for records committed but not yet replicated.
- Prevent both Regions from writing under active/passive architectures.
- Enforce fencing or ownership tokens to block split-brain.
- Handle late-arriving events and duplicates.
- Log transactions requiring reconciliation.

In active/active architectures, design conflict resolution explicitly. Partition write ownership by tenant or aggregate, use versions/sequences with conditional updates, or designate a single writer authority per business entity. Never let two Regions overwrite the same record via last-write-wins if the business cannot tolerate lost updates.

Replication does not replace backups. If data is deleted or encrypted maliciously in primary, replication copies that damage to standby. Maintain point-in-time backups and test restores periodically.

## 20. DNS failover routing

DNS failover directs clients to endpoints in the recovery Region using health checks or routing policies. In Route 53, failover records define primary and secondary targets; health checks guide Route 53 on which record to serve.

Points to remember:

- TTL controls how long resolvers cache older answers.
- Clients may hold existing connections open even after DNS updates.
- Health checks must reflect whether the app can serve real business traffic.
- A health endpoint returning 200 does not guarantee the database or queue is working.
- Never let health checks invoke operations with side effects.
- Test failover from multiple networks/resolvers if users are geographically distributed.

Route 53 includes a last-resort mode: when all records appear unhealthy, it may treat all records as healthy to avoid returning NXDOMAIN. Thus, never assume "all endpoints red" makes DNS stop returning records automatically. Review [Route 53 failover behavior](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-problems.html) and test your actual policy.

AWS recommends lower TTLs for records needing fast failover; 60 or 120 seconds are common examples, though resolver and connection caches can still stretch traffic migration times. See [Route 53 DNS best practices](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/best-practices-dns.html).

## 21. Using Application Recovery Controller routing controls

Amazon Application Recovery Controller (ARC) provides routing controls to shift traffic across application replicas. A routing control is an on/off switch tied to a Route 53 health check; it does not itself measure endpoint latency or health.

Simple workflow:

1. Create routing controls for primary and recovery replicas.
2. Link each control to its corresponding health check.
3. Attach health checks to DNS records routing to Regional endpoints.
4. During failover, operators or automation toggle control states.
5. DNS routing shifts traffic per the updated health checks.

ARC enforces safety rules to block traffic shifts that hurt availability, such as routing to an unready standby or turning off both replicas. Routing controls provide a reliable manual override when automated health checks miss business-level failures.

Traffic shifts are not necessarily instantaneous. Cached DNS records and open connections may keep sending requests to the old Region temporarily. See [ARC routing control](https://docs.aws.amazon.com/r53recovery/latest/dg/routing-control.about.html).

For DR, prefer recovery control paths prepared and tested prior to incidents. AWS recommends considering data-plane operations for failover because control planes typically have more centralized architectures. See [Route 53 data plane best practices](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/best-practices-dns.html).

## 22. Regional failover drill: end-to-end process

Run a failover drill in structured stages:

~~~mermaid
flowchart TD
    A["Select scenario and RTO/RPO targets"] --> B["Verify preconditions"]
    B --> C["Capture baseline and confirm data"]
    C --> D["Simulate primary Region outage"]
    D --> E["Detect and declare failover"]
    E --> F["Activate recovery Region"]
    F --> G["Switch routing"]
    G --> H["Smoke test and verify data"]
    H --> I{"Met RTO/RPO and business checks?"}
    I -->|"No"| J["Abort drill / restore safe state"]
    I -->|"Yes"| K["Hold traffic and monitor stability"]
    K --> L["Prepare failback"]
    L --> M["Sync data and return traffic"]
    M --> N["Reconcile and document lessons"]
~~~

### Phase 1: Preparation

- Select a primary Region and a recovery Region.
- Identify owners for APIs, functions, data, networking, and routing.
- Verify backups, replication, and IaC.
- Verify service quotas and concurrency limits in the recovery Region.
- Confirm experiment abort procedures.
- Notify participants and announce the drill window.
- Capture baselines for technical metrics and business data.

### Phase 2: Cutover

- Inject the simulated outage or mark primary unavailable per scenario.
- Confirm disaster declaration criteria are satisfied.
- Spin up or scale the recovery stack if using pilot light or warm standby.
- Verify functions, APIs, IAM, secrets, queues, and databases are ready.
- Shift traffic via routing controls or failover policies.
- Monitor new requests, in-flight requests, and queue backlogs.

### Phase 3: Verification

- Probe health endpoints and execute synthetic business transactions.
- Read back newly written data.
- Check for duplicates, missing events, and DLQ items.
- Measure actual RTO and RPO.
- Verify p95/p99 latency, error rates, and throughput.
- Inspect audit logs and traces.

### Phase 4: Conclusion

- Keep the recovery Region running long enough to confirm stability.
- Decide whether to fail back or continue running in recovery.
- Synchronize data back in the reverse direction.
- Shift traffic back incrementally.
- Reconcile data and drain any remaining backlogs.
- Publish a report covering timings, metrics, variances, and action items.

## 23. Failback: returning traffic to the primary Region

Failback is often harder than failover because the primary Region may hold stale data, drifted configs, or resources altered during recovery.

Before failback:

1. Confirm which Region currently holds write authority.
2. Prevent both Regions from accepting writes in active/passive architectures.
3. Replicate the latest data from the active Region back to primary.
4. Drain incomplete events and queued messages.
5. Verify schema, version, and configuration compatibility.
6. Run smoke tests in the primary Region.
7. Shift a small slice of traffic to observe if routing supports weighted splits.
8. Shift remaining traffic once criteria pass.
9. Keep a rollback path ready if primary throws errors.
10. Reconcile transactions after completion.

Never fail back automatically the moment primary health checks turn green. The Region may answer health probes while data remains unsynced, queues are unready, or dependencies remain degraded.

## 24. Chaos and DR scenarios to rehearse

| Scenario | How to simulate | What to verify |
|---|---|---|
| Lambda invocation errors | FIS `invocation-error` or test adapter | Retries, alarms, and DLQs work |
| Slow functions | FIS `invocation-add-delay` | Timeouts, caller deadlines, and concurrency |
| Partner API 503 | Fault-injecting stub/proxy | Backoff, circuit breakers, and idempotency |
| Database connection loss | Fault in test dependency/network | Reconnects, timeouts, fallbacks |
| Queue backlog | Cap consumer concurrency | Backpressure and recovery throughput |
| Poison message | Send malformed payload | DLQ routing and safe replay |
| IAM deny | Test role missing permissions | Error classification, auditing, no infinite retries |
| Broken DNS | Private DNS test zone or resolver fault | Timeouts, fallback endpoints |
| AZ dependency outage | Fault on test AZ endpoint/dependency | Multi-AZ behavior and reconnects |
| Primary Region unavailable | Routing and DR stack drill | RTO, RPO, data consistency |
| Data corruption | Inject bad records in test dataset | Backup restore and reconciliation |
| Secret rotation | Rotate secret while functions run | Credential refresh and zero downtime |

Select scenarios aligned with real architectural risks. There is no need to test faults for components your system does not use.

## 25. What must a Java function do during an incident?

A resilient Java function typically exhibits these traits:

- Stateless handlers that never rely on single-execution-environment memory.
- Timeouts shorter than caller deadlines, leaving reserve for cleanup.
- Bounded retries with exponential backoff and jitter.
- No retries on permanent failures like validation or authorization errors.
- Idempotency for mutations and external side effects.
- Circuit breakers or bulkheads guarding critical dependencies.
- Bounded, self-healing connection pools.
- Never storing sole business state in `/tmp` or static fields.
- Logs carrying correlation IDs, event IDs, and release versions.
- Graceful degradation when non-essential dependencies go down.

Never catch all exceptions and return HTTP 200. Doing so hides failures from callers, queue retries, and monitoring. Return statuses or outcomes per contract so callers can decide whether to retry, dead-letter, or raise errors.

For queue triggers, acknowledge messages only after business state is durably persisted. For HTTP, if the client times out after the transaction committed, idempotency keys let clients retry without triggering a second side effect.

## 26. Platform-specific chaos tooling

Principles of hypotheses, blast radius, stop conditions, and steady-state measurement apply across all clouds; supported tools and fault types differ:

| Platform | Tool/capability | Key considerations |
|---|---|---|
| AWS | AWS Fault Injection Service; Lambda actions via managed extension | Experiment templates, targets, IAM roles, stop conditions; Lambda extension requires an S3 config bucket and does not support response streaming |
| Azure | Azure Chaos Studio | Experiment resources, targets/capabilities, and managed identities; permissions to start experiments must be tightly restricted |
| Java application | Test doubles, fault proxies, or dependency stubs | Valuable for simulating application/dependency-layer faults that infrastructure tools cannot inject directly |

With Azure Chaos Studio, tightly governing who can start experiments is critical because that permission injects faults into targeted resources. See [Azure Chaos Studio security and permissions](https://learn.microsoft.com/en-us/azure/chaos-studio/chaos-studio-permissions-security). Regardless of tooling, test on isolated resources first and verify how to halt faults immediately.

## 27. Testing stateful workflows and sagas

A serverless workflow can span multiple functions and services: create order, reserve inventory, charge payment, send email. When one step fails, you cannot simply replay the entire workflow without knowing which prior steps already committed.

Chaos tests should inject faults at every step:

- Function A commits the order but times out before responding.
- Function B reserves inventory successfully, then the message duplicates.
- Function C completes payment, then the acknowledgment is lost.
- Function D fails sending email while the core transaction succeeded.

Maintain durable workflow state, event IDs, idempotency keys, and compensating actions. Sagas use compensating actions to undo or restore consistent business state—such as releasing inventory or refunding payments.

Never assume compensation restores the world to its exact initial state. A sent email cannot be "unsent"; a captured payment may require a separate refund transaction. Model explicit business states such as `PENDING`, `AUTHORIZED`, `CAPTURED`, `FAILED`, and `COMPENSATING` to distinguish outcomes.

## 28. Testing data backups and restores

A DR drill is incomplete if it only tests replication. Practice restoring from backups into an isolated environment:

1. Pick a recovery point matching target RPO.
2. Restore the database or object store.
3. Verify schemas and indexes.
4. Run integrity verification queries.
5. Reconcile record counts and aggregate business totals.
6. Run application smoke tests against restored data.
7. Verify permissions, KMS keys, and secrets.
8. Measure total restore completion time.
9. Document data lost relative to RPO.
10. Clean up the test environment per procedure.

Replication provides near-real-time copies yet faithfully replicates corrupted or deleted data. Point-in-time backups let you rewind before the error. Maintain both when workloads require protection against logical corruption or accidental deletion.

## 29. Testing event replay and backlog recovery

Following failover, queues or event streams may hold unprocessed messages. Some may be in-flight, some retrying, and some sitting in DLQs.

Recovery procedure:

- Identify which queue/stream is the authoritative source.
- Inspect offsets, checkpoints, or visibility timeouts.
- Identify messages already processed yet unacknowledged.
- Ensure consumers in the new Region point to the proper idempotency store.
- Replay in rate-limited batches.
- Monitor oldest message age and processing throughput.
- Halt replay if duplicates or business errors exceed thresholds.
- Reconcile event counts against transaction counts.

For partitioned streams, preserve per-partition/per-aggregate ordering where required by business logic. Never replay an entire stream without verifying checkpoints, as doing so can scramble ordering or repeat side effects.

## 30. Observing chaos experiments and failovers

Every experiment needs dedicated dashboards and logs. Track these metric groups:

**Application**
- Request success/error rates.
- p50, p95, p99 latency.
- Function Errors, Duration, Throttles, and `ConcurrentExecutions`.
- Init/restore durations and timeout counts.

**Messaging**
- Queue depth.
- Age of oldest message.
- Retry counts.
- DLQ depth.
- Duplicate event counts.
- Consumer throughput.

**Data**
- Database connections, latency, and failover events.
- Replication lag.
- Transaction counts and reconciliation mismatches.
- Backup/restore duration.

**Routing**
- Health check statuses.
- DNS answers across resolvers.
- Routing control states.
- Traffic split by Region.
- Open connections lingering on the old Region.

**Business**
- Order success rate.
- Payment success/failure/unknown state counts.
- Inventory mismatches.
- Transactions requiring manual reconciliation.
- Customer-visible errors.

Attach experiment ID, Region, fault type, and release version to logs and metric dimensions. Avoid putting raw customer data in metric labels or writing secrets to logs.

## 31. Regional incident runbook

A runbook must answer these questions without forcing on-call engineers to guess:

1. What conditions qualify as a Region outage?
2. Who holds authority to declare failover?
3. Which dashboards and health checks are the source of truth?
4. Is the standby Region verified ready?
5. Up to what timestamp has data replicated?
6. Must the primary Region be fenced before enabling writers in the new Region?
7. Which commands or controls shift routing?
8. How are APIs and business transactions verified?
9. How are queue backlogs, DLQs, and event replays handled?
10. When is failback permitted?
11. Who approves failback and who oversees reconciliation?
12. How is status communicated to stakeholders?

Store runbooks somewhere accessible when the primary system is down. If runbooks live solely on a wiki or storage inside the primary Region, teams lose access right when they need them most. Keep offline copies or independent replicas per organizational policy.

## 32. Game days and team roles

A game day is a structured exercise with a facilitator, operators, and observers. Roles can include:

| Role | Responsibility |
|---|---|
| Incident commander | Decides start, abort, and failover declaration |
| Experiment operator | Executes fault injection per template |
| Application owner | Monitors function and business behavior |
| Data owner | Verifies replication, backups, and consistency |
| Network/platform owner | Monitors DNS, routing, VPC, and quotas |
| Observer/scribe | Records timeline, metrics, decisions, and anomalies |
| Communications lead | Updates stakeholders on status |

For your first game day, pick a small scenario with clear scope and zero customer impact. Once the team masters the workflow, advance to staging failover drills or policy-approved partial production traffic tests.

Never turn a game day into a test of individuals. The goal is uncovering gaps in architecture, automation, runbooks, and permissions.

## 33. Exit criteria and post-drill reporting

An experiment is complete only when:

- Faults are removed or the experiment has stopped.
- The system returns to steady state.
- Queue backlogs are cleared or follow an active drain plan.
- Zero unintended business side effects remain.
- Data consistency has been verified.
- Region and routing states are confirmed.
- Alarms have returned to normal state.
- The facilitator confirms closure.

Post-drill reports should document:

- Hypothesis and objectives.
- Date/time, Regions, and resource scope.
- Injected faults and actual duration.
- Timeline of detection, decision, failover, recovery, and failback.
- Actual RTO/RPO versus targets.
- Before/during/after metrics.
- Lost, duplicated, or reconciliation-needed transactions.
- What worked well.
- What fell short.
- Action items, owners, and due dates.

Prioritize fixing bugs that risk data loss, split-brain, duplicate side effects, or RTO/RPO misses. After fixes ship, re-run the exact same experiment to verify.

## 34. Common mistakes in chaos testing and failover

| Mistake | Consequence | Fix |
|---|---|---|
| No clear hypothesis | Impossible to tell if the test passed | Define steady state and success criteria |
| No stop conditions | Fault exceeds blast radius | Alarms, safety levers, and live operators |
| Testing only functions, ignoring databases/queues | Misses dependency bottlenecks | Test the complete request path |
| Health checks only ping runtime | Traffic routes to a broken app | Health checks reflect dependencies and business readiness |
| Checking only DNS record updates | Clients keep hitting the old Region | Test resolver caches and connection reuse |
| Standby Region lacks quotas | Fails to scale during failover | Pre-flight quotas and concurrency |
| Ignoring replication lag | RPO breaches target | Monitor lag and transaction sequences |
| Both Regions writing simultaneously | Split-brain and conflicts | Fencing, writer ownership, and conflict policies |
| Non-idempotent DLQ replay | Duplicate side effects | Deduplication and batched replays |
| Never rehearsing failback | Primary cannot safely resume traffic | Dedicated runbook and rehearsal |
| Skipping business reconciliation | API looks green while data is wrong | Business reconciliation post-recovery |

## 35. Production checklist for chaos and DR

**Before the experiment**

1. Are hypothesis and steady-state metrics defined?
2. Are target, blast radius, and fault duration bounded?
3. Are automated stop conditions and a manual kill switch ready?
4. Are backups/restores or rollbacks verified?
5. Have shared dependencies with production been checked?
6. Are experiment roles and IAM permissions least-privilege?
7. Have owners and on-call staff been notified?
8. Does the window avoid risky deploys or migrations?

**During the experiment**

9. Are dashboards tracking application and business metrics?
10. Are correlation IDs and experiment IDs attached?
11. Does the fault match expected rate and duration?
12. Are retries, timeouts, circuit breakers, and DLQs working?
13. Are duplicate transactions absent?
14. Can faults be halted and removed immediately?

**Regional failover drill**

15. Are RTO/RPO defined and measurable?
16. Are code, configs, secrets, IAM, networking, and triggers ready in the standby Region?
17. Have data replication and backup restores been tested?
18. Are split-brain protections in place?
19. Have routing controls/DNS and health checks been tested?
20. Do queues, DLQs, checkpoints, and event replays have runbooks?
21. Do synthetic business transactions succeed post-failover?
22. Are failback and reconciliation plans ready?

**After the experiment**

23. Has the system returned to steady state?
24. Have metrics and data been reconciled?
25. Did actual RTO/RPO meet targets?
26. Do action items have owners and deadlines?
27. Is a re-test scheduled after fixes land?

## References

- [AWS Fault Injection Service: Experiment templates](https://docs.aws.amazon.com/fis/latest/userguide/experiment-templates.html)
- [AWS Fault Injection Service: Stop conditions](https://docs.aws.amazon.com/fis/latest/userguide/stop-conditions.html)
- [AWS Fault Injection Service: Safety levers](https://docs.aws.amazon.com/fis/latest/userguide/safety-lever.html)
- [AWS FIS: Lambda function actions](https://docs.aws.amazon.com/fis/latest/userguide/use-lambda-actions.html)
- [AWS Well-Architected: Disaster recovery options](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html)
- [Amazon Route 53: DNS failover best practices](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/best-practices-dns.html)
- [Amazon Route 53: Failover behavior and cascading failures](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover-problems.html)
- [Amazon Application Recovery Controller: Routing controls](https://docs.aws.amazon.com/r53recovery/latest/dg/routing-control.about.html)
- [Azure Chaos Studio: Security and permissions](https://learn.microsoft.com/en-us/azure/chaos-studio/chaos-studio-permissions-security)

## Conclusion

Chaos testing verifies the fault tolerance of functions and dependencies; failover drills verify the ability to recover entire workloads in a standby region. Both must rest on clear hypotheses, bounded scope, stop conditions, and business metrics.

For Java serverless, test timeouts, retries, idempotency, duplicate events, queue backlogs, dependency outages, and restored data integrity. For multi-Region DR, prepare code, configs, identities, networking, queues, data, quotas, and routing completely. Measure actual RTO/RPO, validate consistency, and rehearse failback separately. Only when business operations recover accurately and data reconciles cleanly is the drill truly successful.
