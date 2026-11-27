# User-Journey and Service-Objective Dashboards

## 1. Dashboards Must Answer User and Operator Questions

An infrastructure dashboard can show CPU, memory, pod counts, and database connection levels. Those metrics are useful, but they do not directly answer the most important question: **are users able to complete what they came to do?** Low CPU does not prove the booking flow works; all pods can look healthy while the payment API is timing out or bookings are stuck in an intermediate state.

A user-journey dashboard organizes observability data around a business goal, such as searching properties, viewing details, holding a room, paying, and receiving confirmation. It connects:

- User-visible outcomes: completion rate, errors, duration, and drop-off steps.
- Service objectives: SLIs/SLOs, error budgets, and impact severity.
- Technical signals: latency, traffic, errors, saturation, queues, dependencies, and traces.
- Operational actions: owners, runbooks, deployment versions, affected regions, and investigation links.

In the **CLOUD_ARCHITECTURE** module, dashboard design is part of observability architecture. It ties compute, networking, databases, APIs, events, and external providers to real user experience, supporting reliability, performance, security, scalability, cost, and operations under Well-Architected principles.

Running example: a booking platform has a journey from search to booking confirmation. Search may return results quickly while those results are unavailable; Booking API may create a booking while the payment provider fails to respond; payment may succeed while notifications go unsent. Only a dashboard spanning the entire journey makes the end-to-end experience visible.

## 2. From Capabilities to User Journeys

A journey describes the sequence of steps a user or partner system takes to reach a goal. Each step may traverse multiple frontends, APIs, services, databases, and external providers.

Example booking journey:

~~~mermaid
flowchart LR
    A["Search property"] --> B["View details"]
    B --> C["Check availability"]
    C --> D["Create booking hold"]
    D --> E["Authorize payment"]
    E --> F["Confirm booking"]
    F --> G["Send confirmation"]
~~~

Not every user follows a single straight path. They may change dates, return to search, try a different payment method, or cancel. Dashboards must distinguish valid branches, retry behavior, technical errors, and voluntary user drop-offs.

### 2.1. Defining Journey Boundaries

For each journey, define:

1. **Actor:** end user, staff, partner, or automated workload?
2. **Trigger:** what user action starts it; what event marks the start?
3. **Success outcome:** what condition proves the goal actually completed?
4. **Steps:** what are the key steps and intermediate states?
5. **Failure outcome:** how are errors, timeouts, business rejections, abandonment, and unknown states distinguished?
6. **Time boundary:** from when to when is it measured; does it include user think time or external waits?
7. **Owner:** which team owns each step and the overall outcome?

For instance, creating a booking record does not guarantee success if payment is unconfirmed and the booking is not committed. Success definitions must reflect the final business state promised to users.

### 2.2. Journey Maps and Service Maps Are Not the Same

A journey map describes the experience in business steps. A service map describes technical components, communications, and dependencies. Connect both maps to move from user symptoms to likely causes.

| Journey Step | Potentially Involved Technical Components | Signals to Observe |
| --- | --- | --- |
| Search | Web/mobile, CDN, Search API, search cluster | Search success, latency, zero-result rate, timeouts |
| View details | Property API, cache, object storage/CDN | Detail load time, cache hits, media failures |
| Availability | Inventory API, database, cache | Availability check success, stale data, DB latency |
| Booking hold | Booking API, DB, locks/queues | Hold success, conflicts, transaction latency |
| Payment | Payment API/provider, event handlers | Authorization success, timeouts, unknown states, reconciliation backlog |
| Confirm | Booking DB, outbox/event broker | Confirmed booking rate, event lag, duplicates/retries |
| Notification | Notification worker, email/SMS provider | Delivery enqueues, delivery latency, provider errors |

## 3. Distinguishing SLIs, SLOs, SLAs, and KPIs

Dashboards add value when they distinguish service measurement targets from business targets and contractual commitments.

| Concept | Meaning | Example |
| --- | --- | --- |
| SLI (Service Level Indicator) | Metric measuring an aspect of service quality | Proportion of search requests succeeding under 800 ms |
| SLO (Service Level Objective) | Internal target for an SLI over a time window | 99.9% of valid search requests meet latency/error thresholds over 30 days |
| SLA (Service Level Agreement) | Service commitment to customers/partners, potentially with clauses and remedies | Contractually committed availability |
| KPI (Key Performance Indicator) | Business performance indicator | Search-to-booking conversion rate |

