# CorsFilter cùng tích hợp cấu hình Spring MVC

## 1. Vì sao CorsFilter và Spring MVC cần được phối hợp?

Một ứng dụng Spring Boot sử dụng Spring MVC để cung cấp REST API tại `https://api.example.com` và Spring Security để xác thực, phân quyền. Giao diện tại `https://app.example.com` thực hiện:

~~~javascript
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": "<csrf-token>"
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

Trình duyệt thường gửi **preflight OPTIONS** trước `POST` vì `Content-Type: application/json` không nằm trong nhóm CORS-safelisted và `X-CSRF-TOKEN` là header tùy biến. Preflight không mang cookie phiên của actual request. Nếu Spring Security yêu cầu xác thực ngay trước khi CORS được xử lý, preflight có thể nhận 401 hoặc 403 và browser không gửi `POST`.

Vấn đề thiết kế đặt ra: **Ai quyết định quy tắc CORS, và lớp nào áp dụng quy tắc trước authentication?**

Spring cung cấp hai cấp độ cơ chế liên quan:

- **Spring MVC** cho phép khai báo CORS ở cấp controller hoặc toàn ứng dụng, thông qua `@CrossOrigin` và `WebMvcConfigurer#addCorsMappings`.
- **CorsFilter** xử lý CORS ở tầng Servlet Filter, với một `CorsConfigurationSource` cung cấp chính sách cho request. Spring Security cũng có cơ chế tích hợp CORS trong security filter chain qua `HttpSecurity.cors(...)`.

Bài học thuộc phạm vi **SPRING_SECURITY_HTTP_PROTECTION**, nơi CORS phối hợp cùng CSRF, security headers, CSP, HSTS, HTTP firewall, session và phân quyền. Trọng tâm là **Servlet và Spring MVC**, đồng thời đối chiếu cách làm tương ứng trên **Reactive/WebFlux**.

### Mục tiêu học tập

Sau khi đọc, bạn có thể:

1. Mô tả nhiệm vụ của `CorsFilter`, `CorsConfigurationSource`, `CorsConfiguration` và bộ xử lý CORS.
2. Phân biệt khai báo CORS ở Spring MVC với việc xử lý CORS ở Servlet Filter.
3. Cấu hình `http.cors(Customizer.withDefaults())` để Spring Security sử dụng chính sách của MVC khi đủ điều kiện.
4. Biết khi nào cần chỉ định `CorsConfigurationSource` riêng, khi nào mới nên đăng ký `CorsFilter` độc lập.
5. Giải thích các lỗi do thứ tự filter, nhiều `SecurityFilterChain`, MVC và gateway cùng cấu hình CORS.
6. Kiểm thử preflight, actual response, cookie, quyền đọc và xung đột với authentication/CSRF.

## 2. Hai tầng xử lý và luồng preflight

Trong ứng dụng Servlet, một request đi qua **Servlet Filter chain** trước khi đến `DispatcherServlet` và controller của Spring MVC. Spring Security được tích hợp bằng filter chain; các filter xác thực/phân quyền có thể từ chối request trước khi controller được gọi.

Nếu chỉ khai báo `@CrossOrigin` ở controller nhưng thiếu tích hợp CORS đúng thứ tự trong Security, cấu hình MVC có thể **không cứu được preflight** đã bị chặn trước `DispatcherServlet`.

~~~mermaid
flowchart TD
    A["Browser gửi OPTIONS preflight"] --> B["Servlet filter chain"]
    B --> C["CORS được tích hợp trước authentication"]
    C --> D["Đọc policy: CorsConfigurationSource hoặc MVC"]
    D --> E{"Origin/method/headers hợp lệ?"}
    E -- "Không" --> F["Từ chối preflight"]
    E -- "Có" --> G["Trả CORS response, kết thúc preflight"]
    G --> H["Browser gửi actual request"]
    H --> I["CORS xử lý actual request"]
    I --> J["Spring Security kiểm tra xác thực, quyền, CSRF"]
    J --> K["DispatcherServlet / Controller"]
~~~

Đây là thứ tự **logic mong muốn** cho request CORS trong Spring Security; ứng dụng có thể còn proxy, firewall, filter tùy biến hoặc nhiều security chains.

Hai trường hợp khác nhau:

- **Preflight:** browser gửi `OPTIONS` cùng `Origin`, `Access-Control-Request-Method` và có thể có `Access-Control-Request-Headers`. Nếu CORS thành công, thành phần xử lý CORS có thể trả response ngay, không đi đến controller và không yêu cầu session đăng nhập.
- **Actual request:** được xử lý CORS để gắn header và kiểm tra quyền đọc; phần xử lý business vẫn phải chịu authentication, authorization, CSRF và các quy tắc của ứng dụng.

