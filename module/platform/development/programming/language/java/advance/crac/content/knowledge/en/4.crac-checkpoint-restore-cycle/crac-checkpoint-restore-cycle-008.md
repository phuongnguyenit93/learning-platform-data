# Distinguishing Between Successful Checkpoint, Failed Checkpoint, and Failed Restore

In the CRaC (Coordinated Restore at Checkpoint) cycle, checkpoint and restore are two separate operations. A **successful checkpoint** means the JVM has created the state image as requested. A **failed checkpoint** means the image creation process did not complete or the runtime rejected the request. A **failed restore** occurs at a later step, when the JVM cannot restore the process from the checkpoint image or the application cannot continue operating normally after restoration.

Properly distinguishing these three outcomes helps isolate errors accurately. The mere appearance of a checkpoint directory is not enough to prove the image is valid; conversely, a failed restore does not automatically prove that the preceding checkpoint operation failed. It is necessary to read the outcome of each stage together with JVM logs, CRIU/platform logs, and application state.

## 1. Viewing the CRaC Cycle as Independent Stages

A typical workflow has the following stages:

```text
Launch JVM with -XX:CRaCCheckpointTo
                  |
                  v
    Application completes initialization
                  |
                  v
        Prepare CRaC resources
                  |
                  v
        Create checkpoint image
                  |
          +-------+-------+
          |               |
      Succeeded         Failed
          |               |
          v               v
Image saving complete  Stop to investigate error
          |
          v
    Launch restore with
  -XX:CRaCRestoreFrom=<path>
          |
     +----+----+
     |         |
 Succeeded   Failed
     |         |
     v         v
   Check    Investigate
 readiness  restore error
```

Here, there are three points to distinguish:

1. The checkpoint preparation process may fail before the JVM starts writing the image, for example when a resource callback reports an error.
2. The JVM may start creating the image but encounter an error while dumping the process or writing data. In that case, an incomplete directory or files may remain.
3. A checkpoint may be created successfully, yet a subsequent restore still fails due to an incompatible environment, insufficient resources, or an error during the restoration stage.

Checkpoint completion and the application functioning properly after restore are two different criteria. A deployment system should record the result of each stage separately.

## 2. What Does a Successful Checkpoint Mean?

A checkpoint is considered successful when the runtime completes the image creation process and confirms the result according to the mechanism of the JDK/CRaC build being used. Typically, this includes resource preparation callbacks completing, the process being dumped, and the required checkpoint data finishing writing.

For example, the application is launched with a checkpoint directory:

```bash
CHECKPOINT_DIR=/var/lib/myapp/checkpoints/release-1
java -XX:CRaCCheckpointTo="$CHECKPOINT_DIR" -jar application.jar
```

After the application is ready, request a checkpoint using `jcmd`:

```bash
jcmd <pid> JDK.checkpoint
```

When evaluating the result, look simultaneously at:

- The output and exit status of the `jcmd` control command as provided by the current runtime.
- JVM logs indicating whether pre-checkpoint callbacks and the checkpoint operation completed.
- Logs from CRIU or the checkpoint infrastructure layer if provided by the environment.
- The state of the original process after checkpoint. With a typical dump process, the process may terminate when the image is created; this is not necessarily an error. The specific behavior should be cross-checked with the CRaC build and deployment method in use.
- Checkpoint data has finished writing at the target path and the runtime reported no errors when ending the operation.

There is no single log message or common directory structure for every CRaC build. Therefore, use the documentation of the deployed JDK distribution to identify the official success signal. The existence of checkpoint data can be used as supporting evidence, but one should not rely solely on the fact that the directory was created.

After a successful checkpoint, the image is ready for the restore step in a compatible environment. This does not yet prove that restore will succeed on every machine, kernel, or deployment configuration.

## 3. What Does a Failed Checkpoint Mean?

A checkpoint fails when the JVM or the infrastructure layer cannot complete image creation. Errors can occur before starting the dump or while writing the image.

### 3.1. Failure at the Resource Preparation Step

Before checkpointing, CRaC invokes registered resource preparation callbacks, such as `beforeCheckpoint`. The application or libraries can close connections, stop threads, flush data, and bring resources to a safe state.

If a callback throws an exception or detects a resource that cannot be checkpointed yet, the runtime may reject the operation. For example:

- A connection pool cannot be closed or paused properly.
- A socket is still in an unsupported state.
- A background thread is performing work that the application cannot safely pause.
- A library detects a file handle or native resource that cannot be saved.
- The application has not completed a transaction or task required before checkpoint.

In this situation, the error belongs to the preparation stage. One should not conclude that the CRIU dump failed if the logs show the runtime stopped before starting the dump.

### 3.2. Failure During Image Creation

If the preparation step completes but dumping the process fails, the cause may lie in the environment or storage system:

- CRIU or a required kernel feature is not installed/enabled or is incompatible.
- Missing required permissions to dump the process, namespaces, or related resources.
- The filesystem does not support the required operation or the target directory is not writable.
- Out of storage space or encountering an I/O error.
- There is a native resource, mapping, or process state that the platform cannot dump.
- Container configuration blocks required capabilities, namespaces, or syscalls.

Logs at this stage usually help determine whether the error comes from the JVM, CRIU, kernel, or filesystem. Use the actual error message to choose the direction of investigation.

### 3.3. Why Does the Directory Exist Yet the Checkpoint Still Failed?

The runtime may create the target directory or write partial data before encountering an error. Therefore, the existence of the directory does not mean the entire image was created successfully. Do not manually rename, modify contents, or delete a few files inside the image to try to make the checkpoint look valid.

When the operation fails, keep the logs and record the directory state for investigation. After identifying the cause, only clean up incomplete checkpoint data according to the runtime's procedure and the application's operational procedure. If a retry is needed, use a new checkpoint directory or one that has been properly cleaned according to the CRaC build's instructions, avoiding mixing data from an old attempt with a new one.

## 4. What Does a Failed Restore Mean?

A failed restore is a situation where a checkpoint has been created or is assumed to have been created, but the JVM cannot restore the process from that image or the application cannot continue operating after restore.

The restore command usually has the form:

```bash
java -XX:CRaCRestoreFrom=/var/lib/myapp/checkpoints/release-1
```

Restore can fail at many different layers:

| Stage | Symptom | Possible Cause Group |
| --- | --- | --- |
| Loading checkpoint | JVM cannot read or recognize the image | Wrong path, missing files, incomplete image, or corrupted data |
| Restoring process | Runtime/CRIU cannot reconstruct the process | Differences in kernel, namespaces, permissions, CPU architecture, or OS resources |
| Restoring resources | Process is reconstructed but post-restore callback reports an error | Database, socket, file, credentials, or external service cannot reconnect |
| Application startup after restore | JVM has resumed but application does not complete startup | Error in `afterRestore`, changed environment configuration, cache or dependency no longer valid |
| Readiness check | Process is alive but cannot serve requests | Endpoint depends on unrecovered resources, background task not running, or application is in an error state |

The important point is to distinguish between **successful JVM restore** and **application ready to serve**. If the process has been restored but `afterRestore` fails or readiness is not met, record the application recovery failure separately. Do not lump all cases into "checkpoint failed".

## 5. Comparison Table of the Three Outcomes

| Criterion | Successful Checkpoint | Failed Checkpoint | Failed Restore |
| --- | --- | --- | --- |
| Time of occurrence | When creating the state image | When preparing or creating the image | After an image already exists and restore begins |
| Typical callback | `beforeCheckpoint` completes | Preparation callback reports an error or dump operation fails | Error when reconstructing the process or `afterRestore` callback |
| Checkpoint image | Confirmed by runtime as completely created | May not exist or only incomplete data remains | Exists/was selected for restore but cannot be used successfully in the current environment |
| JVM state | Checkpoint operation completes according to runtime semantics | Operation is rejected or interrupted by an error | JVM cannot restore, or restores but application fails afterward |
| Handling direction | Proceed to verify via restore | Investigate callbacks, JVM, CRIU, kernel, permissions, and storage | Check image, environment compatibility, and post-restore resources |

A special case that often causes confusion is when checkpoint succeeds but restore fails. In that case, the results of the two operations must be recorded separately: the checkpoint completed; that specific restore attempt did not succeed. The cause may be that the restore environment differs from the checkpoint creation environment, the image was modified after creation, or the application cannot restore external resources.

## 6. Reading Logs by the Right Stage

