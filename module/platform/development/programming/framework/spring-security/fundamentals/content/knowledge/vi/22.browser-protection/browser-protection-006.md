# Content-Security-Policy và giới hạn đối với tấn công XSS

**Content-Security-Policy (CSP)** là một chính sách bảo mật được ứng dụng gửi tới trình duyệt để giới hạn nguồn và cách tải/thực thi một số loại nội dung, đặc biệt là **JavaScript**. CSP giúp **giảm nguy cơ và tác động của nhiều hình thức Cross-Site Scripting (XSS)**, nhưng **không thay thế** việc xử lý dữ liệu đầu vào/đầu ra đúng cách và không bảo đảm ngăn mọi kiểu XSS.

Ví dụ, nếu một điểm yếu cho phép dữ liệu người dùng chèn `<script>...</script>` vào HTML, một CSP đủ chặt có thể từ chối thực thi đoạn script đó. Tuy nhiên, nếu chính mã JavaScript đáng tin của ứng dụng bị lợi dụng như một “gadget”, hoặc CSP cho phép nguồn script nguy hiểm, kẻ tấn công vẫn có thể thực thi hành động ngoài ý muốn.

Bài học tập trung vào: cơ chế CSP ở browser, sự khác biệt giữa **allowlist CSP** và **nonce/hash-based strict CSP**, cách cấu hình header với Spring Security Servlet, triển khai từng bước bằng `Report-Only`, giới hạn CSP với XSS/DOM XSS, và checklist kiểm thử thực tế.

## 1. XSS là gì, và CSP tham gia ở bước nào?

**XSS (Cross-Site Scripting)** xảy ra khi dữ liệu không đáng tin được đưa vào một ngữ cảnh mà browser có thể diễn giải thành JavaScript hoặc nội dung có khả năng thực thi ngoài ý định của ứng dụng.

Ba nhóm thường gặp:

- **Reflected XSS:** Dữ liệu từ request được phản hồi ngay vào trang mà không xử lý đúng ngữ cảnh, ví dụ query parameter hiển thị dưới dạng HTML.
- **Stored XSS:** Payload được lưu trong database, comment, profile hoặc hệ thống nội dung và phát ra khi người khác mở trang.
- **DOM-based XSS:** JavaScript của trang lấy dữ liệu không đáng tin (URL, hash, postMessage, API...) rồi đưa trực tiếp vào một **DOM sink nguy hiểm**, ví dụ `innerHTML`, tạo khả năng thực thi ngoài ý muốn.

Khi XSS thành công, kẻ tấn công có thể gửi request bằng quyền người dùng, thay đổi DOM, đọc dữ liệu trang mà script được phép truy cập và đánh cắp thông tin không được bảo vệ. Cookie `HttpOnly` giảm việc đọc cookie qua `document.cookie`, nhưng **không ngăn script cùng origin tạo request được browser tự gắn cookie**.

**CSP tham gia như một lớp kiểm soát tại browser**: trước khi script/style/resource được tải hoặc thực thi, browser so với chính sách hiện hành. Nếu không được phép, browser có thể chặn và ghi nhận violation. CSP **không sửa dữ liệu đầu vào bị lỗi, không xóa payload khỏi HTML, không thay thế việc encode hoặc sanitize**.

Một chuỗi phòng vệ đúng thường là:

```text
Dữ liệu không đáng tin
        |
        v
Kiểm soát input theo nghiệp vụ
        |
        v
Encode output đúng ngữ cảnh / sanitize HTML nếu phải cho phép HTML
        |
        v
Tránh DOM sinks nguy hiểm (innerHTML, eval, document.write...)
        |
        v
Browser áp CSP (nguồn script, nonce/hash, navigation/frame...)
        |
        v
Theo dõi violation + kiểm thử XSS
```

**Nguyên tắc:** Khắc phục điểm chèn script là phòng vệ chính; CSP là **defense in depth** để tăng chi phí khai thác và giảm phạm vi tác động khi một lớp khác thất bại.

## 2. Cách browser nhận CSP

