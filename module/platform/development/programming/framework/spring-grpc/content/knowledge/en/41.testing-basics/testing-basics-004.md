# Checking generated requests and responses

**Chapter:** Testing basics  
**Scope:** Spring gRPC (SPRING_GRPC) using Protocol Buffers contracts, generated Java code, and client/server implementations for unary or streaming RPCs. This lesson focuses on how to test generated protobuf requests and responses in unit tests, serialization tests, and in-process gRPC tests. The goal is to ensure application code constructs, reads, and exchanges messages according to the defined contract.

## 1. Why check generated requests and responses?

Protocol Buffers generates Java message classes from `.proto` files. Generated classes provide builders, getters, parsers, enums, and APIs for repeated/oneof fields. There is no need to write unit tests to prove `protoc` generates valid getters or builders; what needs testing is that the application uses the generated types according to the contract's semantics.

Common bugs appear where the application creates or reads messages:

- A proto3 field without presence is confused with a field explicitly sent with a default value.
- A present optional field with an empty value is treated as unsent.
- A repeated field loses elements or changes order.
- A oneof branch with false, zero, or an empty string is treated as unselected.
- A new numeric enum value is silently converted into the default value.
- A Timestamp/Duration loses precision during conversion.
- A builder is mutated after building and the test author assumes the built message changed too.
- A message serialized and parsed back does not retain data required by the contract.

Checking generated requests and responses protects the contract at the gRPC boundary, especially when multiple clients and servers run across different versions.

## 2. Choosing the right testing layer

| Test type | What to verify | Is a gRPC server needed? |
| --- | --- | --- |
| Generated message unit test | Defaults, presence, oneof, repeated, enum, equality, and immutability | No |
| Serialization test | Message encode/decode over protobuf wire format | No |
| Mapper test | Application model converts accurately to/from request/response | No |
| In-process gRPC test | Generated stub, service base, request/response, and status via gRPC runtime | Yes, using an in-process server |
| Transport integration test | HTTP/2, Netty, TLS, metadata, and real server configuration | Yes |

Do not use an in-process test to conclude that TLS, the Netty event loop, or load balancing works. Conversely, there is no need to start a Spring context to test a generated message builder.

## 3. Protobuf contract used in the examples

The example Catalog service has a request with an optional field, a repeated field, and a oneof; the response has an enum, Timestamp, repeated field, and oneof:

~~~proto
syntax = "proto3";

import "google/protobuf/timestamp.proto";

package catalog.v1;
option java_package = "com.example.catalog.grpc";
option java_multiple_files = true;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (ProductResponse);
}

message GetProductRequest {
  string product_id = 1;
  optional string locale = 2;
  repeated string expand = 3;
  oneof selector {
    string sku = 4;
    int64 legacy_id = 5;
  }
}

enum ProductState {
  PRODUCT_STATE_UNSPECIFIED = 0;
  PRODUCT_STATE_ACTIVE = 1;
  PRODUCT_STATE_ARCHIVED = 2;
}

message ProductResponse {
  string product_id = 1;
  string display_name = 2;
  ProductState state = 3;
  optional string description = 4;
  repeated string tags = 5;
  google.protobuf.Timestamp updated_at = 6;
  oneof source {
    string supplier_code = 7;
    int64 import_batch_id = 8;
  }
}
~~~

With java_multiple_files, the plugin generates separate message classes in the declared package, along with CatalogServiceGrpc containing the service base and stubs. Tests should import the actual generated types from the project's source set.

## 4. Creating generated requests with builders

Generated messages are immutable. Build a message using its builder, set the fields, and call build():

~~~java
GetProductRequest request = GetProductRequest.newBuilder()
        .setProductId("product-42")
        .setLocale("vi-VN")
        .addExpand("price")
        .addExpand("inventory")
        .setSku("SKU-42")
        .build();
~~~

In tests, builders make input data explicit. Do not mock generated requests because mocks cannot faithfully represent parser behavior, default values, field presence, oneof cases, and unknown fields of the protobuf runtime.

## 5. Checking default values and field presence

For plain proto3 scalars, getters return the default value if the field was not sent. For optional fields, the generated API provides a has-method to distinguish:

~~~java
@Test
void distinguishesAbsentOptionalFieldFromPresentEmptyValue() {
    GetProductRequest absent = GetProductRequest.newBuilder()
            .setProductId("product-1")
            .build();

    GetProductRequest presentEmpty = absent.toBuilder()
            .setLocale("")
            .build();

    assertFalse(absent.hasLocale());
    assertEquals("", absent.getLocale());

    assertTrue(presentEmpty.hasLocale());
    assertEquals("", presentEmpty.getLocale());
}
~~~

Both requests return an empty string from getLocale(), yet only the second request has presence. If the API uses this field to decide whether to override a default locale, that difference matters.

