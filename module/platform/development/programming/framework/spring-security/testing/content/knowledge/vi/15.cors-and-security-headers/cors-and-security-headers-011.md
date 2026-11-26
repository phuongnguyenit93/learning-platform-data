# Đối chiếu header trên phản hồi thành công, lỗi và chuyển hướng

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng spring-security-test trên ứng dụng Servlet và Reactive.

## 1. Vì sao phải kiểm tra nhiều loại response?

Một API có thể trả `200 OK` với đủ security headers, nhưng lại thiếu header trên response `401 Unauthorized`, `403 Forbidden` hoặc `302 Found`. Người dùng gặp lỗi đăng nhập, bị từ chối quyền hoặc được chuyển hướng tới trang đăng nhập; chính các response đó cũng cần được bảo vệ và phải tuân theo chính sách CORS nếu request xuất phát từ frontend khác origin.

Kiểm tra một endpoint thành công không chứng minh mọi đường phản hồi đều đúng. Một response có thể được tạo bởi:

- Controller trả dữ liệu thành công.
- Authentication entry point trả 401 hoặc chuyển hướng tới trang đăng nhập.
- Access denied handler trả 403.
- CSRF filter từ chối request.
- Controller hoặc exception handler tạo response lỗi 4xx/5xx.
- Framework/container xử lý lỗi sau khi request rời khỏi controller.
- Reverse proxy, API gateway hoặc CDN trả response trước khi request tới Spring.

Mỗi đường có thể đi qua các thành phần khác nhau. Vì vậy, bài kiểm thử cần xác nhận **header thực tế trên từng loại response**, không chỉ kiểm tra cấu hình DSL.

Trong module **SPRING_SECURITY_TESTING**, bạn sẽ dùng MockMvc cho Servlet và WebTestClient cho Reactive để đối chiếu CORS headers, security headers, Location, Cache-Control và các header nghiệp vụ theo status code. Browser E2E bổ sung bằng chứng cho redirect chain và chính sách browser thực thi.

Sau bài học, bạn có thể:

1. Lập ma trận response 2xx, 3xx, 4xx và 5xx.
2. Kiểm tra header trên response thành công, xác thực thất bại, thiếu quyền, CSRF bị từ chối và lỗi ứng dụng.
3. Kiểm tra response redirect có Location và các header bảo vệ cần thiết.
4. Phân biệt response CORS được phép với response từ origin bị cấm.
5. Phát hiện header bị mất hoặc bị ghi đè bởi exception handler, error dispatch, security chain hay proxy.

## 2. Nhìn response theo nơi tạo ra

Một request đi vào ứng dụng và có thể kết thúc ở nhiều lớp:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Servlet / WebFlux filters"]
    B --> C{"Security decision"}
    C -->|CORS preflight hợp lệ| D["CORS response"]
    C -->|Chưa xác thực| E["Authentication entry point"]
    C -->|Không đủ quyền / CSRF| F["Access denied handler"]
    C -->|Được phép| G["Controller"]
    G -->|Thành công| H["2xx response"]
    G -->|Chuyển hướng| I["3xx + Location"]
    G -->|Lỗi được xử lý| J["Exception handler"]
    J --> K["4xx / 5xx response"]
    E --> L["Security header writers"]
    F --> L
    H --> L
    I --> L
    K --> L
    D --> M["HTTP response"]
    L --> M
~~~

Sơ đồ mang tính khái quát; vị trí cụ thể của filter và cách commit response phụ thuộc cấu hình/phiên bản. Điều quan trọng là header có thể được thêm ở tầng security, controller hoặc proxy. Test cần chạy qua đúng tầng đang sở hữu policy.

### 2.1. Response thành công 2xx

Ví dụ actual GET từ frontend được phép:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.vn
Vary: Origin
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; object-src 'none'
Cache-Control: no-store
Content-Type: application/json
~~~

Kiểm tra:

- CORS origin có khớp origin request.
- Security headers như nosniff/CSP có đúng policy.
- Cache policy phù hợp loại dữ liệu.
- Header nghiệp vụ cần cho frontend có tồn tại và được expose nếu JavaScript cần đọc qua CORS.

### 2.2. Response chuyển hướng 3xx

Ví dụ endpoint chuyển tới trang đăng nhập:

~~~http
HTTP/1.1 302 Found
Location: /login
Access-Control-Allow-Origin: https://app.example.vn
Vary: Origin
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'; object-src 'none'
~~~

Redirect là một response HTTP thực sự. Test server nên kiểm tra status, Location và các header bảo vệ/CORS theo policy. Browser có thể tiếp tục theo redirect; khi đó cần kiểm tra cả response đích và các quy tắc CORS áp dụng cho chuỗi chuyển hướng.

Không mặc định mọi redirect đều có cùng chính sách. Redirect có thể được tạo bởi authentication entry point, controller, proxy hoặc HTTP-to-HTTPS middleware. Mỗi nơi có thể có cấu hình header khác nhau.

### 2.3. Response lỗi 4xx

Các ví dụ:

- `401`: chưa có danh tính hợp lệ hoặc credential không hợp lệ.
- `403`: đã xác thực nhưng không đủ quyền, hoặc request bị CSRF protection từ chối.
- `404`: không tìm thấy tài nguyên; response có thể do MVC hoặc error handler tạo.
- `400`: request không hợp lệ hoặc không thể parse.

Với origin được phép, response lỗi actual request vẫn có thể cần `Access-Control-Allow-Origin` để frontend đọc status/body lỗi. CORS thành công không biến lỗi nghiệp vụ thành thành công; nó chỉ cho phép browser chia sẻ response với JavaScript.

Ví dụ:

~~~http
HTTP/1.1 403 Forbidden
Access-Control-Allow-Origin: https://app.example.vn
Vary: Origin
X-Content-Type-Options: nosniff
Content-Security-Policy: default-src 'self'
Content-Type: application/problem+json
~~~

Nếu origin không được phép, Spring CORS processor thường từ chối và không phát ACAO cho origin đó. Không dùng test origin bị cấm để kỳ vọng mọi header CORS đều xuất hiện.

### 2.4. Response lỗi 5xx

Lỗi ứng dụng có thể được xử lý trong MVC/WebFlux exception resolver, controller advice, error controller hoặc tầng proxy. Nếu response vẫn đi qua security filter chain, security header writers thường có cơ hội ghi header. Nếu lỗi được tạo ngoài chain hoặc bởi proxy, policy trong Spring không tự động áp dụng.

Ví dụ response lỗi có thể cần:

~~~http
HTTP/1.1 500 Internal Server Error
Access-Control-Allow-Origin: https://app.example.vn
Vary: Origin
X-Content-Type-Options: nosniff
Content-Type: application/problem+json
Cache-Control: no-store
~~~

Không trả stack trace, thông tin database, token hoặc dữ liệu nội bộ trong error body. Test header cần đi cùng test nội dung lỗi không làm lộ thông tin.

## 3. Xây dựng ma trận header theo status

Không phải header nào cũng cần xuất hiện trên mọi response. Hãy xác định policy theo loại nội dung và trạng thái.

| Header | 2xx | 3xx | 4xx | 5xx | Điều kiện/lưu ý |
| --- | --- | --- | --- | --- | --- |
| `X-Content-Type-Options` | Thường có | Thường có | Nên có | Nên có | Header bảo vệ baseline |
| `Content-Security-Policy` | Trang HTML và route cần policy | Theo trang đích/response | Có thể cần trên trang lỗi | Có thể cần trên trang lỗi | API JSON có thể không cần CSP như HTML |
| `X-Frame-Options` | Trang không cho nhúng | Theo trang | Trang lỗi HTML nếu cần | Trang lỗi HTML nếu cần | Phối hợp với frame-ancestors |
| `Strict-Transport-Security` | Có trên HTTPS | Có trên HTTPS | Có trên HTTPS | Có trên HTTPS | Chỉ khi request được xem là secure |
| `Cache-Control` | Theo dữ liệu | Theo redirect | Theo nội dung lỗi | Thường không cache lỗi nhạy cảm | Đừng áp dụng một giá trị cho mọi asset |
| `Access-Control-Allow-Origin` | Với CORS origin hợp lệ | Với response CORS phù hợp | Với actual request từ origin hợp lệ | Với actual request từ origin hợp lệ | Không phát cho origin bị cấm |
| `Access-Control-Allow-Credentials` | Khi policy credentialed | Khi policy credentialed | Khi policy credentialed | Khi policy credentialed | Cần ACAO cụ thể, không wildcard |
| `Vary: Origin` | Khi response phụ thuộc Origin | Khi response phụ thuộc Origin | Khi response phụ thuộc Origin | Khi response phụ thuộc Origin | Kiểm tra cache/proxy nếu response thay đổi theo origin |
| `Location` | Không thường dùng | Khi redirect | Không thường dùng | Không thường dùng | Giá trị phải trỏ đúng đích theo hợp đồng |

