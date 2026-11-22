# Content-Security-Policy: nguồn tài nguyên, nonce và chế độ báo cáo trong Spring Security Servlet

## 1. CSP giải quyết vấn đề gì?

**Content Security Policy (CSP)** là cơ chế bảo mật của trình duyệt, được website công bố chủ yếu qua HTTP **response header** `Content-Security-Policy`. Chính sách cho biết trình duyệt được phép tải hoặc thực thi những loại tài nguyên nào: JavaScript, CSS, hình ảnh, font, kết nối `fetch`, iframe, v.v. CSP cũng có thể giới hạn việc nhúng trang trong frame, đích gửi form và quyền sử dụng `<base>`.

Ví dụ: ứng dụng có điểm nhập liệu cho phép hiển thị lời bình. Nếu kẻ tấn công chèn được nội dung dạng `<script>...</script>` và dữ liệu đó bị render sai thành HTML thực thi, **CSP có thể chặn một số đường thực thi script trái phép**. Cơ chế này là **defense in depth** chống các hậu quả của XSS, tải script độc hại và những dạng chèn tài nguyên. Vẫn phải encode/escape dữ liệu theo ngữ cảnh, kiểm tra input, bảo vệ template và tránh DOM XSS; CSP không thay thế các biện pháp đó.

Một response HTML có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html;charset=UTF-8
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Ý nghĩa: phần lớn loại tài nguyên mặc định chỉ lấy từ **cùng origin**; script chỉ được tải từ cùng origin; không cho plugin object; giới hạn `<base>` và cấm site khác nhúng trang trong frame. Browser tự kiểm tra và chặn những thao tác không thỏa mãn chính sách.

Bài này tập trung vào ba kỹ năng: **chọn nguồn tài nguyên đúng theo directive**, **cấp nonce ngẫu nhiên cho script inline hợp lệ**, và **sử dụng chế độ Report-Only để quan sát vi phạm trước khi cưỡng chế**. Ví dụ nằm trong **Spring Security Servlet / Spring MVC**, khác với cấu hình Reactive WebFlux.

## 2. CSP được browser xử lý ở đâu?

CSP được áp dụng chủ yếu dựa trên **response** chứa tài liệu, không phải dựa trên việc người dùng đã xác thực hay chưa. Với một trang HTML:

~~~text
Browser GET /demo
      |
      v
Servlet filters / Spring Security
      |
      v
Spring MVC controller + template
      |
      v
HTML response + Content-Security-Policy header
      |
      v
Browser lưu policy áp dụng cho document
      |
      +-- Tải <script src="...">? Kiểm tra script-src
      +-- Thực thi <script> inline? Kiểm tra nonce/hash/script-src
      +-- Tải CSS? Kiểm tra style-src
      +-- fetch("...")? Kiểm tra connect-src
      +-- Hiển thị ảnh/font? Kiểm tra img-src/font-src
      +-- Chèn document vào iframe? Kiểm tra frame-ancestors
~~~

**Authentication/authorization** ở server quyết định người gọi có được truy cập endpoint hay không. **CORS** quyết định JavaScript từ một origin khác có thể truy cập response cross-origin trong phạm vi browser hay không. **CSP** quyết định một document được phép tải hoặc thực thi nội dung từ những nguồn nào. Một endpoint có thể trả 200, CORS đúng nhưng script vẫn bị CSP chặn; ngược lại, CSP cho phép `fetch` đến URL khác cũng **không** vượt qua CORS.

Chính sách có thể được khai báo bằng `<meta http-equiv="Content-Security-Policy" ...>`, nhưng cách này có giới hạn, bao gồm **không hỗ trợ Report-Only** và **không áp dụng `frame-ancestors`**. Với ứng dụng Servlet, ưu tiên **HTTP header** trả từ server/gateway. Nếu nhiều response header CSP bắt buộc được gửi, browser áp dụng **tất cả** các policy cưỡng chế; một policy rộng hơn không tự nới policy chặt hơn.

## 3. Cú pháp: directive và source expression

CSP là danh sách directive, cách nhau bằng dấu `;`. Mỗi directive có tên và những nguồn hợp lệ cho nhóm tài nguyên tương ứng:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' https://static.example.com; img-src 'self' data:; object-src 'none'
~~~

Các **source expression** thường gặp:

| Giá trị | Ý nghĩa và lưu ý |
| --- | --- |
| `'self'` | Cùng origin với document (scheme, host, port theo quy tắc CSP); không phải mọi subdomain hoặc mọi port. |
| `'none'` | Không cho nguồn nào đối với directive đó; dùng riêng thay vì ghép với những nguồn được phép. |
| `https://cdn.example.com` | Cho phép nguồn xác định từ HTTPS; vẫn phải đánh giá độ tin cậy và nội dung từ CDN. |
| `https:` | Cho phép nguồn theo scheme HTTPS, phạm vi rộng hơn nhiều so với một hostname cụ thể. |
| `data:` | Cho phép data URL; thường được cân nhắc cho ảnh, nhưng rất nguy hiểm nếu mở rộng bừa cho script. |
| `blob:` | Cho phép blob URL trong phạm vi directive có hỗ trợ; cân nhắc worker, media và mã động. |
| `*` | Wildcard rộng, thường làm yếu CSP. Không dùng để khắc phục lỗi khi chưa xác định nguồn. |
| `'nonce-BASE64'` | Cho phép phần tử inline có nonce khớp giá trị trong header; giá trị thay đổi mỗi response. |
| `'sha256-BASE64'` | Cho phép nội dung inline có hash khớp chính xác bytes nội dung được hash theo quy tắc CSP. |
| `'unsafe-inline'` | Mở đường thực thi inline không an toàn trong những chính sách/cơ chế tương ứng; tránh dùng làm lối tắt. |
| `'strict-dynamic'` | Tùy browser/chính sách, cho phép tin cậy script do script có nonce/hash hợp lệ tải động; cần thử tương thích và hiểu hệ quả tin cậy lan truyền. |

Các keyword source như `'self'`, `'none'` và `'nonce-...'` **cần dấu nháy đơn** trong header. Tên hostname, scheme như `https:` hoặc `data:` không dùng dấu nháy đơn.

Một nonce hoặc hash áp dụng cho script/style inline theo directive liên quan, **không** phải giấy phép cho mọi loại nội dung hay mọi API. Header CSP là chính sách do browser thực thi; nó không phải header `Authorization` và không được kiểm tra như token đăng nhập tại controller.

## 4. Những directive cần biết khi bảo vệ HTTP

| Directive | Điều chỉnh | Ví dụ |
| --- | --- | --- |
| `default-src` | Nguồn dự phòng cho nhiều loại resource-fetch khi thiếu directive chuyên biệt. | `default-src 'self'` |
| `script-src` | Nguồn script, inline script, một số hành vi JavaScript; liên quan `script-src-elem`, `script-src-attr`. | `script-src 'self' 'nonce-...'` |
| `script-src-elem` | Kiểm soát phần tử `<script>`; nếu vắng có cơ chế fallback sang `script-src` rồi `default-src`. | `script-src-elem 'self'` |
| `script-src-attr` | Kiểm soát inline event handler như `onclick`; cấu hình để chặn thuộc tính handler. | `script-src-attr 'none'` |
| `style-src` | Nguồn stylesheet và kiểu inline; có `style-src-elem` / `style-src-attr`. | `style-src 'self'` |
| `img-src` | Ảnh từ URL hoặc `data:` khi được cho phép. | `img-src 'self' data:` |
| `font-src` | Font qua CSS, ví dụ `@font-face`. | `font-src 'self'` |
| `connect-src` | Kết nối từ JS: `fetch`, XMLHttpRequest, WebSocket, EventSource... | `connect-src 'self' https://api.example.com` |
| `frame-src` | Nguồn của frame/iframe mà trang hiện tại **tải vào**. | `frame-src https://player.example.com` |
| `frame-ancestors` | Những origin nào được **nhúng trang hiện tại vào frame**. | `frame-ancestors 'none'` |
| `object-src` | Tài nguyên plugin như `<object>` và `<embed>`. | `object-src 'none'` |
| `base-uri` | Những URL được dùng bởi phần tử `<base>`. | `base-uri 'self'` |
| `form-action` | Những URL form của trang được phép gửi đến. | `form-action 'self'` |
| `worker-src` | Nguồn của Worker/Service Worker tùy cơ chế fallback. | `worker-src 'self'` |
| `report-uri`, `report-to` | Cấu hình nơi browser có thể gửi CSP violation report. | `report-uri /csp-report` |

**Fallback cần hiểu đúng:** Nếu thiếu `img-src`, browser có thể dùng `default-src` để kiểm nguồn ảnh. Nếu thiếu `script-src-elem`, browser tìm `script-src` rồi đến `default-src`. Nhưng `frame-ancestors`, `form-action` và `base-uri` **không đơn giản kế thừa `default-src`**; cần khai báo rõ nếu muốn giới hạn các hành vi đó.

So sánh hai directive dễ nhầm:

- `frame-src`: trang **của bạn được nhúng nội dung của ai**.
- `frame-ancestors`: **ai được nhúng trang của bạn**. Đây là biện pháp giúp chống clickjacking, có quan hệ với `X-Frame-Options` nhưng CSP `frame-ancestors` linh hoạt hơn.

Ví dụ trang web tải JavaScript từ same-origin, ảnh ở CDN, gọi API ở domain riêng:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https://images.example.com; connect-src 'self' https://api.example.com; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

`connect-src https://api.example.com` cho browser **thử** kết nối từ document. Nếu API khác origin, API vẫn phải đáp ứng **CORS** phù hợp. CSP cho phép nguồn kết nối không tự bảo đảm request có quyền hoặc được server chấp nhận.

## 5. CSP của Spring Security mặc định và cấu hình policy tĩnh

Trong Spring Security Servlet, các response header bảo mật cơ bản được bật theo mặc định, nhưng **CSP không tự động được bật với một policy phù hợp mọi ứng dụng**. Lập trình viên cần xác định nguồn script, CSS, CDN, API... trước khi khai báo.

