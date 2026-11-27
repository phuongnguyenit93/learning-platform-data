# Proto Paths and Import Paths in Spring gRPC

In a **Spring gRPC** project, a `.proto` file can import messages, enums, or services declared in other files. For `protoc` to locate those files properly, the build must provide accurate **proto source roots** and **import paths**. Incorrect import paths halt code generation before the Java compiler even runs; overlapping roots can also cause the same schema to be resolved under different logical paths.

This lesson focuses on organizing proto paths, writing `import` statements, supplying shared schemas, and verifying them across CLI, Gradle, and Maven. The focus is on **which files `protoc` looks for and from where**.

## 1. Proto Source Roots and Import Paths

A **proto source root** is the root directory from which paths in `import` statements are resolved. Given this layout:

```text
src/main/proto/
├── common/
│   └── v1/
│       └── money.proto
└── orders/
    └── v1/
        └── order.proto
```

If `order.proto` needs the currency type from `money.proto`, declare:

```proto
syntax = "proto3";

package learning.orders.v1;

import "common/v1/money.proto";

message Order {
  string order_id = 1;
  learning.common.v1.Money total = 2;
}
```

The import path `common/v1/money.proto` is resolved **from the proto source root**, which is `src/main/proto` in this example. It is not resolved relative to the directory containing `order.proto`. Therefore, do not write `import "../common/v1/money.proto"` out of relative-import habits from other languages.

| Concept | Meaning |
| --- | --- |
| Proto source root | Directory passed via `-I` or `--proto_path` |
| Import path | Logical path inside the root, written in the `import` string |
| Input file path | The `.proto` file passed to `protoc` to compile |
| Protobuf package | Namespace of messages/services in the contract |
| Java package | Package of generated Java classes, usually set by `java_package` |

## 2. Selecting Import Roots with protoc

From the project root directory, an illustrative command:

```bash
protoc \
  -I=src/main/proto \
  --java_out=build/generated/java \
  orders/v1/order.proto
```

`-I` is shorthand for `--proto_path`. When `protoc` processes `orders/v1/order.proto`, it interprets the file name relative to the provided root. When it encounters `import "common/v1/money.proto"`, it looks for `common/v1/money.proto` under that root.

If a schema uses files from another directory, pass multiple roots:

```bash
protoc \
  -I=src/main/proto \
  -I=third_party/proto \
  --java_out=build/generated/java \
  orders/v1/order.proto
```

If the additional file lives at `third_party/proto/google/type/date.proto`, the import is:

```proto
import "google/type/date.proto";
```

The path in `import` must be relative to a declared root. Never embed absolute paths from a developer's machine in schemas; use stable logical paths so every machine and CI runner resolves the same contract.

### Why Choose a Common Root?

If all protos live under `src/main/proto`, a single `-I` suffices. You do not need to add subdirectories `common/v1` and `orders/v1` individually. If you pass `-I=src/main/proto/orders/v1`, the file may be identified as `order.proto` instead of `orders/v1/order.proto`; standard import paths will then fail to match.

Choose a stable common root for the entire schema tree. Input files and `import` statements should be expressed consistently relative to that root.

## 3. Proto Path Differs from Protobuf Package and Java Package

These three concepts are independent:

| Declaration | Example | Used For |
| --- | --- | --- |
| File path | `common/v1/money.proto` | Schema location in the repository |
| Protobuf package | `learning.common.v1` | Namespace for messages/services and full RPC names |
| Java package | `vn.example.shared.money.v1` | Package of the generated Java code |

Example contents of `money.proto`:

```proto
syntax = "proto3";

package learning.common.v1;

option java_package = "vn.example.shared.money.v1";
option java_multiple_files = true;

message Money {
  string currency_code = 1;
  int64 units = 2;
  int32 nanos = 3;
}
```

Even though the file is at `common/v1/money.proto`, the protobuf package is `learning.common.v1` and the Java package is `vn.example.shared.money.v1`. In a consumer schema, import by path from the root and reference the type by protobuf namespace:

```proto
import "common/v1/money.proto";

message Order {
  learning.common.v1.Money total = 1;
}
```

Do not write `vn.example.shared.money.v1.Money` inside `.proto`; that is the Java name produced after code generation. Changing the proto root does not automatically change the Java package or RPC name; changing the protobuf `package`, service, or method name can change the RPC path even if the file remains in the same place.

## 4. Organizing Shared Schemas

For Spring gRPC services, organize schemas by domain and version:

```text
src/main/proto/
├── common/v1/
│   ├── money.proto
│   └── pagination.proto
├── orders/v1/
│   └── order.proto
└── inventory/v1/
    └── stock.proto
```

Consumers import using logical paths from the root:

- `orders/v1/order.proto` imports `common/v1/money.proto`.
- `inventory/v1/stock.proto` imports `common/v1/pagination.proto`.
- Domains share a single `Money` definition instead of maintaining similar copies.

When multiple modules share a schema, place it in a dedicated directory or contract artifact and add it to each module's import path. Avoid copying the same proto file into multiple places; copies tend to drift and leave clients and servers using different schemas.

### Proto Dependencies Differ from Java Dependencies