KPIs do not replace SLIs. Falling conversion rate could stem from seasonality, pricing, marketing, or product factors; the search latency SLI helps evaluate one possible technical cause. Conversely, strong technical SLIs do not prove good UX or conversion.

### 3.1. Designing Outcome-Driven SLIs

A good SLI has an unambiguous measurement definition:

- **Which events enter the denominator?** For example, valid search requests, excluding health checks and identified bot traffic.
- **Which events count as good?** A successful HTTP response is insufficient if the payload is wrong or the user cannot proceed.
- **Where is it measured?** Browser, API gateway, service, or database; each vantage point reflects a different perspective.
- **What filters apply?** Region, platform, API version, tenant tier, or journey.
- **Measurement window:** minutes, hours, days, rolling 7/30 days?
- **Source of truth:** which metric, event log, trace, or analytics pipeline?

Example API-level availability SLI:

~~~text
availability SLI = good eligible requests / all eligible requests
~~~

Example latency SLI:

~~~text
latency SLI = eligible requests completed within threshold / all eligible requests
~~~

Ratios can be calculated per request, user session, or journey attempt. Do not mix different units in the same denominator.

### 3.2. SLOs Need Thresholds and Windows

Illustrative example for search:

- Availability SLO: 99.9% of valid requests over a rolling 30-day window return a usable response.
- Latency SLO: 99% of valid requests complete within 800 ms over a rolling 30-day window.
- Error budget corresponds to the allowable miss portion within the window.

These thresholds are examples only, not universal standards. Choose targets based on user requirements, business impact, technical capability, and cost to maintain.

## 4. Measuring Journeys with Funnels and Step-Level SLIs

Funnels reveal where users drop out of a journey. Yet not every drop-off is an error. A user may search and decide not to book; that is natural abandonment. Dashboards must separate expected abandonment from technical failures.

Example:

| Step | Attempts | Success | Error/Timeout | Abandon/Other | Success Rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Search | 100,000 | 98,500 | 1,500 | 0 | 98.5% |
| View details | 70,000 | 68,600 | 700 | 700 | 98.0% |
| Availability | 42,000 | 40,740 | 840 | 420 | 97.0% |
| Booking hold | 12,000 | 11,640 | 240 | 120 | 97.0% |
| Payment | 11,640 | 11,058 | 466 | 116 | 95.0% |
| Confirmation | 11,058 | 10,947 | 55 | 56 | 99.0% |

Hypothetical figures. The abandon/other column must be explicitly defined; do not classify all non-successful requests as either abandonment or system errors. If each step has retries, dashboards must distinguish attempts from unique journeys.

### 4.1. End-to-End Completion Rate

A straightforward ratio:

~~~text
journey completion rate = completed journeys / eligible started journeys
~~~

This does not always equal the product of per-step success rates. Users may skip steps, retry, go back, or take alternative branches. Calculating by cohort journey ID and explicit terminal states yields a more accurate reflection of outcomes.

### 4.2. Step Latency vs. End-to-End Latency

Measure duration for each step to locate bottlenecks, while also measuring total duration from trigger to outcome. Total journey latency may include user think time or external confirmation waits; distinguish:

- **System processing time:** backend/frontend execution time.
- **Dependency wait time:** waiting on databases, queues, or providers.
- **User think time:** intervals where the user interacts outside system processing.
- **End-to-end elapsed time:** total span from journey start to completion.

Do not use end-to-end elapsed time as an API latency SLI if it includes idle user time.

## 5. Supporting Technical Signals: RED and USE

Journey dashboards tell you what is breaking from the user's perspective; RED/USE methodologies help locate the underlying source.

### 5.1. RED for Services / Requests

| Signal | Question | Example Metrics |
| --- | --- | --- |
| Rate | How many requests is the service handling? | requests/sec, requests per route |
| Errors | How many requests are failing? | error ratio, timeouts, status codes |
| Duration | How long do requests take? | latency histogram, p50/p95/p99 |