CSP thường được trả trong **HTTP response header** của tài liệu HTML:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'
```

Một ứng dụng có thể gửi **nhiều chính sách CSP**. Khi browser nhận nhiều chính sách ở chế độ enforce, mỗi chính sách được áp dụng và kết quả tổng hợp là **chặt hơn**, không phải “chính sách sau ghi đè toàn bộ chính sách trước”. Vì thế duplicate headers do reverse proxy, CDN hoặc filter Java có thể gây lỗi tải asset khó hiểu.

Có hai header quan trọng:

| Header | Mục đích | Vi phạm có bị chặn? |
|---|---|---|
| `Content-Security-Policy` | **Enforce**: browser áp chính sách | Có, đối với directive trình duyệt hỗ trợ |
| `Content-Security-Policy-Report-Only` | Quan sát, đo lường ảnh hưởng của chính sách thử nghiệm | **Không** do chính sách Report-Only; báo cáo/console tùy hỗ trợ |

Ví dụ bật thử nghiệm:

```http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; object-src 'none'; report-uri /csp-report
```

Với Report-Only, nội dung bị chính sách thử nghiệm đánh dấu là vi phạm **vẫn có thể chạy**; không dùng nó làm bằng chứng ứng dụng đã được bảo vệ. Một trang có thể đồng thời có chính sách enforce hiện tại và report-only để thử chính sách chặt hơn.

CSP cũng có thể khai báo bằng thẻ `<meta http-equiv="Content-Security-Policy" ...>` trong một số tình huống, nhưng **không hỗ trợ đầy đủ mọi directive** và chỉ có tác dụng sau khi browser đọc tới thẻ đó. Các directive như `frame-ancestors` và chế độ `Report-Only` không có tác dụng qua meta CSP theo cách header hỗ trợ. **Ưu tiên HTTP header** cho cấu hình bảo mật chính thức.

## 3. Nắm các directive thiết yếu

Một CSP gồm các **directive** và **source expressions**. Các directive khác nhau điều khiển các loại tải/hoạt động khác nhau:

| Directive | Chức năng | Gợi ý |
|---|---|---|
| `default-src` | Fallback cho nhiều directive tải tài nguyên khi không khai báo riêng | Khởi đầu chặt, ví dụ `'none'` hoặc `'self'` theo ứng dụng |
| `script-src` | Kiểm soát nguồn và cách thực thi JavaScript | Quan trọng nhất với XSS; cân nhắc nonce/hash |
| `script-src-elem` | Chính sách riêng cho phần tử `<script>` | Nếu khai báo, có ưu tiên so với fallback `script-src` cho phần tử |
| `script-src-attr` | Chính sách riêng cho inline event handlers | Tránh `onclick="..."` và tương tự |
| `style-src` | Nguồn CSS và inline styles | Tách CSS ra file; tránh `unsafe-inline` nếu có thể |
| `img-src` | Nguồn hình ảnh | Chỉ cho những nguồn thực sự dùng |
| `font-src` | Nguồn font | Thường `'self'` và CDN tin cậy nếu cần |
| `connect-src` | Đích mà script có thể kết nối (Fetch/XHR/WebSocket/EventSource...) | Liệt kê đúng API; xét cách browser xử lý scheme/WS |
| `object-src` | `<object>`, `<embed>` | Thường đặt `'none'` |
| `base-uri` | Hạn chế giá trị `<base href="...">` | Thường `'none'` hoặc `'self'` |
| `form-action` | Hạn chế URL đích của form submission | Khóa các đích form theo nghiệp vụ |
| `frame-ancestors` | Ai được nhúng trang trong `frame`/`iframe` | Chống clickjacking, ví dụ `'none'` |
| `frame-src` | Trang hiện tại được nhúng các frame từ đâu | Khác với `frame-ancestors` |
| `upgrade-insecure-requests` | Đề nghị browser nâng request tải tài nguyên HTTP lên HTTPS | Không thay thế cấu hình HTTPS/HSTS |
| `report-uri` / `report-to` | Đích báo cáo vi phạm, tùy browser/CSP reporting support | Triển khai và kiểm thử an toàn dữ liệu report |

**Không phải mọi directive đều kế thừa `default-src`.** `frame-ancestors`, `base-uri` và `form-action` là những ví dụ quan trọng **không dựa vào `default-src` để tự nhận giá trị**. Nếu yêu cầu bảo vệ các hành vi này, hãy chỉ định rõ.

Ví dụ một chính sách nguồn cơ bản cho website dùng JavaScript/CSS từ chính origin:

```http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

Đây là **chính sách minh họa dạng allowlist**, không phải một CSP dùng được cho mọi site. Nếu ứng dụng cần Google Fonts, CDN, websocket, SSO, ảnh bên ngoài hoặc iframe thì phải thiết kế/kiểm lại từng directive. `data:` cho ảnh cần cân nhắc phạm vi; không tùy tiện thêm `data:` vào `script-src`. Đừng sao chép và bật enforce mà chưa đo tác động đối với trang thực.

## 4. Hiểu chính xác các source expressions

Các giá trị thường thấy:

| Source expression | Ý nghĩa |
|---|---|
| `'none'` | Không cho phép nguồn nào cho directive đó |
| `'self'` | Cho tài nguyên cùng origin của tài liệu |
| `https://cdn.example.test` | Một nguồn cụ thể được chỉ định bằng scheme/host |
| `https:` | Cho phép từ nhiều nguồn HTTPS, khá rộng |
| `*` | Cho phép rất rộng; thường không phù hợp bảo vệ script |
| `'nonce-...'` | Cho phép script/style cụ thể mang nonce hợp lệ |
| `'sha256-...'` / `'sha384-...'` / `'sha512-...'` | Cho inline script/style có hash tương ứng |
| `'strict-dynamic'` | Cho script được nonce/hash tin cậy truyền mức tin cậy cho những script nó tải động theo quy tắc CSP3 |
| `'unsafe-inline'` | Nới lỏng chặn inline script/style; thường làm yếu chống XSS |
| `'unsafe-eval'` | Cho phép cơ chế đánh giá chuỗi thành code như `eval()`; tăng rủi ro |

Dấu nháy đơn trong CSP là **một phần cú pháp** của các keyword/hash/nonce expressions. `script-src self` không tương đương `script-src 'self'`. Khi cấu hình thành chuỗi Java, cần giữ nguyên dấu nháy đúng.

Một số hiểu nhầm cần tránh:

- `'self'` **không tự đồng nghĩa nguồn an toàn** nếu origin chứa script do user upload, endpoint trả nội dung có thể thực thi, hoặc JavaScript hiện tại có XSS gadgets.
- Cho `https:` hoặc một CDN rộng **không tương đương** chỉ cho các script được review.
- `'unsafe-inline'` mở khả năng chạy inline script/event handlers trong một số chính sách và làm mất phần lớn lợi ích CSP chống XSS.
- `'unsafe-eval'` cho phép đánh giá chuỗi như code. Đừng bật chỉ vì một thư viện không tương thích; ưu tiên refactor/cấu hình build.
- Nonce/hash chỉ giúp nếu attacker **không thể tự lấy một giá trị hợp lệ gắn vào payload**, và các script đã tin cậy không bị lợi dụng.

## 5. CSP dạng allowlist: dễ bắt đầu nhưng có giới hạn

Ví dụ:

```http
Content-Security-Policy: script-src 'self' https://cdn.example.test; object-src 'none'; base-uri 'none'
```

Browser có thể tải script từ cùng origin hoặc CDN đã cho phép. Cách này tốt hơn không có CSP, nhất là khi loại bỏ `unsafe-inline` và chặn object embedding. Nhưng allowlist CSP có những giới hạn thực tế:

1. Một CDN chứa **nhiều tài nguyên không cùng mức tin cậy**. Nếu attacker có thể đưa script lên một đường dẫn được allowlist bao phủ, CSP có thể chấp nhận script đó.
2. Tài nguyên cùng origin không nhất thiết an toàn nếu ứng dụng có endpoint trả nội dung theo dữ liệu người dùng và trình duyệt coi như JavaScript.
3. Việc duy trì danh sách host đúng trong ứng dụng lớn có thể phức tạp; dev có xu hướng thêm wildcard/HTTPS toàn cục để “hết lỗi”.
4. Một script được cho phép có thể có bug DOM XSS, tải các resource khác hoặc xử lý dữ liệu không đáng tin sai cách.
5. Không phải mọi vấn đề XSS có thể được chặn chỉ bằng danh sách domain, nhất là code đã tin cậy nhưng xử lý sink sai.

