# Giới hạn của header bảo mật: vẫn cần mã hóa đầu ra và kiểm tra dữ liệu

## 1. Mục tiêu

Trong Spring Security **Servlet**, HTTP security headers giúp trình duyệt áp dụng một số quy tắc an toàn: giới hạn nguồn script, chống nhúng frame, ép HTTPS, hạn chế MIME sniffing hoặc giảm rò rỉ referrer. Tuy nhiên chúng **không phải bộ lọc dữ liệu đầu vào** và **không tự mã hóa chuỗi do controller/template xuất ra**. Một ứng dụng có CSP, HSTS và `nosniff` vẫn có thể mắc XSS, SQL injection, path traversal, open redirect hoặc lỗi phân quyền.

Bài học phân biệt ba trách nhiệm:

1. **Security headers:** chính sách ở tầng response/browser; có giá trị *defense in depth*.
2. **Output encoding/sanitization:** làm dữ liệu không tin cậy được diễn giải là **dữ liệu**, không phải mã, khi xuất sang HTML, DOM, JavaScript, CSS hoặc URL.
3. **Input validation và safe APIs:** bảo đảm dữ liệu đúng kiểu, kích thước, quy tắc nghiệp vụ, thẩm quyền truy cập; dùng parameterized SQL, URL allowlist và các API an toàn tại sink.

Phạm vi: **Spring Boot 3 / Spring Security 6 / Java 17+**, ứng dụng Servlet. Các đoạn Spring là mã bên trong project có dependencies; mục 5 có chương trình thuần Java chạy bằng `javac`/`java` để giải thích escaping.

## 2. Header giúp gì và có giới hạn gì?

Ví dụ response:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Strict-Transport-Security: max-age=31536000; includeSubDomains
Cache-Control: no-store
```

Đây là những chính sách khác nhau, không phải “bộ bảo vệ mọi dữ liệu”. HSTS chỉ có ý nghĩa với HTTPS và browser đã nhận policy theo điều kiện áp dụng. CSP có thể chặn nhiều kiểu thực thi script, nhưng hiệu quả phụ thuộc directive và mã frontend. `Cache-Control: no-store` không xóa nội dung người dùng tải ra máy, log hoặc state đã giữ trong SPA.

| Header/cơ chế | Mục đích | Không giải quyết thay |
| --- | --- | --- |
| `Content-Security-Policy` | Hạn chế tài nguyên/script/frame; giảm ảnh hưởng XSS | Không thay escaping, DOM API an toàn, validation |
| `X-Content-Type-Options: nosniff` | Hạn chế MIME sniffing cho một số resource requests | Không kiểm tra file upload, HTML output, SQL |
| `X-Frame-Options` và CSP `frame-ancestors` | Giảm clickjacking qua framing | Không thay CSRF token, transaction confirmation |
| `Strict-Transport-Security` | Hướng browser truy cập host bằng HTTPS | Không lọc input, kiểm soát quyền, escape output |
| `Referrer-Policy` | Giới hạn dữ liệu URL gửi đi trong referrer | Không biến việc đặt secret trong URL thành an toàn |
| `Cache-Control` | Kiểm soát lưu phản hồi ở HTTP cache | Không thay authentication, không xóa log/download |
| `Permissions-Policy` | Giới hạn một số tính năng browser | Không ngăn SQLi hoặc SSRF |
| CORS response headers | Điều khiển việc script tại origin khác có thể đọc response qua CORS | Không phải authentication/authorization hay giải pháp CSRF tổng quát |
| `Secure`/`HttpOnly`/`SameSite` cookie attributes | Giảm các kiểu truy cập hoặc gửi cookie không mong muốn | Không thay input validation, không chống mọi CSRF/XSS |

**Câu hỏi đúng:** Browser sẽ được phép làm gì với response? Dữ liệu chứa trong response có được xây dựng an toàn không? Người gọi có quyền nhận dữ liệu đó không? Đây là **ba nhóm kiểm tra độc lập**.

### 2.1. Một luồng phòng thủ nhiều lớp

```text
Request/query/JSON/headers/DB/upstream (dữ liệu không tin cậy)
    |
    +-- Giới hạn size, kiểu, schema và ngữ nghĩa nghiệp vụ
    +-- Xác thực, phân quyền và kiểm soát owner/tenant
    +-- Dùng safe APIs: SQL parameters, quản lý đường dẫn, URL allowlist
    |
    v
