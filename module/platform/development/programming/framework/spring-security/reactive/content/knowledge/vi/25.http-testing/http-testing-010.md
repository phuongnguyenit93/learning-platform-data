# Kiểm tra header bảo mật, chuyển hướng và cấu trúc lỗi JSON

## Mục tiêu học tập

Bài học thuộc **Kiểm thử HTTP** của **Spring Security reactive (Spring WebFlux)**. Sau khi học, bạn có thể:

1. Dùng `WebTestClient` kiểm tra **status + response headers + JSON body**, không chỉ assert HTTP 200.
2. Phân biệt **security headers mặc định** của Spring Security (`Cache-Control`, `X-Content-Type-Options`, `X-Frame-Options`, HSTS trên HTTPS) với chính sách **phải cấu hình rõ** như Content-Security-Policy (CSP).
3. Kiểm tra **redirect** của request browser chưa đăng nhập: 3xx, `Location`, same-origin, không dùng untrusted return URL, không nhầm với JSON API 401.
4. Xác nhận một API trả **`application/problem+json`** với các trường `type/title/status/detail/instance` và mã lỗi nghiệp vụ `code` ổn định, bao gồm lỗi 400, 401, 403, 404.
5. Hiểu sự khác nhau giữa `ServerAuthenticationEntryPoint` (chưa xác thực), `ServerAccessDeniedHandler` (đã xác thực nhưng không đủ quyền), `@RestControllerAdvice` (lỗi nghiệp vụ) và global WebFlux error handler.
6. Tách hai `SecurityWebFilterChain`: API Bearer JWT **trả JSON** và browser route **chuyển hướng đăng nhập**; có fallback deny-all cho routes ngoài phạm vi.
7. Viết demo Java 17 + Spring Boot 3.5, dùng `mockJwt()` / `mockUser()` để test authorization HTTP; hiểu rằng mock JWT **không kiểm tra chữ ký JWT thật**.
8. Test ranh giới HTTP/HTTPS cho HSTS, `WWW-Authenticate` cho Bearer, không leak token/stack trace trong error body, và CSRF trong ứng dụng có browser cookie/session.
9. Thiết kế kiểm thử **ít brittle**: so header mang tính ngữ nghĩa, dùng JSONPath thay vì so chuỗi JSON nguyên văn, nhưng vẫn assert location/status/code chính xác khi chúng là public contract.

> **Phạm vi:** Spring Security **reactive** với `SecurityWebFilterChain`, `ServerHttpSecurity`, `WebTestClient`; không dùng Servlet `MockMvc`/`HttpSecurity`. Ví dụ browser route cho thấy **chuyển hướng khi chưa đăng nhập**, chưa tích hợp màn hình xác thực thật (OIDC/form login). API route dùng OAuth2 JWT Resource Server; test bằng mockJwt tập trung vào HTTP contract, còn JWS/JWKS/issuer/audience cần test tích hợp riêng.

## 1. Tại sao chỉ kiểm tra status code là chưa đủ?

Một API có thể trả HTTP 401 nhưng vẫn gây lỗi bảo mật:

- Trả HTML redirect `/login` thay vì JSON, khiến REST client không đọc được lỗi.
- Trả JSON `{"error":"Invalid token abc.def.ghi"}`, làm lộ Bearer token trong logs hoặc response.
- Không có `Cache-Control: no-store` trên response chứa thông tin nhạy cảm.
- Không có `X-Content-Type-Options: nosniff` khi client/browser có thể sniff MIME.
- Thiếu CSP cho trang HTML có nội dung nhúng script hoặc bị cho vào iframe không mong muốn.
- Trả 403 cho người chưa đăng nhập trong khi chuẩn ứng dụng là 401; hoặc 302 cho API vốn không có browser.
- JSON lỗi có cấu trúc ngẫu nhiên tùy nơi phát sinh: 401 ở security filter khác 400 ở controller.
- Redirect `Location` lấy từ tham số `returnUrl=https://attacker.example` gây open redirect.
- HSTS được assert trên HTTP localhost rồi nghĩ framework bị lỗi, dù HSTS chỉ được gửi trên **HTTPS**.

Cách kiểm thử tốt đặt **contract** ở ba lớp:

~~~text
HTTP Response
  |
  ├─ Status code: 200/302/400/401/403/404/500
  ├─ Headers:
  |     Content-Type
  |     Cache-Control
  |     X-Content-Type-Options
  |     X-Frame-Options
  |     Content-Security-Policy
  |     Strict-Transport-Security (HTTPS)
  |     WWW-Authenticate (nếu 401 theo HTTP auth)
  |     Location (nếu 3xx)
  |
  └─ Body:
        Successful DTO
        Hoặc problem JSON có schema đã thống nhất
~~~

Không assert tất cả headers cho mọi response theo một bảng máy móc. Security headers có tính **ngữ cảnh**: HTML khác JSON; static resources có thể cache được; HSTS liên quan HTTPS; redirect phục vụ browser chứ không phải luôn đúng cho API.

## 2. Bảng security headers quan trọng trong Spring Security WebFlux

Spring Security 6.5 bật nhiều security response headers mặc định. Một số có thể được ứng dụng thay đổi/ghi đè. Phải đọc **cấu hình hiện tại của security chain** và test behavior thực.

| Header | Ví dụ/kỳ vọng | Tác dụng và lưu ý |
|---|---|---|
| `Cache-Control` | Chứa `no-store` cho dữ liệu riêng tư/lỗi auth | Tránh cache response nhạy cảm. Mặc định thường gồm `no-cache, no-store, max-age=0, must-revalidate`; ứng dụng có thể override. |
| `Pragma` | `no-cache` (nếu policy dùng) | Tương thích HTTP cache cũ; không thay Cache-Control. |
| `Expires` | `0` hoặc giá trị chính sách | Liên quan cache; không nên assert giá trị nếu reverse proxy quản lý và contract không yêu cầu. |
| `X-Content-Type-Options` | `nosniff` | Chống một số dạng MIME sniffing; không thay kiểm tra Content-Type thực. |
| `X-Frame-Options` | `DENY` theo mặc định | Giảm clickjacking bằng cách chặn framing; có thể `SAMEORIGIN` theo policy. |
| `Strict-Transport-Security` | `max-age=...` **trên HTTPS** | HSTS áp cho secure responses; kiểm tra TLS/proxy configuration, không ép có trên HTTP. |
| `X-XSS-Protection` | `0` ở cấu hình mặc định hiện đại | Header cho XSS Auditor đã lỗi thời; không dùng thay CSP/escaping. |
| `Content-Security-Policy` | `default-src 'self'; object-src 'none'`, tùy trang | **Không được Spring thêm mặc định**: ứng dụng phải thiết kế policy phù hợp. |
| `Referrer-Policy` | Ví dụ `strict-origin-when-cross-origin` | Tùy cấu hình; không mặc định coi luôn có. |
| `Permissions-Policy` | Hạn chế camera/microphone/geolocation... | Cần policy riêng; tên/header support tùy stack/proxy. |
| `WWW-Authenticate` | Ví dụ `Bearer realm="api"` | Authentication challenge khi 401 cho Bearer API, khác X-Frame/CSP. |
| `Location` | `/web/login` hoặc URL cùng origin | Chỉ hợp cho response chuyển hướng, cần chặn open redirect. |

