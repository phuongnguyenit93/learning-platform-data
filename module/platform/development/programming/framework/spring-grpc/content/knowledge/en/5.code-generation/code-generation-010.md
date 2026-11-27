# Never Hand-Edit Generated Code in Spring gRPC

In **Spring gRPC**, classes such as `OrderRequest`, `OrderReply`, and `OrderServiceGrpc` are typically created from a Protocol Buffers contract using `protoc` and the gRPC Java plugin. These files are **generated sources**: they reflect the schema and generator version at build time. Because of this, directly editing generated Java code is not a safe way to extend an application. The next code generation run can overwrite your changes, or if the changes linger unintentionally, client and server may end up using different versions of the API.

The working rule is: **edit the source that produces the code, or extend in the application layer; never patch generator outputs directly**. In gRPC Java, the source that produces message and service APIs is the `.proto` file and generator configuration. Business logic belongs in service implementations, client facades, mappers, validators, and interceptors managed by the application.

This lesson focuses on why you should not hand-edit generated code, how to locate the right place to make changes, how to handle cases where a generator lacks a needed capability, and how to verify after regeneration.

## 1. Why Not Edit Generated Java Directly?

Suppose `StockReply.java` is generated from:

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

A developer opens `build/generated/source/proto/main/java/vn/example/stock/v1/StockReply.java` and adds a method:

```java
// Do not do this: this is a generated source.
public boolean isOutOfStock() {
    return getAvailable() == 0;
}
```

The change may work temporarily, but as soon as `generateProto` runs again, the generator recreates `StockReply.java` from `stock.proto` and the added method disappears. If the build skips generation because outputs look up-to-date, the manual edit may linger on one developer's machine while never appearing on CI or teammates' machines.

| Risk | Consequence |
| --- | --- |
| Generation overwrites the file | Manually added logic is lost |
| Local machine keeps patched file, CI regenerates | "Works on my machine"; builds or tests diverge |
| Committing edited generated files | Hard to separate schema changes from manual edits |
| Upgrading the generator | Patches no longer apply or conflict with new output |
| Editing only one side (client or server) | Sides may compile against different APIs |
| Embedding business logic in message classes | Generated model gets coupled to one application's rules |

Generated sources are meant to be recreated. Treat them as **regenerable build outputs**, similar to compiled artifacts, even though you can read them to inspect the generated API.

## 2. Identify the Right Source to Edit

Before opening a generated file to make a change, identify your actual goal:

| What You Want to Change | Where to Edit |
| --- | --- |
| Add, remove, or change a message field | The `.proto` file |
| Change RPC type or service/method name | The `service`/`rpc` block in `.proto` |
| Change Java package, outer class, or multiple-files layout | `option java_*` directives in the schema |
| Change request handling logic | Server implementation class extending the generated server base |
| Add business validation | Validator or application service |
| Convert protobuf messages to domain models | Application-written mapper/adapter |
| Add headers, tokens, trace IDs | Client/server interceptors or call credentials |
| Adapt stub invocation to internal APIs | Client facade/wrapper |
| Change formatting or structure of generated code | Generator configuration or a custom codegen plugin |

For example, to add a `warehouse_id` field to the response, edit the schema:

```proto
message StockReply {
  string sku = 1;
  int64 available = 2;
  int64 version = 3;
  string warehouse_id = 4;
}
```

Then run generation and update application code to use the new field. Do not add `getWarehouseId()` directly into `StockReply.java`, because that API must be generated from the schema.

When modifying published fields, still follow Protocol Buffers compatibility rules: do not reuse removed field numbers; consider `reserved`; evaluate data type and field presence impacts. "Editing the right `.proto` file" does not automatically mean every schema change is safe for older clients.

## 3. Generated Messages Are Data; Business Logic Belongs in the Application Layer

Protobuf message classes are optimized for data representation, builders, parsing, and serialization. They should not become the home for a service's business rules.

For instance, instead of adding `isOutOfStock()` to the generated class, create a policy or mapper in application source code:

```java
package vn.example.stock;

import vn.example.stock.v1.StockReply;

public final class StockPolicy {
    private StockPolicy() {}

    public static boolean isOutOfStock(StockReply reply) {
        return reply.getAvailable() <= 0;
    }
}
```

Usage:

```java
if (StockPolicy.isOutOfStock(reply)) {
    // Apply the application's business rule.
}
```

This brings a key benefit: the same generated message can be shared by multiple clients without dragging along one application's rules. The policy can also be unit-tested independently of code generation.

If the application has its own domain model, avoid letting protobuf messages leak throughout the domain just because the classes already exist. Use a mapper at the RPC boundary:

```java
public record Stock(String sku, long available) {}

public final class StockMapper {
    private StockMapper() {}

    public static Stock toDomain(StockReply reply) {
        return new Stock(reply.getSku(), reply.getAvailable());
    }
}
```

