# CheckpointException, RestoreException, and Aggregated Exceptions

In CRaC, a single checkpoint or restore operation can invoke multiple resource callbacks. Each resource can encounter its own error: failing to close a file, failing to flush data, a connection that cannot be reopened, or a native library that fails to restore its state. If only the first error were kept, the remaining errors would be hidden and diagnosis would become difficult.

CRaC uses two aggregate exceptions: **CheckpointException** and **RestoreException**. Errors arising from callbacks are attached to the aggregate exception as *suppressed exceptions*. Therefore, when handling CRaC errors, you need to read the entire list of suppressed exceptions instead of only looking at the message or cause of the outermost exception.

This lesson explains when each exception appears, how CRaC aggregates multiple errors, how to read the exception tree, and how to write resource callbacks so that errors are reported completely while the application still recovers to the right state.

## 1. Two Exceptions Representing Two Phases

The CRaC API has two main callbacks on the Resource interface:

- **beforeCheckpoint(Context)**: notifies the resource that the process is about to be checkpointed. The resource prepares its state and releases resources that should not be kept in the image.
- **afterRestore(Context)**: notifies that the process has just been restored. The resource recreates the handles and connections needed for the application to continue.

If a callback throws an exception, the global Context collects the error and propagates the result back to the caller that requested checkpoint/restore.

| Exception | Phase with error | Operational meaning |
|---|---|---|
| CheckpointException | Before-checkpoint notification failed, or checkpoint preparation had an error | No checkpoint image was created; the application continues in the original Java process after recovery callbacks are run |
| RestoreException | After-restore notification failed | The image was used to create a new process, but one or more resources failed to recover |
| UnsupportedOperationException | The runtime does not support checkpoint/restore service | No callbacks were executed; the checkpoint request is not supported |

The first two exceptions are aggregate exceptions, inheriting from **Exception**. They do not represent a specific business error like IOException or SQLException. The detailed information lies in the suppressed exceptions inside.

### 1.1 CheckpointException

CheckpointException is thrown when the checkpoint notification of the global Context finishes with errors. One or more resources may have thrown an exception during beforeCheckpoint.

Examples:

- A FileChannel cannot be closed.
- A buffer cannot be flushed to a file.
- An HTTP server cannot stop its listener.
- A connection pool cannot complete its shutdown operation.
- A resource detects that the application state is not yet safe and intentionally throws an exception.

When the global Context handles a callback error, it still continues notifying the remaining resources according to the Context's policy. Afterward, the errors are added to CheckpointException as suppressed exceptions.

If the checkpoint notification fails, the image is not created. CRaC then invokes the after-restore notification in the original Java process so that resources have a chance to reopen what was closed during preparation. If these recovery callbacks also fail, their errors are added to the same CheckpointException.

Therefore, a single CheckpointException can contain both errors from beforeCheckpoint and errors from afterRestore invoked to recover the original process. This is why you should not read only the first exception and conclude the entire issue.

### 1.2 RestoreException

RestoreException occurs when checkpointing has passed the preparation phase and a new process has been created from the image, but one or more afterRestore callbacks fail.

Examples:

- A configuration file no longer exists at the saved path.
- The database rejects new connections.
- A socket cannot reconnect to a remote service.
- A certificate or credential has expired.
- A native library cannot recreate a handle.
- A required cache cannot be reloaded.

In this case, the new process has been restored, but the application's recovery state is incomplete. You should not assume that the application can receive traffic just because the JVM has resumed running from the image.

If checkpointing was invoked via Core.checkpointRestore(), RestoreException is propagated to the calling code in the new process. The application needs to keep readiness in a not-ready state, log the detailed errors, and execute a recovery policy or stop startup according to operational requirements.

## 2. Why Does CRaC Aggregate Multiple Exceptions?

An application can register multiple Resources with the global Context. Each Resource manages its own piece of state: a file, socket, database pool, scheduler, message consumer, or a native library.

Suppose an application has three resources:

- Resource A closes the log file.
- Resource B stops the HTTP listener.
- Resource C closes the connection pool.

