# Postmortems and Post-Incident Reliability Improvements

When a service on Google Cloud suffers an incident, the operations team's top priority is protecting users and restoring service. Once the system stabilizes, the work is not over. The team needs to understand what happened, why safeguards failed to prevent the impact, which decisions helped restore the system, and what changes will reduce the likelihood of recurrence. A meeting that merely recounts an incident produces little value if its findings do not turn into owned, verifiable actions.

A postmortem is both a document and a post-incident learning process. A good postmortem describes impact, timeline, root cause and contributing factors, detection and response, what went well, what needs improvement, and follow-up actions. A blameless approach helps team members speak candidly about the system conditions, tools, processes, and decisions that led to the outcome. The goal is to improve systems and workflows to reduce future risk.

This lesson belongs to the **CLOUD_PROVIDERS_GCP** module. The module guides learners across Google Cloud from project organization, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Through deployment scenarios, learners select services, secure resources, automate releases, and track reliability alongside cost. Within this lesson, we use signals from Cloud Monitoring, Cloud Logging, Error Reporting, and Cloud Trace to analyze incidents, write postmortems, and translate lessons into reliability improvements.

## Objectives

After this lesson, you will be able to:

- Explain the purpose and principles of blameless postmortems.
- Distinguish between service recovery, root-cause analysis, and long-term improvement.
- Construct an incident timeline from metrics, logs, traces, and change history.
- Analyze direct causes and contributing factors without assigning personal blame.
- Write a postmortem with clear scope, impact, detection, response, lessons, and actions.
- Prioritize action items by risk reduction and implementation effort.
- Connect postmortem outcomes to SLIs, SLOs, error budgets, runbooks, and resilience testing practices.

## 1. What Is a Postmortem and Why Conduct One?

A postmortem is a structured record of a past incident and what the organization learned from it. It gives teams a shared, evidence-based understanding instead of relying on memory or oversimplified explanations. Postmortems also feed into reliability roadmaps, risk management, and cross-team knowledge sharing.

A useful postmortem answers:

- Which users and systems were affected?
- When did the incident start and end? How did impact evolve?
- What signals indicated abnormal system behavior? Who or what detected it first?
- What actions did the team take to mitigate impact and restore service?
- Which mechanisms worked properly? Which were missing, slow, or unclear?
- Which technical, architectural, operational, and organizational conditions combined to produce the incident?
- What changes can reduce the probability, detection time, or impact of similar incidents?

A postmortem is not a meeting to find someone to blame. A production system has many interdependent layers: source code, configuration, IAM permissions, networking, databases, pipelines, deployment tooling, alerts, and on-call procedures. Incidents usually emerge when multiple conditions converge. Focusing solely on an individual's final action misses the systemic conditions that enabled that action to cause broad impact.

### Which Incidents Warrant a Postmortem?

Organizations should define clear triggers. Scenarios that commonly merit a postmortem include:

- Service outage or significant degradation against SLOs.
- Many users or a key customer segment unable to complete business workflows.
- Prolonged, recurring incidents or incidents requiring multi-team coordination.
- Data loss, data corruption, security breaches, or compliance impact.
- A deployment, configuration change, or operational action causing significant production impact.
- A near miss that narrowly avoided major impact, even if no users were affected.

Not every minor bug needs a lengthy document. For small glitches, a brief note or learning summary in the ticket suffices. For severe incidents, run a full workflow with an accountable owner and track actions through completion.

## 2. Principles of Blameless Postmortems

A blameless postmortem focuses on the conditions and information participants had at the time they made decisions. When an action led to an incident, ask why that action seemed reasonable in context, what information tooling provided, what constraints existed, and what safeguards the system offered.

For example, saying "the engineer deployed a bad config" fails to explain why a bad config passed through the pipeline. A more useful analysis examines:

- Did the pipeline validate configuration schemas and values?
- Was there a staging environment sufficiently representative of production?
- Was there a canary or percentage-based rollout to cap impact?
- Could the deployer preview changes and recognize risk?
- Was rollback available, tested, and fast enough?
- Did alerts detect impact before users reported errors?

Blameless does not mean abandoning accountability. Teams still need action owners, operational standards, access controls, and risk-management decisions. The difference is that postmortems do not substitute personal blame for fixing systemic conditions.

### Language to Use

