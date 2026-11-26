# Thứ tự xử lý preflight trước các yêu cầu xác thực

## Mục tiêu học tập và tình huống thực tế

Trong chương **CORS** của mô-đun `SPRING_SECURITY_HTTP_PROTECTION`, thứ tự xử lý HTTP là một yếu tố quyết định. Một cấu hình origin đúng vẫn có thể thất bại nếu request `OPTIONS` do trình duyệt tạo bị authentication hoặc một thành phần trung gian từ chối **trước khi CORS kiểm tra preflight**.

Ví dụ hệ thống:

- Frontend tại `https://app.example.com`.
- REST API Spring Security tại `https://api.example.com`.
- Frontend đăng nhập bằng session cookie hoặc sử dụng bearer token.
- Người dùng cập nhật hồ sơ qua `PUT /api/profile` với `Content-Type: application/json`.

Từ phía frontend:

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

Trình duyệt thường gửi **preflight OPTIONS** trước request PUT này. Preflight chỉ hỏi liệu origin, method và request headers dự định có được phép hay không; nó không phải yêu cầu cập nhật hồ sơ và **không mang cookie phiên hoặc token xác thực của actual request theo luồng CORS thông thường**.

Nếu Security hoặc gateway bắt OPTIONS phải đăng nhập, nó có thể trả 401, chuyển hướng đến trang login hoặc trả 403. Browser khi đó **không gửi actual PUT**. Người lập trình có thể nhầm là API thiếu CSRF token, cookie không hoạt động hoặc cấu hình origin sai, trong khi nguyên nhân là **thứ tự filter**.

Sau bài học, bạn có thể:

1. Nhận diện request preflight, phân biệt nó với actual request và các OPTIONS thông thường.
2. Giải thích tại sao CORS phải xử lý preflight **trước** authentication, authorization và bước CSRF của actual request.
3. Cấu hình `HttpSecurity.cors(...)` cho Servlet và `ServerHttpSecurity.cors(...)` cho Reactive/WebFlux.
4. Chẩn đoán trường hợp CORS bị chặn ở gateway, proxy, custom filter hoặc một security chain khác.
5. Kiểm thử thứ tự bằng `curl`, DevTools, `MockMvc`, `WebTestClient`, bao gồm trường hợp preflight hợp lệ không mang credentials.
6. Giữ vững authentication, authorization, CSRF và bảo vệ session mà không phải “mở hết OPTIONS”.

Các địa chỉ thuộc `example.com` và `example.org` chỉ dùng để minh họa.

## 1. Browser gửi preflight trước actual request khi nào?

### 1.1. Preflight là một yêu cầu kiểm tra quyền CORS

Ví dụ JavaScript muốn gửi PUT JSON. Browser có thể tự tạo:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Ba trường đáng chú ý:

| Header trên preflight | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| `Origin` | `https://app.example.com` | Origin của trang chạy JavaScript |
| `Access-Control-Request-Method` | `PUT` | HTTP method của request **sẽ gửi sau**, không phải method OPTIONS hiện tại |
| `Access-Control-Request-Headers` | `content-type,x-csrf-token` | Các **tên header** không safelisted cần hỏi quyền |

Browser không dùng preflight để gửi JSON hay CSRF token thật. `Access-Control-Request-Headers` chứa **tên header**, không chứa giá trị của header đó.

Một preflight được chấp nhận có thể nhận:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Khi browser xác nhận tất cả điều kiện thích hợp, nó mới gửi actual PUT:

~~~http
PUT /api/profile HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Content-Type: application/json
X-CSRF-TOKEN: <valid-csrf-token>
Cookie: SESSION=<session-id-if-browser-allows>

{"displayName":"Lan"}
~~~

Ở request PUT thật, authentication, authorization và CSRF mới có nhiệm vụ quyết định **có được cập nhật hồ sơ hay không**.

### 1.2. Những yếu tố thường gây preflight

| Actual request frontend muốn gửi | Có thường cần preflight? | Vì sao? |
| --- | --- | --- |
| `GET` thông thường, không thêm request header tùy biến | Không | Thường đáp ứng điều kiện CORS-safelisted |
| `POST` với `Content-Type: application/json` | Có | `application/json` không phải giá trị Content-Type safelisted |
| `PUT` hoặc `DELETE` | Có | Method không thuộc tập `GET`, `HEAD`, `POST` safelisted |
| `GET` kèm `Authorization` | Có | `Authorization` không safelisted |
| `POST` với `X-CSRF-TOKEN` | Có | Request header tùy biến |
| `GET` với `credentials: "include"`, không có yếu tố khác | Không chỉ vì credentials | Credentials mode tự nó không bắt buộc preflight |

Preflight có thể được **cache** theo quy tắc trình duyệt, nên không phải lần request nào cũng thấy OPTIONS trên Network tab. Việc không thấy OPTIONS không đủ để kết luận hệ thống không áp dụng CORS.

### 1.3. OPTIONS thường không phải lúc nào cũng là CORS preflight

Một request:

~~~http
OPTIONS /api/profile HTTP/1.1
Host: api.example.com
~~~

không có `Origin` và `Access-Control-Request-Method` chưa chắc là preflight do browser tạo. Đừng xây logic bảo mật dựa trên giả định **mọi OPTIONS đều là preflight**.

Đối với CORS, framework có cơ chế nhận diện request preflight từ tổ hợp method và header. Cần phân biệt nó với OPTIONS do công cụ HTTP hoặc client khác chủ động gọi.

## 2. Vì sao preflight không nên bị authentication chặn?

