# Distinguishing Checkpoint Images, Application JARs, and Container Images

In a Java application using CRaC (Coordinated Restore at Checkpoint), there are three types of artifacts commonly referred to as "images": the application JAR, the container image, and the checkpoint image. They serve three distinct purposes.

- **Application JAR** packages Java code, resources, and metadata needed to run the program.
- **Container image** packages the filesystem, JDK/runtime, system libraries, and default configuration to create a container.
- **Checkpoint image** saves the state of a running Java process at a point in time, so a compatible runtime can restore that process.

A JAR can run on many compatible Java environments. A container image can create multiple containers from the same filesystem image. A checkpoint image is tightly coupled to the process state and the environment that created it. Therefore, these three artifacts cannot substitute for one another or be assumed to have the same degree of portability.

This article explains the content, lifecycle, dependencies, and packaging approaches for all three artifact types when deploying Java CRaC.

## 1. Three Artifact Types Solve Three Problems

### 1.1 Application JAR: Packaging the Program

A JAR (Java Archive) is a ZIP-based archive format. A JAR typically contains:

- Java bytecode compiled into .class files.
- Resources such as properties, YAML, templates, schemas, or static files.
- Metadata in META-INF.
- A manifest describing the entry point or archive information.
- Dependencies if using an executable/fat/uber JAR.

A runnable JAR typically has a manifest with a Main-Class, or is launched by a framework launcher. For example:

~~~bash
java -jar application.jar
~~~

A JAR describes the program to be run. It does not store the current heap, thread stacks, connection state, warmed-up caches, or the execution position of a running JVM.

If an application has been running for 20 minutes, the JAR is still the same file as before it ran. The state that the program accumulated in memory is not written back into the JAR.

### 1.2 Container Image: Packaging the Runtime Environment

A container image is a filesystem image in OCI format or a compatible runtime format. It typically includes:

- A base operating system or minimal root filesystem.
- JDK/JRE and runtime libraries.
- Application JAR and dependencies.
- CA certificates, timezone data, and native libraries.
- User, working directory, entrypoint, and container metadata.
- Default configuration that does not contain environment secrets.

A container image is used to create containers. Multiple containers can be created from the same image but each has its own PID, network namespace, writable layer, volumes, and runtime configuration.

A container image does not itself contain the heap state of a launched JVM. It describes the filesystem and how to start the container, not the full execution state of a specific process.

### 1.3 Checkpoint Image: Packaging Process State

A checkpoint image is an artifact created by the CRaC runtime in coordination with the checkpoint engine. It saves the state necessary to restore a process at a point in time, which may include:

- The Java heap and objects currently referenced.
- Thread state and execution position as supported by the engine.
- Native memory and process address regions as supported.
- Runtime state required to continue execution.
- Mapping information and process resources managed by the engine.

Before creating the image, CRaC invokes Resource callbacks so the application can prepare. After restoration, the callbacks re-establish resources such as files, sockets, connection pools, or external clients.

A checkpoint image is not another JAR and is not a container image in the conventional sense. It depends on the runtime, engine, and environment that created it.

## 2. Direct Comparison

| Criterion | Application JAR | Container Image | Checkpoint Image |
|---|---|---|---|
| Purpose | Package the Java program | Package the filesystem and runtime environment | Save the state of a running process |
| Main content | Classes, resources, manifest, dependencies | Root filesystem, JDK, libraries, app artifacts, metadata | Heap, thread/process state, native memory, and engine-supported state |
| When created | After compile/package | When building the container image | When a running process requests a checkpoint |
| How used | Start a new JVM | Create a container then start the entrypoint | Resume the process from the image |
| Contains warmed-up heap? | No | No, unless stored separately as an artifact | Yes, within what the engine supports |
| Contains application JAR? | It is the JAR itself | May contain the JAR | Do not treat the checkpoint as a replacement for the JAR; keep the corresponding JAR/build |
| Portability | Relatively high across compatible JDKs | Depends on OS/architecture and runtime | Limited, tied to the build and compatible environment |
| Code change | Build a new JAR | Build a new container image or update layers | Typically requires creating a new checkpoint |
| Startup | Creates a new JVM | Creates a new container and process | Resumes the process from the image |
| State source | Source code and build | Dockerfile/build context and base image | Runtime state at the time of checkpoint |

