# JEE pre-authentication và danh tính do Servlet Container cung cấp

> **Phạm vi:** Spring Security **Servlet stack** (Spring MVC, Spring Boot 3.x, Spring Security 6.x, Java 17+, Jakarta Servlet API). Bài tập trung vào cơ chế **container-managed authentication** của Java EE/Jakarta EE được Spring Security dùng làm **pre-authentication**. Điểm cần nắm là **Servlet Container xác thực người dùng trước**, còn Spring Security tiếp nhận danh tính và vai trò đã được Container xác lập để xây `Authentication`, thực hiện phân quyền và tích hợp với ứng dụng. Bài không dùng WebFlux hoặc coi HTTP header do client tự gửi là danh tính đáng tin cậy.

## 1. Pre-authentication nghĩa là gì?

Thông thường trong Spring Security, ứng dụng tự kiểm tra mật khẩu, Bearer token hoặc một phương thức xác thực khác thông qua các filter/providers. Với **pre-authentication**, một hệ thống khác **đã xác thực** HTTP request trước khi Spring Security xử lý. Spring Security không nhận lại mật khẩu để kiểm tra; thay vào đó nó đọc **principal** và (nếu có) **roles/authorities** từ một nguồn đã được tin cậy.

Trong trường hợp JEE, nguồn tin cậy là **Servlet Container / application server** (chẳng hạn một container được cấu hình realm, login mechanism và các security constraints), sử dụng API chuẩn của `HttpServletRequest`. Spring Security dùng các lớp pre-authentication để đưa thông tin này vào `SecurityContext`.

Ví dụ tình huống hợp lý:

1. Người dùng truy cập ứng dụng WAR triển khai vào một application server đã cấu hình xác thực qua realm/SSO.
2. Container buộc user xác thực theo cơ chế được quản trị viên cấu hình (BASIC, FORM, client certificate hoặc cơ chế tích hợp của container, tùy môi trường).
3. Sau khi thành công, container có thể cung cấp principal và vai trò qua `HttpServletRequest`.
4. Spring Security nhận danh tính đã xác thực, ánh xạ vai trò và kiểm tra quy tắc `hasRole` / `hasAuthority` trước khi cho gọi controller.

**Pre-authenticated không có nghĩa "mọi request đều tin được".** Nếu container không thực sự xác thực request hoặc ứng dụng có đường truy cập đi vòng qua lớp xác thực, dữ liệu danh tính không đủ tin cậy. Kiểm soát trust boundary trước khi dùng là điều kiện tiên quyết.

### Những thành phần nào chịu trách nhiệm?

| Thành phần | Trách nhiệm |
| --- | --- |
| **Servlet Container** | Thực thi login mechanism/realm, nhận diện user và vai trò theo cấu hình của container. |
| `HttpServletRequest.getUserPrincipal()` | API cho biết principal liên kết với request từ phía container; có thể trả `null` nếu chưa xác thực. |
| `HttpServletRequest.getRemoteUser()` | Tên user đã được container xác thực, hoặc `null` nếu không có. |
| `HttpServletRequest.getAuthType()` | Kiểu xác thực do container xác lập, ví dụ `BASIC_AUTH` hoặc `FORM_AUTH`; có thể `null`. |
| `HttpServletRequest.isUserInRole(role)` | Kiểm tra user có role theo cấu hình container hay không. |
| `J2eePreAuthenticatedProcessingFilter` | Spring Security lấy principal đã được container xác thực từ Servlet request và tạo pre-authentication token. |
| `J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` | Chuyển thông tin role từ `isUserInRole` thành authorities theo danh sách roles đã được cấu hình. |
| `PreAuthenticatedAuthenticationProvider` | Xử lý token pre-authentication trong `AuthenticationManager`, phối hợp với user-details service tương ứng. |
| `SecurityContext` / `Authentication` | Biểu diễn principal và granted authorities mà các thành phần Spring Security dùng sau khi xác thực. |

## 2. Phân biệt container authentication và Spring Security authentication

