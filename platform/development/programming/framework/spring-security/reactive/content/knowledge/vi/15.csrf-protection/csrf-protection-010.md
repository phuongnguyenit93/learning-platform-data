# Xử lý token CSRF thiếu, sai hoặc hết hạn và phản hồi lỗi phù hợp

> **Bối cảnh:** Spring Security **Reactive/WebFlux**, Spring Framework 6.x, Java 17+; ví dụ Spring Boot 3.3.x và Spring Security 6.3.x để học API. Trọng tâm là phát hiện yêu cầu ghi thiếu token CSRF, token không khớp hoặc token đã trở nên vô hiệu sau khi session hết hạn/đăng xuất; trả lỗi dễ hiểu nhưng **không làm suy yếu bảo vệ CSRF**. Trước khi triển khai production, chọn bản Spring còn được hỗ trợ và cập nhật bản vá bảo mật.

## 1. CSRF là gì và vì sao lại thấy HTTP 403?

**Cross-Site Request Forgery (CSRF)** là tình huống trình duyệt của người dùng tự mang theo credential sẵn có (ví dụ session cookie) đến một server mà nạn nhân đã đăng nhập, trong khi một trang khác cố kích hoạt thao tác thay người dùng. Để chống kiểu tấn công này, ứng dụng yêu cầu một **CSRF token** khó đoán, do ứng dụng cung cấp, phải được trình duyệt đưa vào request thay đổi trạng thái ở vị trí **không tự động được browser gửi như cookie**.

```text
Browser đã có cookie phiên                       WebFlux server
  |
  | GET /api/csrf  ------------------------------> CsrfWebFilter
  |                          tải/tạo CSRF token dự kiến trong WebSession
  | <--------------------------------------------- {headerName, token}
  |                                                Set-Cookie: SESSION=...
  |
  | POST /api/actions
  | Cookie: SESSION=...
  | X-CSRF-TOKEN: <token đã nhận>  --------------> đối chiếu token thực tế
  |                             +-- khớp -------> authorization -> controller
  |                             +-- thiếu/sai --> 403; KHÔNG xử lý thao tác
```

**Cookie phiên** và **CSRF token** là hai dữ kiện khác nhau:

- Cookie `SESSION` (WebFlux mặc định, có thể cấu hình đổi) thường chứa **session ID** để server tìm dữ liệu phiên. Browser tự gắn cookie khi quy tắc Domain/Path/SameSite cho phép.
- Token CSRF được trả từ server qua form hoặc một response được script cùng nguồn tin cậy đọc; phía client gửi lại qua header `X-CSRF-TOKEN` hoặc trường form `_csrf` khi cần.
- Token CSRF **không phải** access token, JWT, API key, mật khẩu hay bằng chứng người dùng đã đăng nhập. Có thể cấp token cho khách chưa login để bảo vệ form đăng nhập và request trước khi login.
- Với `WebSessionServerCsrfTokenRepository` mặc định, expected token gắn với server-side `WebSession`. Không có gì bảo đảm cùng một token vẫn hợp lệ sau khi session mất hoặc thay đổi.

### Nguyên tắc HTTP an toàn

CSRF protection mặc định của Spring Security chủ yếu áp dụng cho **unsafe methods** như `POST`, `PUT`, `PATCH`, `DELETE`. Các method `GET`, `HEAD`, `OPTIONS`, `TRACE` phải được ứng dụng giữ **read-only** đúng nghĩa. Nếu một `GET /delete-account` xóa dữ liệu, việc nó được xem là safe method sẽ phá tiền đề bảo vệ.

**CORS không thay thế CSRF.** Browser có thể *gửi* request cross-site kể cả khi CORS chặn JavaScript *đọc* response. `SameSite` là lớp phòng vệ hữu ích nhưng không thay việc xác định threat model và token chống CSRF.

## 2. Ba trường hợp cần xử lý

| Tình huống | Hiện tượng | Nguyên nhân điển hình | Kết quả an toàn |
|---|---|---|---|
| **Thiếu token** | POST có session cookie nhưng không có `X-CSRF-TOKEN`/`_csrf` | Form quên hidden input, frontend chưa bootstrap token, fetch không set header | **403**; không chạy thao tác ghi |
| **Token sai** | Có header/token nhưng không khớp expected token | Lấy token từ tab/session khác; giá trị hỏng, bị sửa, sai cách giải mã XOR | **403**; không chạy thao tác ghi |
| **Token cũ/“hết hạn”** | Token từng hợp lệ, sau đó không còn xác nhận được | `WebSession` hết hạn/bị invalidate, logout/login đổi state, refresh/redeploy store, chiến lược rotation của ứng dụng | **403** khi CSRF không hợp lệ; không tự replay request |

Từ **“hết hạn” cần hiểu chính xác**: với mặc định lưu token trong `WebSession`, không có một hạn sử dụng độc lập được đảm bảo cho từng token chỉ vì nó là CSRF token. Trên thực tế, session không còn hoặc expected token thay đổi sẽ khiến token cũ không khớp. Nếu ứng dụng tự viết repository có TTL riêng, mới có thể nói về hạn sử dụng của token theo thiết kế đó.

### Có phân biệt được ba lý do chỉ từ exception không?

Trong Spring Security **Servlet**, tài liệu có `org.springframework.security.web.csrf.MissingCsrfTokenException` và `InvalidCsrfTokenException`. **Đừng nhầm chúng với WebFlux.** Ở nhánh reactive có `org.springframework.security.web.server.csrf.CsrfException`; đây là subtype của `AccessDeniedException` và dùng cho trường hợp token thiếu hoặc sai. API mặc định **không hứa** một mã lỗi public khác nhau cho “header mất”, “header sai” và “session đã hết hạn”.

Một token cũ sau session expiration có thể biểu hiện giống token sai. Nếu ứng dụng cần metrics nội bộ chi tiết, hãy thiết kế quan sát an toàn dựa trên state được kiểm soát và chính sách riêng; **đừng parse chuỗi exception message để kết luận chính xác đã hết hạn**, và đừng để client tự khai “token expired” qua header.

**Chính sách đề xuất:** phản hồi HTTP **403** với mã JSON thống nhất `csrf_rejected` cho ba trường hợp. Không trả raw expected/actual token, session ID, exception stack trace hoặc thuật toán sinh token.

## 3. Luồng CsrfWebFilter trong Spring WebFlux

Spring Security WebFlux triển khai CSRF qua:

