# Role, authority, permission, scope và quan hệ giữa các khái niệm

> Bài Knowledge thuộc **Spring Security – authorization**, phần **Bức tranh phân quyền**.

## 1. Vì sao cần phân biệt bốn khái niệm?

Trong hệ thống quản lý hóa đơn, một nhân viên đã đăng nhập vẫn có thể bị cấm đọc hóa đơn của tổ chức khác; kế toán có thể được sửa hóa đơn nháp nhưng không được duyệt; ứng dụng thứ ba có thể nhận access token chỉ được đọc dữ liệu. Những quyết định này không thể giải thích đầy đủ bằng một cờ `authenticated=true`.

- **Authentication (xác thực)**: nhận diện chủ thể đang yêu cầu.
- **Authorization (phân quyền)**: chủ thể đó được thực hiện hành động nào trên tài nguyên nào, trong ngữ cảnh nào?

Role, authority, permission và scope là bốn cách biểu đạt các phần khác nhau của quyết định phân quyền. Trong Spring Security, chúng có thể liên hệ thông qua `Authentication` và `GrantedAuthority` nhưng **không phải bốn tên đồng nghĩa**.

Mục tiêu bài học: hiểu đúng thuật ngữ, nắm cách ánh xạ role/permission/OAuth scope thành authority, phân biệt `hasRole` với `hasAuthority`, và biết khi nào phải kết hợp kiểm tra tài nguyên, tenant, ownership thay vì chỉ kiểm tra chuỗi quyền.

## 2. Bảng khái niệm nền tảng

| Khái niệm | Vai trò | Ví dụ | Không tự bảo đảm |
|---|---|---|---|
| **Role (vai trò)** | Nhóm trách nhiệm/người dùng theo nghiệp vụ | `VIEWER`, `ACCOUNTANT`, `FINANCE_ADMIN` | Không tự cấp mọi quyền hoặc tự có quyền trên mọi bản ghi |
| **Permission (quyền thao tác)** | Khả năng làm hành động trên loại tài nguyên hoặc đối tượng | `invoice:read`, `invoice:approve` | Không cho phép vượt ranh giới tenant/owner khi policy có giới hạn |
| **Authority (quyền dạng Spring Security)** | Giá trị mà Spring Security đối chiếu khi phân quyền | `ROLE_ACCOUNTANT`, `invoice:read`, `SCOPE_invoices.read` | Không tự giải thích ý nghĩa business của từng chuỗi |
| **Scope (phạm vi)** | OAuth: quyền truy cập được cấp cho token/client; nghiệp vụ: ranh giới dữ liệu/ngữ cảnh | OAuth `invoices.read`; dữ liệu `tenant=T1` | Không tự đồng nghĩa với role hoặc ownership |

**Cách nhớ:** role trả lời “thuộc nhóm nào?”, permission trả lời “làm được hành động nào?”, authority trả lời “Spring Security nhìn thấy chuỗi quyền gì?”, OAuth scope trả lời “access token được cấp phạm vi nào?”. Khi nói “scope theo tenant” trong nghiệp vụ, cần ghi rõ đó là một loại **ràng buộc dữ liệu**, không phải scope OAuth.

## 3. Role: nhóm trách nhiệm và mô hình RBAC

Role thường là đơn vị người quản trị dễ gán cho tài khoản:

- `VIEWER`: đọc hóa đơn trong phạm vi được phép.
- `ACCOUNTANT`: tạo, đọc, chỉnh sửa hóa đơn nháp.
- `FINANCE_ADMIN`: duyệt hóa đơn và quản lý chính sách tài chính.

Ứng dụng **có thể tự định nghĩa** ánh xạ sau:

| Role nghiệp vụ | Permission được cấp |
|---|---|
| `VIEWER` | `invoice:read` |
| `ACCOUNTANT` | `invoice:read`, `invoice:create`, `invoice:update_draft` |
| `FINANCE_ADMIN` | `invoice:read`, `invoice:approve`, `finance:settings:update` |

Đây là thiết kế RBAC (*Role-Based Access Control*) mẫu, **không phải luật mặc định do Spring Security suy ra**. Nếu database hay IAM không xây dựng ánh xạ role → permission, người có `ROLE_ACCOUNTANT` không mặc nhiên sở hữu authority `invoice:update_draft`. Có hệ thống kiểm tra thẳng role; có hệ thống gom các permission hiệu lực từ role; hai cách cần được thiết kế và kiểm thử nhất quán.