Bảng là điểm khởi đầu. Hãy điều chỉnh theo loại response, kiến trúc và chính sách đã duyệt. Ví dụ HSTS phụ thuộc secure request, còn CSP có ý nghĩa chính với tài liệu browser như HTML.

## 4. Phân biệt header bảo vệ, CORS và header nghiệp vụ

Khi assertion thất bại, cần biết header thuộc lớp nào:

- **Security headers:** CSP, X-Content-Type-Options, X-Frame-Options, HSTS, Referrer-Policy.
- **CORS headers:** ACAO, ACAC, Allow-Methods, Allow-Headers, Expose-Headers, Max-Age, Vary.
- **HTTP semantics:** Location, Content-Type, Cache-Control, Retry-After.
- **Application headers:** X-Request-ID, correlation ID, rate-limit metadata.

Một endpoint có thể trả đúng X-Content-Type-Options nhưng thiếu ACAO; đó là lỗi CORS. Hoặc response có ACAO đúng nhưng thiếu CSP; đó là lỗi security header. Không gộp các assertion thành một kiểm tra chung khó chẩn đoán.

### 4.1. Header trên response lỗi xác thực

Khi request từ origin hợp lệ chưa đăng nhập, server có thể trả 401. Nếu CORS đã xử lý origin trước authentication, response 401 vẫn có ACAO phù hợp. Frontend có thể đọc 401 và hiển thị trạng thái đăng nhập hết hạn.

Nếu entry point trả redirect tới login thay vì 401, response là 302; hãy kiểm tra Location và header. Đây là quyết định API/UI của ứng dụng, không phải CORS tự quyết định.

### 4.2. Header trên response bị từ chối quyền

Một user đã xác thực nhưng không có authority có thể nhận 403. CORS header vẫn có thể xuất hiện nếu origin được phép. Security headers như nosniff và CSP cũng nên được giữ trên response.

Đừng viết test chỉ kiểm tra status 403. Cần kiểm tra response không làm lộ chi tiết quyền hoặc stack trace, đồng thời header baseline vẫn được áp dụng.

### 4.3. CSRF 403 khác authorization 403

Hai trường hợp có cùng status nhưng nguyên nhân khác nhau:

- Authorization 403: danh tính không có quyền truy cập.
- CSRF 403: request thay đổi trạng thái thiếu token hoặc token không hợp lệ.

Nên có test riêng cho từng nguyên nhân. Khi kiểm tra header, cả hai response đều cần được đối chiếu theo policy. Không tắt CSRF để làm test CORS hoặc response header pass.

## 5. Cấu hình minh họa trong Spring Security Servlet

Ví dụ cấu hình CORS và security headers trong cùng SecurityFilterChain. Chính sách minh họa chỉ cho frontend cụ thể gọi API:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletSecurityConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-XSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .headers(headers -> headers
                .contentTypeOptions(Customizer.withDefaults())
                .frameOptions(frame -> frame.deny())
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; object-src 'none'; frame-ancestors 'none'")))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/private/**").authenticated()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình này minh họa:

- CORS được tích hợp trong security chain.
- Origin cụ thể được cho phép với credentials.
- Security headers được cấu hình trong cùng chain.
- API private yêu cầu xác thực; admin yêu cầu role.
- HTTP Basic entry point thường trả 401 khi thiếu credential.

Trong ứng dụng thực tế, endpoint và authentication mechanism có thể khác. Nếu có nhiều SecurityFilterChain, phải cấu hình header/CORS cho từng chain cần thiết.

## 6. MockMvc: kiểm tra response 2xx, 3xx, 4xx và 5xx

### 6.1. Kiểm tra response thành công

