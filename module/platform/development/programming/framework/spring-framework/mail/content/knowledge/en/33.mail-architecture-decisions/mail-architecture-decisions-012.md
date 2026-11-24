# Recording Decisions, Assumptions, and Alternatives

## 1. Why should an email-sending design be recorded as decisions?

A Spring Boot application can start with a few lines of `JavaMailSender.send(...)`. However, once in production, email is no longer “a function that sends a text string.” It may carry payment notices, order confirmations, account activation links, verification codes, invoices with attachments, system alerts, or marketing newsletters. Each category brings distinct requirements for reliability, processing time, security, and operability.

Engineering teams frequently have to decide:

- Send synchronously inside the request or persist to a **transactional outbox** and send via a worker?
- Use `SimpleMailMessage`, `MimeMessageHelper`, or an intermediate mail model?
- Send over SMTP via `JavaMailSender` or call a provider's HTTP API?
- Use multiple providers; under what conditions is fallback allowed?
- How many retries, what backoff, and how should **unknown** SMTP outcomes be handled?
- Render templates when creating the job or when the worker actually sends?
- Under what lifecycle are inline images, attachments, and personal data stored and deleted?
- When an SMTP provider accepts an email, what does a `SENT` status actually mean?
- Who is authorized to change sender domains, update templates, replay failed emails, or rotate SMTP credentials?
- What evidence must the system retain so that after an incident it can explain **why** this approach was chosen?

If only code, scattered comments, or meeting memories remain, months later someone else will see the **current implementation** without knowing:

1. The **context** at the time of the decision.
2. **Constraints** around business rules, technology, cost, and compliance.
3. **Assumptions** that lacked complete evidence.
4. **Alternatives** that were evaluated.
5. **Selection criteria** and accepted trade-offs.
6. **Residual risks**, owners, and conditions requiring re-evaluation.

That is why you should write an **Architecture Decision Record (ADR)** or an equivalent decision-log format. An ADR is a concise, evidence-backed record of an architecturally significant decision, not documentation describing every Java class.

> The goal of an ADR is not to prove the current choice is forever right, but to help others understand **why it made sense given known context**, what could invalidate it, and when it must change.

## 2. Distinguishing decisions, assumptions, constraints, options, and evidence

Five categories of information are easily conflated when designing Spring Mail.

| Element | Question it answers | Example in a mail system |
| --- | --- | --- |
| **Decision** | What **did we choose to do**? | Persist notifications in a PostgreSQL outbox and have a worker send via `JavaMailSender` |
| **Assumption** | What are we **provisionally treating as true** without full proof? | The SMTP relay can sustain 100 submissions/minute at peak |
| **Constraint** | What **must** be obeyed? | Never write password tokens or sensitive attachments into logs |
| **Alternative** | How else could this be solved? | Synchronous send; message broker; email provider HTTP API |
| **Evidence** | What data supports or refutes it? | Staging load test, incident records, provider SLA, benchmarks |

### 2.1. Decisions must be concrete enough to verify

Avoid writing:

> We use a good, reliable email sending solution.

Prefer writing:

> For transactional emails triggered by business state changes in PostgreSQL, the system writes a delivery intent in the **same transaction** as the business change. A separate worker reads the outbox, constructs MIME via Spring Mail, and sends over SMTP; business requests do not wait on SMTP. Retries and outcomes are recorded per delivery and attempt.

The second statement specifies the transaction boundary, processing mechanism, worker responsibilities, and verifiable evidence.

### 2.2. Assumptions are not guaranteed facts

For example:

> Assumption A-02: The SMTP provider typically responds in under 2 seconds.

This is a measurable assumption. Avoid writing:

> SMTP is always fast, so synchronous sending does not affect latency.

Without real load tests and p95/p99 measurements, never present speculation as a provider-guaranteed property.

### 2.3. Constraints must state their source and scope

For example:

~~~text
Constraint C-01
Source: Organization data protection policy
Scope: Emails containing personal data of EU customers
Requirement: Use only approved providers and regions
Priority: Mandatory
Owner: Security/Compliance
~~~

A lower-latency or cheaper SMTP provider is still ineligible if it violates a constraint. If a constraint comes from internal policy, cite which policy and who approved it rather than guessing from recipient domains.

### 2.4. Risks are distinct from assumptions

Assumption:

> SMTP retries will rarely encounter unknown outcomes.

Corresponding risk:

> If the connection drops after SMTP DATA after the relay already accepted the message, retrying or falling back can produce duplicate emails.

Risk descriptions need **likelihood/uncertainty**, **impact**, **mitigations**, and an **acceptor/owner**. Never just write `Risk: low` without explaining why.

## 3. When should an ADR be created?

Not every Java property change needs an ADR. Create one when a choice:

- Is hard to reverse or carries high switching cost.
- Affects multiple teams or modules.
- Carries risk of lost emails, duplicates, data leaks, or SLA breaches.
- Establishes foundational decisions on persistence, providers, contracts, and transaction boundaries.
- Changes the operational model, ownership, security posture, or cost structure.
- Depends on an important, uncertain assumption.

Examples of decisions **worth an ADR**:

| Topic | Why it matters |
| --- | --- |
| Sync send vs. outbox | Affects transactions, latency, retries, and failure recovery |
| SMTP vs. HTTP email API | Affects vendor lock-in, feedback, authentication, and migration |
| Single provider vs. multi-provider | Affects deliverability, identity, cost, and duplicate risk |
| `ACCEPTED/UNKNOWN/FAILED` model | Governs safety during retries and fallback |
| Storing MIME snapshots vs. template IDs only | Affects replay, audit, PII retention, and content mutability |
| Rendering templates at producer vs. worker | Affects consistency and versioning |
| Attachment storage strategy | Affects disk/object storage, security, and lifecycle |
| Bounce/complaint handling strategy | Affects suppression and contact policies |
| Tenant/region partitioning | Affects authorization, compliance, and provider eligibility |

Small changes may only need a pull request or issue:

- Renaming the variable `smtpTimeoutMillis`.
- Fixing a log typo.
- Adjusting template CSS under an approved design system.
- Adding a unit test for an existing branch.

If a “small” change alters an important contract—such as turning `timeout` into a blind resend—still update the ADR or risk rationale.

## 4. What fields belong in a good ADR?

A useful record typically includes:

| Field | Purpose |
| --- | --- |
| ID/title | Stable lookup and referencing |
| Status | Proposed, Accepted, Superseded... |
| Date | Date the decision was proposed or accepted |
| Owners/deciders | Technical owners and approvers |
| Scope | Email types, services, environments, tenants/regions |
| Context/problem | Current situation and what is broken or needed |
| Decision drivers | NFRs/SLOs, cost, security, operations |
| Constraints | Mandatory rules and policy sources |
| Assumptions | Assumptions with confidence levels and verification plans |
| Considered alternatives | Viable options evaluated |
| Decision/rationale | Chosen option and why |
| Tradeoffs/consequences | Gains, costs, and new operational impacts |
| Risks/mitigations | Remaining gaps and how they are reduced |
| Verification | Acceptance criteria, tests, and confirming metrics |
| Revisit triggers | Conditions requiring reconsideration |
| References | Issues, PRs, diagrams, benchmarks, policies, incidents |

Not every ADR needs to be dozens of pages long. For small decisions, one page suffices. For major decisions like an outbox or provider failover, document **assumptions and potential failure modes** thoroughly enough that future teams do not accidentally repeat old mistakes.

### 4.1. Stable IDs and meaningful titles

Examples:

~~~text
ADR-001: Send transactional emails via a transactional outbox
ADR-002: Use JavaMailSender and MIME for emails with attachments
ADR-003: Standardize SMTP outcomes into ACCEPTED/REJECTED/UNKNOWN
ADR-004: Fall back only when prior provider non-acceptance is proven
ADR-005: Persist template version and payload snapshot before enqueueing
~~~

Numeric IDs provide stable references and history; do not renumber when editing a title. Titles should express **what was chosen**, not vague topics like “Email architecture”.

### 4.2. ADR lifecycle states

A common lifecycle:

~~~text
PROPOSED
    |
    v
UNDER_REVIEW
    |
    +--> REJECTED
    |
    v
ACCEPTED
    |
    v
IMPLEMENTED
    |
    +--> REVISIT_REQUIRED
    |       |
    |       v
    |    New ADR
    |
    v
SUPERSEDED (by ADR-0xx)
~~~

These statuses are **team conventions**, not official enums in Spring Framework Mail. Some teams simply use `Proposed`, `Accepted`, `Deprecated`, and `Superseded`. What matters is defining them clearly:

- `Accepted`: chosen, though code may not yet be deployed.
- `Implemented`: code/config is running in production for the stated scope.
- `Superseded`: replaced by a newer decision while keeping the old record.
- `Rejected`: evaluated and not chosen; kept so the team does not re-propose it without new context.

Do not silently rewrite an old ADR into a new decision and erase history. When architecture changes significantly, create a follow-up ADR and link `supersedes` / `superseded-by`.

## 5. Ready-to-use ADR template

This template can be stored as Markdown in an architecture repository:

~~~markdown
# ADR-XXX: [Action-oriented decision title]

- Status: PROPOSED
- Created: YYYY-MM-DD
- Decision owner: [Role/team]
- Deciders: [Authorized approvers]
- Scope: [Service, email categories, tenant/region, environment]
- Related: [Prior issue/PR/ADR]

## Context
[Current state, problem statement, consequences of inaction]

## Goals / quality attributes
- [SLO/latency]
- [Reliability/recovery]
- [Security/privacy]
- [Observability/operations]
- [Cost/maintainability]

## Constraints
- C-01: [Constraint, source, and scope]

## Assumptions
| ID | Assumption | Confidence | Verification method | Owner |
| -- | ---------- | ---------- | ------------------- | ----- |
| A-01 | ... | Medium | ... | ... |

## Alternatives considered
### Option 1
- How it works:
- Benefits:
- Costs:
- Failure modes:

### Option 2
- How it works:
- Benefits:
- Costs:
- Failure modes:

## Decision
[Chosen approach, boundaries, exceptions]

## Rationale
[Deciding criteria; why alternatives were not selected]

## Consequences and tradeoffs
### Positive
### Negative
### Unknown / deferred

## Risks and mitigations
| Risk | Impact | Mitigation | Owner | Residual risk |
| ---- | ------ | ---------- | ----- | ------------- |

## Validation
- [Required tests/metrics/evidence]
- [Approver]

## Revisit triggers
- [Conditions that break assumptions]
- [Workload, provider, or requirement shifts]

## References
- [Issues/PRs/runbooks/benchmarks]
~~~

Bracketed items are placeholders. Replace them with real metrics and sources when applying; never leave `A-01: provider is stable` without describing how stability is observed or when it is re-evaluated.

## 6. Capturing context and decision drivers

An ADR can be technically accurate yet useless if it fails to articulate the **problem being solved**.

### 6.1. Weak context

> The company sends many emails, so we are replacing the email system.

This fails to distinguish latency, reliability, cost, deliverability, operations, or compliance issues.

### 6.2. Actionable context

