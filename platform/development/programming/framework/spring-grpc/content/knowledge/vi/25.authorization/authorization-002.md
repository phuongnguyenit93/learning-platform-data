# Role, scope và permission

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **role**, **scope** và **permission** trong mô hình phân quyền cho gRPC.
- Hiểu role mô tả nhóm năng lực của subject, scope giới hạn quyền mà access token được cấp, còn permission biểu diễn hành động cụ thể.
- Đọc role/scope từ credential đã xác minh và chuyển chúng thành principal đáng tin cậy.
- Thiết kế policy least-privilege cho service và method trong Spring gRPC.
- Kết hợp role với scope theo quy tắc rõ ràng, mặc định từ chối khi thiếu claim hoặc policy.
- Enforce permission bằng **ServerInterceptor** và **io.grpc.Context**.
- Phân biệt quyền gọi method với quyền trên tenant/resource, kiểm thử các trường hợp allow/deny và audit quyết định.

## 1. Ba khái niệm trả lời ba câu hỏi khác nhau

Trong **SPRING_GRPC**, authentication xác minh caller là ai; authorization quyết định caller được làm gì. Role, scope và permission là ba khái niệm thường xuất hiện trong authorization, nhưng chúng không đồng nghĩa và không nên dùng thay thế cho nhau.

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Role** | Subject thuộc nhóm năng lực nào? | order-reader, order-operator, support-agent |
| **Scope** | Access token được phép truy cập phạm vi API nào? | orders.read, orders.cancel |
| **Permission** | Hành động cụ thể nào được phép? | orders:read, orders:cancel |

Có thể hình dung luồng chuyển đổi như sau:

~~~mermaid
flowchart LR
    A["Credential đã xác minh"]
    B["Roles của subject"]
    C["Scopes của access token"]
    D["Permission catalog / policy"]
    E["Effective permissions"]
    F["Service + method policy"]
    G["Allow hoặc deny"]
    A --> B
    A --> C
    B --> D
    C --> D
    D --> E
    E --> F --> G
~~~

- **Role** thường gom nhiều quyền có liên quan để quản lý subject thuận tiện.
- **Scope** thường giới hạn quyền của một access token đối với resource server/API cụ thể, đặc biệt trong OAuth 2.0.
- **Permission** là đơn vị mà policy kiểm tra khi quyết định cho phép một hành động.

Ví dụ, role **order-operator** có thể được ánh xạ tới quyền đọc và hủy đơn. Nhưng access token hiện tại chỉ có scope **orders.read**; khi đó token chỉ cho phép phần đọc. Scope giới hạn quyền có thể sử dụng trong lần gọi này, ngay cả khi role của subject rộng hơn.

## 2. Role: nhóm năng lực của subject

Role là nhãn mô tả một nhóm năng lực hoặc trách nhiệm được gán cho user, service account hay workload. Ví dụ:

- **order-reader**: đọc thông tin đơn hàng.
- **order-operator**: xử lý và hủy đơn theo quy trình.
- **support-agent**: tra cứu thông tin phục vụ hỗ trợ khách hàng.
- **system-admin**: thực hiện một số thao tác quản trị.

Role giúp quản trị dễ hơn: thay vì gán hàng chục permission trực tiếp cho từng subject, hệ thống gán một hoặc nhiều role rồi ánh xạ role sang permission.

Tuy nhiên, tên role không tự tạo ra quyền. Server phải có policy xác định role đó cấp permission nào, ở service/method nào và trong điều kiện nào. Không nên viết logic kiểu **admin = allow all** vì nó bỏ qua phạm vi API, tenant, token scope và nguyên tắc least privilege.

Role có thể được cấp từ identity provider hoặc quản lý nội bộ. Claim role có tên và cấu trúc khác nhau giữa các nhà cung cấp; có hệ thống dùng **roles**, **groups** hoặc claim lồng theo namespace. Hãy chuẩn hóa claim ở bước authentication thành một mô hình principal thống nhất, thay vì để mỗi interceptor tự đọc claim thô.

## 3. Scope: giới hạn của access token

Trong OAuth 2.0, scope là chuỗi biểu diễn phạm vi truy cập mà authorization server cấp cho client. Resource server dùng scope để kiểm tra token có quyền gọi API tương ứng hay không.

Ví dụ token có scope:

~~~text
scope = "orders.read orders.summary"
~~~

Token này có thể được phép đọc đơn và xem bản tổng hợp, nhưng không có scope **orders.cancel**. Dù subject có role **order-operator**, token hiện tại không nên được dùng để hủy đơn nếu policy yêu cầu scope tương ứng.

