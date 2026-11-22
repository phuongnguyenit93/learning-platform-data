# Stub trong test

## 1. Mục tiêu

Trong Spring gRPC, generated stub là client API được sinh từ Protobuf service. Test dùng stub để gọi RPC và kiểm tra hành vi mà client thực sự quan sát: response, status, metadata, deadline và streaming. Cách test phù hợp phụ thuộc vào lớp đang kiểm tra: application service, gateway/client adapter hay toàn bộ Spring gRPC server.

**Stub trong test** là sử dụng generated gRPC stub trong môi trường kiểm thử để xác minh client gọi đúng method, serialize request, nhận và giải mã response, xử lý lỗi và tuân thủ call options. Một bài test tốt phải chọn đúng ranh giới:

- Unit test application service thường mock gateway interface.
- Test gateway và generated stub có thể dùng in-process gRPC server.
- Integration test Spring cần khởi động server/client theo cấu hình ứng dụng.
- Test deployment/transport cần kết nối qua TCP/TLS và môi trường gần production.

Sau bài học, bạn có thể:

- Tạo blocking, async hoặc future stub trong test.
- Dùng `InProcessServerBuilder` và `InProcessChannelBuilder` để test RPC nhanh.
- Viết fake service từ generated `ImplBase`.
- Kiểm tra response, status, deadline, metadata và streaming.
- Quản lý lifecycle server/channel trong JUnit.
- Phân biệt test in-process với Spring integration test qua transport thật.
- Tránh mock generated stub ở tầng không phù hợp.

## 2. Chọn đúng loại test

Không phải mọi test đều cần khởi động gRPC server. Chọn ranh giới theo điều cần chứng minh:

| Mục tiêu | Cách test phù hợp | Điều được xác minh |
|---|---|---|
| Application service phối hợp nhiều dependency đúng | Unit test, mock gateway interface | Quy tắc nghiệp vụ và orchestration |
| Gateway tạo request và mapping response/status đúng | Generated stub gọi fake service in-process | RPC method, Protobuf marshalling và mapping |
| Spring đăng ký đúng service/client bean | Spring application context test | Dependency injection, auto-configuration và service registration |
| TLS, DNS, load balancing, proxy hoặc socket | Integration test qua TCP/TLS | Transport và cấu hình kết nối |
| Client/server khác phiên bản | Compatibility test với artifact cũ/mới | Wire contract và hành vi mixed-version |

Một unit test mock `CatalogClient` không chứng minh generated stub gọi đúng full method path. Ngược lại, test in-process không cần kiểm tra lại mọi quy tắc nghiệp vụ của application service. Mỗi lớp test nên có một mục tiêu rõ.

## 3. In-process transport là gì?

gRPC Java cung cấp transport in-process để client và server giao tiếp trong cùng JVM mà không mở TCP socket. Nó vẫn dùng generated stub, service descriptor, gRPC call lifecycle và Protobuf marshaller. Vì vậy, đây là lựa chọn phù hợp để test RPC boundary nhanh và ổn định.

Hai builder chính:

- `InProcessServerBuilder`: tạo server test với tên định danh.
- `InProcessChannelBuilder`: tạo channel trỏ tới server có cùng tên.

Dependency test cần có `grpc-inprocess` cùng release line với các thư viện gRPC Java khác:

```kotlin
dependencies {
    testImplementation("io.grpc:grpc-inprocess:<grpc-version>")
}
```

Thay `<grpc-version>` bằng version được quản lý tập trung trong BOM hoặc dependency constraints của dự án. Không tự thêm một version khác với `grpc-api`, `grpc-stub` và các artifact gRPC đang dùng.

In-process test không kiểm tra TLS handshake, certificate, DNS, load balancing, HTTP/2 proxy hoặc cấu hình socket. Những nội dung đó cần test qua transport thật.

## 4. Dựng fake service bằng generated ImplBase

Giả sử contract có RPC unary:

```proto
syntax = "proto3";

package catalog.v1;
option java_package = "dev.example.catalog.v1";
option java_multiple_files = true;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (Product);
}

message GetProductRequest {
  string product_id = 1;
}

message Product {
  string product_id = 1;
  string name = 2;
}
```

