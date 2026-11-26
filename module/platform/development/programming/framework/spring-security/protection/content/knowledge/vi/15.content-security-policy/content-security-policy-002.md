# ContentSecurityPolicyHeaderWriter và chỉ thị do ứng dụng cung cấp

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — bảo vệ HTTP và trình duyệt trong Spring Security, bao gồm CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và session; thực hành trên Servlet lẫn Reactive, kiểm thử tình huống tấn công web và chẩn đoán xung đột khi triển khai.

## 1. Vấn đề cần giải quyết

Một trang web có thể chứa script nội bộ, thư viện giao diện từ CDN, ảnh do người dùng tải lên, API ở domain riêng và WebSocket phục vụ thông báo thời gian thực. Trình duyệt cần biết **nguồn nào được phép tải hoặc thực thi**. Đó là mục đích của **Content Security Policy (CSP)**, một chính sách mà ứng dụng gửi qua HTTP header để trình duyệt áp dụng khi xử lý trang.

Trong Spring Security Servlet, `ContentSecurityPolicyHeaderWriter` là thành phần chuyên ghi header CSP vào HTTP response. Điểm cần hiểu của bài này là: **Spring Security cung cấp cơ chế xuất header; ứng dụng chịu trách nhiệm quyết định chuỗi chỉ thị CSP phù hợp với tài nguyên và rủi ro của chính mình.** Spring Security không tự biết một trang cần CDN, nonce, WebSocket hoặc iframe nào và không tự tạo chính sách CSP riêng cho kiến trúc của bạn.

Ví dụ, ứng dụng gửi:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'
~~~

Trình duyệt dùng các *directive* trong giá trị header để giới hạn hành vi của tài liệu. `script-src 'self'` cho phép tải script từ **cùng origin**, nhưng không cho phép JavaScript nội tuyến thông thường. `object-src 'none'` từ chối nội dung nhúng dạng plugin. `base-uri 'self'` giới hạn URL của `<base>`, còn `form-action 'self'` giới hạn đích submit form.

Mục tiêu sau bài học:

1. Mô tả chức năng, đầu vào và đầu ra của `ContentSecurityPolicyHeaderWriter`.
2. Tự xây dựng chuỗi directive dựa trên nhu cầu của ứng dụng và hiểu các điểm dễ cấu hình sai.
3. Cấu hình CSP bằng DSL hoặc bằng writer trực tiếp cho Spring Security Servlet; biết API tương ứng trên Reactive/WebFlux.
4. Thiết lập Report-Only, kiểm thử header, quan sát trình duyệt và xử lý các xung đột triển khai.

## 2. ContentSecurityPolicyHeaderWriter làm gì?

Trong nhánh Spring Security dành cho Servlet, lớp nằm ở:

~~~java
org.springframework.security.web.header.writers.ContentSecurityPolicyHeaderWriter
~~~

Lớp này hiện thực giao diện `HeaderWriter`. Khi cơ chế ghi security headers của Spring Security được thực thi, writer đưa giá trị chính sách vào HTTP response. Tùy chế độ, tên header là:

| Chế độ | Header HTTP | Tác dụng |
|---|---|---|
| Thực thi | `Content-Security-Policy` | Trình duyệt kiểm tra và chặn hành vi vi phạm directive có hiệu lực |
| Theo dõi | `Content-Security-Policy-Report-Only` | Trình duyệt đánh giá, ghi nhận vi phạm nhưng không chặn chỉ vì chính sách Report-Only này |

Writer **không** phân tích template để tìm các host đang dùng, không tự chọn `script-src`, không tạo nonce và không kiểm tra nội dung người dùng nhập. Nó chỉ lấy **giá trị directive do ứng dụng cấu hình** để ghi header. Công việc diễn ra trên phía server; việc diễn giải và áp dụng CSP là trách nhiệm của trình duyệt.

~~~mermaid
flowchart TD
    A[Ứng dụng xác định nguồn và quy tắc CSP] --> B[Tạo chuỗi policy directives]
    B --> C[Spring Security Headers / CSP HeaderWriter]
    C --> D[HTTP response kèm CSP header]
    D --> E[Trình duyệt nhận tài liệu HTML]
    E --> F{Tài nguyên hoặc hành vi phù hợp CSP?}
    F -- Có --> G[Tiếp tục kiểm tra và xử lý bình thường]
    F -- Không --> H[Chặn khi là policy thực thi]
    F -- Report-Only --> I[Ghi nhận vi phạm nhưng không chặn bởi policy đó]