Với trang chỉ dùng JavaScript/CSS ngoài từ cùng origin, một cấu hình tĩnh bằng `HttpSecurity` có thể như sau. Đây là **mảnh cấu hình nằm trong phương thức tạo SecurityFilterChain**, không phải chương trình Java độc lập:

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; " +
            "script-src 'self'; " +
            "style-src 'self'; " +
            "img-src 'self'; " +
            "object-src 'none'; " +
            "base-uri 'self'; " +
            "frame-ancestors 'none'"
        )
    )
);
~~~

Spring Security tích hợp CSP thông qua cơ chế **response header writer**. Với policy tĩnh, đây là cách đơn giản. Có thể cấu hình chế độ chỉ báo cáo bằng `.reportOnly()` trên CSP DSL tương ứng, ví dụ:

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("default-src 'self'; script-src 'self'; report-uri /csp-report")
        .reportOnly()
    )
);
~~~

Ở chế độ đó, response sử dụng `Content-Security-Policy-Report-Only`. Mặc định, ví dụ bài này sẽ minh họa **nonce thay đổi theo từng response**, nên một chuỗi tĩnh trong `policyDirectives` là **không đủ**. Đặc biệt, không được tạo một nonce một lần khi khởi động app rồi tái sử dụng mãi trong cấu hình tĩnh.

Nếu đã tạo CSP bằng header writer hoặc gateway, cần kiểm tra **có bao nhiêu policy thực sự được gửi**. Các enforced policy độc lập được áp dụng đồng thời, nên một policy thứ hai có thể tiếp tục chặn script dù policy thứ nhất đã cho phép nonce. Tránh tự gọi `setHeader` ở filter đồng thời khai báo một policy mâu thuẫn trong Spring Security.

## 6. Nonce là gì và khi nào cần dùng?

Nonce là **number used once**: giá trị đủ ngẫu nhiên, khó dự đoán, được server tạo **mới cho từng HTTP response HTML**, đưa vào hai nơi:

1. Trong CSP header, chẳng hạn `script-src 'self' 'nonce-f8Wm...'`.
2. Trong thuộc tính `nonce` của **đúng phần tử `<script>` hoặc `<style>` được phép chạy**.

Ví dụ minh họa (nonce bên dưới chỉ là mẫu, không dùng làm mã thực tế):

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-WjRrMkVzbmZTaW53U3pvaA=='; object-src 'none'
~~~

~~~html
<script nonce="WjRrMkVzbmZTaW53U3pvaA==">
  document.getElementById("status").textContent = "Allowed by nonce";
</script>
<script>
  console.log("Without nonce: blocked in enforcement mode");
</script>
~~~

Theo policy này, browser có thể chạy script đầu và chặn script thứ hai. Nonce không thể dựa vào tên đăng nhập, ngày tháng, ID của phiên hoặc chuỗi cố định. Cách tạo thực tế là lấy **ít nhất 128 bit ngẫu nhiên bằng bộ sinh ngẫu nhiên mật mã**, rồi mã hóa Base64; ví dụ `SecureRandom` trong Java.

**Nonce không giống CSRF token.** CSRF token xác minh yêu cầu thay đổi dữ liệu trong một số mô hình xác thực; CSP nonce xác định phần tử script/style inline được tác giả document cho phép. Nonce cũng không phải mã bí mật để cấp quyền truy cập API.

Một số chi tiết cần biết:

- Nonce chỉ có ích khi server kiểm soát việc tạo nonce **và** gắn đúng nonce vào các script/style được tin cậy; không gắn nonce cho HTML do người dùng nhập hoặc script không đáng tin.
- Inline event handler như `onclick="..." `, URL `javascript:` và `eval(...)` không tự được phép chỉ vì một script tag trên trang có nonce. Chuyển event handler sang `addEventListener`.
- Nếu không cần script inline, ưu tiên chuyển JavaScript sang file tĩnh và dùng policy `script-src 'self'`; không cần nonce trong mọi ứng dụng SPA.
- Khi dùng hash, **thay đổi dù chỉ một ký tự nội dung script** có thể làm hash không khớp; hash thích hợp với đoạn inline cố định, nonce hợp với template SSR phát sinh nội dung.
- Không nhúng dữ liệu không tin cậy vào vị trí thuộc tính có khả năng làm thay đổi markup/tag; auto-escaping và output encoding đúng ngữ cảnh vẫn rất quan trọng.
- Nonce không phải cách bảo vệ chống mọi XSS: nếu có mã JavaScript độc hại đã chạy trong origin hoặc một trusted script bị lợi dụng, vẫn có đường tấn công. Cân nhắc CSP chặt hơn, `'strict-dynamic'`, Trusted Types và kiểm soát thư viện nếu threat model yêu cầu.

Với HTML động chứa nonce, **không cache công khai một response có nonce rồi dùng lại cho nhiều người dùng hoặc nhiều lần truy cập**. Cần chính sách cache phù hợp; ví dụ dùng `Cache-Control: no-store` cho trang demo.

