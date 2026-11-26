# Phân biệt quyền đọc phản hồi từ trình duyệt với quyền gọi API trên máy chủ

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng spring-security-test trên ứng dụng Servlet và Reactive.

## 1. CORS trả lời câu hỏi nào?

Một trang web tại `https://attacker.example` có thể thử gửi request tới API ngân hàng tại `https://api.example.vn`. Browser có thể gửi request đó, nhưng chính sách Same-Origin Policy thường không cho JavaScript của trang attacker đọc response từ origin khác. CORS là cơ chế server dùng để nói rõ những origin nào được browser cho phép đọc response.

Điểm cần phân biệt:

- **Quyền đọc response:** browser có cho JavaScript của một origin truy cập status, header và body của response hay không.
- **Quyền gọi API:** server có nhận request, xác thực người gọi, kiểm tra quyền và thực hiện hành động hay không.

Đây là hai quyết định khác nhau. CORS chủ yếu điều khiển việc browser chia sẻ response với mã JavaScript. Authentication và authorization bảo vệ API ở phía server. CSRF protection bảo vệ các request có thể tự động mang thông tin xác thực của browser, đặc biệt là session cookie.

Ví dụ, một trang độc hại gửi một request POST dạng HTML form tới endpoint đổi địa chỉ giao hàng. Nếu request thuộc loại đơn giản, browser có thể gửi request thật tới server mà không cần preflight. Server có thể thực hiện thay đổi nếu session cookie hợp lệ và endpoint thiếu kiểm tra CSRF/authorization phù hợp. Sau đó browser chặn JavaScript của trang độc hại đọc response vì origin không được CORS cho phép. **Việc không đọc được response không có nghĩa là server chưa thực hiện hành động.**

Trong module **SPRING_SECURITY_TESTING**, bài học này giúp bạn kiểm thử riêng từng lớp: CORS quyết định browser có thể đọc response; authentication, authorization và CSRF quyết định server có chấp nhận request và cho phép hành động hay không.

Sau bài học, bạn có thể:

1. Phân biệt browser access control với API authentication/authorization.
2. Giải thích vì sao simple request có thể tới server dù JavaScript không đọc được response.
3. Hiểu vai trò và giới hạn của preflight.
4. Cấu hình CORS cùng các quy tắc bảo vệ endpoint trong Spring Security Servlet và Reactive.
5. Viết test chứng minh CORS không thay thế xác thực, phân quyền hoặc CSRF.

## 2. Hai câu hỏi độc lập trong một request

Hãy nhìn một request cross-origin như hai giai đoạn quyết định:

~~~mermaid
flowchart TD
    A["JavaScript tại origin A gọi API tại origin B"] --> B["Browser gửi request hoặc preflight"]
    B --> C["Server nhận HTTP request"]
    C --> D["CORS policy xử lý Origin / preflight"]
    D --> E["Authentication: người gọi là ai?"]
    E --> F["Authorization: người gọi được làm gì?"]
    F --> G["CSRF và quy tắc nghiệp vụ nếu áp dụng"]
    G --> H["Server tạo response"]
    H --> I["Browser kiểm tra CORS response headers"]
    I -->|Được chia sẻ| J["JavaScript đọc response"]
    I -->|Không được chia sẻ| K["JavaScript nhận lỗi CORS"]
~~~

Sơ đồ chỉ mô tả các quyết định về mặt khái niệm. Trong Spring, CORS filter thường chạy sớm để xử lý preflight và ghi header; authentication, authorization và CSRF được thực thi ở các vị trí tương ứng trong security filter chain. Browser kiểm tra response sau khi server đã xử lý request.

Hai câu hỏi cần được trả lời riêng:

| Câu hỏi | Thành phần quyết định | Ví dụ |
| --- | --- | --- |
| Browser có cho JavaScript đọc response không? | Same-Origin Policy và CORS enforcement của browser | ACAO có khớp origin trang gọi không? |
| Server có chấp nhận request không? | Authentication, authorization, CSRF, validation và business rules | User có đăng nhập và có quyền sửa đơn hàng không? |

Một response có thể được server tạo thành công nhưng browser không cho JavaScript đọc. Ngược lại, browser có thể cho JavaScript đọc một response 401 hoặc 403 vì CORS header hợp lệ. CORS không biến 401 thành 200 và cũng không cấp quyền cho người gọi.

