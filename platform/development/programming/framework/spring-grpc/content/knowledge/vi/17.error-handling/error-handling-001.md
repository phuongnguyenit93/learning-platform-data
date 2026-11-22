# StatusRuntimeException và StatusException

**Chương:** Error handling  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng hợp đồng Protocol Buffers, mã Java được sinh và các RPC unary hoặc streaming. Bài này tập trung vào hai kiểu exception của gRPC Java dùng để biểu diễn một gRPC status: `StatusRuntimeException` và `StatusException`.

## 1. Hai kiểu exception biểu diễn cùng một loại lỗi RPC

Khi server cần từ chối request, gRPC không gửi một Java exception qua mạng. Server kết thúc RPC bằng **gRPC status** gồm mã trạng thái, mô tả và có thể có metadata trailers. Trong Java, thư viện cung cấp hai lớp exception để mang status đó:

| Đặc điểm | `StatusRuntimeException` | `StatusException` |
| --- | --- | --- |
| Kiểu Java | Kế thừa `RuntimeException` | Kế thừa `Exception` |
| Phân loại | Unchecked exception | Checked exception |
| Khai báo `throws` | Không bắt buộc khai báo | Phải bắt hoặc khai báo ở method có thể phát sinh |
| Tạo từ `Status` | `status.asRuntimeException()` | `status.asException()` |
| Truyền qua callback gRPC | Có thể truyền vào `responseObserver.onError(...)` | Có thể truyền vào `responseObserver.onError(...)` |
| Ý nghĩa trên wire | Gửi gRPC status và trailers | Gửi gRPC status và trailers |

**Khác biệt chính nằm ở cách Java yêu cầu xử lý exception, không nằm ở giao thức gRPC.** Nếu cả hai mang cùng status code và trailers, client nhận cùng ý nghĩa lỗi RPC. Việc dùng checked hay unchecked không tạo ra hai loại status khác nhau trên mạng.

Ví dụ, hai cách dưới đây đều tạo lỗi `INVALID_ARGUMENT`:

```java
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;

Status invalid = Status.INVALID_ARGUMENT
        .withDescription("customer_id is required");

StatusRuntimeException unchecked = invalid.asRuntimeException();
StatusException checked = invalid.asException();
```

Không nên chọn kiểu exception theo cảm tính hoặc nghĩ rằng `StatusException` là lỗi “nhẹ” hơn. Hãy chọn theo ranh giới API Java và giữ cách xử lý nhất quán.

## 2. Tạo exception từ Status

`io.grpc.Status` là đối tượng mô tả kết quả RPC. Các hằng như `INVALID_ARGUMENT`, `NOT_FOUND`, `UNAUTHENTICATED` và `INTERNAL` cung cấp mã chuẩn. Có thể bổ sung mô tả và trailers trước khi chuyển thành exception.

### Dùng StatusRuntimeException

Trong một handler bất đồng bộ của Spring gRPC, cách thường gặp là gọi `responseObserver.onError(...)`:

```java
responseObserver.onError(
        Status.NOT_FOUND
                .withDescription("Không tìm thấy đơn hàng")
                .asRuntimeException());
```

`asRuntimeException()` tạo `StatusRuntimeException`. Vì đây là unchecked exception, code không cần khai báo `throws`. Tuy nhiên, trong API callback, **truyền exception cho `onError`** thường rõ ràng hơn việc ném exception ra khỏi callback.

### Dùng StatusException

`StatusException` phù hợp khi helper hoặc tầng nghiệp vụ muốn biểu diễn lỗi bằng checked exception:

```java
private void validateCustomerId(String customerId)
        throws StatusException {
    if (customerId == null || customerId.isBlank()) {
        throw Status.INVALID_ARGUMENT
                .withDescription("customer_id is required")
                .asException();
    }
}
```

Ở ranh giới gRPC, bắt exception rồi chuyển nó thành terminal callback:

```java
@Override
public void findCustomer(
        FindCustomerRequest request,
        StreamObserver<Customer> responseObserver) {
    try {
        validateCustomerId(request.getCustomerId());
        Customer customer = service.find(request.getCustomerId());
        responseObserver.onNext(customer);
        responseObserver.onCompleted();
    } catch (StatusException statusError) {
        responseObserver.onError(statusError);
    }
}
```

