# Phối hợp CSP giữa ứng dụng, proxy và cache

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Bài toán: CSP ở Spring Security đúng nhưng trình duyệt vẫn báo lỗi

Nhóm phát triển có ứng dụng Spring Boot render HTML bằng Thymeleaf. Ở môi trường local, một script nội tuyến tin cậy chạy được nhờ CSP nonce; API và CSS cũng hoạt động. Khi triển khai production qua reverse proxy và CDN:

- Trình duyệt chặn script dù nonce trong HTML có vẻ đúng.
- Một số người dùng thấy lỗi, số khác không.
- Khi tải lại, lỗi biến mất hoặc đổi sang lỗi khác.
- Kiểm thử trực tiếp vào Spring Boot cho kết quả đúng nhưng kiểm thử bằng hostname công khai lại sai.

Nguyên nhân có thể nằm **ngoài controller hoặc SecurityFilterChain**: proxy thêm một CSP khác, CDN trả HTML đã cache với nonce cũ, một tầng chỉ thay header mà không thay body, hoặc endpoint HTML thực sự được phục vụ từ nơi khác.

Ví dụ một đường đi HTTP:

~~~mermaid
flowchart LR
    B[Browser] --> C[CDN / Edge cache]
    C --> P[Reverse proxy / API gateway]
    P --> S[Spring Security]
    S --> V[Controller + HTML template]
    V --> S
    S --> P
    P --> C
    C --> B
~~~

**CSP mà browser thực thi là chính sách nhận được cùng tài liệu cuối cùng**, không phải chỉ giá trị `policyDirectives(...)` trong mã Spring. Vì thế cấu hình ứng dụng, proxy và cache phải được xem như một hệ thống.

Mục tiêu của bài học:

1. Xác định **tầng nào chịu trách nhiệm CSP** cho từng response HTML.
2. Giải thích điều gì xảy ra khi nhiều CSP thực thi cùng được gửi.
3. Phân biệt hành vi thêm, ghi đè, bỏ hoặc hợp nhất header tại proxy/CDN.
4. Thiết kế cache cho HTML tĩnh, HTML cá nhân hóa và HTML có nonce/hash.
5. Cấu hình Spring Security Servlet và Reactive/WebFlux trong kiến trúc nhiều tầng.
6. Kiểm thử từ origin đến endpoint công khai, có cả error page, redirect, 304 và rollout.

## 2. Đường đi của tài liệu quan trọng hơn chỗ đặt cấu hình

CSP chủ yếu được browser áp dụng trong **ngữ cảnh tài liệu** đang hiển thị. Hãy phân biệt các response:

| Response | Ai phục vụ? | Điều cần xác minh |
|---|---|---|
| `GET /dashboard` trả HTML | Spring MVC phía sau proxy | HTML cuối cùng có CSP đúng; nếu có nonce, header khớp template |
| `GET /app/index.html` trả HTML SPA | CDN/static frontend | Chính CDN hoặc máy chủ HTML phải trả CSP |
| `GET /api/orders` trả JSON | Spring Boot API | CSP trên JSON không tự áp chính sách đó lên HTML SPA ở origin khác |
| `GET /js/app.js` trả file script | Static server/CDN | Việc cho tải script chủ yếu do CSP của tài liệu chứa script quyết định |
| `GET /login` trả HTML từ một security chain khác | Spring Security hoặc frontend khác | Kiểm tra CSP ngay trên trang đăng nhập đó |
| `GET /missing-page` trả HTML 404 | App, proxy hoặc CDN | Error page cũng có thể cần CSP, nhưng không chắc đi qua cùng chain |

Ví dụ frontend được cung cấp tại `https://app.example.com` từ CDN, còn API ở `https://api.example.net` do Spring WebFlux phục vụ. Nếu chỉ cấu hình `http.headers().contentSecurityPolicy(...)` ở WebFlux API, frontend **không tự nhận CSP** ấy. Cần phát policy trên response `index.html`/HTML tại nơi CDN cung cấp trang.

Một số ngữ cảnh có chính sách riêng, chẳng hạn worker. Khi phân tích chúng, phải xét đặc thù response và ngữ cảnh của worker; không được mặc định CSP trên một JSON API hoặc tệp script bất kỳ sẽ áp trực tiếp cho tài liệu HTML khác.

### Xác định tài liệu cuối cùng sau redirect

Luồng phổ biến:

~~~text
GET https://app.example.com/dashboard
  → 302 Location: /login
GET https://app.example.com/login
  → 200 text/html
~~~

Nếu mục tiêu là bảo vệ trang login, hãy kiểm tra **response 200 HTML của `/login`**, không chỉ CSP ở response 302 của `/dashboard`. Redirect và tài liệu đích là hai response khác nhau. Tương tự, trang lỗi do proxy/CDN tự dựng không mặc nhiên có header giống HTML do Spring tạo.

## 3. Chọn một chủ sở hữu CSP cho từng nhóm HTML

Không có một lựa chọn duy nhất cho mọi hệ thống; điều quan trọng là **trách nhiệm được định nghĩa rõ**:

| Mô hình triển khai | Chủ thể phát CSP hợp lý | Điều cần đồng bộ |
|---|---|---|
| Spring MVC render Thymeleaf động | Spring Security / tầng render HTML | Controller, filter, nonce/header/template và cache |
| Spring WebFlux render HTML động | Spring Security / tầng render HTML | WebFilter, ServerWebExchange, policy và cache |
| SPA tĩnh do CDN phát | Static server/CDN/edge | HTML version, CSP version, asset origins và cache |
| Proxy quản lý header cho nhiều ứng dụng | Reverse proxy/gateway theo từng route | Không để app/proxy tạo policy mâu thuẫn; kiểm soát thay đổi |
| HTML động từ app qua proxy chỉ chuyển tiếp | Ứng dụng | Proxy không tùy tiện thêm/ghi đè CSP động |
| HTML do edge biến đổi cho mỗi response | Edge được kiểm soát | Biến đổi **đồng bộ cả header và body**, cache/ETag/compression |

Một quy tắc vận hành hữu ích:

> **Mỗi nhóm tài liệu HTML nên có một nguồn chịu trách nhiệm chính về CSP thực thi, một quy trình review và một bộ test response cuối cùng.**

“Một nguồn chịu trách nhiệm” không có nghĩa cấm tuyệt đối nhiều policy: có thể chủ đích áp một baseline chặt ở proxy và policy bổ sung tại ứng dụng. Nhưng đội phát triển phải biết các policy **giao nhau thế nào**, version nào đang chạy và tầng nào chịu trách nhiệm khi một tính năng bị chặn.

### Bộ câu hỏi thiết kế

1. Ai trả response HTML mà browser thực sự render?
2. Có proxy hoặc CDN nào thêm, xóa hoặc cache header hay không?
3. Policy là tĩnh hay có giá trị riêng mỗi response, như CSP nonce?
4. HTML có được cache công khai, cache riêng người dùng, hoặc biến đổi ở edge không?
5. Có nhiều route, security chain, site, tenant hoặc môi trường triển khai không?
6. Khi điều chỉnh CSP, bộ phận nào có thể kiểm tra và rollback toàn bộ các tầng liên quan?

Nếu chưa trả lời được những câu hỏi này, không nên kết luận cấu hình đã đúng chỉ từ việc grep thấy `Content-Security-Policy` trong repository.

