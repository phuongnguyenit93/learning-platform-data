# Same-Origin Policy, origin và mục đích của CORS

> **Phạm vi:** Spring Boot web-runtime → Proxy và CORS. Bài học giải thích nền tảng bảo mật trình duyệt **Same-Origin Policy (SOP)**, cách xác định **origin**, vì sao cần **Cross-Origin Resource Sharing (CORS)**, browser thực thi preflight và kiểm tra response ra sao, rồi triển khai trên Spring MVC và đối chiếu Spring WebFlux/Spring Security. Ví dụ thực hành dùng **Java 17+, Spring Boot 3.3.x**, browser, curl và một web server tĩnh ở cổng khác. CORS là chính sách của trình duyệt, **không phải cơ chế xác thực hoặc phân quyền API**.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Xác định origin của URL dựa trên **scheme + hostname + port** và phân biệt same-origin với same-site.
2. Giải thích SOP hạn chế những thao tác đọc/chạm tài nguyên nào, trong khi một số thao tác điều hướng hoặc tải ảnh/script chéo origin vẫn được phép theo quy tắc riêng.
3. Nêu lý do CORS ra đời: cho phép **một origin được server ủy quyền** đọc response từ origin khác trong browser mà không phá bỏ SOP toàn cục.
4. Đọc chính xác các header `Origin`, `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Expose-Headers`, `Access-Control-Max-Age` và `Vary`.
5. Phân biệt request không cần preflight với request cần **OPTIONS preflight**; hiểu trình duyệt có thể gửi request thật nhưng chặn JavaScript đọc response.
6. Viết ứng dụng Java 17+ dùng `@CrossOrigin`, kiểm thử từ frontend ở cổng 5500 tới API ở cổng 8080, mô phỏng preflight bằng curl và kiểm tra DevTools.
7. Chọn cấu hình CORS tập trung trên Spring MVC/WebFlux, biết cách tích hợp Spring Security và proxy, xử lý credentials/cookies mà không mở quyền tùy tiện.
8. Tách CORS khỏi CSRF, CSP, cookies SameSite, TLS, authentication, authorization và các cấu hình proxy để tránh các lỗ hổng hoặc cách sửa sai như `Access-Control-Allow-Origin: *` cho mọi endpoint.

## 2. Nền tảng: origin được xác định như thế nào?

Một origin của tài liệu web theo mô hình URL thông thường được cấu thành từ:

~~~text
origin = (scheme, host, port)
~~~

Ví dụ:

~~~text
URL:     https://shop.example.test:8443/products?id=5#details
Scheme:  https
Host:    shop.example.test
Port:    8443
Origin:  https://shop.example.test:8443
~~~

**Path, query và fragment không phải thành phần của origin.** Origin không phải URL trang đầy đủ và không bao gồm `/products?id=5#details`. Khi so sánh origin, cổng mặc định của scheme được chuẩn hóa: HTTP mặc định 80, HTTPS mặc định 443; viết `https://example.test` và `https://example.test:443` tương đương origin trong tình huống HTTP thông thường. Tuy nhiên HTTPS và HTTP **khác scheme**, vì vậy khác origin.

| Trang A | Tài nguyên B | Same-origin? | Vì sao? |
|---|---|---|---|
| `https://app.example.test/a` | `https://app.example.test/b?x=1` | Có | Scheme, host và port giống nhau; path/query khác không ảnh hưởng |
| `https://app.example.test` | `http://app.example.test` | Không | Khác scheme HTTPS/HTTP |
| `https://app.example.test` | `https://api.example.test` | Không | Khác hostname/subdomain |
| `https://app.example.test` | `https://app.example.test:8443` | Không | Khác port 443/8443 |
| `http://localhost:5500` | `http://localhost:8080` | Không | Cùng host/scheme, khác port |
| `http://localhost:8080` | `http://127.0.0.1:8080` | Không | Hostname khác; tên DNS và IP không tự đồng nhất origin |
| `https://example.test` | `https://example.test:443` | Có | Cổng mặc định của HTTPS |
| `https://shop.example.test` | `https://api.example.test` | Không | Khác origin nhưng có thể thuộc cùng một *site* |

### Origin khác site

**Same-origin** so sánh ba thành phần scheme–host–port. **Same-site** liên quan khái niệm *site* của browser, thường dựa trên scheme và registrable domain (eTLD+1) trong mô hình schemeful same-site. Hai subdomain `shop.example.test` và `api.example.test` có thể **same-site nhưng cross-origin**. Cookies `SameSite` dùng các quy tắc theo site; SOP/CORS dùng origin. Đừng cấu hình CORS bằng suy luận “cùng công ty” hoặc “cùng domain cấp hai” mà bỏ qua hostname/port/scheme.

### Opaque origins và Origin: null

Các tài liệu từ `data:`, sandboxed iframe không có quyền same-origin hoặc một số ngữ cảnh local file có thể có **opaque origin** (không phải tuple scheme/host/port thông thường). Khi serial hóa trong header, origin ấy có thể thành chuỗi `null`. Không whitelist `Access-Control-Allow-Origin: null` tùy tiện để “hỗ trợ file HTML” — nhiều ngữ cảnh không đáng tin có thể tạo opaque origin và được hưởng quyền đọc nếu server cho phép literal null. Để học CORS, chạy frontend qua HTTP local server thay vì mở trực tiếp `file:///.../index.html`.

Một URL `blob:` thường liên quan origin của môi trường tạo ra nó; không nên coi mọi blob URL là một hostname độc lập. Khái niệm origin liên quan cách browser gán quyền cho *environment*, chứ không đơn thuần so sánh mọi chuỗi URL theo dạng văn bản.

## 3. Same-Origin Policy (SOP) bảo vệ điều gì?

SOP là nhóm quy tắc bảo mật của browser giúp nội dung từ một origin **không tự ý đọc/chạm dữ liệu nhạy cảm của origin khác**. Nếu bạn đang đăng nhập ngân hàng ở `https://bank.example.test`, một trang độc hại mở ở `https://evil.example.test` không được phép chỉ dùng JavaScript để `fetch` rồi đọc toàn bộ HTML/API trả dữ liệu cá nhân của ngân hàng nếu server không cấp quyền CORS phù hợp.

Nhưng SOP **không đơn giản là “browser cấm mọi request cross-origin”**. Một số tương tác cross-origin là nền tảng của Web:

- Người dùng có thể click link để **điều hướng** tới site khác.
- Trang có thể tải hình ảnh bằng `<img src="https://...">` và một số tài nguyên với điều kiện riêng.
- Trình duyệt có thể tải/thi hành script cross-origin bằng classic `<script src="...">` theo các chính sách áp dụng, dù việc đọc trực tiếp response bằng `fetch` khác biệt.
- Một trang có thể nhúng iframe cross-origin, nhưng script trong iframe và trang cha bị giới hạn truy cập DOM của nhau.
- Form HTML có thể gửi request tới origin khác trong những điều kiện nhất định; việc gửi **không tương đương** việc script của trang gửi được đọc response.

Bằng cách phân tách các quyền **gửi, nhúng, đọc và thao tác DOM**, SOP cho phép Web hoạt động mà vẫn cô lập dữ liệu giữa các origin. Các chính sách như CSP, CORP/COEP và sandbox iframe bổ sung những lớp hạn chế khác, không phải cách gọi khác của CORS.

