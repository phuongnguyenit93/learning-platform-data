# Verifying Generated Code in the Build for Spring gRPC

In **SPRING_GRPC**, message classes and service stubs are generated from Protocol Buffers contracts before the Java compiler compiles the application. A successful build must prove more than the presence of files in a generated directory: **the right schema was processed, both messages and gRPC APIs exist, the compiler picks up those sources, and the generated APIs work with the runtime**.

This lesson focuses on verifying generated code directly within the Gradle/Maven build workflow: confirming outputs, checking descriptors and serialization, running compilation/tests, invoking a stub against a server, detecting stale outputs, and integrating checks into CI. The goal is to catch code generation failures before packaging or deploying the service.

## 1. Which Layers Should Be Verified?

A sound verification workflow covers these layers:

| Layer | What to Confirm | Passing Signal |
| --- | --- | --- |
| Generation | Build invoked the right `protoc` and gRPC plugin | Task/goal succeeds, outputs created |
| Output | Expected messages, enums, and service APIs exist | Required generated classes exist |
| Compilation | Generated sources belong to the right source set and compile classpath | `compileJava`/Maven `compile` succeeds |
| Descriptor/schema | Generated API reflects expected service, methods, field numbers, and RPC types | Descriptor assertions pass |
| Runtime call | Stubs and server base classes work with the grpc-java runtime | In-process or integration RPC test passes |
| Application wiring | Spring registers services and configures client/server properly | Spring integration test passes |
| Clean build | Result does not depend on stale outputs on a developer's machine | Build from `clean`/clean checkout passes |

Not every layer requires a separate task. A compile check verifies source roots; descriptor tests verify schema details; in-process tests verify generated stubs and dispatch. Separating layers helps pinpoint whether a failure lies in generation, Java compilation, or runtime.

## 2. Sample Contract for Verification

Use a small inventory service schema:

```proto
syntax = "proto3";

package learning.stock.v1;

option java_package = "vn.example.stock.v1";
option java_multiple_files = true;

message StockRequest {
  string sku = 1;
}

message StockReply {
  string sku = 1;
  int64 available = 2;
}

service StockService {
  rpc GetStock(StockRequest) returns (StockReply);
  rpc WatchStock(StockRequest) returns (stream StockReply);
}
```

With this contract, the build must produce at least:

- `StockRequest` and `StockReply` from the Java protobuf generator.
- `StockServiceGrpc` from the gRPC Java plugin.
- Descriptors for messages, the service, and each RPC.

Example typical output with the Gradle protobuf plugin:

```text
build/generated/source/proto/main/
├── java/vn/example/stock/v1/
│   ├── StockRequest.java
│   └── StockReply.java
└── grpc/vn/example/stock/v1/
    └── StockServiceGrpc.java
```

With the protobuf Maven plugin, outputs usually appear under `target/generated-sources/protobuf/java` and `target/generated-sources/protobuf/grpc-java`. Exact paths depend on plugins and configuration; rely on your actual build outputs.

## 3. Verifying That Generation Tasks/Goals Executed

### Gradle

In setups using the protobuf Gradle plugin, common tasks are:

- `generateProto`: generates code from `main` source set protos.
- `generateTestProto`: generates code from `test` source set protos, if present.
- `compileJava`: compiles application code together with `main` generated sources.
- `compileTestJava`: compiles tests and test generated sources.

Run:

```bash
./gradlew tasks --all
./gradlew clean generateProto
./gradlew compileJava
./gradlew compileTestJava
```

`tasks --all` confirms task names in your project; custom source sets or plugin versions may create different tasks. When the plugin wires task dependencies properly, running `compileJava` automatically triggers generation before compilation. `clean` is helpful when verifying outputs from scratch, while normal development cycles can rely on incremental/up-to-date checks.

To inspect which tasks run and how outputs are handled:

```bash
./gradlew generateProto --info
./gradlew compileJava --dry-run
```

If generation does not appear in the task graph, check the protobuf plugin, proto source sets, and task configuration. Never manually add generated directories to the Java source set before verifying whether the plugin already registered them.

### Maven

With `protobuf-maven-plugin`, goals generating messages and gRPC stubs are usually bound to the `generate-sources` phase:

- `protobuf:compile`: generates Java messages.
- `protobuf:compile-custom`: invokes the gRPC Java plugin to generate service APIs.

Run:

```bash
mvn clean generate-sources
mvn compile
mvn test
```

`mvn compile` and later phases pass through `generate-sources`; if executions are bound properly, generation runs automatically. With Maven, inspect plugin logs to verify which `protoc` and plugin binaries actually executed.

## 4. Confirming Generated Files Exist in the Right Source Set

Checking that a single file exists is not enough. Confirm **all output categories exist** and belong to the right source set.

Checklist for `main`:

- Message classes from the Java generator exist.
- Service class `StockServiceGrpc` exists when the schema defines a `service`.
- Files reside in `main`'s generated root, not only under `test`.
- The Java compiler sees both groups of sources.
- No duplicate class is generated from another schema copy.

