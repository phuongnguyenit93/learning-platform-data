# Phân biệt authentication và authorization

## 1. Hai câu hỏi bảo mật khác nhau

Trong **Spring gRPC**, authentication và authorization thường xuất hiện cùng một request nhưng giải quyết hai câu hỏi riêng:

- **Authentication (xác thực):** request đến từ ai? Hệ thống kiểm tra credential để xác lập danh tính của người dùng hoặc service gọi.
- **Authorization (ủy quyền):** danh tính đó được phép làm gì trên tài nguyên nào? Hệ thống đánh giá quyền và policy trước khi cho phép thao tác.

Ví dụ, một access token hợp lệ có thể xác thực người gọi là nhân viên thuộc tenant-17. Điều đó chưa có nghĩa người này được phép đọc mọi đơn hàng trong tenant. Authorization còn phải kiểm tra vai trò, quyền trên method và quyền truy cập chính đơn hàng được yêu cầu.

Một RPC chỉ nên đi vào logic nghiệp vụ sau khi danh tính đã được xác thực và quyền cần thiết đã được kiểm tra ở đúng phạm vi.

## 2. So sánh authentication và authorization

| Tiêu chí | Authentication | Authorization |
| --- | --- | --- |
| Câu hỏi | Ai đang gọi? | Được phép thực hiện hành động nào? |
| Đầu vào | Certificate, bearer token, API key hoặc credential khác | Principal đã xác thực, permission, resource và policy |
| Kết quả | Danh tính/principal đã được xác minh hoặc từ chối | Cho phép hoặc từ chối thao tác |
| Thời điểm | Thường ở đầu RPC, trước xử lý nghiệp vụ | Ở method boundary và/hoặc trong service khi biết resource |
| Ví dụ | Xác minh chữ ký JWT và thời hạn token | Kiểm tra principal có quyền orders:read trên order cụ thể |
| gRPC status khi thất bại | Thường là UNAUTHENTICATED | Thường là PERMISSION_DENIED |

Hai bước liên quan nhưng không thay thế nhau. Token hợp lệ không tự động cấp mọi quyền; người dùng có role ADMIN cũng vẫn phải chứng minh danh tính trước khi hệ thống tin role đó.

## 3. Luồng xử lý trong Spring gRPC

~~~mermaid
sequenceDiagram
    participant C as gRPC Client
    participant T as TLS / mTLS
    participant A as Authentication interceptor
    participant Z as Authorization policy
    participant S as Spring gRPC service
    participant D as Database
    C->>T: RPC + credential metadata
    T->>T: Xác minh kênh và certificate nếu dùng mTLS
    T->>A: Request đã qua transport security
    A->>A: Xác minh token / credential
    A->>Z: Principal đã xác thực
    Z->>Z: Kiểm tra quyền trên method
    Z->>S: Cho phép tiếp tục
    S->>D: Kiểm tra quyền trên resource và đọc dữ liệu
    D-->>S: Kết quả trong phạm vi được phép
    S-->>C: Response
~~~

TLS bảo vệ kênh truyền; authentication xác lập principal; authorization quyết định principal có quyền thực hiện RPC và thao tác trên resource hay không.

Với một số method, authorization ở interceptor có thể từ chối ngay theo quyền gọi method. Với quyền phụ thuộc dữ liệu như chủ sở hữu đơn hàng, service phải kiểm tra sau khi biết resource nhưng trước khi trả dữ liệu hoặc tạo side effect.

## 4. Authentication: xác minh danh tính

Các cơ chế thường gặp trong gRPC:

### 4.1. TLS và mutual TLS

- TLS xác thực server với client và mã hóa, bảo vệ tính toàn vẹn dữ liệu trên đường truyền.
- Mutual TLS (mTLS) yêu cầu client cũng trình certificate để server xác minh danh tính workload/peer.
- Certificate có thể xác định một service như inventory-service, phù hợp xác thực service-to-service.

