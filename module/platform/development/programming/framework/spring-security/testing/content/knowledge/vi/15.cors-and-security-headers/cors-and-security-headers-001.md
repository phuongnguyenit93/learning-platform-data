# Yêu cầu Origin và chính sách nguồn được phép

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Tại sao phải kiểm thử Origin?

Giả sử giao diện chạy tại `https://portal.example.vn` và API chạy tại `https://api.example.vn`. Hai địa chỉ này khác **origin** dù cùng tổ chức. Trình duyệt chỉ cho JavaScript ở giao diện đọc phản hồi từ API khi chính sách **Cross-Origin Resource Sharing (CORS)** của API cho phép.

Một API có thể xác thực JWT đúng, kiểm tra vai trò đúng nhưng vẫn không dùng được từ giao diện vì thiếu `Access-Control-Allow-Origin`. Ngược lại, API trả lời CORS hợp lệ không có nghĩa người gọi đã đăng nhập hay có quyền truy cập dữ liệu. Vì vậy, bài kiểm thử Spring Security cần xem xét **cả kết quả HTTP lẫn các header CORS**, rồi tách biệt chúng khỏi xác thực, phân quyền và CSRF.

Sau bài này, bạn có thể:

- Nhận diện origin của một yêu cầu và phân biệt yêu cầu CORS thông thường với preflight `OPTIONS`.
- Thiết kế danh sách nguồn được phép theo đường dẫn, phương thức và header, kể cả trường hợp gửi cookie.
- Dùng **MockMvc** và **WebTestClient** kiểm chứng origin hợp lệ, origin bị từ chối, phương thức/header bị từ chối và yêu cầu không có `Origin`.
- Đọc kết quả kiểm thử chính xác khi trình duyệt, reverse proxy và Spring Security tham gia cùng luồng xử lý.

## 2. Origin là gì?

Một origin được xác định bằng bộ ba **scheme + host + port**. Path, query string và fragment không thuộc origin.

| URL của trang | So với `https://portal.example.vn` | Giải thích |
| --- | --- | --- |
| `https://portal.example.vn/profile` | Cùng origin | Khác path không làm đổi origin |
| `https://portal.example.vn:443` | Cùng origin | 443 là cổng mặc định của HTTPS |
| `http://portal.example.vn` | Khác origin | Khác scheme |
| `https://api.example.vn` | Khác origin | Khác host |
| `https://portal.example.vn:8443` | Khác origin | Khác port |

Trình duyệt thường tự gửi header `Origin: https://portal.example.vn` khi gọi tài nguyên khác origin. Đây là **nguồn của trang phát sinh yêu cầu**, không phải địa chỉ máy chủ API, cũng không phải `Host` hoặc `Referer`.

Các điểm cần nhớ:

- Một URL có path như `https://portal.example.vn/dashboard` **không phải** giá trị origin để khai báo trong allowlist.
- `Origin` có thể vắng mặt ở lệnh gọi trực tiếp, tác vụ nội bộ hoặc một số điều kiện trình duyệt. Thiếu `Origin` không tự động là tấn công CORS.
- Giá trị `Origin: null` có thể xuất hiện từ *opaque origin* (ví dụ một số ngữ cảnh sandbox). Không tùy tiện thêm `null` vào danh sách cho phép.
- Client như `curl` có thể tự gán `Origin`. **CORS không phải cơ chế xác thực người gọi**: phía máy chủ vẫn phải kiểm chứng session, JWT và quyền đối với tài nguyên.

## 3. Hai luồng CORS cần phân biệt

### 3.1. Yêu cầu thật (actual request)

Một lời gọi `GET` đủ điều kiện là *simple request* có thể được trình duyệt gửi trực tiếp, kèm `Origin`:

~~~http
GET /api/profile HTTP/1.1
Host: api.example.vn
Origin: https://portal.example.vn
~~~

Nếu được phép, phản hồi có thể chứa:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.vn
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json
~~~

Trình duyệt dựa vào các header này để quyết định có cung cấp nội dung phản hồi cho JavaScript hay không. `MockMvc` và `WebTestClient` **không thực thi chính sách trình duyệt**; vì vậy phải kiểm tra header một cách tường minh.

### 3.2. Preflight `OPTIONS`

Với yêu cầu có đặc điểm cần kiểm tra trước (ví dụ `Authorization` hoặc `Content-Type: application/json`, hay phương thức `DELETE`), trình duyệt thường gửi preflight:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.vn
Origin: https://portal.example.vn
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Một phản hồi chấp thuận điển hình:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://portal.example.vn
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
~~~

Header `Access-Control-Request-Method` nói **phương thức của yêu cầu thật**; `Access-Control-Request-Headers` nói **tên các header** mà yêu cầu thật định gửi, không chứa giá trị bearer token. Preflight thông thường không mang thông tin xác thực của yêu cầu thật, nên phải được xử lý trước khi các bộ lọc đăng nhập đòi credential.

**Một yêu cầu `OPTIONS` bất kỳ chưa chắc là preflight.** Để mô phỏng preflight, phải có `Origin` và `Access-Control-Request-Method` phù hợp.

~~~mermaid
flowchart TD
    A["Trang web gọi API khác origin"] --> B{"Cần preflight?"}
    B -- "Có" --> C["OPTIONS + Origin + Request-Method/Headers"]
    C --> D{"Chính sách CORS cho phép?"}
    D -- "Không" --> E["Spring từ chối, thường HTTP 403"]
    D -- "Có" --> F["Trả Access-Control-Allow-*"]
    F --> G["Trình duyệt gửi yêu cầu thật"]
    B -- "Không" --> G
    G --> H["Xác thực, phân quyền, CSRF và xử lý API"]
    H --> I["Phản hồi + header CORS"]
    I --> J{"Trình duyệt cho JavaScript đọc?"}
~~~

### 3.3. Ý nghĩa các header

| Header | Chiều | Ý nghĩa khi kiểm thử |
| --- | --- | --- |
| `Origin` | Request | Nguồn của trang gửi yêu cầu |
| `Access-Control-Request-Method` | Preflight request | Phương thức mà client dự định gọi |
| `Access-Control-Request-Headers` | Preflight request | Các tên header mà client dự định gửi |
| `Access-Control-Allow-Origin` | Response | Origin được cho phép; cần đúng origin mong đợi |
| `Access-Control-Allow-Methods` | Preflight response | Phương thức được cho phép |
| `Access-Control-Allow-Headers` | Preflight response | Header yêu cầu được phép |
| `Access-Control-Allow-Credentials` | Response | Cho phép trình duyệt đưa phản hồi tới mã JavaScript khi dùng chế độ credential phù hợp |
| `Access-Control-Max-Age` | Preflight response | Thời gian trình duyệt có thể cache kết quả preflight |
| `Vary: Origin` | Response | Hỗ trợ cache phân biệt phản hồi theo origin |

`Access-Control-Allow-Credentials: true` thường cần khi frontend dùng `fetch(..., { credentials: "include" })` với cookie khác origin. Nó **không thay thế** chính sách cookie `SameSite`/`Secure`, xác thực hay CSRF.

## 4. Thiết kế chính sách nguồn được phép

Ví dụ trong bài:

- Frontend hợp lệ: `https://portal.example.vn`.
- API cần bảo vệ: `/api/**`.
- Phương thức được phép: `GET` và `POST`.
- Header yêu cầu được phép: `Authorization` và `Content-Type`.
- Cho phép credential ở mức CORS: `true`, vì ví dụ có thể dùng cookie.
- Không cho phép `https://other.example.vn`, `http://portal.example.vn` hay `DELETE`.

**Chính sách càng cụ thể, phép thử càng có ý nghĩa.** Khi bật `allowCredentials(true)`, không dùng `allowedOrigins("*")`: wildcard không được kết hợp với phản hồi credential theo quy tắc CORS. Spring hỗ trợ `allowedOriginPatterns` khi thật sự cần khớp theo mẫu và có thể phản hồi origin cụ thể, nhưng mẫu quá rộng dễ cho phép ngoài ý muốn. Với số lượng frontend xác định, ưu tiên liệt kê origin tường minh.

Việc cho phép origin chỉ áp dụng cho hành vi đọc tài nguyên xuyên origin trong trình duyệt. Nó **không bảo vệ API trước client tự viết** và không thay thế kiểm tra quyền ở từng endpoint.

## 5. Cấu hình Servlet: Spring MVC + Spring Security

Ví dụ dưới đây dùng API `GET /api/profile`. Ở ứng dụng thật, hãy thay bằng endpoint hiện có và giữ nguyên ý tưởng cấu hình.

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
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            // Xử lý CORS trước các bước xác thực.
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
        cors.setAllowedOrigins(List.of("https://portal.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Có thể dùng một controller tối thiểu để kiểm chứng yêu cầu thật:

~~~java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {
    @GetMapping("/api/profile")
    Map<String, String> profile(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}
~~~

Lưu ý:

1. `http.cors(...)` đưa xử lý CORS vào chuỗi filter thích hợp, để preflight không bị chặn sớm bởi xác thực. Cho phép mọi `OPTIONS` bằng `permitAll` **không tự tạo** các header CORS đúng.
2. Cấu hình `CorsConfigurationSource` phải khớp đường dẫn được kiểm thử. API ngoài `/api/**` không mặc nhiên dùng chính sách này.
3. Ví dụ giữ CSRF ở giá trị mặc định của Spring Security. Preflight được xử lý riêng; khi kiểm thử yêu cầu `POST` thực tế có session/cookie, phải bổ sung token CSRF hợp lệ nếu endpoint yêu cầu.
4. Trong ứng dụng đã cấu hình CORS ở Spring MVC, tránh đăng ký hai chính sách chồng chéo khó dự đoán. Xác định nguồn cấu hình mà Spring Security thực sự sử dụng.

## 6. Kiểm thử Servlet với MockMvc

Thêm dependency **`spring-security-test`** ở scope `test` cùng bộ thư viện Spring Boot Test. `@SpringBootTest` và `@AutoConfigureMockMvc` bên dưới tải chuỗi filter thật của ứng dụng; các ví dụ giả định đã có cấu hình và controller ở mục 5.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.containsStringIgnoringCase;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletCorsTests {

    private static final String ALLOWED = "https://portal.example.vn";
    private static final String DENIED = "https://other.example.vn";

    @Autowired
    MockMvc mvc;

    @Test
    void preflightTuOriginDuocPhep() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS, containsString("GET")))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS,
                containsStringIgnoringCase("authorization")))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void preflightTuOriginKhongDuocPhep() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, DENIED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void preflightPhuongThucKhongDuocPhep() throws Exception {
        mvc.perform(options("/api/profile")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "learner")
    void yeuCauThatDuocPhepVaDaDangNhap() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED));
    }

    @Test
    void originHopLeKhongDongNghiaDaDangNhap() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED));
    }

    @Test
    @WithMockUser
    void khongCoOriginThiKhongCanHeaderCors() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }
}
~~~

**Vì sao cần cả hai phép thử `preflightTuOriginDuocPhep` và `yeuCauThatDuocPhepVaDaDangNhap`?** Preflight kiểm tra khả năng trình duyệt **được gửi** yêu cầu tiếp theo; GET thật kiểm tra header của **phản hồi API** khi bộ lọc bảo mật và controller đã chạy. Chỉ kiểm thử một trong hai dễ bỏ sót lỗi.

Kỳ vọng `403` cho preflight bị từ chối là hành vi điển hình của bộ xử lý CORS mặc định của Spring. Nếu ứng dụng có gateway, exception handler hay bộ lọc CORS riêng, status có thể khác; vẫn cần khẳng định **không phát sinh `Access-Control-Allow-Origin` cho nguồn bị cấm**. Với phép thử `401`, ví dụ dùng HTTP Basic; cơ chế xác thực khác có thể đổi mã phản hồi.

## 7. Kiểm thử Reactive với WebTestClient

Ứng dụng WebFlux dùng `CorsWebFilter` và `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`. Đây là **phương án thay thế cho Servlet** khi ứng dụng chạy reactive, không phải một cấu hình cần bật song song trong cùng ứng dụng.

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsConfig {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    CorsWebFilter corsWebFilter() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://portal.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return new CorsWebFilter(source);
    }
}
~~~

Cho `CorsWebFilter` chạy trước filter bảo mật để preflight được xử lý mà không đòi token. Chain bảo mật WebFlux vẫn phải kiểm soát yêu cầu thật, ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Với Spring Boot Test cho ứng dụng WebFlux:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCorsTests {

    @Autowired
    WebTestClient client;

    @Test
    void preflightOriginHopLe() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, "https://portal.example.vn")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://portal.example.vn")
            .expectHeader().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
    }

    @Test
    void preflightOriginBiCam() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, "https://other.example.vn")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .exchange()
            .expectStatus().isForbidden()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }

    @Test
    void preflightHeaderBiCam() {
        client.options().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, "https://portal.example.vn")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "x-admin-override")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Các phép thử trên chỉ yêu cầu có ứng dụng WebFlux được nạp và filter CORS. Nếu viết kiểm thử cho **yêu cầu thật đã xác thực**, có thể dùng `SecurityMockServerConfigurers.springSecurity()` để liên kết `WebTestClient` với security chain rồi `mutateWith(mockJwt())` khi kiểm thử resource server JWT. `mockJwt()` tạo ngữ cảnh xác thực giả lập, không kiểm thử xác minh chữ ký token. Với Servlet, `@WithMockUser` hoặc `get(...).with(jwt())` cũng chỉ giải quyết phần danh tính/quyền trong test, không thay đổi quyết định CORS.

## 8. Ma trận ca kiểm thử tối thiểu

