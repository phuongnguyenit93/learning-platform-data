# Hoàn thiện ma trận kiểm thử và rà soát cấu hình triển khai Spring Security Servlet

> **Phạm vi:** bài thực hành tổng hợp cho ứng dụng **Spring Security Servlet** trên Java 17+, Spring Boot 3, Spring Security 6, Spring MVC, JUnit 5 và MockMvc. Mục tiêu không chỉ có một số test PASS mà phải chứng minh **mỗi bề mặt HTTP được chọn đúng SecurityFilterChain, xác thực đúng, kiểm quyền đúng và giữ nguyên các biện pháp bảo vệ khi triển khai thật**.
>
> Các đoạn mã Spring cần nằm trong dự án có dependencies, class khởi động `@SpringBootApplication` và cấu hình môi trường phù hợp. Chương trình Java 17 thuần ở mục 5 có thể chạy độc lập. Ví dụ môi trường dùng tên miền `example.test`; đây là tên minh họa, không phải máy chủ IdP thực. **Không sao chép mật khẩu/secret, issuer hoặc origin mẫu vào production.**

## 1. Đầu ra nghiệm thu: phải có bằng chứng, không chỉ có cấu hình

Kết quả mong muốn là một bộ hồ sơ kiểm thử và triển khai với:

1. **Bản đồ tài nguyên và ranh giới bảo mật:** URL, HTTP method, authentication mode, session/cookie, authority/role, owner/tenant và độ nhạy của dữ liệu.
2. **Ma trận kiểm thử có thể truy vết:** case ID, đầu vào, danh tính, ngữ cảnh CSRF, kỳ vọng HTTP status/body/headers, mức test, bằng chứng và owner.
3. **Các test tự động:** unit, Spring Security Test/MockMvc, repository/service authorization, integration với JWT decoder/session/DB thật khi cần, browser end-to-end.
4. **Bản rà soát cấu hình triển khai:** thứ tự filter chain, TLS/proxy, CORS, CSRF, session, cookies, headers, secret management, monitoring, dependency management và container config.
5. **Tiêu chí release/rollback:** lỗi nghiêm trọng nào chặn triển khai, ai phê duyệt, cách kiểm sau rollout và đường quay lại.

Một test `GET /health` trả 200 không chứng minh `POST /transfer` được chống CSRF hoặc `GET /users/{id}` có kiểm tra owner. Một test `with(jwt())` thành công không chứng minh JWT decoder đang xác minh chữ ký. Ngược lại, một test 403 cũng cần phân biệt lỗi **CSRF** với **authorization**. Ma trận phải thể hiện đúng từng lớp.

**Luật nghiệm thu:** thiếu test phủ một ranh giới an toàn quan trọng là *chưa có đủ bằng chứng*, không tự động coi là PASS.

## 2. Vẽ bản đồ hệ thống trước khi viết matrix

Giả sử một ứng dụng có hai nhóm HTTP:

- **API:** `/api/**` dùng `Authorization: Bearer <token>`, Resource Server xác minh JWT, không dùng session/cookie làm credential của API. Các endpoint riêng yêu cầu scopes và owner.
- **Web:** `/web/**`, `/admin/**` và trang login dùng form login + session cookie; các yêu cầu thay đổi dữ liệu phải có CSRF token.
- **Công khai:** `/api/public/ping`, `/login`, static assets.
- **Quản trị/vận hành:** health/readiness, metrics, management endpoints; không mặc định mọi actuator endpoint được công khai.
- **Hạ tầng:** TLS termination, reverse proxy/load balancer, secrets, external identity provider/JWKS, session store, database.

Đây là **mô hình minh họa**, không phải áp đặt mọi ứng dụng phải có hai chain hoặc dùng JWT. Nếu hệ thống chỉ dùng form login, bỏ các trường hợp Bearer không liên quan và bổ sung bài test tương ứng cho authentication mechanism thật. Nếu hệ thống dùng HTTP Basic và browser tự gửi credentials, **không mặc định tắt CSRF** vì tên endpoint bắt đầu bằng `/api`.

### 2.1. Bảng inventory tài nguyên

| Tài nguyên | Method | Caller được phép | Authentication | CSRF/session | Dữ liệu cần bảo vệ |
| --- | --- | --- | --- | --- | --- |
| `/api/public/ping` | GET | Anonymous | Không bắt buộc | Stateless API | Không chứa secret |
| `/api/me` | GET | Có scope `profile.read` | JWT Bearer | Không dựa vào cookie | Chỉ profile chính caller |
| `/api/me/update` | POST | Scope `profile.write` + owner rule | JWT Bearer | Không nhận cookie trong mẫu | Chỉ update account của caller |
| `/web/account` | GET | User đã login | HttpSession | Session cookie | Không lộ account người khác |
| `/web/settings` | POST | User đã login | HttpSession | **CSRF bắt buộc** | Thao tác thay đổi dữ liệu |
| `/admin/report` | GET | Role ADMIN | HttpSession | Session cookie | Dữ liệu quản trị |
| `/login` | GET/POST | Anonymous hoặc đã login | Form authentication | CSRF bảo vệ form POST | Password và session |
| `/logout` | POST | User đang login | Session + cookie | **CSRF bắt buộc** | Hủy session hiện tại |
| `/assets/**` | GET | Anonymous | Không bắt buộc | Không thay đổi trạng thái | Static files, security headers |
| `/actuator/health` | GET | Theo policy vận hành | Cấu hình riêng | Tùy endpoint | Hạn chế thông tin hệ thống |

Bảng trên là **hợp đồng thử nghiệm**. Với mỗi dòng, ghi thêm: HTTP host/port, servlet context, chain name, intended `AuthenticationEntryPoint`, quyền trên service method, tiêu chí bảo vệ dữ liệu và log redaction.

**Phân biệt ba điểm quyết định:**
1. `securityMatcher(...)` xác định **SecurityFilterChain được xét**.
2. Authentication filter xác định credential có được kiểm chứng.
3. `authorizeHttpRequests(...)` và method/domain authorization quyết định user có quyền thao tác tài nguyên hay không.

Nếu chỉ kiểm tra bước 3 bằng mock user, bạn có thể bỏ lỡ việc request thực không vào chain nào.

## 3. Thiết kế ma trận kiểm thử có thể truy vết

Đừng tạo một bảng “test login, test logout” quá chung. Mỗi testcase cần metadata:

| Cột | Nội dung cần ghi |
| --- | --- |
| `ID` | Ví dụ `API-AUTH-001`; duy nhất và ổn định |
| `Feature/Threat` | JWT, CSRF, IDOR, CORS, session fixation, v.v. |
| `Endpoint + method` | URL và HTTP method chính xác |
| `Authentication context` | Anonymous, Basic, form login, JWT hợp lệ/sai, remember-me |
| `Authority/ownership` | Role/scope và owner/tenant của resource |
| `Request state` | CSRF token, cookies, origin, request body, session |
| `Expected` | Status, header, body, side effect và audit |
| `Level` | Unit, MockMvc, integration, E2E/browser, deployment probe |
| `Evidence` | Test method/run ID, artifact đã redact, phiên bản deploy |
| `Owner + status` | Ai chịu trách nhiệm, PASS/FAIL/BLOCKED/NOT_RUN |
| `Risk/priority` | Release blocker hay cảnh báo cần xử lý |

Ma trận nên đủ chặt để **người khác có thể chạy lại mà không hỏi tác giả**. Đặc biệt, status `401/403/302` phải gắn với từng loại ứng dụng và authentication entry point, không áp một đáp án cho mọi dự án.

### 3.1. Ma trận HTTP: xác thực và phân quyền

Dưới đây là **kỳ vọng cho kiến trúc mẫu** ở mục 2 và cấu hình ở mục 7:

| ID | Request và danh tính | Kỳ vọng | Điều đang chứng minh |
| --- | --- | --- | --- |
| AUTH-01 | Anonymous `GET /api/public/ping` | 200, `pong` | API public vẫn qua chain phù hợp |
| AUTH-02 | Anonymous `GET /api/me` | 401, `WWW-Authenticate: Bearer` | API entry point, không redirect login |
| AUTH-03 | Bearer token bị sửa chữ ký vào `GET /api/me` | 401 | Decoder không chấp nhận token giả |
| AUTH-04 | JWT hết hạn | 401 | Thực thi expiry |
| AUTH-05 | JWT sai `iss`/`aud` theo policy | 401 | Issuer/audience validators hoạt động |
| AUTH-06 | JWT hợp lệ, không có `profile.read` | 403 | Authentication thành công nhưng thiếu authority |
| AUTH-07 | JWT hợp lệ, scope `profile.read` | 200, chỉ thông tin caller | Authority và data ownership |
| AUTH-08 | JWT hợp lệ, scope `profile.write`, POST đúng schema | 2xx, update đúng user | Write permission, input validation và audit |
| AUTH-09 | JWT chỉ có `profile.read`, POST update | 403 | Read scope không thành write scope |
| AUTH-10 | JWT hợp lệ nhưng requester giả mạo `userId` khác | 403/404 theo policy, không đọc/ghi khác | Object-level authorization/IDOR |
| AUTH-11 | Anonymous `GET /web/account` | 302 đến login | Web chain dùng form authentication |
| AUTH-12 | Session Alice `GET /web/account` | 200, account Alice | Session authentication |
| AUTH-13 | Session USER `GET /admin/report` | 403 | Role gate |
| AUTH-14 | Session ADMIN `GET /admin/report` | 200, đúng tenant/data scope | Role + business authorization |
| AUTH-15 | Anonymous `GET /apiary` | Web policy, không bị xem nhầm là `/api/**` | Matcher boundary |

Ở AUTH-10, đáp án 403 hay 404 là **policy thiết kế**: một số hệ thống trả 404 nhằm giảm enumeration, nhưng bắt buộc **không trả dữ liệu và không thay đổi trạng thái**. Không dùng sai status để che việc service hoàn toàn bỏ qua owner check.

### 3.2. Ma trận CSRF, CORS, cookie và session

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| WEB-CSRF-01 | User có session POST `/web/settings` **không CSRF** | 403, không thay đổi dữ liệu |
| WEB-CSRF-02 | User có session POST `/web/settings` **có CSRF hợp lệ** | 2xx nếu đủ quyền và input hợp lệ |
| WEB-CSRF-03 | POST `/logout` thiếu CSRF | 403, session chưa logout |
| WEB-CSRF-04 | POST `/logout` có CSRF | Session hiện tại invalidated, cookie/remember-me xử lý theo cấu hình |
| SESS-01 | Login thành công từ session có sẵn | Session ID đổi theo session-fixation policy |
| SESS-02 | Hai phiên Alice, giới hạn một phiên | Đúng policy expire-old hoặc prevent-new |
| SESS-03 | Logout một browser | Không tự tuyên bố mọi browser khác cũng logout |
| SESS-04 | Remember-me khi không có session | Chỉ tự login nếu token hợp lệ và policy cho phép |
| SESS-05 | Remember-me token đã revoke (persistent mode) | Không thể authenticate bằng token series cũ |
| CORS-01 | Origin được allow gửi preflight có Authorization header | Preflight thành công với allow-origin/method/headers đúng |
| CORS-02 | Origin không được allow | Không nhận CORS permission; preflight bị từ chối theo cấu hình |
| CORS-03 | Cross-site request với cookie web | CORS không thay thế CSRF; unsafe action bị chặn nếu thiếu token |
| COOKIE-01 | Session cookie trên HTTPS | `Secure`, `HttpOnly`, `SameSite` và path/domain theo policy |
| COOKIE-02 | Client sửa `JSESSIONID` | Không được kế thừa authenticated session |
| COOKIE-03 | Logout xóa cookie | Phải dùng path/domain phù hợp; test browser thật |

Nếu API **chỉ** nhận Bearer token từ `Authorization` header do client tự thêm và không dùng cookie/Basic, có thể cấu hình stateless và loại CSRF cho chain API *sau khi threat model được xác minh*. Còn nếu credential tự được browser gửi, phải đánh giá CSRF dù endpoint trả JSON.

### 3.3. Ma trận dữ liệu, header, lỗi và tài nguyên

