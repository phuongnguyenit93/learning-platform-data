# Thêm interceptor cho auth và correlation ID

Trong dự án này, hãy xây dựng một cặp interceptor để mọi RPC đi qua cùng một quy tắc xác thực và truy vết yêu cầu. Server interceptor đọc Bearer token, xác minh danh tính, tạo hoặc kiểm tra correlation ID rồi đưa hai giá trị vào gRPC Context. Client interceptor gắn access token và correlation ID vào metadata của RPC outbound.

Kết quả cần đạt: request thiếu hoặc có token không hợp lệ bị từ chối bằng gRPC status phù hợp; service đọc được danh tính đã xác thực và correlation ID mà không phải tự phân tích metadata; response trả lại correlation ID để client và người vận hành tra cứu log. Bài thực hành dùng một RPC unary để minh họa, nhưng interceptor có thể áp dụng cho cả unary và streaming RPC.

Các ví dụ Java sử dụng API có trong Java 11 trở lên và grpc-java. Hãy dùng cùng phiên bản grpc-java cho runtime, stub và dependency kiểm thử.

## 1. Mục tiêu và luồng xử lý

Sau bài thực hành, bạn có thể:

- Khai báo metadata key theo quy ước gRPC.
- Viết server interceptor xác minh Bearer token và trả status khi xác thực thất bại.
- Đưa principal và correlation ID vào **io.grpc.Context**.
- Viết client interceptor gắn thông tin xác thực và correlation ID vào RPC outbound.
- Đăng ký interceptor vào đúng server và channel trong ứng dụng Spring.
- Kiểm thử request hợp lệ, thiếu token, token sai, correlation ID không hợp lệ và việc chuyển correlation ID sang service downstream.

Luồng mong muốn:

~~~mermaid
sequenceDiagram
    participant C as gRPC Client
    participant CI as Client Interceptors
    participant SI as Server Interceptor
    participant S as Spring gRPC Service
    participant D as Downstream Service

    C->>CI: Gọi RPC
    CI->>CI: Gắn Authorization và x-correlation-id
    CI->>SI: Metadata qua HTTP/2
    SI->>SI: Kiểm tra correlation ID
    SI->>SI: Xác minh Bearer token
    alt Token không hợp lệ
        SI-->>C: UNAUTHENTICATED + correlation ID trailer
    else Token hợp lệ
        SI->>S: Gắn principal và correlation ID vào gRPC Context
        S->>D: Gọi RPC downstream
        Note over S,D: Client interceptor đọc correlation ID từ Context
        D-->>S: Response
        S-->>C: Response + correlation ID
    end
~~~

Phân biệt rõ ba khái niệm:

| Thành phần | Vai trò |
|---|---|
| Authentication | Xác minh client đang đại diện cho danh tính nào |
| Authorization | Kiểm tra danh tính đó có quyền gọi thao tác cụ thể hay không |
| Correlation ID | Liên kết log và hoạt động của cùng một request qua nhiều service |

Interceptor xác thực chịu trách nhiệm authentication. Quyền theo nghiệp vụ vẫn cần được kiểm tra ở service hoặc authorization layer. Correlation ID chỉ phục vụ đối chiếu và không được dùng làm bằng chứng danh tính.

## 2. Chuẩn bị hợp đồng và metadata

Dùng một RPC unary nhỏ để kiểm thử interceptor. Tạo file Protocol Buffers, ví dụ **src/main/proto/order.proto**:

~~~proto
syntax = "proto3";

package orders.v1;

option java_multiple_files = true;
option java_package = "com.example.orders.grpc";

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (GetOrderResponse);
}

message GetOrderRequest {
  string order_id = 1;
}

message GetOrderResponse {
  string order_id = 1;
  string status = 2;
}
~~~

Chạy tác vụ sinh mã Protocol Buffers đã cấu hình trong dự án. Phần còn lại dùng generated service base class và stub do plugin tạo ra.

Quy ước metadata của bài thực hành:

| Metadata key | Hướng truyền | Ý nghĩa |
|---|---|---|
| **authorization** | Client → Server | Bearer access token |
| **x-correlation-id** | Client → Server, Server → Client | Mã liên kết request |
| **traceparent**, **tracestate**, **baggage** | Theo cấu hình tracing | Trace context của OpenTelemetry |

Tên metadata key phải viết thường. Dùng **Metadata.ASCII_STRING_MARSHALLER** cho các giá trị văn bản. Không tự đặt key bắt đầu bằng **grpc-**, vì nhóm tên này dành cho giao thức gRPC.

Correlation ID trong ví dụ được giới hạn ở 64 ký tự ASCII thuộc nhóm chữ, số, dấu chấm, gạch dưới và gạch ngang. Nếu client không gửi, server sinh UUID. Nếu client gửi giá trị không hợp lệ, server trả **INVALID_ARGUMENT** và vẫn sinh một ID mới để nhận diện lần từ chối đó. Không đưa token, email, tên người dùng hoặc dữ liệu cá nhân vào correlation ID.

## 3. Tạo lớp metadata và request context

Tạo lớp chứa metadata key dùng chung giữa client và server:

~~~java
package com.example.orders.grpc;

import io.grpc.Metadata;

public final class GrpcMetadata {
    private GrpcMetadata() {}

    public static final Metadata.Key<String> AUTHORIZATION =
            Metadata.Key.of(
                    "authorization",
                    Metadata.ASCII_STRING_MARSHALLER);

    public static final Metadata.Key<String> CORRELATION_ID =
            Metadata.Key.of(
                    "x-correlation-id",
                    Metadata.ASCII_STRING_MARSHALLER);
}
~~~

Tạo các context key để service có thể lấy thông tin đã được interceptor xác minh:

~~~java
package com.example.orders.grpc;

import io.grpc.Context;

public final class GrpcRequestContext {
    private GrpcRequestContext() {}

    public static final Context.Key<AuthenticatedUser> AUTHENTICATED_USER =
            Context.key("authenticated-user");

    public static final Context.Key<String> CORRELATION_ID =
            Context.key("correlation-id");
}
~~~

**io.grpc.Context** gắn dữ liệu với quá trình xử lý RPC và được grpc-java quản lý qua các callback. Nó không phải **ThreadLocal** do ứng dụng tự quản lý. Khi chuyển việc sang executor riêng, cần truyền context một cách tường minh; nếu không, giá trị có thể không còn hiện diện trên thread mới.

Tạo principal tối thiểu cho ứng dụng:

~~~java
package com.example.orders.grpc;

import java.util.Set;

public final class AuthenticatedUser {
    private final String subject;
    private final Set<String> authorities;

    public AuthenticatedUser(String subject, Set<String> authorities) {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        this.subject = subject;
        this.authorities = Set.copyOf(authorities);
    }

    public String getSubject() {
        return subject;
    }

    public boolean hasAuthority(String authority) {
        return authorities.contains(authority);
    }

    public Set<String> getAuthorities() {
        return authorities;
    }
}
~~~

Principal chỉ giữ những thuộc tính cần cho authorization và audit. Không lưu access token thô vào gRPC Context, log hoặc object principal.

## 4. Định nghĩa cổng xác minh token

Không nên tự giải mã JWT rồi coi payload là đáng tin. Cần xác minh chữ ký và các claim bắt buộc bằng thư viện bảo mật đã được dự án lựa chọn.

Tách việc xác minh khỏi interceptor bằng interface:

~~~java
package com.example.orders.security;

import com.example.orders.grpc.AuthenticatedUser;

public interface TokenVerifier {
    AuthenticatedUser verify(String token)
            throws InvalidTokenException,
                   AuthenticationUnavailableException;
}
~~~

Hai exception có thể được khai báo tối thiểu như sau:

~~~java
package com.example.orders.security;

