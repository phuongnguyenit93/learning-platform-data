# Tích hợp CORS với `CorsConfigurationSource` trong Spring Security Servlet

> **Phạm vi:** Spring Security 6.x trên Servlet/Spring MVC (thường đi cùng Spring Boot 3.x), Java 17+. Bài học giải thích việc cấp chính sách CORS bằng `CorsConfigurationSource`, nối nó vào `SecurityFilterChain`, kiểm thử preflight và phân biệt lỗi CORS với xác thực, cookie và CSRF. Spring WebFlux có cơ chế reactive riêng.

## 1. Bài toán: frontend và API ở hai origin

Giả sử frontend tại `http://localhost:5173` gọi backend tại `http://localhost:8080`. Đó là hai **origin khác nhau** dù cùng máy tính: origin gồm **scheme + hostname + port**. `https://app.example.com` và `https://api.example.com` cũng khác origin; path không thuộc origin.

~~~javascript
const response = await fetch("http://localhost:8080/api/hello", {
  credentials: "include"
});
console.log(response.status);
~~~

Browser áp dụng **Cross-Origin Resource Sharing (CORS)** khi JavaScript của origin này muốn đọc response từ origin khác. Server cần công bố origin, HTTP method và request headers nào được phép. Nếu dùng cookie/session, server còn phải cho phép credentialed CORS response.

Trong ứng dụng có Spring Security, thách thức điển hình là request **preflight OPTIONS** của trình duyệt thường không mang cookie đăng nhập. Nếu authentication/authorization chạy trước CORS processing, preflight có thể bị từ chối, dù người dùng đã đăng nhập trong tab frontend.

`CorsConfigurationSource` cung cấp chính sách CORS cho request và là một điểm nối chuẩn với Spring Security Servlet. Sau bài học, cần trả lời được: “request này lấy policy từ đâu?”, “filter nào xử lý OPTIONS?”, “tại sao OPTIONS qua nhưng POST vẫn 403?”, và “kiểm thử policy theo origin, method, header như thế nào?”.

## 2. Trước hết hiểu request CORS và preflight

### 2.1. Cross-origin request thông thường

Một request GET có thể được gửi kèm `Origin`:

~~~http
GET /api/hello HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
~~~

Nếu policy chấp nhận origin này, response có thể có:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json
~~~

Tên/thứ tự header thực tế có thể khác. Với `credentials: "include"`, response cần cơ chế CORS cho credentials phù hợp. Nếu server không gửi `Access-Control-Allow-Origin` hợp lệ, browser có thể nhận response trên mạng nhưng **chặn JavaScript đọc response**. Vì vậy thông báo lỗi CORS ở browser không tự chứng minh rằng HTTP request chưa đến server.

### 2.2. Preflight OPTIONS

Một request `POST` dùng `Content-Type: application/json` hoặc custom header như `X-CSRF-TOKEN` thường làm browser gửi preflight trước:

~~~http
OPTIONS /api/items HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Browser đang hỏi: “Origin này có được gọi `POST /api/items` với các request headers đó không?” Preflight **chưa phải** request nghiệp vụ `POST`, và bình thường không gửi session cookie. Một response hợp lệ có thể như sau:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,PUT,PATCH,DELETE
Access-Control-Allow-Headers: content-type,x-csrf-token
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
~~~

Nếu được chấp nhận, browser mới gửi request thật; response của request thật cũng phải có CORS headers phù hợp để JavaScript đọc. Browser có thể cache kết quả preflight, nhưng thời gian cache còn chịu giới hạn của browser.

Không phải mọi POST đều preflight; nó phụ thuộc phương thức, content type và headers theo quy tắc CORS của browser. Ngược lại, dù không có preflight, server vẫn cần CORS headers phù hợp trong response của request cross-origin.

### 2.3. CORS làm gì và không làm gì?

CORS là chính sách browser áp dụng cho **đọc response cross-origin** và cho một số request cross-origin phức tạp. Nó **không phải** một lớp authentication hoặc authorization. `curl`, Postman hay dịch vụ server-to-server không thực thi Same-Origin Policy như browser. Kể cả khi origin được cho phép, backend vẫn cần kiểm tra người dùng, quyền truy cập, CSRF nếu có cookie xác thực, validation và nghiệp vụ.

