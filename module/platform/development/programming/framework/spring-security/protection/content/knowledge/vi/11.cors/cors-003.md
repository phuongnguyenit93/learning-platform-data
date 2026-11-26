# Origin được phép và cách so khớp chính xác

## Mục tiêu học tập

Trong chủ đề **CORS** của mô-đun `SPRING_SECURITY_HTTP_PROTECTION`, một trong những quyết định quan trọng nhất của API là **JavaScript ở origin nào được đọc phản hồi khác origin**. Spring Security giúp tích hợp quyết định này vào các lớp phòng vệ HTTP và trình duyệt, bên cạnh xác thực, phân quyền, chống CSRF, security headers, CSP, HSTS, HTTP firewall và bảo vệ session. Bài này tập trung vào việc nhận diện, so khớp và cấu hình tập origin được phép, cho cả Servlet và Reactive.

Sau bài học, người học có thể:

1. Xác định origin của một URL theo **scheme, host và port**.
2. Dự đoán chính xác hai địa chỉ nào cùng origin, hai địa chỉ nào khác origin.
3. Giải thích cách `Origin` trong request và `Access-Control-Allow-Origin` trong response hoạt động.
4. Phân biệt allowlist cụ thể, wildcard `*` và pattern subdomain của Spring.
5. Cấu hình, kiểm thử và chẩn đoán lỗi so khớp origin với Spring Security Servlet và WebFlux.

Ví dụ xuyên suốt: frontend chính thức tại `https://app.example`, frontend quản trị tại `https://admin.example`, API tại `https://api.example` và một trang không tin cậy tại `https://evil.example`. Các địa chỉ `.example` chỉ dùng để minh họa.

## 1. Origin được định nghĩa bằng ba thành phần

**Origin = scheme + host + port.**

Đối với URL `https://app.example:8443/dashboard?tab=orders#today`:

| Thành phần | Giá trị | Có tham gia xác định origin? |
| --- | --- | --- |
| Scheme | `https` | Có |
| Host | `app.example` | Có |
| Port | `8443` | Có |
| Path | `/dashboard` | Không |
| Query | `tab=orders` | Không |
| Fragment | `today` | Không |

Origin không bao gồm đường dẫn. JavaScript chạy tại `https://app.example/dashboard` và `https://app.example/settings` có cùng origin nếu chúng dùng cùng scheme, host và port.

Trong HTTP, port mặc định là **80**; trong HTTPS là **443**. Việc chỉ rõ hoặc bỏ port mặc định không tạo origin khác. Trình duyệt thường tuần tự hóa origin theo dạng chuẩn và bỏ port mặc định khi đặt header `Origin`.

| Địa chỉ A | Địa chỉ B | Cùng origin? | Giải thích |
| --- | --- | --- | --- |
| `https://app.example` | `https://app.example:443` | Có | Cùng HTTPS, port mặc định |
| `http://app.example` | `http://app.example:80` | Có | Cùng HTTP, port mặc định |
| `https://app.example` | `https://app.example:8443` | Không | Khác port |
| `http://app.example` | `https://app.example` | Không | Khác scheme |
| `https://app.example` | `https://api.example` | Không | Khác host |
| `https://app.example/a` | `https://app.example/b` | Có | Chỉ khác path |
| `http://localhost:3000` | `http://localhost:5173` | Không | Khác port |
| `http://localhost:5173` | `http://127.0.0.1:5173` | Không | Khác host |

Một API được triển khai trên cùng máy chủ vật lý không làm các origin tự động trùng nhau. `localhost` và `127.0.0.1` cũng khác host, dù thông thường cùng trỏ về máy phát triển.

**Origin khác site:** `https://app.example` và `https://api.example` khác origin vì khác host, nhưng thường cùng site theo cách đánh giá của cookie. CORS xét *origin*, còn `SameSite` của cookie xét *site*. Đừng suy luận hai subdomain cùng tổ chức thì trình duyệt cho đọc response của nhau.

## 2. Origin trong yêu cầu CORS là origin của trang gọi

JavaScript ở `https://app.example` gọi API ở `https://api.example`:

~~~javascript
const response = await fetch("https://api.example/api/products");
const products = await response.json();
~~~

Trình duyệt có thể gửi:

~~~http
GET /api/products HTTP/1.1
Host: api.example
Origin: https://app.example
Accept: */*
~~~

Cần đọc đúng ý nghĩa:

- `Host: api.example` là host của **API đích**.
- `Origin: https://app.example` là origin của **ngữ cảnh trang khởi tạo request**.
- Chính origin của trang gọi được API đối chiếu với danh sách cho phép.

Nếu server cho phép nguồn này, response có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example
Vary: Origin

[{"id":10,"name":"Mouse"}]
~~~

Trình duyệt so khớp quyền CORS trong response. Nếu các điều kiện khác đều hợp lệ, frontend nhận được response để xử lý.

Nếu response lại là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://admin.example

[{"id":10,"name":"Mouse"}]
~~~

`https://admin.example` **không** trùng origin của trang gọi `https://app.example`. Dù API có thể đã trả HTTP 200, JavaScript tại `app.example` không được đọc body vì kiểm tra CORS thất bại.

**Điểm phân biệt:** CORS của trình duyệt quyết định JavaScript có được **đọc response**; nó không thay thế xác thực, phân quyền hay chặn mọi request đến server.

## 3. So khớp origin chính xác, tránh so chuỗi gần giống

Một allowlist điển hình có thể chứa:

~~~text
https://app.example
https://admin.example
~~~

Chỉ các origin được liệt kê mới được cấp quyền CORS theo cấu hình này. Các địa chỉ sau **không** tương đương `https://app.example`:

- `http://app.example` — khác scheme.
- `https://app.example:8443` — khác port.
- `https://login.app.example` — khác host.
- `https://app.example.attacker.test` — host khác hoàn toàn, dù bắt đầu bằng chuỗi `app.example`.
- `https://evil-app.example` — host khác, dù chứa một phần tên quen thuộc.
- `https://api.example` — đây là origin của API, không phải origin của frontend.
- `https://other.example` — không thuộc allowlist.

Đây là lỗi triển khai nguy hiểm:

~~~java
// SAI: hostname do bên thứ ba quản lý có thể chứa chuỗi "app.example".
boolean allow = origin.contains("app.example");

// SAI: https://app.example.attacker.test cũng bắt đầu cùng tiền tố.
boolean allowPrefix = origin.startsWith("https://app.example");
~~~

Hai phép kiểm tra trên bỏ qua ranh giới nhãn hostname hoặc các trường hợp URL bất thường. Đừng xây dựng CORS bằng phép `contains`, `startsWith` hoặc so khớp một phần domain tự viết. Sử dụng thành phần CORS của Spring Framework và giá trị origin đã được chuẩn hóa.

**Cấu hình origin không chứa path:** chuỗi `https://app.example/login` hoặc `https://app.example/` không phải biểu diễn origin chuẩn dành cho allowlist. Đưa đường dẫn đăng nhập hoặc route SPA vào cấu hình CORS là nhầm lẫn giữa URL và origin.

### Đừng ghép nhiều origin vào một header

Response sau không cấp phép hợp lệ cho hai frontend:

~~~http
Access-Control-Allow-Origin: https://app.example, https://admin.example
~~~

`Access-Control-Allow-Origin` phải là **một origin cụ thể** hoặc `*` khi hợp lệ; không phải danh sách phân tách bằng dấu phẩy. Nếu API tin cậy cả hai frontend, server so khớp `Origin` trên từng request rồi trả một giá trị tương ứng:

~~~http
# Request từ app.example
Access-Control-Allow-Origin: https://app.example
Vary: Origin
~~~

~~~http
# Request từ admin.example
Access-Control-Allow-Origin: https://admin.example
Vary: Origin
~~~

`Vary: Origin` giúp cache trung gian hiểu response hoặc header CORS có thể phụ thuộc header `Origin` của request. Nếu cache dùng lại response giữa các origin mà thiếu phân biệt, frontend có thể gặp lỗi khó tái hiện.

## 4. Allowed origin, wildcard và pattern của Spring

Có ba cơ chế khác nhau cần phân biệt:

| Cách khai báo | Ý nghĩa | Phù hợp khi |
| --- | --- | --- |
| `allowedOrigins` chứa origin cụ thể | Chỉ cho phép các origin được liệt kê | Số frontend biết trước, ổn định |
| Header `Access-Control-Allow-Origin: *` | Cho phép mọi origin đọc response trong điều kiện wildcard hợp lệ | API công khai, không dùng credentials mode cross-origin |
| `allowedOriginPatterns` trong Spring | So origin với mẫu do server định nghĩa rồi trả origin cụ thể đã khớp | Có nhiều frontend có quy tắc hostname đáng tin cậy |

### 4.1. Allowed origins cụ thể

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of(
    "https://app.example",
    "https://admin.example"
));
~~~

Với cấu hình này:

- Request `Origin: https://app.example` có thể được cấp quyền.
- Request `Origin: https://admin.example` có thể được cấp quyền.
- Request `Origin: https://evil.example` bị từ chối theo chính sách CORS.

Đây là lựa chọn dễ kiểm tra nhất khi chỉ có vài origin tin cậy.

### 4.2. Dấu `*` không phải wildcard subdomain trong response

Dòng sau **không** phải cách cho phép toàn bộ subdomain của `example.com`:

~~~http
Access-Control-Allow-Origin: https://*.example.com
~~~

Trong response header `Access-Control-Allow-Origin`, dấu `*` hợp lệ ở dạng giá trị wildcard toàn phần, không phải một phần hostname. Browser không hiểu kiểu `https://*.example.com` trong header này.

Với CORS response chứa `Access-Control-Allow-Origin: *`, trình duyệt có thể cấp quyền đọc cho origin bất kỳ khi yêu cầu đáp ứng các điều kiện tương ứng, nhưng **không** chấp nhận wildcard này cho request có `credentials: "include"`.

### 4.3. Allowed origin patterns trong Spring

Nếu có nhiều subdomain thực sự đáng tin cậy, Spring Framework hỗ trợ:

~~~java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOriginPatterns(List.of(
    "https://*.trusted.example"
));
~~~

Khi request từ `https://team.trusted.example` khớp pattern, Spring phản hồi bằng origin cụ thể:

~~~http
Access-Control-Allow-Origin: https://team.trusted.example
Vary: Origin
~~~

Spring cũng hỗ trợ mẫu cho port, ví dụ `https://*.trusted.example:[8080,8081]`. Cú pháp pattern là **quy tắc so khớp tại server**, không phải cú pháp để chép nguyên vào `Access-Control-Allow-Origin`.

**Cảnh báo về phạm vi tin cậy:** pattern bao phủ nhiều origin hơn allowlist liệt kê. Nếu người dùng được tự tạo subdomain, hoặc có record DNS không còn quản lý và có nguy cơ bị chiếm, một subdomain không tin cậy có thể khớp pattern. Với API nhạy cảm, nên ưu tiên từng origin cụ thể và chỉ mở pattern nếu có quy trình kiểm soát subdomain chắc chắn.

### 4.4. Phối hợp với credentials

Khi frontend dùng session cookie hoặc muốn gửi credentials cross-origin:

~~~javascript
const response = await fetch("https://api.example/api/me", {
  credentials: "include"
});
~~~

Để browser cho JavaScript đọc response, API cần trả quyền CORS tương ứng:

~~~http
Access-Control-Allow-Origin: https://app.example
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

`Access-Control-Allow-Origin: *` không hoạt động với `credentials: "include"`, kể cả khi đã có `Access-Control-Allow-Credentials: true`. Trong Spring, kết hợp `setAllowedOrigins(List.of("*"))` và `setAllowCredentials(true)` là cấu hình không hợp lệ, framework có thể từ chối.

`allowedOriginPatterns` có thể dùng với `allowCredentials(true)` vì Spring trả origin cụ thể đã khớp. Nhưng điều đó **không làm pattern quá rộng trở nên an toàn**.

Cookie có thực sự được gửi còn phụ thuộc `credentials`, `SameSite`, `Secure`, domain/path và chính sách cookie của trình duyệt. Bật credentials không tự động gây preflight.

## 5. Những trường hợp đặc biệt của header Origin

### 5.1. `Origin: null`

Một số ngữ cảnh có *opaque origin*, chẳng hạn một số tài liệu sandbox hoặc nội dung `file:`, được biểu diễn bằng giá trị văn bản `null`:

~~~http
Origin: null
~~~

Đây **không** phải một frontend có hostname đã được xác minh. Không mặc định đưa `null` vào allowlist chỉ để thử trang HTML local. Hãy chạy trang dev qua HTTP(S) ở origin rõ ràng, chẳng hạn `http://localhost:5173`.

Phân biệt header hoàn toàn **không xuất hiện** với header có giá trị chữ `"null"`. Hai trường hợp này không đồng nghĩa.

### 5.2. Không có header Origin

Một số request không mang `Origin`: request ngoài browser, request same-origin hoặc các tình huống không thuộc kiểm tra CORS thông thường. Server không được coi “không có Origin” là bằng chứng người gọi đáng tin cậy.

API luôn phải áp dụng xác thực, phân quyền và các lớp bảo vệ HTTP thích hợp.

### 5.3. Origin có thể bị giả mạo từ curl

~~~bash
curl -i "https://api.example/api/profile" \
  -H "Origin: https://app.example"
~~~

Một client ngoài trình duyệt có thể đặt `Origin` tùy ý. Spring có thể trả CORS header cho origin đó, nhưng điều này **không xác thực danh tính** hoặc cấp quyền đọc dữ liệu được bảo vệ. CORS là cơ chế giữa trình duyệt và server; curl không thực thi SOP/CORS như browser.

### 5.4. Vì sao không dùng Origin làm kiểm tra CSRF duy nhất?

Header `Origin` có thể hữu ích trong chiến lược kiểm tra nguồn của request thay đổi trạng thái, nhưng **allowlist CORS** không tự chống CSRF. Một số loại request cross-site có thể tới API mà không cần preflight; việc JavaScript không đọc được response không có nghĩa tác động thay đổi dữ liệu đã bị chặn.

Spring Security cần tiếp tục áp dụng CSRF protection phù hợp với cách ứng dụng dùng session cookie, token và thao tác thay đổi trạng thái.

## 6. Áp dụng trong Spring Security Servlet

Với ứng dụng Spring MVC và Spring Security, tạo `CorsConfigurationSource` và tích hợp qua `HttpSecurity.cors`:

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
class ServletSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
            "https://app.example",
            "https://admin.example"
        ));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setMaxAge(600L);

        // Chỉ bật khi cần đọc response từ request có credentials.
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Những điểm cần đọc đúng:

- `allowedOrigins` là **nguồn frontend**, không phải origin của API.
- `allowedMethods` và `allowedHeaders` là quyền CORS cho method/request headers; chúng **không** cấp quyền thao tác endpoint.
- `setAllowCredentials(true)` cần được đánh giá theo mô hình session/cookie hoặc credentials của ứng dụng. Không bật bừa nếu không dùng.
- `/api/**` là pattern đường dẫn mà chính sách CORS này áp dụng trên server; nó không phải thành phần origin.
- `http.cors(Customizer.withDefaults())` đưa xử lý CORS vào Spring Security, cho phép preflight được xử lý trước các filter đòi xác thực mà preflight không mang cookie/token như actual request.
- `anyRequest().authenticated()` tiếp tục yêu cầu authentication; đoạn mẫu chưa cấu hình cụ thể resource server, session login hay các rule authorization.

Khi triển khai với nhiều môi trường, chỉ đưa `http://localhost:5173` vào dev nếu cần; tránh giữ localhost hoặc môi trường thử nghiệm trong allowlist production.

Nếu API thực sự dùng cookie phiên, hãy xây dựng bảo vệ session và CSRF riêng. Không suy luận rằng mọi request có origin được phép đều đã đăng nhập hay được phép chỉnh sửa dữ liệu.

## 7. Cấu hình tương ứng cho Spring Security Reactive / WebFlux

Trên WebFlux, sử dụng `ServerHttpSecurity`, `SecurityWebFilterChain` và `UrlBasedCorsConfigurationSource` ở package reactive:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(
            "https://app.example",
            "https://admin.example"
        ));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);

        return http
            .cors(spec -> spec.configurationSource(source))
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated())
            .build();
    }
}
~~~

Luật origin trong reactive và servlet có cùng ý nghĩa. Khác nhau ở loại filter/chuỗi bảo mật. Khi dùng `CorsWebFilter` hoặc cấu hình CORS tại WebFlux handler, cần kiểm soát thứ tự so với security chain và tránh trùng lặp luật CORS giữa nhiều tầng.

**Nguyên tắc chung:** preflight cần được xử lý thích hợp trước khi authentication chặn OPTIONS; actual request sau đó vẫn phải qua xác thực, phân quyền, CSRF và các lớp bảo vệ tương ứng.

## 8. Kiểm thử so khớp chính xác

### 8.1. Ma trận origin hợp lệ và không hợp lệ

Giả sử API cho phép hai origin `https://app.example` và `https://admin.example`:

| Origin request | Quyết định dự kiến | Lý do |
| --- | --- | --- |
| `https://app.example` | Cho phép | Khớp allowlist |
| `https://admin.example` | Cho phép | Khớp allowlist |
| `http://app.example` | Từ chối | Khác scheme |
| `https://app.example:8443` | Từ chối | Khác port |
| `https://app.example.attacker.test` | Từ chối | Host giả gần giống |
| `https://login.app.example` | Từ chối | Subdomain khác, không được liệt kê |
| `https://evil.example` | Từ chối | Origin lạ |
| `http://localhost:5173` | Từ chối ở production | Origin dev không nằm trong allowlist |
| `null` | Từ chối | Không cấp quyền cho opaque origin |

Lưu ý: tùy bộ lọc, request từ origin không được phép có thể nhận HTTP 403 hoặc response không có header CORS, nhưng trong browser kết quả chính là **không được cấp quyền đọc**. Nếu request thuộc loại cần preflight, preflight bị từ chối khiến browser không phát request chính.

### 8.2. Kiểm tra actual request qua curl

~~~bash
# Origin hợp lệ:
curl -i "https://api.example/api/products" \
  -H "Origin: https://app.example"

# Origin giả gần giống:
curl -i "https://api.example/api/products" \
  -H "Origin: https://app.example.attacker.test"

# Cùng host nhưng khác scheme:
curl -i "https://api.example/api/products" \
  -H "Origin: http://app.example"
~~~

Thay tên miền ví dụ bằng địa chỉ ứng dụng thật trước khi chạy. Curl là công cụ kiểm tra header HTTP, không phải trình duyệt; đừng xem việc curl đọc được body là CORS đã hoạt động đúng.

### 8.3. Kiểm tra preflight

~~~bash
curl -i -X OPTIONS "https://api.example/api/orders" \
  -H "Origin: https://app.example" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization, content-type"
~~~

Với origin và method/header hợp lệ, response có thể là:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: Authorization,Content-Type
Access-Control-Allow-Credentials: true
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Thay `Origin` thành `https://evil.example` và xác nhận preflight bị từ chối. Spring CORS có thể trả `403 Invalid CORS request`. Ngay cả khi preflight thành công, actual response cũng phải có CORS header phù hợp để JavaScript đọc được.

### 8.4. Ví dụ kiểm thử Servlet với MockMvc

Sau khi ứng dụng mẫu đã cấu hình CORS theo mục 6, có thể dùng kiểm thử tích hợp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsOriginIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void allowsTrustedOrigin() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://app.example")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "authorization,content-type"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "https://app.example"));
    }

    @Test
    void rejectsOtherOrigin() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://evil.example")
                .header("Access-Control-Request-Method", "POST"))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là **mẫu kiểm thử** dựa trên cấu hình và bộ phụ thuộc Spring Boot tương ứng, chưa phải test đã chạy trên một ứng dụng cụ thể. Với WebFlux, dùng `WebTestClient` để gửi tương tự các header `Origin` và `Access-Control-Request-Method`, rồi xác minh response.

## 9. Chẩn đoán lỗi trong triển khai

| Triệu chứng | Khả năng cần kiểm tra | Hành động |
| --- | --- | --- |
| Dev chạy, production lỗi | Chưa thêm origin frontend production | Xem `Origin` thực tế ở DevTools và cấu hình môi trường |
| Chỉ HTTPS chạy hoặc ngược lại | Nhầm `http` với `https` | Đối chiếu scheme; tránh tự động nới allowlist |
| Dev server đổi port thì lỗi | Origin có port mới | Cập nhật đúng origin trong môi trường dev |
| Admin frontend bị chặn | Chưa cho phép `https://admin.example` | Kiểm tra quyền tin cậy rồi thêm chính xác |
| Preflight OPTIONS nhận 401/403 | Authentication hoặc proxy chặn OPTIONS trước CORS | Kiểm tra thứ tự filter, route và response OPTIONS |
| Preflight thành công nhưng actual response lỗi CORS | Response thực tế thiếu hoặc sai `Allow-Origin` | Kiểm tra HTTP response cuối cùng, kể cả lỗi 401/403/500 |
| Response chứa nhiều `Access-Control-Allow-Origin` | App và gateway cùng thêm header | Chọn một tầng chịu trách nhiệm chính sách CORS |
| Request có credentials nhưng dùng `*` | Wildcard không hợp lệ với credentials mode | Trả origin cụ thể và `Allow-Credentials: true` khi cần |
| Lỗi không ổn định qua cache/CDN | Cache chưa phân biệt Origin | Kiểm tra `Vary: Origin` và biến thể cache |
| Trang mở từ file local có `Origin: null` | Opaque origin | Dùng local HTTP server, không nới quyền `null` bừa bãi |

Khi có reverse proxy hoặc TLS termination, trình duyệt có thể truy cập frontend qua HTTPS trong khi backend nội bộ nhận HTTP. Origin cần kiểm tra là **origin của trang frontend như browser nhìn thấy**, không phải địa chỉ nội bộ backend. Nếu CDN/gateway làm biến đổi header hoặc chèn CORS trùng lặp, cấu hình Spring ở service cuối có thể đúng nhưng frontend vẫn thất bại.

## 10. Câu hỏi vận dụng

**Tình huống A.** Frontend chạy ở `https://app.example:443`. Danh sách cho phép có `https://app.example`. Đây có phải cùng origin?

**Trả lời:** Có. HTTPS dùng port mặc định 443, và trình duyệt thường serialize thành `https://app.example`.

**Tình huống B.** API đang cho phép `https://app.example`. Một trang tại `https://app.example.attacker.test` có vượt qua kiểm tra nếu backend dùng `origin.startsWith("https://app.example")` không?

**Trả lời:** Có nguy cơ. Kiểm tra tiền tố không phân biệt ranh giới hostname, nên cần thay bằng cơ chế allowlist origin chuẩn của Spring.

**Tình huống C.** Muốn cho phép frontend ứng dụng và admin. Response có thể chứa `Access-Control-Allow-Origin: https://app.example, https://admin.example` không?

**Trả lời:** Không. Máy chủ cần so khớp mỗi request rồi trả đúng **một** origin cụ thể. Sử dụng `setAllowedOrigins(List.of(...))`.

**Tình huống D.** Cấu hình `allowedOriginPatterns("https://*.trusted.example")`. Header response có thể là `Access-Control-Allow-Origin: https://*.trusted.example` không?

**Trả lời:** Không. Pattern được xử lý ở server. Nếu khớp, Spring trả giá trị origin thực tế đã được chấp nhận, chẳng hạn `https://team.trusted.example`.

**Tình huống E.** API trả `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true`. Frontend gọi bằng `credentials: "include"` có đọc được dữ liệu không?

**Trả lời:** Không. Với credentials mode đó, wildcard không được phép. Phải trả origin cụ thể được tin cậy kèm `Access-Control-Allow-Credentials: true`.

**Tình huống F.** Gửi `curl` với `Origin: https://app.example` và nhận được dữ liệu cá nhân. Như vậy có thể dùng Origin để thay authentication không?

**Trả lời:** Không. `curl` tự giả lập được Origin; API phải xác thực và phân quyền mọi request. Nếu một client không có quyền mà đọc được dữ liệu, đó là lỗi bảo vệ API, không phải vấn đề chỉ sửa bằng CORS.

---

**Ghi nhớ:** Origin của một trang được xác định bằng **scheme, host và port**. Để cấp quyền đọc response cross-origin, Spring Security cần so khớp chính xác `Origin` với danh sách tin cậy và trả **một** giá trị `Access-Control-Allow-Origin` hợp lệ. Wildcard và pattern phải được dùng đúng ý nghĩa; không đánh đồng quyền CORS với authentication, authorization, CSRF hoặc chính sách cookie.