A useful summary in three sentences:

- JAR answers: **what is the program?**
- Container image answers: **what environment does the program run in?**
- Checkpoint image answers: **what state is the process in?**

## 3. Relationships Among the Three Image Types

A Java CRaC workflow typically starts with a JAR, places the JAR in a container image, then starts the container to create a checkpoint image.

~~~mermaid
flowchart TD
    A["Source code + dependencies"] --> B["Build application JAR"]
    B --> C["Build container image<br/>JDK + OS libraries + JAR"]
    C --> D["Start container and JVM"]
    D --> E["Application startup and warm up"]
    E --> F["CRaC beforeCheckpoint callbacks"]
    F --> G["Create checkpoint image"]
    G --> H["Store checkpoint artifact<br/>with compatible container digest"]
    H --> I["Create compatible container"]
    I --> J["Restore checkpoint image"]
    J --> K["CRaC afterRestore callbacks"]
    K --> L["Validate dependencies and serve"]
~~~

The JAR and container image still need to be managed even after a checkpoint image has been created. If the checkpoint cannot be restored due to an environment error, the application needs to be able to start fresh from the JAR inside the container image.

A checkpoint image also needs to be associated with the correct container image or a compatible environment. You should not take a checkpoint from one build and arbitrarily combine it with a JDK or system libraries from a different build.

### 3.1 Which Artifact Is the Source of Truth?

A build chain may have relationships as follows:

~~~text
Source revision
   |
   v
Application JAR
   |
   v
Container image digest
   |
   v
Running JVM
   |
   v
Checkpoint image
~~~

- Source revision identifies the code.
- JAR hash identifies the binary and resources.
- Container digest identifies the filesystem image.
- Checkpoint ID identifies a specific snapshot of process state.

A checkpoint image is a derived artifact from a specific container image and a specific run. Metadata must maintain this relationship for deployment, rollback, and diagnostics.

## 4. A JAR Cannot Replace a Checkpoint Image

Suppose an application takes 30 seconds to start, connect to the database, load caches, and warm up JIT.

When running from the JAR:

1. JVM starts.
2. Classes are loaded.
3. The application context is created.
4. The database connection pool is initialized.
5. The cache is loaded.
6. Critical processing paths are warmed up.
7. The application transitions to a ready state.

The JAR only contains the program and resources to perform these steps. Each time the JAR runs, the startup steps are executed according to application logic.

With CRaC, a checkpoint can be created after warm-up. When restoring, the process continues from the saved state rather than re-executing the entire startup path.

This can reduce startup time, but it does not make the JAR redundant:

- The JAR is still the binary needed for a fresh start.
- The JAR is the source identifying the code corresponding to the checkpoint.
- The JAR is used to create a new checkpoint when code changes.
- The JAR supports fallback if the checkpoint image is incompatible or cannot be restored.
- The JAR can be used to run tests or in deployments that do not use CRaC.

Do not rename checkpoint files to .jar or place a checkpoint image on the classpath. A checkpoint image is not a Java archive and cannot be loaded with `java -jar`.

## 5. A Container Image Is Not the Same as a Checkpoint Image

A container image describes the filesystem and metadata of the runtime environment. A checkpoint image saves the state of a process running in that environment.

A container image can be used to:

- Start a new JVM from the JAR.
- Create a container as the source for warm-up and checkpointing.
- Create a compatible container for restoring a checkpoint.
- Run the same JAR without a checkpoint if the deployment chooses the standard startup mode.

A checkpoint image can be stored in the container's filesystem, a volume, object storage, or a dedicated artifact repository depending on the engine and deployment workflow.

The critical point is that the container used for restoration must have a runtime and filesystem compatible with the checkpoint. Sharing the same container tag name is not sufficient if tags can be overwritten. Associate the checkpoint with an immutable container image digest.

