# Thiết kế CSP cho trang dùng script nội bộ và dịch vụ bên ngoài

## 1. Mục tiêu và bối cảnh thực hành

Trong mô-đun **SPRING_SECURITY_HTTP_PROTECTION**, Content Security Policy (CSP) là một lớp phòng vệ của trình duyệt giúp giảm tác hại của việc chèn nội dung độc hại, đặc biệt là XSS. Bài thực hành này kết hợp thiết kế chính sách CSP, cấu hình HTTP response headers bằng Spring Security, kiểm tra trên trình duyệt và chẩn đoán tích hợp với dịch vụ bên ngoài.

Sau bài học, người học có thể:

1. Kiểm kê script, API, ảnh và các tài nguyên ngoài origin được trang thực sự sử dụng.
2. Chọn chính sách `script-src` phù hợp với cách trang tải script, phân biệt allowlist theo origin với CSP dựa trên nonce/hash.
3. Cấu hình CSP cho **Spring Security Servlet** và nhận biết vị trí cấu hình tương ứng trên **Reactive/WebFlux**.
4. Kiểm tra tình huống hợp lệ, tình huống bị chặn, báo cáo vi phạm và rủi ro của SDK bên thứ ba.
5. Triển khai dần qua `Content-Security-Policy-Report-Only` trước khi bật chế độ chặn.

**Tình huống:** Một trang quản trị được phục vụ tại `https://portal.example` cần chạy:

- `/js/app.js` và `/js/dashboard.js`: JavaScript do nhóm phát triển quản lý, phục vụ từ cùng origin với trang.
- `https://cdn.metrics.example/sdk.js`: SDK đo lường được trang chủ động nhúng.
- `https://api.metrics.example/v1/events`: API nhận dữ liệu được SDK gọi bằng `fetch`.
- `https://img.metrics.example/pixel.gif`: ảnh theo dõi mà SDK có thể tải.
- `/css/app.css` và `/images/logo.svg`: CSS và ảnh nội bộ.

Các tên miền `*.example` chỉ là ví dụ. Khi triển khai thật phải thay bằng các origin đã xác minh qua tài liệu nhà cung cấp và lưu lượng thực tế. Giả định ban đầu: trang **không cần** JavaScript nhúng trực tiếp vào HTML, script `eval()`, iframe hay nguồn tài nguyên tùy ý.

### 1.1. Sơ đồ luồng tài nguyên

~~~mermaid
flowchart LR
    Browser["Trình duyệt: portal.example"]
    App["/js/app.js, /js/dashboard.js"]
    SDK["cdn.metrics.example/sdk.js"]
    API["api.metrics.example"]
    Pixel["img.metrics.example"]
    Other["Nguồn không được duyệt"]

    Browser -->|"script-src 'self'"| App
    Browser -->|"script-src: origin SDK"| SDK
    Browser -->|"connect-src"| API
    Browser -->|"img-src"| Pixel
    Browser -. "CSP chặn" .-> Other
~~~

CSP được nhận từ HTTP response chứa tài liệu HTML và được trình duyệt áp dụng khi trang tải, thực thi hoặc kết nối tới tài nguyên. Việc cho phép tải một tập tin script từ CDN cũng có nghĩa là tin tưởng mã JavaScript bên trong tập tin đó: CSP **không cô lập** quyền của SDK khỏi DOM, cookie không có cờ `HttpOnly` hoặc dữ liệu mà JavaScript trên trang có thể đọc.

## 2. Khảo sát tài nguyên trước khi viết chính sách

Lập bảng kiểm kê từ mã nguồn, tab **Network** và tab **Console** của DevTools. Với mỗi URL phải phân loại theo hành động trình duyệt thực hiện; không gom mọi tên miền vào `script-src`.

