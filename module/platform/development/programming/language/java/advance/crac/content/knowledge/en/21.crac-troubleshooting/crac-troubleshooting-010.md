# Distinguishing a Checkpoint Request Command Reporting Success from an Actually Valid Image

When creating a CRaC checkpoint, a message such as `Command executed successfully` from `jcmd` is easily mistaken to mean the JVM has produced a complete image. Those two things are not the same. The `jcmd` command sends a request to the JVM; a checkpoint image is trustworthy only when resource preparation and the native checkpoint operation have completed, image files are fully written, the artifact has not been altered or missing files, and a new process can restore and operate properly.

This is an important diagnostic point: in the `jcmd` implementation currently described in the CRaC documentation, the output of `JDK.checkpoint` always reports success; if the checkpoint fails, the information is written to the application's console. Therefore, you cannot use `jcmd` output or exit code alone as the criterion for publishing a checkpoint.

Evaluate across multiple layers of evidence: **the request was sent to the right JVM, callbacks ran successfully, the engine created the artifact, the artifact passed integrity verification, and the restore smoke test passed**. Each layer answers a different question.

## 1. Distinguishing Five Levels of Success

A checkpoint pipeline should clearly distinguish the following states:

| Level | What has happened | What is not yet proven |
|---|---|---|
| 1. Request accepted | `jcmd` or API sent the checkpoint request to the JVM | Whether callbacks completed or the engine managed to write an image |
| 2. Resource preparation passed | `beforeCheckpoint(...)` ran without reporting errors | Whether the native checkpoint engine generated complete image files |
| 3. Image creation completed | Engine wrote the image and the checkpoint operation finished per runtime | Whether the artifact is complete, uncorrupted during copying, and restorable in the target environment |
| 4. Artifact integrity passed | Directory/files exist, metadata and checksums match | Whether the image is compatible with kernel, CPU, JDK, and resources at the restore target |
| 5. Restore test passed | A new process restored, ran `afterRestore`, and passed health/smoke tests | That every future host, configuration, or workload is guaranteed to work |

Only level 5 provides direct evidence that an actual restore of the artifact was tested in a specific environment. Even when the restore test succeeds, the scope of the conclusion must still be tied to the tested JDK build, OS/kernel, CPU, container runtime, configuration, and dependencies.

## 2. Why Can `jcmd` Report Success When Checkpoint Fails?

In a typical workflow, the JVM is launched with `-XX:CRaCCheckpointTo=PATH`, and then another terminal sends the command:

```bash
jcmd <pid> JDK.checkpoint
```

The output may look like this:

```text
1563568:
Command executed successfully
```

In the implementation currently described by CRaC documentation, `jcmd` always reports success in this output. The reason is that this message is not the final verification result of the entire native checkpoint process. Actual errors may appear in the target JVM's console, including callback errors, open file descriptors, or errors from the checkpoint engine.

Therefore, treat this output as a tool-layer confirmation that the diagnostic command was processed through the attach mechanism, not as certification that a valid image was created. If using another vendor JDK or build, check the documentation for that specific build because error reporting may vary across versions.

### Verifying the Right JVM Before Sending the Command

A basic diagnostic mistake is sending the command to the wrong PID or wrong JVM. Before requesting a checkpoint, identify the process and command line:

```bash
jcmd -l
jcmd <pid> VM.command_line
```

Verify:

- The PID belongs to the right application to checkpoint.
- The process runs on the exact selected CRaC JDK.
- The JVM was launched with `-XX:CRaCCheckpointTo` pointing to the right output directory.
- A test process, sidecar, or management JVM is not mistaken for the application process.
- The user running `jcmd` has permission to attach to the target JVM.

Only then send the request:

```bash
jcmd <pid> JDK.checkpoint
```

If using the in-application API, calling `Core.checkpointRestore()` is another trigger path. The API may surface checkpoint errors to the caller as exceptions per the runtime contract; you still need to inspect logs and artifacts rather than skipping evidence at later steps.

## 3. Enabling Application Logs and Reading Errors from the Right Place

When checkpoint fails, the target JVM's console is usually the first place indicating the cause. Do not look only at the terminal running `jcmd`.

A CRaC callback may detect an unprepared resource:

```text
Exception in thread "main" jdk.crac.CheckpointException
    at jdk.crac.Core.checkpointRestore(...)
Suppressed: jdk.crac.impl.CheckpointOpenSocketException: ...
```