| ID | Kiểm thử | Kỳ vọng |
| --- | --- | --- |
| DATA-01 | Request body sai kiểu hoặc quá kích thước | 400/413 phù hợp, không cập nhật |
| DATA-02 | Path/ID ngoài tenant | 403/404, không lộ đối tượng |
| DATA-03 | SQL meta characters trong input | Query parameterized, không thay cấu trúc SQL |
| DATA-04 | Chuỗi HTML trong display name | Render escaped text; không DOM XSS |
| DATA-05 | Redirect target ngoài allowlist | Bị từ chối/redirect nội bộ an toàn |
| DATA-06 | Upload có extension/MIME giả | Validation/storage policy từ chối |
| HDR-01 | HTML response | CSP, `nosniff`, frame policy theo dự kiến |
| HDR-02 | HTTPS response | HSTS khi phù hợp với host và môi trường |
| HDR-03 | Response cá nhân/nhạy cảm | `Cache-Control: no-store` theo policy |
| ERR-01 | Không có Authentication | Không lộ stack trace/token qua response |
| ERR-02 | Authorization denied | Log audit tối thiểu, không log credentials |
| ERR-03 | URL firewall từ chối | Không bypass filter chain để cho qua đường dẫn bất thường |
| OPS-01 | Liveness/readiness | Chỉ lộ mức thông tin cần thiết |
| OPS-02 | Management/config endpoints | Không public nếu không được chủ đích cho phép |
| OPS-03 | Thử route chưa định nghĩa | Không trở thành anonymous bypass của Spring Security |

Không nhất thiết một codebase phải triển khai mọi dòng nếu chức năng không tồn tại. Nhưng **bất kỳ dòng nào được đánh dấu N/A** cần có giải thích và reviewer xác nhận, tránh “không test vì chưa kịp”.

## 4. Chiến lược test: test nào chứng minh điều gì?

| Mức test | Mục tiêu phù hợp | Giới hạn cần ghi |
| --- | --- | --- |
| Unit | Input validation, mapping roles/scopes, domain policy | Không chứng minh Servlet filters hoặc JWT signature thật |
| Security service/method test | `@PreAuthorize`, owner/tenant, business roles | Mocked principal có thể bypass login/decoder |
| MockMvc + Spring Security filter chain | Matching, entry point, CSRF, 401/403/302, headers | Cookie/browser, external IdP, real proxy cần test bổ sung |
| Authentication integration | `JwtDecoder`/JWK, issuer/audience, login/session store | Cần test keys/IdP/emulator phù hợp |
| Repository + DB integration | Object ownership, persistent remember-me, transaction, data filters | Embedded DB có thể khác production SQL |
| Browser E2E | Cookies, redirect, CSRF form, CORS, cross-origin, logout | Tốn thời gian, phụ thuộc môi trường |
| Deployment probe | TLS/HSTS, proxy forwarding, actual headers, health, runtime config | Không thay deep authorization tests |
| Pen test/DAST có kiểm soát | Tìm behavior bất ngờ, XSS/IDOR/misconfig | Không thay automation và code review |

**Không kết luận “JWT an toàn” chỉ vì `with(jwt())` pass.** Spring Security Test `jwt()` đặt một Authentication test; chữ ký, issuer và JWK retrieval có thể chưa chạy. Với JWT, cần một nhóm integration test độc lập gọi **real decoder** với token hợp lệ/sai/hết hạn/sai audience.

**Không kết luận “session fixation an toàn” chỉ vì `MockHttpSession.getId()` đổi**. MockMvc có thể đổi ID tại chỗ, không chứng minh container/browser từ chối session ID cũ; nên test HTTP client với hai cookie jars qua container thật.

## 5. Java 17 độc lập: kiểm tra ma trận case ID và phủ nhóm lỗi

Đây là **chương trình thuần JDK 17** để chứng minh cách kiểm tra một phần **chất lượng của ma trận**. Nó không chạy HTTP requests và không thay Spring Security Test. File `SecurityMatrixAuditDemo.java`:

```java
import java.util.List;

public final class SecurityMatrixAuditDemo {
    record Case(String id, String method, String path,
                String identity, int expectedStatus) {}

    static void requireUniqueIds(List<Case> cases) {
        long distinct = cases.stream().map(Case::id)
            .distinct().count();
        if (distinct != cases.size()) {
            throw new IllegalStateException("Duplicate test case ID");
        }
    }

    public static void main(String[] args) {
        List<Case> cases = List.of(
            new Case("AUTH-01", "GET", "/api/public/ping", "anonymous", 200),
            new Case("AUTH-02", "GET", "/api/me", "anonymous", 401),
            new Case("AUTH-06", "GET", "/api/me", "no-scope", 403),
            new Case("AUTH-07", "GET", "/api/me", "profile.read", 200),
            new Case("WEB-CSRF-01", "POST", "/web/settings", "no-csrf", 403),
            new Case("WEB-CSRF-02", "POST", "/web/settings", "with-csrf", 200),
            new Case("AUTH-11", "GET", "/web/account", "anonymous", 302),
            new Case("AUTH-13", "GET", "/admin/report", "user", 403)
        );

        requireUniqueIds(cases);

        long httpErrors = cases.stream()
            .filter(c -> c.expectedStatus() >= 400)
            .count();

        boolean hasCsrfNegative = cases.stream()
            .anyMatch(c -> c.id().equals("WEB-CSRF-01")
                && c.expectedStatus() == 403);

        System.out.println("cases=" + cases.size());
        System.out.println("unique-ids=true");
        System.out.println("http-errors=" + httpErrors);
        System.out.println("csrf-negative=" + hasCsrfNegative);
    }
}
```

Biên dịch/chạy:

```bash
javac SecurityMatrixAuditDemo.java
java SecurityMatrixAuditDemo
```

Stdout chính xác:

```text
cases=8
unique-ids=true
http-errors=4
csrf-negative=true
```

Phân tích: `http-errors=4` gồm 401/403 (còn redirect 302 là response 3xx). Kiểm tra ID duy nhất giúp ma trận có thể dùng làm test catalog hoặc evidence registry; điều kiện `csrf-negative=true` chỉ xác nhận **case được mô tả**, không chứng minh endpoint thực đã trả 403. Không dùng các chuỗi giả lập trong `Case` để thay kiểm thử HTTP.

Mở rộng hữu ích khi làm dự án: mỗi case có `priority`, `owner`, `testMethod`, `actualStatus`, `evidenceUri`, `timestamp` và `deploymentBuildId`; kiểm báo cáo nếu thiếu case P0/P1 hoặc expected != actual. Không cần tự viết một framework test mới nếu JUnit + CI reporting đã có.

## 6. Thứ tự filter chain: cần rà soát trước khi chạy tests

Spring Security Servlet thường đi qua:

```text
HTTP request
  -> Servlet container filters
  -> DelegatingFilterProxy (springSecurityFilterChain)
  -> FilterChainProxy
      -> SecurityFilterChain đầu tiên khớp RequestMatcher
      -> filters bên trong chain được chọn
  -> DispatcherServlet
  -> Controller / Service
```

