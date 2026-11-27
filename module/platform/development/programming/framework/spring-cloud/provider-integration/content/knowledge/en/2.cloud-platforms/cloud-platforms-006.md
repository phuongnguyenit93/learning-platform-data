# Quotas, Rate Limits, and Usage-Based Pricing Models

A Spring Boot application integrating with managed services may run smoothly during testing yet throw errors under load: the app opens too many database connections, storage APIs return throttling errors, queues accumulate message backlogs, or the cloud bill climbs sharply without adding servers. These symptoms stem from three mechanisms that must be kept distinct: **quotas**, **rate limits / throttling**, and **usage-based pricing**.

Within the **Cloud Platforms** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, this lesson builds the foundation for integrating Spring Boot with AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries. When calling storage, messaging, databases, or secret managers, development teams must know how services impose limits per account/project/region, when retries are safe, how to protect data and identities, how to measure actual demand, and how to prevent unexpected charges.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish **quotas, hard limits, rate limits, bursts, concurrency limits, throughput, capacity**, and **budgets**.
- Identify the scope where quotas apply: account, subscription, project, region, service, resource, or principal.
- Interpret responses such as **429, 503, ResourceExhausted, and Throttling**, separating transient errors from configuration/permission errors.
- Design traffic caps, retries with backoff/jitter, timeouts, idempotency, and backpressure for Spring Boot applications.
- Read pricing models for object storage, messaging, databases, secrets, and data transfer across AWS, Azure, and Google Cloud.
- Build cost estimates, set budgets/alerts, attach cost-allocation tags/labels, and run controlled load tests.

## 2. Concepts That Must Not Be Conflated

**Quota** is a threshold set by the provider for a usage dimension—such as VM count, database instance count, API calls per minute, or total resource capacity. Quotas may be defaults, fixed values, adjustable on request, or tier-dependent.

**Service limit / hard limit** is a technical or product boundary that does not necessarily have an increase process—such as maximum message size, resource name length, or component counts allowed by a tier. Just because one quota is adjustable does not mean every limit can be raised.

**Rate limit** restricts request velocity over a time window, such as requests per second or requests per minute. **Throttling** is the act of slowing down, rejecting, or capping requests when a limit is exceeded or when a service must protect its processing capacity. Some services enforce dynamic rate limits rather than publishing a single fixed number for all cases.

**Burst capacity** allows handling a short spike of requests above steady-state rate under specific conditions; afterward, requests may be throttled. **Concurrency limit** measures the number of simultaneously executing tasks, not requests per second directly.

**Throughput** is the actual volume of work processed per unit of time: messages/second, MiB/second, or transactions/second. Throughput can depend on payload size, operation type, network, Region, data partitioning, and tier configuration.

**Budget** is a spending target and a monitoring/alerting mechanism. In most cloud governance tools, **a budget alert is not a hard cap that automatically halts all charges**. Some products support automated caps or actions, but you must configure them explicitly and understand their operational impact before enabling them.

| Term | Example | Impact When Hit | Common Mitigation |
|---|---|---|---|
| Resource quota | Max DB instances in a Region | Cannot provision more resources | Check scope, free unused resources, request quota increase if supported |
| Rate quota | API calls per minute | 429 or provider-specific throttling code | Shed load, backoff, cache, batch |
| Concurrency limit | DB connections, concurrent requests | Pool wait, rejections, timeouts | Pool sizing, concurrency caps, conditional scaling |
| Payload/service limit | Maximum message size | Validation error, invalid request | Split payload or store externally and send a reference |
| Throughput capacity | Message or I/O processing capacity | Queue backlog, high latency | Adjust tier/capacity, batching, right-sized workers |
| Budget | Monthly spend alert | Notification or configured automation | Investigate usage and cost-control policies |
| Billing minimum/rounding | Request units, GB-months, hours/seconds | Charges differ from naive multiplication | Read pricing sheets and SKU rounding rules |

> **A quota is not a price, a budget is not a quota, and a quota is not an SLA guarantee.** An application can stay well below quotas and still become expensive or slow for other reasons.

## 3. A Cloud Request Can Be Limited at Multiple Layers

Suppose Spring Boot handles an HTTP request, queries a database, and publishes an event to a queue. The request passes through multiple boundaries:

~~~mermaid
flowchart LR
    U["Client traffic"] --> G["API gateway / ingress limit"]
    G --> APP["Spring Boot<br/>threads + connection pool"]
    APP --> SDK["SDK throttling / retry policy"]
    SDK --> SVC["Managed API<br/>rate + capacity"]
    SVC --> Q["Queue / database / storage"]
    Q --> B["Billing meters"]
    MET["Metrics + alerts"] -. "Observe" .-> APP
    MET -. "Observe" .-> SVC
    MET -. "Track costs" .-> B
