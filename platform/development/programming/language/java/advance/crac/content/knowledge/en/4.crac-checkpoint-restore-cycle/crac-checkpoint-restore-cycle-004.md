# Requesting a Checkpoint with jcmd and JDK.checkpoint

In CRaC (Coordinated Restore at Checkpoint), an application can save the process state at a point in time for fast restart by restoring the saved state. To initiate this operation, an operator can send a request from the outside using the `jcmd` tool with the `JDK.checkpoint` diagnostic command. Java code can also proactively request a checkpoint–restore cycle through the CRaC API.

The two triggering approaches share the same goal but sit in different places: `jcmd` sends a command to a running JVM, whereas the API lets the application choose the appropriate time itself within the business flow. Both require a CRaC JVM and a process to prepare resources before checkpointing.

## 1. What Is a Checkpoint Request?

A checkpoint records the state of a process so that it can be restored later. The saved state may include the heap, stack, thread state, and the parts of process state supported by the runtime and the checkpoint mechanism.

Checkpointing is not the same as the application already being restored. These are two separate phases:

1. **Checkpoint:** The JVM coordinates with registered resources, prepares the process, and creates a state image.
2. **Restore:** The runtime re-initializes the process from the saved image. The application continues from the restored state and completes resource reconnection steps.

The cycle can be visualized as follows:

~~~text
JVM serving requests
        |
        | Receives checkpoint request
        v
Run beforeCheckpoint callbacks
        |
        v
Complete preparation and save state
        |
        v
Checkpoint image is created
        |
        | Launch restore from image
        v
Restore process
        |
        v
Run afterRestore callbacks
        |
        v
Application continues operating
~~~

Creating a checkpoint is typically used to prepare a process that has already loaded classes, initialized frameworks, or completed some time-consuming startup steps. When a new instance needs to run, the system can restore from the prepared state instead of repeating the entire startup process.

Checkpointing is only safe when the application state and external resources have been handled appropriately. For example, a socket connected to a remote server, an open transaction, or a worker updating data may no longer be valid after restore. CRaC provides callbacks for the application to coordinate handling those situations.

## 2. Prerequisites Before Sending a Request

Before running a checkpoint command, verify that the environment meets the following conditions.

### A CRaC-Supported JVM

Not every JDK distribution supports CRaC. You must use a JDK build or configuration with CRaC support, matching the version and operating system on which the application will run.

You can check the JVM version with:

~~~bash
java -version
~~~

Then check the documentation of the JDK distribution you are using to learn how to enable CRaC, the JVM options, supported platforms, and system requirements. Some CRaC environments on Linux use CRIU (Checkpoint/Restore In Userspace) along with the corresponding permissions and kernel features.

### Checkpoint Storage Location Configured

The path to store the checkpoint image must be prepared before launching the JVM. For many CRaC JDK distributions, the commonly used option is:

~~~bash
-XX:CRaCCheckpointTo=/var/lib/myapp/checkpoint
~~~

Example of starting the application:

~~~bash
java \
  -XX:CRaCCheckpointTo=/var/lib/myapp/checkpoint \
  -jar app.jar
~~~

The path must exist or be creatable by the runtime as required by the JDK distribution, and the account running the JVM must have appropriate write permissions. You should check the guide for your specific JDK distribution because configuration and behavior may vary across vendors.

Do not store checkpoints in a temporary directory that may be cleaned up automatically. A checkpoint image can be large and contains the process's memory state, so you must plan for disk space, access permission restrictions, and retention policies.

### jcmd Can Attach to the Target JVM

`jcmd` is a JDK tool used to send diagnostic commands to a running Java process on the same machine. Typically, the user running `jcmd` needs permissions matching the account running the target JVM. Use the `jcmd` tool from a JDK compatible with the target JVM and check the attach rules of the operating system or container environment.

If running inside a container, ensure the command is executed in the right namespace and can see the JVM process. A PID visible from the host may differ from the PID inside the container.

## 3. Sending a Request with jcmd and JDK.checkpoint

`JDK.checkpoint` is the name of a diagnostic command of the CRaC JVM. An operator invokes this command through `jcmd`, passing in the PID of the process to checkpoint.

