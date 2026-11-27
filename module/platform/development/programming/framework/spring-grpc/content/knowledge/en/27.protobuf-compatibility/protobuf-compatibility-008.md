# Changing Package or Service Name

## 1. Why Can Changing Package or Service Name Break Compatibility?

In **SPRING_GRPC**, a Protobuf schema defines the messages and services used by clients and servers to communicate. Changing a protobuf package or service name is not merely changing a source namespace: they participate in constructing the **full gRPC method name**. Clients invoke RPCs using this full name in the HTTP/2 path; servers register handlers under the same identifier.

Therefore, a new server might still run and parse message bytes, yet old clients call an RPC path the server no longer registers. The Protobuf package also forms fully-qualified message names, affecting descriptors, reflection, and google.protobuf.Any.

You must distinguish between:

- package in the proto file: the namespace for messages, enums, and services; participates in the full gRPC service/method name.
- Service name and rpc name: participate in the RPC path.
- option java_package: the namespace for generated Java classes; affects the compile-time API but does not determine the RPC path.

This lesson focuses on the impact of each name type, keeping old services alive during transitions, dual registration, updating name-dependent integrations, and testing mixed-version rollouts.

## 2. Full gRPC Method Name

Example:

```proto
syntax = "proto3";

package catalog.v1;

service ProductService {
  rpc GetProduct(GetProductRequest) returns (ProductReply);
}
```

The full service name is catalog.v1.ProductService; the full method name is:

```text
/catalog.v1.ProductService/GetProduct
```

This is the name used as the HTTP/2 :path when a client invokes the RPC. The generated Java stub stores the corresponding method descriptor; the client does not simply send a Java class name to the server.

| Component | Old example | If changed | Impact |
| --- | --- | --- | --- |
| Protobuf package | catalog.v1 | catalog.v2 | Changes service full name and RPC path |
| Service name | ProductService | CatalogProductService | Changes RPC path |
| RPC method name | GetProduct | FetchProduct | Changes RPC path |

If the new server only registers /catalog.v2.ProductService/GetProduct, an old client calling /catalog.v1.ProductService/GetProduct will not match any handler. When the server is reachable but lacks the matching method path, the client typically receives UNIMPLEMENTED. This is a contract routing error, distinct from connectivity errors such as UNAVAILABLE.

## 3. Distinguishing protobuf package from java_package

Example:

```proto
syntax = "proto3";

package catalog.v1;

option java_package = "com.example.generated.catalog";
option java_multiple_files = true;

message ProductReply {
  string sku = 1;
}
```

The two namespaces serve different purposes:

| Declaration | Impact |
| --- | --- |
| package catalog.v1 | Protobuf fully-qualified names; service full name; descriptors; Any type URL |
| option java_package | Java package of generated classes |
| option java_multiple_files | How messages/enums are split into Java files |
| option java_outer_classname | Outer wrapper class name when using the corresponding codegen mode |

If you only change java_package, binary message field tags and the gRPC method path stay unchanged, provided protobuf package, service, and RPC names do not change. However, Java consumers may fail to compile because generated classes moved packages.

Conversely, changing package catalog.v1 to package catalog.v2 can keep java_package unchanged while still changing the gRPC method path and Protobuf type names. Keeping the Java package does not restore wire service identity.

The proto file path in an import is also different from the protobuf package. Imports use file paths in the proto source tree; package is the namespace declared inside the file. Changing one does not automatically change the other.

## 4. Changing protobuf package Affects Message Type Identity

Field numbers and wire types determine how binary messages are parsed. Fully-qualified message names are not embedded into every ordinary message payload. Thus, changing the protobuf package while preserving message structure may not alter the bytes of an individual message.

However, type identity is still used by other mechanisms:

- Descriptors and reflection look up messages by fully-qualified name.
- google.protobuf.Any packs a type URL containing the type name, typically formatted as type.googleapis.com/catalog.v1.ProductReply.
- Protobuf JSON for Any requires a type registry to resolve the right message type.
- Schema registries, gateways, validation, and tooling may reference the fully-qualified name.
- Service method descriptors use package/service/method names to identify RPCs.

