# AuthorizationManager và mô hình quyết định truy cập trong Spring Security

> **Chủ đề:** Spring Security – fundamentals → **Phân quyền**. Tài liệu tập trung vào cơ chế xác định một người dùng có được thực hiện một hành động trên tài nguyên cụ thể hay không; cách Spring Security đưa quyết định tại HTTP request, method và object level; cách xây quy tắc an toàn, kiểm thử được và mở rộng khi cần.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **authentication** (xác thực danh tính) và **authorization** (quyết định quyền truy cập).
2. Mô tả luồng `Authentication` → `AuthorizationManager` → grant/deny/abstain → thực thi hoặc từ chối.
3. Hiểu giao diện `AuthorizationManager<T>`, `AuthorizationResult`, `AuthorizationDecision`, `Supplier<Authentication>` và đối tượng `T` cần kiểm tra.
4. Dùng các policy có sẵn (`permitAll`, `denyAll`, `authenticated`, `hasRole`, `hasAuthority`) và kết hợp quy tắc.
5. Tích hợp `AuthorizationManager` ở HTTP layer bằng `authorizeHttpRequests`/`access(...)`; phân biệt với method security (`@PreAuthorize`, `@PostAuthorize`).
6. Thiết kế rule theo **least privilege**, **default deny**, owner/tenant boundaries và kiểm thử các trường hợp 200/401/403.
7. Nhận diện khác biệt API Spring Security 6.x, 7.x và reactive authorization.

## 2. Phân quyền trả lời câu hỏi gì?

**Authentication** trả lời: *Người đang gửi request là ai?* Ví dụ: người dùng `alice` đã đăng nhập và mang các authority `ROLE_USER`, `REPORT_READ`.

**Authorization** trả lời: *Người đó có quyền thực hiện hành động này đối với tài nguyên này, trong ngữ cảnh hiện tại không?*

Hãy mô hình hóa một quyết định:

~~~text
principal = ai đang gọi?         alice
action    = muốn làm gì?          READ
resource  = đối tượng nào?        report/2026-Q4
context   = điều kiện gì?         tenant, owner, trạng thái, thời gian...
policy    = quy tắc tổ chức?      REPORT_READ và đúng tenant
decision  = cho phép hay từ chối? GRANTED hoặc DENIED
~~~

Trong ứng dụng, một người có thể **đăng nhập thành công nhưng vẫn bị từ chối** khi đọc tài liệu của đồng nghiệp. Đây là điều bình thường: "đã đăng nhập" không đồng nghĩa "có mọi quyền".

Ví dụ về các cấp độ kiểm soát:

| Cấp độ | Ví dụ policy | Chỗ kiểm tra thường dùng |
| --- | --- | --- |
| Endpoint | `GET /reports/**` cần `REPORT_READ` | `SecurityFilterChain`/`AuthorizationFilter` |
| HTTP method | `POST /orders/**` cần `ORDER_WRITE` | `authorizeHttpRequests` với `HttpMethod` |
| Service method | Chỉ kế toán được xuất báo cáo | `@PreAuthorize` hoặc custom method `AuthorizationManager` |
| Bản ghi/tài nguyên | Chỉ chủ sở hữu hoặc admin đọc được hồ sơ | Kiểm tra owner/tenant từ nguồn dữ liệu tin cậy |
| Thuộc tính/kết quả | Chỉ xem trường dữ liệu được phép | Policy ở business layer, projection/filter hoặc post-authorization phù hợp |

Có ba kiểu mô hình phổ biến:

- **RBAC (Role-Based Access Control):** quyền gắn với vai trò, ví dụ ADMIN, EDITOR. Dễ quản lý nhưng vai trò nhiều quá có thể khó duy trì.
- **ABAC (Attribute-Based Access Control):** xét thuộc tính người dùng, tài nguyên và môi trường (ví dụ department, owner, classification, tenant, state).
- **ReBAC (Relationship-Based Access Control):** xét quan hệ giữa chủ thể và tài nguyên (chủ sở hữu, thành viên nhóm, người được chia sẻ). Một ứng dụng thường kết hợp cả ba, không nhất thiết chọn đúng một mô hình.

`AuthorizationManager` là cơ chế kỹ thuật nhận thông tin cần kiểm tra và biểu đạt **kết quả**. Nó không tự biết chính sách kinh doanh của bạn nếu chưa cấu hình hoặc cung cấp implementation.

## 3. Luồng quyết định truy cập trong Servlet Security

Với ứng dụng Spring MVC / Servlet dùng DSL `authorizeHttpRequests`, luồng khái quát:

~~~text
HTTP request
    |
    v
SecurityFilterChain (xác thực, security context, ...)
    |
    v
AuthorizationFilter
    | tạo Supplier<Authentication> (lấy identity khi thực sự cần)
    | chọn rule dựa trên request matcher
    v
AuthorizationManager<RequestAuthorizationContext>
    | policy + authentication + request context
    +------ GRANTED ------> Controller/Service
    |
    +------ DENIED -------> AccessDeniedException
                              |
                              v
                        ExceptionTranslationFilter
                        -> entry point / 401 khi chưa xác thực
                        -> access denied handler / 403 khi đã xác thực
~~~

Đây là sơ đồ minh họa, không biểu diễn mọi filter hoặc mọi cách xử lý lỗi. Phản hồi HTTP cuối cùng còn phụ thuộc cách cấu hình authentication entry point, access denied handler và authentication mechanism.

Những thành phần cần phân biệt:

- `SecurityFilterChain`: tập các security filters áp dụng cho request.
- `AuthorizationFilter`: gọi `AuthorizationManager` khi `authorizeHttpRequests` được dùng trên Servlet stack.
- `Authentication`: principal, authorities và trạng thái xác thực. `GrantedAuthority` thường có giá trị chuỗi, ví dụ `ROLE_ADMIN`.
- `SecurityContextHolder`: nơi lấy security context trên Servlet stack, mặc định dùng `ThreadLocal` theo request processing.
- `AuthorizationManager`: quyết định liệu một hành động đối với secure object có được phép hay không.
- `ExceptionTranslationFilter`: chuyển các ngoại lệ bảo mật thành entry point hoặc access-denied response theo ngữ cảnh.

Các bước xác thực và phân quyền liên quan nhưng khác API: **`AuthenticationManager` xác thực credentials; `AuthorizationManager` quyết định quyền truy cập.**

### 401 khác 403 thế nào?

- **401 Unauthorized**: thường xuất hiện khi chưa có thông tin xác thực hợp lệ và endpoint yêu cầu người dùng đăng nhập. Tên HTTP hơi dễ gây nhầm: ý nghĩa thực hành là *cần authentication*.
- **403 Forbidden**: thường là identity đã được xác thực nhưng không đủ quyền cho thao tác. Cũng có thể xuất hiện trong các cấu hình khác, ví dụ CSRF bị từ chối.
- **200 OK**: request được cho qua và endpoint xử lý thành công; không chứng minh mọi tầng dữ liệu đã được bảo vệ đúng.

Đừng kiểm thử policy chỉ bằng một đường dẫn và một tài khoản: cùng endpoint cần thử anonymous, user có quyền, user thiếu quyền, tài khoản khác tenant và tình huống tài nguyên không tồn tại.

## 4. Hợp đồng AuthorizationManager<T>

Giao diện `AuthorizationManager<T>` nhận hai đầu vào quan trọng:

1. `Supplier<Authentication> authentication`: cho phép tra cứu danh tính **trễ**. Rule `permitAll` hoặc `denyAll` có thể không cần lấy authentication.
2. `T object`: đối tượng đang cần bảo vệ. Ví dụ:
   - `RequestAuthorizationContext` khi xét Servlet HTTP request;
   - `MethodInvocation` khi xét trước lời gọi method;
   - ngữ cảnh kết quả method đối với cơ chế post-authorization.

Giao diện hiện đại có thể được hiểu ở mức khái niệm như sau:

~~~java
AuthorizationResult authorize(
    Supplier<Authentication> authentication, T object);

default void verify(
    Supplier<Authentication> authentication, T object);
~~~

**Lưu ý về phiên bản và chữ ký:** Các dòng trên trình bày để học API, không phải file Java độc lập. Ở Spring Security **6.4/6.5**, `authorize(...)` đã có, còn `check(...)` là API cũ đã deprecated. Ở Spring Security **7.x**, API chính là `authorize(...)` (với chú thích/nullability trên type có thể khác giữa các phiên bản). Code gọi trực tiếp `check(...)` hoặc tự `@Override` chữ ký cũ cần được rà soát khi nâng cấp. Các ví dụ chạy ở phần sau dùng **lambda qua `.access(...)`**, tránh phụ thuộc vào một signature override cũ.

**`AuthorizationResult`** có `isGranted()`. Implementation thông dụng là `AuthorizationDecision`, có thể tạo bằng:

~~~java
AuthorizationDecision allow = new AuthorizationDecision(true);
AuthorizationDecision deny  = new AuthorizationDecision(false);
~~~

Đoạn minh họa cần import `org.springframework.security.authorization.AuthorizationDecision`. `AuthorizationDecision` biểu đạt kết quả cho phép/từ chối. Một custom manager cũng có thể trả `null` để **abstain** (không đưa ra quyết định), tùy contract của manager và bộ phận gọi. **Abstain không tương đương GRANTED** và không được dùng để ngầm mở quyền. Khi triển khai rule, luôn xác định rõ thành phần cuối sẽ xử lý tình huống không có quyết định; ở HTTP level, cấu hình `anyRequest().denyAll()` là một bước phòng vệ dễ hiểu.

`verify(...)` gọi cơ chế quyết định và ném `AccessDeniedException` khi kết quả từ chối. Ở những luồng do framework quản lý, Spring Security gọi và diễn giải quyết định cho bạn; không cần tự `try/catch` rồi trả 200 khi exception bị nuốt.

### Vì sao dùng Supplier thay vì Authentication trực tiếp?

Giả sử các endpoint static/public rất phổ biến. Khi matcher đã xác định `permitAll`, Spring Security không cần tải `Authentication` từ session chỉ để ra quyết định cho phép. Việc trì hoãn `authentication.get()` đến khi policy cần giúp giảm công việc thừa và hỗ trợ việc tách policy khỏi cơ chế xác thực.

Đừng gọi `authentication.get()` nhiều lần trong custom logic khi không cần, và đừng giả định kết quả luôn là người dùng đã đăng nhập: thiết kế rule phải xử lý identity vắng mặt, anonymous token, authority không tồn tại và ngoại lệ từ nguồn dữ liệu.

## 5. Ba trạng thái trong mô hình quyết định

| Trạng thái | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **GRANTED** | Policy xác nhận được phép | Người dùng có `REPORT_READ` đọc báo cáo |
| **DENIED** | Policy xác nhận không được phép | Người dùng thiếu `REPORT_READ` |
| **ABSTAIN** | Manager không đưa quyết định | Rule chuyên biệt không có đủ dữ kiện hoặc không áp dụng |

Ví dụ triển khai ngắn minh họa logic chuyên biệt, **không phải endpoint hoàn chỉnh**:

~~~java
AuthorizationManager<RequestAuthorizationContext> onlyReports =
    (authentication, context) -> {
        String path = context.getRequest().getRequestURI();

        if (!path.startsWith("/api/reports/")) {
            return null; // ABSTAIN: manager này không xử lý path khác
        }

        Authentication auth = authentication.get();
        boolean allowed = auth != null
            && auth.getAuthorities().stream()
                .anyMatch(a -> "REPORT_READ".equals(a.getAuthority()));

        return new AuthorizationDecision(allowed);
    };
~~~

Cần import `AuthorizationManager`, `AuthorizationDecision`, `Authentication` và `RequestAuthorizationContext`. Ví dụ này chỉ mô tả semantics của manager. Không dùng `startsWith` làm cơ chế quyết định route trong production nếu chưa xét boundary và path-normalization; hãy dùng `requestMatchers`/`RequestMatcher` chuẩn của Spring Security. Nếu manager trả `null` mà caller coi là "không bị từ chối", sẽ có nguy cơ mở quyền. Với rule HTTP thực tế, thường **đặt matcher đúng phạm vi** và trả quyết định rõ ràng cho nhánh match; dùng `denyAll` cho phần không match.

Đừng nhầm 3 trạng thái trên với mô hình voting cũ: các `AccessDecisionVoter` cũ cũng từng có GRANT/DENY/ABSTAIN, nhưng cách kết hợp tùy `AccessDecisionManager` (affirmative, unanimous...). Không được tự mặc định cùng luật kết hợp khi chuyển sang `AuthorizationManager`.

## 6. Các AuthorizationManager có sẵn

Spring Security cung cấp những policy thường dùng và cơ chế ủy quyền:

| Thành phần | Vai trò |
| --- | --- |
| `AuthorityAuthorizationManager<T>` | Kiểm tra người gọi có authority/role yêu cầu |
| `AuthenticatedAuthorizationManager<T>` | Kiểm tra trạng thái authentication; có thể phân biệt authenticated, fully authenticated, remember-me/anonymous tùy rule |
| `RequestMatcherDelegatingAuthorizationManager` | Chọn manager phù hợp dựa trên request matcher của Servlet |
| `AuthorizationManagers` | Factory tĩnh hỗ trợ phối hợp nhiều managers như `allOf`, `anyOf` |
| `AuthorizationManagerBeforeMethodInterceptor` | Áp chính sách trước khi gọi method |
| `AuthorizationManagerAfterMethodInterceptor` | Áp chính sách sau invocation, dựa trên kết quả |
| Custom `AuthorizationManager<T>` | Rule nghiệp vụ như tenant, owner, trạng thái tài liệu hoặc external policy service |

