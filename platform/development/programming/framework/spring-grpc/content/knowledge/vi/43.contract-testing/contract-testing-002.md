# Kiểm tra service method tồn tại

Một gRPC client chỉ gọi được RPC nếu method có trong contract mà client được sinh ra từ đó và provider đang phục vụ đúng endpoint method đó. Khi client nhận `UNIMPLEMENTED`, nguyên nhân có thể là server chưa triển khai method, service chưa được đăng ký, client/server dùng contract version khác nhau hoặc method path không khớp.

Trong Spring gRPC, kiểm tra service method cần tách ba câu hỏi:

1. **Method có trong protobuf contract không?** Kiểm tra descriptor được sinh từ proto.
2. **Provider có đăng ký method route không?** Kiểm tra ServerServiceDefinition hoặc cấu hình server thực tế.
3. **Handler có thực sự được triển khai không?** Gọi RPC qua generated stub và xác minh kết quả không phải default UNIMPLEMENTED.

Chỉ kiểm tra một lớp là chưa đủ. Generated base class có thể bind method nhưng handler mặc định vẫn trả UNIMPLEMENTED; ngược lại, client có descriptor đúng nhưng server đang chạy phiên bản cũ không có method đó. Bài này hướng dẫn kiểm tra contract, registration và runtime behavior.

## 1. Service method được định danh như thế nào?

Ví dụ protobuf:

```proto
syntax = "proto3";

package shop.catalog.v1;

option java_multiple_files = true;
option java_package = "com.myshop.catalog.v1";
option java_outer_classname = "CatalogProto";

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (Product);
  rpc WatchProduct(WatchProductRequest) returns (stream ProductEvent);
  rpc ImportProducts(stream ImportProductRequest) returns (ImportSummary);
  rpc SyncProducts(stream SyncProductRequest)
      returns (stream SyncProductEvent);
}

message GetProductRequest { string product_id = 1; }
message Product { string product_id = 1; string display_name = 2; }
message WatchProductRequest { string product_id = 1; }
message ProductEvent { string event_id = 1; string product_id = 2; }
message ImportProductRequest { string product_id = 1; }
message ImportSummary { int32 imported_count = 1; }
message SyncProductRequest { string product_id = 1; }
message SyncProductEvent { string state = 1; }
```

Với package `shop.catalog.v1` và service `CatalogService`, full service name là `shop.catalog.v1.CatalogService`. Full method path của `GetProduct` là:

```text
/shop.catalog.v1.CatalogService/GetProduct
```

Path phân biệt chữ hoa/chữ thường và là identity được dùng trong gRPC transport. Đổi package, service hoặc method name có thể khiến client gọi vào path mà provider không đăng ký.

## 2. Kiểm tra method trong protobuf descriptor

Generated protobuf outer class cung cấp file descriptor; generated gRPC class cung cấp gRPC service descriptor. Protobuf descriptor cho biết input/output message type và streaming flags. gRPC descriptor cho biết full method name và method type dùng khi gọi.

Ví dụ kiểm tra protobuf descriptor:

```java
import com.google.protobuf.Descriptors;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CatalogProtoContractTest {
    @Test
    void getProductExistsInProtoContract() {
        Descriptors.ServiceDescriptor service =
                CatalogProto.getDescriptor()
                        .findServiceByName("CatalogService");

        assertNotNull(service);
        assertEquals("shop.catalog.v1.CatalogService",
                service.getFullName());

        Descriptors.MethodDescriptor method =
                service.findMethodByName("GetProduct");
        assertNotNull(method);
        assertEquals("shop.catalog.v1.GetProductRequest",
                method.getInputType().getFullName());
        assertEquals("shop.catalog.v1.Product",
                method.getOutputType().getFullName());
        assertFalse(method.isClientStreaming());
        assertFalse(method.isServerStreaming());
    }
}
```

Kiểm tra gRPC descriptor để xác minh full method path và RPC type:

```java
import io.grpc.MethodDescriptor;
import io.grpc.ServiceDescriptor;

ServiceDescriptor service = CatalogServiceGrpc.getServiceDescriptor();
MethodDescriptor<?, ?> method = service.getMethods().stream()
        .filter(candidate -> candidate.getFullMethodName().equals(
                "shop.catalog.v1.CatalogService/GetProduct"))
        .findFirst()
        .orElseThrow(() -> new AssertionError("GetProduct is absent"));

assertEquals(MethodDescriptor.MethodType.UNARY, method.getType());
```

Hai test này xác nhận code được sinh từ proto có method mong đợi. Chúng không chứng minh server đang chạy đã đăng ký hoặc triển khai method; đó là trách nhiệm của provider test.

## 3. Kiểm tra method trong ServerServiceDefinition

Một service implementation gRPC Java cung cấp `ServerServiceDefinition` thông qua `BindableService.bindService()`. Có thể kiểm tra danh sách method mà service binding đăng ký:

```java
BindableService service = new CatalogGrpcService(catalogUseCase);
ServerServiceDefinition definition = service.bindService();

Set<String> registeredMethods = definition.getMethods().stream()
        .map(ServerMethodDefinition::getMethodDescriptor)
        .map(MethodDescriptor::getFullMethodName)
        .collect(Collectors.toSet());

assertTrue(registeredMethods.contains(
        "shop.catalog.v1.CatalogService/GetProduct"));
```

Đây là kiểm tra route được tạo bởi service binding. Có một chi tiết quan trọng: generated `CatalogServiceImplBase` thường tạo binding cho mọi method trong proto. Nếu subclass không override một method, handler mặc định của generated base vẫn có thể trả `UNIMPLEMENTED`. Vì vậy, method xuất hiện trong `getMethods()` chỉ chứng minh route được bind; nó chưa chứng minh logic method đã được viết.

Nếu Spring gRPC đăng ký service qua annotation hoặc auto-configuration, test `bindService()` riêng không chứng minh bean đó thực sự được gắn vào server. Cần integration test khởi động server do Spring quản lý và gọi method qua channel như client thật.

## 4. Phân biệt method được khai báo với method được triển khai

Ví dụ implementation chỉ override `GetProduct`:

```java
public final class CatalogGrpcService
        extends CatalogServiceGrpc.CatalogServiceImplBase {
    private final CatalogUseCase catalog;

    public CatalogGrpcService(CatalogUseCase catalog) {
        this.catalog = catalog;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<Product> observer) {
        Product product = catalog.getProduct(request.getProductId());
        observer.onNext(product);
        observer.onCompleted();
    }
}
```

Trong ví dụ, `GetProduct` có xử lý. Các method `WatchProduct`, `ImportProducts` hoặc `SyncProducts` vẫn có thể còn default implementation nếu chưa override. Chúng vẫn xuất hiện trong descriptor và server definition nhưng khi gọi có thể trả `UNIMPLEMENTED`.

Không dùng reflection trên tên method Java để kết luận handler đã được triển khai. Generated base class, override và proxy của Spring khiến kiểm tra reflection dễ cho kết quả sai. Cách đáng tin cậy là gọi RPC qua transport test và xác minh behavior/status đã cam kết.

## 5. Provider test bằng in-process server

In-process server giúp gọi service implementation qua gRPC runtime mà không mở TCP port. Test này xác minh method được bind và handler trả kết quả mong đợi:

```java
class CatalogMethodRegistrationTest {
    private Server server;
    private ManagedChannel channel;
    private CatalogServiceGrpc.CatalogServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String name = InProcessServerBuilder.generateName();
        server = InProcessServerBuilder.forName(name)
                .addService(new CatalogGrpcService(testCatalogUseCase()))
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
    void getProductIsImplementedAndCallable() {
        Product response = stub.getProduct(
                GetProductRequest.newBuilder()
                        .setProductId("P-100")
                        .build());
        assertEquals("P-100", response.getProductId());
    }
}
```

