# Test server interceptor

Server interceptor là lớp xử lý nằm trước service handler trong gRPC server call pipeline. Nó thường dùng để đọc metadata, xác thực caller, kiểm tra quyền, gắn principal hoặc correlation ID vào gRPC Context, ghi nhận telemetry và chuẩn hóa cách từ chối request. Vì interceptor ảnh hưởng tới mọi RPC đi qua nó, cần kiểm thử cả trường hợp được phép lẫn bị từ chối, cũng như xác minh handler nhận đúng context.

Trong Spring gRPC, interceptor có thể được đăng ký ở cấp server hoặc gắn với service tùy cấu hình. Test nên phân biệt hai mục tiêu: kiểm tra logic interceptor bằng in-process server và kiểm tra Spring thực sự đăng ký interceptor bean vào server do starter quản lý. In-process test không xác minh TLS, HTTP/2 qua socket, ingress hoặc network policy.

## 1. Server interceptor nằm ở đâu trong call pipeline?

Khi client gọi một RPC, server xác định method rồi đi qua interceptor trước khi dispatch tới service handler:

```text
Client stub
    |
    | request + metadata
    v
gRPC server transport
    |
    v
Server interceptor(s)
    | authenticate / authorize
    | inspect metadata
    | attach Context
    v
Service handler
    |
    v
response messages or gRPC status
```

grpc-java định nghĩa ServerInterceptor với method interceptCall. Interceptor nhận ServerCall, Metadata và ServerCallHandler kế tiếp. Nó có thể:

- Cho call đi tiếp bằng next.startCall(call, headers).
- Đóng call bằng status nếu credential sai hoặc caller không đủ quyền.
- Tạo Context chứa dữ liệu của call và truyền context đó xuống handler.
- Bọc ServerCall hoặc listener để quan sát headers, messages, close và cancellation.

Interceptor không thay thế business validation trong service. Nó xử lý cross-cutting concern áp dụng ở ranh giới RPC; service vẫn phải kiểm tra input và quyền trên tài nguyên nghiệp vụ khi cần.

## 2. Vòng đời của interceptCall

Một interceptor tối thiểu có dạng:

```java
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;

final class LoggingServerInterceptor implements ServerInterceptor {
    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String fullMethod =
            call.getMethodDescriptor().getFullMethodName();

        // Ghi nhận method/correlation ID theo chính sách log.
        return next.startCall(call, headers);
    }
}
```

interceptCall chạy khi server nhận call, trước khi listener xử lý các request message. Listener được trả về sẽ nhận callback như onMessage, onHalfClose, onCancel, onComplete và onReady. Với unary RPC, server thường nhận một request qua onMessage rồi onHalfClose trước khi handler kết thúc call.

Không giữ request-specific data trong field mutable của interceptor singleton. Nhiều RPC có thể chạy đồng thời trên cùng instance; lưu principal hoặc request ID vào field sẽ gây rò dữ liệu giữa caller. Dùng biến local cho call hoặc gRPC Context.

## 3. Metadata, authentication và authorization

Metadata là header/trailer ở tầng gRPC, thường dùng để truyền credential, tenant ID, request ID hoặc tracing information. Interceptor cần đọc metadata theo key đã định nghĩa:

```java
import io.grpc.Metadata;

static final Metadata.Key<String> AUTHORIZATION =
    Metadata.Key.of(
        "authorization",
        Metadata.ASCII_STRING_MARSHALLER);

static final Metadata.Key<String> REQUEST_ID =
    Metadata.Key.of(
        "x-request-id",
        Metadata.ASCII_STRING_MARSHALLER);
```

Quy trình authentication cơ bản:

1. Đọc authorization metadata.
2. Xác minh token/chứng thư bằng verifier đáng tin cậy.
3. Tạo principal từ kết quả xác minh, không lấy role tùy ý từ header caller gửi.
4. Nếu credential thiếu hoặc không hợp lệ, kết thúc bằng UNAUTHENTICATED.
5. Nếu identity hợp lệ nhưng không đủ quyền, kết thúc bằng PERMISSION_DENIED.
6. Nếu được phép, gắn principal vào Context rồi cho call đi tiếp.

Authentication xác định caller là ai; authorization xác định caller được làm gì. Không xem việc header tồn tại là bằng chứng identity hợp lệ. Không ghi bearer token, private key hoặc metadata nhạy cảm vào log.

## 4. Truyền principal qua gRPC Context

Context là cơ chế gRPC để truyền dữ liệu gắn với call qua các callback và thread boundary mà không dùng field mutable toàn cục. Ví dụ interceptor xác minh bearer token rồi gắn principal:

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

