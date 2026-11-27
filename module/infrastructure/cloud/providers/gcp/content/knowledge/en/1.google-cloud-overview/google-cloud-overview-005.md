# Cloud Adoption Framework and the Google Cloud Adoption Journey

## Learning Objectives

After this lesson, learners will be able to:

1. Explain why adopting Google Cloud is a transformation across **people, processes, technology, and governance**, not merely lifting servers to the cloud.
2. Use the **Google Cloud Adoption Framework (CAF)** to evaluate four themes—**Learn, Lead, Scale, Secure**—across three maturity levels: **Tactical, Strategic, Transformational**.
3. Translate assessment results into an **Assess → Plan → Deploy → Optimize** roadmap with business goals, clear owners, risk controls, and measurable metrics.
4. Identify foundational decisions involving projects, IAM, VPCs, Compute Engine, GKE, Cloud Run, storage, databases, automated releases, observability, and cost.
5. Plan Google Cloud adoption for a real-world system, from small pilot experiments to stable operations.

## 1. What Is Cloud Adoption and What Problem Does CAF Solve?

An enterprise can spin up a few VMs on **Compute Engine** in a single day and still lack organizational cloud operating capability. Without a permission model, change management processes, cost controls, or incident response skills, scaling from one pilot application to dozens of production applications becomes unpredictable.

**Cloud adoption** is the process of embedding cloud capabilities into how an organization designs, develops, deploys, secures, operates, and improves its products. This journey may involve migrating existing systems, modernizing applications, and building new services directly in the cloud.

The **Google Cloud Adoption Framework** is a framework for assessing an organization's readiness and maturity. It helps answer three questions:

- **Where are we now?** To what extent do teams already have the skills, decision authority, self-service platforms, and guardrails?
- **Where do we want to go?** What capabilities are truly needed to achieve business goals, rather than chasing a uniform maturity score for every system?
- **What needs to change?** Select the most critical gaps, assign owners, and prioritize work so progress is verifiable.

In the **CLOUD_PROVIDERS_GCP** module, learners approach Google Cloud from resource hierarchy, projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage, and databases; while practicing service selection, resource protection, release automation, reliability monitoring, and cost control. CAF serves as the bridge that turns those technical skills into a cohesive cloud adoption program.

### Distinguishing Three Common Frameworks

| Concept | Primary Question | Typical Outputs |
|---|---|---|
| **Cloud Adoption Framework** | Is the organization ready to use the cloud effectively? | Capability assessment, gaps, improvement roadmap |
| **Migration process** | How do we move a portfolio of workloads to the target environment? | Application inventory, migration strategy, rollout waves, post-cutover validation |
| **Well-Architected Framework** | Do a workload's architecture and operations meet quality requirements? | Review of design, reliability, security, cost, performance, and operations |

These frameworks complement one another: **CAF guides organizational transformation**, the migration process structures moving workloads, and architecture reviews improve the quality of specific solutions. A cloud adoption program can also start with greenfield applications without any migration activity.

## 2. The Four Themes of the Google Cloud Adoption Framework

Google Cloud's official CAF defines four themes: **Learn, Lead, Scale, Secure**. These capabilities must grow in parallel; investing in only one theme usually creates bottlenecks in the others.

| Theme | Focus | Observable Signs of Progress | Questions to Ask |
|---|---|---|---|
| **Learn** | Skills and knowledge sharing | Role-based training, hands-on sandbox practice, documentation, and internal communities | Can the team design, deploy, and troubleshoot independently, or do they rely entirely on external specialists? |
| **Lead** | Executive sponsorship and cross-team alignment | Sponsors, product owners, platform leads; shared objectives and decision-making mechanisms | Who sets priorities, accepts risk, and resolves cross-departmental dependencies? |
| **Scale** | Right cloud services, automation, and repeatable processes | Project templates, Infrastructure as Code, CI/CD, operational standards, managed services | When adding a new app or team, does everything have to be built manually from scratch? |
| **Secure** | Identities, resources, data, and continuous controls | Least-privilege access, logs/auditing, secret management, policies, and configuration drift monitoring | Who can access which data, by what path, and how are misconfigurations detected? |

### 2.1. Learn: Building Autonomy

Learning is more than counting certifications. Development teams need to know how to package and deploy applications; platform teams must understand IAM, VPCs, service accounts, and resource quotas; operations teams need to read metrics, logs, and traces and handle incidents.

For example, before putting an application onto **Cloud Run**, the team practices deploying in a staging environment, reading logs, setting up alerts, diagnosing **Cloud SQL** connection errors, and rolling back to a previous revision. Evidence of maturity is having a **runbook** and recovering independently during a drill, rather than merely completing a course.

### 2.2. Lead: Aligning Technology with Business Goals

Leadership support must show up in clear goals, budgets, decision-making authority, and accountability. Bottom-up collaboration matters just as much: application, security, data, finance, and operations teams all need to participate.

For instance, the goal "reduce release cycle from monthly to weekly" drives budget decisions for CI/CD, automated testing, environment management, and training. Setting a KPI like "number of VMs migrated" alone might check a technical box without improving delivery speed or customer experience.

### 2.3. Scale: Growing Through Repeatable Processes

Scalability here includes **scaling organizational capability**, not just autoscaling instance counts. Common decisions include:

- Standardizing the **organization → folder → project** structure, resource labeling, and billing governance.
- Establishing foundational **VPC/subnet** networking, connectivity to existing systems, DNS, and policy-driven firewall rules.
- Using **Terraform** or suitable IaC tools to reproduce configurations; using pipelines to validate and release changes.
- Choosing **Cloud Run**, **GKE**, or **Compute Engine** based on workload needs and operational capability; favoring managed services when they solve the right problem.
- Maintaining reusable monitoring, alerting, backup, and incident response templates for application teams.

For example, when onboarding a new project for the data analytics team, a workflow can automatically provision the project, apply standard IAM and policies, attach billing, enable logging, and configure a budget alert—with verification and appropriate approvals at each step.

### 2.4. Secure: Security Designed from the Ground Up

Practical controls include **least-privilege** access, separating human and workload identities, managing **service accounts**, storing secrets in **Secret Manager**, data encryption and classification, restricting network flows, audit logs, and organization policies.

Understand **shared responsibility**: Google Cloud protects the provider-managed infrastructure components per the service model; customers remain responsible for data, identities, configurations, access permissions, applications, and many operational activities under their control. Using managed services can reduce server maintenance, but does not automatically fix IAM misconfigurations or overly permissive data access.

For example, for a customer database, only the application's service account should hold minimal access permissions; administrative access must follow a controlled approval process; and backups and recovery capability must be tested periodically.

## 3. Three Maturity Levels: Tactical, Strategic, Transformational

Google Cloud defines the **Cloud Maturity Scale** with three levels. These maturity levels apply **per CAF theme**; an organization can easily be Strategic in security while still Tactical in training.

| Theme | **Tactical** | **Strategic** | **Transformational** |
|---|---|---|---|
| **Learn** | Individuals learn ad hoc, heavy reliance on specialists | Role-based training programs and cross-team knowledge sharing | Learning embedded in daily work, communities of practice, continuous improvement |
| **Lead** | Isolated team efforts, fragmented goals | Dedicated cloud program owner, cross-functional alignment | Cloud acts as a shared capability driving product delivery and business innovation |
| **Scale** | Manual setup, risky and difficult changes | Infrastructure templates, pipelines, governance processes, and automation | Controlled self-service platform with continuous measurement and optimization |
| **Secure** | Isolated controls, heavy reliance on manual reviews | Standardized identities, policies, logging, and security workflows | Integrated, automated controls and drift detection with continuous refinement |

*The indicators in this table are practical examples for learner self-assessment, not an official Google Cloud scoring rubric.*

Crucially, **target maturity depends on goals and risk**. A team running a small internal website may not need a multi-cluster Kubernetes platform. Conversely, a payment system or one processing sensitive data requires strict security, recovery, and monitoring standards from the earliest stages, even while still small in scale.

### How to Run a Maturity Assessment Session

