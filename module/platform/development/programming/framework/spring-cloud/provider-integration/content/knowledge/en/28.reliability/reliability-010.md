# Safely Stopping Applications with In-Flight Messages or Requests

A Spring Boot process must do more than stop quickly; it must stop at a boundary where business state remains consistent. Upon receiving a stop signal, the application may still have active HTTP requests, messages received from a broker, uncommitted database transactions, events being published from an outbox, or background tasks writing files. Closing connections and thread pools immediately can sever requests mid-flight, cause messages to be redelivered or lost depending on settlement mode, and leave outbox events published without updating outbox status.

**Graceful shutdown** is the process of stopping new work intake, allowing in-flight work to finish within a bounded window, persisting required state, settling messages at the right moment, and closing resources in order. When the deadline expires, the application must still terminate safely under forced stop: uncommitted work is left for broker redelivery, while committed side effects are protected by idempotency.

This lesson belongs to the **Reliability** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing the integration of Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Explain failure windows when a process stops mid-request, mid-transaction, mid-settlement, or mid-publish.
2. Distinguish graceful shutdown, immediate shutdown, and crash recovery.
3. Design a sequence for readiness draining, stopping new intake, draining in-flight work, and closing resources.
4. Configure graceful shutdown for Spring Boot's embedded web server.
5. Stop message listeners/pollers while still handling ACK, Complete, Delete, or checkpoints properly.
6. Align visibility timeouts, message locks, ack deadlines, and checkpoints with drain duration.
7. Stop an outbox publisher without falsely marking events as published.
8. Close executors, schedulers, HTTP clients, cloud SDKs, and databases in the proper order.
9. Calculate a termination deadline aligned with Kubernetes or other runtime environments.
10. Test SIGTERM, deadline expiration, redelivery, duplicates, and post-restart recovery.

## 2. What Does Graceful Shutdown Protect?

An application may be performing several kinds of work concurrently:

- HTTP requests reading/writing a database.
- Message handlers that received a message and are running business logic.
- An outbox publisher that claimed an event and is sending it to a broker.
- Schedulers running batches or cleanups.
- Executors processing asynchronous tasks.
- Uploads/downloads transferring data with Blob/S3/Cloud Storage.
- Stream processors handling records not yet checkpointed.
- Sagas updating state and emitting downstream commands.

Goals of graceful shutdown:

- Stop accepting new work before closing resources.
- Allow in-flight work to finish within a time budget.
- Commit business state before ACK/Complete/Delete/checkpoint.
- Never mark a publish successful without confirmation per contract.
- Let the broker redeliver unfinished work if the process is forcibly terminated.
- Close clients, connection pools, and databases after workers stop.

Graceful shutdown cannot guarantee every task finishes. A request may outlast the termination deadline; a dependency may drop; a lock may expire. Your design needs a recovery path when draining does not finish.

## 3. Failure Windows When a Process Stops

### HTTP Request Cut Mid-Transaction

~~~mermaid
sequenceDiagram
    participant LB as Load balancer
    participant A as Spring Boot
    participant DB as Database
    LB->>A: Create order request
    A->>DB: BEGIN + write order
    Note over A,DB: SIGTERM arrives at process
    A--xDB: Process killed before COMMIT
    Note over DB: Transaction rolls back when connection closes
    LB-->>LB: Client may retry
~~~

If the transaction has not committed, the database typically rolls back when the connection closes. Yet the client may not know the outcome and retry the request. APIs need idempotency keys to prevent duplicate orders if the response is lost after commit.

### Message Processed but Not Yet ACKed

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant DB as Database
    B->>C: Deliver message M1
    C->>DB: BEGIN + update business
    DB-->>C: COMMIT
    Note over C: SIGTERM before ACK
    C--xB: Process stops, ACK not sent
    B->>C: Redelivery after restart
    C->>DB: Inbox checks M1
    Note over DB: Duplicate detected
    C->>B: ACK / Complete
~~~

This scenario can happen even during orderly shutdown. Committing before ACK plus inbox/idempotency makes redelivery safe.

### ACKing Before Commit Loses Business Effects

If a consumer ACKs a message and the process stops before database commit, the broker considers the message completed and will not redeliver it. Therefore, never ACK solely because the handler started or submitted work to an internal executor.

### Outbox Publish Succeeded but Not Marked SENT

~~~mermaid
sequenceDiagram
    participant P as Outbox publisher
    participant B as Broker
    participant DB as Database
    P->>B: Publish event E1
    B-->>P: Accepted
    Note over P: SIGTERM before outbox update
    P--xDB: Not marked SENT
    Note over DB: Outbox remains PENDING/IN_FLIGHT
    P->>B: Republish E1 after restart
    Note over B: May receive duplicate
~~~

Keep event IDs stable and use consumer inboxes to prevent repeated business effects. Never generate a new event ID when a publisher retries the same outbox record.

## 4. Shutdown Lifecycle: Stop Intake First, Close Resources Last

