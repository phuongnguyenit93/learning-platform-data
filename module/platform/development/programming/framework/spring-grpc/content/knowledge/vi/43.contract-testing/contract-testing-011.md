# Contract của error detail

gRPC truyền lỗi bằng status code và message trong response trailers. Khi API cần mô tả lỗi có cấu trúc để client xử lý chính xác, có thể dùng **rich error model** của Google: message `google.rpc.Status` chứa code, message và danh sách detail kiểu `google.protobuf.Any`. Trong Java, `StatusProto` của grpc-java chuyển đổi giữa rich status và `StatusRuntimeException`.

Contract của error detail quy định client có thể dựa vào loại detail nào, field nào bắt buộc, ý nghĩa của từng giá trị và cách xử lý khi gặp detail chưa biết. Contract tốt giúp client hiển thị lỗi validation, quyết định retry, hỗ trợ người vận hành và tương thích khi server bổ sung loại detail mới.

## 1. Cấu trúc rich error

Một rich error gồm:

- **gRPC status code:** mã ổn định để mọi client có thể xử lý ở mức tổng quát, ví dụ `INVALID_ARGUMENT`, `NOT_FOUND` hoặc `RESOURCE_EXHAUSTED`.
- **Message:** mô tả ngắn cho người đọc hoặc log; không nên là dữ liệu để client parse logic.
- **Details:** danh sách `Any` chứa các message Protobuf có kiểu, ví dụ `google.rpc.BadRequest` hoặc `google.rpc.ErrorInfo`.

Trên wire, rich status được gửi trong trailer metadata nhị phân `grpc-status-details-bin`. Status code và message cơ bản của gRPC vẫn hiện diện; rich status bổ sung thông tin có cấu trúc. Proxy hoặc gateway cần giữ trailer này nếu muốn client nhận được detail.

Ví dụ một lỗi validation:

~~~text
google.rpc.Status
  code: INVALID_ARGUMENT
  message: "request validation failed"
  details:
    - google.rpc.BadRequest
        field_violations:
          - field: "email"
            description: "must be a valid email address"
~~~

Client có thể dựa vào type của detail và field path để hiển thị lỗi cạnh trường tương ứng, thay vì phân tích chuỗi message.

## 2. Chọn detail type theo ý nghĩa

Google cung cấp các detail type phổ biến trong package `google.rpc`:

| Detail type | Mục đích | Ví dụ sử dụng |
| --- | --- | --- |
| `BadRequest` | Liệt kê field vi phạm validation | Field bắt buộc thiếu hoặc sai định dạng |
| `ErrorInfo` | Mã lỗi ổn định và metadata phân loại | `reason`, `domain`, thông tin không nhạy cảm |
| `RetryInfo` | Gợi ý thời gian chờ trước khi retry | Rate limit hoặc dependency tạm quá tải |
| `ResourceInfo` | Mô tả resource liên quan tới lỗi | Resource type, name và owner |
| `PreconditionFailure` | Liệt kê điều kiện tiên quyết không đạt | Version/state không còn phù hợp |
| `QuotaFailure` | Liệt kê quota violation | Tenant vượt storage quota |

Chọn detail theo semantics, không tạo một message tổng quát chứa mọi trường hợp. Status code vẫn là tín hiệu cấp cao; detail giải thích nguyên nhân và hành động phù hợp. Ví dụ validation thường dùng `INVALID_ARGUMENT` cùng `BadRequest`; quota có thể dùng `RESOURCE_EXHAUSTED` cùng `QuotaFailure`.

## 3. Thêm thư viện Java

Ứng dụng Java cần grpc protobuf integration và các định nghĩa message của Google common protos. Ví dụ Maven dependency; phiên bản phải được quản lý đồng bộ với BOM hoặc dependency management của dự án:

~~~xml
<dependency>
  <groupId>io.grpc</groupId>
  <artifactId>grpc-protobuf</artifactId>
</dependency>
<dependency>
  <groupId>com.google.api.grpc</groupId>
  <artifactId>proto-google-common-protos</artifactId>
</dependency>
~~~

`StatusProto` nằm trong grpc protobuf integration; các class như `com.google.rpc.Status`, `BadRequest` và `ErrorInfo` được sinh từ Google common protos. Tránh khai báo các bản Protobuf runtime không tương thích trong cùng dependency graph.