**Container authentication** trả lời: *Ai đã được container xác thực, và container cho biết user thuộc các vai trò nào?*

**Spring Security** dùng thông tin đó để trả lời: *Request hiện tại thuộc principal nào, có những `GrantedAuthority` nào và có được phép vào URL/method này không?*

~~~text
Browser
  |
  v
Servlet Container (Realm + auth mechanism + security constraints)
  |  thành công: request có Principal, roles
  v
Servlet Filter Chain
  |
  +-- Spring Security / FilterChainProxy
        |
        +-- J2eePreAuthenticatedProcessingFilter
        |      đọc request.getUserPrincipal()
        |      đọc role mapping từ request.isUserInRole(...)
        |      tạo PreAuthenticatedAuthenticationToken
        |
        +-- AuthenticationManager
        |      PreAuthenticatedAuthenticationProvider
        |      UserDetails/GrantedAuthority từ trusted details
        |
        +-- SecurityContext chứa Authentication
        +-- AuthorizationFilter kiểm tra quyền
        |
        v
      Controller / Service
~~~

Thứ tự filter chính xác còn phụ thuộc phiên bản và cấu hình; đây là luồng khái niệm. Tên lớp vẫn dùng tiền tố **J2ee** vì lịch sử API, dù Spring Boot 3.x sử dụng namespace **`jakarta.servlet.*`** thay cho `javax.servlet.*`.

### Vì sao không dùng cùng lúc hai nơi kiểm tra mật khẩu?

Nếu container đã chịu trách nhiệm xác thực request bằng realm/SSO, việc cấu hình thêm Spring form login như một nguồn xác thực riêng cho **cùng một protected path** có thể gây hai login flow, redirect khác nhau hoặc principal/role mapping không nhất quán. Hãy xác định rõ bên nào là **nguồn xác thực chính**, bên nào chỉ thực thi phân quyền. Những khu vực khác nhau có thể có security filter chains riêng, nhưng phải định nghĩa phạm vi và trust boundary tường minh.

## 3. Các API Servlet cung cấp danh tính

Trong code chạy **trước khi Spring Security bọc request**, các API container thường được dùng như sau:

~~~java
Principal principal = request.getUserPrincipal();
String username = request.getRemoteUser();
String authType = request.getAuthType();
boolean isUser = request.isUserInRole("USER");
boolean isAdmin = request.isUserInRole("ADMIN");
~~~

Cần import `java.security.Principal` và `jakarta.servlet.http.HttpServletRequest`; đây là **đoạn mã minh họa trong filter/controller có biến request**, không phải chương trình Java độc lập.

Giải thích:

- `getUserPrincipal()` trả một `Principal` hoặc `null`. Không suy ra rằng principal chắc chắn là chuỗi, email, hay object thuộc một nhà cung cấp SSO cụ thể.
- `getRemoteUser()` thường cho biết tên user do container xác thực; cách định dạng tên phụ thuộc realm.
- `getAuthType()` giúp quan sát cơ chế mà container thông báo; **không tự chứng minh** request an toàn nếu container hoặc đường mạng bị cấu hình sai.
- `isUserInRole("ADMIN")` hỏi chính container xem user có role `ADMIN`. Những vai trò này cần được khai báo/ánh xạ trong môi trường triển khai; chúng không tự xuất hiện từ tên nhóm bất kỳ của LDAP/IdP.

**Lưu ý rất quan trọng khi debug:** sau khi đi qua Spring Security, `HttpServletRequest` có thể được bọc bởi `SecurityContextHolderAwareRequestWrapper`, làm các method bảo mật trên request phản ánh **Spring Security Authentication** thay vì raw container object. Vì vậy nếu muốn xác thực container đã thật sự cung cấp principal/role, hãy quan sát ở container hoặc tại filter chạy **trước Spring Security**; đừng chỉ gọi `request.getUserPrincipal()` ở controller rồi khẳng định đó là object nguyên gốc của container.

