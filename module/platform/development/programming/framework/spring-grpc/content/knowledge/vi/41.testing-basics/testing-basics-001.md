# Unit test mapping protobuf

**Chương:** Testing basics  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng hợp đồng Protocol Buffers, mã Java được sinh và triển khai client/server cho unary hoặc streaming RPC. Bài này tập trung vào unit test cho lớp mapper ở service adapter: chuyển generated protobuf request thành command của application layer và chuyển kết quả ứng dụng thành protobuf response. Mục tiêu là kiểm tra chính xác semantics của mapping mà không cần khởi động Spring context, gRPC server hoặc database.

## 1. Vì sao mapper cần unit test riêng?

Service adapter đứng giữa giao thức gRPC và application layer. Adapter nhận generated message, chuyển dữ liệu sang command/model nội bộ, gọi use case rồi chuyển kết quả về generated response. Mapper là nơi có thể xảy ra những lỗi tinh vi:

- Field không được gửi bị biến thành giá trị mặc định và mất thông tin presence.
- Giá trị `false` hoặc `0` được hiểu nhầm là field không có.
- Repeated field bị mất phần tử hoặc thay đổi thứ tự.
- Enum mới từ client bị âm thầm đổi thành enum mặc định.
- Nhánh `oneof` không được nhận diện đúng.
- Timestamp mất độ chính xác nano giây.
- Mapper trả collection mutable hoặc giữ tham chiếu không mong muốn.

Unit test mapper giúp kiểm tra các quy tắc chuyển đổi một cách nhanh, cô lập và xác định. Test không cần kiểm tra gRPC transport; đó là trách nhiệm của integration test ở tầng khác.

## 2. Phân biệt mapper test với adapter/integration test

| Loại test | Đối tượng | Điều cần xác nhận |
| --- | --- | --- |
| Mapper unit test | Lớp chuyển đổi protobuf ↔ application model | Field, presence, enum, oneof, collection, timestamp được map đúng |
| Adapter unit test | Generated service implementation | Gọi đúng mapper/use case và chuyển kết quả thành response/status |
| In-process gRPC test | Stub, channel, server và interceptor | Request/response/status đi qua gRPC runtime đúng hợp đồng |
| End-to-end test | Các service và dependency thực hoặc gần thực | Luồng nghiệp vụ tích hợp hoạt động trong môi trường triển khai |

Mapper test nên chạy trực tiếp trên generated message đã được tạo bằng builder. Không cần khởi tạo `ManagedChannel`, `Server` hay `@SpringBootTest` nếu chỉ muốn kiểm tra một phép chuyển đổi thuần Java.

## 3. Ví dụ protobuf contract

Giả sử service cập nhật một sản phẩm. Hợp đồng dùng `optional` để phân biệt field không gửi với giá trị mặc định, `repeated` cho labels, enum để phân loại sản phẩm và `oneof` để chọn trạng thái availability:

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

Với `java_multiple_files = true`, protobuf plugin sinh các lớp như `UpdateProductRequest`, `ProductResponse`, `ProductCategory` và service base/stub trong package đã khai báo. Test nên dùng chính các generated classes do build tạo ra; không tự viết class giả có getter tương tự.

## 4. Xác định model phía application

Application layer không cần phụ thuộc vào generated protobuf classes. Ví dụ command và view nội bộ:

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

Command giữ nguyên ý nghĩa “có gửi field hay không” bằng `Optional`/`OptionalLong`. Với `oneof`, hai lựa chọn được biểu diễn thành hai optional nhưng mapper phải bảo đảm không cùng có giá trị. Ở dự án lớn, có thể dùng sealed interface hoặc một kiểu value riêng để biểu diễn oneof an toàn hơn.

## 5. Viết mapper request

Mapper chuyển generated request thành command. Nó nên là thành phần Java thuần, không cần inject repository hoặc mở transaction:

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
                // Client không chọn nhánh availability.
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