## 4. Nhiều CSP thực thi không phải “header sau ghi đè header trước”

Giả sử ứng dụng xuất:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self' https://static.example.net; object-src 'none'
~~~

nhưng proxy xuất thêm:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; object-src 'none'
~~~

Nếu browser nhận **cả hai CSP thực thi**, nó áp dụng cả hai. Script từ `https://static.example.net` có thể bị policy thứ hai từ chối dù policy thứ nhất cho phép.

| Hành vi | Policy ứng dụng | Policy proxy | Kết quả kết hợp |
|---|---|---|---|
| Tải `/js/app.js` cùng origin | Cho phép | Cho phép | Được phép theo CSP |
| Tải `https://static.example.net/app.js` | Cho phép | Không cho | Bị chặn |
| Tải `https://unknown.example/script.js` | Không cho | Không cho | Bị chặn |

**Không thể nới quyền đã bị một policy thực thi khác chặn bằng cách thêm nguồn vào policy riêng của bạn.** Về nguyên tắc, tài nguyên/hành vi phải thỏa **tất cả** CSP thực thi có liên quan.

### Một ví dụ nonce bị policy khác vô hiệu

Ứng dụng trả:

~~~http
Content-Security-Policy: script-src 'self' 'nonce-REQUEST_NONCE'
~~~

HTML:

~~~html
<script nonce="REQUEST_NONCE">
  initializeDashboard();
</script>
~~~

Nếu proxy còn thêm:

~~~http
Content-Security-Policy: script-src 'self'
~~~

thì script inline có thể bị chặn bởi policy proxy. Việc nonce khớp giữa **header của ứng dụng và HTML** chưa đủ khi còn một policy thực thi khác không cấp phép inline.

### CSP thực thi và Report-Only là hai loại khác nhau

~~~http
Content-Security-Policy: script-src 'self' 'unsafe-inline'
Content-Security-Policy-Report-Only: script-src 'self'
~~~

Trong trường hợp này, script inline có thể chạy theo CSP thực thi, đồng thời tạo tín hiệu vi phạm candidate Report-Only (nếu browser hỗ trợ). Report-Only **không chặn chỉ vì bản thân nó**. Khi debug, phải ghi lại **tên header**, nội dung policy và disposition của violation, không gọi chung là “có CSP”.

Một proxy có thể vô tình thay tên header hoặc chuyển candidate Report-Only thành CSP thực thi trước thời điểm rollout. Vì thế bản ghi kiểm thử phải phân biệt rành mạch hai header.

## 5. Thêm, ghi đè và loại bỏ header tại các tầng HTTP

Các thao tác ở proxy/gateway có thể khác nhau:

| Thao tác | Hành vi thường thấy | Rủi ro |
|---|---|---|
| **Forward** CSP upstream | Truyền CSP từ Spring đến browser | Thường phù hợp khi Spring làm chủ policy |
| **Append/Add** một CSP nữa | Browser nhận thêm policy | Policy giao nhau, có thể làm script/ảnh/API bị chặn bất ngờ |
| **Set/Replace** CSP | Header hiện có tại tầng đó bị thay theo cơ chế server | Mất nonce, hash hoặc directive của ứng dụng |
| **Hide/Remove** CSP từ upstream | Browser không nhận policy upstream | Nếu không thay bằng policy khác thì mất lớp bảo vệ |
| **Rewrite** HTML nhưng giữ CSP | Body có thể khác nội dung đã hash/nonce | Script/style inline hợp lệ bị chặn |
| **Cache** header và body | Bản cũ có thể được phát lại | CSP version lệch, nonce bị tái sử dụng |

Không phải mọi hệ thống gọi thao tác theo cùng một tên. Ví dụ cấu hình “set response header” trong gateway có thể **thay giá trị của header tại gateway**, còn chức năng “add header” có thể **tạo thêm một trường CSP**; một tầng sau nữa lại có thể xử lý khác. Cần xem **response cuối cùng trên đường public** để xác nhận, thay vì suy luận từ tên nút cấu hình.

### Header trùng lặp và hợp nhất

Một số proxy hoặc thư viện HTTP có thể đưa nhiều trường header vào một cấu trúc dữ liệu hay thay đổi cách hiển thị chúng. Không giả định việc ghép nhiều CSP bằng dấu phẩy hoặc chỉ lấy phần tử đầu tiên luôn tương đương với xử lý nhiều policy thực thi. Để tránh mơ hồ:

- Lập danh sách mọi tầng viết CSP.
- Thống nhất cơ chế phát và loại bỏ header cũ khi chủ đích chuyển quyền sở hữu.
- Dùng công cụ HTTP và DevTools để quan sát **toàn bộ** giá trị thực nhận.
- Viết bài test đánh giá kết quả hành vi trong browser, không chỉ kiểm tra một chuỗi.

## 6. Reverse proxy: hai phương án cấu hình có chủ đích

Ví dụ dưới đây dùng cú pháp Nginx để minh họa nguyên tắc. Đây không phải file cấu hình production hoàn chỉnh: còn TLS, routing, timeouts, logging, cache, headers khác và quy tắc kế thừa của từng `server`/`location`.

### Phương án A — Spring làm chủ CSP, proxy chuyển tiếp

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    # Cấu hình chứng chỉ TLS và các header khác được quản lý riêng.

    location / {
        proxy_pass http://spring_html_upstream;
        proxy_set_header Host $host;

        # Không thêm CSP thứ hai tại đây.
        # Cho upstream quyết định CSP của HTML động.
    }
}
~~~

Trong mô hình này:

1. Spring render HTML và phát CSP.
2. Proxy thông thường chuyển header đó tới browser.
3. Proxy **không thêm** chính sách CSP thực thi khác ngoài ý muốn.
4. Nếu proxy tự tạo trang lỗi hoặc phục vụ file HTML khác, **phải xác định CSP riêng** cho các response không đi qua Spring.

Đây thường là phương án dễ hiểu khi CSP có **nonce động** được tạo trong cùng luồng render template.

### Phương án B — Proxy làm chủ CSP tĩnh

Nếu trang dùng JS/CSS ở file ngoài và CSP không cần giá trị theo response, gateway có thể làm chủ policy cho nhóm HTML được xác định. Ví dụ:

~~~nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    location / {
        proxy_pass http://spring_html_upstream;
        proxy_set_header Host $host;

        # Chỉ dùng khi đã quyết định chuyển quyền sở hữu CSP về proxy.
        proxy_hide_header Content-Security-Policy;
        proxy_hide_header Content-Security-Policy-Report-Only;

        add_header Content-Security-Policy
          "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self' https://api.example.net; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
          always;
    }
}
~~~

Ở ví dụ này, `proxy_hide_header` chỉ nhắm tới header upstream trong response được proxy xử lý; nó không phải phép xóa “mọi CSP ở mọi tầng”. `add_header ... always` yêu cầu Nginx thêm header với những status code thường không được thêm bởi `add_header` mặc định; tuy nhiên quy tắc kế thừa `add_header` giữa `http`, `server` và `location` có thể ảnh hưởng đến những header khác.

**Điều kiện quan trọng:** không dùng cấu hình tĩnh ở proxy để ghi đè một CSP chứa nonce per-response mà không thiết kế lại luồng tạo nonce. Nếu Spring đang tạo nonce và gắn nó vào HTML, việc proxy thay chính sách bằng `script-src 'self'` có thể làm script inline bị chặn.