Role đơn thuần thường chưa đủ chính xác cho dữ liệu theo từng đối tượng. Hai người cùng vai trò `ACCOUNTANT` có thể quản lý hai công ty khác nhau; cả hai đều có quyền sửa hóa đơn nháp nhưng không được sửa chéo tenant.

### Vai trò và tiền tố `ROLE_`

Theo quy ước mặc định thường dùng trong Spring Security:

- `hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` cũng kiểm tra đúng chuỗi `ROLE_ADMIN`.
- `hasAuthority("ADMIN")` chỉ khớp khi thực sự tồn tại authority `ADMIN`.
- Với tiền tố mặc định, tham số của `hasRole` là `"ADMIN"`, không viết sẵn `"ROLE_ADMIN"`.

Tiền tố role có thể được tùy chỉnh tại những điểm cấu hình phù hợp; khi vận hành phải xem cấu hình cụ thể. Role hierarchy (ví dụ quản trị viên kế thừa vai trò biên tập) cũng cần cấu hình tường minh, **không tự xuất hiện từ tên role**.

## 4. Authority: đơn vị mà Spring Security thực sự so khớp

Sau khi xác thực, Spring Security có một `Authentication` chứa principal và tập `GrantedAuthority`. Với những authority dạng chuỗi quen thuộc, `getAuthority()` có thể trả về:

~~~text
Principal: user-42
GrantedAuthorities:
  ROLE_ACCOUNTANT
  invoice:read
  invoice:update_draft
  SCOPE_invoices.read
~~~

Khi gọi `hasAuthority("invoice:read")`, framework kiểm tra xem trong tập authority có **chuỗi khớp** hay không. Nó không tự hiểu rằng `invoice:update_draft` bao hàm `invoice:read`, hoặc rằng `SCOPE_invoices.read` tương đương `invoice:read`.

**Authority là dạng biểu diễn, không bắt buộc là một “permission” nghiệp vụ.** Chuỗi `ROLE_*` thường biểu diễn role; `SCOPE_*` thường biểu diễn scope từ token; chuỗi `invoice:*` có thể là permission tùy ứng dụng. Cùng chung cơ chế `GrantedAuthority` nhưng ý nghĩa và nguồn gốc khác nhau.

Nguồn authority có thể là tài khoản trong database, LDAP, một IdP, ánh xạ role → permission do ứng dụng làm, hoặc claim của JWT. Với username/password, ứng dụng có thể tạo `SimpleGrantedAuthority`. Với Resource Server, một converter quyết định ánh xạ token claims vào authorities. **Đầu vào phải đến từ nguồn đã xác thực/được tin cậy**, không lấy một role hay authority do client tự nhập vào request rồi cho qua.

## 5. Permission: quyền hành động và quyền trên từng đối tượng

Permission thường được đặt theo cặp “tài nguyên:hành động”:

- `invoice:read` — đọc hóa đơn.
- `invoice:create` — tạo hóa đơn.
- `invoice:update_draft` — sửa hóa đơn nháp.
- `invoice:approve` — duyệt hóa đơn.
- `user:manage` — quản lý tài khoản.

Không có quy tắc Spring Security bắt buộc tên permission phải có dấu hai chấm; đây là **quy ước đặt tên của ứng dụng**. Điều quan trọng là tên phải ổn định, chi tiết phù hợp, và nhất quán giữa cơ sở dữ liệu, chính sách, endpoint, giao diện và tests.

Cần phân biệt:

1. **Permission mức hành động**: có `invoice:read` hay không?
2. **Authorization mức đối tượng**: hóa đơn `INV-01` có thuộc tenant và người sở hữu được phép không? Trạng thái hóa đơn có cho phép sửa không?

Nếu API chỉ kiểm tra `invoice:read` rồi lấy hóa đơn bằng ID tùy ý, người dùng có thể đoán ID để truy cập hóa đơn của người khác (IDOR/BOLA). Permission nghiệp vụ thường là **điều kiện cần**, không phải điều kiện đủ khi có ràng buộc trên tài nguyên.

Spring Security hỗ trợ `hasPermission(...)` qua cơ chế đánh giá permission theo đối tượng, thường cần ứng dụng tích hợp `PermissionEvaluator` phù hợp. Có thể dùng bean policy hoặc custom `AuthorizationManager` để kiểm tra tenant, ownership, trạng thái và quan hệ giữa chủ thể với tài nguyên.

## 6. Scope: hai ngữ cảnh dễ bị nhầm

### 6.1. OAuth 2.0 scope – phạm vi của access token