Trong cấu hình nhiều chain:
- **`securityMatcher`** giới hạn URL/method có thể vào chain đó.
- **`@Order`** xác định thứ tự đánh giá các bean chain.
- **`authorizeHttpRequests(...requestMatchers...)`** kiểm quyền sau khi chain đã chọn.
- Chain catch-all nên đứng sau chain chuyên biệt.
- `permitAll` vẫn cho request đi qua security filter chain (không đồng nghĩa `web.ignoring()`).
- Nếu **không chain nào khớp**, request có thể không được Spring Security bảo vệ.

Để rà soát đúng, liệt kê `FilterChainProxy.getFilterChains()` trong dev/test; với mỗi chain, ghi matcher, order, filters, entry point và các URLs đang bảo vệ. Bật log `org.springframework.security.web.FilterChainProxy=TRACE` **chỉ trong môi trường thử nghiệm**, không log raw tokens/session IDs.

### 6.1. Mẫu rà soát chain

| Chain | Matcher | Order | Authentication | CSRF | Fallback |
| --- | --- | --- | --- | --- | --- |
| API | `/api/**` | 1 | Bearer JWT | Tắt riêng nếu thực sự header-only/stateless | Không |
| Web | Any request | 2 | Form login + session | Bật | Có |
| Management riêng nếu tồn tại | Matcher quản trị | Tùy policy | Mạnh/segregated | Theo flow | Không |

Kiểm tra `/apiary`, `/api`, URL có context path, trailing slash, encoded path, servlet path và reverse proxy rewrite. **Không dùng `startsWith("/api")` tự viết** để thay cho matcher của framework.

## 7. Mẫu Spring Boot 3 / Spring Security 6 để kiểm thử

Ví dụ sau dành cho kiến trúc mẫu **JWT Bearer stateless API + form login web**. Nó minh họa một policy rõ ràng, không phải cấu hình hoàn chỉnh cho mọi doanh nghiệp. Phải có:
- `spring-boot-starter-web`;
- `spring-boot-starter-security`;
- `spring-boot-starter-oauth2-resource-server`;
- `spring-boot-starter-test` và `spring-security-test` trong test scope;
- JDK 17+ và class khởi động Spring Boot;
- JWT issuer/JWKS hợp lệ trong production và user store/auth provider cho form login.

### 7.1. SecurityConfig.java

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .hasAuthority("SCOPE_profile.read")
                .requestMatchers(HttpMethod.POST, "/api/me/update")
                    .hasAuthority("SCOPE_profile.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .cors(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout"))
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId()));

        return http.build();
    }
}
```

**Giải thích security decision:**

1. `@Order(1)` đặt API trước catch-all web.
2. API yêu cầu `SCOPE_profile.read` cho GET, `SCOPE_profile.write` cho POST, và `denyAll` cho các API paths chưa được công nhận.
3. Bearer token được xác minh bởi Resource Server (khi chạy thật có JwtDecoder), còn `@Order(2)` web dùng form/session.
4. CSRF **chỉ bị tắt trong API chain**, vì threat model mẫu khẳng định API **không dùng credential tự được browser gắn như cookie/Basic**, chỉ chấp nhận Bearer token trong Authorization header và không dùng session. Nếu ứng dụng thực có cookie API hoặc Basic, phải thiết kế CSRF lại.
5. Web giữ CSRF default, sử dụng session fixation protection với `changeSessionId()`.
6. Admin có role rule nhưng domain authorization/owner checks **vẫn thuộc service**.
7. Không có logic `permitAll` cho tất cả routes khi test lỗi; unrecognized API paths bị deny.

**Cần cấu hình JWT decoder đúng:** ví dụ với `application.yml` (chỉ minh họa tên issuer):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
```

Ứng dụng production phải dùng issuer thật và xác minh token signature, algorithm, `iss`, `exp`, `nbf`; **audience** có thể cần validator riêng tùy provider/requirements. Không mặc định mọi JWT được issuer ký đều có audience đúng API này. Nếu thiếu IdP/JWKS ở lúc startup hoặc token verification, hành vi fail/availability phụ thuộc decoder config; hãy test thực tế. Không tắt signature validation chỉ để integration tests xanh.

### 7.2. CORS configuration chỉ cho frontend đáng tin

`CorsConfigurationSource` có thể khai báo riêng cho API:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ApiCorsConfig {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration c = new CorsConfiguration();
        c.setAllowedOrigins(List.of("https://app.example.test"));
        c.setAllowedMethods(List.of("GET", "POST"));
        c.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        c.setAllowCredentials(false);
        c.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", c);
        return source;
    }
}
```

Đây là **mẫu cho API header-only Bearer**, không phải CORS policy cho form-login web. `allowedOrigins` cần exact origins (scheme/host/port), không dùng wildcard rộng khi có credentials. CORS là browser policy **không phải authentication/authorization backend**; request từ server-to-server hoặc curl không bị browser CORS chặn, nên APIs vẫn phải tự kiểm auth.

Khi kiểm CORS, test preflight `OPTIONS` với header `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`, rồi kiểm actual response; không chỉ đọc bean configuration.

### 7.3. Controller mẫu cho HTTP matrix

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public/ping")
    String ping() { return "pong"; }

    @GetMapping("/api/me")
    String apiMe() { return "profile"; }

    @PostMapping("/api/me/update")
    String updateProfile() { return "updated"; }

    @GetMapping("/web/account")
    String webAccount() { return "account"; }

    @PostMapping("/web/settings")
    String webSettings() { return "saved"; }

    @GetMapping("/admin/report")
    String adminReport() { return "report"; }
}
```

**Giới hạn:** controller chỉ trả string demo để kiểm filter behavior; nó **không** có DB, update side effect, validation, tenant hoặc owner checks. Kết quả `updated` chỉ chứng minh endpoint qua filter cho request đã được cho phép. Trong thực tế, phải kiểm service authorization, repository, body validation và transaction rollback riêng.

## 8. MockMvc: kiểm chứng positive và negative HTTP cases

Với `SecurityConfig`, `ApiCorsConfig` và `DemoController` được scan, có thể viết `SecurityMatrixHttpTests.java`. Để test `with(jwt())` mà không gọi IdP thật, định nghĩa **JwtDecoder chỉ dành cho môi trường test**. Đây là intentional **mocked-authentication test**, không phải crypto integration test.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Import(SecurityMatrixHttpTests.TestDecoder.class)
class SecurityMatrixHttpTests {

    @Autowired MockMvc mvc;

