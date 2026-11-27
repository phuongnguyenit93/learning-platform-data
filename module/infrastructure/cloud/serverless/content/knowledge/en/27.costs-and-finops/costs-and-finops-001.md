# Modeling Function Costs by Traffic and Execution Duration

The cost of a serverless function depends on the number of invocations, execution duration, allocated resources, and the services the function uses. A function with few invocations that runs for a long time with high memory can cost more than a function invoked frequently that finishes quickly. A workload with a low average but large bursts can also incur different costs due to scale-out, reserved capacity, and supporting services.

To build a useful cost model, you need to connect three layers of data:

1. **Business demand:** number of successful operations, incoming events/requests, and growth rate.
2. **Runtime behavior:** actual invocation count, retries, batch size, duration, memory/CPU, concurrency, and cold starts.
3. **Infrastructure billing:** requests, compute, reserved capacity, queues, API gateways, network, logs, traces, storage, and downstream services.

You should not estimate costs simply by multiplying invocation count by a single unit price. You need to model execution duration, resource allocation, retries, and costs outside the function to understand what a business operation truly costs.

## 1. Factors That Drive Serverless Costs

Depending on the provider and billing model, a serverless Java application can incur the following cost categories:

| Cost Category | Common Drivers | Examples |
|---|---|---|
| Invocation/request | Number of times a function is invoked | HTTP requests, event invocations |
| Compute duration | Execution time and allocated resources | GB-second, vCPU-second, GiB-second |
| Reserved capacity | Provisioned or minimum concurrency/instances | Provisioned concurrency, min instances |
| Events and queues | Number of broker/API operations | SQS requests, Pub/Sub operations, EventBridge events |
| API ingress | Requests and data through gateway/load balancer | API Gateway, HTTP load balancing |
| Network | Data transfer, NAT, cross-zone/region | Egress, VPC connector, NAT processing |
| Observability | Log ingestion, retention, queries, traces | CloudWatch Logs, Cloud Logging, tracing backend |
| Storage | Payloads, artifacts, snapshots, temporary storage | Object storage, container registry, ephemeral storage |
| Downstream | Databases, caches, external APIs, and shared services | Database capacity, connection proxy, payment provider |
| Security/operations | Secrets, keys, auditing, and monitoring | KMS operations, secret access, security logs |

Some services are billed by requests, bytes, data retention duration, or provisioned capacity. Unit prices and billing rules vary by provider, region, runtime, architecture, tier, and time. The model should use unit price variables taken from the current price list of the deployment environment, rather than hard-coding prices from a learning example.

## 2. Separating Business Operations from Function Invocations

A business operation does not necessarily correspond to a single invocation.

For example, an order might:

- Call an API function to receive the order.
- Send an event to a queue.
- Call a function to reserve inventory.
- Call a function to capture payment.
- Call a function to create a shipment.
- Retry one or more steps.
- Send a notification event upon completion.

One business operation can generate multiple invocations across multiple functions. Conversely, a single invocation can process a batch containing multiple messages.

Therefore, you need to distinguish between:

- **business_operations:** number of unique business intents.
- **messages_published:** number of published messages.
- **function_invocations:** number of times functions actually run.
- **successful_operations:** number of completed business operations.
- **retry_attempts:** number of additional processing attempts due to retries/redeliveries.
- **failed_or_rejected_operations:** number of incomplete operations.

This is the foundation for calculating cost per operation and avoiding confusing invocation counts with customer counts or order counts.

### 2.1. Estimating Invocation Counts

For an HTTP function with one request per invocation:

\[
N_{\text{invocations}} \approx
N_{\text{requests}} \times A
\]

Where \(A\) is the average number of attempts per request, including retries from the client or platform.

For a message consumer receiving batches:

\[
N_{\text{invocations}} \approx
\frac{N_{\text{messages processed across attempts}}}
{B_{\text{effective}}}
\]

