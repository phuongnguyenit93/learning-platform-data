# Trailers chứa thông tin lỗi

**Chương:** Error handling  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng Protocol Buffers, mã Java được sinh và các RPC unary hoặc streaming. Bài này tập trung vào **trailing metadata**: cách server đính kèm mã lỗi nghiệp vụ hoặc thông tin hỗ trợ xử lý vào response kết thúc lỗi, và cách client đọc các giá trị đó.

## 1. Trailers là gì?

Một gRPC response có thể có metadata đầu response (*headers*) và metadata cuối response (*trailers*). Trailers được gửi khi RPC kết thúc, cùng với trạng thái cuối của lời gọi. Khi server trả lỗi, trailers là nơi phù hợp để gửi thêm thông tin có cấu trúc nhỏ giúp client hiểu lỗi cụ thể hơn.

Ví dụ server trả status tổng quát `FAILED_PRECONDITION`, đồng thời gửi `error-code = ACCOUNT_SUSPENDED`. Client có thể dựa vào status code để phân loại lỗi chung và dựa vào `error-code` để chọn thông báo hoặc hành động nghiệp vụ tương ứng.

```text
gRPC response kết thúc
    |
    +-- gRPC status
    |     +-- code: FAILED_PRECONDITION
    |     +-- description: thông điệp giải thích tùy chọn
    |
    +-- trailing metadata
          +-- error-code: ACCOUNT_SUSPENDED
          +-- support-reference: req-8f31
```

Trailers khác với:

- **Protobuf response body:** dữ liệu nghiệp vụ của response thành công. Khi RPC kết thúc bằng lỗi, client thường không nhận response body thành công.
- **Initial metadata/headers:** metadata gửi ở đầu response, trước hoặc cùng lúc dữ liệu response. Trailers chỉ có ở cuối RPC.
- **Status description:** chuỗi giải thích nằm trong gRPC status; custom trailers là các cặp metadata riêng, có key và kiểu marshal.
- **Java cause/exception:** nguyên nhân nội bộ của server không tự được truyền thành object Java cho client.

Trailers hữu ích khi client cần một mã lỗi máy đọc được mà không muốn parse câu chữ description. Chúng không thay thế status code và không nên trở thành nơi truyền payload nghiệp vụ lớn.

## 2. Khai báo metadata key trong gRPC Java

gRPC Java dùng `io.grpc.Metadata` để biểu diễn headers và trailers. Mỗi key cần một marshaller xác định cách chuyển giá trị Java thành byte trên đường truyền và ngược lại.

### Giá trị dạng chuỗi ASCII

```java
import io.grpc.Metadata;

public final class ErrorTrailerKeys {
    private ErrorTrailerKeys() {}

    public static final Metadata.Key<String> ERROR_CODE =
            Metadata.Key.of(
                    "error-code",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> SUPPORT_REFERENCE =
            Metadata.Key.of(
                    "support-reference",
                    Metadata.ASCII_STRING_MARSHALLER);
}
```

Tên key metadata phải dùng chữ thường theo quy tắc gRPC. Không dùng tiền tố `grpc-` cho key do ứng dụng tự định nghĩa vì đây là vùng dành riêng cho giao thức. Key dạng text dùng `ASCII_STRING_MARSHALLER`; nếu cần truyền dữ liệu nhị phân, key phải có hậu tố `-bin` và dùng binary marshaller.

### Giá trị dạng byte

```java
public static final Metadata.Key<byte[]> ERROR_CONTEXT =
        Metadata.Key.of(
                "error-context-bin",
                Metadata.BINARY_BYTE_MARSHALLER);
```

Chỉ dùng binary trailer khi thật sự cần dữ liệu nhị phân nhỏ. Không tự tạo một định dạng byte không có version hoặc không có quy tắc giải mã; nếu dữ liệu lỗi có cấu trúc phức tạp, cân nhắc thông điệp lỗi protobuf chuẩn hóa ở mục 7.

## 3. Server Spring gRPC đính kèm trailers khi trả lỗi

Server tạo một `Metadata`, thêm các giá trị rồi truyền nó vào exception được tạo từ `Status`. Với callback gRPC, server kết thúc RPC bằng `responseObserver.onError(...)`.

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

private static final Metadata.Key<String> ERROR_CODE =
        Metadata.Key.of(
                "error-code",
                Metadata.ASCII_STRING_MARSHALLER);

private static final Metadata.Key<String> SUPPORT_REFERENCE =
        Metadata.Key.of(
                "support-reference",
                Metadata.ASCII_STRING_MARSHALLER);

