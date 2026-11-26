# Đánh giá kết quả bằng mô hình nguy cơ, cấu hình và bằng chứng hành vi

## 1. Mục tiêu của bài thực hành tổng hợp

Trong **SPRING_SECURITY_HTTP_PROTECTION**, một cấu hình Spring Security được xem là hiệu quả khi có bằng chứng rằng nó chống được đúng mối đe dọa đặt ra trong **bối cảnh hệ thống đang triển khai**. Việc thấy `csrf(Customizer.withDefaults())`, một header CSP hoặc thông báo kiểm thử thành công chưa đủ để kết luận rằng đường đi từ trình duyệt, reverse proxy, Spring Security đến handler đã được bảo vệ như mong muốn.

Bài thực hành này kết nối các nội dung đã học về **CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, session và cookie** thành một quy trình đánh giá có thể lặp lại cho cả Servlet và Reactive.

Sau bài, người học có thể:

1. Xác định tài sản cần bảo vệ, đối thủ, khả năng tấn công, trust boundary và mức thiệt hại dự kiến.
2. Liên kết từng tình huống nguy cơ với cấu hình tương ứng trong Spring Security và với yêu cầu bảo mật kiểm chứng được.
3. Lập bằng chứng từ cấu hình thực tế, HTTP request/response, kiểm thử tự động và hành vi trình duyệt.
4. Phân biệt kết quả `PASS`, `FAIL`, `INCONCLUSIVE` (chưa đủ bằng chứng), và giải thích rủi ro còn lại.
5. Tạo một báo cáo nghiệm thu có thể truy nguyên từ nguy cơ đến kiểm thử và quyết định triển khai.

**Quy tắc xuyên suốt:**

> Mỗi khẳng định “đã được bảo vệ” cần trả lời ba câu hỏi: **Đang chống mối nguy nào? Cấu hình nào tác động vào đường đi đó? Bằng chứng nào cho thấy attacker không đạt được mục tiêu, trong khi người dùng hợp lệ vẫn hoạt động?**

Tài liệu đưa ra **các kịch bản và kết quả kỳ vọng** để người học tự thực hiện. Các ví dụ PASS/FAIL minh họa không phải kết quả đo được của một ứng dụng đang chạy.

## 2. Hệ thống mẫu và phạm vi đánh giá

Giả sử có hai dịch vụ triển khai sau reverse proxy:

- **Ứng dụng Servlet** tại `https://portal.example.test`: Spring MVC, form login, session cookie `JSESSIONID`, các trang `/dashboard`, `/account/email` và `/admin/`. Các thao tác thay đổi dữ liệu dùng cookie đăng nhập và CSRF token.
- **Dịch vụ Reactive** tại `https://api.example.test`: Spring WebFlux, API `/api/me` và `/api/reports`, xác thực bằng bearer token trong header `Authorization`, không dùng session cookie để xác thực. Trình duyệt tại `https://portal.example.test` được phép gọi API khi đáp ứng CORS.
- **Reverse proxy/CDN** kết thúc TLS, chuyển tiếp request đến các ứng dụng, có thể thêm hoặc thay đổi HTTP response headers.
- **Dịch vụ bên ngoài** được tích hợp theo nghiệp vụ, chẳng hạn SDK phân tích và endpoint API của nhà cung cấp; danh sách nguồn cụ thể phải được kiểm kê.

Tên miền `example.test` dùng cho minh họa, không đại diện một hệ thống có thật. Giả định Servlet và Reactive là hai ứng dụng hoặc hai chain riêng; cách chia ranh giới phải được xác nhận bằng kiến trúc thật.

~~~mermaid
flowchart TB
    Attacker["Website của attacker"]
    Browser["Trình duyệt người dùng"]
    Proxy["Reverse proxy / TLS"]
    MVC["Spring MVC + Session cookie"]
    API["Spring WebFlux + Bearer token"]
    Data["Dữ liệu tài khoản / báo cáo"]
    External["SDK và API bên ngoài"]

    Attacker -. "gửi cross-site request / nhúng frame / chèn script" .-> Browser
    Browser -->|"HTTPS: portal.example.test"| Proxy
    Browser -->|"HTTPS: api.example.test"| Proxy
    Browser -->|"tải nguồn được duyệt"| External
    Proxy --> MVC
    Proxy --> API
    MVC --> Data
    API --> Data
~~~

### 2.1. Những tài sản cần bảo vệ

| Tài sản | Tính chất bảo mật cần giữ | Hậu quả nếu bị xâm phạm |
|---|---|---|
| Phiên đăng nhập | Không bị đánh cắp, sử dụng trái phép, cố định ID hoặc tiếp tục dùng sau logout | Chiếm phiên và sửa dữ liệu người dùng |
| Thao tác thay đổi dữ liệu | Chỉ được thực hiện bởi chủ thể đã xác thực, đủ quyền và có kiểm tra CSRF khi dùng cookie | Đổi email, phân quyền hoặc cấu hình trái ý chủ tài khoản |
| Nội dung trang và DOM | Không thực thi script do bên không tin cậy đưa vào | XSS, đọc dữ liệu phía trình duyệt, phát request dưới quyền phiên |
| Dữ liệu API | Xác thực, phân quyền và giới hạn việc đọc từ origin khác | Rò rỉ dữ liệu qua API hoặc truy cập sai quyền |
| Kênh truyền và cookie | HTTPS, header và thuộc tính cookie được duy trì qua proxy | Rò rỉ credential, downgrade hoặc hoạt động thiếu biện pháp bảo vệ |
| Đường dẫn và bộ lọc bảo mật | Cách chuẩn hóa đường dẫn nhất quán qua proxy, container, firewall và matcher | Bypass phân quyền do diễn giải URL khác nhau |

### 2.2. Tác nhân, khả năng tấn công và ranh giới tin cậy