For non-optional scalars, there is no has-method in standard proto3. If the application needs to distinguish unsent from sending zero/false/empty, design the schema with optional or oneof and test presence accordingly.

## 6. Checking repeated fields and order

Repeated fields may be empty or contain multiple elements. The generated API provides list getters and count/index getters:

~~~java
@Test
void preservesRepeatedFieldOrder() {
    GetProductRequest request = GetProductRequest.newBuilder()
            .addExpand("price")
            .addExpand("inventory")
            .addExpand("images")
            .build();

    assertEquals(3, request.getExpandCount());
    assertEquals(
            List.of("price", "inventory", "images"),
            request.getExpandList());
    assertEquals("inventory", request.getExpand(1));
}
~~~

Do not assert only the element count. Test both content and order if order is meaningful in the contract. Lists returned by generated messages are immutable; when mutation is needed, create a new collection.

## 7. Checking oneof, including default values

Do not infer the oneof branch from getters because a branch may be selected with an empty or zero value. Check the generated case enum:

~~~java
@Test
void distinguishesOneofBranchFromUnsetBranch() {
    GetProductRequest unset = GetProductRequest.newBuilder().build();
    GetProductRequest emptySku = GetProductRequest.newBuilder()
            .setSku("")
            .build();
    GetProductRequest zeroLegacyId = GetProductRequest.newBuilder()
            .setLegacyId(0)
            .build();

    assertEquals(
            GetProductRequest.SelectorCase.SELECTOR_NOT_SET,
            unset.getSelectorCase());
    assertEquals(
            GetProductRequest.SelectorCase.SKU,
            emptySku.getSelectorCase());
    assertEquals(
            GetProductRequest.SelectorCase.LEGACY_ID,
            zeroLegacyId.getSelectorCase());
}
~~~

This test protects "branch was selected" semantics even when the value equals the default. Protobuf guarantees at most one branch in the same oneof is active; when the builder sets another branch, the previous one is cleared.

## 8. Checking enums and unknown numeric values

Proto3 enums use the first zero value as default. Generated enum accessors return UNRECOGNIZED when a wire message carries a numeric value unknown to the current code version. With the generated Java API, the numeric accessor preserves the raw value:

~~~java
@Test
void preservesUnknownEnumNumericValue() {
    ProductResponse response = ProductResponse.newBuilder()
            .setStateValue(99)
            .build();

    assertEquals(ProductState.UNRECOGNIZED, response.getState());
    assertEquals(99, response.getStateValue());
}
~~~

This is the difference between an unknown enum value and an unknown field. The enum field still has a declared field number; only the numeric enum value is unrecognized by the current server/client version. An unknown field is a field number not declared in the current schema.

Tests should reflect application policy: preserve the numeric value for forward compatibility, or reject it when mapping to an application enum. Do not silently turn UNRECOGNIZED into PRODUCT_STATE_UNSPECIFIED if the two carry different semantics.

## 9. Checking Timestamp and response presence

Protobuf Timestamp has seconds and nanos. When converting to Instant, do not convert via milliseconds if nanosecond precision must be preserved:

~~~java
@Test
void preservesTimestampNanosecondPrecision() {
    Timestamp timestamp = Timestamp.newBuilder()
            .setSeconds(1_800_000_000L)
            .setNanos(123_456_789)
            .build();

    ProductResponse response = ProductResponse.newBuilder()
            .setProductId("product-7")
            .setUpdatedAt(timestamp)
            .setDescription("")
            .build();

    assertTrue(response.hasUpdatedAt());
    assertEquals(timestamp, response.getUpdatedAt());
    assertTrue(response.hasDescription());
    assertEquals("", response.getDescription());
}
~~~

Message fields such as Timestamp have their own presence. Optional strings also distinguish absent from present-empty. Response tests should verify that the server returns this distinction accurately if clients rely on it.

When converting Timestamp to java.time.Instant, check seconds and nanos explicitly. Invalid timestamps should be rejected per validation policy; the generated builder does not automatically guarantee all seconds/nanos lie within the valid Timestamp range.

## 10. Checking message immutability

After calling build(), a message does not change when the builder is modified afterward:

~~~java
@Test
void builtMessageIsImmutableSnapshot() {
    GetProductRequest.Builder builder =
            GetProductRequest.newBuilder()
                    .setProductId("product-before");

    GetProductRequest first = builder.build();
    builder.setProductId("product-after");
    GetProductRequest second = builder.build();

    assertEquals("product-before", first.getProductId());
    assertEquals("product-after", second.getProductId());
    assertNotEquals(first, second);
}
~~~

This property is useful when an adapter builds requests/responses and passes them across layers. Never keep a mutable builder shared across RPCs or across threads.

## 11. Serialization round-trip

