# Intentionally Triggering Checkpoint and Restore Failures to Practice Diagnosis

Checkpoint/restore is a process involving multiple components: the application, CRaC Resource, JDK runtime, checkpoint engine, operating system, filesystem, and external services. A successful checkpoint does not prove that the application will restore successfully on the target environment. Similarly, a successful restore does not prove that external resources remain valid or that the application can safely receive traffic.

To operate CRaC reliably, the development team needs to practice identifying and handling failures before bringing the process into production. An effective approach is to intentionally introduce controlled failures in a dedicated test environment, observe logs and resource states, and verify recovery paths.

This practice exercise builds a lab to trigger failures at different points: the `beforeCheckpoint` callback, the `afterRestore` callback, external connections, file descriptors, checkpoint artifacts, and runtime compatibility. Only one factor is changed at a time so that the root cause can be identified. All experiments should be run on a sample application, dummy data, and checkpoint artifacts dedicated to the lab.

## 1. Lab Objectives and Principles

After completing this exercise, learners can:

- Distinguish failures in a Resource callback from failures in the JDK runtime or checkpoint engine.
- Intentionally make a callback fail and determine the state of the process after the failure.
- Identify partially closed resources when a checkpoint is aborted.
- Trigger a recovery failure after restore and keep readiness in a not-ready state.
- Simulate an external dependency losing its connection or being unable to re-authenticate.
- Identify failures caused by unsupported file descriptors/sockets.
- Distinguish missing/corrupted artifacts from runtime compatibility failures.
- Collect logs, PID, FDs, connection states, timings, and runtime information to compile a report.
- Formulate retry, cold start, or rollback decisions based on the root cause.

Principles to follow:

1. Only use a disposable environment; do not use production checkpoints or credentials.
2. Use ports, directories, database schemas, and service accounts dedicated to the lab.
3. Record a baseline before injecting faults.
4. Enable only one fault injection at a time per scenario.
5. Do not manually close file descriptors from the shell to create failures; use the resource owner's API or a fault switch in the application.
6. Do not modify the original checkpoint when testing artifact corruption. Create a copy dedicated to that scenario.
7. Do not open traffic if mandatory restore hooks or health checks have not completed.
8. Record the JDK version, CRaC runtime, engine, OS/kernel, container image, and the platform-specific checkpoint/restore invocation method.

Fault injection is an intentional operation. A callback made to fail in the lab does not mean every runtime handles failures in the same way. Record the actual behavior of the JDK distribution and checkpoint engine being used.

## 2. Preparing the Test Environment

A minimal lab requires:

- A small Java application with at least one CRaC Resource.
- A JDK/runtime that supports CRaC.
- A checkpoint engine and operating system supported by the runtime.
- A dedicated directory to store checkpoint artifacts and logs.
- A mock dependency, such as a small HTTP server or test database.
- Tools to observe processes, threads, file descriptors, and sockets.

The directory can be organized as follows:

~~~text
crac-fault-lab/
  app/
    application.jar
    config/
  checkpoint/
    baseline/
    before-failure/
    after-failure/
    corrupt-copy/
  logs/
    application.log
    checkpoint.log
    restore.log
  evidence/
    runtime.txt
    process.txt
    fd-before.txt
    fd-after.txt
    timings.csv
  scripts/
    run-app.sh
    create-checkpoint.sh
    restore-checkpoint.sh
~~~

This is only a suggested structure. Actual checkpoint file and directory names depend on the engine/runtime. Some implementations create multiple auxiliary files or metadata; do not assume a checkpoint is just a single file.

### Recording runtime and host information

Before running, save platform information:

~~~shell
java -version
java -XshowSettings:properties -version
uname -a
uname -m
~~~

Also record:

- JDK vendor and full build.
- CRaC API/runtime version.
- Checkpoint engine and version.
- Relevant JVM flags and system properties.
- Container image digest if running in a container.
- Kernel, CPU architecture, libc, and filesystem of the checkpoint directory.
- Memory limit, swap policy, and process permissions/capabilities.

Do not use the commands above to infer the engine if the runtime does not expose the engine through them. Obtain the engine version from the tools or documentation of the specific distribution.

### Checking how to invoke checkpoint

Checkpoint and restore commands are not completely identical across JDK distributions. First, check the diagnostic commands published by the running JVM:

~~~shell
jcmd PID help
~~~

Replace `PID` with the actual PID. If the runtime output includes a checkpoint command, use the exact syntax listed by the runtime and documented by the vendor. Some runtimes may provide a command such as `JDK.checkpoint`; do not assume this command exists on every JDK.

Similarly, the restore command must follow the runtime/engine documentation. Do not combine a checkpoint created by one engine with launcher options from another engine.

## 3. Building a Sample Application with a Fault Switch

The lab application should have a Resource that owns a mock client and an admission gate. The fault switch allows enabling a failure via configuration when running the lab. The configuration must be disabled during the baseline run.

The example below illustrates the structure; the `Client`, `ClientFactory`, and `AdmissionGate` types are abstractions defined by the sample application:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class LabResource implements Resource {
    public enum FailurePoint {
        NONE,
        BEFORE_CHECKPOINT,
        AFTER_RESTORE
    }

    public interface AdmissionGate {
        void stopAndDrain() throws Exception;
        void resume() throws Exception;
        boolean isOpen();
    }

    public interface Client extends AutoCloseable {
        void healthCheck() throws Exception;
        @Override
        void close() throws Exception;
    }

    public interface ClientFactory {
        Client create() throws Exception;
    }

    private final AdmissionGate gate;
    private final ClientFactory factory;
    private final FailurePoint failurePoint;
    private volatile Client client;

    public LabResource(
            AdmissionGate gate,
            ClientFactory factory,
            FailurePoint failurePoint) throws Exception {
        this.gate = gate;
        this.factory = factory;
        this.failurePoint = failurePoint;
        this.client = factory.create();
        Core.getGlobalContext().register(this);
    }

    public Client client() {
        Client current = client;
        if (current == null) {
            throw new IllegalStateException(
                    "Client is not ready");
        }
        return current;
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        gate.stopAndDrain();

        if (client != null) {
            client.close();
            client = null;
        }

        if (failurePoint == FailurePoint.BEFORE_CHECKPOINT) {
            throw new IllegalStateException(
                    "LAB: intentional beforeCheckpoint failure");
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        Client restoredClient = factory.create();
        try {
            restoredClient.healthCheck();
            if (failurePoint == FailurePoint.AFTER_RESTORE) {
                throw new IllegalStateException(
                        "LAB: intentional afterRestore failure");
            }
            client = restoredClient;
            gate.resume();
        } catch (Exception failure) {
            restoredClient.close();
            client = null;
            throw failure;
        }
    }

    public synchronized void recoverAfterAbortedCheckpoint()
            throws Exception {
        if (client == null) {
            Client recovered = factory.create();
            recovered.healthCheck();
            client = recovered;
        }
        gate.resume();
    }
}
~~~

Points to observe in the example:

- Admission is stopped and in-flight work is drained before closing the client.
- The `beforeCheckpoint` failure is thrown after the client has been closed, to simulate a partially prepared state.
- If the checkpoint is aborted and the original process continues, the `afterRestore` callback is not the recovery mechanism for that process. The lab's coordinator must invoke a recovery path such as `recoverAfterAbortedCheckpoint()`.
- If `afterRestore` fails, the newly created client is closed again and admission remains closed.
- Handlers may only access the client through the state-checking accessor.

This is not a complete production implementation. A real application must ensure that no thread holds a direct reference to the client and bypasses the admission gate. If there are multiple interdependent Resources, there must be a coordinator or lifecycle contract defining a safe ordering.

### Configuring the fault switch

A system property or environment variable can be mapped to `FailurePoint`. For example:

~~~java
LabResource.FailurePoint point =
        LabResource.FailurePoint.valueOf(
                System.getProperty("lab.failAt", "NONE"));
~~~

Valid values for the lab:

| Value | Behavior |
|---|---|
| NONE | Do not intentionally trigger a failure |
| BEFORE_CHECKPOINT | Close the client and then make the pre-checkpoint callback fail |
| AFTER_RESTORE | Create the client and then make the post-restore callback fail |

Do not leave the fault switch enabled by default. Ideally, only allow it to be enabled in the lab profile and refuse to start if this profile is used outside the test environment.

## 4. Scenario 0: Running a Fault-Free Baseline

The baseline is the reference point for comparing all other scenarios. Run the application with the fault switch set to `NONE` and the mock dependency active.

Steps:

1. Start the application using the pinned JDK/CRaC runtime.
2. Confirm the application reports readiness.
3. Send a sample request and confirm the client works.
4. Record the PID, thread dump if needed, number of FDs, and open sockets.
5. Create a checkpoint in the `baseline` directory using the command supported by the runtime.
6. Restore the checkpoint using the matching runtime/engine.
7. Confirm the `afterRestore` callback completes.
8. Send the sample request again and check the dependency.

Record:

- Initial startup time.
- `beforeCheckpoint` callback duration.
- Checkpoint creation time.
- Artifact size and file list.
- Restore time.
- `afterRestore` callback duration.
- Time to readiness.
- Latency of the first request and subsequent requests.
- Logs, PID, and client state before/after restore.

<badge>Expected result</badge>

The application creates a checkpoint, restores successfully, the client is verified, and readiness only opens after the Resource completes. This is the control result for the subsequent tests.

## 5. Scenario 1: Making beforeCheckpoint Fail

The objective is to observe a pre-checkpoint callback failure and determine what happens when some resources have already been closed but the checkpoint has not completed.

### How to execute

1. Start the application in the lab profile with failure point `BEFORE_CHECKPOINT`.
2. Confirm the client is working and readiness is open.
3. Request a checkpoint using the runtime's mechanism.
4. Observe the logs of the Resource and the checkpoint coordinator.
5. Record whether the runtime aborts the checkpoint and the state of the original process.
6. Check whether the client is closed or still open.
7. Run the application's post-checkpoint-abort recovery path.
8. Confirm the new client works before opening admission.

Do not assume all runtimes have the same behavior after a callback throws an exception. Clearly record whether the runtime immediately stops the checkpoint operation, whether it invokes other registered callbacks, and how it reports the error.

### Results to observe

- Whether the log contains the `LAB` intentional failure message.
- Whether the checkpoint artifact is created completely.
- Whether the original process is still running or has terminated.
- Whether the admission gate is closed or open.
- Whether the client was partially closed before the failure occurred.
- Whether the coordinator invoked the recovery path.
- Whether requests after recovery succeed.

If the process continues running while the client is closed, requests must be blocked until the client is recreated. This is a common bug when a checkpoint preparation callback fails after performing actions with side effects.

### Lessons learned

The `beforeCheckpoint` callback is not an auto-rollback transaction. If some resources have already been closed and a subsequent callback fails, the application needs a recovery path for the original process. Do not expect `afterRestore` to be called on a process that was not restored.

## 6. Scenario 2: Making afterRestore Fail

The objective is to observe a failure occurring after the process is restored but before the application is ready to receive traffic.

### How to execute

1. Create a valid checkpoint using the baseline configuration.
2. Use a restore run with failure point `AFTER_RESTORE`.
3. Restore the artifact using the appropriate runtime/engine.
4. Observe the callback log and the `LAB` intentional failure error.
5. Verify that the client was closed again in the `catch` block.
6. Confirm admission/readiness does not open.
7. Record how the runtime handles the restore callback failure.

### Results to observe

- The `afterRestore` callback begins running.
- The client is created, but the health check or fault injection causes the callback to fail.
- The unready client is closed.
- Readiness remains `false`.
- Handlers cannot use the unready client.
- The runtime reports a restore failure, keeps the process unready, or terminates the process according to implementation semantics.

The final behavior depends on the runtime and checkpoint engine. Do not assume the process will definitely retry the callback on its own. If the runtime treats a callback failure as an unrecoverable restore error, the recovery option may be to discard that instance and start a new instance from a cold start or a verified checkpoint.

### Lessons learned

Restore completing at the process layer does not mean the application is business-ready. Readiness must depend on restoring mandatory resources, verifying dependencies, and completing security initialization.

## 7. Scenario 3: External Dependency Unavailable

The objective is to test the application when a database, HTTP service, or message broker cannot reconnect after restore.

### How to execute with an HTTP dependency

1. Use a mock HTTP service running on a lab-dedicated port.
2. Start the application and confirm the health check succeeds.
3. Create a checkpoint after the Resource has prepared its resources as designed.
4. Stop the HTTP service or block connections from the lab environment.
5. Restore the checkpoint.
6. Observe timeouts, retries, and readiness.
7. Restart the HTTP service.
8. Let the application retry according to policy and confirm readiness opens after the health check succeeds.

If using a database, create a dedicated schema and dummy data. Do not use a production database to intentionally stop the service or break connections.

### Failures to distinguish

- DNS lookup failure.
- TCP connection timeout or connection refused.
- TLS handshake failure due to certificate/clock/trust.
- Expired token or invalid audience/scope.
- Stale database session already closed by the server.
- Broker client unable to re-establish subscription or consumer group state.
- Dependency returning an application error even though the TCP connection succeeded.

### Results to observe

The application must not be marked ready merely because the process restored. Logs need to distinguish connection errors, authentication errors, TLS errors, and business errors. Retries must have reasonable timeouts, backoff, and limits to avoid creating heavy load on a newly recovered dependency.

### Lessons learned

A checkpoint does not freeze the lifecycle of external systems. Databases, brokers, DNS, secret managers, and APIs continue to change while the snapshot is stored. After restore, time-dependent conditions must be re-verified.

## 8. Scenario 4: Holding an Unhandled File Descriptor

The objective is to find the open resource when the checkpoint engine reports an unsupported descriptor or cannot dump it.

### How to execute

1. Create a `FileChannel` or socket owned by the lab application.
2. Enable test mode so the Resource does not close that resource during `beforeCheckpoint`.
3. Record the PID and FD list before checkpointing.
4. Request a checkpoint.
5. Save all runtime/engine logs.
6. If the checkpoint fails, cross-reference the FD or inode in the log with `/proc/PID/fd` and `lsof`.
7. Identify the Java component that created the resource.
8. Re-enable proper close/open lifecycle and run again.

Observation commands on Linux:

~~~shell
ls -l /proc/PID/fd
lsof -nP -p PID
lsof -nP -a -p PID -i
ss -tanp
~~~

Replace `PID` with the actual PID. If the process runs in a container, use the appropriate PID namespace; if observing sockets from the host, identify the corresponding network namespace.

### Results to observe

- FD type: regular file, socket, pipe, eventpoll, device, or native handle.
- Descriptor number and inode if available.
- Path or endpoint.
- Resource owner in the application.
- Specific engine error and failed native step.
- Result after properly closing the resource.

Do not attempt to close an FD using a shell command. Closing a descriptor outside the process can leave the Java object holding the old FD number while the kernel reuses that number for another resource. Fix the lifecycle in the owner API.

## 9. Scenario 5: Missing or Corrupted Checkpoint Artifact

The objective is to distinguish artifact failures from application or runtime failures.

### Preparing the test copy

1. Create a valid baseline checkpoint.
2. Copy all artifacts to the `corrupt-copy` directory.
3. Keep the baseline intact.
4. In the test copy, intentionally delete an auxiliary file or modify a file in a recoverable way.
5. Compute checksums before and after the modification.
6. Attempt to restore the corrupted copy.

Do not modify the original artifact or a checkpoint being used by another environment. If the engine creates multiple files, know which files are mandatory components from the runtime's manifest or logs.

### Two types of tests

**Missing file:** rename or remove a file in the test copy. Restore may report file not found, incomplete metadata, or a read error.

**Modified content:** change one byte or truncate the test copy, then check the checksum and restore. If the manifest has a hash, the integrity verification step should detect the modification before calling the engine.

### Results to observe

- Whether the checksum still matches the manifest.
- Whether the failure occurs at the artifact verification step, file reading step, or restore engine step.
- Whether a dangling/partial process is created.
- Whether the application falls back to the cold-start path.
- Whether logs clearly identify the artifact ID and checkpoint ID.

### Lessons learned

A checkpoint is not just a directory with the right name. It requires a file inventory, checksums, manifest, access permissions, and an immutable release process. If an artifact lacks integrity, do not attempt to restore by bypassing the hash check.

## 10. Scenario 6: Testing Incompatible Runtime or Engine

The objective is to understand why a valid checkpoint on a producer may fail to restore on a consumer.

Only perform this in a disposable environment with two separately installed runtimes/engines that do not share data directories. Do not upgrade or replace the production runtime to test.

### How to execute

1. Create a checkpoint using JDK/CRaC/engine combination A.
2. Save the producer's manifest: vendor, full runtime version, engine, kernel, architecture, native libraries, and container digest.
3. Create test environment B with one pre-selected differing component, such as engine version or JDK build.
4. Before restoring, check vendor documentation to determine whether combination B is supported.
5. If it is an unsupported combination, only test on a copy of the artifact and a dedicated host.
6. Save runtime/engine logs and error codes.
7. Restore combination A and confirm the baseline artifact still works.

### Do not change multiple factors at once

If you change JDK vendor, engine, kernel, CPU architecture, and container image at the same time, a failure result will not pinpoint the specific cause. Change one factor at a time in the lab environment and record a producer/consumer matrix.

### Results to observe

- Whether the runtime rejects before reading the artifact.
- Whether the engine reports an incompatible format or native state.
- Whether the error is related to kernel, architecture, library, or permissions.
- Whether it can still restore successfully on the original producer combination.

### Lessons learned

Compatibility must not be inferred from two environments both running Linux or sharing the same Java major version. Checkpoint binaries are tied to a specific runtime and engine; a supported and tested combination must be used.

## 11. Scenario 7: Hung or Timed-Out Callback

The objective is to test a Resource callback when closing a connection or draining a worker does not complete.

### How to execute

1. Create a test Resource with a latch or a test server that holds requests without responding.
2. In `beforeCheckpoint`, have the Resource wait for that operation to complete.
3. Do not let the test server respond within a bounded time window.
4. Request a checkpoint.
5. Record the callback duration, timeout log, and admission state.
6. Allow the test server to respond or cancel the task according to policy.
7. Run the recovery path if the checkpoint was aborted.

Do not create infinite loops or long sleeps in a production process. Use short, configurable timeouts and a dedicated lab environment.

### Results to observe

- Whether the callback has a clear timeout or hangs indefinitely.
- Whether the coordinator knows which Resource has not completed.
- Which thread is waiting and what condition it is waiting on.
- Whether the admission gate stays closed when the callback fails.
- Whether the original process can recover after the checkpoint is aborted.

### Lessons learned

Every pre-checkpoint operation needs a timeout and a failure strategy. A callback that never finishes can stall the checkpoint coordinator. Timeouts must be paired with rollback/recovery logic, not just throwing an exception and leaving the process in a half-closed state.

## 12. Scenario 8: Testing Ordering Dependencies Between Resources

The objective is to find bugs when two Resources manage components with a dependency relationship.

For example:

- Resource A stops the HTTP client.
- Resource B stops the worker sending requests through the HTTP client.

If the client is closed before the worker stops, the worker may fail or hang. On restore, the worker may run before the client is recreated.

### How to execute

1. Create two test Resources with timestamp logs in each callback.
2. Have a worker continuously send requests through the client.
3. Invoke checkpoint while requests are in flight.
4. Observe the order of stopping the worker and closing the client.
5. Restore and observe the order of opening the client and starting the worker.
6. Repeat multiple times to detect races.

Do not rely on the coincidental order of independent callbacks if the API/runtime does not guarantee it. Use a coordinator with clear ownership to orchestrate the sequence: stop admission, drain worker, close client; on restore, create client, health check, resume worker, and open admission.

## 13. Scenario 9: State Cloned Across Multiple Replicas

The objective is to detect data in the heap that must not be shared when the same checkpoint is restored multiple times.

Create a test application holding:

- A dummy token with an identifying ID.
- A local counter.
- A nonce generator.
- A replica identity.

Before checkpointing, record non-sensitive fingerprints or IDs of these values. Restore the same checkpoint into multiple instances in the lab environment.

Check:

- Whether each replica receives a new identity.
- Whether tokens are newly issued per replica.
- Whether global counters collide.
- Whether nonces could repeat under the same key.
- Whether readiness waits for security initialization to complete.

Do not log real tokens, private keys, or production nonces. Use dummy data and safe fingerprints. For nonces, statistical tests do not prove absolute uniqueness; the key/nonce allocator design must be verified.

## 14. Fault Injection Summary Table

| Scenario | Injected Fault | Signs to Look For | Handling Approach |
|---|---|---|---|
| Baseline | None | Checkpoint/restore completes, readiness opens | Save as reference |
| beforeCheckpoint | Callback throws exception | Resource log, checkpoint aborted, partially closed resources | Recovery for original process |
| afterRestore | Callback throws exception | Restore hook fails, readiness remains closed | Controlled retry or cold start |
| Dependency down | HTTP/DB/broker unavailable | Timeout, auth error, stale connection | Reconnect, retry/backoff, readiness gate |
| Unsupported FD | Unhandled file/socket/pipe | FD/inode/errno in engine log | Find owner and handle lifecycle |
| Artifact missing | Missing checkpoint file | ENOENT or incomplete metadata | Restore complete bundle |
| Artifact corrupt | Checksum/content modified | Hash mismatch or read/restore error | Reject artifact and use valid copy |
| Incompatible runtime | Consumer differs from producer | Runtime/engine/kernel compatibility error | Use supported profile |
| Callback timeout | Resource does not finish | Callback duration exceeds threshold, waiting thread | Timeout and recovery path |
| Resource ordering | Uncoordinated callback dependencies | Race, client closed too early or worker started too early | Lifecycle coordinator |
| Cloned state | Multiple replicas from same snapshot | Duplicate identity/token/counter/nonce | Re-issue identity and separate state |

## 15. Collecting Evidence in Each Run

Do not only record the exception line. A diagnostic report needs enough information for someone else to reproduce it.

### Environment metadata

- Lab run ID.
- Start/end timestamps in UTC.
- Git commit and application build ID.
- JDK vendor, full version, and CRaC runtime.
- Checkpoint engine and version.
- OS, kernel, CPU architecture, and container digest.
- JVM flags, memory limit, and checkpoint path.

### Logs and process state

- Application logs before, during, and after callbacks.
- Checkpoint/restore engine logs.
- PID, parent PID, and process state.
- Thread dump if a callback hangs.
- File descriptor inventory if there is an FD/socket error.
- Socket endpoint/state if there is a network error.
- Resource name and callback duration.

### Results

- Did the checkpoint complete?
- Are the artifacts complete and do checksums match?
- Did the restore complete?
- Did readiness open at the right time?
- Is the dependency working?
- Did recovery or cold-start fallback succeed?
- How long did each phase take?

A sample log table:

| Timestamp UTC | Phase | Resource | Event | Duration | Outcome |
|---|---|---|---|---:|---|
| 08:00:00.100 | beforeCheckpoint | ApiClient | close started | - | - |
| 08:00:00.140 | beforeCheckpoint | ApiClient | close completed | 40 ms | success |
| 08:00:00.141 | beforeCheckpoint | LabResource | injected failure | - | failed |
| 08:00:00.180 | coordinator | checkpoint | request aborted | 80 ms | failed |
| 08:00:00.250 | recovery | ApiClient | reopen completed | 70 ms | success |

The timestamps and durations above are examples only. Synchronize clocks in the lab environment or record monotonic durations to avoid skew when wall clocks change.

## 16. How to Classify Root Causes from Symptoms

| Symptom | Possible Cause Group | Evidence to Look For |
|---|---|---|
| Error appears immediately when invoking checkpoint | Resource callback or runtime precondition | Java stack trace, callback log |
| Callback completes but engine dump fails | Native FD, kernel, permissions, or engine | Engine log, errno, FD inventory |
| Artifact created but restore cannot read it | Missing/corrupted artifact, path, or permissions | Checksum, file inventory, filesystem log |
| Restore process starts but app is not ready | `afterRestore` or dependency failure | Restore hook log, health check, readiness |
| Fails only on a different host | Compatibility or target environment | Producer/consumer manifest, kernel, CPU, engine |
| Intermittent success/failure | Race, timeout, fluctuating dependency, or I/O pressure | Timestamps, thread dump, retries, and metrics |
| Restore succeeds but first request fails | Stale state, expired credentials, cache, or connection | Request trace, auth error, client lifecycle |
| Multiple replicas generate the same ID/token/nonce | Cloned state | Replica identity, key ID, allocator state |

This is an investigation guide map, not an automatic conclusion. One symptom can have multiple causes; confirm with logs and isolated tests.

## 17. Designing Recovery and Fallback

Fault injection is only useful if, after identifying a failure, the application has a defined way to recover.

### When beforeCheckpoint fails

- Mark the checkpoint attempt as failed.
- Identify which Resources were closed or changed state.
- Keep admission closed if mandatory resources are not ready.
- Invoke the recovery path for the current process.
- Recreate necessary clients/credentials/file handles.
- Perform a health check before opening admission.

### When afterRestore fails

- Do not open readiness.
- Close partially created resources.
- Clearly log the failed Resource and dependency.
- Retry only if the error is recoverable and the runtime allows that retry approach.
- If restore cannot continue, discard the instance and use the cold-start path or a verified checkpoint.

### When artifacts or compatibility are invalid

- Do not bypass checksum or compatibility checks.
- Do not edit production artifacts to attempt recovery.
- Select a signed and verified release bundle.
- Use a supported runtime/engine profile.
- If no valid checkpoint is available, cold start from the pinned application artifact.

### When an external dependency fails

- Use bounded timeouts and backoff.
- Do not create thousands of simultaneous retry connections.
- Keep readiness `false` for mandatory dependencies.
- Refresh tokens/certificates on authentication or expiration errors.
- Record metrics to distinguish dependency errors from restore engine errors.

## 18. Operational Checklist for a Practice Session

Before the lab session:

- [ ] Confirm this is a dedicated host/container for testing.
- [ ] Create a dedicated application build and checkpoint artifact.
- [ ] Record runtime, engine, kernel, CPU, and container digest.
- [ ] Prepare mock dependencies and non-sensitive data.
- [ ] Confirm the checkpoint/restore invocation method matches the runtime.
- [ ] Verify the fault switch is disabled by default.
- [ ] Enable callback, duration, and readiness state logging.

During each scenario:

- [ ] Enable only one fault injection.
- [ ] Record the run ID and fault configuration.
- [ ] Save logs before/after checkpoint or restore.
- [ ] Collect PID, FDs, sockets, or thread dumps when needed.
- [ ] Record artifact status and checksums.
- [ ] Determine whether the process is still running, restored, or terminated.
- [ ] Check readiness and dependencies.

After each scenario:

- [ ] Restore the environment to baseline.
- [ ] Clear the fault switch and confirm it is disabled.
- [ ] Do not reuse modified/corrupted artifacts for other scenarios.
- [ ] Save results and root cause hypotheses.
- [ ] Re-run the baseline to confirm the lab is no longer in a faulted state.

## 19. Extension Exercises

After completing the basic scenarios, you can extend with:

**Exercise A — failure that only appears when restoring on a different host.** Create a producer/consumer manifest, change one environment factor in the lab, and identify which factor causes restore to fail.

**Exercise B — slow-recovering dependency.** Add a delay to the HTTP service, measure readiness and the p99 of the first request. Tune timeout/backoff and compare.

**Exercise C — long-running callback.** Create a worker with an in-flight task, measure drain time, and prove the checkpoint only proceeds once the worker stops safely.

**Exercise D — multiple Resources with dependency relationships.** Have a worker depend on a client, design a coordinator, and prove the stop/start ordering does not create a race.

**Exercise E — multiple replicas restoring together.** Issue separate identities, check tokens and key IDs, and verify the nonce allocator is not cloned.

**Exercise F — rollback.** Release two different runtime/application/checkpoint sets in the lab, intentionally make the new release's restore fail, and roll back to the previous release bundle.

For each exercise, state a hypothesis before running, record the observed results, explain differences between prediction and reality, and identify necessary changes in the application or operational procedures.

## 20. Conclusion

Intentionally triggering checkpoint and restore failures helps the development team clearly understand the boundaries between Resource callbacks, the JDK runtime, the checkpoint engine, the operating system, and external dependencies. Key scenarios include failed callbacks, partially closed resources, unavailable dependencies, unsupported file descriptors, corrupted artifacts, incompatible runtimes, timeouts, and state cloned across multiple replicas.

A good lab always has a baseline, isolated fault injection, context-rich logs, and verified recovery paths. When a checkpoint fails, the original process may need to recover closed resources; when a restore fails, readiness must remain closed; when an artifact or runtime is incompatible, restore must be rejected and a verified release or cold start used instead. Perform these experiments in a disposable environment, using the exact commands and limits of the deployed JDK/engine, and then turn the findings into automated tests and repeatable operational procedures.