### Step 1: Find the Application's PID

List the Java processes that `jcmd` can detect:

~~~bash
jcmd -l
~~~

Example output:

~~~text
18420 app.jar
19215 org.example.Worker
~~~

In the example, the PID of `app.jar` is `18420`. Identify the exact process before sending the command. Do not reuse an old PID saved from a previous run because the operating system can reuse PIDs.

### Step 2: Check Available Commands

You can ask the JVM to list diagnostic commands:

~~~bash
jcmd 18420 help
~~~

If the JVM has `JDK.checkpoint` registered, view its specific help:

~~~bash
jcmd 18420 help JDK.checkpoint
~~~

The help command confirms that the command is supported by the runtime and displays the syntax or parameters if the JDK distribution provides them. Command names and options may depend on the CRaC distribution.

If `JDK.checkpoint` does not appear, recheck the running JDK, the `jcmd` tool being used, and the CRaC configuration. Do not assume that a regular Java JVM will have this command.

### Step 3: Send the Checkpoint Request

Once the right PID has been identified and the command is confirmed available, send:

~~~bash
jcmd 18420 JDK.checkpoint
~~~

`jcmd` sends the request to the target JVM. The CRaC JVM coordinates the checkpoint preparation process, including invoking the registered resource callbacks. When the operation completes, the checkpoint image is created at the runtime's configured location.

With a command invoked from the outside, the original process usually terminates after a successful checkpoint; using the image to run the process again is performed in the restore step. Check the command output, JVM logs, and checkpoint directory to confirm the actual operation. The return message of `jcmd` may vary across JDK distributions.

Do not send the command to a process serving critical transactions if the application does not yet have an appropriate drain or checkpoint preparation mechanism. Resource callbacks can close connections and clean up resources, but they do not automatically understand all of the application's business rules.

## 4. Requesting a Checkpoint from Java Code

In some situations, the application needs to decide when to checkpoint itself. For example, the application should only checkpoint after initialization completes, when there are no in-flight requests, or after transitioning into maintenance state.

CRaC provides an API in the `org.crac` package. The `Core.checkpointRestore()` method allows Java code to request a checkpoint–restore cycle:

~~~java
import org.crac.Core;

public final class CheckpointCoordinator {

    public void checkpointAtSafePoint() throws Exception {
        // The application has stopped accepting new work and finished processing in-flight work.
        Core.checkpointRestore();

        // When the process is successfully restored,
        // execution continues from the point after this call.
        resumeApplication();
    }

    private void resumeApplication() {
        // Re-enable workers or allow accepting new requests.
    }
}
~~~

This call belongs to the supported runtime's CRaC API. The application needs an API dependency compatible with the deployed JDK distribution and must run in an environment capable of checkpoint/restore.

The important point is that calling `checkpointRestore()` represents a checkpoint–restore cycle from the perspective of application code. When the process is restored, execution continues from the point after the call. If checkpointing or restoring fails, the error is reported back to the application via an API exception or a related runtime error; the application needs an appropriate handling policy.

Do not call the API at an arbitrary location just because you want to save state. Place the call at a point where the application can guarantee that in-flight work has been completed or safely paused.

### Distinguishing JDK.checkpoint and Core.checkpointRestore()

| Criterion | jcmd with JDK.checkpoint | Core.checkpointRestore() |
|---|---|---|
| Where the request originates | Outside the JVM | Inside Java code |
| Triggering person or component | Operator, script, or management tool | Application logic |
| Target receiving the request | JVM specified by PID | JVM executing the call |
| Purpose | Command a running process to checkpoint | Proactively coordinate the checkpoint–restore cycle from the application |
| Where execution resumes | The process is restarted from the checkpoint according to the runtime's restore method | After the API call when the process is restored |
| Resource preparation | JVM invokes registered CRaC callbacks | JVM invokes registered CRaC callbacks |

`JDK.checkpoint` is the name of a diagnostic command sent via `jcmd`, not a public Java method named `JDK.checkpoint()`. When writing application code, use the CRaC API such as `Core.checkpointRestore()` according to the runtime's documentation.

