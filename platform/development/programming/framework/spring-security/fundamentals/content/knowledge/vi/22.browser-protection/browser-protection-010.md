# Tùy chỉnh cơ chế bảo vệ trình duyệt mặc định theo nhu cầu và kiểm thử cụ thể

## 1. Hiểu đúng bài toán trước khi sửa cấu hình

Spring Security cung cấp một số lớp bảo vệ cho **ứng dụng web chạy trong trình duyệt**. Trình duyệt tự gửi cookie phiên, xử lý HTML/JavaScript, tuân theo chính sách CORS và nhiều HTTP response header. Vì vậy, một thay đổi tưởng như chỉ để “giao diện hoạt động” (cho phép iframe, nới CORS, bỏ CSRF, bật cache) có thể thay đổi khả năng chống tấn công.

Ví dụ: ứng dụng quản lý đơn hàng có giao diện và API cùng origin, dùng phiên đăng nhập qua cookie. Form `POST /orders` cần CSRF token. Khi tách giao diện sang origin khác, nhóm phát triển phải thiết kế thêm CORS và cơ chế trao đổi CSRF token; việc bật CORS **không thay thế** việc kiểm tra CSRF.

**Nguyên tắc:** bắt đầu từ mặc định an toàn; chỉ tùy chỉnh khi có nhu cầu được mô tả bằng **luồng trình duyệt, rủi ro và tiêu chí kiểm thử**. Bài này dùng Spring Security **Servlet** (`HttpSecurity` / `SecurityFilterChain`, phù hợp Spring Boot 3.x và Spring Security 6.x). Với WebFlux phải dùng `ServerHttpSecurity` và bộ công cụ kiểm thử tương ứng, không sao chép nguyên cấu hình Servlet.

## 2. Những mặc định cần nhận diện

| Cơ chế | Hành vi thông dụng của Spring Security Servlet | Khi nào cân nhắc tùy chỉnh? |
| --- | --- | --- |
| CSRF | Mặc định bảo vệ yêu cầu thay đổi trạng thái như `POST`, `PUT`, `PATCH`, `DELETE`; các phương thức an toàn như `GET` không đòi token. | Giao diện SPA dùng cookie, điểm nhận webhook có xác thực chữ ký độc lập, hoặc nhiều luồng đăng nhập khác nhau. |
| `X-Frame-Options` | `DENY`, ngăn trang bị nhúng bằng `iframe`. | Một trang thực sự cần được nhúng trong cùng origin; phải đánh giá clickjacking. |
| `X-Content-Type-Options` | `nosniff`, hạn chế suy đoán kiểu nội dung. | Hầu như luôn giữ; sửa `Content-Type` của tài nguyên sai thay vì tắt `nosniff`. |
| `Cache-Control`, `Pragma`, `Expires` | Mặc định hạn chế lưu cache đáp ứng nhạy cảm. | Chỉ cho phép cache thích hợp cho tài nguyên công khai, tĩnh; giữ chính sách chặt cho trang chứa dữ liệu cá nhân. |
| `Strict-Transport-Security` (HSTS) | Được thêm vào **đáp ứng HTTPS**, không tự xuất hiện trên HTTP. | Hệ thống chạy sau reverse proxy, phạm vi subdomain, chiến lược bật HTTPS/HSTS trên môi trường triển khai. |
| `X-XSS-Protection` | Mặc định `0` vì cơ chế lọc XSS cũ của trình duyệt đã lỗi thời. | Không cố bật bộ lọc cũ thay cho mã hóa đầu ra và CSP. |
| Content Security Policy (CSP) | **Không được Spring Security tự thêm.** | Cần hạn chế nguồn script, style, object và nơi được phép nhúng trang. |
| `Referrer-Policy` | **Không được Spring Security tự thêm.** | Muốn giới hạn thông tin URL gửi qua header `Referer`. |
| CORS | Cần khai báo các origin và phương thức được phép khi giao diện gọi API khác origin. | SPA ở domain/port khác; không dùng CORS như cơ chế xác thực hoặc thay thế CSRF. |

Ngoài những header này, thuộc tính cookie như `Secure`, `HttpOnly`, `SameSite` thường do cấu hình cookie/session và hạ tầng HTTP quyết định, không đơn thuần là `HttpSecurity.headers(...)`. `SameSite=Lax` có ích nhưng không phải lý do bỏ CSRF cho ứng dụng dùng xác thực tự động qua cookie.