~~~

**Lưu ý:** CSP không được Spring Security bật sẵn với một chính sách ứng dụng cụ thể như các header mặc định khác. Bạn phải chủ động cấu hình để response chứa CSP. Ngay cả khi có header, CSP vẫn là lớp phòng vệ bổ sung; ứng dụng cần escape dữ liệu theo ngữ cảnh, dùng template an toàn, làm sạch HTML không đáng tin cậy khi cần và bảo vệ session/CSRF theo đúng mục đích.

### Những API cần nhớ ở Servlet

| Thành phần | Chức năng |
|---|---|
| `new ContentSecurityPolicyHeaderWriter(policyDirectives)` | Tạo writer với chuỗi directive do ứng dụng cung cấp |
| `setPolicyDirectives(policyDirectives)` | Thiết lập/thay đổi chuỗi directive của writer |
| `setReportOnly(true)` | Chọn xuất header `Content-Security-Policy-Report-Only` |
| `writeHeaders(request, response)` | Ghi security header trên Servlet response; thông thường Spring Security gọi qua cơ chế HeaderWriterFilter |
| `HttpSecurity.headers(...).contentSecurityPolicy(...)` | Cấu hình tương đương qua Spring Security DSL, không cần tự tạo writer |
| `HttpSecurity.headers(...).addHeaderWriter(writer)` | Đăng ký một `HeaderWriter` tùy chỉnh trong Servlet security chain |

Không phải trường hợp nào cũng cần tạo writer bằng tay. **DSL là lựa chọn đơn giản** nếu chỉ cần chính sách cố định; cách tạo writer trực tiếp hữu ích khi muốn cấu hình tập trung hoặc gắn một `HeaderWriter` theo cơ chế sẵn có của ứng dụng.

## 3. Ứng dụng cung cấp chính xác những gì?

Đầu vào chính của writer là **một chuỗi directive**, với từng directive ngăn cách bằng dấu chấm phẩy:

~~~text
default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'
~~~

Định dạng chung:

~~~text
<directive-name> <source-expression-1> <source-expression-2>; <directive-name> <source-expression-1>
~~~

Ví dụ, `script-src 'self' https://static.example.com` có nghĩa script có thể được tải từ cùng origin của trang hoặc đúng origin `https://static.example.com`. Các giá trị `'self'`, `'none'`, `'unsafe-inline'`, `'nonce-...'` được viết trong dấu nháy đơn như cú pháp CSP yêu cầu. `'self'` so sánh **origin** (scheme, hostname và port theo quy tắc của trình duyệt), không tự động tin cậy mọi subdomain.

### Các directive cần chọn theo chức năng ứng dụng

| Directive | Giới hạn gì? | Ví dụ lý do ứng dụng cần khai báo |
|---|---|---|
| `default-src` | Giá trị dự phòng cho một số chỉ thị tải tài nguyên | Mặc định chỉ dùng nguồn cùng origin |
| `script-src` | Các nguồn và cách thực thi JavaScript | Cho phép script chính chủ, từ chối script chèn và nguồn ngoài |
| `style-src` | Các stylesheet và kiểu nội tuyến theo quy tắc tương ứng | Cấp quyền cho CSS của ứng dụng hoặc CDN đã chọn |
| `img-src` | Nguồn ảnh | Cho phép ảnh tĩnh, kho ảnh hoặc `data:` nếu thực sự cần |
| `font-src` | Nguồn font | Cho phép font tự phục vụ hoặc font host đáng tin |
| `connect-src` | Kết nối từ script như fetch, XHR và WebSocket | Mở đúng API, endpoint `wss://...` cần thiết |
| `object-src` | Nguồn của `object`/`embed` | Thường dùng `'none'` để giảm bề mặt plugin |
| `base-uri` | Giá trị thẻ `<base>` | Tránh đổi cách phân giải đường dẫn tương đối tới nguồn ngoài |
| `form-action` | Đích gửi biểu mẫu | Giới hạn form đến các endpoint ứng dụng tin cậy |
| `frame-ancestors` | Ai được phép nhúng **trang hiện tại** vào frame | Ngăn ứng dụng bị nhúng vào trang không mong muốn |
| `frame-src` | Những frame mà trang hiện tại có thể tải | Chỉ cho phép ứng dụng nhúng các trang cần thiết |

