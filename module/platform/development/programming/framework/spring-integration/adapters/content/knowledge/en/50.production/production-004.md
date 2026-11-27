# Concurrency and Connection Pool Limits in Spring Integration Adapters

> **Chapter:** Production  
> **Lesson:** Concurrency and connection pool limits  
> **Module:** Spring Integration Adapters  
> **Context:** Connecting external systems via inbound/outbound adapters, gateways, pollers, and `MessageChannel`; handling files, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC with message contracts, errors, and connection lifecycles.

## 1. Learning Objectives and Scenario

After completing this lesson, you will be able to:

1. Distinguish **concurrency**, **parallelism**, **throughput**, **inflight messages**, **queue depth**, **thread pool**, and **connection pool**.
2. Size processing limits from arrival rates, resource hold times, available connections, and downstream quotas.
3. Choose the right Spring Integration channel—`DirectChannel`, `ExecutorChannel`, `QueueChannel`, and others—while understanding sync/async boundaries.
4. Configure `TaskExecutor`, `TaskScheduler`, pollers, batch sizes, and inflight limits without creating unbounded queues or threads.
5. Design backpressure, bulkheads, rate limiting, fairness, and load-shedding mechanisms when external systems slow down.
6. Identify technology-specific limits for File, SFTP, HTTP, JMS, AMQP, Kafka, and JDBC.
7. Verify transactions, acknowledgements, ordering, idempotency, and retries when raising concurrency or scaling across multiple instances.
8. Plan load/soak/failure tests, dashboards, runbooks, and pre-production go/no-go criteria.

**Cross-cutting scenario:** A Spring Boot service uses Spring Integration to poll files from SFTP every 5 seconds, write orders to JDBC, call a partner HTTP API, and emit Kafka events. Scaling from 1 to 5 replicas multiplies tasks quickly, yet the partner HTTP API allows only 40 concurrent requests and the database provides only 30 shared connections. The result can be rising pool waits, request timeouts, Kafka backlogs, duplicate files, and retry storms. The system must **cap load at the bottleneck**, not merely by CPU count or pod count.

**Version boundaries:** Specific API names and properties vary across Spring Integration, Spring Boot, Spring Framework, clients/brokers, and library versions. Examples are reference models; check documentation and test with **your exact application version** before deploying to production.

## 2. Understanding Resource Metrics

| Concept | Meaning | Example |
|---|---|---|
| **Concurrency** | Number of operations actively in progress within a scope | 20 HTTP requests currently in flight/waiting |
| **Parallelism** | Number of tasks executing simultaneously on compute cores | 8 CPU-bound tasks running across cores |
| **Throughput** | Messages/tasks completed per unit time | 120 messages/s |
| **Arrival rate (λ)** | Incoming message rate | 150 messages/s |
| **Service time (W)** | Duration an item holds a resource from start to step completion | 0.25 s/HTTP request |
| **Inflight** | Items received but not yet completed/acked per contract | 50 unacked broker messages |
| **Queue depth** | Messages/tasks waiting for execution | 200 tasks in executor queue |
| **Thread pool** | Set of application threads executing work | 16 worker threads |
| **Connection pool** | Reusable physical/logical connections to an external system | HikariCP 24 DB connections |
| **Pool acquisition wait** | Time spent waiting for a free connection from the pool | 300 ms to borrow a JDBC connection |
| **Backpressure** | Slowing/pausing new intake when downstream cannot keep up | Pause poller when queue is full |
| **Bulkhead** | Isolating resource limits per partner/flow | Max 8 HTTP calls to partner A |
| **Rate limit** | Capping invocations per time window | 200 calls/minute |
| **Capacity** | Sustainable throughput under target conditions | 90 orders/s with p95 under SLO |
| **Saturation** | Resource approaching or hitting its limit | Pool active=24, pending=80 |

### 2.1. Concurrency Does Not Equal Connection Count

A thread may be:

- Waiting in a queue and **holding no connection**;
- Executing JDBC and **holding a DB connection**;
- Waiting on an HTTP response and **holding a pooled HTTP connection**;
- Sleeping in backoff **without holding a connection**, yet still occupying a thread if retrying synchronously;
- Waiting on a lock, forcing a transaction to hold its connection longer;
- Performing async/non-blocking I/O without binding one thread per request.

Conversely, a connection pool may hold idle connections; some clients multiplex multiple requests over one connection depending on protocol (e.g., HTTP/2). Thus you cannot simply set `maxThreads = maxConnections` and call it done. Measure **connections held over time** and actual client behavior.

### 2.2. Multi-Layer Concurrency

A flow might look like:

~~~text
SFTP poller -> File/message handler -> ExecutorChannel queue
            -> JDBC transaction -> HTTP outbound gateway -> Kafka publisher
~~~

Each leg has its own limits and resource hold behavior. If `ExecutorChannel` accepts 500 tasks while the HTTP pool has only 20 connections, you can have 20 tasks calling HTTP, dozens waiting on the pool, and hundreds buffered in the queue. Track **active + waiting + buffered + already acknowledged** explicitly instead of one generic concurrency figure.

## 3. Capacity Modeling: Quantify Before Raising Pool Sizes

### 3.1. Little's Law in Steady State

For a relatively stable system:

\[
L = \lambda W
\]

Where:

- `L`: average number of concurrent items inside a scope (waiting **or** processing, depending on boundary definition);
- `λ`: average completion rate in steady state;
- `W`: average time an item remains in that scope.

**Example:** 80 HTTP requests/s, each holding an HTTP connection for an average of 0.2 s:

\[
L_{\mathrm{connection}} \approx 80 \times 0{.}2 = 16.
\]

This suggests roughly **16 connections in use on average**, yet it does **not** mean a pool of 16 always suffices: p95/p99 latency, bursts, retries, handshakes, and headroom alter peak demand. Load-test to choose the max size based on SLOs and partner quotas.

Another example: if downstream latency jumps from 0.2 s to 1 s while still receiving 80 requests/s, inflight demand jumps from ~16 to **80**. If the pool is capped at 20, the rest must queue, trigger backpressure, or fail—no thread-pool setting makes downstream faster.

### 3.2. Capacity of the Slowest Stage

In a serial flow, sustainable throughput cannot exceed the slowest stage (ignoring pipelining/batching effects):

\[
R_{\mathrm{flow}} \le \min(R_{\mathrm{SFTP}},R_{\mathrm{DB}},R_{\mathrm{HTTP}},R_{\mathrm{Kafka}},\ldots).
\]

If the database commits 120 rows/s and the partner HTTP API caps at 50 requests/s, adding Kafka partitions or executor threads will not push flow completion past 50 requests/s if every order must call HTTP.

### 3.3. Estimating Backlog Growth

Suppose intake arrives at 150 orders/s while the system completes only 100 orders/s. Under steady rates without load shedding:

\[
\Delta Q / \Delta t \approx 150 - 100 = 50\ \mathrm{orders/s}.
\]

After 10 minutes, backlog can grow by **30,000 orders** (rough estimate, ignoring variance/drops). If each item uses 4 KiB on the heap, payload alone occupies ~117 MiB before object/header overhead, retry state, and metadata. Choose **bounded queues** and full-queue policies before going to production.

### 3.4. Practical Sizing Steps

1. Measure arrival rates during peaks and bursts, not just daily averages.
2. Measure p50/p95/p99 service times for each dependency.
3. Confirm downstream **quotas and max concurrent calls**.
4. Estimate inflight demand from load × resource hold time.
5. Choose headroom, max pool sizes, bounded queues, rejection policies, and throttles.
6. Run load/soak tests; monitor pending waits and error rates approaching saturation.
7. Tune from empirical measurements rather than "bigger is always better".

**Do not treat Little's Law as an exact pool-sizing formula** when the system is overloaded, continuously retrying, or facing volatile arrivals. It guides reasoning and bottleneck detection; production settings still require real load testing.

## 4. Multi-Layer Limit Diagram

~~~mermaid
flowchart LR
    SRC["SFTP / File / HTTP / Broker"] --> IN["Inbound endpoint"]
    IN --> POLL["Poller / listener concurrency"]
    POLL --> CH["Bounded MessageChannel"]
    CH --> EXEC["Bounded TaskExecutor"]
    EXEC --> DB["JDBC pool + transaction limit"]
    DB --> HTTP["HTTP pool + partner bulkhead"]
    HTTP --> PUB["Kafka / JMS / AMQP publisher"]
    PUB --> OUT["External target"]
    CH -. "Queue full" .-> BP["Pause / slow ingress"]
    EXEC -. "Rejection" .-> BP
    DB -. "Pool wait high" .-> BP
    HTTP -. "429 / latency" .-> BP
    PUB -. "Lag / broker errors" .-> BP
    BP --> OBS["Metrics + alerts + runbook"]
    DB --> OBS
    HTTP --> OBS
~~~

A production system needs an explicit **overload contract** at each boundary:

- **Pause ingress:** Only when the source durably retains messages/files/rows and supports resumption.
- **Bounded queue:** Only when full-queue outcomes are handled cleanly without dropping already-acked messages.
- **Reject:** Return retryable errors to callers when the contract supports it.
- **Durable buffering:** Persist messages in a broker/outbox/inbox before acknowledging.
- **Bulkhead:** Cap per-dependency/per-tenant resources to prevent noisy neighbors.
- **Rate limit:** Enforce call quotas per time window, not merely concurrent slots.

## 5. Choosing `MessageChannel` Types for Backpressure and Transactions

Spring Integration offers several channel types. Picking the wrong one can turn a smooth local flow into a bottleneck or a message-loss point.

| Channel | Message Handoff | Concurrency Impact | Misconfiguration Risks |
|---|---|---|---|
| **DirectChannel** | Synchronous on sender thread | Slow handlers block upstream thread; downstream throttles via caller | Stalls pollers/HTTP listeners; exceptions propagate backward |
| **ExecutorChannel** | Dispatched via `TaskExecutor` | Decouples threads; workers and queue managed by executor | Unbounded queues, rejected tasks, transaction context does not cross threads |
| **QueueChannel** | Buffers messages for receiver/poller | Decouples producer/consumer via capacity and receive rate | In-memory queues are not durable by default; full queue blocks or drops per caller |
| **PublishSubscribeChannel** | Fans out to multiple subscribers | Sync or async depending on config | One slow/failing subscriber affects sibling branches |
| **PriorityChannel** | Orders by priority | High-priority flood causes starvation | Reorders business sequence; starves low-priority work |
| **RendezvousChannel** | Direct handoff when sender meets receiver | Sender can block waiting for receiver | Deadlocks or timeouts when no receiver is present |

