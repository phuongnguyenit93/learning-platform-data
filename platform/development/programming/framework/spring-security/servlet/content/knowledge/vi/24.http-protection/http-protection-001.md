# Security headers mặc định trong Spring Security Servlet và những rủi ro được giảm thiểu

**Module:** Spring Security – Servlet  
**Chủ đề cha:** Bảo vệ HTTP

## 1. Security header là gì và tại sao cần?

**HTTP security headers** là các header trong **HTTP response** do server gửi cho trình duyệt. Chúng hướng dẫn browser xử lý nội dung theo các quy tắc an toàn hơn: không tự đoán MIME type, hạn chế website khác nhúng trang vào iframe, ghi nhớ yêu cầu dùng HTTPS, kiểm soát bộ nhớ đệm, hạn chế nơi JavaScript có thể tải tài nguyên, v.v.

Trong ứng dụng **Spring Security Servlet**, các header phổ biến được ghi qua **HeaderWriterFilter** và những **HeaderWriter** trong security filter chain. Nếu dùng cấu hình bảo mật HTTP thông thường, Spring Security có một tập header mặc định; không cần tự viết controller để gắn từng header. Tuy nhiên, cấu hình có thể thay đổi theo **phiên bản**, request có phải **HTTPS** không, các filter chain được áp dụng và việc ứng dụng đã đặt header trước đó.

Cần phân biệt ba tầng:

- **TLS/HTTPS** mã hóa và xác thực kết nối; **security headers** bổ sung hành vi bảo vệ ở trình duyệt.
- **Authentication/authorization** xác nhận danh tính và quyền; security headers không cấp hoặc kiểm tra quyền.
- **Input validation, output encoding, CSRF protection, quản lý session** vẫn bắt buộc. Header làm giảm bề mặt tấn công hoặc hậu quả của lỗi khác, nhưng không tự chữa tất cả lỗ hổng ứng dụng.

Một request điển hình:

~~~text
Browser --GET /account--> Servlet container
                            |
                            v
                       SecurityFilterChain
                       HeaderWriterFilter + các filter khác
                            |
                            v
                         Controller
                            |
          HTTP response <----+
          X-Content-Type-Options: nosniff
          X-Frame-Options: DENY
          Cache-Control: no-cache, no-store, ...
          ... tùy request và cấu hình
~~~

Không nên đánh giá an toàn chỉ bằng việc nhìn thấy header: phải hiểu **rủi ro nào được giảm**, **header áp dụng ở đâu**, và **nó không giải quyết vấn đề gì**.

## 2. Các header mặc định trong Spring Security 6 Servlet

Bảng sau mô tả cấu hình mặc định phổ biến của **Spring Security 6.x khi HTTP headers chưa bị tùy biến hoặc tắt**. Giá trị thực tế phải được xác minh trên ứng dụng và phiên bản đang chạy.

| Header | Giá trị mặc định thường gặp | Rủi ro được giảm thiểu / vai trò |
| --- | --- | --- |
| **X-Content-Type-Options** | `nosniff` | Ngăn browser đoán loại nội dung khác với Content-Type mà server khai báo; giảm rủi ro thực thi nhầm tài nguyên như script/style. |
| **X-Frame-Options** | `DENY` | Không cho trang được nhúng trong frame/iframe; giảm nguy cơ **clickjacking**. |
| **Cache-Control** | `no-cache, no-store, max-age=0, must-revalidate` | Hạn chế cache nội dung nhạy cảm của response được bảo vệ. |
| **Pragma** | `no-cache` | Tương thích lịch sử với cơ chế cache HTTP cũ. |
| **Expires** | `0` | Đặt nội dung là đã hết hạn đối với cơ chế cache liên quan. |
| **Strict-Transport-Security** | `max-age=31536000 ; includeSubDomains` | **HSTS** yêu cầu browser tiếp tục dùng HTTPS trong khoảng thời gian xác định; giúp chống quay về HTTP trên các lần truy cập sau. **Chỉ được Spring Security gửi khi request được nhận diện là secure (HTTPS)**. |
| **X-XSS-Protection** | `0` | **Tắt** bộ lọc XSS kiểu cũ của một số browser vì nó lỗi thời và có thể tạo hành vi không an toàn. Đây **không phải** header chống XSS hiện đại. |

