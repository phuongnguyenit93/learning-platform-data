# Restoring Component State When a Checkpoint Is Aborted

In CRaC (Coordinated Restore at Checkpoint), each component can prepare resources before a checkpoint and reinitialize resources after restore through the Resource interface. However, not every checkpoint request successfully creates an image. A callback may throw an exception, the runtime may fail to create an image, or the checkpoint engine may encounter an error at the native step.

When a checkpoint is aborted, the original Java process continues running. Changes that components made during the preparation phase may still be in effect. The application needs to restore them to continue serving normally.

A point to distinguish is **an aborted checkpoint** and **a failed restore**. The two cases occur at two different stages and require different handling.

## 1. Resource lifecycle and potential failure points

An object implementing Resource registers with Context to receive notifications from CRaC. The API has two callbacks:

- beforeCheckpoint(): prepares the component before the runtime creates the image.
- afterRestore(): reinitializes the component after a process is restored from the image.

A successful cycle has the form:

~~~text
Running application
        |
        | Checkpoint request
        v
beforeCheckpoint() of Resources
        |
        v
Runtime creates checkpoint image
        |
        v
Launch process from image
        |
        v
afterRestore() of Resources
        |
        v
Application continues running
~~~

If a beforeCheckpoint() callback fails or the checkpoint operation at the runtime/native layer fails, the cycle branches to the abort path:

~~~text
Running application
        |
        | Checkpoint request
        v
beforeCheckpoint() of Resource
        |
        v
A callback or engine encounters an error
        |
        v
Checkpoint is aborted
        |
        v
Original Java process continues running
        |
        v
Application restores prepared components
        |
        v
Application returns to ready state
~~~

There is no valid image to restore in this branch. Therefore, afterRestore() is not a rollback callback for an aborted checkpoint. afterRestore() is only called when the runtime actually restores a process from a checkpoint image.

### Distinguishing three outcomes

| Outcome | What happened? | Where the application continues |
|---|---|---|
| Checkpoint succeeded and restore succeeded | The image was created and the process was restored | New process, after the restore phase |
| Checkpoint failed or was aborted | No valid checkpoint was created | Original Java process |
| Restore notification failed | The process was restored, but an afterRestore() callback encountered an error | Restored process, but may not be ready to serve |

With the Core.checkpointRestore() API, a failed checkpoint is reported by CheckpointException and execution continues in the original Java instance. An error during the restore phase is reported by RestoreException and occurs in the new Java instance. If the runtime does not support checkpoint/restore, the API may throw UnsupportedOperationException.

## 2. Why must prepared state be rolled back?

beforeCheckpoint() often modifies the active state to satisfy image creation conditions. For example:

- Pausing acceptance of new requests.
- Stopping workers or thread pools.
- Flushing buffers and closing files.
- Closing sockets and database connections.
- Pausing scheduled periodic jobs.
- Switching a cache or component to read-only mode.

If the checkpoint succeeds, components are reinitialized in afterRestore(). However, if the checkpoint is aborted, the old process still exists. Components that closed connections or paused workers need to be reopened.

For example, a server closed its listener in beforeCheckpoint(). Then another Resource detected an unclosed file descriptor and caused the checkpoint to fail. If the server does not reopen the listener, the JVM keeps running, but the application cannot receive new requests.

This is a state bug after an aborted checkpoint: the process is alive, but part of the application remains in preparation mode.

### Do not use afterRestore() as the default rollback

afterRestore() is not called merely because a beforeCheckpoint() callback failed. If recovery logic is placed solely in afterRestore(), the application can get stuck in a paused state when a checkpoint is aborted.

Two operations must be clearly separated:

- **Rollback after checkpoint abort:** restoring the state of the original process after Core.checkpointRestore() throws CheckpointException.
- **Initialization after restore:** recreating resources in afterRestore() of the restored process.

The two operations may share some functions for reopening connections or resuming workers, but they must be called along the appropriate lifecycle branch.

## 3. State model of a component

A resource should explicitly represent its state. For example:

| State | Meaning |
|---|---|
| ACTIVE | The component is serving normally |
| PREPARING | Stopping work or releasing resources |
| PREPARED | Finished preparing for checkpoint |
| ROLLING_BACK | Restoring after the checkpoint was aborted |
| RESTORING | Recreating resources after restore |
| READY | Resources are ready to serve |