Controller / service / view model
    |
    +-- Render đúng ngữ cảnh: HTML text/attribute, URL, JavaScript...
    +-- Nếu rich HTML: sanitizer theo allowlist
    |
    v
HTTP response + security headers
    |
    v
Browser
```

Một bước không thể “đền bù hoàn toàn” khi bước khác bỏ qua. Ví dụ authorization sai làm lộ hóa đơn của Bob dù CSP hoàn hảo; SQL string concatenation có thể bị khai thác trên server trước khi trình duyệt đọc response.

## 3. Vì sao XSS vẫn xảy ra dù bật CSP?

**Cross-Site Scripting (XSS)** xảy ra khi dữ liệu không tin cậy được đặt vào ngữ cảnh mà trình duyệt diễn giải thành markup hoặc code. Có reflected XSS (payload phản chiếu từ request), stored XSS (payload được lưu và phát lại cho người khác) và DOM-based XSS (frontend tự đưa dữ liệu vào sink nguy hiểm).

Phản ví dụ Spring MVC:

```java
// KHÔNG dùng: dữ liệu chưa được encode bị nối thành HTML.
@GetMapping(value = "/welcome", produces = "text/html")
@ResponseBody
String welcome(@RequestParam String name) {
    return "<h1>Welcome " + name + "</h1>";
}
```

Nếu `name` chứa cú pháp HTML, browser sẽ phân tích chuỗi như markup. CSP đủ nghiêm ngặt có thể ngăn một số payload script nhưng **không được dùng làm lý do để giữ code nối HTML sai**. CSP có thể bị nới vì SDK, có script cùng origin bị lỗi, có những hành vi injection không biểu hiện thành inline JavaScript, hoặc browser khác nhau.

**Chặn XSS tại nơi xây output**: dùng template autoescape cho nội dung text, DOM text APIs trong frontend, HTML sanitizer khi thực sự cần rich text, và policy CSP như lớp phụ trợ.

### 3.1. Output phải được xử lý theo đúng context

| Vị trí dữ liệu | Cơ chế phù hợp | Sai lầm phổ biến |
| --- | --- | --- |
| HTML text node | Template autoescape / HTML text encoder | Nối raw input vào response HTML |
| HTML attribute đã quote | HTML attribute encoding từ template/API an toàn | Chèn input vào attribute không quote; event attribute |
| JavaScript string/data | Serializer/encoding đúng context, ưu tiên truyền JSON riêng | Dùng HTML escape rồi nối vào `<script>` |
| DOM text | `textContent`, `createTextNode` | `innerHTML`, `outerHTML` với raw user input |
| URL query component | URL builder và URI component encoding | Dùng HTML escape thay cho URL encoding |
| URL destination/redirect | Kiểm tra scheme, origin, host/path theo allowlist | Chỉ encode URL rồi tin mọi đích hợp lệ |
| CSS/style | Cấu trúc CSS cố định, allowlist giá trị | Cho user tạo `style`/`url(...)` tùy ý |
| Rich HTML | HTML parser sanitizer có allowlist tags, attributes, protocols | Dùng regex xóa `<script>` |
| SQL | Prepared statements / parameter binding | Escape HTML hoặc chặn dấu nháy để “chống SQLi” |
| File path | ID mapping, normalized path và quyền đọc file | Ghép raw filename vào thư mục gốc |

Không có một “hàm encode tổng quát” dùng cho mọi cột bảng trên. Hơn nữa, một số **ngữ cảnh nên tránh hoàn toàn** khi xử lý input không tin cậy: `onclick`, `onerror`, `<script>` chứa code ghép chuỗi, `javascript:` URL, `eval`, `document.write` hoặc CSS do user tự xây.

### 3.2. Stored XSS và dữ liệu từ database

Đừng đánh dấu dữ liệu là “đáng tin” chỉ vì nó đến từ database. User từng lưu một chuỗi ở endpoint khác, import batch từ đối tác, hoặc admin nhập HTML vào CMS. Khi trang khác dùng `th:utext`/`innerHTML` để hiển thị lại, XSS có thể xảy ra **nhiều ngày sau**. Cần encode ở **đúng lần xuất dữ liệu ra sink**, dù dữ liệu đến từ DB hay request.

## 4. Thymeleaf và Spring MVC: render escaped text

Với `spring-boot-starter-thymeleaf`, dạng phổ biến:

```html
<!-- src/main/resources/templates/profile.html -->
<section>
  <h1 th:text="${profile.displayName}">Tên hiển thị</h1>
  <p th:text="${profile.bio}">Tiểu sử</p>