Mapper không tự quyết định mọi quy tắc nghiệp vụ. Ví dụ amount/price âm có được chấp nhận hay không thường thuộc validation ở boundary hoặc domain. Mapper tập trung bảo toàn semantics và chuyển kiểu; test cần xác nhận nó không tự làm mất thông tin.

### Những chi tiết quan trọng trong mapper

- `hasDisplayName()` phân biệt không gửi field với gửi chuỗi rỗng.
- `hasPriceMinorUnits()` phân biệt không gửi với giá trị `0`.
- `Optional.of(false)` giữ được nhánh `active` có mặt nhưng giá trị false.
- `getAvailabilityCase()` xác định chính xác nhánh `oneof`.
- `List.copyOf()` tạo snapshot immutable của repeated field.
- `UNRECOGNIZED` được xử lý tường minh thay vì âm thầm map về unspecified.
- `Timestamps.checkValid()` kiểm tra Timestamp protobuf trước khi đổi sang `Instant`.

## 6. Unit test cho field presence và giá trị mặc định

Test đầu tiên nên xác nhận field có mặt vẫn được giữ ngay cả khi giá trị bằng mặc định:

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

Hai test này bảo vệ một lỗi thường gặp: dùng getter mà quên presence. Nếu mapper chỉ gọi `getDisplayName()`, cả trường hợp không gửi và trường hợp gửi chuỗi rỗng đều thành `""`; thông tin đã mất thì application layer không thể khôi phục.

## 7. Unit test cho repeated field và immutability

Repeated field trong generated message có thứ tự và có thể rỗng. Mapper nên giữ thứ tự theo hợp đồng và không trả lại một collection mà caller có thể vô tình sửa:

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

Không tự loại bỏ phần tử trùng hoặc sắp xếp lại repeated field trừ khi đó là quy tắc chuyển đổi đã được công bố. Nếu nghiệp vụ yêu cầu unique labels, kiểm tra uniqueness trong validator riêng và viết test cho validator.

## 8. Unit test cho enum và giá trị chưa biết

Generated enum có giá trị `UNRECOGNIZED` khi payload chứa numeric value mà phiên bản code hiện tại chưa biết. Test nên xác nhận chính sách của mapper:

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

Nếu API cần forward compatibility và muốn giữ unknown numeric value, model application phải biểu diễn được giá trị chưa biết thay vì ép thành enum đóng. Điều quan trọng là chọn policy rõ ràng và test policy đó; không âm thầm đổi unknown thành `PRODUCT_CATEGORY_UNSPECIFIED`.

## 9. Unit test cho oneof

Protobuf bảo đảm chỉ một nhánh trong `oneof` có mặt tại một thời điểm. Test phải xác nhận mapper đọc case chứ không suy luận từ giá trị getter:

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

Nếu chỉ kiểm tra `getActive()`, giá trị false có thể bị hiểu nhầm là nhánh không được chọn. `getAvailabilityCase()` mới là nguồn thông tin chính xác về presence của oneof.

Test nhánh timestamp:

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

Test với nanosecond khác 0 phát hiện mapper vô tình đổi qua milliseconds và làm mất độ chính xác.

## 10. Viết response mapper và kiểm thử chiều ngược

Chiều response cũng cần test. Ví dụ mapper:

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

Test xác nhận generated response chứa đúng dữ liệu và enum:

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

Nếu response có timestamp, bytes hoặc nested message, bổ sung test cho từng phép chuyển đổi có nguy cơ mất precision hoặc thay đổi semantics. Không cần lặp lại mọi getter nếu mapper chỉ sao chép trực tiếp; tập trung vào field có presence, enum, oneof, thời gian, collection và mapping không tầm thường.

## 11. Tổ chức test trong dự án Spring

Mapper thuần Java thường không cần `@SpringBootTest`. Tạo mapper trực tiếp giúp test nhanh và không phụ thuộc cấu hình Spring:

```java
private final ProductRequestMapper mapper =
        new ProductRequestMapper();
```

Nếu mapper có dependency khác, có thể khởi tạo dependency trực tiếp hoặc dùng constructor injection với mock chỉ khi mapper thực sự cộng tác với thành phần bên ngoài. Một mapper lý tưởng chủ yếu là hàm chuyển đổi xác định, không gọi network, database, clock hệ thống hoặc random generator.

Đặt test cạnh package của mapper trong `src/test/java`, dùng JUnit Jupiter và generated protobuf classes từ source set được build plugin tạo ra. Đảm bảo task generate protobuf chạy trong build/test lifecycle của dự án; không commit generated output nếu quy ước repository không yêu cầu.

## 12. Các anti-pattern trong mapper test

| Anti-pattern | Vì sao có hại | Cách tốt hơn |
| --- | --- | --- |
| Khởi động toàn bộ Spring context để test mapper | Test chậm, lỗi khó khoanh vùng | Unit test thuần Java |
| So sánh chuỗi `toString()` của protobuf | Output không phải contract ổn định | Assert từng field hoặc equality của message |
| Chỉ test happy path | Bỏ sót absent/default/unknown enum | Thêm test presence và edge cases |
| Dùng mock generated message | Getter có thể không phản ánh protobuf semantics | Tạo message thật bằng builder |
| Test chỉ số lượng repeated field | Không phát hiện sai thứ tự/nội dung | Assert toàn bộ list theo thứ tự |
| Dùng clock hiện tại trong mapper | Test không deterministic | Truyền giá trị thời gian tường minh |
| Bỏ qua unknown enum | Có thể diễn giải sai request từ client mới | Test policy cho `UNRECOGNIZED` |
| Gộp validation và mapping không rõ ranh giới | Test khó xác định lỗi thuộc lớp nào | Tách validator và mapper hoặc định nghĩa rõ contract |

## 13. Ma trận kiểm thử tối thiểu

Trước khi coi mapper hoàn chỉnh, nên có các ca phù hợp với schema thực tế:

| Nhóm dữ liệu | Ca cần test |
| --- | --- |
| Scalar optional | Absent, present với giá trị mặc định, present với giá trị thông thường |
| Repeated | Empty, một phần tử, nhiều phần tử có thứ tự |
| Enum | Mỗi giá trị hỗ trợ, unspecified, unknown numeric value |
| Oneof | Không có nhánh, từng nhánh, nhánh mang giá trị false/empty |
| Timestamp/Duration | Giá trị thường, độ chính xác nano, biên hợp lệ |
| Nested message | Field con thiếu, nested object có dữ liệu |
| Response mapping | Domain value sang đúng protobuf field/enum |
| Collection | Không rò rỉ mutable reference, không thay đổi thứ tự |

Không phải schema nào cũng có tất cả loại field. Chọn test theo contract thật; không thêm test cho field không tồn tại chỉ để đạt một checklist.

## 14. Tự luyện tập

1. Vì sao unit test mapper không cần khởi động gRPC server?
2. Phân biệt `hasDisplayName()` với `getDisplayName().isEmpty()`.
3. Viết test chứng minh `active=false` vẫn là nhánh oneof đã được gửi.
4. Làm thế nào kiểm tra mapper không làm mất nanosecond của protobuf Timestamp?
5. Khi generated enum trả về `UNRECOGNIZED`, mapper nên xử lý thế nào theo policy API?
6. Thiết kế test cho repeated field để xác nhận cả thứ tự và immutability.

**Ghi nhớ:** Unit test mapping protobuf tập trung xác nhận generated message được chuyển sang application model và response protobuf chính xác, đặc biệt với presence/default, repeated, enum, oneof, timestamp và collection. Dùng generated message thật được tạo bằng builder, test thuần Java/JUnit 5, tách mapping khỏi transport và domain side effects, rồi bổ sung adapter/integration tests ở tầng phù hợp.
