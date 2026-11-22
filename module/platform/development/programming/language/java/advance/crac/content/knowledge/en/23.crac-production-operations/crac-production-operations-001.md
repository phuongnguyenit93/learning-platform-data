# Designing a Pipeline to Build, Warm Up, Checkpoint, and Verify the Application

A production CRaC pipeline needs to do more than launch a JVM and invoke a checkpoint command. It must produce a reproducible application, run a safe warm-up, bring resources into an appropriate state, create a complete checkpoint image, verify the image in a compatible environment, and publish the artifact only when verification steps pass.

The pipeline should treat a checkpoint image as an immutable deployment artifact bound to a specific build, JDK/CRaC runtime, platform configuration, and image-creation environment. If the build changes, the runtime changes, or a dependency is no longer compatible, the old image may become unusable even if the files still exist and the checksum still matches.

Overall flow:

```text
Source + dependencies
        |
        v
Build application artifact
        |
        v
Create pinned runtime/container image
        |
        v
Start application in checkpoint environment
        |
        v
Warm up classes, JIT, caches and safe resources
        |
        v
Verify warm-up and application readiness
        |
        v
Quiesce and prepare CRaC resources
        |
        v
Create checkpoint image
        |
        v
Package + manifest + checksum/signature
        |
        v
Restore in a clean compatible test environment
        |
        v
Smoke tests + readiness + performance checks
        |
        v
Publish immutable artifact and promote
```

The key point is separating **build succeeded**, **warm-up succeeded**, **checkpoint succeeded**, **restore succeeded**, and **application ready to serve** into independent states. One step must never be treated as automatic proof of the next step.

## 1. Pipeline Goals and Boundaries

The pipeline must answer four questions:

1. **Which build is this image created from?** It must be traceable to source commit, application artifact, dependencies, JDK/CRaC runtime, and configuration.
2. **Has warm-up genuinely finished?** Measurable criteria are required, not just waiting a fixed duration.
3. **Can the checkpoint image be restored?** A trial restore in a compatible environment is needed, checking callbacks and resources.
4. **Does the application work properly after restore?** Health checks and business smoke tests are needed, not only checking whether the process is alive.

A pipeline typically has two types of artifacts:

| Artifact | Contents | Purpose |
| --- | --- | --- |
| Application/runtime artifact | JAR, dependencies, container image, or base filesystem | Provides the exact code and runtime to create/restore the checkpoint. |
| CRaC checkpoint artifact | Checkpointed process state | Fast startup from a warmed-up state. |

The two artifacts must be linked by a manifest. Do not publish a checkpoint independently of the runtime image it depends on. A deployment needs to know the exact image/container digest, checkpoint ID, and corresponding compatibility profile.

## 2. Choosing a Pipeline Architecture: Build Once, Checkpoint in a Standard Environment

An easily controllable model is:

- Build the JAR/container image from a specific source commit.
- Use a runtime image with pinned JDK/CRaC versions and native dependencies.
- Launch the application in a dedicated environment for warm-up and checkpointing.
- Store the checkpoint in separate staging.
- Run a trial restore using the exact runtime image and compatible configuration.
- Only after the restore test succeeds should the checkpoint be published alongside metadata.

Do not rebuild source or download new dependency versions during the warm-up step. If code or dependencies change between build and checkpoint creation, the artifact is no longer reproducible.

Checkpoints can be created in a CI runner, in a dedicated Kubernetes job, or in a separate build service environment. The choice depends on CRaC/CRIU support for kernel, container runtime, privileges, cgroups, filesystems, and CPUs. An ordinary runner does not necessarily have sufficient capabilities to checkpoint/restore containers.

If CI does not support CRaC, split the pipeline into two stages: CI builds and publishes the runtime image; a checkpoint builder with a compatible environment pulls that immutable image, warms up, creates the image, and sends the result back to the artifact registry. Both stages must use the same build ID and manifest.

## 3. Pinning Versions So Images Are Reproducible

A checkpoint depends on more factors than the JAR. The manifest should record at minimum:

- Git commit and application build version.
- JAR checksum or container image digest.
- JDK vendor, version, build, and CRaC implementation.
- CRaC API/library version and important JVM flags.
- CRIU version/capabilities if the platform uses CRIU.
- OS distribution, kernel version, and CPU architecture/feature baseline.
- Container runtime, Kubernetes version, and security configuration if applicable.
- Native libraries, agents, JNI/JNA dependencies, and key drivers.
- Mount layout, filesystem type, UID/GID mapping, and required cgroup configuration.
- Warm-up profile, dataset version, and checkpoint configuration.

Do not pin dependencies only in Maven/Gradle. Pin base images by digest, OS packages, and the JDK runtime as well. If using mutable tags like `latest`, two pipeline runs may create images from different runtimes even when the source commit is unchanged.

Example image configuration using a specific digest:

```dockerfile
FROM registry.example.com/java-crac-runtime@sha256:<immutable-digest>

WORKDIR /opt/myapp
COPY build/libs/myapp.jar /opt/myapp/myapp.jar

ENTRYPOINT ["java", "-XX:CRaCCheckpointTo=/var/lib/myapp/checkpoint", "-jar", "/opt/myapp/myapp.jar"]
```

The digest in the example is a placeholder. JVM flags and checkpoint paths must match the JDK/runtime in use. Do not place secrets in Dockerfiles, image layers, or command lines; inject secrets at runtime via the environment's security mechanism.

## 4. Separating Build, Warm-Up, and Checkpoint into Stateful Jobs

The pipeline should represent states explicitly so a step can be retried without accidentally reusing incomplete data.

| Job | Input | Output | Success condition |
| --- | --- | --- | --- |
| Build | Source commit, lockfile, build config | JAR and runtime image | Build/tests succeed; digest and checksum recorded. |
| Provision | Runtime image and checkpoint profile | Ready environment | Kernel/runtime/capabilities/mounts match. |
| Start | Runtime image, config without fixed secrets | Running process | Startup health passes. |
| Warm-up | Process and warm-up workload | JVM/caches in target state | Warm-up criteria and workload assertions pass. |
| Prepare | Warmed-up process | Quiesced resources | Workers/transactions/resources prepared within deadline. |
| Checkpoint | Prepared process | Checkpoint directory | Runtime confirms checkpoint completed. |
| Package | Checkpoint directory | Archive, manifest, checksum | Files/metadata preserved and checksum matches. |
| Restore validation | Runtime image + checkpoint | Test result | Restore callbacks, readiness, and smoke tests pass. |
| Publish | Verified artifact | Immutable checkpoint artifact | Artifact registry records published state. |
| Promote | Published artifact | Deployment reference | Canary/rollout policy accepts. |

Each job should have its own attempt ID, structured logs, and clear outputs. Do not use a single fixed checkpoint directory across multiple jobs running in parallel.

## 5. Preparing the Warm-Up Environment

Warm-up needs to run in an environment configured closely to the production restore environment, yet should not use unnecessary production data or privileges.

Factors to match or declare:

- JDK/CRaC runtime and JVM options.
- CPU architecture and feature baseline.
- Container user, UID/GID, capabilities, and cgroup limits.
- Mount paths, filesystems, working directory, and file permissions.
- Environment profile, feature flags, and application configuration.
- Schema/database client version and API contracts.
- DNS/service discovery/network policies at a compatible level.
- Secret provider identity and post-restore credential issuance method.

It is not necessary to use the same production database for warm-up. A staging database or representative fixture data can be used. If warming up connections against a real dependency is required, use a least-privilege account and controlled test data.

The goal is creating useful JVM state upon restore while preserving the ability to refresh external resources that have changed. Do not warm up by stuffing large amounts of sensitive data into caches merely to make the checkpoint look "warm".

## 6. Designing a Representative Warm-Up Workload

Warm-up should exercise the application's critical code paths:

- Load classes and initialize the framework/DI container.
- Initialize serializers, mappers, validators, and templates.
- Execute a representative set of requests for critical APIs.
- Exercise hot code paths so the JVM has an opportunity to JIT-compile them.
- Load reference caches that can be safely retained across checkpoints if freshness policies permit.
- Prepare metadata and lookups containing no production data.
- Initialize shared data structures.