`StockReply` is the wire transport type; `Stock` is the application-owned domain type. If the schema changes, the mapper gives you a single centralized place to adapt rather than editing scattered callers.

## 4. Extending the Server via the Generated Server Base

The gRPC Java plugin generates a server base class, such as `StockServiceGrpc.StockServiceImplBase`. This is the **designed extension point**: the application subclasses it and overrides the RPCs to implement.

```java
package vn.example.stock;

import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.stereotype.Service;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockRequest;
import vn.example.stock.v1.StockServiceGrpc;

@Service
public class StockServiceImpl
        extends StockServiceGrpc.StockServiceImplBase {

    private final StockApplicationService applicationService;

    public StockServiceImpl(StockApplicationService applicationService) {
        this.applicationService = applicationService;
    }

    @Override
    public void getStock(
            StockRequest request,
            StreamObserver<StockReply> observer) {

        if (request.getSku().isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("sku must not be blank")
                    .asRuntimeException());
            return;
        }

        StockReply reply = applicationService.findStock(request.getSku());
        observer.onNext(reply);
        observer.onCompleted();
    }
}
```

`StockServiceImpl` is owned by the development team; `StockServiceImplBase` is generated code. When the generator runs again, the implementation class remains intact because it lives in `src/main/java`.

In Spring gRPC, how service beans are registered depends on the integration starter/version. Use the `BindableService` registration mechanism supported by your project. Never add registration code or business logic to generated `*Grpc.java` files.

## 5. Extending the Client via a Facade Instead of Editing Stubs

Generated client stubs provide the gRPC communication API. The application can wrap a stub in a facade to centralize default deadlines, error mapping, and type conversion:

```java
package vn.example.stock;

import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.concurrent.TimeUnit;
import vn.example.stock.v1.StockReply;
import vn.example.stock.v1.StockRequest;
import vn.example.stock.v1.StockServiceGrpc;

public class StockGateway {
    private final StockServiceGrpc.StockServiceBlockingStub stub;

    public StockGateway(StockServiceGrpc.StockServiceBlockingStub stub) {
        this.stub = stub;
    }

    public Stock find(String sku) {
        try {
            StockReply reply = stub
                    .withDeadlineAfter(2, TimeUnit.SECONDS)
                    .getStock(StockRequest.newBuilder()
                            .setSku(sku)
                            .build());

            return StockMapper.toDomain(reply);
        } catch (StatusRuntimeException error) {
            if (error.getStatus().getCode() == Status.Code.NOT_FOUND) {
                return null;
            }
            throw error;
        }
    }
}
```

The facade is application code and can be modified and tested independently. The stub remains a generated API backed by a channel managed by Spring or grpc-java configuration.

Do not try to subclass generated messages just to add helper methods. Generated messages follow an immutable pattern and are not designed as base classes for business extensions. Using a facade, mapper, or utility provides a much cleaner boundary.

## 6. What If You Want to Change How Generated Code Is Produced?

Sometimes a team genuinely needs non-default output, such as internal annotations, wrappers, or API documentation. In that case, the change must live inside the **code generation pipeline**:

1. Check generator options and settings already supported by the current plugin.
2. If custom behavior is required, consider writing or using an additional `protoc plugin`.
3. Have the plugin emit separate files or separate extensions with clear namespaces.
4. Put the plugin, version, and options in the build tool so every machine runs the same pipeline.
5. Test outputs from a clean state and verify generated sources do not depend on workspace state.

As a matter of principle: a custom plugin might generate `StockReplyMapper.java` or `StockValidationMetadata.java` from descriptors, while `StockReply.java` continues to be produced by the Java protobuf generator. Separating outputs by responsibility prevents two generators from writing to the same file.

Never edit generator templates or binaries inside the Gradle/Maven cache or downloaded dependency directories. Such edits are untracked by source control, vanish whenever caches are cleared, and cannot be reproduced on CI. If an upstream generator fix is needed, upgrade to a fixed release or maintain a properly versioned fork/custom plugin.

## 7. When Generated Code Has Bugs or Missing Features

If generated output has an error, first identify its source:

- **Invalid schema:** fix `.proto` and regenerate.
- **Generator bug:** reproduce with a minimal schema, check generator version and issues/releases; upgrade or report upstream.
- **Missing generator feature:** find a suitable option/plugin or build a dedicated plugin.
- **Runtime incompatibility:** align `protoc`, `protoc-gen-grpc-java`, and protobuf/grpc-java runtime versions.
- **Application needs helpers/validation:** write them in the application layer, not in generated classes.

In an emergency, an automated post-processing patch on generated output might be considered as a temporary measure, provided it is automated, version-controlled, executed deterministically after generation, and covered by tests. Manual patches inside output directories are never deliverable solutions.

If the bug truly resides in generated code, build a minimal reproducing schema and record:
- Exact versions of `protoc` and the gRPC plugin.
- Options and import roots.
- Relevant generated output.
- Exact compile or runtime error.
- Results when testing another generator version.

