# X-XSS-Protection cùng vai trò lịch sử của bộ lọc XSS trên trình duyệt

Trong chương **Nâng cấp và tương thích** thuộc **SPRING_SECURITY_HTTP_PROTECTION**, header HTTP `X-XSS-Protection` là trường hợp điển hình của một cơ chế bảo mật từng được sử dụng rộng rãi nhưng hiện không còn phù hợp với trình duyệt hiện đại. Nó vốn cho phép website điều khiển **bộ lọc Cross-Site Scripting (XSS) tích hợp sẵn trong một số browser cũ**. Ngày nay, việc bật lại bộ lọc có thể gây rủi ro, còn nhiều trình duyệt đã loại bỏ hoàn toàn cơ chế này.

Spring Security hiện đại mặc định gửi:

~~~http
X-XSS-Protection: 0
~~~

Giá trị `0` yêu cầu **tắt bộ lọc XSS lịch sử ở trình duyệt có hỗ trợ**. Nó **không có nghĩa là Spring Security tắt mọi biện pháp chống XSS**: bảo vệ thực tế cần kết hợp mã hóa đầu ra theo ngữ cảnh, DOM APIs an toàn, sanitization cho HTML được phép, Content Security Policy (CSP) và kiểm thử các luồng dữ liệu. Những nguyên tắc này áp dụng cho cả Servlet và Reactive/WebFlux, bên cạnh các lớp phòng vệ HTTP khác của module như CSRF, CORS, security headers, HSTS, HTTP firewall và session.

Sau bài học, người học có thể:

1. Phân biệt reflected, stored và DOM-based XSS; nêu chính xác vấn đề mà XSS filter lịch sử từng cố gắng giải quyết.
2. Hiểu các giá trị `0`, `1`, `1; mode=block`, `1; report=...` và giới hạn hỗ trợ trình duyệt.
3. Giải thích vì sao XSS Auditor bị loại bỏ, vì sao bộ lọc có thể làm thay đổi logic trang và rò rỉ thông tin.
4. Giữ hoặc tùy chỉnh header trong Spring Security Servlet/WebFlux bằng đúng API, tránh nhầm `HeaderValue.DISABLED` với `xssProtection(...).disable()`.
5. Thiết kế lộ trình chuyển sang CSP và output encoding, kiểm thử trên trình duyệt thật và ứng phó cảnh báo scanner lỗi thời.

## 1. XSS là gì và vì sao trình duyệt từng có bộ lọc?

**Cross-Site Scripting (XSS)** xảy ra khi dữ liệu không đáng tin được đưa vào trang theo cách khiến trình duyệt hiểu nó thành mã hoặc chỉ thị có thể thực thi, thay vì chỉ là dữ liệu. Có ba dạng điển hình:

| Dạng XSS | Nguồn dữ liệu không tin cậy | Ví dụ | Quan hệ với bộ lọc XSS lịch sử |
|---|---|---|---|
| **Reflected XSS** | Tham số URL, form hoặc request được máy chủ trả lại trong HTML cùng response | Controller ghép trực tiếp `q` vào trang kết quả tìm kiếm | Bộ lọc lịch sử có thể nhận diện *một số* mẫu phản chiếu nhưng không đầy đủ. |
| **Stored XSS** | Nội dung đã lưu trong database, bình luận, diễn đàn, CMS hoặc profile | Một người đăng bình luận có HTML nguy hiểm, người khác tải trang | Thường nằm ngoài phạm vi đối chiếu request hiện tại với response. |
| **DOM-based XSS** | JavaScript của trang đọc một giá trị không tin cậy và đưa vào DOM sink | Lấy `location.hash` rồi gán vào `innerHTML` | XSS filter phản chiếu không bao quát được dòng dữ liệu chạy phía client. |

Xét endpoint Spring MVC sau (cố ý chứa lỗi để giải thích):

~~~java
// MẪU KHÔNG AN TOÀN: tuyệt đối không dùng làm controller sản phẩm.
@GetMapping(value = "/search", produces = MediaType.TEXT_HTML_VALUE)
@ResponseBody
String search(@RequestParam String q) {
    return "<h1>Kết quả cho: " + q + "</h1>";
}
~~~

Nếu giá trị `q` mang ký tự HTML, trình duyệt có thể phân tích đoạn dữ liệu đó thành node HTML hoặc xử lý sự kiện không mong muốn. **Nguyên nhân gốc là ghép dữ liệu chưa được escape vào ngữ cảnh HTML**.