1. **Define scope:** the entire organization, a business unit, or a workload portfolio; state the scope explicitly to avoid vague ratings.
2. **Gather evidence:** approval workflows, architecture diagrams, pipelines, IAM documentation, budgets, incident reports, recovery drill outcomes, training plans.
3. **Assess each theme:** assign Tactical, Strategic, or Transformational and document why; ratings may differ across departments.
4. **Identify gaps:** for example, applications deploy automatically, but no one owns alerts or incident response.
5. **Prioritize work:** base priorities on business value, risk, dependencies, cost, and execution capacity.
6. **Schedule a reassessment:** use the same categories of evidence to verify whether capability has genuinely improved.

Example of an **illustrative internal assessment sheet** (not an official Google API or tool format):

~~~yaml
assessment:
  scope: "Sales product operations team"
  business_goal: "Safe weekly releases"
  themes:
    learn:
      current: tactical
      target: strategic
      evidence: "No incident response drills conducted yet"
      next_action: "Run a Cloud Monitoring lab and author runbooks"
    lead:
      current: strategic
      target: strategic
      evidence: "Product owner and shared cloud team established"
      next_action: "Maintain regular risk and outcome review meetings"
    scale:
      current: tactical
      target: strategic
      evidence: "Projects and deployments performed manually"
      next_action: "Standardize Terraform and CI/CD pipelines"
    secure:
      current: tactical
      target: strategic
      evidence: "Access permissions not reviewed periodically"
      next_action: "Standardize IAM groups, service accounts, and auditing"
~~~

Use this assessment strictly to **drive decisions**. Never average the levels into a single score that masks a critical Secure risk.

## 4. Turning CAF Results into a Google Cloud Adoption Journey

In Google Cloud's migration guidance, the execution process is structured into four phases: **Assess → Plan → Deploy → Optimize**. These are **work phases**, distinct from CAF's three **maturity levels** (Tactical/Strategic/Transformational).

~~~mermaid
flowchart LR
    A["Assess: understand current state<br/>and readiness"] --> B["Plan: design foundation<br/>and rollout waves"]
    B --> C["Deploy: implement, test,<br/>and cut over"]
    C --> D["Optimize: measure, improve,<br/>and scale"]
    D --> E["Reassess Learn / Lead / Scale / Secure"]
    E --> A
~~~

### Phase 1 — Assess: Understand Current State and Goals

**Inputs:** business requirements, existing running systems, legal or data constraints, current team and budget.

Key activities:

- **Set measurable objectives:** shorten release lead times, scale on demand, improve recovery capability, reduce operational toil, or accelerate product delivery.
- **Inventory workloads:** application owners, OS and database versions, data, connectivity flows, internal/external dependencies, latency requirements, and tolerable downtime.
- **Classify data and risks:** personal data, data residency requirements, retention periods, access permissions, and audit obligations.
- **Measure the baseline:** traffic, CPU/RAM, storage capacity, latency, error rates, current total cost, and availability targets; build a baseline for comparison.
- **Assess CAF maturity:** determine whether people, leadership, scaling processes, and security are ready for the planned workloads.
- **Run a small pilot if needed:** a proof of concept with a clear hypothesis and explicit success criteria.

**Outputs:** workload and dependency inventory, CAF assessment, preliminary business case, risks, non-functional requirements, and candidate list for the first wave. **Migration Center** can assist with asset discovery and cost estimation, though humans still need to validate the data and assumptions.

### Phase 2 — Plan: Design the Foundation and Roadmap

Once requirements are clear, the organization designs a **landing zone**—the shared foundation and policies put in place before production workloads go live.

| Component to Decide | Google Cloud Design Example | Verification Criteria |
|---|---|---|
| **Resource hierarchy** | Organization, folders by unit/environment, projects by workload | Clear owners, policy scope, billing boundaries |
| **Identity and access** | User groups, least-privilege IAM roles, dedicated service accounts per workload | No overly broad roles; formal grant/revoke process |
| **Network connectivity** | VPC, regional subnets, DNS, firewall rules, Cloud VPN or Interconnect as needed | Traffic flow diagrams, restricted access, paths to dependent systems |
| **Data protection** | Secret Manager, appropriate encryption and key management, backups, retention policies | Tested recovery capability; data classified |
| **Deployment** | Terraform/IaC, source repositories, CI/CD, review and rollback workflows | Reproducible environments, controlled changes |
| **Observability and operations** | Cloud Logging, Cloud Monitoring, alerts, dashboards, runbooks | On-call ownership and incident handling procedures |
| **FinOps** | Billing account, budgets and alerts, cost allocation labels | Costs tracked by team, product, and environment |

