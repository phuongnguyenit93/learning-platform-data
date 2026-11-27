# Graceful shutdown and completing work before machine termination

In a cloud environment, a virtual machine or container can be stopped at any time due to a new version deployment, scale-in, host maintenance, infrastructure failure, or reclaim of interruptible capacity. If a process is abruptly terminated while processing requests or writing data, the application can lose work, leave partial transactions, or cause messages to be processed multiple times.

**Graceful shutdown** is a controlled termination sequence: the application stops accepting new work, lets in-flight requests finish within a time limit, persists required state, closes connections, and exits cleanly. For workloads subject to reclamation, the application must also recognize imminent stop signals or notices, proactively preserve progress, and be ready to resume on another machine.

This lesson belongs to the **CLOUD_CORE_SERVICES_COMPUTE** module and focuses on designing the application lifecycle to finish work before a VM or container stops. The content applies to APIs, queue workers, batch jobs, streaming consumers, and long-running services on virtual machines or container platforms.

## 1. Why can compute machines be stopped?

A workload must never assume its host will live forever. Common scenarios include:

| Scenario | What happens | Application requirement |
|---|---|---|
| Scale-in | Auto Scaling reduces machine count when load drops | Stop accepting new load and drain in-flight requests |
| Spot/preemptible eviction | Provider reclaims interruptible capacity | Receive advance notice if available, save checkpoints, and exit quickly |
| Rolling deployment | Old version is replaced by new version | Stop taking requests, finish running requests, and exit cleanly |
| Host maintenance | VM is migrated, restarted, or stopped for maintenance | Tolerate disruption upon notice and recover from durable state |
| OS or process failure | Machine or application cannot continue operating normally | Rely on timeouts, leases, retries, and application-level recovery |
| Operator-initiated stop | VM is shut down or deleted on schedule | Run drain, backup, or checkpointing procedures before stopping |

Spot or preemptible VMs cost less because the provider retains the right to reclaim capacity when needed. Notification mechanisms and advance warning windows vary across providers, resource types, and failure modes. Some platforms provide interruption notices or metadata events; in some cases, the machine stops sooner than expected. Never design an application around a fixed notice window assumed across all clouds.

Even regular VMs can fail abruptly. Therefore, graceful shutdown minimizes loss when preparation time exists, while recovery from sudden crashes must still be designed separately.

## 2. What is graceful shutdown?

Graceful shutdown is a sequence of steps enabling an application to stop at a safe boundary. Rather than terminating immediately upon receiving a signal, the application transitions into a **stopping** state and coordinates with load balancers, orchestrators, queues, and dependent services.

A typical sequence:

1. Receive a stop signal or reclamation notice.
2. Mark the instance as no longer ready to accept new work.
3. Stop accepting new requests, messages, or batches.
4. Wait for running requests and tasks to complete within the allowed time.
5. Save checkpoints or return unfinished work to the queue per protocol.
6. Persist data durably, flush buffers, and close transactions.
7. Close connection pools, consumers, listeners, and other resources.
8. Log final status and exit with an appropriate code.

~~~mermaid
sequenceDiagram
    participant P as Cloud / Orchestrator
    participant L as Load Balancer / Queue
    participant A as Application
    participant D as Database / Storage
    P->>A: Send stop signal or notice
    A->>A: Transition to draining state
    A->>L: Report no longer accepting new requests or messages
    L-->>A: Stop dispatching new work
    A->>A: Complete in-flight requests and jobs
    A->>D: Commit data or save checkpoint
    D-->>A: Confirm durable write
    A->>A: Close connections and resources
    A-->>P: Exit before deadline
~~~

Exact ordering varies by workload type. For example, an API must be removed from request routing before waiting for in-flight requests; a queue worker must stop polling before finishing the current job. The shared goal is accepting no new work once stopping begins and never marking work complete before results are safely stored.

## 3. Stop signals and deadlines

Applications need to know when to start shutting down. Common signals include:

- **SIGTERM:** requests a process to terminate gracefully on Unix/Linux and many container runtimes.
- **SIGINT:** typically triggered when a user or terminal interrupts a process.
- **Service control:** on Windows, Service Control Manager sends a stop request to a Windows Service.
- **Orchestrator lifecycle event:** the orchestration platform notifies that a pod, task, or instance is about to be replaced.
- **Cloud interruption notice:** the provider warns before reclaiming a Spot/preemptible instance when supported.
- **Application endpoint or admin command:** a management system calls an internal API to initiate draining.

