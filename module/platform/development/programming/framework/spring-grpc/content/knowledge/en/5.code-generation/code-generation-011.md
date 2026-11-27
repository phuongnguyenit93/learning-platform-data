# Managing protoc and Plugin Versions in Spring gRPC

In a **Spring gRPC** application, Java code generated from Protocol Buffers depends on several independently versioned components: **`protoc`**, the **`protoc-gen-grpc-java`** plugin, the **`protobuf-java`** library, **grpc-java** libraries, and the Spring gRPC starter. Upgrading just one component without checking the rest can cause a project to generate code cleanly yet fail to compile, or compile yet fail at runtime.

Good version management means clearly identifying **which tool generates code**, **which runtime executes that code**, **which dependencies the Spring starter manages**, and how to verify the actual versions resolved by your build. This lesson focuses on version alignment and controlled upgrade workflows for gRPC Java code generation.

## 1. Distinguishing Components and Versions

| Component | Role |
| --- | --- |
| `protoc` | Parses schemas, resolves imports, and invokes generators |
| `protoc-gen-grpc-java` | Generates service descriptors, server base classes, and client stubs |
| `protobuf-java` | Runtime for message classes: builders, parsers, serialization |
| `grpc-protobuf` | Marshaller bridging protobuf messages with grpc-java |
| `grpc-stub` | Stub base classes, `StreamObserver`, and client/server APIs |
| `grpc-api` | Channels, statuses, metadata, descriptors, and core APIs |
| gRPC transport | HTTP/2, connections, TLS, and network call execution |
| Spring gRPC starter | Spring integration, auto-configuration, and starter-managed dependencies |

The two generator versions must be managed separately:

- `protoc` is typically resolved from the `com.google.protobuf:protoc` artifact.
- `protoc-gen-grpc-java` is typically resolved from the `io.grpc:protoc-gen-grpc-java` artifact.

`protobuf-java` is the runtime for message classes; it is not the `protoc` version. Likewise, `grpc-stub` is a library used by your application, not an executable plugin.

## 2. Version Alignment Principles

Manage at least three version groups:

1. **Codegen toolchain:** `protoc`, the gRPC Java generator, and the build plugin orchestrating generation.
2. **Java runtime:** protobuf Java runtime, grpc-java API/stub/protobuf, and transport.
3. **Spring integration:** Spring Boot/Spring gRPC starter along with any BOM or dependency constraints provided by the starter.

Practical rules:

- Pin explicit versions for `protoc` and `protoc-gen-grpc-java`; never use `latest`, dynamic versions, or snapshots in release builds.
- Use a single consistent grpc-java version line across `grpc-api`, `grpc-stub`, `grpc-protobuf`, and transport, usually via the grpc BOM.
- Ensure generated messages are compatible with the `protobuf-java` runtime. Never use a runtime older than what generated code requires.
- Check generator/runtime compatibility guidance when upgrading; never assume arbitrary versions are compatible just because Java compiles.
- When a Spring gRPC starter already manages grpc-java or protobuf dependencies, prefer the starter/BOM's dependency management; avoid overriding individual versions without testing.

**Generator versions and runtime versions must be evaluated together**, though not every component shares the exact same version number. Protobuf and grpc-java follow independent release lines.

## 3. Gradle: Declaring and Centralizing Versions

Illustrative configuration in `build.gradle`:

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

    // Only add transport if the starter does not already provide/manage it.
    runtimeOnly 'io.grpc:grpc-netty-shaded'
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
        all().configureEach { task ->
            task.plugins {
                grpc {}
            }
        }
    }
}
```

The versions here are **configuration examples**, not recommendations for the latest versions. When using Spring Boot/Spring gRPC starters, inspect your application's BOM before adding the grpc BOM or declaring direct versions. Avoid having two BOMs manage the same artifact at different versions without understanding precedence.

### 3.1. Using a Version Catalog

For multi-module Gradle builds, centralize versions in `gradle/libs.versions.toml`:

```toml
[versions]
protobuf = "4.30.2"
grpc = "1.71.0"
protobuf-plugin = "0.9.5"

[libraries]
protobuf-java = { module = "com.google.protobuf:protobuf-java", version.ref = "protobuf" }
grpc-bom = { module = "io.grpc:grpc-bom", version.ref = "grpc" }
grpc-protobuf = { module = "io.grpc:grpc-protobuf" }
grpc-stub = { module = "io.grpc:grpc-stub" }