A shared proto library must supply **`.proto` files with stable internal paths**. Having only a generated Java JAR is generally not enough for `protoc` to resolve `import` statements, unless the artifact also packages proto resources or the build provides an include mechanism.

Example directory outside the main source root:

```text
third_party/proto/
└── acme/
    └── identity/v1/
        └── identity.proto
```

A consumer schema writes:

```proto
import "acme/identity/v1/identity.proto";
```

The CLI needs `-I=third_party/proto`. With Gradle/Maven, configure include paths or proto dependencies per the plugin in use. If generated code references Java classes from that dependency, the application must also declare the corresponding Java artifact on the compile classpath. **Supplying proto sources and supplying Java classes are two separate tasks.**

## 5. Well-Known Types and External Schemas

Protocol Buffers includes standard schemas such as:

- `google/protobuf/timestamp.proto`
- `google/protobuf/duration.proto`
- `google/protobuf/empty.proto`
- `google/protobuf/struct.proto`

Example:

```proto
syntax = "proto3";

package learning.orders.v1;

import "google/protobuf/timestamp.proto";

message OrderEvent {
  string order_id = 1;
  google.protobuf.Timestamp occurred_at = 2;
}
```

Well-known types are normally bundled with `protoc` distributions and supported by the protobuf Java runtime. If `protoc` reports that `google/protobuf/timestamp.proto` cannot be found, check the binary's include files and the import roots supplied by your build plugin; do not create a dummy schema to work around the error.

Schemas such as Google API annotations or external library protos may not be in the default includes. Fetch the dependency containing the source protos and add the proper root to the import path. Adding a Java artifact to `implementation` does not automatically place its proto files on `protoc`'s include path.

## 6. Configuring Proto Roots and Dependencies in Gradle

With the protobuf Gradle plugin, the default main proto source is `src/main/proto`. To add another schema directory:

```groovy
sourceSets {
    main {
        proto {
            srcDir 'src/shared-proto'
        }
    }
}
```

This adds `src/shared-proto` to `main`'s proto sources. Import paths are resolved from the roots passed to `protoc` by the plugin; import strings must match the directory structure inside those roots.

If a proto library packages `.proto` files inside a JAR, the protobuf Gradle plugin supports the `protobuf` configuration to supply proto files for generation:

```groovy
dependencies {
    // JAR must contain proto resources under the agreed import paths.
    protobuf files('libs/shared-protos.jar')

    // If generated Java requires classes from this library,
    // declare the Java artifact on the compile classpath.
    implementation files('libs/shared-protos-java.jar')
}
```

These two configurations have different meanings:

- `protobuf` supplies source schemas so `protoc` can resolve imports.
- `implementation` supplies compiled classes/libraries for the Java compiler and runtime.

Not every Java JAR contains proto files. Verify the artifact's contents and internal paths before adding the dependency. When using custom source sets, attach proto roots and dependency scopes to the right source set; do not put test-only schemas into `main` just to make imports work.

Verify with the actual tasks:

```bash
./gradlew generateProto
./gradlew compileJava
```

If the CLI works while Gradle fails, inspect the proto source directories and dependencies passed to the generation task; do not assume Gradle automatically uses every `-I` flag you passed in a manual `protoc` run.

## 7. Configuring Additional Proto Roots in Maven

With `protobuf-maven-plugin`, the default proto source root is usually `src/main/proto`. When additional include directories exist, you can configure the plugin to add proto paths. Illustrative example for plugin versions supporting `additionalProtoPathElements`:

```xml
<configuration>
    <protoSourceRoot>
        ${project.basedir}/src/main/proto
    </protoSourceRoot>
    <additionalProtoPathElements>
        <additionalProtoPathElement>
            ${project.basedir}/third_party/proto
        </additionalProtoPathElement>
    </additionalProtoPathElements>
    <protocArtifact>
        com.google.protobuf:protoc:4.30.2:exe:${os.detected.classifier}
    </protocArtifact>
    <pluginId>grpc-java</pluginId>
    <pluginArtifact>
        io.grpc:protoc-gen-grpc-java:1.71.0:exe:${os.detected.classifier}
    </pluginArtifact>
</configuration>
```

Verify include parameters against your project's `protobuf-maven-plugin` version. If your plugin version does not support that configuration, use the include/dependency mechanism provided by that version; do not add unrecognized XML elements.

Run generation and compilation:

```bash
mvn generate-sources
mvn compile
```

If an import is not found, inspect the `protoc` command logged by the Maven plugin to verify the actual roots, working directory, proto source root, and additional directories.

## 8. Testing Import Paths via CLI

A quick way to isolate path errors from Spring errors is running `protoc` directly. Given:

```text
src/main/proto/
├── common/v1/money.proto
└── orders/v1/order.proto
```

Run from the project root:

```bash
protoc \
  -I=src/main/proto \
  --descriptor_set_out=build/order-descriptor.pb \
  --include_imports \
  orders/v1/order.proto
```

If the command succeeds, `protoc` found the input file and all referenced imports. `--include_imports` embeds imported descriptors into the descriptor set, which is useful for verifying the import graph. This step does not generate Java code, invoke the gRPC plugin, or test runtime behavior.

