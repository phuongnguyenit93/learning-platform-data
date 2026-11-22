# Lỗi quyền và UNAUTHENTICATED, PERMISSION_DENIED

**Chương:** Error handling  
**Phạm vi:** Spring gRPC (`SPRING_GRPC`) dùng Protocol Buffers, mã Java được sinh và RPC unary hoặc streaming. Bài này tập trung vào hai lỗi bảo mật ở ranh giới API: **không xác thực được danh tính** và **caller đã xác thực nhưng không có quyền thực hiện thao tác**.

## 1. Phân biệt authentication và authorization

Hai bước này giải quyết hai câu hỏi khác nhau:

- **Authentication (xác thực):** caller là ai? Server kiểm tra credential, chữ ký, thời hạn và issuer để xác định danh tính đáng tin cậy.
- **Authorization (ủy quyền):** danh tính đó được phép làm gì trên tài nguyên nào? Server kiểm tra role, scope, permission, tenant và quan hệ với tài nguyên.

Vì vậy, hai gRPC status có ý nghĩa khác nhau:

| Tình huống | Status | Ý nghĩa |
| --- | --- | --- |
| Không có credential bắt buộc | `UNAUTHENTICATED` | Server chưa xác định được danh tính hợp lệ |
| Token sai chữ ký, hết hạn hoặc issuer không hợp lệ | `UNAUTHENTICATED` | Credential không chứng minh được danh tính |
| Token hợp lệ nhưng thiếu scope/role | `PERMISSION_DENIED` | Caller đã xác thực nhưng không được phép |
| Caller có quyền đọc nhưng không có quyền ghi | `PERMISSION_DENIED` cho thao tác ghi | Quyền phụ thuộc hành động |
| Caller không thuộc tenant được phép truy cập | Thường `PERMISSION_DENIED` | Danh tính có thật nhưng phạm vi truy cập không phù hợp |

Ví dụ: một nhân viên có token hợp lệ nhưng chỉ có quyền xem đơn hàng. Khi gọi RPC xóa đơn, server trả `PERMISSION_DENIED`. Nếu token đã hết hạn, server trả `UNAUTHENTICATED` trước khi kiểm tra quyền trên đơn hàng.

**Không dùng hai status thay thế cho nhau.** Nếu trả `UNAUTHENTICATED` cho một user đã xác thực nhưng thiếu quyền, client có thể làm mới token vô ích. Nếu trả `PERMISSION_DENIED` cho token hết hạn, client không biết cần xác thực lại.

## 2. Credential thường được gửi qua metadata

Một client thường gửi access token trong metadata:

```java
Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of(
                "authorization",
                Metadata.ASCII_STRING_MARSHALLER);

Metadata headers = new Metadata();
headers.put(AUTHORIZATION, "Bearer " + accessToken);

CustomerServiceGrpc.CustomerServiceBlockingStub authenticatedStub =
        MetadataUtils.attachHeaders(blockingStub, headers);

Customer customer = authenticatedStub.getCustomer(request);
```

Metadata `authorization` là header ứng dụng, không phải field trong protobuf message. Nó được gửi theo từng RPC. Client không nên hard-code token hoặc ghi token vào log. Trong hệ thống thực, credential nên được gắn bằng cơ chế call credentials hoặc interceptor phù hợp vòng đời token để tự làm mới và tránh chia sẻ token giữa người dùng.

### Bảo vệ credential trên đường truyền

Access token là bearer credential: ai có token có thể sử dụng token theo quyền của nó. Vì vậy:

- Dùng TLS khi gửi credential qua mạng; không gửi bearer token trên kết nối plaintext.
- Không đưa token vào protobuf payload, status description, trailers hoặc log.
- Không ghi toàn bộ metadata headers trong interceptor logging.
- Kiểm tra issuer, audience, chữ ký, thời hạn và thuật toán được cho phép; không chỉ decode token rồi tin các claim.
- Không lấy user ID hoặc role do client tự khai báo trong request làm danh tính đã xác thực.

## 3. Xác thực tại server bằng interceptor

Authentication nên được thực hiện sớm, trước khi gọi business handler. gRPC Java cung cấp `ServerInterceptor` để đọc metadata và xác thực credential cho từng RPC.

Ví dụ dùng một abstraction `TokenAuthenticator` để xác minh token. Chi tiết xác minh chữ ký phụ thuộc hệ thống identity provider, nhưng kết quả phải là principal do server tin cậy tạo ra:

```java
public record AuthenticatedPrincipal(
        String subject,
        String tenantId,
        Set<String> authorities) {}

public interface TokenAuthenticator {
    AuthenticatedPrincipal authenticate(String bearerToken)
            throws InvalidCredentialException;
}
```

Interceptor trích bearer token, gọi authenticator và đưa principal vào gRPC `Context`:

```java
import io.grpc.Context;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import io.grpc.Contexts;

public final class AuthenticationInterceptor implements ServerInterceptor {

    public static final Context.Key<AuthenticatedPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of(
                    "authorization",
                    Metadata.ASCII_STRING_MARSHALLER);

    private final TokenAuthenticator authenticator;

    public AuthenticationInterceptor(TokenAuthenticator authenticator) {
        this.authenticator = authenticator;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AUTHORIZATION);
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        String token = authorization.substring("Bearer ".length()).trim();
        if (token.isEmpty()) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Invalid credentials"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        try {
            AuthenticatedPrincipal principal =
                    authenticator.authenticate(token);
            Context context = Context.current()
                    .withValue(PRINCIPAL, principal);
            return Contexts.interceptCall(context, call, headers, next);
        } catch (InvalidCredentialException invalid) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Invalid credentials"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }
    }
}
```

Đây là ví dụ về ranh giới xác thực; cần đăng ký interceptor với server/service theo cấu hình Spring gRPC của phiên bản đang dùng. Không ghi token hoặc exception chi tiết của thư viện xác thực vào log/description. Lỗi hết hạn, sai chữ ký, sai issuer hoặc token không hợp lệ đều được quy về `UNAUTHENTICATED`.

### Principal trong Context

`Context` của gRPC gắn principal với vòng đời RPC. Handler có thể lấy danh tính đã được interceptor xác minh:

```java
AuthenticatedPrincipal principal =
        AuthenticationInterceptor.PRINCIPAL.get();

if (principal == null) {
    // RPC không đi qua authentication interceptor như mong đợi.
    throw new IllegalStateException("Authenticated principal missing");
}
```

Không lưu principal vào một field mutable của singleton Spring service. Nhiều RPC chạy đồng thời; Context giúp dữ liệu danh tính gắn với call thay vì chia sẻ giữa các request. Khi chuyển công việc sang executor riêng, cần truyền/đính kèm Context đúng cách hoặc truyền principal một cách tường minh.

## 4. Authorization kiểm tra quyền trên hành động và tài nguyên

Sau khi có principal, application service hoặc authorization component quyết định caller có quyền thực hiện hành động hay không. Không nên chỉ kiểm tra một role chung nếu quyền phụ thuộc tenant, chủ sở hữu tài nguyên hoặc trạng thái nghiệp vụ.

Ví dụ một policy:

```java
public interface TransferAuthorization {
    boolean canRead(
            AuthenticatedPrincipal principal,
            String transferId);

    boolean canCancel(
            AuthenticatedPrincipal principal,
            String transferId);
}
```

Service adapter sử dụng principal đã xác thực và trả `PERMISSION_DENIED` khi policy từ chối:

```java
@GrpcService
public class TransferGrpcService
        extends TransferServiceGrpc.TransferServiceImplBase {

    private final TransferApplicationService applicationService;
    private final TransferAuthorization authorization;

    public TransferGrpcService(
            TransferApplicationService applicationService,
            TransferAuthorization authorization) {
        this.applicationService = applicationService;
        this.authorization = authorization;
    }

    @Override
    public void cancelTransfer(
            CancelTransferRequest request,
            StreamObserver<TransferResponse> responseObserver) {

        AuthenticatedPrincipal principal =
                AuthenticationInterceptor.PRINCIPAL.get();

        if (principal == null) {
            responseObserver.onError(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required")
                            .asRuntimeException());
            return;
        }

        if (!authorization.canCancel(principal, request.getTransferId())) {
            responseObserver.onError(
                    Status.PERMISSION_DENIED
                            .withDescription("Operation is not permitted")
                            .asRuntimeException());
            return;
        }

        try {
            Transfer transfer = applicationService.cancel(
                    principal.tenantId(), request.getTransferId());
            responseObserver.onNext(toProto(transfer));
            responseObserver.onCompleted();
        } catch (TransferNotFoundException missing) {
            responseObserver.onError(
                    Status.NOT_FOUND
                            .withDescription("Transfer not found")
                            .asRuntimeException());
        }
    }
}
```

Ví dụ minh họa kiểm tra quyền ở adapter. Với nghiệp vụ phức tạp, nên đặt policy trong application/domain authorization service để tránh lặp logic giữa các transport. Application service vẫn phải ràng buộc tenant/owner trong truy vấn hoặc thao tác cập nhật; không dựa riêng vào bước kiểm tra trước đó nếu có nguy cơ race condition.

### Chống truy cập chéo tenant

Không lấy `tenant_id` từ protobuf request làm căn cứ duy nhất. Hãy lấy tenant từ principal đã xác thực, sau đó giới hạn truy vấn:

```java
repository.findByIdAndTenantId(
        transferId,
        principal.tenantId());
```

Nếu API cần tránh tiết lộ tài nguyên có tồn tại ở tenant khác hay không, có thể trả `NOT_FOUND` thay cho `PERMISSION_DENIED` theo chính sách chống enumeration. Quyết định này phải nhất quán và được ghi rõ trong hợp đồng API; không được vô tình tiết lộ sự tồn tại của tài nguyên qua status hoặc description.

## 5. Status ở client: làm mới credential hay dừng thao tác?

Client nên phân loại theo status code:

| Status | Phản ứng client |
| --- | --- |
| `UNAUTHENTICATED` | Kiểm tra phiên, làm mới credential theo chính sách rồi thử lại có giới hạn |
| `PERMISSION_DENIED` | Dừng thao tác; không retry cùng credential và request |
| `NOT_FOUND` | Hiển thị không tìm thấy hoặc làm mới danh sách |
| `UNAVAILABLE` | Retry có backoff nếu thao tác an toàn |
| `DEADLINE_EXCEEDED` | Kiểm tra kết quả trước retry nếu RPC có tác dụng phụ |

Không tự động refresh token vô hạn. Một chiến lược client hợp lý:

1. Gửi RPC bằng credential hiện tại.
2. Nếu nhận `UNAUTHENTICATED`, yêu cầu token provider refresh một lần.
3. Nếu refresh thành công, gửi lại RPC với credential mới và giới hạn số lần thử.
4. Nếu vẫn `UNAUTHENTICATED`, yêu cầu người dùng đăng nhập lại hoặc dừng.
5. Nếu nhận `PERMISSION_DENIED`, không refresh token để cố vượt qua policy; hiển thị quyền cần thiết hoặc kết thúc thao tác.

Với RPC ghi dữ liệu, lần retry sau refresh vẫn cần idempotency key nếu lần đầu có khả năng đã tạo tác dụng phụ trước khi status được trả về.

## 6. Kiểm thử authentication và authorization

Hai nhóm test phải độc lập vì chúng xác minh hai cổng khác nhau:

| Ca kiểm thử | Credential | Quyền | Kỳ vọng |
| --- | --- | --- | --- |
| Thiếu metadata authorization | Không có | Chưa xác định | `UNAUTHENTICATED` |
| Token sai/hết hạn | Không hợp lệ | Chưa xác định | `UNAUTHENTICATED` |
| Token hợp lệ | Thiếu quyền hủy | Không đủ | `PERMISSION_DENIED` |
| Token hợp lệ | Có quyền hủy | Đủ | RPC thành công nếu nghiệp vụ cho phép |
| Token hợp lệ ở tenant A | Tài nguyên tenant B | Ngoài phạm vi | Status theo policy tenant, thường `PERMISSION_DENIED` hoặc `NOT_FOUND` |

Ví dụ unit test cho policy:

```java
class TransferAuthorizationTest {

    private final TransferAuthorization authorization =
            new DefaultTransferAuthorization();

    @Test
    void viewerCannotCancelTransfer() {
        var viewer = new AuthenticatedPrincipal(
                "user-1", "tenant-A", Set.of("TRANSFER_READ"));

        assertFalse(authorization.canCancel(viewer, "transfer-9"));
    }

    @Test
    void operatorWithCancelPermissionCanCancel() {
        var operator = new AuthenticatedPrincipal(
                "user-2", "tenant-A",
                Set.of("TRANSFER_READ", "TRANSFER_CANCEL"));

        assertTrue(authorization.canCancel(operator, "transfer-9"));
    }
}
```

Integration test qua gRPC in-process nên xác nhận cả interceptor và status thực tế:

- Không gửi metadata: handler nghiệp vụ không được gọi và client nhận `UNAUTHENTICATED`.
- Token giả hoặc hết hạn: handler không được gọi và client nhận `UNAUTHENTICATED`.
- Token hợp lệ nhưng thiếu quyền: authenticator thành công, policy từ chối và client nhận `PERMISSION_DENIED`.
- Token hợp lệ, đủ quyền: handler chạy trong Context có đúng principal.
- Tenant không khớp: repository không trả dữ liệu ngoài tenant.

Test không nên chỉ mock `AuthenticationInterceptor.PRINCIPAL` khi mục tiêu là kiểm tra interceptor; hãy có test tích hợp gửi metadata qua channel để xác nhận credential được xử lý ở đúng ranh giới.

## 7. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Trả `PERMISSION_DENIED` cho token hết hạn | Client không biết cần xác thực lại | Dùng `UNAUTHENTICATED` |
| Trả `UNAUTHENTICATED` khi user thiếu quyền | Client refresh token vô ích | Dùng `PERMISSION_DENIED` |
| Tin user/role/tenant trong request protobuf | Caller có thể giả danh | Lấy principal từ credential đã xác minh |
| Chỉ kiểm tra role, không kiểm tra tài nguyên/tenant | Truy cập chéo dữ liệu | Áp dụng policy theo action và resource |
| Log toàn bộ metadata | Token có thể bị lộ | Redact authorization và credential |
| Dùng Context như biến toàn cục | Danh tính có thể lẫn giữa RPC | Dùng Context theo call, không lưu mutable field |
| Retry vô hạn khi `UNAUTHENTICATED` | Vòng lặp refresh hoặc request | Giới hạn một lần refresh và số lần retry |
| Dùng TLS như thay thế authorization | Người dùng đã kết nối vẫn có thể truy cập trái phép | TLS bảo vệ đường truyền; policy vẫn phải kiểm tra quyền |

## 8. Tự luyện tập

1. Một token có chữ ký hợp lệ nhưng hết hạn. Vì sao server trả `UNAUTHENTICATED`, không phải `PERMISSION_DENIED`?
2. Một user đã đăng nhập nhưng chỉ có quyền đọc. Hãy thiết kế status và phản ứng client khi user gọi RPC xóa tài nguyên.
3. Vì sao tenant ID phải lấy từ principal đã xác thực thay vì tin field trong protobuf request?
4. Viết test chứng minh interceptor từ chối request không có bearer token trước khi gọi handler.
5. Nếu client nhận `UNAUTHENTICATED` sau một RPC tạo giao dịch, cần bảo đảm gì trước khi refresh token và gửi lại?

**Ghi nhớ:** `UNAUTHENTICATED` nghĩa là server không xác minh được danh tính từ credential; `PERMISSION_DENIED` nghĩa là danh tính hợp lệ nhưng không có quyền. Xác thực credential ở interceptor, gắn principal vào Context theo từng RPC, kiểm tra quyền theo hành động/tài nguyên/tenant và không tin identity do client tự khai báo. TLS bảo vệ credential trên đường truyền; authorization vẫn phải được thực hiện ở server.