</section>
```

`th:text` escape text thay vì render tag do dữ liệu sinh ra. Nếu `profile.displayName` là `<strong>Alice</strong>`, trang sẽ hiển thị các ký tự ấy như văn bản, không tạo tag `strong` mới do user chèn.

Mẫu **có rủi ro**:

```html
<!-- Không dùng với dữ liệu chưa sanitize -->
<div th:utext="${profile.bio}"></div>
```

`th:utext` cho phép unescaped HTML, vì vậy chỉ được dùng khi sản phẩm **có hợp đồng dữ liệu HTML** và đã sanitize theo allowlist phù hợp. `@Valid` hoặc CSP không tự xử lý nội dung này.

Ví dụ controller trong dự án Spring Boot MVC:

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class ProfilePageController {
    @GetMapping("/profile")
    String profile(Model model) {
        // Demo: ứng dụng thật cần lấy profile theo user
        // đã xác thực và đã kiểm tra quyền truy cập.
        model.addAttribute("profile",
            new ProfileView("Alice <Admin>", "My profile"));
        return "profile";
    }

    record ProfileView(String displayName, String bio) {}
}
```

Chính template `profile.html` thực hiện escaping. Nếu dùng `@RestController` trả HTML string trực tiếp, Thymeleaf **không tự chạy** để escape string.

### 4.1. Khi thật sự cần rich text

Nếu sản phẩm cho phép `<p>`, `<strong>`, links... trong bài viết, **sanitize HTML** bằng thư viện được thiết kế cho việc đó, thay vì tự viết regex.

Ví dụ Java sử dụng jsoup (cần dependency `org.jsoup:jsoup` tương ứng):

```java
import org.jsoup.Jsoup;
import org.jsoup.safety.Safelist;

public final class RichTextPolicy {
    private RichTextPolicy() {}

    public static String sanitize(String rawHtml) {
        return Jsoup.clean(rawHtml, Safelist.basic());
    }
}
```

`Safelist.basic()` chỉ là **minh họa**. Hãy chọn tags, attributes và URL protocols theo yêu cầu sản phẩm; cập nhật thư viện và kiểm thử HTML phức tạp, kể cả SVG, event attributes, malformed markup và các link scheme. Nếu đưa HTML đã sanitize vào **một context khác** như JavaScript/URL, nó lại cần kiểm soát theo context mới. Nếu chỉ cần hiển thị text thuần, **ưu tiên escaping, không dùng HTML sanitizer**.

Không coi `replace("<script>", "")` hay regex lọc chuỗi `onerror` là HTML sanitizer: browser parser có quá nhiều quy tắc và cú pháp thay thế.

## 5. Java 17 thuần: HTML text escaping có thể chạy trực tiếp

Chương trình này minh họa nguyên tắc: ký tự đặc biệt từ input sẽ thành HTML entities khi xuất vào **HTML text node**. Nó **không phải thư viện encoding production** và không dùng để escape JavaScript, CSS, URL hoặc HTML attribute có cấu trúc khác.

File `HtmlTextEscapeDemo.java`:

```java
public final class HtmlTextEscapeDemo {
    private static String htmlText(String value) {
        StringBuilder out = new StringBuilder();
        for (char ch : value.toCharArray()) {
            switch (ch) {
                case '&' -> out.append("&amp;");
                case '<' -> out.append("&lt;");
                case '>' -> out.append("&gt;");
                case '"' -> out.append("&quot;");
                case '\'' -> out.append("&#39;");
                default -> out.append(ch);
            }
        }
        return out.toString();
    }

    public static void main(String[] args) {
        String input = "<b>Alice & Bob</b> 'hello'";
        System.out.println("raw=" + input);
        System.out.println("htmlText=" + htmlText(input));
    }
}
```

