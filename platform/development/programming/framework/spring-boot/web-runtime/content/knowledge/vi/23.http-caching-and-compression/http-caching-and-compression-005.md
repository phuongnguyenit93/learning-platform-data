# Vary và tính đúng đắn khi phản hồi thay đổi theo header

## 1. Vì sao một URL có thể có nhiều bản phản hồi?

Giả sử cùng gọi `GET /greeting` nhưng client A gửi `Accept-Language: vi` và nhận `Xin chào!`, còn client B gửi `Accept-Language: en` và nhận `Hello!`. Hoặc cùng gọi `GET /assets/app.js`, một trình duyệt hỗ trợ `gzip` nhận dữ liệu nén, trong khi client khác nhận nội dung không nén.

**Cùng method và URL chưa chắc đồng nghĩa cùng representation.** Server có thể chọn nội dung, ngôn ngữ, kiểu media hoặc kiểu mã hóa theo **request headers**. Nếu browser cache, reverse proxy hoặc CDN chỉ lấy URL làm điều kiện tái sử dụng, chúng có thể trả **bản phản hồi không phù hợp** cho client tiếp theo.

HTTP giải quyết phần quan trọng này bằng response header **`Vary`**.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Language: vi
Cache-Control: public, max-age=60
Vary: Accept-Language

Xin chào!
~~~

`Vary: Accept-Language` cho biết quá trình chọn representation có thể phụ thuộc request header `Accept-Language`. Cache HTTP tuân thủ chuẩn phải xét giá trị header đó khi quyết định có thể dùng lại response đã lưu hay không.

**Sau bài học**, bạn sẽ hiểu:
- `Vary` là gì, dùng cho những request header nào và nó thay đổi cache key ra sao.
- Vì sao `Accept-Encoding`, `Accept-Language`, `Accept` và `Origin` là các trường hợp điển hình.
- Cách xử lý content negotiation, compression, CORS và response cá nhân hóa mà không làm rò rỉ nội dung.
- Cách thêm `Vary` bằng Spring MVC/WebFlux, xác minh header bằng `curl` và kiểm thử cache/CDN.
- Quan hệ giữa `Vary`, `Cache-Control`, `ETag`, `304 Not Modified`, và những lỗi tinh vi thường chỉ xuất hiện sau khi có reverse proxy.

> **Phạm vi thực hành:** Ví dụ Java 17+ dùng Spring Boot 3.5.x, Spring MVC và thư viện Spring Web. Với Spring Boot 4.x, starter Spring MVC được tách thành `spring-boot-starter-webmvc`; cơ chế HTTP `Vary` và API `ResponseEntity.varyBy(...)` vẫn có vai trò tương ứng. Một số header bổ sung bởi server, gateway hoặc CORS filter có thể khác theo phiên bản và cấu hình, vì vậy luôn đo response thật.

## 2. `Vary` được định nghĩa ra sao trong HTTP?

Theo **RFC 9110, mục 12.5.5**, `Vary` là **response header field** mô tả những request header field có thể ảnh hưởng đến việc origin server chọn representation, bên cạnh method và target URI. Giá trị thường là danh sách tên header, không phải giá trị cụ thể của các header đó.

Ví dụ hợp lệ:

~~~http
Vary: Accept-Encoding
Vary: Accept-Language
Vary: Accept, Accept-Encoding
Vary: Origin
Vary: *
~~~

### `Vary` không chứa giá trị của request header

Đúng:

~~~http
Vary: Accept-Language
~~~

Không đúng cách sử dụng chuẩn:

~~~http
Vary: Accept-Language: vi
~~~

Dòng sai ở trên không phải cách liệt kê `field-name` theo cú pháp `Vary`. Response nói **hãy xét field nào**, còn cache ghi nhớ field đó đã có giá trị gì trong **request tạo response**.

### Cache xem xét điều kiện gì?

Theo **RFC 9111, mục 4.1**, cache có một stored response với `Vary` không được dùng nó để đáp ứng request mới **nếu các header được nêu trong `Vary` không khớp** với request đã tạo stored response, trừ khi response được revalidate phù hợp.

Mô hình tư duy đơn giản:

~~~text
Cache identity cơ bản: method + target URI

GET /greeting
    |
    +--- Vary: Accept-Language
           |
           +--- request Accept-Language: vi -> representation tiếng Việt
           |
           +--- request Accept-Language: en -> representation tiếng Anh

GET /assets/app.js
    |
    +--- Vary: Accept-Encoding
           |
           +--- request hỗ trợ gzip -> gzip variant
           |
           +--- request không hỗ trợ gzip -> identity variant
~~~

Đây là mô hình **logic**, không khẳng định mọi CDN luôn lưu thành những object vật lý có khóa đúng dạng chuỗi ghép field. Cache implementation có thể chuẩn hóa header hoặc thực hiện revalidation. Nhưng kết quả **không được dùng nhầm representation** cho request không tương thích.

### “Khớp” không nhất thiết là so sánh byte-for-byte

RFC 9111 cho phép chuẩn hóa theo cú pháp và ngữ nghĩa của field, ví dụ:
- Bỏ hoặc thêm whitespace hợp lệ.
- Kết hợp các dòng header cùng tên khi quy tắc field cho phép.
- Chuẩn hóa các giá trị biết là tương đương về ngữ nghĩa, như khác biệt hoa/thường đối với field định nghĩa không phân biệt hoa/thường.

Nếu header được nêu trong `Vary` **vắng mặt** trong request gốc, nó chỉ được coi là khớp với request mới cũng vắng mặt header đó, sau những bước chuẩn hóa hợp lệ. Không tự coi `Accept-Encoding` vắng mặt và `Accept-Encoding: gzip` là tương đương.