To test Java and gRPC plugin generation:

```bash
protoc \
  -I=src/main/proto \
  --java_out=build/generated/java \
  --plugin=protoc-gen-grpc-java=/path/to/protoc-gen-grpc-java \
  --grpc-java_out=build/generated/grpc \
  orders/v1/order.proto
```

If the plugin is on `PATH` under its standard name, `--plugin` can be omitted. In real projects, let Gradle/Maven manage binaries rather than hardcoding personal machine paths.

## 9. Common Import Path Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `File does not reside within any path specified using --proto_path` | Input file does not lie under a proto root | Add the right `-I` or pass an input path relative to the root |
| `Import "common/v1/money.proto" was not found` | Root does not contain that logical path | Check directory structure and the import string |
| `Import "google/protobuf/timestamp.proto" was not found` | Missing well-known type include or incomplete protoc distribution | Check the protoc artifact and include files |
| CLI works, but Gradle/Maven fails | Build plugin does not pass the same include roots | Check source roots, dependencies, and logged `protoc` command |
| Works for developer, fails on CI | Import relies on external files outside repo or local paths | Move proto dependencies into the repository or managed artifacts |
| Works on Windows, fails on Linux CI | Case mismatch in file or directory names | Ensure import paths match exact file casing |
| One proto resolved under two logical names | Overlapping roots or importing the same file via two paths | Standardize on a canonical import path |
| Java package is right, but proto import fails | Confusing `java_package` with proto include path | Check `-I` and the `import` string |

### Canonical Import Paths

A schema should be imported through **one consistent logical path**. If the file resides at `src/main/proto/common/v1/money.proto`, every consumer should use `common/v1/money.proto`. Do not add another root at `src/main/proto/common` and import the same file as `v1/money.proto` elsewhere.

Overlapping roots and a single file appearing under different logical names make descriptors hard to track and can cause duplicate definitions or differences between developer machines and CI. Use a common root, avoid shadowing import names, and never maintain multiple copies of a schema.

## 10. Practical Verification Workflow

When adding a new import to a Spring gRPC service:

1. Place the dependency file under the agreed proto root, e.g., `src/main/proto/common/v1/money.proto`.
2. In the consumer schema, write `import "common/v1/money.proto";`.
3. Run `protoc` with `-I` pointing to the root and export a descriptor set with `--include_imports`.
4. Run Gradle `generateProto` or Maven `generate-sources` to confirm the build plugin passes the right include paths.
5. Run Java compilation to confirm both generated classes and Java dependencies are present.
6. Run an integration test calling an RPC that uses the imported message; verify success and business errors.
7. Run the same build on CI or a clean environment to ensure no reliance on local paths.

A small test confirming the imported generated message can be used:

```java
import org.junit.jupiter.api.Test;
import vn.example.shared.money.v1.Money;
import vn.example.springgrpc.orders.v1.Order;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderProtoImportTest {

    @Test
    void importedMessageCanBeUsed() {
        Money money = Money.newBuilder()
                .setCurrencyCode("VND")
                .setUnits(125_000)
                .build();

        Order order = Order.newBuilder()
                .setOrderId("ORD-100")
                .setTotal(money)
                .build();

        assertEquals("VND",
                order.getTotal().getCurrencyCode());
    }
}
```

The example assumes `Money` and `Order` were generated from two protos with their respective `java_package` options. The test verifies that the generated Java types see each other on the compile/test classpath; it **does not** replace verifying `protoc` import paths. To verify import paths, you must run generation from the actual schemas and build plugin.

## 11. Self-Check Practice

1. Create `common/v1/money.proto` and `orders/v1/order.proto` under `src/main/proto`. Import `Money` from `Order` using a path resolved from the root.
2. Run `protoc` without passing `-I=src/main/proto`. Read the error and explain why the input/import cannot be resolved.
3. Add `-I=third_party/proto` and import an extra file in that directory. Verify the import path starts from the new root.
4. Keep the protobuf package unchanged while changing `java_package`. Observe that Java imports change while the protobuf import path stays the same.
5. Configure Gradle `sourceSets.main.proto.srcDir` to add a secondary root, then run `generateProto`.
6. Package proto resources inside a JAR and provide them via Gradle's `protobuf` configuration. Distinguish a schema dependency from a generated Java classes dependency.
7. Configure an additional include root in Maven per your plugin version; verify the `protoc` log includes the required root.
8. Create two different logical paths pointing to the same schema via overlapping roots. Identify the problem and standardize on a canonical import path.
9. Run generation on Windows and Linux CI to catch case-sensitivity mismatches.
10. Write a test using an imported message and an integration test calling an RPC that takes that message; distinguish what each test verifies.

### Key Takeaway

**Import paths are resolved relative to proto source roots—not from the Java package, and not by default relative to the importing file's directory.** Use `-I`/`--proto_path` in `protoc`, declare proto roots/dependencies in the right source set in Gradle, or configure include roots in Maven. Standardize on canonical import paths, manage versioned schema dependencies, and verify code generation in a clean environment so Spring gRPC clients and servers always share the exact same contract.
