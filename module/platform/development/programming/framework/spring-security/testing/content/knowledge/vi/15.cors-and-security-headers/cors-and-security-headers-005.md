# Credentials và điều kiện cấu hình khi dùng cookie

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Bài toán: gọi API xuyên origin bằng cookie

Giả sử ứng dụng có frontend tại `https://app.example.vn` và API tại `https://api.example.vn`. Người dùng đăng nhập vào API; server tạo session và gửi cookie phiên. Sau đó frontend gọi `GET /api/profile` để lấy thông tin tài khoản.

Dù hai host cùng thuộc một tổ chức, chúng là **hai origin khác nhau**. Khi JavaScript gọi API bằng `fetch`, trình duyệt mặc định không gửi cookie của request cross-origin nếu không bật chế độ credential phù hợp. Server cũng phải phát các header CORS cho phép chia sẻ phản hồi có credential.

Để lời gọi hoạt động, cần đồng thời thỏa nhiều lớp:

- Frontend bật gửi credential, ví dụ `credentials: "include"`.
- CORS server cho phép **origin cụ thể**, đồng thời trả `Access-Control-Allow-Credentials: true`.
- Cookie có thuộc tính `SameSite`, `Secure`, `Domain` và `Path` phù hợp với request.
- Trình duyệt cho phép cookie trong bối cảnh đó; chính sách chặn third-party cookie có thể tác động.
- API xác thực session và kiểm tra quyền như bình thường.
- Với ứng dụng xác thực bằng cookie/session, các thao tác thay đổi trạng thái phải có biện pháp chống CSRF phù hợp.

Bài học này thuộc module **SPRING_SECURITY_TESTING**. Mục tiêu là kiểm thử thực tế CORS có credential trên ứng dụng Servlet và Reactive bằng **MockMvc**, **WebTestClient**, đồng thời phân biệt CORS, cookie và bảo vệ endpoint.

## 2. Origin khác Site: hai khái niệm không được nhầm

CORS sử dụng **origin**. Cookie `SameSite` sử dụng khái niệm **site** (trong trình duyệt hiện đại thường là schemeful site: scheme cùng miền đăng ký được).

Origin được tạo bởi `scheme + host + port`. Site không xét port và thường gom các subdomain cùng miền đăng ký nếu scheme phù hợp.

| Frontend | API | Khác origin? | Khác site? (thông thường) |
| --- | --- | --- | --- |
| `https://app.example.vn` | `https://api.example.vn` | Có, khác host | Không, cùng scheme và site |
| `https://app.example.vn` | `https://api.other.vn` | Có | Có |
| `https://app.example.vn` | `http://api.example.vn` | Có | Có theo schemeful same-site |
| `https://app.example.vn:8443` | `https://api.example.vn` | Có | Thông thường cùng site |

Vì vậy, **cross-origin không luôn đồng nghĩa cross-site**. Ví dụ frontend và API ở hai subdomain HTTPS khác nhau là cross-origin nhưng thường same-site. CORS vẫn áp dụng, nên frontend cần gửi credential cho request cross-origin; cookie có thể vẫn được xem là same-site.

Nếu frontend và API khác site, cookie thường phải có `SameSite=None; Secure` để được gửi trong ngữ cảnh cross-site. Trình duyệt vẫn có thể chặn cookie bên thứ ba theo thiết lập riêng của người dùng hoặc chính sách trình duyệt. Cấu hình CORS không thể buộc trình duyệt bỏ qua các hạn chế này.

## 3. Frontend phải bật credential

### 3.1. Fetch API

Mặc định, `fetch` sử dụng `credentials: "same-origin"`. Khi gọi API khác origin và muốn gửi cookie, frontend cần:

~~~javascript
const response = await fetch("https://api.example.vn/api/profile", {
  method: "GET",
  credentials: "include"
});

if (!response.ok) {
  throw new Error("API request failed: " + response.status);
}

const profile = await response.json();
~~~

Với request `POST`:

~~~javascript
const response = await fetch("https://api.example.vn/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-XSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: "P-100", quantity: 1 })
});
~~~

Header `X-XSRF-TOKEN` là ví dụ cho token CSRF do ứng dụng cấp. Cách lấy và gửi token phụ thuộc cấu hình CSRF của ứng dụng; bật credential không tự tạo token này.

### 3.2. XMLHttpRequest

Nếu dùng `XMLHttpRequest`, cần bật `withCredentials`:

~~~javascript
const xhr = new XMLHttpRequest();
xhr.open("GET", "https://api.example.vn/api/profile");
xhr.withCredentials = true;
xhr.onload = () => console.log(xhr.status, xhr.responseText);
xhr.send();
~~~

Không bật credential ở frontend là một nguyên nhân phổ biến khiến cookie không được gửi dù server đã trả CORS header đúng. Ngược lại, bật `include` cũng chưa bảo đảm cookie sẽ được gửi: trình duyệt còn kiểm tra cookie có khớp domain/path, thời hạn, SameSite, Secure và chính sách quyền riêng tư hay không.

## 4. Server phải cho phép credential một cách tường minh

Giả sử chỉ frontend `https://app.example.vn` được gọi API bằng cookie. Phản hồi actual request hợp lệ cần có dạng:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.vn
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json
~~~

Hai header có vai trò khác nhau:

- `Access-Control-Allow-Origin` cho biết origin nào được đọc phản hồi.
- `Access-Control-Allow-Credentials: true` cho phép trình duyệt chia sẻ phản hồi trong chế độ credential phù hợp.

Với credentialed CORS, không trả `Access-Control-Allow-Origin: *`. Wildcard không hợp lệ cho request có credentials mode `include`. Server phải phản hồi origin cụ thể đã được kiểm tra theo allowlist. Cũng không được trả nhiều origin trong một giá trị phân cách bằng dấu phẩy.

Ví dụ cấu hình sai:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Ví dụ đúng với allowlist cụ thể:

~~~http
Access-Control-Allow-Origin: https://app.example.vn
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

`Vary: Origin` đặc biệt quan trọng nếu server chọn origin phản hồi dựa trên request. Nó giúp cache HTTP không dùng phản hồi được tạo cho origin này để phục vụ nhầm origin khác.

### 4.1. Preflight cũng phải trả credential policy phù hợp

Nếu request thật có `Content-Type: application/json` hoặc header `X-XSRF-TOKEN`, trình duyệt có thể gửi preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.vn
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-xsrf-token
~~~

Phản hồi chấp thuận có thể là:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.vn
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: Content-Type,X-XSRF-TOKEN
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Preflight thông thường **không mang cookie phiên của request thật**. Vì vậy, CORS phải được xử lý trước bước yêu cầu xác thực; không đòi người dùng đăng nhập chỉ để hỏi liệu origin, method và header có được phép hay không. Phản hồi preflight vẫn cần policy tương thích với credential mode của request thật.

## 5. Cookie phải có thuộc tính phù hợp

CORS và cookie là hai hệ thống kiểm soát riêng. Header CORS đúng không làm cookie tự động xuất hiện. Trình duyệt chỉ gửi cookie nếu cookie khớp các quy tắc lưu trữ và gửi cookie.

| Thuộc tính | Vai trò | Điều cần kiểm tra |
| --- | --- | --- |
| `SameSite` | Giới hạn cookie trong ngữ cảnh same-site/cross-site | `Lax`/`Strict` có thể không gửi trong request fetch cross-site; `None` cho phép ngữ cảnh cross-site nhưng cần Secure |
| `Secure` | Chỉ gửi cookie qua kênh bảo mật HTTPS (ngoại lệ localhost theo quy tắc trình duyệt) | Cookie cross-site `SameSite=None` phải có Secure |
| `HttpOnly` | Ngăn JavaScript đọc cookie qua API như document.cookie | Thường bật cho session cookie |
| `Domain` | Xác định host được nhận cookie | Không mở rộng sang mọi subdomain nếu không cần |
| `Path` | Giới hạn đường dẫn request gửi cookie | Đặt phạm vi đủ dùng cho ứng dụng |
| `Expires` / `Max-Age` | Tuổi thọ cookie | Session cookie và persistent cookie có vòng đời khác nhau |