Where \(B_{\text{effective}}\) is the actual effective batch size, which does not necessarily equal the configured maximum batch size. Batches are not always full; batching window, concurrency, payload limits, partial failures, and retries can change the number of invocations.

For a multi-function workflow:

\[
N_{\text{total invocations}} =
\sum_{f=1}^{F} N_f
\]

Calculate separately for each function or group of functions that have different memory, duration, and pricing. Do not multiply total business operations by a single factor if operations follow different execution paths.

## 3. Modeling Compute by Duration and Resources

A common FaaS model bills compute by allocated resources multiplied by billable duration. For a function with fixed memory:

\[
U_{\text{compute}} =
N_{\text{invocations}}
\times D_{\text{billable}}
\times M_{\text{GB}}
\]

Where:

- \(N_{\text{invocations}}\): number of billable invocations.
- \(D_{\text{billable}}\): average billable duration, in seconds.
- \(M_{\text{GB}}\): allocated memory, converted to GB according to provider rules.
- \(U_{\text{compute}}\): amount of compute units, e.g., GB-seconds.

Compute cost can be estimated as:

\[
C_{\text{compute}} =
U_{\text{compute}} \times R_{\text{compute}}
\]

Request cost:

\[
C_{\text{request}} =
\frac{N_{\text{invocations}}}{1.000.000}
\times R_{\text{request per million}}
\]

Total basic function cost:

\[
C_{\text{function}} =
C_{\text{request}} + C_{\text{compute}}
\]

This is a general model. Some providers bill vCPU-seconds and GiB-seconds separately; some have minimum durations, duration rounding increments, or different CPU calculation rules. Replace the compute units and rates with the exact billing dimensions of the platform you are using.

### 3.1. Compute Calculation Example

Suppose an HTTP function has the following monthly forecast metrics:

- 2,600,000 invocations including retries.
- Allocated memory: 512 MiB, equivalent to approximately 0.5 GiB in this example.
- Average billable duration: 240 ms, equivalent to 0.24 seconds.

Estimated compute usage:

\[
2.600.000 \times 0,24 \times 0,5
= 312.000\ \text{GB-second}
\]

Function cost:

\[
C_{\text{function}} =
2,6 \times R_{\text{request per million}}
+ 312.000 \times R_{\text{GB-second}}
\]

The rates here are variables to be filled in based on the current price list. This example does not represent pricing from AWS, Google Cloud, Azure, or any specific region.

### 3.2. Breaking Down Duration into Components

Duration must be measured consistently. For Java, execution time may include:

- Initialization/runtime startup.
- Framework/context initialization.
- Handler execution.
- Dependency calls.
- Serialization and response handling.

Depending on the platform, initialization may be included in billable duration or have separate billing rules. Read the provider's billing semantics. Do not add Init Duration to duration again if the billable metric already includes it.

For message consumers, you should distinguish between the time a message waits in the queue and the time the function actually runs. Queue wait increases message age and can extend SLA, but it is not necessarily billable compute duration for the function.

### 3.3. List Price vs. Effective Cost

When choosing rates for the model, determine whether you are calculating **usage cost at list price** or **effective cost after discounts**. The two figures serve different purposes:

- List price helps compare consumption across configurations and providers.
- Effective rate reflects Savings Plans, committed-use discounts, enterprise discounts, or allocated contract rates.
- Free tier, credits, and promotional balances can lower the actual invoice paid in a period, but do not necessarily reduce resource consumption.
- Taxes, support plans, and account-level fees should be calculated separately if the goal is to forecast the total invoice.

Do not subtract free tier or credits twice. When reporting, keep gross usage, discounts/credits, and net cost separate so readers understand why the invoice differs from consumption.

## 4. Average Duration and Latency Distribution

Average duration is useful for forecasting total compute, but it can hide slow request cohorts.

For example:

- 90% of requests process in 100 ms.
- 9% process in 400 ms.
- 1% process in 5 seconds.

An average does not show tail latency and is insufficient for planning timeouts, concurrency, or provisioned capacity.

You should track:

- p50 duration.
- p90/p95 duration.
- p99 duration.
- Maximum duration.
- Duration by function version, route, or message type.
- Duration by outcome (success/retry/error).

To forecast invoices, use total billable duration or an average calculated from the distribution and volume of each request type. To design capacity and SLOs, also use percentiles and peak concurrency.

If there are multiple workload classes, calculate them separately:

\[
U_{\text{compute}} =
\sum_{k=1}^{K}
N_k \times D_k \times M_k
\]

Where \(k\) is the request class, such as create-order, generate-report, or resize-image.

## 5. Retries Increase Billable Executions

Retries are part of reliability, but they are also a cost driver. A single message can trigger multiple invocations if the function errors, times out, gets throttled, or fails to ack in time.

If an operation has an average of \(A\) attempts:

\[
N_{\text{attempts}} =
N_{\text{logical operations}} \times A
\]

For example, 2 million operations with an average of 1.08 attempts:

\[
N_{\text{attempts}} =
2.000.000 \times 1,08
= 2.160.000
\]

The extra 160,000 attempts increase request charges, compute, and possibly queue/API operations.

Retries can also increase downstream costs if each attempt calls a database or provider. Measure retries by cause:

- Throttling.
- Timeout.
- Network error.
- Business rejection.
- Poison message.
- Dependency unavailable.
- Duplicate delivery.

Not all retries cost the same duration. An attempt that fails after 20 ms differs from an attempt that times out after 30 seconds. Use the actual duration of each attempt group when forecasting.

### 5.1. Retry Storms and Cost Amplification

When a dependency is overloaded, simultaneous retries can cause request counts and compute to spike while the success rate drops. The system may pay for many executions without generating additional business value.

Measures to reduce retry costs without sacrificing reliability:

- Classify retryable vs. permanent errors.
- Exponential backoff and jitter.
- Limit maximum attempts.
- Use idempotency so retries are safe.
- Circuit breakers when downstream services repeatedly fail.
- DLQs for messages that cannot be processed after policy exhaustion.
- Reduce concurrency when dependencies are overloaded.
- Reconcile uncertain outcomes before re-invoking side effects.

Do not mechanically reduce retries just to lower the bill. The goal is to eliminate wasted attempts while maintaining business completion rates.

## 6. How Does Batch Size Affect Cost?

For event-driven functions, batching can group multiple messages into a single invocation. This reduces the number of invocations and handler initialization overhead, but it does not mean compute decreases proportionally.

A large batch size can:

- Reduce request/invocation charges.
- Reduce the number of execution environment creations in some workloads.
- Increase memory and duration due to holding more payloads.
- Increase wait time to assemble batches.
- Increase the blast radius of retried messages on batch-level failures.
- Generate extra compute from reprocessing already-succeeded records if partial batch responses are not used.

Measure actual batch size and duration by batch size. The model can use:

\[
C_{\text{batch compute}} =
N_{\text{batch invocations}}
\times D_{\text{batch}}
\times M_{\text{GB}}
\times R_{\text{compute}}
\]

Add request charges for batch invocations and queue operations according to the provider.

For example, 1 million messages with an effective batch size of 10 can produce roughly 100,000 invocations if batches are full and there are no retries. If the actual average batch size is only 4 messages, the invocation count is closer to 250,000. Use actual metrics from the event source mapping rather than the maximum batch size.

Do not increase batch size solely to reduce invocations. Check payload limits, memory, processing duration, message age, timeouts, and partial failure behavior.

## 7. Memory and CPU: More Resources Can Be Cheaper

In some FaaS platforms, memory allocation simultaneously determines or influences the amount of CPU allocated. Increasing memory can make a Java function process faster, reducing duration and lowering total compute.

Suppose:

- Configuration A: 512 MiB, runs in 800 ms.
- Configuration B: 1,024 MiB, runs in 300 ms.

Relative compute usage:

\[
U_A = 0,5 \times 0,8 = 0,4\ \text{GB-second}
\]

