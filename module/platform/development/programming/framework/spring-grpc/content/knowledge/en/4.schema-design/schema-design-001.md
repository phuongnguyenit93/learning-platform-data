# Proto Package Naming in Spring gRPC

When developing gRPC services with Spring, Protocol Buffers files (typically with the `.proto` extension) serve as the shared contract between client and server. A seemingly minor decision like naming a `package` affects the service name on the wire, how messages are referenced, where generated Java classes live, and how the API can evolve later. Therefore, you should agree on a package convention **before** generating code and publishing the contract to consumers.

After this lesson, you will be able to:

- Distinguish a Protocol Buffers `package` from `option java_package` and the directory path containing the `.proto` file.
- Design namespaces with clear business domains and versions to avoid name collisions when splitting multiple Spring gRPC services.
- Read both the wire-level service name and the Java class names generated from the same schema.
- Assess the impact of changing a package and troubleshoot common errors when proto files import one another.

## 1. Three Easily Confused Concepts

Suppose we have a product lookup service for an e-commerce system. In `catalog/v1/catalog.proto`:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_package = "com.myshop.grpc.catalog.v1";
option java_multiple_files = true;
option java_outer_classname = "CatalogProto";
```

These names play three different roles:

| Component | Role | In the example |
| --- | --- | --- |
| `package shop.catalog.v1;` | **Protocol Buffers logical** namespace: disambiguates messages, enums, and services; participates in forming the full RPC name. | `shop.catalog.v1.CatalogService` |
| `option java_package = "...";` | Package of the **generated Java classes** from the proto file. | `com.myshop.grpc.catalog.v1` |
| Path `catalog/v1/catalog.proto` | Source file location and name used in `import` statements (relative to a proto import root). | `import "catalog/v1/catalog.proto";` |

**Key point:** `java_package` does not change the service name on the wire. Conversely, the proto `package` does not force Java classes into a package of the same name once `java_package` is declared. Nor does the file path automatically configure either of these namespaces.

If `java_package` is not declared, the Java code generator typically uses the namespace from the proto `package`. However, declaring it explicitly makes the contract easier to read and avoids relying on each language's default rules.

### Related Java Options

- `java_multiple_files = true`: generates separate top-level Java classes for messages, enums, and service code produced by the gRPC plugin. This layout is usually easier to use in Spring projects. The file descriptor metadata can still reside in the outer class.
- `java_outer_classname = "CatalogProto"`: names the Java class that holds the file descriptor metadata; particularly useful for avoiding default name collisions with a message. This option does **not** change the RPC name.
- `java_package` is a Java-specific option. Clients written in Go, C#, or other languages have their own code-generation rules and options while still sharing the same proto `package`.

## 2. Choosing a Consistent Namespace Convention

An extensible convention is:

```text
<organization>.<business-domain>.<version>
```

For example:

| Requirement | Proto package | Java package |
| --- | --- | --- |
| Product lookup version 1 | `shop.catalog.v1` | `com.myshop.grpc.catalog.v1` |
| Order placement version 1 | `shop.order.v1` | `com.myshop.grpc.order.v1` |
| Shared data types version 1 | `shop.common.v1` | `com.myshop.grpc.common.v1` |
| Product API with breaking changes | `shop.catalog.v2` | `com.myshop.grpc.catalog.v2` |

The organization and business domain names in the table are only examples; a project should choose a prefix under its own ownership. Use lowercase letters and short, clear segments; name messages in `UpperCamelCase` and fields in `snake_case`. Do not share an overly broad namespace like `shop.v1` across all domains: two teams can easily collide on `CreateRequest`, `Status`, or `Result`.

**When should you add `v1`?** You should include the major version in the namespace starting with the very first public contract. Backward-compatible additions can remain in `v1`; when a breaking contract change is needed, create `v2` and allow both versions to coexist during the migration period. There is no need to change the package every time you add a backward-compatible field.

## 3. Complete Example: Two Protos and One Service

Source file layout:

```text
src/main/proto/
├── common/
│   └── v1/
│       └── money.proto
└── catalog/
    └── v1/
        └── catalog.proto
```

In `src/main/proto/common/v1/money.proto`:

```proto
syntax = "proto3";

package shop.common.v1;

option java_package = "com.myshop.grpc.common.v1";
option java_multiple_files = true;
option java_outer_classname = "MoneyProto";

message Money {
  string currency_code = 1;
  int64 units = 2;
  int32 nanos = 3;
}
```

In `src/main/proto/catalog/v1/catalog.proto`:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_package = "com.myshop.grpc.catalog.v1";
option java_multiple_files = true;
option java_outer_classname = "CatalogProto";

import "common/v1/money.proto";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string display_name = 2;
  .shop.common.v1.Money unit_price = 3;
}
```

