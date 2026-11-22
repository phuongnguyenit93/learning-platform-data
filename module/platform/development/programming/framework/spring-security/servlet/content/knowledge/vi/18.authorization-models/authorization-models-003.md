# RoleHierarchy và quyền được kế thừa giữa các vai trò trong Spring Security Servlet

## 1. Vì sao cần RoleHierarchy?

Giả sử hệ thống quản trị có ba vai trò:

- **USER**: được xem hồ sơ của chính mình.
- **MANAGER**: được làm các việc của USER và thêm chức năng quản lý.
- **ADMIN**: được làm các việc của MANAGER và thêm chức năng quản trị.

Nếu không có mô hình kế thừa, bạn có thể phải gán cho mỗi quản trị viên cả `ROLE_ADMIN`, `ROLE_MANAGER` và `ROLE_USER`; hoặc mỗi lần tạo endpoint lại viết các tổ hợp như `hasAnyRole("USER", "MANAGER", "ADMIN")`. Cả hai cách đều dễ lặp logic, khó bảo trì và có thể bỏ sót quy tắc khi vai trò mới xuất hiện.

**`RoleHierarchy`** trong Spring Security giải quyết phần *suy ra quyền được kế thừa* từ quan hệ giữa các role/authority:

~~~text
ROLE_ADMIN
    |
    v
ROLE_MANAGER
    |
    v
ROLE_USER
~~~

Với quan hệ này:

- Người được **gán trực tiếp** `ROLE_ADMIN` có thể được **xem là có** `ROLE_MANAGER` và `ROLE_USER` khi một cơ chế kiểm tra quyền **đã được tích hợp RoleHierarchy**.
- Người chỉ có `ROLE_MANAGER` có thể được xem là có `ROLE_USER`, nhưng **không** tự thành ADMIN.
- Người chỉ có `ROLE_USER` **không** có các vai trò cao hơn.
- Quan hệ mang tính **bắc cầu**: ADMIN → MANAGER và MANAGER → USER thì ADMIN → USER.
- Quyền **được gán** và quyền **suy ra** là hai khái niệm khác nhau.

Điểm cuối là thiết yếu: **khai báo một bean RoleHierarchy không có nghĩa mọi `AuthorizationManager`, mọi expression handler hoặc mọi thư viện kiểm quyền trong ứng dụng đều tự dùng nó**. Từng điểm tích hợp phải được kiểm tra theo API/phiên bản. Ví dụ chạy được ở phần 9 **nối hierarchy tường minh** vào các manager của `authorizeHttpRequests` để tránh phụ thuộc vào giả định về auto-configuration.

Bài này dành cho **Spring Boot 3.x / Spring Security 6.x, Java 17+, Servlet stack**; trọng tâm là quản lý quan hệ vai trò và áp dụng chúng đúng chỗ. Nó không thay bài toán permission theo đối tượng dữ liệu, owner/tenant, hay xác minh credentials.

## 2. Từ GrantedAuthority đến role hierarchy

### 2.1. Spring Security đánh giá authority string

Sau khi người dùng đăng nhập, `Authentication` thường chứa danh sách các `GrantedAuthority`. Một ví dụ:

~~~text
Authentication
  principal   = "alice"
  authenticated = true
  authorities = ["ROLE_MANAGER"]
~~~

Trong Spring Security, role về bản chất thường được thể hiện bằng **authority string** với prefix `ROLE_` theo quy ước mặc định:

| Cách kiểm tra | Authority mặc định cần có | Ý nghĩa |
| --- | --- | --- |
| `hasRole("USER")` | `ROLE_USER` | Thường dùng để kiểm tra role USER |
| `hasRole("MANAGER")` | `ROLE_MANAGER` | Kiểm tra role MANAGER |
| `hasAuthority("ROLE_USER")` | `ROLE_USER` | So khớp authority đầy đủ |
| `hasAuthority("report:read")` | `report:read` | Permission/scope theo chuỗi cụ thể |
| `authenticated()` | Không phải một role | Kiểm tra trạng thái authentication |

**Đừng gọi `hasRole("ROLE_ADMIN")` khi dùng quy tắc prefix mặc định.** Thường dùng `hasRole("ADMIN")`; nếu muốn kiểm tra chuỗi đã có prefix, dùng `hasAuthority("ROLE_ADMIN")`. Một hệ thống có thể tùy chỉnh prefix, nhưng khi đã đổi phải thống nhất toàn bộ cấu hình hierarchy, role managers, expression handlers và mapping từ identity provider.

### 2.2. Quyền được gán trực tiếp và quyền hiệu lực

Giả sử database chỉ gán `ROLE_ADMIN` cho bob. Phần quyền gốc sau authentication có thể là:

~~~text
Direct authorities:    [ROLE_ADMIN]
Reachable authorities: [ROLE_ADMIN, ROLE_MANAGER, ROLE_USER]
~~~

`Reachable authorities` là **kết quả suy ra từ hierarchy**, không nhất thiết là danh sách thực sự nằm bên trong `Authentication.getAuthorities()`. Nếu bạn đọc đối tượng Authentication thô, có thể vẫn chỉ thấy `ROLE_ADMIN`. Điều đó là bình thường.

Các thành phần như `AuthorityAuthorizationManager` hoặc method security expression handler có thể dùng `RoleHierarchy#getReachableGrantedAuthorities(...)` khi được cấu hình. **Nếu một bộ kiểm quyền không được tích hợp hierarchy, nó có thể không nhìn thấy role kế thừa**.

Vì vậy, đừng kiểm tra:

~~~java
authentication.getAuthorities().stream()
    .anyMatch(a -> a.getAuthority().equals("ROLE_USER"));
~~~

rồi kết luận ADMIN chắc chắn không được quyền USER. Đoạn trên chỉ kiểm tra **direct authorities**. Nó phù hợp nếu bạn thật sự muốn kiểm tra gán trực tiếp, nhưng **không** tương đương kiểm tra có xét role hierarchy. Với kiểm tra quyền hiệu lực, nên dùng manager/expression handler đã tích hợp hierarchy hoặc gọi hierarchy một cách rõ ràng.

### 2.3. Role hierarchy không tự tạo tài khoản

`RoleHierarchy` không thay `AuthenticationManager`, `UserDetailsService`, `PasswordEncoder` hoặc JWT signature verification. Nó cũng không sửa bảng role trong database, không lưu quyền mới vào token, không tạo session, không “nâng cấp” user theo thời gian.

