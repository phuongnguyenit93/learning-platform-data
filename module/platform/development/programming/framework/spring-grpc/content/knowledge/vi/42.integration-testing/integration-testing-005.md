# Kiểm thử auth metadata

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích metadata được gửi cùng gRPC call và phân biệt metadata với Protobuf payload.
- Định nghĩa metadata key đúng quy tắc tên và marshaller.
- Kiểm thử xác thực ở server bằng **ServerInterceptor**.
- Gửi bearer token từ client bằng **ClientInterceptor**.
- Xác minh status **UNAUTHENTICATED** cho credential thiếu/sai và phân biệt với **PERMISSION_DENIED**.
- Tích hợp interceptor vào server Spring gRPC mà không tạo thêm server ngoài ý muốn.
- Kiểm thử cả đường thành công, thất bại và bảo đảm credential được bảo vệ bằng TLS.

## 1. Auth metadata nằm ở đâu trong một gRPC call?

gRPC metadata là tập key-value đi kèm call, được truyền qua HTTP/2 headers/trailers. Metadata thường mang thông tin điều khiển hoặc ngữ cảnh như bearer token, trace ID, tenant ID và correlation ID. Dữ liệu nghiệp vụ của request/response vẫn nằm trong Protobuf message.

Trong **SPRING_GRPC**, authentication thường được thực hiện ở interceptor trước khi request đi vào service method. Interceptor đọc metadata, xác minh credential và quyết định cho phép call tiếp tục hay kết thúc bằng status. Cách này giúp nhiều service áp dụng cùng một policy và tránh lặp logic xác thực trong từng method.

Metadata không tự mã hóa dữ liệu. Bearer token gửi qua metadata vẫn cần TLS để bảo vệ trên đường truyền. Một test dùng plaintext loopback có thể kiểm tra interceptor và status, nhưng không chứng minh credential được bảo vệ trên mạng; TLS cần được kiểm thử riêng.

## 2. Quy tắc đặt metadata key

Metadata key có tên chữ thường theo quy ước gRPC. Key chứa chuỗi ASCII dùng **Metadata.ASCII_STRING_MARSHALLER**; key mang binary data có hậu tố **-bin** và dùng marshaller nhị phân tương ứng.

Ví dụ định nghĩa key authorization:

~~~java
final class AuthMetadata {
    static final Metadata.Key<String> AUTHORIZATION =
        Metadata.Key.of(
            "authorization",
            Metadata.ASCII_STRING_MARSHALLER);

    private AuthMetadata() {}
}
~~~

Không dùng tiền tố dành riêng **grpc-** cho metadata ứng dụng. Tránh đưa payload lớn vào metadata vì header có giới hạn kích thước và metadata được xử lý trên mọi call. Token, tenant hoặc trace ID nên ngắn và có định dạng rõ ràng.

## 3. ServerInterceptor kiểm tra bearer token

**ServerInterceptor** chạy trước service handler. Nếu credential không hợp lệ, interceptor đóng call bằng **UNAUTHENTICATED** và không gọi **next.startCall**, do đó method nghiệp vụ không được thực thi.

Ví dụ dưới đây dùng token cố định chỉ để minh họa test:

~~~java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

final class AuthServerInterceptor implements ServerInterceptor {
    private final TokenVerifier tokenVerifier;