Một số điểm cần nhớ:

- Scope thường được cấp cho **access token**, không phải một role lâu dài của user.
- Scope phản ánh quyền mà client/resource server đã thỏa thuận trong quá trình cấp token.
- Tên claim có thể là **scope**, **scp** hoặc cấu trúc riêng của identity provider; cần đọc theo contract của issuer.
- Scope cần được giới hạn theo audience/resource server; token cấp cho API khác không tự động hợp lệ với gRPC service này.
- Thiếu scope bắt buộc phải được xử lý theo policy rõ ràng, thường là deny.

Scope không thay thế kiểm tra quyền trên từng resource. **orders.read** có thể cho phép gọi **GetOrder**, nhưng không tự cho biết caller được đọc đơn hàng thuộc tenant nào.

## 4. Permission: hành động cụ thể mà policy kiểm tra

Permission mô tả một hành động có thể kiểm soát, thường theo dạng **resource:action**:

~~~text
orders:read
orders:cancel
orders:watch
accounts:disable
reports:export
~~~

Một permission nên có ý nghĩa ổn định trong domain. Không gắn permission trực tiếp với tên role, vì role là nhóm có thể thay đổi; permission mô tả hành động mà service thực hiện.

Ví dụ mapping:

| Role | Permissions được cấp |
| --- | --- |
| **order-reader** | orders:read, orders:watch |
| **order-operator** | orders:read, orders:watch, orders:cancel |
| **support-agent** | orders:read, customers:read |

Scope được ánh xạ tới cùng vocabulary permission:

| OAuth scope | Permission tương ứng |
| --- | --- |
| **orders.read** | orders:read |
| **orders.watch** | orders:watch |
| **orders.cancel** | orders:cancel |
| **customers.read** | customers:read |

Việc ánh xạ này là policy của resource server, không phải quy tắc tự động của OAuth hay gRPC. Đặt tên rõ ràng và version hóa khi thay đổi semantics để client, authorization server và service không hiểu khác nhau.

## 5. Kết hợp role và scope một cách an toàn

Không có một phép kết hợp role/scope duy nhất phù hợp mọi hệ thống. Điều quan trọng là policy phải công bố rõ role và scope đóng vai trò gì. Với access token OAuth, một mô hình an toàn phổ biến là:

1. Role xác định các permission subject có thể được cấp theo trách nhiệm.
2. Scope xác định permission token hiện tại được phép sử dụng tại resource server.
3. Effective permission là phần giao giữa hai tập quyền.
4. Method policy yêu cầu effective permission tương ứng; thiếu role grant hoặc scope grant đều bị từ chối.

Ví dụ:

~~~text
Role: order-operator
  -> orders:read
  -> orders:watch
  -> orders:cancel

Token scopes:
  -> orders.read
  -> orders.watch

Effective permissions:
  -> orders:read
  -> orders:watch

Kết quả:
  GetOrder    -> allow
  WatchOrder  -> allow
  CancelOrder -> deny (token thiếu orders.cancel)
~~~

Phép giao giúp token giới hạn quyền thực tế của subject. Nếu một hệ thống dùng role làm nguồn cấp quyền duy nhất hoặc không dùng OAuth scopes, hãy thiết kế một mode policy riêng và thể hiện rõ điều đó. Đừng âm thầm coi scope bị thiếu là unrestricted, hoặc hợp nhất role và scope theo phép OR khiến token hẹp vẫn được dùng quyền rộng của role.

### 5.1. Principal bất biến sau authentication

Sau khi xác minh credential, chuẩn hóa thông tin cần thiết thành principal:

~~~java
package dev.example.security;

import java.util.Set;

public record GrpcPrincipal(
        String subject,
        Set<String> roles,
        Set<String> scopes,
        String tenantId) {

    public GrpcPrincipal {
        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("subject is required");
        }
        roles = Set.copyOf(roles);
        scopes = Set.copyOf(scopes);
    }
}
~~~

Khai báo một Context key dùng chung để authentication và authorization cùng đọc đúng principal:

~~~java
package dev.example.security;

import io.grpc.Context;

public final class GrpcSecurityContext {

    public static final Context.Key<GrpcPrincipal> PRINCIPAL =
            Context.key("authenticated-principal");

    private GrpcSecurityContext() {}
}
~~~

Principal chỉ chứa dữ liệu đã được xác minh và chuẩn hóa. **roles** và **scopes** không được sao chép trực tiếp từ một custom metadata header do caller tự khai. **tenantId** nếu có cũng phải đến từ claim/identity đã xác minh hoặc policy store đáng tin cậy, không phải từ request field một cách mặc định.

