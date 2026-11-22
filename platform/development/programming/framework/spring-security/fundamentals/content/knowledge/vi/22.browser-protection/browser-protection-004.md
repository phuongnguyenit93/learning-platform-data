# X-Content-Type-Options và kiểm soát kiểu nội dung trong Spring Security

Một ứng dụng web trả tệp có đuôi `.js` nhưng lại gắn `Content-Type: text/plain`. Trình duyệt có nên đoán rằng nội dung bên trong trông giống JavaScript rồi thực thi không? Nếu chấp nhận kiểu “đoán nội dung” (*MIME sniffing*) trên một tài nguyên do người dùng tải lên hoặc một phản hồi bị gắn sai kiểu, browser có nguy cơ chạy mã ngoài ý muốn trong ngữ cảnh website.

**`X-Content-Type-Options: nosniff`** là HTTP response header hướng dẫn browser tôn trọng kiểu MIME server khai báo, thay vì suy diễn kiểu nội dung từ dữ liệu. Với request dùng tài nguyên ở vai trò **script** hoặc **stylesheet**, browser hiện đại sẽ từ chối tải/thi hành khi kiểu MIME không phù hợp. Header này là một lớp phòng thủ quan trọng chống **MIME confusion** và một số đường dẫn tới **XSS**, nhưng **không tự sửa một `Content-Type` sai và không thay Content Security Policy (CSP), kiểm tra file upload hay escaping đầu ra**.

Bài thuộc nhóm **Bảo vệ trình duyệt** của **Spring Security - fundamentals**. Trọng tâm: phân biệt `Content-Type` và `X-Content-Type-Options`, hiểu thế nào là `nosniff`, tác động tới JavaScript/CSS/HTML và file tải lên, cách Spring Security Servlet cấu hình mặc định, kiểm thử trên Java 17+ và cách chẩn đoán lỗi MIME từ trình duyệt. Ví dụ chính sử dụng **Spring Boot 3.3.x, Spring Security 6.3.x, Java 17+**.

## 1. MIME type là gì? Vì sao file extension không quyết định tất cả?

**MIME type** (media type) mô tả kiểu dữ liệu mà server tuyên bố đang gửi trong HTTP response. Một số ví dụ:

| Tài nguyên | Content-Type thường dùng | Ghi chú |
| --- | --- | --- |
| Trang HTML | `text/html; charset=UTF-8` | Browser phân tích như HTML khi phù hợp |
| JavaScript | `text/javascript` | MIME type JavaScript chuẩn, phổ biến cho script |
| Stylesheet CSS | `text/css` | Kiểu chuẩn của CSS |
| API JSON | `application/json` | Dữ liệu JSON, không phải JavaScript thực thi chỉ vì cú pháp có thể giống |
| Văn bản thường | `text/plain; charset=UTF-8` | Hiển thị như văn bản |
| Ảnh PNG | `image/png` | Dữ liệu ảnh |
| PDF | `application/pdf` | Trình duyệt hoặc phần mềm PDF xử lý |
| Tệp nhị phân chung | `application/octet-stream` | Không khẳng định đây là script hay HTML |

Một response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/javascript; charset=UTF-8
X-Content-Type-Options: nosniff

console.log("example");
~~~

cho biết server **cố ý** gửi JavaScript. Ngược lại:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
X-Content-Type-Options: nosniff

console.log("example");
~~~

cho biết server gửi **văn bản thông thường**. Nếu response thứ hai được một trang tham chiếu như script, browser nên từ chối dùng nó như JavaScript.

**Đuôi file không phải bằng chứng duy nhất về MIME:** `app.js` có thể được server gắn `text/html` vì request bị redirect tới trang login; `report.txt` có thể chứa chuỗi trông như HTML; một endpoint không có extension vẫn có thể trả JavaScript hoặc CSS nếu được cấu hình đúng.

Vì vậy, quyết định quan trọng là **`Content-Type` ở HTTP response thực tế**, không chỉ tên file hoặc URL.

### Content-Type không phải X-Content-Type-Options

Hai header làm hai việc khác nhau:

~~~http
Content-Type: text/css
X-Content-Type-Options: nosniff
~~~

- **`Content-Type`:** server thông báo nội dung là kiểu gì.
- **`X-Content-Type-Options: nosniff`:** server yêu cầu browser **không thay kiểu đã khai báo bằng cách đoán từ dữ liệu**.

**Nosniff không biến `text/plain` thành `text/javascript`.** Nếu tài nguyên là JavaScript thật, hãy **sửa server để trả MIME JavaScript đúng**, không tắt `nosniff` để browser cố đoán.

## 2. MIME sniffing và nguy cơ bảo mật

Historically, một số browser cố “giúp đỡ” khi server thiếu/sai MIME type: chúng đọc các byte đầu response và đoán đó là HTML, script, CSS hay loại file khác. Cách này có thể khiến website cũ hoạt động dù server cấu hình sai, nhưng làm mờ ranh giới giữa **dữ liệu** và **mã có thể thực thi**.

Xét tình huống giả định:

1. Website cho người dùng tải lên một file văn bản hoặc file tổng hợp.
2. Nội dung file có phần giống HTML hoặc JavaScript.
3. Server phục vụ file từ một URL có quyền đọc công khai, nhưng `Content-Type` bị thiếu hoặc sai.
4. Một trang khác tham chiếu URL đó trong vai trò tài nguyên thực thi, hoặc người dùng điều hướng trực tiếp tới file.
5. Nếu browser suy đoán file là nội dung thực thi thay vì dữ liệu, có thể xuất hiện đường khai thác XSS hoặc MIME confusion.

Đây là **mô hình nguy cơ**, không có nghĩa mọi browser, mọi context và mọi MIME mismatch đều dẫn đến thực thi. Chính sách hiện đại còn chịu tác động của Fetch, script module, CSP, CORB/CORP và những quy tắc browser khác.