Common errors include:

- `CheckpointOpenSocketException`: a socket was still open when checkpoint started.
- `CheckpointOpenFileException`: a file descriptor was not closed or handled per policy.
- Exceptions from `beforeCheckpoint(...)`: the application failed to drain tasks, flush data, or bring resources to a safe state.
- Native checkpoint errors: the engine could not save part of the process state, lacked permissions, or the kernel did not support a required feature.
- Filesystem errors: unable to write image files, out of disk space, or missing permissions on the checkpoint directory.

If you need to trace the source of a file descriptor, some CRaC builds support:

```bash
java -Djdk.crac.collect-fd-stacktraces=true \
     -XX:CRaCCheckpointTo=/var/tmp/app-checkpoint \
     -jar app.jar
```

This option instructs the JVM to collect stack traces for relevant descriptors, helping trace the code that opened the resource. Verify the option exists in the JDK build in use.

Do not disable logging or close the logging system too early in `beforeCheckpoint`. If logging stops before the engine writes errors, the operations team may only see the generic `jcmd` message. Keep a safe diagnostic output channel, flush important logs, and check both stdout/stderr and log files.

## 4. Inspecting the Checkpoint Directory After the Command Runs

`-XX:CRaCCheckpointTo=PATH` specifies where the runtime writes the image. In the implementation described by CRaC documentation, the image is typically a directory containing multiple files; the directory may be created if it does not exist, yet nonexistent parent directories are not created automatically.

Before running, create the parent directory and use a fresh output path for each attempt:

```bash
mkdir -p /var/tmp/crac-runs
CHECKPOINT_DIR=/var/tmp/crac-runs/orders-2026-11-13-attempt-01
mkdir "$CHECKPOINT_DIR"
```

After the checkpoint attempt finishes, inspect the directory:

```bash
find "$CHECKPOINT_DIR" -type f -printf '%p %s bytes\n'
du -sh "$CHECKPOINT_DIR"
```

Check:

- The directory belongs to the current attempt, not an old image from a previous run.
- The image/metadata files generated by the engine and version in use are present.
- Files have reasonable sizes and are not abnormally empty.
- Total size is non-zero and consistent with the expected process footprint.
- There are no file write errors or checkpoint failure messages in the logs.
- No process/engine is still writing to the directory when you start copying or publishing.

Do not hardcode a single filename list for every runtime. Checkpoint structure depends on the engine, version, and configuration. CRaC documentation describes the image as a directory containing multiple files; use the actual structure of the running build and engine.

### Why Is Directory Existence Not Enough?

The directory may be created as soon as the JVM starts with `-XX:CRaCCheckpointTo`, before a successful checkpoint occurs. A checkpoint failing partway through can also leave behind partial files or directories. Therefore:

- An existing directory does not prove checkpoint completion.
- Having a few files does not prove the entire image was written.
- Large file sizes do not prove metadata and related files are consistent.
- An old directory can trick the pipeline into assuming a new run succeeded.

Use a new path for each attempt and mark the artifact ready only after completion evidence and a restore test. Do not reuse a shared directory and check only `test -d`.

## 5. Reading Checkpoint Engine Logs

If using the CRIU engine, the image directory may contain native logs such as `dump4.log` depending on the build/configuration. When checkpoint fails, this log can show which dump step failed and which operating system resource could not be saved.

Example log check if the file was created:

```bash
test -f "$CHECKPOINT_DIR/dump4.log" && \
  tail -n 200 "$CHECKPOINT_DIR/dump4.log"
```

The filename and level of detail depend on the engine. Not every CRaC engine uses CRIU or produces `dump4.log`; if this file is absent, check the documentation of the running engine and logs emitted by the runtime.

When logs show a native checkpoint error, check in order:

1. Is the CRIU/checkpoint engine the right version and located in the expected runtime?
2. Do required executables/helpers have the proper ownership, permissions, or SUID per vendor documentation?
3. Does the container have the capabilities, namespaces, and security profile permitting checkpoint?
4. Does the target filesystem have enough space, write permissions, and support for the required operations?
5. Does the kernel support the features used by the process/resources?
6. Is the process holding sockets, files, pipes, devices, or native resources that cannot be checkpointed?