Cần phân biệt ba câu hỏi: **Ai được gửi request?** (xác thực, phân quyền), **trình duyệt có được đọc response khác origin?** (CORS), và **request thay đổi trạng thái có do giao diện hợp lệ tạo ra?** (CSRF). Chúng giải quyết các nguy cơ khác nhau.

## 3. Chọn cấu hình theo tình huống thực tế

| Bối cảnh | Quyết định phù hợp | Điều cần kiểm chứng |
| --- | --- | --- |
| Web MVC/Thymeleaf cùng origin, đăng nhập bằng session cookie | Giữ CSRF; dùng token trong form; giữ `X-Frame-Options: DENY` và `nosniff`; bổ sung CSP phù hợp. | Form hợp lệ thành công, POST thiếu/sai CSRF token bị từ chối, trang không bị nhúng trái phép. |
| SPA khác origin gọi API với cookie phiên | Chỉ cho phép các origin cụ thể, bật credential theo nhu cầu; duy trì CSRF và thiết kế cách SPA nhận/gửi token. | Preflight hợp lệ được chấp nhận; origin lạ không được cấp quyền CORS; request ghi thiếu token vẫn bị chặn. |
| API thật sự dùng bearer token do client chủ động gắn, không dùng cookie/HTTP Basic hay thông tin xác thực tự gửi | Đánh giá CSRF theo từng endpoint và cách trình duyệt sử dụng; có thể loại trừ **phạm vi hẹp** sau khi xác minh mô hình xác thực. | Không có đường đi nào từ trình duyệt tự đính kèm thông tin xác thực để thực hiện thay đổi trạng thái; phân quyền vẫn hoạt động. |
| Trang báo cáo cần hiển thị trong `iframe` cùng origin | Có thể đổi sang `SAMEORIGIN` và CSP `frame-ancestors 'self'` cho đúng phạm vi cần nhúng. | Nhúng cùng origin hoạt động; origin ngoài không nhúng được. |
| Tài nguyên CSS/JS công khai cần cache | Cấu hình cache riêng cho tài nguyên tĩnh, giữ bảo vệ trang trả dữ liệu người dùng. | Đáp ứng tĩnh có chính sách cache dự kiến; trang tài khoản vẫn không bị cache nhạy cảm. |

Đừng tắt toàn bộ cấu hình bảo vệ chỉ vì một lỗi `403` hay một thông báo CORS. Trước hết xác định request bị chặn ở bước nào, chứng cứ trong Network/console/log và quy tắc nào cần đổi.

## 4. Ví dụ Java chạy được: giữ CSRF, bổ sung CSP và Referrer-Policy

Giả sử dự án **Spring Boot 3.x, Java 17+**, sử dụng `spring-boot-starter-web` và `spring-boot-starter-security`. Thêm `spring-boot-starter-test` và `spring-security-test` ở phạm vi kiểm thử. Đây là các dependency cho một dự án Boot đã có cấu hình build phù hợp (không phải chương trình Java thuần có thể chạy chỉ bằng `javac`).

Trích đoạn trong `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tệp `src/main/java/demo/browser/BrowserSecurityApplication.java`:

```java
package demo.browser;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BrowserSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(BrowserSecurityApplication.class, args);
    }
}
```

Tệp `src/main/java/demo/browser/SecurityConfig.java`:

```java
package demo.browser;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

@Configuration
@EnableWebSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                // Cho phép hai endpoint minh họa để tách biệt kiểm thử CSRF.
                .requestMatchers("/demo/**").permitAll()
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; object-src 'none'; " +
                    "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
                ))
                .referrerPolicy(referrer -> referrer.policy(
                    ReferrerPolicyHeaderWriter.ReferrerPolicy
                        .STRICT_ORIGIN_WHEN_CROSS_ORIGIN
                ))
            );
        return http.build();
    }
}
```

Tệp `src/main/java/demo/browser/DemoController.java`:

```java
package demo.browser;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/demo")
public class DemoController {
    @GetMapping("/state")
    public String readState() {
        return "ok";
    }