**Không tự viết proxy cache bằng cách so trực tiếp toàn bộ chuỗi headers** trừ khi hiểu RFC và cách xử lý của gateway. Cách dùng đúng nhất là để một HTTP cache tuân thủ chuẩn xử lý `Vary`.

## 3. Lỗi điển hình: cache sai vì thiếu `Vary`

Giả sử origin tạo nội dung theo ngôn ngữ:

| Request | Origin phải trả | Nếu cache chỉ theo URL |
|---|---|---|
| `GET /greeting` + `Accept-Language: vi` | `Xin chào!` | Có thể lưu bản Việt |
| `GET /greeting` + `Accept-Language: en` | `Hello!` | Có thể lấy nhầm bản Việt |
| `GET /greeting` + `Accept-Language: vi` | `Xin chào!` | Bản Việt có thể vẫn đúng do ngẫu nhiên |

Nếu origin gửi response có `Cache-Control: public, max-age=300` nhưng **không gửi** `Vary: Accept-Language`, một shared cache có thể tái sử dụng bản vừa lưu cho các client yêu cầu ngôn ngữ khác. Lỗi thường không lộ khi phát triển trực tiếp không có cache, nhưng xuất hiện sau khi bật CDN.

Cách sửa ở origin:

~~~http
Cache-Control: public, max-age=300
Vary: Accept-Language
Content-Language: vi
~~~

Và trên **mọi variant tương ứng**, kể cả bản mặc định tiếng Anh khi request không gửi `Accept-Language`, phải dùng chính sách `Vary` nhất quán. Chỉ thêm `Vary` vào phản hồi tiếng Việt, còn response mặc định bỏ qua, dễ gây reuse sai cho request sau.

**Điều `Vary` không làm:** nó không dịch ngôn ngữ, không tạo thêm file, không tự bật CDN và không quyết định response được phép cache hay không. Server vẫn phải chọn đúng variant; `Vary` chỉ truyền thông tin giúp cache dùng lại đúng.

## 4. Bảng các header thường làm nội dung thay đổi

| Request header ảnh hưởng | Điều origin có thể thay đổi | `Vary` thường thấy | Cần kiểm tra |
|---|---|---|---|
| `Accept-Encoding` | Body nén `gzip`/`br` hoặc identity | `Vary: Accept-Encoding` | `Content-Encoding` và byte body có tương thích với client không |
| `Accept-Language` | Ngôn ngữ văn bản | `Vary: Accept-Language` | `Content-Language` và chính sách chọn ngôn ngữ |
| `Accept` | Media type như JSON, XML, HTML | `Vary: Accept` | `Content-Type`, 406, message converter |
| `Origin` | Header CORS, đặc biệt `Access-Control-Allow-Origin` | `Vary: Origin` | CORS policy, cache của preflight/actual response |
| `Access-Control-Request-Method` | Kết quả CORS preflight | `Vary: Access-Control-Request-Method` | Chỉ trong preflight nếu kết quả phụ thuộc method |
| `Access-Control-Request-Headers` | Kết quả CORS preflight | `Vary: Access-Control-Request-Headers` | Kết quả phụ thuộc headers được yêu cầu |
| `User-Agent` | HTML/asset phục vụ riêng theo UA | Có thể là `Vary: User-Agent` | Số biến thể cực nhiều, cache-hit giảm |
| Client Hints | Ảnh/chất lượng giao diện theo client hints | `Vary` theo field thật dùng | Privacy, mức hỗ trợ client, cardinality |
| `Cookie` | Nội dung theo phiên/người dùng | Thường **không nên** trông vào `Vary: Cookie` để bảo mật | Dùng `Cache-Control: private` hoặc `no-store` khi cần |

Không phải cứ request có một header là phải thêm header đó vào `Vary`. Chỉ nên liệt kê các field thực sự có thể ảnh hưởng đến việc chọn representation hoặc các header response có liên quan được cache. `User-Agent` và `Cookie` tạo quá nhiều variants, thường làm cache kém hiệu quả.

## 5. Quan hệ với `Accept-Encoding` và nén HTTP

### 5.1. Định dạng không nén và định dạng gzip không tương đương ở mức byte

Client A:

~~~http
GET /assets/app.js HTTP/1.1
Accept-Encoding: gzip
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/javascript
Content-Encoding: gzip
Vary: Accept-Encoding
Cache-Control: public, max-age=3600

<gzip-compressed-bytes>
~~~

Client B:

~~~http
GET /assets/app.js HTTP/1.1
Accept-Encoding: identity
~~~

Server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/javascript
Vary: Accept-Encoding
Cache-Control: public, max-age=3600

<uncompressed-javascript-bytes>
~~~

Hai block biểu diễn cấu trúc; các chuỗi giữa dấu ngoặc nhọn là **chỗ giữ chỗ**, không phải body thực.

`Accept-Encoding` là yêu cầu về những content coding client chấp nhận; `Content-Encoding` mô tả coding đã áp dụng trên response. `Content-Type` vẫn mô tả **kiểu media gốc** của nội dung. Nếu cache đưa bản gzip cho client không hỗ trợ gzip, client có thể nhận byte không đọc được hoặc gặp lỗi giải mã.

### 5.2. Trong Spring Boot, server/container có thể quản lý nén

Spring Boot hỗ trợ response compression cho các embedded server phù hợp, ví dụ Tomcat, Jetty và Reactor Netty. Với Boot 3.5:

~~~yaml
server:
  compression:
    enabled: true
    mime-types:
      - text/plain
      - text/html
      - application/json
      - application/javascript
    min-response-size: 2KB
~~~

Theo tài liệu Boot 3.5, `server.compression.enabled` mặc định `false` và ngưỡng mặc định là **2KB**; các media type được hỗ trợ mặc định gồm text/plain, JSON, CSS, JavaScript... Có thể thay danh sách và ngưỡng. Một response nhỏ có thể **không được nén** dù browser gửi `Accept-Encoding: gzip`; vì vậy không kết luận mọi request có header gzip đều phải nhận `Content-Encoding: gzip`.

Tùy server, HTTP version, proxy và cách viết response, việc phát `Vary: Accept-Encoding` có thể do tầng server/proxy thực hiện. **Phải quan sát header thực tế từ tuyến request đã deploy**, không mặc định rằng chỉ bật compression là mọi tầng cache tự hiểu đúng biến thể.

### 5.3. Lỗi thường xảy ra khi có hai tầng nén

Ví dụ:
- Origin đã nén gzip.
- Reverse proxy tiếp tục xử lý transform hoặc cache key không phân biệt `Accept-Encoding`.
- CDN phục vụ lại body đã nén cho client không hỗ trợ, hoặc gửi `Content-Encoding: gzip` sai với body.

Giải pháp thường là xác định **nơi chịu trách nhiệm nén**, bảo toàn/chuẩn hóa `Vary` hợp lệ, không nén lặp, cấu hình đúng `Content-Encoding` và kiểm tra đường đi thực từ origin qua proxy tới client.

`Cache-Control: no-transform` có thể dùng khi không muốn intermediary biến đổi representation, nhưng nó không tương đương “origin không được phép nén” và không thay `Vary` khi tồn tại nhiều encoding variants.

## 6. `Accept-Language`: ví dụ về content negotiation ngôn ngữ

Request:

~~~http
GET /greeting HTTP/1.1
Accept-Language: vi
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Language: vi
Vary: Accept-Language
Cache-Control: public, max-age=60

Xin chào!
~~~

Ngôn ngữ khác:

~~~http
GET /greeting HTTP/1.1
Accept-Language: en
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Language: en
Vary: Accept-Language
Cache-Control: public, max-age=60

Hello!
~~~

`Content-Language` mô tả ngôn ngữ của nội dung đã chọn. `Vary` chỉ ra trường lựa chọn; `Cache-Control` thông báo cách cache có thể lưu/reuse trong một khoảng thời gian.

### Một điểm nâng cao: q-values và chuẩn hóa ngôn ngữ

Header thực tế của browser có thể phức tạp:

~~~http
Accept-Language: en-US,en;q=0.9,vi;q=0.7
~~~

Đây là danh sách ưu tiên, không phải một chuỗi đơn giản. Một ứng dụng production nên sử dụng **locale negotiation** phù hợp với Spring MVC/Servlet hoặc WebFlux, thay vì cố phân tích chỉ bằng `startsWith("vi")`, vì cần xử lý region, quality factors, default language và các language tags.

Với site có nhiều ngôn ngữ cố định, một URL riêng như `/vi/greeting` và `/en/greeting` có thể giúp CDN cache hiệu quả hơn một URL khác nhau theo toàn bộ chuỗi `Accept-Language` của rất nhiều browser. Dù cách nào, hãy bảo đảm semantics của URL và header thống nhất.

## 7. Thực hành Java 17 với Spring Boot: tự đặt `Vary` đúng cách

Tạo dự án bằng **Spring Initializr**, Java 17+, Gradle, Spring Boot **3.5.x**, dependency **Spring Web**. Không cần Redis, Spring Security hay CDN cho phần này.

Trong một project đã có Boot Gradle plugin/dependency management, dependency dùng cho Boot 3.5 là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Trên Spring Boot 4.x, chọn starter `spring-boot-starter-webmvc` tương ứng. Đây là dependency fragment cho project Boot, không phải toàn bộ file Gradle.

Tạo tệp `src/main/java/demo/vary/VaryDemoApplication.java`:

~~~java
package demo.vary;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class VaryDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(VaryDemoApplication.class, args);
    }

    @GetMapping(value = "/greeting", produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> greeting(
            @RequestHeader(value = "Accept-Language", required = false)
            String acceptLanguage) {

        // Chỉ là quy tắc đơn giản cho hai trường hợp curl: "vi" và "en".
        boolean isVietnamese = acceptLanguage != null
                && acceptLanguage.toLowerCase(Locale.ROOT).startsWith("vi");

        String language = isVietnamese ? "vi" : "en";
        String body = isVietnamese ? "Xin chào!" : "Hello!";

        return ResponseEntity.ok()
                .varyBy("Accept-Language")
                .cacheControl(
                    CacheControl.maxAge(Duration.ofSeconds(60)).cachePublic()
                )
                .header("Content-Language", language)
                .contentType(
                    new MediaType("text", "plain", StandardCharsets.UTF_8)
                )
                .body(body);
    }

    @GetMapping(value = "/payload", produces = MediaType.TEXT_PLAIN_VALUE)
    public String payload() {
        return "A".repeat(4096);
    }
}
~~~

Mã trên là **một class Boot runnable hoàn chỉnh** trong dự án đúng starter. `ResponseEntity.ok().varyBy(...)` là API chính thức của Spring Framework, có thể thêm nhiều request header names. `CacheControl.maxAge(Duration.ofSeconds(60)).cachePublic()` chỉ thích hợp ở đây vì nội dung **hoàn toàn công khai**.