You can list files after generation:

```powershell
Get-ChildItem -Recurse build/generated/source/proto/main |
    Select-Object -ExpandProperty FullName
```

On a Unix shell:

```bash
find build/generated/source/proto/main -type f
```

This is an output diagnostic step. In CI, let compilation and descriptor tests verify the API rather than relying solely on file names in a script.

If dedicated test protos exist, verify `generateTestProto` and `compileTestJava` separately. Test-only services must never leak into the main artifact; conversely, production messages and services must be generated from the `main` source set.

## 5. Verifying Generated Descriptors and Schemas

A descriptor test confirms the generated API accurately reflects key declarations in `.proto`. This catches cases where the build still produces Java code, yet a service, method, or field was altered unexpectedly.

JUnit 5 example:

```java
package vn.example.stock;

import io.grpc.MethodDescriptor;
import org.junit.jupiter.api.Test;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockServiceGrpc;

import static org.junit.jupiter.api.Assertions.*;

class GeneratedSchemaTest {

    @Test
    void generatedMessageContainsExpectedFieldNumbers() {
        var descriptor = StockReply.getDescriptor();

        assertEquals(
                1,
                descriptor.findFieldByName("sku").getNumber());

        assertEquals(
                2,
                descriptor.findFieldByName("available").getNumber());
    }

    @Test
    void generatedServiceContainsExpectedRpcMethods() {
        assertEquals(
                "learning.stock.v1.StockService",
                StockServiceGrpc.SERVICE_NAME);

        assertEquals(
                MethodDescriptor.MethodType.UNARY,
                StockServiceGrpc.getGetStockMethod().getType());

        assertEquals(
                MethodDescriptor.MethodType.SERVER_STREAMING,
                StockServiceGrpc.getWatchStockMethod().getType());
    }
}
```

Descriptor accessors such as `getGetStockMethod()` and `getWatchStockMethod()` are typical APIs created by the gRPC Java generator; if your project uses a different generator version, inspect the generated class and adapt tests to that public API.

Descriptor tests are valuable because they verify **field numbers** and **RPC cardinality**, not just Java class names. When a schema is intentionally updated, update assertions alongside the contract change so diffs clearly capture what changed.

## 6. Verifying Message Serialization

Generated messages must serialize and parse back cleanly through the protobuf runtime. This is a fast check for failures caused by runtime dependencies, generated classes, or schemas.

```java
import org.junit.jupiter.api.Test;
import vn.example.stock.v1.StockReply;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GeneratedMessageTest {

    @Test
    void generatedMessageRoundTripsThroughProtobuf() throws Exception {
        StockReply original = StockReply.newBuilder()
                .setSku("BOOK-101")
                .setAvailable(17)
                .build();

        StockReply parsed = StockReply.parseFrom(original.toByteArray());

        assertEquals(original, parsed);
        assertEquals("BOOK-101", parsed.getSku());
        assertEquals(17, parsed.getAvailable());
    }
}
```

This test confirms generated messages and the protobuf runtime work together on the basic serialize/parse path. It does not prove compatibility with every published client version; compatibility testing requires running old and new schemas/artifacts separately.

## 7. Verifying Generated Stubs via In-Process RPC

Passing compilation does not prove a generated stub can invoke a server. An in-process test exercises generated method descriptors, marshallers, server base classes, and client stubs without opening TCP ports.

In test scope, add the `grpc-inprocess` dependency matching the grpc-java version line used by your application. If using the grpc BOM, let the BOM manage the version:

```groovy
dependencies {
    testImplementation 'io.grpc:grpc-inprocess'
}
```

Minimal server implementation:

```java
import io.grpc.stub.StreamObserver;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockRequest;
import vn.example.stock.v1.StockServiceGrpc;

final class TestStockService
        extends StockServiceGrpc.StockServiceImplBase {

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> observer) {

        StockReply reply = StockReply.newBuilder()
                .setSku(request.getSku())
                .setAvailable(17)
                .build();

        observer.onNext(reply);
        observer.onCompleted();
    }
}
```

Test calling the generated blocking stub:

```java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import org.junit.jupiter.api.Test;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockRequest;
import vn.example.stock.v1.StockServiceGrpc;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GeneratedStubTest {

    @Test
    void generatedStubInvokesGeneratedServerBase() throws Exception {
        String serverName = InProcessServerBuilder.generateName();

        Server server = InProcessServerBuilder
                .forName(serverName)
                .directExecutor()
                .addService(new TestStockService())
                .build()
                .start();

        ManagedChannel channel = InProcessChannelBuilder
                .forName(serverName)
                .directExecutor()
                .build();

        try {
            StockReply reply = StockServiceGrpc
                    .newBlockingStub(channel)
                    .getStock(StockRequest.newBuilder()
                            .setSku("BOOK-101")
                            .build());

            assertEquals("BOOK-101", reply.getSku());
            assertEquals(17, reply.getAvailable());
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
```

