# Work Queues and Worker Orchestration Mechanisms

## Lesson Objectives

After this lesson, you will be able to:

- Describe the roles of producers, queues, brokers, dispatchers, and workers in a background processing architecture.
- Choose a queue model and delivery mechanism suited to durability, ordering, throughput, and latency requirements.
- Design a message lifecycle covering receiving, processing, acknowledging, retrying, and routing to a dead-letter queue.
- Build workers capable of safe duplicate handling, concurrency limiting, and controlled shutdown.
- Orchestrate workers on Kubernetes or container services, scale by backlog, and protect downstream dependencies.
- Monitor and verify system reliability, throughput, latency, and cost.

## 1. Why are work queues needed?

An online request usually needs a fast response. However, many downstream operations can take several seconds or minutes, such as generating invoices, sending emails, transcoding video, generating reports, syncing data, or processing images. If the API performs all the work before responding, response time depends on the speed of every involved service. When one service slows down, pending requests pile up and can exhaust threads, connections, or memory.

A work queue decouples request intake from work execution. The API validates the request, writes a message to the broker, and returns a job ID. Workers pull messages from the queue and process them independently. The API can return an accepted or queued status; the application provides an endpoint or status page for users to check results upon completion.

This architecture creates a buffer between the rate of work creation and the rate of processing. During traffic spikes, the queue holds pending work instead of forcing the API to hold connections open throughout execution. Queues do not make work disappear: if the sustained arrival rate exceeds the processing rate, the backlog will keep growing. Appropriate capacity, load limits, and alerts are required.

For example, an online store receives 500 invoice generation requests in one minute. The API can write 500 jobs to the queue in a short time. The worker pool processes them steadily, calls the invoicing service, and stores the results. If the invoicing service slows down, the queue absorbs some of the fluctuation while the API still responds quickly once the message is durably stored.

## 2. Components and processing flow

A background processing system typically consists of these components:

- **Producer:** creates work and sends messages. This can be an API, application, schedule, or another worker.
- **Queue/broker:** stores messages and manages delivery, acknowledgements, retries, or retention.
- **Consumer/worker:** receives messages, executes business logic, and writes results.
- **Dispatcher or scheduler:** selects workers, queues, partitions, or execution times according to orchestration policies. Some brokers handle most of the distribution, removing the need for a separate dispatcher.
- **Job state store:** persists business states such as queued, running, succeeded, or failed for API and operator lookups.
- **Dead-letter queue (DLQ):** holds messages that cannot be processed after the configured number of attempts or conditions.
- **Observability system:** collects queue depth, message age, processing time, errors, retries, and ready worker counts.

Basic flow:

1. The producer validates permissions, input data, and business rules.
2. The producer generates a unique job ID and sends a message to the queue.
3. The broker acknowledges receipt of the message according to its configured durability guarantees.
4. A worker receives the message and transitions the job to an in-progress state.
5. The worker executes the work, saves results, and updates the job state.
6. The worker acknowledges (acks) the message after processing succeeds.
7. If processing fails, the worker applies retries or routes the message to the DLQ according to policy.

Distinguish between a publish acknowledgement from the producer and a processing acknowledgement from the worker. When a producer receives a publish ack, it means the broker has accepted the message under the broker's contract; it does not mean the work is finished. Completion state must be recorded separately.

### 2.1. Designing work messages

Messages should carry enough information for the worker to understand what to do, while avoiding embedding large payloads or unnecessary secrets.

An illustrative structure:

    {
      "messageId": "msg-7f21",
      "jobId": "invoice-2026-00421",
      "jobType": "generate-invoice",
      "schemaVersion": 1,
      "createdAt": "2026-11-22T10:30:00Z",
      "correlationId": "order-00421",
      "attempt": 0,
      "payload": {
        "orderId": "order-00421",
        "customerId": "customer-018"
      }
    }

Commonly useful fields:

- **messageId:** unique identifier of a message for tracking and duplicate detection.
- **jobId:** business identifier, stable across retries.
- **jobType:** type of work so the worker can select a handler.
- **schemaVersion:** payload structure version for compatible rollouts.
- **createdAt:** creation timestamp for measuring message age.
- **correlationId/traceId:** links logs and traces across API, broker, and worker.
- **attempt:** attempt count, if the broker or application manages this field.
- **payload:** minimal data or a reference to data stored in durable storage.

