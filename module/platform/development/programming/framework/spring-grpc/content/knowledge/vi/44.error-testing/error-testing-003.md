# Test PERMISSION_DENIED

Trong gRPC, **PERMISSION_DENIED** biểu thị caller đã được xác thực nhưng không có quyền thực hiện hành động được yêu cầu. Với Spring gRPC, kiểm thử status này cần chứng minh policy authorization thực sự từ chối principal, service trả đúng status và thao tác nghiệp vụ không chạy sau khi bị từ chối.

Phải phân biệt PERMISSION_DENIED với UNAUTHENTICATED: trường hợp thứ nhất đã biết caller là ai nhưng caller không đủ quyền; trường hợp thứ hai chưa xác minh được danh tính hoặc credential không hợp lệ. Bài này dùng RPC GetPayroll để kiểm thử một principal hợp lệ nhưng thiếu quyền đọc bảng lương.

## 1. Xác định ranh giới authentication và authorization

Luồng bảo mật thường có hai bước:

1. **Authentication:** xác minh token, certificate hoặc credential; tạo principal đáng tin cậy.
2. **Authorization:** kiểm tra principal có quyền thực hiện hành động trên resource cụ thể hay không.

Ví dụ:

| Tình huống | Status |
| --- | --- |
| Không có credential hoặc token sai/hết hạn | UNAUTHENTICATED |
| Token hợp lệ nhưng thiếu quyền PAYROLL_READ | PERMISSION_DENIED |
| Caller có quyền nhưng employee ID không tồn tại | NOT_FOUND |
| Employee ID sai định dạng | INVALID_ARGUMENT |
| Payroll database tạm thời không khả dụng | UNAVAILABLE |

Không dùng PERMISSION_DENIED để biểu diễn mọi lỗi bảo mật. Nếu authentication chưa thành công, server chưa có principal đáng tin cậy để đánh giá quyền.

## 2. Hợp đồng RPC và principal đã xác thực

Ví dụ Protobuf:

~~~proto
syntax = "proto3";

package acme.payroll.v1;

option java_multiple_files = true;
option java_package = "com.acme.payroll.v1";

service PayrollService {
  rpc GetPayroll(GetPayrollRequest) returns (GetPayrollResponse);
}

message GetPayrollRequest {
  string employee_id = 1;
}

message GetPayrollResponse {
  string employee_id = 1;
  int64 gross_amount_minor = 2;
  string currency = 3;
}
~~~

Principal cần được tạo từ thông tin đã xác minh ở authentication layer. Ví dụ model nội bộ:

~~~java
import java.util.Set;

public record AuthenticatedPrincipal(
    String subject,
    String tenantId,
    Set<String> authorities) {}
~~~

Đưa principal vào gRPC Context bằng key dùng chung:

~~~java
public final class AuthenticatedPrincipalContext {
    public static final Context.Key<AuthenticatedPrincipal> PRINCIPAL =
        Context.key("authenticated-principal");

    private AuthenticatedPrincipalContext() {}
}
~~~

Authentication interceptor của ứng dụng phải xác minh credential trước, rồi mới gắn principal vào context:

~~~java
AuthenticatedPrincipal principal =
    verifiedIdentityResolver.authenticate(headers);

Context context = Context.current().withValue(
    AuthenticatedPrincipalContext.PRINCIPAL,
    principal);

return Contexts.interceptCall(context, call, headers, next);
~~~

Đoạn trích trên nằm sau bước xác minh token/certificate; không lấy subject, tenant hoặc role từ metadata do client tự khai rồi coi đó là danh tính đã xác thực. Nếu authentication thất bại, interceptor trả UNAUTHENTICATED và không gọi service handler.

## 3. Kiểm tra quyền trước khi truy cập dữ liệu

Tách policy khỏi service implementation giúp kiểm thử authorization độc lập và giữ logic quyền nhất quán:

~~~java
public interface PayrollAuthorization {
    boolean canReadPayroll(
        AuthenticatedPrincipal principal,
        String employeeId);
}

public interface PayrollRepository {
    Optional<PayrollRecord> findByEmployeeIdAndTenantId(
        String employeeId,
        String tenantId);
}
~~~