Các browser cũ từng cố phát hiện dấu vết đoạn mã đi từ request vào response rồi sửa hoặc chặn HTML. Cơ chế này chỉ dựa vào **heuristic**: browser không thể biết cấu trúc nghiệp vụ của mọi trang, đặc biệt khi dữ liệu có nhiều lớp mã hóa hoặc được tạo ra sau khi HTML tải xong.

## 2. Dòng thời gian và phạm vi của XSS Filter/XSS Auditor

Một số browser từng có các bộ lọc phản chiếu khác nhau:

- **Internet Explorer:** XSS Filter trong các phiên bản cũ, nổi bật ở thế hệ IE8 và các bản tiếp theo.
- **Chrome/Chromium:** `XSS Auditor`, cố phát hiện mã tấn công có dấu vết phản chiếu trong request khi parse HTML.
- **Safari/WebKit:** từng hỗ trợ lọc theo header trong một số phiên bản.
- **Firefox:** không được coi là có cơ chế XSS filter tương đương chỉ vì server gửi header. Cần dựa vào tính năng thực của từng browser và phiên bản thay vì giả định chung.

Lưu đồ minh họa cơ chế lịch sử:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser có XSS filter cũ
    participant S as Spring MVC hoặc WebFlux
    U->>B: Mở /search?q=...
    B->>S: GET /search?q=...
    S-->>B: HTML có chuỗi q phản chiếu
    B->>B: So sánh input request với HTML
    alt Phát hiện mẫu nghi ngờ
        B->>B: Xóa một phần nội dung hoặc chặn render
    else Không phát hiện
        B->>B: Render theo cách thông thường
    end
~~~

Tài liệu Chromium ghi nhận việc công bố ý định loại bỏ XSS Auditor vào **15/07/2019**, vô hiệu hóa vĩnh viễn vào **05/08/2019**, rồi xóa khỏi **Chrome 78**. Nguyên nhân gồm các cách vượt qua cơ chế lọc đã biết và khả năng phát sinh **cross-site information leaks**. Vì vậy, gửi header `1; mode=block` hôm nay **không chứng minh Chrome hiện đại đang dùng XSS Auditor**.

Điểm quan trọng về tương thích: số phiên bản và hành vi từng browser có thể thay đổi. **Danh sách browser tổ chức thật sự hỗ trợ** và thử nghiệm thực tế quan trọng hơn một dòng header xuất hiện trong Network tab.

## 3. Các giá trị lịch sử của header

`X-XSS-Protection` là response header **không thuộc tiêu chuẩn HTTP hiện đại**, hiện được MDN đánh dấu *deprecated* và *non-standard*.

Một response chỉ nên dùng **một** trong các lựa chọn dưới đây:

~~~http
X-XSS-Protection: 0
~~~

~~~http
X-XSS-Protection: 1
~~~

~~~http
X-XSS-Protection: 1; mode=block
~~~

~~~http
X-XSS-Protection: 1; report=/security/xss-report
~~~

| Giá trị | Ý nghĩa lịch sử | Khuyến nghị hiện tại |
|---|---|---|
| `0` | Vô hiệu hóa bộ lọc XSS tích hợp ở browser cũ có hỗ trợ. | **Nên dùng nếu chọn gửi header**; cũng là mặc định của Spring Security hiện đại. |
| `1` | Bật cơ chế lọc; browser có thể cố sửa HTML/JS bị xem là độc hại. | Không dùng làm phòng vệ chính; khả năng làm sai logic của trang. |
| `1; mode=block` | Khi nghi có reflected XSS, browser có thể từ chối render cả trang thay vì sửa một phần. | Chỉ là lựa chọn tương thích lịch sử; có thể gây false positive hoặc side-channel. |
| `1; report=URI` | Tùy biến báo cáo gắn với Chromium cũ khi phát hiện tấn công. | Không xem là telemetry đáng tin trên browser mới; khác reporting của CSP. |

Phân biệt những ý nghĩa dễ nhầm:

- `X-XSS-Protection: 0` chỉ tắt **filter cũ**, không tắt output encoding, CSP, HttpOnly cookie, CSRF hay authorization.
- `1; mode=block` không có quan hệ trực tiếp với CSP directive `block-all-mixed-content` hay `frame-ancestors`.
- `report=` là cơ chế lịch sử của một số browser, khác `Content-Security-Policy-Report-Only`.
- **Không gửi header** có thể khác với **gửi `0`** trên một số trình duyệt cũ: browser có thể có trạng thái lọc mặc định riêng.
- Ở browser đã loại bỏ bộ lọc, các giá trị `0`, `1` và `1; mode=block` có thể không ảnh hưởng hành vi.

