# Assessing Platform Capabilities Before Adopting a Strategy

## Learning Objectives

After this lesson, learners can:

- Explain why actual platform capabilities must be evaluated before selecting a deployment strategy.
- Distinguish between platform-native capabilities, capabilities requiring extra integration, and capabilities the application itself must support.
- Identify requirements for version orchestration, traffic routing, health checks, capacity, data, observability, and recovery.
- Assess the suitability of rolling update, recreate, blue-green, canary, and shadow traffic.
- Build a capability matrix with evidence, constraints, and owners.
- Validate strategies in a safe environment before introducing them to production.
- Choose a deployment strategy aligned with application architecture, operational constraints, and platform capabilities.

## 1. Do not pick a deployment strategy just because a platform advertises support

Rolling update, blue-green, and canary are often cited as ways to lower release risk. However, a strategy only works well when both the platform and application satisfy the required prerequisites.

For example:

- Blue-green requires running two versions in parallel and switching traffic between them.
- Canary requires controlling the traffic share or cohort routed to the new version while measuring results.
- Rolling update requires the ability to run old and new versions concurrently over a transition window.
- Shadow traffic requires mirroring requests or events to the new version without causing unintended business side effects.

A platform may offer percentage-based rollouts, yet the load balancer in front of it might not support weighted routing. A cluster may be able to run two deployments concurrently, yet lack quota to sustain both versions. A platform may support readiness probes, yet the application might report ready before connecting to the database or loading config. A platform may have a rollback button, yet a database migration might have dropped old data, making reverting unsafe.

Therefore, before adopting a strategy, answer two questions:

1. **What operations can the platform genuinely execute?** For example: spinning up parallel versions, shifting traffic, halting rollouts, retaining old revisions, and recovering.
2. **Can the application behave correctly across intermediate states?** For example: two versions reading/writing the same database, processing messages, or sharing sessions.

Never equate a tool having a feature with the overall system being ready to use that feature. Real capability emerges from the platform, network infrastructure, configuration, permissions, dependent services, and application design.

## 2. Evaluate across the entire request path

A deployment strategy changes how a new version receives traffic. Trace the request path from user to application accordingly.

~~~mermaid
flowchart LR
    U["Client"] --> E["DNS / Edge"]
    E --> L["Load balancer / Ingress"]
    L --> S["Service discovery / Routing"]
    S --> P["Application instances"]
    P --> D["Database / Cache / Queue"]
    P --> O["Logs / Metrics / Traces"]
    O --> G["Rollout decision"]
    G --> L
~~~

At each layer, determine:

- Which component decides whether a request goes to the old or new version?
- Can traffic weights be adjusted or user cohorts selected?
- What is the propagation/convergence time when routing changes?
- Are sticky sessions or long-lived connections present?
- When an instance becomes unready, is traffic drained/removed from that instance?
- Does telemetry show which version handled the request and what happened?
- Can the rollout be halted and traffic returned to the previous version?

For example, updating a DNS record may not switch traffic immediately because resolvers and clients cache entries. If you need small-percentage canarying and rapid reactions, DNS alone will likely fall short. A load balancer or service mesh with weighted routing may fit better, yet configuration, connections, and control permissions still require verification.

Evaluate the true request path, including CDNs, API gateways, ingress controllers, service meshes, internal load balancers, and long-lived client connections. A capability at the application layer does not automatically control every upstream layer.

## 3. Capability domains to verify

A capability assessment can be organized into eight domains.

| Capability domain | Key questions | Evidence to gather |
|---|---|---|
| Version orchestration | Can multiple revisions run, update, and be retained? | Deployment controller, rollout API, revision history |
| Traffic routing | Can traffic shift by percentage or rule? | Load balancer, ingress, gateway, service mesh config |
| Health and readiness | Are unready or failing instances detected? | Probes, health endpoints, rollout gates |
| Capacity and scheduling | Are resources sufficient to run the new version concurrently? | Quotas, node capacity, autoscaling limits |
| State and data | Can old and new versions coexist safely? | Compatibility tests, migration plans, session design |
| Observability | Can errors from the new version be isolated? | Metrics, logs, traces, dashboards, alerts |
| Identity and policy | Who can roll out, switch traffic, and roll back? | IAM, service accounts, approval policies, audit logs |
| Recovery | Can we halt, revert traffic, and recover data? | Rollback tests, backup/restore evidence, runbooks |