**Không nhầm hai header:** `Content-Type: application/json` mô tả body; `X-Content-Type-Options: nosniff` bảo browser không đoán MIME ngoài khai báo. Nếu API dùng RFC Problem Details thì `Content-Type` phù hợp là `application/problem+json`.

### 2.1. Assert giá trị đúng chứ không chỉ có header

Dùng `WebTestClient.expectHeader()`:

~~~java
client.get().uri("/api/public")
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
        .valueEquals("X-Content-Type-Options", "nosniff")
    .expectHeader()
        .valueEquals("X-Frame-Options", "DENY");
~~~

Đây là **mảnh test**; cần `client` đã bind Spring context. `exists("X-Frame-Options")` đơn thuần chưa đủ: value có thể là SAMEORIGIN nếu policy đòi DENY. Với security policy có khả năng thay đổi hợp lệ, chọn assert có nghĩa và gắn giá trị với kiến trúc.

### 2.2. Cache-Control nên kiểm tra theo directive

Không cần luôn so cả chuỗi `no-cache, no-store, max-age=0, must-revalidate` bởi thứ tự/giá trị có thể thay đổi do proxy hoặc response riêng. Với endpoint riêng tư có contract `no-store`:

~~~java
.expectHeader().value("Cache-Control", value ->
    assertTrue(value.contains("no-store")));
~~~

Đây là test fragment. Cần import `assertTrue`. Nếu application override Cache-Control để cache asset tĩnh, đừng ép asset trả no-store nếu điều đó trái yêu cầu hiệu năng. Nhưng **không** cache private profile/token/error details ở shared cache một cách vô ý.

### 2.3. HSTS: phải có ngữ cảnh HTTPS

HSTS được gửi khi ứng dụng coi request là secure. Với test in-memory qua `http://localhost`, test **không có HSTS** có thể đúng. Có thể mô phỏng request HTTPS qua `WebTestClient.mutate().baseUrl("https://localhost").build()`; với proxy thật cần integration test TLS/ForwardedHeaderTransformer đúng trust boundary.

**Không chỉ gắn `X-Forwarded-Proto: https` từ client rồi coi đó là trusted HTTPS**. Backend phải tin forwarded headers **chỉ từ proxies được phê duyệt**; attacker không được giả mạo HTTPS hoặc Host qua raw headers.

Cũng không tự bật HSTS `includeSubDomains/preload` trong demo nếu chưa hiểu toàn bộ subdomains đều hỗ trợ HTTPS. Việc preload là một thay đổi chính sách toàn domain, cần review.

### 2.4. CSP không được tự thêm

Với API JSON thuần, một policy chặt như:

~~~http
Content-Security-Policy: default-src 'none'; object-src 'none'; frame-ancestors 'none'
~~~

có thể phù hợp, nhưng CSP chủ yếu tác động lên **trình duyệt**. Với UI HTML dùng script/style và CDN, cần xây policy riêng, không sao chép `default-src 'none'` làm trang bị vỡ.

Spring Security WebFlux DSL:

~~~java
.headers(headers -> headers.contentSecurityPolicy(
    policy -> policy.policyDirectives(
        "default-src 'self'; object-src 'none'; frame-ancestors 'none'")))
~~~

Đây là mảnh `ServerHttpSecurity`, không phải Servlet header writer. CSP không thay HTML escaping, input validation hay clickjacking defense khác.

## 3. Test redirect: HTTP 3xx phải đi kèm Location an toàn

### 3.1. Browser route và API route có thể dùng entry point khác nhau

Một người dùng chưa đăng nhập truy cập trang browser:

~~~http
GET /web/private HTTP/1.1
Accept: text/html
~~~

Hệ thống có thể trả:

~~~http
HTTP/1.1 302 Found
Location: /web/login
~~~

Trong khi client REST gửi:

~~~http
GET /api/reports HTTP/1.1
Accept: application/json
~~~

nên nhận:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
WWW-Authenticate: Bearer realm="api"
~~~

**Không ép cả hai dùng cùng một failure response.** Browser cần điều hướng; API muốn status và JSON machine-readable. Nếu dùng một chain mặc định formLogin cho API, API rất dễ nhận HTML login redirect thay vì 401.

### 3.2. Assert không chỉ là 3xx

~~~java
client.get().uri("/web/private")
    .exchange()
    .expectStatus().is3xxRedirection()
    .expectHeader().value("Location", value -> {
        java.net.URI uri = java.net.URI.create(value);
        assertEquals("/web/login", uri.getPath());
        assertTrue(uri.getHost() == null
            || uri.getHost().equals("localhost"));
    });
~~~

Đây là test fragment. Kiểm tra **path đích** và **origin/host** tránh test chỉ thấy 302 nhưng thật ra bị redirect sang domain khác. Một số redirect strategy trả absolute URI thay vì relative URI, nên parse `java.net.URI` tốt hơn nối chuỗi thủ công.

Nếu hợp đồng yêu cầu 302, có thể dùng `isEqualTo(HttpStatus.FOUND)`. Nếu luồng chấp nhận nhiều mã 3xx hợp lệ do redirect strategy, dùng `is3xxRedirection()` và assert Location. Cần phân biệt **302/303/307/308** trong redirect sau POST vì chúng ảnh hưởng việc client giữ hay đổi HTTP method; không gom mọi thứ thành một status vô nghĩa.

### 3.3. Tránh open redirect

Một thiết kế sai lấy URL trực tiếp từ caller:

~~~http
GET /web/private?next=https://evil.example/collect
~~~

và phản hồi:

~~~http
Location: https://evil.example/collect
~~~

Nếu có `next`/`returnUrl`, backend phải validate origin/path allowlist hoặc chỉ chấp nhận relative local path đã canonicalize. Không tin cả `Host` lẫn `X-Forwarded-Host` raw làm redirect domain. Test phải gửi `next=https://evil.example` rồi xác nhận Location vẫn ở origin được phép.

### 3.4. Test WebTestClient không tự đồng nghĩa trình duyệt thật

`WebTestClient` mặc định test HTTP response, không có browser UI/history/JavaScript. Test 3xx nên assert **response ban đầu** cùng Location; nếu muốn kiểm tra trang login riêng, gửi thêm một GET đến URL login và assert 200. Browser automation chỉ cần khi phải xác minh cookie/SameSite/CSP thực tế hoặc OIDC provider redirect flow end-to-end.

