# SLA, Release Stages, and GCP Service Lifecycle

Google Cloud provides many services to organize resources by organization and project, control permissions with IAM, build VPC networks, run applications on Compute Engine, Google Kubernetes Engine (GKE), or Cloud Run, and store data on Cloud Storage or managed databases. However, choosing the right service type is only part of system design. When taking an application to production, the operations team must also answer three questions:

1. **SLA:** What service level does the provider commit to, measured by what criteria, and under what scope?
2. **Release stage:** Is the feature experimental or Generally Available (GA)?
3. **Lifecycle:** Until when are the service, API, and version supported, and what must be done when they change or reach end of support?

These three questions are closely connected but do not substitute for one another. A GA service may still fail to meet your application's availability goals if your deployment configuration creates a single point of failure. A Preview feature may look appealing yet still change its interface and support terms. A version running smoothly today can still hit end of support in the future.

## 1. Understanding SLA, SLO, and SLI Accurately

### 1.1. Three Frequently Confused Concepts

| Term | Meaning | Who Defines It? | Example |
| --- | --- | --- | --- |
| **SLI – Service Level Indicator** | A measurable metric of an aspect of service quality, such as request success rate, latency, or error rate. | The service-owning team defines how to measure; the provider also defines its own measurement in terms. | 99.97% of valid requests to the API succeeded over 30 days. |
| **SLO – Service Level Objective** | An internal or operational target placed on an SLI over a time window. | Product team, SREs, and operational owners. | At least 99.95% of valid requests succeed each month. |
| **SLA – Service Level Agreement** | A contractual service commitment with users; typically specifies scope, measurement, applicability conditions, and service credits if unmet. | Provider and customer under the effective agreement. | A GCP product SLA specifies a monthly uptime percentage and service credit tiers when qualifying conditions are met. |

**SLI** tells you what is actually happening, **SLO** tells you what level the operations team aims to achieve, and **SLA** states a specific contractual commitment. An SLA is not a guarantee that an application will never experience downtime. Nor does an application's SLO automatically equal the SLA of the underlying cloud services it uses.

In Google Cloud, always look up the **SLA for the exact product, configuration, and usage conditions**. There is no single SLA percentage covering every GCP service. Terms can vary by deployment mode, resource type, geographic scope, or effective agreement version. An SLA must also be distinguished from commitments around **data durability**, latency, support response times, and security features.

### 1.2. Illustrating Availability Math

For a system measured by uptime duration, a simple conceptual formula is:

\[
\text{Availability (\%)} = \frac{\text{Total observation time} - \text{Downtime}}{\text{Total observation time}} \times 100
\]

Assume a month has exactly **30 days**, equal to **43,200 minutes**, and every minute of outage counts:

| Assumed Availability Level | Corresponding Maximum Downtime in 30 Days |
| --- | ---: |
| 99% | 432 minutes = 7 hours 12 minutes |
| 99.9% | 43.2 minutes |
| 99.95% | 21.6 minutes |
| 99.99% | 4.32 minutes |

For example, if the system is down for 70 minutes in 30 days, the rate computed by the formula above is approximately **99.838%**. If the operations team sets a 99.9% SLO under this exact measurement, the system has missed its SLO.

**Note:** This is strictly an illustrative math example to build intuition for percentages. Each Google Cloud product's actual SLA may define "downtime," measurement intervals, regions, error thresholds, exclusions, and rounding differently from this simplified calculation. Do not use this table to conclude on your own that Google owes a service credit.

### 1.3. When Do Service Credits Apply?

When reviewing a GCP SLA document, read at least the following sections:

| Section to Inspect | Operational Question |
| --- | --- |
| **Covered service / scope** | Which services, resources, regions, versions, and configurations are covered? |
| **Metrics and measurement window** | Is "Monthly uptime percentage" or another metric used? How is downtime defined? |
| **Conditions and exclusions** | Are specific configurations required? Which events are excluded from SLA violations? |
| **Service credit tiers** | If conditions are met, what tier calculates the credit and on which eligible charges? |
| **Claim procedure** | Must a claim with evidence be submitted within a deadline? Through which channel? |
| **Effective terms** | Which agreement governs your current contract, product, and usage period? |