Trong Spring application code, nguồn xem danh tính sau khi pre-auth được xử lý là:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication != null && authentication.isAuthenticated()) {
    String name = authentication.getName();
    boolean admin = authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_ADMIN"));
}
~~~

Đoạn này cần import `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.SecurityContextHolder`. Nó chỉ đọc security context; giá trị `isAuthenticated()` phải được kết hợp với chính sách không coi anonymous user là một user hợp lệ. Trong controller được bảo vệ bằng `.authenticated()`, Authentication được Spring Security xử lý theo rule tương ứng.

## 4. Vai trò của J2eePreAuthenticatedProcessingFilter

Lớp `org.springframework.security.web.authentication.preauth.j2ee.J2eePreAuthenticatedProcessingFilter` dựa trên `AbstractPreAuthenticatedProcessingFilter`. Nó không hiển thị form login, không tự gửi người dùng tới Identity Provider và không thay container kiểm tra password. Nó **trích xuất principal** đã được container cung cấp, tạo `PreAuthenticatedAuthenticationToken` và chuyển vào cơ chế authentication của Spring.

Cơ chế tiền xác thực gồm hai việc tách biệt:

1. **Nhận diện principal:** lấy từ `HttpServletRequest.getUserPrincipal()`.
2. **Cấp authorities:** lấy từ thông tin container role thông qua details source hoặc qua nguồn `UserDetailsService` được tin cậy tùy cấu hình.

`J2eeBasedPreAuthenticatedWebAuthenticationDetailsSource` gọi `request.isUserInRole(roleName)` với mỗi role trong danh sách **mappable roles**. Các vai trò phù hợp được chuyển thành `GrantedAuthority`; mapper mặc định thường thêm tiền tố `ROLE_` vào role name để tương thích với `hasRole("USER")` của Spring Security.

Ví dụ:

~~~text
Container đã xác thực user = alice
isUserInRole("USER")  = true
isUserInRole("ADMIN") = false

Spring Security Authentication:
  principal = alice
  authorities = [ROLE_USER]

Rule hasRole("USER")  -> cho qua
Rule hasRole("ADMIN") -> bị từ chối
~~~

Đây là **tình huống giả định**, không phải stdout hoặc log đầu ra mặc định của framework. Điều kiện ánh xạ role cần khớp cấu hình thực tế của container và ứng dụng.

### Các lớp liên quan

`PreAuthenticatedAuthenticationProvider` có thể dùng `PreAuthenticatedGrantedAuthoritiesUserDetailsService` để sử dụng authorities được gói trong authentication details. Trong triển khai tùy chỉnh, có thể dùng `UserDetailsByNameServiceWrapper` để lấy thêm thông tin user theo username. Đây là **cách bổ sung authorities/user details trong Spring**, không phải xác thực lại password mặc định.

Nếu user đã bị vô hiệu hóa trong hệ thống nghiệp vụ nhưng container vẫn cho đăng nhập, ứng dụng phải quyết định rõ cách kiểm tra trạng thái business account trước khi cho phép thao tác; đừng nhầm “container xác thực thành công” với “mọi quyền nghiệp vụ đều hợp lệ”.

## 5. Cấu hình Spring Security 6 bằng HttpSecurity.jee

Đây là ví dụ **Java cấu hình đầy đủ** trong ứng dụng Spring Boot 3.x, có `spring-boot-starter-web` và `spring-boot-starter-security`. Nó giả định ứng dụng được triển khai vào **Servlet Container đã cấu hình xác thực JEE** và các role `USER`, `ADMIN`.

