# Chọn scope hay role claim

> **Chương:** Quyết định thiết kế  
> **Module:** SECURITY_TOKEN_SECURITY_FUNDAMENTALS  
> **Bối cảnh:** Nắm mô hình tin cậy và vòng đời token bảo mật; phân biệt JWT, opaque token, access token và refresh token trong xác thực, phân quyền và OAuth 2.0/OIDC; phát hành, kiểm tra claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **OAuth scope** với **role claim** về ý nghĩa, nguồn cấp và phạm vi sử dụng.
2. Chọn mô hình phù hợp cho API authorization, nghiệp vụ nội bộ và service-to-service.
3. Nhận diện khi nào nên dùng scope, role, permission claim hoặc kết hợp nhiều loại.
4. Thiết kế access token có audience, scope và role claim đúng ranh giới tin cậy.
5. Ánh xạ claim thành authority trong Spring Security mà không nhầm role prefix với scope prefix.
6. Đánh giá token size, độ trễ thu hồi, tenant context, khả năng mở rộng và rủi ro lộ thông tin.
7. Xây dựng decision matrix và kiểm thử cho các quyết định authorization.

## 1. Bài toán: scope hay role claim?

Khi một API nhận access token, nó cần quyết định chủ thể được phép thực hiện hành động nào. Hai cách thường gặp là:

- **Scope:** token mang các quyền được cấp cho một resource/API, ví dụ đọc đơn hàng hoặc tạo thanh toán.
- **Role claim:** token mang vai trò của chủ thể trong một ứng dụng hoặc miền nghiệp vụ, ví dụ quản trị viên tenant, nhân viên hỗ trợ hoặc kế toán.

Ví dụ một người dùng có role TENANT_ADMIN trong hệ thống quản lý tổ chức. Role đó có thể cho phép quản trị thành viên, xem cấu hình và đọc báo cáo. Nhưng khi gọi Orders API, API có thể chỉ cần biết token được cấp scope orders.read hoặc orders.write.

Hai cách này trả lời hai câu hỏi liên quan nhưng khác nhau:

- Scope: **token được cấp quyền truy cập API/resource nào và thực hiện capability nào?**
- Role: **chủ thể đang giữ vị trí hoặc nhóm quyền nào trong miền nghiệp vụ?**

Không có quy tắc rằng mọi hệ thống phải chỉ dùng một trong hai. Quyết định phụ thuộc vào ranh giới API, mô hình quyền nghiệp vụ, cách Authorization Server cấp token và nơi cần thực thi policy.

~~~mermaid
flowchart TD
    T["Access token đã xác minh"] --> S["Scope<br/>orders.read"]
    T --> R["Role claim<br/>TENANT_ADMIN"]
    S --> A["API capability<br/>được cấp cho resource"]
    R --> P["Business role<br/>được gán cho subject"]
    A --> D["Authorization decision"]
    P --> D
    D --> X["Kiểm tra tenant, ownership,<br/>trạng thái và policy"]
    X --> O["Allow / Deny"]
~~~

## 2. Scope là gì?

Trong OAuth 2.0, **scope** là chuỗi biểu diễn phạm vi quyền mà client yêu cầu và Authorization Server có thể cấp. Scope thường được dùng để giới hạn quyền truy cập API hoặc resource. Ví dụ:

- orders.read
- orders.write
- inventory.read
- payments.create
- profile.read

Client có thể yêu cầu scope khi xin access token, nhưng Authorization Server quyết định cấp scope nào theo client registration, consent, subject, resource và policy. Scope được yêu cầu không đồng nghĩa scope chắc chắn được cấp.

### Scope gắn với resource

Một scope cần có ý nghĩa rõ với resource server chịu trách nhiệm thực thi nó. Ví dụ:

| Resource server | Scope | Ý nghĩa |
|---|---|---|
| Orders API | orders.read | Đọc dữ liệu đơn hàng theo policy |
| Orders API | orders.cancel | Hủy đơn hàng theo policy |
| Inventory API | inventory.read | Đọc tồn kho |
| Payment API | payments.create | Tạo yêu cầu thanh toán |
| Profile API | profile.read | Đọc hồ sơ được phép |

Scope không tự động chứng minh quyền truy cập vào mọi bản ghi. Một token có orders.read vẫn có thể chỉ được đọc đơn hàng thuộc tenant hoặc subject cụ thể. API phải kiểm tra object-level authorization, tenant và trạng thái nghiệp vụ.

### Scope trong token

Một access token JWT có thể chứa scope dưới dạng chuỗi phân tách bằng dấu cách:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.cancel",
  "exp": 1893456000
}
~~~

Một số nhà cung cấp dùng claim scp dạng mảng hoặc cấu trúc riêng. Cách biểu diễn không phải lúc nào cũng giống nhau; resource server cần tuân theo contract của Authorization Server và profile token đang dùng.

Scope thường được ánh xạ thành authority có prefix SCOPE_ trong Spring Security, ví dụ SCOPE_orders.read. Đây là quy ước mapping của framework, không phải nội dung bắt buộc của chuỗi scope trong OAuth.

## 3. Role claim là gì?

**Role** là vai trò được gán cho một principal trong miền nghiệp vụ hoặc ứng dụng. Ví dụ:

- TENANT_ADMIN
- ORDER_MANAGER
- FINANCE_APPROVER
- SUPPORT_AGENT
- AUDITOR

Role thường nhóm nhiều quyền có liên quan. Ví dụ ORDER_MANAGER có thể được phép xem đơn hàng, cập nhật trạng thái và xử lý yêu cầu hủy. Tuy nhiên, ý nghĩa role do tổ chức và ứng dụng định nghĩa; OAuth 2.0 không chuẩn hóa một claim role chung cho mọi Authorization Server.

Một JWT có thể chứa role claim:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "alice",
  "aud": ["orders-api"],
  "roles": ["ORDER_MANAGER", "TENANT_ADMIN"],
  "tenant_id": "tenant-a",
  "exp": 1893456000
}
~~~

Trong ví dụ này, roles là claim theo contract riêng của hệ thống. Một nhà cung cấp khác có thể đặt role trong claim lồng như realm_access.roles hoặc resource_access.orders-api.roles. Resource server không nên giả định mọi token đều dùng cùng tên hoặc cấu trúc claim.

### Role thường gắn với chủ thể và miền nghiệp vụ

Role có thể được gán:

- Toàn hệ thống: PLATFORM_AUDITOR.
- Trong một tenant: TENANT_ADMIN của tenant A.
- Trong một ứng dụng: ORDER_MANAGER.
- Trong một phạm vi tài nguyên: PROJECT_MAINTAINER của project cụ thể.

Role không có phạm vi rõ ràng dễ tạo ra lỗi privilege escalation. Nếu một người là ADMIN ở tenant A, không được suy ra người đó là ADMIN ở tenant B.

### Role claim là snapshot tại thời điểm cấp token

Nếu Authorization Server ghi role vào JWT, resource server thường thấy trạng thái role tại thời điểm token được phát hành. Khi role bị gỡ, JWT self-contained vẫn có thể mang role cũ cho tới khi hết hạn, trừ khi có cơ chế kiểm tra trạng thái hoặc thu hồi bổ sung.

Vì vậy, role claim phải được thiết kế cùng token lifetime, refresh policy, revocation và yêu cầu hiệu lực thay đổi quyền.

## 4. Scope và role khác nhau ở đâu?

