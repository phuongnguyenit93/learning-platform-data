# Test INVALID_ARGUMENT từ request sai

Một gRPC service cần kiểm tra request ngay tại ranh giới API trước khi gọi repository hoặc downstream. Khi dữ liệu đầu vào vi phạm hợp đồng của method, server nên trả status **INVALID_ARGUMENT** với mô tả ổn định, đủ giúp caller sửa request. Bài này dùng CreatePayment trong Spring gRPC để minh họa cách validate request Protobuf và kiểm thử status bằng generated blocking stub.

INVALID_ARGUMENT biểu thị request không hợp lệ bất kể trạng thái hiện tại của hệ thống. Nó khác với lỗi điều kiện nghiệp vụ phụ thuộc trạng thái tài nguyên, ví dụ FAILED_PRECONDITION, và khác với lỗi xung đột cần caller thử lại transaction, ví dụ ABORTED. Kiểm thử cần xác minh cả status trả về lẫn việc server từ chối request trước khi tạo side effect.

## 1. Xác định hợp đồng request cần kiểm tra

Giả sử service nhận yêu cầu tạo thanh toán:

~~~proto
syntax = "proto3";

package acme.payment.v1;

option java_multiple_files = true;
option java_package = "com.acme.payment.v1";

service PaymentService {
  rpc CreatePayment(CreatePaymentRequest)
      returns (CreatePaymentResponse);
}

message CreatePaymentRequest {
  string customer_id = 1;
  int64 amount_minor = 2;
  string currency = 3;
}

message CreatePaymentResponse {
  string payment_id = 1;
}
~~~

Với proto3, field scalar không được gửi thường nhận giá trị mặc định. Ví dụ customer_id và currency có thể là chuỗi rỗng; amount_minor có thể là 0. Vì vậy, server cần kiểm tra các điều kiện nghiệp vụ đầu vào thay vì giả định field luôn có mặt.

| Field | Quy tắc ví dụ | Request sai |
| --- | --- | --- |
| customer_id | Không được rỗng hoặc chỉ có khoảng trắng | Chuỗi rỗng hoặc chỉ có khoảng trắng |
| amount_minor | Phải lớn hơn 0; đơn vị là đơn vị tiền nhỏ nhất | 0 hoặc số âm |
| currency | Phải thuộc danh sách currency service hỗ trợ | Rỗng hoặc mã không được hỗ trợ |

Các quy tắc này là hợp đồng API của ví dụ. Trong hệ thống thực tế, danh sách currency và giới hạn amount phải lấy từ chính sách nghiệp vụ có phiên bản rõ ràng.

## 2. Validate trước khi thực hiện side effect

Đặt validation ở service boundary giúp mọi caller gRPC nhận cùng cách xử lý, bất kể request đến từ ứng dụng Spring nào. Không gọi repository trước rồi mới phát hiện request sai.

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;
import java.util.Set;

public final class PaymentGrpcService
        extends PaymentServiceGrpc.PaymentServiceImplBase {

    private static final Set<String> SUPPORTED_CURRENCIES =
        Set.of("USD", "EUR");

    private final PaymentRepository repository;

    public PaymentGrpcService(PaymentRepository repository) {
        this.repository = repository;
    }

    @Override
    public void createPayment(
            CreatePaymentRequest request,
            StreamObserver<CreatePaymentResponse> responseObserver) {

        String invalidReason = validate(request);
        if (invalidReason != null) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription(invalidReason)
                    .asRuntimeException());
            return;
        }

        CreatePaymentResponse response = repository.create(request);
        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }

    private String validate(CreatePaymentRequest request) {
        if (request.getCustomerId().isBlank()) {
            return "customer_id must not be blank";
        }
        if (request.getAmountMinor() <= 0) {
            return "amount_minor must be greater than zero";
        }
        if (!SUPPORTED_CURRENCIES.contains(request.getCurrency())) {
            return "currency is not supported";
        }
        return null;
    }
}
~~~

PaymentRepository là abstraction của tầng lưu trữ, ví dụ:

~~~java
public interface PaymentRepository {
    CreatePaymentResponse create(CreatePaymentRequest request);
}
~~~

Khi validation thất bại, server gửi onError đúng một lần và kết thúc handler. Không gọi onNext hoặc onCompleted sau onError. Không đưa raw request, thông tin bí mật hoặc chi tiết database vào status description; nội dung mô tả nên ổn định và an toàn để caller hiển thị hoặc ghi log.

## 3. Chọn đúng gRPC status cho loại lỗi

Không dùng INVALID_ARGUMENT cho mọi trường hợp thất bại:

| Status | Dùng khi | Ví dụ |
| --- | --- | --- |
| INVALID_ARGUMENT | Giá trị request sai độc lập với trạng thái hệ thống | Amount âm, currency sai định dạng hoặc không được hỗ trợ |
| FAILED_PRECONDITION | Hệ thống chưa ở trạng thái cần thiết để thực hiện request | Tài khoản đang bị khóa, bước xác minh chưa hoàn tất |
| OUT_OF_RANGE | Giá trị hợp lệ về kiểu nhưng vượt miền cho phép theo hợp đồng | Trang yêu cầu vượt giới hạn tối đa đã công bố |
| NOT_FOUND | Tài nguyên được tham chiếu không tồn tại | Customer ID hợp lệ về định dạng nhưng không tìm thấy |
| ABORTED | Thao tác bị hủy do xung đột, caller có thể cần chạy lại transaction | Optimistic locking conflict |
| UNAVAILABLE | Service tạm thời không thể phục vụ | Downstream hoặc server tạm mất kết nối |