## 3. Browser có thể gửi request mà không cho JavaScript đọc response

### 3.1. Simple request không cần preflight

Một số request cross-origin không cần preflight. Ví dụ phổ biến gồm:

- GET hoặc HEAD với các header thuộc CORS-safelisted request headers.
- POST dùng content type thuộc nhóm safelisted như application/x-www-form-urlencoded, multipart/form-data hoặc text/plain, cùng các header đáp ứng điều kiện của chuẩn.

Ví dụ một form HTML gửi dữ liệu:

~~~html
<form action="https://api.example.vn/account/email" method="post">
  <input name="email" value="attacker-controlled@example.test">
  <button type="submit">Submit</button>
</form>
~~~

Browser có thể gửi POST tới server mà không cần OPTIONS preflight. CORS vẫn được kiểm tra ở response để quyết định JavaScript có thể đọc dữ liệu hay không; form navigation cũng không cần JavaScript đọc response để request được gửi.

Nếu server dựa vào giả định “origin lạ không thể gửi request”, endpoint có thể bị CSRF. Với session cookie, browser có thể tự đính kèm cookie nếu cookie và chính sách browser cho phép. Server phải xác minh CSRF token và quyền của người dùng trước khi thay đổi trạng thái.

### 3.2. JavaScript có thể nhận lỗi CORS sau khi server đã xử lý

Giả sử frontend độc hại gửi request đơn giản:

~~~javascript
try {
  const response = await fetch(
    "https://api.example.vn/account/email",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: "email=attacker-controlled%40example.test",
      credentials: "include"
    }
  );

  console.log(await response.text());
} catch (error) {
  console.error("Browser không cho đọc response:", error);
}
~~~

Nếu server không cho origin này đọc response, Fetch có thể reject với lỗi CORS. Tuy nhiên, điều đó tự nó không chứng minh server chưa nhận POST. Nếu endpoint không có CSRF protection và session cookie được gửi, hành động có thể đã xảy ra.

Cách xử lý đúng là bảo vệ endpoint ở phía server:

- Yêu cầu authentication phù hợp.
- Kiểm tra authorization cho đúng tài nguyên và hành động.
- Bảo vệ CSRF khi dùng cookie/session hoặc credential tự động được browser gửi.
- Kiểm tra input và business invariants.
- Dùng CORS để giới hạn những frontend nào được đọc response.

### 3.3. no-cors không phải cách vượt CORS

Fetch mode `no-cors` không tắt Same-Origin Policy. Browser giới hạn method/header được gửi và trả về opaque response mà JavaScript không thể đọc status, headers hoặc body như response thông thường.

Không dùng no-cors để “sửa” lỗi CORS. Nó không cấp quyền đọc response và không thay thế authorization.

## 4. Preflight giới hạn việc gửi actual request trong một số trường hợp

### 4.1. Khi nào browser gửi preflight?

Một request cần preflight khi method, request header hoặc content type không thuộc nhóm CORS-safelisted theo chuẩn. Ví dụ Fetch gửi JSON với Authorization header:

~~~javascript
const response = await fetch("https://api.example.vn/transfers", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer " + accessToken
  },
  body: JSON.stringify({ destination: "account-123", amount: 25 }),
  credentials: "omit"
});
~~~

Browser thường gửi OPTIONS trước:

~~~http
OPTIONS /transfers HTTP/1.1
Origin: https://app.example.vn
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Preflight hỏi server liệu origin, method và request headers dự kiến có được cho phép không. Nếu preflight không được chấp thuận, browser không gửi actual POST trong luồng Fetch đó.

### 4.2. Preflight không xác thực người dùng

Preflight thường không mang session cookie hoặc bearer token của actual request. Vì vậy, cấu hình CORS cần xử lý OPTIONS trước những filter đòi hỏi người dùng đăng nhập. Preflight hợp lệ được CORS filter trả lời; actual request sau đó vẫn phải qua authentication, authorization và CSRF nếu áp dụng.

Không yêu cầu user phải đăng nhập chỉ để trả lời câu hỏi CORS của preflight. Đồng thời, không dùng quy tắc permitAll cho OPTIONS như cách duy nhất để “bật CORS”: authorization rule không tự tạo ACAO, Allow-Methods hoặc Allow-Headers.