## 7. Ví dụ chạy được: Spring Boot 3, Java 17 và nonce theo response

Ta sẽ tạo một trang `GET /demo` render bằng Thymeleaf và một endpoint `POST /csp-report` nhận báo cáo vi phạm. Server:

- Tạo 16 byte bằng `SecureRandom` khi xử lý mỗi response HTML, encode Base64 thành nonce.
- Đặt nonce vào **request attribute**, rồi controller truyền vào template.
- Đặt CSP header chứa **cùng nonce** trước khi render HTML.
- Cho phép `script-src 'self'` và `nonce` cho script inline được tin cậy, chặn `object-src`, giới hạn `base-uri` và `frame-ancestors`.
- Chuyển giữa **enforce** và **report-only** bằng property `demo.csp.report-only`.
- Giữ Spring Security và CSRF mặc định cho các endpoint khác; riêng **endpoint báo cáo** được miễn CSRF vì bản tin browser gửi không mang CSRF token của biểu mẫu ứng dụng.

Cấu trúc:

~~~text
csp-nonce-demo/
├── pom.xml
├── src/main/java/example/csp/CspDemoApplication.java
├── src/main/resources/templates/demo.html
└── src/test/java/example/csp/CspDemoApplicationTests.java
~~~

### 7.1. Maven và JDK

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>csp-nonce-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.2. Servlet filter, security chain và controller

**src/main/java/example/csp/CspDemoApplication.java**:

~~~java
package example.csp;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.security.SecureRandom;
import java.util.Base64;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class CspDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CspDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/demo", "/csp-report").permitAll()
                        .anyRequest().authenticated())
                .csrf(csrf -> csrf.ignoringRequestMatchers("/csp-report"))
                .build();
    }

    @Bean
    FilterRegistrationBean<NonceCspFilter> nonceCspFilter(Environment env) {
        boolean reportOnly =
                env.getProperty("demo.csp.report-only", Boolean.class, false);

        FilterRegistrationBean<NonceCspFilter> registration =
                new FilterRegistrationBean<>(new NonceCspFilter(reportOnly));

        // Chỉ đặt CSP cho trang HTML /demo của bài thực hành.
        registration.addUrlPatterns("/demo");

        // Chạy sớm để controller thấy nonce và header có trước response.
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }

    @Controller
    static class DemoController {

        @GetMapping("/demo")
        String demo(HttpServletRequest request, Model model) {
            model.addAttribute("cspNonce", request.getAttribute("cspNonce"));
            return "demo";
        }

        @PostMapping("/csp-report")
        ResponseEntity<Void> receiveReport() {
            // Demo chủ động bỏ nội dung report; hệ thống thật cần
            // xử lý/rate-limit/lược bỏ dữ liệu nhạy cảm.
            return ResponseEntity.noContent().build();
        }
    }

    static final class NonceCspFilter extends OncePerRequestFilter {
        private final SecureRandom random = new SecureRandom();
        private final boolean reportOnly;

        NonceCspFilter(boolean reportOnly) {
            this.reportOnly = reportOnly;
        }

        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain filterChain
        ) throws ServletException, IOException {
            byte[] bytes = new byte[16]; // 128 bit
            random.nextBytes(bytes);
            String nonce = Base64.getEncoder().encodeToString(bytes);

            request.setAttribute("cspNonce", nonce);

            String policy =
                    "default-src 'self'; " +
                    "script-src 'self' 'nonce-" + nonce + "'; " +
                    "script-src-attr 'none'; " +
                    "style-src 'self'; " +
                    "img-src 'self' data:; " +
                    "connect-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "form-action 'self'; " +
                    "frame-ancestors 'none'; " +
                    "report-uri /csp-report";

            String headerName = reportOnly
                    ? "Content-Security-Policy-Report-Only"
                    : "Content-Security-Policy";

            response.setHeader(headerName, policy);
            response.setHeader("Cache-Control", "no-store");
            filterChain.doFilter(request, response);
        }
    }
}
~~~

Lưu ý:

1. `NonceCspFilter` là **Servlet filter** chạy trước controller; `FilterRegistrationBean` đăng ký filter riêng cho URL `/demo`. `Ordered.HIGHEST_PRECEDENCE` giúp filter chạy sớm trong servlet chain. Các filter của Spring Security vẫn xử lý xác thực và phân quyền như thường lệ.
2. Spring Security **không tự cung cấp API nonce động cho template** chỉ bằng cách viết một `policyDirectives(...)` tĩnh. Ở đây custom filter đặt header và request attribute rồi Thymeleaf lấy đúng nonce. Trong ứng dụng thật có nhiều trang, có thể thiết kế thành phần nonce/header dùng chung hoặc một `HeaderWriter` kết hợp filter tạo nonce.
3. Trong ví dụ **không** khai báo thêm CSP bằng `http.headers(...contentSecurityPolicy(...))` để tránh hai enforced policy chồng nhau ngoài ý muốn. Các header mặc định khác của Spring Security vẫn có thể được cấu hình riêng.
4. Endpoint nhận report được `permitAll` và miễn CSRF vì báo cáo là request tự động của browser. Đây là **ngoại lệ đúng một đường dẫn**; không tắt CSRF toàn ứng dụng. Tình huống production phải hạn chế body size, rate limit, kiểm tra định dạng và xử lý dữ liệu có thể chứa thông tin riêng tư.
5. Ví dụ chỉ đăng ký CSP cho **tài liệu HTML `/demo`**. Các HTML route khác trong ứng dụng thực tế cần policy riêng hoặc đăng ký filter thích hợp; CSP của document điều khiển tài nguyên mà document đó yêu cầu.

