# Limitations of CRaC Regarding Durable Data and External Systems

CRaC (Coordinated Restore at Checkpoint) helps a Java application start quickly by creating a checkpoint of the process and then restoring the process from that checkpoint. This approach can preserve much of the state already prepared in the JVM, such as loaded classes, initialized objects, and data residing in the heap. However, an application rarely operates in isolation. It reads from and writes to databases, exchanges messages, calls APIs, holds network connections, uses files, and participates in multi-machine coordination mechanisms.

Those external systems continue operating on their own lifecycles. Databases still accept transactions, queues can still receive messages, tokens still expire, leases are still renewed or revoked, and files on disk can still change while the Java process is saved as a checkpoint. Therefore, restoring the JVM does not mean restoring the entire world the application interacts with.

To use CRaC safely, you must clearly identify which state belongs to the process, which state is durable data managed by other systems, and which state must be recreated after restore. CRaC is a startup-time optimization technique; it does not replace databases, storage systems, transaction mechanisms, or distributed coordination protocols.

## 1. Boundaries of a Checkpoint

A checkpoint records the state of a process at a point in time. Depending on the CRaC runtime, operating system, and checkpoint/restore tool, the image may include JVM memory state along with a supported subset of process state and OS resources. After restore, the JVM resumes from the saved state and resource recovery callbacks are invoked according to the CRaC mechanism.

That scope has an important boundary:

- The heap holds a copy of data the application read before checkpoint time. That copy may become stale while the application is stopped.
- Data written and committed to a database remains managed by the database. A checkpoint does not rewind or freeze the database.
- External services do not automatically stop alongside the Java process. They can change state, close connections, or process other requests while the application is checkpointed.
- Some OS resources may be supported for restoration by the runtime, yet you should not assume every file descriptor, socket, lock, device, or native state can continue working as before.
- A checkpoint image is not a distributed transaction spanning the JVM, database, message broker, filesystem, and other services.

You can picture the difference through two types of state:

| State Kind | Example | Who Is Responsible for Durability? |
|---|---|---|
| In-process state | Java objects, in-heap caches, loaded configuration, temporary data structures | The checkpoint image preserves state at capture time; the application must check whether that state remains valid after restore |
| External durable data | Records in a database, files on a persistent volume, messages stored in a broker | The external storage system or service |
| Connection and coordination state | JDBC connections, sockets, sessions, leases, distributed locks, tokens | The application and external system must coordinate closing, checking, or recreating them |

For example, a Java object may hold an account balance just read from the database. After checkpoint, another transaction updates the balance in the database. When the process is restored, the object on the heap may still contain the old balance. The JVM recovered successfully, yet the data in memory no longer reflects the latest data.

Therefore, treat a checkpoint as a continuation point of the process, not a consistent snapshot of the entire system.

## 2. Limitations Regarding Durable Data

### 2.1. Databases and Transactions

The database is typically the application's authoritative data source. CRaC does not save data on behalf of the database, does not guarantee an in-flight transaction will commit, and does not guarantee in-heap state matches externally committed data.

Several situations require attention:

1. The application modified an object on the heap without yet writing the change to the database. If checkpointing occurs, the modified object may be preserved even though durable data was not updated.
2. The application sent a write statement and the database committed, yet the process had not updated in-heap state or received the response. After restore, the application may retry the operation and create a duplicate effect.
3. An open transaction or connection may no longer be usable after restore. The database side may have rolled back the transaction, closed the session, or timed out.
4. An external transaction may continue being processed while the application is stopped for checkpointing. The heap snapshot and database state then do not form a single consistent point.

Before checkpointing, the application should bring execution flows to clean transaction boundaries:

- Stop accepting new work or switch the application to a state that rejects incoming requests.
- Wait for in-flight requests to finish within a bounded timeout.
- Commit completed transactions; safely roll back or abort incomplete transactions according to application policy.
- Close connections and connection pools according to library guidelines.
- Do not treat an in-heap object as proof that a transaction was committed. On restore, re-read required data or verify via transaction IDs and data versions.

For operations that may be retried, design for idempotency. For instance, a payment request should carry a stable idempotency key stored durably. If the process restores and resends the request, the payment service can recognize it as the same operation. When coordinating database updates and message publishing, you can use the transactional outbox pattern to record events in the same transaction as business data, then publish events via a separate process.