Do not merely mark Yes/No. A capability may exist at different levels of support:

- **Native:** built into the platform and already enabled.
- **Integrated:** achievable by integrating a gateway, service mesh, controller, or external tool.
- **Application-dependent:** requires application changes or additional business logic.
- **Unavailable:** absent or unachievable under the current architecture.

Also document concrete evidence. Vendor documentation proves a feature exists in theory, whereas testing inside your actual cluster, network, and quota proves it works in your organization's environment.

## 4. Version orchestration capabilities

The platform needs a way to manage revisions and instance states.

Questions to verify:

- Can a new version be deployed while retaining the old version?
- Can minimum and maximum instance counts be bounded during rollout?
- Can the number of concurrently unavailable instances be capped?
- Can a rollout be paused, resumed, or aborted?
- Are revision history and rollout state preserved?
- Is pinning artifacts by digest supported instead of mutable tags?
- Can deployments target specific instance groups, zones, or regions?
- When a new instance fails to start, how does the controller react?

Rolling update needs a scheduler or deployment controller that knows how to replace instances in waves. Blue-green needs the ability to keep two version groups alive simultaneously. Canary needs a way to define the subset of instances or traffic slice receiving the new version.

A platform that only supports replacing all processes after stopping old ones fits recreate, but cannot natively execute rolling or blue-green without additional orchestration.

Check platform limits as well. For example, a service might allow two deployments, yet policies or quotas might cap load balancers, IP addresses, volumes, or replicas.

## 5. Routing and traffic-shifting capabilities

Traffic routing is a critical prerequisite for blue-green, canary, and shadow traffic.

### 5.1. Required capabilities

- Switch all traffic to another backend.
- Split traffic by weight, e.g., 1%, 5%, 10%, and increment gradually.
- Select traffic by header, cookie, tenant, user cohort, or region when needed.
- Preserve or break sticky sessions according to strategy.
- Drain active connections before shutting down the old version.
- Revert routing back to the previous backend.
- Record which routing revision is currently active.

Not every strategy needs all of these capabilities. Simple percentage canarying splits by weight; user-cohort canarying requires stable identifiers or request attributes.

### 5.2. Weighted routing is more than configuring a number

When configuring 5% traffic to the new version, verify:

- The weight is enforced at the intended routing layer.
- All regions and ingress paths are included.
- Connection reuse does not skew actual traffic distribution.
- Internal service-to-service traffic obeys routing rules.
- Client retries do not amplify traffic hitting the new version.
- Actual request counts per version are observable.

If you inspect only declarative config without measuring live traffic, you may assume a canary gets 5% while a large share of traffic follows another path.

### 5.3. Long-lived connections and sessions

WebSockets, gRPC streams, long-lived TCP connections, or sticky sessions can slow traffic migration. After routing changes, existing connections may stay pinned to the old version until closed.

Define drain durations, timeouts, reconnect handling, and cross-version session compatibility. If the new version cannot read sessions created by the old version, rollouts can trigger failures even when routing works properly.

## 6. Health checks and readiness criteria

The platform must know when a new instance can receive traffic and when a rollout should halt.

Distinguish check types:

- **Startup check:** has the application finished initializing? Useful for slow startups.
- **Readiness check:** is the instance ready to accept traffic?
- **Liveness check:** is the process still alive or stuck needing a restart?
- **Smoke test:** do core functional workflows succeed post-deploy?
- **Rollout analysis:** are error rates, latency, and operational metrics within allowed thresholds?

Readiness typically determines whether an instance joins traffic-serving endpoints. Liveness detects hung or unrecoverable processes. Overly aggressive liveness causes restart loops; overly simplistic readiness admits traffic before critical dependencies are ready.

