# Building Checklists Based on Quality Attributes

## 1. Why Does Architecture Assessment Need a Checklist?

A cloud design may work functionally during a demo yet fail when load increases, an Availability Zone experiences an outage, an account's permissions are exposed, the cloud bill exceeds budget, or the operations team cannot pinpoint the root cause of an error. These issues fall under **quality attributes**: characteristics that describe **how well** a system performs its functions under specific conditions.

In the **CLOUD_ARCHITECTURE** module, the goal of building a checklist is to translate business requirements into verifiable architectural questions, thereby evaluating choices in networking, compute, data, and deployment models. A checklist helps the team clearly see the trade-offs between reliability, security, scalability, cost, and operations, while structuring the assessment around **Well-Architected** thinking.

An effective checklist is not a list of checkboxes like "encryption enabled," "autoscaling configured," or "managed database used." Each item must clarify:

- **Risk to avoid:** how can the system fail?
- **Expectation:** what behavior is acceptable when encountering that risk?
- **Evidence:** what documentation, configuration, test results, or metrics prove it?
- **Owner:** who verifies, resolves, and accepts any residual risk?
- **Decision:** pass, fail, needs verification, or not applicable; can deployment proceed?

After this lesson, learners will be able to build quality-based checklists, define measurable criteria, validate against evidence, prioritize issues, and make well-founded architectural decisions.

## 2. Distinguishing Functional Requirements, Quality Attributes, and Constraints

| Requirement Type | Question Answered | Ordering Platform Example |
| --- | --- | --- |
| **Functional** | What can the system do? | Users can create orders, make payments, and view history. |
| **Quality Attribute** | How well and under what conditions does the system perform that function? | When traffic increases 5x, 95% of order-view requests complete within 400 ms; no confirmed orders are lost when a single node fails. |
| **Constraint** | What conditions must be complied with? | Personal data is stored only in approved regions; maximum budget; a specific integration protocol must be used. |
| **Assumption** | What is currently treated as true without evidence? | The payment partner will withstand 300 requests/sec and retries from the application. |
| **Architectural Decision** | Which option is chosen to satisfy requirements and what trade-offs are accepted? | Place stateless API services behind a load balancer and use a durable queue for background processing. |

Do not write "must have high availability" as a pass/fail criterion. The team must define the **target availability level**, measurement window, scope of services included, failures to withstand, and supporting evidence.

For example: "The order creation API achieves a 99.9% availability SLO over one month measured by the ratio of valid requests served successfully" is clearer than "good HA." For an assumed 30-day month, 0.1% corresponds to 43.2 minutes; however, **request-based SLOs** and **time-based SLOs** do not necessarily yield the same result. The SLI formula must be defined before interpreting the numbers.

It is also necessary to distinguish:

- **SLI** (*Service Level Indicator*): the observed quality measurement, such as successful request rate or p95 latency.
- **SLO** (*Service Level Objective*): the internal target set for an SLI.
- **SLA** (*Service Level Agreement*): a contractual commitment, which may include terms and consequences upon violation.
- **RTO** (*Recovery Time Objective*): the maximum target time to restore a service after an incident.
- **RPO** (*Recovery Point Objective*): the maximum amount of data that can be lost, typically expressed as a time interval. An RPO of 0 for confirmed transactions requires a corresponding durability mechanism and cannot be inferred from having daily backups.

The SLA percentage published by a cloud provider for an individual service is **not** a guarantee of end-to-end availability for an application composed of multiple components.

## 3. Selecting Relevant Quality Attribute Groups

There is no single fixed checklist for every architecture. The team must select the attributes that matter most based on the business, users, data, dependencies, and operating model.

| Attribute | What to Observe | Example Indicators / Verification Methods |
| --- | --- | --- |
| **Correctness and Data Integrity** | Are business outcomes accurate, consistent, and free of missing or duplicate records? | Number of lost confirmed transactions; order–payment reconciliation; idempotency checks. |
| **Availability** | Can the service serve requests when users need it? | Successful request ratio over a measurement window; instance/zone loss scenarios. |
| **Reliability and Resilience** | Can it tolerate faults, degrade gracefully, and recover properly? | Dependency failures, failover tests, recovery time, data loss. |
| **Performance** | Does it meet target speed and throughput? | p50/p95/p99, throughput, saturation, queue waiting time. |
| **Scalability** | When users/load increase, how does the system scale capacity? | Stress tests, autoscaling reaction, quotas, DB connection limits. |
| **Security and Privacy** | Are resources and data appropriately protected? | Threat model, IAM, encryption, vulnerability scans, unauthorized access tests. |
| **Observability and Operability** | Can incidents be detected, diagnosed, and resolved quickly enough? | SLI dashboards, alerts, traces, logs, runbooks, on-call drills. |
| **Maintainability and Modifiability** | Can it be modified, upgraded, and deployed safely? | CI/CD, release rollback, contract testing, lead time for changes. |
| **Interoperability** | Can it integrate reliably with other systems? | API contracts, schema compatibility, retry/backoff, rate limits. |
| **Cost Efficiency** | Is cost proportional to the quality level? | Load forecasts, unit cost per transaction, budgets, cost anomalies. |
| **Portability** | Can components be migrated when needed without excessive cost? | List of provider-dependent APIs, export/restore procedures, IaC. |
| **Sustainability** | Is resource waste avoided across the system lifecycle? | Right-sizing, autoscaling, cleanup of no-longer-needed data. |