Những tên trên nói về **kiến trúc**, không có nghĩa mọi class nên được tự tạo thủ công. Với rule cơ bản, DSL của Spring Security đã dựng manager thích hợp:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/reports/**").hasAuthority("REPORT_READ")
    .anyRequest().denyAll()
);
~~~

Đây là đoạn cấu hình minh họa nằm **bên trong một bean `SecurityFilterChain`** có biến `http`. Các rule được xét theo thứ tự đã khai báo: matcher tổng quát không nên đặt trước matcher đặc biệt, nếu không có thể làm rule đặc biệt không bao giờ được áp dụng.

### hasRole và hasAuthority không giống nhau

- `hasAuthority("REPORT_READ")` so sánh với authority có tên **chính xác** `REPORT_READ`.
- `hasRole("ADMIN")` theo cấu hình prefix mặc định tìm authority `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` cũng kiểm tra đúng chuỗi `ROLE_ADMIN`, nhưng người đọc cấu hình cần hiểu ý nghĩa role prefix.
- Role hierarchy, tùy phiên bản/cấu hình, có thể cho phép role cao hàm ý role thấp. Không tự giả định `ROLE_ADMIN` luôn có mọi authority khi chưa khai báo.

Ở OAuth2 Resource Server, các scope thường được ánh xạ thành authority dạng `SCOPE_read` hoặc `SCOPE_reports.read` tùy converter; `hasRole("read")` không tự hiểu "OAuth scope read". Hãy xác định cách JWT claims được chuyển thành authorities rồi viết rule tương ứng.

### Phối hợp AND/OR

`AuthorizationManagers.allOf(...)` biểu đạt yêu cầu đồng thời nhiều điều kiện; `AuthorizationManagers.anyOf(...)` biểu đạt lựa chọn cho phép theo một trong các điều kiện. Ví dụ logic nghiệp vụ:

~~~text
Xem báo cáo nhạy cảm:
  authenticated
  AND có REPORT_READ
  AND cùng tenant

Sửa tài liệu:
  (là owner AND trạng thái DRAFT)
  OR là quản trị viên có DOCUMENT_OVERRIDE
~~~

Đối với các thành phần có thể `abstain`, kết quả tổng hợp còn phụ thuộc implementation và phiên bản; không suy diễn từ toán tử AND/OR đơn giản mà bỏ qua case null. Với chính sách quan trọng, viết test truth table bao phủ GRANT, DENY, ABSTAIN và exception.

**Spring Security 7.x:** Có thêm `AuthorizationManagerFactory<T>`/`DefaultAuthorizationManagerFactory<T>` giúp tùy biến việc tạo manager, prefix role và role hierarchy. Đây là tính năng version-specific; **không đưa thẳng API này vào code của Spring Security 6.5**.

## 7. Request authorization: chọn route và kiểm tra quyền

DSL phổ biến trên Servlet stack:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/catalog").permitAll()
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("ORDER_READ")
        .requestMatchers(HttpMethod.POST, "/api/orders/**")
            .hasAuthority("ORDER_WRITE")
        .anyRequest().denyAll()
    );
    return http.build();
}
~~~

Đoạn cấu hình này cần import `HttpSecurity`, `HttpMethod`, `SecurityFilterChain`, `Bean` và đặt trong class cấu hình Spring; chưa có phần xác thực. Điểm cần nắm:

1. `requestMatchers(...)` chọn request nào được policy xét; có thể xét path, HTTP method, dispatcher type hoặc matcher tùy chỉnh.
2. `securityMatcher(...)` quyết định **toàn bộ một `SecurityFilterChain`** áp dụng cho request nào; nó khác `requestMatchers(...)` là rule *bên trong* chain.
3. Nếu có nhiều `SecurityFilterChain`, thứ tự chain và vùng `securityMatcher` phải được kiểm tra; request không được chain nào bảo vệ có thể thoát khỏi policy mong muốn.
4. Rule GET/POST phải được đặt theo method rõ ràng; cùng một path không đồng nghĩa cùng quyền.
5. `anyRequest().denyAll()` làm default deny, giảm nguy cơ endpoint mới được mở ngoài ý muốn.
6. `permitAll` nên dùng cho static/public content thay vì loại request khỏi security filter chain bằng `ignoring`, vì vẫn giữ được các cơ chế bảo vệ khác như security headers.

### Quy tắc cho đối tượng thực tế

Giả sử route `GET /api/orders/{id}`. Chỉ kiểm tra `hasAuthority("ORDER_READ")` có thể **chưa đủ**, vì một người dùng có authority này chưa chắc được đọc mọi đơn hàng thuộc tenant khác. Cần thêm resource-level authorization:

~~~text
canRead(orderId, user):
  order = repository.findById(orderId)
  nếu order không tồn tại -> xử lý 404 theo policy
  nếu user không có ORDER_READ -> DENY
  nếu order.tenantId != user.tenantId -> DENY
  nếu order.private && owner != user && !manager -> DENY
  còn lại -> GRANT
~~~

Đây là pseudocode nghiệp vụ, không phải Java chạy được. Tenant và owner phải được lấy từ nguồn tin cậy, không dựa duy nhất vào `X-Tenant` do client tự gửi hoặc một biến URL mà client tự khai. Quyết định 403 hay 404 đối với tài nguyên của người khác cần nhất quán với chính sách hạn chế lộ sự tồn tại của tài nguyên.

## 8. Ví dụ ứng dụng hoàn chỉnh (Java 17, Spring Boot 3.5.x)

Mục tiêu: một ứng dụng Spring MVC + Security nhỏ, có bốn tình huống:

- Public endpoint ai cũng gọi được.
- Báo cáo cần authority `REPORT_READ`.
- Tài liệu minh họa được đọc nếu tên owner trên route bằng tên người gọi hoặc người gọi là admin.
- Các request khác bị từ chối.

**Môi trường:** dùng Spring Initializr tạo Maven project, **Java 17+**, **Spring Boot 3.5.x**, package `com.example.authz`. Chọn dependency **Spring Web** (`spring-boot-starter-web`) và **Spring Security** (`spring-boot-starter-security`). Bài này chủ động dùng stack **Servlet/MVC** cho ví dụ chạy; phần reactive được phân biệt rõ ở mục 12. Với Spring Security 7.x, các ý tưởng vẫn áp dụng nhưng hãy đối chiếu guide/migration của phiên bản triển khai.

Các file nằm tại `src/main/java/com/example/authz/`.

### File 1 — AuthorizationDemoApplication.java

~~~java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
~~~

### File 2 — SecurityConfig.java

~~~java
package com.example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationManager<RequestAuthorizationContext> ownerOrAdmin
    ) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.GET, "/api/documents/{owner}")
                    .access(ownerOrAdmin)
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    AuthorizationManager<RequestAuthorizationContext> ownerOrAdmin() {
        return (authentication, context) -> {
            Authentication auth = authentication.get();

            boolean loggedIn = auth != null
                && auth.isAuthenticated()
                && !(auth instanceof AnonymousAuthenticationToken);

            String owner = context.getVariables().get("owner");

            boolean isOwner = loggedIn
                && owner != null
                && owner.equals(auth.getName());

            boolean isAdmin = loggedIn
                && auth.getAuthorities().stream()
                    .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

            return new AuthorizationDecision(isOwner || isAdmin);
        };
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("learn123"))
            .authorities("DOCUMENT_READ")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin123"))
            .authorities("ROLE_ADMIN", "REPORT_READ")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }
}
~~~

**Chú ý từng quyết định:**

- `ownerOrAdmin` là một bean có kiểu `AuthorizationManager<RequestAuthorizationContext>`. Lambda nhận authentication supplier và request context, trả về `AuthorizationDecision`. Đây là **custom AuthorizationManager thực sự**, được lắp vào DSL bằng `.access(ownerOrAdmin)`.
- `isAuthenticated()` một mình chưa đủ để xem mọi `Authentication` là tài khoản thật: anonymous token có thể mang trạng thái authenticated. Do đó ví dụ loại `AnonymousAuthenticationToken`.
- `context.getVariables().get("owner")` đọc path variable đã được matcher trích xuất. Đây là **demo cú pháp**, không phải policy ownership production: client kiểm soát path; với dữ liệu thật phải kiểm tra chủ sở hữu từ bản ghi trong database hoặc một nguồn tin cậy.
- User `reader` có `DOCUMENT_READ`, còn `admin` có `ROLE_ADMIN` và `REPORT_READ`. Chính sách owner demo không yêu cầu `DOCUMENT_READ` cho admin; trong production cần xác định ma trận quyền rõ.
- Dùng `BCryptPasswordEncoder` cho mật khẩu học tập trong memory; không hardcode user/password trong mã nguồn production.
- Không vô hiệu hóa CSRF toàn cục: demo chỉ có GET. Với POST/PUT/DELETE cần thiết kế CSRF phù hợp session/cookie hoặc token-based API và kiểm tra trên từng trường hợp.

### File 3 — ReportService.java

~~~java
package com.example.authz;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("hasAuthority('REPORT_READ')")
    public String quarterlyReport() {
        return "quarterly-report";
    }
}
~~~

`@EnableMethodSecurity` trong `SecurityConfig` kích hoạt method security. `@PreAuthorize` ở `ReportService` kiểm tra thêm tại business/service layer. Khi một bean khác gọi `ReportService.quarterlyReport()` qua Spring proxy, quyết định được kiểm tra **trước** khi method thực thi. Nó hỗ trợ bảo vệ đường gọi khác ngoài controller HTTP.

### File 4 — DemoController.java

~~~java
package com.example.authz;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    private final ReportService reportService;

    public DemoController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/public")
    public String publicInfo() {
        return "public";
    }

    @GetMapping("/reports")
    public String report() {
        return reportService.quarterlyReport();
    }

    @GetMapping("/documents/{owner}")
    public String document(@PathVariable String owner) {
        return "document-for-" + owner;
    }
}
~~~

Để chạy, vào thư mục project và dùng Maven Wrapper được Spring Initializr tạo:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Với cổng mặc định 8080 và không có cấu hình security bổ sung, thử từ terminal khác:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/reports
curl -i -u reader:learn123 http://localhost:8080/api/reports
curl -i -u admin:admin123 http://localhost:8080/api/reports
curl -i -u reader:learn123 http://localhost:8080/api/documents/reader
curl -i -u reader:learn123 http://localhost:8080/api/documents/alice
curl -i -u admin:admin123 http://localhost:8080/api/documents/alice
~~~

**Kết quả kỳ vọng theo code demo** (không phải log đã chạy trong môi trường hiện tại):

| Request | HTTP kỳ vọng | Body khi thành công | Lý do |
| --- | --- | --- | --- |
| Anonymous → `/api/public` | 200 | `public` | `permitAll` |
| Anonymous → `/api/reports` | 401 | — | Cần đăng nhập |
| Reader → `/api/reports` | 403 | — | Thiếu `REPORT_READ` |
| Admin → `/api/reports` | 200 | `quarterly-report` | Có `REPORT_READ` ở HTTP và service |
| Reader → `/api/documents/reader` | 200 | `document-for-reader` | Trùng owner trên route |
| Reader → `/api/documents/alice` | 403 | — | Không phải owner/admin |
| Admin → `/api/documents/alice` | 200 | `document-for-alice` | Có `ROLE_ADMIN` |

Tại sao có hai tầng cho `/api/reports`? HTTP rule chống truy cập trực tiếp trái phép; service rule bảo vệ logic nếu method được gọi từ một phần khác của ứng dụng thông qua proxy. Khi phân quyền thực tế, hai policy phải **khớp nhau** để tránh trải nghiệm sai hoặc tạo lỗ hổng. Không nên copy rule một cách thủ công đến hàng chục nơi; hãy gói policy vào thành phần có thể tái sử dụng và viết test thống nhất.

### Sự khác nhau giữa kết quả demo và dữ liệu thật

Controller `/api/documents/{owner}` chỉ trả chuỗi để dễ nhìn cơ chế quyết định. Nó không tra cứu document theo ID. Trong ứng dụng thật, endpoint ví dụ `GET /api/documents/42` cần kiểm tra *owner thực của tài liệu 42* từ database, kèm tenant và permissions, chứ không nhận `owner=reader` do client tự chọn rồi cho phép truy cập dữ liệu bất kỳ. Đây là vấn đề **IDOR/BOLA** (đọc tài nguyên của người khác bằng cách thay ID).

## 9. Thiết kế AuthorizationManager tùy chỉnh theo nghiệp vụ

Khi `hasRole`/`hasAuthority` chưa đủ, có thể viết custom manager. Nhưng trước khi viết, hãy xác định:

1. **Principal**: danh tính nào, được xác thực bằng cơ chế nào, authorities đã chuẩn hóa ra sao?
2. **Action**: READ, CREATE, APPROVE, DELETE... một hành động khác có thể cần policy khác.
3. **Resource**: tài nguyên nào, owner/tenant/state lấy từ database hay nguồn tin cậy nào?
4. **Context**: thời điểm, MFA, phân loại dữ liệu, policy version... có đáng tin cậy không?
5. **Failure modes**: tài nguyên không tồn tại, DB lỗi, policy service timeout, identity thiếu, kết quả abstain.
6. **Decision**: luôn trả kết quả rõ ràng cho phần policy mình chịu trách nhiệm; không âm thầm cho phép khi dependency lỗi.

Một mô hình thiết kế minh họa:

~~~text
DocumentPolicy.canRead(authentication, documentId)
  = authenticated
    AND permission includes DOCUMENT_READ
    AND (
         sameTenant AND isOwner
         OR explicit DOCUMENT_ADMIN delegation
        )
    AND document.notDeleted
~~~

Phần xác định `sameTenant`, `isOwner` phải dùng bản ghi thật. Nếu DB/policy server không phản hồi, đừng tự cấp quyền: quy tắc an toàn là **fail closed**, đồng thời cần phân biệt lỗi dịch vụ (thường 5xx) với quyết định từ chối nghiệp vụ (403/404 theo policy). "Fail closed" không có nghĩa phải giả mạo mọi lỗi thành HTTP 403.

### Khi nào viết policy riêng thay vì SpEL?

`@PreAuthorize("hasAuthority('DOCUMENT_READ')")` rất rõ ràng. Nhưng expression kéo dài với nhiều nhánh owner/tenant/feature flags thường khó audit và khó unit test. Khi logic phức tạp, dùng service policy có method rõ ràng và inject vào custom manager hoặc method-security expression. Đừng để controller, frontend và database query mỗi nơi tự định nghĩa "admin có quyền gì" theo cách khác nhau.

Nếu quyết định phải gọi một external policy engine (ví dụ OPA), cần timeout, caching theo policy version, phân loại lỗi và kiểm toán; không đẩy lời gọi blocking đắt tiền vào mọi request mà không đo performance. Tránh cache grant quá lâu khi revoke quyền cần có hiệu lực nhanh. Nếu policy có cạnh tranh concurrent update, xem xét snapshot/version hoặc transaction boundary để giảm TOCTOU.

## 10. Method security: quyết định trước/sau lời gọi

HTTP policy chỉ bảo vệ HTTP entrypoint. Business method có thể được gọi từ scheduled jobs, messaging consumers hoặc các component nội bộ, do đó phương pháp hay gặp là kết hợp request và method authorization.

Bật method security:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
~~~

Đây là fragment minh họa; ứng dụng demo đã có `@EnableMethodSecurity` nên không tạo bean cấu hình trùng chỉ để bật lại. Với phương pháp mặc định dựa trên Spring AOP proxies:

- `@PreAuthorize("hasAuthority('REPORT_READ')")`: quyết định trước khi gọi method.
- `@PostAuthorize("returnObject.owner == authentication.name")`: kiểm tra giá trị được trả sau method; cần hiểu rủi ro side effect và dữ liệu lộ trước khi có thể từ chối.
- `@PreFilter` và `@PostFilter`: có thể lọc input/return collection theo expression; tránh dùng tùy tiện với tập dữ liệu rất lớn.
- `@Secured` và `@RolesAllowed` có thể được hỗ trợ tùy cấu hình; không thay thế mọi trường hợp có điều kiện nghiệp vụ phức tạp.

Lưu ý: `@PreAuthorize` và `@PostAuthorize` là cú pháp rule, phía dưới Spring Security sử dụng các interceptor/manager tương ứng. `AuthorizationManagerBeforeMethodInterceptor` đi cùng các manager trước invocation; `AuthorizationManagerAfterMethodInterceptor` có thể xét cả kết quả sau invocation.

**Cảnh báo self-invocation:** trong cơ chế AOP proxy thông dụng, một lời gọi `this.securedMethod()` từ chính class đó có thể không qua proxy nên annotation không được áp. Gọi từ bean khác hoặc thiết kế service rõ ràng; kiểm thử cả đường gọi thực tế. Ngoài ra, lời gọi constructor/non-public method hoặc đối tượng không được Spring quản lý có thể khác hành vi mong đợi do cơ chế proxy.

**Chọn pre hay post?** Với thao tác thay đổi trạng thái (chuyển tiền, xóa, gửi email), ưu tiên kiểm tra quyền **trước side effect**. `@PostAuthorize` hợp lý cho một số tình huống kiểm tra kết quả trả về nhưng không thể "undo" những side effect đã xảy ra trước quyết định deny.

## 11. Test chính sách theo ma trận quyền

Không chỉ test "admin được phép". Một bộ test có giá trị phải bao phủ:

- anonymous/credentials sai;
- user đúng permission;
- user đã login nhưng thiếu permission;
- owner so với non-owner;
- admin thực sự có authority đúng;
- case không match route và default deny;
- same tenant/cross tenant với hệ thống nhiều tổ chức;
- rule giao nhau: thứ tự matcher có đúng không;
- method security khi gọi qua service bean;
- quyền bị revoke hoặc policy service lỗi (nếu có).

Thêm hai dependency trong `pom.xml` thuộc scope `test` (nếu chưa có):

~~~xml
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
~~~

Trong `src/test/java/com/example/authz/DemoAuthorizationTests.java`:

~~~java
package com.example.authz;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DemoAuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointWorksWithoutLogin() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void reportNeedsLogin() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "reader", authorities = "DOCUMENT_READ")
    void readerCannotSeeReport() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "reader", authorities = "DOCUMENT_READ")
    void readerCanSeeOwnDocument() throws Exception {
        mvc.perform(get("/api/documents/reader"))
            .andExpect(status().isOk())
            .andExpect(content().string("document-for-reader"));
    }

    @Test
    @WithMockUser(username = "reader", authorities = "DOCUMENT_READ")
    void readerCannotSeeOthersDocument() throws Exception {
        mvc.perform(get("/api/documents/alice"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin",
                  authorities = {"ROLE_ADMIN", "REPORT_READ"})
    void adminCanReadReport() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isOk())
            .andExpect(content().string("quarterly-report"));
    }
}
~~~

Chạy:

~~~bash
./mvnw test
~~~

Trên PowerShell: `.\mvnw.cmd test`. `@WithMockUser` cung cấp principal giả cho Spring Security test context; đây **không phải kiểm thử cơ chế đăng nhập HTTP Basic thực tế**. Để test Basic authentication, có thể dùng `httpBasic(...)` từ `spring-security-test` hoặc gọi HTTP thật. Hai loại test có mục đích khác nhau: policy test tránh phụ thuộc login flow, integration test xác minh hệ thống end-to-end.

Các assert trên là kết quả kỳ vọng của code và cấu hình đã nêu, chưa phải kết quả đã chạy bởi tài liệu này. Khi triển khai thực tế, chạy Maven tests, kiểm tra logs và phiên bản dependency.

## 12. Servlet và reactive sử dụng AuthorizationManager thế nào?

**Không trộn hai ngăn xếp API.**

| Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `AuthorizationFilter` và Servlet filters | `WebFilter` và reactive security filters |
| `AuthorizationManager<RequestAuthorizationContext>` | `ReactiveAuthorizationManager<AuthorizationContext>` (theo reactive API) |
| `SecurityContextHolder`, thường ThreadLocal | `ReactiveSecurityContextHolder` và Reactor Context |
| `authorizeHttpRequests` | `authorizeExchange` |

Ví dụ **minh họa reactive**, chỉ đặt bên trong Spring WebFlux configuration có các import và bean thích hợp, không đặt cùng ứng dụng Spring MVC demo:

~~~java
@Bean
SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .pathMatchers("/reports/**").hasAuthority("REPORT_READ")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Khi quyết định yêu cầu I/O bất đồng bộ trên WebFlux, chọn `ReactiveAuthorizationManager` và các publisher phù hợp thay vì blocking call trong event loop. Việc mang `AuthorizationManager<RequestAuthorizationContext>` của Servlet sang `authorizeExchange` chỉ vì tên giống nhau là sai type và sai mô hình thực thi. Authorization và authentication trong reactive chain cần dùng Reactor Context để giữ identity xuyên qua async boundaries.

## 13. Những thay đổi quan trọng theo phiên bản

### Từ mô hình AccessDecisionManager/Voter sang AuthorizationManager

Trước đây nhiều ứng dụng dùng `FilterSecurityInterceptor`, `AccessDecisionManager`, `AccessDecisionVoter`, metadata attributes và các chiến lược voting. Mô hình hiện đại đưa chính sách về `AuthorizationManager`, được tích hợp tại request và method security. Những thay đổi đáng nhớ:

- Dùng `authorizeHttpRequests` thay cho cấu hình `authorizeRequests` cũ để kích hoạt đường request authorization dựa trên `AuthorizationFilter`.
- Với custom logic, thay thế hoặc bọc cơ chế voter cũ bằng `AuthorizationManager` có ngữ nghĩa rõ ràng.
- Ở Spring Security 6.4+, ưu tiên `authorize(...)` thay `check(...)`; `check(...)` đã được deprecated trong dòng 6.5.
- Từ Spring Security 7, legacy Access API (`AccessDecisionManager`, `AccessDecisionVoter`, v.v.) nằm ở module legacy `spring-security-access`. Ứng dụng mới không nên phụ thuộc vào API cũ. Khi migrate cần xét riêng dependency và behavior.
- Spring Security 7 có `AuthorizationManagerFactory` để tùy biến cách manager mặc định được tạo. Đây không phải yêu cầu bắt buộc nếu DSL đã diễn đạt policy đầy đủ.

Không nên thay cấu hình theo phép đổi tên tự động rồi tin rằng hành vi được giữ 100%. Khi đổi model, review lại cách xử lý thứ tự matcher, abstain, exception, method interceptors, role prefix và default deny. Đọc migration guide đúng phiên bản đang nâng cấp.

### Khi nào dùng @PreAuthorize, khi nào cần custom AuthorizationManager?

Dùng `@PreAuthorize` cho policy ngắn, rõ, dựa trên authority/parameter khi nhóm dev đều hiểu. Dùng custom manager khi một policy được áp ở nhiều chỗ, có điều kiện domain phức tạp, cần test riêng hoặc tách interface tới dịch vụ quyết định quyền. Một policy service/domain method vẫn có thể được gọi từ custom `AuthorizationManager`; hai kỹ thuật hỗ trợ nhau.

## 14. Lỗi phổ biến và cách tránh

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Chỉ dùng `authenticated()` cho tài nguyên nhạy cảm | Mọi tài khoản login đều có quyền | Chỉ định authority/action/owner/tenant cụ thể |
| Đặt matcher rộng trước matcher hẹp | Rule hẹp bị che hoặc bỏ qua | Thiết kế thứ tự từ cụ thể tới tổng quát và test |
| Không có catch-all rule | Endpoint mới có thể có chính sách ngoài ý muốn | `anyRequest().denyAll()` cho tập endpoint kiểm soát |
| Tin `hasRole("ADMIN")` nghĩa là mọi quyền | Admin role không mặc định hàm ý mọi permission | Định nghĩa rõ role-authority mapping/hierarchy |
| Dùng `hasRole("SCOPE_read")` thay `hasAuthority("SCOPE_read")` | Sai prefix `ROLE_` | Kiểm tra authority thực sự trên authentication |
| Tin owner từ URL/header do client tự chọn | IDOR/BOLA, vượt tenant | Query nguồn dữ liệu tin cậy theo resource ID |
| Tự gọi `authorizationManager.authorize()` rồi bỏ qua kết quả | Quyết định không được thực thi | Dùng framework interceptor hoặc `verify`/kiểm tra kết quả đúng contract |
| Xem `null` (abstain) như `true` | Lỗ hổng "không ai từ chối thì cho qua" | Xác định composition và default deny |
| Catch mọi `AccessDeniedException` rồi trả 200 | Xóa mất security boundary | Giữ exception để handler chuẩn xử lý |
| Chỉ bảo vệ controller, service gọi được tự do | Bypass qua job/messaging/service khác | Method/domain security khi cần |
| Gọi `this.securedMethod()` với AOP proxy | Annotation có thể không được áp | Gọi qua Spring bean proxy, test execution path |
| Dùng `@PostAuthorize` cho operation có side effect | Method đã thay đổi dữ liệu trước khi deny | Authorization trước khi thao tác |
| Không test anonymous và denied | Chỉ chứng minh happy path | Test ma trận 401/403/granted/cross-tenant |
| Dùng blocking policy lookup trên reactive event loop | Nghẽn luồng, giảm throughput | Reactive manager + non-blocking source hoặc cô lập đúng scheduler |
| Hardcode credential/cache quyền quá lâu | Rò bí mật/quyền revoke chậm | Secret management, TTL/invalidation phù hợp |

## 15. Nguyên tắc thiết kế có thể áp dụng ngay

**Least privilege:** cấp đủ quyền cho nhiệm vụ, tránh authority bao trùm quá rộng. Trong hệ thống lớn, ưu tiên tên permission diễn tả hành động rõ như `INVOICE_READ`, `INVOICE_APPROVE` hơn các role không có ý nghĩa nghiệp vụ.

**Deny by default:** khi request không khớp rule đã cho phép, từ chối. Khi chính sách phụ thuộc dữ liệu mà dữ liệu không sẵn có, tránh tự cho phép; phân loại lỗi dịch vụ rõ.

**Defense in depth:** route authorization và method/domain authorization bổ sung cho nhau. Kiểm tra quyền còn đúng tại điểm lấy/sửa tài nguyên, đặc biệt với multi-tenant hay xử lý bất đồng bộ.

**Separation of concerns:** authentication quản lý danh tính; authorization quản lý policy; business service thực hiện nghiệp vụ. Manager nên có trách nhiệm cụ thể và dễ test.

**Correctness under change:** mỗi endpoint/permission mới cần cập nhật policy và test. Role mapping, tenant changes, policy cache, token scope, method proxying và thứ tự filter/chain là những nguồn lỗi thường khó thấy qua review UI.

**Auditability:** khi có quyết định deny, log thông tin cần thiết (principal ID phù hợp, action, resource identifier, policy version, outcome) nhưng tránh log password, access token hoặc dữ liệu cá nhân không cần thiết. Authorization event của Spring Security có thể hỗ trợ quan sát; hãy kiểm tra cấu hình publisher và phiên bản đang dùng.

**Không lấy việc ẩn nút trên frontend làm phân quyền.** UI có thể giúp người dùng không thao tác sai, nhưng backend phải xác minh mọi request. Client có thể tự gửi HTTP request mà không đi qua giao diện.

## 16. Bài tập tự luyện

**Bài 1 — Trạng thái quyết định.** Trong một hệ thống có ba custom managers, manager A trả `null` vì không quản path; manager B trả DENIED vì thiếu permission; manager C trả GRANTED vì người dùng là owner. Có thể kết luận request được cho qua chỉ bằng ba kết quả rời rạc này không? Giải thích phụ thuộc vào logic composition và thứ tự chính sách.

**Bài 2 — Role prefix.** Một token mang authorities `SCOPE_reports.read` và `ROLE_USER`. Dự đoán kết quả của `hasRole("USER")`, `hasAuthority("SCOPE_reports.read")`, `hasRole("reports.read")` theo role prefix mặc định.

**Bài 3 — Bảo vệ tài nguyên.** Endpoint `GET /documents/{id}` đang dùng `authenticated()`. Hãy thiết kế rule kiểm tra `DOCUMENT_READ`, owner và tenant từ database. Nêu riêng trường hợp DB timeout và tài nguyên không tồn tại.

**Bài 4 — Policy order.** Nếu đặt `requestMatchers("/api/**").permitAll()` trước `requestMatchers("/api/admin/**").hasRole("ADMIN")`, điều gì xảy ra? Đổi thứ tự và viết test khẳng định anonymous không thể gọi URL admin.

**Bài 5 — Method security.** Một service có `@PreAuthorize` ở method `transfer()` nhưng method khác trong cùng class gọi `this.transfer()`. Tại sao có nguy cơ bỏ qua annotation khi dùng Spring proxy? Hãy tổ chức lại bean để có một đường gọi đi qua proxy hoặc thực thi policy rõ ràng.

**Bài 6 — Version migration.** Khi nâng Spring Security 6.5 lên 7, hãy tìm nơi custom manager đang override `check(...)`, nơi dùng `AccessDecisionManager/Voter` và cách phản hồi khi manager abstain. Viết regression tests trước khi thay API.

**Gợi ý tự kiểm tra:**

- Bài 1: chưa đủ dữ kiện để kết luận; phải biết matcher và phép kết hợp, không coi abstain là grant.
- Bài 2: `hasRole("USER")` và `hasAuthority("SCOPE_reports.read")` phù hợp; `hasRole("reports.read")` theo mặc định tìm `ROLE_reports.read` và thường không match.
- Bài 3: phải tra owner/tenant từ resource thực, xử lý lỗi bằng fail closed và phân biệt lỗi hệ thống; không tin ID/tenant do client tự khai.
- Bài 4: matcher rộng có thể cấp quyền sớm, bỏ qua rule admin. Đưa rule cụ thể lên trước và có `anyRequest().denyAll()`.
- Bài 5: self-invocation có thể bypass proxy; kiểm tra policy tại boundary đáng tin cậy.
- Bài 6: tách đổi chữ ký API khỏi việc thay đổi quyết định truy cập; regression test bảo vệ security semantics.

## 17. Tổng kết và tài liệu tham khảo

`AuthorizationManager` là cơ chế trung tâm giúp Spring Security áp chính sách **ai được làm gì, trên tài nguyên nào**. Ba yếu tố cốt lõi cần nhớ:

1. **Đúng input:** `Authentication`/authorities đáng tin, hành động, tài nguyên thực, context như tenant/owner.
2. **Đúng decision:** GRANT, DENY, và ABSTAIN có ngữ nghĩa riêng; phải xác định default-deny và error behavior.
3. **Đúng enforcement point:** HTTP rule, method interceptor và domain-level checks bổ sung nhau; kiểm thử đường gọi thực tế.

Bắt đầu với DSL đơn giản, sau đó thêm custom manager khi business policy cần; đừng hy sinh tính rõ ràng và khả năng test để viết một expression quá phức tạp. Một quyết định truy cập đúng chỉ đáng tin khi nó được **áp dụng ở đúng chỗ**.

Tài liệu chính thức để đối chiếu theo phiên bản:

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security 6.5 — AuthorizationManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authorization/AuthorizationManager.html)
- [Spring Security 7 — Authorization overview](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/)
- [Spring Security — Reactive authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html)
