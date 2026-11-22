# Running an Application with `-XX:CRaCCheckpointTo`

In the CRaC (Coordinated Restore at Checkpoint) checkpoint–restore cycle, the JVM needs to know where to store the checkpoint image of the process. The `-XX:CRaCCheckpointTo` option is used to specify that destination directory when launching the application. After the application is ready for a checkpoint, we send the `JDK.checkpoint` command via `jcmd` to request the JVM to create the state image. When we need to run the application again from the saved image, we launch the JVM with the `-XX:CRaCRestoreFrom` option pointing to the same checkpoint.

These two options serve two different phases:

| Option | Phase | Purpose |
| --- | --- | --- |
| `-XX:CRaCCheckpointTo=<path>` | Launching to prepare for creating a checkpoint | Declares the location to store the checkpoint. This option itself does not create a checkpoint automatically. |
| `-XX:CRaCRestoreFrom=<path>` | Launching to restore | Instructs the JVM to restore the process from an existing checkpoint at the specified location. |

The examples in this article use Linux commands and an application packaged as a JAR. CRaC depends on a JDK build with CRaC support and the checkpoint capability of the operating system; perform this on a Linux environment supported by your JDK/CRaC distribution.

## 1. Syntax and Placement of the Option

Basic syntax:

```bash
java -XX:CRaCCheckpointTo=/path/to/checkpoint -jar application.jar
```

`/path/to/checkpoint` is the path that the JVM uses as the destination to store the checkpoint image. Use a clear path that is accessible by the user running the JVM and located on a filesystem suitable for the runtime's checkpoint mechanism. The parent directory must exist; the process needs sufficient permissions to create and write checkpoint data at the target location.

The `-XX:CRaCCheckpointTo` option is a JVM option, so it must be placed before `-jar`:

```bash
java \
  -XX:CRaCCheckpointTo=/var/lib/myapp/checkpoints/release-1 \
  -Xms512m \
  -Xmx512m \
  -jar application.jar \
  --spring.profiles.active=production
```

In this example:

- `-XX:CRaCCheckpointTo=...`, `-Xms512m`, and `-Xmx512m` are JVM options.
- `-jar application.jar` specifies the JAR file to run.
- `--spring.profiles.active=production` is a Spring Boot application argument, placed after the JAR name.

If `-XX:CRaCCheckpointTo` is placed after `-jar`, the JVM will no longer read it as a JVM option; depending on the application, that string may be passed into `main(String[] args)` as an application argument. Therefore, it is necessary to distinguish the boundary between JVM options and application arguments.

Paths containing spaces need to be quoted according to shell rules:

```bash
java "-XX:CRaCCheckpointTo=/var/lib/my app/checkpoint" -jar application.jar
```

Prefer simple, stable paths that do not depend on the current working directory to reduce errors during automated operations.

## 2. Preparing the Environment Before Running

`-XX:CRaCCheckpointTo` only has meaning when the running JVM is a build with CRaC support. A regular JDK does not necessarily recognize this option. Before deploying, confirm the following conditions:

1. **JDK with CRaC support:** use the correct JDK distribution and version with CRaC integration. Keep the version information to reuse when restoring.
2. **Compatible operating system and kernel:** CRaC relies on the platform's process checkpoint mechanism. On Linux, the environment typically requires CRIU along with appropriate kernel features. The specific configuration depends on the distribution, kernel, container runtime, and JDK build.
3. **Access permissions:** the user running the JVM must have permission to write the checkpoint and permission to access the files, directories, and libraries that the process needs upon restore.
4. **Storage capacity:** a checkpoint can contain a large amount of process memory state. Plan for storage capacity, I/O, and image creation time.
5. **Stable path:** choose a storage location that the restore process can access again. If running in a container, the path needs to be mapped to storage that persists after the old container stops or is replaced.
6. **Application resources:** determine how the application handles sockets, database connections, threads, file handles, and external resources across the checkpoint/restore lifecycle.

You can check the Java version before running:

```bash
java -version
```