These groups relate to the six pillars commonly used in **Well-Architected** assessments: **Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, Sustainability**. The two classifications serve different purposes: quality attributes describe the desired behavior of the system; pillars help structure the evaluation of design decisions and operational practices.

A single question may span multiple groups. For instance, adding replicas improves availability but impacts cost; enabling access logs aids auditing and investigation but increases cost while requiring protection of sensitive data in logs. The checklist must record **trade-offs**, rather than forcing every decision into a single bucket.

## 4. Turning Vague Requirements into Measurable Quality Scenarios

A good way to create a checklist is to write a **quality attribute scenario** with six parts:

1. **Source:** who or what event triggers the situation?
2. **Stimulus:** what happens?
3. **Environment:** what state is the system in when the stimulus occurs?
4. **Artifact:** API, database, queue, network zone, or the entire system?
5. **Response:** what should the system do?
6. **Response measure:** what metrics determine an acceptable result?

### Example A: Traffic Spike

| Component | Illustrative Content |
| --- | --- |
| Source | Client applications and end users |
| Stimulus | Order-view requests increase 5x within 2 minutes |
| Environment | Peak hours; system running normally |
| Artifact | CDN, API, cache, connection pool, PostgreSQL |
| Response | Scale out API, throttle DB access, return controlled errors when overloaded |
| Response Measure | In a representative load test: p95 under 400 ms, system error rate under 1%, DB connection limit not exceeded |

### Example B: Availability Zone Failure

| Component | Illustrative Content |
| --- | --- |
| Source | Infrastructure outage |
| Stimulus | A zone serving the application stops operating |
| Environment | Active payment and order transactions in progress |
| Artifact | Load balancer, compute, database, queue |
| Response | Route traffic to healthy components; preserve order correctness |
| Response Measure | Restore order creation flow within 10 minutes; zero loss of orders reported as successful; no duplicate payments created |

### Example C: Unauthorized Data Access

| Component | Illustrative Content |
| --- | --- |
| Source | Over-privileged workload account or leaked token |
| Stimulus | Request to read customer data outside the permitted scope |
| Environment | Production, multiple user groups |
| Artifact | IAM, API, database, audit logs |
| Response | Deny access, record the event, and emit an actionable alert |
| Response Measure | Negative authorization tests are properly denied; no unauthorized data returned; audit trail contains ID, timestamp, and context while avoiding sensitive data exposure |

The numbers in these examples are only for learning how to write criteria; they are not default standards for every product. Real thresholds must be agreed upon by business, architecture, and operations owners based on actual requirements and load data.

**Rule:** If a checklist item does not clearly specify what "pass" means, go back and write the scenario before scoring.

## 5. Designing a Reusable Checklist Structure

A checklist item should not be just a yes/no question. A suitable template for design reviews:

| Field | Meaning | Example |
| --- | --- | --- |
| **ID** | Stable identifier traceable across multiple reviews | REL-03 |
| **Attribute Group** | Primary quality group affected | Reliability |
| **Question/Risk** | What needs verification and the consequence if wrong | During database failover, can the API lose confirmed orders? |
| **Scope and Scenario** | Applicable workload, environment, and failure mode | Payment API in production, primary DB node loss |
| **Acceptance Criteria** | Measurable thresholds and conditions | Zero loss of confirmed transactions; recovery within approved RTO |
| **Verification Method** | Method and source of evidence | Failover rehearsal, transaction logs, reconciliation, RTO metrics |
| **Result** | PASS / FAIL / PARTIAL / NOT_VERIFIED / N/A | NOT_VERIFIED |
| **Risk Level** | P0, P1, or P2 based on business impact | P0 |
| **Owner, Due Date** | Accountability and target closure date | DBA and SRE before cutover date |
| **Links** | ADR, diagrams, configurations, test results, tickets | ADR-12, TEST-DR-04 |