### 5.2. Xác minh token trước khi đọc role và scope

Authentication layer phải kiểm tra credential trước khi tạo principal. Với JWT, các bước thường gồm:

- Xác minh chữ ký bằng key phù hợp và thuật toán được cho phép.
- Kiểm tra **iss** đúng issuer tin cậy.
- Kiểm tra **aud** chứa resource server/API này.
- Kiểm tra **exp**, **nbf** và các điều kiện thời gian.
- Kiểm tra loại token và claim theo contract của issuer.
- Chuẩn hóa role/scope thành chuỗi đã định nghĩa; từ chối claim sai kiểu hoặc cấu trúc không hợp lệ.

Không giải mã JWT rồi tin payload mà chưa xác minh chữ ký. Không dùng token ID hoặc role claim làm permission chỉ vì tên claim có vẻ đáng tin. Khi token hợp lệ, authentication interceptor có thể đặt principal vào **io.grpc.Context** để authorization layer sử dụng.

Đoạn cốt lõi để gắn principal đã xác minh vào đúng Context key dùng chung:

~~~java
Context context = Context.current().withValue(
        GrpcSecurityContext.PRINCIPAL,
        principal);

return Contexts.interceptCall(context, call, headers, next);
~~~

## 6. Xây dựng permission catalog và policy theo method

Ví dụ dưới đây ánh xạ role và scope sang permission, rồi lấy phần giao. Method được định danh bằng tên đầy đủ **package.Service/Method**.

~~~java
package dev.example.security;

import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

@Component
public class GrpcPermissionPolicy {

    private final Map<String, Set<String>> roleGrants = Map.of(
            "order-reader",
            Set.of("orders:read", "orders:watch"),
            "order-operator",
            Set.of("orders:read", "orders:watch", "orders:cancel"));

    private final Map<String, Set<String>> scopeGrants = Map.of(
            "orders.read", Set.of("orders:read"),
            "orders.watch", Set.of("orders:watch"),
            "orders.cancel", Set.of("orders:cancel"));

    private final Map<String, Set<String>> methodRequirements = Map.of(
            "demo.orders.v1.OrderService/GetOrder",
            Set.of("orders:read"),
            "demo.orders.v1.OrderService/WatchOrder",
            Set.of("orders:read", "orders:watch"),
            "demo.orders.v1.OrderService/CancelOrder",
            Set.of("orders:read", "orders:cancel"));

    public boolean allows(
            GrpcPrincipal principal,
            String fullMethodName) {

        Set<String> rolePermissions =
                expand(principal.roles(), roleGrants);
        Set<String> tokenPermissions =
                expand(principal.scopes(), scopeGrants);

        // Token scope giới hạn quyền mà role có thể cấp.
        rolePermissions.retainAll(tokenPermissions);

        Set<String> required =
                methodRequirements.get(fullMethodName);

        // Method chưa khai báo policy luôn bị từ chối.
        return required != null && rolePermissions.containsAll(required);
    }

    private Set<String> expand(
            Set<String> grants,
            Map<String, Set<String>> catalog) {

        return grants.stream()
                .map(catalog::get)
                .filter(permissions -> permissions != null)
                .flatMap(Set::stream)
                .collect(Collectors.toCollection(HashSet::new));
    }
}
~~~

Trong ví dụ, **CancelOrder** cần cả **orders:read** và **orders:cancel**; token phải có cả scope tương ứng và role phải cấp cả hai permission. Một role hoặc scope không được ánh xạ sẽ không đóng góp quyền. Method không có trong **methodRequirements** bị từ chối.

Policy thực tế có thể đến từ cấu hình, database hoặc policy engine. Cần kiểm soát cache, cập nhật, audit và hành vi khi nguồn policy lỗi. Nếu policy không thể đánh giá, fail-closed thường an toàn hơn tự động cho phép.

## 7. Enforce policy trong ServerInterceptor

Authentication interceptor xác minh token và đặt principal vào Context. Authorization interceptor đọc principal, lấy full method name và kiểm tra permission:

~~~java
package dev.example.security;

import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import static dev.example.security.GrpcSecurityContext.PRINCIPAL;