### 2.1. Tách hai câu hỏi bảo mật

Preflight và actual request trả lời **hai câu hỏi khác nhau**:

- **CORS/preflight:** JavaScript ở origin này có được browser cho gửi actual request có method/header như dự định và đọc response nếu đáp ứng CORS không?
- **Authentication/authorization:** Client/user trên actual request là ai, và có được thao tác trên tài nguyên này không?
- **CSRF:** Với loại request và mô hình đăng nhập dễ bị CSRF, thao tác thay đổi trạng thái có token/chứng cứ hợp lệ không?

Preflight không có đủ thông tin để chứng minh người dùng đã đăng nhập theo cơ chế cookie hoặc bearer token của actual request. Yêu cầu nó vượt qua `authenticated()` không làm hệ thống an toàn hơn; nó thường làm browser **không thể hỏi quyền CORS**.

Browser phát preflight theo giao thức riêng; ứng dụng không thể sửa đoạn JavaScript Fetch để ép browser gắn một session cookie hoặc bearer token tự chọn vào OPTIONS như gắn vào actual request.

### 2.2. Sơ đồ sai và đúng

~~~mermaid
flowchart TD
    subgraph Wrong["Sai: Authentication đứng trước xử lý CORS"]
        A["OPTIONS preflight"] --> B["Security filter đòi session/token"]
        B --> C["Không có credentials của actual request"]
        C --> D["401 / redirect login / 403"]
        D --> E["Browser không gửi actual request"]
    end
    subgraph Right["Đúng: CORS kiểm tra preflight trước"]
        F["OPTIONS preflight"] --> G["CORS kiểm tra origin, method, request headers"]
        G --> H{"Preflight có hợp lệ?"}
        H -- "Không" --> I["Từ chối preflight"]
        H -- "Có" --> J["Trả CORS headers hợp lệ"]
        J --> K["Browser gửi actual request"]
        K --> L["Authentication + authorization + CSRF"]
        L --> M["API xử lý hoặc từ chối theo quyền thực"]
    end
~~~

Đặt CORS trước authentication **không có nghĩa** bỏ kiểm tra quyền trên API. Preflight được xử lý theo CORS rồi kết thúc; actual request mới là nơi thông tin xác thực và thao tác nghiệp vụ được xử lý.

### 2.3. CORS cũng là kiểm tra quyền, không phải cho qua mọi OPTIONS

CORS không nên trả thành công cho bất kỳ preflight nào. Bộ xử lý vẫn cần đánh giá:

- `Origin` có nằm trong tập frontend được tin cậy?
- `Access-Control-Request-Method` có được cho phép?
- Các `Access-Control-Request-Headers` có được cho phép?
- Đường dẫn API có chính sách CORS tương ứng không?
- Với browser ở credentials mode phù hợp, có sử dụng origin cụ thể và các response header đúng không?

Nếu bất kỳ điều kiện bắt buộc nào không đạt, preflight bị từ chối dù không cần user đăng nhập. **CORS trước authentication không đồng nghĩa CORS không kiểm tra gì.**

## 3. Điều gì xảy ra khi thứ tự xử lý bị sai?

Giả sử ứng dụng đã cấu hình allowlist `https://app.example.com`, nhưng một filter xử lý authentication từ chối OPTIONS trước khi CORS được chạy.

Trình duyệt gửi:

~~~http
OPTIONS /api/profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Một trong các response có vấn đề:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="API"
~~~

Hoặc:

~~~http
HTTP/1.1 302 Found
Location: /login
~~~

Hoặc:

~~~http
HTTP/1.1 403 Forbidden
~~~

Browser thường báo lỗi liên quan preflight, không gửi actual PUT và JavaScript thấy một lỗi kiểu `TypeError: Failed to fetch` / “CORS preflight failed” tùy trình duyệt.

**Không sửa bằng cách thêm `credentials: "include"` rồi mong cookie xuất hiện trong OPTIONS.** Chế độ này cho actual request sử dụng credentials theo quy tắc browser; preflight vẫn được phát theo cơ chế riêng.

### 3.1. Phân biệt 403 do CORS với 403 do CSRF

| Dấu hiệu | Lỗi CORS/preflight | Lỗi CSRF/authorization |
| --- | --- | --- |
| Request bị lỗi | `OPTIONS` | Thường là actual `POST`, `PUT`, `PATCH`, `DELETE` |
| Actual request có được gửi? | Không nếu preflight bị từ chối | Có, nếu đã qua preflight hoặc không cần preflight |
| Thành phần nên kiểm tra | CORS policy, thứ tự Security, gateway, filter | CSRF token, session, user permissions |
| Tình huống thường gặp | OPTIONS 401/403, thiếu `Allow-Origin`/`Allow-Methods` | Actual PUT 403 dù OPTIONS 200 |
| Hướng sửa | Đưa CORS vào pipeline đúng thời điểm; kiểm tra policy | Xác minh token/phiên và rule bảo mật, không mở CORS bừa |

Spring `DefaultCorsProcessor` thường phản hồi `403 Invalid CORS request` với preflight không phù hợp. Vì vậy **chỉ status 403 không đủ để xác định lớp gây lỗi**: cần xem method, headers và nguồn phản hồi.

### 3.2. 401 hoặc 403 trên actual request không tự là lỗi CORS

Một flow **đúng** vẫn có thể là:

~~~http
OPTIONS /api/profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,PUT
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
~~~

Browser sau đó gửi actual PUT, nhưng token CSRF sai:

~~~http
HTTP/1.1 403 Forbidden
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Content-Type: application/json

{"error":"access_denied"}
~~~

Ở đây browser **được đọc response 403** nếu CORS hợp lệ, rồi frontend hiển thị lỗi. CORS không cần cho PUT thành công về nghiệp vụ. Ngược lại, nếu response lỗi không có CORS headers, browser có thể che status khỏi JavaScript, khiến người lập trình chẩn đoán sai.

## 4. Thứ tự xử lý trong Spring Security Servlet

### 4.1. Vai trò của HttpSecurity.cors

Với Spring MVC / Servlet, Spring Security được thực thi trong một filter chain. Cấu hình `HttpSecurity.cors(...)` tích hợp xử lý CORS theo cách để preflight được xử lý trước các filter authentication có thể từ chối vì không có cookie/token.

Một cách cấu hình tường minh:

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
class ServletSecurityConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
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
                .anyRequest().authenticated())
            .build();
    }
}
~~~

Cách hiểu:

1. `CorsConfigurationSource` chọn policy CORS phù hợp khi request đến `/api/**`.
2. `http.cors(...)` giúp Spring Security xử lý CORS tại vị trí thích hợp trước authentication.
3. Với preflight hợp lệ, CORS có thể phản hồi trực tiếp; `anyRequest().authenticated()` không bắt browser đăng nhập ở bước OPTIONS.
4. Với actual request, `anyRequest().authenticated()` vẫn áp dụng. Khi ứng dụng thực dùng session cookie, cần bảo vệ CSRF phù hợp.
5. Ví dụ chưa cung cấp cơ chế đăng nhập hoặc resource server hoàn chỉnh; trong dự án thật phải cấu hình authentication/authorization tương ứng.

**Không nhầm `allowedMethods` với quyền endpoint.** Cho phép `PUT` qua preflight không tự cho người dùng quyền cập nhật hồ sơ.

### 4.2. Khi đã cấu hình CORS ở Spring MVC

Nếu có Spring MVC và cấu hình CORS qua `WebMvcConfigurer#addCorsMappings` hoặc `@CrossOrigin`, Spring Security có thể tận dụng cấu hình MVC khi các điều kiện tích hợp phù hợp và không có nguồn `CorsConfigurationSource` riêng được cung cấp.

Ví dụ:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class MvcCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PUT")
            .allowedHeaders(
                "Authorization", "Content-Type", "X-CSRF-TOKEN"
            )
            .allowCredentials(true);
    }
}
~~~

Khi đó có thể bật Security CORS integration:

~~~java
import org.springframework.security.config.Customizer;

// Trong SecurityFilterChain:
http.cors(Customizer.withDefaults());
~~~

**Chỉ khai báo `@CrossOrigin` hoặc `WebMvcConfigurer` nhưng để một filter authentication độc lập chặn OPTIONS trước MVC thì chưa đủ.** Bật tích hợp CORS trong Security hoặc sử dụng một filter CORS được xếp đúng thứ tự.

Nếu dự án đã có `CorsConfigurationSource` riêng hoặc nhiều security chains, cấu hình `configurationSource(...)` tường minh thường dễ xác minh hơn. Không nên để MVC, Security và proxy tạo ba chính sách CORS mâu thuẫn.

### 4.3. CorsFilter độc lập là một lựa chọn thay thế

Spring có `org.springframework.web.filter.CorsFilter` để xử lý CORS ở tầng Servlet. Một ứng dụng có thể đăng ký filter này đủ sớm ở bên ngoài security chain nếu thật sự cần.

Tuy nhiên, khi đã dùng `http.cors(...)` cùng chính sách đúng, thường **không cần tạo thêm CorsFilter servlet container độc lập**. Nếu đăng ký trùng với chính sách khác, response có thể chứa header CORS lặp hoặc mất nhất quán.

Cần phân biệt thứ tự giữa:

- Filter của servlet container do ứng dụng hoặc thư viện đăng ký.
- `FilterChainProxy` của Spring Security và các filter nằm bên trong.
- `DispatcherServlet` và Spring MVC handler mapping.

`http.cors(...)` giải quyết thứ tự **bên trong Security filter chain**, nhưng không tự vượt qua một filter tùy biến đặt **trước cả Spring Security** hoặc một gateway chặn OPTIONS từ bên ngoài.

## 5. Thứ tự xử lý trong Spring Security Reactive / WebFlux

WebFlux không dùng Servlet `CorsFilter` và `HttpServletRequest`. Thay vào đó, hệ thống dùng `WebFilter`, `ServerWebExchange` và `SecurityWebFilterChain`.

### 5.1. Tích hợp qua ServerHttpSecurity.cors

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
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
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

Điểm quan trọng là `UrlBasedCorsConfigurationSource` được import từ `org.springframework.web.cors.reactive`. Bộ xử lý CORS chạy trong security pipeline Reactive trước các bước authentication phù hợp với preflight. Actual request tiếp tục chịu xác thực, phân quyền và CSRF theo thiết kế.

### 5.2. CorsWebFilter độc lập cũng được, nhưng phải đúng thứ tự

Có thể chọn `org.springframework.web.cors.reactive.CorsWebFilter` với nguồn CORS reactive. Nếu filter hoạt động bên ngoài Spring Security, phải xác nhận thứ tự của nó so với security WebFilter; một filter CORS chạy **sau** bộ lọc đã từ chối OPTIONS sẽ không giải quyết vấn đề.