### 5.1. SameSite=Lax, Strict và None

- **Strict:** giới hạn nghiêm ngặt; cookie chỉ được gửi trong ngữ cảnh same-site theo quy tắc trình duyệt.
- **Lax:** cho phép một số điều hướng top-level an toàn cross-site, nhưng không phải mặc định phù hợp cho fetch/XHR cross-site.
- **None:** cho phép cookie trong ngữ cảnh cross-site; cookie phải có `Secure`.

Với frontend và API cùng site nhưng khác origin, `SameSite=Lax` có thể vẫn phù hợp về mặt SameSite. Request vẫn cần `credentials: "include"` do khác origin và vẫn cần CORS credential policy. Với frontend và API khác site, cookie thường cần `SameSite=None; Secure`.

### 5.2. Secure và HTTPS

Cookie `SameSite=None` phải có `Secure`. Trong môi trường production, nên chạy frontend/API trên HTTPS và cấu hình session cookie chỉ truyền qua HTTPS. Nếu reverse proxy kết thúc TLS ở ngoài ứng dụng, cần cấu hình forwarded headers/trusted proxy đúng để ứng dụng nhận biết scheme gốc; nếu không, cookie Secure hoặc redirect có thể bị cấu hình sai.

### 5.3. HttpOnly không thay thế CSRF

`HttpOnly` ngăn JavaScript đọc giá trị cookie trực tiếp, nhưng trình duyệt vẫn tự đính kèm cookie vào request đủ điều kiện. Vì vậy, nó không loại bỏ nguy cơ CSRF.

`HttpOnly=false` đôi khi được dùng cho cookie chứa CSRF token để frontend đọc token và gửi lại trong header. Không nên áp dụng cho session cookie chỉ vì frontend cần gọi API. Có thể giữ session cookie HttpOnly và dùng một cơ chế riêng để cung cấp CSRF token.

### 5.4. Domain và phạm vi subdomain

Không đặt `Domain=.example.vn` theo thói quen nếu cookie chỉ cần cho một host. Mở rộng Domain làm nhiều subdomain có thể nhận cookie; điều này tăng phạm vi ảnh hưởng nếu một subdomain yếu bảo mật. Cookie không khai báo Domain là host-only và thường an toàn hơn khi chỉ cần cho đúng host.

Nếu dùng tiền tố `__Host-` cho cookie, trình duyệt yêu cầu cookie có `Secure`, `Path=/` và không có `Domain`. Đây là một cách tăng ràng buộc phạm vi cookie trong những ứng dụng phù hợp.

## 6. Cấu hình Spring Security Servlet