### 5.2. USE for Resources

| Signal | Question | Example Metrics |
| --- | --- | --- |
| Utilization | How much of the resource is used? | CPU, memory, disk, network utilization |
| Saturation | Is work queuing or waiting on unmet demand? | CPU throttling, queue depth, connection wait |
| Errors | What errors is the resource producing? | disk errors, network drops, throttling |

RED fits observing services; USE fits observing resources. Do not look only at CPU utilization: queue depth and connection wait can expose saturation long before CPU hits 100%.

## 6. Distributed Tracing and Cross-Journey Correlation

To investigate a slow or failing journey, spans across multiple services must be linked. Distributed tracing records parent/child relationships between operations, timings, statuses, and controlled attributes.

~~~mermaid
flowchart LR
    B["Browser span"] --> G["API Gateway span"]
    G --> S["Search API span"]
    S --> C["Cache span"]
    S --> DB["Search DB/cluster span"]
    G --> BK["Booking API span"]
    BK --> SQL["Booking DB span"]
    BK --> P["Payment provider span"]
    BK --> Q["Outbox / broker span"]
    Q --> N["Notification worker span"]
~~~

Trace IDs connect spans; journey IDs/business correlation IDs group multiple requests and events belonging to the same journey. Define clear semantics: trace IDs typically follow one trace/transaction context; journey IDs can persist across multiple traces, retries, or extended operations.

### 6.1. Context Propagation

When one service calls another or publishes a message, trace context must be propagated via chosen standards, typically W3C Trace Context or a compatible mechanism. Consumers create spans linked to the message context; for batched messages or multiple parents, span links may be needed instead of forcing a simple parent/child tree.

Context must never contain access tokens, passwords, or personal data. Baggage must be size-limited and carry only useful, vetted attributes.

### 6.2. Minimum Instrumentation

Each important span should include:

- Service name and standardized operation/route.
- Environment, region, deployment version.
- Status/error classification.
- Duration and dependency name.
- Resource/workload identity at a safe level.
- Journey step/business operation if meaningful.
- Sampling decision and trace links when needed.

Never put raw URLs containing emails, booking tokens, or sensitive query strings into spans. Normalize routes into templates like /bookings/{bookingId} instead of storing every ID as a separate operation name.

## 7. Correlating Metrics, Logs, and Traces

The three telemetry types answer different questions:

| Telemetry | Answers | Use in Dashboards |
| --- | --- | --- |
| Metrics | What is rising/falling and at what scope? | SLOs, latency, error rates, queues, saturation, and trends |
| Logs | With what details did a specific event happen? | Error categories, business state transitions, audits, and diagnostic context |
| Traces | Which components did a request/journey traverse and where was time spent? | Critical paths, dependency latency, retries, and call graphs |

Dashboards should start with aggregated metrics, then provide drill-down links to traces and logs sharing the same trace ID/correlation ID. Avoid embedding thousands of log lines or full traces in an overview panel.

### 7.1. Business State Events

For multi-step or asynchronous journeys, emit explicit events such as:

- SearchStarted / SearchCompleted.
- AvailabilityChecked.
- BookingHoldCreated / BookingHoldExpired.
- PaymentAuthorized / PaymentFailed / PaymentUnknown.
- BookingConfirmed / BookingCancelled.
- NotificationQueued / NotificationDelivered.

Events require schemas, timestamps, sources, versions, and correlation context. Observational events must not alter business transaction semantics; if emitting events directly from applications, prevent gaps between commit and publish, such as via a transactional outbox.

## 8. Designing Dashboards by Question and Role

A single giant dashboard holding every metric is hard to read and hard to use during incidents. Organize dashboards by audience and investigation flow:

| Dashboard | Primary Audience | Questions |
| --- | --- | --- |
| Executive/service health | Business owners, service owners | Are users completing journeys? How are SLOs and trends? |
| Journey overview | Product, SRE, support | Which step has rising errors, latency, or abandonment? |
| Service drill-down | Service teams | Which service causes errors/latency? Which version? |
| Dependency/infrastructure | Platform/SRE | Which database, cache, queue, network, or provider is saturated? |
| Tenant/region view | Authorized operations, customer success | Which tenant segment/region is impacted? |
| Security/audit view | Security/compliance | Are there anomalous accesses or data exposures? |

