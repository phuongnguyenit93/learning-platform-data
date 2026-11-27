# Scaling Containers by Request, Concurrency, or Queue

## Lesson Objectives

After this lesson, you will be able to:

- Explain why container counts should change with load rather than stay fixed year-round.
- Select the right scaling signal: CPU, memory, concurrent requests, or queue depth.
- Estimate required replica counts and set safe scaling bounds.
- Configure autoscaling for HTTP workloads and queue-processing workers.
- Verify scale-out, scale-in, recovery behavior, and cost impact.

## 1. Why Do Containers Need Autoscaling?

A container service typically experiences load that shifts by hour, day, or event. An e-commerce API can receive heavy traffic during promotions; an email-sending service can receive thousands of jobs right after a campaign launches; an image-processing system may only be busy during specific windows.

If you always run enough containers for peak hours, most resources sit idle during low load. If you run only enough for average load, the system can respond slowly or reject requests during sudden traffic spikes.

Autoscaling adjusts container replica counts based on observed demand. A controller collects metrics, compares them against targets, and changes replica counts within configured bounds. As load grows, the system performs **scale out**; when load drops steadily, the system performs **scale in**.

For example, an API might run a minimum of 2 replicas to maintain availability and scale up to a maximum of 30 replicas when request volume rises. An order-processing worker might scale from 1 to 20 replicas when the queue accumulates unprocessed messages.

Horizontal scaling changes the number of replicas. This is the common approach for containers because applications can distribute load across multiple instances. Vertical scaling adjusts an instance's CPU or memory; this helps in certain cases, though it typically requires factoring in restart times, node resource ceilings, and application scalability limits.

## 2. Selecting the Right Scaling Signal

The scaling signal must reflect what actually causes the service to saturate. Picking an easy-to-measure metric unrelated to the real bottleneck can cause the system to add containers while latency stays unchanged.

| Signal | Best Suited For | Advantages | Limitations to Watch |
|---|---|---|---|
| CPU utilization | Compute-heavy APIs or workers | Easy to collect, broadly supported | Does not fully reflect I/O wait, locks, or external dependencies |
| Memory | Services whose memory grows with sessions or active data | Helps prevent memory exhaustion and OOM kills | Memory may not drop immediately after load falls; memory-only scale-in can lag |
| Concurrent requests | APIs, HTTP, or RPC services | Closely tracks work currently holding resources | Light and heavy requests can have vastly different resource costs |
| Queue depth | Asynchronous processing workers | Directly measures pending work | Must account for processing rate, SLA wait bounds, and message sizes |
| Oldest message age | Queues with strict latency SLAs | Detects aging backlogs even before count explodes | Depends on queue system metrics and update lag |
| Arrival and processing rates | Pipelines with sharp traffic swings | Helps forecast required capacity | Requires stable metrics and accurate measurement models |

### 2.1. Scaling by CPU or Memory

CPU fits when rising workload volume increases compute time per container. For instance, report-generation APIs or video-encoding workers typically consume substantial CPU.

Memory fits when session counts, cached data, or active tasks raise memory consumption with load. However, distinguish memory genuinely needed for current load from memory retained by the runtime for reuse. A container may keep allocated memory even after request volume drops.

In Kubernetes, the Horizontal Pod Autoscaler (HPA) can read resource metrics from Metrics Server. For percentage-based CPU metrics, containers must declare a CPU request so HPA has a denominator for utilization. If requests are omitted, CPU utilization metrics may not calculate properly for that container.

### 2.2. Scaling by Concurrent Requests

Concurrency is the number of requests or tasks an instance is actively processing at the same time. This signal is useful when an instance has practical limits on connections, worker threads, or per-request memory.

Suppose an API targets 40 concurrent requests per container. With roughly 240 concurrent requests distributed fairly evenly across containers, an initial estimate is:

    Required replicas = ceil(240 / 40) = 6

This is a capacity estimate, not a guarantee that the system always runs exactly 6 containers. The controller also weighs current replica counts, metrics over measurement windows, startup time, and min/max bounds. Monitor latency and error rates to confirm the concurrency target is sound.