**Không phải directive nào cũng kế thừa `default-src`.** Đặc biệt, `base-uri`, `form-action` và `frame-ancestors` cần khai báo riêng. Vì vậy, `default-src 'none'` **không tự động** chặn mọi đích submit form hoặc mọi trang nhúng ứng dụng.

### Ví dụ thiết kế từ yêu cầu thật

Giả sử trang dashboard phục vụ HTML, JavaScript và CSS từ `https://app.example.com`, gọi API tại `https://api.example.com` và WebSocket tại `wss://events.example.com`. Ứng dụng không dùng script bên ngoài, không cho trang khác nhúng và chỉ submit form về chính origin của trang.

Một chính sách khởi đầu:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self' https://api.example.com wss://events.example.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
~~~

Chính sách trên là **ví dụ thiết kế**, không phải cấu hình áp dụng nguyên xi cho mọi sản phẩm. Ở đây:

- `script-src 'self'` từ chối script nội tuyến và script từ domain ngoài; script trên chính origin vẫn được phép nếu thỏa các kiểm tra khác.
- `connect-src` liệt kê API và WebSocket theo đúng origin/protocol của chúng; các trình duyệt có thể xử lý `'self'` với WebSocket khác nhau, nên khai báo `wss://events.example.com` rõ ràng.
- `form-action 'self'` chỉ cho form gửi đến cùng origin; nếu form phải gửi đến hệ thống thanh toán khác, cần xem xét riêng đích đó.
- `frame-ancestors 'none'` từ chối mọi trang nhúng dashboard vào frame.
- Nếu dùng CSS nội tuyến, chính sách này có thể chặn CSS đó; việc trang bị lỗi không phải lý do để tự động thêm `'unsafe-inline'`.

Trường hợp này cũng cho thấy **CSP và CORS giải quyết hai vấn đề khác nhau**. `connect-src` có thể cho phép frontend gửi `fetch` tới API nhưng trình duyệt vẫn có thể không cho frontend đọc response nếu server API chưa trả CORS header phù hợp. Ngược lại, CORS cho phép frontend đọc response không có nghĩa CSP sẽ cho phép tạo kết nối tới origin đó.

## 4. Cấu hình bằng Spring Security Servlet DSL