\[
U_B = 1,0 \times 0,3 = 0,3\ \text{GB-second}
\]

In this example, Configuration B uses fewer compute units despite having double the memory. If request pricing and other factors remain unchanged, compute cost can be lower.

However, do not assume increasing memory always reduces cost. A function waiting on a database or API may not run faster with more CPU. Benchmark memory/CPU tiers using the same input and concurrency.

### 7.1. Memory Tuning Process

1. Select a representative set of inputs.
2. Run each memory/CPU tier in an equivalent environment.
3. Measure duration, p95/p99, peak memory, and errors.
4. Calculate compute usage for each configuration.
5. Calculate cost per successful operation.
6. Choose the configuration that meets SLOs with appropriate cost and headroom.
7. Re-verify under realistic bursts/concurrency.

For Java, also observe heap, garbage collection, thread count, class loading, connection pools, and native memory. Platform memory allocation does not mean the entire allocation is Java heap.

## 8. Cold Starts and Reserved Capacity

Cold starts can affect both latency and cost. However, the billing impact depends on the provider and deployment configuration.

When modeling costs, separate:

- Number of new initializations.
- Initialization duration.
- Handler duration.
- Billable duration according to provider rules.
- Reserved capacity.
- Snapshot/restore or special configuration costs, if any.

If initialization is included in billable duration, the additional compute can be estimated as:

\[
U_{\text{init}} =
N_{\text{cold starts}} \times D_{\text{billable init}} \times M_{\text{GB}}
\]

Only use this formula if init duration is not already included in the measured total billable duration. If it is already included, do not add it again.

### 8.1. Provisioned Concurrency and Minimum Instances

Reserved capacity can reduce cold starts, but it incurs costs even when there are no requests. The model needs to separate:

- Cost of provisioned capacity over time.
- Cost of invocations and compute when capacity is utilized.
- Hours/days the capacity is enabled.
- Amount of reserved capacity by schedule.
- Requests exceeding provisioned capacity that run under a different scaling mechanism.

With AWS Lambda, Provisioned Concurrency has its own pricing dimension separate from request/duration usage; the exact calculation depends on region and configuration. With Cloud Run or serverless container platforms, minimum instances have billing semantics based on CPU allocation/instance-based billing and instance state. Read the actual price list and configuration before calculating.

Do not compare cold start cost with warm cost while ignoring reserved capacity cost. Compare total cost across traffic schedules and latency SLOs.

### 8.2. When Should You Reserve Capacity?

You may consider provisioned/minimum capacity when:

- Cold p95/p99 latency violates SLOs.
- Traffic is predictable by hour.
- The function processes transactions requiring consistent latency.
- The cost of keeping capacity warm is lower than the business impact of latency.
- There is sufficient steady traffic to utilize the allocated capacity.

If traffic is very sparse and latency allows, scale-to-zero is usually more economical. If traffic is continuous and utilization is high, compare FaaS against always-on containers/services based on total compute and operational cost.

## 9. Concurrency and Traffic Shape

Monthly total invocations do not fully describe traffic. Two workloads with the same 10 million invocations can have very different costs:

- Workload A is evenly distributed across 30 days.
- Workload B is concentrated in short bursts.
- Workload C has hourly peaks and requires reserved capacity.
- Workload D receives massive bursts causing scale-out, retries, throttling, or increased queue age.

Average concurrency in steady state can be estimated using Little's Law:

\[
C_{\text{avg}} \approx \lambda \times D
\]

Where \(\lambda\) is the arrival rate (requests/second) and \(D\) is the average processing duration (seconds).

For example, 120 requests/second with a duration of 0.24 seconds:

\[
C_{\text{avg}} \approx 120 \times 0,24 = 28,8
\]

This number is the ideal average concurrency, not the max concurrency configuration. Peak concurrency must be measured or modeled from traffic bursts, tail duration, and platform scaling behavior.

Concurrency can indirectly impact costs:

- Increasing database connections and requests.
- Increasing throttling and retries.
- Increasing instance count or provisioned capacity.
- Generating more logs/traces.
- Changing cache hit rates.
- Triggering downstream autoscaling or capacity-based charges.

## 10. Queues Have Their Own Costs

An event-driven function does not just cost compute. Queues/brokers may charge by:

- Number of requests/API operations.
- Number of message publish/receive/delete/ack operations.
- Payload size or data volume.
- Storage duration and retention.
- Throughput units, partitions, or provisioned capacity.
- Cross-region replication or data transfer.
- Dead-letter and replay operations.

For example, a message passing through producer, queue, consumer, and DLQ can generate multiple broker operations. When retries increase, receive/ack or redelivery counts also increase.

For SQS, Pub/Sub, Kafka, and Azure Service Bus, billing dimensions differ. Self-managed Kafka may charge by broker instance/storage/network; managed Kafka services may charge by capacity/throughput or partitions. Do not use a single generic queue formula in place of the provider's price list.

### 10.1. Retention and Backlog

Queues holding messages longer can increase storage or capacity costs depending on the service. A large backlog can also prolong consumer execution time and increase compute during drain hours.

Backlog costs are not just storage:

- Consumers must run longer to drain.
- Messages may retry multiple times.
- DLQs require storage and replay.
- Business operations complete late, potentially creating support costs or SLA penalties.
- Databases and downstream services may have to scale to handle the backlog.

Track oldest message age, backlog, arrival rate, ack rate, and estimated drain time alongside cost.

## 11. API Gateway, Ingress, and Workflow Charges

HTTP functions often sit behind an API Gateway, load balancer, ingress, or authentication layer. Each layer can have request charges, capacity charges, or data processing fees.

Workflow orchestration can also be billed by number of state transitions, executions, or execution duration depending on the service. A workflow with many small states and frequent retries can cost more than a workflow with fewer states even if total Lambda compute is equivalent.

The model should capture:

- Number of API requests and payload sizes.
- Number of gateway/load balancer requests.
- Number of workflow executions.
- Number of state transitions or task operations.
- Number of retries/redrives.
- Time workflows wait for callbacks if the service bills by duration.
- Integration requests to other services.

Do not assume Wait states or long-running callbacks are always free; billing depends on the service and workflow type.

## 12. Network and Egress

Networking is an easily overlooked part of cost modeling:

- Internet egress.
- Cross-region data transfer.
- Cross-zone transfer.
- NAT gateway hourly/processing fees.
- VPC connectors or private networking.
- Data transfer between functions and databases in different regions/zones.
- API providers returning large payloads.
- Log/trace exports to other regions or vendors.

A small function can have low compute cost but high network cost if it processes large files or calls many services through a NAT gateway.

Measure inbound/outbound bytes by operation class and region. When a function accesses a private database, check the actual costs of NAT, connectors, or network architecture. Do not put sensitive data into telemetry just to allocate network costs.

## 13. Logs, Metrics, and Traces Also Cost Money

Overly verbose debug logging can generate larger log volumes than business data. Every invocation can write multiple lines; retries and bursts multiply log volume alongside traffic.

Drivers include:

- Log ingestion volume.
- Log retention duration.
- Query scan volume.
- Metrics time series and cardinality.
- Trace span volume and sampling.
- Export/network costs to observability vendors.
- Alerting and dashboard queries.

For example, logging full request/response JSON for every message can inflate storage, query costs, and data exposure risk.

### 13.1. Controlling Observability Costs

- Use structured logging and record only necessary fields.
- Do not log secrets, tokens, payment data, or sensitive payloads.
- Choose retention based on operational and audit requirements.
- Sample traces strategically; keep error/slow request traces according to policy.
- Avoid high-cardinality metric labels such as message ID, order ID, or customer ID.
- Use appropriate log levels between production and test.
- Track log GB/day and cost per 1,000 operations.

Do not cut telemetry to the point of losing investigative capability. The goal is to capture the right signals at appropriate volume and retention.