### 8.1. Journey Overview Layout

A helpful layout might include:

1. **Top row:** journey completion, availability SLI, latency SLI, remaining error budget.
2. **Journey funnel:** attempts/success/failure/abandonment per step.
3. **Step latency:** p50/p95/p99 and timeout rates.
4. **Impact breakdown:** region, platform, API version, and permitted tenant segments.
5. **Dependency health:** services, databases, caches, queues, and external providers.
6. **Recent changes:** deployments, config/policy changes, and incident annotations.
7. **Drill-down:** traces, logs, runbooks, and owners.

Dashboards should show last-updated timestamps, timezones, default filters, and metric definitions. Panels lacking clear data windows or units can lead operators to wrong decisions.

## 9. Error Budgets and SLO-Aligned Alerting

An error budget is the allowable error margin corresponding to an SLO over its evaluation window. For a 99.9% availability SLO, the proportional budget is 0.1% of eligible events in that window. As traffic grows, the absolute number of allowed errors scales with the denominator; when traffic is low, a handful of errors can yield a large ratio.

### 9.1. Burn Rate

Burn rate expresses how fast the error budget is being consumed relative to the pace that would exhaust it evenly over the SLO window.

~~~text
burn rate = observed error rate / allowed error rate
~~~

For example, with an allowed error rate of 0.1% and an observed error rate of 1%, the burn rate is 10. If sustained, the budget will exhaust ten times faster than planned.

### 9.2. Multi-Window Alerting

Instead of alerting on every brief spike, combine short and long windows to detect meaningful fast burn:

- Short window: detects active incidents needing immediate response.
- Long window: confirms sustained impact, avoiding alerts on very brief spikes.
- SLO-based alerts: prioritize symptoms directly consuming the error budget.
- Saturation alerts: catch early risks before SLOs are breached.

Exact thresholds must be tuned to the SLO window, sensitivity, and on-call capacity. Never copy thresholds from another service without understanding the current service's traffic and error budget.

### 9.3. Distinguishing Alerts from Dashboard Signals

Dashboards can display many diagnostic signals; alerts should only trigger when action is required. Alerts need severity, owner, runbook, clear conditions, and impact info. Avoid alerting on every high/low metric without a corresponding action.

## 10. Segmenting Data Without Cardinality Explosions

Breaking down by region, platform, version, or tenant tier helps pinpoint blast radius. However, labels with millions of unique values can cause time series counts to explode.

Principles:

- Use low-cardinality labels with normalized values.
- Never put user ID, booking ID, session ID, email, or full URLs into metric labels.
- Keep unique IDs inside controlled traces/logs/events, not default metric labels.
- Tenant-specific dashboards can query controlled analytics/log stores instead of creating per-tenant metric series.
- Limit filter dimensions and heavy query panels.
- Monitor series counts, ingestion volume, query costs, and retention.

If top-tenant analysis is needed, use bounded aggregations or periodic reports; do not emit every tenant as a label on every metric by default.

## 11. Protecting Privacy and Dashboard Access Control

Observability data can hold customer information: URLs, queries, IP addresses, error payloads, emails, booking IDs, or trace attributes. Dashboards must follow data classification and access control just like any other data system.

- Mask/redact personal info and secrets at instrumentation/collector time whenever possible.
- Never put payment data, access tokens, session cookies, or full payloads into logs/traces.
- Separate internal engineering dashboards from customer support dashboards.
- Tenants may only view their own tenant's data if the product offers a customer observability portal.
- Support staff only access data required for assigned cases, with auditing.
- Restrict retention and export/download permissions.
- Protect telemetry backends with identity and network policies.

Never assume a dashboard is "internal" and therefore safe for any data. Mis-shared screenshots or dashboard links create secondary data leaks.

## 12. Multi-Region and Multi-Tenant Dashboards

Global journeys require both aggregate views and per-region/edge breakdowns, because one region can fail while global totals look green. Similarly, a large tenant can suffer issues even when system-wide average latency looks healthy.

Provide:

- System-wide overview alongside region-comparison panels.
- Availability/latency by region and platform.
- Tenant tiers/segments at manageable cardinality.
- Correlation between deployments/versions and SLO regressions.
- Distinction between internal service errors and external provider errors.
- Traffic volume alongside error ratios so low denominators do not mislead.

Never average per-region p95 values to produce a global p95. Percentiles cannot be validly aggregated that way; compute from histograms/buckets or supported raw distributions.

## 13. Dashboards and Observability Pipeline Architecture

~~~mermaid
flowchart LR
    FE["Browser / Mobile telemetry"]
    API["Services / Workers"]
    INF["Infra / Cloud metrics"]
    COL["Collectors / OpenTelemetry"]
    M["Metrics backend"]
    L["Log backend"]
    T["Trace backend"]
    EVT["Business event store"]
    DASH["Journey dashboards"]
    ALERT["Alerting / SLO engine"]
    FE --> COL
    API --> COL
    INF --> M
    COL --> M
    COL --> L
    COL --> T
    API --> EVT
    M --> DASH
    L --> DASH
    T --> DASH
    EVT --> DASH
    M --> ALERT
~~~

Pipelines must address sampling, buffering, backpressure, network cost, regional routing, retention, and access controls. During major incidents, telemetry must not overload the very workloads being observed. Prioritize metric/SLO signals and error logs, reduce sampling for normal traces while retaining error traces or using tail-based sampling where supported.

### 13.1. OpenTelemetry and Semantic Conventions

OpenTelemetry provides APIs/SDKs and protocols to instrument, collect, and export metrics, logs, and traces. Consistent semantic conventions and resource attributes let dashboards link services, deployments, cloud regions, and operations without custom per-team mappings.

Organizations should standardize service.name, deployment.environment, cloud.region, service.version, and appropriate attributes. Prevent each team from inventing different metric/label names; inconsistent naming makes dashboards hard to aggregate and alerts error-prone.

## 14. Investigating from Symptom to Root Cause

An investigation flow can look like:

1. Confirm which journey completion or SLO degraded and since when.
2. Identify which step shows rising errors/latency and which region/platform/tenant segment is impacted.
3. Check traffic volume, deploy/change annotations, and dependency incidents.
4. Open sample traces to pinpoint slow/failing spans on the critical path.
5. Cross-reference logs by correlation ID to understand error classification and business state.
6. Inspect RED/USE for related services/resources: saturation, queues, DBs, caches, networks.
7. Verify final state in databases/events to see whether transactions completed, failed, or remain unknown.
8. Apply mitigations per runbook and monitor SLO recovery.
9. Post-incident, document root cause, time to detect, time to mitigate, and needed changes.

Do not infer root cause from correlation alone. For instance, CPU rising alongside errors could be either the cause or a consequence of a retry storm; traces and dependency signals must confirm it.

## 15. Dashboard Quality and Anti-Patterns

| Anti-Pattern | Why It Hurts | Improvement |
| --- | --- | --- |
| CPU/memory-only dashboards | Does not show whether journeys succeed | Add user-level outcomes and SLIs |
| Looking only at average latency | Hides tail latency | Display histograms/p50/p95/p99 properly |
| Mixing user abandonment into server errors | Distorts SLIs and misleads priorities | Classify terminal outcomes and eligibility |
| Metric labels with unique IDs | Cardinality/cost explodes | Put IDs in controlled traces/logs |
| One dashboard for every audience | Information overload, hard to act | Split overviews and role-based drill-downs |
| Alerting on every panel | Alert fatigue | Alert on SLOs, impact, and concrete actions |
| Missing deploy/version visibility | Hard to tie regressions to changes | Add annotations and version filters |
| Missing owners/runbooks | Issues detected without clear remediation | Attach service owners, severities, and runbooks |
| Averaging percentiles across regions | Statistically invalid results | Aggregate histograms/distributions properly |
| Dashboards lacking timezone/freshness | Misreading data windows | Show time range, timezone, and last update |

## 16. Hands-On Exercise: Designing a Journey Dashboard for a Booking Platform

**Hypothetical context:** a platform includes web/mobile, API gateway, Search Service, Booking Service, Payment integration, PostgreSQL, Redis, an event broker, and a Notification Worker. Users report falling booking completion rates, yet current dashboards only show CPU and gateway HTTP 5xx.