> The order confirmation flow currently calls `JavaMailSender.send` directly inside the HTTP request. When the SMTP relay is slow or unreachable, endpoint p95 latency spikes and some requests fail even though the order creation transaction already committed. After restarts, there is no durable record of unsent emails. The team needs a mechanism that preserves send intents, decouples SMTP failures from order creation outcomes, and supports retries after crashes.

This context pinpoints:

- Where the request and mail boundary sits.
- The mismatch between the **business transaction** and the **side effect**.
- Impact on users and operations.
- Needs for durability, retries, and reconcilability.

### 6.3. Decision drivers should be prioritized explicitly

Example for transactional email:

| Criterion | Priority | Rationale |
| --- | --- | --- |
| No lost send intent after order commit | Must-have | Orders require recoverable notifications |
| Do not block HTTP requests on SMTP | Must-have | User experience and resilience |
| Per-delivery and per-attempt audit trail | Must-have | Supports incident investigation |
| Protection of PII/tokens | Must-have | Security |
| Latency from order creation to submission | High | Notification SLA |
| Operational overhead | Medium | Worker/DB maintenance is acceptable |
| Initial implementation simplicity | Medium | Avoid a broker if the DB handles the load |

A `Must-have` criterion must not be easily offset by high scores on `Low` criteria. If an option fails security or compliance constraints, eliminate it before scoring.

## 7. Alternatives must be documented fairly

A weak ADR details only the chosen option while dismissing others as “unsuitable.” Readers need to know why alternatives **were reasonable contenders** and under what conditions they would become the better choice.

### 7.1. Avoid strawman opponents

Unfair example:

~~~text
Option A: Synchronous send, error-prone, not worth using.
Option B: Outbox, superior in every dimension.
Chosen: B.
~~~

In reality, synchronous sending can be entirely reasonable for small, low-traffic apps where email is non-critical and users accept the resulting failure semantics. An outbox boosts reliability, yet requires:

- Database schema and cleanup.
- Worker/scheduler/queue ownership.
- Retries, backoff, timeouts, and dead letters.
- Duplicate controls, monitoring, and runbooks.
- Lifecycles for templates, attachments, and secrets.

An ADR should state both **costs and valid applicability** for unchosen alternatives.

### 7.2. Alternatives table for email delivery

| Option | Pros | Limitations / risks | When appropriate |
| --- | --- | --- | --- |
| Synchronous `JavaMailSender` in request | Few components, easy to debug, submission outcome known before responding | SMTP latency/outages impact requests; transactions do not cover SMTP | Small apps, optional emails, or workflows accepting timeouts |
| In-memory `@Async` / executor | Fast request returns, simple to implement | Jobs can vanish on JVM restart; error handling/queues are non-durable by default | Best-effort notifications in constrained environments |
| PostgreSQL transactional outbox | Intent persists atomically with business commit; clear retry/replay | Workers, DB load, schema, idempotency, and ops | Important transactional email with existing DB and moderate load |
| DB outbox + message broker | Scales well, decouples consumers, flexible retries/partitions | Higher complexity; requires DB/broker coordination, acks, dedup | High throughput and multiple downstream consumers |
| External notification service | Centralizes sending, templates, and provider routing | Service dependency, API contract, SLA, and ownership | Multiple products sharing notification capabilities |
| Direct provider HTTP API calls | May offer message IDs, templates/webhooks, and vendor idempotency | Vendor lock-in, auth/API quotas, vendor-specific semantics | When provider APIs and feedback fit requirements |

Never add a row claiming “Lost emails: never” for an outbox or broker. An outbox recovers send intents after crashes, yet **SMTP submission still has an ambiguous outcome window**, and inbox delivery cannot be inferred from `send` success alone.

### 7.3. Describing options via failure modes

For every alternative, document at least:

1. What happens if the **producer crashes** before or after business commit?
2. What happens to APIs/users if **SMTP is slow or unreachable**?
3. What happens if a **worker crashes after SMTP accepted** but before DB update?
4. What happens if the **provider returns UNKNOWN** after DATA or HTTP POST?
5. What happens if a **template or attachment disappears** before retry?
6. If operators need **manual redrive**, where is the evidence?
7. If a **tenant has data residency constraints**, can the option comply?

An option with a high average score that leaves a critical failure mode unresolved should not win simply because its “weighted total is high.”

## 8. Building a quantitative tradeoff matrix without false precision

A decision matrix structures discussion, yet weights and scores remain **team judgments**, not scientific facts.

### 8.1. Step 1: eliminate options violating constraints

Example:

~~~text
Constraint:
  Mail intent must be durable after business commit.

Option: @Async using in-memory executor only.
Result: Not eligible for this workflow.
~~~

Do not give `@Async` a 10 for low cost and let that score override a mandatory durability constraint.

### 8.2. Step 2: score remaining eligible options

Hypothetical example for an order service **already running PostgreSQL**:

| Criterion | Weight | DB Outbox | DB + broker | Notification service |
| --- | ---: | ---: | ---: | ---: |
| Intent recovery after crash | 30% | 5 | 5 | 4 |
| Operational simplicity today | 20% | 4 | 2 | 3 |
| Throughput scaling under load growth | 20% | 3 | 5 | 4 |
| Sufficient audit and reconcilability | 20% | 4 | 4 | 4 |
| Initial implementation cost | 10% | 4 | 2 | 3 |
| **Illustrative weighted score** | **100%** | **4.1** | **3.8** | **3.7** |

These numbers solely illustrate how to construct the table. In real decisions:

- Agree on what 1–5 means on the scale.
- Cite evidence backing each score.
- Mark confidence levels for estimates.
- Test sensitivity when weights shift.
- Explain explicitly if the final decision diverges from the raw score.

**Note on the arithmetic above:** options are scored 1–5 against the stated weights; never treat this table as a default Spring Mail benchmark.

### 8.3. Step 3: sensitivity analysis

If throughput grows severalfold, the weight of `Throughput scaling` might rise from 20% to 40% while `Simplicity` falls—making DB + broker more attractive. Record the threshold for change:

> Revisit when sustained daily email volume exceeds the PostgreSQL outbox capacity established by load testing, or queue-age SLO is violated after ordinary scaling.

This keeps the chosen design from becoming “eternal dogma” by giving it **known boundaries of validity**.

### 8.4. Cost is more than per-email pricing

For an SMTP/API provider:

~~~text
Total cost
  = provider charges
  + infrastructure/storage
  + retries and additional traffic
  + engineering and on-call
  + deliverability/incident costs
  + compliance/security controls
~~~

A provider cheaper on a rate card can cost more once incident and feedback integration expenses are included. Never write “B is cheaper” based solely on list pricing without checking workloads, attachments, retention, and support.

## 9. Managing assumptions as a verifiable register

Important assumptions should not stay buried inside prose. An **Assumption Register** shows what remains uncertain and who owns verifying it.

### 9.1. Example for Spring Mail

| ID | Assumption | Confidence | What if it is false? | How to verify | Owner |
| --- | --- | --- | --- | --- | --- |
| A-01 | Outbox workers handle peak load | Medium | Queue age rises, delayed emails | Load test and p95 queue age | Backend |
| A-02 | SMTP provider permits expected connections/quota | Low | Throttling / temporary failures | Contract check and staging test | Platform |
| A-03 | Logo image on classpath exists on every replica | High | MIME build fails | Artifact/container test | Build |
| A-04 | Attachment references stay readable through retries | Medium | Retries lose payloads | Retention / fault-injection test | Storage |
| A-05 | Most SMTP errors classify cleanly for safe retries | Low | Duplicates if UNKNOWN retried | Protocol testing and reconciliation | Mail owner |
| A-06 | Bounces report IDs sufficient for correlation | Medium | Suppression drifts | Webhook/DSN fixture test | Integration |
| A-07 | Marketing and security can share an account without SLO impact | Low | OTP delayed during campaigns | Capacity test, reserved quotas | Operations |
| A-08 | Backup/log data residency complies with policy | Unconfirmed | Internal policy breach | Contract/security review | Compliance |

These are **example assumptions**, not conclusions about any real provider.

### 9.2. Every assumption needs a status

~~~text
PROPOSED
   |
   +--> VALIDATED
   |
   +--> INVALIDATED
   |
   +--> EXPIRED / NEEDS_RECHECK
~~~

An assumption validated by last month's load test may expire after traffic grows, regions change, dependencies upgrade, or provider quotas shift. `VALIDATED` status should include the test date, environment version, and measurement scope.

### 9.3. Confidence cannot substitute for realism

For example:

> A-05: “An SMTP timeout after DATA always means the server rejected the message.”

This assumption is **unsafe**. In SMTP, the outcome is ambiguous if the client loses the reply after finishing DATA transmission. The ADR must document duplicate risk and an `UNKNOWN` design rather than marking `High` confidence to ignore protocol semantics.

### 9.4. Assumption → test → ADR decision

~~~text
Assumption A-01
    |
    v
Hypothesis:
  PostgreSQL outbox can keep queue age below SLO
    |
    v
Benchmark under representative workload
    |
    v
Evidence:
  throughput, DB IOPS, queue age, contention
    |
    v
Decision:
  accept DB outbox or revisit alternatives
~~~

When evidence disproves an assumption, update the decision or formally record risk acceptance. Never leave disproven assumptions in documentation simply because code is already implemented.

## 10. Distinguishing metrics, SLOs, SLAs, and delivery assumptions

Email spans multiple milestones. Without defining them, ADRs easily make unverifiable promises.

~~~text
Business transaction committed
         |
         v
Outbox intent persisted
         |
         v
Worker claims
         |
         v
SMTP/API submission
         |
         v
Provider accepts
         |
         v
Recipient mail server accepts (if feedback known)
         |
         v
Mailbox/inbox placement (often not directly observable)
         |
         v
User sees/reads email (not reliably provable)
~~~

### 10.1. Base SLOs on what is measurable

Instead of:

> 99.9% of emails reach the inbox in under 5 seconds.

Without reliable inbox-placement telemetry, choose an observable SLO:

> For eligible transactional emails, 99% of delivery intents are created and **successfully submitted to the SMTP/API provider** within N seconds of business commit, excluding explicitly defined suppressed or policy-blocked cases.

The threshold N must come from requirements and load tests, not a blanket 5-second default across all systems.

### 10.2. Distinguish delivered from accepted

A clean return from `JavaMailSender.send(...)` typically proves SMTP client submission finished and the relay accepted the message as observed, **not that it reached the inbox**. Provider delivery feedback may indicate recipient-server acceptance, deferral, bounce, or complaint—still not proof the user read it.

### 10.3. Set SLOs by email type

| Email type | Measurement goal | Risk if delayed |
| --- | --- | --- |
| OTP/security | Time from event to submission | Token expires, login fails |
| Transactional | Time from commit to submission | User lacks confirmation |
| Invoice | Completion before business deadline | Delayed invoicing, support tickets |
| Marketing | Throughput within campaign window, complaint rate | Off-hours delivery, reputation harm |
| Internal alert | Submission latency and alerting fallback | Missed incident response |

Not all email needs to share one pool, timeout, or retry policy. ADRs must state scope so marketing assumptions never leak onto OTP flows.