| Hoạt động trên trang | Ví dụ | Directive kiểm soát | Quyết định |
|---|---|---|---|
| Tải script cùng origin | `/js/app.js` | `script-src` (hoặc `script-src-elem` nếu cấu hình) | Cho phép |
| Tải SDK từ CDN đã phê duyệt | `https://cdn.metrics.example/sdk.js` | `script-src` | Cho phép có điều kiện |
| Gửi sự kiện bằng `fetch()` | `https://api.metrics.example/v1/events` | `connect-src` | Cho phép |
| Tải ảnh pixel | `https://img.metrics.example/pixel.gif` | `img-src` | Cho phép nếu tính năng cần |
| Tải CSS nội bộ | `/css/app.css` | `style-src` | Cho phép |
| Chạy `<script>alert(1)</script>` được chèn vào HTML | Inline script | `script-src` | Chặn |
| Chạy `onclick="..."` được chèn vào phần tử | Inline event handler | `script-src` | Chặn |
| Gọi `eval()` hoặc `new Function()` | Thực thi chuỗi thành code | `script-src` | Chặn |
| Tải script từ domain lạ | `https://unexpected.example/x.js` | `script-src` | Chặn |
| Nhúng tài liệu qua iframe | Trang thanh toán/đối tác | `frame-src` | Chỉ thêm nếu có yêu cầu thực tế |

**Ranh giới quan trọng:** `'self'` biểu thị cùng origin (scheme, host và port), không phải mọi subdomain. Origin trong `script-src` không tự cho phép các request `fetch` hoặc ảnh từ cùng nhà cung cấp; chúng cần `connect-src` và `img-src` riêng.

## 3. Phương án A: trang dùng script tách file, chính sách allowlist có giới hạn

Đối với trang có thể đưa toàn bộ JavaScript vào các tập tin và SDK không cần cơ chế tải script động phức tạp, trước tiên có thể sử dụng chính sách dưới đây:

~~~http
Content-Security-Policy: default-src 'none'; base-uri 'none'; object-src 'none'; script-src 'self' https://cdn.metrics.example; connect-src 'self' https://api.metrics.example; img-src 'self' https://img.metrics.example; style-src 'self'; font-src 'self'; form-action 'self'; frame-ancestors 'none'
~~~

Giải thích từng thành phần:

| Directive | Tác dụng trong bài |
|---|---|
| `default-src 'none'` | Chặn các loại tài nguyên dùng fallback khi chưa có directive cụ thể; tránh ngầm mở rộng quyền. |
| `script-src 'self' https://cdn.metrics.example` | Cho phép script nội bộ và script từ đúng origin CDN đã chọn. Inline script và `eval()` tiếp tục bị chặn nếu không có nguồn cho phép đặc biệt. |
| `connect-src 'self' https://api.metrics.example` | Cho phép JavaScript mở kết nối đến API đã kiểm kê. |
| `img-src 'self' https://img.metrics.example` | Cho phép ảnh nội bộ và pixel của dịch vụ. |
| `style-src 'self'` / `font-src 'self'` | Chỉ lấy stylesheet và font từ origin hiện tại. |
| `object-src 'none'` | Chặn tài nguyên nhúng kiểu `object`, `embed` và `applet`. |
| `base-uri 'none'` | Ngăn phần tử `<base>` thay đổi base URL cho các liên kết tương đối. |
| `form-action 'self'` | Hạn chế đích gửi form; không kế thừa từ `default-src`. |
| `frame-ancestors 'none'` | Không cho trang bị nhúng trong frame của trang khác; cũng không kế thừa từ `default-src`. |

Chính sách ví dụ không cho phép `data:` cho script và không dùng `*`, `https:` chung hay `'unsafe-inline'`. Nếu tính năng thật cần ảnh data URI hoặc WebSocket, thêm quyền **đúng directive** (chẳng hạn `img-src 'self' data:` hoặc `connect-src 'self' wss://realtime.example`) sau khi xác minh nguyên nhân. Không tự động mở `data:` cho mọi loại tài nguyên.