Dùng MockMvc qua application context để request đi qua Spring Security filter chain:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletResponseHeaderTests {

    @Autowired
    MockMvc mvc;

    private static final String ORIGIN = "https://app.example.vn";

    @Test
    void successResponseCoCorsVaSecurityHeaders() throws Exception {
        mvc.perform(get("/api/public/report")
                .header(HttpHeaders.ORIGIN, ORIGIN))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN))
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("object-src 'none'")));
    }
}
~~~

Endpoint trong ví dụ cần tồn tại và trả 200. Thay bằng endpoint thực của dự án; assertion phải phản ánh policy đã cấu hình.

### 6.2. Response 401 vẫn có CORS và security headers

~~~java
@Test
void unauthenticatedResponseRetainsHeaders() throws Exception {
    mvc.perform(get("/api/private/profile")
            .header(HttpHeaders.ORIGIN, ORIGIN))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN))
        .andExpect(header().string(
            "X-Content-Type-Options", "nosniff"))
        .andExpect(header().exists("Content-Security-Policy"));
}
~~~

Kỳ vọng 401 giả định HTTP Basic hoặc entry point trả 401. Nếu ứng dụng dùng form login, hãy kiểm tra redirect thay vì ép status 401.

### 6.3. Response 403 do authorization

~~~java
@Test
@WithMockUser(username = "reader", authorities = "report:read")
void forbiddenResponseRetainsHeaders() throws Exception {
    mvc.perform(get("/api/admin/reports")
            .header(HttpHeaders.ORIGIN, ORIGIN))
        .andExpect(status().isForbidden())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN))
        .andExpect(header().string(
            "X-Content-Type-Options", "nosniff"));
}
~~~

Test giả định endpoint admin yêu cầu role/authority cao hơn authority của user giả lập. `@WithMockUser` tạo SecurityContext cho test; không dùng nó để chứng minh cookie hoặc bearer token thật được gửi.

### 6.4. Response 403 do CSRF

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
@WithMockUser
void postThieuCsrfBiTuChoiNhungVanCoHeader() throws Exception {
    mvc.perform(post("/api/private/update")
            .header(HttpHeaders.ORIGIN, ORIGIN))
        .andExpect(status().isForbidden())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN))
        .andExpect(header().string(
            "X-Content-Type-Options", "nosniff"));
}

@Test
@WithMockUser
void postCoCsrfTokenDuocChapNhan() throws Exception {
    mvc.perform(post("/api/private/update")
            .with(csrf())
            .header(HttpHeaders.ORIGIN, ORIGIN))
        .andExpect(status().isOk())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN));
}
~~~

Hai test này cần endpoint POST được bảo vệ CSRF và có thể truy cập bởi user trong test. Nếu dự án dùng CSRF token repository tùy chỉnh, dùng cách cấp token tương ứng. Không nhầm test này với authorization 403.

### 6.5. Response 302 có Location và header

Một controller có thể chủ động chuyển hướng:

~~~java
import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class RedirectController {

    @GetMapping("/api/continue")
    ResponseEntity<Void> continueToLogin() {
        return ResponseEntity.status(HttpStatus.FOUND)
            .location(URI.create("/login"))
            .build();
    }
}
~~~

Test response đầu tiên:

~~~java
@Test
void redirectResponseRetainsCorsAndSecurityHeaders() throws Exception {
    mvc.perform(get("/api/continue")
            .header(HttpHeaders.ORIGIN, ORIGIN))
        .andExpect(status().isFound())
        .andExpect(header().string("Location", "/login"))
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN))
        .andExpect(header().string(
            "X-Content-Type-Options", "nosniff"));
}
~~~

MockMvc không tự chạy theo redirect như browser. Test này chỉ xác nhận response 302 đầu tiên. Nếu cần xác nhận trang đích cũng có CSP/security headers, hãy gửi request riêng tới `/login` và kiểm tra response đó.

### 6.6. Response 500 được tạo bởi ứng dụng

Có thể dùng endpoint test trả status 500 hoặc exception handler của ứng dụng. Ví dụ endpoint minh họa:

~~~java
@GetMapping("/api/failure")
ResponseEntity<String> failure() {
    return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
        .body("Request could not be completed");
}
~~~

Assertion:

~~~java
@Test
void serverErrorResponseRetainsHeaders() throws Exception {
    mvc.perform(get("/api/failure")
            .header(HttpHeaders.ORIGIN, ORIGIN))
        .andExpect(status().isInternalServerError())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN))
        .andExpect(header().string(
            "X-Content-Type-Options", "nosniff"))
        .andExpect(header().exists("Content-Security-Policy"));
}
~~~