- `org.springframework.security.web.server.csrf.CsrfWebFilter`: WebFilter thực thi kiểm tra.
- `ServerCsrfTokenRepository`: lưu/đọc expected token.
- `WebSessionServerCsrfTokenRepository`: implementation **mặc định**, lưu token trong `WebSession`.
- `CookieServerCsrfTokenRepository`: lựa chọn khi frontend JavaScript cần đọc token trong cookie `XSRF-TOKEN`.
- `ServerCsrfTokenRequestHandler`: cách đưa token vào request attribute và xử lý token do client gửi.
- `XorServerCsrfTokenRequestAttributeHandler`: handler mặc định từ Spring Security **6.0**, che/mask token để chống rò rỉ BREACH khi phản hồi có nén.
- `ServerAccessDeniedHandler`: handler nhận lỗi CSRF do filter từ chối.

Sơ đồ:

```text
Request đi vào SecurityWebFilterChain
          |
          v
      CsrfWebFilter
          |
          +--> cung cấp Mono<CsrfToken> tại exchange attribute
          |         (token có thể tải/tạo deferred)
          |
          +--> method có cần bảo vệ CSRF?
          |        |
          |        +-- không (GET, HEAD, OPTIONS, TRACE mặc định)
          |        |         -> tiếp tục các filter/handler
          |        |
          |        +-- có (POST/PUT/PATCH/DELETE)
          |                  |
          |                  +-- repository cung cấp expected token
          |                  +-- request handler đọc token thực tế
          |                  +-- đối chiếu theo cơ chế tương ứng
          |                          |
          |                          +-- valid -> tiếp tục
          |                          +-- invalid/missing
          |                                 -> CsrfException
          |                                 -> CSRF-specific accessDeniedHandler
          |                                 -> HTTP 403
          |
          v
    Authorization / controller (chỉ khi request được qua filter)
```

**Không đồng nhất 403 do CSRF với 403 do thiếu role.** Cùng mã HTTP, nhưng có thể cần mã JSON khác (`csrf_rejected` so với `access_denied`). Một request thiếu CSRF token có thể bị chặn ngay cả khi URL được khai báo `permitAll()` hoặc người gọi có `ROLE_ADMIN`. Lỗi 401 (chưa đăng nhập) và 403 (CSRF) cũng có thể xuất hiện khác nhau tùy thứ tự filter/điều kiện request; **đừng ép mọi lỗi CSRF về 401 hoặc redirect login**.

### Điểm dễ sai: handler của CSRF khác handler phân quyền chung

Trong WebFlux, có hai chỗ cấu hình access denied:

```java
// MẢNH CẤU HÌNH, chưa có class/imports đầy đủ
http
    .csrf(csrf -> csrf
        .accessDeniedHandler(csrfDeniedHandler))
    .exceptionHandling(errors -> errors
        .accessDeniedHandler(generalDeniedHandler));
```

`csrf.accessDeniedHandler(...)` xử lý phản hồi khi `CsrfWebFilter` phát hiện token không hợp lệ. `exceptionHandling(...accessDeniedHandler(...))` xử lý nhiều trường hợp bị từ chối quyền ở luồng authorization. **Chỉ cấu hình exceptionHandling chưa bảo đảm bạn định dạng được mọi lỗi CSRF**, vì filter CSRF có handler riêng. Ví dụ chạy được ở phần 7 khai báo cả hai để contract API rõ ràng.

## 4. Chọn response: 403, JSON hay trang HTML?

### API JSON