Protobuf messages are serialized into wire bytes and parsed back using the generated class's parser. Round-trip tests verify that contract data is preserved:

~~~java
@Test
void requestSurvivesProtobufBinaryRoundTrip() throws Exception {
    GetProductRequest original = GetProductRequest.newBuilder()
            .setProductId("product-42")
            .setLocale("vi-VN")
            .addExpand("price")
            .addExpand("inventory")
            .setLegacyId(0)
            .build();

    byte[] bytes = original.toByteArray();
    GetProductRequest parsed = GetProductRequest.parseFrom(bytes);

    assertEquals(original, parsed);
    assertTrue(parsed.hasLocale());
    assertEquals(
            GetProductRequest.SelectorCase.LEGACY_ID,
            parsed.getSelectorCase());
    assertEquals(0L, parsed.getLegacyId());
}
~~~

Protobuf message equality compares message contents, including fields and unknown fields. This test needs no gRPC channel; it verifies protobuf wire serialization/parsing.

Responses also need round-trip tests if the application has complex response mappings:

~~~java
@Test
void responseSurvivesBinaryRoundTrip() throws Exception {
    ProductResponse original = ProductResponse.newBuilder()
            .setProductId("product-42")
            .setDisplayName("Keyboard")
            .setState(ProductState.PRODUCT_STATE_ACTIVE)
            .addTags("featured")
            .setSupplierCode("supplier-A")
            .build();

    ProductResponse parsed =
            ProductResponse.parseFrom(original.toByteArray());

    assertEquals(original, parsed);
    assertEquals(
            ProductResponse.SourceCase.SUPPLIER_CODE,
            parsed.getSourceCase());
}
~~~

## 12. Unknown fields and forward compatibility

Protobuf's binary format lets parsers preserve unknown fields so messages can be forwarded across different schema versions. You can synthesize an undeclared field number using CodedOutputStream:

~~~java
import com.google.protobuf.CodedOutputStream;
import java.io.ByteArrayOutputStream;
import java.util.Arrays;

@Test
void retainsUnknownFieldWhenParsingAndReserializing() throws Exception {
    GetProductRequest known = GetProductRequest.newBuilder()
            .setProductId("product-9")
            .build();

    ByteArrayOutputStream unknownBytes = new ByteArrayOutputStream();
    CodedOutputStream coded = CodedOutputStream.newInstance(unknownBytes);
    coded.writeUInt64(99, 7L);
    coded.flush();

    byte[] knownBytes = known.toByteArray();
    byte[] wireBytes = Arrays.copyOf(
            knownBytes,
            knownBytes.length + unknownBytes.size());
    System.arraycopy(
            unknownBytes.toByteArray(),
            0,
            wireBytes,
            knownBytes.length,
            unknownBytes.size());

    GetProductRequest parsed = GetProductRequest.parseFrom(wireBytes);
    assertTrue(parsed.getUnknownFields().hasField(99));
    assertEquals(
            7L,
            parsed.getUnknownFields()
                    .getField(99)
                    .getVarintList()
                    .get(0));

    GetProductRequest reparsed =
            GetProductRequest.parseFrom(parsed.toByteArray());
    assertTrue(reparsed.getUnknownFields().hasField(99));
}
~~~

Do not strip unknown fields if the message acts as a proxy/relay that needs to forward data from newer clients to newer services. Conversely, if the application maps a message to an application model and builds a new message, unknown fields may not be retained; clearly identify which components require forward compatibility.

Unknown fields in binary protobuf do not mean a JSON parser must keep every unknown key in the same way. JSON mapping rules and binary wire format rules differ; test according to the serialization format the system actually uses.

## 13. Malformed payloads and parser failures

Generated parsers reject payloads that violate the wire format. For example, a length-delimited field declaring more bytes than actually follow:

~~~java
@Test
void rejectsTruncatedProtobufPayload() {
    byte[] truncated = new byte[] {
            0x0A, // field 1, wire type 2
            0x05, // length declares five bytes
            0x41  // only one byte follows
    };

    assertThrows(
            InvalidProtocolBufferException.class,
            () -> GetProductRequest.parseFrom(truncated));
}
~~~

This is a parser test. In a real RPC, the gRPC runtime parses the message before calling the service handler; malformed payloads can fail the RPC without the adapter ever being invoked. Do not rely on parser failure as a substitute for validating a message that parsed successfully but contains invalid values.

## 14. Testing generated stubs with an in-process gRPC server

Message unit tests do not verify that the generated client stub invokes the right service method. An in-process test can combine generated requests, generated stubs, and the service base without opening sockets:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import org.junit.jupiter.api.Test;

class CatalogGeneratedStubTest {