Nếu ứng dụng dùng `@ControllerAdvice` hoặc error controller, hãy kiểm tra response do chính handler đó tạo. Một response do proxy hoặc container phát ra ngoài security chain có thể không mang header của Spring; khi đó phải kiểm tra ở tầng sở hữu response.

## 7. WebTestClient: kiểm tra response trong ứng dụng Reactive

Với WebFlux, dùng WebTestClient được gắn với application context/security chain. Ví dụ các assertion cơ bản:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveResponseHeaderTests {

    @Autowired
    WebTestClient client;

    private static final String ORIGIN = "https://app.example.vn";

    @Test
    void successResponseHasHeaders() {
        client.get().uri("/api/public/report")
            .header(HttpHeaders.ORIGIN, ORIGIN)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff");
    }

    @Test
    void unauthenticatedResponseHasHeaders() {
        client.get().uri("/api/private/profile")
            .header(HttpHeaders.ORIGIN, ORIGIN)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
            .expectHeader().exists("Content-Security-Policy");
    }

    @Test
    void forbiddenResponseHasHeaders() {
        client.mutateWith(mockUser("reader"))
            .get().uri("/api/admin/reports")
            .header(HttpHeaders.ORIGIN, ORIGIN)
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff");
    }
}
~~~

Kỳ vọng 401 phụ thuộc authentication entry point. Nếu cấu hình trả redirect, thay status theo hợp đồng của ứng dụng và kiểm tra Location. Test Reactive cần endpoint tương ứng và policy CORS/security headers trong SecurityWebFilterChain.

### 7.1. Kiểm tra redirect và server error trong WebFlux

Controller Reactive có thể trả redirect:

~~~java
@GetMapping("/api/continue")
Mono<ResponseEntity<Void>> continueToLogin() {
    return Mono.just(ResponseEntity.status(HttpStatus.FOUND)
        .location(URI.create("/login"))
        .build());
}
~~~

Test:

~~~java
@Test
void redirectResponseHasLocationAndSecurityHeaders() {
    client.get().uri("/api/continue")
        .header(HttpHeaders.ORIGIN, ORIGIN)
        .exchange()
        .expectStatus().isFound()
        .expectHeader().valueEquals("Location", "/login")
        .expectHeader().valueEquals("X-Content-Type-Options", "nosniff")
        .expectHeader().valueEquals(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN);
}
~~~

Response lỗi 500:

~~~java
@GetMapping("/api/failure")
Mono<ResponseEntity<String>> failure() {
    return Mono.just(ResponseEntity
        .status(HttpStatus.INTERNAL_SERVER_ERROR)
        .body("Request could not be completed"));
}
~~~

~~~java
@Test
void serverErrorRetainsHeaders() {
    client.get().uri("/api/failure")
        .header(HttpHeaders.ORIGIN, ORIGIN)
        .exchange()
        .expectStatus().is5xxServerError()
        .expectHeader().valueEquals(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN)
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff");
}
~~~

Đây là response 500 được tạo trong handler. Nếu test một exception chưa được xử lý, cần cấu hình error handling của WebFlux và xác minh đúng response thực tế; không giả định mọi exception đều được ánh xạ thành cùng status/body.

## 8. Redirect: kiểm tra cả response đầu và đích cuối

Redirect có thể xuất phát từ:

- Authentication entry point chuyển người dùng tới trang login.
- Controller chuyển sang trang khác sau khi hoàn tất thao tác.
- HTTP-to-HTTPS redirect ở proxy hoặc web server.
- URL canonicalization hoặc route migration.

Với mỗi redirect, kiểm tra:

1. Status có đúng 301, 302, 303, 307 hoặc 308 theo hợp đồng không?
2. Header Location có đúng path/host/scheme không?
3. Security headers baseline có trên response redirect không?
4. Nếu request là CORS request từ origin được phép, response có ACAO phù hợp không?
5. Response đích có security headers và CORS policy phù hợp không?
6. Redirect có đổi origin không, và browser có thể tiếp tục theo redirect trong chế độ request hiện tại không?

