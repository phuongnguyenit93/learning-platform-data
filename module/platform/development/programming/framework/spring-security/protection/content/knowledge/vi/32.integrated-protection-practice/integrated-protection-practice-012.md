# Hoàn thiện bộ kiểm thử giả lập, HTTP thực và trình duyệt

## 1. Bối cảnh và mục tiêu thực hành

Trong học phần **Thực hành tổng hợp** của mô-đun **SPRING_SECURITY_HTTP_PROTECTION**, nhiệm vụ cuối cùng là xây dựng một bộ kiểm thử có thể xác nhận các lớp phòng vệ HTTP và trình duyệt đang hoạt động đúng trên hệ thống dùng **Spring Security**. Những lớp cần bao phủ gồm CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, session/cookie và kiểm soát truy cập, trên cả Servlet lẫn Reactive.

Một phép thử MockMvc trả `403 Forbidden` là bằng chứng rằng một request bị từ chối trong môi trường giả lập. Nó **chưa** chứng minh reverse proxy chuyển header đúng, trình duyệt chặn inline script hoặc cookie thực nhận có `Secure`. Ngược lại, trình duyệt báo “blocked by CORS” cũng **chưa** chứng minh dữ liệu phía server không bị thay đổi.

Bài thực hành sử dụng **ba tầng kiểm chứng bổ sung cho nhau**:

1. **Giả lập trong tiến trình ứng dụng:** MockMvc cho Servlet và WebTestClient gắn với ApplicationContext cho WebFlux. Tập trung vào filter chain, authentication, authorization, CSRF, CORS và security headers trong môi trường test.
2. **HTTP thực qua cổng mạng:** client gửi request tới ứng dụng đang chạy qua HTTP server, TLS terminator hoặc reverse proxy. Tập trung vào session/cookie, header ở response cuối cùng, URL normalization, forwarding và những sai lệch tích hợp.
3. **Trình duyệt thực:** Playwright hoặc một trình duyệt được điều khiển tương đương. Tập trung vào CSP, HSTS, CORS do browser thực thi, iframe, hành vi cookie và hành trình người dùng.

Mục tiêu đầu ra là **một bộ test tái lập được** có cả luồng hợp lệ và luồng tấn công giả lập, bảng độ bao phủ, bằng chứng hành vi, tiêu chí PASS/FAIL rõ ràng và cách phân tích lỗi khi ba tầng không thống nhất.

> Tất cả địa chỉ `*.example.test` và endpoint dưới đây đều là dữ liệu minh họa. Chạy phép thử trên môi trường staging hoặc fixture được phép kiểm thử, với tài khoản và dữ liệu thử nghiệm. Không coi kết quả kỳ vọng trong tài liệu là kết quả thực tế của hệ thống chưa chạy.

## 2. Chọn hệ thống mẫu và làm rõ ranh giới bảo vệ

Giả sử hệ thống có hai ứng dụng:

- **Portal Servlet** tại `https://portal.example.test` dùng Spring MVC, form login và session cookie `JSESSIONID`. Các route: `GET /login`, `GET /dashboard`, `POST /settings/email`, `POST /logout` và `GET /admin`. Sau khi cập nhật email hợp lệ, endpoint trả `204 No Content`.
- **API Reactive** tại `https://api.example.test` dùng Spring WebFlux, xác thực bằng bearer JWT. `GET /api/me` yêu cầu scope `profile:read`. JavaScript trên `https://portal.example.test` được phép gọi API bằng header `Authorization` thông qua cấu hình CORS chính xác.
- **Reverse proxy** ở ranh giới công khai kết thúc HTTPS và chuyển request tới ứng dụng; nó có thể thay đổi `Host`, `X-Forwarded-Proto`, response headers và cookie.
- **Tài nguyên frontend:** các tệp `/js/app.js`, `/css/app.css`; tùy triển khai có thể thêm một SDK từ CDN đã phê duyệt.

Đối với portal, CSRF là yêu cầu quan trọng do trình duyệt có thể tự đính kèm session cookie. Đối với API chỉ nhận bearer token mà JavaScript tự thêm vào `Authorization`, việc dùng CSRF phụ thuộc xác thực thực tế: **chỉ cân nhắc bỏ CSRF khi chắc chắn không có cookie, HTTP Basic hoặc credential tự gửi khác được dùng để xác thực đường đi đó**.

~~~mermaid
flowchart LR
    M["MockMvc / WebTestClient<br/>giả lập"]
    H["HTTP client<br/>request qua mạng"]
    B["Trình duyệt thực<br/>Playwright"]
    F["Spring Security chain"]
    P["Reverse proxy / TLS"]
    S["Session, API, dữ liệu"]
    R["Báo cáo bằng chứng"]

    M --> F
    H --> P --> F
    B --> P
    F --> S
    M --> R
    H --> R
    B --> R
~~~

Ba tầng khác nhau ở điểm **phần mềm nào thật sự tham gia**. MockMvc không mô phỏng đầy đủ TLS, Servlet container và reverse proxy; WebTestClient khi bind vào ApplicationContext không kiểm thử network socket; client HTTP thường không thực thi CSP/CORS như browser; Playwright kiểm chứng browser nhưng không thay thế test quyền truy cập server trực tiếp.

### 2.1. Các giả thuyết cần bác bỏ bằng kiểm thử

| Mã | Mối nguy | Hành vi an toàn cần chứng minh |
|---|---|---|
| T01 | POST đổi email dùng session nhưng thiếu/sai CSRF token | Không thay đổi dữ liệu; token hợp lệ của đúng phiên hoạt động |
| T02 | Origin lạ yêu cầu API có CORS | Không cấp quyền đọc response; origin hợp lệ nhận đúng CORS headers |
| T03 | Trang thực thi script được chèn hoặc script từ origin lạ | CSP enforced chặn đúng payload, script hợp lệ vẫn chạy |
| T04 | Trang admin bị nhúng vào frame của website khác | Browser từ chối render frame theo `frame-ancestors`/X-Frame-Options |
| T05 | Cấu hình HTTPS/HSTS không tới browser | Response HTTPS cuối cùng có chính sách, kiểm tra redirect và hành vi browser |
| T06 | Cookie session thiếu thuộc tính an toàn, ID không được thay khi login | Cookie có thuộc tính mong đợi; session fixation protection hoạt động |
| T07 | Logout xong session cũ vẫn truy cập được dữ liệu | Session cũ không còn xác thực được |
| T08 | Path bất thường vượt qua bộ lọc hoặc matcher | Request bị từ chối hoặc không đến nội dung nhạy cảm |
| T09 | API Reactive cho truy cập khi thiếu token/thiếu quyền | 401/403 phù hợp; token đúng scope truy cập thành công |
| T10 | Header/proxy ở các route hoặc mã trạng thái khác nhau bị lệch | Đánh giá header của response cuối cùng trên HTML thường, lỗi, đăng nhập, redirect |