A service credit is typically a **billing credit under service terms**, not compensation for all business damages. Receiving a credit also does not restore lost data, reduce outage duration, or satisfy commitments your business made to its own customers.

### 1.4. A Platform SLA Is Not an End-to-End Application SLA

Suppose an ordering API runs on Cloud Run, writes orders to Cloud SQL, and serves product images from Cloud Storage. Order requests can fail if any required dependency fails, if the application is misdeployed, if a service account lacks IAM permissions, if a quota is exhausted, or if network configuration breaks connectivity.

Therefore:

- **Cloud Run:** you must evaluate the application runtime's availability conditions and capacity to handle real traffic.
- **Cloud SQL:** you must review database configuration, failover behavior, connectivity, and recovery plans.
- **Cloud Storage:** you must distinguish data accessibility, storage durability, and the characteristics of the chosen storage class/location.
- **GKE:** control plane availability does not by itself prove that every Pod, node, or team-deployed API meets its SLO.
- **Compute Engine:** a single VM can still be a single point of failure even though Compute Engine has an SLA; multi-zone architecture, load balancing, and recovery are what handle many application failures.

Do not simply add or multiply SLA numbers to claim a new legal SLA for your application. Probabilistic modeling can help during design evaluation, but its results are only meaningful if assumptions about failure independence, dependency chains, and redundancy hold true in the real system. **Measuring end-to-end SLIs from the user's perspective** remains mandatory.

### 1.5. From SLA to Reliability Design

When the business goal is minimizing disruption, the engineering team must design and operate what it controls:

1. Identify critical user journeys, such as "successfully placing an order," then define SLIs and SLOs for that journey.
2. Choose an appropriate architecture: multi-zone, load balancing, HA-capable managed services, autoscaling, or cross-region redundancy when genuinely justified by business requirements.
3. Verify VPC networking, firewalls, IAM, service accounts, quotas, and capacity limits; these are all failure sources outside platform SLAs.
4. Set up Cloud Monitoring, Cloud Logging, SLO-based alerts, failover testing, and incident response procedures.
5. Plan backups and test restores. **HA reduces interruptions; backups recover from data loss or corruption. The two capabilities do not replace each other.**
6. Balance reliability with cost: duplicating resources, cross-region traffic, standby environments, and monitoring all add cost.

With a 99.9% SLO over a 30-day month, the "error budget" equals 43.2 minutes under the time-based illustration. When the error budget burns down rapidly, the team can slow risky releases and prioritize reliability work first.

## 2. Release Stages of GCP Services and Features

### 2.1. What Do Pre-GA and GA Tell You?

Google Cloud releases services and features in multiple stages. Exact labels can vary by product; common terms include **Early Access**, **Alpha**, **Beta**, **Preview** (private or public), and **General Availability (GA)**.

| Common Stage / Label | Key Characteristics | Appropriate Usage |
| --- | --- | --- |
| **Early Access / Alpha / Private Preview** | Access may be restricted, requiring sign-up or invitation; APIs, behavior, supported regions, and docs can change substantially. | Prototyping ideas, checking feasibility, giving feedback; confirm terms and access eligibility. |
| **Beta / Public Preview / Preview** | Broader access for users to try, but the feature is still Pre-GA and may change or have usage and support limitations. | Controlled experiments, compatibility testing, and cost/benefit evaluation before committing critical workloads. |
| **GA – General Availability** | The product or feature is released for broad use under current documentation and terms. | Primary candidate for production systems, after checking security, SLA, regions, quotas, cost, and operability. |

