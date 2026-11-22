# Cold-Start Fallback When Restore Conditions Are Not Met

CRaC (Coordinated Restore at Checkpoint) allows a Java application to resume from a pre-prepared state, thereby reducing startup time. However, a checkpoint can only be restored when the runtime, checkpoint image, and target environment meet compatibility conditions. The artifact may be missing or corrupted, the JDK may have a different build, the kernel or architecture may not match, container resources may be insufficient, or a required dependency may fail to recover.

A well-operated service needs a fallback startup path using a normal JVM. When restore cannot be performed safely, the system skips the checkpoint and starts the application from scratch with the same deployment configuration, then waits for readiness like a fresh startup. The fallback mechanism must be placed in a launcher, supervisor, or orchestrator capable of observing the restore outcome. If an error occurs before application code resumes executing, the restoring process itself usually has no opportunity to decide to run main() again.

It is important to distinguish restore errors from external service failures. A cold start can overcome an incompatible checkpoint or stale connection state, but it cannot fix a database being down, wrong credentials, or broken application configuration. This lesson presents how to design fallback, classify errors, run pre-restore checks, bound retries, ensure only one instance receives traffic, and measure the effectiveness of the fallback startup path.

## 1. Why Is Cold-Start Fallback Needed?

A checkpoint is created at a specific time and environment. Upon restore, the runtime must recover the process state and supported resources. Conditions can change between the two points in time:

- Checkpoint directory was deleted, upload missed files, or artifact is corrupted.
- Manifest does not match the JDK vendor, version, build, or application build.
- CPU architecture, OS, kernel, CRIU, or container runtime is incompatible.
- Target container's cgroup memory/PIDs limit is lower than actual demand.
- File descriptors, sockets, mounts, or network resources cannot be restored.
- Credentials, tokens, DNS, endpoints, or secrets have changed.
- afterRestore() callback cannot reconnect to dependencies.
- Checkpoint was created from an old configuration or schema that is no longer accepted.

If the system only has a restore path, an error in these cases can prevent the instance from starting. Cold-start fallback provides a second path: launch a fresh JVM, load the current configuration, initialize the Spring/application context, and recreate resources following the normal lifecycle.

~~~text
                 Start instance
                       |
                       v
              Checkpoint available?
                 /           \
               No             Yes
               |               |
               v               v
         Start fresh       Verify artifact
              JVM           and target
               |               |
               |          Eligible?
               |           /      \
               |          No       Yes
               |          |         |
               |          |         v
               |          |    Attempt restore
               |          |         |
               |          |    Restore succeeds?
               |          |      /       \
               |          |     Yes       No
               |          |      |         |
               |          +------+---------+
               |                 |
               +-----------------+
                       |
                       v
                Start normally
                       |
                       v
               Dependency checks
                       |
                       v
                  Readiness
                       |
                       v
                 Receive traffic
~~~

The diagram illustrates decisions at the supervisor level. How restore is actually invoked depends on the JDK distribution and platform. Not every CRaC runtime shares the same CLI, exit codes, or process handoff behavior.

## 2. Two Types of Fallback to Distinguish

There are two distinct error groups, and they need to be handled at two different layers.

**Restore cannot start or fails before the application resumes execution.** For example, the runtime cannot read the checkpoint, the artifact is incompatible, CRIU rejects the restore, or the kernel does not support a resource. At this stage, the restored process's application main() has not resumed. Fallback must be performed by an external launcher, supervisor, or orchestrator.

**The process has been restored, but the application does not reach a ready state.** For example, the afterRestore() callback fails when reconnecting to the database, the credential provider cannot obtain a token, or the web server cannot bind an endpoint. At this point, the process may exist but cannot serve traffic. The application should attempt resource recovery under a bounded policy; if the state is unrecoverable, the process must exit or be terminated by the supervisor before the supervisor launches a fresh JVM.