~~~

These boundaries can apply simultaneously: the gateway caps incoming requests, the app's connection pool allows only so many waiting callers, the SDK bounds attempts, the managed service enforces API quotas, and the database limits connections or CPU/I/O.

### 3.1. Calculating Rate Differs from Calculating Concurrency

If a service receives an average of **50 requests/second** and each request holds a connection for **0.2 seconds**, the average number of concurrent in-flight requests is approximately:

\[
L = \lambda \times W = 50 \times 0.2 = 10
\]

This is a straightforward application of **Little's Law** in steady state. If latency rises to **2 seconds** while the arrival rate stays unchanged, average concurrent requests can jump near **100**. With a connection pool of only 20 connections, requests begin queueing or timing out.

Consequently, adding threads or replicas does not automatically solve quota errors. It can increase **total connection count** and overload the managed database.

### 3.2. Burst and Token Bucket

A common rate-limiter model is the **token bucket**: tokens refill at a steady rate, each request consumes a token, and the bucket holds a maximum number of tokens to absorb short bursts. For example, an application limiter refills **10 tokens/second** and holds at most **30 tokens**. After an idle period it can accept a burst of up to 30 requests, yet cannot sustain 30 requests per second indefinitely.

This is only an **illustrative mathematical model**; cloud providers may enforce different algorithms or multi-layered limits. A rate limiter placed locally inside **each Spring Boot instance** does not control aggregate rate across the deployment. With 10 replicas each allowing 10 requests/second, theoretical cluster peak reaches 100 requests/second. When a system-wide cap is required, allocate per-replica quotas or use a coordinated distributed limiter.

## 4. Quota Scope and Management Responsibility

Quotas must be looked up by **service + operation + resource scope + location + tier type**. No single global quota governs every API in a cloud.

| Dimension | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| Primary governance boundary | AWS account, Region, service; sometimes per resource | Subscription, Region, resource/provider, and SKU; sometimes per tenant | Project/consumer project, Region/location, API/service; sometimes per resource |
| Quota inspection tools | Service Quotas, service docs, CloudWatch | Azure Quotas, per-service Usage + quotas page, Azure Monitor | Google Cloud Quotas & System Limits, Cloud Monitoring |
| Limit increase requests | Depends on service quota; request via Service Quotas or support | Depends on quota type, subscription, Region, and support tier | Depends on metric/quota; request adjustments where supported |
| Cost tracking | Cost Explorer, Cost and Usage Report, AWS Budgets | Cost Management, budgets, cost analysis | Cloud Billing reports, budgets, billing export |
| Cost allocation | Account, cost allocation tags, cost categories | Subscription, resource group, tags, billing scopes | Billing account, project, labels, billing export |

**Scope note:** a single enterprise may own many AWS accounts, Azure subscriptions, or Google Cloud projects. Quotas are not automatically pooled, shared, or transferred across them. Conversely, some organization-wide quotas or service limits can constrain multiple units underneath. Only the specific quota documentation answers which applies.

When raising quotas, pair the request with a **capacity, cost, and security plan**. Higher quotas permit more API calls or resource provisioning; they also enable larger bills or wider blast radii if an application misbehaves.

## 5. AWS: Per-Service Quotas and Billing

### 5.1. Amazon S3

S3 automatically scales for object request loads, yet you should never infer that **a bucket can never be throttled**. Throughput depends on factors such as operation type, prefixes, bucket type, Region, and scaling state. Some conditions can return **503 Slow Down**; clients should apply an appropriate retry policy with exponential backoff and monitor retry counts.

S3 charges can include:

- **Storage** per GB-month, storage class, location, retention duration, and rounding rules.
- **Requests** by operation type and billing group, such as PUT/COPY/POST/LIST or GET/SELECT depending on service and storage class.
- **Data retrieval** for specific storage classes or features.
- **Data transfer** across regions, out to the internet, and across billable network paths.
- **Versioning, replication, lifecycle transitions, inventory, analytics**, encryption key/KMS requests, and add-on features.

For example, enabling versioning helps recover overwrites, yet **every retained version continues incurring storage charges** per its storage class and lifecycle rules. Deleting the current object version does not ensure older versions stop billing.

### 5.2. Amazon SQS and SNS

SQS enforces limits by queue type, action, message size, throughput, and feature. **Standard** and **FIFO** differ in throughput and ordering/deduplication traits; some quotas are adjustable while some limits stem from service architecture.

