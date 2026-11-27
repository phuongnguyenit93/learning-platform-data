# Generating Messages and Stubs in Gradle

In Spring gRPC, a `.proto` file serves as the contract source for generating two distinct sets of Java code: protobuf message classes representing requests/responses, and gRPC classes providing client stubs along with server base classes. Gradle needs to run the right `protoc` compiler and `protoc-gen-grpc-java` plugin, place the outputs into the appropriate source sets, and compile them alongside your application code.

This lesson sets up that workflow using the protobuf Gradle plugin. The expected result is that developers only manage proto sources and build configuration; on every build, Gradle automatically generates consistent messages, descriptors, and stubs for both client and server. The content applies to a Java Spring gRPC project; service business logic and server runtime configuration are implemented in subsequent steps.

## 1. Distinguishing protoc, the Gradle Plugin, and the gRPC Java Plugin

The three components each have a specific role:

| Component | Role |
| --- | --- |
| protoc | Compiler that reads `.proto`, validates the schema, and generates Java protobuf messages via the Java builtin |
| protoc-gen-grpc-java | Protoc plugin that generates gRPC service descriptors, client stubs, and server base classes |
| com.google.protobuf Gradle plugin | Creates Gradle tasks, wires proto source sets to the compiler/plugin, and registers generated sources for Java compilation |

Running only the `protoc` Java builtin generates message classes, but does not generate `OrderServiceGrpc` or the service base class. Conversely, the gRPC plugin requires the schema already processed by `protoc` and the corresponding runtime dependencies.

Versions must be pinned explicitly:
- The protobuf Gradle plugin version controls integration with Gradle.
- The `protoc` version determines the compiler and code generation for protobuf Java.
- The `protoc-gen-grpc-java` version should stay aligned with the gRPC Java runtime line used in the application.
- The Protobuf Java runtime must be compatible with the `protoc` version that generated the code.

Do not let the build download an unspecified compiler or use different versions between developer workstations and CI. Use the Gradle Wrapper and declare versions centrally in the project's build configuration or version catalog.

## 2. Placing Proto Files in the Right Source Set

For the default `main` source set, place proto files under `src/main/proto`:

```text
src/
  main/
    java/
      com/myshop/order/
    proto/
      shop/order/v1/order_service.proto
  test/
    java/
    proto/
build/
  generated/
    source/
      proto/
```

The `src/main/proto` directory is the default proto source directory for the protobuf Gradle plugin. Files in `src/test/proto` belong to the test source set and are generated separately when the project has contracts/protos used only in tests.

Do not place `.proto` files inside `src/main/java` or the `generated` directory. Proto files are reviewed and version-controlled input sources; generated Java files are build outputs. If a proto imports another file, the import path must resolve from the proto source roots or dependencies configured on the task.

Small example file to verify generation:

```proto
syntax = "proto3";

package shop.greeting.v1;

option java_multiple_files = true;
option java_package = "com.myshop.greeting.v1";
option java_outer_classname = "GreetingProto";

service GreetingService {
  rpc SayHello(HelloRequest) returns (HelloReply);
}

message HelloRequest {
  string name = 1;
}

message HelloReply {
  string message = 1;
}
```

`package` creates the protobuf namespace and forms part of the full gRPC method name. `java_package` determines the package of the generated Java classes. `java_multiple_files = true` generates each message as its own top-level class; if disabled, message classes are typically nested inside an outer class generated from the proto file. `java_outer_classname` gives the outer descriptor class a stable name.

## 3. Configuring the protobuf Gradle Plugin with Groovy DSL

Example `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'com.google.protobuf' version '<protobuf-gradle-plugin-version>'
}

def protobufVersion = '<protobuf-version>'
def grpcVersion = '<grpc-java-version>'

dependencies {
    implementation platform('io.grpc:grpc-bom:' + grpcVersion)

    implementation 'com.google.protobuf:protobuf-java:' + protobufVersion
    implementation 'io.grpc:grpc-protobuf'
    implementation 'io.grpc:grpc-stub'

    // This transport is only needed when the application runs a client/server over Netty.
    runtimeOnly 'io.grpc:grpc-netty-shaded'

    testImplementation 'org.junit.jupiter:junit-jupiter:<junit-version>'
}

protobuf {
    protoc {
        artifact = 'com.google.protobuf:protoc:' + protobufVersion
    }

    plugins {
        grpc {
            artifact = 'io.grpc:protoc-gen-grpc-java:' + grpcVersion
        }
    }

    generateProtoTasks {
        all().each { task ->
            task.plugins {
                grpc {}
            }
        }
    }
}

test {
    useJUnitPlatform()
}
```

Replace the version placeholders with versions approved and pinned by your project. The example uses the gRPC Java BOM to keep `grpc-*` libraries on the same release train; the protobuf compiler and protobuf runtime are declared separately because they belong to the protobuf version line. If the project uses Spring Boot dependency management or a version catalog, move versions into that centralized mechanism instead of repeating them.