[plugins]
protobuf = { id = "com.google.protobuf", version.ref = "protobuf-plugin" }
```

A version catalog reduces the risk of client and server modules accidentally using different toolchains. However, it **does not lock the entire dependency graph** on its own; combine it with dependency locking if stricter reproducibility is needed.

### 3.2. Checking Which Versions Gradle Actually Resolves

What you declare in a build file is not guaranteed to be the final version on the runtime classpath. Other dependencies or BOMs can influence the outcome:

```bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency grpc-stub

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency protobuf-java
```

Read the output to see which version was selected, which dependencies requested other versions, which BOM/constraint decided the winner, and any conflicts Gradle resolved. If generated code hits linkage errors, inspect both the compile classpath and runtime classpath; the two configurations can differ.

## 4. Maven: Managing Versions with Properties and BOMs

In Maven, use properties to centralize codegen and runtime versions:

```xml
<properties>
    <protobuf.version>4.30.2</protobuf.version>
    <grpc.version>1.71.0</grpc.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.grpc</groupId>
            <artifactId>grpc-bom</artifactId>
            <version>${grpc.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.protobuf</groupId>
        <artifactId>protobuf-java</artifactId>
        <version>${protobuf.version}</version>
    </dependency>
    <dependency>
        <groupId>io.grpc</groupId>
        <artifactId>grpc-protobuf</artifactId>
    </dependency>
    <dependency>
        <groupId>io.grpc</groupId>
        <artifactId>grpc-stub</artifactId>
    </dependency>
</dependencies>
```

The codegen plugin declaration uses those same properties:

```xml
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

The plugin still needs an execution bound to the `generate-sources` phase with goals to generate messages and gRPC stubs. If the Spring Boot parent or Spring gRPC BOM already manages protobuf/grpc-java, use your project's chosen dependency management rather than importing a conflicting BOM.

### 4.1. OS Classifiers and Plugin Executables

`protoc` and `protoc-gen-grpc-java` are executable artifacts, so Maven typically needs platform classifiers. `os-maven-plugin` supplies the appropriate classifier to pick artifacts matching the OS and architecture.

If builds run on Linux CI while developers work on Windows, ensure Maven resolves matching binaries for each environment. Never commit a single-OS executable into a shared build and never hardcode personal machine paths.

### 4.2. Checking the Dependency Tree

```bash
mvn dependency:tree

mvn dependency:tree -Dincludes=io.grpc:grpc-stub,com.google.protobuf:protobuf-java
```

Verify the effective versions of `grpc-api`, `grpc-stub`, `grpc-protobuf`, transport, and `protobuf-java`. If a starter pulls a different version, determine which artifact manages it before overriding. Arbitrary exclusions can strip libraries the starter relies on.

## 5. Compatibility Between Generated Code and Runtime

Generated Java calls APIs in the protobuf and grpc-java runtimes. If a generator emits code referencing a method or class missing from the runtime on the classpath, compilation or runtime execution will fail.

| Error | Possible Cause |
| --- | --- |
| `cannot find symbol` in generated messages | Protobuf runtime lacks APIs needed by generated code, or generator/runtime mismatch |
| `NoSuchMethodError` | Runtime on classpath differs from API referenced by compiled class |
| `NoClassDefFoundError` | Missing runtime dependency or excluded dependency |
| Errors involving `javax.annotation.Generated` | Generator emits annotation API absent from compile classpath |
| Stub compiles, fails on invocation | grpc-java runtime/transport mismatch or bad runtime configuration |
| Plugin fails to run on CI | Wrong OS classifier, executable, or artifact repository |

Do not assume every generated code error is a version mismatch. Before changing versions, verify:
1. Are the schema and import paths correct?
2. Which generator actually ran and at what version?
3. Was generated output recreated from a clean state?
4. Which versions are actually on the compile/runtime classpath?
5. Is a Spring starter applying dependency management or auto-configuration?

### Generated Code and Runtime Do Not Necessarily Share the Same Version Number

Protobuf and grpc-java have separate release schedules. Do not set the exact same version number on `protobuf-java` and `grpc-stub` just to "keep them in sync". Use verified versions from each release line and follow their compatibility guidance. For grpc-java, using a single consistent grpc BOM/version line across grpc-java modules in the same application is the standard practice.

## 6. Controlled Toolchain Upgrades

Avoid upgrading all versions at once unless necessary. A reviewable workflow:

1. **Record the baseline:** current `protoc`, gRPC plugin, protobuf runtime, grpc-java BOM, Spring Boot/starter, and JDK.
2. **Define the upgrade goal:** security patch, bug fix, generator feature, or compatibility requirement.
3. **Read release notes/compatibility:** identify breaking changes and minimum runtime versions.
4. **Upgrade the generator deliberately:** pin the new version in Gradle/Maven while keeping schemas unchanged so diffs are easy to inspect.
5. **Clean generation:** delete old outputs, regenerate all sources, and inspect the diff.
6. **Align runtimes:** update protobuf/grpc-java dependencies per generated code and Spring starter requirements.
7. **Compile and test:** run unit tests, integration tests, and exercise a unary/streaming RPC.
8. **Verify on CI:** run in a clean environment covering supported OS/architectures.
9. **Document the change:** record new versions, rationale, test results, and migration notes.

Separate generator upgrades from business schema changes. Changing fields, RPC paths, and plugin versions together makes test failures much harder to diagnose.

## 7. Example Verification After a Version Upgrade

Suppose a project has unary `StockService.GetStock` and server-streaming `WatchStock`. After upgrading the generator:

```bash
# Gradle
./gradlew clean generateProto compileJava compileTestJava test

# Maven
mvn clean generate-sources compile test
```

After building, verify:
- Both message classes and `StockServiceGrpc` are present.
- Server implementations still override the generated API signatures properly.
- Client blocking/async stubs can still invoke methods.
- Error statuses are preserved, e.g., `INVALID_ARGUMENT` or `NOT_FOUND`.
- Streaming fires the right terminal callbacks and does not terminate unexpectedly.
- TLS, metadata, interceptors, and deadlines were not altered by dependency/runtime upgrades.

A simple grpc-java integration test can verify the generated stub still calls the server:

```java
@Test
void generatedStubCallsStockService() {
    StockReply reply = blockingStub.getStock(
            StockRequest.newBuilder()
                    .setSku("BOOK-101")
                    .build());

    assertEquals("BOOK-101", reply.getSku());
}
```

This test assumes `blockingStub` targets an initialized test server and `StockReply` is returned per the contract. To thoroughly validate a version upgrade, also test error cases, streaming, and the Spring application context if starters/auto-configuration were upgraded too.

## 8. Dependency Locking and Reproducibility

Direct version pinning avoids dynamic versions, but transitive dependencies can still shift if repository metadata changes or resolution is unlocked. With Gradle, you can enable dependency locking:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

After configuring, generate/update lock state using the project's appropriate task, review the lock files, and commit them if required by your organization. Never silently refresh lock files alongside unrelated changes.

In Maven, properties and BOMs centralize versions; the Maven Enforcer Plugin can enforce dependency convergence or version policies. Convergence rules should follow organizational standards, since some dependencies are intentionally designed to exist in multiple versions across isolated modules.

Beyond dependencies, pin the Gradle Wrapper/Maven Wrapper and JDK toolchain. A build with explicit dependency versions can still behave differently if run with arbitrary build tools or JDKs.

## 9. Version Mismatch Diagnostic Checklist

| Observation | First Thing to Check |
| --- | --- |
| Only message code fails | `protoc` and `protobuf-java`, stale vs. fresh generated output |
| Only `*Grpc.java` fails | `protoc-gen-grpc-java` and grpc-java API/stub runtime |
| Compile passes, runtime fails | Runtime dependency graph, transport, and runtime classpath |
| Local passes, CI fails | OS classifier, JDK, wrapper, artifact repository |
| Spring context fails to start | Starter/BOM, auto-configuration, and dependency conflicts |
| Large diff after plugin upgrade | Generator version, options, and schema inputs |
| `NoSuchMethodError` | Identify the actual JAR providing the class/method at runtime |
| `UNAVAILABLE` after upgrade | Transport, TLS, target, and server readiness; do not assume codegen fault |

Always gather evidence from the dependency graph and build logs. Do not look only at a version declared in one file, because the final version may be overridden by a BOM, constraint, parent POM, or another dependency.

## 10. Hands-On Practice

1. Record the versions of `protoc`, `protoc-gen-grpc-java`, `protobuf-java`, and grpc-java artifacts in a project.
2. Intentionally declare mismatched grpc-java artifact versions in a practice copy; use Gradle `dependencyInsight` or Maven `dependency:tree` to locate the conflict source.
3. Align versions under a single grpc BOM; run compilation and integration tests.
4. Upgrade only `protoc-gen-grpc-java` while leaving schemas unchanged; run clean generation and categorize the generated diff.
5. Upgrade the protobuf compiler/runtime together as a compatible pair; run message parse/serialize tests.
6. Test the Maven executable classifier on Windows and Linux CI; confirm the plugin binary resolves properly per platform.
7. Enable Gradle dependency locking or Maven convergence rules; confirm builds reproduce from a clean checkout.
8. Write unary and server-streaming tests after an upgrade; verify success, error statuses, deadlines, and terminal callbacks.

### Key Takeaway

**Managing `protoc` and plugin versions means managing an integrated toolchain of generators and runtimes.** Pin `protoc` and `protoc-gen-grpc-java`; align `protobuf-java` and grpc-java artifacts with compatibility guidance and Spring's BOM/starter; verify resolved versions via the dependency graph; and upgrade incrementally with clean generation, diff inspection, compilation, and integration tests. Declared versions are only configuration intent—the versions actually resolved and used by the build are what must be verified.