    @TestConfiguration
    static class TestDecoder {
        @Bean
        JwtDecoder jwtDecoder() {
            return token -> {
                throw new BadJwtException(
                    "Real JWT decoding not used by these mock-auth tests");
            };
        }
    }

    @Test
    void publicApiIsAccessible() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void anonymousApiGetsBearerChallenge() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string("WWW-Authenticate",
                containsString("Bearer")));
    }

    @Test
    void scopeReadAllowsGet() throws Exception {
        mvc.perform(get("/api/me").with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isOk())
            .andExpect(content().string("profile"));
    }

    @Test
    void missingScopeDeniesGet() throws Exception {
        mvc.perform(get("/api/me").with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.write"))))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeAllowsPostForStatelessApi() throws Exception {
        mvc.perform(post("/api/me/update").with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile.write"))))
            .andExpect(status().isOk())
            .andExpect(content().string("updated"));
    }

    @Test
    void webPostNeedsCsrf() throws Exception {
        mvc.perform(post("/web/settings").with(user("alice")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/web/settings").with(user("alice"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("saved"));
    }

    @Test
    void anonymousWebRedirectsToLogin() throws Exception {
        mvc.perform(get("/web/account"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }

    @Test
    void ordinaryUserCannotReadAdminReport() throws Exception {
        mvc.perform(get("/admin/report").with(user("alice")
                .roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowedOriginPreflight() throws Exception {
        mvc.perform(org.springframework.test.web.servlet.request
                .MockMvcRequestBuilders.options("/api/me")
                .header(HttpHeaders.ORIGIN, "https://app.example.test")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.test"));
    }
}
```

Trong test này, **`with(jwt())` bỏ qua bước parse/verify JWT thật** và cung cấp test Authentication cho filter chain. Nested `TestDecoder` là bean **chỉ dành cho test** để ApplicationContext có `JwtDecoder` mà không cần kết nối IdP. **Không đưa bean test này vào production**: nếu dùng thay decoder thật, mọi token sẽ bị từ chối hoặc auth semantics bị thay đổi.

Chạy trong dự án Maven:

```bash
mvn -Dtest=SecurityMatrixHttpTests test
```

Hoặc Gradle:

```bash
./gradlew test --tests SecurityMatrixHttpTests
```

Test này chứng minh một nhóm route/authority/CSRF/CORS expectations của **cấu hình mẫu**, không chứng minh toàn bộ ứng dụng production. Thay `DemoController` bằng controllers thực, thêm service-layer tests, input validation và JWT decoder integration tests. Status/headers có thể khác nếu ứng dụng thêm custom entry point, context path hay security filters; ma trận phải ghi **hợp đồng đã chọn**.

### 8.1. Kiểm thử JWT decoder thật, không chỉ with(jwt())

Với Resource Server production, cần một test class riêng có `JwtDecoder` được cấu hình bằng **test public key/JWKS** hoặc IdP test tin cậy. Dựng token test bằng private key của fixture (không dùng production keys), gửi vào HTTP:

```http
GET /api/me HTTP/1.1
Host: api.example.test
Authorization: Bearer <test-jwt-signed-by-test-key>
```

Test nhóm tiêu cực ít nhất:
- Signature sai hoặc public key không thuộc JWKS tin cậy → 401.
- `exp` trong quá khứ → 401.
- `nbf` ở tương lai ngoài clock skew cho phép → 401.
- `iss` khác configured issuer → 401.
- `aud` không chứa audience của API → 401 **nếu ứng dụng đã cấu hình audience validator**.
- Algorithm không nằm trong danh sách tin cậy → từ chối.
- Chữ ký đúng nhưng scope thiếu → **403**.
- Key rotation/JWKS failure: xử lý cache, availability và error response theo thiết kế.

**Đừng giả định Spring Security tự kiểm mọi claim theo policy sản phẩm.** Mặc định có những validators sẵn như issuer/timestamps tùy cấu hình, nhưng **audience** và business claims có thể phải bổ sung validator tùy provider/architecture.

### 8.2. Kiểm thử session, login và logout thật

Nếu web chain dùng form login:
1. Tạo session trước login, xác nhận session ID đổi khi user đăng nhập hợp lệ.
2. Thử dùng session ID trước login qua container thật: không được authenticated.
3. Test POST `/logout` có CSRF, session current invalidated.
4. Test POST `/logout` thiếu CSRF bị chặn và không gây side effects.
5. Nếu bật concurrent-session control, test hai browser độc lập (không phải hai tab cùng cookie jar), policy expire-old/prevent-new.
6. Nếu bật remember-me, phân biệt token-based và persistent token; **xóa cookie** không phải luôn tương đương **server-side revocation** của bản sao token.
7. Test session timeout, SameSite/Secure/HttpOnly, session store trong multi-node.
8. Nếu có OAuth2 login, kiểm state/redirect/callback và token/client registration riêng.

Dùng `MockHttpSession` để kiểm filter logic; test container/browser thật cho cookie attributes, old session replay và multi-node behavior.

## 9. Kiểm tra input validation, output encoding và authorization theo tài nguyên

HTTP security matrix không kết thúc ở `authorizeHttpRequests`. Một endpoint trả 200 khi có `SCOPE_profile.read` vẫn có thể lộ profile người khác nếu service lấy `?userId=123` mà không kiểm owner.

### 9.1. Object-level access control

Ví dụ với `GET /api/accounts/{id}`:
- Alice truy cập account Alice: có quyền đọc.
- Alice truy cập account Bob: **từ chối**, dù JWT của Alice có scope đọc profile chung.
- Alice đổi `tenantId` trong request: không thoát tenant boundary.
- Admin có role đúng nhưng chỉ được đọc các tenants thuộc phạm vi trách nhiệm theo policy.

Cần test cả **repository query filtering** và service authorization. Phân quyền ở URL không thay kiểm tra owner/tenant trong business logic.

### 9.2. Input validation và injection

Với `POST /api/me/update` thật:
- Dùng DTO `@Valid`, `@NotBlank`, `@Size`, `@Pattern` theo hợp đồng từng trường.
- Giới hạn body/array/uploads, validate enum/state transition và value ranges.
- Dùng prepared statements/ORM parameter binding thay SQL string concatenation.
- Nếu trả HTML, encode theo HTML text/attribute context; frontend dùng `textContent` thay `innerHTML` để hiển thị plain text.
- Rich HTML phải qua sanitizer có allowlist tags/attributes/protocols.
- URL redirect và SSRF targets phải kiểm scheme/host/path/egress.
- Không dựa vào CSP hoặc input validation để thay output encoding.

Negative test phải kiểm **không có side effects**, không chỉ HTTP 400/403. Với database, transaction test cần quan sát số bản ghi, owner/tenant và audit.

## 10. Rà soát cấu hình triển khai: checklist theo từng lớp

### 10.1. TLS, reverse proxy và trust boundary

- Production dùng HTTPS/TLS hợp lệ, cipher/protocol theo policy tổ chức; HTTP redirect sang HTTPS khi phù hợp.
- HSTS được gửi trên HTTPS cho host phù hợp, `includeSubDomains`/preload chỉ sau khi xác minh toàn bộ subdomains.
- Reverse proxy **loại bỏ incoming `Forwarded`/`X-Forwarded-*` do client tự gửi** rồi gắn header mới; app chỉ trust proxies được kiểm soát.
- Session cookie `Secure` không bị mất vì backend phía sau TLS termination hiểu nhầm request scheme.
- Backend service không bị Internet gọi trực tiếp qua một cổng HTTP không kiểm soát.
- URL/matcher phải được test với context path, servlet path, host và proxy rewrite thật.
- HTTP request headers như `Host`, `X-Forwarded-Host` không được dùng vô điều kiện làm cơ sở tin cậy cho redirect, RP ID hoặc allowed origins.
- Kênh giữa proxy và backend cần bảo vệ theo kiến trúc; mTLS khi cần.

### 10.2. Filter chain, authentication và authorization

- Liệt kê `FilterChainProxy.getFilterChains()`; xác nhận matcher và `@Order`.
- Chain chuyên biệt trước catch-all; không để URL bảo vệ nằm ngoài mọi chain.
- `permitAll` chỉ cho những routes được phép, không dùng `web.ignoring()` bừa vì có thể bỏ security headers.
- API Bearer dùng đúng `BearerTokenAuthenticationFilter` và JWT/opaque verifier.
- Form login/session chỉ nhận cookie/credentials đúng flow.
- `401` với anonymous API; `403` khi authenticated thiếu quyền; `302` ở web login theo design.
- Method security (`@EnableMethodSecurity`, `@PreAuthorize`) có tests cho proxy/self-invocation/owner.
- Không log raw Authorization header, access tokens, passwords, secret keys hoặc session IDs.
- Custom filters đúng thứ tự; tránh vừa đăng ký container filter vừa thêm vào SecurityFilterChain khiến double execution.
- Anonymous và error/async dispatch không tạo bypass.

### 10.3. CSRF, CORS và request boundary

- Phân biệt cookie/session/HTTP Basic với Bearer header-only khi quyết định CSRF.
- Web unsafe requests phải có CSRF; không tắt CSRF global chỉ để qua tests.
- CORS allowlist origins, methods, headers chính xác; không đồng nhất CORS với authorization.
- Preflight `OPTIONS` đi qua CORS filter đúng cách; allowed origin và disallowed origin được test.
- Không phản chiếu tùy tiện mọi `Origin` request nếu có credentials.
- Cookies có `Secure`, `HttpOnly`, `SameSite` phù hợp với kiến trúc, path/domain hạn chế.
- Rate limiting/abuse detection ở gateway/app theo policy; Spring Security không tự cung cấp toàn bộ anti-bot/DoS controls chỉ vì bật filters.
- Redirect targets được validate; không đưa Bearer/CSRF tokens vào URL.

### 10.4. Session, logout và remember-me

- Form login thay đổi session ID sau login (session fixation).
- Session timeout và concurrent-session policies đúng; registry phù hợp multi-node nếu dùng.
- `LogoutHandler` invalidates session/context; POST logout + CSRF theo thiết kế.
- Session cookies bị xóa với path/domain đúng; có browser test.
- Remember-me có TTL, secure cookie flags, key rotation/revocation policy; phân biệt token-based và persistent tokens.
- Logout một thiết bị không mặc định logout-all; nếu cung cấp logout-all, phải thu hồi sessions/tokens đúng backend.
- Không lưu user authentication state nhạy cảm lâu trong logs/cache ngoài policy.

### 10.5. JWT, secrets, crypto và dependencies

- JWT `iss`, `exp`, `nbf`, signature, trusted algorithms/JWKS được kiểm; `aud` theo yêu cầu API.
- Không chấp nhận `alg=none`, không “decode JWT mà không verify” rồi set Authentication.
- JWK caching/rotation và IdP outage có behavior fail-closed/availability được test.
- Client credentials, remember-me keys, database credentials và signing keys đến từ secrets manager/env được kiểm soát, không commit vào Git.
- Key rotation có kế hoạch; biết blast radius khi key bị lộ; không log secret.
- Dependency versions lấy từ Spring Boot BOM phù hợp release; Spring Security core/web/config/test đồng bộ.
- Theo dõi CVE/security advisories, SBOM và software supply-chain controls theo chính sách tổ chức.
- Container image/JDK cập nhật và chạy dưới quyền tối thiểu.

### 10.6. HTTP headers, cache và tài nguyên

- CSP phù hợp app: không tùy tiện bật `unsafe-inline`/`unsafe-eval`.
- `X-Content-Type-Options: nosniff` với MIME type chính xác.
- `frame-ancestors`/`X-Frame-Options` theo anti-clickjacking policy.
- HSTS chỉ khi có HTTPS phù hợp; kiểm response thực qua proxy.
- `Referrer-Policy`/`Permissions-Policy` khi có giá trị theo threat model.
- Dữ liệu nhạy cảm có `Cache-Control` phù hợp, thường `no-store`; static assets có cache policy riêng.
- Không mở upload files dạng active HTML trên application origin nếu không được cô lập và bảo vệ.
- Error pages không hiển thị stack trace, configuration hoặc internal identifiers.

### 10.7. Logging, observability và vận hành

- Audit login success/failure, access denied, privilege changes, account recovery, logout-all, key rotation theo policy riêng tư.
- Logging có request ID/correlation ID nhưng không chứa raw cookie/tokens/password.
- Giới hạn `org.springframework.security=TRACE` vào dev/test hoặc giai đoạn điều tra ngắn có kiểm soát.
- Health/readiness phản ánh DB/IdP/session dependencies hợp lý, không lộ sensitive details public.
- Metrics theo dõi `401/403/5xx`, login failures, JWT decoder issues, CSRF rejections, latency/rate limit.
- Có alert thresholds/baseline và hướng dẫn xử lý false positives.
- Đảm bảo secrets rotation, backup, incident response, alert routing và rollback owners được chỉ định.

## 11. Kiểm tra cấu hình theo môi trường

Một lỗi phổ biến là dev/test dùng HTTP localhost và mock auth, còn production đi qua CDN/reverse proxy, external IdP và nhiều replicas. **Một bộ test PASS ở local không chứng minh toàn bộ deployment**.

| Hạng mục | Local/test | Staging | Production |
| --- | --- | --- | --- |
| TLS | Có thể dùng localhost exemption cho dev | HTTPS như production | HTTPS/headers thật |
| JWT issuer/JWKS | Test keys/fixtures, mock cho unit-only | IdP test integration | Issuer/JWKS tin cậy |
| CORS origins | Dev origin chặt | Exact staging origins | Exact production origins |
| Session store | Mock/in-memory | Shared store nếu multi-node | HA/replication/TTL policy |
| Secrets | Test-only; không reuse production | Managed staging secrets | Secrets manager/rotation |
| Logging | Có thể bật DEBUG có kiểm soát | Tập trung, đã redact | INFO/audit, không TRACE rộng |
| Filter chain | MockMvc tests | HTTP/proxy tests | Live probes an toàn |
| Rollback | Không cần user traffic | Diễn tập deployment | Artifact/schema/session compat |

### 11.1. Fail closed và giới hạn phụ thuộc

Khi JWT verifier không tải được JWKS, không được chuyển sang “trust token payload” hoặc `permitAll` để duy trì traffic. Khi session store lỗi, không cho người dùng không xác thực thực hiện hành động nhạy cảm. Khi CORS policy lỗi, không mở `*` vô điều kiện. Cần đo downtime và thiết kế retry/cache/availability phù hợp nhưng vẫn giữ **authenticity/authorization checks**.

### 11.2. Management endpoints

`/actuator/health` có thể được cho public với mức chi tiết tối thiểu, nhưng `/actuator/env`, `/actuator/configprops`, `/actuator/heapdump`, `/actuator/loggers`, metrics và debug endpoints phải theo policy riêng, thường giới hạn network/role và exposure. Có thể Spring Boot management port dùng container/filter chain khác; cần test chính ingress thực. Không mặc định một rule `/actuator/**` permitAll bao phủ an toàn mọi endpoint.

## 12. Đánh giá chất lượng một ma trận kiểm thử

Một ma trận có **nhiều dòng** không đồng nghĩa đủ độ bao phủ. Cần kiểm các chiều:

1. **Endpoints:** các resource nhạy cảm và public/edge routes.
2. **HTTP methods:** GET/HEAD, POST, PUT, PATCH, DELETE, OPTIONS; path + method rules.
3. **Danh tính:** anonymous, user, admin, wrong tenant, disabled account, expired credential.
4. **Credential state:** thiếu, sai, hết hạn, revoked, đủ quyền, thiếu scope.
5. **Session state:** chưa login, authenticated, remembered, expired, concurrent, logged out.
6. **CSRF/CORS:** có/không CSRF, allow/disallowed origin, preflight, cookie flags.
7. **Dữ liệu:** schema đúng/sai, boundary sizes, IDOR, stored XSS, SQL params.
8. **Failure modes:** IdP timeout, DB unavailable, JWKS rotation, secrets invalid, proxy headers spoofed.
9. **Môi trường:** dev/test, staging, production-specific ingress, multi-node.
10. **Bằng chứng:** actual HTTP exchange/status/headers, DB state, audit, version/git commit.

Với mỗi **control quan trọng**, cần positive + negative tests: `GET /api/me` có scope đúng trả 200 và scope thiếu trả 403; web POST có CSRF thành công và thiếu CSRF bị từ chối; cookie/session hợp lệ cho phép, cookie sai không cho phép.

Đừng “đo coverage” bằng số lượng test methods nếu chúng đều dùng `@WithMockUser` và bỏ qua JWT decoder hoặc web filters. Coverage phần mềm đo code paths, còn security acceptance cần đo **bất biến/ranh giới thực tế**.

## 13. CI quality gates và release blockers

Một pipeline cơ bản:

```text
Compile + dependency audit
   -> Unit tests (validation/domain)
   -> MockMvc Spring Security filter tests
   -> Integration tests (DB/JWT decoder/session)
   -> Browser/HTTP tests (TLS/CORS/cookies/proxy)
   -> Security configuration review
   -> Staging smoke + approval
   -> Progressive rollout + monitoring
```

Ví dụ phân loại lỗi:

| Mức | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **P0 / release blocker** | Anonymous truy cập dữ liệu cá nhân; bypass tenant; JWT sai chữ ký vẫn được chấp nhận; CSRF bypass trên thao tác cookie-authenticated nhạy cảm | Không deploy, sửa và chạy lại tests |
| **P1 / release blocker** | API nhận nhầm chain; mất auth trên route; secrets bị commit; admin endpoint public; logout-all không revoke khi đã cam kết | Chặn release theo policy |
| **P2 / cần đánh giá** | Header bổ sung thiếu ở trang không nhạy cảm, test flakiness có giới hạn, log thiếu thông tin an toàn | Owner đánh giá rủi ro, fix trước rollout hoặc phê duyệt ngoại lệ rõ ràng |
| **N/A có giải thích** | Không có remember-me nên case remember-me không áp dụng | Reviewer xác nhận feature thực sự không tồn tại |

Đừng tự đặt tất cả lỗi 401/403 là P0: một 403 đúng vì policy có thể là **PASS**. Đánh giá dựa vào **actual vs expected behavior** và tác động tới bảo mật.

### 13.1. Trình tự xử lý một testcase FAIL

1. Ghi case ID, environment, build SHA, expected/actual, HTTP method/path, authenticated principal loại nào; **redact credentials**.
2. Xác định security chain được chọn (`FilterChainProxy`/TRACE dev).
3. Xác định lỗi authentication (401), authorization/CSRF (403), login redirect (302), routing (404/405) hay app error (5xx).
4. Nếu sai JWT, kiểm decoder/issuer/audience/algorithm chứ không sửa bằng `permitAll`.
5. Nếu sai CSRF, kiểm cookie authentication/CSRF token/same-origin flow, không tắt protection để qua test.
6. Sửa tại lớp có trách nhiệm; thêm regression test cho chính điều kiện gây lỗi.
7. Chạy lại test liên quan và full security matrix trước release.

## 14. Bằng chứng triển khai: kiểm tra qua HTTP thực

Với staging/production, dùng browser/devtools hoặc HTTP client có cookie jars riêng trong môi trường được cho phép. Ví dụ probe **an toàn chỉ đọc**:

```bash
# Chỉ kiểm endpoint công khai, không chứa token:
curl -i https://api.example.test/api/public/ping

# Kiểm header của HTML page (route thực cần do app cung cấp):
curl -I https://app.example.test/login

# Preflight CORS với origin được cho phép:
curl -i -X OPTIONS https://api.example.test/api/me \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Tên miền chỉ để minh họa; trên hệ thống thật thay bằng staging origin đã được kiểm soát. **Không đưa Bearer token/remember-me cookie/password vào shared shell history hoặc log.** `curl` không thực thi chính sách CORS như browser; nó giúp kiểm response headers nhưng **không chứng minh** browser thực sự chặn/cho phép script theo CORS. Dùng browser E2E riêng cho điều đó.

Nếu reverse proxy đổi scheme/host/port hoặc cache headers, kiểm **HTTP response sau ingress/CDN**, không chỉ nhìn `MockMvc` ở backend.

### 14.1. Hồ sơ chứng cứ tối thiểu

Một release packet gọn có:
- Migration/dependency manifest và source commit;
- danh sách SecurityFilterChain + matcher/order đã rà soát;
- test matrix với case IDs, results, build/environment;
- JWT crypto integration report;
- CSRF/session/CORS/browser test report;
- headers/TLS/proxy probe evidence đã redact;
- các exceptions/risks còn mở và người phê duyệt;
- rollback steps và on-call owner.

Không đưa session IDs, tokens, credentials, raw JWT, private keys hoặc full request bodies có dữ liệu cá nhân vào tài liệu nghiệm thu.

## 15. Lỗi phổ biến khi chốt bài thực hành

1. **Chỉ test happy path:** có 200 nhưng không test anonymous, thiếu role, token sai hoặc CSRF.
2. **Một bảng quá chung:** “API authorization PASS” không chỉ rõ endpoint/method/user/context.
3. **Dùng `with(jwt())` rồi kết luận decoder xác minh chữ ký:** đã mock Authentication, chưa test cryptography.
4. **Dùng `@WithMockUser` để test form login/session fixation:** đã bỏ qua quy trình credential login.
5. **Dùng status 403 để suy ngay lỗi phân quyền:** 403 có thể do CSRF.
6. **Dùng CORS để bảo vệ API thay authentication:** client ngoài browser vẫn gọi được API nếu không auth.
7. **Tắt CSRF toàn cục vì API dùng JSON:** cookie/session web vẫn dễ bị CSRF.
8. **Đặt catch-all chain trước API chain:** route API vào sai filter chain.
9. **Cho `/api/**` permitAll chỉ để qua test:** có thể tạo bypass nghiêm trọng.
10. **Không kiểm owner/tenant:** JWT có scope chung vẫn đọc được dữ liệu người khác.
11. **Chỉ test local HTTP:** bỏ sót `Secure` cookie/HSTS/proxy trust vấn đề thật.
12. **Log token để debug:** gây rò rỉ credential qua log/CI artifacts.
13. **Quên giới hạn actuator:** management endpoints có thể lộ cấu hình hoặc runtime state.
14. **Tin HTTP header thay output encoding/input validation:** CSP/HSTS không thay xử lý XSS/SQLi.
15. **Xem xóa remember-me cookie là thu hồi mọi bản sao token:** token-based remember-me có rủi ro riêng.
16. **Test hai tab cùng browser để chứng minh session concurrency:** thường vẫn dùng chung cookie jar/session.
17. **Không có rollback plan:** khi rollout xảy ra lỗi session/IdP/DB, không có đường hồi phục được kiểm chứng.
18. **Thấy test suite xanh nhưng runtime versions lệch BOM:** cần check resolved dependencies và container JDK/Jakarta compatibility.
19. **Bỏ qua failures của upstream:** JWKS/IdP/session store lỗi không được fail open.
20. **Ghi PASS không có evidence:** không truy ra environment, build ID hay test method nào xác minh hành vi.

## 16. Checklist bàn giao cuối bài

- [ ] Có inventory các URLs, HTTP methods, principals, scopes/roles, owner/tenant, auth mechanisms và session flows.
- [ ] Mỗi endpoint nhạy cảm có test anonymous + authenticated đúng + authenticated thiếu quyền.
- [ ] JWT/opaque token được test thật về issuer/signature/expiry/audience theo policy, không chỉ `with(jwt())`.
- [ ] CSRF được bật khi browser tự gửi credential; POST/logout có negative CSRF tests.
- [ ] CORS origin/method/header và preflight được test ở browser/proxy thật.
- [ ] Filter chains có `securityMatcher`/`@Order` đúng, catch-all ở cuối và không có unprotected URL ngoài ý muốn.
- [ ] Domain authorization/IDOR/tenant boundaries được kiểm ở service và DB.
- [ ] Form login, session fixation, concurrency, remember-me, logout có test nếu feature sử dụng.
- [ ] Validation, parameterized SQL, output encoding và safe redirects/uploads có negative tests.
- [ ] TLS, HSTS, cookies, CSP, headers và proxy trust đã được kiểm trên deployment thực.
- [ ] Secrets, keys, JWK rotation, dependency BOM, JDK/container version và SBOM được rà soát.
- [ ] Actuator/management endpoints không public trái policy; readiness không lộ secrets.
- [ ] Không log raw credentials; audit/metrics/alerts có owner và retention.
- [ ] Test evidence có case ID, build commit, environment, expected/actual, timestamp và owner.
- [ ] Mọi blocker đã được sửa, mọi exception có phê duyệt và risk acceptance rõ ràng.
- [ ] Kịch bản canary/rollout/rollback đã được chuẩn bị và có người chịu trách nhiệm.

**Kết luận:** Một cấu hình Spring Security Servlet chỉ được nghiệm thu khi **ma trận kiểm thử chứng minh các bất biến bảo mật** và **rà soát deployment chứng minh môi trường chạy thật vẫn giữ chúng**. Hãy kết hợp kiểm thử filter chain/401/403/CSRF bằng MockMvc, xác minh token crypto và dữ liệu bằng integration tests, kiểm cookie/CORS/TLS/proxy bằng browser/HTTP thật, rồi quản lý release bằng evidence, owners và rollback plan. **“Build thành công” và “test happy path xanh” là điểm bắt đầu, không phải kết luận bảo mật.**