gRPC Java plugin sinh `CatalogServiceGrpc.CatalogServiceImplBase`. Test có thể kế thừa base class này để tạo fake service:

```java
final class FakeCatalogService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<Product> observer) {

        if ("missing".equals(request.getProductId())) {
            observer.onError(
                    Status.NOT_FOUND
                            .withDescription("product not found")
                            .asRuntimeException());
            return;
        }

        Product response = Product.newBuilder()
                .setProductId(request.getProductId())
                .setName("Keyboard")
                .build();

        observer.onNext(response);
        observer.onCompleted();
    }
}
```

Fake service có thể trả dữ liệu cố định, mô phỏng lỗi hoặc ghi nhận request để test assertion. Nó nên giữ logic tối thiểu và xác định; không sao chép toàn bộ implementation production vào test.

## 5. Tạo in-process server và channel trong JUnit

Ví dụ JUnit 5 tạo server trước mỗi test và đóng tài nguyên sau test:

```java
class CatalogStubTest {

    private Server server;
    private ManagedChannel channel;
    private CatalogServiceGrpc.CatalogServiceBlockingStub blockingStub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .directExecutor()
                .addService(new FakeCatalogService())
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName)
                .directExecutor()
                .build();

        blockingStub = CatalogServiceGrpc.newBlockingStub(channel);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            channel.awaitTermination(5, TimeUnit.SECONDS);
        }
        if (server != null) {
            server.shutdownNow();
            server.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Tên server được tạo riêng cho mỗi test để tránh xung đột khi test chạy song song. Channel và server đều là tài nguyên cần đóng; không để thread hoặc call còn hoạt động sau test.

`directExecutor()` chạy callback trực tiếp trên executor của call, giúp test đơn giản và giảm nondeterminism do scheduling. Nó không mô phỏng đầy đủ concurrency của production. Với test race, cancellation, callback thread hoặc backpressure, hãy thêm test dùng executor riêng và đồng bộ bằng latch.

## 6. Kiểm tra unary response

Sau khi tạo stub, test gọi RPC giống client thật:

```java
@Test
void blockingStubReturnsProduct() {
    GetProductRequest request = GetProductRequest.newBuilder()
            .setProductId("product-42")
            .build();

    Product response = blockingStub.getProduct(request);

    assertEquals("product-42", response.getProductId());
    assertEquals("Keyboard", response.getName());
}
```

Test này đi qua generated blocking stub, method descriptor, channel in-process, fake server implementation và response observer. Nó phù hợp để xác minh request/response mapping của gateway hoặc generated client API.

Nếu test chỉ gọi trực tiếp `FakeCatalogService.getProduct()` thì không kiểm tra stub, marshalling hoặc gRPC call lifecycle. Đó là unit test cho service implementation, có giá trị riêng nhưng không thay thế stub test.

## 7. Kiểm tra gRPC status

Fake service có thể mô phỏng lỗi nghiệp vụ hoặc transport status:

```java
@Test
void blockingStubPreservesNotFoundStatus() {
    GetProductRequest request = GetProductRequest.newBuilder()
            .setProductId("missing")
            .build();

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> blockingStub.getProduct(request));

    assertEquals(Status.Code.NOT_FOUND,
            error.getStatus().getCode());
}
```

Nên kiểm tra status code và metadata/trailers nếu chúng là một phần contract. Không phụ thuộc quá mức vào error description vì nội dung mô tả có thể thay đổi hoặc bị chuẩn hóa bởi lớp gateway.

Với application gateway, có thể thêm test xác minh `NOT_FOUND` được ánh xạ sang exception nghiệp vụ phù hợp. Test đó nên kiểm tra mapping ở gateway/application boundary, không lặp lại toàn bộ kiểm thử Protobuf transport.

## 8. Kiểm tra asynchronous và future stub

### Asynchronous stub

Async stub dùng `StreamObserver`. Test phải chờ callback hoàn tất bằng latch có timeout để không treo suite:

```java
@Test
void asyncStubReturnsResponse() throws InterruptedException {
    CountDownLatch completed = new CountDownLatch(1);
    AtomicReference<Product> result = new AtomicReference<>();
    AtomicReference<Throwable> failure = new AtomicReference<>();

    var asyncStub = CatalogServiceGrpc.newStub(channel);
    asyncStub.getProduct(
            GetProductRequest.newBuilder()
                    .setProductId("product-42")
                    .build(),
            new StreamObserver<>() {
                @Override
                public void onNext(Product value) {
                    result.set(value);
                }

                @Override
                public void onError(Throwable error) {
                    failure.set(error);
                    completed.countDown();
                }

                @Override
                public void onCompleted() {
                    completed.countDown();
                }
            });

    assertTrue(completed.await(2, TimeUnit.SECONDS));
    assertNull(failure.get());
    assertEquals("product-42", result.get().getProductId());
}
```

Không dùng vòng lặp chờ bận hoặc sleep tùy tiện. Latch giúp test chờ đúng callback; timeout làm test thất bại có giới hạn nếu callback không đến.

### Future stub

Future stub phù hợp với unary RPC:

```java
@Test
void futureStubCompletesWithProduct() throws Exception {
    var futureStub = CatalogServiceGrpc.newFutureStub(channel);

    ListenableFuture<Product> future = futureStub.getProduct(
            GetProductRequest.newBuilder()
                    .setProductId("product-42")
                    .build());

    Product response = future.get(2, TimeUnit.SECONDS);
    assertEquals("product-42", response.getProductId());
}
```

Dùng `get(timeout, unit)` thay vì chờ vô hạn. Khi test failure, timeout giúp chỉ ra call không hoàn tất thay vì làm CI treo.

## 9. Kiểm tra streaming stub

Generated asynchronous stub hỗ trợ server-streaming, client-streaming và bidirectional streaming. Test nên xác minh số message, thứ tự, completion và error lifecycle.

Ví dụ fake server-streaming service:

```java
final class FakeInventoryService
        extends InventoryServiceGrpc.InventoryServiceImplBase {

    @Override
    public void watchInventory(
            WatchInventoryRequest request,
            StreamObserver<InventoryUpdate> observer) {
        observer.onNext(update("product-1", 4));
        observer.onNext(update("product-2", 9));
        observer.onCompleted();
    }
}
```

Client test có thể thu thập các message:

```java
CountDownLatch completed = new CountDownLatch(1);
List<InventoryUpdate> updates =
        new CopyOnWriteArrayList<>();