Một OAuth Authorization Server có thể cấp access token với claim tương tự:

~~~json
{
  "sub": "user-42",
  "scope": "invoices.read invoices.write"
}
~~~

Với Spring Security OAuth 2.0 Resource Server JWT, cấu hình mặc định thông dụng lấy scope từ claim `scope` hoặc `scp`, tạo các authority mang tiền tố `SCOPE_`:

| Scope trong token | Authority mặc định |
|---|---|
| `invoices.read` | `SCOPE_invoices.read` |
| `invoices.write` | `SCOPE_invoices.write` |

Do đó, để kiểm tra scope đọc hóa đơn khi dùng mapping mặc định, có thể gọi `hasAuthority("SCOPE_invoices.read")`. Câu lệnh `hasAuthority("invoices.read")` sẽ **không** tự coi là tương đương. Nếu hệ thống tự định nghĩa converter thì phải kiểm tra quy tắc đang dùng.

OAuth scope phản ánh **phạm vi được cấp cho token/client**, không chứng minh chủ thể là kế toán, là chủ sở hữu hóa đơn hoặc được truy cập tất cả tenant. Scope được **cấp thực tế** có thể ít hơn scope client đã yêu cầu. API phải xác minh token (chữ ký, thời hạn, issuer và các điều kiện liên quan); audience cần được kiểm tra/cấu hình theo mô hình tài nguyên của hệ thống. Không lấy ID token thay access token để phân quyền API.

### 6.2. Scope trong nghiệp vụ – giới hạn dữ liệu/ngữ cảnh

Nhiều tài liệu nghiệp vụ gọi “data scope” để nói tới:

- **Tenant/organization:** chỉ xem tài nguyên thuộc `T1`.
- **Owner:** chỉ xem tài nguyên do chính mình sở hữu.
- **Department/region:** chỉ xem đơn vị hoặc địa bàn được phân công.
- **Trạng thái/thời gian:** chỉ sửa nếu `status=DRAFT` và trong thời hạn cho phép.

Các điều kiện này là thuộc tính của chủ thể/tài nguyên/môi trường; chúng có thể thuộc ABAC (*Attribute-Based Access Control*) hoặc kiểm soát truy cập ở mức đối tượng. Chúng **không tự biến thành OAuth scope**. Nên lưu và kiểm tra riêng các trường `tenantId`, `ownerId`, `status` thay vì gộp mọi thứ vào một trường mơ hồ tên `scope`.

## 7. Cách các khái niệm liên kết trong một request

~~~text
User / Service Client
        |
        v
Xác thực danh tính hoặc access token
        |
        v
Dựng Authentication
  - principal
  - roles / permissions hiệu lực
  - OAuth scopes được ánh xạ
        |
        v
GrantedAuthority:
  ROLE_ACCOUNTANT
  invoice:read
  SCOPE_invoices.read
        |
        v
Kiểm tra tại HTTP hoặc method
  hasRole / hasAuthority / custom policy
        |
        v
Kiểm tra tài nguyên và ngữ cảnh
  tenant / owner / status / quan hệ
        |
        v
ALLOW hoặc DENY
~~~

Quan hệ điển hình:

~~~text
Role --(mapping do ứng dụng định nghĩa)--> Permission
Role / Permission --(mapping)--> GrantedAuthority
OAuth scope --(JWT converter)--> SCOPE_* GrantedAuthority
Authorities + quy tắc resource/context --> Authorization decision
~~~

**Không được đảo chiều một cách tùy ý:** thấy `SCOPE_invoices.read` không suy ra `ROLE_ACCOUNTANT`; thấy `ROLE_ACCOUNTANT` không tự suy ra `invoice:read`; thấy `invoice:read` không suy ra quyền đọc hóa đơn thuộc tenant khác.

Một chính sách API đọc hóa đơn có thể yêu cầu đồng thời:

~~~text
ALLOW =
  authenticated
  AND token có invoices.read
  AND chủ thể có invoice:read (trực tiếp hoặc nhờ role)
  AND invoice.tenantId == caller.tenantId
  AND (invoice.ownerId == caller.id OR có quyền xem toàn đơn vị)
~~~

Đây là **chính sách minh họa do ứng dụng quyết định**, không phải công thức chung mà Spring Security tự thực thi. Ứng dụng không dùng OAuth có thể bỏ điều kiện token scope; yêu cầu business chính xác mới quyết định phép kết hợp.

## 8. Tình huống đối chiếu thực tế