Service kiểm tra principal, quyền rồi mới đọc dữ liệu:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class PayrollGrpcService
        extends PayrollServiceGrpc.PayrollServiceImplBase {

    private final PayrollAuthorization authorization;
    private final PayrollRepository repository;

    public PayrollGrpcService(
            PayrollAuthorization authorization,
            PayrollRepository repository) {
        this.authorization = authorization;
        this.repository = repository;
    }

    @Override
    public void getPayroll(
            GetPayrollRequest request,
            StreamObserver<GetPayrollResponse> responseObserver) {

        String employeeId = request.getEmployeeId();
        if (employeeId.isBlank()) {
            responseObserver.onError(
                Status.INVALID_ARGUMENT
                    .withDescription("employee_id must not be blank")
                    .asRuntimeException());
            return;
        }

        AuthenticatedPrincipal principal =
            AuthenticatedPrincipalContext.PRINCIPAL.get();
        if (principal == null) {
            responseObserver.onError(
                Status.UNAUTHENTICATED
                    .withDescription("authentication is required")
                    .asRuntimeException());
            return;
        }

        if (!authorization.canReadPayroll(principal, employeeId)) {
            responseObserver.onError(
                Status.PERMISSION_DENIED
                    .withDescription("caller cannot read payroll")
                    .asRuntimeException());
            return;
        }

        Optional<PayrollRecord> result =
            repository.findByEmployeeIdAndTenantId(
                employeeId, principal.tenantId());

        if (result.isEmpty()) {
            responseObserver.onError(
                Status.NOT_FOUND
                    .withDescription("payroll resource not found")
                    .asRuntimeException());
            return;
        }

        PayrollRecord payroll = result.get();
        responseObserver.onNext(GetPayrollResponse.newBuilder()
            .setEmployeeId(employeeId)
            .setGrossAmountMinor(payroll.grossAmountMinor())
            .setCurrency(payroll.currency())
            .build());
        responseObserver.onCompleted();
    }
}
~~~

PayrollRecord là kiểu dữ liệu nội bộ của ví dụ. Trong ứng dụng Spring, PayrollGrpcService thường được đăng ký bằng cơ chế service registration của starter và nhận PayrollRepository qua constructor injection. Việc kiểm tra quyền trước repository giúp request bị từ chối không truy cập dữ liệu bảng lương. Truy vấn repository tiếp tục ràng buộc tenantId lấy từ principal đã xác thực; không tin tenant ID do caller truyền trong request hoặc metadata.

Với API có chính sách che giấu sự tồn tại của resource, có thể cố ý trả NOT_FOUND thay cho PERMISSION_DENIED cho một số trường hợp. Khi đó phải áp dụng nhất quán và bảo đảm truy vấn được giới hạn theo tenant/principal, tránh để thời gian hoặc side effect làm lộ resource.

## 4. Kiểm thử PERMISSION_DENIED bằng in-process server

In-process transport cho phép chạy service và generated blocking stub trong cùng JVM. Test có thể cài một server interceptor chỉ dành cho fixture để đưa principal đã xác thực vào Context; interceptor này mô phỏng kết quả của authentication layer, không phải cơ chế xác minh credential production.

Test interceptor:

~~~java
final class TestPrincipalServerInterceptor
        implements ServerInterceptor {

    private final AuthenticatedPrincipal principal;

    TestPrincipalServerInterceptor(
            AuthenticatedPrincipal principal) {
        this.principal = principal;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        Context context = Context.current().withValue(
            AuthenticatedPrincipalContext.PRINCIPAL,
            principal);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

JUnit 5 test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import java.io.IOException;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class PayrollGrpcServiceTest {

    private Server server;
    private ManagedChannel channel;
    private PayrollServiceGrpc.PayrollServiceBlockingStub stub;
    private AtomicInteger repositoryCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        repositoryCalls = new AtomicInteger();

        AuthenticatedPrincipal principal =
            new AuthenticatedPrincipal(
                "user-17", "tenant-a", Set.of("PROFILE_READ"));

        PayrollAuthorization authorization =
            (caller, employeeId) -> false;

        PayrollRepository repository = (employeeId, tenantId) -> {
            repositoryCalls.incrementAndGet();
            return Optional.empty();
        };

        PayrollGrpcService service =
            new PayrollGrpcService(authorization, repository);

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                service,
                new TestPrincipalServerInterceptor(principal)))
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();

        stub = PayrollServiceGrpc.newBlockingStub(channel)
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
    void authenticatedCallerWithoutPermissionGetsPermissionDenied() {
        GetPayrollRequest request = GetPayrollRequest.newBuilder()
            .setEmployeeId("employee-42")
            .build();

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getPayroll(request));

        assertEquals(
            Status.Code.PERMISSION_DENIED,
            error.getStatus().getCode());
        assertEquals(
            "caller cannot read payroll",
            error.getStatus().getDescription());
        assertEquals(0, repositoryCalls.get());
    }
}
~~~

authorization trả false, trong khi interceptor cung cấp principal hợp lệ. Vì vậy test chứng minh đúng trường hợp **đã xác thực nhưng thiếu quyền**. Assertion repositoryCalls == 0 bảo đảm service từ chối trước khi truy cập dữ liệu. directExecutor() phù hợp vì handler trong ví dụ không blocking; nếu handler thực hiện I/O hoặc chờ latch, dùng executor phù hợp để không chặn thread test.

## 5. Kiểm thử các nhánh bảo mật liền kề

Chỉ kiểm thử PERMISSION_DENIED chưa đủ để chứng minh ranh giới authentication/authorization đúng. Nên bổ sung các ca:

| Principal/permission | Kết quả mong đợi | Repository |
| --- | --- | --- |
| Không có principal | UNAUTHENTICATED | Không gọi |
| Principal hợp lệ, thiếu PAYROLL_READ | PERMISSION_DENIED | Không gọi |
| Principal có quyền, employee ID sai định dạng | INVALID_ARGUMENT | Không gọi |
| Principal có quyền, resource không tồn tại | NOT_FOUND | Truy vấn theo tenant |
| Principal có quyền, resource thuộc tenant hợp lệ | Thành công | Truy vấn theo tenant |
| Database lỗi | UNAVAILABLE hoặc mapping hạ tầng phù hợp | Không đổi thành lỗi quyền |

Test thành công cần xác minh user có đúng authority nhận được response, còn user thiếu authority không thể đọc dữ liệu dù biết employee ID hợp lệ. Kiểm tra cả tenant boundary: quyền đọc ở tenant A không tự động cho phép truy cập resource tenant B.

## 6. Không kiểm thử bằng cách tin header do client tự gửi

Một test không an toàn thường thêm x-user-id hoặc x-role vào metadata rồi để service coi đó là principal. Cách này chỉ kiểm tra việc đọc header, không kiểm tra authentication. Client có thể tự sửa các giá trị đó.

Trong test service authorization, dùng test-only server interceptor như ví dụ trên để mô phỏng principal đã được xác minh. Trong integration test authentication, gửi token giả/đúng qua cơ chế credential thật và xác minh authentication interceptor:

- Token hợp lệ tạo principal đúng subject, tenant và authorities.
- Token thiếu, sai chữ ký, sai issuer hoặc hết hạn trả UNAUTHENTICATED.
- Token hợp lệ nhưng thiếu permission trả PERMISSION_DENIED.
- Metadata giả mạo role hoặc tenant không thể nâng quyền caller.

Không dùng principal test interceptor trong production. Không ghi access token, private claim hoặc thông tin nhạy cảm vào log.

## 7. Kiểm tra policy và side effect

Với RPC đọc, test xác minh repository không được gọi khi authorization thất bại. Với RPC ghi, cần kiểm tra mạnh hơn:

1. Policy từ chối trước khi transaction tạo hoặc cập nhật dữ liệu.
2. Không phát domain event, gửi message hoặc gọi downstream.
3. Không ghi audit event thành công; nếu cần audit từ chối, ghi event riêng với quyền truy cập hạn chế.
4. Không thay đổi trạng thái resource hoặc cache.
5. Khi policy cho phép, thao tác vẫn tuân thủ tenant scope và các điều kiện nghiệp vụ.