A general sequence:

~~~mermaid
flowchart TD
    A[SIGTERM / stop request] --> B[Mark instance NOT_READY]
    B --> C[Stop accepting new HTTP requests]
    B --> D[Stop polling/receiving new messages]
    B --> E[Stop scheduler from claiming new work]
    C --> F[Drain in-flight HTTP]
    D --> G[Drain message handlers]
    E --> H[Drain background jobs / outbox publish]
    F --> I[Wait for transactions and responses to finish]
    G --> J[Commit then ACK/Complete or leave for redelivery]
    H --> K[Persist state and publish confirmations]
    I --> L[Close executors and clients]
    J --> L
    K --> L
    L --> M[Close database / context]
    M --> N[Process exit]
~~~

Activities can run concurrently once new intake stops, while obeying resource dependencies:

1. Mark NOT_READY and begin draining ingress.
2. Stop accepting new HTTP requests and new messages.
3. Stop schedulers/outbox pollers from claiming new work.
4. Wait for active requests/handlers/publishers to finish.
5. Commit transactions and settle messages per contract.
6. Stop executors/background workers once queues drain or deadlines expire.
7. Close broker clients, storage clients, and HTTP clients.
8. Close the database connection pool and application context.

Never close the database before message handlers and outbox publishers finish updating state. Never close broker clients before listeners stop and required settlements are sent.

## 5. Readiness Draining and Stopping New Work Intake

Before a process exits, the orchestrator must stop routing new traffic to that instance.

### Readiness vs. Liveness

- **Readiness:** should this instance receive new traffic?
- **Liveness:** is the process alive and able to continue running?
- **Startup probe:** has the app finished starting up enough to check readiness/liveness?

When shutdown begins, readiness should transition to NOT_READY. Load balancers/orchestrators need time to update endpoints and stop sending new traffic. Readiness failure does not automatically stop message listeners; consumers must be paused/stopped explicitly.

Never fail liveness solely to initiate shutdown. Liveness failures can trigger forced restarts and cut draining short.

### Readiness Propagation Delay

Readiness and endpoint routing updates are not instantaneous. Some requests may still be routed by the load balancer during propagation. Embedded web server graceful shutdown and the application must still handle requests arriving during this transition window.

A brief drain delay after readiness flips can be used, but include it in your termination budget. Do not rely on fixed sleeps while ignoring real state when the platform provides proper lifecycle hooks.

### Message Ingress Must Be Controlled Separately

HTTP endpoint readiness does not stop brokers from delivering messages. For message-driven applications:

- Stop listener containers or subscriber pull loops.
- Stop long polling/prefetching new messages.
- Do not pull new batches if insufficient time remains before the deadline.
- Wait for active callbacks.
- For stream processors, stop fetching/assignments per client lifecycle and keep checkpoints safe.

## 6. Graceful Shutdown of the Spring Boot Web Server

Spring Boot supports graceful shutdown for embedded web servers. Common configuration:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

When the application context closes, the web server stops accepting new requests per server capabilities and waits for active requests to finish within the shutdown phase timeout.

Notes:

- This setting affects only the embedded web server managed by Spring Boot.
- It does not automatically drain all message listeners, schedulers, custom executors, or cloud SDKs.
- The timeout is a wait bound; requests running longer can still be cut off if the process is forcibly terminated.
- Verify behavior with your actual Spring Boot and web server versions.
- Client retries after lost responses require idempotency keys.
- For WebFlux, test reactive requests and downstream publisher cancellation.

### Application Lifecycle

Spring manages bean lifecycles and components implementing Lifecycle/SmartLifecycle. Lifecycle phases coordinate start/stop order. Phases start in ascending order and stop in reverse order; components with higher phases are requested to stop earlier.

This helps when a listener must stop before the resources it uses. However, not every binder/client uses the same lifecycle phase. Inspect each component's phase and stop semantics before relying on automatic ordering.

### Do Not Rely Solely on @PreDestroy

**@PreDestroy** suits closing a single resource or simple cleanup. A single cleanup method should not try to orchestrate the entire system when listeners, requests, and background tasks must drain. Use explicit lifecycle contracts with deadlines and states.

## 7. Managing In-Flight HTTP Requests

Graceful web server shutdown handles most of an embedded server's request lifecycle, yet applications still need to manage work detached from requests.

For example, a controller submits work to an executor and returns a response:

~~~java
@PostMapping("/reports")
public ResponseEntity<ReportAccepted> createReport(
        @RequestBody ReportCommand command) {
    reportExecutor.submit(() -> reportService.generate(command));
    return ResponseEntity.accepted()
            .body(new ReportAccepted(command.operationId()));
}
~~~

If 202 was returned while the task lives only in an in-memory queue, process shutdown loses the work. Two options:

- Write the command/outbox to durable storage before returning 202 so a worker can resume after restart.
- If the task is strictly best-effort, clearly define that it may be dropped on shutdown and never promise durable acceptance.