### 3.1. Cấu hình Servlet với Spring Security

Spring Security không tự sinh một CSP phù hợp cho mọi ứng dụng. Phải khai báo chính sách trong `SecurityFilterChain` đang xử lý trang:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    private static final String CSP = String.join("; ",
        "default-src 'none'",
        "base-uri 'none'",
        "object-src 'none'",
        "script-src 'self' https://cdn.metrics.example",
        "connect-src 'self' https://api.metrics.example",
        "img-src 'self' https://img.metrics.example",
        "style-src 'self'",
        "font-src 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'"
    );

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp.policyDirectives(CSP))
        );

        // Ghép cấu hình trên vào chain đã có xác thực, phân quyền,
        // CSRF, CORS và quản lý session của ứng dụng.
        return http.build();
    }
}
~~~

Một file HTML tương ứng:

~~~html
<link rel="stylesheet" href="/css/app.css">

<script src="/js/app.js" defer></script>
<script src="/js/dashboard.js" defer></script>
<script src="https://cdn.metrics.example/sdk.js" defer></script>
~~~

Ở phương án này, inline script như `<script>initDashboard()</script>` sẽ bị chặn. Di chuyển đoạn khởi tạo sang `/js/dashboard.js`; thay `onclick="save()"` bằng `addEventListener("click", save)` trong JavaScript tách file.

**Điểm giới hạn của allowlist:** Nếu một origin được phép có thể cung cấp nội dung script tùy ý (ví dụ endpoint upload JSONP cũ hoặc đường dẫn do người dùng kiểm soát), attacker có thể tận dụng origin đó để chạy mã. Vì vậy chỉ liệt kê host có uy tín vẫn chưa đạt mức chống XSS mạnh như strict CSP dựa trên nonce/hash. Việc tự lưu trữ và kiểm soát một bản SDK đã kiểm định có thể giảm phụ thuộc vào nguồn thay đổi bên ngoài, nhưng vẫn phải cập nhật bảo mật.

### 3.2. Nếu dùng Spring WebFlux

Cú pháp cho chính sách tĩnh trên Reactive tương tự, nhưng dùng `SecurityWebFilterChain` và `ServerHttpSecurity`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    http.headers(headers -> headers
        .contentSecurityPolicy(csp -> csp.policyDirectives(CSP))
    );
    return http.build();
}
~~~

`CSP` ở đây là hằng chính sách tĩnh như trong ví dụ Servlet; phần khai báo xác thực và CSRF của WebFlux được tích hợp vào cùng chain. Không dùng Servlet `Filter` cho một ứng dụng WebFlux thuần; nếu cần nonce theo response, thiết kế tương ứng bằng `WebFilter` và truyền nonce qua context hoặc model của luồng reactive.

## 4. Phương án B: strict CSP dựa trên nonce khi trang có script động

Khi trang cần bootstrap inline được tạo bởi server hoặc SDK tải thêm script bằng `document.createElement("script")`, một phương án chặt hơn là cấp **nonce ngẫu nhiên cho từng HTTP response** và gắn nonce cho các script được server chọn trước.

Ví dụ khái niệm:

~~~http
Content-Security-Policy: default-src 'none'; base-uri 'none'; object-src 'none'; script-src 'nonce-GIA_TRI_NGAU_NHIEN' 'strict-dynamic' 'self' https://cdn.metrics.example; connect-src 'self' https://api.metrics.example; img-src 'self' https://img.metrics.example; style-src 'self'; font-src 'self'; form-action 'self'; frame-ancestors 'none'
~~~

Với CSP Level 3, `'strict-dynamic'` làm cho các script gốc có nonce/hash hợp lệ được phép tải thêm script bằng cách tạo phần tử script động. Đồng thời, trình duyệt hỗ trợ CSP3 sẽ **bỏ qua** `'self'` và các host allowlist ở `script-src` trong ví dụ. Do đó một thẻ script được parser đọc trực tiếp từ HTML vẫn **cần nonce**, dù URL ở `/js/app.js` hay ở CDN được liệt kê. Các host ở cuối chỉ đóng vai trò tương thích cho trình duyệt hỗ trợ mức CSP cũ hơn.

