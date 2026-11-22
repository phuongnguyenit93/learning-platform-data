# Kiểm tra status code contract

Trong Spring gRPC, status code là kết quả RPC mà client dùng để quyết định cách xử lý lỗi: sửa request, xác thực lại, báo tài nguyên không tồn tại, thử lại hay dừng. Hai phiên bản server có thể cùng trả response protobuf đúng cấu trúc nhưng vẫn không tương thích nếu một phiên bản đổi `NOT_FOUND` thành `INTERNAL` cho cùng điều kiện nghiệp vụ. Contract test cho status code xác minh mỗi method trả đúng mã cho các kết quả đã công bố.

Status là một phần của API công khai, không chỉ là thông tin phục vụ log. Bài này trình bày cách định nghĩa status contract theo method, ánh xạ exception nhất quán, kiểm tra unary và streaming bằng generated stub, xác minh trailers khi cần và đánh giá tác động của status tới retry/cancellation.

## 1. Status code thuộc contract của từng RPC

Một method có thể có nhiều kết quả hợp lệ:

| Method/điều kiện | Status contract | Ý nghĩa với client |
| --- | --- | --- |
| `GetProduct` với ID hợp lệ và có sản phẩm | `OK` | Nhận Product response |
| `GetProduct` với ID không tồn tại | `NOT_FOUND` | Tài nguyên không tồn tại |
| `CreateProduct` với field bắt buộc sai | `INVALID_ARGUMENT` | Sửa request trước khi gửi lại |
| `CreateProduct` với ID đã được dùng | `ALREADY_EXISTS` | Chọn ID khác hoặc đọc tài nguyên hiện có |
| RPC cần credential nhưng credential thiếu/sai | `UNAUTHENTICATED` | Cung cấp credential hợp lệ |
| Caller đã xác thực nhưng không có quyền | `PERMISSION_DENIED` | Không được phép thực hiện hành động |
| Điều kiện trạng thái hiện tại chưa thỏa | `FAILED_PRECONDITION` | Sửa trạng thái trước khi gọi lại |
| Xung đột đồng thời cần retry toàn bộ transaction | `ABORTED` | Có thể chạy lại transaction theo policy |
| Vượt quota hoặc giới hạn tài nguyên | `RESOURCE_EXHAUSTED` | Giảm tải/chờ quota được cấp lại |
| Backend tạm thời không khả dụng | `UNAVAILABLE` | Có thể retry nếu operation an toàn |

Không định nghĩa một status chung cho mọi lỗi. Status phải phản ánh điều client có thể làm tiếp theo. Cùng một exception Java có thể cần status khác nhau tùy use case; vì vậy mapping cần dựa trên semantics và không chỉ dựa vào tên class.

## 2. Ý nghĩa của các canonical gRPC status

gRPC định nghĩa các status code chuẩn. Các nhóm thường gặp trong API ứng dụng:

| Code | Dùng khi |
| --- | --- |
| `OK` | RPC hoàn tất thành công |
| `CANCELLED` | Call bị caller hủy hoặc operation bị cancel |
| `UNKNOWN` | Lỗi không xác định được nguyên nhân cụ thể; không nên dùng thay cho mapping đã biết |
| `INVALID_ARGUMENT` | Request sai độc lập với trạng thái hệ thống |
| `DEADLINE_EXCEEDED` | Deadline hết trước khi RPC hoàn tất; operation phía server có thể đã hoàn thành nhưng response đến muộn |
| `NOT_FOUND` | Tài nguyên được yêu cầu không tồn tại |
| `ALREADY_EXISTS` | Tài nguyên tạo mới đã tồn tại |
| `PERMISSION_DENIED` | Caller không có quyền, dù đã xác thực |
| `RESOURCE_EXHAUSTED` | Hết quota, giới hạn hoặc tài nguyên |
| `FAILED_PRECONDITION` | Hệ thống phải được đưa về trạng thái phù hợp trước khi retry |
| `ABORTED` | Operation bị hủy do xung đột; retry thường ở mức transaction/workflow |
| `OUT_OF_RANGE` | Giá trị nằm ngoài miền hợp lệ, ví dụ đọc quá cuối một range |
| `UNAUTHENTICATED` | Không có credential hợp lệ |
| `UNAVAILABLE` | Service/backend tạm thời không sẵn sàng |
| `DATA_LOSS` | Mất hoặc hỏng dữ liệu nghiêm trọng |
| `UNIMPLEMENTED` | Method hoặc chức năng chưa được hỗ trợ |
| `INTERNAL` | Lỗi nội bộ bất ngờ của server |

Phân biệt các code gần nghĩa:

- `INVALID_ARGUMENT`: request không hợp lệ bất kể trạng thái hệ thống, ví dụ quantity âm.
- `FAILED_PRECONDITION`: request có thể hợp lệ nhưng trạng thái hiện tại chưa cho phép, ví dụ sản phẩm đang bị khóa.
- `ABORTED`: xung đột khiến transaction cần được chạy lại từ đầu.
- `OUT_OF_RANGE`: giá trị hợp lệ về kiểu nhưng vượt miền/ranh giới được hỗ trợ.
- `UNAUTHENTICATED` và `PERMISSION_DENIED`: lần lượt là chưa xác minh được danh tính và đã xác minh nhưng thiếu quyền.

Chọn sai code khiến client retry sai, hiển thị thông báo sai hoặc xử lý bảo mật không đúng.

## 3. Viết status mapping tập trung

Không để mỗi endpoint tự chọn status theo cảm tính. Một mapper tập trung giúp các service giữ semantics nhất quán:

```java
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;

public final class GrpcStatusMapper {

    public StatusRuntimeException toRuntimeException(Throwable error) {
        if (error instanceof StatusRuntimeException statusError) {
            return statusError;
        }
        if (error instanceof StatusException statusError) {
            return statusError.getStatus()
                    .asRuntimeException(statusError.getTrailers());
        }
        if (error instanceof ProductNotFoundException) {
            return Status.NOT_FOUND
                    .withDescription("Product not found")
                    .asRuntimeException();
        }
        if (error instanceof InvalidProductRequestException) {
            return Status.INVALID_ARGUMENT
                    .withDescription("Invalid product request")
                    .asRuntimeException();
        }
        if (error instanceof DuplicateProductException) {
            return Status.ALREADY_EXISTS
                    .withDescription("Product already exists")
                    .asRuntimeException();
        }
        if (error instanceof ProductLockedException) {
            return Status.FAILED_PRECONDITION
                    .withDescription("Product cannot be changed in its current state")
                    .asRuntimeException();
        }
        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }
}
```

Mapper giữ nguyên `StatusRuntimeException` hoặc status/trailers của `StatusException` đã được chủ động tạo. Các exception nghiệp vụ được ánh xạ rõ ràng; lỗi không nhận diện được trở thành `INTERNAL` với mô tả an toàn. Trong production, log exception đầy đủ ở server với trace/correlation ID và lọc dữ liệu nhạy cảm.

Không dùng `Status.fromThrowable(error)` như chính sách duy nhất. Hàm này hữu ích để tìm status trong cause chain, nhưng exception Java thông thường có thể trở thành `UNKNOWN`. Mapper cần xử lý các lỗi nghiệp vụ đã biết trước khi chuyển lỗi ra transport.

## 4. Chọn status theo hành vi use case

Ví dụ handler unary:

```java
@GrpcService
public class CatalogGrpcService
        extends CatalogServiceGrpc.CatalogServiceImplBase {

    private final CatalogUseCase catalog;
    private final GrpcStatusMapper statusMapper;

    public CatalogGrpcService(
            CatalogUseCase catalog,
            GrpcStatusMapper statusMapper) {
        this.catalog = catalog;
        this.statusMapper = statusMapper;
    }

    @Override
    public void getProduct(
            GetProductRequest request,
            StreamObserver<Product> observer) {
        try {
            Product product = catalog.getProduct(request.getProductId());
            observer.onNext(product);
            observer.onCompleted();
        } catch (RuntimeException error) {
            observer.onError(statusMapper.toRuntimeException(error));
        }
    }
}
```

Sau khi gọi `onError`, không gọi tiếp `onCompleted`. Mỗi RPC chỉ có một terminal outcome. Nếu service xử lý bất đồng bộ, exception phải được ánh xạ ở callback/future completion nơi lỗi thực sự xảy ra; interceptor đồng bộ không thể bắt exception ném ra sau khi callback đã trả về.

Một bảng mapping cần được review cùng application owner:

| Tình huống nghiệp vụ | Status gợi ý | Lý do |
| --- | --- | --- |
| Product ID rỗng/sai định dạng | `INVALID_ARGUMENT` | Client sửa request |
| Product không tồn tại | `NOT_FOUND` | Tài nguyên vắng mặt |
| Product đã tồn tại khi create | `ALREADY_EXISTS` | Xung đột định danh |
| Product đang khóa nên không thể sửa | `FAILED_PRECONDITION` | Cần thay đổi trạng thái trước |
| Optimistic lock conflict cần chạy lại transaction | `ABORTED` | Retry workflow ở mức cao hơn |
| Caller chưa đăng nhập | `UNAUTHENTICATED` | Credential không hợp lệ |
| Caller không thuộc tenant được phép | `PERMISSION_DENIED` | Danh tính hợp lệ nhưng thiếu quyền |
| Dependency tạm thời không sẵn sàng | `UNAVAILABLE` | Có thể phục hồi sau |

