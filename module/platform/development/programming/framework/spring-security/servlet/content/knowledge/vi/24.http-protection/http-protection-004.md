# X-Content-Type-Options: nosniff và bảo vệ trước suy đoán kiểu nội dung

## 1. Vì sao trình duyệt lại “đoán” kiểu nội dung?

Khi máy chủ trả một tài nguyên HTTP, header `Content-Type` mô tả **media type (MIME type)** của response. Ví dụ: `text/html` cho HTML, `text/css` cho CSS, `text/javascript` cho JavaScript, `application/json` cho JSON và `image/png` cho ảnh PNG.

Trong một số bối cảnh và với một số trình duyệt, nếu header bị thiếu hoặc khai báo không phù hợp, trình duyệt có thể xem byte đầu của nội dung và **MIME sniffing**: suy đoán định dạng để quyết định cách xử lý, thay vì chỉ dùng giá trị Content-Type. Việc đoán kiểu từng giúp các website cấu hình sai vẫn hiển thị được, nhưng làm ranh giới giữa **dữ liệu** và **mã có thể thực thi** trở nên kém chắc chắn.

Ví dụ: server định gửi tệp người dùng tải lên như dữ liệu văn bản, nhưng nội dung có cú pháp JavaScript hoặc HTML. Nếu browser diễn giải tài nguyên theo ngữ cảnh chủ động (script, HTML), kẻ tấn công có thể tận dụng lỗi cấu hình để chạy mã hoặc làm lộ dữ liệu trong những điều kiện nhất định.

Header phản hồi sau yêu cầu trình duyệt tôn trọng loại nội dung đã khai báo đối với các đích nhận tài nguyên có quy tắc MIME nghiêm ngặt:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=utf-8
X-Content-Type-Options: nosniff

console.log("This is text, not an executable script");
~~~

`X-Content-Type-Options: nosniff` giúp ngăn việc lấy nội dung `text/plain` ở trên để **thực thi như script** khi trang nhúng nó bằng `<script src="...">`. Đây là **response header**, không phải header mà client phải gửi. Giá trị được chuẩn hóa và hỗ trợ là **`nosniff`**; không thay thế bằng `deny`, `sameorigin` hoặc giá trị tự đặt.

**Phân biệt hai vai trò:** `Content-Type` nói “tôi đang gửi loại gì”; `X-Content-Type-Options: nosniff` bảo browser không chuyển sang một số kiểu nguy hiểm bằng suy đoán. Nếu server khai báo `Content-Type` sai, `nosniff` **không tự sửa MIME type**. Hệ thống cần **cả hai**: khai báo Content-Type đúng **và** gửi nosniff.

## 2. nosniff tác động thực tế đến những trường hợp nào?

### 2.1. Script và stylesheet: hai trường hợp cốt lõi

Khi response được tải đến đích `script`, browser áp dụng kiểm tra MIME type. Với nosniff, một response không có JavaScript MIME type hợp lệ sẽ không được thực thi như JavaScript. Với đích `style`, một response không phải `text/css` sẽ không được dùng làm stylesheet.

| Trang yêu cầu | Server trả Content-Type | Có nosniff | Kết quả mong đợi của browser hiện đại |
| --- | --- | --- | --- |
| `<script src="/assets/app.js">` | `text/javascript` | Có | Có thể thực thi nếu nội dung hợp lệ và các chính sách khác cho phép |
| `<script src="/files/readme.txt">` | `text/plain` | Có | **Chặn thực thi** vì MIME type không phải JavaScript |
| `<script src="/api/data">` | `application/json` | Có | **Chặn thực thi** như script |
| `<link rel="stylesheet" href="/assets/app.css">` | `text/css` | Có | Có thể áp dụng stylesheet |
| `<link rel="stylesheet" href="/files/data.txt">` | `text/plain` | Có | **Chặn stylesheet** vì MIME type không phải CSS |
| `<script src="/uploads/evil.js">` | `text/javascript` | Có | **Không bị nosniff chặn chỉ vì mã độc**: MIME khai báo đã hợp lệ |

