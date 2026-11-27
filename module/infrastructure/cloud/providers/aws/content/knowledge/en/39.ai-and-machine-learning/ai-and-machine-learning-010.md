# Choosing Inference Endpoints, Batch Processing, and Scaling Strategies

## Learning Objectives

After training or selecting a machine learning model, the system must expose a way to invoke the model that fits the application. Some models must respond within tens of milliseconds to support real-time decisions; some process large images, videos, or documents over several minutes; and others only run across millions of records on a nightly schedule. Using the same endpoint type for every case often leads to high costs, missed latency targets, or wasted resources.

In the AWS ecosystem, Amazon SageMaker AI offers multiple inference deployment options: real-time endpoints, serverless endpoints, asynchronous endpoints, and Batch Transform. Endpoints can also use autoscaling, inference components, multi-model hosting, and deployment guardrails. For managed foundation models, Amazon Bedrock provides on-demand inference, Provisioned Throughput, batch inference, and cross-Region inference profiles. Each option addresses a different workload pattern.

This lesson belongs to the **AI and machine learning** chapter of the CLOUD_PROVIDERS_AWS module. It helps learners choose model serving modes, size capacity and scale with load, protect endpoints during model updates, measure performance, and control costs.

After this lesson, you will be able to:

- Distinguish between online inference, asynchronous inference, and batch inference.
- Choose between real-time, serverless, asynchronous, or Batch Transform on SageMaker AI.
- Distinguish SageMaker Batch Transform from Amazon Bedrock batch inference.
- Determine when to use Bedrock on-demand, Provisioned Throughput, or inference profiles.
- Estimate throughput, concurrency, queue backlog, and reserve capacity.
- Design horizontal scaling, vertical scaling, scale-to-zero, and provisioned concurrency.
- Select CPU, GPU, or accelerator instances based on model characteristics and benchmarks.
- Use Inference Recommender and load tests to identify suitable configurations.
- Deploy models using blue/green, canary, or linear traffic shifting.
- Monitor latency, invocations, throttling, queues, error rates, and costs.
- Design IAM, VPC, S3, and KMS permissions for inference flows.
- Build runbooks and production readiness checklists.

## 1. Inference Is the Prediction Serving Stage

Training produces a model artifact or registered model. Inference brings that model into an application to accept inputs and return predictions.

An inference flow typically consists of these steps:

1. The application builds a request containing input data.
2. An API or SDK sends the request to a model endpoint or inference service.
3. The runtime checks permissions, receives the request, and forwards data to the model container or model provider.
4. The model performs preprocessing, forward pass, and postprocessing.
5. Results are returned directly, written to S3, or delivered via callback/notification.
6. The system emits metrics, logs, and traces to track operational health.

An inference architecture must answer four questions:

- **Latency:** how quickly must results arrive?
- **Traffic:** do requests arrive steadily, in bursts, or on a schedule?
- **Payload and compute:** is data small or large, and does the model run for milliseconds or minutes?
- **Cost:** must capacity remain warm, or can requests wait for available resources?

No single deployment mode is optimal for every workload. Start from SLOs and traffic patterns before choosing an endpoint.

## 2. Distinguishing Online, Asynchronous, and Batch Inference

| Processing mode | How requests are sent | How results are received | Examples |
|---|---|---|---|
| Online synchronous | Single request to an endpoint | Prediction returned in the same request | Classifying a transaction at checkout |
| Asynchronous | Request submitted to a queue | Output location or notification received later | Document OCR, image/video analysis |
| Batch | Prepared dataset submitted | Outputs written as a set of files | Scoring all customers nightly |

Online inference fits when the application needs an immediate decision. Asynchronous inference fits when individual requests still need separate outputs but processing takes long or payloads are large. Batch inference fits when many records can be processed independently and users do not need immediate responses.

A single pipeline can combine all three. For example, an API uses a real-time endpoint for new transactions, an asynchronous endpoint processes attached documents, and Batch Transform recomputes scores for all customers overnight.

## 3. Four Inference Options on SageMaker AI

SageMaker AI offers four primary hosting options:

| Option | Reference payload | Reference processing time | Suitable traffic |
|---|---:|---:|---|
| Real-Time Inference | Up to 25 MB | 60 seconds for standard responses; streaming can reach 8 minutes | Continuous traffic needing low, predictable latency |
| Serverless Inference | Up to 4 MB | Up to 60 seconds | Intermittent traffic with idle periods, tolerating cold starts or using provisioned concurrency |
| Asynchronous Inference | Up to 1 GB | Up to 60 minutes | Individual requests that can wait in a queue |
| Batch Transform | Datasets can reach GBs and jobs can run hours/days | Job execution duration | Offline workloads with many pre-collected records |

The limits above are published service limits, not application latency targets. Actual payload sizes, models, containers, and Regions can affect usability. Verify quotas and feature compatibility before designing.

## 4. Real-Time Inference: Synchronous Endpoints

Real-Time Inference provisions a managed REST endpoint and keeps compute instances ready to serve requests. This is the standard choice for APIs needing low latency or high throughput with relatively steady traffic.

Characteristics:

- The endpoint stays online continuously with one or more instances.
- Applications call `InvokeEndpoint` and receive synchronous responses.
- You can pick CPU, GPU, or accelerator instance types suited to the model.
- Supports traffic-based autoscaling.
- Supports deploying multiple production variants to split traffic across models.
- Supports enabling data capture and enhanced metrics where supported.

Example: a payment application sends transaction features to a fraud detection model. The API needs the score before approving or requesting extra verification. If the endpoint is unavailable or latency breaches SLO, checkout slows down.

### 4.1. Calling a Real-Time Endpoint with Boto3

~~~python
import json
import boto3

runtime = boto3.client("sagemaker-runtime", region_name="ap-southeast-1")

payload = {
    "transaction_amount": 1250000,
    "merchant_category": "electronics",
    "account_age_days": 420
}

response = runtime.invoke_endpoint(
    EndpointName="fraud-detection-prod",
    ContentType="application/json",
    Accept="application/json",
    Body=json.dumps(payload).encode("utf-8")
)

result = json.loads(response["Body"].read())
print(result)
~~~

The application role needs `sagemaker:InvokeEndpoint` on the endpoint ARN. If using streaming responses, both the API and client must support the streaming protocol. Never write sensitive data in debug logs of requests/responses.