Ghi chú quan trọng:

1. Thứ tự các header trong response không có ý nghĩa; tên header HTTP không phân biệt chữ hoa/chữ thường. Dấu cách ở phần HSTS có thể do implementation thể hiện khác nhau, không ảnh hưởng ý nghĩa.
2. Spring Security thường **không tự ghi đè các cache header mà ứng dụng đã chủ động đặt**. Ví dụ static asset có thể có chính sách cache riêng.
3. HSTS không xuất hiện trong response HTTP thường là **hành vi đúng**, không có nghĩa security filter thiếu cấu hình.
4. Nếu một endpoint không đi qua **SecurityFilterChain** (chẳng hạn bị loại bằng `web.ignoring()`), các security header do Spring Security ghi có thể vắng mặt.
5. Không mặc định suy ra Content-Security-Policy, Referrer-Policy hay Permissions-Policy từ bảng này; đây là các chính sách cần đánh giá và thường phải cấu hình thêm.

## 3. Phân tích từng cơ chế và rủi ro

### 3.1. `X-Content-Type-Options: nosniff` — ngăn MIME sniffing

Server cần gửi đúng Content-Type, ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
X-Content-Type-Options: nosniff

{"status":"ok"}
~~~

Trong lịch sử, một số browser cố suy đoán MIME type của nội dung nếu khai báo sai. Điều này nguy hiểm nếu dữ liệu upload hoặc nội dung người dùng có thể bị browser hiểu thành JavaScript hay CSS. `nosniff` hạn chế việc browser xử lý tài nguyên ở ngữ cảnh script/style khi loại MIME không đúng, và còn được một số trình duyệt áp dụng trong các tình huống khác.

**Ví dụ rủi ro:** endpoint upload trả về dữ liệu do người dùng kiểm soát với MIME mơ hồ; một trang khác nhúng URL đó như tài nguyên thực thi. Chặn sniffing là một lớp giảm thiểu.

**Giới hạn:** `nosniff` không tự ngăn XSS do ứng dụng cố tình đưa HTML độc hại vào trang. Server vẫn phải gán đúng `Content-Type`, mã hóa output theo ngữ cảnh, kiểm tra upload và dùng `Content-Disposition: attachment` khi cần tải file thay vì hiển thị.

**Lỗi hay gặp:** bật `nosniff` làm script hoặc stylesheet không tải vì backend trả `text/plain` hay `text/html` cho file JavaScript/CSS. Cách sửa là **sửa MIME và đường dẫn tài nguyên**, không tắt header để che lỗi.

### 3.2. `X-Frame-Options: DENY` — hạn chế clickjacking

**Clickjacking** xảy ra khi website của kẻ tấn công đặt ứng dụng thật vào iframe rồi phủ giao diện giả lên trên, dụ người dùng click vào nút nhạy cảm của trang thật.

~~~text
Trang tấn công
+---------------------------------------+
| "Bấm để nhận quà"                     |
|    [nút giả đè lên vị trí nút thật]   |
|       iframe chứa trang ngân hàng     |
+---------------------------------------+
~~~

Với `X-Frame-Options: DENY`, browser hỗ trợ header sẽ từ chối hiển thị trang trong frame, kể cả từ cùng origin. Nếu ứng dụng thực sự cần nhúng **trong cùng origin**, có thể cân nhắc `SAMEORIGIN`. Nếu muốn cho phép nhúng từ các origin được chọn, chính sách hiện đại và linh hoạt hơn là **CSP `frame-ancestors`**.

Phân biệt:

- `X-Frame-Options` và `Content-Security-Policy: frame-ancestors ...` kiểm soát **ai được nhúng trang hiện tại**.
- `Content-Security-Policy: frame-src ...` kiểm soát **trang hiện tại được nhúng nguồn nào**.
- **CORS** kiểm soát quyền JavaScript ở origin khác **đọc response**; CORS không thay thế biện pháp chống clickjacking.

Trong browser hiện đại hỗ trợ CSP `frame-ancestors`, chính sách đó có thể được ưu tiên hơn X-Frame-Options. Không dùng `ALLOW-FROM`: giá trị này không được hỗ trợ đồng nhất trong trình duyệt hiện đại.

### 3.3. `Cache-Control`, `Pragma`, `Expires` — hạn chế lưu nội dung nhạy cảm

Ví dụ response mặc định:

~~~http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
~~~

Ý nghĩa các chỉ thị cần tách riêng:

- **`no-store`**: yêu cầu cache không lưu response/request theo quy tắc caching; đây là chỉ thị quan trọng khi trang hoặc API chứa dữ liệu nhạy cảm.
- **`no-cache`**: không phải là “tuyệt đối không lưu”; nó yêu cầu cache **xác thực lại** trước khi sử dụng nội dung đã lưu.
- **`max-age=0`**: đặt thời gian nội dung được coi là còn mới bằng 0.
- **`must-revalidate`**: hạn chế sử dụng lại bản cache cũ khi không thể xác thực theo quy tắc HTTP.
- **`Pragma: no-cache`**, **`Expires: 0`**: bổ trợ tương thích với cơ chế HTTP cũ.

**Rủi ro:** một trang chứa hồ sơ, giao dịch, thông tin cá nhân vẫn còn trong bộ nhớ đệm browser hoặc proxy dùng chung sau khi người dùng đăng xuất.

**Giới hạn:** các header này **không xóa dữ liệu đã rò rỉ**, không ngăn user chụp màn hình, không thay thế chính sách lưu trữ ở frontend hay server. Với dữ liệu cực nhạy cảm, phải đánh giá cả browser back-forward cache, service worker, lưu trữ IndexedDB/localStorage và cache ở gateway.

**Hiệu năng:** không áp dụng mù quáng `no-store` cho tất cả tài nguyên bất biến. CSS/JS có tên chứa content hash có thể được cache lâu bằng chính sách thích hợp do ứng dụng/CDN thiết lập, trong khi HTML/API chứa dữ liệu riêng tư nên hạn chế cache. Đừng gỡ toàn bộ security headers chỉ để sửa cache.

### 3.4. HSTS — `Strict-Transport-Security`

Ví dụ server trả về **qua HTTPS**:

~~~http
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
~~~

Browser hỗ trợ HSTS ghi nhớ rằng hostname này phải được truy cập bằng HTTPS trong **31.536.000 giây (khoảng một năm)**. `includeSubDomains` mở rộng chính sách đến các tên miền con phù hợp. Các truy cập sau qua HTTP sẽ được browser tự nâng lên HTTPS trước khi gửi request thông thường.

HSTS giúp giảm rủi ro kẻ tấn công cố chuyển người dùng từ HTTPS về HTTP (**SSL stripping/downgrade**) sau khi browser đã học chính sách.

**Ba điểm quan trọng:**

1. HSTS **chỉ có hiệu lực khi được nhận qua kết nối HTTPS hợp lệ**. Header giả mạo trên HTTP không tạo chính sách HSTS đáng tin. HSTS thông thường **không bảo vệ lần truy cập đầu tiên** của một browser chưa từng biết domain; HSTS preload là cơ chế riêng và cần thẩm định kỹ trước khi đăng ký.
2. `includeSubDomains` chỉ nên dùng nếu **mọi subdomain thuộc phạm vi đều phục vụ HTTPS hợp lệ**. Nếu còn subdomain chỉ chạy HTTP, có thể làm các dịch vụ đó không truy cập được từ trình duyệt đã ghi nhớ chính sách.
3. Sau reverse proxy/TLS terminator, backend có thể nhận request HTTP nội bộ và `request.isSecure() == false`; khi đó Spring Security không tự phát HSTS. Cần cấu hình nhận diện forwarded scheme đúng, đồng thời **chỉ tin `Forwarded`/`X-Forwarded-Proto` do proxy đáng tin gắn vào**, không tin tùy tiện từ Internet.