| Tiêu chí | Scope | Role claim |
|---|---|---|
| Ý nghĩa | Capability/phạm vi quyền được cấp cho access token | Vai trò của subject trong ứng dụng/miền nghiệp vụ |
| Nguồn cấp | Authorization Server dựa trên client, subject, resource và policy | Identity/authorization domain gán cho user hoặc workload |
| Phạm vi | Thường gắn với API/resource và grant | Thường gắn với subject, tenant hoặc ứng dụng |
| Vòng đời | Theo access token/grant và policy cấp quyền | Theo membership/role assignment, nhưng claim trong JWT là snapshot |
| Ví dụ | orders.read, payments.create | ORDER_MANAGER, FINANCE_APPROVER |
| Cách dùng | API kiểm tra capability được token cấp | API hoặc service diễn giải vai trò theo policy |
| Tính di động | Có thể chuẩn hóa theo resource/API contract | Thường phụ thuộc mô hình role của tổ chức |
| Rủi ro | Scope quá rộng hoặc không ràng buộc đúng audience | Role toàn cục, role stale hoặc lộ cấu trúc nội bộ |
| Spring authority phổ biến | SCOPE_orders.read | ROLE_ORDER_MANAGER |

Không nên kết luận scope luôn chi tiết hơn role hoặc role luôn rộng hơn scope. Một hệ thống có thể định nghĩa scope rất rộng và role rất cụ thể. Điều quan trọng là semantics, owner và nơi thực thi phải được xác định rõ.

## 5. Khi nào nên chọn scope?

Scope thường là lựa chọn phù hợp khi quyền cần thể hiện rõ trong hợp đồng giữa OAuth client và resource server.

Chọn scope khi:

- API cần phân biệt quyền đọc, ghi, tạo, hủy hoặc phê duyệt.
- Client chỉ nên nhận một tập capability cụ thể cho từng resource.
- Cần downscope token theo từng lần gọi hoặc token exchange.
- Có nhiều client với quyền khác nhau trên cùng API.
- Muốn resource server kiểm tra quyền mà không cần hiểu toàn bộ sơ đồ chức danh của doanh nghiệp.
- Cần kiểm soát quyền service-to-service theo audience/resource.

Ví dụ client mobile chỉ cần orders.read; service đồng bộ nội bộ cần orders.read và orders.write; payment worker cần payments.create. Scope cho phép Authorization Server cấp đúng capability theo từng client và resource.

### Scope nên theo capability của API

Tên scope cần ổn định, có owner và được tài liệu hóa. Tránh tên mơ hồ như admin, full_access hoặc all nếu không có semantics rõ. Scope quá tổng quát làm mất lợi ích của least privilege.

Một số nguyên tắc:

- Tách quyền đọc và ghi khi rủi ro khác nhau.
- Tách thao tác nhạy cảm như refund, approve hoặc delete.
- Không dùng scope để mã hóa mọi điều kiện nghiệp vụ.
- Giới hạn scope theo audience/resource.
- Kiểm tra quyền trên đối tượng và tenant sau khi scope hợp lệ.
- Có versioning/migration plan khi thay đổi semantics scope.

## 6. Khi nào nên chọn role claim?

Role claim phù hợp khi ứng dụng cần ra quyết định dựa trên vai trò ổn định của subject và nhiều method/feature cùng diễn giải vai trò đó.

Chọn role claim khi:

- Nghiệp vụ đã có mô hình role rõ ràng như auditor, approver, manager.
- Nhiều thao tác trong cùng ứng dụng dùng chung một nhóm quyền.
- Quyền được quản lý tập trung theo user/tenant membership.
- Service cần phân biệt người dùng và loại trách nhiệm nghiệp vụ.
- Role được cấp từ nguồn identity/authorization đáng tin cậy và có policy cập nhật rõ.

Ví dụ FINANCE_APPROVER có thể được phép phê duyệt một loại giao dịch, nhưng việc phê duyệt vẫn cần kiểm tra hạn mức, tenant, trạng thái giao dịch, separation of duties và người tạo giao dịch.

### Không dùng role để thay thế mọi kiểm soát API