mTLS không tự xác thực người dùng cuối đang thao tác qua service đó. Một gateway có thể có certificate hợp lệ nhưng vẫn cần token hoặc danh tính người dùng được ủy quyền để thực hiện yêu cầu thay mặt người dùng.

### 4.2. Bearer token trong gRPC metadata

Client thường gửi access token trong metadata:

~~~text
authorization: Bearer <access-token>
~~~

Server cần xác minh ít nhất:

- Chữ ký token bằng key tin cậy.
- Issuer (iss) đúng hệ thống phát hành.
- Audience (aud) phù hợp service nhận.
- Thời hạn (exp, và nbf nếu có).
- Subject (sub) và các claim cần thiết có cấu trúc hợp lệ.
- Scope/role được phát hành từ nguồn tin cậy, không phải claim client tự thêm.

Không chỉ decode JWT rồi tin payload. Decode không xác minh chữ ký. Với opaque token, cần introspection hoặc cơ chế xác minh qua authorization server theo thiết kế hệ thống.

### 4.3. API key và credential khác

API key có thể nhận diện ứng dụng hoặc client tích hợp, nhưng thường không đại diện đầy đủ cho người dùng cuối và không nên thay thế hệ thống identity có khả năng thu hồi, hết hạn, scope và audit. Nếu dùng API key, lưu trữ an toàn, hỗ trợ rotation/revocation và giới hạn quyền rõ ràng.

## 5. Authorization: đánh giá quyền

Sau authentication, server có một principal đáng tin cậy. Authorization sử dụng principal đó để quyết định:

- Principal có được gọi RPC này không?
- Principal có được thao tác trên tenant hoặc resource được chỉ định không?
- Hành động là đọc, tạo, sửa, xóa hay phê duyệt?
- Quyền có phụ thuộc trạng thái resource, quan hệ sở hữu hoặc điều kiện nghiệp vụ không?

Ba cách tổ chức policy thường gặp:

| Mô hình | Ví dụ | Phù hợp |
| --- | --- | --- |
| Role-based access control (RBAC) | ORDER_ADMIN được phép quản lý đơn hàng | Quyền tương đối ổn định theo vai trò |
| Scope/permission-based | orders:read, orders:write | API/service có quyền thao tác rõ ràng |
| Attribute/resource-based (ABAC) | Người tạo đơn hoặc quản lý đúng khu vực mới được đọc | Quyền phụ thuộc principal, resource và ngữ cảnh |

Ứng dụng thực tế thường kết hợp các mô hình. Ví dụ, scope orders:read cho phép gọi chức năng đọc, sau đó ABAC kiểm tra principal có quyền đọc order thuộc tenant và vùng quản lý cụ thể hay không.

## 6. Phân biệt UNAUTHENTICATED và PERMISSION_DENIED

Hai status cần được dùng nhất quán:

| Tình huống | Status thường dùng | Ý nghĩa |
| --- | --- | --- |
| Thiếu bearer token bắt buộc | UNAUTHENTICATED | Chưa xác lập được danh tính |
| Token sai chữ ký, hết hạn hoặc sai audience | UNAUTHENTICATED | Credential không hợp lệ cho service |
| Certificate client không được tin cậy | Lỗi handshake TLS hoặc từ chối transport | Chưa thiết lập được peer identity |
| Token hợp lệ nhưng thiếu scope cần thiết | PERMISSION_DENIED | Đã xác thực nhưng không đủ quyền |
| Principal không sở hữu resource | PERMISSION_DENIED hoặc NOT_FOUND theo chính sách chống dò tìm | Danh tính hợp lệ nhưng không được truy cập |
| Principal được phép | OK nếu xử lý thành công | Authorization đã cho phép |

NOT_FOUND đôi khi được dùng thay PERMISSION_DENIED để không tiết lộ resource có tồn tại hay không. Đây là lựa chọn API/security policy cần thống nhất; không dùng status khác nhau tùy tiện giữa các method tương đương.

Không trả UNAUTHENTICATED cho mọi lỗi bảo mật. Nếu credential hợp lệ nhưng không có quyền, PERMISSION_DENIED giúp client và telemetry phân biệt đúng nguyên nhân.

