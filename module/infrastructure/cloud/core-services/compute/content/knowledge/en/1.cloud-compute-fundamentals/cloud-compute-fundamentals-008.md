# Process for Selecting a Compute Platform Based on Workload Requirements

## 1. Why Select a Compute Platform Using a Structured Process?

A cloud workload can be deployed using virtual machines (VMs), containers, managed container platforms, or serverless services. Each model offers a different level of control, operational responsibility, and pricing structure. Choosing a model solely based on technology popularity often leads to one of two outcomes: the system lacks required control, or the team ends up operating more components than the workload actually demands.

Compute decisions must start from workload characteristics and business requirements. A continuous transaction-processing service may require steady capacity, low latency, and explicit recovery capabilities. An image-processing task that runs only upon events fits an on-demand execution model. A legacy application dependent on a specific OS or software configuration may require VMs initially. No single model fits every scenario.

Within the scope of **cloud compute fundamentals**, the selection process must simultaneously evaluate execution model, CPU, memory, networking, security, deployment, scaling, availability, and operating costs. The final output is not merely the name of a cloud service; it is an architectural decision backed by rationale, assumptions, limits, and validation methods.

After this lesson, learners will be able to:

- Gather technical and business requirements for a workload before selecting compute.
- Compare VMs, containers, and serverless across control, scalability, operations, and cost.
- Estimate CPU, memory, and networking requirements based on realistic loads.
- Make selections accounting for security, deployment, availability, and recoverability.
- Validate selections through load testing, measurements, and cost evaluation.

## 2. Start with a Workload Profile

Before comparing services, describe the workload. A concise profile backed by metrics is far more useful than a wishlist of technologies.

### 2.1. Identify Role and Criticality

Clarify what function the workload serves: transaction API, website, background processing, data analytics, scheduled job, or legacy system component. Determine the business impact if the service slows down or stops. Metrics such as uptime targets, Recovery Time Objective (RTO), Recovery Point Objective (RPO), and target response time directly shape compute design.

For instance, an internal report-generation job may tolerate rerunning upon failure. A payment-confirmation service requires tighter control over latency, availability, duplicate handling, and recoverability. Two workloads with similar CPU profiles may still require different platforms due to differing operational requirements.

### 2.2. Describe the Load Shape

Record average load, peak load, peak duration, and hourly or seasonal variability. Distinguish the following load shapes:

| Load Shape | Characteristics | Impact on Selection |
|---|---|---|
| Steady, always-on | Relatively uniform demand over long periods | Always-on VMs or containers can be easy to budget; compare actual usage against provisioned capacity |
| Periodic | Rises and falls by hour, day, or processing schedule | Needs ability to scale instance counts up/down and scheduled capacity adjustments |
| Bursty / spiky | Rapid, hard-to-predict load surges | Must test scale-out speed, quota limits, queues, and overload resilience before scaling catches up |
| Event-driven | Occurs only when messages, files, or events arrive | Functions or serverless containers can cut idle capacity and simplify operations |
| Batch | Processes a finite unit of work and exits | Can use container workers, ephemeral VMs, or batch services; account for completion deadlines and retryability |

Do not describe load using requests per second alone. Also record request sizes, processing times, concurrent tasks, error rates, open connections, and read/write data volumes. An API receiving few requests where each request processes large payloads can consume more memory and I/O than a high-traffic API doing lightweight work.

### 2.3. Identify Execution Characteristics

Answer the following questions:

- Does the application run continuously or only when triggered?
- Must processes maintain in-memory state between invocations?
- How long can a single task run? Are there execution duration limits to watch?
- Does the application require a specific OS, native libraries, CPU architecture, kernel access, or specialized hardware?
- Can the application be packaged as a container image and run consistently across environments?
- Can the workload be split into independent units that scale separately, or must the whole application scale together?

Long-lived business state should be stored in databases, object storage, or appropriate storage systems. Keeping state in a single instance's memory complicates replacing, scaling, or restarting instances. Nevertheless, some workloads still require local memory or long-lived sessions; clearly document why and how instance replacement is handled.

### 2.4. Identify Dependencies and Constraints