Preview/Alpha/Beta labels do not always appear in a strict sequence or carry identical entitlements across all products. **Pre-GA** is the umbrella term for offerings not yet GA and usually carries separate terms of service. For Pre-GA features, never assume GA-equivalent SLAs, support policies, backward compatibility, or availability in every region; verify in product docs and applicable terms.

**GA also does not mean "an SLA is guaranteed in every configuration."** A generally available service only satisfies production needs after engineers thoroughly verify its terms and actual design. Likewise, **a GA service can introduce Preview features**: evaluate release maturity at the level of the specific feature, API, or version you use, not just the service name.

### 2.2. Three Types of "Release" to Distinguish

In GCP environments, the word *release* can refer to three different things:

| Context | Example | Decision to Make |
| --- | --- | --- |
| **Google product/feature stage** | An API labeled Preview, later moving to GA. | Should production depend on this feature, and which terms currently apply? |
| **Platform versions and release channels** | GKE offers release channels such as Rapid, Regular, and Stable. | At what cadence do we receive updates, how compatible are they, and when must we upgrade? |
| **Development team's app release pipeline** | Promoting code through dev, test/staging, canary, and production. | When to deploy, how to test, and how to roll back or roll forward? |

**GKE release channels** govern Kubernetes version cadence and upgrades—they are not another name for Preview/GA of GKE itself. Similarly, the fact that an application is in "staging" says nothing about the release stage of the Cloud Run API it consumes.

### 2.3. Process for Evaluating a Pre-GA Feature

For example, a team wants to adopt a new BigQuery or Cloud Run feature currently labeled Preview. Before integrating it into a customer-facing service, answer:

1. Which projects, organizations, regions, and user groups have the feature enabled? Does it require special enrollment or approval?
2. How might APIs, data schemas, configurations, and current limits change? Do we have a way to test and update clients?
3. How are Pre-GA terms, data security, data processing conditions, and support commitments described?
4. Does an SLA apply to **this specific feature**, or only to other GA parts of the service?
5. If the feature changes or is discontinued, what fallback or migration path to a GA solution does the team have?

For Pre-GA features, you can dedicate a separate sandbox project, enforce least-privilege IAM, use appropriate test data, set quotas/budgets, and measure with real tests. Only introduce it into critical flows once risks, terms, and recovery paths are explicitly accepted.

## 3. GCP Service Lifecycle: From Experimental to Discontinued

### 3.1. High-Level Lifecycle

The diagram below depicts **possible states**, not a mandatory path for every service:

~~~mermaid
flowchart LR
    A["Concept / Early Access"] --> B["Pre-GA: Alpha, Beta, Preview"]
    B --> C["GA: operations and improvements"]
    C --> D["Deprecated / migration notice"]
    D --> E["End of support or shutdown"]
    B -. "Experiment may be discontinued" .-> E
    C -. "Older version reaches end of support" .-> E
~~~

- **Experimental, Pre-GA:** access scope and capabilities remain fluid; the offering may advance to GA, change design, or be discontinued.
- **GA and maintained:** Google may add features, fix bugs, update APIs, release new versions, or adjust operational parameters per product policy.
- **Deprecated (recommended to stop using or migrate):** an API, version, or feature is announced as legacy and should move to a newer option; it may continue running during a transition window.
- **End of support:** support coverage for a version/feature ends per the relevant policy; this does not necessarily mean the entire service shuts down immediately.
- **Shutdown / Discontinued:** the capability or service is no longer provided per the published schedule and scope. Any application still directly depending on it may stop working.

Notice periods, migration assistance, and discontinuation terms **vary by service, API type, version, and agreement terms**. Never assume a single universal transition window across all of GCP. Always read official announcements for the exact resources your application uses.

### 3.2. Lifecycle Across Multiple Layers

A system can be impacted at multiple layers:

| Layer of Change | Example Scenario | Risk to the Application |
| --- | --- | --- |
| **Entire service** | Provider announces sunsetting of a product. | Must select an alternative architecture or provider. |
| **Feature** | A Preview feature changes behavior or is discontinued. | Business flows relying on that specific feature must be modified. |
| **API / API version** | An older API version is deprecated. | SDKs, integration code, or deployment tools must be upgraded. |
| **Runtime / platform version** | A Kubernetes version or application runtime reaches end of support. | Requires upgrading, compatibility testing, and re-validating deployments. |
| **Configuration / policy** | Usage terms, security defaults, or supported regions change. | The system may need updates to IAM, networking, resources, or budget. |

For example, with GKE you must track the **Kubernetes version** lifecycle, cluster upgrade schedules, and the chosen release channel. With Cloud Run, track both platform features and runtimes, container images, and team-managed libraries. With Compute Engine, an OS image or software version reaching end of support is distinct from the lifecycle of the VM service itself.

### 3.3. Information Sources and Tracking Practices

Do not wait until a deployment breaks to check lifecycle status. During design and operations, teams should:

- Follow product documentation and **release notes** to spot new releases, behavior changes, limits, security upgrades, and deprecation notices.
- Read **SLAs and Service Terms** for the exact service, timeframe, and applicable contract; log the check date on major architecture decisions.
- Monitor relevant announcements via admin consoles, support channels, or service status/info pages; verify who receives notices in the organization.
- Maintain a resource inventory by project, owner, criticality, region, version, API dependencies, and action deadlines.
- Build compatibility, resilience, and cost checks into regular upgrade cycles.

You can use the Google Cloud CLI to **start** inventorying parts of a project:

~~~bash
# PROJECT_ID is the ID of a project the operator has permission to view.
gcloud services list --enabled --project="$PROJECT_ID"
gcloud compute instances list --project="$PROJECT_ID"
gcloud container clusters list --project="$PROJECT_ID"
gcloud run services list --project="$PROJECT_ID"
~~~

The list of enabled APIs is **not** a complete list of active billable services or Preview features in use. These commands are only a starting point; supplement them with resource inventories, configurations, versions, Infrastructure as Code (IaC), change logs, and application dependencies. IAM permissions, enabled APIs, and CLI version also affect command output.

## 4. Deployment Decisions: Combining SLA, Release Stage, and Lifecycle

### 4.1. Scenario: Ordering System on Google Cloud

An enterprise deploys an ordering API on **Cloud Run**, transactional data in **Cloud SQL**, and product images in **Cloud Storage**. The team uses **Cloud Monitoring** to track the order request success rate and sets an internal **99.95% monthly SLO**. This is a self-selected target, not a combined SLA of those GCP products.

When finalizing configurations, the team makes the following decisions:

| Decision | How to Evaluate |
| --- | --- |
| Launching the ordering API to production | Verify whether required components are GA; check SLAs for the exact services, regions, and chosen configurations. |
| Increasing database fault tolerance | Evaluate Cloud SQL HA options and failover behavior; re-test app connections, transactions, and recovery time. |
| Using a Preview feature for report generation | Isolate it in a non-blocking reporting flow; confirm terms, fallback plan, and compatibility. |
| Updating runtimes / APIs | Track version lifecycles, test on staging, roll out progressively, and prepare recovery paths. |
| Demonstrating reliability to customers | Collect SLIs from the API itself, report against SLOs, and communicate incidents transparently; never treat individual resource SLAs as an end-to-end promise. |

If Cloud SQL has to restart or data access permissions are misconfigured, order requests can still fail even while Cloud Run serves HTTP normally. Therefore, the SLI "Cloud Run responds" is less complete than the SLI "order created successfully." Conversely, a platform service incident can impact your product without necessarily qualifying for service credits if it does not meet the SLA's specific definitions.

### 4.2. Workflow When Receiving a Deprecation Notice

Suppose the team receives notice that an API version in use is reaching end of support:

1. **Assess impact:** locate all projects, services, SDKs, automated jobs, and external systems depending on that version; assign an owner.
2. **Confirm timelines:** read the primary announcement, affected scope, cutoff dates, and provider-recommended migration path.
3. **Select migration path:** newer API version, GA replacement feature, SDK upgrade, or architectural adjustment; check security, data, IAM, networking, and cost.
4. **Test:** run compatibility, data, access permission, performance, limit, and recovery tests in an appropriate environment; measure relevant SLIs.
5. **Roll out safely:** deploy progressively if feasible, watch error rates, define halt thresholds, and prepare rollback or roll-forward depending on change type. Some stateful or version upgrades cannot be downgraded.
6. **Verify and close:** remove legacy dependencies, update runbooks, architecture docs, alerts, and lifecycle tracking sheets.

Replacing an API ahead of the deadline not only avoids outages at sunset, but also lets the team calmly evaluate cost, permission, and behavioral changes rather than reacting under incident pressure.

### 4.3. Minimum Checklist Before Using a GCP Service in Production

| Check Area | Completion Criteria |
| --- | --- |
| **Needs** | Clearly state the task, user SLIs/SLOs, and business impact of service interruption. |
| **Maturity** | Confirm GA vs. Pre-GA at the level of features actually used; record applicable terms and limits. |
| **SLA** | Identify the exact applicable SLA, qualifying configurations, measurement rules, exclusions, and credit claim process. |
| **Architecture** | Evaluate zones/regions, HA, serial dependencies, timeouts, retries, idempotency, quotas, and failure modes. |
| **Security** | Review IAM, service accounts, VPCs, data policies, encryption, and administrative privileges. |
| **Observability** | Set up metrics, logs, dashboards, SLO alerts, alert recipients, and runbooks. |
| **Recovery** | Ensure suitable backup/restore, tested recovery, and RTO/RPO targets where needed. |
| **Lifecycle** | Assign an owner to monitor release notes, versions, and deprecation/end-of-support notices. |
| **Cost** | Estimate compute, data transfer, redundancy, and monitoring costs; configure appropriate budgets and spend alerts. |

## 5. Misconceptions to Avoid

**“With a 99.9% SLA, the system is guaranteed at most 43.2 minutes of downtime.”** False. That number is simply a mathematical conversion in a 30-day month example; actual SLA scopes follow specific rules, and application downtime depends on many customer-operated components.

**“If a service is GA, all its APIs and features are GA.”** False. Verify each individual feature, API, version, and region; a GA service can include Preview extensions.

**“Preview features can never be used in production.”** Too absolute. Suitability depends on terms, policies, workload traits, and acceptable risk. For critical paths, prefer an appropriate GA option and keep a clear fallback plan.

**“Deprecated means the service is shut down today.”** Not necessarily. Deprecated usually signals a need to migrate, while exact end-of-support or shutdown dates must be read from the specific notice.

**“Multi-zone redundancy means backups aren't needed.”** False. Zonal/regional redundancy reduces certain outage types, but does not replace the ability to recover data that was accidentally deleted, corrupted by bad logic, or damaged.

**“Service credits are an incident recovery measure.”** False. Service credits relate to contractual SLA remedies; restoring service still requires fault-tolerant architecture, monitoring, operational action, and incident response processes.

## 6. Official References to Cross-Check

Terms, release labels, and deprecation schedules are subject to change. When applying this lesson to real production decisions, verify the currently effective documents at:

- **Google Cloud Service Level Agreements:** https://cloud.google.com/terms/sla
- **Google Cloud Service Specific Terms:** https://cloud.google.com/terms/service-terms
- **Google Cloud documentation:** https://cloud.google.com/docs
- **Google Cloud release notes:** https://cloud.google.com/release-notes
- **GKE release channels documentation:** https://cloud.google.com/kubernetes-engine/docs/concepts/release-channels

For every service choice, the right goal is to **know how commitments are measured, evaluate feature readiness, and track changes throughout the lifecycle**. Turn that information into architectural decisions, end-to-end SLOs, upgrade plans, and verifiable incident response capability.