public final class RoleScopeAuthorizationInterceptor
        implements ServerInterceptor {

    private final GrpcPermissionPolicy policy;

    public RoleScopeAuthorizationInterceptor(
            GrpcPermissionPolicy policy) {
        this.policy = policy;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        GrpcPrincipal principal = PRINCIPAL.get();

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

Authentication interceptor phải gắn principal bằng chính **GrpcSecurityContext.PRINCIPAL**; authorization interceptor đọc cùng key này để lấy principal của đúng RPC.

Khi không có principal, trả **UNAUTHENTICATED**. Khi principal đã xác thực nhưng effective permission không đáp ứng method policy, trả **PERMISSION_DENIED**. Không gọi **next.startCall(...)** khi đã từ chối; nếu vẫn chuyển tiếp thì service implementation vẫn chạy và policy không bảo vệ được RPC.

Đăng ký interceptor theo thứ tự để authentication chạy trước authorization. Với Spring gRPC starter, sử dụng extension point của phiên bản đang dùng; kiểm thử thứ tự thực tế bằng integration test.

## 8. Quyền method khác quyền trên tenant và resource

Role/scope/permission thường quyết định caller có thể gọi một loại method. Chúng không tự động chứng minh caller có quyền trên mọi resource mà request chỉ định.

Ví dụ **orders:read** cho phép gọi **GetOrder**, nhưng service vẫn phải kiểm tra:

- Đơn hàng có thuộc tenant của principal không?
- Subject có quan hệ sở hữu hoặc được phân công hỗ trợ đơn này không?
- Đơn hàng có trạng thái cho phép thao tác không?
- Có quy tắc che giấu sự tồn tại của resource để tránh dò ID không?

Không tin **tenant_id** hoặc **owner_id** do client gửi như bằng chứng quyền. Đối chiếu request với tenant/relationship đã xác minh hoặc dữ liệu policy đáng tin cậy. Đây là kiểm tra resource-level/domain authorization và nên diễn ra ở service/domain layer.

## 9. Role, scope và permission với streaming RPC

Authorization interceptor kiểm tra quyền method khi stream được mở. Nhưng một stream có thể mang nhiều message và nhiều resource ID.

Ví dụ:

- **WatchOrder** có thể yêu cầu **orders:read** và **orders:watch** khi mở stream.
- Nếu stream theo dõi nhiều đơn, mỗi **order_id** vẫn cần kiểm tra tenant/ownership.
- **UploadEvents** có thể cần **events:write**; mỗi event vẫn phải được kiểm tra tính hợp lệ và phạm vi dữ liệu.
- Khi quyền bị thu hồi trong lúc stream dài đang chạy, hệ thống cần chính sách rõ ràng: chỉ áp dụng ở lần mở stream hay tái kiểm tra theo chu kỳ/message.

Nếu cần thu hồi quyền tức thời, chỉ kiểm tra lúc mở stream có thể chưa đủ. Cân nhắc giới hạn thời lượng stream, revalidation theo chu kỳ hoặc cơ chế hủy subscription khi identity/policy thay đổi. Khi từ chối giữa stream, kết thúc bằng status phù hợp và cleanup tài nguyên.

## 10. Least privilege, role sprawl và vận hành policy

Các lỗi thiết kế thường gặp:

- **Role quá rộng:** admin được dùng để tránh thiết kế permission chi tiết.
- **Role trùng lặp:** nhiều role gần như giống nhau, khó audit.
- **Scope quá rộng:** token có orders.* dù chỉ cần đọc một method.
- **Permission gắn với UI:** quyền được đặt tên theo nút/màn hình thay vì hành động domain.
- **Policy mặc định allow:** method mới tự động mở cho mọi principal.
- **Claim không rõ nguồn:** role/scope lấy từ header tự khai hoặc JWT chưa xác minh.
- **Cache không có invalidation:** quyền đã thu hồi vẫn còn hiệu lực quá lâu.

Nên tổ chức role theo nhóm trách nhiệm, scope theo API/resource server và permission theo hành động domain. Review mapping định kỳ, giới hạn thời gian sống của token/cache phù hợp với mức rủi ro, và audit cả thay đổi role lẫn quyết định allow/deny.

Metrics nên dùng method, status và decision có cardinality kiểm soát. Không đưa subject ID, token, tenant ID hoặc request ID thành label metrics. Logs có thể lưu principal ID và correlation ID theo chính sách bảo mật, nhưng phải redact credential và payload nhạy cảm.

## 11. Kiểm thử role, scope và permission

Kiểm thử cần xác minh cả permission được tính ra và việc handler có được gọi hay không.

| Role | Token scope | Method | Kết quả |
| --- | --- | --- | --- |
| order-reader | orders.read | GetOrder | Allow |
| order-reader | orders.cancel | CancelOrder | Deny: role thiếu permission |
| order-operator | orders.read | CancelOrder | Deny: token thiếu scope cancel |
| order-operator | orders.read orders.cancel | CancelOrder | Allow |
| Không có role | orders.read | GetOrder | Deny |
| order-operator | Không có scope | GetOrder | Deny |
| order-operator | orders.read | Method chưa khai báo | Deny |
| order-operator | orders.read | GetOrder của tenant khác | Domain layer deny |

Các nhóm test cần có:

1. Token sai chữ ký, issuer, audience hoặc hết hạn không tạo principal.
2. Role hợp lệ nhưng scope thiếu thì permission bị giới hạn.
3. Scope hợp lệ nhưng role không cấp quyền thì vẫn bị từ chối theo policy giao nhau.
4. Method mới không có mapping bị deny.
5. Authentication chạy trước authorization; handler không được gọi khi deny.
6. Tenant/resource authorization được kiểm tra độc lập với quyền method.
7. Streaming kiểm tra quyền method khi mở và resource theo message khi cần.
8. Audit ghi quyết định nhưng không làm lộ token hoặc metadata nhạy cảm.

Một test in-process có thể dùng authenticator giả để tạo principal có role/scope cụ thể, gọi generated stub và assert status. Đặt mock/flag ở service implementation để xác minh handler không chạy khi bị từ chối. Với JWT/mTLS thực tế, bổ sung test qua transport thật để xác minh identity được thiết lập đúng.

## 12. Bài thực hành và câu hỏi tự kiểm tra

### Bài thực hành

1. Định nghĩa **OrderService** có **GetOrder**, **WatchOrder** và **CancelOrder**.
2. Tạo principal bất biến chứa subject, roles, scopes và tenant đã xác minh.
3. Xây permission catalog ánh xạ **order-reader** và **order-operator** sang các permission orders.
4. Ánh xạ scope **orders.read**, **orders.watch**, **orders.cancel** sang permission tương ứng.
5. Viết policy tính effective permission bằng phần giao giữa role grants và token scope grants.
6. Enforce method policy bằng ServerInterceptor; method chưa khai báo phải bị từ chối.
7. Bổ sung domain check để ngăn đọc/hủy order thuộc tenant khác.
8. Viết test cho role rộng nhưng scope hẹp, scope rộng nhưng role thiếu quyền, token không hợp lệ, method mới và streaming resource check.

### Câu hỏi tự kiểm tra

**1. Role khác permission thế nào?**  
Role gom nhóm năng lực của subject; permission mô tả hành động cụ thể mà policy có thể kiểm tra.

**2. Scope thường đại diện cho điều gì trong OAuth 2.0?**  
Phạm vi truy cập mà access token được cấp cho client/resource server, không phải role lâu dài của user.

**3. Vì sao scope có thể giới hạn role?**  
Role có thể cấp năng lực rộng, trong khi token hiện tại chỉ được cấp một phần phạm vi. Lấy phần giao giúp token không vượt quá quyền đã cấp.

**4. Có nên coi role admin là allow mọi method không?**  
Không mặc định. Phải ánh xạ rõ permission, service/method và các điều kiện bổ sung; quyền rộng cần được giới hạn và audit.

**5. Permission orders:read có cho phép đọc mọi đơn hàng không?**  
Không. Nó có thể cho phép gọi method đọc; tenant, ownership và resource policy vẫn phải được kiểm tra.

**6. Method mới chưa có policy nên xử lý thế nào?**  
Deny-by-default cho tới khi mapping role/scope/permission được khai báo và kiểm thử.

**7. Có thể chỉ kiểm tra scope khi mở streaming RPC không?**  
Scope có thể đủ cho quyền gọi method, nhưng từng resource trong message vẫn cần kiểm tra nếu stream truy cập nhiều tenant/tài nguyên.

**8. Nếu claim scope không xuất hiện trong token thì sao?**  
Áp dụng đúng contract của issuer và policy đã công bố. Không tự coi scope thiếu là unrestricted; với mô hình yêu cầu scope, từ chối.

## Tổng kết

**Role** nhóm năng lực của subject; **scope** giới hạn phạm vi mà access token được cấp; **permission** biểu diễn hành động cụ thể mà server kiểm tra. Trong Spring gRPC, authentication phải xác minh credential và chuẩn hóa role/scope thành principal trước khi authorization chạy. Policy có thể ánh xạ role và scope sang permission rồi lấy phần giao để giới hạn quyền thực tế; service/method chưa có rule phải bị từ chối. Quyền gọi method vẫn cần kết hợp kiểm tra tenant, ownership và trạng thái resource ở domain layer, đặc biệt với streaming. Thiết kế rõ mapping, deny-by-default, audit và test các tổ hợp role/scope giúp tránh cấp quyền rộng hơn token hoặc nhu cầu thực tế.