public final class InvalidTokenException extends Exception {
    public InvalidTokenException(String message) {
        super(message);
    }
}
~~~

~~~java
package com.example.orders.security;

public final class AuthenticationUnavailableException extends Exception {
    public AuthenticationUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Hai exception biểu diễn hai loại lỗi khác nhau:

- **InvalidTokenException**: token thiếu, sai chữ ký, hết hạn, sai issuer/audience hoặc không còn được chấp nhận.
- **AuthenticationUnavailableException**: hệ thống xác minh tạm thời không thể phục vụ, ví dụ dịch vụ introspection hoặc kho khóa bị lỗi.

Phần triển khai **TokenVerifier** nên:

- Chỉ chấp nhận thuật toán ký được cho phép; không tin thuật toán do token tự khai báo.
- Kiểm tra chữ ký, issuer, audience, expiration và not-before.
- Hỗ trợ luân chuyển khóa và cache khóa công khai theo chính sách.
- Trả về subject cùng authorities đã được chuẩn hóa.
- Không ghi token vào log và không trả chi tiết xác minh cho client.

Nếu xác minh bằng JWT và khóa công khai cục bộ, việc kiểm tra thường có thể thực hiện nhanh trong interceptor. Nếu phải gọi một dịch vụ xác minh từ xa, không để lời gọi mạng không giới hạn chặn thread xử lý gRPC. Hãy dùng kiến trúc xác thực bất đồng bộ hoặc cache có timeout, circuit breaker và chính sách lỗi rõ ràng.

## 5. Viết server interceptor

Tạo helper kiểm tra và sinh correlation ID:

~~~java
package com.example.orders.grpc;

import java.util.UUID;
import java.util.regex.Pattern;

public final class CorrelationIds {
    private static final Pattern VALID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,63}");

    private CorrelationIds() {}

    public static boolean isValid(String value) {
        return value != null && VALID.matcher(value).matches();
    }

    public static String newId() {
        return UUID.randomUUID().toString();
    }
}
~~~

Tiếp theo, tạo **AuthCorrelationServerInterceptor**. Interceptor này xác thực trước khi gọi handler. Khi thành công, nó bọc **ServerCall** để trả correlation ID trong response headers nếu service gửi headers tường minh, và trong trailers khi RPC kết thúc. Nhờ vậy cả response thành công lẫn response lỗi đều có thể được đối chiếu.

~~~java
package com.example.orders.grpc;