Results should be defined consistently:

- **PASS:** Evidence exists matching the defined scope and criteria; evidence remains valid for the architecture version under review.
- **FAIL:** Verified and found not to meet the criteria.
- **PARTIAL:** Only part of the criteria is met, or test scope is insufficient.
- **NOT_VERIFIED:** Insufficient conclusive evidence, even if the design "looks right."
- **N/A:** Not applicable, requiring justification and approver sign-off; avoid using N/A to bypass risks.

Do not lump NOT_VERIFIED into PASS. An architecture pattern with a clean diagram that has not undergone load testing, recovery testing, or permission checks should only be recorded as **designed**, not **proven**.

### Sample Item in YAML Format

~~~yaml
id: REL-03
attribute: reliability
scope: "Production - Order Creation API and PostgreSQL"
question: "Does losing a database node cause confirmed orders to be lost?"
scenario: "Primary node failover under 100 transactions/sec"
acceptance:
  rpo: "0 for confirmed orders"
  rto: "10 minutes"
evidence_required:
  - "Failover rehearsal report"
  - "Before/after reconciliation by transaction ID"
  - "Measured detection and recovery time"
result: NOT_VERIFIED
risk: P0
owner: "Data Team and SRE"
due: "Before production approval"
decision_link: "ADR-012"
~~~

This YAML snippet is an illustrative **checklist content template**, not a mandatory repository format or runtime configuration. In practice, checklists can be stored in spreadsheets, issue trackers, or review tools with traceability support.

## 6. Preparing Inputs Before Asking Questions

A checklist is only valuable when it accurately describes the system being evaluated. At minimum, collect:

1. **Business context:** users, critical journeys, and impact of service downtime or data errors.
2. **Non-functional needs:** SLI/SLO, RTO/RPO, load, growth, budget, data protection levels, integration requirements.
3. **Current and target architecture:** context diagrams, containers/components, data flows, trust zones, accounts, and network boundaries.
4. **Resource and dependency inventory:** DNS, CDN, load balancers, compute, databases, caches, queues, third-party services, CI/CD.
5. **Data characteristics:** sensitivity classification, data residency, consistency levels, ownership, backups, lifecycle, and deletion flows.
6. **Operating model:** on-call, dashboards, alerting, change management, emergency access, runbooks, and drills.
7. **Existing evidence:** test results, production dashboards, incident history, security assessments, bills, ADRs, and unverified assumptions.

If a new architecture does not yet have production traffic, representative testing can be used for estimation; it must be clearly labeled as **test evidence**, not presented as live operational metrics.

### Traceability from Business Needs to Check Items

~~~mermaid
flowchart TD
  B[Business needs] --> S[Quality attribute scenario]
  S --> Q[Checklist questions and criteria]
  Q --> D[Architecture decision / ADR]
  Q --> E[Verification evidence]
  D --> T[Design / deployment configuration]
  T --> E
  E --> G{Meets criteria?}
  G -->|Yes| P[PASS, record scope and version]
  G -->|No| R[Risk, owner, remediation plan]
  G -->|Not measured| N[NOT_VERIFIED, test plan]
  R --> Q
  N --> E
~~~

This diagram emphasizes **traceability and feedback loops**. Architecture evaluation does not end at the review meeting; when the design changes or new evidence emerges, checklist statuses must be updated.

## 7. Sample Checklist Set by Quality Attributes

The following tables serve as a **starter question library**. Before using them in a project, the team must fill in specific thresholds, risk levels, owners, and evidence for each row.

### 7.1. Correctness, Consistency, and Data Integrity

| ID | Question to Answer | Suggested Evidence |
| --- | --- | --- |
| DATA-01 | For critical transactions, which data source is authoritative and where are transaction boundaries? | Data flow, ownership, schema, transaction boundary description. |
| DATA-02 | Can a retry operation create duplicate orders, payments, or invoices? | Idempotency tests, unique constraints, correlation IDs. |
| DATA-03 | When a DB write succeeds but event publishing fails, how are events prevented from being lost? | Transactional outbox or equivalent protocol, failure tests. |
| DATA-04 | Are late, redelivered, out-of-order events and deleted records handled properly? | Consumer contracts, retry/ordering/dead-letter tests. |
| DATA-05 | How stale can read data be, and which workflows strictly require reading fresh state? | Replica/cache diagrams, consistency requirements, tests. |
| DATA-06 | During migration or restore, how are record completeness and business totals reconciled? | Watermarks, key comparisons, business sums, checksums, discrepancy reports. |

**Typical hard stop:** If the system returns "payment succeeded" while the design allows losing the payment record in a failure scenario covered by an RPO = 0 requirement, this must be resolved before accepting the design.

