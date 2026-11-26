# CSP, chống nhúng khung và các tùy biến của ứng dụng

> **Chương:** CORS và header bảo vệ  
> **Module:** SPRING_SECURITY_TESTING — kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng spring-security-test trên ứng dụng Servlet và Reactive.

## 1. Mục tiêu: kiểm soát nội dung được tải và nơi được phép nhúng ứng dụng

Một ứng dụng Spring có trang đăng nhập, bảng điều khiển và API. Nếu một trang độc hại có thể nhúng bảng điều khiển vào iframe rồi lừa người dùng bấm nút, ứng dụng có nguy cơ bị clickjacking. Nếu trang cho phép tải script từ nguồn không tin cậy, kẻ tấn công có thể lợi dụng lỗ hổng injection để chạy mã trong origin của ứng dụng.

Hai nhóm response header thường được dùng để giảm các rủi ro này:

- **Content Security Policy (CSP):** giới hạn nguồn và loại tài nguyên mà browser được phép tải hoặc thực thi, đồng thời kiểm soát ai có thể nhúng trang.
- **Frame protection:** ngăn website khác nhúng giao diện nhạy cảm bằng X-Frame-Options và/hoặc CSP frame-ancestors.

Spring Security có thể phát các header này thông qua security header writers. Tuy nhiên, CSP cần được thiết kế theo tài nguyên thực tế của từng ứng dụng. Một policy quá lỏng làm giảm hiệu quả bảo vệ; policy quá chặt có thể làm hỏng script, style, ảnh, font, API, OAuth popup hoặc tích hợp thanh toán.

Trong module **SPRING_SECURITY_TESTING**, mục tiêu là kiểm tra header thực sự được phát qua filter chain, giá trị và directive đúng policy, các response lỗi không làm mất header, và browser thực thi CSP/frame policy như mong muốn.

Sau bài học, bạn có thể:

1. Giải thích vai trò của CSP, X-Frame-Options và frame-ancestors.
2. Phân biệt frame-src với frame-ancestors.
3. Thiết kế CSP theo script, style, image, font, API, form và frame của ứng dụng.
4. Tùy biến policy theo endpoint, CDN, nonce/hash và chế độ Report-Only.
5. Kiểm thử Servlet bằng MockMvc, Reactive bằng WebTestClient và kiểm chứng hành vi browser bằng E2E.

## 2. Content Security Policy hoạt động như thế nào?

CSP là một tập quy tắc browser áp dụng cho tài liệu. Server gửi policy qua response header:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Browser đọc policy và dùng nó để quyết định tài nguyên nào được phép tải hoặc thực thi. Ví dụ:

- Trang chỉ tải script từ origin của chính nó.
- Trang chỉ tải ảnh từ origin của ứng dụng và một CDN đã tin cậy.
- Không cho phép plugin/object.
- Không cho phép trang từ bất kỳ origin nào nhúng trang hiện tại.
- Chỉ cho phép form submit về origin đã chỉ định.

CSP không tự sửa dữ liệu đầu vào, không thay thế output encoding và không làm cho HTML injection trở nên an toàn. Nó là một lớp phòng vệ bổ sung; ứng dụng vẫn cần template escaping, validation và sanitization đúng cách.

### 2.1. Directive quan trọng

| Directive | Kiểm soát | Ví dụ |
| --- | --- | --- |
| **default-src** | Nguồn mặc định cho nhiều loại tài nguyên khi không có directive chuyên biệt | default-src 'self' |
| **script-src** | Script được tải hoặc thực thi | script-src 'self' |
| **style-src** | CSS và style | style-src 'self' |
| **img-src** | Ảnh | img-src 'self' https://images.example-cdn.test |
| **font-src** | Font | font-src 'self' https://fonts.example-cdn.test |
| **connect-src** | Fetch, XHR, WebSocket, EventSource và các kết nối tương tự | connect-src 'self' https://api.example.test wss://socket.example.test |
| **media-src** | Audio/video | media-src 'self' |
| **object-src** | Plugin và object/embed | object-src 'none' |
| **frame-src** | Những nguồn mà trang hiện tại được phép tải vào iframe | frame-src https://pay.example.test |
| **frame-ancestors** | Những origin được phép nhúng trang hiện tại | frame-ancestors 'self' https://portal.example.test |
| **base-uri** | Nguồn hợp lệ cho phần tử base | base-uri 'self' |
| **form-action** | Đích gửi form | form-action 'self' https://login.example.test |
| **upgrade-insecure-requests** | Yêu cầu browser nâng cấp URL tài nguyên không an toàn lên HTTPS | upgrade-insecure-requests |