Không thêm `'strict-dynamic'` nếu không cần ủy quyền tải script động: nó cũng trao khả năng tải script cho SDK được tin cậy, khiến rủi ro tăng lên nếu SDK tự tạo URL script từ dữ liệu attacker điều khiển. Khi có thể cấp nonce cho tất cả thẻ script tĩnh và không có loader động, `script-src 'nonce-{NONCE}'` là lựa chọn đơn giản hơn.

### 4.1. Tạo nonce và đặt CSP header trên Servlet

Đoạn sau minh họa một `OncePerRequestFilter` tạo 16 byte (128 bit) bằng `SecureRandom`, mã hóa Base64, đưa nonce vào request attribute và đặt header **trước khi** trang được render:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.security.SecureRandom;
import java.util.Base64;

public final class CspNonceFilter extends OncePerRequestFilter {
    private final SecureRandom secureRandom = new SecureRandom();

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        byte[] randomBytes = new byte[16];
        secureRandom.nextBytes(randomBytes);
        String nonce = Base64.getEncoder().encodeToString(randomBytes);

        request.setAttribute("cspNonce", nonce);

        String policy = String.join("; ",
            "default-src 'none'",
            "base-uri 'none'",
            "object-src 'none'",
            "script-src 'nonce-" + nonce
                + "' 'strict-dynamic' 'self' https://cdn.metrics.example",
            "connect-src 'self' https://api.metrics.example",
            "img-src 'self' https://img.metrics.example",
            "style-src 'self'",
            "font-src 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'"
        );

        response.setHeader("Content-Security-Policy", policy);
        chain.doFilter(request, response);
    }
}
~~~

Gắn filter vào Security filter chain để nó có mặt trước khi request đến MVC controller và view:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.HeaderWriterFilter;

@Configuration
public class NonceSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.addFilterBefore(new CspNonceFilter(), HeaderWriterFilter.class);

        // Giữ cấu hình xác thực, CSRF, phân quyền và header khác
        // của ứng dụng trong SecurityFilterChain này.
        return http.build();
    }
}
~~~

Đây là **phương án thay thế** cho phần cấu hình `contentSecurityPolicy(...CSP)` tĩnh ở mục 3, không lắp đồng thời hai nơi phát CSP khác nhau vào cùng response. Với hệ thống có proxy/CDN cũng gắn CSP, cần chọn một điểm sở hữu header hoặc chủ động phối hợp nhiều policy: khi có nhiều header CSP, trình duyệt áp dụng **tất cả**, chính sách này không thể mở quyền bị chính sách khác chặn.

Trong ứng dụng Spring Boot, tránh vừa tự đăng ký `CspNonceFilter` như Servlet filter toàn cục, vừa đưa cùng filter vào Spring Security chain; ví dụ trên chỉ khởi tạo filter trực tiếp trong chain. Nếu có nhiều `SecurityFilterChain`, chain xử lý trang HTML phải chứa filter này.

### 4.2. Đưa nonce vào template một cách có kiểm soát

Với Spring MVC và Thymeleaf, controller đưa thuộc tính của request vào model:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class DashboardController {
    @GetMapping("/dashboard")
    public String dashboard(HttpServletRequest request, Model model) {
        model.addAttribute("cspNonce", request.getAttribute("cspNonce"));
        return "dashboard";
    }
}
~~~

Trong `dashboard.html`, chỉ gắn nonce vào các script do template tin cậy khai báo:

~~~html
<script th:src="@{/js/app.js}" th:attr="nonce=${cspNonce}" defer></script>
<script src="https://cdn.metrics.example/sdk.js"
        th:attr="nonce=${cspNonce}" defer></script>
