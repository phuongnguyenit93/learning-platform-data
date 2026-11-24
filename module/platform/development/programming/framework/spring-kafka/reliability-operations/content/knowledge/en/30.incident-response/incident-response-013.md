# Postmortem and Preventive Actions for Spring Kafka Systems

A postmortem is a document analyzing an incident after service has been restored. Its goal is to reconstruct what happened, identify why the system allowed the incident to occur or persist, assess impact, and turn lessons into action items with clear owners, deadlines, and verification criteria.

In a Spring Kafka system, an incident rarely resides in a single line of code. The processing flow can span producers, brokers, consumer groups, listener containers, databases, and downstream services. A good postmortem must trace these relationships using evidence rather than merely recording the final exception seen in logs.

## 1. When Should a Postmortem Be Written?

Hold a postmortem when an incident significantly impacts users or business operations, disrupts event flows, causes data loss or duplicate processing, creates prolonged backlog growth, affects multiple services, or forces operators into manual intervention.

Do not wait for a final root cause conclusion before starting the document. You can open it in "under investigation" status, record verified facts, and update as more evidence emerges. For minor incidents that recur frequently, aggregate occurrences to uncover shared patterns.

A postmortem is typically drafted after:

- The service has returned to an acceptable operating state.
- User and data impact have received an initial assessment.
- Relevant logs, metrics, traces, and deployment records remain retrievable.
- Responders involved in the incident can jointly reconcile the timeline.

Writing a postmortem does not replace status updates while an incident is active. During an incident, prioritize restoring service, limiting blast radius, and communicating with stakeholders. Deep root-cause analysis can continue afterward.

## 2. Blameless Postmortem Principles

A useful postmortem focuses on system conditions, engineering decisions, observability signals, and guardrails present at the time of the incident. Never blame an individual simply because they performed the last action before the system failed.

Example:

- Uninformative phrasing: "Engineer misconfigured the consumer."
- More useful phrasing: "The deployment configuration for the consumer group used a `max.poll.interval.ms` lower than peak-hour batch processing time. The system lacked alerts when processing duration approached the limit, and the rollout lacked representative load testing."

The second version describes verifiable conditions and opens multiple avenues for improvement: configuration checks, duration measurement, early alerting, and load testing.

Blameless does not mean unaccountable. Every post-incident action still needs a single accountable owner, a target completion date, and verification criteria. Accountability here means improving the system and delivering committed work.

Distinguish clearly between:

- **Verified facts:** supported by logs, metrics, traces, deployment history, or other evidence.
- **Hypotheses:** explanations under consideration without sufficient proof yet.
- **Conclusions:** explanations best supported by available evidence; explicitly note limitations where uncertainty remains.

Never rewrite the timeline to make past decisions look obvious in hindsight. Evaluate decisions based on what information on-call responders actually had at that moment.

## 3. Gathering Evidence During an Incident

Postmortems depend on evidence quality. With Spring Kafka, inspect both the broker side and the application side.

### 3.1. Evidence from the Spring Application

Collect logs from producers, listener containers, and downstream components covering before, during, and after the incident. Useful details typically include:

- Service name, application version, environment, and affected instances/pods.
- Relevant topic, partitions, consumer group, and client IDs.
- Start/end timestamps for each batch or message processed, if instrumented.
- Full exceptions, nested causes, retry counts, and dead-letter topic (DLT) routing status.
- Logs of partition assignments, revocations, lost partitions, and rebalances.
- Database or downstream HTTP call durations.
- History of deployments, configuration changes, restarts, scaling, and operational actions.

Logs should include a correlation ID or event ID to trace one event from producer through consumer to downstream services. Never place sensitive payloads, tokens, passwords, personally identifiable information, or confidential data into a postmortem. If payloads must be referenced, use controlled IDs or redacted excerpts.

### 3.2. Evidence from Kafka

Inspect topic, partition, consumer group, and broker states:

```bash
# View topic partitions, leader, replicas, and ISR
kafka-topics.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe \
  --topic orders

# View consumer group offsets, log-end offsets, and lag
kafka-consumer-groups.sh \
  --bootstrap-server kafka.example.internal:9092 \
  --describe \
  --group order-service
```

When reading consumer group output, keep in mind:

- `CURRENT-OFFSET` is the group's committed offset.
- `LOG-END-OFFSET` is the current end position reported by the tool for the partition.
- `LAG` is the tool-calculated delta between log end and committed offset.

Lag does not automatically equal the number of messages users are waiting on. Some messages may already be processed without committed offsets; conversely, consumers may commit before business work finishes if the application orders operations improperly. Therefore, cross-check lag against processing duration, business state, and commit semantics.

From broker monitoring, collect signals suited to your architecture: offline partitions, under-replicated partitions, ISR shrinks, request latency, request queues, network/thread utilization, disk usage, and controller status. Exact metric names vary across JMX exporters and monitoring platforms.

### 3.3. Evidence from Infrastructure and Dependencies

Check the same time window across:

- Kubernetes events, pod restarts, OOMKilled, CPU throttling, readiness/liveness transitions, and scaling history.
- DNS, networking, TLS/SASL, firewalls, and certificate changes.
- Database connection pools, lock waits, query latency, deadlocks, and connection limits.
- Downstream APIs: latency, timeouts, rate limits, and error rates.
- Changes to secrets, ACLs, quotas, broker configs, or topic configs.
- Deployment/configuration management systems and manual change logs.

Synchronize clocks across systems, prefer UTC in documents, and note timestamp sources. If one component's clock drifted, state the estimated skew rather than stitching events in an uncertain order.

## 4. Building a Verifiable Timeline

The timeline should record key events from before failures began until recovery was confirmed—not merely when an alert fired and when the incident closed.

| Time (UTC) | Event | Evidence | Significance |
|---|---|---|---|
| 09:00 | Started rolling out new consumer version | Deployment history | Change near incident start |
| 09:04 | Batch processing duration rose | Application metrics | Consumer processing slowed down |
| 09:07 | Group lag climbed continuously | Consumer group metrics | Processing rate fell below write rate |
| 09:10 | Backlog alert breached threshold | Alert history | System detected degradation |
| 09:14 | Halted rollout | Incident log | Limited change blast radius |
| 09:22 | Rollback completed | Deployment history | Restored prior version |
| 09:31 | Lag began draining | Consumer group metrics | Processing capacity restored |
| 09:45 | Business reconciliation finished | Reconciliation report | Confirmed data was processed |

Times in this table illustrate formatting only; actual postmortems must use verified timestamps.

Timelines should explicitly call out:

1. The first technical event that degraded the system.
2. When users or business flows began feeling impact.
3. When the system detected the issue and when on-call acknowledged the alert.
4. Containment decisions such as halting rollouts, shedding load, pausing consumers, or shifting traffic.
5. Recovery steps and when service returned to normal.
6. When data reconciliation completed and abnormal backlog cleared.

If impact start time cannot be determined, mark it "undetermined" and state the plausible range. Never fabricate an exact timestamp from incomplete data.

## 5. Quantifying Impact

The impact section must answer who was affected, which functionality degraded, for how long, and at what scale. Never write simply "Kafka was slow."

For event streams, measure where applicable:

- Messages published during the incident window.
- Messages delayed, retried, routed to DLT, or needing reprocessing.
- Peak consumer lag, duration lag exceeded threshold, and time needed to drain backlog.
- Number of affected partitions or consumer instances.
- Success, error, and duplicate rates.
- Count of business transactions delayed, failed, or needing manual reconciliation.
- Time from event creation to business completion (event-to-process latency).

Clearly distinguish terms:

- **Message delay:** messages processed later than SLA.
- **Message loss:** messages confirmed absent from the processing flow and unrecoverable via existing procedures.
- **Duplicate processing:** a message applied to business logic multiple times.
- **Data inconsistency:** mismatched state across systems even when messages remain intact.
- **Backlog:** work queued for processing; backlog does not equal data loss.