Do not put passwords, access tokens, private keys, or sensitive data into queues without a clear need. If payloads are large, store objects in object storage or a database, then send a reference along with a checksum and time-limited access permissions. Workers must verify access permissions and the validity of referenced data.

## 3. Choosing queues, pub/sub, and delivery mechanisms

Messaging models have different goals. Choose a model based on how work is consumed, retention requirements, and processing order.

| Model | How it works | Suitable use cases |
|---|---|---|
| Work queue / competing consumers | Multiple workers pull work from one queue; each message is typically processed successfully by one worker | Sending emails, generating invoices, image processing |
| Pub/sub | One event is broadcast to multiple independent subscriptions; each subscriber group has its own consumption stream | When one event must update a data warehouse, analytics, and notifications |
| Partitioned queue / stream | Messages are partitioned by partition or key; order is preserved within a partition per platform guarantees | Processing events per account, order, or device |
| Delayed queue / scheduled delivery | Messages become ready only after a specific time or delay | Payment reminders, delayed retries, scheduled tasks |
| Priority queue | Work is selected based on priority level | Supporting urgent tasks or SLA tiers |

In a work queue, multiple workers typically compete for work. When a worker pulls a message, the broker marks the message as in-flight or grants a lease/visibility timeout. If the worker acks successfully, the message is removed from the queue. If the worker crashes or the lease expires before acking, the broker can return the message so another worker can process it.

In pub/sub, one event can be delivered to multiple subscriptions. Do not use a single shared queue if every processing group must receive the same event, because competing consumers split work among themselves rather than delivering copies to every group.

With partitioned queues, the key determines where a message is written. If per-order sequencing is needed, use `orderId` as the partition key so events for the same order follow one stream. Global ordering usually reduces parallelism and is not supported by all brokers. Specify the exact scope of ordering required: queue-wide, per partition, or per business entity.

### 3.1. Choosing a broker based on requirements

Common services:

| Service | Common usage pattern | Points to consider |
|---|---|---|
| RabbitMQ | Queues, routing keys, exchanges, acknowledgements, and consumers | Flexible routing; requires operating brokers, quorum/replication, and queue capacity |
| Amazon SQS | Managed queues, Standard or FIFO, visibility timeout, and DLQ | Minimal broker operations; check throughput limits, retention, FIFO constraints, and request pricing |
| Google Cloud Pub/Sub | Pub/sub, subscriptions, and acknowledgement deadlines | Suitable for event distribution; design ordering keys and per-subscription retries |
| Azure Service Bus | Queues/topics, subscriptions, lock duration, dead-lettering | Supports enterprise routing and messaging; configure locks, duplicate detection, and DLQs |

There is no single best broker for every workload. Evaluate at least: durability, retention, ordering, throughput, message size, retry capabilities, DLQs, security, observability integration, quotas, regional availability, and cost.

## 4. Message lifecycle: receive, process, and acknowledge

A message should only be deleted or marked complete after processing results have been durably persisted. If a worker acks first and then writes data, a failure between those two steps can lose work. If a worker writes data and crashes before acking, the broker can redeliver the message and the work may be executed a second time.

This is why queue systems commonly provide at-least-once delivery. Workers must assume the same message can appear multiple times.

### 4.1. At-most-once, at-least-once, and exactly-once

| Mechanism | Characteristics | Risks |
|---|---|---|
| At-most-once | Message is delivered at most once per system mechanism; may be lost if failure occurs after receipt | Potential loss of work |
| At-least-once | Broker redelivers when no valid ack is received | Potential duplicate processing |
| Exactly-once | Scope and guarantees depend on broker, transactions, and target system integration | Does not automatically guarantee external side effects happen only once |

In many business systems, at-least-once combined with idempotent processing is the practical choice. Some platforms support exactly-once within a narrow scope, such as processing within broker transactions or a supported pipeline. When writing to a database, calling payment APIs, or sending emails, duplicate control is still needed at the business layer.

### 4.2. Idempotency and duplicate prevention