## 4. Vì sao bật bộ lọc có thể tạo lỗ hổng?

XSS filter lịch sử không chỉ “bảo vệ thêm”. Vì tự sửa HTML/JavaScript, nó có thể làm trang vốn an toàn **chạy theo một nhánh logic khác**.

Ví dụ giả định:

~~~html
<!-- Script khởi tạo một giới hạn bảo vệ. -->
<script>
  window.isDebugMode = false;
</script>

<!-- Ở phần sau trang: -->
<script>
  if (window.isDebugMode !== false) {
    openLegacyDebugPanel();
  }
</script>
~~~

Trong một browser legacy có cơ chế lọc heuristic, attacker có thể thử tạo request khiến script đầu tiên **bị nhầm là nội dung phản chiếu** và bị bỏ. Khi đó biến không được khởi tạo, `undefined !== false` là `true`, và nhánh vốn được kỳ vọng không chạy lại có thể chạy. Đây là minh họa **cơ chế rủi ro**, không phải khẳng định payload bất kỳ sẽ thành công trên mọi browser.

Những hệ quả quan trọng:

1. **False positive:** chuỗi hợp lệ nhưng giống script làm một trang bình thường bị thay đổi hoặc chặn.
2. **Thay đổi logic ứng dụng:** bỏ một đoạn script an toàn có thể khiến phần code còn lại thực thi theo trạng thái sai.
3. **Information leakage:** website khác có thể quan sát khác biệt trong hành vi chặn/nạp trang để suy luận thông tin.
4. **Từ chối phục vụ cục bộ:** `mode=block` có thể khiến người dùng không tải được trang hợp lệ.
5. **Bảo vệ không nhất quán:** browser khác nhau cùng nhận một header nhưng không cùng xử lý.

MDN và OWASP đều khuyến cáo không dựa vào cơ chế lọc này; **CSP nghiêm ngặt kết hợp xử lý dữ liệu đúng ngữ cảnh** là hướng phòng vệ được đề xuất hiện tại.

## 5. So sánh với các lớp bảo vệ hiện đại

| Kiểm soát | Ngăn/chặn vấn đề gì? | Giới hạn quan trọng |
|---|---|---|
| `X-XSS-Protection` | Bộ lọc reflected XSS lịch sử ở browser có hỗ trợ | Không bảo đảm chống stored hoặc DOM XSS; deprecated. |
| **Output encoding theo ngữ cảnh** | Đưa văn bản không đáng tin vào HTML, attribute, URL, JS... dưới dạng dữ liệu | Phải chọn đúng encoder theo **ngữ cảnh đích**; không có một hàm escape dùng cho mọi nơi. |
| **HTML sanitization** | Giữ rich text hợp lệ nhưng loại bỏ node/attribute/URL không cho phép | Phải dùng thư viện/policy đáng tin thay cho regex tự viết. |
| **Safe DOM APIs** | Tránh thực thi khi render dữ liệu động | `textContent`/`createTextNode` khác bản chất với `innerHTML`. |
| **Content Security Policy (CSP)** | Giới hạn nguồn script và nhiều cách thực thi không được phép | Không tự sửa lỗi code; policy phải được thiết kế và kiểm thử đúng. |
| `X-Content-Type-Options: nosniff` | Hạn chế browser suy đoán MIME của script/style | Khác XSS filter, cần Content-Type chính xác. |
| `HttpOnly` / `Secure` / `SameSite` | Giảm rủi ro với cookie qua script, transport, cross-site request | Không ngăn script độc chạy trong cùng origin khi XSS xảy ra. |
| **CSRF** | Ngăn request thay đổi trạng thái bị gửi lợi dụng session | Không thay biện pháp chống XSS; script XSS có thể vượt nhiều giả định CSRF. |
| **CORS** | Kiểm soát JavaScript đọc response cross-origin | Không ngăn reflected XSS, không thay server-side authorization. |

Đặc biệt, một trang được CSRF và CORS bảo vệ **vẫn có thể bị XSS** nếu render dữ liệu sai cách. Ngược lại, một header XSS filter cũ không khắc phục khả năng đánh cắp dữ liệu qua endpoint API trong phiên hiện tại.

## 6. Mặc định Spring Security hiện nay: `X-XSS-Protection: 0`

Spring Security bổ sung nhiều HTTP response headers theo cấu hình mặc định, bao gồm:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
~~~