File `JeeSecurityConfig.java` trong package được Spring Boot quét:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JeeSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/app/admin/**").hasRole("ADMIN")
                .requestMatchers("/app/**").hasAnyRole("USER", "ADMIN")
                .anyRequest().denyAll()
            )
            .jee(jee -> jee
                .mappableRoles("USER", "ADMIN")
            );

        return http.build();
    }
}
~~~

**Ý nghĩa từng phần:**

- `.jee(...)` bật tích hợp **JEE container pre-authentication**, bổ sung bộ lọc `J2eePreAuthenticatedProcessingFilter` và provider liên quan theo Spring Security.
- `mappableRoles("USER", "ADMIN")` khai báo **những role nào được tra từ container** để chuyển sang granted authorities. Với mapping vai trò thông dụng, authorities tương ứng là `ROLE_USER` và `ROLE_ADMIN`.
- `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN` (theo convention mặc định). Đừng viết `hasRole("ROLE_ADMIN")` khi dùng cấu hình thêm tiền tố mặc định.
- `requestMatchers("/app/admin/**")` được xét trước matcher `/app/**`, tránh matcher rộng che rule admin; `anyRequest().denyAll()` khiến những path ngoài phạm vi chỉ định bị từ chối. `/health` là ví dụ endpoint kiểm tra sức khỏe được mở ở **Spring layer**, nhưng vẫn có thể bị container constraint chặn nếu container bảo vệ toàn bộ app.
- **Không** gọi `formLogin()` hoặc `httpBasic()` trong ví dụ. Cơ chế login BASIC/FORM, nếu có, là do **Container** cấu hình trong tình huống này.
- Không tắt CSRF chỉ vì đang dùng JEE. Nếu web app sử dụng session/cookie tự gửi, vẫn phải phân tích CSRF cho các HTTP method thay đổi trạng thái; Spring Security có bảo vệ CSRF mặc định nếu không vô hiệu hóa.

### Cần cấu hình gì ở Servlet Container?

Chỉ thêm `.jee(...)` **không biến** một embedded Tomcat mặc định thành container có realm, login mechanism và security constraints hoàn chỉnh. Nếu `getUserPrincipal()` là `null`, filter không thể tự tạo danh tính thật từ không khí.

Đối với **WAR được deploy vào app server**, có thể khai báo security constraints và role names bằng `web.xml`, đồng thời quản trị viên phải cấu hình realm/user store/SSO trong server. Phần này là **hợp đồng của container**, không phải cấu hình Spring Security tự sinh.

## 6. Ví dụ web.xml của container-managed authentication

Đây là một ví dụ descriptor **Jakarta Servlet 6.0** (phù hợp Jakarta EE 10 khi container hỗ trợ). Đặt tại `src/main/webapp/WEB-INF/web.xml` trong ứng dụng WAR. Container phải có realm triển khai thực tế, user và role mapping; descriptor không tự tạo accounts.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <security-constraint>
        <web-resource-collection>
            <web-resource-name>Protected Application</web-resource-name>
            <url-pattern>/app/*</url-pattern>
        </web-resource-collection>
        <auth-constraint>
            <role-name>USER</role-name>
            <role-name>ADMIN</role-name>
        </auth-constraint>
    </security-constraint>

    <login-config>
        <auth-method>BASIC</auth-method>
        <realm-name>CompanyRealm</realm-name>
    </login-config>

    <security-role>
        <role-name>USER</role-name>
    </security-role>
    <security-role>
        <role-name>ADMIN</role-name>
    </security-role>
</web-app>
~~~

Đây là **ví dụ cấu hình**, không phải một ứng dụng chạy độc lập. Giải thích:

1. Container bảo vệ các URL dưới `/app/*` và yêu cầu user hợp lệ thuộc một trong hai role `USER` hoặc `ADMIN`. Nếu user không đạt container constraint, request có thể bị container từ chối **trước Spring Security**.
2. `<auth-method>BASIC</auth-method>` chọn HTTP Basic **do container triển khai**. Đây không phải `http.httpBasic()` của Spring Security. Môi trường production phải dùng HTTPS để tránh lộ credential và có chính sách login phù hợp.
3. `CompanyRealm` là tên realm minh họa; container phải được cấu hình realm thật và ánh xạ nhóm/người dùng ra các JEE role tương ứng. File XML không chứa mật khẩu hay một user mặc định.
4. Container role `ADMIN` có thể pass constraint, nhưng Spring vẫn áp dụng rule tách biệt: `/app/admin/**` yêu cầu `ROLE_ADMIN`.
5. Matcher `/app/*` của descriptor và `/app/**` của Spring Security dùng **hai hệ thống pattern khác nhau**; cần kiểm thử các URL thực tế, nhất là servlet mapping, context path và những route nested.
6. Vị trí/tính hiệu lực descriptor có thể khác theo bản container/deployment. Với Boot executable JAR dùng embedded server, không thể sao chép file này rồi coi container auth đã sẵn sàng; phải cấu hình embedded container, realm và servlet security integration thực tế.

**Sự phân biệt cần nhớ:** container quyết định ai được vào lớp bảo vệ trước, Spring Security có thể **siết chặt hơn** theo URL/method roles, nhưng Spring không thể cứu ứng dụng khỏi việc container để một đường nhạy cảm đi vòng xác thực nếu application trust model sai.

## 7. Xem danh tính trong controller Spring MVC

Trong controller **sau Spring Security**, nên đọc `Authentication` hoặc `@AuthenticationPrincipal` để lấy danh tính mà Spring thực sự dùng phân quyền. Ví dụ `IdentityController.java`:

~~~java
package com.example.web;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/app/identity")
    public Map<String, Object> identity(Authentication authentication) {
        List<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();

        return Map.of(
                "username", authentication.getName(),
                "authorities", authorities
        );
    }
}
~~~

Code này yêu cầu các dependency Spring MVC/Security đã được cấu hình và giả định `/app/identity` đã qua pre-auth và rule `hasAnyRole("USER", "ADMIN")`. Với một user **alice** có role USER đã được container cung cấp và mapping đúng, response ví dụ **có thể** là:

~~~json
{
  "username": "alice",
  "authorities": ["ROLE_USER"]
}
~~~

Response trên là **tình huống minh họa**, không phải kết quả luôn cố định của mọi container: tên principal và danh sách roles tùy realm/provider và custom mapping.

**Bảo mật:** endpoint này chỉ dùng để hiểu và kiểm thử tích hợp. Trong production tránh phơi bày authorities và chi tiết danh tính không cần thiết ra client; nếu trả thông tin, phải kiểm soát quyền truy cập. Không dựa vào một field gửi từ client (query param, header `X-User`, JSON body) để tạo `Authentication`.

### Có thể dùng Spring Method Security không?

Có. Nếu dự án bật method security và đã có authorities từ JEE mapping, các annotation như `@PreAuthorize("hasRole('ADMIN')")` có thể áp dụng bên cạnh URL authorization. Cần có `@EnableMethodSecurity` ở cấu hình liên quan và bảo đảm method thực sự được gọi qua Spring proxy; method security không tự thay thế container authentication.

## 8. Role mapping: nguyên nhân thường gặp của 403

Container role và Spring Security authority không tự là một chuỗi giống nhau.

Ví dụ container cung cấp:

~~~text
getUserPrincipal().getName() = alice
request.isUserInRole("USER")  = true
request.isUserInRole("ADMIN") = false
~~~

Khi `jee.mappableRoles("USER", "ADMIN")` phù hợp, Spring có thể tạo `GrantedAuthority("ROLE_USER")` và rule `hasRole("USER")` sẽ thành công. Nếu container trả role khác tên, như `TEAM_MEMBER` thay vì `USER`, thì `isUserInRole("USER")` có thể false, Spring không có `ROLE_USER` và sẽ trả 403 khi truy cập URL yêu cầu USER.

### Cách xử lý đúng

- Xem **tên role được container công nhận** trong realm và security role declarations.
- Kiểm tra trực tiếp `request.isUserInRole(...)` ở vị trí tin cậy trước Spring request wrappers.
- Cấu hình `mappableRoles(...)` tương ứng; nếu các authority đã được đặt tiền tố hoặc phải dùng convention riêng, xem xét `mappableAuthorities(...)` hay custom mapping với hiểu biết rõ về prefix.
- Kiểm tra sự khác nhau giữa `hasRole("ADMIN")` và `hasAuthority("ROLE_ADMIN")` theo quy ước của Spring.
- Với role mapping nhiều tenant/nhóm nội bộ, có thể nạp thêm authorities qua trusted service. Tuyệt đối không nâng quyền chỉ bằng string/role do user tự nhập.

Đừng “sửa nhanh” bằng cách chuyển tất cả `/app/**` sang `permitAll()`; nó chỉ che khuất lỗi mapping và làm mất ranh giới authorization.

## 9. Container xác thực rồi, session và logout xử lý ra sao?

Tác vụ **login** thuộc container hoặc hệ thống SSO phía trước; điều này ảnh hưởng logout, session lifetime và principal refresh.

- **Session:** container có thể dùng HTTP session, BASIC per request, SSO cookie hoặc cơ chế khác tùy app server. Spring Security còn có `SecurityContext`, chính sách persistence và session management của nó. Hai vòng đời phải được hiểu cùng nhau; không suy ra cách container hoạt động chỉ từ việc có `JSESSIONID`.
- **Logout:** `http.logout()` của Spring không tự bảo đảm hủy phiên SSO bên ngoài hoặc đăng xuất khỏi container realm. Ở Servlet API có `HttpServletRequest.logout()` trong các môi trường hỗ trợ, nhưng kết quả cụ thể phụ thuộc container; đôi khi cần tích hợp logout với IdP/SSO gateway. Không tuyên bố logout toàn cục nếu chưa kiểm thử.
- **Đổi roles trong khi session còn sống:** role trong container có thể được cache; Spring Security context cũng có vòng đời. Khi role bị thu hồi, cần kế hoạch làm mới hoặc invalidation phù hợp, tránh quyền cũ được sử dụng quá lâu.
- **CSRF:** nếu browser tự gửi cookie xác thực, request POST/PUT/PATCH/DELETE vẫn có rủi ro CSRF; giữ cơ chế phòng vệ của Spring Security nếu thích hợp. Login do container quản lý không đồng nghĩa với CSRF không còn.
- **HTTPS:** dùng TLS cho login, cookie, redirects và API; cấu hình `Secure`, `HttpOnly`, `SameSite` phù hợp và đánh giá proxy/forwarded headers.

Không dùng `request.getUserPrincipal() != null` làm bằng chứng đủ để cho phép mọi thao tác nhạy cảm: authorization vẫn phải xét vai trò/quyền nghiệp vụ, resource ownership, trạng thái tài khoản và điều kiện nghiệp vụ.

## 10. JEE pre-auth và header-based pre-auth khác nhau thế nào?

Spring Security cũng có `RequestHeaderAuthenticationFilter`, thường dùng khi proxy/SSO gateway truyền username qua header (ví dụ `SM_USER`). Đây **không phải** cơ chế JEE container authentication mặc định.

| Tiêu chí | JEE container pre-auth | Header-based pre-auth |
| --- | --- | --- |
| Nguồn principal | `HttpServletRequest.getUserPrincipal()` do container đã xác lập. | Header do một hệ thống upstream cung cấp, filter riêng trích xuất. |
| Nguồn roles | `request.isUserInRole(...)` hoặc trusted user-details mapping. | Hệ thống upstream/role provider do ứng dụng cấu hình. |
| Filter Spring | `J2eePreAuthenticatedProcessingFilter`. | `RequestHeaderAuthenticationFilter`. |
| Điều kiện tin cậy | Container đã xác thực và không có đường đi bypass realm/constraints. | Proxy chặn client trực tiếp, xóa header giả và tự đặt header đáng tin cậy. |
| Rủi ro cấu hình | Container không có principal hoặc role mapping sai. | Attacker tự chèn header username và giả mạo user nếu upstream không bảo vệ. |

**Tuyệt đối không tin `X-Remote-User`, `X-User`, `X-Authenticated-User` chỉ vì tên header nghe có vẻ “đã xác thực”.** Một client có thể tự gửi các header đó nếu proxy không khóa chặt. Nếu cần dùng header preauth, hãy xác định ranh giới mạng, TLS/mTLS, strip/overwrite header tại proxy và chặn đường tới app không qua proxy.

Với JEE, điều cần tin là **danh tính được container bảo đảm**, không phải một request attribute/header mà application code tự điền tùy ý.

## 11. Kiểm thử tích hợp đúng cơ chế

### 11.1 Kiểm thử thực tế trên Servlet Container

Dùng một container có realm thật và hai tài khoản: user chỉ có USER và user có ADMIN. Triển khai WAR cùng `web.xml` và Spring Security config đã thống nhất.

| Tình huống | Kỳ vọng |
| --- | --- |
| Chưa đăng nhập, gọi `/app/identity` | Bị container yêu cầu xác thực hoặc từ chối theo login mechanism; không được vào controller với danh tính hợp lệ. |
| Alice có role USER, vào `/app/identity` | Container xác thực; Spring nhận principal; trả `username` và `ROLE_USER` theo mapping. |
| Alice (chỉ USER) vào `/app/admin/report` | Spring `hasRole("ADMIN")` từ chối; thường HTTP 403. |
| Bob có ADMIN, vào `/app/admin/report` | Có thể qua kiểm tra authorization nếu container constraint cũng cho phép và endpoint tồn tại. |
| User container hợp lệ nhưng `isUserInRole("USER")` sai | Spring thiếu authority; có thể trả 403 dù container báo login thành công. |
| Container không phát principal | Pre-auth không có danh tính để lấy; request bị từ chối theo cấu hình, không tự fallback thành user hợp lệ. |

Các kết quả cuối cùng phụ thuộc cả endpoint, container security policy và method-level rules; đây là **kỳ vọng kiểm thử**, không phải transcript chạy thật.

Nếu dùng container BASIC trên HTTPS và tài khoản thử nghiệm, có thể thử thủ công theo cách của môi trường (browser hoặc HTTP client). Không viết mật khẩu thật vào terminal history hoặc tài liệu. Kiểm tra status, challenge/redirect, và ứng dụng **không** xử lý controller khi chưa đủ quyền.

### 11.2 Phân biệt unit test MockMvc với integration test

Spring Security Test có các helper như `with(user("alice").roles("USER"))` để **giả lập Spring Security Authentication** trong MockMvc. Chúng tiện để test authorization ở Controller/Service, nhưng **không chứng minh** Servlet Container đã xác thực, gọi `isUserInRole` chính xác hoặc `J2eePreAuthenticatedProcessingFilter` thực sự nhận principal từ container.

Để kiểm tra JEE pre-auth thật, cần chạy trong một Servlet Container được cấu hình realm/constraints, hoặc viết integration test có mock container request/preauth filter và role mapping đầy đủ. Không coi một unit test với `@WithMockUser` là xác nhận tích hợp SSO/container production đã đúng.

## 12. Chẩn đoán lỗi khi triển khai

| Dấu hiệu | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Mọi request đều 403 | Container không cung cấp principal, app chưa cấu hình realm/constraints, hoặc security chain không áp dụng đúng. | Kiểm tra container auth trước Spring; xem filter chain và `request.getUserPrincipal()` ở pre-Spring boundary. |
| Không hiện login form nào | `.jee()` không tự tạo login page; container login method/realm chưa được cấu hình. | Kiểm tra deployment descriptor và auth mechanism của container. |
| Người dùng đăng nhập được nhưng `hasRole("ADMIN")` luôn sai | `isUserInRole("ADMIN")` false, role names không khớp hoặc mapping prefixes sai. | Kiểm tra container roles, `mappableRoles`, granted authorities. |
| User thuộc nhóm IdP nhưng không có role Spring | Nhóm IdP chưa được container ánh xạ ra JEE role, hoặc roles không trong danh sách mappable. | Kiểm tra realm/role mapper ở container trước khi sửa Spring. |
| `/health` bị container đòi login dù Spring `permitAll` | Container constraint bảo vệ URL, chạy trước Spring. | Kiểm tra `web.xml` và URL security constraints thực tế. |
| Endpoint nhạy cảm bypass xác thực | Một URL/method không nằm trong container constraints hoặc đường truy cập bỏ qua trusted gateway. | Kiểm tra mọi entry points, dispatcher types, context paths và security matchers; khóa đường bypass. |
| Logout Spring xong vẫn vào ứng dụng với SSO | Container/IdP vẫn giữ phiên; Spring logout không đồng nghĩa logout SSO. | Thiết kế logout liên tầng và kiểm thử session revocation. |
| Môi trường embedded Boot chạy nhưng principal luôn null | Chỉ bật `http.jee` mà chưa thiết lập embedded container auth realm. | Cấu hình container thực sự hoặc chọn cơ chế xác thực Spring native phù hợp. |
| Tài khoản bị đổi role nhưng quyền cũ còn | Caching ở realm, session hoặc SecurityContext. | Cấu hình hết hạn/invalidation và thực hiện kiểm thử role revocation. |
| Principal “xuất hiện” trong controller nhưng không từ realm | Request bị Spring Security wrapper thay đổi cách hiển thị principal. | Kiểm tra raw container request trước security wrapper và Authentication của Spring riêng biệt. |

### Trình tự debug an toàn

1. **Ở container:** có realm và login mechanism thực tế chưa? URL có được container bảo vệ? Realm có xác thực user và ánh xạ role đúng?
2. **Trước Spring filter:** `getUserPrincipal()`, `getRemoteUser()` và `isUserInRole(...)` phản ánh gì? Có request bypass security constraints không?
3. **Trong Spring Security:** `J2eePreAuthenticatedProcessingFilter` có chạy trong đúng chain không? PreAuthenticatedAuthenticationProvider có tạo Authentication? Authorities nào được cấp?
4. **Ở authorization:** matcher nào khớp URL? `hasRole` đang đòi `ROLE_*` nào? Có method security rule khác không?
5. **Vòng đời:** logout, session timeout, thay role, redirect/proxy, HTTPS/CSRF có đồng bộ với container/SSO không?

Khi debug, không ghi thông tin xác thực, session ID, password, SSO ticket hoặc token nhạy cảm vào log. Không trả thẳng toàn bộ security context cho user ngoài mục đích kiểm tra được kiểm soát.

## 13. Khi nào nên chọn JEE pre-auth?

**Phù hợp** khi bạn triển khai Servlet application vào một container/application server doanh nghiệp đã chuẩn hóa realm/SSO và cung cấp principal cùng roles tin cậy; Spring Security cần tận dụng danh tính đó cho URL authorization, method security và các thành phần ứng dụng.

**Không phải giải pháp tiện nhất** khi ứng dụng Spring Boot chạy độc lập trên embedded server chưa có container auth, hoặc hệ thống chủ yếu dùng JWT Bearer resource server/OIDC login được chính Spring Security triển khai. Các cơ chế đó có filter chain và cấu hình riêng; không thêm `.jee()` theo thói quen nếu container không làm pre-authentication.

**Ghi nhớ mối quan hệ:** **Servlet Container xác thực trước → request có principal/roles đáng tin → J2eePreAuthenticatedProcessingFilter đọc identity → Spring Security tạo Authentication và mapped authorities → authorization áp dụng theo URL/method**. Cần kiểm thử cả ranh giới container và Spring; nếu nguồn principal không đáng tin, mọi rule phía sau đều dựa trên nền tảng sai.

## Tài liệu tham khảo chính thức

- Spring Security — Pre-Authentication Scenarios: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/preauth.html
- Spring Security API — JeeConfigurer: https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/config/annotation/web/configurers/JeeConfigurer.html
- Jakarta Servlet API — HttpServletRequest: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletrequest
