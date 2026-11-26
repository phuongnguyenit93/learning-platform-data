# Hash cho tài nguyên nội tuyến cố định

> **Chương:** Chính sách nội dung CSP  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các tình huống tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Bài toán: có một đoạn mã nội tuyến hợp lệ và không thay đổi

Giả sử trang dashboard có một đoạn JavaScript rất nhỏ, do đội phát triển kiểm soát:

~~~html
<script>window.appReady = true;</script>
~~~

Trang đồng thời sử dụng một style block ổn định:

~~~html
<style>.notice{color:#b00020}</style>
~~~

Ứng dụng muốn ngăn script hoặc style do nội dung không đáng tin cậy chèn vào trang. Chính sách cơ bản:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'self'
~~~

cho phép các tệp JavaScript và CSS từ cùng origin, nhưng **không tự cho phép** hai khối inline ở trên. Một cách giải quyết là thêm `'unsafe-inline'`, song điều đó cũng mở rộng quyền cho nhiều payload nội tuyến không mong muốn.

**CSP hash** cho phép chọn đúng *nội dung* inline đã được ứng dụng chấp nhận. Browser tính hash cho phần nội dung của khối `<script>` hoặc `<style>` rồi so sánh với hash được liệt kê trong chính sách. Nếu khớp, khối mã có thể được phép chạy/áp dụng; nếu không khớp, nó bị chặn khi CSP ở chế độ thực thi.

Mục tiêu bài học:

1. Phân biệt hash cho inline script/style với cho phép theo origin và nonce theo response.
2. Tính được hash SHA-256/SHA-384/SHA-512 theo đúng cú pháp source expression của CSP.
3. Đồng bộ mã inline thật trong template với hash được khai báo trong Spring Security.
4. Hiểu quy tắc đối với inline event handler và style attribute, cũng như giới hạn của `'unsafe-hashes'`.
5. Cấu hình Servlet/WebFlux, kiểm thử bằng browser và chẩn đoán sai lệch sau build/deploy.

## 2. CSP hash hoạt động như thế nào?

Một giá trị hash trong CSP source list có dạng:

~~~text
'sha256-BASE64_DIGEST'
'sha384-BASE64_DIGEST'
'sha512-BASE64_DIGEST'
~~~

`BASE64_DIGEST` là phần mã hóa Base64 của digest tương ứng. Đây **không phải** chuỗi hex, không phải giá trị nonce và không phải tên file.

Ví dụ cấu trúc của một CSP có hai hash:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'sha256-SCRIPT_HASH_BASE64'; style-src 'self' 'sha256-STYLE_HASH_BASE64'; object-src 'none'; base-uri 'self'
~~~

Hai chữ `SCRIPT_HASH_BASE64` và `STYLE_HASH_BASE64` chỉ là **placeholder để giải thích**, không phải digest hợp lệ. Khi triển khai, chúng phải được thay bằng digest Base64 thực sự của hai chuỗi mã inline.

~~~mermaid
flowchart TD
    A[Ứng dụng xác định inline script/style tin cậy và cố định] --> B[Tính SHA-256 từ chính nội dung của từng khối]
    B --> C[Mã hóa digest thành Base64]
    C --> D[Đưa source expression sha256 vào CSP header]
    D --> E[Browser nhận HTML và CSP]
    E --> F[Browser tính hash của nội dung inline]
    F --> G{Hash khớp một giá trị được phép?}
    G -- Có --> H[Cho phép theo CSP; vẫn chịu các kiểm tra khác]
    G -- Không --> I[Chặn nếu CSP đang thực thi]
~~~

Giá trị hash không phải bí mật. Kẻ tấn công có thể thấy hash trong header, nhưng việc **biết digest** không cho phép họ viết một script khác mà vẫn khớp digest đã được tính từ nội dung tin cậy, trong điều kiện thuật toán hash mật mã học còn an toàn. Ngược lại, **một đoạn mã có nội dung giống hệt đoạn đã cấp phép có thể được chấp nhận tại một vị trí khác** nếu kẻ tấn công chèn được phần tử và browser áp dụng cùng quy tắc. Vì vậy, hash không gắn quyền với một vị trí DOM cụ thể.

## 3. Chính xác phần nào của HTML được đưa vào hash?

Với:

~~~html
<script>window.appReady = true;</script>
~~~

chuỗi nội dung cần hash là:

~~~javascript
window.appReady = true;
~~~

Không đưa thẻ mở `<script>`, thẻ đóng `</script>` hay thuộc tính HTML vào nội dung đầu vào của phép tính. Tương tự, với:

~~~html
<style>.notice{color:#b00020}</style>
~~~

chuỗi cần hash là:

~~~css
.notice{color:#b00020}
~~~

Điều này đòi hỏi chú ý đến **đúng nội dung được trình duyệt phân tích**, bao gồm whitespace và line break có liên quan:

~~~html
<!-- Dạng A -->
<script>window.appReady = true;</script>

<!-- Dạng B: script có newline và dấu cách ở đầu/cuối -->
<script>
    window.appReady = true;
</script>
~~~

Dạng A và B có **nội dung khác nhau**, nên digest được phép của A không tự cho phép B. Nếu template engine, formatter, minifier hoặc build tool thay đổi script sau khi tính hash, browser có thể từ chối thực thi.

Các lưu ý kỹ thuật:

- Tính trên **nội dung của khối inline**, không trên toàn bộ file HTML và không trên nội dung của một file script ngoài.
- Hãy đối chiếu với **HTML cuối cùng được browser nhận**, đặc biệt khi template engine có chèn biến hoặc bộ build đã tối ưu mã.
- SHA-256 được biểu diễn Base64 theo cú pháp CSP; khác với việc copy chuỗi hex thông thường từ công cụ băm.
- Nên quản lý newline và encoding nhất quán, ví dụ UTF-8, và thử kết quả trên trình duyệt; HTML parsing có thể xử lý chuẩn hóa line ending.
- Với nội dung được thay đổi theo người dùng hoặc response, hash cố định dễ bị lệch. Khi cần inline code động, hãy cân nhắc nonce được sinh riêng cho từng response hoặc chuyển dữ liệu ra khỏi script.

### Cách tính hash bằng OpenSSL

Đối với đúng đoạn JavaScript một dòng ở ví dụ, lệnh minh họa trên shell hỗ trợ `printf` và OpenSSL:

~~~bash
printf %s 'window.appReady = true;' | openssl dgst -sha256 -binary | openssl base64 -A
~~~

Lệnh `printf %s` tránh tự thêm newline cuối chuỗi. Kết quả là Base64 digest, sau đó đặt vào `'sha256-...'` trong `script-src`. Với CSS:

~~~bash
printf %s '.notice{color:#b00020}' | openssl dgst -sha256 -binary | openssl base64 -A
~~~

**Đừng copy nguyên placeholder** trong phần mô tả thành policy production. Cần chạy phép băm trên nội dung thực tế và kiểm tra rằng policy đã có digest được tính ra.

## 4. Tính hash một cách xác định bằng Java

Trong dự án Spring, có thể dùng Java chuẩn để tạo CSP source expression từ một chuỗi cố định. Ví dụ sau dùng `MessageDigest` và `Base64`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

public final class InlineContentHashes {

    // Hai chuỗi phải khớp CHÍNH XÁC nội dung bên trong thẻ HTML khi render.
    public static final String INLINE_SCRIPT = "window.appReady = true;";
    public static final String INLINE_STYLE = ".notice{color:#b00020}";

    private InlineContentHashes() {
    }

    public static String sha256Source(String content) {
        try {
            byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
            String encoded = Base64.getEncoder().encodeToString(digest);
            return "'sha256-" + encoded + "'";
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(
                "SHA-256 is unavailable in the Java runtime",
                exception
            );
        }
    }

    public static String policy() {
        return "default-src 'self'; " +
            "script-src 'self' " + sha256Source(INLINE_SCRIPT) + "; " +
            "script-src-attr 'none'; " +
            "style-src 'self' " + sha256Source(INLINE_STYLE) + "; " +
            "style-src-attr 'none'; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "form-action 'self'; " +
            "frame-ancestors 'none'";
    }
}
~~~

Hàm `sha256Source(...)` trả về **toàn bộ source expression**, gồm dấu nháy đơn và phần `sha256-`. Vì vậy `policy()` có thể nối trực tiếp vào chuỗi directive.

**Phạm vi của ví dụ:** đây là chính sách cho hai khối inline cố định ở mục 1; ứng dụng thực tế còn cần khai báo `img-src`, `font-src`, `connect-src`, `frame-src` hoặc nguồn khác theo kiến trúc. Tạo digest ở thời điểm khởi động cho mã *thật sự không đổi* là hợp lý; không nên tính hash từ một giá trị do người dùng kiểm soát rồi tự động cấp phép script ấy.

### Vì sao không hash dữ liệu do người dùng cung cấp?

Giả sử server render:

~~~html
<script>
  window.currentUserMessage = "NỘI_DUNG_THAY_ĐỔI_THEO_REQUEST";
</script>
~~~

Nếu ứng dụng lấy **toàn bộ script đã chứa dữ liệu người dùng** để tính hash rồi thêm hash đó vào CSP response, nó đã cấp phép chạy bất kỳ mã nào lọt vào khối đó, kể cả mã bị chèn do escape sai. Hash chỉ giúp đảm bảo *nội dung khớp chính sách đã được lựa chọn đáng tin*, chứ không làm cho nội dung không đáng tin trở nên an toàn.

Ưu tiên giữ script cố định và đưa dữ liệu tới JavaScript qua cách an toàn như response JSON/API hoặc một phần tử chứa dữ liệu được escape đúng ngữ cảnh. Với nhu cầu script inline biến thiên thực sự, nonce theo response vẫn phải đi cùng **escape dữ liệu và kiểm soát template**; nonce cũng không sửa lỗi chèn code do ứng dụng tạo ra.

## 5. Spring Security Servlet: áp dụng hash cho script/style cố định

Spring Security Servlet có thể đưa policy do ứng dụng tạo vào `Content-Security-Policy` thông qua `HttpSecurity.headers().contentSecurityPolicy(...)`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(InlineContentHashes.policy())
            )
        );
        return http.build();
    }
}
~~~