An idempotent operation can be executed repeatedly without changing the final business outcome beyond the first execution. For example, generating an invoice with an idempotency key set to `jobId`. Before creating it, the worker checks a job processing table or uses a unique constraint to ensure `jobId` creates only one invoice.

A simple workflow:

1. Receive a message with `jobId`.
2. Start a database transaction.
3. Insert `jobId` into the `processed_jobs` table with a unique constraint.
4. If `jobId` already exists in a completed state, skip side effects and ack the message.
5. If it does not exist, perform business updates and save the completed state in the same transaction whenever possible.
6. Commit the transaction, then ack the message.

If side effects occur outside the database transaction, such as calling a payment gateway or sending an email, use an idempotency key supported by the target service or an appropriate saga/outbox/inbox flow. Do not assume a local transaction can roll back an HTTP request already executed by another service.

### 4.3. Transactional outbox

A common failure occurs when the API writes an order to the database successfully but fails to send the message, or sends the message successfully but the database transaction rolls back. Business data and the queue then become inconsistent.

The transactional outbox solves this by writing the order record and an outbox record in the same database transaction. A publisher reads the outbox and sends messages to the broker; once the broker acknowledges, the publisher marks the record as sent. The publisher may resend if interrupted mid-way, so consumers still need idempotency.

This pattern eliminates the gap between committing business data and publishing messages. It does not eliminate all distributed failures, but it makes message publishing retryable and observable.

## 5. Leases, visibility timeouts, and processing duration

Many brokers do not delete a message immediately when a worker receives it. Instead, the broker grants a processing window (visibility timeout or lock/lease duration). During that window, the message is temporarily hidden from other workers. The worker must ack before the lease expires.

If processing takes longer than the lease, the message can be redelivered while the first worker is still running. Two workers might execute the same job concurrently. There are three ways to handle this:

- Set the lease longer than the maximum measured processing time, accounting for variance.
- Periodically extend the lease/visibility timeout while the worker is making progress.
- Design for idempotency and use business locks to prevent two workers from writing the same result concurrently.

Setting the lease too long slows down message recovery when a worker dies. Setting it too short increases duplicate redeliveries. Measure p95/p99 processing times, set an initial timeout with headroom, and monitor lease expiration counts.

In RabbitMQ, consumer acknowledgements and prefetch settings affect how many unacked messages are delivered to a consumer. In SQS, visibility timeout and `ChangeMessageVisibility` control how long a message remains hidden. In Pub/Sub, the acknowledgement deadline can be extended during processing. API names differ, but the shared principle is limiting how long a worker holds processing ownership and enabling recovery when a worker becomes unresponsive.

## 6. Retries, backoff, and dead-letter queues

Not every error should be retried. Distinguish between:

- **Transient errors:** timeouts, network glitches, rate limits, or temporarily unavailable dependencies.
- **Data/logic errors:** malformed schema payloads, missing required fields, or business rule violations.
- **Infrastructure errors:** terminated workers, disconnected nodes, or temporarily unreachable brokers.

Transient errors can be retried. Data errors cannot be fixed by repeated retries; route them to a DLQ or quarantine queue for inspection. If all workers continuously retry a failing message, it can consume capacity and clog the queue.

### 6.1. Exponential backoff and jitter

A retry policy typically increases the wait duration after each failure:

    delay = min(maxDelay, baseDelay * 2^attempt)

Random jitter can be added so workers do not all retry simultaneously:

    actualDelay = random(0, delay)

Illustrative example with `baseDelay` of 2 seconds and `maxDelay` of 60 seconds:

| Next attempt | Max delay before jitter |
|---|---:|
| 1 | 2 seconds |
| 2 | 4 seconds |
| 3 | 8 seconds |
| 4 | 16 seconds |
| 5 | 32 seconds |
| 6 and beyond | 60 seconds |

Set `max attempts` or a retry time limit. Otherwise, a poison message or invalid data can persist indefinitely and consume resources. For rate-limit errors, respect `Retry-After` if provided by the dependency.

### 6.2. Dead-letter queues

A DLQ receives messages that have exceeded the attempt limit or violated processing conditions. The DLQ should retain enough information for investigation: `messageId`, `jobId`, error type, attempt count, last failure timestamp, `correlationId`, and the payload or payload reference.