import com.example.orders.security.TokenVerifier;
import com.example.orders.security.InvalidTokenException;
import com.example.orders.security.AuthenticationUnavailableException;
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.ForwardingServerCall;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class AuthCorrelationServerInterceptor
        implements ServerInterceptor {

    private final TokenVerifier tokenVerifier;

    public AuthCorrelationServerInterceptor(TokenVerifier tokenVerifier) {
        this.tokenVerifier = tokenVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String incomingId = headers.get(GrpcMetadata.CORRELATION_ID);
        String correlationId =
                incomingId == null ? CorrelationIds.newId() : incomingId;

        if (!CorrelationIds.isValid(correlationId)) {
            return reject(
                    call,
                    Status.INVALID_ARGUMENT.withDescription(
                            "Invalid x-correlation-id"),
                    CorrelationIds.newId());
        }

        String token = extractBearerToken(
                headers.get(GrpcMetadata.AUTHORIZATION));

        if (token == null) {
            return reject(
                    call,
                    Status.UNAUTHENTICATED.withDescription(
                            "Missing or invalid bearer credentials"),
                    correlationId);
        }

        AuthenticatedUser user;
        try {
            user = tokenVerifier.verify(token);
        } catch (InvalidTokenException exception) {
            return reject(
                    call,
                    Status.UNAUTHENTICATED.withDescription(
                            "Invalid bearer credentials"),
                    correlationId);
        } catch (AuthenticationUnavailableException exception) {
            return reject(
                    call,
                    Status.UNAVAILABLE.withDescription(
                            "Authentication service unavailable"),
                    correlationId);
        } catch (RuntimeException exception) {
            // Ghi log exception đã loại bỏ dữ liệu nhạy cảm trước khi trả lỗi.
            return reject(
                    call,
                    Status.INTERNAL.withDescription(
                            "Authentication failed"),
                    correlationId);
        }

        if (user == null) {
            return reject(
                    call,
                    Status.UNAUTHENTICATED.withDescription(
                            "Invalid bearer credentials"),
                    correlationId);
        }

        ServerCall<ReqT, RespT> responseCall =
                new ForwardingServerCall.SimpleForwardingServerCall<>(call) {

            @Override
            public void sendHeaders(Metadata responseHeaders) {
                addCorrelationId(responseHeaders, correlationId);
                super.sendHeaders(responseHeaders);
            }

            @Override
            public void close(Status status, Metadata trailers) {
                addCorrelationId(trailers, correlationId);
                super.close(status, trailers);
            }
        };

        Context requestContext = Context.current()
                .withValue(
                        GrpcRequestContext.AUTHENTICATED_USER,
                        user)
                .withValue(
                        GrpcRequestContext.CORRELATION_ID,
                        correlationId);

        return Contexts.interceptCall(
                requestContext,
                responseCall,
                headers,
                next);
    }

    private static String extractBearerToken(String authorization) {
        if (authorization == null
                || !authorization.regionMatches(
                        true, 0, "Bearer ", 0, 7)) {
            return null;
        }

        String token = authorization.substring(7).trim();
        if (token.isEmpty() || token.chars().anyMatch(Character::isWhitespace)) {
            return null;
        }
        return token;
    }

    private static void addCorrelationId(
            Metadata metadata,
            String correlationId) {
        metadata.discardAll(GrpcMetadata.CORRELATION_ID);
        metadata.put(GrpcMetadata.CORRELATION_ID, correlationId);
    }

    private static <ReqT, RespT> ServerCall.Listener<ReqT> reject(
            ServerCall<ReqT, RespT> call,
            Status status,
            String correlationId) {

        Metadata trailers = new Metadata();
        trailers.put(GrpcMetadata.CORRELATION_ID, correlationId);
        call.close(status, trailers);

        return new ServerCall.Listener<ReqT>() {};
    }
}
~~~

Điểm cần hiểu trong interceptor:

1. Metadata được đọc một lần tại ranh giới RPC. Service không phải tự phân tích chuỗi Authorization.
2. **TokenVerifier** quyết định token có hợp lệ hay không. Token không hợp lệ trả **UNAUTHENTICATED**; hệ thống xác minh tạm thời lỗi trả **UNAVAILABLE**.
3. **Contexts.interceptCall(...)** gắn principal và correlation ID vào context trong quá trình gọi handler và các callback của listener.
4. **ServerCall** được bọc để thêm correlation ID vào response metadata. Khi RPC kết thúc, ID được đưa vào trailers, kể cả khi service không gửi headers tường minh.
5. Khi từ chối request, interceptor đóng call và trả listener rỗng. Service nghiệp vụ không được gọi.

Nếu có RPC công khai không cần token, hãy xây dựng allowlist theo full method name và kiểm thử rõ ràng. Không suy ra rằng mọi method đều công khai chỉ vì metadata Authorization bị thiếu. Các method còn lại phải mặc định yêu cầu xác thực.

## 6. Đọc principal và correlation ID trong service

Tạo service từ generated base class. Service đọc dữ liệu từ gRPC Context và thực hiện authorization theo quyền nghiệp vụ:

~~~java
package com.example.orders.service;

import com.example.orders.grpc.AuthenticatedUser;
import com.example.orders.grpc.GrpcRequestContext;
import com.example.orders.grpc.OrderServiceGrpc;
import com.example.orders.grpc.GetOrderRequest;
import com.example.orders.grpc.GetOrderResponse;
import io.grpc.Status;
import io.grpc.stub.StreamObserver;

