# Generated Code Does Not Match Proto

In Spring gRPC, the `.proto` file is the shared contract between client and server. From this contract, the build produces two groups of Java code: Protocol Buffers message classes and gRPC stub/base classes for services. When generated code does not reflect the current proto content, the application may report missing classes or methods at compile time, or the client may call an RPC the server does not recognize at runtime.

This guide walks through tracing the full path from proto to Java code, finding the exact cause of the mismatch, and regenerating code reproducibly in a Spring gRPC project.

## Identify the Problem

Common symptoms include:

- The IDE or compiler cannot find a message, enum, service stub, or method newly added to proto.
- Java code still contains old fields or RPCs even though the `.proto` file was updated.
- Message classes are generated, yet `*Grpc` classes or stubs do not appear.
- Imports in the service implementation point to a different package than the one the generator just produced.
- Generated code fails to compile because it calls a non-existent runtime API, or there is a compatibility error between generated code and protobuf/gRPC libraries.
- The client compiles successfully yet receives status `UNIMPLEMENTED` when calling a new RPC.

Not all of these errors share the same root cause. Missing-symbol errors usually point to input or code-generation configuration; compatibility errors point to versions; `UNIMPLEMENTED` usually calls for checking the contract and the service actually registered on the server.

## Understand the Generated Outputs Properly

The pipeline looks like:

```text
*.proto
   |
   +-- protoc ----------------------> Java message / enum / descriptor
   |
   +-- protoc-gen-grpc-java --------> Java service base class / stubs
                                           |
                                           v
                                  compile and run application
```

`protoc` generates code for messages, enums, and descriptors. The `protoc-gen-grpc-java` plugin generates code for services, including the class suffixed with `Grpc`, the base class for server implementation, and client stub types. Therefore, running `protoc` alone without configuring the gRPC plugin can generate messages without generating stubs.

Example contract:

```proto
syntax = "proto3";

package inventory.v1;

option java_package = "com.acme.inventory.v1";
option java_multiple_files = true;
option java_outer_classname = "InventoryProto";

service InventoryService {
  rpc GetItem(GetItemRequest) returns (GetItemResponse);
}

message GetItemRequest {
  string id = 1;
}

message GetItemResponse {
  string id = 1;
  string name = 2;
}
```

With those options, the Java types are typically referenced like this:

```java
import com.acme.inventory.v1.GetItemRequest;
import com.acme.inventory.v1.GetItemResponse;
import com.acme.inventory.v1.InventoryServiceGrpc;

InventoryServiceGrpc.InventoryServiceBlockingStub stub = ...;
GetItemResponse response = stub.getItem(
    GetItemRequest.newBuilder().setId("item-42").build()
);
```

Java options directly affect class names and locations:

| Proto Element | Effect on Java Code |
| --- | --- |
| `package` | Full protobuf name of the service/message; for gRPC, it participates in forming the wire service name. |
| `option java_package` | Generated Java package. If omitted, the generator derives a Java package using protobuf's default rules, which may not match the package imported by the application. |
| `option java_multiple_files = true` | Each top-level message/enum is generated into its own Java class. |
| `option java_multiple_files = false` or omitted | Messages/enums usually sit inside an outer wrapper class. For example, you may have to use `InventoryProto.GetItemRequest`. |
| `option java_outer_classname` | Names the wrapper class holding the descriptor and, depending on settings, nested types. If omitted, the name is derived from the proto filename. |
| `service InventoryService` | The gRPC plugin generates `InventoryServiceGrpc`; RPC names in the service determine methods on stubs and descriptors. |

In particular, `package` and `java_package` serve two distinct purposes. Changing `java_package` changes Java imports; changing the protobuf `package` can change the full service name, affecting the RPC path on the wire.

## Diagnostic and Remediation Workflow

### 1. Confirm the Build Reads the Right Proto File

First, find the `.proto` file the build actually feeds into code generation. Check:

- Whether the file being edited sits inside the proto source directory configured by the build tool.
- Whether another proto file with the same name or same message/service definitions exists in another module.
- Whether `import` statements in proto pull schemas from the right dependency/version.
- Whether a multi-module build is running in the module containing the proto.

An easy mistake to miss is editing a file inside a docs or examples directory while Gradle/Maven generates code from a different proto directory. Confirm input paths from the build configuration and codegen task logs rather than relying solely on filename.