~~~

Nếu script nội bộ cần bootstrap inline hợp lệ, nonce có thể gắn lên đúng thẻ `<script>` được server khai báo. Tuy nhiên ưu tiên chuyển code sang file riêng khi có thể, vì dễ quản lý, kiểm thử và cache asset.

Các bất biến phải bảo đảm:

- Nonce dùng cùng giá trị trong **header và các thẻ script được phép của một response**; response khác sinh giá trị mới, không dùng hằng số, timestamp hoặc giá trị có thể đoán.
- Không thêm nonce bằng cách thay thế văn bản mọi chuỗi `<script>` trong HTML sau khi đã render; làm vậy có thể vô tình cấp nonce cho thẻ do attacker chèn.
- Không đặt nonce vào dữ liệu public, cache dùng chung hoặc đoạn HTML được tái sử dụng cho nhiều người. Với trang HTML sinh nonce động, cần cấu hình cache phù hợp (thường là response cá nhân hóa không cache ở shared CDN).
- Khi ứng dụng render lỗi, redirect hoặc HTML qua một chain khác, kiểm tra header và nonce thực tế của từng đường đi.
- Nonce cho script không tự cấp quyền cho `fetch`, ảnh, font hay iframe; những tài nguyên này vẫn theo các directive riêng.

### 4.3. Lựa chọn hash, nonce và Subresource Integrity

| Cơ chế | Khi nào phù hợp | Điều cần lưu ý |
|---|---|---|
| `'self'` + host allowlist | Trang chỉ tải file script từ tập origin kiểm soát được | Origin được cho phép có thể mang nhiều nội dung hơn dự kiến; khó chống bypass qua host đáng tin nhưng có endpoint nguy hiểm. |
| `'nonce-...'` | HTML sinh động, server chọn script nào được chạy | Nonce phải mới cho từng response, được gắn nhất quán vào header và markup. |
| `'sha256-...'` trong CSP | Một đoạn inline script cố định, không thuận tiện sinh nonce | Hash phụ thuộc chính xác vào nội dung script, kể cả khoảng trắng; thay script phải cập nhật hash. |
| `'strict-dynamic'` | Script tin cậy cần tạo và tải script khác động | Truyền quyền tải script cho code đã tin cậy; cân nhắc riêng với SDK bên ngoài. |
| Thuộc tính `integrity` (SRI) | Tải một file CDN có nội dung và phiên bản cố định | Giúp phát hiện file bị thay đổi so với hash dự kiến; không thay thế CSP và cần cấu hình CORS thích hợp cho tài nguyên cross-origin. |

SRI và CSP giải quyết các vấn đề khác nhau: SRI xác nhận nội dung tài nguyên tải từ CDN khớp hash dự kiến, còn CSP quyết định trình duyệt có được tải/thực thi loại tài nguyên từ nguồn đó hay không. Với SDK được nhà cung cấp cập nhật thường xuyên qua cùng URL, cần đánh giá rủi ro thay đổi nội dung, cơ chế pin phiên bản và phương án fallback trước khi chọn SRI.

## 5. Thử chính sách trên trình duyệt và bằng Spring Security test

Một bài CSP chỉ hoàn thành khi cả kịch bản được phép lẫn kịch bản tấn công giả lập đều cho kết quả dự kiến. Hãy chạy thử trên bản staging tương đương production, mở **Network → Headers** để xem response HTML và **Console** để tìm lỗi CSP.

| Ca thử | Hành động | Kết quả kỳ vọng |
|---|---|---|
| T1 | Tải `/js/app.js` | Hoạt động bình thường. Với strict CSP, thẻ script có nonce. |
| T2 | Tải `https://cdn.metrics.example/sdk.js` | Hoạt động nếu thẻ script phù hợp policy. |
| T3 | SDK gọi `https://api.metrics.example/v1/events` | Qua `connect-src`; server vẫn phải đáp ứng CORS nếu đây là request cross-origin. |
| T4 | SDK tải `https://img.metrics.example/pixel.gif` | Qua `img-src`. |
| T5 | Chèn thử `<script>alert(1)</script>` vào vùng dữ liệu không tin cậy | Không thực thi; ghi nhận vi phạm `script-src`. |
| T6 | Thêm `onclick="alert(1)"` vào phần tử | Không thực thi khi không cho phép inline handler. |
| T7 | Tải `https://unexpected.example/x.js` từ HTML | Bị chặn, kể cả khi server CDN bên ngoài trả HTTP 200. |
| T8 | Gọi `fetch("https://unexpected.example/data")` | Bị chặn bởi `connect-src`. |
| T9 | Thử `eval("2 + 2")` từ script đã được phép | Bị CSP chặn do không có `'unsafe-eval'`. |
| T10 | Gắn trang quản trị vào một iframe từ origin khác | Bị chặn bởi `frame-ancestors 'none'`. |
| T11 | Tải HTML hai lần ở phương án nonce | Hai response có nonce khác nhau; nonce mỗi response khớp thẻ script tương ứng. |
| T12 | Script được nonce tải thêm script bằng DOM ở chế độ `'strict-dynamic'` | Script con có thể chạy nếu được loader tin cậy tạo đúng cách; kiểm tra cả nguồn mà SDK tải tiếp. |

**Giới hạn của kiểm thử:** MockMvc/WebTestClient xác nhận header được phát ra; chúng không thực thi chính sách trình duyệt. Kiểm thử chặn script, iframe và tải tài nguyên cần trình duyệt thật hoặc công cụ browser automation.

Ví dụ với MockMvc để phát hiện mất CSP do sửa cấu hình chain:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

@SpringBootTest
@AutoConfigureMockMvc
class CspHeaderTest {
    @Autowired MockMvc mvc;

    @Test
    void htmlResponseHasCsp() throws Exception {
        mvc.perform(get("/dashboard"))
            .andExpect(header().string("Content-Security-Policy",
                containsString("object-src 'none'")));
    }
}
~~~

Thay `/dashboard` bằng endpoint HTML thực sự đi qua chain cần kiểm tra, đồng thời chuẩn bị authentication/test user nếu route yêu cầu đăng nhập. Với phương án nonce, bổ sung assertion header chứa `'nonce-` và thử hai response để đảm bảo nonce không tái sử dụng. Không đặt giá trị nonce cụ thể vào test vì nó phải ngẫu nhiên.

## 6. Triển khai an toàn bằng Report-Only

Trước khi đưa CSP vào chế độ chặn, phát policy dự định dưới header `Content-Security-Policy-Report-Only`. Spring Security hỗ trợ trực tiếp:

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(CSP + "; report-uri /csp-report; report-to csp-endpoint")
        .reportOnly()
    )
);
~~~

Cấu hình HTTP reporting endpoint tương ứng (nếu hỗ trợ `report-to`):

~~~http
Reporting-Endpoints: csp-endpoint="https://portal.example/csp-report"
Content-Security-Policy-Report-Only: default-src 'none'; script-src 'self' https://cdn.metrics.example; object-src 'none'; base-uri 'none'; report-uri /csp-report; report-to csp-endpoint
~~~

Đây là minh họa cho **chính sách tĩnh**. Endpoint `/csp-report` phải được triển khai trước khi bật thu thập: tiếp nhận POST hợp lệ của `application/csp-report` (cơ chế cũ) và `application/reports+json` (Reporting API), giới hạn kích thước/rate, loại bỏ dữ liệu nhạy cảm khỏi log và không tin nội dung báo cáo do client gửi. Nếu Spring Security đang bật CSRF, cần xử lý riêng POST report vốn không có CSRF token; chỉ cân nhắc bỏ yêu cầu token cho đúng endpoint nhận report vô trạng thái và có biện pháp chống lạm dụng. `report-uri` đang được thay thế bởi `report-to` nhưng vẫn thường được cấu hình song song vì khả năng hỗ trợ trên trình duyệt khác nhau.