### 7.2. Availability, Reliability, and Recovery

| ID | Question to Answer | Suggested Evidence |
| --- | --- | --- |
| REL-01 | Have SLIs/SLOs for critical user flows been precisely defined? | SLO document: numerator, denominator, exclusions, measurement window. |
| REL-02 | Is there any single point of failure in ingress, compute, database, or dependencies? | Failure domain diagram, AZ/node failure test results. |
| REL-03 | Are backups restorable, and are RPO/RTO met during rehearsals? | Restore tests, failover exercises, actual timing metrics. |
| REL-04 | Where are timeouts, retries, exponential backoff, jitter, and circuit breakers configured? | Configuration, dependency failure and retry storm tests. |
| REL-05 | When losing a zone or cloud service, how does the system degrade gracefully? | Fault injection scenarios, prioritized feature list. |
| REL-06 | Does losing connectivity to an external service block the entire system? | Bulkheads, queues, fallback policies, backlog handling runbooks. |
| REL-07 | Are controls in place for faulty deployments: canary, blue/green, app and data rollback? | Release pipeline, rehearsals, schema compatibility strategy. |

**Note:** Multi-AZ typically addresses failures within a single region; if recovery from a **region outage** is required, a dedicated backup strategy is needed covering replication, DNS/routing, and data consistency. Having a replica in another region does not automatically guarantee RPO = 0.

### 7.3. Performance and Scalability

| ID | Question to Answer | Suggested Evidence |
| --- | --- | --- |
| PERF-01 | Have normal load, peak load, and traffic ramp rates been described per user journey? | Traffic profiles, assumptions, business forecasts. |
| PERF-02 | Are p95/p99 latency, throughput, and error rate targets set for each critical API? | SLOs, performance test plans. |
| PERF-03 | What saturation thresholds and resource limits exist at each tier? | CPU/memory, DB IOPS, connections, quotas, queue depth. |
| PERF-04 | Does autoscaling react fast enough, and does it risk creating traffic bursts onto the DB? | Load/ramp tests, scaling logs, connection pool metrics. |
| PERF-05 | Are caches, CDNs, pagination, and indexes suited to real access patterns? | Query plans, cache hit ratios, profiling, invalidation tests. |
| PERF-06 | When load exceeds design capacity, does the system enforce backpressure, rate limits, and load prioritization? | Stress tests, queue limits, load-shedding policies. |
| PERF-07 | Is concurrent load tested across API paths, event consumers, and batch jobs? | End-to-end benchmarks on a representative dataset. |

**Note:** Using average CPU to conclude performance is usually insufficient. For APIs, track tail latency (p95/p99), errors, and downstream tier limits. Scaling out compute can **overload the database faster** if connection pools and concurrency are unmanaged.

### 7.4. Security, Privacy, and Compliance

| ID | Question to Answer | Suggested Evidence |
| --- | --- | --- |
| SEC-01 | Have critical assets, trust boundaries, and sensitive data flows been identified? | Threat model, data flows, data classification. |
| SEC-02 | Is least privilege enforced for users, services, CI/CD, and emergency access? | IAM policy reviews, access tests, grant/revocation procedures. |
| SEC-03 | Can internal services or databases be inadvertently accessed from the Internet? | Network topology, firewall/SG/NSG rules, scans and connectivity tests. |
| SEC-04 | Is data encrypted in transit and at rest, and how are keys/secrets managed and rotated? | TLS settings, KMS/Key Vault, secret rotation tests. |
| SEC-05 | Does the API properly handle authentication, authorization, validation, and rate limiting? | Security tests, resource/tenant-level authorization tests. |
| SEC-06 | Do logs/traces leak tokens, personal data, secrets, or financial data? | Log reviews, masking, retention/access policies. |
| SEC-07 | Are data residency, retention, deletion, and auditability constraints satisfied? | Data inventory, location policies, retention/deletion tests. |
| SEC-08 | Does the supply chain scan dependencies/images, sign artifacts, and control provenance/CI permissions? | Pipeline policies, scan reports, deployment attestation where applicable. |

Do not treat a cloud service offering encryption or IAM as proof that the application is secure. Under the shared responsibility model, the application team must still configure appropriate permissions, data flows, and defenses.

### 7.5. Operability, Observability, and Change Management