When checkpointing begins, A may close its file successfully, B may fail to stop the listener, and C still needs to be notified to close the pool. If the Context stopped immediately at the first error, C might continue holding resources while the checkpoint is being prepared.

CRaC's global Context has important behaviors:

1. Every registered Resource still receives the notification, even if another Resource has already thrown an exception.
2. Exceptions from callbacks are caught by the Context and placed into an aggregate exception.
3. Errors are stored as suppressed exceptions.
4. Restore notifications are also executed for Resources according to the Context's rules, even if another callback has failed.

As a result, a single run can report multiple independent errors. Operators can fix all root causes in one diagnostic cycle instead of dealing with errors appearing one after another.

These ordering and collection guarantees describe the global Context. A custom Context may define its own notification policy; when using a custom Context, you should read the contract of that specific Context.

### 2.1 Notification Order of the Global Context

The global Context invokes checkpoint callbacks in the reverse order of Resource registration. Restore callbacks run in the opposite order, i.e., in the order of registration.

For example, if you register A, then B, then C:

~~~text
Registration:       A -> B -> C
beforeCheckpoint:   C -> B -> A
afterRestore:       A -> B -> C
~~~

The reverse invocation order helps the application close components in one order and reopen them in the reverse order. For example, if the server depends on the connection pool, resources can be registered so that the server stops before the pool closes and the pool reopens before the server starts operating.

The callback order does not change the error aggregation principle: one failing callback does not mean the remaining callbacks will be skipped.

## 3. What Is a Suppressed Exception?

Java has two common mechanisms for linking exceptions:

- **Cause:** an exception created because of another exception; accessed via getCause().
- **Suppressed exception:** a secondary exception attached alongside a primary exception; accessed via getSuppressed().

CRaC uses suppressed exceptions for errors from multiple Resource callbacks. The outermost exception acts as an aggregate container, while each actual error resides in the array returned by getSuppressed().

Example structure:

~~~text
CheckpointException
  Suppressed: IOException
    Message: Cannot flush application log
  Suppressed: SQLException
    Message: Connection pool shutdown failed
  Suppressed: IllegalStateException
    Message: HTTP listener is still active
~~~

Restore example:

~~~text
RestoreException
  Suppressed: IOException
    Message: Configuration file is missing
  Suppressed: SQLException
    Message: Database authentication failed
~~~

In current CRaC APIs, CheckpointException and RestoreException are aggregate exceptions without their own message, cause, or stack trace. Therefore:

- getMessage() on the outermost exception may return null.
- getCause() on the outermost exception may return null.
- getStackTrace() of the outermost exception does not contain the stack trace of each callback.
- getSuppressed() is where the errors to investigate are located.

You should not conclude that there is no error just because the message or cause of the outermost exception is empty.

### 3.1 Reading the First Error and All Errors

The following code prints all direct suppressed exceptions:

~~~java
static void printSuppressed(Throwable aggregate) {
    Throwable[] failures = aggregate.getSuppressed();

    System.err.println(
            aggregate.getClass().getSimpleName()
            + " contains " + failures.length + " failure(s)");

    for (int i = 0; i < failures.length; i++) {
        System.err.println("Failure #" + (i + 1));
        failures[i].printStackTrace(System.err);
    }
}
~~~

Call this method in catch:

~~~java
try {
    Core.checkpointRestore();
} catch (CheckpointException e) {
    printSuppressed(e);
} catch (RestoreException e) {
    printSuppressed(e);
}
~~~

Calling printStackTrace() on each error lets you see the original stack trace, cause, and any nested suppressed exceptions inside that error.

A callback exception can itself contain suppressed exceptions. For example, when closing multiple resources with try-with-resources, Java can keep secondary close errors inside the primary exception. Thus, the exception tree can be deeper than one level.

### 3.2 Printing the Entire Cause and Suppressed Tree

When structured logging is needed, you can traverse both cause and suppressed exceptions. Use an identity set to avoid duplicate printing if the same Throwable object is referenced from multiple branches.

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

