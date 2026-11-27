# Trade-Offs Among Committed, On-Demand, and Interruptible Resources

When deploying workloads on the cloud, an organization often has multiple ways to purchase or provision the same type of compute: pay for actual usage, commit for a term in exchange for discounted pricing, or use spare capacity that the provider can reclaim. Each model trades off something different: flexibility, capacity certainty, interruption exposure, and unit cost.

**Committed/reserved capacity** suits stable, predictable baseline workloads. **On-demand** provides flexibility when rapid scaling is needed or demand is uncertain. **Spot/preemptible** taps into spare capacity at a lower price, provided the workload tolerates resource reclamation. No single model is always cheapest when judged solely by hourly rate; you must factor in utilization, idle time, data transfer fees, operational effort, interruptions, and reserve capacity.

A cost-aware strategy usually combines models. Steady baseline load can be covered by commitments; variable load uses on-demand; and batch jobs, CI jobs, or retryable workers use spot. However, the mix ratio must reflect SLOs, execution duration, checkpointing capability, startup latency, and behavior when capacity disappears. The objective is to lower total cost while preserving business serving capability.

This lesson belongs to the **Cost and Sustainability** section of the cloud architecture module. Its focus is evaluating trade-offs among committed, on-demand, and interruptible resources to choose a model aligned with workload characteristics, reliability, scalability, cost, and operations using Well-Architected thinking.

After this lesson, you will be able to:

- Distinguish commitment/reservation, on-demand, and spot/preemptible capacity.
- Evaluate workloads by stability, interruption tolerance, and recovery time.
- Calculate effective cost, utilization, break-even points, and appropriate commitment levels.
- Combine multiple capacity types within an autoscaling architecture.
- Design checkpointing, retries, draining, and interruption handling for spot workloads.
- Avoid overcommitting, underutilization, capacity shortages, and hidden costs.
- Build cost governance, dashboards, budgets, and commitment review processes.

## 1. Three Resource Provisioning Models

Terminology and commercial terms differ across cloud providers and services. Distinguish a **spend/discount commitment** from an **actual capacity reservation**: a pricing commitment does not always guarantee an instance or compute slot can be launched immediately. Before purchasing, read the exact product terms, scope, flexibility, and cancellation/modification conditions.

| Model | Billing Mechanism | Capacity/Availability | Best Suited For |
| --- | --- | --- | --- |
| **Committed / Reserved** | Term or spend/capacity commitment in exchange for a discount | Product-dependent; some reservations guarantee capacity while some commitments only apply discounts | Steady baselines, continuously running or predictable workloads |
| **On-demand** | Pay as you use, no long-term commitment | Flexible, though still subject to quotas, regional capacity, and service limits | Uncertain demand, new applications, short peaks, critical workloads needing flexible capacity |
| **Spot / Preemptible** | Lower price for spare capacity, potentially fluctuating per provider mechanisms | Can be reclaimed when the provider needs capacity; should not be treated as guaranteed capacity | Batch, queue workers, CI, rendering, analytics, and retryable/checkpointed workloads |

### 1.1. Commitments and Reservations

Committed-use discounts or savings commitments typically exchange a commitment on spend, resource type, region, or term for lower rates. Certain reservation products also bind to specific capacity or guarantee launchability within a defined scope. These models are not equivalent:

- A commitment may lower unit prices for eligible usage without guaranteeing capacity when needed.
- A capacity reservation may hold capacity in a zone/region without automatically providing a discount.
- Reserved instances or similar offerings may combine pricing benefits and capacity terms depending on the service.
- Commitments may apply only to a specific family, platform, region, account, or usage type.

Verify terms regarding size flexibility, exchanges, cancellations, payment options, unused commitments, and cross-account sharing before deciding.

### 1.2. On-Demand

On-demand lets you start and stop resources as needed without long commitments. It is typically the right choice for experimentation, workloads without an established baseline, short peaks, and reserve capacity.

On-demand does not mean "unlimited capacity is always available." Quotas, service limits, regional capacity constraints, API rate limits, and provisioning latency still apply. Architectures must monitor quotas and plan for scenarios where immediate scale-out fails.

### 1.3. Spot or Preemptible

Providers offer spare capacity at attractive prices while retaining the right to reclaim it under service terms. Warning lead times, interruption signaling mechanisms, and permitted workload types vary by provider and service. Never assume every offering provides the same advance notice window.

Workloads must be designed to:

- Stop cleanly at any moment according to service semantics.
- Persist progress or perform idempotent units of work.
- Detect interruption signals and stop accepting new work.
- Finish/flush what is safe within any notice window provided.
- Allow jobs to be retried or resumed on replacement capacity.

Spot works best when losing a worker never causes data loss or corrupts final outcomes.

## 2. Evaluating Workloads Before Choosing a Model

Do not pick spot purely for low price, nor buy commitments purely for a headline discount. Start from the workload profile.

### Attributes to Measure

| Attribute | Question |
| --- | --- |
| Baseline utilization | What minimum capacity is required during off-peak hours? |
| Peak profile | How high above baseline do peaks rise, how long do they last, and when do they occur? |
| Predictability | Can demand be forecast by hour, day, season, or business calendar? |
| Criticality | Does losing capacity cause revenue loss, data loss, or SLO breaches? |
| Interruption tolerance | Can work pause, retry, checkpoint, or move hosts? |
| Startup time | How long do provisioning, image pull, warm-up, and readiness take? |
| Statefulness | Does the workload store state on local disk/memory or externalize state? |
| Runtime duration | Do jobs run for seconds, minutes, or many hours? |
| Scaling response | Can it scale rapidly with demand or must capacity stay always ready? |
| Portability | Can the workload run across multiple instance types, zones, or regions? |
| Dependencies | Is it constrained by licenses, GPUs, local storage, or network locality? |
| Cost of delay | What is the impact if a job is delayed by 15 minutes or an hour? |

### Suitability Matrix

| Workload | Committed | On-Demand | Spot/Preemptible |
| --- | --- | --- | --- |
| Production API with steady baseline | Good for baseline if committed to the right scope | Good for burst/headroom | Use only with redundancy and interruption tolerance |
| Primary/stateful database | May fit baseline/discounts depending on product | Usable for controlled flexible capacity | Usually unsuitable if interruption disrupts service or loses state |
| Replaceable read replica | Suitable if load is steady | Suitable for flexible scaling | Can consider if failover/rebuild is proven |
| Batch analytics | Use for steadily running pipelines | Use for tight deadlines and non-deferrable jobs | Very suitable with solid checkpointing/retries |
| CI build/test | Usually does not require full commitment | Good for time-critical pipelines | Suits retryable jobs with external caches/artifacts |
| Video/render/encoding | Possible for steady background queues | Use for urgent deadlines | Suits chunked jobs with saved checkpoints |
| Queue consumer | Usable for baseline throughput | Use when backlogs grow | Suitable if consumers support ack/retry/idempotency |
| Interactive low-latency | Possible for baseline | Suits peaks and critical capacity | Use only as supplemental capacity that can vanish immediately |

This matrix is a starting guide. A single workload can use multiple capacity types simultaneously; decisions must examine SLOs and real recovery mechanisms.

## 3. Separating Baseline, Burst, and Interruptible Work

A practical strategy groups capacity by role:

- **Baseline:** capacity always needed to serve baseline load and minimum requirements.
- **Burst/headroom:** extra capacity to absorb peaks, growth, or node/zone failures.
- **Interruptible pool:** capacity that can be lost without breaking business operations.

~~~mermaid
flowchart TD
    DEMAND["Observed demand"] --> BASE["Stable baseline"]
    DEMAND --> BURST["Variable burst"]
    DEMAND --> FLEX["Deferrable / retryable work"]
    BASE --> COMMIT["Committed or reserved capacity"]
    BURST --> OD["On-demand capacity"]
    FLEX --> SPOT["Spot / preemptible pool"]
    COMMIT --> SERVICE["Application / workers"]
    OD --> SERVICE
    SPOT --> WORKER["Interruptible workers"]
~~~

### Do Not Put the Entire Baseline on Spot

If all API serving capacity sits on spot, a wave of reclamations can slash capacity right during high load. Autoscalers need time to provision replacements and cannot guarantee instant fallback capacity.

Baseline capacity should cover load required under normal conditions and failure scenarios. Burst can use on-demand or reserved capacity. Spot should serve work that can be interrupted while keeping core SLOs intact.

### Headroom Must Account for Failures

Do not size capacity only for normal peaks. Simulate:

- A zone losing capacity.
- A batch of spot instances reclaimed simultaneously.
- An instance family running out of capacity.
- Autoscalers or quotas failing to add resources in time.
- Queue backlogs growing faster than processing rate.

If remaining capacity cannot serve core load, implement admission control, load shedding, or reserve capacity on a more reliable model.