HSTS không tự cấu hình chứng chỉ TLS, TLS version, redirect HTTP → HTTPS hay bảo vệ client không hỗ trợ HSTS. Nên bật HTTPS bắt buộc, certificate hợp lệ và chuyển hướng có kiểm soát ở lớp phù hợp.

### 3.5. `X-XSS-Protection: 0` — tắt bộ lọc XSS cũ

Tên header dễ gây hiểu nhầm: giá trị **`0` nghĩa là tắt** XSS auditor/filter kiểu cũ trên một số browser. Những bộ lọc này đã lỗi thời và từng có các trường hợp tạo ra hành vi không mong muốn; browser hiện đại chủ yếu không dùng chúng.

Do đó, **không đánh dấu ứng dụng đã chống XSS chỉ vì header tồn tại**. Phòng chống XSS thực tế cần:

- Escape/encode output đúng ngữ cảnh HTML, attribute, JavaScript, URL.
- Tránh chèn HTML không được làm sạch bằng `innerHTML`; kiểm soát dữ liệu template.
- Sanitization có kiểm chứng khi thật sự cần render HTML do người dùng nhập.
- **Content Security Policy (CSP)** phù hợp như một lớp phòng vệ bổ sung.
- Bảo vệ cookie/session, cập nhật thư viện frontend, hạn chế lỗ hổng DOM XSS.

Không bật lại `X-XSS-Protection: 1; mode=block` với kỳ vọng nó là giải pháp XSS hiện đại.

## 4. Các header có giá trị nhưng **không được tự bật mặc định**

### 4.1. Content-Security-Policy (CSP)

CSP giới hạn nguồn tài nguyên, script, style, frame và một số hành vi mà trang có thể sử dụng. **Spring Security không tự chọn một CSP thích hợp cho mọi ứng dụng**, vì mỗi hệ thống có CDN, SPA, inline script, analytics và yêu cầu nhúng khác nhau.

Ví dụ một chính sách tương đối chặt cho ứng dụng đơn giản:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
~~~

Giải thích:

- `default-src 'self'`: giá trị mặc định cho nhóm tài nguyên có fallback về `default-src`.
- `script-src 'self'`: cho phép JavaScript từ cùng origin; tránh script từ nguồn ngoài không được chấp thuận.
- `object-src 'none'`: hạn chế nhúng nội dung plugin/object kiểu cũ.
- `base-uri 'self'`: hạn chế thay đổi base URL dùng để giải quyết đường dẫn tương đối.
- `frame-ancestors 'none'`: không cho origin khác, hoặc ngay cả chính origin, nhúng trang này.

**CSP làm giảm rủi ro XSS nhưng không thay thế output encoding.** Không thêm bừa `'unsafe-inline'` hoặc wildcard vào `script-src` cho “hết lỗi” vì làm yếu kiểm soát script. Với ứng dụng cần script inline, nên thiết kế nonce hoặc hash phù hợp. Một chính sách trên còn có thể cần điều chỉnh `connect-src`, `img-src`, `style-src`, `font-src` hoặc API/CDN tùy frontend.

Có thể triển khai thận trọng bằng **`Content-Security-Policy-Report-Only`** để quan sát vi phạm trước khi chuyển sang enforcement. `frame-ancestors` phải được gửi bằng **HTTP response header**, không hoạt động khi chỉ nhúng trong thẻ HTML `<meta http-equiv="Content-Security-Policy">`.