Một hợp đồng đơn giản, dễ dùng với SPA/mobile là `application/problem+json` theo RFC 9457:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "CSRF validation failed",
  "code": "csrf_rejected"
}
```

`code` là extension member do ứng dụng tự định nghĩa. `type: about:blank` và `title: Forbidden` tương thích ý nghĩa HTTP 403. Frontend có thể dựa vào `code` để hướng dẫn người dùng tải lại form hoặc làm mới CSRF token **qua một GET an toàn**, không phải đoán dựa vào HTML lỗi.

Tại sao **không** trả `419 Page Expired` hay `440 Login Timeout` như mặc định? Đó là các mã không thuộc bộ HTTP status chuẩn chung; một framework khác có thể dùng cho convention riêng, nhưng Spring Security WebFlux mặc định dùng **403 Forbidden** khi CSRF thất bại. Nếu một tổ chức chọn mã tùy chỉnh, phải có hợp đồng client/proxy/monitoring rõ; đừng gán mọi 403 thành “hết hạn”.

### Trang web HTML

Đối với form server-rendered, có thể hiển thị trang thông báo **403**: “Phiên làm việc hoặc mã bảo vệ biểu mẫu không còn hợp lệ. Hãy mở lại biểu mẫu rồi gửi lại”. Có thể cung cấp một link `GET /form` để nhận token mới. Không nên tự động redirect một **POST** lỗi CSRF sang login rồi replay dữ liệu ghi: client có thể hiểu nhầm thao tác đã hoàn tất, và làm tăng rủi ro duplicate submission.

Nếu quyết định redirect sang một trang trợ giúp bằng GET, vẫn phải giữ trạng thái thao tác lỗi rõ ràng; không biến lỗi xác thực/CSRF thành 200 thành công. Với API, JSON 403 đơn giản và nhất quán hơn redirect HTML.

### Ưu tiên dữ liệu hữu ích, không tiết lộ internals

Tránh body:

```json
{
  "error": "Expected token 3cb... but got header a71...",
  "sessionId": "secret-session-id"
}
```

Response này vô tình làm lộ chính cơ chế bảo vệ. Để debug, chỉ log metadata không nhạy cảm: timestamp, route template, HTTP method, mã `csrf_rejected`, correlation ID, môi trường và trạng thái hệ thống (không raw cookie/token/header, query secret).

## 5. Khi nào token có thể trở nên không hợp lệ?

### 5.1 WebSession hết hạn

`WebSessionServerCsrfTokenRepository` dùng session phía server. Trình duyệt có thể vẫn giữ `SESSION` cookie nhưng server đã xóa/expire session (idle timeout, restart khi dùng in-memory store, invalidate chủ động). Header CSRF còn trong tab cũ không khớp token mới được server tải/tạo cho session hiện tại.

**Quy trình xử lý:** giữ thao tác POST bị từ chối, điều hướng người dùng đến một **GET an toàn** để tải biểu mẫu/token mới; nếu session đăng nhập đã mất, yêu cầu đăng nhập lại qua cơ chế hợp lệ. Không coi việc có cookie `SESSION` là bằng chứng còn authentication.

### 5.2 Logout, login, session ID và token rotation

Đăng xuất thường khiến `WebSession`/security state bị xóa; token gắn với session cũ có thể bị hủy theo. Khi đăng nhập hoặc nâng quyền, hệ thống có thể thay session ID hoặc làm mới token theo các handler được cấu hình. **Không khẳng định mỗi lần authentication luôn có cùng chuỗi hành vi trong mọi chain**, nhất là Basic/JWT/form login và custom repository khác nhau.

Nếu SPA giữ token cũ trong memory sau logout/login, request thay đổi trạng thái tiếp theo có thể bị 403. Nên bootstrap lại token sau quá trình chuyển trạng thái xác thực và đảm bảo cookie phiên mới được lưu đúng trước khi gửi thao tác khác.

### 5.3 Nhiều tab trình duyệt và race condition

- Một tab mở form trước khi session hết hạn; người dùng quay lại sau nhiều phút, token cũ có thể đã mất hiệu lực.
- Một tab đăng xuất hoặc thay session, tab còn lại giữ token cũ.
- Hai request chạy cùng lúc có thể gặp session rotation/invalidating race; kết quả cần kiểm thử.
- SPA gửi nhiều request đồng thời và tự động refresh token sau 403 có thể tạo “retry storm” hoặc duplicate transaction nếu code không đồng bộ đúng.

Đừng đặt quy trình “403 nào cũng refresh và gửi lại tự động”. Một 403 có thể do **thiếu quyền truy cập**, không liên quan CSRF. Ngay cả với `csrf_rejected`, thao tác tài chính/ghi dữ liệu không nên được replay mù quáng. Dùng idempotency key và xác nhận người dùng khi nghiệp vụ cần.

### 5.4 Đổi kho lưu CSRF token

Với `CookieServerCsrfTokenRepository`, cookie `XSRF-TOKEN` và header `X-XSRF-TOKEN` là tên mặc định thường gặp. Khi JavaScript cần đọc cookie, `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` là lựa chọn được tài liệu mô tả, nhưng làm token có thể bị JavaScript đọc (trade-off khi có XSS). **Đừng đổi sang cookie repository chỉ để “chữa CSRF 403”** khi chưa đánh giá SameSite, origin, BREACH masking và client request handler.

**Cảnh báo Spring Security 6+:** Xor request handler được bật mặc định. Token raw mà JavaScript đọc từ cookie có thể **không được giải mã đúng** nếu gửi thẳng qua header trong một cấu hình không tương thích với cách XOR handler nhận token. Phải dùng chiến lược SPA/request handler phù hợp, kiểm thử với đúng version. Demo phía dưới giữ **WebSession repository + XOR mặc định**, không cần bỏ lớp bảo vệ BREACH.

## 6. Phân biệt CSRF failure với xác thực và phân quyền

| Tình huống request | HTTP status thường mong đợi | Cách xử lý |
|---|---|---|
| `GET /api/csrf` không đăng nhập | 200 nếu endpoint public | Trả token để client chuẩn bị form/API; không có nghĩa user đã login |
| `GET /api/private` không credential | 401 | Yêu cầu xác thực đúng giao thức |
| `POST /api/actions` có Basic hợp lệ nhưng không gửi CSRF | 403 + `csrf_rejected` | Không xử lý hành động, lấy token mới bằng GET |
| `POST /api/actions` có Basic hợp lệ và token sai | 403 + `csrf_rejected` | Không đoán/tiết lộ expected token |
| `POST /api/actions` có Basic hợp lệ và token session đã bị hủy | 403 + `csrf_rejected` | Bootstrap lại session/token, có thể phải login lại |
| `POST /api/actions` có token hợp lệ nhưng không login | 401 | CSRF token không biến thành credential |
| `POST /api/admin` có token hợp lệ, user thiếu ADMIN | 403 + `access_denied` | Không coi là CSRF hết hạn |
| Request GET không có CSRF token | Không bị CSRF chặn chỉ vì thiếu token | Vẫn chịu authentication/authorization |
| POST có lỗi validation sau khi đã qua CSRF | 400 nếu business/validation trả 400 | Không báo nhầm lỗi CSRF |

Status trên là **quy ước của cấu hình demo**, không phải một mệnh đề về mọi thứ tự filter trong mọi ứng dụng. Với một request **đồng thời thiếu authentication và CSRF**, CSRF có thể từ chối trước và người gọi nhìn thấy **403**, không phải 401. Do đó test riêng từng điều kiện, đặc biệt khi debug báo cáo từ client.

### Không “điều trị” một lỗi bảo mật bằng cách bỏ bảo mật

Ba cách sửa sai thường gặp:

```java
// Không làm trong web app dùng cookie session để "sửa" 403:
csrf.disable();

// Không biến mọi route thành public:
.anyExchange().permitAll();

// Không cho POST thiếu token tiếp tục xử lý khi gặp lỗi:
// pseudo-code nguy hiểm: catch (CsrfException) { continueChain(); }
```

Đây là **mã/phát biểu phản ví dụ**, không phải cấu hình chạy độc lập. Hãy tìm nguyên nhân: token chưa được phát, JavaScript quên header, session expired, mask không tương thích, cookie không được gửi, reverse proxy sai domain/path hoặc flow đăng nhập/logout cần re-bootstrap.

## 7. Demo Spring Boot WebFlux đầy đủ: lỗi 403 JSON và token cũ

Ví dụ này dùng **HTTP Basic + WebSession-based CSRF** để có thể kiểm tra độc lập: HTTP Basic xác minh danh tính, còn cookie phiên phục vụ expected CSRF token. Basic không làm token CSRF trở thành password. Một endpoint GET công khai cấp token, hai POST cần login + token; một POST hủy session để mô phỏng **token cũ không còn hợp lệ** sau khi phiên bị hủy.

**Chỉ chạy credential ví dụ trên localhost/HTTPS**. Mật khẩu trong mã là dữ liệu học tập. Dự án production dùng bản framework đã vá, HTTPS, quản lý tài khoản và session phù hợp.

### 7.1 Cấu trúc

```text
webflux-csrf-errors/
  settings.gradle
  build.gradle
  src/main/java/example/csrf/CsrfApplication.java
  src/main/java/example/csrf/SecurityConfiguration.java
  src/main/java/example/csrf/ApiController.java
  src/test/java/example/csrf/CsrfFlowTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-csrf-errors'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.csrf'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không thêm `spring-boot-starter-web` của Servlet. Bài dùng `ServerHttpSecurity`/`SecurityWebFilterChain` và `CsrfWebFilter` của WebFlux.

### 7.2 Application

**src/main/java/example/csrf/CsrfApplication.java**

```java
package example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfApplication.class, args);
    }
}
```

