# Differences in Generated APIs Across Versions in Spring gRPC

In **Spring gRPC**, the exact same Protocol Buffers contract can produce different Java APIs when the schema, codegen options, or `protoc`/`protoc-gen-grpc-java` versions change. Differences may be limited to annotations and source formatting, or they may prevent client/server code from compiling, break old bytecode linkage, or cause RPCs to target the wrong endpoint.

To upgrade safely, distinguish the **generated Java API**, the **protobuf/gRPC wire contract**, and the **execution runtime**. This lesson focuses on identifying generated API differences across versions, evaluating compatibility impact, and testing migrations prior to release.

## 1. Where Do Generated API Changes Come From?

The generated API does not depend solely on message fields. It is produced by a combination of:

- `.proto` schema: package, messages, fields, enums, services, RPCs, and streaming modes.
- Java options: `java_package`, `java_multiple_files`, `java_outer_classname`.
- Generator: `protoc` version and Java generator options.
- gRPC plugin: `protoc-gen-grpc-java` version and plugin configuration.
- Runtime dependencies: `protobuf-java`, `grpc-api`, `grpc-stub`, `grpc-protobuf`, and transport.
- Build configuration: proto roots, import graph, source sets, and dependency resolution.

Two scenarios must be separated:

1. **Schema unchanged, generator changed:** Java output can change because the generator updated APIs, annotations, imports, or implementation details.
2. **Schema changed, generator unchanged:** output changed because the contract changed; this is typically an intentional API change.

When both schema and generator change in a single upgrade, it becomes very hard to tell which diff came from which cause. Establish a baseline and isolate each group of changes whenever possible.

## 2. Four Compatibility Layers to Evaluate

| Layer | Question | Example Failure |
| --- | --- | --- |
| **Source compatibility** | Does existing client/server source still compile against the new generated API? | Getter or stub method signature changed |
| **Binary compatibility** | Does already-compiled bytecode still run against the new generated JAR? | `NoSuchMethodError`, `NoClassDefFoundError` |
| **Wire compatibility** | Do clients and servers of different versions decode and invoke RPCs properly over gRPC? | RPC path changed, field number/type incompatible |
| **Behavioral compatibility** | Do data semantics and RPC behavior remain the same? | Default values or presence altered handling logic |

A change can be compatible at one layer while breaking another. For instance, changing `java_package` can preserve the protobuf wire format while breaking Java source imports of the old package. Conversely, keeping Java class names identical while changing the protobuf service package can make clients call the wrong RPC path.

**Passing compilation does not prove wire compatibility; wire compatibility does not guarantee behavioral compatibility.**

## 3. Differences in Generated Message APIs

Consider this schema:

```proto
syntax = "proto3";

package learning.stock.v1;

option java_package = "vn.example.stock.v1";
option java_multiple_files = true;

message StockReply {
  string sku = 1;
  int64 available = 2;
}
```

With these options, the Java generator creates a standalone message class. Typical API:

```java
StockReply reply = StockReply.newBuilder()
        .setSku("BOOK-101")
        .setAvailable(12)
        .build();

String sku = reply.getSku();
long available = reply.getAvailable();
StockReply.Builder builder = StockReply.newBuilder();
```

Generated classes also include parsers, serialization, descriptors, and builder helper interfaces. This API is owned by the generator; applications should only call the generated public methods.

### 3.1. Java Package and File Splitting

Changing `java_package`:

```proto
option java_package = "vn.example.inventory.v1";
```

changes the Java package of generated types. Source code importing the old `vn.example.stock.v1.StockReply` must be updated, even though protobuf package and field numbers may remain unchanged.

Changing `java_multiple_files` from `true` to `false` turns messages into nested types inside the outer class. For instance, Java references shift from `StockReply` to `StockProto.StockReply`. This affects source/binary APIs, even though messages on the wire use the exact same schema.

`java_outer_classname` sets the name of the outer class holding descriptors and nested types when applicable. Changing this option can break imports or direct references to the outer class.

### 3.2. Field Names, Types, and Presence

Proto field names are converted to camelCase Java accessors:

| Proto Declaration | Typical Java API |
| --- | --- |
| `string sku = 1;` | `getSku()`, `setSku(...)` |
| `int64 available = 2;` | `getAvailable()`, `setAvailable(...)` |
| `repeated string tags = 3;` | `getTagsList()`, `addTags(...)` |
| `map<string, int64> quantities = 4;` | `getQuantitiesMap()`, corresponding builder methods |

Renaming a field while keeping the same field number usually preserves protobuf binary wire decoding, yet **Java accessors change names** and code calling the old getter fails to compile. Field names also affect JSON field names and reflection-based tools.

Changing a field's type or field number can alter the wire format. Never treat successful compilation of generated Java as proof that a change is safe for already-released clients.

Regular proto3 scalar fields have default values and do not always expose presence accessors like message fields do. Declaring `optional` on a scalar adds `hasX()` to distinguish "omitted" from "explicitly set to the default value":