## 3. Các thành phần và trách nhiệm trong Servlet stack

| Thành phần | Trách nhiệm | Điểm dễ nhầm |
| --- | --- | --- |
| `CorsConfiguration` | Dữ liệu chính sách: origin, method, headers, credentials, exposed headers, max age. | Không tự bắt request hoặc thêm response headers. |
| `CorsConfigurationSource` | Chọn `CorsConfiguration` phù hợp cho HTTP request hiện tại. | Có thể trả `null` nếu request không có policy. |
| `UrlBasedCorsConfigurationSource` | Implementation ánh xạ URL pattern như `/api/**` sang policy. | Dùng được ngay, không cần viết custom source cho path thông thường. |
| `CorsFilter`/`CorsProcessor` | Xử lý `Origin` và preflight headers, kiểm tra policy, phát sinh response CORS headers. | Phải được đặt phù hợp trước các filter đòi xác thực trên preflight. |
| `HttpSecurity.cors(…)` | Nối CORS processing vào Spring Security Servlet filter chain. | Cần đúng chain nhận path; không chỉ là thiết lập ở controller. |

Interface về cơ bản có phương thức:

~~~java
CorsConfiguration getCorsConfiguration(HttpServletRequest request);
~~~

Đây là chữ ký API để hiểu hợp đồng, chưa phải một file Java có thể chạy độc lập. `UrlBasedCorsConfigurationSource` triển khai hợp đồng đó bằng cách tra cứu path đã đăng ký. Khi cần policy khác nhau giữa API public/admin, có thể đăng ký nhiều path với policy riêng.