When investigating, first determine at what point the error occurred. Create a timeline consisting of:

1. JVM starts running with `-XX:CRaCCheckpointTo`.
2. Application completes startup and readiness.
3. Command `jcmd <pid> JDK.checkpoint` is sent.
4. Pre-checkpoint callbacks start and finish.
5. Runtime/CRIU starts dumping and finishes or reports an error.
6. Original JVM/process changes state.
7. Restore command with `-XX:CRaCRestoreFrom` is run.
8. JVM completes restoration, post-restore callbacks run, and application reaches or fails to reach readiness.

From this timeline, cross-reference logs to determine the last completed stage. For example:

- If logs report an error from `beforeCheckpoint`, focus on resource callbacks and application state.
- If callbacks completed but CRIU reports an error during dump, focus on kernel, permissions, namespaces, and filesystem.
- If the checkpoint was confirmed successful but restore reports it cannot read the image, check the path, read permissions, integrity, and whether the image was moved/modified.
- If the process was reconstructed but `afterRestore` throws an exception, check the recreation of connections and external resources.
- If the JVM and post-restore callbacks completed but readiness still fails, investigate the application layer and dependencies as when troubleshooting a normal startup failure.

One should not just search for the keyword `ERROR` and jump to conclusions. An application error log may be unrelated to the checkpoint operation; it is necessary to correlate timestamp, PID, command, and the stage being executed.

## 7. Procedure to Confirm a Successful Checkpoint

The following procedure can be used to record a checkpoint:

### Step 1: Record Run Information

Save the JDK version, command line, PID, checkpoint path, application version, kernel/CRIU info, and container configuration if applicable. Use the exact `jcmd` bundled with the JDK running the application.

```bash
java -version
jcmd -l
```

### Step 2: Send the Checkpoint Request

```bash
jcmd <pid> JDK.checkpoint
```

Save the entire output and exit status of the command. At the same time, save the application/JVM logs and checkpoint infrastructure logs from the same time window.

### Step 3: Confirm Runtime Completion

Cross-reference the output, callback logs, dump logs, and process state with the documentation of the CRaC build in use. If the runtime confirms the checkpoint completed, record the result as a successful checkpoint. Termination of the original process may be normal behavior of the dump process; do not automatically treat it as a sign of failure.

### Step 4: Record the Image and Protect Data

Record the path, creation time, application/JDK version, and metadata managed by the deployment process. Do not edit internal checkpoint files. Control access permissions because the image may contain sensitive data in memory.

### Step 5: Verify via Restore

Perform a restore in a compatible environment and confirm both levels:

- Whether the JVM/process is restored and continues.
- Whether the application completes post-restore callbacks, reconnects resources, and achieves readiness.

If this step fails, keep the confirmed checkpoint result and additionally record the failed restore result. Separate classification helps clarify that the image was created but cannot yet be used in the restore environment being tested.

## 8. Procedure to Investigate a Failed Checkpoint

When a checkpoint does not complete, investigate from the earliest stage with an error:

1. **Confirm the right JVM:** check the PID, JDK, and whether the runtime supports the `JDK.checkpoint` command.
2. **Check callbacks:** look for exceptions from `beforeCheckpoint` or registered resources. Identify the specific resource and the condition making it unready.
3. **Check permissions and storage:** confirm the user, write permissions, disk space, filesystem, and mount of the target directory.
4. **Check CRIU/kernel:** read dump logs to find rejected syscalls, capabilities, namespaces, or resources.
5. **Check container:** confirm process namespace, capabilities, security profile, and runtime configuration allow checkpointing.
6. **Controlled retry:** after fixing the cause, create the checkpoint into a new target directory or one cleaned according to runtime instructions; save logs of the new attempt.

If the error comes from an application callback, increasing OS permissions will not solve the root cause. If the logs indicate CRIU cannot dump a resource due to the environment, changing business logic may not be necessary. Rely on the specific stage and error message to choose the right layer to fix.

## 9. Procedure to Investigate a Failed Restore

When a checkpoint has been confirmed but restore does not succeed, check in order:

1. **Path and read permissions:** is the restore JVM pointing to the right checkpoint and can the user read all required data?
2. **Is the image still intact:** was the image partially deleted, overwritten, incompletely moved, or modified after checkpoint? Use metadata/checksums provided by the storage process if available.
3. **Compatibility:** do the JDK, CPU architecture, kernel, CRIU, native libraries, mounts, and namespaces meet the checkpoint's requirements?
4. **Process restoration errors:** do CRIU/runtime logs indicate which process, file descriptor, mapping, or OS resource cannot be reconstructed?
5. **Post-restore callbacks:** are there any exceptions from `afterRestore` or any resource callback?
6. **Readiness and dependencies:** are the database, message broker, DNS, external endpoints, credentials, or cache working in the restore environment?

A checkpoint created on machine A cannot automatically be restored on machine B. Compatibility must be confirmed according to the guidelines of the specific JDK/CRaC build and environment. If restore succeeds on the same environment but fails on a different environment, compare OS components and resources before blaming the checkpoint image.

## 10. Recording Results in a Deployment System

Pipelines or operational scripts should store checkpoint and restore statuses separately. A simple status model:

| Checkpoint status | Restore status | Meaning |
| --- | --- | --- |
| `SUCCEEDED` | `NOT_RUN` | Image was created; restore not yet verified |
| `FAILED` | `NOT_RUN` | Failed to create image; checkpoint investigation needed |
| `SUCCEEDED` | `SUCCEEDED` | Image was created and restore was verified in the tested environment |
| `SUCCEEDED` | `FAILED` | Image created successfully but the verification restore did not succeed |
| `UNKNOWN` | `UNKNOWN` | Missing logs or insufficient results to conclude |

The labels above are examples for a deployment management system, not mandatory status names of the CRaC API. It is advisable to add timestamp, build id, JDK version, checkpoint path, host/runtime identity, and error code for traceability. If retrying, each attempt should have its own identifier so logs from different runs are not mixed together.

Do not mark the entire workflow as successful just because the checkpoint step returned success. If the deployment requirement is "able to restore and serve traffic", the completion condition must include restore and readiness. Conversely, if only creating an image for archival, clearly record the status as checkpoint succeeded but restore not yet verified.

## 11. Scenario Classification Examples

### Scenario A: Callback Rejects Checkpoint

Logs show a resource callback failed while `beforeCheckpoint` was running. The runtime does not proceed to create the image.

**Classification:** checkpoint failed at the resource preparation step.

**Handling direction:** identify the resource, fix the callback or application state, and then perform the checkpoint again. No need to investigate restore because no confirmed image exists.

### Scenario B: Process Dump Fails Due to Environment

Preparation callbacks completed, but CRIU logs report missing permissions or inability to handle a namespace. Some files may have already appeared in the target directory.

**Classification:** checkpoint failed during the dump stage. Incomplete data must not be considered a valid checkpoint.

**Handling direction:** check capabilities, namespaces, kernel, security profile, permissions, and container configuration; then retry according to the runtime's cleanup procedure.

### Scenario C: Checkpoint Succeeded but Restore Is Incompatible

The runtime confirms image creation completed. When restoring on another host, CRIU or the JVM reports it cannot reconstruct the state due to environment differences.

**Classification:** checkpoint succeeded; restore failed on the test environment.

**Handling direction:** compare JDK, CPU, kernel, CRIU, native libraries, namespaces, and mounts between the two environments. Do not change the initial checkpoint status to failed.

### Scenario D: JVM Restored but Application Is Not Ready

The process is restored, but the `afterRestore` callback fails to recreate the connection pool. The JVM stays alive, but the readiness endpoint reports an error.

**Classification:** process restored; application recovery failed. According to operational requirements, the overall restore did not pass.

**Handling direction:** fix the connection pool recreation procedure, validate configuration and dependencies after restore, and then retry readiness.

## 12. Conclusion

A successful checkpoint confirms that the runtime has finished creating the state image. A failed checkpoint indicates that the preparation or image creation process did not complete. A failed restore is an error that occurs afterward, when the JVM cannot restore the image or the application cannot continue operating after restoration.

Record checkpoint and restore as two separate outcomes, use a timeline along with JVM/CRIU logs to identify the stage where the error occurred, and verify readiness after restore when the goal is to bring the application back to serving traffic. This classification helps avoid accidentally deleting usable images, avoid retrying at the wrong layer, and shorten time to root cause.