Không chỉ assert status code. Một service có thể trả PERMISSION_DENIED nhưng đã thực hiện side effect trước đó; test repository/mock invocation và trạng thái dữ liệu để phát hiện lỗi này.

## 8. Status description và chống lộ thông tin

Status description được gửi về caller. Giữ thông điệp ngắn, ổn định và không tiết lộ rule nội bộ, role cụ thể, danh sách user hoặc dữ liệu resource nhạy cảm. Ví dụ caller cannot read payroll đủ cho API công khai; chi tiết policy có thể được ghi trong audit log bảo vệ riêng.

Nếu API cần che giấu resource khỏi caller, quyết định trả NOT_FOUND phải được áp dụng nhất quán cho cả resource không tồn tại và resource ngoài phạm vi. Không để status, message, response time hoặc side effect tiết lộ khác biệt.

## 9. Kiểm thử qua Spring application context

In-process test xác minh service implementation, principal context và status mapping. Nó không chứng minh Spring starter đã đăng ký đúng interceptor hoặc authentication provider. Bổ sung integration test khởi động application context để kiểm tra:

- Authentication interceptor chạy trước service handler.
- Token hợp lệ tạo đúng principal.
- Authorization policy lấy authority từ principal đã xác minh.
- Interceptor không biến PERMISSION_DENIED thành UNKNOWN.
- Repository và downstream không được gọi khi bị từ chối.
- TLS, metadata và credential hoạt động qua transport thực nếu deployment yêu cầu.

Cách đăng ký interceptor phụ thuộc starter/version. Dùng extension point server interceptor của thư viện đang sử dụng; không giả định mọi Spring gRPC starter có cùng annotation hoặc property.

## 10. Ma trận kiểm thử đề xuất

| Nhóm | Kịch bản | Assertion |
| --- | --- | --- |
| Authentication | Token thiếu hoặc sai | UNAUTHENTICATED |
| Authorization | Principal hợp lệ nhưng thiếu quyền | PERMISSION_DENIED |
| Resource | Có quyền nhưng resource không tồn tại | NOT_FOUND |
| Tenant | Có quyền ở tenant khác | Bị từ chối hoặc che giấu theo policy |
| Side effect | Request bị từ chối | Không đọc/ghi repository ngoài bước policy cần thiết; không gọi downstream |
| Success | Principal có quyền và resource hợp lệ | Response đúng |
| Error mapping | Blocking/async client | Đều nhận đúng status |
| Spring wiring | Application context thật | Authentication và authorization interceptor được đăng ký đúng |

Ưu tiên assert Status.Code.PERMISSION_DENIED; không chỉ so sánh chuỗi description. Message có thể thay đổi, nhưng semantics status phải ổn định cho client và retry policy.

## 11. Ghi nhớ và tự kiểm tra

**Test PERMISSION_DENIED** phải dùng principal đã xác thực nhưng thiếu quyền, xác minh server trả đúng status và không thực hiện thao tác bị cấm. Dùng gRPC Context để truyền principal từ authentication interceptor, tách policy authorization khỏi repository, và kiểm thử bằng in-process server cùng generated blocking stub. Bổ sung Spring integration test để xác minh interceptor/credential được nối đúng trong application context.

Tự kiểm tra:

1. Vì sao PERMISSION_DENIED khác UNAUTHENTICATED?
2. Vì sao principal phải đến từ authentication layer đã xác minh thay vì metadata do client tự gửi?
3. Vì sao test cần xác minh repository không được gọi khi policy từ chối?
4. Khi nào API có thể trả NOT_FOUND thay cho PERMISSION_DENIED để tránh resource enumeration?
5. Làm thế nào để bảo đảm quyền của tenant này không áp dụng cho resource tenant khác?
6. In-process test không chứng minh được những phần nào của authentication integration trong Spring?

Kiểm thử authorization đúng giúp Spring gRPC thực thi policy nhất quán, ngăn truy cập trái phép và giữ dữ liệu không bị đọc hoặc thay đổi sau khi request đã bị từ chối.