### 5.1. `DirectChannel`: Simple with Natural Backpressure

~~~text
SFTP poller thread
  -> DirectChannel
     -> validate
        -> JDBC insert
           -> HTTP outbound gateway
              -> response
~~~

If HTTP takes 20 seconds, the poller thread blocks until the handler returns. That gives natural backpressure, yet if one scheduler runs multiple pollers, **one slow dependency can delay unrelated pollers**.

Pros: clear transaction/error propagation on a synchronous path. Cons: does not decouple long I/O and ties up source threads.

### 5.2. `ExecutorChannel`: Thread Separation Does Not Equal Durability

~~~text
Inbound poller -> ExecutorChannel
                     |
               bounded executor
                 8 workers
                queue max 64
                     |
                outbound HTTP
~~~

Required configuration:

- Core/max threads sized to workload;
- Finite queue capacity;
- Explicit rejection policy;
- Shutdown behavior and `awaitTermination`;
- Monitoring for active threads, queue depth, and task rejections;
- Deliberate transaction/correlation context propagation.

**Note:** Transactions typically bind to threads. Crossing an `ExecutorChannel` changes where transactions start/end and how errors propagate back to sources—never assume an upstream `@Transactional` spans async handlers.

### 5.3. `QueueChannel`: Distinguish Memory from Persistence

With an in-memory `QueueChannel`, messages **can be lost if the process crashes** even after successful enqueue. For critical business data:

- Use a persistent `MessageStore` or durable broker;
- Understand enqueue/dequeue transactions and source ack timing;
- Configure bounded capacity and send timeouts;
- Define full-buffer handling policies;
- Provide resume/drain and DLQ/replay paths;
- Crash-test right after the sender receives "send succeeded".

Likewise, a durable queue alone does not guarantee exactly-once consumer side effects. Enforce idempotency on redelivery.

### 5.4. Do Not Switch to Async Just to Dodge Timeouts

If an HTTP inbound gateway awaits a reply, inserting an `ExecutorChannel` frees some handler threads, yet **the caller still enforces its reply deadline**. For long-running work, an accepted-request + durable tracking/status contract fits better; changing channels alone does not convert a sync flow into a full async contract.

## 6. Pollers: Capping Fetch Volume and Spawned Tasks

### 6.1. Distinct Poller Controls

| Control | Effect | Does Not Replace |
|---|---|---|
| Poll interval / fixed delay | Frequency of source checks | SFTP/JDBC operation timeouts |
| Fixed rate / cron | Trigger schedule | Non-overlap guarantee across all setups |
| `maxMessagesPerPoll` | Max messages fetched per poll cycle | Downstream worker/stage limits |
| Receive timeout | Max wait to fetch an item from a pollable source | Whole-flow side-effect limits |
| Poller `TaskExecutor` | Runs polled tasks on the configured executor | Multi-pod distributed locking |
| Scheduler pool size | Polling tasks runnable by the scheduler | Source system connection pools |
| Transactional polling | Wraps poll in transaction per supported mechanism | Cross-system exactly-once |

### 6.2. Why `maxMessagesPerPoll` Alone Is Not Enough

A poller fetching up to 20 messages every 5 seconds can submit 20 tasks to `ExecutorChannel` immediately. If each task spends 30 seconds on HTTP and the executor queue is large, pending tasks accumulate across poll cycles. Combine:

- Max batch size and poll interval;
- Bounded executor queues;
- Downstream concurrency limits;
- Source pause/throttling when queues fill up;
- Explicit retry/backoff ownership;
- Service-level SLOs and backlog age monitoring.

**With 4 replicas**, `maxMessagesPerPoll=20` per replica can pull far more than 20 items cluster-wide. Calculate **replica count × per-instance effective work** rather than treating one pod's config as a cluster quota.

### 6.3. File Inbound Java DSL Example

~~~java
import java.io.File;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.file.dsl.Files;
import org.springframework.messaging.MessageChannel;

@Configuration
class FileIngressFlowConfig {

    @Bean
    MessageChannel readyFiles() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow readyFileIngress() {
        return IntegrationFlow
                .from(
                    Files.inboundAdapter(new File("/srv/inbox/ready"))
                         .patternFilter("*.ready"),
                    endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofSeconds(5))
                               .maxMessagesPerPoll(10)
                    )
                )
                .channel("readyFiles")
                .get();
    }
}
~~~

This is a **structural example** of an inbound adapter and poller, not yet production-ready: add handlers, file-ready protocols, persistent filters/claims, error flows, idempotency, archiving/replay, multi-replica coordination, and metrics. Verify DSL APIs against your project's Spring Integration version.

### 6.4. Poller Checklist

- [ ] Poll schedule fits arrival rates and downstream throughput.
- [ ] Effective `maxMessagesPerPoll` or batch limits are set.
- [ ] Cluster-wide total inflight is bounded, not just per-replica.
- [ ] No overlapping scans/transfers while remote work is still active.
- [ ] Pause/resume controls, backlog metrics, and oldest-pending alerts exist.
- [ ] Source retains items safely when pollers pause.
- [ ] Distributed claims/partitioning protect shared files/rows across replicas.
- [ ] Tested network timeouts/slow reads and scheduler starvation.
- [ ] Full queues never falsely ack or mark source items DONE.

## 7. `TaskExecutor` and `TaskScheduler`: Set Explicit Bounds

### 7.1. `ThreadPoolTaskExecutor` with Bounded Queue

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Bean(name = "partnerIoExecutor")
ThreadPoolTaskExecutor partnerIoExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(16);
    executor.setQueueCapacity(64);
    executor.setThreadNamePrefix("partner-io-");
    executor.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    executor.initialize();
    return executor;
}
~~~

**Illustrative meaning:**

- Pool maintains at least 8 core threads, scaling up to 16 under sustained load per queue policy.
- Queue capacity 64 bounds queued tasks inside the executor.
- When full, `AbortPolicy` rejects new tasks; the caller path must **handle rejections** and ensure sources remain unacked or backed by durable recovery.
- Graceful shutdown waits up to the configured limit for active tasks.

**Important warning:** In `ThreadPoolExecutor` configurations with positive queues, tasks enter the queue **before** scaling threads past `corePoolSize`. Setting core=8, max=16, queue=64 does not mean 9 tasks immediately spawn 9 threads. Load-test `ThreadPoolTaskExecutor` scaling behavior for your version.

### 7.2. Choosing a Rejection Policy

| Policy | Behavior | Risk |
|---|---|---|
| `AbortPolicy` | Throws exception when task is rejected | Requires error/retry/ack handling to avoid message loss |
| `CallerRunsPolicy` | Runs task on caller thread if executor is still running per policy semantics | Can block pollers/HTTP ingress and alter thread/transaction boundaries |
| `DiscardPolicy` | Silently drops task per policy semantics | **Unsuitable** when reliable message delivery is required |
| `DiscardOldestPolicy` | Drops oldest queued task to retry adding the new one | Risks losing messages or breaking ordering |

Do not blindly default to `CallerRunsPolicy` everywhere. While it provides backpressure, you must test **source acks, transactions, thread ownership, and shutdown**—forcing an HTTP servlet thread to run slow business logic can breach gateway SLAs.

### 7.3. `TaskScheduler` Can Become a Bottleneck

Multiple pollers in an app often share a small scheduler. If slow SFTP/JDBC calls hold scheduler threads, unrelated pollers slip their schedules.

Checklist:

- [ ] Map which pollers use which scheduler.
- [ ] Size scheduler pools for concurrent blocking tasks and service times.
- [ ] For slow I/O, consider separating the scheduler from a bounded worker executor.
- [ ] Never let scheduler threads wait indefinitely on remotes.
- [ ] Emit metrics for poll delays, execution duration, and skipped/overlapping polls.
- [ ] Test multiple pollers hitting remote failures concurrently.
- [ ] When scaling replicas, ensure total poll rate stays within source quotas.

### 7.4. Avoid Mixing CPU-Bound and I/O-Bound Work in One Pool

- CPU-bound validation/serialization benefits from core-count-aligned threads.
- I/O-bound HTTP/SFTP/JDBC waits on remotes; concurrency can exceed core counts but is bounded by connection pools, quotas, and memory.
- Sharing one pool between heavy CPU tasks and stalled I/O can starve both.
- Splitting pools by criticality/target protects vital flows, while monitoring **total** process threads and memory.

## 8. Connection Pools: Sizing, Lifecycle, and Exhaustion Handling

### 8.1. Four Decision Areas

Every pool must define:

1. **Max active/leased connections:** Prevent opening more sessions than downstream allows.
2. **Acquisition timeout:** Stop callers from waiting forever on an empty pool.
3. **Idle eviction/lifetime/validation:** Prevent reusing dead sockets and leaking connections.
4. **Shutdown/reconnect policy:** Close resources cleanly and avoid connection storms on deploy/recovery.

### 8.2. Connection Pools Differ from Retries

A timed-out downstream I/O call can invalidate a pooled connection and trigger reconnects. Retrying on the same thread while still holding a connection raises pressure; long timeouts can pin the entire pool while zero useful work finishes.

High pool wait times should be resolved by **reducing inflight load or adding verified capacity**, never merely by raising acquisition timeouts.

### 8.3. Cluster-Wide Capacity Budget

Suppose a database allows **100 connections** for an application group alongside other consumers. After reserving slots for other services, admin tasks, migrations, and headroom, this application group gets at most 60.

With **5 replicas**, setting Hikari `maximumPoolSize=12` per pod already consumes the full 60-connection budget if all pools fill. Scaling to 10 replicas without adjusting pool sizes can exceed the DB limit even if each pod has only a few active workers.

| Variable | Hypothetical Value |
|---|---:|
| DB max connections | 100 |
| Reserved for other systems/ops/headroom | 40 |
| Application budget | 60 |
| Planned replicas | 5 |
| Max pool size/replica | 12 |
| Max total application connections | 60 |

These numbers are **budget illustrations only**. Databases also have CPU, I/O, lock contention, and transaction limits; a pool of 60 does not prove the DB can run 60 heavy concurrent queries.

### 8.4. Downstream-Driven Concurrency Bound Formula

If each task holds one HTTP/DB connection:

\[
C_{\mathrm{effective}} \le \min(C_{\mathrm{executor}}, C_{\mathrm{pool}}, C_{\mathrm{downstream}}, C_{\mathrm{policy}}).
\]

However, if a task holds **two connections simultaneously** or a client multiplexes multiple requests on one connection, adjust the formula to actual behavior. Never hold a JDBC connection while waiting on an HTTP response when transactions and external calls can be cleanly separated.

### 8.5. General Pool Checklist

- [ ] Clear owner and quota for each pool/target.
- [ ] Budgets include peak replicas during autoscaling and rolling deployments.
- [ ] Pool acquisition timeout is shorter than the request deadline.
- [ ] Validation/idle/lifetime policies align with both client and server.
- [ ] Metrics track active, idle, pending, and wait duration.
- [ ] Tested connection leaks, half-open sockets, and reconnect storms.
- [ ] Never share one admin credential across all adapters.
- [ ] On pool exhaustion, callers follow an error/recovery path rather than blocking forever.
- [ ] Pool shutdown closes sockets/sessions cleanly per lifecycle.
- [ ] Explicitly distinguish connection counts from max concurrent operations on multiplexed protocols.

## 9. Backpressure: Need a Clean Stop When Capacity Runs Out

Without real bounds, bottlenecks turn into memory leaks, timeout storms, or retry storms. Design backpressure from ingress to egress.

### 9.1. Load-Shedding Mechanisms

| Mechanism | How It Works | When Appropriate |
|---|---|---|
| **Bounded channel/executor queue** | Caps waiting messages/tasks | Prevents uncontrolled memory growth |
| **Pause/throttle poller** | Slows intake rate from source | Source file/DB/broker can safely retain data |
| **Semaphore/bulkhead** | Caps concurrent operations per target | Partner HTTP/SFTP/DB has explicit concurrency limits |
| **Rate limiter** | Caps calls per time window | API calls/minute quotas, broker throughput limits |
| **Circuit breaker** | Temporarily halts calls when target fails severely | Prolonged remote outages |
| **Durable broker/inbox** | Persists messages durably before processing | Sustained mismatch between arrival and egress rates |
| **Reject with retryable response** | Returns controlled errors to caller | HTTP inbound with retry contract and idempotency |
| **Cooperative consumer pause** | Pauses intake/processing via supported APIs | Kafka/JMS/AMQP with container-specific pause support |

### 9.2. Never Drop Messages After Acknowledging

If a message is received and acknowledged to the source, and `ExecutorChannel` subsequently rejects the task without durable recovery, you risk **message loss**.

Principles:

1. While the source still holds the message, allow failure/rollback/nack for policy-based redelivery.
2. Once the source is acknowledged, a **durable handoff** must already exist.
3. For in-memory queues, document crash-recovery semantics; never mislabel them durable.
4. For long retries, route to durable retry queues/outboxes instead of sleeping on connection-holding threads.
5. For data errors, route to DLQ/quarantine with ownership and evidence.

### 9.3. Backpressure Is Not Rate Limiting

A **concurrency limit** allows at most 10 concurrent requests. If each takes 100 ms, that still sends 100 requests/s. A **rate limit** of 30 requests/s prevents quota breaches even at low concurrency. Many partners enforce both. Implement **both controls** whenever both limits exist.

### 9.4. Fairness and Noisy Neighbors

One tenant sending a million records can monopolize workers and connections, starving other tenants.

- Separate queues/cohorts by tenant or approved priority;
- Enforce per-tenant max inflight and rate limits;
- Reserve baseline capacity for critical flows;
- Prevent starvation of lower-priority messages;
- Monitor lag/oldest age per cohort;
- Avoid spawning excessive per-tenant thread pools that breach total process thread limits.

**Fair scheduling is an operational policy**, enforced with appropriate queues, workers, and limiters—not an automatic feature of every `MessageChannel`.

## 10. File Adapter: Concurrency, Filesystem, and Multiple Replicas

File inbound differs from brokers: files sit in a directory with no built-in consumer-group partitioning. Running multiple pollers on the same folder can make multiple instances pick up the same file.

### 10.1. Limits to Define

| Resource | Sizing Basis | Failure Mode |
|---|---|---|
| Directory scans | Poll interval, scheduler capacity, directory size | Scans take too long; schedules overlap |
| Files picked per poll | Batch / `maxMessagesPerPoll` | Task and memory spikes |
| Concurrent parsing | CPU, memory, file descriptors | Parsers holding multiple large files |
| Concurrent business processing | Worker pool + DB/HTTP capacity | Slow DB commits build backlog |
| File descriptors / open streams | OS/container limits | Too many open files |
| Disk / inode space | Source, archive, failed/quarantine, temp files | Writes/extractions fail |
| Multi-replica claims | Distributed locks/metadata/inbox | Duplicate processing or lost handoffs |

### 10.2. One Large File Differs from 1,000 Small Files

With `maxMessagesPerPoll=20`, pulling twenty 500 MB files into handlers simultaneously can exhaust heap, disk, or FDs. Require:

- Limits on file size, row count, and parser memory;
- Streaming parsers where possible instead of buffering entire files in heap;
- Max concurrent files scaled by size/type;
- Bounded executors and downstream rate limits;
- Ready protocols/timeouts to avoid partial uploads;
- Lossless archiving/quarantine.

### 10.3. Multiple Replicas

- Use **persistent accept-once metadata** in an appropriate store to remember seen files across restarts, while recognizing metadata filters do not replace business idempotency.
- For multi-replica setups, enforce shared/distributed claims/locks, directory partitioning, or coordinator election.
- If a worker crashes after claiming a file, provide lease expiry/recovery and business deduplication keys.
- Never mark files DONE before business side effects commit durably.
- On NFS/SMB/network mounts, test rename/lock semantics and network-drop behavior.
- Record source file ID + checksum/business ID to investigate files sharing names or modified content.

### 10.4. File Checklist

- [ ] Scan/poll rate matches directory size and file arrival rate.
- [ ] Concurrent parsers, memory, and FD usage are bounded.
- [ ] File-ready protocol prevents reading partial uploads.
- [ ] Multiple pods cannot process the same file outside design rules.
- [ ] Incomplete files survive and recover across restarts.
- [ ] Business idempotency keys supplement accept-once filters.
- [ ] Metrics track oldest pending file, active files, failures/quarantine, and disk space.

## 11. SFTP: Limit Sessions/Transfers Before Adding Workers

SFTP runs over SSH sessions, and remote servers commonly enforce connection/session/channel quotas. Adding application threads does not increase server-allowed transfers.

### 11.1. SFTP Sessions and Connection Pools

Depending on client/session factory, you may manage:

- TCP/SSH connections to the remote server;
- SSH channels/SFTP subsystem sessions;
- Bounded session caches/pools;
- Threads/blocking I/O listing directories or reading files;
- Inflight remote uploads/downloads;
- Local destination filesystem and disk buffers.

**Never equate "one session = one TCP connection"** across all SSH implementations. Check the exact limits documented by your library/server and measure actual open connections/channels.

Classes like `DefaultSftpSessionFactory` and `CachingSessionFactory` appear in Spring Integration SFTP, yet exact APIs and behaviors evolve across versions—especially when the underlying SSH client changes. Check how **cache size, wait timeout, shared sessions, validation, and close/reconnect** work in your version.

### 11.2. Illustrative Budget Formula

Suppose a partner permits **12 concurrent transfers** per account. With 3 replicas, steady state might allocate up to 4 transfers per replica. However, reserve headroom for reconnects, maintenance, other jobs sharing the account, and rolling-deployment bursts.

| Hypothetical Parameter | Value |
|---|---:|
| Remote concurrent transfer quota | 12 |
| Concurrent replicas during rolling deploy | 4 (old + new pods) |
| Conservative per-pod transfer limit | 2 |
| Planned total concurrency | 8 |
| Headroom / ops reserve | 4 |

This is a **budget-allocation example**, not a universal rule. If the quota applies cluster-wide per account, local per-pod semaphores **will fail** when autoscaling exceeds expected pods; use distributed coordination or hard HPA/deployment caps.

### 11.3. Timeouts and Session Leases

- [ ] Session acquisition wait is bounded so workers don't block forever on full pools.
- [ ] Connect, SSH handshake, and remote operation timeouts match client capabilities.
- [ ] Broken sessions are invalidated/reconnected properly instead of returned to cache as healthy.
- [ ] Reconnect retries/backoff use jitter to prevent connection storms upon SFTP recovery.
- [ ] Avoid holding SFTP sessions while parsing files or calling HTTP: finish download and close/return sessions early.
- [ ] Cap max inflight bytes/file sizes and local disk usage.
- [ ] Metrics track active/idle/waiting sessions, transfer duration, errors, and remote throttling.
- [ ] Tested server session limits, mid-transfer network drops, pod scale-outs, and credential rotation.

### 11.4. SFTP Outbound

If an outbound adapter writes a file and times out during rename, retries can create duplicates. Higher concurrency increases the chance two workers collide on a target filename. Enforce deterministic naming, temp file + rename, version guards against accidental overwrites, checksums/manifests, and remote state reconciliation after ambiguous outcomes.

## 12. HTTP: Connection Pools, Request Concurrency, and Partner Quotas

HTTP outbound gateways can use `RestTemplate`, `RestClient`, `WebClient`, or other clients. Depending on implementation:

- **Connection pooling** or per-request connections may be used;
- HTTP/1.1 typically maps sockets/connections to concurrent requests per client design;
- HTTP/2 can multiplex multiple streams over a single connection;
- **Per-route/per-host** caps, total connections, and pending-acquisition queues apply;
- Non-blocking I/O reduces thread counts, but does not remove inflight/request quotas or memory limits.

### 12.1. Layers to Control

| Layer | Limit | Risk |
|---|---|---|
| Inbound HTTP server | Request threads/event loops, max connections, request size | Client floods exhaust resources |
| Spring Integration gateway | Reply timeout, correlation, concurrent requests | Delayed replies, large backlogs |
| Worker executor | Active threads, queue capacity | Unbounded queues |
| HTTP connection manager | Total/per-route connections, pending acquires, idle/lifetime | Pool starvation and connection leaks |
| Partner API | Max concurrent requests, rate per minute, tenant quotas | 429, 503, bans/throttling |
| Circuit/bulkhead | Max active/queued calls | Failing partner drags down entire app |
| Business idempotency | Request ID, operation state | Retries duplicate effects |

### 12.2. Concurrency Differs from Rate Limiting

Suppose a partner enforces **20 concurrent requests** and **100 calls/s**. At 0.5 s average response time, reaching 100 calls/s needs ~50 inflight requests—which exceeds 20, so concurrency caps actual throughput. When latency climbs to 2 s, 20 inflight yields roughly 10 calls/s in simple steady state.

Do not crank an executor to 100 threads trying to hit a rate target that partner quotas and latency physically prevent.

### 12.3. HTTP Outbound Checklist

- [ ] Identify actual client/request factory and pooling/multiplexing semantics.
- [ ] Configure appropriate max total/per-route connections or max streams.
- [ ] Set pool acquisition, connect/read/response timeouts, and overall deadlines where supported.
- [ ] Isolate max inflight per partner; avoid one shared global pool for everything.
- [ ] Enforce partner rate limits divided across replicas.
- [ ] Retry/backoff uses jitter without pinning all workers on 429/503.
- [ ] Enforce idempotency/reconciliation before retrying unsafe operations after timeouts.
- [ ] Metrics track leased/idle/pending connections, acquisition waits, 429/503, latencies, and queues.
- [ ] Tested slow servers, half-open sockets, pool leaks, and remote connection caps.

### 12.4. HTTP Inbound Gateway

When ingress spikes while downstream is slow:

- Return 429/503/202 or appropriate **contract responses** instead of buffering everything on the heap;
- For async processing, durably persist the request before returning Accepted;
- Enforce per-client/tenant quotas and authentication;
- Require idempotency keys on side-effecting requests;
- Avoid careless `CallerRunsPolicy` usage that forces servlet threads past gateway deadlines;
- Monitor active requests, rejected requests, and business completion latency.

## 13. JMS: Consumer Concurrency, Prefetch, and Session Transactions

For JMS inbound listeners, connections/sessions/consumers and dispatch policies are governed by the JMS provider and container. **Consumer count does not universally equal TCP connection count.**

### 13.1. Limits to Separate

| Control | Effect | Depends On |
|---|---|---|
| Listener concurrency | Concurrent consumers/sessions processing messages | JMS listener container |
| Connection factory/pool | Connection/session caching, max sessions | Broker/provider/client |
| Prefetch/consumer window | Messages pre-dispatched to consumer before ack | Provider configuration |
| Ack/transaction | When broker considers messages complete | Session mode and transaction manager |
| Queue/topic subscription | How messages distribute across consumers | JMS semantics, durable subscriptions |
| Handler executor | Concurrent business tasks and error propagation | Spring Integration channel/handler |
| DLQ/redelivery | Broker retry counts and error routing | Provider-specific policy |

### 13.2. High Prefetch Can Hurt Fairness

A consumer with large prefetch can hoard **dispatched-but-unprocessed** messages, starving peer consumers and making queue depth look artificially small despite real backlog.

When workers slow down, monitor:

- Ready/pending queue counts;
- Dispatched/unacked messages;
- Active/idle consumers;
- Processing latency;
- Redelivery rates and DLQ age.

Do not blindly raise prefetch just to chase throughput. When ordering matters, raising concurrency can alter observed processing order.

### 13.3. JMS Checklist

- [ ] Listener concurrency is bounded by business handler and DB/HTTP capacities.
- [ ] Connection/session pool sizes match JMS provider limits.
- [ ] Prefetch/consumer windows are backed by load testing.
- [ ] Session transactions/acks and redelivery semantics are well understood.
- [ ] Consumers are idempotent when brokers redeliver after DB commits.
- [ ] Under saturation, listeners can pause/stop cleanly while the broker retains messages.
- [ ] DLQ, bounded redelivery, replay runbooks, and owners exist.
- [ ] Tested broker outages, listener crashes, consumer scaling, and business ordering.
- [ ] Alerts track ready/unacked, consumer lag/age, connections, and session failures.

## 14. AMQP/RabbitMQ: Prefetch, Consumers, and Unacked Inflight

With RabbitMQ, prefetch and consumer count jointly determine how many messages can be delivered yet unacknowledged. A simple upper-bound estimate when prefetch applies per consumer:

\[
M_{\mathrm{unacked,upper}} \approx N_{\mathrm{consumers}}\times P_{\mathrm{prefetch}},
\]

assuming **prefetch count is enforced per consumer** in that topology. Exact global vs. per-consumer prefetch behavior must be checked against your RabbitMQ/Spring AMQP version.

For example, 6 consumers × prefetch 20 can hold up to ~**120 unacked messages**. With large payloads, memory pressure and wait times climb even with a small consumer thread pool.

### 14.1. Parameters to Review

- Concurrent consumer counts and max consumers if dynamic scaling is enabled;
- Prefetch count per queue/consumer and payload size;
- Acknowledgement mode (auto/manual per container);
- Broker QoS/consumer dispatch behavior;
- Broker connection/channel limits;
- Publisher connection pools and publisher confirms/returns;
- RabbitMQ queue depth, ready vs. unacked split, DLQ;
- Requeue/retry/delayed-message behavior on consumer failures.

### 14.2. AMQP Checklist

- [ ] Consumer and prefetch quotas account for totals across all replicas.
- [ ] Never optimize only ready queue depth while ignoring unacked counts.
- [ ] Never ack early just to inflate throughput metrics.
- [ ] Listener retry/error handlers never endlessly requeue poison messages.
- [ ] Consumers handle redeliveries and publisher duplicates idempotently.
- [ ] Outbound publishes are bounded with confirm tracking.
- [ ] Tested multi-replica scaling, broker flow control, queue overload, and delayed retries.
- [ ] Impact of scaling on per-key ordering is reviewed and accepted.
- [ ] Alerts monitor ready, unacked, consumer utilization, and message age.

### 14.3. Is Prefetch = 1 Always Best?

No. Very low prefetch limits unacked counts and can improve fairness, yet degrades throughput when network round-trips or overhead are high. Excessively high prefetch bloats inflight counts and memory, letting one consumer hoard messages. Find the sweet spot via **load tests with realistic payloads, handler durations, and ack semantics**.

## 15. Kafka: Partitions Govern Useful Concurrency

Kafka consumer groups assign partitions to consumers. For a topic with **P partitions**, having more consumers in the same group than P generally adds no parallel partition processing for that topic, since each partition goes to at most one consumer in the group at a time.

### 15.1. Core Rules

- Ordering holds **within a partition** in log order—not globally across the topic.
- If a business key requires ordering, producers must partition consistently by that key.
- Raising listener concurrency above partition count will not increase throughput in simple assignments.
- Slow record processing can trigger `max.poll.interval.ms` violations or rebalances.
- Processing multiple records asynchronously within one partition can break ordering/offset safety unless acks are coordinated.
- Retries/DLTs shift partition progress; define poison-record and version-gating policies.

### 15.2. Kafka Producers Also Have Limits

Kafka producers maintain buffers, batches, in-flight requests, retries, and delivery timeouts. Simply raising `ExecutorChannel` concurrency will not linearly multiply broker connections or throughput. Producers may be constrained by:

- Partition counts and broker throughput;
- Client `buffer.memory`, `batch.size`, `linger.ms`, and `max.block.ms`;
- Record sizes, compression, and serialization;
- `max.in.flight.requests.per.connection` and client retry/ordering semantics;
- Broker quotas, network bandwidth, `acks`, and replication;
- Callback handling and outbox backlog.

### 15.3. Partition/Consumer Examples

| Setup | Partitions | Consumers in Group | Notes |
|---|---:|---:|---|
| A | 6 | 1 | One consumer handles multiple partitions |
| B | 6 | 3 | Partitions distributed across 3 consumers |
| C | 6 | 6 | Max 6 active consumers in simple single-topic case |
| D | 6 | 12 | Extra consumers sit idle in the group |
| E | 24 | 12 | More parallelism possible, but evaluate load/broker/key skew |

This simplifies a single topic and group; do not apply mechanically to multi-topic subscriptions or complex assignment strategies.

### 15.4. Kafka Checklist

- [ ] Listener concurrency aligns with partition counts and actual load.
- [ ] Producer keys satisfy business ordering requirements.
- [ ] Consumer lag is tracked per partition to catch hot partitions.
- [ ] Batch/poll processing times fit within `max.poll.interval.ms`.
- [ ] If listeners process asynchronously, offsets/acks never advance past durably completed records.
- [ ] Retry/DLT policies enforce ordering and idempotency.
- [ ] Producer buffer/batching/inflight/retry settings match Kafka client version.
- [ ] Metrics cover lag, rebalances, bytes in/out, publish latency, errors, and outbox age.
- [ ] Tested consumer scale-in/out, broker failovers, poison records, and commit ambiguity.
- [ ] Never add consumers blindly to "boost throughput" when the DB or HTTP is the bottleneck.

## 16. JDBC: HikariCP Max Pool Size Does Not Solve Contention

JDBC inbound/outbound adapters share a `DataSource`/connection pool across the application. In many Spring Boot projects, `HikariCP` is common; inspect the actual config and total processes hitting the database.

### 16.1. Connection Pool Budget

| Property | Meaning | Common Mistake |
|---|---|---|
| `maximumPoolSize` | Max connections in the pool | Setting 100 per pod when DB allows 100 total |
| `minimumIdle` | Minimum idle connections when configured | Confusing with max active workload |
| `connectionTimeout` | Wait to borrow a connection from pool | Confusing with query timeout |
| `validationTimeout` | Wait to verify connection health | Confusing with transaction timeout |
| `idleTimeout` | Idle connection lifetime per pool semantics | Trying to kill hung queries with it |
| `maxLifetime` | Lifetime cap for pooled connections | Confusing with per-SQL duration limit |
| Leak detection threshold | Detects abnormally held connections | Treating as a substitute for proper closing/transactions |

### 16.2. Spring Boot Hikari Property Example

~~~yaml
# Spring Boot + HikariCP example; cross-check against version and DB quota.
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 2000
      validation-timeout: 1000
      max-lifetime: 1800000
~~~

These numbers are **illustrative**; several Hikari properties above use **milliseconds**. Do not copy as universal optimal settings. `maxLifetime` must coordinate with DB/proxy/network timeouts and be verified with your vendor.

### 16.3. Keep Connections Held as Briefly as Possible

**Bottleneck-prone design:**

~~~text
BEGIN DB transaction
 -> SELECT/UPDATE order
 -> call partner HTTP for 8 s (holds DB connection + lock)
 -> publish Kafka
 -> COMMIT
~~~

If HTTP slows down, the entire DB pool can be pinned, causing lock contention and timeouts.

**Design to consider:**

~~~text
BEGIN DB transaction
 -> validate/UPDATE order
 -> INSERT outbox event
COMMIT

Outbox worker -> HTTP/Kafka with independent retry and idempotency
~~~

Business consistency requirements do not always allow splitting like this; however, if long transactions are used, prove timeouts, locks, retries, pool capacity, and deadlock behavior.

### 16.4. Multi-Worker JDBC Inbound Polling

If multiple pollers run `SELECT ... WHERE status='NEW'` and process outside transactions, the same row can be picked multiple times. Enforce:

- Dialect-appropriate row claiming/locking;
- `lease_owner` and `leaseUntil` for crash recovery;
- Unique processing keys / idempotent business mutations;
- Batch limits and max in-progress row caps;
- Expired-lease reclaiming without letting two workers execute concurrent side effects lacking fencing;
- Proper indexes/SQL plans and bounded lock durations;
- Metrics for NEW/PROCESSING/FAILED row ages.

~~~sql
-- Pseudo-SQL: locking and row-limit syntax depend on DB engine.
BEGIN TRANSACTION;

SELECT id
FROM integration_inbox
WHERE status = 'NEW'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED;

-- Limit batch size per SQL dialect.
-- UPDATE claimed IDs -> PROCESSING with lease owner/version.

COMMIT;
~~~

`SKIP LOCKED` behaves differently across databases, and claiming alone does not replace idempotency. Test the failure window where a worker's lease expires while its remote HTTP call is still running.

### 16.5. JDBC Checklist

- [ ] Total `maxPoolSize` accounts for max replicas, rolling deploys, and shared apps.
- [ ] Pool acquisition timeout is shorter than operation deadlines.
- [ ] Query/lock/transaction timeouts, indexes, and batch sizes are tested on production-like data.
- [ ] Pools shared between web requests and integration jobs are properly partitioned or split if needed.
- [ ] Never hold connections across slow remote I/O unnecessarily.
- [ ] Multi-poller flows enforce claims/leases and idempotency.
- [ ] Metrics cover active/idle/pending/wait, slow SQL, and deadlocks/lock waits.
- [ ] Tested DB failovers, pool saturation, connection leaks, and crashes mid-commit/ack.

## 17. Multi-Stage Flows: Size to the Bottleneck and Overlapping Resources

### 17.1. Case Topology

~~~mermaid
flowchart LR
    S["SFTP 4 transfers"] --> F["File parse 8 workers"]
    F --> D["JDBC pool 12/pod"]
    D --> Q["Outbox persistent queue"]
    Q --> K["Kafka publisher bounded"]
    Q --> H["HTTP partner bulkhead 10"]
    H --> R["Partner API"]
    D --> DB["Database"]
~~~

These are simulated numbers **for one pod**, not blanket recommendations. Validate against the full cluster and real arrival rates.

### 17.2. Avoid Holding Two Expensive Resources Simultaneously

If a handler holds a JDBC connection while awaiting an HTTP response, one request ties up **both pools** for an extended period. Under rising load:

- DB pool exhausts even if SQL queries are fast;
- HTTP pool pending counts spike;
- Worker threads stall on pool acquisition;
- Retries surge and pin even more resources;
- Outbound events delay or drop without durable boundaries.

Separating transactions from remote I/O via outboxes or checkpointed workflows reduces DB connection hold times, while raising requirements for idempotency, ordering, and reconciliation.

### 17.3. Multi-Replica Budgets

Suppose a design runs 5 pods, each configured with:

| Resource | Limit/Pod | Theoretical 5-Pod Total |
|---|---:|---:|
| SFTP transfers | 2 | 10 |
| File parse workers | 8 | 40 |
| JDBC connections | 10 | 50 |
| HTTP concurrent partner A | 6 | 30 |
| Kafka consumer concurrency | 3 | 15 consumer threads |

Totals only materialize when every pod runs at capacity; for Kafka, consumer threads exceeding partition counts add no parallel partition reads. For cluster-wide SFTP/HTTP quotas, include peak autoscaling and rolling-deployment surges.

### 17.4. Avoid Unbounded Buffering Between Stages

A fast parsing stage can emit 1,000 messages/s while the HTTP stage completes only 50 requests/s. Buffering messages in memory causes:

- Queues hitting capacity;
- Large payloads spiking heap/GC pressure;
- Shutdown leaving many non-durable messages behind;
- End-to-end latency soaring despite fast parsing.

Enforce bounded queues, durable persistence, ingress throttling, or routing so backlogs live in systems that can **persist, monitor, and replay** them safely.

## 18. How Concurrency Impacts Transactions, Acks, Ordering, and Idempotency

### 18.1. More Threads Widen Failure Windows

With synchronous processing:

~~~text
poller -> handler -> DB commit -> ack source
~~~

With `ExecutorChannel`:

~~~text
poller -> enqueue async task -> poller continues
                               worker -> DB commit -> ack?
~~~

If the poller treats queuing into the executor as source completion while the task sits only in memory, a pod crash drops messages. Specify **who acks the source and when**; never assume a poller's transaction spans another worker thread.

### 18.2. At-Least-Once Remains the Baseline

Scenarios such as:

- Consumer commits DB then crashes before Kafka offset commit;
- JMS/AMQP handler commits DB then loses connection before broker ack;
- SFTP file downloads successfully while business commit fails;
- HTTP POST succeeds at partner while client loses response;

all lead to retries/redeliveries. Enforce business idempotency keys and side-effect reconciliation—never claim end-to-end exactly-once simply by adding locks or a single pool.

### 18.3. Ordering Under Parallelism

- Kafka preserves order within a partition; dispatching same-key records to multiple async tasks can finish out of order unless coordinated.
- JMS/AMQP delivery/completion order can invert across concurrent consumers and redeliveries.
- File/SFTP pollers sorting by name/date do not inherently guarantee business ordering.
- JDBC queries without `ORDER BY` have unstable result ordering.
- If workflows require revision 1→2→3 ordering, partition by key, check versions, or serialize per key.

### 18.4. Locks Do Not Protect Every Side Effect

Distributed locks or DB leases reduce concurrent claims by two workers, yet:

- A lease may expire while the original worker is still calling HTTP.
- Another worker claims the item, causing **concurrent side effects**.
- Redis/DB locks can lapse during network partitions.
- Delayed callbacks/retries can still land after locks release.

For high-risk actions, pair locks with **fencing tokens/version checks, idempotency keys, and target-state verification** rather than relying solely on mutexes.

### 18.5. Correctness Checklist When Raising Concurrency

- [ ] Source ack/commit and durable handoff boundaries are clear.
- [ ] Idempotency holds when two workers process the same business key simultaneously.
- [ ] Transaction scopes never cross thread boundaries unintentionally.
- [ ] Unique constraints or state machines guard side effects.
- [ ] Per-key/tenant ordering is preserved or out-of-order handling is enforced.
- [ ] Retry/backoff does not expand inflight counts unboundedly.
- [ ] Leases/claims recover after crashes and fence stale workers where needed.
- [ ] DLQ/replays do not create duplicates after system recovery.

## 19. Autoscaling, Rolling Deployments, and Connection Lifecycles

### 19.1. Horizontal Scaling Multiplies Downstream Load

Adding pods can increase:

- File/SFTP/JDBC polling scan rates;
- Open sessions/connections on SFTP/DB/HTTP;
- Consumer group members, rebalances, and redeliveries;
- Concurrent requests to partner APIs;
- Retry volume during dependency errors;
- Disk and message broker I/O pressure.

**CPU-based HPA alone is insufficient** to infer downstream capacity. An I/O-bound service can show low CPU while DB/HTTP pools are heavily queued. Scale on meaningful signals: lag, backlog age, busy workers, queue depth, throughput, and external capacity.

### 19.2. Rolling Deployments Temporarily Increase Replicas

A Deployment targeting 5 pods can run old + new pods concurrently during rolling updates per `maxSurge`/`maxUnavailable`. If each pod has a DB pool of 12, theoretical connections exceed 60 during transition. Size against **peak concurrent replicas**, not just desired replicas.

Checklist:

- [ ] Document max replicas across autoscaling and rolling deploys.
- [ ] Sum of `maximumPoolSize` stays within DB/partner quotas after headroom.
- [ ] Pollers do not double-process files/rows while old pods drain.
- [ ] Kafka group rebalances are tested under scale-in/out.
- [ ] JMS/AMQP consumers, prefetch, and unacked counts are monitored during rollouts.
- [ ] Ingress/consumers stop in order, draining inflight work or recovering per contract.
- [ ] Secret/connection rotation avoids reconnect storms.
- [ ] Scaling down never drops messages queued only in memory.

### 19.3. Graceful Shutdown Is Not Magic

At shutdown time, a worker may be:

- Holding a JDBC connection inside a transaction;
- Downloading an SFTP file into a local temp file;
- Waiting on a partner HTTP call that already committed;
- Awaiting a Kafka publisher callback;
- Holding an unacked JMS/AMQP message.

On `SIGTERM`, stop accepting new work, allow a bounded grace period, and rely on recovery after exit. Never let operations run unboundedly trying to "lose zero messages"; combine bounded timeouts, durable checkpoints, and idempotency.

### 19.4. Real Kill Scenario

1. Start a load test with unique business IDs.
2. With ~50 inflight messages active, kill one replica.
3. Confirm the source redelivers/reclaims incomplete work.
4. Confirm surviving workers do not duplicate business side effects.
5. Reconcile DB, files, Kafka/JMS/AMQP, and remote HTTP state.
6. Measure backlog drain, reconnect rates, and post-failover errors.
7. Verify threads/connections on surviving instances do not leak upward.

