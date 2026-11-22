# In-process state and out-of-process resources

CRaC (Coordinated Restore at Checkpoint) allows saving the state of a Java process at a point in time and then restoring the process from that checkpoint. This approach can shorten startup time: the application runs beforehand, loads classes, initializes frameworks, and warms up needed parts; afterward the prepared state is checkpointed for reuse.

For a checkpoint to restore safely, two things that are frequently confused must be separated:

- **In-process state** is data and execution state managed by the JVM, such as objects on the heap, static values, and thread state.
- **Out-of-process resources** are resources managed by the OS, filesystem, network, or external services, such as database connection sessions, sockets, distributed locks, and data residing in Redis.

A Java object may remain intact after restore while the resource that object represents has expired or become invalid. This is a critical issue to handle when designing CRaC-enabled applications.

## 1. Two layers of state to distinguish

### In-process state

This is the portion of state belonging to the Java process and saved in the checkpoint image according to the mechanisms of the JVM and checkpoint platform. Examples:

- Objects on the heap: parsed configuration, in-memory caches, data structures, singletons, and transient business state.
- Static fields and reference graphs among objects.
- JVM and thread execution state: stacks, execution positions, and runtime data supported by the checkpoint mechanism.
- Initialized framework state: metadata, registries, dependency graphs, and components already created in memory.

When the process is restored, the application can continue using many objects created before the checkpoint without executing the full startup sequence again.

However, checkpointing does not turn the heap into a durable datastore. It is a snapshot of one process's state at a point in time, not a mechanism for saving objects in a business format capable of being read independently, schema-upgraded, or synchronized with another system.

### Out-of-process resources

These are resources whose lifecycle or state is managed outside the Java heap. Examples:

- Databases managing sessions, transactions, cursors, and locks on the database server.
- Redis or message brokers managing connections, subscriptions, consumer groups, and their data.
- Operating systems managing file descriptors, sockets, network ports, file locks, and certain process resources.
- External systems managing tokens, leases, distributed locks, login sessions, and job state.
- Filesystems managing file contents; remote services managing data and recorded side effects.

A Java application usually holds only an object representing an external resource. For example, a Connection object on the heap may hold information to interact with a database session. The fact that the Connection object still exists after restore does not prove the database-side session still exists or remains usable.

### Comparison by example

| Component | In-process state | External state | Action required after restore |
|---|---|---|---|
| JDBC Connection | Connection object and wrapper objects around it | Session, transaction, and socket to the database | Check pool lifecycle; create new valid connections |
| HTTP client | Client object, configuration, and connection manager | TCP/TLS sessions, DNS, and remote servers | Initialize or refresh client per library guidance |
| File | Path, buffers, and file representation object | File contents, access permissions, and file state on the filesystem | Flush data before checkpoint; reopen file if handle is invalid |
| Cache | Entries residing on the heap | Authoritative data sources such as database or Redis | Check freshness and refresh potentially stale entries |
| Distributed lock | Lock manager object and token held on the heap | Lease or lock managed by a distributed coordination system | Verify ownership; do not continue relying on an expired lease |
| Scheduler | Executor object and registered tasks | Wall-clock time, deadlines, and external job state | Reconcile against current time and reschedule when needed |

Some OS resources may be restorable by the checkpoint tool depending on resource kind, version, and deployment environment. Therefore, neither assume every file descriptor or socket is lost, nor assume they definitely remain usable. Check actual supportability and follow integration guidance from the JVM, CRaC, and libraries in use.

## 2. Why can an object still exist while its underlying resource is lost?

Consider an application with an instance field as follows:

~~~java
public final class OrderRepository {
    private final Connection connection;

    public OrderRepository(Connection connection) {
        this.connection = connection;
    }
}
~~~

The `connection` field is a reference residing inside the `OrderRepository` object. When a checkpoint saves process state, this reference belongs to in-memory state. Yet the database is an independent process or service. It does not rewind in time along with the JVM.

During the interval from checkpoint creation to restore, the database may have:

- Closed the session due to timeout or server restart.
- Rolled back uncommitted transactions.
- Reclaimed the connection due to resource limits.
- Modified data that the application cached before checkpointing.
- Changed access permissions or authentication credentials.

Consequently, after restore, calling a method on the old `Connection` object can fail even though the `connection` field is still non-null. A null check only tells whether the application still holds a reference; it cannot check session validity on the server side.

This principle applies to every wrapper object: an object may remain alive on the heap while the resource represented by that wrapper was closed, expired, or changed externally.

## 3. Checkpointing does not rewind external systems

A checkpoint records the state of a Java process. It does not create a consistent snapshot across the entire distributed system.

For example, before checkpointing the application sent a debit request and the database committed the transaction. Later the process is restored from the old checkpoint. The database still retains the committed transaction; it does not automatically undo it just because the JVM returned to an earlier memory state.

This introduces a critical risk: **heap state can be older than side effects that occurred outside the process**.

Distinguish three situations:

1. **Data residing only on the heap:** that data can revert to its exact state at checkpoint time.
2. **Data already written to an external system:** the external data persists according to that system's rules.
3. **An operation in flight:** the outcome depends on whether the external system already received, processed, or committed the operation.

Therefore, before checkpointing, bring the application to a safe point:

- Stop accepting new work during the checkpoint preparation window.
- Wait for running requests or tasks to finish, or cancel them according to an explicit rule.
- Commit or roll back transactions according to business semantics.
- Flush file write buffers and close resources whose lifecycle cannot be guaranteed after restore.
- Do not hold distributed locks or leases assuming external time stops along with the process.

If an operation might be retried after restore, design idempotency, using idempotency keys or deduplication mechanisms. For flows writing data and emitting events, a transactional outbox can preserve consistency between database changes and events to publish. Do not rely on checkpointing to undo side effects already recorded by another system.

## 4. Resource lifecycle around checkpoint and restore

CRaC provides the Resource API for applications to participate in the checkpoint/restore lifecycle. The two key callbacks are:

- `beforeCheckpoint`: prepares resources before the JVM is checkpointed.
- `afterRestore`: recovers or recreates resources after the JVM is restored.

A Resource is registered with a context, typically the global context:

~~~java
Core.getGlobalContext().register(resource);
~~~

Callbacks allow the application to handle resources whose business semantics the JVM cannot fully understand on its own. For example, the JVM can see a client object, yet only the application knows which subscriptions that client holds, which transactions need completion, or where to re-read credentials.

### Before checkpoint: bringing the application to a safe state

In `beforeCheckpoint`, the application can:

- Stop accepting new work and wait for active work to finish.
- Complete or roll back transactions.
- Flush buffered data and close files if necessary.
- Close connections or pools not guaranteed to remain reusable.
- Stop consumers, listeners, or background tasks in a library-supported manner.
- Release locks or leases that might expire while the process is inactive.

Not every resource must be closed manually in a callback. Some resource types are directly supported by the JVM, CRaC, or integrated frameworks/libraries. Check the documentation of your deployed version before managing their lifecycles manually; closing a framework-managed listener or connection at the wrong time can break restoration.

### After restore: re-establishing connections with the current world

In `afterRestore`, the application can:

- Recreate clients, connections, or pools closed prior to checkpoint.
- Restart consumers and background tasks.
- Re-read credentials, dynamic configuration, or certificates if they may have changed.
- Check caches and temporary data that may have become stale.
- Verify leases, subscriptions, and remote resource ownership.
- Run health checks before accepting traffic.

After restore, the application is operating in the present world. It must use current time, service status, and current access credentials instead of assuming everything stayed identical to checkpoint time.

### Example: managing a remote client

The following example illustrates a Resource owning a client that can be closed and recreated. `RemoteClient` is an application- or library-defined type; actual connection creation depends on the library in use.

