# Unit testing protobuf mapping

**Chapter:** Testing basics  
**Scope:** Spring gRPC (`SPRING_GRPC`) using Protocol Buffers contracts, generated Java code, and client/server implementations for unary or streaming RPCs. This lesson focuses on unit testing the mapper layer in a service adapter: converting generated protobuf requests into application-layer commands and converting application results into protobuf responses. The goal is to verify mapping semantics accurately without starting a Spring context, gRPC server, or database.

## 1. Why does a mapper need dedicated unit tests?

The service adapter sits between the gRPC protocol and the application layer. The adapter receives a generated message, converts data to an internal command/model, invokes the use case, and converts the result back into a generated response. Mappers are a place where subtle bugs can occur:

- Unsent fields get turned into default values, losing presence information.
- Values like `false` or `0` are mistaken for an absent field.
- Repeated fields lose elements or change order.
- A new enum from a client is silently converted into the default enum.
- A `oneof` branch is not identified properly.
- Timestamps lose nanosecond precision.
- The mapper returns a mutable collection or retains unwanted references.

Mapper unit tests verify conversion rules quickly, in isolation, and deterministically. The tests do not need to verify gRPC transport; that is the responsibility of integration tests at another layer.

## 2. Distinguishing mapper tests from adapter/integration tests

| Test type | Target | What to verify |
| --- | --- | --- |
| Mapper unit test | Protobuf ↔ application model conversion class | Fields, presence, enum, oneof, collection, and timestamp are mapped correctly |
| Adapter unit test | Generated service implementation | Calls the right mapper/use case and converts results into response/status |
| In-process gRPC test | Stub, channel, server, and interceptor | Request/response/status travel through the gRPC runtime per contract |
| End-to-end test | Real or near-real services and dependencies | Integrated business flows work in the deployment environment |

Mapper tests should run directly on generated messages created via builders. There is no need to initialize `ManagedChannel`, `Server`, or `@SpringBootTest` when you only want to test a pure Java conversion.

## 3. Example protobuf contract

Suppose a service updates a product. The contract uses `optional` to distinguish unsent fields from default values, `repeated` for labels, an enum to categorize products, and `oneof` to select availability status:

~~~proto
syntax = "proto3";

import "google/protobuf/timestamp.proto";

package catalog.v1;
option java_package = "com.example.catalog.grpc";
option java_multiple_files = true;

service ProductService {
  rpc UpdateProduct(UpdateProductRequest)
      returns (ProductResponse);
}

message UpdateProductRequest {
  string product_id = 1;
  optional string display_name = 2;
  optional int64 price_minor_units = 3;
  repeated string labels = 4;
  ProductCategory category = 5;

  oneof availability {
    bool active = 6;
    google.protobuf.Timestamp available_from = 7;
  }
}

message ProductResponse {
  string product_id = 1;
  string display_name = 2;
  int64 price_minor_units = 3;
  repeated string labels = 4;
  ProductCategory category = 5;
}

enum ProductCategory {
  PRODUCT_CATEGORY_UNSPECIFIED = 0;
  PRODUCT_CATEGORY_BOOK = 1;
  PRODUCT_CATEGORY_DIGITAL = 2;
}
~~~

With `java_multiple_files = true`, the protobuf plugin generates classes such as `UpdateProductRequest`, `ProductResponse`, `ProductCategory`, and service base/stub classes in the declared package. Tests should use the actual generated classes produced by the build; do not write fake classes with similar getters.

## 4. Defining the application-side model

The application layer does not need to depend on generated protobuf classes. Example internal command and view:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.OptionalLong;

public enum CatalogProductCategory {
    BOOK,
    DIGITAL
}

public record UpdateProductCommand(
        String productId,
        Optional<String> displayName,
        OptionalLong priceMinorUnits,
        List<String> labels,
        Optional<CatalogProductCategory> category,
        Optional<Boolean> active,
        Optional<Instant> availableFrom) {}

public record ProductView(
        String productId,
        String displayName,
        long priceMinorUnits,
        List<String> labels,
        CatalogProductCategory category) {}
~~~

The command preserves the meaning of "whether the field was sent" using `Optional`/`OptionalLong`. For `oneof`, the two choices are represented as two optionals, though the mapper must guarantee both do not hold values simultaneously. In larger projects, a sealed interface or a dedicated value type can represent oneof more safely.