## 20. Observability: Catch Saturation Before Losing Data

### 20.1. Critical Metrics

| Layer | Metrics to Track | Signal |
|---|---|---|
| Inbound File | Pending files, oldest age, scan duration, active files | Slow scans, stuck files |
| SFTP | Active sessions, wait/acquire time, transfer duration, remote failures | Session pool exhaustion |
| HTTP client | Leased/idle/pending connections, request latency, 429/503 | Pool starvation / quota |
| HTTP server | Active requests, request queue, rejects/429/503, p95/p99 | Ingress overload |
| TaskExecutor | Active threads, pool size, queue depth, rejected tasks | Bounded queue full |
| TaskScheduler | Poll task duration, schedule delay, missed/overlapping polls | Scheduler saturation |
| QueueChannel | Depth, oldest age, enqueue/dequeue rates, send timeouts | Growing backlog |
| JMS | Consumers, ready/dispatched/unacked, redeliveries, DLQ age | Prefetch/load skew |
| AMQP | Ready/unacked, consumers, prefetch, publish/ack rates, DLQ | High unacked |
| Kafka | Consumer lag per partition, rebalances, publish latency/errors | Hot partition, slow broker |
| JDBC/Hikari | Active, idle, pending, acquisition wait, query/lock duration | Pool/DB saturation |
| End-to-end | Business completion rate, latency, duplicate no-op count | Technical vs business success gap |

Actual metric names depend on stack, version, and Micrometer/Actuator/connector setup. Never assume adding a dependency automatically emits full telemetry. Verify every chart and alert fires properly.

### 20.2. Diagnostic Ratios

**Utilization** roughly compares active resources to configured capacity at a point in time. However:

- 100% CPU during CPU-bound batching may be healthy if latency meets SLO.
- 100% active DB pool alongside rising pending counts and timeouts signals distress.
- Queue depth = 0 can mean **zero incoming data** or **consumers holding unacked messages**; inspect ingress, unacked counts, and business completions together.
- Adding consumers without throughput gains points to another bottleneck or idle consumers.
- Retries inflate **effective** downstream arrival rates above new business message rates.

### 20.3. Structured Logs and Traces

| Field | Purpose |
|---|---|
| `correlationId`, `businessId` | Follow one message across adapters |
| `sourceEndpoint`, `targetEndpoint` | Isolate bottlenecks |
| `flowStep`, `threadName`, `podId` | Distinguish threads and pods |
| `poolName`, `acquisitionWaitMs` | Separate pool waiting from slow remote responses |
| `queueAgeMs`, `serviceTimeMs` | Separate queuing delay from processing time |
| `attempt`, `retryBackoffMs` | Quantify retry load |
| `sourceAckState`, `outcome` | Investigate redeliveries and partial failures |
| `messageSchemaVersion` | Diagnose contract issues |
| `concurrencyLimit`, `currentInflight` | Explain rejections or pauses |

Never put high-cardinality `businessId`/`userId` into metric tags; keep them in access-controlled logs and traces. Never log credentials, raw tokens, or unnecessary PII.

### 20.4. Sample Alerts with Runbooks

- Rising pool acquisition p95 paired with sustained `pending > 0`.
- Active workers near max while queue age climbs.
- SFTP oldest ready file breaches SLO.
- Kafka per-partition lag grows while consumer count stays flat.
- AMQP/JMS unacked count rises while completion rate falls.
- Partner HTTP 429s spike as concurrency nears quota.
- Database lock waits/deadlocks rise after scaling workers.
- Task rejections risk losing already-acked messages.
- Outbox/retry queue spikes or event age exceeds SLA.
- Graceful shutdown repeatedly hits grace-period timeout with high inflight.

Every alert needs severity, owner, dashboard link, and remediation steps. Avoid naive alerts like "CPU > 80%" disconnected from queues, latencies, and business throughput.

## 21. Load Testing and Fault-Injection Matrix

Running a benchmark of "100 happy-path messages" is insufficient. Tests must provoke **saturation, slow downstreams, retries, and crashes** at every layer.

### 21.1. Building the Test Suite

1. Generate inputs with stable business IDs and varied payload sizes.
2. Measure baselines with one instance, one consumer, and low concurrency.
3. Step up arrival rates while recording throughput, queue waits, service times, and utilization.
4. Artificially slow HTTP/SFTP/DB/broker dependencies in a controlled way.
5. Scale replicas and verify total quotas, duplicate claims, and ordering.
6. Push to saturation/rejection/backpressure and verify message durability.
7. Kill processes mid-commit and mid-ack.
8. Measure backlog drain times and error/unknown-outcome counts.
9. Reconcile actual target business records—not just received message counts.
10. Run soak tests long enough to catch connection/thread leaks and GC/memory drift.

### 21.2. 60-Case Test Suite

| ID | Scenario | Expected Outcome |
|---|---|---|
| **T01** | `DirectChannel` handler slows down | Clean upstream backpressure; zero message loss |
| **T02** | Bounded `ExecutorChannel` queue fills up | Rejections handled cleanly; source not falsely acked |
| **T03** | Pod dies with in-memory `QueueChannel` | Explicit recovery contract; not falsely assumed durable |
| **T04** | Persistent `MessageStore` with proper transaction | Messages recover cleanly per contract |
| **T05** | `CallerRunsPolicy` when executor is full | Does not break SLAs, threads, acks, or transactions |
| **T06** | `AbortPolicy` when executor is full | Error routing/retry triggers; no silent drops |
| **T07** | Two workload types share an executor | Critical workload protected from policy-violating starvation |
| **T08** | Small `TaskScheduler` with multiple slow pollers | Schedule delays metered; zero lost sources |
| **T09** | Poller `maxMessagesPerPoll` raised from 5 to 100 | Bounded downstream stays safe |
| **T10** | Poller paused for 10 minutes | Durable backlog persists and drains smoothly |
| **T11** | Replicas scaled 1→5 | Total capacity/quotas never exceeded |
| **T12** | Rolling deploy with old and new pods | Total pool connections stay within budget |
| **T13** | Autoscaler adds pods while downstream is overloaded | Does not worsen overload or trigger retry storms |
| **T14** | CPU-bound parsing shares I/O executor | Test catches starvation and validates pool separation |
| **T15** | HTTP client pool runs out of connections | Pool acquisition timeout, bulkhead, and alerts engage |
| **T16** | Slow HTTP responses pin connections | Pending/latency rise cleanly without OOM |
| **T17** | HTTP/2 multiplexed connections | Sizing reflects actual streams/requests |
| **T18** | API quota: 20 inflight, 100 calls/s | Both concurrency and rate limits enforced |
| **T19** | API returns sustained 429/503 | Jittered retries and circuit/rate limiters engage |
| **T20** | HTTP POST times out after remote commit | Idempotency/reconciliation prevents duplicates |
| **T21** | HTTP inbound flood | Concurrent request caps and proper status responses |
| **T22** | SFTP session cache exhausted | Bounded acquisition wait; clear throughput/alerts |
| **T23** | SFTP server caps at 8 transfers | Cluster stays under quota |
| **T24** | Dead SFTP session remains in cache | Invalidated/reconnected cleanly without leaks |
| **T25** | SFTP network stall mid-download | Session/worker recovers or isolates safely |
| **T26** | Multiple pods scan same remote directory | Distributed claims + idempotency protect files |
| **T27** | Ten workers pick up 1 GB files | RAM/disk/FD usage stays bounded |
| **T28** | File mid-upload | Processed only after ready protocol completes |
| **T29** | File business commit succeeds, archive fails | No second business record created |
| **T30** | NFS shared volume disconnects | No silent drops; recovery/runbook executes |
| **T31** | JMS consumer concurrency increased | Throughput/ordering match contract; no session leaks |
| **T32** | JMS prefetch too large | Dispatched/unacked tracked; fairness tuned |
| **T33** | JMS broker redelivery after crash | Idempotent consumer preserves business correctness |
| **T34** | JMS handler retries overlap broker retries | Attempts stay bounded; no storm |
| **T35** | JMS queue receives poison record | Routed to DLQ/recovery without blocking queue forever |
| **T36** | AMQP consumers × prefetch increased sharply | Unacked/memory stay bounded |
| **T37** | Process dies before AMQP ack sent | Redelivery does not duplicate side effects |
| **T38** | AMQP publisher confirm lost | Idempotent retry; consumer deduplicates |
| **T39** | AMQP ready count low while unacked very high | Dashboards do not misreport empty queue |
| **T40** | AMQP delayed retries grow backlog | DLQ/age alerts and quotas active |
| **T41** | Kafka 6 partitions, 12 consumer threads | Idle consumers observed; no false throughput promises |
| **T42** | Kafka hot partition | Key skew and business ordering analyzed |
| **T43** | Kafka consumer exceeds poll interval | Rebalances/`max.poll.interval` handled cleanly |
| **T44** | Kafka async handlers finish out of order | Offsets/acks advance only along safe policy |
| **T45** | Kafka poison record routed to DLT | Business ordering/version gating respected |
| **T46** | Kafka producer buffer exhausted | Backpressure/`max.block`/delivery failures controlled |
| **T47** | Total JDBC max pools exceed DB quota | Test catches breach and reduces pools/replicas |
| **T48** | 100 JDBC workers contend for 10 connections | Pending/acquisition waits alert without hanging |
| **T49** | JDBC transaction holds lock during HTTP call | Load test exposes pool/lock starvation |
| **T50** | Two JDBC pollers claim same row | Only one claim succeeds per design |
| **T51** | JDBC lease expires while old worker still runs | Fencing/idempotency blocks double effects |
| **T52** | JDBC deadlocks under higher concurrency | Bounded transaction retries; zero duplicates |
| **T53** | DB failover with active pool | Connection recovery and error routing succeed |
| **T54** | Outbox worker concurrency raised | Retries stay safe against downstream idempotency |
| **T55** | Per-tenant quotas while one tenant floods | Other tenants retain approved service levels |
| **T56** | Circuit breaker opens while source keeps sending | Ingress throttles/buffers durably without loss |
| **T57** | Retry storm as dependency recovers | Jitter/limiters shield downstream |
| **T58** | SIGTERM mid-transfer / DB commit / ack | Graceful shutdown or safe replay |
| **T59** | Extended soak test with intermittent faults | Zero thread/session/connection leaks |
| **T60** | Rollback after partial backlog processing | Reconciliation avoids duplicates or lost effects |