Trình tự triển khai:

1. **Inventory:** ghi nhận tất cả script, request, ảnh, style, iframe thực sự được trang dùng; loại script không còn cần.
2. **Report-Only:** đưa chính sách ứng viên lên staging; tập hợp report theo trang, browser, `effective-directive` và `blocked-uri`.
3. **Phân loại:** phân biệt tài nguyên hợp lệ bị chặn, extension của người dùng, lỗi cấu hình và script bất thường. Chỉ thêm origin có bằng chứng sử dụng và chủ sở hữu rõ ràng.
4. **Enforce:** đổi sang `Content-Security-Policy` sau khi chức năng chính hoạt động và chính sách ổn định; tiếp tục quan sát lỗi Console, report và luồng đăng nhập/thanh toán.
5. **Hồi quy:** chạy lại bộ test khi bổ sung SDK, đổi CDN, thay bundle, nâng cấp Spring Security hoặc sửa cơ chế render trang.

Có thể chạy **đồng thời** policy hiện hành dạng Enforce và một policy đề xuất chặt hơn dạng Report-Only để đánh giá thay đổi tiếp theo. Khi test nonce bằng Report-Only phải dùng cùng logic phát nonce cho markup; nonce không khớp sẽ tạo report ngay cả với script hợp lệ.

## 7. Chẩn đoán lỗi tích hợp thường gặp

| Triệu chứng | Nguyên nhân có khả năng cao | Cách xử lý |
|---|---|---|
| Script nội bộ bị chặn sau khi bật `'strict-dynamic'` | Thẻ script ở HTML thiếu nonce; trình duyệt CSP3 bỏ qua `'self'` trong `script-src` | Gắn nonce từ đúng response vào thẻ script gốc hoặc điều chỉnh chiến lược CSP. |
| SDK tải được nhưng `fetch` trả thông báo CSP violation | `connect-src` không chứa origin API | Bổ sung origin API được kiểm chứng vào `connect-src`; sau đó kiểm tra riêng CORS. |
| `fetch` qua CSP nhưng trình duyệt vẫn báo lỗi CORS | Server API không cho phép origin/method/header tương ứng theo CORS | Cấu hình CORS phía server API; CSP không cấp quyền đọc response cross-origin. |
| SDK không hiện giao diện | SDK cần CSS inline, frame, worker, ảnh hoặc script con chưa được kiểm kê | Đọc violation report theo directive; xin danh sách domain và yêu cầu kỹ thuật từ vendor; chỉ mở quyền cần thiết. |
| Trang hoạt động ở staging nhưng hỏng sau CDN/proxy | Proxy ghi đè CSP, nhiều CSP được áp dụng đồng thời, hoặc HTML nonce bị cache | Kiểm tra raw headers của response cuối cùng, cấu hình proxy và cache của HTML. |
| `nonce` xuất hiện trong header nhưng script vẫn bị chặn | Header và HTML dùng nonce khác nhau, nonce thiếu ở thẻ hoặc được sinh sau thời điểm render | Lấy nonce từ một request attribute/model duy nhất cho mỗi response. |
| Inline `onclick` hoặc `eval` bị chặn | Code còn phụ thuộc cách thực thi bị CSP hạn chế | Chuyển event handler sang JS tách file, bỏ `eval`; không mở `'unsafe-inline'` hay `'unsafe-eval'` để chữa nhanh. |
| Có hàng loạt report từ trình duyệt cá nhân | Extension, ad blocker hoặc môi trường browser khác nhau | Đối chiếu user agent, document URL và đường đi thực tế; không tự động thêm host lạ vào allowlist. |

Những lưu ý trong triển khai Spring Security:

- **Nhiều SecurityFilterChain:** request chỉ dùng chain đầu tiên khớp matcher. Kiểm tra chain phục vụ HTML, logout, error page và các route khác cần CSP; tránh chỉ cấu hình cho API.
- **Reverse proxy:** header cuối cùng mới quyết định hành vi browser. Hai CSP enforced cùng xuất hiện sẽ cùng được áp dụng, không phải policy đứng sau ghi đè quyền của policy trước trong browser.
- **CSP so với CSRF/CORS:** CSP quyết định những tài nguyên và hành động trang được phép sử dụng. CSRF bảo vệ các thao tác có trạng thái khỏi request giả mạo; CORS quyết định script cross-origin có được đọc response hay không. Ba cơ chế bổ trợ nhau.
- **CSP so với XSS:** tiếp tục encode output đúng ngữ cảnh, kiểm soát đầu vào và tránh DOM API nguy hiểm như gán HTML không tin cậy vào `innerHTML`. CSP là lớp giảm thiểu tác hại khi cơ chế khác sơ suất, không thay thế việc sửa nguồn XSS.
- **SDK ngoài:** cần xem xét cập nhật phiên bản, hợp đồng xử lý dữ liệu, quyền truy cập DOM và hiệu ứng khi CDN bị xâm nhập. Tắt SDK khỏi trang nhạy cảm nếu không cần.

## 8. Bài tập áp dụng và tiêu chí hoàn thành

**Bài tập 1 — Lập policy:** Cho trang có `/js/app.js`, SDK ở `https://cdn.metrics.example`, API ở `https://api.metrics.example` và ảnh ở `https://img.metrics.example`. Hãy viết CSP chặn inline JS, `eval` và script từ origin lạ. Đối chiếu với policy ở mục 3, giải thích vì sao phải khai báo `connect-src` riêng.

**Bài tập 2 — Nâng lên nonce:** Giả sử SDK tạo thêm phần tử script bằng JavaScript. Hãy chuyển sang policy dựa trên nonce, xác định chỗ sinh nonce, vị trí gắn `nonce` trong template và cân nhắc có thật sự cần `'strict-dynamic'` hay không. Kiểm tra hai response liên tiếp và chứng minh nonce thay đổi.

**Bài tập 3 — Điều tra lỗi:** Sau deploy, `/js/app.js` bị chặn dù có `'self'`, trong khi API đo lường cũng thất bại. Với mỗi lỗi, hãy đọc `effective-directive` và `blocked-uri`, giải thích nguyên nhân liên quan đến `'strict-dynamic'` hoặc `connect-src`, rồi đưa ra sửa đổi tối thiểu.

**Tiêu chí nghiệm thu:**

- Response HTML cuối cùng có đúng header CSP cho môi trường đã chọn; không có cấu hình CSP trùng lặp ngoài ý muốn.
- Script nội bộ và SDK đã kiểm duyệt chạy được; các request `fetch`/ảnh thật được phân loại đúng directive.
- Inline script không có nonce/hash, event handler inline, `eval` và script nguồn lạ không được thực thi trong chế độ Enforce.
- Nếu dùng nonce, giá trị đủ ngẫu nhiên, thay đổi từng response và khớp các thẻ script được phép.
- Report-Only đã được quan sát trước khi enforce; các ngoại lệ được giải thích bằng nhu cầu chức năng và bằng chứng kỹ thuật.
- Không làm mất cấu hình xác thực, CSRF, CORS và security headers khác của Spring Security khi tích hợp CSP.

## 9. Tài liệu tham khảo

- [Spring Security — Security HTTP Response Headers (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security — Security HTTP Response Headers (Reactive)](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html)
- [MDN — Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)
- [MDN — script-src và strict-dynamic](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src)
- [OWASP Cheat Sheet — Content Security Policy](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html)
- [W3C — Content Security Policy Level 3](https://www.w3.org/TR/CSP3/)
