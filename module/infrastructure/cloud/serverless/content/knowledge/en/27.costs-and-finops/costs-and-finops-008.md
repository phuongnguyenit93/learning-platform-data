# Evaluating Warm-Up and Reserved Capacity Costs

## 1. Why Must You Evaluate Warm Capacity?

Serverless frees you from managing servers, yet that does not mean every resource only incurs costs when requests arrive. Several mechanisms hold capacity in reserve to reduce cold starts or guarantee readiness during traffic spikes. On AWS Lambda, the most prominent mechanism is **Provisioned Concurrency**. It pre-creates execution environments before requests arrive, lowering initialization latency, yet allocated capacity incurs charges for as long as it is held—even during low or zero invocations.

A warm-capacity decision must answer two questions at once:

- What latency, availability, or burst-handling level must be guaranteed?
- How much extra will idle capacity cost, and is that benefit worth it?

Do not treat warm capacity as a simple performance switch. It is a FinOps decision affecting SLOs, concurrency, compute bills, database connections, quotas, and scalability.

In the CLOUD_SERVERLESS module, learners understand how Java functions are triggered by HTTP, messages, or events; how runtimes initialize; how concurrency scales up and down; and how to choose FaaS while balancing cold starts, reserved capacity, and costs.

## 2. Distinguishing Capacity Concepts

Related terms solve different problems.

| Concept | Purpose | Keeps Execution Environment Warm? | Charges for Idle Capacity? |
|---|---|---|---|
| On-demand concurrency | Platform creates environments as invocations demand | No guarantee | No separate provisioned-capacity fee |
| Provisioned Concurrency (PC) | Pre-initializes a set number of Lambda execution environments | Yes, within allocated limit | Yes |
| Reserved Concurrency (RC) | Sets dedicated concurrency quota and maximum cap for a function | No | No separate fee for reserving concurrency |
| Account concurrency quota | Caps total concurrency across an account/Region | No | Not warm capacity |
| SnapStart | Restores execution environments from snapshots to cut initialization | Does not hold one warm environment per concurrency | May carry snapshot cache/restore fees by runtime and price list |
| Scheduled warmer | Invokes a function periodically hoping environments get reused | No guarantee | Incurs invocation costs and call side effects |
| Provisioned/Minimum instances on container platforms | Keeps a minimum number of instances/containers running | Yes, depending on service | Usually incurs idle instance charges per service model |

Two misconceptions to avoid:

- **Reserved Concurrency is not Provisioned Concurrency.** Reserved Concurrency reserves quota and sets a concurrency ceiling; it does not pre-initialize runtimes, so it does not eliminate cold starts on its own.
- **Provisioned Concurrency is not a maximum ceiling.** It is the number of pre-prepared environments. If load exceeds that level, requests can spill over to on-demand capacity if concurrency quota remains; cold starts can occur there. If the function is capped by Reserved Concurrency, traffic past the ceiling gets throttled.

## 3. Cold Starts and Warm Invocations

Cold starts happen when the platform must prepare a fresh execution environment before running the handler. For Java, steps may include loading the runtime, initializing the JVM, class loading, framework startup, dependency injection, creating clients, and connecting to external services.

Warm invocations reuse an already initialized environment. Warm environments may be reused, yet never assume the platform keeps them indefinitely or reuses them for every request.

Provisioned Concurrency pre-creates environments and runs initialization before requests arrive. When PC covers current load, requests can execute without waiting on standard initialization. PC does not eliminate every latency source: handlers, databases, networking, throttling, and dependencies can still be slow.

Measure separately:

- `Init Duration` and first-invocation latency.
- Warm `Duration` and p50/p95/p99 percentiles.
- `ProvisionedConcurrencyInvocations`.
- `ProvisionedConcurrencySpilloverInvocations`.
- `ProvisionedConcurrencyUtilization`.
- `ConcurrentExecutions`, `Throttles`, error rates, and queue age.

If p99 latency stems mostly from databases or queue backlogs, raising PC can raise costs without meaningfully improving user experience.

