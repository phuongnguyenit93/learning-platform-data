# Monitoring AI Inference Quality, Performance, and Cost

In the **AI and Machine Learning on OCI** chapter of the **Oracle Cloud Infrastructure** module, deploying an endpoint is only the starting point of AI operations. The system must answer three questions simultaneously:

1. **Quality:** do outputs meet business requirements and use only authorized data?
2. **Performance:** how long do users wait, how many requests can the system handle, and can it recover from failures?
3. **Cost:** how much does one request, one processing flow, and one acceptable outcome cost?

An API returning HTTP 200 does not prove the answer is right. Low per-call cost also does not prove the system is efficient if it must retry repeatedly or most outputs require manual correction.

This lesson presents how to combine OCI Monitoring, Logging, service usage data, evaluation records, and cost tools to observe the entire inference flow. Diagrams, schemas, and illustrative thresholds are application designs, not default OCI configurations or SLA commitments.

## 1. Identify the right unit to monitor

### 1.1. A business request differs from a model call

A user's question may trigger multiple steps: authentication, retrieving data from Oracle Database, generating embeddings, calling a model, retrying, validating output, and responding.

Distinguish the following units:

| Unit | Meaning | Example |
| --- | --- | --- |
| **Logical request** | One business request to fulfill | User asks about warranty terms |
| **Model call** | One task invoking a model inside the flow | Generating embeddings or generating an answer |
| **Attempt** | One API call attempt for that task | First attempt times out; second succeeds |
| **Final response** | Output actually returned by the app to the user | Answer after validation and fallback handling |
| **Evaluation** | Assessment outcome for a specific output | Reviewer confirms answer is grounded |

If one logical request calls two models and each task retries, attempt count can be much higher than user request count. Counting every attempt as a "served user" distorts both success rate and unit cost.

### 1.2. Use three metric tiers

| Tier | Question | Illustrative metrics |
| --- | --- | --- |
| **Infrastructure and service** | Are endpoints, serving hosts, and dependencies healthy? | CPU/GPU, RAM, service errors, API latency |
| **Application flow** | How does a request complete end-to-end? | End-to-end latency, retries, timeouts, cache, tokens |
| **Business and quality** | Are outputs usable? | Accuracy, groundedness, pass rate, cost per passing outcome |

Lower-tier metrics help explain upper tiers, but cannot replace them. Low GPU utilization may indicate wasted capacity, or it may mean the application is waiting on a database. Wrong answers can stem from stale retrieved data even while the model itself operates normally.

## 2. Designing an observability flow on OCI

An illustrative architecture for an internal Q&A application can include:

~~~mermaid
flowchart TD
    U["User request"] --> A["Backend: access control and logical request ID"]
    A --> R["Retrieval: Oracle Database or knowledge base"]
    R --> M["OCI Generative AI or Data Science Model Deployment"]
    M --> V["Validate output and respond"]
    A --> T["Application telemetry"]
    R --> T
    M --> T
    V --> T
    M --> N["OCI service metrics"]
    T --> L["OCI Logging: events and correlation links"]
    T --> C["OCI Monitoring: custom metrics"]
    N --> C
    V --> E["Controlled evaluation and feedback store"]
    E --> Q["Aggregate quality by version and data slice"]
    Q --> C
    C --> AL["Dashboards, Alarms, and Notifications"]
    B["Cost Analysis and Cost Reports"] --> D["Cost reconciliation and allocation"]
    T --> D
    E --> D
~~~

Each arrow is an integration to build. OCI does not infer your business criteria, join late-arriving labels, or allocate shared costs to individual conversations automatically.

Operate on two cadences:

- **Near real-time:** errors, latency, call volume, tokens, retries, and estimated spend anomalies.
- **Batch or label-driven:** business accuracy, groundedness evaluation, final outcomes, and cost reconciliation.

A periodic evaluation job can aggregate outcomes, provided it clearly tracks which request time window it is evaluating.

## 3. Defining SLIs, SLOs, and quality criteria

An **SLI** is a measured indicator; an **SLO** is the internal target set for that indicator. Document the numerator, denominator, time window, and exclusions.

**Synthetic** example targets for a customer support application:

| Target | How it is measured | Interpretation conditions |
| --- | --- | --- |
| Technical completion at least 99% | Completed valid requests / total valid requests over 30 days | Timeouts and throttling failures must still count |
| End-to-end p95 at most 4 seconds | Latency distribution from backend receipt to completion | Report successes, errors, and timeouts separately |
| At least 95% of evaluated answers pass rubric | Passing outputs / evaluated rubric-applicable outputs | Record sample size, scope, and evaluation lag |
| Cost within business budget | Costs attributed to the same request set and time window | Distinguish estimates from reconciled billing |

These thresholds only illustrate how to write targets. Real targets must come from user expectations, risk levels, and system budgets.

### 3.1. Do not hide errors by altering the denominator

A malformed request may sit outside "valid requests", yet still must be tracked separately. Never exclude all 429s or timeouts from the denominator simply because the service returned no answer.

Similarly, correctly refusing an unauthorized request can be good quality behavior. However, refusing every question does not satisfy a Q&A system. Measure refusal accuracy, answerability, and task completion separately.

### 3.2. Separate user-experience targets from model targets

A model may finish in 1 second while the user waits 6 seconds due to retrieval and retries. Experience SLOs must measure at the application boundary rather than using model latency as a proxy for the whole flow.

For asynchronous inference, separate job submission time, queue wait time, and time until usable results exist. Successfully accepting a job does not mean the task is complete.

## 4. Measuring quality by problem type

### 4.1. Specialized AI Services and predictive models

Pick metrics matched to the output:

| Problem | Illustrative quality metrics | Additional checks needed |
| --- | --- | --- |
| Ticket or image classification | Per-label precision, recall, F1 | Rare classes and misclassification cost |
| Risk prediction | Discrimination quality, precision/recall at operating threshold | Score calibration and false-alarm cost |
| Numeric prediction | MAE or appropriate error metric | Units, high-error slices, and outliers |
| Invoice extraction | Field-level accuracy and rate of documents passing all required fields | Amounts, dates, and line-item consistency |
| Transcription | Word or character error per defined evaluation protocol | Language, accents, noise, and terminology |

Never use overall accuracy to mask poor performance on an important class. When 1% of requests belong to a rare class, a model predicting only the majority class achieves high accuracy while failing to detect what matters.

Confidence scores or model scores do not prove calibrated probabilities on their own. To use a score for automated decisions, evaluate it on representative data at real operating thresholds.

### 4.2. Generative AI: check multiple independent criteria

For model-generated answers, a rubric can include:

- **Factual accuracy:** statements align with authoritative data.
- **Groundedness:** claims requiring evidence are supported by supplied sources.
- **Citation accuracy:** citations point to the right document and support the corresponding claim.
- **Completeness:** addresses required parts of the request.
- **Structural compliance:** conforms to application schema or format.
- **Permission and policy compliance:** uses only authorized data and properly handles requests requiring refusal.

Valid JSON can contain wrong numbers. Existing citations do not automatically prove an answer is grounded.

You can define **task pass** as meeting all mandatory criteria for the task. A severe violation should never be "offset" by polite phrasing or concise wording.

### 4.3. RAG requires measuring both retrieval and generation

A retrieval-augmented generation flow must isolate at least:

1. Are sources up to date and is the requester permitted to read them?
2. Did retrieval locate relevant passages?
3. Did context passed to the model truncate away essential facts?
4. Did the answer use the evidence faithfully?

When a labeled dataset of questions and relevant documents exists, measure recall@k or ranking quality. Define "relevant" and the authoritative source corpus explicitly.

When retrieval finds no evidence, a model hallucinating an answer is a different failure from a model properly refusing. Dashboards must distinguish the two cases so teams fix the right stage.

### 4.4. Combining automated checks with human review

Schema checks, value bounds, and business arithmetic can be automated directly. For open-ended content, human reviewers or model-based judges can assist, provided agreement and scoring bias are audited.

If using a judge model:

- Pin judge model version, prompt, and rubric.
- Treat judged content as untrusted data; grant no tools or permissions beyond judging.
- Calibrate a subset of results against human reviewers.
- Track cost and latency of the evaluation process itself.

A model-judge score is a noisy measurement, not ground truth by default.