Ranh giới giữa INVALID_ARGUMENT và OUT_OF_RANGE phụ thuộc hợp đồng API. Điều quan trọng là giữ semantics nhất quán: caller không nên retry request không hợp lệ mà phải sửa dữ liệu trước.

## 4. Kiểm thử bằng in-process gRPC server

In-process transport cho phép chạy service thật trong JVM mà không mở TCP port. Nó phù hợp để kiểm tra logic validation, mapping status và việc không gọi repository khi request sai.

Ví dụ JUnit 5 dùng generated blocking stub:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PaymentGrpcServiceTest {

    private Server server;
    private ManagedChannel channel;
    private PaymentServiceGrpc.PaymentServiceBlockingStub stub;
    private AtomicInteger repositoryCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        repositoryCalls = new AtomicInteger();

        PaymentRepository repository = request -> {
            repositoryCalls.incrementAndGet();
            return CreatePaymentResponse.newBuilder()
                .setPaymentId("payment-123")
                .build();
        };

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(new PaymentGrpcService(repository))
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = PaymentServiceGrpc.newBlockingStub(channel)
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
    void blankCustomerIdReturnsInvalidArgument() {
        CreatePaymentRequest request = validRequest()
            .setCustomerId("   ")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.createPayment(request));

        assertEquals(
            Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());
        assertEquals(
            "customer_id must not be blank",
            error.getStatus().getDescription());
        assertEquals(0, repositoryCalls.get());
    }

    @Test
    void nonPositiveAmountReturnsInvalidArgument() {
        CreatePaymentRequest request = validRequest()
            .setAmountMinor(0)
            .build();

        assertInvalidArgument(request);
        assertEquals(0, repositoryCalls.get());
    }

    @Test
    void unsupportedCurrencyReturnsInvalidArgument() {
        CreatePaymentRequest request = validRequest()
            .setCurrency("XYZ")
            .build();

        assertInvalidArgument(request);
        assertEquals(0, repositoryCalls.get());
    }

    @Test
    void validRequestCallsRepositoryAndReturnsResponse() {
        CreatePaymentResponse response =
            stub.createPayment(validRequest().build());

        assertEquals("payment-123", response.getPaymentId());
        assertEquals(1, repositoryCalls.get());
    }

    private void assertInvalidArgument(CreatePaymentRequest request) {
        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.createPayment(request));

        assertEquals(
            Status.Code.INVALID_ARGUMENT,
            error.getStatus().getCode());
        assertNotNull(error.getStatus().getDescription());
    }

    private CreatePaymentRequest.Builder validRequest() {
        return CreatePaymentRequest.newBuilder()
            .setCustomerId("customer-42")
            .setAmountMinor(2500)
            .setCurrency("USD");
    }
}
~~~

Test dùng directExecutor() vì handler validation ngắn và không blocking. Nếu service gọi I/O hoặc chờ latch, hãy dùng executor phù hợp để không chặn thread test hoặc luồng dispatch. grpc-inprocess phải cùng phiên bản với các artifact gRPC Java còn lại.

## 5. Kiểm tra status, description và side effect

Một test tốt nên xác minh ba điều:

1. **Status code:** client nhận đúng INVALID_ARGUMENT.
2. **Public description:** thông điệp đủ rõ để sửa request, không tiết lộ nội bộ.
3. **Không có side effect:** repository, payment gateway hoặc downstream không được gọi.

Chỉ kiểm tra exception được ném ra chưa đủ. Nếu service đã ghi dữ liệu rồi mới trả lỗi, API có thể để lại trạng thái không nhất quán. Bộ đếm hoặc mock verify giúp chứng minh validation xảy ra trước thao tác nghiệp vụ.

Với blocking stub, lỗi được ném dưới dạng StatusRuntimeException. Với async stub, lỗi đi qua StreamObserver.onError; có thể lấy status bằng Status.fromThrowable(error). Cả hai trường hợp đều nên assert Status.Code.INVALID_ARGUMENT, không chỉ so sánh chuỗi message.

## 6. Kiểm thử biên và dữ liệu mặc định của Protobuf

Ngoài một request sai điển hình, hãy kiểm tra các giá trị sát biên:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| customer_id không được set | INVALID_ARGUMENT vì giá trị proto3 là chuỗi rỗng |
| customer_id chỉ có khoảng trắng | INVALID_ARGUMENT |
| amount_minor = 0 | INVALID_ARGUMENT |
| amount_minor < 0 | INVALID_ARGUMENT |
| amount_minor = 1 | Hợp lệ nếu chính sách cho phép |
| currency rỗng hoặc không hỗ trợ | INVALID_ARGUMENT |
| Tất cả field hợp lệ | Repository được gọi đúng một lần |

