# Không lộ stack trace hoặc dữ liệu nhạy cảm

**Chương:** Error handling  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng Protocol Buffers, mã Java được sinh và RPC unary hoặc streaming. Bài này tập trung vào việc **giữ thông tin chẩn đoán nội bộ ở phía server, đồng thời chỉ trả cho client status và thông tin lỗi an toàn**.

## 1. Response lỗi cũng là một ranh giới bảo mật

Khi một RPC thất bại, server thường kết thúc bằng `responseObserver.onError(...)`. Những gì server đặt trong gRPC status description, trailers hoặc error details đều có thể đến client. Client có thể là ứng dụng hợp lệ, nhưng cũng có thể là phiên bản cũ, một tích hợp bên thứ ba hoặc caller đang cố khai thác thông tin nội bộ.

Ví dụ không an toàn:

```java
catch (Exception error) {
    responseObserver.onError(
            Status.INTERNAL
                    .withDescription(error.getMessage())
                    .asRuntimeException());
}
```

`error.getMessage()` có thể chứa câu SQL, tên bảng, đường dẫn file, hostname nội bộ, access token, email, số điện thoại hoặc dữ liệu request. Nếu đưa nguyên văn vào description, server đã biến thông tin chẩn đoán thành dữ liệu công khai của API.

Stack trace cũng có thể tiết lộ package nội bộ, tên lớp, phiên bản thư viện, đường dẫn triển khai và cấu trúc hệ thống. **Không gửi stack trace, cause hoặc exception message thô trong status, trailers hay protobuf response.**

Ranh giới thông tin nên được thiết kế như sau:

```text
Exception / failure nội bộ
        |
        +----> Log/diagnostic nội bộ có kiểm soát
        |        - exception class
        |        - stack trace khi được phép
        |        - trace/support reference
        |        - dữ liệu đã redaction
        |
        +----> gRPC response công khai
                 - status code phù hợp
                 - description chung, an toàn
                 - error code ổn định nếu cần
                 - support reference không nhạy cảm
```

## 2. Những dữ liệu không nên trả về client

| Dữ liệu | Vì sao nhạy cảm | Cách xử lý |
| --- | --- | --- |
| Stack trace | Tiết lộ cấu trúc code, thư viện và đường dẫn nội bộ | Chỉ giữ trong hệ thống chẩn đoán nội bộ có kiểm soát |
| SQL/query và tên bảng | Tiết lộ schema, logic truy cập dữ liệu, đôi khi cả giá trị đầu vào | Trả status tổng quát; ghi diagnostic đã lọc |
| Password, API key, access/refresh token | Có thể cho phép truy cập trái phép | Không ghi log hoặc gửi qua error metadata |
| PII như email, số điện thoại, địa chỉ | Có thể bị lộ qua log hoặc response | Chỉ dùng định danh đã giảm thiểu; che hoặc loại bỏ |
| Payload protobuf | Có thể chứa bí mật hoặc dữ liệu khách hàng | Không serialize toàn request vào log lỗi |
| Đường dẫn file, hostname, IP nội bộ | Tiết lộ hạ tầng và vị trí dữ liệu | Dùng thông báo chung, reference tra cứu nội bộ |
| Exception message thô | Không có cam kết an toàn hoặc ổn định | Ánh xạ theo loại lỗi; dùng mô tả được kiểm soát |

Ngay cả khi một giá trị không phải bí mật xác thực, việc ghép nó vào description hoặc log vẫn có thể tạo rủi ro riêng tư. Chỉ đưa ra ngoài thông tin client cần để xử lý.

## 3. Thiết kế response lỗi an toàn

Một response lỗi thường nên có:

1. **gRPC status code:** phân loại máy đọc được, ví dụ `NOT_FOUND`, `INVALID_ARGUMENT`, `UNAVAILABLE` hoặc `INTERNAL`.
2. **Description ngắn, đã kiểm soát:** giải thích đủ cho client nhưng không chứa chi tiết triển khai.
3. **Application error code tùy chọn:** mã ổn định như `CUSTOMER_NOT_FOUND` hoặc `VALIDATION_FAILED`.
4. **Support reference tùy chọn:** mã tra cứu để đội vận hành tìm log nội bộ, không chứa token hay PII.

Ví dụ:

```text
Status: INTERNAL
Description: Internal server error
Trailers:
  error-code: INTERNAL_FAILURE
  support-reference: 7f1a9c2e
```

Client có thể hiển thị thông báo chung và gửi support reference cho bộ phận hỗ trợ. Server dùng reference để tìm diagnostic chi tiết trong hệ thống log được bảo vệ.

