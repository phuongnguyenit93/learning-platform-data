# Contract test dựa trên proto

Trong Spring gRPC, file `.proto` là hợp đồng công khai giữa client và server: nó định nghĩa package, service, RPC method, kiểu request/response và cấu trúc dữ liệu trên wire. Một thay đổi Java có thể biên dịch thành công nhưng vẫn phá hợp đồng với client đã phát hành trước đó. Contract test dựa trên proto kiểm tra schema, khả năng tương thích và hành vi mà hai phía đã cam kết.

Một quy trình đáng tin cậy kết hợp ba lớp: kiểm tra schema tĩnh, kiểm tra descriptor/code được sinh và chạy RPC qua provider thật trong môi trường test. Chỉ so sánh file `.proto` không chứng minh server thực thi đúng; chỉ gọi server bằng test nội bộ cũng không phát hiện mọi thay đổi wire-incompatible. Bài này trình bày cách kết hợp các lớp đó cho unary và streaming RPC trong hệ sinh thái Spring gRPC.

## 1. Hợp đồng proto gồm những gì?

Ví dụ một service:

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

Contract bao gồm:

- **Identity:** protobuf package, service name và method name. Full method name của RPC là `shop.catalog.v1.CatalogService/GetProduct`.
- **Message schema:** field number, wire type, cardinality, presence, enum number, `oneof`, map và nested type.
- **RPC shape:** unary, server streaming, client streaming hay bidirectional streaming.
- **Generated API:** tên method/stub và kiểu Java sinh từ proto.
- **Behavioral expectations:** status, validation, ordering, idempotency, deadline, authorization và semantics của stream.

Proto định nghĩa cấu trúc dữ liệu và RPC shape, nhưng không tự mô tả đầy đủ mọi hành vi nghiệp vụ. Các cam kết như `NOT_FOUND` khi không tồn tại sản phẩm, sequence phải tăng đơn điệu hoặc stream kết thúc khi nào cần được ghi thành expectation và kiểm thử riêng.

## 2. Ba lớp contract test

| Lớp | Kiểm tra | Phát hiện tốt |
| --- | --- | --- |
| Schema compatibility | So sánh proto hiện tại với phiên bản baseline | Đổi field number, xóa field không reserve, đổi RPC shape |
| Descriptor/generated contract | Kiểm tra service/method/type trong descriptor và code sinh | Sai package, thiếu method, kiểu request/response ngoài dự kiến |
| Provider behavior | Gọi provider qua generated stub và kiểm tra kết quả | Server trả sai field, status, stream order hoặc terminal behavior |

Consumer-side test cũng có vai trò: nó xác nhận client có thể tạo request theo contract và xử lý response/status mà provider cam kết. Với nhiều consumer, lưu các expectation có ý nghĩa và chạy chúng với provider trong CI. Tránh chỉ kiểm tra implementation detail của một client cụ thể.

## 3. Quy tắc tương thích của protobuf

Protocol Buffers dùng field number để nhận diện field trên wire. Field name có ý nghĩa với source/API và JSON mapping, còn field number cùng wire type quyết định cách dữ liệu nhị phân được đọc.

| Thay đổi | Đánh giá | Cách xử lý |
| --- | --- | --- |
| Thêm field với number mới | Thường tương thích wire | Xác định default/presence và semantics khi client cũ bỏ qua field |
| Xóa field | Có thể phá khi tái sử dụng number/name | Reserve cả number và name đã xóa |
| Đổi field number | Breaking | Không đổi number đã phát hành |
| Đổi kiểu field | Có thể đổi wire type hoặc semantics | Xem quy tắc tương thích cụ thể; mặc định xem là breaking cho API công khai |
| Thêm enum value | Thường tương thích wire | Consumer phải xử lý enum value chưa biết |
| Đổi số enum hoặc tái sử dụng số đã xóa | Breaking | Giữ số ổn định, reserve số/name đã xóa |
| Đổi package/service/method | Có thể đổi full RPC path | Xem như thay đổi endpoint contract |
| Đổi unary thành streaming hoặc ngược lại | Breaking | Tạo method/version mới nếu cần |
| Đổi request/response type của method | Thường breaking | Giữ method cũ hoặc phát hành method mới |

Ví dụ khi xóa field:

```proto
message Product {
  string product_id = 1;
  reserved 2;
  reserved "legacy_name";
  int32 available_quantity = 3;
}
```

Không tái sử dụng field number đã phát hành, kể cả khi field cũ không còn được code hiện tại dùng. Một client cũ vẫn có thể gửi dữ liệu mang number đó; tái sử dụng sẽ khiến cùng bytes bị diễn giải thành ý nghĩa mới.

Thêm field thường tương thích về wire vì reader cũ bỏ qua unknown field, nhưng chưa chắc tương thích về nghiệp vụ. Nếu client mới yêu cầu field đó luôn có giá trị mà server cũ không gửi, schema có thể hợp lệ nhưng workflow vẫn hỏng. Contract test cần kiểm tra cả khả năng tương thích lẫn giả định semantics.

