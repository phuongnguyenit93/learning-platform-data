# Assertion status, description và metadata

Trong Spring gRPC, một lỗi RPC có ba phần thông tin quan trọng mà client có thể quan sát: canonical status code, description gắn với status và metadata được gửi trong trailers. Status code xác định loại kết quả để client quyết định hành vi; description giúp người vận hành hoặc người dùng hiểu lỗi; metadata mang mã lỗi nghiệp vụ, request ID hoặc thông tin máy đọc được mà hai phía đã thống nhất.

Error contract test cần xác minh cả ba phần ở ranh giới RPC. Một test chỉ kiểm tra có exception là chưa đủ: NOT_FOUND, INVALID_ARGUMENT và UNAVAILABLE đều có thể xuất hiện dưới dạng StatusRuntimeException nhưng dẫn đến cách xử lý rất khác nhau. Bài này trình bày cách tạo status/trailers ở server, đọc chúng ở client, viết assertion ổn định và tránh làm lộ dữ liệu nội bộ.

## 1. Ba phần của một gRPC error response

| Thành phần | Vai trò | Client đọc bằng |
| --- | --- | --- |
| Status code | Phân loại kết quả RPC theo canonical gRPC status | Status.fromThrowable(error).getCode() |
| Description | Thông điệp ngắn gắn với Status, thường dành cho chẩn đoán hoặc hiển thị | Status.getDescription() |
| Trailers metadata | Các key/value bổ sung theo contract, ví dụ error-code và request ID | StatusRuntimeException.getTrailers() |

Ví dụ một lỗi không tìm thấy đơn hàng có thể có:
- Status: NOT_FOUND.
- Description: Order was not found.
- Trailers: error-code=ORDER_NOT_FOUND và x-request-id=req-42.

Status code là tín hiệu điều khiển chính. Client không nên phân tích chuỗi description để quyết định retry hoặc nhánh nghiệp vụ. Nếu cần mã máy đọc được, định nghĩa custom trailer key ổn định hoặc dùng structured error detail theo contract. Description có thể thay đổi câu chữ theo localization hoặc cải thiện trải nghiệm mà không làm thay đổi semantics.

gRPC đã dành các trường protocol cho status và message. Ứng dụng không tự tạo metadata key grpc-status hoặc grpc-message; hãy dùng Status API để thiết lập chúng và custom key cho metadata của ứng dụng.

## 2. Chọn status code đúng với tình huống

Status phải mô tả điều client có thể làm tiếp theo:

| Tình huống | Status phù hợp | Hướng xử lý của client |
| --- | --- | --- |
| Request thiếu ID hoặc sai định dạng | INVALID_ARGUMENT | Sửa request |
| Tài nguyên không tồn tại | NOT_FOUND | Hiển thị trạng thái không tìm thấy hoặc xử lý fallback |
| Tài nguyên đã tồn tại khi tạo | ALREADY_EXISTS | Đọc tài nguyên hiện có hoặc chọn định danh khác |
| Chưa xác thực được caller | UNAUTHENTICATED | Cung cấp/làm mới credential |
| Caller đã xác thực nhưng không có quyền | PERMISSION_DENIED | Không retry khi quyền không đổi |
| Trạng thái hiện tại chưa cho phép thao tác | FAILED_PRECONDITION | Thay đổi trạng thái trước |
| Xung đột transaction cần thử lại từ đầu | ABORTED | Retry workflow nếu an toàn |
| Dependency tạm thời không sẵn sàng | UNAVAILABLE | Retry có backoff nếu operation an toàn |
| Hết quota hoặc giới hạn tài nguyên | RESOURCE_EXHAUSTED | Giảm tải hoặc chờ quota |
| Deadline hết | DEADLINE_EXCEEDED | Xử lý kết quả chưa chắc chắn; retry có điều kiện |
| Lỗi bất ngờ phía server | INTERNAL | Báo lỗi hệ thống, không lộ chi tiết nội bộ |

Không dùng INTERNAL cho mọi lỗi để che việc thiếu mapping. Cũng không trả INVALID_ARGUMENT cho lỗi dependency. Status code là phần contract mà client có thể dựa vào để chọn retry, yêu cầu người dùng sửa input hoặc dừng thao tác.

## 3. Tạo status, description và trailers ở server