Do not let a restored but failing process keep running in parallel with a new cold-start JVM. If both register consumers, run schedulers, or process jobs, the system can produce duplicate side effects.

## 3. Why Can't the Restoring Process Always Fall Back on Its Own?

Restore is typically a runtime- and operating-system-level operation. The runtime must load the process state before Java threads resume at the checkpointed point. If the state-loading step fails, application code does not continue executing to catch an exception and invoke main() again.

Therefore, the architecture should include a component external to the restored process:

- Container entrypoint or wrapper script.
- Process supervisor.
- Orchestrator controller or init system.
- Deployment platform with a mechanism to attempt restore and then switch to the standard startup command.

This component can inspect the artifact, invoke the restore operation, and detect whether the process was launched successfully. When restore fails to produce a manageable process, the supervisor selects cold start.

Some runtimes integrate restore into the JVM launch command or provide a dedicated API/launcher. In that case, use the exact mechanism supported by the vendor to distinguish a restore failure from an application exit. Do not assume all failures are represented by the same Java exception or exit code.

## 4. Placement of Fallback in the Deployment Architecture

A common pattern is placing the startup mode selection logic in the container entrypoint or supervisor:

~~~text
Container / VM supervisor
        |
        +---- Checkpoint metadata and integrity
        |
        +---- Check target compatibility
        |
        +---- Attempt CRaC restore
        |          |
        |          +---- Success -> monitor restored application
        |
        +---- Restore unavailable/failed
                   |
                   v
             Start fresh JVM
                   |
                   v
             Monitor readiness
~~~

The supervisor needs to retain control over the application's lifecycle. It must know which process is running, which process has exited, which process reached readiness, and when it can switch startup modes.

If the restore command daemonizes the process or returns before the application is ready, the wrapper needs to track the PID/process group or use a readiness protocol provided by the runtime. Do not treat a command exit code of 0 as proof that the application is ready to serve.

## 5. Criteria for Choosing Restore or Cold Start

Do not blindly attempt restore for every artifact present on disk. Before invoking the runtime, the supervisor can check inexpensive metadata:

- Does the artifact exist and include all required files?
- Is the manifest valid and verified?
- Does the artifact match the right application, build, and environment?
- Does the JDK vendor/version/build comply with the compatibility policy?
- Are the OS, architecture, kernel, and checkpoint engine compatible?
- Do cgroup CPU, memory, and PIDs meet the verified minimum levels?
- Is the checkpoint too old or revoked?
- Are the encryption key and restore identity available?
- Is the artifact generation allowed to be restored?

Preflight only eliminates cases that clearly fail eligibility. It cannot prove restore will succeed, because some errors appear only when the runtime actually loads the process state or when resource recovery callbacks run.

The preflight result should include a clear reason, such as ARTIFACT_MISSING, SIGNATURE_INVALID, RUNTIME_MISMATCH, RESOURCE_PROFILE_UNSUPPORTED, or CHECKPOINT_EXPIRED. Do not record only a boolean eligible flag.

## 6. Checking Runtime and Application Compatibility

A checkpoint is typically tied to the runtime and environment that created it. An internal manifest may store:

| Field | Purpose |
|---|---|
| artifactId | Unique identifier of the checkpoint |
| applicationBuild | Application version |
| jdkVendor | JDK vendor |
| jdkVersion/build | Exact version and build |
| cracRuntime | CRaC runtime/engine version |
| os/architecture | Operating system and architecture |
| kernel/runtime profile | Supported platform conditions |
| resourceProfile | CPU, memory, PIDs, and related limits |
| createdAt | Creation timestamp |
| generation | Prevents reusing old artifacts if policy requires |
| integrity/signature | Authenticates origin and contents |

This manifest is metadata defined by the deployment pipeline, not a standard CRaC schema. Authenticate the manifest before trusting its fields. If the compatibility check fails, fall back to cold start and record the specific reason.