List databases, message brokers, filesystems, external services, libraries, protocols, and data locations the workload must access. Record requirements for private connectivity, network latency, bandwidth, static IP addresses, deployment regions, data sovereignty, and portability across environments.

Constraints can also come from the team: Kubernetes operational skills, on-call capacity, OS patching workflows, observability tooling, change-approval processes, and budgets. A feature-rich platform that exceeds existing operational capability can raise real-world risk.

## 3. Understand Compute Models Before Comparing

### 3.1. Virtual Machines (VMs)

VMs provide a virtualized computer environment with a dedicated OS. Operators generally retain high control over the OS, software packages, runtime configs, disk sizing, and certain network settings. VMs fit when workloads need a specific OS environment, legacy software, long-running processes, or custom configurations hard to containerize.

A primary advantage of VMs is a familiar operational boundary and broad control. You can choose machine families, vCPUs, memory, storage types, and network configs tailored to the application. VMs are also useful when lifting an existing application to the cloud with minimal source-code changes.

In return, the team carries greater responsibility for the guest OS: security updates, configuration, hardening, monitoring, disk space management, service startup, and troubleshooting. Always-on VMs incur charges even when CPU is lightly utilized. If scaling is needed, the system must provision additional VMs, distribute load, bootstrap configurations, and terminate excess instances.

**Consider VMs when:** the application relies heavily on the OS; machine-level control is required; commercial or legacy software is hard to package; the workload runs continuously with established server-admin processes; or a low-change migration step is needed before modernization.

### 3.2. Containers

Containers package an application together with required dependencies into an image for consistent deployment. Containers typically share the host's kernel or container runtime environment, so they are not equivalent to a VM with its own OS. Images standardize build, test, and deployment pipelines while enabling splitting applications into independently releasable and scalable services.

Containers can run directly on a host, on an orchestrator like Kubernetes, or on a managed container service. Operational burden differs markedly across those choices. When self-managing a Kubernetes cluster, teams must also understand and operate nodes, the control plane (if unmanaged), networking, storage, ingress, policies, upgrades, and monitoring. Managed container services offload some infrastructure work, yet applications still require proper design, security, and observability.

Containers fit APIs, workers, microservices, and apps needing consistent deployment environments. They can also run background tasks or batch jobs. To realize these benefits, applications should support environment-based or external configuration, log to standard output, handle shutdown signals, expose readiness checks, and persist long-lived state outside containers.

Common pitfalls include bloated images, secrets embedded in images, running containers with elevated privileges, mutable image tags, missing CPU/memory limits, or lacking base-image update pipelines. Using containers does not automatically make an application secure or scalable.

**Consider containers when:** consistent packaging and releases are needed; multiple independent services or workers exist; application-level runtime control is desired; portability across environments is required; and the team has container operational skills or selects a suitable managed service.

### 3.3. Serverless

Serverless is a model where the cloud provider manages most of the execution infrastructure. Developers focus on handler code, configuration, and event triggers. With Function as a Service (FaaS), a function is typically invoked by HTTP requests, schedules, messages, storage events, or events from other services. The platform provisions execution environments automatically and scales executions with demand.

This model fits event processing, service-to-service integrations, automation tasks, and small APIs with variable loads. Some platforms also provide serverless containers to run container images without managing servers or orchestration clusters. Serverless containers help when you need a container environment or longer runtimes than traditional functions, subject to service-specific limits.

Serverless reduces server administration and can cut costs when workloads do not run continuously. However, evaluate execution time limits, memory, CPU, deployment package sizes, concurrent invocations, startup speed, cold starts, connection limits, and quotas. Costs can climb rapidly if traffic surges or functions make frequent downstream calls. A frequently invoked, long-running function is not automatically cheaper than containers or VMs.

Serverless workloads should favor stateless processing, safe retryability, and deduplication mechanisms when event sources may redeliver. If long execution, multi-step coordination, or complex progress tracking is needed, consider workflow orchestration, container workers, or batch services.

**Consider serverless when:** workloads are event-triggered; runtimes stay within service limits; traffic is spiky or infrequent; processing can be stateless; and operational savings outweigh runtime, observability, or per-invocation cost trade-offs.

