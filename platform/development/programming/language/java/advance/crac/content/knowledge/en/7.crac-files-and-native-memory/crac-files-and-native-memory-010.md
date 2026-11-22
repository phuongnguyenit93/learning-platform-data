# Scope of close, reopen, and limitations of resource policies

In CRaC, close and reopen are resource lifecycle management operations around checkpoint and restore. An application can close files, channels, sockets, or clients before checkpoint and reopen them after restore. However, a resource policy is only effective within the scope of the resources that the owning component has explicitly identified and managed.

There is no single generic close command that can automatically understand all of the application's resources. Closing a wrapper object does not necessarily close every related resource; reopening a handle also does not automatically restore sessions, transactions, locks, subscriptions, or business state. To design this properly, it is necessary to define ownership boundaries, dependency order, state to be saved, and the limitations that the application must accept.

## 1. What does a resource policy include?

A resource policy describes how a component prepares before checkpoint and recovers after restore. At a minimum, the policy needs to answer:

- Which component owns the resource?
- Which handles or operations must stop before checkpoint?
- What data needs to be flushed or saved?
- Which resources must be closed and which resources can be kept according to runtime/library guidelines?
- After restore, with what configuration is it reopened and to what extent is state restored?
- If close or reopen fails, how will the application handle it?
- When is the component allowed to accept work again?

For example, a file-reading component may own a FileChannel and a read buffer. Its policy may require stopping the reader, recording the processed logical offset, closing the channel, and discarding the old buffer. After restore, the component opens a new channel, resets the position according to the saved offset, creates a new buffer, and only then continues reading.

This policy does not automatically apply to every other object holding the same file path. Another service may own a separate channel, and must have its own lifecycle policy or be managed by the same explicit owner.

## 2. Management scope: from handles to external systems

The following scopes can be distinguished:

| Scope | Examples | What can a close/reopen policy manage? | Limitations to remember |
|---|---|---|---|
| Handle | InputStream, OutputStream, FileChannel, socket | Close the handle and create a new handle | Does not automatically restore processed data, logical position, or protocol session |
| Component | File reader, HTTP client, connection pool, broker consumer | Coordinate multiple handles and the component's internal state | Needs to know clearly which handles belong to the component's ownership |
| Process | Multiple services, executors, listeners, and shared resources | Coordinate components registered with CRaC | Does not automatically detect all native resources or resources managed internally by hidden libraries |
| External system | Database, filesystem, broker, Redis, HTTP service, distributed lock | Can reconnect or verify state through the system's API | Cannot turn back time or undo side effects already committed in that system |

The wider the scope, the greater the coordination required. An application-level Resource can manage multiple components, but should only do so when there is clear ownership and a defined lifecycle order. Registering a Resource with the global context does not turn it into an automatic manager for every resource in the JVM.

## 3. How far does close reach?

### Close according to the API contract

Each API defines its own close behavior. For example:

- Closing BufferedInputStream usually closes the underlying stream it wraps.
- Closing BufferedOutputStream usually flushes the buffer according to the class contract and then closes the underlying stream.
- Closing FileChannel makes the channel no longer usable and releases related resources according to the API contract.
- Closing a connection obtained from a pool may only return the connection to the pool, not necessarily close the physical connection to the server.
- Closing a high-level client may close multiple internal connections, but the exact scope depends on the library.

Therefore, one cannot infer that calling close on an arbitrary object will release all of the component's resources. Read the API contract and identify which object actually owns the handle.

### Wrappers and underlying resources

A wrapper chain typically looks like this:

~~~text
Application
   |
   v
BufferedInputStream
   |
   v
FileInputStream
   |
   v
Operating system file descriptor
   |
   v
File on filesystem
~~~

Closing the outermost wrapper may close the underlying stream according to the wrapper's contract. However, that does not delete the file, does not close other independent streams opening the same file, and does not stop another thread holding a reference to another wrapper.