```proto
message UpdateStockRequest {
  optional int64 reorder_point = 1;
}
```

`hasReorderPoint()` and `getReorderPoint()` have distinct semantics: the getter returns the default value when absent; the presence method indicates whether the field was set. Changing presence semantics requires reviewing application logic, not just Java signatures.

### 3.3. Enums and Oneof

Generated enums typically include enum constants, numeric values, `forNumber`, and an unrecognized state depending on generator/runtime APIs. When adding enum values, older clients may receive unknown numeric values; code must handle unknown branches instead of assuming every value belongs to the known set.

`oneof` generates APIs to inspect which branch is active, such as `getPayloadCase()`, along with getters/setters per branch. Adding, removing, or changing fields inside a `oneof` can change the case enum and how applications read data. Review both generated APIs and semantics when fields are unset or a different branch is active.

## 4. Differences in Generated gRPC Service APIs

Consider this service:

```proto
service StockService {
  rpc GetStock(StockRequest) returns (StockReply);
  rpc WatchStock(StockRequest) returns (stream StockReply);
}
```

The gRPC Java plugin generates `StockServiceGrpc` containing the service descriptor, method descriptors, server base class, and client stub families. Typical shape:

```java
// Server extension point:
public static abstract class StockServiceImplBase
        implements io.grpc.BindableService {
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {
        // Default behavior typically returns UNIMPLEMENTED.
    }

    public void watchStock(
            StockRequest request,
            StreamObserver<StockReply> responseObserver) {
        // Server streaming.
    }
}

// Blocking client:
StockServiceGrpc.StockServiceBlockingStub blocking =
        StockServiceGrpc.newBlockingStub(channel);

// Async client:
StockServiceGrpc.StockServiceStub async =
        StockServiceGrpc.newStub(channel);
```

This illustrates the common grpc-java API shape; verify against the actual source generated by the plugin version you use. Do not assume every version has identical nested types, method modifiers, or helper APIs.

### 4.1. Cardinality Determines the RPC Signature

Changing an RPC's streaming cardinality changes the generated API:

| RPC Type | Typical Server Method | Typical Client API |
| --- | --- | --- |
| Unary | One request, observer for one response | Blocking returns one response; async takes response observer |
| Server streaming | One request, observer for multiple responses | Blocking returns iterator; async takes observer |
| Client streaming | Returns request observer to receive many requests, takes observer for final response | Async client sends multiple requests |
| Bidirectional streaming | Independent request observer and response observer | Async client sends/receives multiple messages |

For example, changing:

```proto
rpc Upload(UploadRequest) returns (UploadReply);
```

to:

```proto
rpc Upload(stream UploadRequest) returns (UploadReply);
```

is not just a one-word schema edit. The server method shifts from receiving a single `UploadRequest` to returning a `StreamObserver<UploadRequest>` to receive a stream of requests. The client must likewise switch from a unary call to a request stream. This changes both source APIs and RPC semantics; plan a migration for both sides.

### 4.2. Service and Method Names Affect the RPC Path

The full RPC name follows the pattern:

```text
/<protobuf-package>.<ServiceName>/<MethodName>
```

Changing the protobuf package, service name, or method name changes the method path that clients invoke. Changing `java_package` alone changes the Java package without changing the protobuf RPC path. Always evaluate the Java API and the wire endpoint separately.

## 5. Generator Versions Can Change APIs Even When the Schema Is Unchanged

When upgrading `protoc` or `protoc-gen-grpc-java`, generated output can change in:

- Annotations and imports added, removed, or changed.
- Signatures, visibility, or helper methods on generated classes.
- Descriptor and method handler implementations.
- Nested types or interfaces supporting server APIs.
- Deprecation warnings and new runtime API requirements.
- Formatting, comments, and version markers in generated sources.

Not every diff is a breaking change. A comment change may not affect Java APIs; a public method signature change can break compilation; a method descriptor change can affect dispatch. Classify changes based on **public API and behavior**, not diff line count.

Generator comparison workflow:

1. Keep all schemas and import dependencies unchanged.
2. Generate code with the current toolchain and save the baseline output.
3. Change only the generator version being evaluated.
4. Delete old generated outputs and regenerate.
5. Compare changed files; focus on public classes, constructors, methods, nested types, and descriptors.
6. Compile and run tests with the runtime recommended for the new generator.

If both schema and generator change, split them into two review passes so you know which source caused each change.

## 6. How to Review Generated API Diffs

First inspect the source diff:

```bash
git diff -- build/generated/source/proto
```

If generated sources are not committed, generate outputs into two separate temporary directories or use two worktrees/build checkouts with the same schema and different toolchains. Never overwrite the baseline before saving the old results.

Use `javap` to inspect the public API of compiled classes:

```bash
javap -classpath build/classes/java/main vn.example.stock.v1.StockReply
javap -classpath build/classes/java/main vn.example.stock.v1.StockServiceGrpc
```

