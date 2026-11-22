# Context chứa principal và quyền

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của **io.grpc.Context** trong việc gắn principal và quyền với một RPC cụ thể.
- Phân biệt Context nội bộ của grpc-java với metadata được truyền qua network.
- Tạo principal bất biến từ credential đã xác minh và lưu bằng một Context key dùng chung.
- Đọc principal trong authorization interceptor, adapter và application service.
- Truyền Context an toàn qua callback, executor và tác vụ bất đồng bộ.
- Hiểu cách deadline, cancellation và Context con kế thừa trạng thái của RPC.
- Tránh context leak, nhầm principal giữa các request và lưu dữ liệu nhạy cảm không cần thiết.
- Kiểm thử context propagation và authorization trong ứng dụng Spring gRPC.

## 1. Context gắn dữ liệu với vòng đời của một RPC

Trong **SPRING_GRPC**, một request thường cần danh tính caller, tenant và tập quyền đã được xác minh ở nhiều lớp: interceptor, gRPC adapter và application service. Truyền tất cả thông tin này qua từng tham số có thể làm chữ ký phương thức phình to; dùng biến toàn cục hoặc ThreadLocal tự viết lại dễ gây nhầm dữ liệu giữa các request.

**io.grpc.Context** là cơ chế của grpc-java để gắn dữ liệu có phạm vi thực thi với một call. Một Context có thể chứa principal, correlation data hoặc thông tin bảo mật cần dùng trong quá trình xử lý RPC. Context hiện hành được runtime gắn vào luồng thực thi trong các callback; code có thể đọc giá trị thông qua Context key.

Luồng điển hình:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant A as Authentication interceptor
    participant X as Authorization interceptor
    participant H as Service handler
    participant U as Application use case
    C->>A: RPC + credential metadata
    A->>A: Verify credential
    A->>A: Create immutable principal
    A->>X: Context chứa principal
    X->>X: Read principal và check permission
    X->>H: Cho phép gọi handler
    H->>U: Xử lý command
    U->>U: Đọc principal hoặc nhận actor tường minh
    U-->>C: Response / gRPC status
~~~

Context phù hợp cho dữ liệu gắn với **một lần thực thi RPC**. Nó không phải nơi lưu session lâu dài, không phải kho chia sẻ giữa các instance và không tự truyền dữ liệu sang một service khác qua network.

## 2. Context khác metadata như thế nào?

Metadata là dữ liệu gRPC truyền qua network trong request headers hoặc response trailers. Context là cơ chế nội bộ trong process để truyền dữ liệu giữa các lớp/callback.

| Đặc điểm | gRPC Metadata | io.grpc.Context |
| --- | --- | --- |
| Phạm vi | Qua ranh giới client/server | Trong process và execution scope |
| Nguồn | Client, server hoặc interceptor | Server/runtime hoặc code nội bộ |
| Ví dụ | Authorization header, trace header | Principal đã xác minh, permission set |
| Tin cậy | Input phải được xác minh | Giá trị nội bộ được code đáng tin cậy đặt |
| Truyền sang service khác | Có thể gửi qua metadata sau khi chọn lọc | Không tự truyền qua network |
| Vòng đời | Gắn với request/response metadata | Gắn với execution/call context |

Client có thể gửi authorization metadata chứa bearer token. Authentication interceptor đọc token, xác minh chữ ký, issuer, audience, expiry và các claim theo contract. Sau khi xác minh, interceptor tạo principal và đặt vào Context.

Không đặt nguyên metadata tùy ý vào Context rồi coi mọi field là đáng tin. Giá trị trong Context chỉ đáng tin khi thành phần tạo nó đã xác thực và chuẩn hóa dữ liệu. Một custom header x-role: admin vẫn là input không tin cậy cho tới khi được chứng minh bởi credential hoặc nguồn policy tin cậy.

## 3. Principal nên bất biến và chỉ chứa dữ liệu cần thiết

Principal biểu diễn danh tính đã xác minh và các thuộc tính bảo mật cần cho quyết định. Ví dụ:

~~~java
package dev.example.security;

import java.util.Set;

