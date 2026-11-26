# CORS cần được kiểm tra cùng thứ tự filter thực tế

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Vì sao thứ tự filter quyết định kết quả CORS?

Một frontend tại `https://app.example.vn` gọi API tại `https://api.example.vn`. Trình duyệt gửi yêu cầu preflight `OPTIONS` để hỏi API có cho phép origin, phương thức và các header dự kiến hay không. Preflight thông thường không mang session cookie hoặc bearer token của request thật.

Nếu một filter xác thực chạy trước xử lý CORS và từ chối yêu cầu vì chưa đăng nhập, trình duyệt nhận `401 Unauthorized` trước khi API trả lời câu hỏi CORS. Developer thường nhìn thấy thông báo CORS ở Console và thử nới allowlist, trong khi nguyên nhân thật là **thứ tự xử lý trong filter chain**.

Với Spring Security, CORS phải được xử lý trước những filter yêu cầu thông tin xác thực. Khi cấu hình đúng:

- Preflight hợp lệ được xử lý ở tầng CORS và thường kết thúc tại đó; nó không cần đăng nhập và không đi vào controller nghiệp vụ.
- Actual request từ origin được phép nhận header CORS rồi tiếp tục qua authentication, authorization, CSRF và các bước còn lại.
- Actual request có thể trả `401` hoặc `403` vì bảo mật endpoint, nhưng vẫn có `Access-Control-Allow-Origin` hợp lệ để trình duyệt đọc phản hồi lỗi.

Trong module **SPRING_SECURITY_TESTING**, mục tiêu không chỉ là kiểm tra giá trị header. Bạn cần xác nhận request đã đi qua **đúng SecurityFilterChain hoặc SecurityWebFilterChain**, CORS được xử lý đúng vị trí, và các filter tùy chỉnh không chặn preflight ngoài ý muốn.

Sau bài học, bạn có thể:

1. Mô tả thứ tự giữa CORS, xác thực, phân quyền và CSRF trong Servlet/Reactive.
2. Phát hiện lỗi do custom filter, nhiều security chain hoặc cấu hình CORS trùng lặp.
3. Viết kiểm thử MockMvc và WebTestClient chạy qua filter chain của ứng dụng.
4. Phân loại `401`/`403` theo nơi phát sinh thay vì kết luận mọi lỗi đều do CORS.

## 2. Phân biệt các tầng xử lý HTTP

Trong ứng dụng Servlet, request đi qua servlet container trước, sau đó mới tới Spring Security:

~~~text
Client / Browser
      |
      v
Servlet container filters
      |
      v
DelegatingFilterProxy
      |
      v
FilterChainProxy
      |
      +--> Chọn SecurityFilterChain đầu tiên khớp request
              |
              +--> Security filters (CORS, CSRF, authentication, ...)
              |
              v
          DispatcherServlet
              |
              v
          Controller
~~~

`DelegatingFilterProxy` chuyển request tới bean Spring Security; `FilterChainProxy` chọn chuỗi bảo mật phù hợp. Nếu có nhiều `SecurityFilterChain`, chỉ chuỗi đầu tiên có matcher khớp được áp dụng cho request đó.

Trong một SecurityFilterChain đã tích hợp CORS, luồng khái quát:

~~~text
CorsFilter
    |
    +-- Preflight hợp lệ --> ghi Access-Control-Allow-* --> kết thúc
    |
    +-- Origin/method/header không hợp lệ --> từ chối
    |
    +-- Actual request hợp lệ --> tiếp tục
                                  |
                                  v
                            CSRF filter (nếu áp dụng)
                                  |
                                  v
                            Authentication
                                  |
                                  v
                            Authorization
                                  |
                                  v
                            Controller
~~~

Thứ tự chính xác của các filter khác phụ thuộc cấu hình và phiên bản Spring Security; sơ đồ chỉ nhấn mạnh yêu cầu cốt lõi: **CORS phải đứng trước filter xác thực có thể từ chối preflight**. Không nên coi sơ đồ là danh sách đầy đủ mọi filter hoặc vị trí tuyệt đối của từng filter trong mọi ứng dụng.

Với Reactive, request đi qua chuỗi `WebFilter` của WebFlux và chuỗi bảo mật reactive. `ServerHttpSecurity.cors(...)` tích hợp CORS vào `SecurityWebFilterChain` ở vị trí dành cho CORS trước các bước xác thực/phân quyền liên quan.