### 4.3. Preflight thất bại không phải cơ chế bảo vệ API

Khi preflight bị từ chối, browser không gửi actual request trong lần Fetch đó. Đây là giới hạn do browser thực thi. Client ngoài browser như curl, Postman, ứng dụng di động hoặc service backend có thể gọi trực tiếp API mà không chạy thuật toán preflight.

Ngay cả request từ một website độc hại cũng có thể thuộc loại simple request và được gửi trước khi browser kiểm tra response. Vì vậy, không dựa vào preflight để ngăn người gọi thực hiện hành động trên server.

## 5. Authentication, authorization và CSRF bảo vệ API

### 5.1. Authentication: xác định danh tính

Authentication trả lời người gọi là ai. Ví dụ:

- Session cookie hợp lệ xác định phiên đăng nhập.
- Bearer access token được xác minh chữ ký, issuer, audience, expiry và các claim cần thiết.
- HTTP Basic xác minh credential theo cơ chế được cấu hình.

CORS không xác minh bất kỳ credential nào. Một origin được allowlist vẫn có thể gửi request thiếu token và nhận 401. Một client không phải browser có thể gửi token hợp lệ dù nó không thuộc origin frontend nào.

### 5.2. Authorization: kiểm tra quyền trên từng hành động

Sau authentication, server cần kiểm tra người dùng có quyền đọc hoặc thay đổi tài nguyên cụ thể không. Ví dụ user có thể đọc hồ sơ của chính mình nhưng không được chuyển tiền từ tài khoản người khác.

Không dùng origin như một role hoặc danh tính. Header Origin cho biết ngữ cảnh origin mà browser gửi request; client ngoài browser có thể tự tạo header đó. Quyết định authorization phải dựa trên principal, authority, quyền sở hữu tài nguyên và quy tắc nghiệp vụ.

### 5.3. CSRF: bảo vệ credential tự động được browser gửi

Khi ứng dụng dùng session cookie, browser có thể tự đính kèm cookie vào request phù hợp. Website khác có thể khiến browser gửi request bằng form hoặc một số loại request đơn giản. Nếu server chỉ kiểm tra session mà không kiểm tra CSRF, request giả mạo có thể thay đổi dữ liệu dưới danh nghĩa người dùng.

CSRF protection yêu cầu một bằng chứng mà website bên ngoài không thể tự tạo hợp lệ, thường là token gắn với session/request. Với Spring Security, CSRF protection được bật mặc định cho cấu hình thông thường; hãy giữ nó khi dùng cookie/session và kiểm thử cả token hợp lệ lẫn token thiếu/sai.

SameSite cookie là một lớp giảm rủi ro, nhưng không nên coi nó là thay thế chung cho CSRF protection. Hành vi phụ thuộc SameSite mode, site relationship, browser và luồng ứng dụng.

Với API chỉ dùng bearer token được JavaScript chủ động gắn vào Authorization header và không dựa vào credential tự động của browser, mô hình CSRF có thể khác. Chỉ tắt CSRF sau khi đã xác định rõ cách credential được lưu và gửi, các endpoint nào có thể nhận cookie, và không có đường xác thực ambient nào còn được dùng.

## 6. CORS và API authorization trong Spring Security Servlet