## 4. Calculating Effective Cost and Break-Even

Hourly list prices do not capture full cost. Include utilization, idle capacity, unutilized commitments, and operational overhead.

### 4.1. On-Demand Cost

Simple model:

\[
C_{OD}=H \times P_{OD} \times U
\]

Where:

- \(H\): hours in the period.
- \(P_{OD}\): on-demand unit rate.
- \(U\): average capacity units used; for one always-on unit, \(U=1\).

With autoscaling, compute using actual total resource-hours rather than multiplying peak capacity across the entire period.

### 4.2. Commitments and Utilization

Suppose one commitment equals one capacity unit per hour at fixed cost \(P_C\). The workload uses an average of \(u\) units over \(H\) hours, with usage eligible for the discount.

Committed spend and on-demand overage can be modeled as:

\[
C_C=H \times P_C + \max(0,U-u)\times H \times P_{OD}
\]

In practice, billing mechanics may depend on spend/hour, family, instance normalization, account sharing, or usage coverage; this formula is a simplified model for understanding utilization and unused commitments.

Commitment utilization rate:

\[
Utilization=\frac{\text{Eligible usage covered}}{\text{Committed amount}}
\]

Coverage differs from utilization: coverage shows what share of eligible usage is covered by commitments; utilization shows what share of the commitment was used. Monitor both to avoid over-buying or committing to the wrong scope.

### 4.3. Break-Even

For one capacity unit running \(H\) hours, if the commitment has an effective hourly rate \(P_C\) and on-demand is \(P_{OD}\), the commitment yields direct price savings when:

\[
U \times H \times P_{OD} > H \times P_C
\]

Where \(U\) is the fraction of time the capacity has eligible usage able to consume the discount. Simple utilization threshold:

\[
U_{BE}=\frac{P_C}{P_{OD}}
\]

If a commitment lacks a fixed per-unit capacity fee or uses different terms, adapt the formula to the real pricing model. Include the opportunity cost of being unable to scale down the commitment if demand drops.

### 4.4. Illustrative Example

Suppose a workload needs one steady compute unit for 730 hours/month. On-demand costs 1.00 currency unit/hour; commitment equals 0.65 units/hour, excluding ancillary charges.

| Option | Illustrative Monthly Cost |
| --- | ---: |
| On-demand, running all 730 hours | 730 |
| Commitment, running full term and covered | 474.5 |
| Commitment, workload only active 60% | 474.5 for commitment, plus uncovered portion under applicable usage model |

The final case highlights the difference between a fixed capacity commitment and a discount on actual usage: if the workload runs only 60% of the time while you still pay the full-term commitment, the idle portion does not vanish. In that scenario, the commitment only pays off if other workloads can share the benefit or total eligible usage is high enough. Read the billing model before plugging in numbers.

### Total Cost of Ownership (TCO)

TCO should include:

- Compute/storage/network usage.
- Unused commitments and upfront fees.
- Data transfer, egress, and cross-zone/cross-region traffic.
- Image registries, artifact/caches, and backups.
- Monitoring, schedulers, autoscalers, and orchestration.
- Retries, duplicate work, and job re-execution time.
- Licenses, support, and reservation management.
- Engineering effort to handle interruptions, migrations, and capacity planning.
- Downtime costs, missed deadlines, and lost business opportunities.

A significantly cheaper spot instance can still drive higher total cost if jobs are repeatedly reclaimed, recompute from scratch, or demand heavy operational effort.

## 5. Right-Sizing Commitment Purchases

Commitments reduce unit prices when workloads are sufficiently steady, but overbuying leaves the organization paying for unusable capacity.

### Sizing Process

1. Collect hourly/daily usage across a representative window, including peak seasons.
2. Separate steady baselines from variable workloads.
3. Exclude short spikes or experiments unrepresentative of long-term demand.
4. Check growth forecasts, migrations, and retirement plans.
5. Identify eligible usage by region/family/service/account.
6. Start with a conservative commitment level.
7. Monitor utilization, coverage, unused commitments, and forecasts.
8. Review before renewing or purchasing additional commitments.

### Choosing Term and Payment Options

Longer terms often offer deeper discounts at the expense of higher risk if architectures or demand change. Upfront, partial, or periodic payment options affect cash flow and net savings. Evaluate via NPV/cash flow and adaptability, not discount percentage alone.

### Avoid Overcommitting

Do not buy commitments based on:

- Short-term peak demand.
- Unvalidated growth forecasts.
- Workloads scheduled for retirement or migration.
- Instance families/regions likely to change.
- Usage already covered by existing commitments.

Avoid counting the same usage toward multiple discount plans. Cost allocation and ownership must clarify which workloads count toward which commitments.

### Flexibility and Portability

Broader family/region commitments reduce risk when resizing or shifting accounts, though discounts, scope, and capacity guarantees may differ. Architectural portability helps switch instance types or regions, but never assume every license, storage type, accelerator, and network locality is interchangeable.

## 6. Managing Spot/Preemptible Interruptions

Spot is viable only when interruption is a designed-for state, not a rare surprise.

### Interruption Lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> RUNNING
    RUNNING --> INTERRUPT_NOTICE: Provider signal or capacity reclaim
    INTERRUPT_NOTICE --> DRAINING: Stop new work
    DRAINING --> CHECKPOINT: Save progress and flush state
    CHECKPOINT --> TERMINATED: Instance reclaimed
    RUNNING --> TERMINATED: Abrupt loss / no usable notice
    TERMINATED --> REQUEUED: Work lease expires
    REQUEUED --> RUNNING: Replacement worker starts
~~~

Advance notice before interruption is best-effort per service. Designs must survive even zero-notice abrupt termination.

### 6.1. Detecting Interruptions

- Listen for interruption notices/events using provider mechanisms.
- Use appropriate lifecycle hooks or instance metadata endpoints.
- Agents/workers must poll or watch signals during execution.
- Notify the control plane over a channel with short timeouts.
- If no notice arrives, lease timeouts or heartbeats must still detect lost workers.

### 6.2. Stopping Work and Draining

Upon receiving a signal:

1. Stop accepting new jobs.
2. Mark the worker as draining/unavailable in the scheduler.
3. Finish brief in-flight work if sufficient time remains and it is safe.
4. Persist checkpoints or intermediate results durably.
5. Release leases/locks cleanly if possible.
6. Terminate the process and let orchestration replace capacity.

Never attempt to finish work past the notice window. If a job cannot complete in time, let the lease expire and retry from the latest checkpoint.

### 6.3. Checkpointing and Idempotency

Checkpoints must live outside the instance—such as durable object storage or a database—with versioning and checksums. Workers must:

- Write checkpoints at small units of work.
- Commit output before marking a checkpoint complete.
- Use idempotency keys/job IDs.
- Detect stale or overwritten checkpoints.
- Reconcile outputs if a worker dies after writing results but before acknowledging.
- Maintain checkpoint retention and cleanup.

Never store progress solely on a spot node's ephemeral disk. Instance reclamation can destroy local disks and caches.

### 6.4. Retries and Duplicates

At-least-once processing can re-run a job. Consumers must be idempotent or use deduplication/transactional commits. Use backoff and retry caps; route poison jobs to a DLQ or manual review. Never let a perpetually failing job burn capacity indefinitely.

## 7. Designing Workloads for Interruptible Capacity

Spot works best when workloads are decomposed into small, stateless units portable across machine types.

### Job Decomposition

- Split large batches into independent tasks or partitions.
- Keep each task short enough to limit lost work.
- Store inputs/outputs on durable storage.
- Use a scheduler that redistributes tasks on lost heartbeats.
- Optionally allow duplicate execution across workers while committing only one valid result.

### Stateless Workers

Externalize sessions, job state, and metadata outside the instance. Workers hold only transient working state and are replaceable. Local caches are strictly optimizations; cache misses must never break correctness.

### Instance Flexibility

Allow multiple instance sizes/families that satisfy CPU, memory, network, storage, and architecture requirements. Verify:

- Which CPU architectures the binary/container supports.
- Minimum RAM and ephemeral storage.
- Network throughput and ENI/device limits.
- GPU/accelerator dependencies.
- Licenses or host bindings.
- Startup/warm-up behavior and image availability.

A diversified pool reduces dependence on a single capacity pool, but must be benchmarked to avoid picking instances with poor throughput or cost per work unit.

### Queue-Based Worker Pool

~~~mermaid
flowchart TD
    PRODUCER["Job producer"] --> Q[("Durable queue")]
    Q --> SCHED["Scheduler / capacity controller"]
    SCHED --> OD["On-demand workers"]
    SCHED --> SPOT["Spot worker pool"]
    OD --> RESULT[("Durable result store")]
    SPOT --> RESULT
    SPOT -. "Interruption / lost heartbeat" .-> RETRY["Lease expiry / retry policy"]
    RETRY --> Q
    RESULT --> CONSUMER["Result consumer"]