| ID | Question to Answer | Suggested Evidence |
| --- | --- | --- |
| OPS-01 | Who is the owner and on-call contact for each component, dependency, data store, and SLO? | RACI/on-call roster, runbooks. |
| OPS-02 | Are there dashboards showing error rates, latency, saturation, and business signals? | Dashboards, metrics catalog, alert rules. |
| OPS-03 | Are correlation IDs/traces propagated from APIs to DBs, queues, and workers? | Sample traces, distributed trace coverage. |
| OPS-04 | Do alerts have thresholds, recipients, severity levels, and next actions? | Alert inventory, incident drill results. |
| OPS-05 | Are deployment, rollback, feature flag, and schema compatibility processes in place to reduce release risk? | CI/CD, deployment history, rehearsals. |
| OPS-06 | Are IaC, config reviews, drift detection, and pipeline secrets management used? | IaC repository, plan reviews, drift detection evidence. |
| OPS-07 | Are postmortems conducted and preventive actions tracked after incidents? | Incident records, improvement backlog, owners and due dates. |

**Being observable** differs from **having logs**: if logs lack request IDs, metrics cannot distinguish endpoints, or alerts only report high CPU without tying to user impact, diagnosis time can still drag on.

### 7.6. Cost and Sustainability

| ID | Question to Answer | Suggested Evidence |
| --- | --- | --- |
| COST-01 | Does the estimate include compute, DB, storage, backup, NAT, egress, logs, and cross-region data transfer? | Cost model, load assumptions, and regional pricing sheets. |
| COST-02 | Have useful business unit cost metrics been defined? | Cost per 1,000 requests, per order, per tenant, or per GB processed. |
| COST-03 | Do redundancy and autoscaling configurations conflict with the budget? | Peak scenarios, cost envelope, capacity plan. |
| COST-04 | Are tags/labels, cost allocation, budget alerts, and cost owners established? | Billing dashboards, tagging policies, alert tests. |
| COST-05 | Are lifecycle policies in place for objects/logs/backups, test environments, and idle resources? | Retention policies, lifecycle rules, inventory. |
| COST-06 | Has resource efficiency been balanced alongside reliability requirements? | Right-sizing, utilization trends, policies to shut down unnecessary resources. |

Cost optimization does not mean mechanically reducing replicas. Output quality must be verified when changing redundancy levels and scaling capacity. Sustainability should also not be used as an excuse to cut essential data protection resources or resilience capabilities.

### 7.7. Interoperability, Modifiability, and Portability

| ID | Question to Answer | Suggested Evidence |
| --- | --- | --- |
| INT-01 | Do APIs, event schemas, and data contracts have versioning and compatibility policies? | OpenAPI/AsyncAPI specs, contract tests, deprecation plans. |
| INT-02 | Is there a plan for handling partner quotas, timeouts, and retries? | Integration tests, rate-limit models, DLQ/reconciliation. |
| MOD-01 | Do bounded contexts have clear interfaces that minimize cascading changes? | Component diagrams, dependency maps, change history. |
| MOD-02 | Are infrastructure and configuration reproducible with a change verification process? | IaC, pipelines, reproducibility tests. |
| PORT-01 | Have cloud-proprietary dependencies or hard-to-export data formats been documented? | Dependency inventory, ADRs, exit plans proportional to need. |

**Portability is not a mandatory goal for every system.** A team may intentionally adopt cloud-specific services if benefits outweigh lock-in costs; the checklist must capture the decision and mitigation strategy rather than forcing a generic architectural pattern in every case.

## 8. Adding Acceptance Criteria, Evidence, and Priority Levels

Checklists often fail because questions are too broad: "Are there backups?", "Is it secure?", "Is there monitoring?". It is necessary to specify **how much**, **under what conditions**, and **how it was tested**.

| Generic Question | Verifiable Version | Appropriate Evidence |
| --- | --- | --- |
| Are there backups? | Can PostgreSQL be restored to the required point in time within the approved RTO/RPO? | Restore rehearsal with timing metrics and data reconciliation. |
| Is autoscaling enabled? | When traffic increases 5x in 2 minutes, do p95 and errors stay within SLO? | Load test, scale-out timing, DB connections, p95. |
| Is data secured? | Is workload A blocked from reading tenant B; do logs exclude tokens? | Negative permission tests, log reviews, IAM configuration. |
| Is there monitoring? | When API 5xx errors cross threshold, do alerts reach the right person and link to a runbook? | Alert simulation, alert delivery time, runbook link. |
| Is cost optimized? | Does total cost for expected and peak load fit within the budget envelope? | TCO estimate with assumptions, cost anomaly/budget alerts. |

### Assigning Risk Levels

Use three simple levels as an example:

- **P0 — Approval Blocker:** risk of critical data loss/corruption, mandatory constraint violation, severe unauthorized access, or lack of an adequate recovery plan for core flows. A P0 FAIL or P0 NOT_VERIFIED cannot be considered resolved.
- **P1 — Must Address with Clear Due Date:** causes SLO degradation, significant operational disruption, or major cost increase, but has mitigations and an approver accepting responsibility within a defined scope.
- **P2 — Improvement:** suboptimal, can be placed in the backlog if residual risk is explicitly accepted.