Khi request được nhận diện là HTTPS, Spring Security có thể phát thêm HSTS. Bảng trên chỉ trích các header liên quan, không có nghĩa cấu hình triển khai nào cũng trả chính xác từng giá trị đó khi có tùy chỉnh.

Theo tài liệu Spring Security, `X-XSS-Protection: 0` là **mặc định có chủ đích** để vô hiệu hóa bộ lọc cũ. Spring Security **không tự đặt CSP mặc định** cho mọi dự án vì không biết những script, CDN, iframe và resource nào mà ứng dụng cần.

### Ba hành động khác nhau trong cấu hình

| Cấu hình | Response Spring phát ra | Hệ quả |
|---|---|---|
| Mặc định hoặc `HeaderValue.DISABLED` | `X-XSS-Protection: 0` | Yêu cầu filter legacy tắt. |
| `.xssProtection(xss -> xss.disable())` | **Không có header** do writer này tạo | Không yêu cầu rõ tắt filter ở browser cũ. |
| `HeaderValue.ENABLED` hoặc `ENABLED_MODE_BLOCK` | `1` hoặc `1; mode=block` | Cố bật lại filter ở browser có hỗ trợ; không khuyến nghị chung. |

**Chú ý quan trọng:** phương thức `disable()` của cấu hình header nghĩa là **ngừng phát header**, còn giá trị enum `DISABLED` nghĩa là **gửi `0`**. Không nhầm với `headers.disable()`, vì lệnh sau sẽ tắt toàn bộ security headers do Spring Security quản lý.

## 7. Cấu hình Spring Security Servlet

### 7.1. Giữ hoặc khai báo rõ giá trị `0`

Trong Spring Security 6/7, có thể để mặc định hoặc khai báo explicit để dễ audit:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.XXssProtectionHeaderWriter;

@Configuration
class ServletSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/search").permitAll()
                .anyRequest().authenticated())
            .headers(headers -> headers
                .xssProtection(xss -> xss.headerValue(
                    XXssProtectionHeaderWriter.HeaderValue.DISABLED
                ))
            );

        return http.build();
    }
}
~~~

Header mong đợi:

~~~http
X-XSS-Protection: 0
~~~

Ví dụ minh họa cấu hình header; trong ứng dụng thực, giữ authentication, CSRF, session/logout và authorization theo yêu cầu nghiệp vụ. Việc chọn `0` không phải lý do tắt CSRF.

### 7.2. Bỏ riêng header khi có lý do

Nếu cần bỏ hoàn toàn header này ở tầng Spring Security:

~~~java
http.headers(headers -> headers
    .xssProtection(xss -> xss.disable())
);
~~~

Phương thức trên chỉ ngừng writer của **X-XSS-Protection**; các security headers khác vẫn giữ mặc định theo cấu hình. Tuy nhiên, CDN, proxy hoặc một servlet filter khác có thể chèn header sau đó. Phải kiểm tra trên URL công khai.

### 7.3. Cấu hình `mode=block` chỉ dùng khi nghiên cứu legacy

~~~java
http.headers(headers -> headers
    .xssProtection(xss -> xss.headerValue(
        XXssProtectionHeaderWriter.HeaderValue.ENABLED_MODE_BLOCK
    ))
);
~~~

Response tương ứng:

~~~http
X-XSS-Protection: 1; mode=block
~~~

Đây là ví dụ **tương thích lịch sử**, không phải mẫu nên dùng cho sản phẩm mới. Trong trường hợp buộc hỗ trợ một browser rất cũ, cần biết chính xác version, hành vi filter, test false positive và phương án rollback.

## 8. Cấu hình Reactive/WebFlux

API Reactive dùng `ServerHttpSecurity` và writer thuộc package khác với Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.XXssProtectionServerHttpHeadersWriter;

@Configuration
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/search").permitAll()
                .anyExchange().authenticated())
            .headers(headers -> headers
                .xssProtection(xss -> xss.headerValue(
                    XXssProtectionServerHttpHeadersWriter.HeaderValue.DISABLED
                ))
            )
            .build();
    }
}
~~~

Để không phát header trong WebFlux:

~~~java
http.headers(headers -> headers
    .xssProtection(xss -> xss.disable())
);
~~~

Nếu cần trình bày cấu hình lịch sử:

~~~java
http.headers(headers -> headers
    .xssProtection(xss -> xss.headerValue(
        XXssProtectionServerHttpHeadersWriter.HeaderValue.ENABLED_MODE_BLOCK
    ))
);
~~~