SQS billing depends on **billable request units**, queue type, message volume, message size, and related data transfer. A single API call can translate into multiple billable units based on payload size or batching; do not estimate cost solely from successful messages if the application continuously retries or long-polls.

SNS bills by publish type, requests/deliveries, endpoint type, and other factors depending on tier/destination service. One event fanned out to many subscribers can generate **multiple delivery units** plus downstream receiver costs.

### 5.3. Amazon RDS, Secrets Manager, and Supporting Services

RDS imposes limits on instance counts, storage capacity, instance types, connections, and engine parameters depending on configuration. **Maximum database connections** is not one universal AWS constant; it depends on engine, parameter settings, memory, and workload.

RDS costs can include compute time, provisioned/consumed storage, I/O or throughput per engine/mode, backups beyond included allowances, replication, and data transfer. When choosing Multi-AZ or read replicas, account for the additional resources required by the architecture.

AWS Secrets Manager can bill per managed secret and API call; rotation can also invoke other services. Fetching a secret on every HTTP request adds latency and increases call counts/charges. Use caching aligned with rotation requirements, and never cache secrets by writing them to logs or world-readable files.

**AWS tools to check:** Service Quotas for current adjustable quotas; CloudWatch for throttles, requests, DB connections, and queue metrics; AWS Budgets/Cost Explorer for spend visibility; official pricing pages for exact numbers at your Region, tier, and date.

## 6. Azure: Quotas by Subscription, Region, and SKU

### 6.1. Azure Blob Storage

Blob Storage imposes limits at the storage-account level, throughput, request rate, and per operation/feature. Under load pressure or limit breaches, depending on the API and conditions, responses can include **429 Too Many Requests**, **503 Server Busy**, or other throttling details.

Costs can include stored capacity per tier, read/write/list transactions, retrieval fees on applicable tiers, redundancy modes like LRS/ZRS/GRS/GZRS, lifecycle rules, versioning/snapshots, data transfer, private networking, and encryption key options. **GRS/GZRS are data-replication choices**, so evaluate cost, data location, and recovery expectations together rather than looking only at per-GB storage rates.

### 6.2. Azure Service Bus

Namespaces have **tiers** such as Basic, Standard, or Premium with distinct capabilities and billing models. Concepts like operations, message sizes, connections, throughput, and **Messaging Units** capacity depend on tier and features.

Adding Spring Boot workers does not automatically increase namespace capacity. If producers emit faster than consumers process, backlogs grow. Tune prefetch/concurrency, lock/ack settings, retries, DLQs, and tier capacity; estimate costs using the SKU's current pricing model.

### 6.3. Azure SQL Database and Key Vault

Azure SQL Database consumes compute and storage according to purchasing model, service tier, provisioned/serverless mode, backups, and HA/DR. An oversized JDBC pool can cause contention or hit connection limits even when the subscription has plenty of resource creation quota left.

Azure Key Vault enforces transaction limits by operation type, vault/key type, and time window. Operations do not necessarily share the same price or quota—for example, cryptographic key decryption may differ from reading a secret. Some throttling responses include **Retry-After**; never retry 403 errors unboundedly.

**Azure tools to check:** Azure Quotas or service usage blades, Azure Monitor, Cost Management + Billing, and budgets. Never assume quotas and pricing for a storage account in one Region apply to all Regions or SKUs.

## 7. Google Cloud: Quotas, System Limits, and Per-Project Billing

### 7.1. Cloud Storage

Cloud Storage distinguishes **adjustable quotas**, **system limits**, and scaling/performance limits depending on bucket type, location, and operation. During sudden traffic spikes, account for ramp-up behavior, request distribution, retried operations, and service support limits.

Costs can include **storage GB-months**, Class A/Class B operations per pricing tables, data retrieval for applicable storage classes, network egress, and related management/replication charges. Regional, dual-region, and multi-region buckets differ in data location, replication configuration, and pricing; never infer location or unit price from a project ID.

### 7.2. Pub/Sub

Pub/Sub defines quotas for **publish throughput, pull/streaming pull, acknowledge**, topic/subscription resource counts, and other technical limits. Many quotas are scoped to **project and Region**, so check the exact metric in the console; a quota for one request type does not equal whole-system throughput.

Pub/Sub billing can be based on publish/delivery data volume or matching usage meters, retention, snapshots, subscriptions, and other product options. If a message fans out to multiple subscriptions, delivery traffic and costs scale with subscriber count. Retries and redeliveries can also increase resource consumption; verify billable units against current pricing docs.

### 7.3. Cloud SQL, Secret Manager, and API Quotas