CORS là cơ chế browser kiểm soát **quyền đọc response khác origin**. Một số actual request vẫn đến server dù response bị browser chặn đọc. Vì vậy CORS không phải tường lửa dành cho mọi HTTP client và không thể thay thế CSRF.

## 3. CorsFilter thực sự làm gì?

Lớp `org.springframework.web.filter.CorsFilter` là một Servlet Filter của Spring Web. Nó sử dụng:

- `CorsConfigurationSource` để **lấy chính sách CORS** cho request.
- `CorsProcessor` để **kiểm tra request**, áp dụng các response headers CORS và quyết định có tiếp tục filter chain hay không.

Các lớp liên quan:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| `CorsConfiguration` | Mô tả danh sách origin, methods, headers, credentials và thời gian cache | Cho `https://app.example.com` dùng `POST` |
| `CorsConfigurationSource` | Trả `CorsConfiguration` cho một request | Chọn policy theo URL |
| `UrlBasedCorsConfigurationSource` | Triển khai source dựa trên path | `/api/**`, `/admin/**` |
| `CorsProcessor` | So sánh `Origin`, method và request headers; ghi CORS response headers | `DefaultCorsProcessor` |
| `CorsFilter` | Áp dụng processor trong Servlet Filter chain | Xử lý `OPTIONS` trước controller |
| `HttpSecurity.cors(...)` | Tích hợp xử lý CORS vào Spring Security | Đảm bảo preflight được xử lý đủ sớm |

### 3.1. Preflight không phải HTTP OPTIONS thông thường

Một preflight CORS hợp lệ cần các header yêu cầu cụ thể, ví dụ:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type, x-csrf-token
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Bộ xử lý CORS trả lời preflight hợp lệ và không chuyển tiếp đến xử lý business thông thường. Nếu origin, method hoặc header không được phép, preflight có thể trả `403 Invalid CORS request` với bộ xử lý mặc định; proxy hay filter tùy biến có thể thay đổi biểu hiện.

Một `OPTIONS` **không** có `Origin` và `Access-Control-Request-Method` không nhất thiết là preflight CORS. Endpoint OPTIONS thông thường có thể được xử lý theo cơ chế HTTP khác.

### 3.2. Actual request đi tiếp như thế nào?

Sau preflight, browser gửi actual `POST`:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: SESSION=<session-id-if-allowed>
Content-Type: application/json
X-CSRF-TOKEN: <csrf-token>

{"productId":42}
~~~

Với actual request có quyền CORS hợp lệ, `CorsFilter`/thành phần tích hợp CORS thêm header tương ứng rồi cho request đi tiếp đến các bước xử lý tiếp theo. Spring Security vẫn có thể trả `401`, `403` hoặc một trạng thái khác vì thiếu login, thiếu quyền, CSRF token sai hoặc lỗi endpoint.

Nếu actual response có các header CORS phù hợp, JavaScript đọc được status 401/403 và xử lý. Nếu response lỗi thiếu CORS headers, frontend có thể chỉ thấy lỗi CORS dù nguyên nhân gốc là authentication/CSRF.

## 4. Cấu hình CORS ngay trong Spring MVC

Spring MVC có thể lưu CORS policy ở cấp **handler** hoặc cấu hình **global**. Đây là cách tự nhiên nếu API đã dùng `@RestController` và `@RequestMapping`.

### 4.1. Cấu hình toàn cục bằng WebMvcConfigurer

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
                "Authorization",
                "Content-Type",
                "X-CSRF-TOKEN"
            )
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(600);

        registry.addMapping("/admin/**")
            .allowedOrigins("https://admin.example.com")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Authorization", "Content-Type")
            .allowCredentials(true);
    }
}
~~~

Nhìn vào cấu hình:

- `addMapping("/api/**")` chọn **path của API**, không phải origin của frontend.
- `allowedOrigins` là những origin nguồn được browser cấp quyền đọc.
- `allowedMethods` và `allowedHeaders` khai báo các quyền preflight.
- `exposedHeaders` xác định response headers tùy biến mà JavaScript được đọc.
- `allowCredentials(true)` yêu cầu trả `Access-Control-Allow-Credentials: true` trong trường hợp phù hợp, và cần origin cụ thể hoặc pattern an toàn.
- `maxAge(600)` cho phép cache kết quả preflight trong giới hạn trình duyệt.

Đây là **chính sách CORS**, chưa nói gì về việc user nào được `PUT`, ai được đăng nhập hay cookie có thuộc tính `SameSite` nào. Những quyết định đó thuộc Spring Security và cơ chế session/cookie.

### 4.2. Cấu hình cục bộ bằng @CrossOrigin

Với một controller cụ thể:

~~~java
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
@CrossOrigin(
    origins = "https://app.example.com",
    methods = {org.springframework.web.bind.annotation.RequestMethod.GET}
)
class CatalogController {