## 4. How Does Provisioned Concurrency Work?

Provisioned Concurrency is configured on a **published version or alias** of Lambda, never directly on `$LATEST`. Lambda prepares execution environments matching the configured PC level.

Example:

```text
orders-function
  ├── version 41
  ├── version 42
  └── alias production -> version 42
       └── Provisioned Concurrency = 12
```

In this example, alias `production` has 12 pre-initialized execution environments. When deploying a new version, the alias may shift to the new version and PC must be provisioned for the corresponding qualifier. Never assume PC on an old alias transfers automatically to a new version.

Operational points:

- PC takes time to reach `READY`; capacity updates are not instantaneous.
- Only traffic targeting the provisioned qualifier uses that capacity.
- PC can combine with alias routing/canaries, though you must check PC per version/alias and traffic split.
- If PC is exhausted, Lambda can draw on available on-demand concurrency; spillover invocations may experience cold starts.
- If concurrency quotas or Reserved Concurrency are insufficient, invocations exceeding limits may be throttled.

Documentation: [AWS Lambda Provisioned Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html).

## 5. How Does Reserved Concurrency Differ from Provisioned Concurrency?

Reserved Concurrency (RC) serves two roles: reserving a slice of account concurrency for a function and capping the maximum concurrency that function may consume. It protects other functions from one runaway function and can protect downstream dependencies such as databases.

RC does not pre-create execution environments. A function with RC = 50 can still experience cold starts when new requests arrive.

Example:

```text
Reserved Concurrency = 30
Provisioned Concurrency = 10

Maximum concurrency the function can use: 30 concurrent invocations
Of which 10 environments are pre-initialized
Concurrency above 10 can spill over to on-demand if quota allows
Above 30 is throttled
```

PC cannot exceed the concurrency limit applied to the function. The account/Region must also hold enough concurrency quota to provision PC alongside other functions.

| Scenario | Suitable Configuration |
|---|---|
| Need to prevent a function from exhausting database connections | Reserved Concurrency |
| Need to cut cold starts for an API with strict latency SLOs | Provisioned Concurrency or SnapStart depending on workload |
| Need to protect account capacity for critical functions | Reserved Concurrency |
| Need both a warm baseline and an overall load ceiling | Combine PC and RC |
| Just need on-demand scaling where cold starts are acceptable | On-demand concurrency |

Do not sum RC and PC as two independent capacity pools. RC is the quota/ceiling; PC is the pre-prepared environments inside that ceiling.

## 6. Cost Components of Provisioned Concurrency

When PC is enabled, costs may include:

1. **Provisioned capacity charge:** billed by function memory, provisioned concurrency count, and duration capacity is configured/held.
2. **Request charge:** invocations/requests still bill under Lambda's pricing model.
3. **Execution duration charge:** code execution time bills under rates matching PC, architecture, and Region.
4. **Spillover execution:** invocations exceeding PC may run on on-demand capacity if quota allows; these may hit cold starts and bill at on-demand rates.
5. **Supporting costs:** API Gateway, SQS, databases, NAT/network, logs, traces, metrics, secrets, and called services.

The critical FinOps point is that **capacity charges continue accruing while PC is idle**. Holding 20 environments for 24 hours to serve a 30-minute traffic peak leaves capacity largely unused most of the time.