If message loss has not been proven, never write "data loss." Write instead: "no message loss detected; reconciling IDs across window X." Once reconciliation finishes, update the outcome and evidence source.

Record both external and internal impact. For example, if an API still returns HTTP 200 while order status events lag by 20 minutes, users still experience business impact.

## 6. Analyzing Root Causes and Contributing Factors

Do not stop at the final exception. Trace the chain of conditions that caused the error to happen, delayed detection, or hindered recovery.

Break analysis into four layers:

- **Trigger:** the immediate initiating event, e.g., a new release, slow downstream dependency, or loss of a broker.
- **Root cause:** the technical or design condition enabling the trigger to cause an incident, e.g., synchronous consumer processing exceeding poll limits with no isolation around slow dependencies.
- **Contributing factors:** conditions worsening severity or duration, e.g., unbounded retries, large batches, insufficient capacity, or alerts ignoring processing duration.
- **Detection and recovery gaps:** missing signals, unclear runbooks, difficult rollbacks, or absent post-recovery reconciliation.

Do not force every incident to have a single "root cause." In distributed systems, outcomes typically emerge from interacting conditions. Documenting a verifiable causal model is far more useful than an oversimplified one-line summary.

### 6.1. Using Controlled 5 Whys

Example question chain:

1. Why were orders updated late? The consumer group accumulated large lag.
2. Why could the consumer group not keep up with writes? Each batch took longer than normal to process.
3. Why did batches take longer? The listener called the database synchronously and several queries ran slowly.
4. Why did slow queries slow the entire consumer? The connection pool exhausted, retries held processing threads too long, and no proper timeout bounds existed.
5. Why was degradation not detected before broad impact? Dashboards monitored only brokers, without alerts on event processing latency and batch duration.

This chain is illustrative, not a template conclusion for every incident. Every answer requires evidence. If a step is unverified, mark it as a hypothesis and specify what data is needed to prove it.

5 Whys must never become an exercise in finding an individual to ask "why." Use it to uncover missing technical conditions, processes, and guardrails. Combine with timelines, causal diagrams, logs, and reproduction tests to validate hypotheses.

### 6.2. Common Root Cause Categories in Spring Kafka

| Category | Observable symptoms | Investigation direction |
|---|---|---|
| Slow consumer processing | Rising lag, rising message/batch duration | Database, downstream APIs, batch size, CPU, and blocking calls |
| Repeated rebalancing | Continuous revoke/assign logs, unstable consumers | Poll interval, heartbeats, session timeouts, GC pauses, and processing time |
| Poison message | Same record failing repeatedly, partition stalled | Deserialization, validation, retry policy, and DLT |
| Broker/partition degradation | Request latency, offline or under-replicated partitions | Broker health, disks, network, ISR, and leaders |
| Producer unable to publish | Send errors, timeouts, or rising retries | Broker availability, metadata, ACLs, quotas, and producer config |
| Out-of-order commits/processing | Duplicate or missing business effects after restart | Ack mode, offset commits, transactions, and idempotency |
| Environment config drift | One environment fails post-deploy while others work | Config drift, secrets, topic names, ACLs, and bootstrap servers |
| Downstream unavailable | Listeners wait long, connection pools exhaust | Timeouts, circuit breakers, bulkheads, and downstream capacity |

## 7. Example Postmortem: Consumer Lag Spike from Slow Database

This section illustrates connecting symptoms, evidence, causes, and actions. Numbers and timestamps are hypothetical examples showing formatting.

### Incident Summary

Consumer group `order-service` processed topic `orders` slowly during peak hours. Lag climbed continuously, delaying order status updates. Brokers remained healthy; producers continued publishing. Operations reduced query load, rolled back the change that raised processing duration, and monitored until the backlog drained.

### Impact

- A subset of orders had status updates delayed beyond the 5-minute SLA.
- Peak lag reached 120,000 records across affected partitions.
- No evidence of lost messages; order IDs within the incident window were reconciled after lag drained.
- The order-intake API remained available, though asynchronous status updates were delayed.

### Illustrative Timeline