## 5. Preparing Resources Before Checkpoint

A checkpoint request is only the signal to start the process. The application needs to register resources to close, release, or save the state of external resources before the process image is created and restore them after restore.

CRaC defines the `Resource` interface with two main callbacks:

- `beforeCheckpoint()`: runs before the process is checkpointed. Used to stop accepting work, finish running tasks, and release resources that need to be recreated.
- `afterRestore()`: runs after the process is restored. Used to recreate connections, reopen resources, and resume service.

Example of a resource managing a connection to an external system:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class RemoteClientResource implements Resource {
    private RemoteClient client;

    public RemoteClientResource() {
        client = createClient();
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        stopAcceptingRequests();
        waitForInFlightRequests();
        client.close();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        client = createClient();
        resumeAcceptingRequests();
    }

    private RemoteClient createClient() {
        return new RemoteClient();
    }

    private void stopAcceptingRequests() {
        // Transition the application into a paused state.
    }

    private void waitForInFlightRequests() throws Exception {
        // Wait for in-flight requests to finish with a timeout.
    }

    private void resumeAcceptingRequests() {
        // Re-enable accepting requests.
    }
}
~~~

`RemoteClient`, how the client is created, and the coordination methods in the example are illustrative and must be replaced with actual classes. The resource is registered with the global context so the JVM knows to invoke the callbacks during the CRaC cycle.

### What Typically Needs to Be Done in beforeCheckpoint()

Depending on the type of application, the pre-checkpoint callback may need to:

1. Stop accepting new requests or tasks.
2. Wait for running requests to complete or cancel them according to application policy.
3. Flush buffers and complete any necessary data writes.
4. Commit or roll back open transactions.
5. Close network connections, connection pools, or clients whose session state cannot be reused after restore.
6. Stop scheduled jobs if those schedules need to be re-initialized.
7. Release file handles, native handles, or environment-dependent resources.

Do not wait indefinitely in a callback. An unresponsive external service can cause the checkpoint to hang. Use timeouts, clearly log the resource being waited on, and decide whether to abort the checkpoint or report an error when the application cannot be brought into a safe state.

### What Typically Needs to Be Done in afterRestore()

After restore, the application needs to check or recreate resources whose lifecycle is tied to the operating system or external services:

- Create new network connections.
- Re-initialize clients and connection pools.
- Re-read endpoint or credential information if they may have changed.
- Restart workers and scheduled tasks.
- Check the status of dependent services before reopening traffic.

Do not assume that sockets, database connections, or authentication sessions stored in memory will always remain valid after restore. Follow the guidelines of the respective libraries and services.

If a resource's callback fails, the checkpoint or restore may not complete as intended. Log thoroughly, release resources as much as possible, and clearly determine whether the application can continue running or must stop.

## 6. Sample Workflow from Launch to Restore

The example below describes how to configure the checkpoint directory and send a request from `jcmd`. CRaC options may vary by JDK vendor, so cross-check with the actual runtime.

### Launching the Application

Prepare the directory and access permissions:

~~~bash
mkdir -p /var/lib/myapp/checkpoint
~~~

Launch the JVM with the checkpoint storage location:

~~~bash
java \
  -XX:CRaCCheckpointTo=/var/lib/myapp/checkpoint \
  -jar app.jar
~~~

The application finishes starting up and registers the necessary `Resource` instances. After confirming the application is in a checkpointable state, find the PID:

~~~bash
jcmd -l
~~~

### Sending the Checkpoint Command

Suppose the PID is 18420:

~~~bash
jcmd 18420 help JDK.checkpoint
jcmd 18420 JDK.checkpoint
~~~

After the command runs, check the logs and the configured directory. Only consider the checkpoint ready when the runtime reports success and the checkpoint image has been completely created according to that JDK's format. Do not copy a checkpoint directory that is still being written.

### Restoring from a Checkpoint

For CRaC JDK distributions that support this option, you can launch a process from the saved image with:

~~~bash
java \
  -XX:CRaCRestoreFrom=/var/lib/myapp/checkpoint
~~~

