# hasRole, hasAnyRole, hasAuthority và hasAnyAuthority trong Spring Security Servlet

> **Ngữ cảnh:** Spring Security **Servlet**, Java 17+, Spring Boot 3.x / Spring Security 6.x. Bài tập trung vào **phân quyền HTTP** với `authorizeHttpRequests`: một request đã xác thực được cấp hoặc từ chối truy cập dựa trên **GrantedAuthority** nào, khác biệt giữa **role có tiền tố** và **authority so khớp nguyên văn**, ý nghĩa của các hàm `hasAny...` và cách kiểm thử. Có ví dụ Spring Boot gồm cấu hình, controller, người dùng demo, kiểm thử `MockMvc` qua filter chain và một chương trình Java 17 chạy trực tiếp. Không nhầm kiến thức về phân quyền với bước xác thực mật khẩu.

## 1. Hai câu hỏi phải tách rời

**Authentication** trả lời: *request này thuộc danh tính nào và bằng chứng xác thực có hợp lệ không?*  
**Authorization** trả lời: *danh tính hiện tại có được phép thực hiện hành động trên tài nguyên hay không?*

Một user đã đăng nhập thành công **không** tự được truy cập `/admin`. Spring Security kiểm tra những quyền thực tế gắn trong `Authentication.getAuthorities()` và policy của URL/method đang được gọi.

~~~text
HTTP request
   |
   v
FilterChainProxy -> SecurityFilterChain phù hợp
   |
   +-- Authentication mechanism
   |       session / form login / Basic / bearer token ...
   |       -> Authentication đã xác thực
   |       -> authorities do nguồn tin cậy cấp
   |
   v
AuthorizationFilter
   |
   v