This information separates generator bugs from schema mistakes, dependency conflicts, or API misuse.

## 8. Safe Regeneration Workflow After Schema Changes

After editing `.proto`, run a repeatable verification cycle:

1. Review schema changes: field numbers, data types, presence, RPC names, and compatibility.
2. Run generation from the version-pinned build tool.
3. Inspect the generated source diff to confirm changes match the schema.
4. Compile both `main` and `test` source sets.
5. Update server implementations, client facades, mappers, and validators if APIs changed.
6. Run unit tests and integration tests calling a real or in-process RPC.
7. Verify client/server version compatibility if the two sides deploy independently.

Gradle example:

```bash
./gradlew clean generateProto compileJava compileTestJava test
```

Maven example:

```bash
mvn clean generate-sources compile test
```

These commands assume the project already configures the protobuf plugin, gRPC plugin, and test lifecycle properly. Never commit generated outputs in a project that follows build-time generation; if an organization ships a contract JAR containing generated classes, produce that artifact from a standard pipeline.

## 9. Testing to Catch Lost Manual Edits

A useful check is verifying that extension logic resides in application code and keeps working after generated code is recreated.

Example unit test for the policy:

```java
import org.junit.jupiter.api.Test;
import vn.example.stock.StockPolicy;
import vn.example.stock.v1.StockReply;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StockPolicyTest {

    @Test
    void determinesWhetherStockIsEmpty() {
        StockReply empty = StockReply.newBuilder()
                .setSku("BOOK-101")
                .setAvailable(0)
                .build();

        StockReply available = StockReply.newBuilder()
                .setSku("BOOK-101")
                .setAvailable(4)
                .build();

        assertTrue(StockPolicy.isOutOfStock(empty));
        assertFalse(StockPolicy.isOutOfStock(available));
    }
}
```

Then run clean generation and tests:

```bash
./gradlew clean generateProto test
```

If the policy still compiles and tests pass, the logic lives in application-managed sources and does not rely on patches in generated output.

For server implementations, integration tests should invoke the generated stub to verify method binding and status handling:

```java
@Test
void blankSkuReturnsInvalidArgument() {
    var error = org.junit.jupiter.api.Assertions.assertThrows(
            io.grpc.StatusRuntimeException.class,
            () -> blockingStub.getStock(
                    StockRequest.newBuilder().setSku("").build()));

    org.junit.jupiter.api.Assertions.assertEquals(
            io.grpc.Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());
}
```

This test assumes `blockingStub` is wired to a test server and `StockServiceImpl` returns `INVALID_ARGUMENT` for blank SKUs as shown earlier. It tests RPC behavior; separate generation checks are still needed to confirm sources regenerate cleanly from `.proto`.

## 10. Signs That Generated Code Was Hand-Edited

| Sign | What to Check |
| --- | --- |
| Generated file contains business logic or repository calls | Logic was mistakenly placed inside a generated class |
| Diff in generated file does not correspond to schema/toolchain changes | Manual edit occurred or output came from another generator |
| Helper method disappears after `clean generateProto` | Helper was added directly to generated source |
| Machine A has a method that CI lacks | Local generated output was not regenerated from source |
| Upgrading plugin wipes out custom code | Patch was sitting inside generator-overwritten output |
| Client and server use generated JARs from different versions | Contract artifact or dependencies are out of sync |

When spotted, compare the generated output against a clean regeneration. Move business logic into application-managed sources; move API changes into `.proto`; move structural changes to generated output into configuration/plugins. Never keep an old manual patch just because the build happens to pass.

## 11. Hands-On Practice

1. Add a helper method directly to generated `StockReply.java` in a practice copy of the project. Run `clean generateProto` and observe the helper disappear.
2. Move that helper to `StockPolicy` in `src/main/java`; write a unit test and re-run after generation.
3. Add a new field to `stock.proto`, regenerate, and verify the generated API updates; update the mapper without editing any generated file.
4. Write a `StockServiceImpl` extending `StockServiceImplBase` and overriding the unary RPC. Verify the implementation is unaffected when generation reruns.
5. Create `StockGateway` wrapping the generated stub, applying a deadline and translating statuses; test the facade independently.
6. Simulate a compile error due to a runtime version mismatch; determine whether the fault is in the generator or dependency setup without patching generated source.
7. If auto-generated helpers are truly needed, design a plugin that emits a separate `StockReplyMapper.java` file and confirm the two generators do not overwrite each other's outputs.
8. Run clean generation twice and compare generated directories; confirm every change traces back to the schema or toolchain.

### Key Takeaway

**Generated sources are outputs of the contract and generator, not a place to store application logic.** To change messages or RPCs, edit `.proto`; to change business behavior, write service implementations, mappers, validators, or client facades; to change generation behavior, configure the generator or build a versioned plugin. After every change, regenerate from a clean build, inspect diffs, compile, and run tests. This discipline keeps Spring gRPC clients and servers consistent and prevents patches from disappearing on rebuild.