## 5. Writing the request mapper

The mapper converts a generated request into a command. It should be a pure Java component without injecting repositories or opening transactions:

~~~java
import com.google.protobuf.Timestamp;
import com.google.protobuf.util.Timestamps;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.OptionalLong;
import org.springframework.stereotype.Component;

@Component
public class ProductRequestMapper {

    public UpdateProductCommand toCommand(UpdateProductRequest request) {
        Optional<String> displayName = request.hasDisplayName()
                ? Optional.of(request.getDisplayName())
                : Optional.empty();

        OptionalLong price = request.hasPriceMinorUnits()
                ? OptionalLong.of(request.getPriceMinorUnits())
                : OptionalLong.empty();

        Optional<CatalogProductCategory> category =
                switch (request.getCategory()) {
                    case PRODUCT_CATEGORY_UNSPECIFIED -> Optional.empty();
                    case PRODUCT_CATEGORY_BOOK ->
                            Optional.of(CatalogProductCategory.BOOK);
                    case PRODUCT_CATEGORY_DIGITAL ->
                            Optional.of(CatalogProductCategory.DIGITAL);
                    case UNRECOGNIZED ->
                            throw new IllegalArgumentException(
                                    "Unknown product category value: "
                                            + request.getCategoryValue());
                };

        Optional<Boolean> active = Optional.empty();
        Optional<Instant> availableFrom = Optional.empty();
        switch (request.getAvailabilityCase()) {
            case ACTIVE -> active = Optional.of(request.getActive());
            case AVAILABLE_FROM ->
                    availableFrom = Optional.of(
                            toInstant(request.getAvailableFrom()));
            case AVAILABILITY_NOT_SET -> {
                // Client did not select an availability branch.
            }
        }

        return new UpdateProductCommand(
                request.getProductId(),
                displayName,
                price,
                List.copyOf(request.getLabelsList()),
                category,
                active,
                availableFrom);
    }

    private Instant toInstant(Timestamp timestamp) {
        Timestamps.checkValid(timestamp);
        return Instant.ofEpochSecond(
                timestamp.getSeconds(),
                timestamp.getNanos());
    }
}
~~~

The mapper does not decide all business rules on its own. For example, whether a negative amount/price is accepted usually belongs to validation at the boundary or domain. The mapper focuses on preserving semantics and converting types; tests should verify it does not drop information on its own.

### Important details in the mapper

- `hasDisplayName()` distinguishes an unsent field from sending an empty string.
- `hasPriceMinorUnits()` distinguishes unsent from the value `0`.
- `Optional.of(false)` retains the `active` branch being present with a false value.
- `getAvailabilityCase()` accurately identifies the `oneof` branch.
- `List.copyOf()` creates an immutable snapshot of the repeated field.
- `UNRECOGNIZED` is handled explicitly instead of silently mapping to unspecified.
- `Timestamps.checkValid()` validates the protobuf Timestamp before converting to `Instant`.

## 6. Unit tests for field presence and default values

The first test should verify that present fields are preserved even when their value equals the default:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.Optional;
import java.util.OptionalLong;
import org.junit.jupiter.api.Test;

class ProductRequestMapperTest {

    private final ProductRequestMapper mapper =
            new ProductRequestMapper();

    @Test
    void preservesPresentDefaultValues() {
        UpdateProductRequest request =
                UpdateProductRequest.newBuilder()
                        .setProductId("product-1")
                        .setDisplayName("")
                        .setPriceMinorUnits(0)
                        .setActive(false)
                        .build();

        UpdateProductCommand command = mapper.toCommand(request);

        assertEquals(Optional.of(""), command.displayName());
        assertEquals(OptionalLong.of(0), command.priceMinorUnits());
        assertEquals(Optional.of(false), command.active());
        assertTrue(command.availableFrom().isEmpty());
    }

    @Test
    void representsAbsentOptionalFieldsAsEmpty() {
        UpdateProductRequest request =
                UpdateProductRequest.newBuilder()
                        .setProductId("product-2")
                        .build();

        UpdateProductCommand command = mapper.toCommand(request);

        assertTrue(command.displayName().isEmpty());
        assertTrue(command.priceMinorUnits().isEmpty());
        assertTrue(command.active().isEmpty());
        assertTrue(command.availableFrom().isEmpty());
        assertTrue(command.category().isEmpty());
        assertEquals(List.of(), command.labels());
    }
}
~~~

