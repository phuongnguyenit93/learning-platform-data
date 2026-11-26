# Nonce riêng cho phản hồi cùng cách truyền vào template

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình trên Servlet và Reactive, kiểm thử kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Bài toán: trang cần script inline hợp lệ nhưng CSP phải chặn script bị chèn

Hãy xét một ứng dụng Spring MVC dùng Thymeleaf. Trang dashboard có đoạn khởi tạo nhỏ ngay trong HTML:

~~~html
<script>
  initializeDashboard();
</script>
~~~

Ứng dụng muốn đặt CSP:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'
~~~

Chính sách `script-src 'self'` cho phép tải tệp JavaScript từ cùng origin, **không tự cho phép** khối `<script>...</script>` nội tuyến. Do đó, trình duyệt sẽ chặn đoạn khởi tạo trong ví dụ. Nới lỏng bằng `'unsafe-inline'` khiến nhiều đoạn script do kẻ tấn công chèn cũng có cơ hội chạy, làm giảm đáng kể hiệu quả CSP đối với XSS.

Giải pháp có kiểm soát là **nonce** (*number used once*): server tạo giá trị ngẫu nhiên mới cho **mỗi HTTP response chứa HTML cần script/style nội tuyến**, công bố giá trị đó trong CSP header và gắn đúng giá trị lên các phần tử `<script>` hoặc `<style>` mà ứng dụng tin cậy.

Ví dụ minh họa:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-DEMO_NONCE'; style-src 'self' 'nonce-DEMO_NONCE'; object-src 'none'; base-uri 'self'
~~~

~~~html
<script nonce="DEMO_NONCE">
  initializeDashboard();
</script>
~~~

`DEMO_NONCE` ở đây chỉ để thấy hai vị trí phải **khớp nhau**; dùng chuỗi cố định như vậy trong sản xuất là sai. Giá trị nonce thật cần có độ ngẫu nhiên mạnh, không thể đoán trước và được tạo lại cho từng response.

Đích của bài học:

1. Phân biệt nonce theo **response HTML** với giá trị cố định theo ứng dụng, phiên đăng nhập hoặc request API.
2. Giải thích chính sách CSP, vòng đời tạo nonce và việc truyền nonce vào template.
3. Triển khai một cách tiếp cận thống nhất trên Spring Security Servlet/Thymeleaf và Reactive/WebFlux.
4. Kiểm tra rằng nonce của CSP header **khớp HTML trong cùng response**, đồng thời khác ở các response độc lập.
5. Chẩn đoán vấn đề thực tế về filter order, nhiều CSP header, cache, trang lỗi và template không an toàn.

## 2. Nonce cấp quyền cho những gì?

Ví dụ một trang có bốn cách đưa mã vào:

~~~html
<!-- 1. Thẻ script inline do ứng dụng sở hữu -->
<script nonce="NONCE_MATCHES_HEADER">
  initializeDashboard();
</script>

<!-- 2. Script inline không có nonce -->
<script>alert("untrusted");</script>

<!-- 3. Inline event handler -->
<button onclick="alert('clicked')">Bấm</button>

<!-- 4. Inline style attribute -->
<div style="color: red">Thông báo</div>
~~~

Nếu CSP quy định `script-src 'self' 'nonce-NONCE_MATCHES_HEADER'` và `style-src 'self' 'nonce-NONCE_MATCHES_HEADER'`, với trình duyệt hỗ trợ nonce:

| Nội dung | Kết quả kỳ vọng | Giải thích |
|---|---|---|
| Thẻ `<script>` có nonce khớp | Được phép thực thi theo CSP | Phần tử tin cậy có nonce phù hợp |
| Thẻ `<script>` không có nonce/hash hợp lệ | Bị chặn | Không có cấp phép inline |
| `onclick="..."` hoặc `onerror="..."` | Bị chặn khi không có quy tắc khác cho phép | Nonce của `<script>` không áp dụng cho event handler |
| Thẻ `<style nonce="...">` | Được phép theo CSP nếu `style-src` cho nonce đó | Phần tử style có nonce khớp |
| Thuộc tính `style="..."` | Không được nonce cấp phép | Thuộc tính style khác với thẻ `<style>` |

**Nonce không tự sửa lỗi HTML injection.** Nếu ứng dụng đưa chuỗi không đáng tin vào DOM như HTML, kẻ tấn công vẫn có thể chèn nội dung giả mạo hoặc lợi dụng những đường thực thi còn được cho phép. Cần escape dữ liệu theo ngữ cảnh, dùng template an toàn và sanitize HTML khi sản phẩm thật sự cho phép nhập HTML.

Một điểm dễ bị bỏ qua: nonce trên thẻ `<script>` có thể cấp quyền cho **script element**, kể cả một số thẻ tải script ngoài. Vì vậy, không tự động gắn nonce vào *mọi* thẻ script có trong HTML mà không kiểm soát nguồn hoặc nội dung. Chỉ thêm nonce cho những phần tử mà ứng dụng sở hữu và tin cậy.

### Nonce không phải là mật khẩu

Nonce không phải access token, session ID, CSRF token hay secret dài hạn. Nó được gửi tới trình duyệt qua CSP header và HTML của response. Những script đã chạy với quyền hợp lệ trong tài liệu có thể truy cập ngữ cảnh DOM, nên nonce **không bảo vệ được trước mã độc đã được phép thực thi**. Giá trị của nonce nằm ở chỗ kẻ tấn công chỉ chèn markup không đáng tin thì khó đoán được nonce mới của response hiện tại.

## 3. Vòng đời của một nonce cho mỗi response

Một triển khai đúng cần tạo nonce **trước khi template được render**, đồng thời xuất CSP header **trước khi HTTP response được commit**:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as Filter hoặc WebFilter
    participant C as Controller
    participant T as Template renderer
    B->>F: GET /dashboard
    F->>F: Tạo nonce ngẫu nhiên mới
    F->>F: Lưu nonce trong ngữ cảnh request
    F->>F: Đặt CSP header chứa nonce
    F->>C: Chuyển request
    C->>T: Truyền nonce vào model
    T->>T: Gắn nonce lên script/style tin cậy
    T-->>B: HTML cùng CSP header đã khớp nonce
    Note over B: Browser chỉ chạy phần tử phù hợp CSP
~~~

Với hai lượt tải trang độc lập:

| Response | CSP header | HTML được render |
|---|---|---|
| Lần A | `script-src 'nonce-A_RANDOM_VALUE'` | `<script nonce="A_RANDOM_VALUE">` |
| Lần B | `script-src 'nonce-B_RANDOM_VALUE'` | `<script nonce="B_RANDOM_VALUE">` |

Giá trị A và B **phải khác nhau với xác suất cực cao**; chúng không được tạo bằng một hằng cố định, tên người dùng, session ID hay timestamp dễ đoán. Trong mỗi lần tải, CSP header và HTML phải sử dụng **chính xác cùng nonce**.

### “Mỗi response” không đồng nghĩa “mỗi dòng JavaScript”

Nếu một response có ba khối script hợp lệ, chúng có thể **dùng chung nonce của response ấy**. Không cần tạo nonce riêng cho từng thẻ:

~~~html
<script nonce="SAME_NONCE_IN_THIS_RESPONSE">initA();</script>
<script nonce="SAME_NONCE_IN_THIS_RESPONSE">initB();</script>
<style nonce="SAME_NONCE_IN_THIS_RESPONSE">.banner { color: navy; }</style>
~~~

Trong một ứng dụng SPA, điều hướng phía client có thể không tạo tài liệu HTML mới; nonce đã cấp thuộc về **tài liệu hiện tại**. Khi server gửi response HTML mới cho một lần tải tài liệu khác, nonce mới được tạo cho response mới. Không cần thay nonce theo từng `fetch` API chỉ trả JSON.

## 4. Tạo nonce bằng SecureRandom trong Java

Một hàm sinh nonce nên dùng bộ sinh ngẫu nhiên mật mã học. Ví dụ Java:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class CspNonce {
    public static final String ATTRIBUTE = CspNonce.class.getName() + ".nonce";
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    private CspNonce() { }

    public static String create() {
        byte[] bytes = new byte[24]; // 192 bit ngẫu nhiên
        SECURE_RANDOM.nextBytes(bytes);
        return Base64.getEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }

    public static String policy(String nonce) {
        return "default-src 'self'; " +
                "script-src 'self' 'nonce-" + nonce + "'; " +
                "script-src-attr 'none'; " +
                "style-src 'self' 'nonce-" + nonce + "'; " +
                "style-src-attr 'none'; " +
                "img-src 'self'; " +
                "font-src 'self'; " +
                "connect-src 'self'; " +
                "object-src 'none'; " +
                "base-uri 'self'; " +
                "form-action 'self'; " +
                "frame-ancestors 'none'";
    }
}
~~~

`CspNonce.create()` tạo một chuỗi Base64 khác nhau ở mỗi lần gọi; 24 byte ngẫu nhiên cung cấp 192 bit entropy trước khi mã hóa. Base64 chỉ là **biểu diễn**, không làm tăng độ ngẫu nhiên. Một nonce ít entropy dù được Base64 hóa vẫn có thể bị đoán.

`CspNonce.policy(nonce)` đặt nonce vào cả `script-src` và `style-src`. Đây là policy minh họa cho trang dùng tài nguyên cùng origin; với CDN, API domain riêng, WebSocket hoặc iframe hợp lệ, ứng dụng phải bổ sung đúng directive cần thiết. Không ghép host hoặc giá trị nonce do người dùng gửi trực tiếp vào header. Đầu vào nonce của hàm trên chỉ đến từ `SecureRandom`.

Lớp `CspNonce` không chứa HTTP API, vì thế có thể dùng lại cách làm trên cả Servlet và WebFlux. Trong dự án thật, hãy đặt nó tại package phù hợp và giữ một nơi kiểm soát cấu hình policy.

## 5. Spring Security Servlet: tạo nonce trong filter rồi truyền cho Thymeleaf

Trong Spring MVC/Servlet, `OncePerRequestFilter` có thể tạo nonce, đặt nó thành thuộc tính của `HttpServletRequest` và ghi CSP header trước khi MVC controller render template.

### 5.1. Filter tạo nonce và CSP header

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

public final class CspNonceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        String nonce = CspNonce.create();

        // Request scope: model/template của đúng response này sẽ đọc giá trị.
        request.setAttribute(CspNonce.ATTRIBUTE, nonce);

        // Header phải được đặt trước khi response HTML được commit.
        response.setHeader("Content-Security-Policy", CspNonce.policy(nonce));

        filterChain.doFilter(request, response);
    }
}
~~~

Filter ghi một header CSP cho response đi qua nó. Các mặc định security header khác của Spring Security vẫn có thể hoạt động. **Không cấu hình một policy CSP tĩnh khác trên cùng response** nếu chưa có chủ đích: nhiều policy thực thi đồng thời có thể làm script có nonce vẫn bị chặn.

Ví dụ trên sử dụng `OncePerRequestFilter` và không tự phân biệt trang HTML với API, file tĩnh hay redirect. Để triển khai chính xác, cần xác định security chain, loại response và hành vi khi redirect/error/async; chỉ đặt chính sách trên phạm vi trang HTML do ứng dụng sở hữu nếu đó là yêu cầu của hệ thống. Tuy nhiên, ngay cả khi filter ghi CSP trên response JSON, điều đó **không thiết lập CSP cho trang HTML của origin khác**.

### 5.2. Đăng ký filter vào đúng SecurityFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.HeaderWriterFilter;

@Configuration
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        // HeaderWriterFilter là vị trí mốc trong filter chain của Spring Security.
        // CspNonceFilter ở trước nó để đặt nonce/header sớm.
        http.addFilterBefore(new CspNonceFilter(), HeaderWriterFilter.class);

        // Các quy tắc authorizeHttpRequests, CSRF, session... của ứng dụng
        // được cấu hình độc lập với phần tạo CSP nonce.
        return http.build();
    }
}
~~~

`new CspNonceFilter()` trong cấu hình này được đăng ký **trong Spring Security chain**. Tránh đồng thời đánh dấu filter đó là `@Component` hoặc đăng ký thêm một Servlet `FilterRegistrationBean` khiến nó chạy hai lần ở hai vị trí khác nhau. Trong ứng dụng có nhiều `SecurityFilterChain`, phải xác định chain xử lý các trang HTML cần nonce.

**Vì sao không dùng `contentSecurityPolicy(...).policyDirectives("...nonce...")` với chuỗi hằng?** DSL/header writer viết ra policy đã được cấu hình; nó không tự sinh nonce theo response và cũng không tự truyền nonce tới Thymeleaf. Một hằng `'nonce-fixed-value'` sẽ lặp lại qua nhiều response, làm mất tính khó đoán của nonce. Filter trên là ví dụ một cách tạo cả header và request attribute trong cùng luồng.

### 5.3. Truyền nonce vào model của controller

Controller Spring MVC lấy nonce từ request và đưa vào model:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class DashboardController {

    @GetMapping("/dashboard")
    public String dashboard(HttpServletRequest request, Model model) {
        String nonce = (String) request.getAttribute(CspNonce.ATTRIBUTE);
        if (nonce == null) {
            throw new IllegalStateException("CSP nonce was not initialized");
        }

        model.addAttribute("cspNonce", nonce);
        return "dashboard";
    }
}
~~~

Ví dụ này giả định filter đã chạy cho `/dashboard`. Nếu controller thấy `null`, đó là dấu hiệu cần kiểm tra phạm vi security chain, thứ tự filter hoặc cách phục vụ template thay vì âm thầm render một nonce cố định.

Với nhiều trang MVC, có thể trích bước đưa nonce vào model thành `@ControllerAdvice` có `@ModelAttribute` hoặc cơ chế model chung của ứng dụng. Dù chọn cách nào, chỉ có **một nonce đã được tạo** trong request được dùng để render từng response.

### 5.4. Gắn nonce vào template Thymeleaf

Trong `templates/dashboard.html`:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Dashboard</title>
    <link rel="stylesheet" th:href="@{/css/dashboard.css}">

    <!-- Chỉ cấp nonce cho style block do ứng dụng tin cậy -->
    <style th:attr="nonce=${cspNonce}">
        .dashboard-title { font-weight: 700; }
    </style>
</head>
<body>
    <h1 class="dashboard-title">Dashboard</h1>
    <button id="reload" type="button">Tải lại</button>

    <!-- Script cùng origin không cần nonce nếu phù hợp script-src 'self' -->
    <script th:src="@{/js/dashboard.js}" defer></script>

    <!-- Script inline tin cậy cần nonce khớp CSP header -->
    <script th:attr="nonce=${cspNonce}">
        window.dashboardInitialized = true;
    </script>
</body>
</html>
~~~

Sau render, trình duyệt nhận các thuộc tính `nonce="..."` chứa giá trị thật của response. `th:attr="nonce=${cspNonce}"` là cú pháp đưa model attribute vào HTML attribute; không đặt nguyên chuỗi `${cspNonce}` vào HTML tĩnh nếu không có Thymeleaf xử lý.

Chỉ gắn nonce cho các script/style mà ứng dụng **chủ động kiểm soát**. Không viết template tự động ghép nonce vào mọi đoạn HTML người dùng nhập hoặc mọi thẻ script được trích xuất từ nội dung không đáng tin. Nếu phải hiển thị comment dạng văn bản, dùng biểu thức Thymeleaf escape nội dung:

~~~html
<p th:text="${comment}"></p>
~~~

Tránh thay bằng `th:utext` đối với nội dung người dùng không được sanitize thích hợp: kể cả khi CSP chặn script, HTML injection vẫn có thể thay đổi nội dung giao diện.

## 6. Spring Security Reactive/WebFlux: nonce trong ServerWebExchange

WebFlux không có `HttpServletRequest` hoặc `OncePerRequestFilter`; nguyên tắc vẫn giống Servlet nhưng lớp bao quanh HTTP request là `ServerWebExchange`, còn thành phần xử lý xuyên suốt request là `WebFilter`.

### 6.1. WebFilter tạo nonce và CSP header

Sử dụng cùng tiện ích `CspNonce` đã định nghĩa ở mục 4:

~~~java
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public final class CspNonceWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String nonce = CspNonce.create();

        // Dữ liệu theo request/response, không phải biến instance dùng chung.
        exchange.getAttributes().put(CspNonce.ATTRIBUTE, nonce);

        exchange.getResponse().getHeaders().set(
                "Content-Security-Policy",
                CspNonce.policy(nonce)
        );

        return chain.filter(exchange);
    }
}
~~~

`@Order(Ordered.HIGHEST_PRECEDENCE)` đặt WebFilter ở giai đoạn sớm để header được thiết lập trước khi response commit; thứ tự thực tế còn phải được xem xét với các WebFilter khác trong ứng dụng. `@Component` đăng ký WebFilter với Spring một lần. Không đồng thời cấu hình một WebFilter khác sinh nonce hoặc header writer CSP tĩnh cho cùng response nếu chúng không được thiết kế phối hợp.

**Lưu ý khi xử lý Reactive:** mỗi lượt gọi `filter(...)` nhận một `ServerWebExchange` riêng. Nonce được đặt ở `exchange.getAttributes()`, không giữ trong biến field dùng chung hoặc `ThreadLocal`, vì quá trình reactive có thể chuyển execution context giữa các luồng. Một chuỗi Mono/Flux bất đồng bộ cần lấy nonce từ exchange/model phù hợp, không dựa vào “thread hiện tại”.

### 6.2. Controller WebFlux truyền nonce vào model

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.server.ServerWebExchange;

@Controller
public class ReactiveDashboardController {

    @GetMapping("/dashboard")
    public String dashboard(ServerWebExchange exchange, Model model) {
        String nonce = exchange.getAttribute(CspNonce.ATTRIBUTE);
        if (nonce == null) {
            throw new IllegalStateException("CSP nonce was not initialized");
        }

        model.addAttribute("cspNonce", nonce);
        return "dashboard";
    }
}
~~~

Với view renderer Thymeleaf dành cho WebFlux, template ở mục 5.4 sử dụng chính `${cspNonce}` trong model. Không có khác biệt về cú pháp nonce trong HTML: điểm khác nhau chỉ ở cách server lưu và truyền dữ liệu của response đến view.

### 6.3. Quan hệ với ServerHttpSecurity

CSP là một loại security header; Spring Security WebFlux cũng có DSL dạng:

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("default-src 'self'; script-src 'self'")
    )
);
~~~

Đoạn trên dùng **policy tĩnh**, nên không tự giải bài toán nonce. Trong cách triển khai WebFilter động ở mục 6.1, tránh đồng thời bật cấu hình CSP tĩnh như trên nếu chưa xác định rõ header cuối cùng và toàn bộ các CSP thực thi sẽ đến trình duyệt. Các cơ chế authentication/authorization, CSRF, CORS, HSTS và bảo vệ session có thể vẫn được cấu hình trong `ServerHttpSecurity` theo chức năng riêng.

## 7. Tại sao nonce không nên được lưu trong session, singleton hoặc database?

Một cách triển khai sai thường gặp là tạo nonce khi ứng dụng khởi động:

~~~java
// SAI: dùng một giá trị cho mọi response trong suốt vòng đời ứng dụng.
private static final String CSP_NONCE = CspNonce.create();
~~~

Hoặc lưu nonce trong HTTP session:

~~~java
// SAI: dùng chung nonce cố định cho các trang khác nhau của một phiên.
session.setAttribute("cspNonce", CspNonce.create());
~~~

Khi một nonce được lặp lại trong nhiều response, kẻ tấn công có thể có cơ hội biết hoặc dự đoán nó từ một trang đã xem trước đó, làm yếu mục tiêu “cấp phép cho response hiện tại”. Ngoài ra, nếu HTML và CSP header do các tầng khác nhau tạo, một nguồn nonce lâu dài có thể vô tình che khuất lỗi đồng bộ giữa header và template.

| Nơi lưu | Có nên dùng cho nonce CSP? | Lý do |
|---|---|---|
| Biến `static final`/singleton | Không | Tái sử dụng cố định giữa nhiều response |
| HTTP session | Không | Nonce tồn tại theo phiên thay vì theo response |
| Database/cache chia sẻ | Không để tái dùng nonce | Tăng rủi ro dùng lại và nhầm lẫn vòng đời |
| Servlet `request.setAttribute(...)` | Có | Dữ liệu gắn với HTTP request đang render HTML |
| Reactive `exchange.getAttributes()` | Có | Dữ liệu gắn với ServerWebExchange hiện tại |
| Template model | Có, với đúng request | Cầu nối từ code server tới phần tử inline được tin cậy |

Nonce không nhất thiết phải lưu lâu sau khi response đã được render. Việc lưu dữ liệu lâu dài còn tạo thêm bề mặt cần quản lý, trong khi browser chỉ cần nonce của tài liệu đã nhận.

## 8. Cache, CDN, ETag và response HTML chứa nonce

Nonce thay đổi theo response tạo ra xung đột tự nhiên với các hệ thống cache HTML có nội dung cố định. Xét một reverse proxy cache response lần đầu:

~~~http
Content-Security-Policy: script-src 'nonce-AAA'
~~~

~~~html
<script nonce="AAA">initializeDashboard();</script>
~~~

Nếu cache tiếp tục phát **chính xác cả header và body** này cho các client khác nhau, nonce `AAA` bị tái sử dụng. Nếu CDN thay riêng header thành `'nonce-BBB'` nhưng vẫn phát HTML `nonce="AAA"`, script inline sẽ bị chặn vì không khớp. Cả hai đều là cách triển khai cần tránh.

Những lựa chọn kiến trúc:

- Với trang HTML động/sensitive, cân nhắc cache policy phù hợp, ví dụ `Cache-Control: private, no-store` nếu ứng dụng thực sự yêu cầu tránh lưu trữ. Không đặt `no-store` cho mọi tài nguyên tĩnh khi không cần.
- Cache các **tệp JS/CSS tĩnh** bình thường; nonce thường liên quan đến response HTML, không đòi hỏi tái tạo nội dung của file JS/CSS cho mỗi request.
- Nếu muốn cache HTML chung ở CDN, phải có chiến lược tạo nonce và **biến đổi header lẫn HTML đồng bộ** cho từng response được phục vụ; việc thay riêng một phía không đủ.
- Khi có `ETag`, `304 Not Modified`, edge-side rendering hoặc template streaming, cần xác định cách browser ghép body/metadata từ cache, để bảo đảm CSP và nonce trong body không bị lệch hoặc lặp lâu dài.
- Một phương án khác cho script inline **ổn định** là CSP **hash**, vốn không phụ thuộc vào nonce khác nhau theo từng response; nếu có thể chuyển code inline ra file JS/CSS, đó thường là lựa chọn dễ cache nhất.

**Quy tắc kiểm tra thực tế:** đọc *response HTML được trình duyệt nhận*, không chỉ biến `nonce` trong server log. Khi có proxy/CDN, so sánh header cuối cùng và markup cuối cùng ở cùng lượt tải.

## 9. Những luồng dễ bỏ sót: login, error, redirect và streaming

Trong ứng dụng thực tế, không phải mọi HTML đều đi qua một controller đơn giản:

| Tình huống | Điều có thể xảy ra | Hướng kiểm tra |
|---|---|---|
| Trang login của Spring Security | HTML do filter/framework tạo, không phải controller Thymeleaf của bạn | Kiểm tra CSP và cách tạo nonce riêng cho form đăng nhập thực tế |
| Trang lỗi 404/500 | Error dispatch có thể đi qua filter chain khác hoặc do container/proxy trả | Xác minh header và nội dung lỗi; không giả định filter MVC luôn chạy |
| Redirect 302 rồi GET trang đích | Có hai HTTP response khác nhau | Chính sách HTML quan trọng nằm ở response trang đích; đừng tái dùng nonce giữa response |
| Controller async/streaming | Header có thể bị commit trước khi khối HTML cuối được ghi | Tạo nonce/đặt CSP từ sớm; tránh sửa header sau commit |
| Nhiều SecurityFilterChain | Route trang bị xử lý bởi chain khác với chain đăng ký filter | Xác định chain khớp route HTML và test tại route đó |
| Frontend ở CDN, API ở Spring Boot | HTML do CDN trả, API chỉ trả JSON | CSP phải được đặt tại nơi phục vụ HTML; API header không áp policy cho tài liệu frontend |
| HTML có fragment động hoặc widget bên thứ ba | Fragment có thể không nhận cùng nonce | Thiết kế điểm truyền nonce rõ ràng và chỉ cấp cho fragment/script tin cậy |

Trong Servlet, `OncePerRequestFilter` có quy tắc riêng về async/error dispatch; không nên cho rằng một filter mẫu tự chạy ở mọi đường lỗi. Trong WebFlux, thứ tự WebFilter và điểm commit response cũng ảnh hưởng. Kiểm thử theo **loại response người dùng thực sự nhìn thấy** để tránh bảo vệ thiếu trang quan trọng.

## 10. Kiểm thử: nonce khác nhau giữa response, khớp trong cùng response

Chỉ kiểm tra sự hiện diện của header CSP là chưa đủ. Một test đúng cần xác nhận **mối liên hệ giữa header và HTML**.

### 10.1. Integration test với Spring MVC/MockMvc

Giả sử ứng dụng đã có route `/dashboard`, controller ở mục 5 và test cấu hình cho phép gửi request tới route đó:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

@SpringBootTest
@AutoConfigureMockMvc
class CspNonceIntegrationTest {

    private static final Pattern NONCE_PATTERN =
            Pattern.compile("'nonce-([A-Za-z0-9+/]+)'");

    @Autowired
    MockMvc mvc;

    private String assertMatchingNonce() throws Exception {
        MvcResult result = mvc.perform(get("/dashboard")).andReturn();
        assertEquals(200, result.getResponse().getStatus());

        String policy = result.getResponse()
                .getHeader("Content-Security-Policy");
        assertNotNull(policy);

        Matcher matcher = NONCE_PATTERN.matcher(policy);
        assertTrue(matcher.find(), "CSP header must contain a nonce");
        String nonce = matcher.group(1);

        String html = result.getResponse().getContentAsString();
        assertTrue(html.contains("nonce=\"" + nonce + "\""),
                "HTML nonce must match the nonce in CSP header");
        return nonce;
    }

    @Test
    void nonceMatchesHtmlAndChangesBetweenResponses() throws Exception {
        String nonceA = assertMatchingNonce();
        String nonceB = assertMatchingNonce();
        assertNotEquals(nonceA, nonceB,
                "Two independent responses must use fresh nonces");
    }
}
~~~

Nếu route yêu cầu đăng nhập, test phải thiết lập mock authentication phù hợp trước khi yêu cầu status 200; nếu không, HTTP 302/401/403 là kết quả về authorization, chưa phản ánh tính đúng sai của nonce.

**Giới hạn của test:** kiểm tra server tạo và truyền nonce nhất quán. Nó không chứng minh trình duyệt đã chặn mọi kiểu XSS. Cần chạy thử ở browser và đánh giá script được phép/thực sự bị chặn.

### 10.2. Kiểm tra với WebFlux/WebTestClient

Trong một test WebFlux đã có `WebTestClient` kết nối tới route HTML:

~~~java
import org.springframework.test.web.reactive.server.EntityExchangeResult;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.*;

EntityExchangeResult<String> result = webTestClient.get()
    .uri("/dashboard")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class)
    .returnResult();

String policy = result.getResponseHeaders()
    .getFirst("Content-Security-Policy");
assertNotNull(policy);

Matcher matcher = Pattern
    .compile("'nonce-([A-Za-z0-9+/]+)'")
    .matcher(policy);
assertTrue(matcher.find());
assertTrue(result.getResponseBody()
    .contains("nonce=\"" + matcher.group(1) + "\""));
~~~

Cần thêm một lượt GET độc lập và so sánh nonce như bài test Servlet. Nếu ứng dụng dùng HTML streaming, body có thể được đọc theo cách khác; chọn công cụ test phù hợp với kiểu response đó.

### 10.3. Kiểm tra thủ công trong trình duyệt

1. Mở DevTools → Network; chọn request tài liệu HTML, xem `Response Headers` và tìm `script-src 'nonce-...'`.
2. Xem phần HTML của **đúng response** ấy; xác nhận thẻ `<script>`/`<style>` tin cậy có nonce khớp. Một số trình duyệt che giá trị `nonce` khi dùng DOM `getAttribute`, nên hãy kiểm tra nguồn response và cách trình duyệt biểu diễn thuộc tính nonce.
3. Tải lại trang dưới dạng một request HTML mới; kiểm tra nonce đã đổi.
4. Trong môi trường demo có quyền kiểm soát, chèn thẻ `<script>alert('demo')</script>` không có nonce hợp lệ; trình duyệt phải chặn theo CSP thực thi phù hợp.
5. Xác nhận script/style inline tin cậy **có nonce khớp** vẫn hoạt động.
6. Thử `onclick="..."`, `onerror="..."` và thuộc tính `style="..."`. Nonce trong `script-src`/`style-src` không tự cấp quyền cho các thuộc tính này.
7. Kiểm tra trên các trình duyệt mục tiêu và xem mọi CSP header thực thi, đặc biệt nếu reverse proxy/CDN cũng gắn chính sách.

Đừng chỉ đánh giá bằng việc chạy mã từ **DevTools Console**: mã do người dùng chủ động nhập trong Console có thể chịu quy tắc khác với mã được trình duyệt phân tích từ HTML.

## 11. Chẩn đoán lỗi nonce và template

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh và xử lý |
|---|---|---|
| Script tin cậy vẫn bị chặn | Nonce trong HTML thiếu, sai, hoặc không khớp header | So sánh CSP header và HTML của cùng response |
| Tải lại trang nhưng nonce không đổi | Nonce là hằng, lưu session, hoặc HTML/header bị cache | Kiểm tra nơi sinh nonce và các tầng cache |
| Template hiển thị nguyên `${cspNonce}` | HTML không được Thymeleaf xử lý hoặc biểu thức sai ngữ cảnh | Xác minh template resolver, model và thuộc tính `th:attr` |
| Controller lấy nonce là `null` | Filter không chạy trên route hoặc chạy sai thứ tự | Kiểm tra chain mapping, đăng ký filter và điểm đặt thuộc tính |
| Có hai CSP header, script vẫn bị chặn | Proxy hoặc Spring Security thêm policy thực thi khác | Xem tất cả header; thống nhất nguồn chịu trách nhiệm CSP |
| Script hoạt động ở local, lỗi production | CDN cache HTML, build khác hoặc nonce không được truyền qua template | Đối chiếu response cuối cùng qua proxy/CDN |
| Nonce đúng trên script nhưng `onclick` không chạy | Nonce không cấp phép inline handler | Chuyển sang `addEventListener` trong JS tin cậy |
| Nonce đúng trên `<style>` nhưng `style="..."` bị chặn | Nonce không áp dụng cho style attribute | Chuyển style sang CSS class hoặc chính sách riêng có cân nhắc |
| JavaScript không lỗi CSP nhưng API thất bại | `connect-src` hoặc CORS của API không phù hợp | Phân biệt lỗi CSP kết nối và lỗi CORS |
| Trang login/error thiếu nonce | Route không đi qua cơ chế nonce của trang thông thường | Kiểm tra cách tạo response của framework và error dispatch |
| Nhiều lần tạo nonce trong một response | Header và view gọi hàm sinh riêng, hoặc hai filter cùng chạy | Tạo **một nonce**, đặt ở request/exchange và tái sử dụng khi render |

### Những điều không nên làm để “sửa nhanh”

- **Không thêm `'unsafe-inline'` vào `script-src`** chỉ để khối script thiếu nonce hoạt động; nó có thể cấp quyền cho nhiều payload XSS nội tuyến.
- **Không dùng nonce cố định** hoặc sinh nonce từ thông tin có thể đoán như timestamp, user ID hoặc session ID.
- **Không sinh nonce mới trong từng template fragment** nếu CSP header đang chứa nonce khác.
- **Không tự động gắn nonce cho HTML không đáng tin** hoặc mọi script do bên thứ ba cung cấp; việc gắn nonce chính là cấp quyền.
- **Không tắt CSRF/CORS/session security** để giải quyết lỗi CSP. Chúng bảo vệ các bề mặt khác trong Spring Security.
- **Không coi nonce là bằng chứng chống XSS tuyệt đối:** một script hợp lệ có lỗi DOM XSS hoặc một script độc hại đã được cấp nonce vẫn có thể thực thi.

## 12. Nonce, hash và file tĩnh: chọn phương án theo cách render trang

| Đặc điểm | Script/style ngoài cùng origin | CSP hash | CSP nonce |
|---|---|---|---|
| Phù hợp nhất | JS/CSS có thể tách thành file | Inline block ổn định, ít đổi | Inline block thay đổi theo response hoặc cần SSR |
| Điều kiện cho phép | Source list như `'self'` | Nội dung khớp hash trong CSP | Thẻ có nonce khớp header |
| Cần sinh giá trị mỗi response | Không | Không, nếu nội dung không đổi | **Có** |
| Tương tác với cache HTML | Thường đơn giản | Tốt nếu HTML/script ổn định | Cần kiểm soát header/body/cache chặt |
| Rủi ro triển khai | Cho phép nguồn quá rộng hoặc tệp không tin cậy | Hash lệch sau build/format | Tái dùng nonce, gắn sai thẻ, header và HTML không khớp |

Đối với trang chỉ dùng JavaScript/CSS ở file, cấu hình `script-src 'self'; style-src 'self'` có thể đơn giản hơn nhiều so với xây hệ thống nonce. Với inline block ổn định trong HTML được cache, CSP hash đôi khi phù hợp hơn. Nonce có giá trị khi trang **thật sự cần inline code đáng tin cậy** và server kiểm soát được việc sinh nonce đồng bộ cho mỗi response.

Có thể cân nhắc `'strict-dynamic'` kết hợp nonce/hash cho hệ thống nạp script động; đây là cơ chế CSP nâng cao, có ảnh hưởng đến cách host allowlist được áp dụng trong trình duyệt hỗ trợ. Không thêm mặc định nếu chưa xác định rõ chuỗi tải script và tương thích trình duyệt.

## 13. Bài thực hành

**Bối cảnh:** Một dashboard Spring Boot render Thymeleaf có một file JS cùng origin và một khối inline khởi tạo trạng thái giao diện. Yêu cầu là giữ khối inline hợp lệ hoạt động nhưng chặn một thẻ script bị chèn không có nonce.

1. Tạo lớp tiện ích `CspNonce` dùng `SecureRandom`, sinh chuỗi Base64 mới cho mỗi response và xây policy `script-src 'self' 'nonce-...'`.
2. Với Servlet, đăng ký `CspNonceFilter` trong đúng security chain, đặt nonce vào request attribute và CSP header trước khi controller render.
3. Đưa nonce từ request sang Thymeleaf model bằng tên `cspNonce`, gắn lên khối `<script>` tin cậy bằng `th:attr="nonce=${cspNonce}"`.
4. Thực hiện hai request HTML độc lập, kiểm tra nonce trong header khác nhau và khớp với HTML của từng response.
5. Thử một khối script khác không có nonce trong môi trường demo; xem CSP error trong browser. Thử thêm `onclick` để thấy nonce không cho phép inline handler.
6. Bật một lớp cache HTML thử nghiệm và phân tích điều gì xảy ra nếu cache trả lại nonce cũ hoặc thay header mà không thay body.
7. Triển khai phiên bản WebFlux dùng `WebFilter` và `ServerWebExchange`, rồi chứng minh template được truyền nonce mà không phụ thuộc `ThreadLocal`.
8. Kiểm tra trang login, trang lỗi và response HTML cuối cùng nếu hệ thống có reverse proxy/CDN; xác định đường đi của nonce và CSP header.

**Câu hỏi tự đánh giá:**

1. Vì sao không được giữ CSP nonce trong biến `static final` hoặc HTTP session?
2. Vì sao header và template phải dùng nonce đã tạo **một lần** cho cùng response?
3. Nonce có cấp quyền cho `onclick`, `style="..."` hay `eval(...)` không?
4. Dùng `ContentSecurityPolicyHeaderWriter` với `policyDirectives` cố định có tự tạo và truyền nonce đến template không?
5. Trong Servlet, request attribute và model liên hệ như thế nào? Trong WebFlux, `ServerWebExchange` thay vai trò nào?
6. Vì sao cache HTML có thể làm nonce bị tái sử dụng hoặc header không còn khớp body?
7. Khi frontend HTML do CDN phục vụ còn Spring Boot chỉ cung cấp API, CSP nonce phải được tạo ở đâu?
8. Khi nào chuyển inline script sang file tĩnh hoặc dùng hash có lợi hơn thiết kế nonce?

## 14. Ghi nhớ

**CSP nonce phải mới cho mỗi HTTP response HTML cần nó, khó đoán và được sử dụng nhất quán trong cả CSP header lẫn những thẻ `<script>`/`<style>` tin cậy của cùng response.** Đừng tạo nonce một lần cho ứng dụng hoặc phiên đăng nhập, đừng dùng giá trị cố định trong `policyDirectives(...)` và đừng sinh nonce độc lập tại từng template fragment.

Với Spring Security Servlet, có thể tạo nonce trong filter, lưu vào `HttpServletRequest` và truyền cho Thymeleaf model. Với Reactive/WebFlux, dùng `WebFilter` và `ServerWebExchange`. Cả hai cách phải kiểm soát điểm commit response, cache/proxy, security chain và đường phục vụ HTML. Nonce là một lớp giảm thiểu tác động của nội dung bị chèn; việc escape/sanitize, CSRF, CORS, security headers, HSTS, HTTP firewall và bảo vệ session vẫn cần được thiết kế theo chức năng riêng.