Ý tưởng đăng ký filter ưu tiên cao:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class EarlyReactiveCorsConfiguration {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    CorsWebFilter corsWebFilter(
        UrlBasedCorsConfigurationSource corsSource
    ) {
        return new CorsWebFilter(corsSource);
    }
}
~~~

Đoạn này giả định đã khai báo `UrlBasedCorsConfigurationSource` reactive dưới dạng bean, và là **phương án thay thế** cho việc cấu hình CORS trực tiếp trong `ServerHttpSecurity`. Đừng thêm vào song song theo thói quen. `@Order` cho biết ý định sắp xếp, nhưng cần xác minh thứ tự WebFilter và auto-configuration thực tế của ứng dụng.

Trong cả Servlet và Reactive, nguyên tắc đúng vẫn là: **preflight được xét CORS trước authentication; actual request vẫn được bảo vệ đầy đủ**.

## 6. Vì sao permitAll OPTIONS không thay thế CORS?

Một cách sửa lỗi phổ biến là thêm rule:

~~~java
// Ý tưởng chỉ mở phần authorization cho OPTIONS:
.requestMatchers(org.springframework.http.HttpMethod.OPTIONS, "/**")
.permitAll()
~~~

Trong WebFlux, có thể gặp cách viết tương tự:

~~~java
// Ý tưởng reactive:
.pathMatchers(org.springframework.http.HttpMethod.OPTIONS, "/**")
.permitAll()
~~~

Các rule trên chỉ ảnh hưởng tới **authorization** ở vị trí được áp dụng; chúng **không** tự:

- Nhận diện preflight dựa trên `Origin` và `Access-Control-Request-Method`.
- Kiểm tra origin, method, request headers theo policy.
- Thêm `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers`.
- Giải quyết một authentication filter tùy biến đã chặn trước authorization.
- Ngăn một proxy bên ngoài trả 401 cho OPTIONS.

Nếu preflight nhận HTTP 200 mà **không có CORS headers hợp lệ**, browser vẫn từ chối actual request. Vì vậy, cách sửa đúng là cấu hình CORS được tích hợp đủ sớm.

Đồng thời **không cần tắt CSRF toàn cục** để sửa lỗi OPTIONS. CSRF protection có vai trò riêng đối với actual request thay đổi trạng thái; một preflight OPTIONS thông thường là request đọc/kiểm tra chính sách, không phải thao tác cần CSRF token.

## 7. Credentials, cookie và CSRF: đừng lẫn với thứ tự preflight

### 7.1. Preflight không dùng cookie phiên của actual request

Với frontend `https://app.example.com` gọi API `https://api.example.com`:

~~~javascript
const res = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

`credentials: "include"` cho phép browser cân nhắc gửi session cookie trên **actual request khác origin**, nếu luật cookie cho phép. Nó không tự làm request cần preflight và không buộc browser đính cookie vào OPTIONS preflight.

Đối với request cross-origin dùng credentials mode `include`, CORS response hợp lệ để JavaScript đọc thường cần:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
~~~

Không dùng:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Vì wildcard `*` không cho phép browser chia sẻ response trong credentials mode `include`. Cookie có thể vẫn không được gửi vì `SameSite`, `Secure`, Domain/Path hoặc chính sách browser; CORS không ép được browser gửi cookie đã bị hạn chế.

### 7.2. Authenticated actual request và preflight cần các kỳ vọng khác nhau

| Kiểm tra | Preflight OPTIONS | Actual PUT / POST |
| --- | --- | --- |
| `Origin`, method và request headers | CORS phải kiểm tra | Actual response vẫn cần CORS để JS đọc |
| Session cookie / bearer token | Thông thường **không mang credentials của actual request** | Có thể mang khi browser/client được phép |
| Authentication | Không nên là điều kiện để trả lời preflight hợp lệ | Phải áp dụng theo policy API |
| Authorization | Không quyết định quyền thao tác user tại preflight | Bắt buộc kiểm tra theo endpoint/user |
| CSRF token | Không nên yêu cầu token CSRF của actual request | Cần khi loại request và mô hình xác thực đòi hỏi |
| Body business | Không có body nghiệp vụ | Có thể có JSON/form body thực |
| Kết quả thành công | Browser có thể gửi actual request | API xử lý dữ liệu hoặc từ chối theo quyền |

Một actual PUT có thể trả 403 do CSRF token sai, dù preflight được trả lời đúng. Đây **không** phải bằng chứng CORS bị cấu hình sai.

### 7.3. CORS không phải biện pháp chống CSRF

Một form cross-site dùng phương thức và content type thuộc loại không cần preflight vẫn có thể đưa request tới server. Nếu browser gửi session cookie và API thiếu chống CSRF, thay đổi trạng thái có thể xảy ra ngay cả khi browser không cho JavaScript ở trang lạ đọc response.

Do đó với Spring Security dùng session cookie, hãy duy trì CSRF protection và triển khai cơ chế cấp/gửi token phù hợp. Việc mở CORS đúng thứ tự không tự làm giảm hoặc loại bỏ trách nhiệm bảo vệ CSRF.

## 8. Những lớp đứng trước CORS có thể chặn request

Spring Security không phải lớp đầu tiên tuyệt đối của mọi kiến trúc. Một OPTIONS request có thể đi qua:

~~~mermaid
flowchart LR
    B["Browser"] --> G["CDN / reverse proxy / API gateway"]
    G --> F["Servlet filters hoặc WebFlux WebFilters tùy biến"]
    F --> S["Spring Security CORS + authentication chain"]
    S --> H["MVC/WebFlux handler"]
~~~