### 3.5. Form login, OAuth2 Login và custom redirect

Các entry points có thể khác nhau:

- `RedirectServerAuthenticationEntryPoint`: redirect đến URL cấu hình, phù hợp mô phỏng browser navigation.
- Form login: thường dẫn đến login page/redirect nếu configured; login failure và success URLs cũng cần test.
- OAuth2 Login: có thể redirect đến Authorization Server với state/nonce/PKCE, cần test allowlisted redirect URI và CSRF state; không assert raw state ngẫu nhiên cố định.
- JSON API entry point: trả 401, không Location.
- API scope thiếu: trả 403 JSON, không redirect.

Nếu OIDC/OAuth2 redirects động, assert **scheme/host/path, required query keys**, presence of `state` và correlation, không hardcode ngẫu nhiên `state` vào snapshot.

## 4. Error JSON: thiết kế hợp đồng có thể kiểm thử

Bài lab dùng body **gần với RFC 9457 Problem Details**:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required.",
  "instance": "/api/reports",
  "code": "AUTH_REQUIRED"
}
~~~

Ý nghĩa:

| Field | Tác dụng | Điều kiện test |
|---|---|---|
| `type` | URI xác định loại problem, `about:blank` là trường hợp mặc định | Đúng string/URI contract |
| `title` | Mô tả ngắn loại lỗi | Không lộ raw exception |
| `status` | HTTP status trong body, khớp response status | 401/403/400/404 tương ứng |
| `detail` | Lời giải thích an toàn cho người dùng | Không chứa token/stack trace/DB query |
| `instance` | URI/path xảy ra lỗi | Không echo query secrets |
| `code` | Extension field riêng của ứng dụng | Stable machine-readable error code |

RFC 9457 cho phép extension members như `code`. **Không có quy tắc** mọi API phải dùng chính xác các mã AUTH_REQUIRED/ACCESS_DENIED; đây là hợp đồng chọn cho bài học.

### 4.1. Cần nhất quán lỗi ở security filter và controller

Một `@RestControllerAdvice` thông thường xử lý exception từ controller/service, **không phải cách duy nhất bắt lỗi 401/403 từ Spring Security filters**. Hãy phân biệt:

- `ServerAuthenticationEntryPoint`: authentication chưa thành công, tạo **401** (thường kèm WWW-Authenticate nếu dùng Bearer).
- `ServerAccessDeniedHandler`: authenticated nhưng thiếu quyền, tạo **403**.
- `@ExceptionHandler`/`@RestControllerAdvice`: lỗi request validation/business (ví dụ 400, 404) trong controller.
- `ErrorWebExceptionHandler`: ranh giới lỗi WebFlux rộng hơn, nếu muốn chuẩn hóa mọi lỗi.
- Resource Server Bearer-specific handlers có thể tự ghi WWW-Authenticate; nếu custom chúng, phải giữ các chi tiết HTTP auth protocol cần thiết.

**Quan trọng:** Bọc controller bằng try/catch không bắt hết 401/403 do SecurityWebFilterChain trả trước khi request đến controller.

### 4.2. 401 khác 403

| Tình huống | Kỳ vọng | Không nên |
|---|---|---|
| Thiếu Bearer token cho API protected | 401 JSON + challenge Bearer | 302 HTML login |
| JWT sai chữ ký/issuer/audience/expired | 401 (theo auth failure flow) | Lộ token/error kỹ thuật |
| JWT hợp lệ nhưng thiếu scope | 403 JSON, có thể challenge insufficient_scope | 401 làm client liên tục đăng nhập lại |
| Đã authenticated nhưng thiếu business permission | 403 JSON | 200 rỗng hoặc fallback admin |
| Input sai/validation | 400 JSON thống nhất | Trả full stack trace |
| Tài nguyên không tồn tại | 404 JSON thống nhất | Trả thông tin tồn tại resource riêng của user khác |

Với Bearer, `WWW-Authenticate: Bearer realm="api"` ở 401 là một challenge; 403 do scope có thể dùng `Bearer error="insufficient_scope"` theo RFC 6750. Đừng log/echo raw token vào challenge, detail hay response body.

### 4.3. Body và header đều cần assert

Một test tốt:

~~~java
client.get().uri("/api/reports")
    .exchange()
    .expectStatus().isUnauthorized()
    .expectHeader().contentTypeCompatibleWith(
        MediaType.parseMediaType("application/problem+json"))
    .expectHeader().valueEquals(
        "WWW-Authenticate", "Bearer realm=\"api\"")
    .expectHeader().doesNotExist("Location")
    .expectBody()
    .jsonPath("$.status").isEqualTo(401)
    .jsonPath("$.code").isEqualTo("AUTH_REQUIRED")
    .jsonPath("$.type").isEqualTo("about:blank");
~~~

Đây là test fragment; trong mã lab đầy đủ phía sau. **Không so full JSON string** vì thứ tự key không là contract của JSON. Nhưng nếu body phải có `code` cố định, hãy assert chính xác cả giá trị code.

### 4.4. Tránh phản hồi lỗi không an toàn

Không đặt:

~~~json
{
  "detail": "Signature failed for Bearer eyJhbGciOi...",
  "exception": "org.springframework.security.oauth2...",
  "stackTrace": "...",
  "sql": "SELECT * FROM accounts WHERE ..."
}
~~~

Ngoài rò secret, các detail này làm enumeration và hỗ trợ attacker phân tích stack. Trong log nội bộ có thể ghi correlation ID, route, sanitized reason code và trace an toàn. Không cho `instance` chứa nguyên query string nếu query có thể chứa secrets.

### 4.5. Vấn đề response đã committed

Trong reactive `ServerHttpResponse`, cần thiết lập status/headers **trước khi** trả publisher ghi body; không gọi `block()`/`subscribe()` thủ công. Nếu response đã committed, không cố ghi JSON body lần thứ hai hoặc đổi status thành 401 muộn; đó là bug trong pipeline. Security handlers nên được gọi khi response còn có thể ghi.

## 5. Lab Spring Boot WebFlux: API Problem JSON và browser redirect

Ví dụ Java 17 + Spring Boot 3.5.16, gồm:

- API route `/api/**`: OAuth2 JWT Resource Server; public GET, GET reports yêu cầu `SCOPE_reports.read`, GET admin yêu cầu `SCOPE_admin.read`.
- API 401/403 trả `application/problem+json` với WWW-Authenticate khi phù hợp, Cache-Control no-store, không Location.
- GET `/api/validate?limit=0` trả 400 và GET `/api/items/missing` trả 404 qua `@RestControllerAdvice` với **cùng schema JSON**.
- Browser route `/web/**`: GET `/web/private` chưa authenticated chuyển hướng đến `/web/login`, không trả Problem JSON. Đây chỉ là mô phỏng entry point: **chưa triển khai hệ thống đăng nhập thực**.
- `/web/login` public, `/web/private` cần Authentication.
- Catch-all chain cuối dùng deny-all, tránh URL không match hai chains trở thành public.
- Các chains có CSP policy riêng; Spring Security vẫn giữ default security headers.