~~~text
Browser
  |
  +-- OPTIONS /api/items, Origin + Access-Control-Request-*
  |      |
  |      v
  |   Spring Security: CORS processing
  |      |
  |      +--> CorsConfigurationSource -> policy cho /api/**
  |      +--> CorsProcessor kiểm tra Origin/Method/Headers
  |      +--> được phép: trả preflight response
  |      +--> bị từ chối: không cấp CORS approval
  |
  +-- POST /api/items thật
         |
         v
       CORS processing -> authentication -> CSRF -> authorization
         |
         v
       controller khi mọi điều kiện cần thiết hợp lệ
         |
         v
       response có CORS headers nếu origin được phép
~~~

Thứ tự khái niệm trên để giải thích; vị trí chính xác giữa các security filters do Spring Security xây dựng. Điều cần bảo đảm là CORS xử lý preflight **trước khi authentication chặn nó**.

## 4. Ví dụ thực tế: đăng ký `CorsConfigurationSource` theo path

Ứng dụng minh họa dùng Spring Boot 3.x, Java 17+, `spring-boot-starter-web` và `spring-boot-starter-security`. Frontend dev tại `http://localhost:5173`, frontend production tại `https://app.example.com`. API nằm dưới `/api/**`, authentication qua session/form login, CSRF giữ mặc định.

Mã dưới đây là các file Java đầy đủ **khi đặt trong một dự án Spring Boot có dependencies đã nêu**; chạy bằng Gradle/Maven của dự án, không chạy độc lập bằng `javac` không có Spring classpath. Mọi class nằm trong package `com.example.corsdemo`.

**`src/main/java/com/example/corsdemo/CorsDemoApplication.java`:**

~~~java
package com.example.corsdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/corsdemo/SecurityConfig.java`:**

~~~java
package com.example.corsdemo;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration policy = new CorsConfiguration();

        // Origin là scheme + host + port, không gồm path.
        policy.setAllowedOrigins(List.of(
            "http://localhost:5173",
            "https://app.example.com"
        ));

        // Method của request thật được phép trong CORS.
        policy.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE"
        ));

        // Các request headers frontend cần gửi.
        policy.setAllowedHeaders(List.of(
            "Content-Type",
            "Authorization",
            "X-CSRF-TOKEN",
            "X-XSRF-TOKEN"
        ));

        // Cho phép frontend đọc thêm response header Location.
        policy.setExposedHeaders(List.of("Location"));

        // Dành cho luồng dùng session cookie cross-origin.
        policy.setAllowCredentials(true);

        // Thời gian browser có thể cache preflight, tính bằng giây.
        policy.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        // Chỉ áp dụng policy này cho /api/**.
        source.registerCorsConfiguration("/api/**", policy);

        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) throws Exception {

        return http
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Dòng quan trọng nhất là:

~~~java
.cors(cors -> cors.configurationSource(corsSource))
~~~

Nó nối policy source **cụ thể** vào Spring Security chain đang xây dựng. Với request `/api/items`, source tìm policy của `/api/**`. CORS processor quyết định có chấp nhận `Origin`, method, headers và credentials không trước khi request thật đến các tầng còn lại.

**`src/main/java/com/example/corsdemo/ApiController.java`:**

~~~java
package com.example.corsdemo;

import java.net.URI;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Xin chao");
    }

    @PostMapping("/items")
    public ResponseEntity<Map<String, String>> create(
            @RequestBody Map<String, String> input) {
        String name = input.getOrDefault("name", "item");
        return ResponseEntity
            .created(URI.create("/api/items/1"))
            .body(Map.of("id", "1", "name", name));
    }
}
~~~

Nếu authenticated GET được chấp nhận, JSON mẫu là:

~~~json
{"message":"Xin chao"}
~~~

Nếu authenticated POST có CSRF token hợp lệ với JSON `{"name":"Sach"}`, controller trả 201, `Location: /api/items/1` và JSON:

~~~json
{"id":"1","name":"Sach"}
~~~

Controller chỉ minh họa: id `1` cố định, chưa lưu vào database và chưa kiểm tra input nghiệp vụ. CORS không tự bảo đảm dữ liệu được lưu.

### Giải thích chi tiết từng policy

**`setAllowedOrigins(List.of(…))`:** allowlist origin cụ thể. Origin là `http://localhost:5173`, không phải `http://localhost:5173/home`. Scheme, host, port phải đúng; không dùng domain “gần giống”. Origin `null` từ môi trường đặc biệt cũng không nên được cho phép tùy tiện.

**`setAllowedMethods(…)`:** các method của request thật mà browser được phép gọi. Preflight tự gửi bằng `OPTIONS` để hỏi về `POST`/`PUT`/…; **không bắt buộc** thêm `OPTIONS` vào danh sách method chỉ vì browser dùng preflight. Nếu ứng dụng thực sự gọi OPTIONS như nghiệp vụ thì đánh giá riêng.

**`setAllowedHeaders(…)`:** cho phép các tên request headers được browser nêu trong `Access-Control-Request-Headers`. Nó không xác thực giá trị `Authorization` hoặc CSRF token. Nếu frontend dùng `X-Request-ID`, phải bổ sung có chủ đích vào danh sách.

**`setExposedHeaders(…)`:** thêm các response headers mà JavaScript được đọc, ví dụ `Location`. Đây là chiều **response**, khác hẳn `allowedHeaders` của chiều request.

**`setAllowCredentials(true)`:** cho phép credentialed CORS response khi browser muốn gửi cookie/credentials. Client còn phải thiết lập `credentials: "include"`, và cookie vẫn chịu `SameSite`, `Secure`, domain/path, chính sách third-party cookies. Không bật true nếu luồng không cần credentials.

**`setMaxAge(3600L)`:** thời gian cache preflight gợi ý cho browser, đơn vị giây. Không cache quyền truy cập người dùng; browser có thể áp giới hạn riêng.

**`registerCorsConfiguration("/api/**", policy)`:** gắn policy theo path. Những endpoint nằm ngoài `/api/**` (chẳng hạn một endpoint login nếu đặt ở `/login`) không tự nhận policy này; phải thiết kế đường đi frontend thực sự sử dụng.

### Wildcard và credentials

Tránh tổ hợp:

~~~java
// Ví dụ KHÔNG hợp lệ/không nên dùng cho credentials:
policy.setAllowedOrigins(List.of("*"));
policy.setAllowCredentials(true);
~~~

Khi credentials được bật, browser không chấp nhận `Access-Control-Allow-Origin: *` làm CORS approval hợp lệ. Spring có kiểm tra tổ hợp cấu hình này. Dùng allowlist origin cụ thể. `setAllowedOriginPatterns(…)` hỗ trợ pattern và có thể phản hồi origin đã khớp, nhưng pattern phải hẹp và thật sự đáng tin; wildcard quá rộng có thể cho nhiều origin không mong muốn đọc dữ liệu người dùng.

## 5. Khi nào Spring Security tự nhận `CorsConfigurationSource`?

Có ba cách triển khai thường thấy.

### 5.1. Truyền source tường minh

Trong ví dụ mục 4, bean `UrlBasedCorsConfigurationSource` được inject vào `SecurityFilterChain` và truyền trực tiếp cho `.cors(…)`. Cách này khiến code rõ ràng về chính sách nào phục vụ chain nào, hữu ích khi ứng dụng phức tạp hoặc có nhiều source.

### 5.2. Dùng cấu hình mặc định khi có bean thích hợp

Khi có `UrlBasedCorsConfigurationSource` bean thích hợp, Spring Security có thể tích hợp nó qua:

~~~java
.cors(Customizer.withDefaults())
~~~

Điểm quan trọng: nếu có **nhiều `CorsConfigurationSource` bean**, Spring Security không thể tự xác định rõ nên dùng bean nào. Khi đó hãy cấu hình nguồn CORS cho từng chain bằng `cors.configurationSource(…)` thay vì hy vọng framework đoán đúng.

### 5.3. Tích hợp Spring MVC CORS

Nếu ứng dụng sử dụng Spring MVC và không có `CorsConfigurationSource` riêng, Spring Security có thể sử dụng policy CORS của MVC khi bật `.cors(Customizer.withDefaults())`. Cấu hình MVC có thể đến từ `WebMvcConfigurer` hoặc `@CrossOrigin` ở controller.

Tuy nhiên, `@CrossOrigin` ở controller không tự sửa được mọi trường hợp preflight bị security filter chặn. Tránh duy trì allowlist khác nhau ở controller, MVC global config, Security source và gateway mà không biết chính sách nào thực sự áp dụng. Hãy chọn đường tích hợp rõ ràng và kiểm thử path thật.

## 6. Nhiều `SecurityFilterChain` và chính sách theo đường dẫn

Nếu ứng dụng có các filter chain khác nhau, chain đầu tiên khớp request quyết định cấu hình Spring Security được áp dụng. Ví dụ API `/api/**` và trang web `/**` có thể dùng cơ chế xác thực khác nhau. CORS cần được cài trong **chain nhận OPTIONS và request thật**.

Đoạn sau chỉ minh họa một bean bổ sung trong cấu hình **thay thế**, không được đặt thêm cạnh `SecurityFilterChain` bao trùm mọi request ở mục 4 nếu chưa tổ chức lại matcher và thứ tự chain:

~~~java
@Bean
@org.springframework.core.annotation.Order(1)
SecurityFilterChain apiChain(
        HttpSecurity http,
        org.springframework.web.cors.CorsConfigurationSource source)
        throws Exception {

    return http
        .securityMatcher("/api/**")
        .cors(cors -> cors.configurationSource(source))
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(
            org.springframework.security.config.Customizer.withDefaults())
        .build();
}
~~~

Đoạn này minh họa cách gắn source vào **đúng chain**, không định nghĩa đầy đủ các bean bổ sung hoặc quyết định nên dùng HTTP Basic trong production. Nếu có thêm chain cho các path khác, cấu hình security/CORS tương ứng phải được kiểm tra riêng.

Với policy khác nhau theo path, `UrlBasedCorsConfigurationSource` có thể đăng ký nhiều cấu hình:

~~~java
// Fragment bên trong phương thức tạo source.
// publicPolicy/privatePolicy là hai CorsConfiguration đã khai báo.
source.registerCorsConfiguration("/api/public/**", publicPolicy);
source.registerCorsConfiguration("/api/admin/**", privatePolicy);
~~~

Đây là fragment minh họa API, chưa phải một class runnable độc lập. Kể cả frontend origin được CORS cho phép gọi `/api/admin/**`, user vẫn phải được **authorization** cấp quyền admin.

## 7. CORS và các tầng bảo mật khác: đừng nhầm cùng một HTTP 403

| Tầng | Trả lời câu hỏi | Cách phát hiện điển hình |
| --- | --- | --- |
| CORS | Origin này có được đọc response và gửi method/header này trong browser? | Preflight 403 hoặc response thiếu `Access-Control-Allow-Origin`. |
| Authentication | Request thuộc người dùng nào? | 401 hoặc redirect login khi không có phiên hợp lệ. |
| Authorization | Người dùng đã đăng nhập có đủ quyền gọi endpoint? | 403 sau kiểm tra role/permission. |
| Session/cookie | Browser có thật sự gửi cookie tới API? | `SameSite`/`Secure`/domain/path/third-party cookie policy khiến cookie vắng mặt. |
| CSRF | Request thay đổi dữ liệu có token CSRF hợp lệ? | POST/PUT/PATCH/DELETE có thể nhận 403 dù preflight đã qua. |

### 7.1. Preflight thành công nhưng POST thất bại là hoàn toàn có thể

Ví dụ:

1. Browser gửi `OPTIONS /api/items` và CORS cho phép `POST`, `content-type`, `x-csrf-token`.
2. Browser gửi `POST /api/items`.
3. Cookie phiên không tới backend hoặc đã hết hạn → authentication fail.
4. Hoặc đã đăng nhập nhưng thiếu/sai CSRF token → `CsrfFilter` từ chối.
5. Hoặc token hợp lệ nhưng user thiếu quyền → authorization trả 403.

Trong cả ba trường hợp sau, việc tăng quyền CORS không giải quyết nguyên nhân. Cần đọc status/headers và exception từ tầng backend phù hợp.

### 7.2. Cross-origin khác cross-site

Khác cổng đồng nghĩa khác **origin** nhưng có thể vẫn cùng **site**. Cross-site cookies phải đáp ứng chính sách khắt khe hơn; `credentials: "include"` không ép browser bỏ qua `SameSite` hoặc chặn third-party cookies. Khi request thực sự cross-site cần cookie, thường phải thiết kế cookie `SameSite=None; Secure` và HTTPS phù hợp, đồng thời kiểm chứng browser thực tế. CORS source không tự đặt cookie session.

### 7.3. CSRF còn hiệu lực khi dùng session cookie

Nếu ứng dụng xác thực bằng cookie tự được browser gửi, việc bật CORS không bỏ nhu cầu CSRF protection. `setAllowedHeaders(List.of("X-CSRF-TOKEN", …))` chỉ cho phép **tên header** được gửi; frontend vẫn phải lấy token hợp lệ từ backend và gửi đúng giá trị. `csrf(Customizer.withDefaults())` trong mục 4 cố ý giữ bảo vệ CSRF. Với hệ thống dùng Bearer token gắn thủ công trong `Authorization` và không dựa vào browser-managed credentials, threat model có thể khác, nhưng quyết định về CSRF phải được đánh giá riêng.

### 7.4. Vì sao `requestMatchers(OPTIONS, "/**").permitAll()` chưa đủ?

Rule authorization có thể cho OPTIONS đi tiếp, nhưng nó **không tự tạo** `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` và `Access-Control-Allow-Headers`. Browser vẫn có thể chặn preflight vì thiếu header chính sách. Nên cấu hình CORS filter/source đúng trước authentication và chỉ thêm rule OPTIONS nếu thật sự có yêu cầu nghiệp vụ riêng.

## 8. Dùng browser DevTools và `curl` để kiểm tra

Trong DevTools → Network, lọc theo `OPTIONS` và endpoint:

1. Xác nhận request có `Origin` chính xác.
2. Đọc `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
3. Kiểm tra status của preflight và response headers `Access-Control-Allow-Origin`, `-Methods`, `-Headers`, `-Credentials`.
4. Xác định sau preflight có request thật không; nếu có, xem riêng response của request thật.
5. Kiểm tra cookie có được gửi, session/CSRF có hợp lệ, response có bị gateway/proxy sửa header không.

Để gửi preflight từ terminal Linux/macOS:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: http://localhost:5173" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Trên PowerShell, có thể dùng `curl.exe` một dòng:

~~~powershell
curl.exe -i -X OPTIONS "http://localhost:8080/api/items" -H "Origin: http://localhost:5173" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Với policy mục 4, phản hồi mong đợi là preflight thành công (thường HTTP 200), `Access-Control-Allow-Origin: http://localhost:5173`, phương thức POST được phép, và tên headers được chấp nhận. Thứ tự và dạng biểu diễn headers có thể khác giữa các server.

Thử origin không nằm trong allowlist:

~~~bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: https://untrusted.example" \
  -H "Access-Control-Request-Method: POST"
~~~

Với processor Spring mặc định thông dụng, preflight không hợp lệ thường bị trả 403. **Không suy ra** rằng non-browser clients không thể gọi API: `curl` chỉ kiểm tra server headers, không thực thi Same-Origin Policy của browser.

Đừng chỉ nhìn HTTP status. Một preflight 200 nhưng không có `Access-Control-Allow-Origin` phù hợp vẫn là thất bại đối với browser. Ngược lại, request thật 403 có thể do CSRF/auth chứ không còn là vấn đề policy CORS.

## 9. Kiểm thử tích hợp với MockMvc

Thêm test dependencies `spring-boot-starter-test` và `org.springframework.security:spring-security-test`. Đoạn test sau dùng project và controller ở mục 4, kiểm tra preflight được phép, origin trái phép, actual GET có CORS header và POST vẫn bảo vệ CSRF. Test dùng `MockMvc` nên không cần chạy browser, nhưng không thay thế kiểm tra cookie policy trên browser thật.

**`src/test/java/com/example/corsdemo/CorsIntegrationTest.java`:**

~~~java
package com.example.corsdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CorsIntegrationTest {

    private static final String FRONTEND = "http://localhost:5173";

    @Autowired
    MockMvc mvc;

    @Test
    void allowedPreflightWorksWithoutLogin() throws Exception {
        mvc.perform(options("/api/items")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-csrf-token"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS, "true"));
    }

    @Test
    void untrustedPreflightIsRejected() throws Exception {
        mvc.perform(options("/api/items")
                .header(HttpHeaders.ORIGIN, "https://untrusted.example")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void actualGetHasCorsHeader() throws Exception {
        mvc.perform(get("/api/hello")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND));
    }

    @Test
    void corsDoesNotDisableCsrf() throws Exception {
        mvc.perform(post("/api/items")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Sach\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/items")
                .header(HttpHeaders.ORIGIN, FRONTEND)
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Sach\"}"))
            .andExpect(status().isCreated())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND));
    }
}
~~~

Chạy qua wrapper của **dự án Spring Boot có đầy đủ dependencies**, ví dụ `./gradlew test` trên Linux/macOS hoặc `.\gradlew.bat test` trên Windows. Trong các bài kiểm thử, `.with(user("alice"))` tạo user giả lập cho Spring Security, còn `.with(csrf())` thêm token hợp lệ cho MockMvc. Nếu chỉ test preflight mà không test POST thật, bạn sẽ bỏ sót lỗi cookie, authentication hoặc CSRF. Nếu chỉ test POST mà bỏ preflight, browser có thể chặn trước khi request ấy tồn tại.

Điều cần quan sát là:

| Test | Kết quả mong muốn | Chứng minh |
| --- | --- | --- |
| OPTIONS từ allowlisted origin | Preflight 200 và CORS headers phù hợp | Policy cho phép method/header trước authentication. |
| OPTIONS từ origin không tin cậy | Bị từ chối CORS, thường 403 | Allowlist origin có hiệu lực. |
| Authenticated GET có Origin | 200 và `Access-Control-Allow-Origin` | Response thật có thể được browser đọc. |
| Authenticated POST thiếu CSRF | 403 | CORS không thay CSRF protection. |
| Authenticated POST có CSRF | 201 từ controller | CORS, authentication, CSRF cùng hoạt động. |

## 10. Tùy biến khi yêu cầu phức tạp hơn

### 10.1. Mỗi nhóm API một policy

Một `UrlBasedCorsConfigurationSource` có thể đăng ký nhiều đường dẫn:

~~~java
// Fragment trong phương thức tạo source, không phải class độc lập.
// publicPolicy và adminPolicy là CorsConfiguration đã tạo trước đó.
source.registerCorsConfiguration("/api/public/**", publicPolicy);
source.registerCorsConfiguration("/api/admin/**", adminPolicy);
~~~

Đây là cách **policy theo URL**. CORS không quyết định tài khoản có quyền admin hay không; backend phải dùng authorization. Cần kiểm thử xem path pattern nào thực sự khớp từng request.

### 10.2. Nhiều frontend theo môi trường

Nên đưa origin production/dev vào cấu hình môi trường được kiểm soát để tránh vô tình cho phép origin dev trong production. Không phản chiếu giá trị `Origin` bất kỳ từ request vào `Access-Control-Allow-Origin` và bật credentials, vì đó tương đương policy cho phép mọi origin đọc dữ liệu phiên.

`setAllowedOriginPatterns(…)` cho phép pattern như subdomains nhưng có thể mở quyền rộng hơn dự kiến. Chỉ dùng nếu bạn tin cậy **mọi subdomain được khớp**; các subdomain do bên thứ ba lưu trữ có thể không cùng mức tin cậy. Với vài frontend cố định, allowlist chính xác dễ audit hơn.

### 10.3. Custom source theo tenant

Nếu chính sách CORS phải phụ thuộc tenant, có thể tự triển khai `CorsConfigurationSource` hoặc chọn policy từ một nguồn cấu hình tin cậy. Phải kiểm tra tenant và origin bằng dữ liệu server-side đã xác thực; không để client tự truyền “tenantId/origin được phép” rồi dùng nguyên để cấp quyền CORS. Cần xem xét caching, thay đổi tenant và preflight không có credentials khi thiết kế resolver.

### 10.4. Gateway hoặc reverse proxy

Nếu gateway/CDN đã trả preflight hoặc tự thêm CORS headers, cần thống nhất tầng chịu trách nhiệm. Header trùng hoặc mâu thuẫn (ví dụ proxy thêm `*`, Spring thêm origin cụ thể) có thể khiến browser từ chối. Nếu request chưa bao giờ đến Servlet app, sửa `CorsConfigurationSource` trong Spring không ảnh hưởng response lỗi tại gateway.

### 10.5. API không dùng cookie

Nếu API chỉ dùng token chủ động gửi trong `Authorization` và không cần credentialed CORS theo browser policy, cân nhắc cấu hình credentials chặt hơn; đừng bật cho mọi route theo quán tính. Quyết định CSRF tùy vào cơ chế xác thực tổng thể, không chỉ vì có hay không có CORS.

## 11. Bảng chẩn đoán các lỗi tích hợp điển hình

| Triệu chứng | Nguyên nhân cần xác minh | Cách khắc phục |
| --- | --- | --- |
| `OPTIONS` bị 401 hoặc redirect login | Security chain có chạy CORS trước authentication không? | Bật `http.cors(…)` trên đúng chain và truyền source đúng. |
| `OPTIONS` 403 | Origin, requested method/header, path mapping không thuộc policy. | Kiểm tra `Origin`, `Access-Control-Request-*` và policy thực. |
| Browser thiếu `Access-Control-Allow-Origin` | Request không đi qua CORS processing hoặc endpoint ngoài `/api/**`. | Xác định chain/path/gateway, bổ sung policy đúng scope. |
| Cookie không được gửi | Cross-site cookie policy, `SameSite`, `Secure`, domain/path, `credentials`. | Kiểm tra browser Network/cookie; sửa cookie/session config. |
| Preflight qua nhưng POST 403 | CSRF token thiếu/sai hoặc user thiếu quyền. | Xem security exception, không mở rộng CORS vô cớ. |
| Browser báo wildcard origin + credentials | Dùng `*` cùng credentials hoặc proxy tự thêm wildcard. | Dùng origin cụ thể, loại header mâu thuẫn. |
| GET được nhưng POST JSON không được | POST/content-type/header mới làm preflight, policy chưa cho phép. | Thêm đúng method/header có nhu cầu. |
| `@CrossOrigin` đặt ở controller nhưng preflight vẫn lỗi | Security filter chặn trước controller/MVC. | Kết nối CORS vào security chain trước authentication. |
| Nhiều `CorsConfigurationSource` bean | Framework không tự biết source cho chain. | Chỉ định `cors.configurationSource(…)` tường minh. |
| Local chạy, production lỗi | Scheme/host/port, proxy, credential cookie khác môi trường. | So sánh request/response headers và source tương ứng. |
| MockMvc pass, browser fail | Test không mô phỏng đầy đủ chính sách cookie/cross-site của browser. | Test end-to-end trên đúng origin và HTTPS triển khai. |

Một quy trình debug an toàn:

1. Xác định chính xác frontend origin và request path.
2. Xác định có preflight hay không; đọc requested method và headers.
3. Xác định `SecurityFilterChain` nhận `OPTIONS` và request thật.
4. Xác định `CorsConfigurationSource` trả policy nào; có trả null không?
5. Kiểm tra HTTP status **kèm** `Access-Control-Allow-*` trên preflight và actual response.
6. Nếu CORS đã đúng, chuyển sang authentication/session/CSRF/authorization.
7. Kiểm tra gateway/proxy và cache; `Vary: Origin` giúp cache phân biệt response theo origin khi áp dụng.

Không log nguyên session cookie, CSRF token, Authorization header hoặc dữ liệu người dùng nhạy cảm chỉ để debug CORS.

## 12. Những hiểu nhầm phổ biến

**“Thêm `@CrossOrigin("*")` là đủ.”** Không bảo đảm preflight được xử lý trước security filter; wildcard không thể dùng như credentials approval khi bật credentials. Chọn nguồn CORS và thứ tự filter có kiểm chứng.

**“`CorsConfigurationSource` chính là CORS filter.”** Source chỉ **cấp chính sách**; filter/processor xử lý request và response.

**“Mở `OPTIONS permitAll()` là xong.”** Authorization rule không tự phát sinh các `Access-Control-Allow-*` headers browser yêu cầu.

**“Preflight 200 thì POST phải 200.”** Request thật vẫn phải qua cookie, authentication, CSRF, authorization và controller; 401/403/4xx khác có thể hoàn toàn hợp lệ.

**“Có CORS thì không cần CSRF.”** CORS giải quyết chia sẻ response cross-origin; CSRF đánh giá các request thay đổi trạng thái khi browser tự gửi credentials. Hai cơ chế bổ sung nhau.

**“CORS ngăn mọi client bên ngoài.”** CORS chủ yếu do browser thực thi; gọi trực tiếp qua HTTP client không chịu cùng Same-Origin Policy. Backend cần xác thực và phân quyền riêng.

**“Header `Authorization` nằm trong allowedHeaders nghĩa là token đã được kiểm tra.”** Không. Allowed header chỉ là danh sách tên được browser gửi; token bên trong vẫn phải được backend xác minh.

**“Cấu hình CORS ở một chain tự áp dụng cho mọi chain.”** Mỗi request đi vào chain khớp nó; policy phải được gắn đúng nơi và đúng path.

## 13. Bài tập tư duy và đáp án

1. **Frontend đổi từ `localhost:5173` sang `localhost:5174`, vì sao preflight lỗi?** Origin đổi cổng nên không còn khớp allowlist; cập nhật origin được phép nếu đó là frontend đáng tin.
2. **Preflight yêu cầu `content-type,x-csrf-token`, policy chỉ allow `Content-Type`, chuyện gì xảy ra?** Browser không được cho phép sử dụng header còn thiếu; cần khai báo header CSRF thực sự dùng.
3. **Controller nhận `POST /api/items` khi curl gọi, nhưng browser không thấy POST sau OPTIONS: tìm ở đâu?** Kiểm tra response preflight, path mapping, requested method/header, chain và proxy trước khi debug controller.
4. **Preflight qua, POST 403 vì CSRF invalid: có cần `allowedOrigins("*")` không?** Không; sửa luồng nhận và nộp CSRF token.
5. **Hai `CorsConfigurationSource` cùng là bean, chain API cần source riêng: làm sao?** Inject source đúng và dùng `.cors(cors -> cors.configurationSource(source))` trên API chain.
6. **Frontend cần đọc `Location` trên response 201: đặt ở `allowedHeaders` hay `exposedHeaders`?** Đặt ở `exposedHeaders`, vì `Location` là response header.
7. **Vì sao phải test trên browser thật dù MockMvc pass?** MockMvc không thực thi toàn bộ browser cookie policy, preflight cache và hành vi cross-site ngoài môi trường Spring MVC.
8. **Vì sao không nên dùng Origin client tự gửi để tạo policy cho chính Origin đó?** Client có thể chọn một origin bất kỳ; phản chiếu vô điều kiện sẽ biến allowlist thành cho phép tất cả.

**Kết luận:** `CorsConfiguration` mô tả *cái gì được phép*; `CorsConfigurationSource` quyết định *policy nào áp dụng cho request*; `HttpSecurity.cors(…)` và CORS processing thực thi policy đúng vị trí trong Servlet security chain. Để tích hợp đúng, cấu hình allowlist origin/method/header theo yêu cầu, cho preflight qua lớp CORS, rồi kiểm thử cả request thật với authentication, cookie và CSRF.