## 5. Collecting labels, feedback, and detecting quality shifts

### 5.1. Link evaluations to the exact served output

Labels may arrive hours or days later. Store links across:

~~~text
logical request ID
    -> final response ID or output version
    -> model, prompt, data, and configuration used
    -> label or evaluation
    -> label arrival timestamp and rubric version
~~~

Never regenerate an answer with today's model and attribute a past evaluation to it. If an output was edited after delivery, clarify which version reviewers are scoring.

For late-delivery prediction, new orders without delivery outcomes yet must never default to "correct prediction". Count only cases meeting label-maturity rules.

### 5.2. Report both quality and evaluation coverage

Two ratios have different meanings:

~~~text
Pass rate on evaluated set =
    passing results / validly evaluated results

Evaluation coverage =
    evaluated results / results in target monitoring set
~~~

Evaluating 100 easy questions out of 10,000 requests and reporting "99% quality" may not represent overall traffic.

Evaluation samples need an explicit design: random or stratified by language, request type, model, or risk tier. If oversampling error-prone groups, record sampling weights so results are not reported as an unadjusted overall rate.

Voluntary user feedback skews toward very satisfied or very dissatisfied users. It is a useful signal, not a full replacement for representative evaluation sampling.

### 5.3. Track by slice and version

Break quality down across meaningful dimensions such as:

- Model, deployment, prompt template, and knowledge base version.
- Language, document type, business route, or input-length bucket.
- Cache hit/miss, fallback path, and serving mode.
- Request creation window vs. label arrival window.

Shifting input lengths, missingness rates, or label distributions are **drift** signals requiring investigation. Drift does not automatically prove quality dropped; conversely, quality can degrade even before aggregate input distributions trigger alerts.

For small sample sizes, report counts and uncertainty rather than displaying percentages to several decimal places.

## 6. Measuring performance from the user's perspective

### 6.1. Timestamps to capture

| Metric | Suggested measurement boundary |
| --- | --- |
| **End-to-end latency** | Backend receives logical request until response returns or errors out |
| **Queue time** | Work enters queue until execution starts |
| **Retrieval latency** | Retrieval begins until context is assembled |
| **Provider round-trip latency** | Attempt dispatch starts until result or error returns |
| **Time to first token — TTFT** | Defined start mark until first content token in streaming mode |
| **Generation duration** | First content token until generation ends |
| **Post-processing latency** | Validation, normalization, and output finalization |

Clarify whether TTFT is measured at the model or at the application. Receiving a metadata or header packet is not necessarily when the user receives the first content token.