AtomicReference<Throwable> failure = new AtomicReference<>();

asyncStub.watchInventory(request, new StreamObserver<>() {
    @Override
    public void onNext(InventoryUpdate value) {
        updates.add(value);
    }

    @Override
    public void onError(Throwable error) {
        failure.set(error);
        completed.countDown();
    }

    @Override
    public void onCompleted() {
        completed.countDown();
    }
});

assertTrue(completed.await(2, TimeUnit.SECONDS));
assertNull(failure.get());
assertEquals(2, updates.size());
```

Với client-streaming hoặc bidirectional streaming, test cần kiểm tra request observer được đóng bằng `onCompleted()`, server trả response đúng và lỗi ở một phía được truyền về phía kia theo contract. Không gửi thêm message sau terminal signal. Nếu kiểm tra flow control/backpressure, dùng executor và lượng message đủ lớn để kiểm tra hành vi thay vì chỉ dùng `directExecutor()`.

## 10. Kiểm tra deadline và cancellation

Deadline là call option, vì vậy test nên đặt deadline trên stub dẫn xuất:

```java
var shortDeadlineStub = blockingStub.withDeadlineAfter(
        50, TimeUnit.MILLISECONDS);
```

Fake service có thể chờ một latch hoặc thực hiện công việc có thời gian kiểm soát để test deadline. Dùng timeout có biên an toàn và tránh dựa vào một khoảng `Thread.sleep()` rất ngắn, vì scheduling trên CI có thể dao động.

Các điều cần xác minh:

- Call vượt deadline trả `DEADLINE_EXCEEDED`.
- Client cancellation được server quan sát nếu handler theo dõi cancellation.
- Công việc server có thể dừng hoặc tránh side effect khi call đã bị hủy.
- Retry không tự phát sinh nếu call có side effect chưa được bảo vệ bằng idempotency.

In-process transport phù hợp với test logic deadline/cancellation, nhưng test socket timeout, proxy timeout và network interruption cần transport thật.

## 11. Kiểm tra metadata và interceptor

Metadata là dữ liệu theo từng RPC. Có thể dùng client interceptor để gắn header và server interceptor/fake service để xác minh server nhận đúng giá trị.

Ví dụ khai báo key:

```java
static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
                "x-request-id",
                Metadata.ASCII_STRING_MARSHALLER);