DLQ operational procedure:

1. Alert when new messages enter the DLQ or when its growth rate exceeds a threshold.
2. Group errors by error code, `jobType`, and schema version.
3. Identify the root cause: bad data, code bug, dependency issue, or misconfiguration.
4. Fix the root cause and verify on a sample message in a test environment.
5. Redrive with rate and volume limits; monitor duplicates and downstream load.
6. Maintain an audit trail to track which messages were replayed and their final outcomes.

Do not continuously auto-redrive the entire DLQ back to the main queue. If the underlying bug is unfixed, the system just creates a retry loop and amplifies load. Separate quarantine queues per error type or manual approval workflows for sensitive jobs may be required.

## 7. Worker orchestration and load limiting

A worker is a process that executes work. One worker can process one message at a time or multiple messages in parallel. Worker count and concurrency determine throughput, though increasing concurrency does not always increase effective capacity.

### 7.1. Competing consumers

Multiple workers reading from one queue form the competing consumers pattern. The broker distributes messages to available workers according to its mechanism. As worker count grows, throughput can scale nearly linearly at first if jobs are independent and downstream systems have spare capacity.

However, if all workers query a database with a connection limit, adding workers can overload the database. Total connections, per-worker pools, concurrency, and downstream API call rates must be bounded.

### 7.2. Concurrency and prefetch

Concurrency is the number of jobs a worker processes simultaneously. Prefetch is the number of unacked messages a broker can deliver in advance to a consumer. These two parameters are related but distinct.

- Too low concurrency leaves CPUs or workers idle when work can run in parallel.
- Too high concurrency increases memory usage, connections, contention, and the number of jobs disrupted when a worker dies.
- Too large prefetch can let one worker hold many messages while other workers sit idle, reducing fairness.
- Too small prefetch can reduce throughput because workers constantly wait for the broker to dispatch messages.

Start with low concurrency, measure throughput, latency, memory, connection pools, and errors, then scale up gradually. Set prefetch close to the number of jobs a worker can actually process concurrently, especially when processing times vary widely across messages.

### 7.3. Priority and fairness

If there are multiple job types, separate queues or priorities can be used. For example, payment confirmation tasks have a shorter SLA than report generation tasks. A single queue containing heavy jobs can make urgent tasks wait too long.

Splitting queues by job type allows independent worker pools, retries, and autoscaling. However, too many queues increase operational complexity. You can group by SLA and resource characteristics rather than creating a queue for every message type.

In multi-tenant systems, enforce per-tenant quotas or weighted fair scheduling. If one customer submits a huge burst of jobs, they should not monopolize all workers and starve other customers.

### 7.4. Backpressure and producer limiting

Operationally, a queue is a finite buffer. If producers send faster than processing capacity over an extended period, the backlog grows, wait times rise, and storage costs increase. When approaching thresholds, the system must push back:

- Rate-limit incoming requests or return a retry-later status.
- Apply quotas per tenant, `jobType`, or API key.
- Reject non-essential work when queue depth exceeds thresholds.
- Pause producers or throttle event emission rates.
- Scale up workers if downstream systems still have capacity.
- Isolate high-priority queues so critical work is not blocked by normal backlogs.

Set limits on message size, retention, pending message count, and maximum age. For time-sensitive work, stale messages may lose value; define expiration policies and corresponding status handling.

## 8. Estimating throughput and worker count

Let:

- λ be the message arrival rate, in jobs per second.
- μ be the processing rate of one worker, in jobs per second.
- N be the number of active workers.
- ρ be the target utilization, less than 1 to keep headroom.

To handle steady-state load without building a long-term backlog, processing capacity must exceed arrival rate:

    N × μ × ρ >= λ

Reference worker count:

    N = ceil(λ / (μ × ρ))

For example, a queue receives an average of 60 jobs per second; one worker processes 5 jobs per second; target utilization is 75%:

    N = ceil(60 / (5 × 0.75))
    N = ceil(16)
    N = 16 workers

This is a steady-state estimate. If an existing backlog needs to be drained within a given window, additional throughput must handle both new arrivals and backlogged messages.