## 14. Downstream Costs Can Exceed Function Costs

A function running for 200 ms might run 3 database queries, read object storage, call a payment API, and publish an event. Function compute is only part of the cost per operation.

You need to account for:

- Database instance/serverless capacity, storage, and I/O.
- Cache capacity and requests.
- Object storage requests and bytes.
- KMS/secret operations.
- NAT and data transfer.
- External API usage or provider fees.
- Search/indexing and analytics.
- Queues and event buses.
- Shared platform costs allocated to the service.

If multiple functions share a database, do not assign the entire database bill to a single function. Use query count, connection time, storage usage, tenant/service tags, or an agreed allocation rule to distribute shared costs.

An architecture with cheap function compute that requires an always-on high-capacity database may be more expensive than a container service sharing that database. Compare the entire operation path.

## 15. Calculating Cost per Successful Business Operation

A useful FinOps metric is the cost per completed business operation:

\[
C_{\text{per success}} =
\frac{C_{\text{allocated total}}}
{N_{\text{successful unique operations}}}
\]

The numerator should include all relevant allocated costs: function, requests, queues, gateway, network, observability, storage, and downstream. The denominator is the number of unique completed operations, not the number of invocations or attempts.

Example:

- Total allocated cost for the order service: 1,200 currency units for the month.
- 400,000 unique completed orders.

\[
C_{\text{per order}} =
\frac{1.200}{400.000}
= 0,003
\]

Currency units here are illustrative only. You must standardize the currency and shared cost allocation rules.

Track cost per success by:

- Service/function.
- Environment.
- Operation type.
- Tenant or customer segment, if policy permits.
- Region.
- Release/version.
- Traffic channel or source.

Do not use invocation count as the denominator because increased retries can make cost per invocation appear to drop even when successful operations stay flat.

## 16. Cost Model Table Template

You can build a monthly forecast table with these columns:

| Variable | Meaning | Data Source |
|---|---|---|
| Business operations | Number of unique business intents | Product analytics/domain metrics |
| Attempts per operation | Average number of processing attempts | Retry/delivery metrics |
| Invocations per operation | Number of function calls per intent | Trace/workflow map |
| Effective batch size | Number of messages per invocation | Event source metrics |
| Billable duration | Duration per billing semantics | Provider billing/runtime metrics |
| Memory/CPU allocation | Configured resources | Deployment config |
| Request unit price | Invocation unit price | Pricing calculator/current price list |
| Compute rate | Compute unit price | Pricing calculator/current price list |
| Provisioned capacity | Capacity and reserved duration | Platform configuration |
| Queue/API/network | Requests, bytes, retention, and egress | Service metrics/billing export |
| Observability | Log, metric, trace volume | Observability usage |
| Downstream allocation | Database/cache/provider costs | Cost allocation/usage metrics |
| Successful operations | Number of unique completed operations | Domain metrics |

Calculate low/base/high scenarios separately. Each scenario should state clear assumptions for traffic, attempt rate, duration, batch size, peak concurrency, and reserved capacity.

## 17. Three-Scenario Forecast Example

Suppose a Java function processes report generation commands. The following table uses hypothetical numbers to illustrate how to build a forecast:

| Variable | Low | Base | High |
|---|---:|---:|---:|
| Business operations/month | 500,000 | 1,000,000 | 2,000,000 |
| Average attempts | 1.01 | 1.05 | 1.15 |
| Invocations/operation | 1 | 1 | 1 |
| Memory | 512 MiB | 512 MiB | 1,024 MiB |
| Billable duration | 200 ms | 300 ms | 450 ms |
| Provisioned capacity | 0 | Peak hours | Higher than base |

Invocation count:

\[
N = \text{Operations} \times \text{Attempts}
\]

Compute usage:

\[
U = N \times D_{\text{seconds}} \times M_{\text{GB}}
\]

