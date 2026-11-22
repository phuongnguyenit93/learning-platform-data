# Chẩn đoán 403 do thiếu quyền, tiền tố ROLE_ hoặc CSRF trong Spring Security Reactive

## 1. Mục tiêu và phạm vi

Bài này tập trung vào lỗi **HTTP 403 Forbidden** trong ứng dụng **Spring WebFlux + Spring Security reactive**: khi request được xác thực nhưng không có authority cần thiết, khi cấu hình `hasRole`/`hasAuthority` dùng sai tiền tố `ROLE_`, hoặc khi request thay đổi trạng thái thiếu/sai **CSRF token**. Đây là ba nguyên nhân thường có cùng biểu hiện ở phía client nhưng cách sửa khác nhau.

Sau bài học, bạn cần:

1. Phân biệt 401, 403, redirect tới trang đăng nhập và lỗi CORS/gateway; tìm đúng thành phần đã trả 403.
2. Đối chiếu `Authentication.getAuthorities()` với luật `authorizeExchange` và `@PreAuthorize` mà không nhầm `ROLE_`, `SCOPE_` hoặc chuỗi chưa có tiền tố.
3. Kiểm tra CSRF theo HTTP method, cookie/session, header/form token, cách Spring Security 6 bảo vệ token, đặc biệt trong SPA.
4. Dùng `WebTestClient` của Spring Security để chứng minh độc lập trường hợp đủ quyền, thiếu quyền, thiếu CSRF và đủ cả hai.
5. Khắc phục nguyên nhân gốc trong khi giữ nguyên nguyên tắc **chỉ trao đúng quyền cần thiết**.

Các đoạn tích hợp sử dụng API của Spring Security 6.x/Spring Boot 3.x và Java 17+. Một số mẫu nằm trong dự án WebFlux/Spring Boot đã tồn tại; phần mô phỏng Java thuần ở mục 5 có thể biên dịch độc lập.

## 2. 403 có nghĩa gì, và điều gì không thể kết luận?

`403` cho biết phía xử lý request từ chối cho phép truy cập. Với Spring Security, 403 thường xuất hiện khi một `Authentication` đã được thiết lập nhưng không thỏa luật authorization, hoặc khi `CsrfWebFilter` từ chối thao tác không an toàn. Tuy nhiên, cùng mã trạng thái cũng có thể do gateway, reverse proxy, WAF, controller, service hoặc custom error handler trả về.

| Hiện tượng | Giải thích thường gặp | Kiểm tra đầu tiên |
| --- | --- | --- |
| Không có token/không đăng nhập, API trả `401` | Chưa xác thực; entry point yêu cầu credentials | `Authorization` header, cookie, chính sách authentication |
| Không đăng nhập, browser trả `302` tới `/login` | Entry point cho form login | `Location` header và chain áp dụng |
| JWT hợp lệ, GET trả `403` | Không đủ `GrantedAuthority` hoặc điều kiện access | `Authentication.getAuthorities()` và matcher/annotation |
| `GET` thành công, `POST/PUT/DELETE` trả `403` dù cùng user | Nghi CSRF hoặc quyền phụ thuộc method | CSRF token, HTTP method, luật riêng từng method |
| Browser báo lỗi CORS khi preflight `OPTIONS` | Trình duyệt bị chặn ở CORS hoặc tầng trước | Network: actual request có được gửi không; `OPTIONS` status và CORS headers |
| Tất cả request đều 403, kể cả đường dẫn không bảo vệ | Sai `SecurityWebFilterChain`, gateway, WAF, `denyAll` hoặc custom handler | Xác định nơi tạo response trước khi sửa Spring Security |
| Service method trả `AccessDeniedException` | Method-level security hoặc kiểm tra nghiệp vụ từ chối | `@PreAuthorize`, `@PostAuthorize`, authorization service |

**Không thể suy ra từ riêng mã 403** rằng token sai hay user thiếu role. Một request POST có đủ role vẫn có thể bị CSRF từ chối trước khi kiểm tra route. Một request GET không chịu CSRF cũng có thể 403 vì `SCOPE_`/`ROLE_` sai. Cần giữ nguyên các điều kiện request khi so sánh.

Luồng tư duy:

```text
Client gửi request
   |
   v
Reverse proxy / API Gateway / WAF
   |-- 403 ở đây? -> xem log và policy tầng trước
   v
Spring Security WebFilter chain khớp request
   |
   +-- Unsafe method + CSRF không hợp lệ? -> 403, kiểm tra token/session
   |
   +-- Authentication không hợp lệ? -> 401 / redirect / lỗi theo entry point
   |
   +-- Authorization thiếu authority/không qua policy? -> 403
   |
   v
Controller -> Service / @PreAuthorize -> domain checks
   |-- Denied? -> 403 hoặc response do app định nghĩa
   v
2xx / 4xx / 5xx khác
```

Thứ tự chi tiết có thể thay đổi theo filter chain và customizations; sơ đồ dùng để **khoanh vùng nguyên nhân**, không phải mô tả thứ tự tuyệt đối của mọi `WebFilter`.

## 3. Quy trình khoanh vùng 403 theo bằng chứng

### Bước 1: ghi lại một request tái hiện chính xác

Lưu các trường **không nhạy cảm**: method, đường dẫn đã chuẩn hóa, môi trường, status, timestamp, correlation ID, chain/route dự kiến. Trong kênh chẩn đoán có kiểm soát, kiểm tra kiểu xác thực (session/JWT/Basic), principal đã được xác thực và **tên** authorities được cấp. **Không** đưa bearer token, session cookie, raw CSRF token, mật khẩu hay `Authorization` header vào log/ticket.