~~~java
import java.util.concurrent.Callable;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RemoteClientResource implements Resource {
    private final Callable<RemoteClient> clientFactory;
    private RemoteClient client;

    public RemoteClientResource(Callable<RemoteClient> clientFactory)
            throws Exception {
        this.clientFactory = clientFactory;
        this.client = clientFactory.call();
        Core.getGlobalContext().register(this);
    }

    public synchronized RemoteClient getClient() {
        if (client == null) {
            throw new IllegalStateException("Remote client is not ready");
        }
        return client;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (client != null) {
            client.close();
            client = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = clientFactory.call();
    }
}
~~~

Key points in the example:

- The Resource retains a factory so it can create a new client after restore.
- The current client is closed before checkpoint.
- After restore, the client is recreated via the factory.
- The Resource registers only once with the global context.
- The application must control client access while preparing for checkpointing; closing resources in a callback does not replace stopping and draining requests.

When using a connection pool, manage the lifecycle of the pool itself per vendor guidance. With some pools, calling `close` on a connection merely returns it to the pool rather than closing the physical connection. In that case, closing only a borrowed connection may not suffice to refresh all stale connections.

Callbacks must also be designed to handle errors gracefully. If closing or recreating a resource fails, the checkpoint or restore process may not finish as expected. Do not mark the application ready while the client has not yet been created. At the same time, do not assume every `beforeCheckpoint` invocation definitely leads to an `afterRestore` invocation; have a way to recover resources if checkpointing is rejected or fails.

## 5. Types of resources requiring attention

### Database connections and transactions

A Java Connection represents a connection to a database. On the database side, sessions, transactions, locks, and cursors may be managed separately.

Before checkpoint:

- Do not leave business transactions in an incomplete state.
- Commit or roll back transactions according to business rules.
- Stop issuing new connections during preparation.
- Follow the CRaC guidance of the connection pool and JDBC driver in use.

After restore:

- Recreate or refresh the pool if required by the library.
- Test database connectivity before accepting traffic.
- Do not reuse old transactions, cursors, or sessions merely because Java objects still exist.
- Re-read authoritative data if caches on the heap may have gone stale.

### Sockets, HTTP clients, and message brokers

A socket involves both local OS-managed state and remote peer state. The peer may have closed the connection, timed out, or changed state while the application was checkpointed.

For HTTP clients, broker clients, or consumers, check the library's CRaC integration documentation. Some libraries provide hooks or automatic connection refresh; others require the application to close and recreate clients. Pay close attention to subscriptions, consumer assignments, offsets, and message acknowledgments to avoid duplicate or missed processing.

### Files and write buffers

File contents belong to the filesystem, not the JVM heap. File representation objects and Java buffers are in-process state; actual files and access permissions are managed by the filesystem.

Before checkpoint, flush buffered data to avoid losing writes not yet transferred to the filesystem. Close and reopen files after restore if handles are unsupported or invalid. If the application needs guarantees that data is durably persisted, use appropriate filesystem synchronization mechanisms; flushing a Java buffer is not always equivalent to ensuring data resides on storage hardware.

### Locks and leases

In-JVM locks such as `synchronized` or `ReentrantLock` have process-bound state. Meanwhile, file locks, database locks, and distributed locks can be managed by external components.

A distributed lease usually has an expiration time. Time continues passing while the application is checkpointed. Upon restore, the lease may have expired and another process may have acquired ownership. The application must re-verify ownership before continuing operations protected by the lease.

Do not hold a distributed lock across a checkpoint assuming lease timers pause. If business logic must continue after restore, design a re-acquisition step and check fencing tokens or ownership versions per the coordination system's mechanism.

### Caches, configuration, and credentials

Heap caches may restore intact yet be stale relative to authoritative data sources. Configuration or credentials may also have rotated between checkpoint and restore.

After restore, determine which data can continue being used and which must be re-read. For instance, caches of rarely changing reference data can be retained if a version-checking mechanism exists; access tokens, secrets, certificates, and time-limited configuration usually need verification or refreshing.

### Clocks and scheduled tasks

Checkpointing does not halt external system clocks. A deadline, token expiration, lease, or scheduled run may come due while the process is inactive.

Do not simply store a remaining duration on the heap and assume that interval stays accurate after restore. Reconcile current time against an appropriate time source, check deadlines, and recalculate schedules. For duration measurements using monotonic clocks, inspect the behavior of the runtime and checkpoint platform; do not arbitrarily assume values measured before checkpoint are directly comparable with values after restore.

## 6. Designing reliably operable Resources

A good Resource should have clear ownership boundaries: knowing which resource it manages, who may use that resource, and how to recreate it after restore.

Several useful principles:

1. **Register the true owner:** the component responsible for the resource's lifecycle should manage callbacks. Avoid having multiple Resources simultaneously close or recreate the same pool.
2. **Register once:** avoid creating duplicate registrations for the same instance during initialization or refresh.
3. **Make callbacks safe to invoke:** handle cases where the resource is not yet created, already closed, or in a partial state. Do not assume callbacks encounter only an ideal state.
4. **Do not hold active work:** coordinate with request handlers, executors, and consumers to bring the application to a safe point before closing resources.
5. **Recreate from current configuration:** after restore, factories should use currently valid configuration and credentials.
6. **Signal readiness only after recovery finishes:** health checks must reflect actual usability of essential dependencies.
7. **Respect library integration:** do not manually close resources if the framework or library already provides native CRaC support.
8. **Handle errors explicitly:** if a mandatory dependency cannot be recreated, the application must report an error and not continue handling requests as though the dependency were working.

Not every object on the heap needs to implement `Resource`. Only components owning resources whose lifecycle requires coordination with checkpoint/restore need to participate. A pure data object holding no external resources can usually restore alongside process state without dedicated callbacks.

## 7. Testing post-restore behavior

One successful startup from a checkpoint is not enough to prove the application handles every scenario properly. Test in an environment close to real deployment, including:

- Restoring while databases or brokers continue running normally.
- Restoring after a dependency has restarted or closed old sessions.
- Restoring after an interval long enough for tokens, leases, or caches to expire.
- Testing transactions and requests active during checkpoint preparation.
- Verifying the application does not spawn duplicate consumers, schedulers, or background workers.
- Verifying side effects are not executed repeatedly when an operation is retried after restore.
- Verifying callbacks report errors properly when closing or recreating resources fails.
- Performing multiple checkpoint/restore cycles to catch duplicate callback registrations, connection leaks, or duplicated background tasks.

Test outcomes depend on the CRaC-supporting JDK version, libraries, OS, and checkpoint tooling used. Therefore, verify on the exact runtime stack that will run in production.

## 8. Common misconceptions

**“The object still exists, so the connection still works.”**  
Incorrect. The object and the database-side session have distinct lifecycles. Verify or recreate connections according to driver and pool guidance.

**“Restore will roll back operations performed after the checkpoint.”**  
Incorrect. Databases, message brokers, and external services do not automatically revert to earlier states. Committed side effects can still persist.

**“All off-heap resources are automatically lost.”**  
Inaccurate. Restorability depends on resource kind, CRaC implementation, OS tooling, and library integration. Verify each resource type.

**“Just close everything in beforeCheckpoint.”**  
Closing resources out of order can break in-flight requests or conflict with frameworks. First stop accepting new work, drain active work, and follow the lifecycle provided by libraries.

**“Heap caches are always still valid after restore.”**  
Incorrect. Caches may still exist while source data has changed. Validate freshness according to cache policy.

**“A checkpoint is a substitute for database backups.”**  
Incorrect. Checkpointing serves to recover process state. It does not replace backups, transaction logs, replication mechanisms, or storage-system data recovery procedures.

## 9. Conclusion

When designing Java applications with CRaC, treat a checkpoint as the boundary between a process's memory state and an external world that continues operating. Data on the heap can be restored, yet sessions, connections, locks, credentials, deadlines, and external side effects must be evaluated under their own lifecycles.

An application supports CRaC well when it can bring itself to a safe state before checkpointing, recreate or verify resources after restore, and continue processing without assuming external systems have reverted to the past.