gRPC Java biểu diễn custom metadata bằng Metadata.Key. Key phải dùng chữ thường; key chứa bytes kết thúc bằng hậu tố -bin. Ví dụ định nghĩa hai key ASCII:

~~~java
public final class OrderErrorMetadata {
    private OrderErrorMetadata() {}

    public static final Metadata.Key<String> ERROR_CODE =
            Metadata.Key.of(
                    "error-code",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> REQUEST_ID =
            Metadata.Key.of(
                    "x-request-id",
                    Metadata.ASCII_STRING_MARSHALLER);
}
~~~

Tạo lỗi NOT_FOUND có description và trailers:

~~~java
public final class OrderGrpcErrors {
    private OrderGrpcErrors() {}

    public static StatusRuntimeException notFound(String requestId) {
        Metadata trailers = new Metadata();
        trailers.put(OrderErrorMetadata.ERROR_CODE, "ORDER_NOT_FOUND");
        trailers.put(OrderErrorMetadata.REQUEST_ID, requestId);

        return Status.NOT_FOUND
                .withDescription("Order was not found")
                .asRuntimeException(trailers);
    }
}
~~~

Server handler gửi exception qua onError:

~~~java
@GrpcService
public class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderRepository repository;

    public OrderGrpcService(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<Order> observer) {
        try {
            Order order = repository.findById(request.getOrderId())
                    .orElseThrow(OrderNotFoundException::new);

            observer.onNext(order);
            observer.onCompleted();
        } catch (OrderNotFoundException error) {
            observer.onError(
                    OrderGrpcErrors.notFound("req-test-42"));
        }
    }
}
~~~

req-test-42 chỉ là giá trị minh họa cho test. Trong ứng dụng thật, request ID nên đến từ metadata/interceptor hoặc tracing context theo từng call. Không lưu request ID vào field mutable của singleton service vì nhiều RPC có thể chạy đồng thời.

Khi đã gọi observer.onError, đó là terminal signal của RPC. Không gọi tiếp onCompleted hoặc onNext. Với exception không dự kiến, ánh xạ sang INTERNAL với description an toàn và log stack trace ở server; không gửi SQL, hostname nội bộ, file path, token hoặc stack trace qua trailers.

## 4. Assertion status code ở client

Blocking stub thường ném StatusRuntimeException khi RPC kết thúc bằng status khác OK. Dùng Status.fromThrowable để lấy canonical status:

~~~java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.getOrder(
                GetOrderRequest.newBuilder()
                        .setOrderId("missing")
                        .build()));

Status status = Status.fromThrowable(error);
assertEquals(Status.Code.NOT_FOUND, status.getCode());
~~~

Nếu test bắt trực tiếp StatusRuntimeException, có thể đọc error.getStatus(). Dùng Status.fromThrowable hữu ích khi error được bọc trong một exception khác hoặc đi qua callback layer; hàm này tìm status trong cause chain và có thể trả UNKNOWN nếu không tìm thấy status cụ thể.

Không chỉ assert exception type. Một thay đổi vô tình từ NOT_FOUND sang INTERNAL vẫn làm assertThrows(StatusRuntimeException.class) thành công, nhưng phá behavior contract.

## 5. Assertion description có chủ đích

Description lấy từ Status:

~~~java
Status status = Status.fromThrowable(error);
assertEquals("Order was not found", status.getDescription());
~~~

Chỉ assert chính xác toàn bộ description nếu câu chữ đó là một phần contract công khai và cần giữ ổn định. Trong nhiều API, description là thông điệp chẩn đoán có thể được chỉnh sửa; khi đó nên xác minh nó có mặt hoặc phù hợp với quy tắc an toàn, còn client logic dựa vào status code và error-code metadata.

Ví dụ kiểm tra description không rỗng:

~~~java
assertNotNull(status.getDescription());
assertFalse(status.getDescription().isBlank());
~~~

Không dùng description làm mã lỗi bằng cách so sánh chuỗi trong code production. Cũng không nhét dữ liệu nhạy cảm hoặc chi tiết implementation vào description vì giá trị này có thể được chuyển tới client và log ở nhiều nơi.

## 6. Assertion custom metadata trong trailers

Khi server tạo StatusRuntimeException bằng asRuntimeException(trailers), client có thể đọc custom metadata từ getTrailers():