In the configuration above:
- `protoc.artifact` selects the protobuf Java compiler.
- `plugins.grpc.artifact` selects the `protoc-gen-grpc-java` executable.
- `generateProtoTasks` adds the gRPC plugin to every proto generation task, including both `main` and `test` source sets if present.
- The Java builtin is configured automatically by the protobuf Gradle plugin for Java projects; the `grpc` plugin adds gRPC-specific generated sources.
- `grpc-protobuf` and `grpc-stub` are compile dependencies for generated gRPC code and application code.
- `grpc-netty-shaded` provides the Netty network transport when needed at runtime; it is not a compiler plugin.

If using Kotlin DSL in `build.gradle.kts`, the conceptual structure is the same, but plugin and task declaration syntax differs from Groovy DSL. Use the syntax matching your project's protobuf Gradle plugin version; do not mix Groovy snippets into a Kotlin DSL file.

## 4. Understanding Output: Message Classes and gRPC Stubs

After successful generation, default outputs typically reside under `build/generated/source/proto` organized by source set and generator:

| Output | Contents |
| --- | --- |
| build/generated/source/proto/main/java | Message classes, enums, outer descriptor class |
| build/generated/source/proto/main/grpc | gRPC service descriptor, client stubs, and server base class |
| build/generated/source/proto/test/java | Message classes generated from src/test/proto |
| build/generated/source/proto/test/grpc | gRPC classes generated from test protos |

Exact directory names may vary depending on source sets and plugin configuration, but the principle is that the Java builtin and the gRPC plugin have separate outputs. Generated files are task outputs, not places to edit code.

For the `GreetingService` example, key classes include:
- `HelloRequest` and `HelloReply`: protobuf messages with builders, getters, parsers, and serialization.
- `GreetingProto`: outer descriptor class because the example sets `java_outer_classname`.
- `GreetingServiceGrpc`: gRPC class generated from the service definition.
- `GreetingServiceGrpc.GreetingServiceBlockingStub`: synchronous client stub.
- `GreetingServiceGrpc.GreetingServiceStub`: asynchronous client stub.
- `GreetingServiceGrpc.GreetingServiceImplBase`: base class for the server to override methods.

If you see `HelloRequest` but not `GreetingServiceGrpc`, inspect the `grpc` plugin configuration in `generateProtoTasks`. If you see no message classes at all, check the Java builtin, source roots, and the `protoc` task.

## 5. Running Generation and Compilation Tasks

Common commands:

```bash
./gradlew clean generateProto
./gradlew compileJava
./gradlew test
```

On Windows, you can run the Gradle Wrapper via `.\gradlew.bat` with the same task names. `generateProto` generates sources from protos in the `main` source set; `compileJava` compiles the application together with the generated sources wired into the source set by the plugin. `test` compiles and runs the test source set.

Normally, the compile task already depends on the required generated-source task. Running `generateProto` standalone is useful when verifying code generation; running `compileJava` verifies that generated code and dependencies are truly compatible. You do not need to manually add `build/generated/...` to `sourceSets` if the protobuf Gradle plugin already registers its outputs.

When inspecting the task graph or compiler logs:

```bash
./gradlew tasks --all
./gradlew generateProto --info
```

Never edit files in `build/generated`. When a proto changes, Gradle evaluates inputs/outputs and re-runs the affected tasks. `clean` removes generated outputs; subsequent builds regenerate them from proto sources.

## 6. Using Generated Messages and Stubs

After building, the client constructs messages via builders and calls them through the generated stub:

```java
HelloRequest request = HelloRequest.newBuilder()
        .setName("Lan")
        .build();

GreetingServiceGrpc.GreetingServiceBlockingStub stub =
        GreetingServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(1, TimeUnit.SECONDS);

HelloReply reply = stub.sayHello(request);
System.out.println(reply.getMessage());
```

`channel` is a `ManagedChannel` configured and lifecycle-managed at the application layer. Stubs are immutable with respect to call options; `withDeadlineAfter` returns a new stub carrying the deadline for the call. Never create a new `ManagedChannel` per request.

The server extends the generated base class and overrides the method:

```java
public final class GreetingGrpcService
        extends GreetingServiceGrpc.GreetingServiceImplBase {

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> responseObserver) {
        HelloReply response = HelloReply.newBuilder()
                .setMessage("Hello, " + request.getName())
                .build();

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
```

The generated base class supplies RPC method signatures matching the proto. The service implementation only writes business logic and follows the observer lifecycle; never edit generated sources. In Spring gRPC, service implementations are registered according to the starter/framework mechanism in use, while Gradle generation remains an independent build step.

## 7. Dependencies and Annotations at Compile Time

Generated message code requires the protobuf runtime. Generated gRPC code requires gRPC APIs such as `MethodDescriptor`, `Channel`, stubs, `StreamObserver`, and server definitions; therefore, `grpc-protobuf` and `grpc-stub` must be on the compile classpath.

Some generator versions emit the `javax.annotation.Generated` annotation. On JDKs that no longer provide that annotation by default, the compiler may report a missing `javax.annotation` package. Only if you encounter this error and your project's generator actually references that annotation, add an appropriate compile-only dependency, for example:

```groovy
compileOnly 'javax.annotation:javax.annotation-api:1.3.2'
```

Do not add annotation dependencies out of habit if your current generated code does not require them. Likewise, avoid adding transport implementations to the compile dependencies of a contract-only module if that module does not open channels or servers.

## 8. Proto Imports and Multi-Module Gradle Projects

If a proto imports well-known types such as `Timestamp`, `FieldMask`, or `Empty`, `protoc` includes the corresponding paths in its distribution; use the standard import paths, such as `google/protobuf/timestamp.proto`. For internal protos, ensure the task has the source root or artifact containing the imported file.

In a multi-module project, choose a single source of truth for contracts:
- A dedicated contract module holds the proto files and may publish either a proto artifact or a generated Java contract artifact.
- Both client and server depend on the same published contract version.
- Avoid copying the same proto file into multiple modules and generating duplicate classes in the same package.
- If a downstream module must import protos from an upstream module, configure the dependency/proto source path explicitly and version it.
- When upgrading a contract, verify the generated API and compatibility before upgrading both client and server.

Do not commit generated sources unless repository policy explicitly requires it. Typically, only `.proto` files and build configurations are committed; generated files live in `build/` and are reproduced in CI. If an organization publishes generated code as an artifact, the artifact must be tied to the exact proto version and compiler/plugin versions.

## 9. Diagnosing Common Generation Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Message classes exist, but GreetingServiceGrpc is missing | The `grpc` plugin is not configured on the generation task | Check `protobuf.plugins.grpc` and `generateProtoTasks` |
| No generated Java files at all | Proto sources are in the wrong directory, the protoc task did not run, or proto compilation failed | Check `src/main/proto`, task outputs, and `--info` logs |
| Imported `.proto` not found | Missing proto source root/dependency or wrong import path | Verify the import path and task include roots |
| Java compile reports missing `io.grpc.*` | Missing `grpc-stub`/`grpc-protobuf` or mismatched dependency versions | Inspect the compile classpath and BOM |
| Compile reports missing `javax.annotation.Generated` | The generator version emits the annotation, but the JDK does not provide it | Inspect generated sources and add `compileOnly` annotation API if needed |
| Client and server generated APIs differ | Two modules use different proto or generator versions | Compare contract artifacts and compiler/plugin versions |
| IDE shows red errors while Gradle compile passes | The IDE has not synced the Gradle source/task model | Reload the Gradle project and check task outputs |

When debugging, start by examining task inputs/outputs and the underlying `protoc` error. Never edit generated files to work around errors, as the next build will overwrite them and obscure the root cause.

## 10. Completion Checklist

- [ ] `.proto` files are placed in `src/main/proto` or an explicitly configured source root.
- [ ] Protobuf package and Java package are declared with a version.
- [ ] `java_multiple_files` and outer class are chosen intentionally.
- [ ] Protobuf Gradle plugin version is pinned.
- [ ] `protoc` version is compatible with the protobuf runtime.
- [ ] `protoc-gen-grpc-java` is configured and aligned with the gRPC Java runtime.
- [ ] `generateProtoTasks` applies the `grpc` plugin to the required source sets.
- [ ] Message classes and gRPC stubs are generated into their respective outputs.
- [ ] The compile classpath includes the required protobuf/gRPC APIs.
- [ ] `generateProto`, `compileJava`, and `test` succeed.
- [ ] Generated outputs are never edited directly.
- [ ] Multi-module setups use a single contract source and clear versioning.

**Self-Check**

**Question 1.** Why isn't configuring only the `protoc` Java builtin enough to get gRPC stubs?

*Answer:* The Java builtin generates protobuf message classes. Client stubs and server base classes are generated by `protoc-gen-grpc-java`, so you must declare the `grpc` plugin and apply it to the generation tasks.

**Question 2.** How does `src/main/proto` differ from `build/generated/source/proto`?

*Answer:* `src/main/proto` holds contract source files that are reviewed and version-controlled. `build/generated/source/proto` contains outputs generated by Gradle from those sources and can be deleted and regenerated.

**Question 3.** Which components generate `GreetingServiceGrpc` and `HelloRequest`?

*Answer:* `HelloRequest` is generated by the protobuf Java builtin; `GreetingServiceGrpc` is generated by `protoc-gen-grpc-java` from the service definition.

**Question 4.** Why must client and server use the same version of the contract artifact?

*Answer:* Using the same contract version keeps generated method paths, request/response types, and semantics consistent. If two modules copy/generate independently from different schemas, runtime behavior can diverge even if each module compiles on its own.

**Question 5.** Should you edit generated files directly when a compilation error occurs?

*Answer:* No. Generated files are overwritten on the next build. Fix the proto file, compiler/plugin configuration, or dependencies instead, then regenerate.

Gradle generation builds a reproducible bridge between the protobuf contract and Java application code. When proto sources, `protoc`, the gRPC generator, and runtime dependencies are pinned and configured consistently, the client gets messages/stubs to invoke RPCs and the server gets base classes to implement handlers. This is the foundational step for developing and testing Spring gRPC services reliably in both local builds and CI.