CRaC does not by itself provide exactly-once processing. Transaction correctness and duplicate-processing prevention must still be solved through transactions, idempotency keys, version checks, outboxes, or appropriate system protocols.

### 2.2. Files, Directories, and Volumes

A Java object may hold a path, previously read content, read/write position, or buffer state of a file. Those values do not guarantee the external file still has the same content after restore.

For example:

- Another process may modify, replace, or delete the file while the application is checkpointed.
- Temporary files in a container directory may disappear when the container or machine is recreated.
- A persistent volume may survive, yet its contents can still be updated by another process or machine.
- A file descriptor, file lock, memory-mapped file, or read/write offset may depend on OS state and deployment environment. You should not assume such a resource is always valid after restore.

If data must survive across restarts or across different machines, store it in a storage system with appropriate guarantees, such as a database, object storage, or a properly managed persistent volume. When writing important files, follow safe filesystem write procedures: write to a temporary file, flush data as required, and replace the target file with an appropriate operation. In Java, FileChannel.force can ask the OS to flush channel changes to the storage device, yet that does not by itself guarantee volume consistency, storage replication, or atomicity of the overall deployment workflow.

Before checkpointing, close files being written after finishing required operations. After restore, reopen files by path and check current state instead of relying on an old handle. If the application needs to resume appending, verify valid size, version, or offset from durable data.

### 2.3. Caches and In-Memory-Only Data

In-heap caches are an easy source of confusion because a checkpoint can retain the entire cache contents at capture time. That does not mean the cache is still fresh when the application resumes running.

During the interval between checkpoint and restore:

- Source records may have been updated or deleted.
- Cache TTLs may have expired.
- A login session may have been revoked.
- Access permissions or configuration may have changed.
- A key in a cache may no longer exist in a distributed system.

Classify caches by criticality. Rebuildable caches should be cleared or refreshed after restore. Caches containing time-sensitive data must verify TTLs and versions. If a cache is used as the sole source of truth for a business feature, revisit the design because that data can be lost when a process is replaced, a checkpoint is corrupted, or restore runs in another environment.

A common deployment approach is keeping configuration and rarely changing startup data in the checkpoint, while refreshing time-sensitive data from authoritative sources after restore. For large caches, re-initialize incrementally to avoid creating a traffic spike against the database.

### 2.4. Queues and Messaging

Message brokers manage messages and delivery state independently of the JVM. Checkpointing does not automatically synchronize offsets, acknowledgments, consumer groups, or processing state between the application and the broker.

Suppose a consumer receives a message, applies changes in the heap, and acknowledges processing to the broker. If the business changes were not durably persisted before the process is checkpointed, after restore the message may not be redelivered because the broker already received the acknowledgment. Work can then be lost.

The opposite case can also occur: business changes were committed, yet the acknowledgment never reached the broker. After restore, the broker redelivers the message and the application processes it again.

To reduce risk:

- Acknowledge messages only after business outcomes have been durably persisted.
- Use message IDs or business keys to identify already-processed messages.
- Design consumers to handle duplicate processing safely.
- Stop receiving new messages and finish or return in-flight messages before checkpointing.
- On restore, recreate consumers and verify subscriptions, offsets, and group state.

Delivery guarantees still depend on broker configuration and consumer design. CRaC does not turn at-most-once delivery into at-least-once or exactly-once.

## 3. Limitations When Working with External Systems

### 3.1. Network Connections and Connection Pools

TCP, JDBC, HTTP keep-alive, WebSocket, and message-broker connections all have lifecycles on both ends. While the JVM is stopped, the remote server may close connections due to timeouts, load balancing, redeployment, or network policies. Firewalls and NATs may also drop idle connection state.

Even if a socket or file descriptor is technically restored by the runtime, that connection may no longer be valid on the peer side. Therefore, the application should not treat a connection referenced in the heap as an active connection.

Connection pools such as JDBC pools need to be closed before checkpoint and recreated after restore. HTTP clients or SDKs that manage connections also need to be checked against library guidelines. After restore, the application should:

1. Create new connections or pools.
2. Verify connectivity to critical services.
3. Restore required subscriptions or sessions.
4. Accept business traffic only when mandatory dependencies are ready.

Do not send all connection-check requests simultaneously the moment multiple application replicas restore. Consider concurrency limits and retries with backoff and jitter to avoid creating a load surge on external services.