Never treat submitting to an executor as durable acceptance.

### Request Idempotency

Clients may time out and retry when the server committed but did not send the response. For order/payment creation:

- Accept an idempotency key from the client or generate an operation ID during durable intake.
- Save the key and outcome inside the transaction.
- Retries with the same key return the known result or in-progress status.
- Never create a new operation for the same intent just because the connection closed.

### Requests with Side Effects Outside the Database

If a request calls a payment provider and the process stops before saving the result, provider idempotency keys and reconciliation are essential. Graceful shutdown lowers the probability of interruption, but does not replace unknown-outcome recovery.

## 8. Safely Stopping Message Consumers

A consumer must perform these steps:

1. Stop receiving new messages.
2. Stop claiming additional batches or prefetching more work.
3. Wait for active handlers during the drain window.
4. Wait for database transactions to commit/roll back.
5. ACK/Complete/Delete only after commit.
6. If unable to finish before the deadline, do not ACK uncommitted messages; let the broker redeliver per semantics.
7. Close receivers/subscribers after required settlements stop.

### Handlers Running During Shutdown

Never kill threads immediately upon SIGTERM. Let handlers finish within a time cap if:

- They can commit within the deadline.
- The message lock/visibility/ack deadline remains valid or can be renewed.
- Dependencies are still available.
- Overall shutdown budget is respected.

If a handler cannot finish, roll back its transaction and let the message be redelivered. If the handler already triggered an external side effect, rely on idempotency/reconciliation on redelivery.

### Prefetch and Batch Size

Large prefetch/batch sizes increase the number of received-but-unprocessed messages when shutdown begins. This lengthens draining and risks lock/visibility timeout expiration.

Size prefetch/concurrency around:

- p95/p99 processing time.
- Message lock/visibility/ack deadline.
- Worker count.
- Shutdown grace period.
- Ability to renew locks/ack deadlines.
- Cost of redelivery and duplicates.

Never prefetch more work than can finish within expected processing and drain budgets.

## 9. Message Settlement Must Follow Business Commit

For queues supporting ACK/Complete/Delete:

~~~text
Receive message
  → Execute handler
  → Begin database transaction
  → Inbox + business update
  → Commit
  → ACK / Complete / Delete
~~~

If the process stops before commit, the message is not settled and can be redelivered. If commit finishes before stopping prior to ACK, redelivery is caught by the inbox.

For checkpointed streams:

~~~text
Read record at sequence N
  → Persist business state / inbox
  → Commit database
  → Checkpoint only through contiguous completed sequence
~~~

Never checkpoint past uncommitted records. If a failing record is durably saved to a failure store per policy, the checkpoint can advance past it after failure persistence completes and is audited.

### ACK Does Not Mean the Handler Finished

## 10. Azure Service Bus: Locks and Processor Shutdown

Azure Service Bus commonly uses Peek-Lock so consumers receive messages under a lock and Complete them after processing. During shutdown:

- Stop the processor/receiver from fetching new messages.
- Wait for active callbacks to finish if drain time permits.
- Commit the database before calling Complete.
- Ensure locks do not expire before handlers finish; use lock renewal during processing when needed.
- If the process stops or the lock expires before Complete, the message can be redelivered.
- Never Complete before business state is durable.

### Lock Expiry During Drain

Suppose a handler needs 45 seconds while only 20 seconds remain on the lock. If the lock cannot be renewed, the message may be redelivered while the old handler is still running. Two consumers could create concurrent side effects without idempotency/concurrency controls.

Therefore:

- Size lock duration/renewal to match processing duration.
- Bound drain time so enough time remains for Complete.
- Use inbox/unique constraints to guard transactions.
- Never assume stopping a processor renews locks indefinitely.
- Check stop/close APIs and callback behavior for your exact Azure SDK/binder version.

### Receive-and-Delete

With Receive-and-Delete, messages can be removed from the broker immediately upon delivery. If the process stops before the handler finishes, the broker cannot redeliver that message. Do not use this mode for work requiring durable processing unless another durable acceptance/recovery mechanism exists.

## 11. Azure Event Hubs: Stopping Processors and Checkpointing

Event Hubs consumers read streams per partition. During shutdown:

1. Stop receiving new events or stop the processor per API lifecycle.
2. Wait for active handlers to finish within bounds.
3. Commit business state before checkpointing.
4. Checkpoint only up to the last contiguously completed event in the partition.
5. Close the processor/client after required checkpoints are written.

If the process stops after database commit but before checkpointing, events can be re-read from the older checkpoint. Inbox/idempotency protects business effects.

If checkpointing occurs before business commit, events can be skipped after restart. For consumers processing in parallel, never checkpoint past an older event still in flight.

A checkpoint is read progress, not a shared transaction with the database. Use appropriate checkpoint stores and consumer groups; verify behavior during partition ownership changes/rebalances.

## 12. AWS SQS: Visibility Timeouts and Stopping Polling