Biên dịch/chạy:

```bash
javac HtmlTextEscapeDemo.java
java HtmlTextEscapeDemo
```

Stdout chính xác:

```text
raw=<b>Alice & Bob</b> 'hello'
htmlText=&lt;b&gt;Alice &amp; Bob&lt;/b&gt; &#39;hello&#39;
```

Trong HTML text, `&lt;b&gt;` hiển thị là các ký tự `<b>`, **không tạo tag HTML**. Nhưng nếu đưa chuỗi ấy vào JavaScript template, CSS, redirect hoặc SQL, độ an toàn **không được bảo đảm**.

Trong ứng dụng Java web thật, ưu tiên template autoescape hoặc thư viện chuyên biệt như **OWASP Java Encoder** với API phù hợp, chẳng hạn `Encode.forHtml(...)` cho HTML text, `Encode.forHtmlAttribute(...)` cho attribute và `Encode.forJavaScript(...)` cho một số JS contexts. Đây là API **thư viện ngoài**, không có sẵn trong JDK; cần chọn đúng hàm và đọc tài liệu context đích. Dù có encoder, không được coi việc chèn dữ liệu tùy ý vào `onclick` hoặc `eval` là thực hành an toàn.

## 6. JavaScript frontend: textContent thay vì innerHTML

Phản ví dụ DOM XSS:

```javascript
const name = new URLSearchParams(location.search)
  .get("name") ?? "";

// KHÔNG dùng: browser sẽ parse dữ liệu thành HTML.
document.querySelector("#welcome").innerHTML = name;
```

Cách hiển thị text:

```javascript
const name = new URLSearchParams(location.search)
  .get("name") ?? "";

// Hiển thị như text, không parse markup.
document.querySelector("#welcome").textContent = name;
```

Cùng nguyên lý: `document.createTextNode` hoặc interpolation mặc định có escaping của framework là lựa chọn tốt cho plain text. Không bật cơ chế unescaped HTML của framework khi không cần.

### 6.1. Dữ liệu JSON không phải HTML an toàn ở mọi nơi

API trả JSON thông qua serializer của Spring có thể tạo response JSON hợp lệ, nhưng frontend vẫn có thể gây XSS nếu viết:

```javascript
// PHẢN VÍ DỤ ngay cả khi profile đến từ JSON endpoint:
document.querySelector("#profile-name").innerHTML =
  profile.displayName;
```

Thay bằng:

```javascript
document.querySelector("#profile-name").textContent =
  String(profile.displayName ?? "");
```

Nếu nhúng JSON trực tiếp vào `<script>` trong HTML, phải có escaping **hiểu HTML script context**; chỉ gọi `JSON.stringify` rồi nối vào script element không phải giải pháp phổ quát. Có thể ưu tiên endpoint `application/json` riêng, `fetch` và render text bằng DOM API.

### 6.2. Attribute href cần xác minh URL

`element.setAttribute("href", value)` hoặc `link.href = value` không tự kết luận URL an toàn. `javascript:`, cross-origin phishing links hoặc redirect target không mong muốn là **vấn đề semantics**, không giải quyết chỉ bằng HTML escaping.

Ví dụ chỉ cho phép link cùng HTTPS origin:

```javascript
function allowedLocalUrl(raw) {
  try {
    const u = new URL(raw, location.origin);
    return u.protocol === "https:" &&
           u.origin === location.origin;
  } catch {
    return false;
  }
}
```

Đây chỉ là policy minh họa cho website đang chạy HTTPS, không phải URL sanitizer tổng quát. Nếu cho link đến domain khác, cần allowlist scheme/origin, xử lý redirect và domain tương đồng. Không sử dụng `endsWith("example.com")` một cách mơ hồ để kiểm hostname.

## 7. Input validation: đúng hợp đồng và đúng ngữ nghĩa

**Input validation** giúp loại dữ liệu không được ứng dụng chấp nhận, nhưng không thay escaping.

Những nhóm kiểm tra:

- **Schema/kiểu:** body JSON đúng kiểu, các trường required, số/ngày/enum hợp lệ.
- **Size/range:** độ dài tên, số lượng items, giới hạn file upload, page size, request body size.
- **Ngữ nghĩa nghiệp vụ:** số tiền dương, order status đúng chuyển tiếp, ngày bắt đầu trước ngày kết thúc.
- **Quan hệ/ủy quyền:** caller được sửa chính order/profile/tenant đó không.
- **Allowlist giá trị điều khiển cấu trúc:** tên sort key, lựa chọn file type, redirect target, template name.
- **Canonicalization có chủ đích:** Unicode, domain/URL và filesystem paths cần được chuẩn hóa/kiểm tra đúng lớp; tránh các tầng decode không nhất quán.

Không nên cấm global mọi dấu `<`, `>`, `'` hoặc `;`. Một tên hiển thị hoặc bài viết hợp lệ có thể chứa các ký tự đó. Nếu contract cho phép, hãy **lưu dữ liệu đúng nghĩa và escape khi render**.

### 7.1. Spring Boot DTO với Jakarta Validation

Ví dụ Java 17 record `ProfileRequest.java`:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record ProfileRequest(
    @NotBlank
    @Size(max = 80)
    String displayName,

    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9_-]{3,32}")
    String handle
) {}
```

Endpoint minh họa:

```java
import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileApiController {
    @PostMapping("/api/profile")
    ResponseEntity<Map<String, String>> update(
            @Valid @RequestBody ProfileRequest request) {

        // App thật phải xác thực quyền sửa profile,
        // kiểm tra unique handle, persist và audit.
        return ResponseEntity.ok(Map.of(
            "displayName", request.displayName(),
            "handle", request.handle()));
    }
}
```

Cần `spring-boot-starter-web` và `spring-boot-starter-validation` hoặc dependencies tương đương. `@Valid` kiểm các annotation constraint; không tự xác định quyền sửa user khác, không escape HTML và không ngăn SQL injection trong service. `displayName` có thể chứa `<b>` vì chỉ bị giới hạn length; **vẫn an toàn nếu frontend/template hiển thị bằng text APIs đúng**.

**Validation và authorization là hai lớp khác:** ID `123` hợp lệ theo pattern nhưng caller chưa chắc có quyền truy cập resource 123. Backend phải kiểm tra ownership và tenant boundary.

## 8. SQL injection: parameterized query

HTTP headers không sửa được code SQL backend. Phản ví dụ:

```java
// KHÔNG dùng: user input bị nối thành cấu trúc SQL.
String sql = "SELECT id FROM accounts WHERE handle = '" +
             handle + "'";
```

Dùng binding:

```java
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;

public final class AccountLookup {
    private final JdbcTemplate jdbc;