Managed container services like Google Cloud Run let you configure maximum concurrency per instance alongside minimum and maximum instance counts. Setting concurrency too high can overload individual instances, raising latency or exhausting database connections. Setting it too low can spin up more instances than necessary and increase startup overhead.

### 2.3. Scaling by Queue Depth

Workers usually do not receive requests directly from users. Producers enqueue jobs; workers pull messages, process them, and acknowledge completion. Queue depth indicates pending work volume, making it suitable for adjusting worker counts.

Suppose policy targets at most 30 pending messages per worker. When the queue holds 900 messages, the estimated worker count is:

    Required workers = ceil(900 / 30) = 30

If the maximum configuration allows only 20 workers, the system caps at 20 and the backlog drains more slowly. This shows why scaling limits must be chosen alongside processing SLAs and downstream dependency capacity.

Queue depth alone is not always enough. If message processing times vary widely, 100 simple messages may finish faster than 10 compute-heavy messages. Also track oldest message age, arrival rate, completion rate, and error rate.

You can estimate worker capacity from throughput. Let:

- λ be the job arrival rate, in jobs per minute.
- μ be one worker's processing rate, in jobs per minute.
- ρ be the target utilization, less than 1 to preserve headroom.

The minimum workers to keep up with steady load can be estimated as:

    N = ceil(λ / (μ × ρ))

For example, a queue receives 120 jobs per minute; each worker processes an average of 10 jobs per minute; target utilization is 70%:

    N = ceil(120 / (10 × 0.7)) = 18 workers

This formula assumes relatively stable processing speeds. When a backlog already exists, add extra capacity to handle new arrivals while draining the backlog within the required timeframe.

## 3. Control Mechanisms and Key Parameters

A scaling loop typically follows four steps:

1. Collect metrics from the container platform, load balancer, monitoring system, or message broker.
2. The controller compares the current value against the configured target.
3. The platform increases or decreases replica counts within allowed bounds.
4. The controller re-measures after an interval and continues adjusting.

The following parameters directly govern stability:

- **Minimum replicas/instances:** keeps baseline capacity warm. Setting 0 saves cost during zero load, though the first request may wait for startup.
- **Maximum replicas/instances:** caps cost and resource consumption. Set based on quotas, budget, node capacity, and downstream system limits.
- **Metric target:** e.g., 65% average CPU, at most 40 concurrent requests per instance, or 30 queued messages per worker.
- **Sampling and polling intervals:** metrics refresh periodically. Intervals that are too long slow reactions; intervals that are too short cause overreaction to brief spikes.
- **Stabilization window:** delays scale-in to avoid removing replicas immediately after a brief dip in load.
- **Cooldown:** waiting period after a scaling adjustment, particularly useful for event-driven scalers.
- **Scale velocity:** limits how many replicas can be added or removed over a time window.
- **Readiness and startup:** new containers should take load only after the app is ready. If startup takes long, account for the delay between the scaling signal and actual serving capacity.

Prefer policies that scale out rapidly when load rises and scale in gradually when load falls. Slow scale-out lets backlogs or latency spike. Overly aggressive scale-in can cut off active requests, interrupt worker jobs, or cause container thrashing.

## 4. Hands-On Example: Kubernetes HPA for an API

Suppose a checkout service runs via a Deployment named `checkout-api`. Each Pod declares a CPU request of 500 millicores and a memory request of 512 MiB. The HPA keeps at least 2 Pods, scales up to 30 Pods, and targets 65% average CPU relative to CPU requests.

The container resource declaration might look like:

    resources:
      requests:
        cpu: 500m
        memory: 512Mi
      limits:
        cpu: "1"
        memory: 1Gi