For example, if 12,000 messages are waiting and the backlog must clear within 10 minutes, an extra processing rate of 20 messages per second is needed on top of new arrivals. If new arrivals are 60 messages per second, the worker pool needs capacity for at least 80 messages per second before accounting for headroom.

Do not track queue depth alone. Two queues with the same 10,000 messages can have vastly different wait times if average processing times differ. Monitor oldest message age, queue wait time before pickup, processing duration, and completion rate to evaluate SLAs.

## 9. Deploying workers on Kubernetes

On Kubernetes, workers typically run as a Deployment when a continuous pool is needed, or as a Job/CronJob when each run is a finite task.

- **Deployment:** suited for workers continuously polling a queue and processing messages.
- **Job:** suited for a one-off run with a clear endpoint, such as importing a dataset.
- **CronJob:** creates Jobs on a schedule, such as nightly report aggregation.
- **HPA:** adjusts Pod count based on CPU, memory, or custom metrics.
- **KEDA:** integrates metrics from queues and event sources to scale workers, including scaling to 0 if configured.

Example of a continuous worker Deployment:

    apiVersion: apps/v1
    kind: Deployment
    metadata:
      name: invoice-worker
    spec:
      replicas: 3
      selector:
        matchLabels:
          app: invoice-worker
      template:
        metadata:
          labels:
            app: invoice-worker
        spec:
          terminationGracePeriodSeconds: 60
          containers:
            - name: worker
              image: registry.example.com/invoice-worker:v1
              env:
                - name: QUEUE_NAME
                  value: invoices
                - name: BROKER_URL
                  valueFrom:
                    secretKeyRef:
                      name: broker-credentials
                      key: url
              resources:
                requests:
                  cpu: 500m
                  memory: 512Mi
                limits:
                  cpu: "1"
                  memory: 1Gi
              readinessProbe:
                exec:
                  command: ["/app/worker", "ready"]
                periodSeconds: 10
              livenessProbe:
                exec:
                  command: ["/app/worker", "health"]
                periodSeconds: 20
                failureThreshold: 3

A worker's readiness probe should reflect its ability to accept work, such as broker connectivity and drain state. Do not use liveness probes to check every external dependency if transient failures would trigger continuous container restarts. Workers must handle `SIGTERM`: stop fetching new messages, finish or release in-flight messages, and exit within the grace period.

Protect connection credentials with Secrets or the platform's secret management system. In production, configure least-privilege service accounts, network policies, TLS, scanned images, and appropriate resource limits.

### 9.1. Scaling workers by queue with KEDA

KEDA can read broker metrics and create or adjust an HPA for a Deployment. The example below uses the RabbitMQ scaler for the `invoices` queue, targeting 25 messages per worker:

    apiVersion: keda.sh/v1alpha1
    kind: ScaledObject
    metadata:
      name: invoice-worker-scaler
    spec:
      scaleTargetRef:
        name: invoice-worker
      minReplicaCount: 1
      maxReplicaCount: 30
      pollingInterval: 15
      cooldownPeriod: 120
      triggers:
        - type: rabbitmq
          metadata:
            protocol: amqp
            queueName: invoices
            mode: QueueLength
            value: "25"
            hostFromEnv: BROKER_URL

In this example, KEDA checks the queue every 15 seconds, targets 25 messages per replica, and bounds workers between 1 and 30. Ensure the `BROKER_URL` variable is declared in the Pod template and sourced from a Secret; the exact scaler configuration must match the KEDA and broker versions in use.

Setting minimum replicas to 1 keeps a worker ready, reducing cold starts at the cost of idle resources when the queue is empty. If the workload tolerates startup time, `minReplicaCount` can be set to 0. When scaling from 0, verify the scaler can still read the queue and no dependency blocks worker startup.

Deployment and observation steps:

    kubectl apply -f invoice-worker.yaml
    kubectl apply -f invoice-worker-scaledobject.yaml
    kubectl get deployment invoice-worker
    kubectl get scaledobject invoice-worker-scaler
    kubectl describe scaledobject invoice-worker-scaler
    kubectl get hpa
    kubectl get pods -l app=invoice-worker -w

