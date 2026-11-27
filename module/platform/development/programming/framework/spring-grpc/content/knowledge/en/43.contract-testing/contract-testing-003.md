# Verifying Request and Response Fields

In Spring gRPC, protobuf defines the structure of requests and responses exchanged between client and server. An RPC can exist and return status `OK` yet still violate the contract if the server reads the wrong field, ignores valid values, or returns a response missing data that consumers rely on. Contract tests for request/response fields verify the meaning of each field at the API boundary: stable field names and numbers, correct data types, properly understood presence/defaults, consistent validation, and responses containing committed values.

You should not test only internal Java objects before serialization. Tests need to construct protobuf requests like a real client, call the provider via the generated stub, and assert on the received protobuf response. Alongside schema-level checks, descriptor tests provide evidence of field numbers/types; provider tests prove data crossing the RPC carries the intended semantics.

## 1. Fields Are Part of the Wire Contract

Catalog contract example:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_multiple_files = true;
option java_package = "com.myshop.catalog.v1";

service CatalogService {
  rpc CreateProduct(CreateProductRequest) returns (Product);
  rpc GetProduct(GetProductRequest) returns (Product);
}

message CreateProductRequest {
  string product_id = 1;
  string display_name = 2;
  int32 initial_quantity = 3;
  repeated string tags = 4;
  optional string description = 5;
}

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string display_name = 2;
  int32 available_quantity = 3;
  repeated string tags = 4;
  optional string description = 5;
  ProductDetails details = 6;
}

message ProductDetails {
  string category = 1;
  string warehouse_id = 2;
}
```

A field has multiple contract properties:

- **Field number:** identifies the field in the binary wire format; never change or reuse already-released numbers.
- **Field type:** string, integer, enum, message, bytes, bool, and other protobuf types.
- **Cardinality:** singular, repeated, or map.
- **Presence:** whether consumers can distinguish an unset field from a field carrying its default value.
- **Meaning:** units, value range, validation rules, and meaning when absent.

Field names can affect the generated Java API and JSON mapping. Field numbers together with wire types affect how binary data is decoded. Contract tests should protect both wire structure and the public behavior consumers depend on.

## 2. Distinguishing Default Values and Field Presence

Regular proto3 scalar fields have implicit presence. When a field is not sent, the getter returns the default value; the application cannot distinguish an absent field from a field explicitly sent with the default value:

```proto
message UpdateProductRequest {
  string product_id = 1;
  int32 available_quantity = 2;
  optional int32 reorder_threshold = 3;
}
```

In Java:

```java
UpdateProductRequest request = UpdateProductRequest.newBuilder()
        .setProductId("P-100")
        .setAvailableQuantity(0)
        .build();

assertEquals(0, request.getAvailableQuantity());
assertFalse(request.hasReorderThreshold());
```

`available_quantity` is an implicit-presence scalar: the getter returns 0 when unset and also returns 0 when the client sets 0. `reorder_threshold` has `optional`, so the generated API provides `hasReorderThreshold()` to distinguish not sending it from sending the value 0.

Singular message fields have presence. Repeated and map fields do not have presence in the way singular optional fields do; an empty collection typically represents no elements. Contract tests must match actual semantics instead of assuming every getter has `hasX()`.

Selection rules:

| Field kind | Common way to read | Meaning when no data is present |
| --- | --- | --- |
| Implicit-presence scalar | `getAvailableQuantity()` | Returns default such as 0, false, or empty string |
| `optional` scalar | `hasReorderThreshold()` and getter | Distinguishes absent from default value |
| Singular message | `hasDetails()` and getter | Can distinguish an unset message |
| Repeated | `getTagsList()` | Empty list when there are no elements |
| Map | `getAttributesMap()` | Empty map when there are no entries |

Do not add `optional` merely to get `hasX()` if the contract does not need to distinguish absent from default. However, if update semantics require knowing whether the caller intentionally set 0, explicit presence is an important part of the API.

## 3. Checking Field Numbers and Types with Descriptors

Descriptor tests catch structural changes that runtime value assertions might miss:

```java
import com.google.protobuf.Descriptors;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ProductFieldContractTest {

    @Test
    void createRequestKeepsPublishedFieldNumbersAndTypes() {
        Descriptors.Descriptor request =
                CreateProductRequest.getDescriptor();

        Descriptors.FieldDescriptor productId =
                request.findFieldByName("product_id");
        assertNotNull(productId);
        assertEquals(1, productId.getNumber());
        assertEquals(Descriptors.FieldDescriptor.Type.STRING,
                productId.getType());

        Descriptors.FieldDescriptor quantity =
                request.findFieldByName("initial_quantity");
        assertNotNull(quantity);
        assertEquals(3, quantity.getNumber());
        assertEquals(Descriptors.FieldDescriptor.Type.INT32,
                quantity.getType());

        Descriptors.FieldDescriptor tags =
                request.findFieldByName("tags");
        assertNotNull(tags);
        assertEquals(4, tags.getNumber());
        assertTrue(tags.isRepeated());
    }
}
```

In the descriptor API, `isOptional()` in examples reflects the field's label/cardinality in the descriptor, not an explicit presence check for every proto3 scalar. If you need to test explicit presence, check `hasPresence()` on protobuf Java versions that support it or verify using the generated `hasReorderThreshold()` and the appropriate oneof/presence API. Avoid using a descriptor attribute to infer semantics that the API does not represent.

Descriptor tests should focus on important public fields: number, type, repeated/map, oneof membership, and presence semantics. There is no need to snapshot the entire descriptor if snapshotting causes harmless comment/option changes to break tests.

## 4. Testing Request Fields at the Provider Boundary

Request tests should use generated messages just like a real client:

```java
CreateProductRequest request = CreateProductRequest.newBuilder()
        .setProductId("P-100")
        .setDisplayName("Keyboard")
        .setInitialQuantity(25)
        .addTags("office")
        .addTags("input")
        .setDescription("Mechanical keyboard")
        .build();