Every case requires **environment/version, test payload and business key, concurrency/pool/replica settings, expected vs. actual results, metrics/logs/correlation, actual business state, tester, and PASS/FAIL verdict**. A "message sent successfully" log does not prove zero duplicates or zero data loss.

### 21.3. Defining the Saturation Point

Saturation occurs where raising input load stops yielding sustainable throughput gains while latency, queue depth, pending acquisitions, or error rates climb. Identify the **knee point** on throughput–latency curves and operate with headroom rather than running continuously at saturation.

## 22. Runbook When Connection Pools or Workers Exhaust

### 22.1. 10-Step Procedure

1. **Locate bottleneck:** HTTP pool, HikariCP, SFTP sessions, JMS consumers, Kafka partitions, or executor?
2. **Check ingress rate:** New traffic surge, batch replay, or retry storm?
3. **Check pending state:** Queue depth/age, pool acquisition waits, and active task counts?
4. **Check downstream latency:** Query/lock times, HTTP p95/p99, remote transfers, broker acks?
5. **Check hot keys/tenants:** Is one tenant/partition/huge file pinning workers?
6. **Check retries and errors:** 429/503, timeouts, deadlocks, broker redeliveries, poison messages?
7. **Check quotas:** Does cluster-wide max connections exceed DB/partner capacity?
8. **Shed load cleanly:** Pause pollers, rate-limit, enforce bulkheads, lower concurrency, or trip circuit breakers.
9. **Reconcile side effects:** Which messages acked/committed, and could retries duplicate work?
10. **Recover and review:** Drain backlog, fix sizing/code, save evidence, and update runbooks.

### 22.2. Symptom-Based Response Table

| Symptom | Do Not Do | Recommended Action |
|---|---|---|
| High Hikari pending | Blindly raise pools on every pod ignoring DB quota | Find slow SQL/locks, cut inflight, reallocate quota |
| High HTTP pool pending | Only increase connect timeout | Measure partner latency/rate limits, bulkheads, and queues |
| Mass SFTP session errors | Disable host-key verification or hammer reconnects | Check server/certs/quotas; bounded jittered retries |
| Long executor queues | Switch to unbounded queues | Throttle source, buffer durably, and resize |
| High Kafka lag | Scale consumers past partition counts | Investigate hot partitions and DB/HTTP bottlenecks |
| High AMQP unacked | Ack early to clear metrics | Lower prefetch/concurrency; fix handler latency |
| Slow JMS consumers | Drop idempotency for speed | Optimize downstream; tune prefetch/consumers |
| Files repeatedly re-scanned | Arbitrarily delete files/metadata | Inspect claims/filters and business state |
| Retries inflating load | Raise attempts endlessly | Add jitter, circuit breakers, deferred retries |
| Very long DB transactions | Set infinite timeouts | Shorten transactions; decouple external I/O cleanly |

### 22.3. Pausing and Resuming Safely

- Identify endpoint ID and owner for the poller/listener.
- Halt or throttle new intake without corrupting broker acks.
- Preserve durable backlogs; never delete pending items.
- Wait a bounded window for inflight work or let crash recovery handle it.
- Verify side effects before replaying.
- Once dependencies recover, resume **gradually** while watching pending waits and error rates.
- Attach expiry dates and audit records to temporary limit overrides.
- Close the incident only after business completion and backlog age return to approved thresholds.

## 23. Case Study: SFTP → JDBC/Outbox → Kafka and Logistics HTTP

A system pulls partner order CSVs from SFTP, processes and persists them to DB, emits Kafka events via outbox, and calls logistics HTTP in another worker. Target peak is 100 orders/s, running up to 4 replicas normally and scaling to 8.

### 23.1. Faulty Initial Configuration

- Each pod has a 64-thread executor with an unbounded queue.
- SFTP poller runs every 1 second with no distributed claims.
- Each pod opens up to 20 SFTP transfers while the remote allows 30 across the whole tenant.
- Hikari `maximumPoolSize=30` per pod while the database allocates ~80 connections to the app.
- Logistics HTTP partner allows at most 25 concurrent requests, with no rate limiter.
- Some JDBC transactions hold connections open across HTTP calls.
- Kafka topic has 6 partitions yet 8 replicas × 4 consumer threads.
- Aggressive retries enabled across client, advice, and broker simultaneously.

With just 4 pods running, JDBC pools can demand **120 connections**, SFTP can open **80 transfers**, and HTTP can blast far past the 25-request quota. Scaling to 8 pods makes theoretical limits even worse.

### 23.2. Redesign Plan

1. **Lock down real quotas:** Confirm limits with owners of DB, SFTP server, HTTP partner, and Kafka broker.
2. **Capture baselines:** Measure arrival rates, p95 processing times, Hikari active/pending, HTTP 429/503, SFTP transfer durations, and Kafka lag.
3. **Split transactions:** Keep DB transactions short to save order + outbox; run logistics HTTP in a dedicated idempotent worker.
4. **Configure bounded executors:** e.g., 8 core, 12 max, queue 32 for partner I/O, handling rejections via durable recovery.
5. **Cap DB:** Budget total pools across peak replicas, reserving headroom for migrations/ops and peer apps.
6. **Cap SFTP:** Keep cluster-wide transfers under quota with distributed claims.
7. **Cap HTTP:** Enforce cluster-wide max 25 inflight to partner plus contractual calls/s quotas.
8. **Kafka consumers:** Size to partitions, key skew, and downstream DB capacity—not wasted extra threads.
9. **Separate retry owners:** Jittered backoff on SFTP/HTTP errors; brief DB deadlock retries; Kafka outbox uses status ledger + idempotent consumers.
10. **Protect business integrity:** Unique business IDs, side-effect reconciliation, error flows/quarantine.

### 23.3. Illustrative Budget Table After Redesign

| Resource | Hypothetical Cluster Quota | Option to Validate |
|---|---|---|
| SFTP transfers | 30 | Cap below quota, accounting for rolling pods |
| App JDBC connections | 80 | Sum of max pools up to 8 pods + headroom ≤ 80 |
| Logistics HTTP concurrency | 25 | Distributed limiter or per-pod split with HPA cap |
| Kafka partitions | 6 | Useful active consumers matched to partitions/bottleneck |
| File parsing | CPU/memory-bound | Bounded worker queues, file size limits |
| Outbox queue | DB/storage/retention-bound | Durable pending storage, age alerts, retry capacity |

No "magic numbers" like 8 threads or 12 connections fit every workload. Final figures come from load-testing the actual flow.

### 23.4. Failure Drills

**Drill A — Logistics HTTP slows down 5x:** Bulkhead caps inflight at 25, backlog sits in durable queue, DB transactions stay short, zero OOM.

**Drill B — SFTP server rejects over-quota sessions:** Pollers throttle concurrent transfers and back off; zero reconnect storms; pending files remain intact.

**Drill C — Kill one pod between DB commit and Kafka publish:** Outbox replays safely without duplicating orders.

**Drill D — Autoscale to 8 pods:** Total DB/SFTP/HTTP quotas stay respected, including rolling-deploy surges.

**Drill E — Kafka consumer rebalance:** Per-key ordering managed cleanly; offsets never commit before durable business success.

### 23.5. Acceptance Criteria

- Meets business throughput/SLOs with approved headroom.
- Zero lost messages or duplicate side effects in failure drills.
- Never exceeds downstream connection/concurrency quotas.
- Queue/backlog ages are metered and drainable.
- Queues, workers, and session pools are all bounded.
- Restarts/rolling deploys/scale-outs neither drop nor duplicate files/records.
- Retries avoid storms during dependency recovery.
- Owners, on-call, runbooks, dashboards, and go-live approvals are signed off.

## 24. Pre-Go-Live Capacity Review Form Template

This is an **illustrative YAML review artifact**, not a config format recognized by Spring Integration/Spring Boot. Teams must implement/bind, measure, and populate real evidence.

~~~yaml
flow: supplier-orders
owners:
  business: order-operations
  technical: integration-platform
  onCall: platform-operations

topology:
  minReplicas: 2
  desiredReplicas: 4
  maxReplicasIncludingRollingSurge: 8

ingress:
  adapter: sftp-inbound
  pollInterval: 5s
  maxMessagesPerPoll: 10
  distributedClaim: required
  sourceDurableBeforeAck: true

executors:
  partnerHttpIo:
    corePoolSize: 8
    maxPoolSize: 12
    queueCapacity: 32
    rejectionPolicy: fail-to-durable-retry
    shutdownGrace: 30s

connectionBudgets:
  sftp:
    maxClusterTransfers: REVIEW_WITH_PARTNER
    maxPerReplica: REVIEW_REQUIRED
    acquisitionTimeout: REVIEW_REQUIRED
  jdbc:
    maxClusterConnectionsForApp: REVIEW_WITH_DBA
    maxPerReplica: REVIEW_REQUIRED
    acquisitionTimeout: 2s
  httpPartner:
    maxClusterInflight: 25
    maxRequestsPerSecond: REVIEW_WITH_PARTNER
    limiterScope: cluster

kafka:
  partitions: 6
  consumerGroup: supplier-orders-v1
  listenerConcurrencyPerReplica: REVIEW_REQUIRED
  orderingKey: orderId

reliability:
  stableBusinessId: source-orderId-revision
  businessIdempotency: unique-constraint
  outbox: required
  durableBackpressure: required
  errorRecovery: DLQ-and-replay

observability:
  poolActiveIdlePending: required
  executorQueueAndRejection: required
  backlogAgeAndLag: required
  businessCompletionLatency: required

testing:
  saturationTestsPassed: PENDING
  failureDrillsPassed: PENDING
  rollingScaleTestPassed: PENDING

approval:
  businessOwner: PENDING
  databaseOwner: PENDING
  security: PENDING
  operations: PENDING
~~~

### 24.1. Review Rules

