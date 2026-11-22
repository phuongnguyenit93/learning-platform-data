# Lỗi dependency và UNAVAILABLE

**Chương:** Error handling  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng Protocol Buffers, mã Java được sinh và RPC unary hoặc streaming. Bài này tập trung vào lỗi phát sinh khi dịch vụ cần gọi một dependency như gRPC service khác, HTTP API, database hoặc message broker; cách nhận diện lỗi tạm thời và ánh xạ đúng sang gRPC status `UNAVAILABLE`.

## 1. Khi nào một lỗi dependency là UNAVAILABLE?

Một RPC có thể hợp lệ ở tầng API và domain, nhưng không thể hoàn thành vì hệ thống phụ thuộc đang tạm thời không phục vụ được. Ví dụ:

- Dịch vụ thanh toán đang restart hoặc không nhận kết nối.
- HTTP API trả 503 vì đang bảo trì hoặc quá tải.
- DNS, connection pool hoặc network tạm thời không truy cập được dependency.
- gRPC downstream trả `UNAVAILABLE`.
- Circuit breaker đang mở vì dependency liên tục thất bại.

Trong những tình huống này, `UNAVAILABLE` thường diễn đạt đúng rằng **dịch vụ hiện không thể thực hiện request do một phụ thuộc không sẵn sàng**. Client có thể thử lại sau một khoảng chờ nếu thao tác an toàn và còn ngân sách thời gian.

Không phải mọi exception xảy ra khi gọi dependency đều là `UNAVAILABLE`. Một lỗi nghiệp vụ do dependency trả về, ví dụ tài khoản không tồn tại, vẫn cần được ánh xạ theo ý nghĩa nghiệp vụ. Lỗi validation, quyền, quota, deadline và bug nội bộ cũng có status riêng.

## 2. Phân biệt UNAVAILABLE với các status gần nghĩa

| Tình huống | Status thường phù hợp | Vì sao |
| --- | --- | --- |
| Dependency tạm thời không nhận kết nối, connection reset, HTTP 503 | `UNAVAILABLE` | Phụ thuộc không sẵn sàng ở thời điểm gọi |
| Downstream gRPC trả `UNAVAILABLE` | Thường ánh xạ thành `UNAVAILABLE` ở API hiện tại | Lỗi sẵn sàng của dependency được truyền thành lỗi sẵn sàng của dịch vụ |
| Toàn bộ deadline của RPC hiện tại đã hết | `DEADLINE_EXCEEDED` | Ngân sách thời gian của call đã cạn |
| Dependency-specific timeout trong khi deadline caller còn | Theo hợp đồng; thường `UNAVAILABLE` nếu dependency tạm thời không đáp ứng | Không nhầm timeout nội bộ với deadline đầu vào |
| Vượt quota của dependency hoặc tenant | `RESOURCE_EXHAUSTED` | Giới hạn tài nguyên/quota đã bị chạm |
| Request sai hoặc vi phạm quy tắc đầu vào | `INVALID_ARGUMENT` | Client cần sửa request |
| Tài nguyên domain không tồn tại | `NOT_FOUND` | Không phải sự cố sẵn sàng |
| Dependency từ chối do trạng thái nghiệp vụ | `FAILED_PRECONDITION` hoặc status domain tương ứng | Dependency đang hoạt động nhưng không chấp nhận thao tác |
| Xung đột transaction/optimistic lock | `ABORTED` | Cần đọc lại và thử lại workflow/transaction |
| Bug hoặc invariant nội bộ bị phá | `INTERNAL` | Lỗi triển khai không được giả dạng sự cố mạng |

**Không dùng `UNAVAILABLE` làm status mặc định cho mọi exception từ dependency.** Hãy phân loại theo nguyên nhân và ý nghĩa mà client cần biết.

## 3. Nhận diện lỗi từ các loại dependency

### Downstream gRPC

Client gRPC Java thường nhận lỗi trong `StatusRuntimeException` hoặc `StatusException`. Dùng `Status.fromThrowable(error)` để lấy status code, không parse description:

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