### 3.2. Sessions, Leases, and Distributed Locks

Many distributed systems grant resource ownership for a bounded period. Examples include service discovery leases, distributed locks, coordinator sessions, leadership (leader election), and worker heartbeats.

When a process stops, heartbeats may stop sending. A lease can expire and be granted to another process. A distributed lock can be released or revoked. When the old process is restored, its heap may still contain info indicating it holds the lock or is the leader, even though that ownership no longer exists.

This is a dangerous situation because two processes may both believe they are permitted to update a resource. Ownership must be treated as state confirmed by the external coordination system, not a boolean flag in the heap.

Common safeguards:

- Release leases or locks before checkpoint if the protocol permits.
- After restore, re-register and wait for the external system to confirm new ownership.
- Use monotonically increasing fencing tokens or generation numbers so systems recognize and reject operations from stale owners.
- Do not keep writing data solely because an in-memory variable still holds the pre-checkpoint value.
- Re-initialize heartbeats and failure-detection mechanisms once connections are established.

Fencing tokens are especially useful when an old process may wake up after a long pause. Each time new ownership is granted, the coordinator issues a new token; the storage layer checks the token before accepting writes. Thus, a stale owner cannot overwrite data after its authority has expired.

### 3.3. Tokens, Credentials, and Access Permissions

Access tokens, session cookies, short-lived certificates, and credentials from cloud providers usually have expiration times. They may remain in the heap yet already be expired or revoked when the process restores.

Some credentials are also bound to a specific IP address, host, TLS session, workload identity, or work session. Restoring in another environment can alter those conditions.

The application should check expiration and credential status after restore, refresh tokens when needed, and recreate security sessions according to provider guidelines. Do not assume holding a client object on the heap means the server-side authentication session remains valid.

Checkpoint images can also contain sensitive data residing in the heap, including tokens, passwords, API keys, personal data, or request contents. Therefore, checkpoints must be protected as copies that may contain secrets:

- Restrict permissions to read and download checkpoint images.
- Encrypt storage and transport according to deployment policy.
- Limit retention periods and securely delete old images.
- Do not log secrets inside callbacks.
- Prefer fetching or refreshing credentials from a secret manager after restore when the architecture allows.

### 3.4. Time, Deadlines, and Periodic Tasks

Time continues passing while the process is not running. A deadline computed from before the checkpoint may already be due upon restore. Data marked valid for a duration may also have expired.

For example, the application stores a token expiration timestamp, payment timeout, next task run time, or remaining session duration. If it only stores a counter in the heap and continues using that counter after restore, the application may act late or use expired state.

For business deadlines, store absolute timestamps or task state in durable data sources, then recompute remaining time using the current clock after restore. For periodic tasks, re-register schedules with the scheduler or check run schedules from an authoritative source. Do not rely on a sleeping thread or an in-memory timer accurately reflecting elapsed real-world time.

In-process duration values, such as timers for profiling or internal timeouts, also need review. After restore, re-establish deadlines and timeout states according to business requirements rather than assuming time in the heap remains valid.

### 3.5. Native and OS Resources

Java applications can use resources not fully managed by the heap: native libraries, JNI, off-heap memory, file locks, shared memory, devices, pipes, threads waiting on I/O, or resources created by third-party libraries.

The ability to checkpoint and restore these resources depends on the platform, CRaC runtime, library version, and how resources were opened. A library may be unaware the process is about to be checkpointed, and thus fail to release or recreate resources properly.

For every library using native resources or external connections, inspect CRaC support documentation and determine appropriate callbacks or integration mechanisms. If a library cannot safely recreate state, re-initialize those resources after restore or change how the library is used. Do not treat an application restoring successfully as proof that every native resource functions properly.

## 4. Using CRaC Callbacks to Manage Resource Lifecycles

CRaC provides the Resource API for applications to register work needed before checkpoint and after restore. With the CRaC API in package org.crac, a resource implements two methods:

- beforeCheckpoint: prepare the resource before the process is checkpointed. For example: stop accepting new work, wait for in-flight work to finish, flush required data, and close connections.
- afterRestore: restore the resource after the process is restored. For example: create a new connection pool, reconnect to the broker, refresh tokens, and re-register subscriptions.

