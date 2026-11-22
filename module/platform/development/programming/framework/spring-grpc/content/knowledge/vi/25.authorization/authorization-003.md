# Authorization interceptor

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của **Authorization interceptor** trong pipeline xử lý RPC phía server.
- Phân biệt authentication interceptor với authorization interceptor và xác định dữ liệu mà mỗi bước chịu trách nhiệm.
- Lấy principal đã xác minh từ **io.grpc.Context**, xác định RPC bằng full method name và đánh giá policy.
- Từ chối call đúng cách bằng **PERMISSION_DENIED** hoặc **UNAUTHENTICATED** mà không gọi service implementation.
- Đăng ký interceptor đúng thứ tự trong grpc-java và ứng dụng Spring gRPC.
- Thiết kế policy deny-by-default, xử lý lỗi policy, audit quyết định và tránh rò rỉ thông tin.
- Phân biệt quyền gọi method với quyền trên resource, tenant và từng message của streaming RPC.
- Kiểm thử interceptor để chứng minh cả status trả về lẫn việc handler không được thực thi.

## 1. Authorization interceptor đứng ở đâu?

Trong **SPRING_GRPC**, generated stub cho phép client gọi các RPC method được định nghĩa trong Protocol Buffers. Server nhận request và định tuyến tới service implementation. Trước khi lời gọi tới handler, **ServerInterceptor** có thể kiểm tra các điều kiện dùng chung.

Authentication interceptor trả lời caller là ai bằng cách xác minh token, certificate hoặc credential khác. Sau khi xác minh, nó tạo principal đáng tin cậy và đặt principal vào gRPC Context. Authorization interceptor đọc principal đó, xác định method đang được gọi và quyết định có cho phép call đi tiếp hay không.

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant A as Authentication interceptor
    participant Z as Authorization interceptor
    participant S as Service implementation
    C->>A: RPC + credential
    A->>A: Verify credential
    A->>Z: Principal trong Context
    Z->>Z: Kiểm tra policy theo method
    alt Được phép
        Z->>S: next.startCall
        S-->>C: Response / status
    else Chưa xác thực
        A-->>C: UNAUTHENTICATED
    else Không đủ quyền
        Z-->>C: PERMISSION_DENIED
    end
~~~

Authorization interceptor là một **điểm enforce ở ranh giới RPC**. Nó có thể bảo vệ toàn bộ method khỏi caller không có quyền, nhưng không thay thế kiểm tra nghiệp vụ trên từng order, account hoặc tenant. Một principal có quyền gọi GetOrder vẫn có thể không được đọc một order cụ thể.

## 2. Vòng đời của ServerInterceptor

grpc-java định nghĩa ServerInterceptor qua phương thức:

~~~java
<ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
        ServerCall<ReqT, RespT> call,
        Metadata headers,
        ServerCallHandler<ReqT, RespT> next);
~~~

Mỗi RPC tới service được đăng ký với interceptor sẽ đi qua interceptCall. Ba tham số quan trọng:

- **ServerCall** cung cấp method descriptor, attributes, response headers, trailers, status và thao tác đóng call.
- **Metadata headers** chứa metadata request đã được gRPC runtime giải mã.
- **ServerCallHandler next** là bước tiếp theo trong pipeline; thông thường nó gọi service implementation và trả về listener nhận request message.

Authorization interceptor có hai kết quả:

1. **Allow:** gọi next.startCall(call, headers) và trả listener mà bước tiếp theo cung cấp.
2. **Deny:** đóng call bằng status phù hợp, trả listener rỗng và tuyệt đối không gọi next.startCall.

Ví dụ khung:

~~~java
@Override
public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
        ServerCall<ReqT, RespT> call,
        Metadata headers,
        ServerCallHandler<ReqT, RespT> next) {

    AuthorizationDecision decision = authorize(call);

    if (!decision.allowed()) {
        call.close(
                Status.PERMISSION_DENIED.withDescription("Permission denied"),
                new Metadata());
        return new ServerCall.Listener<ReqT>() {};
    }

    return next.startCall(call, headers);
}
~~~

Không gọi next rồi mới kiểm tra quyền. Khi next.startCall đã chạy, service implementation có thể bắt đầu xử lý request; trả PERMISSION_DENIED sau đó không thể đảo ngược side effect đã xảy ra.

Interceptor cũng không nên tự gọi onMessage hoặc tự tạo response nghiệp vụ khi deny. Nó kết thúc RPC tại ranh giới server bằng status/trailers; caller nhận kết quả theo giao thức gRPC.