### 4.2. When Is Real-Time Not Suitable?

Do not keep a real-time endpoint running just to execute once a day. Endpoints maintain compute capacity and incur charges even during zero-traffic periods. For large payloads or lengthy inference, synchronous requests can time out or hold connections open too long. When applications can receive results later, asynchronous or batch is usually more appropriate.

## 5. Serverless Inference: Scaling per Request

Serverless Inference removes the operational burden of selecting and managing instance counts. SageMaker AI provisions compute on demand when requests arrive and bills by processing duration and allocated resources.

Suitable when:

- Traffic is intermittent or has long idle gaps.
- Models and containers fit within serverless limits.
- Payloads are small, up to 4 MB per current limits.
- Requests finish within a maximum of 60 seconds.
- The application tolerates cold-start latency variation, or configures provisioned concurrency.

Key parameters:

| Parameter | Meaning |
|---|---|
| `MemorySizeInMB` | Memory allocated to the endpoint; tiers of 1, 2, 3, 4, 5, or 6 GiB |
| `MaxConcurrency` | Maximum concurrent invocations for the endpoint; current limit up to 200 |
| `ProvisionedConcurrency` | Pre-warmed concurrency to reduce cold starts; cannot exceed `MaxConcurrency` |

On-demand serverless scales up on traffic and scales down when idle. If steadier latency is needed during peak hours, you can allocate Provisioned Concurrency and autoscale that concurrency by schedule or metric.

### 5.1. Serverless Configuration Example

~~~python
import boto3

sm = boto3.client("sagemaker", region_name="ap-southeast-1")

response = sm.create_endpoint_config(
    EndpointConfigName="sentiment-serverless-config",
    ProductionVariants=[
        {
            "VariantName": "AllTraffic",
            "ModelName": "sentiment-model",
            "ServerlessConfig": {
                "MemorySizeInMB": 4096,
                "MaxConcurrency": 40,
                "ProvisionedConcurrency": 5
            }
        }
    ]
)

print(response["EndpointConfigArn"])
~~~

This example illustrates only the API structure. The model must be created beforehand; then create the endpoint from the endpoint configuration. Verify serverless quotas by Region, model/container compatibility, and account-level concurrency quotas.

### 5.2. Cold Starts and Provisioned Concurrency

When an endpoint lacks warm capacity, SageMaker must initialize compute and the container before serving requests. This startup delay can elevate p95/p99 latency. Provisioned Concurrency keeps a baseline concurrency warm to mitigate that impact, though it incurs charges even when unused.

Do not set Provisioned Concurrency equal to peak concurrency if peaks last only a few minutes. Use traffic profiles and schedules to size the baseline, then autoscale reserve concurrency.

## 6. Asynchronous Inference: Queueing Requests and Returning Results Later

Asynchronous Inference accepts requests, places them in a queue, and processes them as endpoint capacity becomes available. Results are written to Amazon S3; applications can use SNS notifications or poll the output location to retrieve results.

Suitable when:

- Payloads are large, up to 1 GB.
- A single request can take up to 60 minutes to process.
- The application does not require an immediate response within the same HTTP call.
- Traffic is bursty and queueable.
- The endpoint can scale down to 0 instances when the queue is empty.

Typical flow:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant API as SageMaker Runtime
    participant Q as Async Queue
    participant EP as Endpoint instances
    participant S3 as Amazon S3
    participant SNS as SNS notification
    App->>API: InvokeEndpointAsync (S3 input)
    API->>Q: Enqueue request
    API-->>App: OutputLocation / InferenceId
    Q->>EP: Deliver request when capacity is ready
    EP->>S3: Write inference result
    EP->>SNS: Notify completion (optional)
    SNS-->>App: Result is ready
    App->>S3: Read output object
~~~

Requests typically point to an input object in S3. Output paths can be configured per endpoint. You can set a request TTL to bound queue wait time and an invocation timeout to bound processing duration.

### 6.1. Sending an Asynchronous Request

~~~python
import boto3

runtime = boto3.client("sagemaker-runtime", region_name="ap-southeast-1")

response = runtime.invoke_endpoint_async(
    EndpointName="document-ocr-async",
    InputLocation="s3://ml-input-prod/ocr/job-2026-11-20/document-001.pdf",
    ContentType="application/pdf",
    Accept="application/json",
    InvocationTimeoutSeconds=3600,
    RequestTTLSeconds=21600
)

print(response["InferenceId"])
print(response["OutputLocation"])
~~~

The runtime calling role needs `sagemaker:InvokeEndpointAsync`. The endpoint execution role needs permissions to read input objects and write output objects in S3. If using SNS notifications, ensure appropriate publish permissions and a topic policy allowing the endpoint to publish.

### 6.2. Queue Backlog and Scale-to-Zero

Async endpoints can scale instance counts down to 0 when no requests exist. This eliminates idle compute costs, though new requests must wait for the endpoint to scale back up.

Key metrics:

- `ApproximateBacklogSize`: number of queued or in-flight requests.
- `ApproximateBacklogSizePerInstance`: backlog divided by active instance count.
- `ApproximateAgeOfOldestRequest`: age of the oldest queued request.
- `HasBacklogWithoutCapacity`: equals 1 when requests are queued while the endpoint has zero instances.

To scale from 0, configure a policy reacting when a backlog appears while capacity is 0. Relying solely on target tracking for backlog-per-instance may fail to bootstrap instances from 0 due to division behavior. AWS provides dedicated guidance for scaling up from zero.

Scale-to-zero cuts costs while increasing completion time for the first request. If SLOs permit waiting, it is a great fit; if fast responses are required, keep minimum capacity or choose a real-time endpoint.

## 7. Batch Transform: Processing Offline Datasets

Batch Transform runs inference on data stored in S3 without maintaining an always-on endpoint. SageMaker launches compute instances for the job, reads inputs, distributes work, and writes outputs back to S3.

Suitable when:

- A large dataset is already prepared.
- Immediate per-request responses are unnecessary.
- You want scheduled scoring or historical backfills.
- You want to run preprocessing/inference as a job and then release compute.

Example: every night the system computes propensity scores for 15 million customers. Results are written as S3 files for downstream analytics and campaign systems.

### 7.1. Batch Transform Flow