### 5.1 OCI Images and Process Checkpoints Are Two Different Concepts

An OCI image is a packaging format for filesystem and metadata for container runtimes. A process checkpoint is the state of a process recorded by the checkpoint engine.

Some platforms may support packaging checkpoint artifacts alongside OCI artifacts or creating a new container image containing the checkpoint files. This is a deployment choice and is tooling-dependent. It does not mean a checkpoint image automatically becomes a standard OCI image or can be run as a regular container image.

It is also important to distinguish CRaC from container-level checkpoint/restore features at the container runtime layer. CRaC provides an API for Java applications to coordinate stopping and recovering resources. Container runtime checkpoints can capture container/process state at a lower layer. The two mechanisms have different goals and lifecycles; they should not be treated as the same operation.

## 6. Contents and Dependency Level of Checkpoint Images

A checkpoint image may contain much runtime state that the JAR and container image do not.

### 6.1 Java Heap

The heap may contain:

- Application context and object graph.
- Loaded caches.
- Metadata and data structures.
- Warmed-up parse or computation results.
- Some framework and library state.

These objects help reduce initialization work after restore. However, caches may be stale and objects may hold references to external resources that have changed.

### 6.2 Threads and Execution State

The checkpoint engine must save the state necessary to restore threads and resume execution. CRaC callbacks help the application bring threads and resources to a safe point before the image is created.

Do not assume that every thread state or every native thread is supported in every engine. Consult the documentation for the specific JDK build and checkpoint engine.

### 6.3 Native Memory and File Mappings

Direct buffers, native allocations, memory mappings, and JNI resources can affect the checkpoint. Some memory regions may be saved as memory pages, but file-backed mappings and native handles also depend on the filesystem, kernel, and engine.

### 6.4 File Descriptors and Connections

Sockets, database sessions, file descriptors, and kernel resources are not simply heap data. Applications typically need to close them before a checkpoint and re-establish them after restore using Resource callbacks.

### 6.5 Sensitive Data

The heap may contain:

- Access tokens and refresh tokens.
- Decrypted passwords or secrets.
- Session state.
- Private keys or credential caches.
- User data being processed.

Because a checkpoint image saves process state, it may contain sensitive data even if the container image and JAR do not contain secrets. Protect checkpoint artifacts as a highly sensitive copy of runtime data.

## 7. Portability and Compatibility Requirements

JARs, container images, and checkpoint images have different degrees of portability.

### 7.1 JAR

A JAR can run on JDKs compatible with the bytecode, APIs, and dependencies the application uses. A JAR built with Java 17 may run on a newer JDK if it does not depend on incompatible behavior or APIs, but that is not automatically true for all libraries.

A JAR does not contain OS native code by default. If an application depends on JNI, the native libraries still require the correct OS, architecture, and ABI.

### 7.2 Container Image

Container images are generally tied to OS userland and architecture. A Linux amd64 image cannot by default run on an arm64 host without a multi-arch manifest or suitable emulation mechanism.

A container image can run on many compatible host kernels, but still depends on system calls, CPU features, drivers, security policies, and the container runtime.

### 7.3 Checkpoint Image

Checkpoint images typically have a narrower compatibility range. At a minimum, verify:

| Component | Why It Matters |
|---|---|
| JDK vendor and build | Internal JVM structure and CRaC integration may differ |
| JDK version | Heap/runtime metadata and implementation change across versions |
| CRaC API/runtime | Resource callbacks and checkpoint/restore behavior depend on the runtime |
| Checkpoint engine | How process state is saved and restored differs |
| OS and kernel | Process state, syscalls, VMAs, and kernel resources are OS-dependent |
| CPU architecture | Registers, instruction set, and native code are architecture-dependent |
| CPU features | Some builds or native libraries require specific features |
| Native libraries and ABI | Libraries loaded in the process must be compatible |
| Filesystem and mounts | File-backed mappings, paths, and permissions can affect restore |
| Runtime configuration | Heap, flags, environment, and engine configuration may need to match the checkpoint |
| External dependencies | Database, DNS, secrets, and service endpoints must be re-verified |