| Time (UTC) | Event |
|---|---|
| 09:00 | Rolled out listener version with modified database query |
| 09:05 | P95 batch processing duration increased |
| 09:08 | Lag began rising across most partitions |
| 09:12 | Lag alert fired; on-call began investigating |
| 09:18 | Confirmed database connection pool near exhaustion |
| 09:23 | Halted rollout and executed rollback |
| 09:30 | Batch processing duration dropped |
| 09:42 | Lag drained steadily |
| 10:05 | Backlog returned within normal bounds |
| 10:20 | Business reconciliation completed |

### Analysis

**Trigger:** the new release increased query count and processing duration per batch.

**Root cause:** the listener executed synchronous database updates per record, and the new query lacked an appropriate index. Rising processing time dropped consumption rate below producer write rate.

**Contributing factors:**

- Alerts relied solely on absolute lag without pairing lag slope and event processing latency.
- Load tests did not reflect peak data distribution and database contention.
- Database retries prolonged batch hold times after the pool exhausted.
- Dashboards did not correlate Kafka lag with database pool saturation.

**Why recovery worked:** rollback removed the new query; afterward the database pool stabilized and consumers drained backlog faster than ingress rate.

### Post-Incident Actions

| Action | Type | Example owner | Completion criteria |
|---|---|---|---|
| Add index and verify execution plan for update query | Prevention | Database team | Query latency meets target at representative load |
| Add metrics for message and batch processing duration | Detection | Service team | Dashboard displays p50/p95/p99 |
| Alert when lag climbs alongside event processing latency | Detection | Platform team | Alert verified via load test simulation |
| Bound retry duration and handle downstream failures cleanly | Mitigation | Service team | Tested timeouts, retries, and recovery |
| Add load tests simulating database contention | Prevention | QA/Service team | Pipeline runs load check pre-release |
| Write runbook for backlog draining and event ID reconciliation | Recovery | On-call team | Successfully rehearsed in staging |

This example demonstrates that simply adding consumers may not fix an issue when the database is the bottleneck. Scaling consumers while downstream connections are exhausted can worsen pressure. Preventive actions must fix the bottleneck condition and surface early signals before impact spreads.

## 8. Turning Conclusions into Preventive Actions

A postmortem delivers operational value only when findings convert into concrete changes. Each action item should answer:

- What problem or risk is addressed?
- What is the specific change?
- Who is the primary accountable owner?
- When is it due?
- What evidence proves the action works?
- Which teams or systems does the action depend on?

Avoid vague items like "improve monitoring," "optimize Kafka," "increase stability," or "be more careful when deploying." Turn them into verifiable work, for example: "Create an alert when p95 event processing latency exceeds 30 seconds for 10 minutes and test the alert by injecting database latency in staging."

### 8.1. Categorizing Actions

| Action type | Purpose | Examples |
|---|---|---|
| Containment | Limit blast radius immediately during an incident | Halt rollouts, throttle producers, isolate failing partitions or dependencies |
| Prevention | Eliminate or reduce likelihood of the cause | Fix queries, validate configs, bound retries, load test |
| Detection | Detect earlier | Alerts on rapid lag growth, processing latency, rebalances, or DLT spikes |
| Recovery | Recover safely and repeatably | Runbooks for DLT replay, draining backlogs, data reconciliation |
| Resilience | Keep operating during dependency degradation | Timeouts, circuit breakers, bulkheads, idempotent handlers |
| Learning | Improve team knowledge and processes | Incident drills, runbook updates, engineering post-incident shares |

Not every incident needs actions in every category. Prioritize changes that directly address confirmed causes and proven detection/recovery gaps.

### 8.2. Writing Measurable Action Items

A good action item follows a clear structure:

```text
Action:
  Description of the concrete change

Reason:
  Postmortem finding this action addresses

Owner:
  One accountable person or role

Due date:
  Target completion date

Priority:
  P0 / P1 / P2 based on risk and impact

Verification:
  Test, metric, alert, or operational evidence confirming the result

Status:
  Open / In progress / Blocked / Done
```

Example:

```text
Action:
  Add an alert for the consumer group when p95 processing latency
  exceeds 30 seconds for 10 consecutive minutes.

Reason:
  The previous incident was detected late because dashboards showed only broker health.

Owner:
  Kafka Platform team

Due date:
  2026-12-05

Priority:
  P1

Verification:
  Simulate a slow listener in staging and confirm the alert
  fires within 10 minutes with topic and group in the payload.

Status:
  Open
```

Dates, thresholds, and owning teams in examples are illustrative. In real projects, choose thresholds based on SLAs, baselines, and operational capacity; never copy example numbers blindly.

Each action item needs one primary owner. Multiple teams may collaborate, yet an item should never list only a generic team name with no individual tracking it. If blocked, document the dependency and the decision required to unblock.

### 8.3. Prioritizing by Risk

A simple prioritization scheme:

- **P0:** risk of data loss, wrong business processing, or immediate recurrence; requires urgent containment or remediation.
- **P1:** gaps capable of causing severe incidents or excessively long detection/recovery times.
- **P2:** reliability, operations, and observability improvements that can be scheduled normally.

Never let priority labels replace risk judgment. A small task that prevents accidentally replaying production data can matter more than a large dashboard overhaul.

## 9. Common Preventive Actions Helpful for Spring Kafka

### 9.1. Managing Retries and Poison Messages

Unbounded retries can let one failing record stall a partition or overload downstream services with repeated requests. Explicitly define retryable exceptions, retry counts, backoff, timeouts, and the transition point to the DLT.

- Transient errors like network timeouts can be retried with bounded backoff.
- Invalid data or schema errors usually require separate handling, logging the cause, and routing to quarantine per policy.
- DLTs need alerts, owners, and handling/replay procedures.
- Replays must preserve idempotency to avoid duplicate business effects.
- Monitor DLT message age, new ingress volume, and unhandled backlog.

Never place every exception into infinite retries. One poison message can delay every subsequent message in the same partition.

### 9.2. Controlling Offsets and Idempotency

A consumer can process a message and crash before committing the offset. Upon restart, the message can be redelivered. This behavior must be accounted for in at-least-once designs.

- Design idempotent handlers using event IDs or suitable business keys.
- Define the order between database writes and offset commits.
- Avoid committing offsets before durable business work completes if doing so could lose required effects.
- Use transactions or outbox/inbox patterns when consistency is needed between database writes and event publishing; understand each mechanism's guarantee boundaries.
- Test restarts/crashes at different points in the processing flow.

Kafka idempotent producers and transactions provide guarantees within Kafka's scope, yet do not automatically make external side effects like database updates or HTTP calls exactly-once. Postmortems on duplicate or lost effects must explicitly note transaction boundaries.

### 9.3. Preventing Unnecessary Rebalances

Rebalances reduce throughput when consumers repeatedly lose and regain partitions. Check:

- Single poll processing duration vs. `max.poll.interval.ms`.
- Heartbeats, session timeouts, and GC pauses.
- Batch size and per-record processing duration.
- Consumer count vs. partition count.
- Shutdown and deployment behavior while containers are processing batches.
- Assignment/revocation logs to distinguish rebalances from deployments, timeouts, or member failures.

Never raise `max.poll.interval.ms` arbitrarily. Measure actual processing duration and consider capping batch size, offloading long work from the poll thread, or tuning concurrency to downstream capacity.

### 9.4. Protecting Downstream Dependencies

Consumers commonly call databases, REST APIs, or internal services. Slow dependencies drag down throughput and build backlogs.

- Set finite connect/read timeouts.
- Use bounded connection pools and monitor utilization.
- Consider circuit breakers or bulkheads to contain cascading failures.
- Retry with backoff, jitter, and caps; avoid concurrent retries across multiple layers.
- Verify database capacity before increasing concurrency.
- Define policies to pause, throttle, or buffer work when downstream is unavailable.

### 9.5. Controlling Producers and Schemas

Producers can also originate incidents:

- Track send errors, retries, request latency, and record queue time.
- Review timeouts, delivery timeouts, idempotence, and buffer limits.
- Manage schema evolution compatibly with running consumers.
- Test rollout order for compatibility: consumers should be able to read the new schema before producers emit new data, per system schema policy.
- Never log sensitive payloads while investigating serialization errors.

### 9.6. Protecting Brokers and Topics

Preventive actions at the Kafka layer include:

- Monitor offline partitions, under-replicated partitions, ISR shrinks, and broker disks.
- Set replication factor and `min.insync.replicas` per durability needs and broker count.
- Control partition counts to avoid unexpected growth in metadata and file handles.
- Monitor quotas, request latency, networking, and storage.
- Review broker upgrade plans, rolling restarts, and client compatibility.
- Govern ACLs, TLS/SASL, and tested certificate rotations.
- Provision topics in a controlled manner, version configurations, and verify topics reside on the right cluster.

### 9.7. Raising Deployment Quality

Every change touching producers, consumers, topics, or brokers should include a rollout and rollback plan.

- Put Kafka configuration under version control; check drift across environments.
- Validate schema and consumer config compatibility before release.
- Use canaries or phased rollouts when appropriate.
- Monitor lag, processing latency, error rates, and rebalances during rollouts.
- Define rollout abort conditions and rollback steps.
- Rehearse rollbacks to verify the process genuinely restores prior versions and configs.

## 10. Designing Monitoring to Catch Issues Before Users Feel Impact

Never monitor broker status alone. Brokers can be UP while consumers process too slowly, DLTs climb, or events fail to complete business flows.

A signal set should span multiple layers:

| Layer | Signals | Operational question |
|---|---|---|
| Producer | Send errors, retries, request latency | Can producers emit events? |
| Broker | Offline/under-replicated partitions, request latency, disk | Is the cluster healthy enough to serve? |
| Consumer | Lag, processing latency, poll interval, rebalances | Are consumers keeping up and stable? |
| Listener | Handler errors, retry counts, DLT rates | Are messages being processed accurately? |
| Dependency | DB/API latency, timeouts, pool saturation | Is the bottleneck outside Kafka? |
| Business | Event-to-process latency, count of stuck pending states | Are users receiving outcomes on time? |

Alerts should include actionable context: cluster, environment, topic, consumer group, partition if applicable, start time, and links to dashboards/runbooks.

Do not alert solely on a fixed lag threshold when throughput differs across topics. Combine:

- Absolute lag and lag growth rate.
- Age of the oldest unprocessed message.
- Event processing latency vs. SLA.
- Error/retry/DLT rates.
- Duration a consumer has made no offset progress.
- Health signals from downstream dependencies.

A good alert must have a clear response action. If no concrete action follows when an alert fires, revisit the threshold or demote it to a monitoring dashboard.

## 11. Verifying Post-Postmortem Actions

Close an action item only when there is evidence the change is deployed and verification criteria pass. A merged PR alone does not prove risk was reduced.

Example verification criteria:

- Alert: inject a controlled fault condition and confirm the alert reaches the right on-call responder with sufficient context.
- Retry: simulate timeouts, permanent errors, and recovery; confirm retry count, backoff, and DLT match design.
- Idempotency: replay the same event ID multiple times and confirm only one business effect occurs.
- Recovery: rehearse backlog draining or DLT replay and verify zero missed or double-processed records.
- Capacity: run representative load and verify processing latency, lag, and dependency pools stay within bounds.
- Runbook: an on-call engineer other than the author executes the document end-to-end without verbal guidance.

After completion, observe over a window matching the load cycle. If tested only in staging without production signal yet, note that limitation explicitly. For long-term items, break them into milestones to reduce risk and simplify tracking.

## 12. Postmortem Document Template

Use the template below for each incident. Mark non-applicable sections as "Not applicable" with a reason; mark unknown items as "Undetermined" along with a plan to verify.