Với DevTools, phân biệt request `OPTIONS` preflight với request `POST` thực sự. Với command-line, ví dụ so sánh cùng một đường dẫn (đổi host cho môi trường kiểm thử):

```bash
# Chỉ là request ví dụ, endpoint/credentials cần phù hợp môi trường.
curl -i https://localhost:8443/reports/demo
curl -i -X POST https://localhost:8443/reports/demo
```

Hai lệnh trên không có credentials, nên chưa chứng minh thiếu quyền hay CSRF; chúng chỉ kiểm tra response chain/headers. Khi lặp lại một request lỗi, dùng **test credentials hợp lệ trong môi trường staging** và giữ mọi biến giống nhau trừ thành phần đang thử. Không gửi token thật lên dịch vụ bên thứ ba để giải mã/debug.

### Bước 2: bật log bảo mật trong thời gian ngắn ở môi trường được phép

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.server.csrf: TRACE
```

Các logger Spring Security có thể giúp tìm filter chain, thao tác CSRF và authorization. Định dạng/thông điệp cụ thể khác nhau theo phiên bản; không viết logic phụ thuộc nguyên văn câu log. Thu hẹp log theo request/correlation ID, giới hạn retention/quyền xem; trả về mức log bình thường sau khi xác định lỗi. Chẩn đoán 403 **không đòi** bật TRACE cho toàn bộ ứng dụng hoặc ghi raw headers.

Ở ứng dụng Reactive, đừng dựa vào `ThreadLocal` hoặc `SecurityContextHolder` theo kiểu servlet khi đang ở callback Reactor. Spring Security WebFlux lưu security context trong **Reactor Context**; truy xuất qua `ReactiveSecurityContextHolder`.

Một method minh họa bên trong Spring bean có thể thu được danh sách authority để **kiểm thử nội bộ**, không công khai thành endpoint:

```java
import java.util.stream.Collectors;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> authorizedNamesForDiagnostics() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication())
            .map(auth -> auth.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .collect(Collectors.joining(",")))
            .defaultIfEmpty("(no reactive SecurityContext)");
}
```

Hàm này chỉ cho biết các **authority string** tại subscription hiện tại, không xác định người dùng có quyền đối với một resource cụ thể. Không log tên principal/tài khoản nếu policy không cho phép; trong production, ưu tiên metric/structured event đã được kiểm duyệt và số lượng từ chối theo nguyên nhân.

### Bước 3: thử lần lượt các giả thuyết

1. Nếu lỗi chỉ ở method **không an toàn** (POST/PUT/PATCH/DELETE), thử cùng user với **CSRF token đúng, cùng phiên**. Nếu hết 403, nguyên nhân ở nhánh CSRF; nếu vẫn 403, kiểm tra tiếp authority/route và domain policy.
2. Nếu lỗi cả ở GET, kiểm tra matcher đã chọn, `Authentication` và danh sách `GrantedAuthority` chính xác, bao gồm chữ hoa/thường và tiền tố.
3. Nếu có JWT, kiểm tra token đã được **xác minh hợp lệ** trước; sau đó phân biệt `scope` của JWT thành `SCOPE_*` với business role thành `ROLE_*`. Chỉ giải mã payload JWT mà chưa xác minh chữ ký không đủ cơ sở cấp quyền.
4. Nếu route authorize thành công nhưng vẫn 403, xét `@PreAuthorize`, `@PostAuthorize`, security của service/gateway và kiểm tra ownership nghiệp vụ. Đừng thay đổi policy trước khi biết tầng nào từ chối.
5. Nếu chỉ lỗi trên trình duyệt, kiểm tra CORS preflight, cookie/session, SameSite, Origin và cách JavaScript gửi CSRF header; Postman/curl có hành vi khác browser và không đủ để kết luận.

## 4. `GrantedAuthority`, `hasAuthority` và tiền tố `ROLE_`

### 4.1. Role trong Spring Security thực chất là authority có quy ước tên

`Authentication.getAuthorities()` trả về danh sách `GrantedAuthority`. Giá trị của `GrantedAuthority.getAuthority()` là chuỗi, ví dụ:

```text
ROLE_ADMIN
ROLE_REPORT_VIEWER
SCOPE_reports.read
ORDER_APPROVE
```

- `hasAuthority("ROLE_ADMIN")` so sánh trực tiếp với chuỗi `ROLE_ADMIN`.
- `hasRole("ADMIN")` là cách viết ngắn, mặc định tìm authority `ROLE_ADMIN`. **Truyền `ADMIN` vào `hasRole`, không truyền `ROLE_ADMIN`.**
- `hasAuthority("ADMIN")` cần chuỗi đúng `ADMIN`; nó không tự thêm `ROLE_`.
- `hasAuthority("SCOPE_reports.read")` kiểm tra scope JWT theo mapping OAuth2 mặc định.
- So sánh tên authority phân biệt chữ hoa/thường, dấu chấm, gạch ngang và tiền tố; `role_admin`, `ROLE_ADMIN`, `ADMIN` là ba giá trị khác nhau.

Bảng quyết định với quy ước tiền tố mặc định:

| Authorities hiện có | Rule | Kết quả | Giải thích |
| --- | --- | --- | --- |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Cho phép | Spring thêm `ROLE_` khi so sánh |
| `ROLE_ADMIN` | `hasAuthority("ROLE_ADMIN")` | Cho phép | So sánh chính xác |
| `ROLE_ADMIN` | `hasAuthority("ADMIN")` | Từ chối | Thiếu tiền tố ở rule |
| `ADMIN` | `hasRole("ADMIN")` | Từ chối | Thiếu `ROLE_` trong granted authority |
| `SCOPE_admin` | `hasRole("ADMIN")` | Từ chối | Scope OAuth2 không tự biến thành role |
| `SCOPE_reports.read` | `hasAuthority("SCOPE_reports.read")` | Cho phép | Đúng tên scope được map |
| `ROLE_REPORT_VIEWER` | `hasRole("report_viewer")` | Từ chối | Sai chữ hoa/thường |

`hasRole("ROLE_ADMIN")` **không phải cách sửa**: nhiều API/version của Spring Security sẽ báo rằng tham số role không được bắt đầu với `ROLE_`, thay vì âm thầm hiểu nó là authority hợp lệ. Để so sánh authority đã có tiền tố, dùng `hasAuthority("ROLE_ADMIN")`.

Nếu ứng dụng chủ động cấu hình tiền tố role khác qua cơ chế phù hợp (ví dụ `GrantedAuthorityDefaults` ở method security), phải kiểm tra cấu hình có hiệu lực ở chính lớp authorization đó. Đừng giả định sửa prefix ở một converter tự động đổi nghĩa của mọi `hasRole` trong filter chain và method annotations.

### 4.2. Ví dụ `SecurityWebFilterChain` reactive

Cấu hình dưới đây yêu cầu role `VIEWER` cho GET và `EDITOR` cho POST; CSRF vẫn bật. Đây là cấu hình Java của một **ứng dụng Spring Boot WebFlux đã có sẵn**:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReportSecurityConfig {
    @Bean
    SecurityWebFilterChain reportSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/reports/demo")
                    .hasRole("VIEWER")
                .pathMatchers(HttpMethod.POST, "/reports/demo")
                    .hasRole("EDITOR")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Điểm cần hiểu:

- `hasRole("VIEWER")` đòi `ROLE_VIEWER`; `hasRole("EDITOR")` đòi `ROLE_EDITOR`.
- Từng method có policy riêng. Request `PUT /reports/demo` đi vào `denyAll()` vì không khớp GET/POST, ngay cả khi người dùng có `ROLE_EDITOR`.
- `httpBasic` cho phép ví dụ xác thực qua HTTP Basic khi được cấu hình user store; **CSRF vẫn áp dụng** cho unsafe methods theo cấu hình này vì trình duyệt có thể tự gửi Basic credentials.
- `anyExchange().denyAll()` minh họa chính sách mặc định chặt. Đừng đổi thành `permitAll()` để xử lý 403.
- Nếu ứng dụng có nhiều `SecurityWebFilterChain` theo `securityMatcher`/`@Order`, phải xác nhận chain nào thật sự nhận đường dẫn. Rule trong một chain khác không giúp request đang khớp chain hiện tại.
- Spring WebFlux sử dụng `ServerHttpSecurity` + `SecurityWebFilterChain`. Đừng sao chép `HttpSecurity`/`SecurityFilterChain`/`authorizeHttpRequests` của **Servlet** rồi mong chúng có tác dụng tương đương trong WebFlux.

### 4.3. Nguồn gây mismatch khi xác thực username/password

Ví dụ app cấp user authorities là `["ADMIN"]`, còn rule là `hasRole("ADMIN")`. Authentication có thể **thành công** nhưng authorization **403** vì Spring đòi `ROLE_ADMIN`. Nếu domain thực sự đang dùng quy ước role, hãy sửa mapper ở nguồn đáng tin để phát hành `ROLE_ADMIN` hoặc đổi rule sang `hasAuthority("ADMIN")` nếu đó là mô hình được thiết kế từ đầu.

Không giải quyết bằng cách bổ sung mọi role cho mọi tài khoản, chuyển cả chain sang `authenticated()`, hoặc thêm một “admin fallback”. Sửa một bên dựa trên **hợp đồng authority chuẩn** và kiểm thử các endpoint khác để tránh cấp quyền quá mức.

## 5. Bài tập Java 17 tự chạy: nhìn thấy nguyên nhân mismatch

Ví dụ này **mô phỏng cách kiểm tra chuỗi**, không dùng thư viện Spring và không thay thế kiểm tra server thực. Lưu vào `AuthorityDiagnosticDemo.java`:

```java
import java.util.Set;