Do not compare only the Java major version string. Two JDK builds both reporting Java 21 may differ in vendor, patches, build, or CRaC implementation. Use an organization-verified compatibility matrix or official vendor documentation.

## 7. Checking the Resource Profile Before Restore

A checkpoint can contain heap, native memory, threads, and runtime decisions formed in the source environment. Restoring into a container with smaller limits can cause OOM or prevent creating additional threads.

Before restoring, compare:

- CPU quota and cpuset.
- JVM availableProcessors used at checkpoint creation.
- Memory limit and expected headroom.
- Maximum heap and usage at checkpoint.
- Direct memory, metaspace, code cache, and thread stacks.
- PIDs limit.
- Disk space for restore staging.
- Required network access and filesystem mounts.

An unsuitable target profile should be marked ineligible for restore. Cold start can select heap sizing and concurrency matching the new limits, provided the JVM starts with appropriate flags. However, cold start also cannot run stably if the container truly lacks resources for the workload.

Do not arbitrarily lower the memory limit and expect fallback to always rescue the instance. The cold-start path must be benchmarked under the same resource limits.

## 8. Checking the Artifact Before Invoking Restore

Preflight should verify that the artifact was completely published:

1. Checkpoint operation reported completion.
2. Required file list is complete.
3. File sizes are non-zero unless explicitly defined.
4. Manifest matches the file list and artifact ID.
5. Checksum, MAC, or signature is valid.
6. Artifact is not marked incomplete, revoked, or expired.
7. Storage object version matches the manifest.
8. Read and decryption permissions are available to the restore workload.

If the artifact is encrypted, verify metadata and KMS permissions before decrypting. Do not pass an artifact with an invalid signature or AEAD authentication failure to the runtime. Mark the artifact as faulty or quarantine it per policy so the system does not repeatedly retry the same broken image.

Preflight does not replace checks performed by the CRaC runtime. An artifact that passes checksum verification may still be incompatible with the kernel or contain unrecoverable resource state.

## 9. Classifying Errors to Decide Fallback

Not every error should trigger cold start immediately. Classification helps avoid futile retries and prevents hiding configuration errors.

| Error Group | Example | Typically Appropriate Action |
|---|---|---|
| Artifact missing | File deleted, not yet published | Cold start |
| Artifact corrupt/unauthenticated | Missing files, invalid checksum/tag/signature | Quarantine artifact, cold start |
| Incompatible runtime | Different JDK build, architecture, or engine | Cold start; update compatibility metadata |
| Insufficient resources | Memory/PIDs below profile | Cold start if profile supports it; otherwise fail explicitly |
| Restore engine failure | CRIU/kernel/resource restore failure | Log diagnostics, cold start if error is non-transient |
| Transient dependency error | KMS, metadata, database, or DNS timeout | Bounded retry or wait for dependency; do not default to cold start |
| Application configuration error | Wrong property, incompatible schema | Fail fast; cold start would likely hit the same error |
| afterRestore callback failure | Client reconnection fails | Bounded recovery attempt; then stop process and fall back |
| Readiness timeout | Dependency or worker not ready | Diagnose cause; stop process before switching mode |

For example, a missing artifact is a clear reason to skip restore. Conversely, a few-second KMS timeout may be transient; an immediate cold start would still need KMS or the secret manager and fail identically. Use bounded retry/backoff for transient dependency failures.

## 10. Retry Policy Before Cold Start

Retrying restore can help when errors are caused by transient storage/network issues, but retrying an incompatible artifact usually just repeats the same failure.

A sound policy distinguishes:

- **No retry:** invalid signature, missing artifact files, incompatible JDK/architecture, revoked checkpoint.
- **Short bounded retry:** storage timeout, transient artifact download failure, KMS throttling, or identified transient errors.
- **Do not switch to cold start immediately:** essential dependency is unavailable if cold start also depends on the same dependency.
- **Cold start after restore failure:** runtime cannot restore the artifact and the application can start cleanly.
- **Fail deployment:** neither restore nor cold start meets minimum conditions or configuration is invalid.