**Vì thế strict CSP dựa trên nonce/hash thường được khuyến nghị hơn cho việc kiểm soát thực thi script**, sau khi đánh giá khả năng tương thích.

## 6. Nonce-based strict CSP hoạt động thế nào?

**Nonce** là giá trị ngẫu nhiên khó đoán, được tạo **mới cho từng HTML response** và gắn đồng thời vào CSP header và những thẻ script hợp lệ mà server chủ động phát ra.

Ví dụ minh họa (nonce giả chỉ để đọc cơ chế, tuyệt đối không dùng cố định trong sản phẩm):

```http
Content-Security-Policy: script-src 'nonce-DEMO_NONCE_NOT_FOR_PRODUCTION' 'strict-dynamic'; object-src 'none'; base-uri 'none'
```

```html
<script nonce="DEMO_NONCE_NOT_FOR_PRODUCTION" src="/assets/main.js"></script>
```

Khi browser thấy script có nonce trùng chính sách, nó cho script đó chạy theo quy tắc CSP. Một script do attacker tự chèn nhưng **không có nonce hợp lệ** thường bị chặn. Ví dụ trên là minh họa cú pháp, không phải cấu hình an toàn vì nonce là chuỗi cố định dễ đoán.

### Những yêu cầu cần tuân thủ

1. **Mới cho mỗi response:** Sinh nonce dùng bộ sinh số ngẫu nhiên mật mã, ví dụ `SecureRandom`, đủ độ bất định (thường lấy từ 128 bit trở lên) và không tái sử dụng một nonce cố định cho mọi page/user.
2. **Cùng giá trị trong một response:** Header CSP và `nonce` attribute của script hợp lệ phải khớp. Có thể có nhiều script hợp lệ dùng cùng nonce của **response hiện tại**.
3. **Do server cấp:** Không lấy giá trị nonce từ query parameter, request header hoặc dữ liệu user kiểm soát.
4. **Không cấp cho nội dung không đáng tin:** Nếu một đoạn HTML user-controlled có thể tự nhận nonce hợp lệ, attacker có thể tận dụng nó.
5. **Không để cache làm lặp response nonce không phù hợp:** HTML được cache/phục vụ qua proxy/CDN cần thiết kế chiến lược sinh và gắn header/markup nhất quán, không để cùng nonce tĩnh dùng rộng qua nhiều response.
6. **Không coi nonce là password của người dùng:** Nonce xuất hiện trong HTML hợp lệ và có thể quan sát trong ngữ cảnh trang; nó phải ngăn việc *đoán/chèn script vào response trước khi browser thực thi*, không phải che khỏi JavaScript đã được phép chạy.

### `strict-dynamic` là gì?

Với CSP3, `'strict-dynamic'` cho phép niềm tin cấp qua nonce/hash của **script gốc** mở rộng đến một số script được script đó tải động, chẳng hạn script element được tạo bằng DOM API và thêm vào document. Khi `strict-dynamic` có hiệu lực trong `script-src`, các allowlist host/scheme như `'self'`, `https:` và `'unsafe-inline'` sẽ bị bỏ qua theo quy tắc hỗ trợ của browser.

**Không có nghĩa script nào do một script tin cậy “gọi” cũng chắc chắn an toàn.** Nếu script gốc lấy URL do attacker kiểm soát rồi tạo script từ URL đó, `strict-dynamic` có thể cho phép nạp script độc hại. Vì vậy dù có CSP, vẫn cần kiểm tra URL, dữ liệu và các dependency của ứng dụng.

Một strict CSP có thể có cấu trúc:

```http
Content-Security-Policy: script-src 'nonce-<gia-tri-ngau-nhien-cho-tung-response>' 'strict-dynamic'; object-src 'none'; base-uri 'none'
```

Đây là **mẫu mô tả**, không phải chuỗi nên copy nguyên vào production. Những directive còn lại như `connect-src`, `style-src`, `img-src`, `form-action`, `frame-ancestors` cũng phải quyết định theo ứng dụng. Các browser cũ có thể hỗ trợ tập tính năng CSP khác nhau; cần kiểm tra đối tượng browser được hỗ trợ.

## 7. Hash-based CSP: phù hợp inline script bất biến

Thay vì nonce thay đổi từng response, với inline script **không đổi**, server có thể đặt hash SHA-256/SHA-384/SHA-512 của **chính xác nội dung script** vào `script-src`.

Ví dụ cấu trúc:

```http
Content-Security-Policy: script-src 'sha256-<Base64-cua-SHA-256-noi-dung-script>'; object-src 'none'; base-uri 'none'
```

Một inline script được cho phép khi browser tính hash nội dung và khớp source expression trong policy. Nếu thay đổi **dù chỉ một dấu cách**, byte đầu vào khác khiến hash khác; build/template có thể làm script không còn chạy được.

**Không nhầm CSP hash với Subresource Integrity (SRI):**

- CSP hash source có thể dùng để cho phép inline script có nội dung chính xác.
- SRI dùng thuộc tính `integrity` trên phần tử tải tài nguyên hỗ trợ nhằm xác minh nội dung của external resource. Hai cơ chế có mục đích liên quan nhưng không hoàn toàn thay thế.
- Với tài nguyên build có hash thay đổi, cần cập nhật CSP cùng artifact được triển khai.

**Ưu tiên nonce cho HTML dựng động**, hash cho các đoạn script tĩnh nhỏ và ổn định. Với SPA build và bundler, bạn có thể tránh inline JavaScript để đơn giản hóa policy, nhưng một allowlist `'self'` thuần túy vẫn không mạnh bằng strict CSP trong mọi threat model.

### Ví dụ Java 17 độc lập: hash đổi khi nội dung đổi