Đây là mapping theo semantics minh họa; domain cụ thể cần quyết định contract phù hợp và giữ ổn định giữa các phiên bản.

## 5. Kiểm tra status bằng generated stub

Với blocking stub, status lỗi được ném dưới dạng `StatusRuntimeException`. Test cần assert `Status.Code`, không chỉ kiểm tra có exception:

```java
@Test
void missingProductReturnsNotFound() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getProduct(
                    GetProductRequest.newBuilder()
                            .setProductId("missing")
                            .build()));

    assertEquals(Status.Code.NOT_FOUND,
            error.getStatus().getCode());
}

@Test
void invalidProductIdReturnsInvalidArgument() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getProduct(
                    GetProductRequest.newBuilder()
                            .setProductId("")
                            .build()));

    assertEquals(Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());
}
```

Với RPC thành công, blocking stub trả response bình thường; điều đó xác nhận status cuối là `OK`. Với async stub, success được biểu diễn bằng `onCompleted`; lỗi đến qua `onError`. Client có thể dùng `Status.fromThrowable(error)` để lấy status trong callback.

Không assert toàn bộ description nếu đó không phải phần contract. Description có thể được chỉnh để dễ hiểu hơn; hãy assert code ổn định và chỉ assert description/trailers khi client thực sự dựa vào chúng.

## 6. Provider contract test với in-process server

In-process server cho phép gọi service implementation bằng generated stub mà không cần mở TCP port:

```java
class CatalogStatusContractTest {
    private Server server;
    private ManagedChannel channel;
    private CatalogServiceGrpc.CatalogServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String name = InProcessServerBuilder.generateName();
        server = InProcessServerBuilder.forName(name)
                .addService(new CatalogGrpcService(
                        testCatalogUseCase(), new GrpcStatusMapper()))
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
    void missingProductUsesPublishedStatus() {
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

Fixture `testCatalogUseCase()` đại diện use case có thể điều khiển kết quả. Nên có test cho từng nhánh status quan trọng và một test cho lỗi không dự kiến để xác minh server không lộ exception nội bộ. In-process test xác minh service behavior qua gRPC runtime; Spring integration test bổ sung xác minh bean, interceptor, security và status mapper được đăng ký đúng trong application context.

## 7. Kiểm tra trailers và error details khi thuộc contract

Status code là phần chính của kết quả lỗi. Trailers có thể mang metadata bổ sung mà client cần, nhưng chỉ đưa vào contract khi có use case rõ ràng. Ví dụ:

```java
private static final Metadata.Key<String> ERROR_REASON =
        Metadata.Key.of(
                "error-reason",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata trailers = new Metadata();
trailers.put(ERROR_REASON, "PRODUCT_LOCKED");

throw Status.FAILED_PRECONDITION
        .withDescription("Product cannot be changed")
        .asRuntimeException(trailers);
```

Client test có thể xác minh trailer:

```java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.updateProduct(request));

assertEquals(Status.Code.FAILED_PRECONDITION,
        error.getStatus().getCode());
assertEquals("PRODUCT_LOCKED",
        error.getTrailers().get(ERROR_REASON));
```

Nếu dùng structured error details như `google.rpc.Status` và detail message, version/type của detail cũng là contract cần quản lý. Không gửi stack trace, SQL, file path, hostname nội bộ, token hoặc dữ liệu cá nhân qua description/trailers. Không ghi toàn bộ trailers vào log nếu có thể chứa credential.

## 8. Status ảnh hưởng retry như thế nào?

Status code giúp client phân loại retry, nhưng không tự động khẳng định retry an toàn:

| Status | Hành vi thường cân nhắc |
| --- | --- |
| `UNAVAILABLE` | Retry có backoff nếu operation idempotent hoặc có idempotency key |
| `ABORTED` | Có thể retry transaction/workflow từ đầu |
| `RESOURCE_EXHAUSTED` | Chờ quota/backoff theo policy; không retry dồn dập |
| `DEADLINE_EXCEEDED` | Chỉ retry nếu còn ngân sách thời gian và biết operation an toàn |
| `CANCELLED` | Thường tôn trọng việc caller đã hủy |
| `INVALID_ARGUMENT` | Không retry cùng request; cần sửa input |
| `FAILED_PRECONDITION` | Sửa trạng thái hệ thống trước khi gọi lại |
| `UNAUTHENTICATED` | Làm mới/cung cấp credential trước |
| `PERMISSION_DENIED` | Không retry nếu quyền không thay đổi |

Không retry tự động mọi lỗi `INTERNAL` hoặc `UNKNOWN`. Với thao tác ghi, server có thể đã commit nhưng response bị mất; retry không có idempotency protection có thể tạo dữ liệu trùng. Contract test nên xác minh status phù hợp để client có thể áp dụng retry policy mà không gây side effect lặp.

## 9. Kiểm tra status cho streaming, deadline và cancellation

Với streaming RPC, status cuối chỉ xuất hiện khi stream kết thúc. Một stream có thể phát một số message rồi kết thúc bằng lỗi; client cần kiểm tra cả message đã nhận lẫn terminal status:

```java
List<ProductEvent> received = new ArrayList<>();

StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> {
            Iterator<ProductEvent> events =
                    stub.watchProduct(request);
            while (events.hasNext()) {
                received.add(events.next());
            }
        });

assertFalse(received.isEmpty());
assertEquals(Status.Code.RESOURCE_EXHAUSTED,
        error.getStatus().getCode());
```

Ví dụ giả định contract cho phép phát một số event rồi kết thúc do quota. Nếu contract yêu cầu all-or-nothing, server phải thiết kế stream semantics tương ứng và test không nên chấp nhận partial result.

Deadline test nên đặt timeout hữu hạn và dùng fixture có latch để điều khiển lúc server hoàn tất; tránh dựa hoàn toàn vào `Thread.sleep` vì dễ flaky. Client thường thấy `DEADLINE_EXCEEDED` khi deadline hết trước khi kết quả đến. Tuy nhiên, server operation có thể đã hoàn tất dù client không nhận được response kịp hạn.

Khi client chủ động cancel, client thường thấy `CANCELLED`; server cần quan sát cancellation qua call context/`ServerCallStreamObserver` và dừng producer. Không giả định hai phía luôn quan sát cùng status trong mọi race giữa deadline và transport cancellation.

## 10. Checklist status contract

- [ ] Mỗi method có bảng điều kiện và status code được công bố.
- [ ] Dùng `INVALID_ARGUMENT` cho request sai, `NOT_FOUND` cho tài nguyên vắng mặt và phân biệt `UNAUTHENTICATED` với `PERMISSION_DENIED`.
- [ ] Phân biệt `FAILED_PRECONDITION`, `ABORTED` và `OUT_OF_RANGE`.
- [ ] Exception nghiệp vụ được ánh xạ tập trung, nhất quán.
- [ ] Giữ nguyên status/trailers đã được chủ động tạo.
- [ ] Lỗi không dự kiến trả status an toàn, không lộ chi tiết nội bộ.
- [ ] Provider test gọi bằng generated stub và assert `Status.Code`.
- [ ] Streaming test xác minh terminal status, partial message semantics và cancellation.
- [ ] Trailers/error details chỉ được assert khi thuộc contract công khai.
- [ ] Retry policy xét status, idempotency, backoff và deadline.
- [ ] Deadline test có timeout hữu hạn và điều khiển được.
- [ ] Spring integration test xác minh mapper/interceptor/security được đăng ký thực tế.

**Tự kiểm tra**

**Câu 1.** Vì sao contract test nên assert `Status.Code` thay vì chỉ assert có exception?

*Đáp án:* Nhiều status có thể biểu diễn bằng exception phía client nhưng dẫn đến cách xử lý khác nhau. Assert code xác minh server giữ đúng semantics mà consumer dựa vào.

**Câu 2.** Khi nào dùng `FAILED_PRECONDITION` thay vì `INVALID_ARGUMENT`?

*Đáp án:* `INVALID_ARGUMENT` dùng khi bản thân request sai; `FAILED_PRECONDITION` dùng khi request có thể hợp lệ nhưng trạng thái hiện tại chưa cho phép thực hiện.

**Câu 3.** Vì sao `UNAVAILABLE` không đồng nghĩa luôn retry an toàn?

*Đáp án:* Operation phía server có thể đã thực hiện nhưng response không tới client. Với thao tác ghi, retry có thể lặp side effect nếu không có idempotency key hoặc cơ chế deduplication.

**Câu 4.** Client async nhận status lỗi ở đâu?

*Đáp án:* Trong callback `StreamObserver.onError`; dùng `Status.fromThrowable` để lấy status. Blocking stub thường ném `StatusRuntimeException`.

**Câu 5.** Vì sao streaming contract test phải kiểm tra terminal status ngoài message?

*Đáp án:* Stream có thể phát một phần message rồi kết thúc bằng lỗi. Consumer cần biết partial result có hợp lệ không và status cuối quyết định cách xử lý tiếp.

Kiểm tra status code contract bảo vệ cách client diễn giải kết quả RPC. Hãy định nghĩa status theo từng điều kiện nghiệp vụ, ánh xạ exception tập trung, kiểm tra code qua generated stub và xác minh terminal status của streaming call. Khi status, retry và idempotency được kiểm thử cùng nhau, các phiên bản Spring gRPC có thể thay đổi implementation mà vẫn giữ hành vi lỗi ổn định cho consumer.