### Ví dụ trực giác

Giả sử `https://app.example.test` chạy:

~~~javascript
const response = await fetch("https://api.example.test/profile");
const profile = await response.json();
console.log(profile);
~~~

Đây là **cross-origin fetch**. Browser sẽ áp dụng chế độ CORS (mặc định của `fetch` cho phần lớn request HTTP cross-origin), gửi `Origin: https://app.example.test` khi thích hợp và kiểm tra response của API. Nếu server không trả CORS headers cho phép, JavaScript **không đọc được** response như một đối tượng dữ liệu hợp lệ. Điều đó không chứng minh request đã không chạm server.

Với cùng URL, `curl https://api.example.test/profile` hoặc một backend Java gọi HTTP client không tự áp dụng SOP của browser. **CORS không được thiết kế để chặn bot/curl/server-to-server clients.** API vẫn phải xác thực, phân quyền và kiểm tra dữ liệu.

## 4. CORS ra đời để giải quyết nhu cầu nào?

Trong kiến trúc hiện đại, frontend ở `https://app.example.test`, API ở `https://api.example.test` và dữ liệu công khai ở CDN có thể thuộc các origin khác nhau. SOP mặc định hạn chế JavaScript đọc response cross-origin, kể cả khi **chính chủ API muốn cho phép ứng dụng frontend khác đọc**.

**Cross-Origin Resource Sharing (CORS)** là giao thức điều phối sự cho phép đó bằng HTTP headers giữa browser và server. API có thể chỉ định:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin

{"message":"Dữ liệu API công khai cho frontend được chọn"}
~~~

Khi origin trong browser request khớp với origin server cho phép và các điều kiện khác thỏa mãn, browser có thể cho JavaScript đọc response. Server **không cần vô hiệu hóa SOP**, chỉ cần nêu ngoại lệ có phạm vi.

### CORS không phải

- **Không phải authentication:** `Access-Control-Allow-Origin` không xác định ai là người dùng hoặc có token hợp lệ.
- **Không phải authorization:** client trực tiếp từ máy chủ khác vẫn có thể gọi API nếu không có các kiểm soát quyền độc lập.
- **Không phải CSRF protection:** request thay đổi trạng thái vẫn có thể được gửi theo một số cơ chế dù browser không cho script đọc response.
- **Không phải reverse proxy:** CORS là HTTP/browser policy; proxy là thành phần mạng có thể chuyển request hoặc thêm header.
- **Không phải “bật HTTPS”:** TLS mã hóa/kiểm tra danh tính ở tầng transport; CORS kiểm soát truy cập response theo origin.
- **Không phải cách xử lý lỗi JSON/404/500:** dù response có CORS hợp lệ, server vẫn có thể trả lỗi ứng dụng.

**Mục đích chính:** cho phép một trang web truy cập có kiểm soát các **HTTP response từ origin khác**, theo lựa chọn của server và quy tắc thực thi của browser.

## 5. Hai đường đi: request được gửi trực tiếp và preflight

Trong bài học nhập môn, người ta thường gọi các CORS requests với điều kiện nhất định là **simple requests**; thuật ngữ thực tế trong Fetch Standard gắn với tập **CORS-safelisted methods/headers/content types** và một số điều kiện khác.

### 5.1. Trường hợp không cần preflight

Một `GET` cross-origin thông thường với các header được browser cho phép có thể được gửi trực tiếp:

~~~http
GET /api/message HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5500
Accept: */*
~~~

Nếu server cho phép:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5500
Vary: Origin
Content-Type: application/json

{"message":"Xin chào từ API"}
~~~

Browser kiểm tra CORS headers **sau khi có response**; nếu hợp lệ, JavaScript đọc body. Nếu header cho phép thiếu/sai, browser báo CORS error và không cung cấp response cho JavaScript, mặc dù request **có thể đã được server xử lý**.

Nhóm điều kiện thông dụng **không cần preflight** gồm method `GET`, `HEAD` hoặc `POST`; request headers thuộc tập safelist; `Content-Type` nếu do client đặt phải thuộc nhóm `application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain` cùng các điều kiện liên quan. **Đây là cách tóm tắt, không phải toàn bộ Fetch Standard**: có các hạn chế chi tiết hơn về giá trị headers, event listeners, streaming body, v.v.

### 5.2. Trường hợp cần OPTIONS preflight

Với JavaScript:

~~~javascript
await fetch("http://localhost:8080/api/echo", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-Request-ID": "client-123"
  },
  body: JSON.stringify({message: "Xin chào"})
});
~~~

Browser thường phải thực hiện **preflight**, vì `Content-Type: application/json` không thuộc tập safelisted content types và `X-Request-ID` là header tùy biến.

Trước request POST, browser tự gửi:

~~~http
OPTIONS /api/echo HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5500
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-request-id
~~~

Server trả thông tin cho phép, ví dụ:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5500
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: Content-Type,X-Request-ID
Access-Control-Max-Age: 600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Status preflight thành công có thể là `200` hoặc status 2xx khác tùy server/framework; body thường không phải dữ liệu API. Nếu browser chấp nhận kết quả kiểm tra, nó mới gửi POST thật. Nếu preflight bị từ chối, **POST thật không được gửi** từ browser theo đường CORS đó. Preflight request theo giao thức thường **không kèm cookies**, do đó ứng dụng dùng Spring Security cần xử lý OPTIONS đúng thứ tự trước các bước yêu cầu session.

### 5.3. Vì sao preflight không “bảo vệ API” thay cho backend?

Preflight là hành vi **của browser**. Curl, Java HttpClient, Postman hoặc server-side code có thể gửi POST trực tiếp mà không gửi OPTIONS trước. Nếu endpoint thực hiện chuyển tiền khi chỉ nhận được POST mà không cần auth/CSRF token, CORS không thể ngăn nó bị lạm dụng.

Một **simple** POST dạng HTML form có thể tới server từ trang cross-site, ngay cả khi response không được script đọc. Do đó không dùng việc “CORS chỉ cho origin đúng” làm CSRF defense.

## 6. Bảng tra các header CORS

| Header | Gửi bởi | Ý nghĩa | Lỗi hiểu thường gặp |
|---|---|---|---|
| `Origin` | Browser request | Origin của môi trường gửi request, ví dụ `http://localhost:5500` | Tự tin rằng header không thể bị giả bởi curl/bot |
| `Access-Control-Request-Method` | Browser preflight | Method mà browser định dùng ở request thật | Nhầm với method của OPTIONS |
| `Access-Control-Request-Headers` | Browser preflight | Các non-safelisted request header mà browser muốn gửi | Tưởng là danh sách response headers |
| `Access-Control-Allow-Origin` | Server response | Chỉ một origin hợp lệ hoặc `*` trong điều kiện thích hợp | Trả `origin1, origin2` như một danh sách, nhưng browser không chấp nhận cú pháp đó |
| `Access-Control-Allow-Methods` | Server preflight | Methods được cho phép cho request thật | Nghĩ nó thay thế Spring route mapping và authorization |
| `Access-Control-Allow-Headers` | Server preflight | Request headers được phép ở request thật | Nhầm với headers JS được phép đọc từ response |
| `Access-Control-Allow-Credentials` | Server response | `true` cho phép chia sẻ response credentialed theo CORS | Dùng với `Access-Control-Allow-Origin: *` |
| `Access-Control-Expose-Headers` | Server response | Non-safelisted response headers được script phép đọc | Nhầm với `Allow-Headers` |
| `Access-Control-Max-Age` | Server preflight | Gợi ý cache kết quả preflight trong thời gian tính bằng giây | Nghĩ cache JSON response hay session |
| `Vary: Origin` | Server response / cache | Response variants thay đổi theo Origin | CORS đúng ở origin nhưng CDN cache lại header từ origin khác |

### Access-Control-Allow-Origin: một origin, không phải mảng

Một response có thể chứa:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

hoặc với **resource thực sự public và request không dùng credentials**:

~~~http
Access-Control-Allow-Origin: *
~~~

Không dùng:

~~~http
Access-Control-Allow-Origin: https://app.example.test, https://admin.example.test
~~~

để tưởng rằng browser sẽ chấp nhận cả hai. Nếu nhiều origin được phép, server so sánh incoming `Origin` với **allowlist**, rồi trả đúng **một** origin tương ứng cho mỗi request; cần cache-vary chính xác. Không phản chiếu bất kỳ origin nào mà không kiểm tra, vì về thực tế nó cho mọi website đọc response được cấp quyền.

### Expose-Headers không phải Allow-Headers

Giả sử API trả:

~~~http
X-Request-ID: server-echo-001
Access-Control-Expose-Headers: X-Request-ID
~~~

Browser JavaScript mới có thể đọc `response.headers.get("X-Request-ID")` từ response cross-origin (ngoài các headers được safelist mặc định). Ngược lại, muốn **gửi** `X-Request-ID` trên request, preflight cần `Access-Control-Allow-Headers` tương ứng. **Set-Cookie không trở thành header JavaScript đọc được chỉ nhờ Expose-Headers.**

### Preflight max-age khác HTTP cache max-age

`Access-Control-Max-Age: 600` yêu cầu browser có thể cache kết quả preflight theo ngữ nghĩa riêng; browser có thể áp thêm cap và điều kiện bộ đệm. Nó **không** thay thế `Cache-Control` dành cho response body, không bảo đảm kết quả preflight tồn tại đúng 600 giây trong mọi browser. Để test lại OPTIONS, có thể đổi tổ hợp URL/method/headers hoặc dọn preflight cache theo công cụ browser; không mặc định cứ refresh trang là có preflight mới.

## 7. CORS với cookies, credentials và SameSite

Browser `fetch` có tùy chọn:

~~~javascript
fetch("https://api.example.test/account", {
  credentials: "include"
});
~~~

`credentials: "include"` yêu cầu browser áp dụng quy tắc gửi credentials cross-origin. Nhưng **cookies không tự đảm bảo được gửi**: còn phụ thuộc cookie domain/path, `Secure`, `SameSite`, third-party cookie policy, privacy restrictions và transport HTTPS. Trong mô hình cross-site cookie thực sự cần được gửi, cookie thường cần `SameSite=None; Secure` theo yêu cầu browser hiện đại; điều này không tự tạo quyền đọc CORS.

Nếu server chủ định cho một origin sử dụng credentialed request, response tương ứng phải chứa:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không dùng `Access-Control-Allow-Origin: *` với credentialed CORS.** Browser từ chối việc cung cấp response cho script trong tổ hợp này. Đặt `Access-Control-Allow-Credentials: false` không phải cách chuẩn để “từ chối”; khi không cho phép, thường bỏ header đó.

### CORS với credentials khác CSRF

Nếu browser tự gửi session cookie cho API, một trang cross-site có thể tìm cách gửi request thay đổi trạng thái qua form/navigation hay các đường tương thích mà không cần đọc response. CORS thiếu quyền đọc không có nghĩa cookie/side effect không xảy ra. Bảo vệ mutation cần **CSRF tokens, SameSite cookies, kiểm tra Origin/Referer khi phù hợp, xác thực và authorization** theo mô hình ứng dụng.

Với token trong `Authorization`, bản thân custom/non-safelisted request header thường dẫn tới preflight, nhưng backend vẫn phải kiểm chữ ký/expiry/scope/permission. Preflight không xác minh token hợp lệ. Một lỗi phổ biến là bật rộng `allowCredentials(true)` và origins không kiểm soát để “sửa đăng nhập”; điều đó có thể cho origin độc hại đọc dữ liệu nhạy cảm nếu cookie/auth credentials được gửi.

### CORS và cookie khác nhau trong hai ví dụ

| Trường hợp | Browser gửi cookies? | Server CORS cần gì? | Lưu ý |
|---|---|---|---|
| Cross-origin fetch mặc định `credentials: "same-origin"` | Không gửi credentials cross-origin theo mode mặc định | ACAO hợp lệ; không nhất thiết ACAC | JavaScript có thể đọc dữ liệu public, không có session |
| Cross-origin fetch `credentials: "include"` | Có thể gửi nếu cookie/policy cho phép | Origin cụ thể + `Access-Control-Allow-Credentials: true` | Không dùng wildcard, vẫn cần CSRF/authorization |
| Server-to-server request | Tùy client tự đặt header/cookies | Không cần CORS để client đọc | Backend vẫn phải xác thực và phân quyền |
| Preflight OPTIONS | Theo giao thức không dùng session cookies thông thường | Có thể cần allow-headers/methods/origin; security phải không chặn sai | Không ép preflight phải đăng nhập bằng session |

## 8. Ví dụ đầy đủ: Spring Boot MVC phục vụ API cross-origin

Ta dựng **hai server local**:

~~~text
Browser page: http://localhost:5500/index.html
               |
               | fetch /api/message và /api/echo
               | Origin: http://localhost:5500
               v
Spring Boot:  http://localhost:8080
               |
               v
           @RestController
~~~

Đây là **cross-origin** vì cổng 5500 khác cổng 8080. Không cần đăng nhập, cookies hay database cho bài thử; chúng chỉ làm phức tạp việc nhận diện CORS.

### 8.1. Maven POM chạy được

Tạo một Spring Boot project Java 17+ với file `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>cors-origin-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Spring MVC sử dụng embedded Tomcat từ `spring-boot-starter-web` mặc định. Đây là cấu hình **không có Spring Security**, phù hợp để nghiên cứu riêng CORS. Trong production, cần tích hợp Spring Security hoặc bộ kiểm soát auth phù hợp ở mọi endpoint nhạy cảm.

### 8.2. Java source đầy đủ

Tạo `src/main/java/example/cors/OriginCorsApplication.java`:

~~~java
package example.cors;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.RequestMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class OriginCorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(OriginCorsApplication.class, args);
    }

    public record EchoPayload(String message) { }

    @RestController
    @RequestMapping("/api")
    @CrossOrigin(
            origins = "http://localhost:5500",
            methods = {RequestMethod.GET, RequestMethod.POST},
            allowedHeaders = {"Content-Type", "X-Request-ID"},
            exposedHeaders = "X-Request-ID",
            maxAge = 600)
    public static class DemoController {

        @GetMapping("/message")
        public ResponseEntity<Map<String, String>> message() {
            return ResponseEntity.ok()
                    .header("X-Request-ID", "server-get-001")
                    .body(Map.of("message", "Xin chào từ API"));
        }

        @PostMapping("/echo")
        public ResponseEntity<Map<String, String>> echo(
                @RequestBody EchoPayload payload) {

            if (payload.message() == null
                    || payload.message().isBlank()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "message must not be blank");
            }

            return ResponseEntity.ok()
                    .header("X-Request-ID", "server-echo-001")
                    .body(Map.of("echo", payload.message()));
        }
    }
}
~~~

Cấu hình cổng trong `src/main/resources/application.properties`:

~~~properties
server.port=8080
~~~

**Giải thích code:**

- `@RestController` khiến controller trả JSON/text response, không phải template view.
- `@CrossOrigin` giới hạn **origin** được phép đọc response từ browser là `http://localhost:5500`. Trang mở ở `http://127.0.0.1:5500` là **origin khác**, nên không tự được cho phép.
- `methods = {GET, POST}` là các method mà CORS cho phép ở API này; nó **không tạo thêm route**. `@GetMapping` và `@PostMapping` mới quyết định method/path ứng dụng thực sự xử lý.
- `allowedHeaders` cho phép browser gửi JSON `Content-Type` và header tùy biến `X-Request-ID`; những request headers khác vẫn chịu kiểm tra CORS tương ứng.
- `exposedHeaders` cho phép JavaScript đọc `X-Request-ID` của **response**; không liên quan đến request header cho phép.
- `maxAge = 600` gợi ý cache **preflight result** trong 600 giây; không cache JSON response 600 giây.
- `allowCredentials` không bật. Đây là demo public không cookie, an toàn hơn việc bật credentials rộng khi không có nhu cầu.
- Không tự viết handler `@RequestMapping(method=OPTIONS)`. Spring MVC CORS infrastructure có thể xử lý OPTIONS preflight hợp lệ cho controller mapping.

Spring Boot application cần Maven 3.x và Java 17+. Khởi động từ thư mục gốc:

~~~bash
mvn spring-boot:run
~~~

Kiểm tra không có origin restriction ở một HTTP client thuần:

~~~bash
curl -i http://localhost:8080/api/message
~~~

Kết quả dự kiến là **HTTP 200** và JSON chứa `"message":"Xin chào từ API"`. Curl không thực thi SOP. Nếu không gửi Origin, việc response có hay không có CORS-specific headers không quyết định curl có đọc được body hay không.

## 9. Trang HTML local hoàn chỉnh để thấy CORS trong browser

Tạo thư mục `frontend/` cùng cấp với `pom.xml`, đặt file `frontend/index.html`:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Origin và CORS</title>
</head>
<body>
  <h1>Frontend ở cổng 5500</h1>
  <button id="read">GET cross-origin</button>
  <button id="send">POST JSON cần preflight</button>
  <pre id="result"></pre>

  <script>
    const output = document.getElementById("result");
    const base = "http://localhost:8080/api";

    document.getElementById("read")
      .addEventListener("click", async () => {
        try {
          const response = await fetch(base + "/message");
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const data = await response.json();
          const trace = response.headers.get("X-Request-ID");
          output.textContent = "GET: "
            + JSON.stringify(data) + "\ntrace=" + trace;
        } catch (error) {
          output.textContent = "GET failed: " + error.message;
        }
      });

    document.getElementById("send")
      .addEventListener("click", async () => {
        try {
          const response = await fetch(base + "/echo", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-Request-ID": "client-123"
            },
            body: JSON.stringify({message: "Từ frontend"})
          });
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const data = await response.json();
          const trace = response.headers.get("X-Request-ID");
          output.textContent = "POST: "
            + JSON.stringify(data) + "\ntrace=" + trace;
        } catch (error) {
          output.textContent = "POST failed: " + error.message;
        }
      });
  </script>
</body>
</html>
~~~

Dùng `output.textContent` thay vì innerHTML để không vô tình thực thi nội dung HTML lấy từ response. Đó là thói quen an toàn dù bài này chủ yếu nói về CORS.

Trong terminal thứ hai, chạy một web server tĩnh ở thư mục `frontend`:

~~~bash
cd frontend
python3 -m http.server 5500
~~~

Trên Windows có thể dùng `py -m http.server 5500` hoặc `python -m http.server 5500` tùy cài đặt. Mở chính xác:

~~~text
http://localhost:5500/index.html
~~~

Đừng mở file trực tiếp từ `file:///`, và đừng đổi tùy tiện sang `http://127.0.0.1:5500` nếu server chỉ cho phép origin `localhost:5500`.

### Điều nên thấy ở DevTools

Mở **Developer Tools → Network**, bật Preserve log nếu muốn giữ log request khi thao tác:

1. Click “GET cross-origin”: thường có một request GET tới cổng 8080, response có `Access-Control-Allow-Origin: http://localhost:5500` và body JSON. Không nhất thiết có OPTIONS.
2. Click “POST JSON cần preflight”: thường xuất hiện OPTIONS `/api/echo`, rồi POST `/api/echo`. Nếu browser đang có preflight cache hợp lệ, OPTIONS có thể không xuất hiện lại trong những lần bấm tiếp theo.
3. Kết quả hiển thị `trace=server-get-001` hoặc `trace=server-echo-001` vì server đặt response header `X-Request-ID` và `Access-Control-Expose-Headers` cho phép script đọc.
4. Đổi tab frontend sang origin không nằm trong allowlist (ví dụ server khác trên port 5501), thử lại: browser nên từ chối cung cấp response cho JS hoặc không gửi request thật nếu preflight thất bại. Console có thể báo CORS policy error.

**Lưu ý:** thông báo browser thường dạng `TypeError: Failed to fetch` hoặc “blocked by CORS policy”, không nhất thiết cung cấp HTTP status cho JavaScript. Điều này có thể khác với tình huống server thực sự trả 4xx/5xx mà CORS headers hợp lệ, khi đó JS có thể nhận Response với `ok=false`.

## 10. Dùng curl để tách phần browser khỏi phần server

Curl hữu ích để nhìn request/response headers nhưng **không tự cưỡng chế CORS**. Các lệnh dưới đây chỉ mô phỏng header do browser thường gửi.

### 10.1. GET có Origin được phép

~~~bash
curl -i \
  -H 'Origin: http://localhost:5500' \
  http://localhost:8080/api/message
~~~

Trong Windows PowerShell, dùng `curl.exe` và lệnh trên một dòng nếu cần. Kỳ vọng có response 200, JSON và `Access-Control-Allow-Origin` khớp origin frontend; có thể có `Vary: Origin` và các header Vary cho preflight theo Spring implementation.

### 10.2. Preflight giả lập

~~~bash
curl -i -X OPTIONS http://localhost:8080/api/echo \
  -H 'Origin: http://localhost:5500' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-request-id'
~~~

Đây là OPTIONS **có đủ thông tin preflight**. Chỉ `curl -X OPTIONS` mà không có Origin và Access-Control-Request-Method chưa tương đương browser preflight. Trong response hợp lệ mong đợi origin được allow, POST và hai request headers được chấp nhận cùng `Access-Control-Max-Age` trong giới hạn policy của Spring/browser. Status có thể là 200 hoặc một thành công 2xx phù hợp.

### 10.3. Gửi POST thật

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
  -H 'Origin: http://localhost:5500' \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: client-123' \
  --data '{"message":"Hello"}'
~~~

Response thành công chứa JSON với `"echo":"Hello"` và `X-Request-ID: server-echo-001`. Khi chạy bằng curl, bạn có thể đọc header X-Request-ID dù server **không** expose nó cho browser JavaScript: đó là khác biệt giữa mạng/HTTP client và browser CORS enforcement.

### 10.4. Origin không nằm trong allowlist

~~~bash
curl -i \
  -H 'Origin: http://localhost:5501' \
  http://localhost:8080/api/message
~~~

Spring MVC CORS processor có thể trả 403 cho request có Origin không được phép; behavior HTTP phụ thuộc route, filter chain và cấu hình thực. Curl có thể đọc response bất kể CORS, nên **đừng kết luận “CORS cho phép” chỉ vì curl nhận body**. Điều cần kiểm tra là browser có được phép đọc response từ origin đó hay không, và server có chính sách độc lập bảo vệ tài nguyên nhạy cảm hay không.

### 10.5. Request không gửi Origin

~~~bash
curl -i http://localhost:8080/api/message
~~~

Request từ curl không có Origin không phải là một cross-origin browser request theo cách mà browser điều khiển. Nhiều API vẫn trả 200. **CORS không phải tường lửa IP, JWT verification hay API key gate**.

## 11. Tại sao cấu hình @CrossOrigin không nên dùng vô điều kiện?

Spring Framework cho phép đặt `@CrossOrigin` trên controller class hoặc method. Nếu dùng `@CrossOrigin` không chỉ định origins, behavior mặc định có thể tương đối rộng; cụ thể framework tài liệu hiện hành mô tả default cho phép origins/headers/methods theo mapping, còn `allowCredentials` không bật mặc định. Với endpoint public chỉ phục vụ dữ liệu công khai có thể phù hợp, nhưng với API riêng tư cần allowlist chặt.

Hai ví dụ tương phản:

~~~java
// Chỉ minh họa cách khai báo annotation.
@CrossOrigin(origins = "https://app.example.test")
@GetMapping("/public-catalog")
public List<Item> list() { /* ... */ }
~~~