Use exponential backoff with jitter for transient errors. Set a maximum total retry time so the instance does not wait indefinitely. Record the attempt count and the reason for each attempt.

Do not retry infinitely inside the same container. Doing so can hold resources, slow down rollouts, and cause the orchestrator to repeatedly restart the pod.

## 11. Cold Start Must Use the Same Current Application Configuration

When switching to standard startup, use the application artifact and configuration released for the current deployment. Do not treat old configuration from checkpoint metadata as the source of truth for values that should change.

The cold-start path must:

- Run the exact supported JDK runtime.
- Use the same deployed application build.
- Load current environment variables, ConfigMaps/secrets, or config services.
- Create a new instance identity.
- Resolve fresh credentials.
- Create new connection pools and clients.
- Initialize the Spring ApplicationContext from scratch.
- Run migrations or startup tasks following idempotent rules.
- Warm up if necessary.
- Reach readiness before accepting traffic.

Do not let cold-start fallback accidentally run a different JAR file, a different profile, or different Java flags than intended for the deployment. If cold start is an official operational path, it must be tested as an independent startup mode.

## 12. Do Not Blindly Reuse Stale Business State

A checkpoint may contain heap state from image creation time. If restore fails and the application cold-starts, that heap state will not exist. Data required to resume work must be stored in a durable system.

Business design should ensure:

- Critical progress is committed to a database or durable store.
- Jobs can resume from saved business checkpoints or cursors.
- Side effects have idempotency keys or operation IDs.
- Message consumers commit offsets with proper semantics.
- Schedulers and leader election acquire new leases.
- Never rely on a static variable or in-heap object as the sole source of progress.
- Startup tasks can rerun safely or have a mechanism to determine completion.

If restore fails, cold start may execute startup hooks again. Hooks that create accounts, send emails, create schemas, or publish messages must be idempotent or have clear transaction boundaries.

## 13. Handling afterRestore Errors and Readiness

Runtime restore may succeed while a resource fails to recover. For example, a connection pool cannot reconnect, a token expired, DNS changed, or a file mount does not exist.

Some applications can recover in place by recreating clients or connections. If a resource cannot recover after the permitted number of attempts:

1. Keep the instance in the not-ready state.
2. Stop accepting new requests and jobs.
3. Log the resource ID and root error.
4. Attempt recovery with bounded timeout/backoff.
5. If recovery fails, exit the process with an exit code or error state recognized by the supervisor.
6. The supervisor terminates the restored process completely.
7. Only then does the supervisor launch a cold-start JVM.
8. The cold-start path recreates resources from current configuration and checks readiness.

Do not let a callback swallow exceptions and report restore success if essential dependencies are not working. Also do not open traffic merely because an HTTP port is bound; readiness must verify the dependencies requests actually need.

## 14. Preventing Two Processes from Running Simultaneously During Fallback

A major risk is the supervisor starting a cold JVM while the old restored process is still alive. Both could:

- Consume the same message group or partition simultaneously.
- Run the same scheduled job simultaneously.
- Hold the same lease or contend for a distributed lock.
- Receive traffic through the same endpoint simultaneously.
- Execute migrations or startup tasks simultaneously.
- Overwrite data or produce duplicate side effects.

Before cold-starting after a post-restore failure, ensure the old process has exited or been terminated and is no longer receiving traffic. The orchestrator must manage process identity and readiness. For workloads with exclusive ownership, use leases and fencing tokens to stop stale processes from continuing side effects.

Do not rely solely on an old PID file, as PIDs can be reused. The supervisor must track process handles, process groups, container lifecycles, or a reliable platform management mechanism.

## 15. Example Supervisor Pseudocode