P0/P1/P2 is an illustrative classification, not a universal Well-Architected mandate. Organizations may use different severity schemes; definitions and approval authorities must be established before the review.

### Scoring Completion Without Masking Risk

You can measure the **percentage of applicable items with PASS evidence**:

~~~text
Coverage = Number of PASS items / Number of applicable items × 100%
~~~

Here "applicable items" includes PASS, FAIL, PARTIAL, and NOT_VERIFIED; only N/A items with valid justification are excluded. For example, 18 PASS out of 24 applicable items equals 75% coverage. **This is an assessment progress metric, not a safety metric.** A design with 95% PASS should still not be approved if open P0 items exist regarding data loss or authorization.

Instead of looking solely at percentages, reports must separately highlight: open P0 counts, open P1 counts, stale evidence, critical assumptions, and risk acceptors. For mandatory criteria, apply **hard gates** before calculating any aggregate score.

## 9. Example: Filling Out a Checklist for a Cloud Ordering System

### 9.1. Architectural Context

An enterprise is migrating an ordering application to the cloud. Proposed architecture:

- HTTPS via CDN/WAF and load balancer to stateless Java API services.
- Managed PostgreSQL storing orders and payments; object storage storing invoices.
- Queues and workers handling emails and webhooks; transactional outbox ensuring events are published from committed transactions.
- Multi-instance API across multiple zones where supported by the service; database configured with HA and backups.
- Telemetry including metrics, traces, and logs with correlation IDs; per-workload IAM.

**Assumed requirements for this exercise:** order creation API p95 under 500 ms at target load of 200 requests/sec; zero loss of confirmed orders; 30-minute RTO for incidents within the planned scope; cost estimate within approved budget. Major scenarios like full-region loss or payment provider failure require separate specifications.

### 9.2. Illustrative Review Results Table

| ID | Criteria and Observed Evidence | Result | Priority | Action Required |
| --- | --- | --- | --- | --- |
| DATA-02 | Idempotency key exists for order creation API, but retry tests after timeout have not been run. | NOT_VERIFIED | P0 | Add retry tests and verify no duplicate orders/payments are created. |
| REL-02 | Multi-instance API; database has HA in design, but failover has not been rehearsed. | PARTIAL | P1 | Test node/zone failure within supported scope and measure impact on order creation flow. |
| REL-03 | Daily backups run; confirmed transactions require RPO = 0, but no proven solution exists for failover/cutover. | FAIL | P0 | Design durability mechanism, verify transactions and recovery; do not infer RPO = 0 from daily backups. |
| PERF-02 | Load test at 200 requests/sec: p95 460 ms, system error rate 0.3% under representative testing. | PASS | P1 | Document scope, timestamp, and test dataset; add separate peak and endurance tests. |
| SEC-02 | Workload IAM separated; one service account still holds broader database admin permissions than needed. | FAIL | P0 | Narrow permissions and test denied access cases. |
| OPS-02 | Latency/error dashboards exist, but alerts and runbooks for outbox backlog failures are missing. | PARTIAL | P1 | Add queue age/outbox lag alerts and rehearse handling. |
| COST-01 | Compute/DB estimates exist, but egress, log retention, and backups are omitted. | PARTIAL | P1 | Add TCO covering normal load, peak load, and growth. |
| PORT-01 | Object storage API dependency documented in ADR; organization accepts current lock-in. | PASS | P2 | Set a review milestone if multi-cloud strategy changes. |

**Example Conclusion:** Cannot issue a **GO** decision yet because DATA-02, REL-03, and SEC-02 at P0 are failing or unverified. The number of PASS items or acceptable latency cannot offset the risk of lost transactions and overly broad permissions.

A proper review must distinguish:

- **Observation:** "In load test X, p95 measured 460 ms at 200 requests/sec."
- **Conditional Inference:** "Performance targets can likely be met within the tested configuration and dataset scope."
- **Unknowns:** "No evidence yet for peak-day traffic, failover, or data skew."
- **Action:** "Performance team re-measures at peak load; data team conducts recovery rehearsal."
- **Decision:** "No production approval while P0 items remain open."

## 10. Handling Trade-offs Between Quality Attributes

A good architecture does not maximize every attribute simultaneously. The checklist should surface decisions and trade-offs for evaluation:

| Choice | Expected Benefit | Trade-offs / Risks to Evaluate |
| --- | --- | --- |
| Add replicas and multi-zone | Increase availability and fault tolerance | Added cost, failover mechanics, potential data lag. |
| Use caching | Reduce latency and database load | Invalidation, stale data, cache operations, privacy. |
| Increase strong consistency | Reduce data anomalies for sensitive transactions | May increase latency and reduce availability during network partitions. |
| Offload processing to queues | Reduce coupling and absorb spikes | Eventual consistency, retries, ordering, backlog, idempotency. |
| Use managed/serverless services | Reduce OS and partial infrastructure ops | Quotas, cold starts, per-request pricing, lock-in, config limits. |
| Increase observability/log retention | Improve incident diagnosis and auditing | Log storage cost, protecting sensitive data, metric cardinality. |
| Strengthen network/private endpoints | Shrink attack surface | Routing, DNS, egress/NAT costs, operational complexity. |

When two checklist items conflict, do not mark one as "not applicable" to erase the conflict. Record it as an **Architecture Decision Record (ADR)** including: prioritized requirements, alternatives, test data, impact on each attribute, residual risk, and approver.

For example: a very low p95 target and a requirement to always read the latest data may conflict when using a cache. Instead of choosing arbitrarily, classify endpoints: product catalog lookups may tolerate short-term stale data; account balances or payment statuses may need to read from the authoritative source. The design and checklist should reflect a **business-driven consistency policy**.

## 11. Process for Conducting an Architecture Review

### Phase 1: Define Scope and Participants

The review lead must know whether this is a **concept review**, **pre-production review**, **post-incident review**, or **periodic review**. Evidence depth varies by stage. Invite the right people: business representatives, architects, application owners, SRE/operations, data specialists, security, and cloud finance when needed.

The output is a list of critical business flows to protect, system boundaries, and high-priority quality attributes.

### Phase 2: Finalize Scenarios and Thresholds

For each critical attribute, write at least one appropriate **normal**, **peak load**, or **failure** scenario. Lock down SLI/SLO formulas, RTO/RPO scope, cost limits, and legal/security requirements. Explicitly document unverified assumptions.

The output is an agreed list of scenarios with testable criteria.

### Phase 3: Complete Checklist with Evidence

Each owner performs a self-assessment, with cross-reviews on P0/P1 items. Do not rely solely on slides or diagrams: require IAM/network configs, test reports, dashboards, query plans, runbooks, simulated bills, and restore evidence depending on the item.

Record the **architecture version**, measurement date, and environment. Sandbox evidence does not automatically prove production readiness.

### Phase 4: Failure Mode Analysis and Decisions

Pick several high-risk areas for a *scenario walkthrough*: zone loss, partner timeout, database failover, queue backlog overflow, leaked service account, unexpected traffic surge. For each step, ask: where is the failure detected, who handles it, does data stay accurate, and who has authority to halt deployment?

Classify P0/P1/P2; document fixes needed, temporary mitigations, owners, due dates, and residual risks.

### Phase 5: Conditional Approval and Follow-up

The review decision should be one of:

| Decision | Condition |
| --- | --- |
| **GO** | Mandatory conditions met; evidence is sufficient and scope is clearly understood. |
| **Conditional GO** | Only policy-permitted temporary risks remain, with mitigations, an approver, and a closure due date. Not used for policy-defined P0 blockers. |
| **NO-GO** | Mandatory conditions fail, critical evidence is missing, or risks are unacceptable. |

Do not treat a one-time review sign-off as indefinite proof. Changes to data, database versions, network topology, traffic profiles, or major integrations can invalidate previous evidence.

### Review Report Template

~~~text
System / architecture version:
Review date / review type:
Participants:
Critical business flows:
SLO / RTO / RPO / budget / security constraints:
Total applicable items:
PASS / FAIL / PARTIAL / NOT_VERIFIED / N/A:
Open P0 items (ID, risk, owner, due date):
Open P1 items (ID, mitigation plan, owner, due date):
Key assumptions:
Evidence / ADR / test reports:
Decision: GO | Conditional GO | NO-GO
Approving authority and approval date:
Re-assessment trigger/milestone:
~~~

## 12. Validating Checklists Across Lifecycle Stages

### Early Design

Rely primarily on requirements, threat models, diagrams, ADRs, reference architectures, and failure mode analysis. Items requiring load measurement or fault testing should stay **NOT_VERIFIED**, accompanied by a verification plan.

### Proof of Concept

Build a representative vertical slice through ingress → compute → data → queue/worker → telemetry. Test priority scenarios: DB connection failure, duplicate event handling, autoscaling, least-privilege IAM, and backup restore. Clearly document POC limitations such as small datasets, synthetic traffic, or different regions.

### Pre-Production