Example HPA using the `autoscaling/v2` API:

    apiVersion: autoscaling/v2
    kind: HorizontalPodAutoscaler
    metadata:
      name: checkout-api
    spec:
      scaleTargetRef:
        apiVersion: apps/v1
        kind: Deployment
        name: checkout-api
      minReplicas: 2
      maxReplicas: 30
      behavior:
        scaleUp:
          stabilizationWindowSeconds: 0
          policies:
            - type: Percent
              value: 100
              periodSeconds: 60
        scaleDown:
          stabilizationWindowSeconds: 300
          policies:
            - type: Percent
              value: 25
              periodSeconds: 60
      metrics:
        - type: Resource
          resource:
            name: cpu
            target:
              type: Utilization
              averageUtilization: 65

In this example, the HPA can rapidly add Pods when CPU exceeds the target. When load drops, it waits out a 300-second stabilization window and caps scale-down to at most 25% every 60 seconds. These values are starting points and should be calibrated with load tests and operational telemetry.

Before applying, verify these prerequisites:

- Metrics Server is running and the resource metrics API returns readings.
- The Deployment specifies CPU requests for the measured containers.
- The application has a readiness probe accurately reflecting request-serving readiness.
- The cluster has enough nodes and quota to schedule new Pods.
- Service and Ingress distribute traffic to ready Pods.

Inspect using these commands:

    kubectl apply -f checkout-hpa.yaml
    kubectl get hpa checkout-api
    kubectl describe hpa checkout-api
    kubectl get pods -l app=checkout-api -w
    kubectl top pods -l app=checkout-api

If the HPA displays metrics as `unknown`, check Metrics Server, CPU requests, and events in `describe` output. If Pod counts do not increase despite high CPU, check `maxReplicas`, quotas, scheduling status, and available cluster resources.

HPA also supports custom and external metrics when the cluster integrates an appropriate metrics adapter. You can use pending request counts or requests per Pod as signals. Metric delivery, units, and aggregation must stay consistent; HPA cannot understand an application metric unless a component exposes it through the Kubernetes Metrics API.

## 5. Hands-On Example: KEDA Scaling Workers on a RabbitMQ Queue

Suppose an e-commerce system writes invoice-sending jobs to an `orders` queue. The `order-worker` Deployment reads the queue and processes each message. As the queue grows, KEDA can scale Pod counts using queue length.

Example `ScaledObject`:

    apiVersion: keda.sh/v1alpha1
    kind: ScaledObject
    metadata:
      name: order-worker-scaler
    spec:
      scaleTargetRef:
        name: order-worker
      minReplicaCount: 0
      maxReplicaCount: 20
      pollingInterval: 15
      cooldownPeriod: 120
      advanced:
        horizontalPodAutoscalerConfig:
          behavior:
            scaleDown:
              stabilizationWindowSeconds: 300
      triggers:
        - type: rabbitmq
          metadata:
            protocol: amqp
            queueName: orders
            mode: QueueLength
            value: "30"
            hostFromEnv: RABBITMQ_HOST

The `RABBITMQ_HOST` environment variable in the Deployment should be sourced from a Kubernetes Secret:

    env:
      - name: RABBITMQ_HOST
        valueFrom:
          secretKeyRef:
            name: rabbitmq-connection
            key: host

The `rabbitmq-connection` Secret must be created and scoped with proper access permissions. Never embed connection strings containing credentials directly in manifests committed to source control. The environment variable name in the Deployment must match `hostFromEnv`.

With this configuration, KEDA polls the queue every 15 seconds, targets 30 messages per worker, and scales replicas between 0 and 20. HPA manages scaling down from multiple Pods to 1 Pod using a 300-second stabilization window; KEDA's 120-second cooldown delays the final step from 1 to 0 once the queue empties. If a worker must always stay warm, set `minReplicaCount` to 1 while retaining the HPA stabilization window. Tune actual values to message processing duration and queue SLAs.

Deployment and verification sequence:

    kubectl apply -f order-worker.yaml
    kubectl apply -f order-worker-scaledobject.yaml
    kubectl get scaledobject
    kubectl describe scaledobject order-worker-scaler
    kubectl get hpa
    kubectl get pods -l app=order-worker -w

Next, publish a batch of test messages into the `orders` queue in a test environment. Watch pending message count, worker count, completion rate, and oldest message age. As the queue drains, confirm HPA steps workers down per the stabilization window; if scale-to-zero is enabled, observe the 1-to-0 step after cooldown.