public final class OrderGrpcService
        extends OrderServiceGrpc.OrderServiceImplBase {

    @Override
    public void getOrder(
            GetOrderRequest request,
            StreamObserver<GetOrderResponse> responseObserver) {

        AuthenticatedUser user =
                GrpcRequestContext.AUTHENTICATED_USER.get();

        String correlationId =
                GrpcRequestContext.CORRELATION_ID.get();

        if (user == null) {
            responseObserver.onError(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required")
                            .asRuntimeException());
            return;
        }

        if (!user.hasAuthority("orders:read")) {
            responseObserver.onError(
                    Status.PERMISSION_DENIED
                            .withDescription("Insufficient permission")
                            .asRuntimeException());
            return;
        }

        // Ghi log có cấu trúc với subject và correlationId.
        // Không ghi access token hoặc dữ liệu nhạy cảm của request.

        GetOrderResponse response = GetOrderResponse.newBuilder()
                .setOrderId(request.getOrderId())
                .setStatus("ACCEPTED")
                .build();

        responseObserver.onNext(response);
        responseObserver.onCompleted();
    }
}
~~~

Trong dự án thật, thay response minh họa bằng kết quả từ service nghiệp vụ. Có thể đưa kiểm tra quyền vào một authorization service hoặc interceptor riêng nếu nhiều RPC dùng chung chính sách. Authentication và authorization nên có status khác nhau: danh tính chưa được xác minh là **UNAUTHENTICATED**; danh tính hợp lệ nhưng không đủ quyền là **PERMISSION_DENIED**.

## 7. Thêm interceptor ở client

Client cần gửi access token từ nguồn cấp token của ứng dụng. Không hardcode token trong source code và không tự tạo token trong interceptor.

Tạo abstraction lấy access token:

~~~java
package com.example.orders.security;

public interface AccessTokenProvider {
    String getAccessToken();
}
~~~

Client interceptor gắn Bearer token:

~~~java
package com.example.orders.grpc;

import com.example.orders.security.AccessTokenProvider;
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

public final class BearerTokenClientInterceptor
        implements ClientInterceptor {

    private final AccessTokenProvider tokenProvider;

    public BearerTokenClientInterceptor(
            AccessTokenProvider tokenProvider) {
        this.tokenProvider = tokenProvider;
    }

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {

            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata headers) {

                String token = tokenProvider.getAccessToken();
                headers.discardAll(GrpcMetadata.AUTHORIZATION);

                if (token != null && !token.isBlank()) {
                    headers.put(
                            GrpcMetadata.AUTHORIZATION,
                            "Bearer " + token);
                }

                super.start(listener, headers);
            }
        };
    }
}
~~~

Nếu không lấy được token, ví dụ vẫn khởi tạo RPC và server sẽ trả **UNAUTHENTICATED**. Ở ứng dụng thực tế, có thể chủ động chặn lời gọi ở client để đưa ra thông báo sớm. **AccessTokenProvider** nên tích hợp với cơ chế OAuth2 hoặc hệ thống cấp token mà ứng dụng đang sử dụng, bao gồm refresh và thời hạn token.

Tạo client interceptor cho correlation ID:

~~~java
package com.example.orders.grpc;

import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

public final class CorrelationIdClientInterceptor
        implements ClientInterceptor {

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {

            @Override
            public void start(
                    Listener<RespT> listener,
                    Metadata headers) {

                String correlationId =
                        GrpcRequestContext.CORRELATION_ID.get();

                if (correlationId == null) {
                    correlationId =
                            headers.get(GrpcMetadata.CORRELATION_ID);
                }

                if (!CorrelationIds.isValid(correlationId)) {
                    correlationId = CorrelationIds.newId();
                }

                headers.discardAll(GrpcMetadata.CORRELATION_ID);
                headers.put(
                        GrpcMetadata.CORRELATION_ID,
                        correlationId);

                super.start(listener, headers);
            }
        };
    }
}
~~~