### 7.3. Template có script dùng nonce

**src/main/resources/templates/demo.html**:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>CSP nonce demo</title>
</head>
<body>
    <h1>Content Security Policy với nonce</h1>
    <p id="status">Script chưa chạy</p>

    <script th:attr="nonce=${cspNonce}">
        document.getElementById("status").textContent =
            "Inline script có nonce đã chạy";
    </script>
</body>
</html>
~~~

Thymeleaf thay `th:attr="nonce=..."` bằng một thuộc tính `nonce="..."` ở HTML được trả về. Nonce trong header được tạo **cùng request** và truyền xuống controller qua request attribute. Khi trình duyệt tải `/demo`, script được cho phép và đoạn văn hiển thị **“Inline script có nonce đã chạy”**.

Lưu ý: ký tự đặc biệt trong template được Thymeleaf xử lý khi tạo attribute; không nối trực tiếp input người dùng vào markup. Nếu thêm một `<script>` inline **không có nonce** vào template, trong chế độ enforce browser sẽ từ chối thực thi script đó (trừ khi có một nguồn cho phép khác). Trong chế độ Report-Only, nó được ghi nhận là vi phạm nhưng **không bị policy đó chặn**.

### 7.4. Chạy và quan sát HTTP

Trong thư mục `csp-nonce-demo`, cài Maven và JDK 17+ rồi chạy:

~~~bash
mvn spring-boot:run
~~~

Ở terminal khác:

~~~bash
curl -i http://localhost:8080/demo
~~~

Trong header sẽ có `Content-Security-Policy: ... 'nonce-<giá-trị-base64>' ...`. Trong body HTML sẽ có `<script nonce="<cùng-giá-trị-base64>">`. Khi gửi lại một GET mới, nonce thường **khác nhau** vì server sinh ngẫu nhiên mỗi response.

Kiểm tra thao tác: mở `http://localhost:8080/demo` trong trình duyệt, xem **Network → /demo → Response Headers**, kiểm tra header CSP, rồi xem trang có dòng **“Inline script có nonce đã chạy”**. Sau đó thêm tạm một script inline không nonce để quan sát lỗi CSP trong DevTools Console khi thực hành; với chế độ enforce nó không được thực thi.

Đổi sang **Report-Only** bằng cách dừng ứng dụng và chạy:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--demo.csp.report-only=true
~~~

Khi đó response có `Content-Security-Policy-Report-Only` thay vì enforced header từ filter demo. Browser **thông báo** chính sách bị vi phạm nhưng không chặn vì policy chỉ báo cáo. Script có nonce vẫn chạy; script không nonce cũng có thể chạy nếu không có enforced policy nào khác. Tùy browser, endpoint `/csp-report` có thể nhận POST violation report.

Một môi trường production có thể đồng thời sử dụng **một enforced policy ổn định** và **một report-only policy mới chặt hơn** để đo mức tương thích trước khi nâng chính sách. Ví dụ sử dụng một policy mới chỉ báo cáo **không có nghĩa** các enforced policy cũ đã ngừng có hiệu lực.

## 8. Kiểm thử tự động header, nonce và chế độ báo cáo

Bài thực hành dưới đây dùng **HTTP server thực** ở random port, qua `@SpringBootTest`, để kiểm cả Servlet filter đăng ký bằng `FilterRegistrationBean` lẫn HTML render bởi Thymeleaf. Nó không cần cấu hình thêm MockMvc.

**src/test/java/example/csp/CspDemoApplicationTests.java**:

~~~java
package example.csp;