Inject test messages into the queue and observe Pod counts, queue depth, completion rate, oldest message age, and errors. When the queue empties, check whether scale-in happens after the cooldown period. If Pods stay Pending, check resource requests, node capacity, taints/tolerations, and node pool limits.

### 9.2. Orchestrating finite Jobs

For one-off tasks, a Kubernetes Job is more suitable than a worker constantly polling a queue. For example, a Job can process a defined dataset, terminate upon completion, and be retried by Kubernetes up to `backoffLimit` when Pods fail.

    apiVersion: batch/v1
    kind: Job
    metadata:
      name: reconcile-orders
    spec:
      backoffLimit: 3
      activeDeadlineSeconds: 1800
      ttlSecondsAfterFinished: 3600
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: reconcile
              image: registry.example.com/order-reconcile:v1
              args: ["--date", "2026-11-21"]
              resources:
                requests:
                  cpu: 1
                  memory: 1Gi

The Job controller manages the Job's Pods; Jobs do not replace a broker when you need to ingest and buffer a large volume of independent work items. If every message spawns a Job, consider Pod creation and API server overhead. For high message volumes, a worker pool is usually more efficient.

## 10. Scheduling and job orchestration

Some jobs need to run on a schedule rather than immediately upon creation. An external scheduler or Kubernetes CronJob can create Jobs periodically.

Important scheduling policies:

- **Concurrency policy:** allow, skip, or replace a new run if the previous run has not finished.
- **Deadline:** skip a run if it passes its allowed start window.
- **Retry:** limit the number of retries when a Job fails.
- **Idempotency:** ensure rerunning the same period does not create duplicate data.
- **Catch-up:** decide whether to backfill missed periods after system downtime.
- **Time zone:** specify the time zone clearly and handle daylight saving transitions where applicable.

Example CronJob for daily aggregation:

    apiVersion: batch/v1
    kind: CronJob
    metadata:
      name: daily-report
    spec:
      schedule: "0 2 * * *"
      timeZone: "Asia/Ho_Chi_Minh"
      concurrencyPolicy: Forbid
      startingDeadlineSeconds: 900
      jobTemplate:
        spec:
          backoffLimit: 2
          template:
            spec:
              restartPolicy: Never
              containers:
                - name: report
                  image: registry.example.com/report-worker:v1
                  args: ["--period", "previous-day"]

With CronJob, the **Forbid** policy skips the new run if the previous Job is still active. This is appropriate when you do not want two aggregation runs writing to the same dataset concurrently. If backfill is required, design an explicit catch-up process; do not assume CronJob will create every missed run in all scenarios.

## 11. Observability, security, and operations

A queue can be up while the service still violates its SLA if messages sit waiting too long. Monitoring must cover the broker, workers, and business outcomes.

| Group | Metric | Operational question |
|---|---|---|
| Queue | Depth, oldest message age, ready and in-flight message counts | Is the backlog growing continuously? Are jobs missing deadlines? |
| Throughput | Messages arrived/sec, succeeded/sec, acked/sec | Are workers keeping up with arrival rates? |
| Worker | Ready replicas, CPU, memory, restarts, concurrency | Are there enough workers? Are they resource-constrained? |
| Latency | Queue wait time, processing time, end-to-end duration | At which step is the SLA being impacted? |
| Reliability | Retries, redeliveries, timeouts, DLQ, errors by `jobType` | Are there repeatedly failing or poison messages? |
| Dependency | Connection pools, API errors, rate limits, database latency | Are workers overloading dependencies? |
| Cost | Worker-hours, broker requests, storage/retention, egress | Are costs rising due to backlogs or retries? |

Secure queues with authentication, per-queue or per-topic producer/consumer authorization, and encryption in transit and at rest when supported by the platform. Restrict permissions to purge, delete, redrive, and alter retention. Keep audit logs for DLQ operations and avoid logging sensitive payloads.

Set alerts based on SLAs rather than only on a fixed queue depth threshold. For example, alert when oldest message age exceeds 5 minutes, backlog grows continuously for 10 minutes, or the DLQ rate crosses a threshold. Actual thresholds should come from business processing deadlines.

## 12. Worker system verification procedure

Execute in a test or staging environment:

1. **Publish check:** send a valid message and verify the producer receives a successful publish result.
2. **Processing check:** verify a worker receives the message, updates status, and acks after saving results.
3. **Duplicate handling check:** resend the same `jobId` or simulate a worker crash after commit but before ack; verify no duplicate side effects occur.
4. **Retry check:** force a dependency to return controlled timeouts; verify backoff, attempt counts, and message state.
5. **DLQ check:** send an invalid payload; verify the message is quarantined after the retry threshold with sufficient diagnostic metadata.
6. **Lease check:** let a job run longer than the initial lease; verify extension or safe duplicate handling.
7. **Shutdown check:** send `SIGTERM` to an active worker; verify no messages are lost and the Pod exits within the grace period.
8. **Load check:** increase publish rate, measure throughput, queue age, p95/p99 processing latency, and downstream load.
9. **Backpressure check:** push the queue near its limit and verify producers are throttled or receive appropriate responses.
10. **Recovery check:** restart the broker/worker in a controlled test scenario; verify message durability and job state consistency.

Compare results against concrete targets: maximum wait time, throughput, error rate, duplicate rate, recovery time, and budget.

## 13. Common scenarios and troubleshooting

| Symptom | Possible causes | Investigation steps |
|---|---|---|
| Queue grows continuously | Arrival rate exceeds processing capacity or workers are failing | Compare λ, throughput, replicas, and dependency latency |
| Messages processed multiple times | Worker crashed before ack, lease expired, or redelivery | Check acks, visibility timeout, idempotency, and `jobId` logs |
| Messages stay in-flight too long | Worker hung, long lease, or broken lease renewal | Check heartbeats, worker health, and processing duration |
| DLQ grows rapidly | Bad payloads, code bugs, or prolonged dependency outage | Categorize errors, halt automated redrives, and fix root cause |
| Low worker CPU but large queue | Workers waiting on I/O, low concurrency, or downstream limits | Measure wait times, connection pools, and concurrent tasks |
| Scaling workers overloads database | Each worker opens too many connections or concurrent queries | Limit pools, concurrency, and database call rates |
| Low-priority jobs starve | High-priority queue consumes all workers | Separate pools, set quotas, or use weighted fair scheduling |
| Scheduled jobs overlap | Previous run not finished or catch-up schedule | Check `concurrencyPolicy`, run period locks, and idempotency |
| Producer succeeds but no output | Publish only confirms broker receipt; worker has not processed | Check queue, consumers, job status, and DLQ |

## 14. Production readiness checklist

- [ ] Choose work queue, pub/sub, partitioned queue, or scheduled queue based on business requirements.
- [ ] Define message schema, `messageId`, `jobId`, version, and `correlationId`.
- [ ] Configure durability, retention, quotas, message size limits, and broker access controls.
- [ ] Select delivery semantics and design idempotent consumers.
- [ ] Only ack after results are durably persisted.
- [ ] Set visibility timeouts/leases and renewal mechanisms for long jobs.
- [ ] Configure retries, exponential backoff, jitter, max attempts, and DLQs.
- [ ] Bound concurrency, prefetch, connection pools, and downstream call rates.
- [ ] Implement backpressure, quotas, and priority/fairness policies across tenants or job types.
- [ ] Implement graceful shutdown and handle unacked messages when workers stop.
- [ ] Choose Deployment, Job, or CronJob matching the work lifecycle.
- [ ] Monitor queue age, depth, throughput, processing latency, retries, and DLQs.
- [ ] Test duplicates, worker crashes, lease expiry, backlog spikes, and broker recovery.
- [ ] Set SLA-based alerts and reconcile operational costs.

## Conclusion

Queues decouple intake from execution and help systems absorb load fluctuations. Reliability depends on how messages are stored, acknowledging only after persisting results, handling duplicates, retries, and isolating failing messages. Worker orchestration must balance concurrency, prefetch, downstream capacity, fairness, and backpressure. When deploying on Kubernetes, choose Deployments for continuous workers, Jobs/CronJobs for finite or scheduled tasks, and scale on metrics that reflect backlogs and SLAs. Verify both normal cases and worker crashes, slow brokers, duplicate messages, and backlog spikes before going to production.
