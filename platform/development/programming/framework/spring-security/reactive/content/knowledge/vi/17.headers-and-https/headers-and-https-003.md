# X-Content-Type-Options và phòng tránh suy đoán sai kiểu nội dung

## Mục tiêu và bối cảnh

Bài thuộc nhóm **Header và HTTPS** trong module **Spring Security - reactive**. Khi trình duyệt tải một file JavaScript, CSS, JSON, HTML hoặc tài liệu do người dùng tải lên, server phải chỉ rõ **kiểu nội dung** bằng header `Content-Type`. Trong lịch sử, một số trình duyệt cố *đoán* kiểu nội dung từ các byte đầu tiên của response, ngay cả khi server không gửi hoặc gửi sai kiểu. Hành vi **MIME sniffing** này có thể khiến một tài liệu vốn chỉ được lưu như dữ liệu bị xử lý như **script hoặc HTML**, tạo rủi ro cross-site scripting (XSS) và rò rỉ dữ liệu.

Header bảo vệ:

```http
X-Content-Type-Options: nosniff
```

yêu cầu trình duyệt tôn trọng MIME type đã khai báo thay vì tự đoán theo các quy tắc mà `nosniff` áp dụng. **Spring Security WebFlux mặc định thêm header này** trong các response đi qua security chain thông thường, nhưng header chỉ có giá trị khi ứng dụng **cũng trả đúng `Content-Type`** cho từng tài nguyên.

Sau bài này, bạn có thể:

1. Phân biệt **MIME type**, `Content-Type` và kỹ thuật **content sniffing**.
2. Giải thích hiệu lực của `X-Content-Type-Options: nosniff` khi browser tải `<script>` và `<link rel="stylesheet">`.
3. Nêu rõ `nosniff` giúp giảm rủi ro MIME confusion/XSS nhưng **không phải** bộ lọc mã độc, trình kiểm tra file, CSP hay cơ chế chống mọi XSS.
4. Phân biệt response `text/javascript`, `text/css`, `application/json`, `text/plain`, `text/html` và `application/octet-stream`.
5. Sử dụng đúng API `ServerHttpSecurity`/`SecurityWebFilterChain` của Spring Security **reactive**, hiểu default security headers và cách kiểm tra bằng HTTP.
6. Dựng ứng dụng **Java 17+, Spring Boot 3.3.13, Spring WebFlux** có tài nguyên JS/CSS đúng MIME và cố ý sai MIME để quan sát browser block.
7. Kiểm thử bằng `WebTestClient`: status, `Content-Type`, `X-Content-Type-Options`, nội dung response và behavior security.
8. Biết xử lý an toàn tài liệu/file upload, download, static resources, reverse proxy, response 401/403/500 và cache/CDN.
9. Phân biệt `nosniff` với CSP, CORS, CSRF, HSTS, `Content-Disposition` và nội dung HTML thực sự được phép chạy.
10. Chẩn đoán thông báo **“Refused to execute script ... MIME type ... strict MIME type checking”** trong DevTools.

**Kết luận cốt lõi:** `nosniff` **không tự sửa sai `Content-Type`**. Nếu script được trả là `text/plain`, browser sẽ chặn script thay vì tự đoán đây là JavaScript. Cách sửa đúng là gửi MIME type phù hợp và giữ `nosniff` bật.

## 1. MIME type và Content-Type là gì?

**MIME type** (media type) phân loại dữ liệu được trả về. Header `Content-Type` cho client biết response body là loại nội dung gì:

```http
HTTP/1.1 200 OK
Content-Type: text/javascript; charset=UTF-8
X-Content-Type-Options: nosniff

document.title = "Demo";
```

Trong ví dụ, `Content-Type` thông báo đây là JavaScript; `nosniff` cho biết browser không nên coi những byte đó thành kiểu khác theo cơ chế sniffing bị hạn chế.

Các cặp thường gặp:

| Nội dung thật | Content-Type thường dùng | Lưu ý |
| --- | --- | --- |
| Trang HTML | `text/html; charset=UTF-8` | HTML có thể thực thi script khi được phép bởi các chính sách khác |
| JavaScript | `text/javascript` | MIME type chuẩn cho script; một số JavaScript MIME khác còn được chấp nhận vì tương thích |
| CSS | `text/css` | Với stylesheet, đây là kiểu browser cần |
| JSON | `application/json` | Không tự biến thành một script thực thi được qua `<script>` khi có `nosniff` |
| Văn bản đơn thuần | `text/plain; charset=UTF-8` | Không được browser tự coi là HTML/JS chỉ từ nội dung |
| File nhị phân không định nghĩa | `application/octet-stream` | Thường kết hợp `Content-Disposition: attachment` khi muốn download |
| SVG | `image/svg+xml` | Có nội dung XML, đôi khi có hành vi active tùy bối cảnh; cần xử lý upload đặc biệt |
| PNG | `image/png` | Không lấy đuôi `.png` làm bằng chứng nội dung thật |
| JPEG | `image/jpeg` | Không nhầm với `image/jpg` không chuẩn |
| PDF | `application/pdf` | PDF có rủi ro riêng; policy preview/download phải được thiết kế |
| CSV | `text/csv; charset=UTF-8` | Dữ liệu CSV tải về cần thêm lưu ý formula injection khi mở bằng bảng tính |

**Extension không phải Content-Type.** Một URL kết thúc bằng `.js` có thể được server trả `Content-Type: text/plain` vì cấu hình CDN/nginx sai; browser quyết định xử lý dựa trên response headers, request destination, mode và policy. Ngược lại, client có thể gửi file tên `image.png` nhưng nội dung chứa HTML/script. Server phải tự xác minh file, không tin mỗi filename hoặc `Content-Type` trong multipart upload.

**Content-Type khác Content-Encoding.** `Content-Encoding: gzip` nói body được nén như thế nào. Sau khi giải nén, một file JavaScript vẫn có MIME type là `text/javascript`; không đặt `Content-Type: application/gzip` chỉ vì truyền JavaScript đã nén gzip qua HTTP.

## 2. Content sniffing: tại sao việc đoán MIME gây nguy hiểm?

Khi server không khai báo MIME hoặc khai báo sai, một browser trước đây có thể nhìn vào các byte đầu:

```text
Server nói: Content-Type: text/plain
Body thực:  <script>/* code điều khiển trang */</script>

Trình duyệt sniff: "Trông giống HTML/JS, có lẽ nên xử lý như active content?"
                         |
                         v
                 Rủi ro XSS / MIME confusion
```

Một tình huống điển hình:

1. Ứng dụng cho người dùng tải lên một file, lưu nó trên cùng hostname với ứng dụng đã đăng nhập.
2. File được server trả về mà không có hoặc với Content-Type không đáng tin.
3. Nội dung là một **polyglot** hoặc cú pháp có thể được trình duyệt hiểu như JavaScript/HTML.
4. Tài liệu bị nhúng vào trang qua `<script>` hoặc được mở trực tiếp trong browsing context, tùy MIME và chính sách của browser.
5. Nếu browser xử lý file như active content trong origin có quyền, mã tấn công có thể truy cập các dữ liệu mà origin ấy được phép truy cập.

`nosniff` làm giảm một lớp nhầm lẫn này, bằng cách không cho phép browser tự nâng một file khai báo không phải script/style thành script/style theo cách bị cấm.

Tuy nhiên, nếu server **cố tình trả nội dung không tin cậy với `Content-Type: text/html`** trên cùng origin, header `nosniff` không biến trang HTML ấy thành text vô hại. Browser được thông báo đó thực sự là HTML. Vì vậy **đối với upload không tin cậy** còn cần tách domain, áp đặt download, làm sạch nội dung và policy CSP/HTML phù hợp.

## 3. Chính xác nosniff tác động đến request nào?

### 3.1. Script destination

Với một `<script src="...">`:

```html
<script src="/assets/good.js" defer></script>
<script src="/assets/bad.js" defer></script>
```

Nếu response đầu có:

```http
Content-Type: text/javascript
X-Content-Type-Options: nosniff
```

thì browser có thể thực thi JavaScript sau khi thỏa các điều kiện tải script khác như CSP, CORS với module và trạng thái mạng.

Nếu response thứ hai có:

```http
Content-Type: text/plain
X-Content-Type-Options: nosniff
```

thì browser phải từ chối thực thi nó trong **script request destination** thay vì sniff nội dung thành JavaScript.

**Cần hiểu đúng:** Body của `bad.js` có thể chứa JavaScript hợp lệ; **chính MIME response không khớp** làm browser chặn. Đổi tên URL thành `good.js` không sửa được lỗi; phải sửa response Content-Type.

Browser hiện đại cũng áp dụng các quy tắc MIME nghiêm ngặt bổ sung cho **JavaScript modules** (`type="module"`) và một số cơ chế tải khác. Không nên dùng kết quả một loại classic script để suy ra mọi kiểu script đều giống nhau khi không có `nosniff`.

### 3.2. Stylesheet destination

Khi HTML chứa:

```html
<link rel="stylesheet" href="/assets/good.css">
<link rel="stylesheet" href="/assets/bad.css">
```

browser kỳ vọng response dành cho `style` có `Content-Type: text/css`. Nếu `bad.css` được trả dưới kiểu `text/plain` với `nosniff`, browser chặn stylesheet sai MIME. Điều này có thể khiến layout mất màu/font vì **server đã khai báo sai kiểu**, không phải do Spring Security từ chối authorization.

### 3.3. Navigation/document và những response khác

Theo tài liệu MDN/Fetch, `nosniff` còn yêu cầu các ngữ cảnh không phải script/style tôn trọng Content-Type hơn thay vì suy đoán lại. Ví dụ một response khai báo `text/plain` nhưng chứa `<h1>...` hoặc `<script>...` sẽ không được browser tự biến thành một trang `text/html` chỉ vì byte trông giống HTML.

Nhưng **không suy rộng thành “nosniff chặn mọi tài nguyên sai MIME trên toàn bộ Web”**:

- Ở **script/style destinations**, có điều kiện **blocking** với MIME không phù hợp.
- Với **navigation/document**, browser sử dụng thông tin MIME được cung cấp; hành vi hiển thị/download có thể khác theo browser và header khác.
- Với **`fetch()`**, việc nhận bytes, gọi `response.text()` hoặc `response.json()` phụ thuộc CORS, body parsing và JS code; `nosniff` **không phải trình kiểm tra JSON schema**. `response.json()` vẫn có thể parse hoặc thất bại dựa trên nội dung chứ không tự thực hiện authorization.
- Với ảnh, PDF, font, media và download, còn có các quy tắc MIME, CORS/CORP/CSP và bảo mật riêng; `nosniff` không thay thế chúng.
- Với **cross-origin** data, trình duyệt có thể sử dụng các cơ chế hạn chế đọc khác, ví dụ CORB ở những triển khai phù hợp. Không lấy CORB làm bảo đảm cho một API thiếu authorization.

### 3.4. Header duy nhất có ý nghĩa là nosniff

Cú pháp:

```http
X-Content-Type-Options: nosniff
```

Không dùng `sniff`, `deny`, `sameorigin` hay `1` làm giá trị thay thế. `DENY` và `SAMEORIGIN` thuộc chính sách khác, ví dụ `X-Frame-Options`.

**Đừng nhầm với `X-XSS-Protection`.** Header đó là cơ chế cũ, đã lỗi thời và thậm chí có thể tạo hành vi không mong muốn; `nosniff` vẫn có mục đích riêng nhưng không thay thế CSP/XSS prevention tại nguồn.

## 4. Lớp bảo vệ liên quan: không cái nào thay thế cái nào

| Cơ chế | Nó bảo vệ điều gì? | Có thay nosniff không? |
| --- | --- | --- |
| `Content-Type` | Khai báo kiểu nội dung chính xác | Cần kết hợp với nosniff |
| `X-Content-Type-Options: nosniff` | Ngăn MIME sniffing không phù hợp; chặn script/style sai MIME | Là biện pháp trọng tâm |
| `Content-Security-Policy` | Kiểm soát nguồn script/style, inline code, các destination khác | Không thay việc gửi MIME đúng |
| `Content-Disposition: attachment` | Định hướng browser download thay vì render inline | Hữu ích cho file không tin cậy, không thay toàn bộ kiểm chứng |
| `Strict-Transport-Security` | Khuyến khích browser dùng HTTPS cho host khi đủ điều kiện | Không liên quan trực tiếp MIME |
| `X-Frame-Options` / `frame-ancestors` | Hạn chế nhúng trang trong frame | Không phân loại script/style |
| `CORS` | Browser cho JS từ origin khác đọc response có điều kiện | Không phải MIME validation |
| `CSRF protection` | Chống một số request thay đổi trạng thái mạo danh qua browser | Không xử lý MIME confusion |
| `Authentication`/`Authorization` | Xác minh ai được truy cập tài nguyên | Không thay nosniff |
| File scanning/sanitization | Phát hiện và xử lý nội dung upload độc hại | Vẫn cần, đặc biệt với HTML/SVG/PDF |
| Separate upload domain | Cách ly active content khỏi origin có quyền | Quan trọng khi người dùng tải file không tin cậy |

Một request có thể đồng thời yêu cầu **HTTPS, authorization, Content-Type đúng, nosniff và CSP**, tùy tài nguyên. Chỉ có `nosniff` không biến một endpoint trả `text/html` tùy ý thành an toàn.

## 5. Spring Security WebFlux mặc định làm gì?

### 5.1. Header mặc định

Khi bật Spring Security reactive qua `SecurityWebFilterChain` và không vô hiệu hóa mặc định, Spring Security thêm một số security response headers, trong đó có:

```http
X-Content-Type-Options: nosniff
```

Các header mặc định khác có thể bao gồm cache-control, `X-Frame-Options`, `X-XSS-Protection: 0` và `Strict-Transport-Security` **chỉ trong điều kiện HTTPS thích hợp**. Bộ header và giá trị cụ thể phải kiểm tra theo phiên bản Spring Security đang sử dụng.