A health endpoint returning HTTP 200 does not prove all functionality works. Pick checks suited to their purpose, avoiding heavy load on health checks or strict coupling to non-essential services.

Before picking a strategy, verify:

- Does the platform support probes or health gates?
- Can the rollout stop when readiness or smoke tests fail?
- Can metrics be evaluated over a sufficiently long window?
- Are error thresholds separated by version?
- Can rollouts auto-pause or abort when thresholds are breached?

## 7. Capacity and parallel execution capability

Some strategies require temporary extra resources. If the platform lacks capacity, rollouts can stall pending or starve the currently serving version.

### 7.1. Blue-green

Blue-green usually requires keeping both old and new groups running before switching traffic. During transition, deployed application resources nearly double, excluding supporting components.

Verify:

- Are CPU, memory, and quotas sufficient for both groups?
- Can the database handle connections from both versions?
- Are enough IPs, load balancers, volumes, and supporting resources available?
- Can the autoscaler provision capacity within the rollout timeframe?
- Can the old group stay alive long enough for rollback?

### 7.2. Rolling update

Rolling typically needs capacity to create new instances before or while old instances terminate. Parameters like max surge and max unavailable directly govern rollout behavior.

If max surge is 0 and the platform must wait for old resources to free up, rollouts slow down or temporarily reduce capacity. If max unavailable is too high, the system risks running short on serving instances.

### 7.3. Canary

Canary typically requires capacity for a small slice of the new version plus observability and orchestration overhead. When deployed as a separate instance group, determine minimum sizing to gather enough measurement samples. A canary receiving very few requests may not yield enough data to catch rare failures.

### 7.4. Check real resource availability

Do not inspect aggregate quota alone. Check capacity by zone, node pool, region, storage class, and per-workload limits. A cluster with spare aggregate CPU can still fail to schedule new pods if matching nodes are full.

## 8. Data compatibility and application state

The platform may run two versions in parallel, yet the application must tolerate that state.

State surfaces to examine:

- Database schemas and data.
- Login sessions.
- Cache keys and cache structures.
- Queue message formats.
- Event schemas.
- File or object storage.
- Distributed locks and scheduled jobs.
- Feature flags and dynamic configuration.

For example, the old version writes `status` as `PENDING`, while the new version changes it to `WAITING_FOR_PAYMENT`. If both run together, each version may misinterpret the other's data.

A safer pattern typically uses expand-and-contract:

1. Expand the schema compatibly with the old version.
2. Deploy the new version capable of reading/writing compatible structures.
3. Gradually migrate traffic or data.
4. Remove old structures only after no instance depends on them.

For message queues, check whether old consumers can parse new messages and new consumers can parse old messages. Version schemas and maintain transition compatibility as needed.

For sessions, consider shared session stores, stateless tokens, or compatible transition schemes. If each version holds sessions in local memory, shifting traffic between versions can log users out or lose state.

## 9. Observability is a prerequisite for rollout decisions

Controlled canary and rolling updates cannot rely merely on new instances starting successfully. You must know whether the new version performs better or worse than the old one.

Useful signals:

- Request success and error rates per version.
- p50, p95, p99 latency per version.
- Timeout and retry rates.
- CPU, memory, and restart counts.
- Queue lag or consumer failures.
- Database connection errors and query latency.
- Business metrics such as checkout completion or payment decline rates.
- Logs and traces tagged with release ID or version.

Distinguish new-version bugs from shared environmental issues. For instance, if both old and new versions show higher latency because the database is overloaded, rolling back the new version may not fix the root cause.

To evaluate a canary, define:

- Which metric is the primary indicator?
- Which version serves as the comparison baseline?
- Is the observation window long enough?
- Is traffic high enough for meaningful samples?
- Which thresholds trigger pause, abort, or proceed?
- Who receives alerts and holds decision authority?