“Có thể” ở bảng nghĩa là browser vẫn áp dụng **CSP, CORS (khi liên quan), SRI, sandbox và những chính sách khác**. nosniff chỉ là một điều kiện kiểm tra MIME, không cấp quyền thực thi.

Lưu ý: **module script** vốn chịu quy tắc MIME chặt hơn classic script theo chuẩn browser hiện đại; nosniff không phải lý do duy nhất khiến module có MIME sai bị chặn. JavaScript MIME type được các trình duyệt hỗ trợ bao gồm `text/javascript`; ứng dụng nên trả đúng type của tài nguyên thực tế.

Ví dụ HTML cố nhúng dữ liệu JSON làm script:

~~~html
<script src="/api/profile"></script>
<link rel="stylesheet" href="/uploads/notes.txt">
~~~

Nếu `/api/profile` trả `Content-Type: application/json` và `/uploads/notes.txt` trả `Content-Type: text/plain`, kèm `X-Content-Type-Options: nosniff`, trình duyệt sẽ không xử lý hai response đó như JavaScript/CSS. DevTools thường hiển thị lỗi liên quan “MIME type” hoặc “strict MIME type checking”; thông điệp và trạng thái mạng có thể khác giữa trình duyệt.

### 2.2. Những bối cảnh không được bảo vệ tuyệt đối

**nosniff không phải bộ kiểm tra hoặc thay thế loại nội dung toàn cục.** Không thể suy ra từ việc một response có header này rằng mọi ảnh, video, tài liệu, navigation hay request `fetch` đều sẽ bị chặn khi sai Content-Type.

- **Điều hướng trực tiếp tới URL**: nếu máy chủ trả HTML với `Content-Type: text/html`, browser có thể hiển thị/chạy HTML; nosniff không “vô hiệu hóa HTML”. Với file tải lên do người dùng kiểm soát, việc cho hiển thị HTML trên origin tin cậy vẫn rất nguy hiểm.
- **JSON qua fetch/XHR**: `nosniff` không thay thế xác thực, phân quyền, CORS hoặc kiểm tra cách client parse nội dung. Browser script cùng origin thường vẫn có thể đọc response `application/json` nếu quyền truy cập hợp lệ.
- **Ảnh và các loại tài nguyên khác**: browser có quy tắc riêng theo destination; đừng dựa vào nosniff như một công cụ xác nhận chữ ký PNG/JPEG hoặc vô hiệu hóa mọi active content.
- **Cross-origin response**: nosniff có thể tham gia các cơ chế bảo vệ dữ liệu cross-origin ở browser (ví dụ CORB ở một số trình duyệt; các triển khai hiện đại còn có Opaque Response Blocking). Phạm vi và hành vi khác nhau giữa trình duyệt và loại response. Đây **không phải cam kết ngăn rò rỉ thông tin** và không thay thế CORS, CORP, COEP, xác thực hay kiểm soát quyền.

Điểm cần nhớ: **nhận được HTTP 200 trên network không đồng nghĩa browser sẽ cho thực thi script/style**. Quyết định chặn theo MIME diễn ra ở browser; `curl` không thực thi JavaScript và không thể dùng một mình để kết luận browser có chặn hay không.

## 3. Các tình huống tấn công và phạm vi phòng thủ

### Tình huống A: Tệp người dùng tải lên bị gọi như JavaScript

Giả sử hệ thống cho người dùng upload `avatar.txt` chứa mã JavaScript, sau đó có thể truy cập qua URL `/uploads/avatar.txt`. Một trang hoặc chức năng khác nhúng URL đó vào script:

~~~html
<script src="/uploads/avatar.txt"></script>
~~~