Do not rely on signals from only one source. For instance, an application might receive SIGTERM during a deployment but receive a metadata event when a Spot VM is reclaimed. Funnel these events into a single handler that transitions state to draining.

### 3.1. Bounded shutdown time

Operating systems and orchestration platforms usually wait only for a finite duration. If the application has not exited when time expires, the system can force-kill the process or VM. Thus, graceful shutdown must enforce a deadline.

Let:

- T_n: time to stop accepting load and update status.
- T_f: maximum time allotted to in-flight requests/jobs.
- T_p: time to write checkpoints or finalize data.
- T_c: time to close connections and exit.
- T_g: buffer margin to absorb variance.
- T_d: total time granted before forced termination.

The design must satisfy:

\[
T_n + T_f + T_p + T_c + T_g < T_d
\]

This is a time budget, not a mandatory fixed sleep. Measure real request/job durations, pick appropriate limits, and preserve margin for busy periods. If a job routinely runs for tens of minutes while the machine only receives tens of seconds of warning, you cannot wait for the job to finish; split work smaller, checkpoint frequently, or choose more suitable compute.

### 3.2. Two layers of timeout

Maintain at least two bounds:

- **Application deadline:** the application's own limit on waiting for requests, jobs, data flushes, and shutdown.
- **Platform termination deadline:** the limit enforced by the OS, container runtime, or cloud provider.

The application deadline must be shorter than the platform deadline so the application has time to close cleanly. If both limits are equal, the process may be killed before cleanup completes.

## 4. Stopping new load and draining connections

An API may be processing requests while the load balancer continues sending new ones. If the process stops immediately, both new and in-flight requests risk failing.

A drain workflow for interactive services typically includes:

1. Mark the instance as draining or not ready.
2. Stop accepting new connections or stop advertising the endpoint.
3. Wait for the load balancer and service discovery to update.
4. Continue processing already-accepted requests within a time limit.
5. Send responses or close connections cleanly per protocol.
6. Exit once no requests remain in flight or the deadline expires.

Readiness and liveness have distinct meanings. Readiness indicates whether an instance should receive traffic; liveness indicates whether the process is still alive or needs restarting. When shutdown begins, flip readiness to false. Never fail liveness just to drain, or the orchestrator may restart the process unnecessarily.

### 4.1. HTTP keep-alive and in-flight requests

HTTP keep-alive allows reusing connections. On shutdown, the server must stop accepting new requests on the listener, finish already-accepted requests, and close sockets cleanly. For HTTP/2 or WebSockets, handle streams or long-lived connections per protocol; avoid dropping sockets unannounced when proper close frames can be sent.

For long-running requests, application-level deadlines and client retry mechanisms may be needed. Retries are safe only when requests carry idempotency keys or operations can repeat without creating duplicate transactions.

### 4.2. Avoiding traffic while load balancers update

Readiness updates or load balancer deregistration take time to propagate. Applications need a drain window aligned with platform propagation. Stopping the listener too early causes already-routed requests to reset; waiting too long risks breaching the shutdown deadline.

Measure the actual delay from marking unhealthy/not-ready until new requests stop arriving. Never assume load balancers, service meshes, or DNS resolvers update instantaneously.

## 5. Completing worker and queue tasks

Message-processing workers can often be interrupted mid-job. Distinguish three states:

- **Received:** the worker has pulled the message or acquired a job lease.
- **In progress:** results have not yet been durably confirmed.
- **Completed:** results are safely persisted and the message is acknowledged.

Crucial rule: **acknowledge only after results are durably stored**. If you acknowledge first and the worker is killed while writing data, the message vanishes while work remains incomplete. If data is written and the worker is killed before acknowledging, the message may be redelivered; hence, operations must be idempotent.

### 5.1. Stop polling first, finish current job second

Upon receiving a shutdown signal, a worker should:

1. Stop calling receive/poll so no additional messages are pulled.
2. Maintain the lease or visibility timeout for the current job within reasonable bounds.
3. Finish the job if possible before the deadline.
4. Commit results and only then acknowledge.
5. If completion is impossible, save a checkpoint or release the job back to the queue per protocol.
6. Close consumers and connections.

If the queue supports visibility timeouts, set them long enough for normal processing or renew them safely. When a worker stops, the lease can expire so another worker picks up the job. Never hold leases indefinitely or keep renewing once the application can no longer complete work.

### 5.2. Idempotency and duplicate handling

Many queue systems provide at-least-once delivery: messages can be delivered more than once if a worker disconnects or fails to acknowledge in time. Workers therefore need idempotency:

- Give every job a unique ID or idempotency key.
- Store processing state in a database or durable store.
- Use transactions to update results and job state together when possible.
- Check whether a job already completed before applying side effects again.
- Use unique constraints or conditional writes to prevent duplicate writes.

Do not assume graceful shutdown guarantees exactly-once processing. Exactly-once is a complex end-to-end pipeline property; it typically requires combining idempotency, transactions, checkpoints, and messaging protocol semantics.

### 5.3. Python worker example

The snippet below illustrates stopping polling, finishing a running job within bounds, and acknowledging after successful persistence. Queue and `process_job` functions are hypothetical adapters to be replaced with real libraries.

~~~python
import asyncio
import signal

stop_requested = asyncio.Event()
MAX_JOB_SECONDS = 40

async def handle_one_job(queue, job):
    try:
        # Bound processing time to fit within the shutdown budget.
        result = await asyncio.wait_for(
            process_job(job),
            timeout=MAX_JOB_SECONDS,
        )
        # Acknowledge only after results are durably stored.
        await persist_result(job.id, result)
        await queue.ack(job)
    except Exception:
        # Retry/release must follow queue semantics.
        await queue.retry_or_release(job)

async def run_worker(queue):
    while not stop_requested.is_set():
        job = await queue.receive(timeout=1)
        if job is None:
            continue

        # If a stop signal arrived during receive, release the job instead of starting it.
        if stop_requested.is_set():
            await queue.release(job)
            break

        await handle_one_job(queue, job)

        # If shutdown arrived during processing, exit the loop here.
        if stop_requested.is_set():
            break

    await queue.close()

def request_shutdown():
    stop_requested.set()

async def main(queue):
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, request_shutdown)
    loop.add_signal_handler(signal.SIGINT, request_shutdown)
    await run_worker(queue)
~~~

In production applications, explicitly handle task cancellation, persistence failures, ack failures, and queue close timeouts. Choose MAX_JOB_SECONDS according to the platform's termination window; if jobs exceed that budget, checkpoint or split jobs rather than simply raising the timeout. The signal registration shown fits Unix-based event loops; Windows requires corresponding signal or service control mechanisms.

## 6. Checkpointing long-running tasks

A batch job may run longer than the advance reclamation notice. In that case, save progress via checkpoints so a new machine can resume.

A checkpoint can contain:

- Job ID and algorithm version.
- Processed position, such as offset, record count, or partition name.
- Intermediate state required to resume.
- Timestamp and input data version.
- Integrity verification details.

Write checkpoints to durable storage such as a database or object storage. Never store checkpoints solely in RAM or on ephemeral VM disks subject to reclamation.

### 6.1. Checkpoint frequency

Checkpointing too frequently increases I/O and cost; checkpointing too infrequently increases rework after a failure. Determine cadence based on:

- Processing time between checkpoints.
- Write cost and checkpoint size.
- Maximum acceptable progress loss.
- Interruption probability and recovery time.

For jobs divisible into independent partitions, saving per-partition progress lets another worker resume unfinished partitions. When writing checkpoints, use atomic operations or versioned writes to avoid half-written state.

### 6.2. Avoiding inconsistent checkpoints

Checkpoints and output data must reflect the same progress point. If a checkpoint is written before outputs are saved, a subsequent run may skip uncreated outputs. If outputs are written but the checkpoint is not updated, the job may re-process that segment. Use transactions, commit markers, idempotent outputs, or an appropriate two-phase protocol to handle this.

## 7. Graceful shutdown on Linux and Windows

### 7.1. Linux and systemd

