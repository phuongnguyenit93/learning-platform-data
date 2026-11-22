# Rà soát cấu hình khi thêm endpoint, vai trò hoặc phương thức đăng nhập

## 1. Vì sao mọi thay đổi nhỏ đều cần rà soát bảo mật?

Trong một ứng dụng Spring Security, thêm một controller, mở thêm một vai trò hoặc bật cách đăng nhập mới có thể thay đổi **ai được truy cập tài nguyên nào, bằng loại danh tính nào và qua chuỗi filter nào**. Vấn đề thường không nằm ở một dòng cấu hình sai cú pháp mà ở khoảng trống giữa nhiều lớp: URL được định tuyến đúng nhưng không khớp `SecurityFilterChain`; vai trò mới được cấp quá rộng; phương thức đăng nhập mới vô tình cho qua bước xác thực dành cho luồng khác.

Ví dụ ba thay đổi tưởng như độc lập:

- Đội sản phẩm thêm `POST /api/reports` để tạo báo cáo. Họ mới cấu hình quyền cho `GET /api/reports/summary` và giả định các request khác tự an toàn.
- Đội quản trị thêm vai trò `REPORT_EDITOR`. Họ chỉ sửa danh sách role ở IdP nhưng quên kiểm tra mapping `ROLE_`, role hierarchy và quyền thao tác dữ liệu thực tế.
- Đội nền tảng bật HTTP Basic, OIDC hoặc bearer token trong ứng dụng vốn chỉ có form login. Họ thêm cơ chế mới mà không kiểm tra request nào được đăng nhập bằng cơ chế nào, CSRF, session, redirect và error handling.

**Rà soát cấu hình** là quá trình so sánh chính sách dự định với **cách mọi request thực sự được xử lý**, bao gồm trường hợp bình thường, thiếu xác thực, thiếu quyền, sai phương thức HTTP và những đường dẫn chưa được khai báo. Mục tiêu là **mở đúng quyền cần thiết mà không mở rộng bề mặt tấn công ngoài ý định**.

Bài học thuộc nhóm **Thiết kế ứng dụng** của module **Spring Security – fundamentals**, sử dụng Spring Security Servlet, Java 17+ và Spring Boot 3.x/Spring Security 6.x. Với WebFlux, cần dùng các API reactive tương ứng; ví dụ `HttpSecurity` ở đây không áp dụng trực tiếp.

### Kết quả học tập

Sau bài này, bạn có thể:

1. Xác định chính xác tác động của việc thêm endpoint, thay đổi role hoặc thêm login mechanism.
2. Phân biệt phạm vi `SecurityFilterChain` với thứ tự rule trong `authorizeHttpRequests`.
3. Đặt chính sách **deny by default** và test cả trường hợp được phép lẫn bị cấm.
4. Phân biệt `hasRole`, `hasAuthority`, HTTP method, endpoint-level policy và bảo mật dữ liệu ở service.
5. Kiểm tra CSRF, CORS, session, cookie, redirect, lỗi 401/403 khi thay cơ chế đăng nhập.
6. Viết bộ regression test chứng minh một thay đổi không mở quyền ở URL/role/luồng khác.

## 2. Mô hình rà soát: thay đổi gì, ảnh hưởng tới đâu?

Một thay đổi bảo mật cần được mô tả bằng ít nhất sáu chiều:

| Chiều | Câu hỏi cần trả lời |
| --- | --- |
| **Tài nguyên** | URL, HTTP method, controller, service, tenant và dữ liệu nào bị ảnh hưởng? |
| **Danh tính** | Anonymous, browser user, service account hay token do bên thứ ba cấp? Ai xác thực nó? |
| **Quyền** | Role, authority, scope, owner/tenant và điều kiện nghiệp vụ nào cho phép thao tác? |
| **Security chain** | `SecurityFilterChain` nào được chọn? Có filter xác thực/CORS/CSRF/authorization cần thiết không? |
| **Trạng thái** | Session, cookie, CSRF token, remember-me, refresh token, logout và thời hạn thế nào? |
| **Giao diện lỗi** | 401, 403, redirect login, `WWW-Authenticate` và response JSON có đúng hợp đồng không? |

Ba nhóm thay đổi có **dấu hiệu rủi ro** khác nhau:

| Loại thay đổi | Sai sót thường gặp | Bằng chứng nghiệm thu |
| --- | --- | --- |
| **Thêm endpoint** | Chưa có rule, rule quá rộng, chỉ bảo vệ GET mà quên POST/DELETE, bỏ qua phân quyền đối tượng. | Ma trận URL × method × actor có ca chấp nhận/từ chối. |
| **Thêm/chỉnh vai trò** | Mapping sai tiền tố `ROLE_`, role mới kế thừa admin ngoài ý muốn, token cũ chưa được cập nhật/revoke. | Test quyền theo từng role, test thiếu quyền và test cùng tài nguyên khác owner. |
| **Thêm login mechanism** | API nhận session ngoài ý muốn, browser nhận bearer như admin, login endpoint ngoài chain, lỗi 302 thay vì 401. | Test tách chain, xác thực hợp lệ/sai, CSRF/CORS, 401/403, session/logout. |

Không nên bắt đầu bằng việc thêm `permitAll()` để “chạy thử endpoint”. Hãy viết rõ **ai được làm gì** trước, rồi mới thay cấu hình.

## 3. Những ranh giới phải xác minh khi dùng Spring Security Servlet

### 3.1. Servlet filter chain và SecurityFilterChain

Luồng giản lược:

```text
HTTP request
    |
    v
Servlet container filters
    |
    v
DelegatingFilterProxy ("springSecurityFilterChain")
    |
    v
FilterChainProxy
    |
    +-- SecurityFilterChain @Order(1): ví dụ /api/**
    |        -> security filters -> AuthorizationFilter
    |
    +-- SecurityFilterChain @Order(2): browser/fallback
             -> security filters -> AuthorizationFilter
    |
    v
DispatcherServlet -> Controller -> Service
```