## 4. Dùng Buf để kiểm tra schema trong CI

Buf cung cấp lint và breaking-change detection cho protobuf. Dự án cần có cấu hình Buf phù hợp với layout proto và quy tắc versioning của tổ chức.

Ví dụ lệnh trong pipeline:

```bash
buf lint
buf breaking --against '.git#branch=main'
```

`buf lint` kiểm tra style và một số lỗi cấu trúc theo rule set. `buf breaking` so sánh schema hiện tại với baseline để phát hiện thay đổi vi phạm mức tương thích được cấu hình. Chọn breaking rule theo chính sách phát hành; mức strict khác nhau có thể chặn những thay đổi mà nhóm chủ động cho phép hoặc bỏ lọt rủi ro mà nhóm cần kiểm soát.

Baseline phải là contract đã phát hành hoặc nhánh ổn định được chọn làm mốc, không phải một file tạm của cùng lần build. Khi phát hành version mới, cập nhật baseline theo quy trình review. Không bỏ qua breaking check chỉ để pipeline xanh; nếu cần phá tương thích, phát hành method/package version mới và có kế hoạch chuyển consumer.

## 5. Tạo descriptor set làm artifact contract

Descriptor set chứa mô tả schema đã biên dịch, có thể lưu cùng artifact để test hoặc công cụ khác kiểm tra. Ví dụ:

```bash
protoc \
  -I src/main/proto \
  --include_imports \
  --descriptor_set_out=build/contracts/catalog.pb \
  src/main/proto/shop/catalog/v1/catalog.proto
```

`--include_imports` đưa descriptor của các dependency proto vào artifact. Có thể thêm `--include_source_info` nếu công cụ cần source location/comment; không cần bật nếu chỉ kiểm tra cấu trúc contract.

Descriptor set hữu ích để:

- Xác minh service/method và request/response type trong artifact được phát hành.
- So sánh contract artifact giữa hai phiên bản.
- Kiểm tra client/server được build từ cùng contract version dự kiến.
- Cung cấp schema cho tool test hoặc registry nội bộ.

Không nên so sánh raw bytes của hai descriptor set như tiêu chí tương thích duy nhất. Thứ tự, source info hoặc option có thể làm artifact khác byte dù semantics không thay đổi. Dùng descriptor-aware diff hoặc breaking checker hiểu protobuf semantics.

## 6. Kiểm tra generated descriptor và RPC identity

Generated Java code có descriptor phản ánh schema được compile. Một test có thể kiểm tra package, service, method và RPC type:

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

`CatalogProto` là tên outer descriptor class minh họa; tên thật phụ thuộc `java_outer_classname` hoặc quy tắc protoc của dự án. Test này xác nhận generated code đang mang đúng schema mong đợi. Nó không chứng minh provider đã đăng ký method hoặc trả đúng behavior; cần provider integration test ở bước tiếp theo.

## 7. Provider contract test với in-process server

In-process transport cho phép gọi service thật trong test mà không mở TCP port. Test dùng generated stub giống client, nên kiểm tra được request/response type, status và serialization của gRPC runtime:

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

Các helper `testCatalog()` và `CatalogGrpcService` đại diện fixture/service implementation của test. Trong Spring integration test, có thể khởi động application context với server thật do Spring cấu hình rồi gọi qua channel test; mục tiêu là xác minh interceptor, dependency injection và đăng ký service đều hoạt động như môi trường ứng dụng.

`directExecutor()` hữu ích để test in-process đơn giản và deterministic, nhưng không mô phỏng thread scheduling hoặc network behavior production. Không dùng kết quả của test này để kết luận TLS, load balancing, deadline qua mạng hay backpressure đã được kiểm tra.

## 8. Contract test cho streaming RPC

Với `WatchProduct`, contract không chỉ là kiểu response. Cần kiểm tra:

- Request hợp lệ bắt đầu đúng stream.
- Event mang đúng product ID và schema field.
- Sequence tăng theo quy tắc đã công bố.
- Thứ tự message được giữ nếu API cam kết ordered stream.
- Stream hoàn tất hoặc lỗi bằng status đúng.
- Cancellation dừng nguồn phát và giải phóng tài nguyên.

Blocking stub cho server streaming trả về `Iterator`:

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

Với client streaming và bidirectional streaming, dùng async stub và observer. Test phải có timeout/latch hữu hạn, kiểm tra số message, thứ tự, status terminal và cancellation. Không dùng một stream vô hạn trong contract test; định nghĩa điều kiện kết thúc rõ để test luôn giải phóng channel/server.

Nếu contract công bố deadline và cancellation semantics, kiểm thử chúng như một phần hành vi RPC. Ví dụ, client đặt deadline ngắn cho một stream cố ý phát chậm và xác minh client nhận `DEADLINE_EXCEEDED`; khi client chủ động cancel, client thường quan sát `CANCELLED` và provider phải dừng nguồn phát, giải phóng tài nguyên. Server thường quan sát cancellation qua call context/`ServerCallStreamObserver`; không giả định hai phía luôn quan sát cùng một mã status trong mọi race giữa deadline và transport cancellation.