### 7.3 SecurityConfiguration: CSRF handler và authentication handler

**src/main/java/example/csrf/SecurityConfiguration.java**

```java
package example.csrf;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("dev-alice-only"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        ServerAuthenticationEntryPoint authEntry = (exchange, failure) ->
            problem(exchange, HttpStatus.UNAUTHORIZED, "authentication_required");

        ServerAccessDeniedHandler csrfDenied = (exchange, failure) ->
            problem(exchange, HttpStatus.FORBIDDEN, "csrf_rejected");

        ServerAccessDeniedHandler permissionDenied = (exchange, failure) ->
            problem(exchange, HttpStatus.FORBIDDEN, "access_denied");

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/api/csrf", "/api/status").permitAll()
                .pathMatchers(HttpMethod.POST,
                    "/api/actions", "/api/session/invalidate")
                    .authenticated()
                .anyExchange().denyAll())
            .httpBasic(basic ->
                basic.authenticationEntryPoint(authEntry))
            .formLogin(form -> form.disable())
            .csrf(csrf -> csrf
                // Mặc định WebFlux đã dùng repository kiểu này;
                // khai báo rõ để người học thấy nơi lưu expected token.
                .csrfTokenRepository(
                    new WebSessionServerCsrfTokenRepository())
                .accessDeniedHandler(csrfDenied))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(authEntry)
                .accessDeniedHandler(permissionDenied))
            .build();
    }

    private static Mono<Void> problem(ServerWebExchange exchange,
                                      HttpStatus status,
                                      String code) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(
            MediaType.APPLICATION_PROBLEM_JSON);
        response.getHeaders().set(HttpHeaders.CACHE_CONTROL, "no-store");

        if (status == HttpStatus.UNAUTHORIZED) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"training\"");
        }

        // Chỉ các mã cố định phía server được chấp nhận.
        // Không xuất exception message, session ID hoặc token.
        String json = switch (code) {
            case "authentication_required" -> """
                {"type":"about:blank","title":"Unauthorized",
                 "status":401,"detail":"Authentication required",
                 "code":"authentication_required"}
                """;
            case "csrf_rejected" -> """
                {"type":"about:blank","title":"Forbidden",
                 "status":403,"detail":"CSRF validation failed",
                 "code":"csrf_rejected"}
                """;
            default -> """
                {"type":"about:blank","title":"Forbidden",
                 "status":403,"detail":"Access denied",
                 "code":"access_denied"}
                """;
        };

        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        return response.writeWith(Mono.just(
            response.bufferFactory().wrap(bytes)));
    }
}
```

**Giải thích theo điểm kỹ thuật:**

1. `@EnableWebFluxSecurity` + `SecurityWebFilterChain` là cấu hình **reactive**, không dùng `HttpSecurity` của Servlet.
2. `GET /api/csrf` và `GET /api/status` là public; token CSRF có thể được cấp cho khách. `POST /api/actions` và `POST /api/session/invalidate` yêu cầu authentication thật.
3. `httpBasic(...authenticationEntryPoint(...))` giúp lỗi Basic credential không hợp lệ trả JSON 401 nhất quán, thay vì một phản hồi mặc định khác.
4. `csrf.csrfTokenRepository(new WebSessionServerCsrfTokenRepository())` lưu expected token trong `WebSession`. Đây là cấu hình minh họa **giá trị mặc định**, không bắt buộc viết lại trong production.
5. `csrf.accessDeniedHandler(csrfDenied)` đảm bảo **các lỗi do CsrfWebFilter từ chối** trả đúng status 403, `application/problem+json` và mã `csrf_rejected`.
6. `exceptionHandling(...accessDeniedHandler(permissionDenied))` cho các lỗi phân quyền chung trả mã **`access_denied`**, không lẫn với CSRF.
7. `exceptionHandling(...authenticationEntryPoint(authEntry))` cho các request cần login nhận **401**, kèm Basic challenge. Token CSRF không giúp bypass cơ chế login.
8. **Không tắt CSRF**, không dùng `permitAll` cho POST nhạy cảm, không fallback error sang hành động thành công.
9. JSON được xây từ các literal cố định; không nối raw exception, user input hay token vào body, tránh leak.
10. Demo cố ý **giữ request handler XOR mặc định** của Spring Security 6.x. Nó cung cấp token thích hợp cho GET `/api/csrf` và phân giải giá trị do client trả lại. Không dùng `ServerCsrfTokenRequestAttributeHandler` để tắt BREACH chỉ cho dễ viết demo.

### 7.4 Controller: cấp token, ghi dữ liệu giả lập, hủy session

**src/main/java/example/csrf/ApiController.java**

```java
package example.csrf;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import org.springframework.security.web.server.csrf.CsrfToken;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    public record CsrfView(String headerName, String token) {}
    public record Command(String action) {}
    public record ActionView(String status, int accepted) {}
    public record CounterView(int accepted) {}
    public record Ack(String status) {}

    private final AtomicInteger accepted = new AtomicInteger();

    @GetMapping("/api/csrf")
    public Mono<CsrfView> csrf(ServerWebExchange exchange) {
        // CsrfWebFilter cung cấp Mono<CsrfToken> tại request attribute.
        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                "CSRF filter is not configured for this request"));
        }

        // Subscribe nguồn token: repository có thể cần sinh/lưu
        // expected token vào WebSession trước khi trả response.
        return token.map(value ->
            new CsrfView(value.getHeaderName(), value.getToken()));
    }

    @GetMapping("/api/status")
    public Mono<CounterView> status() {
        return Mono.just(new CounterView(accepted.get()));
    }

    @PostMapping("/api/actions")
    public Mono<ActionView> action(@RequestBody Command command) {
        if (command.action() == null || command.action().isBlank()) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "action must not be blank"));
        }

        // Đếm request đã thực sự qua bộ lọc CSRF/authorization.
        return Mono.fromSupplier(() ->
            new ActionView("accepted", accepted.incrementAndGet()));
    }

    @PostMapping("/api/session/invalidate")
    public Mono<Ack> invalidate(WebSession session) {
        // Hủy phiên -> expected token lưu trong phiên cũ mất hiệu lực.
        return session.invalidate()
            .thenReturn(new Ack("session-invalidated"));
    }
}
```

**Không đưa endpoint CSRF token này ra Internet mà không cân nhắc CORS và caching.** Đây là một endpoint bootstrap của ứng dụng cùng origin: trả token cho script đáng tin trên cùng website và tạo phiên khi token được tạo. Giới hạn origin, tắt cache, không trả token trong analytics/log, không bật CORS wildcard với credentials. Trong hệ thống có login, token không đại diện quyền login và phải được bảo vệ bằng same-origin/Origin policy thích hợp.