    @PostMapping("/state")
    public String updateState() {
        return "updated";
    }
}
```

**Giải thích hành vi:**

- `.csrf(Customizer.withDefaults())` giữ CSRF theo mặc định. `permitAll()` cho `/demo/**` chỉ bỏ yêu cầu *đăng nhập* cho ví dụ này; nó **không bỏ qua bộ lọc CSRF**.
- Cấu hình CSP minh họa chỉ cho tải tài nguyên cùng origin; không cho `object`, hạn chế thay đổi URL gốc, không cho domain khác nhúng trang và giới hạn đích submit form. Trang thực tế có inline script, CDN, ảnh từ domain khác... phải kiểm kê và thiết kế CSP phù hợp; tránh giải quyết bằng `'unsafe-inline'` tràn lan.
- `Referrer-Policy: strict-origin-when-cross-origin` hạn chế dữ liệu URL bị gửi sang origin khác. Cơ chế này không thay thế kiểm soát URL chứa dữ liệu bí mật.
- Các header mặc định như `X-Frame-Options: DENY` và `X-Content-Type-Options: nosniff` vẫn được giữ khi chỉ bổ sung hai header trên.
- Endpoint demo trả chuỗi và cho truy cập công khai **chỉ để quan sát lớp bảo vệ trình duyệt**. Khi dùng trong sản phẩm, áp dụng quyền truy cập thực tế trước khi phát hành.

## 5. Kiểm thử tự động: cả trường hợp được phép lẫn bị từ chối

Tạo `src/test/java/demo/browser/BrowserSecurityTests.java`:

```java
package demo.browser;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BrowserSecurityTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void httpResponseHasDefaultAndCustomHeaders() throws Exception {
        mockMvc.perform(get("/demo/state"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                "default-src 'self'; object-src 'none'; " +
                "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
            ))
            .andExpect(header().string(
                "Referrer-Policy", "strict-origin-when-cross-origin"
            ))
            .andExpect(header().doesNotExist("Strict-Transport-Security"));
    }

    @Test
    void httpsResponseContainsHsts() throws Exception {
        mockMvc.perform(get("/demo/state").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().exists("Strict-Transport-Security"));
    }

    @Test
    void postWithoutCsrfTokenIsRejected() throws Exception {
        mockMvc.perform(post("/demo/state"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithValidCsrfTokenIsAccepted() throws Exception {
        mockMvc.perform(post("/demo/state").with(csrf()))
            .andExpect(status().isOk());
    }
}
```

Chạy từ gốc dự án Gradle Boot có wrapper:

```bash
./gradlew test --tests demo.browser.BrowserSecurityTests
```

Bốn phép thử có ý nghĩa khác nhau: kiểm tra header sẵn có và mới bổ sung; chứng minh HSTS chỉ xuất hiện khi request được nhận là HTTPS; chứng minh request ghi **không có CSRF token** bị chặn `403`; và chứng minh request có token hợp lệ được xử lý `200`. `with(csrf())` của thư viện kiểm thử tạo token hợp lệ cho MockMvc; nó **không tự chứng minh** rằng JavaScript trong SPA đã lấy và gửi token đúng cách. Các bài kiểm thử này mô phỏng Servlet request, chưa mô phỏng toàn bộ hành vi của trình duyệt thật.

Có thể kiểm tra thêm response đang chạy bằng:

```bash
curl -i http://localhost:8080/demo/state
```

`curl` giúp xem header HTTP nhưng không áp dụng quy tắc nhúng trang/CSP/CORS giống trình duyệt. Để xác minh những quy tắc đó, cần xem Network, Console và thử các luồng giao diện trên trình duyệt thật.

## 6. Ba tùy chỉnh thường gặp cần kiểm thử riêng

### 6.1. SPA gọi API khác origin và dùng cookie phiên

Chỉ bật CORS nếu có nhu cầu thực. Với frontend tại `https://app.example.com` và backend API trên origin khác, có thể bổ sung **đoạn cấu hình** sau vào lớp cấu hình Spring Security (các import tương ứng thuộc `org.springframework.web.cors` và `java.util.List`):

```java
@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    config.setAllowedHeaders(List.of(
        "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"
    ));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
```

Trong `securityFilterChain` thêm `http.cors(Customizer.withDefaults())` và giữ CSRF cho các điểm ghi dùng cookie. Spring Security cần xử lý preflight CORS trước khi bắt buộc xác thực, vì request `OPTIONS` preflight thường không mang cookie phiên. `allowCredentials(true)` phải kết hợp danh sách origin cụ thể, không dùng `"*“` cho `allowedOrigins`. Domain `example.com` chỉ là chỗ điền địa chỉ thật; đừng sao chép vào môi trường triển khai mà chưa thay thế.

**CORS không cung cấp CSRF token.** SPA dùng cookie phải có luồng lấy token, lưu/chuyển token qua header thích hợp và xử lý token sau đăng nhập/đăng xuất. Spring Security 6 có cơ chế deferred token và mã hóa token cho BREACH; riêng việc công khai một cookie chứa token cho JavaScript đọc có thể **chưa đủ** cho toàn bộ luồng SPA. Cần kiểm thử thật với trình duyệt, nguồn phát token và bộ xử lý token được chọn. Chỉ bỏ `HttpOnly` trên cookie chứa CSRF token khi kiến trúc thực sự yêu cầu JS đọc nó; không làm vậy với cookie xác thực phiên.

Kiểm thử tối thiểu: `OPTIONS` từ origin hợp lệ nhận `Access-Control-Allow-Origin` đúng giá trị và cho phương thức/header cần dùng; origin lạ không được cấp quyền; `POST` không có CSRF token vẫn bị chặn; `POST` với token hợp lệ và cookie phiên đúng được xử lý. Đừng kết luận “CORS an toàn” chỉ từ việc frontend không còn báo lỗi.

### 6.2. Cần cho nhúng một phần giao diện qua iframe

Mặc định `X-Frame-Options: DENY` ngăn trang bị nhúng. Nếu chỉ có một báo cáo nội bộ cần nhúng cùng origin, có thể cân nhắc `SAMEORIGIN` và CSP `frame-ancestors 'self'`. Ví dụ **đoạn tùy chỉnh thay cho** chính sách frame của ví dụ trước:

```java
.headers(headers -> headers
    .frameOptions(frame -> frame.sameOrigin())
    .contentSecurityPolicy(csp -> csp.policyDirectives(
        "default-src 'self'; object-src 'none'; frame-ancestors 'self'"
    ))
)
```

`frame-ancestors` điều khiển **ai được nhúng trang của mình**, khác với `frame-src` điều khiển **trang của mình được nhúng nội dung từ đâu**. Nếu chỉ một route cần nhúng, nên thiết kế chính sách theo route/filter chain hoặc header writer chuyên biệt, không nới toàn bộ ứng dụng. Kiểm tra cả nhúng cùng origin **được phép** và nhúng từ origin ngoài **bị chặn** trong trình duyệt; không chỉ kiểm tra chuỗi header.

### 6.3. Một endpoint không dùng xác thực tự gửi của trình duyệt

Webhook được xác thực bằng chữ ký HMAC riêng có thể là ví dụ cho ngoại lệ CSRF hẹp. Sau khi chắc chắn endpoint không dùng session cookie hoặc phương thức xác thực trình duyệt tự gửi, có thể cân nhắc:

```java
// Đoạn đặt trong cấu hình HttpSecurity của ứng dụng.
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/hooks/provider/**")
);
```

Đây **không phải** cách bỏ xác thực cho webhook: server vẫn phải kiểm tra chữ ký, thời hạn, chống phát lại và phân quyền. Đặc biệt, “API stateless” không đủ để chứng minh miễn nhiễm CSRF: cookie JWT và HTTP Basic vẫn có thể bị trình duyệt gửi tự động. Tránh `csrf.disable()` cho toàn ứng dụng chỉ để một đường dẫn hoạt động.

## 7. Bộ tiêu chí kiểm thử khi thay đổi chính sách

| Phép thử | Kết quả kỳ vọng | Cách kiểm tra phù hợp |
| --- | --- | --- |
| `GET` trên HTTP | Có `nosniff`, `DENY` và CSP đã cấu hình; không có HSTS nếu request là HTTP. | MockMvc + kiểm tra header. |
| `GET` trên HTTPS | Có HSTS và header bảo vệ khác. | MockMvc `secure(true)`; kiểm tra thêm qua HTTPS thật. |
| `POST` dùng cookie, không có/sai CSRF token | `403 Forbidden`. | MockMvc kiểm thử âm tính; request thực tế từ UI. |
| `POST` có token hợp lệ và quyền phù hợp | Thành công theo hợp đồng API. | MockMvc kiểm thử dương tính; trình duyệt thật. |
| CORS preflight từ origin hợp lệ | Chỉ cho phép origin, method, header cần dùng. | Kiểm tra `OPTIONS` và response header. |
| CORS từ origin không được phép | Không được cấp quyền đọc response qua CORS. | Browser DevTools; kiểm thử preflight. |
| Trang bị nhúng bởi origin ngoài | Bị trình duyệt từ chối theo `X-Frame-Options`/`frame-ancestors`. | Trang thử có iframe ở origin ngoài. |
| Trang có script/style cần thiết | Không sinh lỗi CSP ngoài dự kiến, không phải nới vô tội vạ. | Browser Console, tự động hóa trình duyệt. |
| Trang chứa dữ liệu phiên sau đăng xuất | Không lộ dữ liệu nhạy cảm từ cache. | Kiểm tra response header, back-navigation, storage/cache. |

Với HTTPS đi qua reverse proxy/load balancer, xác nhận ứng dụng nhìn thấy thông tin HTTPS đúng (chẳng hạn cấu hình forwarded headers đáng tin cậy); nếu request bị nhận nhầm là HTTP, quy tắc chỉ thêm HSTS cho HTTPS sẽ bị ảnh hưởng. Khi cân nhắc `includeSubDomains` hoặc HSTS dài hạn, phải chắc chắn các subdomain có HTTPS hoạt động; trình duyệt có thể ghi nhớ chính sách trong thời gian dài.

CSP nên triển khai thận trọng theo từng tài nguyên/đường dẫn, có thể bắt đầu từ `Content-Security-Policy-Report-Only` để quan sát vi phạm trước khi áp dụng chặn thực tế. Báo cáo vi phạm và bài test header không thay thế việc dùng trình duyệt thử luồng đăng nhập, form, iframe, tải CSS/JS và thanh toán.

## 8. Sai lầm phổ biến và cách tự rà soát

1. **Bỏ CSRF vì API dùng JSON hoặc “stateless”.** Hãy kiểm tra thông tin xác thực có được trình duyệt tự gửi không, thay vì suy ra từ kiểu payload/session.
2. **Đặt `allowedOrigins("*")` cùng `allowCredentials(true)`.** Cần danh sách origin cụ thể và giới hạn method/header theo nhu cầu.
3. **Tắt `X-Frame-Options` toàn cục để sửa một iframe.** Chỉ nới đúng các trang cần nhúng; phối hợp với CSP `frame-ancestors`.
4. **Bật CSP cực chặt mà không kiểm thử tài nguyên của trang.** Kiểm tra script, style, font, ảnh, kết nối và form; ưu tiên nonce/hash hoặc nguồn tin cậy cần thiết thay vì mở rộng vô hạn.
5. **Mở cache cho mọi response để tăng tốc.** Chỉ áp dụng cache cho tài nguyên công khai thích hợp; nội dung cá nhân phải xét riêng.
6. **Thử HSTS bằng HTTP rồi kết luận bị tắt.** HSTS mặc định chỉ được ghi vào response HTTPS.
7. **Chỉ viết test “luồng hợp lệ chạy được”.** Phải thêm kiểm thử âm tính cho token thiếu/sai, origin lạ, iframe ngoài và tài nguyên CSP bị chặn.
8. **Nhầm `permitAll()` là bỏ mọi filter.** Endpoint có thể cho phép anonymous nhưng vẫn chịu CSRF, CORS và header bảo vệ.

Trước khi chấp nhận thay đổi, hãy trả lời được: **(a)** nhu cầu trình duyệt cụ thể là gì; **(b)** mặc định nào bị giữ/thay; **(c)** ảnh hưởng tới endpoint và origin nào; **(d)** test nào chứng minh trường hợp được phép và bị từ chối; **(e)** trình duyệt thực tế đã được kiểm thử sau khi triển khai chưa.

## Tài liệu tham khảo

- Spring Security — [Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html).
- Spring Security — [Cross-Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).
- Spring Security — [CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html).
- Spring Security — [Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/).