State flow when checkpoint succeeds:

~~~text
ACTIVE -> PREPARING -> PREPARED
                           |
                           | Restore succeeds
                           v
                       RESTORING
                           |
                           v
                         READY
~~~

State flow when checkpoint is aborted:

~~~text
ACTIVE -> PREPARING -> PREPARED
                           |
                           | CheckpointException
                           v
                      ROLLING_BACK
                           |
                           v
                         READY
~~~

If an error occurs midway through preparation, the component must undo the work it itself has performed before throwing an exception. If the component has finished preparing successfully, but another resource or the checkpoint engine fails afterward, the application's coordinator needs to instruct the prepared components to roll back.

### Design principles

**Record each change:** if a worker was paused, a connection closed, or a buffer flushed, save the corresponding state to know which step needs to be undone.

**Rollback can be called multiple times:** a component may be asked to roll back during local error handling and later called again by the coordinator. The rollback method should be idempotent, meaning calling it again does not corrupt the state.

**Undo in reverse order:** if A was prepared before B and B depends on A, the rollback process usually needs to restore B first and then A. This order reverses the preparation order.

**Do not mark READY too early:** only allow accepting requests after the listener, workers, connection pools, and required dependencies are operational.

**Preserve the original error:** if rollback also fails, record the rollback error as a suppressed exception or log it separately, without hiding the cause that aborted the checkpoint.

## 4. Self-rollback if beforeCheckpoint() fails midway

A callback may perform multiple operations. If the third operation fails after the first two succeeded, that callback itself must undo the work already done.

