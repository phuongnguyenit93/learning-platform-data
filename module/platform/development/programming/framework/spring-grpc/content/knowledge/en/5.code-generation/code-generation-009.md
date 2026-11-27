# Deterministic Code Generation in Spring gRPC

In a **Spring gRPC** project, the same Protocol Buffers contract must produce the exact same set of Java sources whenever built again with the same inputs and toolchain. This property is called **deterministic code generation**: if the schema, import graph, generator options, and tool versions remain unchanged, the generated sources should be stable and byte-comparable.

This prevents teams from hitting situations where two developers generate two different versions of `StockServiceGrpc.java` while working on the same contract; it also helps distinguish changes caused by schema edits from changes caused by generator upgrades.

This lesson focuses on making code generation **deterministic and repeatable**: controlling inputs, pinning the toolchain, keeping import paths stable, regenerating from clean outputs, and verifying results via diffs/hashes. The guidance applies to gRPC Java codegen in both Gradle and Maven.

## 1. What Does Deterministic Code Generation Mean?

A code generation run takes these primary inputs:

- The `.proto` files and all imported schemas.
- Proto source roots and import resolution rules.
- Versions of `protoc`, `protoc-gen-grpc-java`, and any other generators.
- Java/gRPC generator options and output configuration.
- Relevant execution environment details for the plugin, including OS/architecture binaries and the build tool.

If those inputs are identical, the generated sources should be identical file-for-file, ideally **byte-for-byte**. You can verify this by running generation twice from a clean state and comparing the outputs.

Distinguish three levels:

| Level | What Is Verified | Example |
| --- | --- | --- |
| Deterministic codegen | Same inputs and generator produce the same sources | Two runs generating `StockRequest.java` produce the same hash |
| Reproducible build | Same sources/toolchain produce identical build artifacts under defined criteria | JAR has identical contents and metadata |
| Runtime consistency | Client/server execute compatible contracts and policies | RPC returns the expected status per business rules |

**Deterministic code generation does not automatically make a JAR reproducible or runtime behavior identical.** A JAR also depends on the compiler, resource processing, timestamps, packaging, and other plugins; runtime behavior also depends on data, network, TLS, deadlines, and service state.

## 2. Sources of Differences Between Two Generation Runs

| Source of Drift | Symptom | How to Control |
| --- | --- | --- |
| Different `protoc` or gRPC plugin version | APIs, annotations, comments, or source structure change | Pin exact generator versions |
| Different proto source root | Logical paths or generated comments change | Standardize roots and working directory |
| Different import path | Resolves to a different schema or the same schema under two names | Use canonical import paths; avoid overlapping roots |
| Unpinned proto dependency | Same import resolves to changed schema contents | Use immutable artifact versions |
| Different generator options | Different Java package, outer class, or output layout | Manage options in build configuration |
| Different OS/architecture plugin binary | Can introduce differences if binaries are not equivalent | Pin artifacts and verify in CI matrix |
| Stale leftover outputs | Files deleted from proto still linger in generated directory | Clean outputs before a clean verification run |
| Manual edits to generated sources | Next run overwrites edits or creates confusing diffs | Edit only `.proto` or application code |
| Dynamic dependencies | Today's and tomorrow's builds resolve different generators | Never use dynamic/snapshot versions for release toolchains |

Generated Java code sometimes embeds generator version markers, source names, or annotations. Thus, upgrading a plugin can produce diffs even when the schema has not changed. That is a **toolchain** change, not necessarily a protobuf API change.

## 3. Locking Code Generation Inputs

### 3.1. Managing Schemas and Imports

Keep schemas in source control and standardize proto roots. For example:

```text
src/main/proto/
├── common/v1/money.proto
└── orders/v1/order.proto
```

In `order.proto`, every module uses the same import path:

```proto
import "common/v1/money.proto";
```

Never let a developer machine import from a local directory outside the repository while CI imports a different copy. If schemas come from an external artifact, pin a specific version and ensure the artifact is never overwritten under the same version.

### 3.2. Pinning Generator Versions