Restore usually requires an environment compatible with the environment where the checkpoint was created, including the JDK distribution, architecture, operating system, native libraries, and dependent paths. Check the vendor's guide for specific requirements.

If using `Core.checkpointRestore()` in Java code, the application goes through the checkpoint–restore cycle via the API; when restore succeeds, execution continues after the call. How the checkpoint image is launched or managed still depends on the runtime and deployment environment.

## 7. Common Errors When Requesting a Checkpoint

### JDK.checkpoint Not Found

**Symptom:** `jcmd` reports that the command does not exist or does not list `JDK.checkpoint` in help.

Possible causes:

- The running JVM is not a JDK distribution with CRaC support.
- The `jcmd` tool being used is not compatible with the target JVM.
- The PID points to a different process.
- The runtime distribution or configuration does not provide this diagnostic command.

How to resolve: verify `java -version`, `jcmd -l`, the PID, the path to `jcmd`, and the documentation of the CRaC JDK distribution.

### Unable to Attach to the Process

**Symptom:** `jcmd` cannot connect to the PID or reports a permission error.

Check:

- The process still exists and the PID is accurate.
- `jcmd` is running under an account with appropriate attach permissions.
- The command is running on the same machine or in the right container environment.
- Whether the JVM allows attaching under the current configuration.

Do not arbitrarily run with elevated privileges without understanding the permission model of the deployment environment.

### Unable to Write the Checkpoint

**Symptom:** the command fails, logs report unable to create the image, or there is no valid checkpoint image.

Check:

- The `CRaCCheckpointTo` path was configured properly when launching the JVM.
- The directory exists and the JVM account has write permissions.
- The disk has sufficient space.
- The filesystem and runtime environment meet the runtime's requirements.
- CRIU, the kernel, and system permissions have been set up according to the documentation of the JDK in use.

Do not use an old or partially written checkpoint directory to restore. If the operation fails, determine whether the image was completely created before retrying.

### beforeCheckpoint() Callback Hangs or Throws an Exception

**Symptom:** the checkpoint waits for a long time, is aborted, or logs record a resource error.

Common causes are that the callback is waiting on an unfinished request, an unresponsive external connection, or a lock held by another thread.

How to resolve:

- Log the resource name and the step being executed.
- Set timeouts for waiting operations.
- Ensure workers can receive stop signals.
- Avoid holding locks while calling external services.
- Only allow the checkpoint to proceed when the application state meets safety conditions.

### Restore Fails or Application Is Not Ready

**Symptom:** the runtime cannot restore the image or the application errors inside `afterRestore()`.

Check compatibility between the checkpoint and restore environments, resource access permissions, endpoints, credentials, configuration, and native libraries. Read the runtime logs along with exceptions in callbacks to identify the failing resource.

If a connection cannot be recreated, the application needs a retry policy or a controlled shutdown. Do not reopen traffic before required dependencies are ready.

## 8. Safe Operating Principles

- Use the right JDK with CRaC support and confirm the `JDK.checkpoint` command exists before operating.
- Identify the exact PID and use `jcmd` with appropriate attach permissions.
- Configure the checkpoint path when launching the JVM and check disk space and write permissions.
- Treat `jcmd JDK.checkpoint` as an external request; use `Core.checkpointRestore()` when the application needs to proactively coordinate the cycle.
- Register `Resource` instances for connections and resources that must be closed before checkpoint and reopened after restore.
- Stop accepting new work and wait for running work to reach a safe state.
- Set timeouts for callbacks, avoiding indefinite waits or holding locks during I/O operations.
- Check logs and the completed checkpoint image before deploying a restore.
- Restore in an environment compatible with the environment where the checkpoint was created.
- Protect the checkpoint directory because the process image may contain sensitive data in memory.

When distinguishing the `jcmd JDK.checkpoint` command from the `Core.checkpointRestore()` API, operators can choose the right trigger point. `jcmd` is suitable for administrative operations on a running JVM; the API is suitable when the application needs to control the checkpoint timing according to business state. Whichever approach is used, registering resources and preparing the application before checkpointing remain the deciding factors for the reliability of the restore cycle.
