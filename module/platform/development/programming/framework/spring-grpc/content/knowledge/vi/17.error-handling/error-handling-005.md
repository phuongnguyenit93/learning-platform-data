# Không trả INTERNAL cho mọi exception

**Chương:** Error handling  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng Protocol Buffers, mã Java được sinh và RPC unary hoặc streaming. Bài này tập trung vào việc **phân loại exception tại ranh giới server và ánh xạ theo ngữ nghĩa sang gRPC status**, để client có thể sửa request, xác thực lại, chờ hoặc retry đúng cách.

## 1. Vì sao không nên biến mọi exception thành INTERNAL?

`INTERNAL` có nghĩa server gặp lỗi nội bộ không mong đợi hoặc không thể công bố chi tiết hơn. Nếu mọi exception đều bị chuyển thành `INTERNAL`, client không thể phân biệt:

- Request sai dữ liệu và cần sửa.
- Tài nguyên không tồn tại.
- Caller chưa xác thực hoặc không có quyền.
- Trạng thái nghiệp vụ hiện tại không cho phép thao tác.
- Xung đột đồng thời có thể giải quyết bằng cách đọc lại và thử transaction mới.
- Dịch vụ phụ thuộc tạm thời không sẵn sàng.
- Lỗi lập trình hoặc sự cố nội bộ thực sự.

Status là một phần **hợp đồng API**. Ánh xạ đúng giúp client xử lý có chủ đích; ánh xạ sai có thể khiến client retry lỗi vĩnh viễn, bỏ qua một xung đột có thể khắc phục hoặc hiển thị lỗi hệ thống cho một request không hợp lệ.

Luồng xử lý nên có ranh giới rõ:

```text
Request / application operation
          |
          v
Domain + infrastructure exceptions
          |
          v
gRPC exception mapper
          |
          +-- Lỗi client / domain / security / dependency đã biết
          |        -> status cụ thể
          |
          +-- Status exception đã có
          |        -> giữ nguyên status và trailers
          |
          +-- Lỗi không dự kiến
                   -> log nội bộ + INTERNAL an toàn
          |
          v
responseObserver.onError(...)
```

Mục tiêu không phải loại bỏ `INTERNAL`. Mục tiêu là chỉ dùng nó cho lỗi thực sự không được phân loại, thay vì dùng làm câu trả lời mặc định cho mọi tình huống.

## 2. Bảng ánh xạ theo ý nghĩa lỗi

| Nguyên nhân | gRPC status thường phù hợp | Hành động client |
| --- | --- | --- |
| Request thiếu trường hoặc sai định dạng | `INVALID_ARGUMENT` | Sửa request; không retry nguyên trạng |
| Tài nguyên không tồn tại | `NOT_FOUND` | Thông báo hoặc chọn tài nguyên khác |
| Tạo tài nguyên đã tồn tại | `ALREADY_EXISTS` | Tra cứu tài nguyên hoặc xử lý trùng |
| Trạng thái hiện tại không cho phép thao tác | `FAILED_PRECONDITION` | Thay đổi điều kiện nghiệp vụ trước |
| Optimistic locking/transaction conflict | `ABORTED` | Đọc lại và thử lại toàn transaction |
| Chưa có credential hợp lệ | `UNAUTHENTICATED` | Đăng nhập hoặc làm mới credential |
| Đã xác thực nhưng không đủ quyền | `PERMISSION_DENIED` | Dừng thao tác hoặc yêu cầu quyền |
| Vượt quota/tài nguyên được cấp | `RESOURCE_EXHAUSTED` | Giảm tải hoặc chờ theo quota |
| Phụ thuộc tạm thời không sẵn sàng | `UNAVAILABLE` | Retry có backoff nếu thao tác an toàn |
| RPC hết deadline | `DEADLINE_EXCEEDED` | Xác minh kết quả nếu thao tác có tác dụng phụ |
| Caller chủ động hủy | `CANCELLED` | Dừng producer và cleanup |
| Lỗi không dự kiến hoặc invariant bị phá vỡ | `INTERNAL` | Điều tra phía server |

Không ánh xạ chỉ dựa trên tên lớp exception. Ví dụ:

- `IllegalArgumentException` có thể là lỗi lập trình, không nhất thiết là request sai. Chỉ lỗi validation được xác định tại biên request mới nên trở thành `INVALID_ARGUMENT`.
- `DataIntegrityViolationException` có thể là vi phạm unique key đã biết, nhưng cũng có thể là lỗi constraint khác. Chỉ chuyển thành `ALREADY_EXISTS` khi biết chính xác đó là xung đột tài nguyên theo hợp đồng.
- `DataAccessException` không đồng nghĩa dịch vụ database luôn tạm thời không sẵn sàng. Chỉ dùng `UNAVAILABLE` khi nguyên nhân thực sự là phụ thuộc tạm thời và có thể phục hồi.
- `TimeoutException` của một tác vụ downstream không tự động có nghĩa toàn RPC đã hết deadline. Phân biệt timeout cục bộ với deadline của gRPC call.

## 3. Tạo loại exception có ý nghĩa ở tầng ứng dụng

Domain/application nên phát biểu điều gì đã xảy ra mà không phụ thuộc `io.grpc.Status`. Ví dụ:

```java
public class RequestValidationException extends RuntimeException {
    public RequestValidationException(String message) {
        super(message);
    }
}

public class CustomerNotFoundException extends RuntimeException {
    public CustomerNotFoundException(String customerId) {
        super("Customer not found: " + customerId);
    }
}

public class DuplicateOrderException extends RuntimeException {
    public DuplicateOrderException(String orderId) {
        super("Order already exists: " + orderId);
    }
}

public class OrderStateConflictException extends RuntimeException {
    public OrderStateConflictException(String message) {
        super(message);
    }
}

public class DependencyUnavailableException extends RuntimeException {
    public DependencyUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class QuotaExceededException extends RuntimeException {
    public QuotaExceededException(String message) {
        super(message);
    }
}
```

Trong dự án thực, có thể dùng các exception chuyên biệt đã tồn tại thay vì tạo lại. Điều quan trọng là tầng application phát ra lỗi **có ngữ nghĩa**, không ném `StatusRuntimeException` ở mọi method nghiệp vụ.

Ví dụ application service:

```java
public Order createOrder(CreateOrderCommand command) {
    if (command.customerId() == null || command.customerId().isBlank()) {
        throw new RequestValidationException("customerId is required");
    }
    if (!customerRepository.existsById(command.customerId())) {
        throw new CustomerNotFoundException(command.customerId());
    }
    if (orderRepository.existsByExternalId(command.externalId())) {
        throw new DuplicateOrderException(command.externalId());
    }
    return orderRepository.save(Order.create(command));
}
```

Application service không cần biết lời gọi đến từ gRPC hay REST. Adapter sẽ chuyển exception thành giao thức phù hợp.

## 4. Xây dựng mapper có phân loại rõ ràng

Mapper nên xử lý theo thứ tự:

1. Nếu exception đã chứa gRPC status, giữ nguyên code, description và trailers.
2. Nếu là lỗi đã biết của request/domain/security/dependency, ánh xạ sang status phù hợp.
3. Nếu không nhận diện được, ghi log nội bộ và trả `INTERNAL` với description chung.

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;
import io.grpc.Status.Code;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Component;

@Component
public class GrpcExceptionMapper {

    private static final Logger log =
            LoggerFactory.getLogger(GrpcExceptionMapper.class);

    public StatusRuntimeException toStatusException(Throwable error) {
        Throwable existingGrpcError = findGrpcStatus(error);
        if (existingGrpcError != null) {
            Status existing = Status.fromThrowable(existingGrpcError);
            Metadata trailers =
                    Status.trailersFromThrowable(existingGrpcError);
            // Không đổi một status gRPC đã được tầng dưới chủ động tạo.
            return trailers == null
                    ? existing.asRuntimeException()
                    : existing.asRuntimeException(trailers);
        }

        if (hasCause(error, RequestValidationException.class)) {
            return Status.INVALID_ARGUMENT
                    .withDescription("Request không hợp lệ")
                    .asRuntimeException();
        }
        if (hasCause(error, CustomerNotFoundException.class)) {
            return Status.NOT_FOUND
                    .withDescription("Không tìm thấy khách hàng")
                    .asRuntimeException();
        }
        if (hasCause(error, DuplicateOrderException.class)) {
            return Status.ALREADY_EXISTS
                    .withDescription("Đơn hàng đã tồn tại")
                    .asRuntimeException();
        }
        if (hasCause(error, OrderStateConflictException.class)) {
            return Status.FAILED_PRECONDITION
                    .withDescription("Trạng thái đơn hàng không cho phép thao tác")
                    .asRuntimeException();
        }
        if (hasCause(error, OptimisticLockingFailureException.class)) {
            return Status.ABORTED
                    .withDescription("Dữ liệu đã thay đổi; hãy tải lại và thử lại")
                    .asRuntimeException();
        }
        if (hasCause(error, AuthenticationException.class)) {
            return Status.UNAUTHENTICATED
                    .withDescription("Yêu cầu xác thực hợp lệ")
                    .asRuntimeException();
        }
        if (hasCause(error, AccessDeniedException.class)) {
            return Status.PERMISSION_DENIED
                    .withDescription("Không có quyền thực hiện thao tác")
                    .asRuntimeException();
        }
        if (hasCause(error, QuotaExceededException.class)) {
            return Status.RESOURCE_EXHAUSTED
                    .withDescription("Đã vượt hạn mức")
                    .asRuntimeException();
        }
        if (hasCause(error, DependencyUnavailableException.class)) {
            return Status.UNAVAILABLE
                    .withDescription("Dịch vụ phụ thuộc tạm thời không sẵn sàng")
                    .asRuntimeException();
        }

        // Chỉ lỗi chưa phân loại mới đi vào nhánh INTERNAL.
        log.error("Unmapped exception at gRPC boundary", error);
        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }

    private Throwable findGrpcStatus(Throwable error) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (current instanceof StatusRuntimeException
                    || current instanceof StatusException) {
                return current;
            }
        }
        return null;
    }

    private boolean hasCause(
            Throwable error, Class<? extends Throwable> expectedType) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
```

Ví dụ giữ lại status exception đã có trước khi kiểm tra exception domain. Điều này tránh vô tình đổi một lỗi `UNAVAILABLE` hoặc `PERMISSION_DENIED` đã được tạo ở tầng dưới thành `INTERNAL`.

Các description trả client đều là chuỗi chung đã kiểm soát. Mapper không đưa `error.getMessage()` vào response, vì message có thể chứa ID nhạy cảm, SQL, tên bảng, đường dẫn nội bộ hoặc thông tin triển khai.

### Lưu ý khi mở rộng mapper

- Thứ tự kiểm tra quan trọng nếu một exception có thể kế thừa từ nhiều loại exception.
- Chỉ thêm mapping khi biết rõ semantics và hành động client mong đợi.
- Không map mọi `IllegalArgumentException` thành `INVALID_ARGUMENT`; lỗi này có thể do bug ở server.
- Không map mọi `DataAccessException` thành `UNAVAILABLE`; phân biệt lỗi kết nối tạm thời, conflict, constraint và lỗi dữ liệu.
- Không bắt `Throwable` để che các lỗi JVM nghiêm trọng. Mapper nhận `Throwable` để xử lý wrapper ở ranh giới, nhưng adapter nên bắt các loại exception mà ứng dụng có thể xử lý.

## 5. Gọi mapper ở ranh giới Spring gRPC

Với unary RPC, adapter chuyển exception từ application service thành terminal gRPC status:

```java
@GrpcService
public class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderApplicationService applicationService;
    private final GrpcExceptionMapper exceptionMapper;

    public OrderGrpcService(
            OrderApplicationService applicationService,
            GrpcExceptionMapper exceptionMapper) {
        this.applicationService = applicationService;
        this.exceptionMapper = exceptionMapper;
    }

    @Override
    public void createOrder(
            CreateOrderRequest request,
            StreamObserver<OrderResponse> responseObserver) {
        try {
            Order order = applicationService.createOrder(
                    toCommand(request));
            responseObserver.onNext(toProto(order));
            responseObserver.onCompleted();
        } catch (Exception error) {
            responseObserver.onError(
                    exceptionMapper.toStatusException(error));
        }
    }
}
```

Adapter không cần tự đoán từng lỗi ở mọi method. Mapper tập trung giúp status nhất quán giữa các RPC. Tuy nhiên, chỉ bắt `Exception` ở ranh giới nơi ứng dụng có chiến lược ánh xạ rõ ràng; không bắt `Throwable` rồi tiếp tục xử lý cả lỗi JVM.

### Streaming callback

Với client streaming, lỗi có thể xảy ra trong `onNext()` hoặc khi hoàn tất ở `onCompleted()`. Khi phát hiện lỗi, server gọi `onError` đúng một lần và không gửi receipt thành công:

```java
return new StreamObserver<OrderItem>() {
    private boolean terminated;

    @Override
    public void onNext(OrderItem item) {
        if (terminated) return;
        try {
            applicationService.accept(item);
        } catch (Exception error) {
            terminated = true;
            responseObserver.onError(
                    exceptionMapper.toStatusException(error));
        }
    }

    @Override
    public void onError(Throwable inboundError) {
        // Client/transport kết thúc inbound stream: cleanup, không trả receipt.
        terminated = true;
    }

    @Override
    public void onCompleted() {
        if (terminated) return;
        try {
            OrderSummary summary = applicationService.finish();
            terminated = true;
            responseObserver.onNext(toProto(summary));
            responseObserver.onCompleted();
        } catch (Exception error) {
            terminated = true;
            responseObserver.onError(
                    exceptionMapper.toStatusException(error));
        }
    }
};
```

Đoạn minh họa giả định callback được điều phối tuần tự. Nếu có worker bất đồng bộ, cancellation handler hoặc nhiều thread, cần terminal state atomic/đồng bộ và cleanup idempotent. Lỗi inbound `onError(Throwable)` là lỗi/hủy từ phía client hoặc transport; không chuyển nó thành `INTERNAL` rồi cố gửi status ngược trên call đã kết thúc.

## 6. Phân biệt lỗi domain, security, dependency và lỗi lập trình

| Nguồn lỗi | Ví dụ | Cách xử lý tại gRPC boundary |
| --- | --- | --- |
| Validation request | Thiếu customer ID, định dạng sai | `INVALID_ARGUMENT` |
| Domain | Customer không tồn tại, đơn đã tồn tại | `NOT_FOUND`, `ALREADY_EXISTS` |
| Trạng thái nghiệp vụ | Không thể hủy đơn đã giao | `FAILED_PRECONDITION` |
| Concurrent update | Optimistic lock conflict | `ABORTED` |
| Authentication | Token thiếu/hết hạn | `UNAUTHENTICATED` |
| Authorization | Caller không có quyền | `PERMISSION_DENIED` |
| Quota | Tenant vượt hạn mức | `RESOURCE_EXHAUSTED` |
| Dependency tạm thời | Dịch vụ thanh toán không sẵn sàng | `UNAVAILABLE` nếu có thể phục hồi |
| Bug/invariant bị phá | Null bất ngờ, lỗi lập trình | `INTERNAL` |

Authentication/authorization thường được xử lý sớm hơn trong security interceptor hoặc filter. Không cần đợi domain service phát exception mới quyết định `UNAUTHENTICATED` hay `PERMISSION_DENIED`.

Một lỗi database cũng cần được phân loại theo nguyên nhân. Ví dụ unique constraint đã biết có thể trở thành `ALREADY_EXISTS`; optimistic locking trở thành `ABORTED`; database connection tạm thời không truy cập được có thể trở thành `UNAVAILABLE`. Một `DataAccessException` không rõ nguyên nhân nên được điều tra và fallback an toàn, không tự động coi là lỗi tạm thời.

## 7. Retry phải theo status và tính idempotent

Status cụ thể giúp client chọn hành động:

- `INVALID_ARGUMENT`, `NOT_FOUND`, `PERMISSION_DENIED`: thường không retry cùng request không đổi.
- `ALREADY_EXISTS`: tra cứu tài nguyên; nếu thao tác tạo có idempotency key, kiểm tra xem kết quả mong muốn đã tồn tại chưa.
- `FAILED_PRECONDITION`: thay đổi trạng thái hoặc điều kiện trước khi thử lại.
- `ABORTED`: đọc lại dữ liệu và chạy lại transaction/workflow.
- `RESOURCE_EXHAUSTED`: giảm tốc, chờ quota hoặc chia nhỏ batch.
- `UNAVAILABLE`: có thể retry với exponential backoff và jitter nếu thao tác an toàn.
- `DEADLINE_EXCEEDED`: không chứng minh server chưa thực hiện thao tác; tra cứu trạng thái hoặc dùng idempotency key trước khi gửi lại.
- `INTERNAL`: điều tra; không retry vô hạn như một lỗi mạng tạm thời.

Không để mapper quyết định retry. Mapper chỉ mô tả lỗi bằng status; retry policy thuộc client hoặc tầng workflow và phải xét deadline, retry budget, tính idempotent cùng tác dụng phụ đã xảy ra.

## 8. Kiểm thử mapper và hành vi RPC

Mapper có thể được kiểm thử đơn vị bằng cách xác nhận status code:

```java
import io.grpc.Status;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GrpcExceptionMapperTest {

    private final GrpcExceptionMapper mapper = new GrpcExceptionMapper();

    @Test
    void validationErrorIsNotInternal() {
        var status = mapper.toStatusException(
                new RequestValidationException("missing field"));

        assertEquals(Status.Code.INVALID_ARGUMENT,
                status.getStatus().getCode());
    }

    @Test
    void dependencyFailureIsUnavailable() {
        var status = mapper.toStatusException(
                new DependencyUnavailableException("payment", null));

        assertEquals(Status.Code.UNAVAILABLE,
                status.getStatus().getCode());
    }

    @Test
    void unexpectedFailureFallsBackToInternal() {
        var status = mapper.toStatusException(
                new IllegalStateException("unexpected bug"));

        assertEquals(Status.Code.INTERNAL,
                status.getStatus().getCode());
        assertEquals("Internal server error",
                status.getStatus().getDescription());
    }
}
```

Nên bổ sung test cho:

1. Domain not found → `NOT_FOUND`.
2. Duplicate resource → `ALREADY_EXISTS`.
3. Optimistic locking conflict → `ABORTED`.
4. Authentication và authorization → hai status khác nhau.
5. Một `StatusRuntimeException` bọc trong cause chain được giữ nguyên code và trailers.
6. Lỗi bất ngờ trả description chung, không lộ message nội bộ.
7. Qua gRPC in-process, client nhận đúng status mà mapper tạo.
8. Với streaming, lỗi giữa luồng kết thúc một lần, không có response thành công sau lỗi.

Unit test mapper không thay thế integration test. Cần kiểm tra cả ranh giới transport để xác nhận status và trailers thực sự đến client.

## 9. Tự luyện tập

1. Một request có customer ID rỗng. Vì sao nên trả `INVALID_ARGUMENT` thay vì để `NullPointerException` rơi xuống `INTERNAL`?
2. Database báo optimistic locking conflict khi hai client cập nhật cùng đơn. Vì sao `ABORTED` thường phù hợp hơn `UNAVAILABLE`?
3. Một lỗi unique constraint xảy ra. Cần biết thêm điều gì trước khi ánh xạ thành `ALREADY_EXISTS`?
4. Một service thanh toán timeout nhưng deadline gRPC bên ngoài vẫn còn. Vì sao không nhất thiết trả `DEADLINE_EXCEEDED`?
5. Thiết kế test chứng minh `StatusRuntimeException` đã có từ tầng dưới không bị mapper đổi thành `INTERNAL`.

**Ghi nhớ:** Không trả `INTERNAL` cho mọi exception. Hãy phân loại lỗi đã biết theo ngữ nghĩa request, domain, security, concurrency và dependency; giữ nguyên gRPC status đã có; chỉ fallback `INTERNAL` cho lỗi không dự kiến, đồng thời log chi tiết ở server và trả thông điệp an toàn cho client.