~~~

The scheduler can favor spot for backlogs without tight deadlines, while keeping a baseline of on-demand capacity for critical jobs or low spot supply.

## 8. Autoscaling Across Multiple Capacity Types

Autoscaling must decide both when to scale capacity up/down and which capacity types are permitted to accept which workloads.

### Scaling Signals

- Queue depth and oldest job age.
- Request concurrency and latency.
- CPU/memory/network utilization.
- Worker throughput and job duration.
- Spot interruption rates and capacity availability.
- On-demand quotas and provisioning time.

Low CPU does not necessarily mean idle workers; they may be blocked on I/O or downstream quotas. Use metrics reflecting true demand.

### Mixed Capacity Policy

Illustrative policy:

1. Keep an on-demand or reserved baseline sufficient for minimum SLA.
2. As queues grow, prefer adding spot capacity for retryable jobs.
3. If spot is unavailable and backlogs threaten deadlines, expand on-demand within budget.
4. When demand drops, drain spot first or scale in per cost/risk policy.
5. Never shrink the baseline below failure-survival thresholds.

### Scale-Out Lag

Autoscalers take time to detect demand, call APIs, wait for capacity, boot instances, pull images, load secrets, and pass readiness checks. If jobs require immediate processing, relying purely on reactive spot/on-demand scale-out may fall short. Warm pools or headroom may be required for latency SLOs.

### Scale-In

Scale-in must respect active jobs, leases, draining, checkpoints, and consumer groups. Never terminate a worker committing side effects without idempotency/recovery.

## 9. Reliability and SLOs with Flexible Capacity

Low prices must never silently erode SLOs. Explicitly define what happens when spot capacity is reclaimed.

### Separating SLOs by Workload

| Workload | Suggested SLO | Can Use Spot? |
| --- | --- | --- |
| Public API requests | Strict latency/availability | Only as supplemental capacity with redundancy and fallback |
| Batch data processing | Job completion within a time window | Yes, if checkpointing/retries meet deadlines |
| CI tests | Results completed within pipeline SLA | Yes, if jobs are retryable and artifacts are stored durably |
| Video rendering | Total job finished before deadline | Yes, if rendering is chunked and checkpointed |
| Offline ML training | Training finishes within budget/time | Yes, if model/optimizer checkpoints resume cleanly |
| Stateful database primary | RPO/RTO and consistency | Usually do not use spot for the primary writer |

### Failure Capacity Reserve

When sizing the baseline, account for:

- Loss of a node or zone.
- Simultaneous reclamation of a spot pool.
- Throttled or capped on-demand provisioning.
- Extra load from worker retries.
- Queue backlogs requiring drain after an outage.

Without sufficient headroom, you will need admission shedding, priority scheduling for critical jobs, relaxed deadlines, or costlier reserve capacity.

### Interruption Budget

Track interruption rates, retry rates, lost work, job completion times, and cost per successful job. A pool with a cheap hourly rate yet frequent interruptions can be inefficient overall. Evaluate by **cost per completed outcome**, not cost per instance-hour alone.

## 10. Hidden Costs of Spot and Commitments

### Spot Hidden Costs

- Lost work requiring re-execution.
- Checkpoint writes/reads and storage.
- Queues, schedulers, and orchestration overhead.
- Engineering time spent building resilience.
- On-demand fallback when spot supply tightens.
- Provisioning churn, image pulls, and cache warm-up.
- Duplicate results, idempotency stores, and reconciliation.

### Commitment Hidden Costs

- Unused commitments when demand falls.
- Mismatches across region, family, account, or usage type.
- Lost flexibility during migrations or architecture changes.
- Prepayments and cost of capital.
- Being locked into one resource type even when newer options are more efficient.
- Contractual modification or cancellation fees/restrictions.

### On-Demand Hidden Costs

- Higher unit rates over long durations.
- Unchecked spend without budgets or autoscaling bounds.
- Quota and capacity constraints causing shortages at peak.
- Temporary resources left behind without cleanup.

### Unit Economics

Choose metrics that reflect delivered value:

- Cost per successful request.
- Cost per processed record.
- Cost per completed job.
- Cost per GB transformed.
- Cost per training run/converged model.
- Cost per tenant or business transaction.

When comparing on-demand against spot, include retries and rework. A fast spot worker that gets reclaimed repeatedly can cost more than a stable on-demand worker.

## 11. Capacity Planning and Forecasting