public record GrpcPrincipal(
        String subject,
        String tenantId,
        Set<String> permissions) {

    public GrpcPrincipal {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId is required");
        }
        permissions = Set.copyOf(permissions);
    }

    public boolean hasPermission(String permission) {
        return permissions.contains(permission);
    }
}
~~~

Set.copyOf tạo tập quyền không thể sửa thông qua reference bên ngoài. Tính bất biến giúp các callback cùng đọc một principal mà không lo một lớp khác âm thầm thay đổi quyền trong lúc RPC đang chạy.

Chỉ đưa dữ liệu cần thiết vào principal:

- Subject hoặc service identity đã xác minh.
- Tenant hoặc phạm vi tenant đã được xác minh.
- Permission/authority đã chuẩn hóa theo policy.
- Một số claim cần thiết để quyết định authorization.

Không đưa access token thô, refresh token, private key, toàn bộ JWT payload, entity database lớn hoặc object mutable vào Context. Nếu cần token để gọi downstream, giữ credential trong thành phần quản lý credential và chỉ truyền dữ liệu tối thiểu qua ranh giới được kiểm soát.

Principal cũng không nên là singleton Spring bean mutable. Mỗi RPC có principal riêng, được gắn vào Context của call đó.

## 4. Dùng một Context.Key dùng chung

Để đọc cùng một giá trị ở nhiều lớp, khai báo Context key đúng một lần:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

Context.Key là đối tượng định danh; tên chuỗi chủ yếu hỗ trợ debug. Gọi Context.key("authenticated-principal") ở hai lớp khác nhau sẽ tạo hai key khác nhau, dù tên giống nhau. Vì vậy, authentication và authorization phải import cùng GrpcSecurityContext.PRINCIPAL.

Tránh khai báo key bên trong phương thức interceptCall hoặc tạo key mới mỗi lần request. Key nên là static final và dùng xuyên suốt pipeline.

## 5. Authentication interceptor đặt principal vào Context

Authentication interceptor chịu trách nhiệm xác minh credential. Sau khi tạo được principal đáng tin cậy, nó tạo Context con bằng withValue và gọi Contexts.interceptCall để chạy phần pipeline tiếp theo trong Context đó.

Ví dụ abstraction xác minh credential:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import java.util.Optional;

public interface CredentialAuthenticator {
    Optional<GrpcPrincipal> authenticate(Metadata headers);
}
~~~

Interceptor:

~~~java
package dev.example.security;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class AuthenticationServerInterceptor
        implements ServerInterceptor {

    private final CredentialAuthenticator authenticator;

    public AuthenticationServerInterceptor(
            CredentialAuthenticator authenticator) {
        this.authenticator = authenticator;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        var authenticated = authenticator.authenticate(headers);

        if (authenticated.isEmpty()) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context = Context.current().withValue(
                GrpcSecurityContext.PRINCIPAL,
                authenticated.get());

        return Contexts.interceptCall(context, call, headers, next);
    }
}
~~~

Contexts.interceptCall gọi bước tiếp theo dưới Context được cung cấp và bọc listener để callback nhận message/cancel/close cũng chạy trong Context tương ứng. Nhờ đó, authorization interceptor và handler có thể đọc principal qua Context.current() hoặc Context key.

Nếu credential không hợp lệ, interceptor đóng call bằng UNAUTHENTICATED, trả listener rỗng và không chuyển tiếp tới service. Không tạo principal mặc định hoặc đặt permission rộng để cho request chạy tiếp.

## 6. Authorization đọc principal từ Context