### 4.2. Referrer-Policy

`Referrer-Policy` quyết định lượng thông tin từ URL của trang gốc được browser gửi trong header `Referer` khi điều hướng hoặc tải tài nguyên. Ví dụ:

~~~http
Referrer-Policy: strict-origin-when-cross-origin
~~~

Với chính sách này, browser thường gửi URL đầy đủ cho request cùng origin, chỉ gửi **origin** khi request chuyển sang origin khác qua kết nối an toàn phù hợp, và không gửi referrer khi đi từ HTTPS sang HTTP. Điều đó giảm nguy cơ lộ đường dẫn/query chứa thông tin nhạy cảm sang website bên ngoài.

**Giới hạn:** không đặt access token, mật khẩu hay thông tin bí mật vào query string ngay từ đầu; referrer policy không phải nơi lưu trữ bí mật. Các browser hiện đại có thể đã dùng mặc định tương tự, nhưng quy định rõ policy giúp hành vi ứng dụng có chủ đích.

### 4.3. Permissions-Policy

Giới hạn khả năng trang/iframe truy cập các tính năng trình duyệt, ví dụ:

~~~http
Permissions-Policy: camera=(), microphone=(), geolocation=()
~~~

Ví dụ này từ chối camera, microphone và geolocation đối với tài liệu nằm trong phạm vi chính sách. Có thể thiết kế allowlist riêng nếu ứng dụng thực sự cần. **Permissions-Policy không cấp hoặc xác thực quyền ở server**, cũng không thay thế hộp thoại xin quyền của browser.

### 4.4. Các chính sách khác tùy nhu cầu

- **Cross-Origin-Opener-Policy (COOP)**: cô lập browsing context ở mức nhất định; có thể ảnh hưởng luồng popup đăng nhập OAuth hoặc thanh toán.
- **Cross-Origin-Embedder-Policy (COEP)** và **Cross-Origin-Resource-Policy (CORP)**: kiểm soát embedding/tải tài nguyên qua origin, có thể cần khi dùng cross-origin isolation. Bật sai dễ làm hỏng tài nguyên hoặc iframe.
- **Clear-Site-Data**: có thể dùng ở các response phù hợp, ví dụ sau khi logout, để yêu cầu browser xóa một số dạng dữ liệu; cần hiểu phạm vi, hỗ trợ browser và tác động đến nhiều ứng dụng cùng origin.
- **CORS response headers** như `Access-Control-Allow-Origin`: chỉ cấu hình khi có luồng cross-origin hợp lệ; không mặc định cho phép mọi origin cùng credentials.

Các chính sách này **không nên được gắn như một bộ “càng nhiều càng tốt”**. Mỗi header phải gắn với mô hình rủi ro và yêu cầu tương thích cụ thể.

## 5. Ví dụ chạy được: giữ mặc định và thêm CSP, Referrer-Policy, Permissions-Policy

Ví dụ dùng **Java 17**, **Spring Boot 3.3.5 / Spring Security 6.x** với Spring MVC trên **Servlet stack**. Bản version ở đây dùng để tái hiện cấu hình; dự án thực tế phải cập nhật lên bản vá được hỗ trợ.

**Cấu trúc thư mục**

~~~text
header-demo/
├── pom.xml
└── src/
    ├── main/java/demo/HeaderDemoApplication.java
    └── test/java/demo/HeaderDemoApplicationTests.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>header-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

**src/main/java/demo/HeaderDemoApplication.java**