Cho hóa đơn `INV-01` thuộc tenant `T1`, owner `lan`. API dùng access token với scope `invoices.read`. Người có `FINANCE_ADMIN` được đọc hóa đơn của mọi owner **trong tenant mình**, nhưng vẫn phải có token scope.

| Người gọi | Role/permission nghiệp vụ | Token scope | Tenant | Quan hệ | Kết quả |
|---|---|---|---|---|---|
| Lan | `invoice:read` | `invoices.read` | T1 | Owner | **Cho phép** |
| Lan | `invoice:read` | Không có | T1 | Owner | **Từ chối:** thiếu scope |
| Lan | `invoice:read` | `invoices.read` | T2 | Khác tenant | **Từ chối:** sai tenant |
| Minh | `FINANCE_ADMIN` | `invoices.read` | T1 | Không phải owner | **Cho phép** theo policy admin |
| An | Không có quyền đọc | `invoices.read` | T1 | Owner | **Từ chối:** scope không thay permission |

Điểm quan trọng: **quyền hành động, quyền token và quyền trên tài nguyên là các chiều kiểm tra tách biệt**.

## 9. Thực hành Java 17: mô hình hóa một quyết định phân quyền

Đây là chương trình **Java thuần độc lập**, dùng để hiểu mối quan hệ giữa bốn thành phần. Vai trò `FINANCE_ADMIN` trong mã là tên business, **chưa** được ánh xạ thành authority `ROLE_FINANCE_ADMIN` của Spring Security.

Lưu dưới tên `AccessDecisionExample.java`:

~~~java
import java.util.Set;

public class AccessDecisionExample {
    record Caller(
            String id,
            Set<String> roles,
            Set<String> permissions,
            Set<String> tokenScopes,
            String tenantId) {
    }

    record Invoice(String id, String ownerId, String tenantId) {
    }

    static boolean canRead(Caller caller, Invoice invoice) {
        boolean admin = caller.roles().contains("FINANCE_ADMIN");
        boolean hasBusinessPermission =
                admin || caller.permissions().contains("invoice:read");
        boolean tokenAllowsRead =
                caller.tokenScopes().contains("invoices.read");
        boolean sameTenant =
                caller.tenantId().equals(invoice.tenantId());
        boolean allowedObject =
                admin || caller.id().equals(invoice.ownerId());

        return hasBusinessPermission
                && tokenAllowsRead
                && sameTenant
                && allowedObject;
    }

    public static void main(String[] args) {
        Invoice invoice = new Invoice("INV-01", "lan", "T1");

        Caller lan = new Caller(
                "lan", Set.of("VIEWER"), Set.of("invoice:read"),
                Set.of("invoices.read"), "T1");

        Caller missingScope = new Caller(
                "lan", Set.of("VIEWER"), Set.of("invoice:read"),
                Set.of(), "T1");

        Caller wrongTenant = new Caller(
                "lan", Set.of("VIEWER"), Set.of("invoice:read"),
                Set.of("invoices.read"), "T2");

        Caller admin = new Caller(
                "minh", Set.of("FINANCE_ADMIN"), Set.of(),
                Set.of("invoices.read"), "T1");

        System.out.println("lan: " + canRead(lan, invoice));
        System.out.println("missingScope: " + canRead(missingScope, invoice));
        System.out.println("wrongTenant: " + canRead(wrongTenant, invoice));
        System.out.println("admin: " + canRead(admin, invoice));
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac AccessDecisionExample.java
java AccessDecisionExample
~~~

Stdout chính xác:

~~~text
lan: true
missingScope: false
wrongTenant: false
admin: true
~~~

Lan có đủ quyền, scope và ràng buộc dữ liệu. `missingScope` bị từ chối dù là owner; `wrongTenant` bị từ chối dù có cùng ID và permission; admin được truy cập nhờ chính sách nêu rõ nhưng vẫn bị giới hạn tenant/scope. Trong ứng dụng thật, dữ liệu roles/permissions phải đến từ server/IAM, scopes đến từ token đã xác minh và tenant/owner phải dựa trên nguồn đáng tin.

## 10. Triển khai ý tưởng với Spring Security Servlet

### 10.1. Kiểm tra tại HTTP

Đoạn mã là **một lớp cấu hình Spring**, không phải chương trình Java độc lập. Nó phù hợp phong cách Spring Boot 3.x / Spring Security 6.x khi dự án dùng Spring Security Servlet và OAuth 2.0 Resource Server với JWT được cấu hình/kiểm chứng hợp lệ.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoices.read")
                .requestMatchers(HttpMethod.POST, "/api/invoices/**")
                    .hasAuthority("SCOPE_invoices.write")
                .requestMatchers("/api/admin/**")
                    .hasRole("FINANCE_ADMIN")
                .anyRequest().denyAll()
        );

