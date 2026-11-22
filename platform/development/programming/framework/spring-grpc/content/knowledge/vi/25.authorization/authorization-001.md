# Quyền gọi theo service và method

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt xác thực danh tính (**authentication**) với quyết định quyền gọi (**authorization**) trong gRPC.
- Xác định một RPC bằng tên đầy đủ **package.Service/Method** và dùng nó làm khóa policy.
- Thiết kế quyền ở hai phạm vi: service và method, theo nguyên tắc mặc định từ chối.
- Thực thi policy phía server bằng **ServerInterceptor**, principal và **io.grpc.Context**.
- Phân biệt **UNAUTHENTICATED** với **PERMISSION_DENIED**, đồng thời không tin metadata do client tự khai là quyền.
- Xử lý quyền cho streaming, tài nguyên/tenant và các method đặc biệt như health/reflection.
- Kiểm thử quyền cho phép, từ chối và trường hợp chưa xác thực trong Spring gRPC.

## 1. Authorization nằm ở đâu trong một gRPC call?

Trong **SPRING_GRPC**, Protocol Buffers định nghĩa service và các method mà client có thể gọi. Generated stub giúp client gọi các method đó, nhưng việc một method được khai báo và được client nhìn thấy **không có nghĩa mọi caller đều được phép sử dụng**.

**Authorization** là quyết định một principal đã được xác thực có được gọi một service/method hay không. Ví dụ:

- Service **OrderService** chỉ dành cho workload có quyền truy cập miền đơn hàng.
- Method **GetOrder** yêu cầu quyền đọc đơn hàng.
- Method **CancelOrder** yêu cầu quyền hủy đơn.
- Method quản trị có thể yêu cầu quyền riêng, dù nó nằm trong cùng service.

Luồng điển hình:

~~~mermaid
sequenceDiagram
    participant C as gRPC client
    participant A as Authentication interceptor
    participant Z as Authorization interceptor
    participant S as Service implementation
    C->>A: RPC + credentials
    A->>A: Xác minh token / certificate
    A->>Z: Principal đã xác minh trong Context
    Z->>Z: Kiểm tra service và method policy
    alt Được phép
        Z->>S: Chuyển tiếp RPC
        S-->>C: Response + status
    else Không đủ quyền
        Z-->>C: PERMISSION_DENIED
    else Chưa xác thực
        A-->>C: UNAUTHENTICATED
    end
~~~

Authorization thường được kiểm tra ở server vì client do người gọi kiểm soát. Client có thể ẩn nút hoặc không hiển thị method trong UI, nhưng biện pháp đó chỉ cải thiện trải nghiệm; nó không bảo vệ API.

## 2. Xác thực khác với phân quyền

Hai bước này có mục tiêu khác nhau:

| Bước | Câu hỏi | Ví dụ kết quả |
| --- | --- | --- |
| **Authentication** | Caller là ai? | Principal **service:billing-worker** đã được xác minh |
| **Authorization** | Principal đó được gọi method này không? | Có **orders:read**, được gọi **OrderService/GetOrder** |

Authentication có thể xác minh JWT, OAuth2 access token, mTLS certificate hoặc credential khác. Sau khi xác minh chữ ký/issuer/audience/expiry và các claim cần thiết, lớp xác thực tạo một principal đáng tin cậy.

Authorization sử dụng principal đó cùng policy để quyết định. Không được lấy **user-role**, **permissions** hay **tenant** từ metadata tùy ý rồi coi đó là bằng chứng quyền. Metadata là dữ liệu caller gửi; nó chỉ đáng tin nếu được xác minh hoặc được một thành phần tin cậy thiết lập qua kênh được bảo vệ.

gRPC thường dùng các status sau:

- **UNAUTHENTICATED**: thiếu credential, credential sai/hết hạn hoặc không thể xác minh danh tính.
- **PERMISSION_DENIED**: danh tính đã xác minh, nhưng policy không cho phép gọi service/method hoặc thao tác.
- **INVALID_ARGUMENT**: request không hợp lệ; không dùng mã này để biểu thị thiếu quyền.
- **NOT_FOUND**: tài nguyên không tồn tại hoặc được cố ý che giấu theo policy bảo mật; cần lựa chọn nhất quán để tránh rò rỉ thông tin.