## 3. Preflight và actual request tác động tới filter chain ra sao?

### 3.1. Preflight

Ví dụ frontend muốn gửi POST JSON kèm token CSRF:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.vn
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-xsrf-token
~~~

CORS filter kiểm tra:

- Origin có trong allowlist không?
- Phương thức request thật `POST` có được cho phép không?
- Các tên header `content-type` và `x-xsrf-token` có được cho phép không?

Nếu hợp lệ, server trả các header `Access-Control-Allow-*`. Preflight được xử lý mà không yêu cầu session cookie, bearer token hay CSRF token của request thật. Với `CorsFilter`/`CorsWebFilter`, preflight được xử lý ở filter và không tiếp tục qua controller.

### 3.2. Actual request

Sau khi preflight thành công, trình duyệt mới gửi request thật:

~~~http
POST /api/orders HTTP/1.1
Origin: https://app.example.vn
Content-Type: application/json
X-XSRF-TOKEN: <csrf-token>
Cookie: SESSION=<session-id>
~~~

Nếu origin hợp lệ, CORS xử lý header phản hồi rồi cho request tiếp tục qua các filter bảo mật. Lúc này:

- Authentication xác định người dùng từ session/JWT hoặc cơ chế cấu hình.
- Authorization kiểm tra người dùng có quyền thực hiện hành động không.
- CSRF xác minh token nếu ứng dụng dùng cookie/session và yêu cầu bảo vệ CSRF.
- Controller chỉ chạy sau khi các bước cần thiết chấp thuận.

**Preflight thành công không cấp quyền truy cập endpoint.** Nó chỉ cho phép trình duyệt gửi request thật theo chính sách CORS.

### 3.3. Vì sao 401 có thể vẫn kèm CORS header?

Một actual request có origin hợp lệ nhưng chưa đăng nhập có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: https://app.example.vn
Vary: Origin
~~~

Đây là kết quả tốt về mặt thứ tự: CORS đã nhận diện origin hợp lệ và cho request đi tiếp; authentication sau đó từ chối vì thiếu danh tính. JavaScript có thể đọc response 401 nếu các header khác cũng phù hợp.

Ngược lại, nếu preflight nhận 401 và thiếu `Access-Control-Allow-Origin`, hãy kiểm tra xem authentication filter hoặc filter tùy chỉnh có chạy trước CORS hay không, hoặc request có đi vào security chain không được cấu hình CORS hay không.

## 4. Tích hợp CORS vào Spring Security Servlet

### 4.1. Cấu hình chuẩn qua CorsConfigurationSource

Với ứng dụng Spring MVC và Spring Security, khai báo `CorsConfigurationSource` và bật `.cors(...)` trong chuỗi bảo mật:

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
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-XSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

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
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Khi có một bean `CorsConfigurationSource` phù hợp, `.cors(Customizer.withDefaults())` cho phép Spring Security dùng cấu hình CORS đó. Nếu ứng dụng có nhiều nguồn cấu hình hoặc nhiều security chain, hãy chỉ rõ source tương ứng cho từng chain để tránh phụ thuộc vào lựa chọn không chủ định.

**Không dùng `permitAll()` cho OPTIONS như cách duy nhất để sửa CORS.** Quy tắc authorization có thể cho phép OPTIONS ở tầng quyền, nhưng nó không tự tạo `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` hoặc `Access-Control-Allow-Headers`. CORS vẫn cần được cấu hình và đặt đúng vị trí.

### 4.2. Container CorsFilter và CORS trong security chain

Có hai cách triển khai thường gặp:

1. Tích hợp CORS trong Spring Security bằng `.cors(...)` và `CorsConfigurationSource`.
2. Đăng ký một `CorsFilter` ở cấp servlet container để chạy trước `DelegatingFilterProxy`.

Cả hai có thể hoạt động nếu được tổ chức có chủ đích. Tuy nhiên, **không đăng ký cùng một chính sách ở nhiều tầng một cách vô tình**. Ví dụ, khai báo `CorsFilter` thành bean có thể khiến Spring Boot tự đăng ký nó như servlet filter, đồng thời cấu hình `.cors(...)` lại tạo filter CORS trong SecurityFilterChain. Khi đó request có thể bị xử lý hai lần, header trùng lặp hoặc kết quả khác nhau theo thứ tự đăng ký.

