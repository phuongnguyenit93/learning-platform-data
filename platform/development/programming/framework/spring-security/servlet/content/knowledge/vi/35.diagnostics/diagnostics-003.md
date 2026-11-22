# Điều tra 401, 403 và chuyển hướng 302 sai dự kiến

**Module:** Spring Security – Servlet  
**Chủ đề cha:** Chẩn đoán

## 1. Hiểu đúng câu hỏi trước khi sửa cấu hình

Trong Spring Security Servlet, ba kết quả HTTP thường khiến người học nhầm lẫn là:

- **401 Unauthorized**: request cần xác thực nhưng không cung cấp credential hợp lệ hoặc cơ chế xác thực yêu cầu thử lại. Tên HTTP là "Unauthorized" nhưng ý nghĩa thực tế của 401 thường là **chưa được xác thực**.
- **403 Forbidden**: request bị từ chối. Có thể vì người dùng đã xác thực nhưng thiếu authority, vì **CSRF token** thiếu/sai, vì policy `denyAll`, vì CORS hoặc vì một điều kiện kiểm tra quyền khác. **Không phải mọi 403 đều do thiếu role**.
- **302 Found**: redirect đến một URL khác qua header `Location`. Trong ứng dụng web dùng `formLogin()`, request chưa đăng nhập thường bị chuyển tới `/login`. Nhưng 302 cũng có thể là **chuyển hướng sau login, sau logout, về saved request**, do ứng dụng hoặc reverse proxy tạo.

Điều tra hiệu quả không bắt đầu bằng "làm sao tắt security để hết lỗi", mà bắt đầu bằng câu hỏi:

> **Request thực đi qua chuỗi bảo mật nào, được xác thực bằng cơ chế gì, bị chặn ở filter hay authorization nào, và response do thành phần nào tạo?**

Cùng một endpoint có thể trả 401, 403 hoặc 302 phụ thuộc:

1. **HTTP method**: GET hay POST; POST có cần CSRF không?
2. **Đường dẫn thực**: `/api/orders`, `/web/orders`, context path, servlet path, trailing slash và forward/error dispatch.
3. **SecurityFilterChain được chọn**: HTTP Basic, OAuth2 Resource Server, form login hay một chuỗi fallback.
4. **Trạng thái người gọi**: anonymous, session hợp lệ, bearer token hợp lệ, credential sai, tài khoản đã xác thực nhưng thiếu quyền.
5. **Authority và chính sách**: `ROLE_ADMIN`, `SCOPE_orders.read`, `hasAuthority`, `hasRole`, `denyAll`, method security hoặc kiểm tra quyền theo resource.
6. **Chính sách CSRF/CORS**: browser tự gửi cookie, request JSON, preflight OPTIONS và token CSRF.
7. **Entry point, error handler, reverse proxy hoặc controller**: ai quyết định 401, 403 hay 302?

Bài này hướng dẫn cách lần theo từng tầng, kèm một **dự án Java 17 / Spring Boot 3.3.5 / Spring Security 6** để kiểm tra hành vi thực qua MockMvc.

## 2. Bảng đọc nhanh: dấu hiệu nào gợi ý nguyên nhân nào?

| Kết quả | Dấu hiệu thường gặp | Cần kiểm tra trước |
| --- | --- | --- |
| 401 + `WWW-Authenticate: Basic ...` | API dùng HTTP Basic, chưa có hoặc sai Basic credentials | Đúng chain chưa? Header Authorization? UserDetailsService/PasswordEncoder? |
| 401 + `WWW-Authenticate: Bearer ...` | Resource Server không chấp nhận bearer token | Token, issuer, audience, chữ ký/introspection, `exp`, cấu hình resource server |
| 403 sau khi đã login | Thiếu role/scope/permission hoặc policy chặn | Authority thực tế, `hasRole`/ `hasAuthority`, order matcher, object-level permission |
| 403 cho POST nhưng GET cùng path dùng được | Có thể thiếu/sai CSRF token | `CsrfFilter`, form hidden field, cookie/session, security test `csrf()` |
| 403 ngay cả khi là admin | `denyAll`, sai filter chain, role prefix, object/tenant rule, CSRF | Rule được chọn, security matcher, method, context |
| 302 tới `/login` | Form login yêu cầu xác thực, không phải API 401 | `formLogin()`, entry point, chain, session |
| 302 tới trang khác sau login | Saved request / success handler / `defaultSuccessUrl` | `Location`, request cache, success handler, session |
| 302 lặp vô hạn | Login/session/cookie/host/proxy/redirect URI bất nhất | `Set-Cookie`, `Location`, HTTPS, forwarded headers, SameSite/Domain/Path |
| 200 trả HTML login thay vì JSON | Client theo redirect tự động nên che 302 ban đầu | Network redirect chain, `Content-Type`, `Location` |
| 403 cho OPTIONS preflight | Policy/security/CORS chưa xử lý preflight đúng | `Origin`, `Access-Control-Request-Method`, CORS config, chain |

**Ghi nhớ:** bảng này cho biết **giả thuyết cần kiểm tra**, không phải quy tắc tuyệt đối cho mọi ứng dụng. Có `@ControllerAdvice`, custom `AuthenticationEntryPoint`, gateway hoặc nhiều chain, cùng một lỗi có thể được biến đổi thành mã khác.

## 3. Luồng request trong Spring Security Servlet

Một request HTTP thường đi qua:

~~~text
Client / browser
    |
    v
Reverse proxy / load balancer / ingress (nếu có)
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy("springSecurityFilterChain")
    |
    v
FilterChainProxy
    |--- chọn SecurityFilterChain ĐẦU TIÊN match request
    |
    v
Các filter của chain đã chọn
    |--- SecurityContextHolderFilter / context repository
    |--- CsrfFilter (nếu áp dụng)
    |--- authentication filters (Basic, Bearer, formLogin...)
    |--- AnonymousAuthenticationFilter
    |--- ExceptionTranslationFilter
    |--- AuthorizationFilter
    |
    v
DispatcherServlet
    |--- Controller
    |--- Service / @PreAuthorize
    |--- Exception handlers
    v
Response: 200 / 302 / 401 / 403 / ...
~~~

Sơ đồ biểu diễn **vai trò các nhóm filter**, không phải danh sách thứ tự chính xác bất biến của mọi phiên bản/cấu hình. Thành phần có mặt và thứ tự thực tế phụ thuộc `SecurityFilterChain` đã được tạo.

### 3.1. Authentication và authorization không phải một bước