Oracle uses metrics such as TTFT, request latency, and throughput in Generative AI benchmarks. Performance depends on concurrency and input/output token distributions. Never treat benchmark figures as guarantees for a different application flow. [Dedicated AI Cluster Performance Benchmarks](https://docs.oracle.com/en-us/iaas/Content/generative-ai/performance.htm).

### 6.2. Using appropriate percentiles and distributions

- **p50** describes median experience.
- **p95/p99** expose slow tail requests.
- **Mean** helps some analyses but can hide very slow outliers.

Never add retrieval p95 and model p95 and call it end-to-end p95. Measure total duration per logical request and compute percentiles from that distribution.

Likewise, never average p95 values across multiple instances to estimate global p95. Proper aggregation requires raw distributions or mergeable histogram sketches.

Track durations separately for errors and timeouts. A timeout shows when the application stopped waiting, not exactly when the model finished computing.

### 6.3. Throughput, concurrency, and output length

Requests/second measures request rate over time; concurrency measures requests actively in flight. For LLMs, tokens/second also depends on whether you measure single-request speed or aggregate system throughput.

Two systems both serving 10 requests/second experience very different load if one generates 30 tokens per answer and the other generates 1,000 tokens.

During load testing, keep input/output distributions, cache hit ratios, bursts, and concurrency realistic to production targets. Track arrived, accepted, and completed request counts alongside queue depth; measuring only successful requests can hide overload.

## 7. Using native OCI metrics and logs within their true scope

### 7.1. OCI Data Science Model Deployment

Model deployment metrics emit in the **oci_datascience_modeldeploy** namespace; Oracle docs note these metrics are available automatically for created model deployments. [Model Deployment Metrics](https://docs.oracle.com/en-us/iaas/Content/data-science/using/metrics-model-deploy.htm).

| Typical metric | What to observe |
| --- | --- |
| **PredictRequestCount** | Predict invocation volume |
| **PredictLatency** | Predict latency in milliseconds |
| **CpuUtilization / MemoryUtilization** | CPU and memory pressure |
| **GPUCoreUtilization / GPUMemoryUtilization** | GPU usage when supported by shape |
| **PredictBandwidth** | Deployment network bandwidth usage |

Filter by **resourceId** to observe the exact deployment; some metrics offer additional dimensions like result or instance. Do not assume every metric supports every dimension.

Infrastructure metrics help pinpoint bottlenecks, but do not provide model precision, recall, or business accuracy. Different Data Science resource types emit different metric sets. [Data Science Metrics](https://docs.oracle.com/en-us/iaas/Content/data-science/using/metrics.htm).

### 7.2. OCI Generative AI

Generative AI metric documentation covers hosting dedicated AI clusters and endpoints, with metrics such as:

| Metric | Meaning |
| --- | --- |
| **TotalInvocationCount** | Invocation count |
| **InvocationLatency** | Invocation processing duration |
| **InputTokenCount / OutputTokenCount** | Processed input and output tokens |
| **ClientErrorCount / ServerErrorCount** | Client-side or service-side errors |

Metric names are listed by Oracle in [Metric Details in Generative AI](https://docs.oracle.com/en-us/iaas/Content/generative-ai/metric-details.htm). The query namespace is **oci_generativeai**. [Creating a Query for Generative AI Metrics](https://docs.oracle.com/en-us/iaas/Content/generative-ai/create-query.htm).

Verify the actual metrics available for your serving mode, model, and resources. Do not assume every on-demand call emits the exact same metrics or dimensions as a dedicated endpoint. Application telemetry remains essential for observing logical requests and multi-service flows.

For other specialized AI Services, consult each service's own metric documentation; never query the Generative AI namespace expecting all AI services to appear there.

### 7.3. Logging requires configuration and its own lifecycle

Data Science Logging integration is optional. Model deployments offer access logs with metadata such as timestamp, status, model latency, and request ID; predict logs come from code inside the model artifact. [Data Science Logs](https://docs.oracle.com/en-us/iaas/Content/data-science/using/log-about.htm).

Access logs help link a request to an endpoint error. They do not become a correctness evaluation dataset on their own. Predict logs also contain no quality signals unless artifact code emits what is needed.

Distinguish three sources:

- **Metrics:** fast aggregates powering charts and alarms.
- **Logs:** detailed events for root-cause investigation.
- **Traces or correlation links:** connecting steps of one logical request across components.

There is no need to dump full prompts and responses into shared logs just to count calls or measure latency.

## 8. Designing application telemetry

### 8.1. Capture enough information to join all three dimensions

An event for a single attempt can contain:

~~~json
{
  "eventType": "inference_attempt_completed",
  "eventId": "event-demo-0042-02",
  "logicalRequestId": "request-demo-0042",
  "modelCallId": "call-demo-0042-generation",
  "attemptId": "attempt-02",
  "timestamp": "2026-11-21T02:15:00Z",
  "environment": "prod",
  "route": "support-rag",
  "modelId": "APPROVED_MODEL",
  "promptVersion": "support-v5",
  "knowledgeVersion": "kb-r12",
  "providerRequestId": "SERVICE_REQUEST_ID",
  "outcome": "SUCCESS",
  "httpStatus": 200,
  "providerRoundTripMs": 1400,
  "inputTokens": 900,
  "outputTokens": 200,
  "usageStatus": "PROVIDER_REPORTED",
  "priceVersion": "pricing-reference-v3",
  "qualityStatus": "PENDING"
}
~~~

This is an application-designed illustrative schema, not an OCI API response. Numbers and identifiers are synthetic.

Record logical request completion in a separate event with total duration, attempt count, terminal status, cache/fallback flags, and final response ID. Later evaluations join onto that final response ID.

If an attempt times out without token usage, mark usage status as **unknown** or labeled estimate. Never turn unknown usage into 0 and report total cost as exact.

### 8.2. Measure with the right clock and record failures too

Pseudocode:

~~~text
when logical request arrives:
    generate logical request ID
    capture start time using a monotonic duration clock
    authenticate and validate inputs

    for each required model call:
        execute attempts within retry and time budgets
        for each attempt:
            measure duration
            collect usage if returned by service
            log outcome or sanitized error
            retain service-returned request ID when present

    validate output and select final response
    in finalization always record:
        logical request status
        end-to-end duration
        call counts, retries, cache, and fallback flags
        output identifier for later evaluation linkage
~~~

UTC timestamps align events across systems; monotonic clocks accurately measure elapsed intervals within a process. Never rely solely on wall-clock differences between two machines to measure latency.

Telemetry emitters also need error handling and backpressure. Never let slow log writes stall the response path, while still monitoring dropped or failed telemetry events.

### 8.3. Control dimensions and sensitive data

Metric dimensions should have bounded, managed value sets such as environment, route, model, or outcome category. Logical request IDs, emails, phone numbers, and full prompts are unsuitable as metric dimensions.

Every dimension combination creates additional metric time series. Keep high-cardinality IDs in controlled logs or event stores; send only needed aggregate slices to Monitoring.

Custom namespaces must not use the reserved prefixes **oci_** or **oracle_**. For example, you might choose **aiapp_inference** for application metrics. [Publishing Custom Metrics](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/publishingcustommetrics.htm).

Detailed evaluation contents should live in access-controlled storage with appropriate retention. Redaction, encryption, or ID substitution does not automatically eliminate all re-identification risks.

## 9. Querying metrics and avoiding bad aggregations

### 9.1. MQL query examples

In Metrics Explorer, select the right region, compartment, and namespace before running queries.

Example for **oci_datascience_modeldeploy**:

~~~text
PredictLatency[5m]{resourceId = "REPLACE_WITH_DEPLOYMENT_OCID", result = "Success"}.mean()
~~~

This query illustrates average predict latency across matching datapoints in a 5-minute window. It is not end-user p95.

For custom namespace **aiapp_inference**, assuming the application emits **AppLatencyMs** as properly sampled per-logical-request latency observations:

~~~text
AppLatencyMs[5m]{environment = "prod", route = "support-rag"}.percentile(0.95)
~~~

If the application emits **LogicalRequestCount** with value 1 per unique completion event:

~~~text
LogicalRequestCount[5m]{environment = "prod", route = "support-rag"}.sum()
~~~

Interval syntax, statistics, and dimensions are documented in [Monitoring Query Language Reference](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Reference/mql.htm).

### 9.2. Count, sum, and percentile are not interchangeable

- **count()** counts observations received in the window.
- **sum()** adds the values of those observations.
- **percentile()** estimates percentiles over the actual datapoints submitted.

If each datapoint already represents a 1-minute request total, `count()` counts datapoints, not requests. If a metric is a cumulative counter, summing cumulative snapshots directly also yields the wrong delta.

Similarly, if each datapoint is already a window's p95, taking a percentile over those p95s does not recover the true global p95 across all requests. Design distribution storage or aggregation properly from the start.

With sampled telemetry, sample size and sampling method affect accuracy. At large scale, consider proper distribution sketches and analytics stores rather than dropping data randomly under load.

### 9.3. Late-arriving quality data requires different handling

Monitoring enforces timestamp constraints when publishing datapoints. Do not assume labels arriving days later can be published back onto the original request's timestamp. [Publishing Custom Metrics — Considerations](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/publishingcustommetrics.htm).

You can store label history in an evaluation store and emit aggregated quality metrics at current calculation time. Reports must clearly state the request cohort, label completeness, and evaluation time. Never conflate "quality of today's requests" with "labels recorded today".

## 10. Calculating inference cost across the entire flow

### 10.1. Distinguish operational estimates from reconciled billing data

| Source | Purpose |
| --- | --- |
| Per-attempt usage or tokens | Fast estimation and spotting anomalous call loops |
| Provisioned capacity and runtime hours | Estimating dedicated infrastructure cost |
| Cost Analysis | Viewing spend by service, compartment, or tag |
| Cost Reports | Reconciling consumption, rates, and charges at detailed granularity |

Cost Analysis supports filtering and grouping spend; billing records arrive with delay and are unsuitable as an instant per-request circuit breaker. [Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

OCI provides Cost Reports in native and FOCUS formats; when reconciling, account for late-arriving usage and adjustment lines. Never blindly sum downloaded files while ignoring line identifiers and adjustments. [Cost Reports](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm).

Never present an application-side cost estimate as an exact invoice amount. Attach rate-card version, currency, billing units, and applicable discount or allocation rules.

### 10.2. Token formulas apply only under matching billing models

If a model has separate prices per million input and output tokens:

~~~text
C_generation =
    input_tokens / 1,000,000 × P_input
  + output_tokens / 1,000,000 × P_output
~~~

Example with 8 million input tokens and 2 million output tokens:

~~~text
C_generation = 8 × P_input + 2 × P_output
~~~

This is an illustrative formula, not an OCI price list. Verify the actual model and SKU, including cached tokens or other billing units if applicable.

Never divide character counts by a fixed constant to settle Vietnamese token billing. Prefer API-reported usage; local counting requires the exact matching tokenizer and must be labeled an estimate prior to reconciliation.

### 10.3. Dedicated or self-hosted models carry capacity costs

For dedicated serving resources, costs tie to provisioned capacity and commitment duration rather than solely call counts:

~~~text
Infrastructure cost allocated per request =
    capacity cost in period / requests attributed to that capacity
~~~

Define allocation rules when multiple applications share capacity: by tokens, GPU time, resource utilization, or an agreed internal rule. Allocated unit cost does not automatically equal the marginal cost of one additional request.

A cache-hit request may skip calling the model yet still consume backend, cache, storage, and network resources. An idle deployment can still incur capacity charges. Avoid double-counting the same cost once cluster capacity has been allocated.

### 10.4. Include retries and auxiliary steps

End-to-end flow cost can include:

~~~text
C_total =
    C_model
  + C_retrieval
  + C_backend
  + C_storage_and_network
  + C_observability
  + C_evaluation
~~~

Keep these cost buckets distinct to avoid double-counting. Embeddings, reranking, retries, agent tool calls, and judge models can all generate extra consumption.

For canceled or timed-out requests, never assume server-side work stopped and incurred zero cost. Collect usage evidence when returned and keep uncertain records flagged for reconciliation.

## 11. Tracking cost per passing outcome

### 11.1. Two denominators yield two different conclusions

~~~text
Cost per logical request =
    cost of request set / total logical requests in that set

Cost per passing outcome =
    cost of request set / passing outcomes in that same set
~~~

Include costs of failed requests and failing outputs in the numerator if they belong to the same workload set. Otherwise, a low-quality system looks artificially cheaper by ignoring wasted spend.

If passing outcomes equal 0, the metric is undefined; never display 0 as though the system cost nothing.

### 11.2. Example comparing two configurations

The table below uses synthetic data, with cost in **hypothetical currency units** allocated over the same scope. All 10,000 requests in each configuration were evaluated against the same rubric.

| Metric | Configuration A | Configuration B |
| --- | ---: | ---: |
| Logical requests | 10,000 | 10,000 |
| Technical completions | 9,600 | 9,800 |
| Business-passing outcomes | 8,640 | 7,000 |
| Total cost | 120 | 100 |
| Cost / logical request | 0.012 | 0.010 |
| Cost / 1,000 passing outcomes | About 13.89 | About 14.29 |

Configuration B has lower cost per request yet higher cost per 1,000 passing outcomes. Selection must also weigh performance SLOs, minimum quality bars, and critical failure modes.

If evaluating only a small sample, never divide total system cost by passing counts inside the sample and call it overall cost. Either compute cost strictly within the allocated sample, or project system-wide with published methodology and uncertainty bounds.

### 11.3. Attributing cost to owners

Compartments and defined tags can attribute resource spend to projects, environments, or owning teams. Tags must never contain personal data. [Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

Resource tags on a shared deployment cannot break out costs per individual end user. That requires application telemetry and attribution rules.

During reconciliation, align time windows, UTC conventions, regions, currencies, and service scopes. Separate inference operating spend from training, experimentation, or evaluation spend when reporting by purpose.

## 12. Dashboards and alarms must drive action

### 12.1. A dashboard should connect all three dimensions

| Display group | Contents |
| --- | --- |
| Volume and health | Logical requests, attempts, errors, timeouts, throttling, queue depth |
| Experience | End-to-end p50/p95/p99, TTFT if applicable, breakdown by length |
| Resources | CPU/GPU, RAM, bandwidth, instance count, or capacity |
| Quality | Pass rate, error categories, sample size, coverage, label lag |
| Cost | Tokens, near-real-time estimate, reconciled cost, cost per passing outcome |
| Versions | Model, prompt, data, config, and rollout markers |

Plot charts on a shared timeline and annotate model changes, traffic shifts, or knowledge base updates. When quality drops after a change, inspect data slices and evaluation coverage before jumping to conclusions.

### 12.2. Alarms need windows, sample sizes, and owners

| Signal | Conditions to clarify | Suggested action |
| --- | --- | --- |
| Latency spike | Duration and affected slices | Inspect queues, retrieval, tokens, and compute |
| Errors or 429s rising | Per-attempt vs. per-logical-request | Bound retries, check quotas/capacity, and fallback |
| Quality drop | Sufficient sample, same rubric, label maturity | Investigate data and versions; consider rollback |
| Sudden token surge | Traffic growth vs. tokens/request | Check loops, prompts, and call fan-out |
| Unit cost rising | Same allocation scope and quality baseline | Look for retries, idle capacity, or pass-rate drop |
| Telemetry missing | Is traffic or heartbeat expected? | Check exporter, IAM, networking, and ingestion pipeline |

Quantitative thresholds should be grounded in baselines. Severe incidents like data leaks require severity-based escalation immediately without waiting for sample size thresholds.

Monitoring supports absence alarms to detect when expected metrics stop arriving. Distinguish zero traffic from broken observability pipelines. [Creating an Absence Alarm](https://docs.oracle.com/en-us/iaas/Content/Monitoring/Tasks/create-alarm-absence.htm).

After creating alarms, test Notification topics and recipients in an appropriate environment. An alarm stuck in firing state that never reaches an owner creates zero response capability.

### 12.3. Budgets do not automatically shut off spend

OCI Budgets set soft thresholds and emit spend alerts; they do not block individual API calls or shut down clusters automatically. [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm).

For faster enforcement, applications can apply:

- Input and output length caps.
- Model call, retry, and time caps per logical request.
- Usage quotas per group or route.
- Permissions restricting resource creation or scaling.
- Graceful degradation to lower-cost paths or queues upon crossing agreed thresholds.

Service limits or quotas do not automatically equal a maximum dollar spend cap. Provisioned resources and retained data can continue accruing charges.

## 13. Optimizing while preserving quality and availability

| Change | Expected benefit | What must be re-measured |
| --- | --- | --- |
| Trim context | Fewer tokens and faster processing | Whether required evidence or facts are lost |
| Use a smaller model on selected routes | Lower consumption or latency | Per-slice quality and cost per passing outcome |
| Caching | Fewer redundant calls | Freshness, permission boundaries, and stale-hit errors |
| Rerank before generation | More relevant context | Extra step cost/latency and final answer quality |
| Batching | Higher efficiency for background tasks | Wait time and business deadlines |
| Add capacity or scale out | Shorter queues under load | Latency, idle capacity, and allocated cost |
| Reduce retries | Curb load amplification | Completion rate within deadline |
| Fallback | Maintain continuity on failures | Quality and consistency across serving paths |

Caches must include factors governing output validity such as permissions, data version, and model/prompt version when relevant. Never share answers built from restricted data across users with different access rights.

Retries need bounded attempts and appropriate backoff. Unlimited retries during 429 spikes worsen both cost and latency.

When rolling out a new configuration, compare equivalent traffic slices, keep versions controlled, and set rollback criteria spanning quality, performance, and cost. For shadow testing, account for the extra call volume and cost incurred without returning results to users.

Never switch regions solely to cut latency or find capacity while ignoring data-transfer rules, model availability, and application dependencies.

## 14. IAM, networking, and observability data lifecycle

Users viewing metrics, staff reading evaluation contents, workloads emitting metrics, and engineers editing alarms all need different permissions.

Example policy to read metrics in a compartment:

~~~text
Allow group AiObservers to read metrics in compartment ai-prod
~~~

This permission does not grant reading prompts, log contents, evaluation buckets, or managing endpoints. Namespaces can be scoped where needed; Monitoring policies are documented in [Securing Monitoring](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/monitoring_security.htm).

Workloads emitting custom metrics must authenticate and hold proper permissions. When using instance principals or resource principals, scope dynamic groups tightly by workload and environment; never embed personal API keys in code just to emit telemetry.

Verify network paths separately to Monitoring ingestion, Logging, evaluation stores, and model services. A workload in a private subnet needs an appropriate route to each destination.

Observability data lifecycle design must specify:

- Which fields belong in shared logs vs. restricted evaluation stores.
- Who can inspect raw content vs. aggregate numbers only.
- Retention periods for prompts, responses, retrieved sources, and labels.
- How derived copies in logs, objects, reports, and backups are deleted per policy.
- Cost of logs, metrics, traces, and evaluation calls.

Retain enough evidence for investigations without storing every payload indefinitely by default.

## 15. Procedure for investigating an anomaly

Example: a dashboard shows cost per passing outcome spiked over the past two days.

1. **Verify the measurement:** same data window, currency, allocation rule, rubric, and label completeness?
2. **Separate volume from unit consumption:** did request count rise or did tokens/request rise?
3. **Check amplification:** how did attempts/request, retries, agent steps, and cache hits change?
4. **Cross-check quality:** which routes, languages, or input slices saw more failures?
5. **Audit versions:** did model, prompt, knowledge base, or configuration change?
6. **Inspect performance and resources:** queue depth, timeouts, database latency, CPU/GPU, and idle capacity.
7. **Check reconciled billing:** are there late-arriving records, adjustments, or newly allocated resources?
8. **Apply controlled remediation:** fix root causes, cap amplification, roll back, or adjust capacity based on evidence.
9. **Confirm after change:** did quality, performance, and cost all return to target?

For example, a new prompt injecting full conversation history on every turn can raise both tokens and latency. Blindly truncating history can hurt quality. The right fix keeps useful context and re-evaluates on representative data.

## 16. Hands-on: building a minimal monitoring suite

Practice in a learning compartment using synthetic or authorized data. The steps below are guidance for learners, not operations already executed on a tenancy.

### 16.1. Choose a task and define measurements

1. Choose a Data Science endpoint or supported Generative AI flow.
2. Define logical requests, model calls, attempts, and final responses.
3. Write a concise rubric with mandatory pass criteria.
4. Choose SLIs for completion, latency, quality, and cost.
5. Document formulas, units, denominators, and windows for each indicator.

### 16.2. Collect and correlate data

1. Observe native resource metrics in the exact namespace, region, and compartment.
2. Configure appropriate logs and emit secret-free application telemetry.
3. Send a representative set of requests carrying correlation IDs.
4. Record successes, controlled errors, retries, and fallbacks.
5. Join evaluations to the exact final outputs.
6. Trace several requests from application records to service request IDs where available.

### 16.3. Build dashboards and test alerts

1. Plot logical requests alongside attempts.
2. Plot end-to-end latency alongside service latency.
3. Display pass rate alongside sample size and coverage.
4. Display token counts, estimated cost, and reconciliation status.
5. Create an alarm in a test environment with verifiable trigger conditions.
6. Test both owner notifications and telemetry-missing scenarios.

### 16.4. Reconcile and compare a change

1. Use the same request set or equivalent slices to compare two configurations.
2. Record model, prompt, and dataset versions.
3. Compute cost per request and cost per passing outcome over the same scope.
4. Compare performance, quality, and critical error slices.
5. Label clearly which figures are estimates and which are reconciled.
6. Inspect resource states and log lifecycles after finishing practice.

An observability suite proves its worth when it explains **which outputs degraded, which step slowed down, which consumption driver grew, and which change restores targets**. That is the foundation for operating AI inference on OCI with controllable quality, availability, and cost.