Cloud SQL has resource/instance quotas and instance/engine limits; actual processing capacity depends on CPU, RAM, storage, I/O, connection pools, and HA/read replicas. Costs can include compute, storage, backups, networking, and replicas per configuration.

Secret Manager distinguishes secret/version counts, operations, and API limits; different data-access modes can carry different pricing. Polling secrets continuously does not substitute for proper caching, rotation, and payload protection.

Google Cloud frequently tracks quotas against the **consumer project** or granular API scopes. If a client uses a default project different from the project owning the resource, check which project is charged for quotas and billing, alongside IAM, API enablement, and organization policies.

**GCP tools to check:** Google Cloud Quotas & System Limits, Cloud Monitoring, Cloud Billing reports/budgets, and Cloud Billing export for granular analysis from real usage data.

## 8. Recognizing Throttling and Classifying Errors

An HTTP status alone is **not enough to conclude** which constraint was violated. SDKs may use gRPC statuses, custom error codes, exception wrappers, or internal retries before surfacing the final error.

| Signal | Possible Meaning | How to Verify |
|---|---|---|
| HTTP **429** or gRPC **RESOURCE_EXHAUSTED** | Rate/quota exceeded, throttling, or product limit | Provider error code, quota metrics, headers, quota scope/name |
| HTTP **503** / **Slow Down** / **Server Busy** | Service overloaded or temporarily shedding load | Request metrics, error-code docs, latency, and Retry-After if present |
| HTTP **403** / PermissionDenied | Missing IAM/RBAC, policy, token audience, or network restriction | Runtime identity, resource scope, policies; do not raise quotas blindly |
| HTTP **400** | Invalid payload, request, or parameter | Validation, payload size, service limits, error details |
| HTTP **409** / conflict | Version, state, or concurrent operation conflict | Preconditions, ETag/generation, idempotency |
| Timeout / connection reset | Slow network or downstream; outcome may be unknown | Trace/request ID, deadline, server logs, and idempotency |

Basic diagnostic steps:

1. Record **service, action, resource ID, Region, principal, request ID, and timestamp**, omitting tokens/secrets.
2. Read the **detailed error code** and matching quota metric rather than stopping at HTTP status.
3. Identify the **quota scope**: per project, account, region, resource, identity, or request method.
4. Check retry activity from both **SDK and application**; one logical request can generate multiple downstream attempts.
5. Also inspect permissions, networking, capacity tier, and business logic if quotas are nowhere near saturation.

**Never retry 401/403 or validation errors indefinitely.** For transient errors, retries are only safe when handling the possibility that an earlier attempt already caused side effects.

## 9. Rate Limiting, Retries, and Backpressure in Spring Boot

### 9.1. Controlling Load Across Layers

~~~mermaid
flowchart LR
    API["Incoming requests"] --> RL["Rate limit / admission control"]
    RL --> BH["Bulkhead / concurrency cap"]
    BH --> SDK["Cloud SDK: timeout + bounded retry"]
    SDK --> SV["AWS / Azure / Google service"]
    SV --> MT["Metrics: 429, latency, backlog"]
    MT -. "Adjust capacity" .-> RL
    MT -. "Adjust retry/limit" .-> BH
~~~

An ordered approach:

- **Limit incoming requests** per tenant/client or service-wide so one caller cannot exhaust shared quotas.
- **Cap concurrency** per downstream using semaphores/bulkheads and connection pools.
- Use **bounded queues** for asynchronous work; avoid unbounded queues.
- Use **batch APIs** where beneficial, checking payload limits, per-batch quotas, partial success handling, and billing rules.
- **Retry with exponential backoff + jitter**, honoring `Retry-After` if supported, capping attempts and overall deadlines.
- Enforce **idempotency keys** when retrying writes/creates, paired with application-level deduplication.
- Monitor p95/p99, throttling rates, and saturation to tune parameters rather than blindly bumping retry counts.

### 9.2. Why Nested Retries Are Dangerous

If the HTTP layer retries 3 times, the service layer retries 3 times, and the SDK retries 3 times, one business request can generate **up to 27 downstream attempts** under failure. Multiplying attempts drives load higher right when the downstream is overloaded, inflates billable requests, and risks duplicate side effects.

Use the built-in retry policies of the AWS SDK, Azure SDK, or Google Cloud client library where appropriate. Before layering Spring Retry/Resilience4j on top, agree on one responsible layer and measure **total attempts**. Outer retries must also respect overall deadlines and idempotency.

### 9.3. Spring Boot + AWS SDK v2 Example: Limiting Concurrency When Sending to SQS

