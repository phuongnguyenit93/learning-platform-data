# Mapping lỗi domain sang gRPC status

**Chương:** Error handling  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng Protocol Buffers, mã Java được sinh và RPC unary hoặc streaming. Bài này tập trung vào việc chuyển **lỗi nghiệp vụ của domain/application thành gRPC status** tại ranh giới server, để client nhận được mã lỗi ổn định mà tầng nghiệp vụ không phải phụ thuộc gRPC.

## 1. Vì sao cần một lớp ánh xạ?

Giả sử ứng dụng đặt hàng có các lỗi nghiệp vụ: khách hàng không tồn tại, đơn hàng đã được tạo, trạng thái đơn hàng không cho phép hủy hoặc tồn kho không đủ. Đây là các khái niệm của domain. Khi triển khai API bằng gRPC, server phải chuyển chúng thành các status chuẩn như `NOT_FOUND`, `ALREADY_EXISTS` hoặc `FAILED_PRECONDITION`.

Không nên để domain tự ném `StatusRuntimeException` ở mọi nơi. Làm như vậy khiến domain phụ thuộc vào thư viện transport và khó tái sử dụng khi cùng nghiệp vụ được gọi từ REST, message consumer hoặc batch job.

Ranh giới hợp lý:

```text
gRPC request
    |
    v
Generated service / gRPC adapter
    |
    v
Application service
    |
    v
Domain logic
    |
    +-- CustomerNotFound
    +-- DuplicateOrder
    +-- OrderStateConflict
    +-- InventoryUnavailable
    |
    v
DomainStatusMapper
    |
    +-- NOT_FOUND
    +-- ALREADY_EXISTS
    +-- FAILED_PRECONDITION
    +-- RESOURCE_EXHAUSTED
    |
    v
responseObserver.onError(Status...)
```

Mapper chuyển ý nghĩa nghiệp vụ thành **giao ước lỗi của API**. Client dựa vào status code để quyết định hành vi; server có thể thay đổi cách lưu trữ hoặc cấu trúc domain mà không buộc client parse tên exception Java.

## 2. Ánh xạ theo ngữ nghĩa, không theo tên exception một cách máy móc

Một domain exception nên biểu đạt điều gì đã xảy ra trong nghiệp vụ. gRPC status phải biểu đạt client nên hiểu kết quả RPC ra sao.

| Lỗi domain | gRPC status thường phù hợp | Lý do |
| --- | --- | --- |
| Không tìm thấy khách hàng/đơn hàng | `NOT_FOUND` | Tài nguyên được yêu cầu không tồn tại |
| Dữ liệu đầu vào vi phạm quy tắc định dạng | `INVALID_ARGUMENT` | Client cần sửa request |
| Tạo tài nguyên đã tồn tại | `ALREADY_EXISTS` | Thao tác xung đột với tài nguyên hiện có |
| Hủy đơn đã giao hoặc thao tác sai trạng thái | `FAILED_PRECONDITION` | Trạng thái hiện tại không cho phép thao tác |
| Xung đột optimistic locking khi cập nhật | `ABORTED` | Có thể cần chạy lại toàn bộ transaction/workflow |
| Vượt quota hoặc hạn mức nghiệp vụ | `RESOURCE_EXHAUSTED` | Yêu cầu vượt ngân sách tài nguyên |
| Phụ thuộc tạm thời không sẵn sàng | `UNAVAILABLE` | Có thể phục hồi; retry cần backoff và tính idempotent |
| Caller đã xác thực nhưng không đủ quyền | `PERMISSION_DENIED` | Danh tính có thật nhưng không được phép |
| Lỗi nội bộ không dự kiến | `INTERNAL` | Không tiết lộ chi tiết triển khai |

Một số lựa chọn cần xét theo ngữ cảnh:

- **`ALREADY_EXISTS` hay `ABORTED`:** tạo một mã đơn hàng đã tồn tại thường là `ALREADY_EXISTS`; xung đột phiên bản khi cập nhật có thể là `ABORTED` vì client cần đọc lại và chạy lại transaction.
- **`FAILED_PRECONDITION` hay `INVALID_ARGUMENT`:** trạng thái đơn hàng hiện tại không cho phép hủy thường là `FAILED_PRECONDITION`; một trường request sai định dạng thường là `INVALID_ARGUMENT`.
- **`UNAVAILABLE` hay `INTERNAL`:** dịch vụ phụ thuộc tạm thời mất kết nối có thể là `UNAVAILABLE`; lỗi lập trình hoặc invariant bị phá vỡ thường là `INTERNAL`.
- **`UNAUTHENTICATED` hay `PERMISSION_DENIED`:** thiếu/không hợp lệ credential là `UNAUTHENTICATED`; đã xác thực nhưng không đủ quyền là `PERMISSION_DENIED`. Các lỗi xác thực thường được xử lý ở security/interceptor boundary.