Tạo file `CspHashDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

public class CspHashDemo {
    static String cspHash(String script) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(
                script.getBytes(StandardCharsets.UTF_8));
        return "sha256-" + Base64.getEncoder().encodeToString(digest);
    }

    public static void main(String[] args) throws Exception {
        String original = "console.log('ok');";
        String same = "console.log('ok');";
        String changed = "console.log('ok'); ";

        System.out.println("Same content: " +
                cspHash(original).equals(cspHash(same)));
        System.out.println("Extra space changes hash: " +
                !cspHash(original).equals(cspHash(changed)));
        System.out.println("CSP hash prefix: " +
                cspHash(original).startsWith("sha256-"));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac CspHashDemo.java
java CspHashDemo
```

Đầu ra chính xác:

```text
Same content: true
Extra space changes hash: true
CSP hash prefix: true
```

Ví dụ chỉ dùng Java chuẩn và giải thích tính nhạy với byte của CSP hash. Khi áp dụng thật, phải hash **nội dung inline script thực tế ở HTML cuối cùng** theo quy tắc trình duyệt, không hash cả thẻ `<script>` hoặc text khác với nội dung được render.

## 8. Inline script, event handlers và `eval`

Các dạng sau thường gây vấn đề khi xây dựng CSP chặt:

```html
<script>alert("inline script")</script>
<button onclick="submitForm()">Submit</button>
<a href="javascript:submitForm()">Submit</a>
```

Khi có `script-src` phù hợp và không cho phép inline unsafe, những cách thực thi trực tiếp này thường bị chặn, trừ các trường hợp được policy cho phép theo nonce/hash và các cơ chế liên quan. **Nonce trên một thẻ script không tự cấp phép cho `onclick` attribute**; hãy refactor event handlers sang JavaScript qua `addEventListener`.

Ví dụ sửa:

```html
<button id="submit-button" type="button">Submit</button>
<script src="/assets/form.js"></script>
```

```javascript
document.querySelector("#submit-button").addEventListener("click", () => {
    // Gọi hành động được phép theo logic ứng dụng.
    console.log("Clicked");
});
```

Ví dụ trên cần policy cho `/assets/form.js` (ví dụ nonce hợp lệ cho script tag khi strict CSP, hoặc nguồn phù hợp trong allowlist CSP) và phải có file `/assets/form.js` thực tế. Nó là minh họa HTML/JS, không phải chương trình Java chạy độc lập.

`eval(userInput)`, `new Function(userInput)` và những API chuyển chuỗi thành mã thực thi làm tăng nguy cơ. CSP thường chặn các cơ chế như vậy trừ khi policy cho phép `'unsafe-eval'` hoặc cơ chế đặc thù. Đừng bật `unsafe-eval` để “chữa nhanh” lỗi framework/bundler mà chưa phân tích hậu quả và cấu hình build production.

**CSP giúp ngăn thực thi**, nhưng nếu dữ liệu người dùng vẫn bị nhúng sai vào HTML/JavaScript, bạn chưa sửa lỗ hổng gốc. Cần encode đúng context, hạn chế các sink nguy hiểm, và sanitize khi thật sự cho phép HTML do người dùng cung cấp.

## 9. Spring Security Servlet có bật CSP mặc định không?

**Không.** Spring Security có nhiều HTTP response security headers được hỗ trợ sẵn, nhưng **không tự thêm CSP mặc định** vì không thể biết danh sách nguồn script/style và các yêu cầu của từng ứng dụng. Người phát triển phải tự khai báo policy. Do đó “đã thêm Spring Security dependency” **không chứng minh** response đang mang CSP.