1. Prepare input files in S3.
2. Select a created SageMaker model.
3. Choose instance type and instance count.
4. Configure input content type, split strategy, and batch strategy.
5. Create the Transform Job.
6. SageMaker distributes input objects/records across compute instances.
7. Model containers process the data.
8. Outputs are written back to S3 in corresponding files.
9. The job finishes and compute is released.

Batch Transform does not expose an endpoint for applications to call continuously. If the application must send individual requests as they arrive, choose real-time, serverless, or asynchronous.

### 7.2. Creating a Batch Transform Job with Boto3

~~~python
import boto3

sm = boto3.client("sagemaker", region_name="ap-southeast-1")

response = sm.create_transform_job(
    TransformJobName="customer-score-20261120",
    ModelName="customer-propensity-model",
    TransformInput={
        "DataSource": {
            "S3DataSource": {
                "S3DataType": "S3Prefix",
                "S3Uri": "s3://ml-input-prod/customer-features/2026-11-20/"
            }
        },
        "ContentType": "text/csv",
        "SplitType": "Line",
        "CompressionType": "None"
    },
    TransformOutput={
        "S3OutputPath": "s3://ml-output-prod/customer-score/2026-11-20/",
        "Accept": "text/csv",
        "AssembleWith": "Line"
    },
    TransformResources={
        "InstanceType": "ml.m5.2xlarge",
        "InstanceCount": 4
    },
    BatchStrategy="MultiRecord",
    MaxConcurrentTransforms=4,
    MaxPayloadInMB=6
)

print(response["TransformJobArn"])
~~~

Illustrative example. The model container must support the chosen input/output formats. Payload and concurrent transform parameters must adhere to API limits; `MaxPayloadInMB` cannot exceed 100 MB, and the product of `MaxConcurrentTransforms` and `MaxPayloadInMB` also cannot exceed 100 MB.

### 7.3. Partitioning Data to Utilize Multiple Instances

SageMaker distributes S3 objects across instances. When inputs span multiple files, instances process different objects in parallel. If there is only a single huge file and input splitting cannot distribute it well, some instances may sit idle.

Partition data into multiple reasonably sized files, choose an appropriate `SplitType`, and verify how the model container handles records. CSVs with embedded newlines require special handling because Batch Transform does not support them with `SplitType=Line`.

`MaxConcurrentTransforms`, `BatchStrategy`, and `MaxPayloadInMB` tune how many records reach the container per request. Raising concurrency does not always speed up a job: containers can saturate CPU, memory, or GPU, while oversized requests can cause timeouts or payload errors.

## 8. Amazon Bedrock: Choosing On-Demand, Provisioned, or Batch

If an application uses foundation models managed by Amazon Bedrock, there is no need to spin up a SageMaker endpoint for that model. You can invoke the Bedrock Runtime API and choose an appropriate capacity mode.

| Bedrock mode | Best fit | Characteristics |
|---|---|---|
| On-Demand inference | Variable traffic, pay-per-use | Calls models within model/Region quotas and capacity |
| Provisioned Throughput | High, steady workloads needing pre-allocated throughput | Purchases model units for a term on supported models |
| Batch inference | Many prompts that can run asynchronously | Inputs/outputs stored in S3; jobs run as capacity allows |
| Cross-Region inference profile | When requests may be processed in other Regions within the profile | Service routes requests across supported Regions |

Bedrock batch inference does not support provisioned models per current documentation. Batch jobs process prompts from S3 files and write results to S3; completion time depends on model and capacity. Do not assume a batch job completes on an HTTP request timescale.

Cross-Region inference profiles can boost capacity availability and expand processing regions, though you must check data residency rules, profile-supported Regions, and organizational data policies. If data must stay in one specific Region, do not select a cross-Region routing profile.

SageMaker Batch Transform and Bedrock batch inference are both offline jobs, but differ in model hosting and APIs. Pick the service corresponding to where the model is managed.

## 9. Inference Option Decision Table

| Requirement | Starting choice | Rationale |
|---|---|---|
| Fast API response, steady traffic | SageMaker Real-Time | Always-ready endpoint with selectable instances |
| Low, spiky traffic, compact model | SageMaker Serverless | Zero instance management and lower idle cost |
| Bursty traffic, wait-tolerant, large payloads | SageMaker Asynchronous | Queueing, S3 outputs, scale-to-zero |
| Scheduled scoring of millions of records | SageMaker Batch Transform | Offline job without keeping an endpoint up |
| Request-by-request Bedrock FM calls | Bedrock On-Demand | No model self-hosting |
| High, steady FM throughput | Bedrock Provisioned Throughput | Dedicated capacity via model units |
| Large prompt sets, no immediate response needed | Bedrock Batch Inference | Asynchronous processing via S3 |
| Serving many small models on shared infrastructure | SageMaker Multi-Model or Inference Components | Boosts utilization and avoids per-model endpoints |
| Model updates needing limited blast radius | SageMaker deployment guardrails | Canary/linear shifting, baking, and auto-rollback |

These are initial choices. Benchmark with real data, traffic profiles, and SLOs before finalizing architecture.

## 10. Understanding Throughput, Latency, and Concurrency

Three frequently confused metrics:

- **Latency:** time taken to process a single request.
- **Throughput:** number of requests completed per unit of time.
- **Concurrency:** number of requests being processed simultaneously.

An endpoint may show low latency for a single request yet spike in latency under high concurrency. High throughput does not guarantee low p99 latency if queues build up.

Little's Law for a stable system:

\[
L = \lambda \times W
\]

Where:

- \(L\) is the average number of requests inside the system.
- \(\lambda\) is the average arrival rate (requests/second).
- \(W\) is the average time a request spends in the system (seconds).

For example, a system receives 50 requests/second with an average processing time of 0.2 seconds:

\[
L = 50 \times 0.2 = 10
\]

On average, roughly 10 requests are in flight. If latency climbs to 1 second at the same arrival rate, average concurrency rises to 50. This is why you must monitor both queues and latency rather than invocation counts alone.

## 11. Estimating Capacity Before Scaling

A rough sizing estimate:

\[
RequiredInstances \approx
\left\lceil \frac{PeakRPS}{SafeRPSPerInstance} \right\rceil
\]

Suppose benchmarking shows one instance safely handles 25 requests/second while keeping p95 latency within SLO. Peak traffic is 180 requests/second:

\[
RequiredInstances = \left\lceil \frac{180}{25} \right\rceil = 8
\]