try {
    return paymentStub.authorize(request);
} catch (StatusRuntimeException error) {
    Status downstream = Status.fromThrowable(error);
    switch (downstream.getCode()) {
        case UNAVAILABLE -> throw new DependencyUnavailableException(
                "Payment service unavailable", error);
        case RESOURCE_EXHAUSTED -> throw new DependencyQuotaException(
                "Payment service quota exceeded", error);
        case NOT_FOUND -> throw new PaymentMethodNotFoundException();
        default -> throw error;
    }
}
```

Đoạn ví dụ cho thấy cần giữ ý nghĩa của status downstream. Không đổi `NOT_FOUND` thành `UNAVAILABLE` chỉ vì nó đến từ một service khác. Với các status khác, quyết định giữ nguyên hay ánh xạ sang status domain của API hiện tại theo hợp đồng công khai; tránh chuyển tiếp description hoặc trailers nội bộ một cách mù quáng.

### HTTP dependency

Một HTTP client có thể phân biệt:

- HTTP 503: dịch vụ tạm thời không sẵn sàng, thường ánh xạ `UNAVAILABLE`.
- HTTP 429: rate limit/quota, thường ánh xạ `RESOURCE_EXHAUSTED`; tôn trọng `Retry-After` nếu có và được tin cậy.
- HTTP 400/422: request mà dịch vụ hiện tại gửi sang dependency sai; thường là lỗi tích hợp hoặc mapping nội bộ, không tự động quy cho client gRPC.
- HTTP 401/403: credential hoặc quyền giữa hai service; cần phân biệt lỗi cấu hình/identity của dịch vụ gọi với quyền của caller bên ngoài.
- HTTP 404: tài nguyên dependency không tồn tại; ánh xạ theo ý nghĩa API hiện tại, có thể là `NOT_FOUND` hoặc lỗi dependency nếu đây là endpoint bắt buộc bị cấu hình sai.

Không bắt chung mọi `RestClientException` hoặc `WebClientException` rồi trả `UNAVAILABLE`: nhóm exception rộng có thể chứa lỗi request, decode, status nghiệp vụ và bug serialization.

### Database và broker

- Connection refused, connection reset hoặc pool tạm hết kết nối có thể là lỗi phụ thuộc tạm thời.
- Unique constraint, foreign key hoặc dữ liệu vi phạm schema không phải mặc định `UNAVAILABLE`; cần phân loại thành lỗi domain, conflict hoặc lỗi nội bộ.
- Broker từ chối do quota có thể phù hợp `RESOURCE_EXHAUSTED`; broker không sẵn sàng có thể phù hợp `UNAVAILABLE`.
- Query timeout phải được phân biệt với deadline của RPC đầu vào và timeout do chính sách truy vấn.

Hãy chuyển lỗi thư viện thành exception ứng dụng có ngữ nghĩa tại adapter của dependency. Điều đó giúp phần gRPC không phụ thuộc vào class exception riêng của từng HTTP/database client.

## 4. Chuẩn hóa lỗi dependency trước khi ánh xạ

Một số exception ứng dụng có thể biểu đạt các nguyên nhân đã được phân loại:

```java
public class DependencyUnavailableException extends RuntimeException {
    public DependencyUnavailableException(String dependency, Throwable cause) {
        super(dependency, cause);
    }
}

public class DependencyQuotaException extends RuntimeException {
    public DependencyQuotaException(String dependency, Throwable cause) {
        super(dependency, cause);
    }
}

public class DependencyTimeoutException extends RuntimeException {
    public DependencyTimeoutException(String dependency, Throwable cause) {
        super(dependency, cause);
    }
}
```

Adapter của HTTP, gRPC hoặc database chuyển exception đã nhận diện sang các kiểu này. Không tạo `DependencyUnavailableException` cho một lỗi chưa phân loại chỉ để tránh xử lý nó.

Mapper ở ranh giới gRPC có thể ánh xạ các loại lỗi đã biết:

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.springframework.stereotype.Component;

@Component
public class DependencyStatusMapper {

    public StatusRuntimeException map(Throwable error) {
        if (error instanceof DependencyUnavailableException) {
            return Status.UNAVAILABLE
                    .withDescription(
                            "A required service is temporarily unavailable")
                    .asRuntimeException();
        }
        if (error instanceof DependencyQuotaException) {
            return Status.RESOURCE_EXHAUSTED
                    .withDescription("A dependency quota has been exceeded")
                    .asRuntimeException();
        }
        if (error instanceof DependencyTimeoutException) {
            return Status.UNAVAILABLE
                    .withDescription("A required service did not respond in time")
                    .asRuntimeException();
        }

        // Lỗi chưa được nhận diện cần được xử lý ở mapper tổng quát
        // hoặc chuyển tới fallback INTERNAL có logging nội bộ.
        return Status.INTERNAL
                .withDescription("Internal server error")
                .asRuntimeException();
    }
}
```