Không dùng status code chung để che mọi loại lỗi. Nếu lỗi đã biết, hãy giữ status phù hợp với ngữ nghĩa API; nguyên tắc bảo mật chỉ yêu cầu **description và metadata không làm lộ chi tiết nhạy cảm**.

## 4. Ánh xạ exception mà không đưa message thô ra ngoài

Một mapper ở ranh giới gRPC có thể phân loại exception và chỉ tạo description từ các hằng số an toàn:

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class SafeGrpcErrorMapper {

    private static final Logger log =
            LoggerFactory.getLogger(SafeGrpcErrorMapper.class);

    public static final Metadata.Key<String> ERROR_CODE =
            Metadata.Key.of(
                    "error-code",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> SUPPORT_REFERENCE =
            Metadata.Key.of(
                    "support-reference",
                    Metadata.ASCII_STRING_MARSHALLER);

    public StatusRuntimeException map(Throwable error) {
        String reference = UUID.randomUUID().toString();
        Status status;
        String applicationCode;

        if (error instanceof CustomerNotFoundException) {
            status = Status.NOT_FOUND
                    .withDescription("Không tìm thấy tài nguyên");
            applicationCode = "CUSTOMER_NOT_FOUND";
        } else if (error instanceof RequestValidationException) {
            status = Status.INVALID_ARGUMENT
                    .withDescription("Dữ liệu yêu cầu không hợp lệ");
            applicationCode = "VALIDATION_FAILED";
        } else {
            status = Status.INTERNAL
                    .withDescription("Internal server error");
            applicationCode = "INTERNAL_FAILURE";

            // Không ghi exception message hoặc payload vào log thường.
            log.error("gRPC request failed: reference={}, exceptionType={}",
                    reference, error.getClass().getName());
            // Nếu cần stack trace, chuyển qua diagnostic sink riêng
            // có quyền truy cập, retention và redaction phù hợp.
        }

        Metadata trailers = new Metadata();
        trailers.put(ERROR_CODE, applicationCode);
        trailers.put(SUPPORT_REFERENCE, reference);
        return status.asRuntimeException(trailers);
    }
}
```

Ví dụ dùng `UUID` làm reference minh họa; hệ thống có thể dùng trace ID hoặc mã sự cố được tạo ở gateway. Reference phải không chứa thông tin khách hàng và không được dùng như credential. Nếu request đã có trace ID từ hạ tầng tin cậy, hãy xác thực/chuẩn hóa trước khi dùng để liên kết log.

Mapper không gọi `error.getMessage()`, không gắn `error` làm cause của status trả ra client và không serialize exception. Nếu cần chẩn đoán sâu, gửi exception tới nơi lưu diagnostic nội bộ đã được kiểm soát thay vì đưa vào gRPC metadata.

### Giữ nguyên status exception đã được tạo có chủ đích

Một tầng dưới có thể đã tạo `StatusRuntimeException` với status và trailers hợp lệ. Khi đó adapter có thể giữ status/trailers, nhưng vẫn phải xem xét liệu description và metadata có an toàn để công bố hay không. Không mặc định mọi exception từ thư viện hoặc downstream đều được phép chuyển tiếp nguyên trạng.

## 5. Dùng mapper ở Spring gRPC service

Ở unary RPC, adapter chỉ trả response thành công khi xử lý xong; nếu lỗi, gửi status đã được làm sạch:

```java
@GrpcService
public class CustomerGrpcService
        extends CustomerServiceGrpc.CustomerServiceImplBase {

    private final CustomerApplicationService applicationService;
    private final SafeGrpcErrorMapper errorMapper;

    public CustomerGrpcService(
            CustomerApplicationService applicationService,
            SafeGrpcErrorMapper errorMapper) {
        this.applicationService = applicationService;
        this.errorMapper = errorMapper;
    }

    @Override
    public void findCustomer(
            FindCustomerRequest request,
            StreamObserver<Customer> responseObserver) {
        try {
            Customer customer =
                    applicationService.find(request.getCustomerId());
            responseObserver.onNext(toProto(customer));
            responseObserver.onCompleted();
        } catch (Exception error) {
            responseObserver.onError(errorMapper.map(error));
        }
    }
}
```

Đoạn code minh họa ranh giới adapter. Trong triển khai thực tế, chỉ bắt các exception mà adapter có thể ánh xạ; không bắt `Throwable` để che lỗi JVM nghiêm trọng. Validation request, domain exception và lỗi hạ tầng nên được phân loại rõ trước khi fallback sang `INTERNAL`.

### Streaming RPC

Với client streaming hoặc server streaming, cùng nguyên tắc áp dụng cho từng terminal path:

- Nếu phát hiện lỗi khi nhận message, dừng xử lý và gọi `responseObserver.onError(safeError)` đúng một lần.
- Nếu inbound stream bị client hủy, dọn tài nguyên; không cố gửi error response mới trên call đã bị hủy.
- Nếu thành công, gửi response cuối rồi `onCompleted()`.
- Không gọi `onNext()` hoặc `onCompleted()` sau `onError()`.

Không ghi toàn bộ request stream vào log khi lỗi xảy ra ở message thứ 500. Thay vào đó, ghi batch ID đã được kiểm soát, sequence, số message đã nhận, status code và support reference. Nếu cần lưu payload để điều tra, phải có chính sách dữ liệu riêng, không tự động bật logging payload.

## 6. Log nội bộ cũng phải bảo vệ dữ liệu

“Không gửi stack trace cho client” không có nghĩa là log server có thể chứa mọi thứ. Log thường được chuyển tới nhiều hệ thống: collector, dashboard, kho lưu trữ, cảnh báo và nhà cung cấp quan sát. Mỗi nơi đều là một bề mặt truy cập dữ liệu.

### Ghi log có cấu trúc và tối thiểu

Một log lỗi vận hành thường chỉ cần:

- timestamp và severity;
- service/method gRPC;
- gRPC status code và application error code;
- support reference hoặc trace ID;
- exception class (nếu hữu ích);
- tenant/user identifier đã giảm thiểu hoặc pseudonym hóa khi cần;
- số lượng message/byte hoặc thời gian xử lý, không phải payload.

Ví dụ:

```java
log.warn(
        "gRPC operation rejected: method={}, status={}, errorCode={}, reference={}",
        "CustomerService/FindCustomer",
        "NOT_FOUND",
        "CUSTOMER_NOT_FOUND",
        supportReference);
```

Không nên:

```java
// Rủi ro: message có thể chứa SQL, token hoặc dữ liệu request.
log.error("Request failed: request={}, error={}", request, error.getMessage());
```

Nếu cần stack trace cho lỗi không mong đợi, ghi vào diagnostic sink riêng với quyền truy cập giới hạn, thời gian lưu phù hợp và quy trình redaction. Cần kiểm tra message/cause của exception vì thư viện có thể nhúng tham số truy vấn hoặc giá trị đầu vào vào đó. Không tự động gửi cùng log chi tiết tới mọi appender.

### Chống log injection

Không ghép nguyên văn giá trị do client kiểm soát vào log message. Chuỗi chứa newline hoặc ký tự điều khiển có thể giả mạo nhiều dòng log. Ưu tiên structured logging; giới hạn độ dài, chuẩn hóa hoặc loại bỏ ký tự điều khiển đối với trường văn bản tự do.

## 7. Description, trailers và TLS không thay thế nhau

| Thành phần | Có thể được client đọc? | Cách dùng an toàn |
| --- | --- | --- |
| Status description | Có | Chuỗi ngắn, chung, không chứa exception message thô |
| Custom trailers | Có | Mã lỗi/reference nhỏ, không chứa bí mật |
| Error details protobuf | Có | Chỉ chứa dữ liệu được phép công bố theo hợp đồng |
| Server logs | Không phải response RPC, nhưng có thể nhiều hệ thống nội bộ truy cập | Kiểm soát quyền, retention và redaction |
| Stack trace/cause nội bộ | Không tự truyền qua wire | Giữ trong diagnostic channel được bảo vệ |

TLS mã hóa đường truyền giữa các điểm kết nối, nhưng **không làm dữ liệu trong response trở nên bí mật đối với client nhận response**. Client được phép đọc status và trailers mà server gửi. Vì vậy, không thể dùng TLS làm lý do để trả stack trace hoặc token trong error metadata.

## 8. Kiểm thử để phát hiện rò rỉ thông tin

Test không chỉ kiểm tra status code. Nó cần khẳng định description và trailers không chứa secret, exception message hoặc stack trace.

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SafeGrpcErrorMapperTest {

    private final SafeGrpcErrorMapper mapper = new SafeGrpcErrorMapper();

    @Test
    void unexpectedFailureDoesNotExposeExceptionMessage() {
        String secret = "Bearer-super-secret-token";
        RuntimeException internal =
                new RuntimeException("SQL failed with token " + secret);

        StatusRuntimeException rpcError = mapper.map(internal);
        Status status = rpcError.getStatus();

        assertEquals(Status.Code.INTERNAL, status.getCode());
        assertEquals("Internal server error", status.getDescription());
        assertFalse(status.getDescription().contains(secret));

        Metadata trailers = Status.trailersFromThrowable(rpcError);
        assertNotNull(trailers);
        assertEquals("INTERNAL_FAILURE",
                trailers.get(SafeGrpcErrorMapper.ERROR_CODE));
        assertFalse(trailers.get(SafeGrpcErrorMapper.SUPPORT_REFERENCE)
                .contains(secret));
    }

    @Test
    void knownDomainErrorKeepsSafePublicMeaning() {
        StatusRuntimeException rpcError = mapper.map(
                new CustomerNotFoundException("customer-private-123"));

        assertEquals(Status.Code.NOT_FOUND,
                rpcError.getStatus().getCode());
        assertEquals("Không tìm thấy tài nguyên",
                rpcError.getStatus().getDescription());
        assertFalse(rpcError.getStatus().getDescription()
                .contains("customer-private-123"));
    }
}
```

Trong ví dụ, các key metadata được khai báo `public` hoặc package-private để test truy cập; điều chỉnh visibility theo cấu trúc dự án. Cần thêm integration test qua gRPC in-process để xác nhận client thực sự nhận status/trailers đã làm sạch.

### Ma trận kiểm thử bảo mật

| Ca | Assertion |
| --- | --- |
| Exception message chứa token | Description và trailers không chứa token |
| Exception message chứa SQL hoặc đường dẫn nội bộ | Không xuất hiện trong response RPC |
| Domain error có ID khách hàng | Description công khai không echo ID |
| Lỗi bất ngờ | Status `INTERNAL`, description chung, có support reference |
| Lỗi đã biết | Status code cụ thể, mô tả đã kiểm soát |
| Không có trailer | Client xử lý được giá trị thiếu |
| Streaming lỗi giữa luồng | Không có receipt thành công sau terminal error |
| Logging | Log thường không chứa request object, payload, credential hoặc PII thô |

Test log nên dùng appender test/capture để kiểm tra nội dung được ghi; không chỉ kiểm tra response. Diagnostic sink chứa stack trace cần được kiểm tra quyền truy cập và redaction theo chính sách vận hành.

## 9. Checklist trước khi phát hành API

- [ ] Status code phản ánh đúng loại lỗi, không dùng `INTERNAL` làm mặc định cho mọi exception.
- [ ] Description được tạo từ thông điệp đã kiểm soát, không lấy trực tiếp `getMessage()`.
- [ ] Không gửi stack trace, cause, SQL, đường dẫn nội bộ hoặc payload trong status/trailers.
- [ ] Error code và support reference không chứa credential hoặc PII.
- [ ] Client có fallback khi description/trailer thiếu hoặc có mã chưa biết.
- [ ] Log thường là structured, tối thiểu và đã loại bỏ dữ liệu nhạy cảm.
- [ ] Diagnostic stack trace chỉ ở nơi có quyền truy cập và retention phù hợp.
- [ ] Giá trị client kiểm soát được giới hạn/chuẩn hóa để tránh log injection.
- [ ] Test xác nhận response và log không làm lộ secret.
- [ ] TLS được cấu hình, nhưng không xem TLS là biện pháp thay thế data minimization.

## 10. Tự luyện tập

1. Một exception database có message chứa câu SQL và email khách hàng. Hãy thiết kế status description, trailer và log an toàn cho lỗi đó.
2. Vì sao không nên gọi `log.error("failure", exception)` vào mọi appender nếu exception message có thể chứa dữ liệu nhạy cảm?
3. Thiết kế support reference để client có thể cung cấp cho đội hỗ trợ nhưng không thể dùng reference đó để truy cập tài nguyên.
4. Viết integration test xác nhận một lỗi streaming không gửi receipt và không để lộ payload của message lỗi.
5. TLS đã bật trên channel. Vì sao server vẫn phải loại stack trace và token khỏi trailers?

**Ghi nhớ:** Error response là dữ liệu công khai với client. Hãy trả status code có ý nghĩa, description chung, error code và support reference an toàn; giữ stack trace/cause và chi tiết exception trong diagnostic nội bộ được bảo vệ. Không log hoặc gửi payload, credential, PII và dữ liệu hạ tầng một cách tùy tiện; kiểm thử cả response lẫn log để phát hiện rò rỉ.