### Ví dụ an toàn về sự nhầm lẫn kiểu

HTML đang tải script:

~~~html
<!DOCTYPE html>
<html lang="vi">
<head><meta charset="UTF-8"><title>MIME demo</title></head>
<body>
  <script src="/assets/mislabeled.js"></script>
</body>
</html>
~~~

Server phản hồi `/assets/mislabeled.js`:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
X-Content-Type-Options: nosniff

console.log("Đây là dữ liệu văn bản, không phải script hợp lệ");
~~~

Trình duyệt có thể ghi thông báo kiểu “Refused to execute script ... MIME type text/plain ... strict MIME type checking” và **không chạy JavaScript từ response này**. Mục đích của ví dụ là kiểm soát kiểu dữ liệu, không phải chứng minh server đã xác thực người dùng hay chống mọi loại XSS.

## 3. Cú pháp header và ý nghĩa của nosniff

Cú pháp chính:

~~~http
X-Content-Type-Options: nosniff
~~~

`nosniff` là directive được browser hỗ trợ cho header này. Không có một danh sách các giá trị “an toàn hơn” như `deny`, `strict`, `on` hay `nosniff=true` để thay thế. `DENY` thuộc ngữ nghĩa của **`X-Frame-Options`**, không phải `X-Content-Type-Options`.

Theo tài liệu Fetch/MDN, hai hệ quả cần nắm rõ:

1. **Đối với request có đích là script hoặc style:** browser chặn response nếu MIME type không thuộc kiểu hợp lệ của JavaScript hoặc không phải `text/css` tương ứng.
2. **Đối với các loại response khác, bao gồm một số điều hướng tài liệu:** browser không dùng MIME sniffing để biến nội dung thành kiểu khác; ví dụ nội dung khai báo `text/plain` không nên tự bị diễn giải thành `text/html` chỉ vì body giống HTML.

Không nên hiểu `nosniff` là “browser chặn mọi file có extension sai”. Trong phần script/style, quyết định phụ thuộc vào **request destination và MIME**, không đơn giản là extension.

### So sánh các trường hợp

| Ngữ cảnh sử dụng | Response Content-Type | Có nosniff | Kỳ vọng từ browser hiện đại |
| --- | --- | --- | --- |
| `<script src="...">` | `text/javascript` | Có | Có thể được tải và thực thi nếu chính sách khác cho phép |
| `<script src="...">` | `text/plain` | Có | Bị từ chối dùng như script |
| `<script src="...">` | `text/html` | Có | Bị từ chối dùng như script |
| `<link rel="stylesheet" ...>` | `text/css` | Có | Có thể được áp dụng nếu các điều kiện khác hợp lệ |
| `<link rel="stylesheet" ...>` | `text/plain` | Có | Bị từ chối dùng như stylesheet |
| Điều hướng tới text file | `text/plain` | Có | Không suy đoán text thành HTML |
| `fetch("/api/data")` | `application/json` | Có | Được xử lý như response dữ liệu theo chính sách fetch/CORS, không tự thành script |
| File `.js` bị trả HTML login | `text/html` | Có | Không sử dụng response HTML đó làm script |

Các dòng “có thể tải” **không có nghĩa bảo đảm thành công**: URL còn có thể bị 404, 401, CORS/CSP, integrity, lỗi mạng, hoặc nội dung JavaScript/CSS không hợp lệ về cú pháp.

### Module script còn có kiểm tra MIME chặt

~~~html
<script type="module" src="/assets/main.js"></script>
~~~

Module scripts có cơ chế strict MIME type checking; một response không có MIME JavaScript phù hợp sẽ không được thực thi như module. **Không dùng lập luận “module tự đủ an toàn nên bỏ nosniff”**: `nosniff` vẫn là header phòng thủ chung và có tác dụng ở những bối cảnh khác.

## 4. Ba tầng cần có: kiểu đúng, nosniff và quản lý dữ liệu

Một cách tư duy phù hợp:

~~~text
Đúng Content-Type?
       |
       +--> Không → sửa cấu hình server/static resources/controller
       |
       +--> Có
             |
             v
Có X-Content-Type-Options: nosniff?
       |
       +--> Không → tăng khả năng browser đoán MIME tùy context
       |
       +--> Có
             |
             v
Có chính sách bảo vệ dữ liệu và executable content?
       |
       +--> Validation upload, HTML escaping, CSP,
       |    Content-Disposition, quyền truy cập,
       |    tách domain cho file không tin cậy...
       |
       v
Kiểm thử response headers và hành vi browser thật
~~~

Header `nosniff` là **lớp phòng thủ**; không thay thế việc kiểm soát đầu vào upload, lọc nội dung nguy hiểm khi render, chống XSS hoặc phân quyền truy cập file.

Ví dụ một endpoint có `Content-Type: text/html` và `X-Content-Type-Options: nosniff`, nhưng chèn trực tiếp HTML không tin cậy vào nội dung trang, vẫn có thể bị XSS. Browser thấy header **không có nghĩa nó sẽ từ chối một trang HTML được server khai báo hợp lệ**. Phải escape hoặc sanitize dữ liệu không tin cậy theo ngữ cảnh.

## 5. Spring Security mặc định thêm X-Content-Type-Options

Trong ứng dụng Servlet có Spring Security filter chain chuẩn, Spring Security 6.x **mặc định** thêm:

~~~http
X-Content-Type-Options: nosniff
~~~

Nó là một trong các security response headers mặc định, bên cạnh những header như cache control và frame options (tập header cụ thể có thể khác theo phiên bản/giao thức).

Với cấu hình đơn giản:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().permitAll()
        );
    return http.build();
}
~~~