You do not necessarily have to run every API. Choose workloads based on traffic profiles and business criticality. A warm-up profile can declare routes, request types, iteration counts, fixture data, concurrency, and latency criteria.

Example YAML profile:

```yaml
warmup:
  profile: standard-api-v3
  timeout: 5m
  concurrency: 4
  scenarios:
    - name: health-read
      method: GET
      path: /internal/catalog/sample
      iterations: 20
      expectedStatus: 200
    - name: search-validation
      method: POST
      path: /internal/search
      fixture: search-small.json
      iterations: 30
      expectedStatus: 200
    - name: pricing-calculation
      method: POST
      path: /internal/pricing/preview
      fixture: pricing-fixture.json
      iterations: 20
      expectedStatus: 200
```

This is an illustrative pipeline schema, not a format automatically understood by Spring Boot or CRaC. The project's warm-up runner must parse the profile, bound payloads, and verify responses.

## 7. Avoiding Side Effects During Warm-Up

Warm-up must not accidentally create real transactions. A request might send emails, debit funds, publish messages, update data, increment counters, or spawn background jobs.

Control measures:

- Use fixture data and test tenants.
- Use preview/dry-run endpoints if supported by the application.
- Disable outbound notifications or point them to a mock sink.
- Use a dedicated database/schema for warm-up.
- Use a dedicated broker/topic or a consumer that does not execute real business actions.
- Disable schedulers that generate production work in the warm-up profile.
- Attach test idempotency keys and clean up data after warm-up.
- Do not use credentials with production write privileges if only class/JIT warm-up is needed.

Do not rely solely on an environment variable `WARMUP=true` if business code does not genuinely honor it. Test that side effects are blocked at the appropriate layer.

If warm-up needs to populate caches, identify which data is allowed to remain after checkpoint. Caches containing permissions, credentials, user data, or rapidly changing data should be invalidated/refreshed per policy in `afterRestore`.

## 8. Measuring Warm-Up Instead of Merely Sleeping

A pipeline should not wait `sleep 60` and assume the JVM is warmed up. JIT compilation time depends on CPU, workload, compiler, and application state. Warm-up needs clear completion conditions.

Criteria that can be used:

- Startup readiness is reached.
- All warm-up scenarios finish with expected statuses.
- Minimum execution counts are reached.
- p95/p99 latency stabilizes across consecutive measurement windows.
- Error rate is 0 or within defined thresholds.
- CPU/JIT activity drops to a steady baseline per profile if suitable telemetry is available.
- Cache hit ratio or target entry count reaches threshold if caches are warmed up.
- No warm-up requests or background tasks remain unfinished.

Example criteria:

| Metric | Illustrative condition |
| --- | --- |
| Scenario completion | 100% of mandatory scenarios succeed. |
| Error rate | 0 errors across mandatory warm-up requests. |
| p95 latency | Below configured threshold across 3 consecutive windows. |
| Warm-up duration | Does not exceed pipeline timeout. |
| Background work | No warm-up tasks still writing data. |
| Readiness | `ACCEPTING_TRAFFIC` before starting checkpoint preparation. |

Thresholds must come from the application's and runner's baseline. Do not use one global latency value for every service.

## 9. JIT Warm-Up and Workload Stability

The JVM compiles code according to method hotness and runtime profiling. Too short a warm-up may fail to warm critical code paths; an unrepresentative warm-up may optimize rarely used paths by mistake.

Recommendations:

- Run critical routes/operations with representative input shapes.
- Use concurrency close to the production model yet bounded to avoid overload.
- Measure multiple windows to recognize when latency stabilizes.
- Record the warm-up profile version to compare across builds.
- Avoid warming up with purely random data if it exercises code paths unlike production.
- Avoid calling only health endpoints; health checks usually do not exercise critical business logic.

JIT compilation has no single flag or metric proving the whole application is optimized. The practical goal is reducing startup cost and stabilizing critical code paths, then measuring post-restore performance with an independent workload.

