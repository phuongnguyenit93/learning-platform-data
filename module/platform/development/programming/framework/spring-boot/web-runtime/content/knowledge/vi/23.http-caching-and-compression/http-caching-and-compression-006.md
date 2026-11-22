# Cấu hình server.compression.enabled và loại nội dung được nén

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Spring Boot, server có thể nén **HTTP response body** trước khi truyền đến trình duyệt hoặc API client. Với HTML, CSS, JavaScript, JSON hoặc XML có nhiều ký tự lặp, nén thường giúp giảm lượng dữ liệu truyền qua mạng. Tuy nhiên, nén cần thêm CPU và có thể không mang lại lợi ích với response nhỏ hoặc tệp vốn đã nén như JPEG, PNG, ZIP.

**Điểm khởi đầu:**

~~~properties
server.compression.enabled=true
~~~

Dòng cấu hình trên **bật khả năng nén response** của embedded web server, nhưng không đảm bảo mọi response sẽ mang header `Content-Encoding: gzip`. Việc có nén thực tế phụ thuộc thương lượng HTTP, `Content-Type`, kích thước response, loại response, khả năng của container và các tầng proxy/CDN.

Sau bài này, bạn có thể:

1. Giải thích cơ chế `Accept-Encoding` và `Content-Encoding`, phân biệt nén response với cache và nén request.
2. Sử dụng chính xác `server.compression.enabled`, `server.compression.mime-types` và `server.compression.min-response-size`.
3. Đọc danh sách tám MIME type nén mặc định của Spring Boot 3.3 và tùy chỉnh để thêm/bớt loại phù hợp.
4. Xây dựng ứng dụng Spring MVC chạy được bằng Java 17+ để thử JSON, văn bản lớn/nhỏ và binary.
5. Dùng `curl` kiểm tra header, lưu bytes gzip thực, giải nén và so sánh kích thước.
6. Xử lý các trường hợp không thấy gzip, `Content-Length` thay đổi, cache proxy, file đã nén, streaming/SSE và bảo mật.
7. Xác định ranh giới hỗ trợ giữa Tomcat, Jetty, Undertow, Reactor Netty và reverse proxy.

Ví dụ chính dùng **Spring Boot 3.3.5, Java 17+, Spring MVC + embedded Tomcat**. Tài liệu Spring Boot 3.3 cũng liệt kê hỗ trợ nén response đối với **Tomcat, Jetty, Undertow và Reactor Netty**; hành vi chi tiết ở từng container vẫn phải kiểm chứng khi triển khai.

## 2. Nén HTTP response diễn ra ở đâu?

Mô hình khái quát:

~~~text
Client
  |
  | GET /api/text/large
  | Accept-Encoding: gzip
  v
Spring Boot web server
  |
  | Controller / static resource handler
  | tạo response body và Content-Type
  v
HTTP response compression (nếu đủ điều kiện)
  |
  | Content-Encoding: gzip
  | Payload là bytes đã nén
  v
Proxy / CDN (nếu có)
  |
  v
Client nhận gzip -> giải nén -> xử lý nội dung
~~~

Trong ứng dụng có embedded server, Spring Boot chuyển cấu hình `server.compression.*` xuống cơ chế compression của container. Controller thông thường chỉ việc trả body; không cần tự nén bằng `GZIPOutputStream`, đặt `Content-Encoding` rồi gửi bytes gzip thủ công.

HTTP có ba lớp khái niệm dễ nhầm:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `Content-Type` | Kiểu dữ liệu **sau khi giải mã content coding**, giúp client biết đây là HTML, JSON, PNG... | `application/json` |
| `Accept-Encoding` (request) | Các content coding mà client chấp nhận và mức ưu tiên | `gzip, br;q=0.8` |
| `Content-Encoding` (response) | Body response đang được mã hóa/nén bằng cơ chế nào | `gzip` |
| `Transfer-Encoding` | Cơ chế truyền các thông điệp HTTP/1.1, ví dụ chunked | `chunked` |
| `Cache-Control` | Chính sách cache response | `public, max-age=3600` |

**Không nhầm `Content-Encoding` với `Content-Type`.** Một JSON được gzip vẫn có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

Body thực tế là bytes gzip; client giải nén rồi mới parse JSON.

`Transfer-Encoding: chunked` không phải thuật toán nén. Một response có thể vừa chunked vừa gzip hoặc chunked mà không nén. Trong HTTP/2, cách framing khác HTTP/1.1, nên không suy luận nén dựa vào việc có hay không có header `Transfer-Encoding`.

**Nén transport và cache là hai vấn đề độc lập.** Bật gzip không tự bật cache; đặt `Cache-Control` không tự bật gzip. Cùng một URL có thể có nhiều representation (identity/gzip) theo `Accept-Encoding`; cache dùng chung phải xử lý biến thể đúng cách.

## 3. server.compression.enabled: bật/tắt nén response

Spring Boot 3.3 có thuộc tính:

~~~properties
server.compression.enabled=false
~~~

**Giá trị mặc định là `false`**: nếu chỉ có Spring Boot mặc định và không có tầng khác xử lý, response thường được gửi ở dạng không nén.

Để bật:

~~~properties
server.compression.enabled=true
~~~

Tương đương trong `application.yml`:

~~~yaml
server:
  compression:
    enabled: true
~~~

Khi cấu hình là `true`, server **được phép** nén những response thỏa các điều kiện. Điều đó không có nghĩa “bắt mọi request phải nhận gzip”:

- Client có thể không yêu cầu một coding mà server hỗ trợ, hoặc từ chối coding đó.
- `Content-Type` của response có thể không nằm trong danh sách `mime-types`.
- Response có thể quá nhỏ so với `min-response-size`.
- Một số response không có body, đang streaming theo cơ chế riêng, đã được nén sẵn hoặc bị container loại khỏi diện áp dụng.
- Reverse proxy/CDN có thể thay đổi coding mà client cuối cùng nhìn thấy.

Thuộc tính này dùng cho **HTTP response** do web server phát ra. Nó **không** tự giải nén HTTP request có `Content-Encoding: gzip`, không thay cơ chế gzip của WebClient ở phía HTTP client và không tự đóng gói file `.zip`.

## 4. server.compression.mime-types: nén những loại nội dung nào?

Spring Boot 3.3 khai báo **tám MIME type mặc định** cho response compression:

~~~properties
text/html
text/xml
text/plain
text/css
text/javascript
application/javascript
application/json
application/xml
~~~

Đây là danh sách **giá trị mặc định của property** khi bạn bật nén mà không cấu hình riêng `mime-types`. Theo tài liệu Boot 3.3, chúng bao gồm:

| MIME type | Response điển hình | Vì sao thường nén tốt? |
| --- | --- | --- |
| `text/html` | Trang HTML tĩnh hoặc template engine render | Nhiều thẻ, thuộc tính và văn bản lặp |
| `text/xml` | XML được đánh dấu là text | Cấu trúc tag lặp |
| `text/plain` | Text, log hoặc báo cáo văn bản | Dữ liệu ký tự lặp |
| `text/css` | Stylesheet CSS | Tên thuộc tính, selector và khoảng trắng lặp |
| `text/javascript` | JavaScript theo MIME kiểu cũ | Mã dạng văn bản |
| `application/javascript` | JavaScript thông dụng | Mã nguồn JS dạng văn bản |
| `application/json` | API trả JSON | Key, dấu cấu trúc và text lặp |
| `application/xml` | API trả XML | Cấu trúc tag lặp |

Trong cùng một hệ thống, JSON lớn thường nén tốt, còn JSON chỉ vài chục byte có thể **không đáng nén**. Bật MIME type là một điều kiện cần, **chưa phải** kết luận sẽ có `Content-Encoding: gzip`.

### 4.1. Ghi đè danh sách mặc định

Ví dụ bạn chỉ muốn nén HTML và JSON:

~~~properties
server.compression.enabled=true
server.compression.mime-types=text/html,application/json
server.compression.min-response-size=1KB
~~~

Với cấu hình trên, response `text/plain` không còn thuộc danh sách nén, ngay cả khi dài 100 KB. Đây là lỗi thường gặp khi tùy chỉnh: `mime-types` trong Spring Boot 3.3 **thay thế danh sách mặc định**, không phải chỉ thêm vào cuối.

Nếu muốn thêm `image/svg+xml` mà vẫn giữ các loại mặc định, liệt kê đầy đủ:

~~~properties
server.compression.enabled=true
server.compression.mime-types=text/html,text/xml,text/plain,text/css,text/javascript,application/javascript,application/json,application/xml,image/svg+xml
~~~

**SVG** là dạng XML có nhiều text, thường có thể nén hiệu quả. Trong khi đó, đừng thêm mọi `image/*` chỉ vì “càng nhiều loại càng tốt”: ảnh JPEG, PNG, GIF, WebP, AVIF thường đã dùng định dạng nén; nén gzip thêm thường ít lợi ích và có thể tăng chi phí CPU.

Các loại như `application/problem+json`, `application/manifest+json`, `application/graphql-response+json`, `application/wasm` hoặc `font/woff2` có thể xuất hiện trong ứng dụng thật. **Đừng mặc định** rằng danh sách `application/json` tự bao phủ mọi MIME type có hậu tố `+json`. Hãy kiểm tra danh sách, cách container so khớp MIME và hành vi thực tế trước khi bổ sung.

### 4.2. Bảng chọn MIME theo đặc tính nội dung

| Loại nội dung | Quyết định thường phù hợp |
| --- | --- |
| HTML, CSS, JavaScript | Bật compression khi response đủ lớn |
| JSON, XML API | Thường có lợi nếu body lớn hoặc cấu trúc lặp |
| Text, CSV, SVG | Có thể có lợi; thêm MIME chính xác nếu chưa nằm trong danh sách |
| JPEG, PNG, WebP, AVIF | Thường không cần gzip thêm |
| ZIP, gzip, 7z, Brotli file | Đã nén; nén lại thường không đáng |
| MP4, WebM, MP3, AAC | Định dạng media đã nén, nên ưu tiên streaming/range phù hợp |
| PDF | Nhiều PDF đã nén luồng bên trong; cần đo thực tế |
| `application/octet-stream` | Nội dung không xác định; không bật vô điều kiện |
| `text/event-stream` (SSE) | Cẩn trọng: buffering/compression có thể tăng độ trễ event |

**MIME type do server gán mới là dữ liệu dùng trong phép kiểm tra.** URL đuôi `.json` không đủ để khẳng định response có `Content-Type: application/json`; controller có thể chủ động trả text, XML hoặc binary. Ngược lại, API không có đuôi file vẫn có thể trả JSON. Hãy kiểm tra header thực tế bằng `curl -i`.

### 4.3. Charset không phải loại MIME riêng

Một response có thể ghi:

~~~http
Content-Type: text/plain;charset=UTF-8
~~~

Về loại nội dung cơ bản, đó là `text/plain` cùng tham số charset. Trong cơ chế container thông dụng, so khớp compression dựa trên MIME type thích hợp, không yêu cầu bạn thêm chuỗi `text/plain;charset=UTF-8` như một mục riêng. Tuy nhiên, kiểm tra container/version khi sử dụng MIME custom có tham số bất thường.

## 5. server.compression.min-response-size: kích thước tối thiểu

Spring Boot 3.3 công bố giá trị mặc định:

~~~properties
server.compression.min-response-size=2KB
~~~

Ở định dạng DataSize của Boot, `2KB` tương đương **2048 byte**. Bạn có thể đặt ngưỡng khác:

~~~properties
server.compression.min-response-size=1KB
~~~

hoặc:

~~~properties
server.compression.min-response-size=4096B
~~~

Ý nghĩa: ngưỡng tối thiểu của response được phép cân nhắc để nén. Tài liệu property mô tả ngưỡng này theo **`Content-Length`**; tùy container, response có kích thước chưa biết/chunked có thể được xử lý khác response đã công bố `Content-Length`. Vì vậy, đừng áp công thức “body có hơn 2.048 ký tự Java thì chắc chắn gzip”.

**Đếm theo byte, không theo số ký tự hiển thị:**

- Chuỗi ASCII 1.024 ký tự thường tương ứng 1.024 byte ở UTF-8.
- Chữ tiếng Việt dùng UTF-8 có thể chiếm nhiều byte cho mỗi ký tự.
- JSON đã có thể chứa escape sequence; số byte khi serialize có thể khác độ dài `String.length()`.
- Nếu application không biết Content-Length trước khi stream, quyết định nén theo threshold có thể phụ thuộc đặc tính runtime.

Ví dụ với ngưỡng `1KB`, MIME `text/plain` được phép nén và client chấp nhận gzip:

| Đáp ứng | Kết luận dự kiến |
| --- | --- |
| Body 2 byte, `Content-Length: 2` | Thường không nén vì dưới ngưỡng |
| Body 700 byte, `Content-Length: 700` | Thường không nén |
| Body 5.000 byte, `Content-Length: 5000` | Có thể gzip nếu mọi điều kiện khác thỏa |
| Body 8.000 byte, MIME `image/png` không cấu hình | Không nén chỉ vì body lớn |
| Body lớn nhưng client không chấp nhận gzip | Không được tự chọn gzip không được client cho phép |
| Không biết trước `Content-Length` | Phải kiểm tra container; không suy luận từ Java String |

Ngưỡng rất thấp có thể tốn CPU và đôi khi làm payload **lớn hơn** vì header/trailer gzip. Ngưỡng rất cao có thể bỏ qua nhiều JSON/text response thực sự có lợi. Hãy quyết định theo dữ liệu đo.

## 6. Thương lượng nội dung: Accept-Encoding và Content-Encoding

**Client gửi** những cách mã hóa mà nó chấp nhận:

~~~http
GET /api/text/large HTTP/1.1
Host: localhost:8080
Accept-Encoding: gzip
~~~

**Server phản hồi**, nếu chọn gzip:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

Sau header là bytes gzip; body không còn là text UTF-8 có thể đọc trực tiếp cho đến khi giải nén. Những header minh họa trên là hình thức thường gặp; việc có chính xác `Vary`, `Content-Length`, `Transfer-Encoding` hay các header khác phụ thuộc server và proxy.

### 6.1. q-value và identity

Các giá trị thông dụng:

~~~http
Accept-Encoding: gzip
Accept-Encoding: gzip, br;q=0.8
Accept-Encoding: gzip;q=1.0, identity;q=0.5
Accept-Encoding: gzip;q=0
Accept-Encoding: identity
~~~

- `gzip`: client chấp nhận gzip.
- `br`: client hỗ trợ Brotli, **không** đảm bảo embedded server Spring Boot sẽ chọn Brotli khi bật property nén.
- `q` (0 đến 1): mức ưu tiên/chấp nhận của coding. `q=0` có nghĩa coding đó không được chấp nhận.
- `identity`: không dùng content coding để nén body. Dùng `Accept-Encoding: identity` khi muốn kiểm tra response không nén.
- Header không có `Accept-Encoding` không nên được hiểu là một phép đo gzip dứt khoát: tiêu chuẩn HTTP và cách implement thực tế có sắc thái khác nhau. Muốn thử rõ ràng hãy gửi `gzip` hoặc `identity`.

**Không nhầm với `Accept: application/json`.** Header `Accept` liên quan đến **media type** client muốn nhận; `Accept-Encoding` liên quan đến **content coding** trên bytes truyền đi. Một client có thể đồng thời gửi:

~~~http
Accept: application/json
Accept-Encoding: gzip
~~~

Cả hai header có vai trò khác nhau.

### 6.2. gzip, br và các server

Trong Spring Boot 3.3, chỉ dùng `server.compression.enabled=true` **không phải lời hứa rằng ứng dụng hỗ trợ mọi coding**. Gzip là cách phổ biến có thể kiểm thử với Tomcat. Brotli có thể được hỗ trợ bởi CDN/reverse proxy hoặc cơ chế tài nguyên đã nén sẵn, nhưng không được suy ra rằng nén Brotli động tự bật cho tất cả embedded server.

Hãy xem `Content-Encoding` ở **đầu ra cuối cùng** và kiểm tra tầng nào thực hiện phép nén. Một upstream trả identity có thể được CDN chuyển thành Brotli cho browser; một upstream trả gzip có thể được proxy giải nén rồi nén lại.

## 7. Ví dụ chạy được — Spring Boot 3.3.5 + Tomcat + Java 17

Lab sau minh họa bốn điều kiện:

1. `text/plain` lớn, đủ ngưỡng, client yêu cầu gzip.
2. `text/plain` nhỏ, cùng MIME nhưng dưới ngưỡng.
3. `application/json` lớn, thuộc danh sách MIME nén.
4. `application/octet-stream` lớn, **không** thuộc danh sách MIME nén của lab.

Không cần database, template engine hay thư viện nén ngoài Spring Boot.

### 7.1. Cấu trúc project

~~~text
compression-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/compression/
    │   ├── CompressionDemoApplication.java
    │   └── CompressionController.java
    └── resources/
        ├── application.properties
        └── static/
            └── index.html
~~~

### 7.2. Tệp pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>com.example</groupId>
    <artifactId>compression-demo</artifactId>
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

`spring-boot-starter-web` mặc định mang Spring MVC và embedded Tomcat trong phiên bản lab. Server compression do Boot/embedded container quản lý; không cần viết Servlet filter gzip thủ công.

### 7.3. Tệp application.properties

**`src/main/resources/application.properties`:**

~~~properties
server.port=8080

# Bật nén ở embedded web server
server.compression.enabled=true

# Chỉ nén text/plain, JSON và HTML trong lab này
server.compression.mime-types=text/plain,application/json,text/html

# 1 KB = 1024 byte
server.compression.min-response-size=1KB
~~~

Cấu hình này **khác danh sách mặc định tám MIME type**: chúng ta chủ động giới hạn còn ba loại để dễ thấy tác dụng của `mime-types`. Nếu muốn CSS/JS/XML cũng được nén trong ứng dụng thật, phải liệt kê thêm các MIME type đó.

### 7.4. Lớp khởi động

**`src/main/java/com/example/compression/CompressionDemoApplication.java`:**

~~~java
package com.example.compression;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CompressionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CompressionDemoApplication.class, args);
    }
}
~~~

### 7.5. Controller cho text, JSON và binary

**`src/main/java/com/example/compression/CompressionController.java`:**

~~~java
package com.example.compression;