### 3.4. Quick Comparison

| Criterion | VM | Container | Serverless |
|---|---|---|---|
| OS control | High | Platform-dependent; typically no separate kernel per container | Low; platform manages execution environment |
| App packaging | Machine and OS configuration | Image containing app and dependencies | Code/function or image depending on service type |
| Operational work | OS admin, patching, config, and machine scaling | Image, runtime, and potentially cluster orchestration | Focused on code, permissions, triggers, and service limits |
| Scaling | Typically by VM or VM group | By container, pod, or service | Typically automatic by request/event and quotas |
| Best-fit loads | Continuous, OS-specific, legacy apps | Long-running services, APIs, workers, microservices | Events, short tasks, or intermittent workloads |
| Things to verify | Low utilization waste, patching, and boot time | Orchestration complexity, resource limits, and image security | Cold starts, timeouts, concurrency, quotas, and per-execution costs |

These categories are not mutually exclusive. One system can use VMs for legacy components, containers for APIs, and serverless for event handling. Choosing per workload or component is usually better than forcing the entire system into one model.

## 4. Compute Platform Selection Process

### Step 1: Translate Requirements into Verifiable Criteria

From the workload profile, extract mandatory criteria and preferred criteria. For example:

- Runtime must support the existing OS or libraries.
- p95 or p99 latency must stay within business thresholds.
- Service must recover within target duration when an instance or availability zone fails.
- Peak load must be handled without exceeding CPU, memory, connection, or quota limits.
- Sensitive data must reside in a private network and be accessible only by authorized workload identities.
- The team must be able to deploy, observe, update, and recover using existing workflows.

Distinguish hard requirements from nice-to-haves. If a candidate violates a hard requirement, eliminate it before scoring. Never let an aggregate score mask a non-negotiable security or availability constraint.

### Step 2: Build a Candidate Shortlist

Create a shortlist of VMs, managed containers, container orchestrators, and serverless options matching the profile. There is no need to evaluate every service from every provider in round one. Eliminate early any options lacking required runtimes, execution durations, data locations, or protocols.

An initial screening flow:

```text
Does the workload require OS, kernel, or specialized software control?
  Yes -> Evaluate VMs first.
  No  -> Can the app be packaged as a container?
            Yes -> Evaluate managed container services.
            No  -> Consider refactoring the app or using VMs.

Is the workload event-triggered, stateless, and within runtime limits?
  Yes -> Evaluate functions/serverless.
  No  -> Favor always-on VMs/containers or batch workers.

Does the team genuinely need and have the capability to run an orchestrator cluster?
  Yes -> May evaluate Kubernetes or equivalent platforms.
  No  -> Favor higher-managed tiers if requirements are met.
```

This flow helps generate a shortlist; it does not replace verifying service limits and testing the workload.

### Step 3: Evaluate CPU and Memory

Select CPU and memory based on application behavior, not merely defaults or legacy environment specs.

**For CPU:** Determine whether the workload is compute-heavy, sequential, or concurrent. Measure CPU utilization, wait times, processing durations, and latency as concurrency rises. A CPU-bound workload usually improves with more CPU capacity or algorithm optimization. An I/O-bound workload may see minimal gain from adding CPUs.

**For memory:** Measure actual usage under normal and peak loads, including heap, caches, buffers, and growth over long runs. Insufficient memory can cause allocation failures, prolonged garbage collection, or platform termination. Allocating excessive memory inflates costs and can hide memory leaks.

When evaluating, examine:

- Consumption at both average and peak loads, not a single point-in-time sample.
- Minimum instances required to meet latency and availability targets.
- CPU/memory caps of the VM, container, or function.
- How the platform allocates CPU when idle or when multiple workloads share nodes.
- Headroom for growth, rolling deployments, and single-instance loss.
- Correlation between rising concurrency and CPU, memory, and connection consumption.

Do not apply one fixed headroom percentage across all applications. Use load tests and production telemetry to size headroom matching volatility and service targets.

### Step 4: Design Networking for Request and Data Paths

