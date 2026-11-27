# Versioning Packages and Services

Once a gRPC API already has running clients, contract changes affect more than Protocol Buffers files and generated Java code. The protobuf package name and service name also form the **RPC identity on the wire**. Changing them can cause old clients to call a path that the new server no longer registers, even when the underlying handler logic is nearly identical.

In **Spring gRPC**, versioning packages and services lets multiple API generations coexist during a transition period. This lesson focuses on distinguishing a protobuf `package` from `java_package`, deciding when to keep `v1` vs. create `v2`, naming services, and running two versions side by side.

## 1. Three Different Names, Three Different Impacts

Consider `catalog/v1/catalog.proto`:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_package = "com.myshop.grpc.catalog.v1";
option java_multiple_files = true;
option java_outer_classname = "CatalogProto";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string display_name = 2;
}
```

Each declaration plays a distinct role:

| Declaration | What is it for? | What a change affects |
| --- | --- | --- |
| `package shop.catalog.v1;` | Namespace of messages, enums, and services in protobuf descriptors | Full type names; full service name and RPC paths |
| `option java_package = "...";` | Java package containing generated classes | Imports, generated class locations, and dependent Java code |
| `service CatalogService` | Service name in the gRPC contract | RPC path of every method in the service |
| File path `catalog/v1/catalog.proto` | Source file location and path used in `import` | Build/import paths; does not automatically determine the protobuf package |

With the declarations above, the full service name is `shop.catalog.v1.CatalogService`; the method path is:

```text
/shop.catalog.v1.CatalogService/GetProduct
```

This path is formed from **protobuf package + service name + method name**. `java_package` plays no part in constructing that path.

For instance, changing only:

```proto
option java_package = "com.myshop.generated.catalog";
```

moves the generated Java classes to a different package, yet the service is still invoked at `/shop.catalog.v1.CatalogService/GetProduct`. Conversely, changing `package shop.catalog.v1` to `shop.catalog.v2` changes the service and message identities in protobuf, even if `java_package` stays the same.

## 2. When to Keep `v1`, and When to Create `v2`?

You do not need a new package for every field addition. Distinguish **compatible extensions** from changes that cause clients to misinterpret data or stop working against the contract.

| Change | Typically appropriate approach |
| --- | --- |
| Adding a new field with an unused field number and a safe fallback | Keep `shop.catalog.v1` |
| Adding a new RPC without changing existing RPCs' behavior | Can be added to the `v1` service; deploy the server before clients call the new method |
| Adding an enum value when every consumer has a safe unknown branch | Can keep `v1`, but roll out carefully |
| Changing the meaning of a field already used by clients | Create a new API or `v2`; never silently alter `v1` semantics |
| Changing a field type/number incompatibly | Design a `v2` message/API |
| Renaming a published service or method | RPC path changes; keep the old endpoint in parallel or publish a new API |
| Removing behavior that old clients still rely on | Keep `v1` during migration; `v2` defines the new behavior |

A practical rule: **`v1` preserves its published contract and behavior; `v2` is for changes that cannot remain safely compatible**. A new version is not a substitute for evaluating compatibility. If you are only adding an optional field with a safe default, creating `v2` increases client, documentation, and operational costs without real benefit.

### Structural Changes vs. Behavioral Changes

Some changes still parse cleanly in binary protobuf yet break the contract. For example, changing the meaning of `price_minor_units` from "dollars" to "cents" does not necessarily alter the wire format, yet clients will miscalculate prices. Similarly, a server might start requiring a new field and return `INVALID_ARGUMENT` to `v1` clients even though the new schema still parses old requests.

When deciding on versioning, evaluate all four dimensions:

- **Wire compatibility:** do old fields still decode properly?
- **Behavior compatibility:** do old clients still receive the same outcomes and errors as before?
- **Source compatibility:** does generated Java code still expose the classes, accessors, and methods applications use?
- **Routing compatibility:** do old clients still hit the right full method path?

## 3. Putting the Version in the Protobuf Package

For major changes affecting multiple messages or services in the same domain, putting the version in the protobuf package is a clean approach:

```proto
// catalog/v1/catalog.proto
package shop.catalog.v1;
option java_package = "com.myshop.grpc.catalog.v1";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string display_name = 2;
}
```

When incompatible changes are needed:

```proto
// catalog/v2/catalog.proto
package shop.catalog.v2;
option java_package = "com.myshop.grpc.catalog.v2";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
  string locale = 2;
}