Nếu chỉ kiểm tra TENANT_ADMIN, token có thể mang quyền quản trị quá rộng tới nhiều API. Một role có ý nghĩa trong ứng dụng quản lý tenant không nhất thiết có quyền gọi Payment API hoặc đọc dữ liệu nhạy cảm ở mọi resource.

Có thể dùng role để xác định nhóm quyền, sau đó map role sang capability cụ thể ở service. Với API contract OAuth, scope vẫn giúp giới hạn quyền token tới resource server.

## 7. Mô hình kết hợp scope và role

Nhiều hệ thống nên dùng cả hai nhưng với trách nhiệm riêng:

- Scope giới hạn capability mà access token được cấp cho API.
- Role cung cấp ngữ cảnh vai trò nghiệp vụ của subject.
- Tenant/membership xác định phạm vi tổ chức.
- Object-level policy xác định subject có thể thao tác trên tài nguyên cụ thể không.

Ví dụ Alice có role ORDER_MANAGER trong tenant A. Access token cho Orders API có scope orders.read và orders.cancel. Khi Alice hủy order-a1 thuộc tenant A, API kiểm tra scope, role, tenant, ownership/workflow và trạng thái đơn hàng.

~~~mermaid
flowchart TD
    T["Access token"] --> V["Validate issuer, audience,<br/>signature/introspection, expiry"]
    V --> S["Scope check<br/>orders.cancel"]
    S --> R["Role check<br/>ORDER_MANAGER"]
    R --> N["Tenant membership<br/>tenant-a"]
    N --> O["Object/workflow policy<br/>order-a1"]
    O --> A["Allow cancel"]
    S --> D["Deny"]
    R --> D
    N --> D
    O --> D
~~~

Không phải mọi API đều cần mọi lớp. Chỉ áp dụng những điều kiện có ý nghĩa cho nghiệp vụ, nhưng không bỏ qua object-level authorization chỉ vì scope và role đã hợp lệ.

## 8. Decision matrix: chọn theo nhu cầu

| Nhu cầu | Lựa chọn phù hợp | Lý do |
|---|---|---|
| API chỉ cần quyền đọc/ghi cụ thể | Scope | Capability rõ theo resource |
| Nhiều client gọi cùng API với quyền khác nhau | Scope | Authorization Server cấp quyền riêng theo client/grant |
| Nghiệp vụ có nhóm vai trò như auditor/approver | Role claim hoặc role lookup | Phản ánh responsibility của subject |
| Role chỉ có ý nghĩa trong một tenant | Role + tenant context | Ngăn role bị áp dụng xuyên tenant |
| Service-to-service không đại diện user | Scope với workload/client identity | Giới hạn capability của workload |
| Service gọi thay mặt user | Scope + subject/actor context, có thể thêm role | Giữ quyền API và ngữ cảnh người dùng |
| Quyền thay đổi rất thường xuyên | Authorization lookup/introspection hoặc token ngắn hạn | Giảm thời gian role snapshot cũ còn hiệu lực |
| API cần kiểm soát quyền trên từng object | Scope/role kết hợp object policy | Claim không thay thế ownership/relationship check |
| Token cần tối giản | Scope tối thiểu hoặc policy lookup | Tránh nhúng toàn bộ role/permission graph |
| Nhiều ứng dụng có role semantics khác nhau | Scope theo API; role mapping tại từng domain | Tránh phụ thuộc role nội bộ xuyên hệ thống |

### Quy tắc quyết định nhanh

1. Nếu câu hỏi là “client được phép gọi capability nào của API này?”, bắt đầu với scope.
2. Nếu câu hỏi là “subject có trách nhiệm nghiệp vụ nào trong domain?”, dùng role.
3. Nếu cần cả hai, giữ semantics tách biệt và kiểm tra độc lập.
4. Nếu quyền phụ thuộc bản ghi, tenant, amount hoặc trạng thái workflow, dùng authorization policy tại server.
5. Nếu thay đổi quyền phải có hiệu lực gần như tức thời, cân nhắc introspection, online policy check hoặc token lifetime ngắn cùng revocation strategy.