Không phải mọi redirect đều tương đương. 301/302/303 có thể thay đổi cách xử lý method/body theo quy tắc client; 307/308 giữ method. Với request thay đổi trạng thái, hãy chọn status phù hợp để không vô tình gửi lại POST theo cách không mong muốn.

MockMvc/WebTestClient kiểm tra từng response server. Browser E2E cần thiết để xác nhận Fetch/navigation theo redirect chain, đặc biệt khi đích redirect khác origin hoặc có CORS policy riêng.

## 9. CORS trên response lỗi và chuyển hướng

CORS cần được xem xét trên actual response, không chỉ preflight.

### 9.1. Origin hợp lệ, actual response là 401/403

Nếu origin được phép, CORS filter có thể ghi ACAO trước khi authentication/authorization từ chối request. Nhờ vậy frontend đọc được status lỗi và có thể xử lý session hết hạn hoặc thiếu quyền.

Test nên kiểm tra status và ACAO cùng lúc:

~~~java
mvc.perform(get("/api/private/profile")
        .header(HttpHeaders.ORIGIN, ORIGIN))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN));
~~~

### 9.2. Origin bị cấm

Với origin không nằm trong allowlist, không kỳ vọng server phát ACAO cho origin đó. Preflight không hợp lệ thường bị CORS processor từ chối trước controller. Với actual request, hành vi server phụ thuộc nơi thực thi CORS; nếu Spring CorsFilter được cấu hình và nhận request, nó thường từ chối origin không hợp lệ.

Không viết test rằng request từ origin bị cấm luôn không tới server trong mọi kiến trúc. Browser có thể gửi simple request trước khi chặn JavaScript đọc response; gateway hoặc filter server cũng có thể xử lý request theo policy riêng. Hãy kiểm tra log/response tại đúng tầng.

### 9.3. Vary và cache trên response thay đổi theo Origin

Nếu response ACAO thay đổi theo request Origin, cache cần biết response phụ thuộc Origin. Kiểm tra `Vary: Origin` trên các response có CORS policy động, bao gồm response lỗi và redirect nếu chúng cũng thay đổi theo Origin.

Một response 401 có thể bị cache khác với response 200; đừng dùng một cache policy tùy tiện. Với nội dung riêng tư, thường cần no-store hoặc policy được thiết kế rõ. Kiểm tra cache headers của response cuối tuyến qua proxy/CDN.

## 10. Response lỗi có thể bỏ qua security filter chain

MockMvc/WebTestClient qua application context chứng minh response trong đường xử lý của ứng dụng. Tuy nhiên, một số lỗi có thể do thành phần ngoài chain tạo ra:

- Reverse proxy từ chối request do giới hạn kích thước hoặc rate limit.
- Gateway không tìm được upstream.
- TLS handshake thất bại trước khi HTTP request tới Spring.
- Servlet container phát lỗi trước DispatcherServlet hoặc sau khi ứng dụng đã commit response.
- CDN trả trang lỗi riêng.

Trong các trường hợp này, Spring Security không thể bảo đảm header writer của nó được áp dụng. Hãy xác định nơi sở hữu response và cấu hình header tại proxy/gateway nếu cần.

Đối với MVC exception handler, test response qua request thật và xác nhận handler đang được gọi. Đối với error dispatch của container, kiểm tra filter registration và dispatcher type theo cấu hình ứng dụng. Không mặc định một exception handler đã bao phủ mọi lỗi ở mọi tầng.

## 11. Ma trận kiểm thử tổng hợp

| Mã | Loại response | Điều kiện | Assertion tối thiểu |
| --- | --- | --- | --- |
| RESP-01 | 200 | Origin hợp lệ | ACAO, nosniff, CSP/cache theo policy |
| RESP-02 | 204 | Actual request không có body | Security/CORS headers theo policy |
| RESP-03 | 301/302 | Redirect controller | Status, Location, ACAO và security headers |
| RESP-04 | 401 | Chưa xác thực | Entry point status/Location, ACAO nếu origin hợp lệ, baseline headers |
| RESP-05 | 403 authorization | Đã xác thực, thiếu authority | ACAO và security headers |
| RESP-06 | 403 CSRF | Thiếu token CSRF | ACAO và security headers; nguyên nhân được phân loại riêng |
| RESP-07 | 404 | Không tìm thấy route | Header trên error response theo policy |
| RESP-08 | 500 | Exception/handler lỗi | Security/CORS headers và body không lộ chi tiết nội bộ |
| RESP-09 | CORS denied | Origin không được phép | Không ACAO cho origin bị cấm |
| RESP-10 | Redirect chain | Đích cùng/khác origin | Header trên từng response và browser behavior |
| RESP-11 | HTTPS response | Request secure | HSTS có max-age đúng |
| RESP-12 | Gateway error | Proxy tạo response | Header được cấu hình ở tầng gateway/proxy |