~~~java
// Rủi ro: rộng hơn nhu cầu nếu dữ liệu user-specific.
@CrossOrigin
@GetMapping("/user-profile")
public Profile profile() { /* ... */ }
~~~

Các class `Item`, `Profile` ở đây thuộc ứng dụng thực, mã không tự biên dịch độc lập. CORS rộng không tự tạo authentication bypass, nhưng nếu client gửi credentials trong cấu hình khác hoặc dữ liệu endpoint công khai nhầm, bề mặt bị đọc cross-origin có thể mở quá mức. Luôn quyết định chính sách theo data classification, origin tin cậy và credentials requirement.

### Khi nào dùng @CrossOrigin?

- Một hoặc ít endpoint có policy riêng, dễ đặt ngay cạnh controller.
- CORS policy gắn với nghiệp vụ của route, không có nhiều origin động.
- Dự án nhỏ hoặc API public cần một allowlist rõ ràng.

Khi nhiều controllers dùng cùng frontend origin và yêu cầu CORS nhất quán, nên dùng **central configuration** thay vì sao chép annotation vào hàng chục class.

## 12. Spring MVC: cấu hình CORS toàn cục

Trong một ứng dụng Spring MVC, có thể dùng `WebMvcConfigurer`:

~~~java
package example.cors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class GlobalMvcCorsConfig implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5500")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-Request-ID")
                .exposedHeaders("X-Request-ID")
                .allowCredentials(false)
                .maxAge(600);
    }
}
~~~