A checkpoint image created in a development environment cannot be assumed to be restorable in production. Create and test images in an environment close to where they will be restored.

### 7.4 Multi-Architecture

If deploying to both amd64 and arm64, do not use a single checkpoint artifact for both architectures. Create separate checkpoints from the respective runtime/architecture and attach clear metadata.

Container images may have multi-arch manifests, but checkpoint artifacts still need to be classified by the actual architecture and build.

## 8. Packaging the JAR in a Container Image

A multi-stage Dockerfile can build the JAR in the first stage and place the artifact in a runtime image in a later stage.

Example:

~~~dockerfile
# Stage 1: build the application
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY pom.xml .
COPY src ./src
RUN mvn -B -DskipTests package

# Stage 2: runtime with CRaC
FROM <crac-enabled-jdk-runtime-image>
WORKDIR /app

COPY --from=build /workspace/target/application.jar /app/application.jar

USER 10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/application.jar"]
~~~

`CRAC-ENABLED-JDK-RUNTIME-IMAGE` in the example is a placeholder for a base image with a CRaC runtime and checkpoint engine appropriate for the deployment environment. Not every Temurin or OpenJDK image includes a real checkpoint engine.

The build stage can use a standard JDK if only compilation is needed, but the runtime stage must provide a compatible JDK/CRaC build to create and restore checkpoints.

### 8.1 Separating Build Stage from Runtime Stage

Multi-stage builds help to:

- Avoid including Maven, Gradle, or source code in the runtime image if not needed.
- Reduce image size.
- Separate build dependencies from runtime dependencies.
- Control the JDK used when running CRaC.

If the application uses JNI or native libraries, the runtime stage must still contain the corresponding runtime libraries. Do not accidentally copy binaries that exist only in the build stage and are not present in the runtime stage.

### 8.2 Pin the Base Image

Do not use only a mutable tag such as `latest` for the runtime image. Pin the version and digest of the base image in the build process to know exactly which JDK, libraries, and filesystem were used to create the checkpoint.

When the base image is updated, re-evaluate checkpoint compatibility. A new container image, even if only the JDK patch version or a native library changed, may not be compatible with the old checkpoint according to vendor guarantees.

## 9. The Checkpoint Artifact Creation Process

Checkpoints should be created from a process that has run inside the exact runtime/container image intended for use.

A typical workflow:

1. Build the JAR.
2. Build the container image with a CRaC-enabled JDK.
3. Start the container in a compatible environment.
4. Wait for startup to complete.
5. Initialize dependencies and run warm-up.
6. Bring the application to a checkpoint-ready state.
7. CRaC calls `beforeCheckpoint` to stop work and release necessary resources.
8. The checkpoint engine creates the image.
9. Store the checkpoint artifact and the corresponding metadata.
10. Test restore in a compatible container.

~~~mermaid
sequenceDiagram
    participant CI as Build Pipeline
    participant Registry as Artifact Registry
    participant Container as Runtime Container
    participant CRaC as CRaC Runtime
    participant Store as Checkpoint Store

    CI->>CI: Build application JAR
    CI->>CI: Build container image
    CI->>Registry: Push JAR/container artifacts
    Registry-->>Container: Pull exact image digest
    Container->>Container: Start JVM and warm up
    Container->>CRaC: Request checkpoint
    CRaC->>Container: beforeCheckpoint callbacks
    CRaC->>Store: Write checkpoint files
    Store-->>CI: Checkpoint artifact + metadata
    CI->>Store: Publish immutable checkpoint version
~~~

The details of checkpoint creation, the output location, and how to export it depend on the JDK vendor, engine, and platform. Do not assume a single command or a single checkpoint directory is the same across all builds.

### 9.1 Why Not Just Run the Checkpoint Inside the Dockerfile?