### Kế thừa add_header và trang lỗi

Trong Nginx, khi một cấp cấu hình có `add_header` riêng, danh sách header được kế thừa từ cấp trước có những quy tắc không trực giác và còn phụ thuộc phiên bản/tính năng. Có thể vô tình làm mất các header bảo vệ khác, không chỉ CSP.

Vì vậy khi sửa CSP cần kiểm tra **toàn bộ security headers**, ví dụ HSTS, `X-Content-Type-Options` và những header thực sự dùng trong hệ thống. Không xóa một header để sửa CSP rồi vô tình tắt HSTS hay các phòng vệ khác.

Trang lỗi do proxy tạo, internal redirect qua `error_page` và location phục vụ file tĩnh có thể sử dụng cấu hình header khác với `location /`. Hãy kiểm tra trực tiếp các route lỗi và HTML tĩnh; **không suy luận** rằng `always` ở một location chắc chắn bao phủ mọi response của site.

## 7. Spring Security Servlet: cấu hình CSP cho HTML do ứng dụng render

Ví dụ ứng dụng MVC không cần inline JavaScript/CSS, sử dụng policy tĩnh do Spring làm chủ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HtmlSecurityConfig {

    private static final String CSP_POLICY =
        "default-src 'none'; " +
        "script-src 'self'; " +
        "style-src 'self'; " +
        "img-src 'self' https://images.example.net; " +
        "font-src 'self'; " +
        "connect-src 'self' https://api.example.net; " +
        "object-src 'none'; " +
        "base-uri 'none'; " +
        "form-action 'self'; " +
        "frame-ancestors 'none'";

    @Bean
    SecurityFilterChain htmlSecurityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(CSP_POLICY)
            )
        );

        // Authentication, authorization, CSRF, CORS và session
        // được cấu hình theo yêu cầu ứng dụng, không thay bằng CSP.
        return http.build();
    }
}
~~~

Trong cách này, `ContentSecurityPolicyHeaderWriter` được Spring Security dùng qua DSL để ghi policy do ứng dụng cung cấp. **Spring Security không tự biết** proxy/CDN có đang ghi thêm CSP hay không và không tự phân tích nội dung HTML để suy ra directive.

Nếu dự án có nhiều `SecurityFilterChain`, route HTML có thể bị xử lý bởi chain khác. Kiểm tra cụ thể `/`, `/login`, `/dashboard`, các trang SSR và đường lỗi thay vì chỉ kiểm tra một endpoint API JSON.

### Tránh đăng ký hai nguồn viết cùng một policy

Nếu đã dùng DSL:

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(CSP_POLICY)
    )
);
~~~

thì không cần thêm một `ContentSecurityPolicyHeaderWriter` khác để viết lại policy ấy, trừ khi bạn có thiết kế cụ thể. Trong cùng response, writer hoặc filter có thể thay/ghép header theo cách khác nhau; một proxy ở ngoài còn có thể thêm CSP khác. **Kiểm chứng response cuối cùng** là tiêu chuẩn quyết định.

## 8. Spring Security Reactive/WebFlux: cùng trách nhiệm, API khác

Ví dụ ứng dụng WebFlux render HTML, dùng policy tĩnh tương đương:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveHtmlSecurityConfig {

    @Bean
    SecurityWebFilterChain htmlSecurityWebFilterChain(ServerHttpSecurity http) {
        String policy =
            "default-src 'none'; " +
            "script-src 'self'; " +
            "style-src 'self'; " +
            "img-src 'self' https://images.example.net; " +
            "font-src 'self'; " +
            "connect-src 'self' https://api.example.net; " +
            "object-src 'none'; " +
            "base-uri 'none'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";

        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(policy)
            )
        );
        return http.build();
    }
}
~~~

Khác biệt giữa Servlet và Reactive nằm ở API server: `HttpSecurity`/`SecurityFilterChain` so với `ServerHttpSecurity`/`SecurityWebFilterChain`. **Trình duyệt đánh giá CSP trên response HTML theo cùng một nguyên tắc**, bất kể stack đã tạo response đó.

Nếu WebFlux chỉ phục vụ API còn CDN phục vụ SPA, CSP phải được đưa vào response HTML ở CDN. Đừng cố sửa lỗi CSP của frontend bằng cách đặt header trên response `text/event-stream` hoặc JSON, bởi chúng không tự thay CSP của document đang mở.

## 9. Cache HTML: phân loại trước khi quyết định policy

Một chiến lược cache tốt phụ thuộc HTML có **cố định**, **cá nhân hóa** hoặc **chứa nonce biến thiên** hay không.

| Loại tài nguyên/HTML | Cách cache thường phù hợp | Lý do bảo mật |
|---|---|---|
| JS/CSS/ảnh tĩnh có tên file gắn version/hash | Có thể dùng cache công khai, TTL dài | Không chứa nonce CSP của document |
| HTML tĩnh, giống nhau cho mọi người, chỉ dùng JS/CSS ngoài | Có thể cache có kiểm soát | CSP header và HTML ổn định theo cùng release |
| HTML tĩnh có inline block cố định và CSP hash | Có thể cache nếu header/body cùng version | Hash khớp nội dung inline không đổi |
| HTML SSR cá nhân hóa | Thường cần cache riêng hoặc không lưu | Tránh lộ nội dung người dùng giữa các request |
| HTML chứa nonce riêng từng response | Tránh phục vụ bản HTML đã cache công khai một cách nguyên vẹn | Không được tái sử dụng nonce hoặc làm lệch header/body |
| API JSON có token/dữ liệu nhạy cảm | Theo quy tắc cache riêng của API | Không dùng CSP để giải quyết rò rỉ cache |

Một ví dụ cache cho file tài nguyên tĩnh đã fingerprint:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

Ví dụ ấy phù hợp khi file URL thay đổi mỗi khi nội dung file đổi. Không áp TTL một năm cho một file không version mà ứng dụng có thể sửa trực tiếp.

Với HTML động và nhạy cảm:

~~~http
Cache-Control: no-store
~~~

có thể là lựa chọn phù hợp nếu ứng dụng không muốn các cache lưu response. Cần xác định yêu cầu thực tế; không nhất thiết áp `no-store` cho mọi tệp JS/CSS/ảnh rồi làm mất lợi ích cache.

### Cache-Control không thay CSP

`Cache-Control` điều khiển việc lưu và tái sử dụng response; `Content-Security-Policy` điều khiển những hành vi browser được phép khi hiển thị tài liệu. Cả hai cần đúng **đồng thời**, nhưng thay đổi `Cache-Control` không tự sửa source list, nonce hay một policy chồng chéo.

## 10. CSP nonce động và CDN cache: xung đột dễ gây lỗi nhất

Một nonce CSP nên có giá trị ngẫu nhiên khó đoán, được sinh mới **cho mỗi response HTML cần nonce**. Hai response độc lập có thể minh họa:

~~~http
HTTP/1.1 200 OK
Content-Security-Policy: script-src 'self' 'nonce-AAA_RANDOM'
Cache-Control: no-store
~~~

~~~html
<script nonce="AAA_RANDOM">
  initializeDashboard();
</script>
~~~

Request HTML khác:

~~~http
HTTP/1.1 200 OK
Content-Security-Policy: script-src 'self' 'nonce-BBB_RANDOM'
Cache-Control: no-store
~~~