Nếu chọn CORS trong security chain, thường không cần thêm một container `CorsFilter` thứ hai. Nếu phải đăng ký filter ở container, kiểm tra thứ tự để nó chạy trước security proxy và không lặp lại trong chain.

### 4.3. Filter tùy chỉnh có thể chặn preflight

Giả sử ứng dụng có filter kiểm tra API key hoặc token trước khi request vào controller. Nếu filter đó được đặt trước CORS và yêu cầu header xác thực trên mọi request, preflight có thể bị từ chối vì trình duyệt chưa gửi thông tin xác thực của request thật.

Với filter thuộc SecurityFilterChain, có thể đặt nó sau CORS khi nghiệp vụ cho phép:

~~~java
import org.springframework.web.filter.CorsFilter;

// Sau khi cấu hình http.cors(...)
http.addFilterAfter(apiAuditFilter, CorsFilter.class);
~~~

`addFilterAfter` chỉ là ví dụ về vị trí tương đối. Hãy chọn vị trí dựa trên nhiệm vụ thực tế của filter; một filter kiểm tra dữ liệu đầu vào, rate limit hoặc chặn IP có thể có yêu cầu khác. Nếu filter cần chạy trước CORS vì lý do kiến trúc, nó phải nhận diện preflight và không đòi credential của request thật một cách sai lệch.

Đối với servlet filter đăng ký ở container, thứ tự được điều khiển bởi cơ chế đăng ký filter của container/Spring Boot, không phải `addFilterAfter` trong `HttpSecurity`.

## 5. Nhiều SecurityFilterChain: kiểm tra đúng chain được chọn

Một ứng dụng có thể có nhiều `SecurityFilterChain`, ví dụ:

- `/api/**` là API xác thực bằng JWT.
- `/admin/**` là trang quản trị dùng session.
- Các đường dẫn còn lại dùng chính sách khác.

`FilterChainProxy` chọn **chuỗi đầu tiên khớp request**. Nếu chỉ cấu hình CORS trong chain `/api/**` nhưng request preflight lại đi vào chain quản trị hoặc chain fallback, kết quả có thể là 401/403 và không có CORS header như mong đợi.

Ví dụ cấu trúc:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http,
                             CorsConfigurationSource cors) throws Exception {
    return http
        .securityMatcher("/api/**")
        .cors(c -> c.configurationSource(cors))
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a
            .requestMatchers("/admin/**").authenticated()
            .anyRequest().permitAll())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Ví dụ giả định các bean JWT và form login đã được cấu hình cho ứng dụng. Chain API có CORS source riêng; chain web không tự kế thừa CORS source của API. Nếu frontend khác origin cũng cần gọi `/admin/**`, hãy cấu hình CORS cho chain đó theo chính sách riêng.

Khi debug, xác minh:

1. Request path và method thực tế có khớp `securityMatcher` nào?
2. Có chain nào đứng trước khớp rộng hơn và chiếm request không?
3. Chain được chọn có tích hợp CORS không?
4. CORS source đăng ký pattern cho đúng path chưa?
5. Một request thật và preflight cùng path có thực sự đi vào cùng chain dự kiến không?

**Lỗi matcher** thường khó phát hiện nếu chỉ test controller. Một test integration qua security chain là bằng chứng tốt hơn.

## 6. Tích hợp CORS trong Spring Security Reactive