import java.nio.charset.StandardCharsets;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class CompressionController {

    private static final String LARGE_TEXT =
            "Spring Boot response compression works for large text. "
                    .repeat(300);

    @GetMapping(value = "/text/large",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> largeText() {
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .contentLength(
                        LARGE_TEXT.getBytes(StandardCharsets.UTF_8).length)
                .body(LARGE_TEXT);
    }

    @GetMapping(value = "/text/small",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> smallText() {
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .contentLength(2)
                .body("OK");
    }

    @GetMapping(value = "/json/large",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> largeJson() {
        return Map.of(
                "message",
                "Spring Boot JSON compression example. ".repeat(300)
        );
    }

    @GetMapping(value = "/binary",
                produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<byte[]> binary() {
        // 8192 byte zero có thể nén rất tốt về mặt toán học,
        // nhưng MIME không nằm trong danh sách cấu hình.
        byte[] bytes = new byte[8192];
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(bytes.length)
                .body(bytes);
    }
}
~~~

**Giải thích code:**

- `GET /api/text/large` có body ASCII dài hơn ngưỡng `1KB`; controller đặt `Content-Length` theo số byte UTF-8 thực để giúp bài đo không phải đoán kích thước.
- `GET /api/text/small` trả body `OK` đúng **2 byte**, cố ý nhỏ hơn ngưỡng.
- `GET /api/json/large` trả một `Map`; Jackson (được Spring Boot Web quản lý) serialize thành JSON, `Content-Type: application/json` phù hợp với danh sách.
- `GET /api/binary` có body 8192 byte zero, dù rất dễ gzip về mặt kỹ thuật, nhưng `application/octet-stream` không được liệt kê nên **không đủ điều kiện nén** trong cấu hình lab.
- Không có code nào trực tiếp sử dụng `GZIPOutputStream` hoặc đặt `Content-Encoding`. Chúng ta muốn kiểm tra chính cơ chế response compression của server.
- Response JSON có thể không biết `Content-Length` từ đầu; nếu không có gzip trong một môi trường cụ thể, hãy xem header và cơ chế server. Endpoint text lớn có `Content-Length` rõ ràng là bài kiểm thử cốt lõi.

### 7.6. Một file HTML tĩnh

**`src/main/resources/static/index.html`:**

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>HTTP compression demo</title>
</head>
<body>
  <h1>Kiểm tra nén HTTP với Spring Boot</h1>
  <p>Đây là trang HTML tĩnh được Spring Boot phục vụ.</p>
  <p>
    <a href="/api/text/large">Văn bản lớn</a>
    <a href="/api/text/small">Văn bản nhỏ</a>
    <a href="/api/json/large">JSON lớn</a>
  </p>
</body>
</html>
~~~

HTML thuộc `text/html` nhưng khá nhỏ, nên với ngưỡng `1KB`, `GET /` có thể không được gzip. Sự khác nhau này có chủ ý: **cùng một MIME được cho phép nén không có nghĩa mọi trang HTML đều sẽ nén**.

### 7.7. Chạy application

Trong thư mục gốc `compression-demo`, cài JDK 17+ và Maven 3.x rồi chạy:

~~~bash
mvn spring-boot:run
~~~

Khi embedded Tomcat khởi động và lắng nghe port 8080, thử URL:

~~~text
http://localhost:8080/
http://localhost:8080/api/text/large
http://localhost:8080/api/text/small
http://localhost:8080/api/json/large
http://localhost:8080/api/binary
~~~

Không cần cấu hình reverse proxy để làm lab; hãy gọi trực tiếp `localhost:8080` để phân biệt đúng tầng nén của embedded server.

## 8. Kiểm thử gzip bằng curl đúng cách

Một số công cụ HTTP **tự giải nén** nội dung và khiến bạn nhìn body như plain text dù server đã trả gzip. Vì vậy phải kiểm tra **header và bytes** riêng.

### 8.1. Yêu cầu gzip và lưu response thô

Trong terminal thứ hai (Bash/zsh trên Linux/macOS):

~~~bash
curl --http1.1 -sS \
  -H "Accept-Encoding: gzip" \
  -D headers-gzip.txt \
  -o body-gzip.bin \
  http://localhost:8080/api/text/large
~~~

Lệnh này yêu cầu gzip **nhưng không dùng `--compressed`**, nên `curl` lưu **bytes của response body nhận được** vào `body-gzip.bin`.

Kiểm tra headers:

~~~bash
cat headers-gzip.txt
~~~

Với lab Tomcat cấu hình đúng và response thỏa điều kiện, kỳ vọng có:

~~~http
HTTP/1.1 200
Content-Type: text/plain
Content-Encoding: gzip
~~~

Dòng status/header còn tùy phiên bản container, và có thể xuất hiện `Vary`, `Transfer-Encoding` hoặc các header khác. **Đây là các header cần tìm, không phải lời cam kết stdout byte-for-byte.**

Giải nén bytes để kiểm chứng:

~~~bash
gzip -dc body-gzip.bin | head -c 160
~~~

Nội dung giải nén bắt đầu bằng câu:

~~~text
Spring Boot response compression works for large text.
~~~

Lưu ý chuỗi trong body lặp nhiều lần; `head -c 160` chỉ in một đoạn đầu. Không so dung lượng `body-gzip.bin` với số ký tự trong source; hãy so với số byte của response identity.

### 8.2. Yêu cầu không nén để làm đối chứng

~~~bash
curl --http1.1 -sS \
  -H "Accept-Encoding: identity" \
  -D headers-plain.txt \
  -o body-plain.txt \
  http://localhost:8080/api/text/large
~~~

Với `identity`, không kỳ vọng `Content-Encoding: gzip`. Đọc file `body-plain.txt` sẽ thấy text ASCII ban đầu.

So sánh kích thước file:

~~~bash
wc -c body-gzip.bin body-plain.txt
~~~

Nội dung nhiều câu lặp sẽ có cơ hội nén rất cao; file gzip thường nhỏ hơn file plain đáng kể. **Không gán trước một con số byte chính xác**, vì header gzip, container và phiên bản có thể khác.

### 8.3. Đọc body đã được curl tự giải nén

~~~bash
curl --http1.1 -i --compressed \
  http://localhost:8080/api/text/large
~~~

`--compressed` yêu cầu một encoding mà bản `curl` hỗ trợ và **tự giải nén response để hiển thị body**. Đây là cách dễ xem nội dung nhưng **không phù hợp để lưu và đếm bytes gzip trên dây**. Một số phiên bản `curl` có thể quảng cáo nhiều encoding như gzip/br/zstd nếu được build kèm thư viện; muốn thí nghiệm đúng `gzip` thì dùng header `Accept-Encoding: gzip` như ở mục 8.1.

Khi `--compressed` đã decode body, header in bởi `-i` vẫn có thể cho biết response ban đầu chứa `Content-Encoding: gzip`. Đừng nhìn body hiển thị thành text rồi kết luận server không nén.

### 8.4. Test 2 byte: cùng MIME, khác kích thước

~~~bash
curl --http1.1 -i -H "Accept-Encoding: gzip" \
  http://localhost:8080/api/text/small
~~~

Kỳ vọng body chính xác:

~~~text
OK
~~~

Với `Content-Length: 2` và ngưỡng `1KB`, Tomcat thông thường **không** gắn `Content-Encoding: gzip`. Nếu server vẫn có nén, cần kiểm tra cấu hình có bị override bởi proxy/filter hoặc một container khác không.

### 8.5. Test JSON: MIME trong danh sách

~~~bash
curl --http1.1 -i --compressed \
  http://localhost:8080/api/json/large
~~~

Kỳ vọng response có JSON chứa key `message` với chuỗi lặp dài; khi Web server biết đủ điều kiện compression, header `Content-Encoding: gzip` có thể xuất hiện. Tùy khả năng tính `Content-Length` trước khi ghi và cách runtime áp dụng threshold, kết quả cần kiểm tra thực tế.

### 8.6. Test binary: lớn nhưng MIME bị loại

~~~bash
curl --http1.1 -sS \
  -H "Accept-Encoding: gzip" \
  -D headers-binary.txt \
  -o body-binary.bin \
  http://localhost:8080/api/binary
~~~

Trong lab, `Content-Type` là `application/octet-stream` và không nằm trong danh sách `mime-types`, nên không kỳ vọng gzip. `body-binary.bin` có thể chứa byte 0 không hiển thị được trong terminal; **không dùng `curl -i` rồi đưa binary ra stdout** làm cách quan sát. Kiểm tra:

~~~bash
wc -c body-binary.bin
cat headers-binary.txt
~~~

Dữ liệu gốc có 8192 byte. Mục tiêu là chứng minh quyết định nén không chỉ dựa trên byte count.

### 8.7. Kiểm tra trên PowerShell

Windows PowerShell thường có alias `curl` riêng trong một số phiên bản. Dùng `curl.exe` thay vì `curl`:

~~~powershell
curl.exe --http1.1 -i --compressed http://localhost:8080/api/text/large
curl.exe --http1.1 -i -H "Accept-Encoding: identity" http://localhost:8080/api/text/small
curl.exe --http1.1 -sS -H "Accept-Encoding: gzip" -D headers-gzip.txt -o body-gzip.bin http://localhost:8080/api/text/large
~~~

Nếu cần kiểm tra binary gzip trên Windows, dùng thư viện/công cụ giải nén hỗ trợ định dạng gzip, hoặc dùng `curl.exe --compressed` để kiểm chứng body đã được giải nén mà không tự đọc bytes thô.

## 9. Bật/tắt nén mà không sửa code Java

Để so sánh cùng code, build JAR:

~~~bash
mvn clean package
~~~

Dừng instance chạy bằng Maven trước, rồi chạy bản bật nén:

~~~bash
java -jar target/compression-demo-0.0.1-SNAPSHOT.jar \
  --server.compression.enabled=true
~~~

Dừng process và chạy bản tắt nén:

~~~bash
java -jar target/compression-demo-0.0.1-SNAPSHOT.jar \
  --server.compression.enabled=false
~~~

Trong phiên bản Java/Spring Boot của lab, command-line argument `--server.compression.enabled=false` override property trong `application.properties`. Trên Windows, viết lệnh một dòng nếu shell không hỗ trợ backslash nối dòng.

Kiểm tra lại `/api/text/large` bằng `curl -H "Accept-Encoding: gzip"` trước/sau. Khi tắt nén **tại embedded server**, không kỳ vọng header `Content-Encoding: gzip` do embedded server tạo ra. Nếu vẫn thấy gzip ngoài production, rất có thể reverse proxy, CDN, filter hoặc ứng dụng phía trước đang nén; xác định từng tầng trước khi kết luận property không có hiệu lực.

**Không chạy hai process cùng port 8080**. Nếu cần chạy song song, đổi `--server.port=8081` cho một process và dùng URL tương ứng.

## 10. Header Vary và cache: tránh phục vụ nhầm biến thể

Response có nén và không nén của cùng URL **khác bytes**, dù nội dung logic sau giải nén giống nhau. Một cache dùng chung phải biết encoding client chấp nhận.

Header quan trọng:

~~~http
Vary: Accept-Encoding
~~~

Nó chỉ ra rằng representation phụ thuộc `Accept-Encoding`; cache phải xét header request này khi chọn phiên bản lưu. Nếu cache/CDN bỏ qua `Vary`, có thể gửi bytes gzip cho client không chấp nhận gzip hoặc gửi representation không tối ưu.

**Cần kiểm tra thực tế:** không giả định mọi embedded server/reverse proxy sẽ phát `Vary` giống nhau trong tất cả nhánh response. Khi đứng sau CDN, hãy kiểm tra `Vary`, cache key, quy tắc normalize Accept-Encoding và thử cả client gzip/identity trên **cùng URL**.

Ví dụ:

~~~text
GET /api/catalog
  Accept-Encoding: gzip
  -> Content-Encoding: gzip

GET /api/catalog
  Accept-Encoding: identity
  -> không Content-Encoding
~~~

Hai request có thể trả **nội dung JSON tương đương**, nhưng body bytes khác nhau.

Phân biệt:

- `Cache-Control`: quyết định có thể cache, ở đâu, thời gian bao lâu.
- `ETag`/`Last-Modified`: hỗ trợ conditional request và xác thực bản lưu.
- `Vary`: các header request phải được xét khi chọn phiên bản cache.
- `Content-Encoding`: coding trên bytes của response hiện tại.

**ETag có sắc thái:** một ETag mạnh gắn với một representation byte cụ thể phải nhất quán với representation được cache/serve. Nén động sau khi framework đã tạo ETag có thể gây vấn đề nếu ETag đại diện cho bytes trước nén mà được tái sử dụng như strong validator cho bytes đã nén. Hãy kiểm tra ETag/conditional request end-to-end, dùng weak validator hoặc cơ chế proxy/server phù hợp nếu cần, không tự giả định ETag tự động “đúng cho mọi encoding”.

Một response cá nhân hóa có thể cần `Cache-Control: private` hoặc `no-store` theo chính sách dữ liệu; **bật gzip không tự bảo vệ hoặc tự cache an toàn**.

## 11. Khác nhau giữa nén động và tệp đã nén sẵn

Có hai cách phổ biến để gửi asset nén:

**A. Dynamic compression từ web server:**

~~~text
static/app.js (bản gốc)
  -> embedded server đọc JS
  -> chọn gzip theo MIME/size/Accept-Encoding
  -> HTTP response Content-Encoding: gzip
~~~

Cấu hình trọng tâm:

~~~properties
server.compression.enabled=true
~~~

**B. Precompressed static resources:**

~~~text
static/app.js
static/app.js.gz
static/app.js.br
  -> static resource resolver có thể chọn file đã nén
  -> HTTP response với Content-Encoding tương ứng
~~~

Trong Spring MVC resource chain, Boot 3.3 có property riêng:

~~~properties
spring.web.resources.chain.compressed=true
~~~

Property này dùng cho việc tìm **resource đã được nén sẵn** như `.gz` hoặc `.br` trong resource chain khi được cấu hình đúng, và nó **khác** `server.compression.enabled`. Bật compressed resource chain **không tự tạo** `app.js.gz` hay `app.js.br`. Cần có bước build/deploy sinh file nén phù hợp và xác minh resource handling.

Điều cần tránh:

- Đừng nén động lại một payload đã mang `Content-Encoding: gzip`, tạo double compression.
- Đừng trả file `app.js.gz` như thể đó là JavaScript thường nếu thiếu `Content-Encoding` và `Content-Type` phù hợp.
- Đừng giả định Brotli dynamic được bật khi server.compression.enabled=true chỉ vì resource chain có thể chọn `.br` precompressed.
- CDN có thể tự thực hiện compression ngoài ứng dụng; cần phân định nơi nén chính để giảm CPU và tránh cấu hình mâu thuẫn.

## 12. Spring MVC và WebFlux: điểm chung, điểm khác

Spring Boot hỗ trợ server compression ở nhiều embedded server. Một số điểm thực tế:

| Stack / server | Cấu hình Spring Boot | Điều cần lưu ý |
| --- | --- | --- |
| Spring MVC + embedded Tomcat | `server.compression.*` | Container quyết định gzip theo MIME, size, Accept-Encoding và status |
| Spring MVC + Jetty | `server.compression.*` | Có implementation compression riêng; header/threshold có thể khác |
| Spring MVC + Undertow | `server.compression.*` | Cơ chế encoding được tích hợp với server |
| Spring WebFlux + Reactor Netty | `server.compression.*` | Compression ở Netty HTTP server, không phải Servlet filter |
| Spring WebFlux chạy trên Servlet runtime | `server.compression.*` nếu runtime được Boot hỗ trợ | Không suy luận tên stack từ package reactor; kiểm tra server đang chạy |

Bạn có thể chuyển dự án MVC lab sang WebFlux bằng starter tương ứng rồi viết handler phù hợp, nhưng **không** copy `HttpServletRequest`, Servlet filter hoặc chiến lược `Content-Length` của MVC sang code WebFlux mà cho rằng giống hệt. Trong WebFlux, response có thể được ghi theo luồng, khiến thời điểm biết kích thước khác nhau.

Bật nén **không biến luồng blocking thành non-blocking** và không tự hạn chế số lượng request song song. Với CPU cao và dữ liệu lớn, nén gzip có thể trở thành nút thắt; đo RPS, CPU, latency và số byte truyền.

## 13. Response nào cần đặc biệt cẩn trọng?

### 13.1. SSE và streaming

**Server-Sent Events (SSE)** thường có `Content-Type: text/event-stream` và được gửi theo nhiều event nhỏ. Nếu bạn đưa loại này vào danh sách nén, một số cơ chế buffer/flush có thể trì hoãn event, khiến client cảm giác “server không gửi dữ liệu”.

Nên ưu tiên **độ trễ event** và kiểm chứng flush trước khi bật compression cho SSE. Trong phần lớn ứng dụng, để `text/event-stream` ngoài danh sách MIME nén là lựa chọn thực tế. Tương tự, large-file streaming cần đánh giá backpressure/range/caching thay vì bật gzip đại trà.

### 13.2. Ảnh, video và file nén

Các loại `image/jpeg`, `image/png`, `video/mp4`, `application/zip` thường đã nén. Dùng thêm gzip có thể tốn CPU mà tiết kiệm không đáng kể. Với video và file lớn, còn phải xét `Range`/`Content-Range`, seekability và CDN. Đừng ép mọi binary response qua gzip.

### 13.3. Response không có body

Status `204 No Content`, `304 Not Modified` và nhiều response `HEAD` không có response body bình thường để nén. Không dùng việc thiếu `Content-Encoding` ở các response này làm bằng chứng tính năng nén bị tắt.

### 13.4. Response đã tự mã hóa

Nếu controller tự trả bytes nén kèm `Content-Encoding`, server/proxy phải biết không nén lặp. Không trộn “nén trong controller” và “nén của container” nếu chưa có thiết kế rõ. Khi làm file download, nên để client nhận được MIME/coding phù hợp thay vì tự gắn `Content-Encoding` cho mọi tệp zip.

### 13.5. HTTP qua HTTPS

Nén HTTP response vẫn có thể diễn ra **trước khi mã hóa TLS**. Nó không đồng nghĩa với cơ chế TLS-level compression (không nên bật). Tuy vậy, nén trang HTTPS có chứa secret cạnh dữ liệu người tấn công điều khiển có thể tạo rò rỉ theo kích thước, như nhóm tấn công **BREACH**. Xem mục bảo mật.

## 14. Vấn đề bảo mật: side channel khi nén nội dung nhạy cảm

Gzip tiết kiệm byte bằng cách khai thác chuỗi lặp. Kích thước response nén có thể tiết lộ thông tin **khi bí mật được phản chiếu trong cùng response với dữ liệu do kẻ tấn công kiểm soát** và kẻ đó đo được độ dài qua nhiều lần thử.

Ví dụ rủi ro:

~~~text
Response HTML/JSON động chứa:
  token bí mật / CSRF token / dữ liệu bí mật
  + một đoạn văn bản do attacker điều khiển
  -> cùng được gzip
  -> kích thước sau nén thay đổi theo chuỗi lặp
~~~

Các rủi ro như BREACH phụ thuộc mô hình tấn công, khả năng điều khiển đầu vào và quan sát độ dài. **Không kết luận rằng mọi response có gzip đều bị lộ secret**, nhưng cũng không nghĩ HTTPS tự loại bỏ kênh rò rỉ kích thước.

Biện pháp cần cân nhắc theo rủi ro:

1. Không đưa secret không cần thiết vào HTML/JSON; không để chúng nằm cạnh nội dung phản chiếu tùy ý nếu có thể tránh.
2. Hạn chế nén trên những endpoint thực sự nhạy cảm hoặc tách nội dung bí mật khỏi phần phản chiếu nếu thiết kế cho phép.
3. Dùng token phù hợp và các lớp bảo vệ CSRF, SameSite, authorization; chúng không thay thế hoàn toàn phân tích side channel.
4. Với response có secret, có thể áp cơ chế padding/randomization hoặc chính sách compression riêng khi threat model yêu cầu.
5. Khi dùng CDN/proxy, cần kiểm tra cả tầng ngoài chứ không chỉ property Spring Boot. Tắt gzip ở origin không đủ nếu CDN bật lại đối với response nhạy cảm.

**Không thể chọn loại MIME thay cho authorization.** Việc tắt nén `application/json` không giúp API riêng tư tự có xác thực và phân quyền. Compression là tối ưu truyền tải; bảo mật ứng dụng là vấn đề rộng hơn.

## 15. Tối ưu hiệu năng và cách đo

Để quyết định ngưỡng/nội dung nén, hãy đo **cùng workload** trước và sau khi bật, ở điểm quan sát phù hợp.

| Chỉ số | Cần đo | Diễn giải |
| --- | --- | --- |
| Response bytes trước/sau nén | Độ giảm bytes theo MIME và endpoint | Đừng chỉ dựa vào file có thể nén tốt trong lab |
| CPU và time spent compressing | Chi phí nén mỗi request | RPS lớn, payload nhiều có thể làm CPU tăng |
| Latency p50/p95/p99 | Độ trễ client trải nghiệm | Gzip không chắc cải thiện latency khi server CPU bị bão hòa |
| Throughput/RPS, tỷ lệ lỗi | Năng lực khi tải thực tế | Nén có thể giúp network nhưng làm hạn chế CPU |
| Cache hit ratio | Proxy/CDN/browser có cache không | Cache có thể giảm tải origin nhiều hơn gzip |
| Bandwidth và thời gian tải | Đặc biệt trên mạng di động/độ trễ cao | Nén text lớn thường có lợi |
| Phân phối kích thước body | Bao nhiêu response dưới/qua ngưỡng | Cơ sở chọn `min-response-size` |

### 15.1. Ví dụ tính tỷ lệ tiết kiệm

Giả sử đo được một response JSON identity 120.000 byte và gzip 18.000 byte:

~~~text
Bytes tiết kiệm = 120000 - 18000 = 102000 byte
Tỷ lệ tiết kiệm = 102000 / 120000 = 85%
~~~

Đây là **ví dụ số học**, không phải số đo của lab. Kết quả phụ thuộc dữ liệu. Nếu response chỉ 50 byte, gzip có thể khiến kích thước không giảm; vì thế mới cần ngưỡng và MIME filter.

### 15.2. Checklist thử tải

- Chạy cùng JDK, Spring Boot version, CPU, số instance, network và request distribution.
- So sánh nhiều lần: warm-up JVM/JIT, ghi p50/p95/p99, CPU, RPS, bytes transfer.
- Phân loại theo `Content-Type` và response size; đừng so sánh “toàn API” khi workload thay đổi.
- Thử mạng chậm/băng thông thấp vì lợi ích nén trên wire có thể khác môi trường local.
- Kiểm tra proxy/CDN có nén sẵn không; tránh đo hai cấu hình khác nhau ở hai tầng mà kết luận do server.compression.
- Với streaming và response có secret, ưu tiên ràng buộc về latency/an toàn thay vì tối đa hóa ratio.

**Nguyên tắc thực hành:** bắt đầu bằng bật gzip cho các MIME text phổ biến, giữ ngưỡng vừa phải, đo trước và sau. Chỉ tăng danh sách MIME hoặc hạ threshold khi dữ liệu cho thấy có lợi.

## 16. Lỗi phổ biến khi cấu hình

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Đã bật `server.compression.enabled=true` nhưng không thấy gzip | Client không yêu cầu, MIME bị loại, body dưới ngưỡng, server/proxy khác | Thử `Accept-Encoding: gzip`, kiểm tra `Content-Type` và body length |
| JSON nén nhưng CSS không nén | `mime-types` bị ghi đè chỉ còn `application/json` | Thêm `text/css` vào danh sách |
| File JPG 5MB không nén | JPEG không thuộc MIME mặc định và đã nén | Đây thường là hành vi hợp lý |
| File nhỏ không nén | `min-response-size` đặt cao | Đo bytes, không dùng ký tự làm ngưỡng |
| Browser hiển thị text, tưởng không gzip | Browser/`curl --compressed` đã giải nén | Xem `Content-Encoding` trong Network tab/raw headers |
| `curl -i` in ký tự rác | Đã yêu cầu gzip nhưng client không tự giải nén | Dùng `--compressed` hoặc lưu gzip bytes rồi giải nén |
| Có gzip dù server property tắt | CDN/proxy/filter khác đang nén | Gọi trực tiếp origin để phân biệt |
| Thêm `br` vào `Accept-Encoding` nhưng server chỉ gzip | Embedded server/stack không có Brotli dynamic | Kiểm tra coding hỗ trợ, precompressed resources và CDN |
| Client khác nhận nhầm gzip từ cache | Cache chưa quản lý `Vary: Accept-Encoding` đúng | Kiểm tra `Vary` và cache key |
| Header `Content-Length` mất/đổi khi gzip | Compression làm thay body bytes; có thể chuyển chunked | Không suy luận lỗi từ absence của Content-Length |
| SSE tới chậm sau khi bật nén | Buffer/flush do compression hoặc proxy | Tránh nén SSE và kiểm tra flush |
| CPU tăng, RPS giảm dù bytes nhỏ hơn | Compression CPU overhead quá lớn | Nâng threshold, giới hạn MIME, offload sang proxy |
| Chạy test local đúng, production không nén | Proxy chuyển coding, server khác hoặc cấu hình profile khác | So configs, `Accept-Encoding`, headers từng hop |
| Static JS không được nén | MIME trả về không phải loại đã liệt kê hoặc file dưới ngưỡng | Xem `Content-Type`, kích thước và đường dẫn |
| Thấy header gzip với response không đọc được | Client đang parse bytes nén như JSON chưa giải nén | Dùng HTTP client có decompression, không tự JSON.parse binary gzip |

### 16.1. Trình tự chẩn đoán đáng tin

1. **Xác định web server thực tế:** Tomcat/Jetty/Undertow/Reactor Netty và version Spring Boot. Kiểm tra startup logs, dependency và cấu hình deployment.
2. **Xác nhận property:** `enabled`, `mime-types`, `min-response-size` trong đúng profile/environment. CLI, environment variables và config server có thể override.
3. **Gửi request có chủ đích:** `Accept-Encoding: gzip` để thử nén và `Accept-Encoding: identity` để làm đối chứng, tới **cùng URL**.
4. **Đọc response headers:** `Content-Type`, `Content-Encoding`, `Vary`, `Content-Length`/`Transfer-Encoding` nếu có.
5. **Thử body dài đã biết:** endpoint `/api/text/large` từ lab có text và `Content-Length` rõ ràng, tránh lẫn threshold/chunking.
6. **Tách từng hop:** request tới origin trực tiếp, sau đó qua reverse proxy/CDN; xem tầng nào biến đổi response.
7. **Đo hiệu năng thực tế:** CPU, p99, bytes transferred và lỗi, không kết luận chỉ từ một response gzip thành công.

## 17. Tự kiểm tra và bài tập

**Câu 1.** Spring Boot 3.3 có bật nén mặc định không? Ngưỡng và danh sách MIME mặc định là gì?

**Câu 2.** Vì sao `GET /api/text/small` trong lab không gzip, dù `text/plain` đã được liệt kê?

**Câu 3.** Sau khi đặt `server.compression.mime-types=application/json`, một file CSS dài 200KB có còn nằm trong danh sách nén không?

**Câu 4.** Phân biệt `Accept: application/json` và `Accept-Encoding: gzip`.

**Câu 5.** Một response `application/octet-stream` 10MB và chứa byte lặp. Chỉ dựa trên kích thước lớn có đủ để server nén không?

**Câu 6.** Cách nào kiểm tra bytes gzip gốc bằng `curl` mà không để `curl` giải nén khi ghi file?

**Câu 7.** Vì sao `Vary: Accept-Encoding` quan trọng với reverse proxy/CDN cache?

**Câu 8.** Một HTTP response có `Content-Type: application/json`, `Content-Encoding: gzip` và `Transfer-Encoding: chunked`. Ba header nói về ba vấn đề gì?

**Câu 9.** Bật `spring.web.resources.chain.compressed=true` có giống `server.compression.enabled=true` không? Có tự sinh file `.br` hay `.gz` không?

**Câu 10.** Vì sao không nên bật gzip vô điều kiện cho SSE, PNG và các response chứa dữ liệu bí mật phản chiếu với input không tin cậy?

**Đáp án định hướng:**

1. Không; `enabled=false`, ngưỡng mặc định `2KB=2048 byte`, MIME mặc định gồm `text/html`, `text/xml`, `text/plain`, `text/css`, `text/javascript`, `application/javascript`, `application/json`, `application/xml`.
2. Body `OK` chỉ 2 byte, dưới `1KB`; điều kiện MIME không đủ để quyết định.
3. Không. `mime-types` khi cấu hình riêng sẽ thay danh sách mặc định; chỉ JSON còn được liệt kê.
4. `Accept` nói loại dữ liệu muốn nhận; `Accept-Encoding` nói thuật toán mã hóa/nén bytes có thể nhận.
5. Không. MIME `application/octet-stream` không có trong danh sách lab; còn cần chấp nhận encoding và điều kiện container.
6. Dùng `curl -H "Accept-Encoding: gzip" -D headers.txt -o body.gz URL`, **không** thêm `--compressed`; kiểm tra Content-Encoding rồi giải nén file.
7. Cache có thể lưu representation gzip/identity khác bytes cho cùng URL, cần phân biệt theo request header.
8. JSON là media type; gzip là content coding; chunked là cách truyền message trên HTTP/1.1.
9. Không. Resource chain chọn file đã nén sẵn khi được cấu hình và file tồn tại; server compression có thể nén response động. Không property nào tự sinh file nén trong quá trình build.
10. SSE cần flush với độ trễ thấp; PNG thường đã nén; dữ liệu bí mật trộn với input attacker có thể rò theo kích thước response nén.

## 18. Tóm tắt thực hành

- `server.compression.enabled=true` **bật khả năng nén HTTP response**, không bắt buộc mọi response đều gzip.
- `server.compression.mime-types` chọn **những Content-Type được phép nén**. Với Boot 3.3, mặc định có tám MIME text/JS/JSON/XML; tùy chỉnh property **thay** danh sách đó.
- `server.compression.min-response-size` kiểm soát **ngưỡng byte**, mặc định `2KB`; hành vi khi Content-Length chưa biết tùy container.
- `Accept-Encoding` ở request và `Content-Encoding` ở response là cách xác nhận thương lượng content coding; `Content-Type` vẫn là loại dữ liệu.
- Kiểm thử bằng `curl -H "Accept-Encoding: gzip"` + raw body file; dùng `curl --compressed` để xem body đã giải nén.
- Nén, HTTP cache, file precompressed và CDN là các lớp **khác nhau**. Kiểm tra `Vary`, proxy và coding thực tế.
- Tối ưu theo **bytes, CPU, latency, cache và an toàn**, không chỉ theo tỷ lệ nén. Tránh tự bật compression cho mọi binary, SSE hay response nhạy cảm mà chưa đánh giá rủi ro.

## 19. Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Embedded Web Servers, mục *Enable HTTP Response Compression* (các server hỗ trợ, 2048 byte và tám MIME mặc định): https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — Common Application Properties, `server.compression.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — `Compression` API (`getMimeTypes`, `getMinResponseSize`, `getEnabled`): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/server/Compression.html
- Spring Framework — Static Resources / encoded resource resolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html
- RFC 9110 — HTTP Semantics, Accept-Encoding, Content-Encoding và Vary: https://www.rfc-editor.org/rfc/rfc9110.html
- RFC 9111 — HTTP Caching (Vary và variants): https://www.rfc-editor.org/rfc/rfc9111.html