Commitments should rest on evidence-backed baselines, not guesswork. Spot should rest on flexible workloads and diversified supply.

### Data to Collect

- Resource-hours by service, region, family, and environment.
- Hourly/daily p50/p95/p99 utilization.
- Peak/burst patterns and seasonality.
- Queue throughput, backlog, and job age.
- Spot interruption rates and replacement times.
- On-demand provisioning success and latency.
- Commitment utilization/coverage and unused spend.
- Growth forecasts and migration roadmaps.

### Forecast Scenarios

Build at least three scenarios:

| Scenario | Demand | Decision |
| --- | --- | --- |
| Conservative | Demand below forecast | Keep commitments cautious, avoid lock-in |
| Expected | Projected demand | Commit part of the baseline |
| Growth/peak | Rapid growth or high season | Use on-demand/headroom; revisit commitments once patterns stabilize |

Never commit against unvalidated growth forecasts. Layer commitments incrementally as actual usage confirms a new baseline.

### Forecast Error

Measure variance between forecast and actuals. If forecasts consistently overshoot actuals, the organization may be overcommitting; if far too low, it may miss discounts or hit capacity shortages. Include forecast accuracy in monthly/quarterly reviews.

## 12. Cost Governance and FinOps Controls

Capacity choices must tie into financial and technical accountability.

### Ownership and Allocation

- Assign an owner and cost center to every workload.
- Tag by service, environment, team, product, and data classification as appropriate.
- Allocate shared commitments by usage or transparent rules.
- Separate production, staging, dev/test, and sandbox environments.
- Link budgets and alerts to owners empowered to act.

### Guardrails

- Explicit autoscaling minimums/maximums.
- Quotas and instance family allowlists.
- Spot percentage caps by workload criticality.
- Commitment purchase approvals based on spend and term.
- Budget alerts when utilization/coverage drifts.
- Cleanup policies for ephemeral environments.
- Cost anomaly detection by service/team/region.

### Showback and Chargeback

Showback shares cost visibility so teams understand usage; chargeback allocates costs to budgets or cost centers. Both require consistent rules covering shared platforms, commitment discounts, idle capacity, and network charges.

Never evaluate teams solely on low spend. Evaluate cost alongside SLOs, throughput, reliability, and business value.

## 13. Sustainability and Resource Efficiency

Using capacity efficiently reduces both cost and environmental impact, yet cutting capacity to the point of constant retries or significantly longer runtimes backfires.

### Practices

- Right-size based on CPU, memory, network, and I/O profiles.
- Increase utilization with controls to avoid overprovisioning.
- Scale down idle resources outside business hours or batch schedules.
- Select efficient instance generations/architectures when workloads are compatible.
- Place compute near data to cut network transfer.
- Eliminate duplicate compute from unnecessary retries or pipeline reruns.
- Use spot for interruptible workloads when total energy and time-to-completion remain reasonable.
- Archive or expire temporary resources and data on lifecycle schedules.

### Efficiency per Unit of Work

Track energy/carbon metrics where providers and tools supply trustworthy data. Otherwise, use proxies such as compute-hours, CPU utilization, GB transferred, and retry counts. Avoid claiming specific carbon reductions solely from switching to spot without measurement methodology.

### Trade-Offs

An undersized worker may run longer, add overhead, and incur repeated startups; an oversized worker may finish quickly while leaving capacity idle. Benchmark cost, time, and energy per unit of output.

## 14. Design Example: E-Commerce Platform

**Hypothetical scenario:** A platform runs a public API, transactional database, search indexing, image processing, recommendation training, and nightly analytics. The API needs steady latency; the database holds critical state; image processing and analytics tolerate bounded delays; and recommendation training uses checkpoints. This is a simulated exercise.

### Capacity Grouping

| Workload | Primary Capacity | Supplemental Capacity | Rationale |
| --- | --- | --- | --- |
| Production API | Reserved/committed baseline and on-demand headroom | Do not rely on spot for mandatory serving | Latency/availability SLOs |
| Primary database | Stable capacity per service tier | Reservation if semantics fit | Stateful and requires writer availability |
| Search read nodes | Commitment for baseline | On-demand or rebuildable spot replicas | Replicas are rebuildable, though query SLOs must hold |
| Image processing | Spot workers | On-demand when deadline backlog rises | Independent jobs, durable output storage |
| Nightly analytics | Spot pool | On-demand for critical deadlines | Batch supports retries/checkpointing |
| Model training | Diversified spot instances | On-demand fallback near deadlines | Model/optimizer checkpoints |

