# UNAUTHENTICATED do metadata thiếu

Trong **SPRING_GRPC**, client thường gửi thông tin xác thực trong gRPC Metadata, phổ biến nhất là header authorization chứa Bearer access token. Server interceptor đọc header, xác minh token và chỉ cho phép request đi tiếp khi credential hợp lệ. Nếu metadata không được gửi, dùng sai key/format hoặc bị mất trên đường truyền, server có thể trả UNAUTHENTICATED.

Khi xử lý lỗi này, cần lần theo toàn bộ đường đi của credential: token provider ở client, cơ chế gắn metadata vào từng RPC, channel/stub thực tế được gọi, server interceptor và proxy/gateway ở giữa. Bài này tập trung vào lỗi thiếu authentication metadata trong Spring gRPC, cách phân biệt với lỗi phân quyền và cách kiểm thử cả trường hợp thiếu lẫn hợp lệ.

## 1. Authentication metadata trong gRPC

gRPC Metadata là tập key-value đi cùng RPC dưới dạng HTTP/2 headers hoặc trailers. Authentication metadata thường được gửi ở request headers:

```text
authorization: Bearer <access-token>
```

Tên metadata key phải viết thường ASCII. Dùng key authorization và Metadata.ASCII_STRING_MARSHALLER cho Bearer token dạng text:

```java
public final class GrpcAuthMetadata {

    private GrpcAuthMetadata() {
    }

    public static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of(
                    "authorization",
                    Metadata.ASCII_STRING_MARSHALLER);
}
```

Metadata key là một phần của transport contract. Những lỗi như dùng key tùy chỉnh auth-token trong khi server chỉ đọc authorization, dùng binary marshaller sai loại hoặc không gắn header vào RPC thực tế đều có thể khiến server coi credential là thiếu.

Không gửi token trong protobuf request body. Dùng authentication metadata và bảo vệ kết nối bằng TLS để credential không bị đọc trên đường truyền.

## 2. Phân biệt UNAUTHENTICATED và PERMISSION_DENIED

Hai status này biểu thị hai giai đoạn khác nhau:

| Status | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| UNAUTHENTICATED | Server không xác minh được danh tính caller | Thiếu token, token sai chữ ký, hết hạn hoặc sai định dạng |
| PERMISSION_DENIED | Caller đã được xác thực nhưng không có quyền thực hiện hành động | Principal hợp lệ nhưng không có quyền inventory:reserve |

Nếu thiếu authentication metadata, server không có đủ credential để xác minh danh tính nên thường trả UNAUTHENTICATED. Không trả PERMISSION_DENIED cho trường hợp này vì client chưa vượt qua bước authentication.

Ngược lại, không dùng UNAUTHENTICATED để che mọi lỗi authorization. Khi token hợp lệ nhưng principal không được phép gọi method, trả PERMISSION_DENIED. Giữ semantics nhất quán giúp client biết khi nào cần đăng nhập/làm mới credential và khi nào cần yêu cầu quyền.

## 3. Các nguyên nhân khiến metadata bị thiếu

| Nguyên nhân | Dấu hiệu | Cách kiểm tra |
| --- | --- | --- |
| Client không gắn credential | Mọi RPC từ client đều thiếu header | Kiểm tra CallCredentials hoặc client interceptor |
| Gắn header vào channel/stub khác | Một số call có token, call khác không | Kiểm tra stub thực tế được dùng để gọi |
| Sai metadata key | Client gửi auth-token, server đọc authorization | Chuẩn hóa key dùng chung |
| Sai format | Header không có tiền tố Bearer | Kiểm tra format trước khi gọi |
| Token provider trả rỗng/hết hạn | Lỗi xuất hiện sau refresh hoặc khi token cache hết hạn | Kiểm tra lifecycle token, không log giá trị token |
| Server interceptor chưa đăng ký | Service vẫn chạy mà không có bước xác thực mong đợi | Kiểm tra interceptor registration |
| Proxy/gateway loại bỏ header | Client gửi đúng nhưng server không nhận | Kiểm tra allowlist request headers trên proxy |
| Downstream RPC không gắn credential | Request đầu vào có auth nhưng call tiếp theo thiếu | Cấu hình credential riêng cho downstream |

Không kết luận server có lỗi chỉ từ status. Xác nhận client đã gửi metadata, server interceptor đã chạy và request tới đúng backend trước khi thay đổi authentication policy.

## 4. Gắn token ở client bằng CallCredentials

CallCredentials phù hợp để gắn credential theo từng RPC. Nó cho phép lấy token mới từ provider, thay vì giữ một token cố định trong metadata của channel.

```java
import io.grpc.CallCredentials;
import io.grpc.Metadata;
import io.grpc.Status;

import java.util.concurrent.Executor;

public final class BearerTokenCredentials extends CallCredentials {

    private final AccessTokenProvider tokenProvider;

    public BearerTokenCredentials(AccessTokenProvider tokenProvider) {
        this.tokenProvider = tokenProvider;
    }

    @Override
    public void applyRequestMetadata(
            RequestInfo requestInfo,
            Executor appExecutor,
            MetadataApplier applier) {

        appExecutor.execute(() -> {
            try {
                String token = tokenProvider.currentAccessToken();

                if (token == null || token.isBlank()) {
                    applier.fail(Status.UNAUTHENTICATED
                            .withDescription("Authentication credentials unavailable"));
                    return;
                }

                Metadata headers = new Metadata();
                headers.put(
                        GrpcAuthMetadata.AUTHORIZATION,
                        "Bearer " + token);

                applier.apply(headers);
            } catch (CredentialUnavailableException error) {
                applier.fail(Status.UNAVAILABLE
                        .withDescription("Credential provider unavailable"));
            } catch (RuntimeException error) {
                applier.fail(Status.UNAUTHENTICATED
                        .withDescription("Authentication credentials unavailable"));
            }
        });
    }
}
```

AccessTokenProvider nên trả token còn hiệu lực từ cache hoặc refresh theo cơ chế bảo mật của ứng dụng. Không thực hiện network refresh blocking tùy tiện trên thread gọi RPC; dùng executor và timeout phù hợp. Nếu token provider tạm thời không truy cập được, UNAVAILABLE phản ánh lỗi dependency tốt hơn việc giả định token của caller không hợp lệ.

Gắn credentials vào stub:

```java
ManagedChannel channel = ManagedChannelBuilder
        .forTarget("inventory.internal:9090")
        .useTransportSecurity()
        .build();

CatalogServiceGrpc.CatalogServiceBlockingStub client =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withCallCredentials(
                        new BearerTokenCredentials(tokenProvider));
```

withCallCredentials trả về stub mới. Hãy dùng đúng stub đã gắn credentials khi gọi RPC; nếu giữ lại stub cũ rồi gọi qua nó, metadata sẽ không được thêm.

Các API CallCredentials có thể khác chi tiết theo phiên bản grpc-java. Dùng cùng phiên bản thư viện với Spring gRPC runtime và kiểm tra chữ ký API trong dependency đang build.

## 5. Client interceptor và metadata tĩnh

Một client interceptor cũng có thể gắn metadata:

```java
public final class StaticAuthInterceptor
        implements ClientInterceptor {

    private final String token;

    public StaticAuthInterceptor(String token) {
        this.token = token;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall
                .SimpleForwardingClientCall<>(
                        next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata headers) {
                headers.put(
                        GrpcAuthMetadata.AUTHORIZATION,
                        "Bearer " + token);
                super.start(listener, headers);
            }
        };
    }
}
```

Cách này có thể hữu ích cho integration test hoặc credential cố định trong môi trường nội bộ. Với access token ngắn hạn, multi-user hoặc token cần refresh, không nên giữ token trong field interceptor lâu dài: token có thể hết hạn và nhiều caller có thể vô tình dùng chung credential. Ưu tiên CallCredentials hoặc cơ chế security integration phù hợp.

Không ghi token vào log khi debug interceptor. Chỉ log việc metadata có được gắn hay không và RPC method cần thiết; redact toàn bộ giá trị authorization.

## 6. Server interceptor xác minh Bearer token

Server interceptor đọc metadata trước khi gọi service implementation. Ví dụ dưới đây dùng một TokenVerifier để xác minh chữ ký, issuer, audience và expiry; chi tiết xác minh phụ thuộc hệ thống identity provider.

```java
public final class AuthenticationInterceptor
        implements ServerInterceptor {

    public static final Context.Key<AuthenticatedPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private final TokenVerifier tokenVerifier;

    public AuthenticationInterceptor(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization =
                headers.get(GrpcAuthMetadata.AUTHORIZATION);

        if (authorization == null
                || !authorization.startsWith("Bearer ")
                || authorization.length() <= "Bearer ".length()) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }

        String token = authorization.substring("Bearer ".length());

        try {
            AuthenticatedPrincipal principal =
                    tokenVerifier.verify(token);

            Context context = Context.current()
                    .withValue(PRINCIPAL, principal);

            return Contexts.interceptCall(
                    context, call, headers, next);
        } catch (InvalidCredentialException error) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Invalid authentication credentials"),
                    new Metadata());
            return new ServerCall.Listener<>() {};
        }
    }
}
```

Interceptor chỉ gọi next sau khi xác minh thành công. Khi metadata thiếu hoặc credential sai, call được đóng bằng status UNAUTHENTICATED; service implementation không được chạy.

Principal nên là object bất biến, chỉ chứa claims cần thiết. Không lưu raw token vào Context, không đưa token vào exception hoặc log. Application use case nên nhận principal/actor đã xác minh qua application context hoặc tham số rõ ràng, thay vì phụ thuộc trực tiếp vào gRPC API.

## 7. Đăng ký interceptor trong Spring gRPC

Có interceptor đúng class nhưng không đăng ký vào server thì authentication không chạy. Với Spring gRPC, hãy dùng cơ chế server interceptor registration mà phiên bản dependency của dự án hỗ trợ.

Kiểm tra:

- AuthenticationInterceptor được tạo thành Spring bean.
- Bean được đăng ký global hoặc theo service theo đúng policy.
- Interceptor áp dụng cho đúng gRPC server và port.
- Không có profile/condition khiến interceptor bị loại ở môi trường đang chạy.
- Interceptor authentication chạy trước adapter logic cần principal.
- Không có cấu hình khác vô tình thay thế hoặc bỏ qua interceptor.

Nếu chỉ bảo vệ một nhóm service, đăng ký theo phạm vi đó và kiểm tra từng service/method. Nếu mọi RPC đều cần authentication, dùng global policy và chỉ loại trừ health/reflection endpoint theo quy định rõ ràng. Đừng để một service nhạy cảm không có interceptor chỉ vì nó nằm ngoài package scan.

Tên annotation/cơ chế đăng ký interceptor có thể khác giữa các dòng Spring gRPC và starter. Tra cứu đúng phiên bản dependency của ứng dụng; không sao chép annotation từ một starter khác mà chưa xác minh.

## 8. TLS bảo vệ credential trên đường truyền

Bearer token là credential có thể được sử dụng lại cho đến khi hết hạn hoặc bị thu hồi. Vì vậy, gửi token qua plaintext transport có thể làm lộ danh tính caller.

Client production nên cấu hình TLS:

- Dùng useTransportSecurity hoặc TLS configuration tương ứng.
- Xác minh server certificate và hostname.
- Dùng CA trust phù hợp; không tắt certificate validation để “sửa” lỗi authentication.
- Với mTLS, quản lý client certificate/key riêng và xác định rõ cách kết hợp certificate identity với Bearer token.
- Không đặt token trong URL, log, protobuf payload hoặc exception message.

TLS bảo vệ dữ liệu trên đường truyền; nó không thay thế token validation hoặc authorization. Server vẫn phải xác minh issuer, signature, audience, expiry và claims theo policy.

## 9. Metadata khi gọi downstream service

Metadata inbound không tự động được chuyển sang một gRPC call outbound. Nếu service nhận request đã xác thực rồi gọi service khác, cần quyết định rõ danh tính nào được dùng ở downstream:

1. **Service identity**: downstream xác thực chính service hiện tại bằng credential của workload.
2. **Delegated user identity**: service chuyển tiếp danh tính caller theo cơ chế token exchange/delegation được thiết kế.
3. **On-behalf-of token**: identity provider cấp token mới có audience và scope dành riêng cho downstream.

Không sao chép toàn bộ inbound metadata sang downstream một cách mù quáng. Raw token có thể không hợp audience, scope hoặc trust boundary. Không forward authorization nếu downstream cần service identity riêng. Mỗi downstream client phải gắn credential theo policy và endpoint của nó.

Nếu server interceptor đưa principal vào gRPC Context, Context đó chỉ là trạng thái trong process. Khi gọi downstream, adapter/client cần chủ động chuyển thông tin được phép thành credential hoặc metadata mới.

## 10. Test server interceptor khi metadata thiếu

Có thể kiểm thử server interceptor qua in-process transport. Tạo một service đơn giản và bảo vệ nó bằng interceptor:

```java
ServerServiceDefinition protectedService =
        ServerInterceptors.intercept(
                new CatalogGrpcService(getItemUseCase, mapper),
                authenticationInterceptor);

Server server = InProcessServerBuilder
        .forName(serverName)
        .directExecutor()
        .addService(protectedService)
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();

try {
    CatalogServiceGrpc.CatalogServiceBlockingStub client =
            CatalogServiceGrpc.newBlockingStub(channel);

    StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> client.getItem(
                    GetItemRequest.newBuilder()
                            .setItemId("item-42")
                            .build()));

    assertEquals(
            Status.Code.UNAUTHENTICATED,
            Status.fromThrowable(error).getCode());
} finally {
    channel.shutdownNow();
    server.shutdownNow();
    channel.awaitTermination(2, TimeUnit.SECONDS);
    server.awaitTermination(2, TimeUnit.SECONDS);
}
```

Test này chứng minh khi client không gắn metadata, interceptor chặn call trước service. Có thể bổ sung assertion rằng getItemUseCase không được gọi để chắc chắn request không lọt vào application layer.

## 11. Test credential hợp lệ và token sai

Positive test dùng credential giả lập hợp lệ:

```java
CatalogServiceGrpc.CatalogServiceBlockingStub authenticatedClient =
        CatalogServiceGrpc.newBlockingStub(channel)
                .withCallCredentials(
                        new TestBearerCredentials("valid-test-token"));

GetItemReply reply = authenticatedClient.getItem(
        GetItemRequest.newBuilder()
                .setItemId("item-42")
                .build());

assertEquals("item-42", reply.getItemId());
verify(tokenVerifier).verify("valid-test-token");
```

TestBearerCredentials có thể là implementation nhỏ của CallCredentials chỉ gắn token test vào authorization. Không dùng token production trong test.

Bổ sung negative cases:

- Không có header → UNAUTHENTICATED.
- Header không có Bearer prefix hoặc token rỗng → UNAUTHENTICATED.
- Token hết hạn/sai chữ ký/sai issuer → UNAUTHENTICATED.
- Token hợp lệ nhưng thiếu scope/role → PERMISSION_DENIED.
- Token provider tạm thời không truy cập được → status phản ánh lỗi dependency, thường UNAVAILABLE.

Kiểm tra verifier không được gọi khi header thiếu hoặc sai cấu trúc. Với token hợp lệ nhưng thiếu quyền, authentication interceptor có thể đặt principal vào Context; authorization policy ở interceptor/use case sẽ trả PERMISSION_DENIED.

## 12. Trình tự troubleshooting khi nhận UNAUTHENTICATED

Đi theo thứ tự để khoanh vùng nơi metadata bị thiếu:

1. Xác nhận RPC đang gọi đúng channel và endpoint.
2. Kiểm tra client stub thực tế có gắn CallCredentials hoặc interceptor không.
3. Xác nhận token provider trả token không rỗng và còn hiệu lực, không ghi token ra log.
4. Kiểm tra metadata key là authorization và format là Bearer <token>.
5. Xác nhận interceptor được đăng ký trên đúng server/service.
6. Kiểm tra server có nhận header hay không bằng instrumentation an toàn chỉ ghi trạng thái present/absent.
7. Nếu qua proxy/gateway, kiểm tra allowlist request headers và chính sách forward authorization.
8. Xác minh token issuer, audience, signature, expiry và clock skew.
9. Nếu lỗi ở downstream, kiểm tra outbound client có credential riêng hay chưa.
10. Chạy in-process test thiếu token, token hợp lệ và token sai để xác định behavior mong đợi.

Không log giá trị token hoặc dump toàn bộ metadata để chẩn đoán. Dùng request ID, RPC method, status code và cờ authorization_present để theo dõi.

## 13. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng key auth-token trong client nhưng server đọc authorization | Server coi credential là thiếu | Dùng metadata key thống nhất |
| Gắn credential vào stub khác | RPC thực tế không có header | Gọi bằng stub trả về từ withCallCredentials |
| Giữ token tĩnh lâu dài | Token hết hạn nhưng interceptor vẫn gửi token cũ | Token provider và CallCredentials theo từng RPC |
| Interceptor chưa đăng ký | Không có bước authentication mong đợi | Kiểm tra server registration và startup config |
| Sai Bearer prefix | Server không parse được credential | Chuẩn hóa format |
| Proxy loại bỏ authorization | Client gửi nhưng server không nhận | Cấu hình allowlist/forward header có kiểm soát |
| Forward raw token sang downstream | Sai audience hoặc vượt trust boundary | Service identity hoặc token exchange |
| Ghi token vào log | Lộ credential có thể tái sử dụng | Redact hoàn toàn giá trị header |
| Dùng PERMISSION_DENIED khi thiếu token | Client nhận sai semantics | Trả UNAUTHENTICATED |
| Tắt TLS để thử nhanh | Credential có thể lộ trên mạng | Dùng test token và TLS test configuration |

## 14. Bài tập thực hành

1. Khai báo Metadata.Key<String> cho authorization với ASCII marshaller.
2. Viết BearerTokenCredentials gắn token theo từng RPC.
3. Tạo ServerInterceptor kiểm tra Bearer prefix và xác minh token.
4. Đặt principal đã xác thực vào gRPC Context, không lưu raw token.
5. Đăng ký interceptor trong Spring gRPC server và xác minh bean được tạo.
6. Viết in-process test không có metadata và assert UNAUTHENTICATED.
7. Viết positive test với token hợp lệ và xác nhận use case được gọi.
8. Viết test token sai/hết hạn và test principal hợp lệ nhưng thiếu quyền trả PERMISSION_DENIED.
9. Kiểm tra downstream call dùng service credential hoặc delegated token đúng policy.
10. Xác minh TLS được bật và log không chứa authorization value.

### Ghi nhớ

**UNAUTHENTICATED do metadata thiếu thường nằm ở đường đi credential giữa client và server.** Kiểm tra CallCredentials/interceptor, đúng stub, key authorization, Bearer format, server interceptor registration và proxy forwarding. Phân biệt credential thiếu/sai với principal hợp lệ nhưng thiếu quyền; bảo vệ token bằng TLS, không log secret và kiểm chứng bằng in-process tests cho cả negative lẫn positive path.

## Tài liệu tham khảo

- [gRPC — Authentication](https://grpc.io/docs/guides/auth/)
- [gRPC — Metadata](https://grpc.io/docs/guides/metadata/)
- [gRPC Java — CallCredentials](https://grpc.github.io/grpc-java/javadoc/io/grpc/CallCredentials.html)
- [gRPC Java — ServerInterceptor](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerInterceptor.html)
- [gRPC Java — Metadata](https://grpc.github.io/grpc-java/javadoc/io/grpc/Metadata.html)
- [Spring gRPC — Server](https://docs.spring.io/spring-grpc/reference/server.html)