Ví dụ trong một **dự án Spring Boot 3 / Spring Security 6 dùng Servlet**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CspSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        String policy = "default-src 'none'; "
                + "script-src 'self'; "
                + "style-src 'self'; "
                + "img-src 'self' data:; "
                + "font-src 'self'; "
                + "connect-src 'self'; "
                + "object-src 'none'; "
                + "base-uri 'self'; "
                + "form-action 'self'; "
                + "frame-ancestors 'none'";

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .headers(headers -> headers
                        .contentSecurityPolicy(csp -> csp
                                .policyDirectives(policy)))
                .build();
    }
}
```

Đây là ví dụ **cấu hình tích hợp framework**, không biên dịch độc lập bằng `javac`. Cần có Spring Boot, Spring Security, controller, security configuration và các asset tương ứng. Chính sách minh họa cho `script-src 'self'` **không phải strict nonce-based policy**; nó phù hợp để giải thích API Spring và cần review theo ứng dụng thật trước khi bật.

Khi dùng nhiều `SecurityFilterChain`, kiểm tra `securityMatcher` và thứ tự chain. Header CSP phải được áp dụng cho **response HTML thích hợp**; đừng chỉ cấu hình ở chain dành riêng cho `/api/**` rồi cho rằng trang browser ở `/dashboard` cũng có CSP.

### Chỉ muốn theo dõi trước: `Report-Only`

Spring Security hỗ trợ cấu hình policy ở chế độ báo cáo thay vì enforce:

```java
.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; script-src 'self'; "
            + "object-src 'none'; base-uri 'none'; "
            + "report-uri /csp-report")
        .reportOnly()))
```

Đoạn trên là **mảnh của `HttpSecurity` builder**, không phải class hoàn chỉnh; `reportOnly()` là API phù hợp cho cấu hình Servlet này theo tài liệu Spring Security 6. Nếu trong dự án/phiên bản có API khác, kiểm tra JavaDoc cụ thể. Ở chế độ Report-Only, browser không chặn vi phạm vì policy đó. `/csp-report` là endpoint minh họa, muốn thu nhận báo cáo phải thực sự triển khai một API bảo mật phù hợp.

**Không dùng `Report-Only` vĩnh viễn như thay thế enforce** khi mục tiêu là giảm thiểu XSS bằng CSP. Quy trình chuẩn là quan sát → sửa tương thích → áp enforce → tiếp tục giám sát.

### Sinh nonce động với Spring Security

Với **strict CSP có nonce**, không thể viết một `policyDirectives("script-src 'nonce-ABC'")` cố định cho mọi request: giá trị nonce phải thay đổi theo từng HTML response. Cần có một thành phần xử lý request/response tạo nonce an toàn, đặt vào template và đưa **cùng nonce** vào header CSP.

Luồng kiến trúc:

```text
Request tới trang HTML
     |
     v
Server sinh nonce ngẫu nhiên mới bằng SecureRandom
     |
     +--> request attribute/template model: cspNonce
     |
     +--> response header: script-src 'nonce-<cspNonce>' ...
     |
     v
Template render script được tin cậy với nonce khớp
     |
     v
Browser chỉ chấp nhận script thỏa CSP
```

Nếu dùng Servlet Filter, phải cân nhắc **thời điểm set header**, phạm vi filter và tránh để cấu hình CSP ở Spring Security/Gateway ghi đè hoặc thêm policy khác ngoài ý muốn. Đừng đồng thời gắn một CSP tĩnh và một CSP động ở nhiều tầng mà chưa kiểm response thực.

Hàm Java minh họa **chỉ riêng thao tác sinh nonce**, không phải cấu hình filter hoàn chỉnh:

```java
import java.security.SecureRandom;
import java.util.Base64;

public final class CspNonceGenerator {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static String newNonce() {
        byte[] bytes = new byte[16]; // 128 bit ngẫu nhiên
        RANDOM.nextBytes(bytes);
        return Base64.getEncoder().encodeToString(bytes);
    }
}
```

Khi dùng thật, gọi `newNonce()` **mỗi HTML response**, dùng kết quả đó cho cả header lẫn những `<script nonce="...">` đáng tin của response, không lưu hằng và không nhận nonce từ user. Chương trình ở đoạn này là một helper Java có thể biên dịch trong project, không có `main`; ví dụ Java độc lập đã có ở mục 7.

## 10. CSP bảo vệ được gì, và không bảo vệ được gì?

### Trường hợp CSP có thể giúp giảm tác hại

- Một payload chèn thêm `<script>` inline nhưng **không có nonce/hash hợp lệ** có thể bị chặn.
- `onerror=...`, `onclick=...` hoặc `javascript:` URL có thể bị hạn chế khi policy không nới lỏng inline script.
- Script từ origin bên ngoài danh sách/policy cho phép có thể bị chặn.
- `object-src 'none'` và `base-uri 'none'` giảm một số đường tấn công qua object/base element.
- `frame-ancestors 'none'` hoặc giới hạn origin được nhúng giúp giảm clickjacking (đây là mục tiêu khác với XSS).
- `form-action` có thể hạn chế nơi form được submit; `connect-src` hạn chế một số đích request script.
- Báo cáo violation giúp phát hiện một số hành vi đáng ngờ hoặc asset bị chặn khi rollout.

### Những điều CSP không thể bảo đảm

1. **Không thay thế output encoding theo ngữ cảnh.** Chèn dữ liệu vào HTML body, attribute, JS string, URL, CSS có quy tắc escape/sanitize khác nhau.
2. **Không tự loại DOM XSS.** Script được tin cậy vẫn có thể đưa dữ liệu không an toàn vào DOM sinks.
3. **Không ngăn mọi yêu cầu trái phép do XSS.** Nếu JavaScript đáng tin bị điều khiển, attacker có thể lợi dụng hành vi nó đã được cho phép, kể cả gọi API qua quyền người dùng.
4. **Không tự che token/cookie khỏi code chạy được.** `HttpOnly` che cookie khỏi `document.cookie`, nhưng script cùng origin vẫn có thể tạo request với cookie tự gửi. CSP không thay thế session/CSRF/access-control design.
5. **Không thay thế CSRF token.** CSP có thể giảm một số đường thực thi/exfiltration nhưng không xác nhận ý định của request cookie-authenticated.
6. **Không thay thế authorization.** Trang/API phải kiểm tra quyền truy cập với từng tài nguyên, không dựa vào browser policy để bảo vệ server.
7. **Không tự cản mọi lộ dữ liệu.** Chính sách `connect-src` không bao trùm mọi đường exfiltration; một XSS chạy được có thể lợi dụng đích được cho phép hoặc hành vi hợp lệ của ứng dụng.
8. **Không phải mọi browser hỗ trợ đầy đủ mọi directive.** Cần kiểm tra browser mục tiêu, extension, WebView và tương thích CSP level.
9. **Không ngăn các lỗi phía server.** SQL injection, SSRF, logic authorization, xử lý file upload là các vấn đề khác.
10. **Không khiến script bên thứ ba đáng tin thành an toàn tuyệt đối.** Nếu CDN hoặc dependency được cho phép bị xâm nhập, policy có thể vẫn chấp nhận tài nguyên đó.

**CSP chỉ có giá trị khi chính sách phù hợp với trust boundary và được browser thực thi đúng.** “Có header CSP” là điều kiện chưa đủ để kết luận chống XSS hiệu quả.

## 11. Tại sao `unsafe-inline`, `unsafe-eval`, wildcard làm CSP yếu?

Một chính sách kiểu:

```http
Content-Security-Policy: default-src * data: blob:; script-src * 'unsafe-inline' 'unsafe-eval' data: blob:
```

có vẻ cho phép mọi thành phần hoạt động, nhưng lại **bỏ qua các lớp chặn quan trọng đối với nhiều vector XSS**. Nó không phải một CSP có giá trị phòng vệ tốt chỉ vì browser nhận header.

Hậu quả phổ biến:

- `'unsafe-inline'`: payload inline và event handler có nhiều cơ hội thực thi hơn.
- `'unsafe-eval'`: code có thể biến chuỗi không đáng tin thành JavaScript thực thi.
- `*`/`https:` rộng: script không được review vẫn có thể được tải từ nhiều nguồn.
- `data:` hoặc `blob:` ở script sources: mở thêm phương thức tải script; chỉ dùng khi hiểu rõ mô hình và kiểm soát cần thiết.
- Third-party script nằm trong allowlist: được browser tin theo policy, dù chính dependency có thể có bug hoặc bị compromise.

**Không đánh giá chỉ bằng độ dài header.** Chính sách dài mà chứa nhiều wildcard/unsafe có thể kém bảo vệ hơn strict CSP đơn giản sử dụng nonce/hash và cấm object embedding.

Ngoài ra, khi `'strict-dynamic'` có hiệu lực, các host/scheme allowlist trong cùng `script-src` có thể **bị bỏ qua** trên browser CSP3, nên dev phải hiểu semantics trước khi “thêm domain” để chữa lỗi. Tránh copy chính sách nhiều thế hệ CSP mà không kiểm tra browser cụ thể.

## 12. DOM XSS và Trusted Types

Ngay cả khi mọi `<script>` đều được nonce cho phép, một đoạn JavaScript trong script hợp lệ vẫn có thể chứa code nguy hiểm:

```javascript
const value = new URLSearchParams(location.search).get("message");
document.querySelector("#message").innerHTML = value ?? "";
```

Đoạn trên đưa dữ liệu URL không đáng tin thẳng vào HTML parser thông qua `innerHTML`. CSP có thể chặn một số script do dữ liệu tạo ra, nhưng **điểm lỗi là sử dụng DOM sink không an toàn**.

Nếu chỉ cần hiển thị văn bản, cách an toàn hơn:

```javascript
const value = new URLSearchParams(location.search).get("message");
document.querySelector("#message").textContent = value ?? "";
```

`textContent` đưa nội dung thành text, không parse thành HTML. Đây là sửa lỗi gốc, không phụ thuộc vào CSP.

Nếu nghiệp vụ thật sự cần render một tập HTML do người dùng cung cấp, phải dùng **HTML sanitizer được kiểm chứng và cấu hình phù hợp**; không đưa raw HTML tùy ý vào `innerHTML`.

### Trusted Types là gì?

Trên những browser hỗ trợ, **Trusted Types** giúp kiểm soát một số sink dễ tạo DOM XSS bằng cách yêu cầu giá trị thuộc kiểu tin cậy thay vì chuỗi tùy ý. CSP có directive như:

```http
Content-Security-Policy: require-trusted-types-for 'script'; trusted-types app-policy
```

Nội dung policy trong ví dụ minh họa yêu cầu dùng Trusted Types cho các sink phù hợp và có thể giới hạn tên các Trusted Types policies được tạo. Nhưng:

- Trusted Types cần **code ứng dụng đúng và policy sanitizer đúng**; nó không tự biến input bất kỳ thành an toàn.
- `trusted-types app-policy` không có nghĩa mọi dữ liệu đi qua policy đều an toàn nếu implementation return dữ liệu chưa sanitize.
- **Browser support không đồng nhất**; cần kiểm tra browser/embedded WebView mục tiêu và cơ chế fallback.
- Trusted Types cũng **không thay thế** việc encode/sanitize phía server, authz và CSP script policy.

Phối hợp code không dùng sink nguy hiểm, Trusted Types khi hỗ trợ và strict CSP thường mạnh hơn chỉ có một header CSP allowlist.

## 13. Report-Only, báo cáo vi phạm và quy trình rollout

Bật enforce ngay một CSP chặt trên website lớn có thể làm hỏng chức năng: form validation, analytics, image/font, websocket, mã bootstrap SPA hoặc các thẻ inline được template tạo ra.

Một quy trình thực tế:

1. **Kiểm kê:** Xác định HTML routes, script/styles đang tải, script inline, inline event handlers, nguồn API/WS, iframe, form destinations, CDN và third-party integrations.
2. **Sửa nguồn gây nới lỏng:** Chuyển inline handlers sang `addEventListener`, tránh `eval`, bỏ script load từ nguồn không cần thiết, phân loại asset.
3. **Chọn mô hình:** Nonce/hash-based strict CSP nếu có khả năng triển khai, hoặc allowlist hẹp như bước chuyển tiếp.
4. **Bật `Content-Security-Policy-Report-Only`:** Thu thập console violations và reporting endpoint, không thay đổi hành vi production ngay.
5. **Lọc false positives:** Browser extensions, bot, resource bị chặn vì thiết kế hợp lệ, nội dung khác version; đối chiếu với request/page thật.
6. **Tạo test tự động:** Kiểm CSP response trên các HTML routes, test script hợp lệ vẫn chạy, test inline không được phép bị chặn, test các luồng auth và thanh toán.
7. **Triển khai enforce theo phạm vi có kiểm soát:** Với chính sách đúng đã đo, chuyển sang `Content-Security-Policy`, tiếp tục theo dõi violations.
8. **Duy trì:** CI/asset pipeline, dependency upgrade, new frontend domains và các trang mới phải xét CSP; tránh nới wildcard chỉ để “qua lỗi”.

### Báo cáo vi phạm không phải bằng chứng chắc chắn có tấn công

Việc browser báo CSP violation có thể đến từ code hợp lệ chưa được allow, extension hoặc script độc hại. Ngược lại, một đợt tấn công không nhất thiết tạo report nếu browser không hỗ trợ reporting, mạng chặn gửi report, không có endpoint hoặc attacker sử dụng luồng được cho phép.

Endpoint thu nhận report phải:

- Chịu được payload không tin cậy, có giới hạn dung lượng, rate limiting và cơ chế lưu phù hợp.
- Không log thừa bí mật, session cookie, query có dữ liệu riêng hoặc nội dung raw không cần thiết.
- Không xem JSON report là chứng cứ xác thực danh tính client.
- Được bảo vệ trước abuse/DoS; không đưa toàn bộ chi tiết report chưa lọc vào dashboard công khai.

`report-uri` đã tồn tại lâu và còn được dùng phổ biến; `report-to`/Reporting API có hỗ trợ thay đổi theo browser. Kiểm thử thực tế theo browser thay vì giả định mọi violation luôn được gửi tới một endpoint.

## 14. CSP trong SPA, CDN, reverse proxy và caching

Khi frontend là SPA build riêng, một chính sách đúng phải phù hợp **entry HTML**, bundle scripts và runtime:

- **Nonce-based:** Cần HTML/response được sinh hoặc chỉnh có kiểm soát để header và nonce attribute dùng chung một giá trị mới. CDN cache HTML mà không cập nhật nonce/header đúng cách có thể làm token tái sử dụng hoặc policy không khớp.
- **Hash-based:** Các inline scripts ổn định có thể dùng hash sinh trong build, nhưng thay đổi bất kỳ byte nào phải cập nhật CSP.
- **External scripts:** Với allowlist CSP, chỉ `'self'` có thể cho bundles cùng origin; với strict CSP phải hiểu cách root script được nonce/hash tin cậy và các script động được tải.
- **Stylesheets:** `style-src` có thể chặn CSS-in-JS, style attributes, framework runtime; cần xử lý qua nonce/hash hoặc refactor, không mở `unsafe-inline` một cách vô thức.
- **APIs/WebSocket:** `connect-src` phải cho các endpoint thực sự dùng, nhưng đừng coi nó là firewall chặn mọi loại network request.
- **Fonts/Images:** `font-src`, `img-src` cần tối thiểu đủ dùng; cân nhắc static assets, data URLs và privacy.
- **Iframe:** `frame-src` định nghĩa trang được nhúng, `frame-ancestors` định nghĩa ai được nhúng trang của mình. Hai directive khác chiều.

Nếu cấu hình CSP ở **Spring Security, reverse proxy, CDN và frontend server** cùng lúc, phải thống nhất nơi quyết định policy, ngăn duplicate ngoài ý muốn và kiểm **response cuối cùng mà browser nhận**. Không đánh giá chỉ dựa trên Java code vì proxy có thể thêm, xóa hoặc thay CSP headers.

Đối với **API JSON-only**, CSP header trên JSON response thường không giúp bảo vệ trang HTML chính vì browser thi hành chính sách gắn với **tài liệu HTML** chứa script. Hãy đặt CSP nơi nội dung được browser render và script thực thi; không chỉ thêm CSP vào mọi `/api/**` rồi coi browser UI đã được bảo vệ.

## 15. So sánh CSP với các lớp bảo mật liên quan

| Cơ chế | Bảo vệ chính | Không thay thế |
|---|---|---|
| **Output encoding đúng ngữ cảnh** | Ngăn dữ liệu bị diễn giải thành code/markup ngoài ý muốn | Authentication, authorization |
| **HTML sanitization** | Cho phép một tập HTML giới hạn, loại thành phần nguy hiểm | Encode mọi ngữ cảnh, chính sách bảo mật khác |
| **CSP** | Giới hạn nguồn/cách thực thi, giảm hậu quả content injection | Sửa lỗi XSS gốc, authz, CSRF |
| **Trusted Types** | Giảm DOM XSS qua sink được hỗ trợ bằng kiểm kiểu đầu vào | Sanitizer/policy đúng và browser coverage |
| **HttpOnly cookie** | Giảm việc script đọc cookie auth | XSS có thể tạo request; CSRF |
| **SameSite cookie** | Hạn chế cookie tự gửi trong một số ngữ cảnh cross-site | XSS, mọi kiểu CSRF, authz |
| **CSRF token** | Chống giả mạo request đổi trạng thái có cookie/credential tự gửi | XSS, injection ở output |
| **HSTS / HTTPS** | Bảo vệ kết nối, chống downgrade theo chính sách | XSS trong trang hợp lệ |
| **frame-ancestors / X-Frame-Options** | Giảm clickjacking theo cách được browser hỗ trợ | XSS, thiếu authorization |
| **CORS** | Điều chỉnh quyền script đọc cross-origin response | XSS, CSRF, authentication |

Trường hợp điển hình: `Content-Security-Policy: script-src 'self'` có thể chặn inline script do attacker chèn, nhưng nếu app chủ động làm `innerHTML` từ dữ liệu user, bạn vẫn phải sửa DOM sink và kiểm tra dữ liệu. Tương tự, website có CSP tốt nhưng thiếu kiểm quyền ở backend vẫn có lỗ hổng dữ liệu nghiệp vụ.

## 16. Chẩn đoán sự cố CSP trong Spring Security

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy CSP header ở response HTML | Chưa cấu hình `.headers().contentSecurityPolicy`, chain không match, hoặc proxy bỏ header | Kiểm Network response cuối cùng và `SecurityFilterChain` |
| Inline script bị chặn | Thiếu nonce/hash đúng hoặc vẫn dùng inline handlers | Gắn nonce đúng cho script tin cậy, refactor event handlers |
| Script có nonce vẫn bị chặn | Nonce không khớp header, proxy/cache thay HTML, bị policy khác chặn | So sánh response header và thẻ script trong đúng request |
| External JS bị chặn | `script-src` không cho nguồn đó hoặc strict-dynamic làm thay đổi semantics host allowlist | Điều chỉnh trust policy, không mở `*` |
| API fetch bị chặn dù server trả 200 | `connect-src` không cho endpoint hoặc browser còn lỗi CORS | Kiểm console CSP violation và CORS riêng |
| CSS/Font không tải | `style-src` hoặc `font-src` quá chặt | Kiểm nguồn asset, refactor/sửa directive cụ thể |
| `iframe` không hiển thị | `frame-src` trang cha hoặc `frame-ancestors` trang con từ chối | Kiểm policy đúng chiều và cả hai response |
| Report-Only có violation nhưng trang vẫn hoạt động | Đó là hành vi mong đợi của Report-Only | Sửa vi phạm, chuyển sang enforce khi đủ điều kiện |
| Sau khi enforce SPA trắng trang | Bootstrap inline script bị chặn, nonce sai, build thay hash, cache cũ | Test deployment theo asset version, rollback policy sai có kiểm soát |
| Có CSP nhưng vẫn phát hiện XSS | Policy yếu, script trusted bị lợi dụng, browser không hỗ trợ hoặc điểm lỗi khác | Sửa XSS gốc và audit nonce/hash/trust boundaries |
| Một số trang có header khác nhau | Multiple filter chains/proxy/CDN/tách frontend server | Kiểm CSP theo từng HTML route và tầng response |
| Violation reports chứa dữ liệu nhạy cảm | Logging không lọc hoặc URI chứa data riêng | Rút gọn/lọc report và sửa URL thiết kế |

**Không “chữa” bằng cách thêm ngay `'unsafe-inline' 'unsafe-eval' *`.** Các lựa chọn đó có thể làm mất mục tiêu phòng vệ của CSP. Cần xác định chính xác directive gây lỗi và sửa code/nguồn tin cậy thay vì mở toàn cục.

## 17. Kiểm thử bảo vệ và giới hạn CSP

Một quy trình kiểm thử an toàn ở môi trường do bạn kiểm soát:

1. **Đọc header thực:** Dùng Developer Tools → Network chọn **HTML document**, kiểm `Content-Security-Policy` hoặc `Content-Security-Policy-Report-Only`.
2. **Kiểm syntax:** Kiểm các directive có `'self'`/`'none'` đúng dấu nháy, không chứa source quá rộng, tránh duplicate headers ngoài ý muốn.
3. **Kiểm script hợp lệ:** Tải trang và chạy các luồng thực tế: login, menu, form validation, search, frontend bundles và analytics được phê duyệt.
4. **Kiểm script không được phép:** Trên **trang test của chính ứng dụng** tạo một inline script **không nonce/hash**, xác nhận nó bị chặn trong chế độ enforce, không chỉ có warning Report-Only.
5. **Kiểm nonce/hash:** Với strict CSP, nonce phải mới theo response và khớp script hợp lệ; với hash, thay đổi một byte phải bị chặn khi không còn khớp.
6. **Kiểm từng nguồn:** Thử form-action, iframe, font, image, connect-src trên các route có chức năng tương ứng.
7. **Kiểm browser hỗ trợ:** Desktop/mobile browser và WebView mục tiêu, xem sự khác nhau CSP3/Trusted Types/reporting.
8. **Kiểm sửa lỗi gốc:** Review đường đưa user input vào HTML/JS/DOM sinks; không xem “CSP chặn payload mẫu” là bằng chứng không còn XSS.
9. **Kiểm proxy/cache:** So sánh HTML response nonce với CSP header trên cùng request qua CDN/reverse proxy.
10. **Kiểm reports/telemetry:** Report endpoint không lộ secrets và không thể bị spam quá mức.

Ví dụ lệnh xem header ở website **của bạn hoặc môi trường test được phép**:

```bash
curl -I https://portal.example.test/
```

Tên miền `example.test` chỉ dùng minh họa; lệnh chỉ hoạt động khi thay bằng endpoint thực tế. `curl` có thể đọc header HTTP nhưng **không thi hành CSP như trình duyệt**; việc CSP có hiệu lực phải được xác minh trong browser.

### Các câu hỏi review trước khi cho production

- Có script inline nào không có nonce/hash? Nếu có, vì sao không thể chuyển ra external file hoặc dùng nonce/hash?
- Nonce được sinh đủ ngẫu nhiên **mỗi response** và gắn cả header lẫn template đúng không?
- Có `unsafe-inline`, `unsafe-eval`, `https:`, `data:`, `blob:` hoặc `*` trong `script-src` không? Có lý do bảo mật đã review?
- Có phụ thuộc CDN hoặc user-upload cùng origin mà CSP có thể tin nhầm không?
- `object-src 'none'`, `base-uri` và `frame-ancestors` có đáp ứng nhu cầu không?
- Có đường xác thực, form và API nào bị chặn bởi `form-action` hoặc `connect-src` không?
- Có nhiều CSP headers từ các tầng hạ tầng khác nhau không?
- Dữ liệu user đã được encode/sanitize đúng trước khi render chưa?
- Có kế hoạch xử lý violations, thay đổi frontend và browser support không?

## 18. Câu hỏi tự kiểm tra

**1. CSP có ngăn mọi XSS không?** Không. Nó giảm một số khả năng thực thi/nạp nội dung trái phép; code đáng tin bị lợi dụng, policy quá rộng hoặc lỗ hổng không thuộc phạm vi CSP vẫn có thể gây tác hại. Phải sửa output/DOM sink sai cách.

**2. Vì sao Spring Security không tự bật CSP?** Mỗi ứng dụng có nguồn scripts/styles/frames/API khác nhau, nên không có một policy chặt vừa dùng được cho tất cả; developer phải định nghĩa.

**3. `Content-Security-Policy` và `Content-Security-Policy-Report-Only` khác gì?** Header thứ nhất enforce/block theo policy; header thứ hai giám sát vi phạm nhưng không chặn chỉ vì chính policy Report-Only đó.

**4. `script-src 'self'` có luôn là strict CSP không?** Không. Nó là origin allowlist; có nguy cơ khi cùng origin chứa script không an toàn. Strict CSP thường dùng nonce/hash với các directive bổ sung.

**5. Nonce nên sinh bao lâu một lần?** Mới cho từng HTML response bằng nguồn ngẫu nhiên mật mã, cùng giá trị dùng trong policy và script của response đó.

**6. CSP nonce có cho phép tự động mọi inline event handlers không?** Không. `onclick`/inline handlers cần refactor hoặc một cơ chế policy chuyên biệt, không được cho phép chỉ vì script khác có nonce.

**7. `strict-dynamic` có nghĩa gì?** Trong CSP3, tin cậy theo nonce/hash có thể truyền đến script được root script tải động, đồng thời host/scheme allowlists bị bỏ qua trong trường hợp tương ứng. Nó không sửa lỗ hổng của root script.

**8. `frame-ancestors` có dùng `default-src` fallback không?** Không; phải khai báo riêng nếu muốn hạn chế nguồn được nhúng trang.

**9. CSP có thay CSRF token, authentication hoặc authorization không?** Không. Chúng xử lý các trách nhiệm khác nhau.

**10. Một trang không có cảnh báo CSP vi phạm đã hết XSS chưa?** Chưa. Có thể policy thiếu hiệu lực, không có reporting, browser không hỗ trợ hoặc vector khai thác không gây violation.

**Kết luận:** **CSP là lớp phòng vệ bổ sung cho trình duyệt, không phải cách vá mọi XSS.** Ưu tiên sửa dữ liệu đầu ra và DOM sinks, sau đó thiết kế CSP chặt bằng nonce/hash phù hợp, loại bỏ `unsafe-inline` và `unsafe-eval` khi có thể, triển khai qua `Report-Only` → enforce và tiếp tục kiểm thử thực tế.

## Tài liệu tham khảo

- [Spring Security — Security HTTP Response Headers (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): cấu hình CSP, Report-Only và các security headers.
- [Spring Security — Security HTTP Response Headers (Features)](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): CSP giảm thiểu content injection/XSS; không thay xử lý input/output.
- [MDN — Content Security Policy (CSP)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP): directives, nonce, hash, strict-dynamic và kiểm thử.
- [MDN — Content-Security-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy): cú pháp, quyền fallback, các source expressions.
- [OWASP — Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html): xây CSP phòng vệ theo chiều sâu và lộ trình triển khai.
- [OWASP — Cross-Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): output encoding, sanitization, DOM XSS và giới hạn CSP.