Đây là một sơ đồ kiến trúc điển hình, không phải thứ tự cứng của tất cả ứng dụng. CORS trong Spring Security chỉ có thể xử lý một request **đã đến được security chain**; nếu gateway chặn ở trước đó, việc đổi `HttpSecurity.cors(...)` không tự sửa gateway.

### 8.1. API gateway hoặc proxy trả lời OPTIONS trước ứng dụng

Một số gateway có thể:

- Chặn mọi OPTIONS bằng 401, 403 hoặc 405.
- Chỉ cho phép GET/POST ở route và vô tình không chuyển preflight.
- Tự xử lý CORS bằng một allowlist khác ứng dụng.
- Xóa `Origin`, `Access-Control-Request-Method` hoặc thay đổi path khi rewrite.
- Thêm `Access-Control-Allow-Origin` lần thứ hai trên response.

Cần quyết định một cách nhất quán:

- **Gateway chịu trách nhiệm CORS:** gateway phải cho preflight đúng policy, trả đúng headers và bảo đảm actual response có header CORS tương ứng, kể cả response lỗi; backend vẫn thực hiện auth/CSRF.
- **Ứng dụng Spring chịu trách nhiệm CORS:** gateway phải chuyển tiếp OPTIONS phù hợp và không chèn header mâu thuẫn; Spring Security xử lý preflight sớm.

Không kết luận “Spring CORS hỏng” khi request chưa từng đến Spring.

### 8.2. Custom authentication filter đặt quá sớm

Một filter tự viết có thể kiểm tra mọi request:

~~~java
// Mẫu anti-pattern trong một filter tùy biến:
// Từ chối ngay tất cả request thiếu token, kể cả CORS preflight.
if (authorizationHeader == null) {
    // trả 401 trước khi thành phần CORS chạy
}
~~~

Nếu filter này chạy **trước CORS**, browser không thể dùng giao thức preflight.

Hướng khắc phục:

1. Ưu tiên tích hợp auth filter vào Spring Security đúng vị trí để CORS được chạy trước.
2. Nếu có filter ở bên ngoài security chain, kiểm soát thứ tự registration và bảo đảm CORS được xử lý trước bước authentication phù hợp.
3. Chỉ khi cần xử lý riêng, nhận diện **preflight thật** bằng cơ chế của framework, không bỏ qua authentication cho mọi OPTIONS hoặc mọi request có thể giả mạo.
4. Giữ mọi kiểm tra authentication/authorization trên **actual request**, kể cả method OPTIONS nếu ứng dụng có endpoint OPTIONS nghiệp vụ riêng và chính sách yêu cầu xác thực.

Việc đổi thứ tự phải đi cùng test preflight và actual request, không chỉ test header trên response HTTP 200.

### 8.3. HTTP firewall và lỗi malformed request

Spring Security HTTP firewall hoặc proxy có thể từ chối request không hợp lệ trước khi nó được xử lý CORS. Đây có thể là biện pháp bảo vệ có chủ đích, không nhất thiết là lỗi thứ tự. Đừng nới lỏng HTTP firewall chỉ để làm một preflight malformed “thành công”; hãy kiểm tra chính xác method, URL, header và định dạng request thực tế.

## 9. Nhiều SecurityFilterChain và nhiều nguồn cấu hình CORS

Trong ứng dụng Servlet có thể tồn tại các `SecurityFilterChain` khác nhau cho `/api/**` và `/admin/**`, mỗi chain có rule authentication riêng. Trong Reactive cũng có thể có nhiều `SecurityWebFilterChain`.

**Preflight được chọn vào chain theo request OPTIONS thực sự**, không phải theo một method “được hỏi” bên trong `Access-Control-Request-Method` nếu chain dùng rule method để matching. Đây là lỗi đặc biệt dễ bỏ sót.

Ví dụ một chain chỉ khớp request HTTP POST:

~~~java
// Ví dụ về một matcher phạm vi quá hẹp cho CORS:
// Chain này không tự nhận OPTIONS preflight của POST.
http.securityMatcher(request ->
    "POST".equals(request.getMethod())
        && request.getServletPath().startsWith("/api/")
);
~~~

Nếu preflight là `OPTIONS /api/orders` và dùng header `Access-Control-Request-Method: POST`, matcher kiểm tra **HTTP method OPTIONS**, nên không khớp chain chỉ nhận POST. Một chain khác hoặc tầng mặc định có thể xử lý OPTIONS và chặn nó.

Giải pháp thường là xây các chain theo **đường dẫn rõ ràng** đủ để cả OPTIONS và actual request liên quan đi qua nơi có xử lý CORS, rồi áp dụng phân quyền method-specific trong các rule tiếp theo. Nếu bắt buộc matching theo method, phải bảo đảm có một đường xử lý preflight an toàn trước các matcher đó.

Các câu hỏi cần đặt:

- Preflight OPTIONS thật sự rơi vào security chain nào?
- Chain đó có `cors(...)` với đúng `CorsConfigurationSource` không?
- Có chain nào bắt authentication cho OPTIONS trước CORS không?
- MVC/WebFlux source có đăng ký path của request sau proxy rewrite chưa?
- Với nhiều nguồn CORS, chain dùng source nào? Có bị mâu thuẫn với gateway không?

Không dựa vào việc một `CorsConfigurationSource` bean tồn tại để kết luận mọi chain tự động xử lý CORS đúng. Khi cần, gắn nguồn CORS **tường minh** cho chain tương ứng.

## 10. Kiểm thử thủ công: chứng minh preflight không cần phiên đăng nhập