A standard Dockerfile primarily creates filesystem layers. `RUN` instructions typically execute inside a temporary build container; the process may not exist in the runtime context that production uses for restoration.

A checkpoint depends on process state, kernel, engine, filesystem, and environment. Therefore, creating a checkpoint is typically a separate step in the pipeline or a workflow that runs actual containers, rather than treating it as a simple output of the JAR build.

Some platforms have specialized checkpoint image build processes. If using them, follow the platform's tooling and maintain the association with the base image digest.

## 10. Storing and Linking Artifacts

There are multiple ways to store checkpoint artifacts:

- An artifact directory in the build workspace.
- A shared volume or filesystem.
- Object storage.
- An artifact registry that supports the appropriate artifact type.
- OCI artifacts or container image layers, as supported by platform tooling.

Not every registry treats a checkpoint image as a restorable artifact. If storing the checkpoint in a new container image, metadata and a corresponding restore process are still required.

### 10.1 Use Immutable Identifiers

A checkpoint artifact should have an immutable identifier, for example:

~~~text
application: orders-service
build: 2.8.1
jar-sha256: <digest>
container-digest: sha256:<digest>
jdk-build: <vendor-version-build>
engine: <engine-version>
architecture: linux-amd64
checkpoint-id: <unique-id>
created-at: <timestamp>
~~~

The values in angle brackets are placeholders. This metadata identifies which code, runtime, and environment the checkpoint was created from.

Do not reuse the same filename and overwrite the old checkpoint. Immutable versions support rollback, auditing, and comparing restore outcomes.

### 10.2 Example Manifest Metadata

~~~json
{
  "application": "orders-service",
  "applicationVersion": "2.8.1",
  "jarSha256": "sha256:...",
  "containerImage": "registry.example/orders@sha256:...",
  "jdk": {
    "vendor": "example-vendor",
    "version": "21.x",
    "build": "crac-build-id"
  },
  "checkpointEngine": {
    "name": "engine-name",
    "version": "engine-version"
  },
  "platform": {
    "os": "linux",
    "architecture": "amd64"
  },
  "checkpointId": "orders-2.8.1-linux-amd64-001",
  "createdAt": "2026-11-13T06:00:00Z"
}
~~~

This is an illustrative schema defined by the pipeline, not a mandatory CRaC format. You may add kernel, CPU features, config revision, schema compatibility, image checksums, and a list of external dependencies.

### 10.3 Linking the Checkpoint to the Container Digest

If the checkpoint was created from container image digest `sha256:abc...`, store that digest in the metadata. When restoring, pull the exact image digest or an image proven to be compatible.

Do not rely on the tag `orders-service:latest` as it may point to a different image after the next build.

## 11. The Restore Process

Restoration typically begins by creating a compatible container, providing the checkpoint files, and invoking the runtime/engine's restore mechanism.

A high-level flow:

~~~text
Select checkpoint artifact
   |
   v
Read checkpoint metadata
   |
   v
Verify application and runtime compatibility
   |
   v
Pull exact compatible container image
   |
   v
Prepare required mounts and environment
   |
   v
Restore process from checkpoint
   |
   v
Run afterRestore callbacks
   |
   v
Reconcile external state
   |
   v
Mark application ready
~~~

Distinguish the phases:

- **Container creation:** create the filesystem environment and namespace.
- **Process restore:** recover the JVM state from the checkpoint.
- **Resource recovery:** run `afterRestore` callbacks to reopen resources.
- **External reconciliation:** re-read current configuration, secrets, schema, leases, and service state.
- **Readiness:** open traffic only when all required conditions are met.

A container may be successfully created but the process restore may still fail. A process restore may succeed but `afterRestore` callbacks may still error. A running JVM does not yet mean the application is ready to serve.

## 12. Keeping a Fresh Startup Path as Fallback

A checkpoint artifact may be unusable because:

- The runtime or engine is incompatible.
- The checkpoint is corrupted or missing files.
- A different kernel or CPU is required.
- External file backing does not exist.
- Secrets or dependencies cannot be recovered.
- Resource callbacks fail.
- The application has a new version and the old image was revoked.