Never pick arbitrary thresholds. Anchor thresholds to SLOs, normal variance, real traffic, and change risk.

## 10. Recovery and rollback capabilities

Before using a strategy, verify exactly what the platform can recover.

Typically rollbackable:

- Artifacts to a prior digest.
- Routing to the old backend.
- Deployment manifests to a prior revision.
- Runtime configuration to a prior revision if still valid.

However, not all state reverses automatically:

- Database migrations may have deleted or transformed data.
- Published messages may already be consumed.
- Emails, payments, or external actions cannot be recalled.
- Caches or sessions may have transitioned to new formats.
- Old secrets may have been revoked.

Therefore, rollback plans must address application code, routing, configuration, and data state. For irreversible changes, prepare a forward-fix or recovery procedure.

The platform must support at least the operations matching the chosen strategy:

- Halt the rollout.
- Retain the previous version.
- Shift traffic back to the previous version.
- Restore configuration.
- Monitor post-recovery health.
- Audit decisions and outcomes.

Rehearse rollbacks in non-production environments. Having a rollback button in the UI does not prove the entire system can recover safely.

## 11. Capabilities of common platform types

No platform category inherently fits every strategy. Assess actual configurations and services in place.

| Platform type | Typical capabilities | Must verify further |
|---|---|---|
| Self-managed VMs or bare metal | Can run multiple processes/versions if orchestrated manually | Load balancer, service discovery, capacity, health checks, rollback automation |
| Container platform | Provides images, replicas, and scheduling | Traffic splitting, rollout analysis, storage, quotas, controllers, and policies |
| Kubernetes | Deployments, ReplicaSets, Services, readiness probes, rollout history | Ingress/service mesh, weighted routing, autoscaling, resource quotas, stateful compatibility |
| PaaS | Often provides managed releases, scaling, and health checks | Blue-green/canary support, routing control, rollback windows, runtime limits |
| Serverless | Often supports versions/aliases and traffic shifting per service | Cold starts, concurrency quotas, event sources, state compatibility, observability |
| Edge/CDN platform | Can distribute versions and route at the edge | Cache invalidation, propagation delay, region consistency, and rollback behavior |

This table describes typical capabilities, not guarantees for every product. Platform versions, service tiers, plugins, account configuration, and granted permissions substantially change real capabilities.

For example, Kubernetes provides Deployment rollouts natively, yet weighted canary traffic typically requires an ingress controller, service mesh, or progressive delivery controller. Never assume having Kubernetes means every form of canary is ready out of the box.

## 12. Comparing requirements across deployment strategies

| Strategy | Required platform capabilities | Application requirements | Common limitations |
|---|---|---|---|
| Recreate | Stop old version, start new version | Tolerates downtime or has fallback handling | Outage during transition |
| Rolling update | Multi-instance management, readiness, surge/unavailable limits | Old and new versions compatible together | Bugs can spread gradually before halt |
| Blue-green | Run two groups, routing switch, retain old group | Both versions share data and dependencies safely | High capacity cost, potential state divergence |
| Canary | Traffic splitting or cohort routing, versioned metrics, pause/abort | Detects failures and isolates impact by group | Small traffic samples, routing complexity |
| Shadow traffic | Duplicate/replicate requests or events, isolate side effects | Requests run safely without real effects | Resource cost, sensitive data, side-effect risks |

Shadow traffic is commonly used to evaluate a new version without returning its responses to users. However, if requests place orders, send emails, or execute payments, mirrored copies can cause side effects. Mock, block, or sandbox writes and external calls before mirroring traffic.

## 13. Build a capability matrix before deciding

A capability matrix turns general assumptions into reviewable evidence.

Example for a service running on a container platform:

| Capability | Support level | Evidence | Gaps / actions |
|---|---|---|---|
| Run two revisions in parallel | Native | Two deployments coexist in test environment | Verify production quota |
| Weighted routing | Integrated | Ingress supports traffic weights | Test propagation and connection reuse |
| Readiness gate | Native | Probes respected by controller | Add dependency readiness |
| Versioned metrics | Application-dependent | Metrics include release label | Standardize dashboards and alerts |
| Auto-abort canary | Integrated | Rollout controller reads metrics | Verify thresholds and abort behavior |
| Rollback routing | Native/Integrated | Backend switches back to prior revision | Rehearse with long-lived connections |
| Database compatibility | Application-dependent | Expand-and-contract integration tests | Add realistic production-like data tests |
| Capacity for blue-green | Unverified | No load/capacity test yet | Check quotas and headroom |

Add columns where useful:

- Capability owner.
- Verified environment.
- Verification date and platform version.
- Link to test report or runbook.
- Residual risk.
- Status: verified, partial, unknown, or unsupported.

Never mark a capability verified simply from reading documentation. A capability needs concrete evidence: tests, live configuration, measured limits, or confirmation from the platform owner.

## 14. Platform evaluation workflow before adoption

Follow these steps:

1. **Define release goals:** reduce downtime, cap blast radius, test on a user cohort, or enable fast rollback?
2. **Identify application requirements:** stateful vs. stateless, sessions, databases, queues, long-lived connections, and side effects.
3. **Inspect the platform:** check enabled APIs, features, versions, quotas, networking, identities, and policies.
4. **Build the capability matrix:** classify items as native, integrated, application-dependent, or unavailable.
5. **Identify gaps:** do you need a gateway, service mesh, controller, telemetry, or application changes?
6. **Run a proof of concept:** test in a representative environment with matching routing, quotas, and dependencies.
7. **Test failure paths:** intentionally fail health checks, exhaust capacity, break routing, or deploy a crashing version.
8. **Rehearse rollback:** verify artifacts, configs, routing, and data can recover.
9. **Finalize strategy:** document the choice, rationale, prerequisites, and residual risks.
10. **Codify in the pipeline:** turn verified conditions into preflight checks, gates, and automation.

~~~mermaid
flowchart TD
    A["Define release goals"] --> B["Analyze application and state"]
    B --> C["Explore platform capabilities"]
    C --> D["Build capability matrix"]
    D --> E{"Prerequisites met?"}
    E -- "Not yet" --> F["Add integrations or pick another strategy"]
    F --> C
    E -- "Yes" --> G["PoC in representative environment"]
    G --> H["Test failures and rollback"]
    H --> I{"Evidence passes?"}
    I -- "No" --> F
    I -- "Yes" --> J["Finalize strategy and policy"]
    J --> K["Automate into pipeline gates"]
~~~

The proof of concept must test both happy paths and failure paths. One successful deploy does not prove pause, abort, routing rollback, or unhealthy-instance handling work.

## 15. Example: choosing a strategy by platform capability

Suppose an API service has these traits:

- Runs three replicas.
- Has a load balancer, but no weighted routing yet.
- Has readiness probes.
- Shared database with a schema currently compatible across both versions.
- Metrics distinguish release versions.
- Quota suffices for one extra replica, not two full groups.

Assessment:

- **Blue-green:** unsuitable because capacity cannot support two complete groups.
- **Percentage-based canary:** not ready because the load balancer lacks weighted routing.
- **Rolling update:** viable if the controller supports max surge/unavailable and readiness probes accurately reflect traffic readiness.
- **Recreate:** possible, but risks downtime.
- **Instance-based canary:** potentially testable if service discovery allows adding one new instance and traffic can be targeted via another verified mechanism.

In this case, rolling update is a reasonable first choice. The team still must test crashing new instances, tight quotas, failing readiness, and old/new versions serving requests together. Once weighted routing and extra capacity are added later, canary or blue-green can be re-evaluated.

This example shows that a good strategy is one matching goals with proven capabilities—not the strategy with the most buzzwords or features.

## 16. Anti-patterns when evaluating platform capabilities