    @GetMapping
    String catalog() {
        return "public-catalog";
    }
}
~~~

`@CrossOrigin` có thể đặt ở class hoặc method. Nếu global MVC CORS và `@CrossOrigin` cùng áp dụng lên một handler, các cấu hình có thể **được kết hợp** theo quy tắc của Spring MVC: thuộc tính danh sách có thể hợp nhất, còn một số thuộc tính đơn nhận ưu tiên từ cấp cục bộ.

Ví dụ, đừng giả định rằng thêm `@CrossOrigin(origins = "https://admin.example.com")` ở một method sẽ luôn **thu hẹp** origin đã cho phép bởi global `/api/**`. Hãy kiểm tra tập origin hiệu lực bằng test; việc kết hợp cấu hình danh sách có thể làm tập origin **rộng hơn dự kiến**.

### 4.3. MVC không phải nguồn quyết định duy nhất về bảo mật

Một controller có `@CrossOrigin` không tự tạo session hay cho phép client bypass CSRF. Tương tự, bật MVC CORS trong `WebMvcConfigurer` không đảm bảo preflight đi tới MVC nếu filter bảo mật đã chặn nó từ trước.

Để tích hợp đúng với Spring Security Servlet, cần làm bước ở phần tiếp theo.

## 5. Tích hợp CORS của Spring MVC vào Spring Security

Nếu ứng dụng dùng Spring MVC và chính sách đã khai báo qua `WebMvcConfigurer` hoặc `@CrossOrigin`, trong điều kiện Spring Security **không được cung cấp một CorsConfigurationSource riêng**, Spring Security có thể sử dụng cấu hình CORS của MVC.