The resource needs to be registered with the global context so the runtime knows to invoke its callbacks:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class DatabasePoolResource implements Resource {
    private volatile HikariDataSource pool;

    public DatabasePoolResource() {
        Core.getGlobalContext().register(this);
        openPool();
    }

    public HikariDataSource pool() {
        HikariDataSource current = pool;
        if (current == null) {
            throw new IllegalStateException("Database pool is not ready");
        }
        return current;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) {
        closePool();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) {
        openPool();
    }

    private synchronized void openPool() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(System.getenv("DB_URL"));
        config.setUsername(System.getenv("DB_USER"));
        config.setPassword(System.getenv("DB_PASSWORD"));
        pool = new HikariDataSource(config);
    }

    private synchronized void closePool() {
        HikariDataSource current = pool;
        pool = null;
        if (current != null) {
            current.close();
        }
    }
}
~~~

The example above illustrates closing the old pool and creating a new pool. It assumes the application has already stopped accepting requests and no transactions are using the pool before the pool-closing callback executes. In a real application, a coordination step is needed to halt traffic, drain in-flight work, and close the pool only once those operations finish. HikariCP also needs to be on the example's classpath.

Callbacks do not automatically solve every system problem:

- Only registered resources or those integrated via a corresponding mechanism receive callbacks.
- Callbacks do not commit on behalf of the database, do not acknowledge messages on behalf of the broker, and do not renew leases on behalf of the coordinator.
- Closing a connection in beforeCheckpoint does not guarantee an in-progress business operation was durably saved.
- afterRestore can fail because the database, broker, or network is not yet ready. The application needs bounded retry policies, readiness state, and handling when critical dependencies cannot recover yet.
- Callbacks must have bounded execution time, handle errors cleanly, and avoid creating duplicate business side effects.

If multiple resources depend on one another, coordinate proper closing and opening order. For example, stop the consumer before closing the broker connection; on restore, establish the connection first and only then start the consumer. Do not rely on callback ordering not guaranteed by the runtime or library.

## 5. Design Workflow Before Checkpoint and After Restore

A general workflow can be divided into two phases.

### Before Checkpoint

1. Transition the application to a quiescing state to stop accepting new work.
2. Wait for running requests, transactions, and tasks to complete within a defined timeout.
3. Commit or roll back transactions per business rules; acknowledge messages only after outcomes are durable.
4. Flush and close files being written; release locks or leases if required by protocol.
5. Close connection pools, sockets, consumers, and resources that cannot safely continue being used.
6. Verify the application has reached a checkpointable state; if not, report an error for the checkpoint workflow to handle.

### After Restore

1. Re-read configuration that may change and refresh authentication credentials.
2. Recreate connection pools, sockets, clients, and subscriptions.
3. Check the health of critical dependencies.
4. Refresh caches, verify data versions, and evict expired state.
5. Re-register leases, locks, heartbeats, and task schedules; verify ownership before resuming writes.
6. Open readiness state and accept traffic once the application is ready.

General flow:

~~~mermaid
flowchart TD
    A[Stop accepting new work] --> B[Drain requests and transactions]
    B --> C[Complete durable data writes]
    C --> D[Close external resources]
    D --> E[Checkpoint process]
    E --> F[Restore process]
    F --> G[Recreate connections and authenticate]
    G --> H[Sync caches, leases, and task schedules]
    H --> I[Check readiness]
    I --> J[Accept new work]
~~~

This is a conceptual workflow. Actual ordering must match the protocols of each service, library, and deployment environment. If checkpointing fails after the application has closed resources, operational procedures also need a way to return the application to serving state or restart closed resources.

## 6. Design Patterns to Make Applications Safer

### 6.1. Treat External Systems as the Authoritative Source

Do not use data in the heap as final proof of business state that can change externally. After restore, re-read critical data or verify via version, revision, or transaction ID. Caches should only hold rebuildable data or have explicit validity-checking rules.

### 6.2. Design Idempotent Operations

An operation may be retried when the process is unsure whether the previous attempt succeeded. Attach a unique ID or idempotency key to business requests and persist the processing outcome durably. This prevents retries from creating extra payments, duplicate orders, or duplicate events.

### 6.3. Separate Business State from Connection State

Business state such as a confirmed order should be stored in the database. Database connections, broker sessions, or HTTP clients are only resources used to access that state. Connections can be closed and recreated without losing business state.