Next, **group workloads into waves** based on dependencies and risk. Loosely coupled apps may suit the initial wave; systems sharing databases with strict downtime windows require more complex planning.

For each workload, evaluate the strategies:

- **Rehost:** move largely as-is, such as shifting data center VMs to Compute Engine; faster to execute, though it may preserve existing costs or operational overhead.
- **Replatform:** swap part of the platform, such as moving a compatible database to Cloud SQL or running containers on a managed service.
- **Refactor/re-architect:** redesign the architecture to leverage autoscaling, asynchronous processing, or serverless services; requires more testing and engineering effort.
- **Replace/repurchase:** adopt an off-the-shelf product or SaaS when it is more cost-effective than maintaining a custom system.
- **Retain/retire:** keep workloads unsuitable for migration for now, or decommission systems that no longer deliver value.

Do not assume everything must be containerized by default. Base the decision on runtime requirements, team skills, risk, total cost of ownership, and expected benefits.

**Outputs:** validated landing zone, target architectures, chosen strategy per workload, wave sequencing, cost estimates, test plans, rollback plans, owners, and approval gates.

### Phase 3 — Deploy: Controlled Rollout

Run a **pilot** on a small workload with high validation value, then expand across waves. A typical deployment cycle:

1. Provision infrastructure using reviewed configurations; apply standard IAM, networking, secret storage, and monitoring.
2. Deploy the application to a test environment; run functional, data, load, security, and integration tests.
3. Sync or migrate data using methods compatible with source/target systems; verify integrity and expected downtime.
4. Establish a **cutover** window, rollback plan, and incident communication channels.
5. Shift traffic according to plan; watch errors, latency, data correctness, and business KPIs; proceed or roll back based on pre-agreed thresholds.
6. Hand over to operations with dashboards, alerts, runbooks, access permissions, and change records.

**Outputs:** workload running in the target environment, test evidence, cutover sign-off, post-deployment review, and any remaining follow-up items assigned to owners.

### Phase 4 — Optimize: Data-Driven Improvement

Once workloads stabilize, use real production metrics to improve:

- **Reliability:** define appropriate SLIs/SLOs, tune alerts, test backups/restores, and review failure domains and recovery times.
- **Cost:** identify idle resources, oversized rights/capacities, track budgets and per-workload spend, and weigh cost against delivered value.
- **Performance and scaling:** measure latency, throughput, and load patterns before adjusting autoscaling, caching, databases, or architecture.
- **Security:** review permissions, rotate secrets when needed, detect configuration drift, patch vulnerabilities, and validate compliance controls.
- **Organizational capability:** turn pilot lessons into reusable templates, train subsequent teams, and update the CAF assessment.

**Optimize does not end after a single migration wave.** It is an ongoing practice that elevates cloud usage from isolated deployments into a dependable organizational capability.

## 5. How Does CAF Influence Service Selection?

Service selection must combine technical requirements with **Learn** skills, **Lead** alignment, **Scale** standardization, and **Secure** constraints. The table below suggests evaluation directions rather than rigid default rules:

| Need / Workload | Google Cloud Options to Consider | CAF Questions to Answer First |
|---|---|---|
| Deep dependency on VMs or OS-level software | **Compute Engine** | Can the team handle VM patching, backups, monitoring, and lifecycle management? |
| Stateless APIs or workers running in containers | **Cloud Run** | Has the app externalized state and properly handled connections, secrets, and autoscaling? |
| Multi-service platform needing Kubernetes control | **GKE** | Is there a clear technical reason plus capability to run clusters, network policies, upgrades, and monitoring? |
| Relational database compatible with a managed service | **Cloud SQL** or **AlloyDB** where appropriate | Have version compatibility, performance, HA, backups, RPO/RTO, and migration strategy been evaluated? |
| Storing objects like images, documents, backups | **Cloud Storage** | Are storage classes, retention periods, access controls, and lifecycle policies defined? |
| Large-scale data analytics | **BigQuery** | Are data governance, query/cost controls, and dataset access permissions in place? |
| Asynchronous messaging between components | **Pub/Sub** | Has the team designed for retries, duplicate messages, ordering (if needed), and dead-letter queues? |