Exact restore commands vary by JDK vendor and platform, so the example below describes the contract of a wrapper provided by the deployment team. The restore-wrapper must return an explicit outcome: either restore could not start, or the supervisor took over and is monitoring the restored process.

~~~bash
#!/usr/bin/env bash
set -u

APP_JAR="/app/app.jar"
CHECKPOINT_DIR="/checkpoint/current"

log() {
  printf '%s %s\n' "$(date -Iseconds)" "$*"
}

if [ -d "$CHECKPOINT_DIR" ] && /app/bin/verify-checkpoint "$CHECKPOINT_DIR"; then
  log "Checkpoint passed preflight; attempting restore"

  /app/bin/restore-wrapper "$CHECKPOINT_DIR"
  restore_rc=$?

  if [ "$restore_rc" -eq 0 ]; then
    log "Restore supervisor completed normally"
    exit 0
  fi

  log "Restore failed with code $restore_rc; selecting cold start"
else
  log "No usable checkpoint; selecting cold start"
fi

exec java \
  -XX:MaxRAMPercentage=60 \
  -jar "$APP_JAR"
~~~

This is an illustrative skeleton, not a script usable directly for every CRaC distribution. Clearly define the exit contract of restore-wrapper. If the restore command succeeds and detaches the process, the wrapper must continue monitoring that process and must not launch a second JVM. If the process is restored but readiness later fails, the supervisor must stop the old process before entering the cold-start path.

In a container environment, the entrypoint shell can use exec to replace the shell with the cold-start JVM. When both the restored process and the cold process must be managed, a dedicated supervisor or the orchestrator's process management mechanism may be needed instead of a simple script.

## 16. Java Example for Preflight Decision

The application can define a preflight result with an explicit reason. This runs before calling runtime restore, inside a launcher or control component that can execute before process restoration.

~~~java
public record RestoreEligibility(
        boolean eligible,
        String reason) {
}

public interface CheckpointInspector {
    RestoreEligibility inspect(
            String checkpointPath,
            RuntimeProfile target);
}

public record RuntimeProfile(
        String jdkVendor,
        String jdkBuild,
        String os,
        String architecture,
        long memoryLimitBytes,
        int cpuCapacity) {
}
~~~

An inspector implementation can read the verified manifest and compare it against the current RuntimeProfile. Do not write a naive version-string comparison yourself and treat it as a compatibility guarantee. Compatibility policies must be built from runtime documentation and verified configurations.

Example decision logic:

~~~java
RestoreEligibility eligibility =
        inspector.inspect(checkpointPath, currentProfile);

if (!eligibility.eligible()) {
    logger.warn("Skipping CRaC restore: {}", eligibility.reason());
    return StartupMode.COLD;
}

return StartupMode.RESTORE;
~~~

This is mode selection logic at the launcher layer. It cannot replace actual restore verification by the runtime.

## 17. Keeping the Cold-Start Path Simple and Independent

Cold start must be maintained even when most production instances use checkpoints. Do not test only restore and neglect normal startup.

A good cold-start path should:

- Use the official application entrypoint.
- Be able to run in the same container image without requiring a checkpoint directory.
- Not require restore artifacts to start.
- Recreate all clients/sockets/pools from current configuration.
- Refresh credentials and identity.
- Start schedulers/consumers according to the readiness gate.
- Not re-execute non-idempotent side effects.
- Have explicit timeouts and health/readiness probes.
- Be triggerable via a startup mode or deployment flag.

Do not let cold start depend on an environment variable produced only by the checkpoint pipeline. Configurations needed for the application to start from scratch must be packaged or provided by the deployment environment.

## 18. Cold Start Is Not Always the Right Option

Fallback has limits. There are failures that cold start cannot resolve:

- The database or message broker is down.
- KMS/secret manager is unreachable and the application needs it to start.
- Wrong application image or missing dependencies.
- Invalid production configuration.
- Container memory limit is too low even for cold start.
- JDK runtime cannot run the application.
- Incompatible database schema.
- Network policies block all paths to dependencies.