Product response = stub.createProduct(request);

assertEquals("P-100", response.getProductId());
assertEquals("Keyboard", response.getDisplayName());
assertEquals(25, response.getAvailableQuantity());
assertEquals(List.of("office", "input"), response.getTagsList());
assertTrue(response.hasDescription());
assertEquals("Mechanical keyboard", response.getDescription());
```

This test verifies that the provider understands the fields and returns values per the contract. If tag order is meaningful in the API, assert order; if it is only a set, the contract should state so clearly and tests should not enforce an uncommitted order.

You should have separate tests for:

- Business-required fields missing or empty.
- Scalars sent with their default values.
- Optional fields absent vs. present with empty/0 values.
- Repeated fields empty, with one element, and with multiple elements.
- Message fields absent vs. set.
- Boundary values, Unicode, and payloads of valid sizes.

Proto3 has no `required` keyword like proto2. If `product_id` is required for the use case, the service must validate it and return the appropriate status; the schema alone does not guarantee the client set that field.

## 5. Testing Response Fields That Consumers Actually Need

The response contract must ensure the server returns the expected fields and meanings, not just a non-null response:

```java
Product response = stub.getProduct(
        GetProductRequest.newBuilder()
                .setProductId("P-100")
                .build());

assertEquals("P-100", response.getProductId());
assertEquals("Keyboard", response.getDisplayName());
assertEquals(25, response.getAvailableQuantity());
assertTrue(response.hasDetails());
assertEquals("input-devices",
        response.getDetails().getCategory());
```

Assert the fields that constitute the public guarantee consumers need. Do not assert internal fields or unstable values such as randomly generated timestamps, map ordering, or implementation metadata if the contract does not commit to them.

If the response has optional fields, test both absent and present cases if consumers need to distinguish them. If an implicit-presence scalar field returns a default, verify the published default semantics. When a new field is added, older clients typically ignore unknown fields; newer clients calling older servers may see default/absent values, so you must define how consumers handle that case.

## 6. Validation and Statuses for Invalid Request Fields

Request validation should take place at the boundary/application layer before performing side effects. For example:

```java
public void createProduct(
        CreateProductRequest request,
        StreamObserver<Product> observer) {
    if (request.getProductId().isBlank()) {
        observer.onError(Status.INVALID_ARGUMENT
                .withDescription("product_id must not be blank")
                .asRuntimeException());
        return;
    }
    if (request.getInitialQuantity() < 0) {
        observer.onError(Status.INVALID_ARGUMENT
                .withDescription("initial_quantity must be non-negative")
                .asRuntimeException());
        return;
    }

    Product created = catalog.create(request);
    observer.onNext(created);
    observer.onCompleted();
}
```

In production code, validation exceptions may be mapped through a shared exception mapper. Regardless of implementation, contract tests must verify the status and that no side effects occur when the request is invalid.

Example:

```java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.createProduct(
                CreateProductRequest.newBuilder()
                        .setProductId(" ")
                        .setInitialQuantity(1)
                        .build()));

assertEquals(Status.Code.INVALID_ARGUMENT,
        error.getStatus().getCode());