Similarly, two services may share a shared client. If one service closes the client in its own callback while the other service is still using it, the application will encounter errors. Shared resources need a single lifecycle owner or a clear reference count/coordination rule.

### Close does not replace stopping work

Closing a handle while another thread is still reading or writing can cause that operation to fail, write partial data, or leave inconsistent business state. Before closing, the component needs to:

1. Stop accepting new work.
2. Wait for operations currently using the resource to complete or cancel them according to defined rules.
3. Synchronize buffers and save necessary progress.
4. Close the handle after there are no remaining users.

A Resource callback that only closes resources does not automatically solve coordinating requests, executors, or consumers. That part is the responsibility of the application architecture.

## 4. Reopen means creating a new resource

Reopen typically creates a new handle to the same resource source. It does not bring a closed handle object back to life and does not guarantee that the external environment is still the same as at checkpoint time.

When reopening, it is necessary to determine:

- The current address or path.
- The access mode: read, write, append, or truncate.
- Whether credentials and certificates are still valid.
- The offset, sequence, or cursor to restore.
- The subscription, consumer group, or lease to re-register.
- Ownership of shared resources.
- Which dependencies must be ready before opening dependent resources.

For example, reopening a FileChannel with READ and WRITE does not automatically set the channel to its pre-checkpoint position. The application must save and restore the position as needed. Reopening an HTTP client does not restore a login session if the token has expired. Reopening a broker consumer does not mean unacknowledged messages will not be redelivered.

Reopen can also fail. The file may have been deleted, access permissions changed, the database unavailable, or credentials revoked. If the resource is required, the application needs to report an unready state and not accept work that depends on that resource.

## 5. Defining ownership boundaries

Each resource should have a single lifecycle owner. The owner is responsible for:

- Creating the handle and publishing how it is used.
- Not allowing external code to arbitrarily close the handle without an established convention.
- Stopping resource users before checkpoint.
- Performing close and reopen according to the same policy.
- Checking state after recovery.

If a pool is used by multiple repositories, repositories should not register their own callbacks to close the pool. The pool-managing component should be responsible for the pool's lifecycle; repositories only use the pool according to the contract.

If multiple types of resources depend on each other, the close and reopen order may differ. For example, a consumer depends on a broker client:

- Before checkpoint, stop the consumer first and only then close the client.
- After restore, create the client first and only then start the consumer.

Similarly, if a writer depends on a FileChannel, it is necessary to stop the writer and flush data before closing the channel; after restore, open the channel first and only then allow the writer to operate.

Do not rely on callback ordering between independent Resources if it is not guaranteed by the CRaC API/runtime version in use. When ordering matters, group dependent parts into a single coordinating component or use an ordered coordination mechanism supported by the framework.

## 6. Example: managing a group of resources with dependency relationships