void rejectSuspendedAccount(
        StreamObserver<TransferResponse> responseObserver,
        String requestReference) {

    Metadata trailers = new Metadata();
    trailers.put(ERROR_CODE, "ACCOUNT_SUSPENDED");
    trailers.put(SUPPORT_REFERENCE, requestReference);

    responseObserver.onError(
            Status.FAILED_PRECONDITION
                    .withDescription("Tài khoản chưa thể thực hiện giao dịch")
                    .asRuntimeException(trailers));
}
```

Ở đây:

- `FAILED_PRECONDITION` là status code chuẩn, dùng để phân loại trạng thái không cho phép thao tác.
- `withDescription(...)` cung cấp thông tin giải thích có thể đọc được; không nên đưa chi tiết nhạy cảm vào đây.
- `error-code` là mã nghiệp vụ ổn định để client xử lý.
- `support-reference` giúp liên kết yêu cầu với log/trace nội bộ, không phải token xác thực.

Sau `responseObserver.onError(...)`, response observer đã kết thúc. Không gọi thêm `onNext()` hoặc `onCompleted()` trên cùng observer.

### Dùng trong service implementation

```java
@GrpcService
public class TransferGrpcService
        extends TransferServiceGrpc.TransferServiceImplBase {

    private final TransferApplicationService service;

    public TransferGrpcService(TransferApplicationService service) {
        this.service = service;
    }

    @Override
    public void transfer(
            TransferRequest request,
            StreamObserver<TransferResponse> responseObserver) {
        try {
            TransferResponse response = service.transfer(request);
            responseObserver.onNext(response);
            responseObserver.onCompleted();
        } catch (AccountSuspendedException error) {
            Metadata trailers = new Metadata();
            trailers.put(ErrorTrailerKeys.ERROR_CODE, "ACCOUNT_SUSPENDED");
            trailers.put(ErrorTrailerKeys.SUPPORT_REFERENCE,
                    error.requestReference());

            responseObserver.onError(
                    Status.FAILED_PRECONDITION
                            .withDescription(
                                    "Tài khoản chưa thể thực hiện giao dịch")
                            .asRuntimeException(trailers));
        } catch (RuntimeException unexpected) {
            // Ghi chi tiết exception ở server, không gửi stack trace ra client.
            log.error("Unexpected transfer failure", unexpected);
            responseObserver.onError(
                    Status.INTERNAL
                            .withDescription("Internal server error")
                            .asRuntimeException());
        }
    }
}
```

Đoạn code minh họa vị trí ánh xạ lỗi nghiệp vụ. Trong ứng dụng thực, dùng logger và correlation ID nhất quán; tránh bắt mọi `RuntimeException` rồi vô tình che các lỗi nghiêm trọng mà ứng dụng không thể phục hồi. Có thể đặt việc ánh xạ status/trailers trong một helper hoặc exception mapper dùng chung.

## 4. Client đọc trailers từ lỗi RPC

Với blocking stub, client thường bắt `StatusRuntimeException`. Với async stub, callback `onError(Throwable)` nhận exception khi RPC kết thúc lỗi. Cả hai trường hợp đều có thể dùng `Status.trailersFromThrowable(...)`.

```java
import io.grpc.Metadata;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;