These two tests guard against a common bug: using a getter while forgetting presence. If the mapper only calls `getDisplayName()`, both the unsent case and the empty-string case become `""`; once lost, the application layer cannot recover that information.

## 7. Unit tests for repeated fields and immutability

Repeated fields in generated messages are ordered and can be empty. The mapper should preserve the contract order and not return a collection that the caller could accidentally mutate:

~~~java
@Test
void mapsRepeatedLabelsInOrderAndReturnsImmutableList() {
    UpdateProductRequest request =
            UpdateProductRequest.newBuilder()
                    .setProductId("product-3")
                    .addAllLabels(List.of("featured", "sale", "new"))
                    .build();

    UpdateProductCommand command = mapper.toCommand(request);

    assertEquals(
            List.of("featured", "sale", "new"),
            command.labels());
    assertThrows(
            UnsupportedOperationException.class,
            () -> command.labels().add("changed"));
}
~~~

Do not deduplicate or reorder repeated fields on your own unless that is a published conversion rule. If business logic requires unique labels, check uniqueness in a separate validator and write tests for the validator.

## 8. Unit tests for enums and unknown values

A generated enum has the value `UNRECOGNIZED` when the payload contains a numeric value unknown to the current code version. Tests should verify the mapper's policy:

~~~java
@Test
void rejectsUnknownEnumValue() {
    UpdateProductRequest request =
            UpdateProductRequest.newBuilder()
                    .setProductId("product-4")
                    .setCategoryValue(99)
                    .build();

    IllegalArgumentException error = assertThrows(
            IllegalArgumentException.class,
            () -> mapper.toCommand(request));

    assertTrue(error.getMessage().contains("99"));
}
~~~

If the API needs forward compatibility and wants to preserve unknown numeric values, the application model must be able to represent the unknown value instead of forcing it into a closed enum. The key is choosing a clear policy and testing it; never silently convert unknown values to `PRODUCT_CATEGORY_UNSPECIFIED`.

## 9. Unit tests for oneof

Protobuf guarantees only one branch in a `oneof` is present at a time. Tests must verify that the mapper reads the case rather than inferring from getter values:

~~~java
@Test
void preservesFalseValueOfPresentOneofBranch() {
    UpdateProductRequest request =
            UpdateProductRequest.newBuilder()
                    .setProductId("product-5")
                    .setActive(false)
                    .build();

    UpdateProductCommand command = mapper.toCommand(request);

    assertEquals(Optional.of(false), command.active());
    assertTrue(command.availableFrom().isEmpty());
}
~~~

If you only check `getActive()`, a false value can be mistaken for an unselected branch. `getAvailabilityCase()` is the accurate source of truth for oneof presence.

Testing the timestamp branch:

~~~java
@Test
void mapsTimestampWithNanosecondPrecision() {
    Instant expected = Instant.parse("2026-04-05T06:07:08.123456789Z");
    Timestamp timestamp = Timestamp.newBuilder()
            .setSeconds(expected.getEpochSecond())
            .setNanos(expected.getNano())
            .build();

    UpdateProductRequest request =
            UpdateProductRequest.newBuilder()
                    .setProductId("product-6")
                    .setAvailableFrom(timestamp)
                    .build();

    UpdateProductCommand command = mapper.toCommand(request);

    assertEquals(Optional.of(expected), command.availableFrom());
    assertTrue(command.active().isEmpty());
}
~~~

Testing with non-zero nanoseconds catches mappers that accidentally convert through milliseconds and lose precision.

## 10. Writing the response mapper and testing the reverse direction

The response direction also needs tests. Example mapper:

~~~java
import org.springframework.stereotype.Component;

@Component
public class ProductResponseMapper {

    public ProductResponse toProto(ProductView product) {
        ProductCategory category = switch (product.category()) {
            case BOOK -> ProductCategory.PRODUCT_CATEGORY_BOOK;
            case DIGITAL -> ProductCategory.PRODUCT_CATEGORY_DIGITAL;
        };

        return ProductResponse.newBuilder()
                .setProductId(product.productId())
                .setDisplayName(product.displayName())
                .setPriceMinorUnits(product.priceMinorUnits())
                .addAllLabels(List.copyOf(product.labels()))
                .setCategory(category)
                .build();
    }
}
~~~