verify(catalogRepository, never()).save(any());
```

Do not use `INTERNAL` for request errors that the client can fix. Status `INVALID_ARGUMENT` is the contract signal indicating an invalid request; the description should be concise, stable, and not leak internal details.

## 7. Complex Fields: oneof, enum, map, and bytes

With `oneof`, only one branch can be present at a time:

```proto
message ProductSelector {
  oneof selector {
    string product_id = 1;
    string sku = 2;
  }
}
```

The generated Java API provides a case enum:

```java
switch (selector.getSelectorCase()) {
    case PRODUCT_ID -> loadById(selector.getProductId());
    case SKU -> loadBySku(selector.getSku());
    case SELECTOR_NOT_SET -> throw new IllegalArgumentException(
            "A product selector is required");
}
```

Contract tests need to verify each branch, the unset state, and that two branches do not coexist after serialization/parsing.

For enums, keep numeric values stable and handle unknown values from newer versions. Java protobuf enums can return `UNRECOGNIZED` for unknown numeric values; `getXValue()` lets you preserve the raw integer when needed. For maps, test keys/values and semantics when a key does not exist. For bytes, test exact binary contents without assuming UTF-8 if the contract defines binary data.

## 8. Unknown Fields and Client/Server Compatibility

Protobuf is designed so readers can ignore unknown fields, allowing new fields to be added while older clients still parse messages. However, newer consumers calling older servers may not receive the new field and must handle default/presence appropriately.

A helpful test matrix:

| Client | Provider | Expectation |
| --- | --- | --- |
| Old | New with added response field | Old client parses and ignores unknown field |
| New with new request field | Old without understanding the field | Old provider ignores unknown field; client does not assume the server applied the new semantics |
| New | New | New field is read/written according to the contract |
| Old | New that retired an old field | Old field number is not reused; transition semantics are defined |

When deleting a field, reserve its number and name. Never reuse field numbers. When adding a field with important presence or default semantics, test compatible consumer/provider versions during rolling deployments. Compatibility checkers like Buf can catch schema changes, yet behavior tests are still needed to verify consumers handle absent/unknown values properly.

Example when removing field `legacy_code`:

```proto
message Product {
  string product_id = 1;
  reserved 2;
  reserved "legacy_code";
  string display_name = 3;
}
```

`reserved` prevents future schemas from accidentally reusing number 2 or name `legacy_code`. During contract reviews, check both deleted numbers and names; do not just delete the field from the file and leave an unprotected slot.

## 9. Testing Fields via In-Process Provider and Spring

An in-process server lets you invoke services using generated stubs, verifying serialization, request mapping, response fields, and status without TCP:

```java
class ProductFieldProviderTest {
    private Server server;
    private ManagedChannel channel;
    private CatalogServiceGrpc.CatalogServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String name = InProcessServerBuilder.generateName();
        server = InProcessServerBuilder.forName(name)
                .addService(new CatalogGrpcService(testCatalog()))
                .build()
                .start();
        channel = InProcessChannelBuilder.forName(name).build();
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
    void mapsRequestFieldsToResponseContract() {
        Product response = stub.createProduct(
                CreateProductRequest.newBuilder()
                        .setProductId("P-200")
                        .setDisplayName("Mouse")
                        .setInitialQuantity(12)
                        .addTags("accessories")
                        .build());

        assertEquals("P-200", response.getProductId());
        assertEquals("Mouse", response.getDisplayName());
        assertEquals(12, response.getAvailableQuantity());
        assertEquals(List.of("accessories"), response.getTagsList());
    }
}
```

The fixture `testCatalog()` and `CatalogGrpcService` are test components of the application. For Spring integration tests, start the application context and call through the real configured server/channel to verify beans, interceptors, validation, and mappers are wired properly. In-process tests do not replace testing TLS, load balancing, or network failures.

## 10. Field Contract Test Checklist

- [ ] Field numbers/types/cardinality match the published contract.
- [ ] Deleted field numbers/names are never reused; old fields are reserved.
- [ ] Implicit presence and explicit presence are properly distinguished.
- [ ] Default values have documented and tested semantics.
- [ ] Repeated/map/message/oneof/enum fields are tested via generated Java APIs.
- [ ] Invalid request fields return an appropriate status such as `INVALID_ARGUMENT`.
- [ ] Valid requests map accurately to the use case.
- [ ] Responses contain all public fields consumers require.
- [ ] Optional/absent/default/unknown fields have compatibility tests.
- [ ] Implementation details or unstable data outside the contract are not asserted.
- [ ] Provider tests via generated stubs and Spring integration tests are present.
- [ ] Tests use finite deadlines/timeouts and clean up channels/servers.

**Self-Check**

**Question 1.** Why can `getAvailableQuantity()` return 0 even when the client did not send the field?

*Answer:* Regular proto3 scalars use implicit presence; getters return the default value when a field is unset. If you need to distinguish absent from setting 0, declare `optional` or use a type with appropriate explicit presence.

**Question 2.** When does generated Java code have `hasDescription()`?

*Answer:* For singular message fields or scalars declared with explicit presence such as `optional`, the generated API provides a presence check. Regular implicit-presence scalars do not have `hasX()`.

**Question 3.** Why should contract tests call the provider using a generated stub?

*Answer:* Doing so tests protobuf request/response handling through gRPC serialization and the real handler, rather than testing only internal objects before transport.

**Question 4.** How should a request missing `product_id` be handled?

*Answer:* Proto3 does not automatically make this scalar string required. The provider must validate it per the contract and typically return `INVALID_ARGUMENT` before performing side effects.

**Question 5.** When adding a new response field, what do older clients need to do?

*Answer:* Older clients typically ignore unknown fields when parsing protobuf. Newer clients calling older servers must handle the new field being absent/default according to presence semantics; do not assume all providers upgrade simultaneously.

Verifying request and response fields must protect both structure and data meaning. Descriptor tests keep numbers/types/presence stable; provider tests via generated stubs verify mapping and validation; compatibility tests ensure older and newer clients handle absent or unknown fields correctly. Combining these layers keeps Spring gRPC contracts clear and safe when deploying multiple versions concurrently.