### Architecture

~~~mermaid
flowchart TD
    USER["Customer traffic"] --> API["API baseline pool"]
    API --> DB[("Transactional database")]
    API --> Q[("Durable work queues")]
    Q --> CTRL["Scheduler / autoscaler"]
    CTRL --> BASE["Committed baseline workers"]
    CTRL --> OD["On-demand burst workers"]
    CTRL --> SPOT["Spot interruptible workers"]
    BASE --> STORE[("Object / result store")]
    OD --> STORE
    SPOT --> STORE
    SPOT -. "Interruption" .-> CP["Checkpoint / retry / requeue"]
    CP --> Q
    STORE --> SEARCH["Search indexing / analytics / ML"]
~~~

### Operating Rules

- The API never depends on spot workers to answer requests.
- The transactional database never runs on interruptible capacity.
- Queues persist jobs durably; lost workers trigger lease expiry and job requeuing.
- Image processing stores outputs keyed by job ID so retries do not duplicate artifacts.
- Analytics has deadlines; when backlogs cross thresholds, scale on-demand within budget.
- Model training saves periodic checkpoints and tests resuming after interruptions.
- Dashboards show cost per completed image/job and interruption costs.

### Acceptance Criteria

- The API maintains SLOs during spot pool reclamation.
- No queue-acknowledged jobs are lost.
- Duplicate workers never produce duplicate or corrupted outputs.
- Batch jobs meet deadlines even when spot supply drops under fallback policies.
- Commitment utilization meets approved targets.
- Cost per output includes retries, storage, and orchestration.

## 15. Practice Exercise: Selecting Commitments, On-Demand, and Spot for Cloud Workloads

**Scenario:** A SaaS company operates an API with a steady baseline and hourly peaks, export workers, CI pipelines, nightly batch analytics, and a stateful database. Export and analytics workers are retryable; the API needs stable SLOs; CI jobs must finish before release windows; and the database cannot lose its writer unexpectedly. This is a simulated dataset.

### Tasks

1. **Workload inventory:** profile baseline, peak, predictability, runtime, criticality, and interruption tolerance.
2. **Capacity strategy:** define committed/reserved baseline, on-demand burst, and interruptible spot portions.
3. **Financial model:** compute resource-hours, utilization, coverage, unused commitments, break-even, and cost per successful job.
4. **Commitment decision:** recommend term, scope, payment option, and initial purchase size; state assumptions and sensitivities.
5. **Spot design:** design interruption signals, draining, checkpoints, leases, retries, idempotency, DLQs, and replacement.
6. **Autoscaling:** define queue/latency/concurrency signals, warm pools, min/max bounds, and fallback when spot is unavailable.
7. **Reliability:** simulate spot pool reclamation, zone failures, quota limits, and queue backlogs.
8. **Governance:** define owners/tags/budgets/alerts, commitment reviews, and exception approvals.
9. **Sustainability:** compare compute-hours and cost per unit output; assess wasted rework.

### Test Matrix

| Test | Scenario | Required Evidence |
| --- | --- | --- |
| Stable baseline | Baseline demand runs continuously | Commitment utilization/coverage meets target |
| Low demand | Demand drops longer than projected | Unused commitments detected and forecasts adjusted |
| Peak burst | Sudden traffic surge | On-demand/headroom absorbs or admission policy triggers cleanly |
| Spot reclaim | Group of workers receives interruption | Drain/checkpoint/requeue loses zero jobs |
| Abrupt loss | Spot node disappears with no usable notice | Lease timeout and retries recover work |
| Duplicate execution | Job runs simultaneously on two workers | Idempotency/deduplication preserves correct output |
| Spot shortage | Additional spot capacity unavailable | On-demand fallback or deadline/degradation policy activates |
| Quota limit | On-demand scale-out blocked | Alerts, capacity plan, and admission control operate |
| Queue backlog | Consumers lag behind producers | Oldest-age alert and controlled scaling without overloading downstream |
| Commitment mismatch | Resource family/region changes | Cost coverage drop detected and owner alerted |
| Database failure | Primary requires failover | Writer does not rely on spot; RTO/RPO meet design |
| Cost anomaly | Retries drive up cost per job | Dashboard/anomaly alert catches regression |

### Deliverables