`javap` shows the class/method signatures produced by the Java compiler. It helps when source diffs are huge, though it does not replace checking protobuf descriptors or wire compatibility.

For contract libraries published as JARs, you can use binary/source API comparison tools such as **Revapi** or **japicmp** to compare old and new artifacts. Configure the tool according to your project's policy; classify findings by impact and verify by compiling older clients.

## 7. Compatibility Testing When Upgrading Generated APIs

A solid test suite covers multiple layers:

### 7.1. Compile Old Clients Against the New Contract

If clients are built from source, try compiling an older client against the new contract JAR. Getter, package, stub, or method signature breaks surface at compile time.

This checks **source compatibility**, not old bytecode linkage or wire behavior.

### 7.2. Check Binary Compatibility

If clients are already compiled and distributed, verify linkage against the new JAR. Run an API comparison tool and execute a smoke test with older client bytecode on the new runtime classpath. Watch for errors like `NoSuchMethodError` and `NoClassDefFoundError`.

### 7.3. Check Wire Compatibility

Run old client versions against the new server, and new clients against the old server in a test environment. Verify:

- RPC paths and method types still match.
- Field numbers/types decode accurately.
- New fields, new enum values, and unknown fields are handled safely.
- Statuses and metadata preserve the contract.

### 7.4. Check Behavioral Compatibility

Test meaningful business cases: absent fields vs. default values, unknown enums, unset `oneof` branches, empty request streams, cancellation, and deadlines. Generated APIs may compile cleanly while new semantics still cause the application to behave incorrectly.

## 8. Safe Upgrade Workflow

When updating generated APIs in the **SPRING_GRPC** module, follow this sequence:

1. **Record the baseline:** schema versions, `protoc`, gRPC plugin, protobuf/grpc-java runtimes, and Spring starter.
2. **Classify the change:** schema change, generator-only change, or runtime change.
3. **Generate in isolation:** keep schemas unchanged while evaluating a generator; archive old and new generated outputs.
4. **Review the API:** packages, classes, public methods, RPC descriptors, method cardinality, and presence semantics.
5. **Compile consumers:** test existing clients/servers against the new contract.
6. **Verify wire compatibility:** run an old/new client vs. old/new server matrix if deployed independently.
7. **Run integration tests:** unary, streaming, statuses, metadata, deadlines, and TLS per application scope.
8. **Release with proper versioning:** contract JARs and server/client releases must carry clear versions, migration notes, and a compatibility plan.

Never upgrade a generator just because a newer version exists. Have a clear goal, review diffs, and run runtime tests before releasing.

## 9. Example Checklist for a Specific Change

Suppose `java_package` changes from `vn.example.stock.v1` to `vn.example.inventory.v1` while protobuf package, service, method, and field numbers remain unchanged.

| Check | Expected Outcome |
| --- | --- |
| Java imports | Package imports in client/server sources must be updated |
| Generated class names | Relative message names stay the same, inside the new Java package |
| Protobuf field numbers/types | Unchanged |
| gRPC full method path | Unchanged if protobuf package/service/method stay unchanged |
| Binary compatibility | Risk of breaking if old Java classes are no longer supplied |
| Wire compatibility | Usually preserved with unchanged protobuf binary/gRPC paths |
| Application behavior | Integration tests must run to verify mapping and runtime wiring |

This example shows how a change can be **breaking for Java consumers yet compatible at the wire level**. If the contract library is shared by multiple Java applications, you need a major version bump or a proper migration strategy even though servers and clients on the network can still talk to each other.

## 10. Hands-On Practice

1. Generate `StockReply` from the sample schema; record its package, getters, builders, and descriptors.
2. Change `java_package` while keeping the protobuf package; classify source, binary, and wire impacts.
3. Toggle `java_multiple_files`; observe how message references and outer classes change.
4. Rename a field while keeping its field number; check Java getters, JSON names, and wire decoding.
5. Add an `optional` scalar; inspect `hasX()` and how absent fields differ from default values.
6. Change a unary RPC to client-streaming; compare server base methods and client stub signatures.
7. Upgrade only `protoc-gen-grpc-java` with schemas untouched and review the public API diff.
8. Use `javap` or Revapi/japicmp to compare the contract JAR before and after the upgrade.
9. Build an older client against the new contract, then run two-version client/server integration tests.
10. Write migration notes specifying changes to source APIs, binary APIs, RPC paths, and wire semantics.

### Key Takeaway

**Generated API differences must be evaluated across Java source, bytecode binary, protobuf/gRPC wire contract, and runtime behavior.** Schema options can rename Java packages/classes without touching the wire; protobuf package/service/method or field numbers/types affect network communication; generator upgrades can change public APIs even when schemas stay fixed. Maintain a baseline, upgrade one layer at a time, review generated diffs, check descriptors, compile both old and new consumers, and run integration tests before releasing.