Nếu server trả `Content-Type: text/plain` **và** `nosniff`, browser hiện đại từ chối chạy như script. Nếu server bỏ header, một số hành vi MIME sniffing kiểu cũ hoặc cấu hình đặc thù có thể tạo điều kiện diễn giải sai. Tuy nhiên **nếu server nhầm lẫn trả `text/javascript`**, nosniff không giúp vì MIME đã được khai báo là JavaScript.

Biện pháp đúng: xác định loại nội dung đáng tin, không cho người dùng quyết định MIME chỉ bằng tên file/header upload, dùng allowlist và kiểm tra nội dung, ngăn server trả file không tin cậy với MIME có khả năng thực thi; cân nhắc phục vụ tệp người dùng từ **origin riêng**. Với file tải về không cần render inline, dùng `Content-Disposition: attachment`.

### Tình huống B: Nội dung HTML/SVG không tin cậy được phục vụ inline

Một file `evil.html` hoặc SVG có nội dung chủ động được trả với `Content-Type: text/html` hoặc `image/svg+xml` có thể tạo rủi ro XSS hoặc script tùy nơi sử dụng, origin, CSP và browser. **nosniff không tự vô hiệu hóa nội dung chủ động được gán MIME hợp lệ.**

Bảo vệ bằng cách không cho render inline loại file nguy hiểm trên origin ứng dụng, chuyển sang download attachment khi phù hợp, dùng origin riêng không giữ cookie xác thực, áp dụng CSP/sandbox và quy tắc cho phép file rõ ràng. Không tin vào phần mở rộng file hay `Content-Type` mà client upload tự cung cấp.

### Tình huống C: Response dữ liệu bị nhúng chéo origin

Một website khác có thể cố nhúng tài nguyên qua các phần tử HTML. Browser có các bảo vệ đặc thù để giảm rò rỉ response thuộc loại HTML/XML/JSON qua tài nguyên không phù hợp. `nosniff` giúp một số cơ chế này đưa ra quyết định dựa trên loại đã khai báo, nhưng **không** bảo vệ nội dung công khai trước việc đọc trực tiếp, không xử lý lỗi CORS cấp phép quá rộng và không thay thế kiểm tra người dùng được phép xem dữ liệu.

### Phân biệt với các biện pháp khác

| Cơ chế | Mục tiêu chính | nosniff có thay thế được không? |
| --- | --- | --- |
| `Content-Type` chính xác | Khai báo media type của dữ liệu | Không; nosniff dựa vào thông tin này |
| `Content-Security-Policy` (CSP) | Giới hạn nguồn và cách thực thi nội dung chủ động | Không |
| `Content-Disposition: attachment` | Khuyến khích tải file thay vì render trong trang | Không |
| Kiểm tra loại file/upload, origin riêng | Giảm nguy cơ file không tin cậy chạy cùng origin ứng dụng | Không |
| CORS | Kiểm soát việc JavaScript cross-origin đọc response theo chính sách browser | Không |
| CSRF defense | Ngăn request thay đổi trạng thái trái ý người dùng qua thông tin xác thực tự gửi | Không |
| `X-Frame-Options` / CSP `frame-ancestors` | Giới hạn embedding trang trong frame | Không |

## 4. Spring Security Servlet gửi X-Content-Type-Options ra sao?

### 4.1. Mặc định của Spring Security

Trong cấu hình **Spring Security Servlet** thông thường, khi một request đi qua `SecurityFilterChain` và HTTP security headers chưa bị tắt, Spring Security mặc định thêm header:

~~~http
X-Content-Type-Options: nosniff
~~~

Thành phần chịu trách nhiệm ghi security headers nằm trong hệ thống `HeaderWriterFilter`/`HeaderWriter` của Spring Security; writer dành cho Content-Type Options cung cấp `nosniff`. Vì vậy nhiều ứng dụng Spring Boot có `spring-boot-starter-security` đã có header này ngay cả khi bạn chưa viết dòng cấu hình riêng.