For example: if a small team only needs to deploy a stateless API, Cloud Run typically lowers infrastructure overhead. If an app needs specialized OS daemons, Compute Engine may fit better. If a platform team already exists and multiple workloads require Kubernetes configurability, GKE can be worth the investment. Every choice must be verified through testing and real requirements.

## 6. End-to-End Scenario: Retail Company Migrating an Ordering System

Suppose **An Phat** company runs an ordering website on several self-managed VMs, a PostgreSQL database, and local product image storage. The development team wants to release weekly, but every release requires manual steps; operations worries about data loss or system outages.

### 6.1. Current-State CAF Assessment

| Theme | Observation | Short-Term Goal |
|---|---|---|
| Learn | Two developers know containers; no one has practiced database recovery | Practice Cloud Run, Cloud SQL, Logging; test restores |
| Lead | Budget is sponsored, but operational ownership is unclear | Assign product owner, platform owner, security owner, and cutover approver |
| Scale | VMs, network configs, and releases are managed manually | Create IaC configs and a deployment pipeline for staging |
| Secure | Shared accounts and secrets stored in config files | Separate IAM/service accounts, adopt Secret Manager, restrict network paths |

The critical bottleneck is not necessarily VM capacity. Even if new machines run faster, **release and recovery workflows** still block business goals.

### 6.2. Conditional Target Design

- **Organization/folder/project:** separate staging and production projects, assigning owners, billing, and appropriate access policies.
- **Frontend/API:** evaluate moving to Cloud Run if the app can be containerized without local state; keep Compute Engine in mind if OS constraints require VMs.
- **PostgreSQL:** verify version, extensions, workload profile, required features, and connection needs before selecting Cloud SQL; data plan must include consistency checks and rollback.
- **Product images:** evaluate Cloud Storage, migrate data, and define appropriate access permissions and caching.
- **Networking/security:** design app-to-database connectivity, enforce least-privilege IAM, Secret Manager, egress controls, and audit logging per actual requirements.
- **Release/operations:** pipeline with tests and production approval gate, error/latency observability, alerts routed to on-call staff, backups, and recovery drills.

This is a **hypothetical design for learning**, not a production-ready architecture until load testing, compatibility checks, security reviews, and compliance requirements are completed.

### 6.3. Organizing Waves

| Wave | Activities | Exit Criteria |
|---|---|---|
| **Pilot** | Set up staging project; deploy sample version, configure IAM/logging and pipeline | App runs, logs are traceable, owners are assigned |
| **Data and integration** | Test connectivity, migrate a suitable data copy, and rehearse restores | Data matches, backups restore cleanly, downtime bounds are known |
| **Controlled production** | Shift traffic per plan, monitor closely, keep rollback ready | Operational and business metrics meet approved thresholds |
| **Scale out** | Turn lessons into templates; migrate subsequent workloads | Proven reuse, costs and risks actively tracked |

### 6.4. How to Measure Outcomes?

Instead of reporting only “migrated 5 VMs,” the team tracks:

| Goal | Metrics | How to Use |
|---|---|---|
| Faster releases | Deployment frequency, lead time from merge to production | Compare before/after and check release quality |
| Safer releases | Change failure rate, time to recover after incidents | Identify process flaws, improve runbooks and rollbacks |
| User reliability | Request success rate, latency percentiles, SLOs | Tune alerts and prioritize improvements |
| Cost control | Cost per workload/order, budget variance, utilization trends | Drive rightsizing, autoscaling, and capacity planning |
| System protection | Overly broad permissions remediated, restore drill pass rate | Measure Secure progress with concrete evidence |

Target values must be set by the business from its **baseline** and service requirements. No single SLO, budget, or migration timeline fits every application.

## 7. 90-Day Adoption Plan Template

This is an **illustrative execution schedule**, not a standard Google Cloud timeline. Systems with heavy dependencies may take significantly longer for assessment, security hardening, and migration.