On Linux, SIGTERM is typically the signal asking a process to terminate gracefully. Applications should register signal handlers, stop accepting new work, wait for active tasks, and close resources. SIGKILL cannot be caught or handled; if a process still runs past its deadline, the system may send SIGKILL to terminate it.

For systemd services, you can configure the stop timeout:

~~~ini
[Unit]
Description=Catalog background worker
After=network-online.target

[Service]
Type=simple
User=catalog
ExecStart=/opt/catalog/bin/worker
Restart=on-failure
KillSignal=SIGTERM
TimeoutStopSec=55s

[Install]
WantedBy=multi-user.target
~~~

TimeoutStopSec is an example configuration for a systemd service. The application must finish shutting down within this interval; otherwise, systemd may terminate the process per the service's kill policy. Align this timeout with external VM or container deadlines. An inner-layer timeout cannot extend how long the cloud provider permits the machine to survive.

Commands to inspect the service:

~~~bash
# Check service status
systemctl status catalog-worker

# Request graceful stop
systemctl stop catalog-worker

# View logs during shutdown
journalctl -u catalog-worker --since "10 minutes ago"
~~~

Do not use kill -9 as a normal stop method because SIGKILL bypasses cleanup.

### 7.2. Windows Service

A Windows Service receives stop requests via Service Control Manager (SCM), typically SERVICE_CONTROL_STOP. The service should transition to stop pending, stop accepting new work, complete running tasks, persist data, and report stopped when finished.

For longer cleanup tasks, Windows provides preshutdown notifications for services configured to support them. Preshutdown wait times and SCM timeouts must be coordinated with host and cloud platform shutdown workflows. Never assume a service is always granted unlimited time to exit.

Key implementation items:

- Handle stop controls and cancel new listeners/consumers.
- Set deadlines on in-flight requests or jobs.
- Use cancellation tokens or equivalent mechanisms to propagate stop signals to components.
- Flush critical logs and data.
- Close database connections, threads, timers, and handles.
- Write event logs if shutdown fails or times out.

PowerShell can issue a service stop command:

~~~powershell
# Check service status
Get-Service -Name "CatalogWorker"

# Request service stop
Stop-Service -Name "CatalogWorker"

# Verify service stopped
Get-Service -Name "CatalogWorker"
~~~

These are illustrative administrative commands; the executing account needs appropriate permissions and the service must implement a controlled stop handler.

## 8. Graceful shutdown in containers and Kubernetes

Container runtimes and orchestrators have their own lifecycles. When stopping a container, the runtime typically sends a termination signal to the main process (PID 1), waits for a period, and force-kills it if the process has not exited. Default signals and wait periods can vary by runtime configuration.

Containerized applications should:

- Run the main process directly or use a proper init process to forward signals.
- Catch SIGTERM and run cleanup.
- Avoid shell wrappers that swallow signals without forwarding them to the application.
- Expose a readiness endpoint or equivalent draining mechanism.
- Align shutdown timings with orchestrator limits.

### 8.1. Kubernetes termination flow

When a Pod is deleted or replaced, Kubernetes marks the Pod as terminating, updates EndpointSlices to remove the Pod from ready endpoints, runs any preStop hook, sends the stop signal to containers, and waits up to terminationGracePeriodSeconds. If a container still has not exited when time expires, the runtime may send SIGKILL.

Endpoint updates and network propagation take time. Applications must still handle requests routed while changes propagate.

Example Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: api
          image: registry.example/catalog-api:v2
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: http
          livenessProbe:
            httpGet:
              path: /health
              port: http
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]
~~~

This example illustrates a 60-second grace period and a short preStop hook. sleep does not drain requests by itself; the application must still handle SIGTERM and close the server properly. Hooks also consume time inside the grace period rather than adding extra time outside the configured budget. In production, prefer a drain endpoint or explicit application behavior over relying solely on a fixed sleep.

### 8.2. Shutdown budget in Kubernetes

Suppose a Pod has terminationGracePeriodSeconds set to 60 seconds. You can allocate part of that time to endpoint draining and the remainder to in-flight requests and cleanup. Measure exact values for your application. If preStop spends 10 seconds, the application has less time left to finish requests after receiving SIGTERM.

Do not let livenessProbe fail simply because the Pod entered terminating state. Readiness removes the Pod from traffic; liveness should continue reflecting process health while it finishes existing work.