Networking affects latency, security, availability, and cost. Map the path from users or event sources to compute, then onward to databases, storage, and dependent services.

Check these areas:

1. **Ingress:** Does the service accept traffic from the Internet, corporate networks, or only internal services? Are load balancers, API gateways, WAF, or edge authentication needed?
2. **Network segmentation:** Does the workload sit in public or private subnets? Which components require public addresses? Can access be restricted via security groups, firewalls, or network policies?
3. **Egress:** How does compute call external services? Are NAT, proxies, private endpoints, or IP allowlists needed? Will outbound traffic generate substantial charges?
4. **Internal connectivity:** Is compute colocated near databases or storage by deployment region? Are encrypted links, private DNS, service discovery, or east-west traffic controls required?
5. **Fault tolerance:** Are network paths, load balancers, and dependencies available across multiple availability zones? Is there any single point of failure that cuts off multiple instances simultaneously?

Placing compute near data usually lowers latency and cross-region transfer traffic. However, placement must simultaneously satisfy data sovereignty, recoverability, and security policies. Never expose admin ports or SSH/RDP to the Internet merely to simplify operations; use controlled, audited administrative access mechanisms.

### Step 5: Assess Security and Responsibility Boundaries

Every compute model offloads some infrastructure work to the provider, yet customer security responsibilities remain. Clarify who owns the OS, base images, runtimes, app code, identities, data, and network configs.

| Control Layer | VM | Container | Serverless |
|---|---|---|---|
| OS and patches | Team typically manages guest OS and patches | Provider manages host; team manages app images/runtimes per platform | Provider manages most OS and base runtimes; team updates code and libraries |
| Workload identity | Assign role/service identity to VM and app | Grant identity to service/pod; avoid embedding keys in images | Grant least-privilege role to function or service |
| Networking | Firewalls, subnets, security groups, and host configs | Add network policies, ingress, and service-to-service permissions | Configure service invocation permissions, ingress, egress, and endpoints |
| Secrets | Use secrets manager; restrict insecure config files and env vars | Inject secrets at runtime; never bake secrets into images | Fetch secrets from secrets manager using workload identity |
| Monitoring and auditing | OS, app, and administrative activity logs | App, runtime, orchestration, and config-change logs | Invocation, error, access permission, and service activity logs |

Enforce least privilege: each workload may read, write, or invoke only required resources. Use workload identities instead of static access keys when supported by the platform. Encrypt data in transit and at rest; manage keys and secrets through dedicated services. Enable audit logs for administrative actions and permission changes.

For VMs, maintain OS patching schedules, config baselines, vulnerability scanning, and failed-machine replacement workflows. For containers, use trusted images, scan images, pin versions or digests, strip unnecessary tools, and run with minimal privileges. For serverless, audit per-function permissions, dependency libraries, public triggers, and potential sensitive data appearing in logs.

### Step 6: Validate Deployment, Scaling, and Availability

A compute option is viable only when it can be deployed and recovered repeatably.

**Deployment:** Standardize configurations using Infrastructure as Code where appropriate; separate environment config from images or code; version artifacts; automate builds, tests, security scans, and releases. Maintain clear rollback or roll-forward strategies. For containers, verify readiness/liveness probes and graceful shutdown. For VMs, standardize machine images and initialization scripts. For serverless, manage versions, trigger configs, and per-environment permissions.

**Scaling:** Select scaling signals tied to true bottlenecks. CPU may fit compute-heavy workloads; queue depth fits message workers; request rate or concurrency fits APIs; latency can serve as a secondary signal. Set min and max limits to protect downstream dependencies and cap costs. Scaling out will not resolve quota ceilings, overloaded databases, or low-concurrency downstream services.

**Availability:** Run multiple instances when needed to eliminate single points of failure; distribute across availability zones per requirements; configure health checks and remove unhealthy instances from traffic rotation. Design apps to handle backoff retries, timeouts, circuit breakers, and duplicate message delivery. For background tasks, use durable queues and dead-letter queues or error-handling workflows. For data, multi-zone compute does not create resilience if the database or storage remains a single point of failure.