Method generated service thường không khai báo `throws StatusException`; vì vậy không thể ném checked exception tùy ý ra khỏi override. Hãy bắt tại adapter và chuyển qua `responseObserver.onError`. Với `StatusRuntimeException`, cũng có thể truyền trực tiếp vào callback.

## 3. Truyền trailers cùng status

Trailers là metadata được gửi khi RPC kết thúc. Chúng có thể mang mã lỗi máy đọc được hoặc thông tin hỗ trợ chẩn đoán không nhạy cảm. Ví dụ:

```java
import io.grpc.Metadata;
import io.grpc.Status;

private static final Metadata.Key<String> ERROR_CODE =
        Metadata.Key.of(
                "error-code",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata trailers = new Metadata();
trailers.put(ERROR_CODE, "CUSTOMER_NOT_ACTIVE");

responseObserver.onError(
        Status.FAILED_PRECONDITION
                .withDescription("Khách hàng chưa thể thực hiện thao tác")
                .asRuntimeException(trailers));
```

Nếu API nội bộ dùng checked exception, có thể tạo cùng status và trailers bằng `asException(trailers)`. Khi nhận ở client, trailers có thể được lấy bằng `Status.trailersFromThrowable(error)`.

Quy tắc khi dùng trailers:

- Tên key metadata phải theo quy tắc gRPC; key nhị phân có hậu tố `-bin` và dùng binary marshaller.
- Chỉ đưa thông tin cần thiết để client xử lý hoặc hỗ trợ vận hành.
- Không gửi access token, mật khẩu, dữ liệu cá nhân hoặc stack trace trong trailers.
- Tránh đưa payload lớn vào trailers; metadata có giới hạn kích thước tùy transport/proxy.
- Mô tả lỗi cho client nên ổn định và an toàn; chi tiết nội bộ ghi ở log phía server với correlation ID.

## 4. Server Spring gRPC: ánh xạ lỗi nghiệp vụ thành status

Không nên để mọi lỗi đều biến thành `INTERNAL`, cũng không nên trả nguyên exception nội bộ cho client. Adapter gRPC cần phân biệt lỗi đầu vào, không tìm thấy tài nguyên và lỗi hệ thống.

```java
@GrpcService
public class CustomerGrpcService
        extends CustomerServiceGrpc.CustomerServiceImplBase {

    private final CustomerApplicationService service;

    public CustomerGrpcService(CustomerApplicationService service) {
        this.service = service;
    }

    @Override
    public void findCustomer(
            FindCustomerRequest request,
            StreamObserver<Customer> responseObserver) {
        try {
            if (request.getCustomerId().isBlank()) {
                responseObserver.onError(
                        Status.INVALID_ARGUMENT
                                .withDescription("customer_id is required")
                                .asRuntimeException());
                return;
            }

            Customer customer = service.find(request.getCustomerId());
            if (customer == null) {
                responseObserver.onError(
                        Status.NOT_FOUND
                                .withDescription("Customer not found")
                                .asRuntimeException());
                return;
            }

            responseObserver.onNext(customer);
            responseObserver.onCompleted();
        } catch (CustomerRuleException ruleError) {
            responseObserver.onError(
                    Status.FAILED_PRECONDITION
                            .withDescription("Customer operation is not allowed")
                            .asRuntimeException());
        } catch (RuntimeException unexpected) {
            // Ghi chi tiết nội bộ ở server; không gửi exception ra ngoài.
            log.error("Unexpected error in findCustomer", unexpected);
            responseObserver.onError(
                    Status.INTERNAL
                            .withDescription("Internal server error")
                            .asRuntimeException());
        }
    }
}
```

Ví dụ dùng `StatusRuntimeException` vì handler callback không cần khai báo checked exception. Nếu tầng application có method phát sinh `StatusException`, adapter có thể bắt và chuyển exception đó sang `onError` như mục 2.

Một số nguyên tắc:

1. **Lỗi do client gửi:** dùng status như `INVALID_ARGUMENT` khi request sai cấu trúc hoặc giá trị.
2. **Không tồn tại:** dùng `NOT_FOUND` nếu tài nguyên được yêu cầu không có.
3. **Vi phạm trạng thái nghiệp vụ:** dùng `FAILED_PRECONDITION` hoặc status phù hợp hợp đồng.
4. **Lỗi bất ngờ phía server:** log exception nội bộ và trả mô tả chung với `INTERNAL`.
5. **Kết thúc đúng một lần:** sau `onError`, không gọi tiếp `onNext` hoặc `onCompleted` trên cùng response observer.

Không bắt `Throwable` một cách tùy tiện để biến cả lỗi JVM nghiêm trọng thành status bình thường. Chỉ ánh xạ các loại lỗi mà tầng ứng dụng có thể xử lý có chủ đích.

## 5. Client đọc StatusRuntimeException và StatusException

Ở client, blocking stub thường báo lỗi RPC bằng `StatusRuntimeException`. Với async stub, callback `onError(Throwable)` nhận nguyên nhân lỗi; ứng dụng nên dùng API của gRPC để trích status thay vì so sánh chuỗi thông báo.

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

try {
    Customer customer = blockingStub.findCustomer(request);
    // Xử lý customer.
} catch (StatusRuntimeException error) {
    Status status = Status.fromThrowable(error);
    Metadata trailers = Status.trailersFromThrowable(error);

    switch (status.getCode()) {
        case NOT_FOUND -> showNotFound();
        case INVALID_ARGUMENT -> showInvalidInput();
        case UNAVAILABLE -> scheduleRetry();
        default -> logRpcFailure(status.getCode());
    }

    if (trailers != null) {
        String code = trailers.get(ERROR_CODE);
        if (code != null) {
            logSafeErrorCode(code);
        }
    }
}
```

`Status.fromThrowable(Throwable)` trích gRPC status từ exception hoặc cause chain. `Status.trailersFromThrowable(Throwable)` lấy trailers nếu exception mang chúng. Với helper tầng Java có thể phát `StatusException`, client code cũng có thể dùng cùng hai hàm này; không cần phân nhánh theo class để hiểu mã lỗi.

Trong callback async:

```java
StreamObserver<Customer> responseObserver = new StreamObserver<>() {
    @Override
    public void onNext(Customer customer) {
        handleCustomer(customer);
    }

    @Override
    public void onError(Throwable error) {
        Status status = Status.fromThrowable(error);
        handleRpcStatus(status.getCode());
    }

    @Override
    public void onCompleted() {
        finishRequest();
    }
};
```

Đừng coi mọi lỗi `UNAVAILABLE` hoặc `DEADLINE_EXCEEDED` là chắc chắn retry an toàn. Với RPC có tác dụng phụ, client cần idempotency key hoặc tra cứu trạng thái trước khi gửi lại.

## 6. Chọn status code theo ý nghĩa, không theo class exception

`StatusRuntimeException` và `StatusException` không quyết định mã lỗi. Mã được quyết định bởi đối tượng `Status` dùng để tạo chúng.

| Status | Dùng khi | Retry? |
| --- | --- | --- |
| `INVALID_ARGUMENT` | Tham số hoặc message không hợp lệ | Thường không; sửa request trước |
| `NOT_FOUND` | Tài nguyên không tồn tại | Tùy nghiệp vụ; thường không retry ngay |
| `ALREADY_EXISTS` | Tài nguyên hoặc khóa đã tồn tại | Kiểm tra trạng thái hiện tại |
| `FAILED_PRECONDITION` | Trạng thái hiện tại không cho phép thao tác | Cần thay đổi điều kiện trước |
| `UNAUTHENTICATED` | Thiếu hoặc không hợp lệ thông tin xác thực | Làm mới thông tin xác thực theo chính sách |
| `PERMISSION_DENIED` | Caller đã xác thực nhưng không có quyền | Không retry nguyên trạng |
| `RESOURCE_EXHAUSTED` | Vượt quota hoặc tài nguyên tạm thời cạn | Giảm tải/chờ theo retry policy |
| `UNAVAILABLE` | Dịch vụ tạm thời không sẵn sàng | Có thể retry có backoff nếu thao tác an toàn |
| `DEADLINE_EXCEEDED` | RPC vượt ngân sách thời gian | Kết quả có thể chưa rõ; xác minh trước retry |
| `INTERNAL` | Lỗi nội bộ ngoài dự kiến | Điều tra; không lộ chi tiết nội bộ |

Chọn status theo hợp đồng API để client có thể xử lý ổn định. Không dùng `INTERNAL` cho mọi lỗi validation, và không dùng `INVALID_ARGUMENT` để che lỗi database hoặc lỗi lập trình.

## 7. Kiểm thử hai exception type

Có thể kiểm thử việc tạo và trích status trực tiếp mà không cần transport:

```java
import io.grpc.Status;
import io.grpc.StatusException;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GrpcStatusExceptionTest {

    @Test
    void bothExceptionTypesCarryTheSameGrpcCode() {
        Status status = Status.INVALID_ARGUMENT
                .withDescription("missing customer_id");

        StatusRuntimeException runtimeError =
                status.asRuntimeException();
        StatusException checkedError =
                status.asException();

        assertEquals(Status.Code.INVALID_ARGUMENT,
                Status.fromThrowable(runtimeError).getCode());
        assertEquals(Status.Code.INVALID_ARGUMENT,
                Status.fromThrowable(checkedError).getCode());
    }
}
```

Kiểm thử tích hợp cần gọi service qua gRPC in-process hoặc transport thực, sau đó kiểm tra **status code và trailers** mà client nhận được. Không nên khẳng định client luôn nhận đúng cùng class Java mà server đã tạo: qua ranh giới RPC, điều quan trọng là status/trailers trên wire, không phải danh tính object exception ở server.

Các ca nên có:

- Request sai nhận `INVALID_ARGUMENT`.
- Tài nguyên thiếu nhận `NOT_FOUND`.
- Lỗi nghiệp vụ nhận status đã quy định.
- Lỗi nội bộ không làm lộ stack trace hoặc thông tin nhạy cảm.
- Trailers có mã lỗi dự kiến và không chứa bí mật.
- Client xử lý status bằng `Status.fromThrowable`, không phân tích chuỗi description.

## 8. Quy tắc lựa chọn trong dự án Spring gRPC

| Ranh giới code | Lựa chọn phù hợp |
| --- | --- |
| Handler gRPC bất đồng bộ gọi `responseObserver.onError` | Có thể tạo `StatusRuntimeException` trực tiếp |
| Helper nghiệp vụ muốn buộc caller xử lý lỗi | Có thể khai báo `throws StatusException` |
| Adapter nhận checked exception từ tầng dưới | Bắt và chuyển qua `responseObserver.onError` |
| Client cần phân loại lỗi RPC | Dùng `Status.fromThrowable` và `Status.trailersFromThrowable` |

Không cần đổi toàn bộ code từ kiểu này sang kiểu kia chỉ để “chuẩn hóa gRPC”. Hãy chọn một quy ước theo ranh giới Java của dự án, nhưng thống nhất **status code, description an toàn và trailers** để client không phụ thuộc cách server biểu diễn exception nội bộ.

## 9. Tự luyện tập

1. Viết một helper validation khai báo `throws StatusException`; chuyển lỗi đó thành `responseObserver.onError` ở service adapter.
2. Chuyển cùng helper sang trả `StatusRuntimeException`. Khác biệt nào xuất hiện trong chữ ký method và nơi compiler yêu cầu xử lý?
3. Thêm trailer `error-code` cho lỗi `FAILED_PRECONDITION`; viết client đọc trailer bằng `Status.trailersFromThrowable`.
4. Một lỗi database phát sinh khi tìm khách hàng. Vì sao không nên gửi nguyên message exception hoặc SQL ra client?
5. Viết integration test chứng minh hai kiểu exception tạo cùng gRPC status code khi truyền qua RPC.

**Ghi nhớ:** `StatusRuntimeException` là unchecked, `StatusException` là checked; cả hai đều mang gRPC `Status` và trailers. Chọn kiểu theo ranh giới Java, ánh xạ lỗi nghiệp vụ sang status code có ý nghĩa, gửi qua `responseObserver.onError`, và để client đọc bằng `Status.fromThrowable` thay vì phụ thuộc class exception hoặc chuỗi thông báo.