**Giới hạn có chủ đích của demo:** `startsWith("vi")` chỉ thể hiện rõ hai lệnh curl `Accept-Language: vi` và `en`. Nó không phải thuật toán chọn ngôn ngữ đúng cho mọi `Accept-Language` có `q` values. Trong hệ thống thật, dùng cơ chế locale resolver/negotiation chuẩn; `Vary` vẫn phải nêu đúng các header ảnh hưởng nội dung.

Để thử cả HTTP compression, tạo `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080
  compression:
    enabled: true
    mime-types:
      - text/plain
    min-response-size: 2KB
~~~

Khởi động ở thư mục gốc project do Spring Initializr tạo:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 7.1. Kiểm tra hai ngôn ngữ

Với ứng dụng đang chạy:

~~~bash
curl -sS -i -H 'Accept-Language: vi' http://localhost:8080/greeting
~~~

Response body kỳ vọng:

~~~text
Xin chào!
~~~

Các header quan trọng kỳ vọng có (không cam kết thứ tự/kiểu viết hoa hay các header khác do server thêm):

~~~http
HTTP/1.1 200
Vary: Accept-Language
Content-Language: vi
Cache-Control: public, max-age=60
~~~

Lệnh cho client khác:

~~~bash
curl -sS -i -H 'Accept-Language: en' http://localhost:8080/greeting
~~~

Response body kỳ vọng:

~~~text
Hello!
~~~

Và header liên quan:

~~~http
Vary: Accept-Language
Content-Language: en
~~~

Khi bỏ `Accept-Language`, demo chọn bản mặc định tiếng Anh **nhưng vẫn gửi `Vary: Accept-Language`**. Đây là điều cần thiết để cache biết default variant cũng liên quan tới quy tắc lựa chọn.

`curl` thông thường **không tự làm shared HTTP cache**, vì vậy các lệnh trên xác thực origin response và header, chưa kiểm chứng hit/miss thực tế của CDN. Muốn đánh giá cache thật, chạy qua proxy/CDN đã cấu hình và xem cache-status header/log tương ứng với hệ thống đó.

### 7.2. Kiểm tra nén với một body đủ lớn

Endpoint `/payload` trả **4.096 ký tự A**, để dễ vượt ngưỡng nén 2KB trên server phù hợp.

Client không yêu cầu gzip:

~~~bash
curl -sS -D - -o /dev/null \
  -H 'Accept-Encoding: identity' \
  http://localhost:8080/payload
~~~

Client yêu cầu gzip; `--compressed` giúp curl tự giải mã content coding hỗ trợ:

~~~bash
curl -sS --compressed -D - -o /dev/null \
  -H 'Accept-Encoding: gzip' \
  http://localhost:8080/payload
~~~

Quan sát `Content-Encoding`, `Vary`, `Content-Length`/`Transfer-Encoding` và body khi cần; compressed body không nên in raw ra terminal. Với nhiều môi trường Tomcat/Boot 3.5, gzip sẽ xuất hiện ở request thứ hai, nhưng **không khẳng định header chính xác giống nhau ở mọi container, proxy và phiên bản**.

**Phải biết:** body `/greeting` quá ngắn so với ngưỡng 2KB; một request `Accept-Encoding: gzip` tới `/greeting` có thể không được nén. Đừng lấy test response nhỏ để kết luận compression hay `Vary` cho toàn hệ thống đúng/sai.

## 8. Phân biệt `Vary: Accept` với `Vary: Accept-Encoding`

Hai header có vai trò khác nhau:

- `Accept`: client thông báo **kiểu media** mà nó chấp nhận, ví dụ `application/json` hoặc `application/xml`.
- `Accept-Encoding`: client thông báo **mã hóa biểu diễn** như `gzip`, `br` hoặc `identity`.

Ví dụ cùng resource có hai loại representation:

~~~http
GET /profile/public HTTP/1.1
Accept: application/json
~~~

Response có thể là:

~~~http
Content-Type: application/json
Vary: Accept

{"name":"Example"}
~~~

Một client khác:

~~~http
GET /profile/public HTTP/1.1
Accept: application/xml
~~~

Response có thể là:

~~~http
Content-Type: application/xml
Vary: Accept

<profile><name>Example</name></profile>
~~~

Nếu server không hỗ trợ kiểu client yêu cầu và không có lựa chọn phù hợp, kết quả có thể là `406 Not Acceptable`. Trong Spring MVC/WebFlux, media type negotiation có thể được thực hiện qua mapping `produces` và message converter; header thực tế phải được kiểm tra cho route đang phục vụ.

Nếu cùng route còn phục vụ gzip và identity, có thể cần:

~~~http
Vary: Accept, Accept-Encoding
~~~

Trước khi thêm `Vary: Accept` một cách cơ học, xác minh response thực sự có thể thay đổi theo `Accept`. Một endpoint luôn trả JSON và không thương lượng media type có thể không cần thêm Vary theo Accept chỉ để “an toàn”.

## 9. `Vary: Origin` và CORS

Khi browser gọi API cross-origin, request có thể mang:

~~~http
Origin: https://app.example.test
~~~

Nếu origin server cho phép chính origin đó, response có thể phát:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
~~~

Với request từ origin khác trong allowlist, `Access-Control-Allow-Origin` có thể đổi giá trị. **Ngay cả khi response body JSON giống nhau**, metadata CORS thay đổi theo `Origin`, nên shared cache cần không dùng nhầm CORS headers của origin A cho origin B. `Vary: Origin` giúp phân biệt.

Spring MVC/WebFlux có cơ chế xử lý CORS ở tầng HandlerMapping/Filter. Với một số triển khai, framework cũng gửi các field `Vary` liên quan preflight như:

~~~http
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Điều này không có nghĩa bạn phải thêm nguyên bộ ba cho **mọi endpoint**. Quan sát cấu hình CORS, xem request có phải preflight hay actual request, và bảo đảm `Vary` phản ánh chính xác các request headers được dùng để chọn kết quả.

### CORS không phải `Vary`

- **CORS** quy định browser JavaScript từ origin nào được đọc response cross-origin.
- **`Vary`** giúp cache phân biệt response theo headers.
- `Vary: Origin` **không tự cấp quyền CORS**.
- `Access-Control-Allow-Origin` **không bảo đảm shared cache dùng đúng response**, trừ khi cache behavior phù hợp.

Khi bật CORS có credentials, không đặt tùy tiện `Access-Control-Allow-Origin: *`; Spring giới hạn cách dùng wildcard khi `allowedCredentials=true`. Chỉ cho phép các origin tin cậy theo chính sách cụ thể; CORS cũng không phải cơ chế xác thực người dùng.

## 10. `Vary` khác `Cache-Control` như thế nào?

Một response có thể có cả hai:

~~~http
Cache-Control: public, max-age=600
Vary: Accept-Language
~~~

Ý nghĩa:
- `Cache-Control`: response có thể được các cache thích hợp lưu và coi là fresh trong khoảng nào.
- `Vary`: nếu cache muốn tái sử dụng, phải xét thêm **những request header names nào**.

Bảng:

| Header / Directive | Câu hỏi nó trả lời |
|---|---|
| `Vary: Accept-Language` | Bản response này dùng được cho request có ngôn ngữ tương ứng không? |
| `Cache-Control: max-age=60` | Response có thể được xem là fresh bao lâu theo cache rules? |
| `Cache-Control: public` | Có được shared cache dùng nếu thỏa các điều kiện khác không? |
| `Cache-Control: private` | Có cấm shared cache lưu response cho nhiều user không? |
| `Cache-Control: no-store` | Có yêu cầu cache không lưu request/response liên quan không? |
| `Cache-Control: no-cache` | Có cần revalidate trước khi dùng lại stored response không? |
| `ETag: "..."` | Có validator nào để revalidate representation không? |

**Đặc biệt:** `no-cache` không đồng nghĩa “không lưu”; nó cho phép lưu nhưng buộc revalidate trước khi tái sử dụng. `no-store` mới đưa ra yêu cầu không lưu. `private` chặn lưu ở shared cache, nhưng có thể cho phép private browser cache theo các chỉ thị khác.

### Response theo user/cookie/auth

Nếu `GET /api/me` trả thông tin tài khoản theo cookie `JSESSIONID` hoặc token `Authorization`, **không chỉ dựa vào**:

~~~http
Vary: Cookie
~~~

Cách này tạo cache key có cardinality cao, khó kiểm chứng, và không thay thế chính sách bảo vệ dữ liệu. Chọn response policy như:

~~~http
Cache-Control: private, no-store
~~~

cho thông tin nhạy cảm hoặc không được lưu. Với nội dung cá nhân nhưng cho phép cache riêng trên thiết bị, `private` và TTL phù hợp có thể chấp nhận tùy threat model; phải phân tích rủi ro logout, thiết bị chia sẻ và dữ liệu thay đổi.

RFC có quy tắc riêng với request dùng `Authorization` và shared cache. Tuy nhiên **không nên dựa duy nhất vào mặc định proxy** để bảo vệ dữ liệu bí mật; cấu hình rõ các response nhạy cảm và test qua hạ tầng thật.

## 11. `Vary: *` có ý nghĩa gì?

~~~http
Vary: *
~~~

Giá trị wildcard này cho biết quá trình chọn representation phụ thuộc yếu tố mà recipient không thể xác định đầy đủ chỉ từ danh sách field names. Theo RFC 9111, một stored response chứa `Vary: *` **luôn không khớp** để sử dụng lại theo cơ chế matching bình thường.

Nhưng **`Vary: *` không đồng nghĩa `Cache-Control: no-store`**:
- `Vary: *` nói về việc tái sử dụng stored response để thỏa request tiếp theo.
- `no-store` nói về nghĩa vụ không lưu request/response trong cache.

Trong thực hành, khi mục tiêu là **không lưu dữ liệu nhạy cảm**, nên dùng `Cache-Control: no-store` phù hợp thay vì lấy `Vary: *` làm cơ chế bảo mật. `Vary: *` cũng làm giảm khả năng reuse cache; đừng dùng để né việc xác định những header thật sự ảnh hưởng representation.

## 12. ETag, Last-Modified, 304 và các phiên bản nén

`Vary` và conditional requests phải phối hợp để tránh một cache “revalidate đúng URL nhưng sai variant”.

### 12.1. Validator là gì?

- `ETag` là entity tag để so sánh phiên bản representation.
- `If-None-Match` là điều kiện client/cache gửi để kiểm tra stored representation có đổi không.
- `Last-Modified` và `If-Modified-Since` là cơ chế kiểm tra dựa trên thời gian.

Với GET, nếu điều kiện hợp lệ cho biết representation chưa đổi, origin có thể trả **304 Not Modified** và client/cache dùng lại stored body phù hợp. Không nên trả 304 cho một variant không tương thích với các selecting headers trong `Vary`.

### 12.2. ETag cho gzip và identity

Tưởng tượng body JavaScript giống nhau về nội dung ở mức giải nén nhưng khác bytes thực:

~~~text
Identity bytes: [function hello() {...}]
Gzip bytes:     [header gzip + compressed bytes]
~~~

**Strong ETag** biểu thị sự tương đương mạnh ở mức representation data; dùng **cùng strong ETag** cho hai bản có byte representation khác nhau có thể vi phạm ngữ nghĩa validator. Một số server/CDN dùng ETag khác nhau giữa các content codings, hoặc điều chỉnh cách tạo validator để bảo đảm đúng.

Ví dụ minh họa:

~~~http
Content-Encoding: gzip
Vary: Accept-Encoding
ETag: "app-v12-gzip"
~~~

Và identity:

~~~http
Vary: Accept-Encoding
ETag: "app-v12-identity"
~~~

Hai ETag trên chỉ là chuỗi giả định để thể hiện cách phân biệt, **không phải giá trị tự động của Spring Boot**. Weak validator `W/"..."` có thể biểu thị tương đương yếu trong những trường hợp phù hợp; nhưng việc dùng strong/weak validator đúng đòi tuân thủ RFC và cách server/transformer thực sự sinh ETag.

### 12.3. 304 cũng cần giữ thông tin lựa chọn representation

Một response 304 cần phát các header liên quan như `ETag`, `Cache-Control` và `Vary` khi chúng sẽ hiện diện trong 200 tương ứng, theo các điều kiện của HTTP semantics. Nếu một tầng proxy làm rơi `Vary` trên response 304 rồi cập nhật stored metadata sai, cache có thể chọn nhầm variant ở request sau.

Khi điều tra lỗi “lần đầu đúng, lần thứ hai sai”, hãy xem không chỉ **200** mà cả **304**, request `If-None-Match` và thông tin cache revalidation.

## 13. Cache ở browser, reverse proxy và CDN có thể khác nhau

Sơ đồ:

~~~text
Browser
  | Cookie / Accept-Language / Accept-Encoding
  v
Browser cache
  |
  v
CDN edge / shared cache
  |
  v
Reverse proxy / load balancer
  |
  v
Spring Boot origin
~~~

Từng tầng có thể:
- Cache hoặc không cache một response.
- Chuẩn hóa request headers, ví dụ `Accept-Encoding`.
- Thêm/bỏ header, thực hiện content compression.
- Phục vụ stale response theo cấu hình cụ thể.
- Có quy tắc cache key riêng, không tự động tuân theo cách origin mong muốn trong mọi tình huống.

Khi dùng CDN, **không chỉ kiểm tra origin**. Phải cấu hình hạ tầng edge để nó bảo toàn `Vary` liên quan, không gom các biến thể không tương thích, và hiểu cache-key chính thức của sản phẩm CDN. Một số CDN giới hạn các header được phép dùng làm cache key hoặc cache/normalize một tập giá trị `Accept-Encoding`; cần đọc tài liệu của nhà cung cấp cụ thể.

### Cache key explosion

Nếu dùng:

~~~http
Vary: Accept-Language, User-Agent, Cookie
~~~

số tổ hợp có thể rất lớn, khiến hit ratio gần bằng 0, lãng phí bộ nhớ/CDN cache và tăng tải origin. Giải pháp tốt hơn có thể là:
- Chuyển ngôn ngữ thành một tập giá trị đã chuẩn hóa, hoặc dùng path riêng cho ngôn ngữ.
- Không vary theo cookie đối với nội dung cá nhân: dùng `private`/`no-store`.
- Chỉ dùng các client hints thật sự cần thiết.
- Bật compression ở một tầng nhất quán và dùng cache key encoding được nhà cung cấp hỗ trợ.

Tối ưu cache-hit ratio chỉ có giá trị khi **không đánh đổi tính đúng đắn hay bảo mật**.

## 14. Viết `Vary` trong Spring MVC và WebFlux

### Spring MVC — ResponseEntity

Trong ví dụ runnable, API chuẩn là:

~~~java
return ResponseEntity.ok()
        .varyBy("Accept-Language")
        .cacheControl(CacheControl.maxAge(Duration.ofSeconds(60)).cachePublic())
        .header("Content-Language", language)
        .body(body);
~~~

Đây là **fragment** của controller. `varyBy(String... requestHeaders)` nhận một hoặc nhiều tên header; nó giúp thêm tên vào `Vary` và tránh lặp cùng tên trong những trường hợp mà builder quản lý. Khi cần nhiều selecting fields:

~~~java
return ResponseEntity.ok()
        .varyBy("Accept", "Accept-Language")
        .body(body);
~~~

Chỉ thêm `Accept` nếu nội dung/kiểu media thực sự phụ thuộc field đó. API `varyBy` là một cách rõ ràng và ít lỗi hơn tự đặt nguyên chuỗi `"Vary: ..."`; nếu có filter/proxy cũng chỉnh `Vary`, vẫn cần xem header sau cùng.

### Spring WebFlux — ResponseEntity / functional endpoints

Trong annotated controller WebFlux, `ResponseEntity` và `varyBy(...)` cũng có thể dùng:

~~~java
@GetMapping("/reactive-greeting")
public Mono<ResponseEntity<String>> greeting() {
    return Mono.just(
            ResponseEntity.ok()
                .varyBy("Accept-Language")
                .body("Hello!")
    );
}
~~~

Đây là **fragment**; class `@RestController`, imports và dependency WebFlux phải có trong project. Nó minh họa API gắn header, không phải endpoint thương lượng ngôn ngữ thật. Với functional routing/WebFlux, có thể dùng API builder tương đương để tạo header Vary. Chọn MVC hay WebFlux dựa trên web stack của ứng dụng, không dùng cả hai starter vô ý.

### Spring Security, CORS và filter

Một filter, Spring Security, CORS processor hoặc reverse proxy có thể thêm các trường `Vary`. Khi nhiều layer đóng góp giá trị, kết quả cuối cần bảo toàn **đầy đủ các selecting fields**. Đừng ghi đè:

~~~text
Vary: Accept-Encoding
~~~

thành chỉ:

~~~text
Vary: Origin
~~~

nếu cả hai điều kiện đều ảnh hưởng response. Phải thêm/merge:

~~~http
Vary: Accept-Encoding, Origin
~~~

theo cơ chế hợp lệ và kiểm tra đúng behavior. Việc dùng `ResponseEntity.varyBy(...)` cho riêng controller không đủ để chứng minh proxy downstream không xóa/ghi đè.

## 15. Quy trình test tính đúng đắn

### 15.1. Test origin bằng `curl`

Các lệnh ở mục 7 xác nhận:
- Cùng `/greeting`, body thay đổi theo `Accept-Language`.
- Response của cả `vi` và `en` đều có `Vary: Accept-Language`.
- `Content-Language` phù hợp với body.
- Response công khai có chính sách cache có thể giải thích được.

**Không dùng `curl` thường rồi nói “cache đã hit”**, vì `curl` không đại diện một browser/CDN cache có state.

### 15.2. Test qua một shared cache thật

Khi hạ tầng có CDN hoặc reverse proxy caching đã cấu hình, chạy kịch bản sau trên cùng URL:

| Thứ tự | Request | Điều cần kiểm tra |
|---|---|---|
| 1 | `Accept-Language: vi` | Cache có thể MISS, body tiếng Việt |
| 2 | `Accept-Language: vi` lặp lại | Cache có thể HIT, body vẫn tiếng Việt |
| 3 | `Accept-Language: en` | Không dùng bản Việt sai; có thể MISS |
| 4 | `Accept-Language: en` lặp lại | Cache có thể HIT, body vẫn tiếng Anh |
| 5 | Bỏ `Accept-Language` | Không tự dùng nhầm variant chỉ vì thiếu header |
| 6 | `Accept-Encoding: gzip` | Nếu compressed variant, header/body gzip khớp |
| 7 | `Accept-Encoding: identity` | Không nhận bytes gzip với encoding identity |
| 8 | Có `Origin` A và B | CORS headers đúng từng origin được cho phép |
| 9 | `If-None-Match` của variant phù hợp | 304/revalidation không trộn body hoặc validator khác variant |

`HIT`/`MISS` là kết quả **có thể** tùy policy, TTL, cache eligibility và implementation; hai request giống nhau không nhất thiết luôn HIT. Điều kiện **bắt buộc** là body và header phản hồi **đúng cho request** và không rò dữ liệu.

### 15.3. Quan sát nhiều tầng

Thu cả:
- Request headers nhìn ở **browser → CDN** và **CDN → origin**.
- Response headers ở **origin → CDN** và **CDN → browser**.
- `Vary`, `Cache-Control`, `Content-Encoding`, `Content-Type`, `Content-Language`.
- `ETag`, `Age` và những header cache-status mà hạ tầng thực sự cung cấp.
- Content hash hoặc so sánh body thật sau khi giải mã.
- Revalidation 304, redirect và error responses.

Nếu `Age` tăng và response sai, khả năng có tầng cache tái sử dụng không đúng. Tuy vậy không phải mọi CDN phát `Age` hay cache-status như nhau; cần dựa trên logs/cấu hình nhà cung cấp.

## 16. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách sửa hoặc xác minh |
|---|---|---|
| Browser tiếng Anh nhận nội dung tiếng Việt sau một request khác | Thiếu `Vary: Accept-Language` trên response cacheable | Thêm Vary nhất quán cả default variant; kiểm tra CDN key |
| Client không hỗ trợ gzip nhận body gzip | Shared cache gom variant encoding hoặc header sai | Kiểm tra `Vary: Accept-Encoding`, `Content-Encoding` và config nén |
| Origin trả đúng, qua CDN trả sai | CDN bỏ qua/ghi đè `Vary`, normalize header không phù hợp | So sánh header hai phía, cấu hình cache key |
| Có `Vary` nhưng cache vẫn lộ dữ liệu người dùng | Dựa vào `Vary: Cookie` thay cho cache privacy policy | Dùng `private`/`no-store`, bảo vệ auth và xác minh CDN |
| Ngôn ngữ mặc định hay bị cache sai | Default response không phát `Vary` | Áp dụng cùng Vary cho mọi representation |
| Sau bật gzip, ETag/304 cho dữ liệu sai | Dùng validator không đúng cho coded variants | Kiểm tra strong/weak ETag, revalidation và Vary trên 304 |
| Cache hit ratio sụt mạnh | Vary theo `User-Agent`, `Cookie` hoặc header quá chi tiết | Giảm cardinality, dùng URL/locale đã chuẩn hóa |
| Header `Vary` chỉ còn `Origin` | Proxy/filter thay thế các giá trị Vary đã có | Merge thay vì overwrite; kiểm tra response cuối |
| Có `Vary: Origin` nhưng browser vẫn chặn CORS | Thiếu/không đúng `Access-Control-Allow-Origin` và credentials policy | Cấu hình CORS, không coi Vary là cấp quyền |
| `Accept-Encoding: gzip` nhưng không thấy nén | Compression tắt, MIME không được chọn, body quá nhỏ, proxy transform | Kiểm tra server config, min-response-size, response size |
| `curl` hai lần không hiển thị HIT | curl không tự là shared cache | Thử qua cache/CDN thật và xem log/status |
| Bật `Vary: *` nhưng nghĩ đã vô hiệu hóa lưu trữ | Nhầm Vary với no-store | Dùng Cache-Control no-store khi yêu cầu không lưu |

### Checklist trước khi deploy

- [ ] Có danh sách rõ ràng request header **thật sự** làm representation hoặc response policy khác nhau.
- [ ] Mọi variant, kể cả default, trả `Vary` nhất quán khi cần.
- [ ] `Content-Type`, `Content-Language`, `Content-Encoding` khớp body thực.
- [ ] Cache-Control cho tài nguyên công khai và nội dung theo user khác nhau rõ ràng.
- [ ] Không dùng `Vary: Cookie` như cơ chế bảo mật thay `private`/`no-store`.
- [ ] Compressor, origin, proxy, CDN không ghi đè/làm rơi selecting fields.
- [ ] ETag/revalidation/304 tuân thủ ngữ nghĩa của từng variant.
- [ ] Đã thử có/không có `Accept-Language` và `Accept-Encoding`, nhiều `Origin`.
- [ ] Không giả định cache-hit ratio cao đồng nghĩa phản hồi đúng.
- [ ] Có kiểm thử qua **đường đi production**, không chỉ gọi trực tiếp localhost.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Hai request cùng URL, một gửi `Accept-Language: vi`, một gửi `en`; server trả nội dung khác. Response nên có gì?

**Đáp án:** `Vary: Accept-Language` trên các response variant có thể cache để cache không dùng lẫn ngôn ngữ.

**Câu 2.** `Vary: Accept-Encoding` có bắt buộc server phải gzip mọi response không?

**Đáp án:** Không. Header chỉ thông báo `Accept-Encoding` có thể ảnh hưởng representation; việc nén phụ thuộc request, MIME, kích thước, cấu hình server và các điều kiện khác.

**Câu 3.** `Cache-Control: public, max-age=600` có tự bảo đảm đúng ngôn ngữ không?

**Đáp án:** Không. Nó nói về cache eligibility và freshness; cần `Vary`/cache key phù hợp khi representation phụ thuộc request header.

**Câu 4.** Nếu dữ liệu phụ thuộc session cookie, chỉ thêm `Vary: Cookie` đã đủ an toàn chưa?

**Đáp án:** Chưa. Đối với nội dung cá nhân/nhạy cảm, phải có policy `Cache-Control: private` hoặc `no-store` phù hợp cùng xác thực/phân quyền và cấu hình CDN.

**Câu 5.** `Vary: *` có giống `no-store` không?

**Đáp án:** Không. `Vary: *` khiến stored response không khớp để dùng lại theo cách bình thường; `no-store` yêu cầu cache không lưu.

**Câu 6.** Nếu body và header CORS thay đổi theo `Origin`, cần lưu ý gì?

**Đáp án:** `Vary: Origin` giúp shared cache không trộn CORS responses theo origin; nhưng bản thân nó không cấp quyền CORS và không thay policy `Access-Control-Allow-Origin`.

**Câu 7.** Có nên dùng cùng một strong ETag cho body gzip và identity có bytes khác nhau không?

**Đáp án:** Không nên. Strong validator phải phản ánh tương đương mạnh của representation; kiểm tra cách nén, tạo validator và 304 cho từng variant.

**Câu 8.** Gửi `Accept-Language: en` rồi `vi` bằng curl và thấy đúng hai body có chứng minh CDN cache an toàn không?

**Đáp án:** Chưa. Nó chỉ chứng minh origin phản hồi đúng với hai request. Cần thử qua shared cache thật và đối chiếu header, body, hit/miss, 304.

### Bài tập mở rộng

Từ dự án Java mục 7, thêm lựa chọn tiếng Pháp `fr` cho `GET /greeting` và bảo đảm response có `Content-Language: fr` cùng `Vary: Accept-Language`. Sau đó triển khai sau một cache thử nghiệm có thể quan sát HIT/MISS, gửi tuần tự `vi → en → fr → vi`; ghi lại khi nào cache được phép tái sử dụng. Cuối cùng tạo một endpoint `/account/me` giả lập nội dung theo người dùng và giải thích vì sao chọn `Cache-Control: private, no-store` thay vì `Vary: Cookie`.

## 18. Nguồn tài liệu và chuẩn HTTP

- [RFC 9110 `12.5.5 — Vary (HTTP Semantics)](https://www.rfc-editor.org/rfc/rfc9110.html#name-vary)
- [RFC 9111 `4.1 — Calculating Cache Keys with Vary](https://www.rfc-editor.org/rfc/rfc9111.html#name-calculating-cache-keys-with)
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [Spring Framework — ResponseEntity.HeadersBuilder.varyBy](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ResponseEntity.HeadersBuilder.html)
- [Spring Boot 3.5 — Embedded Web Servers / Enable HTTP Response Compression](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/)
- [Spring Framework — CORS trong Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [Spring Framework — CORS trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html)
- [MDN — HTTP caching, Vary, content negotiation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)

**Thông điệp cuối:** `Vary` là một phần của **hợp đồng tính đúng đắn giữa origin và cache**. Nó không quyết định dữ liệu được cache bao lâu và không bảo mật dữ liệu cá nhân. Khi response phụ thuộc request header, phải xác định header lựa chọn, gửi `Vary` nhất quán, cấu hình cache policy phù hợp và kiểm thử tất cả tầng từ origin đến CDN/browser.