Fixture `testCatalogUseCase()` cung cấp dữ liệu test. Nếu service không đăng ký đúng service/method path, call sẽ kết thúc với `UNIMPLEMENTED`; nếu method đã được đăng ký nhưng handler gặp lỗi nghiệp vụ, test nhận status tương ứng. Vì vậy, test cần assert response hoặc status cụ thể theo contract thay vì chỉ assert call không ném exception bất kỳ.

## 6. Test method chưa được override và server version cũ

Có thể tạo implementation cố ý chưa override method để xác minh test phát hiện default `UNIMPLEMENTED`:

```java
final class IncompleteCatalogService
        extends CatalogServiceGrpc.CatalogServiceImplBase {
    // Không override getProduct: generated default handler trả UNIMPLEMENTED.
}
```

Khi gọi `getProduct` qua stub tới service này, test nên xác minh:

```java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.getProduct(
                GetProductRequest.newBuilder()
                        .setProductId("P-100")
                        .build()));

assertEquals(Status.Code.UNIMPLEMENTED,
        error.getStatus().getCode());
```

Tình huống tương tự xảy ra khi client được generate từ proto mới nhưng server production vẫn chạy binary cũ chưa có method. Đây là lý do contract test cần kiểm tra version client/provider và chạy provider verification trên artifact sắp phát hành.

`UNIMPLEMENTED` là tín hiệu hữu ích nhưng không phải bằng chứng duy nhất rằng method không tồn tại trong proto. Một handler có thể chủ động trả status đó; test fixture cần phân biệt default handler với policy nghiệp vụ có chủ đích.

## 7. Kiểm tra đủ bốn loại RPC

Method existence còn bao gồm đúng RPC shape:

| RPC | Proto signature | Method type |
| --- | --- | --- |
| Unary | `rpc GetProduct(A) returns (B);` | `UNARY` |
| Server streaming | `rpc WatchProduct(A) returns (stream B);` | `SERVER_STREAMING` |
| Client streaming | `rpc ImportProducts(stream A) returns (B);` | `CLIENT_STREAMING` |
| Bidirectional streaming | `rpc SyncProducts(stream A) returns (stream B);` | `BIDI_STREAMING` |

Test descriptor nên xác minh cờ `isClientStreaming()` và `isServerStreaming()` cho từng method. Test runtime cần gọi đúng kiểu stub:

- Unary: blocking hoặc async stub, assert response/status.
- Server streaming: đọc iterator hoặc observer tới terminal signal, assert stream phát đúng contract.
- Client streaming: gửi request messages và hoàn tất request stream, assert response cuối.
- Bidirectional: kiểm tra hai chiều, message order và terminal behavior.

Nếu proto khai báo server streaming nhưng generated/server binding có method type khác, descriptor test sẽ phát hiện trước khi chạy. Nếu method tồn tại nhưng server không triển khai đúng luồng, runtime streaming test sẽ phát hiện.

## 8. Kiểm tra đăng ký service trong Spring gRPC

Trong ứng dụng Spring, service thường được đăng ký qua annotation hoặc auto-configuration của phiên bản framework. Unit test gọi `bindService()` trực tiếp không kiểm tra application context có phát hiện bean hay không.

Spring integration test nên:

1. Khởi động application context với cấu hình gRPC test.
2. Đợi server sẵn sàng và lấy channel/client stub hướng tới server đó.
3. Gọi method bằng generated stub với request hợp lệ.
4. Assert response hoặc status contract cụ thể, đồng thời xác minh không nhận `UNIMPLEMENTED`.
5. Đóng channel và dừng context sau test.

Tên annotation, port random và cách inject channel phụ thuộc Spring gRPC starter/version mà dự án sử dụng. Dùng đúng extension point hiện có; không giả định một bean service bất kỳ tự động được đăng ký nếu chưa có integration test chứng minh.

Server reflection có thể giúp công cụ khám phá service/method, nhưng reflection là một service riêng và có thể bị tắt hoặc giới hạn vì lý do bảo mật. Không dùng việc reflection không liệt kê method làm kết luận duy nhất rằng application service không có method. Contract test nên kiểm tra descriptor và thực hiện RPC qua endpoint thực tế.