```markdown
# Postmortem: [Incident Title]

## Metadata
- Incident ID:
- Service / environment:
- Topic / consumer group / cluster:
- Severity:
- Incident commander:
- Authors / reviewers:
- Date:
- Status: Draft / Review / Final

## Executive summary
Briefly describe what happened, the main impact, and current status.

## Customer and business impact
- Affected users/functionality:
- Start and end times:
- Affected transaction/message counts:
- Breached SLAs/SLOs:
- Data reconciliation results:

## Detection
- First alert or signal:
- Time to detect:
- Time to responder engagement:
- Unobserved duration before detection:

## Timeline (UTC)
| Time | Event | Evidence | Decision / impact |
|---|---|---|---|

## Technical details
- Producer:
- Broker / topic / partition:
- Consumer group / listener:
- Downstream dependencies:
- Deployment/configuration changes:
- Logs, metrics, traces, links:

## Root cause and contributing factors
- Trigger:
- Root cause:
- Contributing factors:
- Detection gaps:
- Recovery gaps:
- Confirmed facts:
- Open hypotheses:

## Resolution
- Containment:
- Recovery steps:
- Data reconciliation:
- Validation that service is healthy:

## What went well
-

## What made the incident harder
-

## Action items
| ID | Action | Type | Priority | Owner | Due date | Verification | Status |
|---|---|---|---|---|---|---|---|

## Follow-up
- Date to review outstanding actions:
- Evidence to collect:
- Runbook/dashboard/alert updates:
- Lessons to share:
```

This template can be adapted to your organization's incident process. Keep the summary concise while retaining enough evidence in technical sections so someone outside the incident can understand the decisions and conclusions.

## 13. Review Meeting Process

An effective review meeting includes a facilitator, someone who knows the application flow, someone versed in Kafka/infrastructure, and a business representative when customers were impacted.

Suggested agenda:

1. Align on incident scope and recovery outcome.
2. Walk through the timeline, confirming each event and evidence source.
3. Quantify impact and confirm data state.
4. Analyze triggers, root causes, and contributing factors.
5. Identify gaps in detection, containment, and recovery.
6. Propose action items, priorities, owners, due dates, and verification criteria.
7. Identify docs/runbooks/dashboards needing updates.
8. Confirm the follow-up tracker and review date for open actions.

If disagreement exists about root cause, document the hypotheses and missing evidence needed. Do not drag out a meeting to force a conclusion lacking data. Assign a dedicated investigation action with an owner and deadline instead.

## 14. Tracking Trends Across Multiple Postmortems

A single incident reveals a specific weakness; multiple postmortems can reveal systemic issues in design or operations.

Periodically aggregate:

- Incidents by service, topic, consumer group, and root-cause category.
- Incident recurrence frequency.
- Mean time to detect (MTTD) and mean time to recover (MTTR), using consistent definitions.
- Percentage of action items completed on time.
- Count of overdue or blocked actions.
- Percentage of incidents detected by monitoring before customer reports.
- Percentage of incidents requiring replay, reconciliation, or manual intervention.
- Trends in processing latency, lag, and DLT volume across critical flows.

Never use these metrics to rank individuals. Use them to identify which services need investment in observability, load testing, automated recovery, or architectural improvements.

Overdue action items should be reviewed by risk. If an action is no longer relevant, document why and what replaces it; never close items merely to inflate completion rates.

## 15. Criteria for Finalizing a Postmortem

A postmortem can move to final status when:

- Scope and impact are described with traceable data.
- The timeline cites evidence and separates facts from hypotheses.
- Causes and contributing factors explain the path from trigger to impact.
- Remaining uncertainties are explicitly noted.
- Action items have owners, priorities, due dates, and verification criteria.
- Necessary updates to runbooks, dashboards, alerts, or processes are captured as items.
- A follow-up schedule exists for open actions.

Not every action item must be finished before finalizing a postmortem. A dedicated tracking plan and reminder cadence ensure lessons do not end up forgotten in a document.

With Spring Kafka, a thorough postmortem connects the state of producers, brokers, partitions, consumer groups, listeners, and downstream systems to real business impact. When every conclusion is backed by evidence and every action has clear verification, incidents become concrete inputs for strengthening system reliability.