~~~html
<script nonce="BBB_RANDOM">
  initializeDashboard();
</script>
~~~

`AAA_RANDOM` và `BBB_RANDOM` chỉ là ký hiệu minh họa, **không phải nonce đủ an toàn**. Triển khai thật cần ngẫu nhiên mật mã học, ví dụ `SecureRandom`; header và những thẻ `<script>`/`<style>` đáng tin phải dùng cùng nonce của response tương ứng.

### Cache hit phát lại cả header và HTML

Giả sử CDN lưu response đầu tiên và phát nguyên bản cho người dùng tiếp theo:

~~~text
Cache entry:
  CSP header: script-src 'nonce-AAA_RANDOM'
  HTML body:  <script nonce="AAA_RANDOM">...</script>

Client B nhận từ cache:
  CSP header: script-src 'nonce-AAA_RANDOM'
  HTML body:  <script nonce="AAA_RANDOM">...</script>
~~~

Script có thể vẫn chạy, vì header và HTML khớp nhau, nhưng nonce **đã bị tái sử dụng giữa các response được phục vụ**. Điều đó làm suy yếu mục tiêu chỉ cho phép những script được đánh dấu bằng nonce mới của tài liệu; không được xem “giao diện vẫn chạy” là bằng chứng cách cache đúng.

### Cache hit chỉ thay header

Một lỗi khác:

~~~text
CDN trả HTML cũ:    <script nonce="AAA_RANDOM">...</script>
Proxy ghi CSP mới: script-src 'nonce-BBB_RANDOM'
~~~

Browser từ chối khối script vì nonce trong policy **không khớp** thuộc tính nonce của phần tử. Đây là lỗi thường bị hiểu nhầm thành “Spring Security sinh nonce sai”, dù ứng dụng đã sinh đúng trước khi HTML bị cache hoặc bị proxy chỉnh sửa.

### Cách thiết kế an toàn hơn

- Với HTML SSR có nonce và dữ liệu người dùng, cân nhắc **không cache HTML** ở shared CDN, ví dụ trả `Cache-Control: no-store` khi phù hợp.
- Cache **asset tĩnh** riêng biệt; JS/CSS fingerprinted có thể giữ TTL dài.
- Nếu HTML thực sự ổn định, cân nhắc bỏ inline code bằng cách chuyển JS/CSS ra file hoặc dùng **CSP hash** cho khối inline bất biến.
- Nếu bắt buộc cache HTML và tạo nonce tại edge, edge phải có cơ chế **thay nonce trong cả header và toàn bộ HTML liên quan một cách đồng bộ cho mỗi response**, kể cả fragment, template, compression và conditional requests. Đây là thiết kế nâng cao, cần review và kiểm thử kỹ, không phải chỉ một phép replace chuỗi.
- Không tạo nonce cố định theo session/user hoặc dùng timestamp dễ đoán để “làm việc với cache”.

**`Vary: Cookie` không tự giải quyết bài toán nonce.** Nó có thể phân chia cache theo cookie ở những cache tuân thủ, nhưng không bảo đảm nonce được làm mới cho mỗi response và không thay thế kiểm soát cache HTML cá nhân hóa.

## 11. HTML tĩnh và CSP hash: thuận lợi hơn cho cache

Nếu một trang HTML có đoạn inline cố định:

~~~html
<script>window.appReady = true;</script>
~~~

ứng dụng có thể tính SHA-256 digest Base64 của **chính nội dung** `window.appReady = true;` rồi khai báo:

~~~http
Content-Security-Policy: script-src 'self' 'sha256-ACTUAL_DIGEST_BASE64'
~~~

`ACTUAL_DIGEST_BASE64` chỉ là placeholder; cần thay bằng hash thật. Với HTML không đổi, policy hash có thể giữ nguyên giữa các response và phù hợp hơn với cơ chế cache công khai.

Tuy nhiên, nếu CDN hoặc proxy **minify HTML**, thay whitespace trong inline script, đưa thêm biến động vào khối script hoặc chuyển đổi nội dung, digest có thể không còn khớp. Hash cần được tính từ **nội dung cuối cùng browser phân tích**.

| Phương án | Đặc điểm cache | Điều kiện an toàn |
|---|---|---|
| JavaScript ngoài cùng origin | Rất thuận lợi | Kiểm soát đường phục vụ file và `script-src` |
| Hash cho inline script cố định | Thuận lợi khi HTML/version cố định | Hash khớp chính xác inline code sau mọi biến đổi |
| Nonce ngẫu nhiên mỗi response | Cần tránh phát lại HTML nguyên bản từ cache chung | Nonce mới, header/body khớp từng response |
| `'unsafe-inline'` để khỏi cần nonce/hash | Dễ làm giao diện chạy nhưng CSP yếu hơn | Không nên dùng làm cách sửa cache |

Nếu HTML tĩnh đã cache lâu cùng CSP cũ, khi deploy inline code mới phải thay **policy và HTML cùng một version**, đồng thời xử lý invalidation/caching. Chỉ purge HTML nhưng không purge header được cache ở một tầng khác cũng có thể tạo mismatch.

## 12. ETag, 304 Not Modified và việc thay đổi CSP

Cache HTTP còn có các yêu cầu có điều kiện:

~~~http
GET /dashboard HTTP/1.1
If-None-Match: "html-v42"
~~~

Nếu server thấy bản đã lưu vẫn hợp lệ, nó có thể trả:

~~~http
HTTP/1.1 304 Not Modified
ETag: "html-v42"
~~~

Response 304 không mang HTML body đầy đủ như 200. Browser/cache dùng bản đã lưu và cập nhật metadata theo quy tắc HTTP caching. Vì thế, khi CSP thay đổi, không thể chỉ xem một response 304 riêng lẻ rồi kết luận chính sách nào đang được áp cho nội dung mà browser dùng.

### Những lỗi cần tránh

1. **ETag giữ nguyên dù inline content đã đổi:** cache có thể tin rằng HTML chưa thay đổi.
2. **Header CSP mới nhưng body cache cũ:** policy và nội dung inline không tương thích.
3. **Nonce thay trong header khi tái sử dụng body:** các phần tử inline có nonce cũ bị chặn.
4. **CSP chỉ được thêm trên response 200 mà không kiểm tra 304:** hành vi metadata cache có thể không như mong đợi.
5. **Các tầng cache có TTL khác nhau:** CDN phục vụ HTML cũ trong khi proxy/app đã trả policy mới.

Hướng kiểm tra:

- Thử cả **request đầu tiên**, **refresh**, **conditional request** và **cache hit**.
- Đọc CSP trong response mạng và xác định HTML body nào browser thực sự hiển thị.
- Với HTML động chứa nonce, ưu tiên chính sách tránh tái sử dụng response thay vì tự ghép nonce mới với bản 304/body cache cũ.
- Khi dùng hash và HTML tĩnh, version/invalidation phải đồng bộ với nội dung build.

**Không có một quy tắc đơn giản rằng “304 luôn có/không có CSP mới”.** Response có thể mang metadata header và cache áp dụng quy tắc cập nhật riêng. Cần quan sát đường request thực tế và bộ cache đang dùng.

## 13. Biến đổi HTML ở proxy/CDN có thể làm thay đổi CSP

Một số tầng edge tối ưu hóa HTML bằng cách:

- Loại whitespace, newline hoặc comment.
- Chèn script analytics, performance monitoring, banner cookie, A/B testing.
- Thay URL tài nguyên từ origin sang CDN.
- Áp compression/minification hoặc render các fragment tại edge.
- Thêm các thuộc tính hoặc khối script/style phục vụ một tính năng ngoài mã Spring.

Các thay đổi này có thể ảnh hưởng:

| Edge làm gì? | CSP có thể bị ảnh hưởng thế nào? |
|---|---|
| Chèn inline script | Script mới thiếu nonce/hash trong policy |
| Thay nội dung inline script | Hash không còn khớp |
| Chỉ thay `nonce` trên thẻ script | Header chứa nonce khác |
| Chỉ thay nonce trong header | HTML còn nonce cũ |
| Thay URL JS/CSS/ảnh/API | Source list không còn cho phép đúng origin |
| Chèn iframe hoặc beacon | Cần đánh giá `frame-src`/`connect-src`/`img-src` |
| Gộp nhiều fragment HTML | Fragment có thể mang nonce/policy không cùng response |

**Giải pháp:** xác định ai kiểm soát việc biến đổi HTML. Nếu edge thêm script, phải đưa nó vào quy trình review CSP và deployment, không chỉ tự động nới `'unsafe-inline'`. Với policy hash, có thể tính hash từ artifact HTML cuối cùng. Với nonce, cần một cơ chế tạo và truyền nonce thống nhất đến mọi phần tử cần cấp phép.

### HTML compression và chuyển đổi

Compression như gzip/brotli không tự làm thay đổi nội dung logic mà browser phân tích sau giải nén. Nhưng **minification/rewriting** có thể thay đổi nội dung script/style inline. Khi debug, cần phân biệt chuyển đổi mã hóa truyền tải với biến đổi HTML thực chất, và kiểm tra body sau khi trình duyệt giải nén/diễn giải.

### Thêm script giám sát ở edge

Nếu một CDN tự chèn JavaScript RUM, tracker hoặc banner consent, cách dễ nhất về mặt kỹ thuật có thể là mở `'unsafe-inline'`. Nhưng điều này mở quyền cho nhiều mã inline không được kiểm soát. Lựa chọn tốt hơn là dùng file script từ nguồn đã review, CSP nonce/hash nếu hợp lý và kiểm tra rủi ro supply chain/quyền riêng tư của script đó.

## 14. Phối hợp nonce giữa Spring và template khi có proxy

Trong Spring MVC, có thể sinh nonce ở tầng request trước khi template render. Đây là ví dụ **minh họa** nếu ứng dụng chủ động phát CSP, proxy chỉ chuyển tiếp và không cache HTML:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public final class CspNonce {
    public static final String REQUEST_ATTRIBUTE = "cspNonce";
    private static final SecureRandom RANDOM = new SecureRandom();

    private CspNonce() {}

    public static String create() {
        byte[] bytes = new byte[24];
        RANDOM.nextBytes(bytes);
        return Base64.getEncoder().withoutPadding().encodeToString(bytes);
    }
}
~~~

Ví dụ filter:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;

public final class HtmlCspNonceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {
        String nonce = CspNonce.create();
        request.setAttribute(CspNonce.REQUEST_ATTRIBUTE, nonce);

        response.setHeader(
            "Content-Security-Policy",
            "default-src 'none'; " +
            "script-src 'self' 'nonce-" + nonce + "'; " +
            "style-src 'self'; object-src 'none'; " +
            "base-uri 'none'; form-action 'self'"
        );
        response.setHeader("Cache-Control", "no-store");
        chain.doFilter(request, response);
    }
}
~~~

Controller lấy **đúng nonce đã được filter tạo**:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class DashboardController {

    @GetMapping("/dashboard")
    String dashboard(HttpServletRequest request, Model model) {
        String nonce = (String) request.getAttribute(
            CspNonce.REQUEST_ATTRIBUTE
        );
        if (nonce == null) {
            throw new IllegalStateException("CSP nonce not initialized");
        }
        model.addAttribute("cspNonce", nonce);
        return "dashboard";
    }
}
~~~

Trong Thymeleaf:

~~~html
<script th:attr="nonce=${cspNonce}">
  initializeDashboard();
</script>
~~~

**Điều kiện vận hành của ví dụ:**

- Filter phải được đăng ký **một lần** và chạy trước khi controller render, trên đúng chain/route HTML. Không đăng ký hai nơi làm nonce được tạo lại.
- Nếu CSP được tạo trong filter, không đồng thời cấu hình một CSP tĩnh không tương thích trên cùng response.
- Với nhiều route (login/error/async), phải kiểm tra filter dispatch và điểm commit header.
- Ví dụ filter áp header lên mọi response nó đi qua; trong ứng dụng thật cần giới hạn đúng route HTML hoặc thiết kế chain có phạm vi rõ ràng.
- Proxy không thêm policy chặt hơn làm vô hiệu nonce và **không cache chung** HTML chứa nonce.
- Các directive như `img-src`, `connect-src`, `font-src` cần mở đúng nhu cầu của sản phẩm; ví dụ tập trung vào quan hệ giữa nonce/header/template.

Đây là **một phương án** để thực thi một nonce theo response trong Servlet. Có thể dùng header writer động hoặc kiến trúc khác nếu có test chứng minh kết quả tương đương, nhưng không được tự tính nonce hai lần ở header và template.

### Áp dụng nguyên tắc trên WebFlux

Trong Reactive/WebFlux, thay `OncePerRequestFilter` và `HttpServletRequest` bằng `WebFilter` và `ServerWebExchange`. Lưu nonce ở `exchange.getAttributes()`, truyền vào model render, ghi CSP header trước khi response được commit và kiểm tra không có policy thứ hai từ proxy. Tránh giữ nonce trong field singleton hoặc `ThreadLocal`, vì reactive pipeline không bảo đảm gắn với một thread cố định.

## 15. Trust boundary: scheme/host phía browser khác địa chỉ nội bộ

Ứng dụng Spring có thể chạy trên:

~~~text
http://spring-service:8080
~~~

nhưng trình duyệt truy cập:

~~~text
https://app.example.com
~~~

Proxy kết thúc TLS và chuyển request vào mạng nội bộ. Đối với CSP, `'self'` được browser đánh giá theo **origin của tài liệu công khai**, không phải địa chỉ nội bộ `spring-service:8080` của container.

Điều này có hai hệ quả:

1. Đừng thêm `http://spring-service:8080` vào CSP của frontend chỉ vì đó là upstream mà proxy dùng; browser thường không thể hoặc không nên kết nối trực tiếp tới địa chỉ nội bộ ấy.
2. Nếu ứng dụng **tạo động absolute URL hoặc source expression** từ `Host`, `Forwarded` hay `X-Forwarded-*`, phải cấu hình trust proxy chính xác để tránh dùng header không đáng tin làm nguồn cấu hình CSP.

Ví dụ sai về ý tưởng:

~~~java
// KHÔNG nên dùng host do client có thể kiểm soát trực tiếp
// để tạo source expression CSP mà không có trust boundary rõ ràng.
String dynamicPolicy = "connect-src https://" + request.getHeader("Host");
~~~

Thay vào đó, nên dùng origin công khai được cấu hình và kiểm duyệt theo environment, hoặc lấy thông tin forwarded từ **proxy được tin cậy** theo cấu hình Spring/infra phù hợp. Đặc biệt, wildcard subdomain và hostname do tenant cung cấp phải được review trước khi đưa vào allowlist.

