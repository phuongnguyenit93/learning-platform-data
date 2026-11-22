# Kiểm tra request và response field

Trong Spring gRPC, protobuf định nghĩa cấu trúc request và response mà client/server trao đổi. Một RPC có thể tồn tại và trả status `OK` nhưng vẫn vi phạm contract nếu server đọc sai field, bỏ qua giá trị hợp lệ hoặc trả response thiếu dữ liệu mà consumer cần. Contract test cho request/response field xác minh ý nghĩa của từng field ở ranh giới API: tên và số field ổn định, kiểu dữ liệu đúng, presence/default được hiểu đúng, validation nhất quán và response chứa giá trị đã cam kết.

Không nên chỉ kiểm tra object Java nội bộ trước khi serialize. Test cần tạo protobuf request như client thật, gọi provider qua generated stub và assert protobuf response nhận được. Với schema-level checks, descriptor test bổ sung bằng chứng về field number/type; provider test chứng minh dữ liệu đi qua RPC có đúng semantics.

## 1. Field là một phần của wire contract

Ví dụ contract catalog:

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

Một field có nhiều thuộc tính contract:

- **Field number:** định danh field trong binary wire format; không đổi hoặc tái sử dụng number đã phát hành.
- **Field type:** string, integer, enum, message, bytes, bool và các kiểu protobuf khác.
- **Cardinality:** singular, repeated hoặc map.
- **Presence:** consumer có thể phân biệt field không được set với field mang giá trị default hay không.
- **Meaning:** đơn vị, miền giá trị, quy tắc validation và ý nghĩa khi vắng mặt.

Field name có thể ảnh hưởng generated Java API và JSON mapping. Field number cùng wire type ảnh hưởng cách dữ liệu binary được giải mã. Contract test nên bảo vệ cả cấu trúc wire lẫn hành vi public mà consumer dựa vào.

## 2. Phân biệt default value và field presence

Proto3 scalar field thông thường có implicit presence. Khi field không được gửi, getter trả default value; ứng dụng không phân biệt được field vắng mặt với field được gửi bằng đúng default:

```proto
message UpdateProductRequest {
  string product_id = 1;
  int32 available_quantity = 2;
  optional int32 reorder_threshold = 3;
}
```

Trong Java:

```java
UpdateProductRequest request = UpdateProductRequest.newBuilder()
        .setProductId("P-100")
        .setAvailableQuantity(0)
        .build();

assertEquals(0, request.getAvailableQuantity());
assertFalse(request.hasReorderThreshold());
```

`available_quantity` là scalar implicit-presence: getter trả 0 khi không được set và cũng trả 0 khi client set 0. `reorder_threshold` có `optional` nên generated API có thể dùng `hasReorderThreshold()` để phân biệt không gửi với gửi giá trị 0.

Singular message field có presence. Repeated và map không có presence theo cách singular optional dùng; collection rỗng thường biểu diễn không có phần tử. Contract test phải khớp semantics thực tế thay vì giả định mọi getter đều có `hasX()`.

Quy tắc lựa chọn:

| Field kind | Cách đọc phổ biến | Ý nghĩa khi không có dữ liệu |
| --- | --- | --- |
| Scalar implicit presence | `getAvailableQuantity()` | Trả default như 0, false hoặc chuỗi rỗng |
| Scalar `optional` | `hasReorderThreshold()` và getter | Phân biệt absent với giá trị default |
| Singular message | `hasDetails()` và getter | Có thể phân biệt message chưa set |
| Repeated | `getTagsList()` | List rỗng khi không có phần tử |
| Map | `getAttributesMap()` | Map rỗng khi không có entry |

Không thêm `optional` chỉ để có `hasX()` nếu contract không cần phân biệt absent và default. Nhưng nếu semantics update cần biết caller có chủ ý set 0 hay không, presence tường minh là một phần quan trọng của API.

## 3. Kiểm tra field number và type bằng descriptor

Descriptor test phát hiện thay đổi cấu trúc mà assertion giá trị runtime có thể bỏ sót:

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

Trong descriptor API, `isOptional()` ở ví dụ thể hiện label/cardinality của field trong descriptor, không phải phép kiểm tra proto3 explicit presence cho mọi scalar. Nếu cần test explicit presence, kiểm tra `hasPresence()` trên phiên bản protobuf Java hỗ trợ hoặc xác minh bằng generated `hasReorderThreshold()` và oneof/presence API phù hợp. Tránh dùng một thuộc tính descriptor để suy ra semantics mà API đó không biểu diễn.