A deployment system should have a fallback path to run the JAR from a compatible container image.

~~~mermaid
flowchart TD
    A["Deployment requests instance"] --> B["Validate checkpoint metadata"]
    B --> C{"Checkpoint compatible?"}
    C -->|Yes| D["Attempt restore"]
    C -->|No| G["Fresh JVM startup from JAR"]
    D --> E{"Restore and callbacks successful?"}
    E -->|Yes| F["Reconcile and mark ready"]
    E -->|No| G
    G --> H["Run startup, migration policy and warm up"]
    H --> I["Mark ready"]
~~~

The fallback needs careful design. If a restore performed some side effects before failing, a fresh start may re-execute them. Migrations, seeding, and business operations need idempotent mechanisms or durable state.

Do not retry restore indefinitely with a checkpoint artifact that is known to be incompatible. Record the cause and switch to the fallback or create a new checkpoint.

## 13. Versioning and Invalidation

A checkpoint image is the result of a specific program version and environment. When those components change, evaluate whether the image is still valid.

### 13.1 When to Create a New Checkpoint?

A new checkpoint should generally be created when:

- The JAR or application code changes.
- Java dependencies change.
- The JDK vendor/build or CRaC runtime changes.
- The checkpoint engine changes.
- The base container image or native libraries change.
- An environment variable affecting runtime state changes.
- The startup configuration or JVM flags change.
- The CPU architecture or kernel environment changes.
- Warm-up or cache semantics change.

Some minor changes may be supported by the vendor within a certain compatibility range. However, do not extrapolate the compatibility scope on your own. Use the support matrix for the exact build and test restore.

### 13.2 Old Checkpoint with a New Database Schema

A checkpoint image may hold old code while the database has been migrated. Before restoring, verify that the schema version is within the compatibility range of the application build.

If the old code is not compatible with the new schema, do not restore the old image. Use expand/contract strategies and manage the lifecycle of checkpoint artifacts alongside deployment versions.

### 13.3 Tagging and Retention

A possible naming convention:

~~~text
orders-service/
  2.8.1/
    linux-amd64/
      container-image-digest.txt
      checkpoint-001/
      checkpoint-002/
      manifest.json
  2.8.2/
    linux-amd64/
      ...
~~~

This directory structure is not required; what matters is that each checkpoint has a unique ID and is linked to the build/runtime digest.

Set a retention policy for old checkpoints. When deleting an image, ensure that no active deployment or rollback workflow still references it.

## 14. Artifact Security

JARs, container images, and checkpoint images have different security surfaces.

| Artifact | Potentially Sensitive Data | Protection Approach |
|---|---|---|
| JAR | Code, endpoints, resources, occasionally secrets packaged by mistake | Artifact scanning, do not bake secrets, sign and control download permissions |
| Container image | OS packages, JDK, app binaries, CA certificates, and default config | Vulnerability scanning, pin digest, sign image, run as non-root |
| Checkpoint image | Heap, tokens, sessions, decrypted secrets, user data, native memory | Encrypt at rest and in transit, strict ACLs, audit access, retention and secure deletion |

A checkpoint image may contain secrets even if the application retrieves secrets from a secret manager after startup. At the time of checkpoint, secrets may already have been decrypted and placed on the heap or in native memory.

Therefore:

- Do not store checkpoint artifacts in a public bucket.
- Restrict checkpoint read access by environment and workload identity.
- Encrypt artifacts at rest and in transit.
- Do not place secrets in the manifest metadata.
- Control the copying of checkpoints between development, staging, and production.
- Delete expired artifacts according to policy.
- Treat checkpoint images as a sensitive copy of application runtime state.

Container images may be distributed more broadly than checkpoint artifacts. Not everyone with permission to pull the container image necessarily has permission to download checkpoints containing runtime data.

## 15. Reproducibility and the Build Pipeline

A good pipeline needs to produce traceable artifacts:

~~~mermaid
flowchart LR
    A["Git commit"] --> B["Build JAR"]
    B --> C["Test JAR"]
    C --> D["Build OCI image"]
    D --> E["Scan and sign image"]
    E --> F["Run CRaC warm-up job"]
    F --> G["Create checkpoint"]
    G --> H["Validate restore"]
    H --> I["Publish checkpoint + manifest"]
    I --> J["Deploy by immutable digest"]
~~~

Some principles:

- The JAR should be built from an identified source revision.
- The container image should pin the base image and dependencies.
- The checkpoint must be created from the exact image whose digest was recorded.
- Metadata must link the checkpoint ID, JAR hash, and container digest.
- Restore tests must run with the target runtime/engine.
- Publish the checkpoint only after the restore test passes according to pipeline criteria.
- Retain the corresponding container image in the registry for the entire lifetime of the checkpoint.

Do not create a checkpoint from a container that was manually modified after being pulled. If the filesystem changes, the original digest no longer accurately describes the environment that created the checkpoint.

## 16. Avoid Packaging Secrets and Environment-Specific Configuration

Container images are typically built once and then deployed to multiple environments. Therefore, do not bake credentials, production endpoints, or environment-specific data into the image.

Checkpoints, however, may contain the environment state that was loaded into the process. If an image is created in staging and then restored in production, the heap may still hold:

- Staging URLs.
- Staging feature flags.
- Staging database endpoints.
- Staging credentials.
- Staging tenant or region IDs.

Replacing environment variables in the new container does not automatically replace objects already recovered in the heap. The application needs to reconcile environment-dependent configuration after restore, or create separate checkpoints for each environment.

A checkpoint should be explicitly associated with an environment or config compatibility scope. Do not share images between environments simply because the JAR and container image are the same.

## 17. Typical Deployment Scenarios

### 17.1 JAR Only

Suitable when running the JVM directly or in environments that do not use containers.

~~~text
JAR -> JVM startup -> Application
~~~

The advantage is simplicity and ease of movement between compatible JDKs. The disadvantage is that every startup executes the full startup and warm-up sequence.

### 17.2 JAR in Container Image, Without Checkpoint

~~~text
JAR -> Container image -> New container -> New JVM
~~~

Suitable when a consistently packaged environment is needed but startup reduction via CRaC is not required.

### 17.3 JAR + Container Image + Checkpoint Artifact

~~~text
JAR -> CRaC container -> Warm-up -> Checkpoint artifact
                                         |
                                         v
                                Compatible container
                                         |
                                         v
                                      Restore
~~~

Suitable when startup time needs to be reduced for many instances and the restore environment can be controlled.

### 17.4 Separate Checkpoints per Architecture

~~~text
Application JAR
    |
    +--> linux/amd64 container --> amd64 checkpoint
    |
    +--> linux/arm64 container --> arm64 checkpoint
~~~

This approach works for clusters with multiple CPU architectures. Each checkpoint needs its own metadata and validation.

### 17.5 Separate Checkpoints per Environment

~~~text
Same application version
    |
    +--> staging runtime + staging config --> staging checkpoint
    |
    +--> production runtime + production config --> production checkpoint
~~~

Share checkpoints only if the configuration and state have been verified as safe to share. With different credentials, identities, or endpoints, separate checkpoints are generally safer.

## 18. Diagnosing Restore Failures

When a restore fails, identify which layer the error belongs to:

| Layer | Symptoms | Investigation Direction |
|---|---|---|
| Artifact | Missing files, wrong checksum, mismatched manifest | Check checkpoint ID, hash, storage, and publishing process |
| Container | Wrong digest pulled, missing files or native libraries | Check OCI digest, root filesystem, and mounts |
| Runtime | Incompatible JDK/CRaC build | Check vendor, version, flags, and engine |
| Platform | Different kernel, architecture, CPU feature, or permissions | Check host and container runtime configuration |
| Resource callback | `beforeCheckpoint`/`afterRestore` throws exception | Read the exception and suppressed exceptions |
| External dependency | DB, DNS, secrets, or service not ready | Reconnect, validate, and check readiness |
| Application state | Stale cache, config, or schema | Cross-reference revision and compatibility |