final class AuthServerInterceptor implements ServerInterceptor {
    static final Context.Key<String> PRINCIPAL =
        Context.key("authenticated-principal");

    private final TokenVerifier verifier;

    AuthServerInterceptor(TokenVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String authorization = headers.get(AUTHORIZATION);
        String principal = verifier.verify(authorization);
        if (principal == null) {
            call.close(
                Status.UNAUTHENTICATED
                    .withDescription("missing or invalid credentials"),
                new Metadata());
            return new ServerCall.Listener<>() {};
        }

        Context context = Context.current()
            .withValue(PRINCIPAL, principal);
        return Contexts.interceptCall(
            context, call, headers, next);
    }
}
```

TokenVerifier là abstraction của ứng dụng, phải xác minh chữ ký, expiry, issuer/audience và các claim cần thiết. Ví dụ trên rút gọn phần kiểm tra để làm rõ interceptor; production cần phân biệt credential sai với lỗi verifier hoặc identity provider tạm thời không khả dụng theo policy.

Contexts.interceptCall đảm bảo Context được gắn trong quá trình xử lý call và các listener callback. Handler có thể đọc principal bằng AuthServerInterceptor.PRINCIPAL.get(). Không truyền principal qua static mutable variable hoặc field của service singleton.

## 5. Cho phép hoặc từ chối call bằng status

Khi không cho phép call, interceptor phải đóng ServerCall và không gọi next.startCall. Ví dụ:

```java
if (!authorizationPolicy.canReadOrders(principal)) {
    call.close(
        Status.PERMISSION_DENIED
            .withDescription("caller cannot read orders"),
        new Metadata());
    return new ServerCall.Listener<>() {};
}

return next.startCall(call, headers);
```

Status thường được dùng:

| Tình huống | Status |
| --- | --- |
| Credential thiếu, sai hoặc hết hạn | UNAUTHENTICATED |
| Identity hợp lệ nhưng thiếu quyền | PERMISSION_DENIED |
| Request sai format/validation | INVALID_ARGUMENT |
| Resource không tồn tại | NOT_FOUND |
| Dependency tạm thời không khả dụng | UNAVAILABLE theo contract |

Không trả INTERNAL cho mọi lỗi xác thực. Không trả UNAUTHENTICATED khi caller đã xác thực nhưng thiếu role; phân biệt đúng status giúp client xử lý lỗi và giúp telemetry phân loại sự cố.

Sau khi đã gọi call.close, không tiếp tục gọi next hoặc gửi response. Listener rỗng được trả về để hoàn tất hợp đồng của interceptCall; không dùng nó để thực hiện business work.

## 6. Áp dụng policy theo full method name

Một interceptor có thể áp dụng policy khác nhau cho từng method. Dùng full method name từ MethodDescriptor:

```java
String method = call.getMethodDescriptor().getFullMethodName();

if (method.equals("acme.orders.v1.OrderService/GetOrder")) {
    if (!policy.canReadOrders(principal)) {
        call.close(Status.PERMISSION_DENIED, new Metadata());
        return new ServerCall.Listener<>() {};
    }
}

if (method.equals("acme.orders.v1.OrderService/CancelOrder")) {
    if (!policy.canCancelOrders(principal)) {
        call.close(Status.PERMISSION_DENIED, new Metadata());
        return new ServerCall.Listener<>() {};
    }
}

return next.startCall(call, headers);
```

Tên method là proto package + service + method, không phải Java package hay tên bean Spring. Nên gom policy vào một authorization component có thể unit test riêng, thay vì viết một chuỗi điều kiện dài trong interceptor.

Mặc định từ chối các method quản trị hoặc method nhạy cảm nếu chưa có rule. Các RPC public như health probe có thể cần ngoại lệ có kiểm soát, nhưng không nên bỏ qua authentication cho toàn server chỉ để probe hoạt động.

## 7. Thứ tự nhiều interceptor

Một server có thể dùng nhiều interceptor cho authentication, authorization, tracing, logging và metrics. Chúng được lồng thành chuỗi wrapper; interceptor ở lớp ngoài có thể chặn call trước khi interceptor bên trong chạy.

Ví dụ một thứ tự logic thường hợp lý:

1. Correlation/tracing: tạo hoặc xác thực request ID.
2. Authentication: xác minh credential và tạo principal.
3. Authorization: kiểm tra quyền trên method/resource.
4. Metrics/logging: ghi nhận method, outcome và duration theo policy.
5. Service handler: thực thi nghiệp vụ.

Thứ tự đăng ký thực tế phụ thuộc API helper và cách starter xây dựng interceptor chain. Đừng suy luận thứ tự chỉ từ thứ tự các bean trong application context. Viết test dùng spy/counter để xác minh thứ tự thật, nhất là khi một interceptor phụ thuộc Context do interceptor khác tạo.

Nếu authorization chạy trước authentication, principal có thể chưa tồn tại. Nếu logging ghi metadata trước khi redaction, credential có thể bị lộ. Kiểm thử thứ tự là một phần của security test, không chỉ là chi tiết cấu hình.

## 8. Dựng in-process server có server interceptor

In-process transport cho phép test interceptor qua generated stub mà không mở TCP port:

```java
String serverName = InProcessServerBuilder.generateName();