| Scenario | Estimated Invocations | Illustrative Compute Usage |
|---|---:|---:|
| Low | 505,000 | 50,500 GB-seconds |
| Base | 1,050,000 | 157,500 GB-seconds |
| High | 2,300,000 | 1,035,000 GB-seconds |

The High scenario has double the base memory, longer duration, and a higher attempt rate, causing compute to surge. When using this table in practice, add request charges, reserved capacity, and supporting services.

A forecast is not an invoice commitment. Replace assumptions with billing/runtime data after each cycle and update according to actual traffic.

## 18. Sensitivity Analysis

Sensitivity analysis shows which variables have the greatest impact on cost:

- Operations increase by 20%.
- Retry rate rises from 1.02 to 1.15 attempts/operation.
- Duration increases by 30% due to downstream latency.
- Memory is stepped up one tier to reduce duration.
- Batch size increases, but message age also increases.
- Provisioned capacity is enabled for an extra 8 hours/day.
- Log volume increases due to debug logging.
- Egress increases due to large payloads.

With a linear compute model, if invocations rise by 20% and other factors stay constant, compute usage also rises by roughly 20%. However, if higher concurrency causes throttling/retries to spike, total cost can grow faster.

Rank variables by impact and controllability. Typically, duration, retries, memory/CPU, batch behavior, and downstream costs are worth measuring closely.

## 19. Comparing FaaS with Containers or Always-On Services

FaaS is often well suited for variable workloads that can scale to zero and do not need persistent processes. Containers/always-on services can be more economical when utilization is high, traffic is steady, or long-running processing is needed.

The comparison should evaluate:

| Factor | FaaS | Container/service |
|---|---|---|
| Compute billing | By invocation/duration or compute unit | By instance/vCPU/memory over time |
| Scale-to-zero | Usually supported | Depends on platform and configuration |
| Reserved capacity | May have separate charges | Always-on instances/min replicas incur cost |
| Cold starts | Can affect latency | Can be mitigated with always-on instances |
| Traffic bursts | Platform auto-scales within limits | Requires autoscaling/capacity planning |
| Runtime duration | Subject to service limits | More flexible depending on platform |
| Operational overhead | Less server management | Managing services/containers and scaling |

There is no universal break-even point. Use hourly traffic, utilization, memory/CPU, min capacity, retries, and downstream costs to model both options. If both share the same database or queue, keep shared costs consistent in the comparison.

## 20. FinOps: Measure, Allocate, Optimize, and Govern

FinOps is a collaborative loop across engineering, finance, and product to understand costs relative to value delivered.

A practical loop:

1. **Measure:** collect usage, billing exports, and business metrics.
2. **Allocate:** attribute costs to services, teams, environments, and owners.
3. **Forecast:** project low/base/high traffic scenarios.
4. **Optimize:** tune duration, memory, batching, retries, capacity, and data transfer.
5. **Govern:** set budgets, alerts, ownership, and periodic reviews.
6. **Learn:** compare cost per success before and after changes.

### 20.1. Tagging and Allocation

Tag resources using a consistent convention, for example:

~~~text
service = orders-api
team = commerce-platform
environment = production
cost_center = CC-042
owner = team-orders
module = cloud-serverless
~~~

Not all costs can be tagged directly. For shared databases, networks, or observability platforms, you need allocation rules based on usage metrics or agreed proportions.

Ensure tags are applied to functions, queues, state machines, log groups, storage, databases, and network resources where supported by the service. Audit untagged resources without an owner to prevent unallocated costs.

### 20.2. Budgets and Anomaly Detection

Establish:

- Budgets by service/team/environment.
- Alerts when forecasts exceed budget.
- Alerts when daily spend spikes abnormally.
- Tracking for cost per operation and cost per success.
- Tracking for retry rates, duration, and log volume.
- Reviews of unused reserved resources.
- Detection of test/staging resources left running too long.

A rising bill can stem from legitimate traffic, retry storms, log verbosity, egress, or provisioned resources. Alerts should be paired with usage metrics to pinpoint the root cause.