Lý do có `CounterView`: khi token thiếu/sai, controller `action()` **không nên được gọi**. Có thể đọc bộ đếm trước/sau request bị từ chối để chứng minh không có tác động nghiệp vụ; đây chỉ là counter demo, không phải database transaction.

### 7.5 Chạy ứng dụng và xem JSON lỗi

Từ thư mục dự án (JDK 17+, Gradle tương thích Spring Boot 3.3, kết nối Maven repository):

```bash
gradle bootRun
```

Nếu có Gradle Wrapper tương thích, dùng `./gradlew bootRun`; Windows sử dụng `gradlew.bat bootRun`.

Thử request **thiếu token**:

```bash
curl -i -X POST http://localhost:8080/api/actions \
  -H "Content-Type: application/json" \
  --data '{"action":"ping"}'
```

Kỳ vọng HTTP **403** với `code: csrf_rejected`. Request trên còn thiếu credential, nhưng trong cấu hình WebFlux có CSRF filter, lỗi token có thể được xử lý trước nhánh yêu cầu đăng nhập. **Không xem 403 này là user đã login**.

Để lấy token và cookie đúng một phiên, có thể dùng công cụ HTTP client hỗ trợ cookie jar (không chép nguyên token vào hướng dẫn hoặc logs). Luồng khái niệm:

```http
GET /api/csrf HTTP/1.1
Accept: application/json

HTTP/1.1 200 OK
Set-Cookie: SESSION=<opaque-session-id>; Path=/; HttpOnly; ...
Content-Type: application/json

{"headerName":"X-CSRF-TOKEN","token":"<masked-csrf-token>"}

POST /api/actions HTTP/1.1
Authorization: Basic <credentials>
Cookie: SESSION=<same-session-id>
Content-Type: application/json
X-CSRF-TOKEN: <masked-csrf-token>

{"action":"ping"}
```

Tất cả giá trị trong dấu `<...>` ở ví dụ HTTP là placeholder, **không phải credential**. Token trả từ GET được mask theo handler mặc định; client gửi nguyên giá trị đã nhận qua `headerName` tương ứng và giữ cookie session. **Đừng tự tạo token trong client bằng cách sinh UUID**, vì server phải có expected token tương ứng trong repository.

Mục 7.6 cung cấp test tự động thực sự đọc token từ GET và cookie từ response, không dùng token giả.

## 7.6. Kiểm thử tích hợp bằng WebTestClient (token và cookie thật)

Test dưới đây dùng `RANDOM_PORT` thay vì mock security principal để kiểm chứng flow HTTP end-to-end của chính ứng dụng: GET cấp token, POST có Basic/CSRF, POST sai token, hủy session và gửi lại token cũ. Không dùng `mutateWith(csrf())` cho các test cần chứng minh session/token thật, vì test mutator sẽ mô phỏng một token hợp lệ và không thay thế kịch bản session expired.

**src/test/java/example/csrf/CsrfFlowTest.java**

```java
package example.csrf;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CsrfFlowTest {

    @Autowired
    WebTestClient client;

    record SessionToken(String sessionId, String headerName,
                        String token) {}

    private SessionToken issueToken() {
        var result = client.get().uri("/api/csrf")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectBody(ApiController.CsrfView.class)
            .returnResult();

        var body = result.getResponseBody();
        assertNotNull(body);

        ResponseCookie session =
            result.getResponseCookies().getFirst("SESSION");
        assertNotNull(session);
        assertTrue(!session.getValue().isBlank());
        assertTrue(!body.token().isBlank());

        return new SessionToken(session.getValue(),
            body.headerName(), body.token());
    }

    @Test
    void safeGetDoesNotRequireCsrf() {
        client.get().uri("/api/status")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.accepted").exists();
    }

    @Test
    void missingTokenWithValidAuthenticationReturns403() {
        var issued = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_PROBLEM_JSON)
            .expectBody()
            .jsonPath("$.code").isEqualTo("csrf_rejected");
    }

    @Test
    void wrongTokenWithSameSessionReturns403() {
        var issued = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(issued.headerName(), "definitely-wrong");
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("csrf_rejected");
    }

    @Test
    void correctTokenAndCredentialCanPerformAction() {
        var issued = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(issued.headerName(), issued.token());
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("accepted");
    }

    @Test
    void csrfTokenDoesNotReplaceLoginCredential() {
        var issued = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", issued.sessionId())
            .header(issued.headerName(), issued.token())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody()
            .jsonPath("$.code")
            .isEqualTo("authentication_required");
    }

    @Test
    void tokenWithoutItsSessionIsRejected() {
        var issued = issueToken();

        // Token do server cấp nhưng thiếu cookie SESSION tương ứng.
        client.post().uri("/api/actions")
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(issued.headerName(), issued.token());
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("csrf_rejected");
    }

    @Test
    void oldTokenAfterInvalidateIsRejectedAndFreshTokenWorks() {
        var old = issueToken();

        // Request hợp lệ để chủ động hủy WebSession.
        client.post().uri("/api/session/invalidate")
            .cookie("SESSION", old.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(old.headerName(), old.token());
            })
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("session-invalidated");

        // Gửi lại cookie/CSRF token của session đã hủy -> 403.
        client.post().uri("/api/actions")
            .cookie("SESSION", old.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(old.headerName(), old.token());
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("csrf_rejected");

        // Bootstrap lại token/session qua GET an toàn.
        var fresh = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", fresh.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "dev-alice-only");
                h.set(fresh.headerName(), fresh.token());
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void badBasicCredentialWithValidCsrfIs401() {
        var issued = issueToken();

        client.post().uri("/api/actions")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> {
                h.setBasicAuth("alice", "wrong-password");
                h.set(issued.headerName(), issued.token());
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new ApiController.Command("ping"))
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody()
            .jsonPath("$.code")
            .isEqualTo("authentication_required");
    }
}
```

**8 phương thức test** được thiết kế để chứng minh:

1. GET an toàn không đòi CSRF token.
2. Có session và user hợp lệ nhưng **thiếu header** → 403 `csrf_rejected`.
3. Token gửi lên **sai giá trị** → 403 `csrf_rejected`.
4. Token + credential hợp lệ → 200 và action được chấp nhận.
5. Có token nhưng **không xác thực** → 401; CSRF không thay credential.
6. Token đúng nhưng không có **cookie session tương ứng** → 403.
7. Sau `WebSession.invalidate()`, token cũ không được sử dụng lại; GET cấp token mới rồi POST hợp lệ được phép.
8. Password Basic sai khi CSRF đúng → 401; khác với CSRF failure.