### 5.1. Cấu trúc thư mục

~~~text
http-security-tests/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/HttpContractApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/example/HttpContractTest.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'http-security-tests'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

JDK 17+ và Gradle/Gradle Wrapper phù hợp. Demo thuần WebFlux, không cần Servlet `spring-boot-starter-web`, không cần database.

Tệp `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
          jwk-set-uri: https://idp.example.test/issuer/jwks
          audiences:
            - reports-api
~~~

Issuer/JWKS trên là **placeholder**; phải thay bằng IdP HTTPS thật để validate Bearer JWT trong production. Có cả `issuer-uri` và `jwk-set-uri` giúp biết keys URI mà không cần discovery ngay startup; signature/issuer/audience validation vẫn là công việc của JWT decoder khi nhận token. `mockJwt()` trong unit test không kiểm tra các validation ấy.

### 5.2. Ứng dụng đầy đủ

Tệp `src/main/java/example/HttpContractApplication.java`:

~~~java
package example;

import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.ServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationEntryPoint;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class HttpContractApplication {

    private static final MediaType PROBLEM_JSON =
        MediaType.parseMediaType("application/problem+json");

    public static void main(String[] args) {
        SpringApplication.run(HttpContractApplication.class, args);
    }

    public record ProblemDocument(
        String type,
        String title,
        int status,
        String detail,
        String instance,
        String code) {
    }

    static ProblemDocument problemDocument(
        HttpStatus status, String detail, String path, String code) {

        return new ProblemDocument(
            "about:blank",
            status.getReasonPhrase(),
            status.value(),
            detail,
            path,
            code);
    }

    // Security handlers operate BEFORE controller advice.
    static Mono<Void> writeSecurityProblem(
        ServerWebExchange exchange,
        ObjectMapper mapper,
        HttpStatus status,
        String detail,
        String code) {

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(status);
        response.getHeaders().setContentType(PROBLEM_JSON);
        response.getHeaders().setCacheControl("no-store");

        if (status == HttpStatus.UNAUTHORIZED) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer realm=\"api\"");
        }
        else if (status == HttpStatus.FORBIDDEN) {
            response.getHeaders().set(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer error=\"insufficient_scope\"");
        }

        var body = problemDocument(
            status,
            detail,
            exchange.getRequest().getPath().value(),
            code);

        return Mono.fromCallable(() ->
                mapper.writeValueAsBytes(body))
            .flatMap(bytes -> response.writeWith(
                Mono.just(response.bufferFactory().wrap(bytes))));
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain api(
        ServerHttpSecurity http, ObjectMapper mapper) {

        ServerAuthenticationEntryPoint entryPoint =
            (exchange, error) -> writeSecurityProblem(
                exchange, mapper,
                HttpStatus.UNAUTHORIZED,
                "Authentication is required.",
                "AUTH_REQUIRED");

        ServerAccessDeniedHandler deniedHandler =
            (exchange, error) -> writeSecurityProblem(
                exchange, mapper,
                HttpStatus.FORBIDDEN,
                "Insufficient permission.",
                "ACCESS_DENIED");

        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/api/**"))
            // Chỉ đúng cho Bearer-only API, KHÔNG dùng session cookie.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .headers(headers -> headers
                .contentSecurityPolicy(policy -> policy
                    .policyDirectives(
                        "default-src 'none'; object-src 'none'; "
                        + "frame-ancestors 'none'")))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/validate")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/items/*")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.GET, "/api/admin")
                    .hasAuthority("SCOPE_admin.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler)
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browser(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/web/**"))
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            // Login UI là demo; chưa bật form login thật.
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .headers(headers -> headers
                .contentSecurityPolicy(policy -> policy
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; "
                        + "frame-ancestors 'none'")))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new RedirectServerAuthenticationEntryPoint(
                        "/web/login")))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/web/login")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/web/private")
                    .authenticated()
                .anyExchange().denyAll())
            .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain denyOtherRoutes(ServerHttpSecurity http) {
        return http
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().denyAll())
            .build();
    }

    static class InvalidLimit extends RuntimeException {
    }

    static class ItemMissing extends RuntimeException {
    }

    @RestController
    public static class Endpoints {

        @GetMapping("/api/public")
        public Mono<Map<String, String>> publicApi() {
            return Mono.just(Map.of("message", "public"));
        }

        @GetMapping("/api/reports")
        public Mono<Map<String, String>> reports() {
            return Mono.just(Map.of("report", "available"));
        }

        @GetMapping("/api/admin")
        public Mono<Map<String, String>> admin() {
            return Mono.just(Map.of("admin", "ok"));
        }

        @GetMapping("/api/validate")
        public Mono<Map<String, Integer>> validate(
            @RequestParam int limit) {

            if (limit < 1 || limit > 100) {
                return Mono.error(new InvalidLimit());
            }
            return Mono.just(Map.of("limit", limit));
        }

        @GetMapping("/api/items/{id}")
        public Mono<Map<String, String>> item(
            @PathVariable String id) {

            if (!"visible".equals(id)) {
                return Mono.error(new ItemMissing());
            }
            return Mono.just(Map.of("id", id));
        }

        @GetMapping(
            value = "/web/login",
            produces = MediaType.TEXT_PLAIN_VALUE)
        public Mono<String> login() {
            return Mono.just("Demo login page");
        }

        @GetMapping(
            value = "/web/private",
            produces = MediaType.TEXT_PLAIN_VALUE)
        public Mono<String> privatePage() {
            return Mono.just("Private browser page");
        }
    }

    @RestControllerAdvice
    public static class ApiErrors {

        @ExceptionHandler(InvalidLimit.class)
        public ResponseEntity<ProblemDocument> invalidLimit(
            ServerWebExchange exchange) {

            return businessProblem(
                exchange, HttpStatus.BAD_REQUEST,
                "limit must be between 1 and 100.",
                "INVALID_LIMIT");
        }

        @ExceptionHandler(ItemMissing.class)
        public ResponseEntity<ProblemDocument> itemMissing(
            ServerWebExchange exchange) {

            return businessProblem(
                exchange, HttpStatus.NOT_FOUND,
                "Requested item does not exist.",
                "ITEM_NOT_FOUND");
        }

        private ResponseEntity<ProblemDocument> businessProblem(
            ServerWebExchange exchange,
            HttpStatus status, String detail, String code) {

            return ResponseEntity.status(status)
                .contentType(PROBLEM_JSON)
                .cacheControl(CacheControl.noStore())
                .body(problemDocument(
                    status,
                    detail,
                    exchange.getRequest().getPath().value(),
                    code));
        }
    }
}
~~~

### 5.3. Vì sao có hai security chains và một fallback?

- `@Order(1)` cho `/api/**` xử lý Bearer/JWT và JSON Problem.
- `@Order(2)` cho `/web/**` xử lý browser navigation, chưa authenticated thì redirect `/web/login`.
- `@Order(3)` deny-all tránh các URLs ngoài phạm vi bị bỏ qua do không chain nào match.
- Khi nhiều `SecurityWebFilterChain` tồn tại, **chain match đầu tiên được dùng**; không mặc định request chạy cả 3 chains.
- API chain tắt formLogin/Basic, dùng custom entry point/access denied handler. Browser chain không dùng API JSON entry point.
- API error handler được cấu hình cả trong `exceptionHandling` và OAuth2 Resource Server DSL để không có sự khác biệt bất ngờ giữa “không có credential” và Bearer authentication thất bại.
- `@RestControllerAdvice` xử lý 400/404 từ controller, không cố bắt 401/403 từ Spring Security filter.
- Mỗi chain có CSP riêng; các security headers mặc định khác vẫn được giữ, không gọi `headers().disable()`.
- CSRF chỉ bị disable ở **API Bearer-only**. Browser chain để CSRF mặc định; nếu bổ sung POST forms/cookie login, cần test `csrf()`.

### 5.4. Cơ chế viết JSON trong reactive security handler

Trong `writeSecurityProblem(...)`:

1. Đặt status trước khi response committed.
2. Đặt Content-Type `application/problem+json`.
3. Đặt Cache-Control `no-store`.
4. Đặt `WWW-Authenticate` phù hợp Bearer 401/403 trong lab.
5. Tạo `ProblemDocument` với code ổn định và path, **không** copy raw token/query string/exception.
6. Dùng Jackson `ObjectMapper.writeValueAsBytes(...)` bên trong `Mono.fromCallable` và `response.writeWith(Mono.just(...))`.
7. Không `block()` hoặc `subscribe()` thủ công.
8. Dùng `response.bufferFactory().wrap(bytes)` tạo DataBuffer; reactive server sẽ quản lý write và completion.

Mẫu này phù hợp error body nhỏ. Production nên gom error-code registry, correlation ID, telemetry, exception mapping và handling serialization failures; không ghi response lần hai khi đã committed.

### 5.5. Hợp đồng HTTP dự kiến

| Request | Authentication | Expected status | Content-Type / Location | `code` |
|---|---|---:|---|---|
| GET /api/public | Anonymous | 200 | application/json | Không có problem |
| GET /api/reports | Anonymous | 401 | application/problem+json; **không** Location | AUTH_REQUIRED |
| GET /api/reports | JWT thiếu reports.read | 403 | application/problem+json | ACCESS_DENIED |
| GET /api/reports | JWT có reports.read | 200 | application/json | Không có problem |
| GET /api/admin | JWT chỉ có reports.read | 403 | application/problem+json | ACCESS_DENIED |
| GET /api/admin | JWT có admin.read | 200 | application/json | Không có problem |
| GET /api/validate?limit=0 | Anonymous | 400 | application/problem+json | INVALID_LIMIT |
| GET /api/items/missing | Anonymous | 404 | application/problem+json | ITEM_NOT_FOUND |
| GET /web/private | Anonymous | 3xx | Location dẫn đến /web/login | Không có Problem JSON |
| GET /web/login | Anonymous | 200 | text/plain | Không có problem |
| GET /web/private | mock authenticated | 200 | text/plain | Không có problem |

Dữ liệu trên là **expected behavior** của code, không khẳng định đã thực thi. Browser route chưa có login flow thật. API JWT protected cũng cần issuer/JWKS thật khi không dùng test mocks.

## 6. Test tích hợp WebTestClient cho các HTTP contracts

Tệp `src/test/java/example/HttpContractTest.java`:

~~~java
package example;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class HttpContractTest {

    @Autowired
    WebTestClient client;

    private WebTestClient withScope(String scope) {
        return client.mutateWith(mockJwt().authorities(
            new SimpleGrantedAuthority("SCOPE_" + scope)));
    }

    @Test
    void publicApiReturns200AndJson() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.message").isEqualTo("public");
    }

    @Test
    void defaultNosniffAndFrameDenyArePresent() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff")
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY");
    }

    @Test
    void cspWasConfiguredForTheApi() {
        client.get().uri("/api/public")
            .exchange()
            .expectHeader().value(
                "Content-Security-Policy", csp -> {
                    assertTrue(csp.contains(
                        "default-src 'none'"));
                    assertTrue(csp.contains(
                        "frame-ancestors 'none'"));
                });
    }

    @Test
    void successfulApiResponseIsNotStoredInSharedCache() {
        client.get().uri("/api/public")
            .exchange()
            .expectHeader().value(
                HttpHeaders.CACHE_CONTROL,
                value -> assertTrue(
                    value.contains("no-store")));
    }

    @Test
    void hstsIsAbsentForPlainHttpRequest() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                "Strict-Transport-Security");
    }

    @Test
    void hstsIsPresentOnMockHttpsRequest() {
        WebTestClient secureClient = client.mutate()
            .baseUrl("https://localhost").build();

        secureClient.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().value(
                "Strict-Transport-Security",
                value -> assertTrue(value.contains("max-age=")));
    }

    @Test
    void anonymousApiGets401ProblemAndBearerChallenge() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/problem+json"))
            .expectHeader().valueEquals(
                HttpHeaders.WWW_AUTHENTICATE,
                "Bearer realm=\"api\"")
            .expectHeader().doesNotExist(
                HttpHeaders.LOCATION)
            .expectBody()
            .jsonPath("$.type").isEqualTo("about:blank")
            .jsonPath("$.title").isEqualTo("Unauthorized")
            .jsonPath("$.status").isEqualTo(401)
            .jsonPath("$.code").isEqualTo("AUTH_REQUIRED")
            .jsonPath("$.instance").isEqualTo("/api/reports");
    }

    @Test
    void error401IsExplicitlyNotCached() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().value(
                HttpHeaders.CACHE_CONTROL,
                value -> assertTrue(
                    value.contains("no-store")));
    }

    @Test
    void insufficientScopeGets403ProblemNotRedirect() {
        withScope("other.read")
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/problem+json"))
            .expectHeader().doesNotExist(HttpHeaders.LOCATION)
            .expectBody()
            .jsonPath("$.status").isEqualTo(403)
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED")
            .jsonPath("$.instance").isEqualTo("/api/reports");
    }

    @Test
    void reportsScopeGrantsReportsEndpoint() {
        withScope("reports.read")
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.report").isEqualTo("available");
    }

    @Test
    void reportScopeDoesNotGrantAdminAccess() {
        withScope("reports.read")
            .get().uri("/api/admin")
            .exchange()
            .expectStatus().isForbidden()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ACCESS_DENIED");
    }

    @Test
    void adminScopeCanAccessAdminRoute() {
        withScope("admin.read")
            .get().uri("/api/admin")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.admin").isEqualTo("ok");
    }

    @Test
    void anonymousBrowserRouteRedirectsToLocalLogin() {
        client.get().uri("/web/private")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(
                HttpHeaders.LOCATION, value -> {
                    URI target = URI.create(value);
                    assertEquals("/web/login", target.getPath());
                    assertTrue(target.getHost() == null
                        || target.getHost().equals("localhost"));
                });
    }

    @Test
    void untrustedNextParameterCannotChangeRedirectOrigin() {
        client.get().uri(
            "/web/private?next=https://evil.example/steal")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value(
                HttpHeaders.LOCATION, value -> {
                    URI target = URI.create(value);
                    assertEquals("/web/login", target.getPath());
                    assertFalse(value.contains("evil.example"));
                });
    }

    @Test
    void browserLoginPageIsPublic() {
        client.get().uri("/web/login")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_PLAIN)
            .expectBody(String.class)
            .isEqualTo("Demo login page");
    }

    @Test
    void authenticatedBrowserRequestDoesNotRedirect() {
        client.mutateWith(mockUser("alice").roles("USER"))
            .get().uri("/web/private")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(HttpHeaders.LOCATION)
            .expectBody(String.class)
            .isEqualTo("Private browser page");
    }

    @Test
    void businessValidationErrorUsesSameProblemShape() {
        client.get().uri("/api/validate?limit=0")
            .exchange()
            .expectStatus().isBadRequest()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/problem+json"))
            .expectBody()
            .jsonPath("$.type").isEqualTo("about:blank")
            .jsonPath("$.status").isEqualTo(400)
            .jsonPath("$.code").isEqualTo("INVALID_LIMIT")
            .jsonPath("$.instance").isEqualTo("/api/validate");
    }

    @Test
    void missingBusinessResourceUses404Problem() {
        client.get().uri("/api/items/missing")
            .exchange()
            .expectStatus().isNotFound()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.parseMediaType("application/problem+json"))
            .expectBody()
            .jsonPath("$.status").isEqualTo(404)
            .jsonPath("$.code").isEqualTo("ITEM_NOT_FOUND");
    }

    @Test
    void errorInstanceDoesNotEchoSensitiveQuery() {
        client.get().uri(
            "/api/validate?limit=0&token=do-not-echo")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.instance").isEqualTo("/api/validate");
    }

    @Test
    void errorBodyDoesNotExposeExceptionOrToken() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectBody(String.class)
            .consumeWith(result -> {
                String body = result.getResponseBody();
                assertNotNull(body);
                assertFalse(body.contains("stackTrace"));
                assertFalse(body.contains("exception"));
                assertFalse(body.contains("Bearer "));
            });
    }
}
~~~

### 6.1. Chạy tests

~~~bash
gradle test
~~~

Nếu có wrapper: `./gradlew test` (Linux/macOS) hoặc `gradlew.bat test` (Windows). Lớp trên có **20 phương thức test**. Chúng **được thiết kế để pass** với Spring Boot 3.5.x/Spring Security 6.5.x tương thích; vẫn phải thực thi build/test trên môi trường thật mới biết kết quả thực tế. Không tuyên bố những tests đã chạy trong lúc soạn bài.

### 6.2. Vì sao test HSTS dùng hai requests khác nhau?

- `hstsIsAbsentForPlainHttpRequest`: kiểm tra plain HTTP mock request **không có** HSTS. Đây không phải lỗi.
- `hstsIsPresentOnMockHttpsRequest`: tạo `WebTestClient` với base URL HTTPS để mô phỏng secure request, rồi assert HSTS có `max-age=`.
- Trong production reverse proxy, cần **test end-to-end TLS thật** để xác định bên nào chèn HSTS và backend thấy scheme gì. Không chỉ giả mạo X-Forwarded-Proto bằng một request header tự gửi.
- Nếu ứng dụng hoặc gateway override security headers, test kỳ vọng phải gắn với contract **sau toàn bộ proxy path**, không chỉ một in-memory mock.

### 6.3. Vì sao mockJwt()/mockUser() không phải full authentication test?

`mockJwt()` tạo JwtAuthenticationToken trong security context test và có thể gắn authorities tường minh. Nó bỏ qua chữ ký, `iss`, `aud`, expiry và JWKS decoder. Bài này kiểm tra response contracts sau authorization, **không kiểm tra token issuance/validation**.

Tương tự `mockUser()` chứng minh browser route yêu cầu authenticated principal và không redirect khi có mock Authentication, **không** chứng minh form login/OIDC/cookies hoạt động. Nếu triển khai đăng nhập thật, cần thêm tests cho login, session fixation, cookie flags, CSRF, logout và refresh flows.

### 6.4. Tại sao so JSONPath thay vì toàn body?

JSON là object không có thứ tự key mang tính ngữ nghĩa. Không nên test:

~~~java
// PHẢN VÍ DỤ: dễ fail chỉ vì thứ tự key thay đổi.
expectBody(String.class).isEqualTo(
    "{\"code\":\"AUTH_REQUIRED\",\"status\":401}");
~~~

Trong khi JSON thực có thể chứa thêm `type/title/detail/instance`. Dùng `jsonPath("$.code").isEqualTo(...)` và `jsonPath("$.status").isEqualTo(...)` để kiểm tra contract. Nếu API yêu cầu **không có** một field bảo mật nhất định, có thể dùng JSONPath `doesNotExist()` hoặc parse JSON tree để assert field absent; trong demo, check raw body không chứa exception/token chỉ là sanity check bổ sung.

### 6.5. Assert 401 vs 403 đúng ngữ cảnh

Một số ứng dụng yêu cầu authentication khác nhau trên nhiều chains: browser chưa đăng nhập 302, API không Bearer 401, authenticated thiếu scope 403. Test **cùng URL với ba identities** giúp phát hiện regression:

~~~text
GET /api/reports, không token            → 401 problem JSON
GET /api/reports, mock JWT scope=other   → 403 problem JSON
GET /api/reports, mock JWT scope=reports  → 200 JSON
~~~

Tương tự browser:

~~~text
GET /web/private, anonymous             → 3xx Location=/web/login
GET /web/private, authenticated         → 200 text/plain
GET /web/login, anonymous               → 200 text/plain
~~~

Đây là bảng contract dự kiến, không phải live HTTP output đã quan sát.

## 7. Kiểm tra lỗi JSON ở nhiều lớp ứng dụng

### 7.1. Lỗi security và business phải cùng JSON contract

Trong lab:

~~~text
Request
  |
  ├─ SecurityWebFilterChain
  |      ├─ ServerAuthenticationEntryPoint → 401 ProblemDocument
  |      └─ ServerAccessDeniedHandler      → 403 ProblemDocument
  |
  └─ Controller / service
         ├─ @ExceptionHandler(InvalidLimit) → 400 ProblemDocument
         └─ @ExceptionHandler(ItemMissing)  → 404 ProblemDocument
~~~

Đây là lý do cần test cả 400/401/403/404. Nếu chỉ test controller advice, security filter có thể trả HTML mặc định. Nếu chỉ test filter, lỗi validation có thể trả một schema hoàn toàn khác.

### 7.2. Cách test 500 mà không lộ chi tiết nhạy cảm

Trong production, có thể định nghĩa response chuẩn:

~~~json
{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "An unexpected error occurred.",
  "instance": "/api/example",
  "code": "INTERNAL_ERROR"
}
~~~

Không phát raw exception message, stacktrace, SQL, credential. Tuy nhiên đừng bắt mọi `Throwable` rồi nuốt lỗi như 200; hãy để monitoring nhận tín hiệu failure và trả HTTP 500. Để có contract nhất quán, kiểm tra hành vi của `ErrorWebExceptionHandler`/Spring Boot error handling thực sự được bật. **Lab không cài một fallback 500 mới**, nên không hứa rằng mọi exception không dự kiến đều theo schema của demo.

### 7.3. JSON serialization và độ an toàn

Dùng Jackson/ObjectMapper đã cấu hình trong ứng dụng, không tự nối JSON string từ `exception.getMessage()`. `ProblemDocument` dùng field names/values rõ ràng; `instance` lấy từ request path đã được framework parse, không echo query params. Nhờ serializer, dấu nháy/ký tự điều khiển sẽ được escape đúng.

### 7.4. Chú ý WWW-Authenticate

Theo RFC 6750, Bearer API nên có challenge đúng khi 401; 403 thiếu scope có thể cung cấp `insufficient_scope`. Lab dùng đơn giản:

~~~http
WWW-Authenticate: Bearer realm="api"
~~~

và:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Nhưng một ứng dụng thật có thể dùng `BearerTokenServerAuthenticationEntryPoint` và `BearerTokenServerAccessDeniedHandler` để tạo challenge dựa trên OAuth2 error code. Nếu thay bằng JSON handlers tự viết, cần kiểm tra cả HTTP auth headers, không chỉ JSON body.

## 8. Kiểm thử redirect trong OIDC/OAuth2 và sau POST

Lab chỉ redirect đến `/web/login`. Với login OAuth2 thật, redirect thường chứa:

~~~text
/oauth2/authorization/<registrationId>
    → authorization endpoint của IdP
       ?response_type=code
       &client_id=...
       &redirect_uri=...
       &scope=...
       &state=<random>
       [&code_challenge=...]
~~~

Đây là sơ đồ, không phải một URL có thể chạy trực tiếp. Các tests nên:

- Xác nhận Location dùng **issuer/authorization host được phê duyệt**, không domain từ untrusted input.
- Xác nhận `response_type=code`, `state` hiện diện và không rỗng, redirect_uri chính xác trong allowlist.
- Với PKCE, xác nhận code_challenge và method hợp lệ trong flow cần PKCE; không assert giá trị challenge ngẫu nhiên cố định.
- Không log raw authorization code, `state`/session ID hoặc tokens.
- Test callback state sai/bị thiếu hoặc expired phải bị từ chối; tránh CSRF/login CSRF.
- Không để tham số `next`/`returnUrl` biến redirect thành open redirect.
- Sau POST, phân biệt 303 (đổi sang GET theo redirect semantics) với 307/308 (giữ method/body), đặc biệt với thao tác nhạy cảm.

Nếu test có browser thật, verify cookie flags `Secure`, `HttpOnly`, `SameSite`, session rotation, CSRF protection và logout redirects. Đừng suy diễn từ một WebTestClient mock rằng toàn bộ OIDC/SAML/browser flow đã được kiểm thử.

## 9. Những lỗi thường gặp

**1. Chỉ assert HTTP 200:** thiếu các kiểm tra 401, 403, 3xx, security headers và error body.

**2. Tin rằng CSP có mặc định:** Spring Security không thêm CSP chung; cần explicit policy.

**3. Assert HSTS trên HTTP localhost:** HSTS theo HTTPS; phải test secure request hoặc TLS thật.

**4. Bật preload/includeSubDomains HSTS tùy tiện:** có thể khóa subdomains chưa HTTPS; review domain policy trước.

**5. Chỉ assert header tồn tại:** X-Frame-Options SAMEORIGIN có thể không đúng policy DENY.

**6. So toàn chuỗi Cache-Control theo thứ tự cố định:** thường chỉ cần assert no-store/no-cache directives theo contract.

**7. Trộn Content-Type với X-Content-Type-Options:** chúng có chức năng khác nhau.

**8. Disable toàn bộ headers bằng `headers.disable()` để test pass:** làm mất security defaults.

**9. Cấu hình form login cho API rồi chấp nhận 302:** REST caller thường cần 401 JSON, không HTML redirect.

**10. Nhầm 401 và 403:** chưa authenticated → 401; authenticated thiếu quyền → 403.

**11. Không assert WWW-Authenticate:** làm Bearer client khó xử lý challenge đúng RFC.

**12. 3xx nhưng Location trỏ domain attacker:** cần kiểm tra host/origin, open redirect.

**13. Test chỉ `is3xxRedirection()`:** bỏ sót redirect sang sai path/host.

**14. So code/state ngẫu nhiên của OAuth2 redirect:** dễ brittle và không kiểm tra đúng security properties.

**15. Dùng @RestControllerAdvice để bắt tất cả Spring Security filter errors:** 401/403 thường phát sinh trước controller.

**16. Security handler trả raw exception message:** rò token, SQL, stack trace.

**17. Custom 401 Problem JSON nhưng quên Bearer challenge:** phá HTTP auth contract.

**18. Custom 403 nhưng dùng AUTH_REQUIRED code:** làm client hiểu nhầm cần đăng nhập lại.

**19. So JSON body nguyên string:** thứ tự fields/formatting thay đổi gây false failures; dùng JSONPath.

**20. Chỉ test Content-Type application/json với Problem Details:** `application/problem+json` nên được kiểm tra đúng.

**21. Chỉ kiểm tra lỗi controller:** bỏ sót lỗi ở security chain, gateway, reverse proxy, decoder.

**22. Dùng mockJwt rồi kết luận JWT signature hợp lệ:** mocks không verify JWS/JWKS/issuer/audience.

**23. Dùng mockUser rồi kết luận login flow hoàn chỉnh:** chỉ tạo Authentication giả cho test.

**24. Không có catch-all SecurityWebFilterChain:** một số URL có thể không match chain nào và không được bảo vệ.

**25. Multiple chains sai @Order:** API có thể bị browser entry point redirect hoặc ngược lại.

**26. Đặt key/token trong query rồi echo instance:** query leak vào JSON error/logs.

**27. Tắt CSRF cho browser cookie/session route:** giữ CSRF cho unsafe methods.

**28. Khẳng định HSTS tại app nhưng proxy strip header:** phải kiểm tra full production network path.

**29. Đặt report CSP nhưng không test trên HTML thực:** browser CSP có thể phá chức năng trang hoặc còn quá lỏng.

**30. Dùng local-only test thay kiểm tra TLS/redirect/cookie ở staging:** nhiều vấn đề chỉ lộ sau proxy.

## 10. Checklist cho bộ HTTP security tests

1. Mỗi endpoint có bảng status cho anonymous, authenticated thiếu quyền, đủ quyền?
2. API endpoint thiếu token có 401 JSON, không 302 HTML?
3. API thiếu scope có 403 JSON, không bắt user đăng nhập lại?
4. `WWW-Authenticate` phù hợp scheme (Basic/Bearer) và error codes?
5. `Content-Type` của Problem Details đúng `application/problem+json`?
6. JSON chứa `type/title/status/detail/instance/code` và status khớp HTTP?
7. JSON không có stackTrace/exception/raw token/query secret?
8. Lỗi 400/404 từ controller và 401/403 từ security có cùng schema?
9. Unexpected 500 có generic body, audit/correlation, không leak stack/SQL?
10. X-Content-Type-Options là `nosniff`?
11. X-Frame-Options có đúng DENY/SAMEORIGIN theo chính sách?
12. Cache-Control private endpoints có no-store?
13. CSP explicit và phù hợp API/HTML page?
14. HSTS chỉ assert trên HTTPS; có test TLS/proxy end-to-end?
15. Có phân biệt normal HTTP và HTTPS mocks?
16. Không coi X-XSS-Protection là giải pháp thay CSP?
17. Redirect status 3xx có Location đúng path và trusted host?
18. Không có open redirect qua next/returnUrl, Host/X-Forwarded-Host?
19. Sau POST, redirect có 302/303/307/308 semantics đúng?
20. OAuth2/OIDC redirect có state, PKCE, redirect_uri và issuer allowlist?
21. Browser login page public, private page chỉ authenticated?
22. CSRF tests cho unsafe methods khi có browser cookies?
23. Có kiểm tra security chain order và catch-all deny?
24. WebTestClient tests không bypass login/token flows rồi kết luận đã test authentication?
25. Có signed JWT/JWKS tests bên cạnh mockJwt authorization tests?
26. Error mapping không đổi status/headers sau khi response đã committed?
27. Có negative tests cho malformed header/invalid body/unknown route?
28. Đã chạy tests trên Gradle/JDK tương thích và trong staging với reverse proxy?

## 11. Tự kiểm tra

**1.** Spring Security reactive có tự thêm Content-Security-Policy mặc định không?

**Đáp án:** Không; ứng dụng phải cấu hình CSP phù hợp.

**2.** `X-Content-Type-Options: nosniff` có đồng nghĩa response Content-Type là JSON không?

**Đáp án:** Không. Content-Type mô tả body, nosniff cấm một số kiểu đoán MIME của browser.

**3.** Vì sao không nên assert HSTS trên mọi request HTTP local?

**Đáp án:** HSTS được thêm trên secure HTTPS responses; mock HTTP có thể đúng khi không có HSTS.

**4.** API chưa xác thực nên trả 302 hay 401?

**Đáp án:** Trong contract REST của lab, trả 401 JSON Problem; browser route mới redirect.

**5.** Token hợp lệ nhưng thiếu scope reports.read gọi /api/reports thì sao?

**Đáp án:** 403 JSON với `code=ACCESS_DENIED`.

**6.** Làm sao kiểm tra redirect không sang domain attacker?

**Đáp án:** Parse Location bằng URI, assert path/host/origin allowlist, test untrusted next parameter.

**7.** Vì sao JSONPath ít brittle hơn so nguyên chuỗi JSON?

**Đáp án:** JSON fields không có thứ tự ngữ nghĩa; JSONPath kiểm tra keys/values đúng contract.

**8.** Tại sao @RestControllerAdvice không đủ cho 401/403 từ Spring Security?

**Đáp án:** Security filters có thể từ chối request trước controller; cần ServerAuthenticationEntryPoint/ServerAccessDeniedHandler.

**9.** Có nên echo exception.getMessage() vào detail?

**Đáp án:** Không mặc định, vì có thể chứa credentials/SQL/internal implementation; dùng generic safe messages.

**10.** `mockJwt()` đã test chữ ký/aud/issuer chưa?

**Đáp án:** Chưa. Nó giúp test authorization; signature/decoder phải test bằng signed JWT/JWKS riêng.

**11.** Trang browser chưa login chuyển hướng, test chỉ is3xxRedirection đủ chưa?

**Đáp án:** Chưa. Phải assert Location hợp lệ và không bị open redirect.

**12.** Nếu ứng dụng dùng browser cookies, có thể copy csrf.disable() của API không?

**Đáp án:** Không. Cần CSRF protection cho unsafe methods theo threat model cookie/session.

**13.** RFC 9457 Problem Details có cho phép field code tùy biến không?

**Đáp án:** Có, dưới dạng extension member có contract riêng của ứng dụng.

**14.** Vì sao 401 với Bearer nên test WWW-Authenticate?

**Đáp án:** Vì đó là authentication challenge giúp client hiểu scheme/error; custom JSON handler không nên bỏ các yêu cầu protocol.

## Tài liệu tham khảo

- Spring Security 6.5 — **Reactive Security HTTP Response Headers**: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html
- Spring Security — **Default security headers, HTTPS-only HSTS**: https://docs.spring.io/spring-security/reference/6.5/features/exploits/headers.html
- Spring Security 6.5 — **Reactive Testing Authentication với WebTestClient/mutateWith**: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security 6.5 — **Reactive Testing JWT bằng mockJwt**: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security 6.5 — **ServerHttpSecurity** and exception handling: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security 6.5 — **RedirectServerAuthenticationEntryPoint** Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/RedirectServerAuthenticationEntryPoint.html
- Spring Security 6.5 — **JWT Resource Server WebFlux**: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Framework — **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — **Error Responses / Problem Details**: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
- RFC 9457 — **Problem Details for HTTP APIs**: https://www.rfc-editor.org/rfc/rfc9457
- RFC 6750 — **OAuth 2.0 Bearer Token Usage**: https://www.rfc-editor.org/rfc/rfc6750
- OWASP — **HTTP Headers Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html
- OWASP — **Unvalidated Redirects and Forwards Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html