Class Java trên có thể được thêm vào project MVC nếu không muốn đặt `@CrossOrigin`; khi thử **cấu hình này** nên **bỏ @CrossOrigin** khỏi controller demo để hiểu một nguồn policy duy nhất. Nếu đặt cả annotation và global settings, Spring MVC có thể **combine** cấu hình CORS cục bộ và toàn cục theo quy tắc framework; một số thuộc tính kiểu tập hợp có thể được kết hợp còn thuộc tính đơn có thể override. Không dựa vào trực giác rằng policy “chặt hơn sẽ luôn thắng”.

- `addMapping("/api/**")` áp dụng cho routes theo pattern, không phải “mở CORS trên mọi tài nguyên/static page”.
- `allowedOrigins` kiểm tra **origin string** có scheme, host, port. Nó không so trực tiếp URL path.
- `allowedMethods` chỉ định methods mà CORS cho phép, nhưng endpoint/controller vẫn phải có handler cho method.
- `allowedHeaders` phục vụ request headers của preflight; `exposedHeaders` phục vụ response headers mà browser script đọc.
- `maxAge` được diễn giải theo giây, không phải TTL JSON.
- `allowCredentials(false)` là policy non-credentialed; nếu không cần cookies, đây là lựa chọn đơn giản.

**Không cần `@EnableWebMvc` chỉ để bật CORS.** Spring Boot MVC auto-configuration đã hoạt động; thêm `WebMvcConfigurer` là cách mở rộng ít xâm lấn. `@EnableWebMvc` có thể thay đổi nhiều cấu hình mặc định của Boot và không phải bước cần thiết để sửa lỗi CORS.

### Nhiều allowed origins

Nếu có cả production và một dev frontend:

~~~java
registry.addMapping("/api/**")
        .allowedOrigins(
                "https://app.example.test",
                "http://localhost:5500")
        .allowedMethods("GET", "POST");
~~~

Danh sách ở đây là **allowlist của server**, còn response sẽ trả một origin phù hợp cho **mỗi request**, không tạo một `Access-Control-Allow-Origin` chứa cả hai. Đừng đưa origin dev localhost vào production nếu không có nhu cầu; cấu hình theo profile/environment.

## 13. Origin patterns, wildcard và cache proxy

### Không dùng wildcard tùy tiện

Nếu dữ liệu thật sự public và không dùng credentials, có thể dùng `Access-Control-Allow-Origin: *`. Nhưng với dữ liệu account, lịch sử giao dịch, thông tin nội bộ hoặc API dựa trên cookie, đó thường là thiết kế không phù hợp.

Khi `allowCredentials(true)` trong Spring CORS, `allowedOrigins("*")` không được kết hợp theo quy tắc của Spring/Fetch. Framework có `allowedOriginPatterns` để khớp những nhóm origin nếu thật sự cần; nó có thể phản hồi **origin cụ thể đã match** thay vì literal wildcard. Tuy nhiên pattern rộng như `https://*.example.test` có thể vô tình cấp quyền cho subdomain bị takeover hoặc tenant không đáng tin. **Ưu tiên allowlist cụ thể** với ứng dụng có credentials.

### Cẩn trọng Vary và CDN

Giả sử shared HTTP cache/CDN giữ một response với:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
~~~

Nếu CDN bỏ qua `Vary: Origin` hoặc cache key không tách các variants, client từ `https://admin.example.test` có thể nhận response headers gắn với origin trước đó. Thường browser sẽ chặn đọc vì ACAO không match, nhưng cache policy sai có thể gây lỗi khó đoán hoặc rò rỉ khi có kiểu phản chiếu Origin không an toàn. Với authenticated data, phải thiết kế cả `Cache-Control: private/no-store`, key/authorization và caching tại CDN.