Trong WebFlux, DSL là `ServerHttpSecurity`, **không phải Servlet `HttpSecurity`**:

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(ex -> ex
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Dù code không gọi `headers(...)`, **default Content-Type Options vẫn bật**. Cấu hình `permitAll()` chỉ cho phép request đi đến handler; nó không nói phải bỏ security headers trên response công khai.

### 5.2. Khi cần diễn đạt bật header tường minh

Nếu muốn codebase thấy cấu hình rõ ràng, Spring Security hỗ trợ:

```java
// Mảnh minh họa thêm vào ServerHttpSecurity trước build().
.headers(headers -> headers
    .contentTypeOptions(Customizer.withDefaults()))
```

Phương thức thuộc `ServerHttpSecurity.HeaderSpec` reactive. Trong Spring Security WebFlux, bộ xử lý security headers được tích hợp vào security filter chain. **Không cần tự viết WebFilter chỉ để đặt `X-Content-Type-Options` khi đang dùng default**, và không tự thêm một bản sao header nếu gateway đã thống nhất cấu hình.

### 5.3. Cách vô hiệu hóa (để hiểu, không khuyến nghị)

```java
// Mảnh minh họa — không áp dụng cho ví dụ chạy ở bài này.
.headers(headers -> headers
    .contentTypeOptions(contentTypeOptions ->
        contentTypeOptions.disable()))
```

Vô hiệu hóa làm browser mất một lớp bảo vệ khi xử lý script/style và những MIME contexts khác. Nếu static JS/CSS đang không tải được sau khi bật `nosniff`, **sửa MIME ở nguồn phát** (WebFlux controller, resource handler, object storage, nginx/CDN) thay vì tắt header.

**Không cần disable nosniff để trả JSON, CSV, ảnh hay PDF**. Mỗi loại nên có `Content-Type` thích hợp và quy tắc download/render riêng.

### 5.4. Header có xuất hiện với mọi URL không?

Header do **security chain** áp dụng. Trong ứng dụng có nhiều `SecurityWebFilterChain`, một request có thể được xử lý bởi chain khác với cấu hình header khác; nếu không có chain nào khớp, đừng tự suy header được gắn.

Ngoài ra:

- Response được proxy/CDN sinh ra **trước khi tới ứng dụng** có thể không có header do Spring Security tạo.
- Exception phát sinh trong một WebFilter chạy trước security chain có thể được xử lý bởi global error handler mà không đi qua writer tương ứng.
- Static resources có thể được xử lý bởi resource handler hoặc một domain/CDN khác.
- Khi response đã committed, filter phía sau không thể sửa response tùy ý.

Vì vậy **kiểm thử thực tế** cả 200, 401/403, 404, 500, file download, static assets và response qua reverse proxy quan trọng hơn chỉ đọc bean cấu hình.

## 6. Ví dụ runnable: Java 17+, Spring Boot WebFlux và browser

Ứng dụng demo cố ý phục vụ hai JS và hai CSS:

- `/assets/good.js`: body JavaScript, `Content-Type: text/javascript`.
- `/assets/bad.js`: body JavaScript **nhưng** `Content-Type: text/plain`.
- `/assets/good.css`: body CSS, `Content-Type: text/css`.
- `/assets/bad.css`: body CSS **nhưng** `Content-Type: text/plain`.

Tất cả đều có `X-Content-Type-Options: nosniff` khi qua security chain.

Trang `/demo.html` chứa `<script>` và `<link>` trỏ tới bốn tài nguyên, giúp kiểm tra trên Chrome/Firefox. Ngoài ra có endpoint `/api/public` JSON, `/api/private` cần Basic auth và `/download/untrusted` gửi dữ liệu dưới dạng attachment.

> Hai endpoint `bad.js`/`bad.css` được cố ý cấu hình sai **chỉ cho bài lab**. Khi triển khai ứng dụng thật, phải sửa MIME và không phát nguồn script/style nhầm kiểu; mục tiêu là quan sát cách browser từ chối tải.

### 6.1. Cây thư mục

```text
webflux-nosniff-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/NosniffApplication.java
      resources/static/demo.html
    test/
      java/example/NosniffApplicationTests.java
```

### 6.2. settings.gradle

```groovy
rootProject.name = 'webflux-nosniff-lab'
```

### 6.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot BOM quản lý các phiên bản Spring Security, Spring WebFlux và Reactor tương thích. Mẫu không dùng `spring-boot-starter-web` (MVC/Servlet). Trong sản phẩm thật, hãy chọn bản Boot còn được hỗ trợ theo chính sách bảo trì/bảo mật; bản 3.3.13 ở đây được cố định để tái lập môi trường bài học.

### 6.4. NosniffApplication.java

Tạo `src/main/java/example/NosniffApplication.java`:

```java
package example;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class NosniffApplication {

    private static final MediaType JAVASCRIPT =
            MediaType.parseMediaType("text/javascript");

    private static final MediaType CSS =
            MediaType.parseMediaType("text/css");

    public static void main(String[] args) {
        SpringApplication.run(NosniffApplication.class, args);
    }

    @GetMapping("/api/public")
    public Map<String, String> publicJson() {
        return Map.of("message", "PUBLIC_OK");
    }

    @GetMapping("/api/private")
    public Map<String, String> privateJson() {
        return Map.of("message", "PRIVATE_OK");
    }

    @GetMapping("/assets/good.js")
    public ResponseEntity<String> goodScript() {
        return ResponseEntity.ok()
                .contentType(JAVASCRIPT)
                .body("document.getElementById('good-script')"
                        + ".textContent = 'GOOD SCRIPT EXECUTED';");
    }

    @GetMapping("/assets/bad.js")
    public ResponseEntity<String> badScript() {
        // Chỉ để demo trình duyệt chặn script MIME sai.
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("document.getElementById('bad-script')"
                        + ".textContent = 'BAD SCRIPT EXECUTED';");
    }

    @GetMapping("/assets/good.css")
    public ResponseEntity<String> goodCss() {
        return ResponseEntity.ok()
                .contentType(CSS)
                .body("#good-style { color: green; "
                        + "font-weight: bold; }");
    }

    @GetMapping("/assets/bad.css")
    public ResponseEntity<String> badCss() {
        // Chỉ để demo trình duyệt chặn CSS MIME sai.
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("#bad-style { color: crimson; "
                        + "font-weight: bold; }");
    }

    @GetMapping("/download/untrusted")
    public ResponseEntity<byte[]> downloadUntrusted() {
        // Dữ liệu giả lập, không lấy từ upload thật.
        byte[] bytes = "<script>alert('not executed')</script>"
                .getBytes(StandardCharsets.UTF_8);

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"untrusted.txt\"")
                .body(bytes);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                "/demo.html", "/assets/**",
                                "/api/public", "/download/untrusted")
                        .permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // Không thêm headers(...): giữ default nosniff.
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(alice);
    }
}
```

**Những chi tiết cần hiểu trong Java code:**

1. `@EnableWebFluxSecurity` và `SecurityWebFilterChain` bật Spring Security reactive; default header writer sẽ thêm `X-Content-Type-Options: nosniff`.
2. `ResponseEntity.contentType(...)` gửi một MIME cụ thể cho bốn tài nguyên, không trông chờ framework suy ra theo đuôi `.js/.css` từ URL controller.
3. `goodScript` dùng `text/javascript`; `goodCss` dùng `text/css`. Khi browser tải với destination script/style, MIME phù hợp.
4. `badScript`/`badCss` trả JavaScript/CSS có cú pháp hợp lệ nhưng tự khai báo `text/plain`. Với `nosniff`, browser từ chối thực thi/áp dụng trong đúng ngữ cảnh.
5. `/api/public` trả object Map, Spring WebFlux/Jackson mặc định serialize thành JSON và Content-Type thích hợp, không cần đặt `text/plain`.
6. `/api/private` được `anyExchange().authenticated()` bảo vệ, dù vẫn cần header security ở response có auth và cả một số error responses.
7. `/download/untrusted` có `Content-Type: application/octet-stream` và `Content-Disposition: attachment` để browser tải về thay vì hiển thị như HTML. **Không phải** trình kiểm tra virus/file; production còn phải giới hạn/tách nguồn upload.
8. `{noop}learn` chỉ là password demo cục bộ; không dùng trong production. HTTP Basic cần HTTPS thật và password hashing mạnh, rate limiting, chống credential stuffing.
9. `formLogin(...disable())` giúp request không có credentials nhận Basic challenge 401 thay vì redirect trang login.
10. Mẫu không khai báo `@CrossOrigin`; trang demo và backend **cùng origin `localhost:8080`**. Vì vậy lỗi MIME quan sát được không bị trộn với lỗi CORS.

### 6.5. Trang HTML demo

Tạo `src/main/resources/static/demo.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WebFlux X-Content-Type-Options demo</title>
  <link rel="stylesheet" href="/assets/good.css">
  <link rel="stylesheet" href="/assets/bad.css">
</head>
<body>
  <h1>Demo nosniff và MIME type</h1>

  <h2>JavaScript</h2>
  <p id="good-script">GOOD SCRIPT NOT YET LOADED</p>
  <p id="bad-script">BAD SCRIPT DID NOT RUN</p>

  <h2>Stylesheet</h2>
  <p id="good-style">GOOD CSS SHOULD BE GREEN</p>
  <p id="bad-style">BAD CSS SHOULD STAY DEFAULT</p>

  <p>Quan sát DevTools Network và Console để kiểm tra.</p>

  <script defer src="/assets/good.js"></script>
  <script defer src="/assets/bad.js"></script>
</body>
</html>
```

HTML này sử dụng cùng origin với backend. Hai script có `defer` sẽ chạy sau khi document parse xong. Nếu browser tuân theo `nosniff`, good script đổi text của `good-script`, bad script bị chặn, nên text `BAD SCRIPT DID NOT RUN` không đổi.

Với CSS, `good-style` chuyển màu xanh, còn `bad-style` không nhận quy tắc `color: crimson` từ CSS MIME sai. Một số yếu tố ngoài MIME (CSP, extension, DevTools cache, proxy) cũng có thể ảnh hưởng, nên hãy đối chiếu response headers chứ không kết luận chỉ bằng màu sắc.

### 6.6. Chạy ứng dụng

Yêu cầu JDK 17+ và Gradle tương thích Spring Boot 3.3.13. Ở thư mục dự án:

```bash
gradle bootRun
```

Nếu có Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Nếu chưa có wrapper, lệnh `gradle bootRun` sử dụng Gradle đã cài. Ví dụ không đòi Redis, database hoặc service ngoài.

Mở browser:

```text
http://localhost:8080/demo.html
```

Sau khi tải, quan sát:

| Tài nguyên | Content-Type từ backend | nosniff | Kết quả trong script/style context |
| --- | --- | --- | --- |
| `/assets/good.js` | `text/javascript` | Có | Script chạy; text “GOOD SCRIPT EXECUTED” |
| `/assets/bad.js` | `text/plain` | Có | Browser chặn; text “BAD SCRIPT DID NOT RUN” |
| `/assets/good.css` | `text/css` | Có | Style áp dụng; chữ màu xanh |
| `/assets/bad.css` | `text/plain` | Có | Browser chặn; không áp dụng style sai MIME |
| `/api/public` | `application/json` | Có | API JSON trả bình thường |
| `/download/untrusted` | `application/octet-stream` | Có | Browser được định hướng tải file |
| `/api/private` (không auth) | Tùy response lỗi | Thường có trong chain | 401 Basic challenge, không phải lỗi MIME |

Đây là **kết quả dự kiến** theo behavior browser hiện đại; chưa phải bản ghi chạy thực tế trên máy người học. Không viết bài test dựa vào text chính xác của DevTools error message vì thông điệp của Chrome/Firefox có thể thay đổi.

### 6.7. DevTools cần nhìn ở đâu?

Vào DevTools → **Network**, tải lại `/demo.html` với cache phù hợp:

1. Chọn request `good.js`. Xem Response Headers: `Content-Type: text/javascript`, `X-Content-Type-Options: nosniff`.
2. Chọn request `bad.js`. `Content-Type: text/plain` và `nosniff`. Tab Console có thể hiện thông báo từ chối chạy script vì MIME type không phải JavaScript.
3. Chọn `good.css` và `bad.css`. Kiểm tra cả hai MIME, rồi xem `Computed styles` của phần tử good/bad.
4. Nếu cả hai JS không chạy, xem **Console CSP/mixed content/CORS** ngoài MIME. Đừng vội tắt nosniff.
5. Nếu bad JS lại chạy, xác định browser/devtools cache, response header thực tế và có proxy nào loại bỏ `nosniff` hay biến `Content-Type` thành JavaScript không.
6. Nếu HTML không tải được, xác minh `/demo.html` đã được permitAll và static resource mapping hoạt động; lỗi route/401 khác lỗi MIME.

## 7. Kiểm tra trực tiếp response headers bằng curl

`curl` hiển thị HTTP headers và body nhưng **không thực thi luật browser MIME sniffing**. Dùng curl để xác nhận server cấu hình đúng, sau đó dùng browser để kiểm tra script/style có chạy thật không.

### 7.1. JS đúng và sai MIME

```bash
curl -i http://localhost:8080/assets/good.js
curl -i http://localhost:8080/assets/bad.js
```

Đầu ra mong đợi (rút gọn):

```http
HTTP/1.1 200 OK
Content-Type: text/javascript
X-Content-Type-Options: nosniff

document.getElementById('good-script').textContent = 'GOOD SCRIPT EXECUTED';
```

và:

```http
HTTP/1.1 200 OK
Content-Type: text/plain
X-Content-Type-Options: nosniff

document.getElementById('bad-script').textContent = 'BAD SCRIPT EXECUTED';
```

Đây là cách diễn tả header/body **đã lược bỏ các headers khác**; response thực có thể kèm `charset` và có thứ tự headers khác. Thấy body chứa JavaScript không có nghĩa browser sẽ chạy: browser còn kiểm tra MIME trong `<script>` context.

### 7.2. CSS đúng và sai MIME

```bash
curl -i http://localhost:8080/assets/good.css
curl -i http://localhost:8080/assets/bad.css
```

Phần quan trọng:

```http
Content-Type: text/css
X-Content-Type-Options: nosniff
```

so với:

```http
Content-Type: text/plain
X-Content-Type-Options: nosniff
```

Kết quả kiểu stylesheet phụ thuộc actual response. Cả hai URL đều có thể HTTP 200, nhưng chỉ MIME đúng phù hợp để browser áp dụng style.

### 7.3. JSON, private endpoint và download

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/private
curl -i -u alice:learn http://localhost:8080/api/private
curl -I http://localhost:8080/download/untrusted
```

Ở lệnh cuối `curl -I` gửi **HEAD**; nếu route chỉ khai báo `@GetMapping`, Spring WebFlux thường hỗ trợ HEAD tương ứng, nhưng behavior/headers có thể khác tùy handler. Để kiểm tra đầy đủ GET attachment, dùng:

```bash
curl -i http://localhost:8080/download/untrusted
```

Kỳ vọng response GET chứa:

```http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="untrusted.txt"
X-Content-Type-Options: nosniff
```

`nosniff` **không đổi body thành an toàn**, mà chỉ làm browser không đoán sai MIME; `Content-Disposition: attachment` định hướng download. Nếu user tải và tự mở file bằng một ứng dụng khác, ứng dụng đó có trust boundary và nguy cơ riêng.

## 8. Test tự động bằng WebTestClient

Tạo `src/test/java/example/NosniffApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class NosniffApplicationTests {

    private static final String NOSNIFF = "X-Content-Type-Options";

    @Autowired
    WebTestClient client;

    @Test
    void publicJsonHasCorrectTypeAndNosniff() {
        client.get().uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        value -> assertTrue(
                                value.startsWith("application/json")))
                .expectBody()
                .jsonPath("$.message").isEqualTo("PUBLIC_OK");
    }

    @Test
    void correctJavaScriptMimeKeepsNosniff() {
        client.get().uri("/assets/good.js")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(
                                type.startsWith("text/javascript")))
                .expectBody(String.class)
                .isEqualTo(
                    "document.getElementById('good-script')"
                    + ".textContent = 'GOOD SCRIPT EXECUTED';");
    }

    @Test
    void mislabeledJavaScriptStillHasNosniff() {
        client.get().uri("/assets/bad.js")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(
                                type.startsWith("text/plain")))
                .expectBody(String.class)
                .isEqualTo(
                    "document.getElementById('bad-script')"
                    + ".textContent = 'BAD SCRIPT EXECUTED';");
    }

    @Test
    void correctCssIsTextCss() {
        client.get().uri("/assets/good.css")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(type.startsWith("text/css")));
    }

    @Test
    void mislabeledCssIsPlainTextAndNosniff() {
        client.get().uri("/assets/bad.css")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(type.startsWith("text/plain")));
    }

    @Test
    void demoHtmlIsServedThroughSecurityChain() {
        client.get().uri("/demo.html")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(type.startsWith("text/html")));
    }

    @Test
    void privateApiNeedsBasicCredentials() {
        client.get().uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().exists(
                        HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void authorizedPrivateJsonStillHasNosniff() {
        client.get().uri("/api/private")
                .headers(h -> h.setBasicAuth("alice", "learn"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectBody()
                .jsonPath("$.message").isEqualTo("PRIVATE_OK");
    }

    @Test
    void untrustedDataDownloadUsesAttachment() {
        client.get().uri("/download/untrusted")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(NOSNIFF, "nosniff")
                .expectHeader().value(HttpHeaders.CONTENT_TYPE,
                        type -> assertTrue(
                                type.startsWith("application/octet-stream")))
                .expectHeader().value(
                        HttpHeaders.CONTENT_DISPOSITION,
                        value -> assertTrue(
                                value.startsWith("attachment;")));
    }
}
```

Chạy:

```bash
gradle test
```

**Những điều test xác minh được:**

- Spring Security WebFlux phát `X-Content-Type-Options: nosniff` qua security chain với public/private/static/download resources.
- MIME type của JS/CSS **đúng** và **sai** được đặt chính xác theo ý định demo, không bị Spring tự sửa bằng sniffing.
- API JSON có đúng kiểu và authentication vẫn được kiểm tra độc lập.
- Download có cả `Content-Disposition: attachment`, không chỉ có nosniff.

**Giới hạn:** `WebTestClient` **không phải trình duyệt**. Nó không thực thi `<script>`, không render CSS, không áp dụng thuật toán MIME sniffing của browser. Vì thế test header PASS **không tự chứng minh** một script bị chặn trong Chrome/Firefox. Phải kết hợp WebTestClient với kiểm tra browser hoặc browser automation thật cho kịch bản script/style.

**Đừng test một con số thời gian hay message của DevTools.** Nội dung cảnh báo Console phụ thuộc browser/version; thứ cần kiểm chứng là resource destination, server MIME, header nosniff và script/style đã thực thi hay chưa.

## 9. Ma trận hành vi: cùng body nhưng header khác

Giả sử body chứa JavaScript hợp lệ.

| Content-Type của response | X-Content-Type-Options | Bối cảnh browser | Kết quả quan trọng |
| --- | --- | --- | --- |
| `text/javascript` | `nosniff` | `<script src>` | Có thể chạy nếu CSP/network/auth phù hợp |
| `application/javascript` | `nosniff` | `<script src>` | Cũng là một JavaScript MIME type còn được chấp nhận; chuẩn hiện nay khuyến nghị `text/javascript` |
| `text/plain` | `nosniff` | `<script src>` | Bị chặn do MIME sai |
| `application/json` | `nosniff` | `<script src>` | Bị chặn do không phải JavaScript MIME |
| Không có header Content-Type | `nosniff` | `<script src>` | Không được dựa vào browser đoán để chạy script |
| `text/javascript` | không có `nosniff` | `<script src>` | Có thể chạy; thiếu lớp bảo vệ cho tài nguyên khác |
| `text/plain` | không có `nosniff` | Classic script | Có thể có khác biệt theo browser; không được dựa vào sniffing để làm script chạy |
| `text/plain` | `nosniff` | Direct navigation | Browser không nên đoán bytes thành HTML |
| `text/html` chứa nội dung do người dùng viết | `nosniff` | Direct navigation | Vẫn là HTML active content; nosniff **không vô hiệu hóa HTML đúng MIME** |
| `application/octet-stream` + attachment | `nosniff` | Direct navigation | Định hướng tải về; còn phụ thuộc browser và các policy khác |

Đừng hiểu bảng như một engine kiểm thử tuyệt đối cho mọi browser/mọi loại tài nguyên. **Request destination, CSP, crossorigin mode, browser version và media type parser** đều tác động. Cặp cần nhớ nhất là **script/style destination với MIME không phù hợp + nosniff → browser từ chối**.

## 10. File upload: nơi nosniff có giá trị nhưng chưa đủ

Hệ thống cho upload ảnh, tài liệu, PDF, log, CSV hoặc HTML fragment là nơi thường phát sinh MIME confusion.

### 10.1. Dòng dữ liệu nguy hiểm

```text
Client upload:
  filename: contract.png
  Content-Type: image/png      (client tự khai)
  bytes: <html><script>...</script></html>

Server:
  lưu nguyên bytes
  phục vụ tại https://app.example.test/files/contract.png
  tin extension/Content-Type do client gửi

Browser:
  nếu resource bị xử lý như HTML/JS trong origin app,
  có thể tạo XSS hoặc dữ liệu active ngoài ý định
```

**Client Content-Type và đuôi file là dữ liệu không tin cậy.** Nếu server trả trực tiếp những giá trị đó như header response, kẻ tấn công có thể buộc server gửi `text/html` hoặc `text/javascript` cho một file chưa được xét duyệt. Khi header đã khai active MIME, `nosniff` không biến nó thành vô hại.

### 10.2. Chính sách tối thiểu khi xử lý upload

1. **Allowlist định dạng** theo yêu cầu nghiệp vụ; từ chối loại không hỗ trợ.
2. **Kiểm tra nội dung thực** bằng parser/decoder uy tín; không chỉ dựa vào tên file hoặc client MIME.
3. **Giới hạn kích thước**, số file, file nesting/decompression bomb, số lượng request và quota.
4. **Đổi tên lưu trữ** bằng ID do server tạo, tránh path traversal; không dùng tên người dùng để xây đường dẫn filesystem trực tiếp.
5. **Lưu trên domain riêng không có session cookie ứng dụng chính** khi người dùng được phép tải hoặc xem nội dung chưa tin cậy; cân nhắc domain có chính sách CSP hạn chế.
6. **Set Content-Type chuẩn** cho dữ liệu đã xác minh, không phản ánh `Content-Type` từ multipart nếu chưa kiểm chứng.
7. Với tài liệu không cần inline preview, đặt **`Content-Disposition: attachment`**; dùng `application/octet-stream` hoặc loại đã xác minh phù hợp.
8. **Set `X-Content-Type-Options: nosniff`** trên response để browser không tự đoán sai.
9. Với HTML/SVG thật sự cần hiển thị, cân nhắc sanitization, CSP sandbox, domain riêng và URL signing/authorization.
10. **Quét malware** theo threat model với PDF/Office/archive và kiểm soát quyền/TTL đối với file private.
11. Bảo đảm access control theo user/resource; nosniff không quyết định ai được tải file.
12. Không tin một lần kiểm tra là đủ nếu file có thể bị thay đổi trong object storage sau khi đã duyệt.

### 10.3. Khi nào dùng attachment?

Ví dụ server trả file văn bản không tin cậy:

```http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="review.txt"
X-Content-Type-Options: nosniff
```

Browser được yêu cầu tải xuống, không render nó như một trang HTML của origin ứng dụng. Đối với business case cần preview, hãy tạo **preview đã sanitize** và phục vụ từ trust boundary phù hợp. Một policy an toàn không bao giờ chỉ dựa vào việc “đuôi file có vẻ là .txt”.

### 10.4. Hạn chế của nosniff với HTML hợp lệ

Nếu server phục vụ:

```http
Content-Type: text/html
X-Content-Type-Options: nosniff
```

và body là HTML chứa `<script>` do attacker nhập, đây vẫn là HTML, và browser có thể thực thi script theo các chính sách khác. Vì vậy thông điệp **“đã bật nosniff nên HTML upload an toàn”** là sai. Bạn còn cần sanitization, CSP, sandbox hoặc tách origin; có thể không cho phép HTML upload nếu nghiệp vụ không yêu cầu.

### 10.5. SVG, PDF và định dạng active khác

`image/svg+xml` là định dạng vector XML có khả năng active content tùy cách sử dụng; không đánh đồng nó với PNG/JPEG bất động. PDF và Office có khả năng nhúng các cấu trúc phức tạp/active content khác nhau. `nosniff` không thực hiện parsing an toàn cho chúng. Thiết kế upload/download dựa trên file type thật và viewer được sandbox đúng cách.

## 11. Khi browser báo “Refused to execute script”

Thông báo có thể tương tự:

```text
Refused to execute script from ... because its MIME type
('text/plain') is not executable, and strict MIME type
checking is enabled.
```

**Các bước chẩn đoán:**

1. Mở DevTools **Network**, chọn request chính xác đang bị từ chối.
2. Xác nhận response là **200/304** hay **404/302/401/500**. Nhiều ứng dụng SPA trả `index.html` có `Content-Type: text/html` cho một URL `.js` không tồn tại; browser chặn vì HTML không phải JavaScript.
3. Xem **Response Headers → Content-Type**. Script cần JavaScript MIME type, stylesheet cần `text/css`.
4. Xem **X-Content-Type-Options** có `nosniff` không. Nếu có, đây là bằng chứng browser được yêu cầu không sniff. Đừng sửa bằng cách xóa header.
5. Xem **Response body**: nếu body là login HTML, JSON error hoặc nginx 404 page, vấn đề có thể là route/security/rewrite, không phải nội dung JS.
6. Xem **Request URL** qua reverse proxy và deployment base path. Ứng dụng có thể tham chiếu `/assets/app.js` nhưng file thật ở `/app/assets/app.js`.
7. Kiểm tra **Content-Type mapping của object storage/CDN**. File `.js` phải được upload với metadata đúng hoặc do gateway tự cấu hình đúng.
8. Nếu dùng JS module, kiểm tra strict MIME và CORS/CSP theo cơ chế module, không đánh đồng classic script.
9. Nếu là CSS, xem response có HTML error page không. CSS URL bị redirect về login có thể hiện như MIME `text/html`.
10. Tải lại sau khi sửa CDN/cache, dùng versioned asset URL nếu cần để tránh nhận lại header sai từ cache.
11. Kiểm tra CSP error ở Console **riêng với MIME error**. Nếu CSP chặn script từ source khác, sửa CSP/nguồn tải tương ứng, không tắt nosniff.
12. Dùng `curl -I`/`curl -i` để xem response ở từng hop; browser test cuối cùng xác nhận việc chạy script/style.

### 11.1. Khi Content-Type là text/html cho URL JS

Một tình huống rất phổ biến trong SPA:

```text
Browser requests:
  GET /static/app-123.js

Server fallback route:
  returns index.html
  Content-Type: text/html

Result:
  browser blocks JS; Console MIME type ('text/html') error
```

Sửa **static asset mapping hoặc rewrite rule**, không thay `Content-Type: text/html` của index.html thành `text/javascript` để “qua mặt” browser. Cũng không tắt security header. Đảm bảo missing asset trả 404 thay vì body HTML dưới URL JS nếu phục vụ JS.

### 11.2. Lỗi proxy gửi application/octet-stream cho JS

Một số server dùng kiểu `application/octet-stream` làm fallback. Với script/style, đây không phải kiểu mà browser kỳ vọng khi `nosniff` bật. Cần sửa cấu hình MIME type của proxy/static server, ví dụ mapping `.js → text/javascript`, `.css → text/css`. Không viết một WebFilter global đổi **mọi** octet-stream thành JavaScript; điều đó có thể biến binary/upload thành active content nguy hiểm.

### 11.3. Lỗi MIME do response 401/403/404

Một `<script src>` có thể nhận 401 JSON hoặc 302 redirect đến HTML login page. Browser không chạy body lỗi như JavaScript. Đây là hành vi tốt. Điều cần sửa là **route asset, authentication policy hoặc cách tải asset đúng**, không phải nosniff.

### 11.4. Cache 304 và header

Với 304 Not Modified, browser kết hợp metadata/cache từ response trước. Debug có thể thấy không phải mọi header xuất hiện ở mỗi 304 theo cách giống 200, nên cần kiểm tra response 200 gốc, cache metadata và CDN. Nếu asset từng được cache với MIME sai, hãy làm mới metadata/URL đúng cách; không suy ra browser bỏ qua nosniff từ riêng một trace 304.

## 12. Spring WebFlux: nơi nên đặt Content-Type

### 12.1. Controller trả JSON

```java
@GetMapping(value = "/api/report",
            produces = MediaType.APPLICATION_JSON_VALUE)
public Mono<ReportResponse> report() {
    return service.loadReport();
}
```

Đây là **mảnh code**, cần định nghĩa `ReportResponse` và `service`; có thể trả DTO/Map với Jackson nếu endpoint có cấu hình codec phù hợp. `produces` cho phép WebFlux content negotiation áp đúng kiểu JSON.

Đừng trả JSON body với `Content-Type: text/javascript` chỉ để client nhúng bằng `<script>`. JSONP/script cross-origin là mô hình cũ với rủi ro riêng; dùng CORS và authentication thích hợp cho API JSON.

### 12.2. Controller trả text

```java
@GetMapping(value = "/api/plain",
            produces = MediaType.TEXT_PLAIN_VALUE)
public Mono<String> plain() {
    return Mono.just("<h1>Đây chỉ là text</h1>");
}
```

Với header `nosniff` và response `text/plain`, browser không tự coi đoạn `<h1>` là HTML khi navigation theo behavior chuẩn. Khi cần hiển thị HTML thực, chỉ gửi `text/html` cho nội dung **được tin cậy hoặc đã sanitize**.

### 12.3. Static assets trong classpath

Spring Boot WebFlux có thể phục vụ static resources từ `classpath:/static/`. Hệ thống thường suy ra MIME type qua resource name/MediaTypeFactory. Nhưng không nên giả định mọi loại file mới hoặc CDN proxy đều có mapping đúng.

Ví dụ:

```text
src/main/resources/static/
  demo.html
  css/app.css
  js/app.js
  images/logo.png
```

Mỗi asset cần response Content-Type phù hợp. Với đuôi file lạ hoặc binary download, hãy cấu hình resource handler/metadata đúng thay vì tắt nosniff. Khi ứng dụng đặt static content trên CDN khác, **điểm phát response thực tế** phải đặt header phù hợp.

### 12.4. WebFilter tự viết response

Một `WebFilter` có thể ghi body trực tiếp:

```java
// Mảnh minh họa — không phải WebFilter độc lập.
ServerHttpResponse response = exchange.getResponse();
response.getHeaders().setContentType(MediaType.TEXT_PLAIN);
response.getHeaders().set(
        "X-Content-Type-Options", "nosniff");
response.setStatusCode(HttpStatus.BAD_REQUEST);
return response.writeWith(
        Mono.just(response.bufferFactory().wrap(
                "Bad request".getBytes(StandardCharsets.UTF_8))));
```

Mảnh này phải có imports/variables của WebFlux tương ứng; nó minh họa một filter *là chủ sở hữu response*. Khi đã có security header writer mặc định, **không cần tự chèn nosniff ở mọi handler**, trừ trường hợp custom filter nằm ngoài chain và phải trả response riêng. Không ghi body xong rồi tiếp tục `chain.filter(exchange)`; có thể gây double write hoặc committed response.

### 12.5. Response khi lỗi đã committed

Nếu server đã bắt đầu stream một response 200 rồi xảy ra lỗi, không thể luôn thay status/header sau commit. `nosniff` phải được thiết lập **trước khi response commit**, nhờ cơ chế writer/filter phù hợp. Vì vậy header security nên được xử lý ở đầu response lifecycle thay vì chờ đến sau khi body đã gửi.

## 13. Security chain, response lỗi và HTTPS

### 13.1. PermitAll không có nghĩa bỏ headers

`.pathMatchers("/assets/**").permitAll()` cho phép client lấy static assets mà không login. Spring Security vẫn có thể thêm security headers cho những request đó. Nếu bạn thấy endpoint public thiếu `nosniff` còn private có, hãy kiểm tra **securityMatcher/chain selection**, không chỉ controller annotation.

### 13.2. Nhiều SecurityWebFilterChain

Giả sử:

```text
Order 1: /api/**      -> Resource Server/Bearer
Order 2: /assets/**   -> public/static
Order 3: /**          -> form login
```

Mỗi chain có thể cấu hình headers riêng. `WebFilterChainProxy` chọn chain đầu tiên khớp; một chain dành cho static assets có thể vô tình `headers(...disable())` hoặc bị bỏ qua. Khi đó JS/CSS nhận header khác API.

**Kiểm thử từng nhóm URL**, bao gồm:
- JS/CSS từ security chain static;
- API JSON public/private;
- HTTP error response 401/403;
- file download;
- đường dẫn không có handler;
- response do gateway/CDN chặn hoặc sinh ra.

Nếu request đi qua một **domain riêng** không chạy Spring Security, phải đặt headers ngay tại origin/proxy tương ứng. Không tự kết luận Spring Security header sẽ được đưa qua mọi hop.

### 13.3. Header nosniff và HSTS làm hai việc khác nhau

**HTTPS** mã hóa traffic. `Strict-Transport-Security` (HSTS) hướng browser quay lại HTTPS với host sau khi nhận policy qua kết nối hợp lệ. `X-Content-Type-Options: nosniff` quyết định cách browser xử lý media type. Hai cơ chế bổ trợ nhưng không thay thế nhau.

Với Spring Security, HSTS header được gửi theo điều kiện HTTPS và cấu hình bảo mật. Việc curl HTTP local `localhost:8080` không có HSTS **không chứng minh nosniff thiếu**; kiểm tra từng header riêng. Sản phẩm thật cần TLS, HSTS theo policy, redirect HTTP→HTTPS hợp lệ, certificate trust và reverse proxy forwarded headers đúng.

### 13.4. CORS không phải sửa lỗi MIME

Một script có thể bị chặn vì CORS (đặc biệt module script tải cross-origin) hoặc vì MIME, CSP, network/authorization. Bật `@CrossOrigin("*")` không biến `text/plain` thành JavaScript. Hãy xem Console/Network **lỗi thuộc lớp nào** trước khi sửa.

### 13.5. CSRF không giải quyết MIME confusion

CSRF protection ngăn một số request giả mạo làm thay đổi trạng thái khi browser tự đính kèm credentials. Nó không thay thế nosniff. Ngược lại, nosniff không bảo vệ endpoint POST khỏi CSRF. Cả hai nên tồn tại khi mô hình cần.

## 14. Vận hành và kiểm soát thay đổi

### 14.1. Checklist cho API và assets

1. **Security defaults:** Spring Security WebFlux đang bật và không tắt `contentTypeOptions`?
2. **Đúng MIME:** `.js → text/javascript`, `.css → text/css`, JSON → `application/json`, HTML tin cậy → `text/html`.
3. **Static resources:** không redirect JS/CSS chưa xác thực về HTML login; không trả `index.html` khi file JS không tồn tại.
4. **Upload:** validate bytes, MIME, extension, size, loại cho phép và nơi lưu; không phản ánh client MIME trực tiếp.
5. **Preview:** không render HTML/SVG không tin cậy trên cùng origin quyền cao nếu chưa có sandbox/sanitization.
6. **Download:** có `Content-Disposition: attachment` khi mục đích là tải file; MIME phù hợp.
7. **Authorization:** file private và API vẫn kiểm tra user/resource; nosniff không phải ACL.
8. **Proxy/CDN:** giữ hoặc bổ sung `X-Content-Type-Options: nosniff` nhất quán, không ghi đè Content-Type sai.
9. **Cache:** sau khi sửa MIME, clear/invalidate cache hoặc đổi tên versioned assets; kiểm tra 200/304.
10. **Response lỗi:** xem 401/403/404/500 có headers cần thiết theo đường thực tế; tránh leak HTML login body vào JS URLs.
11. **Browser tests:** Chrome/Firefox thực sự chặn bad.js/bad.css và cho good.js/good.css hoạt động.
12. **Automated tests:** WebTestClient xác minh headers/status, không giả định nó mô phỏng browser.
13. **Content-Security-Policy:** xem `script-src`/`style-src` và những quy tắc khác khi có active content.
14. **HTTPS/HSTS:** kiểm tra riêng truyền tải và MIME policy; header nosniff không thay TLS.
15. **Monitoring:** ghi metric lỗi tải static/script, Content-Type drift, 404 assets, browser errors và scanner findings.

### 14.2. Test regression khi nâng cấp

Mỗi lần nâng Spring Boot/Spring Security, đổi CDN/static server hoặc chuyển sang WebFlux functional endpoints, nên chạy lại:

- Test default `X-Content-Type-Options`;
- Test JS/CSS MIME trên response 200 và error;
- Test static resource mapping/`index.html` fallback;
- Test security chain khác nhau;
- Test files uploaded được download/sandbox đúng policy;
- Test response qua proxy/canonical hostname;
- Test behavior browser đối với module scripts, CSP và MIME.

**Không dựa vào scanner PASS một header đơn lẻ**. Một scanner thấy `nosniff` có thể vẫn không phát hiện server đang gửi `text/html` cho file upload nguy hiểm hoặc đang cho phép người dùng truy cập file không thuộc quyền.

### 14.3. Triển khai cấu hình an toàn cho CDN/reverse proxy

Đối với asset từ CDN, cần đảm bảo:

```http
Content-Type: text/javascript
X-Content-Type-Options: nosniff
Cache-Control: public, max-age=...
```

Dấu `...` chỉ minh họa chính sách cache; không copy nguyên nó thành header thật. Với file static có hash trong tên, có thể dùng cache dài theo versioned URL. Nhưng **Content-Type và nosniff là metadata bắt buộc chính xác**, không liên quan TTL cache.

Nếu CDN trả HTML 404 cho URL JS, phải sửa routing/status và content type; không ép mọi response dưới đường `/js/**` thành JavaScript nếu response body thực là HTML lỗi.

### 14.4. Khi tổ chức có Security Header Baseline

Đặt hợp đồng kiểm soát:

```text
Mỗi response từ app/proxy thuộc phạm vi bảo vệ phải:
  - có X-Content-Type-Options: nosniff
  - khai Content-Type đúng với body (hoặc không body khi thích hợp)
  - không lộ stack trace/secret trong error page
  - có Content-Disposition hợp lý với download
  - tuân CSP, HSTS, CORS, cache policy riêng theo tài nguyên
```

Đây là một baseline chung; có thể có ngoại lệ như response `204 No Content`, `304 Not Modified` hoặc thành phần ngoài chain, nên đánh giá theo semantics HTTP cụ thể. Tránh ép mọi response có body `Content-Type: application/json` chỉ để đạt yêu cầu scanner.

## 15. Sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| Tắt `nosniff` để JS sai MIME chạy | Mất lớp bảo vệ | Sửa `Content-Type` của JS và static server |
| Coi `nosniff` là trình kiểm tra virus | Không phân tích nội dung độc hại | Validate, scan, sanitize, giới hạn uploads |
| Trả untrusted HTML với `text/html` rồi tin nosniff đủ | Browser vẫn được thông báo đó là HTML | Tách domain/sandbox/sanitize/attachment |
| Dùng `application/json` cho một `<script src>` | Không phải JavaScript MIME | Trả JS đúng loại hoặc dùng `fetch` cho JSON |
| Dùng `text/plain` cho CSS | Style destination yêu cầu `text/css` | Sửa CSS MIME |
| Tin file extension hoặc upload Content-Type | Client có thể giả | Kiểm tra file thật trên server |
| Dùng `application/octet-stream` cho mọi response | JS/CSS/browser không thể xử lý đúng | Chọn media type theo tài nguyên |
| Thay tất cả 404 bằng `index.html` | JS asset miss thành HTML MIME error | Giới hạn SPA fallback ở navigation phù hợp |
| Cho rằng status 200 = script đã chạy | Browser còn kiểm MIME/CSP/CORS | Kiểm browser Console/Network |
| Cho rằng WebTestClient mô phỏng nosniff | HTTP client không có browser enforcement | Thử Chrome/Firefox/browser automation |
| Coi CORS lỗi là nosniff lỗi | Hai cơ chế khác nhau | Xem exact error layer trong DevTools |
| Tự thêm header ở mỗi controller | Dễ thiếu static/error responses | Dùng security defaults hoặc proxy policy thống nhất |
| Header hiện trên API nhưng không trên CDN | Khác origin/response owner | Cấu hình CDN/proxy đúng |
| Bỏ `nosniff` cho 401/403/500 | Có thể lộ cách browser xử lý error body | Kiểm security chain và global error handling |
| Dùng browser sniff để “sửa” tải asset | Hành vi không ổn định, tăng rủi ro | Đặt header MIME đúng và versioned assets |

## 16. Câu hỏi tự kiểm tra

**1. X-Content-Type-Options: nosniff yêu cầu browser làm gì?**  
Tôn trọng Content-Type đã khai thay vì đoán kiểu theo những trường hợp bị hạn chế; đặc biệt **chặn script/style** có MIME không phù hợp.

**2. Nếu body là JavaScript hợp lệ nhưng server trả Content-Type: text/plain với nosniff, `<script src>` có chạy không?**  
Không, browser hiện đại sẽ từ chối thực thi trong script destination do MIME sai.

**3. Nếu body là CSS nhưng server trả text/plain với nosniff, trình duyệt có áp dụng style không?**  
Không; stylesheet destination yêu cầu `text/css`.

**4. Bật nosniff có giúp browser tự xác định MIME đúng khi server không khai không?**  
Không. Header **không sửa Content-Type**, chỉ hạn chế sniffing. Server phải khai loại phù hợp.

**5. Tại sao có thể nhận 200 cho /assets/app.js mà trang vẫn trống?**  
Response có thể là HTML fallback/login, JSON error hoặc text/plain thay cho JavaScript, nên browser chặn script dù HTTP status thành công.

**6. Nosniff có ngăn XSS nếu server trả HTML người dùng tải lên với Content-Type: text/html không?**  
Không. HTML đó vẫn là active content theo MIME đã khai; cần cách ly, sanitize, CSP/sandbox/attachment phù hợp.

**7. Có phải nosniff thay authentication/authorization cho file riêng tư?**  
Không. Nó không biết user, role hay owner; backend vẫn phải kiểm quyền truy cập.

**8. Content-Disposition: attachment có cùng chức năng với nosniff không?**  
Không. Attachment định hướng tải file; nosniff hạn chế browser tự suy diễn MIME. Có thể cần cả hai.

**9. Trong Spring Security WebFlux, phải tự cấu hình headers(...) mới có nosniff không?**  
Không. Spring Security bật mặc định Content-Type Options; không cần thêm cấu hình nếu chưa bị vô hiệu hóa.

**10. Đổi ServerHttpSecurity sang HttpSecurity có phải cách tùy biến nosniff cho WebFlux?**  
Không. `ServerHttpSecurity` là DSL của reactive WebFlux; `HttpSecurity` thuộc Servlet.

**11. Vì sao phải dùng text/javascript thay vì application/octet-stream cho JS?**  
Vì script destination cần JavaScript MIME type. `application/octet-stream` không phải kiểu script để browser tự tải chạy khi nosniff bật.

**12. Tại sao WebTestClient header test PASS chưa chứng minh browser chặn bad.js?**  
Vì WebTestClient kiểm HTTP response, không thực thi script/style hoặc luật sniffing của trình duyệt. Cần browser test riêng.

**13. CSP và nosniff khác nhau thế nào?**  
CSP hạn chế nguồn và cách sử dụng active resources; nosniff hạn chế diễn giải MIME. Hai lớp bổ trợ.

**14. HSTS có làm JS text/plain thành JavaScript không?**  
Không. HSTS liên quan HTTPS; MIME vẫn phải đúng.

**15. Có thể tự đặt Content-Type: text/html cho mọi endpoint để bảo đảm browser hiển thị không?**  
Không. Với JSON/JS/CSS/download, điều đó sai và có thể tăng XSS risk. Chọn đúng kiểu mỗi tài nguyên.

**16. Nếu một file upload tên avatar.png nhưng bytes là HTML, phải làm gì?**  
Không tin tên file/MIME client khai; xác minh nội dung, từ chối định dạng không hợp lệ, tách upload domain và dùng headers/policy đúng.

**17. Khi JavaScript được trả từ CDN khác domain, Spring Security ở backend có tự đặt header cho response CDN không?**  
Không. Header phải được cấu hình tại thành phần **thực sự trả response**, ví dụ CDN/object storage/reverse proxy.

**18. Vì sao Content-Type text/plain + nosniff có thể hữu ích cho dữ liệu văn bản không tin cậy?**  
Vì browser không tự suy dữ liệu có các thẻ HTML thành trang HTML active trong những ngữ cảnh mà header kiểm soát.

**19. Có nên tắt nosniff khi browser báo MIME error?**  
Không. Phải kiểm đúng request URL, actual response body và Content-Type của asset.

**20. Một API JSON fetch response có nosniff có tự bảo đảm JSON hợp lệ và dữ liệu không bị lộ không?**  
Không. JSON parse, CORS, authentication, authorization và chống lộ dữ liệu vẫn là trách nhiệm riêng.

**Ghi nhớ:** Trong Spring Security reactive, hãy **giữ `X-Content-Type-Options: nosniff` bật**, phục vụ mọi tài nguyên với **`Content-Type` chuẩn xác**, dùng `Content-Disposition`/domain riêng/sanitization cho upload không tin cậy, và kiểm thử **browser + WebTestClient**. Nếu script/style bị chặn, sửa **MIME ở nguồn phát**, không nới chính sách bảo vệ để che lỗi cấu hình.

## Tài liệu tham khảo

- [MDN — X-Content-Type-Options](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Content-Type-Options): cú pháp `nosniff`, script/style blocking và các MIME contexts khác.
- [MDN — MIME Type Verification](https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/MIME_types): bảo vệ script/style, MIME sniffing và khuyến nghị Content-Type đúng.
- [MDN — Content-Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Type): media type, charset và sự khác nhau giữa Content-Type và Content-Encoding.
- [WHATWG — MIME Sniffing Standard](https://mimesniff.spec.whatwg.org/): xác định MIME từ response và tương tác với quy tắc browser.
- [WHATWG — Fetch Standard](https://fetch.spec.whatwg.org/): request destination, `nosniff`, CORS và behavior của fetch.
- [Spring Security — Default Security HTTP Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html): các security headers mặc định và `X-Content-Type-Options: nosniff`.
- [Spring Security — HTTP Response Headers in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html): `ServerHttpSecurity.headers(...)`, Content-Type Options mặc định và cách disable.
- [Spring Security — ServerHttpSecurity.HeaderSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.html): `contentTypeOptions(...)` cho reactive.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`/`ServerHttpSecurity`.
- [Spring Framework — WebFlux Static Resources](https://docs.spring.io/spring-framework/reference/web/webflux/config.html#webflux-config-static-resources): resource handling, caching và MIME mappings.
- [MDN — Content-Disposition](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Disposition): download vs inline semantics.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): allowlist, validation, storage isolation và xử lý upload an toàn.