RequestMatcher (ví dụ: GET /api/reports/**)
   |
   v
AuthorizationManager do authorizeHttpRequests khai báo
   |
   +-- Quyền phù hợp -> tiếp tục đến DispatcherServlet/controller
   |
   +-- Không đủ quyền -> AccessDenied / 403 thông thường
   |
   +-- Chưa xác thực -> AuthenticationEntryPoint,
                         có thể redirect login hoặc 401
~~~

**Định nghĩa tối thiểu:** một `GrantedAuthority` là đối tượng có `String getAuthority()`, ví dụ `ROLE_ADMIN`, `ROLE_USER`, `SCOPE_reports.read` hoặc `DOCUMENT_READ`. Đây **không** phải password, username hay tên HTTP endpoint; nó là chuỗi mà hệ thống sử dụng để đối chiếu với rule.

Một principal có thể có nhiều authority:

~~~text
Authentication.getName()       = "alice"
Authentication.isAuthenticated() = true

Authentication.getAuthorities() = [
  ROLE_ADMIN,
  DOCUMENT_READ,
  BILLING_WRITE,
  SCOPE_reports.read,
  SCOPE_reports.write
]
~~~

Khi authorization kiểm tra, framework không tự hỏi “alice có tên là admin không?”. Nó so quyền đã được **server xác nhận** với các điều kiện mà người phát triển khai báo.

## 2. So sánh nhanh bốn hàm

| Rule trong `authorizeHttpRequests` | Ý nghĩa với cách đặt tên ROLE_ mặc định | Ví dụ authorities cần có |
| --- | --- | --- |
| `hasRole("ADMIN")` | Yêu cầu **một role**, được diễn giải như authority `ROLE_ADMIN`. | `ROLE_ADMIN` |
| `hasAnyRole("ADMIN", "OPS")` | Có **ít nhất một** trong các role được liệt kê. | `ROLE_ADMIN` **hoặc** `ROLE_OPS` |
| `hasAuthority("DOCUMENT_READ")` | Yêu cầu **một authority đúng nguyên chuỗi**. | `DOCUMENT_READ` |
| `hasAnyAuthority("BILLING_READ", "BILLING_WRITE")` | Có **ít nhất một** authority đúng nguyên chuỗi. | `BILLING_READ` **hoặc** `BILLING_WRITE` |

Với cách cấp authority thông thường của Spring Security:

~~~text
hasRole("ADMIN")                   ≈ hasAuthority("ROLE_ADMIN")
hasAnyRole("ADMIN", "OPS")         ≈ hasAnyAuthority("ROLE_ADMIN", "ROLE_OPS")
hasAuthority("ADMIN")             KHÁC hasAuthority("ROLE_ADMIN")
hasAuthority("SCOPE_reports.read") không tự tương đương hasRole("reports.read")
~~~

Ký hiệu `≈` chỉ biểu đạt hiệu quả so khớp **với tiền tố role mặc định và không có cấu hình đặc biệt**; không phải mọi phiên bản hoặc mọi tích hợp method/expression security đều dùng chung một cơ chế tùy chỉnh prefix.

**Nhớ ngay:** `hasAny...` là **OR**, không phải AND. Nếu cần user phải có **hai quyền cùng lúc**, không dùng `hasAnyAuthority("A","B")` vì chỉ cần A *hoặc* B là được; cần điều kiện kết hợp được hỗ trợ, custom `AuthorizationManager` hoặc policy thích hợp.

## 3. hasRole: chuyển tên role sang chuỗi GrantedAuthority thế nào?

Ví dụ:

~~~java
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

Trong cấu hình phổ biến, điều kiện tìm authority `ROLE_ADMIN` trong `Authentication.getAuthorities()`. User mang `ROLE_ADMIN` qua được; user chỉ có `ADMIN` thì **không** qua với policy này. Chính cơ chế **ROLE_ prefix** tạo ra khác biệt.

**Nên truyền `"ADMIN"`, không truyền `"ROLE_ADMIN"` vào `hasRole`.** Trong DSL `authorizeHttpRequests` dựa trên `AuthorityAuthorizationManager`, hàm `hasRole` thuộc các phiên bản Spring Security 6 thường kiểm tra đầu vào không chứa tiền tố chuẩn `ROLE_` và có thể ném `IllegalArgumentException` nếu bạn gọi `hasRole("ROLE_ADMIN")`. Khi muốn kiểm tra chính xác chuỗi `ROLE_ADMIN`, dùng `hasAuthority("ROLE_ADMIN")`.

### Cấp authority từ UserDetails

`User.withUsername(...)` có hai kiểu DSL dễ gây nhầm:

~~~java
// Trích từ một method trả UserDetails trong ứng dụng có
// PasswordEncoder encoder đã được khai báo.
UserDetails byRole = User.withUsername("an")
    .password(encoder.encode("demo-only"))
    .roles("ADMIN")
    .build();

// Tương đương về chuỗi quyền: ROLE_ADMIN.
UserDetails byExactAuthority = User.withUsername("binh")
    .password(encoder.encode("demo-only"))
    .authorities("ROLE_ADMIN")
    .build();
~~~

Các ví dụ trên là **mảnh code**, cần import `User`, `UserDetails`, và biến `encoder` đã được truyền đúng kiểu. Với cách builder chuẩn, `roles("ADMIN")` thêm tiền tố `ROLE_` khi tạo authorities; `authorities("ROLE_ADMIN")` thì giữ nguyên chuỗi mà caller cung cấp.

**Sai lầm quan trọng:** không nên gọi `.roles("ADMIN").authorities("DOCUMENT_READ")` rồi giả định chắc chắn kết quả có cả hai nhóm. Các method của `User.UserBuilder` có thể đặt lại trường authorities theo lần gọi sau; hãy xây **danh sách đầy đủ** bằng `.authorities("ROLE_ADMIN", "DOCUMENT_READ")`, hoặc dùng thành phần mapping roles → authorities rõ ràng do bạn quản lý.

### ROLE_ là quy ước, không phải “kiểu dữ liệu role” riêng

Trong `Authentication.getAuthorities()`, thường chỉ có các đối tượng `GrantedAuthority` mang chuỗi. Tiền tố `ROLE_` cho framework/ứng dụng một quy ước đặt tên để phân biệt role cấp cao với quyền chức năng. Không có cơ chế Java tự suy ra role từ chuỗi username hoặc bảng `roles` nếu bạn không ánh xạ dữ liệu đúng lúc xây `Authentication`.

Ví dụ, bảng database chứa role `ADMIN`. Nếu service ánh xạ ra `new SimpleGrantedAuthority("ADMIN")` trong khi cấu hình HTTP dùng `hasRole("ADMIN")`, kiểm tra thất bại do thiếu `ROLE_`. Hãy quyết định thống nhất: role được chuẩn hóa thành `ROLE_ADMIN`, hoặc dùng `hasAuthority("ADMIN")` đúng định dạng theo policy (và xử lý các thành phần security khác cho đồng bộ).

## 4. hasAnyRole: ít nhất một role, không phải tất cả role

~~~java
.requestMatchers("/ops/**").hasAnyRole("ADMIN", "OPS")
~~~

Quy tắc này cho phép request khi danh sách authorities chứa **ROLE_ADMIN hoặc ROLE_OPS**. Không đòi user phải đồng thời có cả hai.

| Authorities của user | hasAnyRole("ADMIN","OPS") | Lý do |
| --- | --- | --- |
| `[ROLE_ADMIN]` | Cho phép | Có ROLE_ADMIN. |
| `[ROLE_OPS]` | Cho phép | Có ROLE_OPS. |
| `[ROLE_ADMIN, ROLE_OPS]` | Cho phép | Có cả hai nhưng chỉ cần một. |
| `[ROLE_USER]` | Từ chối | Không có authority được yêu cầu. |
| `[ADMIN]` | Từ chối | Chuỗi thiếu ROLE_ theo quy ước mặc định. |
| `[]` | Từ chối | Không có quyền tương ứng. |

Giả sử business rule yêu cầu người sử dụng phải vừa là **nhân sự tài chính** vừa đã được **duyệt quyền ký lệnh**. Dùng `hasAnyRole("FINANCE", "APPROVED_SIGNER")` là **sai semantics** vì nó cho người chỉ có một quyền qua. Cần diễn đạt **AND** trong một `AuthorizationManager` hoặc cơ chế điều kiện hỗ trợ.

Một admin **không tự có tất cả role còn lại** nếu chưa cấu hình **role hierarchy**. Chẳng hạn user có `ROLE_ADMIN` nhưng không có `ROLE_USER` thường không thỏa `hasRole("USER")`. Nếu muốn admin kế thừa user, hãy cấp cả hai hoặc cấu hình role hierarchy được framework và đúng loại authorization manager sử dụng. Đừng dựa vào suy luận “ADMIN lớn hơn USER nên chắc chắn được phép” khi test chưa chứng minh điều đó.

## 5. hasAuthority: đối chiếu chính xác, không thêm ROLE_

~~~java
.requestMatchers("/docs/**").hasAuthority("DOCUMENT_READ")
~~~

Rule yêu cầu chuỗi authority **đúng** `DOCUMENT_READ`, không tự đổi thành `ROLE_DOCUMENT_READ`. Nếu nguồn quyền chứa:

~~~text
[DOCUMENT_READ, ROLE_USER, SCOPE_reports.read]
~~~

thì `hasAuthority("DOCUMENT_READ")` có thể cấp quyền, còn `hasAuthority("ROLE_DOCUMENT_READ")` thì không nếu chỉ có tập trên.

### Scope của OAuth2/JWT

Một mẫu thường gặp ở resource server là ánh xạ scope của bearer token thành authority có tiền tố `SCOPE_`. Ví dụ claim `scope: "reports.read reports.write"` có thể tạo `SCOPE_reports.read` và `SCOPE_reports.write` thông qua converter mặc định phù hợp.

Khi đó:

~~~java
.requestMatchers(HttpMethod.GET, "/api/reports/**")
    .hasAuthority("SCOPE_reports.read")

.requestMatchers(HttpMethod.POST, "/api/reports/**")
    .hasAuthority("SCOPE_reports.write")
~~~

Đây là **authority scope chính xác**, không phải role. Không nên viết `hasRole("SCOPE_reports.read")`. Điều kiện đó sẽ tìm `ROLE_SCOPE_reports.read` theo quy ước role mặc định, khác hẳn scope mà resource server cấp.

**Cẩn trọng:** converter JWT có thể đã được tùy chỉnh, và các claim/authority thực tế có thể mang tên khác. Hãy kiểm tra `Authentication.getAuthorities()` **ở môi trường phát triển đã ẩn dữ liệu nhạy cảm** và unit/integration test converter; không tự suy ra mọi JWT đều được ánh xạ giống nhau.

### Business permissions

Một ứng dụng có thể dùng authority có tính mô tả hành động:

~~~text
INVOICE_VIEW
INVOICE_APPROVE
INVOICE_REFUND
DOCUMENT_READ
DOCUMENT_WRITE
CUSTOMER_EXPORT
~~~

Đó là các chuỗi do **server** cấp và đối chiếu trực tiếp bằng `hasAuthority`. Việc đặt tên permission rõ ràng khiến policy ít phụ thuộc vào role: người có vai trò quản lý và người có vai trò kế toán đều có thể được cấp `INVOICE_VIEW` nếu nghiệp vụ cho phép.

Role có thể là **nhóm quyền tổng quát**, authority có thể biểu diễn **quyền cụ thể**. Tuy nhiên Spring Security không ép bạn theo một schema quản trị phân quyền cố định; nó đối chiếu những chuỗi authority mà authentication đã mang. Mọi phép ánh xạ role → permission là quyết định của ứng dụng hoặc bộ quản lý danh tính.

## 6. hasAnyAuthority: một trong nhiều quyền cụ thể

~~~java
.requestMatchers("/billing/**")
    .hasAnyAuthority("BILLING_READ", "BILLING_WRITE")
~~~

Trên policy này, người có **BILLING_READ hoặc BILLING_WRITE** được đi vào. Đây có thể là thiết kế hợp lý cho trang tổng quan dùng chung, nhưng **không** phù hợp để bảo vệ endpoint **ghi/sửa** dữ liệu thanh toán nếu người có BILLING_READ cũng sẽ được chấp nhận.

Ví dụ tốt hơn với HTTP method khác nhau:

~~~java
.requestMatchers(HttpMethod.GET, "/billing/invoices/**")
    .hasAnyAuthority("BILLING_READ", "BILLING_WRITE")
.requestMatchers(HttpMethod.POST, "/billing/invoices/**")
    .hasAuthority("BILLING_WRITE")
.requestMatchers("/billing/invoices/**")
    .denyAll()
~~~

Phân quyền nên theo **hành động trên endpoint**, không chỉ theo tên nhóm URL. Một policy cho `GET` không tự an toàn cho `POST`, `PUT`, `PATCH` hay `DELETE`.

### OR không có nghĩa kế thừa và không có nghĩa AND

Cho authorities `[BILLING_READ]`:

~~~text
hasAnyAuthority("BILLING_READ", "BILLING_WRITE") -> true
hasAuthority("BILLING_WRITE")                    -> false
~~~

Cho authorities `[ROLE_ADMIN]`:

~~~text
hasAnyAuthority("BILLING_READ", "BILLING_WRITE") -> false
hasAnyRole("ADMIN", "OPS")                        -> true
~~~

Không có liên hệ ngầm giữa một role tổng quát và tất cả permission ứng dụng. Muốn admin có `BILLING_WRITE`, bạn phải cấp permission ấy khi map principal hoặc cấu hình role hierarchy/authorization manager phù hợp và kiểm thử. Những điều kiện dùng role prefix và scope prefix không phải cùng một namespace.

## 7. Một bảng tra cứu quan trọng

Giả sử danh sách quyền thực tế:

~~~text
ROLE_ADMIN
ROLE_USER
DOCUMENT_READ
SCOPE_reports.read
~~~

| Rule | Kết quả | Giải thích |
| --- | --- | --- |
| `hasRole("ADMIN")` | Đúng | Có ROLE_ADMIN. |
| `hasRole("USER")` | Đúng | Có ROLE_USER. |
| `hasRole("OPS")` | Sai | Không có ROLE_OPS. |
| `hasAnyRole("OPS","ADMIN")` | Đúng | Có ADMIN, chỉ cần một. |
| `hasAuthority("ADMIN")` | Sai | Không có nguyên chuỗi ADMIN. |
| `hasAuthority("ROLE_ADMIN")` | Đúng | Có nguyên chuỗi ROLE_ADMIN. |
| `hasAnyAuthority("DOCUMENT_WRITE","DOCUMENT_READ")` | Đúng | Có DOCUMENT_READ. |
| `hasAuthority("SCOPE_reports.read")` | Đúng | Có scope tương ứng. |
| `hasRole("reports.read")` | Sai | Điều kiện sẽ tìm ROLE_reports.read. |
| `hasAnyAuthority("SCOPE_reports.write","ROLE_OPS")` | Sai | Không có cả hai chuỗi được liệt kê. |

Dạng câu hỏi kiểm thử này hữu ích hơn việc học thuộc tên API: hãy **viết ra đúng danh sách GrantedAuthority**, biến từng rule thành phép kiểm tra membership/OR rồi quyết định kết quả. Tuy nhiên, test với danh sách tự tạo chỉ chứng minh phép so khớp; cần thêm test xem quá trình login/JWT converter có cấp đúng authorities thật hay không.

## 8. Áp dụng bốn hàm trong authorizeHttpRequests

Trong Spring Security 6, ứng dụng Servlet thường khai báo:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/ops/**").hasAnyRole("ADMIN", "OPS")
    .requestMatchers("/docs/**").hasAuthority("DOCUMENT_READ")
    .requestMatchers("/billing/**")
        .hasAnyAuthority("BILLING_READ", "BILLING_WRITE")
    .anyRequest().authenticated());
~~~

Đây là **mảnh cấu hình**, cần class `@Configuration`, `HttpSecurity`, `SecurityFilterChain`. Thứ tự khai báo rule có ý nghĩa: với matcher-based registry thông dụng, rule đầu tiên khớp request sẽ chọn `AuthorizationManager` áp dụng. Một điều kiện quá rộng đặt trước có thể khiến rule cụ thể phía sau không bao giờ được xét.

### Ví dụ thứ tự nguy hiểm

~~~java
// PHẢN VÍ DỤ: mọi URL đều đi qua authenticated trước,
// và rule /admin/** phía dưới không còn cơ hội áp dụng.
http.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
    .requestMatchers("/admin/**").hasRole("ADMIN"));
~~~

Trong một số phiên bản, DSL còn ngăn cấu hình matcher sau `anyRequest` bằng lỗi build. Dù biểu hiện là exception hay policy không mong muốn, nguyên tắc vẫn là **rule cụ thể trước, rule rộng sau**. Không cố “khắc phục” bằng cách dùng `permitAll` ở đầu chuỗi.

### HTTP method là một phần của quyền

~~~java
.requestMatchers(HttpMethod.GET, "/api/items/**")
    .hasAuthority("ITEM_READ")
.requestMatchers(HttpMethod.POST, "/api/items/**")
    .hasAuthority("ITEM_WRITE")
.requestMatchers("/api/items/**").denyAll()
~~~

Ở cấu hình này, một người có `ITEM_READ` không được phép sửa bằng POST; các method chưa nêu ra bị từ chối thay vì vô tình thừa hưởng quyền read. **CSRF** là lớp kiểm tra khác: với browser cookie session, POST có thể bị CSRF filter từ chối **trước cả khi** tới authorization. Để kiểm thử quyền POST, phải cung cấp CSRF token hợp lệ, nếu không một `403` có thể chỉ nói rằng thiếu token chứ không kiểm chứng `hasAuthority`.

### Phân biệt 401, 403 và redirect

Không nên viết quy tắc cứng rằng “sai role luôn trả 401”. Trong web browser:

- User chưa xác thực: có thể được chuyển tới form login `302` hoặc nhận `401` tùy `AuthenticationEntryPoint` và request.
- User đã xác thực nhưng thiếu authority: thường nhận `403 Forbidden`.
- User đã xác thực và đủ quyền: request đi tiếp tới controller, nhưng controller vẫn có thể từ chối vì tài nguyên không tồn tại hoặc business policy sâu hơn.

Hãy test response từ **đúng security chain** và xác nhận authentication state; không suy luận role từ mỗi HTTP status.

## 9. Ví dụ Spring Boot 3 / Java 17 đầy đủ

Chúng ta xây ứng dụng với các endpoint minh họa **cả bốn hàm** và kiểm thử HTTP thật qua `MockMvc`. Dùng Spring Initializr tạo dự án Boot 3.x với JDK 17+ và dependencies:

~~~text
spring-boot-starter-web
spring-boot-starter-security
spring-boot-starter-test   (test scope)
spring-security-test      (test scope)
~~~

Các tệp Java bên dưới nằm trong package `com.example.roleauthority`. Cần một dự án Maven/Gradle được cấu hình dependency đúng; mã Spring không phải chương trình Java SE có thể biên dịch đơn lẻ bằng `javac`.

### 9.1. SecurityConfig.java

~~~java
package com.example.roleauthority;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-alice-only"))
                .authorities(
                    "ROLE_ADMIN",
                    "DOCUMENT_READ",
                    "BILLING_WRITE",
                    "SCOPE_reports.read",
                    "SCOPE_reports.write")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("demo-bob-only"))
                .authorities("ROLE_OPS", "BILLING_READ")
                .build();

        UserDetails cara = User.withUsername("cara")
                .password(encoder.encode("demo-cara-only"))
                .authorities("DOCUMENT_READ", "SCOPE_reports.read")
                .build();

        UserDetails dave = User.withUsername("dave")
                .password(encoder.encode("demo-dave-only"))
                .roles("USER")
                .build();

        return new InMemoryUserDetailsManager(alice, bob, cara, dave);
    }

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public").permitAll()

                // HTTP method cụ thể phải đứng trước rule tổng quát.
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.write")
                .requestMatchers("/api/reports/**").denyAll()

                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/ops/**").hasAnyRole("ADMIN", "OPS")
                .requestMatchers("/docs/**")
                    .hasAuthority("DOCUMENT_READ")
                .requestMatchers("/billing/**")
                    .hasAnyAuthority("BILLING_READ", "BILLING_WRITE")
                .requestMatchers("/user/**").hasRole("USER")

                .requestMatchers("/profile").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults());

        // CSRF mặc định vẫn bật cho các unsafe methods.
        return http.build();
    }
}
~~~

**Đọc đúng đoạn cấu hình:**

1. `GET /api/reports/{id}` cần `SCOPE_reports.read`.
2. `POST /api/reports/{id}` cần `SCOPE_reports.write` **và** nếu dùng CSRF-enabled chain thì phải qua CSRF filter.
3. Các method còn lại trên `/api/reports/**` bị `denyAll`. Không suy ra DELETE được phép vì POST được phép.
4. `/admin/**` yêu cầu `ROLE_ADMIN` (qua `hasRole("ADMIN")`).
5. `/ops/**` chấp nhận `ROLE_ADMIN` hoặc `ROLE_OPS` (qua `hasAnyRole`).
6. `/docs/**` yêu cầu đúng `DOCUMENT_READ`.
7. `/billing/**` chấp nhận `BILLING_READ` hoặc `BILLING_WRITE`. Đây là trang demo chỉ đọc; với endpoint cập nhật cần rule riêng cho WRITE như mục 6.
8. `/user/**` cần `ROLE_USER`; **alice** không tự qua được dù có `ROLE_ADMIN`, vì demo không cấu hình role hierarchy và Alice không có `ROLE_USER`.
9. `.anyRequest().denyAll()` đóng mặc định các route chưa được liệt kê; tốt cho bài tập phân quyền vì mọi API mới phải có policy được review.
10. `formLogin` cho browser session; `httpBasic` thêm cơ chế xác thực dễ thử HTTP test. Không dùng mật khẩu demo trong production; use user store/secret policy thật.

**Không tạo authority từ dữ liệu client:** danh sách Alice/Bob/Cara/Dave được server cố định trong `UserDetailsService` của demo. Trong production, nó phải được truy vấn từ kho quyền có phân quyền quản trị hoặc ánh xạ từ issuer JWT đã được xác thực signature/issuer/audience, không dùng `X-Role` hay JSON `roles` do client tự gửi.

### 9.2. AccessController.java

~~~java
package com.example.roleauthority;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccessController {

    @GetMapping("/")
    public String root() {
        return "public-home";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/admin/panel")
    public String admin() {
        return "admin";
    }

    @GetMapping("/ops/panel")
    public String ops() {
        return "ops";
    }

    @GetMapping("/docs/file")
    public String document() {
        return "document";
    }

    @GetMapping("/billing/invoices")
    public String billing() {
        return "billing";
    }

    @GetMapping("/user/home")
    public String userHome() {
        return "user-home";
    }

    @GetMapping("/profile")
    public String profile(Authentication auth) {
        return auth.getName();
    }

    @GetMapping("/api/reports/{id}")
    public String readReport(@PathVariable String id) {
        return "report:" + id;
    }

    @PostMapping("/api/reports/{id}")
    public String updateReport(@PathVariable String id) {
        // Bài học chỉ trả chuỗi để minh họa security,
        // không thực sự chỉnh sửa báo cáo.
        return "updated:" + id;
    }
}
~~~

**Chú ý:** vì response của `POST /api/reports/{id}` không làm thay đổi DB trong bài demo, test vẫn minh họa được **authorization và CSRF ở HTTP boundary**. Trong production, controller/service phải kiểm tra thêm quyền theo **tài nguyên cụ thể** (owner, tenant, trạng thái đơn hàng/báo cáo...), không chỉ URL và role tổng quát.

### 9.3. RoleAuthorityApplication.java

~~~java
package com.example.roleauthority;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoleAuthorityApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoleAuthorityApplication.class, args);
    }
}
~~~

Các class trên phải cùng package `com.example.roleauthority` hoặc nằm trong component scan của main class. Một project Spring Boot đã có main class riêng không cần thêm main thứ hai; sử dụng một cấu trúc package nhất quán.

### 9.4. Chạy ứng dụng minh họa

Trong project có Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Đường dẫn demo (chỉ trên localhost):

~~~bash
# Public, không cần đăng nhập:
curl -i http://localhost:8080/public

# Alice có ROLE_ADMIN:
curl -i -u alice:demo-alice-only \
  http://localhost:8080/admin/panel

# Bob có ROLE_OPS nhưng không có ROLE_ADMIN:
curl -i -u bob:demo-bob-only \
  http://localhost:8080/ops/panel

# Cara có DOCUMENT_READ:
curl -i -u cara:demo-cara-only \
  http://localhost:8080/docs/file

# Cara đọc reports được bằng scope:
curl -i -u cara:demo-cara-only \
  http://localhost:8080/api/reports/42
~~~

Với cấu hình và credentials demo, những request trên có thể trả `200` cùng body `public`, `admin`, `ops`, `document` hoặc `report:42` tương ứng. Đừng khẳng định toàn bộ header/stdout `curl -i` cố định vì phiên bản HTTP/container có thể khác. **Không đưa mật khẩu thật vào command line**: lệnh `curl -u` ở đây chỉ minh họa với tài khoản giả trên localhost; command line/history và process inspection có thể làm lộ credential.

Với POST protected và CSRF mặc định bật, không thể chỉ dùng `curl -X POST -u ...` rồi suy ra authority có hợp lệ khi thấy 403; CSRF có thể đã chặn request trước. Hãy dùng `MockMvc` cùng `csrf()` như phần sau, hoặc một client tích hợp lấy token đúng cơ chế.

## 10. Bộ test tích hợp: kiểm tra đúng từng phương thức

Tạo `src/test/java/com/example/roleauthority/HttpAuthorizationIntegrationTest.java` trong cùng project với `spring-boot-starter-test` và `spring-security-test`:

~~~java
package com.example.roleauthority;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HttpAuthorizationIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointNeedsNoCredentials() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void adminRoleAndOpsRoleAreDifferent() throws Exception {
        mvc.perform(get("/admin/panel")
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));

        mvc.perform(get("/admin/panel")
                    .with(httpBasic("bob", "demo-bob-only")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/ops/panel")
                    .with(httpBasic("bob", "demo-bob-only")))
            .andExpect(status().isOk());

        mvc.perform(get("/ops/panel")
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isOk());
    }

    @Test
    void roleAdminDoesNotAutomaticallyImplyRoleUser()
            throws Exception {
        mvc.perform(get("/user/home")
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/user/home")
                    .with(httpBasic("dave", "demo-dave-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("user-home"));
    }

    @Test
    void exactAuthoritiesControlDocumentsAndBilling()
            throws Exception {
        mvc.perform(get("/docs/file")
                    .with(httpBasic("cara", "demo-cara-only")))
            .andExpect(status().isOk());

        mvc.perform(get("/docs/file")
                    .with(httpBasic("bob", "demo-bob-only")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/billing/invoices")
                    .with(httpBasic("bob", "demo-bob-only")))
            .andExpect(status().isOk());

        mvc.perform(get("/billing/invoices")
                    .with(httpBasic("cara", "demo-cara-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void scopeReadDoesNotGrantScopeWrite() throws Exception {
        mvc.perform(get("/api/reports/42")
                    .with(httpBasic("cara", "demo-cara-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:42"));

        // Có csrf() để chắc chắn 403 xuất phát từ policy
        // thiếu SCOPE_reports.write, không do thiếu CSRF.
        mvc.perform(post("/api/reports/42")
                    .with(csrf())
                    .with(httpBasic("cara", "demo-cara-only")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/reports/42")
                    .with(csrf())
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isOk())
            .andExpect(content().string("updated:42"));
    }

    @Test
    void unsafeRequestStillRequiresCsrf() throws Exception {
        // Alice có scope write nhưng POST không mang CSRF token.
        mvc.perform(post("/api/reports/42")
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unlistedHttpMethodIsDeniedEvenForAdmin()
            throws Exception {
        mvc.perform(delete("/api/reports/42")
                    .with(csrf())
                    .with(httpBasic("alice", "demo-alice-only")))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là **integration test qua servlet filter chain**, không phải gọi `AuthorizationManager` trực tiếp. `httpBasic(...)` gửi Basic credentials giả đến Spring Security; `UserDetailsService` trả authorities; sau đó `AuthorizationFilter` áp dụng từng rule. Những assertion này có ý nghĩa hơn việc chỉ tạo một object `Authentication` giả rồi kiểm tra kết quả của một method.

Các tình huống được chứng minh:

- `hasRole("ADMIN")` chấp nhận Alice có `ROLE_ADMIN`, từ chối Bob có `ROLE_OPS`.
- `hasAnyRole("ADMIN","OPS")` cho cả Alice hoặc Bob qua `/ops/**`.
- `hasAuthority("DOCUMENT_READ")` cho Cara qua `/docs/**` nhưng không cho Bob.
- `hasAnyAuthority("BILLING_READ","BILLING_WRITE")` chấp nhận Bob với BILLING_READ; không chấp nhận Cara.
- Alice có `ROLE_ADMIN` nhưng **không** có `ROLE_USER`; `/user/**` vẫn bị 403 vì không thiết lập hierarchy.
- Cara chỉ có `SCOPE_reports.read`; được GET nhưng không được POST sau khi đã gửi token CSRF hợp lệ. Alice có `SCOPE_reports.write` được POST.
- `DELETE /api/reports/42` bị deny-all vì không có method rule cho DELETE, dù user là admin.
- Với CSRF-enabled web chain, POST thiếu token vẫn bị 403 ngay cả khi authority write có sẵn; đừng gán mọi 403 là thiếu role.

Chạy bộ test qua Maven Wrapper:

~~~bash
./mvnw test
~~~

Không đưa ra một stdout cố định cho Maven/Test vì phụ thuộc môi trường, cấu hình JDK, phiên bản thư viện và các test khác. Một bài học nâng cao là kiểm tra **nguyên nhân** của 403 bằng cách bảo đảm request đã có CSRF hợp lệ và user đã authenticated.

### Mock user vs xác thực thật

`spring-security-test` còn có `user("test").roles("ADMIN")` hoặc `@WithMockUser(roles="ADMIN")`. Chúng rất phù hợp để **unit-test authorization** nhưng có thể bỏ qua bước **cấp quyền từ user store** hoặc login thực tế. Nếu code mapping role từ database bị sai, test chỉ dùng mock user có `ROLE_ADMIN` vẫn xanh.

Vì vậy nên có cả:

1. Test mapping authority ở `UserDetailsService`/JWT converter.
2. HTTP integration test như trên có credential thật của fixture (hoặc flow login phù hợp), để chứng minh kết quả mapping được đi vào `AuthorizationManager`.
3. Test resource-level/tenant-level permissions tại service, vì chỉ URL permission chưa đủ để bảo vệ từng bản ghi.

## 11. Java 17 độc lập: tự mô phỏng chính xác bốn điều kiện

Cần một thí nghiệm không phụ thuộc Spring Security để hiểu các phép so khớp. Tạo file `RoleAuthorityDemo.java`:

~~~java
import java.util.Set;

public final class RoleAuthorityDemo {

    static boolean hasAuthority(Set<String> granted, String wanted) {
        return granted.contains(wanted);
    }

    static boolean hasAnyAuthority(
            Set<String> granted, String... wanted) {
        for (String authority : wanted) {
            if (hasAuthority(granted, authority)) {
                return true;
            }
        }
        return false;
    }

    static boolean hasRole(Set<String> granted, String role) {
        if (role.startsWith("ROLE_")) {
            throw new IllegalArgumentException(
                    "Pass role name without ROLE_ prefix");
        }
        return hasAuthority(granted, "ROLE_" + role);
    }

    static boolean hasAnyRole(Set<String> granted, String... roles) {
        for (String role : roles) {
            if (hasRole(granted, role)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) {
        Set<String> granted = Set.of(
                "ROLE_ADMIN",
                "BILLING_READ",
                "SCOPE_reports.read");

        System.out.println("hasRole(ADMIN)="
                + hasRole(granted, "ADMIN"));
        System.out.println("hasRole(USER)="
                + hasRole(granted, "USER"));
        System.out.println("hasAuthority(ADMIN)="
                + hasAuthority(granted, "ADMIN"));
        System.out.println("hasAuthority(ROLE_ADMIN)="
                + hasAuthority(granted, "ROLE_ADMIN"));
        System.out.println("hasAnyRole(USER,ADMIN)="
                + hasAnyRole(granted, "USER", "ADMIN"));
        System.out.println("hasAnyAuthority(WRITE,READ)="
                + hasAnyAuthority(
                    granted, "BILLING_WRITE", "BILLING_READ"));
        System.out.println("hasAuthority(SCOPE_reports.write)="
                + hasAuthority(granted, "SCOPE_reports.write"));
    }
}
~~~

Biên dịch và chạy trực tiếp bằng JDK 17+:

~~~bash
javac RoleAuthorityDemo.java
java RoleAuthorityDemo
~~~

Stdout **chính xác**:

~~~text
hasRole(ADMIN)=true
hasRole(USER)=false
hasAuthority(ADMIN)=false
hasAuthority(ROLE_ADMIN)=true
hasAnyRole(USER,ADMIN)=true
hasAnyAuthority(WRITE,READ)=true
hasAuthority(SCOPE_reports.write)=false
~~~

Chương trình này **không** tạo `SecurityFilterChain`, không kiểm tra mật khẩu, không xử lý HTTP, cũng không thực thi `AuthorizationManager` thật. Nó cố ý chỉ mô phỏng **quy tắc membership** với tiền tố ROLE_ mặc định. Mục tiêu là thấy một dòng authorities `ROLE_ADMIN` sẽ thỏa `hasRole("ADMIN")` nhưng **không** thỏa `hasAuthority("ADMIN")`.

Không nhầm phần kiểm tra role của Java SE này với bảo đảm bảo mật đầy đủ: trong hệ thống thật, authorities phải đến từ nguồn server tin cậy, policy phải nằm trong Spring Security chain phù hợp, và những endpoint ghi dữ liệu phải kiểm tra CSRF hay token/permission theo thiết kế.

## 12. Cách ánh xạ role từ database an toàn

Một hệ thống thường lưu role dưới dạng `ADMIN`, `OPS`, `USER`. `UserDetailsService` hoặc adapter phía server nên chuyển chúng thành authorities có tiền tố đúng theo policy đang dùng:

~~~java
// MẢNH CODE: roles là tập String lấy từ nguồn tin cậy ở server.
List<GrantedAuthority> mapped = roles.stream()
    .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
    .toList();
~~~

Đoạn mảnh này cần import `java.util.List`, `GrantedAuthority` và `SimpleGrantedAuthority`, cùng biến `roles` từ kho dữ liệu đáng tin. Nó **không** được dùng với `roles` đọc từ JSON/header mà client tự gửi. Trước khi thêm tiền tố, hãy xác nhận dữ liệu đang lưu chưa có `ROLE_` để tránh tạo `ROLE_ROLE_ADMIN`.

Nếu dữ liệu có một cột `role_name` và một cột `permission_code`, nên tách mapping rõ ràng:

~~~text
role_name="ADMIN" -> "ROLE_ADMIN"
permission_code="DOCUMENT_READ" -> "DOCUMENT_READ"
oauth_scope="reports.read" -> "SCOPE_reports.read"
~~~

Với mô hình nhiều tenant, `ROLE_ADMIN` ở tenant A **không mặc định** được truy cập dữ liệu tenant B. Một authority chung chỉ nói về *nhóm quyền*; access control theo tài nguyên/tenant phải kiểm tra thêm ID tenant đáng tin tại service hoặc policy. Không chỉ dựa vào tên role để xác nhận ownership.

### Không chấp nhận quyền từ client

Các mẫu như sau đều là **sai**:

~~~java
// PHẢN VÍ DỤ: KHÔNG cấp role từ input HTTP.
String role = request.getHeader("X-Role");
return User.withUsername(username)
    .password(passwordHash)
    .authorities(role)
    .build();
~~~

Nếu user có thể tự đặt `X-Role: ROLE_ADMIN` thì người đó có thể tự nâng quyền. Đường tin cậy đúng là: server xác minh danh tính bằng credential đã được kiểm tra → truy vấn/cấp authorities từ nguồn quyền có kiểm soát → Spring Security authorization đối chiếu.

Với JWT, chỉ tin scopes/roles từ token sau khi đã kiểm tra **chữ ký, thuật toán, issuer, audience, expiration** và các claim liên quan. Có thể cần converter để đặt tên `SCOPE_` hay `ROLE_` theo chính sách; không copy claims chưa xác minh sang `Authentication`.

## 13. Role hierarchy, ROLE_ prefix và cấu hình tùy biến

### Role hierarchy không tự động tồn tại

Nếu một tổ chức định nghĩa ADMIN “bao gồm” USER, Spring Security chỉ biết điều đó khi:

- Bạn thực sự cấp cả `ROLE_ADMIN` và `ROLE_USER` cho user; **hoặc**
- Bạn cấu hình một **RoleHierarchy** và bảo đảm chính thành phần `AuthorizationManager` của HTTP và các policy liên quan sử dụng hierarchy ấy.

Ví dụ mô tả quan hệ:

~~~text
ROLE_ADMIN > ROLE_OPS
ROLE_OPS   > ROLE_USER
~~~

Đây là **quy tắc nghiệp vụ có thể cấu hình**, không phải mặc định. Một số API/hook để đưa `RoleHierarchy` vào Spring Security đã thay đổi qua các phiên bản; do đó hãy test request thực, không chỉ định nghĩa một bean rồi giả định mọi checker kể cả method security đều dùng.

Khi phân quyền đặc thù, có thể **cấp permissions cụ thể cho role** lúc tạo `Authentication`, thay vì dựa vào hierarchy. Cách đó làm `hasAuthority("DOCUMENT_READ")` nhất quán giữa authorization và security audit. Đừng “thêm ROLE_ADMIN vào mọi account” để chữa một lỗi 403.

### Tùy chỉnh tiền tố ROLE_

Spring Security có khái niệm `GrantedAuthorityDefaults` để điều chỉnh default role prefix trong các **thành phần phù hợp**, ví dụ một số cơ chế expression/method authorization. Tuy nhiên không nên khẳng định cứ khai báo một bean đổi prefix thì **mọi** lời gọi `hasRole` trong `authorizeHttpRequests` đều lập tức dùng prefix mới: cơ chế DSL dựa trên `AuthorityAuthorizationManager` có behavior cụ thể tùy API/phiên bản.

Một cách đơn giản, dễ kiểm thử khi phải dùng hệ thống authority prefix không chuẩn là **sử dụng `hasAuthority("EXACT_STRING")`** tại HTTP rule, và ghi rõ format mà provider phát ra. Nếu hệ thống chọn `ROLE_` mặc định, dùng `hasRole("ADMIN")` là biểu đạt ý định rõ ràng, không tự chế prefix.

### Dùng hasAuthority hay hasRole khi có nhiều hệ thống?

- Role chỉ có ý nghĩa trong ứng dụng: `hasRole("ADMIN")` với mapper thống nhất `ROLE_ADMIN`.
- Permission từ policy server: `hasAuthority("INVOICE_APPROVE")`.
- OAuth2/JWT scope: thường `hasAuthority("SCOPE_invoice.approve")`, tùy converter.
- Role/authority từ SSO/LDAP: xác minh format thực tế trước khi chọn API. Không suy rằng mọi nhóm directory được tự động dịch thành `ROLE_...`.

## 14. Phân quyền theo path có giới hạn gì?

Chỉ một rule `/orders/**.hasRole("ADMIN")` không đủ bảo vệ mọi kiểu dữ liệu. HTTP authorization thường giải quyết **truy cập vào loại endpoint**, còn phân quyền đối tượng cụ thể cần điều kiện sâu hơn:

- **IDOR/BOLA:** user có `ORDER_READ` không tự có quyền đọc **mọi** đơn hàng bằng cách đổi ID.
- **Tenant isolation:** một admin của tenant A không phải admin toàn hệ thống; cần kiểm tra tenant và resource ownership từ nguồn đáng tin.
- **HTTP method override:** hãy test `POST`, `PUT`, `PATCH`, `DELETE` và handler mapping để tránh route ghi dữ liệu lọt qua rule đọc.
- **Forward/include/error dispatch:** ứng dụng có dispatcher types khác nhau; kiểm tra việc phân quyền khi sử dụng internal forwards, error pages và custom servlet filters. Đừng đặt permitAll quá rộng chỉ để thông báo lỗi render được.
- **Nhiều SecurityFilterChain:** chain đầu tiên match sẽ xử lý; cùng URL có thể chịu policy khác tùy `securityMatcher` và `@Order`. Không đủ chỉ nhìn một đoạn `authorizeHttpRequests` nếu request đi qua chain khác.
- **Static resources và health:** quyết định rõ công khai những route nào; `permitAll()` trên nguồn tài nguyên công khai khác với bỏ qua hoàn toàn security filter chain.
- **Custom AuthenticationProvider:** nếu provider tạo authenticated result nhưng cấp thiếu/nhầm authorities, role checker sẽ làm đúng trên **dữ liệu sai**. Phải test cả bước cấp authorities.

### Tách role permission khỏi feature flag

Một feature flag cho phép hiện nút “Chỉnh sửa” chỉ là điều khiển UI; API vẫn phải kiểm tra `ITEM_WRITE`. Ngược lại, một `403` không có nghĩa frontend phải luôn ẩn hoàn toàn tài nguyên; ứng dụng có thể hiển thị trạng thái “không đủ quyền” và quy trình xin quyền có kiểm soát.

### hasAnyAuthority có thể gây overgrant

Ví dụ nhiều người viết:

~~~java
.requestMatchers("/payments/**")
    .hasAnyAuthority("PAYMENTS_VIEW", "PAYMENTS_REFUND")
~~~

Nếu `/payments/refund` được bảo vệ bởi rule này và chưa có rule đặc thù trước đó, một user chỉ có `PAYMENTS_VIEW` cũng có thể đi vào handler hoàn tiền — một lỗi phân quyền nghiêm trọng. Nên tách:

~~~java
.requestMatchers(HttpMethod.POST, "/payments/refund")
    .hasAuthority("PAYMENTS_REFUND")
.requestMatchers(HttpMethod.GET, "/payments/**")
    .hasAnyAuthority("PAYMENTS_VIEW", "PAYMENTS_REFUND")
.requestMatchers("/payments/**").denyAll()
~~~

Cấu hình này là **mảnh minh họa**, chưa gồm bean/import/method controller. Lưu ý POST còn cần CSRF trong browser cookie chain. Mô hình “rule ghi cụ thể trước, rule đọc rộng sau, những method khác deny” dễ kiểm tra hơn một wildcard cấp quyền quá rộng.

## 15. Hướng chẩn đoán 403 theo đúng trình tự

Khi đã có rule nhưng user bị 403, hãy xác minh lần lượt:

1. **Đúng security chain chưa?** `FilterChainProxy` chọn chain nào cho URL và method? Có `securityMatcher` hoặc `@Order` khác không?
2. **User thật sự authenticated chưa?** `Authentication` đến từ form/session, HTTP Basic, bearer JWT hay mock? Có phải `AnonymousAuthenticationToken` không?
3. **Authorities chính xác là gì?** Đếm/nội dung từ server-side principal sau xác thực; không in password/token vào log.
4. **Rule nào match đầu tiên?** Có wildcard `/**`, `permitAll`, `authenticated` hoặc deny trước rule bạn mong muốn không?
5. **Chuỗi role có prefix chưa?** `hasRole("ADMIN")` tìm `ROLE_ADMIN` trong cấu hình mặc định; `hasAuthority("ADMIN")` tìm `ADMIN`.
6. **Hàm hasAny... có OR như mong đợi không?** Không có quyền A hoặc B thì fail; nếu muốn cả hai thì policy hiện tại có sai semantics không?
7. **HTTP method có khớp không?** GET được, POST chưa chắc; verify `HttpMethod` rule cụ thể.
8. **CSRF có chặn trước không?** Với POST/PUT/PATCH/DELETE trong web chain dùng cookie, gửi token hợp lệ để kiểm tra phần authorization.
9. **Service-level rule có chặn không?** Có `@PreAuthorize`, `@PostAuthorize` hoặc kiểm tra tenant/ownership phía service không?
10. **Biến thể URL có match khác không?** Context path, trailing slash, case, encoded path, reverse proxy và Servlet dispatch type phải được test theo deployment thực.

Không được sửa 403 bằng cách chuyển `hasRole("ADMIN")` thành `permitAll()` để request “chạy được”. Việc đó vô hiệu ranh giới bảo mật thay vì sửa nguyên nhân sai mapping/policy.

## 16. Kiểm thử cả “không có quyền” lẫn “đủ quyền”

Một bộ test phân quyền đáng tin thường có ma trận:

| Người dùng (server cấp) | GET /admin/panel | GET /ops/panel | GET /docs/file | GET /billing/invoices | GET /api/reports/42 | POST /api/reports/42 với CSRF |
| --- | --- | --- | --- | --- | --- | --- |
| Alice: ROLE_ADMIN, DOCUMENT_READ, BILLING_WRITE, scope read/write | 200 | 200 | 200 | 200 | 200 | 200 |
| Bob: ROLE_OPS, BILLING_READ | 403 | 200 | 403 | 200 | 403 | 403 |
| Cara: DOCUMENT_READ, scope read | 403 | 403 | 200 | 403 | 200 | 403 |
| Dave: ROLE_USER | 403 | 403 | 403 | 403 | 403 | 403 |

Các giá trị `200` và `403` được nêu cho controller/configuration demo ở trên, khi **user được xác thực với đúng fixture** và request unsafe mang CSRF token phù hợp. Nếu request chưa đăng nhập, HTTP status có thể khác vì entry point.

Thực tế nên bổ sung:

- Positive và negative test cho **từng rule**.
- Test **method chưa khai báo** không bị fallback cấp quyền quá rộng.
- Test **anonymous** để xác nhận người chưa login không đi được vào tài nguyên bảo vệ.
- Test role → GrantedAuthority mapper, JWT authority converter và cấu hình RoleHierarchy nếu có.
- Test request từ nhiều chain (API JWT / UI session), nếu ứng dụng kết hợp.
- Test quyền theo tài nguyên: user A không đọc/ghi tài nguyên tenant B dù có cùng role.
- Test chính sách lỗi (403/401/redirect) không lộ dữ liệu nhạy cảm hoặc username enumeration.

### Vì sao không nên assert chỉ status?

Một endpoint có thể trả `403` vì thiếu CSRF, không phải vì role. Một endpoint có thể trả `404` vì controller route không tồn tại, không chứng minh rule phân quyền hoạt động. Một `200` có thể đến từ `permitAll` ở matcher rộng hơn, không phải từ intended authority check.

Vì vậy hãy kiểm tra authentication state, correct request path/method, CSRF, matched rule và nội dung response. Với production security regression, có thể instrument authorization decisions/metrics ở mức không lộ dữ liệu nhạy cảm.

## 17. Những lỗi thường gặp trong code review

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `hasRole("ROLE_ADMIN")` | Có thể lỗi cấu hình vì truyền prefix vào API role. | Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")`. |
| `hasAuthority("ADMIN")` với user chỉ có `ROLE_ADMIN` | 403 vì không khớp chuỗi. | Đồng bộ mapper hoặc dùng API role. |
| `roles("ROLE_ADMIN")` ở `UserBuilder` | Có thể ném lỗi do input đã có prefix. | Dùng `roles("ADMIN")` hoặc `authorities("ROLE_ADMIN")`. |
| `hasAnyAuthority("READ","WRITE")` bảo vệ endpoint WRITE | User chỉ có READ cũng có thể vào. | Dùng `hasAuthority("WRITE")` cho ghi. |
| `hasAnyRole("A","B")` để yêu cầu cả A và B | Chỉ cần một role là đủ. | Dùng AND/custom manager. |
| Coi ROLE_ADMIN tự có ROLE_USER | Admin có thể bị 403 ở user path. | Cấp cả hai hoặc cấu hình hierarchy. |
| Quyền cấp từ header/body client | Attacker tự nâng quyền. | Lấy authorities từ store/trusted claims sau authentication. |
| Đặt `anyRequest().authenticated()` trước rule nhạy cảm | Matcher rộng có thể làm mất policy role. | Rule cụ thể trước, fallback sau. |
| Không xét HttpMethod | Người có quyền đọc có thể vào endpoint ghi. | Ràng buộc method và deny default. |
| POST test không kèm CSRF | 403 không chứng minh thiếu authority. | Dùng `csrf()` trong MockMvc. |
| Chỉ dùng `@WithMockUser` test | Bỏ sót lỗi mapping user store/JWT converter. | Có test end-to-end credential → authorities. |
| Chỉ kiểm tra URL, không kiểm tra ownership | IDOR/BOLA và cross-tenant access. | Kiểm tra resource-level authorization. |
| Trông vào cấu hình role prefix ở một chỗ | Các checker khác có thể dùng semantics khác. | Kiểm tra đúng Java DSL, method/security API phiên bản mục tiêu. |
| Không có fallback deny cho route mới | URL mới có thể được truy cập ngoài ý muốn. | Dùng `anyRequest().denyAll()` khi hợp nghiệp vụ, test coverage. |

## 18. Bài tập tự kiểm tra

**Bài 1.** User có `ROLE_STAFF` và `DOCUMENT_READ`, không có `ROLE_MANAGER`. Rule `hasAnyRole("MANAGER","STAFF")` có cho phép không?  
**Đáp án:** Có, vì `ROLE_STAFF` được cấp và hasAnyRole dùng OR.

**Bài 2.** User có `ROLE_ADMIN` nhưng không có `ADMIN`. `hasAuthority("ADMIN")` có khớp không?  
**Đáp án:** Không. Kiểm tra authority là **exact string**.

**Bài 3.** Khi nào `hasRole("ADMIN")` tương đương `hasAuthority("ROLE_ADMIN")`?  
**Đáp án:** Khi quy ước role prefix chuẩn `ROLE_` được dùng và không có custom rule semantics làm thay đổi cách kiểm tra. Đây là trường hợp thường gặp trong `authorizeHttpRequests`.

**Bài 4.** Muốn cả `INVOICE_VIEW` **và** `INVOICE_APPROVE` thì chọn `hasAnyAuthority("INVOICE_VIEW","INVOICE_APPROVE")` đúng không?  
**Đáp án:** Sai. Hàm này dùng OR; cần AND theo policy thích hợp.

**Bài 5.** User có `SCOPE_reports.read` nhưng không có `SCOPE_reports.write`. Với method-specific rules, GET và POST báo cáo có kết quả gì?  
**Đáp án:** GET được phép, POST không được phép (khi POST đi qua CSRF hợp lệ để tới authorization).

**Bài 6.** Vì sao `ROLE_ADMIN` không mặc nhiên thỏa `hasRole("USER")`?  
**Đáp án:** Vì danh sách GrantedAuthority không có `ROLE_USER` nếu ứng dụng chưa cấp role ấy hoặc cấu hình hierarchy có hiệu lực.

**Bài 7.** Một test POST trả `403` vì thiếu CSRF. Có thể kết luận rule `hasAuthority("WRITE")` hoạt động đúng không?  
**Đáp án:** Không. Request có thể bị CsrfFilter chặn trước authorization. Phải dùng token hợp lệ và test user có/không có WRITE.

**Bài 8.** Khi có nhiều `SecurityFilterChain`, tại sao một rule đúng ở chain A vẫn không bảo vệ URL?  
**Đáp án:** Request có thể match chain B trước; phải xác định `securityMatcher` và thứ tự `@Order` của từng chain.

**Bài 9.** Nếu frontend ẩn nút “Refund” cho user thiếu quyền, backend có thể bỏ `hasAuthority("PAYMENTS_REFUND")` không?  
**Đáp án:** Không. Client/UI có thể bị sửa hoặc gọi HTTP trực tiếp; enforcement phải ở server và có kiểm tra ownership khi cần.

**Bài 10.** Nên chọn `hasRole` hay `hasAuthority` cho một scope đã được đổi thành `SCOPE_orders.read`?  
**Đáp án:** `hasAuthority("SCOPE_orders.read")`, vì nó tìm đúng chuỗi scope được server cấp, không thêm `ROLE_`.

## 19. Checklist kết thúc

- [ ] Đã phân biệt authentication, HTTP authorization và resource-level permission.
- [ ] Biết chính xác `Authentication.getAuthorities()` chứa những chuỗi gì.
- [ ] `hasRole("X")` được hiểu theo `ROLE_X` với prefix mặc định, không truyền sẵn `ROLE_`.
- [ ] `hasAnyRole` và `hasAnyAuthority` đều dùng **OR**.
- [ ] `hasAuthority` không tự thêm `ROLE_` và phù hợp với permissions/scopes theo chuỗi chính xác.
- [ ] Role/permission được cấp từ nguồn server tin cậy, không từ input client.
- [ ] URL-specific và method-specific matchers đứng trước fallback rộng.
- [ ] Endpoint ghi được bảo vệ bằng WRITE, không phải READ OR WRITE.
- [ ] Có deny default cho các method/URL chưa được phê duyệt nếu phù hợp kiến trúc.
- [ ] CSRF/session/token policy vẫn được kiểm thử đúng threat model.
- [ ] Có positive/negative integration tests bằng `MockMvc` và test mapper/claims.
- [ ] Nếu dùng role hierarchy hoặc custom prefix, đã test behavior thật trên phiên bản Spring Security đang chạy.
- [ ] Có kiểm tra tenant, ownership hoặc phân quyền bản ghi riêng với các API cần thiết.

**Ghi nhớ:** `hasRole` và `hasAnyRole` là cú pháp thuận tiện cho **role với tiền tố `ROLE_`**; `hasAuthority` và `hasAnyAuthority` là **so chuỗi GrantedAuthority nguyên văn**. Hai hàm `hasAny...` dùng **OR**, không phải AND. Trong HTTP authorization, quyết định cuối cùng còn phụ thuộc **đúng SecurityFilterChain, đúng path/method, đúng thứ tự matcher và danh sách authorities đã được xác minh phía server**.