### 6.4. Use Readiness to Control Traffic

A newly restored JVM may already be running yet still unable to connect to the database or broker. Readiness probes should reflect actual ability to process work. If mandatory dependencies are not ready, do not route traffic to the instance. Liveness and readiness must represent two different things: the process is alive vs. the process is ready to serve.

### 6.5. Support Multiple Restores from the Same Checkpoint

One checkpoint image can be used to create multiple instances. In that case, every instance starts with the same copy of heap state. If that copy contains a fixed consumer ID, scheduler, sequence counter, session, or resource ownership information, instances can conflict.

Generate a new instance identity on startup, register distributed resources independently, and obtain business IDs from a source with an appropriate uniqueness mechanism. Do not copy a lock, lease, or leader privilege from a checkpoint image across multiple instances. Operations with external effects still require idempotency and distributed coordination.

## 7. Assumptions to Exclude from Your Design

| Assumption | Why It Is Unsafe | How to Handle It |
|---|---|---|
| The database will revert to checkpoint time | The database runs independently and may have received new transactions | Re-read data or verify versions after restore |
| Connections in the heap remain active | Remote peers, firewalls, or brokers may have closed connections | Close before checkpoint and create new connections after restore |
| Cache variables still reflect latest data | Source data may have changed while the process stopped | Clear, refresh, or verify TTL/version |
| Messages processed in the heap were definitely persisted | The heap and broker acknowledgments do not form a single transaction | Commit durable outcomes before acknowledging; handle duplicates safely |
| The restored process still owns the distributed lock | The lease may have expired and been granted to another instance | Re-register, verify ownership, and use fencing tokens |
| In-memory tokens remain valid | Tokens may have expired or been revoked | Refresh or re-authenticate after restore |
| Timers in the heap accurately reflect elapsed time | Real time keeps passing while the process is stopped | Recompute deadlines from authoritative timestamps |
| All native resources are restored | Support depends on platform and library | Check support, release, and recreate resources |
| Multiple restores create no duplicate effects | Instances may start from identical heap state | Generate new identities and use deduplication in external systems |

## 8. Verifying in the Deployment Environment

Do not stop at verifying that checkpoint and restore commands finish successfully. Test application behavior when external systems change while the process is stopped.

Several valuable test scenarios:

- The database closes connections or restarts after checkpoint. Does the application create a new pool and serve only once the database is reachable?
- A record is updated by another process while the application is stopped. Does the application read the new version instead of using a stale cache?
- The broker redelivers a message because the acknowledgment was unconfirmed. Does the consumer avoid duplicate business side effects?
- A token expires or is revoked before restore. Does the application refresh authentication?
- A lease expires and is granted to another worker. Does the restored instance re-verify ownership before writing?
- Files on a volume change or the volume is remounted. Does the application reopen and check files properly?
- Wall-clock time passes a task deadline. Does the scheduler recompute the schedule?
- The same checkpoint is restored into multiple instances. Do the instances avoid sharing identity, locks, and sequence state?
- A dependent service is unavailable for several minutes after restore. Does the application perform bounded retries and keep readiness in the appropriate state?

Tests should run in an environment close to production in terms of OS, kernel, JDK, native libraries, container runtime, volumes, and CRaC configuration. Resource restorability can differ across platforms. A good result on a developer machine does not by itself guarantee the same checkpoint will work in another deployment environment.

## 9. When Should You Use CRaC?

CRaC fits when the goal is reducing startup time and the application can clearly define how to prepare, close, and recreate resources. Costly startup state that rarely changes, such as loaded classes, shared rebuildable data structures, or static configuration, is usually a good candidate for checkpointing.

Time-dependent state, open connections, distributed ownership, latest business data, or in-progress operations need separate handling. They must be verified or recovered from authoritative sources after restore.

Do not use a checkpoint image as the sole storage location for business data. Images can be deleted, become incompatible with new environments, fail to restore, or contain stale state. Data needing long-term persistence must still be stored in durable systems with appropriate backup, recovery, and consistency policies.

When boundaries are designed properly, CRaC can shorten JVM time-to-readiness without changing the responsibilities of databases, message brokers, filesystems, or distributed services. Applications must prepare state before checkpointing, recreate resources after restore, and always re-verify assumptions that may have changed while the process was stopped.