An Any stored with type URL type.googleapis.com/catalog.v1.ProductReply does not automatically become catalog.v2.ProductReply simply because the new schema changed packages. New consumers must retain the ability to resolve the old type or perform an explicit data conversion step.

Hence, evaluating a package rename must cover both RPC paths and message type identity, especially when the system stores Any payloads, descriptors, or long-lived Protobuf data.

## 5. Changing Service Name or RPC Method Name

Changing the service name while keeping the package:

```proto
package catalog.v1;

service CatalogProductService {
  rpc GetProduct(GetProductRequest) returns (ProductReply);
}
```

The RPC path changes from:

```text
/catalog.v1.ProductService/GetProduct
```

to:

```text
/catalog.v1.CatalogProductService/GetProduct
```

Renaming method GetProduct to FetchProduct also changes the path, even if request/response messages stay identical.

Places that commonly depend on service/method names:

- Generated Java stubs and service base classes.
- Server registration and gRPC reflection.
- gRPC Health Checking Protocol, where health statuses can be registered per service name.
- Authorization/interceptor rules matching full method names.
- Service configs, retry policies, and load-balancing method configs.
- Metrics, tracing span names, dashboards, and alerts.
- Gateways, transcoding configs, OpenAPI, or client SDKs.
- Integration tests, command-line tools, and operational scripts.

If you rename a service but forget to update health status registration or authorization rules, the RPC may execute while health probes report errors or requests get rejected. Every component using full service/method names must be updated.

## 6. Why Doesn't reserved Solve Service Renaming?

Protobuf reserved is used inside messages and enums to lock removed field numbers/names or enum numbers/names. It is not an aliasing mechanism for package, service, or RPC method names.

When retiring an old service, the way to protect active clients is to **continue registering the old service/method during a transition period**. There is no service-level reserved declaration that lets a server automatically map an old name to a new name.

For fields and messages, reservations and schema compatibility rules can prevent certain kinds of reuse. For service identity, you must manage it via versioned APIs, retaining old handlers, contract registries, and RPC path testing.

## 7. Versioning and Keeping v1/v2 Services Coexisting

A common approach is to retain the v1 package/service and introduce a v2 API. Shared messages can stay in package v1 while the new service lives in package v2:

```proto
syntax = "proto3";

package catalog.v2;

import "catalog/v1/product_messages.proto";

service ProductService {
  rpc GetProduct(catalog.v1.GetProductRequest)
      returns (catalog.v1.ProductReply);
}
```

During the transition period, the server registers both v1 and v2 services. Both adapters can delegate to the same application/domain service:

```java
Server server = ServerBuilder.forPort(port)
    .addService(new ProductServiceV1Adapter(applicationService))
    .addService(new ProductServiceV2Adapter(applicationService))
    .build();
```

Adapter class names are illustrative. Each adapter is generated from its respective service definition; adapters translate requests/responses if the v2 contract uses different messages.

This approach lets old clients keep calling the v1 full method name, new clients call v2, and business logic stay shared. If message packages must also change, create v2 messages and write mappings between v1/v2 messages and the domain model. If only the service namespace needs to change, you can import and reuse existing message types.

## 8. Safe Rollout Sequence

Changing package/service names must be rolled out in server/reader-before-client order:

1. **Inventory consumers:** identify client versions, service paths, gateways, health probes, auth policies, service configs, reflection, and Any data.
2. **Define the new API:** create the v2 package/service; retain old methods in the v1 schema during transition.
3. **Deploy server dual registration:** the new server registers both v1 and v2, delegating through the application service or adapters.
4. **Update infrastructure:** ensure health services, authorization/interceptors, routing, metrics, tracing, and gateways recognize both names.
5. **Test the new server:** invoke both v1 and v2 full method names; confirm both work.
6. **Release v2 clients:** gradually migrate consumers to the new endpoint/method; maintain rollback capability.
7. **Monitor v1 traffic:** measure request counts, errors, and consumers still calling the old service.
8. **Conditionally retire v1:** only after confirming no consumers, data, or jobs require v1 and the rollback window has elapsed.
9. **Deregister old service:** remove the v1 service in a separate release, announce deprecation, and update the contract baseline.