Không cần mọi endpoint đều có toàn bộ header giống nhau. Cần ghi rõ policy mong đợi theo loại response và kiểm tra những route đại diện cho mỗi security chain.

## 12. Chẩn đoán khi assertion thất bại

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| 200 có header, 401 không có | Entry point hoặc filter tạo response ở đường khác | Kiểm tra thứ tự filter, exception handling và chain |
| 403 authorization có header, 403 CSRF không có | CSRF response đi qua nhánh khác hoặc header writer bị bỏ qua | Test riêng CSRF filter và response commit |
| Redirect thiếu ACAO | CORS chưa áp dụng cho path hoặc redirect được proxy tạo | Kiểm tra request Origin, chain và Location |
| Redirect có header nhưng trang đích thiếu | Policy đích khác hoặc đích thuộc chain khác | Gửi request riêng tới Location |
| 500 thiếu security headers | Error handler/container/proxy tạo response ngoài chain | Xác định tầng tạo response và cấu hình tại đó |
| Có hai ACAO hoặc CSP | App và proxy cùng ghi header | Kiểm tra response cuối tuyến |
| Header có giá trị sai trên một path | Chain matcher hoặc header writer khác nhau | Xác minh chain đầu tiên khớp request |
| HSTS thiếu trên redirect HTTPS | Request không được xem là secure | Kiểm tra TLS termination và forwarded scheme |
| Cache header không phù hợp trên 401/500 | Policy chỉ cấu hình ở controller thành công | Đưa policy vào tầng response phù hợp và test error path |

Khi debug, ghi nhận riêng status, Location, response headers, body và thành phần đã tạo response. Không suy luận nguyên nhân chỉ từ status code.

## 13. Bài thực hành và tiêu chí hoàn thành

Một ứng dụng có frontend `https://app.example.vn`, API public/private, trang admin và endpoint redirect. Nhóm yêu cầu:

- Origin hợp lệ có thể đọc response của API.
- Origin không hợp lệ không được cấp ACAO.
- Security headers baseline có trên response thành công và lỗi.
- 401/403 có body lỗi theo định dạng thống nhất, không lộ thông tin nội bộ.
- Redirect có Location đúng và response header phù hợp.
- Response nhạy cảm có Cache-Control phù hợp.
- HSTS chỉ xuất hiện khi request được xem là HTTPS.

Hãy thực hiện:

1. Lập bảng policy cho 2xx, 3xx, 4xx, 5xx và ghi rõ header nào áp dụng.
2. Viết MockMvc test cho success, 401, 403 authorization, 403 CSRF, redirect và 500.
3. Viết WebTestClient test tương đương nếu ứng dụng dùng WebFlux.
4. Thêm Origin hợp lệ vào actual request và kiểm tra ACAO trên response lỗi.
5. Thêm test origin bị cấm và xác nhận không cấp ACAO.
6. Kiểm tra Location và gửi request riêng tới đích redirect để đối chiếu header ở cả hai đầu.
7. Kiểm tra HSTS trên secure request và không đòi HSTS trên HTTP thường.
8. Nếu gateway/proxy tạo error hoặc redirect, kiểm tra response cuối tuyến.
9. Dùng browser E2E cho redirect chain và CORS behavior thực tế.

**Tiêu chí hoàn thành:** bộ test phân biệt được response thành công, lỗi và chuyển hướng; xác nhận header theo policy trên từng loại response; phân loại đúng 401/403; kiểm tra cả redirect đích và phát hiện response được tạo ngoài Spring Security filter chain.

**Điểm cần nhớ:** header đúng trên 200 không bảo đảm header đúng trên 401, 403, 302 hay 500. Hãy kiểm tra response theo nơi tạo ra nó, chạy test qua security filter chain thực và bổ sung browser/gateway test cho những đường phản hồi nằm ngoài phạm vi HTTP test client.