Example of a resource managing a cache with writers and a file handle:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CacheResource implements Resource {
    private final LocalCache cache;

    private boolean writersPaused;
    private boolean fileClosed;
    private boolean prepared;

    public CacheResource(LocalCache cache) {
        this.cache = cache;
        Core.getGlobalContext().register(this);
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        if (prepared) {
            return;
        }

        try {
            cache.pauseWriters();
            writersPaused = true;

            cache.flush();
            cache.closeFile();
            fileClosed = true;

            prepared = true;
        } catch (Exception failure) {
            rollbackPartialPreparation(failure);
            throw failure;
        }
    }

    private void rollbackPartialPreparation(Exception failure) {
        if (fileClosed) {
            try {
                cache.reopenFile();
                fileClosed = false;
            } catch (Exception rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }

        if (writersPaused) {
            try {
                cache.resumeWriters();
                writersPaused = false;
            } catch (Exception rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }

        prepared = false;
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        cache.reopenFile();
        cache.resumeWriters();

        fileClosed = false;
        writersPaused = false;
        prepared = false;
    }

    public synchronized void rollbackAfterAbortedCheckpoint()
            throws Exception {
        if (!prepared && !fileClosed && !writersPaused) {
            return;
        }

        if (fileClosed) {
            cache.reopenFile();
            fileClosed = false;
        }

        if (writersPaused) {
            cache.resumeWriters();
            writersPaused = false;
        }

        prepared = false;
    }
}
~~~

LocalCache is only an illustrative class. In a real application, it should be replaced with the actual cache and file resource.

The example demonstrates three points:

1. The callback records changes after each successful operation.
2. If the callback itself fails, it rolls back the work already performed and then rethrows the original error.
3. If the callback has completed, but the checkpoint is aborted later, the coordinator calls rollbackAfterAbortedCheckpoint().

In a real implementation, the reopenFile() and resumeWriters() methods should be able to handle cases where the resource is already open or the workers are already running. If a rollback step fails, the unrecovered state must be preserved so it can be retried or transition the application to a not-ready state.

## 5. Rolling back when another Resource causes the checkpoint to fail

An important scenario is when resource A has run beforeCheckpoint() successfully, and then resource B throws an exception. Resource A does not automatically know that another callback caused the checkpoint to be aborted.

Resource only has two standard callbacks: beforeCheckpoint() and afterRestore(). The API does not provide a separate afterCheckpointAborted() callback to notify every resource that the checkpoint was aborted.

When the application invokes a checkpoint via Core.checkpointRestore(), the coordinator can catch CheckpointException and then explicitly invoke the rollback operation on the components that participated in preparation.

### Defining the participant

~~~java
public interface CheckpointParticipant {
    void rollbackAfterAbortedCheckpoint() throws Exception;
}
~~~

Each component implements this interface alongside Resource. The rollback method needs to check its internal state and only restore changes that were actually made.

### Checkpoint coordinator

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.crac.CheckpointException;
import org.crac.Core;
import org.crac.RestoreException;

public final class CheckpointCoordinator {
    private final List<CheckpointParticipant> participants;

    public CheckpointCoordinator(
            List<CheckpointParticipant> participants) {
        this.participants = new ArrayList<>(participants);
    }

    public void checkpoint() throws Exception {
        try {
            Core.checkpointRestore();

            // Continue here only after restore succeeds.
            resumeNormalTraffic();

        } catch (CheckpointException checkpointFailure) {
            rollbackPreparedComponents(checkpointFailure);
            throw checkpointFailure;

        } catch (RestoreException restoreFailure) {
            // In the restored instance.
            // This is a post-restore initialization error, not an aborted checkpoint.
            markApplicationNotReady(restoreFailure);
            throw restoreFailure;
        }
    }

    private void rollbackPreparedComponents(
            CheckpointException originalFailure) {

        List<CheckpointParticipant> reverse =
                new ArrayList<>(participants);

        Collections.reverse(reverse);

        for (CheckpointParticipant participant : reverse) {
            try {
                participant.rollbackAfterAbortedCheckpoint();
            } catch (Exception rollbackFailure) {
                originalFailure.addSuppressed(rollbackFailure);
            }
        }
    }

    private void resumeNormalTraffic() {
        // Reopen request acceptance after restore succeeds.
    }

    private void markApplicationNotReady(Exception failure) {
        // Record the restore error and keep the application in a not-ready state.
    }
}
~~~

The participants list should contain components that may modify state in beforeCheckpoint(). Rollback methods must be safe when called on components that have not yet prepared or have already rolled themselves back.

In a real application, request acceptance state should be coordinated with the coordinator. For example, before calling Core.checkpointRestore(), the system switches to drain mode; upon receiving CheckpointException, the coordinator rolls back resources and only reopens traffic when all required components have recovered.

### Why roll back in reverse order?

Suppose components are prepared in the order:

~~~text
1. DatabasePool.pauseAndClose()
2. Repository.flushAndPause()
3. RequestHandler.stopAccepting()
~~~

If the checkpoint is aborted, it may be necessary to restore in reverse order:

~~~text
1. RequestHandler.startAccepting()
2. Repository.resume()
3. DatabasePool.reopenAndResume()
~~~

However, the example above is only valid if RequestHandler and Repository do not start processing before the database is ready. In many systems, the actual recovery order should be database, repository, and then request handler. The rule to follow is to restore dependencies before consumers, rather than mechanically applying a fixed order.

Clearly describe the dependency relationships between components and choose a rollback order so that a reopened component only uses dependencies that are already ready.

## 6. Handling checkpoint errors and restore errors separately

CheckpointException and RestoreException represent two different situations.

### CheckpointException

CheckpointException is thrown when a checkpoint does not succeed, such as an error in a checkpoint notification callback or an error during image creation. Execution continues in the original Java instance.

The application needs to:

1. Log the cause of the checkpoint failure.
2. Check which components transitioned to PREPARED.
3. Call rollback on those components.
4. Collect any errors that occur during rollback.
5. Reopen traffic only when the application state has been restored.

CheckpointException may contain suppressed exceptions. They often provide details about the callback or resource that caused the error. Do not log only the top-level message and ignore the suppressed part.

Example:

~~~java
try {
    Core.checkpointRestore();
} catch (CheckpointException e) {
    logger.error("Checkpoint failed", e);

    for (Throwable suppressed : e.getSuppressed()) {
        logger.error("Checkpoint preparation detail", suppressed);
    }

    rollbackComponents();
    throw e;
}
~~~

If a component cannot roll back, the application should not pretend that it is ready. It can stay in maintenance mode, retry recovery according to a retry policy, or terminate the process so the monitoring system restarts it.

### RestoreException

RestoreException occurs when the restore notification process encounters an error. At this point, the process has already been restored into a new instance. This is not an aborted checkpoint in the original instance.

Do not run rollbackAfterAbortedCheckpoint() as if the checkpoint had never occurred. Instead:

- Identify which resource failed to initialize.
- Keep the application in a not-ready state.
- Attempt to recreate the resource if the operation can be safely retried.
- Do not accept requests that depend on the failing resource.
- Log the cause and forward the error to the monitoring mechanism or the application's shutdown policy.

If a resource needs a database, but afterRestore() cannot connect to the database, opening the listener before the connection pool is ready may cause requests to fail en masse.

### UnsupportedOperationException

If the CRaC API is called on a runtime that does not support checkpoint/restore, UnsupportedOperationException may be received. This case differs from a checkpoint being aborted after preparation has started. The application should check the runtime configuration and not let components transition to the PREPARED state before knowing the request can be executed.

## 7. When the checkpoint request comes from jcmd

A checkpoint can be requested externally using:

~~~bash
jcmd <pid> JDK.checkpoint
~~~

When using jcmd, the request is sent to the running JVM. The application's Java code does not directly call Core.checkpointRestore() at a location that can be wrapped in a try/catch. Therefore, the application cannot rely on a catch CheckpointException block in the business flow to automatically roll back an external jcmd command.

This is a point to consider when designing operational procedures.

If rollback after an aborted checkpoint is mandatory, the application should coordinate the request through an internal administrative endpoint or mechanism, and then call Core.checkpointRestore() within the application's control flow. The coordinator can catch CheckpointException and restore the participants.

If an organization still needs to use jcmd directly, callbacks should be designed so that preparation can be safely recovered, and there should be a separate administrative procedure to bring the application back to a serving state after a failed checkpoint. Do not assume that CRaC will call afterRestore() when a checkpoint is aborted.

Some jcmd implementations may return a message indicating the command was executed even when a checkpoint error is logged in the application console. Therefore, do not rely solely on jcmd output to determine checkpoint success. Observe JVM logs and application state according to the documentation of the JDK distribution in use.

## 8. Managing callback order and resource dependencies

Resource registration order affects callback order. In common CRaC implementations, beforeCheckpoint() is called in registration order; afterRestore() is called in reverse order. Check the documentation of the runtime in use.

Example:

~~~java
Core.getGlobalContext().register(databaseResource);
Core.getGlobalContext().register(cacheResource);
Core.getGlobalContext().register(serverResource);
~~~

Preparation order:

~~~text
databaseResource.beforeCheckpoint()
cacheResource.beforeCheckpoint()
serverResource.beforeCheckpoint()
~~~

Post-restore recovery order:

~~~text
serverResource.afterRestore()
cacheResource.afterRestore()
databaseResource.afterRestore()
~~~

Do not choose registration order based solely on component names. Determine actual dependencies. If the server needs the cache and database to operate, the server should only reopen traffic after its dependencies are ready.

For an aborted checkpoint, the application coordinator may need a separate rollback order. This order must be based on dependency relationships and changed state, not by calling afterRestore() across the board.

### Register once and keep state consistent

Resources are usually registered during component initialization. Avoid creating and registering new resources on every checkpoint unless there is a corresponding lifecycle management mechanism.

Ensure that:

- Each component has a canonical state to determine whether it is active or prepared.
- Registration is not unintentionally duplicated.
- Rollback and afterRestore() can distinguish the current state.
- Components do not serve requests while dependencies are still closed.
- Logs show the callback order to easily locate the failing component.

## 9. Testing aborted checkpoint scenarios

Do not test only the happy path. Actively inject errors at different stages to verify that the application restores state properly.

### Testing a callback failing on its own

Have a Resource throw an exception after pausing workers but before finishing closing resources.

Expected results:

- The Resource rolls back the work it has done.
- Workers resume operation or transition to a controlled error state.
- The original exception is still reported to the coordinator.
- The application does not reopen traffic before the component is ready.

### Testing another Resource failing

Have Resource A prepare successfully, then Resource B throw an exception.

Expected results:

- The checkpoint is aborted.
- Core.checkpointRestore() throws CheckpointException.
- The application continues in the original instance.
- The coordinator calls rollback for A.
- A restores its resources and serving state.
- No checkpoint image is considered valid for that request.

### Testing an error in the native checkpoint engine

Have the checkpoint engine fail after application callbacks have completed.

Expected results:

- The error is recognized as a checkpoint failure.
- Components in the PREPARED state are rolled back.
- The original application returns to operational state or switches to maintenance if rollback fails.
- Logs distinguish between callback errors and engine errors.

### Testing a post-restore error

Have a Resource throw an exception in afterRestore().

Expected results:

- The error is distinguished from CheckpointException.
- The application does not run aborted-checkpoint rollback logic.
- The restored instance is kept in a not-ready state.
- The failing component is retried or reported so the monitoring system can handle it.

### Testing repeated rollback

Call rollback twice on the same participant.

Expected results:

- The second call does not close/open resources in the wrong state.
- No duplicate threads or connections are created.
- The final state remains consistent.

## 10. Logging and observing the recovery process

When a checkpoint is aborted, logs need enough information to determine the state of each component.

Record:

- Resource name and checkpoint attempt identifier.
- Start and end timestamps of beforeCheckpoint().
- State before preparation.
- Completed operations, such as pausing workers, flushing buffers, closing connections.
- Cause of the checkpoint failure.
- Start and end timestamps of rollback.
- Rollback errors and suppressed exceptions.
- Final state: READY, MAINTENANCE, or FAILED.

Do not log just a single line “checkpoint failed”. If the application has resumed running while the listener is still closed, component state information is what helps find the actual root cause.

Metrics that can be tracked:

| Metric | Meaning |
|---|---|
| checkpoint_attempt_total | Total number of checkpoint requests |
| checkpoint_failure_total | Number of failed checkpoints |
| checkpoint_prepare_duration | Resource preparation duration |
| checkpoint_rollback_duration | Recovery duration after abort |
| checkpoint_rollback_failure_total | Number of unsuccessful rollbacks |
| component_ready | Whether the component is ready to serve |

Avoid logging credentials, tokens, personal data, or sensitive content. Use resource identifiers and error codes to correlate events within the same cycle.

## 11. Common design mistakes

**Recovering only in afterRestore():** an aborted checkpoint does not produce a restore, so the original process may continue with closed or paused resources.

**Not recording step-by-step state:** a callback failing midway leaves the application unaware of what was performed and needs to be rolled back.

**Non-idempotent rollback:** calling recovery twice can create duplicate connections, open files multiple times, or start multiple workers.

**Wrong rollback order:** opening a consumer before its dependency causes requests to access unready resources.

**Ignoring rollback errors:** the checkpoint failure was recorded, but the component remains in an error state. The application then reopens traffic and causes cascading errors.

**Using jcmd while expecting a catch in Java code:** the jcmd command comes from outside and does not run inside a business-flow try/catch block. If controlled rollback is needed, use a coordinator that calls the CRaC API inside the application.

**Confusing CheckpointException with RestoreException:** an aborted checkpoint requires rollback on the old instance; a failed restore notification requires recovery on the new instance.

## 12. Implementation principles

- Treat beforeCheckpoint() as a preparation phase that can fail.
- Roll back local changes if a component's callback fails midway.
- For checkpoints requested via Core.checkpointRestore(), catch CheckpointException and roll back all prepared participants.
- Do not wait for afterRestore() to recover when a checkpoint is aborted.
- Distinguish CheckpointException, RestoreException, and UnsupportedOperationException.
- Design idempotent rollback and record step-by-step state.
- Restore dependencies before consumers and reopen traffic only when all required components are READY.
- If rollback fails, keep the application in a not-ready state and report the error to the monitoring system.
- If using jcmd directly, design an appropriate administrative procedure because the application cannot catch that exception in the API call flow.
- Test callback errors, engine errors, restore errors, and repeated rollbacks.

The ability to recover after an aborted checkpoint is part of CRaC resource design. Each component needs to know what it has changed, how it can undo those changes, and when it is allowed to operate again. When the coordinator clearly distinguishes the failed checkpoint branch from the successful restore branch, the application can continue safely even when a checkpoint request fails to create an image.