`FilterChainProxy` chọn **SecurityFilterChain đầu tiên có matcher phù hợp**. Nó **không gộp tất cả chain** cùng khớp request. Nếu một chain `@Order(1)` bắt `/api/**`, các request `/api/**` sẽ không tiếp tục chạy thêm chain browser fallback.

Bẫy quan trọng: `http.securityMatcher("/api/**")` giới hạn **toàn bộ chain**. Nếu bạn thêm một endpoint ngoài đường dẫn đó mà không có chain fallback, endpoint có thể **không được Spring Security bảo vệ**. Mặt khác, nếu chain fallback có `anyRequest().permitAll()`, bạn đã khiến một URL mới vô tình công khai.

**Chiến lược khuyến nghị:** chỉ định matcher cụ thể cho chain ưu tiên, giữ một fallback chain có chính sách rõ ràng và không công khai ngoài ý định.

### 3.2. `securityMatcher` khác `requestMatchers`

```java
http
    .securityMatcher("/api/**")                // Chọn chain
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()    // Chọn quyền trong chain
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().denyAll()
    );
```

- `securityMatcher` xác định request có dùng chain này hay không.
- `requestMatchers` trong `authorizeHttpRequests` xác định **rule đầu tiên** được áp dụng **trong chain đã chọn**.
- `permitAll()` cho phép theo rule nhưng **không bỏ qua các security filter khác**. Các cơ chế bảo vệ như security headers, CSRF, CORS và custom filter vẫn có thể áp dụng.
- `web.ignoring()` bỏ qua Spring Security filter chain cho các đường dẫn được chọn; cần cân nhắc vì mất cả header/security protections. Với endpoint/public static resource thường ưu tiên `permitAll()`.

### 3.3. Thứ tự rule có thể mở rộng quyền

Cấu hình có lỗi phổ biến:

```java
// SAI về ý định: rule rộng đứng trước làm rule admin ở dưới không đạt tới.
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Nếu request `/api/admin/users` khớp rule đầu tiên, Spring Security chỉ yêu cầu đăng nhập thay vì role ADMIN.

Thứ tự đúng phải ưu tiên **từ cụ thể tới tổng quát**:

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
```

Cần review quy tắc rộng nằm phía trước và matcher riêng cho HTTP method. `GET /orders` khác `POST /orders` về tác động; một rule chung `requestMatchers("/orders/**").authenticated()` có thể cấp quyền ghi cho người chỉ được xem.

### 3.4. Dispatcher và tầng method/đối tượng

HTTP request có thể có các dispatcher `REQUEST`, `FORWARD`, `ERROR`, `ASYNC`. Spring Security 6 dùng `AuthorizationFilter` để xử lý các request dispatch liên quan theo cấu hình. Khi trang lỗi hoặc forward bị chặn, cân nhắc chính sách `dispatcherTypeMatchers` phù hợp; không giải quyết bằng `anyRequest().permitAll()`.

Ngay cả khi HTTP rule cho phép `GET /api/orders/{id}` với role VIEWER, backend vẫn phải xác minh **đơn hàng đó có thuộc tenant/user được phép xem không**. Endpoint authorization không tự thay thế object-level authorization hoặc kiểm tra quyền trên service. Với nhiều code path gọi cùng service, có thể dùng method security như `@PreAuthorize` sau khi bật `@EnableMethodSecurity`, hoặc kiểm tra quyền trực tiếp ở domain/service.

## 4. Thêm endpoint: lập chính sách trước khi thêm controller

Mẫu review khi thêm một endpoint:

```text
Endpoint: POST /api/reports
Tác dụng: tạo báo cáo mới
Actor: nhân viên có vai trò REPORT_EDITOR
Authentication: API HTTP Basic trong ví dụ học; production sẽ cân nhắc token
Authorization: ROLE_REPORT_EDITOR + quyền tạo trong tenant tương ứng
CSRF: Bật trong ví dụ vì Basic có thể được browser gửi tự động
Body: dữ liệu được validate và giới hạn kích thước
Response: 200/201 tùy hợp đồng, không chứa secret/stacktrace
Missing authentication: 401 (API)
Authenticated but missing role: 403
Wrong method/unknown URL: không được mở quyền
Tests: editor OK; viewer 403; no credentials 401; no CSRF 403
```

Khi duyệt thay đổi, nên lập bảng quyền trước:

| HTTP request | Anonymous | REPORT_VIEWER | REPORT_EDITOR | ADMIN |
| --- | --- | --- | --- | --- |
| `GET /api/public/ping` | 200 | 200 | 200 | 200 |
| `GET /api/reports/summary` | 401 | 200 | 200 | 403 nếu ADMIN không có role báo cáo |
| `POST /api/reports`, CSRF hợp lệ | 401 | 403 | 200 | 403 nếu ADMIN không có role báo cáo |
| `POST /api/reports`, thiếu CSRF | 403 theo CSRF filter | 403 | 403 | 403 |
| `DELETE /api/reports/7` | Không được phép | Không được phép | Không được phép | Không được phép |
| `GET /api/unknown` | Không được phép | Không được phép | Không được phép | Không được phép |

Các status cụ thể phụ thuộc **filter chain và hợp đồng**. Ví dụ Spring Security có thể trả 401 cho anonymous GET, 403 cho người xác thực thiếu quyền, và 403 với POST thiếu/sai CSRF ngay cả trước bước phân quyền. Ở web dùng form login, anonymous có thể được **302 redirect tới `/login`** thay vì 401. Đừng gán cùng một kỳ vọng cho API và trang web.

### 4.1. Đối chiếu cả URL lẫn HTTP method

Điểm dễ bỏ sót:

- `GET /api/reports` được cho phép **không** mặc nhiên cho phép `POST /api/reports`.
- Controller thêm `@DeleteMapping` hoặc `@PatchMapping` mà giữ rule `/api/reports/**` quá rộng có thể mở quyền nguy hiểm.
- Path parameter `{id}` không tự tạo quyền trên resource tương ứng; cần ownership/tenant check.
- Tránh sử dụng URL pattern dựa vào chuỗi `contains("admin")` trong custom filter; dùng `RequestMatcher` phù hợp và kiểm thử.
- Nếu có trailing slash, encoded path, context path, reverse proxy rewrite, phải test dạng URL thực tế do hạ tầng chuyển tới Spring MVC.
- Khi thêm webhook/file upload/stream, cân nhắc request body size, MIME type, replay protection, signatures và rate limit.
- Với endpoint tạo/cập nhật, đừng truyền thông tin xác thực hoặc token qua URL/log để dễ debug.

### 4.2. Public endpoint vẫn cần bảo vệ

Một health check hoặc public catalog có thể dùng `permitAll()`, nhưng vẫn cần chính sách CORS, security headers, rate limit, data minimization và validation. **Công khai** không có nghĩa được phép trả dữ liệu nhạy cảm hoặc bỏ qua toàn bộ security chain. Hãy chỉ công khai đúng URL và method cần thiết.

## 5. Thêm vai trò: rà soát authority mapping và giới hạn quyền

### 5.1. `hasRole` khác `hasAuthority`

Trong cấu hình thông dụng:

```java
.requestMatchers("/ui/admin/**").hasRole("ADMIN")
```

`hasRole("ADMIN")` thường yêu cầu authority `ROLE_ADMIN` (Spring Security tự thêm tiền tố role mặc định). Trong khi đó:

```java
.requestMatchers("/api/reports/**").hasAuthority("REPORTS_READ")
```

`hasAuthority("REPORTS_READ")` so sánh chính xác chuỗi authority, không tự thêm `ROLE_`.

Nếu `UserDetails` được tạo bằng:

```java
User.withUsername("editor")
    .password(encodedPassword)
    .roles("REPORT_EDITOR")
    .build();
```

nó cung cấp authority `ROLE_REPORT_EDITOR` theo tiền tố mặc định. Khi dùng `hasRole("REPORT_EDITOR")`, **không viết `hasRole("ROLE_REPORT_EDITOR")`** trừ khi đã hiểu cấu hình role prefix đặc biệt. Khi token do IdP cấp dùng `scope`, các scope thường được chuyển thành authority dạng `SCOPE_...` và phải dùng rule tương ứng; **không tự giả định JWT scope bằng user role**.

### 5.2. Quyền mới không tự kế thừa theo tên gọi

Không có nghĩa vụ mặc định rằng:

```text
ROLE_ADMIN > ROLE_REPORT_EDITOR > ROLE_REPORT_VIEWER
```

Tên role chỉ là tên. Nếu application yêu cầu role hierarchy, phải cấu hình và test riêng. Nếu không, một tài khoản chỉ có `ROLE_ADMIN` **không tự có** `ROLE_REPORT_EDITOR` trong phép kiểm tra `hasRole("REPORT_EDITOR")`.

Trong bài thực hành, chính sách cố tình **không suy ra quyền báo cáo từ ADMIN**. Đây là lựa chọn để khẳng định quyền được cấp **minh thị** và tránh suy diễn “admin luôn làm mọi việc” không qua review. Hệ thống thật có thể chọn hierarchy, nhưng phải ghi rõ và kiểm thử.

### 5.3. Khi role thay đổi tại IdP hoặc database

Kiểm tra:

1. Nguồn cấp role là database, LDAP, IdP, JWT claim hay một phép chuyển đổi tùy chỉnh?
2. Khi bỏ role khỏi tài khoản, session/JWT **đang còn hiệu lực** có giữ quyền cũ tới khi hết hạn không?
3. Cache của `UserDetailsService`, Session, JWT và API gateway có cần invalidation/revoke không?
4. Role có phân biệt môi trường, tenant và phạm vi tài nguyên không?
5. Có cần MFA hoặc xác thực tăng cường cho role mới không?
6. Ai duyệt quyền, thời hạn cấp, nhật ký thay đổi và quy trình thu hồi?
7. Khi không có role phù hợp, backend trả 403 hay có một luồng kinh doanh đặc biệt?

**Không giải quyết bằng cách cho `anyRequest().authenticated()` rồi kiểm tra role ở frontend.** Một người dùng có thể gọi API trực tiếp và bỏ qua UI.

### 5.4. Tầng HTTP, method và object-level authorization

HTTP rule là cửa đầu tiên, không thay thế phân quyền nghiệp vụ. Ví dụ:

```java
// Trích đoạn trong service, chỉ có ý nghĩa khi đã bật @EnableMethodSecurity
// và biến permissionService được tiêm từ bean thực tế.
@PreAuthorize("@permissionService.canReadOrder(authentication, #orderId)")
public OrderDto getOrder(long orderId) {
    return orderRepository.findDto(orderId);
}
```

Đây là **minh họa riêng**, không phải method tự chạy độc lập của demo phía dưới. Khi áp dụng, cần khai báo bean `permissionService`, repository và DTO, bảo đảm proxy/method-security interception thực sự hoạt động. Dùng integration test truy cập một order khác tenant để kiểm chứng object-level access.

## 6. Thêm phương thức đăng nhập: thay đổi cả luồng, không chỉ thêm filter

Khi ứng dụng vốn chỉ có form login bắt đầu hỗ trợ HTTP Basic, OAuth2 login, bearer token hoặc passkey, cần trả lời **những request nào được phép dùng cách nào**.

| Cơ chế | Mục tiêu thường gặp | Điểm phải rà soát |
| --- | --- | --- |
| Form login + `HttpSession` | Browser interactive user | CSRF, session fixation, cookie, logout, redirect và login failure. |
| HTTP Basic | API tương thích/nhu cầu hạn chế | HTTPS; browser có thể tự gửi credentials; CSRF cho unsafe request; không dùng password người dùng làm service credential. |
| OAuth2/OIDC login | Người dùng đăng nhập qua IdP | Authorization Code + PKCE theo loại client; state/nonce, callback/login/logout endpoint nằm trong chain phù hợp. |
| Bearer/JWT Resource Server | API nhận access token | Chữ ký, issuer, audience, expiry, scope, 401/403, `WWW-Authenticate`; quản lý token tách session. |
| OAuth2 Client Credentials | Workload gọi API tự động | Client identity, secret/cert hoặc workload federation, scope tối thiểu, TTL và khả năng thu hồi. |
| Passkey/WebAuthn | Người dùng tương tác | Challenge/origin/RP ID, account binding, recovery, session lifecycle và step-up. |

