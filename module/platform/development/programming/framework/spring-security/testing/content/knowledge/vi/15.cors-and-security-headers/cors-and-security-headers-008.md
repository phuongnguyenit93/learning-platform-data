# Kiểm tra header bảo vệ theo chính sách đã cấu hình

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive.

## 1. Vì sao cần kiểm thử security response headers?

Một ứng dụng Spring Security có thể xác thực và phân quyền đúng nhưng vẫn trả response thiếu các header bảo vệ cần thiết. Nếu response HTML không có Content Security Policy (CSP) phù hợp, bề mặt rủi ro từ nội dung script không tin cậy tăng lên. Nếu trang quản trị có thể bị website khác nhúng trong frame, người dùng có thể đối mặt với clickjacking. Nếu response nhạy cảm bị cache sai, dữ liệu cá nhân có thể còn lại trong bộ nhớ đệm dùng chung.

Spring Security cung cấp cơ chế ghi security headers vào response. Một số header cơ bản được bật mặc định; các chính sách cụ thể như CSP, Referrer-Policy hoặc Permissions-Policy thường cần cấu hình theo ứng dụng. Việc cấu hình writer chưa đủ: cần kiểm tra response thực tế qua filter chain, trên cả response thành công và response lỗi.

Trong module **SPRING_SECURITY_TESTING**, bài học này hướng dẫn kiểm chứng các header bảo vệ bằng **MockMvc** cho Servlet và **WebTestClient** cho Reactive, đồng thời phân biệt kiểm tra phía server với việc browser thực thi chính sách.

Sau bài này, bạn có thể:

- Nhận diện các security response headers thường dùng và mục đích của chúng.
- Phân biệt header Spring Security bật mặc định với header cần cấu hình.
- Viết assertion cho giá trị header và directive của CSP.
- Kiểm tra HSTS đúng điều kiện HTTPS và header trên response 401/403.
- Phát hiện header bị thiếu, bị ghi đè hoặc khác nhau giữa các SecurityFilterChain.

## 2. Các header bảo vệ thường gặp

| Header | Mục đích | Nội dung cần kiểm tra |
| --- | --- | --- |
| `X-Content-Type-Options` | Ngăn browser MIME sniffing trong các trường hợp không phù hợp | `nosniff` |
| `X-Frame-Options` | Hạn chế trang bị nhúng trong frame/iframe | `DENY` hoặc `SAMEORIGIN` theo policy |
| `Content-Security-Policy` | Giới hạn nguồn tải script, style, ảnh, frame và tài nguyên | `default-src`, `script-src`, `object-src`, `frame-ancestors` |
| `Strict-Transport-Security` | Yêu cầu browser dùng HTTPS cho các lần truy cập tiếp theo | `max-age`, `includeSubDomains`, `preload` nếu được dùng |
| `Referrer-Policy` | Kiểm soát thông tin URL được gửi qua Referer | Ví dụ `strict-origin-when-cross-origin` |
| `Permissions-Policy` | Hạn chế browser feature như camera, microphone, geolocation | Danh sách feature được bật/tắt |
| `Cache-Control` | Kiểm soát cache response, nhất là dữ liệu riêng tư | `no-store` hoặc policy cache phù hợp |
| `Cross-Origin-Opener-Policy` | Cô lập browsing context trong một số tình huống cross-origin | Ví dụ `same-origin` nếu tương thích |
| `Cross-Origin-Resource-Policy` | Kiểm soát việc tài nguyên được tải từ site/origin khác | `same-origin`, `same-site` hoặc `cross-origin` |

Không phải mọi header đều phù hợp với mọi ứng dụng. `Cross-Origin-Opener-Policy: same-origin` có thể ảnh hưởng OAuth popup hoặc cửa sổ thanh toán; `Cross-Origin-Resource-Policy: same-origin` có thể chặn việc nhúng ảnh từ site khác. Chỉ bật khi đã hiểu luồng tích hợp và kiểm tra trên browser.

## 3. Header mặc định và header cần cấu hình

Spring Security thêm một số security headers mặc định khi sử dụng cấu hình headers mặc định. Các header thường gặp gồm:

- `Cache-Control` với policy không cache nội dung nhạy cảm.
- `X-Content-Type-Options: nosniff`.
- `X-Frame-Options` theo chế độ mặc định của Spring Security.
- `Strict-Transport-Security` khi request được xem là HTTPS/secure.
- `X-XSS-Protection` ở các phiên bản có writer tương ứng; đây là cơ chế cũ, không thay thế CSP.