~~~java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HeaderDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(HeaderDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            // Cho phép truy cập endpoint demo để dễ xem response headers.
            // permitAll KHÔNG có nghĩa là bỏ qua Spring Security filters.
            .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
            .headers(headers -> headers
                // Các header mặc định như nosniff, DENY, cache và HSTS
                // vẫn được giữ nguyên khi thêm các header bên dưới.
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'self'; script-src 'self'; " +
                    "object-src 'none'; base-uri 'self'; " +
                    "frame-ancestors 'none'"
                ))
                .referrerPolicy(ref -> ref.policy(
                    ReferrerPolicyHeaderWriter.ReferrerPolicy
                        .STRICT_ORIGIN_WHEN_CROSS_ORIGIN
                ))
                .addHeaderWriter((request, response) ->
                    response.setHeader(
                        "Permissions-Policy",
                        "camera=(), microphone=(), geolocation=()"
                    )
                )
            );

        return http.build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/api/hello")
        Map<String, String> hello() {
            return Map.of("message", "ok");
        }
    }
}
~~~

**Vì sao ví dụ này đúng phạm vi?**

- Khai báo `SecurityFilterChain` bảo đảm request `/api/hello` đi qua Spring Security. `permitAll()` cho phép anonymous đọc endpoint, **vẫn có HeaderWriterFilter**.
- Khối `.headers(...)` **bổ sung** CSP, Referrer-Policy, Permissions-Policy, không gọi `defaultsDisabled()` hay `.disable()`; các header mặc định vẫn hoạt động.
- Chính sách CSP là ví dụ phù hợp với endpoint JSON và trang chỉ tải script từ chính origin. Khi chuyển sang SPA thực tế, cần kiểm tra tài nguyên, inline script, fonts, CDN và API trước khi áp dụng nguyên xi.
- HTTP GET không cần CSRF token theo mặc định. **Bảo vệ CSRF vẫn đang bật** cho các method thay đổi trạng thái; ví dụ không cần vô hiệu hóa nó.
- Permissions-Policy được thêm qua `HeaderWriter` tùy biến; thay thế bằng DSL tương ứng cũng được nếu phiên bản đang dùng hỗ trợ và yêu cầu dự án phù hợp.

**Chạy chương trình**

~~~bash
mvn spring-boot:run
~~~

Kiểm tra response (Linux/macOS dùng `curl`, trên PowerShell có thể dùng `curl.exe`):

~~~bash
curl -i http://localhost:8080/api/hello
~~~

Ví dụ phần body là:

~~~json
{"message":"ok"}
~~~

Quan sát response header thực tế: trên **HTTP localhost**, kỳ vọng có `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, các header cache, `X-XSS-Protection: 0` và ba chính sách vừa thêm. **Không kỳ vọng HSTS** vì request HTTP chưa secure. Không khẳng định thứ tự header hoặc các header phụ do container tự thêm.

Trong môi trường HTTPS thật hoặc mô phỏng request secure trong test, kiểm tra thêm HSTS. Không lấy kết quả từ `http://localhost` rồi kết luận HSTS bị lỗi.

## 6. Kiểm thử tự động header bằng MockMvc

**src/test/java/demo/HeaderDemoApplicationTests.java**

