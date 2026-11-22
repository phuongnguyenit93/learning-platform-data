# Attaching Version, Source Code, and Environment Information to Image Releases

A CRaC checkpoint saves the state of a Java process at a point in time. When packaging a checkpoint for deployment, operations teams need to know which application version the image was created from, which commit the source code came from, which dependencies and JDK were used, what environment it was created in, and which runtime is required to restore it. Without this information, a checkpoint file may exist, yet determining its origin, evaluating compatibility, or tracing deployment errors becomes very difficult.

A checkpoint release should be accompanied by provenance information (build origin), a list of software components, checksums, and signatures. Stable build information can be embedded into the application while packaging an external manifest to describe the specific checkpoint and the image creation environment. These two parts complement each other: build info identifies the application; the release manifest identifies the checkpoint artifact and its deployment conditions.

## 1. Distinguishing Applications, Container Images, and Checkpoint Images

In a CRaC workflow, the word "image" can refer to several different artifact types:

- **Application artifact:** the compiled and packaged JAR, WAR, or application file set.
- **Container image:** the filesystem and configuration packaged in OCI format to create containers.
- **Checkpoint image:** the process state image created by the CRaC runtime, typically containing memory data and the components needed to restore the process.
- **Release bundle:** the release package combining the checkpoint artifact with the manifest, checksums, signatures, SBOM, and related documentation.

These artifacts are not interchangeable. A container image identifies the filesystem environment and application; a checkpoint image identifies the state of a running process. A checkpoint can depend tightly on the runtime, operating system, CPU architecture, and how resources were handled at checkpoint time. Therefore, simply tagging a container image is not sufficient for versioning a checkpoint.

A release bundle may have the following structure:

~~~text
release/
  application.jar
  checkpoint/
    checkpoint-data
    checkpoint-metadata
  checkpoint-manifest.json
  checkpoint-manifest.sig
  sbom.cdx.json
  checksums.txt
~~~

Actual checkpoint filenames and directory structure depend on the CRaC implementation or checkpoint tool in use. Do not assume that every runtime produces the exact same filenames or format.

## 2. Three Groups of Information to Attach to a Release

Release information should be divided into three groups for easy traceability.

### Version and Source Code Identity

This group answers the question: which application is inside the checkpoint and from which source was it built?

- Application name and module.
- Release version, for example 2.4.1.
- Build number or CI run ID.
- Full Git commit SHA.
- Git tag or release branch.
- Working tree state at build time: clean or dirty.
- Hash of source archive or patch if the build did not originate from a clean commit.
- Gradle/Maven version and critical build plugins.
- Hash of dependency lockfile.
- SBOM describing dependencies and library versions.

The Git commit SHA is an important identifier, but it is trustworthy only when the build was genuinely produced from that commit's contents. If the working tree has uncommitted changes, record the dirty state and store the corresponding patch/source snapshot, or reject the release per CI policy.

### Runtime and Checkpoint Creation Environment Information

This group answers the question: on which platform was the process run and checkpointed?

- JDK vendor, full version, build number, and runtime version.
- CRaC API/runtime or checkpoint implementation and its version.
- JVM flags affecting runtime, class loading, JIT, or checkpointing.
- Operating system, distribution version, and kernel.
- CPU architecture, such as x86_64 or aarch64.
- libc and critical native libraries if the environment depends on them.
- Container base image and immutable digest.
- CPU or platform features required by the runtime to restore.
- Checkpoint creation tool information and how the checkpoint was invoked.

Do not record only "Java 21" or "Linux". Two JDKs of the same feature release can differ in vendor, build, CRaC patches, or native libraries. Record the full version and the actual runtime that ran the application.

### Checkpoint and Packaging Information

This group answers the question: which artifact was created, when, and how was it verified?

