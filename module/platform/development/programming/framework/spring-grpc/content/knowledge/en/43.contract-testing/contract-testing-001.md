# Proto-Based Contract Testing

In Spring gRPC, the `.proto` file is the public contract between client and server: it defines the package, service, RPC methods, request/response types, and wire data layout. A Java change can compile successfully yet still break the contract with previously released clients. Proto-based contract testing verifies the schema, compatibility, and behavior committed to by both sides.

A reliable workflow combines three layers: static schema checks, generated descriptor/code checks, and running RPCs against a real provider in a test environment. Comparing `.proto` files alone does not prove the server implements them correctly; calling the server only with internal tests does not catch every wire-incompatible change. This lesson explains how to combine those layers for unary and streaming RPCs in the Spring gRPC ecosystem.

## 1. What Does a Proto Contract Include?

Example of a service:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_multiple_files = true;
option java_package = "com.myshop.catalog.v1";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (Product);
  rpc WatchProduct(WatchProductRequest) returns (stream ProductEvent);
}

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string display_name = 2;
  int32 available_quantity = 3;
}

message WatchProductRequest {
  string product_id = 1;
}

message ProductEvent {
  string event_id = 1;
  int64 sequence = 2;
  string state = 3;
  string product_id = 4;
}
```

The contract includes:

- **Identity:** protobuf package, service name, and method name. The full method name of the RPC is `shop.catalog.v1.CatalogService/GetProduct`.
- **Message schema:** field number, wire type, cardinality, presence, enum number, `oneof`, map, and nested types.
- **RPC shape:** unary, server streaming, client streaming, or bidirectional streaming.
- **Generated API:** method/stub names and Java types generated from proto.
- **Behavioral expectations:** status, validation, ordering, idempotency, deadline, authorization, and stream semantics.

Proto defines data structures and RPC shapes, but does not by itself fully describe all business behaviors. Commitments such as returning `NOT_FOUND` when a product does not exist, ensuring sequences increase monotonically, or when a stream ends need to be recorded as expectations and tested separately.

## 2. Three Layers of Contract Testing

| Layer | What It Checks | Best at Catching |
| --- | --- | --- |
| Schema compatibility | Compares current proto against a baseline version | Changed field numbers, deleted unreserved fields, changed RPC shapes |
| Descriptor/generated contract | Inspects service/method/types in descriptor and generated code | Wrong package, missing method, unexpected request/response types |
| Provider behavior | Calls provider via generated stub and checks results | Server returning wrong fields, status, stream order, or terminal behavior |

Consumer-side tests also play a role: they confirm the client can construct requests according to the contract and handle the responses/statuses promised by the provider. With multiple consumers, store meaningful expectations and run them against the provider in CI. Avoid testing only the implementation details of a single specific client.

## 3. Protobuf Compatibility Rules

Protocol Buffers uses field numbers to identify fields on the wire. Field names matter for source/API and JSON mapping, while field numbers along with wire types determine how binary data is decoded.

| Change | Assessment | How to Handle |
| --- | --- | --- |
| Add field with a new number | Usually wire-compatible | Define default/presence and semantics when old clients ignore the field |
| Delete field | Can break if number/name is reused | Reserve both the deleted number and name |
| Change field number | Breaking | Do not change already-released numbers |
| Change field type | May change wire type or semantics | Check specific compatibility rules; treat as breaking by default for public APIs |
| Add enum value | Usually wire-compatible | Consumers must handle unknown enum values |
| Change enum number or reuse deleted number | Breaking | Keep numbers stable, reserve deleted numbers/names |
| Change package/service/method | May change full RPC path | Treat as an endpoint contract change |
| Change unary to streaming or vice versa | Breaking | Create a new method/version if needed |
| Change method request/response type | Usually breaking | Keep the old method or release a new method |

Example when deleting a field:

```proto
message Product {
  string product_id = 1;
  reserved 2;
  reserved "legacy_name";
  int32 available_quantity = 3;
}
```

Never reuse an already-released field number, even when the old field is no longer used by current code. An older client may still send data carrying that number; reusing it causes the same bytes to be interpreted with a new meaning.

Adding a field is usually wire-compatible because older readers ignore unknown fields, but it is not necessarily business-compatible. If a new client requires that field to always have a value that an older server does not send, the schema may be valid while the workflow still breaks. Contract tests need to verify both compatibility and semantic assumptions.

## 4. Using Buf for Schema Checks in CI

Buf provides linting and breaking-change detection for protobuf. A project needs a Buf configuration suited to its proto layout and the organization's versioning rules.

Example commands in a pipeline:

```bash
buf lint
buf breaking --against '.git#branch=main'
```

`buf lint` checks style and structural errors against a rule set. `buf breaking` compares the current schema against a baseline to detect changes violating the configured compatibility level. Choose breaking rules according to release policy; different strictness levels may block changes the team intentionally allows or miss risks the team needs to control.

The baseline must be a released contract or a stable branch chosen as the reference point, not a temporary file from the same build. When releasing a new version, update the baseline through the review process. Do not bypass breaking checks just to keep the pipeline green; if breaking compatibility is necessary, release a new method/package version and plan consumer migration.

## 5. Generating a Descriptor Set as a Contract Artifact

A descriptor set contains the compiled schema description, which can be stored alongside artifacts for tests or other tools to inspect. For example:

```bash
protoc \
  -I src/main/proto \
  --include_imports \
  --descriptor_set_out=build/contracts/catalog.pb \
  src/main/proto/shop/catalog/v1/catalog.proto
