# Context chứa principal và quyền

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao gRPC cần một execution context để mang principal và quyền đã xác minh qua các callback của cùng một RPC.
- Phân biệt **io.grpc.Context** với gRPC Metadata và với session lưu lâu dài.
- Tạo principal bất biến, tối thiểu và đặt vào Context bằng một **Context.Key** dùng chung.
- Kết hợp authentication interceptor, authorization interceptor và service handler đúng thứ tự.
- Truyền Context qua executor, CompletableFuture và callback bất đồng bộ mà không làm lẫn danh tính.
- Hiểu quan hệ giữa Context, deadline và cancellation.
- Nhận biết ranh giới process: Context không tự truyền sang gRPC service khác.
- Kiểm thử context propagation, request đồng thời và trường hợp thiếu principal để phát hiện context leak.

## 1. Vì sao cần Context chứa principal?

Trong **SPRING_GRPC**, một RPC thường đi qua nhiều lớp: authentication interceptor, authorization interceptor, gRPC adapter và application service. Các lớp này có thể cần cùng một số thông tin đã được xác minh như subject, tenant và permission. Nếu mỗi lớp tự đọc token hoặc tự diễn giải metadata, logic bảo mật dễ bị lặp và không nhất quán.

**io.grpc.Context** là cơ chế của grpc-java để gắn dữ liệu với một phạm vi thực thi. Server có thể đặt principal sau khi xác minh credential; các interceptor và callback tiếp theo của cùng RPC đọc principal đó mà không cần client gửi lại danh tính trong từng message.

Context giải quyết việc truyền dữ liệu trong một process và trong vòng đời xử lý call. Nó không xác thực token, không tự quyết định quyền, không lưu session lâu dài và không thay thế database hay identity provider.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant A as Authentication interceptor
    participant Z as Authorization interceptor
    participant H as Service handler
    participant U as Application use case
    C->>A: RPC + credential metadata
    A->>A: Verify credential
    A->>A: Create immutable principal
    A->>Z: Context chứa principal
    Z->>Z: Read principal và check permission
    Z->>H: Cho phép handler chạy
    H->>U: Command + actor
    U-->>C: Response hoặc gRPC status
~~~

Một RPC có một execution context hiện hành tại mỗi thời điểm xử lý. Khi runtime gọi callback trong context đó, code có thể truy xuất principal đã gắn vào call. Khi một request khác chạy đồng thời, request đó có Context riêng; principal của request này không được dùng chung với request kia.

## 2. Context khác Metadata và session như thế nào?

Metadata là dữ liệu gRPC truyền qua network trong request headers hoặc response trailers. Context là cơ chế nội bộ process để truyền dữ liệu trong execution flow. Session hoặc server-side store lại có vòng đời dài hơn một RPC.

| Đặc điểm | gRPC Metadata | io.grpc.Context | Session/store |
| --- | --- | --- | --- |
| Phạm vi | Qua network | Trong process | Có thể qua nhiều request |
| Vòng đời | Request/response metadata | Execution/call scope | Theo TTL hoặc quy trình đăng xuất |
| Nguồn | Client, server, interceptor | Runtime hoặc code nội bộ | Database/cache/session service |
| Ví dụ | Bearer token, trace header | Principal đã xác minh, deadline | Refresh session, user preferences |
| Tin cậy | Phải xác minh input | Tin cậy tùy thành phần đã đặt value | Theo quyền truy cập store |
| Tự truyền sang service khác | Có thể chọn lọc gửi tiếp | Không | Không tự động |

Client có thể gửi bearer token trong Metadata. Authentication interceptor đọc token, xác minh chữ ký, issuer, audience, expiry và claim theo contract. Sau đó interceptor tạo principal đã chuẩn hóa và đặt vào Context.

Không sao chép toàn bộ Metadata vào Context rồi xem mọi field là đáng tin. Header như x-role hoặc x-tenant-id do client tự gửi vẫn là input không tin cậy cho tới khi được xác minh bằng credential hoặc nguồn policy phù hợp.

## 3. Principal nên bất biến và chỉ chứa dữ liệu cần thiết

Principal biểu diễn danh tính và thuộc tính bảo mật đã được xác minh. Ví dụ:

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

Record cùng Set.copyOf giúp principal không bị thay đổi thông qua reference bên ngoài. Đây là điều quan trọng vì nhiều callback có thể đọc principal trong khi RPC đang chạy. Context bản thân nó bất biến, nhưng value được lưu trong Context không tự động trở nên bất biến. Nếu đặt một object mutable vào Context, code khác vẫn có thể sửa object đó.

Chỉ giữ thông tin cần cho quyết định:

- Subject hoặc service identity đã xác minh.
- Tenant hoặc tập tenant được phép đã xác minh.
- Permission/authority đã chuẩn hóa.
- Một số claim tối thiểu cần thiết cho authorization.

Không đưa access token thô, refresh token, private key, toàn bộ JWT payload, entity database lớn hoặc dữ liệu cá nhân không cần thiết vào Context. Context không phải kho bí mật; các giá trị có thể bị quan sát bởi code chạy trong cùng process.

Principal cũng không nên là singleton Spring bean mutable. Mỗi RPC phải có principal tương ứng với caller của chính call đó.

## 4. Dùng một Context.Key dùng chung

Để nhiều lớp đọc cùng một principal, khai báo key một lần:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

Context.Key là đối tượng định danh. Chuỗi tên như authenticated-principal hữu ích cho debug, nhưng không phải cơ chế để hai key độc lập tự động tương đương. Nếu authentication interceptor gọi Context.key một lần và authorization interceptor gọi Context.key lần khác, chúng có hai key khác nhau dù cùng tên.

Vì vậy:

- Khai báo key là static final ở một lớp dùng chung.
- Authentication và authorization import đúng key đó.
- Không tạo key bên trong interceptCall hoặc trong mỗi request.
- Không tạo một key khác cùng tên trong module khác rồi kỳ vọng đọc cùng giá trị.

Khi đọc principal, giá trị null có nghĩa Context hiện tại chưa chứa principal. Xử lý như chưa xác thực và từ chối; không tự tạo principal mặc định hoặc fallback sang một caller trước đó.

## 5. Authentication interceptor đặt principal vào Context

Authentication interceptor chịu trách nhiệm xác minh credential và tạo principal. Có thể tách việc xác minh thành abstraction để thay JWT, mTLS hoặc identity provider mà không đổi cách Context được sử dụng:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import java.util.Optional;

public interface CredentialAuthenticator {
    Optional<GrpcPrincipal> authenticate(Metadata headers);
}
~~~

Interceptor đặt principal sau khi xác minh thành công:

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

withValue tạo một Context con chứa principal. Contexts.interceptCall thực thi phần pipeline tiếp theo trong Context đó và bọc listener để callback của RPC tiếp tục chạy với Context tương ứng. Vì vậy authorization interceptor và service handler có thể đọc cùng principal.

Nếu credential không hợp lệ, interceptor đóng call bằng UNAUTHENTICATED và không gọi next. Không đặt principal rỗng hoặc permission rộng để cho request đi tiếp.

## 6. Authorization interceptor đọc cùng principal