Với cấu hình lambda DSL trên một ứng dụng Spring MVC/Servlet, cách phổ biến nhất là khai báo CSP trong `SecurityFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    private static final String CSP_POLICY =
            "default-src 'self'; " +
            "script-src 'self'; " +
            "style-src 'self'; " +
            "img-src 'self'; " +
            "font-src 'self'; " +
            "connect-src 'self' https://api.example.com " +
                "wss://events.example.com; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(CSP_POLICY)
            )
        );
        return http.build();
    }
}
~~~

Ở đây, `policyDirectives(CSP_POLICY)` chính là điểm **ứng dụng cung cấp chỉ thị**. Spring Security dùng giá trị đó để tạo header CSP trên những response đi qua security chain phù hợp. Nó không tự mở `script-src` cho một CDN mới khi frontend bắt đầu sử dụng thư viện từ CDN đó.

Trong ứng dụng có **nhiều `SecurityFilterChain`**, hãy xác định chain nào xử lý request đến trang HTML. Nếu chỉ cấu hình CSP ở chain của `/api/**` trong khi trang được phục vụ bằng chain khác, response HTML có thể không nhận được CSP.

## 5. Dùng ContentSecurityPolicyHeaderWriter trực tiếp trong Servlet

Có thể tạo writer và đăng ký qua `addHeaderWriter`. Đây là **cách cấu hình thay thế** cho DSL ở mục 4; chọn một trong hai ví dụ khi triển khai một chính sách CSP duy nhất.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ContentSecurityPolicyHeaderWriter;

@Configuration
class SecurityConfig {

    private static final String CSP_POLICY =
            "default-src 'self'; " +
            "script-src 'self'; " +
            "style-src 'self'; " +
            "connect-src 'self'; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        ContentSecurityPolicyHeaderWriter writer =
                new ContentSecurityPolicyHeaderWriter(CSP_POLICY);

        http.headers(headers -> headers.addHeaderWriter(writer));
        return http.build();
    }
}
~~~

Sau khi một response đi qua chain có writer, trình duyệt có thể nhận:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
~~~

Nếu code muốn thay đổi giá trị trong giai đoạn cấu hình, writer cung cấp `setPolicyDirectives(String)`. Việc gọi setter trên một writer được chia sẻ **sau khi ứng dụng đang phục vụ request** không phải cơ chế phù hợp để chọn CSP riêng cho từng người dùng hoặc từng response. Khi cần tạo nonce/hay tùy biến theo request, hãy thiết kế một cơ chế tạo chính sách nhất quán theo request thay vì thay đổi trạng thái chung của writer.

### Chuyển sang chế độ Report-Only

Vẫn dùng writer dành cho Servlet:

~~~java
ContentSecurityPolicyHeaderWriter writer =
        new ContentSecurityPolicyHeaderWriter(
            "default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'"
        );
writer.setReportOnly(true);

http.headers(headers -> headers.addHeaderWriter(writer));
~~~

Khi đó writer xuất:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'
~~~

Report-Only rất hữu ích khi chính sách mới có thể chặn thư viện hoặc tính năng đang dùng. Trình duyệt vẫn cho phép các hành vi chỉ vi phạm chính sách này, đồng thời có thể hiển thị cảnh báo vi phạm trong DevTools. **Report-Only không có nghĩa mọi trình duyệt tự gửi report về server**: muốn thu thập tập trung cần cấu hình cơ chế reporting và endpoint nhận phù hợp, đồng thời kiểm tra hỗ trợ của trình duyệt.

Nếu response có cả header CSP **thực thi** lẫn **Report-Only**, các giới hạn của CSP thực thi vẫn có hiệu lực; Report-Only không “mở lại” tài nguyên đã bị CSP thực thi chặn.

### Khi nào chọn writer trực tiếp?

| Nhu cầu | Cách phù hợp |
|---|---|
| Chỉ thiết lập policy cố định cho một security chain | DSL `contentSecurityPolicy(...).policyDirectives(...)` |
| Đã có cơ chế đăng ký các đối tượng `HeaderWriter` tùy chỉnh | Tạo `ContentSecurityPolicyHeaderWriter` và `addHeaderWriter(...)` |
| Muốn thử policy trong Report-Only | Có thể đặt `setReportOnly(true)` trên writer |
| Policy chứa nonce động theo HTTP response | Cần thiết kế tạo nonce và phát header/HTML đồng bộ cho từng request; writer có policy cố định không tự xử lý |
| Ứng dụng chạy WebFlux | Sử dụng API security header của Reactive, không đưa Servlet writer vào Reactive chain |

## 6. Spring Security Reactive/WebFlux dùng API tương ứng

`ContentSecurityPolicyHeaderWriter` ở trên thuộc **Servlet stack** và làm việc với `HttpServletRequest`/`HttpServletResponse`. Với Spring WebFlux, cấu hình CSP qua `ServerHttpSecurity` và `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                    "default-src 'self'; " +
                    "script-src 'self'; " +
                    "style-src 'self'; " +
                    "connect-src 'self' https://api.example.com; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "form-action 'self'; " +
                    "frame-ancestors 'none'"
                )
            )
        );
        return http.build();
    }
}
~~~

Ở cả hai stack, điểm chung là **ứng dụng sở hữu chuỗi policy**, Spring Security đưa chuỗi đó vào response, còn trình duyệt thực thi. Khác biệt là API filter chain và loại request/response ở server.

Một tình huống dễ nhầm: backend WebFlux chỉ trả JSON ở `api.example.com`, còn HTML được phục vụ từ `app.example.com` bằng CDN hoặc frontend server riêng. Header CSP trên response JSON của API **không thiết lập CSP cho tài liệu HTML do frontend server trả về**. Cần triển khai policy trên response tài liệu HTML tại origin thực tế của frontend.

## 7. Policy tĩnh, nonce động và hash: ai chịu trách nhiệm?

Writer tĩnh rất phù hợp với ứng dụng sử dụng file JavaScript và CSS riêng biệt. Nhưng nhiều frontend framework hoặc trang HTML server-side rendering có script nội tuyến hợp lệ. Khi đó chỉ dùng `script-src 'self'` có thể khiến chức năng ngừng hoạt động.

Có ba hướng xử lý, theo mức độ thường ưu tiên:

1. Chuyển script nội tuyến thành file JavaScript từ một nguồn được CSP cho phép và gắn handler bằng JavaScript thay cho thuộc tính `onclick`.
2. Với script nội tuyến ổn định, dùng **CSP hash** của đúng nội dung script, ví dụ `'sha256-...'`. Khi nội dung script đổi, hash phải đổi theo.
3. Với script nội tuyến động, dùng **nonce** khó đoán và khác nhau cho từng HTTP response. Đặt nonce trong `script-src` và thuộc tính `nonce` của những thẻ script tin cậy.

Ví dụ dưới đây chỉ để chỉ ra **cấu trúc khớp nhau**, không dùng giá trị nonce minh họa làm nonce cố định trong hệ thống:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'nonce-EXAMPLE_RANDOM_PER_RESPONSE'; object-src 'none'; base-uri 'none'
~~~

~~~html
<script nonce="EXAMPLE_RANDOM_PER_RESPONSE">
    initializePage();
</script>
~~~

Để triển khai nonce an toàn, ứng dụng phải:

- Tạo giá trị mạnh, không thể đoán trước, mới cho **mỗi response** chứa HTML cần nó.
- Đưa cùng giá trị vào CSP header và các thẻ `script` được tin cậy của **đúng response đó**.
- Bảo đảm bước tạo nonce diễn ra trước khi template render và trước khi response commit.
- Tránh cache HTML/header khiến giá trị nonce lặp lại hoặc không còn khớp.
- Không cho dữ liệu do người dùng kiểm soát quyết định nonce, chèn nonce vào thẻ script của họ, hoặc đưa secret/nonce mẫu cố định vào code sản xuất.

**ContentSecurityPolicyHeaderWriter không tự tạo nonce.** Cấu hình `policyDirectives("script-src 'nonce-...'")` với một chuỗi hằng không phải cách triển khai nonce an toàn. Nếu cần nonce theo request, nên tách rõ trách nhiệm: thành phần tạo nonce theo request; view/template dùng nonce đó; thành phần trả CSP header dùng cùng nonce; mọi bước được thử với HTTP response thực tế.

Với ứng dụng có yêu cầu nâng cao về CSP, `'strict-dynamic'` có thể được cân nhắc cùng nonce/hash để điều chỉnh sự tin cậy với script được nạp động. Điều này đòi hỏi hiểu luồng nạp script và kiểm thử tương thích; không cần đưa vào mặc định nếu chưa có nhu cầu.

## 8. Kiểm thử chính writer và response thực tế

Có hai cấp độ cần kiểm chứng: (1) writer xuất đúng header khi được gọi; (2) **response HTML mà người dùng thực sự nhận** có CSP như kỳ vọng. Sau đó cần kiểm thử bằng trình duyệt vì test phía server không thể chứng minh một payload đã bị CSP chặn.

### 8.1. Unit test cho writer Servlet

Ví dụ với JUnit 5 và `spring-test`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.web.header.writers.ContentSecurityPolicyHeaderWriter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class ContentSecurityPolicyHeaderWriterTest {

    @Test
    void writesEnforcedPolicy() {
        String policy = "default-src 'self'; script-src 'self'; object-src 'none'";
        ContentSecurityPolicyHeaderWriter writer =
                new ContentSecurityPolicyHeaderWriter(policy);

        MockHttpServletResponse response = new MockHttpServletResponse();
        writer.writeHeaders(new MockHttpServletRequest(), response);

        assertEquals(policy, response.getHeader("Content-Security-Policy"));
        assertNull(response.getHeader("Content-Security-Policy-Report-Only"));
    }

    @Test
    void writesReportOnlyPolicy() {
        String policy = "default-src 'self'; script-src 'self'";
        ContentSecurityPolicyHeaderWriter writer =
                new ContentSecurityPolicyHeaderWriter(policy);
        writer.setReportOnly(true);

        MockHttpServletResponse response = new MockHttpServletResponse();
        writer.writeHeaders(new MockHttpServletRequest(), response);

        assertEquals(
                policy,
                response.getHeader("Content-Security-Policy-Report-Only")
        );
        assertNull(response.getHeader("Content-Security-Policy"));
    }
}
~~~

Test này kiểm tra **hành vi của writer**. Nó không chứng minh writer đã được đăng ký vào security chain, cũng không chứng minh CSP thực sự giảm thiểu XSS trên giao diện.

### 8.2. Integration test cho HTTP response

Trong ứng dụng Servlet có route HTML phù hợp với test (ví dụ `/dashboard`), dùng MockMvc với Spring Security filters:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

mockMvc.perform(get("/dashboard"))
       .andExpect(header().string(
           "Content-Security-Policy",
           containsString("script-src 'self'")
       ));
~~~

Nếu chạy trên WebFlux với WebTestClient:

~~~java
webTestClient.get()
    .uri("/dashboard")
    .exchange()
    .expectHeader()
    .valueMatches("Content-Security-Policy", ".*script-src 'self'.*");
~~~

Các test trên giả định route tồn tại và môi trường test đã bật cấu hình Spring Security. Khi một response chuyển hướng tới login hoặc được reverse proxy chỉnh sửa, phải kiểm tra **response HTML cuối cùng** thay vì chỉ nhìn một response trung gian.

### 8.3. Xác minh bằng browser

Một quy trình kiểm thử thực hành:

1. Mở trang ở Network của DevTools, chọn request tài liệu HTML và xem `Response Headers` để chắc chắn có `Content-Security-Policy` đúng giá trị.
2. Trong môi trường kiểm thử có kiểm soát, chèn `<img src="x" onerror="alert('xss')">` vào một điểm render HTML được thiết kế cho bài thực hành; với `script-src 'self'`, handler nội tuyến thông thường phải bị CSP chặn.
3. Thử tải script từ một origin không có trong `script-src` và xem thông báo từ chối trong Console.
4. Thử tải file JS từ cùng origin để xác nhận policy không chặn tài nguyên hợp lệ; nếu có `nonce` hoặc các policy khác, đọc đầy đủ thông báo vi phạm trước khi kết luận.
5. Nếu dùng Report-Only, quan sát vi phạm được báo nhưng hành vi có thể vẫn diễn ra; chuyển sang policy thực thi sau khi đã giải quyết vi phạm hợp lệ.

Không nên dùng kết quả chạy lệnh tùy ý trong **DevTools Console** làm bằng chứng duy nhất về XSS: cách browser xử lý thao tác từ Console có thể khác với script thực sự được chèn vào DOM.

### 8.4. Đọc header từ command line

~~~bash
curl -I http://localhost:8080/dashboard
~~~

Tùy server, route và cách xử lý HTTP HEAD, kết quả có thể khác response GET. Khi cần chắc chắn, dùng GET và xem response header của request thực tế (ví dụ `curl -i http://localhost:8080/dashboard` trong môi trường thực hành). Phải kiểm tra **đúng origin cung cấp HTML**; một CSP trả từ API không thể áp đặt chính sách cho trang HTML do một origin khác phục vụ.

## 9. Chẩn đoán lỗi do chỉ thị ứng dụng cung cấp

Vì ứng dụng tự đặt directive, sai sót thường xuất hiện khi thay đổi frontend, deploy qua proxy hoặc bổ sung tích hợp mới.

| Biểu hiện | Điều cần kiểm tra | Hướng xử lý |
|---|---|---|
| Không thấy CSP header | Request có đi qua security chain chứa cấu hình không? Header có bị reverse proxy/CDN thay đổi? | Xem header ở browser và cấu hình của chain thực sự xử lý trang |
| Có CSP ở API nhưng trang vẫn thiếu CSP | HTML do hệ thống frontend/host khác phục vụ | Đặt CSP ở nơi trả trang HTML |
| Script hợp lệ từ CDN bị chặn | `script-src` có khai báo đúng origin của CDN không? | Ưu tiên tự phục vụ script; nếu phải dùng CDN, thêm đúng nguồn được kiểm soát |
| Nút bấm hoặc widget không chạy | Handler nội tuyến/inline script bị từ chối | Chuyển logic sang file script hoặc triển khai nonce/hash an toàn |
| CSS bị mất, font không tải | `style-src`, `font-src` hoặc inline style không phù hợp | Mở đúng nguồn cần thiết; tránh tự động thêm wildcard |
| API dùng được trên Postman nhưng bị browser chặn | `connect-src` hoặc CORS không phù hợp | Kiểm tra CSP trong Console và CORS ở response API riêng |
| WebSocket bị từ chối | `connect-src` thiếu endpoint `wss://...` | Khai báo origin/endpoint cần thiết và kiểm thử trình duyệt mục tiêu |
| Trang vẫn thực thi script dù DevTools báo vi phạm | Chỉ dùng `Content-Security-Policy-Report-Only` | Hiểu rõ chế độ báo cáo và triển khai enforcement đúng thời điểm |
| Trang bị chặn nhiều hơn policy đang đọc | Có thể tồn tại nhiều CSP header hoặc CSP từ proxy | Rà toàn bộ header; các policy thực thi cùng tồn tại đều được áp dụng |
| Policy trên staging chạy nhưng production lỗi | Khác domain, CDN, port, WebSocket hoặc cách render | Kiểm kê nguồn theo môi trường; quản lý cấu hình có kiểm soát |

### Những lỗi cấu hình dễ bỏ qua

**1. Dùng `'unsafe-inline'` để sửa lỗi JavaScript.** Với `script-src`, nó thường làm mất một rào chắn quan trọng chống mã script được chèn. Chọn thay đổi frontend hoặc nonce/hash phù hợp; không thêm `'unsafe-inline'` chỉ để im cảnh báo.

**2. Dùng nguồn quá rộng.** `script-src *` hoặc chỉ `https:` cấp quyền cho quá nhiều nơi cung cấp script. Một origin đã được cho phép nhưng phân phối mã không đáng tin cậy vẫn có thể dẫn đến XSS.

**3. Nhầm thứ tự directive với quyền ưu tiên.** Browser đánh giá từng directive theo quy tắc CSP. Không phải viết `default-src 'none'` trước hay sau `script-src 'self'` là làm chính sách tự nới lỏng; directive chuyên biệt quyết định cho loại tài nguyên tương ứng. Tránh khai báo trùng cùng tên directive vì quy tắc xử lý phần khai báo lặp có thể không giống điều người viết kỳ vọng.

**4. Cấu hình cả DSL và writer tùy chỉnh cho cùng CSP.** Khi có nhiều header do ứng dụng hoặc proxy cùng trả, trình duyệt áp dụng nhiều policy thực thi với hiệu ứng cộng dồn giới hạn. Tài nguyên có thể bị chặn dù nhìn vào một policy riêng lẻ thì có vẻ được phép. Hãy quản lý một nguồn cấu hình rõ ràng cho từng trang và kiểm tra tất cả response header.

**5. Chèn giá trị từ request vào policy mà không kiểm soát.** Directive được ứng dụng cung cấp phải đến từ cấu hình tin cậy. Không nối trực tiếp URL, hostname hoặc chuỗi do người dùng gửi vào CSP header; nếu cần lựa chọn nguồn, dùng danh sách được phê duyệt và chuẩn hóa đầu vào.

**6. Dùng CSP thay thế các lớp bảo vệ khác.** CSP không loại bỏ HTML độc hại khỏi DOM, không sửa lỗi encode đầu ra và không thay cho CSRF token, CORS hay cookie session an toàn. Từng cơ chế trong mô-đun bảo vệ HTTP giải quyết những nhóm rủi ro khác nhau.

## 10. Quy trình triển khai khi ứng dụng thay đổi

Với ứng dụng thực tế, chính sách CSP cần được quản lý như một phần của kiến trúc frontend và quy trình phát hành:

1. **Kiểm kê nguồn:** tìm origin thực sự cung cấp script, stylesheet, font, ảnh, API, WebSocket và frame; ghi rõ tính năng cần chúng.
2. **Chọn chính sách nhỏ nhất:** dùng `default-src` làm fallback phù hợp, ưu tiên `object-src 'none'`, bổ sung `base-uri`, `form-action` và `frame-ancestors` theo nhu cầu thực tế.
3. **Cấu hình ở nơi trả HTML:** dùng DSL hoặc writer trên Servlet, API Reactive trên WebFlux, hoặc tầng trả HTML tương ứng nếu frontend tách biệt.
4. **Thử ở Report-Only:** dùng DevTools và hệ thống báo cáo nếu đã thiết lập; phân biệt vi phạm của frontend hợp lệ với nội dung chèn hoặc extension trình duyệt.
5. **Sửa nguồn lỗi:** đưa script nội tuyến ra file, thêm nguồn cụ thể hoặc nonce/hash đúng trường hợp, tránh nới lỏng toàn bộ policy vì một thư viện.
6. **Bật thực thi và quan sát:** kiểm thử trình duyệt mục tiêu, kiểm tra trang đăng nhập, trang lỗi, proxy/CDN và các security chain; cập nhật policy khi tích hợp mới thay đổi nhu cầu tải tài nguyên.

Một mẫu ghi chép giúp review cấu hình:

| Quyết định | Ví dụ | Câu hỏi cần trả lời khi review |
|---|---|---|
| Script | `script-src 'self'` | Có thực sự cần script CDN/inline không? |
| Kết nối | `connect-src 'self' https://api.example.com` | Tại sao API này cần được browser gọi? Có WebSocket không? |
| Form | `form-action 'self'` | Có luồng thanh toán hoặc SSO dùng form sang origin khác không? |
| Frame | `frame-ancestors 'none'` | Có đối tác hợp lệ cần nhúng trang không? |
| Triển khai | HTTP header tại frontend origin | Response HTML nào áp dụng? Proxy/CDN có ghi đè header không? |
| Giám sát | Report-Only rồi enforcement | Có vi phạm hợp lệ còn chưa xử lý không? |

## 11. Bài thực hành và tự đánh giá

**Bài thực hành:** xây dựng một dashboard demo dùng một file JS cùng origin, một API khác origin và một iframe tùy chọn. Tạo lần lượt hai cấu hình Servlet, mỗi lần chỉ bật một phương án: (a) `contentSecurityPolicy(...).policyDirectives(...)`, (b) `new ContentSecurityPolicyHeaderWriter(...)` và `addHeaderWriter(...)`.

1. Đọc response header của trang HTML, xác nhận chuỗi policy bạn cấu hình được gửi nguyên vẹn.
2. Thêm `connect-src 'self' https://api.example.com` rồi thử gọi một endpoint được phép và một endpoint ngoài danh sách. Ghi nhận sự khác nhau giữa chặn bởi CSP và chặn bởi CORS.
3. Đổi writer sang Report-Only, quan sát tên header và hành vi của browser khi tài nguyên vi phạm.
4. Chuyển trở lại CSP thực thi; thử một handler nội tuyến bị chèn trong môi trường test. Đối chiếu thông báo Console với directive đã khai báo.
5. Bổ sung một `SecurityFilterChain` chuyên cho API nếu demo có nhiều chain, rồi xác nhận response HTML đi qua chain nào.
6. Nếu demo có WebFlux, thiết lập cùng policy qua `ServerHttpSecurity` và đối chiếu HTTP header thực nhận.

**Câu hỏi tự đánh giá:**

1. `ContentSecurityPolicyHeaderWriter` làm phần việc nào, còn trình duyệt làm phần việc nào?
2. Vì sao ứng dụng phải tự quyết định danh sách nguồn trong `policyDirectives(...)`?
3. Việc thêm `default-src 'self'` có tự thiết lập `form-action` và `frame-ancestors` không?
4. Sự khác nhau giữa header CSP thực thi và Report-Only là gì?
5. Khi frontend được phục vụ từ CDN riêng, CSP trên response JSON của API có đủ bảo vệ trang không?
6. Vì sao nonce cố định trong Java string của writer không phải triển khai CSP nonce an toàn?
7. Unit test writer, HTTP integration test và kiểm thử trong trình duyệt chứng minh những khía cạnh khác nhau nào?

## 12. Ghi nhớ

`ContentSecurityPolicyHeaderWriter` là cơ chế **ghi CSP header cho Servlet response** trong Spring Security. API này chỉ xuất các directive **do ứng dụng lựa chọn và cung cấp**; nó không tự tìm nguồn tài nguyên của frontend hay tự tạo nonce. Với ứng dụng Servlet, có thể cấu hình ngắn gọn qua `HttpSecurity.headers(...).contentSecurityPolicy(...)` hoặc đăng ký writer trực tiếp; với Reactive, dùng API tương ứng của `ServerHttpSecurity`.

Hiệu quả bảo vệ phụ thuộc vào việc chọn directive đúng, đặt header trên response HTML cần được bảo vệ, tránh nguồn quá rộng và thực sự kiểm thử trong trình duyệt. CSP bổ sung khả năng giảm thiểu tác động của nội dung bị chèn, còn xử lý dữ liệu an toàn, CSRF, CORS, session và các cơ chế phòng vệ HTTP khác vẫn phải được thực hiện riêng.
