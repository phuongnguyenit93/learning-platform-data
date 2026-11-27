# Versioning Contract Testing

In Spring gRPC, contract versioning ensures clients and servers can be released, upgraded, and rolled back at different times while still communicating properly. A contract does not consist solely of `.proto` files; it also includes wire service/method names, message types, field semantics, status/error details, and the behavior clients expect.

**Versioning contract testing** verifies key client/server version pairs before release. The goal is to catch compatibility-breaking changes early, especially during rolling deployments or when multiple consumers cannot upgrade simultaneously.

## 1. Distinguishing Wire Versions from Java Versions

The Protobuf package name determines the full names of messages and gRPC services on the wire. A gRPC method path is formed from the package, service, and method:

~~~text
/acme.catalog.v1.CatalogService/GetProduct
~~~

Different components play different roles:

| Component | Impact |
| --- | --- |
| `package` in `.proto` | Full Protobuf name and gRPC service path; changing it can prevent clients from finding the method |
| `service` or `rpc` name | Part of the gRPC method path; changing it changes the wire endpoint |
| `java_package` | Generated Java package; does not itself change the gRPC method path |
| `java_multiple_files` | How Java classes are generated; does not change the wire contract |
| Field number and wire type | How Protobuf messages are encoded/decoded |

You can change `java_package` to reorganize source code if you keep the proto package, service, method, and message semantics unchanged. Changing the package from `acme.catalog.v1` to `acme.catalog.v2` creates a different service path; treat that as a new API version and maintain v1 while consumers migrate.

## 2. Safe Protobuf Evolution Rules

When extending messages, prefer adding new fields with previously unused field numbers. For example:

~~~proto
// Contract v1
message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string name = 2;
}
~~~

An extended version can add fields:

~~~proto
// Current contract, still keeping v1's proto package/service/method
message GetProductRequest {
  string product_id = 1;
  optional string locale = 2;
}

message GetProductResponse {
  string product_id = 1;
  string name = 2;
  optional string display_name = 3;
}
~~~

Key rules:

- Never change already-released field numbers.
- Never reuse field numbers or names of deleted fields; use `reserved`.
- Adding a new field is usually compatible at the wire level, yet consumers still need to handle default values and presence.
- Never change a type merely because certain types share the same wire type; semantics, value ranges, and encoding can differ.
- Never change singular to repeated, move fields into/out of `oneof`, or alter the meaning of an active field.
- Adding enum values requires ensuring older clients handle unknown values.
- Never rename services/methods or proto packages within the same version path if older clients must remain supported.

When deleting a field, keep the previously used number and name in a `reserved` state:

~~~proto
message GetProductResponse {
  string product_id = 1;
  string name = 2;
  optional string display_name = 3;

  reserved 4;
  reserved "legacy_description";
}
~~~

`reserved` prevents developers from accidentally reassigning old tags in a future change. This provides long-term protection for data serialized, stored, or transmitted across different versions.

## 3. Which Changes Require a New Version?

| Change | Risk | Recommended Approach |
| --- | --- | --- |
| Add a new optional field | Usually wire-compatible | Check default/presence handling in older consumers |
| Delete a field without reserving | Risk of tag reuse | Reserve both number and name |
| Change field number | Breaking | Keep the old tag; add a new field if needed |
| Change `int32` to `sint32` | Same wire type yet different encoding | Do not change directly; add a new field |
| Change `string` to `bytes` | May parse yet semantics change | Add a new field and migrate |
| Rename RPC or service | gRPC method path changes | Keep the old endpoint or create a new version |
| Change proto package | Full service/message names change | Maintain v1 and create v2 in parallel |
| Add enum value | Older clients may encounter unknown values | Require clients to handle unknown enums |
| Change streaming shape | Alters call protocol | Create a new RPC/version |

Do not evaluate compatibility solely by whether the schema compiles. A change can be wire-compatible yet break business semantics, such as changing the meaning of `price` from dollars to cents while keeping `int64`.

## 4. Bidirectional Testing Between Old Clients and New Servers

Rolling deployments often have new servers running while some clients still use older generated stubs. Contract tests must prove:

1. v1 clients can call the new server.
2. New clients can call the v1 server if the change is designed to be compatible.
3. New fields do not cause older clients to fail when parsing responses.
4. Older servers ignore new request fields and new clients handle missing values per default/presence rules.

Example test fixtures with two `.proto` files keeping the same package, service, RPC, and old fields, while using different `java_package` values to coexist in the test module:

~~~proto
// Client v1 fixture: java_package = "com.acme.catalog.client.v1"
syntax = "proto3";
package acme.catalog.v1;
option java_multiple_files = true;
option java_package = "com.acme.catalog.client.v1";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}
message GetProductRequest {
  string product_id = 1;
}
message GetProductResponse {
  string product_id = 1;
  string name = 2;
}
~~~