Điểm thiết kế chính:

- **Form login** có thể trả `302 /login` cho người chưa đăng nhập. **API JSON** thường muốn 401/403 rõ ràng. Nếu bật hai cơ chế trong cùng chain, kiểm tra chính xác entry point nào sẽ xử lý từng request.
- **`SecurityFilterChain` tách theo URL** giúp giữ hành vi riêng cho API và browser; cần nhớ login/logout/callback URL phải được chain tương ứng xử lý. Nếu chain chỉ match `/ui/**` mà filter login được cấu hình tại `/login`, request `POST /login` có thể nằm **ngoài chain** đó.
- Nếu API **chỉ** dùng bearer token do client tự đính header và không dùng credential trình duyệt tự gửi, có thể thiết kế tắt CSRF cho chain stateless đó sau khi review. Nếu API dùng **cookie hoặc HTTP Basic trong browser**, không mặc định “stateless = miễn CSRF”.
- CORS không phải phân quyền: khi frontend cross-origin, `http.cors()` phải xử lý preflight trước xác thực; không thêm wildcard origin để chữa lỗi 401.
- `OAuth2ResourceServer` xác minh token người gọi; `OAuth2Client` là ứng dụng đi xin token để gọi API khác; `oauth2Login` là luồng người dùng tương tác. Ba chức năng không tương đương.
- Logout `HttpSession` không tự thu hồi JWT/access token đã phát hành. Cần test lại refresh/revocation/session với đúng hợp đồng.
- Khi có nhiều cách đăng nhập, giữ chiến lược chống **account linking sai**, session fixation, credential stuffing, login CSRF và confused deputy.

## 7. Ví dụ hoàn chỉnh: hai chain, role rõ ràng và mặc định từ chối

Ta tạo ứng dụng học với hai nhóm:

**API `/api/**`:** dùng HTTP Basic qua HTTPS trong ví dụ; có hai role báo cáo. Giữ CSRF cho unsafe method vì browser có thể tự thêm Basic credentials. API đặt `SessionCreationPolicy.STATELESS`, nhưng điều này **không tự miễn CSRF**. Với production M2M, cân nhắc OAuth2 bearer/mTLS thay mật khẩu.

**Browser `/ui/**`:** dùng form login + session; có trang home cho người đã xác thực và trang admin chỉ dành cho `ROLE_ADMIN`. Một fallback rule từ chối các URL chưa khai báo.

Khi thêm endpoint/role/login, ta sẽ dùng chính bộ test để chứng minh không có quyền nào bị nới rộng ngoài ý định.

### 7.1. Thư viện và cấu trúc