```

`--include_imports` includes descriptors of proto dependencies in the artifact. `--include_source_info` can be added if tools need source locations/comments; there is no need to enable it if only checking contract structure.

Descriptor sets are useful for:

- Verifying services/methods and request/response types in published artifacts.
- Comparing contract artifacts between two versions.
- Verifying that client/server are built from the expected contract version.
- Providing schemas to test tools or an internal registry.

You should not compare raw bytes of two descriptor sets as the sole compatibility criterion. Ordering, source info, or options can make artifacts differ byte-for-byte even when semantics have not changed. Use a descriptor-aware diff or a breaking checker that understands protobuf semantics.

## 6. Checking Generated Descriptors and RPC Identity

Generated Java code includes descriptors reflecting the compiled schema. A test can verify package, service, method, and RPC type:

```java
import com.google.protobuf.Descriptors;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class CatalogProtoContractTest {
    @Test
    void exposesExpectedServiceAndMethods() {
        Descriptors.ServiceDescriptor service =
                CatalogProto.getDescriptor()
                        .findServiceByName("CatalogService");
        assertNotNull(service);
        assertEquals("shop.catalog.v1.CatalogService",
                service.getFullName());

        Descriptors.MethodDescriptor getProduct =
                service.findMethodByName("GetProduct");
        assertNotNull(getProduct);
        assertEquals("shop.catalog.v1.GetProductRequest",
                getProduct.getInputType().getFullName());
        assertEquals("shop.catalog.v1.Product",
                getProduct.getOutputType().getFullName());
        assertFalse(getProduct.isClientStreaming());
        assertFalse(getProduct.isServerStreaming());

        Descriptors.MethodDescriptor watch =
                service.findMethodByName("WatchProduct");
        assertNotNull(watch);
        assertTrue(watch.isServerStreaming());
    }
}
```

`CatalogProto` is an illustrative outer descriptor class name; the actual name depends on `java_outer_classname` or the project's protoc rules. This test confirms that generated code carries the expected schema. It does not prove the provider registered the method or returns the right behavior; a provider integration test is needed in the next step.

## 7. Provider Contract Testing with an In-Process Server

In-process transport allows calling the real service in tests without opening a TCP port. Tests use the same generated stub as clients, so they verify request/response types, status, and gRPC runtime serialization:

```java
class CatalogProviderContractTest {
    private Server server;
    private ManagedChannel channel;
    private CatalogServiceGrpc.CatalogServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String name = InProcessServerBuilder.generateName();
        server = InProcessServerBuilder.forName(name)
                .directExecutor()
                .addService(new CatalogGrpcService(testCatalog()))
                .build()
                .start();
        channel = InProcessChannelBuilder.forName(name)
                .directExecutor()
                .build();
        stub = CatalogServiceGrpc.newBlockingStub(channel)
                .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        channel.shutdownNow();
        server.shutdownNow();
        channel.awaitTermination(1, TimeUnit.SECONDS);
        server.awaitTermination(1, TimeUnit.SECONDS);
    }

    @Test
    void getProductReturnsContractFields() {
        Product response = stub.getProduct(
                GetProductRequest.newBuilder()
                        .setProductId("P-100")
                        .build());
        assertEquals("P-100", response.getProductId());
        assertEquals("Keyboard", response.getDisplayName());
        assertTrue(response.getAvailableQuantity() >= 0);
    }

    @Test
    void unknownProductUsesNotFoundStatus() {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getProduct(
                        GetProductRequest.newBuilder()
                                .setProductId("missing")
                                .build()));
        assertEquals(Status.Code.NOT_FOUND,
                error.getStatus().getCode());
    }
}
```

The helpers `testCatalog()` and `CatalogGrpcService` represent test fixtures/service implementations. In a Spring integration test, you can start the application context with the real Spring-configured server and call it through a test channel; the goal is to verify interceptors, dependency injection, and service registration all work as in the application environment.

`directExecutor()` is useful for keeping in-process tests simple and deterministic, but it does not simulate production thread scheduling or network behavior. Do not use results from this test to conclude that TLS, load balancing, deadlines over the network, or backpressure have been verified.

## 8. Contract Testing for Streaming RPCs

For `WatchProduct`, the contract is not just the response type. You need to verify:

- A valid request starts the stream properly.
- Events carry the expected product ID and schema fields.
- Sequences increase according to published rules.
- Message order is preserved if the API promises an ordered stream.
- The stream completes or errors with the right status.
- Cancellation stops the producer and releases resources.

A blocking stub for server streaming returns an `Iterator`:

```java
Iterator<ProductEvent> events = stub.watchProduct(
        WatchProductRequest.newBuilder()
                .setProductId("P-100")
                .build());

