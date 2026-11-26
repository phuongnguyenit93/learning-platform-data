# Kiểm thử cả origin được phép, bị chặn và client ngoài trình duyệt

## 1. Mục tiêu: chứng minh ba hành vi khác nhau

Trong chương **CORS** của mô-đun `SPRING_SECURITY_HTTP_PROTECTION`, việc nhìn thấy frontend hoạt động không đủ để kết luận chính sách CORS đúng. Một bộ kiểm thử cần chứng minh đồng thời:

1. **Origin được phép:** JavaScript từ frontend tin cậy có thể thực hiện request hợp lệ và đọc response theo chính sách CORS.
2. **Origin bị chặn:** một frontend không tin cậy không được trình duyệt cấp quyền đọc response; preflight không hợp lệ phải bị từ chối.
3. **Client ngoài trình duyệt:** `curl`, Postman hoặc một backend HTTP client **không thực thi Same-Origin Policy (SOP) như browser**; API vẫn phải bảo vệ dữ liệu bằng authentication, authorization, CSRF khi cần và các chính sách phía server.

Một lỗi kiểm thử phổ biến là gửi `curl -H "Origin: ..."`, thấy HTTP 200 rồi tuyên bố “CORS đã an toàn”. `curl` chỉ quan sát phản hồi HTTP; nó không tự quyết định có cho JavaScript đọc body hay không. Một lỗi khác là chỉ kiểm thử case hợp lệ, bỏ qua `Origin: null`, khác port, preflight với method không được phép và response 401/403.

Bài này hướng dẫn quy trình kiểm thử từ **HTTP thấp nhất → Spring Security Servlet/Reactive → browser thật → gateway/CDN**, không nhập nhằng CORS với các cơ chế khác của module như CSRF, security headers, CSP, HSTS, HTTP firewall và session protection.

### Sau bài học, bạn có thể

- Nhận diện request CORS thực tế, request preflight OPTIONS và request HTTP bình thường không có `Origin`.
- Lập ma trận origin dương/âm theo scheme, host, port, path, method, request header và credentials.
- Dùng `curl` để kiểm tra response headers của server mà không hiểu sai về SOP.
- Viết kiểm thử `MockMvc` cho Spring MVC + Spring Security Servlet và `WebTestClient` cho WebFlux + Spring Security Reactive.
- Thực nghiệm bằng DevTools trên **hai origin khác nhau** để quan sát browser từ chối đọc.
- Tách lỗi CORS khỏi 401/403 của authentication, CSRF, authorization và lỗi cookie.
- Kiểm tra chính sách khi API đi qua reverse proxy/CDN hoặc có nhiều security chains.

Những hostname `example.com` và `example.org` trong tài liệu là tên miền minh họa, cần thay bằng môi trường kiểm thử thật.

## 2. Thiết lập kịch bản kiểm thử có thể đánh giá

Giả sử có ba website và một API:

| Vai trò | URL | Mức độ tin cậy |
| --- | --- | --- |
| Frontend chính thức | `https://app.example.com` | Được phép gọi `/api/**` |
| Frontend quản trị | `https://admin.example.com` | Chỉ được phép gọi các đường dẫn admin theo chính sách riêng |
| Website không tin cậy | `https://evil.example.org` | Không nằm trong allowlist |
| Spring Security API | `https://api.example.com` | Nhận và kiểm soát request |

Chính sách kiểm thử của `/api/**`:

~~~text
Allowed origin     = https://app.example.com
Allowed methods    = GET, POST, PUT
Allowed headers    = Content-Type, Authorization, X-CSRF-TOKEN
Exposed headers    = X-Request-Id
Allow credentials  = true
Preflight max age  = 600 seconds
API path           = /api/**
~~~

Các điểm cần nắm:

- **Origin** là tổ hợp `scheme + host + port`, không chứa path. `https://app.example.com:8443` khác `https://app.example.com`.
- `Access-Control-Allow-Origin` không tự xác thực user. API chỉ cho frontend đọc response nếu browser áp dụng quy tắc tương ứng.
- `/api/**` là pattern của **đường dẫn API**, không phải pattern của origin frontend.
- Khi request Fetch ở credentials mode `include`, ACAO phải là origin cụ thể, không phải `*`; server còn cần `Access-Control-Allow-Credentials: true`.
- Không tự xem `https://admin.example.com` là được phép gọi `/api/**`. Quyền CORS phải phụ thuộc policy của endpoint đang gọi, không phụ thuộc “admin nghe có vẻ đáng tin”.

### 2.1. Ma trận ca kiểm thử tối thiểu

| Mã | Request/Origin | Dự kiến về CORS | Điều phải xác minh riêng |
| --- | --- | --- | --- |
| P1 | `Origin: https://app.example.com`, preflight `PUT` với header cho phép | **Cho phép** | OPTIONS không cần session/token của actual request |
| P2 | Origin app, actual `GET /api/me` | **Có ACAO phù hợp** | API vẫn xác thực user |
| N1 | `Origin: https://evil.example.org`, preflight PUT | **Từ chối** | Không cấp ACAO cho origin lạ |
| N2 | `Origin: http://app.example.com` | **Từ chối** | Khác scheme |
| N3 | `Origin: https://app.example.com:8443` | **Từ chối** | Khác port |
| N4 | `Origin: https://app.example.com.evil.example.org` | **Từ chối** | Hostname nhìn giống nhưng không khớp |
| N5 | `Origin: null` | **Từ chối** | Opaque origin không có trong allowlist |
| N6 | Origin app, preflight `DELETE` | **Từ chối** | Method không nằm trong policy |
| N7 | Origin app, `PUT` với `x-admin-override` | **Từ chối** | Header không được phép |
| N8 | Origin app nhưng path không có CORS policy | Không cấp quyền từ policy `/api/**` | Không nhầm path với origin |
| B1 | Browser ở site evil gửi request không cần preflight | Không được JS đọc response nếu không được cấp CORS | Request **có thể đã đến server** |
| C1 | `curl` không có `Origin` | Không phải kiểm thử SOP/CORS browser | API vẫn phải bắt authentication/authorization |
| C2 | `curl` tự gửi `Origin` giả | Server có thể xử lý/từ chối theo CORS | Header Origin không chứng minh danh tính |
| S1 | Origin app, actual PUT thiếu CSRF token | CORS có thể hợp lệ | Server phải từ chối thao tác nếu CSRF bắt buộc |
| S2 | Origin app, Alice truy cập tài nguyên Bob | CORS có thể hợp lệ | Authorization theo object/tenant phải từ chối |

Bộ test tốt cần ghi cả **điều kiện đầu vào**, **status/header thực tế**, **browser có gửi actual request không** và **đã có tác động nghiệp vụ hay chưa**.

## 3. Nhận diện preflight và actual request

Một trang ở `https://app.example.com` gọi:

~~~javascript
const response = await fetch("https://api.example.com/api/profile", {
  method: "PUT",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ displayName: "Lan" })
});
~~~

Vì `PUT` và các header/giá trị liên quan không thuộc điều kiện safelisted tương ứng, browser thường gửi preflight:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Nếu chính sách chấp nhận, Spring có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Browser sau đó mới phát actual `PUT`, nếu điều kiện CORS và browser policy cho phép. Actual request có thể mang cookie:

~~~http
PUT /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: SESSION=<session-cookie-if-allowed>
Content-Type: application/json
X-CSRF-TOKEN: <valid-csrf-token>

{"displayName":"Lan"}
~~~

Trong Spring Security, actual PUT vẫn phải qua xác thực, phân quyền và CSRF theo mô hình ứng dụng.

### 3.1. Khi nào không có preflight?

Một `GET` không có request header tùy biến thường có thể gửi thẳng:

~~~javascript
const res = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

**Không thấy OPTIONS không đồng nghĩa CORS bị bỏ qua.** Browser còn kiểm tra CORS trên actual response. Ngoài ra, kết quả preflight trước đó có thể đã được cache bởi browser theo `Access-Control-Max-Age`.

Không nên thiết kế test chỉ đếm số lượng OPTIONS mà không xem method, header, cache và actual request.

### 3.2. Response từ origin bị chặn sẽ có biểu hiện nào?

Có hai khả năng khác nhau:

1. **Preflight bị từ chối**: browser không gửi actual request dự kiến sau OPTIONS thất bại.
2. **Request không cần preflight**: actual request có thể tới API và được xử lý/từ chối ở server; browser vẫn không cho JavaScript đọc response nếu không có ACAO hợp lệ.

Bộ xử lý CORS của Spring có thể trực tiếp từ chối cả actual CORS request không hợp lệ bằng HTTP 403; vì vậy không được khẳng định actual request **luôn** đi đến handler. Điều chắc chắn về mặt trình duyệt là JavaScript không được đọc response trái chính sách.

### 3.3. Không nhầm OPTIONS thông thường với CORS preflight

Một request:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
~~~

không có `Origin` và `Access-Control-Request-Method` không phải mẫu preflight browser thông thường. Khi kiểm thử thứ tự Security filters, phải gửi **đủ** các header mô phỏng preflight, thay vì chỉ gọi `curl -X OPTIONS` rồi kết luận.

## 4. Cấu hình mẫu cho Spring Security Servlet

Ví dụ dùng `CorsConfigurationSource` với một allowlist cụ thể:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletCorsTestConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-CSRF-TOKEN"
        ));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        CorsConfigurationSource corsConfigurationSource
    ) throws Exception {
        return http
            .cors(cors -> cors.configurationSource(corsConfigurationSource))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .build();
    }
}
~~~

Ở cấu hình trên:

- `http.cors(...)` giúp preflight OPTIONS được xử lý trước những bộ lọc auth có thể từ chối vì thiếu cookie/token.
- `CorsConfigurationSource` gắn chính sách vào URL path `/api/**`.
- `authenticated()` **không bị CORS thay thế**; actual request vẫn cần danh tính phù hợp.
- CSRF vẫn được Spring Security bảo vệ theo cấu hình mặc định và cần giải pháp token phù hợp nếu dùng cookie/session cho các thao tác thay đổi trạng thái.
- Chưa có login/user store hoặc endpoint nghiệp vụ hoàn chỉnh. Đây là cấu hình tối thiểu để minh họa **chính sách CORS**.

Để kiểm thử actual GET có handler và principal, ví dụ:

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AccountTestController {

    @GetMapping("/api/me")
    Map<String, String> me(Principal principal) {
        return Map.of("user", principal.getName());
    }
}
~~~

Trong test với `spring-security-test`, có thể giả lập principal `alice`. Ứng dụng thật cần cơ chế authentication và kiểm tra quyền dữ liệu đầy đủ, không sử dụng controller demo làm cơ chế bảo mật.

## 5. Kiểm thử preflight bằng curl: trường hợp được phép

`curl` hữu ích để kiểm tra **HTTP response do backend/gateway trả về**, nhưng không có browser SOP. Lệnh sau mô phỏng preflight một cách đầy đủ:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Không cần thêm `Cookie` hoặc `Authorization`: browser preflight thông thường không dùng credentials của actual request.

Một response được phép cần xem:

| Kiểm tra | Kỳ vọng |
| --- | --- |
| HTTP status | Thông thường 2xx với CORS processor mặc định khi hợp lệ |
| `Access-Control-Allow-Origin` | Chính xác `https://app.example.com` |
| `Access-Control-Allow-Credentials` | `true` vì ví dụ bật credentials |
| `Access-Control-Allow-Methods` | Bao gồm `PUT` |
| `Access-Control-Allow-Headers` | Cho phép `Content-Type`, `X-CSRF-TOKEN` |
| `Access-Control-Max-Age` | Có thể là `600` theo chính sách |
| `Vary` | Phản ánh các request headers ảnh hưởng response CORS |
| Có bị redirect sang login? | **Không**, nếu preflight hợp lệ đã được xử lý đúng thứ tự |

**Đừng chỉ kiểm tra HTTP 200.** Một server có thể trả OPTIONS 200 mà thiếu `Access-Control-Allow-Origin`; browser vẫn không coi đó là preflight thành công.

### 5.1. Thử GET thông thường

~~~bash
curl -i "https://api.example.com/api/me" \
  -H "Origin: https://app.example.com"
~~~

Nếu không cung cấp thông tin xác thực, response có thể là 401/403 hoặc chuyển hướng login, tùy entry point. Điều đó **không nói rằng CORS sai**. Khi frontend được phép, response lỗi có thể cần ACAO thích hợp để JavaScript đọc status.

Muốn test API thật, cung cấp credential của tài khoản kiểm thử theo cơ chế được triển khai (cookie phiên hoặc bearer token hợp lệ). Không chèn token/ID phiên thực vào tài liệu, log công khai hay lệnh có thể lưu vào shell history.

### 5.2. CORS headers phải xuất hiện ở actual response

Ví dụ người dùng đã xác thực gọi GET:

~~~http
GET /api/me HTTP/1.1
Origin: https://app.example.com
Cookie: SESSION=<valid-session>
~~~

Response:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Content-Type: application/json

{"user":"alice"}
~~~

Đây là actual response. Browser có thể chia sẻ body cho JavaScript khi các điều kiện Fetch/CORS/cookie liên quan đều đáp ứng. Test preflight thành công **không thay thế** việc xác minh header trên response GET/PUT thực.

## 6. Kiểm thử origin bị từ chối

### 6.1. Origin hoàn toàn ngoài allowlist

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://evil.example.org" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type"
~~~

Bộ xử lý CORS mặc định của Spring thường trả:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: text/plain

Invalid CORS request
~~~

Cách trả status/body có thể khác nếu request bị gateway hoặc filter tùy biến xử lý trước. **Yêu cầu bất biến** là preflight không được trả những CORS response headers cấp quyền cho origin không tin cậy.

### 6.2. Origin chỉ khác scheme

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: http://app.example.com" \
  -H "Access-Control-Request-Method: PUT"
~~~

`http://app.example.com` khác `https://app.example.com`. Không nên tự thêm HTTP vào production allowlist chỉ vì local testing không dùng TLS.

### 6.3. Origin chỉ khác port

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com:8443" \
  -H "Access-Control-Request-Method: PUT"
~~~

Port là một phần của origin. Nếu frontend dev chạy tại `http://localhost:5173`, nên đưa vào chính sách **dev** riêng, không mở mọi port/protocol trong production.

### 6.4. Hostname giả gần giống

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com.evil.example.org" \
  -H "Access-Control-Request-Method: PUT"
~~~

Host này **không phải** `app.example.com`. Cấu hình kiểm tra kiểu `origin.startsWith("https://app.example.com")` có thể mắc lỗi. Hãy dùng so khớp của Spring CORS cùng allowlist origin cụ thể.

### 6.5. Origin `null`

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: null" \
  -H "Access-Control-Request-Method: PUT"
~~~

Một số ngữ cảnh sandboxed iframe, file URL hoặc opaque origin có thể phát `Origin: null`. Đừng mặc định cho phép `null` với API private chỉ để sửa một môi trường thử nghiệm. Hãy chạy frontend trên một origin HTTP(S) được kiểm soát.

### 6.6. Path không thuộc policy

~~~bash
curl -i -X OPTIONS "https://api.example.com/admin/users" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST"
~~~

Ví dụ chỉ đăng ký `/api/**`. Do đó preflight `/admin/users` không có chính sách CORS tương ứng từ source này. Một security chain khác hoặc gateway có thể quyết định response; cần kiểm tra **response cuối cùng**, không chỉ cấu hình của chain API.

## 7. Kiểm thử method và request headers bị từ chối

Origin đúng không đồng nghĩa mọi thao tác CORS được phép.

### 7.1. Method bị từ chối

Chính sách chỉ cho `GET`, `POST`, `PUT`. Thử `DELETE`:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: DELETE"
~~~

Kỳ vọng: không cấp quyền preflight cho DELETE. Nếu browser thực sự muốn gửi DELETE có preflight, nó sẽ không gửi actual DELETE sau khi preflight thất bại.

### 7.2. Request header bị từ chối

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type,x-admin-override"
~~~

`X-Admin-Override` không có trong `allowedHeaders`. Bộ xử lý CORS không được cấp quyền cho request này chỉ vì Origin là app tin cậy.

### 7.3. Phân biệt allowedHeaders và exposedHeaders

~~~java
cors.setAllowedHeaders(List.of(
    "Content-Type", "Authorization", "X-CSRF-TOKEN"
));
cors.setExposedHeaders(List.of("X-Request-Id"));
~~~

- `allowedHeaders` ảnh hưởng đến **request headers** mà browser muốn gửi trong preflight.
- `exposedHeaders` ảnh hưởng đến **response headers** mà JavaScript được đọc sau actual request.

Việc kiểm thử `Access-Control-Expose-Headers: X-Request-Id` không có nghĩa actual response tự có `X-Request-Id`. Handler/middleware phải thật sự phát header đó.

### 7.4. Kiểm thử credentials khi bị wildcard

Với request:

~~~javascript
fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

response sau sẽ **không hợp lệ để browser chia sẻ**:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Một test chỉ kiểm tra server trả HTTP 200 sẽ bỏ sót lỗi này. Hãy kiểm tra ACAO bằng origin cụ thể khi Fetch credentials mode là `include` và xác minh behavior trong browser.

## 8. Client ngoài trình duyệt: kiểm thử điều gì và không điều gì?

`curl`, Postman, một service Java `WebClient` hoặc `RestClient` không thực thi SOP của browser. Chúng vẫn gửi HTTP request đến API, nhưng không cần “xin quyền đọc cross-origin” theo cơ chế trình duyệt.

### 8.1. Gọi không có Origin

~~~bash
curl -i "https://api.example.com/api/me"
~~~

Không có `Origin`, request này thường không được coi là request CORS browser. API vẫn kiểm tra authentication/authorization. Nếu không có credentials, endpoint `/api/me` phải bị từ chối theo security policy; response chính xác có thể là 401, 403 hoặc login redirect tùy cơ chế đã cấu hình.

### 8.2. Tự đặt Origin không biến client thành frontend tin cậy

~~~bash
curl -i "https://api.example.com/api/me" \
  -H "Origin: https://app.example.com"
~~~

`curl` có thể tự gửi header này. Không được sử dụng `Origin` làm bằng chứng user là admin, đã đăng nhập hay có quyền tài khoản.

**Lưu ý kỹ thuật:** một Spring `CorsFilter`/CORS processor vẫn có thể **từ chối ở phía server** các request gửi Origin không hợp lệ, kể cả từ curl. Vì vậy không diễn giải “CORS chỉ ở browser” thành “Spring không bao giờ trả 403 khi curl gửi Origin”. Điều riêng của browser là **nó tự thực thi quyền đọc response**. HTTP client ngoài browser không làm bước đó.

### 8.3. Thử có thông tin xác thực thực

Nếu API được cấu hình bearer token, ví dụ:

~~~bash
curl -i "https://api.example.com/api/me" \
  -H "Authorization: Bearer <test-access-token>"
~~~

Hoặc với session cookie của tài khoản thử nghiệm, sử dụng cách truyền cookie phù hợp trong môi trường riêng. Token phía trên chỉ là **placeholder**, không hoạt động với ví dụ Security nếu dự án chưa cấu hình resource server.

Kỳ vọng: client được cấp quyền chỉ xem dữ liệu mà authorization cho phép. Việc không có `Origin` không được khiến server cho phép truy cập dữ liệu bí mật mà không xác thực.

### 8.4. Vì sao đây là test bảo mật quan trọng?

CORS **không phải API firewall**. Nếu backend chỉ dựa vào “Origin có nằm trong allowlist” để quyết định cho user đọc hồ sơ, nó sẽ sai với HTTP clients có thể tự đặt hoặc bỏ header đó.

Một API private cần:

- Authentication đáng tin cậy.
- Authorization theo endpoint, role/scope, ownership và tenant.
- CSRF protection nếu nhận browser-managed credentials dễ bị CSRF.
- Giới hạn tốc độ, audit và những kiểm soát nghiệp vụ phù hợp.
- CORS allowlist riêng để kiểm soát quyền **browser JavaScript đọc response**.

## 9. MockMvc: kiểm thử Servlet với cả trường hợp dương và âm

`MockMvc` có thể thực hiện request qua Spring MVC và Spring Security filter chain nếu test context được cấu hình đầy đủ. Dùng `@SpringBootTest` và `@AutoConfigureMockMvc` là một lựa chọn integration test; `@WebMvcTest` phù hợp slice tests nhưng cần nhập chính xác Security/CORS configuration.

Bộ test sau giả định có cấu hình `ServletCorsTestConfiguration` ở mục 4, controller `GET /api/me` và dependency `spring-security-test`.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletCorsOriginIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void preflightAllowsTrustedOriginWithoutCredentials() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "PUT")
                .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin",
                "https://app.example.com"))
            .andExpect(header().string(
                "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void preflightRejectsUntrustedOrigin() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://evil.example.org")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }

    @Test
    void preflightRejectsWrongScheme() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "http://app.example.com")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }

    @Test
    void preflightRejectsWrongPort() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://app.example.com:8443")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }

    @Test
    void preflightRejectsUnsupportedMethod() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "DELETE"))
            .andExpect(status().isForbidden());
    }

    @Test
    void preflightRejectsUnsupportedHeader() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "PUT")
                .header("Access-Control-Request-Headers",
                    "content-type,x-admin-override"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualGetIsReadableForTrustedOriginWhenAuthenticated()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(user("alice"))
                .header("Origin", "https://app.example.com"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin",
                "https://app.example.com"))
            .andExpect(jsonPath("$.user").value("alice"));
    }

    @Test
    void nonBrowserStyleGetStillNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().is4xxClientError());
    }

    @Test
    void noOriginWithAuthenticatedUserDoesNotNeedCorsHeaders()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(header().doesNotExist(
                "Access-Control-Allow-Origin"));
    }
}
~~~

Các assertion này minh họa hành vi của **Spring CORS processor mặc định** và controller/security context giả định; chưa chạy trên project thực tế. Với custom gateway/filter, status có thể khác nhưng phải giữ bất biến: origin không được phép **không nhận quyền CORS**.

### 9.1. Điều gì được chứng minh?

Test `preflightAllowsTrustedOriginWithoutCredentials` chứng minh OPTIONS hợp lệ không cần token/session để được CORS trả lời. Test `actualGetIsReadableForTrustedOriginWhenAuthenticated` xác minh actual response có ACAO chính xác và user được mô phỏng có quyền đọc endpoint.

Test không Origin cho thấy request HTTP bình thường **vẫn cần authentication**. Nó không phải một trình duyệt có SOP; việc test qua MockMvc không có Origin không chứng minh client ngoài browser không thể tự gửi bất kỳ HTTP request nào.

### 9.2. Bổ sung assertion cho Origin null và hostname giả

~~~java
@Test
void preflightRejectsOpaqueOrigin() throws Exception {
    mvc.perform(options("/api/profile")
            .header("Origin", "null")
            .header("Access-Control-Request-Method", "PUT"))
        .andExpect(status().isForbidden());
}

@Test
void preflightRejectsLookalikeHostname() throws Exception {
    mvc.perform(options("/api/profile")
            .header("Origin",
                "https://app.example.com.evil.example.org")
            .header("Access-Control-Request-Method", "PUT"))
        .andExpect(status().isForbidden());
}
~~~

Hai test này nằm trong cùng class hoặc class integration tương đương; bảo đảm các import static và setup `MockMvc` của phần trước.

## 10. Tách CORS tests khỏi CSRF và authorization tests

Preflight thành công không đồng nghĩa actual `PUT` được phép. Để chứng minh tầng server bảo vệ request, cần một endpoint ghi có CSRF và kiểm tra quyền nghiệp vụ.

### 10.1. Kiểm thử CSRF trên actual request

Nếu đã có `PUT /api/profile` và ứng dụng đang dùng CSRF protection của Spring Security:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.put;

// Trong một MockMvc integration test khác:

@Test
void authenticatedPutWithoutCsrfIsRejected() throws Exception {
    mvc.perform(put("/api/profile")
            .with(user("alice"))
            .header("Origin", "https://app.example.com")
            .contentType("application/json")
            .content("{\"displayName\":\"Alice\"}"))
        .andExpect(status().isForbidden());
}
~~~

Để kiểm thử luồng hợp lệ, dùng `.with(csrf())` cùng dữ liệu và principal thích hợp. Khi đó vẫn phải xác minh **authorization** và handler, không coi token CSRF hợp lệ là quyền chỉnh sửa mọi tài nguyên.

**Lưu ý:** `/api/profile` là endpoint PUT cần được triển khai trong project để kiểm thử cả tác động nghiệp vụ thành công; test chặn thiếu CSRF có thể bị Security từ chối trước khi đến handler. Mã chỉ minh họa test, không giả định endpoint PUT đã tồn tại trong đoạn controller GET ở trên.

### 10.2. BOLA/IDOR: có Origin đúng vẫn phải từ chối

Giả sử Alice sở hữu account `1001`, còn account `2002` thuộc Bob. Một integration test hoặc service test cần chứng minh:

~~~text
Given: Alice authenticated; CSRF token valid.
When : Alice PUT /api/accounts/2002
       Origin: https://app.example.com
       X-CSRF-TOKEN: <valid-token>
Then : Server rejects request (e.g. 403).
And  : Bob's account 2002 remains unchanged.
~~~

Điều kiện quyết định là **server-side ownership/tenant authorization**. Một request từ frontend được CORS tin cậy vẫn có thể chứa ID bị thay đổi bởi người dùng hoặc script độc hại. Không lấy Origin làm bằng chứng authorization.

### 10.3. Kiểm thử response lỗi có CORS đúng

Một actual GET thiếu login thường nhận 401, 403 hoặc login redirect tùy security entry point. Nếu frontend `app.example.com` được phép đọc status, response lỗi cần CORS header phù hợp khi đi qua CORS pipeline:

~~~http
HTTP/1.1 401 Unauthorized
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Content-Type: application/json

{"error":"unauthorized"}
~~~

Không mặc định mọi ứng dụng đều trả 401 với JSON: khi Spring Security cấu hình form login, response có thể là redirect. Test cần dựa trên authentication entry point của ứng dụng thật và kiểm tra **status + CORS headers** đồng thời.

## 11. WebFlux: cấu hình nguồn Reactive và WebTestClient

`org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` dùng `ServerWebExchange`, không phải `HttpServletRequest`. Trong Reactive, Security được cấu hình bởi `ServerHttpSecurity` và `SecurityWebFilterChain`.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsTestConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "Authorization", "X-CSRF-TOKEN"
        ));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);

        return http
            .cors(spec -> spec.configurationSource(source))
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Ví dụ handler tối thiểu để kiểm tra response thật trên WebFlux:

~~~java
import java.security.Principal;
import java.util.Map;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReactiveAccountTestController {

    @GetMapping("/api/me")
    Mono<Map<String, String>> me(Mono<Principal> principal) {
        return principal.map(p -> Map.of("user", p.getName()));
    }
}
~~~

### 11.1. WebTestClient: positive và negative preflight

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.http.HttpHeaders.*;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCorsOriginIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void preflightAllowsTrustedOriginWithoutSession() {
        client.options()
            .uri("/api/profile")
            .header(ORIGIN, "https://app.example.com")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "PUT")
            .header(ACCESS_CONTROL_REQUEST_HEADERS,
                "content-type,x-csrf-token")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                ACCESS_CONTROL_ALLOW_ORIGIN, "https://app.example.com")
            .expectHeader().valueEquals(
                ACCESS_CONTROL_ALLOW_CREDENTIALS, "true");
    }

    @Test
    void preflightRejectsForeignOrigin() {
        client.options()
            .uri("/api/profile")
            .header(ORIGIN, "https://evil.example.org")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "PUT")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void preflightRejectsDelete() {
        client.options()
            .uri("/api/profile")
            .header(ORIGIN, "https://app.example.com")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "DELETE")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void actualGetFromTrustedOriginContainsCorsHeaders() {
        client.mutateWith(mockUser("alice"))
            .get()
            .uri("/api/me")
            .header(ORIGIN, "https://app.example.com")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                ACCESS_CONTROL_ALLOW_ORIGIN, "https://app.example.com")
            .expectBody()
            .jsonPath("$.user").isEqualTo("alice");
    }

    @Test
    void noOriginDoesNotBypassAuthentication() {
        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().is4xxClientError();
    }
}
~~~

Bài test trên minh họa cấu hình Security Reactive với nguồn CORS và handler tương ứng; cần dependency `spring-security-test`, context đầy đủ, và phiên bản Spring Boot tương thích. Những assertion trả 403 dựa trên bộ xử lý CORS mặc định; chưa chạy trên dự án thật.

### 11.2. Kiểm thử CSRF Reactive riêng

Nếu dùng session cookie và CSRF protection, thêm test actual `PUT` với principal giả lập nhưng không có CSRF token, kỳ vọng bị chặn:

~~~java
@Test
void authenticatedActualPutWithoutCsrfIsRejected() {
    client.mutateWith(mockUser("alice"))
        .put()
        .uri("/api/profile")
        .header(ORIGIN, "https://app.example.com")
        .bodyValue("{\"displayName\":\"Alice\"}")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Khi cần test request có CSRF hợp lệ, Spring Security Test có các bộ hỗ trợ mock CSRF tương ứng cho Reactive. Dù CSRF hợp lệ, backend vẫn phải kiểm tra user và ownership trước khi cập nhật.

## 12. Thử bằng trình duyệt thật từ hai origin khác nhau

`MockMvc`, `WebTestClient` và `curl` không thực thi SOP/CORS như browser. Vì vậy **test thật từ browser ở hai origin khác nhau là bước không được bỏ qua** nếu mục tiêu là xác nhận JavaScript có đọc được response hay không.

### 12.1. Chuẩn bị hai trang thử nghiệm

Sử dụng hai website HTTPS khác origin do nhóm kiểm thử kiểm soát:

- `https://app.example.com/test-cors.html` — origin được phép.
- `https://evil.example.org/test-cors.html` — origin không được phép, phục vụ mục đích test.

Cả hai chứa cùng đoạn JavaScript, chạy từ chính origin của trang:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Kiểm tra CORS</title>
</head>
<body>
  <button id="run">Kiểm tra GET /api/me</button>
  <pre id="result"></pre>

  <script>
    document.querySelector("#run").addEventListener("click", async () => {
      const output = document.querySelector("#result");
      output.textContent = "Đang gửi request...";

      try {
        const response = await fetch(
          "https://api.example.com/api/me",
          { credentials: "include" }
        );

        const text = await response.text();
        output.textContent =
          "HTTP " + response.status + "\n" + text;
      } catch (error) {
        output.textContent = "Fetch bị chặn/lỗi mạng: " + error;
      }
    });
  </script>
</body>
</html>
~~~

Đây là một file HTML demo để nhóm triển khai trên **origin thật**, không phải file cần tạo trong workspace của bài này. Nếu server yêu cầu đăng nhập, user phải đăng nhập trong môi trường test theo cơ chế ứng dụng. Có thể cần chính sách cookie phù hợp để browser gửi session tới API; một lỗi cookie không nên bị nhầm thành lỗi CORS.

### 12.2. Kỳ vọng ở trang được phép

Tại `https://app.example.com`:

- Nếu session hợp lệ, response và body `/api/me` có thể được JavaScript đọc.
- Nếu session thiếu, browser vẫn có thể đọc status 401/403 **khi actual response có CORS headers đúng**; kết quả cụ thể phụ thuộc cách Spring Security cấu hình entry point.
- Trong DevTools → Network, tìm request GET và kiểm tra `Origin`, Cookie (nếu browser cho phép), ACAO và ACAC.
- Một GET đơn giản không nhất thiết gửi OPTIONS, nên không xem vắng OPTIONS là lỗi.

### 12.3. Kỳ vọng ở trang bị chặn

Tại `https://evil.example.org`:

- JavaScript không được đọc `/api/me` nếu API không cấp CORS quyền cho origin này.
- `fetch` thường reject và Console báo lỗi CORS (hoặc browser báo lỗi mạng liên quan).
- Network có thể vẫn hiển thị actual GET/response hoặc CORS rejection từ server. Không đồng nhất thông điệp lỗi của tất cả trình duyệt.
- Nếu đã có preflight cho một request khác, preflight bị từ chối có thể khiến actual request **không được gửi**.

**Cẩn thận:** không dùng dữ liệu sản xuất thật, session của người dùng thật hoặc domain không thuộc quyền kiểm soát để thử các kịch bản này. Hãy sử dụng tài khoản và dữ liệu test.

### 12.4. CSP có thể chặn trước khi CORS được đánh giá

Nếu frontend có Content Security Policy:

~~~http
Content-Security-Policy: connect-src 'self' https://api.example.com
~~~

thì JavaScript được phép kết nối tới API theo CSP. Nhưng nếu `connect-src` không cho phép API, browser có thể **không phát request** và báo vi phạm CSP. Đây không phải bằng chứng về CORS policy.

Khi debug, cần phân biệt các lỗi Console như **CSP connect-src violation**, **CORS preflight failure**, **ACAO mismatch**, lỗi DNS/TLS và các lỗi mạng khác. HSTS và TLS còn có thể ảnh hưởng việc trình duyệt có kết nối được tới origin hay không.

## 13. Kiểm thử với cookie và credentials: đúng CORS vẫn có thể thiếu cookie

`credentials: "include"` khiến browser **cân nhắc** gửi cookie trên cross-origin request. Tuy nhiên:

- Cookie `Domain`/`Path` không khớp thì không được gửi.
- Cookie `Secure` chỉ được gửi trong ngữ cảnh phù hợp theo quy tắc browser.
- `SameSite=Lax`/`Strict` có thể hạn chế cross-site requests; cross-origin không luôn là cross-site.
- Browser có thể hạn chế third-party cookies ngay cả khi server trả ACAO/ACAC hợp lệ.
- `HttpOnly` ngăn JavaScript đọc cookie bằng `document.cookie` nhưng không ngăn browser gửi cookie khi điều kiện phù hợp.
- `Set-Cookie` không phải response header mà JavaScript được đọc chỉ bằng cách thêm nó vào `Access-Control-Expose-Headers`.

Ví dụ `https://app.example.com` và `https://api.example.com` khác origin nhưng thường same-site (HTTPS cùng registrable domain). Cookie `SameSite=Lax` có thể được gửi trên request same-site phù hợp nếu Fetch dùng `credentials: "include"`.

Vì vậy, để test rõ ràng hãy phân biệt:

1. **CORS đúng nhưng cookie vắng mặt:** preflight/actual response có ACAO/ACAC phù hợp, song request thiếu Cookie vì Fetch/cookie policy.
2. **Cookie được gửi nhưng CORS sai:** server có thể đã xử lý phiên; browser vẫn chặn JavaScript đọc response do ACAO không khớp.
3. **CORS và cookie đều đúng nhưng thiếu quyền:** actual request bị authentication/authorization/CSRF từ chối.
4. **Frontend không tin cậy nhưng cùng site:** SameSite không đồng nghĩa với allowlist CORS; cần đánh giá subdomain user-controlled và rủi ro XSS.

Đặc biệt không mở `allowedOriginPatterns("*")` với `allowCredentials(true)` cho API riêng tư chỉ để “sửa” lỗi cookie.

## 14. Reverse proxy, CDN, cache và nhiều security chains

Test trong JVM có thể pass nhưng triển khai thật vẫn lỗi vì gateway/CDN hoặc chain matcher.

### 14.1. Vary và response được cache theo Origin

Nếu API chọn ACAO theo Origin:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
~~~

CDN phải tôn trọng hoặc tái tạo phân biệt variant phù hợp. Nếu nó cache response của app rồi phát lại cho origin khác, browser có thể thấy ACAO mismatch. `Vary: Origin` có ích cho HTTP cache, nhưng **không bảo vệ dữ liệu cá nhân hóa khỏi bị shared cache trộn giữa users**: response private thường cần `Cache-Control: no-store` hoặc chính sách bypass shared caching thích hợp.

Kết quả preflight của browser lại có bộ nhớ đệm riêng do `Access-Control-Max-Age` điều khiển. Nó **không phải** TTL HTTP cache của CDN. Hãy thử browser profile mới hoặc điều kiện request mới khi cần kiểm tra chính sách preflight đã thay đổi.

### 14.2. Test trực tiếp backend và qua gateway

Thử cùng request:

~~~bash
# Đường đi công khai qua gateway/CDN:
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Sau đó thực hiện trên **địa chỉ test backend trực tiếp được tổ chức cho phép**, với các header route/host phù hợp. Đừng tự suy ra một URL nội bộ hay bỏ qua quy định bảo mật mạng. So sánh status, ACAO, ACAC, `Vary`, path rewrite và header bị gateway chèn thêm.

Không được cấu hình cả gateway và Spring tùy ý phát nhiều `Access-Control-Allow-Origin` trong response cuối. Header trùng hoặc giá trị ghép thường khiến browser từ chối.

### 14.3. Nhiều security chains có thể làm OPTIONS rơi vào chain khác

Nếu dùng `SecurityFilterChain` theo path `/api/**`, `/admin/**`, hãy kiểm thử preflight cho từng nhóm. Một chain chỉ match HTTP POST/PUT có thể **không nhận OPTIONS** dù `Access-Control-Request-Method` ghi POST/PUT; do đó preflight có thể rơi vào fallback chain thiếu CORS.

Trong WebFlux, điều tương tự áp dụng cho các `SecurityWebFilterChain`. Xác minh chain được chọn theo **request OPTIONS thật**, không chỉ actual method.

### 14.4. Firewall, authentication filter và lỗi HTTP

Một gateway hoặc custom filter có thể trả `401`, `403`, `404` hoặc `405` trước Spring CORS. Nếu request đã bị chặn ở bên ngoài security chain, chỉ sửa `http.cors(...)` hay `ServerHttpSecurity.cors(...)` không đủ.

Đồng thời, Spring Security HTTP firewall có thể từ chối malformed request vì lý do chính đáng. Không nới lỏng HTTP firewall khi một request test sai cú pháp; hãy sửa request hoặc xác định rõ policy.

## 15. Bảng chẩn đoán kết quả kiểm thử

| Quan sát | Nguyên nhân có thể | Kiểm tra tiếp theo |
| --- | --- | --- |
| `curl` OPTIONS 200, browser vẫn chặn | Thiếu hoặc sai ACAO/ACAM/ACAH; wildcard với credentials | Đọc CORS response headers, không chỉ status |
| Origin app được phép trong MockMvc nhưng browser bị chặn | Gateway/CDN sửa headers, frontend Origin khác dự kiến, CSP/TLS | So Network, URL thực, response cuối |
| Origin evil nhận preflight 200 có ACAO của evil | Allowlist/pattern quá rộng hoặc phản chiếu Origin | Thu hẹp policy; kiểm tra credentials |
| Origin evil nhận HTTP 403 ở GET | Spring CORS processor có thể từ chối actual request | Xem server log/filter và ACAO, đừng suy là browser đã chặn mọi request |
| Origin evil không thể đọc GET nhưng server ghi side effect | Actual request có thể đã đến server | Sửa unsafe GET, áp dụng CSRF/authorization |
| OPTIONS 401 dù không gửi cookie | Authentication/gateway đứng trước CORS | Kiểm tra thứ tự filter và routing |
| OPTIONS 403 `Invalid CORS request` | Origin/method/header/path không đạt | Đối chiếu request với `CorsConfiguration` |
| GET app trả 401/403 dù ACAO đúng | Thiếu auth, quyền hoặc lỗi CSRF với thao tác tương ứng | Kiểm tra actual request security |
| PUT app preflight thành công, actual PUT 403 | CSRF token hoặc quyền thực | Test CSRF và authorization độc lập |
| `curl` không Origin vẫn nhận dữ liệu bí mật | Backend thiếu authentication/authorization | Sửa server security; không dùng Origin để xác thực |
| Host giống app nhưng thêm hậu tố được cho phép | So khớp origin bằng chuỗi tiền tố/regex sai | Dùng allowlist chính xác và negative test |
| Test khác port/scheme vẫn được phép bất ngờ | Cấu hình wildcard hoặc origin pattern rộng | Kiểm tra allowedOrigins/allowedOriginPatterns |
| Cookie vắng mặt dù ACAO/ACAC đúng | SameSite, Secure, Domain/Path, credentials mode, third-party policies | Xem DevTools Cookies và request thực |
| Không thấy OPTIONS ở lần thứ hai | Browser preflight cache | Kiểm tra `Access-Control-Max-Age` và request attributes |
| Browser báo `connect-src` | CSP chặn kết nối trước CORS | Rà soát CSP của frontend |
| Một backend instance hoạt động, instance khác lỗi | Rollout policy không đồng nhất | So cấu hình và response theo instance |
| Response 401 từ gateway không có ACAO | Gateway trả lỗi trước Spring | Thống nhất xử lý CORS trên cả error responses |
| Header ACAO xuất hiện hai lần | Gateway và backend cùng ghi | Chọn một chính sách và nơi phát phù hợp |
| `curl` với `Origin` giả bị 403 | Server CORS processor từ chối Origin | Thử không Origin và kiểm tra auth riêng; không suy curl áp dụng SOP |

## 16. Checklist CI và release

Nên biến các kết quả dương/âm quan trọng thành **regression tests** trong CI, thay vì chỉ kiểm tra thủ công khi frontend bị lỗi.

- [ ] Preflight từ origin được phép, đúng method/headers, **không mang cookie/token**, thành công với ACAO thích hợp.
- [ ] Origin ngoài allowlist bị từ chối: tên miền lạ, khác scheme, khác port, hostname giả gần giống và `Origin: null`.
- [ ] Origin đúng nhưng method/header không cho phép bị từ chối.
- [ ] Path ngoài `/api/**` không vô tình nhận policy của API.
- [ ] Actual GET được phép có ACAO đúng và không dùng wildcard cùng credentials mode `include`.
- [ ] Response 401/403 ở origin được phép có CORS headers phù hợp khi frontend cần đọc lỗi.
- [ ] Request không có `Origin` vẫn cần authentication/authorization cho endpoint private.
- [ ] Client ngoài browser có thể tự đặt Origin, nhưng không thể bypass authentication và object-level authorization.
- [ ] Actual POST/PUT/PATCH/DELETE dùng session vẫn phải qua CSRF protection khi áp dụng.
- [ ] Đã kiểm thử browser thật trên ít nhất một origin được phép và một origin bị chặn, dùng dữ liệu thử nghiệm.
- [ ] Cookie/SameSite/Secure/third-party restrictions được kiểm tra riêng với CORS.
- [ ] Các test Servlet/Reactive chạy với đúng Security filter chain, không chỉ trực tiếp gọi controller.
- [ ] Security chain của preflight OPTIONS được xác nhận, kể cả khi ứng dụng có nhiều chains.
- [ ] CDN/gateway forward OPTIONS và trả các CORS headers nhất quán, không tạo ACAO trùng.
- [ ] `Vary: Origin` và chính sách cache HTTP không làm trộn response giữa origins/users.
- [ ] CSP `connect-src`, TLS/HSTS và HTTP firewall không bị nhầm với lỗi CORS.
- [ ] Không lưu credentials thật trong test artifacts, CI logs hoặc lệnh shell được chia sẻ.

## 17. Câu hỏi tình huống có đáp án

**Tình huống 1 — Chỉ test origin được phép.** Nhóm phát triển có một test `OPTIONS` từ `https://app.example.com` trả 200. Có thể kết luận CORS an toàn chưa?

**Đáp án:** Chưa. Cần test origin không tin cậy, sai scheme/port, host giả, `Origin: null`, method/header bị từ chối, actual response và credentials. HTTP 200 không đủ nếu CORS response headers thiếu hoặc sai.

**Tình huống 2 — Curl thấy JSON.** `curl` không gửi Origin nhưng nhận JSON từ `GET /api/me`. Đây có phải lỗ hổng CORS?

**Đáp án:** Không thể kết luận chỉ từ đó. Curl không áp dụng SOP; điều cần xem là API có yêu cầu authentication/authorization đúng không. Nếu JSON riêng tư được trả cho client không có credentials, đó là lỗi bảo mật server nghiêm trọng, không được chữa bằng CORS.

**Tình huống 3 — Origin bị từ chối nhưng side effect xảy ra.** Một request cross-origin không cần preflight làm server thay đổi dữ liệu, nhưng JavaScript không đọc được response. CORS có “chặn” thao tác không?

**Đáp án:** Không. Browser có thể chặn việc đọc response sau khi actual request đã đến server. API cần CSRF protection, authorization và không được thay đổi trạng thái qua GET.

**Tình huống 4 — Preflight thiếu cookie.** OPTIONS hợp lệ trả 401 do auth filter. Có nên gắn session cookie vào preflight bằng JavaScript?

**Đáp án:** Không. Browser tự tạo preflight và không gửi credentials của actual request theo cách thông thường. Cần xử lý CORS đủ sớm trước authentication; actual request mới chịu auth/CSRF.

**Tình huống 5 — CSRF không phải CORS.** Preflight cho PUT hợp lệ trả 200; actual PUT của user đã login trả 403. Cần mở rộng `allowedMethods` không?

**Đáp án:** Không nếu PUT đã nằm trong allowlist. Điều tra CSRF token, authentication và authorization của actual PUT.

**Tình huống 6 — App đổi port.** `https://app.example.com:8443` bị từ chối nhưng `https://app.example.com` hoạt động. Đây có phải lỗi ngẫu nhiên không?

**Đáp án:** Không. Port là một phần của origin. Chỉ thêm port mới nếu frontend ở port đó thực sự được tin cậy; tách môi trường dev/prod.

**Tình huống 7 — Postman với Origin giả.** Client ngoài browser có thể gửi `Origin: https://admin.example.com`. Server có thể coi request đến từ admin không?

**Đáp án:** Không. Origin không phải identity. Server phải xác thực token/session và kiểm tra role/scope/ownership độc lập.

**Tình huống 8 — Wildcard credentials.** Response trả `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true`. `fetch` dùng `credentials: "include"` có đọc được body không?

**Đáp án:** Không. Browser yêu cầu ACAO là origin cụ thể phù hợp. Không sửa bằng phản chiếu mọi Origin; phải dùng allowlist đáng tin cậy.

**Tình huống 9 — WebTestClient pass, browser fail.** Test Reactive với Origin app trả ACAO chính xác, nhưng browser báo CSP `connect-src`. Có cần sửa `CorsWebFilter` không?

**Đáp án:** Trước hết phải kiểm tra CSP frontend. CSP có thể chặn kết nối trước khi CORS được đánh giá; đây là cơ chế độc lập.

**Tình huống 10 — Origin đúng, tài nguyên sai chủ.** Alice gọi `PUT /api/accounts/2002` của Bob với Origin được phép và CSRF token hợp lệ. Server cập nhật dữ liệu. Lỗi ở đâu?

**Đáp án:** Authorization cấp đối tượng/BOLA. CORS và CSRF đều có thể làm đúng nhiệm vụ riêng nhưng server thiếu kiểm tra ownership theo principal và target account.

**Tình huống 11 — CDN phát ACAO của origin A cho origin B.** Browser B nhận lỗi trong khi backend direct hoạt động. Bước tiếp theo?

**Đáp án:** So HTTP response trước và sau CDN, kiểm tra Origin forwarding, `Vary: Origin`, cache key, chính sách edge và header ACAO trùng. Không mở wildcard cho dễ.

**Tình huống 12 — Không thấy OPTIONS.** Browser gửi GET không header tùy biến và không có OPTIONS trong Network. Có nghĩa CORS không được bảo vệ?

**Đáp án:** Không. GET safelisted có thể không cần preflight; browser vẫn kiểm tra CORS trên actual response. Preflight trước đó cũng có thể đã được cache.

---

**Ghi nhớ:** Để kiểm thử CORS đúng, phải có **case được phép**, **case bị chặn** và **case HTTP client ngoài browser**, kết hợp quan sát **preflight** với **actual response**. `curl`, `MockMvc` và `WebTestClient` kiểm tra HTTP/CORS processor; **browser thật** mới xác nhận hành vi SOP/CORS và cookie. Dù origin được phép hay bị chặn, API Spring Security vẫn phải xác thực, phân quyền theo tài nguyên, chống CSRF khi cần và giữ các lớp phòng vệ HTTP trên cả Servlet lẫn Reactive.