| Trường hợp | Đầu vào chính | Kết quả nên kiểm chứng |
| --- | --- | --- |
| Preflight hợp lệ | `Origin` hợp lệ, `Request-Method: GET` | Thành công; `Allow-Origin` đúng; method được phép |
| Origin lạ | Origin ngoài allowlist | Preflight bị từ chối; không có `Allow-Origin` cấp quyền |
| Sai scheme | `http://portal.example.vn` thay vì HTTPS | Bị từ chối theo allowlist |
| Sai port | `https://portal.example.vn:8443` | Bị từ chối theo allowlist |
| Method bị cấm | Preflight `Request-Method: DELETE` | Bị từ chối |
| Header bị cấm | Preflight `Request-Headers: x-admin-override` | Bị từ chối |
| Yêu cầu thật hợp lệ | GET, origin hợp lệ, người dùng có quyền | Kết quả endpoint đúng; phản hồi có `Allow-Origin` |
| Không đăng nhập | GET, origin hợp lệ, không có danh tính | Bị chặn bởi security; kết quả CORS vẫn được đánh giá riêng |
| Không có Origin | GET đã đăng nhập, không gửi `Origin` | Endpoint hoạt động theo bảo mật HTTP; không bắt buộc có `Allow-Origin` |
| `POST` thực tế | Origin hợp lệ + cookie/session | Kiểm tra thêm CSRF, phân quyền và cookie; preflight thành công chưa đủ |

Có thể bổ sung ca **yêu cầu thật từ origin bị cấm** để xác minh ứng dụng không tiết lộ `Access-Control-Allow-Origin` cho nguồn đó. Trong nhiều cấu hình Spring mặc định, actual request CORS không hợp lệ cũng bị trả `403`; phản hồi qua gateway hoặc CORS handler riêng có thể khác.

## 9. Chẩn đoán lỗi bằng HTTP thực tế

Dùng `curl` mô phỏng preflight để xem nguyên nhân ở server:

~~~bash
curl -i -X OPTIONS 'https://api.example.vn/api/profile' \
  -H 'Origin: https://portal.example.vn' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Thử lại với `Origin: https://other.example.vn` hoặc `Access-Control-Request-Method: DELETE`. Quan sát status, `Access-Control-Allow-Origin`, `Allow-Methods` và `Allow-Headers`.

**Cẩn trọng:** `curl` không chặn nội dung vì chính sách CORS như trình duyệt. Nếu `curl` đọc được body thì chưa thể kết luận JavaScript trong trang khác origin cũng đọc được.

Khi kiểm thử thất bại, lần lượt kiểm tra:

1. **Origin thực tế:** scheme, host và port có đúng allowlist không? Có reverse proxy chuyển tiếp scheme/host làm thay đổi cấu hình mong đợi không?
2. **Đường dẫn:** `/api/profile` có khớp pattern `/api/**`? Endpoint có bị gateway đổi path trước khi vào ứng dụng không?
3. **Preflight:** request có đủ `Origin` và `Access-Control-Request-Method`? Phương thức/header có được cấp quyền không?
4. **Thứ tự filter:** phản hồi `401` trên preflight có thể chỉ ra Security đã yêu cầu xác thực trước khi CORS xử lý; kiểm tra đăng ký `http.cors(...)` hoặc `CorsWebFilter`.
5. **Yêu cầu thật:** preflight `200` nhưng `POST` trả `403` có thể do CSRF hoặc phân quyền, không nhất thiết là CORS.
6. **Cache/CDN:** phản hồi phụ thuộc `Origin` cần chính sách `Vary` phù hợp; cache sai có thể phục vụ nhầm header cho frontend khác.
7. **Credential:** khi gửi cookie xuyên origin, cần cấu hình frontend, `Access-Control-Allow-Credentials`, origin tường minh và chính sách cookie cùng phù hợp.

CORS khác với các **security response header** như `Content-Security-Policy`, `X-Content-Type-Options` hay `Referrer-Policy`. Chúng giải quyết các rủi ro khác nhau; một phép thử CORS không xác nhận những header bảo vệ kia được cấu hình đúng.

## 10. Tiêu chí hoàn thành thực hành

Bạn đã kiểm chứng đúng chính sách nguồn được phép khi bộ kiểm thử chứng minh được đồng thời:

- Preflight từ `https://portal.example.vn` với `GET` và `Authorization` trả header CORS tương ứng.
- Preflight từ origin ngoài allowlist, phương thức `DELETE` hoặc header lạ bị từ chối.
- Yêu cầu API thật từ origin hợp lệ có header CORS hợp lệ, nhưng **vẫn chịu** xác thực, phân quyền và CSRF như bình thường.
- Các phép thử chạy qua **filter chain thực** của Servlet (MockMvc) hoặc Reactive (WebTestClient); không chỉ gọi trực tiếp controller và suy luận thay cho lớp bảo mật.

Đây là nền tảng để mở rộng kiểm thử ở các bài sau: kết hợp `@WithMockUser`, JWT/OAuth2/OIDC giả lập với kỳ vọng `401`/`403` và với các header bảo vệ HTTP khác, nhưng luôn giữ kết luận về **CORS** tách bạch khỏi kết luận về **quyền truy cập**.