        http.oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Giải thích:

- `hasAuthority("SCOPE_invoices.read")` yêu cầu authority tương ứng với scope đọc theo ánh xạ JWT mặc định.
- `hasRole("FINANCE_ADMIN")` yêu cầu `ROLE_FINANCE_ADMIN` nếu dùng tiền tố role mặc định.
- **Converter JWT mặc định ánh xạ scope sang `SCOPE_*`, không tự ánh xạ claim role tùy biến thành `ROLE_FINANCE_ADMIN`.** Muốn dùng role do IdP phát hành, phải thiết lập converter phù hợp và xác định claim nào đáng tin.
- `anyRequest().denyAll()` từ chối URL chưa định nghĩa rule; trong dự án thực cần khai báo public/health endpoints cần thiết có chủ đích.
- Cần có phụ thuộc và cấu hình Resource Server/JWT (issuer, khóa, validation). Đoạn mã không tự cấp access token.
- Đối với `GET /api/invoices/{id}`, việc kiểm tra scope ở HTTP **chưa đủ** để bảo đảm người gọi được xem đúng hóa đơn; logic sở hữu/tenant vẫn phải chạy ở tầng nghiệp vụ.

Nếu cần kiểm tra permission nội bộ như `invoice:read`, có thể dùng `hasAuthority("invoice:read")` **sau khi** phần authentication đã đưa đúng permission vào `GrantedAuthority`. Không thay tên chuỗi rồi mặc nhiên giả định mapping đã tồn tại.

### 10.2. Kiểm tra tại method/service

`@EnableMethodSecurity` kích hoạt hỗ trợ kiểm tra qua annotation như `@PreAuthorize` trên Spring-managed methods. Ví dụ điều kiện sau có thể được đặt trên một method nhận tham số `invoiceId`:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_invoices.read') " +
    "and @invoicePolicy.canRead(authentication, #invoiceId)"
)
~~~

Đây là **minh họa annotation**, phụ thuộc bean `invoicePolicy` do ứng dụng tự xây dựng. Chính bean đó phải kiểm tra permission nghiệp vụ và quan hệ của bản ghi với người gọi bằng dữ liệu đáng tin. Spring phải nhận diện tên tham số `invoiceId` (ví dụ qua `-parameters` hoặc khai báo tường minh), và lời gọi phải đi qua cơ chế Spring method security. Tự gọi method ngay trong cùng instance có thể bỏ qua proxy advice.

Có thể tổ chức ba lớp bảo vệ:

1. **HTTP boundary:** xác thực, token scope và các rule tuyến đường.
2. **Service/use case:** permission nghiệp vụ, tenant, owner, trạng thái.
3. **Data access:** truy vấn giới hạn bởi tenant/chủ thể khi thích hợp, tránh trả nhầm bản ghi.

Không dựa vào việc ẩn nút ở frontend: một client vẫn có thể gọi API trực tiếp.

## 11. Các mô hình phân quyền liên quan

- **RBAC:** gán vai trò rồi dựa trên vai trò để cấp/chặn thao tác. Dễ vận hành nhưng thường cần bổ sung điều kiện mức đối tượng.
- **Permission-based policy:** kiểm tra khả năng cụ thể như `invoice:approve`. Permissions có thể được tổng hợp qua roles.
- **ABAC:** xem xét thuộc tính chủ thể, hành động, tài nguyên và môi trường (ví dụ tenant, owner, trạng thái, thời gian).
- **Quan hệ đối tượng:** chủ sở hữu, người được chia sẻ, thành viên nhóm hoặc quan hệ giữa tài nguyên và chủ thể.

Những mô hình này có thể **được kết hợp**. Spring Security cung cấp điểm thực thi quyết định và các extension; không tự định nghĩa toàn bộ luật business của một hệ thống cụ thể.

## 12. Lỗi phổ biến