This illustrates a **local concurrency cap** to protect resources—not a distributed rate limiter or AWS quota setting:

~~~java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;

@Configuration
class CloudClientConfig {
    @Bean
    SqsClient sqsClient(@Value("${app.aws.region}") String region) {
        return SqsClient.builder().region(Region.of(region)).build();
    }
}

@Service
class OrderPublisher {
    private final SqsClient sqs;
    private final String queueUrl;
    private final Semaphore inFlight = new Semaphore(16);

    OrderPublisher(
            SqsClient sqs,
            @Value("${app.messaging.queue-url}") String queueUrl) {
        this.sqs = sqs;
        this.queueUrl = queueUrl;
    }

    String send(String eventJson) throws InterruptedException {
        if (!inFlight.tryAcquire(250, TimeUnit.MILLISECONDS)) {
            throw new IllegalStateException("Publisher is overloaded");
        }
        try {
            return sqs.sendMessage(SendMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .messageBody(eventJson)
                    .build()).messageId();
        } finally {
            inFlight.release();
        }
    }
}
~~~

~~~yaml
app:
  aws:
    region: ap-southeast-1
  messaging:
    queue-url: https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders-test
~~~

The **app.*** properties here are defined by this example, not universal Spring Cloud AWS properties across all versions. The code assumes the AWS SDK v2 SQS dependency, basic Spring Boot auto-configuration, and runtime credentials via the provider chain/role. If the app already uses a Spring Cloud AWS auto-configured client, avoid declaring duplicate beans and pick a Spring Boot-compatible BOM.

Important caveats:

- **16 permits** only cap concurrent in-flight calls **within one instance**; they do not enforce a 16 requests/second cap or a cluster-wide limit.
- The SDK may retry internally per its default policy; one Java call can emit multiple API attempts.
- A succeeded send whose response is lost can cause retries to emit a second message. Payloads should carry an **eventId/idempotency key** for safe consumer deduplication; use an outbox when publishing must follow DB commits reliably.
- In production systems, map overload exceptions to proper responses, measure permit wait times, set end-to-end timeouts, and use a centralized rate limiter when deployment-wide caps are required.
- Never embed AWS access keys/secret keys in code or YAML.

Similarly, with **Spring Cloud Azure** or **Spring Cloud GCP**, place limits at the application adapter/service layer and combine them with service-supported SDK retry policies. Check per-operation settings and starter properties against your **exact library version**.

## 10. Usage-Based Pricing: Understanding Billing Units Properly

Clouds typically use **multi-meter billing models**. A single resource can accumulate multiple charge types simultaneously.

| Component | Common Billing Units | Practical Example |
|---|---|---|
| Compute/runtime | vCPU-seconds, GB-seconds, instance hours/seconds, capacity units | Always-on containers, provisioned databases |
| Object storage | GB-months by tier/location | Images, invoice files, replicas, versions |
| Storage operations | Request/transaction counts by type | PUT, GET, LIST, lifecycle transitions |
| Messaging | Operations, request units, ingress/egress bytes, capacity tiers | Publish, pull, send, delivery, retention |
| Managed database | Compute, storage, IOPS/I/O, backups, replicas | Primary + read replicas, long-term backups |
| Secrets/KMS | Secrets/versions, API operations, cryptographic requests | Reading secrets, key decrypt calls |
| Network | GB transferred to internet, cross-Region/AZ, gateways/endpoints | App calling a DB in another Region |
| Observability | Ingested logs, retained GB, metric series, traces | Debug-logging full requests with long retention |
| Backup/replication | GB copied/stored, requests, traffic | Cross-region backups, secondary databases |

**Unit prices** vary by provider, Region, storage class, SKU/tier, timing, contracts, and free tiers. Some products bill minimum increments, provisioned time even with zero requests, or minimum storage durations. When budgeting, use **exact SKU pricing on the current date**; never treat illustrative examples below as price quotes.

### 10.1. Simple Estimation Formula

~~~text
Estimated total cost
  = Compute
  + Primary and replica storage
  + API requests / operations
  + Messaging ingress, delivery, retention
  + Data transfer / networking
  + Backups, KMS, secrets, logs
  + Additional service line items
  - Applicable credits / discounts
~~~

Hypothetical example for a **31-day** month, selecting only four items to practice the calculation method:

| Hypothetical Item | Usage | Hypothetical Unit Price | Subtotal |
|---|---:|---:|---:|
| Object storage | 120 GB-months | 0.025 USD/GB-month | 3.00 USD |
| API operations | 2,000,000 requests | 0.004 USD/1,000 requests | 8.00 USD |
| Billable network egress | 70 GB | 0.09 USD/GB | 6.30 USD |
| Always-on runtime | 744 hours | 0.05 USD/hour | 37.20 USD |
| **Hypothetical total** | | | **54.50 USD** |