### 2. Regenerate Code from Current Inputs

Code in the generated directory is a build output. When proto changes, run the generation task or a clean build to eliminate stale outputs.

With Gradle and the protobuf Gradle plugin:

```bash
# macOS / Linux
./gradlew clean generateProto compileJava

# Windows
gradlew.bat clean generateProto compileJava
```

With Maven, when the protobuf plugin is bound to the `compile` lifecycle:

```bash
mvn clean compile
```

If the project has a dedicated task or profile for proto generation, use the exact configured task/profile. A clean build from the command line using Gradle Wrapper or Maven Wrapper clarifies whether the error is in the build or only in the IDE cache/index.

Common output directories are:

| Build Tool | Java Messages | gRPC Java |
| --- | --- | --- |
| Gradle protobuf plugin | `build/generated/source/proto/main/java` | `build/generated/source/proto/main/grpc` |
| protobuf-maven-plugin | `target/generated-sources/protobuf/java` | `target/generated-sources/protobuf/grpc-java` |

Paths may differ if the project changes source sets, modules, classifiers, or output configuration. Check the build configuration and logs if you do not see these directories.

After running, open the generated file and check that the package declaration, class names, field names, and RPCs reflect the proto in use. Do not edit generated files directly: the next build will overwrite them and changes will no longer be traceable to the contract.

### 3. Check That the gRPC Generator Plugin Is Enabled

If Java messages appear yet no `*Grpc` class exists, check plugin configuration. With the Gradle protobuf plugin, the minimal conceptual configuration includes the `protoc` artifact, the gRPC plugin, and wiring the plugin into the generation tasks:

```groovy
plugins {
    id 'java'
    id 'com.google.protobuf' version '<protobuf-gradle-plugin-version>'
}

def protobufVersion = '<protobuf-version>'
def grpcVersion = '<grpc-version>'

dependencies {
    implementation "com.google.protobuf:protobuf-java:${protobufVersion}"
    implementation "io.grpc:grpc-protobuf:${grpcVersion}"
    implementation "io.grpc:grpc-stub:${grpcVersion}"
}

protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:${protobufVersion}"
    }
    plugins {
        grpc {
            artifact = "io.grpc:protoc-gen-grpc-java:${grpcVersion}"
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
```

This snippet illustrates configuration for a project using the protobuf Gradle plugin directly. If the Spring gRPC starter or Spring Boot dependency management already manages certain runtime libraries, keep your project's unified version management and only add the missing codegen configuration.

With Maven, `protobuf-maven-plugin` needs to run both the `compile` goal to generate messages and `compile-custom` to invoke the gRPC plugin. Configuration typically looks like:

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
  <executions>
    <execution>
      <goals>
        <goal>compile</goal>
        <goal>compile-custom</goal>
      </goals>
    </execution>
  </executions>
</plugin>
```

The Maven example above uses an OS classifier variable; the project must configure the extension providing `${os.detected.classifier}` (commonly `os-maven-plugin`) and declare the corresponding version properties. Cross-check against your project's plugin versions and conventions before copying configuration.

### 4. Match Generated Package and Type Names

When the compiler reports `cannot find symbol` even though the generated file exists, inspect the `package` line directly at the top of the generated file and compare it with imports in application code.

For example, if the proto declares:

```proto
option java_package = "com.acme.inventory.api";
option java_multiple_files = true;
```

then message imports must use package `com.acme.inventory.api`. If `java_multiple_files` is not enabled, inspect the outer wrapper class and reference messages according to the generated nested structure.

For services, check all three parts: the protobuf `package` name, `service` name, and RPC name. If the client imports the right class yet calls a non-existent method, the client may be using a stub generated from a different proto version or from another similarly named service.

### 5. Align Generator and Runtime Versions

Generated code depends on protobuf and gRPC library APIs. If the generator and runtime versions drift apart, the compiler may report missing classes/methods or generated code may be incompatible at runtime.

Check these groups separately:

- The `protoc` version downloaded or invoked by the build tool.
- The `protobuf-java` version on compile/runtime classpaths.
- The `protoc-gen-grpc-java` version used to generate stubs.
- The `grpc-*` runtime libraries used by the application, such as `grpc-stub` and `grpc-protobuf`.
- The Spring gRPC/Spring Boot BOM version if the project uses dependency management to manage those libraries.

Keep `protoc` and `protobuf-java` within a compatible version range per protobuf guidelines; keep the `protoc-gen-grpc-java` plugin at the same version as the matching gRPC Java runtime libraries. Do not upgrade a single gRPC dependency in isolation while the remaining dependencies stay pinned by a BOM or another module at an older version.

You can inspect the dependency tree to spot multiple versions appearing together:

```bash
# Gradle
./gradlew dependencies --configuration compileClasspath