Authorization interceptor sử dụng đúng key mà authentication đã đặt:

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

        String fullMethodName =
                call.getMethodDescriptor().getFullMethodName();

        if (!policy.allows(principal, fullMethodName)) {
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

Authentication phải chạy trước authorization. Với grpc-java có thể biểu diễn thứ tự này khi bọc service:

~~~java
ServerServiceDefinition securedService =
        ServerInterceptors.interceptForward(
                orderService,
                authenticationInterceptor,
                authorizationInterceptor);

serverBuilder.addService(securedService);
~~~

Trong Spring gRPC starter, đăng ký interceptor qua extension point/bean registration mà phiên bản starter đang dùng hỗ trợ. Không tạo server thứ hai nếu starter đã quản lý server. Viết integration test để xác minh authorization nhìn thấy principal được authentication đặt vào Context.

Nếu principal null, trả UNAUTHENTICATED. Nếu principal tồn tại nhưng thiếu quyền, trả PERMISSION_DENIED. Không gọi next.startCall khi đã từ chối; handler không được chạy.

## 7. Đọc principal ở gRPC adapter và truyền vào use case

Trong adapter, có thể đọc principal hiện hành rồi chuyển thành actor/command tường minh:

~~~java
public GetOrderResponse getOrder(GetOrderRequest request) {
    GrpcPrincipal principal =
            GrpcSecurityContext.PRINCIPAL.get();

    if (principal == null) {
        throw Status.UNAUTHENTICATED
                .withDescription("Authentication required")
                .asRuntimeException();
    }

    OrderView result = getOrderUseCase.execute(
            principal,
            request.getOrderId());

    return OrderMapper.toProto(result);
}
~~~

Truyền principal hoặc kiểu Actor của application vào use case làm dependency bảo mật hiển thị rõ trong chữ ký phương thức và dễ unit test. Context giúp interceptor/adapter lấy dữ liệu gắn với RPC; không bắt buộc mọi lớp domain phải phụ thuộc grpc-java.

Với domain model độc lập transport, nên chuyển principal thành kiểu Actor/CurrentUser của application. Tránh để domain gọi GrpcSecurityContext.PRINCIPAL.get() ở khắp nơi vì sẽ tạo dependency ngầm vào execution context.

Method-level authorization ở interceptor vẫn chưa đủ cho mọi thao tác. Use case cần kiểm tra tenant, ownership và quyền trên resource cụ thể trước business action. Context chỉ mang dữ liệu để quyết định; nó không tự thực hiện authorization.

## 8. Context bất biến và Context con

Context không bị sửa tại chỗ. withValue trả về một Context con với key/value mới:

~~~java
Context parent = Context.current();

Context child = parent.withValue(
        GrpcSecurityContext.PRINCIPAL,
        principal);
~~~

Context con kế thừa các giá trị khác từ parent. Điều này quan trọng vì Context hiện hành có thể chứa deadline, cancellation và dữ liệu khác của RPC. Khi thêm principal, thường nên tạo Context con từ Context.current() thay vì dùng Context.ROOT một cách tùy tiện.

Context key có thể bị shadow trong Context con. Kỹ thuật này có ích khi tạo execution scope riêng, nhưng không nên thay principal giữa một RPC nếu không có ranh giới bảo mật rõ ràng. Không dùng Context như map mutable chia sẻ giữa các request.

Một Context có thể chứa các giá trị khác nhau dưới nhiều key. Hãy đặt tên key có ý nghĩa, giới hạn số lượng dữ liệu và tránh đưa các object có vòng đời lớn vào Context vì chúng có thể được giữ tham chiếu trong suốt tác vụ.

## 9. Truyền Context qua executor và CompletableFuture

grpc-java quản lý Context cho các callback của RPC. Tuy nhiên khi ứng dụng tự chuyển việc sang thread pool hoặc executor, không nên giả định Context tự động được truyền sang thread mới.

Có thể capture Context hiện hành và wrap tác vụ:

~~~java
Context captured = Context.current();

executor.execute(captured.wrap(() -> {
    GrpcPrincipal principal =
            GrpcSecurityContext.PRINCIPAL.get();

    processForTenant(principal.tenantId());
}));
~~~

Hoặc tạo executor gắn Context tại thời điểm tạo wrapper:

~~~java
Executor contextAwareExecutor =
        Context.currentContextExecutor(executor);

CompletableFuture.supplyAsync(
        () -> useCase.execute(command),
        contextAwareExecutor);
~~~

Capture Context bên trong callback của RPC, tại thời điểm đã có principal. Context.wrap hoặc currentContextExecutor sẽ gắn Context đã capture khi tác vụ chạy và khôi phục Context trước đó sau khi callback kết thúc.

Không lưu một Context của request rồi tái sử dụng cho request khác. Nếu công việc được đưa vào queue và chạy sau khi RPC đã kết thúc, hãy truyền actor, tenant và operation cần thiết trong job envelope đã được bảo vệ, thay vì giữ toàn bộ Context của request sống lâu.

Nếu tác vụ chạy trong scheduler, batch worker hoặc message consumer không có RPC hiện hành, Context.current() có thể không chứa principal. Worker phải có service identity riêng và xác minh actor/tenant từ job contract; không lấy Context của một request trước đó làm fallback.

## 10. Deadline và cancellation gắn với Context

Context có thể mang deadline và trạng thái cancellation. Context con tạo từ Context hiện hành tiếp tục kế thừa lifecycle state theo cơ chế của grpc-java.

Điều đó giúp các tác vụ gắn với RPC phối hợp vòng đời:

- Khi caller hủy RPC, tác vụ chạy trong Context được truyền đúng có thể quan sát cancellation và dừng sớm.
- Khi deadline hết, công việc downstream nên dừng hoặc không bắt đầu nếu không còn ngân sách.
- Khi wrap executor, capture Context đúng thời điểm để tác vụ không vô tình chạy như công việc độc lập không deadline.
- Khi công việc phải tiếp tục sau khi RPC kết thúc, chuyển nó thành job độc lập với timeout và identity riêng.

Có thể kiểm tra Context hiện hành:

~~~java
Context current = Context.current();

if (current.isCancelled()) {
    return;
}

Deadline deadline = current.getDeadline();
if (deadline != null && deadline.isExpired()) {
    return;
}
~~~

Không giữ Context request lâu hơn cần thiết. Task bị treo có thể giữ reference tới principal và dữ liệu gắn với request. Khi cancellation xảy ra, cleanup listener, subscription, buffer và future phù hợp.

## 11. Context không tự truyền sang service khác

io.grpc.Context chỉ là execution context trong process hiện tại. Khi Spring gRPC service A gọi service B, Context không tự biến thành metadata trên outbound request.

Nếu downstream cần xác thực caller hoặc workload, client phải gửi credential/identity theo cơ chế được thiết kế rõ ràng:

- Dùng service identity hoặc mTLS để xác minh workload gọi downstream.
- Nếu cần delegated user identity, dùng token exchange hoặc delegation phù hợp.
- Chỉ propagate trace context/correlation metadata đã được chuẩn hóa.
- Không forward toàn bộ inbound metadata một cách mù quáng.
- Downstream tự xác minh credential và tạo principal Context của chính nó.

Ví dụ, service A có thể biết user U đã được xác minh. Khi gọi service B, A không thể serialize GrpcPrincipal thành x-principal rồi mong B tin. B cần xác minh service A và/hoặc delegated token theo trust model. Một Java object nội bộ không phải credential liên dịch vụ.

## 12. Tránh context leak và dữ liệu bảo mật không cần thiết

Các lỗi thường gặp:

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Tạo Context key riêng ở mỗi interceptor | Authorization không đọc được principal | Dùng một static final key dùng chung |
| Principal lưu trong singleton mutable | Request đồng thời ghi đè danh tính nhau | Principal bất biến, gắn theo Context từng call |
| Tin role/tenant từ metadata chưa xác minh | Caller tự nâng quyền hoặc đổi tenant | Xác minh credential/membership trước khi tạo principal |
| Tác vụ executor không capture Context | Mất principal, deadline hoặc cancellation | Dùng Context.wrap hoặc context-aware executor |
| Giữ Context của RPC trong job dài hạn | Giữ reference và lifecycle không phù hợp | Truyền actor/tenant tường minh vào job |
| Dùng Context.ROOT không cần thiết | Mất parent deadline/cancellation và giá trị khác | Tạo Context con từ Context.current() |
| Gửi principal object sang service khác | Tin cậy sai ranh giới process | Gửi credential/delegation có xác minh |
| Không kiểm tra principal null | Null dereference hoặc fallback allow | Trả UNAUTHENTICATED, không mặc định quyền |
| Ghi token/principal nhạy cảm vào log | Lộ credential và dữ liệu cá nhân | Redact và chỉ log định danh tối thiểu |

Không gọi attach() mà quên detach() trong code thủ công. Nếu phải attach Context ngoài cơ chế Contexts.interceptCall hoặc Context.wrap, luôn khôi phục Context trước đó trong finally. Ưu tiên API wrapper có sẵn để giảm nguy cơ rò Context giữa các tác vụ dùng chung thread.

Context chỉ là cơ chế truyền dữ liệu; nó không làm dữ liệu bên trong tự an toàn. Hãy giữ principal bất biến, không chứa token thô, giới hạn quyền truy cập log và không đặt dữ liệu nhạy cảm vào key có thể được nhiều thành phần đọc không cần thiết.

## 13. Kiểm thử Context và principal propagation

Test cần xác minh dữ liệu của từng RPC không bị trộn và các callback bất đồng bộ nhìn thấy đúng Context.

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
| Outbound call sang service khác | Identity được truyền bằng credential/delegation đã xác minh, không phải Context object |

Có thể dùng in-process gRPC test để đăng ký authentication/authorization interceptor như production, gọi qua generated stub và assert principal trong handler. Dùng latch/barrier để chạy hai RPC đồng thời với hai principal khác nhau; test này giúp phát hiện việc dùng ThreadLocal hoặc field mutable sai cách.

Với executor, tạo tác vụ trong lúc Context có principal A, wrap Context rồi thực thi; xác minh tác vụ thấy A. Sau đó chạy tác vụ không có Context và xác minh không thấy principal A. Bổ sung test cancellation/deadline để chắc chắn công việc nền được dừng hoặc kết thúc theo policy.

Một test quan trọng khác là cố tình khai báo hai Context key cùng tên nhưng khác instance trong test fixture để chứng minh authorization không đọc được principal. Sau đó dùng shared key và xác minh request được xử lý đúng. Test này bảo vệ khỏi lỗi refactor vô tình tạo key trùng tên.

## 14. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo GrpcPrincipal bất biến chứa subject, tenant và permissions đã xác minh.
2. Tạo GrpcSecurityContext.PRINCIPAL là một Context key dùng chung.
3. Viết authentication interceptor xác minh credential giả lập và gắn principal bằng Context.current().withValue.
4. Dùng Contexts.interceptCall để chuyển Context sang interceptor/handler tiếp theo.
5. Viết authorization interceptor đọc cùng key và trả UNAUTHENTICATED hoặc PERMISSION_DENIED đúng trường hợp.
6. Đọc principal trong gRPC adapter rồi truyền actor tường minh vào application use case.
7. Chạy tác vụ executor bằng Context.current().wrap hoặc Context.currentContextExecutor và xác minh principal/deadline được giữ.
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