In these cases, cold start will likely fail the same way. The system should report the error clearly and let the orchestrator retry per policy or halt the rollout. Do not use fallback as a way to mask infrastructure or configuration errors.

Three final outcomes can be distinguished:

- RESTORE_READY: restore succeeded and the instance is ready.
- COLD_START_READY: restore was not used; standard startup succeeded.
- STARTUP_FAILED: neither path met serving conditions.

Metrics and logs must retain the final startup mode so operations know which path the instance is running on.

## 19. Timeouts and Startup Budgets

Set separate timeouts for each phase:

- Artifact discovery/preflight.
- Download and integrity verification.
- Restore engine.
- afterRestore resource recovery.
- Cold JVM startup.
- Application warm-up.
- Readiness.
- Total startup deadline.

Cold start is typically slower than restore. If startup probes or orchestrator timeouts are set assuming every instance restores quickly, fallback may be killed before the application finishes starting.

Conceptual budget example:

| Phase | Timeout to Consider |
|---|---|
| Preflight | Short enough to reject bad artifacts quickly |
| Artifact download/decrypt | Based on image size and network |
| Restore attempt | Based on baseline restore p95 and safety margin |
| Cold start | Based on startup p95 in target resource profile |
| Dependency readiness | Based on actual timeouts of external services |
| Total startup | Covers phases and bounded retries |

Do not apply a single number across all applications. Use cold-start and restore-to-ready benchmarks to configure startup probes, liveness probes, and orchestrator deadlines. A readiness failure does not necessarily require restarting the process immediately; liveness failure is typically what triggers restarts per policy.

## 20. Updating Checkpoints After Cold Start

If a checkpoint fails or becomes incompatible, do not continue using it for every startup. Mark the artifact as stale/quarantined and schedule creating a new checkpoint from a cleanly started instance.

A flow could be:

1. Restore fails and the artifact is marked unused.
2. Cold start succeeds.
3. The application reaches readiness and warms up.
4. The pipeline creates a new checkpoint matching the compatibility profile.
5. The new artifact is verified, published, and tagged with a new generation.
6. The old artifact is retained or deleted per retention policy.

Do not create a new checkpoint immediately while the cold-start fallback is still serving requests or dependencies are unstable. Follow standard quiesce and resource-check procedures just like normal checkpointing.

If the old artifact failed only due to a transient storage issue, it does not necessarily need immediate deletion. Quarantining and recording the cause aids investigation. Delete only per approved retention and policy.

## 21. Deploying on Kubernetes or an Orchestrator

In Kubernetes, a container can run an entrypoint wrapper to choose restore or cold start. The orchestrator still manages restarts, readiness, liveness, and rollouts. Probes must be configured with enough time for both modes.

Some principles:

- The readiness probe succeeds only when the application can genuinely serve requests.
- The startup probe allows cold start to take longer than normal liveness intervals.
- Liveness should not fail solely because an external dependency is temporarily failing if the process can still recover.
- A Pod that is not ready receives no traffic from the Service under standard readiness mechanisms.
- Rolling updates need sufficient surge capacity so cold-start fallback does not exhaust capacity.
- The checkpoint volume and access permissions must be ready before the entrypoint attempts restore.
- Logs must distinguish restore attempts from cold-start attempts.

If using an init container to download or verify artifacts, remember that an init container only completes preflight; it cannot replace the runtime restore operation if restore needs to recover process state. Coordination must align with the CRaC runtime and container lifecycle.

## 22. Security and Integrity in Fallback

Fallback must not weaken restore security checks. If a signature is invalid or encryption authentication fails, do not decrypt/restore the artifact just to try one more time.

Some requirements:

- Verify the artifact before passing it to the runtime.
- Only authorized workload identities may read/decrypt checkpoints.
- Do not log tokens, keys, or signed URLs.
- Quarantine faulty artifacts to prevent retry loops.
- Do not automatically fetch artifacts from untrusted sources when restore fails.
- Apply the same secrets and identity policy to the cold-start path.
- Log an audit event for the decision to skip the checkpoint and the reason.
- Protect checkpoint metadata and logs, as they can disclose configuration.

Cold start must obtain fresh credentials from the identity provider rather than taking tokens stored in the checkpoint manifest. Artifact metadata can be used for compatibility checks, but it is not the source of truth for current secrets.

## 23. Observing Fallback in Production

Have separate metrics for each startup mode and each reason:

| Metric | Meaning |
|---|---|
| startup_mode_total | Number of times restore or cold start was selected |
| restore_attempt_total | Total restore attempts |
| restore_success_total | Successful restores |
| restore_failure_total{reason} | Restore failures by group |
| restore_preflight_rejected_total{reason} | Artifacts rejected before invoking runtime |
| cold_start_fallback_total{reason} | Number of fallbacks to cold start |
| cold_start_duration | Time for a fresh JVM to reach readiness |
| restore_to_ready_duration | Time from restore to readiness |
| fallback_success_total | Successful cold starts after fallback |
| startup_failure_total | Both paths failed to reach readiness |
| checkpoint_artifact_age | Age of the artifact at restore time |

Each startup log should include:

- Startup attempt ID.
- Instance/pod ID.
- Application build and JDK build.
- Checkpoint artifact ID/generation.
- Selected startup mode.
- Preflight result and reason.
- Restore exit/error classification.
- Cold-start reason if fallback occurred.
- Duration of each phase.
- Readiness result and dependency failures.

Do not label every restore failure as a generic error. Clear classification reveals whether to fix the checkpoint pipeline, runtime compatibility, resource profile, or dependencies.

## 24. Deliberate Fallback Testing

Fallback is reliable only when tested, not merely when present in code.

Scenarios to cover:

1. Missing checkpoint artifact: application cold-starts successfully.
2. Artifact missing a required file: preflight rejects and cold-starts.
3. Manifest invalid signature or checksum: artifact is quarantined, cold-starts.
4. JDK build violates compatibility policy: skips restore.
5. Unsupported architecture or runtime profile: cold-starts or fails per policy.
6. Memory/PIDs limit below threshold: preflight rejects or runtime restore fails cleanly.
7. Restore command returns error before process starts: supervisor cold-starts.
8. Restored process runs but afterRestore fails: process stays not-ready, is terminated, and cold-starts if the error is recoverable by fresh initialization.
9. External dependency down: verify cold start does not create an infinite retry loop.
10. Cold start also fails: orchestrator receives an explicit failure state.
11. Supervisor restarts mid-startup decision: does not create two processes.
12. Older artifact reintroduced: rollback policy handles it properly.
13. Multiple replicas fall back simultaneously: no duplicate jobs or consumer ownership.
14. After cold start, a new checkpoint is created and test-restored successfully.

Use test artifacts and synthetic data. Do not intentionally corrupt production checkpoints or disrupt live services to test fallback.

## 25. Example Decision Matrix

A simple matrix helps standardize behavior:

| Situation | Restore | Cold Start | Expected Outcome |
|---|---|---|---|
| No artifact | Skip | Yes | Normal startup |
| Invalid artifact | Do not attempt | Yes | Log reason, quarantine |
| Runtime mismatch | Do not attempt | Yes if cold-start runtime is valid | Fresh startup |
| Transient storage timeout | Bounded retry | After retries if policy permits | No infinite retries |
| Non-retryable restore engine error | Failed | Yes | Supervisor switches mode |
| Transient afterRestore dependency error | Already restored | Bounded recovery/readiness retry | Do not open traffic yet |
| Unrecoverable afterRestore failure | Process not ready | After terminating process | Never run two instances |
| Database down | Not solved by restore | Likely also not ready | Report dependency failure |
| Cold start configuration error | No | Failed | Fail fast, no infinite loop |