## 7. Đặt authentication trong ServerInterceptor

Server interceptor là nơi thích hợp để xác minh credential chung cho nhiều RPC. Khi token hợp lệ, tạo principal và đặt vào gRPC Context để service và interceptor tiếp theo đọc được.

Ví dụ minh họa với một TokenVerifier của ứng dụng:

~~~java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class AuthenticationInterceptor
        implements ServerInterceptor {

    static final Context.Key<AuthenticatedPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of(
                    "authorization",
                    Metadata.ASCII_STRING_MARSHALLER);

    private final TokenVerifier tokenVerifier;

    public AuthenticationInterceptor(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AUTHORIZATION);
        if (authorization == null
                || !authorization.startsWith("Bearer ")
                || authorization.length() <= "Bearer ".length()) {
            call.close(Status.UNAUTHENTICATED
                    .withDescription("Missing or invalid credentials"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        AuthenticatedPrincipal principal;
        try {
            String token = authorization.substring("Bearer ".length());
            principal = tokenVerifier.verify(token);
        } catch (InvalidCredentialException error) {
            call.close(Status.UNAUTHENTICATED
                    .withDescription("Missing or invalid credentials"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        Context authenticated = Context.current()
                .withValue(PRINCIPAL, principal);
        return Contexts.interceptCall(
                authenticated, call, headers, next);
    }
}
~~~

TokenVerifier phải thực hiện xác minh chữ ký/issuer/audience/expiry hoặc introspection theo loại token. AuthenticatedPrincipal là kiểu dữ liệu ứng dụng chứa subject, tenant và quyền đã xác minh; không lấy các trường này trực tiếp từ request body.

Interceptor không nên ghi token vào log hoặc trả chi tiết nội bộ như signature mismatch cho caller. Log nội bộ có thể ghi lý do phân loại an toàn, không chứa credential.

## 8. Authorization ở method boundary

Với quyền áp dụng cho toàn RPC, có thể dùng một interceptor tiếp theo để kiểm tra policy dựa trên full method name:

~~~java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class MethodAuthorizationInterceptor
        implements ServerInterceptor {

    private final MethodPermissionPolicy policy;
    private final AuthorizationService authorization;

    public MethodAuthorizationInterceptor(
            MethodPermissionPolicy policy,
            AuthorizationService authorization) {
        this.policy = policy;
        this.authorization = authorization;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        AuthenticatedPrincipal principal =
                AuthenticationInterceptor.PRINCIPAL.get();
        String method = call.getMethodDescriptor().getFullMethodName();
        Permission required = policy.requiredPermission(method);

        if (principal == null
                || required == null
                || !authorization.hasPermission(principal, required)) {
            call.close(Status.PERMISSION_DENIED
                    .withDescription("Permission denied"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

Đăng ký authentication interceptor trước method authorization interceptor để principal đã có trong Context khi policy chạy. Thứ tự cụ thể của interceptor có thể phụ thuộc cách cấu hình server/Spring gRPC; cần xác minh chain thực tế của phiên bản đang dùng.

Policy nên fail closed: mọi method được bảo vệ phải có permission mapping rõ ràng. Nếu method chưa có mapping, từ chối thay vì mặc định cho phép. Những RPC công khai nên được khai báo rõ trong một policy riêng.

Không phải mọi quyền đều có thể kiểm tra ở interceptor. Method interceptor biết RPC name nhưng thường chưa biết order ID, owner hoặc trạng thái nghiệp vụ nằm trong request message. Những quyền đó phải được kiểm tra trong application service.

## 9. Authorization theo resource trong service

Ví dụ người gọi có scope orders:read, nhưng chỉ được đọc đơn hàng thuộc tenant của mình hoặc khu vực được phân công. Service cần lấy principal từ Context và truy vấn resource trong phạm vi quyền:

~~~java
import io.grpc.Status;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final AuthorizationService authorization;

    public OrderApplicationService(
            OrderRepository orders,
            AuthorizationService authorization) {
        this.orders = orders;
        this.authorization = authorization;
    }

    @Transactional(readOnly = true)
    public Order getOrder(String orderId) {
        AuthenticatedPrincipal principal =
                AuthenticationInterceptor.PRINCIPAL.get();
        if (principal == null) {
            throw Status.UNAUTHENTICATED
                    .withDescription("Authentication required")
                    .asRuntimeException();
        }

        authorization.requirePermission(principal, "orders:read");

        Order order = orders.findByIdAndTenantId(
                        orderId, principal.tenantId())
                .orElseThrow(() -> Status.NOT_FOUND
                        .withDescription("Order not found")
                        .asRuntimeException());

        authorization.requireCanReadOrder(principal, order);
        return order;
    }
}
~~~

findByIdAndTenantId() giới hạn truy vấn theo tenant đã xác thực thay vì tin tenant_id do client gửi. Nếu người dùng có quyền truy cập chéo tenant theo nghiệp vụ, policy phải xác minh quan hệ đó một cách tường minh.

Kiểm tra quyền nên nằm trong cùng transaction hoặc cùng truy vấn có điều kiện phù hợp để giảm race giữa kiểm tra quyền và sử dụng resource. Với thao tác ghi, kiểm tra quyền trước side effect và cân nhắc điều kiện authorization ngay trong câu lệnh update/delete.

## 10. Gắn credential từ client

Client nên dùng cơ chế credential của gRPC như CallCredentials để đính kèm bearer token theo từng call. Token cần được lấy từ nguồn credential an toàn, làm mới khi hết hạn và không lưu cứng trong source code.

Ví dụ cách sử dụng một implementation CallCredentials do ứng dụng cung cấp:

~~~java
import java.util.concurrent.TimeUnit;
import com.example.catalog.v1.CatalogServiceGrpc;
import com.example.catalog.v1.GetItemRequest;
import com.example.catalog.v1.GetItemResponse;

CatalogServiceGrpc.CatalogServiceBlockingStub authenticatedStub =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withCallCredentials(
                        new BearerTokenCallCredentials(tokenProvider));

GetItemResponse response = authenticatedStub
        .withDeadlineAfter(2, TimeUnit.SECONDS)
        .getItem(request);
~~~

BearerTokenCallCredentials và tokenProvider là thành phần ứng dụng; implementation cần tạo metadata authorization cho call, xử lý refresh/error và không chia sẻ mutable token state không an toàn giữa nhiều request.

Không truyền token trong Protobuf request, query string hoặc log. Metadata cũng là dữ liệu nhạy cảm: cấu hình tracing/proxy/logging để không ghi header authorization. Luôn dùng TLS khi gửi bearer token qua mạng.

## 11. Kết hợp mTLS và token

Trong service-to-service, có thể dùng cả mTLS và bearer token:

| Lớp | Danh tính được xác minh | Mục đích |
| --- | --- | --- |
| mTLS | Workload/service peer qua client certificate | Xác nhận service kết nối tới server là workload được tin cậy |
| Bearer token | User hoặc service principal theo issuer/audience | Xác định chủ thể và scope của request |
| Authorization policy | Principal + method + resource | Quyết định request được phép làm gì |

Ví dụ gateway có certificate hợp lệ để kết nối tới order-service, đồng thời chuyển tiếp access token của người dùng. Order service xác minh cả peer identity theo trust policy lẫn token người dùng, sau đó kiểm tra người dùng có quyền đọc order cụ thể.

Nếu gateway thay mặt người dùng gọi service bằng service token, cần có cơ chế delegation/token exchange đáng tin cậy để truyền actor và subject. Không tin header tùy ý như x-user-id nếu nó có thể được client bên ngoài tự đặt.

## 12. Kiểm thử authentication và authorization

Hai nhóm test nên tách biệt để chứng minh mỗi lớp hoạt động đúng:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Không gửi token | UNAUTHENTICATED; service method không chạy |
| Token sai chữ ký/hết hạn/sai audience | UNAUTHENTICATED |
| Token hợp lệ, đủ scope và đúng resource | RPC thành công |
| Token hợp lệ nhưng thiếu permission method | PERMISSION_DENIED |
| Token hợp lệ, scope đúng nhưng khác tenant | Bị từ chối theo resource policy |
| Principal không phải owner của order | Bị từ chối hoặc NOT_FOUND theo contract |
| Certificate mTLS không tin cậy | TLS handshake bị từ chối trước RPC |
| Token hết hạn giữa các lần gọi | Call mới bị từ chối; refresh credential theo flow |
| Client tự gửi tenant_id khác | Server vẫn dùng tenant từ principal đã xác thực |
| Interceptor chain sai thứ tự | Test phát hiện principal chưa có khi authorization chạy |

Ngoài status, kiểm tra side effect: request bị từ chối không được đọc dữ liệu ngoài phạm vi, ghi database hoặc phát event. Dùng test certificate/token riêng cho test; không đưa credential production vào fixture.

## 13. Sai lầm thường gặp

1. **Coi token hợp lệ là được phép làm mọi việc.** Authentication không thay thế authorization.
2. **Coi mTLS là danh tính người dùng cuối.** Certificate thường xác định workload/peer.
3. **Chỉ kiểm tra role ở gateway.** Service vẫn phải bảo vệ resource và side effect của chính nó.
4. **Tin tenant/user ID từ request body hoặc metadata tùy ý.** Lấy principal từ credential đã xác minh.
5. **Trả UNAUTHENTICATED cho mọi lỗi quyền.** Credential hợp lệ nhưng thiếu quyền nên dùng PERMISSION_DENIED.
6. **Chỉ kiểm tra permission theo method.** Quyền resource/ownership có thể cần kiểm tra trong service.
7. **Decode JWT mà không xác minh chữ ký và audience.** Payload tự nó không chứng minh danh tính.
8. **Đưa bearer token vào log hoặc trace.** Có thể làm lộ credential.
9. **Không kiểm thử thứ tự interceptor.** Authorization có thể chạy khi principal chưa được thiết lập.
10. **Cho rằng cancellation hoặc lỗi transport làm mất side effect đã commit.** Authentication/authorization không thay thế idempotency và transaction design.

## 14. Bài tập vận dụng

Với orders.v1.OrderService/GetOrder:

1. Thiết kế bearer token có iss, aud, sub, exp, tenant và scope.
2. Viết authentication interceptor xác minh token và đặt principal vào gRPC Context.
3. Viết method authorization policy yêu cầu orders:read.
4. Trong application service, truy vấn order theo tenant của principal và kiểm tra ownership/resource policy.
5. Cấu hình TLS; thử mTLS để xác minh workload client riêng với token người dùng.
6. Viết test cho token thiếu/sai/hết hạn, thiếu scope, khác tenant và đúng quyền.
7. Xác minh request bị từ chối không tạo side effect và log không chứa token.

**Tiêu chí hoàn thành:** người học giải thích được authentication xác lập danh tính còn authorization quyết định quyền; cấu hình được credential/interceptor, phân biệt UNAUTHENTICATED với PERMISSION_DENIED, kiểm tra quyền method và resource, đồng thời kiểm thử cả TLS/mTLS và bearer token.

### Tài liệu tham khảo

- [gRPC Authentication](https://grpc.io/docs/guides/auth/): TLS, token và cơ chế xác thực trong gRPC.
- [gRPC Metadata](https://grpc.io/docs/guides/metadata/): truyền credential và metadata trong RPC.
- [gRPC Java ServerInterceptor API](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerInterceptor.html): xử lý authentication/authorization ở server boundary.
- [gRPC Status Codes](https://grpc.io/docs/guides/status-codes/): phân biệt UNAUTHENTICATED và PERMISSION_DENIED.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): principal, authentication và authorization trong Spring.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): tích hợp gRPC client/server trong Spring.