Authorization interceptor đọc principal bằng cùng key, sau đó kiểm tra permission cho method thực tế:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class AuthorizationServerInterceptor
        implements ServerInterceptor {

    private final GrpcMethodPolicy policy;

    public AuthorizationServerInterceptor(GrpcMethodPolicy policy) {
        this.policy = policy;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        GrpcPrincipal principal =
                GrpcSecurityContext.PRINCIPAL.get();

        if (principal == null) {
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        String method =
                call.getMethodDescriptor().getFullMethodName();

        if (!policy.allows(principal, method)) {
            call.close(
                    Status.PERMISSION_DENIED
                            .withDescription("Permission denied"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        return next.startCall(call, headers);
    }
}
~~~

Authentication phải chạy trước authorization. Có thể dùng ServerInterceptors.interceptForward để thể hiện thứ tự mong muốn:

~~~java
ServerServiceDefinition securedService =
        ServerInterceptors.interceptForward(
                orderService,
                authenticationInterceptor,
                authorizationInterceptor);

serverBuilder.addService(securedService);
~~~

Trong Spring gRPC starter, đăng ký interceptor qua extension point/bean registration của phiên bản starter đang sử dụng. Không tự tạo server thứ hai nếu starter đã quản lý server. Hãy viết integration test để xác minh authorization thực sự nhìn thấy principal đã được authentication đặt vào Context.

## 7. Đọc principal trong adapter và application service

Trong callback xử lý RPC, code có thể lấy principal hiện hành:

~~~java
GrpcPrincipal principal =
        GrpcSecurityContext.PRINCIPAL.get();

if (principal == null) {
    throw Status.UNAUTHENTICATED
            .withDescription("Authentication required")
            .asRuntimeException();
}
~~~

Adapter có thể chuyển principal thành actor/command tường minh khi gọi application service:

~~~java
public GetOrderResponse getOrder(GetOrderRequest request) {
    GrpcPrincipal principal =
            GrpcSecurityContext.PRINCIPAL.get();

    OrderView result = getOrderUseCase.execute(
            principal,
            request.getOrderId());

    return OrderMapper.toProto(result);
}
~~~

Cách truyền principal tường minh vào use case làm dependency bảo mật dễ nhìn thấy và dễ unit test. Context giúp adapter/interceptor lấy dữ liệu gắn với RPC; nó không bắt buộc mọi lớp domain phải phụ thuộc trực tiếp vào grpc-java.

Với code domain độc lập transport, nên chuyển principal thành một kiểu Actor hoặc CurrentUser của application. Không để domain gọi GrpcSecurityContext.PRINCIPAL.get() ở khắp nơi vì điều đó làm logic nghiệp vụ phụ thuộc execution context ngầm.

## 8. Context là bất biến; withValue tạo Context con

Các thao tác trên Context không sửa object hiện tại. withValue trả về một Context con chứa key/value bổ sung hoặc ghi đè giá trị cho key đó:

~~~java
Context parent = Context.current();

Context child = parent.withValue(
        GrpcSecurityContext.PRINCIPAL,
        principal);
~~~

Context con kế thừa các giá trị khác từ parent, bao gồm deadline/cancellation state theo cơ chế Context. Vì vậy, không dùng Context.ROOT một cách tùy tiện khi thêm principal; làm vậy có thể tách công việc khỏi Context hiện tại và mất các thông tin như deadline hoặc cancellation.

Context key có thể được shadow trong Context con. Điều này hữu ích khi cần tạo execution scope khác, nhưng không nên thay principal giữa một RPC trừ khi có lý do bảo mật và ranh giới rõ ràng. Không dùng Context như một map mutable dùng chung giữa các request.

## 9. Truyền Context qua executor và tác vụ bất đồng bộ

Context được grpc-java gắn vào các callback mà runtime quản lý. Khi ứng dụng tự chuyển việc sang thread pool hoặc executor riêng, không nên giả định Context sẽ tự truyền sang thread mới.

Có thể capture Context hiện tại và wrap tác vụ:

~~~java
Context captured = Context.current();

executor.execute(captured.wrap(() -> {
    GrpcPrincipal principal =
            GrpcSecurityContext.PRINCIPAL.get();

    processForTenant(principal.tenantId());
}));
~~~

Hoặc tạo executor có khả năng gắn Context tại thời điểm submit:

~~~java
Executor contextAwareExecutor =
        Context.currentContextExecutor(executor);

CompletableFuture.supplyAsync(
        () -> useCase.execute(command),
        contextAwareExecutor);
~~~

Capture Context ở đúng thời điểm tạo tác vụ. Không giữ Context của một RPC rồi dùng lại cho request khác. Nếu công việc được đưa vào queue để chạy sau khi RPC kết thúc, hãy cân nhắc truyền actor/tenant/operation tường minh trong job envelope thay vì giữ toàn bộ Context sống lâu.

Nếu tác vụ chạy trong scheduler, batch worker hoặc message consumer không có RPC hiện hành, Context.current() có thể là Context mặc định và không có principal. Worker cần identity riêng và dữ liệu actor/tenant được xác minh theo contract của job.

## 10. Deadline và cancellation đi cùng Context

Context có thể mang deadline và trạng thái cancellation. Context con tạo bằng withValue tiếp tục kế thừa các thuộc tính này.

Điều đó có ý nghĩa thực tế:

- Nếu caller hủy RPC, tác vụ chạy trong Context được truyền đúng có thể quan sát cancellation và dừng sớm.
- Nếu deadline hết, công việc downstream nên dừng hoặc không bắt đầu khi không còn ngân sách.
- Khi wrap executor, capture đúng Context để tác vụ không vô tình chạy như một công việc độc lập không deadline.
- Nếu công việc phải tiếp tục sau khi RPC kết thúc, thiết kế nó như job độc lập với lifecycle, timeout và identity riêng.

Không giữ một Context request lâu hơn cần thiết. Một task bị treo có thể giữ reference tới principal và dữ liệu gắn với request. Cleanup listener, subscription và future khi cancellation xảy ra.

## 11. Context không tự truyền sang service khác

io.grpc.Context chỉ là execution context trong process hiện tại. Khi Spring gRPC service gọi một gRPC service khác, Context không tự biến thành metadata trên outbound request.

Nếu downstream cần xác thực caller hoặc workload, client phải gửi credential/identity qua cơ chế được thiết kế rõ ràng:

- Dùng service identity hoặc mTLS để xác minh workload gọi downstream.
- Nếu cần delegated user identity, dùng token exchange/delegation phù hợp; không gửi nguyên principal object như một header tùy ý.
- Chỉ propagate trace context/correlation metadata đã được chuẩn hóa.
- Không forward toàn bộ inbound metadata một cách mù quáng.
- Downstream tự xác minh credential và tạo principal Context của chính nó.

Ví dụ, service A có thể biết user U đã được xác minh. Khi gọi service B, A không thể đơn giản serialize GrpcPrincipal vào x-principal rồi mong B tin. B cần xác minh service A và/hoặc delegated token theo trust model.

## 12. Tránh context leak và lỗi bảo mật

Các lỗi thường gặp:

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tạo Context key riêng ở mỗi interceptor | Authorization không đọc được principal | Dùng một static final key dùng chung |
| Principal lưu trong singleton mutable | Request đồng thời có thể ghi đè danh tính nhau | Principal bất biến, gắn theo Context từng call |
| Tin role/tenant từ metadata chưa xác minh | Caller tự nâng quyền hoặc đổi tenant | Xác minh credential/membership trước khi tạo principal |
| Tác vụ executor không capture Context | Mất principal, deadline hoặc cancellation | Dùng Context.wrap/context-aware executor |
| Giữ Context của RPC trong job dài hạn | Giữ reference và lifecycle không phù hợp | Truyền actor/tenant tường minh vào job |
| Dùng Context.ROOT không cần thiết | Mất parent deadline/cancellation và giá trị khác | Tạo Context con từ Context.current() |
| Gửi principal object sang service khác | Tin cậy sai ranh giới process | Gửi credential/delegation có xác minh |
| Không kiểm tra principal null | Null dereference hoặc fallback allow | Trả UNAUTHENTICATED, không mặc định quyền |
| Ghi token/principal nhạy cảm vào log | Lộ credential và dữ liệu cá nhân | Redact và chỉ log định danh tối thiểu |

Không gọi attach() mà quên detach() trong code thủ công. Nếu phải attach Context ngoài cơ chế Contexts.interceptCall/Context.wrap, luôn khôi phục Context trước đó trong finally. Ưu tiên API wrapper có sẵn để giảm nguy cơ rò rỉ Context giữa các tác vụ dùng chung thread.

## 13. Kiểm thử Context và principal propagation

Test nên xác minh dữ liệu của từng RPC không bị trộn và các callback bất đồng bộ nhìn thấy đúng Context.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Credential hợp lệ | Principal xuất hiện trong authorization interceptor |
| Credential không hợp lệ | UNAUTHENTICATED; handler không chạy |
| Principal thiếu permission | PERMISSION_DENIED; handler không chạy |
| Hai RPC đồng thời với principal khác nhau | Mỗi handler đọc đúng subject/tenant của call mình |
| Executor được wrap Context | Tác vụ đọc đúng principal đã capture |
| Executor không có Context | Không có principal; không fallback sang request trước |
| RPC bị cancel | Tác vụ có Context quan sát cancellation và cleanup |
| Deadline hết | Downstream không tiếp tục vô hạn |
| Context con dùng withValue | Kế thừa parent state và ghi đè đúng key |
| Outbound call sang service khác | Identity được propagate bằng credential/delegation đã xác minh, không phải Context object |

Có thể dùng in-process gRPC test để đăng ký authentication/authorization interceptor như production, gọi qua generated stub và assert principal trong handler. Dùng latch/barrier để chạy hai RPC đồng thời với hai principal khác nhau; test này giúp phát hiện việc dùng ThreadLocal hoặc field mutable sai cách.

Với executor, tạo một tác vụ trong lúc Context có principal A, wrap Context rồi thực thi; xác minh tác vụ thấy A. Sau đó chạy tác vụ không có Context và xác minh không thấy principal A. Bổ sung test cancellation/deadline để chắc chắn công việc nền được dừng hoặc kết thúc theo policy.

## 14. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo GrpcPrincipal bất biến chứa subject, tenant và permissions.
2. Tạo GrpcSecurityContext.PRINCIPAL là một Context key dùng chung.
3. Viết authentication interceptor xác minh credential giả lập và gắn principal bằng Context.current().withValue.
4. Dùng Contexts.interceptCall để chuyển Context sang interceptor/handler tiếp theo.
5. Viết authorization interceptor đọc cùng key và trả UNAUTHENTICATED hoặc PERMISSION_DENIED đúng trường hợp.
6. Đọc principal trong gRPC adapter rồi truyền actor tường minh vào application use case.
7. Chạy tác vụ executor bằng Context.current().wrap(...) và xác minh principal/deadline được giữ.
8. Viết integration test cho hai RPC đồng thời, cancellation, context missing và outbound identity propagation.

### Câu hỏi tự kiểm tra

**1. io.grpc.Context dùng để làm gì?**  
Gắn dữ liệu theo execution scope của RPC để interceptor, listener và callback trong cùng process có thể đọc đúng thông tin.

**2. Context có được gửi qua network như metadata không?**  
Không. Context là nội bộ process; muốn downstream xác minh identity phải truyền credential/delegation qua metadata theo trust model.

**3. Vì sao phải dùng chung một Context.Key instance?**  
Vì key là định danh đối tượng. Hai key tạo riêng dù cùng tên không đọc cùng một giá trị.

**4. Principal nên chứa dữ liệu gì?**  
Chỉ subject, tenant, permission và thuộc tính bảo mật tối thiểu đã xác minh; không chứa token thô hoặc object mutable lớn.

**5. Vì sao không dùng ThreadLocal tự viết?**  
Thread pool tái sử dụng thread và tác vụ có thể đổi thread; nếu không quản lý attach/cleanup chính xác, dữ liệu caller trước có thể rò sang request sau.

**6. Context có tự truyền qua executor không?**  
Không nên giả định. Capture Context hiện tại rồi dùng Context.wrap hoặc context-aware executor.

**7. Vì sao Context con nên tạo từ Context.current()?**  
Để kế thừa deadline, cancellation và các giá trị parent cần thiết cho lifecycle của RPC.

**8. Khi nào không nên giữ Context?**  
Khi công việc sống lâu hơn RPC hoặc chạy trong queue/scheduler độc lập; hãy truyền actor/tenant/operation tường minh và dùng identity riêng cho worker.

## Tổng kết

**io.grpc.Context** là execution scope nội bộ để gắn principal và quyền đã xác minh với một RPC. Authentication interceptor tạo principal bất biến và đặt nó dưới một Context key dùng chung; authorization interceptor, listener và handler đọc cùng giá trị trong đúng call. Context con kế thừa deadline/cancellation, nhưng tác vụ do ứng dụng tự chuyển sang executor phải capture và wrap Context rõ ràng. Context không truyền qua network, không thay credential khi gọi downstream và không nên sống lâu hơn RPC. Dùng principal tối thiểu, key dùng chung, Context propagation có kiểm soát và test các RPC đồng thời giúp tránh nhầm danh tính hoặc rò rỉ quyền giữa request.