    public AccountLookup(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Long> findIds(String handle) {
        return jdbc.queryForList(
            "SELECT id FROM accounts WHERE handle = ?",
            Long.class,
            handle
        );
    }
}
```

Đây là class trong Spring application có `spring-jdbc`, datasource và schema phù hợp. `?` dùng cho **giá trị**, giữ data khỏi cấu trúc SQL. Không áp `HTML escape` vào giá trị để chống SQL injection.

Với tên cột/table hay `ORDER BY`, placeholder thường không dùng để thay SQL identifiers: hãy map key user nhập sang literals được phép trong code.

```java
static String sortableColumn(String key) {
    return switch (key) {
        case "created" -> "created_at";
        case "name" -> "display_name";
        default -> throw new IllegalArgumentException("Unknown sort key");
    };
}
```

Không nối trực tiếp `sortColumn` từ request.

## 9. HTML sanitizer, path traversal, redirects và uploads

### 9.1. Sanitization khác encoding

- **Encoding:** giữ dữ liệu thành text thay vì code trong context output.
- **Sanitization:** khi business cần HTML thực, cho phép subset tag/attribute/protocol sau khi parse và làm sạch.
- **Validation:** loại dữ liệu không hợp lệ theo contract, không phải phép biến đổi HTML.
- **Authorization:** quyết định user nào được tác động vào resource nào.

Ví dụ cần hiển thị Markdown do người dùng soạn: có thể parse Markdown bằng thư viện phù hợp, tạo HTML rồi **sanitize output HTML** và render trong bề mặt được thiết kế cho rich text. Đừng chỉ chạy regex xóa `<script>`.

### 9.2. File upload

`nosniff` không đủ để an toàn khi upload. Cần hạn chế kích thước, loại file, scan/parse khi cần, kiểm tra bytes/content thay vì chỉ tin extension/MIME do client khai báo, dùng tên file server-generated, lưu ngoài thư mục thực thi, phân quyền download và phục vụ với Content-Type/Content-Disposition phù hợp. Ảnh/file từ user nếu cùng origin và bị phục vụ như active HTML có thể gây rủi ro dù hệ thống đã có CSP.

### 9.3. Path traversal

Không biến `?file=../../secret` thành path bằng cách nối string. Dùng resource ID do server quản lý, chuẩn hóa path và kiểm tra nó thuộc directory/tenant cho phép; cân nhắc symbolic links, encoded separators và cách normalize của proxy/container. CSP/HSTS không bảo vệ filesystem.

### 9.4. Open redirect

Đầu vào `next=https://attacker.example.test` không nên đi thẳng tới HTTP `Location`. Chỉ cho redirect tương đối có kiểm tra hoặc exact allowlist scheme/host/path. HTML escaping cho parameter `next` không tự bảo đảm đích redirect hợp lệ.

### 9.5. SSRF và shell injection

- SSRF: service tự gọi URL do client cung cấp; cần hạn chế đích, DNS/IP, redirects và egress network.
- Shell injection: ưu tiên API lập trình thay vì shell; nếu bắt buộc gọi process, dùng arguments được kiểm soát, không xây command shell từ raw user input.

Đó là các **sinks backend**; security headers của response không bảo vệ chúng.

## 10. Cấu hình HTTP headers trong Spring Security Servlet

Spring Security có những headers mặc định hữu ích như `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, cache-control cho response động và HSTS đối với HTTPS khi tương ứng. **CSP không tự được Spring Security tạo chỉ từ dependency.** Bộ header cuối cùng phụ thuộc phiên bản, filter chain và cấu hình của ứng dụng/edge.

File `WebSecurityConfig.java` trong Spring Boot 3 / Spring Security 6:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; " +
                        "script-src 'self'; " +
                        "object-src 'none'; " +
                        "base-uri 'self'; " +
                        "frame-ancestors 'none'"))
                .referrerPolicy(ref -> ref
                    .policy(ReferrerPolicyHeaderWriter.ReferrerPolicy
                        .STRICT_ORIGIN_WHEN_CROSS_ORIGIN))
                .frameOptions(frame -> frame.deny()));
        return http.build();
    }
}
```

Đây là cấu hình có thể dùng **trong project Spring Boot hoàn chỉnh**, không phải file Java thuần chạy bằng `javac` khi thiếu dependencies. Các điểm cần hiểu:

1. `permitAll()` vẫn đi qua security filter chain và các headers; `web.ignoring()` có thể bỏ qua các filters/headers của Spring Security.
2. CSP này là baseline ví dụ: nguồn script cho phép cùng origin, `object-src 'none'` cấm một số plugin objects, `base-uri 'self'` giới hạn base URL, `frame-ancestors 'none'` không cho nhúng frame. Sản phẩm có resources khác phải thiết kế policy theo thực tế.
3. Đừng copy CSP quá cứng khiến ứng dụng hỏng rồi bật `'unsafe-inline'`/`'unsafe-eval'` rộng. Xử lý code/templates gây vi phạm và nới có kiểm soát.
4. `X-Frame-Options` và `frame-ancestors` có thể bổ sung nhau cho các browser khác nhau.
5. HSTS do Spring Security ghi khi request được xem là HTTPS; không kỳ vọng nó xuất hiện trong mọi request HTTP.
6. **Không có dòng nào trong bean trên tự escape dữ liệu trong HTML/JavaScript hoặc validate request DTO.**

### 10.1. CSP có lợi nhưng không thay output encoding

Một CSP tốt có thể chặn nhiều injected inline scripts. Tuy nhiên:
- Script được phép từ cùng origin vẫn có thể mang DOM XSS.
- CSP bị nới bằng `unsafe-inline`/`unsafe-eval` có thể giảm hiệu quả.
- Nonce/hash là kỹ thuật hữu ích nếu triển khai đúng: nonce phải ngẫu nhiên, phù hợp theo từng response, không hardcode cố định.
- Những chính sách nâng cao như `strict-dynamic` hoặc Trusted Types cần kiểm tra browser support, kiến trúc script và thư viện UI.
- CSP report-only giúp đo violation khi rollout nhưng **không chặn**; thiếu violation reports không phải chứng nhận ứng dụng không có XSS.

Ưu tiên sửa input-to-output flow và frontend sinks ngay cả khi CSP đang hoạt động.

### 10.2. HSTS và môi trường proxy

Nếu TLS kết thúc ở reverse proxy, việc Spring Security nhận dạng secure request và phát HSTS phụ thuộc cấu hình forwarded headers/proxy tin cậy. Không cho client tự điều khiển `X-Forwarded-Proto`/`Forwarded` rồi backend tin vô điều kiện. HSTS bảo vệ transport ở browser, không thay TLS cấu hình đúng ở biên.

### 10.3. CORS và CSRF

CORS không phải authorization; server vẫn phải bảo vệ từng resource. Nếu browser tự gửi credential qua cookie/session/HTTP Basic, cần đánh giá CSRF ngay cả khi có CSP hay HSTS. Với API chỉ nhận bearer token trong header do client gửi chủ động, threat model CSRF khác; quyết định theo **cách credential được chấp nhận**, không dựa vào việc API có JSON hay không.

## 11. Kiểm thử các lớp bảo vệ

### 11.1. MockMvc kiểm tra response headers

Một endpoint demo:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }
}
```

Test `SecurityHeadersTest.java` trong Spring Boot project với `spring-boot-starter-test` và security filters:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeadersTest {
    @Autowired
    MockMvc mvc;

    @Test
    void publicPageHasSecurityHeaders() throws Exception {
        mvc.perform(get("/public/ping").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(header().string(
                "X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                containsString("object-src 'none'")))
            .andExpect(header().string(
                HttpHeaders.STRICT_TRANSPORT_SECURITY,
                containsString("max-age=")));
    }
}
```