Spring Security vẫn có thể ghi header `nosniff` cho những response **được xử lý qua chain**, dù `permitAll()` nghĩa là trang không yêu cầu đăng nhập. **`permitAll()` không đồng nghĩa tắt security headers.**

Nếu muốn thể hiện rõ header này trong DSL:

~~~java
http.headers(headers -> headers
    .contentTypeOptions(Customizer.withDefaults())
);
~~~

Đây là mảnh cấu hình cần được đặt trong phương thức nhận `HttpSecurity`, với import `org.springframework.security.config.Customizer`. Trong ứng dụng tiêu chuẩn, việc nêu rõ này thường **không cần**, vì nosniff đã được bật theo mặc định.

### Không tắt toàn bộ security headers để khắc phục lỗi JS/CSS

Đoạn cấu hình sau là **ví dụ không nên dùng như cách chữa lỗi MIME**:

~~~java
// KHÔNG áp dụng chỉ để chữa lỗi MIME:
http.headers(headers -> headers.disable());
~~~

Nó tắt cả bộ ghi security headers, có thể loại bỏ các lớp phòng thủ không liên quan. Tương tự:

~~~java
// Minh họa cú pháp tắt riêng nosniff — không phải giải pháp đề xuất:
http.headers(headers -> headers
    .contentTypeOptions(options -> options.disable())
);
~~~

Nếu browser báo script bị chặn vì `Content-Type: text/html` hoặc `text/plain`, hãy kiểm tra **server trả gì tại URL script**, không ưu tiên bỏ header `nosniff`.

### Resource bị bỏ qua khỏi filter chain