| Avoid Writing | Write Instead |
|---|---|
| Engineer X broke production | The new configuration was applied without a corresponding validation step |
| Operations ignored the alert | The alert used a threshold that did not reflect user impact and lacked a clear recipient |
| Developer forgot to test | The pipeline lacked test coverage for dependency timeout scenarios |
| On-call responded too slowly | The runbook omitted safe load-shedding steps; the team needed time to determine the right action |
| Must never make this mistake again | The design needs guardrails so a single error cannot cause widespread impact |

Describe actions, conditions, signals, and outcomes. Avoid speculating on participants' motives or competence.

## 3. Incident Lifecycle and Postmortem Timing

A postmortem begins once the situation is stable enough for the team to analyze. While an incident is active, the team focuses on detection, coordination, mitigation, and recovery. Timeline notes can be captured in parallel, but writing documentation must never slow down response activities.

~~~mermaid
flowchart TD
    A["Detect anomalous signals"]
    B["Declare incident and assess severity"]
    C["Coordinate, communicate, and assign roles"]
    D["Mitigate impact / restore service"]
    E["Confirm system stability"]
    F["Gather evidence and build timeline"]
    G["Analyze causes and contributing factors"]
    H["Write postmortem and agree on action items"]
    I["Track, verify, and share lessons"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
~~~

Some organizations assign an incident commander to coordinate, an operations lead to execute technical changes, and a communications lead to update stakeholders. In smaller teams, one person may hold multiple roles, provided it is clear who coordinates and who authorizes production changes.

### Distinguishing Three Phases

**Recovery:** reduce or stop impact and return the service to an acceptable state. Techniques include rollbacks, toggling feature flags, shifting traffic, adding capacity, or pausing a processing flow.

**Analysis:** reconstruct what happened from logs, metrics, traces, deployment events, and responder notes. Identify direct causes and contributing conditions.

**Improvement:** turn findings into verifiable changes—such as adding pre-deploy checks, improving alerts, limiting blast radius, or rehearsing rollbacks.

A workaround that restores service may be only a temporary fix. The postmortem must document any remaining risks or limits of that workaround alongside follow-up actions to address the underlying cause.

## 4. Gathering Evidence and Constructing a Timeline

Participants' memories can diverge, especially during long or multi-team incidents. Build the timeline from timestamped data sources and clearly separate verified facts from hypotheses.

### Data Sources on Google Cloud

| Source | Evidence Provided | Supporting Questions |
|---|---|---|
| Cloud Monitoring | Request counts, latency, error rates, CPU, memory, instance counts, alert incidents | When did impact begin and how did it grow? |
| Cloud Logging | Application logs, platform logs, structured events | Which component logged errors? Are there common error patterns? |
| Error Reporting | Grouped exceptions and error trends | Which application exceptions spiked abnormally? |
| Cloud Trace | Request traces and spans | Which service or dependency consumed the time? |
| Cloud Audit Logs | IAM changes, config changes, or admin operations | Which resource was modified, by which principal, and via which method? |
| CI/CD and Artifact Registry | Build history, deploy history, image digests, rollouts | Which release appeared right before the incident? |
| Business systems | Failed orders, transactions, messages, or jobs | At what scale were users and data affected? |
| Incident notes | Decisions, actions, owners, and timestamps | What did the team try and what happened? |

Cloud Audit Logs are valuable when identifying changes to Google Cloud resources. However, not all log types are enabled by default or share identical retention windows. Verify available log scope, access permissions, and time ranges before concluding no changes occurred.

### Steps to Build a Timeline

1. Define the incident window, including the earliest anomaly and when impact ended.
2. Pick one standard time zone—typically UTC in incident docs; note clearly if any source uses another time zone.
3. Collect alerts, metrics, logs, traces, audit logs, deploy events, and response notes.
4. Record key events: changes, alerts, user reports, mitigation decisions, rollbacks, and recovery confirmations.
5. Cross-check timestamps across sources. Distinguish when an event occurred, when logs were ingested, and when responders saw notifications.
6. Mark which entries are verified events versus estimates or hypotheses.

Example timeline:

| Time (UTC) | Event | Source | Confidence |
|---|---|---|---|
| 09:02 | New revision began receiving traffic | Cloud Run / deploy history | Verified |
| 09:05 | P95 latency rose above alert threshold | Cloud Monitoring | Verified |
| 09:07 | API error rate increased | Cloud Monitoring | Verified |
| 09:10 | On-call team confirmed incident | Incident notes | Verified |
| 09:16 | Traffic shifted back to previous revision | Deploy history | Verified |
| 09:21 | Error rate returned to baseline | Cloud Monitoring | Verified |
| 09:28 | Order-creation flow verified healthy | Business verification | Verified |

Never treat an illustrative timeline as data from a real incident. In a real postmortem, every milestone requires a source and corresponding confidence level.

### Preserving Verifiable Evidence

Save Logs Explorer queries, Monitoring charts, trace IDs, relevant revision names or image digests, and links to the incident ticket. Never paste payloads containing tokens, personal data, or customer data into the postmortem. When sensitive evidence must be preserved, link to an access-controlled repository following your organization's security process.

## 5. Assessing Impact and Incident Scope

Severity is not determined solely by complete downtime. An incident might subject a subset of users to high latency, process duplicate transactions, or leave data inconsistent even while the API keeps returning HTTP 200.

Describe impact across relevant dimensions:

- **Users:** affected customer segments, regions, tenants, or business flows.
- **Functionality:** which features failed, degraded, or became unusable.
- **Duration:** start time, end time, full disruption duration, and partial recovery duration.
- **Scale:** number of affected requests, transactions, accounts, or jobs, citing sourced metrics.
- **Data:** data loss, duplication, corruption, or delayed updates, if any.
- **Service commitments:** which SLIs/SLOs were breached and how much error budget was consumed.
- **Secondary impact:** backlogs, increased costs, customer support load, or manual cleanup work.

Distinguish between **incident onset time**, **user impact time**, and **operations awareness time**. These three intervals do not always coincide. For example, a dependency might degrade at 09:00, alerts fire at 09:05, and the team notices at 09:08. Distinguishing them highlights opportunities to improve detection and response.

If exact numbers are unavailable, state estimates, calculation methods, and limitations explicitly. Never invent numbers just to make a report look complete.

## 6. Analyzing Causes and Contributing Factors

Cause analysis must explain the chain of conditions leading to impact. "A bad deploy caused the outage" is usually just a starting point. Investigate how that change interacted with dependencies, configurations, traffic, data, and safeguards.

### Direct Causes and Contributing Factors

- **Direct cause:** the immediate event or technical state right before failures surfaced—for instance, connection pool exhaustion preventing requests from reaching the database.
- **Contributing factors:** conditions that increased likelihood or severity—for example, overly long timeouts, missing concurrency limits, CPU-only alerts, or unautomated rollbacks.
- **Underlying conditions:** long-standing architectural or process traits—such as services sharing one database, non-representative staging tests, or unreviewed config changes.
- **Detection gaps:** signals that existed yet were too insensitive, unalerted, unowned, or lacked runbook instructions.

Do not force every incident into a single "root cause." Many incidents result from a convergence of independent conditions. State confidence levels and any remaining open questions clearly.

### Five Whys Analysis

Five Whys is a technique of asking "why" repeatedly to move from symptoms to deeper systemic conditions. It is an exploratory aid, not a rigid rule requiring exactly five questions.

Example:

1. Why did order-creation requests time out? Because the service could not acquire connections from the pool.
2. Why did the pool run out of connections? Because many requests held connections longer than usual.
3. Why did connection hold time increase? Because a database query slowed down after a schema change.
4. Why did the schema change create a slow query? Because the production query plan was not checked against representative data volumes.
5. Why did testing miss it? Because the pipeline ran only functional tests on a small dataset and lacked performance checks for critical queries.

The output suggests multiple actions: inspect query plans, add performance tests with representative data, enforce query timeouts and connection limits, and alert on pool saturation. Writing only "be more careful during deploys" fails to address any of the conditions that caused the incident.

### Causal Trees and Evidence

You can use a causal diagram to depict multiple contributing factors:

~~~mermaid
flowchart TD
    A["Order-creation requests time out"]
    B["Connection pool exhausted"]
    C["Slow database query"]
    D["Small staging dataset"]
    E["Missing performance check"]
    F["Unsuitable timeouts and pool limits"]
    G["Alerts did not track pool wait time"]
    A --> B
    B --> C
    C --> D
    D --> E
    B --> F
    A --> G
~~~

This diagram is valuable only when every link is backed by evidence. Unconfirmed links must be marked as hypotheses with clear verification steps.

### Avoid Conclusions Beyond the Evidence

Do not conclude a change caused an incident merely because it occurred near the incident start time. Compare before-and-after metrics, revisions or image digests, configurations, logs, traces, and external factors. If the cause remains undetermined, a postmortem can still be completed with an "undetermined" conclusion paired with action items to add telemetry or test hypotheses.

## 7. Writing a Structured Postmortem

A consistent template helps readers quickly grasp the incident and locate actions. Length depends on complexity; prioritize useful details and verifiable evidence.

### Recommended Sections

| Section | Content |
|---|---|
| Title and metadata | Incident name, date, service, owner, severity |
| Summary | One paragraph describing what happened and main impact |
| Impact | Affected users, functions, data, duration, and SLOs |
| Detection | First signal, detection time, and detection delay |
| Timeline | Events, decisions, actions, and evidence sources |
| Root cause / contributing factors | Direct causes, contributing conditions, and confidence level |
| Response | Mitigation measures, recovery, and outcomes |
| What went well | Mechanisms or actions that helped contain impact |
| What could be improved | Gaps in design, tooling, or processes |
| Action items | Concrete actions, owner, priority, due date, and verification method |
| Follow-up | Ticket links, status, reviewers, and scheduled review date |

### Postmortem Template

~~~markdown
# Postmortem: [Incident Title]

## General Information
- Incident ID:
- Service / project:
- Date:
- Severity:
- Incident commander:
- Postmortem owner:
- Document status:

## Summary
[What happened, primary impact, and how service was restored.]

## Impact
- Affected users / features:
- Start and end times:
- Figures and sources:
- SLI / SLO / error budget:
- Data or business impact:

## Detection
- First signal:
- Time of detection:
- Detection delay:
- Alerts or user reports:

## Timeline (UTC)
| Time | Event | Evidence |
|---|---|---|
| | | |

## Causes and Contributing Factors
- Direct cause:
- Technical factors:
- Process / organizational factors:
- Detection or recovery gaps:
- Open hypotheses:

## Response and Recovery
- Mitigation measures:
- Recovery time:
- Verification checks:

## What Went Well
- 

## What Could Be Improved
- 

## Action Items
| Action | Risk reduced | Priority | Owner | Due date | Verification |
|---|---|---|---|---|---|
| | | | | | |

## Related Documents
- Dashboard:
- Logs Explorer query:
- Trace:
- Change / deployment:
- Incident record:
~~~

Never put credentials, sensitive payloads, or personal data in the template. Link to sources with appropriate access controls.

## 8. Example: Latency Spike After a Cloud Run Deployment

Hypothetical scenario: an `orders-api` service running on Cloud Run begins experiencing high latency and partial request failures after releasing a new revision. Users cannot complete some order-creation operations.

### Summary

The new revision changed how orders were queried and increased how long connections to Cloud SQL were held. As traffic grew, the connection pool hit its limit. Requests began queuing for connections, causing high latency and timeouts. The on-call team shifted traffic back to the prior revision; after rollback, error rates dropped and the service recovered.

### Data to Verify

- Cloud Monitoring: request counts, request latency, error counts, instance counts, and database connection metrics if available.
- Cloud Logging: connection acquisition exceptions, timeouts, and structured logs by request ID.
- Cloud Trace: duration of database call spans relative to other spans.
- Cloud Run: revisions, traffic shift timestamps, and concurrency settings.
- Cloud SQL: connection counts, query latency, and database resource usage.
- CI/CD: commit, build, image digest, test results, and change approver.

### Illustrative Timeline

| Time (UTC) | Event |
|---|---|
| 09:02 | New revision received traffic |
| 09:05 | P95 latency exceeded threshold |
| 09:07 | Error rate spiked; on-call received alert |
| 09:10 | Incident declared; team confirmed impact on order-creation flow |
| 09:16 | Traffic shifted back to prior revision |
| 09:21 | Error rate returned to baseline |
| 09:28 | Order creation verified healthy; incident moved to monitoring |

### Causes and Contributing Factors

- The new query lengthened connection hold times against production data.
- Pre-release tests lacked a representative dataset and query load testing.
- Alerts tracked error rates and latency but lacked early signals on connection pool saturation.
- Rollback was feasible, yet the runbook did not specify exact criteria and decision authority for shifting traffic.

### Potential Action Items

| Action | Improvement Type | Verification |
|---|---|---|
| Add performance tests for critical queries using representative data | Preventive | Pipeline runs tests and blocks release when thresholds fail |
| Configure query timeouts and appropriate connection pool limits | Preventive / containment | Load test confirms pools are never held indefinitely |
| Add dashboards for connection count, pool wait time, and query latency | Detective | Dashboard surfaces signals before error rate rises |
| Write and rehearse a Cloud Run revision rollback runbook | Recovery | Drill measures actual recovery duration |
| Roll out by percentage and check SLIs before raising traffic | Blast radius reduction | Canary run halts automatically on failing conditions |

This is an illustrative example, not telemetry from a live system. In real incidents, document only conclusions verified against actual data sources.

## 9. Turning Lessons into Completable Action Items

Action items determine whether a postmortem produces real improvement. A strong action item states the concrete change, rationale, owner, and evidence required to confirm completion.

Each action item should include:

- **Action:** clear verb and expected outcome.
- **Risk reduced:** lower probability, smaller blast radius, earlier detection, or faster recovery.
- **Priority:** urgency grounded in risk level and impact.
- **Owner:** one person or role accountable for seeing it to completion.
- **Due date:** target completion or review date.
- **Verification:** test, metric, dashboard, drill, or proof confirming completion.
- **Tracking link:** ticket or work item to track progress.

### Categorizing Actions

| Category | Goal | Example |
|---|---|---|
| Preventive | Reduce likelihood of occurrence | Add schema checks or performance tests |
| Detective | Detect faster | SLI alerts and dependency dashboards |
| Containment | Limit blast radius | Rate limits, bulkheads, quotas, or canaries |
| Recovery | Recover faster | Automated rollbacks, rehearsed backup restores |
| Learning | Improve system understanding | Runbooks, dependency docs, and on-call training |

Not every action requires code changes. A clear runbook, pre-staged emergency access, or recovery drill can significantly shrink MTTR.

### Writing Concrete Action Items

| Vague | Concrete and Verifiable |
|---|---|
| Improve monitoring | Create an alert when `orders-api` P95 latency breaches SLO for 10 minutes and test notification in a drill |
| Add more tests | Add a load test for order queries against a representative dataset in the pre-release pipeline |
| Optimize database | Inspect query plan, add verified index, and compare before/after P95 query latency |
| Improve rollback | Document revision rollback runbook, designate approvers, and rehearse quarterly in staging |
| Be more careful deploying | Enable a 5% traffic canary and check error ratio and latency before increasing traffic |

Avoid filing dozens of tiny action items just to show activity. Select a realistic number of completable items prioritizing the highest risk reduction. Actions that cannot start immediately still need an owner and a scheduled review date so they do not vanish after the meeting ends.

## 10. Prioritizing with SLOs and Error Budgets

SLOs define the reliability level a team must deliver. SLIs measure user experience or outcomes, such as successful request ratio or latency of eligible requests. The error budget is the failure allowance under the SLO target over a period.

After an incident, review:

- Which SLIs were affected and how severely they were breached.
- Error budget consumed during the incident and overall period trend.
- Whether the incident accelerated error budget burn rate.
- Whether risky feature releases should pause to focus on reliability improvements.
- Which action items reduce the likelihood of the next SLO breach.

For example, if an SLO requires 99.9% of eligible requests to succeed over a month, the error budget equals 0.1% of requests in that period. An incident causing many request failures can burn most of that budget quickly. Calculate consumption from actual figures; never treat downtime duration as a proxy for every SLI when the SLO is request-based.

An error budget is not a metric for punishing developers. It is a tool for balancing change velocity against reliability. When budget burns rapidly, teams have objective grounds to prioritize bug fixes, curb release risk, and invest in resilience.

## 11. Improving Systems After an Incident

Durable improvements usually span multiple layers rather than merely patching the offending line of code.

### Designing to Limit Blast Radius

- Use canaries or progressive delivery so a new change initially touches only part of traffic.
- Use feature flags to quickly turn off faulty features without redeploying the entire service.
- Isolate critical dependencies with appropriate timeouts, bounded retries, circuit breakers, and bulkheads.
- Enforce quotas, rate limits, and concurrency limits so traffic spikes do not bring down the entire system.
- Implement retries with exponential backoff and jitter; avoid synchronized retry storms that hammer struggling dependencies.
- Use queues and dead-letter handling for asynchronous work where business logic permits.

### Improving Detection

- Measure SLIs close to user experience rather than monitoring only CPU or memory.
- Configure alerts with clear recipients, thresholds, and action guidance.
- Propagate correlation IDs and trace context in logs to speed up investigations.
- Monitor dependencies, queue age, connection pools, saturation, and per-service errors.
- Test alerts through drills or fault simulation rather than merely verifying rule creation.

### Improving Recovery

- Prepare rollbacks and define trigger criteria.
- Test backup restores, failover, and disaster recovery on a schedule.
- Set appropriate timeouts and health checks.
- Verify applications restart cleanly, handle duplicate messages, and recover from dependency blips.
- Maintain runbooks for emergency operations alongside pre-staged access permissions.

### Improving Change Processes

- Validate configurations and policies before applying them.
- Require reviews proportional to change risk.
- Use immutable artifacts and record image digests or revisions.
- Run automated post-deploy verification with synthetic checks or smoke tests.
- Halt rollouts when SLIs degrade or critical alerts fire.

No single mechanism eliminates every incident. The goal is to make failures easy to detect, contain their impact, and recover service within acceptable bounds.

## 12. Tracking Postmortem Effectiveness

Never measure postmortem quality by page count or action-item count. Evaluate whether the organization is actually reducing risk and improving response capability.

Metrics worth tracking:

| Metric | Meaning | Interpretation |
|---|---|---|
| Time to detect (TTD) | Time from impact onset to detection | Falling TTD can indicate better monitoring |
| Time to acknowledge | Time from alert firing to human acknowledgment | Evaluates alert routing and on-call processes |
| Time to mitigate | Time until impact is substantially reduced | Evaluates containment capability |
| Time to restore | Time until service is restored | Evaluates rollback and recovery |
| SLO attainment | Degree of SLO achievement in the period | Evaluates user experience |
| Repeat incident rate | Rate of incidents recurring from the same cause class | Evaluates improvement effectiveness |
| Action completion rate | Share of action items completed on time | Evaluates post-postmortem follow-through |
| Action effectiveness | Whether actions actually reduced risk signals | Verified via tests, metrics, or drills |

Time metrics need consistent definitions. For instance, time to mitigate might end when error rates drop, whereas time to restore ends when all business flows are verified operational. Document start and end boundaries so cross-incident comparisons remain meaningful.

Categorize repeat incident rates by service, failure mode, or contributing factor. Two incidents in the same service with different causes are not necessarily repeats of the same underlying issue.

## 13. Running Review Meetings and Sharing Lessons

Review meetings should have a facilitator who keeps discussion evidence-based and prevents personal arguments. Attendees may include responders, service owners, SRE representatives, database or network teams, and business stakeholders when customer impact warrants it.

Suggested agenda:

1. Reiterate review goals and blameless principles.
2. Confirm incident scope and impact.
3. Walk through the evidence-based timeline.
4. Analyze direct causes and contributing factors.
5. Identify what went well and what needs improvement.
6. Prioritize action items, assign owners, and define verification methods.
7. Designate who updates the document and when to re-review.

If disagreements arise about root causes, record competing hypotheses along with missing evidence. Do not force consensus around one narrative without enough data. File an action item to add telemetry or run a reproduction test.

Share postmortems with teams that can learn from the incident. For security or sensitive-data incidents, follow restricted access scopes and dedicated handling workflows; a sanitized version shared broadly can strip sensitive details while preserving key engineering lessons.

## 14. Hands-On Exercise: Writing a Postmortem for a Cloud Run Incident

Suppose `orders-api` deployed a new revision. Minutes later, P95 latency rose, error rate spiked, and some order-creation requests failed. The on-call team rolled back the revision and the service returned to normal. Initial facts:

- Cloud Monitoring shows latency began rising right after the new revision started receiving traffic.
- Cloud Logging recorded database connection wait errors.
- Cloud Trace shows database query spans taking longer than baseline.
- Deploy history confirms a new image digest was released.
- The team has not yet confirmed whether the new query, pool configuration, or increased traffic was the primary factor.

Complete these tasks:

1. Write a 3–5 sentence incident summary distinguishing verified facts from remaining hypotheses.
2. Build a timeline including deploy time, metric signal, first log error, incident declaration, rollback, and recovery confirmation.
3. List user impact and potentially affected SLIs. Where figures are missing, specify which data must be collected.
4. Use Five Whys to develop at least two hypothesis branches around query latency and the connection pool.
5. Identify one direct cause and at least three contributing factors, stating conclusions only where supported by evidence.
6. Draft action items across preventive, detective, containment, and recovery categories.
7. For each action item, assign an owner, priority, due date, and verification method.
8. Choose one metric or SLI to evaluate whether the actions reduced risk.
9. Run a brief review using the agenda above and document any open questions.

### Evaluation Criteria

- Timeline includes timestamps, evidence sources, and separates facts from hypotheses.
- Impact is framed from the user perspective with explicit numbers or documented bounds.
- Analysis explains systemic conditions without blaming individuals.
- Action items are concrete, owned, and verifiable.
- Findings link back to SLOs, alerts, runbooks, or architectural improvements.

## 15. Postmortem Checklist

- [ ] Incident scope and owner are clearly defined.
- [ ] Summary describes the event, impact, and recovery state.
- [ ] Impact is quantified or missing data gaps are explicitly noted.
- [ ] Timeline uses a consistent time zone and cites evidence sources.
- [ ] Metrics, logs, traces, audit logs, and change history were reviewed where relevant.
- [ ] Direct causes and contributing factors are distinguished.
- [ ] Unverified hypotheses are clearly labeled.
- [ ] Language is blameless and focused on systemic conditions.
- [ ] Both what went well and what could be improved are documented.
- [ ] Action items specify owners, priorities, due dates, and verification methods.
- [ ] Actions tie back to SLIs, SLOs, or risk-reduction goals.
- [ ] Documents and evidence contain no secrets or sensitive data.
- [ ] Postmortem was shared with appropriate teams and has a follow-up schedule.
- [ ] Completed action items are reviewed to confirm effectiveness.

## Self-Check Questions

**1. What is the primary goal of a blameless postmortem?**

To understand the technical and organizational conditions that led to an incident, then improve the system to reduce likelihood, impact severity, or recovery time.

**2. Why should you avoid writing simply "deployment error"?**

Because a deployment is usually just one event in a causal chain. You need to analyze how the change interacted with traffic, dependencies, testing, rollouts, alerts, and rollbacks.

**3. How do Cloud Monitoring and Cloud Logging support postmortems?**

Monitoring provides trends and impact magnitude over time; Logging provides detailed events to pinpoint failing components and specific errors. Cloud Trace adds timing and relationships across operations.

**4. What details does a strong action item need?**

A concrete action, risk reduced, priority, owner, due date, verification method, and tracking link.

**5. What decisions does an error budget help teams make after an incident?**

It shows error budget consumption and helps balance feature release velocity against reliability engineering investments.

**6. Should a postmortem be delayed if the root cause is not yet fully identified?**

Not necessarily. You can document verified facts, open hypotheses, and action items to gather missing data or test hypotheses.

## References

- [Google SRE Book: Postmortem Culture](https://sre.google/sre-book/postmortem-culture/)
- [Google SRE Workbook: Postmortem](https://sre.google/workbook/postmortem/)
- [Google SRE: Managing Incidents](https://sre.google/workbook/managing-incidents/)
- [Google Cloud: Incident response](https://cloud.google.com/architecture/framework/operational-excellence/incident-response)
- [Cloud Monitoring documentation](https://docs.cloud.google.com/monitoring/docs)
- [Cloud Logging documentation](https://docs.cloud.google.com/logging/docs)
- [Cloud Trace documentation](https://docs.cloud.google.com/trace/docs)
- [Cloud Audit Logs overview](https://docs.cloud.google.com/logging/docs/audit)

## Conclusion

Postmortems help organizations turn a past incident into shared understanding and verifiable change. By describing impact, building an evidence-based timeline, analyzing causes alongside contributing factors, and maintaining a blameless approach, teams uncover weaknesses in architecture, monitoring, and processes. Action items need owners, priorities, and verification criteria, then connect back to SLIs, SLOs, error budgets, runbooks, and resilience testing. Reliability improves when post-incident lessons genuinely make systems easier to detect, contain, and recover.