### Tasks

1. Map the journey from search to booking confirmation and list branches for success, business rejection, user abandonment, timeouts, retries, and unknown states.
2. Choose at least three outcome/end-to-end SLIs and three step-level technical SLIs; define denominators, good criteria, windows, and data sources.
3. Propose availability/latency SLOs per capability, explaining business impact and error budgets.
4. Design an event/correlation schema connecting browser, API, worker, payment provider, and database state.
5. Build an overview dashboard with funnel, completion rate, step latency, region/platform, and dependency health.
6. Build a service drill-down using RED/USE and traces to locate the critical path.
7. Design multi-window burn-rate alerts, severities, owners, and runbooks.
8. Identify high-cardinality/sensitive labels; establish redaction and access control rules.
9. Simulate three scenarios: rising Search latency, payment provider timeout, and notification backlog; describe what the dashboard will reveal.
10. Write an ADR covering the telemetry pipeline, sampling, retention, cost, and SLO ownership.

### Sample SLI Catalog

| Journey/Capability | SLI | Good Event | Eligible Event | Dimensions |
| --- | --- | --- | --- | --- |
| Search | Search availability | Valid results returned within timeout | Valid search requests | Region, app version |
| Search | Search latency | Completed under threshold | Valid search requests | Query class, region |
| Booking | Hold success | Hold created validly | Eligible hold attempts | Region, booking path |
| Payment | Authorization outcome | Confirmed by provider per semantics | Payment attempts, unknown tracked separately | Provider, method, region |
| Journey | Booking completion | Booking in confirmed terminal state | Valid journey attempts | Platform, region |
| Notification | Delivery latency | Notification accepted by provider within threshold | Notification events | Channel, provider |

### Completion Criteria

- Journeys have clear triggers, steps, terminal outcomes, and owners.
- SLIs/SLOs reflect real outcomes with explicit numerators/denominators and windows.
- Dashboards separate business rejections, user abandonment, and technical failures.
- Traces/logs/events correlate without exposing secrets/PII.
- Drill-down paths connect SLOs to steps, services, dependencies, and traces.
- Alerts use burn rates and include owners/runbooks.
- Region/tenant breakdowns are safe, controlling cardinality and cost.
- Dashboards support incident investigation rather than only showing infrastructure status.

## 17. Well-Architected Checklist Before Releasing a Journey Dashboard

- [ ] Journeys are tied to user goals and business owners.
- [ ] Triggers, steps, terminal states, retries, and abandonment are defined.
- [ ] Service maps/dependency maps link to the journey map.
- [ ] Each SLI has clear good events, eligible events, data sources, and windows.
- [ ] SLOs derive from business impact and have error budgets.
- [ ] Funnels distinguish success, business rejections, user abandonment, technical failures, and unknown states.
- [ ] End-to-end latency and step latency exist; user think time is not mixed into system processing time.
- [ ] RED/USE supports drill-down into service and resource saturation.
- [ ] Distributed tracing/context propagation connects services and asynchronous events.
- [ ] Metrics, logs, traces, and business events have proper correlation and retention.
- [ ] Alerts have severities, owners, runbooks, actions, and burn-rate semantics.
- [ ] Dashboards show time range, timezone, freshness, definitions, and deployment annotations.
- [ ] Region/tenant dimensions have controlled cardinality; unique IDs are not used as metric labels.
- [ ] PII, tokens, secrets, and sensitive payloads are stripped/masked.
- [ ] Dashboards/queries/exports are access-controlled and audited.
- [ ] Sampling, backpressure, pipeline HA, retention, and telemetry cost are evaluated.
- [ ] Incident drills verify dashboards support root-cause discovery and mitigation decisions.
- [ ] An ADR defines owners, SLO review cadence, and dashboard lifecycle.

**Key takeaway:** user-journey dashboards start with outcomes, translate outcomes into well-defined SLIs/SLOs, and connect them to step, service, dependency, and resource telemetry. When funnels, metrics, logs, traces, alerts, and runbooks are linked, teams recognize true user impact, pinpoint real bottlenecks, and prioritize recovery around user experience rather than server status alone.