### 10.1. Thử preflight bằng curl

Thay hostname giả định bằng địa chỉ API thật khi triển khai.

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

**Quan trọng:** không gửi `Cookie` hay `Authorization` trong lệnh này. Mục tiêu là xác minh preflight hợp lệ **không cần phiên đăng nhập**.

Kỳ vọng logic:

- HTTP 2xx hoặc response preflight thành công từ CORS processor.
- `Access-Control-Allow-Origin` trả origin tin cậy cụ thể.
- `Access-Control-Allow-Methods` bao gồm `PUT`.
- `Access-Control-Allow-Headers` cho phép `Content-Type` và `X-CSRF-TOKEN`.
- `Access-Control-Allow-Credentials: true` nếu cấu hình API cần browser gửi/đọc credentials mode `include`.
- Không bị redirect tới `/login` hay trả 401 vì thiếu session.

Thử origin không tin cậy:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://evil.example.org" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: content-type"
~~~

Preflight này phải **không được cấp quyền CORS**. Với bộ xử lý mặc định, Spring thường trả 403 cho request CORS không hợp lệ.

Thử method không được phép:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: DELETE"
~~~

Nếu policy chỉ cho GET/POST/PUT, preflight DELETE không đạt dù origin đúng.

### 10.2. Thử actual request tách biệt

Sau khi OPTIONS đạt, gửi actual request không có thông tin đăng nhập:

~~~bash
curl -i -X PUT "https://api.example.com/api/profile" \
  -H "Origin: https://app.example.com" \
  -H "Content-Type: application/json" \
  --data '{"displayName":"Lan"}'
~~~

Actual request này **không nên tự động được cập nhật dữ liệu**. Với endpoint cần đăng nhập/CSRF, server có thể trả 401 hoặc 403, tùy cấu hình authentication và CSRF. Một số ứng dụng chuyển hướng đến login; cần xác định cơ chế thực tế. Mục tiêu là chứng minh: **preflight được phép không mở quyền nghiệp vụ**.

Không dùng `curl` làm bằng chứng JavaScript sẽ đọc response trong browser: curl không áp dụng SOP/CORS của trình duyệt. Trên PowerShell cũ, `curl` có thể là alias của `Invoke-WebRequest`; hãy dùng `curl.exe` nếu cần đúng cú pháp dòng lệnh.

### 10.3. Ma trận phân biệt sự cố

| Test | Preflight | Actual request | Điều muốn chứng minh |
| --- | --- | --- | --- |
| Origin tin cậy, PUT và headers hợp lệ, không cookie | Thành công | Chưa gửi trong test này | CORS không yêu cầu session trên OPTIONS |
| Origin lạ, PUT hợp lệ | Bị từ chối | Browser không gửi | CORS vẫn kiểm tra allowlist |
| Origin đúng, method DELETE không được phép | Bị từ chối | Browser không gửi | CORS kiểm tra method |
| Origin đúng, header `x-admin-override` lạ | Bị từ chối | Browser không gửi | CORS kiểm tra request headers |
| OPTIONS thành công rồi actual PUT không login | Thành công | Từ chối theo auth/CSRF | Quyền CORS khác quyền tài nguyên |
| OPTIONS thành công rồi actual PUT thiếu CSRF | Thành công | Có thể bị 403 | CSRF áp dụng riêng với actual request |
| GET đơn giản, không preflight | Không xuất hiện | Có thể bị 401/403 | Actual response vẫn cần header CORS phù hợp |
| OPTIONS nhận 401 ngay tại gateway | Bị chặn trước Spring | Browser không gửi | Phải xử lý ở tầng gateway/filter trước đó |

## 11. Kiểm thử Servlet bằng MockMvc

Giả sử ứng dụng Spring Boot, Spring MVC và Spring Security đã nạp chính sách Servlet ở mục 4. Một integration test có thể mô phỏng preflight **không mang cookie/token**:

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
class CorsPreflightOrderingTest {

    @Autowired
    MockMvc mvc;

    @Test
    void allowsPreflightWithoutAuthentication() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "PUT")
                .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "https://app.example.com"))
            .andExpect(header().string(
                "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void rejectsUntrustedOriginBeforeActualRequest() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://evil.example.org")
                .header("Access-Control-Request-Method", "PUT"))
            .andExpect(status().isForbidden());
    }

    @Test
    void rejectsUnsupportedPreflightMethod() throws Exception {
        mvc.perform(options("/api/profile")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "DELETE"))
            .andExpect(status().isForbidden());
    }
}
~~~

Các test trên minh họa kiểm tra CORS processor của Spring khi Security chain đã tích hợp đúng. Cần các dependency test, Spring context và source CORS phù hợp trong dự án thật; đây **không phải bộ test đã chạy** trên project cụ thể.

**Bổ sung quan trọng:** viết một test riêng cho actual `PUT` không có session hoặc thiếu CSRF token. Nó cần xác minh request bị từ chối theo auth/CSRF, **không phải** mong HTTP 200 chỉ vì preflight đã đạt. Nếu kiểm tra status, phải biết rõ entry point authentication và thứ tự CSRF thực tế của ứng dụng.

Khi có reverse proxy hoặc custom Servlet filter bên ngoài Spring Security, `MockMvc` có thể **không tái hiện đầy đủ** tầng gateway/container. Hãy kết hợp test HTTP ở môi trường triển khai.

## 12. Kiểm thử Reactive bằng WebTestClient