Thứ tự ưu tiên là correlation ID đang có trong gRPC Context, sau đó là metadata do caller cung cấp, cuối cùng mới sinh UUID. Nhờ đó, khi service A xử lý một request rồi gọi service B, client interceptor của channel outbound có thể dùng lại ID mà server interceptor đã đưa vào Context.

Nếu client cần giữ cùng một ID qua nhiều RPC độc lập, hãy tạo ID tại ranh giới của request nghiệp vụ và đặt nó vào context trong phạm vi các lời gọi:

~~~java
String correlationId = CorrelationIds.newId();

io.grpc.Context.current()
        .withValue(
                GrpcRequestContext.CORRELATION_ID,
                correlationId)
        .run(() -> {
            orderStub.getOrder(request);
            // Các RPC tiếp theo trong cùng phạm vi sẽ dùng lại ID.
        });
~~~

Với tác vụ chuyển sang executor riêng, bọc tác vụ bằng **Context.current().wrap(...)** hoặc dùng **Context.currentContextExecutor(executor)**. Không giả định context sẽ tự truyền qua mọi **CompletableFuture**, **@Async** hoặc scheduler.

## 8. Đăng ký interceptor trong ứng dụng Spring

Để Spring quản lý dependency, khai báo các interceptor như bean:

~~~java
@Configuration
public class GrpcInterceptorConfiguration {

    @Bean
    AuthCorrelationServerInterceptor authCorrelationServerInterceptor(
            TokenVerifier tokenVerifier) {
        return new AuthCorrelationServerInterceptor(tokenVerifier);
    }

    @Bean
    BearerTokenClientInterceptor bearerTokenClientInterceptor(
            AccessTokenProvider tokenProvider) {
        return new BearerTokenClientInterceptor(tokenProvider);
    }

    @Bean
    CorrelationIdClientInterceptor correlationIdClientInterceptor() {
        return new CorrelationIdClientInterceptor();
    }
}
~~~

Bean chỉ được tạo trong Spring container; cần bảo đảm starter đang dùng thực sự đăng ký interceptor vào gRPC server hoặc channel. Cơ chế đăng ký khác nhau giữa các phiên bản và starter. Hãy dùng global server interceptor hook hoặc server builder customizer mà phiên bản dự án cung cấp, rồi xác minh interceptor đã nằm trong chuỗi xử lý của service.

Ở mức grpc-java thuần, đăng ký server interceptor có dạng:

~~~java
serverBuilder.addService(
        ServerInterceptors.intercept(
                orderGrpcService,
                authCorrelationServerInterceptor));
~~~

Và gắn các client interceptor vào channel:

~~~java
ManagedChannel channel = ManagedChannelBuilder
        .forAddress(host, port)
        .useTransportSecurity()
        .intercept(
                bearerTokenClientInterceptor,
                correlationIdClientInterceptor)
        .build();
~~~

Trong ứng dụng Spring, để starter tạo và quản lý server/channel, hãy nối các bean trên qua extension point của starter thay vì tạo một channel mới ngoài vòng đời quản lý của Spring. Kiểm tra cấu hình TLS trên channel production; chỉ dùng plaintext trong môi trường kiểm thử cục bộ được kiểm soát.

## 9. Kiểm thử tích hợp bằng in-process gRPC

Dùng in-process server/channel để kiểm thử interceptor mà không cần mở cổng mạng. Dependency kiểm thử **grpc-inprocess** phải dùng cùng phiên bản grpc-java với các dependency gRPC còn lại.

Khởi tạo server kiểm thử:

~~~java
String serverName = InProcessServerBuilder.generateName();

Server server = InProcessServerBuilder
        .forName(serverName)
        .directExecutor()
        .addService(
                ServerInterceptors.intercept(
                        testOrderService,
                        authCorrelationServerInterceptor))
        .build()
        .start();

ManagedChannel channel = InProcessChannelBuilder
        .forName(serverName)
        .directExecutor()
        .build();