Ví dụ dưới đây cấu hình credentialed CORS cho frontend đã biết và bảo vệ endpoint bằng xác thực HTTP Basic để minh họa security chain. Trong ứng dụng session thực tế, thay HTTP Basic bằng cơ chế đăng nhập/session đang sử dụng.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-XSRF-TOKEN", "X-Requested-With"));
        cors.setExposedHeaders(List.of("X-Request-ID"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Các điểm cần kiểm tra:

1. `setAllowedOrigins` dùng origin cụ thể, không phải wildcard.
2. `setAllowCredentials(true)` cho phép response credentialed CORS.
3. `setAllowedHeaders` chứa header CSRF mà frontend dự kiến gửi. Nếu request không dùng `X-XSRF-TOKEN` thì không cần khai báo header này.
4. `http.cors(...)` tích hợp xử lý CORS trước các bước xác thực thích hợp.
5. CSRF vẫn bật theo mặc định. Không tắt CSRF chỉ để request cookie hoạt động.

### 6.1. Thuộc tính session cookie của Spring Boot

Với ứng dụng Servlet dùng session cookie do container quản lý, có thể cấu hình trong `application.properties`:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=none
~~~

Đặt `same-site=none` khi frontend/API thực sự khác site và cần cookie trong ngữ cảnh cross-site. Nếu frontend và API same-site, chọn chính sách hẹp hơn như Lax nếu tương thích với luồng đăng nhập. `secure=true` yêu cầu HTTPS; trong môi trường local HTTP, cần cấu hình profile dev riêng thay vì nới lỏng production.

Nếu dùng Spring Session, cookie có thể được quản lý bởi cấu hình Spring Session như `DefaultCookieSerializer`; khi đó hãy cấu hình ở đúng nơi phát session cookie, tránh hai nguồn cấu hình không nhất quán.

## 7. CSRF khi xác thực bằng cookie

Cookie là credential mà trình duyệt tự động gửi theo quy tắc của nó. Nếu người dùng đăng nhập, một trang độc hại có thể cố khiến trình duyệt gửi request thay đổi dữ liệu đến API. CORS chủ yếu kiểm soát việc chia sẻ phản hồi với JavaScript; nó **không phải cơ chế chống CSRF**.

Với ứng dụng session/cookie:

- Giữ CSRF protection cho các phương thức làm thay đổi trạng thái.
- Frontend cần lấy CSRF token theo cơ chế của ứng dụng và gửi lại bằng header hoặc tham số được cấu hình.
- Nếu header token không thuộc safelist, preflight phải được phép header đó, ví dụ `X-XSRF-TOKEN`.
- Không coi `SameSite` là lớp bảo vệ duy nhất; đánh giá thêm kiến trúc, trình duyệt hỗ trợ và luồng điều hướng.
- Không nhầm CORS preflight thành request nghiệp vụ; preflight không cần session cookie hoặc CSRF token của request thật.

Trong Spring Security, `CookieCsrfTokenRepository` là một lựa chọn cho ứng dụng cần chia sẻ CSRF token qua cookie. Nếu frontend phải đọc cookie CSRF bằng JavaScript, cookie token có thể cần `HttpOnly=false`; quyết định này chỉ áp dụng cho **CSRF token cookie**, không phải session cookie. Các ứng dụng Spring Security hiện đại có cơ chế deferred token và yêu cầu xử lý token theo cấu hình; hãy dùng hướng dẫn tương ứng phiên bản của dự án khi triển khai.

## 8. Kiểm thử Servlet bằng MockMvc

### 8.1. Kiểm thử preflight có credential policy

Preflight không cần session cookie, nhưng phản hồi cần công bố credential policy phù hợp. Dùng MockMvc để xác nhận các header:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.containsStringIgnoringCase;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletCredentialCorsTests {

    private static final String ORIGIN = "https://app.example.vn";

    @Autowired
    MockMvc mvc;

    @Test
    void preflightDuocPhepChoRequestCoCredential() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-xsrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                containsString("POST")))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                containsStringIgnoringCase("x-xsrf-token")));
    }

    @Test
    void preflightOriginLaBiTuChoi() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, "https://evil.example.vn")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }
}
~~~

Đây là test kiểm tra chính sách CORS trong filter chain. Không thêm `@WithMockUser` vào preflight: trình duyệt thông thường không gửi session cookie của request thật trên preflight, và test cần chứng minh CORS xử lý trước authentication.

### 8.2. Kiểm thử actual request đã xác thực

Có thể dùng `@WithMockUser` để kiểm tra response CORS của endpoint khi security context đã có người dùng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletCredentialedActualRequestTests {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "learner")
    void actualResponseChoPhepOriginVaCredential() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.ORIGIN, "https://app.example.vn"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.vn"))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void originHopLeNhungChuaDangNhapVanBiChan() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.ORIGIN, "https://app.example.vn"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.vn"));
    }
}
~~~