### CORS, HSTS và CSP không cùng một vai trò

| Cơ chế | Bảo vệ chính | Liên quan đến kiến trúc proxy thế nào? |
|---|---|---|
| CSP | Giới hạn nguồn và kiểu hành vi trong browser | Đặt đúng trên HTML cuối cùng |
| CORS | Kiểm soát khả năng JS đọc response cross-origin theo cơ chế browser | API và preflight cần xử lý đúng origin thực |
| HSTS | Yêu cầu browser dùng HTTPS cho host phù hợp | Thường cấu hình tại edge/TLS endpoint hoặc ứng dụng có nhận thức proxy đúng |
| CSRF | Ngăn yêu cầu thay đổi trạng thái không hợp lệ | Server phải kiểm tra token/ngữ cảnh, không dựa vào CSP |
| Cookie `Secure`/`SameSite` | Kiểm soát truyền cookie/phiên | Scheme công khai và reverse proxy có thể ảnh hưởng cấu hình |
| HTTP firewall | Chuẩn hóa/giới hạn các request HTTP vào ứng dụng | Proxy và Spring Security có thể áp các kiểm tra bổ sung |

Không tắt HSTS, CORS, CSRF hay HTTP firewall chỉ để một policy CSP chạy được. Khi sửa lỗi ở proxy, cần bảo toàn các biện pháp bảo vệ HTTP khác.

## 16. Bảng kiểm các response cần có trong phép thử

Không đủ nếu chỉ gọi `GET /` một lần. Nên thử các nhóm sau:

| Ca kiểm thử | Điều cần quan sát |
|---|---|
| Trang HTML công khai | CSP enforcement và Report-Only đúng kế hoạch |
| Trang đăng nhập | Có CSP tương thích với script/form login |
| Trang cá nhân hóa | Không trả HTML/cookie nhạy cảm từ cache chung; nonce mới nếu dùng |
| Trang SPA từ CDN | CSP do nơi phát HTML cung cấp |
| Response 302 dẫn tới HTML | Kiểm tra tài liệu đích sau redirect |
| Trang 404/500 do Spring trả | Có CSP và các header bảo vệ phù hợp |
| Trang lỗi do proxy/CDN dựng | Không giả định kế thừa CSP upstream |
| Response 304 sau conditional GET | HTML cache và metadata CSP tương thích |
| Cache hit CDN | Header/body đúng version; không tái dùng nonce trái thiết kế |
| Cache miss CDN | Policy vẫn đồng nhất với đường đi qua origin |
| File JS/CSS/ảnh fingerprinted | Cache hợp lý và nguồn được CSP của trang cho phép |
| API JSON, SSE/WebSocket | CSP của HTML tham chiếu API đúng; CORS/Origin/auth riêng |
| Route qua SecurityFilterChain khác | Đúng CSP cho route đó |
| Trang có inline script/SSR template | Nonce hoặc hash trong HTML khớp policy cuối cùng |

### Chú ý kiểm thử qua hai đường khác nhau

Cần phân biệt:

1. **Origin test:** gọi trực tiếp Spring hoặc upstream nội bộ trong môi trường được phép.
2. **Public-path test:** gọi hostname công khai qua CDN/proxy đúng như người dùng thật.

Nếu origin test PASS mà public-path test FAIL, hãy tìm thay đổi ở **proxy, edge rule, caching, redirect hoặc TLS**. Nếu cả hai FAIL, trước hết kiểm tra config Spring/HTML; tuy nhiên không bỏ qua khả năng upstream tự dùng một proxy nội bộ khác.

## 17. Kiểm tra HTTP thực nhận bằng công cụ dòng lệnh

Các lệnh sau là **ví dụ thao tác**, không bắt buộc phải chạy trong STEP 4. Chỉ thực hiện ở môi trường bạn có quyền kiểm thử.

Để đọc header của response GET thực sự (không phụ thuộc hành vi riêng của HEAD):

~~~bash
curl -sS -D - -o /dev/null https://app.example.com/dashboard
~~~

Để xem redirect và header của các chặng:

~~~bash
curl -sS -i https://app.example.com/dashboard
curl -sS -L -D - -o /dev/null https://app.example.com/dashboard
~~~

Khi đọc output, tìm các header:

~~~text
Content-Security-Policy: ...
Content-Security-Policy-Report-Only: ...
Cache-Control: ...
ETag: ...
Age: ...
Vary: ...
Location: ...
Via: ...
~~~

`Age`/`Via` và header debug riêng của CDN có thể giúp xác định cache hit hoặc proxy hop, nhưng không phải mọi CDN đều xuất đủ các trường này. Không tự suy ra “không có Age = không có cache”.

### Kiểm tra CSP ở HTML và nonce cùng response

Một câu lệnh chỉ in header không đủ khi có nonce. Cần lấy **header và body của cùng một GET** rồi so sánh:

~~~bash
curl -sS -i https://app.example.com/dashboard
~~~

Trong output, xác minh:

~~~text
Content-Security-Policy: script-src 'nonce-VALUE_A' ...
...
<script nonce="VALUE_A">...</script>
~~~

Sau đó thực hiện một GET độc lập và xác nhận có nonce mới (với xác suất rất cao), không phải một nonce cũ bị CDN phát lại. Trên trang HTML lớn, có thể sử dụng công cụ HTTP có khả năng lưu riêng header và body của **cùng request** để tránh nhầm giữa hai response khác nhau.

### Kiểm tra conditional request có chủ đích

Khi hệ thống có ETag, thực hiện GET lấy ETag thật, rồi thử request có `If-None-Match` với giá trị nhận được:

~~~bash
curl -sS -D - -o /dev/null \
  -H 'If-None-Match: "html-v42"' \
  https://app.example.com/dashboard
~~~

`"html-v42"` ở đây là placeholder; cần thay ETag thật nếu muốn thử 304. Kết hợp với DevTools để xác định body cache mà browser sử dụng. Đừng kết luận chính sách của tài liệu chỉ từ response 304 không có body.

## 18. Kiểm thử Spring Security ở origin

Đối với ứng dụng Servlet, có thể kiểm tra policy trên route HTML bằng MockMvc. Ví dụ giả định route `/dashboard` trả 200 và test bật Spring Security filters:

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(get("/dashboard"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("script-src 'self'")
    ))
    .andExpect(header().string(
        "Content-Security-Policy",
        containsString("object-src 'none'")
    ));
~~~

Với WebFlux:

~~~java
webTestClient.get()
    .uri("/dashboard")
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
    .valueMatches(
        "Content-Security-Policy",
        ".*script-src 'self'.*"
    );
~~~

Những test này xác nhận **hành vi của Spring Security ở tầng test**. Chúng không kiểm chứng cấu hình Nginx/CDN hoặc response browser thực sự nhận. Vì vậy một pipeline đáng tin nên có thêm HTTP integration test qua hostname công khai/staging và E2E browser test.

### Test quan hệ CSP nonce–HTML trên origin

Nếu dùng nonce, nên đọc toàn bộ response HTML trong test, trích nonce từ CSP header và kiểm tra phần tử inline đáng tin dùng cùng giá trị. Cần test **hai request HTML độc lập** để xác nhận nonce không bị tái sử dụng.

Ví dụ ý tưởng:

~~~java
String nonceFromHeader = extractCspNonce(responseHeader);
String html = responseBody;