An SQS consumer receives a message and the message becomes invisible for its visibility timeout. The consumer deletes the message after processing succeeds.

During shutdown:

- Stop long polling/receiving new messages.
- Do not pull new batches when insufficient processing time remains.
- Wait for active handlers to commit.
- Call DeleteMessage after commit.
- If unable to finish, do not delete; once visibility timeout expires, the message can be redelivered.
- Ensure visibility timeout covers processing and drain, or extend it during execution.

### Visibility Timeout and Redelivery

If the visibility timeout is shorter than handler runtime, the message can reappear before the old handler finishes. If shutdown runs long, the visibility timeout can expire and another consumer can receive the message.

Ensure:

- Size visibility timeout for p99 processing duration plus shutdown margin.
- Use ChangeMessageVisibility when processing needs extending per policy.
- Never extend indefinitely; enforce deadlines and maximum processing times.
- Use inbox/idempotency to guard against duplicates.
- For FIFO queues, note that a message group stays blocked until the message is deleted or visibility timeout expires.

### Never Delete Messages in a finally Block

Never call DeleteMessage unconditionally in a finally block. If the handler throws an exception or the transaction rolls back, deleting the message destroys retry opportunities. Delete only after business commit or after the failure is durably written to a failure store per policy.

## 13. AWS Kinesis Data Streams: Checkpoints and Shard Ownership

Kinesis consumers typically checkpoint sequence numbers per shard. With the Kinesis Client Library, worker/lease lifecycles and shard shutdown must follow the API/version in use.

When stopping:

- Stop fetching new records for shards or stop the worker per library lifecycle.
- Finish in-flight records if time remains.
- Commit business state before checkpointing.
- Checkpoint only through contiguously completed record sequences.
- Leave uncheckpointed records to be re-read when the shard resumes.
- When leases shift, the new worker resumes from the latest checkpoint.

Never checkpoint a newer record while an older record is unfinished. If processing in parallel, track contiguous completion. Use event IDs/inboxes to stop duplicates after restarts or lease handoffs.

## 14. Google Cloud Pub/Sub: Ack Deadlines and Subscriber Shutdown

Pub/Sub subscribers receive messages with an ack deadline. Client libraries can automatically extend deadlines during processing per lease management configuration.

During shutdown:

- Stop receiving new messages via the Subscriber/client lifecycle.
- Allow active callbacks to finish within bounds.
- Commit business state before ACKing.
- If not ACKed before the deadline expires, messages can be redelivered.
- Close the subscriber after required callbacks/settlements finish or the deadline expires.
- Use inbox/idempotency because redelivery can still occur under delivery semantics.

### Exactly-Once Delivery

If a subscription enables exactly-once delivery and the client/API meets supported conditions, ACK confirmation carries stronger semantics within the feature scope. That does not create a shared transaction with a database. A process can commit the database and stop before ACK confirmation; applications still need idempotent business effects and recovery.

### Flow Control

Flow control caps outstanding messages/bytes. Lowering outstanding counts speeds up draining and reduces messages holding leases during shutdown. However, too low a limit hurts normal throughput; size based on latency and capacity.

## 15. Spring Cloud Stream Binders and Listener Lifecycles

Spring Cloud Stream provides function/consumer abstractions, while lifecycle, pause/resume, acknowledgment, and stop behavior depend on the binder.

Verify:

- Which bean creates and manages the binding/listener container?
- Can new message intake be paused/stopped while still waiting for in-flight callbacks?
- When stopping, does the binder settle in-flight messages?
- When a handler returns normally, when does ACK/Complete execute?
- When a handler throws during shutdown, how do retries/DLQs behave?
- Can a batch listener stop mid-batch?
- Is manual acknowledgment supported and via which API?
- Can consumer concurrency/prefetch be reduced ahead of shutdown?
- Does closing the binder close clients shared with producers?

Never assume one stop command behaves identically across Service Bus, SQS, Pub/Sub, Event Hubs, and Kinesis. Write integration tests against your exact binder and version.

### Listener Containers and SmartLifecycle

Some listener containers implement Spring Lifecycle/SmartLifecycle. Spring can ask containers to stop by phase. For custom components, you can use SmartLifecycle to coordinate asynchronous stopping, invoking the callback only when draining genuinely finishes or the deadline expires.

Never invoke the callback immediately upon receiving a stop signal if handlers are still running. Conversely, holding the lifecycle callback indefinitely prevents the application context from closing on time.

## 16. Safely Stopping Outbox Publishers and Producers

Outbox publishers also require graceful shutdown:

1. Stop the scheduler/poller from claiming new records.
2. Keep already-claimed records in leased status.
3. Wait for active publishes to complete within the deadline.
4. Mark SENT only after broker confirmation.
5. If outcomes are unknown, leave records in retry/lease-expiry state; the next run publishes the same event ID.
6. Close producers/clients after publish tasks stop.
7. Never delete outbox records merely because the process is shutting down.

### If a Publish Was Accepted but Not Marked SENT