try {
    TransferResponse response = blockingStub.transfer(request);
    handleSuccess(response);
} catch (StatusRuntimeException error) {
    Status status = Status.fromThrowable(error);
    Metadata trailers = Status.trailersFromThrowable(error);

    String errorCode = trailers == null
            ? null
            : trailers.get(ErrorTrailerKeys.ERROR_CODE);

    String supportReference = trailers == null
            ? null
            : trailers.get(ErrorTrailerKeys.SUPPORT_REFERENCE);

    if (status.getCode() == Status.Code.FAILED_PRECONDITION
            && "ACCOUNT_SUSPENDED".equals(errorCode)) {
        showAccountSuspended();
    } else {
        showGenericRpcFailure(status.getCode(), supportReference);
    }
}
```

Luôn xử lý trường hợp `trailers == null` hoặc key không có giá trị. Không phải mọi lỗi đều do server chủ động tạo custom trailers: deadline, cancellation, lỗi kết nối hoặc proxy có thể khiến client không nhận được các key ứng dụng mong đợi.

### Trong callback async

```java
StreamObserver<TransferResponse> responseObserver = new StreamObserver<>() {
    @Override
    public void onNext(TransferResponse response) {
        handleSuccess(response);
    }

    @Override
    public void onError(Throwable error) {
        Status status = Status.fromThrowable(error);
        Metadata trailers = Status.trailersFromThrowable(error);
        String code = trailers == null
                ? null
                : trailers.get(ErrorTrailerKeys.ERROR_CODE);

        handleFailure(status.getCode(), code);
    }

    @Override
    public void onCompleted() {
        finishCall();
    }
};
```

Đừng parse `status.getDescription()` để tìm chuỗi `ACCOUNT_SUSPENDED`. Description dành cho người đọc; custom trailer có key riêng để client lấy trực tiếp. Cũng không giả định callback `onError` luôn nhận chính class exception server đã tạo: ranh giới RPC truyền status và metadata, không truyền object Java của server.

## 5. Trailers và status code có vai trò khác nhau

Status code phải đủ để client xử lý nhóm lỗi tổng quát ngay cả khi custom trailer vắng mặt. Trailer bổ sung chi tiết nghiệp vụ, không nên là điều kiện duy nhất để hiểu lỗi.

| Status code | Trailer `error-code` | Ý nghĩa và cách xử lý |
| --- | --- | --- |
| `INVALID_ARGUMENT` | `INVALID_ACCOUNT_ID` | Request sai; client sửa dữ liệu |
| `NOT_FOUND` | `CUSTOMER_NOT_FOUND` | Không tìm thấy tài nguyên |
| `FAILED_PRECONDITION` | `ACCOUNT_SUSPENDED` | Trạng thái nghiệp vụ không cho phép |
| `RESOURCE_EXHAUSTED` | `TENANT_QUOTA_EXCEEDED` | Vượt quota; chờ hoặc giảm tải theo chính sách |
| `UNAVAILABLE` | Có thể không có | Lỗi dịch vụ/transport tạm thời; chỉ retry nếu thao tác an toàn |
| `INTERNAL` | Thường không gửi chi tiết nội bộ | Lỗi server; dùng support reference nếu cần điều tra |

Nếu status là `FAILED_PRECONDITION` nhưng trailer không có, client vẫn phải xử lý được một lỗi điều kiện chung. Nếu trailer có mã không được client biết (do server triển khai phiên bản mới), client nên dùng nhánh fallback theo status code thay vì thất bại khi parse.

Không dùng trailer để thay status chuẩn. Ví dụ, đừng trả `UNKNOWN` rồi yêu cầu mọi client đọc `error-code` mới hiểu lỗi; hãy chọn status code phù hợp trước.

## 6. Quy ước thiết kế và versioning

Custom trailers là metadata dạng key/value, không có schema protobuf mạnh. Vì vậy, cần công bố quy ước:

- **Tên key ổn định:** ví dụ `error-code`, `support-reference`; dùng chữ thường và không dùng tiền tố dành riêng `grpc-`.
- **Giá trị ổn định:** mã như `ACCOUNT_SUSPENDED` không phụ thuộc ngôn ngữ hoặc câu chữ description.
- **Tương thích phiên bản:** client phải bỏ qua key không biết; server không được thay ý nghĩa một mã cũ mà không có kế hoạch versioning.
- **Giá trị tùy chọn:** client luôn có fallback khi trailer thiếu, bị loại bỏ hoặc không được gửi.
- **Kích thước nhỏ:** chỉ gửi mã, reference hoặc số liệu ngắn. Không đưa danh sách lỗi lớn, object nghiệp vụ hay payload file vào trailers.

Nếu cần cấu trúc phong phú, có nhiều trường lồng nhau hoặc danh sách chi tiết lỗi, hãy cân nhắc mô hình lỗi chuẩn `google.rpc.Status` với `google.rpc.ErrorInfo`, `BadRequest`, `RetryInfo` hoặc các detail protobuf phù hợp. Những detail này thường được đóng gói trong metadata nhị phân `grpc-status-details-bin` theo quy ước của gRPC ecosystem; cần dependency và hỗ trợ tương ứng ở client/server. Không tự dùng key dành riêng của giao thức để chứa định dạng riêng.

## 7. Bảo mật và giới hạn metadata

Trailers đi qua cùng đường truyền RPC và có thể được ghi lại bởi proxy, gateway hoặc instrumentation. Hãy coi chúng là dữ liệu có thể quan sát bởi client và hạ tầng trung gian.

- Không gửi password, access token, session cookie, khóa bí mật hoặc thông tin cá nhân không cần thiết.
- Không gửi SQL, stack trace, tên bảng, đường dẫn nội bộ hay chi tiết topology server.
- Dùng support reference ngẫu nhiên/khó đoán hoặc trace ID không mang thông tin nhạy cảm; phía server mới tra cứu chi tiết log.
- Giữ metadata nhỏ để tránh giới hạn header/trailer của gRPC, HTTP/2 và proxy.
- Không đưa payload lớn vào một giá trị ASCII; binary metadata cũng chịu giới hạn kích thước.
- Chỉ gửi trailer sau khi đã xác định status cuối; không coi trailers là kênh trao đổi message trong lúc stream đang chạy.

Nếu một lỗi có thể chứa dữ liệu nhạy cảm, chỉ gửi status code chung và reference hỗ trợ. Server lưu chi tiết có kiểm soát ở log nội bộ.

## 8. Kiểm thử server gửi và client đọc trailers

Kiểm thử đơn vị có thể xác nhận key và marshaller, nhưng cần kiểm thử RPC để xác nhận metadata thực sự đến client. Ví dụ dưới dùng gRPC in-process, JUnit 5 và một service tối giản:

```java
@GrpcService
class TrailerTestService extends TransferServiceGrpc.TransferServiceImplBase {
    @Override
    public void transfer(
            TransferRequest request,
            StreamObserver<TransferResponse> responseObserver) {
        Metadata trailers = new Metadata();
        trailers.put(ErrorTrailerKeys.ERROR_CODE, "ACCOUNT_SUSPENDED");
        trailers.put(ErrorTrailerKeys.SUPPORT_REFERENCE, "test-ref-17");

        responseObserver.onError(
                Status.FAILED_PRECONDITION
                        .withDescription("Operation is not allowed")
                        .asRuntimeException(trailers));
    }
}
```

Client test gọi stub và xác nhận status cùng custom metadata:

```java
@Test
void receivesCustomErrorTrailers() throws Exception {
    // server/channel in-process đã được khởi tạo trong @BeforeEach.
    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> TransferServiceGrpc.newBlockingStub(channel)
                    .transfer(TransferRequest.getDefaultInstance()));

    assertEquals(Status.Code.FAILED_PRECONDITION,
            Status.fromThrowable(error).getCode());

    Metadata trailers = Status.trailersFromThrowable(error);
    assertNotNull(trailers);
    assertEquals("ACCOUNT_SUSPENDED",
            trailers.get(ErrorTrailerKeys.ERROR_CODE));
    assertEquals("test-ref-17",
            trailers.get(ErrorTrailerKeys.SUPPORT_REFERENCE));
}
```

Test cần dependency `grpc-inprocess`, JUnit 5 và các lớp protobuf/gRPC đã sinh. Nếu kiểm thử service Spring thực, khởi tạo Spring context hoặc đăng ký service implementation vào in-process server theo cấu hình test.

Các ca cần bổ sung:

| Ca | Điều cần xác nhận |
| --- | --- |
| Server trả status không có custom trailers | Client không lỗi null; vẫn xử lý theo status code |
| Trailer có key không được client biết | Client bỏ qua key lạ |
| Status có description nhưng thiếu `error-code` | Client dùng fallback theo status |
| Trailer có binary key `-bin` | Client dùng đúng binary marshaller để đọc |
| RPC hết deadline hoặc bị cancel | Client chấp nhận trailers có thể không tồn tại |
| Trailer có support reference | Giá trị không chứa token hoặc dữ liệu bí mật |

## 9. Tự luyện tập

1. Tạo key `retry-after-ms` dạng ASCII và gửi kèm status `RESOURCE_EXHAUSTED`. Client nên xử lý giá trị thiếu hoặc sai định dạng thế nào?
2. Vì sao client nên kiểm tra status code trước rồi mới diễn giải custom trailer?
3. Thiết kế một mã lỗi nghiệp vụ tương thích khi server bổ sung mã mới mà client cũ chưa biết.
4. Khi cần gửi danh sách nhiều field lỗi validation, vì sao một trailer chuỗi tự định dạng không phải lựa chọn tốt?
5. Viết integration test xác nhận server gửi `FAILED_PRECONDITION`, description và hai custom trailers; đồng thời kiểm tra trường hợp server không gửi trailers.

**Ghi nhớ:** Trailers là **metadata cuối RPC**, phù hợp để gửi mã lỗi nghiệp vụ hoặc support reference nhỏ kèm status. Server tạo `Metadata` rồi truyền vào `Status.asRuntimeException(trailers)` cho `responseObserver.onError()`; client đọc bằng `Status.trailersFromThrowable()`, luôn xử lý trường hợp thiếu key và dùng status code làm nền tảng phân loại lỗi. Không đưa bí mật hoặc payload lớn vào trailers.