Đặc biệt với **preflight response**, variation có thể phụ thuộc `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`. Framework thường bổ sung Vary phù hợp; nếu proxy tự thêm headers, cần đảm bảo không tạo nhiều giá trị ACAO bất hợp lệ.

### Proxy và CORS headers phải có owner

Một kiến trúc:

~~~text
Browser --> CDN/Ingress/Nginx --> Spring Boot API
               |
               +--- có thể thêm/ghi đè CORS headers
~~~

Nếu Nginx trả `Access-Control-Allow-Origin: *` trong khi Spring trả origin cụ thể, response có thể chứa **hai ACAO headers** hoặc giá trị không tương thích. Browser sẽ từ chối. Tốt nhất chọn **một tầng chịu trách nhiệm chính** cho CORS policy, nhất là với cookies, đồng thời test end-to-end qua đúng ingress. Nếu proxy tự xử lý OPTIONS, phải bảo đảm policy của nó đồng bộ với Spring Security/routes, không cho qua methods/headers không được backend chấp nhận.

## 14. Spring Security: CORS cần xử lý trước authentication

Khi có `spring-boot-starter-security`, filter chain của Spring Security có thể từ chối preflight nếu request OPTIONS không có session/cookie/token. Spring Security docs nhấn mạnh CORS nên được xử lý **trước** security processing theo integration đúng, vì preflight thường không mang session credentials.

Với Spring MVC có CORS config thông qua `WebMvcConfigurer`, cấu hình Security thường có thể tích hợp:

~~~java
// Mảnh cấu hình: đặt trong @Configuration của ứng dụng
// đã có spring-boot-starter-security.
@Bean
SecurityFilterChain filterChain(HttpSecurity http)
        throws Exception {
    http.cors(Customizer.withDefaults());
    http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated());
    return http.build();
}
~~~

Đoạn trên là **snippet**, cần imports `org.springframework.security.web.SecurityFilterChain`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.config.Customizer`, `org.springframework.context.annotation.Bean` và một ứng dụng có auth phù hợp. **Không** lấy snippet này chèn vào demo không Security rồi kỳ vọng compile. Nó cũng **không tắt CSRF**; với POST cookie-based auth cần giữ CSRF protection phù hợp và xử lý tokens trong frontend.

Nếu Spring Security không nhận CORS config MVC bạn mong đợi, có thể định nghĩa một `UrlBasedCorsConfigurationSource` bean với allowlist rõ và dùng `http.cors(...)` theo cấu hình tương ứng. Nhưng đừng định nghĩa nhiều `CorsConfigurationSource` beans rồi mặc định Security tự chọn đúng; xem bean wiring, filter order và Spring Security version.

### Đúng nghĩa của preflight 401/403

Một OPTIONS hợp lệ có thể bị từ chối vì:

1. Security yêu cầu auth trước khi CORS filter xử lý.
2. Origin chưa được allow.
3. Method (ví dụ DELETE) không nằm trong allowedMethods.
4. Header (ví dụ Authorization hoặc X-Token) không nằm trong allowedHeaders.
5. Request thực bị chặn bởi gateway/WAF trước khi tới Spring.
6. Path không match controller/CORS mapping hoặc route proxy chuyển sai.

Bật `permitAll()` cho mọi OPTIONS **không đủ** nếu CORS header không được trả đúng, và mở mọi OPTIONS cũng không tạo quyền đọc dữ liệu. Ngược lại, tắt CSRF toàn cục chỉ để POST “hết lỗi CORS” là cách sửa nguy hiểm; cần phân biệt CORS preflight, CSRF token failure và authentication failure qua Network/logs.

## 15. Spring WebFlux cũng hỗ trợ CORS, nhưng dùng API config reactive

Với WebFlux, annotated controllers vẫn có `@CrossOrigin`. Để cấu hình toàn cục cho WebFlux, dùng `WebFluxConfigurer` và package reactive:

~~~java
package example.reactivecors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class GlobalReactiveCorsConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.test")
                .allowedMethods("GET", "POST")
                .allowedHeaders("Content-Type", "X-Request-ID")
                .exposedHeaders("X-Request-ID")
                .maxAge(600);
    }
}
~~~

Class này là một **configuration file cho dự án WebFlux**, không phải runnable server độc lập; cần `@SpringBootApplication`, `spring-boot-starter-webflux` và annotated routes. Trong Spring WebFlux, `WebFluxConfigurer` / `org.springframework.web.reactive.config.CorsRegistry` khác với `WebMvcConfigurer` / `org.springframework.web.servlet.config.CorsRegistry`. Đừng import nhầm package nếu thấy hai class cùng tên CorsRegistry.

Nếu ứng dụng dùng **functional endpoints (RouterFunction)**, hãy kiểm tra cơ chế `CorsWebFilter` hoặc cấu hình reactive pipeline tương thích, vì không nên suy ra `@CrossOrigin` trên một controller khác tự áp dụng cho mọi functional route. Spring Security WebFlux dùng `SecurityWebFilterChain` và cấu hình `ServerHttpSecurity.cors(...)`, **khác** với Servlet `SecurityFilterChain`/`HttpSecurity`.

Lưu ý: dùng WebFlux không làm CORS biến thành “non-blocking authorization”. Browser áp dụng cùng Origin/CORS model; chỉ framework xử lý HTTP khác. Với cả MVC và WebFlux, CORS nên được kiểm tra kết hợp với reverse proxy và security middleware của stack đang triển khai.

## 16. Phân biệt CORS với CSRF, CSP và các cơ chế khác

| Cơ chế | Mục tiêu chính | Tại đâu? | Có thay thế CORS không? |
|---|---|---|---|
| **SOP** | Cô lập quyền đọc/DOM giữa origins | Browser | CORS là ngoại lệ có kiểm soát cho một số request |
| **CORS** | Server cho phép browser JS đọc response cross-origin theo điều kiện | HTTP headers + browser | Không thay auth, CSRF, CSP |
| **CSRF protection** | Ngăn browser của người dùng bị lừa thực hiện thao tác có hiệu lực dựa trên credentials tự động | Server + cookie/token/origin checks | Không. CORS không ngăn mọi mutation request |
| **CSP connect-src** | Hạn chế nơi JavaScript của **trang hiện tại** có thể kết nối | Browser thực thi policy do trang phát | Không. CSP của frontend không cho API từ origin khác quyền CORS |
| **SameSite cookie** | Hạn chế gửi cookie theo quan hệ site | Browser cookie policy | Không. Same-site khác same-origin |
| **CORP/COEP/COOP** | Chính sách tài nguyên/cô lập browsing context để giảm rủi ro cross-origin khác | Browser / response headers | Không. Áp dụng cho các use case riêng |
| **TLS/HTTPS** | Bảo mật truyền tải và xác thực endpoint theo trust | HTTP transport | Không. HTTPS app và HTTPS API vẫn có thể cross-origin |
| **Authentication/Authorization** | Xác định danh tính, kiểm quyền dữ liệu/hành động | Application/API gateway | Bắt buộc độc lập với CORS |
| **Reverse proxy** | Route, terminate TLS, cache, giới hạn request, có thể inject headers | Infrastructure | Proxy có thể quản lý CORS, nhưng bản thân proxy không phải SOP |

**Một nguyên tắc thực hành:** nếu tắt CORS trong browser khiến lỗi JavaScript, đừng vội “fix” bằng cách tắt CSRF, cho `*` mọi endpoint, thêm wildcard response headers hoặc chạy browser với web security disabled. Thay vào đó hãy chẩn đoán chính xác origin, preflight và quyền đọc theo browser policy.

## 17. Checklist debug lỗi CORS theo từng tầng

### Bước 1 – Ghi đúng hai origins

- URL đang mở của frontend là gì **bao gồm scheme, hostname và port**?
- API URL được gọi từ `fetch` là gì?
- Có redirect HTTP → HTTPS, redirect sang host khác hoặc proxy rewrite khiến origin thực không như nghĩ không?
- Người dùng mở frontend bằng `localhost` hay `127.0.0.1`? Đây là hai hostname khác nhau.

Trong DevTools Console:

~~~javascript
console.log(window.location.origin);
~~~

Kết quả mong đợi cho lab khi mở đúng địa chỉ: `http://localhost:5500`. Không dựa vào tên project hoặc IP máy host để đoán origin.