Nếu schema dùng optional, wrapper hoặc oneof để phân biệt không gửi với gửi giá trị mặc định, test phải kiểm tra cả presence semantics. Đừng chỉ kiểm tra getter vì getter của scalar proto3 có thể trả giá trị mặc định cho cả trường hợp vắng mặt.

## 7. Không retry request INVALID_ARGUMENT

INVALID_ARGUMENT là lỗi từ request; gửi lại cùng payload không làm lỗi tự biến mất. Client nên hiển thị hoặc trả lỗi validation về caller, cho phép sửa input rồi tạo request mới.

Retry policy tự động không nên liệt kê INVALID_ARGUMENT trong retryableStatusCodes. Nếu có lớp retry chung ở ứng dụng, hãy loại status này khỏi danh sách retry. Retry không kiểm soát chỉ làm tăng tải và che khuất lỗi dữ liệu từ client.

Phân biệt lỗi này với UNAVAILABLE, vốn có thể retry theo policy nếu thao tác an toàn và deadline còn đủ. Với command có side effect, retry các lỗi không rõ kết quả vẫn cần idempotency key.

## 8. Kiểm thử qua Spring application context

In-process test xác minh service implementation và status mapping, nhưng không chứng minh Spring starter đã đăng ký đúng service, interceptor hoặc server configuration. Nên có thêm integration test khởi động application context và gọi endpoint gRPC qua transport thật hoặc cổng test:

- Xác minh PaymentGrpcService được đăng ký đúng service name.
- Xác minh interceptor không biến lỗi validation thành status khác.
- Xác minh metadata/trailers được giữ đúng.
- Xác minh TLS hoặc proxy nếu production dùng các lớp này.
- Xác minh request sai không chạm repository bean thật.

Trong Spring Boot, có thể dùng SpringBootTest cùng cấu hình server test của starter đang dùng. Tên property chọn port hoặc cách lấy channel phụ thuộc starter/version; dùng đúng integration point của dự án thay vì giả định một property chung cho mọi thư viện Spring gRPC.

## 9. Bảo mật thông tin lỗi

Status description là dữ liệu gửi về client và có thể được ghi log ở nhiều tầng. Không đưa vào description:

- SQL statement, tên bảng hoặc connection string.
- Stack trace hay tên class nội bộ.
- Token, secret, dữ liệu thanh toán hoặc dữ liệu cá nhân.
- Nội dung request đầy đủ khi có thể chứa thông tin nhạy cảm.

Có thể dùng thông điệp ổn định như amount_minor must be greater than zero, đồng thời ghi log nội bộ với request ID và mã lỗi đã chuẩn hóa. Nếu API cần nhiều lỗi field trong một lần trả về, cân nhắc google.rpc.BadRequest trong rich error model và bảo đảm client/proxy hỗ trợ trailers tương ứng.

## 10. Ma trận kiểm thử đề xuất

| Nhóm | Input/kịch bản | Assertion |
| --- | --- | --- |
| Required field | customer_id rỗng | INVALID_ARGUMENT; repository không gọi |
| Whitespace | ID chỉ có khoảng trắng | INVALID_ARGUMENT |
| Numeric boundary | Amount bằng 0 hoặc âm | INVALID_ARGUMENT |
| Enum/domain | Currency không hỗ trợ | INVALID_ARGUMENT |
| Valid boundary | Amount nhỏ nhất hợp lệ | Thành công theo hợp đồng |
| Side effect | Request sai | Không ghi dữ liệu, không gọi downstream |
| Error mapping | Blocking/async client | Đều quan sát đúng status code |
| Spring wiring | Application context thật | Service/interceptor được đăng ký đúng |
| Security | Request sai chứa dữ liệu nhạy cảm | Description không làm lộ dữ liệu |

Giữ test độc lập và dùng fixture/fake repository. Không phụ thuộc database thật để kiểm tra một quy tắc validation thuần túy.

## 11. Ghi nhớ và tự kiểm tra

**Test INVALID_ARGUMENT từ request sai** cần xác minh validation ở service boundary, status gRPC chính xác và không có side effect. Dùng generated request builder để tạo dữ liệu sai, in-process server để kiểm tra nhanh logic service, rồi bổ sung Spring integration test để xác minh wiring thực tế. INVALID_ARGUMENT yêu cầu caller sửa payload; không retry cùng request.

Tự kiểm tra:

1. Vì sao field string không được set trong proto3 thường phải được kiểm tra như chuỗi rỗng?
2. Khi nào dùng INVALID_ARGUMENT thay vì FAILED_PRECONDITION?
3. Vì sao test cần xác minh repository không được gọi khi request sai?
4. Blocking stub và async stub biểu diễn lỗi INVALID_ARGUMENT khác nhau thế nào?
5. Vì sao status này không nên nằm trong retry policy?
6. In-process test không xác minh được những phần nào của Spring gRPC deployment?

Kiểm thử validation đúng giúp Spring gRPC từ chối request sai một cách nhất quán, giữ dữ liệu không bị ghi dở và cung cấp phản hồi đủ rõ để caller sửa input.