Do not arbitrarily change system permissions just to make the command pass. Cross-check security requirements and guidance for the exact runtime/engine, especially when running in containers.

## 6. Distinguishing CRIU Environment Checks from Image Checks

The command:

```bash
criu check
```

checks the kernel features CRIU needs to dump/restore processes. Output `Looks good.` indicates the kernel satisfies the feature set checked by the command; it does not open a specific checkpoint directory to prove that the image is complete or restorable.

A specific process may use additional resources requiring other kernel features. Therefore, an environment passing `criu check` can still fail when checkpointing an application using AIO, TUN devices, namespaces, or specialized resource types.

If `crit` is available, it can read/display some metadata and statistics of CRIU images, such as processes, file descriptors, or memory mappings. This information helps investigate image structure; it does not replace an actual restore. Tool capabilities and syntax depend on the CRIU/CRIT version.

| Tool/evidence | Question it can answer | What it does not prove |
|---|---|---|
| `jcmd ... JDK.checkpoint` | Which JVM received the request? | Whether the image is complete or restorable |
| Application console/logs | What errors did callbacks and runtime report? | Whether the entire image is definitely valid |
| Inspecting files in directory | Which artifact files were written and what are their sizes? | Whether linked files are consistent and restorable |
| `criu check` | Does the current kernel have the basic CRIU features checked? | Whether a specific checkpoint artifact is valid |
| `crit` inspect | How much image metadata/statistics are readable? | Whether the process will restore and run properly |
| Checksum | Do current bytes match recorded bytes? | Whether those bytes form a valid checkpoint |
| Restore smoke test | Does the runtime read the image, recover the process, and pass test scenarios? | Whether every future host/workload is compatible |

## 7. Verifying Integrity Before Distributing Artifacts

Once checkpoint is complete and the engine is no longer writing to the output directory, create an immutable artifact package or checksums for all files. With a multi-file directory, the checksum of a single file does not represent the entire image.

Example generating a checksum manifest on Linux:

```bash
cd "$CHECKPOINT_DIR"
find . -type f ! -name CHECKSUMS.sha256 -print0 | sort -z | \
  xargs -0 sha256sum > CHECKSUMS.sha256
```

When packaging, preserve the directory structure and required file metadata:

```bash
tar -cpf checkpoint.tar -C "$(dirname "$CHECKPOINT_DIR")" \
  "$(basename "$CHECKPOINT_DIR")"
sha256sum checkpoint.tar > checkpoint.tar.sha256
```

At the destination, verify the checksum before extracting/restoring:

```bash
sha256sum -c checkpoint.tar.sha256
```

Checksums only confirm that bytes have not changed relative to the checksum manifest. They do not confirm the checkpoint was created successfully, do not check compatibility, and do not replace a restore test. If checksums are stored alongside the artifact in the same untrusted location, they also do not prove provenance on their own; use signatures or provenance attestation when you need to verify an artifact was produced by a trusted pipeline.

Do not modify, rename, or remove files inside the checkpoint after checksums are generated. If repackaging is needed, compute a new checksum for the final archive and record the relationship between the archive and the release manifest.

## 8. Restore Is the Most Direct Verification

An image is proven restorable only when the runtime actually starts from that image. Use the exact JDK/runtime and an environment compatible with where it will be deployed.

Example:

```bash
java -XX:CRaCRestoreFrom=/var/tmp/crac-runs/orders-2026-11-13-attempt-01
```

The restore option replaces the normal JVM initialization path with the process state saved in the checkpoint according to the runtime. Exact invocation, engine options, and requirements for preserving the original image depend on the JDK/engine/vendor; follow the documentation of the build that created the image.

During the restore test, confirm:

1. The JVM reports no errors reading the image or metadata.
2. The runtime recovers the process and executes `afterRestore(...)`.
3. Resources are recreated: database pools, sockets/listeners, clients, schedulers, and exporters if used by the application.
4. The application loads the right configuration/secrets for the restore test environment.
5. Readiness switches to accepting only after required dependencies are healthy.
6. A smoke test request traverses a real business path and receives the expected result.
7. Logs show no delayed errors, hung threads, or stale resources after the first request.

If the restored process launches yet `afterRestore` fails, the image may be readable yet the application cannot serve traffic. If callbacks complete yet the first request fails due to stale pools/sockets/caches, the artifact still does not meet release criteria.