Ví dụ ánh xạ dependency timeout thành `UNAVAILABLE` khi timeout đó thuộc ngân sách riêng của dependency và RPC đầu vào vẫn còn hạn. Nếu deadline của RPC hiện tại đã hết, gRPC sẽ kết thúc call bằng `DEADLINE_EXCEEDED`; không ghi đè semantics của deadline caller bằng một status khác.

Trong ứng dụng thực, mapper dependency nên được tích hợp vào mapper tổng thể để không vô tình biến domain exception, `StatusException` đã có hoặc lỗi bảo mật thành `INTERNAL`. Có thể giữ nguyên status đã được tạo có chủ đích nếu nó phù hợp hợp đồng API; description/trailers downstream cần được kiểm tra trước khi công bố.

## 5. Trả UNAVAILABLE từ Spring gRPC adapter

Adapter gọi application service và chuyển lỗi dependency đã phân loại thành status:

```java
@GrpcService
public class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    private final OrderApplicationService applicationService;
    private final DependencyStatusMapper statusMapper;

    public OrderGrpcService(
            OrderApplicationService applicationService,
            DependencyStatusMapper statusMapper) {
        this.applicationService = applicationService;
        this.statusMapper = statusMapper;
    }

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<Order> responseObserver) {
        try {
            Order order = applicationService.getOrder(request.getOrderId());
            responseObserver.onNext(toProto(order));
            responseObserver.onCompleted();
        } catch (DependencyUnavailableException
                | DependencyQuotaException
                | DependencyTimeoutException dependencyError) {
            responseObserver.onError(statusMapper.map(dependencyError));
        } catch (OrderNotFoundException missing) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Order not found")
                            .asRuntimeException());
        }
    }
}
```

Ví dụ chỉ minh họa các lỗi đã biết. Cần có fallback an toàn cho exception bất ngờ, ghi log nội bộ và trả `INTERNAL` chung. Không đưa exception message hoặc hostname nội bộ của dependency vào description.

Với streaming RPC, nếu dependency lỗi khi xử lý một message hoặc khi hoàn tất batch, server phải kết thúc response đúng một lần bằng status phù hợp. Sau `responseObserver.onError(...)`, không gửi thêm response message hoặc gọi `onCompleted()`. Nếu inbound call đã bị hủy, ưu tiên dừng tác vụ và cleanup thay vì cố gửi status trên call đã kết thúc.

## 6. Deadline phải truyền xuống dependency

Một RPC đầu vào có deadline 2 giây không thể cho phép mỗi dependency call tự chạy 5 giây. Nếu không giới hạn thời gian downstream, request có thể tiếp tục tiêu thụ thread/connection sau khi client đã nhận `DEADLINE_EXCEEDED`.

Lấy ngân sách còn lại từ gRPC `Context`:

```java
import io.grpc.Context;
import io.grpc.Deadline;
import java.util.concurrent.TimeUnit;

long dependencyBudgetNanos(
        long configuredMaximumNanos,
        long cleanupReserveNanos) {

    Deadline deadline = Context.current().getDeadline();
    if (deadline == null) {
        return configuredMaximumNanos;
    }

    long remaining = deadline.timeRemaining(TimeUnit.NANOSECONDS);
    long usable = remaining - cleanupReserveNanos;
    if (usable <= 0) {
        throw Status.DEADLINE_EXCEEDED
                .withDescription("Request deadline exceeded")
                .asRuntimeException();
    }
    return Math.min(usable, configuredMaximumNanos);
}
```

Với downstream gRPC, áp dụng ngân sách này cho stub:

```java
long budget = dependencyBudget(
        TimeUnit.SECONDS.toNanos(1),
        TimeUnit.MILLISECONDS.toNanos(50));

PaymentServiceGrpc.PaymentServiceBlockingStub bounded =
        paymentStub.withDeadlineAfter(budget, TimeUnit.NANOSECONDS);

return bounded.authorize(request);
```

Nếu call không có deadline, vẫn nên có timeout tối đa riêng cho dependency. Nếu ứng dụng tách Context khi chạy trên executor hoặc dùng HTTP/database client, hãy truyền ngân sách còn lại thành timeout của client đó; không giả định mọi thư viện ngoài gRPC tự hiểu `io.grpc.Context`.

## 7. Retry, circuit breaker và bulkhead

`UNAVAILABLE` có thể là lỗi tạm thời, nhưng retry không phải lúc nào cũng an toàn. Một dependency có thể đã thực hiện thao tác rồi mất response; gửi lại lệnh ghi có thể tạo tác dụng phụ trùng.

### Quy tắc retry

- Chỉ retry khi thao tác idempotent hoặc có idempotency key.
- Dùng exponential backoff kèm jitter; tránh retry đồng loạt sau khi dependency phục hồi.
- Giới hạn số lần thử và tổng thời gian retry theo deadline còn lại.
- Không retry `INVALID_ARGUMENT`, `PERMISSION_DENIED` hoặc lỗi domain không thể tự phục hồi.
- Tôn trọng quota và thời gian chờ mà dependency công bố.
- Tránh retry ở nhiều tầng cùng lúc; client, gateway và service đều retry có thể khuếch đại tải.

Ví dụ lịch chờ có giới hạn:

```text
Lần thử 1: ngay lập tức
Lần thử 2: 100 ms + jitter
Lần thử 3: 200 ms + jitter
Lần thử 4: 400 ms + jitter
Sau đó: dừng nếu hết retry budget hoặc deadline
```

Các giá trị chỉ minh họa; chính sách thực cần căn cứ SLA, tải và retry budget của hệ thống.

### Circuit breaker

Khi dependency thất bại liên tục, circuit breaker có thể mở để từ chối sớm thay vì tiếp tục gọi một hệ thống đang quá tải. Lỗi circuit-open thường có thể trả `UNAVAILABLE` vì dependency hiện không phục vụ request. Client không nên retry ngay lập tức; circuit breaker cần thời gian phục hồi và chuyển sang half-open theo chính sách.

### Bulkhead

Bulkhead giới hạn số call đồng thời hoặc kích thước hàng đợi tới dependency. Khi giới hạn nội bộ đã đầy, có thể trả `RESOURCE_EXHAUSTED` nếu đây là quota/capacity limit của caller hoặc hệ thống. Nếu policy coi đây là dependency tạm thời không sẵn sàng, có thể dùng `UNAVAILABLE`; phải thống nhất hợp đồng để client biết nên giảm tải hay chờ.

## 8. Fallback không được giả vờ thành công

Một số thao tác đọc có thể dùng cache hoặc dữ liệu stale khi dependency tạm thời mất kết nối. Nếu làm vậy:

- Xác định rõ dữ liệu có thể cũ đến mức nào.
- Đánh dấu nguồn hoặc freshness trong response nếu client cần biết.
- Không dùng fallback cho thao tác ghi hoặc nghiệp vụ yêu cầu tính nhất quán mạnh nếu chưa có thiết kế phù hợp.
- Không trả response mặc định như thể dependency đã xác nhận thành công.

Nếu không có fallback hợp lệ, trả `UNAVAILABLE` rõ ràng. Một lỗi minh bạch giúp client áp dụng retry hoặc thông báo đúng hơn một kết quả thành công giả.

## 9. Kiểm thử lỗi dependency

Kiểm thử mapper độc lập:

```java
import io.grpc.Status;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DependencyStatusMapperTest {

    private final DependencyStatusMapper mapper =
            new DependencyStatusMapper();

    @Test
    void temporaryDependencyFailureMapsToUnavailable() {
        var error = mapper.map(
                new DependencyUnavailableException("payment", null));

        assertEquals(Status.Code.UNAVAILABLE,
                error.getStatus().getCode());
    }

    @Test
    void quotaFailureDoesNotBecomeUnavailable() {
        var error = mapper.map(
                new DependencyQuotaException("payment", null));

        assertEquals(Status.Code.RESOURCE_EXHAUSTED,
                error.getStatus().getCode());
    }

    @Test
    void unknownFailureUsesSafeInternalFallback() {
        var error = mapper.map(new IllegalStateException("unexpected"));

        assertEquals(Status.Code.INTERNAL,
                error.getStatus().getCode());
        assertEquals("Internal server error",
                error.getStatus().getDescription());
    }
}
```

Integration test qua gRPC in-process nên dùng fake dependency để mô phỏng:

| Ca | Kỳ vọng |
| --- | --- |
| Dependency gRPC trả `UNAVAILABLE` | API hiện tại trả `UNAVAILABLE` theo hợp đồng |
| HTTP dependency trả 503 | Ánh xạ `UNAVAILABLE` |
| HTTP dependency trả 429 | Ánh xạ quota, thường là `RESOURCE_EXHAUSTED` |
| Dependency trả lỗi nghiệp vụ `NOT_FOUND` | Giữ ý nghĩa `NOT_FOUND`, không đổi thành `UNAVAILABLE` |
| Circuit breaker open | Từ chối sớm, không gọi dependency |
| Deadline caller hết trước downstream | Client nhận `DEADLINE_EXCEEDED`; downstream bị dừng khi có thể |
| Dependency timeout trong khi caller còn hạn | Status theo chính sách dependency đã công bố |
| Retry thao tác ghi | Cùng idempotency key, không tạo tác dụng phụ trùng |

Kiểm thử cần xác nhận cả status code và số lần gọi dependency. Một test chỉ thấy `UNAVAILABLE` nhưng không kiểm tra retry count có thể bỏ sót vòng retry quá mức.

## 10. Quan sát và vận hành

Ghi metrics theo dependency và operation:

- Số lần gọi, latency và timeout.
- Số lỗi theo status code và loại dependency.
- Retry count, số lần circuit breaker mở/half-open và bulkhead rejection.
- Số request bị hủy do deadline và thời gian còn lại khi gọi downstream.
- Tỷ lệ fallback và độ mới của dữ liệu fallback.

Log nên có tên dependency, operation, gRPC method, status và correlation ID. Không log bearer token, payload, SQL chứa dữ liệu khách hàng hoặc exception message chưa được kiểm soát. Description trả client nên chung và không tiết lộ hostname, topology hoặc địa chỉ nội bộ.

Nếu `UNAVAILABLE` tăng đồng thời ở nhiều dependency, có thể là sự cố mạng hoặc quá tải chung. Nếu chỉ một dependency tăng, tập trung điều tra endpoint, connection pool, DNS, quota và health của dependency đó.

## 11. Tự luyện tập

1. Một downstream HTTP API trả 503. Vì sao `UNAVAILABLE` phù hợp hơn `INTERNAL` nếu sự cố được xác định là tạm thời?
2. Downstream trả 404 vì khách hàng không tồn tại. Vì sao không nên đổi status đó thành `UNAVAILABLE`?
3. RPC đầu vào còn 300 ms nhưng timeout mặc định của HTTP client là 3 giây. Bạn cần truyền ngân sách như thế nào?
4. Một lệnh thanh toán nhận `UNAVAILABLE` sau khi downstream có thể đã commit. Cần dùng idempotency và tra cứu trạng thái ra sao trước retry?
5. Circuit breaker mở và bulkhead đầy đều từ chối request. Hãy chọn status cho từng trường hợp theo hợp đồng API và giải thích phản ứng client.

**Ghi nhớ:** Dùng `UNAVAILABLE` khi dependency thực sự tạm thời không sẵn sàng; phân biệt với deadline hết hạn, quota, lỗi domain và bug nội bộ. Chuẩn hóa exception theo nguyên nhân, truyền deadline còn lại xuống downstream, retry có backoff chỉ khi an toàn, và kết hợp circuit breaker/bulkhead để ngăn sự cố lan rộng.