~~~

Dùng **TokenVerifier** giả trong test: chấp nhận một token kiểm thử đã biết và từ chối các giá trị khác. Không dùng JWT production hoặc secret thật trong unit test.

Ví dụ verifier giả:

~~~java
TokenVerifier testTokenVerifier = token -> {
    if (!"test-token".equals(token)) {
        throw new InvalidTokenException("invalid test token");
    }
    return new AuthenticatedUser(
            "test-user",
            Set.of("orders:read"));
};
~~~

Có thể gắn metadata kiểm thử vào stub bằng **MetadataUtils.newAttachHeadersInterceptor(...)**:

~~~java
Metadata requestHeaders = new Metadata();
requestHeaders.put(
        GrpcMetadata.AUTHORIZATION,
        "Bearer test-token");
requestHeaders.put(
        GrpcMetadata.CORRELATION_ID,
        "test-order-001");

OrderServiceGrpc.OrderServiceBlockingStub stub =
        OrderServiceGrpc.newBlockingStub(channel)
                .withInterceptors(
                        MetadataUtils.newAttachHeadersInterceptor(
                                requestHeaders));
~~~

Tạo test service ghi nhận principal và correlation ID từ **GrpcRequestContext** vào **AtomicReference**. Sau lời gọi, kiểm tra các giá trị đúng như metadata gửi vào. Thêm một client interceptor capture response trailers để xác nhận **x-correlation-id** được trả lại ngay cả khi RPC thất bại.

Bộ test cần có tối thiểu các trường hợp:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Token hợp lệ và correlation ID hợp lệ | Service được gọi; Context có đúng principal và ID |
| Thiếu Authorization | **UNAUTHENTICATED**; service không được gọi |
| Token sai hoặc hết hạn | **UNAUTHENTICATED**; service không được gọi |
| Token verifier tạm thời lỗi | **UNAVAILABLE** |
| Principal hợp lệ nhưng thiếu authority | **PERMISSION_DENIED** |
| Không gửi correlation ID | Server sinh UUID và trả ID trong response trailers |
| Correlation ID chứa ký tự không cho phép | **INVALID_ARGUMENT**, có ID mới trong trailers |
| Service gọi một RPC downstream | Client interceptor truyền tiếp correlation ID trong Context |
| Client gửi RPC streaming | Interceptor vẫn xác thực và gắn ID cho toàn bộ RPC |

Ví dụ kiểm tra status:

~~~java
StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> unauthenticatedStub.getOrder(request));

assertEquals(
        Status.Code.UNAUTHENTICATED,
        error.getStatus().getCode());
~~~

Đóng channel và server sau mỗi test hoặc trong **@AfterEach** để tránh giữ thread và tài nguyên. In-process test xác minh logic interceptor, metadata và status; nó không kiểm thử TLS, proxy hoặc giới hạn HTTP/2 trên mạng. Những phần đó cần integration test riêng với cấu hình transport gần production.

## 10. Xử lý các lỗi thường gặp

**Server luôn trả UNAUTHENTICATED**

- Kiểm tra client interceptor đã được gắn vào đúng channel của stub.
- Kiểm tra key **authorization** và định dạng **Bearer <token>**.
- Kiểm tra token provider có trả token còn hạn không.
- Kiểm tra **TokenVerifier** xác minh đúng issuer, audience, chữ ký và thời hạn.
- Xác nhận server interceptor thực sự được đăng ký vào service đang gọi.

**Service không đọc được principal hoặc correlation ID**

- Kiểm tra interceptor có gọi **Contexts.interceptCall(...)** với context mới không.
- Kiểm tra service đang đọc đúng context key dùng chung.
- Nếu lỗi chỉ xuất hiện trong tác vụ bất đồng bộ, kiểm tra context propagation qua executor.
- Không đọc giá trị từ một thread local tự tạo rồi giả định nó tương đương gRPC Context.

**Correlation ID thay đổi giữa các service**