## 10. CRaC Resources Must Be Prepared Before Creating the Image

Warm-up may open connections, start workers, create schedulers, or populate caches. Before checkpoint, resources that cannot be kept intact across restore must be closed or transitioned to a safe state.

A `Resource` can coordinate:

- Stopping acceptance of new requests/messages.
- Draining active requests, transactions, and workers.
- Stopping schedulers so no new work is generated.
- Flushing durable data per policy.
- Closing sockets, connection pools, or clients that cannot continue.
- Retaining logical configuration and factories needed to recreate resources.

After restore, the `afterRestore` callback can:

- Refresh DNS, secrets, credentials, and endpoints.
- Create new connection pools/clients.
- Restart schedulers/consumers in order.
- Revalidate caches/versions and dependency status.
- Open readiness only after mandatory resources are operational.

Do not treat a successful warm-up as a reason to keep all sockets or credentials inside the image. A warm-up can warm classes/JIT and safe caches while network connections are closed before checkpoint and recreated after restore.

## 11. Example Resource Preparing and Recovering Resources

The following example illustrates separating warm-up from resource lifecycle. The interfaces are application abstractions:

```java
import org.crac.Context;
import org.crac.Resource;

public final class ApplicationCracResource implements Resource {
    private final WorkCoordinator work;
    private final DependencyFactory dependencies;
    private final ReadinessGate readiness;

    public ApplicationCracResource(
            WorkCoordinator work,
            DependencyFactory dependencies,
            ReadinessGate readiness) {
        this.work = work;
        this.dependencies = dependencies;
        this.readiness = readiness;
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        readiness.refuseTraffic();
        work.stopAcceptingNewWork();
        work.drainWithTimeout();
        dependencies.closeCheckpointSensitiveResources();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        dependencies.refreshConfigurationAndReconnect();
        dependencies.validateRequiredServices();
        work.resume();
        readiness.acceptTraffic();
    }
}
```

`drainWithTimeout()` and `refreshConfigurationAndReconnect()` must have finite deadlines. In a real implementation, roll back if `beforeCheckpoint` fails or the checkpoint is aborted; do not use `afterRestore` as a rollback callback. `acceptTraffic()` runs only after all mandatory dependencies are ready.

If the Spring Boot version already provides CRaC integration for lifecycle components, do not register an extra coordinator doing the same thing. Check ownership of each Resource to avoid closing or starting the same pool twice.

## 12. Triggering Checkpoint from the Pipeline

Once warm-up and preconditions are met, the pipeline asks the JVM to take a checkpoint. How to trigger it depends on the JDK/CRaC distribution and runtime. Some environments support diagnostic commands via `jcmd`, for example:

```bash
jcmd <pid> JDK.checkpoint
```

Confirm the command exists in the runtime using `jcmd <pid> help` or documentation for the JDK in use. Command name, execution permissions, process namespaces, and completion semantics can depend on distribution/version.

The application can also invoke CRaC APIs in code via the corresponding library/runtime, such as `org.crac.Core.checkpointRestore()`. Verify exact APIs and exception types against the actual CRaC dependency. Do not call checkpoint arbitrarily from a production request path; use a dedicated control path with authentication, authorization, and pipeline state.

The pipeline must await the result according to runtime semantics:

- Record the timestamp when the checkpoint request is sent.
- Wait for the command/operation to finish or receive checkpoint-success status.
- Inspect JVM/CRIU logs and the output directory.
- Confirm no writers are still writing the checkpoint.
- Distinguish command exit code from image success status.
- On timeout, do not immediately copy the directory or delete the image; first check whether the runtime/process is still running.

Some APIs may pause the calling thread until the process is restored; some out-of-process control methods may report results differently. The pipeline must follow specific runtime documentation rather than assuming all checkpoint commands share identical exit behavior.

## 13. Creating Checkpoints in a Separate Staging Directory

Each pipeline run needs its own checkpoint path:

```text
/var/lib/myapp/crac/
├── staging/
│   └── build-<build-id>/
│       └── attempt-<attempt-id>/
└── published/
    └── build-<build-id>/
```

Do not reuse a directory that might still hold files from a previous attempt. Before creating the image, verify filesystem space and permissions of the user running the JVM. The path must exist or be created as required by the runtime, have proper owner/permissions, and reside on a supported filesystem.

If checkpointing fails, mark the attempt as `FAILED` or `INCOMPLETE`; do not use that directory as input for restore validation. Retain logs per retention policy for investigation, then clean up after ensuring no process is still writing.

## 14. Verifying That a Checkpoint Has Completed

Do not use a single condition such as "directory exists" or "image file present" to determine success. The pipeline should combine:

- Operation outcome per runtime API/command.
- Exit status and JVM/CRIU logs.
- Process state per checkpoint mode semantics.
- Output structure and metadata expected by the runtime.
- Reasonable size/file count compared to baseline, used only as an anomaly check.
- No processes remaining writing to the checkpoint directory.

If the runtime supports an official status/metadata command, use that command instead of guessing from filenames. Do not edit or delete internal checkpoint files to make the pipeline "pass".

## 15. Packaging and Generating the Manifest

Once checkpoint completion is confirmed, the pipeline can archive the directory in a way that preserves required file metadata. If restore expects the original directory tree, extraction must preserve exact relative paths without adding extra directory levels.

The manifest should link:

| Group | Fields |
| --- | --- |
| Identity | Artifact ID, build ID, checkpoint attempt ID, createdAt UTC. |
| Source | Git commit, JAR checksum, container image digest. |
| Runtime | JDK vendor/build, CRaC version, JVM flags, CRIU version. |
| Platform | OS, kernel, CPU architecture/features, container runtime. |
| Warm-up | Profile ID/version, scenario count, duration, result summary. |
| Checkpoint | Callback results, checkpoint command/API, result status. |
| Package | Archive format, compression, size, SHA-256, signature. |
| Validation | Restore test environment, restore duration, readiness result, smoke test version. |
| Promotion | Registry location, artifact state, and deployment reference. |

Do not include secrets, access tokens, passwords, private keys, or user data in the manifest. If warm-up uses a fixture dataset, store only the version/hash and name of fixtures cleared for publication.

Compute checksums after archiving finishes:

```bash
sha256sum checkpoint.tar > checkpoint.tar.sha256
sha256sum --check checkpoint.tar.sha256
```

Checksums detect file modification/corruption during storage and transfer. They do not prove the image is compatible or that restore succeeds.

## 16. Restore Validation in a Clean Environment

An image should be published only after undergoing a trial restore in a compatible environment. This test should use a clean sandbox that shares no state with the builder and has no other processes occupying required namespaces/resources.

Conditions that must match:

- Identical runtime image digest or a proven compatibility profile.
- Compatible JDK/CRaC/CRIU, kernel, and CPU baseline.
- Required container configuration, user, mounts, cgroups, and namespaces.
- Dependency test endpoints and secret provider test identity.
- Fully extracted checkpoint path with proper permissions.

Do not restore into a traffic-serving production environment merely to validate an artifact. Use an isolated test instance with staging dependencies or test doubles.

## 17. Post-Restore Smoke Tests

After restore, the pipeline must verify both the process and the application:

1. Process restores successfully, JVM continues running.
2. `afterRestore` callbacks finish; no mandatory Resource fails.
3. DNS/secrets/config are refreshed if they can change.
4. Connection pools/clients are recreated and health checks pass.
5. Message consumers/schedulers start in the right order if within warm-up scope.
6. Readiness switches to accepting traffic once mandatory dependencies operate.
7. API smoke tests return expected results.
8. Read/write business tests produce no unexpected side effects.
9. Error rates and latencies are within thresholds.
10. No logs contain secrets or ignored callback errors.

Do not consider process `RUNNING` sufficient. Use readiness endpoints, per-dependency health indicators, and a representative set of requests. Liveness should check whether the process can continue operating; do not make liveness directly depend on every external dependency because that can trigger a restart storm when a service has a temporary outage.