Các header như **Content-Security-Policy**, **Referrer-Policy** hoặc **Permissions-Policy** cần được cấu hình theo policy ứng dụng. Không nên mặc định rằng chỉ bật Spring Security là đã có CSP phù hợp.

Spring Security cho phép cấu hình qua DSL `HttpSecurity.headers(...)` trong Servlet và `ServerHttpSecurity.headers(...)` trong Reactive. Có thể giữ các header mặc định rồi bổ sung chính sách cần thiết, hoặc vô hiệu hóa một writer cụ thể khi có lý do rõ ràng. Tránh tắt toàn bộ headers chỉ để xử lý một header đơn lẻ.

### 3.1. Policy mẫu

Giả sử ứng dụng có trang quản trị và API:

- Không cho trang khác nhúng ứng dụng: `X-Frame-Options: DENY` và CSP `frame-ancestors 'none'`.
- Chặn MIME sniffing: `X-Content-Type-Options: nosniff`.
- Chỉ tải tài nguyên từ origin của ứng dụng theo CSP cơ bản.
- Chỉ cho phép form submit về cùng origin.
- Không cho plugin/object nhúng: `object-src 'none'`.
- Dùng `Referrer-Policy: strict-origin-when-cross-origin`.
- Dùng HSTS trên HTTPS với `max-age=31536000`; chỉ bật `includeSubDomains` khi mọi subdomain liên quan đã sẵn sàng HTTPS.
- Tắt camera, microphone và geolocation nếu ứng dụng không cần.

CSP mẫu:

~~~http
Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'
~~~

Đây là policy khởi đầu để minh họa, không phải policy hoàn chỉnh cho mọi SPA. Ứng dụng có thể cần nguồn script/style, API, font, ảnh hoặc nonce/hash cụ thể. Hãy thiết kế CSP theo tài nguyên thực tế và kiểm tra browser Console trước khi áp dụng enforcement trên production.

## 4. Cấu hình security headers trong Servlet

Ví dụ dùng Spring Security DSL để giữ header mặc định và bổ sung CSP, Referrer-Policy, frame policy, HSTS cùng Permissions-Policy:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.StaticHeadersWriter;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter.ReferrerPolicy;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .headers(headers -> headers
                .contentTypeOptions(withDefaults())
                .frameOptions(frame -> frame.deny())
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; " +
                    "base-uri 'self'; " +
                    "object-src 'none'; " +
                    "frame-ancestors 'none'; " +
                    "form-action 'self'"))
                .referrerPolicy(referrer -> referrer
                    .policy(ReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN))
                .httpStrictTransportSecurity(hsts -> hsts
                    .maxAgeInSeconds(31536000)
                    .includeSubDomains(false))
                .addHeaderWriter(new StaticHeadersWriter(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=()"))
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").authenticated()
                .anyRequest().permitAll())
            .build();
    }
}
~~~

Các điểm cần lưu ý:

1. `contentTypeOptions` ghi `X-Content-Type-Options: nosniff`.
2. `frameOptions(frame -> frame.deny())` yêu cầu browser không nhúng trang trong frame.
3. `contentSecurityPolicy` cấu hình CSP enforcement; browser mới là thành phần thực thi directive.
4. `referrerPolicy` giới hạn thông tin referrer.
5. HSTS chỉ được ghi trên request secure/HTTPS theo cơ chế của writer; test bằng HTTP thường sẽ không thấy header này.
6. `StaticHeadersWriter` bổ sung Permissions-Policy theo giá trị tĩnh. Nếu policy khác theo endpoint, cần thiết kế writer/filter phù hợp.

HSTS `includeSubDomains` được đặt false trong ví dụ. Chỉ bật true khi mọi subdomain trong phạm vi domain đều hỗ trợ HTTPS ổn định. `preload` cũng là quyết định triển khai riêng, không nên bật chỉ để làm test pass.

## 5. Kiểm thử Servlet với MockMvc

### 5.1. Kiểm tra header trên response thành công

Dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để request đi qua filter chain thực của ứng dụng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicResponseCoSecurityHeaders() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("object-src 'none'")))
            .andExpect(header().string(
                "Referrer-Policy",
                "strict-origin-when-cross-origin"))
            .andExpect(header().string(
                "Permissions-Policy",
                containsString("camera=()")));
    }
}
~~~

Test giả định endpoint `/public` tồn tại và trả thành công. Khi áp dụng vào dự án, thay bằng endpoint công khai đang có. Assertion cần phản ánh policy đã thống nhất của ứng dụng, không sao chép nguyên giá trị mẫu nếu ứng dụng cần CSP khác.