- **Authentication** xác nhận chủ thể: mật khẩu, session, Basic header, bearer token, OIDC login...
- **Authorization** quyết định chủ thể đã xác thực có được thực hiện request không, dựa trên authorities và chính sách.
- **`SecurityContextHolder`** cho biết `Authentication` hiện hành khi xử lý cùng luồng thực thi.
- **`AuthenticationEntryPoint`** bắt đầu quá trình authentication khi cần: có thể trả 401 hoặc redirect 302.
- **`AccessDeniedHandler`** xử lý một trường hợp bị từ chối truy cập: thông thường trả 403; có thể tùy biến.
- **`ExceptionTranslationFilter`** chuyển một số `AuthenticationException` và `AccessDeniedException` thành hành vi entry point hoặc access-denied. Tuy nhiên, **CSRF filter có thể tự xử lý AccessDeniedException bằng handler**, nên không được suy ra mọi 403 đều do filter này.

### 3.2. Cơ chế 401, 403 và 302 theo loại người gọi

~~~text
Request đến endpoint được bảo vệ
    |
    +-- Chưa có authentication hợp lệ
    |      |
    |      +-- Chain dùng HTTP Basic ---> 401 + Basic challenge
    |      +-- Chain dùng bearer -------> 401 + Bearer challenge
    |      +-- Chain dùng form login ---> 302 Location: /login
    |      +-- Custom entry point ------> theo cấu hình
    |
    +-- Đã xác thực, nhưng thiếu quyền
    |      |
    |      +-- Authorization từ chối --> thường 403
    |
    +-- POST thiếu/sai CSRF token
    |      |
    |      +-- CsrfFilter từ chối -----> thường 403
    |
    +-- Đã xác thực, có quyền, request hợp lệ
           |
           +-- Controller xử lý -----> 200/201/204/302/4xx/5xx theo app
~~~

**Quan trọng:** các nhánh không phải một thứ tự kiểm tra cố định; CSRF có thể chặn POST **trước khi** authorization kiểm tra role. Một POST anonymous thiếu CSRF có thể trả 403 ngay cả khi GET anonymous sẽ trả 302/401.

## 4. Khi nào trả 401?

### 4.1. HTTP Basic

Với chain có `httpBasic()`, một request thiếu credential tới endpoint bảo vệ có thể nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

Client cần gửi header `Authorization: Basic ...` đúng định dạng. Spring Security xử lý credential qua `AuthenticationManager` và provider phù hợp. Những nguyên nhân phổ biến:

- Không gửi header Authorization.
- Username không tồn tại, password sai hoặc encoder không khớp cách lưu hash.
- Request đi vào Basic chain thay vì form-login chain.
- Proxy/gateway làm rơi header Authorization.
- Custom `AuthenticationEntryPoint` thay đổi response.

**Không giải quyết bằng cách cho `permitAll()` toàn bộ endpoint** chỉ để hết 401; phải xác định vì sao authentication không thành công.

### 4.2. Bearer/JWT/opaque token

Với `oauth2ResourceServer().jwt()` hoặc `.opaqueToken()`, token có thể không được chấp nhận do:

- Header `Authorization: Bearer ...` vắng hoặc không hợp lệ.
- JWT hết hạn, chữ ký sai, algorithm không được chấp nhận, issuer không khớp.
- Token không thuộc audience/resource mong đợi, nếu hệ thống có validator/policy về audience.
- JWK endpoint/issuer metadata không tải được hoặc introspection endpoint không phản hồi đúng.
- Opaque introspection trả `active:false` hoặc resource server không có credentials hợp lệ để introspect.

Một response minh họa:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Không phải mọi 401 đều có thông tin `invalid_token`; nội dung challenge phụ thuộc lỗi và handler. **Không đưa token thô, client secret hay thông tin nhạy cảm vào log để debug**.

### 4.3. Vì sao 401 đôi khi lại thành 302?

Nếu request đi vào **form-login chain**, `LoginUrlAuthenticationEntryPoint` thường redirect đến `/login` thay vì trả Basic/Bearer challenge. Đây là hành vi hợp lý cho trình duyệt web, nhưng có thể sai kỳ vọng của API client.

Một API gọi `GET /api/profile` bằng `fetch()` nhận `200 text/html` chứa trang login thường là kết quả của **302 bị client tự theo**. Khi debug, phải xem request đầu tiên và chuỗi redirect, không chỉ nhìn response cuối.

Nếu một ứng dụng cố cung cấp cả web login và REST API, thiết kế **SecurityFilterChain/AuthenticationEntryPoint riêng** cho từng nhóm đường dẫn hoặc chỉ định entry point theo RequestMatcher một cách có chủ đích.

## 5. Khi nào trả 403?

### 5.1. Có Authentication nhưng không đủ authority

Ví dụ endpoint:

~~~java
// Đoạn minh họa bên trong HttpSecurity DSL:
.requestMatchers("/admin/**").hasRole("ADMIN")
~~~

Khi dùng prefix mặc định, `hasRole("ADMIN")` tìm authority **`ROLE_ADMIN`**. Nếu authentication chỉ có `ROLE_USER`, request bị từ chối.

| Rule | Authority cần có (mặc định) |
| --- | --- |
| `hasRole("ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("ROLE_ADMIN")` | `ROLE_ADMIN` |
| `hasAuthority("SCOPE_reports.read")` | `SCOPE_reports.read` |
| `hasAnyRole("EDITOR", "ADMIN")` | Ít nhất một trong `ROLE_EDITOR`, `ROLE_ADMIN` |

Sai lầm thường gặp là gọi `hasRole("ROLE_ADMIN")` khi đang dùng prefix `ROLE_` mặc định, hoặc coi `SCOPE_profile` là role admin. Cần xem authority **thực sự có trong `Authentication`**, không đoán theo tên user hay claim của IdP.

**Ngay cả khi có role**, method security `@PreAuthorize`, domain permission, ownership/tenant hoặc một policy `denyAll` vẫn có thể từ chối. Kiểm tra cả lớp service khi URL rule có vẻ đúng.

### 5.2. 403 do CSRF

Trong Spring Security Servlet, với web app dùng session/cookie hoặc một số kiểu credential được browser tự gửi, CSRF là lớp bảo vệ cần thiết.

Request ví dụ thiếu token:

~~~http
POST /web/notes HTTP/1.1
Cookie: JSESSIONID=...
Content-Type: application/x-www-form-urlencoded

text=hello
~~~

Nếu CSRF được bật và request cần token, `CsrfFilter` thường trả **403** dù session hợp lệ và user có role đúng.

Request hợp lệ có thể chứa hidden field `_csrf`, tên/value do server render:

~~~html
<form method="post" action="/web/notes">
    <input name="text" value="hello">
    <input type="hidden" name="_csrf" value="gia-tri-server-cung-cap">
    <button type="submit">Lưu</button>
</form>
~~~

Giá trị trên **chỉ minh họa**; không hard-code token hoặc tự tạo một chuỗi giả. Với Spring MVC/Thymeleaf, server có thể expose `_csrf.parameterName` và `_csrf.token` trong request; cũng có thể tự chèn token qua `RequestDataValueProcessor` tùy cách render form.

Để chứng minh 403 là do **role** trong MockMvc POST test, dùng `csrf()` hợp lệ rồi kiểm tra user thiếu authority. Nếu quên token, test 403 có thể **xanh sai lý do**.

### 5.3. DenyAll hoặc sai SecurityFilterChain

Với nhiều chuỗi:

~~~text
@Order(1): /api/admin/**       -> rule ADMIN
@Order(2): /api/**             -> rule API
@Order(3): catch-all           -> rule WEB / denyAll
~~~

Spring Security chọn **SecurityFilterChain đầu tiên khớp**. Rule của các chuỗi sau không được xét nếu một chuỗi trước đã match.

- `http.securityMatcher(...)`: chọn phạm vi **chuỗi**.
- `authorizeHttpRequests().requestMatchers(...)`: chọn **quy tắc quyền bên trong chuỗi**.
- `anyRequest().denyAll()`: chặn các request vào chuỗi nhưng không có rule cho phép.
- Catch-all chain không giới hạn `securityMatcher`: bảo vệ các URL còn lại.

Một admin user có thể gặp 403 không phải vì tài khoản thiếu role, mà vì request đi vào chain **khác** hoặc khớp `denyAll` trước một rule dự kiến cho phép.

### 5.4. CSRF và CORS không phải một thứ

Một browser gửi cross-origin request có thể có preflight `OPTIONS`. Nếu CORS chưa được cấu hình đúng, browser có thể chặn request hoặc server/proxy trả 401/403 cho preflight. Đừng nhầm với CSRF:

- **CORS** kiểm soát browser có thể đọc/cấp phép một số cross-origin request như thế nào. Nó không phải cơ chế xác thực token.
- **CSRF** bảo vệ các thao tác đổi trạng thái trước việc browser bị lợi dụng gửi credential tự động.
- **401/403 preflight** có thể phát sinh trước khi request chính được gửi; hãy xem riêng `OPTIONS`, `Origin`, `Access-Control-Request-Method`, `Access-Control-Allow-*`.
- **Không** đặt `Access-Control-Allow-Origin: *` cùng credentialed CORS như một cách chữa mọi lỗi.
- Với SPA dùng cookie, cần phân tích **cả CORS, CSRF, SameSite và session**; với API bearer stateless có threat model khác.

## 6. Khi nào 302 là đúng, khi nào 302 sai?

### 6.1. Anonymous request tới web form login

Browser gọi:

~~~http
GET /web/home HTTP/1.1
Host: localhost:8080
~~~

Nếu `/web/home` cần authentication và chain dùng `formLogin()`, kết quả thường:

~~~http
HTTP/1.1 302 Found
Location: http://localhost:8080/login
~~~

`Location` là URL đích. Đây là hành vi bình thường của form-login flow, không phải chứng cứ endpoint đã bị public.

### 6.2. Redirect sau khi login

Sau POST `/login` hợp lệ, Spring Security có thể:

- Chuyển tới **saved request** ban đầu đã khiến người dùng phải login.
- Chuyển tới `defaultSuccessUrl` hoặc URL do `AuthenticationSuccessHandler` quyết định.
- Chuyển tới một URL cấu hình cho ứng dụng.

Nếu test kỳ vọng `/dashboard` mà thực tế sang `/orders/42`, có thể do request cache đã lưu URL ban đầu. `defaultSuccessUrl("/dashboard", true)` buộc dùng default target trong cấu hình đó, còn nếu không ép target, saved request có thể được ưu tiên.

**Không kiểm tra chỉ mã 302; phải assert header `Location` và ngữ cảnh session/request-cache**. Một response redirect đúng status nhưng sai target vẫn là lỗi chức năng.

### 6.3. Vòng lặp redirect login

Tình huống:

~~~text
GET /web/home
 -> 302 /login
GET /login
 -> 302 /login
GET /login
 -> 302 /login
 ...
~~~

Các nguyên nhân có thể:

1. URL `/login` **không được `permitAll`**, hoặc nằm ngoài phạm vi chain chứa `formLogin`/default login page filter.
2. Session cookie không được giữ vì **Domain, Path, Secure, SameSite, HTTPS/HTTP hoặc proxy**.
3. Sau login thành công, SecurityContext không được lưu/khôi phục như kỳ vọng.
4. Reverse proxy sửa host/scheme không nhất quán, tạo redirect ngược giữa HTTP và HTTPS.
5. OAuth2/OIDC redirect URI, callback path, `state` hoặc session không khớp.
6. Handler/controller tùy biến có logic redirect về login ngay cả khi authenticated.
7. Browser tự động theo redirect khiến bước đầu tiên bị che trong log cuối.

Hãy quan sát **mỗi response 302**, `Location` và `Set-Cookie` (giữ bí mật), không chỉ URL cuối trên thanh địa chỉ.

### 6.4. Redirect không đến từ Spring Security

`302` còn có thể do:

- Controller trả `redirect:/...`.
- Servlet container chuyển URL hoặc bảo vệ session theo cấu hình riêng.
- Gateway/ingress/CDN chuyển HTTP sang HTTPS, thêm slash hoặc đổi hostname.
- Một thư viện SSO khác (CAS, SAML2, OAuth2 Login).
- Application exception handler hoặc redirect sau khi lưu form.

Vì vậy phải xác định **response được tạo ở layer nào**. Dùng correlation ID an toàn để đối chiếu access log của gateway, app và test.

## 7. Tạo một dự án chẩn đoán chạy được: Java 17 + Spring Boot 3.3.5

Ví dụ dùng **hai SecurityFilterChain** để kết quả có thể phân biệt bằng hành vi:

- **API chain** `/api/**` dùng HTTP Basic: anonymous thường **401**, đúng user+quyền **200**, user thiếu quyền **403**.
- **Web/fallback chain** xử lý đường dẫn còn lại với form login: anonymous tới `/web/home` thường **302 /login**, user thiếu `ROLE_ADMIN` ở `/web/admin` **403**.
- **POST** ở cả hai nhóm vẫn yêu cầu **CSRF** mặc định trong demo này; HTTP Basic có thể là credential browser tự gửi nên không vô hiệu hóa CSRF chỉ vì có chữ "API".
- **Catch-all denyAll** chặn URL chưa khai báo; một controller `/shadow` có thật nhưng không được phép truy cập.
- Spring Security Test / MockMvc kiểm tra cả status và một số response headers.

Đây là mô hình demo để **phân biệt nguyên nhân**; production cần chọn provider, session strategy, CSRF policy và resource authorization phù hợp.

### 7.1. Cấu trúc thư mục

~~~text
security-status-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── StatusDemoApplication.java
    │   ├── SecurityConfiguration.java
    │   └── StatusController.java
    └── test/java/demo/StatusDemoTests.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>security-status-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
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

`starter-web` cung cấp Servlet Spring MVC, `starter-security` tạo filter infrastructure, `starter-test` chứa JUnit Jupiter/MockMvc, `spring-security-test` chứa `user()`, `csrf()`, `httpBasic()` và helpers.

### 7.3. src/main/java/demo/StatusDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StatusDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(StatusDemoApplication.class, args);
    }
}
~~~

### 7.4. src/main/java/demo/SecurityConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService testUsers(PasswordEncoder encoder) {
        // Các user/password cố định chỉ dùng để demo local.
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-only"))
                .authorities("DOC_READ").build(),
            User.withUsername("writer")
                .password(encoder.encode("demo-only"))
                .authorities("DOC_WRITE").build(),
            User.withUsername("editor")
                .password(encoder.encode("demo-only"))
                .roles("EDITOR").build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-only"))
                .roles("ADMIN").build()
        );
    }

    // API được xét trước: Basic challenge khi chưa xác thực.
    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/documents")
                    .hasAuthority("DOC_READ")
                .requestMatchers(HttpMethod.POST, "/api/documents")
                    .hasAuthority("DOC_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // Giữ CSRF mặc định: Basic có thể bị browser tự gửi.
        return http.build();
    }

    // Không giới hạn securityMatcher: vừa là web chain, vừa catch-all.
    @Bean
    @Order(2)
    SecurityFilterChain webAndFallback(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/login")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/web/home")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/web/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/web/notes")
                    .hasRole("EDITOR")
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/web/home", true)
            )
            .logout(Customizer.withDefaults());

        // Không tắt CSRF: form login, form POST và logout đều cần token.
        return http.build();
    }
}
~~~

**Giải thích:**

1. `apiChain` có `securityMatcher("/api/**")`, nên GET `/api/documents` được xử lý bằng Basic entry point. Request thiếu authentication thường trả **401**, không redirect tới login form.
2. `webAndFallback` không khai báo `securityMatcher` riêng, nên bao phủ tất cả request **chưa khớp API chain**. GET `/web/home` anonymous thường trả **302** tới `/login`.
3. `@Order(1)` trước `@Order(2)`: thứ tự quyết định chain; `anyRequest` chỉ quyết định rule **trong chain đã chọn**.
4. `hasRole("ADMIN")` cần `ROLE_ADMIN`, còn `hasAuthority("DOC_READ")` cần chính xác `DOC_READ`.
5. `anyRequest().denyAll()` là chính sách fail closed: route mới hoặc method mới không tự public.
6. `formLogin` tạo trang login mặc định; `defaultSuccessUrl("/web/home", true)` ép target sau login thành công thay vì dùng saved request. Một hệ thống thật có thể muốn giữ saved-request behavior, cần cân nhắc trước khi ép target.
7. Mật khẩu `demo-only` nằm trong source chỉ để học. **Không dùng người dùng hard-code hoặc HTTP Basic không TLS trong production**.
8. Mã giữ CSRF protection mặc định cho cả hai chain. Không suy ra rằng mọi API Basic phải dùng chính xác cùng policy: threat model thực tế quyết định.

### 7.5. src/main/java/demo/StatusController.java

~~~java
package demo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/")
    Map<String, String> home() {
        return Map.of("message", "home-public");
    }

    @GetMapping("/api/public")
    Map<String, String> apiPublic() {
        return Map.of("message", "api-public");
    }

    @GetMapping("/api/documents")
    Map<String, String> readDocument() {
        return Map.of("message", "document-read");
    }

    @PostMapping("/api/documents")
    Map<String, String> writeDocument() {
        // Demo: không ghi DB hoặc nhận dữ liệu nhạy cảm.
        return Map.of("message", "document-written");
    }

    @GetMapping("/web/home")
    Map<String, String> webHome() {
        return Map.of("message", "web-home");
    }

    @GetMapping("/web/admin")
    Map<String, String> webAdmin() {
        return Map.of("message", "web-admin");
    }

    @PostMapping("/web/notes")
    Map<String, String> notes() {
        return Map.of("message", "web-note-saved");
    }

    @GetMapping("/shadow")
    Map<String, String> shadow() {
        return Map.of("secret", "not-allowed");
    }
}
~~~

Controller `/shadow` **có thật** nhưng không có allow rule trong catch-all, nhờ vậy một test 403 trên `/shadow` chứng minh fallback đang bảo vệ route; không nhầm với 404 vì thiếu handler.

### 7.6. Chạy local và quan sát status + Location

Từ thư mục project:

~~~bash
mvn spring-boot:run
~~~

Các lệnh `curl` sau dành cho máy local học tập:

~~~bash
# Public API: thường 200.
curl -i http://localhost:8080/api/public

# API bảo vệ, chưa xác thực: thường 401 + WWW-Authenticate: Basic.
curl -i http://localhost:8080/api/documents

# Basic user có DOC_READ: thường 200.
curl -i -u reader:demo-only \
  http://localhost:8080/api/documents

# User có DOC_WRITE nhưng thiếu DOC_READ: thường 403.
curl -i -u writer:demo-only \
  http://localhost:8080/api/documents

# Web chưa login: thường 302 + Location: /login.
curl -i http://localhost:8080/web/home
~~~

**Đừng dùng `curl -L` ở bước đầu điều tra 302**, vì nó theo redirect và che response ban đầu. Dùng `-i` để thấy headers `Location` và `WWW-Authenticate`.

Với password thật, `curl -u` có thể để lại thông tin ở shell history/monitoring; dùng công cụ quản lý bí mật phù hợp. Không gửi Basic password qua HTTP ngoài demo localhost không nhạy cảm; production dùng **HTTPS**.

**Kỳ vọng:** API anonymous 401, authorized 200, authenticated thiếu quyền 403, web anonymous 302. Đây là kết quả **dự kiến theo mã**, không phải log thực tế đã được thực thi/ghi nhận trong quá trình soạn bài.

## 8. MockMvc: kiểm tra nguyên nhân chứ không chỉ status

### 8.1. src/test/java/demo/StatusDemoTests.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class StatusDemoTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicApiReturns200() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("api-public"));
    }

    @Test
    void apiWithoutCredentialsReturns401BasicChallenge()
            throws Exception {
        mvc.perform(get("/api/documents"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE, containsString("Basic")));
    }

    @Test
    void invalidBasicPasswordReturns401() throws Exception {
        mvc.perform(get("/api/documents")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderCanReadApi() throws Exception {
        mvc.perform(get("/api/documents")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("DOC_READ"))))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("document-read"));
    }

    @Test
    void authenticatedUserWithoutReadPermissionGets403()
            throws Exception {
        mvc.perform(get("/api/documents")
                .with(user("writer").authorities(
                    new SimpleGrantedAuthority("DOC_WRITE"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiPostWithoutCsrfIs403EvenForWriter() throws Exception {
        mvc.perform(post("/api/documents")
                .with(user("writer").authorities(
                    new SimpleGrantedAuthority("DOC_WRITE"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiPostWithCsrfButWrongPermissionIs403()
            throws Exception {
        mvc.perform(post("/api/documents")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("DOC_READ")))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiPostWithCsrfAndPermissionIs200() throws Exception {
        mvc.perform(post("/api/documents")
                .with(user("writer").authorities(
                    new SimpleGrantedAuthority("DOC_WRITE")))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("document-written"));
    }

    @Test
    void anonymousWebRequestRedirects302ToLogin()
            throws Exception {
        mvc.perform(get("/web/home"))
            .andExpect(status().isFound())
            .andExpect(header().string(
                HttpHeaders.LOCATION, containsString("/login")));
    }

    @Test
    void authenticatedWebUserMayOpenHome() throws Exception {
        mvc.perform(get("/web/home")
                .with(user("editor").roles("EDITOR")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("web-home"));
    }

    @Test
    void authenticatedEditorCannotOpenAdmin() throws Exception {
        mvc.perform(get("/web/admin")
                .with(user("editor").roles("EDITOR")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenAdmin() throws Exception {
        mvc.perform(get("/web/admin")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("web-admin"));
    }

    @Test
    void webPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/web/notes")
                .with(user("editor").roles("EDITOR")))
            .andExpect(status().isForbidden());
    }

    @Test
    void webPostWrongRoleStill403WithValidCsrf()
            throws Exception {
        mvc.perform(post("/web/notes")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("DOC_READ")))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void webPostCorrectRoleAndCsrfIs200() throws Exception {
        mvc.perform(post("/web/notes")
                .with(user("editor").roles("EDITOR"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("web-note-saved"));
    }

    @Test
    void loginPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "editor")
                .param("password", "demo-only"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validFormLoginReturns302ToConfiguredSuccessUrl()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "editor")
                .param("password", "demo-only"))
            .andExpect(status().isFound())
            .andExpect(header().string(
                HttpHeaders.LOCATION, "/web/home"));
    }

    @Test
    void mappedButUnlistedEndpointIsDenied() throws Exception {
        mvc.perform(get("/shadow")
                .with(user("editor").roles("EDITOR")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unknownApiPathIsDeniedForAuthenticatedUser()
            throws Exception {
        mvc.perform(get("/api/unlisted")
                .with(user("reader").authorities(
                    new SimpleGrantedAuthority("DOC_READ"))))
            .andExpect(status().isForbidden());
    }
}
~~~

Bộ ví dụ gồm **19 test**: public, 401 Basic challenge, sai password, 403 thiếu quyền, 403 CSRF, API POST đủ quyền, 302 web anonymous, web home/admin, login POST, URL chưa khai báo. Các phương thức test tách từng điều kiện để không chỉ assert 403 do **một nguyên nhân vô tình khác**.

### 8.2. Điểm kiểm thử quan trọng

- **`.with(user(...))`** đặt authentication giả trên **MockMvc request cụ thể**. Nó giúp test authorization nhưng **không kiểm tra password encoder hay HTTP Basic authentication thật**.
- **`.with(httpBasic(...))`** tạo header Basic để kiểm tra đường authentication thực của API chain. Test sai password xác nhận ít nhất một nhánh reject.
- **`.with(csrf())`** tạo CSRF token test hợp lệ; dùng nó khi cần cô lập authorization POST khỏi lỗi thiếu token.
- **`status().isFound()`** kiểm tra 302, **`header().string("Location", ...)`** kiểm tra redirect tới đúng URL. Chỉ assert 302 không đủ.
- **`header().string("WWW-Authenticate", ...)`** kiểm tra API nhận Basic challenge, giúp phân biệt với form-login redirect.
- **`/shadow`** là controller có thật nhưng phải bị catch-all denyAll chặn. Test này phát hiện rủi ro nếu xóa fallback chain.
- **`/api/unlisted`** không có controller nhưng match API chain; test với authenticated user có thể nhận 403 từ `denyAll` **trước khi MVC xem có route hay không**.
- **`@SpringBootTest` + `@AutoConfigureMockMvc`** dùng ApplicationContext và Spring Security filters. Với `MockMvcBuilders.standaloneSetup` mà quên `springSecurity()`, các test có thể bỏ qua security và cho kết quả sai.
- Không dùng `@AutoConfigureMockMvc(addFilters = false)` khi mục tiêu là kiểm thử bộ lọc bảo mật.

Chạy:

~~~bash
mvn test
~~~

Kỳ vọng **19 tests, 0 failures, 0 errors** nếu cấu hình đầy đủ như các file trên. Đây là **kết quả dự kiến**, không phải kết quả Maven đã chạy trong môi trường soạn bài.

## 9. Phương pháp điều tra thực tế theo trình tự

### Bước 1 — Ghi nhận request/response đầu tiên

Không bắt đầu bằng một ảnh chụp cuối cùng của browser. Ghi các dữ kiện **không chứa secret**:

| Trường | Ví dụ |
| --- | --- |
| Method + path | `GET /api/documents` |
| Scheme/host | `https://api.example.test` |
| Response đầu tiên | `401 Unauthorized` |
| `WWW-Authenticate` | `Basic realm="Realm"` |
| `Location` nếu redirect | `/login` hoặc `https://...` |
| Có gửi credentials không | Có/không, **không lưu giá trị** |
| Có cookie session không | Có/không, **không lưu ID** |
| CSRF (với POST) | Có/thiếu/sai, **không log token** |
| Content type / Accept | `application/json` / `text/html` |
| Correlation ID | ID an toàn nối giữa gateway và ứng dụng |

Cũng cần kiểm tra **request đúng HTTP method hay không**. GET và POST cùng URL có thể đi qua các rule khác nhau và POST có CSRF.

### Bước 2 — Kiểm tra đúng SecurityFilterChain

Với nhiều chain, liệt kê `securityMatcher` và `@Order`, tìm chain **đầu tiên match** request. Sau đó mới đọc `requestMatchers` của `authorizeHttpRequests` bên trong chain đó.

Nếu chain chỉ match `/api/**`, thì `anyRequest().authenticated()` hay `denyAll()` bên trong **không** tự bảo vệ `/web/**`. Cần chain khác hoặc catch-all. Nếu chain formLogin có matcher quá hẹp, `/login` hoặc OAuth2 callback có thể nằm ngoài vùng của chính login filter.

Để xem chain bằng log trong môi trường test, có thể dùng cấu hình **chỉ để debug tạm**:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Các mức logging khác nhau theo phiên bản Spring Security; không dựa chỉ vào một dòng log cố định để kết luận. **Không bật TRACE tràn lan trong production**, và cần cấu hình che `Authorization`, session cookie, token/PII trên toàn bộ logger/gateway.

### Bước 3 — Xác định anonymous hay authenticated

Với một request bị chặn, hỏi:

- Authentication có được xây dựng từ credential/token/session hay không?
- Nếu có, `principal` và **tên authority** là gì? Có thể ghi tên quyền trong môi trường test với dữ liệu giả, không ghi credential/token thật.
- User có `ROLE_ADMIN` hay chỉ `ADMIN`? Có `SCOPE_reports.read` hay chỉ `ROLE_USER`?
- Có nhiều authentication mechanisms (session + Basic + bearer) ở cùng một chain làm chọn sai loại authentication không?
- Nếu login thành công nhưng request kế tiếp lại anonymous: SecurityContext có được lưu vào session và cookie có quay lại không?

Khi đối chiếu request 401, xác nhận provider đã thực sự được gọi. Với bearer, xem lỗi validator/introspector bằng instrumentation an toàn; với Basic, xem `AuthenticationManager`/provider mà không log password.

### Bước 4 — Phân biệt 403 do CSRF với 403 do authorization

Thử ma trận:

| Authentication | CSRF token | Quyền cần thiết | Kỳ vọng POST |
| --- | --- | --- | --- |
| Đã login, có quyền | **Thiếu** | Đủ | 403 do CSRF có thể đến trước authorization. |
| Đã login, thiếu quyền | Hợp lệ | Thiếu | 403 do authorization. |
| Đã login, có quyền | Hợp lệ | Đủ | Cho tới controller; thường 200/201/302 theo app. |
| Anonymous | Thiếu | Không có | Có thể 403 vì CSRF trước khi entry point được gọi. |
| Anonymous | Hợp lệ | Không có | Có thể 401/302 tùy entry point và chain. |

**Đừng tắt CSRF để khiến test xanh**. Đối với web session/cookie, hãy render/gửi token hợp lệ và xác minh luồng login/logout làm mới token khi cần. Với API stateless bearer, có thể áp CSRF policy khác dựa trên threat model đã chứng minh.

### Bước 5 — Tìm redirect origin và kiểm tra session

Với 302, cần:

1. Xem **header `Location` ở response đầu tiên** và mọi bước tiếp theo.
2. Xác định redirect từ Spring Security entry point, authentication success/failure handler, controller, OAuth2 flow hay gateway.
3. Nếu redirect login lặp, kiểm tra cookie session có được **Set-Cookie và gửi lại** không; chỉ ghi nhận sự có mặt và attributes an toàn.
4. Kiểm tra **HTTPS, Host, X-Forwarded-Proto, context path, cookie Secure/SameSite/Domain/Path**, reverse proxy và đường callback.
5. Xác nhận saved request/target URL logic: request ban đầu, success handler, `defaultSuccessUrl(..., true)` hay custom handler.
6. Với OAuth2/OIDC, kiểm tra `redirect_uri`, `state`, callback route và session một cách an toàn; không chia sẻ code/token thật.

### Bước 6 — Kiểm tra tầng controller và gateway

Nếu Spring Security cho qua nhưng response vẫn 403/302:

- **Method security** `@PreAuthorize` hoặc domain permission có thể từ chối ở service.
- Controller có thể trả `ResponseEntity.status(FORBIDDEN)`, `redirect:/...` hoặc ném exception được `@ControllerAdvice` xử lý.
- Backend downstream có thể trả 401/403 rồi gateway chuyển nguyên hoặc đổi mã.
- Error dispatch tới `/error` hoặc `FORWARD` tới một view có thể bị chain khác chặn.
- Reverse proxy có thể tự tạo redirect HTTPS hoặc chặn CORS.
- Resource server có thể cần kiểm tra **audience, tenant và quyền theo từng đối tượng** dù token hợp lệ.

Muốn phân biệt, so sánh kết quả **MockMvc tại ứng dụng** với request **qua gateway** trên cùng case hợp lệ/không hợp lệ. Nếu hai kết quả khác nhau, điều tra ở biên proxy/hạ tầng mà không tắt security trong ứng dụng.

## 10. Điểm khó: lỗi ở ERROR/FORWARD dispatch

Servlet có thể có dispatch nội bộ:

~~~text
REQUEST /api/orders
    -> Controller ném exception
    -> ERROR dispatch /error
    -> security matcher/chain được đánh giá lại tùy filter dispatcher mapping
    -> /error bị từ chối
    -> response cuối khác 500/404 dự kiến
~~~

Vì vậy nếu controller thực sự lỗi nhưng client nhận 403 hoặc 302 vào login, hãy kiểm tra dispatcher type và đường `/error`. Trong một số ứng dụng, có thể cần cho phép `DispatcherType.ERROR` hoặc `DispatcherType.FORWARD` có chủ đích:

~~~java
// Trích đoạn minh họa trong authorizeHttpRequests:
.dispatcherTypeMatchers(
    jakarta.servlet.DispatcherType.ERROR
).permitAll()
~~~

Đoạn này **không phải file Java độc lập** và không tự động cần trong mọi cấu hình. Việc cho phép error dispatch phải được đánh giá để không mở endpoint nhạy cảm. Không sửa 403 bí ẩn bằng `anyRequest().permitAll()` cho toàn bộ ứng dụng.

## 11. Khi API trả 302 HTML login: chọn entry point thế nào?

Một API JSON thường nên trả **401** kèm challenge/response phù hợp cho unauthenticated, thay vì redirect login HTML. Một web app session thường nên redirect user tới login. Khi có hai nhóm URL, có hai cách thiết kế:

- **Tách SecurityFilterChain theo path** (như ví dụ): `/api/**` dùng Basic/Bearer và `/web/**` dùng form login.
- **Một chain với request-specific AuthenticationEntryPoint**: dùng `exceptionHandling(...)` và matcher rõ ràng để chọn entry point cho API/web khi kiến trúc bắt buộc chung chain.

Sơ đồ:

~~~text
GET /api/profile  -> API chain -> 401 (nếu anonymous)
GET /web/profile  -> WEB chain -> 302 /login (nếu anonymous)
GET /web/profile  -> WEB chain -> 200 (nếu authenticated)
GET /api/profile  -> API chain -> 403 (nếu authenticated nhưng thiếu quyền)
~~~

**Không dựa chỉ vào header `Accept: application/json`** để đoán client nếu ứng dụng có URL API rõ ràng. Browser có thể gửi Accept khác nhau; lựa chọn entry point phải là **hợp đồng được test**, không vô tình phụ thuộc content negotiation. Nếu nhiều cơ chế xác thực trong một chain, kiểm tra thứ tự `exceptionHandling().defaultAuthenticationEntryPointFor(...)` và matchers theo API hiện hành.

Nếu API dùng bearer token, chỉ đổi entry point không đủ: cần bảo đảm filter/validator bearer được cấu hình đúng và không vô tình chấp nhận cookie session như cơ chế auth API.

## 12. Kiểm tra session, login và logout mà không làm yếu bảo mật

### 12.1. Trường hợp GET login chạy nhưng POST login 403

Đây thường là **login CSRF**:

- GET `/login` render form với CSRF token.
- POST `/login` gửi username/password và CSRF token hợp lệ.
- Nếu token thiếu/sai hoặc session thay đổi, `CsrfFilter` trả 403 trước khi kiểm tra password.

Đừng xóa `csrf()` hoặc thêm `permitAll` tùy tiện rồi nghĩ đã giải quyết xong. `permitAll` **không tắt kiểm tra CSRF**.

### 12.2. Login 302 thành công nhưng GET kế tiếp lại 302 /login

Kiểm tra:

- Browser có lưu cookie session được cấp không?
- Cookie có `Secure` nhưng trang kế tiếp lại HTTP không?
- Cookie `Domain` hoặc `Path` không khớp?
- Có đổi hostname giữa `localhost`, IP, proxy hostname hoặc subdomain không?
- Session ở server/load balancer có sống qua nhiều request/nút không?
- `SecurityContextRepository`, `SessionCreationPolicy`, session fixation protection và custom filter có thay đổi việc lưu context không?
- `SameSite` có phù hợp với luồng OAuth2 cross-site redirect/session cookie không?
- Có thực sự login thành công hay đang đi nhánh failure handler cũng tạo 302?

Không dựa vào mã 302 để kết luận authentication thành công. Kiểm tra **`Location` của POST /login**, session và request sau login.

### 12.3. Logout 302 khác với logout thành công

Spring Security logout thường dùng **POST /logout kèm CSRF** khi CSRF bật. Một GET `/logout` có thể chỉ hiển thị confirmation page. Sau logout có thể 302 tới `/login?logout` hoặc URL đã cấu hình.

Test đúng phải kiểm tra request method, token và user được clear, không chỉ thấy redirect. Session cookie và token cũ có thể bị invalidated nên form giữ từ phiên trước có thể trả 403.

## 13. Kiểm thử những giả thuyết dễ gây nhầm

| Giả thuyết sai | Vì sao nguy hiểm | Cách kiểm chứng |
| --- | --- | --- |
| “401 luôn có nghĩa user thiếu role.” | 401 thường là authentication challenge, không phải authorization deny. | Xem entry point, challenge, có Authentication hợp lệ không. |
| “403 luôn là thiếu `ROLE_ADMIN`.” | Có thể do CSRF, denyAll, CORS, method security, tenant. | Với POST thêm CSRF hợp lệ; kiểm tra policy/dispatcher chain. |
| “302 là lỗi security.” | Với form login, redirect login là behavior dự kiến. | Kiểm tra `Location` và chain. |
| “200 HTML login nghĩa API đã cho truy cập.” | HTTP client có thể tự theo 302. | Xem redirect history và Content-Type. |
| “Có `permitAll` là POST không cần CSRF.” | CSRF filter hoạt động độc lập với URL authorization. | Test POST có/thiếu `csrf()`. |
| “Cấp `ROLE_ADMIN` sẽ qua mọi chỗ.” | Matcher sai, `denyAll`, resource/tenant policy vẫn chặn. | Xem chuỗi đầu tiên match + authority thật + object permission. |
| “Chỉ cần `anyRequest().authenticated()` bên trong `/api/**`.” | Không bảo vệ URL nằm ngoài phạm vi chain. | Test controller mapped ngoài /api bằng catch-all deny. |
| “Mọi request chưa có controller phải trả 404.” | Security có thể trả 401/403 trước MVC routing. | Test path chưa khai báo với authentication phù hợp; so sánh handler mapping. |
| “`@WithMockUser` chứng minh password/login đúng.” | Nó tạo Authentication giả, bỏ qua password provider. | Thêm integration test Basic/formLogin với credentials thật của test fixture. |
| “Tắt filter sẽ làm test HTTP chạy ổn.” | Test xanh giả vì không còn security. | Bật filters trong MockMvc, assert case denied. |
| “CORS `*` sẽ sửa mọi 403.” | Không xử lý role/CSRF/token; có thể tạo cấu hình credential sai. | Tách preflight, response headers, browser console và server behavior. |
| “Giữ cùng hostname là đủ; session sẽ luôn sống.” | Proxy scheme/cookie attributes/server storage có thể sai. | Theo từng redirect, theo cookie metadata và session lifecycle. |

## 14. Quy trình Debug theo HTTP Status — 15 bước

1. Ghi **method, full URL, status đầu tiên, `Location`/`WWW-Authenticate`**, không ghi secret.
2. Dừng tự động theo redirect trong công cụ test để thấy **302 đầu tiên**.
3. Xác nhận hostname, scheme, context path, servlet path, HTTP method và dispatcher type.
4. Tìm **SecurityFilterChain đầu tiên match** request và `@Order` của nó.
5. Xem chain có `formLogin`, `httpBasic`, `oauth2ResourceServer` hay custom provider không.
6. Kiểm tra cơ chế AuthenticationEntryPoint; 401 hay 302 có đúng policy của endpoint không.
7. Xác nhận Authentication có tồn tại và đã xác thực đúng chưa; không suy từ username form.
8. So sánh authorities thực `ROLE_`, `SCOPE_` và `hasAuthority` / `hasRole`.
9. Xem thứ tự `requestMatchers` và `anyRequest()` trong chain.
10. Với POST/PUT/PATCH/DELETE, kiểm tra **CSRF token/session** trước khi quy kết lỗi role.
11. Với CORS, phân biệt **OPTIONS preflight** với request nghiệp vụ.
12. Nếu authorization cho qua, xem method security, domain policy, controller, advice, downstream và error dispatch.
13. Với 302 loop, theo từng `Location`, `Set-Cookie` attributes, proxy headers và session continuity.
14. Viết **negative test + positive test** trong MockMvc cho chính lỗi đã quan sát, gồm status và header/response phù hợp.
15. Chỉ sửa policy sau khi tìm được nguyên nhân; kiểm tra regressions và không nới `permitAll` toàn cục.

## 15. Checklist Production và bảo mật

- [ ] HTTP Basic/bearer/form login được phân chia rõ theo path và chain/entry point.
- [ ] Mọi endpoint cần bảo vệ đều match **ít nhất một SecurityFilterChain**; có catch-all phù hợp.
- [ ] HTTP status và headers theo hợp đồng API/browser; 302 không bị client tự theo che mất nguyên nhân.
- [ ] Không log token, Basic password, session cookie, CSRF token hoặc toàn bộ request headers nhạy cảm.
- [ ] Có kiểm thử anonymous, authenticated thiếu role, đủ role, token sai, CSRF sai và redirect target.
- [ ] CSRF chỉ được disable nơi threat model thật sự cho phép; web session/cookie được bảo vệ.
- [ ] CORS cấu hình origin/method/header/credentials đúng, không thay thế authentication.
- [ ] API bearer token kiểm tra issuer/audience/lifetime/introspection theo provider; không chấp nhận token tự khai.
- [ ] Session cookie có Secure/HttpOnly/SameSite/Domain/Path phù hợp, dùng HTTPS thực tế.
- [ ] Proxy forwarded headers/host/scheme được tin cậy có kiểm soát; không tin header client tự gửi.
- [ ] `/login`, `/logout`, OAuth2 callback, `/error` và dispatch nội bộ nằm trong chain phù hợp.
- [ ] Authorization không chỉ dựa vào URL; có kiểm tra resource/tenant/ownership khi cần.
- [ ] Có test status **và** header: `Location`, `WWW-Authenticate`, response content type.
- [ ] Có correlation ID an toàn để nối trace ở gateway/app nhưng không tiết lộ danh tính/credential.
- [ ] Khi thêm endpoint mới, mặc định bị deny cho đến khi chủ đích thêm policy và tests.

## 16. Tự kiểm tra

**Câu 1.** Tại sao cùng GET `/api/documents` lại có 401 khi anonymous nhưng 403 khi đã login bằng user khác?

**Trả lời:** 401 thường là authentication challenge vì chưa có credentials hợp lệ; 403 là authorization denial vì đã xác thực nhưng thiếu `DOC_READ`.

**Câu 2.** Tại sao POST `/api/documents` bằng user có `DOC_WRITE` vẫn có thể 403?

**Trả lời:** Vì CSRF filter vẫn yêu cầu token theo cấu hình demo. Nếu thiếu CSRF, request bị chặn trước khi rule quyền có tác dụng. Trong MockMvc, thử `csrf()` để cô lập role check.

**Câu 3.** Tại sao GET `/web/home` anonymous trả 302 thay vì 401?

**Trả lời:** Request đi vào web/form-login chain; LoginUrlAuthenticationEntryPoint redirect browser tới `/login`. API Basic chain có entry point khác.

**Câu 4.** Tại sao browser báo 200 HTML khi JavaScript mong JSON?

**Trả lời:** Có thể request API nhận 302 tới login và `fetch` tự theo redirect. Cần xem lịch sử redirect và Content-Type của response cuối.

**Câu 5.** Có `ROLE_ADMIN` rồi nhưng vẫn 403; điều tra gì trước?

**Trả lời:** Xác nhận đúng SecurityFilterChain, `securityMatcher` và rule đầu tiên khớp; kiểm tra authority thực, `denyAll`, method security, ownership, CSRF và dispatcher type.

**Câu 6.** 302 sau POST login có chứng minh login thành công không?

**Trả lời:** Không. Cả login success/failure handler hoặc controller khác đều có thể redirect. Xem `Location`, session và request bảo vệ tiếp theo.

**Câu 7.** Để test 403 do thiếu role trên POST, tại sao cần gửi CSRF token hợp lệ?

**Trả lời:** Vì nếu thiếu token, `CsrfFilter` có thể chặn trước và test vẫn trả 403 dù authorization rule hoàn toàn sai.

**Câu 8.** Nếu `/api/unlisted` không có controller nhưng trả 403, có nghĩa MVC có route đó không?

**Trả lời:** Không. Security chain match path và `denyAll` có thể chặn trước bước tìm controller. 403 và 404 phản ánh các tầng xử lý khác nhau.

**Câu 9.** Tại sao lỗi CORS preflight không nên chữa bằng `permitAll` mọi endpoint?

**Trả lời:** Vì CORS/preflight và authorization của request chính là hai vấn đề khác nhau. Nới quyền chung tạo rủi ro truy cập trái phép mà chưa chắc sửa được CORS.

**Câu 10.** Thứ đầu tiên cần nhìn khi debug một redirect lặp là gì?

**Trả lời:** Response 302 đầu tiên, chuỗi `Location` và thuộc tính session cookie theo từng bước, sau đó xác định chain/entry point và proxy/callback.

---

**Kết luận:** Điều tra **401, 403 và 302** trong Spring Security Servlet là bài toán **xác định tầng phát sinh response**. 401 thường gắn với authentication challenge; 403 có thể do authorization, CSRF hoặc policy khác; 302 thường là điều hướng của form login/success handler nhưng cũng có thể đến từ controller/gateway. Luôn bắt đầu bằng request đầu tiên và headers, tìm SecurityFilterChain đúng, kiểm tra authentication/authority/CSRF, theo redirect + session, rồi dùng MockMvc test tích cực và tiêu cực để chứng minh nguyên nhân trước khi sửa cấu hình.