## 9. Thiết kế claim và token payload

Ví dụ token kết hợp scope, role và tenant:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "web-portal",
  "scope": "orders.read orders.cancel",
  "roles": ["ORDER_MANAGER"],
  "tenant_id": "tenant-a",
  "exp": 1893456000
}
~~~

Cần hiểu từng trường:

- iss: nguồn phát hành token.
- sub: subject mà token đại diện.
- aud: resource server được phép nhận token.
- client_id: OAuth client liên quan theo token profile.
- scope: capability được cấp cho access token.
- roles: role claim theo contract riêng của hệ thống.
- tenant_id: tenant context đã được issuer xác minh.
- exp: thời điểm token hết hiệu lực.

Không đưa toàn bộ role, group và permission graph vào JWT. Token có thể tăng kích thước, lộ cấu trúc tổ chức và tạo snapshot quyền khó thu hồi. JWT ký thường chỉ đảm bảo integrity, không mã hóa payload; người nắm token có thể đọc claims.

### Role claim trong access token hay ID token?

API authorization nên dựa trên access token được cấp cho API. Không lấy role từ ID token rồi dùng nó như credential gọi API. ID token phục vụ OIDC client; audience và mục đích khác access token.

Nếu client cần hiển thị UI theo role, có thể dùng thông tin identity phù hợp với OIDC client, nhưng quyết định bảo mật cuối cùng vẫn phải được API thực hiện bằng access token và policy server-side.

### Không tin claim do client tự gửi

Không nhận role, scope hoặc tenant từ header/body rồi đưa thẳng vào SecurityContext. Claims phải được phát hành bởi issuer tin cậy, token phải được xác minh và mapping phải theo schema đã đăng ký.

## 10. Token size, privacy và least privilege

Nhúng nhiều role và permission vào token có các trade-off:

- **Token size:** header HTTP lớn hơn, ảnh hưởng proxy, gateway, cookie và giới hạn request.
- **Privacy:** role/group có thể tiết lộ chức vụ, dự án, tenant hoặc quan hệ nội bộ.
- **Staleness:** JWT có thể giữ role cũ đến khi hết hạn.
- **Revocation:** thay đổi role không tự động sửa JWT đã phát hành.
- **Coupling:** resource server phụ thuộc cấu trúc role của Identity Provider.
- **Policy drift:** nhiều service tự diễn giải role theo cách khác nhau.

Scope cũng có thể quá nhiều hoặc quá rộng. Không giải quyết vấn đề bằng cách nhét toàn bộ quyền vào access token.

Hãy ưu tiên:

- Token chỉ chứa claims cần cho resource server.
- Audience hẹp theo API.
- Scope tối thiểu cho thao tác.
- Role claim chỉ khi consumer thật sự cần semantics role.
- Role-to-permission mapping được quản lý ở domain có thẩm quyền.
- Token lifetime phù hợp với độ nhạy của quyền.
- Introspection/online authorization cho quyền cần cập nhật nhanh.
- Pseudonymization và log redaction cho subject/role metadata.

## 11. Scope, role và tenant trong hệ thống multi-tenant

Một role như TENANT_ADMIN không có ý nghĩa an toàn nếu thiếu tenant context. Người dùng có thể là admin ở tenant A nhưng chỉ là member ở tenant B.

Ví dụ:

~~~json
{
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.cancel",
  "tenant_id": "tenant-a",
  "roles": ["TENANT_ADMIN"]
}
~~~

API cần xác minh role được gắn với tenant-a và membership còn hợp lệ theo policy. Không nhận header X-Tenant-Id=tenant-b để ghi đè tenant claim nếu không có quy trình chuyển tenant và kiểm tra membership.

Nếu người dùng có nhiều tenant, có thể dùng token tenant-bound riêng cho từng tenant context hoặc online membership/policy check. Tránh phát một token chứa danh sách hàng trăm tenant và toàn bộ role của người dùng nếu API chỉ cần một tenant tại một thời điểm.

## 12. Service-to-service và client credentials

Với client credentials grant, subject thường đại diện client/workload thay vì user. Trong trường hợp này, scope thường là cách tự nhiên để giới hạn capability của workload:

- orders.read
- inventory.reserve
- reporting.export

Có thể có role claim cho workload như BATCH_PROCESSOR hoặc BILLING_WORKER nếu role mang semantics riêng trong domain. Tuy nhiên, đừng thêm role chỉ để nhân đôi scope.

Nếu service gọi thay mặt user, token exchange có thể giữ subject và thể hiện actor. Khi đó:
- Scope giới hạn quyền API đích.
- Subject giữ danh tính người dùng được đại diện.
- Actor cho biết service đang thực hiện hành động.
- Tenant/resource policy giới hạn dữ liệu.
- Role claim chỉ được dùng nếu policy downstream thực sự cần role đó.

Không chuyển nguyên bearer token có audience của service A sang service B. Token exchange hoặc workload token riêng phải cấp audience và scope phù hợp.

## 13. Ánh xạ scope và role trong Spring Security

Spring Security thường ánh xạ scope thành authority có prefix SCOPE_. Role có thể được ánh xạ thành ROLE_ nếu ứng dụng sử dụng convention đó.

Ví dụ kiểm tra scope:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Order getOrder(String id) {
    return orderRepository.findById(id).orElseThrow();
}
~~~

Ví dụ kiểm tra role:

~~~java
@PreAuthorize("hasRole('ORDER_MANAGER')")
public void cancelOrder(String id) {
    orderWorkflow.cancel(id);
}
~~~

hasRole('ORDER_MANAGER') thường kiểm tra authority ROLE_ORDER_MANAGER theo role prefix mặc định. hasAuthority so sánh chuỗi authority chính xác. Không viết hasRole('ROLE_ORDER_MANAGER') nếu framework tự thêm prefix ROLE_.

### Ánh xạ claim scope và roles

Ví dụ converter cho JWT có scope dạng chuỗi và roles dạng danh sách:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class TokenAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private final JwtGrantedAuthoritiesConverter scopeConverter =
        new JwtGrantedAuthoritiesConverter();

    public TokenAuthoritiesConverter() {
        scopeConverter.setAuthoritiesClaimName("scope");
        scopeConverter.setAuthorityPrefix("SCOPE_");
    }

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        List<GrantedAuthority> result = new ArrayList<>();

        Collection<GrantedAuthority> scopes =
            scopeConverter.convert(jwt);

        if (scopes != null) {
            result.addAll(scopes);
        }

        List<String> roles = jwt.getClaimAsStringList("roles");
        if (roles != null) {
            roles.stream()
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .forEach(result::add);
        }

        return result;
    }
}
~~~

Đăng ký converter với JWT authentication converter:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(
        new TokenAuthoritiesConverter()
    );

    return converter;
}
~~~

Ví dụ này giả định role claim là danh sách chuỗi tên roles ở claim cấp cao. Nếu Identity Provider phát role trong claim lồng hoặc dùng scp thay scope, hãy viết converter theo đúng contract. Không tự động tin mọi role claim chỉ vì nó có mặt trong JWT; issuer, audience, chữ ký, thời gian và token profile vẫn phải được xác minh trước.

### Kết hợp scope và role trong method policy

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.cancel') " +
    "and hasRole('ORDER_MANAGER')"
)
public void cancelOrder(String orderId) {
    orderWorkflow.cancel(orderId);
}
~~~

Đây chỉ là kiểm tra capability và role. Service vẫn phải kiểm tra tenant, ownership, trạng thái đơn hàng, hạn mức và separation of duties nếu nghiệp vụ yêu cầu.

## 14. Không biến role thành quyền toàn cục

Các tên như ADMIN, SUPERUSER hoặc SUPPORT có thể bị diễn giải quá rộng khi nhiều API dùng chung token.

Nên xác định:

- Role thuộc ứng dụng nào?
- Role thuộc tenant nào?
- Role cho phép action gì?
- Role có thời hạn hoặc điều kiện nào?
- API nào được phép hiểu role đó?
- Role được cấp bởi issuer nào?
- Có cần role claim trong access token hay service có thể truy vấn policy?
- Thay đổi role có hiệu lực trong bao lâu?

Có thể namespace role theo domain, ví dụ ORDERS_MANAGER hoặc BILLING_AUDITOR. Nếu role được định nghĩa ở nhiều ứng dụng, không mặc định cùng tên có cùng ý nghĩa.

Với quyền đặc biệt như platform admin hoặc support access, cần policy riêng, phạm vi resource cụ thể, thời hạn, audit và cơ chế thu hồi.

## 15. Kiểm thử scope và role claim

Một bộ test phải chứng minh cả trường hợp được phép và bị từ chối.

### Ma trận kiểm thử

| Subject | Scope | Role | Resource | Kết quả mong đợi |
|---|---|---|---|---|
| Alice, tenant A | orders.read | ORDER_MANAGER | order A | Cho phép đọc |
| Alice, tenant A | orders.read | Không có | order A | Cho phép đọc nếu role không bắt buộc |
| Alice, tenant A | orders.cancel | ORDER_MANAGER | order A | Cho phép nếu workflow hợp lệ |
| Alice, tenant A | orders.cancel | Không có | order A | Từ chối nếu policy yêu cầu role |
| Bob, tenant B | orders.read | ORDER_MANAGER của B | order A | Từ chối cross-tenant |
| Alice | profile.read | ORDER_MANAGER | Orders API | Từ chối vì thiếu scope |
| Service A | inventory.read | BATCH_PROCESSOR | Inventory API | Cho phép đọc theo policy |
| Service A | inventory.read | BATCH_PROCESSOR | Payment API | Từ chối sai audience |
| Alice | orders.cancel | ORDER_MANAGER cũ | order A | Từ chối sau revoke theo SLA |
| Alice | orders.read | Role claim giả từ header | order A | Không dùng claim tự khai |

### Test các lỗi mapping

- Scope claim là chuỗi nhưng converter mong mảng.
- Token dùng scp trong khi converter chỉ đọc scope.
- Role claim bị thiếu hoặc sai kiểu.
- Role claim nằm trong nested object nhưng converter đọc cấp cao.
- Authority prefix bị thêm hai lần.
- Role ở tenant A bị dùng cho tenant B.
- ID token có roles nhưng API chỉ nhận access token.
- Token từ issuer khác có claim roles giống nhau.
- JWT role snapshot còn cũ sau khi membership bị thu hồi.
- Token exchange vô tình giữ scope hoặc role vượt quyền cần thiết.

### Test integration

Dùng JWT ký bằng test key hoặc Authorization Server test để kiểm tra:
- Issuer và audience.
- Chữ ký và thuật toán.
- Scope mapping.
- Role claim mapping.
- Tenant context và membership.
- Revocation/introspection nếu kiến trúc hỗ trợ.
- HTTP 401 cho token không hợp lệ và 403 cho token hợp lệ nhưng thiếu quyền.

Test chỉ tạo Authentication giả có thể kiểm tra method authorization nhưng không chứng minh JWT decoder hoặc claim mapping thật hoạt động.

## 16. Những anti-pattern cần tránh