- Kiểm tra client interceptor có ưu tiên context hiện tại trước metadata caller không.
- Xác nhận server interceptor ghi correlation ID vào Context trước khi handler chạy.
- Kiểm tra executor có giữ context khi service gọi downstream không.
- Phân biệt correlation ID của request với trace ID của OpenTelemetry. Nếu tracing được bật, hãy để propagator quản lý **traceparent** và span context.

**Interceptor đã là Spring bean nhưng không chạy**

- Xác minh extension point đăng ký interceptor của starter đang sử dụng.
- Kiểm tra đúng server, service definition và channel được tạo bởi Spring.
- Thêm test tích hợp gọi qua stub thật và xác nhận interceptor được thực thi; chỉ kiểm tra bean tồn tại là chưa đủ.

## 11. Bảo mật và vận hành

- Dùng TLS cho kết nối client/server; cân nhắc mTLS khi cần xác thực danh tính workload ở tầng transport.
- Không tin user ID, role hoặc tenant ID do client tự gửi trong metadata. Principal phải được tạo từ token đã xác minh hoặc nguồn tin cậy tương đương.
- Không ghi Authorization header, token, secret hoặc payload nhạy cảm vào log.
- Không chuyển tiếp nguyên token của người gọi sang service downstream nếu chưa có chính sách delegation rõ ràng. Có thể dùng service identity hoặc token exchange theo kiến trúc bảo mật của hệ thống.
- Dùng **UNAUTHENTICATED** cho danh tính chưa được xác minh, **PERMISSION_DENIED** cho danh tính hợp lệ nhưng thiếu quyền, **INVALID_ARGUMENT** cho correlation ID sai định dạng và **UNAVAILABLE** khi dịch vụ xác minh tạm thời không hoạt động.
- Không trả thông tin nội bộ như lý do chữ ký JWT sai, tên khóa hoặc chi tiết nhà cung cấp xác thực cho client.
- Đặt giới hạn độ dài và tập ký tự cho correlation ID; không dùng giá trị này làm metric label có cardinality cao.
- Correlation ID không thay thế distributed tracing. Khi dùng OpenTelemetry, tiếp tục inject/extract trace context bằng instrumentation hoặc propagator tương ứng.

Các trường log nên có RPC method, status code, subject đã chuẩn hóa và correlation ID. Chỉ ghi subject khi chính sách dữ liệu cho phép. Dùng correlation ID để tìm toàn bộ log của một request qua nhiều service; dùng trace ID và span ID để phân tích quan hệ cha-con và thời gian từng operation.

## 12. Tiêu chí hoàn thành dự án

- [ ] Metadata key **authorization** và **x-correlation-id** được khai báo một lần và dùng chung.
- [ ] Token verifier kiểm tra chữ ký/claim theo chính sách và không log token.
- [ ] Server interceptor từ chối token thiếu hoặc không hợp lệ bằng **UNAUTHENTICATED**.
- [ ] Lỗi tạm thời của hệ thống xác minh được ánh xạ thành **UNAVAILABLE**.
- [ ] Principal đã xác minh và correlation ID được đưa vào gRPC Context.
- [ ] Service kiểm tra quyền nghiệp vụ và không tự parse Authorization metadata.
- [ ] Server trả correlation ID trong response metadata hoặc trailers.
- [ ] Client interceptor gắn Bearer token và truyền tiếp correlation ID.
- [ ] Interceptor được đăng ký vào đúng Spring gRPC server và channel.
- [ ] Test bao phủ token hợp lệ, token sai, thiếu quyền, correlation ID thiếu/sai và downstream propagation.
- [ ] Có TLS, log an toàn và phân biệt correlation ID với trace context.

Khi các tiêu chí trên đều đạt, mọi RPC được bảo vệ bởi cùng một điểm xác thực, service nhận được danh tính đã xác minh qua Context, và correlation ID đi theo luồng gọi để hỗ trợ điều tra sự cố.