Quy trình thường là:

~~~text
Credentials/token được xác minh
            |
            v
Authentication đã tin cậy, chứa direct authorities
            |
            v
AuthorizationManager / expression handler
            |
            +-- RoleHierarchy tính reachable authorities
            |
            v
Quyết định cho phép/từ chối theo vai trò/permission được yêu cầu
~~~

Nếu token đầu vào chứa role do client tự khai mà không được xác minh đáng tin cậy, hierarchy chỉ **khuếch đại lỗi cấp quyền**. Nền tảng luôn là authentication/claim mapping an toàn.

## 3. Mô hình kế thừa có hướng và tính bắc cầu

### 3.1. Cú pháp quan hệ

Một cách khai báo trong `RoleHierarchyImpl` là chuỗi các quan hệ:

~~~text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
~~~

Dấu `>` được hiểu như **role bên trái bao gồm quyền của role bên phải**. Không đảo ngược chiều:

~~~text
ROLE_MANAGER > ROLE_ADMIN
~~~

dòng này sẽ có nghĩa MANAGER thừa hưởng ADMIN — rất nguy hiểm nếu bạn định nghĩa MANAGER là quyền thấp hơn.

Hình dung dưới dạng tập:

| Role trực tiếp | Các role hiệu lực theo ví dụ |
| --- | --- |
| `ROLE_ADMIN` | `ROLE_ADMIN`, `ROLE_MANAGER`, `ROLE_USER` |
| `ROLE_MANAGER` | `ROLE_MANAGER`, `ROLE_USER` |
| `ROLE_USER` | `ROLE_USER` |
| Không có role thuộc cây trên | Không nhận thêm role từ cây |

Tính bắc cầu cho phép mở rộng thành nhiều tầng, nhưng **đừng tạo hierarchy dài không cần thiết**. Một sơ đồ role có quá nhiều cạnh sẽ khó xem xét các quyền phát sinh và dễ làm sai nguyên tắc quyền tối thiểu.

### 3.2. RoleHierarchy cũng xử lý nhiều nhánh

Ví dụ:

~~~text
ROLE_ADMIN > ROLE_OPERATIONS
ROLE_ADMIN > ROLE_FINANCE
ROLE_OPERATIONS > ROLE_USER
ROLE_FINANCE > ROLE_USER
~~~

ADMIN suy ra OPERATIONS, FINANCE và USER; OPERATIONS/FINANCE đều có USER nhưng không suy ra nhau. Đây là mô hình đồ thị có hướng, không nhất thiết là một đường thẳng.

Hãy đặt tên các role theo **trách nhiệm thực tế**, không theo giả định rằng mọi role luôn xếp thành một bậc thang duy nhất. Đặc biệt không nên tạo “SUPER_ROLE” bao trùm mọi nghiệp vụ chỉ để dễ kiểm thử nếu policy phân tách trách nhiệm đòi các quyền không được gộp.

### 3.3. Tránh vòng lặp và đồ thị khó audit

Một quan hệ vòng có thể khiến hai vai trò trở nên tương đương về quyền kế thừa:

~~~text
ROLE_A > ROLE_B
ROLE_B > ROLE_A
~~~

Đừng cố tình hoặc vô tình tạo cycle khi mong A cao hơn B. Tùy implementation/phiên bản, role hierarchy có thể xử lý hoặc cảnh báo theo cách khác nhau; điều quan trọng là **không dựa vào hành vi ngầm khi có chu trình**.

Tốt nhất duy trì cấu trúc **đồ thị có hướng không chu trình (DAG)** khi roles đại diện cấp bậc và trách nhiệm khác nhau. Test tính bao hàm mong muốn và kiểm tra không xuất hiện quyền ngoài ý định.

### 3.4. Không nhất thiết role cao hơn được mọi permission

Nếu policy riêng của endpoint là `hasAuthority("billing:refund")`, ADMIN được gán `ROLE_ADMIN` không nhất thiết có chuỗi `billing:refund`. RoleHierarchy chỉ mở rộng những authority có **quan hệ được khai báo** và những điểm kiểm tra đã sử dụng hierarchy.

Ví dụ:

~~~text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
~~~

**Không** tự suy ra:

~~~text
ROLE_ADMIN > billing:refund
ROLE_ADMIN > deploy:production
~~~

trừ khi chính bạn đã khai báo quan hệ/ánh xạ hoặc cấp permissions theo cách khác. Đây là lợi thế: phân tách quyền đặc biệt như xuất tiền hoặc triển khai production khỏi role chung.

## 4. API nền tảng của Spring Security

Các kiểu quan trọng:

- `org.springframework.security.access.hierarchicalroles.RoleHierarchy`: abstraction cho việc mở rộng authorities.
- `org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl`: implementation thường dùng.
- `org.springframework.security.core.GrantedAuthority`: một quyền được gán/suy ra.
- `org.springframework.security.core.authority.SimpleGrantedAuthority`: implementation đơn giản giữ chuỗi authority.
- `org.springframework.security.authorization.AuthorityAuthorizationManager`: manager kiểm role/authority; có thể được gắn `RoleHierarchy`.
- `org.springframework.security.web.access.intercept.RequestAuthorizationContext`: ngữ cảnh kiểm quyền HTTP từ `authorizeHttpRequests`.
- `org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler`: một cách cấu hình expressions cho method security.

### 4.1. Tạo RoleHierarchyImpl

Ví dụ chạy trên nhánh Spring Security 6 phổ biến:

~~~java
@Bean
RoleHierarchy roleHierarchy() {
    RoleHierarchyImpl hierarchy = new RoleHierarchyImpl();
    hierarchy.setHierarchy("""
        ROLE_ADMIN > ROLE_MANAGER
        ROLE_MANAGER > ROLE_USER
        """);
    return hierarchy;
}
~~~

Đoạn này cần đặt trong một lớp `@Configuration` với imports tương ứng. `setHierarchy(String)` là API quen thuộc của Spring Security 6; trên một số bản mới nó được đánh dấu **deprecated** để hướng sang factory/builder. Với production, kiểm tra phiên bản đã cố định và có thể chuyển sang cách khởi tạo được khuyến nghị trong phiên bản ấy; không đưa API của bản mới vào dự án cũ mà không kiểm chứng.

