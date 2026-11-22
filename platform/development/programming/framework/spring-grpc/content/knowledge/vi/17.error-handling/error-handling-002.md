# Đọc status code và status description

**Chương:** Error handling  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng Protocol Buffers, mã Java được sinh và các RPC unary hoặc streaming. Bài này tập trung vào cách **đọc và diễn giải gRPC status** ở client: mã trạng thái cho logic máy đọc và description cho thông tin giải thích.

## 1. Một gRPC error có những thông tin nào?

Khi RPC kết thúc lỗi, client thường nhận một `StatusRuntimeException` hoặc `StatusException`. Đối tượng này mang một `Status`, trong đó có hai thông tin thường được ứng dụng quan tâm:

- **Status code:** mã chuẩn, ví dụ `NOT_FOUND`, `INVALID_ARGUMENT`, `UNAVAILABLE`. Đây là tín hiệu ổn định để chương trình phân loại lỗi.
- **Status description:** chuỗi mô tả tùy chọn, ví dụ `Customer not found`. Giá trị có thể là `null`, thay đổi theo phiên bản hoặc ngôn ngữ, và không nên được dùng làm khóa điều khiển.

Ngoài ra, lỗi có thể mang cause ở phía Java và metadata trailers. Hai thông tin đó có mục đích riêng; không nhầm chúng với status code hoặc description.

```text
RPC thất bại
    |
    v
StatusRuntimeException / StatusException
    |
    +-- Status code       -> phân loại bằng enum
    |
    +-- Description       -> thông tin giải thích, có thể null
    |
    +-- Cause             -> nguyên nhân Java nếu có
    |
    +-- Trailers          -> metadata cuối RPC nếu có
```

**Nguyên tắc:** dùng code để quyết định hành vi; dùng description để hiển thị hoặc hỗ trợ chẩn đoán sau khi đã kiểm tra an toàn.

## 2. Trích Status từ Throwable

API thông dụng là `Status.fromThrowable(Throwable)`. Hàm này tìm gRPC status trong exception hoặc cause chain. Nếu throwable không chứa `StatusException` hay `StatusRuntimeException`, kết quả là status `UNKNOWN` mang cause đó; vì vậy không nên giả định mọi exception đều chứa status do server chủ động chọn.

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

try {
    Customer customer = blockingStub.findCustomer(request);
    use(customer);
} catch (StatusRuntimeException error) {
    Status status = Status.fromThrowable(error);

    Status.Code code = status.getCode();
    String description = status.getDescription(); // Có thể null.

    handle(code, description);
}
```

Có thể đọc trực tiếp từ exception:

```java
Status status = error.getStatus();
Status.Code code = status.getCode();
String description = status.getDescription();
```

Tuy nhiên, `Status.fromThrowable` tiện hơn khi tầng gọi chỉ có kiểu `Throwable`, chẳng hạn trong callback async hoặc khi lỗi được bọc trong một exception khác.

### Xử lý description có thể null

`getDescription()` không bảo đảm luôn trả chuỗi. Server có thể chỉ trả status code mà không đặt description. Vì vậy, tránh gọi trực tiếp `description.toLowerCase()`, `description.contains(...)` hoặc đưa giá trị null vào UI mà không có fallback.

```java
String description = status.getDescription();
String safeDescription =
        (description == null || description.isBlank())
                ? "Yêu cầu không thể hoàn tất"
                : description;