## 9. Consumer expectations và version compatibility

Consumer contract test nên mô tả những gì client thực sự cần, không sao chép toàn bộ implementation của provider:

| Consumer expectation | Provider verification |
| --- | --- |
| Client gửi `product_id` hợp lệ | Provider đọc đúng field và trả đúng sản phẩm |
| Client xử lý unknown field | Provider mới thêm field mà client cũ có thể bỏ qua |
| Client xử lý enum value chưa biết | Provider có thể phát enum mới mà consumer không crash |
| Client cần `NOT_FOUND` cho ID không tồn tại | Provider trả status đã cam kết |
| Client cần stream ordered | Provider giữ thứ tự sequence đã công bố |
| Client đặt deadline ngắn | Client nhận `DEADLINE_EXCEEDED` khi server không hoàn tất đúng hạn |
| Client chủ động cancel stream | Provider dừng nguồn phát và giải phóng tài nguyên |

Trong rollout, có thể tồn tại đồng thời client cũ/server mới và client mới/server cũ. Lập ma trận version để kiểm tra các cặp quan trọng:

- Client phiên bản đang chạy với server phiên bản mới.
- Client mới với server cũ trong giai đoạn rolling deployment.
- Consumer có tốc độ nâng cấp chậm hoặc bên thứ ba dùng contract đã phát hành.

Test compatibility không thay thế kiểm thử migration và rollout. Nếu thay đổi không tương thích là bắt buộc, phát hành package/service version mới, duy trì method cũ trong giai đoạn chuyển tiếp và theo dõi consumer trước khi loại bỏ.

## 10. Đưa contract test vào CI và checklist

Một pipeline thường chạy theo thứ tự:

1. Lint proto và kiểm tra breaking change với baseline.
2. Generate Java code và descriptor set từ proto đã review.
3. Compile consumer/provider modules để phát hiện sai khác generated API.
4. Chạy descriptor contract test.
5. Chạy provider integration test cho unary, streaming và status.
6. Chạy Spring integration test cho wiring/interceptor/configuration.
7. Lưu contract artifact/version cùng release để consumer có thể xác định schema đã dùng.

Checklist:

- [ ] Proto package, service, method và RPC cardinality được review.
- [ ] Field number/name đã xóa được reserve; không tái sử dụng number.
- [ ] Enum number ổn định và consumer xử lý unknown value.
- [ ] Buf lint và breaking check chạy với baseline đúng.
- [ ] Descriptor/generated contract xác nhận full method name và type.
- [ ] Provider test gọi bằng generated stub, kiểm tra response và gRPC status.
- [ ] Streaming test xác minh message count/order/terminal/cancellation.
- [ ] Test có deadline và timeout hữu hạn để tránh treo pipeline.
- [ ] Spring integration test xác minh service và interceptor được đăng ký.
- [ ] Có ma trận tương thích client/server cho rolling deployment.
- [ ] Contract artifact được version hóa và truy vết tới release.

**Tự kiểm tra**

**Câu 1.** Vì sao chỉ compile proto không đủ để xác nhận contract?

*Đáp án:* Compile chỉ xác nhận schema có thể sinh code. Nó không chứng minh thay đổi tương thích với consumer cũ hoặc provider trả đúng status, dữ liệu và stream semantics.

**Câu 2.** Vì sao không tái sử dụng field number đã xóa?

*Đáp án:* Client cũ có thể vẫn gửi field number đó. Tái sử dụng khiến bytes cũ bị diễn giải thành field mới với ý nghĩa khác; cần reserve number và name đã xóa.

**Câu 3.** Descriptor test và provider behavior test khác nhau thế nào?

*Đáp án:* Descriptor test kiểm tra service/method/type được sinh từ proto; provider test gọi RPC thực qua generated stub để xác minh response, status và streaming behavior.

**Câu 4.** Vì sao in-process test không thay thế được deployment test?

*Đáp án:* In-process test không mô phỏng TCP/TLS, load balancing, network failure hoặc scheduling thực tế. Nó kiểm tra contract behavior ở mức service/runtime trong môi trường test.

**Câu 5.** Contract của streaming RPC cần kiểm tra thêm điều gì ngoài message type?

*Đáp án:* Số lượng và thứ tự message, sequence, terminal status, điều kiện hoàn tất, cancellation và deadline.

Contract test dựa trên proto tạo một hàng rào giữa schema và hành vi provider: schema checker bảo vệ wire compatibility, descriptor test bảo vệ RPC identity, còn integration test chứng minh server thực hiện đúng kỳ vọng của consumer. Kết hợp các lớp này trong CI giúp Spring gRPC phát hiện breaking change trước khi contract mới tới client đang chạy.