Ví dụ dưới đây cho phép một frontend cụ thể đọc response, đồng thời bảo vệ API bằng authentication và authority. CSRF vẫn được giữ trong cấu hình vì ví dụ giả định ứng dụng có thể dùng session/cookie.

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
class ServletApiSecurityConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.vn"));
        cors.setAllowedMethods(List.of("GET", "POST"));
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
    SecurityFilterChain securityFilterChain(HttpSecurity http,
            CorsConfigurationSource cors) throws Exception {
        return http
            .cors(config -> config.configurationSource(cors))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/profile").authenticated()
                .requestMatchers(HttpMethod.POST, "/api/transfers")
                    .hasAuthority("transfer:write")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Cấu hình thể hiện hai chính sách riêng:

- CORS cho phép browser origin `https://app.example.vn` đọc response cho các request phù hợp.
- Authorization yêu cầu danh tính cho GET profile và authority `transfer:write` cho POST transfer.

Origin được allowlist không tự nhận được authority. Người dùng chưa đăng nhập vẫn có thể nhận 401; người dùng đã đăng nhập nhưng thiếu quyền vẫn nhận 403. CORS header có thể xuất hiện trên các response lỗi đó để frontend được phép đọc chúng.

Nếu ứng dụng chỉ dùng bearer token và không dùng cookie/session, hãy thiết kế CSRF policy theo mô hình xác thực thực tế. Không tắt CSRF chỉ vì endpoint có prefix /api hoặc vì request có CORS.

## 7. Cấu hình tương đương trong Spring Security Reactive

Với WebFlux, cấu hình CORS qua reactive CorsConfigurationSource và tích hợp vào ServerHttpSecurity:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
class ReactiveApiSecurityConfig {

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
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, CorsConfigurationSource cors) {
        return http
            .cors(config -> config.configurationSource(cors))
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/profile").authenticated()
                .pathMatchers(HttpMethod.POST, "/api/transfers")
                    .hasAuthority("transfer:write")
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là cấu hình minh họa cho WebFlux. Cần kiểm tra API DSL theo phiên bản Spring Security của dự án. CORS và authorization vẫn là hai policy riêng: cấu hình CORS không tự cấp authority và security rule vẫn quyết định request có được thực hiện hay không.

## 8. MockMvc: kiểm chứng hai quyết định riêng biệt

MockMvc có thể kiểm tra CORS filter và security filter chain nếu được tạo từ application context với filter được bật. Các ví dụ dưới đây giả định endpoint tồn tại theo cấu hình ở phần Servlet.

### 8.1. Origin hợp lệ nhưng chưa xác thực vẫn nhận 401

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsAndAuthorizationTests {

    @Autowired
    MockMvc mvc;

    private static final String ALLOWED_ORIGIN =
        "https://app.example.vn";

    @Test
    void allowedOriginDoesNotBypassAuthentication() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN));
    }
}
~~~

Test này cho thấy CORS cho phép origin đọc response 401. Nó không đăng nhập người dùng và không cấp quyền truy cập profile.

### 8.2. User đã xác thực nhưng thiếu authority vẫn nhận 403

~~~java
import org.springframework.security.test.context.support.WithMockUser;

@Test
@WithMockUser(username = "reader", authorities = "profile:read")
void authenticatedUserWithoutTransferAuthorityIsForbidden()
        throws Exception {
    mvc.perform(post("/api/transfers")
            .with(csrf())
            .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
            .contentType("application/json")
            .content("{\"destination\":\"account-123\",\"amount\":25}"))
        .andExpect(status().isForbidden())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN));
}
~~~

Ví dụ giả định endpoint yêu cầu authority `transfer:write` và user chỉ có `profile:read`. CSRF token được thêm để test tập trung vào authorization. Nếu endpoint có validation hoặc business rules khác, dữ liệu test cần đáp ứng các điều kiện đó để kết quả 403 đến từ đúng lớp đang kiểm tra.

### 8.3. Có authority và CSRF hợp lệ thì request mới có thể thành công

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
@WithMockUser(username = "operator", authorities = "transfer:write")
void authorizedUserWithCsrfCanCallTransferEndpoint() throws Exception {
    mvc.perform(post("/api/transfers")
            .with(csrf())
            .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
            .contentType("application/json")
            .content("{\"destination\":\"account-123\",\"amount\":25}"))
        .andExpect(status().is2xxSuccessful())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN));
}
~~~

Test này cần endpoint có thể trả thành công với payload minh họa. `@WithMockUser` tạo SecurityContext cho test; nó không chứng minh session cookie hoặc bearer token thật được browser gửi.

### 8.4. Preflight hợp lệ không cần đăng nhập

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;

