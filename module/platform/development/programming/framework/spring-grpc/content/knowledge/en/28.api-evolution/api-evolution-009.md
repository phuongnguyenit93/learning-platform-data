# Compatibility of Generated Code

## 1. Objectives

In Spring gRPC, Protobuf files are the source of truth for contracts; from them, tools generate Java messages, service base classes, and client stubs. When upgrading schemas or dependencies, a change might remain wire-compatible yet fail to compile Java code, fail to instantiate generated classes, or prevent the server from registering the right methods.

**Generated code compatibility** is the ability of Protobuf schemas, generated Java code, codegen compilers/plugins, runtime libraries, and application code using those classes to work together properly. It is a distinct layer alongside wire compatibility and behavioral compatibility.

After this lesson, you will be able to:

- Distinguish Protobuf Java message code from gRPC service/stub code.
- Identify the roles of `protoc`, `protoc-gen-grpc-java`, and runtime dependencies.
- Keep Java packages, class names, and generated accessors stable when source compatibility is needed.
- Manage generator/runtime versions in a controlled manner.
- Prevent multiple Protobuf/gRPC runtime versions from appearing on the classpath.
- Build a reproducible code generation pipeline in CI.
- Test source, binary/runtime, and wire compatibility before upgrading.

## 2. What Gets Generated from a .proto File

A gRPC contract typically generates two distinct groups of code:

| Generated Code Group | Primary Tool | Examples |
|---|---|---|
| Protobuf Java messages | `protoc` with built-in Java generator | `SearchRequest`, `SearchResponse`, enums, builders, and descriptors |
| gRPC Java service | `protoc-gen-grpc-java` plugin | `CatalogServiceGrpc`, `ImplBase`, blocking/async/future stubs |

Example schema:

```proto
syntax = "proto3";

package catalog.v1;
option java_package = "dev.example.catalog.v1";
option java_multiple_files = true;
option java_outer_classname = "CatalogProtocol";

service CatalogService {
  rpc Search(SearchRequest) returns (SearchResponse);
}

message SearchRequest {
  string query = 1;
}

message SearchResponse {
  repeated string product_ids = 1;
}
```

The Java generator produces message classes and descriptors. The gRPC Java plugin produces service descriptors, method descriptors, stubs, and base classes for server implementations. Applications typically use both groups together:

```java
SearchRequest request = SearchRequest.newBuilder()
        .setQuery("keyboard")
        .build();

SearchResponse response = CatalogServiceGrpc
        .newBlockingStub(channel)
        .search(request);
```

If you run only the Java generator without the gRPC plugin, message classes may exist, while `CatalogServiceGrpc` and stubs are missing. If the gRPC plugin runs against an unexpected schema or compiler version, generated service code may not match the project's API/runtime.

## 3. Distinguishing Compatibility Layers

| Layer | What Must Be Compatible | Error Example |
|---|---|---|
| Wire compatibility | Protobuf bytes and full method paths | Client calls old path while server only registers new path |
| Generated source compatibility | Java package, class, method, and accessor names | Changing `java_package` breaks caller imports |
| Runtime compatibility | Generated code runs against runtime dependencies | Generated class calls an unavailable runtime API/version |
| Build/codegen compatibility | Compiler and plugins generate consistent code | CI and developer machines generate different classes |
| Behavioral compatibility | Server behavior still honors the contract | Getter still compiles, yet business defaults changed |

A change can be compatible in one layer yet incompatible in another. For instance, changing `java_package` does not change binary Protobuf fields or the full method path if the proto `package` stays the same, yet it breaks compilation of Java source using the old package.

When reviewing an upgrade, answer each question separately: is the wire intact, does the generated Java API change, does the runtime support the generated code, is the build reproducible, and is caller behavior preserved?

## 4. Roles of protoc and the gRPC Java Plugin

### protoc

`protoc` reads `.proto` files, validates the schema, and generates code for the requested language. For Java, it produces message classes, enums, builders, and descriptors.

Illustrative command:

```bash
protoc \
  --proto_path=src/main/proto \
  --java_out=build/generated/source/proto/main/java \
  src/main/proto/catalog.proto
```

### protoc-gen-grpc-java

The gRPC Java plugin generates the service/stub code:

```bash
protoc \
  --proto_path=src/main/proto \
  --plugin=protoc-gen-grpc-java=/path/to/protoc-gen-grpc-java \
  --grpc-java_out=build/generated/source/proto/main/grpc \
  src/main/proto/catalog.proto
```

The plugin path depends on the OS and how the build fetches executables. In Gradle/Maven, the build plugin usually manages downloading and invoking the executable; never manually copy an unversioned plugin binary onto developer machines.

These two steps illustrate generator responsibilities, not a recommendation to write custom shell tasks for every project. Use a maintained build plugin with explicitly configured versions so both the Java generator and gRPC plugin are invoked consistently.

## 5. Generated Java API Can Change Even When Wire Format Does Not

### java_package

`package` in Protobuf determines the service namespace on the wire. `java_package` determines the package of generated classes.

```proto
package catalog.v1;
option java_package = "dev.example.catalog.v1";
```

Changing `java_package` from `dev.example.catalog.v1` to `dev.example.api.catalog` keeps the full method path `/catalog.v1.CatalogService/Search` intact, yet Java imports in callers and servers will change. This is a source compatibility break, not necessarily a wire break.

### java_multiple_files

`java_multiple_files = true` generates messages/enums as separate top-level Java classes. Omitting this option causes types to be accessed through an outer wrapper class derived from the proto file. Changing this option alters class names and imports even if schema fields remain unchanged.

### java_outer_classname

If `java_outer_classname` is not declared, the wrapper name is derived from the filename per generator rules. Renaming the proto file can change the wrapper name and break source code referencing that class. Explicit declaration keeps the wrapper name stable.

### Field Names and Accessors

Field numbers determine wire identity; field names determine generated Java accessors:

```proto
message SearchRequest {
  string query_text = 1;
}
```

Generated Java has accessors matching the field name, such as `getQueryText()`. If renamed to `query` while keeping tag `1`, old bytes can still be parsed, yet source code calling `getQueryText()` will fail to compile after regenerating code.

Therefore:

- Keep `java_package`, `java_multiple_files`, and `java_outer_classname` stable when callers depend on the generated API.
- Avoid renaming fields purely for cosmetics if Java code or JSON mappings use the old names.
- When forced to rename, run a separate source migration and update all callers.
- Never edit generated Java files directly to fix issues; changes must originate in the schema or generator configuration.

## 6. Generated gRPC Service APIs Are Also a Source Contract

For the service:

```proto
service CatalogService {
  rpc Search(SearchRequest) returns (SearchResponse);
}
```

The gRPC Java plugin produces an API like:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub blockingStub =
        CatalogServiceGrpc.newBlockingStub(channel);