Với template HTML xuất ra đúng các đoạn đã tính hash:

~~~html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Hash CSP demo</title>
    <style>.notice{color:#b00020}</style>
</head>
<body>
    <p class="notice">Ứng dụng sẵn sàng.</p>
    <script>window.appReady = true;</script>
</body>
</html>
~~~

Sau khi được render, hash trong CSP header phải khớp **nội dung chính xác giữa cặp thẻ**. Đoạn JavaScript và CSS một dòng trong ví dụ được chọn cố ý để giảm sự khác biệt vì indent.

Nếu dùng Thymeleaf, có thể đặt khối cố định nguyên văn trong template. Hãy tránh cho template xử lý hoặc biến đổi nội dung của hai khối trên nếu hash được tính từ constant ở Java. Một formatter tự thêm newline vào khối inline sẽ làm thay đổi nội dung cần hash.

### Đăng ký HeaderWriter trực tiếp

Nếu ứng dụng đã quản lý `HeaderWriter` thủ công trong Servlet stack, cũng có thể dùng:

~~~java
import org.springframework.security.web.header.writers.ContentSecurityPolicyHeaderWriter;

ContentSecurityPolicyHeaderWriter cspWriter =
    new ContentSecurityPolicyHeaderWriter(InlineContentHashes.policy());

http.headers(headers -> headers.addHeaderWriter(cspWriter));
~~~

Đây là **cách thay thế** cho DSL ở ví dụ trước trong cùng một chain. Đừng đăng ký cả hai chỉ để tạo cùng một CSP mà không có mục đích rõ ràng. Nếu server/proxy cùng xuất nhiều CSP thực thi, trình duyệt áp dụng **tất cả** chính sách đó; một chính sách khác có thể chặn khối inline dù hash của nó hợp lệ trong chính sách bạn đang xem.

**Spring Security không tự đọc template để tính hash.** Các giá trị mà `policyDirectives(...)` hoặc writer nhận là những directive do ứng dụng cung cấp; ứng dụng phải tự giữ chúng khớp với HTML thực tế.

## 6. Spring Security Reactive/WebFlux

Với WebFlux, cấu hình tương tự về CSP nhưng dùng `ServerHttpSecurity` và `SecurityWebFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        http.headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(InlineContentHashes.policy())
            )
        );
        return http.build();
    }
}
~~~

`InlineContentHashes` là tiện ích Java thuần nên có thể dùng lại ở Servlet và Reactive. Ý nghĩa của `sha256-...` cũng không khác: **trình duyệt** tính hash của inline code và áp dụng CSP. Nếu HTML được phát từ CDN hoặc frontend server khác origin, backend WebFlux chỉ trả JSON thì header CSP cần được đặt trên **response HTML thực tế** do frontend server trả, thay vì chỉ đặt trên API response.

Với template reactive có nội dung inline cố định, cách đồng bộ vẫn là đảm bảo template cuối cùng render đúng mã đã hash. Không cần nonce theo request chỉ để cho phép một nội dung inline thực sự bất biến; chính điều đó làm hash thuận lợi cho các trang có HTML cache.

## 7. Trình duyệt xử lý script/style hash và các directive chi tiết

Trong CSP, hash chỉ có tác dụng khi nó nằm trong directive phù hợp với loại nội dung. Bảng sau giả định browser hỗ trợ CSP Level 3:

| Nội dung | Directive ưu tiên | Fallback nếu directive ưu tiên không có |
|---|---|---|
| `<script>...</script>` | `script-src-elem` | `script-src` → `default-src` |
| `<script src="...">` | `script-src-elem` | `script-src` → `default-src` |
| Handler `onclick`/`onerror` | `script-src-attr` | `script-src` → `default-src` |
| `<style>...</style>` | `style-src-elem` | `style-src` → `default-src` |
| Stylesheet ngoài | `style-src-elem` | `style-src` → `default-src` |
| `style="..."` | `style-src-attr` | `style-src` → `default-src` |

### Bẫy 1: hash nằm ở script-src nhưng script-src-elem được khai báo riêng

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self' 'sha256-SCRIPT_HASH_BASE64'; script-src-elem 'self'
~~~

Ở browser hỗ trợ `script-src-elem`, thẻ `<script>...</script>` được kiểm theo `script-src-elem 'self'`. Vì directive ấy không chứa hash hoặc một cách cho phép inline khác, script inline có thể **vẫn bị chặn**, dù hash tồn tại trong `script-src`.

Nếu cần dùng directive chi tiết, hãy đưa hash vào đúng danh sách cho phép:

~~~http
Content-Security-Policy: default-src 'none'; script-src 'self'; script-src-elem 'self' 'sha256-SCRIPT_HASH_BASE64'; script-src-attr 'none'
~~~

Với `<style>...</style>`, quy tắc tương tự áp dụng khi có `style-src-elem`: hash của style block cần nằm trong directive thực sự điều khiển style element. Trong tài liệu học này, các ví dụ sản xuất ở mục 5 và 6 giữ chính sách đơn giản với `script-src`/`style-src` và không khai báo `-elem` chuyên biệt.

### Bẫy 2: hash cho script block không tự cho phép onclick

~~~html
<script>saveDraft();</script>
<button onclick="saveDraft()">Lưu</button>
~~~

Hai chuỗi JavaScript có vẻ giống nhau, nhưng một cái là script element, một cái là event handler trong thuộc tính HTML. Hash đã đặt trong `script-src` cho script element **không tự** cấp phép cho event handler.

Với CSP Level 3, có cơ chế `'unsafe-hashes'` kết hợp hash cho những nội dung inline attribute nhất định:

~~~http
Content-Security-Policy: script-src 'self'; script-src-attr 'unsafe-hashes' 'sha256-HANDLER_HASH_BASE64'
~~~

Đây là **minh họa cú pháp**. `HANDLER_HASH_BASE64` phải là digest thật của nội dung handler. Cơ chế này làm cùng chuỗi handler được cấp phép ở nhiều vị trí và có những giới hạn về hỗ trợ trình duyệt; vì vậy **ưu tiên chuyển handler sang `addEventListener(...)` trong file JavaScript tin cậy**.

Tương tự, hash của một khối `<style>` không tự cho phép thuộc tính `style="..."`. Cơ chế `'unsafe-hashes'` có thể được dùng với directive phù hợp cho style attribute trong những môi trường hỗ trợ, nhưng nên ưu tiên CSS class thay vì inline style attribute.

## 8. Không nhầm CSP hash, nonce và Subresource Integrity

Ba khái niệm thường xuất hiện cùng nhau, nhưng bảo vệ theo cách khác nhau.

| Kỹ thuật | Dùng ở đâu | Mục đích chính |
|---|---|---|
| **CSP hash** | Trong `script-src`/`style-src` và directive cụ thể phù hợp | Cấp phép nội dung inline có digest đúng, hữu ích khi nội dung ổn định |
| **CSP nonce** | CSP header và thuộc tính `nonce` của thẻ script/style tin cậy | Cấp phép thẻ có nonce khó đoán, được tạo mới cho từng response |
| **Subresource Integrity (SRI)** | Thuộc tính `integrity` của phần tử tải tài nguyên ngoài | Kiểm tra nội dung tài nguyên tải về khớp digest được khai báo |

Ví dụ SRI cho tệp script ngoài:

~~~html
<script
  src="https://static.example.net/app.js"
  integrity="sha384-BASE64_DIGEST_OF_FILE"
  crossorigin="anonymous"></script>
~~~

`BASE64_DIGEST_OF_FILE` chỉ là placeholder. SRI kiểm tra *bytes của tài nguyên tải về*, trong khi CSP hash inline ở các ví dụ trước kiểm tra *nội dung nằm trong thẻ script/style*. Chúng có thể được dùng cùng nhau nhưng không thay thế nhau.

Đối với tài nguyên script/style ngoài, CSP có các quy tắc tương tác riêng với hash và SRI/`integrity` trong những trình duyệt hỗ trợ; đừng giả định chỉ thêm hash của tệp vào `script-src` sẽ cho phép URL ngoài tự động như trường hợp inline. Bài học này chủ yếu dùng CSP hash cho **nội dung nội tuyến cố định**, còn tài nguyên ngoài cần thiết kế source list và SRI phù hợp.

### Khi nào chọn hash, nonce hoặc file ngoài?

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| JS/CSS có thể chuyển thành file cùng origin | File ngoài + source list chặt | Dễ cache, test, cập nhật và kiểm kê |
| Inline script 1–2 dòng, bất biến qua các response | CSP hash | Không cần phát giá trị mới cho mỗi response |
| Inline style block bất biến | CSP hash | Có thể cố định digest qua các lượt tải |
| Inline script thật sự cần thay đổi theo từng response | Nonce theo response + escape dữ liệu đúng ngữ cảnh | Tránh hash phải cập nhật liên tục |
| Script lấy từ CDN | Source list phù hợp, cân nhắc SRI | Phân biệt nguồn tải và toàn vẹn tệp |
| Inline event handler trong HTML cũ | Chuyển sang file JS, dùng `addEventListener` | Tránh phải nới quyền qua `'unsafe-hashes'` |

Hash không bảo vệ được nếu ứng dụng cố tình cấp phép hash của nội dung bị chèn. Nonce không bảo vệ được nếu kẻ tấn công điều khiển một script đã được cấp nonce. Cả hai đều là lớp phòng vệ hỗ trợ việc **ngăn thực thi mã không được cho phép**, không thay thế kiến trúc xử lý HTML an toàn.

## 9. Vòng đời của hash trong template và build pipeline

Với nội dung inline **cố định**, hash không cần được tạo mới theo response như nonce. Tuy nhiên, nội dung ấy có thể thay đổi khi code được build, format hoặc deploy:

~~~mermaid
flowchart LR
    A[Đoạn JS/CSS tin cậy trong nguồn] --> B[Build hoặc render template]
    B --> C[HTML cuối cùng gửi tới browser]
    A --> D[Tính CSP hash]
    D --> E[Gắn digest vào CSP header]
    C --> F{Nội dung inline và hash có khớp?}
    E --> F
    F -- Có --> G[Inline code hoạt động theo CSP]
    F -- Không --> H[Browser chặn; DevTools báo vi phạm]
~~~

Nếu B biến đổi nội dung (minify, thêm whitespace, chèn biến template, thay dấu xuống dòng) thì đường A → D có thể tạo digest **khác** nội dung đường B → C. Cách kiểm soát:

1. Chọn một **nguồn sự thật** cho nội dung mã inline, ví dụ chuỗi hằng dùng chung hoặc artifact HTML cuối cùng.
2. Tính hash từ chính đoạn code **sau các phép biến đổi làm thay đổi nội dung**, không dựa trên bản phác thảo khác với output.
3. Khi thay đổi nội dung inline, cập nhật digest và CSP **trong cùng bản phát hành**.
4. Thêm integration test đối chiếu HTML cuối cùng với hash trong response header.
5. Khi deploy qua reverse proxy/CDN, xác nhận không có tầng nào thêm hoặc thay đổi CSP mà không đồng bộ nội dung HTML.

**Các dạng thay đổi dễ làm lệch hash:**

| Thay đổi | Hệ quả |
|---|---|
| Thêm newline/indent trong `<script>` | Thay đổi nội dung cần hash |
| Đổi dấu nháy, dấu chấm phẩy, comment, khoảng trắng | Hash mới có thể khác dù hành vi JavaScript giữ nguyên |
| Chuyển script từ template tĩnh sang template có biến | Nội dung có thể khác giữa các lượt render |
| CDN minify nội dung HTML hoặc inject script | HTML được browser phân tích có thể khác bản đã hash |
| Cấu hình CSP cache lâu hơn phiên bản HTML | Script/style mới có thể bị chặn bởi policy cũ |
| Có nhiều CSP header thực thi | Mã phải thỏa tất cả policy, không chỉ policy chứa hash |

Với hệ thống có cache HTML tĩnh, CSP hash thường **hợp với cache hơn nonce**, vì chính sách có thể không đổi nếu inline code thật sự giữ nguyên. Dù vậy, không được giữ hash cũ khi nội dung inline đã thay đổi.

## 10. Kiểm thử phía server: hash có khớp HTML được render?

Một kiểm thử chỉ xác nhận header có chứa `sha256-` là chưa đủ. Cần chắc chắn hash trong header được tính từ nội dung inline thực tế.

### 10.1. Kiểm thử helper Java

Ví dụ JUnit 5:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class InlineContentHashesTest {

    @Test
    void producesSha256SourcesForTrustedInlineCode() {
        String scriptSource =
            InlineContentHashes.sha256Source(InlineContentHashes.INLINE_SCRIPT);
        String styleSource =
            InlineContentHashes.sha256Source(InlineContentHashes.INLINE_STYLE);

        assertTrue(scriptSource.matches("'sha256-[A-Za-z0-9+/]+={0,2}'"));
        assertTrue(styleSource.matches("'sha256-[A-Za-z0-9+/]+={0,2}'"));

        String policy = InlineContentHashes.policy();
        assertTrue(policy.contains("script-src 'self' " + scriptSource));
        assertTrue(policy.contains("style-src 'self' " + styleSource));
    }
}
~~~

Test trên kiểm tra định dạng và việc ghép source expression. Nó **không** chứng minh mã trong template vẫn giữ nguyên vì test chưa đọc HTML render.

### 10.2. Integration test cho Servlet bằng MockMvc

Giả sử ứng dụng có route HTML `/hash-demo` dùng template ở mục 5, Spring Security filters được bật trong test:

~~~java
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
class CspHashResponseTest {

    @Autowired
    MockMvc mvc;

    @Test
    void htmlAndCspHeaderUseTheSameTrustedInlineContent() throws Exception {
        MvcResult result = mvc.perform(get("/hash-demo"))
            .andExpect(status().isOk())
            .andReturn();

        String policy = result.getResponse()
            .getHeader("Content-Security-Policy");
        String html = result.getResponse().getContentAsString();
        assertNotNull(policy);

        assertTrue(policy.contains(InlineContentHashes.sha256Source(
            InlineContentHashes.INLINE_SCRIPT)));
        assertTrue(policy.contains(InlineContentHashes.sha256Source(
            InlineContentHashes.INLINE_STYLE)));

        assertTrue(html.contains(
            "<script>" + InlineContentHashes.INLINE_SCRIPT + "</script>"));
        assertTrue(html.contains(
            "<style>" + InlineContentHashes.INLINE_STYLE + "</style>"));
    }
}
~~~

Đây là test thích hợp cho **đúng template HTML mẫu**: nó kiểm tra hai block được render nguyên văn và policy chứa hash từ cùng chuỗi hằng. Trong dự án có formatter hoặc template biến đổi code, có thể trích nội dung giữa thẻ của HTML đã render rồi băm lại, thay vì chỉ so chuỗi định dạng mẫu.

Nếu route thực tế yêu cầu đăng nhập, cần thiết lập mock user hoặc authentication tương ứng trong test; HTTP 302/401/403 do authorization không chứng minh CSP hash đúng hay sai.

### 10.3. Kiểm tra response trên WebFlux

Với một ứng dụng WebFlux phục vụ HTML ở `/hash-demo`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

var result = webTestClient.get()
    .uri("/hash-demo")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class)
    .returnResult();

String policy = result.getResponseHeaders()
    .getFirst("Content-Security-Policy");
String html = result.getResponseBody();

assertNotNull(policy);
assertNotNull(html);
assertTrue(policy.contains(InlineContentHashes.sha256Source(
    InlineContentHashes.INLINE_SCRIPT)));
assertTrue(html.contains(
    "<script>" + InlineContentHashes.INLINE_SCRIPT + "</script>"));
~~~

Các test server xác minh **nội dung response**. Chúng không thay thế kiểm thử tương thích và hành vi CSP của trình duyệt.

## 11. Kiểm thử bằng trình duyệt: hash đúng, hash sai, script bị chèn

Trong môi trường demo mà bạn quản lý:

1. Phục vụ HTML có hai khối inline ở mục 5 và header CSP chứa hash thực sự của từng khối. Vào Network → Response Headers xác nhận `script-src` và `style-src` có source expression thích hợp.
2. Tải trang, kiểm tra JavaScript `window.appReady` được khởi tạo và CSS `.notice` áp dụng bình thường.
3. Chỉ thêm một dấu cách hoặc newline vào nội dung khối script trong template **mà chưa đổi hash trong header**. Sau khi render lại, browser phải từ chối khối script theo CSP thực thi phù hợp.
4. Cập nhật digest để khớp nội dung mới, tải lại trang và xác nhận script hợp lệ hoạt động.
5. Chèn một script khác không có hash được cấp phép trong môi trường thử nghiệm. Quan sát Console xem browser từ chối nội dung đó theo directive nào.
6. Thử `onclick="..."` và `style="..."` để xác nhận hash của script/style block không tự cấp phép cho các thuộc tính này.
7. Thử thêm một CSP header thực thi chặt hơn ở môi trường kiểm thử để thấy nhiều policy cùng có hiệu lực; bỏ cấu hình chồng chéo sau khi thử.

**Phân biệt enforcement và Report-Only:** header `Content-Security-Policy` chặn các hành vi vi phạm; `Content-Security-Policy-Report-Only` chỉ ghi nhận vi phạm theo policy đó. Có thể thử candidate policy chứa hash bằng Report-Only trước khi bật thực thi cho một frontend đang hoạt động. Một script đã được policy thực thi khác cho phép vẫn có thể bị Report-Only báo vi phạm, và ngược lại.

Trình duyệt đôi khi in ra hash gợi ý trong thông báo `Refused to execute inline script`. Hãy xem đó là **gợi ý kỹ thuật** và chỉ đưa hash vào allowlist sau khi xác minh script/style thực sự do ứng dụng tin cậy. Không tự động lấy mọi hash xuất hiện trong report để cấp phép.

## 12. Chẩn đoán những xung đột thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Script inline hợp lệ bị chặn dù có hash | Digest được tính từ chuỗi khác HTML sau render | So sánh byte/nội dung script; kiểm tra newline, indent, build, template |
| CSS inline không hoạt động | Hash của `style` khác nội dung thật hoặc hash nằm trong directive khác | Hash đúng style block và đặt trong `style-src`/`style-src-elem` thích hợp |
| Browser báo hash không hợp lệ | Dùng hex, thiếu Base64 hoặc thiếu cú pháp `'sha256-...'` | Tạo digest nhị phân, mã hóa Base64 và đặt trong nháy đơn |
| Script có hash trong `script-src` nhưng vẫn chặn | `script-src-elem` đã được cấu hình riêng | Đưa hash vào directive điều khiển script element |
| `onclick` bị chặn dù script block được phép | Hash cho script element không tự mở cho event handler | Dùng `addEventListener` trong JS tin cậy |
| Trang local chạy, production lỗi | Minifier, CDN, template formatter hoặc response thực tế khác | Kiểm tra HTML cuối cùng, đồng bộ CSP cùng version build |
| Mã đúng trong một CSP nhưng bị chặn | Có nhiều CSP thực thi từ app/proxy/CDN | Xem tất cả response headers và kiểm tra từng policy |
| Script thay đổi theo request, hash không ổn định | Nội dung inline chứa dữ liệu động | Tách dữ liệu khỏi script hoặc dùng nonce per response với escape đúng ngữ cảnh |
| Script chạy dù Report-Only báo vi phạm | Report-Only không chặn | Đánh giá policy và chuyển sang enforcement khi phù hợp |
| Hash từ tệp JavaScript ngoài không cho tải script | Nhầm hash của inline block với cơ chế tệp ngoài/SRI | Kiểm tra `script-src`, URL, SRI và thuộc tính `integrity` theo trường hợp |
| Một CSP xuất ở API nhưng trang HTML không có | Frontend được phục vụ bởi origin khác | Đặt CSP trên response HTML, không chỉ response JSON |

Khi chẩn đoán, ưu tiên kiểm tra **header và HTML cuối cùng trên browser**. Nếu server trả redirect đến login, hãy xem response HTML của trang đích. Nếu có nhiều `SecurityFilterChain`, kiểm tra chain nào phục vụ tài liệu. Cũng cần phân biệt lỗi CSP với CORS, CSRF, TLS, HTTP 404/500 và những lỗi JavaScript không liên quan tới CSP.

### Những quyết định bảo mật không nên bỏ qua

- Không thay hash bằng `'unsafe-inline'` chỉ để xóa lỗi, vì như vậy nhiều payload nội tuyến cũng có thể được phép.
- Không gắn hash cho đoạn code được hình thành từ dữ liệu người dùng chưa được escape/sanitize; hành động đó cấp quyền cho nội dung có thể bị chèn.
- Không giả định hash chỉ cấp phép ở một vị trí trong HTML. Quyền được xác định bởi nội dung khớp hash và ngữ cảnh directive.
- Không mặc định mọi script từ cùng origin đều an toàn; nếu cho `'self'`, ứng dụng vẫn phải kiểm soát tệp có thể phục vụ ở origin đó.
- Không để CSP header bị thay bằng chính sách cũ trong khi frontend đã deploy mã inline mới.
- Không dùng CSP thay thế các phòng vệ HTTP khác: CSRF token, CORS, HSTS, cookie/session bảo mật, HTTP firewall và mã hóa đầu ra đều có vai trò riêng.

## 13. Bài thực hành tổng hợp

**Bối cảnh:** Một trang Spring Boot có HTML render bằng Thymeleaf, một script khởi tạo giao diện và một khối CSS cố định. Đội phát triển muốn giữ chúng hoạt động mà không cho JavaScript nội tuyến tùy ý chạy.

1. Viết script `window.appReady = true;` và style `.notice{color:#b00020}` vào template trên một dòng, đúng như ở mục 5.
2. Dùng OpenSSL hoặc `MessageDigest` của Java để tính SHA-256 Base64 của **nội dung bên trong thẻ**, không tính cả thẻ HTML.
3. Dựng CSP có `script-src 'self' 'sha256-...'` và `style-src 'self' 'sha256-...'`, cộng với `object-src 'none'`, `base-uri 'self'` và các directive cần thiết cho ứng dụng.
4. Cấu hình policy trong Spring Security Servlet, đọc header từ request HTML bằng MockMvc và trình duyệt.
5. Chỉnh một ký tự của script mà không đổi hash để tái hiện vi phạm CSP; sau đó sửa digest cho đúng.
6. Thử một inline event handler `onclick`, lý giải vì sao hash script block không cấp quyền cho handler và chuyển sang `addEventListener`.
7. Viết cấu hình tương đương bằng `ServerHttpSecurity` cho WebFlux, so sánh HTTP header thực nhận.
8. Thử bật Report-Only khi thay đổi một policy đang triển khai, phân loại vi phạm hợp lệ trước khi áp dụng thực thi.
9. Đổi template thành inline script có nội dung thay đổi theo request và giải thích vì sao hash cố định không còn phù hợp; đề xuất nonce theo response hoặc đưa code ra file.

**Câu hỏi tự đánh giá:**

1. Vì sao hash được tính từ `<script>window.appReady = true;</script>` phải bỏ thẻ mở/đóng?
2. SHA-256 digest ở dạng hex có thể được đưa nguyên vào `'sha256-...'` của CSP không?
3. Một dòng script giống nhau về hành vi nhưng có newline/indent khác nhau sẽ được xử lý thế nào?
4. Vì sao hash cho `<script>` không tự cấp phép cho `onclick` hoặc `javascript:` URL?
5. Khi đã có `script-src-elem`, hash đặt trong `script-src` có luôn cấp phép cho inline script không?
6. Điểm khác nhau chính giữa CSP hash, nonce và SRI là gì?
7. Vì sao không nên tính hash từ script đã chứa nội dung người dùng vừa nhập rồi đưa ngay vào header CSP?
8. Nếu HTML được phát từ CDN và API từ Spring Security, nơi nào phải xuất CSP của tài liệu?
9. Khi sửa lỗi build khiến hash không khớp, vì sao thêm `'unsafe-inline'` không phải lựa chọn tốt?

## 14. Ghi nhớ

**CSP hash phù hợp với script và style inline có nội dung cố định, đã được đánh giá là tin cậy.** Server khai báo digest Base64 trong directive phù hợp; trình duyệt so sánh với đúng nội dung inline của tài liệu. Chỉ một thay đổi whitespace hoặc code cũng có thể khiến digest không còn khớp. Hash **không phải secret**, không gắn với một vị trí DOM và không sửa lỗi HTML injection.

Trong Spring Security Servlet hoặc WebFlux, ứng dụng phải quản lý chuỗi directive và bảo đảm hash khớp HTML cuối cùng được phục vụ. Hãy ưu tiên đưa JS/CSS ra file ngoài khi hợp lý; dùng hash cho đoạn inline bất biến, nonce cho những đoạn cần cấp phép theo response và kiểm thử cả server lẫn trình duyệt. CSP là một lớp giảm thiểu rủi ro bên cạnh xử lý HTML an toàn, CSRF, CORS, HSTS, HTTP firewall và bảo vệ session.