Một mô hình nguy cơ tốt phải xác định **attacker làm được gì**. Ví dụ:

- **Người điều khiển website khác origin:** có thể khiến trình duyệt nạn nhân truy cập URL, gửi form hoặc thử đọc API qua JavaScript; không được giả định có thể đọc cookie `HttpOnly` hoặc tự lấy CSRF token hợp lệ.
- **Người chèn nội dung vào vùng dữ liệu:** có thể đưa chuỗi HTML/JS nguy hiểm vào tên hiển thị hoặc một bình luận; cần xét cả mã hóa output và CSP.
- **Người gửi HTTP request tùy ý:** có thể sửa path, phương thức, header, cookie hoặc token khi gọi server trực tiếp. Người này không bị giới hạn bởi cơ chế CORS của trình duyệt.
- **Thành phần bên ngoài bị xâm nhập:** có thể thay nội dung SDK từ host đã cho phép; cần xem xét phạm vi tin cậy được cấp cho mã này.
- **Sai lệch hạ tầng:** reverse proxy có thể không chuyển đúng scheme, strip header, cache HTML chứa nonce, hoặc giải mã path khác với ứng dụng.

**Trust boundary cần kiểm tra:**

1. Dữ liệu không tin cậy → HTML/DOM.
2. Origin bên ngoài → trình duyệt có session của ứng dụng.
3. Trình duyệt → reverse proxy/TLS → security filter chain → controller.
4. Servlet cookie-authentication → endpoint thay đổi trạng thái.
5. Reactive bearer-authentication → tài nguyên có phân quyền.
6. CDN/SDK bên ngoài → khả năng thực thi trên trang và truy cập API.

Không có biện pháp đơn lẻ nào giải quyết toàn bộ các ranh giới này. Ví dụ: **CORS hạn chế việc script ở origin không được phép đọc response**, nhưng không chứng minh một yêu cầu POST có side effect được chống CSRF; **CSP hạn chế script/tài nguyên**, nhưng không thay thế encode đầu ra hoặc phân quyền phía server.

## 3. Lập mô hình nguy cơ thành các giả thuyết có thể kiểm chứng

Có thể dùng STRIDE để nghĩ đến nhóm nguy cơ (giả mạo, sửa đổi, chối bỏ, lộ thông tin, từ chối dịch vụ, leo thang đặc quyền), nhưng báo cáo thực hành cần mô tả **đường tấn công cụ thể**. Ví dụ: “Attacker kiểm soát một website khác origin, nạn nhân đang đăng nhập, attacker gửi POST đổi email qua form” rõ ràng hơn “nguy cơ spoofing”.

Mỗi mục nguy cơ gồm: mã định danh, tài sản, điểm vào, điều kiện tiên quyết, tác động, biện pháp, phép thử và mức rủi ro còn lại.

| ID | Giả thuyết nguy cơ và điều kiện | Biện pháp kỳ vọng | Bằng chứng hành vi tối thiểu |
|---|---|---|---|
| T01 | Nạn nhân đăng nhập Servlet bằng cookie; website lạ phát POST thay đổi email không có CSRF token | CSRF token trên thao tác thay đổi trạng thái; cấu hình cookie phù hợp | POST không token bị từ chối; POST hợp lệ có token được xử lý |
| T02 | Script tại origin lạ cố đọc response của endpoint CORS được bảo vệ | CORS allowlist chính xác; authentication và authorization server-side | Preflight origin lạ không được cấp quyền; origin hợp lệ được cấp đúng quyền; truy cập thiếu credential bị từ chối |
| T03 | Attacker chèn chuỗi `<script>`/inline event handler vào vùng HTML | Output encoding, tránh sink nguy hiểm, CSP phù hợp | Script chèn không thực thi; script nội bộ hợp lệ vẫn chạy |
| T04 | Attacker nhúng trang quản trị vào iframe để dụ click | `frame-ancestors 'none'`; có thể kết hợp `X-Frame-Options: DENY` | Trình duyệt thực từ chối hiển thị trang trong iframe |
| T05 | Người dùng truy cập qua HTTP hoặc proxy làm thất lạc chính sách HTTPS | TLS và chuyển hướng HTTP→HTTPS ở edge, HSTS trên HTTPS | HTTPS response có HSTS; HTTP được chuyển hướng; kiểm tra luồng proxy thực |
| T06 | ID phiên không thay đổi sau login hoặc cookie không đủ thuộc tính bảo vệ | Session fixation protection; `Secure`, `HttpOnly`, `SameSite` | ID session trước/sau login được thay khi có session trước login; cookie trên response thực có thuộc tính mong đợi |
| T07 | URL có dấu chấm phẩy, encoded path hoặc phân cách bất thường được xử lý khác nhau qua các lớp | `StrictHttpFirewall`, matcher rõ ràng, thống nhất canonicalization | Request bất thường bị từ chối hoặc không tới tài nguyên cần quyền; request chuẩn vẫn hoạt động |
| T08 | Sau logout, session cũ vẫn truy cập được trang bảo vệ | Logout invalidation và xóa thông tin xác thực | Thực hiện logout hợp lệ, replay cookie cũ không truy cập được nội dung đã bảo vệ |
| T09 | API Reactive chấp nhận thiếu bearer token hoặc không kiểm tra quyền | Authentication, authorization tại `SecurityWebFilterChain` | Không token trả 401; token thiếu quyền bị 403; token hợp lệ đúng quyền được xử lý |
| T10 | Lỗi, redirect hoặc đường dẫn ngoài chain không mang đủ security headers | Bao phủ các route/chain và header tại response cuối cùng | Header được kiểm tra trên HTML thường, lỗi, route đăng nhập và sau proxy |

Bảng này là **sổ đăng ký nguy cơ ban đầu**, có thể thay đổi khi có phát hiện mới. Cần thêm điều kiện riêng cho ứng dụng, chẳng hạn WebSocket, iframe thanh toán, CSP nonce, CORS có credential hoặc nhiều `SecurityFilterChain`.