`@WithMockUser` thiết lập `SecurityContext` cho test; nó **không chứng minh trình duyệt đã gửi cookie phiên**. Muốn kiểm thử chính cookie session, cần test tích hợp với cơ chế session/repository của ứng dụng: tạo session đã đăng nhập, gửi lại session cookie tương ứng trong request tiếp theo, rồi xác nhận endpoint nhận đúng danh tính. MockMvc có thể gắn `MockHttpSession` vào request, nhưng thao tác này mô phỏng session ở server và không thực thi quy tắc trình duyệt về SameSite, Secure hoặc third-party cookie.

Để kiểm tra thuộc tính `Set-Cookie` thực sự được container phát ra, dùng kiểm thử tích hợp với server phù hợp và đối chiếu thuộc tính `HttpOnly`, `Secure`, `SameSite`, `Path` và `Domain` theo cấu hình. Không suy ra thuộc tính cookie từ riêng header CORS.

## 9. Reactive: cấu hình và kiểm thử WebTestClient

Với WebFlux, có thể tích hợp CORS qua `SecurityWebFilterChain`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-XSRF-TOKEN", "X-Requested-With"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http,
                                    CorsConfigurationSource cors) {
        return http
            .cors(spec -> spec.configurationSource(cors))
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Nếu ứng dụng sử dụng `CorsWebFilter` độc lập, cần đặt nó trước security web filter và tránh đăng ký policy trùng lặp. Chỉ chọn một cách tích hợp rõ ràng để dễ kiểm thử.

Test WebTestClient:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCredentialCorsTests {

    @Autowired
    WebTestClient client;

    @Test
    void preflightCredentialPolicy() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, "https://app.example.vn")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-xsrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.vn")
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true")
            .expectHeader().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
    }

    @Test
    void actualRequestCoCredentialPolicy() {
        client.mutateWith(mockUser("learner"))
            .get().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, "https://app.example.vn")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.vn")
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true");
    }

    @Test
    void originKhongDuocPhep() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, "https://evil.example.vn")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }
}
~~~

Với một số cấu hình WebTestClient tùy chỉnh, cần liên kết security filter bằng `springSecurity()` khi tạo client từ application context. Ví dụ dùng `@AutoConfigureWebTestClient` theo cấu hình Spring Boot của dự án; nếu test client được dựng thủ công, cần áp dụng cấu hình security test tương ứng.

Tương tự MockMvc, `mockUser` chỉ giả lập principal trong security context. Nó không mô phỏng trình duyệt lưu, gửi và từ chối cookie theo SameSite hoặc chính sách third-party cookie.

## 10. Ma trận lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| API trả `200` nhưng JavaScript không đọc được | Thiếu `Access-Control-Allow-Origin` hoặc origin không khớp | Xem response header trên actual request |
| Response có `Allow-Origin` nhưng cookie không được gửi | Frontend chưa bật `credentials: include`; cookie sai SameSite/Domain/Path/Secure; browser chặn third-party cookie | Xem Request Headers, cookie storage và Console |
| Preflight `401` | Security yêu cầu đăng nhập trước khi CORS xử lý | Kiểm tra thứ tự CORS filter và security chain |
| Preflight `403` | Origin/method/header không được phép hoặc gateway từ chối | Đối chiếu từng header yêu cầu và policy |
| `Allow-Origin: *` cùng `Allow-Credentials: true` | Cấu hình credentialed CORS không hợp lệ cho trình duyệt | Dùng origin cụ thể trong allowlist |
| Cookie không được gửi trên HTTP | Cookie có `Secure` nhưng môi trường không HTTPS | Kiểm thử qua HTTPS hoặc profile dev phù hợp |
| Cookie cross-site không được gửi | `SameSite` không phù hợp hoặc `SameSite=None` thiếu Secure | Kiểm tra Set-Cookie và chính sách trình duyệt |
| Cookie gửi được nhưng POST trả `403` | CSRF token thiếu/sai hoặc authorization từ chối | Kiểm tra CSRF riêng, không nới CORS |
| MockMvc test qua nhưng trình duyệt lỗi | MockMvc không thực thi chính sách cookie của trình duyệt | Kiểm thử thêm trên browser thật |
| Cookie bị gửi tới subdomain ngoài dự kiến | Domain cookie quá rộng | Thu hẹp Domain hoặc dùng host-only cookie |