## 3. Principal phải đến từ authentication đã xác minh

Authorization không được tự suy ra danh tính từ header tùy ý. Client có thể gửi metadata như x-user, x-role hoặc x-permissions, nhưng các giá trị đó không phải bằng chứng quyền.

Một principal bất biến có thể chứa subject và tập permission đã được xác minh:

~~~java
package dev.example.security;

import java.util.Objects;
import java.util.Set;

public record GrpcPrincipal(
        String subject,
        Set<String> permissions) {

    public GrpcPrincipal {
        Objects.requireNonNull(subject, "subject");
        if (subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        permissions = Set.copyOf(permissions);
    }

    public boolean hasPermission(String permission) {
        return permissions.contains(permission);
    }
}
~~~

Dùng một Context key chung giữa authentication và authorization:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

Sau khi xác minh credential, authentication interceptor đặt principal vào Context:

~~~java
Context context = Context.current().withValue(
        GrpcSecurityContext.PRINCIPAL,
        verifiedPrincipal);

return Contexts.interceptCall(context, call, headers, next);
~~~

Authorization interceptor đọc cùng key bằng:

~~~java
GrpcPrincipal principal = GrpcSecurityContext.PRINCIPAL.get();
~~~

Điều quan trọng là cả hai interceptor dùng **chính cùng một Context.Key instance**. Tạo hai key riêng dù cùng tên chuỗi vẫn tạo hai khóa khác nhau; authorization sẽ không đọc được principal mà authentication đã đặt.

Context gắn dữ liệu với quá trình xử lý RPC và được grpc-java truyền qua callback theo cơ chế của runtime. Nếu service chuyển công việc sang executor tùy chỉnh, cần truyền Context sang tác vụ bằng API như Context.wrap hoặc cơ chế tương đương. Không giả định ThreadLocal tự viết tự động lan truyền sang thread khác.

## 4. Xác định method và đánh giá policy

Method đang được gọi có thể lấy trực tiếp từ descriptor:

~~~java
String fullMethodName =
        call.getMethodDescriptor().getFullMethodName();
~~~

Tên đầy đủ có dạng:

~~~text
demo.orders.v1.OrderService/GetOrder
demo.orders.v1.OrderService/CancelOrder
demo.accounts.v1.AccountService/DisableAccount
~~~

Không tự phân tích URL, hostname hoặc metadata để xác định method. Dùng MethodDescriptor giúp policy gắn với contract thực tế của gRPC.

Một policy đơn giản ánh xạ method sang permission bắt buộc:

~~~java
package dev.example.security;

import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class GrpcAuthorizationPolicy {

    private final Map<String, Set<String>> requiredPermissions = Map.of(
            "demo.orders.v1.OrderService/GetOrder",
            Set.of("orders:read"),
            "demo.orders.v1.OrderService/WatchOrder",
            Set.of("orders:read", "orders:watch"),
            "demo.orders.v1.OrderService/CancelOrder",
            Set.of("orders:cancel"),
            "demo.accounts.v1.AccountService/DisableAccount",
            Set.of("accounts:disable"));

    public boolean allows(
            GrpcPrincipal principal,
            String fullMethodName) {

        Set<String> required =
                requiredPermissions.get(fullMethodName);

        // Method chưa có policy luôn bị từ chối.
        return required != null
                && principal.permissions().containsAll(required);
    }
}
~~~

Policy này dùng deny-by-default: method chưa khai báo không được phép. Không dùng quy tắc kiểu "nếu không tìm thấy policy thì allow", vì method mới thêm vào proto có thể vô tình mở ra cho mọi caller.

Với hệ thống lớn, policy có thể đến từ cấu hình có version, database hoặc policy engine. Dù dùng nguồn nào, cần quy định rõ cache, invalidation, audit và hành vi khi không truy cập được policy store. Nếu không thể đánh giá quyền một cách đáng tin cậy, fail-closed thường an toàn hơn tự động cho phép.

## 5. Cài đặt Authorization interceptor

Ví dụ sau dùng principal trong Context và policy theo full method name:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import org.springframework.stereotype.Component;

@Component
public final class AuthorizationServerInterceptor
        implements ServerInterceptor {

    private final GrpcAuthorizationPolicy policy;
    private final AuthorizationAudit audit;

    public AuthorizationServerInterceptor(
            GrpcAuthorizationPolicy policy,
            AuthorizationAudit audit) {
        this.policy = policy;
        this.audit = audit;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        String method =
                call.getMethodDescriptor().getFullMethodName();

        GrpcPrincipal principal =
                GrpcSecurityContext.PRINCIPAL.get();

        if (principal == null) {
            audit.record(null, method, false, "missing_principal");
            call.close(
                    Status.UNAUTHENTICATED
                            .withDescription("Authentication required"),
                    new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        boolean allowed = policy.allows(principal, method);

        audit.record(
                principal.subject(),
                method,
                allowed,
                allowed ? "allowed" : "permission_denied");

        if (!allowed) {
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

Ví dụ giả định authentication interceptor đã chạy trước và đặt principal. Nếu principal vắng mặt, interceptor trả **UNAUTHENTICATED**; trường hợp này thường biểu thị authentication interceptor chưa được áp dụng, credential không hợp lệ hoặc Context không được truyền đúng.

Nếu principal đã xác minh nhưng thiếu permission, trả **PERMISSION_DENIED**. Không đưa tên permission nội bộ, policy rule, token hoặc chi tiết credential vào response description. Caller chỉ cần status ổn định; server có thể ghi lý do cụ thể trong audit log có kiểm soát.

**AuthorizationAudit** nên là abstraction ghi sự kiện allow/deny. Implementation thực tế cần thread-safe, không block callback bằng I/O chậm và không ghi token hay toàn bộ metadata. Nếu audit bắt buộc phải bền vững trước khi cho phép thao tác nhạy cảm, hãy thiết kế rõ yêu cầu durability và latency thay vì mặc định ghi log đồng bộ.

## 6. Authentication phải chạy trước authorization

Authorization cần principal do authentication tạo ra, vì vậy thứ tự interceptor là một phần của correctness và security.

~~~text
Incoming RPC
    |
    v
Authentication interceptor
    |  verify credential
    |  set GrpcSecurityContext.PRINCIPAL
    v
Authorization interceptor
    |  read principal
    |  check method policy
    +---- deny --> close(PERMISSION_DENIED)
    |
    v
Service implementation
~~~

Với grpc-java, có thể đăng ký các interceptor quanh service bằng ServerInterceptors. Ví dụ:

~~~java
ServerServiceDefinition securedService =
        ServerInterceptors.interceptForward(
                orderEndpoint,
                authenticationInterceptor,
                authorizationInterceptor);

serverBuilder.addService(securedService);
~~~

Đoạn code thể hiện thứ tự mong muốn: authentication tạo Context trước, authorization đọc Context sau. Thứ tự thực thi cụ thể cần được xác minh theo API registration đang dùng và phiên bản grpc-java/starter; hãy viết integration test để chứng minh principal đã có mặt tại authorization interceptor.

Trong Spring gRPC starter, đăng ký interceptor qua extension point hoặc bean registration mà phiên bản starter hỗ trợ. Không tạo server thủ công trên cùng port nếu starter đã sở hữu server. Cũng cần tránh đăng ký cùng interceptor hai lần, vì audit và metrics có thể bị ghi trùng.

## 7. Chọn status và đóng call đúng cách

Authorization interceptor thường cần phân biệt hai trường hợp:

| Tình huống | Status | Ý nghĩa |
| --- | --- | --- |
| Không có principal hoặc credential chưa xác minh | **UNAUTHENTICATED** | Server chưa xác định được danh tính caller |
| Principal đã xác minh nhưng không đủ quyền | **PERMISSION_DENIED** | Caller có danh tính nhưng policy từ chối hành động |
| Policy không có rule cho method | **PERMISSION_DENIED** | Deny-by-default |
| Policy store không sẵn sàng | Thường fail-closed; status tùy lỗi hạ tầng và contract | Không được mặc định allow |
| Request sai định dạng | **INVALID_ARGUMENT** | Lỗi dữ liệu request, không phải lỗi quyền |

Khi từ chối, gọi ServerCall.close với status và trailers rồi trả listener rỗng. Không gọi next.startCall. Không gọi close nhiều lần; tránh phát status terminal thứ hai khi call đã kết thúc.

Nếu policy service gặp lỗi hạ tầng, có thể chọn **UNAVAILABLE** hoặc **INTERNAL** tùy contract vận hành, nhưng tuyệt đối không chuyển lỗi policy thành allow. Phân biệt lỗi policy từ chối với lỗi không thể đánh giá policy giúp client và hệ thống giám sát xử lý đúng.

## 8. Quyền method khác quyền trên resource

Authorization interceptor phù hợp cho quyền ở mức service/method, ví dụ principal có được gọi GetOrder hay CancelOrder. Nó không tự biết caller có quyền truy cập một order cụ thể hay không.

Ví dụ principal có permission orders:read, nhưng request chứa orderId thuộc tenant khác. Service/domain layer cần kiểm tra:

- order có tồn tại và thuộc tenant đã xác minh của principal không;
- caller có quan hệ ownership hoặc được phân công xử lý không;
- trạng thái nghiệp vụ có cho phép thao tác không;
- response có cần che giấu sự tồn tại của resource để tránh dò ID không.

Không tin tenantId hoặc ownerId do client tự gửi là bằng chứng quyền. Đối chiếu request với principal hoặc dữ liệu policy đáng tin cậy. Có thể dùng authorization interceptor cho policy tổng quát, sau đó service thực hiện resource authorization với dữ liệu thực tế.

## 9. Authorization cho streaming RPC

Interceptor đánh giá quyền method khi RPC được mở. Với client-streaming hoặc bidirectional streaming, nhiều message có thể đến sau đó và mỗi message có thể tham chiếu resource khác nhau.

Ví dụ:

- WatchOrder yêu cầu permission orders:read và orders:watch khi mở stream.
- Nếu WatchOrder theo dõi nhiều orderId, mỗi order vẫn phải qua kiểm tra tenant/ownership.
- UploadEvents cần permission events:write, nhưng từng event vẫn phải được kiểm tra schema, tenant và trạng thái.
- Khi quyền bị thu hồi trong lúc stream dài đang chạy, cần chính sách rõ ràng về revalidation hoặc cancellation.

Không giả định một lần kiểm tra method ở thời điểm mở stream cho phép mọi message về sau. Nếu yêu cầu thu hồi quyền nhanh, cân nhắc giới hạn thời lượng stream, revalidate theo chu kỳ hoặc hủy subscription khi identity/policy thay đổi. Khi từ chối giữa stream, service phải kết thúc stream bằng status phù hợp và cleanup tài nguyên.

## 10. Các lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mọi call đều UNAUTHENTICATED | Authentication chưa đăng ký hoặc Context key khác nhau | Dùng chung Context key và kiểm tra thứ tự |
| User hợp lệ vẫn PERMISSION_DENIED | Policy dùng sai full method name hoặc thiếu mapping | Log method name, kiểm tra catalog và test |
| Method mới tự động được gọi | Policy mặc định allow | Deny-by-default và yêu cầu mapping cho method mới |
| Handler vẫn chạy dù audit ghi deny | Interceptor gọi next trước khi kiểm tra hoặc vẫn gọi next sau deny | Đóng call và trả listener rỗng |
| Audit ghi hai lần | Interceptor đăng ký trùng hoặc audit ở nhiều lớp | Kiểm tra registration và định nghĩa event |
| Quyền bị trộn giữa hai RPC | Principal lưu trong field mutable dùng chung | Đặt principal trong Context theo từng call |
| Streaming truy cập tenant khác | Chỉ kiểm tra method khi mở stream | Kiểm tra resource theo từng message |
| Policy store lỗi nhưng call vẫn được phép | Fallback allow khi lỗi | Fail-closed và quan sát lỗi policy |
| Client nhìn thấy chi tiết quyền nội bộ | Status description chứa policy/claim | Response chung; chi tiết ở audit log |

Khi debug, kiểm tra lần lượt: credential có được xác minh không; authentication interceptor có đặt đúng Context key không; authorization có đọc được principal không; full method name có khớp policy không; decision có được enforce trước next.startCall không; status có được gửi về client đúng không.

## 11. Kiểm thử Authorization interceptor

Test cần xác minh cả kết quả RPC và side effect ở server. Chỉ assert PERMISSION_DENIED là chưa đủ nếu handler vẫn chạy trước khi call bị đóng.

| Tình huống | Status mong đợi | Handler |
| --- | --- | --- |
| Không có principal | UNAUTHENTICATED | Không chạy |
| Principal thiếu permission | PERMISSION_DENIED | Không chạy |
| Method chưa có policy | PERMISSION_DENIED | Không chạy |
| Principal đủ quyền | OK hoặc status nghiệp vụ | Được chạy |
| Policy store lỗi | Fail-closed theo contract | Không chạy |
| Có quyền method nhưng resource sai tenant | Status domain/security phù hợp | Có thể vào handler, nhưng thao tác resource bị chặn |

Nên dùng in-process gRPC test để gọi qua generated stub, đăng ký authentication và authorization interceptor như production rồi kiểm tra:

1. Authentication tạo principal bằng shared Context key.
2. Authorization đọc đúng principal trong cùng RPC.
3. Method không có policy bị từ chối.
4. Khi deny, mock/flag xác nhận service implementation không được gọi.
5. Khi allow, handler chạy và trả response bình thường.
6. Hai RPC đồng thời với principal khác nhau không chia sẻ nhầm context.
7. Streaming bị từ chối đúng lúc mở hoặc tại resource check trong message processing.

In-process test không kiểm tra TLS, proxy hoặc credential validation qua network. Nếu identity đến từ JWT/mTLS hoặc gateway, cần bổ sung integration test qua transport thật để kiểm tra toàn bộ chuỗi xác thực và phân quyền.

## 12. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Tạo một GrpcPrincipal bất biến chứa subject và permission đã được xác minh.
2. Tạo GrpcSecurityContext với một Context key dùng chung cho authentication và authorization.
3. Tạo authentication interceptor giả trong test, đặt principal vào Context bằng Contexts.interceptCall.
4. Viết GrpcAuthorizationPolicy ánh xạ full method name sang permission bắt buộc; method chưa có rule phải deny.
5. Viết AuthorizationServerInterceptor trả UNAUTHENTICATED khi thiếu principal và PERMISSION_DENIED khi thiếu quyền.
6. Đăng ký authentication trước authorization bằng API server phù hợp và xác minh thứ tự trong integration test.
7. Đặt mock/flag trong service implementation để chứng minh handler không chạy khi bị deny.
8. Bổ sung resource/tenant check ở service và test streaming có nhiều resource ID.

### Câu hỏi tự kiểm tra

**1. Authorization interceptor có nhiệm vụ gì?**  
Đọc principal đã xác minh, xác định full method name, đánh giá policy và chặn RPC trước khi service implementation chạy nếu caller không đủ quyền.

**2. Vì sao authentication phải chạy trước authorization?**  
Authorization cần principal đáng tin cậy. Nếu authentication chưa xác minh credential hoặc chưa đặt Context, interceptor không có cơ sở quyết định quyền.

**3. Vì sao hai interceptor phải dùng cùng Context.Key instance?**  
Context key là đối tượng định danh. Tạo hai key khác nhau dù cùng tên không làm chúng tham chiếu cùng một giá trị.

**4. Khi nào trả UNAUTHENTICATED và khi nào trả PERMISSION_DENIED?**  
UNAUTHENTICATED khi chưa xác minh được caller; PERMISSION_DENIED khi principal đã xác minh nhưng policy không cho phép.

**5. Vì sao method chưa có policy phải bị từ chối?**  
Deny-by-default ngăn method mới được thêm vào proto vô tình trở thành API công khai.

**6. Có thể dùng interceptor để kiểm tra ownership của từng order không?**  
Interceptor có thể kiểm tra quyền chung của method; ownership cần dữ liệu resource nên thường được kiểm tra trong service/domain layer.

**7. Một lần authorize khi mở stream có đủ không?**  
Chỉ đủ cho quyền gọi method. Nếu message tham chiếu nhiều resource hoặc quyền có thể bị thu hồi, cần kiểm tra theo message/chu kỳ hoặc hủy stream.

**8. Test nào chứng minh interceptor thực sự bảo vệ service?**  
Test gọi qua gRPC runtime, assert status và đồng thời xác nhận handler không được gọi khi decision là deny.

## Tổng kết

**Authorization interceptor** là lớp enforce policy ở ranh giới server gRPC. Authentication xác minh credential và đặt principal vào một **io.grpc.Context** dùng chung; authorization đọc principal, lấy full method name và kiểm tra permission theo nguyên tắc deny-by-default. Khi thiếu principal, trả **UNAUTHENTICATED**; khi principal không đủ quyền, trả **PERMISSION_DENIED** và không gọi next.startCall. Đăng ký đúng thứ tự trong Spring gRPC, giữ policy fail-closed, audit an toàn và kiểm thử cả status lẫn việc handler có chạy hay không. Quyền method vẫn cần kết hợp resource/tenant authorization ở service/domain layer, nhất là với streaming RPC.