### 2.2. frame-src và frame-ancestors không thay thế nhau

Hai directive có chiều kiểm soát ngược nhau:

- **frame-src** trả lời: trang của tôi được phép nhúng nội dung từ đâu?
- **frame-ancestors** trả lời: những trang nào được phép nhúng trang của tôi?

Ví dụ một cổng quản trị cần nhúng trang thanh toán bên ngoài:

~~~http
Content-Security-Policy: default-src 'self'; frame-src https://checkout.example-pay.test; frame-ancestors 'none'
~~~

Policy cho phép trang quản trị tải iframe thanh toán, nhưng không cho website khác nhúng chính trang quản trị. Đây là hai quyết định độc lập.

### 2.3. Fallback và nguồn tài nguyên

**default-src 'self'** là fallback cho nhiều loại tài nguyên nếu không có directive cụ thể. Khi thêm **script-src** hoặc **img-src**, directive cụ thể sẽ quyết định loại tài nguyên đó; không nên giả định browser luôn cộng các nguồn từ default-src.

Các source expression thường gặp:

- **'self'**: origin hiện tại.
- **'none'**: không cho phép nguồn nào.
- **https:**: mọi nguồn HTTPS; khá rộng, không nên dùng nếu có thể allowlist host cụ thể.
- **https://cdn.example.test**: một host cụ thể.
- **'nonce-...'**: script/style có nonce phù hợp với response.
- **'sha256-...'**: nội dung inline khớp hash đã khai báo.

Các keyword như 'self', 'none', 'unsafe-inline' và 'unsafe-eval' cần đặt trong dấu nháy đơn. Host nguồn và scheme không đặt trong dấu nháy.

## 3. X-Frame-Options và chống clickjacking

X-Frame-Options là response header cũ nhưng vẫn hữu ích để tương thích với browser. Hai giá trị phổ biến:

~~~http
X-Frame-Options: DENY
~~~

Không cho trang được nhúng trong frame.

~~~http
X-Frame-Options: SAMEORIGIN
~~~

Chỉ cho phép frame từ cùng origin.

**ALLOW-FROM** đã lỗi thời và không được browser hiện đại hỗ trợ nhất quán. Nếu cần cho phép một tập parent origin cụ thể, hãy dùng CSP frame-ancestors.

### 3.1. frame-ancestors là chính sách chi tiết hơn

Ví dụ chỉ cho portal cùng origin và một cổng đối tác tin cậy nhúng:

~~~http
Content-Security-Policy: frame-ancestors 'self' https://partner.example.test
~~~

Chỉ những ancestor phù hợp với policy mới được phép nhúng tài liệu. Browser kiểm tra toàn bộ chuỗi ancestor; nếu một ancestor không được cho phép, tài liệu bị chặn trong frame.

**frame-ancestors** phải được gửi bằng HTTP response header; directive này không có tác dụng khi khai báo trong thẻ meta. X-Frame-Options và CSP frame-ancestors nên được thiết kế nhất quán. Browser hiện đại hỗ trợ CSP thường ưu tiên frame-ancestors, nhưng X-Frame-Options vẫn có thể ảnh hưởng tới browser cũ.

### 3.2. Khi ứng dụng cần được nhúng bởi origin ngoài

Nếu trang quản trị cần nhúng bởi https://portal.example.test, policy có thể là:

~~~http
Content-Security-Policy: default-src 'self'; frame-ancestors 'self' https://portal.example.test
~~~

X-Frame-Options không có giá trị tương đương để chỉ định một origin bên ngoài tùy ý. Nếu response đồng thời có X-Frame-Options DENY hoặc SAMEORIGIN, browser cũ có thể từ chối nhúng dù CSP cho phép. Hãy quyết định hỗ trợ browser nào, và cấu hình frame header phù hợp cho endpoint đó. Không tắt frame protection toàn ứng dụng chỉ để phục vụ một trang cần nhúng.

## 4. Thiết kế CSP theo nhu cầu thực tế của ứng dụng