long previousSequence = 0;
while (events.hasNext()) {
    ProductEvent event = events.next();
    assertEquals("P-100", event.getProductId());
    assertTrue(event.getSequence() > previousSequence);
    previousSequence = event.getSequence();
}
```

For client streaming and bidirectional streaming, use an async stub and observers. Tests must have finite timeouts/latches and verify message count, ordering, terminal status, and cancellation. Do not use an infinite stream in contract tests; define a clear termination condition so the test always releases the channel/server.

If the contract publishes deadline and cancellation semantics, test them as part of RPC behavior. For example, the client sets a short deadline on an intentionally slow-emitting stream and verifies the client receives `DEADLINE_EXCEEDED`; when the client actively cancels, the client typically observes `CANCELLED` and the provider must stop emitting and release resources. The server typically observes cancellation via the call context/`ServerCallStreamObserver`; do not assume both sides always observe the exact same status code in every race between deadline and transport cancellation.

## 9. Consumer Expectations and Version Compatibility

Consumer contract tests should describe what the client actually needs, rather than duplicating the provider's entire implementation:

| Consumer Expectation | Provider Verification |
| --- | --- |
| Client sends a valid `product_id` | Provider reads the field correctly and returns the expected product |
| Client handles unknown fields | New provider adds fields that old clients can ignore |
| Client handles unknown enum values | Provider can emit new enum values without crashing consumers |
| Client expects `NOT_FOUND` for missing IDs | Provider returns the committed status |
| Client expects an ordered stream | Provider preserves the published sequence order |
| Client sets a short deadline | Client receives `DEADLINE_EXCEEDED` when the server does not finish in time |
| Client actively cancels the stream | Provider stops the emitter and releases resources |

During a rollout, old client/new server and new client/old server may coexist simultaneously. Build a version matrix to test the critical pairs:

- Current running client version with the new server version.
- New client with old server during a rolling deployment.
- Slow-upgrading consumers or third parties using a released contract.

Compatibility tests do not replace migration and rollout testing. If an incompatible change is unavoidable, release a new package/service version, maintain the old method during the transition period, and monitor consumers before deprecating and removing it.

## 10. Integrating Contract Tests into CI and Checklist

A pipeline typically runs in this order:

1. Lint proto and check for breaking changes against the baseline.
2. Generate Java code and descriptor sets from the reviewed proto.
3. Compile consumer/provider modules to detect discrepancies in the generated API.
4. Run descriptor contract tests.
5. Run provider integration tests for unary, streaming, and status handling.
6. Run Spring integration tests for wiring/interceptors/configuration.
7. Store the contract artifact/version alongside the release so consumers can identify the schema used.

Checklist:

- [ ] Proto package, service, method, and RPC cardinality are reviewed.
- [ ] Deleted field numbers/names are reserved; numbers are never reused.
- [ ] Enum numbers are stable and consumers handle unknown values.
- [ ] Buf lint and breaking checks run against the right baseline.
- [ ] Descriptor/generated contracts confirm full method names and types.
- [ ] Provider tests call via generated stubs and check responses and gRPC statuses.
- [ ] Streaming tests verify message count/order/terminal state/cancellation.
- [ ] Tests have finite deadlines and timeouts to prevent pipeline hangs.
- [ ] Spring integration tests verify services and interceptors are registered.
- [ ] A client/server compatibility matrix exists for rolling deployments.
- [ ] Contract artifacts are versioned and traceable to releases.

**Self-Check**

**Question 1.** Why is compiling proto alone not enough to verify a contract?

*Answer:* Compilation only confirms the schema can generate code. It does not prove the change is compatible with older consumers or that the provider returns the right statuses, data, and stream semantics.

**Question 2.** Why should deleted field numbers not be reused?

*Answer:* Older clients may still send that field number. Reusing it causes old bytes to be interpreted as a new field with a different meaning; deleted numbers and names must be reserved.

**Question 3.** How do descriptor tests and provider behavior tests differ?

*Answer:* Descriptor tests check the service/methods/types generated from proto; provider tests call real RPCs via generated stubs to verify responses, statuses, and streaming behavior.

**Question 4.** Why do in-process tests not replace deployment tests?

*Answer:* In-process tests do not simulate TCP/TLS, load balancing, network failures, or real-world scheduling. They verify contract behavior at the service/runtime level in a test environment.

**Question 5.** What else must a streaming RPC contract verify besides message types?

*Answer:* Message count and ordering, sequence, terminal status, completion conditions, cancellation, and deadlines.

Proto-based contract testing creates a guardrail between schema and provider behavior: schema checkers protect wire compatibility, descriptor tests protect RPC identity, while integration tests prove the server fulfills consumer expectations. Combining these layers in CI helps Spring gRPC catch breaking changes before a new contract reaches running clients.