    AuthServerInterceptor(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AuthMetadata.AUTHORIZATION);
        if (authorization == null
                || !authorization.startsWith("Bearer ")) {
            call.close(
                Status.UNAUTHENTICATED
                    .withDescription("Authentication required"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        String token = authorization.substring("Bearer ".length());
        if (!tokenVerifier.isValid(token)) {
            call.close(
                Status.UNAUTHENTICATED
                    .withDescription("Invalid credentials"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

**TokenVerifier** đại diện cho thành phần xác minh chữ ký, issuer, audience, expiry và các claim của token. Không nên chỉ kiểm tra chuỗi token bằng phép so sánh trong production. Không ghi token vào log hoặc trả token/chi tiết xác minh nội bộ trong status description.

**UNAUTHENTICATED** có nghĩa caller chưa được xác thực hoặc credential không hợp lệ. Nếu caller đã được xác thực nhưng thiếu quyền thực hiện một hành động, dùng **PERMISSION_DENIED**.

## 4. ClientInterceptor gắn metadata vào call

Client có thể gắn authorization metadata bằng một **ClientInterceptor**. Interceptor nhận **Metadata** riêng của call và thêm bearer token trước khi call được gửi:

~~~java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

final class BearerTokenClientInterceptor implements ClientInterceptor {
    private final String token;

    BearerTokenClientInterceptor(String token) {
        this.token = token;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall
                .SimpleForwardingClientCall<ReqT, RespT>(
                    next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata headers) {
                headers.put(
                    AuthMetadata.AUTHORIZATION,
                    "Bearer " + token);
                super.start(responseListener, headers);
            }
        };
    }
}
~~~

Trong ứng dụng thực, token nên đến từ credential provider có vòng đời phù hợp, chẳng hạn cơ chế refresh token hoặc **CallCredentials**, thay vì hard-code trong stub. Interceptor trên chỉ là test fixture nhỏ để chứng minh metadata được gửi trên mỗi call.

Không dùng một **Metadata** mutable toàn cục rồi chia sẻ giữa nhiều call. Tạo/gắn header trên metadata của từng call để tránh rò token giữa request, đặc biệt khi nhiều tenant hoặc user dùng chung channel.

## 5. Đăng ký interceptor vào Spring gRPC server

Có hai trường hợp cần phân biệt:

- Nếu Spring gRPC starter tự khởi động server và tự đăng ký service bean, hãy cấu hình server interceptor theo đúng extension point của starter/phiên bản đang dùng.
- Nếu test tự sở hữu server, có thể đăng ký interceptor trực tiếp trên **NettyServerBuilder**.

Ví dụ fixture test tự quản lý server:

~~~java
final class AuthTestGrpcServer implements SmartLifecycle {
    private final BindableService service;
    private final ServerInterceptor authInterceptor;
    private volatile Server server;

    AuthTestGrpcServer(
            BindableService service,
            ServerInterceptor authInterceptor) {
        this.service = service;
        this.authInterceptor = authInterceptor;
    }

    @Override
    public synchronized void start() {
        if (server != null && !server.isShutdown()) {
            return;
        }

        try {
            NettyServerBuilder builder = NettyServerBuilder.forPort(0);
            builder.intercept(authInterceptor);
            builder.addService(service);
            server = builder.build().start();
        } catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot start authenticated gRPC test server", ex);
        }
    }

    int port() {
        Server current = server;
        if (current == null || current.isShutdown()) {
            throw new IllegalStateException("gRPC server is not running");
        }
        return current.getPort();
    }

    @Override
    public synchronized void stop() {
        Server current = server;
        server = null;
        if (current == null) {
            return;
        }
        current.shutdown();
        try {
            if (!current.awaitTermination(5, TimeUnit.SECONDS)) {
                current.shutdownNow();
            }
        } catch (InterruptedException ex) {
            current.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public boolean isRunning() {
        Server current = server;
        return current != null && !current.isShutdown();
    }
}
~~~

Fixture bind port **0** để hệ điều hành cấp port động. Spring quản lý **SmartLifecycle**: server start cùng context và stop khi context đóng. Nếu starter đã quản lý server, không tạo fixture thứ hai cho cùng service; thay vào đó kiểm thử interceptor trên server của starter bằng cấu hình đăng ký chính thức.

## 6. Đăng ký test bean và tạo client channel

Test configuration tạo service, token verifier, interceptor và server fixture:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class AuthGrpcTestConfiguration {
    @Bean
    TokenVerifier tokenVerifier() {
        return token -> "integration-test-token".equals(token);
    }

    @Bean
    AuthServerInterceptor authServerInterceptor(TokenVerifier verifier) {
        return new AuthServerInterceptor(verifier);
    }

    @Bean
    AuthTestGrpcServer authTestGrpcServer(
            GreeterServiceImpl greeter,
            AuthServerInterceptor interceptor) {
        return new AuthTestGrpcServer(greeter, interceptor);
    }
}
~~~

**GreeterServiceImpl** là service bean minh họa; thay bằng implementation generated base class của dự án. Nếu production starter đã khởi động server, cấu hình test cần dùng interceptor bean trên server đó thay vì import **AuthTestGrpcServer**.

Test tạo channel sau khi Spring refresh context:

~~~java
@SpringBootTest
@Import(AuthGrpcTestConfiguration.class)
class AuthMetadataIntegrationTest {
    @Autowired
    AuthTestGrpcServer grpcServer;

    private ManagedChannel channel;
    private GreeterGrpc.GreeterBlockingStub stub;

    @BeforeEach
    void connect() {
        channel = ManagedChannelBuilder
            .forAddress("127.0.0.1", grpcServer.port())
            .usePlaintext()
            .build();

        stub = GreeterGrpc.newBlockingStub(channel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);
    }

    @AfterEach
    void closeChannel() throws InterruptedException {
        if (channel == null) {
            return;
        }
        channel.shutdown();
        if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
            channel.shutdownNow();
        }
    }
}
~~~

Plaintext ở đây chỉ dành cho test loopback nhằm tập trung vào logic interceptor. Trong môi trường thật, bearer token phải được gửi qua TLS; không triển khai authentication metadata trên kết nối plaintext không tin cậy.

## 7. Kiểm thử thiếu metadata và token không hợp lệ

Stub không gắn interceptor sẽ gửi call không có authorization metadata. Server phải kết thúc bằng **UNAUTHENTICATED**:

~~~java
@Test
void rejectsCallWithoutAuthorizationMetadata() {
    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> stub.sayHello(
            HelloRequest.newBuilder().setName("Mai").build()));

    assertEquals(
        Status.Code.UNAUTHENTICATED,
        Status.fromThrowable(error).getCode());
}
~~~

Có thể tạo stub gắn token sai:

~~~java
Channel invalidAuthChannel = ClientInterceptors.intercept(
    channel,
    new BearerTokenClientInterceptor("wrong-token"));

GreeterGrpc.GreeterBlockingStub invalidStub =
    GreeterGrpc.newBlockingStub(invalidAuthChannel)
        .withDeadlineAfter(2, TimeUnit.SECONDS);

StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> invalidStub.sayHello(
        HelloRequest.newBuilder().setName("Mai").build()));

assertEquals(Status.Code.UNAUTHENTICATED,
    Status.fromThrowable(error).getCode());
~~~

Test nên kiểm tra thêm service method không được gọi khi interceptor từ chối call, ví dụ dùng spy hoặc counter. Như vậy test chứng minh authentication được thực thi trước business handler, thay vì chỉ kiểm tra client nhận một lỗi bất kỳ.

## 8. Kiểm thử token hợp lệ

Gắn interceptor client với token test hợp lệ rồi gọi cùng server:

~~~java
@Test
void acceptsValidBearerMetadata() {
    Channel authenticatedChannel = ClientInterceptors.intercept(
        channel,
        new BearerTokenClientInterceptor("integration-test-token"));

    GreeterGrpc.GreeterBlockingStub authenticatedStub =
        GreeterGrpc.newBlockingStub(authenticatedChannel)
            .withDeadlineAfter(2, TimeUnit.SECONDS);

    HelloReply reply = authenticatedStub.sayHello(
        HelloRequest.newBuilder().setName("Mai").build());

    assertEquals("Hello, Mai", reply.getMessage());
}
~~~

Channel gốc vẫn là tài nguyên cần đóng; **ClientInterceptors.intercept** tạo channel wrapper, không tạo một kết nối vật lý độc lập cần shutdown riêng. Không đóng channel trong lúc RPC khác còn đang sử dụng.

Nếu interceptor xác thực thành công rồi gắn principal vào gRPC **Context**, service có thể đọc identity từ context. Khi đó nên có test xác nhận principal đúng được truyền tới handler, không chỉ xác nhận response chung chung.

## 9. Phân biệt authentication và authorization

Hai quyết định bảo mật có status khác nhau:

| Tình huống | Status | Ý nghĩa |
| --- | --- | --- |
| Thiếu token | **UNAUTHENTICATED** | Caller chưa chứng minh được danh tính. |
| Token sai chữ ký, hết hạn hoặc issuer không hợp lệ | **UNAUTHENTICATED** | Credential không được chấp nhận. |
| Token hợp lệ nhưng thiếu scope/role | **PERMISSION_DENIED** | Caller đã xác thực nhưng không đủ quyền. |
| Resource không tồn tại | **NOT_FOUND** | Lỗi nghiệp vụ/resource, không phải lỗi xác thực. |

Không trả **UNAUTHENTICATED** cho mọi lỗi authorization. Phân biệt này giúp client biết có cần đăng nhập/refresh credential hay cần yêu cầu quyền khác.

Một test authorization nên dùng token hợp lệ nhưng thiếu quyền và xác nhận **PERMISSION_DENIED**. Không nên dùng token sai để mô phỏng thiếu role, vì hai tình huống xảy ra ở hai giai đoạn khác nhau.

## 10. Metadata cho trace và tenant

Ngoài authorization, integration test có thể kiểm tra metadata tùy ngữ cảnh:

- **x-request-id**: liên kết log giữa client, interceptor và service.
- **traceparent** hoặc trace metadata theo tracing stack đang dùng.
- **x-tenant-id**: định tuyến hoặc chọn tenant sau khi xác thực.

Tenant ID do client gửi không tự chứng minh caller thuộc tenant đó. Server phải đối chiếu tenant trong token/principal với tenant metadata trước khi truy cập dữ liệu. Không tin metadata do client tự khai báo nếu nó ảnh hưởng quyền truy cập.

Test nên gửi tenant hợp lệ, tenant không khớp principal và metadata bị thiếu. Kiểm tra rằng interceptor/service từ chối trường hợp không khớp trước khi truy cập dữ liệu tenant khác.

## 11. Các lưu ý về bảo mật metadata

- Dùng TLS để bảo vệ bearer token trên đường truyền.
- Không ghi authorization hoặc token vào application log, tracing attribute hay exception message.
- Không đưa token vào Protobuf payload, URL hoặc query string.
- Không chia sẻ mutable metadata object giữa các call.
- Giới hạn kích thước metadata và từ chối giá trị sai định dạng.
- Xác minh chữ ký, issuer, audience, expiry và thuật toán token theo policy.
- Không tin tenant/role do client tự khai báo nếu chưa được ràng buộc với principal đã xác thực.
- Dùng credential test ngắn hạn, không dùng secret production trong test resources.

Metadata là header của RPC, không phải nơi lưu dữ liệu bí mật an toàn tự thân. TLS, xác minh credential và chính sách log đều cần được kiểm tra riêng.

## 12. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đặt metadata key chữ hoa hoặc sai marshaller | Key không được xử lý như mong đợi | Dùng tên chữ thường và marshaller đúng loại. |
| Gắn token vào Protobuf payload | Trộn auth với dữ liệu nghiệp vụ | Dùng authorization metadata. |
| Gửi bearer token qua plaintext không tin cậy | Credential có thể bị đọc trên đường truyền | Bật TLS và test TLS riêng. |
| Chỉ test token hợp lệ | Bỏ sót đường từ chối | Test thiếu token, token sai và token hết hạn. |
| Trả **PERMISSION_DENIED** cho token không hợp lệ | Client không phân biệt được authn/authz | Dùng **UNAUTHENTICATED** cho credential không hợp lệ. |
| Tin tenant ID từ client | Có thể truy cập chéo tenant | Đối chiếu với principal đã xác thực. |
| Log toàn bộ metadata | Rò token hoặc dữ liệu nhạy cảm | Redact authorization và metadata nhạy cảm. |
| Kiểm tra status nhưng không xác nhận handler không chạy | Lỗi có thể phát sinh từ business method | Dùng spy/counter xác nhận interceptor chặn trước handler. |
| Đăng ký interceptor ở test server khác production | Test không phản ánh cấu hình thật | Kiểm thử extension point của starter đang triển khai. |

## 13. Ma trận kiểm thử auth metadata

Một bộ integration test cơ bản nên bao gồm:

1. Authorization metadata bị thiếu: **UNAUTHENTICATED**.
2. Bearer token sai hoặc hết hạn: **UNAUTHENTICATED**.
3. Token hợp lệ: RPC thành công.
4. Token hợp lệ nhưng thiếu role/scope: **PERMISSION_DENIED**.
5. Tenant metadata không khớp principal: bị từ chối trước khi truy cập dữ liệu.
6. Authorization metadata không bị ghi vào log.
7. Nhiều call đồng thời với token/tenant khác nhau không rò metadata qua nhau.
8. TLS test xác nhận credential được gửi trên kết nối đã mã hóa.

Đặt deadline cho mỗi RPC và đóng channel sau test. Nếu dùng Spring context cache, để Spring quản lý server; test chỉ đóng channel do chính test tạo.

## 14. Bài tập thực hành

Tạo integration test cho service **Greeter** có authentication metadata:

1. Định nghĩa key **authorization** với **ASCII_STRING_MARSHALLER**.
2. Tạo **AuthServerInterceptor** xác minh bearer token trước khi gọi service handler.
3. Đăng ký interceptor trên server Spring gRPC theo extension point của starter hoặc fixture test sở hữu server.
4. Tạo client interceptor gắn bearer token trên từng call.
5. Test thiếu token và token sai nhận **UNAUTHENTICATED**.
6. Test token hợp lệ gọi được RPC.
7. Thêm trường hợp token hợp lệ nhưng thiếu scope nhận **PERMISSION_DENIED**.
8. Xác nhận service handler không chạy khi authentication thất bại.
9. Kiểm tra metadata không bị log và channel/server đóng đúng lifecycle.

**Tiêu chí hoàn thành:** test chứng minh metadata được gửi đúng, server interceptor chặn request chưa xác thực, status phân biệt authn/authz và credential không rò giữa các call.

## 15. Ghi nhớ

- gRPC metadata truyền ngữ cảnh của call qua HTTP/2 headers/trailers; payload nghiệp vụ vẫn nằm trong Protobuf.
- Dùng metadata key chữ thường và marshaller đúng loại; key binary có hậu tố **-bin**.
- Server interceptor xác thực trước service handler và có thể kết thúc call bằng **UNAUTHENTICATED**.
- Client interceptor hoặc **CallCredentials** gắn credential theo từng call.
- **UNAUTHENTICATED** dành cho danh tính/credential không hợp lệ; **PERMISSION_DENIED** dành cho caller đã xác thực nhưng thiếu quyền.
- Metadata không tự mã hóa; bearer token cần TLS trên kết nối không tin cậy.
- Không log token, không tin tenant metadata nếu chưa đối chiếu principal và không chia sẻ metadata mutable giữa các call.
- Integration test cần bao gồm thành công, thiếu/sai token, thiếu quyền, isolation và TLS.

Kiểm thử auth metadata qua server interceptor và client credential giúp dịch vụ Spring gRPC xác thực request trước business logic, trả status nhất quán và giữ credential an toàn giữa các RPC đồng thời.