Cấu hình Security điển hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/**", "/admin/**").authenticated()
                .anyRequest().denyAll())
            .build();
    }
}
~~~

Ở đây `http.cors(Customizer.withDefaults())` là bước **bật tích hợp CORS trong Spring Security**. Khi Spring MVC có mặt và không có nguồn `CorsConfigurationSource` riêng được cung cấp, Spring Security có thể dùng các chính sách CORS mà MVC biết để kiểm tra preflight sớm.

Đó là lý do cấu hình `WebMvcConfigurer` ở mục 4 có thể được tái sử dụng mà không cần đăng ký thêm `@Bean CorsFilter`.

> **Không cần thêm CorsFilter Servlet độc lập khi tích hợp CORS của Spring Security đã xử lý cùng chính sách đúng thứ tự.** Đăng ký thêm filter có thể khiến cùng request được xử lý CORS ở nhiều tầng, gây khó chẩn đoán khi các chính sách không giống nhau.

Các bước logic:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SC as Spring Security CORS integration
    participant MVC as Spring MVC CORS configuration
    participant A as Authentication / CSRF
    participant C as Controller

    B->>SC: OPTIONS /api/orders
    SC->>MVC: Lấy CorsConfiguration theo handler/path
    MVC-->>SC: Allowed origins/methods/headers
    SC-->>B: Preflight response hợp lệ
    B->>SC: Actual POST /api/orders
    SC->>MVC: Lấy cấu hình CORS phù hợp
    MVC-->>SC: CorsConfiguration
    SC->>A: Chuyển tiếp actual request
    A->>C: Chỉ khi xác thực/CSRF/quyền hợp lệ
    C-->>B: Actual response có CORS headers
~~~

Sơ đồ diễn tả cách phối hợp tổng quát, không nhất thiết phản ánh đúng từng method call nội bộ ở mọi phiên bản Spring.

### 5.1. Khi Spring Security không tự tìm được nguồn MVC phù hợp

Nếu ứng dụng không có Spring MVC, có nhiều `CorsConfigurationSource` beans, hoặc cấu hình nhiều security chains, đừng giả định `http.cors(withDefaults())` luôn chọn đúng nguồn.

Trong trường hợp cần xác định rõ chính sách, dùng:

~~~java
http.cors(cors -> cors.configurationSource(myCorsConfigurationSource));
~~~

Một cấu hình tường minh sẽ giúp người đọc và người kiểm thử biết đúng `CorsConfigurationSource` nào đã được gắn vào chain.

### 5.2. Không nhầm permitAll của OPTIONS với CORS

Có người sửa lỗi preflight 401 bằng:

~~~java
.requestMatchers(org.springframework.http.HttpMethod.OPTIONS, "/**")
.permitAll()
~~~

Điều này chỉ nói với authorization rằng request OPTIONS được phép đi tiếp, **không** tự tạo `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` hoặc `Access-Control-Allow-Headers`. Browser vẫn từ chối nếu response thiếu quyền CORS.

Cách xử lý là cấu hình CORS đúng vào pipeline, để preflight được xử lý bằng `Origin`, method và headers dự định; authentication/authorization tiếp tục bảo vệ actual request.

## 6. Cấu hình nguồn CORS riêng khi không dùng MVC làm nguồn chính

Một hệ thống có thể cần nguồn CORS tập trung độc lập với annotations/controller, chẳng hạn có nhiều path API hoặc nhiều security chains với yêu cầu rõ ràng. Khi đó, sử dụng `UrlBasedCorsConfigurationSource` và chỉ định cho `HttpSecurity`.

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
class ExplicitCorsSecurityConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration api = new CorsConfiguration();
        api.setAllowedOrigins(List.of("https://app.example.com"));
        api.setAllowedMethods(List.of("GET", "POST", "PUT"));
        api.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        api.setExposedHeaders(List.of("X-Request-Id"));
        api.setAllowCredentials(true);
        api.setMaxAge(600L);

        CorsConfiguration admin = new CorsConfiguration();
        admin.setAllowedOrigins(List.of("https://admin.example.com"));
        admin.setAllowedMethods(List.of("GET", "POST"));
        admin.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        admin.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", api);
        source.registerCorsConfiguration("/admin/**", admin);
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
                .requestMatchers("/api/**", "/admin/**").authenticated()
                .anyRequest().denyAll())
            .build();
    }
}
~~~

Ở cấu hình này, **source tường minh** chính là nguồn CORS được gắn vào Spring Security. Không nên bổ sung một cấu hình global MVC có chính sách khác nếu không hiểu rõ cơ chế phối hợp, vì nhóm phát triển có thể tưởng cả hai cùng “quyết định” origin được phép.

Các nguyên tắc:

- `registerCorsConfiguration("/api/**", api)` so khớp **URL path của API**.
- `api.setAllowedOrigins(...)` so khớp **origin của frontend**.
- `http.cors(...)` tích hợp xử lý CORS trong security chain.
- `CorsConfigurationSource` **không thực thi authentication**; actual request vẫn qua các rule Security.
- Các policy origin khác nhau cho `/api/**` và `/admin/**` phải được thử riêng.

### 6.1. Vì sao không luôn cần một bean CorsFilter?

Nếu Spring Security đã gắn bộ xử lý CORS vào security chain từ `http.cors(...)` và `CorsConfigurationSource`, việc tự khai báo thêm `@Bean CorsFilter` có thể dẫn đến một filter được servlet container đăng ký độc lập, hoặc được thành phần Security nhận diện theo cơ chế cấu hình, làm luồng khó theo dõi.

Không nên tạo hai bộ xử lý cho cùng path mà không xác định rõ **thứ tự và nguồn policy**. Trong một hệ thống thông thường, hãy chọn một phương thức tích hợp nhất quán:

- **MVC CORS + `http.cors(...)`** khi chính sách được quản lý bởi MVC.
- **`CorsConfigurationSource` tường minh + `http.cors(...)`** khi muốn quản lý chính sách trong Security.
- **CorsFilter Servlet đăng ký độc lập** khi có nhu cầu xử lý CORS ở filter toàn ứng dụng ngoài cách tích hợp trên và kiểm soát được thứ tự.

## 7. Khi nào đăng ký CorsFilter Servlet độc lập?

`CorsFilter` độc lập có ích khi ứng dụng cần CORS **trước toàn bộ logic xử lý Servlet** hoặc không dùng cấu hình MVC làm nguồn xử lý. Trong Spring Boot, nếu chọn cách này, cần hiểu rõ thứ tự đăng ký servlet filter so với Spring Security và các filter khác.

Ví dụ minh họa **một lựa chọn thay thế** cho tích hợp `http.cors(...)` (không sử dụng đồng thời cùng một chính sách CORS ở cả hai nơi):

~~~java
import java.util.List;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

@Configuration
class EarlyCorsFilterConfiguration {

    @Bean
    FilterRegistrationBean<CorsFilter> corsFilterRegistration() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type"
        ));

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);

        FilterRegistrationBean<CorsFilter> registration =
            new FilterRegistrationBean<>(new CorsFilter(source));
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }
}
~~~

Đây là mã minh họa kỹ thuật đăng ký một Servlet Filter trước các filter có thứ tự cao hơn về mặt số học. Cần kiểm tra thứ tự thực tế trong ứng dụng, nơi cấu hình Spring Security cũng có thể có registration khác và proxy/filter ngoài ứng dụng. Không sao chép máy móc `Ordered.HIGHEST_PRECEDENCE` cho mọi filter vì nó có thể thay đổi tương tác với thành phần khác.

**Không đăng ký một filter CORS độc lập chỉ để khắc phục lỗi mà chưa xác định tầng đang xử lý CORS.** Nếu security chain đã dùng `http.cors(...)` và MVC cũng đang bật CORS, cần xem xét việc hợp nhất thay vì chồng thêm lớp mới.

Ngoài ra, đoạn ví dụ này chưa thiết lập cookie-session credentials. Nếu request cần `credentials: "include"`, phải dùng origin cụ thể và `cors.setAllowCredentials(true)`, cùng chính sách cookie, session và CSRF thích hợp.

## 8. Xung đột giữa Spring MVC và Spring Security

### 8.1. Một controller có @CrossOrigin nhưng preflight vẫn trả 401

Tình huống:

~~~java
@RestController
@RequestMapping("/api/orders")
@CrossOrigin(origins = "https://app.example.com")
class OrderController {
    // ...
}
~~~

Một request `OPTIONS` với `Origin` hợp lệ bị trả `401 Unauthorized` trước khi đến controller. Nguyên nhân đáng kiểm tra là filter Security đã yêu cầu authentication trước khi CORS được xử lý. Điều này xảy ra dù annotation ở controller có vẻ đúng.

Hướng xử lý: bật tích hợp `http.cors(Customizer.withDefaults())`, để Spring Security dùng cấu hình MVC khi đủ điều kiện, hoặc chỉ định một `CorsConfigurationSource` tương ứng. Sau đó kiểm tra OPTIONS có được trả quyền CORS trước authentication và actual request vẫn được bảo vệ.

### 8.2. Có MVC CORS global nhưng security chain đang dùng source khác

Nếu một bean `CorsConfigurationSource` tường minh xuất hiện, bộ xử lý CORS của Spring Security có thể sử dụng bean đó thay cho policy MVC. Khi các cấu hình khác nhau, frontend có thể nhận response không đúng điều người viết `WebMvcConfigurer` dự đoán.

Để chẩn đoán:

1. Xác định request đi qua security chain nào.
2. Xem chain đó dùng `http.cors(...)` theo mặc định hay `configurationSource(...)` tường minh.
3. Xem có bean `CorsFilter` hoặc servlet filter CORS đăng ký độc lập không.
4. Kiểm tra MVC `@CrossOrigin` / `addCorsMappings` và gateway có chèn thêm header không.
5. Đối chiếu **actual response cuối cùng** ở browser.

### 8.3. Policy global và @CrossOrigin kết hợp theo cách khó đoán

Khi MVC global cho `https://app.example.com`, một controller có annotation cho `https://preview.example.com`, hành vi gộp danh sách có thể mở thêm origin preview. Nếu preview chứa code chưa được tin cậy nhưng API trả dữ liệu phiên, đây là thay đổi quan trọng về quyền đọc response.

Hãy viết test với các origin được phép và không được phép, đặc biệt khi dùng `allowCredentials(true)`. Không dựa vào cảm giác “annotation ở method sẽ luôn ghi đè global” để đánh giá phạm vi tin cậy.

### 8.4. Có nhiều SecurityFilterChain

Một ứng dụng có thể dùng chain riêng cho `/api/**` và `/admin/**`:

~~~java
@Bean
@org.springframework.core.annotation.Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/admin/**")
        .cors(cors -> cors.configurationSource(adminCorsSource()))
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .build();
}
~~~

Đây là đoạn minh họa ý tưởng, cần có source, chain khác và authentication của ứng dụng thực. Điều then chốt: **SecurityFilterChain khớp request phải có tích hợp CORS phù hợp**. Một chain khác bật `cors()` không bảo đảm chain đang nhận OPTIONS cũng áp dụng policy ấy.

Nếu nhiều `CorsConfigurationSource` beans tồn tại, cấu hình tường minh cho từng chain giúp giảm mơ hồ. Đừng tự suy ra Spring sẽ chọn đúng nguồn chỉ dựa vào tên bean.

### 8.5. Gateway, proxy, CDN và duplicate headers

Một proxy có thể tự trả OPTIONS hoặc thêm `Access-Control-Allow-Origin` vào response. Nếu Spring Security và gateway cùng xử lý CORS với chính sách khác nhau, browser có thể thấy:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Origin: https://admin.example.com
~~~

Hoặc giá trị bị ghép thành danh sách. Đó không phải response `Access-Control-Allow-Origin` hợp lệ để cấp quyền cho nhiều origin. Cần quy định rõ tầng nào chịu trách nhiệm CORS và kiểm tra output cuối cùng từ bên ngoài.

Tương tự, gateway có thể rewrite `/backend/api/orders` thành `/api/orders` hoặc ngược lại. `CorsConfigurationSource` dựa trên path mà ứng dụng thực sự nhận, nên phải kiểm tra routing sau rewrite.

## 9. Đối chiếu với Reactive / Spring WebFlux

`org.springframework.web.filter.CorsFilter` là **Servlet Filter**. Không dùng trực tiếp filter này trong `SecurityWebFilterChain` của WebFlux.

Bên Reactive, các thành phần tương đương là:

- `org.springframework.web.cors.reactive.CorsWebFilter`.
- `org.springframework.web.cors.reactive.CorsConfigurationSource`.
- `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`.
- Cấu hình CORS ở WebFlux handler, chẳng hạn `WebFluxConfigurer#addCorsMappings`.
- Tích hợp với `ServerHttpSecurity.cors(...)` trong Spring Security WebFlux.

Ví dụ tập trung vào tích hợp CORS trực tiếp trong security chain Reactive:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "X-CSRF-TOKEN"
        ));
        cors.setAllowCredentials(true);

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

Nếu dùng `CorsWebFilter` riêng, cần đảm bảo thứ tự xử lý đúng so với bảo mật reactive, và tránh các thành phần CORS khác cùng xử lý request khiến header bị sửa. WebFlux cũng có annotation `@CrossOrigin`, nhưng nguồn/kiểu filter là reactive.

Trong cả hai stack, preflight thường thiếu thông tin xác thực của actual request. CORS cần được xử lý trước bước authentication chặn OPTIONS; actual request tiếp tục qua authentication, authorization và CSRF khi cần.

## 10. Kiểm thử tích hợp Servlet bằng MockMvc

Với ứng dụng Spring Boot sử dụng `WebMvcConfigurer` ở mục 4 và `http.cors(...)` ở mục 5, một bài test tích hợp kiểm tra CORS được xử lý trước authentication.

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
class MvcCorsAndSecurityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void preflightSucceedsWithoutSessionCookie() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "POST")
                .header("Access-Control-Request-Headers",
                    "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "Access-Control-Allow-Origin", "https://app.example.com"))
            .andExpect(header().string(
                "Access-Control-Allow-Credentials", "true"));
    }

    @Test
    void preflightRejectsUntrustedOrigin() throws Exception {
        mvc.perform(options("/api/orders")
                .header("Origin", "https://evil.example.org")
                .header("Access-Control-Request-Method", "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiOriginCannotUseAdminPolicy() throws Exception {
        mvc.perform(options("/admin/reports")
                .header("Origin", "https://app.example.com")
                .header("Access-Control-Request-Method", "POST"))
            .andExpect(status().isForbidden());
    }
}
~~~

Đây là ví dụ kiểm thử **chưa chạy trên một dự án Spring cụ thể**. Nó giả định có đủ dependency test, cấu hình Spring Security/MVC, đường dẫn tương ứng và dùng CORS processor mặc định. Nếu một request không đạt có biểu hiện khác do filter/gateway tùy biến, cần điều chỉnh assertion để kiểm tra kết quả bảo mật thực sự.

Khi triển khai, nên bổ sung kiểm thử **actual response** của endpoint phù hợp: một response 401/403 do authentication hoặc CSRF vẫn phải có CORS headers nếu muốn frontend được đọc status. Kiểm tra riêng rằng request thực sự bị từ chối về quyền dù origin được cấp CORS.

Ở WebFlux, dùng `WebTestClient` gửi OPTIONS với cùng các header, rồi xác minh response của `SecurityWebFilterChain`.

## 11. Chẩn đoán trong DevTools và curl

### 11.1. Thử preflight bằng curl

Với các hostname ví dụ, mô phỏng preflight:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Nếu ứng dụng cấu hình đúng, response thường có `Access-Control-Allow-Origin`, `Allow-Methods`, `Allow-Headers` và `Allow-Credentials` phù hợp.

Thử origin lạ:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://evil.example.org" \
  -H "Access-Control-Request-Method: POST"
~~~

Sau đó thử đúng origin nhưng sai method:

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: DELETE"
~~~

`curl` giúp thấy response HTTP, **không áp dụng CORS/SOP như browser**. Do đó vẫn phải thử bằng `fetch` từ đúng frontend origin. Trên PowerShell cũ, có thể dùng `curl.exe` để tránh bí danh `curl` của `Invoke-WebRequest`.

### 11.2. Ma trận chẩn đoán

| Triệu chứng | Nguyên nhân cần xác minh | Bước kiểm tra |
| --- | --- | --- |
| `OPTIONS` trả 401 trước controller | CORS chưa chạy trước authentication | Kiểm tra `http.cors(...)` và chain khớp request |
| `OPTIONS` trả 403 dù origin hợp lệ | Method/header chưa được phép, path mismatch hoặc policy khác | So preflight request và CORS response |
| Có `@CrossOrigin` nhưng browser vẫn báo CORS | Security chặn trước MVC hoặc chưa tích hợp policy MVC | Kiểm tra Security CORS integration và filter ordering |
| Thay MVC `addCorsMappings` không có hiệu lực | Security đang dùng `CorsConfigurationSource` riêng | Xem bean/source/chain thực tế |
| Response có hai giá trị `Allow-Origin` | Nhiều filter, MVC hoặc gateway cùng chèn | Đối chiếu response ở từng tầng |
| Chỉ route admin lỗi | Chính sách `/admin/**` không khớp hoặc origin không được phép | Kiểm tra path và policy riêng |
| Chỉ POST JSON lỗi, GET được | Preflight thiếu `Allow-Headers` hoặc `Allow-Methods` | Kiểm tra OPTIONS request/response |
| PUT/POST actual nhận 403 | CSRF token sai, thiếu quyền hoặc authentication | Kiểm tra server log và actual response |
| Cookie không được gửi | Fetch credentials mode, SameSite/Secure/Domain/Path hoặc chính sách cookie | Kiểm tra Request Headers, tab Cookies |
| Spring đúng nhưng proxy lỗi | Proxy chặn OPTIONS, rewrite path hoặc sửa CORS headers | So kết quả trước và sau gateway |
| CORS thất bại không liên tục | Cache thiếu `Vary: Origin`, preflight cache, nhiều backend policy khác nhau | Kiểm tra cache, response và cấu hình các instance |

### 11.3. Quy trình quan sát thực tế

1. Mở DevTools → Network, tìm OPTIONS và actual request liên quan.
2. Ghi lại origin của frontend, path backend, HTTP method và request headers.
3. Xem `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` ở preflight.
4. Đối chiếu CORS response headers với chính sách MVC hoặc `CorsConfigurationSource` mà security chain thực dùng.
5. Kiểm tra actual request có được gửi không; nếu có, xem authentication, CSRF và response headers của nó.
6. Kiểm tra tầng gateway, filter registration và việc chèn header trùng.
7. Nếu dùng cookie, xem `credentials` và chính sách cookie riêng; đừng chỉ nhìn `Access-Control-Allow-Credentials`.

Không dùng `fetch(..., { mode: "no-cors" })` để né lỗi; response opaque không cho JavaScript đọc JSON như nhu cầu của ứng dụng.

## 12. Bảo vệ HTTP không dừng ở CorsFilter

CORS là một phần trong nhiều lớp bảo vệ:

| Lớp | Vai trò |
| --- | --- |
| CorsFilter / MVC CORS | Xét quyền browser được đọc cross-origin response và preflight |
| Authentication | Kiểm tra user/client là ai |
| Authorization | Kiểm tra quyền truy cập endpoint, thao tác và dữ liệu |
| CSRF protection | Chặn thao tác thay đổi trạng thái trái ý muốn trong mô hình xác thực dễ bị CSRF |
| Session/cookie security | Kiểm soát phiên, cookie `HttpOnly`/`Secure`/`SameSite` và vòng đời session |
| CSP | Hạn chế nguồn tài nguyên và nơi script được kết nối, chẳng hạn `connect-src` |
| HSTS/TLS | Bảo vệ kết nối HTTPS, giảm khả năng downgrade |
| HTTP firewall | Xử lý những dạng request HTTP bất thường/nguy hiểm trước bước authorization |

Ví dụ một request `POST` có thể không cần preflight khi dùng form content type safelisted, dù vẫn được gửi cross-site. Việc JavaScript trên trang lạ không đọc được response **không ngăn backend đã thực hiện thay đổi**. Ứng dụng xác thực bằng cookie vẫn cần thiết kế CSRF protection đúng.

Cấu hình allowlist CORS quá rộng với `allowCredentials(true)` có thể khiến JavaScript từ trang không tin cậy đọc dữ liệu của user đã đăng nhập khi cookie được gửi. Vì vậy không bật `Access-Control-Allow-Origin: *` hoặc phản chiếu mọi `Origin` để “sửa nhanh” lỗi frontend.

## 13. Checklist triển khai

- [ ] Xác định rõ dùng **MVC CORS + Security integration** hay **source CORS tường minh + Security integration**; hiểu chính xác filter nào xử lý.
- [ ] Chỉ đăng ký `CorsFilter` độc lập khi có yêu cầu rõ ràng và kiểm soát thứ tự filter.
- [ ] Xác nhận mỗi `SecurityFilterChain` liên quan đã có CORS policy phù hợp; không mặc định các chain chia sẻ cùng cấu hình.
- [ ] Không nhầm pattern `/api/**` với origin pattern của frontend.
- [ ] Có allowlist origin cụ thể, method và request headers thật sự cần; cân nhắc credentials theo mô hình ứng dụng.
- [ ] Preflight `OPTIONS` hợp lệ đi qua trước authentication và được trả CORS headers đúng.
- [ ] Actual request vẫn chịu authentication, authorization, CSRF và kiểm tra session.
- [ ] Đã kiểm tra ảnh hưởng của `@CrossOrigin` với cấu hình MVC global, nhất là khi combine origin lists.
- [ ] Không có CORS response headers bị trùng hoặc mâu thuẫn ở MVC, Security và gateway.
- [ ] Có kiểm thử origin hợp lệ, origin lạ, sai method, sai header, sai path và response lỗi của actual request.
- [ ] Kiểm tra riêng chính sách cookie và frontend `credentials` khi dùng session.
- [ ] Với WebFlux, dùng thành phần reactive phù hợp; không dùng Servlet `CorsFilter` trong security chain reactive.

## 14. Câu hỏi tự kiểm tra

**Tình huống 1.** Controller có `@CrossOrigin(origins = "https://app.example.com")` nhưng `OPTIONS /api/orders` nhận 401 trước khi đến controller. Có phải annotation sai cú pháp?

**Trả lời:** Chưa chắc. Khả năng phổ biến là Security xử lý authentication trước preflight. Cần bật `http.cors(...)` và tích hợp đúng policy MVC hoặc source riêng để xử lý OPTIONS trước authentication.

**Tình huống 2.** Dự án đã dùng Spring MVC `WebMvcConfigurer#addCorsMappings`. Nếu Spring Security cấu hình `http.cors(Customizer.withDefaults())` và không có `CorsConfigurationSource` riêng, Spring Security có thể dùng policy MVC không?

**Trả lời:** Có, khi Spring MVC hiện diện và các điều kiện tích hợp tương ứng được đáp ứng. Nên xác nhận qua bài test OPTIONS từ frontend được phép và từ origin lạ.

**Tình huống 3.** Nhóm phát triển thêm `@Bean CorsFilter` trong khi security chain đã bật `http.cors(...)`, sau đó thấy các CORS headers mâu thuẫn. Cách xử lý?

**Trả lời:** Kiểm kê các nơi đang xử lý CORS, chọn cách tích hợp rõ ràng với một policy nhất quán, bỏ phần đăng ký trùng không cần thiết và xác minh thứ tự filter. Chỉ sửa header ở controller thường không giải quyết nguyên nhân.

**Tình huống 4.** `@CrossOrigin` trên method bổ sung origin preview trong khi global MVC đã cho app production. Có chắc nó thu hẹp quyền CORS về preview không?

**Trả lời:** Không. Cấu hình cục bộ và global có thể được kết hợp; các thuộc tính dạng danh sách có thể hợp nhất. Cần test allowlist hiệu lực cho từng endpoint.

**Tình huống 5.** Một preflight được phép nhưng actual `POST` trả 403 vì sai CSRF token. Việc chỉnh `allowedMethods` có khắc phục lỗi không?

**Trả lời:** Không. Preflight đã đạt. CSRF là kiểm tra riêng trên actual request, cần gửi token hợp lệ và cấu hình CSRF theo mô hình phiên đăng nhập.

**Tình huống 6.** Có hai `SecurityFilterChain` cho `/api/**` và `/admin/**`. CORS hoạt động với API nhưng OPTIONS của admin bị 401. Cần xem gì?

**Trả lời:** Xem chain nào nhận OPTIONS admin, chain đó có bật CORS và gắn đúng source không, cùng với route/proxy. CORS được bật ở chain API không đảm bảo chain admin tự có.

**Tình huống 7.** Chuyển sang WebFlux nhưng tiếp tục tạo `org.springframework.web.filter.CorsFilter` như Servlet. Cách này phù hợp không?

**Trả lời:** Không. WebFlux dùng `CorsWebFilter`, nguồn CORS reactive hoặc tích hợp `ServerHttpSecurity.cors(...)`; phải áp dụng các class đúng stack Reactive.

**Tình huống 8.** Một API chỉ có `CorsFilter` nhưng không kiểm tra quyền ở controller. Có thể coi API đã được bảo vệ khỏi client giả mạo không?

**Trả lời:** Không. CORS hạn chế việc trình duyệt chia sẻ response cho JavaScript ở origin khác. Client ngoài trình duyệt vẫn có thể gửi HTTP request trực tiếp, nên server luôn phải thực hiện authentication, authorization và kiểm soát dữ liệu.

---

**Ghi nhớ:** `CorsFilter` là lớp xử lý CORS trong **Servlet Filter chain**, còn `@CrossOrigin` và `WebMvcConfigurer` là những cách Spring MVC **khai báo chính sách**. `HttpSecurity.cors(...)` giúp Spring Security xử lý preflight sớm, có thể tích hợp chính sách MVC hoặc dùng `CorsConfigurationSource` tường minh. Chọn một cách cấu hình nhất quán, kiểm soát filter ordering và tiếp tục giữ authentication, authorization, CSRF và bảo vệ session cho actual request; với Reactive phải dùng các thành phần CORS của WebFlux.