If KEDA fails to create the scaler or read metrics, inspect `ScaledObject` status, events, KEDA operator logs, Secret permissions, and connectivity to RabbitMQ. If workers hit `maxReplicaCount` while backlog keeps climbing, revisit the max cap, per-worker throughput, and downstream capacity.

Workers must acknowledge messages only after successful processing. If a container is terminated mid-job, the broker needs a mechanism to re-queue unacknowledged messages. Design handlers to be idempotent so redelivered messages do not generate duplicate invoices or repeated side effects.

## 6. Managed Service Example: Scaling an API by Concurrency

On managed container platforms such as Google Cloud Run, operators can configure maximum concurrent requests per instance along with minimum and maximum instance counts. For example, an order-lookup API sets a concurrency limit of 40 requests per instance, a minimum of 2 instances, and a maximum of 30 instances.

When request volume rises, the platform adds instances based on load and internal signals. When load drops, it scales instances down according to service policy. The concurrency limit is critical: sending too many requests to one instance increases latency, CPU contention, or exhausts connection pools.

During testing, step the concurrency limit gradually—for example 10, 20, then 40 concurrent requests per instance. At each tier, measure p95/p99 latency, error rate, CPU, memory, and database connection count. Pick the value that meets SLAs and downstream limits rather than simply selecting the highest concurrency the platform permits.

Platforms like Amazon ECS also support scaling service task counts via target tracking, such as CPU, memory, or Application Load Balancer requests per target. For workers, you can use queue metrics from services like Amazon SQS with appropriate metric alarms and scaling policies. Regardless of platform, the rule stays the same: select a metric tied to real capacity, set min/max bounds, and verify behavior as load rises and falls.

## 7. Operational Trade-Offs and Incident Prevention

### 7.1. Reaction Speed vs. Cost

Rapid scale-out absorbs spikes quickly but can launch many containers at once, putting pressure on registries, networks, nodes, and downstream services. Slower scale-out conserves resources but risks queuing requests longer.

Higher minimum replicas cut startup lag during sudden bursts, at the expense of paying for idle capacity. Scale-to-zero suits infrequent workloads or those tolerant of cold starts; it is unsuitable when every request requires immediate response.

### 7.2. Downstream Service Limits

Adding API Pods can simultaneously multiply database connections. If each Pod opens a pool of 20 connections and the system allows 30 Pods, potential connections can reach 600. If the database only supports 200 connections, scaling out shifts the bottleneck from the API to the database.

Enforce connection pool limits, concurrency caps, rate limits, or queues to protect downstreams. `maxReplicas` should reflect the capacity of the entire processing chain, not container resources alone.

### 7.3. Startup and Readiness

New containers must pull images, boot the runtime, connect to services, and warm caches. During that window, unready Pods must not take traffic. Readiness probes must accurately reflect serving readiness; liveness probes should not fail solely because a dependency is briefly slow if doing so triggers endless container restarts.

For slow-starting apps, consider keeping a minimum number of warm replicas, trimming image size, optimizing startup paths, and checking platform scale-out rate limits.

### 7.4. Safe Scale-In

When reducing replica counts, the platform sends a termination signal to containers. The application must stop accepting new requests, finish or gracefully reject in-flight requests, and exit within the termination grace period.

Workers must trap termination signals, stop pulling new messages, and either finish current work or let the broker redeliver unacknowledged messages. Visibility or ack timeouts must align with processing times. Never acknowledge a message before results are durably persisted.

### 7.5. Replica Oscillation (Thrashing)

If a metric repeatedly crosses above and below its threshold, replica counts can oscillate up and down. This causes unstable costs and latency. Reduce oscillation using stabilization windows, cooldowns, scale-in rate limits, metric targets with headroom, and smoothed metrics.

Never set targets right at 100% capacity. Systems need headroom for variance, metric sampling lag, and container startup latency.

### 7.6. Observing the Right Outcomes

Track three metric groups simultaneously:

- **Capacity:** desired and actual replica counts, CPU, memory, concurrent requests, ready workers.
- **Service quality:** throughput, p95/p99 latency, error rate, timeouts, retry counts.
- **Queue health:** queue depth, oldest message age, arrival rate, completion rate, failed or dead-lettered messages.

Seeing container counts go up is not enough to declare autoscaling successful. If Pod counts rise while latency stays flat, the bottleneck may lie in databases, external APIs, shared locks, or network limits.

## 8. Autoscaling Verification Workflow

Run in a test or staging environment under controlled load:

1. **Capture baseline:** record replica counts, CPU, memory, throughput, p95 latency, and queue state under low load.
2. **Ramp load gradually:** step up user count or message publish rate. Note when metrics cross targets.
3. **Verify scale-out:** confirm desired replicas increase, new containers schedule, readiness passes, and traffic distributes evenly.
4. **Verify service quality:** confirm p95/p99 latency, error rate, and queue wait times stay within SLOs under steady peak load.
5. **Test maximum ceiling:** push load until hitting `maxReplicas`. Confirm downstream protections engage and backlog or latency alerts fire.
6. **Reduce load:** stop load generation and watch scale-in. Confirm stabilization windows/cooldowns take effect and replicas step down smoothly.
7. **Test container termination:** intentionally terminate a Pod serving traffic or processing messages. Confirm requests drain cleanly and no messages are lost.
8. **Compare costs:** compare runtime hours, average instance count, and resource consumption against budget targets.

A test suite should include both sharp spikes and gradual ramps. Sharp spikes test reaction speed; gradual ramps expose miscalibrated metric targets or scale thresholds. For workers, test messages with varying processing durations and failure scenarios to validate retries, idempotency, and dead-letter queues.

## 9. Troubleshooting Common Scenarios

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| High CPU yet HPA does not add Pods | Missing CPU requests, unavailable metrics, or HPA at max | Inspect `describe hpa`, Metrics Server, requests, and `maxReplicas` |
| Pods increase yet latency stays high | Bottleneck in database, external API, locks, or network | Correlate dependency latency, connection pools, and throughput |
| Queue grows yet workers do not scale | Scaler cannot read queue or metrics | Inspect `ScaledObject`, KEDA operator logs, Secret, and broker permissions |
| Workers scale up yet backlog keeps growing | Low per-worker throughput, `maxReplicas` too low, or poison messages failing repeatedly | Measure processing rate, message age, retries, and dead-letter queue |
| Pod count oscillates continuously | Noisy metrics, tight thresholds, or aggressive scale-in | Increase stabilization window/cooldown and cap scale-in velocity |
| New Pods stuck in Pending | Insufficient node CPU/memory, quotas, or scheduling constraints | Inspect events, node capacity, quotas, and cluster autoscaler |
| Requests fail during scale-in | App does not drain or termination window is too short | Inspect graceful shutdown, readiness, and termination grace period |

## 10. Pre-Production Checklist

- [ ] Selected a metric matching the real bottleneck: CPU, memory, concurrency, or queue.
- [ ] Derived min/max replicas from SLAs, quotas, budget, and downstream capacity.
- [ ] Declared appropriate resource requests/limits and readiness probes.
- [ ] Configured stabilization windows, cooldowns, and scale-in/scale-out rate limits.
- [ ] Protected broker connection details using Secrets or a platform secret store.
- [ ] Capped connection pools and concurrency to protect downstream dependencies.
- [ ] Ensured graceful shutdown, retry handling, and idempotency for workers.
- [ ] Monitored replica counts, latency, errors, queue depth, and message age.
- [ ] Tested load ramps, load drops, hitting `maxReplicas`, and container termination.
- [ ] Set alerts for missing metrics, scaler failures, or SLA-breaching backlogs.

## Conclusion

Effective container autoscaling starts with choosing the right signal. CPU fits compute-heavy workloads; concurrency fits concurrent request-handling services; queue depth and message age fit asynchronous workers. Min/max bounds, stabilization windows, readiness checks, and drain behavior determine whether the system reacts smoothly. Validate with realistic load and monitor both service quality and downstream dependency capacity before enabling scaling policies in production.