**Recoverability:** Define how to rebuild compute from images, configs, and stored data. Test instance replacement, new version rollouts, zone outages, and backup restorations as appropriate. Measure actual recovery times to compare against RTO/RPO.

### Step 7: Calculate Total Cost of Ownership

Do not compare VMs, containers, and serverless solely by unit compute price. Price out the full processing flow and operational engineering labor.

Components typically included in a cost model:

- Always-on compute, on-demand execution duration, and standby headroom.
- Memory, disks, snapshots, image registries, and temporary storage.
- Load balancers, NAT, IP addresses, Internet egress, or cross-region data transfer.
- Logs, metrics, traces, log retention, and alerting.
- Dependent services such as databases, queues, caches, secrets managers, and backups.
- Costs for development, testing, staging, and disaster recovery environments.
- Engineering effort for patching, upgrades, on-call, incident response, and platform administration.

Always-on VMs or containers can yield predictable costs under steady, high-utilization loads. Serverless can save money for sparse or spiky loads, but count invocations, duration, memory, concurrency, and downstream service fees. Kubernetes can optimize shared resource utilization at scale, yet cluster ops cost and complexity must enter the decision.

Evaluate at least three scenarios: average load, peak load, and low load. Add a growth scenario to see when the current choice must be revisited. Use official provider pricing tables and calculators at decision time; prices, quotas, and discount terms vary by region and service tier.

### Step 8: Score and Document the Decision

After eliminating candidates that fail mandatory requirements, a scorecard can clarify trade-offs. The example below uses a 1–5 scale, where 5 is the best fit. Weights must be adjusted to the specific workload.

| Criterion | Illustrative Weight | VM | Managed Container | Serverless |
|---|---:|---:|---:|---:|
| Runtime and dependency fit | 25% |  |  |  |
| Load and latency fit | 20% |  |  |  |
| Security and control | 15% |  |  |  |
| Availability and recovery | 15% |  |  |  |
| Operational effort | 15% |  |  |  |
| Estimated total cost | 10% |  |  |  |

Score based on evidence: service limit documentation, prototypes, benchmark numbers, cost estimates, and team capability. Never assign scores by gut feel. An option with a high total score must still be disqualified if it violates a mandatory requirement.

Record the decision in a brief Architecture Decision Record (ADR) covering: context, requirements, considered options, selected option, rationale, trade-offs, assumptions, risks, mitigations, and review triggers. This helps teams understand why the platform was chosen and avoids rehashing debates when owners change.

## 5. Validate the Choice Through Testing

Never push a decision to production based solely on a comparison table. Run a prototype representing the real request or task path.

A useful validation cycle includes:

1. **Prepare workload:** Use representative test data, request sizes, concurrency levels, and realistic dependencies. Never copy sensitive production data into test environments without proper safeguards.
2. **Measure baseline:** Record p50/p95/p99 latency, throughput, error rate, CPU, memory, I/O, connections, and startup time.
3. **Ramp load in a controlled manner:** Test normal load, peak load, bursts, and sustained load. Observe both scale-out speed and scale-in behavior.
4. **Test failures:** Stop an instance, disrupt a dependency, or inject malformed messages. Verify retries, timeouts, health checks, and recovery.
5. **Measure cost:** Map resource consumption and estimated bills against completed requests or tasks. Calculate cost per unit of useful work.
6. **Document results:** Compare against mandatory criteria, note limits, and decide whether to proceed, tune, or pick another model.

A meaningful measurement ties cost to output. For instance, cost per thousand successful requests or cost per thousand processed images enables fairer comparisons than hourly compute rates when models differ in autoscaling behavior.

## 6. Applied Examples

### Example 1: Legacy Management Application Moving to the Cloud

The application runs continuously and depends on a specific OS version and several host-installed libraries. Source code is hard to change short term; the team already has server administration workflows.

**Initial choice:** VMs are a sensible candidate because they preserve the OS environment and reduce migration scope. Design a VM group behind a load balancer, separate durable data from local disks if the app permits, and manage patches and configs via standard processes. Once stable, evaluate individual components to containerize or gradually replace with managed services.

**Things to verify:** Multi-instance execution capability, session handling, software licensing, backups, patching workflows, and recovery when a VM or availability zone fails.