Do not remove the v1 service solely because v2 clients have been released. Batch jobs, mobile clients, external integrations, or queue consumers may upgrade much more slowly.

## 9. Testing Compatibility and Routing

CI should verify both the schema and actual RPC paths:

| Test | What to verify |
| --- | --- |
| Descriptor test | ServiceDescriptor has the expected full service name |
| Method descriptor test | Full method name preserves the exact package/service/method |
| Old client → new server | Dual-registered server still accepts v1 RPCs |
| New client → new server | v2 RPCs work |
| New client → old server | Clarify whether rollback compatibility is supported |
| Health check | Health service reports status for both v1/v2 service names |
| Reflection | Clients/tooling see the required service versions |
| Auth/interceptor | Policies match full method names for both versions |
| Any payload | Old type URLs resolve or migrate as planned |
| Gateway/JSON | Routes and mappings are not broken by the namespace change |

Example descriptor test in Java:

```java
assertEquals(
    "catalog.v2.ProductService",
    ProductServiceGrpc.getServiceDescriptor().getName()
);

assertEquals(
    "catalog.v2.ProductService/GetProduct",
    ProductServiceGrpc.getGetProductMethod().getFullMethodName()
);
```

Generated class names depend on java_package and codegen options; use the exact classes from the contract under test. Descriptor tests confirm the identifier generated code will invoke, while integration tests confirm the server actually registers the matching handler.

Beyond path tests, run schema breaking checks against the released baseline. Schema tools and descriptor tests do not replace checks for gateways, health, authorization, and production traffic.

## 10. Common Mistakes

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| Old client receives UNIMPLEMENTED | Server no longer registers the old full method name | Dual-register v1/v2 during the transition period |
| Java client fails to compile after changing java_package | Generated classes moved namespaces | Update imports or version the contract artifact |
| RPC path changed even though Java package stayed the same | Protobuf package or service name changed | Check the full method name from the descriptor |
| Health probe reports NOT_SERVING/unknown | Health registry only registered the new or old service name | Register health status for every supported service name |
| Authorization rejects new RPC | Interceptor rule still matches old path | Update policies for the new full method name |
| Reflection/tools cannot see old service | Server stopped registering old service or reflection was not updated | Check registered services and reflection |
| Any.unpack() fails | Type URL uses old protobuf message FQN | Keep old type or convert type URL/data in a controlled way |
| Metrics split into a new series | Full method name/label changed | Update dashboards and monitor both names in parallel |

When diagnosing, obtain the full method name from the client descriptor or trace. Never infer the RPC path from the Java package; the two namespaces serve distinct roles.

## 11. Checklist for Reviewing Package/Service Changes

- Clarified whether this changes the protobuf package, service name, RPC method name, or only java_package.
- Documented both old and new full gRPC method names.
- Audited fully-qualified message names, descriptors/reflection, and Any type URLs if changing the protobuf package.
- Evaluated generated Java API impact if changing java_package, java_outer_classname, or codegen options.
- v1 service remains registered while old clients exist.
- v2 server is ready before switching clients.
- Health checking, auth/interceptors, service configs, gateways, and observability are updated.
- Descriptor tests and integration tests exist for both v1 and v2 paths.
- Plan is in place to measure old traffic, deprecate, and schedule v1 removal.
- CI breaking check uses the released baseline and records the new contract version.

With **SPRING_GRPC**, the protobuf package and service name are part of RPC identity, whereas java_package primarily governs the namespace of generated Java code. Changing them by mistake or without dual registration can cause old clients to call a method path that no longer exists. Keeping old services during transitions, deploying v2-capable servers before clients, and testing full method names along with dependent integrations enable controlled upgrades.