    @Test
    void generatedStubExchangesGeneratedRequestAndResponse()
            throws Exception {
        String serverName = InProcessServerBuilder.generateName();
        ProductResponse expected = ProductResponse.newBuilder()
                .setProductId("product-42")
                .setDisplayName("Mechanical keyboard")
                .setState(ProductState.PRODUCT_STATE_ACTIVE)
                .build();

        CatalogServiceGrpc.CatalogServiceImplBase service =
                new CatalogServiceGrpc.CatalogServiceImplBase() {
                    @Override
                    public void getProduct(
                            GetProductRequest request,
                            StreamObserver<ProductResponse> observer) {
                        assertEquals("product-42", request.getProductId());
                        observer.onNext(expected);
                        observer.onCompleted();
                    }
                };

        Server server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(service)
                .build()
                .start();
        ManagedChannel channel = InProcessChannelBuilder
                .forName(serverName)
                .directExecutor()
                .build();

        try {
            GetProductRequest request = GetProductRequest.newBuilder()
                    .setProductId("product-42")
                    .build();
            ProductResponse actual =
                    CatalogServiceGrpc.newBlockingStub(channel)
                            .getProduct(request);

            assertEquals(expected, actual);
        } finally {
            channel.shutdownNow();
            server.shutdownNow();
        }
    }
}
~~~

In-process tests verify generated stubs, method binding, and message exchange through the gRPC runtime. They do not replace Netty/HTTP2/TLS integration tests because the in-process transport does not open TCP sockets.

## 15. Organizing JUnit 5 tests

Generated message tests are typically pure Java tests:

~~~java
import org.junit.jupiter.api.Test;

class GeneratedProductMessageTest {
    // Build generated messages with builders and assert semantics.
}
~~~

You do not need `@SpringBootTest` or Mockito if you are only testing builders, parsers, and equality. When testing mappers, instantiate the real mapper. When testing stub/service registration, use an in-process gRPC server. Keep each test focused on a single contract behavior so failures are easy to diagnose.

Typical test dependencies include:

- JUnit Jupiter for test lifecycle and assertions.
- Protobuf Java runtime used by generated code.
- gRPC in-process transport if testing generated stubs.
- Mockito only when mocking application dependencies in adapter tests.

The protobuf runtime version, protoc plugin, and gRPC artifacts must match the module's BOM/build conventions. Never upgrade the protobuf runtime independently just to make a single test compile.

## 16. Test matrix for generated requests and responses

| Group | Important cases |
| --- | --- |
| Scalar/default | Unsent, sent with default value, sent with normal value |
| Optional | Absent, present-empty, present-non-empty |
| Repeated | Empty, single element, multiple elements and order |
| Oneof | Unset, each branch, branch with zero/empty value |
| Enum | Each known enum, unspecified, unknown numeric value |
| Timestamp/Duration | Presence, seconds/nanos, boundary values |
| Immutability | Modifying builder after build does not alter built message |
| Serialization | Request/response binary round-trip |
| Unknown field | Parse and reserialize retains unknown fields when needed |
| Malformed payload | Parser rejects invalid wire bytes |
| Generated stub | Request reaches the right service method, response returns expected type |

Select cases based on the real schema. There is no need to test every generated getter if there are no special semantics; focus on field presence, compatibility, and conversions that risk losing data.

## 17. Common anti-patterns

- **Mocking generated messages:** fails to exercise protobuf builder/parser semantics.
- **Asserting only getter values:** misses the difference between absent and present-default.
- **Asserting only repeated count:** fails to catch wrong order or content.
- **Not checking oneof case:** mistakes false/zero/empty values for an unselected branch.
- **Converting Timestamp through milliseconds:** loses nanosecond precision.
- **Dropping unknown fields in relays:** breaks forward compatibility.
- **Testing the parser and concluding the validator works:** parsing and semantic validation are two separate concerns.
- **Using in-process tests to conclude TLS works:** this transport does not perform a TLS handshake over TCP.
- **Starting the full Spring context for message tests:** slows down tests without increasing reliability.

## 18. Self-practice

1. Why should generated protobuf messages be created with real builders in unit tests?
2. Which assertions distinguish an absent optional field from a present-empty one?
3. Write a test proving a oneof branch with value zero is still selected.
4. How do you verify Timestamp does not lose nanoseconds during serialization/parsing?
5. Distinguish an unknown enum numeric value from an unknown field number.
6. When should you test that unknown fields are preserved across parse and reserialize?
7. What can an in-process gRPC test verify, and what can it not verify?

**Remember:** Test generated requests and responses using real messages created from builders; verify defaults/presence, repeated fields, oneof, enums, timestamps, immutability, and binary serialization. Use parser tests for malformed payloads, unknown-field tests for forward compatibility, and in-process gRPC tests for generated stub/service exchange. Keep message semantics, application validation, and transport behavior clearly separated.