```

Trong test, tạo metadata mới cho call:

```java
Metadata headers = new Metadata();
headers.put(REQUEST_ID, "test-request-17");

var callStub = blockingStub.withInterceptors(
        MetadataUtils.newAttachHeadersInterceptor(headers));
```

Fake service hoặc server interceptor có thể đọc header và ghi giá trị vào `AtomicReference` để assertion. Không dùng chung một `Metadata` mutable giữa nhiều test/call đồng thời.

Test interceptor nên kiểm tra:

- Header được gắn đúng key và value.
- Interceptor không ghi đè metadata của call khác.
- Tracing/metrics chỉ được ghi một lần.
- Không đưa token hoặc dữ liệu nhạy cảm vào log.
- Response headers/trailers được đọc đúng ở client nếu API yêu cầu.

## 12. Test generated stub hay mock stub?

Generated stub là API transport. Mock trực tiếp stub có thể hữu ích trong một số unit test nhưng thường không chứng minh được serialization, method path, interceptor hay status mapping. Một số generated stub class là `final`, nên khả năng mock còn phụ thuộc cấu hình Mockito/mock maker.

Quy tắc thực tế:

- Application service: ưu tiên phụ thuộc interface gateway và mock gateway trong unit test.
- Gateway: dùng generated stub thật với in-process server để kiểm tra request/response và lỗi.
- Server implementation: test logic nghiệp vụ riêng; bổ sung RPC test để kiểm tra observer/status.
- Spring configuration: kiểm tra bean wiring và service registration bằng application context test.
- Transport/security: dùng TCP/TLS test riêng.

Nếu cần mock stub để cô lập một nhánh rất nhỏ, hãy giữ test đó ở tầng unit và không coi nó là bằng chứng gRPC client hoạt động đúng.

## 13. Spring integration test

In-process test không chứng minh Spring đã đăng ký đúng service bean hoặc tạo client channel theo cấu hình ứng dụng. Một Spring integration test nên:

1. Khởi động application context với gRPC server configuration thực tế.
2. Dùng cổng ngẫu nhiên hoặc cơ chế test port mà Spring gRPC starter hỗ trợ.
3. Lấy endpoint/port từ context thay vì hard-code cổng dùng chung.
4. Tạo generated stub qua channel test hoặc inject client bean đã cấu hình.
5. Gọi RPC qua server do Spring quản lý.
6. Xác minh service registration, interceptor, security và exception mapping.
7. Đóng channel test và context đúng lifecycle.

Tên annotation, property bật random port và cách lấy port phụ thuộc Spring gRPC starter/version. Dùng test support của starter đang có trong dự án; không giả định mọi starter đều dùng cùng annotation hoặc property.

Đối với TLS, cấu hình test certificate và trust store giống mô hình production nhưng dùng certificate test riêng. In-process channel không thực hiện TLS handshake nên không thể thay thế bài test này.

## 14. Cô lập test và quản lý tài nguyên

Test gRPC dễ gây flaky nếu channel/server còn sống sau test hoặc nhiều test dùng cùng tên server/port.

Checklist:

- Dùng `InProcessServerBuilder.generateName()` cho mỗi server fixture.
- Mỗi test hoặc test class có ownership rõ ràng cho server/channel.
- Luôn shutdown channel và server trong `@AfterEach`/`@AfterAll`.
- Chờ termination với timeout hữu hạn.
- Không chia sẻ mutable observer, metadata hoặc request builder giữa test.
- Không dùng port cố định khi test chạy song song.
- Không phụ thuộc thứ tự test.
- Dùng dữ liệu fixture xác định và không gọi dịch vụ bên ngoài không cần thiết.

Nếu dùng JUnit extension hoặc test fixture dùng chung, bảo đảm cleanup vẫn chạy khi assertion hoặc setup thất bại. Tránh để exception trong setup khiến một channel đã tạo không được đóng.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Test gọi trực tiếp service nhưng stub lỗi | Test không đi qua generated stub/channel | Thêm in-process RPC test |
| CI treo ở async callback | Chờ không có timeout hoặc observer không terminal | Dùng latch/future với timeout |
| Test pass nhưng Spring không đăng ký service | Chỉ dùng fake in-process server | Bổ sung Spring application context test |
| Test pass nhưng TLS production lỗi | In-process transport không có TLS | Test qua TCP/TLS với certificate test |
| Test song song đụng server name | Dùng tên in-process cố định | Sinh tên riêng cho mỗi fixture |
| Channel/thread còn sót sau test | Không shutdown hoặc không await termination | Cleanup server/channel trong lifecycle hook |
| Mock stub không hoạt động | Generated stub là final hoặc API không mock được | Mock gateway interface hoặc dùng fake server |
| Không phát hiện sai method path | Chỉ test mapper hoặc mock stub | Gọi generated stub tới server fixture |
| Metadata giữa test bị lẫn | Dùng chung Metadata mutable | Tạo metadata riêng cho từng call |
| Test deadline chập chờn | Dựa vào sleep quá ngắn hoặc executor trực tiếp | Dùng latch, timeout có biên an toàn và executor phù hợp |

## 16. Bài tập thực hành

**Tình huống:** `CatalogGateway` dùng blocking stub để gọi `GetProduct`; một client khác dùng async stub cho `WatchInventory`. Ứng dụng Spring cần xác minh response, lỗi NOT_FOUND, deadline và metadata request ID.

Hãy thực hiện:

1. Thêm `grpc-inprocess` test dependency cùng release line với gRPC Java runtime.
2. Viết fake `CatalogServiceImplBase` trả product hoặc `NOT_FOUND` theo product ID.
3. Dựng in-process server và channel với tên duy nhất trong JUnit 5.
4. Tạo blocking stub và kiểm thử request/response qua RPC thật.
5. Kiểm thử `StatusRuntimeException` giữ đúng `NOT_FOUND`.
6. Tạo async stub, thu thập nhiều inventory update bằng observer và latch có timeout.
7. Gắn `x-request-id` bằng client interceptor và xác minh server nhận đúng metadata.
8. Dùng stub dẫn xuất với deadline ngắn; xác minh `DEADLINE_EXCEEDED` bằng fake service có thời gian chờ kiểm soát.
9. Shutdown channel/server và await termination sau mỗi test.
10. Bổ sung một Spring integration test qua server do application context quản lý; nếu có TLS, kiểm thử qua TCP/TLS riêng.

**Tiêu chí hoàn thành:** test dùng generated stub thật; fake service có hành vi xác định; response/status/metadata/deadline được kiểm tra; async test không treo; tài nguyên được đóng; phân biệt rõ in-process test với Spring/transport integration test.

## 17. Ghi nhớ

Test generated stub bằng cách gọi RPC thật tới fake service, thay vì chỉ gọi trực tiếp implementation hoặc mock mọi lớp transport. `InProcessServerBuilder` và `InProcessChannelBuilder` cho phép kiểm tra generated stub, Protobuf marshalling, method routing, status, metadata và streaming mà không mở TCP socket. Dùng JUnit lifecycle để tạo tên server riêng và luôn shutdown channel/server. Async/future test phải có timeout. In-process test không kiểm tra Spring bean registration, TLS, DNS hay load balancing; bổ sung Spring application context và TCP/TLS integration test cho các ranh giới đó. Ở tầng application, mock gateway interface để kiểm tra orchestration; ở tầng gateway, dùng stub thật để kiểm tra hành vi gRPC.