~~~java
Metadata trailers = error.getTrailers();

assertNotNull(trailers);
assertEquals(
        "ORDER_NOT_FOUND",
        trailers.get(OrderErrorMetadata.ERROR_CODE));
assertEquals(
        "req-test-42",
        trailers.get(OrderErrorMetadata.REQUEST_ID));
~~~

Trailers có thể null nếu server không gửi custom metadata hoặc lỗi xảy ra trước khi metadata được tạo. Nếu contract yêu cầu một key, assert trailers khác null rồi assert value; nếu key là optional, kiểm tra null như một trường hợp hợp lệ.

Metadata key và marshaller phải khớp hai phía. Với ASCII value dùng ASCII_STRING_MARSHALLER. Với binary value dùng key kết thúc -bin và BINARY_BYTE_MARSHALLER:

~~~java
static final Metadata.Key<byte[]> ERROR_DETAIL =
        Metadata.Key.of(
                "error-detail-bin",
                Metadata.BINARY_BYTE_MARSHALLER);
~~~

Không tự base64 bytes trước khi đưa vào binary metadata; gRPC marshaller chịu trách nhiệm encoding wire. Không dùng cùng một key lúc là ASCII, lúc là binary.

## 7. Provider contract test bằng in-process server

Test qua generated stub xác minh status, description và trailers đi qua gRPC runtime. In-process transport nhanh và không cần mở TCP port:

~~~java
class OrderErrorContractTest {
    private Server server;
    private ManagedChannel channel;
    private OrderServiceGrpc.OrderServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();

        server = InProcessServerBuilder.forName(serverName)
                .addService(new OrderGrpcService(new MissingOrderRepository()))
                .build()
                .start();

        channel = InProcessChannelBuilder.forName(serverName).build();
        stub = OrderServiceGrpc.newBlockingStub(channel)
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
    void notFoundErrorPreservesStatusDescriptionAndTrailers() {
        StatusRuntimeException error = assertThrows(
                StatusRuntimeException.class,
                () -> stub.getOrder(
                        GetOrderRequest.newBuilder()
                                .setOrderId("missing")
                                .build()));

        Status status = Status.fromThrowable(error);
        assertEquals(Status.Code.NOT_FOUND, status.getCode());
        assertEquals("Order was not found", status.getDescription());

        Metadata trailers = error.getTrailers();
        assertNotNull(trailers);
        assertEquals(
                "ORDER_NOT_FOUND",
                trailers.get(OrderErrorMetadata.ERROR_CODE));
        assertEquals(
                "req-test-42",
                trailers.get(OrderErrorMetadata.REQUEST_ID));
    }
}
~~~

MissingOrderRepository là fixture trả về Optional.empty(). Test dùng service implementation và generated blocking stub thật, vì vậy nó xác minh cả mapping ở provider lẫn cách client nhận lỗi. Trong test suite thực tế, luôn shutdown channel/server trong teardown; deadline hữu hạn ngăn test treo khi server không phản hồi.

In-process test không xác minh TLS, proxy hoặc network failure. Nếu metadata đi qua gateway/service mesh, bổ sung integration test ở môi trường tương ứng để xác nhận trailers được forward như contract.

## 8. Kiểm tra lỗi INTERNAL không làm lộ thông tin

Một test riêng nên xác minh lỗi bất ngờ không làm rò rỉ exception nội bộ:

~~~java
@Test
void unexpectedFailureReturnsSafeInternalError() {
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stubWithBrokenRepository.getOrder(request));

    Status status = Status.fromThrowable(error);
    assertEquals(Status.Code.INTERNAL, status.getCode());
    assertEquals("Internal server error", status.getDescription());

    String description = status.getDescription();
    assertFalse(description.contains("SELECT"));
    assertFalse(description.contains("jdbc:"));
}
~~~

Trong production, log đầy đủ exception ở server với trace/request ID và quyền truy cập phù hợp. Response gửi client chỉ nên chứa thông điệp an toàn cùng error code ổn định. Tránh ghi authorization metadata, token hoặc toàn bộ trailers vào log nếu chúng có thể chứa dữ liệu nhạy cảm.

## 9. Các lỗi thường gặp khi assertion