Không ánh xạ mọi exception thành `INTERNAL`, cũng không dùng `INVALID_ARGUMENT` cho mọi lỗi để client “tự sửa”. Status là một phần hợp đồng API, cần phản ánh đúng nguyên nhân có thể hành động.

## 3. Giữ domain độc lập với gRPC

Một cách đơn giản là dùng mã lỗi domain riêng, không import `io.grpc.Status` trong domain:

```java
public enum DomainErrorCode {
    CUSTOMER_NOT_FOUND,
    DUPLICATE_ORDER,
    ORDER_STATE_CONFLICT,
    OPTIMISTIC_LOCK_CONFLICT,
    QUOTA_EXCEEDED,
    DEPENDENCY_UNAVAILABLE,
    ACCESS_DENIED
}

public class DomainException extends RuntimeException {
    private final DomainErrorCode code;

    public DomainException(DomainErrorCode code) {
        super(code.name());
        this.code = code;
    }

    public DomainErrorCode code() {
        return code;
    }
}
```

Domain service ném lỗi theo ngữ nghĩa:

```java
if (customer == null) {
    throw new DomainException(DomainErrorCode.CUSTOMER_NOT_FOUND);
}
if (orderAlreadyExists(command.orderId())) {
    throw new DomainException(DomainErrorCode.DUPLICATE_ORDER);
}
if (!order.canBeCancelled()) {
    throw new DomainException(DomainErrorCode.ORDER_STATE_CONFLICT);
}
```

Ví dụ dùng một `DomainException` có mã enum để làm rõ cơ chế. Dự án lớn có thể dùng các lớp exception chuyên biệt (`CustomerNotFoundException`, `DuplicateOrderException`...) thay cho enum. Dù chọn cách nào, domain vẫn không cần biết status code gRPC.

Không đưa trực tiếp `Status.Code` vào `DomainErrorCode`: nếu làm vậy, tầng domain lại phụ thuộc transport và mapper mất ý nghĩa.

## 4. Xây DomainStatusMapper ở adapter layer

Mapper nhận lỗi domain và trả một `StatusRuntimeException` để adapter gửi qua `responseObserver.onError()`.

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Component;

@Component
public class DomainStatusMapper {