Require evidence closer to the live environment: contract tests, load testing, backup restores, incident drills, policy configurations, monitoring and alerting, and cost envelopes. Reconcile the deployed/IaC version against the reviewed version.

### Operations

Use SLI/SLO metrics, incidents, cost trends, vulnerability findings, capacity data, and workload changes to re-evaluate risks. Periodic checklists can focus on changes, but must not drop invariants such as data protection, privacy, and resilience.

## 13. Pitfalls That Undermine Checklist Value

| Pitfall | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Checklist with hundreds of identical questions for every project | High effort; reviewers just tick boxes to finish | Use a question library and select based on system journeys and risks. |
| Writing "yes/no" without thresholds | Cannot distinguish existence of config from meeting quality standards | Attach scenarios, SLIs/SLOs, scope, and evidence. |
| Accepting architecture diagrams or verbal claims as PASS | Unknown how the design behaves under real failures or load | Keep as NOT_VERIFIED until appropriate tests/measurements exist. |
| Rolling all items into an overall score and ignoring blockers | P0 issues get masked by many easy-to-pass items | Separate hard gates and report open P0/P1 items. |
| Not specifying owners | Risks sit unresolved on reports indefinitely | Assign owner, due date, and fix verification method. |
| Ignoring queues, batches, and third-party systems | End-to-end correctness is not guaranteed | Track the full business flow and integration boundaries. |
| Treating cloud SLAs as application SLOs | Cloud SLAs omit application logic and full dependency chains | Measure end-to-end and calculate actual failure domains. |
| Assessing once and never revisiting | Conclusions go stale after load, feature, or topology changes | Set re-assessment triggers tied to changes and incidents. |
| Confusing N/A with "not done yet" | Risks get erased from scope | N/A requires justification; missing evidence is NOT_VERIFIED. |

## 14. Practice Exercise

An online learning platform deployed on the cloud has:

- Frontend behind CDN/WAF; auto-scaling containerized Java APIs; managed PostgreSQL storing submissions and grades.
- Object storage holding submitted files; queues and workers for automated grading; external providers sending email and SMS.
- Normal load of 200 requests/sec; during exams, peak load can reach 8x. Every submission confirmed by the system must be preserved.
- Illustrative requirements: submission API p95 under 600 ms at target load, recovery time under 20 minutes for a single-zone outage, monthly budget within business-approved limits.
- Two user roles: students can only read their own submissions; instructors can view submissions and grades within classes they oversee.

Build a checklist with **at least 15 items**, covering data correctness, reliability, performance/scalability, security/privacy, observability/operability, and cost. For each item, fill in ID, question, scenario, threshold, required evidence, priority, and owner.

Next, assume the engineering team provides the following evidence:

1. At 200 requests/sec, p95 measured 420 ms; no test exists at 8x load.
2. PostgreSQL backups run daily; restore has not been rehearsed.
3. Submission API has an idempotency key, but grading workers do not yet prevent duplicate processing on retry.
4. Each application has its own service account, yet instructors can still call the API to read grades from other classes if they know the ID.
5. Dashboards show CPU and HTTP errors, lacking metrics for submissions received, ungraded submissions, or backlog age.
6. Cost estimates include compute and database, omitting object storage, egress, logs, and exam-period scaling.

**Required exercise deliverables:**

- Score each item as PASS, FAIL, PARTIAL, NOT_VERIFIED, or N/A, noting corresponding evidence.
- Identify the P0 items preventing a **GO** decision. Explain why passing latency at normal load does not prove readiness at exam load.
- Write two measurable quality attribute scenarios: one for peak load; one for database failure or zone outage.
- Select the top three priority tests and state what results count as passing.
- Propose an ADR documenting the trade-off between keeping extra standby compute capacity and cost-saving goals.
- Produce a final review report containing the decision, owners, due dates, and re-assessment conditions.

### Self-Assessment Guide

A strong submission should demonstrate three points. First, verification criteria tie directly to **critical user journeys**, especially confirmed submissions and preventing instructors from accessing data outside their classes. Second, PASS ratings have **proper evidence**; untested areas like peak load or recovery remain marked as unverified. Third, the report delivers a **justified decision** and actionable backlog rather than merely listing generic risks.

## 15. Methodological Conclusion

A quality-attribute checklist bridges business requirements and testable architectural decisions. The consistent workflow is **select critical flows → define attributes and scenarios → set thresholds → design questions → gather evidence → classify risks → make decisions → re-evaluate**.

A "Well-Architected" design is not one with the most cloud services or a fully checked-off table. It is a design where the team understands system behavior under critical conditions, holds evidence for commitments, recognizes trade-offs, and actively addresses unacceptable risks.