Không nhập nhằng `XXssProtectionHeaderWriter` của Servlet và `XXssProtectionServerHttpHeadersWriter` của Reactive. Cả hai mô hình đều phải thử response cuối cùng ở trình duyệt, vì server chỉ phát header, còn browser quyết định có áp dụng filter hay không.

## 9. Di trú từ cấu hình cũ

Một ứng dụng lâu năm có thể đang dùng Java DSL chain cũ hoặc cấu hình XML, chẳng hạn:

~~~xml
<!-- Ví dụ cấu hình mang tính lịch sử -->
<headers>
    <xss-protection headerValue="1; mode=block" />
</headers>
~~~

Khi nâng cấp sang API lambda, **không được sao chép cơ học giá trị `ENABLED_MODE_BLOCK`** chỉ để giữ nguyên kết quả scanner. Cần quyết định lại chính sách trên cơ sở browser thực tế được hỗ trợ.

Quy trình đề xuất:

1. **Kiểm kê:** tìm `X-XSS-Protection`, `xssProtection`, `XXssProtectionHeaderWriter`, `ENABLED_MODE_BLOCK`, rule add-header của CDN/gateway và các custom filters.
2. **Xác định browser target:** ghi rõ engine/version còn cần hỗ trợ, đặc biệt nếu có Internet Explorer hoặc WebKit phiên bản cũ.
3. **Đánh giá nguồn XSS thực sự:** audit controller ghép HTML, Thymeleaf `th:utext`, rich text, các DOM sinks như `innerHTML` và thông tin qua URL/JSON.
4. **Chọn trạng thái header:** phần lớn ứng dụng hiện đại nên giữ `0` mặc định theo OWASP/Spring Security. Nếu bỏ header, hiểu sự khác biệt với browser legacy.
5. **Xây dựng CSP:** bắt đầu Report-Only, quan sát vi phạm, sửa script/inline code và CDN dependencies, sau đó chuyển sang enforcement.
6. **Kiểm thử cả hai web stack nếu sử dụng:** Servlet dùng MockMvc; Reactive dùng WebTestClient; đường công khai chạy qua proxy/CDN có thể đổi header.
7. **Triển khai theo giai đoạn:** kiểm tra lại login/logout, OAuth redirect, iframe, third-party scripts, CSRF token flow và các chức năng hợp lệ.
8. **Cập nhật scanner/tiêu chuẩn đội ngũ:** tránh quy tắc cũ tự động yêu cầu header `1` hoặc `mode=block`.

| Trạng thái tìm thấy | Hướng xử lý thực tế | Sai lầm cần tránh |
|---|---|---|
| `X-XSS-Protection: 1` | Phân tích lý do lịch sử, chuyển về `0` khi không còn yêu cầu legacy. | Coi việc bật filter là bằng chứng đã fix XSS. |
| `X-XSS-Protection: 1; mode=block` | Xác định browser có còn hỗ trợ; thay bằng CSP/encoding và `0` theo mặc định mới. | Tin Chrome hiện đại sẽ chặn như trước năm 2019. |
| Không có header | Kiểm tra yêu cầu sản phẩm và behavior browser; giữ default `0` hoặc có lý do để bỏ. | Tự động báo “XSS enabled” chỉ từ vắng header. |
| Header bị CDN ghi đè | Chọn owner, sửa chính sách biên và đo response public. | Thay đổi Spring mà không xem cấu hình CDN. |
| `headers.disable()` được dùng chỉ để bỏ XSS header | Thay bằng `xssProtection(...).disable()` nếu thật sự cần bỏ riêng. | Xóa cả HSTS, nosniff, frame/caching headers. |

## 10. CSP và output encoding là nền tảng bảo vệ XSS hiện đại

### 10.1. CSP giới hạn quyền thực thi thay vì đoán payload

Một policy khởi đầu **dành cho ứng dụng không cần inline JavaScript**:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
X-XSS-Protection: 0
X-Content-Type-Options: nosniff
~~~

Ý nghĩa:

- `script-src 'self'` giới hạn nguồn script về cùng origin trong ví dụ và không tự cho phép inline script.
- `object-src 'none'` ngăn một số cơ chế nhúng plugin/object.
- `base-uri 'self'` hạn chế việc thay đổi cách trình duyệt diễn giải URL trong document.
- `frame-ancestors 'none'` ngăn trang bị nhúng trong frame (có thể phải thay đổi nếu nghiệp vụ cho phép iframe).
- `X-Content-Type-Options: nosniff` yêu cầu tuân thủ MIME, khác cơ chế kiểm soát XSS filter cũ.