If reserve capacity is needed for instance failures or scaling lag, set minimum capacity higher than the theoretical floor. Final figures must be validated through load testing, since request size, batch size, model architecture, and concurrency all impact throughput.

Never treat peak throughput from a brief synthetic test as production capacity. Test sustained load, bursts, cold starts, model warmup, and scale-out lag.

## 12. Horizontal Scaling vs. Vertical Scaling

**Horizontal scaling** increases instance counts to distribute requests. **Vertical scaling** switches to larger instances or stronger accelerators.

| Criterion | Horizontal scaling | Vertical scaling |
|---|---|---|
| Approach | Increase/decrease instance count | Change instance type or accelerator |
| Fault tolerance | Multiple instances increase redundancy | Relies on fewer large instances |
| Constraints | Model must fit on each instance; sufficient quotas needed | Instance sizes and quotas |
| Change speed | Autoscaling adjusts dynamically | Changing config usually requires an endpoint update |
| Best fit | Traffic grows by request rate | Model exceeds memory or needs a faster GPU |

A large model may not fit into a small instance's RAM/GPU memory. Adding more instances will not help if a single replica cannot load onto one instance. In that case, use vertical scaling, model sharding/parallelism, or an inference architecture supporting distributed models.

## 13. Autoscaling for Real-Time Endpoints

SageMaker AI supports target tracking and step scaling for production variants. Target tracking is typically easiest to operate: pick a metric and target, and Application Auto Scaling creates alarms and adjusts instance counts toward the target.

Common metrics:

- `InvocationsPerInstance`: average invocations per instance over a period.
- CPU/GPU utilization or custom metrics when tracking resource saturation.
- Application metrics such as queue depth or concurrent requests if custom-published.

Rule of thumb: if an instance benchmarks safely at around 70 invocations/minute, set an initial target lower to preserve headroom. After load testing, tune the target based on latency and error rates.

### 13.1. Registering an Endpoint Variant as a Scalable Target

~~~bash
aws application-autoscaling register-scalable-target \
  --service-namespace sagemaker \
  --resource-id endpoint/fraud-detection-prod/variant/AllTraffic \
  --scalable-dimension sagemaker:variant:DesiredInstanceCount \
  --min-capacity 2 \
  --max-capacity 12
~~~

### 13.2. Creating a Target Tracking Policy

Create `scaling-policy.json`:

~~~json
{
  "TargetValue": 70.0,
  "PredefinedMetricSpecification": {
    "PredefinedMetricType": "SageMakerVariantInvocationsPerInstance"
  },
  "ScaleInCooldown": 300,
  "ScaleOutCooldown": 60
}
~~~

Apply the policy:

~~~bash
aws application-autoscaling put-scaling-policy \
  --policy-name fraud-endpoint-target-tracking \
  --policy-type TargetTrackingScaling \
  --service-namespace sagemaker \
  --resource-id endpoint/fraud-detection-prod/variant/AllTraffic \
  --scalable-dimension sagemaker:variant:DesiredInstanceCount \
  --target-tracking-scaling-policy-configuration file://scaling-policy.json
~~~

Numbers in the example are starting points only. `InvocationsPerInstance` is measured per metric period; verify the target matches units in CloudWatch and your benchmark. `MinCapacity` should cover baseline traffic and scale-out duration.

Scale-out cooldown is typically shorter than scale-in cooldown. Slower scale-in prevents premature capacity drops right after a brief burst. Do not assume `min-capacity` of 0 works on real-time endpoints just because async endpoints support it; the hosting type and scalable dimension must support that behavior.

## 14. Autoscaling for Asynchronous Endpoints

Async endpoints have queues, so scaling policies should reflect backlog and request age. Watching invocation rate alone can miss bursty requests piling up and waiting too long.

Common metrics:

- `ApproximateBacklogSizePerInstance` for target tracking.
- `ApproximateAgeOfOldestRequest` to monitor queue wait SLOs.
- `HasBacklogWithoutCapacity` to detect queued work when instance count is 0.
- CPU/GPU utilization to check whether instances are saturated.

Target tracking policy example:

~~~json
{
  "TargetValue": 5.0,
  "CustomizedMetricSpecification": {
    "MetricName": "ApproximateBacklogSizePerInstance",
    "Namespace": "AWS/SageMaker",
    "Dimensions": [
      {
        "Name": "EndpointName",
        "Value": "document-ocr-async"
      }
    ],
    "Statistic": "Average"
  },
  "ScaleOutCooldown": 60,
  "ScaleInCooldown": 300
}
~~~

A target of 5 means operations wants to maintain roughly 5 queued requests per instance on the chosen metric. This is not requests per second. Tune according to average processing time and queue wait SLOs.

When using scale-to-zero, add a scale-out-from-zero policy driven by `HasBacklogWithoutCapacity`. Without this policy, the endpoint may stall waiting for a valid backlog-per-instance metric before booting capacity.

## 15. Autoscaling Provisioned Concurrency for Serverless

On-demand Serverless Inference scales compute automatically with traffic. When Provisioned Concurrency is configured, Application Auto Scaling can scale pre-warmed concurrency up and down.

The scalable dimension is `sagemaker:variant:DesiredProvisionedConcurrency`.

Resource IDs by endpoint and variant follow the pattern `endpoint/endpoint-name/variant/variant-name`.

Example registering the scalable target:

~~~bash
aws application-autoscaling register-scalable-target \
  --service-namespace sagemaker \
  --resource-id endpoint/sentiment-serverless/variant/AllTraffic \
  --scalable-dimension sagemaker:variant:DesiredProvisionedConcurrency \
  --min-capacity 2 \
  --max-capacity 20
~~~

Then attach target tracking or scheduled scaling. Provisioned concurrency must be at least 1 and cannot exceed `MaxConcurrency`. You can schedule capacity increases before peak hours and decreases after business hours to balance latency and cost.

## 16. Batch Scaling: Accelerating Jobs by Data

Batch Transform does not scale like an endpoint. Operators pick instance counts at job creation, then tune parallelism and input partitioning.

Levers:

- Increase `InstanceCount` when enough S3 objects or partitions exist to distribute.
- Pick stronger instance types when each record demands substantial CPU/GPU memory.
- Increase `MaxConcurrentTransforms` when the container handles concurrent requests well.
- Choose `BatchStrategy=MultiRecord` if the model accepts multiple records per invocation.
- Tune `MaxPayloadInMB` within API limits and container memory.
- Split inputs into multiple reasonably sized files so one instance does not shoulder the entire workload while others sit idle.