## 4. Server tạo error detail có cấu trúc

Ví dụ service kiểm tra request và trả `BadRequest` khi email sai:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.BadRequest;
import io.grpc.Status;
import io.grpc.protobuf.StatusProto;
import io.grpc.stub.StreamObserver;

public final class RegistrationGrpcService
        extends RegistrationServiceGrpc.RegistrationServiceImplBase {

    @Override
    public void register(
            RegisterRequest request,
            StreamObserver<RegisterResponse> observer) {

        if (!request.getEmail().contains("@")) {
            BadRequest detail = BadRequest.newBuilder()
                .addFieldViolations(
                    BadRequest.FieldViolation.newBuilder()
                        .setField("email")
                        .setDescription("must be a valid email address")
                        .build())
                .build();

            com.google.rpc.Status richStatus =
                com.google.rpc.Status.newBuilder()
                    .setCode(Status.Code.INVALID_ARGUMENT.value())
                    .setMessage("request validation failed")
                    .addDetails(Any.pack(detail))
                    .build();

            observer.onError(
                StatusProto.toStatusRuntimeException(richStatus));
            return;
        }

        observer.onNext(RegisterResponse.newBuilder()
            .setRegistrationId("reg-123")
            .build());
        observer.onCompleted();
    }
}
~~~

Server nên tạo detail từ validation result hoặc domain error đã chuẩn hóa. Không đưa stack trace, SQL, token, secret, nội dung credential hoặc dữ liệu cá nhân không cần thiết vào message/detail. Message nên ổn định vừa đủ để hỗ trợ chẩn đoán; client không được dựa vào message để quyết định logic.

## 5. Client đọc detail và vẫn giữ fallback status

Client kiểm tra status code trước, sau đó unpack detail type mà nó hiểu:

~~~java
import com.google.rpc.BadRequest;
import com.google.rpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.protobuf.StatusProto;

try {
    RegisterResponse response = stub.register(request);
    // Xử lý response thành công.
} catch (StatusRuntimeException error) {
    Status richStatus = StatusProto.fromThrowable(error);

    if (error.getStatus().getCode()
            == io.grpc.Status.Code.INVALID_ARGUMENT
            && richStatus != null) {
        for (com.google.protobuf.Any detail : richStatus.getDetailsList()) {
            if (detail.is(BadRequest.class)) {
                BadRequest badRequest = detail.unpack(BadRequest.class);
                badRequest.getFieldViolationsList().forEach(violation ->
                    showFieldError(
                        violation.getField(),
                        violation.getDescription()));
            }
        }
    } else {
        handleGrpcStatus(error.getStatus().getCode());
    }
}
~~~

`StatusProto.fromThrowable` có thể không tìm thấy rich status trong throwable, ví dụ server/proxy chỉ gửi status cơ bản. Vì vậy client luôn phải có nhánh fallback dựa trên gRPC status code. Nếu không nhận được detail hoặc gặp detail không hỗ trợ, client vẫn xử lý được lỗi tổng quát thay vì crash.

Khi unpack, kiểm tra type bằng `Any.is(Class)` trước `unpack(Class)`. Không giả định detail đầu tiên luôn là loại mình cần; danh sách có thể chứa nhiều detail và thứ tự không nên mang ý nghĩa ưu tiên nếu contract không quy định.

## 6. Contract test cho status code và detail

Contract test phải xác minh cả hai tầng:

1. **Status semantics:** code gRPC đúng với loại lỗi.
2. **Detail schema:** có đúng type detail và field contract cần thiết.