@Test
void preflightIsHandledWithoutAuthenticatedUser() throws Exception {
    mvc.perform(options("/api/transfers")
            .header(HttpHeaders.ORIGIN, ALLOWED_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-xsrf-token"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED_ORIGIN))
        .andExpect(header().string(
            HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
            org.hamcrest.Matchers.containsString("POST")));
}
~~~

Preflight được CORS xử lý trước authentication. Nó không chứng minh actual POST có quyền thành công; actual request vẫn phải qua CSRF, authentication, authorization và business validation.

### 8.5. Origin không được allowlist không nhận quyền đọc response

~~~java
@Test
void disallowedOriginDoesNotReceiveCorsPermission() throws Exception {
    mvc.perform(get("/api/profile")
            .header(HttpHeaders.ORIGIN, "https://attacker.example"))
        .andExpect(header().doesNotExist(
            HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
}
~~~

Với cấu hình Spring CorsFilter mặc định, request CORS có origin không hợp lệ thường bị từ chối trước khi tới controller; response không có ACAO cho origin đó. Assertion này kiểm tra CORS behavior của Spring. Nó **không phải** test authorization và cũng không chứng minh một client trực tiếp không thể gọi endpoint.

## 9. WebTestClient: kiểm chứng CORS không cấp quyền trong Reactive

WebTestClient cần được gắn với application context và SecurityWebFilterChain. Ví dụ kiểm tra origin hợp lệ nhưng người dùng chưa xác thực:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCorsAuthorizationTests {

    @Autowired
    WebTestClient client;

    @Test
    void allowedOriginStillNeedsAuthentication() {
        client.get().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, "https://app.example.vn")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.vn");
    }

    @Test
    void validPreflightDoesNotNeedUserAuthentication() {
        client.options().uri("/api/transfers")
            .header(HttpHeaders.ORIGIN, "https://app.example.vn")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-xsrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.vn");
    }

    @Test
    void disallowedOriginDoesNotReceiveAllowOrigin() {
        client.get().uri("/api/profile")
            .header(HttpHeaders.ORIGIN, "https://attacker.example")
            .exchange()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }
}
~~~

Kỳ vọng 401 giả định entry point của ứng dụng trả 401. Nếu ứng dụng dùng form login, có thể nhận redirect; khi đó kiểm tra status/Location tương ứng và vẫn xác nhận ACAO trên response nếu origin hợp lệ.

Test Reactive về authorization nên dùng mock security context với authority cụ thể và endpoint tương ứng. Hãy kiểm tra độc lập request thiếu authority, request thiếu CSRF token (nếu CSRF áp dụng) và request hợp lệ. Không dùng test preflight để kết luận endpoint được phép thực hiện hành động.

## 10. Những client nào chịu CORS?

| Client | Browser thực thi CORS? | Có thể gọi API trực tiếp? | Ai bảo vệ API? |
| --- | --- | --- | --- |
| JavaScript Fetch/XHR trong browser | Có | Có, theo giới hạn của browser | Server authentication, authorization, CSRF và CORS response policy |
| HTML form/navigation | Không dùng CORS để cho JavaScript đọc response như Fetch | Có thể gửi form/navigation cross-origin | Server authentication, authorization, CSRF |
| curl | Không | Có | Server authentication, authorization, network policy |
| Postman/Insomnia | Không theo browser enforcement | Có | Server authentication, authorization |
| Backend service | Không | Có | Credential/service identity, authorization, network policy |
| Mobile application native | Thông thường không áp dụng browser CORS | Có | Token/certificate, authentication, authorization |

Header Origin có thể xuất hiện trong một số request không phải browser, nhưng client trực tiếp có thể tự đặt hoặc bỏ header đó. Không dùng Origin làm credential hoặc bằng chứng danh tính. Nếu cần hạn chế nguồn truy cập ở network layer, dùng firewall, gateway, private networking hoặc mTLS theo kiến trúc; CORS không thay thế các biện pháp đó.

## 11. Các hiểu lầm thường gặp

**“CORS chặn website khác gọi API.”** CORS chủ yếu kiểm soát browser chia sẻ response với JavaScript. Một simple request có thể tới server; client ngoài browser không thực thi CORS.

**“Fetch báo lỗi CORS nên server chưa làm gì.”** Sai. Với simple request, server có thể đã xử lý và tạo side effect trước khi browser chặn JavaScript đọc response.

**“Đưa origin vào allowlist là cấp quyền truy cập.”** Sai. Allowlist chỉ cho browser origin đó đọc response khi các điều kiện CORS phù hợp. Authentication và authorization vẫn phải được thực thi.

**“Preflight OPTIONS thành công thì POST được phép.”** Sai. Preflight chỉ cho browser biết request có đáp ứng CORS policy không. POST thật vẫn cần credential, authority, CSRF token và validation.

**“Origin không được allowlist thì curl cũng bị chặn.”** Sai. curl không thực thi CORS. Server có thể xử lý request trực tiếp nếu authentication/authorization cho phép và các lớp server khác không từ chối.

**“Tắt CSRF vì đã cấu hình CORS.”** Sai. CORS không ngăn mọi request cross-site được gửi. Với session cookie, vẫn cần CSRF protection phù hợp.

**“Cho OPTIONS permitAll là đủ.”** Sai. Cần cấu hình CORS để trả các header preflight. Quy tắc authorization không tự sinh CORS response.

## 12. Ma trận kiểm thử đề xuất

| Mã | Tình huống | Kỳ vọng phía server | Kỳ vọng phía browser |
| --- | --- | --- | --- |
| AUTH-CORS-01 | Origin hợp lệ, chưa đăng nhập | 401/redirect và ACAO hợp lệ | JavaScript đọc được response lỗi |
| AUTH-CORS-02 | Origin hợp lệ, user thiếu authority | 403 và ACAO hợp lệ | JavaScript đọc được 403 |
| AUTH-CORS-03 | Origin hợp lệ, user đủ quyền | Request được xử lý theo nghiệp vụ | JavaScript đọc được response |
| AUTH-CORS-04 | Preflight hợp lệ, không có user | OPTIONS được CORS xử lý | Browser gửi actual request nếu preflight pass |
| AUTH-CORS-05 | Preflight origin/method/header sai | CORS từ chối, không cấp ACAO phù hợp | Browser không gửi actual request cần preflight |
| AUTH-CORS-06 | Simple request cross-origin | Server phải tự kiểm tra authz/CSRF; có thể nhận request | JavaScript có thể không đọc được response |
| AUTH-CORS-07 | Session cookie và thiếu CSRF | POST bị CSRF từ chối | Browser có thể gửi cookie theo policy |
| AUTH-CORS-08 | Client curl không có Origin | Server quyết định bằng authn/authz | Không có browser CORS enforcement |
| AUTH-CORS-09 | Client trực tiếp tự đặt Origin | Origin không chứng minh danh tính | Không có browser CORS enforcement |
| AUTH-CORS-10 | User đủ quyền nhưng payload sai | Validation/business rule từ chối | Browser đọc lỗi nếu CORS cho phép |

Khi test, ghi riêng ba kết quả: request có tới server không, server có chấp nhận hành động không, và browser có cho JavaScript đọc response không. Đây là ba quan sát khác nhau.

## 13. Bài thực hành và tiêu chí hoàn thành

Một ứng dụng có frontend tại `https://app.example.vn` và API chuyển khoản tại `/api/transfers`. API chỉ cho user có authority `transfer:write` thực hiện POST. Ứng dụng dùng session cookie và CSRF protection.

Hãy thực hiện:

1. Cấu hình CORS cho origin frontend, method POST và các request header cần thiết.
2. Cấu hình authorization yêu cầu authentication và authority transfer:write.
3. Giữ CSRF protection và xác định cách frontend lấy/gửi CSRF token.
4. Viết MockMvc test cho origin hợp lệ nhưng chưa đăng nhập (401), user thiếu authority (403), user đủ quyền nhưng thiếu CSRF (403), và user đủ quyền có CSRF hợp lệ.
5. Viết preflight test không có user authentication; xác nhận OPTIONS hợp lệ được xử lý.
6. Viết test origin không được allowlist và xác nhận không có ACAO.
7. Dùng browser E2E để quan sát một simple request cross-origin và một request cần preflight; ghi nhận request nào thực sự được gửi.
8. Dùng curl hoặc HTTP client khác để chứng minh server vẫn phải kiểm tra authentication/authorization dù client không chạy CORS.
9. Kiểm tra response 401/403 có ACAO khi origin được phép để frontend có thể xử lý lỗi.

**Tiêu chí hoàn thành:** bạn giải thích được CORS kiểm soát quyền browser đọc response, còn server authentication/authorization quyết định request có được thực hiện hay không; bạn phân biệt được simple request và preflight, và có test riêng cho quyền đọc, danh tính, quyền hành động và CSRF.

**Điểm cần nhớ:** một response bị browser che khỏi JavaScript không có nghĩa request chưa tới server hoặc hành động chưa xảy ra. Hãy bảo vệ API ở phía server bằng authentication, authorization, CSRF và business rules; dùng CORS để giới hạn origin nào được browser chia sẻ response.