    public StatusRuntimeException map(DomainException error) {
        Status status = switch (error.code()) {
            case CUSTOMER_NOT_FOUND ->
                    Status.NOT_FOUND.withDescription("Customer not found");
            case DUPLICATE_ORDER ->
                    Status.ALREADY_EXISTS.withDescription("Order already exists");
            case ORDER_STATE_CONFLICT ->
                    Status.FAILED_PRECONDITION
                            .withDescription("Order state does not allow this action");
            case OPTIMISTIC_LOCK_CONFLICT ->
                    Status.ABORTED.withDescription("Order changed; reload and retry");
            case QUOTA_EXCEEDED ->
                    Status.RESOURCE_EXHAUSTED.withDescription("Quota exceeded");
            case DEPENDENCY_UNAVAILABLE ->
                    Status.UNAVAILABLE.withDescription("A required service is unavailable");
            case ACCESS_DENIED ->
                    Status.PERMISSION_DENIED.withDescription("Operation is not permitted");
        };
        return status.asRuntimeException();
    }
}
```

Vì switch bao phủ enum, khi thêm một `DomainErrorCode` mới, compiler giúp phát hiện mapper chưa xử lý mã đó. Đây là lợi ích của việc có một danh mục domain error rõ ràng.

Description trong ví dụ là chuỗi công khai đã được kiểm soát. Không lấy `error.getMessage()` tùy tiện rồi trả cho client: message có thể chứa SQL, tên bảng, dữ liệu cá nhân, đường dẫn nội bộ hoặc thông tin không phù hợp để lộ.

Nếu cần mã lỗi chi tiết cho client, có thể thêm trailer `error-code` hoặc dùng error detail protobuf theo hợp đồng API. Không biến description thành một giao thức ngầm mà client phải parse.

## 5. Áp dụng mapper tại Spring gRPC service

Service adapter gọi application service, chuyển domain exception thành gRPC status và kết thúc RPC đúng một lần:

```java
@GrpcService
public class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderApplicationService applicationService;
    private final DomainStatusMapper statusMapper;

    public OrderGrpcService(
            OrderApplicationService applicationService,
            DomainStatusMapper statusMapper) {
        this.applicationService = applicationService;
        this.statusMapper = statusMapper;
    }

    @Override
    public void cancelOrder(
            CancelOrderRequest request,
            StreamObserver<Order> responseObserver) {
        try {
            Order order = applicationService.cancel(request.getOrderId());
            responseObserver.onNext(toProto(order));
            responseObserver.onCompleted();
        } catch (DomainException domainError) {
            responseObserver.onError(statusMapper.map(domainError));
        } catch (RuntimeException unexpected) {
            log.error("Unexpected error while cancelling order", unexpected);
            responseObserver.onError(
                    Status.INTERNAL
                            .withDescription("Internal server error")
                            .asRuntimeException());
        }
    }
}
```

Mapper được gọi tại ranh giới gRPC, nơi ứng dụng biết domain error cần được công bố qua API như thế nào. Domain/application service vẫn có thể được gọi từ REST hoặc job mà không phải xử lý gRPC exception.

### Không ghi response trước khi biết kết quả

Với unary RPC, chỉ gọi `onNext(response)` sau khi application service hoàn tất thành công. Nếu đã gọi `onNext` rồi mới phát hiện lỗi và gọi `onError`, client có thể quan sát một response message trước terminal status; điều đó thường làm hợp đồng khó hiểu.

Với server streaming hoặc client streaming, quy tắc terminal vẫn tương tự: khi phát hiện domain error, chuyển thành status và gọi `onError` một lần; không tiếp tục gửi message hoặc gọi `onCompleted` sau đó.

## 6. Ánh xạ lỗi trong streaming callback

Trong streaming RPC, domain exception có thể phát sinh khi xử lý một message trong `onNext()` hoặc khi tổng hợp/commit trong `onCompleted()`. Cần giữ trạng thái kết thúc để không gửi hai terminal callback:

```java
return new StreamObserver<OrderItem>() {
    private boolean terminated;

    @Override
    public void onNext(OrderItem item) {
        if (terminated) return;
        try {
            applicationService.accept(item);
        } catch (DomainException domainError) {
            terminated = true;
            responseObserver.onError(statusMapper.map(domainError));
        }
    }

    @Override
    public void onError(Throwable inboundError) {
        terminated = true;
        // Client hủy/lỗi inbound: dọn tài nguyên; không gửi receipt.
    }

    @Override
    public void onCompleted() {
        if (terminated) return;
        try {
            OrderSummary summary = applicationService.finish();
            terminated = true;
            responseObserver.onNext(toProto(summary));
            responseObserver.onCompleted();
        } catch (DomainException domainError) {
            terminated = true;
            responseObserver.onError(statusMapper.map(domainError));
        }
    }
};
```

Đoạn minh họa giả định callback được điều phối tuần tự trong một RPC và phần xử lý không chạy song song trên nhiều thread. Nếu có tác vụ bất đồng bộ, cancellation handler hoặc nhiều worker, cần state terminal atomic/đồng bộ và cleanup idempotent. Không gọi response observer đồng thời từ nhiều thread.

Lỗi inbound `onError(Throwable)` không phải domain error do server chủ động tạo; nó biểu thị phía client/transport đã kết thúc luồng request bằng lỗi. Không ánh xạ mọi lỗi đó sang `INTERNAL`.

## 7. Những lỗi không nên đưa qua DomainStatusMapper

Không phải mọi exception trong server đều là lỗi domain:

| Nguyên nhân | Xử lý phù hợp |
| --- | --- |
| Request protobuf thiếu trường bắt buộc hoặc sai định dạng | Validate ở adapter; trả `INVALID_ARGUMENT` |
| Domain không tìm thấy đơn hàng | Domain exception → `NOT_FOUND` |
| Trạng thái đơn không cho phép hủy | Domain exception → `FAILED_PRECONDITION` |
| Credential thiếu/sai | Security layer/interceptor → `UNAUTHENTICATED` |
| Caller không có quyền | Authorization boundary → `PERMISSION_DENIED` |
| Deadline/cancellation của RPC | Giữ semantics gRPC `DEADLINE_EXCEEDED`/`CANCELLED`; cleanup |
| Lỗi database bất ngờ | Log nội bộ, status phù hợp như `INTERNAL`; chỉ dùng `UNAVAILABLE` khi thực sự là phụ thuộc tạm thời không sẵn sàng |
| Bug hoặc invariant bị phá vỡ | `INTERNAL`, không giả dạng lỗi đầu vào |

Nếu một tầng dưới đã phát sinh gRPC status exception, adapter nên giữ nguyên status đó thay vì chuyển nó thành domain error mới. Tương tự, không biến `CancellationException` hoặc lỗi deadline thành `INTERNAL` chỉ vì chúng xuất hiện dưới dạng exception Java.

## 8. Kiểm thử ánh xạ độc lập và qua RPC

Mapper là logic thuần, nên có thể kiểm thử bằng unit test mà không cần khởi động server:

```java
import io.grpc.Status;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DomainStatusMapperTest {

    private final DomainStatusMapper mapper = new DomainStatusMapper();

    @Test
    void customerNotFoundMapsToNotFound() {
        var grpcError = mapper.map(
                new DomainException(DomainErrorCode.CUSTOMER_NOT_FOUND));

        assertEquals(Status.Code.NOT_FOUND,
                grpcError.getStatus().getCode());
    }

    @Test
    void orderStateConflictMapsToFailedPrecondition() {
        var grpcError = mapper.map(
                new DomainException(DomainErrorCode.ORDER_STATE_CONFLICT));

        assertEquals(Status.Code.FAILED_PRECONDITION,
                grpcError.getStatus().getCode());
    }

    @Test
    void duplicateOrderMapsToAlreadyExists() {
        var grpcError = mapper.map(
                new DomainException(DomainErrorCode.DUPLICATE_ORDER));

        assertEquals(Status.Code.ALREADY_EXISTS,
                grpcError.getStatus().getCode());
    }
}
```

Unit test xác nhận bảng ánh xạ. Integration test qua gRPC in-process nên xác nhận thêm client thực sự nhận đúng status:

- Gọi hủy đơn không tồn tại, client nhận `NOT_FOUND`.
- Gọi hủy đơn đã giao, client nhận `FAILED_PRECONDITION`.
- Tạo đơn với ID đã tồn tại, client nhận `ALREADY_EXISTS`.
- Lỗi bất ngờ không làm lộ exception message hoặc stack trace.
- Với streaming, lỗi phát sinh giữa luồng kết thúc response đúng một lần và không có receipt thành công.

Kiểm thử không nên phụ thuộc vào câu description nguyên văn nếu đó không phải một phần hợp đồng ổn định. Kiểm tra status code trước; chỉ kiểm tra description khi API có chủ đích cam kết nội dung đó.

## 9. Quy tắc vận hành và retry

Ánh xạ status cũng ảnh hưởng trực tiếp đến retry:

- `INVALID_ARGUMENT`, `NOT_FOUND`, `PERMISSION_DENIED` thường không nên retry cùng request không đổi.
- `ALREADY_EXISTS` cần tra cứu tài nguyên hoặc coi thao tác tạo đã đạt trạng thái mong muốn theo idempotency contract.
- `FAILED_PRECONDITION` yêu cầu thay đổi trạng thái hoặc điều kiện trước khi thử lại.
- `ABORTED` có thể cần đọc lại dữ liệu và chạy lại toàn transaction.
- `RESOURCE_EXHAUSTED` cần giảm tải hoặc chờ theo quota, không retry dồn dập.
- `UNAVAILABLE` có thể retry với exponential backoff và jitter nếu thao tác an toàn.
- `DEADLINE_EXCEEDED` không chứng minh server chưa thực hiện thao tác; với thao tác ghi, cần idempotency key hoặc API tra cứu trạng thái.

Ghi log domain error cùng correlation ID, operation và status code; không log token hoặc payload nhạy cảm. Theo dõi tần suất từng status để phát hiện lỗi validation, xung đột nghiệp vụ, quá quota và sự cố phụ thuộc. Nếu status mapping thay đổi, xem đó là thay đổi hợp đồng API và đánh giá ảnh hưởng đến client.

## 10. Tự luyện tập

1. Một đơn hàng đã giao nhưng client yêu cầu hủy. Vì sao `FAILED_PRECONDITION` phù hợp hơn `INVALID_ARGUMENT`?
2. Một lần tạo đơn bị trùng ID và một lần cập nhật gặp optimistic locking conflict. Khi nào chọn `ALREADY_EXISTS`, khi nào chọn `ABORTED`?
3. Thiết kế thêm `DomainErrorCode.PAYMENT_DECLINED`. Hãy chọn gRPC status và mô tả an toàn để client có thể hành động.
4. Vì sao `DomainException` không nên chứa hoặc phụ thuộc trực tiếp vào `io.grpc.Status.Code`?
5. Một client nhận `UNAVAILABLE` sau thao tác ghi đơn hàng. Cần bảo đảm gì trước khi retry để không tạo đơn trùng?

**Ghi nhớ:** Domain phát biểu **điều gì sai trong nghiệp vụ**; gRPC adapter chuyển lỗi đó thành **status code mà client có thể hiểu ổn định**. Giữ domain độc lập với transport, ánh xạ tập trung theo ngữ nghĩa, không lộ chi tiết nội bộ và kiểm thử status ở cả mapper lẫn ranh giới RPC.