These are **hypothetical unit prices purely for arithmetic illustration**; they do not assert AWS, Azure, or Google Cloud prices. The table omits databases, queues, KMS, backups, logs, taxes, free tiers, rounding rules, volume discounts, and other charges. Production estimates must account for every billing meter of the actual services used.

### 10.2. Traffic Growth Does Not Mean Linear Cost Growth

Systems combine **fixed provisioned-capacity costs** with **variable usage costs**. For a DB instance running all month, halving SQL queries rarely halves the compute bill. Conversely, object storage bills can climb as stored data accumulates even if request traffic drops.

Once traffic crosses a threshold, a system may require additional DB replicas, higher messaging tiers, or more network capacity—causing costs to jump in **step functions** rather than smooth linear curves.

## 11. Six Ways Costs Grow Silently

1. **Retry storms:** SDK and multiple app layers retry together, multiplying billable requests and quota pressure.
2. **Multiple data copies:** versioning, soft delete, backups, snapshots, and cross-region replication retain far more data than expected.
3. **Cross-region or internet egress:** workloads placed far from data, export jobs, and backups drive heavy transfer charges.
4. **Excessive logging:** logging full request/response bodies, stack traces, or 100% tracing at high volume inflates ingestion/storage while risking data exposure.
5. **Forgotten provisioned resources:** DBs, private endpoints, NAT gateways, premium tiers, test clusters, IPs, or disks keep billing while idle.
6. **Fan-out/retention:** emitting each event to many subscriptions/queues, long retention windows, or retries/redeliveries inflating backlogs.

Cost optimization must respect **correctness and security**. For instance, slashing backup retention below RPO/RTO needs or deleting required audit logs saves money on paper while creating far greater risk.

## 12. Budgets, Quotas, and Guardrails in Operations

### 12.1. Three Control Layers

~~~mermaid
flowchart TD
    PLAN["Load and cost forecast"] --> Q["Quota / service limit<br/>per service, Region, project"]
    PLAN --> B["Budget + cost alerts"]
    PLAN --> L["Rate / concurrency limit<br/>in application"]
    Q --> OBS["Metrics + billing review"]
    B --> OBS
    L --> OBS
    OBS --> ACT["Adjust capacity, code, policies, and budgets"]
~~~

- **Quotas** cap technical quantities; they help restrain provisioning or request volume, yet do not replace cost governance.
- **Budgets** detect spending variance; by default they do not halt running provisioned capacity or delayed billing charges.
- **Application guardrails** like rate limits, bounded queues, timeouts, and concurrency caps prevent the app from generating runaway load per business rules.

### 12.2. Ownership and Budgets

A mature deployment should define:

| Control | Suggested Owner | Evidence |
|---|---|---|
| Quota headroom for launch | Platform/SRE | Quota metrics and capacity plans |
| Per-tenant rate limiting | Backend team | Load tests, accepted/rejected metrics |
| Controlled retries | Backend team | Total attempts/request, 429 rate, p95/p99 |
| Environment budgets | FinOps/Platform | Alert thresholds, billing dashboards |
| Cost-labeled resources | IaC/Platform | Tag/label coverage and cost allocation |
| Test environment cleanup | QA/Platform | TTLs, IaC teardowns, leftover resource lists |
| Anomaly response process | On-call/Operations | Runbooks, alert routing, incident history |

Apply **environment**, **team**, **service**, and **cost-center** labels where supported by each service. However, tags/labels do not automatically attribute costs to the right team if cost allocation is not enabled or if charges live in shared services.

### 12.3. What to Do When a Budget Alert Fires?

When alerted: identify which resource/service drove the bill up, compare against baseline traffic, and inspect retry spikes, egress, log ingestion, newly provisioned resources, backups/replication, or tier upgrades. Never automatically delete a production database just because a budget threshold fired.

If building spend-capping automation, test it in an isolated environment, separate **stoppable** workloads from **non-stoppable** ones, and define approvers plus impacts on data, availability, and ongoing billing.

## 13. Capacity Planning Problems for Spring Boot

### 13.1. Database Connection Pools Under Horizontal Scaling

Suppose Spring Boot runs **20 replicas**, each configured with **maximum pool size = 20**. Maximum theoretical app connections reach **400 connections** (20 × 20), before counting admin sessions, maintenance tasks, jobs, and other services.