- Workload suitability matrix.
- Baseline/burst/interruptible capacity plan.
- Commitment sizing and financial model.
- Spot interruption/checkpoint/retry architecture.
- Autoscaling policies and quota/headroom strategy.
- SLO, cost per unit output, and sustainability metrics.
- Budget/tag/owner/approval governance.
- Load/failure test plan and ADR documenting trade-offs.

## 16. Evaluation via Well-Architected

| Pillar | Capacity Purchasing Strategy Questions |
| --- | --- |
| **Operational Excellence** | Do usage, commitments, interruptions, forecasts, and workload owners have dashboards, runbooks, and reviews? |
| **Security** | Do spot workers have short-lived, workload-scoped identities, secrets, network, and data access? |
| **Reliability** | Do baseline/headroom survive failures? Are checkpoints, idempotency, queues, retries, and deadlines tested? |
| **Performance Efficiency** | Do instance families/sizes, startup times, scaling lag, and locality meet workload needs? |
| **Cost Optimization** | Are commitment utilization, on-demand burst, spot retries, hidden costs, and unit economics accounted for? |
| **Sustainability** | Are idle capacity and duplicate work minimized without extending runtimes or triggering futile retries? |

## 17. Common Pitfalls

**Buying commitments sized to peak.** Short peaks leave the organization paying for idle capacity most of the time.

**Confusing a discount commitment with a capacity guarantee.** Discounted pricing does not guarantee instances will launch in your target zone.

**Locking into overly long terms while roadmaps are unstable.** Migrations, family shifts, or falling demand can strand commitments.

**Putting APIs or primary databases on spot.** Interruptions can directly impact availability or consistency.

**Assuming spot always gives warning.** Designs must tolerate abrupt instance loss.

**Keeping checkpoints only on local disk.** Progress disappears when the instance is reclaimed.

**Non-idempotent retries.** Re-executed jobs can produce duplicate charges, records, or outputs.

**Running all batch workloads on spot without deadline policies.** Low supply can push backlogs past processing windows.

**Keeping no on-demand fallback.** When spot supply dries up, critical work stalls.

**Ignoring retry and orchestration costs.** Low hourly instance prices distort true cost per output.

**Autoscaling past database capacity.** Adding workers can worsen downstream bottlenecks.

**Failing to track commitment coverage/utilization.** Teams can keep paying for unused commitments unnoticed.

**Judging sustainability by price alone.** Rework, completion duration, and data transfer also drive resource efficiency.

## 18. Pre-Deployment Capacity Strategy Checklist

- [ ] Workload profiles capture baseline, peak, seasonality, criticality, and interruption tolerance.
- [ ] Commitments and capacity reservations are distinguished accurately per service terms.
- [ ] Baseline capacity is derived from actual usage and failure headroom.
- [ ] Commitment scope, term, payment options, sharing, and unused commitments are verified.
- [ ] Forecasts include conservative/expected/growth scenarios and track forecast error.
- [ ] On-demand has quotas, max scaling bounds, and budget guardrails.
- [ ] Spot runs only retryable/checkpointed or safely replaceable workloads.
- [ ] Interruption notices, abrupt losses, draining, and lease recovery are tested.
- [ ] Checkpoints/outputs reside on durable storage with versioning/integrity checks.
- [ ] Jobs implement idempotency, deduplication, retry limits, and DLQs.
- [ ] Mixed capacity policies preserve baseline capacity during spot shortages or zone failures.
- [ ] Autoscaling accounts for provisioning lag, warm-up, downstream quotas, and scale-in draining.
- [ ] Costs include compute, storage, network, retries, orchestration, idle time, and engineering overhead.
- [ ] Cost per successful request/job/output is tracked.
- [ ] Owners, tags, showback/chargeback, budget alerts, and purchase approvals are established.
- [ ] Commitment utilization, coverage, and spot interruptions are reviewed periodically.
- [ ] Worker security identities, secrets, and networks are scoped to the workload.
- [ ] Sustainability metrics evaluate resource-hours, idle capacity, and duplicate work.
- [ ] An ADR documents assumptions, trade-offs, owners, and strategy revisit triggers.

Trading off committed, on-demand, and interruptible resources is both a financial and an architectural decision. Use commitments for stable baselines within well-matched terms, on-demand for flexibility and uncertain demand, and spot for workloads engineered to survive interruption. Measure utilization, coverage, cost per completed unit of work, and failure behavior rather than comparing hourly rates alone. A strong strategy keeps core capacity reliable, turns deferrable work into elastic load, and lets the organization scale without getting trapped in stranded commitments or dependent on capacity that can vanish.