**Nhưng phải xác minh response thực tế**: header có thể thiếu khi request không đi qua security chain, ứng dụng đã tắt headers, có filter/proxy can thiệp hoặc lỗi được trả trực tiếp từ tầng khác. Header của static resource cũng cần được xem xét, không chỉ controller JSON.

### 4.2. Cấu hình Spring Security 6+ bằng Java 17

Ví dụ dưới đây là **class cấu hình trong dự án Spring Boot 3.x/Spring Security 6+**, sử dụng `spring-boot-starter-web` và `spring-boot-starter-security`. Đoạn này không phải chương trình Java độc lập để chạy bằng `javac`; container Spring tạo `HttpSecurity` và `SecurityFilterChain`.

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**", "/api/status", "/download/**")
                .permitAll()
                .anyRequest().authenticated())
            .headers(headers -> headers
                .contentTypeOptions(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

`contentTypeOptions(Customizer.withDefaults())` ở đây **làm rõ chủ đích**; với header mặc định chưa bị tắt, gọi tường minh không bắt buộc. Security headers **không cấp quyền vào endpoint** và cũng không thay thế authentication/authorization của `authorizeHttpRequests`.

Tránh kiểu cấu hình sau khi không có lý do rõ ràng:

~~~java
// Không nên dùng chỉ để “đơn giản hóa”:
// http.headers(headers -> headers.disable());
~~~

Lệnh trên tắt nhóm HTTP security headers do Spring Security quản lý, không chỉ nosniff. Nếu có nhiều `SecurityFilterChain`, kiểm tra chain nào khớp từng URL và header có xuất hiện ở response của mỗi chain hay không. Cấu hình ở một chain không tự đảm bảo response đi qua chain khác cũng có cùng header.

**Đặc biệt với static assets:** ưu tiên `permitAll()` cho URL public vẫn cần security headers. Nếu bỏ hẳn asset khỏi Spring Security bằng `WebSecurityCustomizer.ignoring()`, request có thể không đi qua `HeaderWriterFilter` và mất header bảo vệ; khi đó web server/CDN phải chịu trách nhiệm bổ sung. Tương tự, response do nginx/gateway/CDN tự tạo có thể không đi qua Spring Security.

### 4.3. Đúng MIME cho từng endpoint

Header nosniff chỉ phát huy ý nghĩa khi server khai báo media type hợp lý. Đối với Spring MVC:

- Tài nguyên CSS trả `Content-Type: text/css`.
- Tài nguyên JS trả JavaScript MIME type hợp lệ, thường `text/javascript` hoặc một loại tương thích mà trình duyệt chấp nhận. Không ép mọi file sang `text/plain` để “an toàn” nếu trình duyệt thực sự cần tải script/style.
- JSON trả `application/json`; văn bản thường là `text/plain; charset=utf-8`; HTML chỉ dùng `text/html` với nội dung tin cậy.
- File tải về nên chọn MIME đúng với dữ liệu và, nếu không cần hiển thị nội tuyến, thêm `Content-Disposition: attachment`.
- Khi dùng proxy, storage hoặc CDN để phục vụ tài nguyên, kiểm tra Content-Type thực tế sau các tầng đó.

Controller sau minh họa một JSON API và endpoint tải CSV, giữ loại nội dung rõ ràng. Mỗi public class đặt trong file cùng tên trong dự án Spring Boot; đoạn dưới là **file `ResourceController.java`**:

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ResourceController {
    public record StatusResponse(String status) {}

    @GetMapping(path = "/api/status",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public StatusResponse status() {
        return new StatusResponse("ok");
    }

    @GetMapping("/download/report")
    public ResponseEntity<byte[]> download() {
        byte[] csv = "name,score\nLan,90\n"
            .getBytes(StandardCharsets.UTF_8);

        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType("text/csv"))
            .header(HttpHeaders.CONTENT_DISPOSITION,
                    "attachment; filename=\"report.csv\"")
            .body(csv);
    }
}
~~~

Nếu có Jackson qua `spring-boot-starter-web`, request GET `/api/status` trả JSON dạng `{"status":"ok"}` với media type `application/json`. Với endpoint tải CSV, server trả `Content-Type: text/csv`, `Content-Disposition: attachment; filename="report.csv"` và nội dung CSV. Header `X-Content-Type-Options: nosniff` được Spring Security thêm ở lớp filter nếu request đi qua chain đã cấu hình.

Với static resource, đặt `app.js` vào `src/main/resources/static/assets/app.js` và kiểm tra phản hồi thực tế của `GET /assets/app.js`. Spring Boot có thể xác định MIME từ mapping của servlet container hay cấu hình resource, nên không nên đoán một giá trị header cố định cho mọi môi trường.

### 4.4. Một lưu ý về HTTP và cache

Cache/CDN có thể lưu cả body và headers; cấu hình sai làm một tài nguyên JS hợp lệ bị trả với `text/plain` hoặc thiếu `nosniff`. Khi khắc phục, làm sạch cache phù hợp rồi kiểm tra cả response qua CDN, không chỉ response trực tiếp từ app. Đừng tạo hai Content-Type mâu thuẫn giữa proxy và ứng dụng.

Mỗi response có đúng một cách diễn giải MIME rõ ràng và một giá trị nosniff nhất quán. Server có thể trả HTTP status 200 nhưng browser vẫn chặn resource do MIME sai; đây là tín hiệu cần **sửa cấu hình Content-Type**, không phải xóa nosniff để “hết lỗi”.

## 5. Kiểm thử thực tế

### 5.1. Xem headers HTTP

Chạy ứng dụng Spring Boot rồi kiểm tra endpoint:

~~~bash
curl -i http://localhost:8080/api/status
curl -I http://localhost:8080/download/report
curl -I http://localhost:8080/assets/app.js
~~~

Các lệnh là ví dụ; endpoint static cuối chỉ tồn tại nếu bạn đã tạo `app.js`. Với `/api/status` và cấu hình minh họa, các phần quan trọng của response **dự kiến** là:

~~~http
HTTP/1.1 200
Content-Type: application/json
X-Content-Type-Options: nosniff

{"status":"ok"}
~~~

Một số server thêm charset, Content-Length, các header khác hoặc thay thứ tự; đây là **mẫu rút gọn**, không phải output nguyên xi của một phiên chạy. `curl -I` gửi HEAD; Spring MVC xử lý HEAD cho nhiều GET mapping, nhưng một endpoint tùy biến có thể yêu cầu kiểm tra bằng GET. Với file CSV, kiểm tra thêm `Content-Disposition`.

Bước kiểm tra giá trị: nếu response có `nosniff` nhưng JavaScript vẫn bị chặn vì `Content-Type: text/plain`, thì cơ chế đang làm đúng nhiệm vụ; **sửa loại nội dung mà server cung cấp**, không tắt header.

### 5.2. Integration test của Spring Security

Với các dependency test Spring Boot/Spring Security thông thường, có thể đặt file `SecurityHeaderTest.java` trong thư mục test cùng package với ứng dụng:

~~~java
package com.example.demo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityHeaderTest {
    @Autowired
    MockMvc mvc;

    @Test
    void jsonEndpointHasNosniffAndCorrectMime() throws Exception {
        mvc.perform(get("/api/status"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"))
            .andExpect(content()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.status").value("ok"));
    }
}
~~~

Test này xác minh response trong application context có header và JSON type đúng; **không mô phỏng thuật toán chặn MIME của trình duyệt**. Test cũng cần cấu hình SecurityFilterChain và controller ở mục trước cùng các dependency Spring Boot thực tế. Có thể mở rộng kiểm tra static assets, route 401/403/404, file tải về và các chain khác nếu ứng dụng sử dụng.

### 5.3. Kiểm tra ở browser

1. Mở DevTools → **Network**; chọn response của CSS, JS, JSON, file upload và quan sát `Content-Type`/`X-Content-Type-Options`.
2. Tạo trang test nhúng một file `text/plain` như `<script src="...">` trên môi trường thử nghiệm; browser hiện đại nên chặn thực thi khi response có nosniff.
3. Xem **Console** để tìm thông báo về MIME/strict MIME type, đồng thời kiểm tra stylesheet cũng phải được trả `text/css`.
4. Thử đường đi thực tế qua reverse proxy/CDN, các trạng thái lỗi và response static; chúng có thể khác với `MockMvc`.
5. Đừng kết luận “đã an toàn” chỉ từ header: tiếp tục kiểm tra upload, CSP, quyền truy cập, loại file được chấp nhận và việc nội dung không tin cậy có thể chạy cùng origin hay không.

## 6. Cách xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Browser báo “Refused to execute script … MIME type text/html/text/plain” | URL JS trỏ sang trang lỗi, login page hoặc server khai báo sai Content-Type | Kiểm tra URL, 200/302/404, body và Content-Type; phục vụ JS thực sự với JS MIME type |
| Stylesheet không được áp dụng; strict MIME check | CSS bị trả thành `text/html` hoặc `text/plain` | Sửa mapping/resource server để trả `text/css` |
| API trả `application/json` nhưng có người đề nghị xóa nosniff để nhúng qua `<script>` | Dùng sai cơ chế tải JSON | Dùng `fetch`/XHR với authentication, CORS phù hợp; không biến JSON thành JavaScript |
| Một số URL có nosniff, một số không | Nhiều SecurityFilterChain, `web.ignoring()`, CDN/proxy hoặc error handler khác nhau | Xác định tầng trả response và thêm header ở đúng tầng |
| Trình duyệt vẫn chạy HTML không tin cậy | HTML được trả đúng `text/html`, nên nosniff không phải hàng rào XSS | Tách origin, attachment/sandbox, CSP và quy tắc upload |
| `curl` trả HTTP 200 nhưng browser báo blocked MIME | Browser có bước thực thi/kiểm tra riêng | Dùng DevTools, sửa Content-Type; không coi 200 là bằng chứng script được thực thi |
| Header có nhưng JavaScript mã độc vẫn chạy | Server hoặc ứng dụng đã phục vụ nội dung đó dưới JavaScript MIME type hợp lệ | Kiểm soát nguồn script, upload, CSP và quyền; nosniff không phân tích xem mã có độc hại không |

### Checklist khi triển khai production

- [ ] Những response cần bảo vệ, bao gồm **JS, CSS, JSON và tài nguyên không tin cậy**, trả Content-Type đúng và nhất quán.
- [ ] Các response chạy qua Spring Security Servlet có `X-Content-Type-Options: nosniff`; không vô tình tắt toàn bộ headers hoặc bypass chain.
- [ ] Các response do **CDN, reverse proxy, storage, web server và error handler** phát ra cũng được kiểm tra; không chỉ test controller.
- [ ] Không cho phép HTML/SVG/script do người dùng kiểm soát chạy trên origin có quyền nhạy cảm; kiểm soát download, MIME và CSP phù hợp.
- [ ] Không phụ thuộc nosniff để xử lý **CORS, CSRF, XSS, authorization hoặc kiểm soát upload**.
- [ ] Có cả HTTP header test và browser/DevTools test; khi script/style bị chặn, sửa MIME của tài nguyên đúng thay vì tắt nosniff.

**Kết luận:** `X-Content-Type-Options: nosniff` là hàng rào quan trọng giúp browser từ chối dùng một số response sai MIME làm **JavaScript hoặc CSS**, đồng thời hỗ trợ một số biện pháp bảo vệ cross-origin tùy trình duyệt. Trong Spring Security Servlet, header này thường đã được bật mặc định. Hiệu quả phụ thuộc vào **Content-Type chính xác, đường đi thật qua filter/proxy và cách lưu phục vụ nội dung không tin cậy**; nosniff không phải cơ chế phòng thủ toàn diện cho mọi dạng tải tài nguyên.