The test verifies that the generated response contains the right data and enum:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

class ProductResponseMapperTest {

    private final ProductResponseMapper mapper =
            new ProductResponseMapper();

    @Test
    void mapsApplicationViewToGeneratedResponse() {
        ProductView product = new ProductView(
                "product-7",
                "Distributed Systems",
                125_000,
                List.of("book", "featured"),
                CatalogProductCategory.BOOK);

        ProductResponse response = mapper.toProto(product);

        assertEquals("product-7", response.getProductId());
        assertEquals("Distributed Systems", response.getDisplayName());
        assertEquals(125_000, response.getPriceMinorUnits());
        assertEquals(List.of("book", "featured"), response.getLabelsList());
        assertEquals(
                ProductCategory.PRODUCT_CATEGORY_BOOK,
                response.getCategory());
    }
}
~~~

If the response has timestamps, bytes, or nested messages, add tests for each conversion that risks losing precision or changing semantics. There is no need to repeat every getter if the mapper just copies directly; focus on fields with presence, enums, oneof, time values, collections, and non-trivial mappings.

## 11. Organizing tests in a Spring project

Pure Java mappers typically do not need `@SpringBootTest`. Instantiating the mapper directly keeps tests fast and independent of Spring configuration:

```java
private final ProductRequestMapper mapper =
        new ProductRequestMapper();
```

If a mapper has other dependencies, you can instantiate them directly or use constructor injection with mocks only when the mapper genuinely collaborates with external components. An ideal mapper is mainly a deterministic conversion function that does not call the network, database, system clock, or random generators.

Place tests alongside the mapper's package in `src/test/java`, using JUnit Jupiter and the generated protobuf classes from the source set produced by the build plugin. Ensure the protobuf generation task runs in the project's build/test lifecycle; do not commit generated output unless repository conventions require it.

## 12. Anti-patterns in mapper tests

| Anti-pattern | Why it is harmful | Better approach |
| --- | --- | --- |
| Starting the full Spring context to test a mapper | Slow tests, failures hard to isolate | Pure Java unit tests |
| Comparing protobuf `toString()` strings | Output is not a stable contract | Assert individual fields or message equality |
| Testing only the happy path | Misses absent/default/unknown enum cases | Add presence and edge case tests |
| Mocking generated messages | Getters may not reflect protobuf semantics | Build real messages using builders |
| Testing only repeated field size | Misses wrong order or contents | Assert the entire list in order |
| Using the current clock in the mapper | Non-deterministic tests | Pass explicit time values |
| Ignoring unknown enums | May misinterpret requests from newer clients | Test the policy for `UNRECOGNIZED` |
| Mixing validation and mapping without clear boundaries | Tests struggle to pinpoint which layer failed | Separate validator and mapper or define clear contracts |

## 13. Minimum test matrix

Before considering a mapper complete, include cases matching the actual schema:

| Data group | Cases to test |
| --- | --- |
| Scalar optional | Absent, present with default value, present with normal value |
| Repeated | Empty, single element, multiple elements in order |
| Enum | Each supported value, unspecified, unknown numeric value |
| Oneof | No branch set, each branch, branch with false/empty value |
| Timestamp/Duration | Normal values, nanosecond precision, valid boundaries |
| Nested message | Missing child fields, nested object with data |
| Response mapping | Domain values to the right protobuf fields/enums |
| Collection | No leaked mutable references, order preserved |

Not every schema has every field type. Choose tests according to the real contract; do not add tests for non-existent fields just to satisfy a checklist.

## 14. Self-practice

1. Why do mapper unit tests not need to start a gRPC server?
2. Distinguish `hasDisplayName()` from `getDisplayName().isEmpty()`.
3. Write a test proving that `active=false` is still a sent oneof branch.
4. How do you verify a mapper does not lose nanoseconds from a protobuf Timestamp?
5. When a generated enum returns `UNRECOGNIZED`, how should the mapper handle it according to API policy?
6. Design a test for a repeated field to verify both order and immutability.

**Remember:** Unit testing protobuf mapping focuses on verifying that generated messages convert accurately to application models and response protobufs, especially regarding presence/defaults, repeated fields, enums, oneof, timestamps, and collections. Use real generated messages built with builders, write pure Java/JUnit 5 tests, separate mapping from transport and domain side effects, and add adapter/integration tests at the appropriate layers.