## 9. Chẩn đoán lỗi method không tồn tại

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Client không compile khi gọi method | Client code được generate từ proto không có method | Kiểm tra proto dependency và generated source version |
| Runtime trả `UNIMPLEMENTED` | Server cũ, service chưa đăng ký, route thiếu hoặc default handler | Kiểm tra deployed artifact, service definition và provider invocation |
| Service tồn tại nhưng full path khác | Package/service/method name không khớp | So sánh full method name ở client và server descriptor |
| Method được bind nhưng chưa override | Generated base default handler | Gọi RPC và assert status/response; không chỉ kiểm tra method list |
| Local test pass nhưng Spring app lỗi | Bean không được scan/đăng ký hoặc cấu hình server khác | Chạy Spring integration test qua server thật của context |
| Reflection không liệt kê method | Reflection chưa bật, bị chặn hoặc trỏ endpoint khác | Kiểm tra server configuration và gọi method trực tiếp |

Khi xử lý version mismatch, xác minh client và server build đang dùng contract artifact nào. Với rolling deployment, có thể server cũ tiếp tục nhận traffic từ client mới; chỉ triển khai client gọi method mới sau khi provider tương thích đã sẵn sàng hoặc có fallback.

## 10. Checklist contract test

- [ ] Proto descriptor có đúng service và method name.
- [ ] Full service name và full method path khớp contract đã phát hành.
- [ ] Request/response message type đúng.
- [ ] RPC cardinality đúng: unary, server, client hoặc bidi streaming.
- [ ] Generated gRPC descriptor chứa đúng method type.
- [ ] ServerServiceDefinition có route mong đợi.
- [ ] Không nhầm route được bind với handler đã override.
- [ ] Provider test gọi qua in-process server và assert response/status cụ thể.
- [ ] Có test phát hiện default `UNIMPLEMENTED` khi method chưa được triển khai.
- [ ] Spring integration test xác minh service được đăng ký trong application context.
- [ ] Client/server contract version được kiểm tra trước release/rolling deployment.
- [ ] Reflection chỉ là công cụ khám phá bổ trợ, không thay thế contract test.

**Tự kiểm tra**

**Câu 1.** Protobuf descriptor xác nhận điều gì khi tìm thấy một service method?

*Đáp án:* Nó xác nhận method được khai báo trong schema đã compile, gồm input/output type và streaming shape. Nó không xác nhận provider đang chạy đã đăng ký hoặc triển khai method.

**Câu 2.** Vì sao method có trong ServerServiceDefinition vẫn có thể trả UNIMPLEMENTED?

*Đáp án:* Generated service base có thể bind mọi method và cung cấp default handler trả `UNIMPLEMENTED` nếu subclass chưa override method đó.

**Câu 3.** Test nào xác nhận handler thực sự hoạt động?

*Đáp án:* Gọi RPC qua generated stub tới provider đang chạy trong in-process hoặc Spring integration test, rồi assert response hoặc status đã cam kết; không chỉ kiểm tra method list.

**Câu 4.** Full method path gồm những thành phần nào?

*Đáp án:* Nó gồm protobuf package, service name và method name theo dạng /package.Service/Method; sai một thành phần có thể khiến server không tìm thấy route.

**Câu 5.** Vì sao không thể chỉ dựa vào server reflection?

*Đáp án:* Reflection có thể bị tắt, giới hạn hoặc trỏ tới endpoint khác. Nó hỗ trợ khám phá nhưng không chứng minh handler triển khai đúng; cần descriptor và runtime contract test.

Kiểm tra service method tồn tại cần đi từ schema tới server runtime. Descriptor bảo vệ tên và hình dạng method; server definition cho biết route được bind; provider/Spring integration test chứng minh handler thực sự trả kết quả theo contract thay vì default UNIMPLEMENTED. Kết hợp cả ba giúp phát hiện sớm lỗi generate code, đăng ký service và lệch version giữa client với server.