Java text block `"""..."""` yêu cầu Java 15+, nên project dùng **Java 17** là phù hợp.

### 4.2. getReachableGrantedAuthorities

Có thể quan sát kết quả bằng một đoạn minh họa:

~~~java
RoleHierarchy hierarchy = /* bean RoleHierarchy đã cấu hình */;
var direct = List.of(new SimpleGrantedAuthority("ROLE_ADMIN"));
var reachable = hierarchy.getReachableGrantedAuthorities(direct);
~~~

Đây là **snippet**, không phải class độc lập. `reachable` có các authority có thể đi tới theo các cạnh hierarchy, bao gồm các authority trực tiếp. Không dùng thứ tự phần tử của collection làm yêu cầu nghiệp vụ; khi muốn in kết quả ổn định, hãy `map(GrantedAuthority::getAuthority).sorted().toList()`.

### 4.3. RoleHierarchy là một quy tắc trong authorization, không phải user repository

Khi user `admin` đăng nhập, `UserDetailsService` có thể chỉ cung cấp `ROLE_ADMIN`. RoleHierarchy đóng vai trò ánh xạ quyền tại bước kiểm tra — không cần “nhân bản” cả ba role vào database chỉ để mô phỏng inheritance.

Tuy nhiên nếu một phần hệ thống không dùng RoleHierarchy (ví dụ custom service lấy `authentication.getAuthorities()` rồi so chuỗi trực tiếp), kết quả giữa các tầng có thể khác nhau. **Cần thống nhất nguồn chính sách và test cho mọi điểm được bảo vệ**.

## 5. Tích hợp đúng với authorizeHttpRequests trên Servlet

### 5.1. Không nên giả định chỉ cần khai báo bean là đủ

Ví dụ này có thể trông đúng nhưng không nên dùng làm bằng chứng hierarchy đã được áp dụng ở mọi phiên bản/cấu hình:

~~~java
@Bean
RoleHierarchy roleHierarchy() {
    RoleHierarchyImpl hierarchy = new RoleHierarchyImpl();
    hierarchy.setHierarchy("ROLE_ADMIN > ROLE_USER");
    return hierarchy;
}