`secure(true)` mô phỏng HTTPS request để kiểm tra HSTS. Test này **chỉ chứng minh header có mặt** trong môi trường test, không chứng minh toàn ứng dụng không có XSS/SQLi/IDOR.

Lệnh:

```bash
mvn -Dtest=SecurityHeadersTest test
# Với Gradle project tương ứng:
./gradlew test --tests SecurityHeadersTest
```

### 11.2. Test XSS ở output thực

Dùng các giá trị như `<b>Alice</b>`, chuỗi chứa quotes/ampersands, Unicode và markup không mong muốn. Render trang bằng template thật, rồi kiểm tra chuỗi được hiển thị như text, không tạo node HTML do user điều khiển. Với frontend, component test cần xác nhận dùng `textContent`/escaped interpolation, không phải `innerHTML`.

Nếu sản phẩm hỗ trợ rich HTML, test sanitize cho tags/attributes/protocols được phép và bị từ chối. Không coi “CSP đã có” là kết quả test escaping.

### 11.3. Test validation, SQL, quyền

- `displayName` rỗng/quá dài và `handle` sai regex phải bị từ chối theo DTO.
- `handle` chứa quote phải không làm thay đổi cấu trúc SQL khi dùng parameter binding.
- Caller được xác thực nhưng sửa `userId` của người khác phải bị từ chối qua authorization/ownership.
- URL redirect ngoài allowlist và file path ra khỏi root phải bị từ chối.
- File upload size/type không hợp lệ phải được xử lý đúng.
- Trang/endpoint chứa dữ liệu cá nhân nên có `no-store` theo chính sách, nhưng vẫn cần quyền truy cập.

### 11.4. Ma trận kiểm tra

| Trường hợp | Lớp bảo vệ phải kiểm chứng |
| --- | --- |
| Browser nhận CSP sai hoặc không có | Header integration test |
| User input xuất vào HTML text | Template escaping |
| User input xuất vào HTML attribute | Attribute encoding và URL validation phù hợp |
| URL query được gán cho `innerHTML` | DOM sink review/test; dùng `textContent` |
| Rich HTML chứa event handlers | Sanitizer allowlist |
| JavaScript data được nhúng vào script element | Context-aware serialization/escaping hoặc JSON endpoint |
| SQL chứa ký tự điều khiển/quote | Prepared statements và business validation |
| Dynamic sort column | Server allowlist mapping |
| Profile ID thuộc tenant khác | Authorization/ownership tests |
| Upload file MIME giả | File validation, isolation, headers đúng |
| Redirect tới domain attacker | Redirect allowlist |
| Cookie-authenticated unsafe POST | CSRF protection |
| Asset công khai và API riêng | Cache policy theo độ nhạy |
| Response qua CDN/reverse proxy | Final headers và cache behavior trên đường thực |