**Nguyên tắc oracle:** mỗi phép thử cần định nghĩa trước điều kiện đầu vào, request, tác động lên trạng thái hệ thống, response kỳ vọng và bằng chứng quan sát. “Trả 403” một mình không đủ để phân biệt CSRF, authorization, firewall hoặc một lỗi tầng proxy.

## 3. Chia hợp lý trách nhiệm giữa ba tầng kiểm thử

| Hành vi | Giả lập MockMvc/WebTestClient | HTTP thực | Trình duyệt thực |
|---|---|---|---|
| Thiếu CSRF token | **Chính:** kiểm tra 403 và dữ liệu không đổi | **Bổ sung:** token/cookie thật qua network | **Bổ sung:** form được render, token được gửi |
| Phân quyền và JWT | **Chính:** quyền trên chain | **Chính:** chữ ký, issuer/audience, token thật | Kiểm tra hành trình đăng nhập/gọi API |
| CORS preflight | Kiểm tra cấu hình filter | Xem status/header sau proxy | **Chính:** browser có thể/không thể đọc response |
| CSP và inline script | Xác nhận header có policy dự kiến | Xem policy cuối cùng | **Chính:** script bị chặn/thực thi |
| Clickjacking | Xác nhận header | Kiểm tra header sau proxy | **Chính:** iframe không render |
| HSTS | Kiểm tra chỉ trên request `secure(true)` | Kiểm tra header và redirect | Kiểm chứng ghi nhớ policy trong browser |
| Cookie `Secure`/`HttpOnly`/`SameSite` | Kiểm tra `Set-Cookie` trong test | Xem cookie sau proxy | **Chính:** cookie được lưu/gửi theo policy |
| Session rotation/logout | Test state/filter | Kiểm tra credential thật còn dùng được không | Kiểm tra chu trình đăng nhập/đăng xuất |
| HTTP firewall/path encoding | Kiểm tra matcher, rejection sơ bộ | **Chính:** path qua proxy và server thực | Bổ sung với navigation/browser |
| Header trên trang lỗi, redirect | Test một số route | **Chính:** response cuối cùng từng route | Xác nhận khi người dùng gặp lỗi |

Không nhất thiết phải nhân mọi test lên cả ba tầng. Tốt hơn là có một **nguồn bằng chứng chính** cho mỗi hành vi và một kiểm tra chéo tại ranh giới có nguy cơ sai lệch.

## 4. Chuẩn bị môi trường, fixture và dữ liệu kiểm thử

### 4.1. Định nghĩa hợp đồng có thể kiểm tra

Trước khi viết test, thống nhất hợp đồng của ứng dụng mẫu:

| Endpoint | Điều kiện hợp lệ | Kết quả chuẩn |
|---|---|---|
| `GET /login` | Chưa đăng nhập vẫn được xem | HTTP 200, form login |
| `GET /dashboard` | Đăng nhập bằng session | HTTP 200, CSP đúng |
| `POST /settings/email` | Session hợp lệ, CSRF token hợp lệ, email hợp lệ | HTTP 204, email được cập nhật |
| `GET /admin` | Session mang quyền ADMIN | HTTP 200 |
| `POST /logout` | Session và CSRF token hợp lệ | Invalidate session, redirect theo thiết kế |
| `GET /api/me` | JWT hợp lệ có `SCOPE_profile:read` | HTTP 200, dữ liệu đúng subject |
| `GET /api/me` | Không có JWT | HTTP 401 |
| `GET /api/me` | JWT hợp lệ thiếu scope | HTTP 403 |

Nếu ứng dụng thật dùng 200/302 thay cho 204 hoặc tên scope khác, cập nhật oracle theo hợp đồng thực tế. Không chỉnh code server chỉ để chiều theo một assertion mẫu thiếu căn cứ.

### 4.2. Cấu hình fixture

Chuẩn bị:

1. Tài khoản người dùng thường `learner`, tài khoản quản trị `admin-test` và người dùng thứ hai để phát hiện truy cập chéo dữ liệu.
2. Bản ghi email ban đầu có thể đọc lại sau POST; test âm tính phải xác minh **không có side effect**, không chỉ kiểm tra status.
3. Một trang fixture chỉ có trên staging, ví dụ `/test-fixtures/csp-inline`, chứa **một inline script do nhóm kiểm thử chủ động đặt** để xác nhận CSP chặn; response fixture phải dùng cùng chính sách CSP với HTML thật.
4. Một website fixture khác origin, ví dụ `https://attacker.example.test`, có iframe và form gửi sang portal.
5. Một origin hợp lệ trong cấu hình CORS: `https://portal.example.test`. Mọi request từ `https://attacker.example.test` là negative case.
6. TLS certificate hợp lệ trong môi trường chạy, đường đi qua proxy và một biến thể request từ client trực tiếp tới ứng dụng nếu cần so sánh.

**Cách ly:** không dùng tài khoản thật, xóa dữ liệu test sau kiểm thử; ghi phiên bản build, revision cấu hình, browser và loại triển khai (Servlet hay Reactive). Test tự động phải độc lập: reset dữ liệu hoặc transaction ở đúng nơi, không phụ thuộc trạng thái test chạy trước đó.

### 4.3. Phụ thuộc kiểm thử

Với Spring Boot, hai nhóm dependency phổ biến là `spring-boot-starter-test` và `spring-security-test`, theo phiên bản tương thích với ứng dụng. WebTestClient cần các thành phần reactive test tương ứng, Playwright cần runtime trình duyệt và cấu hình test riêng. Các đoạn code sau minh họa API của Spring Security thế hệ cấu hình `SecurityFilterChain`/`SecurityWebFilterChain`; kiểm tra import, package và starter theo version đang dùng.

Không cài thêm dependency chỉ để che phủ một phần hành vi đã có test tương đương; ưu tiên những trường hợp tăng khả năng phát hiện lỗi thực sự.

## 5. Tầng 1 — MockMvc: kiểm thử Spring Security Servlet