// Ở nơi khác:
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/user/**").hasRole("USER")
);
~~~

Nhiều phiên bản/điểm mở rộng có chính sách auto-discovery khác nhau. Nếu manager được tạo mà **không nhận RoleHierarchy**, một user chỉ có ROLE_ADMIN có thể bị từ chối ở `hasRole("USER")`. Test hành vi thực thay vì suy luận từ sự tồn tại của bean.

### 5.2. Cấu hình tường minh qua AuthorityAuthorizationManager

Có thể tạo manager riêng cho từng role và gắn hierarchy:

~~~java
AuthorityAuthorizationManager<RequestAuthorizationContext> userRule =
    AuthorityAuthorizationManager.hasRole("USER");
userRule.setRoleHierarchy(roleHierarchy);

AuthorityAuthorizationManager<RequestAuthorizationContext> adminRule =
    AuthorityAuthorizationManager.hasRole("ADMIN");
adminRule.setRoleHierarchy(roleHierarchy);

http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").access(adminRule)
    .requestMatchers("/user/**").access(userRule)
    .anyRequest().denyAll()
);
~~~

Đây là **snippet trong cấu hình** có sẵn bean `roleHierarchy`; ví dụ hoàn chỉnh được cung cấp ở phần 9. `AuthorityAuthorizationManager` sẽ kiểm tra quyền theo RoleHierarchy đã gắn cho chính instance manager đó. Sử dụng `.access(...)` bảo đảm DSL dùng đúng manager.

Ưu điểm:

- Không phụ thuộc vào giả định “Spring Security tự động nhìn thấy bean RoleHierarchy ở mọi chỗ”.
- Có thể test inheritance rõ ràng cho từng endpoint.
- Nhìn vào cấu hình là biết manager nào có sử dụng hierarchy.
- Dễ phân biệt rule role hierarchy với các policy đòi authority độc lập.

### 5.3. Rule order vẫn quan trọng

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").access(adminRule)
    .requestMatchers("/user/**").access(userRule)
    .anyRequest().denyAll()
);
~~~

Đây là hai URL khác nhau nên không overlap. Với URL lồng nhau thì đặt matcher cụ thể trước rộng:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").access(adminRule)
    .requestMatchers("/api/**").access(userRule)
    .anyRequest().denyAll()
);
~~~

`RequestMatcherDelegatingAuthorizationManager` chọn **rule đầu tiên có matcher khớp**, rồi áp dụng manager của rule đó. Không có chuyện nếu `adminRule` từ chối thì Spring Security đi thử `userRule` ở phía sau.

Hierarchy chỉ ảnh hưởng **quyền hiệu lực** của manager, không thay thuật toán chọn RequestMatcher hoặc thứ tự các `SecurityFilterChain`.

### 5.4. AuthenticationEntryPoint và AccessDeniedHandler

Nếu request thiếu credentials mà vào `/user/**`, ứng dụng có thể trả **401** (HTTP Basic), hoặc redirect tới trang login (formLogin). Nếu đã authenticated nhưng role không đủ, thường là **403**. Đó là hành vi của `ExceptionTranslationFilter`, `AuthenticationEntryPoint` và `AccessDeniedHandler` trong chain.

**RoleHierarchy không quyết định HTTP status.** Nó quyết định authorities được xét khi manager đánh giá; cơ chế HTTP response phụ thuộc loại authentication và exception handling.

### 5.5. hasAuthority có cần inheritance không?

`AuthorityAuthorizationManager.hasAuthority("report:read")` có thể được tích hợp cùng RoleHierarchy nếu hệ thống thiết kế quan hệ đến authority đó, ví dụ `ROLE_MANAGER > report:read`. Nhưng việc dùng role hierarchy để kế thừa **permission string** phải được cân nhắc: chuỗi report:read không phải role theo quy ước đặt tên, và một số thành phần khác có thể không diễn giải như bạn kỳ vọng.

**Tách role hierarchy và permission mapping là lựa chọn dễ audit hơn trong nhiều hệ thống lớn.** Role mô tả chức năng/trách nhiệm, permission mô tả hành động; policy service có thể ánh xạ role→permissions theo nghiệp vụ. Nếu có quan hệ role→permission trong hierarchy, ghi rõ contract và test đủ mọi entry point.

## 6. Tích hợp với method security: cần kiểm tra riêng

HTTP authorization bảo vệ URL. Với logic nghiệp vụ nhạy cảm, Spring Security còn có method security:

~~~java
@PreAuthorize("hasRole('USER')")
public Profile loadProfile() {
    // ...
}
~~~

Snippet này **không** độc lập biên dịch; cần method security được bật và method nằm trong Spring bean với AOP proxy thích hợp.

Để hierarchy có hiệu lực trong expression-based method security, có thể cấu hình handler một cách tường minh (trong một cấu hình bật `@EnableMethodSecurity`):

~~~java
@Bean
static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
        RoleHierarchy roleHierarchy) {

    DefaultMethodSecurityExpressionHandler handler =
        new DefaultMethodSecurityExpressionHandler();

    handler.setRoleHierarchy(roleHierarchy);
    return handler;
}
~~~

Cần imports:

~~~java
import org.springframework.security.access.expression.method.DefaultMethodSecurityExpressionHandler;
import org.springframework.security.access.expression.method.MethodSecurityExpressionHandler;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.context.annotation.Bean;
~~~

Tùy **phiên bản Spring Security**, một bean RoleHierarchy có thể được hỗ trợ bởi phương án cấu hình tự động khác. Snippet trên diễn tả ý định **nối hierarchy vào expression handler** để dễ kiểm soát. Nếu dự án đã có MethodSecurityExpressionHandler tùy chỉnh, không tạo thêm bean cạnh tranh mà hãy cấu hình đúng handler đang dùng. Test method-level authorization trong môi trường thực.

**Lưu ý quan trọng về AOP:** method security có thể không chạy khi một method trong cùng object gọi thẳng method protected của chính nó (**self-invocation**) vì lời gọi không đi qua proxy. Hierarchy không khắc phục được vấn đề proxy; xem xét thiết kế service boundaries và test method qua Spring proxy.

### 6.1. HTTP rule và method rule có thể cùng áp dụng

Ví dụ:

~~~text
HTTP: GET /api/reports/42
  |
  +-- HTTP manager yêu cầu ROLE_USER -> được phép nhờ ROLE_ADMIN > ROLE_USER
  |
  +-- Service method yêu cầu report:read và đúng tenant
        |
        +-- user thiếu permission/không thuộc tenant -> từ chối
~~~

Role hierarchy giúp mở rộng role có thứ bậc; **không loại bỏ** chính sách permission chi tiết, ownership hoặc tenant isolation.

## 7. Những trường hợp KHÔNG nên kế thừa role

### 7.1. Phân tách trách nhiệm (Separation of Duties)

Một tổ chức có hai vai trò:

- `ROLE_PAYMENT_CREATOR`: tạo yêu cầu chi tiền.
- `ROLE_PAYMENT_APPROVER`: phê duyệt yêu cầu chi tiền.

Không nên định nghĩa `ROLE_PAYMENT_APPROVER > ROLE_PAYMENT_CREATOR` chỉ vì tên “approver” nghe cấp cao hơn. Chính sách có thể **cố ý yêu cầu người tạo và người duyệt là hai chủ thể khác nhau**. Kế thừa sai sẽ phá nguyên tắc bốn mắt.

Tương tự, `ROLE_SUPPORT`, `ROLE_SECURITY_AUDITOR` và `ROLE_DB_OPERATOR` có thể thuộc các nhóm trách nhiệm **không bao hàm nhau**. Đừng coi hierarchy là một thứ tự tuyệt đối của mọi role.

### 7.2. Quyền phụ thuộc đối tượng/tenant

Trong hệ thống nhiều tenant, một user có `ROLE_ADMIN` của tenant A **không** mặc nhiên là ADMIN ở tenant B. Một hierarchy chung:

~~~text
ROLE_ADMIN > ROLE_USER
~~~

chỉ mô tả sự bao hàm **theo tên role**, không chứa ngữ cảnh tenant. Nếu không mã hóa scope trong Authentication/policy hoặc kiểm tra tenancy ở service, một role ADMIN chung có thể gây overauthorization.

Giải pháp thường là ràng buộc role theo tenant và policy thực tế, ví dụ một đối tượng `TenantMembership(userId, tenantId, role)` ở service hoặc custom AuthorizationManager đọc nguồn đáng tin. Không dùng `?tenantId=A` do client tự khai như bằng chứng membership.

### 7.3. Role không tương đương permission

Đơn vị nghiệp vụ có thể muốn:

- USER được xem profile của chính mình.
- MANAGER được xem profile nhân viên thuộc nhóm.
- ADMIN xem báo cáo hệ thống.

Không có nghĩa ADMIN được xem **mọi** profile cá nhân. RoleHierarchy tuyến tính `ADMIN > MANAGER > USER` chỉ phù hợp khi **quyền tổng hợp thật sự** có tính bao hàm. Đừng dựng hierarchy trước rồi ép policy riêng tư theo nó.

### 7.4. Authority theo scope/token

Trong OAuth2 resource server, authorities có thể đến từ scopes như `SCOPE_read` hoặc claims roles đã qua xác minh. Đừng giả mọi scope tự kế thừa theo ROLE_ mà không có mapping tin cậy. JWT cần xác minh chữ ký/issuer/audience/expiration; role mapping phải đến từ IdP đáng tin, và các claim có thể stale cho tới khi token hết hạn/được thu hồi.

### 7.5. Permission đặc biệt có vòng đời riêng

Một số quyền như `deploy:production`, `refund:high_value` hoặc `export:pii` thường cần MFA/step-up, approval, thời gian hiệu lực hoặc kiểm toán. Không nhét các permission này dưới ADMIN chỉ để đơn giản hóa hierarchy. Khi quyền có điều kiện động, dùng policy service hoặc AuthorizationManager riêng.

## 8. Lưu ý kỹ thuật: authorities không tự được “chuyển đổi” trong token/session

### 8.1. Authentication.getAuthorities() có thể không đổi

Giả sử Spring Security xác thực user admin và trả:

~~~text
authentication.getAuthorities() = [ROLE_ADMIN]
~~~

Sau khi gắn RoleHierarchy cho một manager, `hasRole("USER")` có thể cho phép user này nhưng gọi `authentication.getAuthorities()` vẫn chỉ trả `ROLE_ADMIN`. Không so sánh danh sách direct với danh sách reachable rồi kết luận Spring Security “làm mất quyền”.

Trong giao diện quản trị, nếu cần hiển thị roles được **gán thực tế**, hiển thị direct roles; nếu cần giải thích **quyền hiệu lực**, hiển thị reachable roles có ghi chú rõ rằng đây là quyền suy ra. Phần demo `GET /roles` chỉ để học; production không nên công khai danh sách authorities cho mọi client.

### 8.2. Session và token có thể chứa thông tin cũ

Nếu bạn thay hierarchy từ:

~~~text
ROLE_ADMIN > ROLE_MANAGER
ROLE_MANAGER > ROLE_USER
~~~

thành:

~~~text
ROLE_ADMIN > ROLE_MANAGER
~~~

manager sử dụng bean mới có thể thay đổi reachable authorities ngay sau deploy; nhưng:
- Một số server instance có thể vẫn dùng cấu hình cũ trong lúc rolling deployment.
- Session/JWT có thể giữ **direct authorities cũ** hoặc claims stale.
- Cached authorization decisions có thể chưa được refresh.
- Custom code không sử dụng hierarchy có thể cư xử khác.

Cần có quy trình rollout/version, invalidation/re-authentication khi đổi quyền nhạy cảm và kiểm thử nhiều instance. **RoleHierarchy không tự thu hồi JWT hoặc session**.

### 8.3. Tính toán reachable authorities và performance

Role hierarchy thường có thể chuẩn bị/cached các quan hệ để việc tra cứu permission hiệu quả; cấu hình càng nhiều role/cạnh thì càng cần đo thời gian khởi tạo và tính phức tạp. Đừng dùng nó như một database policy engine hay xây đồ thị quyền ngẫu nhiên từ request user chưa xác thực.

Với nghiệp vụ động theo đối tượng, đặt kiểm tra ở service/policy được tối ưu và có kiểm soát dữ liệu hơn là xây lại hierarchy trong mỗi HTTP request.

## 9. Ví dụ hoàn chỉnh: Spring Boot 3.3.13, Java 17, HTTP Basic và MockMvc

Project dưới đây xây **một `RoleHierarchyImpl`** và gắn **tường minh** vào ba `AuthorityAuthorizationManager`. Chương trình có bốn user demo:

| Username | Direct role | Reachable roles | Endpoint có thể vào |
| --- | --- | --- | --- |
| `user` | `ROLE_USER` | USER | `/user` |
| `manager` | `ROLE_MANAGER` | MANAGER, USER | `/manager`, `/user` |
| `admin` | `ROLE_ADMIN` | ADMIN, MANAGER, USER | `/admin`, `/manager`, `/user` |
| `auditor` | `ROLE_AUDITOR` | AUDITOR | Không vào ba endpoint role trên |

Tất cả dùng password học tập `demo-pass`; đây **không phải** cấu hình production. Demo dùng `httpBasic` để test 401/403 mà không cần form login/CSRF token cho các GET endpoint. Khi đưa HTTP Basic lên Internet phải bắt buộc dùng HTTPS, và nên áp dụng authentication/threat model phù hợp.

### 9.1. Cấu trúc thư mục

~~~text
role-hierarchy-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/roles/
    │       ├── RoleHierarchyApplication.java
    │       ├── SecurityConfig.java
    │       └── DemoController.java
    └── test/
        └── java/com/example/roles/
            └── RoleHierarchyTests.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>role-hierarchy-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/com/example/roles/RoleHierarchyApplication.java`**

~~~java
package com.example.roles;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoleHierarchyApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoleHierarchyApplication.class, args);
    }
}
~~~

### 9.2. SecurityConfig.java: hierarchy + manager rõ ràng

**`src/main/java/com/example/roles/SecurityConfig.java`**

~~~java
package com.example.roles;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.access.hierarchicalroles.RoleHierarchyImpl;
import org.springframework.security.authorization.AuthorityAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
public class SecurityConfig {

    @Bean
    RoleHierarchy roleHierarchy() {
        RoleHierarchyImpl hierarchy = new RoleHierarchyImpl();
        hierarchy.setHierarchy("""
            ROLE_ADMIN > ROLE_MANAGER
            ROLE_MANAGER > ROLE_USER
            """);
        return hierarchy;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RoleHierarchy roleHierarchy) throws Exception {

        AuthorityAuthorizationManager<RequestAuthorizationContext> adminRule =
            AuthorityAuthorizationManager.hasRole("ADMIN");
        adminRule.setRoleHierarchy(roleHierarchy);

        AuthorityAuthorizationManager<RequestAuthorizationContext> managerRule =
            AuthorityAuthorizationManager.hasRole("MANAGER");
        managerRule.setRoleHierarchy(roleHierarchy);

        AuthorityAuthorizationManager<RequestAuthorizationContext> userRule =
            AuthorityAuthorizationManager.hasRole("USER");
        userRule.setRoleHierarchy(roleHierarchy);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").access(adminRule)
                .requestMatchers("/manager").access(managerRule)
                .requestMatchers("/user").access(userRule)
                .requestMatchers("/roles").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        String encoded = encoder.encode("demo-pass");

        return new InMemoryUserDetailsManager(
            User.withUsername("user")
                .password(encoded)
                .roles("USER")
                .build(),
            User.withUsername("manager")
                .password(encoded)
                .roles("MANAGER")
                .build(),
            User.withUsername("admin")
                .password(encoded)
                .roles("ADMIN")
                .build(),
            User.withUsername("auditor")
                .password(encoded)
                .roles("AUDITOR")
                .build()
        );
    }
}
~~~

**Phân tích thiết kế:**

1. `RoleHierarchyImpl` chỉ định hai cạnh. Từ đó ADMIN suy ra MANAGER và USER theo tính bắc cầu.
2. Mỗi `AuthorityAuthorizationManager<RequestAuthorizationContext>` được tạo bằng `hasRole(...)`, sau đó **gắn chính xác cùng một bean RoleHierarchy**.
3. `.access(adminRule/managerRule/userRule)` nói rõ rule HTTP nào dùng manager có hierarchy. Ta không dựa vào việc một bean RoleHierarchy được auto-wire vào matcher DSL.
4. `.anyRequest().denyAll()` từ chối URL không liệt kê; ví dụ không cần controller cho mọi đường dẫn.
5. Tài khoản `auditor` không có đường kế thừa tới USER nên không được vào `/user`.
6. `HttpBasic` không tạo vai trò từ URL/query. Authentication được xác minh bằng password BCrypt với `UserDetailsService` demo.
7. `setHierarchy(...)` có thể bị deprecated ở phiên bản mới hơn; nó vẫn được dùng trong ví dụ Spring Security 6 có API này. Khi nâng cấp hãy đổi sang factory/builder đã được phiên bản mục tiêu xác nhận, không thay behavior theo cảm tính.

**Không thêm một “global hasRole bypass” cho ADMIN.** Dù là ADMIN, user vẫn phải qua manager được chọn; hierarchy cho phép ADMIN đi qua manager USER/MANAGER vì **quan hệ đã khai báo**, không phải vì Spring Security coi từ “ADMIN” là đặc biệt.

### 9.3. Controller: xem direct và reachable roles

**`src/main/java/com/example/roles/DemoController.java`**

~~~java
package com.example.roles;

import java.util.List;
import java.util.Map;

import org.springframework.security.access.hierarchicalroles.RoleHierarchy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final RoleHierarchy roleHierarchy;

    public DemoController(RoleHierarchy roleHierarchy) {
        this.roleHierarchy = roleHierarchy;
    }

    @GetMapping("/public")
    public Map<String, String> publicPage() {
        return Map.of("status", "public-ok");
    }

    @GetMapping("/user")
    public Map<String, String> userPage() {
        return Map.of("status", "user-ok");
    }

    @GetMapping("/manager")
    public Map<String, String> managerPage() {
        return Map.of("status", "manager-ok");
    }

    @GetMapping("/admin")
    public Map<String, String> adminPage() {
        return Map.of("status", "admin-ok");
    }

    public record RolesView(
        String username,
        List<String> direct,
        List<String> reachable
    ) {
    }

    @GetMapping("/roles")
    public RolesView roles(Authentication authentication) {
        List<String> direct = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        List<String> reachable = roleHierarchy
            .getReachableGrantedAuthorities(authentication.getAuthorities())
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return new RolesView(authentication.getName(), direct, reachable);
    }
}
~~~

Endpoint `GET /roles` cố ý tiết lộ danh sách authorities **cho mục đích demo local**. Với production, không cung cấp tùy tiện danh sách quyền nội bộ trong response, hoặc phải kiểm tra authorization phù hợp.

**Điểm quan sát quan trọng:** user `admin` trả `direct = ["ROLE_ADMIN"]` nhưng `reachable` chứa ADMIN, MANAGER và USER. RoleHierarchy giúp kiểm quyền hiệu lực **mà không nhất thiết thay đổi object Authentication gốc**.

### 9.4. Kiểm thử phân quyền và kế thừa với MockMvc

**`src/test/java/com/example/roles/RoleHierarchyTests.java`**

~~~java
package com.example.roles;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RoleHierarchyTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("public-ok"));
    }

    @Test
    void anonymousRequestNeedsCredentials() throws Exception {
        mvc.perform(get("/user"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void userDoesNotInheritHigherRoles() throws Exception {
        mvc.perform(get("/user")
                .with(httpBasic("user", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/manager")
                .with(httpBasic("user", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("user", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void managerInheritsUserButNotAdmin() throws Exception {
        mvc.perform(get("/user")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/manager")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/admin")
                .with(httpBasic("manager", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminInheritsManagerAndUserTransitively() throws Exception {
        mvc.perform(get("/user")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/manager")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void unrelatedRoleDoesNotInherit() throws Exception {
        mvc.perform(get("/user")
                .with(httpBasic("auditor", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void reachableRolesAreDifferentFromDirectRoles() throws Exception {
        mvc.perform(get("/roles")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("admin"))
            .andExpect(jsonPath("$.direct[0]").value("ROLE_ADMIN"))
            .andExpect(jsonPath("$.direct.length()").value(1))
            .andExpect(jsonPath("$.reachable",
                hasItems("ROLE_ADMIN", "ROLE_MANAGER", "ROLE_USER")));
    }

    @Test
    void fallbackDeniesEvenAdmin() throws Exception {
        mvc.perform(get("/unlisted")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
~~~

Những test này kiểm tra **hành vi qua Spring Security filter chain thật của MockMvc**, không chỉ gọi riêng `getReachableGrantedAuthorities`. Chúng chứng minh:

- Anonymous chưa xác thực → **401** khi dùng HTTP Basic.
- USER chỉ vào endpoint user, không vào manager/admin.
- MANAGER kế thừa USER nhưng không kế thừa ADMIN.
- ADMIN kế thừa MANAGER và USER; đây là trường hợp có tính bắc cầu.
- AUDITOR không tự có USER.
- Direct roles khác reachable roles.
- Fallback `denyAll` vẫn chặn cả ADMIN nếu URL không được phép.

Nếu một developer sau này bỏ `setRoleHierarchy(...)` trên manager USER, test ADMIN vào `/user` sẽ phát hiện lỗi. Đây là lý do nên test **cả inherited grants và inherited denials**, không chỉ kiểm tra endpoint admin.

### 9.5. Chạy project và quan sát

Máy cần **JDK 17+, Maven** và có thể tải dependencies ở lần build đầu:

~~~bash
mvn test
mvn spring-boot:run
~~~

**Kết quả mong đợi** là các test vượt qua và Maven báo `BUILD SUCCESS` nếu các file được tạo đúng. Đây là **mô tả cách chạy và kết quả dự kiến**, **chưa thực thi Maven trong tài liệu này**.

Khi server chạy:

~~~bash
curl -i http://localhost:8080/public
# Dự kiến HTTP 200, {"status":"public-ok"}

curl -i http://localhost:8080/user
# Dự kiến HTTP 401 với Basic challenge

curl -i -u user:demo-pass http://localhost:8080/user
# Dự kiến HTTP 200

curl -i -u user:demo-pass http://localhost:8080/manager
# Dự kiến HTTP 403

curl -i -u manager:demo-pass http://localhost:8080/user
# Dự kiến HTTP 200 nhờ kế thừa ROLE_USER

curl -i -u admin:demo-pass http://localhost:8080/manager
# Dự kiến HTTP 200 nhờ kế thừa ROLE_MANAGER

curl -i -u admin:demo-pass http://localhost:8080/roles
# Dự kiến HTTP 200; direct=[ROLE_ADMIN],
# reachable=[ROLE_ADMIN,ROLE_MANAGER,ROLE_USER] theo thứ tự sorted

curl -i -u auditor:demo-pass http://localhost:8080/user
# Dự kiến HTTP 403

curl -i -u admin:demo-pass http://localhost:8080/unlisted
# Dự kiến HTTP 403
~~~

Lưu ý: HTTP Basic gửi credentials trong Authorization header (Base64 **không phải mã hóa**). Chỉ dùng HTTP trên localhost cho học tập; production phải dùng TLS/HTTPS và policy lưu trữ credentials phù hợp.

## 10. Kiểm thử mở rộng: thay đổi hierarchy và kiểm tra hồi quy

### 10.1. Chỉ có quyền trực tiếp

Nếu **bỏ hai cạnh hierarchy** nhưng giữ user admin có direct `ROLE_ADMIN`, các request tới `/manager` và `/user` sẽ **không còn chắc chắn được phép** bởi những manager yêu cầu MANAGER/USER. Nếu vẫn trả 200, có thể có rule khác rộng hơn, RoleHierarchy khác hoặc custom mapping.

### 10.2. Chỉ kế thừa một tầng

Nếu khai báo:

~~~text
ROLE_ADMIN > ROLE_MANAGER
~~~

ADMIN thừa hưởng MANAGER, nhưng **không** tự thừa hưởng USER. Manager vẫn không tự có USER nếu không có cạnh tương ứng. Đây là cách xác minh test có thực sự kiểm tính bắc cầu hay không.

### 10.3. Thêm role không liên quan

~~~text
ROLE_AUDITOR > ROLE_AUDIT_READER
~~~

Nếu AUDITOR không có đường đi tới USER, nó không được vào endpoint yêu cầu USER. Test negative này giúp ngăn lỗi “mọi role được xem như role chung” do một custom manager sai.

### 10.4. Thay đổi hierarchy theo tenant

Giả sử tenant A muốn MANAGER > USER nhưng tenant B không cho phép. Một bean `RoleHierarchyImpl` toàn cục **không đại diện đầy đủ cho điều kiện động theo tenant**. Nếu bạn cố gắng mutate hierarchy toàn cục theo request của từng tenant, có thể tạo **race condition và lộ quyền chéo**. Hãy dùng policy/AuthorizationManager có ngữ cảnh tenant đáng tin, hoặc mô hình role scoped theo tenant, thay vì thay bean singleton trên mỗi request.

### 10.5. Permission có điều kiện

Với hành động refund giá trị cao, rule “ADMIN có ROLE_USER” không chứng minh người đó đã hoàn thành MFA hoặc được phê duyệt. Dùng authorization policy kiểm các điều kiện động:

~~~text
Authenticated user
    |
    +-- Có permission refund:create?
    +-- Đúng tenant?
    +-- MFA/step-up còn hiệu lực?
    +-- Không phải người duyệt chính yêu cầu do mình tạo?
    |
    +--> tất cả đều đạt: cho phép
~~~

Hierarchy có thể là **một** tín hiệu trong quyết định, không phải toàn bộ quyết định.

## 11. Những lỗi phổ biến khi áp dụng RoleHierarchy

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đảo chiều `ROLE_USER > ROLE_ADMIN` | USER thừa hưởng ADMIN, có nguy cơ leo thang quyền | Vẽ sơ đồ trước khi khai báo, test negative |
| Coi hierarchy là “role nào cũng bao gồm role bên dưới” không cần cấu hình | Quyền được suy ra không đúng | Chỉ suy ra qua cạnh rõ ràng và tính bắc cầu |
| Khai báo RoleHierarchy bean nhưng không nối vào manager thực dùng | `hasRole` có thể không thấy role kế thừa | Dùng `setRoleHierarchy`/handler được tích hợp, test HTTP & method |
| Kiểm tra trực tiếp `Authentication.getAuthorities()` rồi đòi thấy ROLE_USER của admin | Hiểu sai direct và reachable | Phân biệt assigned/effective; dùng hierarchy ở check cần thiết |
| Dùng `hasRole("ROLE_ADMIN")` với prefix mặc định | Dễ cấu hình sai/exception | Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |
| Tự tin ADMIN có `report:read` mà không khai báo | Truy cập thất bại hoặc lộ do bypass | Thiết kế permission mapping rõ ràng |
| Tạo cycle giữa các role | Quyền bị bao hàm ngoài ý định | Tránh cycles, kiểm thử đồ thị |
| Mutate singleton hierarchy theo request/tenant | Race condition, leak chéo tenant | Policy scoped theo context đáng tin |
| Kế thừa cả role tạo thanh toán và role duyệt | Phá separation of duties | Giữ vai trò độc lập, policy có kiểm soát |
| Coi role hierarchy là ownership check | User A có thể đọc dữ liệu user B | Kiểm tra owner/tenant tại service/method |
| Đổi policy mà không thu hồi session/token cũ | Quyền stale trong phiên/claims | Có versioning/revocation/re-authentication |
| Thêm `anyRequest().permitAll()` để chữa 403 | Mở endpoint ngoài ý muốn | Kiểm tra manager, authorities và fallbacks |
| Chỉ test admin có vào admin được | Không kiểm tra inheritance và leak quyền | Test USER, MANAGER, AUDITOR, anonymous, fallback |
| Quên sự khác nhau giữa HTTP và method security | Policy không nhất quán giữa endpoint và service | Test cả hai tầng, cấu hình đúng handlers |
| Thử tự bật bean mới bằng tên API không có ở bản phụ thuộc | Build fail khi nâng/hạ phiên bản | Khóa phiên bản, kiểm tra API thực và migration notes |

## 12. Quy trình đưa RoleHierarchy vào một dự án thật

### Bước 1: Phân tích quyền nghiệp vụ

Lập danh sách vai trò trực tiếp và những hành động từng vai trò được phép. Với mỗi cạnh `A > B`, đặt câu hỏi:

> “Mọi thành viên của A, trong mọi ngữ cảnh áp dụng, có chắc chắn được làm tất cả những việc mà B được làm không?”

Nếu câu trả lời là “không” hoặc “chỉ trong một tenant/đơn hàng”, không nên tạo cạnh toàn cục. Thiết kế permission/ownership policy thay thế.

### Bước 2: Vẽ và review đồ thị

Vẽ DAG, đảm bảo không đảo chiều, không chu trình, không overgrant, và review cùng security/business owners. Một role mới có thể mở rộng reachable authorities cho hàng nghìn account; xem sự thay đổi này như **thay đổi chính sách bảo mật**.

### Bước 3: Tạo RoleHierarchy bean theo version

Dùng API có trong Spring Security hiện tại; nếu sử dụng `RoleHierarchyImpl.setHierarchy(...)`, lưu ý deprecation ở phiên bản mới. Không dùng chung một string build động từ input người dùng. Role hierarchy thường là cấu hình được kiểm soát, không phải dữ liệu từ request.

### Bước 4: Tích hợp tất cả điểm kiểm quyền cần thiết

Kiểm tra:

- `authorizeHttpRequests` + `AuthorityAuthorizationManager` thực sự được gắn hierarchy?
- Method security expression handler có dùng hierarchy?
- Custom policy có tự so direct authorities thay vì reachable?
- Gateway/resource server có cùng role mapping và trust boundary?
- Các endpoint nhạy cảm có thêm kiểm tra permission, owner/tenant, MFA?

### Bước 5: Test ma trận cấp quyền

| User/role | /public | /user | /manager | /admin |
| --- | --- | --- | --- | --- |
| Anonymous | 200 | 401 (Basic) | 401 | 401 |
| USER | 200 | 200 | 403 | 403 |
| MANAGER | 200 | 200 | 200 | 403 |
| ADMIN | 200 | 200 | 200 | 200 |
| AUDITOR | 200 | 403 | 403 | 403 |

Mã HTTP trong bảng giả định cấu hình **HTTP Basic** ở ví dụ; với form login, anonymous có thể nhận redirect 302. Test cả negative cases, không chỉ happy path.

### Bước 6: Rollout/observability có kiểm soát

Theo dõi tỷ lệ 403/401, đường đi policy và các thay đổi bất thường, nhưng không log raw password, session cookie, Bearer token hoặc dữ liệu cá nhân không cần thiết. Khi đổi hierarchy, cân nhắc session/JWT stale, deploy nhiều phiên bản và backward compatibility.

### Bước 7: Tài liệu hóa sự kế thừa

Mỗi quan hệ nên có người chịu trách nhiệm, lý do nghiệp vụ và test thể hiện kỳ vọng. Đừng cho phép mọi module tự định nghĩa hierarchy khác nhau mà không có thiết kế chung; điều đó làm cùng role nhưng mỗi endpoint kiểm quyền khác nhau.

## 13. Câu hỏi tự kiểm tra

**1. `ROLE_ADMIN > ROLE_MANAGER` có nghĩa gì?**

ADMIN được xem là bao hàm quyền của MANAGER tại những thành phần authorization có dùng RoleHierarchy tương ứng. Không có nghĩa MANAGER được ADMIN.

**2. Nếu ADMIN > MANAGER và MANAGER > USER, ADMIN có USER không?**

Có, do tính bắc cầu. Đây là một trường hợp trọng tâm cần test.

**3. User chỉ có ROLE_USER thì có ROLE_MANAGER không?**

Không. Quan hệ có chiều; role thấp không tự suy ra role cao.

**4. Có bean RoleHierarchy rồi thì mọi `hasRole` đều tự kế thừa không?**

Không nên giả định vậy. Phải xác nhận manager/expression handler đang dùng RoleHierarchy theo phiên bản và cấu hình; ví dụ HTTP nối bằng `AuthorityAuthorizationManager#setRoleHierarchy`.

**5. Vì sao `Authentication.getAuthorities()` của ADMIN có thể chỉ có ROLE_ADMIN?**

Vì đó là danh sách authority **được gán trực tiếp**. Reachable roles được tính bởi hierarchy khi cần, không nhất thiết mutate Authentication.

**6. `hasRole("ADMIN")` mặc định tương đương kiểm tra gì?**

Thường kiểm `ROLE_ADMIN`. Với prefix mặc định, không truyền `ROLE_ADMIN` trực tiếp cho `hasRole`.

**7. ADMIN có mọi `hasAuthority("...")` không?**

Không. Một permission riêng như `refund:approve` chỉ có hiệu lực nếu được cấp/ánh xạ theo policy tương ứng. Role ADMIN không tự có mọi chuỗi permission.

**8. RoleHierarchy có giải quyết vấn đề tenant A admin xem dữ liệu tenant B không?**

Không. Cần policy owner/tenant lấy từ dữ liệu đáng tin. Một role toàn cục không tự mã hóa phạm vi tenant.

**9. Có nên cho payment approver kế thừa payment creator không?**

Chỉ nếu business thực sự cho phép và không phá separation of duties; nhiều hệ thống cần hai role tách biệt.

**10. Sau khi đổi RoleHierarchy, JWT/session cũ có tự bị thu hồi không?**

Không. Cần cơ chế expiration, revocation, policy version hoặc re-authentication phù hợp.

**11. Tại sao fallback `anyRequest().denyAll()` vẫn chặn cả ADMIN?**

Vì hierarchy không bỏ qua rule deny; request không được liệt kê vẫn bị từ chối theo chính sách.

**12. Tại sao cần test cả method security nếu HTTP đã có RoleHierarchy?**

Vì chúng có thể sử dụng các expression handler/authorization managers khác nhau; method-level policy còn bảo vệ logic nghiệp vụ được gọi từ nhiều entry point.

**13. Khi nào không nên dùng một hierarchy tuyến tính ADMIN > MANAGER > USER?**

Khi các vai trò không thật sự bao hàm nhau, có separation of duties, permissions theo đối tượng, hoặc các ràng buộc động/tenant; dùng đồ thị có nhánh hoặc policy độc lập.

**Ghi nhớ:** **RoleHierarchy mô tả những quan hệ quyền kế thừa có hướng giữa các role/authority. Kết quả reachable có thể lớn hơn direct authorities, nhưng chỉ phát huy tác dụng khi được tích hợp đúng vào authorization managers/expressions. Kế thừa phải được thiết kế theo nghiệp vụ, tránh overgrant, và không thay thế ownership, tenant, MFA hay khả năng thu hồi phiên/token.**