If the database permits or handles well fewer than 400 connections, scaling out more replicas worsens failures. Strategies:

- Measure active connections and connection hold times rather than sizing pools mechanically from CPU.
- Sum pool sizes across **all replicas and workers**, reserving headroom.
- Use a supported proxy/pooler if suitable for the engine and workload, without treating it as infinite connections.
- Shorten long transactions, optimize SQL, and cache where consistent with business rules.
- Load-test against real database limits and verify autoscaling behavior.

### 13.2. Queue Backlogs When Producers Outpace Consumers

If producers average **1,000 messages/minute** while consumers process **800 messages/minute**, the backlog grows by roughly **200 messages/minute** under steady conditions. After 30 minutes, new backlog reaches **6,000 messages** (excluding retries, DLQs, and variance).

To resolve this, increase sustainable consumer throughput, reduce message volume, batch appropriately, or apply producer backpressure. **Simply raising retention** keeps messages around longer without helping consumers catch up.

### 13.3. Separating Three Thresholds

Before ramping traffic, set three distinct thresholds:

1. **Business thresholds:** orders/minute, user-facing latency, success rate.
2. **Technical thresholds:** DB connections, API request quotas, messaging throughput, pool saturation.
3. **Financial thresholds:** projected daily/monthly spend, egress, storage growth, and budget alerts.

A system hitting technical limits before financial limits still needs remediation. A system well within quotas whose egress multiplies several-fold still demands a cost investigation.

## 14. Designing Controlled Integration and Performance Tests

Before running load tests on AWS/Azure/GCP, use a dedicated test account/subscription/project and isolated datasets; assign resource ownership and cleanup procedures. Ramp load gradually per an approved plan, never bursting into production or tripping quotas uncontrollably.

| Scenario | What to Observe | Success Criteria |
|---|---|---|
| Ramping load to target threshold | Throughput, p95/p99, 429/503, CPU/pools | No unbounded queues or cascading timeouts |
| Per-instance rate limiter | Accepted/rejected per pod and cluster-wide | Aggregate load obeys the designed policy |
| Retries after 429 | Attempts, backoff, Retry-After, deadlines | No retry storms |
| Publisher loses ACK after send | Duplicate events, outbox, consumer dedup | Zero duplicate business side effects |
| DB pool near limit | Acquire latency, timeouts, active/idle | Controlled backpressure and recovery |
| Sustained queue backlog | Oldest message age, DLQ, retries | Alerts fire; scaling or producer throttling works |
| Billing under higher load | API request units, egress, logs | Actuals align closely with billing meters and estimates |
| Resource in wrong Region/tier | Location, SKU, endpoint, cost | Caught before pushing real data |
| Missing IAM role | PermissionDenied/403 | Classified as permission error; no infinite retries |
| Post-test cleanup | Bucket objects, DB/queues, disks, alerts | No unexpected billable resources left behind |

**Mock tests** can verify retry logic, semaphores, and error parsing, yet do not validate real quotas, pricing, or network behavior. Cloud integration/load tests must enforce safety caps on request counts, duration, projected spend, and emergency stop controls.

### 14.1. Metrics to Capture

- **Client/SDK:** requests, attempts, retries, 429/503s, timeouts, end-to-end deadline breaches, p50/p95/p99 request latency.
- **Application:** active threads, connection-pool saturation, concurrent calls, rejected requests, queue length, circuit breaker state.
- **Messaging:** ingress/egress, send/receive rates, backlog, oldest message age, delivery counts, DLQs, message sizes.
- **Database:** active/max connections, waiting requests, query latency, I/O, CPU, lock waits.
- **Cost:** usage by service, Region, environment, and billing meter; daily spend, forecasts, anomaly alerts, log/egress/backup growth.
- **Security:** policy-driven throttling vs. IAM 403s, audits on quota increases, role changes, tier changes, or replication toggles.

Strip tokens, access keys, secret values, personal payloads, and sensitive data from metrics and logs. Billing data can lag behind request metrics, so cost alerting should pair **near-real-time technical signals** with billing reports.

## 15. Common Diagnostic Scenarios

### Scenario A: AWS S3 Returns 503 During an Upload Spike

A job launches massive parallel PUTs against the same storage path. Check request distribution, operations, prefixes/bucket type, throughput, SDK retries, and CloudWatch metrics. Smooth spikes with concurrency caps, backoff/jitter, appropriate batching/distribution, and gradual load ramp-up. Also verify whether retries are inflating request charges or duplicating work.

### Scenario B: Azure Service Bus Is Slow Despite Adding Workers