Raising instance counts may yield no speedup if the input is a single unsplittable object or the container hits another bottleneck. Always measure total runtime, utilization, file counts, and output throughput.

## 17. Choosing Instances and Optimizing Models

Pick instances based on actual bottlenecks:

| Workload type | Resources to inspect |
|---|---|
| Small tabular models, light preprocessing | CPU, memory, and networking |
| Computer vision or deep learning | GPU memory, GPU utilization, batch size |
| Models suited for specialized accelerators | AWS Inferentia/Trainium inference support per framework and serving stack |
| Embeddings and vector generation | CPU/GPU, memory, batch throughput |
| Large LLMs | GPU memory, tensor parallelism, token throughput, concurrency, and context length |

Before switching instance types, verify:

- Does the model artifact fit in memory?
- Does the model have a long load time?
- Is lower precision such as FP16/BF16/INT8 supported?
- Does larger batch size raise throughput while meeting latency targets?
- Is CPU preprocessing or serialization becoming a bottleneck?
- Should the container be optimized or the model compiled?

Not every model runs faster on GPUs. For tiny models or very short requests, GPU data-transfer overhead can increase latency. Benchmark on the actual target instance and representative payloads.

## 18. Multi-Model Endpoints, Multi-Container Endpoints, and Inference Components

When hosting many models, you do not always need a separate endpoint per model.

| Deployment pattern | When suitable | Trade-offs |
|---|---|---|
| Single-model endpoint | One model with high traffic or strict isolation needs | Predictable resources, potential idle capacity |
| Multi-Model Endpoint (MME) | Many models sharing the same framework/container with low per-model traffic | Saves instances, introduces model loading/cache eviction behavior |
| Multi-Container Endpoint | Multiple models requiring different containers/frameworks | Flexible, more complex resource and config management |
| Serial inference pipeline | Chained preprocessing/model/postprocessing steps | Unified pipeline, adds sequential hop latency |
| Inference Components | Multiple models sharing endpoint infrastructure with independent resource/copy management | Fine-grained resource orchestration, requires capacity tracking |

Inference Components let you attach models to an endpoint and allocate CPU, GPU, memory, and copy counts per component. Components can scale independently, update models separately, and share endpoint infrastructure. Some components can scale copies down to 0 to free resources for others.

Do not pick MME merely because you have many model files. Consider supported frameworks, model size, invocation frequency, load times, memory caching, and reload latency.

## 19. Deployment Guardrails: Safe Model Updates

Model updates can spike latency, degrade prediction quality, or crash containers. SageMaker AI deployment guardrails support blue/green and rolling deployments for real-time and asynchronous endpoints per feature compatibility.

In a blue/green deployment:

- **Blue fleet** is the currently serving version.
- **Green fleet** is the new fleet running the updated model or config.
- SageMaker provisions the green fleet, shifts traffic per policy, and watches CloudWatch alarms during a baking period.
- If an alarm triggers, the service can automatically roll back to the blue fleet.

Three traffic shifting modes:

| Mode | How traffic shifts | Best fit |
|---|---|---|
| All at once | Shifts 100% in one step | Fast updates accepting larger blast radius |
| Canary | Shifts a small fraction first, observes, then shifts the rest | Balances risk and rollout speed |
| Linear | Shifts in equal incremental steps | Gradual verification with small blast radius |

For example, linear shifting might move 20% of traffic per step with a 5-minute baking period. Base exact numbers on traffic volume and error detection speed. A canary with too little traffic may lack enough samples to catch issues.

### 19.1. CloudWatch Alarms for Auto-Rollback

Create alarms on signals such as:

- Model latency p95/p99 exceeding SLO.
- Invocation 5xx or model container errors rising.
- Throttling increasing.
- Abnormal CPU/GPU or memory pressure.
- Business metrics like fraud false positive rates or classification drift if an evaluation pipeline emits them.

Alarms should compare the green fleet against baselines or defined thresholds. Never rely solely on CPU since a model can emit bad predictions while infrastructure looks healthy.

Multi-step blue/green rollouts with baking periods keep both fleets active concurrently, raising costs during the deployment window. Budget capacity and spend for overlap windows.

## 20. Differences Between Canary, Shadow, and A/B Testing

These three techniques evaluate new models with different goals:

- **Canary deployment:** a slice of live traffic is routed to the new model; outputs affect users.
- **Shadow deployment:** live requests are mirrored to the new model for measurement, while shadow responses are discarded rather than returned to users.
- **A/B testing:** users or requests are intentionally randomized into groups to compare model outcomes and business metrics.

SageMaker production variants can distribute traffic across variants. For shadow testing, ensure the shadow model causes zero side effects such as sending emails, charging payments, or mutating business state.

A/B tests need proper randomization and enough duration to avoid sample bias. Canary is a deployment risk-mitigation technique, not a substitute for statistical model quality evaluation.

## 21. Observing Endpoints with CloudWatch

Metrics detect overloaded endpoints, failing models, or scaling lag.

Key metrics:

| Metric | Meaning | Used for |
|---|---|---|
| `Invocations` | Requests hitting the endpoint | Measuring traffic |
| `InvocationsPerInstance` | Average invocations per instance | Target tracking |
| `ModelLatency` | Time spent inside the model container | Tracking model compute latency |
| `OverheadLatency` | SageMaker overhead outside model processing | Separating model slowness from service/network overhead |
| `Invocation4XXErrors` | Client-side request errors | Checking payloads, auth, endpoint usage |
| `Invocation5XXErrors` | Server/container errors | Investigating model servers and runtimes |
| `InvocationModelErrors` | Errors raised by the model container | Debugging inference code |
| `InvocationThrottles` | Throttled requests | Checking concurrency/capacity |
| `CPUUtilization` / `GPUUtilization` | Compute utilization | Detecting compute saturation |
| `MemoryUtilization` / `GPUMemoryUtilization` | Memory utilization | Detecting OOM risk or model loading pressure |

Metrics carry dimensions such as `EndpointName`, `VariantName`, or `InstanceId` depending on type. Select the exact dimensions when building dashboards and alarms. Endpoint-level averages can hide a single hot instance.