## 11. Writing decisions traceable to code and operations

An ADR must connect to the live system rather than sitting isolated as a one-time read.

### 11.1. Essential links

~~~text
ADR-001: Transactional outbox
   |
   +--> Work item / issue
   +--> Pull request introducing outbox tables
   +--> Database migration
   +--> MailOutboxService / MailDispatchWorker
   +--> Dashboard for queue age / retry
   +--> Runbook for SMTP outage
   +--> Incident reports
   +--> ADR-003 for provider outcome model
~~~

You do not need to list every Java file in the ADR. Link only the artifacts that **embody the decision** and the evidence maintainers need.

### 11.2. Where to store them?

A common layout:

~~~text
docs/
  architecture/
    decisions/
      0001-transactional-outbox.md
      0002-mail-payload-snapshot.md
      0003-provider-outcome-model.md
      0004-fallback-guardrails.md
      index.md
~~~

Keeping ADRs inside the repo eases pull-request reviews and stays synchronized with code. For cross-service decisions, a central architecture registry can work as long as participating repos reference it easily.

### 11.3. Why not rely solely on PR descriptions?

PRs show **implementation changes**, yet over time:

- Code evolves across many subsequent PRs.
- Newcomers do not know which PR captured the original decision.
- Rationale gets buried in review comments and threads.
- There is no clear `Superseded` status.
- There are no revisit triggers, assumption owners, or risk acceptances.

Keep ADRs as the **stable decision record**, linking out to PRs for implementation details.

### 11.4. A consolidated decision log

| ADR | Topic | Status | Owner | Latest evidence | Revisit trigger |
| --- | --- | --- | --- | --- | --- |
| ADR-001 | Mail outbox | Accepted | Messaging team | Load test L-01 | Queue age exceeds SLO |
| ADR-002 | Template snapshot | Proposed | Product + Backend | Prototype P-02 | Before production rollout |
| ADR-003 | SMTP outcome UNKNOWN | Accepted | Mail owner | Fault injection F-03 | Provider API changes |
| ADR-004 | Provider fallback | Under review | Platform | Vendor contract review | After secondary testing |

This is a structural example. “Evidence L-01” is not an existing report in the reader's project; replace placeholders with verifiable links in real usage.

## 12. Complete ADR example: sending transactional email via a transactional outbox

This is a **hypothetical example** illustrating how to write a reviewable, actionable ADR. Replace load parameters, SLAs, and requirements with real application data.

### ADR-001 — Decision

~~~text
ID: ADR-001
Title: Persist transactional mail intent in PostgreSQL outbox
Status: ACCEPTED (example)
Created: 2026-11-12 (example date)
Scope: Spring Boot Order Service; transactional confirmation emails
Owner: Backend Messaging
Deciders: Order Service owner + Platform owner
Supersedes: None
~~~

### 12.1. Context

When an order is created successfully, the application must notify the customer. The current implementation calls SMTP directly from the HTTP handler:

~~~text
POST /orders
    |
    v
BEGIN DB transaction
    |
    v
INSERT order
    |
    v
COMMIT
    |
    v
JavaMailSender.send(email)
    |
    v
HTTP response
~~~

When SMTP is slow, responses slow down. When SMTP fails after the business commit, the HTTP request may error out even though the order was created; users may resubmit and create duplicate orders if business idempotency is weak. If the process crashes before sending mail, no durable record remains to recover the notification.

### 12.2. Goals

- Never lose the **send intent** once the order creation transaction commits.
- Never block user responses on SMTP latency.
- Track status and attempts for every notification.
- Support retries, attempt caps, dead letters, and audited manual redrive.
- Never send to the wrong recipient or leak tokens/PII into logs.
- Emit metrics for queue age and latency from business commit to provider submission.

### 12.3. Constraints

- C-01: Orders and the mail outbox can share the same PostgreSQL transaction manager.
- C-02: Never send an email when the order creation transaction rolls back.
- C-03: Deliveries must be scoped by tenant, recipient, and business event.
- C-04: SMTP does not support distributed transactions with PostgreSQL.
- C-05: Never store SMTP passwords/tokens in the outbox table.

### 12.4. Assumptions

| ID | Description | Confidence | How to verify |
| --- | --- | --- | --- |
| A-01 | Existing PostgreSQL has enough capacity for outbox load | Medium | Load test measuring insert/claim/index/cleanup |
| A-02 | Workers can drain the queue within latency SLO | Medium | Staging test at peak workload |
| A-03 | SMTP provider has sufficient quota and verified identity | Unconfirmed | Vendor contract + test |
| A-04 | Attachment/payload references stay valid across retries | Medium | Retention/fault-injection test |
| A-05 | Stable business keys already exist for deduplication | Medium | Review order events and retries |

### 12.5. Alternatives considered

**Option A: continue sending directly inside the HTTP handler.**

- Pros: simple to implement, minimal components.
- Cons: request coupling, post-commit failures hard to recover, latency impact.
- Acceptable only when email is best-effort and durable intents are unneeded.

**Option B: use `@Async` or an in-memory executor.**

- Pros: requests do not wait on SMTP, minimal code changes.
- Cons: queued but unprocessed tasks vanish on restart; hard to audit and retry durably.
- Fails the durable intent requirement.

**Option C: PostgreSQL transactional outbox + worker.**

- Pros: commits order and intent in one transaction; queryable state/audit; uses existing DB infrastructure.
- Cons: requires job claiming, leases, indexes, retries, and retention; SMTP still has an UNKNOWN outcome window.

**Option D: order transaction + direct publish to message broker.**

- Pros: high throughput and scalable consumers.
- Cons: no atomic transaction between PostgreSQL order and broker publish without proper transactional coordination; producer crashes can drop events.
- Can still add a broker **downstream** of the outbox if scaling demands increase.

### 12.6. Decision

Choose **Option C**. Producers insert the outbox row **in the same transaction** as the order, and workers process after commit. Never perform SMTP submission inside the order creation transaction.

~~~text
POST /orders
    |
    v
BEGIN PostgreSQL transaction
    |
    +--> Insert order
    |
    +--> Insert mail_outbox(
    |      event_key, recipient, template,
    |      state=PENDING)
    |
    v
COMMIT
    |
    v
HTTP response (SMTP not awaited)

Separate worker:
    |
    v
Claim PENDING with lease
    |
    v
Build MIME and submit SMTP
    |
    v
Persist result ACCEPTED/RETRY/FAILED/UNKNOWN
~~~

### 12.7. Consequences

**Positive**

- Send intent is tied atomically to the business commit.
- Recovers cleanly from the outbox after restarts.
- Queue age and attempts become observable.
- Workers can pace throughput independently of HTTP traffic.

**Negative**

- Emails arrive asynchronously after the HTTP response (eventual consistency).
- Requires operating a job scheduler/worker and retry policy.
- Requires outbox history cleanup, data protection, and bloat prevention.
- Requires reconciliation when SMTP outcomes are ambiguous.

**Uncertain**

- Maximum DB claim/update throughput.
- Percentage of SMTP submissions ending in UNKNOWN.
- Real-world provider quotas and deliverability under growing load.

### 12.8. Risks and mitigations

| Risk | Impact | Mitigation | Residual |
| --- | --- | --- | --- |
| Worker crashes before sending | Delayed notification | Lease expiry and reclaim | Delay |
| Worker crashes after SMTP accepted, before DB commit | Duplicates if retried blindly | Mark UNKNOWN/reconcile, trace attempt/provider | Cannot prove exactly-once over plain SMTP |
| DB outage | Producer cannot commit orders/outbox | Apply failure policy, DB HA | Availability depends on DB |
| Mailbox quota throttled | Outbox backlog grows | Backoff, rate limiting, alerts | Delayed emails |
| Template/payload retention expires | Retries cannot rebuild mail | Immutable snapshot/reference and retention policy | Storage cost |
| Duplicate business event published | Duplicate emails | Unique business key per recipient/operation | Requires accurate key definition |

### 12.9. Validation / acceptance

Never state “the outbox guarantees zero lost mail” without tests. Example acceptance criteria:

1. Order creation rollback → no mail intent in outbox.
2. Order creation commit → outbox row exists even when SMTP is offline.
3. Worker restart before submission → intent survives and is reclaimed.
4. Concurrent claims by two workers → at most one valid owner per row at a time.
5. Temporary SMTP failure → scheduled retry, no tight spin loop.
6. SMTP timeout after DATA → outcome is not assumed to be definite FAILED.
7. Successful send → persists attempt/provider timestamps and correlation IDs.
8. Queue age/throughput/failed/unknown appear on dashboards.
9. Content/templates/attachments reproduce accurately across retries.
10. Security review confirms credentials and out-of-scope PII are excluded from logs.

### 12.10. Revisit triggers

- Sustained queue age exceeds business SLO despite reasonable worker/DB tuning.
- Volume causes outbox load to degrade order transaction performance.
- Multiple downstream services need the same notification event.
- Provider feedback/idempotency APIs enable a better submission model.
- Changing residency/retention rules invalidate current storage.
- UNKNOWN/duplicate rates exceed accepted risk appetite.

This ADR translates directly into implementation tasks, tests, and dashboards rather than simply saying “use an outbox because it is best practice.”

## 13. Illustrative Spring code for ADR-001

An ADR does not replace code, yet code examples clarify the chosen **architectural boundaries**.

### 13.1. Persisting business transaction and intent together

~~~java
package com.example.orders;

import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderApplicationService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public UUID createOrder(CreateOrderCommand command) {

        Order order = orders.create(command);

        outbox.insertOnce(new MailIntent(
                UUID.randomUUID(),
                command.tenantId(),
                "ORDER_CONFIRMED:" + order.id()
                    + ":" + command.recipientId(),
                command.recipientAddress(),
                "order-confirmation",
                order.id().toString()));

        return order.id();
    }
}
~~~

`OrderRepository`, `MailOutboxRepository`, `CreateOrderCommand`, and `MailIntent` are **application-defined interfaces/models**, not built-in Spring Mail classes. The key requirement illustrated is that `orders.create(...)` and `outbox.insertOnce(...)` share the **same transaction manager/datasource**, and `insertOnce` relies on a real unique constraint on the business key.

### 13.2. Illustrative database schema

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    business_key VARCHAR(250) NOT NULL,
    recipient_address VARCHAR(320) NOT NULL,
    template_key VARCHAR(120) NOT NULL,
    template_version VARCHAR(80),
    payload_ref VARCHAR(500),
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claim_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(tenant_id, business_key)
);

CREATE INDEX ix_mail_outbox_ready
    ON mail_outbox(status, next_attempt_at);
~~~

This schema illustrates the ADR rather than serving as a complete migration. Production also needs attachment manifests, provider attempts, retention, claim owners, auditing, and data protection. Never turn recipient emails into metric tags or log full rows for debugging.

### 13.3. Short claims without holding transactions across SMTP