Không đưa token, certificate detail, policy nội bộ hay lý do nhạy cảm vào status description. Client chỉ cần mã status ổn định để xử lý; server ghi chi tiết chẩn đoán trong log bảo mật.

## 3. Định danh service và method trong gRPC

Tên method đầy đủ là khóa tự nhiên để áp dụng policy:

~~~text
demo.orders.v1.OrderService/GetOrder
demo.orders.v1.OrderService/WatchOrder
demo.orders.v1.OrderService/CancelOrder
demo.admin.v1.AdminService/DisableAccount
~~~

Trong grpc-java, có thể lấy tên này từ:

~~~java
String fullMethodName =
        call.getMethodDescriptor().getFullMethodName();
~~~

Giá trị **fullMethodName** có dạng **package.Service/Method**, không có dấu gạch chéo ở đầu. HTTP/2 **:path** thường có dạng **/package.Service/Method**. Hãy dùng API descriptor để lấy tên method, tránh tự phân tích URL, authority hoặc chuỗi path từ metadata.

Policy nên dùng tên đầy đủ và ổn định. Khi đổi package, service hoặc method trong proto, tên RPC có thể thay đổi; cần cập nhật policy và test cùng lúc với thay đổi contract.

## 4. Kết hợp quyền service-level và method-level

Quyền ở cấp service giới hạn miền API mà principal được tiếp cận. Quyền ở cấp method giới hạn hành động cụ thể bên trong service.

Ví dụ policy:

| Service / method | Quyền cần có |
| --- | --- |
| **OrderService** | **orders:access** |
| **OrderService/GetOrder** | **orders:read** |
| **OrderService/WatchOrder** | **orders:read** |
| **OrderService/CancelOrder** | **orders:cancel** |
| **AdminService** | **admin:access** |
| **AdminService/DisableAccount** | **accounts:disable** |

Để gọi **OrderService/GetOrder**, principal cần cả **orders:access** và **orders:read**. Cách kết hợp này tạo một lớp policy tổng quát cho service và một lớp quyền chi tiết cho method.

Một số hệ thống có thể chọn policy method kế thừa quyền service nếu method không có rule riêng. Dù chọn cách nào, phải quy định rõ semantics kế thừa và **mặc định từ chối method chưa khai báo**. Không nên vô tình cho phép method mới chỉ vì nó được thêm vào proto.

### 4.1. Mô hình principal bất biến

Sau khi xác thực, lưu subject và tập quyền đã được xác minh trong một đối tượng bất biến:

~~~java
package dev.example.security;

import java.util.Objects;
import java.util.Set;

public record GrpcPrincipal(
        String subject,
        Set<String> permissions) {

    public GrpcPrincipal {
        Objects.requireNonNull(subject, "subject");
        permissions = Set.copyOf(permissions);
    }

    public boolean hasPermission(String permission) {
        return permissions.contains(permission);
    }
}
~~~

Tập quyền phải đến từ nguồn tin cậy như claim đã xác minh, policy engine hoặc service identity registry. Không xây dựng principal bằng cách sao chép một header **x-permissions** do client tự gửi.

### 4.2. Policy theo tên đầy đủ

Một policy đơn giản có thể yêu cầu cả quyền service và method:

~~~java
package dev.example.security;

import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class GrpcMethodPolicy {

    private final Map<String, String> servicePermissions = Map.of(
            "demo.orders.v1.OrderService", "orders:access",
            "demo.admin.v1.AdminService", "admin:access");

    private final Map<String, String> methodPermissions = Map.of(
            "demo.orders.v1.OrderService/GetOrder", "orders:read",
            "demo.orders.v1.OrderService/WatchOrder", "orders:read",
            "demo.orders.v1.OrderService/CancelOrder", "orders:cancel",
            "demo.admin.v1.AdminService/DisableAccount",
                    "accounts:disable");

    public boolean allows(
            GrpcPrincipal principal,
            String fullMethodName) {

        int separator = fullMethodName.indexOf('/');
        if (separator <= 0 || separator == fullMethodName.length() - 1) {
            return false;
        }

        String serviceName = fullMethodName.substring(0, separator);
        String servicePermission = servicePermissions.get(serviceName);
        String methodPermission = methodPermissions.get(fullMethodName);

        // Không có rule service hoặc method nghĩa là deny.
        return servicePermission != null
                && methodPermission != null
                && principal.hasPermission(servicePermission)
                && principal.hasPermission(methodPermission);
    }
}
~~~