static void printThrowableTree(Throwable error) {
    Set<Throwable> visited =
            Collections.newSetFromMap(new IdentityHashMap<>());
    printThrowableTree(error, "", visited);
}

private static void printThrowableTree(
        Throwable error,
        String indent,
        Set<Throwable> visited) {

    if (error == null || !visited.add(error)) {
        return;
    }

    System.err.println(
            indent + error.getClass().getName()
            + ": " + error.getMessage());

    if (error.getCause() != null) {
        System.err.println(indent + "Caused by:");
        printThrowableTree(
                error.getCause(), indent + "  ", visited);
    }

    for (Throwable suppressed : error.getSuppressed()) {
        System.err.println(indent + "Suppressed:");
        printThrowableTree(
                suppressed, indent + "  ", visited);
    }
}
~~~

This traversal is useful when the logging system needs to separate each error into its own field or send the exception tree to an observability tool. If you only need standard diagnostic logs, printStackTrace() already displays cause and suppressed exceptions in a structured manner.

## 4. Distinguishing Checkpoint Errors and Restore Errors in the Same Call

When an application calls Core.checkpointRestore(), the success flow can be visualized as follows:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Core as CRaC Core
    participant Ctx as Global Context
    participant Image as Checkpoint Engine

    App->>Core: checkpointRestore()
    Core->>Ctx: beforeCheckpoint
    Ctx-->>Core: No error
    Core->>Image: Create checkpoint image
    Image-->>Core: Image created
    Note over App,Image: Old process terminates
    Image->>Core: Initialize process from image
    Core->>Ctx: afterRestore
    Ctx-->>Core: No error
    Core-->>App: Continue after checkpointRestore()
~~~

In the success flow, code after the checkpointRestore() call runs in the new process after restore completes.

If beforeCheckpoint fails, a different flow occurs:

~~~mermaid
sequenceDiagram
    participant App as Original JVM
    participant Ctx as Global Context
    participant Engine as Checkpoint Engine

    App->>Ctx: beforeCheckpoint
    Ctx->>Ctx: Invoke Resource callbacks
    Ctx-->>App: CheckpointException
    Note over App,Engine: No image created
    App->>Ctx: afterRestore on original process
    Ctx->>Ctx: Attempt to recover modified Resources
    Ctx-->>App: Recovery results aggregated into CheckpointException
    App->>App: Catch CheckpointException
~~~

Important point: when the checkpoint notification fails, CRaC runs the restore notification directly in the original process so that resources have a chance to return to an operational state. This is a lifecycle recovery step, not a general transaction rollback. Side effects that have already occurred in external systems are not automatically undone.

Therefore, CheckpointException may contain:

- Errors from one or more beforeCheckpoint callbacks.
- Errors from one or more afterRestore callbacks invoked to recover the original process.

If the checkpoint notification succeeds and the image is created, but an afterRestore callback in the new process fails, the errors are aggregated in RestoreException.

## 5. Catching Exceptions from Core.checkpointRestore()

The example below illustrates how to branch by exception type:

~~~java
import org.crac.CheckpointException;
import org.crac.Core;
import org.crac.RestoreException;

public final class CheckpointCoordinator {

    public void checkpoint() {
        try {
            Core.checkpointRestore();

            // Only continues in the successfully restored process.
            System.out.println("Restore completed");

        } catch (CheckpointException e) {
            System.err.println(
                    "Checkpoint preparation failed in original JVM");
            printThrowableTree(e);

            // No new image was created.
            // Verify that resources have been recovered to a usable state.

        } catch (RestoreException e) {
            System.err.println(
                    "One or more resources failed after restore");
            printThrowableTree(e);

            // In the new process, but resources have not fully recovered.
            // Do not open readiness to serve traffic in this state.

        } catch (UnsupportedOperationException e) {
            System.err.println(
                    "Checkpoint/restore is not supported by this runtime");
            e.printStackTrace(System.err);
        }
    }

    private static void printThrowableTree(Throwable error) {
        System.err.println(error.getClass().getName());

        for (Throwable failure : error.getSuppressed()) {
            failure.printStackTrace(System.err);
        }
    }
}
~~~