SearchResponse response = blockingStub.search(request);
```

On the server, applications typically extend:

```java
public final class CatalogGrpcService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void search(
            SearchRequest request,
            StreamObserver<SearchResponse> observer) {
        // Process the request and terminate the observer exactly once.
    }
}
```

Changing the Protobuf package, service name, or method name alters generated types and can alter the full method path. Changing cardinality from unary to streaming also alters handler/stub signatures. Review these changes as API migrations, not merely re-running code generation.

Stub flavors are also part of the generated API: blocking, async, and future stubs may be used by different callers. Do not remove or alter stub generation without locating all dependent call sites.

## 7. Runtime Dependencies Must Be Compatible with Generated Code

Generated source does not bundle the entire Protobuf or gRPC implementation. At runtime, the classpath needs compatible libraries:

| Component | Role |
|---|---|
| `protobuf-java` | Runtime for generated Protobuf messages |
| `grpc-protobuf` | Integrates Protobuf with gRPC |
| `grpc-stub` | Stub APIs, base services, and call abstractions |
| `grpc-api` | Core gRPC Java APIs |
| Transport implementation | E.g., Netty or Netty shaded for channels/servers |
| Spring gRPC starter | Integrates lifecycle, bean registration, and configuration with Spring |

Generated Protobuf Java code is tightly coupled to the runtime API. Do not assume arbitrary combinations of generated code and `protobuf-java` are compatible. The safe rule is to pin compiler/generator and runtime to a verified compatible version set; prefer matching the same release line per Protobuf Java guidance.

Similarly, gRPC generated service code requires APIs from the gRPC Java runtime. Keep `grpc-*` artifacts on the same release line using gRPC Java's dependency management/BOM if your project uses it. The Spring gRPC starter version must also sit within the compatibility range published by the starter.

A common pitfall is compiling cleanly because one dependency pulls in a newer runtime version, while the deployment environment loads a different runtime via transitive dependencies or classloaders. Always inspect the dependency graph and run smoke/integration tests on a classpath close to production.

## 8. Managing Toolchain and Runtime Versions

A toolchain has at least these versions to manage:

- Protobuf compiler `protoc`.
- gRPC Java codegen plugin `protoc-gen-grpc-java`.
- Protobuf Java runtime.
- `grpc-*` libraries.
- Spring gRPC starter and corresponding Spring Boot/Spring Framework versions.
- JDK and Java source/target configuration.

Do not update one component in isolation while ignoring related ones. For example, upgrading `protoc` while leaving the gRPC plugin far behind can cause builds to emit message and service code from two different toolchain generations.

A version policy table in your build or engineering docs helps reviewers see the aligned versions:

| Component | How to Manage |
|---|---|
| `protoc` | Pin a specific version in the build |
| `protoc-gen-grpc-java` | Pin a specific version; upgrade alongside gRPC Java |
| `protobuf-java` | Select runtime compatible with generated Java code |
| `grpc-*` | Use a BOM or dependency constraints to stay aligned |
| Spring gRPC starter | Follow the starter's compatibility matrix |
| JDK | Use a consistent toolchain version across CI and local machines |

Avoid `latest`, dynamic versions, or relying on whatever version happens to be installed on a developer's machine. If versions drift over time because the build does not lock them, the same commit can generate different code across builds.

## 9. Managing the Dependency Graph to Prevent Duplicate Runtimes

An application can pull in `protobuf-java` from multiple transitive dependencies. If the classpath contains multiple versions, the build tool usually picks one via resolution rules; the selected version might not be the one generated code or the starter was tested with.

Check:

- Is there exactly one effective version of `protobuf-java` on the runtime classpath?
- Are `grpc-api`, `grpc-stub`, `grpc-protobuf`, and transport artifacts on the same release line?
- Is an old dependency downgrading `grpc-*` or Protobuf runtime to an older version?
- Does any library bundle/shade its own Protobuf or gRPC runtime?
- Do tests and production resolve the exact same dependency graph?

Example inspection commands with Gradle:

```bash
./gradlew dependencyInsight --dependency protobuf-java --configuration runtimeClasspath
./gradlew dependencyInsight --dependency grpc-stub --configuration runtimeClasspath
```

With Maven, use `mvn dependency:tree` and inspect relevant transitive branches. When forcing versions, prefer centralized dependency management/BOMs or constraints; avoid scattering ad-hoc exclusions without understanding which dependency needs which API.

Do not place both `grpc-netty` and `grpc-netty-shaded` on the runtime classpath unless intentionally using both transports. Choose the transport supported by your Spring gRPC starter and configure it consistently.

## 10. Reproducible Code Generation

Generated code should be identical when the same schema and toolchain run in CI or on a developer machine. The workflow should:

1. Store `.proto` files in a version-controlled source directory.
2. Pin versions of the compiler and all codegen plugins.
3. Have the build tool invoke generators with the exact same configuration in every environment.
4. Output generated code into a dedicated build directory, separate from handwritten source.
5. Never edit generated files manually.
6. If the repository commits generated code, always regenerate with the pinned toolchain and review the diff alongside the schema.
7. If the repository generates during build, ensure CI runs codegen before compile/test.

Pick one clear policy:

| Policy | Advantage | What to Guarantee |
|---|---|---|
| Generate at build time | Schema is the single source of truth; avoids huge generated diffs in reviews | Build/CI must have exact compiler and plugin versions |
| Commit generated source | Consumers can inspect or use generated source directly | Every schema change must regenerate; no manual edits |

Do not both commit generated code and let some modules regenerate it with a different version. That creates two sources of truth and causes bugs that appear in only one environment.

When changing generators, the generated source diff can be huge even when `.proto` is unchanged. Reviews must determine which parts are internal generator formatting changes versus public API or runtime requirement changes. Never wave through the entire diff without understanding the impact.

## 11. Java Annotations and JDK Compatibility

Generated code may reference annotations or APIs tied to the JDK and annotation libraries. For example, some gRPC Java generator versions emit `@javax.annotation.Generated`; newer JDKs do not necessarily ship that annotation in standard modules as older JDKs did.

If compilation fails on a missing annotation:

- Check the exact import in the generated source.
- Identify the generator version in use.
- Add the corresponding annotation dependency if required by the generator and suitable for the application.
- Or upgrade the generator as planned to emit code compatible with the current toolchain.

Do not mass-replace `javax` with `jakarta` in generated source via manual scripts. `javax.annotation` and `jakarta.annotation` are different packages; renaming does not guarantee annotation API compatibility.

Configure a uniform Java toolchain in the build so generator outputs and source compile on the same JDK baseline. Upgrading the JDK also requires checking plugins, annotation processors, and the Spring gRPC starter.

## 12. Upgrading Generated Code Safely

An upgrade should follow these steps:

1. **Capture baseline:** record the current schema, key generated source APIs, and dependency graph.
2. **Define scope:** is this changing `.proto`, compiler, gRPC plugin, runtime, or JDK?
3. **Check release notes/compatibility:** confirm generator/runtime and Spring starter support the target combination.
4. **Upgrade in controlled sync:** update versions in dependency management/build plugins rather than ad-hoc per-module edits.
5. **Regenerate:** produce message and service code from schemas using the new toolchain.
6. **Review source diff:** inspect packages, classes, accessors, stubs, annotations, and descriptors.
7. **Compile callers:** verify application source and dependent modules still compile and work.
8. **Run runtime tests:** instantiate generated messages, server, and client on the real classpath.
9. **Test wire compatibility:** verify old/new messages and clients/servers communicate per contract.
10. **Deploy via rollout:** keep servers/callers compatible during transition.

Avoid bundling multiple major upgrades at once if failures cannot be isolated. For example, upgrading JDK, Spring Boot, protoc, and schemas simultaneously makes diagnosing compatibility regressions much harder.

## 13. Compatibility Matrix to Test

### Client/Server Versions

| Client Generated Code | Server Generated Code | What to Verify |
|---|---|---|
| Old | Old | Baseline works |
| Old | New | Old requests parse and old semantics are preserved |
| New | New | New contract works |
| New | Old | New fields ignored or new methods return expected status |

This matrix verifies wire/service compatibility; runtime dependencies still need separate verification.

### Generated Code/Runtime

Do not assume every combination of old/new versions is supported. Build a matrix based on Protobuf Java and gRPC Java compatibility policies:

| Combination | How to Evaluate |
|---|---|
| Generated code and runtime from the same chosen release line | Standard combination for testing and release |
| Generated code newer than runtime | Do not use if runtime lacks APIs/versions required by generated code |
| Runtime newer than generated code | Use only if runtime compatibility policy permits; still must test |
| New gRPC plugin with old gRPC runtime | Inspect APIs referenced by generated service code |
| Generated code produced by a different compiler in CI | Unacceptable unless toolchain is pinned and verified |

With Protobuf Java, generated code may include runtime version checks. Let runtime checks and build policies catch mismatches; never disable or bypass checks just to make the app boot. The safe approach is using a verified compatible compiler/generator/runtime bundle.

## 14. Specific Tests

### Source Compatibility Test

Compile key caller modules against the new generated artifact. This test catches:

- Changed packages/classes.
- Changed accessors from renamed fields.
- Changed stub methods or signatures.
- `java_multiple_files`/outer class import changes.

If your organization publishes generated proto code as a separate library, maintain a small consumer fixture depending on that artifact to verify the real Java API.

### Descriptor Test

Verify full method names and message types:

```java
var descriptor = CatalogServiceGrpc.getServiceDescriptor();
var method = descriptor.getMethods().stream()
        .filter(candidate ->
                candidate.getBareMethodName().equals("Search"))
        .findFirst()
        .orElseThrow();