## 18. Post-Restore Performance Checks

The goal of CRaC is often reducing startup time and improving time-to-readiness. Measure the exact same workload before and after applying checkpoints.

Milestones to measure:

- Process launch/restore start.
- Start and end times of `afterRestore`.
- Reconnect duration per dependency.
- Time readiness is reached.
- Time to first successful request.
- p50/p95/p99 latency of the smoke workload.
- Post-restore CPU and memory.
- Number of retries or errors during the initial window.

Compare against a cold-start baseline using the same runtime image, resource limits, dependencies, and workload. If a checkpoint reduces JVM startup while `afterRestore` spends a long time reconnecting, actual RTO may not improve as expected.

Do not set performance thresholds based on a single run. Use multiple measurements under identical conditions and appropriate percentiles. Record the warm-up profile and runner hardware to explain variance.

## 19. Canary and Artifact Promotion

Once restore validation passes, publish the checkpoint as an immutable artifact. Do not overwrite old artifacts or swap contents under the same artifact ID.

A promotion workflow can be:

1. Publish the checkpoint and runtime image digest to the registry.
2. Attach `VALIDATED` status after restore smoke tests.
3. Deploy a canary instance using the exact artifact ID.
4. Check readiness, error rates, latency, and dependency behavior.
5. Gradually increase traffic percentage if the canary passes.
6. On failure, roll back the deployment pointer to a known-good artifact/runtime pair.
7. Retain previous artifacts within the rollback window.

Do not promote merely because the checksum matches or process restore succeeded. Confirm the post-restore application genuinely serves requests.

## 20. Rollback and Old Checkpoints

An old checkpoint may be incompatible with current database schemas, secret versions, DNS, or service APIs. Therefore, rolling back is not as simple as pointing to an old checkpoint.

Before allowing rollback, confirm:

- The application build remains compatible with the database schema.
- The secret provider can issue current credentials.
- Endpoints/service APIs still support the old version.
- Caches/leases/tokens in the image will be invalidated or refreshed.
- Runtime/kernel/CPU compatibility still holds.
- Message consumer offsets and event schemas will not reprocess data incorrectly.

A rollback can use the old runtime image yet create a new checkpoint from that build in the current environment. For systems with schema migrations, use expand-and-contract to preserve compatibility during the rollback window.

## 21. Security in the Pipeline

A checkpoint can contain secrets and user data in the heap. Warm-up can also load payloads and caches into memory. Therefore, the pipeline must protect both the builder environment and artifacts:

- Use a secret manager or workload identity; do not hardcode secrets in pipeline YAML, Dockerfiles, or command lines.
- Use test credentials with least privilege.
- Do not warm up with production data without an approved protection mechanism.
- Do not print full environment variables or system properties to logs.
- Encrypt checkpoints at rest and in transit.
- Restrict read, copy, restore, and delete permissions.
- Audit artifact access.
- Maintain appropriate retention; delete staging and old artifacts based on references/leases.
- Do not paste checkpoints/heap dumps into tickets or ordinary chat.
- Sign manifests if release provenance verification is required.

Do not assume closing a pool or clearing a secret variable before checkpoint removes every copy from the heap. Design the pipeline to limit secrets loaded into the builder process and use post-restore credential refresh mechanisms.

## 22. Illustrative Pipeline YAML Example

The snippet below describes a tool-neutral pipeline structure, not copy-paste syntax for GitHub Actions, GitLab CI, or Jenkins. Each step must be translated into jobs/tasks for the actual CI engine:

```yaml
pipeline:
  build:
    steps:
      - checkout_source
      - resolve_locked_dependencies
      - run_unit_tests
      - build_application
      - build_runtime_image
      - record_build_manifest

  checkpoint:
    needs: build
    environment: crac_compatible_builder
    steps:
      - verify_runtime_and_kernel
      - create_unique_attempt_directory
      - start_application
      - wait_for_startup_readiness
      - run_warmup_profile
      - verify_warmup_criteria
      - request_checkpoint
      - verify_checkpoint_completion
      - package_checkpoint
      - generate_checksum_and_manifest
      - upload_to_staging

  validate:
    needs: checkpoint
    environment: compatible_restore_sandbox
    steps:
      - download_immutable_candidate
      - verify_checksum_and_manifest
      - verify_compatibility
      - extract_checkpoint
      - restore_application
      - wait_for_after_restore_and_readiness
      - run_smoke_tests
      - measure_restore_to_ready
      - publish_validation_result

  publish:
    needs: validate
    when: validation_success
    steps:
      - publish_immutable_artifact
      - update_deployment_reference
      - retain_previous_release
```

The pipeline engine must enforce dependency ordering, retry policies, and clear cleanup. If a checkpoint job is retried, generate a new attempt ID or have a mechanism confirming the previous attempt has finished and the staging directory is no longer in use.

## 23. Conceptual Shell Orchestration Example

An orchestration script can check each step and stop immediately when conditions fail. The following example only illustrates sequence; replace commands and health endpoints to match the real runtime/application:

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_PID="${APP_PID:?APP_PID must be set}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:?CHECKPOINT_DIR must be set}"
WARMUP_URL="${WARMUP_URL:?WARMUP_URL must be set}"

curl --fail --silent "$WARMUP_URL/actuator/health/readiness"

# Warm-up runner executes the versioned profile and exits non-zero on failure.
./bin/run-warmup --profile standard-api-v3 --timeout 5m

# Confirm the warm-up runner has no outstanding work before checkpoint.
./bin/verify-warmup-state

# Runtime-specific command; confirm support on the selected CRaC JDK.
jcmd "$APP_PID" JDK.checkpoint

# The orchestrator must wait for the runtime's documented completion signal
# before packaging CHECKPOINT_DIR.
./bin/verify-checkpoint-complete "$CHECKPOINT_DIR"

tar --xattrs --acls --numeric-owner -cpf checkpoint.tar \
    -C "$(dirname "$CHECKPOINT_DIR")" "$(basename "$CHECKPOINT_DIR")"

sha256sum checkpoint.tar > checkpoint.tar.sha256
```

This script is not a complete implementation for every CRaC JDK. Specifically, `JDK.checkpoint` and how checkpoint completion is determined must be verified per distribution/version; `verify-checkpoint-complete` is a pipeline-specific script. Do not run `tar` until the runtime confirms checkpointing is complete and no writers remain. In environments subject to shell interruption, manage process state and cleanup explicitly rather than assuming `set -e` handles every failure mode.

## 24. Managing Pipeline State and Retries

Checkpoint jobs typically consume significant time and resources. Uncontrolled retries can create multiple images, overwrite artifacts, or leave incomplete directories behind.

A state machine should be used:

```text
BUILDING
   |
   v
BUILT
   |
   v
WARMING
   |
   v
WARMED
   |
   v
PREPARING
   |
   v
CHECKPOINTING
   |
   v
CHECKPOINTED
   |
   v
PACKAGED
   |
   v
RESTORE_VALIDATING
   |
   +---- failure ----> REJECTED
   |
   v
VALIDATED
   |
   v
PUBLISHED
   |
   v