The example uses the **org.crac** package. If the application uses the API built into the JDK, import the corresponding classes from **jdk.crac**. Do not mix classes from the two packages in the same Resource system because they are different Java types.

Three cases to remember:

1. **No exception:** checkpoint and restore complete; the call returns in the restored process.
2. **CheckpointException:** checkpoint failed to create an image; the application continues in the original process after the recovery notification procedure.
3. **RestoreException:** the image was restored into a new process, but there were errors in the afterRestore callbacks.

UnsupportedOperationException is a separate case: the runtime does not support the operation and performs no notifications. Do not treat it as a CheckpointException with suppressed callback failures.

If checkpointing is triggered externally via jcmd, an HTTP endpoint, or a controller, the code calling Core.checkpointRestore() may not be where the request originated. In that case, the exception is not necessarily returned to the client sending the command. Check the target JVM logs and the output from the checkpoint engine to see the detailed errors.

## 6. Designing Resource Callbacks to Avoid Losing Errors

The global Context aggregates exceptions across different Resources. However, within a single Resource, developers must still ensure that independent cleanup steps are attempted.

For example, a Resource manages three components: a file, a socket, and a scheduler. If closing the file fails and the callback immediately throws an exception, the socket and scheduler might not be closed. The Context cannot know on its own about the remaining internal steps of a Resource.

You can collect errors inside the callback and then throw a primary exception with secondary suppressed exceptions attached:

~~~java
import java.io.IOException;
import org.crac.Context;
import org.crac.Resource;

public final class CompositeResource implements Resource {

    private final LogFile logFile;
    private final ClientSocket socket;
    private final WorkerScheduler scheduler;

    public CompositeResource(
            LogFile logFile,
            ClientSocket socket,
            WorkerScheduler scheduler) {
        this.logFile = logFile;
        this.socket = socket;
        this.scheduler = scheduler;
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        Exception failure = null;

        try {
            scheduler.stopAndWait();
        } catch (Exception e) {
            failure = append(failure, e);
        }

        try {
            socket.close();
        } catch (Exception e) {
            failure = append(failure, e);
        }

        try {
            logFile.flushAndClose();
        } catch (Exception e) {
            failure = append(failure, e);
        }

        if (failure != null) {
            throw failure;
        }
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Recreate components in dependency order.
    }

    private static Exception append(
            Exception primary,
            Exception next) {
        if (primary == null) {
            return next;
        }

        primary.addSuppressed(next);
        return primary;
    }
}
~~~

In this example, the callback attempts all three operations. The first error becomes the primary exception; subsequent errors are attached to it. When the callback throws the exception outward, the global Context continues aggregating that exception into CheckpointException.

The log structure can have multiple levels:

~~~text
CheckpointException
  Suppressed: IOException: Scheduler stop failed
    Suppressed: TimeoutException: Worker did not terminate
  Suppressed: IOException: Socket close failed
  Suppressed: IOException: Log flush failed
~~~

Aggregating errors inside a Resource is useful when a component manages multiple independent handles. If an operation depends on a previous one, you should stop that specific chain when a prerequisite fails; do not continue an operation that could make the state worse.

### 6.1 Do Not Swallow Exceptions

A common mistake is catching an exception and only logging it:

~~~java
@Override
public void beforeCheckpoint(
        Context<? extends Resource> context) {
    try {
        closeSocket();
    } catch (Exception e) {
        logger.error("Could not close socket", e);
    }
}
~~~

The callback above returns normally even though the socket was not closed. The Context may consider this notification successful and proceed with the checkpoint. If the socket is a resource that must be released, this behavior hides the error.

Log if needed, but then you must throw the exception so CRaC knows the callback failed:

~~~java
@Override
public void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {
    try {
        closeSocket();
    } catch (Exception e) {
        logger.error("Could not close socket", e);
        throw e;
    }
}
~~~