| Nhầm lẫn | Hệ quả và cách sửa |
|---|---|
| `hasRole("ADMIN")` và `hasAuthority("ADMIN")` được coi như nhau | Theo tiền tố mặc định, role yêu cầu `ROLE_ADMIN`. Kiểm tra tên authority thực tế. |
| JWT có `scope=invoices.read` rồi kiểm tra `hasAuthority("invoices.read")` | Mặc định authority được tạo là `SCOPE_invoices.read`. Đối chiếu converter đang sử dụng. |
| Có `ROLE_ACCOUNTANT` thì mặc định có `invoice:read` | Phải có mapping role → permission hoặc chính sách rõ ràng; framework không tự suy luận. |
| Có OAuth scope nên được xem tất cả bản ghi | Phải kiểm tra tenant, owner và policy business. |
| Nhận role/tenant từ request body/header tự khai | Dữ liệu dễ bị giả mạo; dùng nguồn tin cậy từ server hoặc token đã xác thực. |
| Chỉ dùng `isAuthenticated()` | Xác thực không tương đương được phép thực hiện hành động. |
| Chỉ kiểm tra ở UI/controller | Service hoặc API có thể được gọi qua đường khác; bảo vệ ở tầng nghiệp vụ. |
| Tưởng role tự kế thừa | Chỉ có hierarchy khi được cấu hình; cần kiểm thử quyền hiệu lực. |
| Quên bật `@EnableMethodSecurity` | Annotation method có thể không được áp dụng; còn phải lưu ý self-invocation/proxy. |
| Viết URL matchers quá rộng/sai thứ tự | Rule được xét theo thứ tự; đặt rule cụ thể trước, chọn default deny rõ ràng. |

**401 và 403:** thiếu xác thực/token không hợp lệ thường dẫn tới `401 Unauthorized`, còn đã xác thực nhưng không đủ quyền thường dẫn tới `403 Forbidden`. Phản hồi cụ thể phụ thuộc cấu hình filter chain, entry point và access-denied handler.

## 13. Checklist thiết kế cho một chức năng mới

Với chức năng “duyệt hóa đơn”, cần trả lời đầy đủ:

1. **Ai gọi?** User hay service client, xác thực bằng gì?
2. **Làm gì?** Permission chính xác là `invoice:approve` hay tên nào khác?
3. **Role nào?** Gán permission qua role nào, có ngoại lệ không?
4. **Nguồn authority nào?** Database, IAM, JWT claim; mapping được làm ở đâu?
5. **OAuth scope nào?** Access token có cần `invoices.approve` không?
6. **Tài nguyên nào?** Cùng tenant? Ai là owner? Trạng thái hóa đơn hợp lệ?
7. **Điểm chặn nào?** Request, service, repository; tránh đường vòng.
8. **Test từ chối nào?** Thiếu role, thiếu permission, thiếu scope, khác tenant, khác owner, sai trạng thái, token hết hạn.

Luôn có bài test **đúng quyền hành động nhưng sai đối tượng**. Đó là tình huống dễ làm lộ dữ liệu khi mô hình quyền chỉ dựa trên role.

## 14. Ghi nhớ và câu hỏi tự kiểm tra

- **Role** là nhóm trách nhiệm, **permission** là quyền làm thao tác, **authority** là dạng quyền mà Spring Security so khớp, **OAuth scope** là phạm vi truy cập được cấp cho token/client.
- Role, permission và OAuth scope **có thể** được biểu diễn thành authorities sau mapping; không được đồng nhất chúng.
- Với tiền tố mặc định, `hasRole("X")` thường tương đương việc đòi `ROLE_X`; `hasAuthority("X")` đòi đúng `X`.
- `SCOPE_*` là cách Spring Security Resource Server thường biểu diễn scope, không thay thế giới hạn tenant/ownership.
- Quyết định phân quyền an toàn cần xem **chủ thể + hành động + tài nguyên + ngữ cảnh**, ưu tiên không cấp quyền khi thiếu điều kiện.

**Tự kiểm tra:**

1. JWT chỉ có scope `reports.read`, không có role. `hasRole("REPORTER")` có tự pass không? **Không**, vì chưa có `ROLE_REPORTER` được ánh xạ.
2. Người dùng có `invoice:read` nhưng hóa đơn thuộc tenant khác. Có được đọc không? **Không** nếu chính sách tenant yêu cầu cùng tổ chức.
3. `hasAuthority("SCOPE_invoices.read")` đã kiểm tra quyền trên từng hóa đơn chưa? **Chưa**, nó chỉ kiểm tra một authority.
4. Role `ADMIN` có đương nhiên được truy cập mọi tenant không? **Không**, đặc quyền xuyên tenant phải được chính sách xác định rõ, được kiểm thử và giám sát.

### Tham khảo chính thức

- Spring Security – Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security 6.5 – OAuth 2.0 Resource Server JWT (Servlet): https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html