### Running Restore Tests in an Isolated Environment

Restore can resume a process carrying pre-checkpoint identities, consumers, schedulers, or state. Do not test restoring a copy of a production checkpoint into the same production network without controlling side effects. Use a canary/test environment, isolated dependencies, distinct instance IDs, and endpoints that do not dispatch real messages or transactions.

A good restore test should verify both recovery capability and post-recovery application behavior without causing duplicate jobs, message consumers, or leases alongside live serving instances.

## 9. Evidence Matrix for Deciding Whether to Release an Artifact

The pipeline should store results per layer instead of a single `checkpointSuccess` flag:

| Check | Stored evidence | Pass criteria |
|---|---|---|
| Target process | PID, command line, JDK build, checkpoint path | Right JVM and right output path |
| Request trigger | Command, timestamp, `jcmd` output or API result | Request sent; do not treat this as final result |
| Application callback | `beforeCheckpoint` logs, exceptions/suppressed exceptions | Resource preparation complete, no remaining errors |
| Native engine | Engine logs and exit/result per runtime | Engine confirms dump operation finished |
| Artifact directory | File list, sizes, timestamps, total size | New image created completely per engine format |
| Integrity | Checksums, manifest, artifact digest | Bytes uncorrupted and unaltered during distribution |
| Restore | Restore logs, callbacks, exit/result | New process launched from the exact image |
| Application smoke test | Health/readiness, sample request, dependency check | Application serves properly after restore |
| Compatibility | JDK, OS/kernel, CPU, engine, container metadata | Within the tested set of environments |

An artifact can be in the `CREATED` state yet not `VERIFIED`. Only promote to `VERIFIED` or an equivalent status after the restore smoke test and application checks pass.

## 10. Example Manual Verification Workflow

The example below illustrates a workflow on Linux with a CRaC JDK using the CRIU engine. Replace the JDK path, app JAR, PID, and directory for your real environment.

### Terminal 1 — Launching the Checkpointable Application

```bash
mkdir -p /var/tmp/crac-runs
CHECKPOINT_DIR=/var/tmp/crac-runs/orders-attempt-01
mkdir "$CHECKPOINT_DIR"

"$JAVA_HOME/bin/java" \
  -XX:CRaCCheckpointTo="$CHECKPOINT_DIR" \
  -jar target/orders-service.jar
```

Wait for the application to start, warm up, and enter the checkpoint-ready state. Capture the process logs.

### Terminal 2 — Identifying the Process and Sending the Request

```bash
"$JAVA_HOME/bin/jcmd" -l
"$JAVA_HOME/bin/jcmd" <pid> VM.command_line
"$JAVA_HOME/bin/jcmd" <pid> JDK.checkpoint
```

The `Command executed successfully` output is only a `jcmd`-layer signal. Return to terminal 1 and read the application logs. Wait for the runtime/engine to finish the attempt according to the build's semantics.

### Checking the Artifact and Logs

```bash
find "$CHECKPOINT_DIR" -type f -printf '%p %s bytes\n'
du -sh "$CHECKPOINT_DIR"

if [ -f "$CHECKPOINT_DIR/dump4.log" ]; then
  tail -n 200 "$CHECKPOINT_DIR/dump4.log"
fi
```

Cross-check results against application logs. If there is an exception or engine error, do not publish the directory even if it contains some files.

### Restore Test

Run on a compatible test environment:

```bash
"$JAVA_HOME/bin/java" \
  -XX:CRaCRestoreFrom="$CHECKPOINT_DIR"
```

Wait for `afterRestore`, health checks, and the request smoke test. Only after that create the release package, checksums, and promotion manifest.

The commands above are a reference workflow for builds supporting the corresponding options. Some vendors/engines differ in storage, logging, process retention, or restore options; always consult the actual runtime documentation.

## 11. Diagnosing by Observed Symptoms