assertTrue(html.contains("nonce=\"" + nonceFromHeader + "\""));

// Request HTML thứ hai phải có nonce được tạo mới.
assertNotEquals(nonceFirstResponse, nonceSecondResponse);
~~~

Các biến/hàm ở ví dụ này là **pseudocode của phép kiểm tra**, không phải một test JUnit có thể biên dịch độc lập. Triển khai thật cần lấy `responseHeader` và `responseBody` từ cùng một result của MockMvc/WebTestClient, và trích nonce từ directive thực sự điều khiển thẻ script/style.

Ở tầng public, lặp lại phép thử để phát hiện proxy/cache làm thay đổi kết quả. Thậm chí khi origin sinh nonce mới đúng, CDN vẫn có thể phát lại một bản HTML cũ.

## 19. Kiểm thử trình duyệt: kết quả hành vi mới là bằng chứng cuối

Tạo một trang demo có:

~~~html
<!-- Script ngoài cùng origin -->
<script src="/js/dashboard.js" defer></script>

<!-- Inline script chỉ hợp lệ nếu policy cấp nonce/hash -->
<script nonce="SAME_RESPONSE_NONCE">
  window.dashboardLoaded = true;
</script>

<!-- Một ví dụ script không có nonce/hash để kiểm tra CSP -->
<script>console.log("unapproved inline script");</script>
~~~

Trang thật cần dùng nonce ngẫu nhiên thay placeholder `SAME_RESPONSE_NONCE`, và phải có CSP đúng trong **header của cùng response**.

Quy trình:

1. Mở DevTools → Network và chọn **document HTML**, không chọn JSON API.
2. Xem **tất cả** `Content-Security-Policy` và `Content-Security-Policy-Report-Only`; ghi policy nào do app và proxy/edge phát.
3. Xem body HTML; xác định nonce/hash của script hợp lệ có khớp policy thực thi cuối cùng không.
4. Tải mới trang ít nhất hai lần; đối chiếu nonce, `Age`/cache status và CSP. Nếu nonce không đổi, kiểm tra cache hoặc cách sinh nonce.
5. Quan sát Console: script thiếu nonce/hash cần bị CSP thực thi chặn nếu không có nguồn cấp phép khác.
6. Kiểm tra hành vi JS, CSS, ảnh, font, API, WebSocket, form và login; CSP báo đúng không có nghĩa mọi yêu cầu khác sẽ thành công.
7. Thử cache miss/hit, reload, back/forward navigation, redirect và trang lỗi theo kiến trúc thực tế.
8. Thử trên browser mục tiêu; xử lý CSP Level 3/Report-Only và thông báo có thể khác nhau.

Mã gõ trực tiếp trong DevTools Console không luôn chịu đúng cùng quy tắc như script do tài liệu phân tích. Khi đánh giá CSP, ưu tiên phép thử trong **HTML hoặc tệp JS thực sự được tải** ở môi trường demo.

### Phân biệt bfcache và HTTP cache

Browser có thể khôi phục một trang từ *back-forward cache* khi người dùng quay lại lịch sử, thay vì tải HTML mới. Trong trường hợp này, không có nghĩa server đã gửi một HTTP response HTML mới với nonce cũ. Cần phân biệt **khôi phục tài liệu đang tồn tại** với **một request HTML mới được CDN đáp trả**, nhất là khi kiểm thử “nonce phải khác sau mỗi lần quay lại trang”.

## 20. Chẩn đoán xung đột thường gặp

| Triệu chứng | Khả năng nguyên nhân | Kiểm tra và hướng xử lý |
|---|---|---|
| MockMvc PASS nhưng browser FAIL | Proxy/CDN thêm hoặc thay CSP | So sánh origin và public response |
| Nonce trong HTML khớp header app nhưng script bị chặn | Policy thực thi thứ hai không cho nonce | Xem **mọi** CSP ở browser |
| Sau deploy script inline mới bị chặn | Hash/HTML hoặc nonce/header bị thay đổi ở edge | Đối chiếu body cuối cùng và policy |
| Chỉ một số người dùng lỗi CSP | CDN cache hit theo vùng/edge hoặc canary trộn version | Kiểm tra cache key, TTL, policy version, edge POP |
| Tải mới mà nonce giữ nguyên | HTML/header bị cache hoặc nonce tĩnh/session | Kiểm tra cache và nguồn sinh nonce |
| HTML nonce cũ, CSP nonce mới | Header bị proxy viết lại sau khi body cache | Đồng bộ hoặc tắt cache HTML nonce |
| Script CDN chạy ở local nhưng production chặn | Proxy phát `script-src 'self'` khác app | Thống nhất chủ sở hữu policy |
| Có hai `Content-Security-Policy` header | App và gateway cùng thêm | Xác định chủ đích; tránh policy mâu thuẫn |
| Chỉ trang login/404 thiếu CSP | Route qua chain/handler lỗi khác | Kiểm tra HTML đích và error page |
| `Content-Security-Policy-Report-Only` bị coi là chặn | Hiểu nhầm header hoặc còn CSP thực thi | Phân biệt disposition và tất cả headers |
| `304 Not Modified` gây hành vi khác lần 200 | Metadata cache/body version không đồng bộ | Thử conditional GET và xem tài liệu thực browser dùng |
| HTML cache chung hiển thị dữ liệu cá nhân | Cache key/cache policy sai nghiêm trọng | Ngừng shared caching HTML nhạy cảm và điều tra rò dữ liệu |
| CSS tải nhưng font không hiện | `font-src` hoặc CORS font CDN | Kiểm tra Network font, CSP và CORS |
| API bị CSP chặn dù server bật CORS | `connect-src` của tài liệu không cho nguồn | Sửa CSP ở HTML, giữ CORS API riêng |
| Form login bị chặn | `form-action` hoặc policy thứ hai | Kiểm tra đích submit, SSO/redirect, server |
| App tạo URL nội bộ vào CSP | Dùng Host/forwarded header sai ở reverse proxy | Cấu hình public origin và trust proxy |
| CSP còn hiệu lực sau khi code đã rollback | CDN/proxy cache hoặc config tách biệt | Kiểm tra version và purge đúng phạm vi |
| CSP vắng mặt trên production HTML | Chỉ cấu hình ở JSON API hoặc proxy loại header | Xác định service trả HTML; cấu hình lại owner |

### Vì sao không nên sửa bằng unsafe-inline hoặc allowlist quá rộng?

Nếu script bị chặn vì policy chồng chéo, thêm `'unsafe-inline'` vào một policy có thể không có tác dụng do policy còn lại vẫn chặn; nếu có tác dụng, nó có thể mở quyền thực thi nội tuyến vượt quá nhu cầu.

Tương tự, mở `script-src https:`, `connect-src *` hoặc `img-src *` chỉ để tránh thay đổi cấu hình CDN khiến chính sách giảm đáng kể giá trị. Sửa **nguồn sinh CSP, cache hoặc sự lệch version** là cách giải quyết trực tiếp hơn.

## 21. Rollout có kiểm soát khi CSP đi qua nhiều tầng

Triển khai CSP mới nên có **policy version**, chủ sở hữu và đường rollback rõ ràng:

| Giai đoạn | Công việc | Kiểm chứng |
|---|---|---|
| 1. Kiểm kê | Tìm tất cả nơi ghi CSP, loại HTML, cache và biến đổi edge | Sơ đồ trách nhiệm được thống nhất |
| 2. Thiết kế | Chọn owner, CSP tĩnh/dynamic, allowlist và cache strategy | Review ứng dụng + hạ tầng |
| 3. Report-Only | Thử candidate trên **HTML cuối cùng**, không chỉ JSON | Console/report và chức năng |
| 4. Staging enforcement | Kiểm tra sau proxy/CDN staging | Browser E2E, login, API, 404, 304, cache hit/miss |
| 5. Canary | Áp dụng policy theo route/nhóm người dùng nếu có cách cache an toàn | Violation `enforce`, JavaScript errors, tác vụ nghiệp vụ |
| 6. Rollout | Mở rộng theo kết quả đo | Policy và HTML cùng version ở các edge |
| 7. Duy trì | Kiểm tra khi đổi CDN, asset, HTML build hoặc Spring config | Automated checks và dashboard |

### Canary phải tương thích với cache key

Một trang HTML dùng policy A cho nhóm thử nghiệm và policy B cho nhóm còn lại không thể dùng bừa **cùng một cache entry công khai** mà không phân tách. Nếu CDN lưu bản A rồi phát cho nhóm B, canary không còn đúng phạm vi và có thể trộn policy với nội dung.

Phải thiết kế phân phối theo route/variant hoặc vô hiệu cache thích hợp trong giai đoạn canary, đồng thời kiểm tra những response cuối cùng ở nhiều edge. Nếu CSP có nonce theo response, việc cache HTML nguyên bản càng cần tránh.

### Rollback đúng cách

Khi có sự cố nghiêm trọng, rollback nên phục hồi **một baseline CSP đã được kiểm thử** cùng phiên bản HTML/asset tương ứng. Không mặc định tắt hẳn CSP, HSTS hoặc CSRF. Cần kiểm tra TTL của policy/HTML tại CDN; rollback code Spring chưa chắc làm các edge phục vụ HTML cũ dừng ngay.

Nếu sự cố là cache trả HTML cá nhân hóa cho sai người dùng, hãy ưu tiên xử lý rò rỉ dữ liệu/cache, không coi đó chỉ là lỗi CSP.

## 22. Bài thực hành tổng hợp

**Bối cảnh:** Dựng ứng dụng Spring Boot có route `/dashboard` render HTML và file JS cùng origin, một inline bootstrap script hợp lệ và API ở `https://api.example.net`. Đặt một reverse proxy hoặc CDN test trước ứng dụng. Mục tiêu là chứng minh policy đúng trên **đường public**, không chỉ tại Spring.

1. Cấu hình CSP tĩnh trong Spring Security Servlet hoặc WebFlux cho trang **không dùng inline code**: `default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self' https://api.example.net; object-src 'none'; base-uri 'none'`. Kiểm tra header ở origin.
2. Thêm một CSP chặt hơn tại reverse proxy ở môi trường thử nghiệm. Quan sát script/asset nào bị từ chối khi có **hai CSP thực thi**.
3. Chọn một owner cho CSP; điều chỉnh proxy để chuyển tiếp policy ứng dụng hoặc chủ đích thay thế policy tĩnh mà không tạo header mâu thuẫn.
4. Tạo một script inline hợp lệ. Chuyển sang nonce ngẫu nhiên per response, truyền nonce đến template và xuất CSP cùng giá trị.
5. Thử cache nguyên cả header/body của HTML nonce: kiểm tra nonce có bị tái sử dụng giữa các request. Thử trường hợp cache HTML nhưng proxy thay riêng CSP header: kiểm tra lỗi mismatch.
6. Chỉnh cache của HTML động theo nhu cầu, trong khi vẫn cho phép cache dài hạn các file JS/CSS versioned.
7. Tạo một HTML tĩnh với inline code cố định có CSP hash. Thử minify/chỉnh whitespace trong script mà không cập nhật hash, quan sát vi phạm rồi sửa đồng bộ.
8. Thử 302 sang login, 404 do Spring, 404 do proxy và một conditional GET có ETag; xác định **response HTML nào** browser thực dùng và CSP đi kèm.
9. Sử dụng MockMvc hoặc WebTestClient kiểm tra header tại origin; dùng công cụ HTTP/DevTools kiểm tra **public endpoint** qua proxy/CDN.
10. Thiết kế thử nghiệm Report-Only rồi enforcement theo canary, có policy version, người review và kế hoạch rollback khi cache/CDN phục vụ sai variant.

### Câu hỏi tự đánh giá

1. Vì sao CSP trong `HttpSecurity` có thể đúng nhưng script vẫn bị chặn sau reverse proxy?
2. Khi browser nhận hai CSP thực thi, policy nào quyết định nếu một cho phép CDN và policy kia từ chối?
3. Đặt CSP trên API JSON có bảo vệ tài liệu HTML được phục vụ từ một CDN khác không?
4. Vì sao cache lại toàn bộ header và HTML có nonce là vấn đề dù script vẫn chạy?
5. Vì sao chỉ đổi nonce trong header, không đổi HTML, có thể làm script hợp lệ bị chặn?
6. Khi nào CSP hash phù hợp hơn nonce với HTML được cache?
7. `Vary: Cookie` có bảo đảm nonce mới cho mỗi response HTML không?
8. Tại sao cần kiểm tra 304/ETag khi policy và nội dung HTML thay đổi?
9. Reverse proxy kết thúc TLS có làm `'self'` được browser đánh giá theo hostname upstream nội bộ không?
10. Vì sao kiểm thử Spring Security bằng MockMvc/WebTestClient không đủ để khẳng định CSP production đúng?
11. Điều gì có thể xảy ra nếu edge minify inline script nhưng policy vẫn chứa hash của phiên bản cũ?
12. Khi rollout canary, cache key và khả năng phát lại response có thể làm sai phạm vi thử nghiệm thế nào?
13. Nếu bật `add_header` ở một Nginx location, vì sao phải kiểm tra các security header khác và trang lỗi?
14. Khi rollback CSP, vì sao cần kiểm tra cả HTML/asset version và cache TTL ở CDN?

## 23. Ghi nhớ

**CSP phải được thiết kế và kiểm thử theo toàn bộ đường HTTP tới trình duyệt.** Spring Security có thể phát header đúng, nhưng reverse proxy/CDN có thể thêm policy khác, thay header, chỉnh HTML hoặc phát lại bản cache. Nhiều CSP thực thi cùng có hiệu lực; một policy cho phép không vô hiệu hóa được chính sách khác đang chặn. Vì vậy phải phân công nguồn chịu trách nhiệm CSP rõ ràng và kiểm chứng trên response HTML công khai.

Với **HTML động có nonce**, cần sinh nonce mạnh cho từng response, đồng bộ header–template và tránh cache chung phát lại nonce. Với **HTML tĩnh**, JS/CSS ngoài hoặc CSP hash cho inline code cố định thường thuận lợi hơn cho cache; khi nội dung đổi, policy và cache version phải đổi đồng bộ. Kiểm thử cả 200, redirect, lỗi, cache hit/miss, conditional 304, Servlet/Reactive và browser. CSP chỉ là một phần của hệ thống phòng vệ HTTP: vẫn phải phối hợp xử lý HTML an toàn, CSRF, CORS, HSTS, HTTP firewall, TLS và bảo vệ session trong `SPRING_SECURITY_HTTP_PROTECTION`.