### 21.1. Monitoring p95 and p99

Average latency can look healthy even when a tail of requests is slow. For interactive applications, p95 and p99 matter far more than averages.

Example SLOs:

- p95 latency below 250 ms.
- p99 latency below 600 ms.
- Error rate below 0.1%.
- Zero throttling during normal operating hours.

These values are illustrative. Define SLOs around user experience and measure end-to-end latency on the application side, since `ModelLatency` excludes API Gateway, network hops, and client processing.

## 22. Monitoring Model Quality After Deployment

An endpoint can look healthy at the infrastructure level while prediction quality drops due to shifting input distributions. Monitor both operations and model quality.

Approaches:

- Data capture to sample requests/responses per policy.
- SageMaker Model Monitor to check data quality, model quality, bias, or drift in supported use cases.
- Logging business outcomes once ground truth arrives.
- Comparing prediction distributions across model versions.
- Tracking feature missing rates, out-of-range values, and schema mismatches.
- Using trace IDs to link predictions back to requests and business outcomes.

Never store full sensitive payloads solely for observability. Apply sampling, masking, and retention limits. When ground truth arrives late, build offline evaluation pipelines rather than judging quality solely from raw inference outputs.

## 23. Capacity Planning and Load Testing

Before production, load tests must simulate real workloads:

1. Use representative payloads and realistic request-size distributions.
2. Ramp virtual users or request rates in steps.
3. Measure throughput, p50/p95/p99 latency, errors, and throttling.
4. Watch CPU, GPU, memory, queues, and model loading.
5. Test sustained load over a meaningful duration.
6. Test traffic bursts and scale-out/scale-in transitions.
7. Test cold starts when using serverless or async scale-to-zero.
8. Repeat across alternative instance types or endpoint modes.

Amazon SageMaker Inference Recommender can automatically benchmark models across supported real-time or serverless configurations. Results help select instance types, instance counts, container parameters, memory, and concurrency. Treat it as a starting guide; supply representative sample data and validate against production traffic.

### 23.1. Do Not Benchmark Only One Request

One successful request only proves the model runs. Production requires knowing:

- How long does model loading take?
- How does latency shift at 10, 50, or 200 concurrent requests?
- While instances scale out, do requests queue or throttle?
- When traffic drops, does scale-in hurt latency on the next burst?
- If a model container restarts, does the endpoint recover cleanly?
- If one instance fails, can the remaining fleet absorb the load?

Save benchmark results alongside model version, container image digest, instance type, Region, payload distribution, and endpoint configuration for future comparisons.

## 24. Strategies to Reduce Inference Costs

Costs depend on hosting mode, instance type, compute hours, traffic, model size, data transfer, storage, and logging.

| Measure | Impact |
|---|---|
| Use Serverless for intermittent traffic | Cuts idle compute |
| Use Async with scale-to-zero | Avoids holding instances when queues are empty |
| Use Batch Transform for offline workloads | Avoids always-on endpoints |
| Right-size instances | Eliminates overprovisioning |
| Autoscale on benchmarked metrics | Tracks actual demand |
| Multi-model / inference components | Increases shared infrastructure utilization |
| Quantization / compilation / optimized containers | Lowers compute per inference |
| Request batching when supported by the model | Raises throughput per compute unit |
| Trim bloated payloads and redundant preprocessing | Cuts latency and overhead |
| Manage data capture / log retention | Controls storage and logging bills |

Never optimize costs by cutting capacity below SLO. If an endpoint throttles frequently, client retries can amplify traffic and push total costs higher.

## 25. Securing the Inference Pipeline

Inference endpoints frequently process business-critical or personal data. Security must cover model artifacts, requests, outputs, and administrative access.

### 25.1. Separating IAM Roles by Responsibility

Separate:

- **Training/deployment role:** reads model artifacts and creates models/endpoints.
- **Endpoint execution role:** reads model artifacts from S3, pulls images from ECR, and accesses required resources.
- **Application invoke role:** calls only `sagemaker:InvokeEndpoint` or `sagemaker:InvokeEndpointAsync` on specific endpoints.
- **Batch job role:** reads S3 inputs and writes S3 outputs.
- **Operations role:** views metrics, logs, and endpoint status; update/delete permissions are gated separately.

Never grant `sagemaker:*` to applications that only need inference. For Bedrock, scope `bedrock:InvokeModel` or `bedrock:InvokeModelWithResponseStream` by model/resource and grant batch job permissions separately when needed.

### 25.2. VPC, PrivateLink, and Encryption

Real-time endpoints can be configured with VPC access to control network interfaces and connect to private resources. AWS PrivateLink can provide private connectivity to SageMaker APIs/runtimes where supported.

Protect:

- Model artifacts in S3 using bucket policies and KMS.
- Requests/responses with TLS.
- Endpoint networking with appropriate VPCs, security groups, and endpoint policies.
- CloudWatch logs and data capture with encryption and retention limits.
- Secrets used inside containers via AWS Secrets Manager or Systems Manager Parameter Store.
- Model artifacts and container images with versioning, scanning, and approvals.

Do not log sensitive payloads or predictions in application logs without explicit justification and retention policies.

## 26. Request Management, Retries, and Idempotency

When an endpoint times out or errors, clients may retry. However, retries are not always harmless.

- For pure inference, retries usually do not mutate business state, though they increase load and cost.
- For model services with side effects, enforce idempotency keys or decouple inference from side effects.
- For async, use `InferenceId`/request IDs to correlate inputs, outputs, and notifications.
- For batch, record `TransformJobName` and input manifests for traceability, retries, or reruns.
- Use exponential backoff with jitter for throttling/transient errors.
- Never infinitely retry 4xx errors caused by bad payloads or permissions.
- Set client timeouts intentionally above model timeouts while staying within SLOs.

With queues, handle TTL expirations, failed outputs, and delayed notifications. Never treat receiving the initial HTTP acceptance response from an async call as proof that inference completed.

## 27. Error Handling and Throttling