| Timeframe | Deliverables | Primary Owners |
|---|---|---|
| **Days 1–15** | Business brief, scope, workload inventory, dependency map, CAF assessment, baseline, and risks | Product owner, architect, operations, security |
| **Days 16–35** | Landing zone, IAM/VPC, logging, billing/budgets, IaC, per-workload strategy, rollback plan | Platform/cloud team with security and finance |
| **Days 36–60** | Complete pilot, data and recovery tests, dashboards/alerts, runbooks, outcome review | Application and operations teams |
| **Days 61–75** | Production rollout or Wave 1 if acceptance criteria pass | Product owner makes go/no-go decision with stakeholders |
| **Days 76–90** | Optimization, cost review, incident retrospective, update standard templates, reassess CAF | Platform, SRE/operations, finance, security |

Attach **stage-gate conditions** to each timeframe: verified security and rollback evidence before production; empirical measurements before cost or performance tuning. Go/no-go decision authority must be established before cutover.

## 8. Common Mistakes

**Counting only migrated resources.** Workloads running in the cloud do not prove operational maturity. Measure user experience, reliability, delivery speed, risk, and cost.

**Treating Secure as the final step.** If shared accounts, open networks, and hardcoded secrets persist from the pilot, fixing them in production becomes much harder. Design IAM, logging, and data classification from day one.

**Picking GKE for every application.** Kubernetes provides powerful orchestration, but carries a learning and operational tax. Choose services based on requirements and capability, and validate with a pilot.

**Ignoring dependencies and rollback capability.** An application might run fine yet fail to reach a payment gateway or lose database sync during cutover. Build dependency maps, data plans, recovery tests, and go/no-go criteria.

**Optimizing on unit infrastructure price alone.** Lower VM unit cost does not guarantee lower total cost if operational toil, downtime, or risk increases. Compare **TCO** and business value alongside service pricing.

**Forcing every CAF theme to the same level.** Targets for training, security, automation, and leadership often vary by scope. Prioritize the gaps with the largest impact on outcomes.

## 9. Applied Exercise

An internal team plans to move a staff scheduling application to Google Cloud. The app has a Java API, PostgreSQL, roughly a few hundred users, daily backup requirements, integration with the company's identity provider, and no release pipeline yet.

**Practice tasks:**

1. Build a **Learn, Lead, Scale, Secure** table with current-state evidence, maturity level, and three-month targets.
2. Choose an initial deployment option among Compute Engine, Cloud Run, or GKE; justify it using application traits and team skills.
3. List at least five landing zone components required before running in production.
4. Design a pilot with success criteria, data tests, a rollback plan, and a designated decision maker.
5. Propose three metrics to evaluate cloud adoption success **after** deployment.

**Self-check hint:** A strong answer clearly explains *why the service was chosen*, *who owns each risk*, *what evidence permits cutover*, and *how improvement is measured*. There is no single right compute answer when load figures, platform constraints, and organizational limits are still unspecified.

## 10. Takeaways and References

- **CAF** answers the question of **organizational readiness**, across four themes (**Learn, Lead, Scale, Secure**) and three maturity levels (**Tactical, Strategic, Transformational**).
- **Assess → Plan → Deploy → Optimize** is Google Cloud's migration execution workflow, repeatable across waves; it is distinct from CAF's three maturity levels.
- Cloud adoption success is measured by **business value, security, operability, and continuous improvement**, alongside cloud service usage.

Official sources for deeper reading:

1. [Google Cloud Adoption Framework](https://cloud.google.com/adoption-framework) — the four themes of the cloud adoption framework.
2. [Migrate to Google Cloud: Get started](https://docs.cloud.google.com/architecture/migration-to-gcp-getting-started) — the three maturity levels and the Assess, Plan, Deploy, Optimize phases.
3. [Migrate to Google Cloud: Assess and discover your workloads](https://docs.cloud.google.com/architecture/migration-to-gcp-assessing-and-discovering-your-workloads) — inventory, dependencies, TCO, and migration readiness.
4. [Migration Center: About migration planning](https://docs.cloud.google.com/migration-center/docs/migration-planning-overview) — landing zones, grouping workloads into waves, and risk management.