# Maven
mvn dependency:tree -Dincludes=com.google.protobuf,io.grpc
```

Compare the actual resolved versions in the dependency tree against the artifact versions declared in generator configuration. Checking only the versions written in `build.gradle` or `pom.xml` is insufficient if dependency management or transitive dependencies override versions during resolution.

### 6. Check `UNIMPLEMENTED` Errors at Runtime

If both client and server code compile yet an RPC call returns `UNIMPLEMENTED`, check:

1. Whether both client and server were generated from the exact same proto version.
2. Whether protobuf `package`, `service`, and RPC names match on both sides.
3. Whether the server implements the newly generated `*Grpc.*ImplBase` class.
4. Whether the service implementation is registered in the Spring application context and wired into the server by Spring gRPC.
5. Whether the client connects to the right server instance/environment where the new version is deployed.

gRPC identifies methods by paths of the form `/package.Service/Method`. Thus, changing a protobuf package, service, or method can cause the client to call a path that an older server does not serve. In this situation, regenerating code on the client is not enough; you must build and deploy the server from the same agreed contract.

## Quick Lookup Table

| Symptom | Cause to Check First | Resolution |
| --- | --- | --- |
| New message class not found | Build reads wrong proto or has not regenerated code | Verify proto sources, run clean and codegen tasks. |
| Messages exist yet `*Grpc` is missing | `protoc-gen-grpc-java` plugin undeclared or not attached to task | Check gRPC plugin and `compile-custom`/`generateProtoTasks`. |
| Wrong package import | `java_package` or `java_multiple_files` differs from code assumptions | Read package and class structure in generated files, then fix imports or proto options intentionally. |
| Old fields/methods remain | Stale output, wrong module built, or IDE using stale generated sources | Run clean via wrapper, verify output of the right module, resync IDE. |
| Generated code fails to compile | Runtime protobuf/gRPC incompatible with generator | Inspect dependency tree and align versions per BOM/compatibility guidance. |
| Client receives `UNIMPLEMENTED` | Client/server differ in service name or server has not registered the new RPC | Match package/service/method and verify the server runs the right build. |

## Example of Handling a Specific Change

Suppose the team adds RPC `GetItem` to `InventoryService`, yet the IDE reports `getItem(...)` does not exist on `InventoryServiceBlockingStub`.

1. Open the proto file used by the build and confirm `rpc GetItem(...)` is inside the right `service InventoryService`.
2. Check that the gRPC generation task ran; if only `GetItemRequest.java` and `GetItemResponse.java` appear without `InventoryServiceGrpc.java`, revisit gRPC plugin configuration.
3. Run `clean` and regenerate code using the project's wrapper.
4. Open the newly generated `InventoryServiceGrpc.java`, confirm the corresponding method exists, and inspect the class package.
5. Inspect the compile classpath to ensure `grpc-stub`, `grpc-protobuf`, and the gRPC plugin use compatible versions.
6. Rebuild the server module and confirm the implementation extends the new base class. If the client still receives `UNIMPLEMENTED`, verify the server instance the client calls has deployed the new build.

This workflow separates three questions: is the build reading the right contract, did the generator produce the right API, and is the running server actually exposing that API?

## Prevent Recurring Mismatches

- Place proto files in a clear source set and manage proto imports via versioned dependencies.
- Centralize versions of protoc, the gRPC plugin, and runtime libraries with properties or an appropriate BOM.
- Keep code generation inside the build lifecycle so CI always generates code from proto in the same build.
- Do not commit or hand-edit generated sources unless project convention requires it; always treat proto files and generator config as the source of truth.
- Whenever modifying `package`, `service`, `rpc`, or Java options, review impact on both Java imports and client/server compatibility.
- In CI, cleanly build the module containing proto and run integration tests covering at least one critical RPC call.

When generated code does not match proto, verify the exact inputs, regenerate code, inspect package/plugin configuration, and only then check runtime versions and the running server. Following this order isolates errors cleanly from contract source to RPC execution time.