| Symptom | Possible cause | Investigation path |
|---|---|---|
| `jcmd` reports success yet no image files exist | `jcmd` does not reflect native errors; wrong output path; callback/engine failed | Read JVM console, verify `CRaCCheckpointTo`, check engine logs and directory timestamps |
| Directory exists yet is empty | Directory created at startup or checkpoint did not start/failed | Use a new path, inspect application logs and engine logs |
| Directory has partial files | Checkpoint interrupted, out of space, or write error | Do not publish; check logs, disk quota, and engine state |
| `CheckpointOpenSocketException` occurs | Listener/client socket still open | Find resource owner, stop server/client in `beforeCheckpoint` |
| `CheckpointOpenFileException` occurs | File descriptor unclosed or disallowed by policy | Use FD stack traces, identify owning library and lifecycle |
| `CheckpointException` with native error occurs | Engine, kernel, privileges, or native resource incompatible | Read stack trace, `dump4.log`, permissions/capabilities, and kernel support |
| Image complete yet restore reports missing CPU features | Restore host lacks compatible CPU feature set | Use a matching host or configure CPU features per runtime guide |
| Restore reports missing file/mapping | Filesystem, mounts, binaries, or native dependencies differ from creation env | Compare paths, mounts, permissions, image digests, and native libraries |
| Restore succeeds yet readiness does not come up | `afterRestore` or dependency recreation failed | Read application logs, inspect pools, endpoints, credentials, and resource state |
| Restore works yet first request fails | Stale cache/client/socket or wrong readiness ordering | Run smoke test along dependency graph, open traffic after health check |
| Checksum mismatch after download | Artifact corrupted or altered during copy | Re-download from trusted source, verify digest and storage pipeline |

## 12. Factors Making an Image Unrestorable Even When Files Exist

An image with all files present and valid checksums can still fail to restore because byte integrity is different from runtime compatibility.

### Runtime and Operating System

- The JDK vendor/build at restore differs from the image creation build.
- OS libraries or native ABIs have changed.
- The kernel or checkpoint engine lacks required features.
- Container runtime, namespaces, cgroups, or security profile differ.
- CPU architecture or CPU features are incompatible.

### Filesystem and Off-Process Resources

- Files, mounts, or paths saved in the checkpoint no longer exist.
- Permissions/ownership changed.
- Native libraries or drivers have the wrong version.
- Sockets/peers, databases, brokers, or service registries are no longer in a valid state.
- Credentials or certificates have expired.

### Application State

- `beforeCheckpoint` did not fully drain requests/tasks.
- Background workers still hold locks or native resources.
- Cache/static state contains endpoints or identities of the old environment.
- `afterRestore` did not recreate clients or update readiness in the proper order.

Therefore, checking image files and checksums are necessary steps, yet do not replace restore testing across the target environment group.

## 13. Protecting and Managing Checkpoint Artifacts

A checkpoint can contain the application's heap and native memory, including tokens, passwords, sessions, private keys, request data, or caches. Artifacts must be protected as sensitive data.

- Restrict read access to the checkpoint directory and artifact repository.
- Do not publish checkpoints to public registries.
- Encrypt at rest/in transit according to security requirements.
- Use checksums to detect corruption and signatures/provenance to verify origin.
- Use separate versioned paths for each attempt/release.
- Do not overwrite verified checkpoints.
- Do not copy artifacts while the engine is still writing.
- Set retention policies and revocation/deletion procedures for old artifacts.
- Do not use a preparation-environment checkpoint containing production secrets if new secrets can be issued after restore.

A technically valid artifact may still not be permitted for release if it contains secrets or data disallowed for distribution. Image validity and security approval are two separate criteria.

## 14. Avoiding Checks That Lead to False Conclusions

**Relying solely on `Command executed successfully`.** This output does not prove checkpoint success; read the JVM console and confirm engine output.

**Checking only `jcmd`'s exit code.** It does not replace the JVM/native engine's checkpoint outcome in the documented implementation.

**Checking only whether the checkpoint directory exists.** The directory may be created before checkpoint or left behind from a failed attempt.

**Checking only for large total size.** Size does not prove related files are consistent or restorable.

**Running `criu check` and marking the image valid.** This command checks kernel feature support, not a specific image directory.

**Generating checksums and skipping the restore test.** Checksums only confirm bytes have not changed, not that the runtime can restore the process.

**Testing restore on a differently configured developer machine and concluding the artifact is corrupted.** First compare JDK, kernel, CPU, filesystem, engine, and resource environments; the failure may come from an incompatible host.

**Reusing the directory from a previous run.** Old files can cause the pipeline to mistake a failed attempt for a new checkpoint. Use a fresh path and a manifest tied to the attempt ID.

## 15. Designing Pipeline States for Checkpointing

Instead of a boolean `success` variable, you can use explicit states:

```text
REQUESTED
   |
   v
PREPARING_RESOURCES
   |
   v
ENGINE_WRITING
   |
   v
IMAGE_CREATED
   |
   v
INTEGRITY_VERIFIED
   |
   v
RESTORE_TESTED
   |
   v
APPROVED_FOR_RELEASE
```

Each step should record a timestamp, release ID, process/runtime identity, log reference, and artifact digest when available. If a step fails, transition to `FAILED` or `REJECTED`, retain logs for investigation, and do not promote the artifact.

Example verification manifest:

```yaml
checkpoint:
  attemptId: orders-2026-11-13-001
  status: RESTORE_TESTED
  applicationImageDigest: sha256:IMAGE_DIGEST
  jdkBuild: crac-jdk-full-build-version
  engine: criuengine
  outputPath: checkpoint/orders-2026-11-13-001
  artifactDigest: sha256:CHECKPOINT_DIGEST
  commandRequestedAt: "2026-11-13T06:00:00Z"
  imageCreatedAt: "2026-11-13T06:00:12Z"
  restoreTest:
    status: PASSED
    environment: approved-linux-node-group
    smokeTest: PASSED
```

These values are placeholders. The pipeline must record status from real results; do not set `RESTORE_TESTED` solely because the checkpoint command or checksum succeeded.

## 16. Checklist for Distinguishing Command Success from Image Validity

### Before Sending the Command

- [ ] Verified the right PID/JVM and JDK build.
- [ ] JVM has `-XX:CRaCCheckpointTo` pointing to the right output path.
- [ ] Parent directory exists and output path is dedicated to the new attempt.
- [ ] Process logs are being collected and are readable after triggering.
- [ ] Warm-up, drain, and resource lifecycle have been prepared.

### After Sending the Command

- [ ] Do not rely solely on `Command executed successfully` as the final result.
- [ ] Read the target JVM's console/logs.
- [ ] No `CheckpointException`, suppressed resource exceptions, or native engine errors.
- [ ] The engine completed its write operation per runtime semantics.
- [ ] Checkpoint directory contains new artifacts, not leftover files from a previous run.
- [ ] Files have reasonable sizes and total size is appropriate.
- [ ] Inspected `dump4.log` or engine logs if present.

### Before Release

- [ ] Artifact was checksummed after the engine finished writing.
- [ ] Checksum was verified after copying/downloading.
- [ ] Manifest matches the checkpoint to the right application image/JDK/runtime.
- [ ] Restore test was performed in a compatible environment.
- [ ] `afterRestore` completed and dependencies were recreated.
- [ ] Health/readiness and request smoke test succeeded.
- [ ] Artifact was promoted only after the restore test passed.
- [ ] Checkpoint is protected as an artifact that may contain sensitive data.

## 17. Conclusion

The `Command executed successfully` message from `jcmd` is not a certification of a valid checkpoint image. In the implementation described by CRaC documentation, `jcmd` may always report success while actual errors appear on the JVM console. Confirm the right process, read application/engine logs, inspect the new checkpoint directory, evaluate files and metadata, compute checksums after the engine finishes writing, and then restore using a new process.

`criu check` only checks kernel support; checksums only check bytes; an existing directory only proves a path exists. The strongest evidence is a restore test in a compatible environment, successful recovery callbacks, and the application passing health and smoke tests. Only when all those steps are satisfied should a checkpoint be marked verified and released.

## References

- [CRaC — Checkpoint and restore](https://crac.org/use/checkpoint-and-restore/): describes `-XX:CRaCCheckpointTo`, output of `jcmd JDK.checkpoint`, the warning that `jcmd` currently always reports success while errors are logged on the application console, and how to restore with `-XX:CRaCRestoreFrom`.
- [CRaC — Debugging failures](https://crac.org/reference/debugging/): examples of `CheckpointException`, file descriptor/socket errors, CRIU engine permission requirements, and `dump4.log` location.
- [CRIU — Check the kernel](https://criu.org/CLI/cmd/check): explains how `criu check` checks kernel features needed for CRIU.
- [CRIU — CRIT](https://criu.org/CRIT): describes the tool for reading and displaying metadata/statistics of CRIU images.
- [Azul — Debugging CRaC Failures](https://docs.azul.com/crac/usage/debugging.html): guide for investigating native checkpoint/restore and file descriptor errors.