~~~java
package demo;

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
class HeaderDemoApplicationTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void defaultAndAddedHeadersOnHttp() throws Exception {
        mockMvc.perform(get("/api/hello"))
            .andExpect(status().isOk())
            .andExpect(header().string("X-Content-Type-Options", "nosniff"))
            .andExpect(header().string("X-Frame-Options", "DENY"))
            .andExpect(header().string(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; " +
                "object-src 'none'; base-uri 'self'; " +
                "frame-ancestors 'none'"
            ))
            .andExpect(header().string(
                "Referrer-Policy", "strict-origin-when-cross-origin"
            ))
            .andExpect(header().string(
                "Permissions-Policy",
                "camera=(), microphone=(), geolocation=()"
            ))
            .andExpect(header().doesNotExist("Strict-Transport-Security"));
    }

    @Test
    void hstsOnlyWhenRequestIsSecure() throws Exception {
        mockMvc.perform(get("/api/hello").secure(true))
            .andExpect(status().isOk())
            .andExpect(header().exists("Strict-Transport-Security"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Kỳ vọng** cả hai test đều PASS: test HTTP không có HSTS, test secure có HSTS. Đây là kết quả mong đợi của ví dụ, không phải log chạy thật được sao chép. Nếu sau này thay đổi `SecurityFilterChain`, các test này giúp phát hiện việc vô tình mất header.

Để kiểm tra đầy đủ trong môi trường triển khai, thử thêm response **200, 302, 401, 403, 404**, endpoint API và trang tĩnh quan trọng, HTTPS qua load balancer/proxy, cũng như các chain dùng `securityMatcher` khác nhau. Header có thể bị thêm, xóa hoặc ghi đè sau ứng dụng ở gateway/CDN; kiểm tra cả response **bên ngoài** proxy.

## 7. Khi nào chỉnh sửa mặc định và chỉnh sửa như thế nào?

### 7.1. Cho phép iframe từ cùng origin có chủ đích

Ví dụ một công cụ nội bộ phải nhúng trang của chính mình trong iframe. Thay đổi trong block `.headers(...)`:

~~~java
.frameOptions(frame -> frame.sameOrigin())
~~~

**Đây là một dòng cấu hình minh họa đặt bên trong DSL headers, không phải một class Java độc lập.** Khi dùng cả CSP, `frame-ancestors 'none'` vẫn từ chối iframe; muốn cho phép nhúng cùng origin, cần đồng bộ thành `frame-ancestors 'self'`. Chỉ thực hiện sau khi đánh giá clickjacking với trang chứa thao tác nhạy cảm.

### 7.2. Tối ưu cache cho nội dung công khai

Với tài nguyên tĩnh có tên file gắn hash, đặt `Cache-Control` phù hợp tại resource handler/CDN (ví dụ `public, max-age=31536000, immutable`). Với HTML hoặc API chứa dữ liệu cá nhân, duy trì cache chính sách chặt. **Không dùng `headers.disable()` làm cách sửa cache**, vì sẽ làm mất những biện pháp khác.

### 7.3. Dịch vụ sau reverse proxy

Nếu HTTPS kết thúc ở gateway, hãy kiểm tra kết quả `request.isSecure()` và header HSTS trên **response client nhận được**. Spring Boot hỗ trợ chiến lược xử lý forwarded headers, ví dụ cấu hình sau khi hạ tầng tin cậy đã loại bỏ các forwarded header do client giả mạo:

~~~properties
server.forward-headers-strategy=framework
~~~

Tùy container/cloud, cấu hình proxy-native có thể thích hợp hơn. Đây là **đoạn cấu hình môi trường**, chỉ dùng sau khi xác thực trust boundary của proxy. Bật tùy tiện việc tin forwarded headers có thể gây lỗi xác định origin/scheme, redirect hoặc cookie.

### 7.4. Nhiều `SecurityFilterChain`

Một ứng dụng có thể khai báo nhiều chain với `@Order` và `securityMatcher`. Mỗi request dùng **chain đầu tiên khớp**. Nếu chain riêng vô hiệu hóa headers hoặc không được match, một số endpoint có thể thiếu header dù endpoint khác hoạt động đúng.

Cách đúng là kiểm tra các chain áp dụng cho từng tập URL, ưu tiên **`permitAll()`** cho tài nguyên công khai vẫn cần filter, thay vì bỏ hẳn URL khỏi Spring Security bằng `web.ignoring()` khi không có lý do rõ ràng.

## 8. Các nhầm lẫn thường gặp

| Nhầm lẫn / triệu chứng | Giải thích đúng và cách xử lý |
| --- | --- |
| “Có X-XSS-Protection là đã chặn XSS.” | Giá trị `0` là **tắt** bộ lọc cũ. Dùng escaping/sanitization và CSP phù hợp. |
| “HSTS phải xuất hiện trên HTTP localhost.” | Spring Security chỉ ghi HSTS khi request được coi là secure. Kiểm tra HTTPS hoặc MockMvc `.secure(true)`. |
| “HSTS khiến HTTPS hoạt động dù server chưa cài TLS.” | HSTS chỉ yêu cầu browser dùng HTTPS; server vẫn phải có TLS/chứng chỉ hợp lệ. |
| “X-Frame-Options DENY cấm mọi trang khác gọi API.” | Nó cấm **nhúng vào frame**, không thay thế CORS, CSRF hay authorization. |
| “`no-cache` đồng nghĩa không lưu.” | `no-cache` yêu cầu revalidation; `no-store` mới là chỉ thị không lưu vào HTTP cache. |
| “Thêm CSP với `unsafe-inline` là xong.” | Có thể làm suy yếu cơ chế kiểm soát script. Thiết kế nguồn, nonce/hash và kiểm tra vi phạm thực tế. |
| “Thêm `<meta>` CSP là đủ cho `frame-ancestors`.” | `frame-ancestors` cần CSP trong HTTP response header. |
| “Controller trả header, vậy mọi response đều có.” | Redirect, exception, static resource, gateway hoặc chain khác có thể xử lý khác. Kiểm tra response thực. |
| “`permitAll()` làm mất security headers.” | `permitAll()` vẫn chạy filter chain. `web.ignoring()` mới bỏ qua Spring Security cho request tương ứng. |
| “Tắt toàn bộ HTTP headers để cho iframe hoặc static cache.” | Điều chỉnh riêng frame policy/cache policy cần thiết; giữ các header bảo vệ khác. |
| “Bật `includeSubDomains` ở mọi nơi.” | Chỉ an toàn khi toàn bộ subdomain thuộc phạm vi có HTTPS phù hợp. |
| “Có header là đủ chống CSRF hoặc SQL injection.” | CSRF cần cơ chế chống CSRF phù hợp; SQL injection cần parameterized queries và quyền DB tối thiểu. |

## 9. Quy trình đánh giá bảo vệ HTTP trong dự án thật

1. **Kiểm kê endpoint và filter chain:** HTML/SPA, JSON API, download, static asset, trang lỗi và redirect; xác định chain nào xử lý.
2. **Quan sát response thật:** dùng DevTools Network hoặc `curl -i` trên cả HTTP, HTTPS, các mã trạng thái quan trọng và qua proxy/CDN. Không dùng HEAD làm bằng chứng duy nhất nếu hệ thống xử lý HEAD khác GET.
3. **Đối chiếu rủi ro:** MIME sniffing → nosniff; clickjacking → DENY/frame-ancestors; cache nhạy cảm → no-store; downgrade HTTPS → HSTS; tải script độc hại → CSP và encoding; rò referrer → Referrer-Policy; API browser features → Permissions-Policy.
4. **Kiểm tra tương thích:** iframe nghiệp vụ, login popup, OAuth redirect, CDN, analytics, inline script, ảnh, fonts, service worker và các subdomain. Có thể dùng CSP Report-Only trước khi ép chính sách.
5. **Tạo regression tests:** xác nhận những header quan trọng của từng chain và hành vi có/không HSTS. Đừng chỉ dựa vào security scanner đưa ra điểm số.
6. **Giám sát thay đổi ở gateway:** nginx, ingress, CDN có thể viết lại header, tạo header trùng hoặc bỏ một chính sách. Xác minh response người dùng cuối nhìn thấy.

**Ghi nhớ:** Spring Security Servlet cung cấp một lớp bảo vệ HTTP mặc định hữu ích cho **MIME sniffing, clickjacking, cache dữ liệu nhạy cảm và HTTPS downgrade**. Header `X-XSS-Protection: 0` chỉ **tắt** cơ chế lỗi thời. **CSP, Referrer-Policy, Permissions-Policy** thường cần được thêm theo nhu cầu. HSTS chỉ gửi cho request secure, và **không header nào thay thế các kiểm soát cốt lõi ở server hoặc frontend**.