public final class AuthorityDiagnosticDemo {
    static boolean hasAuthority(Set<String> actual, String required) {
        return actual.contains(required);
    }

    static boolean hasRole(Set<String> actual, String role) {
        if (role.startsWith("ROLE_")) {
            throw new IllegalArgumentException("pass role without ROLE_ prefix");
        }
        return hasAuthority(actual, "ROLE_" + role);
    }

    public static void main(String[] args) {
        Set<String> user = Set.of(
                "ADMIN", "ROLE_VIEWER", "SCOPE_reports.read");

        System.out.println("hasRole ADMIN: " + hasRole(user, "ADMIN"));
        System.out.println("hasAuthority ADMIN: "
                + hasAuthority(user, "ADMIN"));
        System.out.println("hasRole VIEWER: " + hasRole(user, "VIEWER"));
        System.out.println("hasRole reports.read: "
                + hasRole(user, "reports.read"));
        System.out.println("hasAuthority SCOPE_reports.read: "
                + hasAuthority(user, "SCOPE_reports.read"));
    }
}
```

Chạy với JDK 17+:

```bash
javac --release 17 AuthorityDiagnosticDemo.java
java AuthorityDiagnosticDemo
```

Stdout chính xác:

```text
hasRole ADMIN: false
hasAuthority ADMIN: true
hasRole VIEWER: true
hasRole reports.read: false
hasAuthority SCOPE_reports.read: true
```

Bài học: **có một authority không có nghĩa mọi rule mang tên gần giống đều match**. Khi gặp 403, so sánh giá trị thực từ `getAuthorities()` với giá trị rule yêu cầu, cả tiền tố.

## 6. JWT OAuth2 resource server: `SCOPE_` khác `ROLE_`

Với resource server WebFlux xác minh JWT, Spring Security mặc định chuyển claim `scope` hoặc `scp` thành authorities có tiền tố `SCOPE_`. Ví dụ token hợp lệ có claim:

```json
{
  "iss": "https://id.example.org/tenant-a",
  "sub": "user-42",
  "aud": ["reports-api"],
  "scope": "reports.read reports.write"
}
```

Sau khi token **được decoder xác minh thành công**, những scope trên thường được chuyển thành:

```text
SCOPE_reports.read
SCOPE_reports.write
```

Chúng **không tự trở thành** `ROLE_REPORTS_READ` hoặc `ROLE_ADMIN`. Vì vậy:

```java
// Đoạn cấu hình minh họa cho JWT resource server WebFlux.
// Đây là một SecurityWebFilterChain riêng, không ghép với
// ReportSecurityConfig của ví dụ Basic/CSRF.
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers(HttpMethod.GET, "/api/reports/**")
                .hasAuthority("SCOPE_reports.read")
            .pathMatchers(HttpMethod.POST, "/api/reports/**")
                .hasAuthority("SCOPE_reports.write")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .build();
}
```

Cần có các import tương ứng ở ví dụ `ReportSecurityConfig`, cộng dependency `spring-boot-starter-oauth2-resource-server` và cấu hình issuer/JWK set. Không đưa riêng phương thức này vào codebase nếu đang có cấu hình SecurityWebFilterChain trùng matcher; hãy xác định phạm vi chain trước.

Nếu rule viết `hasRole("REPORTS_READ")` trong khi token chỉ cấp `SCOPE_reports.read`, request hợp lệ vẫn 403. Sửa **rule phù hợp với mô hình authorization** (scope OAuth2 thì dùng `SCOPE_`) hoặc, nếu nghiệp vụ thật sự dùng role, thiết kế converter từ claim **role đáng tin** với allowlist và tiền tố được nhất quán ở mọi nơi.

**Không map tùy tiện** mọi scope thành `ROLE_ADMIN`. Chỉ các role do issuer đáng tin cấp theo hợp đồng, sau khi token được xác thực và kiểm tra `iss`, `aud`, `exp`, `nbf`, mới có thể trở thành authority; vẫn cần least privilege. Một token có payload ghi `"roles":["ADMIN"]` nhưng chữ ký sai không phải bằng chứng quyền admin.

Trong test WebFlux, `mockJwt().authorities(new SimpleGrantedAuthority("SCOPE_reports.read"))` giúp cô lập **authorization behavior**. Nó không chứng minh decoder sẽ chấp nhận token production; cần integration test riêng cho JWT signature/issuer/audience và converter.

## 7. CSRF: nguyên nhân 403 ngay cả khi user đủ quyền

### 7.1. Vì sao CSRF kiểm tra khác authorization?

**Cross-Site Request Forgery** xảy ra khi browser tự mang credentials của một user đang đăng nhập (thường là session cookie hoặc HTTP Basic/những cơ chế tự gửi tương tự) theo yêu cầu do trang khác kích hoạt. Kẻ tấn công không cần đọc response để có thể gây ra một thao tác thay đổi trạng thái nếu hệ thống không kiểm tra bằng chứng mà trang khác khó có được.

Spring Security WebFlux **bật CSRF protection theo mặc định**. Những method được coi là an toàn như GET, HEAD, OPTIONS, TRACE thường được bỏ qua kiểm tra CSRF; các method khác như POST/PUT/PATCH/DELETE cần token hợp lệ, trừ khi ứng dụng cấu hình matcher khác. **GET phải không tạo side effect** nếu muốn dựa vào ngoại lệ “safe method”.

Ví dụ user `alice` có `ROLE_EDITOR` gửi POST và đã vượt qua điều kiện role:

```text
POST /reports/demo
Cookie: SESSION=...
X-CSRF-TOKEN: (không có)
```

Mặc dù role đúng, `CsrfWebFilter` có thể trả 403 vì thiếu token. Nếu chỉ bổ sung `ROLE_EDITOR` mà không xử lý CSRF thì không khắc phục được. Ngược lại, nếu đã có CSRF token hợp lệ nhưng user chỉ có `ROLE_VIEWER`, request POST vẫn 403 vì thiếu role. **Hai điều kiện phải cùng đúng**.

### 7.2. Repository CSRF và tên header trong WebFlux

Mặc định Spring Security reactive lưu expected CSRF token trong `WebSession` với `WebSessionServerCsrfTokenRepository`; tên header mặc định thường là `X-CSRF-TOKEN`, tham số form `_csrf`. Cần gửi token nhận được cho **cùng phiên** đang dùng, qua trường form hoặc header phù hợp. Token copy từ tab/browser/session khác không chứng minh hợp lệ.

Nếu dùng `CookieServerCsrfTokenRepository`, mặc định cookie có tên `XSRF-TOKEN` và server đọc token từ header `X-XSRF-TOKEN` (hoặc tham số `_csrf`). Cấu hình hỗ trợ client JavaScript đọc cookie:

```java
// Đoạn thêm vào builder ServerHttpSecurity của ứng dụng SPA
.csrf(csrf -> csrf.csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
```

Import: `org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository`. Chỉ chọn `withHttpOnlyFalse()` khi JavaScript **phải đọc cookie** để gửi header; nếu không cần, dùng repository giữ HttpOnly để giảm bề mặt tiếp cận. Cookie `XSRF-TOKEN` là token chống CSRF, **không phải** cookie đăng nhập; ứng dụng vẫn cần policy session/SameSite/Secure/CORS phù hợp.

**Lưu ý Spring Security 6:** mặc định dùng `XorServerCsrfTokenRequestAttributeHandler` để bảo vệ khi xuất token nhằm giảm rủi ro BREACH. Với SPA đọc token *thô* từ cookie rồi gửi header, phải kiểm tra cách request handler của **chính phiên bản WebFlux** giải mã/xử lý token; đừng giả định một ví dụ trên Servlet với `CsrfTokenRequestHandler` áp dụng nguyên xi cho Reactor. Tài liệu WebFlux có `ServerCsrfTokenRequestAttributeHandler` để dùng handler đơn giản hơn khi có nhu cầu tương thích đặc biệt, nhưng bỏ lớp che token phải được đánh giá về bảo vệ BREACH. Trước khi thay handler, thử một round-trip lấy token → gửi POST với cùng phiên rồi đối chiếu token dạng raw/masked theo cấu hình thực tế.

### 7.3. HTML form, SPA và session lifecycle

- **Server-rendered form:** giữ token đã được Spring Security phát hành trong hidden field `_csrf` của form POST; tích hợp Thymeleaf có hỗ trợ tạo CSRF field khi được cấu hình đúng. Form GET không cần token vì không được dùng để thay đổi trạng thái.
- **SPA dùng cookie:** lấy token được cấp cho phiên, đọc cookie nếu thiết kế cho phép, gửi đúng header ở request thay đổi trạng thái; cấu hình CORS/same-site phải phù hợp và không đưa token lên URL/log. Kiểm tra handler XOR của Spring Security 6.
- **Đăng nhập/đăng xuất và session timeout:** CSRF token có thể bị invalidated hoặc hết hiệu lực khi session đổi. Sau đó client phải lấy token mới; request dùng token cũ có thể bị 403 mặc dù người dùng đã đăng nhập.
- **HTTP client không giữ cookie:** với repository dựa trên `WebSession`, gửi một token nhưng bỏ mất session cookie sẽ khiến server không có expected token tương ứng. Luôn kiểm tra cookie jar và response Set-Cookie.
- **HTTPS và reverse proxy:** cookie `Secure`, `SameSite` và domain/path ảnh hưởng việc browser mang cookie; proxy có thể làm origin/host lệch nếu cấu hình forwarding không đúng.
- **Đừng sửa bằng CORS tùy tiện:** CORS điều khiển browser truy cập cross-origin; nó không thay thế token chống CSRF. Bật wildcard origin cùng credentials hoặc loại bỏ CSRF là thay đổi bảo mật riêng, không phải cách chẩn đoán.

### 7.4. Có được tắt CSRF cho API bearer không?

Có trường hợp một API **thuần bearer token**, hoàn toàn không dựa vào credentials tự gửi từ browser, được thiết kế stateless và **không cần CSRF** cho đúng nhóm endpoint đó. Ví dụ resource server chỉ chấp nhận bearer header do client chủ động đặt; trong ứng dụng thiết kế và kiểm chứng như vậy, có thể giới hạn CSRF theo `securityMatcher`/matcher phù hợp.

Nhưng **không mặc định tắt CSRF cho toàn bộ ứng dụng** chỉ vì API dùng JSON hoặc tên đường dẫn bắt đầu `/api`: một ứng dụng có thể vừa hỗ trợ cookie session/form login, vừa cung cấp API. Không dùng `csrf.disable()` như bước đầu tiên khi thấy 403.

Nếu sau review thật sự quyết định tắt CSRF ở một security chain riêng chỉ dành cho bearer-only API, phải chứng minh không có session/Basic/cookie authentication tự gửi cho các endpoint trong chain đó, kiểm tra chain ordering và giữ authorization chặt. Cấu hình session/browser còn lại vẫn cần CSRF. Việc **bỏ CSRF có chủ đích** khác với việc **bỏ xác thực hoặc cấp thêm quyền**.

## 8. Ví dụ tích hợp có kiểm thử: phân biệt ROLE_ và CSRF bằng WebTestClient

Đây là fixture có thể đặt trong **một dự án Spring Boot 3.x WebFlux hiện hữu**. Dùng ba tệp Java cùng package `demo`, không dùng endpoint production thật. Nó minh họa bốn kết quả riêng: GET đúng role thành công; GET authority thiếu tiền tố 403; POST có role nhưng thiếu CSRF 403; POST có cả role và CSRF thành công.

Dependencies trong `build.gradle` của ứng dụng dùng Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**Tệp 1:** `src/main/java/demo/ReportSecurityConfig.java` — nội dung như mục 4.2. Trong fixture, chỉ khai báo **một** security chain đó; không đưa thêm cấu hình JWT ở mục 6 vào cùng test.

**Tệp 2:** `src/main/java/demo/ReportEndpoint.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReportEndpoint {
    @GetMapping("/reports/demo")
    public Mono<String> read() {
        return Mono.just("read-ok");
    }

    @PostMapping("/reports/demo")
    public Mono<String> write() {
        return Mono.just("write-ok");
    }
}
```

**Tệp 3:** `src/test/java/demo/ReportAccessTest.java`:

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@WebFluxTest(controllers = ReportEndpoint.class)
@Import(ReportSecurityConfig.class)
class ReportAccessTest {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void viewerRoleCanGet() {
        client.mutateWith(mockUser("alice").roles("VIEWER"))
                .get().uri("/reports/demo")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("read-ok");
    }

    @Test
    void unprefixedAuthorityCannotSatisfyHasRole() {
        client.mutateWith(mockUser("alice").authorities(
                        new SimpleGrantedAuthority("VIEWER")))
                .get().uri("/reports/demo")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorWithoutCsrfCannotPost() {
        client.mutateWith(mockUser("alice").roles("EDITOR"))
                .post().uri("/reports/demo")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorWithCsrfCanPost() {
        client.mutateWith(mockUser("alice").roles("EDITOR"))
                .mutateWith(csrf())
                .post().uri("/reports/demo")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("write-ok");
    }

    @Test
    void viewerWithCsrfStillCannotPost() {
        client.mutateWith(mockUser("alice").roles("VIEWER"))
                .mutateWith(csrf())
                .post().uri("/reports/demo")
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Lưu ý về import static: để tránh một import bị cắt sai khi sao chép, trong Java có thể viết ba dòng riêng liền mạch như sau:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
```

**Khi chạy thực tế, dùng ba dòng import liền mạch trên thay cho ba cặp dòng xuống hàng trong khối test** nếu công cụ/formatter của bạn không hỗ trợ cách trình bày import. Java cho phép whitespace trước dấu `.`; cả hai cách đều là cùng một import, nhưng một dòng làm ví dụ dễ sao chép hơn.

Chạy test bằng Gradle wrapper của **chính dự án**:

```bash
./gradlew test --tests demo.ReportAccessTest
```

Hoặc trên Windows:

```powershell
.\gradlew.bat test --tests demo.ReportAccessTest
```

Các assertion thể hiện kỳ vọng. Không có một stdout cố định độc lập với Gradle, JDK, test framework và cấu hình dự án; khi tất cả test qua, Gradle báo `BUILD SUCCESSFUL` theo cấu hình thông thường. `mockUser` và `csrf()` chỉ là công cụ test; chúng không cung cấp user, secret hay token thật cho production. Test này kiểm tra **authorization/CSRF trong chain mock**, không thay thế integration test cho IdP, JWT signature, cookie trình duyệt hoặc reverse proxy.

## 9. Vì sao vẫn 403 dù test đã tạo user có quyền?

### 9.1. Method-level security là một tầng quyết định riêng

Nếu ứng dụng bật `@EnableReactiveMethodSecurity`, method có thể có điều kiện như:

```java
// Ví dụ method trong Spring-managed service.
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Mono<Report> loadReport(String id) {
    return reportRepository.findById(id);
}
```

Điều kiện ở `authorizeExchange` cho request đi tới controller **không loại bỏ** điều kiện `@PreAuthorize` tại method. Một token có `ROLE_VIEWER` nhưng thiếu `SCOPE_reports.read` vẫn có thể bị từ chối ở service.

Muốn dùng method security với Reactor, bảo đảm method nhận/trao quyền thông qua reactive security context. Không thay `Mono`/`Flux` bằng `block()` trong request thread, không tự tạo `subscribe()` ngoài vòng đời handler và không giả định `SecurityContextHolder` servlet sẽ chứa user của WebFlux. Cũng cần kiểm tra proxy method security: gọi nội bộ `this.securedMethod()` trong cùng bean có thể bỏ qua AOP proxy, đó là nguy cơ **bypass**, không phải cách khắc phục 403.

Nếu lỗi xuất hiện sau khi chuyển từ servlet sang WebFlux, rà soát cả `@EnableMethodSecurity`/`@EnableReactiveMethodSecurity` và lớp config đúng cho reactive. Không cố giữ `HttpSecurity` hoặc `OncePerRequestFilter` làm chính sách WebFlux.

### 9.2. Matcher và thứ tự của nhiều chain

Một số ví dụ sai thường gặp:

```java
// Sai thứ tự: rule rộng bắt trước, rule cụ thể không còn cơ hội.
.authorizeExchange(ex -> ex
    .pathMatchers("/**").authenticated()
    .pathMatchers("/admin/**").hasRole("ADMIN")
    .anyExchange().denyAll())
```

Rule rộng `/**` sẽ làm luật `/admin/**` không được áp dụng. Trong ví dụ này `authenticated()` còn có thể **quá dễ dãi** chứ không chỉ gây 403. Quy tắc: kiểm tra route/method cụ thể trước, wildcard sau, và thêm test đảm bảo các endpoint nhạy cảm không bị nới lỏng.

Với nhiều chain:

```text
Chain A: securityMatcher("/api/**")       -> JWT + SCOPE_...
Chain B: securityMatcher("/**")           -> session + CSRF + ROLE_...
```

Nếu thứ tự `@Order` hoặc matcher khác dự kiến, request `/api/reports` có thể đi vào chain B, khiến CSRF/authority khác xuất hiện. Tránh sửa từng rule trước khi xác định chain thực tế đã được chọn. Khi request đi qua gateway có rewrite path hoặc context path, phải so sánh **đường dẫn mà Spring WebFlux nhìn thấy**, không chỉ URL trên browser.

### 9.3. Authentication hợp lệ nhưng authority bị mất khi chuyển đổi

Với JWT, `Authentication` do reactive JWT converter tạo ra có thể chứa `SCOPE_reports.read`; nếu ứng dụng tự viết converter và trả về `Authentication` với danh sách rỗng, token vẫn có thể xác thực nhưng 403 ở authorization. Với session/basic, user details loader có thể trả role chưa có tiền tố hoặc đã map nhầm.

Bảng đối chiếu nguyên nhân:

| Chỗ kiểm tra | Kết quả quan sát | Việc cần sửa |
| --- | --- | --- |
| JWT claims `scope=reports.read` | `getAuthorities=[]` | Kiểm tra converter/claim name/decoder, không bỏ validation |
| JWT authorities `SCOPE_reports.read` | Rule `hasRole("REPORTS_READ")` | Thống nhất dùng scope authorization hoặc mapping role được chấp thuận |
| UserDetails authorities `VIEWER` | Rule `hasRole("VIEWER")` | Chỉnh mapper thành `ROLE_VIEWER` hoặc rule exact authority đúng thiết kế |
| Method `@PreAuthorize` cần `SCOPE_edit` | Route chỉ cần `ROLE_EDITOR` | Xem chính sách hai tầng, không tự cấp thêm scope |
| POST đã có quyền nhưng thiếu CSRF | `CsrfWebFilter` từ chối | Sửa token/session/header hoặc thiết kế CSRF đúng |
| Browser lỗi CORS trước POST | Actual request không đến controller | Sửa CORS/origin/credentials, không sửa role mù quáng |

## 10. Cách phát hiện có phải CSRF hay không bằng test và log

Một cách thực dụng để loại bỏ sự nhập nhằng là **thử cùng user và cùng endpoint, chỉ thay CSRF**:

```text
Authenticated = ROLE_EDITOR, request POST /reports/demo
  A. Không có CSRF -> 403 (expected)
  B. Có CSRF hợp lệ cùng phiên -> 200 (expected)

Authenticated = ROLE_VIEWER, request POST /reports/demo
  C. Có CSRF hợp lệ -> 403 (expected)

Authenticated = ROLE_VIEWER, request GET /reports/demo
  D. CSRF không cần cho GET -> 200 (expected)
```

Trong test `WebTestClient`, `mutateWith(csrf())` là cách tạo một request có CSRF token hợp lệ cho môi trường test. Nếu B vẫn 403, kiểm tra role, URL/method, custom matcher, method security và controller. Nếu A lại 200, cần xem CSRF đã bị vô hiệu hóa ở chain hay matcher đã exclude endpoint hay chưa. Nếu C lại 200, có khả năng rule POST đang quá rộng/không áp dụng.

Với ứng dụng browser thật, kiểm tra:

1. Request lấy CSRF token được thực thi khi có session thích hợp và token đã được materialize, không chỉ tạo một `Mono<CsrfToken>` mà chưa subscribe.
2. Client gửi **tên header đúng theo repository** và token ở dạng mà request handler chấp nhận.
3. Cookie session và token thuộc cùng user/session và được gửi đúng domain/path/SameSite/Secure.
4. Sau login/logout/session renewal, client đã lấy CSRF token mới khi token cũ không còn hợp lệ.
5. Cookie CSRF đọc được bởi JavaScript chỉ khi thiết kế cho phép; không mở HttpOnly của session cookie, không nhầm token CSRF với JWT.
6. CORS preflight được xử lý đúng nếu SPA khác origin. `OPTIONS` bị chặn không nhất thiết là CSRF trên request `POST`.
7. Không log full cookie/CSRF token để “so sánh” — dùng thông tin trạng thái/phiên bản và kết quả xác minh thay cho giá trị bí mật.

## 11. Mẫu khắc phục đúng nguyên nhân

### Trường hợp A — tài khoản đã xác thực nhưng thiếu ROLE_

**Triệu chứng:** `GET /reports/demo` trả 403; diagnostics cho thấy `authorities=[VIEWER]`, cấu hình dùng `hasRole("VIEWER")`.

**Nguyên nhân:** rule chờ `ROLE_VIEWER` nhưng mapper cấp `VIEWER`.

**Khắc phục:** quyết định chuẩn dữ liệu là role với `ROLE_` hay authority literal; sửa đúng nơi map (từ user store/IdP), hoặc dùng `hasAuthority("VIEWER")` nếu ứng dụng chủ ý dùng authority literal. Bổ sung test GET user có/không có đúng tên authority, test các role khác không được cấp nhầm.

### Trường hợp B — scope JWT được kiểm tra như role

**Triệu chứng:** JWT hợp lệ có `scope=reports.read`, authorities thực tế có `SCOPE_reports.read`, rule lại dùng `hasRole("REPORTS_READ")`.

**Nguyên nhân:** quy ước OAuth scope và Spring Security role bị trộn.

**Khắc phục:** dùng `hasAuthority("SCOPE_reports.read")` hoặc manager `hasScope("reports.read")` ở WebFlux theo phiên bản tương ứng. Nếu thực sự cần business role, mapping từ claim role đáng tin và được kiểm tra bởi issuer theo policy, **không** biến mọi scope thành admin.

### Trường hợp C — POST có đủ role nhưng thiếu CSRF

**Triệu chứng:** GET thành công; POST chỉ 403 khi chạy từ SPA/browser hoặc công cụ không gửi CSRF token.

**Nguyên nhân:** unsafe HTTP method, thiếu/không khớp token với session, hoặc client dùng header/repository/handler sai.

**Khắc phục:** phát hành token bằng server, đưa qua form/header phù hợp, giữ phiên/cookie, điều chỉnh tích hợp SPA theo Spring Security 6 hiện dùng, kiểm tra lại bằng `WebTestClient.mutateWith(csrf())` và integration browser. Không dùng `permitAll` hay tắt CSRF toàn cục.

### Trường hợp D — 403 vẫn tồn tại sau khi đã sửa role và CSRF

**Triệu chứng:** test quyền/CSRF riêng lẻ đều đúng nhưng request thực vẫn 403.

**Nguyên nhân có thể:** method security `@PreAuthorize`, controller/ACL nghiệp vụ, đường dẫn bị rewrite, multiple filter chains, custom access denied handler, gateway/WAF hoặc CORS preflight.

**Khắc phục:** xác định tầng trả status theo request ID/log, tái hiện qua từng tầng, so sánh đường dẫn/method/principal/authority tại đúng vị trí. Không mở quyền để “thử cho nhanh”; có thể vô tình tạo lỗ hổng còn nghiêm trọng hơn 403.

## 12. Những lỗi cần tránh khi gỡ 403

| Cách làm sai | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| `anyExchange().permitAll()` để xác nhận request chạy được | Có thể cho qua authorization thực | Test bằng `mockUser` và scope cụ thể, giữ deny-by-default |
| Chuyển mọi `hasRole` sang `authenticated()` | Xóa yêu cầu quyền nghiệp vụ | Chuẩn hóa authorities và sửa rule có chủ đích |
| Cấp thêm `ROLE_ADMIN` cho user đang lỗi | Vi phạm least privilege | Xác định thiếu role nào thật sự được phép |
| Đổi `hasRole("ADMIN")` thành `hasRole("ROLE_ADMIN")` | Dùng API không đúng hợp đồng | `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |
| Tin claim chưa xác minh trong JWT | Attacker tự ghi role/scope trong payload | Xác minh signature, issuer, audience và thời gian |
| Tắt CSRF cho ứng dụng browser dùng session | Mở CSRF attack surface | Phát token và gửi đúng header/form, cùng session |
| Chỉ bật CORS, không gửi token CSRF | CORS không chứng minh người dùng chủ động thao tác | Giải quyết CORS và CSRF theo hai cơ chế riêng |
| Copy cấu hình servlet `HttpSecurity` sang WebFlux | Rule không nằm trong reactive chain phù hợp | Dùng `ServerHttpSecurity`, `SecurityWebFilterChain` |
| Đọc `SecurityContextHolder` trong async callback | Nhầm ThreadLocal với reactive context | Dùng `ReactiveSecurityContextHolder` trong subscription |
| Ghi log raw JWT/cookie/CSRF khi DEBUG | Lộ thông tin xác thực | Chỉ log tín hiệu an toàn và loại nguyên nhân |
| Chỉ test happy path 200 | Không biết role/CSRF có đang được thực thi không | Có test âm tính 403 cho cả thiếu quyền và thiếu CSRF |
| Coi mọi 403 là do Spring | Bỏ sót gateway/WAF/ACL | Xác nhận tầng sinh response bằng request ID |

## 13. Checklist kiểm chứng và kiến thức ghi nhớ

Khi gặp một `403` mới, hãy xử lý theo thứ tự:

1. **Xác định nguồn 403:** ứng dụng, gateway, WAF, method security hay logic nghiệp vụ; ghi method/path/correlation ID và check redirect/OPTIONS.
2. **Xác nhận authentication:** request dùng session, Basic hay bearer JWT; không đánh đồng `401` với `403`.
3. **Đối chiếu chính xác authority:** `getAuthorities()` có `ROLE_*`, `SCOPE_*` hay chuỗi khác; rule `hasRole`/`hasAuthority`/`@PreAuthorize` cần gì?
4. **Kiểm tra method và matcher:** GET/POST khác nhau, đường dẫn match rule nào, có nhiều chain không, `denyAll` có chặn ngoài dự kiến không?
5. **Nếu unsafe method:** kiểm tra CSRF token hợp lệ với **cùng phiên**, form/header name, cookie, XOR handler trong Spring Security 6 và vòng đời login/logout.
6. **Chạy test cô lập:** mock user đúng/sai quyền; cùng POST có/không có `csrf()`; test positive lẫn negative.
7. **Sửa đúng lớp gây lỗi:** converter, user store, route policy, CSRF integration, method security hoặc upstream. Không nới quyền ngoài yêu cầu.
8. **Đánh giá hồi quy:** kiểm tra endpoint công khai, 401/redirect, 403 cho user không đủ quyền, 200 cho user đủ quyền, CSRF với browser session, JWT scopes và request đồng thời.

Điều quan trọng nhất: **một 403 là kết quả của một phép kiểm tra cụ thể**. Muốn sửa, phải biết chính xác phép kiểm tra nào đã thất bại. `ROLE_`, `SCOPE_`, CSRF và policy ở nhiều tầng là các cơ chế khác nhau; sửa đúng cơ chế mới bảo đảm vừa truy cập hợp lệ, vừa không làm rộng quyền.

## Tài liệu chính thức

- Spring Security — Authorize ServerHttpRequest (WebFlux): https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — CSRF cho WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — Testing WebTestClient authentication: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Security — Testing CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security — WebTestClient setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Security — Testing OAuth2/JWT: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