Test in-process dưới đây gọi generated blocking stub và xác minh `INVALID_ARGUMENT` cùng `BadRequest`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import com.google.rpc.BadRequest;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.protobuf.StatusProto;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class RegistrationErrorContractTest {

    private Server server;
    private ManagedChannel channel;
    private RegistrationServiceGrpc.RegistrationServiceBlockingStub stub;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new RegistrationGrpcService())
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = RegistrationServiceGrpc.newBlockingStub(channel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);
    }

    @AfterEach
    void tearDown() throws InterruptedException {
        if (channel != null) {
            channel.shutdownNow();
            assertTrue(channel.awaitTermination(5, TimeUnit.SECONDS));
        }
        if (server != null) {
            server.shutdownNow();
            assertTrue(server.awaitTermination(5, TimeUnit.SECONDS));
        }
    }

    @Test
    void invalidEmailReturnsInvalidArgumentWithBadRequestDetail() {
        RegisterRequest request = RegisterRequest.newBuilder()
            .setEmail("not-an-email")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.register(request));

        assertEquals(
            Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());

        com.google.rpc.Status richStatus =
            StatusProto.fromThrowable(error);
        assertNotNull(richStatus);
        assertEquals(
            Status.Code.INVALID_ARGUMENT.value(),
            richStatus.getCode());

        BadRequest detail = richStatus.getDetailsList().stream()
            .filter(any -> any.is(BadRequest.class))
            .map(any -> {
                try {
                    return any.unpack(BadRequest.class);
                } catch (com.google.protobuf.InvalidProtocolBufferException ex) {
                    throw new AssertionError(ex);
                }
            })
            .findFirst()
            .orElseThrow();

        assertEquals(1, detail.getFieldViolationsCount());
        assertEquals("email", detail.getFieldViolations(0).getField());
        assertEquals(
            "must be a valid email address",
            detail.getFieldViolations(0).getDescription());
    }
}
~~~

In-process transport kiểm tra service, generated stub và rich status trong cùng JVM. Bổ sung integration test qua transport/proxy thật nếu gateway, ingress hoặc load balancer có thể lọc trailer metadata. Contract phải được kiểm tra ở đúng đường đi mà client production sử dụng.

## 7. Tương thích khi thêm hoặc gặp detail type mới

`Any` mang type URL và payload Protobuf. Client cũ có thể gặp detail type được server mới thêm mà client chưa có class hoặc chưa biết cách diễn giải. Thiết kế tương thích cần tuân thủ:

- Client bỏ qua detail type chưa biết và tiếp tục dựa trên status code cơ bản.
- Server giữ status code và message fallback có ý nghĩa ngay cả khi client không đọc được detail.
- Thêm detail mới theo hướng additive; không đổi ý nghĩa của detail type đang tồn tại.
- Không đổi field number hoặc tái sử dụng field number trong message detail Protobuf.
- Nếu đổi semantics, tạo reason/version mới hoặc detail type mới thay vì âm thầm đổi hợp đồng cũ.
- Client không phụ thuộc vào thứ tự detail trừ khi contract nêu rõ.

Một server có thể gửi nhiều detail trong cùng rich status, ví dụ `ErrorInfo` để phân loại lỗi và `BadRequest` để chỉ ra field vi phạm. Client chỉ xử lý những type mà nó hiểu.

## 8. Dùng ErrorInfo cho mã lỗi ổn định

`ErrorInfo` cung cấp `reason`, `domain` và metadata. Ví dụ:

~~~java
import com.google.protobuf.Any;
import com.google.rpc.ErrorInfo;
import io.grpc.Status;
import io.grpc.protobuf.StatusProto;

ErrorInfo errorInfo = ErrorInfo.newBuilder()
    .setReason("EMAIL_ALREADY_REGISTERED")
    .setDomain("registration.acme.example")
    .putMetadata("field", "email")
    .build();

com.google.rpc.Status richStatus = com.google.rpc.Status.newBuilder()
    .setCode(Status.Code.ALREADY_EXISTS.value())
    .setMessage("registration already exists")
    .addDetails(Any.pack(errorInfo))
    .build();
~~~

Client có thể xử lý reason ổn định mà không parse message. Domain giúp phân biệt namespace lỗi. Metadata chỉ nên chứa giá trị không nhạy cảm và được contract công bố; không nhét token, email đầy đủ hoặc dữ liệu riêng tư vào đó nếu client không cần.

Không tạo reason tùy tiện từ exception class hoặc message. Dùng danh sách reason có kiểm soát, tài liệu hóa status code tương ứng và hành động client được phép thực hiện.

## 9. RetryInfo và contract retry

Với lỗi có thể retry sau một khoảng chờ, server có thể đính kèm `google.rpc.RetryInfo`. Client cần kết hợp retry delay với deadline tổng, giới hạn số attempt và idempotency:

~~~java
import com.google.protobuf.Any;
import com.google.protobuf.Duration;
import com.google.rpc.RetryInfo;

RetryInfo retryInfo = RetryInfo.newBuilder()
    .setRetryDelay(Duration.newBuilder()
        .setSeconds(2)
        .build())
    .build();

com.google.rpc.Status richStatus = com.google.rpc.Status.newBuilder()
    .setCode(io.grpc.Status.Code.RESOURCE_EXHAUSTED.value())
    .setMessage("request rate limit exceeded")
    .addDetails(Any.pack(retryInfo))
    .build();
~~~

Detail chỉ là gợi ý theo contract; client vẫn phải kiểm tra status có retryable không và operation có an toàn để lặp không. Không retry `INVALID_ARGUMENT`, `UNAUTHENTICATED` hoặc `PERMISSION_DENIED` chỉ vì có detail. Với command có side effect, giữ nguyên idempotency key qua các attempt.

## 10. Giới hạn kích thước và bảo mật error detail

Rich detail đi trong trailers nên cũng tiêu thụ giới hạn metadata/trailer của HTTP/2, proxy và client. Không gửi stack trace, toàn bộ object request, danh sách lỗi không giới hạn hoặc nội dung file trong detail.

Nguyên tắc:

- Chỉ gửi field cần để client sửa request hoặc chọn hành động.
- Giới hạn số field violation và độ dài message/metadata.
- Không đưa secret, access token, internal hostname, SQL hay stack trace vào detail.
- Không dùng detail để lộ resource hoặc tenant mà caller không được biết.
- Đảm bảo gateway/proxy giữ `grpc-status-details-bin`; nếu bị loại bỏ, status code cơ bản vẫn phải đủ để fallback.
- Ghi log chi tiết nội bộ ở server với correlation ID, nhưng không trả nguyên log cho client.

## 11. Ma trận contract test đề xuất

| Trường hợp | Assertion |
| --- | --- |
| Validation sai | `INVALID_ARGUMENT` + `BadRequest` có field violation |
| Resource đã tồn tại | `ALREADY_EXISTS` + `ErrorInfo` reason ổn định |
| Quota vượt | `RESOURCE_EXHAUSTED` + `QuotaFailure` hoặc `RetryInfo` theo contract |
| Dependency không sẵn sàng | `UNAVAILABLE`; detail nếu có không thay semantics |
| Client không hiểu detail type | Bỏ qua detail lạ, vẫn xử lý status code |
| Proxy bỏ rich trailer | Client fallback bằng status code/message cơ bản |
| Detail chứa dữ liệu nhạy cảm | Test không chấp nhận field/metadata bị cấm |
| Thêm detail mới | Client cũ vẫn xử lý lỗi tổng quát |

Contract test nên xác minh type URL/type class, field bắt buộc và ý nghĩa code; tránh chỉ so sánh toàn bộ chuỗi message vì message thường được chỉnh sửa để dễ đọc.

## 12. Ghi nhớ và tự kiểm tra

**Contract của error detail** định nghĩa cách server diễn tả lỗi có cấu trúc bằng `google.rpc.Status` và `Any`, trong khi gRPC status code vẫn là fallback ổn định. Với Java, server tạo rich status qua `StatusProto.toStatusRuntimeException`, client đọc bằng `StatusProto.fromThrowable` và chỉ unpack detail type mà nó hiểu. Contract test cần kiểm tra status semantics, detail schema, khả năng bỏ qua type mới, trailer qua proxy và giới hạn dữ liệu nhạy cảm/kích thước.

Tự kiểm tra:

1. Rich error detail khác status code/message cơ bản ở điểm nào?
2. Vì sao client phải kiểm tra `Any` type trước khi unpack?
3. Nếu client cũ gặp detail type mới, hành vi tương thích nên là gì?
4. Vì sao message không nên được dùng làm khóa logic?
5. `RetryInfo` có tự động cho phép retry mọi RPC không?
6. Cần kiểm tra điều gì nếu proxy làm mất rich error trailer?

Contract error detail rõ ràng giúp client Spring gRPC xử lý lỗi nhất quán, cung cấp hướng sửa/retry có kiểm soát và duy trì tương thích khi server phát triển API.