In this example:

1. `import "common/v1/money.proto"` tells the compiler which file defines `Money`. Import paths are resolved from the root directory configured for the proto compiler, here `src/main/proto`.
2. `.shop.common.v1.Money` is a **fully qualified protobuf type name**. The leading dot indicates lookup from the root namespace, avoiding ambiguity with similarly named types in the current package.
3. `shop.catalog.v1` is the namespace of `CatalogService`, `GetProductRequest`, and `GetProductResponse`, while `shop.common.v1` is the namespace of `Money`. Importing does **not** pull types from another package into the same namespace.
4. Having the directories `common/v1` and `catalog/v1` match the trailing parts of the packages is a convention to aid lookup; it is not a Protocol Buffers syntax requirement.

### Java Code Generation Output

With the Protocol Buffers compiler and gRPC Java plugin configured in the project, the generated classes typically look like:

```text
com.myshop.grpc.common.v1
  ├── Money
  └── MoneyProto

com.myshop.grpc.catalog.v1
  ├── CatalogProto
  ├── GetProductRequest
  ├── GetProductResponse
  └── CatalogServiceGrpc
```

`CatalogServiceGrpc` contains the gRPC Java code generated from `service CatalogService`, while `GetProductRequest` and `GetProductResponse` are the message classes. This layout lets Spring code import the exact classes it needs directly:

```java
import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import com.myshop.grpc.catalog.v1.GetProductRequest;
import com.myshop.grpc.catalog.v1.GetProductResponse;
import com.myshop.grpc.common.v1.Money;
```

For example, a server implementation using Spring gRPC can be written as follows (assuming the project has configured the corresponding runtime and code-generation tools):

```java
package com.myshop.server.catalog;

import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import com.myshop.grpc.catalog.v1.GetProductRequest;
import com.myshop.grpc.catalog.v1.GetProductResponse;
import com.myshop.grpc.common.v1.Money;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class CatalogGrpcEndpoint
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<GetProductResponse> observer) {

        if (request.getProductId().isBlank()) {
            observer.onError(Status.INVALID_ARGUMENT
                    .withDescription("product_id is required")
                    .asRuntimeException());
            return;
        }

        GetProductResponse response = GetProductResponse.newBuilder()
                .setProductId(request.getProductId())
                .setDisplayName("Sample product")
                .setUnitPrice(Money.newBuilder()
                        .setCurrencyCode("VND")
                        .setUnits(125000)
                        .build())
                .build();

        observer.onNext(response);
        observer.onCompleted();
    }
}
```

The package `com.myshop.server.catalog` is the package of your **hand-written source code** and does not need to match the package of the generated code. The `@GrpcService` annotation enables Spring gRPC to discover and register the implementation; the location of `CatalogServiceGrpc` is still determined by `java_package`. The exact annotation name and registration configuration must match the Spring gRPC library version used by the project.

### What Names Appear on the Wire?

From the service declaration in the proto:

```proto
package shop.catalog.v1;
service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}
```

gRPC uses:

- Full service name: `shop.catalog.v1.CatalogService`.
- Full method name: `shop.catalog.v1.CatalogService/GetProduct`.
- HTTP/2 path of the call: `/shop.catalog.v1.CatalogService/GetProduct`.

Changing `java_package` to a different Java name **does not change** these three values; changing `package shop.catalog.v1` does. Clients with old stubs generally cannot call a server that only registers the service under a new package name, even when the handler logic is identical.

## 4. What Happens When You Change a Package?

| Change | Key impact | How to handle |
| --- | --- | --- |
| Rename `package shop.catalog.v1` to `shop.catalog.v2` | Changes the full names of services and messages in descriptors; changes RPC paths, affecting clients, reflection, and type references. | Treat as a contract change; create and deploy the `v2` API in parallel while clients migrate. |
| Change `java_package` while keeping the proto package | Java classes move to a new namespace, breaking imports or binary references in old Java code; RPC names on the wire stay the same. | Update Java projects and regenerate stubs alongside the contract. |
| Change `java_multiple_files` | Changes how generated Java classes are structured; may require fixing imports and type references. | Decide early and keep it stable once projects depend on generated code. |
| Change `java_outer_classname` | The name of the Java class containing the descriptor or wrapper class may change. | Check usages of the outer class and regenerate code. |
| Move/rename `.proto` files | `import` paths and build configurations in other projects may break; RPC names do not change automatically just from moving files. | Update import paths and compiler configurations for all consumers. |