assertEquals(
        "catalog.v1.CatalogService/Search",
        method.getFullMethodName());
```

This example iterates methods in gRPC Java's `ServiceDescriptor` and looks up by bare method name. What must be protected is the published full method path and request/response descriptors; specific descriptor APIs should match your project's gRPC Java version.

### Wire Test

Serialize messages with old generated code, parse with new code, and verify committed fields:

```java
byte[] oldBytes = oldRequest.toByteArray();
NewSearchRequest parsed = NewSearchRequest.parseFrom(oldBytes);

assertEquals("keyboard", parsed.getQuery());
```

Reverse-direction testing is also required when old servers must read messages sent by new clients. Unknown fields may be handled by the Protobuf runtime, yet do not assume old servers execute the semantics of new fields.

### Runtime Integration Test

Boot the Spring application context or test server with real dependencies:

- Service beans are registered.
- Generated stubs make calls successfully.
- Messages serialize/deserialize properly.
- Statuses and deadlines behave correctly.
- No `NoSuchMethodError`, `NoClassDefFoundError`, `LinkageError`, or runtime version errors occur on startup.

Unit tests on mappers cannot catch classpath or service registration failures.

## 15. Common Pitfalls

| Symptom | Cause | How to Fix |
|---|---|---|
| Missing `CatalogServiceGrpc` | Only ran Java Protobuf generator | Configure and run the gRPC Java plugin |
| Callers cannot find generated classes | Changed `java_package` or `java_multiple_files` | Keep Java options or run a planned import migration |
| `NoSuchMethodError` at runtime | Runtime dependency mismatches generated code or another library | Inspect dependency graph and align versions |
| Runtime version validation fails | Generated code and Protobuf runtime incompatible | Use a verified toolchain/runtime set |
| Developer machine and CI generate different code | Unpinned compiler/plugin | Lock versions and use a uniform build plugin |
| Compile fails missing `javax.annotation.Generated` | Generated code references annotation absent from classpath | Check generator and appropriate annotation dependency |
| Stub lacks new method | Client uses old generated artifact/schema | Upgrade proto artifact and regenerate client |
| Full method path changes unexpectedly | Changed Protobuf package/service/method | Keep old path or publish a versioned service |
| Huge generated diff | Changed generator or formatter | Review public API/runtime impact, not just line count |
| Runtime has multiple Protobuf versions | Transitive dependencies pull different versions | Use BOM/constraints and inspect `runtimeClasspath` |

## 16. Hands-On Exercise

**Scenario:** A Spring gRPC module publishes a `catalog-proto` library for multiple client services. The team wants to add `page_size` to `SearchRequest` while upgrading Protobuf and gRPC Java toolchain versions. Some services still build against the old generated artifact.

Perform the following:

1. Record the current `package`, `java_package`, `java_multiple_files`, `java_outer_classname`, full method path, and generated API.
2. Select `protoc`, `protoc-gen-grpc-java`, `protobuf-java`, `grpc-*`, and Spring gRPC starter versions from a verified compatible set.
3. Pin versions in the build; avoid dynamic/latest versions.
4. Add `optional int32 page_size` with an unused tag; keep existing fields and Java options unchanged.
5. Regenerate message/service code via the build tool; never manually edit generated source.
6. Inspect the dependency graph to avoid multiple runtime versions.
7. Compile a consumer fixture using both old and new generated APIs; document source changes requiring migration.
8. Run descriptor, wire, and Spring gRPC integration tests.
9. Test old client/new server and new client/old server; verify defaults and unknown-field behavior.
10. Publish the new artifact only after CI reproduces code generation and runtime tests pass.

**Completion criteria:** toolchain is pinned; generated code is reproducible; source API changes are identified; runtime dependencies are compatible; full method paths remain intact; old/new client-server pairs have verified behavior.

## 17. Key Takeaways

Generated code is part of the Java API that applications actually compile and run. `protoc` generates Protobuf messages; `protoc-gen-grpc-java` generates services, stubs, and base classes. Keep `java_package`, `java_multiple_files`, `java_outer_classname`, and field names stable when source compatibility is required; distinguish these Java options from the Protobuf `package` that defines the full method path. Pin compilers/plugins/runtimes, align gRPC artifacts, avoid duplicate runtime versions on the classpath, and generate code via a reproducible build workflow. Verify source, descriptor, wire, and runtime integration before releasing; wire compatibility alone does not prove generated code compatibility.