After the application starts, use `jcmd` from the same JDK to view the diagnostic commands provided by the JVM:

```bash
jcmd <pid> help
```

On a suitable CRaC runtime, the command list must include `JDK.checkpoint`. If the `-XX:CRaCCheckpointTo` option is reported as unrecognized or the `JDK.checkpoint` command does not exist, recheck the JDK distribution, version, and CRaC configuration before continuing.

## 3. Launching the Application with a Checkpoint Directory

Suppose the application is packaged at `/opt/myapp/application.jar` and the checkpoint will be stored at `/var/lib/myapp/checkpoints/release-1`.

```bash
APP_JAR=/opt/myapp/application.jar
CHECKPOINT_DIR=/var/lib/myapp/checkpoints/release-1

java -XX:CRaCCheckpointTo="$CHECKPOINT_DIR" -jar "$APP_JAR" &
APP_PID=$!
```

Explanation:

- `APP_JAR` holds the JAR file path to make the run command readable and avoid repeating the path string.
- `CHECKPOINT_DIR` is the location that will be used for the checkpoint.
- The `&` sign runs the JVM in the background in the current shell.
- `$!` captures the PID of the process just launched by the shell. This approach is suitable when the `java` command directly creates the application process, without going through a wrapper script that forks or daemonizes itself.

If the application runs under a service manager, container, or orchestration system, obtain the actual PID of the JVM in the correct process namespace. The PID on the host may differ from the PID visible inside the container.

After launching, check the logs and wait for the application to complete initialization steps. You can use:

```bash
jcmd -l
```

This command lists the JVMs that `jcmd` can identify. Match the PID to the correct application before sending the checkpoint command. Do not accidentally select the PID of another JVM running on the same machine.

## 4. Requesting the JVM to Create a Checkpoint

When the application is ready, request a checkpoint with:

```bash
jcmd "$APP_PID" JDK.checkpoint
```

`jcmd` connects to the JVM with the corresponding PID and sends the `JDK.checkpoint` diagnostic command. The JVM coordinates with CRaC to run the checkpoint procedure, including the registered resource preparation callbacks, and then writes the process state to the location declared by `-XX:CRaCCheckpointTo`.

The key point to remember is that `-XX:CRaCCheckpointTo` only configures the storage destination. The `JDK.checkpoint` command is what actually requests the checkpoint execution. If the application is only launched with this option without a checkpoint request, the checkpoint image will not appear automatically just because the JVM has been running for some time.

When the checkpoint succeeds, the original process usually terminates according to CRaC's checkpoint procedure to avoid continuing to run concurrently with the process that will be restored from the same state image. Check the command result, JVM logs, and process status instead of assuming the application is still serving requests as before.

Operational verification steps:

```bash
# Check running JVMs again
jcmd -l

# Inspect the contents of the checkpoint directory
find "$CHECKPOINT_DIR" -maxdepth 2 -type f -print
```

The file names and structure inside the checkpoint are managed by the runtime/CRIU; the application should not manually edit or delete individual files inside the checkpoint image. Nor should the existence of the directory be treated as the sole proof that the checkpoint is valid. You need to verify that the checkpoint command completed and test restoring in an appropriate environment.

## 5. Restoring the Application from a Checkpoint

After having a checkpoint, launch the JVM with the restore option:

```bash
java -XX:CRaCRestoreFrom="$CHECKPOINT_DIR"
```

`-XX:CRaCRestoreFrom` points to the previously created checkpoint image. The JVM restores the process and continues from the saved state. This is a process restore, not a fresh run of `application.jar` from scratch; therefore, the restore command does not need `-jar application.jar` like the initial launch command.

After restore, the application continues its runtime lifecycle according to the saved state and executes post-restore handling registered by the application or CRaC libraries. Check logs, readiness, and request-handling capability before putting the instance into traffic.

Example of a complete workflow:

```bash
# 1. Launch the application and configure where to store the checkpoint
CHECKPOINT_DIR=/var/lib/myapp/checkpoints/release-1
java -XX:CRaCCheckpointTo="$CHECKPOINT_DIR" -jar /opt/myapp/application.jar &
APP_PID=$!

# 2. Wait for the application to be ready and send a warm-up workload if needed
#    Replace this step with a health check/warm-up appropriate for the application.

# 3. Request checkpoint creation
jcmd "$APP_PID" JDK.checkpoint

# 4. When restore is needed, run the command in a compatible environment
java -XX:CRaCRestoreFrom="$CHECKPOINT_DIR"
```

This is an illustrative example of the command sequence; in practice, the restore step is usually performed in another deployment or startup process after the checkpoint has been safely stored.

## 6. Role of Lifecycle Hooks During Checkpoint and Restore

A checkpoint image saves process state, but it does not automatically make all external resources valid when the process resumes running. The application needs to coordinate with CRaC to prepare before checkpoint and recover resources after restore.

Conceptually, the lifecycle consists of two critical moments:

| Moment | Goal | Example Handling |
| --- | --- | --- |
| Before checkpoint (`beforeCheckpoint`) | Bring resources to a state that can be saved and restored | Complete or stop in-flight work, close non-reusable connections, flush necessary data, and stop appropriate threads/timers. |
| After restore (`afterRestore`) | Restore or verify resources needed for subsequent operation | Recreate connection pools, reopen database/socket connections, refresh environment-dependent information, and restart appropriate tasks. |

Frameworks or libraries with CRaC integration may automatically manage some resources. For resources created by the application itself, check whether they have been registered and handled properly in the lifecycle. Do not assume that a JDBC connection, socket, or file descriptor will always be usable after restore just because the corresponding Java object is still on the heap.

When calling `jcmd <pid> JDK.checkpoint`, a preparation callback may detect that the application is not ready and cause the checkpoint to fail. This is an intentional safeguard: it is better to fix the resource management or checkpoint timing rather than ignoring the error and creating an unsafe state image.

## 7. Choosing the Checkpoint Timing

Setting `-XX:CRaCCheckpointTo` at launch only resolves the storage location. Checkpoint quality also depends on when `JDK.checkpoint` is sent.

If checkpointing immediately after the JVM starts running, the state image may not yet contain sufficient application caches, loaded classes, or useful JIT state. If checkpointing after the application has processed a representative workload, the runtime state may be better suited for the initial traffic phase after restore.

A preparation workflow typically includes:

1. Launch the application with `-XX:CRaCCheckpointTo` pointing to a checkpoint directory dedicated to the deployment version.
2. Wait for the application to complete startup and necessary health checks.
3. Perform representative warm-up if the goal is to retain useful cache/JIT state for post-restore traffic.
4. Confirm there are no remaining transactions or tasks that need to complete in a way incompatible with checkpointing.
5. Send `jcmd <pid> JDK.checkpoint`.
6. Confirm the checkpoint succeeded and test restoring with the exact compatible runtime.

Warm-up needs to avoid unintended side effects. If an endpoint modifies data, sends notifications, or creates transactions, use test data and appropriate isolation mechanisms. Do not create a checkpoint when the application is in the middle of a business operation where continuing after restore could cause duplication or data loss.

## 8. Operating in Containers and Deployment Environments

In containers, the checkpoint path should usually be placed on a volume mounted from outside the container or a storage area with a sufficiently long lifecycle. If the checkpoint only resides in the writable layer of the old container, deleting or replacing the container can lose the checkpoint image.

Example of configuring the path at the application level:

```bash
java -XX:CRaCCheckpointTo=/checkpoint/release-1 -jar application.jar
```

Here `/checkpoint` needs to be mounted into the container with appropriate access permissions. Besides mounting the directory, the container environment must also meet CRaC/CRIU requirements and necessary kernel privileges. Simply mounting a volume does not automatically make process checkpointing supported in every container runtime.

When calling `jcmd`, execute it in the correct process namespace environment and use privileges appropriate for the user owning the JVM. If the JVM's PID inside the container is `1`, the command inside the container can use PID `1`; do not assume the PID on the host is also `1`.