PROMOTED
```

Each transition must log timestamp, attempt ID, and outcome. Do not transition to `CHECKPOINTED` merely because the trigger command was sent; there must be evidence the runtime finished. Do not transition to `VALIDATED` if only the checksum passed without running a trial restore.

Retries are appropriate for transient infrastructure failures such as runner unavailable or storage upload timeouts. If a warm-up scenario fails due to an application bug, do not retry endlessly. If a checkpoint operation's state is unclear, before retrying inspect the process/runtime and staging directory of the previous attempt.

## 25. Pipeline Observability

The pipeline should emit structured metrics and logs for each stage:

- Build duration, test results, image digest, and JAR checksum.
- Provision duration, kernel/runtime compatibility results.
- Startup duration and readiness transitions.
- Warm-up profile ID, scenario count, request count, error rate, and latency percentiles.
- Callback duration per Resource and remaining workers/transactions.
- Checkpoint duration, result code, image size, and disk usage.
- Package/compression duration, upload throughput, and checksum results.
- Restore duration, `afterRestore` duration, and dependency reconnect times.
- Restore-to-ready duration, smoke test results, error rate, and latency.
- Artifact state, retention deadline, and deployment reference.

Tag all logs with build ID, checkpoint attempt ID, and artifact ID. Do not use secrets, request payloads, or user IDs as metric labels. If a step fails, log the specific error class/code and component to simplify root-cause analysis.

## 26. Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Warm-up job passes yet post-restore performance does not improve | Workload unrepresentative or calls only health endpoints | Build profile from critical code paths and measure post-restore latency. |
| Checkpoint image incompatible with target host | Differing JDK/kernel/CPU/CRIU/runtime | Pin compatibility profiles and run restore tests before publishing. |
| Image missing files or corrupted | Pipeline copies while checkpoint is still writing | Wait for completion signal and confirm no writers remain. |
| Application restores yet readiness not reached | Dependencies unready, old secrets, or stale pools/sockets | Refresh/reconnect in `afterRestore`, readiness gate, and retry deadline. |
| Warm-up creates real data | Workload calls APIs with side effects | Use fixtures, dry-run, test tenants, and dedicated sinks. |
| Identical build produces different checkpoints | Runtime/base image/dependencies unpinned or non-deterministic warm-up | Record digests, pin toolchain, and version warm-up profiles. |
| Pipeline retries create junk artifacts | Shared attempt ID/path or unclear state | Use separate directories per attempt and a state machine. |
| Restore test passes yet production deployment fails | Validation environment differs in CPU/kernel/mounts/secrets/network | Match compatibility profile closely to production and check drift. |
| Readiness opens too early | Pipeline only waits for process alive or callback return | Wait for dependency health and smoke tests before accepting traffic. |
| Rollback to old checkpoint fails | Schemas, credentials, or APIs changed | Verify compatibility and maintain a controlled rollback window. |

## 27. Pipeline Design Checklist

- [ ] Build from a specific source commit and dependency lockfile.
- [ ] Pin JDK/CRaC, CRIU, base image digest, native dependencies, and platform profile.
- [ ] Link the application artifact and checkpoint image via a manifest.
- [ ] Use a checkpoint environment compatible with the restore target.
- [ ] Use a versioned warm-up profile and representative workload.
- [ ] Warm-up causes no production side effects and loads no unnecessary sensitive data.
- [ ] Have measurable warm-up criteria, not only a fixed sleep.
- [ ] Check startup readiness before warm-up and warm-up completion before prepare.
- [ ] Stop accepting work, drain workers/transactions, and prepare Resources within deadline.
- [ ] Trigger checkpoint only after preconditions pass.
- [ ] Wait for runtime confirmation that checkpointing completed before copying/compressing.
- [ ] Each attempt uses its own staging directory.
- [ ] Create archive, checksum, manifest, and signature if needed.
- [ ] Run a trial restore in a clean, compatible sandbox.
- [ ] Verify `afterRestore`, dependencies, readiness, and smoke workloads.
- [ ] Measure restore-to-ready and post-restore performance.
- [ ] Publish an immutable artifact only after validation passes.
- [ ] Have canary, rollback, and retention policies.
- [ ] Protect checkpoints because memory may contain secrets and user data.
- [ ] Have a state machine, retry policy, cleanup, and observability per job.

## 28. Conclusion

A reliable CRaC pipeline must tightly link building, runtime, warm-up, resource preparation, checkpointing, packaging, restore validation, and promotion. Builds must be reproducible; warm-up environments must be compatible and use safe workloads; checkpoints must be taken only after the application satisfies warm-up criteria and resources are ready; images must be published only after checksums, compatibility, and restore smoke tests pass.

Manage each attempt with its own identifier, store complete manifests, measure time from restore to readiness, and deploy artifacts using canary/rollback. CRaC can reduce startup time, yet its benefits are reliable only when the pipeline proves the image can restore in the target environment and the post-restore application genuinely serves business logic properly.