## 12. Lỗi triển khai thường gặp

1. **“CSP đã bật nên không cần escape.”** Sai: CSP là lớp giảm thiểu, không làm code chèn raw HTML trở nên đúng.
2. **“@Valid đã chống XSS.”** Sai: dữ liệu hợp lệ nghiệp vụ vẫn phải encode khi render.
3. **“Xóa `<script>` bằng regex là sanitizer.”** Sai: HTML parsing và DOM sinks phức tạp.
4. **“Escape một lần khi nhận rồi lưu DB.”** Dễ double-encode và sai khi dữ liệu dùng ở nhiều contexts. Encode khi xuất theo context.
5. **“HTML escape đủ cho JavaScript/URL/SQL.”** Sai: mỗi sink có semantics khác.
6. **“JSON serializer tự chống DOM XSS.”** Sai nếu frontend đặt JSON value vào `innerHTML`.
7. **“nosniff thay file upload validation.”** Sai: còn cần content checks, filenames, storage, authorization.
8. **“CORS thay authentication/CSRF.”** Sai: CORS không phải access control backend.
9. **“HSTS chống SQL injection.”** Sai: HSTS là transport policy của browser.
10. **“'self' nghĩa mọi script cùng origin đều an toàn.”** Sai: script cùng origin có thể tồn tại lỗ hổng.
11. **“Header đầy đủ thì endpoint không thể lộ dữ liệu người khác.”** Sai: lỗi authorization vẫn lộ dữ liệu.
12. **“Không có CSP report thì không có XSS.”** Sai: violation reporting không thay code review và tests.
13. **“Tắt security filter chain cho static assets để cache.”** Có thể mất headers; tinh chỉnh cache policy theo phạm vi thay vì bỏ toàn bộ chain.
14. **“Chỉ test 200 là đủ.”** Phải test headers, rendering, rejected inputs và quyền theo tài nguyên.

## 13. Checklist cuối bài

- [ ] Phân biệt HTTP security headers với validation, authorization và output encoding.
- [ ] Bật headers phù hợp trong Spring Security Servlet và kiểm tra response cuối qua proxy/CDN.
- [ ] Thiết kế CSP theo nguồn tài nguyên thật; không mặc định bật `unsafe-inline` rộng.
- [ ] HTML/Thymeleaf dùng autoescape (`th:text`), không dùng `th:utext` với raw input.
- [ ] Frontend dùng `textContent` hoặc escaped interpolation; hạn chế `innerHTML`/`eval`.
- [ ] Rich HTML được xử lý bằng sanitizer có allowlist, không dùng regex.
- [ ] Đúng encoder theo HTML text/attribute, JavaScript, URL; tránh các context vốn nguy hiểm.
- [ ] DTO có schema/type/size/business validation; không cấm ký tự toàn cục thay cho escaping.
- [ ] SQL dùng parameter binding, sort/identifiers map từ server-side allowlist.
- [ ] File/redirect/URL/SSRF được kiểm tra tại sink backend tương ứng.
- [ ] Backend xác thực quyền và object ownership độc lập với headers.
- [ ] CORS, cookie, session và CSRF được đánh giá theo credential gửi thực tế.
- [ ] Có test header **và** test output/input/authorization; không coi một test header là đủ.
- [ ] Không đưa secret, raw bearer token hay dữ liệu cá nhân vào URL hoặc log.

**Kết luận:** Spring Security giúp phát HTTP security headers hữu ích như CSP, `nosniff`, HSTS và frame policy, nhưng **không mã hóa đầu ra thay cho ứng dụng và không kiểm tra dữ liệu nghiệp vụ thay cho service**. Cách bảo vệ đúng là **validation theo hợp đồng → authentication/authorization đúng tài nguyên → safe APIs → output encoding theo ngữ cảnh → security headers defense in depth**, với kiểm thử ở từng lớp.