### 3.1. Đánh giá mức độ ưu tiên

Để ưu tiên kiểm thử, nhóm có thể sử dụng thang điểm đơn giản, **không coi là phép đo tuyệt đối**:

- `Likelihood` từ 1 đến 5: từ khó xảy ra đến dễ khai thác trong kiến trúc hiện tại.
- `Impact` từ 1 đến 5: từ ảnh hưởng nhỏ đến mất quyền kiểm soát dữ liệu/phiên quan trọng.
- `Risk = Likelihood × Impact`, điểm từ 1 đến 25.

Ví dụ minh họa: T01 có likelihood 4, impact 4 ⇒ 16; T04 có likelihood 3, impact 3 ⇒ 9. Nhóm cần ghi **lý do** cho điểm và cập nhật sau khi thấy bằng chứng. Một tình huống có mức ảnh hưởng nghiêm trọng không được nghiệm thu chỉ vì tổng điểm trung bình của các phép thử khác cao.

## 4. Bản đồ liên kết nguy cơ → cấu hình → phép thử

Ba góc đánh giá phải liên kết bằng cùng một mã nguy cơ.

~~~mermaid
flowchart LR
    Threat["T01: POST đổi email từ website lạ"]
    Config["CSRF áp dụng cho /account/email<br/>session cookie được bảo vệ"]
    Positive["POST đăng nhập + token hợp lệ<br/>thành công theo hợp đồng"]
    Negative["POST đăng nhập, thiếu/sai token<br/>403 và không đổi dữ liệu"]
    Evidence["Raw response + test log<br/>DB state + mã revision"]
    Decision["PASS / FAIL / INCONCLUSIVE<br/>Rủi ro còn lại"]

    Threat --> Config
    Config --> Positive
    Config --> Negative
    Positive --> Evidence
    Negative --> Evidence
    Evidence --> Decision
~~~

Một bảng traceability dùng trong báo cáo:

| Threat | Config cần kiểm chứng | Test âm tính | Test dương tính | Bằng chứng cần lưu |
|---|---|---|---|---|
| T01 | CSRF trong chain Servlet, route POST không bị bỏ qua | Không/sai token → 403, không thay dữ liệu | Token hợp lệ → thành công | Cấu hình + request/response đã ẩn token + trạng thái dữ liệu trước/sau |
| T02 | CORS nguồn cho `/api/reports/**`, không mở wildcard khi gửi credential | Origin lạ không nhận `Access-Control-Allow-Origin` | Origin được duyệt có header đúng; đăng nhập/quyền vẫn được kiểm tra | Preflight raw headers + browser console/network |
| T03 | CSP tại response HTML và mã hóa dữ liệu đầu ra | Inline script giả lập không chạy | Bundle script nội bộ vẫn chạy | Header của trang + ảnh/console DevTools + phép thử DOM |
| T04 | `frame-ancestors` trong CSP | Frame từ origin lạ không hiển thị trang bảo vệ | Trang mở top-level bình thường | Console lỗi frame + header của response được nhúng |
| T05 | TLS, redirect và HSTS | HTTPS không bị hạ xuống HTTP sau khi HSTS đã được ghi nhớ | HTTPS login hoạt động | HTTP redirect + HTTPS header + kiểm tra browser |
| T06 | Cookie flags, session rotation/logout | Cookie/ID session cũ không duy trì quyền sau logout | Session mới đăng nhập hợp lệ | `Set-Cookie` đã che ID + thao tác login/logout |
| T07 | HTTP firewall và request matchers | Path bất thường không vượt qua kiểm tra | URL chuẩn đến đúng endpoint | Log kiểm thử path + response và route xử lý |
| T09 | WebFlux `SecurityWebFilterChain` cho API | Không token/token sai quyền bị từ chối | Token hợp lệ có quyền phù hợp thành công | WebTestClient/HTTP traces + quyết định authorization |

**Không suy luận ngược từ header sang bảo vệ đầy đủ.** Ví dụ, thấy `Content-Security-Policy` trong response không chứng minh DOM XSS đã được loại bỏ; thấy mã 403 không chứng minh CSRF là nguyên nhân nếu request bị chặn từ bước authentication hoặc CORS. Với mỗi phép thử cần kiểm tra **điều kiện khởi đầu** và **lý do hành vi**.

## 5. Đối chiếu với cấu hình Spring Security Servlet

### 5.1. Cấu hình minh họa cho portal có session

Trong ví dụ dưới đây, chuỗi cấu hình dùng xác thực bằng form, bảo vệ CSRF mặc định và tách quyền truy cập admin. Các URL và policy phải được điều chỉnh theo ứng dụng thật.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfig {

    private static final String CSP = String.join("; ",
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'"
    );

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**", "/error").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .cors(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
            )
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.changeSessionId())
            )
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(CSP))
                .frameOptions(frame -> frame.deny())
                .httpStrictTransportSecurity(hsts -> hsts
                    .maxAgeInSeconds(86400)
                    .includeSubDomains(false)
                )
            );

        return http.build();
    }
}
~~~

**Đọc cấu hình để tìm bằng chứng gì?**