Descriptor test nên tập trung field public quan trọng: number, type, repeated/map, oneof membership và presence semantics. Không cần snapshot toàn bộ descriptor nếu snapshot khiến thay đổi comment/options vô hại cũng làm test thất bại.

## 4. Kiểm tra request field ở provider boundary

Request test nên dùng generated message như client thật:

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

Test này xác minh provider hiểu đúng field và trả các giá trị theo contract. Nếu thứ tự tags có ý nghĩa trong API, assert thứ tự; nếu chỉ là tập hợp, contract nên nói rõ và test không nên áp đặt thứ tự không được cam kết.

Nên có test riêng cho:

- Field bắt buộc theo nghiệp vụ bị thiếu hoặc rỗng.
- Scalar được gửi bằng default value.
- Optional field vắng mặt và hiện diện với giá trị rỗng/0.
- Repeated field rỗng, có một phần tử và nhiều phần tử.
- Message field vắng mặt và được set.
- Giá trị biên, Unicode và payload có kích thước hợp lệ.

Proto3 không có từ khóa `required` như proto2. Nếu `product_id` bắt buộc cho use case, service phải validate và trả status phù hợp; schema đơn thuần không bảo đảm client đã set field đó.

## 5. Kiểm tra response field mà consumer thực sự cần

Response contract cần bảo đảm server trả đúng field và ý nghĩa, không chỉ response khác null:

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

Hãy assert các field tạo thành public guarantee mà consumer cần. Không nên assert mọi field nội bộ hoặc giá trị không ổn định như timestamp sinh ngẫu nhiên, thứ tự map hoặc metadata triển khai nếu contract không cam kết chúng.

Nếu response có field optional, test cả hai trường hợp absent và present nếu consumer cần phân biệt. Nếu field scalar implicit-presence trả default, xác minh semantics default đã công bố. Nếu field mới được thêm, client cũ thường bỏ qua unknown field; client mới gọi server cũ có thể thấy default/absent, nên phải xác định consumer xử lý trường hợp đó ra sao.

## 6. Validation và status cho request field sai

Validation của request nên diễn ra tại boundary/application layer trước khi thực hiện side effect. Ví dụ:

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

Trong code production, có thể chuyển validation exception qua exception mapper dùng chung. Dù triển khai cách nào, contract test phải xác minh status và không có side effect khi request không hợp lệ.

Ví dụ:

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

Không dùng `INTERNAL` cho lỗi request mà client có thể sửa. Status `INVALID_ARGUMENT` là tín hiệu contract cho biết request không hợp lệ; description nên ngắn, ổn định và không tiết lộ chi tiết nội bộ.

## 7. Các field phức hợp: oneof, enum, map và bytes

Với `oneof`, chỉ một nhánh có thể hiện diện tại một thời điểm:

```proto
message ProductSelector {
  oneof selector {
    string product_id = 1;
    string sku = 2;
  }
}
```

Generated Java API cung cấp case enum:

```java
switch (selector.getSelectorCase()) {
    case PRODUCT_ID -> loadById(selector.getProductId());
    case SKU -> loadBySku(selector.getSku());
    case SELECTOR_NOT_SET -> throw new IllegalArgumentException(
            "A product selector is required");
}
```

Contract test cần xác minh mỗi nhánh, trạng thái chưa set và việc hai nhánh không cùng tồn tại sau serialize/parse.

Với enum, giữ ổn định numeric value và xử lý giá trị chưa biết từ phiên bản mới. Java protobuf enum có thể trả `UNRECOGNIZED` cho numeric value không biết; `getXValue()` cho phép giữ số nguyên gốc khi cần. Với map, test key/value và semantics khi key không tồn tại. Với bytes, test nội dung binary chính xác, không giả định UTF-8 nếu contract định nghĩa dữ liệu nhị phân.

## 8. Unknown field và tương thích client/server

Protobuf được thiết kế để reader có thể bỏ qua field chưa biết, giúp thêm field mới mà client cũ vẫn parse được. Tuy nhiên, consumer mới gọi server cũ có thể không nhận field mới và phải xử lý default/presence phù hợp.

Một ma trận test hữu ích:

| Client | Provider | Kỳ vọng |
| --- | --- | --- |
| Cũ | Mới có thêm response field | Client cũ parse được và bỏ qua field chưa biết |
| Mới có request field mới | Cũ chưa hiểu field | Provider cũ bỏ qua unknown field; client không giả định server đã áp dụng semantics mới |
| Mới | Mới | Field mới được đọc/ghi theo contract |
| Cũ | Mới đã ngừng dùng field cũ | Field number cũ không được tái sử dụng; semantics chuyển tiếp được xác định |

Khi xóa field, reserve number và name. Không tái sử dụng số field. Khi thêm field có presence hoặc default semantics quan trọng, test cả phiên bản consumer/provider tương thích trong rolling deployment. Compatibility checker như Buf có thể phát hiện thay đổi schema, nhưng behavior test vẫn cần xác minh consumer xử lý giá trị absent/unknown đúng.

Ví dụ khi loại bỏ field `legacy_code`:

```proto
message Product {
  string product_id = 1;
  reserved 2;
  reserved "legacy_code";
  string display_name = 3;
}
```

`reserved` ngăn schema tương lai vô tình tái sử dụng number 2 hoặc tên `legacy_code`. Khi review contract, kiểm tra cả number lẫn name đã xóa; không chỉ xóa field khỏi file rồi để slot trống không được bảo vệ.

## 9. Kiểm thử field qua in-process provider và Spring

In-process server cho phép gọi service bằng generated stub, kiểm tra serialization, request mapping, response field và status mà không cần TCP:

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

Fixture `testCatalog()` và `CatalogGrpcService` là thành phần test của ứng dụng. Với Spring integration test, khởi động application context và gọi qua server/channel được cấu hình thật để xác minh bean, interceptor, validation và mapper được nối đúng. In-process test không thay thế kiểm tra TLS, load balancing hoặc network failure.

## 10. Checklist contract test cho field

- [ ] Field number/type/cardinality không lệch contract đã phát hành.
- [ ] Không tái sử dụng field number/name đã xóa; field cũ được reserve.
- [ ] Implicit presence và explicit presence được phân biệt đúng.
- [ ] Default value có semantics được ghi rõ và được test.
- [ ] Repeated/map/message/oneof/enum được kiểm tra theo API Java sinh ra.
- [ ] Request field sai trả status phù hợp như `INVALID_ARGUMENT`.
- [ ] Request hợp lệ được map đúng sang use case.
- [ ] Response chứa đúng field public mà consumer cần.
- [ ] Optional/absent/default/unknown field có test tương thích.
- [ ] Không assert implementation detail hoặc dữ liệu không ổn định ngoài contract.
- [ ] Có provider test qua generated stub và Spring integration test.
- [ ] Test có deadline/timeout hữu hạn và dọn channel/server.

**Tự kiểm tra**

**Câu 1.** Vì sao `getAvailableQuantity()` có thể trả 0 dù client không gửi field?

*Đáp án:* Scalar proto3 thông thường dùng implicit presence; getter trả default value khi field không được set. Nếu cần phân biệt absent với set 0, khai báo `optional` hoặc dùng kiểu có explicit presence phù hợp.

**Câu 2.** Khi nào generated Java có `hasDescription()`?

*Đáp án:* Với singular message field hoặc scalar được khai báo explicit presence như `optional`, generated API cung cấp cách kiểm tra presence. Scalar implicit-presence thông thường không có `hasX()`.

**Câu 3.** Vì sao contract test cần gọi provider bằng generated stub?

*Đáp án:* Cách đó kiểm tra protobuf request/response qua gRPC serialization và handler thật, thay vì chỉ kiểm tra object nội bộ trước transport.

**Câu 4.** Request thiếu product_id nên được xử lý thế nào?

*Đáp án:* Proto3 không tự bắt buộc scalar string này. Provider phải validate theo contract và thường trả `INVALID_ARGUMENT` trước khi thực hiện side effect.

**Câu 5.** Khi thêm response field mới, client cũ cần làm gì?

*Đáp án:* Client cũ thường bỏ qua unknown field khi parse protobuf. Client mới gọi server cũ phải xử lý trường hợp field mới vắng mặt/default theo presence semantics; không giả định mọi provider đã nâng cấp đồng thời.

Kiểm tra request và response field phải bảo vệ cả cấu trúc lẫn ý nghĩa dữ liệu. Descriptor test giữ ổn định number/type/presence; provider test qua generated stub xác minh mapping và validation; compatibility test bảo đảm client cũ/mới xử lý field absent hoặc unknown đúng. Kết hợp các lớp này giúp contract của Spring gRPC rõ ràng và an toàn khi triển khai nhiều phiên bản cùng lúc.