With Gradle, declare explicit versions for the plugin, `protoc`, and the gRPC plugin:

```groovy
plugins {
    id 'java'
    id 'com.google.protobuf' version '0.9.5'
}

def protobufVersion = '4.30.2'
def grpcVersion = '1.71.0'

protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:$protobufVersion"
    }
    plugins {
        grpc {
            artifact = "io.grpc:protoc-gen-grpc-java:$grpcVersion"
        }
    }
    generateProtoTasks {
        ofSourceSet('main').configureEach { task ->
            task.plugins {
                grpc {}
            }
        }
    }
}
```

With Maven, pin the plugin and executable artifacts in `pom.xml`:

```xml
<properties>
    <protobuf.version>4.30.2</protobuf.version>
    <grpc.version>1.71.0</grpc.version>
</properties>

<plugin>
    <groupId>org.xolstice.maven.plugins</groupId>
    <artifactId>protobuf-maven-plugin</artifactId>
    <version>0.6.1</version>
    <configuration>
        <protocArtifact>
            com.google.protobuf:protoc:${protobuf.version}:exe:${os.detected.classifier}
        </protocArtifact>
        <pluginId>grpc-java</pluginId>
        <pluginArtifact>
            io.grpc:protoc-gen-grpc-java:${grpc.version}:exe:${os.detected.classifier}
        </pluginArtifact>
    </configuration>
</plugin>
```

The versions in the examples are illustrative. Projects must pick a version set verified to be compatible with the protobuf runtime, grpc-java runtime, and Spring gRPC starter. **Pinning generators** and **pinning runtimes** are related but distinct tasks: generators produce source code, while runtimes provide the APIs that source code calls.

Do not use dynamic or snapshot versions for release toolchains. Commit the Gradle Wrapper and Maven Wrapper as well so all machines use the same build tool version.

### 3.3. Stabilizing Options and Paths

Keep schema options such as `java_package`, `java_multiple_files`, and `java_outer_classname` in source control. Do not depend on environment variables or absolute paths that only exist on a personal machine.

Standardize on:

- One primary proto root for `main` sources.
- One canonical import path per schema.
- Dependency directories explicitly declared in the build.
- Generator options configured in Gradle/Maven, not passed manually at run time.

## 4. Making Gradle Code Generation Deterministic

The Gradle protobuf plugin manages generation through its task graph. Compact configuration for the `main` source set:

```groovy
plugins {
    id 'java'
    id 'com.google.protobuf' version '0.9.5'
}

def protobufVersion = '4.30.2'
def grpcVersion = '1.71.0'

dependencies {
    implementation "com.google.protobuf:protobuf-java:$protobufVersion"
    implementation platform("io.grpc:grpc-bom:$grpcVersion")
    implementation 'io.grpc:grpc-protobuf'
    implementation 'io.grpc:grpc-stub'
}

protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:$protobufVersion"
    }
    plugins {
        grpc {
            artifact = "io.grpc:protoc-gen-grpc-java:$grpcVersion"
        }
    }
    generateProtoTasks {
        ofSourceSet('main').configureEach { task ->
            task.plugins {
                grpc {}
            }
        }
    }
}
```

This configuration restricts the gRPC plugin to the `main` proto task. If the `test` source set also needs stubs, configure `test` explicitly or use `all().configureEach`. Avoid applying the plugin to source sets that do not need it, as that increases output volume and change surface.

Clean verification commands:

```bash
./gradlew --version
./gradlew clean generateProto
./gradlew compileJava
```

`clean` removes stale outputs so generation cannot rely on leftover files. `generateProto` produces message and gRPC sources; `compileJava` verifies the compiler sees them. In projects using the wrapper, run `./gradlew` instead of an uncontrolled global Gradle installation.

## 5. Making Maven Code Generation Deterministic

Maven needs pinned versions for the protobuf plugin, `protoc` artifact, gRPC plugin artifact, and OS classifier plugin. Two goals are typically bound to the `generate-sources` phase:

```xml
<execution>
    <id>generate-protobuf-and-grpc</id>
    <phase>generate-sources</phase>
    <goals>
        <goal>compile</goal>
        <goal>compile-custom</goal>
    </goals>
</execution>
```