Exact rates depend on Region, architecture, memory, timeframe, and invocation type. Do not treat one fixed rate from an article as a budget; check [AWS Lambda Pricing](https://aws.amazon.com/lambda/pricing/) and the AWS Pricing Calculator when budgeting.

## 7. Formula for Estimating Idle Capacity Costs

Estimate the capacity charge using:

```text
PC capacity GB-seconds
  = memory_GB × provisioned_concurrency × provisioned_seconds

PC capacity cost
  = PC capacity GB-seconds × PC price per GB-second
```

Hypothetical example:

- Memory: 1 GB.
- Provisioned Concurrency: 8.
- Held continuously: 8 hours/day.

```text
1 GB × 8 concurrency × 8 × 3,600 seconds
= 230,400 GB-seconds per day
```

If held at the same level 24 hours/day:

```text
1 GB × 8 × 24 × 3,600
= 691,200 GB-seconds per day
```

This is provisioned capacity usage, not the full bill. Add requests, execution duration, spillover, and supporting services at current pricing. The example shows how scheduling around active hours can cut idle capacity substantially when traffic is genuinely periodic.

## 8. Estimating Concurrency from Traffic

A basic estimate uses Little's Law:

```text
Average concurrency ≈ arrival rate (requests/second)
                       × average execution duration (seconds)
```

For example, a function receives 60 requests/second with an average duration of 120 ms:

```text
60 × 0.12 = 7.2 average concurrent executions
```

The figure 7.2 is not enough to size PC. Traffic can burst, duration has a long tail, and cold starts or dependencies can stretch processing times. Inspect short-window distributions, peak concurrency, p95/p99 duration, concurrent requests, and SLOs.

A practical sizing approach:

1. Collect request rates in 1-second or 1-minute buckets depending on workload.
2. Measure duration when warm and when dependencies fluctuate.
3. Calculate concurrency required at peak, not just average.
4. Add a justified buffer for bursts/forecast error.
5. Run load tests and inspect spillover/throttles.
6. Choose baseline PC and a scaling mechanism for the remainder.

Never set PC equal to average concurrency and expect zero cold starts. PC provides ready capacity, not a guarantee that all traffic will stay within that capacity.

## 9. Sizing by Latency SLO and Bursts

PC fits when cold starts affect a significant share of requests under strict latency requirements. Determine:

- Share of requests that can tolerate cold starts.
- Target p95/p99 latency.
- Burst magnitude arriving within one second.
- PC scale-up time and warm-up time.
- Standby concurrency buffer to maintain.
- Off-hours holding cost.

For example, an API peaks at 100 RPS with 150 ms average duration. Estimated average concurrency is 15. If traffic arrives in bursts and p95 duration is 250 ms, short-term concurrency can be far higher. Setting PC to 15 from the average alone is overly optimistic. Load test with the real burst pattern and monitor `ProvisionedConcurrencySpilloverInvocations`.

Not every request needs PC. Separate latency-critical endpoints onto a dedicated function with PC, leaving batch/reporting workloads on-demand.

## 10. Target Utilization and Spare Capacity Buffer

If PC constantly runs near 100% utilization, minor bursts cause spillover. If PC sits far above load, idle capacity inflates costs.

A target utilization below 100% preserves a buffer. For instance, a 70% target tells autoscaling to hold PC above expected concurrency to leave headroom. This is an autoscaling target, not an exact guarantee on latency or invocation counts.

Metrics to track:

- `ProvisionedConcurrentExecutions`: PC currently in use.
- `ProvisionedConcurrencyUtilization`: share of PC utilized.
- `ProvisionedConcurrencySpilloverInvocations`: invocations not served by PC.
- `ConcurrentExecutions`: total concurrency.
- `Throttles`: invocations rejected due to quota/concurrency.
- `Duration`, `Init Duration`, p95/p99, and error rates.

If utilization stays low with no clear SLO benefit, trim the baseline or narrow active hours. If spillover climbs during peaks, revisit targets, schedules, max capacity, and forecasts.

## 11. Scheduled Scaling for Provisioned Concurrency

If traffic follows predictable cycles (business hours, sales schedules, batch windows), scheduled scaling can provision ahead of peaks and scale back afterward.

Example:

```text
07:30        Raise PC from 0 to 12
08:00        API peak hours begin
08:00-17:30  Maintain baseline 12, autoscale as needed
18:00        Lower PC to 0 or minimum level
```

Raise capacity early enough for Lambda to finish provisioning and reach `READY` before traffic arrives. Do not schedule scaling right at peak start if provisioning takes time.

Scheduled scaling works well for predictable patterns. For campaign-driven or unexpected spikes, combine target tracking or keep a modest buffer. Do not scale down the moment traffic dips for a minute; use cooldowns/hysteresis to avoid oscillation.

## 12. Autoscaling Provisioned Concurrency

Application Auto Scaling supports target tracking and scheduled scaling for Lambda provisioned concurrency on eligible aliases/versions. Target tracking adjusts PC to maintain a target utilization level.

Configuration parameters:

- Min capacity: lowest PC level, which can be 0 if off-hours cold starts are acceptable.
- Max capacity: caps cost and concurrency.
- Target utilization: desired utilization, typically below 100% to preserve buffer.
- Scale-out cooldown: prevents overly rapid repeated scale-ups.
- Scale-in cooldown: prevents shrinking capacity prematurely.
- Schedules: pre-provisions ahead of predictable traffic waves.

Autoscaling cannot completely eliminate cold starts during bursts faster than scaling speed. If ultra-low latency is required in the very first second of a spike, you need a larger baseline PC or a buffering mechanism such as queues/async APIs.

Documentation: [Application Auto Scaling for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html#application-auto-scaling).

## 13. SnapStart as an Alternative for Some Java Workloads

SnapStart takes a snapshot of the execution environment after initialization when publishing a version; new environments can restore from that snapshot to cut startup time. It does not hold a fixed number of environments continuously ready like PC.

| Criterion | Provisioned Concurrency | SnapStart |
|---|---|---|
| Goal | Keep pre-initialized execution environments ready | Cut initialization cost when creating environments |
| Idle capacity | Incurs charges even with zero requests | No idle concurrency held |
| Bursts | Served up to provisioned PC; excess may spill over | Can restore environments from snapshot, still requires capacity scaling |
| Java startup | Initialization runs before requests arrive | Restores from snapshot instead of full initialization |
| Best fit | Strict latency SLOs, predictable traffic, or required warm baseline | High Java cold starts, variable traffic, avoiding large PC spend |
| Limitations | Requires sizing, quotas, and capacity holding cost | Must verify runtime support, snapshot/restore behavior, and post-restore state safety |

SnapStart can fit better when cold starts are the main problem yet traffic is too uneven to justify paying for PC. However, SnapStart does not guarantee zero cold starts or zero latency; restore and handler execution still take time. Verify supported Java runtimes, versions/aliases, hooks, and values needing re-initialization after restore.

Documentation: [AWS Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html).

## 14. Scheduled Warmers Are Not a Capacity Guarantee

Some systems use EventBridge Scheduler or cron to ping functions periodically hoping to keep environments warm. This creates steady invocations, but does not guarantee:

- The next invocation lands in the previous environment.
- The platform will not scale in or recycle the environment.
- Every concurrency slot stays warm.
- Burst traffic will not spin up new environments.
- Warm-up invocations avoid unintended side effects.

Warmers still incur requests, duration, logs, and potential downstream calls. If used, the handler must detect warm-up payloads and exit quickly and safely—running no business logic, sending no messages, and writing no production data.

Never treat a warmer as an SLO guarantee. If latency must be guaranteed, evaluate PC or SnapStart. If cold starts are acceptable, on-demand may be cheaper.

## 15. Example Calculating Costs by Time Window

Suppose a Java API needs 1 GB memory and expects 10 concurrency during 8 business hours. Traffic is low the rest of the day.

| Option | Baseline PC | Holding Window | Capacity GB-s/day (Est.) |
|---|---:|---:|---:|
| A: always on | 10 | 24 hours | 864,000 |
| B: business hours only | 10 | 8 hours | 288,000 |
| C: small baseline | 3 | 24 hours | 259,200 |
| D: no PC | 0 | 0 | 0 |

Values use `memory_GB × concurrency × seconds`; they exclude execution, requests, spillover, and supporting services. Option C may look cheaper than B yet fall short during peak hours; check SLOs and spillover. Option D has zero PC cost yet exposes traffic to cold starts.

Never choose an option strictly from the GB-s table. Measure the share of requests actually served by PC, cost per successful request, and impact on p95/p99.

## 16. Total Cost and Cost per Successful Request

Total cost of a function with PC should be broken down by component:

```text
Total cost
  = Provisioned Concurrency capacity charge
  + invocation request charge
  + execution duration charge
  + on-demand spillover cost
  + API Gateway / queue / event cost
  + database / cache / connection proxy cost
  + network / NAT / data transfer cost
  + logs / metrics / traces cost

Cost per successful request
  = total cost / successful business operations
```

Counting successful Lambda invocations is insufficient if operations fail downstream or retry. Use completed operations at the domain boundary.

PC may raise total spend while trimming tail latency; weigh that against the business value of the SLO. For example, lower checkout p99 can lift conversion or cut timeouts/retries. For internal batch functions with no user waiting, PC may not deliver commensurate value.

## 17. Opportunity Cost of Reserved Capacity

Reserved capacity is not just a direct line item. It consumes concurrency quotas, account capacity, and downstream headroom.

For instance, 40 PC for one API reduces available concurrency for other functions in the same account/Region. A function with high RC reserves dedicated quota and can starve other functions. Capacity planning must happen at the account/service portfolio level, not one Lambda at a time.

Maintain an inventory of:

- PC by function alias/version and environment.
- RC by function.
- Account concurrency quota and peak utilization.
- Database/cache/provider reserved capacity.
- Scaling schedules and accountable owners.
- Review/expiration dates for temporary capacity settings.

Set alerts when provisioned capacity sits unused, when RC lacks clear justification, or when one function consumes a large share of account quota.

## 18. Protecting Databases When Keeping Lambda Warm

PC holds many execution environments ready. If each environment opens a large connection pool, the database can face a sudden surge of connections right upon provisioning or scale-out.

Example:

```text
Provisioned Concurrency = 40
Maximum connections per environment = 10
Potential connections = 40 × 10 = 400
```

This is the potential ceiling if every environment fills its pool; it does not mean all connections stay open constantly. Still, account for warm environments, spillover environments, other functions, and non-Lambda applications.

Measures:

- Keep pools small and aligned with actual concurrency.
- Use RDS Proxy or an appropriate connection proxy when workloads demand it.
- Reuse clients/connections inside execution environments while handling stale connections.
- Cap Lambda concurrency to match database capacity.
- Monitor database connection counts, queueing, CPU, and lock waits.
- Avoid provisioning high function concurrency before downstream capacity is ready.

Warm compute capacity can overload databases faster. PC and RC must be designed alongside dependency capacity.

## 19. Optimizing Memory and Duration When Using PC

PC capacity charges depend on memory and provisioned concurrency. Raising memory increases capacity charge per environment, yet can boost CPU and shorten execution duration. When functions finish faster, concurrency needed for the same throughput can drop.

Therefore, benchmark multiple memory settings:

- Low memory: lower PC charge per environment, yet handlers may run longer, requiring higher concurrency.
- High memory: higher PC charge per environment, yet handlers may run faster and free capacity sooner.
- The optimum depends on CPU-bound vs. I/O-bound behavior, JVM startup, GC, payloads, and downstream speeds.

Measure cost per successful request for each configuration, not just GB-seconds or duration. In Java, inspect GC, heap, native memory, and framework startup. Optimizing code and connection reuse can cut both duration and required concurrency.

## 20. Allocating Warm Capacity by Workload Type

Not every function needs PC.

| Workload | Direction | Reason |
|---|---|---|
| Public API with strict p99 | Baseline PC or SnapStart; canary by alias | Direct requests suffer from cold starts |
| Low-traffic Admin API | On-demand or SnapStart | Not worth paying for large idle capacity |
| Batch-processing queue worker | On-demand + queue buffering; RC to protect downstream | Can tolerate queue delay and scale with backlog |
| Daily scheduled job | On-demand, SnapStart if startup is sizable | No need to stay warm all day |
| Fast-response webhook | PC for ingress endpoint if SLO requires; async business work | Separates acceptance latency from processing latency |
| Hourly patterned traffic | Scheduled PC + target tracking | Peak hours are predictable |
| Unpredictable traffic bursts | SnapStart/on-demand with buffer; queue if business allows | Large fixed PC can be very expensive |
| Function calling connection-limited DB | RC to cap concurrency, PC only if latency requires | Protect downstream before optimizing cold starts |

## 21. Hybrid Strategy: Warm Baseline Plus On-Demand Spillover

A practical setup holds modest PC for regular traffic and lets on-demand capacity absorb spikes.

Example:

```text
Regular traffic: 5-8 concurrency
Provisioned Concurrency: 10
Reserved Concurrency: 30

0-10 concurrent: served by PC first
10-30 concurrent: can spill over to on-demand
Above 30: throttled
```

This model costs less than holding 30 PC while accepting cold starts on spillover. If every request must meet a strict latency SLO, provision for full peak or use another mechanism to absorb bursts.

Track spillover by alias and time window. If rare spillover causes severe p99 violations, raise PC during that window. If spillover is frequent, baseline PC is too low or the forecast is off.

## 22. When Should Queues Replace Warm Capacity?

When callers do not need immediate results, queues absorb bursts and let workers scale with backlogs. Producers return `202 Accepted` after persisting/publishing events; workers process as capacity allows.

Queues do not replace PC in all scenarios. They trade synchronous latency for processing SLAs. Monitor:

- `ApproximateAgeOfOldestMessage` or event age.
- Queue depth and arrival/processing rates.
- Lambda concurrency and batch size.
- Visibility timeouts, retries, DLQs, and idempotency.
- Business expiration `expiresAt`.

If workers must finish within seconds, PC or baseline capacity may still be needed. If work can wait minutes, on-demand scaling is usually more economical.

## 23. Other Serverless Platforms

Warm/minimum capacity concepts appear on other platforms as well, though pricing and semantics differ:

| Platform | Closest Equivalent | What to Verify |
|---|---|---|
| AWS Lambda | Provisioned Concurrency, SnapStart | PC idle charges, versions/aliases, spillover, runtime support |
| Azure Functions | Always Ready / prewarmed instances depending on hosting plan | Plan, minimum instances, execution/idle billing, and scaling behavior |
| Google Cloud Run | Minimum instances, startup CPU boost | Instance-based/request-based billing, idle allocation, and min instance settings |
| Container/serverless platforms | Minimum tasks/instances or reserved capacity | Whether idle time bills, scale-to-zero, startup time, and quotas |

Do not port Lambda pricing formulas directly to Azure Functions or Cloud Run. Read the pricing model for the exact hosting plan/Region and calculate from actual configuration.

## 24. FinOps: Assigning Owners, Budgets, and Reviews

Every warm capacity configuration needs a justification and an owner. A governance record might include:

| Field | Example |
|---|---|
| Service/function | `orders-api` |
| Environment | `production` |
| Alias/version | `production -> version 42` |
| PC min/max | 4 / 24 |
| RC | 30 |
| Schedule | 07:30–18:00 business days |
| Target utilization | 70% |
| SLO | p99 under 400 ms |
| Owner | Team Orders |
| Cost center | `CC-ORDERS` |
| Review date | Monthly or post-peak event |

FinOps reviews should inspect:

- Hourly/daily PC utilization.
- Spillover and throttles.
- Cost per successful request.
- SLO compliance before and after enabling PC.
- Off-hours costs and unused capacity.
- Downstream connection/capacity pressure.
- Forecast variance and scaling schedules.

If metrics do not show PC improving SLOs or cutting business losses, lower the baseline, tighten schedules, or switch to SnapStart/on-demand.

## 25. Decision Process for Enabling Provisioned Concurrency

1. **Measure baseline:** cold starts, warm latency, p95/p99, traffic profile, and cost.
2. **Identify latency source:** initialization, framework, networking, or downstream.
3. **Optimize without holding capacity first:** trim package size, optimize init, reuse clients, use SnapStart where suitable.
4. **Isolate traffic needing warm capacity:** which routes/aliases have strict SLOs.
5. **Estimate PC:** use peak concurrency, burst profiles, and a safety buffer.
6. **Set RC:** protect account/downstream and cap total concurrency.
7. **Calculate costs:** idle capacity, requests, execution, spillover, and supporting services.
8. **Pre-provision:** wait for `READY` state before shifting traffic.
9. **Canary:** ramp traffic incrementally while watching spillover, p99, errors, and cost.
10. **Autoscale/schedule:** configure min/max, targets, cooldowns, and schedules per demand.
11. **Review:** reduce or disable PC once SLO benefit disappears.

## 26. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Confusing RC with PC | Functions still cold start despite reserved concurrency | Use PC when the goal is keeping environments warm |
| Running PC 24/7 for daytime traffic | High idle costs | Scheduled scaling or small minimum capacity |
| Setting PC equal to average concurrency | Bursts cause spillover/cold starts | Size for peak and load test |
| Setting PC equal to RC | Zero room for spillover; easily throttled | Set RC and PC for their distinct purposes |
| Provisioning on `$LATEST` | Invalid qualifier configuration | Use published versions/aliases |
| Shifting alias before PC is `READY` | New traffic still hits cold starts | Wait for provisioning to finish before shifting traffic |
| Using warmers as SLO guarantees | Environment reuse is not guaranteed | PC or SnapStart are more suitable |
| Looking only at Lambda costs | Misses databases, networking, logs, and API Gateway | Calculate end-to-end cost per successful operation |
| PC overloading databases | Connection storms and rising latency | RC, small pools, RDS Proxy, and downstream capacity plans |
| Not measuring spillover | Blind to how much traffic runs on-demand | Dashboard PC metrics and set alerts |
| Never reviewing after peak events | Temporary capacity becomes permanent fixed cost | Assign expiration/review owners to configs |

## 27. Pre-Production Checklist

- [ ] Verified whether cold starts actually violate SLOs.
- [ ] Distinguished Provisioned Concurrency from Reserved Concurrency.
- [ ] Attached PC to the proper published version/alias.
- [ ] Calculated capacity GB-seconds for the warm holding window.
- [ ] Included requests, execution, spillover, and supporting services.
- [ ] Measured peak traffic, bursts, and duration distributions.
- [ ] Sized PC with proper buffer rather than average concurrency alone.
- [ ] Set RC to protect functions/accounts/downstream without starving quotas.
- [ ] Built dashboards for utilization, spillover, throttles, p95/p99, and cost.
- [ ] Configured scheduled scaling/target tracking with clear min/max/cooldowns.
- [ ] Waited for PC `READY` status before shifting traffic.
- [ ] Verified aliases/versions and canary/rollback procedures.
- [ ] Compared SnapStart/on-demand before holding large PC.
- [ ] Confirmed warmers cause no side effects and are not treated as guarantees.
- [ ] Confirmed database connection pools and downstream capacity cover PC + spillover.
- [ ] Assigned owner, cost center, budget, and review date.
- [ ] Checked current pricing for Region/architecture/runtime.

## References

- [AWS Lambda Provisioned Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html)
- [Application Auto Scaling for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html#application-auto-scaling)
- [AWS Lambda Reserved Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html)
- [AWS Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html)
- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/)
- [AWS Lambda concurrency](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [Amazon RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html)
- [Azure Functions scale and hosting](https://learn.microsoft.com/azure/azure-functions/functions-scale)
- [Google Cloud Run minimum instances](https://cloud.google.com/run/docs/configuring/min-instances)

## Conclusion

Warm capacity cuts cold starts and stabilizes latency, yet incurs charges even while environments sit idle. Provisioned Concurrency pre-initializes Lambda execution environments; Reserved Concurrency merely reserves quota and caps concurrency. Size PC from peak traffic and SLOs, include full capacity GB-seconds alongside invocations, spillover, and dependency costs, and use schedules/target tracking to minimize idle capacity. For Java, evaluate SnapStart and startup optimization before holding large PC. Finally, protect databases with proper RC/connection pools and regularly review utilization, spillover, p99, and cost per successful request.