### Example 2: Mobile Application API

The API releases frequently, can be packaged as an image, runs statelessly, and must scale with traffic. The team wants runtime control and consistent deployments across testing and production.

**Initial choice:** A managed container service is a strong fit. Package the API into an immutable image, configure CPU/memory resources, readiness checks, autoscaling, and load balancing. Use workload identity to access databases or secrets managers. If the team needs complex orchestration policies and has operational expertise, Kubernetes may fit; otherwise, a simpler container platform generally reduces administration overhead.

**Things to verify:** p95/p99 during scale-out, database connection counts, concurrency limits, container startup time, zero-downtime deployments, and rollback capability.

### Example 3: Generating Thumbnails Upon New File Uploads

When users upload images to object storage, the system must generate several image sizes and write results back to storage. Work occurs only when new files arrive, each task is relatively independent, and tasks are retryable.

**Initial choice:** Serverless functions may fit because storage events trigger processing and the platform manages most execution infrastructure. The function needs read access to source files and write access to the right output prefix; memory limits, execution duration, image sizes, and concurrency must be verified. Use task identifiers or deterministic output naming to safely handle duplicate event deliveries.

**Things to verify:** Cold starts, duration limits, file sizes, native image-processing libraries, concurrency quotas, costs during large upload bursts, and failed-event handling. If images are huge or processing exceeds function limits, container workers or batch services may fit better.

## 7. Common Mistakes

- **Choosing by hype:** Adopting Kubernetes or serverless simply because other teams use it. Start from workload requirements and operational cost.
- **Treating containers as automatic scaling:** Containers are only a packaging and execution format. You still need orchestration, health checks, autoscaling, and resource limits.
- **Ignoring state:** Scaling multiple instances while sessions or temp files remain tied to one machine. Define where state lives and how instance replacement works.
- **Measuring only average CPU:** Ignoring memory, I/O, networking, database connections, and peak-load latency. Measure bottlenecks along the entire request path.
- **Scaling compute without protecting dependencies:** Adding instances can overwhelm downstream databases or APIs. Set concurrency caps, connection pools, and backpressure.
- **Forgetting network and observability costs:** Logs, NAT, cross-region data transfers, and load balancers can generate major expenses.
- **Assuming serverless is always cheap:** Steady loads, long execution times, or massive invocation counts can make other models more economical.
- **Skipping recovery testing:** Having multiple instances that all depend on one zone, one shared config, or one single database. Test failures against RTO/RPO targets.
- **Failing to document assumptions:** As traffic, teams, or security needs shift, old decisions may become invalid. ADRs and operational telemetry indicate when to re-evaluate.

## 8. Pre-Decision Sign-Off Checklist

- [ ] Documented workload role, criticality, and load shape.
- [ ] Identified runtime, dependencies, state, execution duration, and data constraints.
- [ ] Separated mandatory requirements from preferred criteria.
- [ ] Compared VMs, containers, and serverless against actual suitability.
- [ ] Measured or estimated CPU, memory, I/O, networking, and concurrency.
- [ ] Designed ingress, egress, network segmentation, and data connectivity.
- [ ] Defined security responsibilities, workload identities, least privilege, secrets, and patching.
- [ ] Defined deployment, rollback, autoscaling, health checks, and recovery mechanisms.
- [ ] Priced out compute, storage, networking, observability, dependencies, and operations.
- [ ] Conducted load and failure testing against explicit acceptance criteria.
- [ ] Recorded decision, trade-offs, assumptions, and review triggers.

## 9. Conclusion

Selecting a compute platform is the process of matching workload characteristics with the level of control and operational responsibility a team can sustain. VMs fit when flexible server environments or compatibility with existing apps are required. Containers fit when consistent packaging, repeatable deployments, and independent service scaling are needed. Serverless fits many event-driven or intermittent workloads when execution limits meet requirements.

A sound decision rests on a workload profile, mandatory criteria, CPU/memory/network design, security controls, deployment and recovery plans, and a total cost model. After deployment, continue monitoring latency, errors, resource usage, and spend to tune configurations or revisit the model as the workload evolves.