~~~proto
// Current server fixture: java_package = "com.acme.catalog.server.current"
syntax = "proto3";
package acme.catalog.v1;
option java_multiple_files = true;
option java_package = "com.acme.catalog.server.current";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}
message GetProductRequest {
  string product_id = 1;
  optional string locale = 2;
}
message GetProductResponse {
  string product_id = 1;
  string name = 2;
  optional string display_name = 3;
}
~~~

`java_package` differs to avoid Java class name collisions; the Protobuf package remains `acme.catalog.v1`, so the full gRPC method path stays identical. In real repositories, place old fixtures in a separate test source set or pull generated artifacts from the previous release rather than hand-editing generated files.

## 5. Contract Test: Old Client Calling New Server

The new server understands `locale` and additionally returns `display_name`. The older client only knows v1 fields:

~~~java
import io.grpc.Server;
import io.grpc.ManagedChannel;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OldClientNewServerContractTest {

    @Test
    void oldClientCanReadResponseFromNewServer() throws Exception {
        String name = InProcessServerBuilder.generateName();

        var service =
            new com.acme.catalog.server.current.CatalogServiceGrpc
                .CatalogServiceImplBase() {
                @Override
                public void getProduct(
                    com.acme.catalog.server.current.GetProductRequest request,
                    StreamObserver<
                        com.acme.catalog.server.current.GetProductResponse>
                            observer) {
                    observer.onNext(
                        com.acme.catalog.server.current.GetProductResponse
                            .newBuilder()
                            .setProductId(request.getProductId())
                            .setName("Keyboard")
                            .setDisplayName("Mechanical Keyboard")
                            .build());
                    observer.onCompleted();
                }
            };

        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(service)
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

        try {
            var oldStub =
                com.acme.catalog.client.v1.CatalogServiceGrpc
                    .newBlockingStub(channel)
                    .withDeadlineAfter(1, TimeUnit.SECONDS);

            var response = oldStub.getProduct(
                com.acme.catalog.client.v1.GetProductRequest.newBuilder()
                    .setProductId("p-42")
                    .build());

            assertEquals("p-42", response.getProductId());
            assertEquals("Keyboard", response.getName());
            // Client v1 has no display_name getter; the new field is treated as unknown.
            assertTrue(response.getUnknownFields().asMap().containsKey(3));
        } finally {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }
}
~~~

This test proves the new response is still parsed by the older client: old fields preserve their tags and types; the new field is preserved as an unknown field in Protobuf Java. Older applications cannot use the new field, yet they still read the data they need.

## 6. Contract Test: New Client Calling Old Server

The older server does not know `locale` and `display_name`. The new client must accept responses without the new field:

~~~java
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class NewClientOldServerContractTest {

    @Test
    void newClientAcceptsResponseFromOldServer() throws Exception {
        String name = InProcessServerBuilder.generateName();

        var legacyService =
            new com.acme.catalog.client.v1.CatalogServiceGrpc
                .CatalogServiceImplBase() {
                @Override
                public void getProduct(
                    com.acme.catalog.client.v1.GetProductRequest request,
                    StreamObserver<
                        com.acme.catalog.client.v1.GetProductResponse>
                            observer) {
                    observer.onNext(
                        com.acme.catalog.client.v1.GetProductResponse
                            .newBuilder()
                            .setProductId(request.getProductId())
                            .setName("Keyboard")
                            .build());
                    observer.onCompleted();
                }
            };

        Server server = InProcessServerBuilder.forName(name)
            .directExecutor()
            .addService(legacyService)
            .build()
            .start();
        ManagedChannel channel = InProcessChannelBuilder.forName(name)
            .directExecutor()
            .build();

        try {
            var currentStub =
                com.acme.catalog.server.current.CatalogServiceGrpc
                    .newBlockingStub(channel)
                    .withDeadlineAfter(1, TimeUnit.SECONDS);

            var response = currentStub.getProduct(
                com.acme.catalog.server.current.GetProductRequest.newBuilder()
                    .setProductId("p-42")
                    .setLocale("vi-VN")
                    .build());

            assertEquals("p-42", response.getProductId());
            assertEquals("Keyboard", response.getName());
            assertFalse(response.hasDisplayName());
            assertEquals("", response.getDisplayName());
        } finally {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }
}
~~~

The older server ignores the unrecognized `locale` field and returns a response without tag 3. The new client must have a sensible fallback when `display_name` is absent. Use `optional` if the application needs to distinguish an absent field from a default value; for fields without presence, the default value may not distinguish those two situations.

Both tests above use in-process transport to test protobuf serialization, gRPC method paths, and generated stubs. If old and new fixtures are built in separate modules, you can run the same contract test over loopback Netty to verify the real transport and published dependency artifacts.

## 7. Enums, `oneof`, and Field Presence

Adding an enum value is usually a wire-compatible change, yet older clients must handle unrecognized values:

~~~proto
enum ProductState {
  PRODUCT_STATE_UNSPECIFIED = 0;
  PRODUCT_STATE_ACTIVE = 1;
  PRODUCT_STATE_ARCHIVED = 2;
  // Added in new version:
  PRODUCT_STATE_PENDING_REVIEW = 3;
}
~~~

Older Java clients may receive unknown numeric enums as `UNRECOGNIZED`. Do not write switches assuming only known values exist without a fallback branch. If the enum is persisted long-term, keep numeric values unchanged and never reuse deleted values.

With `oneof`, only one member can be present at a time. Adding a new member can cause older clients not to recognize the new selection; clients must handle `getChoiceCase()` returning `CHOICE_NOT_SET` or unknown fields. Never silently move existing fields into or out of a `oneof` because presence semantics change.

For proto3 scalars, use `optional` when you need to distinguish an absent field from a default value. Contract tests must check both `hasField()` and the getter value if business logic depends on presence.

## 8. Schema Breaking Checks in CI

Runtime contract tests prove real client/server pairs work. Add schema diffs to catch breaking changes before compilation or deployment. Buf can compare the current schema against a released baseline:

~~~bash
buf lint proto
buf breaking proto --against '.git#branch=main'
~~~

The `buf breaking` command uses the repository's breaking rules configuration and the schema on the baseline branch. CI should pin the Buf version, inspect the right module directory, and ensure the baseline is a released contract rather than an arbitrary commit.

Schema checks do not replace integration contract tests: they do not verify Spring wiring, interceptors, authorization, status mapping, TLS, proxy trailers, or business semantics.

## 9. Versioning gRPC Service Paths

When a genuine breaking change is required, create a new package version:

~~~proto
package acme.catalog.v2;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}
~~~

The v2 method path becomes:

~~~text
/acme.catalog.v2.CatalogService/GetProduct
~~~

The server can register both v1 and v2 services concurrently during the transition period. Clients upgrade in waves; monitor v1 traffic and only retire v1 when no valid consumers remain. Never reuse the `v1` name for a schema with incompatible semantics.

## 10. Error Details Are Also Part of the Contract

If the API uses `google.rpc.Status` and `Any` to return rich errors, versioning tests must verify:

- Status codes preserve their semantics across versions.
- Detail type URLs remain stable if the detail type is retained.
- Field numbers inside detail messages are neither changed nor reused.
- Older clients ignore new detail types and still handle the basic status.
- Adding optional fields to details does not cause older clients to fail parsing.

Changing the proto package or message name of a detail alters the type URL inside `Any`; older clients may fail to unpack it. When needing to change a detail schema, keep the old type during the compatibility window or release a new type/version while maintaining fallback statuses.

## 11. Versioning Contract Test Matrix

| Client | Server | Key Checks |
| --- | --- | --- |
| v1 | v1 | Baseline contract and current semantics |
| v1 | new/additive | Old client parses new response, ignores new fields |
| new/additive | v1 | New client tolerates absent response fields |
| v1 | breaking v2 | Do not assume compatibility; v1 path must still be served or migration must be announced |
| new | new | Field presence, enum, `oneof`, and error detail semantics |
| Old client | Server with new details | Fallback status when detail type is unknown |

Besides statuses and responses, check deadlines, metadata, authentication/authorization, and retry behavior if they belong to the RPC's public contract.

## 12. Takeaways and Self-Check

**Versioning contract testing** verifies that clients and servers at different versions still adhere to the same wire contract. Keep proto packages, service/method paths, field numbers, and existing field semantics unchanged; add new fields additively, reserve deleted tags, and handle unknown enum/detail types. Use bidirectional old-client/new-server and new-client/old-server tests alongside schema breaking checks in CI.

Self-Check:

1. How does `java_package` differ from the Protobuf `package` with respect to the gRPC method path?
2. Why must deleted field numbers never be reused?
3. Which two classes of bugs do bidirectional old-client/new-server and new-client/old-server tests catch?
4. Why does adding an enum value still require a client fallback?
5. When should you create a `v2` package instead of editing `v1`?
6. Why does a Buf breaking check not replace contract tests using generated stubs?

Versioning contract testing helps Spring gRPC execute rolling upgrades safely, catch wire/API contract-breaking changes early, and keep clients and servers compatible throughout the upgrade process.