| Symptom | Common cause | Resolution |
|---|---|---|
| `ModelNotReadyException` | Model not ready or container still booting | Check endpoint status, model load time, and health checks |
| `ModelError` | Inference container failed | Inspect model server, payload, and container logs |
| `ValidationError` | Malformed request or exceeded limits | Check `ContentType`, payload size, and schema |
| `ThrottlingException` | Exceeded concurrency/quota/capacity | Smooth bursts, retry with backoff, or raise capacity |
| p99 latency spikes | Queueing, cold starts, GPU saturation, or model loading | Correlate `ModelLatency`, `OverheadLatency`, and utilization |
| Async backlog grows | Arrival rate exceeds processing rate | Scale out, optimize model, or adjust TTL/SLO |
| Slow batch job | Few input files, idle instances, or suboptimal batch size | Partition data, benchmark instances, and tune concurrency |
| Endpoint update fails | Quotas, image/model incompatibility, or deployment config | Inspect endpoint events, service quotas, and model logs |
| 5xx rises after model update | Model/container regression | Use alarms and auto-rollback; compare blue/green metrics |
| Missing S3 output | Execution role lacks permissions or job unfinished | Check role, bucket policy, KMS, and job status |

When handling errors, record request ID, endpoint name, model version, variant, timestamp, and error code. Avoid logging raw payloads if data may be sensitive.

## 28. Case Study: Choosing Three Inference Modes for an E-Commerce Platform

An e-commerce platform has three use cases:

**A. Fraud detection at checkout**

- Needs scores within 150 ms at p95.
- Traffic is steady during business hours and surges during campaigns.
- Choose a SageMaker Real-Time endpoint.
- Set minimum instances for baseline, autoscale on `InvocationsPerInstance`.
- Use canary deployment for model updates.
- Alert on p95 latency, 5xx, and throttling.

**B. Invoice and document OCR**

- PDF/image files can be large, taking 20–90 seconds per inference.
- Users can wait for a notification.
- Choose SageMaker Asynchronous Inference.
- Store inputs/outputs in S3; send SNS notifications on completion.
- Autoscale on backlog and age of oldest request.
- Enable scale-to-zero when queues empty if SLOs allow.

**C. Customer propensity scoring**

- Nightly scoring of 12 million customers.
- Results are consumed the next day.
- Choose SageMaker Batch Transform.
- Partition inputs into multiple files; tune instance count and `MaxConcurrentTransforms` via benchmarks.
- Write outputs to S3 for Glue/Athena or downstream services.

If fraud detection transitions to a managed foundation model on Bedrock, evaluate On-Demand or Provisioned Throughput based on token throughput and quotas; if scoring millions of prompts offline, evaluate Bedrock batch inference instead of self-hosting endpoints.

The three use cases use three different inference modes while sharing IAM governance, model registry, CI/CD, CloudWatch dashboards, and model review workflows.

## 29. Lab: Comparing Real-Time, Async, and Batch

Run in a lab account or approved sandbox environment. Use a small model and synthetic data; do not deploy to production.

### Step 1: Prepare Model and Roles

- Choose an existing model artifact in S3.
- Create an execution role with permission to read the artifact.
- Prepare input and output S3 locations.
- Verify KMS key policies if buckets use customer managed keys.

### Step 2: Create a Real-Time Endpoint

1. Create a SageMaker Model.
2. Create an `EndpointConfig` with a suitable instance type.
3. Create the endpoint.
4. Wait until the endpoint reaches `InService`.
5. Call `InvokeEndpoint` with a small payload.
6. Record p50/p95 latency and invocation errors.

### Step 3: Create an Asynchronous Endpoint

1. Create an endpoint configuration with `AsyncInferenceConfig`.
2. Configure the S3 output path and optional SNS topic.
3. Create the endpoint.
4. Send a request via `InvokeEndpointAsync` pointing to S3 input.
5. Record `InferenceId` and output location.
6. Verify outputs once processing completes.
7. Observe backlog metrics.

### Step 4: Run Batch Transform

1. Create a `TransformJob` pointing to an S3 input prefix.
2. Choose instance type and instance count.
3. Pick appropriate `SplitType` and `BatchStrategy`.
4. Run the job and monitor status.
5. Inspect output files in S3.
6. Compare completion time and estimated cost against endpoints.

### Step 5: Compare

Record:

- Request latency or job completion time.
- Throughput.
- Instance utilization.
- Error and retry counts.
- Estimated compute cost.
- Operational effort and SLO compliance.

### Step 6: Clean Up

Delete endpoints, endpoint configurations, models, and lab resources no longer needed. Stop or delete test jobs per account procedures. Keep outputs only if needed for exercises and free of real data.

## 30. Pre-Production Inference Checklist

### Architecture Selection

- [ ] Workload classified as online, asynchronous, or batch.
- [ ] SLOs defined for latency, throughput, availability, and queue wait.
- [ ] Payload sizes and processing timeouts verified.
- [ ] SageMaker vs. Bedrock compared based on where the model is hosted.
- [ ] Feature compatibility and Region/quotas verified.

### Capacity and Scaling

- [ ] Instance types selected via benchmarks.
- [ ] Headroom reserved for peak traffic and instance failures.
- [ ] Autoscaling metrics reflect actual bottlenecks.
- [ ] Min/max capacity and cooldowns tested.
- [ ] Async scale-to-zero includes a scale-up-from-zero policy.
- [ ] Serverless concurrency and Provisioned Concurrency match traffic profiles.
- [ ] Batch inputs partitioned to utilize parallelism.
- [ ] Load tests include sustained load, bursts, and cold starts.

### Deployment and Monitoring

- [ ] Model versions and container images are traceable.
- [ ] Canary/blue-green or rollback plans exist.
- [ ] CloudWatch alarms monitor latency, errors, throttling, and utilization.
- [ ] Logs, traces, and request IDs exist for investigation.
- [ ] Model quality/drift monitored per use case.
- [ ] Retries, timeouts, idempotency, and queue TTLs are defined.

### Security and Cost

- [ ] Application invoke roles hold least-privilege permissions.
- [ ] Execution roles read/write only required S3 resources.
- [ ] Requests, artifacts, outputs, and logs are encrypted.
- [ ] VPC/PrivateLink used when network isolation is required.
- [ ] Sensitive payloads masked with appropriate retention.
- [ ] Cost allocation tags and budget alerts configured.
- [ ] Scheduled reviews exist for capacity, model quality, and costs.

## 31. Self-Check Exercises

### Question 1

When should you choose SageMaker Real-Time Inference?

**Answer:** When the application requires synchronous responses with low/predictable latency and traffic is continuous enough to justify keeping an endpoint active.