ServerServiceDefinition securedService =
    ServerInterceptors.intercept(
        new GreeterService().bindService(),
        new AuthServerInterceptor(testTokenVerifier));

Server server = InProcessServerBuilder.forName(serverName)
    .directExecutor()
    .addService(securedService)
    .build()
    .start();

ManagedChannel channel = InProcessChannelBuilder
    .forName(serverName)
    .directExecutor()
    .build();

GreeterGrpc.GreeterBlockingStub stub =
    GreeterGrpc.newBlockingStub(channel);
```

ServerInterceptors.intercept bọc ServiceDefinition với interceptor được chỉ định. Cách này kiểm tra interceptor implementation và service dispatch. Nếu cần kiểm tra global interceptor hoặc server customizer do Spring starter đăng ký, phải khởi động Spring context theo cấu hình ứng dụng thay vì tự bọc service trong test fixture.

Tạo server name mới cho từng fixture. Đóng channel trước server trong teardown và đặt timeout hữu hạn cho shutdown để tránh test suite bị treo.

## 9. Kiểm thử metadata và Context khi được phép

Client test có thể gắn authorization metadata bằng ClientInterceptor:

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ClientInterceptors;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;

ClientInterceptor authHeader = new ClientInterceptor() {
    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {
        return new ForwardingClientCall.SimpleForwardingClientCall<>(
                next.newCall(method, callOptions)) {
            @Override
            public void start(
                    Listener<RespT> responseListener,
                    Metadata requestHeaders) {
                requestHeaders.put(
                    AUTHORIZATION, "Bearer test-token");
                super.start(responseListener, requestHeaders);
            }
        };
    }
};

Channel authenticatedChannel =
    ClientInterceptors.intercept(channel, authHeader);
GreeterGrpc.GreeterBlockingStub authenticatedStub =
    GreeterGrpc.newBlockingStub(authenticatedChannel);

HelloReply reply = authenticatedStub.sayHello(request);
```

Trong test, TokenVerifier có thể nhận token giả đã định trước và trả về principal test. Service handler đọc AuthServerInterceptor.PRINCIPAL.get() rồi lưu giá trị vào AtomicReference để test assertion sau khi RPC hoàn tất.

Ví dụ handler ghi nhận principal từ Context để test xác minh:

```java
final class GreeterService extends GreeterGrpc.GreeterImplBase {
    private final AtomicReference<String> observedPrincipal;

    GreeterService(AtomicReference<String> observedPrincipal) {
        this.observedPrincipal = observedPrincipal;
    }

    @Override
    public void sayHello(
            HelloRequest request,
            StreamObserver<HelloReply> observer) {
        observedPrincipal.set(AuthServerInterceptor.PRINCIPAL.get());
        observer.onNext(HelloReply.newBuilder()
            .setMessage("Hello, " + request.getName())
            .build());
        observer.onCompleted();
    }
}
```

Sau khi gọi bằng authenticatedStub, assertion trên thread test có thể xác minh observedPrincipal bằng principal do test verifier trả về. Dùng AtomicReference ở đây là trạng thái quan sát của test fixture; không biến nó thành field lưu identity dùng chung trong service production.

Test cần xác minh:

- Header được gửi đúng key/value.
- Verifier nhận credential và trả principal mong đợi.
- Handler thấy principal qua Context.
- Hai call với principal khác nhau không rò dữ liệu cho nhau.
- Token không xuất hiện trong log.

Không dùng token production trong test. Credential test nên là dữ liệu giả và verifier test phải có behavior xác định.

## 10. Kiểm thử bị từ chối và không gọi handler

Khi metadata thiếu hoặc token sai, test cần xác minh cả status và việc service handler không chạy:

```java
StatusRuntimeException error = assertThrows(
    StatusRuntimeException.class,
    () -> GreeterGrpc.newBlockingStub(channel).sayHello(request));

assertEquals(
    Status.Code.UNAUTHENTICATED,
    error.getStatus().getCode());
assertEquals(0, handlerInvocationCount.get());
```