- Every per-pod value must be multiplied out to **peak replicas + rolling surge** and checked against partner quotas.
- Set limits only after measuring actual load and dependency capacities.
- Resolve all `REVIEW_REQUIRED`, `REVIEW_WITH_...`, and `PENDING` items before approving deployment.
- A `rejectionPolicy` entry in the form is only a logical intent; real code paths must ensure zero message loss.
- Never approve "GO" just because `maximumPoolSize` or `maxThreads` is set to a positive number.

## 25. Go/No-Go Checklist

### Before Production

- [ ] Flow diagram covers `MessageChannel`, pollers, listeners, and outbound adapters.
- [ ] Measured peak arrival rates, p50/p95/p99 service times, and bottlenecks.
- [ ] Thread/queue/connection/broker-consumer budget table built per dependency.
- [ ] Cluster budgets include max replicas and rolling-deploy surges.
- [ ] Executor queues are bounded with recovery paths on rejection.
- [ ] Pool acquisition timeouts, max sizes, and lifecycles reviewed.
- [ ] Backpressure/limiters/bulkheads protect slow downstreams and per-tenant quotas if needed.
- [ ] Pollers enforce batch caps and multi-replica claims for File/SFTP/JDBC.
- [ ] JMS/AMQP concurrency, prefetch/acks, and Kafka partitions/offsets tested.
- [ ] Idempotency, transaction boundaries, DLQs, and replays cover redeliveries/retries.
- [ ] Metrics cover active/idle/pending, queue depth/age, retries, and business completions.
- [ ] Load, soak, outage, scale-out, crash, and rollback drills passed.
- [ ] Owners, alerts, runbooks, and on-call handoffs completed.

### During Rolling Rollout

- [ ] Deploy canary / lower initial inflight; verify metrics report accurately.
- [ ] Ramp traffic/batches/concurrency gradually while watching latency and saturation.
- [ ] Keep total pool connections under quota while old and new pods overlap.
- [ ] Watch queue age, redelivery/duplicate rates, DB locks, and HTTP 429/503s.
- [ ] Retain ability to pause intake safely while sources buffer durably.
- [ ] Exceptions carry owners, expiration dates, and mitigations.
- [ ] Scale up only after business correctness and throughput meet targets.

### Decision

| Status | Criteria |
|---|---|
| **GO** | Tests prove safety, throughput/SLOs met, quotas respected, recovery backed by evidence |
| **GO WITH EXCEPTION** | Minor exception with owner, expiration, mitigation, and formal signoff |
| **HOLD / RETEST** | Insufficient load data, untested multi-replica/connection leaks, or unclear source ack |
| **NO-GO** | Silent drops post-ack, pools exceeding quotas, duplicate side effects, missing backpressure/recovery, or security risks |

## 26. Common Anti-Patterns

**"More threads means faster processing."** When downstream is the bottleneck, more threads raise pool waits, memory usage, retries, and latency. Size to real service times and capacities.

**"Infinite queues prevent message loss."** Unbounded in-memory queues trigger OOMs and lose tasks on crashes. Use bounded queues and durable boundaries.

**"One pod works with pool 20, so 10 pods is fine too."** Total max connections jump to 200, potentially blowing DB quotas. Calculate using peak replicas plus rolling surges.

**"`DirectChannel` is inferior to `ExecutorChannel`."** Synchronous `DirectChannel` offers clear transaction/error propagation and natural backpressure; `ExecutorChannel` requires managing async boundaries, queues, and acks. Pick based on contract.

**"`ExecutorChannel` parallelizes transactions without changing semantics."** Thread boundaries stop upstream transactions from propagating to async handlers. Re-verify transactions and acks after changing channels.

**"`CallerRunsPolicy` is always good backpressure."** It can trap HTTP listener or poller threads inside slow handlers, breaching SLAs or altering transaction scopes. Test deliberately.

**"Raising Kafka consumer threads past partitions increases throughput."** Extra consumers sit idle; bottlenecks stay at partitions or downstream systems.

**"Large RabbitMQ prefetch is always better."** Inflates unacked counts and memory while hurting fairness. Load-test to find the right value.

**"JMS consumer = one TCP connection."** Providers manage sessions and connections differently. Check implementation docs.

**"Large SFTP session caches speed up downloads."** Remote quotas and bandwidth still constrain throughput; oversized caches cause connection storms.

**"Hikari `maxLifetime` is a query timeout."** It manages pooled connection lifecycles—it never aborts slow queries.

**"Setting only a rate limit is enough."** Rate limits don't cap concurrent waiting requests when remote latency spikes; pair with concurrency/bulkhead limits.

**"Holding a DB transaction across HTTP calls keeps everything consistent."** It does not create cross-system ACID transactions and holds connections/locks far too long. Use outboxes and orchestration.

**"File/row locking alone gives exactly-once."** Leases can expire and retries can repeat side effects. Enforce business idempotency and reconciliation.

**"Canary is one pod so it cannot breach quotas."** Consumer groups, pollers, and broker topologies may not route traffic proportionally; rolling surges also add connections.

**"Low active pool count means no bottleneck."** Workers may be blocked at another layer or messages haven't reached the pipeline; inspect ingress, queue depth, lag, and business completion together.

## 27. Self-Check Questions and References

### 27.1. Questions

1. How does concurrency differ from parallelism and throughput?
2. If arrival rate is 80 requests/s and average response time is 0.2 s, how many average inflight requests does Little's Law predict?
3. Why isn't Little's Law's average enough to pick `maximumPoolSize`?
4. If HTTP latency increases 5x while arrival rate stays flat, what happens to inflight demand?
5. How do `DirectChannel` and `ExecutorChannel` differ regarding threads and transactions?
6. Does an in-memory `QueueChannel` survive process restarts?
7. Why doesn't `maxMessagesPerPoll` guarantee downstream processes only that many messages concurrently?
8. Does `corePoolSize=8, maxPoolSize=16, queueCapacity=64` always spin up 16 threads for 16 tasks?
9. When an executor rejects a task, what condition prevents message loss?
10. How do rate limiting and concurrency limiting differ?
11. Why can HTTP/2 decouple connection count from inflight request count?
12. Why must SFTP session pools account for both server quotas and replica counts?
13. What happens when two File pollers read the same shared directory?
14. How can JMS prefetch affect fairness and memory?
15. In AMQP, why doesn't `ready=0` prove a queue has no backlog?
16. Does a 6-partition Kafka topic gain throughput from 12 consumers in one group?
17. Why can a Kafka hot partition remain a bottleneck despite a high total partition count?
18. How does Hikari `connectionTimeout` differ from `maximumPoolSize` and query timeouts?
19. Why must connection budgets include rolling deployments, not just desired replicas?
20. If a worker's DB lease expires while its HTTP side effect is still running, what protects you?
21. When a DB transaction holds a connection across an HTTP call, how can pool saturation cascade?
22. Which metrics reveal whether queues are growing due to source bursts vs. slow downstreams?
23. How can retry bursts elevate downstream request load even while new business throughput drops?
24. When should you pause a poller instead of enlarging an executor queue?
25. Which test proves scaling 1→5 pods introduces no duplicate files, rows, or broker records?

**Hint:** For every question, break down three scopes—**per-task → per-instance → cluster-wide**—and trace **threads/queues/connections → business side effects → source ack/commit**.

### 27.2. Glossary

| Term | Meaning |
|---|---|
| **Concurrency** | Operations actively in flight simultaneously |
| **Throughput** | Tasks completed per unit time |
| **Inflight** | Messages/requests not yet completed per contract |
| **TaskExecutor / TaskScheduler** | Task execution pool / periodic trigger scheduler |
| **MessageChannel** | Channel passing messages inside Spring Integration |
| **Bounded queue** | Queue with a finite capacity |
| **Rejection policy** | Behavior when an executor refuses a task |
| **Backpressure / bulkhead** | Throttling intake / isolating resources per dependency |
| **Rate limiter** | Request cap over a time window |
| **Pool acquisition** | Waiting to borrow a connection/session from a pool |
| **Prefetch** | Messages pushed early to a consumer prior to ack |
| **Consumer group / partition** | Kafka's mechanism for distributing records across consumers |
| **Idempotency** | Reprocessing without duplicating business side effects |
| **Outbox** | Persisting publish obligations inside the business DB transaction |
| **Lease / fencing token** | Time-bounded claim / mechanism blocking stale writers |
| **Little's Law** | Relationship: items in system = throughput × residence time |
| **Graceful shutdown** | Halting intake and draining/recovering inflight work cleanly |
| **Saturation** | Point where higher load raises latency/backlog without meaningful throughput gains |

### 27.3. Core Reference Documentation

When implementing for real systems, verify against **your exact version**:

- **Spring Integration Reference Guide:** Message Channels, Polling Consumer, Endpoint Lifecycle, File/SFTP/HTTP/JMS/AMQP/Kafka/JDBC adapters, Message Store, and Error Handling.
- **Spring Framework Reference:** `TaskExecutor`, `TaskScheduler`, `ThreadPoolTaskExecutor`, transaction management, messaging gateways.
- **Spring Boot Reference:** Configuration properties, Actuator, Micrometer, graceful shutdown, and DataSource pool settings.
- **Spring AMQP Reference / RabbitMQ Documentation:** Listener containers, concurrent consumers, prefetch, ack/requeue, publisher confirms, and broker quotas.
- **Spring for Apache Kafka Reference / Apache Kafka Documentation:** Consumer concurrency, partitions, offsets, producer settings, retries, and group rebalances.
- **JMS / Jakarta Messaging specification and provider documentation:** Session/connection pooling, acknowledgement, prefetch, transactions, redelivery.
- **HikariCP Configuration Guide and database vendor documentation:** Pool sizing, acquisition waits, connection lifecycles, SQL locks, and deadlocks.
- **Spring Integration SFTP / underlying SSH client documentation:** Cached sessions, connection/channel limits, host-key verification, and reconnects.
- **HTTP client documentation (Apache HttpClient / Reactor Netty / partner):** Max connections/streams, per-route pooling, timeouts, quotas, and HTTP/2 multiplexing.

**Conclusion:** Concurrency and connection pool configs are safe only when **every stage's capacity matches the end-to-end flow**, resources are bounded per instance and across the cluster, received messages have durable recovery under overload, and parallelism never breaks transactions, ordering, or idempotency. Base decisions on load measurements, downstream limits, backpressure, failure testing, and operational evidence—never guesswork.