Consumers scale from 5 to 30 replicas, yet the namespace is on a limited tier/capacity and the downstream database hits max connections. Adding workers increases redeliveries, lock expirations, or DB timeouts. Inspect namespace metrics, lock durations, prefetch, aggregate DB pool sizing, DLQs, and billing units. Tune **producer rate, worker concurrency, tier capacity, and DB throughput** together.

### Scenario C: GCP Pub/Sub Returns RESOURCE_EXHAUSTED

Publishers increase message sizes and throughput while the SDK retries multiple attempts. Check the exact quota metric per project/region and API, IAM, API enablement, backlog, batch settings, publish flow control, and error details. Throttle back, configure appropriate batching/flow control, or request a quota increase once the service supports it and workload demand is justified.

### Scenario D: Database Costs Rise While Traffic Stays Flat

A managed database was scaled up to a higher instance tier for performance testing and never scaled back down; read replicas were added or backup retention was extended. Bills climb even with constant RPS. Audit resource inventory, current SKUs, instance-hours, backups, replicas, cross-region transfer, and cost-allocation labels; add post-test review gates.

### Scenario E: Spring Boot Fails with 403 Yet the Team Requests a Quota Increase

A 403 can stem from missing IAM/RBAC, the wrong service account/managed identity, resource scope, or network policies. Raising quotas will not fix access permissions. Verify the actual principal and required permission actions first, inspecting error codes and traces. Request quota adjustments only when evidence shows a true technical quota limit was reached.

## 16. Common Misconceptions

| Misconception | What to Understand Instead |
|---|---|
| "High quotas mean costs stay low" | Quotas only cap technical usage; using more still bills more |
| "Setting a budget means the cloud stops automatically on overspend" | Budgets are usually alerts; stop/block automation must be designed separately |
| "Every 429 means monthly quota is exhausted" | It can be a time-window, principal, operation, or resource rate limit |
| "Increasing retry count clears limits faster" | Aggressive retries worsen throttling and increase billing |
| "Concurrency 16 means only 16 requests/second" | Concurrency is simultaneous calls; RPS also depends on latency |
| "Per-pod limiters give a global limit" | Total load multiplies by replica count without coordination |
| "Zero traffic means zero charges" | Provisioned DBs, instances, disks, endpoints, backups, or tiers can still bill |
| "One message equals one billing unit" | Payload size, batching, fan-out, delivery, and pricing models can change unit counts |
| "Any quota can be raised by paying more" | Hard limits and non-adjustable quotas exist |
| "Quotas and pricing match across all regions" | Regions, tiers, resource types, and contracts can differ |
| "Mock tests prove the app handles cloud quotas" | Isolated cloud tests and real metrics are required |
| "Increasing the connection pool always speeds up the DB" | Excess connections and contention can overload the DB |

## 17. Pre-Production Checklist

- **Quota inventory:** list services, operations, scopes, Regions, current usage, limits, and increase eligibility; reserve launch headroom.
- **Traffic model:** estimate requests/second, bursts, message sizes, concurrency, database connections, and replica counts.
- **SDK policy:** know the cloud SDK's default retries, set overall deadlines, backoff/jitter, timeouts, max attempts, and handle `Retry-After` properly.
- **Idempotency:** every retryable write/send must prevent duplicate business side effects; consumers handle redeliveries and DLQs.
- **Backpressure:** bound ingress, concurrency, pools, queues, and autoscaling to match downstream capacity.
- **Pricing model:** list billing meters by Region/SKU across requests, storage, compute, networking, KMS, backups, logs, and replication.
- **Budgets/alerts:** set alerts by environment, team, and service; confirm recipients, responders, and safe actions.
- **Security:** scope IAM roles, managed identities, and service accounts tightly; never log secrets; never escalate permissions on 403s.
- **Testing:** run controlled load tests covering 429/503s, timeouts, retries, duplicates, DB pools, and cleanup without impacting production.
- **Periodic reviews:** audit cost anomalies, tier drift, idle resources, quota headroom, backup retention, and label hygiene.

## 18. Summary

**Quotas** define resource/API usage caps, **rate limits** regulate request velocity and concurrency, and **pricing models** convert usage into charges across multiple meters. These three mechanisms interact yet do not replace one another. An application can get throttled well before exhausting overall quotas, or rack up large bills without ever seeing a 429.

When integrating Spring Boot with AWS, Azure, and Google Cloud, follow the sequence: **identify quota scopes → measure real load → bound concurrency/rate → retry safely → protect idempotency → monitor billing meters → set budgets and test**. This keeps storage, messaging, databases, and secret managers stable, makes costs predictable, and prevents transient load spikes from turning into wide outages.