Ví dụ dùng map tĩnh để làm rõ cơ chế. Production có thể tải policy từ cấu hình được kiểm soát hoặc policy engine, nhưng cần xác định cách cập nhật, cache, audit và xử lý lỗi khi nguồn policy không sẵn sàng. Nếu không thể xác định policy, không được mặc định cho phép.

## 5. Đưa principal vào Context sau authentication

**io.grpc.Context** mang dữ liệu gắn với một RPC qua các callback của grpc-java. Authentication interceptor xác minh credential rồi gắn principal vào Context. Authorization interceptor đọc principal đó.

Khai báo context key dùng chung:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

Authentication interceptor có thể có dạng:

~~~java
package dev.example.security;

import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Optional;

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

        Optional<GrpcPrincipal> authenticated =
                authenticator.authenticate(headers);

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

**CredentialAuthenticator** là abstraction của ứng dụng để xác minh token/certificate; nó không được coi metadata là principal trước khi kiểm tra credential. Ví dụ không triển khai thuật toán xác minh token vì lựa chọn thư viện, issuer và trust configuration phụ thuộc hệ thống.

Nếu handler chuyển công việc sang executor riêng, cần truyền Context sang thread đó bằng API như **Context.wrap(...)**. Không dựa vào ThreadLocal tự viết hoặc giả định mọi tác vụ bất đồng bộ tự kế thừa principal.

## 6. Enforce quyền ở ServerInterceptor

Authorization interceptor kiểm tra principal và method trước khi chuyển tiếp tới service implementation:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