Đây là ví dụ **có điều kiện**: ứng dụng có CDN, script của bên thứ ba, WebSocket, iframe hoặc inline script sẽ cần một chính sách được thiết kế lại, tránh copy y nguyên làm hỏng chức năng.

Với Servlet:

~~~java
http.headers(headers -> headers
    .xssProtection(xss -> xss.headerValue(
        XXssProtectionHeaderWriter.HeaderValue.DISABLED
    ))
    .contentSecurityPolicy(csp -> csp.policyDirectives(
        "default-src 'self'; script-src 'self'; "
      + "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    ))
);
~~~

Tương tự với Reactive:

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp.policyDirectives(
        "default-src 'self'; script-src 'self'; "
      + "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    ))
);
~~~

Trong cả hai ví dụ, Spring Security **không tự phát nonce động** thích hợp với các template của ứng dụng. Nếu dùng script inline được ủy quyền, cần nonce ngẫu nhiên **mới cho mỗi response** hoặc hash chính xác thay vì mở `'unsafe-inline'`.

### 10.2. Triển khai dần qua Report-Only

Trong giai đoạn quan sát:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; report-uri /csp-reports
~~~

Report-Only có thể cung cấp thông tin về script vi phạm, nhưng **không tự chặn**. Sau khi xử lý các vi phạm hợp lệ và tương thích browser, chuyển sang `Content-Security-Policy` để thực thi. Việc thu thập CSP reports phải giới hạn dữ liệu nhạy cảm và dung lượng; cơ chế `report-uri` hay `report-to` hỗ trợ tùy browser, không xem là bảo đảm telemetry tuyệt đối.

### 10.3. Mã hóa đầu ra theo đúng ngữ cảnh

| Ngữ cảnh đưa dữ liệu vào | Giải pháp |
|---|---|
| HTML text | Template engine auto-escape (ví dụ Thymeleaf `th:text`) hoặc encoder HTML text. |
| HTML attribute | Encoder dành cho attribute và cấu trúc thuộc tính phù hợp. |
| URL | Validate scheme/host/path, encode thành phần URL; HTML escape không tự chặn `javascript:`. |
| JavaScript string | Tránh nhúng trực tiếp dữ liệu; serialize đúng ngữ cảnh; không dùng HTML encoder thay JS encoder. |
| DOM text | `textContent` hoặc `createTextNode`. |
| Rich text có HTML được phép | Dùng sanitizer với policy allowlist theo node/attribute/URL. |

Ví dụ phía JavaScript:

~~~javascript
// Văn bản từ API được render đúng như văn bản.
const message = apiResponse.message;
document.querySelector("#notice").textContent = message;

// Không dùng với message không đáng tin:
document.querySelector("#notice").innerHTML = message;
~~~

Ví dụ trong Thymeleaf:

~~~html
<!-- query được đưa vào như văn bản và được escape -->
<h1 th:text="${query}">Từ khóa tìm kiếm</h1>

<!-- th:utext không escape HTML; không áp dụng trực tiếp cho input thô -->
~~~

Lưu ý: khi HTML có nội dung đã lưu từ người dùng khác, **stored data vẫn là untrusted input**; không an toàn chỉ vì nó nằm trong database.

## 11. Kiểm thử ở Spring Security và trình duyệt

### 11.1. Servlet: MockMvc xác minh header

Giả sử dự án có endpoint `GET /search` trả HTTP 200 và cấu hình Servlet tại mục 7, với `spring-security-test`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class XssHeaderServletTest {

    @Autowired MockMvc mvc;

    @Test
    void springSecurityWritesLegacyFilterOff() throws Exception {
        mvc.perform(get("/search").param("q", "abc"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-XSS-Protection", "0"))
            .andExpect(header().string("X-Content-Type-Options", "nosniff"));
    }
}
~~~

Test chỉ kiểm tra **HTTP response do ứng dụng phát**. Nó không chứng minh browser đã tắt/bật filter hay XSS đã được xử lý đúng. Nếu đã cấu hình bỏ header thay vì gửi `0`, thay assertion bằng:

~~~java
.andExpect(header().doesNotExist("X-XSS-Protection"));
~~~

### 11.2. Reactive: WebTestClient

Ví dụ giả định dự án WebFlux có handler `GET /search` trả 200:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class XssHeaderReactiveTest {

    @Autowired WebTestClient client;

    @Test
    void reactiveSecurityWritesLegacyFilterOff() {
        client.get().uri("/search")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals("X-XSS-Protection", "0");
    }
}
~~~

Để test chạy được, phải có ứng dụng WebFlux thật và endpoint tương ứng. Tránh nạp lẫn dependency Servlet/Reactive để kiểm tra một tính năng không phụ thuộc controller.

### 11.3. Header nhìn từ URL công khai

Proxy hoặc CDN có thể thêm/ghi đè header, vì vậy kiểm tra response thực qua đường public:

~~~bash
curl -sS -D - -o /dev/null https://app.example.com/search?q=abc
~~~

Đối chiếu với origin trong môi trường thử nghiệm:

- Header `X-XSS-Protection` xuất hiện **một lần** với giá trị đã quyết định hay không?
- CDN có chèn lại `1` dù Spring gửi `0` không?
- CSP, HSTS, `X-Content-Type-Options`, `Cache-Control` còn đúng sau proxy hay không?
- Response `401/403`, redirect login, HTML và JSON có header theo chủ đích không?
- Browser có thực thi CSP, báo CSP violation và hiển thị giao diện đúng không?

**`curl` không chạy XSS filter hoặc CSP của trình duyệt.** Nó chỉ kiểm chứng bytes và headers của HTTP response.

### 11.4. Kiểm thử XSS theo nơi dữ liệu đi vào

Trong môi trường kiểm thử được cho phép, dùng dữ liệu có ký tự đặc biệt như `<`, `>`, `"`, `'` và `&`, theo dõi nơi dữ liệu đi vào DOM và response:

1. **Reflected path:** thử query/form rồi xác nhận HTML text được escape, không tạo phần tử hoặc handler mới ngoài dự kiến.
2. **Stored path:** lưu bình luận/bản nháp, đăng nhập tài khoản thử khác và xác nhận dữ liệu được render an toàn.
3. **DOM path:** thử dữ liệu qua URL, `location.hash`, JSON API hoặc message rồi kiểm tra các sink (`innerHTML`, `eval`, `document.write`).
4. **CSP:** scripts hợp lệ hoạt động; script không được phép bị chặn khi CSP enforcement, còn Report-Only chỉ ghi nhận.
5. **Chính sách bảo mật khác:** xác minh login/logout, CSRF, CORS và session vẫn đúng khi thay các security headers.

Không đánh giá bằng cách đơn giản xem scanner có thấy chữ `X-XSS-Protection` hay không: cần xem **ngữ cảnh của lỗi XSS và tác động thật**.

## 12. Chẩn đoán khi nâng cấp hoặc triển khai

| Hiện tượng | Nguyên nhân nên điều tra | Cách xử lý |
|---|---|---|
| Scanner báo nguy hiểm vì `X-XSS-Protection: 0` | Bộ quy tắc cũ yêu cầu `1; mode=block` | Dẫn OWASP/MDN và bằng chứng CSP/encoding; cập nhật rule thay vì bật filter cũ. |
| Spring test trả `0` nhưng browser thấy `1` | CDN/gateway/custom filter thêm header | Xác định policy owner, loại bỏ nguồn ghi đè, kiểm thử URL công khai. |
| Header bị mất ở một endpoint | Route/chain khác, cache/CDN, error handler trả response trước filter | So sánh response tại origin và edge, xác định chain/policy cần áp dụng. |
| Browser báo lỗi script sau khi bật CSP | `script-src` chưa cho nguồn hợp lệ, inline JS chưa chuyển nonce/hash | Điều tra CSP violation, sửa script/nonce, dùng Report-Only trước khi enforce. |
| Website bị lỗi chỉ trên browser cũ | Legacy filter sửa hoặc chặn HTML hợp lệ | Kiểm tra version, header, console và hành vi sau khi đặt `0`. |
| HTML qua template an toàn nhưng SPA vẫn XSS | DOM sink nguy hiểm (`innerHTML`, xử lý URL/JSON) | Dùng safe APIs/sanitization và test DOM path. |
| Nhóm muốn gọi `headers.disable()` để xóa một header | Hiểu nhầm config API | Chỉ dùng `xssProtection(xss -> xss.disable())` khi muốn bỏ header; giữ các default headers khác. |

Đặc biệt, nếu DevTools xuất hiện thông báo **“Refused to execute inline script”**, nguyên nhân thường là **CSP**, không phải bằng chứng XSS Auditor đang chạy. Xem chính sách `script-src`, nonce/hash, nguồn script và browser hiện tại.

## 13. Bài tập thực tế: ứng dụng sau CDN đang phát header trái nhau

**Bối cảnh:** một cổng quản trị dùng Spring Security Servlet được nâng cấp, phía trước có CDN. Spring trả:

~~~http
X-XSS-Protection: 0
~~~

Nhưng CDN chèn:

~~~http
X-XSS-Protection: 1; mode=block
~~~

Cổng còn có trang tìm kiếm render query trong HTML, nội dung bình luận được lưu database và một SPA dùng `innerHTML` để render message từ API. Máy trạm đa số là Chromium hiện đại, một số bộ phận yêu cầu browser legacy.

**Câu hỏi:**

1. Tại sao không thể coi header `mode=block` của CDN là bằng chứng bảo vệ XSS?
2. Việc kiểm thử các dòng dữ liệu nào cần làm trước khi hoàn tất nâng cấp?
3. Quyết định header nên thuộc tầng nào, và cần kiểm tra nó tại đâu?
4. Cần làm gì với nhóm máy trạm browser legacy?
5. Thay đổi nào giúp giảm XSS nhưng giữ hoạt động ổn định của login/logout và CSP?

**Gợi ý lời giải:**

- Chọn một nơi chịu trách nhiệm phát header; nếu phù hợp yêu cầu, giữ `0` theo Spring Security và bỏ rule `1; mode=block` tại CDN. Tránh response chứa các giá trị mâu thuẫn.
- Sửa/refactor controller tìm kiếm để output HTML được escape theo ngữ cảnh; bình luận đã lưu phải được render an toàn hoặc sanitize khi có rich text.
- Thay `innerHTML` bằng `textContent` khi message là text; kiểm kê DOM sinks khác và các URL do người dùng điều khiển.
- Triển khai CSP Report-Only để tìm inline JS và nguồn bên thứ ba, xử lý rồi mới bật enforcement; giữ `X-Content-Type-Options: nosniff` cùng các bảo vệ khác.
- Kiểm thử browser hiện đại lẫn browser legacy **đã được định danh cụ thể**. Nếu legacy còn bắt buộc, ghi nhận khác biệt hành vi filter và rủi ro của lựa chọn header.
- Đo response **sau CDN**, làm các test Servlet/DOM, đồng thời xác minh CSRF, CORS, session và HTTP redirect không bị tác động bởi thay đổi header.

## 14. Checklist phát hành

| Kiểm tra | Tiêu chí hoàn tất |
|---|---|
| Header từ ứng dụng và edge | Đã biết chính xác giá trị cuối cùng, không có giá trị mâu thuẫn. |
| Browser targets | Có danh sách version cần hỗ trợ và kết quả kiểm thử phù hợp. |
| Reflected XSS | Tất cả điểm phản chiếu được output-encode theo ngữ cảnh. |
| Stored XSS | Dữ liệu từ database được render như untrusted input. |
| DOM-based XSS | Các sink nguy hiểm đã được thay hoặc có sanitization đáng tin. |
| CSP | Có policy phù hợp ứng dụng, Report-Only rồi enforcement. |
| Spring Security Servlet/Reactive | Chọn đúng DSL/package và giữ các default security headers khác. |
| Tính năng liên quan | Login, logout, CSRF, CORS, HSTS, cookie/session và các trang HTML chạy đúng. |
| Scanner | Các rule deprecated được cập nhật dựa trên nguồn OWASP/MDN. |
| Hậu kiểm | Theo dõi CSP violation, lỗi JS và xác minh response qua CDN. |

## Tài liệu tham khảo

- [MDN — X-XSS-Protection header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-XSS-Protection): cú pháp, deprecation, cảnh báo bảo mật và tương thích browser.
- [OWASP — HTTP Security Response Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): khuyến nghị không gửi hoặc đặt `X-XSS-Protection: 0`.
- [Chrome for Developers — Chrome 78 Deprecations and Removals](https://developer.chrome.com/blog/chrome-78-deps-rems): quyết định loại bỏ XSS Auditor.
- [Chromium — XSS Auditor Design](https://new.chromium.org/developers/design-documents/xss-auditor/): cách phát hiện reflected XSS và giới hạn.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): mặc định `X-XSS-Protection: 0` và các lớp phòng vệ khác.
- [Spring Security — Servlet HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): cấu hình `XXssProtectionHeaderWriter` và CSP.
- [Spring Security — Reactive HTTP Response Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html): cấu hình `XXssProtectionServerHttpHeadersWriter`.
- [OWASP — Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): encoding theo ngữ cảnh, sanitization và safe sinks.
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): CSP, nonce/hash và reporting.