Dự án **Spring Boot 3.x / Spring Security 6.x / Java 17+**, có Gradle plugin và wrapper. Thêm các dependency trong `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **khối dependencies trong dự án Boot đã có plugin**, không phải toàn bộ build script. Tạo các class sau cùng package `demo.securityreview`.

### 7.2. Lớp khởi động

Tệp `src/main/java/demo/securityreview/SecurityReviewApplication.java`:

```java
package demo.securityreview;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityReviewApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityReviewApplication.class, args);
    }
}
```

### 7.3. Cấu hình Spring Security

Tệp `src/main/java/demo/securityreview/SecurityConfig.java`:

```java
package demo.securityreview;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/public/ping"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/reports/summary"
                ).hasAnyRole("REPORT_VIEWER", "REPORT_EDITOR")
                .requestMatchers(
                    HttpMethod.POST, "/api/reports"
                ).hasRole("REPORT_EDITOR")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // CHỦ ĐÍCH không disable CSRF ở API Basic:
        // trình duyệt có thể tự đính kèm HTTP Basic credentials.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/login", "/error"
                ).permitAll()
                .requestMatchers(
                    "/ui/admin/**"
                ).hasRole("ADMIN")
                .requestMatchers(
                    "/ui/**"
                ).authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(form -> form
                .defaultSuccessUrl("/ui/home", true)
            )
            .logout(Customizer.withDefaults());

        // Chain fallback này không có securityMatcher, bao các URL còn lại.
        // CSRF được giữ theo mặc định cho browser.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode("viewer-demo"))
                .roles("REPORT_VIEWER")
                .build(),
            User.withUsername("editor")
                .password(encoder.encode("editor-demo"))
                .roles("REPORT_EDITOR")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-demo"))
                .roles("ADMIN")
                .build()
        );
    }
}
```

**Vì sao cấu hình này có chủ đích?**

1. `@Order(1)` và `securityMatcher("/api/**")` khiến API chain được chọn cho đúng nhánh API; chain browser không can thiệp vào API sau khi đã có match.
2. `@Order(2)` là fallback không có matcher giới hạn, giúp các URL khác vẫn chịu cơ chế bảo mật. `anyRequest().denyAll()` ở cuối ngăn “mở cửa” cho URL mới chưa được review.
3. Rule `GET /api/public/ping` public nhưng **chỉ GET**. Những HTTP method khác đến cùng URL không được tự cho phép.
4. `GET /api/reports/summary` dành cho VIEWER hoặc EDITOR. `POST /api/reports` chỉ dành cho EDITOR; chính sách **không** suy diễn ADMIN luôn được quyền báo cáo.
5. `SessionCreationPolicy.STATELESS` dành cho API: không sử dụng session để lưu `SecurityContext`. HTTP Basic vẫn có thể được browser tự đính kèm; vì thế **CSRF vẫn được bật**. Khi triển khai API thật cần thiết kế cơ chế phát/nhận CSRF token cho các client dùng cookie/Basic, hoặc dùng kiến trúc bearer không ambient credential và rà soát trước khi thay chính sách.
6. Browser chain giữ form login, redirect và CSRF. `/login` nằm trong fallback chain nên form login filter xử lý được endpoint đó.
7. Nếu admin chưa được cấp `ROLE_REPORT_EDITOR`, họ không được POST báo cáo. Muốn ADMIN có quyền EDITOR là **một yêu cầu thiết kế cần duyệt**, không phải một điều hiển nhiên từ tên role.
8. Password trong ví dụ chỉ phục vụ test; không dùng credential cố định này trong production. HTTP Basic cần TLS và chính sách brute-force protection phù hợp.

### 7.4. Controller

Tệp `src/main/java/demo/securityreview/DemoController.java`:

```java
package demo.securityreview;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    public Map<String, String> ping() {
        return Map.of("result", "pong");
    }

    @GetMapping("/api/reports/summary")
    public Map<String, Integer> summary() {
        return Map.of("count", 2);
    }

    @PostMapping("/api/reports")
    public Map<String, Boolean> createReport() {
        return Map.of("created", true);
    }

    @GetMapping("/ui/home")
    public Map<String, String> home(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }

    @GetMapping("/ui/admin/panel")
    public Map<String, Boolean> adminPanel() {
        return Map.of("admin", true);
    }
}
```

Chú ý: controller trả `Map` để kiểm tra JSON đơn giản, không phụ thuộc database. Một hệ thống thật vẫn cần input validation, giao dịch, object-level permissions, kiểm toán, giới hạn tải và kiểm soát dữ liệu. Không suy luận chỉ vì HTTP path đã được bảo vệ thì mọi bản ghi trong service đều được phép truy cập.

### 7.5. Trạng thái lỗi đúng theo từng luồng

| Request | Cơ chế | Tình trạng | Kỳ vọng |
| --- | --- | --- | --- |
| `GET /api/reports/summary` không credentials | Basic API | Chưa xác thực | 401 và challenge Basic phù hợp. |
| `GET /api/reports/summary` với viewer | Basic API | Đã xác thực, có role | 200. |
| `POST /api/reports` với viewer + CSRF | Basic API | Có xác thực, thiếu role EDITOR | 403. |
| `POST /api/reports` với editor, thiếu CSRF | Basic API | Bị bảo vệ CSRF chặn | 403, dù role đủ. |
| `POST /api/reports` với editor + CSRF | Basic API | Đúng role và CSRF | 200. |
| `GET /ui/home` anonymous | Form browser | Chưa đăng nhập | Thường redirect 302 tới `/login`. |
| `GET /ui/admin/panel` với viewer | Form browser | Thiếu ROLE_ADMIN | 403. |
| `GET /ui/admin/panel` với admin | Form browser | Có ROLE_ADMIN | 200. |

**Không nhầm 302 với 401:** browser form login có thể redirect, API Basic trả 401. Nếu sau này thêm OAuth2 login hoặc dùng API JSON, cần chủ động thống nhất hợp đồng response/redirect thay vì để frontend suy luận từ HTML login page.

## 8. Kiểm thử regression: thêm thứ mới không làm đổi quyền cũ

Spring Security Test có helper `httpBasic()`, `csrf()`, `user()` và `formLogin()`. Demo sử dụng MockMvc có Spring Security filter chain thông qua `@SpringBootTest` và `@AutoConfigureMockMvc`.

Tệp `src/test/java/demo/securityreview/SecurityReviewTests.java`:

```java
package demo.securityreview;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityReviewTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicPingDoesNotRequireLogin() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("pong"));
    }

    @Test
    void privateReportWithoutCredentialsRequiresBasicLogin()
            throws Exception {
        mvc.perform(get("/api/reports/summary"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void viewerCanReadReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("viewer", "viewer-demo")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(2));
    }

    @Test
    void editorCanReadReport() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("editor", "editor-demo")))
            .andExpect(status().isOk());
    }

    @Test
    void viewerCannotCreateReportEvenWithValidCsrf()
            throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("viewer", "viewer-demo"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCannotCreateReportWithoutCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void editorCanCreateReportWithCsrf() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("editor", "editor-demo"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.created").value(true));
    }

    @Test
    void administratorIsNotImplicitlyReportEditor() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("admin", "admin-demo"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void undeclaredApiRouteIsRejectedForAuthenticatedUser()
            throws Exception {
        mvc.perform(get("/api/not-declared")
                .with(httpBasic("editor", "editor-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void undeclaredHttpMethodIsRejectedEvenForEditor()
            throws Exception {
        mvc.perform(delete("/api/reports/7")
                .with(httpBasic("editor", "editor-demo"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousBrowserUserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/ui/home"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("http://localhost/login"));
    }

    @Test
    void viewerCanReadBrowserHome() throws Exception {
        mvc.perform(get("/ui/home")
                .with(user("viewer").roles("REPORT_VIEWER")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.user").value("viewer"));
    }

    @Test
    void viewerCannotReadAdminPanel() throws Exception {
        mvc.perform(get("/ui/admin/panel")
                .with(user("viewer").roles("REPORT_VIEWER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReadAdminPanel() throws Exception {
        mvc.perform(get("/ui/admin/panel")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.admin").value(true));
    }

    @Test
    void validFormLoginRedirectsToBrowserHome() throws Exception {
        mvc.perform(formLogin()
                .user("viewer")
                .password("viewer-demo"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/ui/home"));
    }

    @Test
    void httpBasicIsNotAnAlternativeLoginForBrowserChain()
            throws Exception {
        mvc.perform(get("/ui/admin/panel")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().is3xxRedirection());
    }
}
```

**Lưu ý về redirect URL:** khi test với MockMvc, `LoginUrlAuthenticationEntryPoint` thường tạo Location tuyệt đối `http://localhost/login` trong môi trường giả lập của MockMvc. Nếu ứng dụng có context path, proxy, host tùy chỉnh hoặc khác cấu hình redirect, hãy assert pattern/URL phù hợp hợp đồng thực tế. Không thay kiểm thử redirect bằng giả định anonymous luôn trả 403.

Chạy từ gốc dự án đã cấu hình Gradle wrapper:

```bash
./gradlew test --tests demo.securityreview.SecurityReviewTests
```

Bộ ví dụ có **16 test**. Đây là **kỳ vọng kiểm thử của tài liệu**, không phải khẳng định đã thực thi trên máy người đọc. Những test MockMvc tạo HTTP request giả lập và sử dụng filter chain, không chứng minh được mọi đặc điểm của reverse proxy, browser cookie và hệ thống IdP ngoài ứng dụng.

**Test coverage theo thay đổi:**

| Thay đổi | Test bảo đảm quyền mới | Test chống mở quyền sai |
| --- | --- | --- |
| Thêm public GET | Anonymous GET `/api/public/ping` trả 200 | DELETE/POST chưa khai báo không được mở. |
| Thêm report viewer | VIEWER đọc summary 200 | VIEWER tạo report 403. |
| Thêm report editor | EDITOR đọc và POST có CSRF thành công | EDITOR POST thiếu CSRF 403; DELETE chưa khai báo 403. |
| Thêm/admin role | ADMIN đọc trang quản trị UI | ADMIN không tự thành REPORT_EDITOR. |
| Bật Basic cho API | HTTP Basic đúng credentials truy cập API | API thiếu credentials 401, không tự dùng web login redirect. |
| Bật form login cho UI | Form login thành công, UI role đúng | HTTP Basic không tự thành phiên browser. |
| Giữ fallback | Controller mới cần được khai báo policy trước | URL không khai báo bị deny ngay cả khi đã xác thực. |

### 8.1. Vì sao test cả 401, 403, 302 và 200?

- **200** chứng minh chức năng hợp lệ không bị chặn nhầm.
- **401** chứng minh API thiếu/sai credentials được yêu cầu xác thực đúng giao thức.
- **403** chứng minh role/CSRF/default deny hoạt động với request không được phép.
- **302** hoặc status redirect tương ứng chứng minh browser vẫn đi theo luồng form login, không bị cơ chế API làm thay đổi.
- Với endpoint tạo mới, nhiều ứng dụng trả 201. Khi đổi hợp đồng controller, sửa assertion theo status và location/body dự định; đừng biến 201 thành 200 chỉ để phù hợp một test cũ.

**Không chỉ dùng `@WithMockUser` để chứng minh cả login.** Nó giả lập `Authentication` để test phân quyền, nhưng không xác nhận password encoder, form authentication hoặc JWT signature. Test `formLogin()` xác nhận login flow ở mức Spring Security/MockMvc, còn end-to-end login có cookie/MFA/IdP cần integration test riêng.

### 8.2. MockMvc không thay thế test bảo mật ngoài JVM

Một bộ test trên không tự kiểm tra:

- Cookie `Secure`/`HttpOnly`/`SameSite` trong browser thật;
- CORS preflight từ origin khác hoặc gateway xử lý lỗi 401/403;
- JWT issuer/audience/signature khi chuyển sang bearer token;
- Race condition, session fixation, logout/session timeout trên Servlet container thực;
- Tài nguyên bị cache ở CDN, API gateway hoặc browser back-forward cache;
- Quyền trên dữ liệu thực tế giữa hai tenant và audit log;
- Cấu hình reverse proxy path rewrite, host/prefix và lỗi khi hạ tầng chuyển tuyến.

Các phần này cần integration/end-to-end test ở môi trường gần production.

## 9. Khi thêm một cơ chế đăng nhập mới, cần thêm những regression test nào?

### 9.1. Chuyển API từ Basic sang Bearer token

Nếu API chuyển từ Basic sang OAuth2 Resource Server:

- Thay `httpBasic()` bằng `oauth2ResourceServer(oauth -> oauth.jwt(...))` hoặc cơ chế token phù hợp trong **đúng chain API**.
- Xác thực chữ ký, issuer, audience, expiration, token type và authority mapping theo issuer.
- Kiểm tra 401 với thiếu/sai token, 403 với token hợp lệ nhưng thiếu scope; challenge `WWW-Authenticate: Bearer` đúng giao thức.
- Chỉ cân nhắc tắt CSRF trong API nếu nó **không dùng** cookie/session/Basic tự động đính kèm để xác thực các thao tác nguy hiểm. Giữ CSRF cho browser chain.
- Viết test ngăn browser session tự thay thế bearer token ở `/api/**` và ngăn service token truy cập trang người dùng nếu chính sách không cho phép.
- Kiểm tra `Authorization` không bị ghi vào URL, log hoặc error response; bearer token cần HTTPS.

**Trích đoạn minh họa phương pháp (không ghép trực tiếp với demo Basic):**

```java
http
    .securityMatcher("/api/**")
    .sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
    )
    .csrf(csrf -> csrf.disable()) // Chỉ khi API này chỉ dùng bearer header
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/reports/**").hasAuthority("SCOPE_reports.read")
        .anyRequest().denyAll()
    )
    .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
```

Để chạy trích đoạn này, dự án cần `spring-boot-starter-oauth2-resource-server` và `JwtDecoder`/JWK/issuer thật, không thể chỉ copy thêm dòng `oauth2ResourceServer` rồi cho rằng validation JWT đã xong.

### 9.2. Bật OIDC login cho browser

Khi thêm `oauth2Login()`, rà soát các URL như `/oauth2/authorization/{registrationId}`, `/login/oauth2/code/{registrationId}` và logout endpoint. Nếu browser chain chỉ match `/ui/**`, các endpoint xác thực ở ngoài phạm vi có thể không được filter tương ứng xử lý.

Phải kiểm thử:

- Redirect khởi tạo authorization, callback URI khớp IdP, `state`, PKCE và nonce theo giao thức.
- Login thành công tạo đúng principal/authorities và không tự nâng `ROLE_ADMIN` từ claim chưa thẩm định.
- Login thất bại/IdP lỗi trả thông điệp an toàn, không lộ token/secret.
- Session fixation, logout local, logout IdP và behavior khi SSO còn hiệu lực.
- Account linking: một email trùng không tự chứng minh hai tài khoản thuộc cùng người nếu issuer/subject chưa được xác thực.
- API `/api/**` vẫn trả 401/403 theo hợp đồng, không vô tình redirect sang HTML login/IdP.

### 9.3. Bổ sung login bằng passkey hoặc MFA

Kiểm tra có hai mức:

- **Authentication:** challenge, origin/RP ID, cryptographic verification, anti-replay, account recovery và session creation.
- **Authorization:** một session đã login bằng passkey/MFA có được cấp role đúng không? Các hành động rủi ro có cần step-up không?

Không tự động cấp ADMIN chỉ vì “đăng nhập mạnh hơn”; độ mạnh xác thực và quyền nghiệp vụ là hai khái niệm khác nhau.

## 10. Những yếu tố liên quan cần đánh giá sau thay đổi

### 10.1. CSRF và thay đổi method

Một endpoint GET công khai không nên đổi trạng thái. Nếu thêm POST/PATCH/DELETE, cần đánh giá liệu trình duyệt tự gửi cookie/Basic credential hay không. Trong Spring Security Servlet, CSRF bật mặc định để bảo vệ request thay đổi trạng thái. Cần test:

- POST có token hợp lệ và đúng role → được xử lý.
- POST không token hoặc token sai → 403 trước khi cập nhật dữ liệu.
- Logout/login phải tuân theo CSRF lifecycle đúng.
- Đừng tắt CSRF toàn ứng dụng chỉ để một test POST đi qua.

**Lưu ý:** bản thân `SessionCreationPolicy.STATELESS` không chứng minh API an toàn khỏi CSRF nếu browser vẫn tự gửi credentials.

### 10.2. CORS và preflight

Frontend ở origin khác có thể cần CORS. `OPTIONS` preflight không gửi credentials bình thường, nên CORS phải được xử lý trước khi Spring Security yêu cầu authentication. Cấu hình `http.cors()`/`CorsConfigurationSource` đúng cho chain; không coi `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` là thay thế cho policy CORS.

Khi dùng cookie cross-origin cần ACAO là origin được cho phép cụ thể và `Access-Control-Allow-Credentials: true` cùng chính sách cookie/CSRF phù hợp, không dùng ACAO wildcard với credentials.

### 10.3. Session, cookie, remember-me và logout

Bật phương thức login mới có thể tạo một session mới hoặc thay đổi cách xác thực từng request. Rà soát session fixation, thời gian idle, concurrent sessions nếu có, remember-me và logout. Với token ngoài session, logout `HttpSession` không tự thu hồi tất cả bearer token.

### 10.4. Error handling và status

401 từ Basic/Bearer thường cần `WWW-Authenticate`; 403 là thiếu quyền hoặc các cơ chế bảo vệ khác như CSRF. Form login có thể trả redirect. Đừng gộp mọi trường hợp thành 200 + JSON báo lỗi, và đừng để exception chứa credentials/token lộ ra browser.

### 10.5. Logging, audit và dữ liệu nhạy cảm

Review log/trace khi thêm login mới: không ghi raw `Authorization`, `Cookie`, `Set-Cookie`, password, OAuth code, refresh token hoặc CSRF token. Ghi route template, correlation ID an toàn, loại actor, quyết định ALLOW/DENY và mã lỗi đã chuẩn hóa. Với role mới cần có audit cấp/thu hồi quyền.

### 10.6. Cache và quyền cũ

Thay role tại IdP/database không đồng nghĩa mọi JWT/session đã phát hành lập tức đổi quyền. Cần định nghĩa TTL/revoke/invalidation, đặc biệt khi thu hồi quyền nhạy cảm. Nếu cache dữ liệu theo người/tenant, tránh để response của người dùng cũ được chia sẻ sai sau role/session change.

## 11. Playbook review pull request thay đổi bảo mật

Trước khi merge một thay đổi:

**Bước 1 — Mô tả change set.** Nêu endpoint/role/login mechanism nào thêm, sửa, xóa; actor và mục đích nghiệp vụ. Nếu có nhiều service, ghi rõ service nào phát token và service nào xác thực.

**Bước 2 — Vẽ đường request.** Với từng URL/method, xác định matcher, `SecurityFilterChain`, authentication filter, CSRF/CORS, `AuthorizationFilter`, controller, method security và data access.

**Bước 3 — Cập nhật ma trận quyền.** Liệt kê anonymous, user roles, service principal và trường hợp khác tenant. Không chỉ kiểm tra role có quyền; phải kiểm tra role **không được quyền**.

**Bước 4 — Đảm bảo deny-by-default.** Rule cụ thể trước rule rộng; fallback chain bao URL không khớp chain chuyên biệt; unknown URL/method không được vô tình công khai.

**Bước 5 — Kiểm tra dữ liệu định danh.** Role/authority/claim lấy từ hệ thống xác thực đã kiểm tra, không từ request body hoặc header tự do; mapping `ROLE_`/`SCOPE_` đúng quy ước.

**Bước 6 — Kiểm tra side effects.** CSRF, CORS preflight, cookie, redirect/login page, logout/session, remember-me, caching và error 401/403. Nếu bật OAuth, kiểm tra callback và token issuer/audience.

**Bước 7 — Chạy regression tests.** Tối thiểu một ca thành công và nhiều ca bị từ chối cho mỗi thay đổi, thêm ca role cũ, URL không khai báo, method ngoài phạm vi và tác nhân khác.

**Bước 8 — Quan sát và kế hoạch rollback.** Bật log cấu hình ở môi trường test để kiểm tra các filter chain, theo dõi biến động 401/403/5xx khi triển khai, chuẩn bị rollback. Không bật TRACE kèm token/cookie trong production.

### Mẫu biểu ngắn để đưa vào pull request

```text
Security Change Review
- Endpoint / HTTP method:
- Actor type:
- Auth mechanism:
- Matching SecurityFilterChain:
- Required authority/role/scope:
- Data ownership/tenant rules:
- CSRF/CORS/session/cookie impacts:
- 401/403/redirect contract:
- Positive tests:
- Negative tests:
- Existing behavior intentionally unchanged:
- Auditor/reviewer and rollback plan:
```

Đây là mẫu mô tả; đừng xem việc điền biểu mẫu là đủ thay thế kiểm thử thực tế.

## 12. Sai lầm thường gặp

1. **Đặt `/api/**.authenticated()` trước `/api/admin/**.hasRole("ADMIN")`.** Rule rộng thắng; sửa thứ tự từ cụ thể tới tổng quát.
2. **Tưởng `securityMatcher` và `requestMatchers` giống nhau.** Một cái chọn chain, cái kia chọn policy trong chain.
3. **Không có fallback chain hoặc fallback `permitAll()`.** Endpoint mới có thể được bỏ qua bảo mật hoặc mở công khai.
4. **Tin rằng `permitAll()` tắt hết filter.** Nó không vô hiệu hóa CSRF, CORS, headers hoặc custom filter.
5. **Thêm POST nhưng test chỉ GET.** Phải rà soát method, CSRF và quyền ghi.
6. **Cho `ROLE_ADMIN` mọi quyền mà chưa định nghĩa hierarchy.** Role có tên cao hơn không tự sở hữu mọi authority.
7. **Trộn `hasRole("ADMIN")` với `hasAuthority("ADMIN")`.** Kiểm tra tiền tố `ROLE_` và cách cấp quyền thực tế.
8. **Chỉ có role-level access, không có object-level access.** Cần kiểm tra tenant/owner tại data/service.
9. **Bật Basic, cookie hoặc remember-me rồi tắt CSRF chỉ vì API “stateless”.** Browser có thể tự gửi credentials; phân tích theo kênh xác thực.
10. **Thêm login endpoint ngoài security chain.** Filter tạo login/redirect/callback có thể không bao giờ được gọi.
11. **Bật OAuth2 login làm mọi API redirect tới IdP.** API JSON và browser cần entry point riêng theo thiết kế.
12. **Tin rằng test `@WithMockUser` chứng minh JWT đã được ký và xác thực.** Mock authentication chỉ phục vụ test phân quyền.
13. **Cho phép mọi origin để “sửa 401”.** CORS không cấp quyền; phải chẩn đoán CORS và auth riêng.
14. **Quên revoke/invalidate khi bỏ role.** Session hoặc JWT cũ có thể giữ quyền tới khi bị hết hạn/thu hồi.
15. **Chỉ test happy path.** Phần nguy hiểm nhất là người/role/method không được cấp quyền nhưng vẫn truy cập được.
16. **Không xem log/error contract khi thêm login.** Dễ lộ token, cookie, password hoặc chi tiết hệ thống.

## 13. Bài tập thực hành

Một hệ thống có các yêu cầu mới:

- Người có `ROLE_SUPPORT` được xem `GET /api/tickets/{id}` nếu ticket thuộc tenant mà họ phục vụ.
- Người có `ROLE_TICKET_EDITOR` được `PATCH /api/tickets/{id}` nhưng không được xóa ticket.
- Một worker cần gọi `POST /api/m2m/ticket-sync` bằng client credentials thay vì dùng session nhân viên.
- Người dùng tương tác bắt đầu đăng nhập bằng OIDC bên cạnh form login cũ.

Hãy lập bảng chính sách trả lời:

1. Chain nào xử lý `/api/tickets/**`, `/api/m2m/**`, `/ui/**` và `/login/oauth2/code/**`? Có fallback bao URL còn lại không?
2. Rule nào cần đặt trước để tránh `authenticated()` rộng làm mất `hasRole`/`hasAuthority` cụ thể?
3. Quyền đọc ticket có kiểm tra tenant/owner ở service không?
4. PATCH có cần CSRF không khi dùng session/cookie? Khi API M2M chỉ dùng bearer header thì chính sách khác gì?
5. Token service có issuer, audience, scope và đúng loại principal không? Nó có vào được UI nhân viên không?
6. Người đăng nhập bằng OIDC có được map sang authority phù hợp mà không tự cấp ADMIN không?
7. Những trường hợp 200, 201, 302, 401, 403 và 404 nào cần test? API phải trả JSON hay redirect?
8. Khi thu hồi `ROLE_TICKET_EDITOR`, session/JWT cũ mất quyền sau bao lâu?
9. Có thể chỉ dùng browser UI để “ẩn nút Xóa” thay authorization backend không? **Không.**
10. Khi request sai quyền bị từ chối, log có đầy đủ correlation ID để tra cứu mà không lưu token/cookie thật không?

Tạo regression tests cho ít nhất: SUPPORT đúng tenant; SUPPORT sai tenant; EDITOR PATCH thành công; EDITOR thiếu CSRF bị chặn; DELETE bị deny; worker đúng token; worker token sai audience/scope; user session gọi M2M bị chặn; API anonymous; login callback và fallback URL.

## 14. Kết luận và tài liệu tham khảo

**Không có thay đổi endpoint, role hay login mechanism nào được coi là “chỉ sửa một chỗ”** khi chính sách bảo mật gồm nhiều lớp. Rà soát đúng là xác định **chain được chọn, rule đầu tiên khớp, nguồn danh tính, authority, quyền dữ liệu, CSRF/CORS, session và hành vi lỗi**; sau đó chứng minh bằng test dương tính **và** âm tính. Khi chưa có rule được duyệt, **từ chối theo mặc định** tốt hơn tự mở quyền.

Tài liệu chính thức để đối chiếu khi nâng cấp Spring Security:

- Spring Security — [Java Configuration và multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html).
- Spring Security — [Authorize HttpServletRequests, matcher precedence và denyAll](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- Spring Security — [CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- Spring Security — [Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html).
- Spring Security — [CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- Spring Security — [OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- Spring Security — [Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/).
- OWASP — [Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).
- OWASP — [Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).