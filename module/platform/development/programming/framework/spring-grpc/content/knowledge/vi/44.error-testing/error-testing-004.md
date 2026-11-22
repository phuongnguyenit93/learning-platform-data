# Test UNAUTHENTICATED

Trong gRPC, **UNAUTHENTICATED** biểu thị server không xác minh được danh tính caller. Với Spring gRPC, lỗi này thường xuất hiện khi request thiếu credential, bearer token sai định dạng, chữ ký không hợp lệ, token hết hạn hoặc issuer/audience không được chấp nhận. Kiểm thử cần chứng minh server từ chối call trước khi service handler thực hiện nghiệp vụ.

Phân biệt UNAUTHENTICATED với PERMISSION_DENIED: trường hợp đầu tiên caller chưa có danh tính đã xác minh; trường hợp thứ hai caller đã được xác thực nhưng không có quyền thực hiện hành động. Bài này dùng RPC GetMyProfile, authentication interceptor, gRPC Context và generated blocking stub để kiểm tra các nhánh credential.

## 1. Authentication nằm trước authorization

Luồng xử lý bảo mật thường theo thứ tự:

1. Client gửi credential qua TLS, thường trong metadata authorization.
2. Server interceptor xác minh credential: chữ ký, issuer, audience, expiry và các claim bắt buộc.
3. Nếu hợp lệ, interceptor tạo principal đáng tin cậy và gắn vào gRPC Context.
4. Service handler đọc principal từ context.
5. Authorization policy kiểm tra quyền trên method/resource.
6. Chỉ khi đủ quyền, service mới truy cập dữ liệu hoặc thực hiện side effect.

| Tình huống | Status phù hợp |
| --- | --- |
| Không có bearer token | UNAUTHENTICATED |
| Authorization header sai scheme hoặc token rỗng | UNAUTHENTICATED |
| Token sai chữ ký, hết hạn hoặc sai issuer/audience | UNAUTHENTICATED |
| Token hợp lệ nhưng thiếu quyền đọc resource | PERMISSION_DENIED |
| Token hợp lệ, đủ quyền nhưng resource không tồn tại | NOT_FOUND |
| Token hợp lệ nhưng identity provider tạm không khả dụng | UNAVAILABLE hoặc lỗi hạ tầng tương ứng |

Không đổi lỗi identity provider thành UNAUTHENTICATED một cách tùy tiện. Credential không hợp lệ là lỗi danh tính; identity provider timeout là lỗi availability, có thể cần retry theo policy và deadline.

## 2. Đưa principal đã xác minh vào gRPC Context

Principal phải được tạo từ kết quả xác minh credential, không lấy subject hoặc role trực tiếp từ header do client tự khai.

~~~java
import java.util.Set;

public record AuthenticatedPrincipal(
    String subject,
    String tenantId,
    Set<String> authorities) {}
~~~

Khai báo context key dùng chung giữa interceptor và service:

~~~java
import io.grpc.Context;

public final class PrincipalContext {
    public static final Context.Key<AuthenticatedPrincipal> PRINCIPAL =
        Context.key("authenticated-principal");

    private PrincipalContext() {}
}
~~~

Verifier là abstraction của ứng dụng; implementation production có trách nhiệm kiểm tra chữ ký, issuer, audience, thời hạn và các claim theo policy:

~~~java
public interface TokenVerifier {
    AuthenticatedPrincipal verify(String token)
        throws InvalidTokenException, IdentityProviderUnavailableException;
}
~~~

Không ghi token hoặc toàn bộ claim nhạy cảm vào log. Nếu dùng JWT, không chỉ decode payload rồi tin nội dung; phải xác minh chữ ký và các claim cần thiết. Nếu dùng token introspection từ identity provider, đặt timeout và deadline rõ ràng.

## 3. Server interceptor từ chối credential không hợp lệ

Authentication interceptor kiểm tra metadata trước khi dispatch đến service:

~~~java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class BearerAuthenticationInterceptor
        implements ServerInterceptor {

    public static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of(
            "authorization",
            Metadata.ASCII_STRING_MARSHALLER);

    private final TokenVerifier tokenVerifier;

    public BearerAuthenticationInterceptor(
            TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AUTHORIZATION);
        if (authorization == null
                || !authorization.startsWith("Bearer ")) {
            return reject(call, "valid bearer credential is required");
        }

        String token = authorization.substring("Bearer ".length()).trim();
        if (token.isEmpty()) {
            return reject(call, "valid bearer credential is required");
        }

        final AuthenticatedPrincipal principal;
        try {
            principal = tokenVerifier.verify(token);
        } catch (InvalidTokenException ex) {
            return reject(call, "credential is invalid or expired");
        } catch (IdentityProviderUnavailableException ex) {
            call.close(
                Status.UNAVAILABLE.withDescription(
                    "identity provider is temporarily unavailable"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        Context context = Context.current().withValue(
            PrincipalContext.PRINCIPAL, principal);
        return Contexts.interceptCall(context, call, headers, next);
    }

    private <ReqT, RespT> ServerCall.Listener<ReqT> reject(
            ServerCall<ReqT, RespT> call,
            String description) {
        call.close(
            Status.UNAUTHENTICATED.withDescription(description),
            new Metadata());
        return new ServerCall.Listener<>() {};
    }
}
~~~

Interceptor không gọi next.startCall(...) khi credential không hợp lệ, vì vậy service handler không được thực thi. Mô tả lỗi không tiết lộ token sai ở điểm nào, chữ ký nào thất bại hoặc user có tồn tại hay không.

Nếu verifier thực hiện network call tới identity provider, không block transport/event-loop thread trong interceptor. Dùng cơ chế authentication bất đồng bộ phù hợp với server integration, hoặc xác minh token cục bộ bằng key đã cache. Khi provider lỗi, trả status availability tương ứng thay vì giả vờ caller gửi credential sai.

## 4. Service chỉ đọc principal đã xác minh

Ví dụ service đọc hồ sơ của caller:

~~~java
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public class ProfileGrpcService
        extends ProfileServiceGrpc.ProfileServiceImplBase {

    @Override
    public void getMyProfile(
            GetMyProfileRequest request,
            StreamObserver<GetMyProfileResponse> responseObserver) {

        AuthenticatedPrincipal principal =
            PrincipalContext.PRINCIPAL.get();
        if (principal == null) {
            responseObserver.onError(
                Status.UNAUTHENTICATED
                    .withDescription("authentication is required")
                    .asRuntimeException());
            return;
        }

        responseObserver.onNext(GetMyProfileResponse.newBuilder()
            .setSubject(principal.subject())
            .setTenantId(principal.tenantId())
            .build());
        responseObserver.onCompleted();
    }
}
~~~

Trong ứng dụng Spring, service thường nhận dependency qua constructor injection. Interceptor phải được đăng ký vào server trước khi call tới service. Chỉ khai báo interceptor thành Spring bean không đảm bảo starter tự động áp dụng nó; hãy dùng đúng cơ chế server interceptor registration/customizer của phiên bản starter đang chạy.

## 5. Kiểm thử bằng in-process gRPC server

In-process transport chạy server và client trong cùng JVM. Nó phù hợp để kiểm tra status mapping và chứng minh authentication interceptor chặn request trước service handler. Test interceptor/credential ở đây không xác minh TLS hoặc chữ ký JWT production; các phần đó cần integration test riêng.

Client test interceptor thêm bearer token:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

final class TestBearerTokenClientInterceptor
        implements ClientInterceptor {

    private final String token;

    TestBearerTokenClientInterceptor(String token) {
        this.token = token;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate =
            next.newCall(method, callOptions);

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(delegate) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                headers.put(
                    BearerAuthenticationInterceptor.AUTHORIZATION,
                    "Bearer " + token);
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

JUnit 5 test cho missing, invalid và valid token:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.ClientInterceptors;
import io.grpc.ManagedChannel;
import io.grpc.Server;
import io.grpc.ServerInterceptors;
import io.grpc.Status;
import io.grpc.StatusRuntimeException;
import io.grpc.inprocess.InProcessChannelBuilder;
import io.grpc.inprocess.InProcessServerBuilder;
import io.grpc.stub.StreamObserver;
import java.io.IOException;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ProfileAuthenticationTest {

    private Server server;
    private ManagedChannel channel;
    private AtomicInteger handlerCalls;

    @BeforeEach
    void setUp() throws IOException {
        String serverName = InProcessServerBuilder.generateName();
        handlerCalls = new AtomicInteger();

        TokenVerifier verifier = token -> {
            if ("valid-token".equals(token)) {
                return new AuthenticatedPrincipal(
                    "user-42", "tenant-a", Set.of("PROFILE_READ"));
            }
            throw new InvalidTokenException();
        };

        ProfileGrpcService service = new ProfileGrpcService() {
            @Override
            public void getMyProfile(
                    GetMyProfileRequest request,
                    StreamObserver<GetMyProfileResponse> observer) {
                handlerCalls.incrementAndGet();
                super.getMyProfile(request, observer);
            }
        };

        server = InProcessServerBuilder.forName(serverName)
            .directExecutor()
            .addService(ServerInterceptors.intercept(
                service,
                new BearerAuthenticationInterceptor(verifier)))
            .build()
            .start();

        channel = InProcessChannelBuilder.forName(serverName)
            .directExecutor()
            .build();
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
    void missingTokenReturnsUnauthenticatedBeforeHandler() {
        var stub = ProfileServiceGrpc.newBlockingStub(channel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getMyProfile(GetMyProfileRequest.getDefaultInstance()));

        assertEquals(
            Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
        assertEquals(0, handlerCalls.get());
    }

    @Test
    void invalidTokenReturnsUnauthenticatedBeforeHandler() {
        var authenticatedChannel = ClientInterceptors.intercept(
            channel,
            new TestBearerTokenClientInterceptor("invalid-token"));
        var stub = ProfileServiceGrpc.newBlockingStub(authenticatedChannel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);

        StatusRuntimeException error = assertThrows(
            StatusRuntimeException.class,
            () -> stub.getMyProfile(GetMyProfileRequest.getDefaultInstance()));

        assertEquals(
            Status.Code.UNAUTHENTICATED,
            error.getStatus().getCode());
        assertEquals(0, handlerCalls.get());
    }

    @Test
    void validTokenReachesHandlerWithVerifiedPrincipal() {
        var authenticatedChannel = ClientInterceptors.intercept(
            channel,
            new TestBearerTokenClientInterceptor("valid-token"));
        var stub = ProfileServiceGrpc.newBlockingStub(authenticatedChannel)
            .withDeadlineAfter(1, TimeUnit.SECONDS);

        GetMyProfileResponse response =
            stub.getMyProfile(GetMyProfileRequest.getDefaultInstance());

        assertEquals("user-42", response.getSubject());
        assertEquals("tenant-a", response.getTenantId());
        assertEquals(1, handlerCalls.get());
    }
}
~~~

Test giả định các kiểu InvalidTokenException, IdentityProviderUnavailableException, TokenVerifier, generated Protobuf classes và service base đã được khai báo như các ví dụ trước. Có thể dùng spy/mock thay cho subclass service nếu service implementation được giữ final. directExecutor() chỉ phù hợp với handler ngắn, không blocking; dùng executor riêng nếu test mô phỏng I/O.

## 6. Các assertion quan trọng

Một test UNAUTHENTICATED nên xác minh:

1. **Status code:** caller nhận đúng Status.Code.UNAUTHENTICATED.
2. **Handler không chạy:** counter hoặc mock verify cho thấy service không được gọi.
3. **Không có side effect:** repository, downstream và event publisher không được gọi.
4. **Credential không bị lộ:** description/log không chứa token hoặc chi tiết xác minh nhạy cảm.
5. **Valid credential vẫn hoạt động:** một test thành công chứng minh interceptor không từ chối mọi request.

Chỉ assert exception được ném ra chưa đủ. Nếu service handler vẫn chạy sau khi authentication thất bại, có thể đã xảy ra truy cập dữ liệu hoặc side effect trước khi lỗi được trả về.

## 7. Phân biệt authentication failure và authorization failure

Sau khi token được xác minh, authorization mới quyết định quyền trên resource:

| Credential | Quyền | Kết quả |
| --- | --- | --- |
| Thiếu/sai/hết hạn | Chưa thể đánh giá | UNAUTHENTICATED |
| Hợp lệ | Không có quyền | PERMISSION_DENIED |
| Hợp lệ | Có quyền, resource thiếu | NOT_FOUND |
| Hợp lệ | Có quyền, resource hợp lệ | Thành công |

Không đưa UNAUTHENTICATED vào retry policy chung. Caller cần lấy credential mới hoặc sửa cấu hình identity. Retry cùng token hết hạn không làm nó hợp lệ.

Nếu identity provider tạm thời không khả dụng, phân biệt lỗi này với token invalid. Có thể trả UNAVAILABLE và retry có giới hạn nếu deadline còn đủ; không đánh dấu token của mọi caller là sai chỉ vì verifier đang gặp sự cố.

## 8. Bảo mật metadata và TLS

Bearer token thường được truyền trong metadata key authorization. Metadata không tự mã hóa dữ liệu; chỉ gửi credential qua TLS với certificate/hostname được xác minh. Không dùng plaintext hoặc trust-all để làm test pass.

Các nguyên tắc:

- Chỉ chấp nhận scheme được quy định, ví dụ Bearer.
- Xác minh chữ ký, issuer, audience, expiry và claim bắt buộc.
- Không tin x-user-id, x-role hoặc tenant-id do client tự khai làm principal.
- Không ghi token, authorization header hoặc secret vào log/tracing.
- Không trả chi tiết như user không tồn tại hoặc chữ ký sai ở byte nào cho caller.
- Giới hạn kích thước metadata và thời gian xác minh credential.

Nếu dùng mTLS, certificate có thể cung cấp workload identity ở tầng transport. Ứng dụng vẫn cần ánh xạ identity đó sang principal và policy; TLS handshake thành công tự nó không đồng nghĩa caller có quyền nghiệp vụ.

## 9. Tích hợp authentication interceptor trong Spring

Có thể quản lý verifier và interceptor bằng Spring bean:

~~~java
@Configuration
public class GrpcAuthenticationConfiguration {

    @Bean
    BearerAuthenticationInterceptor bearerAuthenticationInterceptor(
            TokenVerifier tokenVerifier) {
        return new BearerAuthenticationInterceptor(tokenVerifier);
    }
}
~~~

Bean này cần được đăng ký vào gRPC server bằng extension point tương ứng của starter đang sử dụng. Một số starter cung cấp server interceptor customizer hoặc danh sách interceptor; API và thứ tự thực thi thay đổi theo phiên bản. Xác minh rằng authentication interceptor chạy trước service handler và trước các interceptor nghiệp vụ cần principal.

Trong integration test Spring, khởi động application context và gọi server qua channel thực tế để chứng minh interceptor được gắn. In-process unit test chỉ xác minh logic interceptor/service khi test tự lắp chúng với nhau.

## 10. Ma trận kiểm thử đề xuất

| Kịch bản | Status mong đợi | Handler |
| --- | --- | --- |
| Không có authorization header | UNAUTHENTICATED | Không chạy |
| Sai scheme hoặc token rỗng | UNAUTHENTICATED | Không chạy |
| Token sai chữ ký/hết hạn | UNAUTHENTICATED | Không chạy |
| Token hợp lệ | Thành công hoặc đi tiếp authorization | Chạy |
| Token hợp lệ nhưng thiếu quyền | PERMISSION_DENIED | Chạy tới authorization, không chạy nghiệp vụ bị cấm |
| Identity provider timeout | UNAVAILABLE hoặc status hạ tầng đã quy định | Không chạy nghiệp vụ |
| Token giả mạo trong metadata phụ | Không nâng được principal | Theo credential thật |

Kiểm thử authentication production cần bao gồm TLS, verifier thực hoặc test identity provider, issuer/audience/expiry và interceptor registration. Không dùng fake verifier để tuyên bố đã xác minh chữ ký JWT hoặc cấu hình TLS.

## 11. Ghi nhớ và tự kiểm tra

**Test UNAUTHENTICATED** phải chứng minh credential thiếu hoặc không hợp lệ bị từ chối trước service handler, status trả về chính xác và không có side effect. Dùng server interceptor để xác minh bearer token, gắn principal đã xác minh vào gRPC Context, và kiểm thử bằng in-process server cùng generated blocking stub. Bổ sung Spring integration test cho wiring thực tế và TLS/identity provider theo môi trường triển khai.

Tự kiểm tra:

1. Vì sao UNAUTHENTICATED khác PERMISSION_DENIED?
2. Những claim nào cần xác minh khi dùng JWT?
3. Vì sao không được lấy principal từ metadata tùy ý do client gửi?
4. Làm thế nào chứng minh service handler không chạy khi token thiếu?
5. Vì sao identity provider timeout không nên bị ánh xạ thành token invalid?
6. In-process test không chứng minh được những phần nào của authentication production?

Kiểm thử authentication đúng giúp Spring gRPC chỉ đưa request có danh tính đã xác minh vào service, giữ authorization tách biệt và ngăn truy cập nghiệp vụ khi credential không hợp lệ.