Với WebFlux, sử dụng `WebTestClient` để kiểm tra pipeline `SecurityWebFilterChain` đã nạp cấu hình ở mục 5:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.http.HttpHeaders.*;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCorsPreflightOrderingTest {

    @Autowired
    WebTestClient client;

    @Test
    void preflightPassesWithoutSessionCookie() {
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
    void preflightRejectsUntrustedOrigin() {
        client.options()
            .uri("/api/profile")
            .header(ORIGIN, "https://evil.example.org")
            .header(ACCESS_CONTROL_REQUEST_METHOD, "PUT")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Giống MockMvc, `WebTestClient` kiểm tra HTTP behavior trong ứng dụng, nhưng không thay thế DevTools browser để xác nhận cookie policy, SOP, preflight cache, redirects hoặc tình huống third-party cookies. Bộ test trên cũng là **ví dụ chưa chạy**.

Nếu dùng một `CorsWebFilter` riêng, cần thêm test xác minh filter được sắp xếp trước security WebFilters, và kiểm tra không có hai nguồn CORS làm response header bị lặp.

## 13. Chẩn đoán theo lớp trước khi chỉnh cấu hình

### 13.1. Quy trình trong DevTools

1. Mở frontend thật ở đúng origin; bật **Network** và thử request tạo lỗi.
2. Xác định có `OPTIONS` không. Nếu có, xem `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` của OPTIONS.
3. Xem **OPTIONS response**: có 401, 302, 403 hay thiếu CORS headers? Có thể xác định tầng trả lỗi từ response headers, server logs hoặc tracing.
4. Nếu OPTIONS bị chặn, kiểm tra thứ tự Security CORS, chọn chain, custom filter và gateway. Đừng sửa CSRF của actual request trước khi có bằng chứng.
5. Nếu OPTIONS đạt, tìm actual request. Xem auth/authorization/CSRF và CORS headers của **actual response**, kể cả response lỗi.
6. Nếu cookie vắng mặt, kiểm tra Fetch `credentials`, cookie `SameSite`, `Secure`, Domain/Path và chính sách browser.
7. Nếu chỉ lỗi sau gateway, so sánh request/response trực tiếp vào ứng dụng và qua gateway. Đặc biệt kiểm tra path rewrite và filter route OPTIONS.

### 13.2. Bảng nguyên nhân và hành động

| Triệu chứng | Nguồn gốc có thể | Cách xử lý |
| --- | --- | --- |
| `OPTIONS` 401, `PUT` không xuất hiện | Auth filter kiểm tra trước CORS | Tích hợp CORS đúng vị trí, xác minh thứ tự filter |
| `OPTIONS` 302 đến `/login` | Authentication entry point xử lý preflight | Để CORS xử lý OPTIONS trước login/redirect |
| `OPTIONS` 403 `Invalid CORS request` | Origin/method/header/path không được phép | Sửa policy dựa trên request thực tế, không bỏ auth |
| `OPTIONS` 405 từ gateway | Gateway route không cho OPTIONS | Cấu hình gateway chuyển tiếp hoặc xử lý CORS đúng |
| `OPTIONS` 200 nhưng browser vẫn từ chối | Thiếu `Allow-Origin`/`Allow-Methods`/`Allow-Headers` hoặc credentials | Kiểm tra response headers preflight, không chỉ status |
| OPTIONS đúng, actual PUT 401 | Session/token thiếu hoặc sai | Kiểm tra auth trên actual request |
| OPTIONS đúng, actual PUT 403 | Thiếu quyền hoặc CSRF token | Kiểm tra rule authorization và CSRF |
| Actual response 401/403 nhưng JS báo CORS | Error response thiếu CORS headers phù hợp | Bảo đảm CORS được xử lý sớm và nhất quán |
| Cấu hình `cors()` ở chain A nhưng OPTIONS vào chain B | Security matcher không bao phủ OPTIONS | Rà soát chain selection, cấu hình CORS cho đúng chain |
| CORS hoạt động trực tiếp nhưng lỗi qua CDN | Gateway chặn OPTIONS, sửa header, cache sai | So headers từng tầng; xử lý một nguồn CORS nhất quán |
| Header `Allow-Origin` xuất hiện hai lần | Nhiều filter/gateway cùng thêm | Thống nhất nơi phát chính sách CORS |
| Cookie không gửi dù CORS hợp lệ | Fetch mode hoặc luật cookie | Điều tra cookie riêng, không đổi thứ tự preflight bừa |
| Có lúc không thấy OPTIONS | Preflight cache hoặc request safelisted | Xem điều kiện Fetch, cache, không kết luận là lỗi |
| Gửi OPTIONS không có các header CORS nhưng bị auth | Đó có thể là OPTIONS thông thường | Phân biệt bằng `Origin` và `Access-Control-Request-Method` |

### 13.3. Đừng dùng no-cors hoặc mở wildcard làm cách sửa

Hai thay đổi dễ tạo cảm giác “hết lỗi” nhưng không giải quyết vấn đề:

~~~javascript
// SAI nếu frontend cần đọc JSON:
fetch("https://api.example.com/api/profile", {
  mode: "no-cors"
});
~~~

`no-cors` thường làm response bị hạn chế đọc (*opaque*), không cho JavaScript xử lý dữ liệu như nhu cầu. Nó không sửa thứ tự filter hay quyền auth.

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Đây không phải cấu hình hợp lệ để browser chia sẻ response của request dùng credentials mode `include`. Mở wildcard hoặc phản chiếu mọi `Origin` còn tạo rủi ro lộ dữ liệu nếu origin không tin cậy được cấp quyền đọc.

## 14. Checklist kiểm tra thứ tự trước khi triển khai

- [ ] Đã phân biệt preflight `OPTIONS` thật với OPTIONS HTTP thông thường.
- [ ] CORS kiểm tra origin, method và request headers trước những bước authentication chặn preflight.
- [ ] `HttpSecurity.cors(...)` hoặc `ServerHttpSecurity.cors(...)` được cấu hình trên **đúng chain** xử lý request.
- [ ] Nếu dùng `CorsFilter`/`CorsWebFilter` độc lập, thứ tự thực tế trước Security được xác minh và không xử lý trùng.
- [ ] Gateway/proxy không chặn OPTIONS hoặc phản hồi policy CORS mâu thuẫn.
- [ ] Preflight hợp lệ **không mang cookie/token** vẫn được xử lý thành công.
- [ ] Preflight từ origin lạ, sai method và sai request header vẫn bị từ chối.
- [ ] Actual request không authenticated hoặc thiếu quyền vẫn bị từ chối, dù preflight thành công.
- [ ] CSRF protection trên actual request dùng session cookie vẫn hoạt động.
- [ ] Actual response thành công và response 401/403 có CORS headers phù hợp nếu frontend cần đọc status.
- [ ] Phạm vi origin tin cậy không bị mở rộng vô tình, đặc biệt với `allowCredentials(true)`.
- [ ] Đã test trong browser thật và qua đường đi deployment đầy đủ, không chỉ trong unit test của handler.

## 15. Câu hỏi vận dụng có đáp án

**Tình huống A.** Browser gửi `OPTIONS /api/profile` có `Origin` và `Access-Control-Request-Method: PUT`, nhưng filter JWT trả 401 vì không có bearer token. Nên yêu cầu browser gửi JWT trong OPTIONS hay đổi thứ tự?

**Đáp án:** Đổi cách tích hợp/thứ tự để CORS xử lý preflight trước authentication. Browser phát preflight theo giao thức riêng và thường không mang token của actual request. JWT vẫn bắt buộc được kiểm tra trên actual PUT nếu endpoint yêu cầu.

**Tình huống B.** Nhóm cấu hình `permitAll` cho toàn bộ HTTP OPTIONS, nhận HTTP 200 nhưng Console vẫn báo preflight CORS error. Vì sao?

**Đáp án:** `permitAll` chỉ tác động authorization; response vẫn cần `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers` hợp lệ theo request. Cần cấu hình CORS, không chỉ rule authorization.

**Tình huống C.** Preflight hợp lệ trả 200; actual PUT trả 403 vì thiếu CSRF token. Có nên tắt CSRF để “CORS hoạt động” không?

**Đáp án:** Không. CORS đã xử lý đúng. Actual request cần CSRF token hợp lệ theo thiết kế nếu ứng dụng dựa trên session cookie và dễ bị CSRF.

**Tình huống D.** Chỉ có `SecurityFilterChain` dành cho POST bật CORS; preflight OPTIONS của POST bị chain khác từ chối. Tại sao?

**Đáp án:** Security matcher thường xét **method thực tế của request**, tức OPTIONS, không dùng `Access-Control-Request-Method: POST` để tự khớp chain POST. Phải bảo đảm preflight được CORS xử lý trong chain hoặc filter đủ sớm.

**Tình huống E.** Spring Security đã bật CORS, nhưng API gateway trả 401 cho mọi OPTIONS trước khi chuyển tiếp. Thay đổi `http.cors(...)` có đủ không?

**Đáp án:** Không. Request chưa đến Spring. Gateway phải xử lý CORS hợp lệ hoặc chuyển tiếp preflight đến ứng dụng theo chính sách nhất quán.

**Tình huống F.** OPTIONS không mang cookie được chấp nhận. Điều đó có nghĩa actual PUT thiếu cookie cũng được cập nhật hồ sơ không?

**Đáp án:** Không. Preflight chỉ xác nhận quyền CORS. Actual PUT vẫn cần authentication, authorization và CSRF theo thiết kế; API phải từ chối khi thiếu quyền.

**Tình huống G.** Request GET đơn giản không thấy OPTIONS nhưng JavaScript vẫn báo CORS. Có nghĩa thứ tự preflight sai không?

**Đáp án:** Chưa chắc. GET có thể không cần preflight. Cần xem **actual response** có `Access-Control-Allow-Origin` phù hợp không, và nếu request dùng credentials mode `include` thì có `Access-Control-Allow-Credentials: true` không.

**Tình huống H.** Preflight bị trả 403. Có cách nào biết đây là do CORS hay CSRF?

**Đáp án:** Xem method thật của request bị lỗi và body/headers/log. Preflight OPTIONS không nên cần CSRF token của actual request; 403 kèm `Invalid CORS request` thường chỉ chính sách CORS không đạt, còn 403 trên actual PUT có thể do CSRF/authorization. Đừng đoán chỉ từ mã 403.

---

**Ghi nhớ:** Browser gửi **preflight để hỏi chính sách CORS**, không phải để chứng minh phiên đăng nhập. CORS phải xử lý **preflight trước authentication/authorization có thể chặn OPTIONS**, nhưng vẫn từ chối origin, method hoặc headers không được phép. Sau đó, **actual request** tiếp tục chịu authentication, authorization, CSRF và bảo vệ session. Cấu hình `http.cors(...)` cho Servlet hoặc `ServerHttpSecurity.cors(...)` cho Reactive, đồng thời kiểm soát gateway, filter ordering và security chain thực sự nhận request.