Một CSP an toàn không phải lúc nào cũng chỉ có default-src 'self'. Hãy lập danh sách tài nguyên mà trang thực sự sử dụng.

Ví dụ ứng dụng SPA có:

- Script và style từ origin của ứng dụng.
- Ảnh từ CDN.
- Font từ font host đã phê duyệt.
- API và WebSocket tới backend.
- Iframe thanh toán từ một nhà cung cấp.
- Form đăng nhập gửi về identity provider.

Policy minh họa:

~~~http
Content-Security-Policy: default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self' https://login.example.test; script-src 'self'; style-src 'self'; img-src 'self' https://images.example-cdn.test; font-src 'self' https://fonts.example-cdn.test; connect-src 'self' https://api.example.test wss://socket.example.test; frame-src https://checkout.example-pay.test
~~~

Không sao chép nguyên policy này nếu ứng dụng dùng inline script, CSS framework, analytics, OAuth popup hoặc tài nguyên khác. Hãy kiểm tra browser Console và network requests để bổ sung đúng nguồn cần thiết.

### 4.1. Tránh các nguồn quá rộng

Những cấu hình sau làm CSP yếu đi đáng kể:

- **script-src \*** cho phép script từ quá nhiều nguồn.
- **script-src 'unsafe-inline'** cho phép inline script không có nonce/hash.
- **script-src 'unsafe-eval'** cho phép các cơ chế đánh giá chuỗi thành mã.
- **default-src https:** cho phép mọi host HTTPS, không chỉ host đã tin cậy.

Nếu framework cũ cần inline script/style, hãy đánh giá nonce hoặc hash và nâng cấp cách render. Không thêm unsafe-inline chỉ để xóa cảnh báo CSP trong Console.

### 4.2. Nonce cho script inline

Nonce là một giá trị ngẫu nhiên, khó đoán, được tạo mới cho mỗi response. Server đưa nonce vào CSP:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-r4nd0mPerResponseValue'
~~~

Và gắn cùng nonce vào script được phép:

~~~html
<script nonce="r4nd0mPerResponseValue">
  window.appConfig = { mode: "production" };
</script>
~~~

Nonce phải giống nhau giữa header và phần tử script trong cùng response, nhưng không được tái sử dụng cố định qua nhiều response. Nếu nonce bị đoán hoặc tái sử dụng lâu dài, lợi ích bảo vệ giảm mạnh.

Với Spring MVC/Thymeleaf, một cách triển khai là tạo nonce trước khi render view, lưu vào request attribute, dùng cùng giá trị trong template và CSP header writer. Đảm bảo filter tạo nonce chạy trước phần ghi header/render view; không cache HTML chứa nonce theo cách khiến nonce cũ được phục vụ cho response khác.

Ví dụ luồng sinh nonce an toàn:

~~~java
byte[] nonceBytes = new byte[32];
secureRandom.nextBytes(nonceBytes);
String nonce = Base64.getEncoder().encodeToString(nonceBytes);

request.setAttribute("cspNonce", nonce);
// Template đọc cspNonce; CSP header writer dùng cùng nonce.
~~~

Sử dụng SecureRandom và Base64 theo cách biểu diễn phù hợp. Không log nonce hoặc đặt nonce vào dữ liệu có thể bị cache dùng chung. Đoạn mã trên minh họa luồng dữ liệu; ứng dụng cần khai báo và inject SecureRandom, tích hợp request attribute với template engine, và dùng một header writer đọc đúng nonce của request.

### 4.3. Hash cho inline script tĩnh

Nếu inline script không thay đổi, có thể dùng hash SHA-256 của chính nội dung script. Browser chỉ thực thi đoạn inline khớp hash đã khai báo. Bất kỳ thay đổi whitespace hoặc nội dung nào cũng làm hash thay đổi; pipeline build cần cập nhật hash khi source thay đổi.

Nonce phù hợp nội dung động theo response; hash phù hợp đoạn script tĩnh, ổn định. Cả hai đều tốt hơn việc mở rộng unsafe-inline không có kiểm soát.

## 5. Report-Only để triển khai CSP an toàn

CSP enforcement có thể làm hỏng tính năng nếu policy chưa phản ánh đủ nguồn tài nguyên. Trước khi chặn thật, ứng dụng có thể phát:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; object-src 'none'; frame-ancestors 'none'
~~~