Some investigation steps:

- Verify the checkpoint artifact contains all files required by the engine.
- Check checksums and metadata.
- Verify the container digest matches the image that created the checkpoint.
- Read JVM, CRaC runtime, and checkpoint engine logs.
- Examine the exception tree from callbacks.
- Check mounts, permissions, filesystem, and file backing.
- Check external services after restore.
- Try a fresh startup from the same JAR to distinguish application errors from checkpoint errors.

If a fresh startup also fails, the root cause may be in the JAR, container, or dependencies. If a fresh startup succeeds but restore fails, focus on compatibility, process state, and the Resource lifecycle.

## 19. Operational Checklist for Each Checkpoint Release

Before releasing a checkpoint artifact, record:

- Application version and source revision.
- JAR checksum.
- Container image digest.
- JDK vendor/version/build.
- CRaC API/runtime version.
- Checkpoint engine/version.
- OS, kernel, and CPU architecture.
- Relevant JVM flags.
- Config revision and environment.
- Database schema compatibility.
- List of external resources that were prepared.
- Checkpoint ID, timestamp, and checksum.
- Restore test results.
- Restore time and readiness.
- Artifact retention and access permissions.

This checklist helps operations teams know exactly where the checkpoint was created and under what conditions it can be used. It also supports rollback when a new build cannot be restored.

## 20. Recommended Deployment Workflow

A Java CRaC packaging workflow can be carried out in the following steps:

**Step 1 — Build the JAR.** Compile the code, package resources and dependencies. Record the source revision and JAR checksum.

**Step 2 — Build the container image.** Choose a CRaC-enabled JDK runtime, copy the JAR and required native dependencies, pin the base image digest, and run as non-root.

**Step 3 — Start in the target environment.** Create a container from the exact image digest, load configuration, and check dependencies.

**Step 4 — Warm up.** Run the necessary initialization steps, bring the application to a checkpoint-ready state, and avoid accepting traffic if the process requires it.

**Step 5 — Create the checkpoint.** CRaC calls `beforeCheckpoint`, the checkpoint engine writes the process image, and the pipeline collects metadata.

**Step 6 — Link the artifacts.** Store the checkpoint with the JAR hash, container digest, JDK build, engine, OS, and architecture. Use immutable IDs.

**Step 7 — Test restore.** Create a compatible container, restore the image, run `afterRestore`, and verify external dependencies.

**Step 8 — Publish.** Publish only checkpoints that have passed restore and security checks. Keep the corresponding container image in the registry.

**Step 9 — Deploy.** Select the checkpoint by metadata, verify compatibility, and restore. If restoration is not possible, use a fresh startup from the JAR according to the fallback policy.

**Step 10 — Monitor and revoke.** Measure startup/restore time, readiness, callback errors, and manage retention of old checkpoints.

## References

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): the checkpoint/restore model and its coordinating role with Java applications.
- [CRaC — Running an Application With CRaC](https://docs.azul.com/crac/usage/running-crac): preparing the runtime and running a CRaC application.
- [CRaC — CRaC Engines](https://docs.azul.com/crac/usage/crac-engines): checkpoint engines and differences across builds.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): Resource callbacks and application lifecycle.
- [Open Container Initiative — Image Format Specification](https://github.com/opencontainers/image-spec): container image structure and metadata.
- [Open Container Initiative — Distribution Specification](https://github.com/opencontainers/distribution-spec): distributing artifacts via registries.
- [Docker — Multi-stage builds](https://docs.docker.com/build/building/multi-stage/): separating build stage and runtime stage.
- [Docker — Image digests](https://docs.docker.com/dhi/core-concepts/digests/): immutable image identifiers.
- [Java JAR File Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jar/jar.html): JAR structure and manifest.
- [Kubernetes — Container Images](https://kubernetes.io/docs/concepts/containers/images/): using images, tags, and digests in deployments.