### Bước 2 – Xem Network request đầu tiên

- Có OPTIONS preflight không? Nếu có, đọc `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`.
- Nếu OPTIONS trả 401/403/404/405, kiểm tra Security, CORS mapping, gateway/WAF và route.
- Nếu không có OPTIONS, request có thể thuộc nhóm CORS-safelisted hoặc preflight đã được browser cache; không coi “không thấy OPTIONS” là proof CORS bị tắt.
- Nếu request GET đã gửi và response 200 nhưng Console báo CORS, nhìn response headers: ACAO có chính xác origin của frontend không? Có duplicate headers hay wildcard+credentials sai không?

### Bước 3 – Kiểm tra response preflight và response thật

Cần phân biệt:

~~~text
Preflight OPTIONS response:
  Access-Control-Allow-Origin
  Access-Control-Allow-Methods
  Access-Control-Allow-Headers
  Access-Control-Max-Age
  Access-Control-Allow-Credentials (nếu có credentials)

Actual GET/POST response:
  Access-Control-Allow-Origin
  Access-Control-Allow-Credentials (nếu có credentials)
  Access-Control-Expose-Headers (nếu JS đọc header riêng)
~~~

Nếu preflight thành công nhưng actual response không có ACAO (ví dụ server lỗi 500 và proxy bỏ headers ở error pages), browser vẫn có thể chặn JS đọc response. CORS phải áp dụng nhất quán cho cả thành công và lỗi, qua đúng middleware/proxy.

### Bước 4 – Phân biệt lỗi mạng/TLS và CORS

Nếu DNS lookup thất bại, TLS certificate không được tin, mixed-content policy chặn từ frontend HTTPS sang HTTP, server không listen, hoặc proxy timeout, browser có thể báo fetch failed trước khi CORS hoàn tất. Bổ sung ACAO vào controller **không chữa được** lỗi TLS/network. Dùng curl với xác minh TLS đúng, Network waterfall, server logs và proxy logs để tìm nơi request bị ngắt.

### Bước 5 – Kiểm tra quyền và cookie

Nếu fetch dùng `credentials: "include"`, kiểm:

- Origin allowlist **cụ thể**, không `*`.
- Response `Access-Control-Allow-Credentials: true` khi phù hợp.
- Cookie có domain/path/SameSite/Secure và third-party policy đúng.
- API thực sự có authentication và authorization.
- CSRF token xử lý đúng cho mutation; đừng tắt CSRF như một “CORS workaround”.
- Browser preflight OPTIONS không mang session cookie thông thường; Spring Security filter order đúng.

### Bước 6 – Loại bỏ xung đột tại proxy

Kiểm tra cả direct backend `http://localhost:8080` và URL thực qua ingress. Nếu hai đường khác nhau, khả năng proxy/CDN/WAF thay headers hoặc chặn OPTIONS. Không sửa cả Nginx và Spring theo kiểu mỗi nơi thêm một ACAO; chọn owner và có integration test ở URL cuối cùng.

## 18. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Sửa |
|---|---|---|
| `No 'Access-Control-Allow-Origin' header` | Route thiếu CORS policy, controller không khớp, proxy bỏ header | Cấu hình đúng mapping và origin, kiểm tra actual response |
| `ACAO does not match origin` | Sai scheme/host/port, frontend dùng IP thay localhost | Đọc window.location.origin, sửa allowlist chính xác |
| `Credential is not supported if ACAO='*'` | Credentialed fetch cùng wildcard | Dùng origin cụ thể + allowCredentials true khi thật sự cần |
| `Multiple Access-Control-Allow-Origin` | Proxy + app cùng thêm header | Chỉ một owner CORS, không gửi danh sách origins trong ACAO |
| `Request header x-request-id not allowed` | Custom request header chưa được preflight allow | Thêm allowedHeaders phù hợp nếu API thực sự cho phép |
| `Method PUT/DELETE not allowed` | Preflight method chưa được allow | Chỉ bổ sung method cần thiết và route/authorization tương ứng |
| OPTIONS 401/403 | Security chain chặn preflight hoặc origin sai | Bật integration CORS trước auth, kiểm tra allowlist |
| POST 403 sau OPTIONS thành công | CSRF token thiếu, auth/authorization fail | Chẩn đoán Security, không tự coi là CORS |
| GET 200 trong curl nhưng fetch fail | Curl không enforce CORS; browser không nhận ACAO phù hợp | Test bằng browser DevTools, kiểm tra CORS headers |
| `Set-Cookie` không đọc được từ response.headers | Set-Cookie bị cấm expose cho JS | Để browser quản lý cookie theo policy, không đọc bằng fetch headers |
| Frontend mở `file:///...` gây origin null | Trang không phục vụ qua HTTP origin ổn định | Chạy local static server trên localhost |
| Từ frontend HTTPS gọi HTTP API bị chặn | Mixed content / HTTPS security, không chỉ CORS | Dùng HTTPS cho API hoặc cấu hình proxy TLS đúng |
| Preflight cache khiến OPTIONS ít xuất hiện | `Access-Control-Max-Age` hoặc browser cache | Kiểm tra lần đầu/cách cache và tránh kết luận sai |
| Browser vẫn fail dù backend đúng | CDN/proxy/WAF sửa headers hoặc cache variants | Test qua URL thực, Vary Origin, một policy owner |
| API bị gọi bởi bot từ origin lạ | CORS không phải firewall/API auth | Thêm authentication, authorization, rate limiting, validation |
| Dữ liệu user bị JS trang lạ đọc | Allowed origins quá rộng + credentialed response | Thu hẹp allowlist, review cookies, credentials, CSRF và thông tin nhạy cảm |

## 19. Một test matrix thực tế trước khi release

Một API cross-origin nên có kiểm thử với các trường hợp **được phép** và **bị từ chối**, không chỉ nhìn status 200 một lần.