import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CspDemoApplicationTests {

    private static final Pattern NONCE =
            Pattern.compile("'nonce-([A-Za-z0-9+/=]+)'");

    @Autowired
    TestRestTemplate client;

    @Test
    void nonceInHeaderMatchesHtmlAndChangesForNextResponse() {
        ResponseEntity<String> first =
                client.getForEntity("/demo", String.class);
        ResponseEntity<String> second =
                client.getForEntity("/demo", String.class);

        assertThat(first.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(second.getStatusCode()).isEqualTo(HttpStatus.OK);

        String firstPolicy =
                first.getHeaders().getFirst("Content-Security-Policy");
        String secondPolicy =
                second.getHeaders().getFirst("Content-Security-Policy");

        assertThat(firstPolicy).contains("script-src");
        assertThat(firstPolicy).contains("object-src 'none'");
        assertThat(first.getHeaders().getFirst(
                "Content-Security-Policy-Report-Only")).isNull();

        String firstNonce = nonceFrom(firstPolicy);
        String secondNonce = nonceFrom(secondPolicy);

        assertThat(first.getBody())
                .contains("nonce=\"" + firstNonce + "\"");
        assertThat(second.getBody())
                .contains("nonce=\"" + secondNonce + "\"");
        assertThat(firstNonce).isNotEqualTo(secondNonce);
    }

    private static String nonceFrom(String policy) {
        Matcher matcher = NONCE.matcher(policy);
        assertThat(matcher.find()).isTrue();
        return matcher.group(1);
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Test kiểm tra **HTTP header và HTML thực tế khớp nonce** trong cùng response, rồi xác nhận hai request liên tiếp có nonce khác nhau. Việc hai nonce ngẫu nhiên 128 bit tình cờ trùng nhau có xác suất cực nhỏ, nên test phù hợp để xác nhận hành vi thực tế.

Để kiểm riêng chế độ báo cáo, có thể thêm test thứ hai trong cùng package, file **src/test/java/example/csp/CspReportOnlyTests.java**:

~~~java
package example.csp;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "demo.csp.report-only=true"
)
class CspReportOnlyTests {

    @Autowired
    TestRestTemplate client;

    @Test
    void usesReportOnlyHeader() {
        ResponseEntity<String> response =
                client.getForEntity("/demo", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getHeaders().getFirst(
                "Content-Security-Policy-Report-Only"))
                .contains("script-src");
        assertThat(response.getHeaders().getFirst(
                "Content-Security-Policy")).isNull();
    }
}
~~~

Test HTTP xác minh header trong hai chế độ. **Browser mới là thành phần thực thi CSP**, nên muốn kiểm việc script bị chặn hay vi phạm được báo cáo thì vẫn phải kiểm bằng browser thực và DevTools; kiểm status 200 của endpoint không chứng minh chính sách CSP đang được thực thi đúng.

## 9. Enforce và Report-Only khác nhau như thế nào?

Hai tên response header có mục đích khác nhau:

| Header | Browser thực thi | Thu thập vi phạm | Khi nào dùng |
| --- | --- | --- | --- |
| `Content-Security-Policy` | **Chặn** hành vi vi phạm directive được hỗ trợ. | Có thể báo cáo nếu cấu hình reporting. | Chính sách chính sau khi đã kiểm thử nguồn hợp lệ. |
| `Content-Security-Policy-Report-Only` | **Không chặn** chỉ vì policy Report-Only này. | Có thể ghi console/report khi có nguồn nhận. | Quan sát tác động của policy mới trước khi bật enforce. |

Ví dụ chính sách đang muốn đánh giá:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' 'nonce-ABC'; object-src 'none'; report-uri /csp-report
~~~

Nếu trang có script inline không nonce, Report-Only có thể phát sinh báo cáo, nhưng script vẫn chạy nếu **không có enforced policy khác chặn**. Không được hiểu “Report-Only chặn nhưng chỉ hiện cảnh báo”; nó **không cưỡng chế chính sách riêng của mình**.

Có thể gửi hai header cùng lúc, chẳng hạn:

~~~http
Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self' 'nonce-ABC'; object-src 'none'; report-uri /csp-report
~~~

Trong trường hợp này, policy enforced đầu tiên vẫn chặn hành vi mà nó cấm; policy report-only thứ hai quan sát các vi phạm của nó. Để kiểm nonce, không dùng `ABC` tĩnh ngoài ví dụ minh họa; phải cấp nonce an toàn theo mỗi response. Và nếu enforced policy cũng hạn chế script, Report-Only không có quyền nới giới hạn đó.

**Đưa CSP vào production theo lộ trình:**

1. Kiểm kê tài nguyên: HTML/template, inline script/style, CDN, images, fonts, WebSocket, API, iframe, analytics.
2. Viết policy dự kiến theo danh sách nguồn tối thiểu. Đừng đặt `script-src *` hay `'unsafe-inline'` chỉ để hết cảnh báo.
3. Chạy policy ở **Report-Only**, kiểm DevTools và báo cáo thực tế từ nhiều luồng chức năng, browser và trạng thái đăng nhập.
4. Loại bỏ inline script không tin cậy, chuyển script sang external file hoặc cấp nonce/hash đúng; bổ sung nguồn chỉ khi có bằng chứng ứng dụng cần và nguồn đáng tin.
5. Chuyển policy đã ổn định sang **enforce**; giữ một policy Report-Only mới nếu muốn thử các ràng buộc chặt hơn.
6. Theo dõi vi phạm sau triển khai và cập nhật khi tính năng/domain đáng tin cậy thay đổi.

## 10. Báo cáo vi phạm: report-uri, report-to và dữ liệu nhận được

Để browser gửi báo cáo, CSP có thể dùng `report-uri` (cơ chế lâu đời, vẫn hữu ích cho tính tương thích) hoặc tích hợp Reporting API bằng `report-to` cùng cấu hình endpoint như `Reporting-Endpoints`. **Hỗ trợ khác nhau giữa browser**; không nên chỉ phụ thuộc một cơ chế mà không kiểm tra ứng dụng mục tiêu.

Ví dụ dùng `report-uri`:

~~~http
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; report-uri /csp-report
~~~

Một browser có thể gửi POST tới `/csp-report` với Content-Type `application/csp-report` và body gần giống:

~~~json
{
  "csp-report": {
    "document-uri": "https://app.example.com/demo",
    "effective-directive": "script-src-elem",
    "blocked-uri": "inline",
    "disposition": "report",
    "original-policy": "default-src 'self'; script-src 'self'; report-uri /csp-report"
  }
}
~~~

Với Reporting API hiện đại, payload thường có cấu trúc báo cáo khác, có thể là mảng và chứa các trường như `type`, `url`, `body.effectiveDirective`, `body.blockedURL`; cần parse đúng theo Content-Type và đặc tả được browser hỗ trợ. Đừng giả định mọi report đều có cùng JSON shape.

Ví dụ cấu hình reporting hiện đại có thể yêu cầu:

~~~http
Reporting-Endpoints: csp-endpoint="https://app.example.com/csp-report"
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; report-to csp-endpoint
~~~

Một số triển khai triển khai kết hợp `report-to` và `report-uri` để hỗ trợ browser cũ. Khi cả hai được khai báo, browser hỗ trợ `report-to` có thể ưu tiên nó. Kiểm lại chính sách cùng browser đích vì reporting là phần có khác biệt tương thích đáng kể.

**Báo cáo không phải dữ liệu đáng tin tuyệt đối**: nguồn gửi có thể giả mạo POST, nội dung có thể chứa URL hoặc thông tin nhạy cảm, có thể nhiều dữ liệu và không bảo đảm tất cả vi phạm sẽ được báo cáo. Với endpoint nhận báo cáo:

- Giới hạn kích thước body, tần suất và số lượng request; chống spam/DoS.
- Không tin dữ liệu báo cáo là bằng chứng xác thực người dùng hay nguồn gốc đáng tin.
- Loại bỏ hoặc giảm độ chi tiết URL, query, referrer và nội dung nhạy cảm theo chính sách riêng tư.
- Lưu/nhóm theo `effectiveDirective`, `blocked-uri`, `document-uri`, `disposition`, browser hoặc phiên bản (sau khi xử lý riêng tư).
- Kiểm kỹ lưỡng trước khi thêm origin vào allowlist; script/chức năng bên thứ ba bị chặn không mặc nhiên là nguồn tin cậy.

Ở demo mục 7, `/csp-report` cố tình trả 204 và bỏ payload để tránh biến bài thực hành thành bộ thu dữ liệu. Nếu cần thống kê, bổ sung endpoint thu thập chuyên dụng với kiểm tra định dạng và ràng buộc vận hành tương ứng.

## 11. Những lỗi thường gặp khi áp dụng CSP trong Servlet

**Lỗi 1 — Chỉ cấu hình CSP nhưng nghĩ Spring Security tự chống hết XSS.** CSP là một lớp hạn chế thực thi ở browser. Vẫn cần output encoding, kiểm tra giá trị đưa vào HTML/JS/URL và giữ template an toàn. CSP policy quá rộng có thể gần như mất tác dụng.

**Lỗi 2 — Script hợp lệ bị chặn bởi `script-src 'self'`.** Script inline không có nonce/hash sẽ bị chặn, dù HTML được trả bởi cùng origin. `'self'` cho phép URL tài nguyên same-origin; **nó không tự cho phép mọi script inline**. Di chuyển script ra file hoặc gắn nonce ngẫu nhiên đúng cách.

**Lỗi 3 — Tạo nonce một lần khi app khởi động.** Nonce cố định làm giảm ý nghĩa chống chèn inline script. Tạo nonce **mỗi response** bằng `SecureRandom` và dùng chung chính giá trị đó cho header + template của response.

**Lỗi 4 — Nonce header và HTML không khớp.** Nếu controller tạo nonce khác hoặc header bị proxy ghi đè, browser chặn script. Kiểm response header và thuộc tính `nonce` trong response HTML. Với browser hiện đại, thuộc tính nonce có hành vi ẩn bớt giá trị khi đọc DOM qua một số API; quan sát raw response hoặc `.nonce` trên phần tử khi debug.

**Lỗi 5 — Có nhiều CSP header mâu thuẫn.** Nếu gateway thêm `script-src 'none'` còn app cho phép script theo nonce, enforced policies được áp dụng đồng thời; header của app không thể nới hạn chế do gateway đưa ra. Xác định mọi tầng sinh header và thống nhất chính sách.

**Lỗi 6 — Dùng `default-src 'self'` rồi tưởng đã bảo vệ mọi thứ.** `frame-ancestors`, `form-action` và `base-uri` cần xem xét riêng. Bổ sung directive đúng mục tiêu thay vì phụ thuộc nhầm vào fallback.

**Lỗi 7 — Thấy vi phạm ở Report-Only nhưng nghĩ browser đã chặn.** Báo cáo và enforcement là hai chế độ. Kiểm tên header và `disposition` trong report; chỉ policy enforced mới chặn do chính policy đó.

**Lỗi 8 — CSP cho `connect-src` nhưng `fetch` vẫn lỗi CORS.** CSP chỉ là một điều kiện. Cross-origin API vẫn phải xử lý CORS và có thể yêu cầu authentication/authorization. Ngược lại, API cho CORS không tự được CSP của trang cho phép kết nối.

**Lỗi 9 — Cho `'unsafe-inline'`/mọi `https:`/wildcard để trang chạy lại.** Đây có thể là nới chính sách quá lớn. Nên xác định directive bị vi phạm, nguồn thực tế và thay bằng external script, nonce/hash hoặc origin cụ thể.

**Lỗi 10 — Chỉ test một URL.** Document SSR, trang lỗi, route login, trang hiển thị do server render, JavaScript bundle, dynamic import, WebSocket, font, iframe... có thể yêu cầu chính sách khác. Đặt policy vào đúng response HTML và test các tuyến chức năng thực tế.

**Lỗi 11 — CDN cache HTML có nonce.** Nếu HTML cùng nonce được phân phối từ cache công khai, đặc tính “mỗi response mới một nonce” không còn được đảm bảo từ góc nhìn người dùng. Kiểm cache/CDN, template, edge responses và việc response header/body được cache đồng bộ.

**Lỗi 12 — Tin 100% vào violation report.** Báo cáo không có bảo đảm giao hàng và có thể thiếu, trùng, bị giả mạo hoặc chứa dữ liệu nhạy cảm. Kết hợp với DevTools, kiểm thử chức năng và telemetry server an toàn.

## 12. Bài tập kiểm tra kiến thức

**Bài 1.** Policy `default-src 'self'; script-src 'self'` có cho phép script inline `<script>alert(1)</script>` không? **Không theo mặc định**, vì `'self'` không cấp quyền cho inline script. Có thể chuyển thành file same-origin hoặc cấp nonce/hash hợp lệ.

**Bài 2.** `img-src https://img.example.com` có cho phép `fetch("https://img.example.com/api")` không? **Không suy ra được.** `fetch` thuộc `connect-src`, có cơ chế fallback riêng nếu directive đó vắng. Cho phép nguồn ảnh không đồng nghĩa với cho phép kết nối JS.

**Bài 3.** Trang A cần được nhúng bên trong iframe của portal B. Nên xem `frame-src` hay `frame-ancestors` ở response A? **`frame-ancestors`** quyết định ai được nhúng A; `frame-src` ở trang B liên quan B được tải iframe từ đâu.

**Bài 4.** Hai request GET trả HTML có cùng nonce do cấu hình cố định trong `policyDirectives`. Có đạt nguyên tắc nonce không? **Không.** Nonce phải được tạo mới bằng nguồn ngẫu nhiên mật mã cho từng response không bị cache/phát lại.

**Bài 5.** Trang chạy một script không nonce khi chỉ có header `Content-Security-Policy-Report-Only: script-src 'nonce-ABC'`. Đây có phải lỗi browser không? **Không.** Policy chỉ báo cáo, không tự chặn script.

**Bài 6.** Response có hai enforced CSP: một header cho phép script từ `'self'` và header khác là `script-src 'none'`. Script same-origin có chạy không? **Không**, vì phải đáp ứng **tất cả** enforced policies.

**Bài 7.** Browser báo CSP từ chối `fetch` đến domain API, trong khi server đã bật CORS. Bạn kiểm gì? Kiểm `connect-src` trong policy của document trước, rồi kiểm CORS, credential và xác thực của API như các cơ chế độc lập.

**Bài 8.** Report endpoint nhận hàng nghìn POST `application/csp-report` từ client không xác thực. Có tin toàn bộ nội dung không? **Không.** CSP reports có thể bị giả mạo; cần rate limit, xử lý dữ liệu tối thiểu và validation.

## 13. Tóm tắt để áp dụng

- **CSP là response header do browser áp dụng cho document**; Spring Security Servlet cần được cấu hình policy phù hợp, không có một CSP tự bật đúng cho mọi ứng dụng.
- **Directive quy định nhóm tài nguyên**: `script-src`, `style-src`, `img-src`, `connect-src`, `font-src`, `frame-ancestors`, `form-action`, `base-uri`. Đừng nhầm `frame-src` với `frame-ancestors` hoặc nghĩ mọi directive đều fallback về `default-src`.
- **Nonce phải đủ ngẫu nhiên và được tạo mới mỗi response**, xuất hiện đồng nhất trong CSP header và thuộc tính `nonce` của script/style inline được tin cậy. Với HTML không cần inline script, policy dùng external files có thể đơn giản hơn.
- **Enforce** dùng `Content-Security-Policy` để chặn vi phạm; **Report-Only** dùng `Content-Security-Policy-Report-Only` để quan sát trước khi bật cưỡng chế. Có thể dùng cả hai cho hai mục tiêu khác nhau.
- **CSP, CORS, CSRF, authentication và authorization không thay thế nhau.** CSP tăng sức phòng vệ trước nội dung/script không đáng tin, còn server vẫn chịu trách nhiệm bảo vệ dữ liệu và quyền truy cập.