This test verifies gRPC Java dispatch over the in-process transport. It does not verify Spring bean registration, TCP/HTTP2, TLS, or production configuration. If the application relies on Spring gRPC auto-configuration, add an integration test that boots the application context and calls the service over the configured channel/port.

## 8. Distinguishing Codegen Checks from Spring Wiring Checks

| Test | What It Verifies | What It Does Not Prove |
| --- | --- | --- |
| Descriptor test | Message field numbers, service name, RPC types | That Spring registered the server |
| Serialization test | Message parse/serialize with protobuf runtime | Network compatibility between client and server |
| In-process RPC | Generated stub, server base, marshallers, and dispatch | TCP, TLS, Spring auto-configuration |
| Spring integration test | Bean registration, channel/server config, interceptors under test config | Production behavior under real load |
| End-to-end test | Independent client and server communicating in a near-real environment | Every operational and load scenario |

Do not treat an in-process test as proof that TLS works; the in-process transport does not establish TLS like a network connection. Likewise, a descriptor test does not confirm the service bean is registered with Spring.

## 9. Detecting Stale Generated Outputs

A dangerous bug occurs when the generated directory still holds files from an earlier generation run. For example, an RPC was removed from `.proto`, yet old generated output remains because the build was not cleaned properly or a file was created manually.

Verification workflow:

1. Inspect the current schema and list of generated files.
2. Run `clean` to remove old outputs.
3. Re-run generation from scratch.
4. Confirm deleted files and methods no longer appear if removed from the schema.
5. Compile/test to catch any source code still referencing old APIs.

With Gradle:

```bash
./gradlew clean generateProto compileJava test
```

With Maven:

```bash
mvn clean generate-sources compile test
```

Never manually delete individual generated files just to make a build pass; inspect task outputs and lifecycle bindings. `clean` is a useful diagnostic step, while regular builds must track inputs and outputs accurately so generation is never skipped erroneously.

## 10. Integrating Checks into CI

A CI pipeline verifying generated code should perform at least:

1. Check out schemas and build configuration.
2. Use the agreed Gradle/Maven Wrapper and JDK.
3. Run clean generation.
4. Compile `main` and `test` source sets.
5. Run descriptor and serialization tests.
6. Run in-process or Spring integration RPC tests per scope.
7. Archive generation and dependency resolution logs on failure.

Gradle example:

```bash
./gradlew --no-daemon clean test
```

Maven example:

```bash
./mvnw -B clean verify
```

If `check`/`verify` does not yet include dedicated integration tests, wire that test task/profile into CI. Do not claim a build verifies Spring wiring if the pipeline only runs compilation and unit tests.

When generated sources are not committed, CI can still verify everything cleanly because sources are built from `.proto`. If a contract JAR is published, verify the packaged artifact contains the exact generated API and version matching the reviewed schema.

## 11. Diagnosing Common Errors

| Symptom | Cause to Check |
| --- | --- |
| Missing message classes | Java generator did not run, wrong proto root, or schema syntax error |
| Messages exist, but `*Grpc.java` is missing | gRPC plugin not applied to proto task/goal |
| Files exist, but `compileJava` cannot see them | Generated source root not registered or wrong source set |
| Descriptor test reports wrong method type | Schema cardinality changed or test runs against stale output/version |
| Serialization test throws linkage errors | Incompatible protobuf runtime or missing dependency |
| In-process RPC returns `UNIMPLEMENTED` | Test service did not override the right method or called wrong RPC |
| Spring integration test cannot find service | Bean/service registration or starter configuration error |
| Local passes, CI fails | Stale output, different toolchain, missing import dependency, or unclean environment |
| Tests pass, but TLS fails in real environment | In-process test does not verify network TLS; need real transport tests |

When investigating, keep task/goal logs, generated outputs, and the dependency graph. Isolate whether the failure occurs at generation, source registration, compilation, runtime dispatch, or Spring wiring before changing schemas or bumping versions.

## 12. Hands-On Practice

1. Run clean generation and confirm `StockRequest`, `StockReply`, and `StockServiceGrpc` all exist.
2. Write a descriptor test verifying field numbers and RPC types.
3. Write a serialization round-trip test for `StockReply`.
4. Write an in-process test calling `GetStock` using the generated blocking stub.
5. Remove an RPC from the schema, run clean generation, and confirm the method disappears from the generated API.
6. Place a test-only proto in the test source set and confirm its output does not enter the main artifact.
7. Run compilation from a clean checkout on CI; verify no generated sources need to be committed.
8. Add a Spring integration test confirming the service bean is registered and the client calls the configured server.
9. Distinguish what is proved by descriptor, in-process, Spring integration, and end-to-end tests in a build report.

### Key Takeaway

**Verifying generated code in the build must confirm both the output and its usability.** Check generation tasks/goals, presence of messages and gRPC APIs, source sets, Java compilation, descriptors, serialization, and an RPC via a generated stub. Add Spring integration tests whenever you need to verify bean registration, channels, TLS, or interceptors. Clean CI builds eliminate reliance on stale generated outputs and prove generated code is reproducible from the contract.