~~~sql
WITH selected AS (
  SELECT id
  FROM mail_outbox
  WHERE status IN ('PENDING', 'RETRY')
    AND next_attempt_at <= now()
  ORDER BY next_attempt_at, created_at, id
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
UPDATE mail_outbox AS m
SET status='PROCESSING',
    attempt_count=attempt_count+1,
    claim_token=:claim_token,
    lease_until=now() + INTERVAL '2 minutes',
    updated_at=now()
FROM selected
WHERE m.id=selected.id
RETURNING m.id, m.attempt_count,
          m.recipient_address, m.template_key,
          m.payload_ref;
~~~

Claiming and inserting attempt history (if used) must commit in a short transaction. The worker then invokes SMTP **outside any transaction** and persists the outcome in a separate transaction provided the claim token still matches the current attempt.

### 13.4. Why not wrap both order logic and SMTP send in `@Transactional`?

~~~java
@Transactional
public void createAndSend(CreateOrderCommand cmd) {
    orders.create(cmd);
    mailSender.send(prepareMimeMessage(cmd));
}
~~~

A database transaction does not span network SMTP sending:

- SMTP may accept the email before the DB transaction rolls back → email sent for a non-existent order.
- DB connections and locks stay held during slow network I/O.
- Exceptions or timeouts do not prove whether the submission was accepted.

ADRs must state the **transaction boundary** explicitly rather than saying “send email inside a @Transactional method.”

### 13.5. Retries and UNKNOWN require a supporting decision

Never capture all reliability logic in a single catch block:

~~~java
catch (Exception ex) {
    scheduleRetry();
}
~~~

A retry policy must classify at least:

~~~text
DEFINITE_RETRYABLE_FAILURE
DEFINITE_PERMANENT_FAILURE
UNKNOWN_SUBMISSION_OUTCOME
~~~

If the client loses connectivity after SMTP DATA, you cannot prove the relay rejected the email. Blind retries or fallback risk duplicates. Therefore, ADR-001 should link to a companion ADR defining `UNKNOWN` policy, duplicate tolerance, and reconciliation.

## 14. Second ADR: SMTP provider adapter and fallback

The outbox ADR addresses **persisting intents and scheduling sends**. A separate decision must govern **which provider is selected** and when switching to a backup provider is permitted.

### 14.1. Context

The system uses SMTP provider A for transactional mail. When A has an outage, outbox backlog rises. The team considers adding provider B to preserve SLOs. However:

- From domains, DKIM/SPF/DMARC, accounts, and sender identities must be verified on B.
- B may use different regions and log retention.
- SMTP lacks a universal idempotency key like some HTTP APIs.
- An attempt on A may end in UNKNOWN after a timeout.
- Bounces/complaints from A may still arrive after switching to B for new mail.

### 14.2. Options

| Option | Idea | Pros | Risks |
| --- | --- | --- | --- |
| A | Single provider, retry/backoff | Simple operations, consistent identity | Vulnerable to single-provider outages |
| B | Two providers, fall back on any exception | Protects against some outages | Serious duplicate email risk |
| C | Two providers, fall back only on proven non-acceptance when B is eligible | Balances resilience and duplicate control | Needs classifier, policy, and operations |
| D | Use HTTP APIs with idempotency and status lookups throughout | Better submission reconciliation depending on API | Vendor lock-in and migration cost |

### 14.3. Decision

Select **Option C** within approved email scopes. Provider B is a candidate only when all conditions hold:

~~~text
tenant/region/category policy
AND sender identity verified
AND attachment/size capability
AND provider contract/quota
AND TLS/security requirements
AND feedback/bounce handling available
~~~

After attempt A:

~~~text
ACCEPTED
   -> stop submitting; await feedback

DEFINITE_REJECTED (retryable, before submission)
   -> may try approved B within attempts/deadline

DEFINITE_REJECTED (permanent/policy)
   -> do not blindly fallback

UNKNOWN
   -> hold/reconcile; never equate timeout with no submission
~~~

### 14.4. Assumptions and evidence

| Assumption | How to verify | If false |
| --- | --- | --- |
| B has valid sender identity and DKIM | Mailbox test, check auth headers | Rejections/spam/DMARC failures |
| B has enough quota during A's outage | Capacity testing, contract | Secondary overload |
| Policy permits B to process this region | Security/legal sign-off | Data handling violation |
| Adapter classifies pre-submission errors accurately | SMTP fault injection | Duplicates if misclassified |
| Provider logs/feedback exist to investigate UNKNOWN | Incident workflow test | Heavy manual intervention needed |

### 14.5. Consequences

**Pros**

- New deliveries or proven pre-submission failures can route to an eligible secondary provider.
- Prevents provider B from handling unauthorized regions or identities.
- Route and fallback decisions remain auditable.

**Cons**

- Must manage two sets of credentials, quotas, DNS records, and webhooks.
- Must record provider IDs and route-policy versions per attempt.
- Cannot guarantee automatic continuation for every error; `UNKNOWN` requires reconciliation.
- Increases deliverability testing and on-call overhead.

### 14.6. Revisit triggers

- Provider B ceases to comply with region/compliance policies.
- Provider B's quota cannot absorb A's outage traffic.
- API or idempotency contracts change.
- Duplicate email rates exceed accepted risk tolerance.
- Per-recipient feedback becomes mandatory where SMTP A lacks it.

**Takeaway:** an ADR must document not only “we have a backup provider,” but also the **situations where fallback is strictly forbidden**.

## 15. Third ADR: rendering templates and snapshotting email content

An easily overlooked decision is **when to render** an email and **where to store input data**. It directly affects consistency and retry safety.

### 15.1. Three options

**Option A — Store only template key and domain entity ID.**

~~~text
Outbox:
  orderId=O123
  templateKey=order-confirmation

At send:
  load order O123
  render current template
~~~

Pros: minimal redundant storage; templates stay up to date. Cons: if the order or template changes between enqueue and send, content may no longer match the original event. If the entity is deleted or moved, retries lack needed data.

**Option B — Store an immutable mail model snapshot and template version.**

~~~text
Outbox:
  deliveryId=D1
  templateKey=order-confirmation
  templateVersion=v12
  modelSnapshotRef=object://.../snapshot-v1

At send:
  load frozen model and template version
  render
~~~

Pros: content reproduces faithfully on retry without depending on mutable entities. Cons: requires managing template versions, storage, retention, and PII.

**Option C — Render complete HTML/text/MIME at enqueue time.**

~~~text
Outbox:
  deliveryId=D1
  renderedHtmlRef=...
  renderedTextRef=...
  attachmentsRef=...
~~~

Pros: output is frozen; easy to inspect exact planned content. Cons: increases storage footprint, risks keeping stale information, and requires managing MIME/attachment lifecycles and deletion.

### 15.2. A conditional decision

For example, choose **Option B** for auditable invoice emails, and **Option A** for best-effort newsletters that do not require historical content preservation. The ADR should define scope per category rather than forcing one rule on all mail.

| Email type | Priority | Evaluation recommendation |
| --- | --- | --- |
| Transaction confirmation | Reproduce state at event time | Snapshot model + template version |
| Invoice | Exact amounts/content, audit trail | Frozen payload/document version |
| OTP/password reset | Short lifetime, do not retain tokens long | Never log tokens; dedicated expiry and policy |
| Marketing | Deliver campaign template version | Campaign version, consent, and suppression |
| Scheduled reports | May generate content at send time | Render-time data per requirement |

### 15.3. Assumptions to record

- Template version v12 remains retrievable throughout the retry window.
- The model snapshot holds all fields needed for rendering without querying mutated domain entities.
- Object storage retains valid attachment versions throughout the delivery window.
- Sensitive fields in snapshots are protected and deleted per retention schedules.
- `UTF-8` encoding and locale/timezone settings preserve identical output on re-render.

### 15.4. Failure mode

~~~text
Order changed from "pending" to "cancelled"
       |
       v
Outbox created before cancellation
       |
       v
Worker renders using CURRENT order
       |
       v
Email may not describe original event
~~~

Conversely, if an email is delayed for days, snapshotted content can become **stale** (for example, an expired OTP). Therefore, alongside snapshots, enforce a **business expiry** and state policy governing when sending must stop.

### 15.5. Sample conclusion for ADR-005

> For transactional emails requiring faithful reproduction, store the template ID/version and an immutable model snapshot in access-controlled storage; workers render strictly from that snapshot without querying mutable entities arbitrarily. For short-lived tokens, never retain tokens beyond validity and halt sending upon expiry. Attachment references are pinned to immutable versions with retention covering at least the allowed retry window.

**Residual risk:** storing snapshots increases storage cost and PII footprint. Encryption, authorization, retention, redaction, and deletion tests are required. These trade-offs belong in the ADR, not buried solely in storage runbooks.

## 16. Making explicit decisions on SimpleMailMessage and MimeMessageHelper

Even an API choice within Spring Mail affects contracts.

### 16.1. When SimpleMailMessage suffices

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("no-reply@example.com");
mail.setTo("recipient@example.net");
mail.setSubject("Notification");
mail.setText("Plain text content.");
mailSender.send(mail);
~~~

`SimpleMailMessage` fits plain-text emails that need no HTML, inline resources, or attachments. In an ADR, it is a sensible choice when products only need short notifications without complex templates.

### 16.2. When MimeMessageHelper is required

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("recipient@example.net");
helper.setSubject("Confirmation");

helper.setText(
        "Confirmation information in plain text.",
        "<html><body>"
            + "<p>Confirmation information</p>"
            + "<img src=\"cid:companyLogo\" alt=\"Logo\">"
            + "</body></html>");

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

mailSender.send(mime);
~~~

With MIME, the ADR should evaluate:

- Whether the plain-text alternative matches the HTML meaning.
- Inline images use Content-ID; local filesystem paths in HTML are unreachable by recipients.
- Appropriate `MimeMessageHelper` multipart mode and encoding.
- Whether attachment sources are reopenable streams surviving until transport reads them.
- Whether sensitive files/documents may be emailed directly.
- Template complexity, MIME size, and rendering consistency across mail clients.

### 16.3. Decisions can sit at the intermediate model layer

Rather than letting every service depend on `MimeMessageHelper`, you can standardize on an intermediate mail model:

~~~java
public record MailComposition(
        String recipient,
        String senderIdentityId,
        String subject,
        String plainText,
        String htmlText,
        java.util.List<InlineAssetRef> inlineAssets,
        java.util.List<AttachmentRef> attachments) {
}
~~~

`InlineAssetRef` and `AttachmentRef` are application-defined types holding authorized resource IDs/versions; never hold single-use `InputStream` instances or HTTP-request temp files. A mail composer/builder turns the model into a `MimeMessage`, while the provider adapter handles delivery.

When a product has many templates and providers, this intermediate layer lowers coupling at the cost of an extra abstraction. The ADR should judge whether that complexity is warranted right now.

## 17. Decisions on retries, dead letters, and state semantics

A mail system lacking crisp state definitions triggers endless operational debates:

> This email says `SENT` — does that mean the recipient saw it?

Not necessarily. You usually need to distinguish:

~~~text
PENDING
   |
   v
PROCESSING
   |
   +--> ACCEPTED (SMTP/API provider accepted submission)
   |
   +--> RETRY (definite failure, eligible for another attempt)
   |
   +--> FAILED (terminal; no automatic retry)
   |
   +--> UNKNOWN (provider may have accepted)
                 |
                 v
              RECONCILE
~~~

Email providers may emit additional downstream events:

~~~text
ACCEPTED
   |
   +--> DEFERRED
   |
   +--> RECEIVER_ACCEPTED / DELIVERED (per provider definition)
   |
   +--> HARD_BOUNCE / COMPLAINT
~~~

### 17.1. Decisions must specify which layer defines “success”

An ADR might state:

> `ACCEPTED` is an application-level observation that the SMTP relay accepted submission or the HTTP provider received the request per contract. It does not guarantee inbox placement, reading, or user completion. Bounce and delivery feedback events are stored in a separate projection.

Never equate `MailException` with a definite failure. When an error occurs after SMTP DATA or an HTTP POST reached the provider, the outcome may be `UNKNOWN`. Blind resends risk duplicates, especially when switching providers.

### 17.2. Max retry attempts is an explicit decision

You can tabulate:

| Failure class | Handling | Rationale |
| --- | --- | --- |
| DNS/connect failure before submission | Retry/backoff; fall back if eligible | Proven not accepted |
| Verified temporary rejection | Bounded retry | Reasonable chance of recovery |
| Permanent invalid recipient | FAILED/suppress per policy | Switching providers likely will not help |
| Template validation | FAILED; fix input/template | Repeated retries will not fix bad data |
| SMTP timeout after DATA | UNKNOWN/reconcile | May already be accepted |
| HTTP API idempotent POST timeout | Retry same key within TTL or query status | Per specific provider contract |
| Security content policy violation | Quarantine/FAILED | Never auto-redrive |

### 17.3. A dead-letter queue is not just a log message

If an ADR states “failed emails go to the DLQ,” specify **where the DLQ lives**, whether it is durable, and its audit, retention, and redrive workflow.

~~~text
Mail attempt fails permanently
        |
        v
BEGIN DB transaction
        |
        +--> mark delivery FAILED
        +--> insert dead_letter_event
        +--> update attempt outcome
        |
        v
COMMIT
        |
        v
Operator review/redrive (authorized)
~~~

Naming a Spring Integration `DirectChannel` `deadLetterChannel` does not persist failed messages across JVM restarts. When using RabbitMQ or Kafka, define durability, ack/offset semantics, and retry/deduplication rules.

### 17.4. Lease and worker risks

Atomic claim/lease protects against two workers mutating state together, yet does not prevent duplicate external side effects:

~~~text
Worker A starts SMTP
  |
  +-- lease expires while network is slow
             |
             v
Worker B reclaims and sends
             |
             v
A might also be accepted
~~~

The ADR must define timeouts, heartbeats, fencing tokens, reclaim policies, and handling for ambiguous attempts. Never write “exactly once” simply because you use `FOR UPDATE SKIP LOCKED`.

## 18. Security and data decisions cannot wait until later

Emails carry contact addresses, order details, invoices, documents, and password reset links. Architectural choices affect **data minimization, retention, access controls, regions, and threat models**.

### 18.1. Constraints worth documenting

| Topic | Decisions needed |
| --- | --- |
| Credentials | Secret manager/runtime injection, rotation, no raw logs |
| Transport | SMTP STARTTLS/implicit TLS, hostname verification, timeouts |
| Sender identity | Verified From, DKIM/SPF/DMARC, envelope MAIL FROM |
| Data residency | Approved providers/regions, logs/backups/webhooks |
| PII | Data minimization, encrypted snapshots, retention/deletion |
| Attachments | Immutable references, malware/size checks, tenant scoping |
| HTML | Contextual escaping, trusted template sources |
| Inbound webhooks | Signature verification, replay protection, event deduplication |
| Operator actions | RBAC, redrive auditing, suppression checks |
| Compliance | Policy source, owner, effective dates, exception approval |

### 18.2. Data ADRs must separate “must” from “nice to have”

For example:

~~~text
Must:
  EU-regulated payload is processed only through approved path.

Could:
  Prefer provider with lower average latency.
~~~

Never use a latency score to override a residency constraint. If the backup provider is non-compliant, hold the mail (`HOLD`) and alert rather than violating policy.

### 18.3. Decisions on raw logging

Instead of:

~~~java
log.error("Failed to send message {}", mimeMessage, exception);
~~~

prefer structured metadata:

~~~json
{
  "event": "mail.delivery.failure",
  "deliveryId": "opaque-delivery-id",
  "attemptId": "opaque-attempt-id",
  "providerGroup": "transactional-primary",
  "stage": "SMTP_DATA",
  "outcome": "UNKNOWN",
  "safeErrorCode": "SMTP_RESPONSE_TIMEOUT"
}
~~~

Never place raw subjects, bodies, attachment bytes, access tokens, or recipient emails in metric tags. Detailed incident logs require approved access controls, masking, and retention policies.

### 18.4. An assumption about a provider can be a compliance risk

> A-08: “Provider B hosts its SMTP endpoint in the EU, so all data stays in the EU.”

This is **an unsafe conclusion**: the endpoint location can differ from where logs, backups, support tools, or webhooks are processed. Verify contracts and actual data flows rather than assuming from an `eu-...` hostname.

### 18.5. Managing policy exceptions

If a team proposes sending PII documents through an unapproved provider to cut latency, that is not merely a technical trade-off. Require:

~~~text
Policy requirement
     |
     v
Provider eligibility review
     |
     +--> Compliant -> candidate
     |
     +--> Not compliant -> reject
     |
     +--> Exception request -> authorized risk owner review
~~~

An ADR may reference an **approved exception record**, its expiration date, and its scope. It never replaces approval from the proper authority. A chat note saying “security agreed” is insufficient without evidence and scope.

## 19. Validating decisions with experiments and fault injection

An ADR quickly devolves into opinion debates unless paired with verification methods. For Spring Mail, critical failure windows usually **never appear in happy-path demos**, so turn them into explicit test scenarios.

### 19.1. Experiments for synchronous sending vs. outbox

| Experiment | Setup | Data to collect |
| --- | --- | --- |
| SMTP relay offline | Stop fake SMTP before creating order | Does order commit? Does outbox persist? HTTP behavior? |
| Slow SMTP | Inject 15-second response delay | HTTP p95, worker latency, queue age |
| Producer crash | Kill immediately after DB commit | Does the mail intent survive? |
| Worker crash | Kill after claim, before send | Lease/reclaim, history, no lost intent |
| Lost SMTP response | Drop connection after DATA | Outcome UNKNOWN, policy avoids blind retry |
| DB outcome update fails | Relay accepted, DB fails | Reconciliation and duplicate risk |
| Burst traffic | Simulate peak load | DB contention, throughput, SLO |

Tests using only Spring MockMvc cannot verify SMTP protocol semantics. Use a programmable fake SMTP server, Postgres Testcontainers, and fault injection at appropriate boundaries.

### 19.2. Experiments for templates and attachments

~~~text
Create mail intent with:
  templateVersion = v12
  attachmentVersion = object-v3

Then:
  deploy template v13
  update original document to object-v4
  restart worker
  retry delivery

Observe:
  Is MIME content still v12 + object-v3?
~~~

If the ADR specified snapshots yet the test renders new content, the implementation failed to realize the decision.

### 19.3. Experiments for multi-provider fallback

- A refuses connection before submission; B is eligible → B may be selected.
- A times out after DATA; B is eligible → no automatic fallback; transition to UNKNOWN.
- A returns a permanent recipient rejection → do not retry B merely to work around the rejection.
- B lacks a verified sending domain → exclude B from the candidate set.
- B sits outside the approved region → fail closed even during an A outage.
- A accepted, feedback not yet received → do not submit to B.
- B webhook arrives late after failback → still correlates cleanly to B's attempt.

### 19.4. Define pass/fail criteria before running experiments

Never benchmark first and pick thresholds afterward to declare success. For each acceptance test:

~~~text
Experiment ID: EXP-MAIL-07
Hypothesis: Outbox survives a worker crash
Input: 100 test deliveries, 1 worker killed after claim
Expected: 100 durable intents remain accounted for;
          none silently disappear
Observed: [filled after test]
Status: PASS / FAIL / INCONCLUSIVE
Environment: [DB version, SMTP fake, build, date]
Evidence: [link to test/artifact]
~~~

These test parameters are illustrative only. In production, define “accounted for” precisely—such as across `PENDING/RETRY/PROCESSING/ACCEPTED/FAILED/UNKNOWN`—and distinguish **business intents** from **SMTP submissions**. Never claim exactly-once delivery based solely on outbox row counts.

### 19.5. Strength of different types of evidence

| Evidence | What it can prove | What it cannot yet prove |
| --- | --- | --- |
| Unit tests for planner | Fallback rules behave as coded for mocked inputs | That a real SMTP provider behaves identically |
| Testcontainers PostgreSQL | Row locking/constraints/migrations in test env | Production DB behavior under identical peak load |
| Fake SMTP | MIME layout and certain send failure modes | Real inbox placement across providers |
| Vendor staging | Staging contract and limits | That production accounts have identical quotas/reputation |
| Production metrics | Actual behavior over the measured interval | Root causes or universality across all incidents |
| Vendor SLA/contract | Contractual commitments | Zero outages or zero duplicates |

When updating an ADR, state precisely “proven under these conditions” rather than simply “tested.”

## 20. Decision-making and approval workflow

An ADR helps teams collaborate and preserve history; the process should stay lightweight while maintaining clear ownership.

### 20.1. Recommended lifecycle

~~~text
Trigger: issue / incident / requirement
              |
              v
Architecture owner drafts ADR
              |
              v
List constraints, assumptions, options
              |
              v
Collect evidence / prototype
              |
              v
Review by affected teams
              |
        +-----+------+
        |            |
        v            v
     Accepted      Rework/reject
        |
        v
Link implementation PR/migrations
        |
        v
Deploy with telemetry/rollback
        |
        v
Record observed consequences
        |
        v
Revisit when trigger occurs
~~~

### 20.2. Who needs to be involved?

| Decision category | Typical stakeholders needed |
| --- | --- |
| SMTP integration/API contract | Backend, integration, platform |
| Outbox/DB schema | Service owner, DBA/platform, SRE |
| OAuth/credentials/TLS | Security, platform |
| Provider/region/data retention | Legal/compliance, security, vendor owner |
| Marketing consent/suppression | Product, compliance, marketing operations |
| OTP/security latency | Identity/security, product, on-call |
| Attachment storage | Backend, storage, security |
| On-call/runbooks | Operations/SRE, service owner |

Not every group needs to sign off on minor tweaks. However, if a choice changes compliance obligations, retry side effects, or data processing regions, bring in the proper owners before marking `Accepted`.

### 20.3. Distinguishing proposer, decider, and implementer

~~~text
Proposer: frames the problem and options
Decider: approves the choice under granted authority
Implementer: executes according to the ADR
Reviewer: verifies relevant requirements and risks
Operator: runs the system and supplies production feedback
~~~

One person may wear multiple hats on a small team. Still, know who owns **updating the ADR when assumptions break** and who is authorized to accept residual risk.

### 20.4. Decision time-boxing

Teams can stall indefinitely waiting for perfect information. An ADR can state:

> Adopt Option C for 90 days capped at 2 workers and a single provider, then measure queue age and throughput. If SLOs fail or the provider ships stronger idempotency APIs, reopen the decision.

That establishes a **time-boxed, scoped decision** rather than “carved in stone forever.”

### 20.5. Recording what was intentionally deferred

For example:

~~~text
Decided now:
  PostgreSQL outbox + one SMTP provider.

Deferred:
  Multi-region active-active mail dispatch.
  Provider B automatic failover.
  Tenant-specific branding portal.

Revisit:
  After peak load test or confirmed SLA requirement.
~~~

Deferring an option is not ignoring it; recording **why it was deferred and its trigger** prevents both premature overengineering and blind spots.

## 21. Managing change and superseding ADRs

A decision that made sense last year may become obsolete after:

- Growth in email or tenant volume.
- Switching providers, regions, or SMTP accounts.
- Adding MIME features, attachments, or inbound mail.
- Revised security/retention mandates.
- An unanticipated production incident.
- Behavior changes in Spring Boot, Spring Mail, or Jakarta Mail dependencies.

### 21.1. Never rewrite history as if the old decision never happened

Avoid:

~~~text
ADR-001 in 2025:
  "Use synchronous send"

In 2026, edit same ADR to:
  "Use outbox"
~~~

Future readers would never know the system once sent synchronously or why it changed. Instead:

~~~text
ADR-001 (SUPERSEDED)
  Use synchronous mail send.
  Superseded by ADR-014.

ADR-014 (ACCEPTED)
  Use transactional outbox for transactional email.
  Supersedes ADR-001.
  Rationale: failures/latency requirements changed.
~~~

You can append a brief supersession note to ADR-001 while keeping its original context and rationale intact.

### 21.2. Decision drift: when code and ADRs diverge

Suppose an ADR states:

> Every UNKNOWN attempt must be held for reconciliation.

But a PR adds:

~~~java
catch (MailSendException ex) {
    retryImmediately();
}
~~~

This is **decision drift**. The current code may violate the ADR's duplicate-prevention policy. Reviewers should:

- Point out the affected ADR.
- Check whether the change is a bug fix or a new architectural decision.
- If the decision changed, update/supersede the ADR with approval.
- If the code is wrong, align the implementation with the approved decision.

An ADR does not need to describe every line of code; it simply needs core invariants, contracts, and failure semantics to remain true.

### 21.3. Linking incidents to re-evaluation

For example:

~~~text
Incident INC-42:
  SMTP relay accepted message
  DB markSent failed
  worker retried and duplicated confirmation
            |
            v
ADR-003 assumption invalidated:
  "send failure always means not accepted"
            |
            v
New ADR-016:
  introduce UNKNOWN + reconciliation
~~~

A postmortem should pinpoint **which assumption proved false or went unrecorded** and which decision must change, rather than blaming a single line of code.

### 21.4. Scheduling re-evaluations

You can add:

~~~text
NextReviewDate: 2027-02-01
ReviewOwner: Messaging Platform
RevisitTrigger:
  - p99 queue age exceeds business SLO
  - SMTP provider increases rejection rate
  - regional data policy changes
  - new provider API offers status reconciliation
~~~

Review dates are internal governance schedules, not Spring requirements. **Metric/condition-based** revisit triggers are usually far more useful than waiting for a calendar date.

## 22. Connecting architecture decisions to a dependency map

A mail decision can impact services and resources outside application code. If you only document Spring components without **data flows and ownership**, migrations easily miss critical boundaries.

### 22.1. Example dependency map

~~~text
Order Service
    |
    | transaction: create order + mail intent
    v
PostgreSQL Outbox
    |
    v
Mail Dispatch Worker
    |
    +--> Template Repository
    |       +--> template version
    |
    +--> Asset Storage
    |       +--> inline images
    |       +--> attachments
    |
    +--> Credential Provider
    |       +--> SMTP secret / API token
    |
    +--> JavaMailSender / Provider Adapter
            |
            v
       SMTP / HTTP provider
            |
            +--> Bounce mailbox
            +--> Feedback webhook
                      |
                      v
               Delivery event store
                      |
                      v
              Central suppression
~~~

An ADR for provider fallback may require updating DNS, credentials, SPF/DKIM, webhook authentication, and suppression—not just changing `spring.mail.host`.

### 22.2. What to include in impact analysis

| Surface | Questions |
| --- | --- |
| Business semantics | Who creates the intent? How many valid emails can one event spawn? |
| Storage | Which tables, unique constraints, retention, backups, and migrations? |
| API | What does HTTP/gateway return when SMTP is unavailable? |
| Background processing | Schedulers/workers, leases, concurrency, retry ownership? |
| Provider | Accounts, quotas, credentials, APIs, feedback? |
| Sender identity | From, Reply-To, envelope sender, DNS authentication? |
| Templates | Versioning, encoding, HTML/text, inline images? |
| Attachments | Immutable bytes, access control, sizes, cleanup? |
| Security/compliance | Regions, logs, data deletion, audits, access? |
| Observability | Dashboards, metrics, alerts, runbooks? |
| Testing | Protocol faults, crash windows, duplicate prevention? |
| Rollout/rollback | Canary scope, feature flags, data compatibility? |

### 22.3. Decision boundaries are also ownership boundaries

For example:

~~~text
Order service:
  responsible for creating correct intent once

Mail worker:
  responsible for scheduling and submitting intent

Provider adapter:
  responsible for transport-specific conversion/outcome

Feedback handler:
  responsible for validating and normalizing provider events

Operations:
  responsible for triage/redrive under policy
~~~

Without knowing who owns `UNKNOWN` when a provider times out, service A may assume service B will retry while B assumes the email was already handled. ADRs should assign **one owner per actionable state**, not merely one owner for the entire codebase.

## 23. Integrating ADRs into pull requests and release workflows

Good architectural changes leave a clear trace from decision to code.

### 23.1. Example PR description

~~~markdown
## What changed
- Added mail_outbox schema and indexes.
- Introduced worker claim and attempt state.
- Replaced synchronous send in order request.

## Architecture decisions
- Implements ADR-001.
- Relies on ADR-003 for UNKNOWN handling.

## Assumptions
- A-01: Existing PostgreSQL can support peak mail workload.
- A-04: Attachment snapshot retained for retry window.

## Evidence
- Test: business rollback does not create outbox intent.
- Test: worker restart resumes durable pending rows.
- Test: SMTP after-DATA timeout is UNKNOWN.

## Rollout
- Feature flag enabled for internal canary.
- Monitor queue age, error rate, duplicate incidents.
- Rollback procedure documented.
~~~

This content is illustrative. In practice, replace `Test` placeholders with real test/evidence links; never mark PASS before running them.

### 23.2. Implementation checklists differ from acceptance evidence

`Checklist`:

- Migration exists for the outbox table.
- Worker reads pending rows.
- Timeouts and structured logs are configured.

`Evidence`:

- Migration applied cleanly in the test environment.
- Worker survived the defined fault-injection tests.
- Queue age stayed below the approved threshold under load testing.

“Code has been written” does not equal “assumptions have been verified.” Track both separately.

### 23.3. Feature flags and shadow mode

When migrating from synchronous sending to an outbox, feature flags enable gradual rollout. Be careful with **shadow mode**:

~~~text
Old path: synchronous SMTP sends
New path: outbox worker also sends
             |
             v
      Duplicate emails!
~~~

Safe shadow mode persists intents and validates data/latency **without submitting to SMTP**, or routes to an isolated test sink. Never let both paths execute real side effects toward live recipients.

### 23.4. Rollback plans must be state-aware

If an outbox rollout already created thousands of `PENDING` intents, disabling workers and re-enabling synchronous sends leaves a stranded backlog. If workers are later re-enabled, the same events could send twice.

A rollback plan must address:

1. How feature flags apply to **new deliveries**.
2. Whether intents already created on the new path finish draining or migrate.
3. How to prevent one business event from taking both paths.
4. Whether schemas can roll back without destroying unprocessed mail intents.
5. Who decides whether to redrive deliveries left in UNKNOWN.

### 23.5. Migrating without losing the audit trail

When replacing provider A with provider B, retain:

- Provider ID for every attempt.
- Provider message IDs/feedback references where available.
- Route policy version and selection rationale.
- Webhook/bounce ingestion from A for already-accepted messages.
- Suppression records enforced across both providers.

A migration ADR must specify retention for legacy streams rather than merely stating “switch config to B.”

## 24. Decisions worth splitting rather than stuffing into one giant ADR

An oversized ADR is hard to supersede piecemeal. Split decisions along **responsibilities and rates of change**.

| ADR | Question to decide | Can evolve independently? |
| --- | --- | --- |
| ADR-001: Outbox | When is send intent persisted durably? | Yes |
| ADR-002: MIME composition | Which API builds HTML/inline/attachments? | Yes |
| ADR-003: Outcome semantics | When is a job ACCEPTED/UNKNOWN/FAILED? | Yes |
| ADR-004: Retry and dead letter | Who schedules retries and redrives? | Yes |
| ADR-005: Template snapshot | What content is frozen and when? | Yes |
| ADR-006: Provider abstraction | Which interface hides SMTP/HTTP APIs? | Yes |
| ADR-007: Fallback policy | When is switching providers safe? | Yes |
| ADR-008: Feedback processing | How are bounces/complaints correlated? | Yes |
| ADR-009: Security/data residency | Which providers/assets are eligible? | Yes |

A tiny app does not need nine separate ADRs. The rule of thumb is: **each ADR should address one central choice** that can evolve without invalidating unrelated decisions.

### 24.1. Dependencies between decisions

For example:

~~~text
ADR-001 (Outbox)
    |
    +--> ADR-003 (Outcome semantics)
    |       |
    |       +--> ADR-004 (Retry policy)
    |       +--> ADR-007 (Fallback policy)
    |
    +--> ADR-005 (Template snapshot)
    |
    +--> ADR-008 (Feedback processing)
~~~

A PR modifying `UNKNOWN` behavior must check both retry and fallback policies. Dependent ADRs do not have to be approved on the same day; record dependencies and temporary constraints explicitly.

### 24.2. Resolving conflicting ADRs

For example:

~~~text
ADR-003: UNKNOWN must not be automatically resent.
ADR-007: Any SMTP error triggers fallback to provider B.
~~~

These two decisions conflict. Amend or supersede one of them, clarifying scope and precedence. Never leave developers guessing which ADR “looks newer” by filename. An index showing status, supersession links, and review owners prevents contradictions.

## 25. Reviewing an ADR with targeted questions

Instead of asking only “any thoughts?”, review ADRs using questions tied to **correctness and operations**.

### 25.1. Goals and scope

- Does the decision solve a real problem or just add abstraction?
- Which email types are in scope, and which are excluded?
- Are concrete business SLOs, retention windows, and deadlines defined?
- Does it state what is **not guaranteed**, such as inbox placement or exactly-once?

### 25.2. Alternatives

- Was at least one simpler alternative evaluated?
- Was reusing existing infrastructure considered?
- Were provider SDKs/HTTP APIs compared fairly against SMTP?
- Does it document conditions under which an unchosen option would win?
- Are migration and rollback costs included?

### 25.3. Assumptions

- Which assumption, if false, would overturn the decision?
- Who owns validating each assumption?
- Is evidence backed by benchmarks/tests/contracts or only guesses?
- What events invalidate past evidence?
- Are clear trigger conditions defined to abandon the choice if key assumptions fail?

### 25.4. Mail-flow correctness

- Are business intents separated from SMTP submissions?
- Can crashes or timeouts produce duplicate emails?
- What happens if SMTP accepts but the DB state commit fails?
- How are suppressed recipients, expired tokens, and missing attachments handled?
- Are HTML/inline rendering quirks across mail clients in scope?
- Is there a way to reconcile bounces, complaints, and delivery feedback?

### 25.5. Security

- Where do secrets originate and how are they rotated?
- Are sender identities verified across every eligible provider?
- Can email contents or attachments leave authorized regions?
- Do logs, DLQs, or the outbox store excessive PII?
- What permissions and audit trails govern manual redrives?

### 25.6. Operations

- Who receives queue-backlog alerts?
- Which metrics prove the decision meets SLOs?
- Do runbooks exist for provider outages and UNKNOWN outcomes?
- Can we roll back without losing email intents?
- When must a new ADR be written instead of quietly patching code?

## 26. Runbook: when an architectural assumption breaks in production

An ADR is not a write-once document. During an incident, it bridges **symptoms**, **original assumptions**, and the **decision needing revision**.

### 26.1. Example: sudden spike in queue age

Symptoms:

~~~text
PENDING mail intents: increasing
Oldest due age: 40 minutes
Worker process: running
SMTP response time: elevated
HTTP order requests: mostly healthy
~~~

Current decision: PostgreSQL outbox + SMTP worker.

Suspected assumption:

> A-01: Worker/DB/SMTP capacity is sufficient for peak traffic within SLO.

Steps:

1. Check mail categories, intent counts, and `next_attempt_at`.
2. Isolate whether the backlog comes from DB contention, too few workers, SMTP throttling, network latency, or template rendering.
3. Inspect `inflight` metrics, provider 4xx/5xx codes, queue age, and worker crashes.
4. Check retry storms/backoff and UNKNOWN attempts held for review.
5. Measure before adding workers; extra concurrency can worsen SMTP quota throttling.
6. If the capacity assumption failed, update evidence and reopen the worker/broker/provider ADR.
7. Before changing designs, document rollout/rollback plans and mail loss/duplicate risks.

Never conclude “PostgreSQL outbox does not scale” simply because the backlog grew while the SMTP provider was rate-limiting submissions.

### 26.2. Example: duplicate emails after restart

Symptoms:

~~~text
Mail D1:
  attempt #1 -> provider accepted?
  worker crashed before state update
  attempt #2 -> SMTP accepted
  recipient reports two copies
~~~

False assumption:

> Any exception or missing state means the provider did not accept the message.

Steps:

1. Gather delivery ID, attempt IDs, SMTP/provider logs, and timestamps.
2. Check whether the outcome was `UNKNOWN` and why a retry was scheduled.
3. Inspect lease expiry/reclaim timing against SMTP timeouts.
4. Separate claim concurrency bugs from side-effect idempotency limitations.
5. Document residual risk: plain SMTP may lack deduplication guarantees.
6. Update the outcome-semantics and fallback/reconciliation ADRs.
7. Add fault-injection tests simulating crashes right after DATA/accepted.

Never rewrite history to claim “we had exactly-once”; database transactions and unique constraints alone cannot guarantee that across SMTP.

### 26.3. Example: migrating to provider B increases bounces

Symptoms:

~~~text
Provider B acceptance: high
Hard bounce / complaint: rising
Delivery feedback: incomplete
~~~

Assumptions under inspection:

- B's sender identity, DKIM, and DMARC are properly configured.
- B's webhooks consistently map back to deliveries.
- Central suppression applies equally across A and B.

Steps:

1. Verify DNS/authentication records and sender identity.
2. Distinguish provider acceptance from recipient-server delivery.
3. Inspect webhook signatures, correlation keys, and event lag.
4. Audit suppression lists, consent rules, and category routing.
5. Reduce canary traffic or roll back **for new deliveries**.
6. Keep B's feedback ingestion active for already-accepted emails.
7. Re-evaluate the provider fallback/migration ADR using the new evidence.

### 26.4. Recording a re-evaluation note

~~~markdown
## Review record — 2026-11-12 (example)

ADR: ADR-001
Trigger: Oldest due queue age exceeded defined SLO
Observed evidence: [dashboard link / test IDs]
Assumption affected: A-01 (capacity)
Finding: [validated / invalidated / still inconclusive]
Decision: [keep / amend scope / open new ADR]
Owner: Messaging team
Follow-up issue: [link]
~~~

Do not edit the original decision text if the choice stays intact. Append a linked review note, and write a new ADR when a substantial part of the decision changes.

## 27. Common mistakes when documenting architecture decisions

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Recording only the final choice | Nobody knows why it was picked | Document context, drivers, alternatives, rationale |
| Omitting assumptions | Breaks silently when load/providers change | Maintain an assumption register + revisit triggers |
| Treating assumptions as facts | Overpromises SMTP latency/delivery | Attach confidence levels and evidence |
| Omitting scope | Marketing policies leak onto OTPs | Scope by email type, tenant/region |
| Skipping simpler alternatives | Overengineering | Compare sync, async, DB outbox, and broker fairly |
| Claiming “outbox guarantees exactly once” | Misjudges duplicate risk | Separate durable intent from SMTP acceptance |
| Equating `SENT` with inbox delivered | Misleading KPIs/delivery reports | Define submission vs. feedback stages |
| Falling back to B on any error from A | Duplicates after unknown outcomes | Fall back only when strict conditions allow |
| Leaving out security constraints | Picks non-compliant provider/region | Filter non-negotiables before scoring |
| Scoring without evidence | Subjective numbers with false precision | Cite evidence and run sensitivity analysis |
| Ignoring negative consequences | Future teams inherit hidden ops debt | Document tradeoffs, costs, and owners |
| Missing acceptance criteria | Decision cannot be verified | Define tests and metrics upfront |
| Writing “tested” with no environment | Results are unreproducible | Record workload, build, provider, and test scope |
| Keeping decisions only in chat/meetings | Rationale gets lost | Version-control ADRs and link PRs |
| Stuffing 10 independent choices into one ADR | Hard to amend/supersede piecemeal | Split along decision boundaries |
| Editing an old ADR into a new choice | Destroys history | Supersede old ADRs with new ones |
| Missing an owner | Nobody re-checks assumptions | Assign clear decision and review owners |
| Not linking incidents | Repeats known failures | Trace incident → assumption → ADR |
| Planning code-only rollbacks | Strands intents/backlog/feedback | Cover data and state in rollback plans |
| Benchmarking only the happy path | Misses crashes, unknowns, duplicates | Run fault-injection acceptance tests |
| Calling `errorChannel` a DLQ | Errors vanish on JVM restart | Specify durable disposition mechanisms |
| Forgetting attachment lifecycles | Retries lose files | Pin immutable references and retention |
| Ignoring template versioning | Retried emails change content | Decide snapshot vs. render-time rules |
| Choosing purely on per-email price | Surprise ops/deliverability costs | Use total cost and risk models |
| Setting review dates without triggers | Misses major shifts between cycles | Trigger reviews on SLO/quota/provider/incidents |
| Letting PRs alter semantics without checking ADRs | Decision drift | Reference relevant ADRs in PR reviews |

### 27.1. Writing ADRs does not mean code must be complex

An ADR may legitimately conclude:

> For the first 6 months, keep one SMTP provider and a simple `JavaMailSender`; omit an adapter registry because no second provider exists yet. Document vendor outage risk, monitor delivery SLOs, and revisit if contracts require failover or observed downtime exceeds thresholds.

That can be a deeply responsible decision when matched to workload and risk appetite. “Do not add abstraction yet” is still a valuable decision worth recording with its reasoning.

### 27.2. Recording “undecided” differs from silence

For example:

~~~text
Decision:
  Use DB outbox for transactional emails.

Not decided yet:
  Whether marketing mail needs separate provider.

Assumption:
  Campaign volume below current account quota.

Trigger:
  First marketing peak load test or confirmed volume forecast.
~~~

This clarifies **decision boundaries** so nobody assumes every email category must share the exact same provider.

## 28. Frequently asked questions

**“Is an ADR a detailed design document?”**  
No. An ADR records **why a choice was made and its consequences**. A design doc covers full APIs, schemas, and sequence diagrams. The two link together; an ADR does not need to copy all code.

**“Does Spring Framework Mail provide a standard ADR format?”**  
No. ADRs are an engineering documentation practice adopted by teams. Spring Mail supplies APIs like `JavaMailSender` and `MimeMessageHelper`, while teams pick a format to capture rationale.

**“Must every feature get an ADR?”**  
No. Prioritize choices that are hard to reverse or impact cross-team boundaries, reliability, security/compliance, or cost. Small bug fixes only need a PR.

**“What is the difference between a decision and an assumption?”**  
A decision is **what the team chose**; an assumption is **what is provisionally taken as true**. Choosing an outbox is a decision; assuming PostgreSQL handles peak traffic is an assumption needing proof.

**“If an assumption is already validated, should we still keep it?”**  
Yes, because evidence is scoped to a code version, environment, workload, and date. When conditions shift, old evidence can expire.

**“Do we have to document unchosen alternatives?”**  
Yes. They clarify trade-offs and stop future members from re-proposing the same option without context. Present them fairly rather than turning unchosen options into strawmen.

**“If an option violates a security constraint, should it enter the scoring matrix?”**  
You may list it as disqualified, but never award high points elsewhere to override a mandatory constraint. Filter eligibility before weighted scoring.

**“Is a scoring matrix mandatory?”**  
No. For clear-cut choices, strong qualitative rationale often beats subjective numbers. If you use a matrix, document sources, weights, confidence, and sensitivity.

**“Should ADRs live in a wiki or a repository?”**  
Both can work. Repos excel at version control and PR reviews; wikis help cross-team visibility. What matters is stable IDs/links, discoverability, owners, statuses, and supersession history.

**“Does an Accepted ADR mean the code is deployed?”**  
Not necessarily. `Accepted` means the choice was approved; implementation and rollout may follow later. Use `Implemented` or link PRs/releases to track rollout.

**“When changing a decision, edit the old ADR or write a new one?”**  
If the core choice changes, create a new ADR and link `supersedes`. If only adding evidence or clarifications while keeping the decision intact, append a review note by convention.

**“Should an ADR list every Spring class used?”**  
Only the APIs and constraints central to the decision. Choosing `JavaMailSender` is a contract boundary; detailed methods and constructors belong in design docs and code.

**“Does `@Async` count as durable retry?”**  
Not by default. With an in-memory executor, queued tasks disappear on process restart. If durability is required, use a proper store, broker, or outbox.

**“Does a transactional outbox guarantee emails are sent exactly once?”**  
No. It preserves sending intent atomically with the business transaction; because SMTP has no distributed transaction with the DB, a crash window still exists after acceptance before state updates.

**“Can `SENT` be treated as inbox delivered?”**  
Avoid doing so when relying solely on `JavaMailSender.send`. Track submitted/accepted separately from provider/recipient feedback; inbox placement and open/read status are distinct concepts.

**“Why not automatically retry SMTP timeouts?”**  
Because timeouts after DATA can occur after the provider accepted the message when the final reply was lost. Immediate retries risk duplicates; ADRs must specify `UNKNOWN` and reconciliation.

**“Is provider fallback a purely technical choice?”**  
No. It involves regions, tenants, sender identities, quotas, compliance, attachment support, and business tolerance for duplicates.

**“Which assumptions should be verified first?”**  
Those combining **high impact if wrong** with low confidence: duplicate semantics, data residency, security, critical SLOs, retry/recovery behavior, and provider quotas.

**“What if an ADR has an assumption that cannot be tested immediately?”**  
Mark it `unvalidated`, stating why, its owner, risk mitigations, and when/what trigger will validate it. Never leave it implicit so an assumption silently turns into a promise.

**“How do submission SLOs differ from inbox delivery SLOs?”**  
Submission measures handoff from the app to the provider; inbox delivery depends on external servers and is not always observable. Anchor SLOs on what your system can actually measure.

**“Should templates be rendered when the worker runs?”**  
Depends on requirements. To preserve exact content at event time, snapshot models/versions or rendered output. To reflect the latest data, render later while safeguarding business correctness.

**“Are MIME snapshots a security concern?”**  
Potentially yes—they can hold PII, tokens, and attachments. ADRs must specify retention, encryption, tenant access controls, and deletion, not just replay convenience.

**“Does sending HTML emails with images require its own ADR?”**  
A single template convention may suffice for small apps. If decisions around asset storage, inline CID vs. HTTPS URLs, replayability, and PII affect the whole platform, write an ADR.

**“Can we skip load testing by trusting the SMTP provider's SLA?”**  
Provider SLAs are useful evidence, but do not test your application's workload, connection pools, credentials, network paths, or retry amplification.

**“If a load test passed once, does the assumption stay valid forever?”**  
No. Evidence is bounded by version and scale. Revisit whenever workloads, providers, or dependencies change.

**“Who should approve data-residency ADRs?”**  
Authorized approvers under organizational policy—typically security/compliance alongside architecture owners. Never treat a casual developer comment as legal sign-off.

**“Should failover share an ADR with the provider adapter?”**  
Possible in small scopes, though adapter contracts and fallback policies often evolve independently. Separate ADRs let you change fallback rules without muddying adapter rationale.

**“Does every incident require a new ADR?”**  
Not always. If an incident simply exposed a bug without altering decisions, update evidence and runbooks. If it disproved a core assumption or forced a policy shift, write or supersede an ADR.

**“Do ADRs replace incident postmortems?”**  
No. Postmortems capture timelines, impacts, and root causes; ADRs capture choices made after weighing context and alternatives. Link the two together.

**“Can Superseded ADRs be deleted?”**  
Avoid deleting them unless retention rules mandate it. Preserving history explains why designs changed and prevents repeating old mistakes.

**“Why assign an owner?”**  
Because assumptions need verification, risks need sign-off, and decision drift needs response. Without owners, ADRs decay into unmaintained logs.

**“Should rollback plans be documented?”**  
Yes for any choice affecting live delivery. Rollback covers more than reverting code—it must handle backlogs, in-flight attempts, schema compatibility, and delayed feedback.

**“How do we keep ADRs from becoming bureaucracy?”**  
Focus each ADR on one core decision, keep it concise with clear context, link evidence and owners, and tie updates to PRs, incidents, and revisit triggers rather than demanding long forms for minor edits.

## 29. Practical checklist for Spring Framework Mail projects

### Before finalizing a decision

1. Identify the **central architectural question** the ADR answers.
2. Specify services, email types, tenants, regions, and environments in scope.
3. Explain why the status quo fails requirements or what opportunity motivates change.
4. Define criteria for reliability, latency, security, observability, and cost.
5. Separate **mandatory constraints** from negotiable trade-offs.
6. Record unverified assumptions, confidence levels, and owners.
7. Include at least one simpler alternative or reuse of existing infrastructure.
8. Document benefits, limitations, and failure modes of each alternative fairly.
9. If scoring, state weights, evidence sources, and decision sensitivity.
10. Never let a security/compliance-violating option win on cost scores alone.

### When designing the mail flow

11. Define when business intents are created and by which transaction.
12. Distinguish synchronous sends, in-memory `@Async`, outboxes, and brokers.
13. Define boundaries across `JavaMailSender`, mail models, and provider adapters.
14. Choose `SimpleMailMessage` or `MimeMessageHelper` based on MIME needs.
15. Define how templates render and pin template versions.
16. Ensure attachments and inline assets remain readable throughout retries.
17. Define SMTP/API submission outcomes and what `ACCEPTED` means.
18. Define `UNKNOWN` handling; never assume timeouts mean non-delivery.
19. Specify retries, backoff, max attempts, dead letters, and manual redrives.
20. Specify business idempotency keys and accepted residual duplicate risk.
21. Specify when fallback is permitted, eligible providers, and region/identity policies.
22. Define feedback/bounce/complaint correlation and suppression rules.
23. Document secret management, TLS, PII retention, and auditing.

### During verification

24. Maintain unit tests for decision logic and mappings.
25. Run integration tests against real PostgreSQL or Testcontainers when relying on row locks.
26. Use fake/test SMTP servers for MIME structure and protocol failures.
27. Inject faults immediately before and after SMTP acceptance.
28. Test crashes and restarts for both producers and workers.
29. Test attachment and template versioning across retries.
30. Test multi-tenant/region restrictions and credential handling.
31. Benchmark representative workloads with semantically accurate metrics.
32. Record environment, versions, dates, and links to evidence.
33. Never mark assumptions `VALIDATED` unless tests actually cover them.

### During rollout and operations

34. Ensure ADRs list owners, statuses, and links to issues and PRs.
35. Plan clear canary rollouts; never double-send live emails in “shadow” mode.
36. Maintain rollback plans covering backlogs, in-flight jobs, and delayed feedback.
37. Build dashboards for queue age, attempts, failures, UNKNOWNs, and bounces/complaints.
38. Configure alerts tied to business SLOs and runbooks per failure class.
39. Establish redrive procedures checking permissions, suppression, expiry, and duplicate risk.
40. Enforce data retention/cleanup without dropping active work items.
41. Track revisit triggers and assumption owners.
42. Update or supersede ADRs whenever code changes semantics.
43. Link incident postmortems to affected assumptions and decisions.
44. Retain older ADRs to preserve historical reasoning for design changes.

## 30. Compact Decision Log template for meetings

You do not always have enough information during a meeting to draft a full ADR immediately. Start with a compact table:

| Field | Example content |
| --- | --- |
| Decision ID | ADR-012 |
| Question | Should we stick with one SMTP relay or add a secondary provider? |
| Why now | Provider A outages are growing the backlog and threatening SLOs |
| Mandatory constraints | Tenant/region, sender identity, suppression |
| Options | A-only retries, A+B blind fallback, A+B guarded fallback |
| Provisional choice | Guarded fallback only after definite pre-submission failures |
| Key assumption | Provider B has enough quota and verified domains |
| Highest risk | UNKNOWN on A could cause duplicates if resent on B |
| Evidence needed | SMTP fault injection, quota verification, DKIM/DMARC tests |
| Owner | Messaging/Platform |
| Status | Proposed pending evidence |
| Follow-up | Draft full ADR, security review, run tests |

After the meeting, the ADR author expands the decision log into a full document with alternatives and rationale. Never mark `Accepted` while mandatory constraint approvals remain pending.

### 30.1. One-page template for smaller decisions

~~~markdown
# ADR-XXX: [Decision title]

**Status:** Proposed
**Scope:** [Which messages/services]
**Owner:** [Role]

## Problem
[What breaks or needs to improve?]

## Constraints
- [...]

## Options
1. [Option A: benefit / downside]
2. [Option B: benefit / downside]

## Assumptions
- A-01: [Claim; confidence; validation owner]

## Decision
[Chosen option and boundaries]

## Why
[Most important rationale and tradeoff]

## Validate
- [Test / SLO / evidence link]

## Revisit when
- [Trigger]
~~~

If a decision carries meaningful risk, add risk/mitigation and rollout/rollback sections. A short template is never an excuse to omit safety controls.

## 31. End-to-end decision lifecycle diagram

~~~text
              New requirement / incident
                         |
                         v
              Define the architecture question
                         |
                         v
                  Describe context
                         |
         +---------------+----------------+
         |               |                |
         v               v                v
     Constraints     Assumptions       Goals/SLO
         |               |                |
         +---------------+----------------+
                         |
                         v
                List viable alternatives
                         |
                         v
            Filter mandatory constraints
                         |
                         v
            Compare risks, tradeoffs, cost
                         |
                         v
            Gather evidence / run experiments
                         |
                   +-----+-----+
                   |           |
                   v           v
                Inconclusive  Sufficient
                   |           |
                   v           v
             Time-box/     Decide + record
             mitigate          |
                               v
                       Review / approval
                               |
                               v
                      Implement via PR
                               |
                               v
                       Deploy with metrics
                               |
                               v
                     Observe actual outcomes
                               |
                     +---------+---------+
                     |                   |
                     v                   v
               Assumptions hold     Assumption invalid /
                     |              trigger breached
                     v                   |
               Keep decision            v
                     |               Re-evaluate
                     |                   |
                     |                   v
                     |               New ADR if
                     |               decision changes
                     |                   |
                     +-------------------+
                               |
                               v
                   Keep immutable decision history
~~~

### 31.1. Three questions every ADR must answer

When reading any ADR for Spring Framework Mail, a maintainer should be able to answer:

1. **Why did we choose this approach over alternatives given our initial context?**
2. **Which assumptions or risks could render this approach invalid?**
3. **What evidence and triggers determine whether to keep, amend, or replace the decision?**

If a document cannot answer those three questions, it is merely a current-state description rather than an actionable **Architecture Decision Record**.

## 32. Conclusion

**Recording decisions, assumptions, and alternatives** makes a Spring Framework Mail architecture explainable, verifiable, and safe to evolve. Production email systems must do far more than merely “send a message”: they must govern transaction boundaries, retry/unknown outcomes, provider limits, MIME/template/attachment lifecycles, data security, feedback loops, and failure-mode operations.

Strong ADRs clearly document the **problem, options, criteria, constraints, assumptions, and evidence**, connecting them directly to tests, dashboards, incidents, and live code. Unchosen alternatives deserve fair treatment, because their trade-offs show future teams when an architecture must change. With Spring Mail in particular, avoid unproven claims such as “SMTP accepted equals inbox delivered,” “an outbox guarantees exactly-once,” or “any exception is safe to fall back on.”

The greatest value of an ADR is not having another document on disk, but **preserving today's reasoning so tomorrow's engineers and operators can re-evaluate choices with evidence instead of guessing or repeating past incidents**.