- T01: `csrf(Customizer.withDefaults())` có hiệu lực trên chain chứa `POST /account/email`, và không có matcher ngoại lệ nào vô tình bỏ bảo vệ.
- T03: `script-src 'self'` không cấp phép inline script, `eval()` hay host lạ. Giao diện và trang đăng nhập phải được kiểm tra để bảo đảm không phụ thuộc inline JavaScript/CSS bị chặn.
- T04: `frame-ancestors 'none'` áp dụng với trang HTML; `X-Frame-Options: DENY` hỗ trợ hành vi chống nhúng trên trình duyệt phù hợp.
- T05: HSTS được phát cho request được nhận diện là HTTPS. `max-age=86400` trong ví dụ phù hợp cho thử nghiệm rollout; thời hạn dài và `includeSubDomains` cần quyết định sau khi xác minh toàn bộ hostname dùng HTTPS.
- T06: `changeSessionId()` bảo vệ khỏi cố định ID phiên khi đăng nhập trên môi trường Servlet hỗ trợ; vẫn phải xác minh session thực sự được tạo trước login trong phép thử.
- T07: cấu hình không cố tình nới `StrictHttpFirewall` mặc định của Spring Security; cần kiểm tra request thực tế sau reverse proxy.
- T08: với CSRF đang bật, logout mặc định yêu cầu POST có token hợp lệ. Kiểm tra invalidate session và thử lại bằng cookie cũ.

Cấu hình này **chưa chứa** việc chuyển hướng HTTP→HTTPS ở reverse proxy, cấu hình TLS hoặc cấu hình cookie. Những điều đó là phần riêng của kiểm tra triển khai. Với nhiều `SecurityFilterChain`, request chỉ sử dụng chain đầu tiên có `securityMatcher` phù hợp; phải xác định rõ chain nào xử lý từng URL trước khi đánh giá.

### 5.2. Cookie và phiên trong ứng dụng Servlet

Ví dụ cấu hình Spring Boot cho session cookie:

~~~yaml
server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

Khi chạy HTTPS tại reverse proxy nhưng HTTP giữa proxy và ứng dụng, cần cấu hình nhận diện forwarded headers một cách có kiểm soát trên hạ tầng đã tin cậy. Kiểm tra `Set-Cookie` ở **response cuối cùng mà trình duyệt nhận**, thay vì chỉ nhìn YAML.

Ý nghĩa khi đánh giá:

| Thuộc tính/cơ chế | Điều xác nhận được | Điều chưa được đảm bảo |
|---|---|---|
| `Secure` | Trình duyệt chỉ gửi cookie trên kênh phù hợp HTTPS | Không giải quyết XSS hay CSRF |
| `HttpOnly` | JavaScript không đọc trực tiếp cookie qua `document.cookie` | XSS vẫn có thể gọi API dưới quyền trình duyệt |
| `SameSite=Lax` | Hạn chế một số trường hợp gửi cookie trong ngữ cảnh cross-site | Không thay thế CSRF token; top-level navigation an toàn có thể vẫn gửi cookie |
| Thay session ID khi login | Giảm nguy cơ dùng trước một ID phiên mà attacker đã biết | Không chứng minh session không thể bị đánh cắp theo cách khác |
| Vô hiệu hóa session khi logout | Token phiên cũ không còn xác thực request tiếp theo | Không tự xóa mọi cache hoặc token ở hệ thống khác |

Để kiểm tra session fixation có ý nghĩa, cần tạo **session trước khi đăng nhập** (ví dụ vào trang lấy CSRF token), ghi nhận ID theo cách ẩn danh, rồi đăng nhập và xác nhận ID thay đổi. Nếu không có session trước login, việc chỉ quan sát cookie mới sau login không đủ chứng minh cơ chế rotation.

### 5.3. CORS cho endpoint dành cho một origin tin cậy