| Anti-pattern | Risk | Improvement |
|---|---|---|
| Picking canary because the platform has a canary button | Routing and metrics might not actually work | Verify live traffic paths and rollout analysis |
| Assuming Kubernetes includes weighted canary out of the box | Missing suitable ingress/service mesh/controller | Build a per-cluster capability matrix |
| Testing only successful deploys | Unknown how the platform handles failures | Test pause, abort, unhealthy instances, and rollback |
| Skipping capacity checks | Blue-green or surge rollouts stall Pending | Measure headroom across quotas, zones, and workloads |
| Ignoring data compatibility | Two versions corrupt each other's data | Test schema, message, and session compatibility |
| Using overly simplistic readiness endpoints | Instances take traffic before ready | Design readiness around critical dependencies |
| Missing versioned metrics | Cannot tell if canary errors exceed old version | Tag metrics, logs, and traces with release/version |
| Treating rollback as full restoration | Data or side effects may be irreversible | Build recovery plans per state category |
| Reading only vendor docs | Overlooks real quotas, policies, and config | Run a PoC in a representative environment |
| Omitting verification date and platform version | Capabilities may have drifted or changed | Record evidence, platform version, and owner |

## 17. Pre-adoption checklist for deployment strategies

Before enabling a strategy in production, verify:

- [ ] Release objectives and risk tolerance are defined.
- [ ] Request paths across DNS, gateway, load balancer, and service are mapped.
- [ ] The platform manages revisions as required by the strategy.
- [ ] Routing switches or splits traffic across the intended scope.
- [ ] Long-lived connections, sticky sessions, and connection draining are addressed.
- [ ] Startup, readiness, and liveness checks have appropriate semantics.
- [ ] Rollouts can be paused, aborted, and monitored for status.
- [ ] Capacity, quotas, and autoscaling suffice for transitional states.
- [ ] Both versions are compatible with databases, caches, queues, sessions, and events.
- [ ] Metrics, logs, and traces distinguish versions.
- [ ] SLO-based proceed, pause, and abort thresholds exist.
- [ ] Identity and policies restrict execution to authorized people or workloads.
- [ ] Artifacts and configuration are pinned by revision/digest.
- [ ] Failure paths and rollbacks have been tested in a representative environment.
- [ ] Non-rollbackable risks have recovery or forward-fix plans.
- [ ] The capability matrix records evidence, owner, date, and platform version.
- [ ] Pipelines include preflight checks to catch drifted capabilities or violated prerequisites.

## 18. Self-assessment exercise

A team wants to use blue-green for a payment service. The current platform provides:

- Kubernetes with Deployments and Services.
- An ingress controller that routes traffic to only one backend at a time.
- A database migration renaming a column.
- Sessions stored in per-pod memory.
- Dashboards showing aggregate metrics only, without release version labels.
- Production quota sufficient only for the current replica count.
- Rollout history enabled, yet rollback has never been rehearsed.

Evaluate:

1. Which capabilities does blue-green require that the platform currently lacks?
2. Is running two Deployments concurrently enough to conclude blue-green is ready?
3. What must change at the ingress or routing layer for controlled traffic cutover?
4. How do in-memory sessions behave when traffic switches to the new group?
5. Is a column-renaming migration compatible with two versions running concurrently?
6. Which metrics and logs must be added to observe each version individually?
7. How must quotas change or the strategy adapt?
8. Which failure and rollback steps need rehearsal?
9. If blue-green requirements cannot yet be met, which strategy better fits current capabilities?

A strong design identifies missing capabilities, required evidence, and remediation sequence. You may adopt a simpler strategy initially and revisit once both platform and application satisfy the prerequisites.

## Conclusion

A deployment strategy lowers risk only when the platform and application genuinely support the operations that strategy demands. Evaluate version orchestration, routing, health checks, capacity, data compatibility, observability, identity, and recovery before choosing rolling, blue-green, canary, recreate, or shadow traffic.

Build an evidence-backed capability matrix, validate in a representative environment, and test both failure paths and rollbacks. When capabilities fall short, add the missing integrations or choose a strategy better suited to current constraints. Evidence-driven decisions prevent deploying a model that exists only on paper yet cannot run safely on the real platform.
