# CSP làm hỏng chức năng hoặc nonce không khớp template

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Sự cố thường gặp: trang tải được nhưng chức năng đột ngột ngừng hoạt động

Ứng dụng Spring Boot trả một trang checkout qua HTTPS. Sau khi nhóm bảo mật triển khai Content Security Policy (CSP), HTML vẫn là HTTP 200, nhưng nút xác nhận đơn hàng không phản hồi. Trong DevTools Console xuất hiện thông báo tương tự:

~~~text
Refused to execute inline script because it violates the following
Content Security Policy directive: "script-src 'self' 'nonce-M2F...='".
~~~

Một phép kiểm tra khác cho thấy response header:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-abc123'; object-src 'none'; base-uri 'self'
~~~

Trong khi HTML render:

~~~html
<script nonce="xyz789">
  initializeCheckout();
</script>
~~~

Đây là **nonce mismatch**: nonce trong CSP response không khớp nonce ở thẻ script được phép chạy. Khi đó browser có thể chặn script **dù HTML hợp lệ, server 200 và người dùng đăng nhập thành công**.

Nhưng không phải mọi lỗi chức năng sau triển khai CSP đều do nonce. Một ứng dụng có thể hỏng vì:

- `connect-src` không cho API/WebSocket;
- `script-src` không cho thư viện tải từ CDN;
- `style-src` chặn inline style;
- `img-src` không cho ảnh ngoài domain;
- `frame-src` chặn iframe thanh toán;
- `form-action` ngăn submit đến identity provider;
- proxy chèn CSP thứ hai chặt hơn hoặc trả HTML cache kèm nonce cũ;
- mã frontend còn dùng `onclick=`, `eval` hoặc chuỗi script động mà CSP không cho phép.

**Mục tiêu của chẩn đoán:** xác định **chính directive** đang chặn **chính tài nguyên/hành vi** nào, và nếu dùng nonce thì phải chứng minh **nonce CSP header và HTML của cùng HTTP document response** khớp với nhau.

### Sau bài học, bạn có thể

1. Dùng browser Console, Network, `SecurityPolicyViolationEvent` và Report-Only để phân loại CSP violation.
2. Phân biệt CSP đang chặn với lỗi CORS, CSRF, HSTS, authentication, firewall, network hoặc JavaScript runtime.
3. Thiết kế nonce ngẫu nhiên đủ mạnh, mới cho từng **document response**, dùng đúng một giá trị từ header tới template.
4. Tích hợp CSP nonce trong Spring Security Servlet/MVC/Thymeleaf và Reactive/WebFlux, không phát nhiều CSP policies xung đột.
5. Điều tra CDN, gateway, ESI/fragment cache, SSR hydration, proxy/security header rewrite và HTTP caching.
6. Viết phép thử tích cực và tiêu cực bằng MockMvc, WebTestClient, Playwright và runbook xử lý sự cố.

## 2. CSP là chính sách được browser thực thi, không phải kết quả HTTP

CSP thường được gửi trong response header của **HTML document**:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'
~~~

Chính sách này có thể cho trang tải JavaScript từ cùng origin, nhưng chặn phần lớn script inline vì `script-src 'self'` **không tự cho phép inline scripts**.

~~~html
<!-- Có thể được phép theo script-src 'self' -->
<script src="/assets/app.js"></script>

<!-- Bị chặn nếu không có nonce/hash/ngoại lệ phù hợp -->
<script>startApp();</script>
~~~

Browser áp CSP lên các hành động thuộc phạm vi policy, ngay cả khi server trả mã 200, response body đầy đủ và cookie/session hợp lệ. Nó không sửa DOM, không gửi CSRF token hộ frontend và không quyết định người dùng có quyền gọi API.

~~~mermaid
flowchart TD
    A[Spring hoặc gateway trả HTML và CSP] --> B[Browser parse CSP]
    B --> C{Tải script, style, connect, frame, form...?}
    C --> D{Directive hiệu lực cho hành động?}
    D -- Cho phép --> E[Browser tiếp tục]
    D -- Chặn --> F[Console/CSP violation và chức năng có thể lỗi]
    F --> G[Xác định directive, blockedURI, policy và response owner]
    G --> H[Sửa policy hoặc thiết kế frontend, không tắt bảo vệ]
~~~

### Không đồng nhất “request bị chặn” với “server đã xử lý”

- Khi CSP `connect-src` chặn một `fetch` trước network, **request có thể chưa từng tới Spring**.
- Khi CORS chặn quyền đọc response, actual request có thể **đã tới server và đã thay đổi dữ liệu**.
- Khi CSRF trả 403, Spring Security có thể đã nhận request nhưng không cho phép xử lý thao tác.

Ba loại lỗi này có hậu quả và cách sửa khác nhau. Không thử lại POST thanh toán một cách vô điều kiện chỉ vì `fetch` ném lỗi.

## 3. CSP Enforcement và Report-Only: cùng cú pháp, khác tác động

Chế độ chặn thực tế:

~~~http
Content-Security-Policy: script-src 'self' 'nonce-r4nd0m...'; object-src 'none'
~~~

Chế độ quan sát:

~~~http
Content-Security-Policy-Report-Only: script-src 'self' 'nonce-r4nd0m...'; object-src 'none'
~~~

| Quan sát | Enforce CSP | CSP Report-Only |
|---|---|---|
| Vi phạm policy | Browser có thể **chặn** hành động | Browser **không chặn vì riêng policy report-only** |
| Console | Thông báo refusal/blocked | Thường có ngữ nghĩa “would be blocked” |
| `SecurityPolicyViolationEvent.disposition` | `enforce` | `report` |
| Report endpoint | Có thể cấu hình | Có thể cấu hình |
| Tác động tới chức năng | Có thể hỏng nếu policy chưa tương thích | Không gây chặn bởi chính report-only policy |

**Một response có thể chứa đồng thời enforce và report-only.** Nếu script bị chặn, đừng đổ lỗi cho Report-Only khi một enforce policy khác đang áp dụng. Muốn biết policy nào gây chặn, cần đọc **toàn bộ các header CSP được browser nhận**.

### Quy trình rollout an toàn

1. Tạo candidate policy với phạm vi tài nguyên rõ ràng.
2. Chạy Report-Only trên browser routes và kiểm tra violation reports thực tế.
3. Sửa frontend có thể sửa; chỉ mở allowlist cho nguồn được tin cậy.
4. Test critical workflows: login, logout, upload, checkout, form, embedded content, API, WebSocket.
5. Chuyển sang enforce theo canary/route; giữ positive và negative security tests.
6. Quan sát sau triển khai; không mặc định mọi report là lý do mở CSP.

## 4. Đọc một CSP violation: bị chặn cái gì, theo directive nào?

Browser Console có thể thông báo:

~~~text
Refused to connect to 'wss://events.example.net/socket'
because it violates "connect-src 'self' https://api.example.com".
~~~

Đừng tìm `script-src` trong trường hợp này. Hành vi bị chặn là WebSocket và directive liên quan là `connect-src`.

| Dữ liệu | Vai trò |
|---|---|
| `effectiveDirective` | Directive browser thực thi cho vi phạm, chẳng hạn `script-src-elem` hoặc `connect-src` |
| `violatedDirective` | Directive được báo theo định dạng/browser |
| `blockedURI` | Nguồn bị chặn; có thể được browser lược bớt để bảo vệ riêng tư |
| `sourceFile`/`lineNumber` | Vị trí liên quan, không luôn trỏ tới nguyên nhân gốc |
| `originalPolicy` | Chính sách đã dẫn đến violation |
| `disposition` | `enforce` hoặc `report` |
| Console message | Gợi ý nhanh nhưng wording khác nhau theo browser |

**Không chỉ đọc phần “Refused to…” rồi nới `default-src *`.** Phải xác định directive hiệu lực và lý do fallback: ví dụ `script-src-elem` có thể fallback về `script-src`; `connect-src` có thể fallback về `default-src` khi không khai báo.

### Chẩn đoán trực tiếp từ Network

Trong DevTools:

1. Chọn **response HTML document** để xem headers CSP, không nhầm CSP của API/JS response.
2. Xem response có **một hay nhiều CSP headers** do Spring/proxy/CDN phát.
3. Xem script/style/API resource có network request không. Một request không xuất hiện có thể bị CSP chặn trước network.
4. Xem URL/Origin/Content-Type/redirect chain thực và lỗi Console tương ứng.
5. Nếu browser vẫn báo lỗi sau khi sửa, kiểm tra HTML/CDN cache và service worker.

## 5. Chọn đúng directive theo hành vi bị hỏng

| Chức năng | Directive thường liên quan | Dấu hiệu / hướng kiểm tra |
|---|---|---|
| JavaScript inline trên HTML | `script-src`/`script-src-elem` | Nonce/hash, inline script, CSP violation |
| `onclick="..."` hoặc script attribute | `script-src-attr` (fallback) | Nonce trên thẻ script **không mở** inline handler |
| Script từ CDN | `script-src-elem`/`script-src` | Exact script origin, integrity, redirect |
| `eval()`, `new Function()` | `script-src` | Tránh eval thay vì bật `'unsafe-eval'` |
| Inline `<style>` | `style-src-elem`/`style-src` | Nonce của style tag nếu policy cho phép |
| `style="..."` | `style-src-attr` | Nonce style tag không áp cho style attributes |
| CSS từ CDN | `style-src-elem`/`style-src` | Style sheet origin/CORS nếu liên quan |
| `fetch`, XHR, EventSource | `connect-src` | HTTPS API origin, CORS vẫn kiểm tra riêng |
| WebSocket | `connect-src` | `wss:` endpoint và browser support |
| Ảnh, data URL | `img-src` | Host hoặc `data:` có thật sự cần không |
| Font | `font-src` | Host font và CORS yêu cầu theo browser |
| Payment/SSO iframe | `frame-src` | Parent page có cho nhúng iframe không |
| Trang bị nhúng vào iframe | `frame-ancestors` | Policy trên **response của trang con** |
| Submit form tới IdP | `form-action` | Destination form thực, redirects |
| Document base URL | `base-uri` | `<base>` được phép hay không |
| Worker/script worker | `worker-src` (fallback tương ứng) | Worker URL, blob worker |

**Không có một directive duy nhất sửa mọi chức năng.** Nếu `script-src` đã đúng nhưng WebSocket bị chặn, chỉnh `connect-src`. Nếu CSP của trang cha đã cho `frame-src` nhưng trang con có `frame-ancestors 'none'`, parent vẫn không được nhúng.

## 6. Một nonce CSP có tác dụng ở đâu?

Ví dụ CSP:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-kTnS7VbYz80yA3m93E1Jqw=='; object-src 'none'
~~~

HTML:

~~~html
<script nonce="kTnS7VbYz80yA3m93E1Jqw==">
  window.appStarted = true;
</script>
~~~

Khi nonce thỏa policy và script element có nonce tương ứng, browser có thể cho inline script đó chạy. Nonce là **giá trị được browser so khớp giữa policy của document và script/style element**; đó không phải token xác thực và **không liên quan CSRF token**.

### Những điều nonce KHÔNG làm

- Không làm mọi inline event handler như `onclick=` hoặc `javascript:` URL tự được phép.
- Không cho mọi inline `style=` chạy nếu thiếu `style-src-attr` policy phù hợp.
- Không làm `fetch` tới mọi domain vượt qua `connect-src`.
- Không thay thế server authorization, CSRF, cookie protections, CORS hay input sanitization.
- Không giúp script vượt qua một **CSP enforce policy khác** đang cấm nó.
- Không nên được dùng như bí mật đăng nhập hoặc mã chống CSRF.

### Nonce có thể được dùng cho style element nhưng phải có style policy

~~~http
Content-Security-Policy: script-src 'self' 'nonce-N'; style-src 'self' 'nonce-N'
~~~

~~~html
<script nonce="N">startApp();</script>
<style nonce="N">.dialog{display:block}</style>
~~~

Đây là ví dụ cú pháp khái niệm; production cần dùng nonce ngẫu nhiên khó đoán. Nếu chỉ khai báo nonce trong `script-src`, việc đặt cùng nonce trên `<style>` **không tự cho phép inline CSS**.

## 7. Tại sao nonce phải mới và khó đoán trên từng HTML response?

Nonce CSP cần có entropy cao, được tạo bằng bộ sinh số ngẫu nhiên an toàn, không thể bị attacker đoán trước khi cố chèn script. Một phương án thường dùng là **ít nhất 128 bit ngẫu nhiên** cho mỗi document response và mã hóa Base64.

~~~java
import java.security.SecureRandom;
import java.util.Base64;

final class CspNonceFactory {
    private static final SecureRandom RANDOM = new SecureRandom();

    static String newNonce() {
        byte[] bytes = new byte[16]; // 128 bit
        RANDOM.nextBytes(bytes);
        return Base64.getEncoder().encodeToString(bytes);
    }
}
~~~

**Sai:**

~~~java
// Không dùng một giá trị cố định cho mọi response.
private static final String CSP_NONCE = "fixed-nonce";

// Không dùng session ID/CSRF token làm nonce.
String cspNonce = session.getId();

// Không dùng Math.random() / UUID ngẫu nhiên kiểu không có
// bảo đảm entropy cần thiết như một shortcut thiết kế CSP nonce.
~~~

Nonce phải được tạo mới theo **response mang document** chứ không chỉ một lần khi ứng dụng khởi động hoặc mỗi phiên login. Không dùng nonce lâu dài trong HTML cache công khai.

### Tại sao “nonce bí mật” không có nghĩa phải giấu khỏi chính trang?

Nonce hợp lệ cần hiện diện trong HTML để browser kiểm tra. Mục tiêu là **không cho attacker chủ động dự đoán/chèn đúng nonce trước khi phản hồi được tạo**, và ngăn mã độc được gắn nonce thông qua những chỗ user-controlled. Nó không phải khóa bí mật duy trì qua nhiều request. Tránh log nonce/header và tránh xuất nonce vào API hoặc URL không cần thiết, nhưng không xem nonce như password.

### CSP nonce không bù cho XSS rendering bug

Nếu ứng dụng cho dữ liệu không tin cậy kiểm soát HTML attributes, chèn script tag hợp lệ, hoặc thao túng DOM đang chứa nonce của script đã được phép, CSP có thể không ngăn toàn bộ XSS. Vẫn phải escape template, sanitize những HTML cho phép, tránh DOM injection và review script loaders/trusted code.

## 8. Bốn nguyên nhân nonce mismatch dễ gặp

~~~mermaid
flowchart TD
    A[Header nonce không khớp script nonce] --> B{Nguồn tạo nonce?}
    B --> C[Header writer sinh A, template sinh B]
    B --> D[Render HTML trước/khác request context]
    B --> E[CDN/SSR fragment cache HTML nonce cũ]
    B --> F[Proxy thêm CSP thứ hai hoặc sửa header]
    C --> G[Chọn một source nonce per document response]
    D --> G
    E --> H[Không cache HTML nonce sai; phối hợp fragments]
    F --> I[Chọn một CSP owner; kiểm tra tất cả policies]
~~~

### 8.1. Header và template gọi generator độc lập

~~~java
// Phản ví dụ: sinh hai giá trị khác nhau.
String headerNonce = CspNonceFactory.newNonce();
String templateNonce = CspNonceFactory.newNonce();
~~~

Nếu CSP chứa A và HTML có B, script B bị chặn. Cách đúng là tạo A **một lần cho response**, đưa A vào request/exchange attributes, rồi dùng A cho **cả CSP header và template**.

### 8.2. Đặt nonce trong session

Một session nonce dùng lại qua nhiều trang không đáp ứng mục tiêu freshness per-response. Session cookie và CSP nonce có vòng đời và mục tiêu khác nhau.

### 8.3. HTML và header bị cache độc lập

CDN có thể cache HTML với nonce A trong khi Spring/edge tạo CSP header mới nonce B. Hoặc ESI/SSR fragment chứa script nonce cũ được ghép vào HTML document mới. Những trường hợp này **không được sửa bằng cách cho nonce cố định**.

### 8.4. Nhiều enforced policies

Spring trả policy nonce A; gateway thêm policy nonce B. Browser áp dụng **từng enforce policy**, nên script có nonce A vẫn có thể bị chặn theo policy B. Không chỉ so nonce với policy đầu tiên.

## 9. CSP trên response nào mới điều khiển một trang?

Trong trường hợp thông thường, CSP header trên **HTML document response** ràng buộc tài nguyên mà document đó tải/thực thi. Header CSP trên riêng file `/assets/app.js` không thay thế policy của HTML document tải nó.

| Response | Mục đích quan sát |
|---|---|
| `GET /dashboard` trả HTML | **CSP thực sự áp lên document** |
| `GET /assets/app.js` trả JavaScript | MIME type, `nosniff`, cache, CORS/cross-origin resource behavior |
| `GET /api/data` trả JSON | HTTP status, CORS nếu cross-origin, cache/CSRF/auth |
| `GET /payment/iframe` trả HTML | CSP của iframe document, bao gồm `frame-ancestors` của chính trang iframe |
| `GET /error` trả HTML | CSP có thể khác nếu response được tạo bởi error handler/proxy |

Nếu một scanner chỉ báo “missing CSP” trên file JS nhưng HTML đã có policy đúng, đó có thể là một yêu cầu kiểm tra thiếu ngữ cảnh. Ngược lại, nếu HTML response có CSP nonce nhưng template không render cùng giá trị, sự cố là thực.

### Tách header và meta CSP

Một HTML có thể chứa:

~~~html
<meta http-equiv="Content-Security-Policy"
      content="default-src 'self'; script-src 'self'">
~~~

Nhưng meta CSP có giới hạn so với HTTP response header, chẳng hạn không hỗ trợ một số directive dùng cho framing/reporting. Nếu server còn gửi CSP header, cả hai có thể dẫn đến các giới hạn áp dụng đồng thời. **Ưu tiên quản lý CSP bằng HTTP headers**, kiểm tra meta tag còn sót nếu mới chuyển CSP từ frontend sang backend.

## 10. Servlet: một nonce per response, lưu trong request attribute

Đối với Spring Security Servlet, có thể tạo một filter chuyên trách:

1. Sinh nonce bằng `SecureRandom` một lần cho document response.
2. Lưu nonce trong `HttpServletRequest` attribute.
3. Tạo **một** header CSP dùng chính nonce đó.
4. Controller lấy request attribute, truyền tới template.
5. Template chỉ **dùng lại** nonce đã nhận, không tự sinh nonce khác.

### Một filter minh họa có phạm vi rõ

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.security.SecureRandom;
import java.util.Base64;
import org.springframework.web.filter.OncePerRequestFilter;

public final class CspNonceServletFilter extends OncePerRequestFilter {

    public static final String NONCE_ATTRIBUTE = "cspNonce";
    private static final SecureRandom RANDOM = new SecureRandom();

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        // Chỉ minh họa một HTML document route của lab.
        return !"/csp-lab".equals(request.getServletPath());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        byte[] bytes = new byte[16];
        RANDOM.nextBytes(bytes);
        String nonce = Base64.getEncoder().encodeToString(bytes);

        request.setAttribute(NONCE_ATTRIBUTE, nonce);
        response.setHeader(
            "Content-Security-Policy",
            "default-src 'self'; " +
            "script-src 'self' 'nonce-" + nonce + "'; " +
            "script-src-attr 'none'; " +
            "style-src 'self'; " +
            "connect-src 'self'; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "frame-ancestors 'none'"
        );

        // Với document HTML có nonce biến thiên: không cache chia sẻ.
        response.setHeader("Cache-Control", "no-store");
        chain.doFilter(request, response);
    }
}
~~~

**Đây là fixture giảng dạy**, không phải một thư viện CSP chung cho mọi routes. Cấu hình phải được review theo frontend và cách render thực tế:

- `/csp-lab` chỉ là HTML route trong lab. Production cần bao phủ mọi dynamic HTML document có script inline cần nonce.
- `getServletPath()` có thể khác public path khi dùng servlet context, forwarded prefix hoặc reverse proxy. Hãy test **path servlet nhận**, không chỉ browser URL.
- Đừng tự động phát nonce CSP trên file JS, JSON hoặc response được CDN cache lâu.
- Đây là nơi sở hữu **duy nhất** CSP header cho route; **không** đồng thời thêm một CSP nonce riêng qua `ContentSecurityPolicyHeaderWriter` hoặc gateway trên cùng response.
- Nếu một filter/handler phía sau ghi đè CSP, nó có thể làm mất nonce vừa tạo. Test header cuối cùng, không chỉ log filter đã chạy.

### Vì sao không viết nonce vào static field?

Vì static field tồn tại qua nhiều requests. Chỉ `SecureRandom` có thể là static shared generator; **giá trị nonce trả về phải được tạo mới** mỗi document response.

## 11. Servlet: đăng ký filter trong đúng SecurityFilterChain

Nếu chỉ có một Servlet chain cho lab:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.HeaderWriterFilter;

@Configuration
public class CspLabSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/csp-lab", "/assets/**").permitAll()
            .anyRequest().authenticated()
        );
        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());

        http.addFilterBefore(
            new CspNonceServletFilter(),
            HeaderWriterFilter.class
        );

        // HSTS, nosniff, framing và những headers mặc định khác vẫn bật.
        // Không cấu hình một CSP writer thứ hai cho /csp-lab.
        return http.build();
    }
}
~~~

**Tại sao chọn đăng ký như vậy?** Filter thuộc security chain, tạo nonce trước khi các bộ lọc sau và handler/template cần giá trị. `HeaderWriterFilter` có vị trí filter riêng cho các default security headers; CSP được filter minh họa tự ghi đúng một lần trên route lab. Không có yêu cầu phải tắt default security headers chỉ vì ứng dụng tự phát CSP.

### Tránh double registration của Servlet filter

Nếu vừa khai báo `@Bean CspNonceServletFilter` để servlet container tự đăng ký, vừa `http.addFilterBefore(filter, ...)` trên Spring Security chain, filter có thể được gọi theo hai đường khác nhau. Với ví dụ này, filter **được tạo bằng `new` và đăng ký duy nhất trong security chain**. Nếu kiến trúc cần bean/injection, phải kiểm soát việc servlet container đăng ký hoặc disable auto-registration theo Spring Boot version.

### Một chú ý về multiple chains

Nếu có API chain `@Order(1)` chỉ match `/api/**` và web chain `@Order(2)` match HTML, filter phải được gắn vào **web chain thật sự xử lý `/csp-lab`**. `permitAll()` bên trong một chain không match route không giúp nonce đến template.

### Không dùng web.ignoring cho document route cần CSP

Nếu `/csp-lab` bị `web.ignoring()`, filter gắn trong Spring Security sẽ không chạy và template có thể nhận null nonce. Ưu tiên `permitAll()` cho public document có security headers, không bypass chain chỉ để tải được HTML.

## 12. Servlet MVC: truyền đúng request nonce vào Thymeleaf

Controller lab đọc giá trị được đặt trước đó:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class CspLabController {

    @GetMapping("/csp-lab")
    public String page(HttpServletRequest request, Model model) {
        Object nonce = request.getAttribute(
            CspNonceServletFilter.NONCE_ATTRIBUTE
        );

        if (!(nonce instanceof String)) {
            throw new IllegalStateException(
                "CSP nonce filter did not run for this document"
            );
        }

        model.addAttribute("cspNonce", nonce);
        return "csp-lab";
    }
}
~~~

Chủ đích **fail closed** ở lab nếu nonce không có: không render một script inline thiếu nonce nhưng lại giả rằng trang được bảo vệ đúng. Với production, hãy thiết kế error handling hợp lý, tránh lộ stacktrace/nonce trong response lỗi.

### Thymeleaf template: dùng giá trị đã cấp

Trong template `csp-lab.html` (chỉ là ví dụ nội dung; bài này không tạo file đó):

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>CSP lab</title>
  <link rel="stylesheet" href="/assets/site.css">
</head>
<body>
  <button id="confirm" type="button">Xác nhận</button>

  <script th:attr="nonce=${cspNonce}" data-lab="allowed">
    window.__allowedInlineExecuted = true;
    document.getElementById("confirm").addEventListener(
      "click", () => console.log("Đã nhận thao tác")
    );
  </script>

  <!-- Không có nonce: dùng làm đối chứng bị chặn trong lab -->
  <script data-lab="blocked">
    window.__blockedInlineExecuted = true;
  </script>
</body>
</html>
~~~

Khi Thymeleaf render, kết quả mong đợi:

~~~html
<script nonce="nA1b2C3..."> ... </script>
~~~

Nonce phải **bằng đúng nonce trong CSP header của response HTML đó**. `th:attr` đưa giá trị Model vào attribute, không tự sinh nonce mới.

### Những sai lầm template thường gặp

~~~html
<!-- Sai: literal chuỗi, không phải giá trị Model -->
<script nonce="cspNonce">startApp();</script>

<!-- Sai: cố định nonce qua mọi response -->
<script nonce="fixed-nonce">startApp();</script>

<!-- Sai: đặt nonce lên phần tử không phải script/style rồi mong script chạy -->
<div nonce="abc">Nội dung</div>
<script>startApp();</script>

<!-- Sai: event handler inline không được nonce script tag cho phép -->
<button onclick="startApp()">Xác nhận</button>
~~~

Với `onclick`, hãy dùng `addEventListener` trong script được phép chạy hoặc file JS hợp lệ. Nếu template fragment hiển thị từ cache, nó phải được render với nonce document hiện tại, không thể mang nonce cũ.

## 13. Header CSP writer tĩnh không tự giải bài toán nonce động

Spring Security Servlet hỗ trợ khai báo CSP tĩnh:

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; script-src 'self'; object-src 'none'"
        )
    )
);
~~~

Code trên có ích cho các policy **không cần nonce biến thiên**. Nhưng viết:

~~~java
String nonce = CspNonceFactory.newNonce();
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("script-src 'self' 'nonce-" + nonce + "'")
    )
);
~~~

trong thời điểm build `SecurityFilterChain` có thể tạo nonce **chỉ một lần khi khởi tạo cấu hình**, và template sẽ không có cùng nonce per response. Đây là **phản ví dụ**, không phải cách cấu hình dynamic CSP.

### Chọn một cơ chế CSP owner

Có thể dùng request-aware custom `HeaderWriter` hoặc filter an toàn như mục 10; điều quan trọng là **giá trị nonce phải được tạo theo response và dùng lại ở template**, không tách generator giữa header writer và controller.

Nếu ứng dụng đã có CSP tại Nginx/CDN, hoặc thêm một CSP policy khác bằng `headers().contentSecurityPolicy(...)`, hãy chọn một owner/hợp đồng rõ. **Hai policy enforce không kết hợp thành một danh sách lựa chọn**, mà browser cần thỏa từng policy.

## 14. Nonce cho inline style, style attribute và CSS-in-JS

Giả sử một UI library tạo:

~~~html
<style>.modal{opacity:1}</style>
~~~

CSP:

~~~http
Content-Security-Policy: style-src 'self'
~~~

không cho inline style tag đó. Có thể đưa CSS ra một file `/assets/style.css` hoặc nếu có lý do rõ ràng, dùng nonce cho style tag:

~~~http
Content-Security-Policy: style-src 'self' 'nonce-S4...'
~~~

~~~html
<style nonce="S4...">.modal{opacity:1}</style>
~~~

**Nonce được so theo đúng directive:** một nonce trong `script-src` không tự mở `style-src`; nếu cần nonce cho cả hai, CSP phải khai báo cho cả hai loại.

### Style attribute khác style tag

~~~html
<div style="display:none">Nội dung</div>
~~~

Nonce trên `<style>` hoặc `<script>` không tự cho phép attribute `style=`. Nên chuyển style động sang class được CSS file quản lý hoặc xem chính sách `style-src-attr` có kiểm soát. **Không bật `'unsafe-inline'` toàn cục chỉ vì một thư viện cũ đang dùng style attributes**.

### CSS-in-JS cần hợp đồng nonce riêng

Một số framework CSS-in-JS chèn `<style>` vào document ở runtime. Nó có thể cần biết **nonce hiện tại** để gắn vào các style tags được tạo. Nếu thư viện lấy nonce từ giá trị build-time, session hoặc một fragment cache, CSP mismatch sẽ xuất hiện từng lúc.

Kiểm tra cách thư viện nhận nonce trong **cùng document response**, thay vì xuất một nonce cố định trong cấu hình bundler. Nếu không muốn chèn nonce vào dynamic style tags, cân nhắc CSS file/class strategy theo kiến trúc frontend.

## 15. Nonce không sửa được inline event handlers và eval

Một trang:

~~~html
<button onclick="submitOrder()">Thanh toán</button>
<script nonce="VALID_NONCE">
  function submitOrder() { /* ... */ }
</script>
~~~

vẫn có thể không chạy `onclick` dưới CSP chặt. Thay bằng:

~~~html
<button id="pay" type="button">Thanh toán</button>
<script nonce="VALID_NONCE">
  document.getElementById("pay").addEventListener(
    "click", submitOrder
  );
  function submitOrder() { /* ... */ }
</script>
~~~

### Tránh giải pháp `'unsafe-inline'` và `'unsafe-eval'`

- `'unsafe-inline'` nới giới hạn thực thi mã inline, làm giảm một lợi ích quan trọng của CSP.
- `'unsafe-eval'` cho phép một số dạng evaluation động mà nhiều ứng dụng không cần trong production.
- Một số chế độ build/dev tool dùng eval hoặc hot reload; **tách policy development và production** khi cần, không mặc định đưa cờ nguy hiểm sang production.
- Nonce không mở quyền `eval`; nếu dependency cần `new Function()`, tìm build/dependency alternative trước.

### Hash cho inline script cố định là lựa chọn khác

Với script inline nhỏ, bất biến, CSP hash như `'sha256-...'` có thể phù hợp. Hash được tính trên **chính xác nội dung inline script**, thay đổi ký tự/whitespace là đổi hash. Nếu script chứa dữ liệu động hoặc interpolation của template, nonce per response thường dễ quản lý hơn hash cố định.

## 16. Vì sao script-src đã cho nonce nhưng external script vẫn lỗi?

Ví dụ:

~~~http
Content-Security-Policy: script-src 'self' 'nonce-N'
~~~

~~~html
<script src="https://cdn.example.net/widget.js"></script>
~~~

Script từ CDN này có thể bị chặn vì:

- URL không thuộc `'self'` và element không có nonce/hash phù hợp.
- Một policy enforce khác đã chặn nguồn CDN.
- Script được loader tạo động, và cấu hình `strict-dynamic`/trust propagation khác dự kiến.
- CSP cho phép nhưng SRI, CORS, MIME `nosniff`, TLS hoặc network chặn.

**Không cho phép `https:` hoặc `*` toàn bộ script sources chỉ để một widget chạy.** Nếu cần CDN, review nguồn cụ thể, supply-chain risks, versioning/SRI và policy.

### Về `'strict-dynamic'`

Trong CSP được thiết kế kỹ, `'strict-dynamic'` có thể cho các script đáng tin cậy được nonce/hash ủy quyền tải thêm script, với hành vi và fallback tùy trình duyệt hỗ trợ. Đây **không phải** cách giải mọi nonce mismatch; nếu chính bootstrap script bị chặn vì nonce không khớp, loader phía sau cũng không hoạt động.

Chỉ dùng sau khi đã mô hình hóa cách bundler/runtime nạp script, browser compatibility và security review.

## 17. Reactive/WebFlux: nonce thuộc ServerWebExchange, không phải HttpServletRequest

Trên WebFlux, không dùng `OncePerRequestFilter` Servlet và `HttpServletRequest`. Ứng dụng xử lý request qua `ServerWebExchange` và các `WebFilter`. Ý tưởng **một nonce cho một document response** vẫn như Servlet nhưng nơi truyền dữ liệu khác:

~~~text
HTTPS HTML request
  -> WebFilter tạo nonce
  -> Lưu exchange attribute + gắn CSP response header
  -> Reactive security / WebFlux handler
  -> Controller đưa attribute vào Model
  -> Thymeleaf render script nonce đúng giá trị
  -> Browser so CSP với HTML của cùng response
~~~

### WebFilter tạo nonce cho đúng HTML route

~~~java
import java.security.SecureRandom;
import java.util.Base64;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

public final class CspNonceReactiveFilter implements WebFilter {

    public static final String NONCE_ATTRIBUTE = "cspNonce";
    private static final SecureRandom RANDOM = new SecureRandom();

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String path = exchange.getRequest()
            .getPath()
            .pathWithinApplication()
            .value();

        if (!"/csp-lab".equals(path)) {
            return chain.filter(exchange);
        }

        byte[] bytes = new byte[16];
        RANDOM.nextBytes(bytes);
        String nonce = Base64.getEncoder().encodeToString(bytes);

        exchange.getAttributes().put(NONCE_ATTRIBUTE, nonce);
        exchange.getResponse().getHeaders().set(
            "Content-Security-Policy",
            "default-src 'self'; " +
            "script-src 'self' 'nonce-" + nonce + "'; " +
            "script-src-attr 'none'; " +
            "style-src 'self'; " +
            "connect-src 'self'; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "frame-ancestors 'none'"
        );
        exchange.getResponse().getHeaders()
            .set("Cache-Control", "no-store");
        return chain.filter(exchange);
    }
}
~~~

Mã này chỉ minh họa cách ghi header **trước khi response được commit**. Trong reactive pipeline, không được cập nhật response headers sau khi headers đã được gửi; nếu một downstream filter/proxy ghi đè CSP, phải có test trên response cuối.

### Đăng ký WebFilter trước security WebFilters

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.server.WebFilter;

@Configuration
public class ReactiveCspNonceRegistration {

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE + 10)
    WebFilter cspNonceWebFilter() {
        return new CspNonceReactiveFilter();
    }
}
~~~

Thứ tự này chỉ thể hiện ý đồ xử lý nonce sớm; ứng dụng có các custom WebFilters khác cần xác minh effective ordering. **Đừng gắn cùng filter hai lần** qua cả global WebFilter và một cơ chế khác nếu không có kế hoạch.

### WebFlux security chain vẫn giữ các lớp bảo vệ khác

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveCspLabSecurity {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        http.authorizeExchange(auth -> auth
            .pathMatchers("/csp-lab", "/assets/**").permitAll()
            .anyExchange().authenticated()
        );
        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());

        // Giữ các security headers mặc định; CSP lab do WebFilter sở hữu.
        return http.build();
    }
}
~~~

Không thêm một `http.headers(...contentSecurityPolicy(...))` tĩnh có thể xung đột với nonce policy của WebFilter trên `/csp-lab`. Trong hệ thống nhiều `SecurityWebFilterChain`, xác định chính xác route nào đang match; global WebFilter có thể chạy trên các routes ngoài chain, cần policy/ownership rõ.

## 18. Reactive controller và Thymeleaf dùng exchange attribute

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.server.ServerWebExchange;

@Controller
public class ReactiveCspLabController {

    @GetMapping("/csp-lab")
    public String page(ServerWebExchange exchange, Model model) {
        String nonce = exchange.getAttribute(
            CspNonceReactiveFilter.NONCE_ATTRIBUTE
        );

        if (nonce == null) {
            throw new IllegalStateException(
                "Missing CSP nonce for reactive document"
            );
        }

        model.addAttribute("cspNonce", nonce);
        return "csp-lab";
    }
}
~~~

Template Thymeleaf dùng chung cấu trúc:

~~~html
<script th:attr="nonce=${cspNonce}">
  window.__allowedInlineExecuted = true;
</script>
~~~

Thymeleaf dùng Model value của **request hiện tại**, không lấy một nonce khác qua static field hay một global reactive variable.

### Reactive context không có nghĩa là thread-local request

Với xử lý không đồng bộ, không nên dùng một biến static, mutable singleton hoặc `ThreadLocal` để lưu nonce request rồi kỳ vọng nó luôn đi cùng một flow. Dùng `ServerWebExchange` attributes hoặc cơ chế truyền context có vòng đời request rõ ràng.

### Reactive rendering và caching

Nếu trang hoặc HTML fragments được cache ở template/CDN/edge, vẫn có nguy cơ nonce trong HTML lệch CSP response. Không giải quyết bằng cách reuse nonce lâu dài trong Reactor context. Hãy để nonce thuộc document response và phối hợp caching đúng.

## 19. Một flow debug đúng cho nonce header và template

Giả sử browser nhận:

~~~http
Content-Security-Policy: script-src 'self' 'nonce-HEADER_A'
~~~

HTML:

~~~html
<script nonce="TEMPLATE_B">startApp();</script>
~~~

Chẩn đoán theo chuỗi:

1. Ghi **response ID** của document và mã policy, không log giá trị nonce production vào hệ thống dùng chung.
2. Trong test có kiểm soát, lấy CSP header và body của **cùng HTTP response**.
3. So nonce trong `script-src` với `nonce` của từng inline script/style tag hợp lệ.
4. Tìm nơi tạo nonce: filter, HeaderWriter, controller, template helper, SSR renderer hoặc frontend bootstrapping.
5. Xác minh header có bị proxy override, append hoặc CDN cache riêng không.
6. Sau khi sửa, đảm bảo hai document responses liên tiếp **không dùng cùng nonce**.
7. Có negative test: inline script không nonce vẫn bị chặn.

### Không tự dùng hai HTTP requests để so nonce

Sai:

~~~text
GET /csp-lab lần 1 -> lấy CSP header nonce A
GET /csp-lab lần 2 -> lấy HTML nonce B
So A với B rồi kết luận mismatch
~~~

Nonce **phải khác giữa các responses**, nên phép so trên hai requests khác nhau cho false positive. Luôn đọc header và body của **một response duy nhất**, rồi dùng request khác chỉ để kiểm tra freshness.

## 20. Nhiều CSP enforced headers: vì sao nonce đúng vẫn bị chặn?

Spring phát:

~~~http
Content-Security-Policy: script-src 'self' 'nonce-ABC'; object-src 'none'
~~~

Proxy thêm:

~~~http
Content-Security-Policy: script-src 'self'; object-src 'none'
~~~

Một inline script có `nonce="ABC"` được policy đầu cho phép nhưng policy thứ hai **không cho phép inline scripts**. Browser thực thi các policies riêng biệt, nên kết quả cuối cùng vẫn chặn.

### Sửa ở đúng tầng

- Xác định ai sở hữu CSP: Spring, ingress, CDN hoặc BFF.
- Với nonce động do Spring render, **proxy không thể phát static nonce CSP khác** rồi mong browser tự “gộp để cho phép”.
- Nếu edge muốn thêm security policies, phải thống nhất hợp đồng sao cho không chặn legitimate scripts hoặc bỏ qua dynamic nonce của document.
- Kiểm tra raw headers, gồm các giá trị bị gộp thành một dòng trong một số công cụ.
- Phân biệt hai enforce policies với một enforce và một Report-Only.

**Không bỏ CSP header ở Spring rồi thêm `'unsafe-inline'` ở proxy như đường tắt.** Cần sửa policy ownership và kiểm thử đồng thời chức năng lẫn protection.

## 21. Caching: nonce động và HTML cache lâu là cặp dễ xung đột

Một CSP nonce được sinh mới cho từng document response. Nếu HTML body và header được cache/ghi lại **không đồng bộ**, nonce mismatch là hệ quả rất dễ gặp.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant C as CDN
    participant S as Spring SSR
    B->>C: GET /checkout
    C->>S: Cache MISS, lấy document
    S-->>C: HTML nonce A + CSP nonce A
    C-->>B: HTML A + CSP A
    Note over C: Body HTML A được cache
    B->>C: GET /checkout lần sau
    C->>S: Lấy CSP/header mới hoặc xử lý edge
    S-->>C: CSP nonce B
    C-->>B: HTML cũ A + CSP B
    Note over B: Inline scripts A bị chặn
~~~

### Hướng kiểm soát caching

- Dynamic HTML chứa nonce: thường dùng `Cache-Control: no-store` và cấu hình CDN bypass cache cho HTML/authenticated routes nếu phù hợp.
- Static assets fingerprinted (JS/CSS/images) vẫn có thể được cache lâu; **không cần nhúng nonce vào nội dung JS file**.
- Nếu SSR fragment/edge side include được cache, fragment chứa inline script nonce phải được render với **nonce document hiện tại** hoặc đổi cấu trúc sang external script không cần nonce riêng.
- Với HTTP 304 hoặc revalidation, cần xem representation cuối browser dùng; đừng ghép header mới có nonce B với HTML cache nonce A.
- Với service worker, kiểm tra response HTML có bị trả từ cache cũ hay bị rewrite headers không.

### Nonce và cache policy không phải vấn đề browser duy nhất

Đừng kết luận từ một response HTTP 200 qua origin rằng CDN cache đã đúng. Hãy so **public response** qua cả cache hit/miss, request ID và policy version.

## 22. SSR hydration và các script inline do framework chèn

Các frontend frameworks có thể render:

~~~html
<script id="__BOOTSTRAP_DATA__" type="application/json">...</script>
<script>window.hydrateApp();</script>
~~~

Script chứa JSON data không thực thi có thể được xử lý khác tùy type, nhưng script hydrate thực thi phải được CSP cho phép theo quy tắc. **Không mặc định mọi thẻ `<script>` cần nonce chỉ vì tên tag giống nhau**; xác minh browser và content type.

### Lỗi thường gặp với renderer

1. Server framework tự sinh script bootstrap sau khi template code đã render.
2. Nonce được gắn vào script của ứng dụng nhưng thiếu trên script do SSR framework chèn.
3. Client hydration tạo inline script hoặc style tag runtime không truyền nonce.
4. Template engine escape/mutate attribute sai, ví dụ render chuỗi `"${nonce}"` literal.
5. Một script loader thêm script mới, nhưng CSP `script-src`/`strict-dynamic` không phù hợp.

### Cách xử lý

Đi theo pipeline thật: layout → SSR renderer → fragments → HTML response → browser. Kiểm tra nonce trên **từng script thực thi** và CSP header của đúng response. Tích hợp nonce vào API CSP của framework nếu framework hỗ trợ; không thêm một JavaScript runtime tự lấy nonce rồi sửa DOM **sau khi browser đã quyết định chặn bootstrap script**.

### Hạn chế inline script là một phương án tốt

Nếu ứng dụng có thể đưa bootstrap logic vào external JS cùng origin, hoặc bỏ inline event handlers và inline style attributes, cấu hình CSP có thể đơn giản hơn và ít phải truyền nonce hơn. Tuy nhiên dữ liệu SSR động cần cách bootstrap an toàn, escaping đúng và threat model riêng.

## 23. DevTools Console: khẳng định đó là CSP chứ không phải lỗi JS runtime

Một trang có nút không hoạt động có thể do:

~~~text
TypeError: Cannot read properties of null
~~~

hoặc:

~~~text
Refused to execute inline script because it violates CSP
~~~

Hai lỗi không tương đương. Nếu script bị CSP chặn, các hàm và event listeners trong script ấy chưa chạy, dẫn đến một chuỗi lỗi thứ cấp như `ReferenceError`. Cần khắc phục **violation gốc** trước thay vì sửa mọi ReferenceError bằng cách thêm globals.

### Checklist trong Console/Network

| Quan sát | Kết luận ban đầu cần kiểm chứng |
|---|---|
| “Refused to execute inline script” | Nonce/hash/inline script directive |
| “Refused to connect to …” | `connect-src`, có thể request chưa gửi |
| “Refused to load the stylesheet” | `style-src-elem`/`style-src` |
| “Refused to frame …” | `frame-src` ở parent hoặc `frame-ancestors` ở child |
| 403 POST trong Network | CSRF/authorization/auth; không phải chỉ CSP |
| CORS preflight 401/403 | Authentication/CORS pipeline, khác CSP |
| MIME type mismatch + nosniff | Content-Type/asset pipeline, không chỉ CSP |
| DNS/TLS/network failed | Không nới CSP trước khi xác minh network |
| Report-Only warning | Không phải cơ chế chặn nếu chỉ report policy |

**Quan sát thứ tự:** HTML response có CSP gì → browser đã tải/chặn resource nào → request API thật có gửi không → authentication/CSRF/authorization của request thật.

## 24. SecurityPolicyViolationEvent: đọc vi phạm bằng dữ liệu có cấu trúc

Đối với trang kiểm thử do mình kiểm soát, có thể thu violation events:

~~~javascript
document.addEventListener("securitypolicyviolation", (event) => {
  const record = {
    directive: event.effectiveDirective,
    blockedURI: event.blockedURI,
    disposition: event.disposition,
    sourceFile: event.sourceFile,
    lineNumber: event.lineNumber
  };

  // Trong lab có thể quan sát; production phải hạn chế/ẩn dữ liệu.
  console.debug("CSP violation", record);
});
~~~

`SecurityPolicyViolationEvent` có thể cho biết `effectiveDirective` và `disposition`, giúp phân biệt chặn enforce với cảnh báo Report-Only.

### Giới hạn cần hiểu

- Event listener phải được gắn **đủ sớm** để ghi nhận vi phạm ở giai đoạn bootstrap. Nếu chính script gắn listener bị CSP chặn, listener đó không chạy.
- Browser có thể ẩn/bớt dữ liệu `blockedURI` hoặc thông tin đường dẫn do quy tắc riêng tư và cross-origin restrictions.
- Sự vắng mặt của event trong một phép thử không chứng minh mọi chính sách đúng; lỗi có thể xuất hiện trước listener, trong iframe khác origin, hoặc do browser support.
- Không dùng dữ liệu event do client gửi như một lệnh cấu hình allowlist. Violation reports là **telemetry không đáng tin cậy**.

### Bảo vệ thông tin khi thu báo cáo

Nếu vận chuyển event/report về server, cần tránh ghi các URL chứa tokens, thông tin cá nhân, query nhạy cảm, code snippets hoặc nội dung do người dùng kiểm soát. Chỉ lưu trường cần cho chẩn đoán theo retention policy.

## 25. CSP violation reporting: thu đủ dữ liệu nhưng không tin mù quáng

Một chính sách có thể khai báo endpoint báo cáo, ví dụ dùng Reporting API theo mức browser hỗ trợ:

~~~http
Reporting-Endpoints: csp-endpoint="https://reports.example.com/csp"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; report-to csp-endpoint
~~~

Một số môi trường còn sử dụng `report-uri` để tương thích browser/triển khai:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; report-uri /csp-report
~~~

**Không coi hai cơ chế reporting hoàn toàn tương đương trên mọi browser.** Khả năng hỗ trợ, schema và cách gửi report phụ thuộc phiên bản/implementation. Quan sát Network/collector logs bằng browser mục tiêu.

### Report endpoint cũng có security boundary

- Thu báo cáo theo chính sách chống spam/rate limiting và validation kích thước/schema.
- Không yêu cầu browser gửi session credentials để “được phép báo lỗi” nếu điều đó không phù hợp cơ chế reporting.
- Không tự tắt CSRF trên toàn API chỉ vì một report endpoint; nếu endpoint chuyên tiếp nhận browser reports cần rule riêng, review threat model.
- Không để report chứa dữ liệu nhạy cảm trong ticket/analytics.
- Thêm version/build identifier để phân biệt policy canary và production.

Mục tiêu là tìm **các tài nguyên bị policy mới chặn**, không xây một đường đưa dữ liệu người dùng hoặc thông tin nội bộ ra ngoài.

## 26. MockMvc: chứng minh nonce trong CSP và HTML của cùng response khớp

Giả sử Servlet application có:

- `CspNonceServletFilter` gắn đúng `SecurityFilterChain`;
- Controller `GET /csp-lab` trả Thymeleaf view;
- Template có script `th:attr="nonce=${cspNonce}"`;
- Browser document route trả 200 với CSP duy nhất như mục 10.

Một test dùng full Spring Boot context:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletCspNonceTest {

    @Autowired MockMvc mockMvc;

    private static String nonceFromPolicy(String csp) {
        assertNotNull(csp);
        Matcher matcher = Pattern.compile(
            "script-src[^;]*'nonce-([^']+)'"
        ).matcher(csp);
        assertTrue(matcher.find(), "Missing script nonce in CSP");
        return matcher.group(1);
    }

    @Test
    void headerAndTemplateUseSameNonce() throws Exception {
        MvcResult result = mockMvc.perform(get("/csp-lab"))
            .andExpect(status().isOk())
            .andReturn();

        String csp = result.getResponse()
            .getHeader("Content-Security-Policy");
        String html = result.getResponse().getContentAsString();
        String nonce = nonceFromPolicy(csp);

        assertTrue(html.contains("nonce=\"" + nonce + "\""));
        assertEquals(1, result.getResponse()
            .getHeaders("Content-Security-Policy").size());
        assertEquals("no-store", result.getResponse()
            .getHeader("Cache-Control"));
    }

    @Test
    void separateResponsesUseDifferentNonces() throws Exception {
        MvcResult first = mockMvc.perform(get("/csp-lab"))
            .andExpect(status().isOk()).andReturn();
        MvcResult second = mockMvc.perform(get("/csp-lab"))
            .andExpect(status().isOk()).andReturn();

        String a = nonceFromPolicy(first.getResponse()
            .getHeader("Content-Security-Policy"));
        String b = nonceFromPolicy(second.getResponse()
            .getHeader("Content-Security-Policy"));
        assertNotEquals(a, b, "Nonce should be fresh per response");
    }
}
~~~

**Lưu ý phạm vi:** test này giả định template thật được render qua MockMvc có Thymeleaf. Nếu dùng `MockMvcBuilders.standaloneSetup(...)` chỉ gắn controller, bạn có thể **không chạy Spring Security filters**; đó là test setup khác. Nếu CSP được sinh ở gateway, MockMvc không phát hiện gateway ghi đè/lặp header.

### Không ghi nonce vào test logs

Test chỉ so nonce trong bộ nhớ và in thông điệp PASS/FAIL chung. Không print response body/CSP header chứa nonce lên CI logs khi không cần.

### Một điều kiện test hữu ích khác

Thêm test một request 401/403 của API mà không bị áp dynamic HTML nonce policy ngoài ý muốn. Không dùng một CSP nonce filter toàn cục khiến mỗi JSON response thêm nonce và vô tình ngăn caching hoặc lộ policy sai loại.

## 27. MockMvc: những lỗi không được che bằng permitAll hoặc disable CSRF

Sau khi CSP chặn script khởi tạo form, POST có thể không được gửi hoặc thiếu CSRF token. Đây là **hậu quả gián tiếp** khác với trường hợp POST đã tới Spring rồi bị CSRF 403.

Trong một Servlet lab có form được CSRF bảo vệ:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

mockMvc.perform(post("/api/profile")
        .with(user("alice").roles("USER"))
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isForbidden());

mockMvc.perform(post("/api/profile")
        .with(user("alice").roles("USER"))
        .with(csrf())
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isNoContent());
~~~

Đây là ví dụ trong một test method có imports/assertions và controller fixture trả 204. Một test `with(csrf())` chỉ mô phỏng token hợp lệ cho server; nó **không chứng minh JavaScript trong browser có thể tải CSRF token và gửi POST** khi CSP đang chặn bootstrap script.

**Hướng giải quyết:** sửa CSP/nonce để frontend bootstrap chạy, sau đó dùng browser E2E kiểm tra chuỗi GET CSRF token → POST cùng session. Không tắt CSRF hoặc bỏ authentication để làm một POST “xanh”.

## 28. WebTestClient: xác nhận reactive nonce và HTML thuộc cùng response

Giả sử WebFlux đã có `CspNonceReactiveFilter`, controller/Thymeleaf theo mục 17–18, và WebTestClient bind đúng application context:

~~~java
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveCspNonceTest {

    @Autowired WebTestClient webTestClient;

    private static String extractNonce(String csp) {
        assertNotNull(csp);
        Matcher m = Pattern.compile(
            "script-src[^;]*'nonce-([^']+)'"
        ).matcher(csp);
        assertTrue(m.find());
        return m.group(1);
    }

    @Test
    void renderedNonceMatchesCsp() {
        EntityExchangeResult<String> result = webTestClient.get()
            .uri("/csp-lab")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .returnResult();

        String policy = result.getResponseHeaders()
            .getFirst("Content-Security-Policy");
        String html = result.getResponseBody();
        String nonce = extractNonce(policy);

        assertNotNull(html);
        assertTrue(html.contains("nonce=\"" + nonce + "\""));
        assertEquals(1, result.getResponseHeaders()
            .getOrEmpty("Content-Security-Policy").size());
    }

    @Test
    void nonceIsNotReusedAcrossResponses() {
        EntityExchangeResult<String> first = webTestClient.get()
            .uri("/csp-lab").exchange()
            .expectBody(String.class).returnResult();
        EntityExchangeResult<String> second = webTestClient.get()
            .uri("/csp-lab").exchange()
            .expectBody(String.class).returnResult();

        assertNotEquals(
            extractNonce(first.getResponseHeaders()
                .getFirst("Content-Security-Policy")),
            extractNonce(second.getResponseHeaders()
                .getFirst("Content-Security-Policy"))
        );
    }
}
~~~

Test yêu cầu WebFlux application có template engine thật, WebFilter được đăng ký và được chọn cho `/csp-lab`. Nếu test client bind trực tiếp handler mà không chạy WebFilters, nó sẽ không tái hiện CSP middleware. Đối chiếu cách bootstrap test trong framework/version dự án.

### Header trên public response vẫn cần integration test

WebTestClient với mock application context không bắt được CSP do CDN/WAF/proxy thêm ở response công khai. Nếu local tests PASS nhưng browser production FAIL, so **cùng request qua origin và public edge** và kiểm tra HTML caching.

## 29. Playwright: chứng minh script được nonce cho chạy, script không nonce bị chặn

Trên môi trường HTTPS staging do nhóm kiểm thử sở hữu (ví dụ `https://app.example.test`), trang lab có hai inline scripts:

~~~html
<script nonce="VALID" data-lab="allowed">
  window.__allowedInlineExecuted = true;
</script>
<script data-lab="blocked">
  window.__blockedInlineExecuted = true;
</script>
~~~

HTML trên là **kết quả minh họa**. Trong ứng dụng thật, `VALID` được thay bằng nonce request và match CSP header.

### Browser behavior test

~~~javascript
import { test, expect } from "@playwright/test";

test("CSP nonce cho script đúng chạy và chặn script thiếu nonce",
  async ({ page }) => {
    const response = await page.goto(
      "https://app.example.test/csp-lab"
    );
    if (!response) throw new Error("No document response");
    expect(response.status()).toBe(200);

    const result = await page.evaluate(() => ({
      allowed: window.__allowedInlineExecuted === true,
      blocked: window.__blockedInlineExecuted === true,
      nonce: document.querySelector(
        'script[data-lab="allowed"]'
      )?.nonce ?? null
    }));

    const headers = await response.allHeaders();
    const policy = headers["content-security-policy"] ?? "";
    const headerNonce = policy.match(
      /script-src[^;]*'nonce-([^']+)'/
    )?.[1] ?? null;

    expect(result.allowed).toBe(true);
    expect(result.blocked).toBe(false);
    expect(result.nonce).toBe(headerNonce);
});
~~~

**Cần lưu ý:**

- Test dùng browser engine thật với CSP enforcement mặc định; không tắt web security.
- Khi JavaScript đọc nonce, dùng thuộc tính `element.nonce`. Vì cơ chế *nonce hiding*, một số browser có thể trả giá trị rỗng qua `getAttribute("nonce")` nhằm hạn chế một số kiểu CSS selector/exfiltration; đó **không chứng minh nonce thiếu**.
- Assert chỉ dựa vào `page.evaluate` sau load có thể bỏ qua một vài timing/async script; với app có hydration phức tạp hãy chờ readiness signal phù hợp.
- Negative test phải xác nhận browser thực sự chặn inline script, không chỉ response có CSP string.

### Thu violation event từ đầu trang khi cần

~~~javascript
test("ghi nhận CSP violation trong lab", async ({ page }) => {
  await page.addInitScript(() => {
    window.__cspViolations = [];
    document.addEventListener("securitypolicyviolation", (event) => {
      window.__cspViolations.push({
        directive: event.effectiveDirective,
        disposition: event.disposition
      });
    });
  });

  await page.goto("https://app.example.test/csp-lab");
  const violations = await page.evaluate(
    () => window.__cspViolations ?? []
  );

  expect(violations.some(v =>
    v.disposition === "enforce" &&
    v.directive.startsWith("script-src")
  )).toBe(true);
});
~~~

Event collection phụ thuộc browser test harness và thời điểm listener. Dùng thêm browser console và Network khi cần, không xem một test event thiếu dữ liệu là bằng chứng policy không chặn.

## 30. Kiểm thử một chức năng API thật: connect-src và CORS là hai cửa kiểm tra

Giả sử từ trang `https://app.example.com`, frontend gọi:

~~~javascript
await fetch("https://api.example.com/api/orders", {
  credentials: "include",
  headers: { "X-CSRF-TOKEN": csrfToken }
});
~~~

Nhưng CSP document là:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-N'; connect-src 'self'
~~~

`connect-src 'self'` có thể **không cho phép** kết nối tới `https://api.example.com` vì khác origin. Khi browser chặn theo CSP, request có thể không xuất hiện trong Network hoặc Spring access logs.

### Sửa với allowlist hẹp

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-N'; connect-src 'self' https://api.example.com
~~~

Lúc này request còn phải vượt qua:

1. Browser CORS khi origin khác và request có CORS requirements.
2. Cookie `Secure`/`SameSite`/`Domain`/`Path` và `credentials` mode nếu dùng session.
3. CSRF protection nếu request thay đổi state và flow cần token.
4. Authentication/authorization/business validation ở server.

**CSP không thay thế CORS**, và một request có `connect-src` hợp lệ vẫn có thể bị server 401/403. Không tắt CORS hoặc CSRF để “chữa CSP”.

### WebSocket và EventSource

Nếu ứng dụng kết nối `wss://events.example.com/socket` hoặc server-sent events, phải xác minh origin endpoint tương ứng trong `connect-src`. Không giả định `'self'` luôn bao phủ mọi kết nối WebSocket `wss:` ở mọi browser và topology; khi cần, khai báo chính xác WSS origin được tin cậy.

## 31. Browser automation kiểm thử chức năng, không chỉ đọc header

Một test chỉ so:

~~~javascript
expect(headers["content-security-policy"]).toContain("script-src");
~~~

chưa chứng minh chức năng checkout/login/upload hoạt động. Test browser nên xác nhận **hành vi có mục tiêu**:

- Script có nonce khớp được thực thi.
- Script không nonce bị chặn.
- Form submit yêu cầu CSRF, và POST thật được gửi theo policy.
- Fetch API được `connect-src` cho phép khi origin hợp lệ.
- CORS được server chấp thuận khi frontend cross-origin.
- WebSocket hoặc iframe cần thiết hoạt động mà không nới policy ngoài phạm vi.
- Network không bị redirect/mixed content/TLS/CSP sai.

### Test tránh side effect thật

Với checkout/upload/payment, dùng fixture hoặc sandbox endpoint, không test trực tiếp giao dịch thật. Nếu browser báo fetch failure, kiểm tra server đã xử lý request chưa trước khi tự retry POST. CSP failure xảy ra trước network có hành vi khác với CORS failure sau actual request.

### Negative test quan trọng

Chỉ một positive test “button click thành công” không đủ. Nếu CSP được nới thành `script-src 'unsafe-inline'`, chức năng có thể chạy nhưng lớp bảo vệ quan trọng bị mất. Giữ negative test script không nonce vẫn bị chặn trên document test.

## 32. CSP và các lớp Spring Security khác: đừng chẩn đoán nhầm

| Hiện tượng | Lớp cần xem trước | Dữ liệu chứng minh |
|---|---|---|
| Inline script không chạy, Console báo CSP | CSP nonce/script-src | HTML document CSP + nonce trên script |
| Script chạy nhưng API không có request | `connect-src` hoặc network/CSP | Browser violation, Network request absence |
| OPTIONS preflight 401/403 | CORS trước authentication, chain order, gateway | OPTIONS request/response |
| POST thực nhận 403 + CSRF failure | CSRF token/session | Spring Security CSRF logs |
| POST thực nhận 403 do thiếu role | Authorization | AccessDenied/security matcher |
| GET API 401 | Authentication/cookie/session | Request Cookies, challenge, server logs |
| UI lỗi sau CDN deploy, nonce lúc đúng lúc sai | HTML/header cache mismatch | Same-response header/body, cache HIT/MISS |
| Resource bị MIME reject, có `nosniff` | Content-Type/MIME handling | JS/CSS response headers |
| CSP violation không có nhưng fetch `TypeError` | CORS, DNS/TLS, mixed content, runtime | Browser Console và Network |
| HTTP redirect lặp giữa HTTP/HTTPS | HSTS/TLS proxy forwarding | Location, scheme, forwarded headers |
| Request bị HTTP firewall từ chối | URL normalization, firewall | `RequestRejectedException`/HTTP parser |
| Cookie không đi cross-site | SameSite/credentials/browser policy | Actual Request Cookies, blocked reasons |

**Phân biệt response của HTML và response của API.** CSP thường được áp từ document; CORS/CSRF/auth xử lý request API. Nếu script bootstrap bị CSP chặn thì POST có thể không được gửi, không có CSRF error của POST để sửa.

## 33. Tầng viết CSP: Spring, ingress, CDN hay ứng dụng frontend?

Một production path có thể:

~~~mermaid
flowchart LR
    B[Browser] --> C[CDN/cache]
    C --> G[Ingress/gateway]
    G --> S[Spring Security]
    S --> T[Template SSR]
    T --> S
    S --> G
    G --> C
    C --> B
~~~

Nguồn CSP có thể là:

1. Spring Security `ContentSecurityPolicyHeaderWriter` (policy tĩnh).
2. Custom Servlet `Filter`/reactive `WebFilter` (policy động theo nonce).
3. Controller/header builder hoặc exception handler.
4. Nginx/Ingress/API Gateway cấu hình `add_header`/rewrite.
5. CDN rules, edge middleware, worker, cache policy.
6. Meta CSP trong HTML template.

### Cách so giữa origin và public

| Spring origin response | Public response | Giả thuyết |
|---|---|---|
| Header nonce A, body nonce A | Header A, body A | Đường đi CSP cơ bản khớp |
| Header A, body A | Header B, body A | Proxy/edge đổi CSP header |
| Header A, body A | Header A và policy B, body A | Gateway thêm enforce policy thứ hai |
| Header A, body A | Header A, body B | Cached/rewrite body hoặc template ở tầng khác |
| Header A, body B | Giữ nguyên A/B | Mismatch đã phát sinh trong Spring/template |
| Header/body khớp nhưng browser chặn external API | Khớp | Directive khác (connect-src, frame-src...) |

Phép thử phải giữ **cùng request, same Origin, same path và cùng cache state**; không so nonce từ hai document responses khác nhau rồi kết luận edge sửa header.

### Một chủ sở hữu không có nghĩa mọi header phải đến cùng tầng

HSTS có thể do HTTPS edge phát, còn CSP nonce gắn với SSR template nên hợp lý hơn để **application render CSP và HTML cùng nhau**. Thiết kế phải có hợp đồng rõ ràng giữa owners; không mặc định CDN phải viết CSP nonce nếu nó không biết nonce HTML.

## 34. Kịch bản A — Nonce sinh hai lần trong một Servlet request

**Triệu chứng:** mọi lần tải `/checkout` đều có CSP violation inline script. Header:

~~~http
Content-Security-Policy: script-src 'self' 'nonce-HEADER_A'
~~~

HTML:

~~~html
<script nonce="TEMPLATE_B">startCheckout();</script>
~~~

**Root cause:** HeaderWriter/controller/template helper mỗi nơi gọi generator riêng.

### Chẩn đoán và sửa

1. Dùng test lấy header/body từ **cùng** MockMvc request.
2. Tìm mọi nơi gọi `SecureRandom`/nonce helper.
3. Chỉ giữ một lần tạo nonce cho document response.
4. Đưa nonce vào request attribute rồi truyền tới Model/Thymeleaf.
5. Bỏ static CSP writer khác nếu nó dùng nonce độc lập.
6. Test hai document responses mới phải có nonce khác nhau.
7. Test browser allowed script chạy, blocked script không nonce vẫn bị chặn.

**Không sửa** bằng cách copy một nonce cố định vào header và template. Cách đó làm test khớp nhưng phá freshness của CSP nonce.

## 35. Kịch bản B — Lỗi chỉ xảy ra lúc CDN cache hit hoặc sau deploy

**Triệu chứng:** lần đầu tải trang thành công, refresh một số lần thì script bị CSP chặn; ứng dụng có nhiều node hoặc CDN.

~~~text
Origin response mới:
  CSP nonce B
  HTML body nonce B

CDN HIT lỗi:
  CSP nonce B
  HTML cached nonce A
~~~

### Chẩn đoán

- Xem `Age`/cache status, response source và build version.
- Đối chiếu **header và HTML của cùng public response**.
- So cache MISS vs HIT, ETag/304 và service worker nếu có.
- Xem HTML dynamic có `Cache-Control: no-store` và edge có tuân thủ không.
- Kiểm tra SSR/ESI fragments chứa inline script/nonce cũ.

### Sửa

Không cache độc lập body/header nonce động. Tách static assets để cache lâu, giữ dynamic document nonce theo từng response. Nếu cần cached fragments, bỏ script inline khỏi fragments hoặc phối hợp inject nonce document hiện tại.

**Không** chuyển nonce sang session-level/fixed chỉ để cache được HTML.

## 36. Kịch bản C — Spring nonce khớp nhưng gateway thêm CSP tĩnh

**Triệu chứng:** local MockMvc PASS; browser production vẫn báo inline script violation.

~~~text
Spring:
  CSP: script-src 'self' 'nonce-A'
  HTML: <script nonce="A">

Public gateway:
  CSP policy 1: script-src 'self' 'nonce-A'
  CSP policy 2: script-src 'self'
~~~

Policy thứ hai không cho inline script, nên browser chặn.

### Cách xử lý

1. Xem **toàn bộ** Content-Security-Policy headers của document public.
2. So Spring origin với public response.
3. Xác định rule gateway/edge đã thêm CSP thứ hai.
4. Chọn một policy owner hoặc thiết kế các enforced policies phối hợp mà không chặn legitimate scripts.
5. Test cả HTML 200 và response error/redirect nếu gateway có rule khác theo status.

**Đừng thêm `'unsafe-inline'` vào Spring policy**: nếu gateway vẫn chặn, chức năng chưa chắc được sửa; nếu policy được nới thực, bảo vệ lại yếu đi.

## 37. Kịch bản D — Script chạy rồi fetch/WebSocket bị chặn

**Triệu chứng:** nonce header/template đúng, bootstrap script chạy, nhưng trang không tải dữ liệu hoặc realtime updates.

Browser báo:

~~~text
Refused to connect to 'https://api.example.com/data'
because it violates "connect-src 'self'".
~~~

### Quy trình

1. Xác nhận script bootstrap thực sự chạy và không có nonce violation.
2. Kiểm tra `effectiveDirective=connect-src` và endpoint thực.
3. Cho phép **đúng API/WSS origin được duyệt** trong `connect-src`.
4. Test CORS riêng cho API cross-origin và cookie credentials nếu có.
5. Xác nhận CSRF/auth/authorization của actual API request vẫn hoạt động.
6. Không cho `connect-src *` theo phản xạ.

Nếu request có mặt trong Spring logs và nhận 403 CSRF, đó không còn là kết luận “CSP chặn connect” cho request ấy.

## 38. Kịch bản E — Modal/checkout hỏng do inline handler hoặc CSS-in-JS

**Triệu chứng:** nonce script khớp, nhưng nút dùng `onclick="pay()"` không chạy, hoặc modal có HTML nhưng không có style.

### Kiểm tra

| Ngữ cảnh | Nguyên nhân thường gặp | Sửa hợp lý |
|---|---|---|
| `onclick="..."` | `script-src-attr` không cho inline handler | Dùng `addEventListener` |
| `javascript:...` URL | Inline script execution bị policy chặn | Dùng URL/handler đúng nghĩa |
| `<style>` từ SSR | Thiếu nonce/style-src phù hợp | CSS file hoặc nonce cho style tag |
| `style="..."` | Style attribute không được nonce style tag mở | CSS classes hoặc policy được review |
| CSS-in-JS runtime | Library tạo style tag nhưng thiếu nonce | Tích hợp nonce request vào library |
| Template fragment cũ | Style/script nonce từ response khác | Bỏ fragment nonce cache hoặc re-render |

**Không bật `'unsafe-inline'` trên toàn policy** chỉ vì một thành phần UI bị chặn. Chỉnh cấu trúc frontend hoặc policy hẹp sau khi xác định chính directive.

## 39. Kịch bản F — Iframe thanh toán và redirect SSO thất bại

**Triệu chứng:** trang checkout mở được nhưng iframe payment provider trống; hoặc form login chuyển đến identity provider bị CSP chặn.

### Ba directive không nên nhầm

- `frame-src` ở **trang cha** quyết định nơi trang cha được phép nhúng iframe.
- `frame-ancestors` trên **trang con** quyết định những origin nào được nhúng trang con (không được thay bằng `frame-src` ở chính child).
- `form-action` ở **trang chứa form** giới hạn nơi form được gửi đến.

Ví dụ policy parent:

~~~http
Content-Security-Policy: default-src 'self'; frame-src 'self' https://checkout.partner.example; form-action 'self' https://login.idp.example
~~~

Nếu child trang thanh toán phát:

~~~http
Content-Security-Policy: frame-ancestors 'none'
~~~

parent vẫn không thể nhúng chỉ bằng việc mở `frame-src`. Đây là quyết định bảo mật của trang con, không nên tìm cách vượt qua bằng tắt CSP ở trang cha.

**Sửa đúng:** review hợp đồng tích hợp với IdP/partner, đúng URL và redirect behavior, frame policy của từng phía, HTTPS/TLS, cookies/SameSite trong iframe. Không thêm wildcard hoặc tắt toàn bộ CSP chỉ vì một provider widget.

## 40. Kịch bản G — Header nonce có nhưng trang error/login không render template đó

**Triệu chứng:** `GET /dashboard` chạy bình thường; trang login, redirect destination hoặc lỗi 500 có CSP violation, thậm chí template code không tìm thấy `cspNonce`.

Nguyên nhân có thể:

- Nonce filter chỉ áp dụng `/dashboard`, trong khi error HTML được render bởi `/error`.
- Filter đặt trong security chain không match route đăng nhập hoặc 404 page.
- `web.ignoring()` loại một số public HTML khỏi chain.
- Error dispatch dùng filter registration/dispatcher types khác.
- CDN/WAF trả error page HTML với CSP riêng nhưng thiếu nonce tương ứng.
- Template layout dùng fragment từ pipeline khác không nhận Model nonce.

### Cách xử lý

1. Kiểm tra **response HTML cuối cùng**: status, CSP và tất cả script/style elements.
2. Xác định ai render HTML: Spring MVC/Thymeleaf, WebFlux, default login page, proxy error template hay CDN.
3. Xem path/dispatcher types và chain matcher, không chỉ controller path.
4. Với mỗi loại HTML document có inline script, bảo đảm một CSP owner và nonce cùng response.
5. Nếu error page không cần inline script, chọn policy chặt và tách template đơn giản thay vì tái sử dụng bootstrap SPA.

Không có yêu cầu tất cả HTML pages phải dùng **cùng một nonce**: đúng hơn, mỗi document response có nonce mới và template tương ứng. Error HTML không tự động kế thừa nonce từ request trước.

## 41. Kịch bản H — Chỉ development/hot reload lỗi vì eval, production khác

**Triệu chứng:** frontend dùng development server, devtools/hot reload/source-map runtime và xuất hiện:

~~~text
Refused to evaluate a string as JavaScript because 'unsafe-eval'
is not an allowed source of script...
~~~

Đây có thể là một dependency/tooling đang dùng `eval`, `new Function` hoặc code generation động. Việc thêm nonce cho `<script>` bootstrap **không giải quyết** hoạt động eval trong script.

### Quy trình

1. Xem stacktrace/chunk runtime nào sử dụng eval.
2. Xác định chỉ dev/HMR hay tồn tại trong production bundle.
3. Ưu tiên cấu hình build không dùng eval, hoặc dependency alternative.
4. Có policy development riêng nếu bắt buộc phục vụ tooling; kiểm soát không deploy cờ nguy hiểm sang production.
5. Test production artifact dưới CSP enforce thật.

Không đưa `'unsafe-eval'` hoặc `'unsafe-inline'` vào production chỉ vì developer console của dev mode báo lỗi.

## 42. Ma trận chẩn đoán nhanh theo dấu hiệu

| Quan sát | Giả thuyết chính | Bằng chứng quyết định | Hướng sửa |
|---|---|---|---|
| Inline script có nonce nhưng bị từ chối | Header/template mismatch | Header và script nonce trong **cùng response** | Một generator per document |
| Script A chạy, script B không chạy | Script B thiếu nonce/hash hoặc policy khác | Kiểm tra từng script element và effectiveDirective | Gắn đúng nonce hoặc chuyển external |
| Nonce khớp, browser vẫn chặn | Nhiều enforced CSP policies | Raw header list/meta CSP | Một CSP owner/policies tương thích |
| Local PASS, CDN HIT FAIL | Body/header hoặc fragment cache lệch | So HIT/MISS cùng public response | Bypass cache dynamic HTML |
| CSS-in-JS không render | `style-src`/`style-src-elem` | Violation event/inline style tag | CSS file hoặc nonce style tag |
| `onclick` không chạy | `script-src-attr` | Element attributes và Console | addEventListener |
| Script chạy, fetch không gửi | `connect-src` | Violation connect-src và Network | Exact API allowlist |
| Fetch gửi nhưng browser CORS error | CORS response | Actual/preflight response headers | Sửa CORS riêng |
| POST gửi, Spring trả 403 | CSRF/authorization | Spring logs/status | Sửa token/roles, giữ CSP |
| API trả 401 | Auth/session/cookie | Cookie/Authorization request thật | Sửa session/auth riêng |
| External JS không tải | `script-src(-elem)` hoặc SRI/MIME/TLS | Console, Network, response | Source policy và asset pipeline |
| Eval bị chặn | `'unsafe-eval'` thiếu | Eval violation/stacktrace | Loại eval khỏi production |
| Iframe payment bị chặn | `frame-src` hoặc child `frame-ancestors` | Policy của parent và child | Sửa hợp đồng tích hợp |
| Form SSO không submit | `form-action` | Destination thực, violation | Thêm trusted IdP cụ thể |
| WebSocket không kết nối | `connect-src`/WSS/CORS/network | Browser và server WS logs | Exact WSS endpoint |
| Report-Only cảnh báo, chức năng vẫn chạy | Chính sách quan sát | `disposition=report` | Điều chỉnh candidate policy |
| HTML mới nhưng nonce cũ sau navigation | SPA/fragment/service-worker cache | Response header/body và cache | Fresh document nonce |
| CSP thiếu chỉ trên error HTML | Error route/proxy chain khác | Status, response source, matcher | CSP owner cho error page |
| CSP cho hết mọi Origin sau fix | Allowlist/wildcard nới quá rộng | Negative tests với nguồn không tin | Thu hẹp policy |
| Header CSP đúng nhưng HTML/JS không chạy do MIME | nosniff/Content-Type | Script response MIME và Console | Sửa MIME/asset routing |

**Cùng một thông báo “Failed to fetch” hoặc “button không hoạt động” có thể phát sinh ở nhiều lớp.** Đừng xóa CSP trước khi có bằng chứng vi phạm chính sách trên đúng document; đừng sửa CSRF khi request POST chưa từng tới server.

## 43. Runbook chẩn đoán tám bước

~~~mermaid
flowchart TD
    A[Chức năng hỏng sau triển khai CSP] --> B{Browser báo CSP violation enforce?}
    B -- Không --> C[CORS, CSRF, auth, MIME, TLS, runtime và network]
    B -- Có --> D[Đọc effectiveDirective và blockedURI]
    D --> E{Nonce-related inline script/style?}
    E -- Có --> F[So nonce CSP header và HTML của cùng response]
    F --> G{Khớp nhưng vẫn blocked?}
    G -- Có --> H[Multiple CSP headers, meta, cache, policy khác]
    G -- Không --> I[Single nonce generator, template binding, SSR/cache]
    E -- Không --> J[Source list theo connect/style/frame/form/script]
    H --> K[Test browser hành vi thật]
    I --> K
    J --> K
    C --> K
    K --> L[Positive/negative + Servlet/Reactive regression]
~~~

### Bước 1 — Chọn một request document và chức năng bị lỗi

Ghi browser, URL, method, build, user flow, status, response source và thời điểm triển khai. Với lỗi ở iframe, chọn đúng document cha/con. Không lấy CSP header từ API JSON thay cho CSP trên trang HTML.

### Bước 2 — Xem CSP enforce, Report-Only và Console

Đọc toàn bộ `Content-Security-Policy`, `Content-Security-Policy-Report-Only`, meta CSP nếu có. Ghi `effectiveDirective`, `disposition`, `blockedURI` và status của resource request. Nếu chỉ Report-Only, không kết luận policy đó đã chặn chức năng.

### Bước 3 — Xác định hành vi bị chặn

Script inline, script CDN, style, fetch/WebSocket, frame, form hay worker? Chọn directive tương ứng; không nới `script-src` để sửa một vi phạm `connect-src`.

### Bước 4 — Nếu có nonce, so đúng **một document response**

Lấy header và body cùng request. So nonce từng inline script/style với policy hiệu lực. Xem nonce có được tạo một lần mỗi request và template đã dùng đúng attribute chưa. Không lấy nonce từ một request khác để so.

### Bước 5 — Xác định CSP owner và caching

So Spring origin với public CDN/proxy; kiểm tra CSP headers bị append/rewrite, HTML cache hit, SSR/ESI fragments, service worker và response error. Nếu có nhiều enforce policies, tìm policy thực sự chặn.

### Bước 6 — Sửa nhỏ nhất

Ưu tiên thay inline handler/eval bằng thiết kế frontend phù hợp, gắn nonce đúng template hoặc cho phép **nguồn cần thiết được review** trong directive tương ứng. Không tắt CSP toàn cục, không dùng `unsafe-inline`/`unsafe-eval` hay wildcard để che lỗi.

### Bước 7 — Test browser và các lớp Spring Security liên quan

Playwright chứng minh script đúng chạy và script thiếu nonce bị chặn; test login/logout/CSRF/POST, CORS preflight, session, CSP connect-src/frame-src. Với API side effects, xác nhận request đã gửi hay chưa trước khi retry.

### Bước 8 — Hồi quy deploy/canary/cache

Test Servlet MockMvc hoặc Reactive WebTestClient nonce freshness, HTTPS public header/body, CDN cache hit/miss, response error và nhiều nodes. Quan sát Report-Only/violation reporting theo privacy policy. Chỉ nâng sang enforce rộng sau khi critical flows và negative cases đạt.

## 44. Những cách sửa sai có thể làm mất phòng vệ

| Anti-pattern | Vì sao sai | Cách thay thế |
|---|---|---|
| Tắt CSP khi một button lỗi | Mất lớp hạn chế XSS/third-party script | Tìm directive cụ thể và fix đúng |
| Thêm `'unsafe-inline'` để mọi inline script chạy | Giảm tác dụng chặn script injection | Nonce/hash hoặc external scripts |
| Thêm `'unsafe-eval'` vì dev tool lỗi | Cho phép code evaluation động rộng hơn | Build/dependency không eval ở production |
| Nonce cố định trong application.yml | Không có freshness, attacker có thể đoán | SecureRandom per document response |
| Dùng session ID/CSRF token làm nonce | Trộn security boundaries, lộ credential nếu render | Nonce độc lập không dùng làm credential |
| Tạo nonce riêng ở header và template | Mismatch dù cả hai random | Một nonce attribute chung |
| Sinh nonce mới khi static bundle được tải | Không làm HTML document nonce đúng | Sinh nonce ở HTML response, không phải mỗi asset |
| Cache HTML dynamic kèm nonce lâu dài | Reuse hoặc header/body mismatch | Bypass cache dynamic HTML, cache static assets |
| Cho CDN thêm CSP tĩnh bên cạnh CSP nonce | Multiple policies có thể chặn script hợp lệ | Một CSP owner/hợp đồng rõ |
| Chỉ nhìn header đầu tiên | Bỏ sót enforce policy khác hoặc meta | Đọc mọi CSP enforce/report |
| Thấy CSP violation rồi nới `default-src *` | Mở quá nhiều nhóm tài nguyên | Sửa directive chính xác |
| Thêm nonce cho `onclick=`, mong handler chạy | Nonce script tag không mở event attributes | addEventListener |
| Dùng nonce của script cho style không khai báo style policy | Không được `style-src` chấp thuận | Cấu hình style-src hoặc external CSS |
| Chuyển tất cả API sang `permitAll()` khi frontend lỗi | Mở authentication/authorization | Sửa CSP/CORS, giữ API auth |
| Tắt CSRF để POST 403 biến mất | Mất chống CSRF cho browser credentials | Sửa token/session, giữ CSRF |
| Bật CORS wildcard để xử lý `connect-src` | CORS không thay CSP của HTML | Chỉnh connect-src hẹp và CORS riêng |
| Retry POST khi browser báo CORS/CSP | Có thể tạo side effect hai lần | Kiểm tra server state/idempotency |
| Đưa nonce hoặc URL tokens vào analytics logs | Có nguy cơ rò dữ liệu, khó tuân thủ privacy | Log metadata cần thiết, sanitize |
| Chỉ assert CSP header tồn tại | Không chứng minh nonce match hoặc browser enforce | So same response + positive/negative browser tests |
| Tắt web security trong Playwright | Mất giá trị phép thử | Browser mặc định với HTTPS/cert hợp lệ |

**Không có một policy CSP “cứ mở hết là an toàn”.** Việc sửa chức năng phải đi cùng mục tiêu bảo toàn phòng vệ XSS và tránh nới trust boundary của ứng dụng.

## 45. Bài thực hành tổng hợp: chẩn đoán CSP nonce mismatch qua Spring và proxy

**Môi trường:** một lab an toàn với hai biến thể Servlet/MVC/Thymeleaf và Reactive/WebFlux/Thymeleaf; HTML route `GET /csp-lab`, script inline đúng nonce, script inline không nonce, CSS file cùng origin, API demo được bảo vệ, HTTPS reverse proxy/CDN mock và Playwright.

### Nhiệm vụ

1. **Baseline:** dùng one nonce per document và CSP enforce `script-src 'self' 'nonce-N'`; ghi header và HTML từ **cùng response**.
2. **Servlet:** triển khai `CspNonceServletFilter`, gắn vào đúng `SecurityFilterChain`; controller lấy request attribute và Thymeleaf `th:attr` render nonce.
3. Viết MockMvc test: CSP nonce bằng HTML script nonce, response khác dùng nonce khác, header CSP một giá trị, HTML dynamic không cache chia sẻ.
4. **Reactive:** triển khai `CspNonceReactiveFilter` gắn global WebFilter có order phù hợp, controller lấy exchange attribute; WebTestClient so nonce/header/body.
5. **Browser:** chạy Playwright trên HTTPS staging; script có nonce thực thi, script không nonce không thực thi, không bỏ qua web security/TLS.
6. **Sai lệch có chủ đích:** làm controller sinh nonce B khác filter nonce A; test MockMvc/WebTestClient phải FAIL; sửa bằng một source.
7. **Static CSP writer:** thêm một CSP tĩnh có mục đích ở security/gateway lab; xác nhận browser chặn theo policy bổ sung dù nonce A khớp policy đầu.
8. **Cache lỗi:** mô phỏng cache body HTML nonce A, gắn CSP header nonce B; xác minh mismatch; sửa cache policy cho document và fragments.
9. **Report-Only:** chuyển candidate policy sang `Content-Security-Policy-Report-Only` và phân biệt warning với enforcement.
10. **connect-src:** đặt frontend gọi API/WSS demo chưa được phép; xác minh CSP block trước request; mở đúng origin theo review rồi test CORS/auth riêng.
11. **Inline handler:** để `onclick=` trên button; xác nhận nonce script không mở handler; chuyển sang `addEventListener`.
12. **style-src:** thử inline style tag không nonce rồi dùng CSS file hoặc style nonce cùng response theo policy.
13. **iframe/form:** dùng các endpoints lab khác origin, phân biệt `frame-src`/`frame-ancestors`/`form-action`.
14. **CSRF:** sau khi frontend script đã chạy, thử POST có và không có token; xác nhận 403 thực là CSRF chứ không phải CSP.
15. **Hạ tầng:** so raw CSP headers/body Spring origin với HTTPS public qua proxy/cache, test 200/302/401/403/error pages.
16. **Regression:** giữ một negative test script không nonce vẫn bị chặn và one CSP owner; không thêm unsafe-inline/unsafe-eval/wildcard.

### Bảng minh họa kết quả

| Ca kiểm thử | CSP header nonce | HTML nonce | Browser dự kiến |
|---|---|---|---|
| Same-response hợp lệ | A | A | Inline script có nonce được phép |
| Sinh nonce hai lần | A | B | Script B bị chặn |
| Hai document responses liên tiếp | A rồi B | A rồi B tương ứng | Cả hai hợp lệ, nonce mới |
| Cache body HTML cũ | B | A | Script A bị chặn |
| CSP thứ hai ở gateway không cho inline | A và policy khác | A | Vẫn có thể bị chặn |
| Script thiếu nonce | A | Không có | Bị chặn theo enforce |
| Report-Only đơn độc, script thiếu nonce | Policy report | Không có | Không bị chặn vì riêng report policy |
| CSP connect-src không cho API | A | A | Bootstrap có thể chạy, fetch bị CSP chặn |
| CSP đúng, POST thiếu CSRF | A | A | Request POST có thể nhận 403 CSRF |
| CSP đúng, response API CORS sai | A | A | Fetch có thể bị CORS chặn đọc response |

### Mẫu báo cáo kỹ thuật

| Trường | Giá trị ghi nhận |
|---|---|
| Document/request ID | ID không chứa secrets |
| URL + Content-Type | HTML document URL thật |
| CSP owner | Spring filter hoặc edge theo thiết kế |
| Response status | HTTP 200/30x/40x... |
| CSP enforce count | Số chính sách được áp |
| Effective directive | `script-src-elem`/`connect-src`... |
| Report/enforce | Browser disposition |
| Nonce header/body match | YES/NO (không cần lưu nguyên nonce) |
| Nonce freshness | Khác giữa documents? |
| Cache source | Origin/CDN HIT/MISS/service worker |
| Actual API request sent | YES/NO |
| Root cause | Policy mismatch, template, cache, gateway, runtime... |
| Minimal fix + negative test | Bảo toàn phòng vệ nào? |

Không đính kèm body chứa dữ liệu người dùng hay Authorization/Cookie/CSRF token vào báo cáo. Với nonce, thông tin **match/mismatch** thường đủ cho triage; không cần chia sẻ nonce production.

## 46. Câu hỏi tự đánh giá

1. Vì sao trang HTML có HTTP 200 vẫn có thể không chạy JavaScript?
2. `Content-Security-Policy` và `Content-Security-Policy-Report-Only` khác nhau ở điểm nào?
3. Làm thế nào nhận ra một policy Report-Only không phải nguyên nhân trực tiếp của hành vi bị chặn?
4. Vì sao phải so nonce header với HTML **của cùng response**?
5. Tại sao nonce được tạo lại mỗi document response mà không dùng một giá trị trong session?
6. Vì sao `SecureRandom` phù hợp hơn giá trị cố định hoặc generator yếu?
7. Phải truyền nonce từ Servlet filter đến Thymeleaf thông qua dữ liệu request nào?
8. Với WebFlux, đối tượng nào lưu nonce theo request thay cho `HttpServletRequest`?
9. Vì sao không nên lưu nonce vào static mutable field hoặc `ThreadLocal`?
10. `HeaderWriterFilter`/`ContentSecurityPolicyHeaderWriter` có tự tạo nonce động theo template không?
11. Vì sao thêm một CSP enforce header thứ hai có thể làm script đúng nonce vẫn bị chặn?
12. CDN cache body HTML nhưng cập nhật header CSP riêng sẽ gây ra lỗi gì?
13. `Cache-Control: no-store` nên tập trung ở HTML dynamic hay mọi bundle có hash?
14. `onclick=` có được phép chỉ vì một script tag khác có nonce đúng không?
15. Script nonce và style nonce phụ thuộc những directives nào?
16. Nonce có làm `style="..."` attribute được phép không?
17. Vì sao bật `'unsafe-inline'` để sửa UI hỏng có rủi ro?
18. Vì sao bật `'unsafe-eval'` vì dev tooling cần được xét riêng khỏi production?
19. Nếu `connect-src` chặn API, request có nhất thiết xuất hiện trong Spring logs không?
20. CORS khác `connect-src` và CSRF khác CSP ở mục tiêu gì?
21. Khi `frame-src` đã cho iframe nhưng `frame-ancestors 'none'` của child vẫn chặn, ai cần sửa policy?
22. `form-action` dùng để kiểm soát hành vi nào trong login/SSO?
23. Tại sao một WebTestClient/MockMvc PASS không chứng minh CDN public CSP đúng?
24. Điều gì làm một error page có thể thiếu nonce dù dashboard bình thường?
25. Vì sao phải kiểm tra script bootstrap SSR và script do library runtime chèn?
26. Browser nonce hiding khiến `getAttribute("nonce")` có thể gây hiểu nhầm thế nào?
27. Trong Playwright, điều kiện tích cực/tiêu cực nào chứng minh CSP vừa cho phép hợp lệ vừa chặn injection?
28. Nếu browser báo fetch failure sau POST, có được retry ngay không? Vì sao?
29. Vì sao CSP reporting endpoint không nên ghi raw URL/tokens vào logs?
30. Những điều kiện cần PASS trước khi chuyển một candidate CSP từ Report-Only sang Enforce?

## 47. Ghi nhớ

**CSP làm hỏng chức năng** khi browser thực thi một policy không cho phép hành vi frontend đang sử dụng; lỗi có thể đến từ script, style, connect, iframe, form, worker hoặc một CSP enforce policy khác. **Nonce mismatch** là trường hợp đặc biệt: nonce được render trên script/style element không khớp nonce mà CSP của **chính document response** cho phép.

Trong **Servlet**, có thể tạo nonce qua `SecureRandom` trong request-aware filter, lưu vào `HttpServletRequest` attribute, phát một CSP header và truyền cùng giá trị qua Model/Thymeleaf. Trong **Reactive/WebFlux**, dùng `WebFilter` và `ServerWebExchange` attributes rồi render template theo cùng nguyên tắc. **Không tạo nonce tĩnh khi build SecurityFilterChain, không sinh độc lập ở header và template, không cache HTML/fragment chứa nonce cũ rồi gắn header mới**.

Chẩn đoán theo thứ tự: **HTML document response → toàn bộ CSP enforce/report-only policies → effectiveDirective → same-response nonce/header/body → source/caching/proxy → browser behavior → API CORS/CSRF/auth nếu request thật được gửi**. Dùng MockMvc/WebTestClient để kiểm chứng nonce và configuration trong app, kết hợp Playwright/DevTools để chứng minh browser thực thi đúng và proxy/CDN không sửa policy.

Trong `SPRING_SECURITY_HTTP_PROTECTION`, mục tiêu là **khôi phục chức năng hợp lệ mà không nới lỏng phòng vệ không cần thiết**: giữ CSRF, CORS, HTTPS/HSTS, security headers, HTTP firewall, cookie/session và authentication/authorization. Một CSP fix tốt phải đồng thời cho script/truy cập hợp lệ hoạt động và **tiếp tục chặn script không được nonce/hash hoặc nguồn không tin cậy**.