When verifying from scratch:

```bash
mvn --version
mvn clean generate-sources
mvn compile
```

`mvn clean` deletes `target`, forcing generation to produce fresh outputs. `generate-sources` runs the Java generator and custom gRPC plugin per the configured execution; `compile` verifies that the Maven compiler recognizes the generated roots.

Use the Maven Wrapper (`mvnw`/`mvnw.cmd`) and pin its version in wrapper properties. If using `os-maven-plugin` to select binaries, control the extension version and the classifier resolved by CI.

## 6. Comparing Two Generation Runs

A direct check is running generation twice from a clean state, copying the first output to a temporary directory **outside the build output**, and comparing it against the second run.

Example for Gradle in a Unix-style shell:

```bash
set -eu

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

./gradlew clean generateProto
cp -R build/generated/source/proto/main "$tmp/first"

./gradlew clean generateProto
diff -ru "$tmp/first" build/generated/source/proto/main
```

If `diff` prints no differences and exits with code 0, two generation runs in the same environment produce the exact same file tree. If differences appear, keep both outputs and investigate the cause before updating any baseline.

With Maven, use the protobuf Maven plugin's output root:

```bash
set -eu

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mvn clean generate-sources
cp -R target/generated-sources/protobuf "$tmp/first"

mvn clean generate-sources
diff -ru "$tmp/first" target/generated-sources/protobuf
```

Paths may vary if the plugin or project customizes outputs. Use the actual generated roots. On Windows, you can run the same workflow with PowerShell, comparing relative path lists along with each file's SHA-256 hash.

**This check proves repeatability within the same environment**—it does not yet prove every OS or JDK produces identical output. To verify cross-platform determinism, run the same steps across a CI matrix and compare generated source artifacts across supported environments.

## 7. Using Hashes to Detect Drift

When you need to store evidence in CI, generate a manifest containing relative paths and SHA-256 hashes for each generated source file:

```bash
find build/generated/source/proto/main -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  > build/codegen-manifest.sha256
```

The manifest helps identify which files changed between two runs and whether file contents still share the same hash. Use relative paths instead of absolute paths so the manifest does not depend on workspace location.

When comparing two manifests, ensure path normalization and line endings are consistent. If the only difference is line endings, pinpoint the cause and standardize your policy; do not ignore differences just to make a test pass.

Manifests can be stored as CI artifacts, though you do not need to commit every generated file or hash into the repository. They serve as verification evidence, not a replacement for schemas and build configuration.

## 8. Analyzing Diffs When Upgrading Generators

When upgrading `protoc` or `protoc-gen-grpc-java`, generated sources can change even though `.proto` files did not. Safe upgrade workflow:

1. Record the old versions of `protoc`, the gRPC plugin, and runtimes.
2. Run clean generation with the old toolchain and save the output/manifest.
3. Update only the target generator version in an isolated, intentional change.
4. Run clean generation with the new toolchain.
5. Inspect the diff; classify changes caused by annotations, APIs, comments, packages, or output layout.
6. Compile and run integration tests with compatible runtimes.
7. Update version locks/BOMs along with release notes if generated APIs changed.

Avoid bundling schema, generator, and runtime upgrades into a single large change unless necessary; isolating causes helps reviewers understand diffs and simplifies rollbacks.

| Diff Pattern | What to Verify |
| --- | --- |
| Only generated comments or version markers changed | Confirm it comes from the generator version and is intentional |
| Method or stub API signatures changed | Check source compatibility and client/server code |
| Package or class names changed | Check `java_package`, options, and imports |
| Method descriptors or RPC paths changed | Check protobuf package, service/method names, and wire compatibility |
| Old files remain after deleting a message | Old outputs were not cleaned or task does not fully manage outputs |
| Many unexpected files changed | Check generator options, import roots, and dependency versions |

## 9. CI: Verifying Generation from a Clean Environment

A CI job dedicated to code generation should:

- Use the specified JDK and build tool versions.
- Resolve `protoc`/plugins from pinned artifact versions.
- Check out all required proto dependencies.
- Run clean generation and compilation.
- Re-run generation to compare outputs if the project enforces determinism checks.
- Run unit/integration tests verifying generated stubs work with the server.
- Archive logs, manifests, or generated output diffs on failure.

Example pipeline commands:

```bash
# Gradle
./gradlew --no-daemon clean generateProto compileJava test

# Maven
./mvnw -B clean generate-sources compile test
```

These are illustrative commands; real CI setups may run `build` or `verify` with appropriate profiles. If you need to compare two generation runs, add the clean repeat-and-diff step from section 6.

Do not rely on leftover generated outputs from a previous job's cache or workspace to conclude that generation is deterministic. Caches can speed up builds, but you still need an independent clean-build verification path.

## 10. What Does Deterministic Codegen NOT Solve?

Deterministic code generation only guarantees **source outputs** under a defined set of inputs and toolchain. It does not guarantee:

- Older clients remain compatible with newer servers after a contract change.
- Every RPC returns identical responses when underlying data or system state differs.
- Deadlines, retries, cancellation, TLS, or interceptors are configured properly.
- JARs have identical timestamps and metadata across every build.
- Custom plugins are environment-independent if they read system time, environment variables, or undeclared files.

For custom generator plugins written by your team, avoid embedding non-deterministic data in outputs such as current timestamps, absolute workspace paths, random identifiers, or unstable file traversal orders. If such information is needed for debugging, put it in logs or separate build metadata instead of generated source files.

## 11. Troubleshooting Checklist for Non-Deterministic Output

| Symptom | Diagnostic Question |
| --- | --- |
| Same schema, different sources across machines | Are `protoc`/plugin versions and binary classifiers identical? |
| CI generates extra or missing files | Are proto inputs/import roots identical? Were old outputs cleaned? |
| Generated comments contain different paths | Which root/working directory is the build using? |
| Diffs appear after a version bump | Did the generator change APIs or markers? |
| Local build passes, CI fails | Did CI fetch all proto dependencies and artifacts? |
| Hash changed while contents look identical | Did line endings, encoding, or file ordering change? |
| Repeated builds still produce stale outputs | Are task inputs/outputs or lifecycle bindings accurate? |
| Generated sources are deterministic, yet RPC fails | Is the bug in runtime config, service registration, channel, or contract compatibility? |

When a mismatch appears, save both sets of generated outputs, manifests, tool versions, and exact commands/tasks executed. Never simply re-run until the diff disappears; identify **which input or step introduced the difference**.

## 12. Hands-On Practice

1. Pin `protoc` and `protoc-gen-grpc-java` versions in Gradle; run `clean generateProto` twice and compare both output trees.
2. Perform the same workflow with Maven `clean generate-sources` and `diff -ru`.
3. Edit a comment in `.proto`, regenerate, and observe which files change; explain why schema sources are inputs to the generator.
4. Change `java_package` and compare generated paths and Java imports. Distinguish a Java package change from a protobuf RPC path change.
5. Upgrade only the gRPC generator version, save the diff, and separate marker/tooling changes from API changes.
6. Run the same generation on two supported CI environments, generate SHA-256 manifests, and compare them.
7. Configure an import root pointing to a local schema outside the repository, observe why clean CI cannot reproduce it, and replace it with a managed dependency.
8. In a custom generator, try inserting the current timestamp into an output comment, identify the source of non-determinism, and remove the varying data.
9. Write a CI job that runs clean generation, compilation, integration tests, and a repeat/diff check; archive the manifest whenever differences occur.

### Key Takeaway

**Deterministic code generation means the same schema, import graph, options, and generator toolchain must produce identical generated sources.** Pin `protoc`/plugin versions, standardize proto roots and import paths, keep dependencies immutable, never edit generated outputs, and verify two clean runs using diffs or hashes. Both Gradle and Maven support this workflow; CI must regenerate from source independently of prior workspaces. Deterministic generated sources provide the foundation for reviewing changes and reliable builds, though runtime and contract compatibility testing are still required separately.