| Lỗi test | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Chỉ assert có StatusRuntimeException | Không phân biệt NOT_FOUND, INTERNAL hay UNAVAILABLE | Assert Status.Code |
| Parse description để quyết định retry | Câu chữ có thể đổi hoặc được localization | Dùng status và error-code metadata |
| Giả định getTrailers luôn khác null | Không phải mọi lỗi đều có custom trailers | Kiểm tra null theo contract |
| Dùng key viết hoa hoặc key grpc-* | Không phù hợp quy tắc metadata của ứng dụng | Dùng key lowercase, không chiếm prefix protocol |
| Dùng ASCII marshaller cho bytes | Kiểu encode không khớp contract | Dùng hậu tố -bin và binary marshaller |
| Gửi stack trace trong description | Làm lộ implementation và thông tin nội bộ | Dùng thông điệp an toàn, log chi tiết ở server |
| Assert toàn bộ metadata không liên quan | Test dễ vỡ khi thêm key độc lập | Chỉ assert key thuộc contract |
| Không đặt deadline cho test | Test có thể treo vô hạn | Dùng deadline hữu hạn và teardown đúng |

Với metadata có thể xuất hiện nhiều lần, định nghĩa cardinality rõ ràng và dùng getAll(key) để kiểm tra tất cả value. Với key đơn trị, test duplicate behavior thay vì phụ thuộc ngẫu nhiên vào value được đọc đầu tiên.

## 10. Checklist và tự kiểm tra

- [ ] Assert canonical status code cho từng điều kiện nghiệp vụ.
- [ ] Chỉ assert exact description nếu câu chữ là contract ổn định.
- [ ] Không để client parse description để điều khiển retry/business flow.
- [ ] Custom trailer key dùng chữ thường và marshaller đúng kiểu.
- [ ] Binary metadata dùng hậu tố -bin và BINARY_BYTE_MARSHALLER.
- [ ] Assert metadata bắt buộc có mặt và đúng giá trị.
- [ ] Xử lý trường hợp trailers null nếu contract cho phép.
- [ ] Lỗi bất ngờ trả description an toàn, không lộ stack trace.
- [ ] Provider test gọi qua generated stub và in-process server.
- [ ] Test có deadline hữu hạn và giải phóng channel/server.
- [ ] Không log token, credential hoặc metadata nhạy cảm.
- [ ] Có integration test qua proxy nếu môi trường production dùng gateway/service mesh.

**Tự kiểm tra**

**Câu 1.** Vì sao assertThrows(StatusRuntimeException.class) chưa đủ?

*Đáp án:* Nhiều canonical status được ném cùng kiểu exception. Test phải xác minh Status.Code để bảo vệ semantics mà client dựa vào.

**Câu 2.** Khi nào nên assert chính xác description?

*Đáp án:* Khi câu chữ là thông điệp công khai cần giữ ổn định. Nếu description chỉ phục vụ chẩn đoán, nên tránh dùng nó làm machine contract và kiểm tra status/error code thay thế.

**Câu 3.** Custom error-code nên đặt ở đâu?

*Đáp án:* Trong custom trailers metadata với key được định nghĩa ổn định, ví dụ error-code. Không tự tạo grpc-status hoặc grpc-message vì đó là protocol fields do gRPC quản lý.

**Câu 4.** Vì sao getTrailers() có thể null?

*Đáp án:* Server có thể không gửi custom trailers, hoặc lỗi xảy ra trước khi metadata được tạo. Test cần phản ánh việc key bắt buộc hay tùy chọn theo contract.

**Câu 5.** Vì sao không gửi stack trace qua description?

*Đáp án:* Description được truyền tới client và có thể xuất hiện trong log. Stack trace có thể tiết lộ SQL, đường dẫn, hostname hoặc chi tiết nội bộ; giữ nó trong server-side logs có kiểm soát.

Assertion status, description và metadata tạo thành một error contract có thể kiểm thử ở ranh giới RPC. Status code bảo vệ cách client phân loại lỗi, description cung cấp thông tin an toàn cho người đọc, còn trailers mang error code/request ID có cấu trúc. Khi provider test xác minh cả ba qua generated stub, các phiên bản Spring gRPC có thể thay đổi implementation mà vẫn giữ hành vi lỗi rõ ràng và ổn định cho consumer.