Với WebFlux, cấu hình CORS thông qua `ServerHttpSecurity` và reactive `CorsConfigurationSource`:

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
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-XSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, CorsConfigurationSource cors) {
        return http
            .cors(c -> c.configurationSource(cors))
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

`ServerHttpSecurity.cors(...)` tích hợp CORS vào security web filter chain. Một preflight hợp lệ được CORS xử lý trước các bước xác thực. Actual request hợp lệ tiếp tục qua authentication và authorization.

Có thể dùng `CorsWebFilter` độc lập, nhưng khi đó cần quản lý vị trí trong WebFlux filter chain và tránh cùng lúc cấu hình một policy khác trong `ServerHttpSecurity`. Không nên đăng ký hai `CorsWebFilter` cùng xử lý một request nếu chưa có lý do và kiểm soát rõ ràng.

Nếu có nhiều `SecurityWebFilterChain`, cần xem xét thứ tự và matcher của từng chain tương tự Servlet. Cấu hình CORS ở một chain không tự động áp dụng cho chain khác.

## 7. MockMvc: chứng minh thứ tự CORS trước authentication

### 7.1. Tạo preflight không có danh tính

Test quan trọng nhất: preflight hợp lệ **không đăng nhập** vẫn phải được xử lý và trả header CORS. Dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để request đi qua filter của ứng dụng:

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
import static org.springframework.security.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletCorsOrderTests {

    private static final String ORIGIN = "https://app.example.vn";

    @Autowired
    MockMvc mvc;

    @Test
    void preflightDuocXuLyTruocAuthentication() throws Exception {
        mvc.perform(options("/api/orders")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "content-type,x-xsrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ORIGIN))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                containsString("POST")))
            .andExpect(header().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS));
    }
}
~~~

Test không dùng `@WithMockUser`, không gửi cookie và không gửi bearer token. Nếu preflight chỉ thành công khi thêm `@WithMockUser`, hãy kiểm tra CORS filter có chạy trước authentication không và request có bị filter tùy chỉnh chặn trước CORS không.

### 7.2. Actual request chưa xác thực vẫn có CORS header

~~~java
@Test
void actualRequestChuaDangNhapBi401NhungCorsDaXuLy() throws Exception {
    mvc.perform(get("/api/orders")
            .header(HttpHeaders.ORIGIN, "https://app.example.vn"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
            "https://app.example.vn"));
}
~~~

Phép thử này cần đặt trong cùng lớp test hoặc một lớp có đủ import và bean. Kỳ vọng `401` giả định ứng dụng dùng HTTP Basic hoặc entry point trả 401; form login có thể redirect. Điều cần xác nhận là response của request từ origin được phép vẫn có CORS header dù authentication từ chối.

### 7.3. Actual request đã xác thực đi qua toàn bộ chuỗi

~~~java
@Test
@WithMockUser(username = "learner")
void actualRequestDaXacThucDuocXuLy() throws Exception {
    mvc.perform(get("/api/orders")
            .header(HttpHeaders.ORIGIN, "https://app.example.vn"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
            "https://app.example.vn"));
}
~~~

`@WithMockUser` tạo `SecurityContext` cho test. Nó không kiểm tra token mạng hoặc session cookie thật, nhưng giúp xác nhận request sau bước CORS có thể đi tiếp khi security context hợp lệ.

### 7.4. Không bỏ qua filter khi tạo MockMvc

Các phép thử trên giả định MockMvc được tạo từ application context và có filter của ứng dụng. Nếu dùng `MockMvcBuilders.standaloneSetup(...)`, bạn phải chủ động thêm filter hoặc security config cần thiết; nếu không, test có thể gọi controller mà không chạy Spring Security.

`@AutoConfigureMockMvc` mặc định thêm các servlet filter được đăng ký trong application context. Không đặt `addFilters = false` cho test nhằm chứng minh thứ tự filter. Khi cần test cấu hình tối giản, xác nhận filter chain được gắn vào MockMvc trước khi kết luận.

## 8. WebTestClient: chứng minh thứ tự CORS trong WebFlux

Với WebFlux, test bằng `@SpringBootTest` và `@AutoConfigureWebTestClient` để gọi ứng dụng qua WebTestClient đã cấu hình:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCorsOrderTests {

    @Autowired
    WebTestClient client;

    @Test
    void preflightKhongCanAuthentication() {
        client.options().uri("/api/orders")
            .header(HttpHeaders.ORIGIN, "https://app.example.vn")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-xsrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.vn")
            .expectHeader().exists(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS);
    }

    @Test
    void actualRequestChuaDangNhapVanCoCorsHeader() {
        client.get().uri("/api/orders")
            .header(HttpHeaders.ORIGIN, "https://app.example.vn")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.vn");
    }
}
~~~

Kỳ vọng `401` giả định cấu hình HTTP Basic/entry point trả 401. Nếu dùng form login hoặc entry point tùy chỉnh, hãy đổi status theo hợp đồng xác thực nhưng vẫn xác nhận CORS header của origin hợp lệ.

Nếu tạo WebTestClient thủ công bằng `bindToApplicationContext`, cần áp dụng cấu hình Spring Security Test tương ứng, ví dụ `SecurityMockServerConfigurers.springSecurity()`. Không dùng client chỉ bind vào controller rồi suy luận rằng security web filter chain đã chạy.

## 9. Kiểm tra filter tùy chỉnh và thứ tự thực tế

### 9.1. Nhận diện filter nào đã từ chối request

Khi preflight trả 401/403, đừng sửa allowlist ngay. Hãy xác định request dừng ở đâu:

- CORS filter có nhận được request không?
- Request có match đúng `SecurityFilterChain`/`SecurityWebFilterChain` không?
- Có filter API key/JWT tùy chỉnh nào chạy trước CORS không?
- Có servlet container filter hoặc gateway từ chối trước `DelegatingFilterProxy` không?
- Có filter CORS thứ hai ghi đè hoặc từ chối response không?

Trong môi trường phát triển/test, có thể bật log chi tiết của Spring Security:

~~~properties
logging.level.org.springframework.security=TRACE
~~~

Log TRACE có thể chứa nhiều chi tiết về filter chain và quyết định bảo mật. Chỉ bật trong môi trường kiểm soát, tránh lưu thông tin nhạy cảm vào log chia sẻ. Debugger đặt breakpoint ở filter tùy chỉnh và CORS processor cũng giúp xác định thứ tự thực tế.

### 9.2. Phân biệt các triệu chứng

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| Preflight trả 401, không có ACAO | Authentication/custom filter chạy trước CORS; request chọn sai chain; CORS chưa được tích hợp |
| Preflight trả 403, không có ACAO | CORS từ chối origin/method/header; hoặc filter/gateway khác từ chối trước CORS |
| Preflight trả 200, request thật không gửi | Header Allow-Origin/Methods/Headers/Credentials thiếu hoặc sai; browser policy |
| Preflight 200, actual trả 401 nhưng có ACAO | CORS đã chạy; authentication từ chối actual request |
| Preflight 200, actual trả 403 có ACAO | Kiểm tra authorization, CSRF hoặc logic ứng dụng |
| OPTIONS được permitAll nhưng thiếu ACAO | Đã mở authorization nhưng chưa cấu hình CORS |
| Một đường dẫn có CORS header, đường khác không | Các path chọn chain khác nhau hoặc CORS mapping không khớp |
| Response có hai ACAO hoặc giá trị ghép | Có nhiều tầng cùng ghi CORS header |
| MockMvc test qua nhưng browser lỗi | Test chưa đi qua đúng filter, cookie/browser policy, proxy hoặc cache |

Status một mình không xác định filter nào từ chối. Đọc cả response header, log filter chain và request matcher.

### 9.3. CORS ở gateway và CORS ở ứng dụng

Một số kiến trúc có API gateway/reverse proxy đứng trước Spring. Gateway có thể tự trả preflight, thêm CORS header hoặc từ chối request trước khi tới ứng dụng. Trong trường hợp này:

- Test MockMvc/WebTestClient tại ứng dụng xác minh chính sách trong Spring.
- Test qua URL gateway xác minh hành vi của toàn tuyến.
- Tránh để gateway và ứng dụng phát hai bộ `Access-Control-Allow-Origin` không thống nhất.
- Nếu gateway kết thúc preflight, có thể request OPTIONS không bao giờ tới Spring; đừng kỳ vọng breakpoint trong ứng dụng được gọi.

Phải xác định **thành phần sở hữu chính sách CORS** trong mỗi môi trường và kiểm tra response cuối cùng mà trình duyệt nhận được.

## 10. Bảng kiểm thử tích hợp theo thứ tự filter

| Mã ca | Request | Trạng thái danh tính | Kỳ vọng | Ý nghĩa |
| --- | --- | --- | --- | --- |
| ORDER-01 | Preflight origin/method/header hợp lệ | Không đăng nhập | 200/204 + Allow-* phù hợp | CORS xử lý trước authentication |
| ORDER-02 | Preflight origin bị cấm | Không đăng nhập | Bị từ chối, không ACAO | CORS policy từ chối |
| ORDER-03 | Actual GET origin hợp lệ | Không đăng nhập | 401 (tùy entry point) + ACAO | CORS trước authentication |
| ORDER-04 | Actual GET origin hợp lệ | Đã xác thực | 200 + ACAO | Request đi qua security chain |
| ORDER-05 | Actual GET origin hợp lệ | Đã xác thực, thiếu authority | 403 + ACAO | Authorization từ chối sau CORS |
| ORDER-06 | Actual POST origin hợp lệ | Đã xác thực, thiếu CSRF | 403 + ACAO (nếu CSRF là nguyên nhân) | CSRF vẫn được áp dụng |
| ORDER-07 | Preflight tới path thuộc chain khác | Không đăng nhập | Theo policy chain tương ứng | Xác minh matcher/chain |
| ORDER-08 | Preflight với custom filter bật | Không đăng nhập | Vẫn được CORS xử lý | Phát hiện filter tùy chỉnh chặn sớm |
| ORDER-09 | Response qua gateway | Theo request | Header CORS duy nhất, nhất quán | Xác minh toàn tuyến |

Các status trong bảng là kỳ vọng cho cấu hình minh họa; ứng dụng có thể có entry point, exception handler hoặc gateway trả status khác. Cần ghi rõ hợp đồng response của hệ thống.

## 11. Những lỗi cấu hình thường gặp

**Chỉ cho phép OPTIONS bằng authorization rule.** `permitAll()` không tạo header CORS. Phải cấu hình CORS source và thứ tự filter.

**Đặt custom authentication filter trước CORS.** Filter có thể đòi token trên preflight. Xem xét đưa filter xuống sau CORS hoặc điều chỉnh logic để không yêu cầu credential trên preflight.

**Cấu hình CORS ở chain không được chọn.** `securityMatcher` và `@Order` quyết định chain. Kiểm tra path thực tế và thứ tự chain.

**Đăng ký CorsFilter hai lần.** Một filter ở container và một filter trong security chain có thể tạo header trùng hoặc kết quả khó dự đoán. Chọn một cách tích hợp có chủ đích.

**Chỉ test controller.** `standaloneSetup` hoặc test gọi trực tiếp controller không chứng minh CORS/security filter đã chạy. Dùng test tích hợp qua application context hoặc gắn filter rõ ràng.

**Cho rằng 401 là lỗi CORS.** Nếu actual response 401 vẫn có ACAO đúng, CORS đã cho phép origin; authentication mới là bước từ chối.

**Cho rằng preflight thành công nghĩa là endpoint an toàn.** Request thật vẫn phải qua xác thực, phân quyền, CSRF và kiểm tra nghiệp vụ.

## 12. Thực hành và tiêu chí hoàn thành

Một API Spring Security có frontend `https://app.example.vn`, endpoint `/api/orders` và filter tùy chỉnh kiểm tra API key. Hãy thực hiện:

1. Cấu hình CORS bằng `CorsConfigurationSource` và tích hợp `.cors(...)` vào đúng security chain.
2. Viết test preflight hợp lệ không có `@WithMockUser`, cookie hoặc bearer token. Xác nhận status và `Access-Control-Allow-*`.
3. Viết test preflight origin sai và method/header sai. Xác nhận bị từ chối, không cấp `Access-Control-Allow-Origin`.
4. Viết test actual GET origin hợp lệ nhưng chưa đăng nhập. Xác nhận authentication từ chối nhưng response vẫn có CORS header.
5. Viết test actual request có danh tính giả lập để chứng minh request tiếp tục qua authorization.
6. Đặt filter API key ở vị trí phù hợp; chạy lại preflight để bảo đảm nó không yêu cầu credential của request thật.
7. Nếu có nhiều security chain, kiểm tra request matcher và policy CORS của từng chain liên quan.
8. Chạy tương đương trên WebFlux bằng `WebTestClient` nếu ứng dụng dùng Reactive.
9. Đối chiếu log/debugger để xác nhận filter chain được chọn và thứ tự thực tế.
10. Nếu có gateway, kiểm tra cả response ở ứng dụng và response cuối tuyến.

Bạn hoàn thành khi chứng minh được **preflight được CORS xử lý trước authentication**, actual request tiếp tục qua các filter bảo mật theo đúng thứ tự, và các filter tùy chỉnh/multiple chains/gateway không làm sai kết quả.

**Điểm cần nhớ:** CORS là một phần của chuỗi xử lý HTTP. Một allowlist chính xác vẫn không đủ nếu filter xác thực chặn preflight trước khi CORS được thực thi. Kiểm thử Spring Security cần đi qua filter chain thực tế để chứng minh cả vị trí xử lý CORS lẫn kết quả xác thực, phân quyền và CSRF của request thật.