The matrix must be tailored to the runtime semantics and workload type. For certain errors, the safest policy is to fail the deployment instead of cold-starting.

## 26. Common Design Mistakes

**Placing fallback inside main() and expecting it to catch all restore failures.** The runtime may fail before Java code resumes. Use an external launcher or supervisor.

**Launching the cold JVM immediately after the restore command returns.** The restored process may already have been started or detached. Define the exit contract clearly and track the process.

**Failing to stop a restored process that is not yet ready.** A second cold JVM may run concurrently and cause duplicate side effects. Terminate the old process before switching modes.

**Infinitely retrying the same corrupted checkpoint.** The error will not disappear on its own. Classify artifact corruption and quarantine it.

**Cold-starting while the database or KMS is down.** Fresh startup still depends on those services. Retry with limits and report dependency failure.

**Using checkpoint metadata as current production configuration.** Endpoints, credentials, and identities may be stale. Cold start must load configuration from the current deployment.

**Skipping signature or integrity verification before restore.** A tampered artifact could be passed into the runtime. Verify before restoring.

**Marking ready as soon as the process exists.** Dependencies or workers may not have recovered yet. Readiness must reflect serving capability.

**Allowing startup hooks to produce non-idempotent side effects.** Cold start may re-run hooks after a restore failure. Use operation IDs, transactions, or idempotency.

**Failing to measure fallback rate.** The system may silently cold-start almost every time. Track restore success and fallback reasons.

**Testing only the restore path.** When a checkpoint breaks, the application has no verified recovery path. Test cold start independently and test mode switching.

## 27. Fallback Operations Checklist

- [ ] Is there a launcher/supervisor external to the restore process?
- [ ] Are the restore command, exit contract, and process ownership clearly defined?
- [ ] Does preflight verify artifact completeness, integrity, and compatibility?
- [ ] Are JDK vendor/build, OS, architecture, kernel, and CRaC engine verified?
- [ ] Do CPU, memory, PIDs, and storage profiles meet verified levels?
- [ ] Are errors classified into permanent, transient, dependency, or application failures?
- [ ] Do retries have bounds on time, attempts, and backoff/jitter?
- [ ] Are faulty artifacts quarantined to prevent infinite retry loops?
- [ ] Does the cold-start path use the exact current JDK, application build, and configuration?
- [ ] Are credentials, identity, DNS, and clients created/refreshed for the current environment?
- [ ] Are startup hooks and jobs idempotent or backed by durable progress?
- [ ] Is a failed restored process terminated before the cold JVM runs?
- [ ] Does readiness succeed only when essential dependencies and workers are ready?
- [ ] Do startup probes/deadlines provide sufficient time for cold start?
- [ ] Do metrics/logs record the startup mode and fallback reason?
- [ ] Have missing/corrupt artifacts, runtime mismatches, afterRestore failures, and cold-start failures been tested?
- [ ] Has multi-replica fallback been verified not to create duplicate side effects?
- [ ] Is there a plan to create a new checkpoint after a successful cold start?

## Conclusion

Normal startup is a necessary fallback path when a checkpoint cannot be restored in the target environment. Restore can fail before application code resumes, so the fallback decision must be made in the launcher, supervisor, or orchestrator. If the process has restored but callbacks or readiness fail, perform bounded recovery or terminate that process before launching a new JVM.

Reliable design requires artifact and compatibility preflighting, error classification, bounded retries, keeping the cold-start path independent, loading current configuration and identity, and preventing two processes from running simultaneously. Cold start cannot cure dependency outages or broken application configuration; those cases must be reported clearly and handled per policy. By separately measuring restore success, fallback rate, cold-start duration, and readiness, operations teams can tell whether checkpoints deliver real benefits or whether the system frequently falls back to standard startup.