Browser báo cáo vi phạm nhưng không chặn tài nguyên theo policy Report-Only. Cách này giúp nhóm thu thập lỗi trong staging hoặc một giai đoạn giám sát trước khi bật enforcement.

Một số điểm cần phân biệt:

- **Content-Security-Policy:** policy được thực thi, tài nguyên vi phạm có thể bị chặn.
- **Content-Security-Policy-Report-Only:** policy chỉ báo cáo, không chặn theo policy đó.
- **report-uri** là cơ chế cũ; **report-to** sử dụng Reporting API và cần cấu hình endpoint báo cáo tương ứng.
- Báo cáo CSP có thể chứa URL, directive và thông tin về trang; endpoint nhận báo cáo cần được bảo vệ khỏi spam và không ghi dữ liệu nhạy cảm không cần thiết.

Có thể phát đồng thời một policy enforcement và một policy Report-Only để quan sát policy chặt hơn trước khi bật. Hai policy được đánh giá độc lập; Report-Only không nới lỏng policy enforcement.

## 6. Cấu hình CSP và frame protection trong Spring Security Servlet

Ví dụ dùng Spring Security DSL. Policy này dành cho một ứng dụng không cần nhúng trong iframe:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; " +
                    "base-uri 'self'; " +
                    "object-src 'none'; " +
                    "frame-ancestors 'none'; " +
                    "form-action 'self'; " +
                    "script-src 'self'; " +
                    "style-src 'self'"))
                .frameOptions(frame -> frame.deny()))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            .build();
    }
}
~~~

Spring Security phát CSP và X-Frame-Options qua header writers. Browser thực thi policy; test phía server cần xác nhận response mang đúng header.

### 6.1. Cấu hình Report-Only

Có thể dùng chế độ Report-Only khi triển khai policy thử nghiệm:

~~~java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
        .reportOnly()))
~~~

Đặt Report-Only trong môi trường quan sát trước khi chuyển sang enforcement. Khi cần cả policy hiện hành và policy thử nghiệm, cần cấu hình hai response header riêng một cách có chủ đích; không thay policy enforcement bằng Report-Only rồi cho rằng nội dung đã được bảo vệ.

### 6.2. Tùy biến theo endpoint

Một ứng dụng có thể có trang quản trị không cho nhúng, nhưng một trang widget cần cho phép portal tin cậy nhúng. Không nên dùng một policy rộng cho toàn bộ ứng dụng nếu yêu cầu khác nhau theo route.

Có thể tổ chức nhiều SecurityFilterChain với matcher cụ thể và thứ tự rõ ràng, hoặc dùng header writer/filter tùy chỉnh chọn policy theo request. Nếu có nhiều chain, kiểm tra chain đầu tiên khớp request và xác nhận policy được áp dụng đúng path. Đừng để một chain catch-all đứng trước chain chuyên biệt.

Ví dụ policy mong muốn:

| Endpoint | CSP frame-ancestors | Frame policy |
| --- | --- | --- |
| /admin/** | 'none' | DENY |
| /portal/widget/** | 'self' https://portal.example.test | Cần đánh giá tương thích X-Frame-Options |
| /public/** | Theo nhu cầu nội dung | Chọn policy tối thiểu phù hợp |

Đây là yêu cầu policy; cấu hình thực tế có thể dùng chain riêng hoặc writer tùy chỉnh. Nếu cho phép external ancestor, không phát X-Frame-Options mâu thuẫn trên endpoint đó cho các browser mà ứng dụng hỗ trợ.

## 7. Cấu hình CSP và frame protection trong Reactive

Với WebFlux, cấu hình qua ServerHttpSecurity.headers(...):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; base-uri 'self'; " +
                    "object-src 'none'; frame-ancestors 'none'; " +
                    "form-action 'self'"))
                .frameOptions(frame -> frame
                    .mode(XFrameOptionsServerHttpHeadersWriter.Mode.DENY)))
            .authorizeExchange(auth -> auth
                .anyExchange().permitAll())
            .build();
    }
}
~~~

API DSL có thể khác theo phiên bản Spring Security của dự án. Hãy dùng phiên bản dependency làm chuẩn khi áp dụng. Nguyên tắc kiểm thử không đổi: response từ chain Reactive phải chứa CSP/frame header theo policy, kể cả khi request bị từ chối bởi authentication/authorization nếu response đi qua chain đó.

## 8. Kiểm thử Servlet bằng MockMvc

### 8.1. Kiểm tra CSP và X-Frame-Options trên response thành công

Dùng @SpringBootTest và @AutoConfigureMockMvc để request đi qua security filter chain:

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
class CspHeaderTests {

    @Autowired
    MockMvc mvc;

    @Test
    void responseCoCspVaFrameProtection() throws Exception {
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
                containsString("frame-ancestors 'none'")))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"));
    }
}
~~~

Thay /public bằng endpoint thực của ứng dụng. Assertion tách theo directive giúp thông báo rõ policy nào thiếu. Không so sánh toàn bộ chuỗi nếu thứ tự directive không phải một phần hợp đồng.

### 8.2. Kiểm tra Report-Only tách biệt enforcement

~~~java
@Test
void responseCoCspReportOnlyTheoPolicy() throws Exception {
    mvc.perform(get("/csp-report-only"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            "Content-Security-Policy-Report-Only",
            containsString("object-src 'none'")));
}
~~~

Test này chỉ xác nhận server phát header Report-Only. Nó không chứng minh browser đã gửi report hoặc endpoint báo cáo hoạt động. Nếu ứng dụng không dùng Report-Only, không cần tạo test cho header này.

### 8.3. Security headers trên response lỗi

~~~java
@Test
void unauthorizedResponseVanCoCspVaFrameProtection() throws Exception {
    mvc.perform(get("/admin/reports"))
        .andExpect(status().isUnauthorized())
        .andExpect(header().exists("Content-Security-Policy"))
        .andExpect(header().string("X-Frame-Options", "DENY"));
}
~~~

Kỳ vọng 401 giả định ứng dụng có entry point trả 401; form login có thể redirect. Điều cần kiểm tra là header protection vẫn xuất hiện trên response được tạo bởi security chain.

### 8.4. Kiểm tra endpoint cho phép parent cụ thể

Nếu widget cho phép portal nhúng, kiểm tra đúng policy của endpoint:

~~~java
@Test
void widgetChoPhepPortalDuocChiDinh() throws Exception {
    mvc.perform(get("/portal/widget"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            "Content-Security-Policy",
            containsString(
                "frame-ancestors 'self' https://portal.example.test")));
}
~~~

Nếu endpoint này không cho external frame, hãy kiểm tra 'none' hoặc policy tương ứng. Không chỉ kiểm tra header tồn tại; giá trị cần phản ánh đúng yêu cầu tích hợp.

## 9. Kiểm thử Reactive bằng WebTestClient

Với WebFlux, dùng WebTestClient gắn với application context và Spring Security:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCspHeaderTests {

    @Autowired
    WebTestClient client;

    @Test
    void responseCoCspVaFrameProtection() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueMatches(
                "Content-Security-Policy",
                ".*default-src 'self'.*")
            .expectHeader().valueMatches(
                "Content-Security-Policy",
                ".*frame-ancestors 'none'.*")
            .expectHeader().valueEquals(
                "X-Frame-Options", "DENY");
    }

    @Test
    void response401VanCoCsp() {
        client.get().uri("/admin/reports")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists("Content-Security-Policy");
    }
}
~~~

Các test giả định ứng dụng Reactive có endpoint và entry point tương ứng. Nếu test client được dựng thủ công, bảo đảm nó đã gắn SecurityWebFilterChain; test chỉ bind controller không chứng minh security headers đã chạy.

## 10. Kiểm tra browser thực thi CSP và frame policy

MockMvc/WebTestClient xác minh server phát header; browser E2E mới xác minh browser thực thi policy. Có thể dùng Playwright để mở một trang kiểm thử và quan sát hành vi.

### 10.1. CSP chặn script ngoài allowlist

Trang test cần có một script từ host không được phép. Trong browser test, lắng nghe sự kiện securitypolicyviolation:

~~~typescript
import { test, expect } from "@playwright/test";

test("CSP chan script ngoai allowlist", async ({ page }) => {
  await page.goto("https://app.example.test/csp-probe");

  const violation = await page.evaluate(() => {
    return new Promise(resolve => {
      document.addEventListener("securitypolicyviolation", event => {
        resolve({
          directive: event.violatedDirective,
          blockedURI: event.blockedURI
        });
      }, { once: true });

      const script = document.createElement("script");
      script.src = "https://untrusted.example.test/probe.js";
      document.head.appendChild(script);
    });
  });

  expect(violation.directive).toContain("script-src");
});
~~~

Trang probe phải trả CSP enforcement có directive script-src không cho phép host không tin cậy. Nếu dùng Report-Only, browser chỉ báo cáo vi phạm và vẫn có thể tải script; test phải phân biệt hai chế độ.

### 10.2. Trang bị chặn khi nhúng từ origin không được phép

Một trang attacker test có thể tạo iframe tới ứng dụng:

~~~html
<iframe src="https://app.example.test/admin/reports"></iframe>
~~~

Browser test truy cập trang attacker, quan sát lỗi frame/CSP trong Console hoặc kiểm tra nội dung frame không thể được tải/đọc theo policy. Không chỉ dựa vào việc frame element tồn tại: browser vẫn tạo node iframe dù navigation bên trong bị chặn. Hãy kiểm tra event vi phạm, lỗi navigation hoặc nội dung trang theo browser engine.

### 10.3. Parent được phép vẫn có thể nhúng

Nếu ứng dụng cho phép https://portal.example.test trong frame-ancestors, cần một test positive từ đúng origin đó. Nếu chỉ test negative, policy có thể vô tình chặn tất cả parent. Browser E2E cần kiểm tra cả parent được phép và parent bị cấm.

## 11. CSP và frame policy theo tùy biến ứng dụng

### 11.1. CDN và dịch vụ bên ngoài

Nếu trang sử dụng CDN, font provider, analytics, API hoặc WebSocket, chỉ thêm host cần thiết vào directive tương ứng. Không đưa một host vào default-src chỉ vì một loại tài nguyên cần nó; dùng directive cụ thể như img-src, font-src hoặc connect-src.

### 11.2. SPA và API

SPA có thể tải script từ origin frontend, gọi API ở origin khác và mở WebSocket. CSP của trang frontend cần connect-src cho API/WebSocket; CORS của API là policy riêng để browser cho phép JavaScript đọc response. **CSP connect-src và CORS bổ sung nhau**, không thay thế nhau.

### 11.3. OAuth popup và thanh toán

Một số luồng đăng nhập dùng popup, cửa sổ khác origin hoặc iframe từ nhà cung cấp. Các policy như frame-ancestors, frame-src và COOP có thể ảnh hưởng luồng này. Kiểm thử login/payment trên browser thật sau khi thay đổi header; test response header đơn thuần không chứng minh popup hoặc redirect hoạt động.

### 11.4. Nhiều policy CSP

Nếu response có nhiều CSP header, browser thực thi tất cả policy enforcement; các policy không được hợp nhất theo kiểu lấy nguồn rộng nhất. Kết quả thường là hạn chế giao nhau: tài nguyên phải đáp ứng mọi policy đang được thực thi. Một proxy thêm CSP thứ hai có thể vô tình làm trang không tải được.

Vì vậy, kiểm tra số lượng và nội dung CSP header ở response cuối tuyến. Nếu gateway và Spring cùng quản lý CSP, thống nhất một nơi sở hữu policy hoặc xác định rõ cách kết hợp.

### 11.5. Nhiều SecurityFilterChain

Nếu trang admin và widget có policy khác nhau, nhiều chain có thể giúp tách cấu hình. Kiểm tra thứ tự matcher, tránh chain rộng bắt request trước chain chuyên biệt và xác nhận endpoint thuộc đúng chain. Với một route cần policy động theo tenant hoặc request, dùng writer tùy chỉnh có kiểm soát thay vì tạo quá nhiều chain.

## 12. Ma trận kiểm thử đề xuất

| Mã | Tình huống | Kiểm thử server | Kiểm thử browser |
| --- | --- | --- | --- |
| CSP-01 | Trang công khai | CSP có directive bắt buộc | Tài nguyên hợp lệ tải được |
| CSP-02 | Script ngoài allowlist | Header không cho host lạ | Browser chặn script |
| CSP-03 | Report-Only | Có header Report-Only, không nhầm enforcement | Browser ghi nhận violation nhưng không chặn theo policy đó |
| CSP-04 | Nonce | Header có nonce theo response | Script có nonce chạy; script không có nonce bị chặn |
| CSP-05 | CDN | Directive chỉ chứa CDN đã duyệt | Asset từ CDN tải được |
| FRAME-01 | Trang admin | frame-ancestors 'none', XFO DENY | Parent bên ngoài không nhúng được |
| FRAME-02 | Widget đối tác | frame-ancestors chứa parent cụ thể | Parent được phép nhúng thành công |
| FRAME-03 | Parent lạ | Không có origin ngoài allowlist | Browser chặn nhúng |
| CHAIN-01 | Admin và widget khác policy | Header theo đúng chain/path | Cả hai luồng hoạt động theo yêu cầu |
| PROXY-01 | Response qua gateway | CSP không trùng hoặc bị ghi đè sai | Browser nhận policy cuối cùng |

## 13. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Trang trắng sau khi bật CSP | Script/style/API/font bị chặn | Đọc Console và bổ sung nguồn cụ thể cần thiết |
| Inline script không chạy | Thiếu nonce/hash hoặc policy vẫn cấm inline | Dùng nonce/hash; tránh mở unsafe-inline |
| Iframe thanh toán không tải | frame-src chưa cho phép provider | Thêm đúng host vào frame-src |
| Website đối tác không nhúng được widget | frame-ancestors thiếu parent hoặc XFO mâu thuẫn | Kiểm tra cả CSP và X-Frame-Options |
| CSP Report-Only không chặn script | Đây là hành vi đúng của Report-Only | Chuyển sang enforcement sau khi đánh giá |
| CSP có nhiều header | Spring và proxy cùng phát policy | Kiểm tra response cuối tuyến và thống nhất chủ sở hữu |
| MockMvc pass nhưng browser vẫn lỗi | Header đúng ở app nhưng gateway/browser policy khác | Kiểm tra Network, Console và response cuối |
| Header không có trên 401/403 | Response lỗi đi qua chain/handler khác | Kiểm tra SecurityFilterChain và error path |
| Nonce bị cache hoặc lặp lại | HTML/header được cache sai hoặc nonce tĩnh | Tạo nonce mới mỗi response và điều chỉnh cache |
| Widget được nhúng ở mọi nơi | frame-ancestors quá rộng hoặc không có | Giới hạn parent origin cụ thể |

## 14. Bài thực hành và tiêu chí hoàn thành

Một ứng dụng có ba trang:

- /admin/reports: không được nhúng trong frame.
- /portal/widget: chỉ portal https://portal.example.test được nhúng.
- /app: tải script từ origin ứng dụng, ảnh từ CDN và gọi API/WebSocket đã phê duyệt.

Hãy thực hiện:

1. Thiết kế CSP riêng cho script, style, image, font, connect, form, object và frame theo tài nguyên thực tế.
2. Cấu hình frame-ancestors 'none' và frame protection cho trang admin.
3. Cấu hình widget cho phép đúng portal; xử lý X-Frame-Options nhất quán với browser mục tiêu.
4. Dùng Report-Only để quan sát policy mới trước khi bật enforcement nếu ứng dụng có nhiều tài nguyên.
5. Nếu có inline script, chọn nonce hoặc hash; không dùng nonce tĩnh và không cache HTML chứa nonce dùng chung.
6. Viết MockMvc test cho CSP, X-Frame-Options và response lỗi trên Servlet; viết WebTestClient tương ứng cho Reactive.
7. Viết browser E2E xác nhận script không tin cậy bị chặn, admin không nhúng được và widget chỉ nhúng được từ parent đã cho phép.
8. Kiểm tra response qua gateway để phát hiện CSP header trùng hoặc bị ghi đè.

**Tiêu chí hoàn thành:** bạn chứng minh được CSP và frame policy được cấu hình đúng trên response, policy thay đổi theo endpoint có chủ đích, test server xác nhận header qua filter chain và browser E2E xác nhận hành vi thực thi.

**Điểm cần nhớ:** CSP là policy browser thực thi, còn MockMvc/WebTestClient kiểm tra policy server phát ra. X-Frame-Options và frame-ancestors bảo vệ theo những cách liên quan nhưng không đồng nhất; hãy thiết kế chúng cùng yêu cầu nhúng thực tế của từng trang và kiểm tra cả positive lẫn negative cases.