After restart, the publisher may resend the event. This is an expected duplicate under the failure model. Consumer inboxes and stable event IDs prevent repeated side effects.

### Stop Producers First or Consumers First?

No single order fits every topology. For an instance that both consumes commands and emits events:

- Stop ingress first.
- Wait for active handlers to commit and write outbox records.
- Stop the outbox poller from claiming new events once handlers stop generating new outbox rows.
- Drain in-flight publishes.
- Close broker clients.

If the outbox poller stops too early while HTTP/message handlers can still write outbox records, new events wait for another instance/worker. That is acceptable if the outbox is durable and another worker picks them up; otherwise coordinate shutdown ordering properly.

## 17. Stopping Schedulers, Executors, and Background Jobs

An executor holds two kinds of tasks:

- Already started and running.
- Queued and not yet started.

During shutdown:

- Stop submitting new tasks.
- Call shutdown to reject new submissions and let accepted tasks finish.
- Await termination for a bounded duration.
- When the deadline expires, request cancellation on cancelable tasks and log/record unstarted tasks.
- Never assume interrupts can halt blocking network I/O.
- Unstarted tasks in an in-memory queue must either be durably backed or allowed to drop per policy.

### Illustrative Java ExecutorService

~~~java
public void stopExecutor(ExecutorService executor, Duration timeout) {
    executor.shutdown();

    try {
        if (!executor.awaitTermination(
                timeout.toMillis(), TimeUnit.MILLISECONDS)) {
            List<Runnable> neverStarted = executor.shutdownNow();
            recordUnstartedTasks(neverStarted);
            executor.awaitTermination(
                    Math.min(1000, timeout.toMillis()),
                    TimeUnit.MILLISECONDS);
        }
    } catch (InterruptedException ex) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
~~~

This snippet is conceptual. In real applications, avoid spending the entire remaining timeout on each executor sequentially. Share a single shutdown deadline and pass remaining time to each phase.

### Scheduled Tasks

Schedulers must stop triggering new executions. A periodic task may already be running when shutdown starts; wait for it to finish if possible. Never let schedulers launch new batches after readiness turns NOT_READY.

## 18. Resource Closing Order

A practical rule:

| Resource | When to Stop / Close |
| --- | --- |
| Readiness/ingress | First |
| HTTP server accepting new requests | Start of drain |
| Message listeners/subscribers | Start of drain |
| Schedulers/pollers claiming new work | After blocking ingress from creating new work |
| In-flight handlers/requests | Wait to finish |
| Outbox publishers in flight | Wait for confirmation or leave for post-restart retry |
| Executors/background workers | After no new submissions arrive |
| Broker producer/consumer clients | After listeners/publishers stop |
| Storage/HTTP clients | After tasks using them finish |
| Database connection pool | Near the end |
| Application context/process | Last |

A resource that others depend on must close after the components using it. For instance, the database pool must stay open while handlers commit; the broker producer must stay open while the outbox publisher waits for confirmation.

Never close the database or broker client just because a bean's cleanup ran early. Use lifecycle phases/dependencies to enforce order and test with real shutdowns.

## 19. Shutdown Deadlines and Termination Budgets

Orchestrators typically grant processes a fixed window before sending SIGKILL or force-terminating. Every phase must fit inside that budget.

One way to budget:

~~~text
Termination grace period
  >= readiness propagation
   + stop accepting new work
   + in-flight drain
   + message settlement / checkpoint
   + resource cleanup
   + safety margin
~~~

Some phases can run concurrently, so you do not always sum all maxima, yet you must measure real durations and avoid blowing the overall deadline.

### Illustrative Budget Example

| Phase | Budget |
| --- | ---: |
| Readiness/endpoint propagation | 5 seconds |
| Stop accepting new HTTP/messages | 3 seconds |
| Drain requests/handlers | 20 seconds |
| Commit/ACK/checkpoint | 5 seconds |
| Close clients/executors/database | 5 seconds |
| Safety margin | 7 seconds |
| **Reference total** | **45 seconds** |

Numbers are illustrative only. Base yours on p95/p99 processing times, max handler duration, lock/visibility deadlines, and orchestrator settings.

### What Happens When the Deadline Expires?

If draining does not complete:

- Do not ACK uncommitted messages.
- Do not checkpoint past incomplete records.
- Do not mark outbox rows SENT when confirmation is unclear.
- Persist progress or operation state if possible.
- Safely cancel cancelable tasks.
- Let the broker redeliver unsettled messages.
- Rely on inbox/idempotency for safe reprocessing.
- Close resources and exit before the orchestrator force-kills if time remains.

Never try to keep the process alive indefinitely waiting on an outaged dependency.
## 20. Kubernetes: SIGTERM, preStop, and terminationGracePeriodSeconds

When Kubernetes terminates a Pod, kubelet executes the shutdown lifecycle, potentially running a preStop hook and then sending SIGTERM to the process per container stop behavior. The Pod has a termination grace period; once expired, the process may receive SIGKILL.

Example manifest:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: provider-integration
      image: example/provider-integration:1.0
      lifecycle:
        preStop:
          exec:
            command: ["/bin/sh", "-c", "sleep 5"]
~~~

This is illustrative only. preStop can initiate draining or allow endpoint propagation, but hook duration also consumes the termination grace period. Never add an arbitrary long sleep and forget how little time remains for Spring Boot.

### Readiness Probe

The readiness probe should reflect whether the instance is accepting traffic. When shutdown begins, the application can flip readiness state to REFUSING_TRAFFIC when using Spring Boot Actuator availability support.

Example probe configuration in Kubernetes:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 2
  failureThreshold: 1
~~~

Paths/ports must match Actuator and your deployment. Readiness probes do not replace stopping message listeners.

### Budgets Must Include preStop

The termination grace period starts before or during lifecycle hooks per Kubernetes semantics. Include preStop in your total time calculation and check your cluster/runtime version behavior. Configure the grace period larger than drain + cleanup plus a safety margin.

### Pod Disruption and Rolling Updates

During rolling updates or node drains:

- Readiness stops routing new requests.
- PodDisruptionBudget limits concurrent Pod disruptions, though it does not make an individual process drain cleanly.
- maxUnavailable/maxSurge impact capacity during rollouts.
- Applications must handle SIGTERM and restart idempotently.
- Consumer workers must coordinate with remaining replicas to pick up messages after a Pod exits.

## 21. Docker, systemd, and Non-Kubernetes Environments

Graceful shutdown does not apply only to Kubernetes.

### Docker

Docker stop typically sends SIGTERM and waits for a timeout before SIGKILL. Configure the stop timeout longer than the application's shutdown budget. Ensure the Java process receives signals directly; entrypoint scripts should use exec so signals are not trapped by a parent shell.

### systemd

Services can use TimeoutStopSec to cap stop duration. Set it higher than the designed drain/cleanup duration. Check KillSignal and the process tree so child workers are not orphaned.

### Other VM/Container Platforms

Verify exact stop signals, grace periods, health routing, and how the platform replaces instances. Never assume every platform sends SIGTERM in the same sequence.

## 22. Shutting Down During Long Uploads/Downloads or Streams

Streaming operations can last longer than typical HTTP requests:

- Blob/S3/Cloud Storage uploads.
- Large file downloads.
- Streaming responses via WebFlux.
- Reading/writing Event Hubs or Kinesis batches.
- Transferring data between two providers.

Define:

- Maximum operation duration.
- Chunk/part checkpoints.
- Multipart upload cleanup/abort.
- Resume tokens or offsets if supported.
- Temporary file cleanup.
- Idempotent object keys and conditional writes.
- Behavior when the process stops between chunks.

For multipart uploads, some parts may have been transmitted while the object is not committed. Recovery must resume or abort the upload per API/provider semantics; never treat starting an HTTP request as upload success.

For streaming responses, graceful web server shutdown waits for open requests within limits. For indefinite streams, enforce a maximum duration or reconnect/resume protocol.

## 23. Shutdown and Scheduled Maintenance

Background tasks such as outbox polling, reconciliation, cleanup, and scheduled exports need their own lifecycle.

- Stop triggering new runs.
- Stop claiming new batches once shutdown begins.
- Wait for the current batch to commit checkpoints/state.
- If a batch is incomplete, persist a cursor and retry after restart.
- Never delete files/records currently in use by consumers.
- Ensure jobs use leases/locks and fencing tokens across multiple replicas.
- Do not run outbox/inbox cleanup while publishers/consumers still need those records.

Cron-scheduled jobs can overlap with shutdown. Use distributed locks/leases and durable checkpoints to stop two instances from executing side effects together.

## 24. Readiness, Liveness, and Dependency Health During Shutdown

Do not turn every dependency outage into an immediate readiness failure, nor keep an instance accepting traffic once shutdown starts.

Principles:

- Readiness transitions to NOT_READY when draining starts.
- Liveness continues reflecting whether the process is deadlocked/broken.
- Dependency health exposes each provider's status without necessarily pulling the instance from the load balancer.
- During shutdown, readiness never reverts to ACCEPTING_TRAFFIC.
- Health checks must not fire heavy requests at draining dependencies.
- Never let liveness restart a process carrying out a controlled shutdown.

When using Spring Boot Actuator availability states, integrate readiness state with your orchestrator. Verify actual endpoint health groups and probe settings.

## 25. Observability for Shutdown

You must know which phase a process is in and how much unfinished work remains.

| Metric | Meaning |
| --- | --- |
| shutdown_started_total | Shutdowns initiated |
| shutdown_duration_seconds | Total shutdown duration |
| shutdown_phase_duration_seconds | Duration per shutdown phase |
| shutdown_deadline_exceeded_total | Times the shutdown deadline expired |
| readiness_drain_seconds | Time from NOT_READY until ingress stops |
| http_inflight_requests | Active HTTP requests |
| message_inflight_count | Active message handlers |
| message_settlement_pending | Processed messages awaiting ACK/Complete |
| outbox_inflight_publish_count | Active outbox publishes |
| outbox_pending_count | Unpublished outbox events |
| executor_active_count | Running tasks |
| executor_queue_depth | Queued tasks |
| checkpoint_lag | Distance from committed position |
| shutdown_forced_task_count | Tasks halted when deadline expired |

Shutdown logs should include:

- Shutdown reason/signal.
- Instance/pod ID and application version.
- Phase start/end timestamps.
- In-flight counts at phase start/end.
- Messages Completed/Deleted/ACKed.
- Unsettled messages left for redelivery.
- Outbox publish confirmations/unknown outcomes.
- Last committed checkpoint.
- Remaining deadline and forced-stop reasons.

Never log sensitive payloads or tokens. Include correlation IDs in logs while avoiding high-cardinality IDs in metric labels.

## 26. Testing Graceful Shutdown

A unit test calling bean close is not enough to prove a process handles SIGTERM properly. Run integration tests and tests on production-like runtimes.

### Test Matrix

| Scenario | Expected Outcome |
| --- | --- |
| No active requests/messages | Stops quickly and cleanly |
| HTTP request running, transaction commits before deadline | Response completes or client can look up result |
| HTTP request uncommitted at force stop | Transaction rolls back; client retry creates no duplicate |
| Message handler commits then shuts down before ACK | Redelivered; inbox blocks duplicate side effect |
| Message handler uncommitted at deadline | No ACK; broker redelivers |
| Outbox publish accepted but not marked SENT | May publish duplicate after restart; consumer deduplicates |
| Outbox publisher not yet sent | Record stays pending and is handled by next worker |
| Stream record committed but not checkpointed | Replay is deduplicated |
| Checkpoint before business commit | Test must flag risk of lost side effect |
| Visibility/lock/ack deadline expires during drain | Redelivery causes no duplicate business effect |
| Executor has queued tasks | Durable tasks recover; best-effort tasks are logged |
| Dependency unavailable during shutdown | Process exits within budget; unknown operations reconciled |
| Kubernetes sends SIGTERM then grace expires | App stops before force kill or leaves recovery to broker |
| Multi-replica rolling update | Traffic and messages absorbed by remaining replicas |

### Fault Injection

1. Send SIGTERM while an HTTP transaction is active.
2. Send SIGTERM after database commit but before sending the response.
3. Send SIGTERM after message commit but before ACK.
4. Let broker lock/visibility/ack deadlines expire while a handler runs.
5. Kill the outbox publisher right after broker confirmation.
6. Stop a stream consumer after business commit but before checkpointing.
7. Slow down the database so draining exceeds expected p99.
8. Force a dependency timeout and verify overall deadline adherence.
9. Leave tasks in executor queues when shutdown grace expires.
10. Restart Pods and verify redelivery/replay causes no duplicate side effects.

### Testing Against Managed Services

- Use dedicated test queues/topics/streams.
- Run production-matching binder and cloud SDK versions.
- Measure listener stop time and active handler counts.
- Inspect message lock/visibility/ack deadlines and delivery counts.
- Verify inbox, business state, outbox, and checkpoints after restart.
- Run rolling updates across multiple replicas to verify remaining capacity.
- Never deliberately force-kill production consumers handling live critical transactions.

## 27. Runbook When Instances Must Stop or Roll Out

### Before Rollout

1. Confirm remaining replicas have enough capacity for traffic/messages.
2. Check queue backlogs, processing lag, and outbox pending age.
3. Check handler p95/p99 and termination grace period.
4. Confirm readiness, SIGTERM, and lifecycle configs are deployed.
5. Check broker lock/visibility/ack deadlines are appropriate.
6. Pause large batch/replay jobs if they compete for capacity.

### When Shutdown Starts

1. Mark NOT_READY.
2. Stop accepting new HTTP requests.
3. Stop listeners/pollers from receiving new messages.
4. Stop schedulers from claiming new batches.
5. Wait for in-flight requests/handlers/publishers.
6. Commit then settle messages; never settle uncommitted work.
7. Log unfinished work and remaining deadline.

### After Restart

1. Check message redeliveries and delivery counts.
2. Verify inbox deduplication.
3. Verify remaining PENDING/IN_FLIGHT outbox records are reclaimed.
4. Verify checkpoints and replays from safe offsets.
5. Reconcile business operations with unknown outcomes.
6. Monitor duplicates, backlogs, and error rates.

### When Draining Does Not Finish

- Never extend the process indefinitely past the grace period.
- Leave unsettled messages for redelivery.
- Keep unconfirmed outbox records for publisher retries.
- Leave checkpoints at safe positions.
- Use idempotency/reconciliation to resolve uncertain operations.
- Record which phase and resource slowed down shutdown.

## 28. Lab Exercise: Safely Stopping an Order Consumer During Rollout

**Context:** The Spring Boot Order service runs three replicas on Kubernetes. Each replica serves HTTP requests, consumes OrderPaid from a managed broker, updates the database, and writes ReceiptRequested to the outbox. During a rolling update, a Pod may receive SIGTERM while processing an order or publishing an event.

### Part A — HTTP Graceful Shutdown

1. Enable graceful shutdown on the embedded server.
2. Configure lifecycle timeouts.
3. When shutdown starts, transition readiness to NOT_READY.
4. Verify the load balancer stops sending new requests.
5. Send an in-flight request plus SIGTERM; inspect transaction/response behavior.
6. Retry the client with the same idempotency key and verify no duplicate order is created.

### Part B — Message Consumer

1. Stop receiving/polling before closing the database.
2. Wait for the active handler to commit inbox and business state.
3. ACK/Complete/Delete after commit.
4. If the deadline expires, leave uncommitted messages for redelivery.
5. Restart the Pod and verify duplicates are handled by the inbox.

### Part C — Outbox Publisher

1. Stop the poller from claiming new records.
2. Wait for in-flight publishes to receive confirmation.
3. Mark SENT only after confirmation.
4. Kill the publisher between broker acceptance and marking SENT.
5. Restart and verify the same event ID is safely republished.

### Part D — Kubernetes Budget

1. Choose terminationGracePeriodSeconds based on drain and cleanup.
2. If using preStop, include hook time in the grace period.
3. Verify readiness propagation.
4. Run a rolling update with three replicas.
5. Measure shutdown phase durations and unsettled message counts.

### Deliverables

- Shutdown lifecycle diagram covering HTTP, listeners, outbox, and resources.
- Spring Boot graceful shutdown configuration.
- Kubernetes readiness/termination grace period configuration.
- Table of timeouts/locks/visibility/ack deadlines per broker.
- Test evidence for SIGTERM during requests and message handlers.
- Evidence that duplicate outbox publishes are deduplicated.
- Dashboard of shutdown duration, in-flight counts, pending settlements, and checkpoint lag.
- Runbook for rollouts and recovery after forced termination.

### Self-Check Questions

1. Why does readiness draining not automatically stop message listeners?
2. What does Spring Boot's graceful web server shutdown protect?
3. Why must new message intake stop before closing the database?
4. When a message is committed but not yet ACKed, what can happen?
5. Why can ACKing before commit lose business work?
6. How do Azure Service Bus locks, SQS visibility timeouts, and Pub/Sub ack deadlines affect draining?
7. Why must Event Hubs/Kinesis checkpoints follow contiguously completed records?
8. What should an outbox publisher do if the broker accepted an event before SENT was marked?
9. Why is submitting a task to an executor not durable acceptance?
10. How do Spring Lifecycle phases affect stop ordering?
11. Does Kubernetes preStop consume the termination grace period?
12. When the shutdown deadline expires, how should uncommitted messages be handled?
13. Why do client retries after lost HTTP responses need idempotency keys?
14. How do you verify shutdown is genuinely graceful during a rolling update?
15. Which metrics indicate a process was forcibly terminated with work remaining?

## 29. Takeaways

- Graceful shutdown begins by stopping new work intake, then drains in-flight requests/handlers/publishers, and finally closes resources.
- Readiness draining stops HTTP traffic; message listeners/pollers must be paused/stopped separately.
- Spring Boot web server graceful shutdown does not automatically drain every binder, scheduler, executor, or cloud SDK.
- Commit business state before ACK/Complete/Delete/checkpoint; if stopping before ACK, redelivery is handled via inbox/idempotency.
- Event Hubs/Kinesis checkpoint only through contiguously completed records; never skip past uncommitted records.
- Outbox publishers stop claiming new work, wait for in-flight publishes, and mark SENT only after broker confirmation.
- In-memory executor queues are not durable queues; ACK only once work or continuation intent is durably persisted.
- Close listeners/workers before broker clients and close the database near the end so transactions can still finish.
- Termination budgets must cover readiness propagation, drain, settlement, cleanup, and a safety margin; preStop also consumes time.
- When the deadline expires, leave unsettled messages for redelivery, keep checkpoints safe, and rely on idempotency/reconciliation to recover.
- Test SIGTERM during HTTP requests, message handlers, outbox publishing, and stream checkpointing in production-like environments.

## References

- [Spring Boot graceful shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Framework lifecycle and SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Kubernetes Pod termination lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Kubernetes probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Azure Event Hubs checkpoints and processor](https://learn.microsoft.com/azure/event-hubs/event-processor-balance-partition-load)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Amazon Kinesis Data Streams consumers](https://docs.aws.amazon.com/streams/latest/dev/building-consumers.html)
- [Google Cloud Pub/Sub lease management](https://cloud.google.com/pubsub/docs/lease-management)
- [Google Cloud Pub/Sub flow control](https://cloud.google.com/pubsub/docs/flow-control)
- [Spring Cloud Stream reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Java ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