### 5.2. HSTS phải được kiểm tra với request HTTPS

HSTS chỉ có ý nghĩa khi server nhận request secure. Với MockMvc, có thể đánh dấu request là secure:

~~~java
@Test
void hstsDuocGhiChoSecureRequest() throws Exception {
    mvc.perform(get("/public").secure(true))
        .andExpect(status().isOk())
        .andExpect(header().string(
            "Strict-Transport-Security",
            containsString("max-age=31536000")));
}
~~~

Một test HTTP thường không nên đòi HSTS. Trong production có TLS termination ở reverse proxy, cần xác minh ứng dụng nhận diện request gốc là HTTPS qua cấu hình forwarded headers đáng tin cậy; đồng thời kiểm tra response cuối cùng qua proxy.

### 5.3. Header phải xuất hiện trên response lỗi phù hợp

Security headers hữu ích cả trên response 401/403. Ví dụ endpoint yêu cầu đăng nhập:

~~~java
@Test
void unauthorizedResponseVanCoSecurityHeaders() throws Exception {
    mvc.perform(get("/admin/reports"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().string(
            "X-Content-Type-Options", "nosniff"))
        .andExpect(header().string(
            "X-Frame-Options", "DENY"));
}
~~~

Kỳ vọng `401` giả định ứng dụng dùng entry point trả 401 (ví dụ HTTP Basic). Nếu dùng form login, có thể nhận redirect 302. Hãy giữ assertion về security headers trên response thực tế và chọn status phù hợp với cơ chế xác thực.

### 5.4. Kiểm tra CSP theo directive

~~~java
@Test
void cspCoCacDirectiveBatBuoc() throws Exception {
    mvc.perform(get("/public"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            "Content-Security-Policy",
            containsString("default-src 'self'")))
        .andExpect(header().string(
            "Content-Security-Policy",
            containsString("object-src 'none'")))
        .andExpect(header().string(
            "Content-Security-Policy",
            containsString("frame-ancestors 'none'")));
}
~~~

Có thể kiểm tra directive theo từng assertion để test failure nói rõ policy nào bị thiếu. Nếu CSP được tạo động theo nonce, không so sánh toàn bộ chuỗi header với literal cố định; kiểm tra phần directive tĩnh và định dạng nonce riêng.

## 6. Cấu hình và kiểm thử Reactive

Với WebFlux, Spring Security cấu hình security headers thông qua `ServerHttpSecurity.headers(...)`. Ví dụ cho các header cốt lõi:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.XFrameOptionsServerHttpHeadersWriter;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .headers(headers -> headers
                .contentTypeOptions(Customizer.withDefaults())
                .frameOptions(frame -> frame
                    .mode(XFrameOptionsServerHttpHeadersWriter.Mode.DENY))
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; object-src 'none'; " +
                    "frame-ancestors 'none'; base-uri 'self'"))
                .hsts(hsts -> hsts
                    .maxAge(Duration.ofDays(365))
                    .includeSubdomains(false))
            )
            .authorizeExchange(auth -> auth
                .pathMatchers("/admin/**").authenticated()
                .anyExchange().permitAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

API cấu hình header có thể khác nhẹ giữa các phiên bản Spring Security. Hãy dùng phiên bản Spring Security của dự án làm chuẩn khi áp dụng. Nếu phiên bản không có writer hoặc method cụ thể, bổ sung header qua cơ chế `ServerHttpHeadersWriter` tương ứng và vẫn kiểm thử response cuối cùng.

Kiểm thử bằng WebTestClient:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveSecurityHeadersTests {

    @Autowired
    WebTestClient client;

    @Test
    void responseCoSecurityHeaders() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff")
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY")
            .expectHeader().valueMatches(
                "Content-Security-Policy",
                ".*object-src 'none'.*");
    }

    @Test
    void response401VanCoHeaderBaoVe() {
        client.get().uri("/admin/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                "X-Content-Type-Options", "nosniff")
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY");
    }
}
~~~

Test HSTS cần chạy trên request/server được xem là HTTPS. Nếu WebTestClient bind trực tiếp vào application context không tạo secure request, không dùng assertion HSTS như trên một cách máy móc. Dùng test server HTTPS hoặc cấu hình request secure phù hợp với phiên bản framework; sau đó xác minh response qua TLS endpoint.

## 7. Kiểm tra header theo loại response và endpoint

Không chỉ kiểm tra một endpoint duy nhất. Header có thể khác theo route, filter chain hoặc response được tạo bởi thành phần khác.

| Nhóm response | Header cần kiểm tra | Lưu ý |
| --- | --- | --- |
| Trang công khai | nosniff, frame, CSP, Referrer-Policy | Baseline của ứng dụng |
| API JSON | nosniff, cache policy phù hợp | CSP thường có ý nghĩa hơn với HTML |
| Trang quản trị | CSP chặt, frame deny, no-store nếu có dữ liệu nhạy cảm | Xác nhận cả 401/403 |
| Response HTTPS | HSTS | Không đòi header trên HTTP không secure |
| Tài nguyên tĩnh | nosniff, cache policy, CSP phù hợp | Asset versioned có thể có cache riêng |
| Download file | nosniff, Content-Disposition, cache policy | Không chỉ dựa vào CSP |
| Response lỗi | Security headers baseline | Exception handler/custom response có thể đi đường khác |

Security headers thường được ghi bởi filter nên có thể xuất hiện cả khi controller không được gọi. Tuy nhiên, response do reverse proxy, CDN, servlet container hoặc error handler ngoài Spring tạo ra có thể không đi qua cùng filter chain. Cần test các đường response quan trọng.

## 8. Những điểm cần cẩn trọng khi kiểm thử

### 8.1. CSP là policy có ngữ nghĩa, không phải chuỗi tùy ý

Test kiểm tra header CSP có chứa `default-src 'self'` chỉ chứng minh directive đó có trong response. Nó không chứng minh toàn bộ policy không có directive mâu thuẫn hoặc nguồn nguy hiểm khác. Cần rà soát:

- `script-src`: nguồn JavaScript; cân nhắc nonce/hash thay cho `unsafe-inline`.
- `style-src`: nguồn CSS; một số framework có inline style.
- `img-src`: nguồn ảnh, có thể cần `data:` hoặc CDN.
- `connect-src`: API, WebSocket hoặc telemetry.
- `object-src 'none'`: vô hiệu hóa plugin/object.
- `frame-ancestors`: kiểm soát ai được nhúng trang.
- `base-uri` và `form-action`: hạn chế base URL và đích form.

CSP có thể triển khai trước ở chế độ `Content-Security-Policy-Report-Only` để thu thập vi phạm trước khi bật enforcement. Test cần phân biệt header report-only và header enforcement; một header không thay thế header kia.

### 8.2. HSTS chỉ có tác dụng khi browser nhận qua HTTPS

HSTS được browser lưu khi nhận từ secure connection. Test MockMvc dùng `.secure(true)` kiểm tra điều kiện request ở tầng Servlet, không thực hiện TLS handshake. Test qua HTTPS server hoặc gateway mới kiểm tra được đường truyền TLS thực tế. Không phát HSTS cho HTTP response chỉ để thỏa assertion.

### 8.3. X-Frame-Options và frame-ancestors

`X-Frame-Options` có các giá trị thông dụng `DENY` và `SAMEORIGIN`. CSP `frame-ancestors` cho phép policy chi tiết hơn. Nếu đặt cả hai, hãy đảm bảo chúng nhất quán; browser hiện đại thường ưu tiên CSP frame-ancestors khi hỗ trợ. Không kiểm tra header này chỉ bằng một trang API JSON nếu mục tiêu là chống clickjacking trên trang HTML nhạy cảm.

### 8.4. Header bảo vệ có thể khác theo loại nội dung

CSP của trang HTML không nhất thiết áp dụng giống nhau cho API JSON hoặc file tải xuống. Có thể dùng policy theo endpoint, nhưng phải kiểm tra không tạo lỗ hổng ở đường dẫn nhạy cảm. Với nhiều SecurityFilterChain, bảo đảm từng chain có header writers phù hợp; chain đầu tiên match request mới là chain thực thi.

### 8.5. Không dựa vào X-XSS-Protection cũ

`X-XSS-Protection` là cơ chế cũ, không thay thế CSP và không nên được xem là giải pháp XSS hiện đại. Chính sách nên tập trung vào output encoding, sanitization, template safety và CSP được thiết kế đúng.

## 9. Bảng kiểm thử đề xuất

| Mã | Request | Assertion |
| --- | --- | --- |
| HDR-01 | GET trang công khai | nosniff, frame, CSP, Referrer-Policy |
| HDR-02 | GET trang quản trị đã xác thực | Policy CSP và frame theo yêu cầu |
| HDR-03 | GET trang quản trị chưa xác thực | 401/redirect phù hợp và security headers vẫn hiện diện |
| HDR-04 | Request HTTPS | HSTS có max-age và includeSubDomains đúng |
| HDR-05 | API JSON | nosniff và cache policy theo yêu cầu |
| HDR-06 | Download file | nosniff, Content-Disposition và cache policy |
| HDR-07 | CSP | Có đủ directive bắt buộc, không xuất hiện directive bị cấm |
| HDR-08 | Permissions-Policy | Browser feature không cần dùng bị hạn chế |
| HDR-09 | Response 403 | Header baseline không bị mất khi authorization từ chối |
| HDR-10 | Nhiều SecurityFilterChain | Header policy của chain được chọn đúng với path |

Nên có ít nhất một test kiểm tra **giá trị chính xác** cho header đơn giản, một test kiểm tra **directive bắt buộc** cho CSP, một test HSTS trên HTTPS và một test response lỗi.

## 10. Chẩn đoán khi test thất bại

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Thiếu toàn bộ security headers | Filter chain không chạy, headers bị disable hoặc response do proxy tạo | Xác nhận MockMvc/WebTestClient có security filter |
| Thiếu HSTS | Request không được xem là secure; TLS terminate tại proxy nhưng forwarded headers sai | Test HTTPS và kiểm tra cấu hình proxy |
| Thiếu CSP | Chưa cấu hình CSP writer hoặc route đi qua chain khác | Kiểm tra chain matcher và headers DSL |
| Có hai CSP header | Nhiều filter/proxy cùng phát policy | Kiểm tra header writers ở app và gateway |
| CSP chặn script hợp lệ | Policy thiếu nguồn, nonce/hash hoặc directive phù hợp | Xem browser Console/Report-Only |
| Iframe bị chặn dù cần nhúng | X-Frame-Options DENY hoặc frame-ancestors không cho parent | Rà soát yêu cầu tích hợp và allowlist parent |
| Permissions-Policy không có | Chưa thêm writer hoặc gateway xóa header | Kiểm tra response cuối tuyến |
| Cache-Control không đúng | Header mặc định hoặc filter khác ghi đè | Kiểm tra cache writer và policy endpoint |
| Header có trên 200 nhưng thiếu trên 401/403 | Response lỗi đi qua đường xử lý khác | Test error path và exception handling |

MockMvc/WebTestClient xác minh header mà ứng dụng trả về. Browser E2E cần thiết khi muốn xác nhận CSP, HSTS, frame policy hoặc Permissions-Policy được browser thực thi như mong đợi. Với HSTS, cần môi trường HTTPS thực; với CSP, quan sát Console hoặc report endpoint để phát hiện vi phạm runtime.

## 11. Bài thực hành và tiêu chí hoàn thành

Một ứng dụng có trang `/admin/reports` và API `/api/reports`. Nhóm yêu cầu:

- `X-Content-Type-Options: nosniff`.
- `X-Frame-Options: DENY` cho trang quản trị.
- CSP có `default-src 'self'`, `object-src 'none'` và `frame-ancestors 'none'`.
- `Referrer-Policy: strict-origin-when-cross-origin`.
- HSTS `max-age=31536000` trên HTTPS.
- Permissions-Policy tắt camera, microphone và geolocation.
- Response quản trị nhạy cảm không được lưu cache theo policy đã thống nhất.

Hãy thực hiện:

1. Cấu hình header writers trong Spring Security Servlet hoặc Reactive theo phiên bản dự án.
2. Viết MockMvc/WebTestClient test cho response 200 và response 401/403.
3. Kiểm tra từng header bằng giá trị hoặc directive cụ thể; không chỉ kiểm tra tồn tại.
4. Đánh dấu request secure khi test HSTS; bổ sung kiểm thử HTTPS thực nếu hệ thống có TLS termination.
5. Kiểm tra policy trên tất cả SecurityFilterChain áp dụng cho trang/API liên quan.
6. Nếu CSP có nonce/hash hoặc nhiều nguồn tài nguyên, test phần tĩnh và xác minh runtime bằng browser.
7. Nếu gateway/CDN có thêm hoặc xóa header, kiểm tra response cuối tuyến.

**Tiêu chí hoàn thành:** bộ test chứng minh response thực sự chứa header bảo vệ theo policy đã cấu hình, bao gồm response lỗi và request HTTPS; CSP được kiểm tra theo directive, HSTS được kiểm tra đúng điều kiện secure, và các header khác không bị filter/proxy ghi đè ngoài ý muốn.

**Điểm cần nhớ:** bật header writer mới là bước cấu hình. Chỉ khi test qua filter chain thực và đối chiếu đúng giá trị trên nhiều loại response, bạn mới có bằng chứng ứng dụng đang phát policy bảo vệ mà nhóm đã yêu cầu.