There is no need to log at every layer if the logger already prints the exception tree at the coordination layer. Repeatedly logging the same stack trace in each Resource can clutter the logs. Choose one place to log the full exception tree, while Resources add necessary context such as resource name, handle type, and failed operation.

## 7. Recovering When Checkpoint Fails

When a beforeCheckpoint callback fails, CRaC does not create an image and the original process continues. However, other Resources may have already closed successfully before the error was detected.

For example:

- The scheduler has stopped.
- The socket has closed.
- The log file failed to close.
- Another resource has stopped its consumer.

After the error, the restore notification is invoked so that Resources have a chance to reopen resources and resume operation. Therefore, afterRestore must be designed to handle states where beforeCheckpoint only partially completed.

### 7.1 Recovery Callbacks Must Be Idempotent

A Resource may have closed no resources, closed partially, or closed completely when the checkpoint notification fails. The afterRestore callback should not assume that all beforeCheckpoint operations succeeded.

Store the lifecycle state of the Resource itself:

~~~java
public final class ManagedFileResource implements Resource {

    private FileChannel channel;
    private boolean reopenRequired;

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        if (channel != null && channel.isOpen()) {
            try {
                channel.close();
            } finally {
                if (!channel.isOpen()) {
                    channel = null;
                    reopenRequired = true;
                }
            }
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {

        if (reopenRequired) {
            FileChannel reopened = openChannel();
            channel = reopened;
            reopenRequired = false;
        }
    }

    private FileChannel openChannel() throws IOException {
        return FileChannel.open(
                Path.of("application.log"),
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND);
    }
}
~~~

This is an illustrative example. In a real application, you need to declare imports and define specific file policies. The main point is to mark recovery as complete only after opening the resource succeeds. If openChannel() fails, reopenRequired remains true so the error is reported and subsequent handling still knows the resource needs to be opened.

### 7.2 Do Not Assume afterRestore Only Runs After an Image Exists

The callback name may lead readers to think it only runs in a new process. With the global Context, when the checkpoint notification fails, the restore notification is still invoked in the original process to recover modified resources.

Therefore, afterRestore should be understood as the callback that brings the resource back to its post-checkpoint-phase state, and should not rely on the assumption that the PID or process has changed.

### 7.3 Recovery Is Not Business Rollback

If beforeCheckpoint sends a command to an external system and then fails in the next step, CRaC does not automatically undo that command. Similarly, reopening a socket does not revert a message already processed by a server or a transaction already committed.

For external side effects, you need transactions, idempotency keys, message acknowledgments, or compensating mechanisms at the business layer. Callbacks only manage the resource lifecycle and state necessary for the process to continue.

## 8. Handling RestoreException and Application Readiness

RestoreException means that a new process has been created, but at least one recovery callback failed. This is a state that must be handled carefully because some components may be operational while others are not yet ready.

For example, the database pool has reopened, but the message consumer has failed to connect. If the application opens readiness immediately, traffic may enter while the consumer or a critical dependency has not yet recovered.

A recovery policy may include:

1. Keeping readiness at false.
2. Logging the full exception tree along with the checkpoint ID and instance ID.
3. Categorizing errors by resource and dependency.
4. Retrying with backoff if the error is recoverable and the reopen operation is safe.
5. Enabling readiness only after all essential dependencies have been verified.
6. If the retry deadline expires, stopping the instance or letting the orchestrator start a new instance according to the deployment policy.

You should not catch RestoreException and continue serving as if the restore succeeded. If a callback fails due to wrong credentials or a missing required file, infinite retries will not help. There must be timeouts, retry limits, and observable error states.

Some errors may not affect essential functionality. The application may allow continuing if that resource is truly optional, but this decision must be reflected in the readiness policy and clearly logged. Do not ignore an error just because the callback did not cause the process to stop immediately.

## 9. Classifying and Diagnosing Errors

When receiving a CheckpointException or RestoreException, you should investigate each suppressed exception individually.

### 9.1 Classifying by Callback

Read the stack trace to determine whether the error comes from:

- Which Resource's beforeCheckpoint.
- Which Resource's afterRestore.
- Application code or framework library.
- Java API or native library.
- I/O, network, database, or thread lifecycle operation.

A Resource should add context to the exception before throwing it, such as the resource name and the action being performed:

~~~java
try {
    closeConnectionPool();
} catch (SQLException e) {
    throw new IllegalStateException(
            "Resource database-pool failed to close before checkpoint",
            e);
}
~~~

The cause of this exception preserves the original SQLException. When the Context aggregates exceptions, the entire exception chain will reside under a suppressed exception of CheckpointException.

### 9.2 Classifying by Error Type

| Error group | Examples | Investigation direction |
|---|---|---|
| File system | File does not exist, permission denied, channel fails to close | Path, permissions, mount, ownership, and channel state |
| Network | Connection refused, timeout, DNS failure | DNS, route, peer, firewall, credentials, and timeout |
| Database | Pool shutdown or reconnect failed | Open transactions, stale sessions, credentials, database availability |
| Thread lifecycle | Worker does not stop, executor timeout | What the thread is running, interrupt policy, and drain deadline |
| Native resource | Native handle cannot be recreated | JNI/JNA, native library, system call, and runtime compatibility |
| Application state | Cache or subscription not recovered | Business state that needs saving and resynchronization steps |

### 9.3 Using Stack Traces Properly

When printing the aggregate exception, you should preserve the full stack trace and suppressed exceptions. Logging only the class name or message is usually not enough to locate where the resource was created.

For native errors or errors from the checkpoint engine, the Java stack trace may not pinpoint the exact cause. You need to combine runtime logs, checkpoint engine logs, and OS tools. The CRaC Debugging documentation describes an example of an open file descriptor error and how to enable stack trace collection options to find the source that created the FD.

### 9.4 Do Not Address Only the First Error

If a CheckpointException has five suppressed exceptions, fixing the first error and re-running the checkpoint may just expose the second and third errors. Record and group all errors in a single run, fix the independent root causes, and then retry.

If the errors have dependency relationships, handle them in order: the error preventing the resource from stopping, the cleanup error arising afterward, and then the recovery error. Preserve the cause and suppressed relationships so the original order and context are not lost.

## 10. Testing Exception Aggregation

Do not test only the happy path. You can create test Resources that intentionally throw exceptions to observe how the Context aggregates errors.

Example of a Resource that intentionally fails:

~~~java
public final class FailingResource implements Resource {