| Case | Request từ đâu | Expected browser behavior |
|---|---|---|
| 1. Allowed GET | `http://localhost:5500` → `http://localhost:8080/api/message` | JS đọc JSON được, không nhất thiết có OPTIONS |
| 2. Allowed JSON POST | 5500 → `/api/echo` với JSON và X-Request-ID | Preflight hợp lệ (nếu chưa cache), POST được gửi và JS đọc JSON |
| 3. Allowed exposed header | 5500 → `/api/message` | JS đọc `X-Request-ID` vì Expose-Headers |
| 4. Disallowed origin | 5501 → cùng API | Browser không cho JS đọc response; route có thể vẫn được chạm với simple GET |
| 5. Wrong scheme | `https://localhost:5500` nếu thực sự chạy HTTPS → API HTTP | Khác origin; còn có thể bị mixed-content blocking |
| 6. Wrong hostname | `http://127.0.0.1:5500` → API localhost | Không tự match `http://localhost:5500` |
| 7. Disallowed method | 5500 → DELETE `/api/echo` | Không được preflight authorize hoặc không có handler; không tự tạo DELETE route |
| 8. Disallowed header | 5500 → POST với `X-Admin-Key` | Browser preflight thất bại nếu header không được allowed |
| 9. Credentialed wildcard | Any origin + credentials include + ACAO wildcard | Browser không chia sẻ response cho JS |
| 10. Server error page | Allowed origin nhưng handler trả 4xx/5xx | CORS headers cần đúng để JS đọc lỗi hữu ích; authorization vẫn áp dụng |
| 11. Proxy/nginx path | Frontend → deployed public API URL | Kết quả giống policy backend, không có duplicate/stripped ACAO |
| 12. Server-to-server request | Java HttpClient hoặc curl không gửi Origin | API vẫn cần auth; CORS không phải bộ lọc bảo mật |

Khi chạy test tự động, đừng chỉ kiểm `Access-Control-Allow-Origin` trên response từ curl: hãy có **browser-level integration test** (Playwright/Selenium hoặc manual DevTools) để xác nhận hành vi Fetch/preflight/credentials thật. Với hệ production, dùng các host do tổ chức sở hữu thay vì giả định mọi tên miền ví dụ có DNS/TLS thật.

### Kết luận trong một câu

**SOP đặt ranh giới đọc/chạm dữ liệu giữa origins trong browser; CORS là ngoại lệ do server cho phép browser JavaScript đọc một số response cross-origin; còn authentication, authorization và CSRF protection vẫn phải được thiết kế độc lập.**

## 20. Câu hỏi tự kiểm tra

**1. Origin có bao gồm path và query không?**  
Không. Origin thông thường gồm scheme, host, port. `https://a.example.test/x` và `https://a.example.test/y?z=1` có cùng origin.

**2. `http://localhost:5500` và `http://localhost:8080` có same-origin không?**  
Không. Port khác nhau.

**3. `https://shop.example.test` và `https://api.example.test` có cùng origin vì cùng domain đăng ký không?**  
Không. Subdomain khác hostname nên cross-origin, dù có thể same-site.

**4. SOP có cấm browser gửi mọi request cross-origin không?**  
Không. SOP chủ yếu ngăn các truy cập/đọc bị hạn chế; một số tải tài nguyên/điều hướng/form request cross-origin vẫn xảy ra theo quy tắc.

**5. Vì sao phải có CORS?**  
Để server cho phép JavaScript của các origin được chọn đọc cross-origin responses mà không tắt SOP cho toàn Web.

**6. Curl không thấy lỗi CORS, còn browser fetch báo lỗi. Ai sai?**  
Không ai nhất thiết sai. Curl không enforce browser SOP, còn browser kiểm response headers theo CORS. Phải kiểm API response và allowlist.

**7. POST application/json với X-Request-ID thường có OPTIONS trước không?**  
Có, khi là cross-origin browser CORS request và chưa có preflight cache hợp lệ, vì non-safelisted content type/header.

**8. Preflight OPTIONS có chứa session cookie như request thật không?**  
Theo quy tắc CORS, preflight không gửi cookies thông thường; security phải xử lý preflight trước khi áp authentication phụ thuộc cookie.

**9. Server có thể trả ACAO với hai origins ngăn dấu phẩy không?**  
Không. Response phải chỉ định một origin hoặc `*` trong điều kiện hợp lệ.

**10. `Access-Control-Allow-Headers` và `Access-Control-Expose-Headers` khác gì?**  
Allow-Headers cho request headers được browser gửi sau preflight; Expose-Headers cho response headers mà JavaScript được đọc.

**11. CORS có tự bảo vệ khỏi CSRF không?**  
Không. Một số state-changing requests vẫn có thể được gửi mà không cần đọc response. Cần CSRF protection/authorization riêng.

**12. `Access-Control-Allow-Origin: *` có dùng cùng `Access-Control-Allow-Credentials: true` cho cookie-based API được không?**  
Không. Browser không chấp nhận tổ hợp này cho credentialed CORS.

**13. `Access-Control-Max-Age` là TTL của JSON response?**  
Không. Nó ảnh hưởng cache kết quả preflight theo quy tắc browser; không thay Cache-Control response caching.

**14. Dùng @CrossOrigin thì có cần @EnableWebMvc không?**  
Không. Spring MVC hỗ trợ CORS, và Spring Boot auto-configuration xử lý phần MVC mặc định; chỉ cần cấu hình policy đúng.

**15. Tại sao OPTIONS có thể 403 khi GET vẫn chạy?**  
Do CORS policy/preflight methods/headers, Security filter order, proxy hoặc route mapping. Cần xem Network và request headers.

**16. Nếu API dùng @RestController cho GET /api/message, response 200 trong curl nhưng browser không đọc được, nguyên nhân chắc chắn do CORS?**  
Không chắc chắn. Có thể do network/TLS/mixed content/CSP hoặc CORS; phải xác định request đã đến server và đọc DevTools.

**17. SameSite cookie có giống same-origin không?**  
Không. SameSite dựa trên quan hệ site; SOP/CORS theo scheme–host–port origin.

**18. CORS preflight thất bại có nghĩa API không thể bị gọi bởi bot không?**  
Không. Bot/server-side HTTP client có thể gửi request trực tiếp; API phải tự xác thực/phân quyền và rate limit.

## 21. Tài liệu tham khảo

- [MDN – Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy): nguồn gốc, ranh giới quyền đọc, cách xác định origin và trường hợp opaque.
- [MDN – Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Origin): request Origin header và serialization.
- [MDN – Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): HTTP request/response headers, preflight, credentials và browser behavior.
- [MDN – CORS errors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors): danh sách lỗi thường gặp và cách chẩn đoán.
- [MDN – Access-Control-Allow-Origin](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin): wildcard, origin cụ thể, Vary và cache.
- [MDN – Access-Control-Allow-Credentials](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Credentials): credentialed fetch và quy tắc preflight.
- [Fetch Standard (WHATWG)](https://fetch.spec.whatwg.org/): định nghĩa normative cho CORS protocol, safelists, preflight và credentials.
- [Spring Framework – MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): `@CrossOrigin`, global `WebMvcConfigurer`, combination của local/global configuration.
- [Spring Framework – WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): annotation, reactive config và CorsWebFilter.
- [Spring Security – Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): tích hợp CorsFilter/CorsConfigurationSource và preflight trước auth.
- [Spring Security – Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): tích hợp policy trên reactive SecurityWebFilterChain.
- [Spring Boot 3.3 Reference](https://docs.spring.io/spring-boot/3.3/reference/): Spring MVC/WebFlux và web runtime configuration.