Chạy:

```bash
gradle test
```

Đây là kết quả **kỳ vọng theo thiết kế và API**, không phải khẳng định build đã được chạy trên môi trường hiện tại. Các lỗi do dependency/Gradle/Netty hoặc khác biệt cấu hình thực tế cần được kiểm tra trên log. Dự án dùng WebSession store mặc định trong cùng một process, không chứng minh trực tiếp timeout idle thật hay tương tác nhiều node.

### 7.7. Kiểm thử nhanh bằng csrf() mutator của Spring Security Test

Khi bạn chỉ muốn kiểm một route POST yêu cầu CSRF mà **không** cần xác minh cookie/token lifecycle thực, Spring Security Test có tiện ích:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

// MẢNH TEST dùng WebTestClient đã cấu hình Spring Security Test:
client.mutateWith(csrf())
    .post().uri("/api/actions")
    .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
    .bodyValue(new ApiController.Command("ping"))
    .exchange()
    .expectStatus().isOk();
```

Dòng import trên có thể viết một dòng cho tiện sao chép:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

Cần có dependency `spring-security-test` khi dùng `csrf()`, `WebTestClient` có integration test config phù hợp, và test mutator hoạt động chủ yếu với mock server. Không dùng một token **do test tự giả lập** để tuyên bố session expiry được xử lý đúng ở ứng dụng thật; với mục tiêu đó, hãy dùng test HTTP token+cookie thật ở mục 7.6. Đây chỉ là mảnh test bổ sung và cần import dependencies.

## 8. Frontend xử lý 403 như thế nào?

### Phân biệt theo mã lỗi

Client API có thể dùng JSON status và `code`:

```text
response.status == 401:
    -> authentication không hợp lệ/cần đăng nhập
    -> chuyển người dùng vào login flow

response.status == 403 && body.code == "csrf_rejected":
    -> request ghi bị từ chối
    -> thông báo thao tác CHƯA được thực hiện
    -> lấy token mới qua GET /api/csrf (cùng origin)
    -> yêu cầu người dùng gửi lại hoặc retry có kiểm soát

response.status == 403 && body.code == "access_denied":
    -> user không có quyền
    -> KHÔNG liên tục refresh CSRF token
```

### Pseudocode JavaScript phía client

```javascript
let csrf = null;

async function loadCsrf() {
  const response = await fetch("/api/csrf", {
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) throw new Error("Cannot fetch CSRF token");
  csrf = await response.json();
}

async function submitAction(action) {
  if (!csrf) await loadCsrf();

  const response = await fetch("/api/actions", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ action })
  });

  if (response.status === 403) {
    const problem = await response.json().catch(() => ({}));
    if (problem.code === "csrf_rejected") {
      csrf = null;
      // ĐỪNG tự gửi lại thao tác ghi ở đây.
      // Có thể gọi loadCsrf() để chuẩn bị lần submit kế tiếp,
      // nhưng phải cho người dùng biết thao tác vừa bị từ chối.
      throw new Error("Session/CSRF token invalid; retry manually");
    }
  }

  if (response.status === 401) {
    throw new Error("Sign-in required");
  }

  if (!response.ok) throw new Error("Action rejected");
  return response.json();
}
```

Code trên là **minh họa client**; trong dự án production phải xử lý accessibility/i18n, loading state, idempotency, network timeout và quản lý authentication thật. API demo dùng Basic nên trình duyệt có thể hiện prompt; một SPA thực tế có thể có cookie-based login/OIDC, khi đó chiến lược gửi credential/CSRF khác và cần điều chỉnh.

### Vì sao không auto-retry POST?

- Yêu cầu cũ có thể đã gửi đến backend trong một tình huống failure không xác định khác; không mặc định retry mọi loại lỗi bảo mật hoặc mạng.
- Người dùng có thể đã đăng xuất hoặc phiên hết hạn; phải xác minh trạng thái login mới.
- Các thao tác chuyển tiền/đặt hàng không được phát lại mù quáng. Nếu business có idempotency key và contract retry an toàn, mới xét retry có kiểm soát.
- Một 403 có thể là thiếu role hoặc vi phạm policy, không liên quan CSRF.
- Gửi lại cùng token cũ sau khi session mất sẽ chỉ lặp 403.

## 9. Phát sinh token mới đúng cách

### 9.1 Với form HTML server-side

Server có thể đưa `CsrfToken` vào hidden input, ví dụ (token giả minh họa):

```html
<form method="post" action="/account/update">
  <input type="hidden" name="_csrf" value="<token-from-server>">
  <input type="text" name="displayName">
  <button type="submit">Lưu</button>