```

Fallback chỉ phục vụ hiển thị. Logic nghiệp vụ vẫn phải dựa trên `status.getCode()`.

## 3. Status code là hợp đồng máy đọc

Các code của gRPC là enum chuẩn. Một số code thường gặp:

| Code | Ý nghĩa tổng quát | Cách ứng dụng thường phản ứng |
| --- | --- | --- |
| `INVALID_ARGUMENT` | Tham số/request không hợp lệ | Hiển thị lỗi đầu vào; sửa request |
| `NOT_FOUND` | Tài nguyên không tồn tại | Hiển thị trạng thái không tìm thấy |
| `ALREADY_EXISTS` | Tài nguyên đã tồn tại | Tra cứu hoặc xử lý xung đột |
| `UNAUTHENTICATED` | Thiếu hoặc sai thông tin xác thực | Đăng nhập/làm mới credential theo chính sách |
| `PERMISSION_DENIED` | Đã xác thực nhưng không có quyền | Dừng thao tác và báo quyền truy cập |
| `FAILED_PRECONDITION` | Trạng thái hiện tại chưa cho phép thao tác | Thay đổi điều kiện trước khi thử lại |
| `ABORTED` | Thao tác bị hủy do xung đột | Có thể thử lại ở cấp transaction/workflow |
| `RESOURCE_EXHAUSTED` | Hết quota hoặc tài nguyên | Giảm tải, chờ hoặc chia nhỏ công việc |
| `DEADLINE_EXCEEDED` | RPC vượt ngân sách thời gian | Xác minh kết quả nếu thao tác có tác dụng phụ |
| `CANCELLED` | RPC bị hủy | Dừng công việc; không tự retry |
| `UNAVAILABLE` | Dịch vụ tạm thời không sẵn sàng | Có thể retry có backoff nếu thao tác an toàn |
| `UNIMPLEMENTED` | Phương thức chưa được hỗ trợ | Kiểm tra phiên bản/hợp đồng client-server |
| `INTERNAL` | Lỗi nội bộ | Ghi log có kiểm soát và điều tra |
| `DATA_LOSS` | Mất hoặc hỏng dữ liệu nghiêm trọng | Báo lỗi và xử lý theo quy trình phục hồi |
| `UNKNOWN` | Không xác định được nguyên nhân cụ thể | Điều tra cause/log; không suy đoán từ description |

Các code này không phải tất cả đều có nghĩa “server lỗi”. Ví dụ `INVALID_ARGUMENT` thường là request không hợp lệ; `PERMISSION_DENIED` là quyết định quyền; `UNAVAILABLE` có thể là sự cố tạm thời.

## 4. Status description là thông tin giải thích, không phải mã lỗi

Server có thể tạo status như sau:

```java
responseObserver.onError(
        Status.NOT_FOUND
                .withDescription("Customer not found")
                .asRuntimeException());
```

Client nhận:

- `getCode() == NOT_FOUND`
- `getDescription() == "Customer not found"` nếu description được truyền nguyên vẹn.

Description giúp con người hiểu lỗi, nhưng không nên dùng nó để quyết định luồng chương trình:

```java
// Không nên: phụ thuộc câu chữ có thể thay đổi.
if ("Customer not found".equals(status.getDescription())) {
    showNotFound();
}

// Nên: dùng mã trạng thái chuẩn.
if (status.getCode() == Status.Code.NOT_FOUND) {
    showNotFound();
}
```

Một server khác có thể dùng description `No customer for id`, hoặc không gửi description. Cả hai vẫn có thể mang code `NOT_FOUND`. Description cũng có thể được bản địa hóa hoặc thay đổi để tránh tiết lộ thông tin nội bộ.

### Không hiển thị nguyên văn mọi description cho người dùng

Description do server tạo, nhưng có thể chứa chi tiết kỹ thuật hoặc dữ liệu đầu vào. Ứng dụng nên ánh xạ code sang thông báo người dùng đã kiểm soát; description chỉ dùng cho log hoặc giao diện kỹ thuật đã được phép.

## 5. Phân loại lỗi trong client Spring gRPC

Đưa logic phân loại vào một hàm nhỏ giúp blocking và async client dùng chung chính sách:

```java
import io.grpc.Status;

enum RpcFailureAction {
    FIX_REQUEST,
    AUTHENTICATE,
    STOP,
    RETRY_WITH_BACKOFF,
    CHECK_OPERATION_RESULT,
    INVESTIGATE
}

RpcFailureAction classify(Status.Code code) {
    return switch (code) {
        case INVALID_ARGUMENT -> RpcFailureAction.FIX_REQUEST;
        case UNAUTHENTICATED -> RpcFailureAction.AUTHENTICATE;
        case CANCELLED, PERMISSION_DENIED, NOT_FOUND ->
                RpcFailureAction.STOP;
        case UNAVAILABLE, RESOURCE_EXHAUSTED ->
                RpcFailureAction.RETRY_WITH_BACKOFF;
        case DEADLINE_EXCEEDED ->
                RpcFailureAction.CHECK_OPERATION_RESULT;
        default -> RpcFailureAction.INVESTIGATE;
    };
}
```

Đây là chính sách minh họa, không phải quy tắc retry tự động cho mọi hệ thống. Đặc biệt:

- `RESOURCE_EXHAUSTED` chỉ nên retry sau khi đã giảm tải hoặc hết thời gian quota; retry ngay có thể làm tình trạng nặng hơn.
- `UNAVAILABLE` có thể retry với exponential backoff và jitter, nhưng chỉ khi thao tác an toàn hoặc có idempotency key.
- `DEADLINE_EXCEEDED` không chứng minh server chưa thực hiện thao tác. Với thao tác ghi, cần tra cứu trạng thái hoặc dùng idempotency trước khi gửi lại.
- `ABORTED` thường cần thử lại một workflow/transaction lớn hơn, không chỉ lặp đúng một request không đổi.
- `FAILED_PRECONDITION` cần sửa trạng thái hoặc điều kiện trước, không retry mù.

### Dùng trong callback async

```java
StreamObserver<UploadReceipt> responseObserver = new StreamObserver<>() {
    @Override
    public void onNext(UploadReceipt receipt) {
        showReceipt(receipt);
    }

    @Override
    public void onError(Throwable error) {
        Status status = Status.fromThrowable(error);
        Status.Code code = status.getCode();
        String description = status.getDescription();

        RpcFailureAction action = classify(code);
        reportFailure(action, code, safeForDiagnostics(description));
    }

    @Override
    public void onCompleted() {
        finishUpload();
    }
};
```

Với client streaming, `onCompleted()` của response observer chỉ chạy khi response kết thúc bình thường. Nếu server trả lỗi, client nhận `onError()`; không được đánh dấu batch thành công chỉ vì client đã gọi `requestObserver.onCompleted()` để half-close chiều gửi.

## 6. Status trailers là metadata riêng

Status code và description không phải toàn bộ thông tin lỗi. Server có thể gửi **trailers** để cung cấp mã lỗi chi tiết hoặc correlation token an toàn:

```java
Metadata trailers = new Metadata();
Metadata.Key<String> errorCode =
        Metadata.Key.of(
                "error-code",
                Metadata.ASCII_STRING_MARSHALLER);
trailers.put(errorCode, "CUSTOMER_SUSPENDED");

responseObserver.onError(
        Status.FAILED_PRECONDITION
                .withDescription("Customer cannot perform this operation")
                .asRuntimeException(trailers));
```

Client đọc trailers bằng:

```java
Status status = Status.fromThrowable(error);
Metadata trailers = Status.trailersFromThrowable(error);

String applicationCode =
        trailers == null ? null : trailers.get(errorCode);
```

Hãy dùng status code để phân loại tổng quát, trailers cho mã nghiệp vụ có cấu trúc khi cần, và description cho lời giải thích. Không nhét token, mật khẩu, stack trace hoặc payload lớn vào description/trailers.

## 7. Cause và status không phải một

Ở server, exception nội bộ có thể là nguyên nhân tạo ra status:

```java
try {
    repository.save(entity);
} catch (DataAccessException databaseError) {
    log.error("Cannot persist customer", databaseError);
    responseObserver.onError(
            Status.INTERNAL
                    .withDescription("Internal server error")
                    .withCause(databaseError)
                    .asRuntimeException());
}
```

`withCause` giữ nguyên nguyên nhân trong exception Java phía server. **Cause không phải trường status code được gửi nguyên dạng qua wire**; client không nên kỳ vọng nhận được stack trace hoặc class exception database của server. Client nên đọc status/trailers; server ghi cause trong log nội bộ có correlation ID.

Khi `Status.fromThrowable(error)` không tìm thấy gRPC status trong cause chain, kết quả là `UNKNOWN` gắn với throwable. Vì vậy, nếu client thấy `UNKNOWN`, hãy kiểm tra cause/log và ranh giới adapter; đừng tìm một câu description cụ thể để suy ra nguyên nhân.

## 8. Kiểm thử status code và description

Kiểm thử đơn vị xác nhận code và description độc lập:

```java
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class StatusReadingTest {

    @Test
    void readsCodeAndDescription() {
        StatusRuntimeException error = Status.NOT_FOUND
                .withDescription("Customer not found")
                .asRuntimeException();

        Status status = Status.fromThrowable(error);

        assertEquals(Status.Code.NOT_FOUND, status.getCode());
        assertEquals("Customer not found", status.getDescription());
    }

    @Test
    void descriptionCanBeAbsent() {
        StatusRuntimeException error =
                Status.INVALID_ARGUMENT.asRuntimeException();

        Status status = Status.fromThrowable(error);

        assertEquals(Status.Code.INVALID_ARGUMENT, status.getCode());
        assertNull(status.getDescription());
    }
}
```

Kiểm thử tích hợp qua gRPC in-process hoặc transport thật nên xác nhận:

1. Server trả đúng code khi request sai hoặc tài nguyên không tồn tại.
2. Client trích đúng code bằng `Status.fromThrowable`.
3. Description có thể vắng mặt; client không ném `NullPointerException`.
4. Trailers được trích riêng và không bị nhầm với description.
5. Client không phụ thuộc câu chữ description để quyết định retry hoặc hiển thị trạng thái nghiệp vụ.

Không kiểm tra class exception ở client để suy luận server đã ném class nào. Ranh giới RPC truyền status và metadata, không truyền object Java của server.

## 9. Checklist khi đọc lỗi RPC

- Đọc `Status.Code` trước; đây là cơ sở phân loại lỗi.
- Đọc description theo kiểu nullable và dùng fallback nếu thiếu.
- Không parse description hoặc so sánh nguyên văn để điều khiển logic.
- Đọc trailers riêng nếu hợp đồng có mã lỗi nghiệp vụ.
- Giữ cause/stack trace ở log nội bộ; không giả định client nhận cause server.
- Quyết định retry dựa trên code, tính idempotent, deadline còn lại và retry budget.
- Với `DEADLINE_EXCEEDED` hoặc `UNAVAILABLE` sau thao tác ghi, xác minh kết quả trước khi gửi lại.

## 10. Tự luyện tập

1. Hai server trả description khác nhau nhưng cùng code `NOT_FOUND`. Vì sao client vẫn nên xử lý giống nhau?
2. `Status.getDescription()` trả `null`. Hãy viết cách tạo thông báo mặc định mà không ảnh hưởng phân loại lỗi.
3. Một callback async nhận `CompletionException` bọc `StatusRuntimeException`. Dùng API nào để lấy code mà không phân tích chuỗi?
4. Server có lỗi database và trả `INTERNAL` với description chung. Vì sao client không nên nhận stack trace qua description?
5. Client nhận `DEADLINE_EXCEEDED` sau khi gửi yêu cầu tạo đơn hàng. Cần kiểm tra điều gì trước khi retry?

**Ghi nhớ:** `status code` là tín hiệu chuẩn để chương trình phân loại lỗi; `status description` là thông tin giải thích tùy chọn và có thể null. Dùng `Status.fromThrowable()` để trích status, xử lý theo enum code, đọc trailers riêng và không phụ thuộc câu chữ description cho logic hoặc retry.