Với identity hợp lệ nhưng thiếu quyền, kỳ vọng PERMISSION_DENIED. Dùng AtomicInteger trong service test double để đếm số lần handler được gọi; assertion sau call xác minh interceptor chặn trước khi dispatch.

Không chỉ kiểm tra status. Một interceptor có thể vô tình gọi next.startCall rồi mới close call; test handler invocation sẽ phát hiện business code đã chạy dù client nhận lỗi. Tương tự, test authorization cần dùng principal có quyền và không có quyền để xác minh cả hai nhánh.

## 11. Spring wiring và ranh giới integration test

In-process test với ServerInterceptors.intercept kiểm tra logic interceptor, nhưng không chứng minh Spring gRPC starter đã đăng ký interceptor bean đúng. Để xác minh wiring:

1. Tạo Spring test context dùng đúng starter và cấu hình ứng dụng.
2. Đăng ký service, authentication verifier và interceptor như production.
3. Khởi động server do Spring quản lý trên port test hoặc port động.
4. Gọi RPC bằng stub qua channel tới server đó.
5. Kiểm tra allow/deny, Context propagation, interceptor ordering và shutdown lifecycle.

Extension point để đăng ký global/server interceptor phụ thuộc phiên bản starter. Dùng cơ chế mà phiên bản dự án hỗ trợ; không giả định mọi starter tự động đăng ký mọi bean implement ServerInterceptor.

TCP/TLS integration test cần thiết khi xác minh certificate, HTTP/2, ingress, service mesh, proxy hoặc metadata qua transport thật. In-process transport không kiểm tra những ranh giới đó.

## 12. Ma trận kiểm thử và bài tập vận dụng

| Nhóm | Ca kiểm thử | Điều kiện PASS |
| --- | --- | --- |
| Authentication | Token hợp lệ | Call tới handler và Context có principal |
| Missing credential | Không có authorization metadata | UNAUTHENTICATED, handler không chạy |
| Invalid credential | Token sai/hết hạn | UNAUTHENTICATED |
| Authorization | Principal thiếu quyền | PERMISSION_DENIED, handler không chạy |
| Method policy | GetOrder và CancelOrder | Mỗi method áp dụng đúng permission |
| Context | Hai call với principal khác nhau | Không rò principal giữa call |
| Metadata | Request ID và credential | Đọc đúng key, không log secret |
| Interceptor order | Nhiều interceptor | Thứ tự thực tế đúng thiết kế |
| Error path | Verifier/dependency lỗi | Status mapping theo policy |
| Concurrency | Nhiều call đồng thời | Không dùng mutable state chung cho call |
| Spring wiring | Starter quản lý server | Interceptor bean được đăng ký thực tế |
| Transport | TCP/TLS | Certificate, HTTP/2 và proxy hoạt động |

**Bài tập:** OrderService có GetOrder chỉ cho role ORDER_READ và CancelOrder chỉ cho role ORDER_ADMIN. Mọi call cần bearer token, request ID và audit record; health probe có policy riêng.

1. Viết AuthServerInterceptor xác minh token và gắn principal vào Context.
2. Viết authorization policy theo full method name cho GetOrder và CancelOrder.
3. Dùng in-process server để test token hợp lệ, thiếu token, token sai và role không đủ quyền.
4. Xác minh handler không chạy khi interceptor từ chối call.
5. Gửi hai call đồng thời với principal khác nhau và kiểm tra Context isolation.
6. Kiểm tra thứ tự tracing, authentication, authorization và logging interceptor.
7. Viết Spring context test xác minh starter đăng ký interceptor bean.
8. Bổ sung TCP/TLS test để xác minh metadata và identity qua transport thật.

**Câu hỏi tự kiểm tra:**

- ServerInterceptor chạy ở giai đoạn nào của gRPC call?
- Vì sao không lưu principal trong field mutable của interceptor?
- Authentication khác authorization thế nào?
- Khi từ chối call, vì sao phải đóng ServerCall và không gọi next?
- Contexts.interceptCall giúp điều gì cho callback?
- Full method name được tạo từ những thành phần nào?
- Vì sao cần test handler invocation count bên cạnh status?
- Thứ tự interceptor có thể ảnh hưởng authentication và logging ra sao?
- In-process test không xác minh được phần nào của Spring/TCP/TLS integration?

**Ghi nhớ:** Test server interceptor phải kiểm tra cả call được phép và bị từ chối. Xác minh metadata, token verifier, principal trong Context, method-specific permission, status và việc handler có được gọi hay không. Dùng in-process server để kiểm tra call pipeline; dùng Spring context test để xác minh interceptor wiring và TCP/TLS integration test để kiểm tra transport production.