## 21. Optimizing Costs While Preserving SLOs

Optimization choices should be tied to root causes:

| Symptom | Optimization Direction |
|---|---|
| High duration due to CPU | Benchmark higher memory/CPU tiers |
| High duration due to slow APIs | Reasonable timeouts, connection reuse, reduce redundant calls |
| High retry rate | Fix root error, backoff/jitter, idempotency |
| Frequent small batches | Tune batching window and batch size |
| Large batches causing timeouts | Reduce batch size or handle partial failures |
| Cold latency violating SLO | Compare provisioned/min capacity against latency impact |
| High log volume | Structured logs, sampling, and retention |
| High egress/NAT | Optimize data paths and placement |
| High database cost | Query/index/pooling and capacity tuning |
| Idle reserved capacity | Adjust schedules and provisioned levels |

Do not optimize compute by increasing timeouts to avoid errors if that causes invocations to run longer and incur higher charges. Do not strip necessary logging or drop critical retries just to lower the bill.

Every change should be evaluated across both metrics:

\[
\Delta C = C_{\text{after}} - C_{\text{before}}
\]

\[
\Delta SLO = SLO_{\text{after}} - SLO_{\text{before}}
\]

A good change lowers cost per successful operation while still meeting latency, reliability, and correctness requirements.

## 22. Guardrails to Prevent Cost Surprises

Set limits and alerts for:

- Maximum function duration/timeout.
- Memory/CPU allocation.
- Reserved/max concurrency.
- Queue batch size and retry count.
- DLQ depth and redrive rate.
- Provisioned concurrency/min instances.
- Ephemeral storage and payload size.
- Log retention and trace sampling.
- Egress and cross-region transfer.
- Database connection pools and capacity.
- Daily/monthly budgets.
- Cost per successful operation.

Guardrails should align with business needs. For example, max concurrency protects the database but can cause backlogs to grow; alerts should report both downstream saturation and message age so operations understands the trade-off.

## 23. Function Cost Modeling Process

1. **Define the business unit.** Is one order, payment attempt, event, or report one operation?
2. **Map the execution path.** List all functions, queues, APIs, workflows, and downstream services.
3. **Collect traffic data.** Daily/hourly operations, bursts, growth, and seasonality.
4. **Measure runtime behavior.** Invocations, attempts, duration, memory/CPU, batch size, and cold starts.
5. **Estimate compute.** Calculate billable compute units per provider semantics.
6. **Calculate request and event charges.** Function, queue, gateway, and workflow operations.
7. **Add reserved capacity.** Provisioned concurrency, min instances, and enabled hours.
8. **Add network/observability/storage.** Egress, NAT, logs, traces, and retention.
9. **Allocate downstream costs.** Databases, caches, object storage, and external services.
10. **Build low/base/high scenarios.** State assumptions for retries, duration, batching, and traffic shape.
11. **Calculate cost per success.** Divide total allocated cost by unique completed operations.
12. **Reconcile against invoices.** Compare forecasts with billing exports and refine assumptions.
13. **Set budgets and alerts.** Monitor cost anomalies alongside usage/quality signals.
14. **Review after changes.** Compare cost, latency, reliability, and business outcomes.

## 24. Self-Check Questions

- Why does the number of business operations differ from the number of function invocations?
- Which components make up the cost of a serverless function?
- From which variables are GB-seconds or compute units calculated?
- Why must you check billing semantics before adding initialization duration?
- In what ways do retries increase costs?
- How does batch size affect invocation counts and retry costs?
- Why does increasing memory sometimes reduce compute costs?
- How do cold starts and provisioned capacity impact costs?
- How do traffic bursts affect concurrency and billing?
- What cost drivers exist for queues, API gateways, networking, and observability?
- Why is cost per successful operation more useful than cost per invocation?
- How should shared database costs be allocated?
- When should you compare FaaS against always-on containers?
- Which measure, allocate, forecast, and optimize steps does FinOps require?
- Which guardrails help detect abnormal cost increases?