</form>
```

`<token-from-server>` là placeholder. Với Spring Security WebFlux, token thường được cung cấp qua exchange attribute hoặc tích hợp Thymeleaf, không hardcode trong HTML. Sau khi session hết hạn, render lại biểu mẫu/GET mới để nhận token mới. **Không gửi token CSRF trong URL query** vì nó dễ lộ qua logs, browser history và referer.

### 9.2 Với JSON/AJAX

Dùng `GET /api/csrf` cùng origin, backend trả tên header và token; frontend dùng đúng tên header. Cơ chế default với XOR có thể làm **giá trị token xuất cho mỗi response khác nhau** dù expected raw token chưa thay; đừng so sánh chuỗi token được mask giữa hai GET để suy ra session đã thay.

### 9.3 Với CookieServerCsrfTokenRepository

`CookieServerCsrfTokenRepository` hỗ trợ các client JavaScript đọc cookie `XSRF-TOKEN` và gửi `X-XSRF-TOKEN`. Nhưng khi giữ handler XOR mặc định, cần cấu hình request handler phù hợp với cách JS gửi raw cookie token; tùy phiên bản cần phối hợp mask/unmask và bootstrap token sau login/logout. Không sao chép một đoạn code Servlet `CookieCsrfTokenRepository` để áp dụng cho WebFlux; tên interface/implementation khác.

### 9.4 Không phát token mới qua GET gây tác động nghiệp vụ

GET bootstrap token có thể bắt đầu WebSession (dữ liệu kỹ thuật cần thiết) nhưng **không được thực hiện giao dịch nghiệp vụ**. Vì GET thường là safe HTTP method, thiết kế CSRF bảo vệ dựa trên việc GET/HEAD/OPTIONS/TRACE không thay đổi state kinh doanh.

## 10. Vấn đề thực tế dễ bị bỏ qua

### 10.1 Token có mặt nhưng vẫn bị từ chối

Các nguyên nhân thường gặp:

- Header name sai: client gửi `X-XSRF-TOKEN` trong khi repo/response yêu cầu `X-CSRF-TOKEN`; hãy dùng `getHeaderName()` hoặc contract tương ứng.
- Header value sai: client lấy raw token từ cookie nhưng server trông đợi token XOR-masked theo request handler mặc định.
- Cookie `SESSION` không được gửi: khác domain, Path, SameSite, Secure, CORS credentials hoặc cookie hết hạn.
- Expected token trong WebSession đã đổi/bị xóa: logout, session invalidate/timeout, mất session store khi restart hoặc multi-node.
- Frontend giữ token từ phiên user trước trong memory/localStorage; không đồng bộ lại sau login/logout.
- Form gửi `Content-Type: application/json` nhưng token lại nằm trong query/form field không được request handler đọc theo cách dự kiến.
- Nhiều `SecurityWebFilterChain`: route đi vào chain có CSRF repository/request handler khác.
- Endpoint `/api/csrf` chưa thực sự subscribe `Mono<CsrfToken>` nên expected token chưa được sinh/lưu khi response hoàn tất.

Đừng “khắc phục” bằng cách đặt tất cả unsafe methods vào danh sách ignore CSRF. Hãy xác nhận request/response thực tế ở devtools với **token bị che giá trị** khi thu log hoặc chia sẻ ảnh chụp.

### 10.2 Session hết hạn có thể dẫn đến 401 hoặc 403

Một GET protected sau khi session hết hạn có thể nhận **401/redirect login** vì identity không còn. Trong khi POST cùng cookie cũ và CSRF token cũ có thể bị **403** bởi `CsrfWebFilter` trước khi authorization xác định authentication. Do đó client không thể suy từ **mỗi status 403** rằng session chắc chắn đã hết hạn. Cách an toàn là trả `csrf_rejected` cho kiểm tra CSRF thất bại, rồi re-bootstrap/reauth theo flow nếu cần.

### 10.3 Có phải token CSRF cần một thời gian hết hạn riêng?

Không nhất thiết. `WebSessionServerCsrfTokenRepository` gắn token với session; chính sách idle timeout của WebSession là một yếu tố chính. Nếu hệ thống yêu cầu rotation/TTL riêng, cần thực hiện trong repository hoặc session-management policy rõ ràng và kiểm thử đồng bộ multi-tab; không bịa thêm “token hết hạn sau 30 phút” khi framework không cam kết điều đó.

### 10.4 Có nên trả HTTP 200 kèm JSON lỗi?

**Không.** Trả 403 thực giúp client, proxy, metrics, APM và người dùng hiểu thao tác đã bị chặn. `{"success":false}` với 200 không cho biết đúng semantics và dễ bị client hiểu nhầm là thành công.

### 10.5 Có nên redirect POST lỗi CSRF về login?

Không nên mặc định. 302/303 có thể khiến browser tải trang login, nhưng xóa mất tín hiệu “thao tác thất bại” và có thể làm thất lạc form data; redirect không sửa token và cũng không bảo đảm session đã hết hạn. Trang HTML có thể trả 403 với link GET tải lại form, còn API nên trả 403 JSON.

### 10.6 Có nên in exception message để biết token sai?

Không. Một số thông báo lỗi có thể chứa thông tin chi tiết về token/header. Log `exception.getMessage()` nguyên văn mà không xem xét có thể đưa token vào log. Dùng structured metric code cố định, correlation ID, route template và status. Nếu cần chẩn đoán sâu trong môi trường kiểm soát, phải redact token và session ID triệt để.

### 10.7 Nhiều instance và session store

Nếu ứng dụng dùng `InMemoryWebSessionStore` trên nhiều pod không chung store, cookie có thể trỏ đến session chỉ pod A biết; request đến pod B có thể bị từ chối CSRF. Khi cần scale, đánh giá Spring Session Redis/reactive repository, cấu hình session TTL, serialization và consistency. Sticky session chỉ là một giải pháp tạm thời, không chữa mất phiên khi pod restart.

### 10.8 Basic, JWT và browser cookie

CSRF rủi ro nhất khi browser **tự gửi credential** đến site theo ngữ cảnh (cookie/session, một số dạng browser-managed authentication). Với API dùng bearer token chỉ được JavaScript gắn vào `Authorization` có chủ đích, CSRF threat model có thể khác. Chỉ cân nhắc loại trừ CSRF cho các chain thực sự stateless và không dùng cookie/credentials tự động, sau khi đánh giá toàn bộ API. Không tắt mặc định chỉ vì tên route có tiền tố `/api`.

## 11. Các giải pháp sửa lỗi theo triệu chứng

| Triệu chứng | Cần kiểm tra | Giải pháp |
|---|---|---|
| Mọi POST đều 403 ngay sau mở trang | Có GET/bootstrap token chưa? Client gửi đúng header/field chưa? | Render token trên form hoặc gọi GET cấp token rồi gửi header |
| POST đầu tiên OK, sau idle lâu bị 403 | `WebSession` timeout, cookie cũ, logout ở tab khác? | Không replay POST; thông báo tải lại form/token và đăng nhập lại nếu cần |
| Có XSRF-TOKEN cookie nhưng header vẫn bị 403 | Cookie repo + XOR request handler có khớp cách client gửi raw token không? | Đối chiếu Spring Security version và cấu hình SPA/request handler |
| POST 403 nhưng user vẫn đăng nhập và có đúng role | Có thể do CSRF thay vì role | Phân biệt mã `csrf_rejected` với `access_denied` qua handler, test |
| POST không token trả 200 | CSRF đã bị disable/ignore, sai security chain, dùng GET ghi dữ liệu? | Khôi phục CSRF filter và bảo đảm unsafe route thuộc chain bảo vệ |
| 403 khi gọi từ domain frontend khác | Cookie SameSite/Secure, CORS credentials, Origin và CSRF header | Cấu hình CORS + CSRF token đúng, không open wildcard |
| Token lấy từ /csrf rồi gửi vẫn 403 | Có gửi cùng session cookie không? Có mask token đúng không? | Giữ cùng cookie jar và sử dụng token server trả |
| Lỗi 403 sau logout rồi đăng nhập | Session/token chưa được bootstrap lại | Clear token cache client, GET cấp token mới |
| 403 trên request PUT/PATCH/DELETE | Các method này cũng là unsafe | Gửi token cho mọi unsafe method được policy yêu cầu |
| Không phân biệt user thiếu quyền và CSRF | Chỉ có một generic 403 từ mọi filter | Đặt `csrf.accessDeniedHandler` và `exceptionHandling.accessDeniedHandler` riêng |
| Test dùng `mutateWith(csrf())` PASS nhưng production lỗi | Test bypass phần trao đổi session-cookie thực | Viết integration test token+cookie thật như mục 7.6 |
| Lỗi ngẫu nhiên qua load balancer | WebSession store không chia sẻ hoặc timeout khác nhau | Dùng shared reactive session store, đồng bộ TTL và monitoring |

## 12. Checklist triển khai và kiểm thử bảo mật

1. Xác nhận dùng **WebFlux/reactive** (`CsrfWebFilter`, `ServerHttpSecurity`), không nhầm Servlet `CsrfFilter`/`HttpSecurity`.
2. Bật CSRF cho mọi request thay đổi trạng thái trong web app dùng browser-managed credential.
3. Đảm bảo GET/HEAD/OPTIONS/TRACE không thực hiện side-effect nghiệp vụ.
4. Quyết định repository: WebSession mặc định hay CookieServerCsrfTokenRepository theo SPA; cấu hình request handler tương thích XOR và phiên bản.
5. Nếu cấp token qua GET, **subscribe** `Mono<CsrfToken>` và trả cookie/session tương ứng; bảo vệ same-origin/CORS và no-store.
6. Đối với unsafe methods, gửi token trong header hoặc form parameter, **không chỉ trông đợi cookie tự gửi**.
7. Trả **403** với mã lỗi generic `csrf_rejected` cho token thiếu/sai/không còn hợp lệ; không tiết lộ token/session.
8. Giữ mã khác cho `401 authentication_required` và `403 access_denied` do role/business policy.
9. Không tự replay POST/PUT/DELETE khi thấy lỗi CSRF; hướng dẫn lấy token mới và gửi lại có chủ đích.
10. Kiểm tra idle timeout, logout/login, session ID rotation, nhiều tab, refresh và multi-node session store.
11. Chạy test token thật với cookie thật; thêm test thiếu token, token sai, cookie vắng, session đã hủy, auth thiếu/sai.
12. Kiểm tra CSRF/CORS, SameSite, Secure, HttpOnly, TLS reverse proxy và custom exception handling theo chain.
13. Không ghi raw token, session ID, Authorization header vào log/telemetry; dùng metric/trace ID không nhạy cảm.
14. Chỉ loại trừ CSRF cho route có threat model đã phân tích và không phụ thuộc credential browser tự gửi.
15. Nâng cấp Spring Security đúng bản được hỗ trợ, kiểm lại API sau khi đổi major/minor version và test theo môi trường thực.

## 13. Bài tập tự luyện

1. Chạy dự án và gửi `POST /api/actions` với Basic hợp lệ nhưng **không** có `X-CSRF-TOKEN`. Vì sao nhận 403 trước khi controller?
2. Gọi `GET /api/csrf`; lưu `SESSION` cookie và token. Gửi POST cùng cookie và token, xác nhận 200.
3. Đổi đúng một ký tự trong token khi gửi POST. Giải thích vì sao server không được “sửa” token của client.
4. Dùng token vừa nhận nhưng **bỏ cookie SESSION**. Vì sao token đó không chứng minh session hiện tại là phiên đã phát token?
5. Gọi `POST /api/session/invalidate` hợp lệ rồi dùng lại token cũ. Tại sao đây là mô phỏng token không còn hiệu lực, **không phải** bằng chứng token có TTL riêng?
6. Thay `httpBasic` bằng form-login/session thật và viết test browser GET login, POST login CSRF, logout, sau đó request với tab cũ. Phân biệt 401, 302 và 403.
7. Đổi repository sang cookie `XSRF-TOKEN`, kiểm thử quy tắc `X-XSRF-TOKEN` và XOR request handler. Giải thích rủi ro khi tắt `HttpOnly`.
8. Viết integration test kiểm tra **counter không tăng** khi POST thiếu/sai CSRF token.
9. Tạo một user có quyền `ROLE_USER` nhưng không phải `ROLE_ADMIN`, thêm route POST admin và test 403 `access_denied` khi CSRF hợp lệ.
10. Thiết kế UI cho trường hợp người dùng điền form 30 phút, session mất, bấm Lưu. Thông báo nào không gây hiểu nhầm? Khi nào phải yêu cầu đăng nhập lại?
11. Kiểm tra việc thay đổi tên cookie session hoặc chạy hai pod không chung WebSessionStore. Triệu chứng quan sát và cách khắc phục?
12. Phân biệt CORS blocked, CSRF rejected, invalid Basic credential và authorization denied. Vì sao chỉ nhìn một 403 không đủ?

## Kết luận

Trong Spring Security **WebFlux**, `CsrfWebFilter` kiểm tra CSRF token ở các request **không an toàn**; default `WebSessionServerCsrfTokenRepository` lưu expected token trong `WebSession`. **Thiếu token, sai token và token cũ sau khi session không còn hợp lệ đều phải làm request bị từ chối**, thường bằng HTTP **403**. Đừng nhầm `CsrfException` reactive với các exception Servlet hoặc tự gắn nhãn “expired” khi không có bằng chứng về TTL riêng. API nên trả `application/problem+json` với mã generic `csrf_rejected`, khác `authentication_required` (401) và `access_denied` (403). Khi client gặp lỗi, **không tắt CSRF, không tự phát lại POST**; thay vào đó bootstrap token/session mới qua GET an toàn, yêu cầu đăng nhập lại khi cần và để người dùng gửi lại thao tác theo một luồng có kiểm soát.

## Tài liệu chính thức để kiểm tra theo phiên bản

1. Spring Security 6.5 — CSRF for WebFlux, WebSession repository, request handler và session timeout: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
2. Spring Security 6.3.8 — `CsrfWebFilter` và `setAccessDeniedHandler`: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/web/server/csrf/CsrfWebFilter.html
3. Spring Security 6.3.8 — `XorServerCsrfTokenRequestAttributeHandler`: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html
4. Spring Security 6.5 — `ServerHttpSecurity.CsrfSpec.accessDeniedHandler`: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.CsrfSpec.html
5. Spring Security 6.3.8 — `CsrfException` reactive: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/web/server/csrf/CsrfException.html
6. Spring Security — Reactive WebTestClient CSRF testing: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
7. Spring Security — CSRF conceptual reference, synchronizer token và safe methods: https://docs.spring.io/spring-security/reference/features/exploits/csrf.html
8. Spring Framework — WebSession API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebSession.html
9. RFC 9457 — Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457