public final class MethodAuthorizationInterceptor
        implements ServerInterceptor {

    private final GrpcMethodPolicy policy;

    public MethodAuthorizationInterceptor(GrpcMethodPolicy policy) {
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

Nếu bị từ chối, interceptor đóng call và trả listener rỗng; service implementation không được gọi. Không chỉ ghi log rồi vẫn gọi **next.startCall(...)**, vì như vậy authorization không thực sự được enforce.

Authentication phải chạy trước authorization để Context đã có principal. Khi đăng ký nhiều interceptor, xác minh thứ tự lồng/bọc của API server hoặc starter đang dùng và viết integration test để bảo đảm principal có mặt tại authorization interceptor.

### 6.1. Đăng ký trong ứng dụng Spring

Trong cấu hình grpc-java trực tiếp, interceptor được gắn vào service definition trước khi đăng ký với server. Ví dụ wiring theo ý tưởng:

~~~java
@Bean
ServerServiceDefinition securedOrderService(
        OrderEndpoint endpoint,
        AuthenticationServerInterceptor authentication,
        MethodAuthorizationInterceptor authorization) {

    return ServerInterceptors.interceptForward(
            endpoint,
            authentication,
            authorization);
}
~~~

Đoạn wiring minh họa thứ tự mong muốn: authentication tạo principal trong Context trước, authorization đọc principal sau đó. Khi dùng Spring gRPC starter, đăng ký các interceptor qua extension point/bean registration của đúng phiên bản starter; không tạo thêm server thủ công nếu starter đã quản lý server. Kiểm tra thứ tự bằng test thay vì phụ thuộc vào giả định về thứ tự cấu hình.

## 7. Quyền service/method không thay thế quyền trên tài nguyên

Quyền gọi method chỉ trả lời caller có được phép gọi một loại thao tác hay không. Nó chưa chắc cho biết caller được thao tác trên **mọi tài nguyên** mà request chỉ định.

Ví dụ, **orders:read** cho phép gọi **GetOrder**, nhưng service vẫn phải xác minh caller có quyền đọc **order_id** cụ thể trong tenant tương ứng. Tương tự, quyền gọi **CancelOrder** không tự động cho phép hủy mọi đơn hàng.

Cần kiểm tra ở tầng service/domain khi quyền phụ thuộc vào:

- **Resource ownership:** người dùng chỉ xem hoặc sửa tài nguyên của mình.
- **Tenant boundary:** workload chỉ truy cập dữ liệu thuộc tenant được cấp.
- **Relationship/attribute:** quyền phụ thuộc trạng thái đơn, vai trò trong tổ chức hoặc thuộc tính tài nguyên.
- **Business state:** chỉ được hủy đơn khi đơn chưa giao hoặc chưa quyết toán.

Không dùng **tenant_id** do request gửi lên làm bằng chứng tenant. Đối chiếu nó với tenant/relationship đã xác minh trong principal hoặc policy store. Việc này ngăn một caller hợp lệ thay ID để truy cập dữ liệu của tenant khác.

## 8. Authorization với streaming RPC

Với unary RPC, interceptor có thể quyết định quyền trước khi handler xử lý request. Với client-streaming và bidirectional streaming, interceptor vẫn chỉ thấy method ở thời điểm mở call; message tiếp theo có thể mang nhiều resource ID khác nhau.

Vì vậy:

- Kiểm tra quyền gọi service/method ngay khi mở stream.
- Kiểm tra từng message hoặc từng resource ở tầng nghiệp vụ nếu stream có thể thao tác trên nhiều tài nguyên.
- Dừng stream bằng status phù hợp khi phát hiện message không được phép.
- Cleanup subscription, buffer và công việc nền khi call bị hủy hoặc bị từ chối.
- Không giả định một lần authorize lúc mở stream cho phép caller truy cập mọi resource được gửi về sau.

Ví dụ **WatchOrder** có thể được phép ở mức method, nhưng mỗi **order_id** cần được kiểm tra tenant/ownership trước khi đăng ký subscription.

## 9. Các method đặc biệt: health, reflection và internal APIs

Một số method không thuộc business service nhưng vẫn có thể được gọi từ mạng:

- **gRPC health** thường cần cho load balancer/orchestrator kiểm tra service.
- **Reflection** giúp công cụ khám phá service descriptor, nhưng có thể làm lộ bề mặt API.
- **Admin/internal methods** có thể thay đổi trạng thái hệ thống hoặc đọc thông tin nhạy cảm.

Không tạo ngoại lệ kiểu "mọi method không có policy đều được phép". Hãy khai báo rõ method nào public, method nào chỉ dành cho workload nội bộ và method nào cần quyền quản trị. Nếu health endpoint cần truy cập không xác thực trong network nội bộ, giới hạn nó bằng listener/network policy hoặc một policy riêng; không mở toàn bộ business service theo cùng ngoại lệ.

Reflection không phải cơ chế authorization. Ẩn service khỏi reflection không ngăn một client biết tên method gọi trực tiếp.

## 10. Audit, cache policy và nguyên tắc an toàn

Authorization là quyết định bảo mật nên cần quan sát nhưng không làm lộ dữ liệu:

- Ghi nhận **principal ID**, full method name, quyết định allow/deny và correlation ID theo chính sách log.
- Không ghi token, private key, toàn bộ metadata hoặc payload nhạy cảm.
- Dùng status ổn định; tránh mô tả chi tiết policy nội bộ trong response.
- Dùng deny-by-default cho method mới hoặc policy không đọc được.
- Nếu cache quyền, xác định TTL, invalidation và thời gian thu hồi quyền.
- Giữ policy thay đổi có audit trail, review và rollback.
- Metrics nên dùng method/status/decision có cardinality kiểm soát; không dùng user ID làm label.

Cache lâu có thể khiến quyền đã thu hồi vẫn được dùng. Với quyền nhạy cảm, cần cache ngắn hoặc kiểm tra policy trực tuyến theo yêu cầu độ trễ và khả năng chịu lỗi. Nếu policy service lỗi, quyết định fail-closed thường an toàn hơn tự động cho phép.

## 11. Kiểm thử authorization

Nên kiểm tra quyết định qua gRPC runtime để xác nhận interceptor thực sự chặn call trước handler.

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Không có principal | **UNAUTHENTICATED** |
| Principal thiếu quyền service | **PERMISSION_DENIED** |
| Có quyền service nhưng thiếu quyền method | **PERMISSION_DENIED** |
| Có đủ hai quyền | Handler được gọi, RPC có thể thành công |
| Method mới chưa có policy | **PERMISSION_DENIED** |
| Metadata giả **x-role: admin** nhưng principal không có quyền | **PERMISSION_DENIED** |
| Có quyền method nhưng không sở hữu resource | Domain/service từ chối thao tác tài nguyên |
| Streaming message chứa resource ngoài tenant | Stream bị từ chối/dừng theo policy |
| Health/reflection method | Chỉ truy cập theo rule riêng đã công bố |

Một test in-process nên dùng principal giả được inject bởi test authenticator, sau đó gọi qua generated stub và xác minh status. Đồng thời đặt cờ hoặc mock trên service implementation để khẳng định handler **không được gọi** khi interceptor từ chối. Bổ sung test qua transport thật nếu authorization phụ thuộc mTLS, gateway hoặc identity được proxy chuyển tiếp.

## 12. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Định nghĩa **OrderService** có **GetOrder**, **WatchOrder** và **CancelOrder**.
2. Tạo **GrpcPrincipal** chỉ chứa subject và permission đã được xác minh.
3. Tạo policy yêu cầu **orders:access** ở service level; **orders:read** cho GetOrder/WatchOrder và **orders:cancel** cho CancelOrder.
4. Đặt principal vào **io.grpc.Context** trong authentication interceptor.
5. Thêm **MethodAuthorizationInterceptor** đọc **getFullMethodName()** và từ chối method không có policy.
6. Viết in-process test cho thiếu principal, thiếu service permission, thiếu method permission, đủ quyền và method chưa khai báo.
7. Thêm kiểm tra ownership/tenant ở domain service cho **order_id**, kể cả khi principal có **orders:read**.
8. Kiểm tra log/audit và xác minh không có token hoặc dữ liệu nhạy cảm trong status/metadata.

### Câu hỏi tự kiểm tra

**1. Authentication khác authorization thế nào?**  
Authentication xác minh caller là ai; authorization quyết định principal đó được gọi service/method hoặc thao tác tài nguyên nào.

**2. Vì sao authorization phải được enforce ở server?**  
Client có thể bị sửa hoặc bỏ qua UI. Chỉ server mới là ranh giới tin cậy để quyết định có thực thi RPC hay không.

**3. getFullMethodName() trả về dạng nào?**  
Dạng **package.Service/Method**, phù hợp làm khóa policy cho method gRPC.

**4. Khi nào trả UNAUTHENTICATED và khi nào trả PERMISSION_DENIED?**  
UNAUTHENTICATED khi không xác minh được danh tính; PERMISSION_DENIED khi principal đã xác minh nhưng thiếu quyền.

**5. Vì sao cần cả service-level và method-level permission?**  
Service-level giới hạn miền API; method-level giới hạn hành động cụ thể trong miền đó.

**6. Method mới chưa có policy nên được xử lý thế nào?**  
Mặc định từ chối cho tới khi policy được khai báo và kiểm thử.

**7. Có thể chỉ kiểm tra quyền một lần cho mọi streaming message không?**  
Chỉ đủ cho quyền gọi method. Nếu mỗi message nhắm tới resource/tenant khác nhau, phải kiểm tra quyền ở tầng nghiệp vụ cho từng resource.

**8. Vì sao không tin x-role: admin từ client?**  
Đó là metadata caller tự khai, không chứng minh danh tính hay quyền. Principal phải được tạo từ credential đã xác minh.

## Tổng kết

**Authorization theo service và method** kiểm soát caller nào được phép gọi từng RPC. Server xác minh danh tính trước, đưa principal đáng tin vào **io.grpc.Context**, rồi dùng **ServerInterceptor** đối chiếu full method name với policy service-level và method-level. Không có principal trả **UNAUTHENTICATED**; principal thiếu quyền hoặc method chưa có rule trả **PERMISSION_DENIED** theo nguyên tắc deny-by-default. Với quyền phụ thuộc tenant, ownership hoặc trạng thái tài nguyên, service/domain vẫn phải kiểm tra dữ liệu cụ thể, kể cả trong streaming. Kiểm thử cả quyết định allow/deny và việc handler có bị chặn thực sự giúp policy bảo vệ đúng bề mặt API Spring gRPC.