## 9. Reclaiming Spot/preemptible VMs

Spot or preemptible VMs can be reclaimed when the provider needs capacity. Some platforms deliver advance events or notices via APIs, metadata endpoints, event services, or notification channels.

Application design should follow these principles:

1. Run a component monitoring interruption notices per provider documentation.
2. Upon receiving a notice, immediately switch the application to draining.
3. Stop pulling new jobs or deregister from the load balancer.
4. Save checkpoints and finish tasks that fit within the budget.
5. Return unfinished work to the queue or let leases expire safely.
6. Record the stop reason and checkpoint state so a new instance can resume.
7. Maintain spare fleet capacity or replacement instance groups to preserve serving capacity.

Avoid coupling application logic directly to a single provider's metadata endpoint if running multi-cloud. Build an adapter that emits an internal event such as ShutdownRequested(reason, deadline), with provider-specific adapters underneath.

### 9.1. Internal event interface example

~~~text
ShutdownRequested
  reason: "spot-interruption" | "scale-in" | "deployment" | "maintenance"
  deadline: timestamp
  source: "cloud-event" | "signal" | "orchestrator" | "operator"
~~~

The application listens for this event and runs one unified shutdown workflow. The deadline lets it calculate remaining budget rather than assuming every shutdown grants the same duration.

### 9.2. Replacing instances and preserving capacity

For stateless APIs, the load balancer shifts traffic to other instances once the reclaimed instance drains. For workers, the queue holds work for a new worker to resume. For batch workloads, the scheduler can launch a replacement job from the checkpoint.

Maintain sufficient spare capacity or rapid instance launch capability. Graceful shutdown only protects how a single instance exits; it does not automatically ensure the system retains enough serving capacity after reclamation.

## 10. Designing shutdown for each workload type

| Workload | On stop initiation | How to preserve work |
|---|---|---|
| HTTP API | Set readiness false, stop accepting new connections | Finish in-flight requests, close server |
| Queue worker | Stop polling and pulling new messages | Finish job, commit then ack; or release/let lease expire |
| Batch job | Stop acquiring new partitions or processing steps | Save checkpoint and output state |
| Streaming consumer | Stop consuming new partitions or records | Commit offsets after outputs are durably saved |
| WebSocket service | Reject new sessions, notify active clients | Let clients reconnect or migrate sessions if supported |
| GPU job | Stop accepting new batches | Save model/checkpoint and sync data to durable storage |
| Database | Stop accepting new writes per database procedures | Use database engine shutdown/replication/backup mechanisms |

Databases require special handling. Never send kill signals directly to database processes in place of formal shutdown procedures. Use the database engine's management commands or managed service workflows so transactions settle and data stays recoverable.

## 11. Observing and logging the shutdown process

You cannot improve shutdown behavior without knowing how long it takes and where it fails. Emit structured logs and metrics for each phase:

- Timestamp when the stop signal arrived and signal source.
- Time taken to flip readiness false or deregister from the load balancer.
- Count of in-flight requests/jobs when stopping began.
- Count of requests/jobs completed, retried, or checkpointed.
- Time spent flushing data and closing connection pools.
- Total shutdown duration.
- Count of forced kills or deadline breaches.
- Count of retried jobs, redelivered messages, or failed requests around deployments.

Suggested metrics:

| Metric | Meaning |
|---|---|
| shutdown_started_total | Number of times the application initiated shutdown |
| shutdown_duration_seconds | Time from receiving stop signal to process exit |
| shutdown_deadline_exceeded_total | Number of times shutdown budget was exceeded |
| inflight_requests | Requests in progress during drain |
| inflight_jobs | Jobs in progress during shutdown |
| checkpoint_duration_seconds | Time spent saving checkpoints |
| jobs_retried_after_shutdown_total | Jobs retried after an instance stopped |

Metric names are illustrative; follow your system's telemetry conventions. Never log sensitive data, tokens, or full payloads in shutdown logs.

## 12. Testing graceful shutdown

Test shutdown in a representative environment, not merely by checking whether the process catches SIGTERM.

Scenarios to test:

1. Stop the application when no requests or jobs are running.
2. Stop under high concurrent requests and keep-alive connections.
3. Stop when a job is nearly complete.
4. Stop when a job exceeds the shutdown budget.
5. Stop mid-write or mid-transaction commit.
6. Lose connectivity to the queue or database during shutdown.
7. Send two consecutive stop signals.
8. Send SIGKILL or simulate host loss to verify abrupt crash recovery.
9. Perform a rolling deployment or scale-in under load.
10. Simulate a Spot interruption and verify a new instance resumes from the checkpoint.

Pass criteria:

- No new work accepted after transitioning to draining.
- In-flight requests complete or fail cleanly in a controlled manner.
- Messages are acknowledged only after results are durable.
- Unfinished jobs can be retried or resumed.
- No partial writes corrupt business state.
- Application exits before the deadline under supported conditions.
- System maintains adequate capacity or recovers per service targets.

Always test cases where graceful shutdown gets no chance to run. Cloud hosts can vanish or processes can be killed abruptly; backups, replication, queues, transactions, and idempotency form the next line of defense.

## 13. Practical example: order-processing worker

An online store runs multiple workers reading messages from a queue to process orders. Each job checks inventory, records order state, and calls a payment service. When a worker receives a scale-in notice, it must stop pulling new jobs while finishing the order currently in progress.

Appropriate workflow:

1. Worker enters draining state and stops polling the queue.
2. Worker continues processing the current job within the allowed window.
3. Order updates use transactions or idempotency keys.
4. Results are persisted durably to the database.
5. Worker acknowledges the message only after the commit succeeds.
6. Worker closes connections to the queue and database and exits.
7. If the deadline nears before completion, the worker saves a checkpoint or releases the job for another worker to pick up.

If the worker acknowledged immediately upon receiving the message, the order could be abandoned if the machine were reclaimed. If the worker committed to the database before failing to ack, the message may be redelivered; idempotency prevents duplicate charges or duplicate orders. That is why shutdown workflows must be designed alongside queue and database semantics.

## 14. Design checklist

Before deploying a workload to the cloud, verify:

- Which stop signals the application receives: SIGTERM, service control, orchestrator events, or cloud interruption notices?
- Who is responsible for flipping readiness and stopping new load?
- How many requests/jobs can run concurrently?
- What are the maximum processing duration and shutdown deadline?
- Which data must be committed, flushed, or checkpointed?
- When are messages acknowledged? How are leases/visibility timeouts managed?
- Are jobs idempotent and safe to retry?
- Which connections must close and in what order?
- Do logs/metrics show whether shutdown succeeded or exceeded its deadline?
- Have rolling deployments, scale-in, interruptions, and abrupt host loss been tested?

## 15. Common mistakes

- **Handling SIGTERM without draining traffic:** load balancers may keep routing new requests while the application exits.
- **Acknowledging messages too early:** messages are removed from the queue before results are durably stored.
- **Missing idempotency:** redelivered messages cause duplicate transactions or side effects.
- **Long jobs without checkpoints:** machine reclamation forces all progress to restart from zero.
- **No deadline set:** cleanup drags on until the platform force-kills the process.
- **Setting application timeout equal to platform timeout:** no buffer remains to close connections.
- **Treating preStop as complete graceful shutdown:** hooks do not replace shutdown logic inside the application.
- **Using liveness to drain:** can trigger unnecessary restarts instead of removing traffic.
- **Assuming Spot notices always arrive on time:** event behavior varies by provider and failure type.
- **Testing only graceful stops:** failing to verify power loss, host loss, or SIGKILL recovery.
- **Protecting only the instance while forgetting capacity:** the instance exits safely, yet the system lacks capacity to serve load.

## 16. Key takeaways

Graceful shutdown enables controlled application termination during deployments, scale-in, maintenance, or compute reclamation. Applications must catch signals, transition to draining, stop accepting new work, finish or checkpoint running work, persist data durably, close resources, and exit before the deadline.

For workers and streaming consumers, coordinate checkpoints, leases, retries, commits, and acknowledgments. For APIs, drain requests and connections. Across Linux, Windows, and Kubernetes, signaling mechanisms differ, yet the application should funnel them into one time-bounded shutdown workflow. Finally, test both graceful shutdowns and abrupt machine losses to ensure workloads resume on other compute without losing or duplicating work.