The following example describes a component-level Resource managing multiple resource parts. The list is passed in dependency order: foundational components first, components that use them later. When preparing for checkpoint, the group closes in reverse order; when restoring, the group opens in forward order.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ResourceScope implements Resource {
    public interface ManagedPart {
        // If the method throws an error, the part must preserve or restore
        // its own usable state.
        void closeForCheckpoint() throws Exception;

        // If the method throws an error, the part must clean up any
        // partially opened state and remain in a closed state.
        void reopenAfterRestore() throws Exception;
    }

    private final List<ManagedPart> dependencyOrder;
    private boolean prepared;
    private boolean unavailable;

    public ResourceScope(List<ManagedPart> dependencyOrder) {
        this.dependencyOrder = List.copyOf(dependencyOrder);
        Core.getGlobalContext().register(this);
    }

    public synchronized boolean isReady() {
        return !prepared && !unavailable;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (prepared) {
            return;
        }

        unavailable = true;
        List<ManagedPart> closed = new ArrayList<>();

        try {
            for (int i = dependencyOrder.size() - 1; i >= 0; i--) {
                ManagedPart part = dependencyOrder.get(i);
                part.closeForCheckpoint();
                closed.add(part);
            }
            prepared = true;
        } catch (Exception failure) {
            boolean recovered = true;
            for (int i = closed.size() - 1; i >= 0; i--) {
                try {
                    closed.get(i).reopenAfterRestore();
                } catch (Exception recoveryFailure) {
                    failure.addSuppressed(recoveryFailure);
                    recovered = false;
                }
            }
            if (recovered) {
                unavailable = false;
            }
            throw failure;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        if (!prepared) {
            return;
        }

        List<ManagedPart> reopened = new ArrayList<>();
        try {
            for (ManagedPart part : dependencyOrder) {
                part.reopenAfterRestore();
                reopened.add(part);
            }
            prepared = false;
            unavailable = false;
        } catch (Exception failure) {
            for (int i = reopened.size() - 1; i >= 0; i--) {
                try {
                    reopened.get(i).closeForCheckpoint();
                } catch (Exception cleanupFailure) {
                    failure.addSuppressed(cleanupFailure);
                }
            }
            throw failure;
        }
    }
}
~~~

In the example:

- dependencyOrder is ordered from foundational resources to components that depend on them.
- beforeCheckpoint marks the scope as unavailable, then closes in reverse order.
- If a part fails to close, the already-closed parts are reopened in the appropriate order and the error is propagated.
- afterRestore opens in dependency order; if an open step fails, the already-opened parts are closed again in reverse order.
- isReady allows the application layer to check the scope before accepting work.

This is an illustrative coordination skeleton. ManagedParts need to implement close/reopen safely on partial failure as described in the contract in the code. In a real application, the unavailable state needs to be wired to a readiness/traffic gate; if recovery or rollback fails, do not continue processing work that depends on the resource group. Synchronizing callbacks with threads currently using the resource must also be performed at the owning layer.

This example manages ordering within a single scope. It does not impose ordering on other Resources registered independently with the CRaC runtime.

## 7. Limitations of close/reopen policies

### Does not automatically detect all resources

An application may use resources through libraries, JNI, native code, or frameworks. An application-written Resource only manages what it knows about and is given ownership of. Resources hidden inside libraries need to be handled by the library's CRaC integration or the vendor's specific guidance.

Do not create a generic callback that tries to close everything in the JVM. That approach can mistakenly close resources managed by the framework, conflict with shutdown order, or corrupt state needed for restore.

### Does not undo external side effects

Closing a database connection does not undo a committed transaction. Closing an OutputStream does not erase file content already written. Closing a broker consumer does not revoke an acknowledged message. Reopen does not return the database, broker, or filesystem to its state at checkpoint time.

If an operation may be resent after restore, an idempotency key, deduplication, or business checkpoint is needed to determine whether the operation has already completed. A JVM checkpoint is not a distributed transaction.

### Does not guarantee restoring the exact same state

A new handle may point to the same path or endpoint while the data state has changed. A file may have been replaced; a server may have switched nodes; a token may have been revoked; a lease may have expired.

The application must verify the version, offset, ownership, and current state before continuing. If it cannot verify, it needs to reinitialize from the authoritative data source or invoke a business recovery process.

### Does not replace thread coordination

A Resource callback does not automatically stop all threads using a resource. A thread may be writing to a buffer, a request may be holding a connection, or a consumer may be processing a message. The application must coordinate stopping incoming work, draining, or canceling in-flight operations before closing the handle.

### Does not guarantee every close can be reopened

Some sources are one-time streams, pipes, or response bodies that do not support seek/resume. After closing, the same next byte cannot be retrieved if the source does not provide a resume protocol. In such cases, checkpointing must be saved at the protocol or business layer.

### Does not replace backup and data recovery

Close/reopen manages handle lifecycles. It does not replace file backups, database backups, transaction logs, replication, or data recovery procedures. If a file is deleted or data is corrupted during checkpoint, reopening the file cannot automatically recover the lost content.

### Does not guarantee callbacks always complete successfully

Close can fail due to an I/O error; reopen can fail due to an unavailable service or changed access permissions. Callback errors must be propagated and handled according to the capabilities of the CRaC runtime. Errors should not be swallowed and the resource marked ready.

If checkpoint preparation fails after some resources have already closed, the application needs a rollback or local recovery strategy. If rollback also fails, keep the application in an unavailable state and let operational mechanisms decide how to recover; do not continue using a resource group in an indeterminate state.

## 8. Common resource types and limitations

| Resource | Typically required policy | Limitations |
|---|---|---|
| InputStream from file | Save logical offset, close, reopen, restore position | General streams have no seek API; file may change |
| OutputStream | Stop writer, flush, close, choose append/truncate properly | Flush does not always mean data is durable; records may be partially written |
| FileChannel | Save position, sync when needed, close and reopen | I/O position may differ from business progress; locks must be reacquired |
| JDBC connection/pool | Drain transactions, close or refresh per pool guidance, validate connection | Database-side sessions and transactions have their own lifecycle |
| HTTP client/socket | Close or refresh connections, authenticate and reconnect | Peer may change; protocol session is not automatically restored |
| Message consumer | Stop receiving messages, process/ack per rules, re-subscribe | Unacked messages may be redelivered; deduplication is needed |
| Distributed lock/lease | Release or re-verify ownership | Leases continue to expire according to external time |
| Native handle/JNI | Use APIs and hooks provided by the library/native component | A Java Resource cannot automatically infer how to close every native pointer |

## 9. Designing policies according to the required level

Not every resource needs the same policy. They can be divided into groups:

**Keep as-is when supported.** Some states or resources are directly supported by the CRaC runtime or library. Follow the official guidance of the version in use and avoid closing them yourself if that conflicts with the integration.

**Close and recreate.** Applies to handles that can be safely reopened, such as file channels, clients, or connection pools when required by the library. Save the information needed to recreate them, not the expectation that the old handle remains valid.

**Verify then continue.** Applies to caches, credentials, leases, subscriptions, or remote state that may still exist but have changed. After restore, query the authoritative source before using.

**Cannot resume directly.** Applies to one-time streams or protocols that do not support offset restoration. It is necessary to redesign checkpointing at the business layer, or accept re-reading from the beginning in a safe manner.

A component can combine multiple groups. For example, an application closes HTTP connections, re-reads credentials, verifies caches, and re-registers subscriptions. The policy needs to describe each resource individually rather than assigning a single action to the entire component.

## 10. Testing and operations

Testing a resource policy should include both success and failure scenarios:

- Checkpoint when no I/O operations are running.
- Checkpoint when requests or consumers are actively using the resource.
- A close failure after dependent resources have already closed.
- Reopen failure because the file no longer exists, credentials expired, or the service is unavailable.
- A shared resource used by multiple components.
- External files or data changing during the checkpoint interval.
- A message or write operation being redelivered after restore.
- Multiple checkpoint/restore cycles to detect duplicate open handles, duplicated threads, or incorrect readiness state.

Operational observability should clearly show what state the component is in: active, preparing for checkpoint, closed, recovering, ready, or failed. Logs should indicate which resource failed and why, without logging credentials or sensitive data.

Readiness must reflect the actual usability of essential dependencies. A non-null client object is not enough to mark ready; it is necessary to verify the connection or complete required handshakes/registrations.

## 11. Conclusion

The scope of close/reopen is determined by ownership and the contract of each resource. A good policy clearly states which handles need to be closed, which component coordinates, what data must be saved, the recovery order, and how errors are handled. For interdependent resources, ordering should be managed within a single scope with a clear owner.

The core limitation is that close/reopen only manages the lifecycle of resources that the application controls. It does not automatically detect all native handles, does not stop all threads, does not undo external side effects, does not guarantee the data source remains intact, and does not make every stream resumable. The application needs to verify state after restore and only continue when required resources are ready.