### Question 2

What traffic pattern suits Serverless Inference?

**Answer:** Intermittent or unpredictable traffic with small payloads and processing times within serverless limits; cold starts must be factored in.

### Question 3

Can Serverless Inference configure Provisioned Concurrency?

**Answer:** Yes. Provisioned Concurrency keeps concurrency warm to reduce cold starts and supports autoscaling; its value cannot exceed `MaxConcurrency`.

### Question 4

What are the reference maximum payload and processing time for SageMaker Asynchronous Inference?

**Answer:** Up to 1 GB payload and up to 60 minutes of processing per current service limits.

### Question 5

Why does Async Inference fit large document OCR?

**Answer:** Requests can be queued, take longer to process, pass inputs/outputs via S3, and notify the application when done.

### Question 6

Does Batch Transform require a persistently running endpoint?

**Answer:** No. SageMaker provisions compute for the Transform Job and releases it once the job finishes.

### Question 7

Why might Batch Transform fail to utilize multiple instances if given only one input file?

**Answer:** Distribution depends on S3 objects and split strategy. A single input object can leave only one instance processing while others sit idle.

### Question 8

What is the main difference between SageMaker Batch Transform and Bedrock batch inference?

**Answer:** Batch Transform runs SageMaker-hosted models; Bedrock batch inference sends bulk prompts to Bedrock-supported foundation models using S3 inputs/outputs.

### Question 9

Does Bedrock batch inference support provisioned models?

**Answer:** No, per current documentation.

### Question 10

Which metric does target tracking autoscaling for real-time endpoints commonly use?

**Answer:** `InvocationsPerInstance` is the standard predefined metric; targets should be set via benchmarking.

### Question 11

Which metrics are useful for autoscaling asynchronous endpoints?

**Answer:** `ApproximateBacklogSizePerInstance`; also monitor `ApproximateAgeOfOldestRequest` and `HasBacklogWithoutCapacity`.

### Question 12

Why does an async endpoint need a scale-up-from-zero policy?

**Answer:** When instance count is 0, backlog-per-instance may not trigger scaling; `HasBacklogWithoutCapacity` signals queued requests with zero active instances.

### Question 13

What is the difference between horizontal and vertical scaling?

**Answer:** Horizontal scaling adds instances; vertical scaling moves to larger instances or stronger accelerators.

### Question 14

When should you use inference components?

**Answer:** When multiple models must share endpoint infrastructure while retaining independent resource allocation, copy counts, and lifecycles.

### Question 15

How does a blue/green canary deployment reduce risk?

**Answer:** Shifts only a small slice of traffic to the green fleet first, monitors CloudWatch alarms during a baking period before shifting the rest, and supports auto-rollback.

### Question 16

Why are p95/p99 latencies more useful than average latency for interactive APIs?

**Answer:** Averages can hide a slow subset of requests; p95/p99 reflect the user experience at the tail of the distribution.

### Question 17

If throughput rises yet queue backlog also grows, what problem is the system experiencing?

**Answer:** Arrival rate still exceeds processing rate or capacity is scaling too slowly; inspect queue age, instance utilization, and scaling policies.

### Question 18

How does Inference Recommender help?

**Answer:** Automatically load-tests and compares instance/endpoint configurations to recommend suitable performance and cost profiles.

### Question 19

Why should you never retry infinitely when an endpoint throttles?

**Answer:** Retries add traffic and load, creating overload loops; use exponential backoff, jitter, and capacity/quota reviews.

### Question 20

A workload runs nightly over 10 million records with results needed the next morning. Which option usually fits?

**Answer:** Batch Transform or Bedrock batch inference depending on model type and where the model is hosted; no need to keep an endpoint online all day.

## 32. Official References

- [Inference options in Amazon SageMaker AI](https://docs.aws.amazon.com/sagemaker/latest/dg/deploy-model-options.html)
- [Deploy models for inference](https://docs.aws.amazon.com/sagemaker/latest/dg/deploy-model.html)
- [Real-Time Inference](https://docs.aws.amazon.com/sagemaker/latest/dg/realtime-endpoints.html)
- [Serverless Inference](https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints.html)
- [Create a serverless endpoint configuration](https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints-create-config.html)
- [Automatically scale Provisioned Concurrency for a serverless endpoint](https://docs.aws.amazon.com/sagemaker/latest/dg/serverless-endpoints-autoscale.html)
- [Asynchronous Inference](https://docs.aws.amazon.com/sagemaker/latest/dg/async-inference.html)
- [Autoscale an asynchronous endpoint](https://docs.aws.amazon.com/sagemaker/latest/dg/async-inference-autoscale.html)
- [Alarms and logs for asynchronous endpoints](https://docs.aws.amazon.com/sagemaker/latest/dg/async-inference-monitor.html)
- [Batch Transform](https://docs.aws.amazon.com/sagemaker/latest/dg/batch-transform.html)
- [Automatic scaling of SageMaker AI models](https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling.html)
- [Auto scaling policy overview](https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling-policy.html)
- [Inference Recommender](https://docs.aws.amazon.com/sagemaker/latest/dg/inference-recommender.html)
- [Inference cost optimization best practices](https://docs.aws.amazon.com/sagemaker/latest/dg/inference-cost-optimization.html)
- [Advanced endpoint options](https://docs.aws.amazon.com/sagemaker/latest/dg/deploy-model-advanced.html)
- [Inference components and real-time model hosting](https://docs.aws.amazon.com/sagemaker/latest/dg/realtime-endpoints-deploy-models.html)
- [Deployment guardrails](https://docs.aws.amazon.com/sagemaker/latest/dg/deployment-guardrails.html)
- [Blue/green deployments](https://docs.aws.amazon.com/sagemaker/latest/dg/deployment-guardrails-blue-green.html)
- [Process multiple prompts with Bedrock batch inference](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html)
- [Amazon Bedrock capacity and performance](https://docs.aws.amazon.com/bedrock/latest/userguide/capacity-limits-cost-optimization.html)
- [Amazon Bedrock scaling and throughput best practices](https://docs.aws.amazon.com/bedrock/latest/userguide/scaling-throughput-best-practices.html)

Payload limits, timeouts, quotas, feature compatibility, and pricing can change by Region, instance type, model, and service version. Prior to deployment, verify against current documentation, benchmark with representative workloads, and check account quotas.