| Anti-pattern | Vấn đề | Hướng xử lý |
|---|---|---|
| Chỉ dùng ADMIN cho mọi API | Quyền quá rộng, khó least privilege | Scope riêng theo resource và action |
| Nhét toàn bộ permission vào JWT | Token lớn, stale, khó thu hồi | Chỉ đưa quyền cần thiết hoặc dùng policy lookup |
| Dùng scope thay tenant/object policy | Có thể đọc dữ liệu tenant khác | Kiểm tra tenant và resource ownership |
| Dùng role claim từ ID token tại API | Sai token purpose/audience | Dùng access token cho API |
| Tin role từ header/body | Client có thể tự nâng quyền | Chỉ dùng claim từ token đã xác minh |
| Dùng cùng role name ở mọi domain | Semantics không thống nhất | Namespace và document role |
| Không xét token lifetime khi role thay đổi | Quyền cũ còn hiệu lực | TTL, revocation hoặc online policy |
| Map mọi group thành role | Token bloat và quyền ngoài ý muốn | Allowlist group/role cần thiết |
| Dùng role làm scope | Trộn responsibility và API capability | Giữ hai khái niệm riêng |
| Cấp mọi scope theo role mà không policy | Client có thể nhận quyền rộng hơn nhu cầu | Scope theo client/resource/consent |

## 17. Quy trình ra quyết định cho một API mới

Khi thiết kế authorization cho API, có thể làm theo trình tự:

1. Xác định resource server và audience riêng.
2. Liệt kê capability cần bảo vệ: read, create, update, delete, approve, refund.
3. Xác định client nào được phép yêu cầu từng capability.
4. Thiết kế scope tối thiểu và policy cấp scope.
5. Xác định có role nghiệp vụ nào thật sự cần thiết ở API hay không.
6. Xác định role thuộc tenant/app/domain nào và ai là nguồn phát hành.
7. Quyết định role nằm trong access token hay được tra cứu online.
8. Xác định tenant, actor, ownership và điều kiện workflow.
9. Đặt token lifetime/revocation phù hợp với độ nhạy quyền.
10. Viết negative tests cho sai audience, thiếu scope, role sai, tenant sai và quyền bị thu hồi.

### Ví dụ quyết định: Orders API

Yêu cầu:
- Web client đọc đơn hàng của người dùng.
- Order manager có thể hủy đơn trong tenant của mình.
- Payment service không được gọi chức năng hủy đơn.
- Platform support chỉ truy cập khi có quy trình break-glass.

Thiết kế có thể là:
- Audience: orders-api.
- Scope: orders.read, orders.cancel.
- Role claim: ORDER_MANAGER chỉ khi cần xác định trách nhiệm nghiệp vụ.
- Tenant: tenant context được xác minh.
- Object policy: order thuộc tenant và workflow cho phép.
- Support access: policy riêng, thời hạn ngắn, audit và approval.

Web client không cần nhận orders.cancel chỉ vì user là ORDER_MANAGER nếu client đó chỉ có chức năng đọc. Authorization Server cấp scope theo client/resource và policy, còn API kiểm tra role và object-level rule cho thao tác nhạy cảm.

## 18. Tổng kết

**Scope** thể hiện capability được Authorization Server cấp cho access token và thường gắn với resource/API. **Role claim** thể hiện vai trò của subject trong một ứng dụng hoặc miền nghiệp vụ; cấu trúc và semantics role thường là contract riêng của hệ thống, không phải claim chuẩn hóa chung của OAuth 2.0.

Hãy ưu tiên scope để giới hạn quyền client/API theo audience và dùng role khi nghiệp vụ thật sự cần biết trách nhiệm của subject. Có thể kết hợp cả hai: scope giới hạn capability, role cung cấp ngữ cảnh nghiệp vụ, còn tenant và object-level policy quyết định tài nguyên cụ thể có được truy cập hay không.

Quyết định phải tính tới token lifetime, thay đổi quyền, revocation, token size, privacy, multi-tenant và cách ánh xạ authority ở resource server. **Chọn claim theo câu hỏi authorization mà nó trả lời, giữ semantics rõ ràng và kiểm tra quyền tại API; không để một role hoặc scope rộng trở thành quyền truy cập toàn hệ thống.**