CORS là một chính sách trình duyệt, cần xuất hiện ở API mà script cross-origin truy cập. Ví dụ Servlet cho phép chỉ `https://reports.example.test` gọi `/api/reports/**` có gửi cookie:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://reports.example.test"));
    config.setAllowedMethods(List.of("GET", "POST"));
    config.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/reports/**", config);
    return source;
}
~~~

Đây là ví dụ **riêng cho endpoint Servlet có nhu cầu credentialed CORS thật sự**. Với API Reactive bearer-only của tình huống đầu bài, cấu hình CORS phải đặt trong dịch vụ Reactive tương ứng và chỉ cho các origin cần thiết. Không áp dụng bean Servlet trên một ứng dụng WebFlux thuần.

Một request cross-origin được CORS cho phép **không được miễn CSRF** nếu trình duyệt tự gửi session cookie khi thực hiện thao tác thay đổi dữ liệu. `Access-Control-Allow-Credentials: true` cũng không thay thế authentication hoặc kiểm tra quyền.

## 6. Đối chiếu với Reactive và lựa chọn chiến lược CSRF

Với **Spring WebFlux**, logic tương ứng được cấu hình trong `SecurityWebFilterChain` bằng `ServerHttpSecurity`. Nếu API **chỉ** chấp nhận bearer token do client chủ động đưa trong header `Authorization`, không sử dụng cookie/HTTP Basic hoặc bất kỳ credential nào trình duyệt tự gửi, có thể cân nhắc vô hiệu hóa CSRF cho nhóm route đó sau khi kiểm tra giả định.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        // Chỉ phù hợp khi API thực sự bearer-only,
        // không xác thực bằng cookie hoặc Basic.
        .csrf(csrf -> csrf.disable())
        .cors(Customizer.withDefaults())
        .headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                    "default-src 'none'; object-src 'none'; frame-ancestors 'none'"
                )
            )
        )
        .build();
}
~~~

Ví dụ giả định ứng dụng đã cấu hình `JwtDecoder` hoặc issuer/JWK cho resource server và có CORS source Reactive tương ứng. Header CSP ở API trả JSON không phải bằng chứng thay cho CSP trên **document HTML** của portal; chính response tài liệu HTML mới kiểm soát tải script của trang.

Quy tắc đánh giá quyết định CSRF:

| Cơ chế xác thực của endpoint | Credential có được trình duyệt tự gửi? | Hướng đánh giá |
|---|---|---|
| Form login + session cookie | Có, tùy SameSite và ngữ cảnh request | Duy trì CSRF token cho thao tác thay đổi dữ liệu |
| HTTP Basic do trình duyệt quản lý | Có thể | Phân tích CSRF, không mặc định bỏ |
| Bearer token trong header do client tự gắn | Thông thường không | Có thể không dùng CSRF nếu **tất cả** đường xác thực thật sự bearer-only |
| API hỗn hợp bearer và session cookie | Có trên một số đường đi | Đánh giá riêng từng chain/route; không suy rộng từ API bearer-only sang endpoint cookie-authenticated |

T09 cần kiểm thử **authentication và authorization** riêng. Một API trả 401 khi không có token vẫn có thể bị lỗi phân quyền nếu token của user A đọc được dữ liệu user B.

## 7. Thiết kế phép thử đủ để chứng minh hành vi

Khi viết testcase, phải có:

1. **Tiền điều kiện:** tài khoản, quyền, session đã đăng nhập, origin nguồn, HTTPS, token hoặc dữ liệu trước khi thử.
2. **Hành động:** phương thức, URL, header, body và nơi request được phát (browser, HTTP client, MockMvc, WebTestClient).
3. **Kỳ vọng:** HTTP status, header, cookie, DOM hoặc thay đổi dữ liệu.
4. **Quan sát:** đầu ra thực tế, timestamp, phiên bản ứng dụng và chứng cứ kèm theo.
5. **Diễn giải:** phép thử đã chứng minh/không chứng minh điều gì; còn đường nào chưa kiểm tra.

### 7.1. Ma trận positive/negative

| Mã test | Điều kiện và hành động | Kết quả kỳ vọng | Threat |
|---|---|---|---|
| B01 | Đăng nhập hợp lệ, POST đổi email **thiếu** CSRF token | 403; email giữ nguyên | T01 |
| B02 | Cùng POST với CSRF token đúng từ phiên đang đăng nhập | Thành công theo hợp đồng API; email thay đổi đúng | T01 |
| B03 | Đưa CSRF token từ phiên A sang request của phiên B | Bị từ chối; không thay dữ liệu | T01 |
| B04 | Preflight từ origin lạ đến endpoint CORS | Không cấp `Access-Control-Allow-Origin` tương ứng | T02 |
| B05 | Preflight từ origin được duyệt, method/header được duyệt | CORS header chính xác, không dùng wildcard khi có credentials | T02 |
| B06 | CORS được cho phép nhưng request API thiếu authentication | 401/đáp ứng từ chối phù hợp | T02/T09 |
| B07 | Chèn inline script không có nonce/hash vào HTML được CSP bảo vệ | Không chạy; trình duyệt báo CSP violation | T03 |
| B08 | Script nội bộ hợp lệ tải từ nguồn được duyệt | Chạy bình thường; không tạo violation ngoài dự kiến | T03 |
| B09 | Trang admin bị nhúng trong iframe từ trang attacker | Trình duyệt từ chối render iframe | T04 |
| B10 | Tải document qua HTTPS sau reverse proxy | HSTS, CSP và các header liên quan hiện diện | T05/T10 |
| B11 | Tạo session trước login, login, so sánh session ID | ID thay đổi | T06 |
| B12 | Đăng xuất bằng POST hợp lệ, thử dùng cookie cũ truy cập `/admin/` | Không còn quyền truy cập | T08 |
| B13 | Request path có đoạn mã hóa hoặc `;` gây nhập nhằng | Bị chặn hoặc không thể bypass kiểm tra quyền | T07 |
| B14 | Request API Reactive không có bearer token | 401 | T09 |
| B15 | Request API với token hợp lệ nhưng thiếu role/scope | 403 hoặc từ chối đúng hợp đồng | T09 |
| B16 | Request API với token và quyền hợp lệ | Thành công và không tiết lộ dữ liệu ngoài phạm vi | T09 |

Đối với B01/B03, **kiểm tra dữ liệu không thay đổi**: một mã 403 có thể bị trả sau khi ứng dụng đã gây side effect do lỗi sắp xếp bước xử lý. Với B12, không chỉ nhìn redirect của logout; phải replay credential cũ vào endpoint thực sự yêu cầu đăng nhập.

### 7.2. MockMvc: xác nhận CSRF, quyền và response headers

Các đoạn sau mang tính mẫu. Để chạy được phải có các endpoint và dependency test tương ứng (Spring Security Test, JUnit, Spring Boot Test) trong ứng dụng.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PortalSecurityBehaviorTest {

    @Autowired
    MockMvc mvc;

    @Test
    void changingEmailWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/account/email")
                .with(user("alice").roles("USER"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "other@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void changingEmailWithValidCsrfIsAllowed() throws Exception {
        mvc.perform(post("/account/email")
                .with(user("alice").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("email", "new@example.test"))
            .andExpect(status().isOk()); // Giả định handler trả 200 khi thành công.
    }

    @Test
    void ordinaryUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin/")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void httpsHtmlResponseContainsExpectedHeaders() throws Exception {
        mvc.perform(get("/login").secure(true))
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("frame-ancestors 'none'")
            ))
            .andExpect(header().string(
                "Strict-Transport-Security",
                containsString("max-age=86400")
            ));
    }
}
~~~

Đối với B02, assertion `200` phải thay bằng status theo hợp đồng endpoint thật; cần thêm kiểm tra dữ liệu đã thay đổi đúng. Với B01, nên dùng test database riêng và xác minh bản ghi không đổi. `with(user(...))` mô phỏng authentication trong MockMvc; nó **không** chứng minh luồng login qua cookie trên trình duyệt. `with(csrf())` cung cấp token phục vụ test, không tự xác nhận giao diện thật có gửi token đúng.

### 7.3. WebTestClient: xác nhận authentication của Reactive API

Ví dụ với API có endpoint `GET /api/me` yêu cầu bearer token:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ApiSecurityBehaviorTest {

    @Autowired
    WebTestClient client;

    @Test
    void missingBearerTokenIsUnauthorized() {
        client.get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Test trên không khẳng định token đã được kiểm tra signature, audience, expiry hoặc phân quyền nghiệp vụ. Để chứng minh T09, bổ sung token thật/test token với claim hợp lệ và các trường hợp token sai, hết hạn, thiếu role/scope, truy cập tài nguyên của người khác.

### 7.4. HTTP và reverse proxy: quan sát response cuối cùng

Ví dụ kiểm tra header của HTTPS response:

~~~bash
curl -sS -D - -o /dev/null https://portal.example.test/login
~~~

Quan sát `Content-Security-Policy`, `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options` (nếu ứng dụng phát), `Cache-Control` và `Set-Cookie` khi response thực sự tạo session. **Không** kết luận cookie sai chỉ vì response `/login` chưa tạo session nên chưa có `Set-Cookie`.

Kiểm tra CORS preflight từ origin không tin cậy:

~~~bash
curl -sS -i -X OPTIONS \
  "https://portal.example.test/api/reports/summary" \
  -H "Origin: https://untrusted.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Kỳ vọng không cấp `Access-Control-Allow-Origin` cho `https://untrusted.example.test`; tùy cấu hình, server có thể trả 403 hoặc một response không cho phép trình duyệt đọc. Không đồng nhất “thiếu header CORS” với “server không nhận request cross-site”. POST dạng form đơn giản vẫn có thể được gửi; vì vậy B01 phải kiểm thử riêng.

Preflight từ origin tin cậy dùng cùng lệnh nhưng thay Origin thành `https://reports.example.test`, kỳ vọng header `Access-Control-Allow-Origin: https://reports.example.test` và, nếu thực sự dùng credentialed CORS, `Access-Control-Allow-Credentials: true`. Trường hợp này vẫn phải xác thực, phân quyền và chống CSRF ở request POST thực tế.

Kiểm tra HTTP→HTTPS và HSTS cần quan sát cả **edge** lẫn trình duyệt. HSTS chỉ được trình duyệt chấp nhận qua kết nối HTTPS hợp lệ và chỉ tác động sau khi host đã được ghi nhớ (trừ trường hợp preload). Do đó một redirect HTTP→HTTPS thành công không đủ để chứng minh HSTS hoạt động; ngược lại HSTS cũng không chứng minh lần truy cập HTTP đầu tiên được bảo vệ.

### 7.5. Browser: hành vi CSP, iframe, cookie và session

CSP là chính sách trình duyệt, cần dùng trình duyệt thật hoặc browser automation. Thực hiện tối thiểu:

- Mở tab **Network**, chọn response document HTML và ghi nhận CSP cuối cùng. Kiểm tra các route `/login`, `/dashboard`, `/admin/` và trang lỗi.
- Mở **Console**, chèn thử một inline script không có nonce/hash trong vùng thử nghiệm có kiểm soát; xác minh nó không chạy và tìm `effective-directive` tương ứng.
- Mở ứng dụng bình thường; xác minh script, CSS, API cần thiết hoạt động và không có vi phạm CSP ngoài dự kiến.
- Tạo một trang khác origin chứa `<iframe src="https://portal.example.test/admin/">`; xác nhận browser từ chối render theo `frame-ancestors` hoặc X-Frame-Options.
- Trong DevTools → Application/Storage → Cookies, xác minh `Secure`, `HttpOnly` và `SameSite` của cookie phiên, sau đó kiểm tra rotate ID khi login và invalidation khi logout.
- Dùng Network để đối chiếu request/response CORS: kiểm tra `Origin`, preflight, `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials` và lỗi browser nếu có.

**Lưu ý khi diễn giải:** Một endpoint trả 200 khi gọi bằng `curl` nhưng bị script browser chặn bởi CORS không mâu thuẫn: `curl` không thực thi cùng mô hình bảo mật của trình duyệt. MockMvc có thể thấy CSP header nhưng không thể tự chứng minh script đã bị chặn.

## 8. Chuẩn hóa bằng chứng và mức độ tin cậy

Một báo cáo mạnh có bằng chứng **từ nhiều tầng khác nhau**, được liên kết bằng mã test và phiên bản triển khai.

| Loại bằng chứng | Ví dụ | Giá trị chứng minh | Giới hạn |
|---|---|---|---|
| Cấu hình nguồn | `SecurityFilterChain`, `SecurityWebFilterChain`, cấu hình proxy, properties cookie | Ý định bảo vệ và phạm vi matcher | Có thể khác cấu hình runtime hoặc bị proxy ghi đè |
| Kiểm thử Spring | MockMvc/WebTestClient có assertion | Hành vi filter chain/server trong môi trường test | Không thay cho browser/proxy production |
| HTTP raw capture | Status, CSP/HSTS/CORS/Set-Cookie của response sau proxy | Chính sách HTTP người dùng thật có thể nhận | Header hiện diện chưa chứng minh được hành vi browser |
| Browser capture | Console, Network, iframe blocking, cookie attributes | Hành vi thực khi browser áp dụng policy | Phụ thuộc browser, phiên, extension, trạng thái cache |
| Bằng chứng dữ liệu | Snapshot dữ liệu trước/sau POST, session replay | Cho thấy side effect được chặn hay cho phép đúng | Cần cách ly dữ liệu test, tránh dùng dữ liệu thật |
| Log/trace | Request ID, route được xử lý, lý do từ chối | Phân biệt CSRF/authz/firewall/CORS | Log có thể thiếu hoặc chứa dữ liệu nhạy cảm nếu không kiểm soát |

### 8.1. Mẫu hồ sơ một phép thử

Mỗi phép thử nên có một bản ghi theo cấu trúc:

~~~yaml
testId: B01
threatId: T01
environment: staging
appVersion: "<commit-or-build-id>"
configVersion: "<config-revision>"
timestampUtc: "<ISO-8601>"
precondition: "Đã xác thực bằng session cookie; email ban đầu đã ghi nhận"
action: "POST /account/email thiếu CSRF token"
expected:
  httpStatus: 403
  dataChanged: false
observed:
  httpStatus: "<status-thuc-te>"
  dataChanged: "<true-or-false-thuc-te>"
evidence:
  - "HTTP request/response đã ẩn cookie và token"
  - "Đối chiếu dữ liệu trước/sau thao tác"
verdict: "PASS|FAIL|INCONCLUSIVE"
residualRisk: "<mo-ta-rui-ro-con-lai>"
owner: "<nguoi-phu-trach>"
~~~

Đây là **mẫu điền kết quả**, không được thay placeholder bằng kết quả ước đoán. Bằng chứng cần lưu đúng thời điểm thực thi, bao gồm bản build, browser version nếu phù hợp và trạng thái cấu hình proxy. Khi dùng test trên production, chỉ dùng tài khoản và dữ liệu thử nghiệm được cho phép.

### 8.2. Không để lộ bí mật trong bằng chứng

Trước khi lưu HAR, ảnh chụp hoặc log:

- Che/mask giá trị `Cookie`, `Set-Cookie`, bearer token, CSRF token, session ID, email thật, query có dữ liệu nhạy cảm.
- Giữ lại **tên** của thuộc tính/header và kết quả so sánh cần thiết. Với kiểm tra session fixation, có thể ghi “ID trước và sau khác nhau” cùng hash/nhãn không thể dùng để xác thực, không cần giữ giá trị nguyên bản.
- Hạn chế quyền xem file chứng cứ, thời gian lưu và phạm vi chia sẻ. Không đưa credential hoặc token vào đường dẫn, commit hay ảnh chụp.

## 9. Phân tích kết quả và rủi ro còn lại

### 9.1. Quy tắc gán trạng thái

| Trạng thái | Khi nào sử dụng | Ví dụ |
|---|---|---|
| **PASS** | Tiền điều kiện chính xác, hành vi quan sát khớp kỳ vọng, có bằng chứng kiểm tra được | POST thiếu CSRF token trả 403 **và** dữ liệu không đổi; POST token đúng thành công |
| **FAIL** | Một điều kiện bảo mật quan trọng bị vi phạm, hoặc luồng hợp lệ bị chặn ngoài dự kiến | Origin lạ được CORS cấp quyền khi không được phép; iframe admin vẫn render |
| **INCONCLUSIVE** | Chưa đủ bằng chứng hoặc phép thử không đi qua đường cần đánh giá | Request bị 401 trước khi CSRF được kiểm tra; chỉ nhìn CSP header mà không chạy browser |
| **NOT_APPLICABLE** | Nguy cơ không áp dụng và có tài liệu chứng minh ranh giới | API không dùng cookie và chỉ chấp nhận bearer header: một số kịch bản CSRF cookie có thể không áp dụng |

Không gộp `NOT_APPLICABLE` với `PASS`. Một kiểm thử lỗi do script/fixture hoặc môi trường cũng không được tính là PASS; nên sửa tiền điều kiện và chạy lại.

### 9.2. Diễn giải ba tình huống điển hình

**Tình huống A — Header có, browser vẫn chạy script độc hại.** Cấu hình CSP chưa đạt mục tiêu T03. Có thể do `'unsafe-inline'`, thiếu directive, policy ở chế độ Report-Only, route HTML không nhận header, hoặc mã độc chạy trong script hợp lệ. Hãy ghi FAIL cho mục tiêu chống XSS cụ thể, tìm đúng nguyên nhân trước khi cập nhật policy.

**Tình huống B — Browser báo CORS blocked, nhưng dữ liệu vẫn bị thay đổi.** Đây không phải PASS của T01. CORS chỉ ngăn script của origin lạ đọc response; browser vẫn có thể gửi request gây side effect. Kiểm tra CSRF và authentication của route, trạng thái dữ liệu, SameSite cookie, và các đường gửi form đơn giản.

**Tình huống C — POST thiếu CSRF token trả 403 nhưng route đang yêu cầu login.** Nếu request không có session hợp lệ, 403 có thể không chứng minh CSRF đã hoạt động. Thực hiện lại với session đã xác thực và bằng chứng request có cookie hợp lệ nhưng thiếu token, so sánh với POST token đúng trong cùng phiên.

### 9.3. Mẫu bảng tổng hợp cho nhóm nghiệm thu

| Threat | Priority | Config verified | Positive | Negative | Browser/Edge | Verdict | Residual risk |
|---|---|---|---|---|---|---|---|
| T01 | Cao | Đã/Chưa | B02 | B01, B03 | Browser form | Chờ dữ liệu | Phạm vi exception CSRF |
| T02 | Cao | Đã/Chưa | B05, B06 | B04 | CORS browser | Chờ dữ liệu | Endpoint ngoài allowlist |
| T03 | Cao | Đã/Chưa | B08 | B07 | CSP Console | Chờ dữ liệu | Script từ nguồn được tin cậy |
| T04 | Trung bình | Đã/Chưa | Top-level load | B09 | iframe browser | Chờ dữ liệu | Frame route nằm ngoài chain |
| T05 | Cao | Đã/Chưa | HTTPS load | HTTP downgrade | Edge + browser | Chờ dữ liệu | Truy cập đầu tiên chưa có HSTS |
| T06/T08 | Cao | Đã/Chưa | Login mới | B11, B12 | Cookie/browser | Chờ dữ liệu | Các phiên/token ở dịch vụ khác |
| T07 | Cao | Đã/Chưa | URL chuẩn | B13 | Proxy + app | Chờ dữ liệu | Canonicalization theo hạ tầng |
| T09 | Cao | Đã/Chưa | B16 | B14, B15 | API trace | Chờ dữ liệu | Quyền theo từng tài nguyên |

Bảng trên là **khung báo cáo**; không được tự đánh dấu “Đã” hoặc PASS khi chưa có quan sát tương ứng. Rủi ro còn lại cần có chủ sở hữu và quyết định xử lý: sửa cấu hình, thay thiết kế, giảm phạm vi, tăng kiểm soát hoặc chấp nhận có căn cứ.

## 10. Khi nào kết luận đủ điều kiện triển khai?

Một bộ tiêu chí chấp nhận thực tế có thể gồm:

1. **Traceability:** tất cả nguy cơ quan trọng đều có owner, yêu cầu bảo mật, cấu hình chịu trách nhiệm và phép thử liên kết bằng ID.
2. **Coverage:** các luồng nhạy cảm (đăng nhập, thao tác có trạng thái, admin, logout, API dữ liệu, response HTML sau proxy) có cả phép thử hợp lệ và bất hợp lệ tương ứng.
3. **Behavior:** những mục ưu tiên cao có kết quả PASS với dữ liệu và browser/edge evidence phù hợp; không có FAIL nghiêm trọng chưa xử lý.
4. **Configuration consistency:** cấu hình trong source, runtime chain và header tại proxy nhất quán; các ngoại lệ CSRF/CORS/CSP được ghi rõ lý do.
5. **Residual risk:** giới hạn của mỗi kiểm thử được nêu và các lỗ hổng chưa xử lý có người phụ trách, kế hoạch và thời điểm xem lại.
6. **Reproducibility:** có app/config version, dữ liệu test, các bước tái hiện và log đã được ẩn thông tin nhạy cảm.

**Không dùng tỉ lệ test PASS đơn độc để quyết định.** Ví dụ, 19/20 test PASS vẫn không đạt nếu test còn lại chứng minh người dùng thường có thể thay đổi quyền admin. Ngược lại, một lỗi browser extension sinh violation CSP có thể được phân loại đúng và không nhất thiết là blocker nếu sản phẩm vẫn bảo vệ đúng kịch bản đã định nghĩa.

### 10.1. Checklist bàn giao theo môi trường

| Hạng mục | Local/CI | Staging | Production |
|---|---|---|---|
| Unit/integration test filter chain | Bắt buộc | Chạy lại theo bản build | Theo pipeline triển khai |
| Cookie/HSTS sau TLS edge | Có thể mô phỏng, không đủ kết luận cuối | Bắt buộc kiểm tra thật | Giám sát, regression sau thay proxy |
| CSP/CORS với trình duyệt thực | Smoke test | Kiểm thử đầy đủ luồng chính | Quan sát lỗi/violation và cảnh báo |
| Firewall path normalization | Test app/container | Test qua proxy thật | Theo dõi lỗi bất thường và regression |
| Session login/logout | Test có kiểm soát | Test phiên và dữ liệu | Canary/smoke trên tài khoản thử |
| Thay đổi bên thứ ba | Xem xét dependency | Kiểm tra nguồn/tính năng | Theo dõi phiên bản, origin, report |

## 11. Bài tập thực hành cuối bài

### Bài tập 1: Thẩm định một báo cáo “đã an toàn”

Đội triển khai cung cấp bốn bằng chứng:

- Mã cấu hình có `csrf(Customizer.withDefaults())`.
- Gọi một POST không có cookie và CSRF token nhận 403.
- Response `/login` có `Content-Security-Policy`.
- Gọi API từ `curl` trả 200 dù từ origin khác.

Hãy đánh giá mục nào đủ chứng minh T01, T02, T03; mục nào còn thiếu điều kiện. **Gợi ý:** POST không cookie chưa chứng minh chặn CSRF đối với phiên đăng nhập; CSP header chưa chứng minh browser thực thi chính sách; `curl` không áp dụng CORS như trình duyệt.

### Bài tập 2: Bổ sung bằng chứng theo mô hình nguy cơ

Chọn ba nguy cơ T01, T03, T09 và xây dựng cho mỗi nguy cơ:

1. Một giả thuyết tấn công đủ điều kiện.
2. Mảnh cấu hình chịu trách nhiệm và chain/route được áp dụng.
3. Một test âm tính, một test dương tính, quan sát trước/sau.
4. Một bằng chứng lấy từ tầng thích hợp (Spring test, browser hoặc HTTP sau proxy).
5. Một kết luận `PASS`, `FAIL` hay `INCONCLUSIVE` chỉ **sau khi** chạy phép thử.

### Bài tập 3: Điều tra thay đổi gây hồi quy

Sau khi CDN mới được đưa vào, script chính của trang hoạt động nhưng SDK phân tích ngừng gửi sự kiện. Browser Console báo vi phạm `connect-src`. Đồng thời một API endpoint trả 403 cho form hợp lệ.

Hãy truy vết hai lỗi độc lập: kiểm tra origin API ngoài danh sách CSP cho `connect-src`; với form, xác định đó là CSRF, authentication, authorization hay request bị HTTP firewall từ chối bằng cách quan sát request thực tế và logs. Không thêm hàng loạt origin vào CSP hoặc tắt CSRF chỉ để làm test xanh.

### Tiêu chí nộp bài

Bài nộp gồm một **bảng threat → control → test → evidence**, cấu hình rút gọn cho các chain/route liên quan, kịch bản test có điều kiện đầu vào, ảnh/chụp raw HTTP đã làm sạch thông tin nhạy cảm, và nhận xét rủi ro còn lại. Người đánh giá phải có thể chọn một threat ID bất kỳ và lần theo đầy đủ: mối nguy → cấu hình thực → phép thử → quan sát → kết luận.

## 12. Tài liệu tham khảo

- [Spring Security — Servlet Exploit Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/index.html)
- [Spring Security — Reactive Exploit Protection](https://docs.spring.io/spring-security/reference/reactive/exploits/index.html)
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [OWASP Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/)
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)