    private final String name;

    public FailingResource(String name) {
        this.name = name;
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        throw new IOException(
                name + ": simulated beforeCheckpoint failure");
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        throw new IOException(
                name + ": simulated afterRestore failure");
    }
}
~~~

Register multiple instances in a test environment:

~~~java
Context<? extends Resource> context = Core.getGlobalContext();

context.register(new FailingResource("resource-A"));
context.register(new FailingResource("resource-B"));
context.register(new FailingResource("resource-C"));
~~~

When requesting a checkpoint, verify:

- Whether Resources are invoked in the order of the global Context.
- Whether one failing callback prevents subsequent callbacks from being invoked.
- Whether CheckpointException contains the suppressed exceptions from all failing callbacks.
- If the checkpoint notification fails, whether afterRestore is invoked in the original process.
- Whether errors in afterRestore when recovering the original process are aggregated into CheckpointException.
- If the checkpoint notification succeeds but a restore callback fails, whether RestoreException contains all errors.

Do not run intentionally failing Resources in a production environment. Use a test runtime that supports CRaC and an environment where checkpoint images can be deleted after testing.

### 10.1 Scenario Matrix

| beforeCheckpoint | afterRestore | Expected result |
|---|---|---|
| All succeed | All succeed | Checkpoint and restore succeed |
| One callback fails | Recovery succeeds | CheckpointException; no new image |
| Multiple callbacks fail | Recovery succeeds | One CheckpointException containing multiple suppressed exceptions |
| One callback fails | One recovery callback also fails | CheckpointException containing errors from both notification phases |
| All succeed | One callback fails in the new process | RestoreException |
| All succeed | Multiple callbacks fail in the new process | RestoreException containing multiple suppressed exceptions |

Tests should verify both the error contents and the resource state after the callbacks complete. Simply counting exceptions is not enough; you must ensure resources are not left behind and readiness does not switch to true when essential errors remain.

## 11. Common Handling Mistakes

### Reading Only getMessage()

CheckpointException and RestoreException are aggregate exceptions with no message of their own. getMessage() may return null while there are multiple suppressed exceptions.

### Reading Only getCause()

CRaC does not use the cause of the outermost exception to store all callback failures. Read getSuppressed().

### Logging Only the Outermost Exception

The aggregate's stack trace does not replace the stack trace of each callback. Log all suppressed exceptions and causes to find the class, line of code, and resource causing the error.

### Throwing the First Exception and Skipping Remaining Cleanup

The global Context continues calling other Resources, but it cannot automatically perform the remaining cleanup operations inside the same Resource. Attempt all independent operations and aggregate errors before throwing.

### Catching and Ignoring Errors

If a callback returns normally after an essential operation fails, the Context does not know the resource is in an error state. Propagate the exception outward.

### Assuming CheckpointException Means Nothing Changed in the Process

Some Resources may have already closed their resources before another Resource failed. The restore notification will be called to recover, but that is not an automatic rollback for all side effects.

### Assuming RestoreException Means the JVM Was Not Restored

RestoreException reports errors in after-restore callbacks. The new process has been created, but the application state may be incomplete. Keep readiness false and handle the errors.

### Swallowing RestoreException and Opening Traffic

An essential resource that has not recovered can cause request failures, lost messages, or corrupted business state. Open readiness only after verifying required components.

### Letting Cleanup Errors Mask the Original Error

If a primary operation fails and the cleanup step also fails, keep the primary error as the main exception and attach the cleanup error using addSuppressed(). Do not replace the original exception with an error thrown in finally.

## 12. Error Handling Workflow in a CRaC Application

You can apply the following workflow when a checkpoint/restore attempt fails:

**Step 1 — Identify the outermost exception.** CheckpointException indicates the checkpoint notification phase failed; RestoreException indicates the restore notification phase failed.

**Step 2 — Collect all suppressed exceptions.** Iterate over getSuppressed(), print stack traces, and continue reading nested cause/suppressed exceptions.

**Step 3 — Identify the Resource and callback.** Use the Resource name, contextual message, and stack trace to find the failing operation.

**Step 4 — Classify the root cause.** Determine whether the error stems from a file, socket, database, thread, native handle, or business state.

**Step 5 — Check the post-error state.** For CheckpointException, verify that the original process has recovered its resources. For RestoreException, verify whether the new process can continue or must stop.

**Step 6 — Fix the root causes and retry.** Address all independent errors, test the callbacks, and perform checkpoint/restore again in an appropriate environment.

**Step 7 — Save operational traces.** Attach the checkpoint ID, instance ID, phase, resource name, and timestamp to logs for tracing across multiple attempts.

A diagnosable CRaC system needs to preserve original exceptions, aggregate sufficient errors from Resources, and report readiness status accurately reflecting recovery results. The two aggregate exceptions are not generic error messages; they are entry points for finding all errors in the checkpoint/restore lifecycle.

## References

- [CRaC API — Package summary](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/package-summary.html): describes the checkpoint/restore flow, suppressed exceptions, and global Context behavior.
- [CRaC API — CheckpointException](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/CheckpointException.html): aggregate exception for errors during the checkpoint phase.
- [CRaC API — RestoreException](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/RestoreException.html): aggregate exception for errors during the restore phase.
- [CRaC API — Core](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/Core.html): signature and outcomes of Core.checkpointRestore().
- [CRaC API — Resource](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/Resource.html): contract of beforeCheckpoint and afterRestore.
- [CRaC — Debugging failures](https://crac.org/reference/debugging/): suppressed exception examples and diagnosing file descriptor errors.
- [Java Throwable API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Throwable.html): getCause(), getSuppressed(), addSuppressed(), and printStackTrace().