Proto3 encodes data fields by **field number and wire type**, so changing the proto package alone does not necessarily change the bytes of a plain message. However, wire-level compatibility of a message alone **does not mean** gRPC API compatibility: the service name used for routing will differ. `google.protobuf.Any`, server reflection, or descriptor-processing code may also depend directly on the full message name.

Beyond packages, when evolving a schema you should keep published field numbers stable; if you remove a field, use `reserved` for the old number and name to prevent accidental reuse. That is a compatibility rule independent of namespace naming.

## 5. Process for Deciding a Package for a New API

1. **Identify the API owner:** choose an organization-managed prefix, such as `shop`, instead of an arbitrary name that could collide with other systems.
2. **Identify the business domain:** `catalog`, `order`, or `identity`. If two sets of messages have different lifecycles and owners, consider splitting packages.
3. **Determine the contract version:** start with `v1`; prepare a strategy to run `v1` and `v2` concurrently if breaking changes are needed.
4. **Choose an explicit Java package:** use a namespace aligned with company conventions, such as `com.myshop.grpc.catalog.v1`, and keep it consistent across files in the same domain.
5. **Name files and import roots:** organize `src/main/proto/catalog/v1/` in a predictable layout and configure one or more clear import roots during compilation.
6. **Generate code and inspect the actual names:** check the imports of `GetProductRequest`/`CatalogServiceGrpc` and the full service name; test an end-to-end call once the server is running.
7. **Publish the contract with conventions:** client and server generate code from the same proto version; manage changes via version control and an API review process.

Example of checking the registered method with `grpcurl` when a test server is listening on `localhost:9090`, supporting plaintext connections, and the proto files are available at the location above:

```bash
grpcurl -plaintext -import-path src/main/proto -proto catalog/v1/catalog.proto -d '{"productId":"P-100"}' localhost:9090 shop.catalog.v1.CatalogService/GetProduct
```

The end of the command is the service/method name from the **proto package**, not `com.myshop.grpc.catalog.v1.CatalogServiceGrpc`. Port, TLS, and server address are separate deployment settings; changing the namespace does not replace security or endpoint configuration.

## 6. Common Errors and How to Diagnose Them

| Symptom | Causes to check | Resolution |
| --- | --- | --- |
| Java reports `package ... does not exist` when importing stubs | Using the proto `package` for a Java import when `java_package` differs; or code has not been generated/added to the classpath. | Check the `java_package` setting, generated classes, and build setup. |
| Compiler reports `common/v1/money.proto` not found | Import root does not cover `src/main/proto`, or the `import` path does not match. | Fix the proto include path or directory structure, then recompile. |
| Compiler does not recognize `Money` or reports ambiguity | The file is imported but the wrong namespace is used, or two packages have colliding type names. | Reference `.shop.common.v1.Money` and check `package` in the defining file. |
| Client receives `UNIMPLEMENTED` even though the server is running | Client calls an old service/method name; server registers a new package, or the implementation is not registered. | Compare the full service name against what the server actually exposes and check Spring gRPC registration config. |
| Java code suffers from duplicate class name collisions | Multiple protos share the same `java_package` and have colliding message/outer class names. | Split packages by domain/version, adjust class names, and regenerate code. |
| Clients in multiple languages see unexpected names | Confusing Java names with protobuf names, or relying on a language-specific option. | Standardize the schema and proto `package`; verify code-generation options for each language. |

## 7. Knowledge Self-Check

**Scenario A:** The file `catalog.proto` has `package shop.catalog.v1;` and `option java_package = "com.myshop.api.catalog";`. The client calls `/shop.catalog.v1.CatalogService/GetProduct`. If `java_package` is changed to `com.myshop.grpc.catalog.v1` without modifying the proto package, does the gRPC path change?

**Answer:** No. The gRPC path is based on the proto `package`, `service` name, and `rpc` name. Java projects may need to update imports, recompile, and redistribute the generated code library.

**Scenario B:** Two files in `catalog/v1/` and `order/v1/` both declare `message CreateRequest`. How can name collisions be avoided?

**Answer:** Set `package shop.catalog.v1;` and `package shop.order.v1;` respectively; when cross-referencing, use the fully qualified protobuf name. Also set distinct `java_package` values so generated Java code does not collide.

**Scenario C:** A team plans to switch from `shop.catalog.v1` to `shop.catalog.v2` without modifying running clients. What is the main risk?

**Answer:** The full service name and RPC path change, so clients calling the old name may encounter `UNIMPLEMENTED`. You need to keep the `v1` server running or provide a compatibility layer while migrating clients to `v2`.

Remember: **the proto `package` defines the gRPC contract identity; `java_package` determines where generated Java code is placed; the file path determines how schemas are located and imported.** Designing all three consistently from the start helps multi-service, polyglot Spring gRPC systems evolve reliably.