message GetProductResponse {
  string product_id = 1;
  string display_name = 2;
  string localized_description = 3;
}
```

Both services share the short name `CatalogService`, yet their different protobuf packages give them distinct full names and RPC paths:

| Version | Full service name | Method path |
| --- | --- | --- |
| v1 | `shop.catalog.v1.CatalogService` | `/shop.catalog.v1.CatalogService/GetProduct` |
| v2 | `shop.catalog.v2.CatalogService` | `/shop.catalog.v2.CatalogService/GetProduct` |

`v1` clients keep calling `v1`; upgraded clients call `v2`. Both can run on the same server and port if the server registers both services. Reusing the method name `GetProduct` causes no conflict because the full service names differ.

### Do Not Confuse Package With Directory

The file path `catalog/v2/catalog.proto` is a source-organization convention. The compiler does not infer `package shop.catalog.v2` from the directory. Nor should you expect moving a file from `catalog/v1` to `catalog/v2` to rename RPCs automatically; you must update the `package` declaration and corresponding imports to change the namespace.

## 4. When to Version the Service Name Instead of the Package?

Sometimes only one group of methods needs to change while shared messages keep their exact semantics. In that case, you can keep the package and add a new service:

```proto
package shop.catalog.v1;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

service CatalogAdminService {
  rpc ReindexCatalog(ReindexCatalogRequest)
      returns (ReindexCatalogResponse);
}
```

If an incompatible behavior is needed for just one service, you can also publish a newly named service such as `CatalogQueryV2Service` while keeping messages in the current package. However, that requires consistent naming conventions and can leave multiple contract generations mixed inside one package.

Choose based on the scope of change:

- **Version the package** when messages, enums, and multiple services of an API all need a new contract generation. This cleanly isolates `v1` and `v2` namespaces.
- **Version the service** when only one service boundary changes, related messages remain compatible, and the team wants to keep other services in the same package.
- **Add a method to an existing service** when introducing new functionality without altering the semantics of existing methods.

If you version only the service while the new request/response types are also incompatible, declare new messages with distinct names such as `GetProductV2Request` and `GetProductV2Response`; never alter old message definitions still used by `v1` clients. If many messages must change together, package versioning usually draws a cleaner boundary.

Avoid redundant versioning in both package and service like `shop.catalog.v2.CatalogServiceV2`, unless an explicit convention explains why two version numbers represent independent lifecycles. Choosing one place as the version boundary is usually easier to read.

## 5. What Does Changing the Protobuf Package Affect?

Changing `package` does not change message field numbers, so the binary payload of an individual message may carry the same tags. However, **type identities** in protobuf change:

1. **RPC routing:** the full service name changes; old client stubs still call the old path. If the server registers the service only under the new package, old clients typically receive `UNIMPLEMENTED`.
2. **Descriptors and reflection:** full message/service names differ; reflection tools, schema registries, or descriptor-driven systems must be updated.
3. **`google.protobuf.Any`:** the default type URL contains the full message name, e.g., `type.googleapis.com/shop.catalog.v1.Product`. Changing the package changes the type URL, so consumers must handle both identifiers during migration if `Any` payloads are stored or exchanged.
4. **Generated Java:** if `java_package` also changes, Java imports and binary/source APIs change. If only the protobuf package changes, Java classes may remain in the old Java package while protobuf descriptors still carry the new names.
5. **Importing files:** fully qualified type references and source imports may need adjustments. File paths and protobuf packages are separate concepts.

Therefore, never treat changing a protobuf package as a mere directory rename. It creates a brand-new API identity at the protobuf/gRPC layer.

## 6. Is Changing `java_package` an API Version Change?

No. `java_package` controls only the generated Java namespace. For example:

```proto
package shop.catalog.v1;
option java_package = "com.myshop.grpc.catalog.generated";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}
```

The full service name remains `shop.catalog.v1.CatalogService`; the method path remains `/shop.catalog.v1.CatalogService/GetProduct`. However, Java code will import classes from `com.myshop.grpc.catalog.generated`.

Changing `java_package` can break compilation in Java projects until imports, dependencies, and generated artifacts are updated. If multiple Java modules consume the generated classes, treat this as a Java source/binary API change and plan upgrades accordingly. It does not create a `v2` gRPC endpoint and does not automatically let `v1` and `v2` servers coexist.

When compiling `v1` and `v2` into the same Java artifact, set distinct `java_package` values (typically including the version suffix) so classes with the same simple message names do not collide. That is a Java code namespace decision; RPC paths remain governed by the protobuf package and service name.

## 7. Running `v1` and `v2` Simultaneously in Spring gRPC

With two different packages, code generation produces two separate service base classes. A server can register both implementations:

```java
package com.myshop.server.catalog;

import com.myshop.grpc.catalog.v1.CatalogServiceGrpc;
import org.springframework.grpc.server.service.GrpcService;

@GrpcService
public class CatalogV1Endpoint
        extends CatalogServiceGrpc.CatalogServiceImplBase {
    // Keep published v1 behavior and contract.
}

@GrpcService
public class CatalogV2Endpoint
        extends com.myshop.grpc.catalog.v2.CatalogServiceGrpc.CatalogServiceImplBase {
    // Map v2 requests/responses to the domain service as appropriate.
}
```

This example assumes the project's Spring gRPC version discovers implementations via `@GrpcService`. During integration, verify that the server registers **two distinct full service names**. Never register two implementations with the same full service name on the same server, as they compete for the same endpoint.

Both endpoints can call a shared domain/application service:

```text
CatalogV1Endpoint ──┐
                    ├── CatalogApplicationService ── Repository
CatalogV2Endpoint ──┘
```

This keeps business logic consistent while `v1`/`v2` adapters translate between different messages. Never have the `v2` implementation call the server's own `v1` RPC over the network when it can invoke the application service directly; looping over the network adds timeouts, serialization overhead, and operational coupling.

## 8. Planning Client Migration From `v1` to `v2`

Versioning is only useful with a clear migration path:

1. **Publish `v2`:** define the new package, messages, and semantics; document differences from `v1`.
2. **Deploy parallel server support:** register both `shop.catalog.v1.CatalogService` and `shop.catalog.v2.CatalogService`.
3. **Test both contracts:** confirm `v1` clients retain legacy behavior; `v2` clients can call the new endpoint and handle statuses properly.
4. **Roll out `v2` clients in waves:** shift an initial slice of traffic and monitor `UNIMPLEMENTED`, `INVALID_ARGUMENT`, latency, and per-service usage share.
5. **Announce `v1` deprecation:** specify timelines, remaining consumers, and partner support options.
6. **Retire `v1` after confirming zero consumers:** remove the old service only once metrics prove traffic has migrated, not merely because new client code was released.

If `v2` uses the same host and port, clients select the version through their corresponding generated stub. gRPC does not negotiate package versions automatically or silently fall back from `v1` to `v2`. A call to a non-existent full method path will not automatically route to a similarly named service.

### Tracking Traffic by Full Method Name

Metrics and interceptors should distinguish methods such as:

```text
shop.catalog.v1.CatalogService/GetProduct
shop.catalog.v2.CatalogService/GetProduct
```

This tells operations teams which clients still use `v1`, whether `v2` produces errors, and when `v1` can be retired. Avoid tagging metrics with user IDs or sensitive data; the full method name is usually sufficient to track API adoption.

## 9. Version Boundary Checklist

- [ ] Determined whether the change is additive or breaks wire, behavior, source, or routing compatibility.
- [ ] Distinguished `package`, `java_package`, service name, and file path.
- [ ] If creating a `v2` package, new messages and services have distinct full names without descriptor collisions.
- [ ] If versioning only a service, shared messages retain compatible semantics.
- [ ] Avoided redundant versioning in both package and service unless justified by independent lifecycles.
- [ ] Checked `Any` type URLs, reflection, and schema registries if used.
- [ ] Server can register two full service names in parallel and keep `v1` running.
- [ ] Clients choose the right generated stub rather than expecting gRPC to fall back between versions.
- [ ] Per-full-method-name metrics, a migration plan, and `v1` retirement criteria are in place.

**Self-Check**

**Question 1.** Does changing `option java_package` from `com.myshop.grpc.catalog.v1` to `com.myshop.generated.catalog` change the path `/shop.catalog.v1.CatalogService/GetProduct`?

*Answer:* No. The path is determined by the protobuf package, service name, and method name. The Java package changes only where generated classes live.

**Question 2.** What is the impact of changing `package shop.catalog.v1` to `shop.catalog.v2` while keeping the service name unchanged?

*Answer:* The full service name and method path change; message full names and descriptors also change. Wire fields might still decode if tags/types match, yet it is a brand-new API identity.

**Question 3.** When should you add a method to a `v1` service instead of creating a `v2` package?

*Answer:* When the new capability extends the API without breaking existing semantics, existing messages still fit cleanly, and `v1` clients see no behavioral change. Deploy the method on the server before clients invoke it.

**Question 4.** Can `v1` and `v2` be registered on the same server?

*Answer:* Yes, provided they have different full service names, typically via different protobuf package versions. Two implementations with the same full service name will conflict.

Versioning packages and services is how you manage **API identity**, not just directory names. Keeping `v1` for compatible extensions, creating `v2` when semantics or identities cannot stay intact, and running both services in parallel during migration lets Spring gRPC clients upgrade under full control.