### 5.1. Cấu hình mẫu để hiểu đường đi kiểm thử

Một security chain Servlet minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class PortalSecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/js/**", "/css/**", "/error").permitAll()
                .requestMatchers("/admin", "/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; " +
                    "script-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "frame-ancestors 'none'"
                ))
                .frameOptions(frame -> frame.deny())
            );

        return http.build();
    }
}
~~~

Đây là một chain ví dụ. Spring Security có thể phát một số header mặc định, nhưng **CSP phải được chỉ định theo ứng dụng**. Nếu thực tế có nhiều `SecurityFilterChain`, cần kiểm tra thứ tự chain và `securityMatcher`: request chỉ vào chain đầu tiên khớp. Không thể kết luận route đã bảo vệ chỉ vì một bean cấu hình có tồn tại.

### 5.2. Kiểm tra âm tính và dương tính cho CSRF

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfServletTest {

    @Autowired MockMvc mvc;

    @Test
    void signedInUserCannotPostWithoutCsrf() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("learner").roles("USER"))
                .param("email", "new@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void signedInUserCannotPostWithInvalidCsrf() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("learner").roles("USER"))
                .with(csrf().useInvalidToken())
                .param("email", "new@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void signedInUserCanPostWithValidCsrf() throws Exception {
        mvc.perform(post("/settings/email")
                .with(user("learner").roles("USER"))
                .with(csrf())
                .param("email", "new@example.test"))
            .andExpect(status().isNoContent());
    }
}
~~~

Trong ví dụ, `POST /settings/email` được giả định trả 204. Khi đưa vào dự án thật, phải xác nhận cách gửi dữ liệu của controller, cơ chế validation, quyền và kết quả HTTP cụ thể.

**Phần kiểm thử không được thiếu:** lấy email trước/sau từ repository hoặc test double có ý nghĩa để khẳng định hai trường hợp bị từ chối **không thay đổi dữ liệu** và trường hợp token hợp lệ **đã thay đổi đúng**. Cần reset dữ liệu giữa các test. Nếu chỉ nhìn status 403, request có thể đã bị chặn vì thiếu đăng nhập, thiếu role hoặc lỗi khác, làm test âm tính trở nên vô nghĩa.

`with(user(...))` tạo authentication cho MockMvc; nó **không mô phỏng đầy đủ cookie/session được browser tạo khi login thật**. `with(csrf())` cung cấp CSRF token phù hợp với test để thử cơ chế bảo vệ; cần thêm test HTTP/browser xác nhận form thật có token và cookie đúng.

### 5.3. Kiểm tra authorization và headers

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PortalHeadersAndAccessTest {

    @Autowired MockMvc mvc;

    @Test
    void ordinaryUserCannotReadAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(user("learner").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void dashboardHasCspAndFrameProtection() throws Exception {
        mvc.perform(get("/dashboard")
                .with(user("learner").roles("USER"))
                .secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("frame-ancestors 'none'")))
            .andExpect(header().string("X-Frame-Options", "DENY"));
    }

    @Test
    void secureLoginResponseHasHsts() throws Exception {
        mvc.perform(get("/login").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().exists("Strict-Transport-Security"));
    }
}
~~~

Trong một request MockMvc, `secure(true)` đánh dấu request là HTTPS cho chain xử lý. Nó không thiết lập TLS connection thật. HSTS thường được Spring Security phát trên secure response theo cấu hình và mặc định liên quan; việc kiểm tra header ở MockMvc chỉ chứng minh tầng filter đã phát header trong điều kiện giả lập.

Lưu ý: khi MVC redirect hoặc view xử lý có thể trả trạng thái khác với ví dụ, phải điều chỉnh test theo hợp đồng. Không dùng `status().isOk()` như cách phổ quát cho mọi route đăng nhập/đăng xuất.

### 5.4. Dấu hiệu một MockMvc test đang tạo cảm giác an toàn giả

| Dấu hiệu | Vì sao chưa đủ | Cách bổ sung |
|---|---|---|
| Tất cả test dùng `@WithMockUser` hoặc `with(user(...))` | Bỏ qua login thật, cookie rotation và logout | Test HTTP/browser với session do server tạo |
| Chỉ kiểm tra response 403 | Chưa xác nhận nguyên nhân từ chối và dữ liệu không thay đổi | Kiểm tra principal/route, log và trạng thái dữ liệu |
| Chỉ chạy `GET /dashboard` | Không bao phủ route login, error, admin và redirect | Ma trận URL + response code thực tế |
| Thấy CSP trong header là đánh dấu PASS XSS | MockMvc không thực thi JavaScript | Test trên browser với fixture có inline script |
| Test HSTS dùng `secure(true)` | Không kiểm tra TLS/cấu hình proxy | Curl HTTPS qua edge và browser |
| Path bất thường bị block trong MockMvc | Servlet container/proxy có thể chuẩn hóa URL theo cách khác | Gửi raw HTTP bằng `--path-as-is` qua proxy |

## 6. Tầng 1 — WebTestClient: kiểm thử Spring Security Reactive

### 6.1. Một `SecurityWebFilterChain` cho bearer API

Ví dụ cho API **chỉ dùng bearer JWT**, không có session cookie xác thực:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.http.HttpMethod;

@Bean
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/me")
                .hasAuthority("SCOPE_profile:read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()))
        .csrf(csrf -> csrf.disable())
        .cors(Customizer.withDefaults())
        .build();
}
~~~

Việc `csrf(...disable())` chỉ phù hợp với giả định bearer-only. Với WebFlux có login form hoặc xác thực thông qua cookie, cần đánh giá lại CSRF và test token như Servlet; không suy rộng quy tắc “API là stateless nên tắt CSRF” cho mọi API.

Nếu CORS được bật qua `cors(Customizer.withDefaults())`, ứng dụng cần một cấu hình CORS đúng. Ví dụ dưới đây sử dụng type của **Reactive**, không dùng `UrlBasedCorsConfigurationSource` thuộc Servlet:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(
        List.of("https://portal.example.test"));
    config.setAllowedMethods(List.of("GET", "OPTIONS"));
    config.setAllowedHeaders(
        List.of("Authorization", "Content-Type"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Với bearer header tự đính kèm và không dùng cookie cross-origin, ví dụ không bật `allowCredentials(true)`. Nếu thực tế có yêu cầu gửi cookie, cần thiết kế riêng, tránh `Access-Control-Allow-Origin: *` với credentials và xem xét CSRF.

### 6.2. WebTestClient bind vào ApplicationContext

Ở tầng giả lập, WebTestClient có thể gắn trực tiếp vào Spring ApplicationContext với cấu hình Spring Security test:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ApiReactiveSecurityTest {

    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void withoutTokenIsRejected() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void tokenWithoutScopeIsForbidden() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_other")))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tokenWithRequiredScopeSucceeds() {
        client.mutateWith(mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile:read")))
            .get().uri("/api/me")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

Giả định `GET /api/me` tồn tại và trả 200 khi authorized. `mockJwt()` giúp kiểm thử **quyết định phân quyền** trong Spring Security; nó **không chứng minh JWT được ký đúng, issuer/audience hợp lệ hoặc token hết hạn bị từ chối**. Những mục này phải có integration test với decoder hoặc request bearer thật qua HTTP network.

### 6.3. Kiểm tra CORS ở tầng giả lập

Với bean CORS ở mục trước, có thể kiểm tra riêng preflight:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

// client đã được cấu hình như mục 6.2.
@Test
void allowedOriginReceivesCorsHeader() {
    client.options().uri("/api/me")
        .header(HttpHeaders.ORIGIN,
            "https://portal.example.test")
        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
        .exchange()
        .expectHeader().valueEquals(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
            "https://portal.example.test");
}

@Test
void untrustedOriginIsNotGrantedCorsAccess() {
    client.options().uri("/api/me")
        .header(HttpHeaders.ORIGIN,
            "https://attacker.example.test")
        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
        .exchange()
        .expectHeader().doesNotExist(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
}
~~~

Đây là các **method bổ sung vào class test** có trường `client`, không phải một class Java riêng. Một preflight bị từ chối có thể trả 403 hoặc response không có header cho phép tùy cấu hình; oracle quan trọng là không cấp quyền cho origin lạ.

CORS không phải biện pháp authorization. Dù origin được phép, API vẫn phải trả 401/403 nếu thiếu authentication/authorization. Một request có `Origin` tùy ý từ `curl` vẫn có thể tới server: browser mới là thành phần áp dụng cơ chế CORS cho việc đọc response của script.

## 7. Tầng 2 — Kiểm thử HTTP thật từ client ngoài tiến trình

Tầng HTTP thật cần khởi chạy app qua port HTTP(S), tốt nhất chạy đường đi giống staging:

~~~text
HTTP client
    -> DNS / HTTPS / reverse proxy
    -> Servlet container hoặc Netty
    -> Spring Security chain
    -> Controller/Handler
    -> Data store
~~~

Công cụ minh họa là `curl`; trên Windows PowerShell nên gọi `curl.exe` để tránh alias của `curl` trong một số bản PowerShell. Những lệnh dưới đây viết theo cú pháp curl phổ thông, dùng địa chỉ của môi trường kiểm thử, và **không** thêm `-k/--insecure` vì bỏ qua xác minh TLS sẽ làm sai ý nghĩa bài kiểm tra HTTPS.

### 7.1. Quan sát HTTPS response và headers cuối cùng

~~~bash
curl -sS -D - -o /dev/null \
  "https://portal.example.test/login"
~~~

Ở output, kiểm tra:

- `Content-Security-Policy` hoặc `Content-Security-Policy-Report-Only`: **phân biệt** Enforce với chế độ chỉ ghi nhận; chỉ Enforce chặn hành vi.
- `Strict-Transport-Security`: xuất hiện trên HTTPS response, kiểm tra `max-age`, `includeSubDomains` và thời điểm rollout theo chính sách.
- `X-Content-Type-Options: nosniff`, `X-Frame-Options` nếu dùng, `Referrer-Policy`, `Cache-Control`: so với yêu cầu hệ thống.
- `Set-Cookie`: chỉ kiểm tra khi endpoint thực sự phát cookie; nhiều trang GET sẽ không sinh session mới.
- `Location` trong response redirect: xác minh scheme/host đúng sau reverse proxy.

Với `/dashboard` đang bảo vệ bằng login, request không có cookie có thể nhận 302 hoặc 401; nó **không** chứng minh header của trang dashboard đã được phát. Cần dùng phiên đăng nhập thật khi kiểm tra response 200 của trang đó.

Nếu nhiều CSP header cùng tồn tại, browser áp dụng đồng thời các policy enforced; một policy khác chặt hơn có thể làm script bị chặn dù bạn đã cho phép trong policy do ứng dụng phát. Kiểm tra response cuối cùng sau proxy, không chỉ bean Spring.

### 7.2. Kiểm tra CORS preflight qua mạng

Origin hợp lệ:

~~~bash
curl -sS -i -X OPTIONS \
  "https://api.example.test/api/me" \
  -H "Origin: https://portal.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
~~~

Origin không hợp lệ:

~~~bash
curl -sS -i -X OPTIONS \
  "https://api.example.test/api/me" \
  -H "Origin: https://attacker.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
~~~

Kiểm tra origin hợp lệ được cấp `Access-Control-Allow-Origin: https://portal.example.test` và các method/header cần thiết; origin lạ không được cấp header cho phép. Khi request thực tế cần bearer token, endpoint vẫn phải kiểm tra token. Kiểm tra thêm preflight có được xử lý **trước** kiểm tra authentication khi cấu hình CORS yêu cầu, vì preflight không mang bearer token.

**Giới hạn:** curl chỉ xem response HTTP. Muốn chứng minh browser không cho JavaScript ở origin lạ đọc response, phải thực hiện thêm test trình duyệt. Một form POST đơn giản có thể được gửi mà không phụ thuộc quyền đọc response; CORS không thay thế CSRF.

### 7.3. Kiểm tra CSRF bằng cookie và token thật

Đối với portal sử dụng form login, cần kiểm thử một chuỗi HTTP **cùng phiên**:

1. GET `/login`, lưu cookie jar và trích CSRF token do server gửi trong form hoặc endpoint phù hợp.
2. POST login bằng tài khoản thử nghiệm, cookie jar và CSRF token hợp lệ; xác minh login thành công.
3. POST `/settings/email` khi đã đăng nhập nhưng **thiếu CSRF token**, vẫn gửi cookie đúng.
4. Kiểm tra response bị từ chối và email **không đổi**.
5. POST tương tự với token hợp lệ từ đúng phiên, kiểm tra email đổi thành công.
6. Lấy token của phiên khác hoặc thay token bằng giá trị sai, kiểm tra bị từ chối.
7. Logout và replay cookie cũ vào route bảo vệ, kiểm tra không được truy cập.

Có thể dùng `curl --cookie-jar`, `--cookie` và `--data-urlencode`, nhưng cách lấy token phụ thuộc mẫu form (hidden input, header, cookie repository, v.v.). Không sao chép giá trị token hay mật khẩu thật vào tài liệu hoặc log. Nếu CSRF token được lưu theo cơ chế deferred hoặc request handler tùy biến, phải đi theo luồng thật thay vì giả định luôn có input tên `_csrf`.

**Không làm sai mục đích test:** một POST chưa đăng nhập bị 403 không chứng minh CSRF đang ngăn thay đổi dữ liệu của người đã đăng nhập. Trạng thái xác thực và quyền phải được xác minh trước khi tiến hành negative test.

### 7.4. Kiểm tra URL và HTTP firewall qua proxy

Để phát hiện sai khác ở các tầng URL normalization, gửi một số request được chuẩn bị kỹ tới route hạn chế quyền, ví dụ các biến thể có dấu chấm phẩy, path segment lặp, URL-encoded slash hoặc double encoding, bên cạnh URL chuẩn.

~~~bash
curl --path-as-is -i \
  "https://portal.example.test/admin/..;/dashboard"
~~~

Ví dụ này chỉ là một case thử hành vi với path bất thường, **không mặc định** tất cả máy chủ sẽ trả cùng mã status. Một triển khai có thể trả 400/403, proxy có thể từ chối, hoặc ứng dụng có thể normalize trước khi matcher xử lý. Oracle phải kiểm tra **không bypass authorization và không lộ nội dung cần quyền**.

So sánh request nhận ở proxy (nếu có log được phép xem) và handler/controller thực sự xử lý. Một test chỉ ghi “HTTP 404” nhưng request vẫn tới handler nhạy cảm có thể bỏ sót lỗi. Cần giữ header `Host`, scheme, encoded path và phương thức trong phạm vi dữ liệu log được phép thu thập.

## 8. Tầng 3 — Kiểm thử trình duyệt với Playwright

Tầng browser đặc biệt quan trọng với CSP, CORS, HSTS và iframe. Ví dụ dưới đây dùng Playwright Test với TypeScript. Cấu hình `baseURL` đến portal staging, các tài khoản test được tạo qua fixture và không hardcode mật khẩu vào repository.

### 8.1. Thiết lập kiểm thử browser

Ví dụ cấu hình tối thiểu:

~~~ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  use: {
    baseURL: 'https://portal.example.test',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome']
  },
  retries: 1,
  timeout: 30_000
});
~~~

Trong môi trường CI, hạn chế dữ liệu nhạy cảm trong trace và HAR; trace có thể chứa HTML, cookie hoặc thông tin request. Chạy test với dữ liệu dùng riêng cho automation và kiểm soát thời gian lưu artifact.

### 8.2. Kiểm chứng CSP thực sự chặn inline script

Tạo trên staging route `/test-fixtures/csp-inline` với response HTML chịu **cùng CSP enforced** như portal. Trong HTML có một inline script không gắn nonce/hash:

~~~html
<h1>CSP fixture</h1>
<script>window.__cspProbeRan = true;</script>
<script src="/js/app.js" defer></script>
~~~

Script inline phải bị chặn, còn file `/js/app.js` thuộc `'self'` được phép tải. Trước khi tải trang, Playwright cài listener để nhận event vi phạm CSP:

~~~ts
import { test, expect } from '@playwright/test';

test('CSP chặn inline script trên HTML thật', async ({ page }) => {
  await page.addInitScript(() => {
    (window as any).__violations = [];
    document.addEventListener('securitypolicyviolation', (event) => {
      (window as any).__violations.push(event.effectiveDirective);
    });
  });

  await page.goto('/test-fixtures/csp-inline');

  const result = await page.evaluate(() => ({
    ran: Boolean((window as any).__cspProbeRan),
    directives: (window as any).__violations as string[]
  }));

  expect(result.ran).toBe(false);
  expect(result.directives.some((name) =>
    name.startsWith('script-src'))).toBe(true);
});
~~~

Cần đảm bảo fixture không có script khác vô tình đặt `__cspProbeRan`. Một số kiểm thử chạy qua `innerHTML` sẽ không làm script thực thi **ngay cả khi không có CSP**; vì vậy không dùng cách chèn script bằng `innerHTML` làm phép thử duy nhất. Fixture phải chứa script ngay trong HTML browser parse để nhận biết rõ cơ chế bị chặn.

Nếu chính sách dùng CSP nonce/hash, fixture phải có script **không được cấp nonce/hash**, còn script hợp lệ có nonce hoặc hash đúng để kiểm chứng chiều dương tính. Nếu CSP chỉ ở `Report-Only`, script có thể chạy dù event violation xuất hiện: bài test bắt buộc xác minh header **Enforce**.

### 8.3. Kiểm chứng clickjacking bằng iframe

Tạo một trang fixture tại `https://attacker.example.test/frame-check`:

~~~html
<h1>External origin</h1>
<iframe
  src="https://portal.example.test/admin"
  title="admin-iframe">
</iframe>
~~~

Khi browser mở trang này, CSP `frame-ancestors 'none'` hoặc `X-Frame-Options: DENY` phải ngăn tài liệu quản trị hiển thị trong iframe. Ở DevTools/Playwright có thể ghi nhận thông báo từ chối framing và xác minh nội dung nhạy cảm không xuất hiện trong frame.

**Đừng chỉ mong iframe element biến mất:** browser vẫn có thể giữ thẻ `<iframe>` trong DOM, nhưng không render tài liệu đích. Test phải xác nhận document đích không được tải như một frame hợp lệ và đối chiếu header trên **response của trang được nhúng**. Nếu `/admin` chuyển hướng sang `/login` vì chưa đăng nhập, cũng phải kiểm tra kịch bản với phiên đã xác thực, tránh chỉ chứng minh trang login không cho nhúng.

### 8.4. Kiểm chứng cookie và session thật

Trong browser context đã đăng nhập bằng tài khoản fixture:

~~~ts
import { test, expect } from '@playwright/test';

test('session cookie có thuộc tính dự kiến', async ({ page }) => {
  // Bước đăng nhập phải được thực hiện bằng fixture/hàm login
  // thực tế trước assertion dưới đây.

  const cookies = await page.context().cookies(
    'https://portal.example.test');
  const session = cookies.find((cookie) =>
    cookie.name === 'JSESSIONID');

  expect(session).toBeDefined();
  expect(session?.secure).toBe(true);
  expect(session?.httpOnly).toBe(true);
  expect(session?.sameSite).toBe('Lax');
});
~~~

Tên cookie và chính sách `SameSite` phụ thuộc triển khai thực tế; trước khi coi là FAIL, kiểm tra requirement và việc cookie thực sự được tạo trong phiên test. Để kiểm tra rotation, ghi nhận nhãn định danh phiên trước login khi session đã tồn tại, đăng nhập thật, so sánh ID sau login, rồi logout và thử gọi route được bảo vệ với cookie cũ.

Không lưu giá trị cookie nguyên bản vào screenshot, CI log hay commit. Playwright `storageState` có thể chứa session token; phải quản lý như bí mật, không chia sẻ công khai.

### 8.5. Kiểm chứng CORS từ ngữ cảnh cross-origin

Đưa test browser tới `https://attacker.example.test` rồi thử `fetch` sang API:

~~~ts
import { test, expect } from '@playwright/test';

test('origin lạ không đọc được API qua fetch', async ({ page }) => {
  await page.goto('https://attacker.example.test/cors-check');

  const outcome = await page.evaluate(async () => {
    try {
      await fetch('https://api.example.test/api/me', {
        method: 'GET',
        credentials: 'omit',
        headers: { Authorization: 'Bearer invalid-test-token' }
      });
      return 'resolved';
    } catch {
      return 'rejected';
    }
  });

  expect(outcome).toBe('rejected');
});
~~~

Ở đây header `Authorization` kích hoạt preflight trong trường hợp bình thường; origin lạ phải bị CORS chặn. **Điểm cần điều chỉnh để phép thử có ý nghĩa:** API phải chắc chắn không trả CORS allow-origin cho origin này. Một response không CORS sẽ làm `fetch` bị reject, nhưng cũng có thể reject vì network/TLS; do đó phải thu DevTools/Network evidence để phân biệt nguyên nhân.

Để kiểm tra **origin hợp lệ**, vào `https://portal.example.test` và gọi API bằng bearer token hợp lệ của tài khoản test. Quan sát preflight nếu có, response trả 200 và nội dung hợp lệ. Test origin lạ với token giả không chứng minh API giữ bí mật với **token hợp lệ**; muốn kiểm tra ranh giới CORS độc lập với authentication, dùng token test hợp lệ trong môi trường staging được quản lý chặt chẽ, và kiểm tra status/header trên server song song. Không suy luận “CORS chặn đọc” thành “server không xử lý request”.

### 8.6. HSTS và hành vi trình duyệt

Kiểm tra riêng hai yêu cầu:

- **Cấp phát:** HTTPS document response cuối cùng có `Strict-Transport-Security` với `max-age` theo chính sách, không bị proxy bỏ header.
- **Áp dụng:** sau khi browser đã ghi nhớ HSTS policy cho host test, yêu cầu truy cập `http://portal.example.test` được nâng lên HTTPS theo hành vi của trình duyệt.

Browser chỉ chấp nhận HSTS từ HTTPS hợp lệ, và **lần truy cập HTTP đầu tiên trước khi ghi nhớ HSTS** vẫn cần được edge xử lý an toàn. HSTS preload là một quyết định triển khai riêng, không được suy luận từ một test redirect.

Không xóa hoặc thay đổi HSTS state trên browser profile dùng chung. Mỗi lần chạy integration/browser test nên có context/profile test riêng; xác nhận cách runner quản lý profile trước khi viết assertion dựa trên trạng thái HSTS lưu lâu dài.

## 9. Ma trận hoàn chỉnh: test ID, tầng, oracle và bằng chứng

| Test ID | Kiểm tra | Tầng chính | Kết quả kỳ vọng | Bằng chứng |
|---|---|---|---|---|
| M01 | POST có session mock nhưng thiếu CSRF | MockMvc | 403, dữ liệu không đổi | Assertion + repository snapshot |
| M02 | POST sai CSRF token | MockMvc | 403, dữ liệu không đổi | Assertion + repository snapshot |
| M03 | POST token đúng | MockMvc | 204, dữ liệu cập nhật | HTTP + repository snapshot |
| M04 | User thường gọi `/admin` | MockMvc | 403 | Status + quyền sử dụng |
| M05 | HTTPS giả lập nhận CSP/HSTS | MockMvc | Header hiện diện đúng | Assertion header |
| M06 | Reactive API thiếu JWT | WebTestClient | 401 | Test assertion |
| M07 | JWT mock thiếu scope | WebTestClient | 403 | Test assertion |
| M08 | JWT mock đúng scope | WebTestClient | 200 | Test assertion + response đúng subject |
| M09 | Preflight origin lạ | WebTestClient | Không cấp CORS allow-origin | Preflight assertion |
| M10 | Preflight origin hợp lệ | WebTestClient | Allow-origin đúng | Preflight assertion |
| H01 | HTTPS HTML qua reverse proxy | HTTP thực | CSP/HSTS/cookie/header đúng | Raw response sau proxy |
| H02 | Login session và thay email thiếu CSRF token | HTTP thực | Từ chối, không đổi dữ liệu | Cookie jar đã che + dữ liệu trước/sau |
| H03 | Login và thay email token hợp lệ | HTTP thực | Thành công | HTTP + dữ liệu |
| H04 | Preflight cả hai origin | HTTP thực | Quyết định CORS đúng | Hai raw response |
| H05 | Path encoding bất thường | HTTP thực | Không bypass quyền | Status + log route |
| H06 | Logout rồi dùng session cũ | HTTP thực | Không truy cập nội dung bảo vệ | HTTP trước/sau |
| H07 | JWT thật thiếu/sai chữ ký/hết hạn/sai quyền | HTTP thực | Bị từ chối theo từng loại | Decoder/API status + log an toàn |
| B01 | Inline script bị CSP chặn | Browser | Không chạy, ghi nhận violation | Playwright + Console |
| B02 | Script hợp lệ chạy bình thường | Browser | Chạy không tạo vi phạm ngoài dự kiến | Browser/network |
| B03 | Trang admin trong iframe khác origin | Browser | Document đích không render | Console + frame observation |
| B04 | Cookie session và luồng login/logout | Browser | Flags, rotation, invalidation đúng | Cookie metadata + hành vi |
| B05 | Origin lạ gọi API bằng fetch | Browser | Không đọc được response qua CORS | Browser Network + Console |
| B06 | Origin hợp lệ gọi API | Browser | CORS cho phép, authz vẫn đúng | Browser Network |
| B07 | HSTS đã ghi nhớ nâng HTTP lên HTTPS | Browser | Browser nâng cấp an toàn | Browser network/state |
| B08 | Trang lỗi/redirect vẫn tuân thủ header theo yêu cầu | Browser + HTTP | Header và hành vi tương ứng | Header cuối cùng + UI |

Tập test này là gợi ý cho phạm vi học phần; khi áp dụng cần điều chỉnh theo kiến trúc, chính sách và endpoint thực tế. Không buộc mọi test phải chạy trên cả Servlet và Reactive nếu mối nguy không xuất hiện trên cả hai.

### 9.1. Điều kiện chấp nhận cho test

Mỗi test có:

- **Precondition:** trạng thái đăng nhập, quyền, dữ liệu ban đầu, origin, scheme, phiên bản ứng dụng/cấu hình.
- **Action:** HTTP method, URL, header, body hoặc thao tác browser.
- **Expected outcome:** status/headers, DOM, session, dữ liệu và lý do hành vi được bảo vệ.
- **Observed outcome:** bằng chứng thực tế, có timestamp và môi trường.
- **Verdict:** `PASS`, `FAIL`, `INCONCLUSIVE` hoặc `NOT_APPLICABLE` có giải thích.

Không đánh dấu PASS chỉ vì assertion status mong đợi nếu đó là status trả về do một điều kiện sai khác. Ví dụ, B05 `fetch` bị reject do certificate lỗi là `INCONCLUSIVE` với mục tiêu CORS, không phải PASS.

## 10. Tự động hóa theo pipeline với điểm dừng hợp lý

Một pipeline khả thi:

~~~mermaid
flowchart TD
    Commit["Commit ứng dụng và cấu hình"]
    Unit["MockMvc / WebTestClient<br/>bộ test giả lập"]
    Stage["Deploy build vào staging<br/>TLS + proxy + dữ liệu test"]
    HTTP["Test HTTP thật<br/>headers / session / firewall / JWT"]
    Browser["Playwright<br/>CSP / iframe / CORS / HSTS"]
    Report["Tổng hợp kết quả và bằng chứng"]
    Gate{"Có FAIL nghiêm trọng<br/>hoặc thiếu bằng chứng?"}
    Accept["Ứng viên được nghiệm thu"]
    Block["Chặn phát hành / điều tra"]

    Commit --> Unit --> Stage --> HTTP --> Browser --> Report --> Gate
    Gate -->|Có| Block
    Gate -->|Không| Accept
~~~

Ưu tiên chạy mock tests thường xuyên vì nhanh và gần mã nguồn. HTTP thực và browser nên chạy trên bản build đã triển khai tương đương production, trước khi release và khi thay đổi proxy, security chain, CSP, CORS, session hoặc SDK ngoài.

Những cách giảm test flakiness có căn cứ:

1. Reset fixture và dữ liệu giữa các case; tạo tài khoản/test token riêng cho từng run khi cần.
2. Tránh phụ thuộc thứ tự test, đợi theo điều kiện cụ thể (selector/network response) thay vì `sleep` cố định.
3. Cố định browser/runtime versions trong CI ở mức phù hợp và ghi lại khi nâng cấp.
4. Không gom mọi kiểm tra UI vào một test dài: khi lỗi, khó xác định CSP, CORS, authentication hay backend.
5. Tách lỗi hạ tầng (DNS, TLS, unavailable staging) khỏi FAIL an ninh; retry lỗi hạ tầng có giới hạn, ghi `INCONCLUSIVE` nếu chưa kiểm chứng được.
6. Không dùng test vượt qua TLS verification hoặc bật mọi origin CORS để làm CI xanh.

## 11. Chẩn đoán khi ba tầng cho kết quả khác nhau

| Hiện tượng | Diễn giải có thể | Kiểm tra tiếp |
|---|---|---|
| MockMvc có HSTS, curl HTTPS không có | Proxy bỏ header, response không qua chain, cấu hình edge khác | Kiểm tra raw headers ở upstream và edge, scheme forwarded |
| MockMvc có CSP, Playwright vẫn chạy inline script | Policy chỉ Report-Only, HTML route khác, policy cho inline, fixture sai | Xem response document, `Content-Security-Policy` enforced, script nguồn |
| WebTestClient CORS PASS, browser `fetch` FAIL | Preflight gửi headers khác, redirect, token/authz, TLS hoặc edge sửa CORS | Network tab + raw preflight và request thật |
| Curl từ origin lạ đọc API được, browser không đọc được | Curl không áp dụng same-origin policy/CORS | Không kết luận CORS sai từ curl đọc body; xác minh response CORS headers |
| POST thiếu token trả 403 nhưng dữ liệu đã đổi | Side effect xảy ra trước kiểm tra hoặc test sai dữ liệu | Điều tra handler/filter, transaction, event/queue và thời điểm cập nhật |
| Session flag đúng trong config, cookie browser thiếu `Secure` | TLS offload/forwarded scheme/cookie phát từ service khác | Xem `Set-Cookie` sau proxy và nguồn phát cookie |
| Mock HTTP firewall PASS, path thật qua proxy bypass | Proxy và ứng dụng giải mã path khác nhau, matcher lệch | Kiểm tra raw path và route matched qua từng tầng |
| CSP chặn SDK sau nâng cấp | SDK thêm script, iframe, kết nối hoặc origin mới | Phân loại CSP violation theo directive, đối chiếu nhà cung cấp |
| Browser login PASS, JWT integration FAIL | Test browser dùng cookie còn API giả định bearer-only | Xác minh credential thật của từng route và chain |
| Test logout PASS nhưng cookie cũ gọi API vẫn 200 | API dùng bearer token không bị invalidate khi logout portal | Định nghĩa lại phạm vi logout/revocation theo kiến trúc |

Khi điều tra, đọc kết quả theo thứ tự **đường đi thực tế → chain khớp → header cuối cùng → browser behavior → trạng thái dữ liệu**. Một kết quả tốt ở tầng trước không tự phủ định lỗi được phát hiện ở tầng sau.

### 11.1. Cách xác định chủ sở hữu lỗi

- Sai response code/authorization trong MockMvc/WebTestClient: kiểm tra chain matcher, rule phân quyền và test fixture.
- Sai headers hoặc đường dẫn khi qua HTTP thật: kiểm tra reverse proxy, app server, forwarding và khác biệt cấu hình staging.
- Sai CSP/CORS/HSTS hành vi browser: kiểm tra response tài liệu, nguồn script, preflight, browser policy và origin/credential.
- Sai trạng thái dữ liệu sau response bị từ chối: kiểm tra logic nghiệp vụ, transaction, xử lý bất đồng bộ và thứ tự áp dụng filter.

## 12. Báo cáo bằng chứng và tiêu chí hoàn thành

Một hồ sơ thực thi tối thiểu nên có:

~~~yaml
runId: "<id-cua-lan-chay>"
appRevision: "<git-commit-hoac-build-id>"
configRevision: "<revision-cau-hinh>"
environment: "staging"
browserVersion: "<neu-dung-browser>"
testId: "H02"
threatId: "T01"
description: "POST thay đổi email có session hợp lệ nhưng thiếu CSRF token"
precondition: "Đăng nhập thành công, email ban đầu đã ghi nhận"
expected:
  httpStatus: 403
  dataChanged: false
observed:
  httpStatus: "<gia-tri-quan-sat>"
  dataChanged: "<true-hoac-false>"
evidence:
  - "http-request-response-redacted.txt"
  - "test-data-before-after-redacted.txt"
verdict: "PASS|FAIL|INCONCLUSIVE"
owner: "<nguoi-phu-trach>"
residualRisk: "<gioi-han-hay-rui-ro-con-lai>"
~~~

Các placeholder cần được thay bằng **quan sát thật**. Khi lưu response, HAR, trace hoặc screenshots, phải che cookie, bearer token, CSRF token, email thật và nội dung nhạy cảm. Một HTTP transcript đã ẩn token nhưng vẫn đủ metadata để xác định loại header, request ID, phương thức và kết quả là bằng chứng phù hợp hơn việc lưu toàn bộ session secret.

### 12.1. Tiêu chí nghiệm thu thực hành

Có thể coi bộ kiểm thử đã hoàn thiện về mặt thiết kế khi:

1. Mỗi nguy cơ T01–T10 áp dụng cho hệ thống đều có ít nhất một test rõ **điều kiện âm tính**, test tương ứng cho luồng hợp lệ nếu cần, và phép đo trạng thái bên ngoài status.
2. Với CSRF, test chứng minh **request có phiên hợp lệ, thiếu/sai token bị từ chối và không thay đổi dữ liệu**; request cùng nghiệp vụ với token hợp lệ hoạt động.
3. Với CORS, có cả preflight origin hợp lệ và origin lạ ở tầng HTTP, sau đó xác nhận browser có hoặc không được đọc response; authentication/authorization vẫn được test riêng.
4. Với CSP và clickjacking, browser thật xác nhận script không được cấp phép không thực thi và tài liệu nhạy cảm không render trong frame, đồng thời tài nguyên hợp lệ vẫn chạy.
5. Với HSTS, cookie và session, có kiểm tra trên response HTTPS cuối cùng và hành vi browser/login/logout tương ứng.
6. Với HTTP firewall, có ít nhất một bộ request path bình thường và bất thường qua **proxy thực**; không có bypass phân quyền.
7. Với Reactive bearer API, có test thiếu token, thiếu quyền, đúng quyền và ít nhất một test HTTP thực cho chữ ký/hết hạn/claims theo thiết kế.
8. Báo cáo thể hiện kết quả PASS/FAIL/INCONCLUSIVE theo quan sát, định danh build/config và rủi ro còn lại. Không gộp các trường hợp chưa chạy vào PASS.

**Điểm đặc biệt cần nhớ:** không dùng tổng tỷ lệ “95% test xanh” để chấp nhận một lỗi nghiêm trọng còn mở. Một lỗ hổng CSRF trên thao tác thay đổi quyền hoặc bypass authorization phải được xử lý theo tác động của nó dù các test header còn lại đều PASS.

## 13. Bài tập cuối bài

**Bài tập A — Viết bộ kiểm thử nhỏ nhất có ý nghĩa.** Chọn portal Servlet với `POST /settings/email`. Thiết kế ba test MockMvc (thiếu token, sai token, token hợp lệ), một chuỗi HTTP thật với cookie và token từ login, một test browser kiểm tra form hợp lệ. Với từng test, ghi rõ dữ liệu trước/sau và chỉ ra điều kiện khiến kết quả 403 **chưa đủ chứng minh** CSRF.

**Bài tập B — Kiểm thử CORS và API Reactive.** Thiết kế test WebTestClient cho scope `profile:read`, preflight với origin được phép/không được phép; dùng curl xem response cuối cùng và Playwright thử `fetch` ở hai origin. Giải thích vì sao `mockJwt()` không chứng minh chữ ký token và vì sao curl nhận 200 không tự chứng minh CORS sai.

**Bài tập C — Điều tra hồi quy sau deploy.** Ở môi trường staging, MockMvc xác nhận CSP/HSTS đúng, nhưng trình duyệt vẫn thực thi inline script trên một trang lỗi và thiếu `Secure` ở cookie. Hãy truy lại chain xử lý route lỗi, chính sách CSP `Enforce` hay `Report-Only`, reverse proxy, cách nhận diện HTTPS và `Set-Cookie` sau proxy. Ghi lại test sẽ bổ sung để lỗi này không tái diễn.

**Bài tập D — Báo cáo nghiệm thu.** Tạo bảng từ T01–T10 đến M/H/B test tương ứng; chạy những test có sẵn trong môi trường được cấp quyền; điền kết quả và bằng chứng đã che dữ liệu nhạy cảm. Ghi ít nhất một rủi ro còn lại và một test hiện tại chưa đủ kết luận, kèm kế hoạch bổ sung bằng chứng.

## 14. Tài liệu tham khảo

- [Spring Security — Testing (Servlet)](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring Security — Testing (Reactive)](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security — Protection Against Exploits (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/index.html)
- [Spring Security — Protection Against Exploits (Reactive)](https://docs.spring.io/spring-security/reference/reactive/exploits/index.html)
- [Spring Security — HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Playwright — Writing Tests](https://playwright.dev/docs/writing-tests)
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [OWASP — Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
- [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