Trong Spring Security, cấu hình `web.ignoring()` cho một tập tài nguyên có thể khiến request **không đi qua security filter chain**, đồng nghĩa các headers do Spring Security thêm cũng có thể mất. Với tài nguyên tĩnh công khai, thường ưu tiên:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/assets/**", "/public/**").permitAll()
    .anyRequest().authenticated()
)
~~~

thay vì bỏ qua hoàn toàn Spring Security filter chain chỉ để cho browser tải CSS/JS. Với nhiều `SecurityFilterChain`, cần kiểm tra đường dẫn static assets có được một chain chứa header writer xử lý hay không.

**Quan trọng:** header này thuộc **HTTP response**, không phải một `@PreAuthorize` hoặc cờ cấu hình xác thực. Người dùng không cần đăng nhập để browser nhận `nosniff`; server cần trả header trên những response cần được bảo vệ, kể cả tài nguyên công khai.

## 6. Phân biệt MIME của tài nguyên với MIME của request upload

`Content-Type` có thể xuất hiện trong cả **request** và **response**, nhưng mục đích khác nhau:

~~~http
POST /api/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=ExampleBoundary
~~~

Đây là **Content-Type request**: client mô tả payload đang gửi.

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
X-Content-Type-Options: nosniff
~~~

Đây là **Content-Type response**: server mô tả dữ liệu được trả về để browser xử lý.

`X-Content-Type-Options` là **response header**. Nó không thực hiện file upload validation và không ép server kiểm tra request upload có đúng `image/png` như client nói. Một attacker có thể tự khai `Content-Type: image/png` khi gửi dữ liệu khác; server cần kiểm tra định dạng thật theo chính sách và có thể cần chuyển đổi hoặc cách ly file.

Các kiểm tra cần cân nhắc khi upload:

1. Danh sách loại file/extension được phép theo nghiệp vụ.
2. Xác minh media type thực tế (không tin riêng header từ client).
3. Giới hạn kích thước, kiểm soát số file và đường dẫn lưu.
4. Quét nội dung độc hại/giải nén an toàn theo loại file và mức rủi ro.
5. Phát file từ domain không mang cookie của ứng dụng khi cần cách ly.
6. Dùng `Content-Type` đúng khi trả file.
7. Dùng `Content-Disposition: attachment` nếu không có lý do render inline.
8. Cân nhắc CSP/sandbox đối với nội dung HTML/SVG do người dùng kiểm soát.
9. Kiểm tra quyền xem/tải file và tránh lỗi traversal.

**Không có một header đơn lẻ nào biến file upload tùy ý thành nội dung an toàn để render trong origin của ứng dụng.**

## 7. Chương trình Java 17+ nhỏ để hiểu quy tắc MIME theo destination

Tệp `MimePolicyDemo.java` sau là một chương trình Java **độc lập**, dùng quy tắc học tập tối giản cho script và stylesheet. Nó **không tái triển khai đầy đủ Fetch/MIME Sniffing Standard**, không tính mọi JavaScript MIME alias hay các quy tắc browser đặc biệt. Mục tiêu là cho thấy **request destination** quyết định cách xem xét MIME.

~~~java
import java.util.Locale;

public class MimePolicyDemo {

    static boolean matchesDestination(String destination, String contentType) {
        if (contentType == null) {
            return false;
        }

        String mime = contentType.split(";", 2)[0]
                .trim()
                .toLowerCase(Locale.ROOT);

        return switch (destination) {
            case "script" ->
                    mime.equals("text/javascript")
                    || mime.equals("application/javascript");
            case "style" -> mime.equals("text/css");
            default -> true; // Demo: không mô hình hóa loại khác.
        };
    }

    public static void main(String[] args) {
        System.out.println(matchesDestination(
                "script", "text/javascript; charset=UTF-8"));
        System.out.println(matchesDestination(
                "script", "text/plain"));
        System.out.println(matchesDestination(
                "style", "text/css"));
        System.out.println(matchesDestination(
                "style", "text/html"));
        System.out.println(matchesDestination(
                "script", "application/javascript"));
    }
}
~~~

Biên dịch/chạy với Java 17+:

~~~bash
javac MimePolicyDemo.java
java MimePolicyDemo
~~~

Stdout xác định bởi đoạn mã:

~~~text
true
false
true
false
true
~~~

Giải thích: JavaScript MIME phù hợp có thể được dùng như script; text/plain không phù hợp làm script; CSS phải `text/css`; text/html không phù hợp làm stylesheet. **Hàm này là bài học về cách so MIME, không được dùng làm một hệ thống kiểm tra nội dung an toàn trong production.**

## 8. Ví dụ Spring Boot: trả đúng Content-Type và mặc định có nosniff

Ví dụ Spring MVC sau minh họa cả **tài nguyên đúng MIME** và **tài nguyên cố tình gắn sai MIME** để quan sát browser từ chối. Nội dung JavaScript/CSS chỉ là chuỗi vô hại, không cần database.

Dự án dùng **Java 17+, Spring Boot 3.3.x và Spring Security 6.3.x**.

### 8.1. Cấu trúc thư mục

~~~text
mime-security-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/example/mimesecurity/
│   ├── MimeSecurityApplication.java
│   ├── SecurityConfig.java
│   └── ResourcesController.java
└── src/test/java/example/mimesecurity/
    └── MimeSecurityTest.java
~~~

### 8.2. settings.gradle và build.gradle

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'mime-security-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Khi ghép vào dự án Spring Boot hiện có, chỉ bổ sung dependencies cần thiết; không tạo trùng plugin/version.

### 8.3. MimeSecurityApplication.java

Tệp `src/main/java/example/mimesecurity/MimeSecurityApplication.java`:

~~~java
package example.mimesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MimeSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(MimeSecurityApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig.java

Tệp `src/main/java/example/mimesecurity/SecurityConfig.java`:

~~~java
package example.mimesecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/private").authenticated()
                .anyRequest().permitAll()
            )
            .httpBasic(Customizer.withDefaults())
            .headers(headers -> headers
                .contentTypeOptions(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Dù có dòng `.contentTypeOptions(Customizer.withDefaults())` để nêu rõ mục tiêu, Spring Security **vốn đã bật `nosniff` mặc định** khi security headers không bị vô hiệu hóa. Chúng ta để `/private` cần đăng nhập nhằm chứng minh phản hồi 401 trong filter chain cũng có thể kèm header; các URL khác công khai nhưng **vẫn đi qua chain**.

Dự án không có endpoint ghi dữ liệu, chỉ sử dụng GET, nên ví dụ không điều chỉnh CSRF. Nếu bổ sung POST/PUT/DELETE hoặc browser session, hãy áp dụng phân quyền và CSRF theo kiến trúc thực tế.

### 8.5. ResourcesController.java

Tệp `src/main/java/example/mimesecurity/ResourcesController.java`:

~~~java
package example.mimesecurity;

import java.util.Map;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ResourcesController {

    @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
    public String index() {
        return """
                <!doctype html>
                <html lang="vi">
                <head>
                  <meta charset="UTF-8">
                  <link rel="stylesheet" href="/assets/style.css">
                  <link rel="stylesheet" href="/assets/mislabeled.css">
                </head>
                <body>
                  <h1>MIME demo</h1>
                  <script src="/assets/app.js"></script>
                  <script src="/assets/mislabeled.js"></script>
                </body>
                </html>
                """;
    }

    @GetMapping(value = "/assets/app.js", produces = "text/javascript")
    public String script() {
        return "console.log('correct JS MIME');";
    }

    @GetMapping(value = "/assets/mislabeled.js",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String mislabeledScript() {
        return "console.log('MIME mismatch');";
    }

    @GetMapping(value = "/assets/style.css", produces = "text/css")
    public String style() {
        return "body { color: navy; }";
    }

    @GetMapping(value = "/assets/mislabeled.css",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String mislabeledStyle() {
        return "body { color: navy; }";
    }

    @GetMapping(value = "/api/info",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> info() {
        return Map.of("message", "json data");
    }

    @GetMapping("/uploads/example.txt")
    public ResponseEntity<String> download() {
        String textWithHtml = "<html><body>Just text</body></html>";

        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename("example.txt")
                                .build()
                                .toString())
                .body(textWithHtml);
    }

    @GetMapping("/private")
    public String privatePage() {
        return "private data";
    }
}
~~~

Lưu ý:

- `/assets/app.js` khai báo MIME JavaScript đúng, nên browser có thể chạy.
- `/assets/mislabeled.js` có phần mở rộng `.js` và body JavaScript, nhưng server **cố ý** trả `text/plain`. Với `nosniff`, browser phải từ chối sử dụng resource đó như script.
- `/assets/style.css` trả `text/css`, còn `/assets/mislabeled.css` trả `text/plain`. Browser không sử dụng nhầm text/plain như CSS trong ngữ cảnh stylesheet.
- `/api/info` trả JSON để phân biệt response data và script.
- `/uploads/example.txt` cố tình chứa chuỗi trông như HTML nhưng trả `text/plain` và `Content-Disposition: attachment`. Đây là ví dụ phục vụ **download** thay vì render trong origin ứng dụng.
- `@RestController` trả trực tiếp body, còn `produces`/`ResponseEntity.contentType(...)` quyết định media type; extension URL không tự thay thế chúng.
- `/private` được security chain yêu cầu xác thực. Không có username/password trong ví dụ vì không nhằm minh họa login; request chưa xác thực thường nhận 401 với HTTP Basic entry point.
- Mẫu không thực hiện upload thật hay validation nội dung file, không được dùng nguyên như giải pháp upload production.

**Cảnh báo khi sao chép:** phiên bản Java 17 hỗ trợ text block `"""` trong phương thức `index()`. Các đoạn Java trên là những file độc lập có package/import, không cần dùng JSP hoặc Thymeleaf.

## 9. Kiểm thử header và MIME bằng MockMvc

MockMvc kiểm tra **response headers do Spring Security và Spring MVC thực tế tạo ra**, nhưng **không chạy engine thực thi JavaScript/CSS của trình duyệt**. Do đó, ta kiểm tra server trả đúng các điều kiện để browser có thể áp dụng `nosniff`, không tuyên bố một phép thử MockMvc đã nhìn thấy browser từ chối thực thi.

Tệp `src/test/java/example/mimesecurity/MimeSecurityTest.java`:

~~~java
package example.mimesecurity;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MimeSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void htmlIsServedAsHtmlWithNosniff() throws Exception {
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_HTML))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void javascriptIsServedWithCorrectMime() throws Exception {
        mvc.perform(get("/assets/app.js"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.parseMediaType("text/javascript")))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void cssIsServedWithTextCss() throws Exception {
        mvc.perform(get("/assets/style.css"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.parseMediaType("text/css")))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void mislabeledScriptIsStillPlainText() throws Exception {
        mvc.perform(get("/assets/mislabeled.js"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void mislabeledStyleIsStillPlainText() throws Exception {
        mvc.perform(get("/assets/mislabeled.css"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void jsonHasApplicationJsonAndNosniff() throws Exception {
        mvc.perform(get("/api/info"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void untrustedTextIsAttachmentNotHtml() throws Exception {
        mvc.perform(get("/uploads/example.txt"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN))
                .andExpect(header().string(
                        HttpHeaders.CONTENT_DISPOSITION,
                        containsString("attachment")))
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void publicAssetStillGetsSecurityHeader() throws Exception {
        mvc.perform(get("/assets/style.css"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string(
                        "X-Content-Type-Options", "nosniff"));
    }
}
~~~

Lệnh chạy:

~~~bash
./gradlew test --tests '*MimeSecurityTest'
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "*MimeSecurityTest"
~~~

**Kết quả kỳ vọng:** 9 phép thử thành công với các dependencies và phiên bản đã nêu. Đó là kết quả **kỳ vọng theo mã**, không phải báo cáo thực tế đã chạy trong môi trường này.

Kiểm thử chứng minh:

1. Header `nosniff` được gắn vào response public HTML, CSS, JS, JSON, text download và một phản hồi bảo mật.
2. `Content-Type` phân biệt đúng JavaScript/CSS với tài nguyên cố ý dán nhãn sai.
3. Tài nguyên công khai đi qua `SecurityFilterChain` vẫn nhận security headers.
4. MockMvc **không** kiểm tra browser có thực thi `app.js` hoặc từ chối `mislabeled.js`. Cần thử browser thật như phần sau.

## 10. Xác minh trong trình duyệt thật

Dùng dự án mẫu từ phần 8. Sau khi có Gradle wrapper tương thích:

~~~bash
./gradlew bootRun
~~~

Mở `http://localhost:8080/` rồi Developer Tools → Network/Console.

Quan sát:

1. `GET /` trả `text/html` và `X-Content-Type-Options: nosniff`.
2. `GET /assets/app.js` trả `text/javascript` và `nosniff`. Console có thông báo từ script đúng MIME.
3. `GET /assets/mislabeled.js` trả `text/plain` và `nosniff`. Browser từ chối thực thi như script; thông điệp console thay đổi theo browser.
4. `GET /assets/style.css` trả `text/css` và được áp dụng.
5. `GET /assets/mislabeled.css` trả `text/plain`, nên browser không dùng nó làm stylesheet.
6. `GET /uploads/example.txt` có `text/plain` và `Content-Disposition: attachment`, thường được xử lý như file tải xuống theo chính sách trình duyệt.

**Không cần tắt nosniff để tạo trường hợp minh họa.** Các endpoint `mislabeled` cố ý có MIME sai để kiểm thử khả năng browser từ chối. Hệ thống thực phải **sửa MIME trả về**.

### Khi browser báo lỗi MIME strict checking

Ví dụ log khái quát:

~~~text
Refused to execute script because its MIME type ("text/html")
is not executable, and strict MIME type checking is enabled.
~~~

Nguyên nhân thường gặp **không phải file script hỏng**, mà request đến `/assets/app.js` đã bị server trả **HTML**:

- URL script sai, dẫn tới trang lỗi 404 dạng HTML.
- Người dùng chưa đăng nhập, server redirect tới `/login` và trả HTML login.
- Reverse proxy/ngăn cache trả trang HTML fallback của SPA cho đường `.js`.
- Spring Security filter chain không cho phép tải static asset, trả error page.
- Static resources build/deploy sai path hoặc MIME mapping trong server.

Cách kiểm tra: mở **Network → request của file JS → Status, Redirect chain, Response headers, Preview/Response body**. Nếu body là trang login/404, sửa routing/authorization. Đừng chỉ nhìn extension `.js` rồi tắt `X-Content-Type-Options`.

### Khi file CSS không hoạt động

Nếu `<link rel="stylesheet" href="/assets/style.css">` bị chặn, kiểm tra request status, `Content-Type: text/css`, `X-Content-Type-Options`, response body, browser console và CSP. Một endpoint trả CSS dưới `application/octet-stream` hay `text/plain` không tương đương `text/css`. Trả đúng MIME là cách xử lý chính.

## 11. Static resources, Spring MVC và máy chủ proxy

Spring Boot/Spring MVC thường phục vụ static resources từ vị trí mặc định như:

~~~text
src/main/resources/static/
src/main/resources/public/
src/main/resources/resources/
src/main/resources/META-INF/resources/
~~~

Ví dụ khi đặt file `src/main/resources/static/assets/app.js`, Spring MVC resource handler sẽ xử lý URL `/assets/app.js` theo cấu hình. Trong ví dụ hoàn chỉnh, resource được trả bởi Controller để chủ động minh họa `produces`; **không tạo thêm file static trùng đường dẫn** khi chạy cùng project, tránh mapping cạnh tranh.

Nếu static content được phục vụ **ngoài Spring Security filter chain**, chẳng hạn bởi Nginx/CDN, header mặc định của Spring Security **không tự lan ra đến response do CDN tạo**. Hãy kiểm tra header ở **điểm người dùng thực sự nhận response**, không chỉ ở backend local.

Các trường hợp cần xác minh:

- Spring Security cho phép assets bằng `permitAll`, giữ filter chain tham gia.
- Controller có `produces` hoặc `ResponseEntity.contentType(...)` đúng.
- Static resource handler nhận đúng loại MIME từ file mapping.
- Reverse proxy không ghi đè `Content-Type` hoặc xóa `X-Content-Type-Options`.
- CDN và cache không phục vụ một bản HTML lỗi như file `.js`/`.css`.
- Các HTTP status 200/304/401/403/404 được cấu hình nhất quán; đừng suy ra mọi response ngoài filter chain đều có header.
- Có kiểm tra gzip/brotli và `Content-Encoding` riêng với `Content-Type`: nén nội dung không biến CSS thành JavaScript.

### Content-Encoding khác Content-Type

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: text/javascript
Content-Encoding: gzip
X-Content-Type-Options: nosniff
~~~

`Content-Type` mô tả loại nội dung sau khi giải mã các content codings, còn `Content-Encoding` nói cách dữ liệu được nén/truyền. **Không sửa lỗi MIME bằng cách đổi gzip hoặc extension.** Phải đảm bảo đúng loại media và cấu hình nén độc lập.

## 12. Kiểm soát file upload và tài nguyên người dùng tạo

File upload là một trường hợp nhạy cảm vì dữ liệu **không hoàn toàn thuộc quyền kiểm soát của server**. Nếu website cho tải lên `avatar.svg`, `report.html` hoặc một tệp có cấu trúc phức tạp, browser có thể có cách xử lý riêng khi điều hướng, nhúng hay tải xuống.

Các lớp phòng thủ nên kết hợp:

| Lớp | Việc cần làm |
| --- | --- |
| Input validation | Kiểm tra loại file được phép, magic bytes, kích thước, cấu trúc |
| Storage | Đổi tên file tránh path traversal, hạn chế quyền thực thi |
| Response MIME | Gắn `Content-Type` đúng với loại file thật |
| Nosniff | Gửi `X-Content-Type-Options: nosniff` |
| Download policy | Dùng `Content-Disposition: attachment` cho nội dung không cần render inline |
| Domain isolation | Phục vụ nội dung không tin cậy từ một origin riêng, không có cookie phiên ứng dụng |
| CSP/sandbox | Kiểm soát cách HTML/SVG có thể chạy script hoặc nhúng |
| Authorization | Kiểm tra ai được tải/xem tệp |
| Audit | Ghi log metadata an toàn, không tiết lộ file hay credential nhạy cảm |

Ví dụ một endpoint trả file văn bản chứa chuỗi HTML:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Disposition: attachment; filename="report.txt"
X-Content-Type-Options: nosniff

<html><body>Untrusted text</body></html>
~~~

Browser được hướng dẫn xử lý như file tải xuống thay vì một trang HTML của ứng dụng. Nhưng **Content-Disposition không thay thế quét/validate file**, và những client khác có thể xử lý theo khả năng riêng. Không bao giờ dựa chỉ vào tên `report.txt` để quyết định dữ liệu an toàn.

### Có nên đặt toàn bộ file upload dưới cùng hostname với ứng dụng không?

Nếu file không đáng tin có thể được diễn giải thành active content (như HTML/SVG), một origin **riêng**, không có cookie đăng nhập của ứng dụng, thường là phòng thủ đáng cân nhắc. Nó giúp giảm tác động nếu browser hoặc một cấu hình MIME xử lý nội dung không như mong muốn. Cần đồng thời có chính sách CORS/CORP và quyền tải phù hợp, thay vì chuyển origin rồi cho phép truy cập mọi dữ liệu nhạy cảm.

## 13. X-Content-Type-Options không thay CSP, CORS hoặc CORP

Các header/chính sách làm những việc khác nhau:

| Cơ chế | Chức năng chính | Không thay thế |
| --- | --- | --- |
| `Content-Type` | Khai báo media type của response | Việc xác minh dữ liệu nguồn đáng tin |
| `X-Content-Type-Options: nosniff` | Tránh browser suy đoán MIME, chặn script/style sai MIME | CSP, file upload validation, XSS escaping |
| `Content-Security-Policy` | Giới hạn nguồn được tải/chạy, inline script và một số loại nội dung | Việc đặt đúng Content-Type |
| `Cross-Origin Resource Sharing (CORS)` | Điều khiển quyền JS từ origin khác đọc response ở browser | Authentication, CSRF, MIME kiểm tra |
| `Cross-Origin-Resource-Policy (CORP)` | Giới hạn một số dạng tải/nhúng tài nguyên cross-origin/no-cors | Authorization và Content-Type |
| `Content-Disposition` | Gợi ý inline hay tải xuống, tên file | Kiểm tra nội dung/file độc hại |
| `X-Frame-Options` / CSP frame-ancestors | Chống nhúng trang trái phép trong frame | Bảo vệ script MIME |
| `Strict-Transport-Security` | Yêu cầu browser dùng HTTPS cho host đã khai báo | Chống mọi XSS hoặc MIME confusion |

**CORS và nosniff có thể cùng xuất hiện** trên API JSON, nhưng không có nghĩa response tự trở thành an toàn nếu server trả HTML nhạy cảm cho một origin không tin cậy. Mỗi header có mô hình nguy cơ riêng.

### Cần tránh hiểu nhầm về cross-origin data

Một số browser có các cơ chế bảo vệ phản hồi cross-origin như CORB/ORB, và `nosniff` có thể tương tác với cách phân loại nội dung. Không nên viết quy tắc phổ quát rằng “nosniff chặn mọi fetch cross-origin” hoặc “nosniff thay CORS”. Với `fetch`, JS vẫn tuân theo SOP/CORS và chính sách request mode/credentials riêng; kiểu MIME chỉ là một phần của cơ chế xử lý response.

## 14. WebFlux có header tương tự nhưng API khác

Với Spring WebFlux, phần bảo mật dùng `ServerHttpSecurity` và `SecurityWebFilterChain`, **không** dùng nguyên `HttpSecurity` của Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges ->
                        exchanges.anyExchange().permitAll())
                .build();
    }
}
~~~

Đây là một cấu hình reactive **minh họa**, cần chạy trong ứng dụng Spring WebFlux thay vì project Servlet ở phần 8. Spring Security WebFlux cũng có hỗ trợ security response headers, bao gồm `X-Content-Type-Options` theo mặc định phù hợp. Tương tự Servlet, vẫn phải khai báo đúng MIME của response thực tế; việc phản hồi là `Mono<String>` hay `Flux<DataBuffer>` không tự biến dữ liệu thành JavaScript/CSS đúng kiểu.

## 15. Bảng gỡ lỗi nhanh

| Vấn đề | Cần kiểm tra | Hướng sửa |
| --- | --- | --- |
| JS bị báo MIME `text/html` | Redirect login, SPA HTML fallback, 404/500 page | Sửa URL/routing/filter chain và MIME JS |
| JS bị báo MIME `text/plain` | Controller `produces`/static mapping sai | Trả `text/javascript` |
| CSS bị báo MIME `application/octet-stream` | Web server MIME mapping sai | Trả `text/css` |
| Script bị chặn dù Content-Type đúng | CSP, CORS với module, integrity, error JS | Kiểm tra Console và Network |
| Không có `X-Content-Type-Options` | Request không đi qua Spring filter, headers bị tắt, proxy/CDN | Giữ filter chain hoặc cấu hình header ở nguồn thực tế |
| Header có nosniff nhưng file upload vẫn nguy hiểm | File active content được phép render trong origin ứng dụng | Content-Disposition, origin riêng, CSP, validation |
| Browser chặn đọc response API | CORS hoặc authentication, không nhất thiết MIME | Kiểm tra Origin, CORS, HTTP status |
| MIME đúng trong local nhưng sai trên CDN | Proxy/CDN rewrite/cache, version deploy | Kiểm tra headers công khai |
| `Content-Type` nhầm request và response | Xem nhầm panel/header | Kiểm tra Response Headers tại URL tài nguyên |
| `nosniff` bị vô hiệu hóa để sửa assets | Dữ liệu JS/CSS thực ra được gắn sai kiểu | Khôi phục nosniff, sửa Content-Type |
| 404 JSON không có header | Không đi qua chain hoặc error dispatch khác | Kiểm tra toàn bộ đường phản hồi bảo mật |
| 401/login HTML ở URL `.js` | Script yêu cầu auth, chưa công khai assets | `permitAll` cho assets phù hợp, không bỏ filter chain |

Một phép kiểm tra bằng curl:

~~~bash
curl -i http://localhost:8080/assets/app.js
curl -i http://localhost:8080/assets/mislabeled.js
curl -i http://localhost:8080/assets/style.css
curl -i http://localhost:8080/uploads/example.txt
~~~

Hãy xem `Content-Type` và `X-Content-Type-Options` của từng response. **Curl không thực thi JavaScript và không kiểm tra chính sách browser**, nên kết quả 200 từ curl không chứng minh browser sẽ chấp nhận asset.

## 16. Những sai lầm cần tránh

1. **“Đã có nosniff nên không cần đặt Content-Type.”** Sai. Browser cần MIME đúng để nhận dạng script/CSS.
2. **“Đuôi .js luôn được thực thi.”** Sai. Response `text/plain` với nosniff sẽ bị chặn ở script destination.
3. **“Nosniff tự chuyển text/plain thành JavaScript.”** Sai. Nó yêu cầu tôn trọng kiểu đã khai báo.
4. **“Nosniff sẽ sửa XSS trong HTML.”** Sai. XSS vẫn xảy ra nếu render HTML không tin cậy như HTML hợp lệ.
5. **“Có nosniff là upload arbitrary file an toàn.”** Sai. Cần validation, isolation, download policy và CSP khi cần.
6. **“Tắt header để trang hoạt động.”** Đó chỉ là cách che lỗi MIME server và có thể làm giảm bảo vệ.
7. **“Chỉ URL có login mới cần security header.”** Static assets công khai cũng nên được header writer xử lý.
8. **“`web.ignoring()` giống `permitAll()`.”** Sai; ignoring có thể bỏ qua toàn bộ filter chain và mất headers.
9. **“Tất cả response có extension .css đều hợp lệ làm stylesheet.”** Sai nếu server trả HTML hoặc text/plain.
10. **“X-Content-Type-Options áp dụng kiểm tra file upload input.”** Sai. Nó là response header cho browser.
11. **“CORS bị lỗi vì nosniff.”** Có thể là hai lỗi độc lập; phải đọc Network/Console.
12. **“CSP và nosniff thay thế nhau.”** Chúng bổ sung nhưng không thay nhau.
13. **“JSON có thể chạy như JS vì giống object.”** Không dùng MIME data để thay script; browser áp dụng kiểm soát theo destination.
14. **“Content-Encoding gzip quyết định media type.”** Sai. Đó là cơ chế nén/truyền.
15. **“Test MockMvc khẳng định browser đã từ chối chạy script.”** Sai. MockMvc chỉ quan sát response server.
16. **“Nếu server chạy đúng local, CDN tự có header.”** Không chắc. Phải kiểm tra response cuối người dùng nhận.
17. **“Header nosniff áp dụng mọi request như firewall.”** Sai. Nó định hướng browser xử lý response, không chặn request tới server.
18. **“HTTP status 200 chứng minh script tải thành công.”** Browser còn có thể từ chối do MIME/CSP/module rules.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** `X-Content-Type-Options: nosniff` có thay đổi `Content-Type: text/plain` thành `text/javascript` không?

**Đáp án:** Không. Nosniff yêu cầu browser tôn trọng `Content-Type` đã khai báo và hạn chế sniffing.

**Câu 2.** Một trang tải `/assets/app.js`, response 200 nhưng `Content-Type: text/html` kèm nosniff. Vì sao browser từ chối?

**Đáp án:** Request đang cần tài nguyên script nhưng nhận HTML; MIME không phải JavaScript. Có thể URL sai, 404/login fallback hoặc server cấu hình sai.

**Câu 3.** File `/assets/style.css` trả `Content-Type: text/plain`. Nên sửa gì?

**Đáp án:** Sửa server trả `text/css` và giữ nosniff. Không tắt header để browser cố đoán CSS.

**Câu 4.** API trả JSON với `application/json` và nosniff. Có nghĩa API đã xác thực người dùng chưa?

**Đáp án:** Không. MIME và nosniff không thay authentication/authorization.

**Câu 5.** Người dùng tải lên HTML và server phát lại `Content-Type: text/html` trong cùng origin. Có nosniff là đủ chống XSS không?

**Đáp án:** Không. Server khai báo đây là HTML; cần xử lý nội dung không tin cậy bằng validation, isolation, Content-Disposition, CSP/sandbox và chính sách phù hợp.

**Câu 6.** Tại sao `web.ignoring()` có thể làm mất nosniff ở tài nguyên static?

**Đáp án:** Vì request bỏ qua Spring Security filter chain, trong đó có thành phần thêm security headers.

**Câu 7.** MockMvc xác nhận status 200, `Content-Type: text/plain` và nosniff cho `/assets/mislabeled.js`. Có chứng minh browser thật đã chặn script không?

**Đáp án:** Chưa. MockMvc xác minh headers phía server; để xác nhận hành vi browser, cần kiểm tra Network/Console trên trình duyệt thật.

**Câu 8.** `X-Content-Type-Options` và `Content-Security-Policy` có cùng tác dụng không?

**Đáp án:** Không. Nosniff chống suy đoán MIME; CSP giới hạn nguồn và loại thực thi/nội dung theo policy. Chúng bổ sung nhau.

**Câu 9.** Header thuộc request hay response?

**Đáp án:** `X-Content-Type-Options` là **response header**. `Content-Type` có thể xuất hiện ở request hoặc response nhưng có ý nghĩa tương ứng.

**Câu 10.** Khi file JS bị redirect tới trang login HTML, có nên cấu hình thêm `Content-Type: text/javascript` trên trang login?

**Đáp án:** Không. Phải sửa đường truy cập assets, cấu hình permitAll/routing và redirect phù hợp; không gắn kiểu JS cho HTML login.

**Câu 11.** Tại sao script module thường yêu cầu MIME JavaScript đúng ngay cả khi một browser có những cơ chế sniffing cũ?

**Đáp án:** Module scripts áp dụng strict MIME checking. Đó không phải lý do để bỏ bảo vệ nosniff ở các ngữ cảnh khác.

## 18. Checklist trước khi triển khai

- Mọi HTML, JavaScript, CSS, JSON, ảnh và file download có `Content-Type` chính xác chưa?
- Browser nhận `X-Content-Type-Options: nosniff` trên các response liên quan chưa?
- Resource công khai có đi qua Spring Security filter chain hoặc được edge server thêm security headers chưa?
- Có kiểm tra JS/CSS thực tế trong Network khi status 200 nhưng browser vẫn báo MIME error chưa?
- Các đường redirect login/SPA fallback có vô tình trả HTML cho URL `.js`/`.css` chưa?
- Có phân biệt kiểm tra MIME của request upload và response được tải về chưa?
- Với file upload, đã có validation, size limit, Content-Disposition và origin isolation phù hợp chưa?
- CSP, CORS, CORP, CSRF và quyền truy cập đã được thiết kế riêng theo threat model chưa?
- Đã kiểm tra header cuối cùng sau reverse proxy/CDN thay vì chỉ backend local chưa?
- Đã kiểm tra các status/error pages quan trọng khi request qua hoặc ngoài filter chain chưa?
- Đã có MockMvc tests cho HTML, JS, CSS, JSON, tài nguyên dán nhãn sai và unauthorized response chưa?
- Đã chạy thử browser thực tế để xác nhận resource dán nhãn sai **không được thực thi** chưa?

**Kết luận:** `X-Content-Type-Options: nosniff` giúp trình duyệt **không “đoán lại” media type** mà server đã khai báo, đặc biệt ngăn script và stylesheet được sử dụng khi MIME sai. Trong Spring Security 6.x, header này thường **đã bật mặc định** cho response qua filter chain. Cách triển khai đúng là **giữ nosniff, trả Content-Type chính xác, quản lý nội dung người dùng tải lên và kiểm thử response thực tế ở trình duyệt**.

## Tài liệu đối chiếu

- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): mặc định `nosniff` và lý do hạn chế MIME sniffing.
- [Spring Security — Servlet Security Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): header writer và DSL cấu hình.
- [Spring Security — Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `headers(...contentTypeOptions(...))` trong cấu hình hiện đại.
- [MDN — X-Content-Type-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options): script/style destination, browser MIME handling.
- [MDN — MIME type verification](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/MIME_types): yêu cầu MIME đúng cho JS/CSS.
- [MDN — Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type): media type trong request/response.
- [OWASP — HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html): khuyến nghị `nosniff` và Content-Type đúng.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): các lớp bảo vệ nội dung upload không tin cậy.