- Unique checkpoint/release ID.
- Timestamp when the checkpoint was created in UTC.
- Application version that was checkpointed.
- Relative path, size, and SHA-256 of each checkpoint file.
- SHA-256 of the archive or release bundle after packaging.
- Checkpoint preparation step status and warmup procedure version.
- Manifest schema version.
- Timestamp and identity of the release pipeline.
- Manifest signature or artifact signature.

Build time and checkpoint time are two separate milestones. You can build the JAR first, run the application and warm it up, and only then create the checkpoint. Record these timestamps separately for accurate traceability.

## 3. Why Record Both Source Code and Environment?

When a checkpoint restore fails, knowing only the application version is often insufficient to find the root cause. For example:

- A native dependency was updated even though the Java source did not change.
- CI used a different JDK vendor/build from the environment that created the checkpoint.
- The container base image was changed while keeping the same tag.
- The kernel or CPU architecture of the restore host differs from the checkpointing environment.
- An uncommitted patch was included in the JAR.
- Secrets or dynamic configuration changed between checkpoint creation and restore.

The commit SHA traces back to source. Dependency locks and SBOMs identify libraries. JDK/CRaC runtime along with OS/kernel allow compatibility cross-checking. Digests confirm the exact checkpoint files being deployed.

Environment information serves as evidence for comparison, not a guarantee that every host with the same OS name or major JDK version is definitely compatible. Specific compatibility conditions depend on the CRaC runtime, checkpoint tool, vendor, and deployment platform. You must test restore on the target environment.

## 4. Embedding Build Identity into the Application Artifact

The application should carry an immutable build identifier so it can self-report the running version. You can generate a resource such as `build-info.properties` inside the JAR.

Example content:

~~~properties
app.name=order-service
app.version=2.4.1
build.id=ci-18427
git.commit=8f6a9f4b3c2d1e0a...
git.dirty=false
build.jdk=21.0.x+build
build.gradle=8.x
dependency.lock.sha256=...
~~~

The values above only illustrate the format. The pipeline must populate real values from source control and the build environment. If a value is unavailable, record `unknown` explicitly or omit the field; do not guess.

### Generating `build-info.properties` with Gradle

One approach is to pass metadata from CI via environment variables and generate the resource during the build. The example below uses Gradle Groovy DSL:

~~~groovy
def buildInfoDir = layout.buildDirectory.dir("generated/build-info")
def gitCommit = providers.environmentVariable("GIT_COMMIT")
        .orElse("unknown")
def buildId = providers.environmentVariable("BUILD_ID")
        .orElse("local")
def gitDirty = providers.environmentVariable("GIT_DIRTY")
        .orElse("unknown")
def appVersion = project.version.toString()

tasks.register("generateBuildInfo") {
    inputs.property("gitCommit", gitCommit)
    inputs.property("buildId", buildId)
    inputs.property("gitDirty", gitDirty)
    inputs.property("appVersion", appVersion)

    outputs.file(buildInfoDir.map {
        it.file("build-info.properties")
    })

    doLast {
        def output = buildInfoDir.get()
                .file("build-info.properties").asFile
        output.parentFile.mkdirs()
        output.text = [
                "app.name=" + project.name,
                "app.version=" + appVersion,
                "build.id=" + buildId.get(),
                "git.commit=" + gitCommit.get(),
                "git.dirty=" + gitDirty.get()
        ].join(System.lineSeparator()) + System.lineSeparator()
    }
}

sourceSets.main.resources.srcDir(buildInfoDir)
tasks.named("processResources") {
    dependsOn("generateBuildInfo")
}
~~~

The pipeline must set `GIT_COMMIT`, `BUILD_ID`, and `GIT_DIRTY` from the exact checkout being built. Do not take a commit SHA from a CI variable not bound to the actual workspace. If the project uses Kotlin DSL or a build convention plugin, adapt the resource generation to the corresponding configuration.

For builds requiring reproducibility, do not embed the current timestamp into a resource in a way that alters the JAR on every build from the same source. Build timestamp can be stored in the release manifest or derived from `SOURCE_DATE_EPOCH` per pipeline convention. Build ID and commit SHA remain necessary to distinguish releases.

### Reading Build Info at Application Runtime

The application can read the resource to log or display it in a diagnostic endpoint:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class BuildInfo {
    private static final Properties VALUES = load();

    private BuildInfo() {}

    private static Properties load() {
        Properties properties = new Properties();
        try (InputStream input =
                     BuildInfo.class.getResourceAsStream(
                             "/build-info.properties")) {
            if (input == null) {
                throw new IllegalStateException(
                        "build-info.properties is missing");
            }
            properties.load(input);
            return properties;
        } catch (IOException error) {
            throw new IllegalStateException(
                    "Cannot read build information", error);
        }
    }

    public static String version() {
        return VALUES.getProperty("app.version", "unknown");
    }

    public static String commit() {
        return VALUES.getProperty("git.commit", "unknown");
    }

    public static String buildId() {
        return VALUES.getProperty("build.id", "unknown");
    }
}
~~~

You can log version, commit, and build ID at startup or expose them through a controlled internal endpoint. Do not put secrets, full environment dumps, tokens, or connection strings into build info.

Build info inside the JAR identifies the built application. It cannot self-identify the final checkpoint's digest because the checkpoint is created only after the application has run.

## 5. Creating a Release Manifest for the Checkpoint

After creating the checkpoint, the pipeline creates an external manifest describing the checkpoint artifact itself. The manifest can be JSON, YAML, or a metadata format defined by your organization. JSON is convenient for CI, verification tools, and artifact storage systems.

Example:

~~~json
{
  "schemaVersion": "1",
  "release": {
    "name": "order-service",
    "version": "2.4.1",
    "buildId": "ci-18427",
    "createdAt": "2026-11-13T07:00:00Z"
  },
  "source": {
    "repository": "https://example.invalid/platform/order-service",
    "commit": "8f6a9f4b3c2d1e0a...",
    "tag": "v2.4.1",
    "workingTreeClean": true,
    "dependencyLockSha256": "..."
  },
  "application": {
    "artifact": "application.jar",
    "sha256": "..."
  },
  "checkpoint": {
    "id": "order-service-2.4.1-20261113T070000Z",
    "createdAt": "2026-11-13T07:00:00Z",
    "implementation": "vendor-crac-runtime",
    "runtimeVersion": "recorded-full-version",
    "files": [
      {
        "path": "checkpoint/checkpoint-data",
        "sizeBytes": 123456789,
        "sha256": "..."
      }
    ]
  },
  "environment": {
    "jdkVendor": "recorded-vendor",
    "javaRuntimeVersion": "recorded-full-version",
    "cracRuntimeVersion": "recorded-version",
    "os": "recorded-distribution-and-version",
    "kernel": "recorded-kernel-version",
    "architecture": "x86_64",
    "libc": "recorded-libc-version",
    "containerBaseImage": "registry.example/app-base@sha256:..."
  },
  "provenance": {
    "pipeline": "release-pipeline",
    "runId": "18427",
    "sbom": "sbom.cdx.json",
    "signature": "checkpoint-manifest.sig"
  }
}
~~~

This is an illustrative schema, not a mandatory CRaC manifest format. Implementation name, runtime version, OS, kernel, and digest values must come from the actual environment. If the checkpoint consists of multiple files, list all required files or create an immutable archive and record the archive's digest.

Do not place a dummy value like `latest` in the manifest. Use a specific version, full commit SHA, and immutable digest. If a field does not apply, omit it or record `unknown` per the agreed schema.

## 6. Binding the Manifest to the Exact Checkpoint Artifact

A manifest is useful only if it can prove it describes the exact artifact being deployed. Compute SHA-256 for the checkpoint files or archive after checkpointing and packaging complete.

Example on Linux:

~~~shell
sha256sum application.jar
sha256sum checkpoint/*
sha256sum release.tar
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 -LiteralPath .\application.jar
Get-FileHash -Algorithm SHA256 -LiteralPath .\release.zip
~~~

If the checkpoint is a directory with multiple files, the pipeline must generate a list of relative paths, sizes, and hashes for each file. Do not hash only the directory name; a directory is not an immutable byte stream. Another option is to package the checkpoint into an archive, hash the archive, and ensure the archive is completely built before signing the manifest.

Do not embed the checkpoint's digest into the checkpoint file itself in a way that creates a circular dependency. Nor should you modify checkpoint contents after computing the hash. Instead:

1. Create the checkpoint.
2. Package the checkpoint files.
3. Compute hashes for each file or archive.
4. Generate the manifest referencing those hashes.
5. Sign the manifest.
6. Publish the immutable bundle.

Build info embedded in the JAR can contain the commit and version. The external release manifest links that JAR to a specific checkpoint via digests and environment information.

## 7. Capturing Environment Information at the Right Time

Information that needs to be collected at build time can differ from what needs to be collected when running the application and creating the checkpoint.

| Milestone | Information to Record |
|---|---|
| Source checkout | Commit SHA, tag, dirty state, submodule revision, source archive hash |
| Build | JDK compiler/vendor/version, Gradle/Maven version, build ID, dependency lock hash, SBOM |
| Runtime startup | Java runtime version, JVM flags, classpath/module path, CRaC runtime identity |
| Checkpoint | UTC timestamp, checkpoint tool/implementation, runtime build, OS/kernel, architecture, container digest, checkpoint file inventory |
| Restore target | Actual runtime and host, container digest, compatibility check results, restore time and readiness |

Some information can be obtained using commands or system APIs. For example:

~~~shell
java -version
java -XshowSettings:properties -version
uname -a
uname -m
~~~

`uname` commands suit Linux/Unix. On Windows, use corresponding system tools to record OS version and architecture. For containers, record the digest of the pulled image as well, not just a tag that could change.

The JVM can print some system properties, though not every piece of environmental information can be retrieved accurately from Java APIs. CI or the checkpoint launcher is usually the right place to gather kernel, container digest, CPU architecture, and checkpoint tool version.

It is unnecessary to collect all environment variables. Record only non-sensitive variable names needed for reproducibility. For secrets, record only the version identifier or revision if policy permits; do not record secret values, passwords, tokens, or private keys.

## 8. OCI Labels and Linking to Container Images

If the checkpoint is created inside a container, the container image should also carry metadata identifying source and release. Common OCI image annotations/labels include:

- org.opencontainers.image.title
- org.opencontainers.image.description
- org.opencontainers.image.version
- org.opencontainers.image.revision
- org.opencontainers.image.source
- org.opencontainers.image.created
- org.opencontainers.image.licenses

Example Dockerfile:

~~~dockerfile
ARG APP_VERSION
ARG GIT_COMMIT
ARG BUILD_CREATED

LABEL org.opencontainers.image.title="order-service" \
      org.opencontainers.image.version="$APP_VERSION" \
      org.opencontainers.image.revision="$GIT_COMMIT" \
      org.opencontainers.image.created="$BUILD_CREATED"
~~~

`ARG` values must be passed from a pipeline that verified the source checkout. Upon release, record the actual OCI image digest. A tag like `order-service:2.4.1` is convenient for humans, yet can be reassigned; the sha256 digest is the immutable identifier of the image contents.

The checkpoint manifest must reference the container image digest used to create the checkpoint. Upon restore, compare the digest and runtime details against the compatibility policy. OCI labels are only metadata; they do not by themselves guarantee that the checkpoint can restore on that container.

## 9. SBOM and Dependency Provenance

An SBOM (Software Bill of Materials) describes the software components contained in an artifact, such as Java libraries, native libraries, and dependency versions. SPDX or CycloneDX formats can be used according to organizational policy.

For a Java application, record:

- Direct and transitive dependencies.
- Actual resolved versions.
- Hash or revision of the dependency lockfile.
- Critical plugins/build tools.
- Native libraries and runtime components affecting the checkpoint.
- JDK vendor/build and CRaC implementation.

The lockfile enables reproducing the dependency graph, while the SBOM informs operators and security tools about which components were packaged. Both complement each other.

Provenance describes how an artifact was created: which pipeline ran, which source revision was checked out, which builder identity executed the build, which parameters were used, and what digests the output artifacts have. If the organization has an attestation system such as SLSA provenance or an equivalent format, link the checkpoint manifest to that attestation.

## 10. Signatures and Release Bundle Integrity

Checksums detect unexpected file changes. Digital signatures verify that the manifest was issued by a trusted pipeline or identity.

A release workflow can be:

~~~text
Verified source commit
       |
       v
Build application.jar
       |
       v
Generate build-info and SBOM
       |
       v
Run application with selected JDK/CRaC runtime
       |
       v
Warmup and prepare Resources
       |
       v
Create checkpoint
       |
       v
Compute SHA-256 for artifacts
       |
       v
Generate checkpoint-manifest.json
       |
       v
Sign manifest and verify signature
       |
       v
Publish immutable release bundle
~~~

Signing keys should be managed inside the CI system or a trusted signing service, never stored in the source repository or checkpoint image. Release signing permissions should be restricted to approved pipelines and identities.

When deploying, verify the manifest signature, check artifact hashes, confirm commit/version, and validate runtime compatibility before restoring. If any hash mismatches, do not use that bundle.

## 11. Restore Environment Compatibility Rules

Environment information helps construct a compatibility policy. Do not simply compare version strings and conclude compatibility.

Dimensions to evaluate:

| Dimension | Question to Verify |
|---|---|
| JDK vendor/build | Is the restore runtime the exact supported JDK/CRaC build? |
| CRaC implementation | Which implementation/version created and will restore the checkpoint? |
| OS and kernel | Does the target kernel support the checkpoint/restore mechanism and required resources? |
| CPU architecture | Are the CPU architecture and features compatible with machine code/runtime in the checkpoint? |
| Native libraries | Are required shared libraries, libc, and ABI present and compatible? |
| Container filesystem | Do required paths, mounts, permissions, files, and libraries exist? |
| Configuration and secrets | Are current endpoints, credentials, certificates, and config still valid? |
| External resources | Have databases, brokers, sockets, locks, and dependencies been recovered per policy? |

Some platforms may allow restoring across similar hosts; others enforce stricter requirements. Follow the documentation of the exact CRaC distribution and checkpoint tool. Record both source and target environments so discrepancies can be identified if errors occur.

Do not tie a checkpoint to a replaceable container tag or let a release automatically pick the latest runtime. Pin the JDK/container with verified versions and digests. Upgrading the JDK, kernel, or base image requires creating and testing a new checkpoint following the release workflow.

## 12. Do Not Put Sensitive Configuration in the Manifest

The manifest serves traceability and deployment, not secret storage. Do not place the following values into manifests, logs, or artifact names:

- Database passwords.
- API keys, bearer tokens, or session tokens.
- Private keys, private certificate material.
- Contents of secret files.
- Connection strings containing credentials.
- Environment values that must not be exposed publicly.

If you need to know which secret was used, record only a secret reference, version ID, or non-sensitive revision per your secret manager's policy. Because secrets may have been loaded onto the heap before checkpointing, the checkpoint image itself must also be protected and access-controlled like an artifact containing credentials.

Do not place internal hostnames, IP addresses, or detailed topology information into a public manifest unnecessarily. An operational manifest can be stored in an access-controlled internal repository.

## 13. Pre-Release Packaging and Verification Workflow

A pipeline can implement these steps:

1. Check out source at a specific commit; confirm a clean working tree or save a patch if dirty builds are allowed.
2. Record commit, tag, submodule revision, and build ID.
3. Build the application using the pinned JDK and build tool.
4. Generate `build-info.properties` in the JAR; generate the SBOM and save the dependency lock hash.
5. Build the container image with OCI labels and record the immutable digest.
6. Launch with the exact JDK/CRaC runtime; execute warmup and prepare resources as documented.
7. Create the checkpoint in a controlled environment.
8. Collect runtime, OS, kernel, CPU architecture, and checkpoint tool details at image creation time.
9. Create a checkpoint file inventory, compute SHA-256 hashes, and package the release bundle.
10. Generate the manifest linking application digest, container digest, source revision, and checkpoint digest.
11. Sign the manifest, verify the signature, and store the bundle alongside the SBOM/provenance.
12. Test restore with the exact runtime and target environment before promoting the release.

Each new checkpoint should receive a unique ID, even if the application version did not change. One application can produce multiple checkpoints from the same JAR at different times or in different environments; do not overwrite an old checkpoint under the same artifact name.

## 14. Post-Deployment and Restore Checks

Before restore:

- Verify the manifest signature.
- Recompute hashes and compare against the manifest.
- Confirm application version, commit SHA, and container digest.
- Check JDK/CRaC runtime, OS/kernel, and architecture against compatibility policy.
- Confirm checkpoint files are complete with proper access permissions.

After restore:

- Log release ID, build ID, commit, and checkpoint ID.
- Verify external dependencies have reconnected or been refreshed.
- Verify current configuration and secrets.
- Check readiness before accepting traffic.
- Record restore duration and recovery outcome.
- Correlate logs, metrics, and traces with release ID/checkpoint ID.

If the post-restore runtime does not comply with policy, do not force a restore simply because the manifest shares the same application version. Fall back to creating a checkpoint in a compatible environment or starting the application via the supported cold-start path.

## 15. Common Mistakes

**Putting only the version in the checkpoint filename.**

A filename does not prove provenance. You need the commit SHA, build ID, runtime, environment, digests, and a verifiable manifest.

**Recording only Java 21.**

A feature release is insufficient to identify vendor, build, CRaC patch, and actual runtime. Record the full version and implementation.

**Using a container tag as the unique identifier.**

Tags can be reassigned. Store the OCI digest to identify the exact container image used.

**Ignoring working tree status.**

A commit SHA does not describe uncommitted patches. Record dirty state and the corresponding source snapshot, or reject dirty builds from release.

**Putting the checkpoint hash inside the checkpoint itself.**

That creates a circular dependency when hashing. Store hashes in an external manifest after the checkpoint artifact is complete.

**Modifying the manifest after signing.**

Any metadata change after signing invalidates the signature. Create a new manifest, recompute digests, and re-sign per workflow.

**Putting secrets into build info or manifests.**

Artifacts can be copied across multiple environments. Record only secret references/versions if allowed, never the values.

**Assuming same OS and major JDK version guarantees compatibility.**

Kernel, vendor build, native libraries, CPU architecture, and CRaC implementation can also affect compatibility. Test restore on the actual target environment.

**Skipping restore tests before release.**

Manifests and checksums do not prove a checkpoint can restore. Include a restore integration test and readiness validation step.

## 16. Conclusion

A checkpoint release must identify the source, application build, image-creating runtime, OS environment, and the checkpoint artifact itself. Embed stable build identity in the application artifact, generate an external manifest after checkpointing to record runtime/environment and hashes, and attach SBOM, provenance, and signatures.

The manifest must link commit SHA, build ID, application/container digests, and checkpoint digests. Environment details support compatibility evaluation, while checksums and signatures verify integrity and publisher provenance. Keep secrets out of metadata; protect checkpoint images and restore only when the artifact has been verified on a supported runtime and environment.