### 10.1. CORS thành công không đồng nghĩa cookie tồn tại

Khi response có:

~~~http
Access-Control-Allow-Origin: https://app.example.vn
Access-Control-Allow-Credentials: true
~~~

điều đó chỉ chứng minh server công bố policy CORS phù hợp cho origin này. Nó không chứng minh:

- Cookie đã được lưu thành công.
- Cookie chưa hết hạn.
- Cookie khớp host, path và scheme.
- Trình duyệt chấp nhận cookie trong ngữ cảnh third-party.
- Request thật đã mang cookie.
- Session còn tồn tại hoặc người dùng có quyền.

Cần xem cả header `Set-Cookie` ở response đăng nhập và header `Cookie` ở request kế tiếp (nếu DevTools hiển thị). Trình duyệt có thể ẩn hoặc chặn cookie vì lý do chính sách; kiểm tra mục Issues/Storage/Application tùy browser.

## 11. Thực hành kiểm chứng bằng HTTP và trình duyệt

Dùng `curl` mô phỏng preflight:

~~~bash
curl -i -X OPTIONS 'https://api.example.vn/api/profile' \
  -H 'Origin: https://app.example.vn' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: content-type'
~~~

Đối chiếu `Access-Control-Allow-Origin` phải đúng origin và `Access-Control-Allow-Credentials` là `true`. Preflight không mang session cookie của actual request.

Sau đó kiểm thử actual request bằng một session cookie của môi trường dev:

~~~bash
curl -i 'https://api.example.vn/api/profile' \
  -H 'Origin: https://app.example.vn' \
  -H 'Cookie: SESSION=<session-cookie-dev>'
~~~

Lệnh trên chỉ minh họa cách gửi cookie; `curl` không mô phỏng quy tắc SameSite, Secure hay third-party cookie của trình duyệt. Không dùng cookie production trong terminal, shell history hoặc log.

Trên trình duyệt, xác nhận theo trình tự:

1. Đăng nhập và kiểm tra response `Set-Cookie`: cookie có đúng Domain/Path, Secure, HttpOnly và SameSite không?
2. Gọi API với `credentials: "include"`. Request có gửi cookie không?
3. Nếu có preflight, `OPTIONS` có trả origin cụ thể, credential true, method và requested headers đúng không?
4. Actual request có tới API không; server nhận được session và trả kết quả xác thực mong đợi không?
5. Với POST/PUT/DELETE, CSRF token có được gửi và xác minh không?
6. Nếu cookie không gửi dù CORS header đúng, kiểm tra browser policy, cookie partitioning/third-party restrictions và sự khác biệt same-site/cross-site.

## 12. Tiêu chí hoàn thành bài thực hành

Một bộ kiểm thử credentialed CORS đáng tin cậy cần chứng minh được:

- Origin hợp lệ nhận `Access-Control-Allow-Origin` cụ thể và `Access-Control-Allow-Credentials: true`.
- Origin không được phép không nhận header cấp quyền.
- Preflight không yêu cầu cookie phiên, nhưng phản hồi vẫn có credential policy phù hợp và cho phép các method/header cần thiết.
- Frontend dùng `credentials: "include"` hoặc `withCredentials = true` đúng chỗ.
- Cookie có thuộc tính SameSite/Secure/HttpOnly/Domain/Path theo kiến trúc và môi trường.
- Request thật vẫn chịu xác thực, phân quyền và CSRF.
- MockMvc/WebTestClient kiểm tra được response header và security context; kiểm thử trình duyệt/integration bổ sung bằng chứng về cookie transport.

**Điểm cốt lõi:** để dùng cookie qua CORS, phải phối hợp thiết lập của frontend, response header CORS, thuộc tính cookie và chính sách trình duyệt. Spring Security chỉ là một phần của luồng; kiểm thử cần xác nhận cả phản hồi HTTP lẫn quyết định bảo vệ endpoint, và không coi CORS là biện pháp thay thế CSRF.