Checkpoints depend on the runtime environment. When transferring the image to another host, ensure compatibility of the JDK, CPU architecture, kernel, native libraries, mount paths, and resources the application needs. Do not treat a checkpoint like a portable JAR file that can be restored arbitrarily on any machine.

Because a checkpoint can contain the application's heap and memory state, it may include tokens, passwords, user data, or other sensitive information residing in memory. Control read/write permissions, protect storage, and manage retention policies and deletion procedures for old checkpoints just as you would for sensitive data.

## 9. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `Unrecognized VM option 'CRaCCheckpointTo'` | The JDK being used does not support CRaC options or the option name/syntax is wrong | Verify the CRaC JDK distribution and version; check the spelling of `-XX:CRaCCheckpointTo=<path>`. |
| `jcmd` cannot find the PID | Wrong PID used, JVM has stopped, or running in a different process namespace | Run `jcmd -l` in the correct environment; check the process manager/container and get the actual JVM PID. |
| `JDK.checkpoint` is not in the command list | The runtime does not integrate CRaC or the command is not provided in the running build | Check `jcmd <pid> help`, the JDK version, and the distribution's documentation. |
| Cannot write checkpoint | Invalid path, missing permissions, filesystem or environment does not meet requirements | Check user permissions, storage space, mounts, filesystem, kernel, and CRIU configuration. |
| Checkpoint rejected by a resource | A resource was not prepared or the `beforeCheckpoint` callback failed | Read the logs and fix the resource's lifecycle; retry checkpointing when the application is in a safe state. |
| Restore fails on another host | Differences in JDK, architecture, kernel, native libraries, mounts, or environment resources | Restore on a compatible environment and check all process dependencies. |
| Application errors after restore | Resources were not recreated or the `afterRestore` callback handled them incorrectly | Check restore logs, connection pools, sockets, file handles, and background tasks. |

When investigating, record the JDK version, launch command, checkpoint path, logs from before checkpoint through after restore, and host/container environment information. This data helps distinguish errors caused by option syntax, access permissions, CRIU, or the application's lifecycle.

## 10. Operational Checklist

Before creating a checkpoint, confirm:

- [ ] Using a JDK with CRaC support and the exact version expected for restore.
- [ ] `-XX:CRaCCheckpointTo` is placed before `-jar` and points to a valid path.
- [ ] The user running the JVM has permission to write the checkpoint and storage has sufficient space.
- [ ] Kernel, CRIU, container runtime, and filesystem meet the environment requirements.
- [ ] The application has completed startup and the necessary warm-up workload.
- [ ] Resources have registered lifecycle hooks and can handle checkpoint/restore.
- [ ] There are no in-progress side effects or transactions that could cause inconsistencies upon restore.
- [ ] Protection, retention, and access methods for the checkpoint image have been defined.

After checkpointing, confirm:

- [ ] `jcmd <pid> JDK.checkpoint` completed without errors.
- [ ] Logs show that the checkpoint process succeeded.
- [ ] The checkpoint image is at the configured path.
- [ ] Restore is tested using `-XX:CRaCRestoreFrom=<path>` on a compatible environment.
- [ ] The application completes post-restore processing and passes readiness checks.
- [ ] Critical endpoints, connections, and background tasks operate normally.

## 11. Conclusion

`-XX:CRaCCheckpointTo` is a JVM option used to declare where to store the checkpoint when launching an application. It does not automatically create a checkpoint image. After the application is ready and resources are prepared, use `jcmd <pid> JDK.checkpoint` to request the JVM to perform the checkpoint. When restoration is needed, launch with `-XX:CRaCRestoreFrom=<path>` to resume the process from the saved image.

For this cycle to work reliably, it requires proper coordination of the CRaC JDK, kernel/CRIU, filesystem, access permissions, and application resource lifecycle. Verify the checkpoint with an actual restore on a compatible environment; merely seeing the checkpoint directory or seeing the launch command report no errors is not enough to prove the application can be restored successfully.
