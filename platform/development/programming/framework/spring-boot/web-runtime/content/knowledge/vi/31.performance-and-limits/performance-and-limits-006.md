# Giới hạn request body, multipart, header và dữ liệu codec trong Spring Boot

## 1. Mục tiêu và bốn loại giới hạn không được đánh đồng

Một endpoint Spring Boot có thể nhận JSON, form, tệp upload, dữ liệu nhị phân hoặc các request có rất nhiều HTTP headers. Nếu chỉ tăng heap hoặc đặt một property “max size” bất kỳ, ứng dụng vẫn có thể bị quá tải bởi request quá lớn, ngốn disk temp, header parsing, bộ đệm decoder hoặc quá nhiều kết nối đồng thời.

Bài học thuộc nhóm **Hiệu năng và giới hạn** của module **Spring Boot - web-runtime**. Ta phân biệt bốn phạm vi quan trọng:

1. **Request body**: toàn bộ dữ liệu HTTP request, có thể là JSON, text, binary hoặc multipart. Giới hạn tổng body ở gateway/container/ứng dụng không phải luôn là một property chung.
2. **Multipart upload**: tổng request, từng file part, form field, số parts, headers từng part, ngưỡng dùng memory và thư mục disk tạm. Servlet và WebFlux có cơ chế khác nhau.
3. **HTTP headers**: request line/URI và headers HTTP như Cookie/Authorization. Đây là giới hạn **trước khi vào controller**; khác headers của một multipart part.
4. **Codec buffering**: số byte một HTTP message reader/decoder phải gom trong memory để chuyển thành một object như JSON DTO/String/byte[]. Nó **không phải giới hạn tổng request body** trong mọi route, nhất là khi đọc streaming.

**Điều cần nhớ nhất:** `spring.codec.max-in-memory-size=256KB` không biến mọi request >256KB thành HTTP 413. Nó cấu hình buffer cho **auto-configured WebFlux server/WebClient codecs** khi codec phải aggregate/decode. `spring.servlet.multipart.max-file-size` áp dụng upload multipart Servlet, không phải mọi `@RequestBody` JSON. `server.tomcat.max-swallow-size` kiểm soát lượng body Tomcat bỏ qua khi request đã bị từ chối, không phải “max upload size”.

Bài dùng **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1.x** với hai dự án chạy độc lập: MVC/Tomcat và WebFlux/Reactor Netty. Các mức 64KiB, 128KiB… trong demo là **con số thực hành để dễ kiểm thử**, không phải giá trị production tối ưu cho mọi hệ thống. Với triển khai thật, cần hiệu chỉnh theo payload hợp đồng, số kết nối đồng thời, memory/disk quota và yêu cầu nghiệp vụ.

## 2. Giới hạn xảy ra ở nhiều tầng, không chỉ trong controller

```text
Browser / HTTP client
        │
        │ HTTP headers, Content-Length / Transfer-Encoding, body
        ▼
CDN / API gateway / reverse proxy
        │   - max body size, header limits
        │   - rate/connection/time limits
        │   - authentication, WAF, host validation
        ▼
Embedded server
  Tomcat / Jetty / Undertow / Reactor Netty
        │   - HTTP request line/header decoder limits
        │   - form parser / multipart limits / connection budget
        ▼
Spring Web MVC hoặc WebFlux
        │   - Servlet MultipartResolver hoặc Reactive PartReader
        │   - HttpMessageConverter / HttpMessageReader / Decoder
        │   - @RequestBody, @RequestPart, @RequestParam
        ▼
Controller / Application service
        │   - business max payload, count, schema, byte quota
        │   - file storage, antivirus, transaction, temp cleanup
        ▼
Database / Object storage / downstream
```

**Giới hạn hiệu lực thường là giới hạn nhỏ nhất trên đường request thực sự đi qua**, nhưng lỗi và status do **tầng đầu tiên phát hiện** quyết định. Ví dụ:
- Gateway từ chối body quá lớn → request **không tới Spring Boot**.
- Tomcat từ chối headers trước khi parse request → `@ControllerAdvice` không thể tạo JSON error của ứng dụng.
- Multipart parser từ chối file lớn → controller method có thể chưa được gọi.
- WebFlux decoder ném `DataBufferLimitException` → request đã tới web layer, nhưng error mapping có thể tùy cấu hình.
- Business service từ chối mảng JSON chứa 100.000 phần tử → decoder có thể đã đọc toàn bộ JSON trước khi service kiểm tra.

**Đừng chỉ dùng một limit.** Cần phối hợp edge/proxy, server parser, framework codecs, business validation, disk quotas, concurrent requests và timeouts. Bất kỳ tầng nào cũng có thể bị dùng nhiều tài nguyên trước khi tầng sau từ chối.

## 3. Bảng chọn property trong Spring Boot 3.3

| Phạm vi | Property / API | Stack | Thực sự giới hạn |
|---|---|---|---|
| HTTP request headers | `server.max-http-request-header-size` | Tomcat/Netty/embedded server | Header parsing, semantics khác theo server |
| HTTP initial line | `server.netty.max-initial-line-length` | Reactor Netty | Độ dài request line |
| Form body | `server.tomcat.max-http-form-post-size` | Tomcat | Nội dung POST form được Tomcat parse; **không là limit mọi JSON body** |
| Multipart file | `spring.servlet.multipart.max-file-size` | Spring MVC Servlet | Kích thước mỗi file upload |
| Multipart request | `spring.servlet.multipart.max-request-size` | Spring MVC Servlet | Kích thước tổng multipart request |
| Multipart disk threshold | `spring.servlet.multipart.file-size-threshold` | Spring MVC Servlet | Ngưỡng dùng disk thay cho memory |
| Multipart temp location | `spring.servlet.multipart.location` | Spring MVC Servlet | Nơi lưu trung gian |
| Multipart part count | `server.tomcat.max-part-count` | Tomcat trên Boot 3.3 | Số parts trong multipart/form-data |
| Multipart part header | `server.tomcat.max-part-header-size` | Tomcat trên Boot 3.3 | Header của từng multipart part |
| Swallow after rejection | `server.tomcat.max-swallow-size` | Tomcat | Lượng request body tiếp tục đọc/bỏ sau khi abort |
| Codec aggregation | `spring.codec.max-in-memory-size` | Auto-configured WebFlux/WebClient | Bytes cần buffer bởi decoder/message reader |
| Reactive multipart in-memory | `spring.webflux.multipart.max-in-memory-size` | WebFlux | Non-file part max; ngưỡng file part được spill to disk |
| Reactive multipart disk | `spring.webflux.multipart.max-disk-usage-per-part` | WebFlux | Disk tối đa cho mỗi file part đã spool |
| Reactive multipart count | `spring.webflux.multipart.max-parts` | WebFlux | Số parts trong một multipart request |
| Reactive per-part headers | `spring.webflux.multipart.max-headers-size` | WebFlux | Bộ nhớ cho header từng multipart part |
| Reactive temp directory | `spring.webflux.multipart.file-storage-directory` | WebFlux | Disk tạm của part reader |
| Raw streamed body | `DataBufferUtils.join(buffers, maxByteCount)` hoặc streaming quota | WebFlux | Giới hạn do code chủ động đặt; cần xử lý release |
| Raw Servlet input | Đọc `ServletInputStream` theo số byte, reject đúng lúc | MVC | Giới hạn route tùy biến, không thay container-wide limit |
| Proxy inbound body | `client_max_body_size` (NGINX) | Proxy | Tổng body vào proxy theo cấu hình |

Các property ứng dụng ở bảng dựa theo **Spring Boot 3.3 Common Application Properties**, không sao chép nguyên cách đặt của Boot 4.x. Một số mức mặc định có thể khác giữa server/version. **Điều kiện auto-configuration và loại server thực tế phải được xác nhận** trước khi suy luận một property sẽ áp dụng.

## 4. Các giá trị mặc định quan trọng, và điều chúng KHÔNG có nghĩa

Trong Spring Boot **3.3**, các mức được document đáng lưu ý:

| Property | Giá trị mặc định trong Boot 3.3 | Chú thích |
|---|---|---|
| `spring.servlet.multipart.max-file-size` | `1MB` | Giới hạn per file trong multipart Servlet |
| `spring.servlet.multipart.max-request-size` | `10MB` | Tổng multipart Servlet request |
| `spring.servlet.multipart.file-size-threshold` | `0B` | Thường đẩy file part xuống disk thay vì giữ memory |
| `server.max-http-request-header-size` | `8KB` | Tomcat tính tổng request line + headers; Netty áp theo từng header theo mô tả Boot |
| `server.tomcat.max-http-form-post-size` | `2MB` | Form parsing POST ở Tomcat |
| `server.tomcat.max-swallow-size` | `2MB` | Swallow body sau abort; không phải max allowed body |
| `server.tomcat.max-part-count` | `10` | Số multipart parts |
| `server.tomcat.max-part-header-size` | `512B` | Header từng part |
| `spring.webflux.multipart.max-in-memory-size` | `256KB` | Non-file part limit / file spool threshold |
| `spring.webflux.multipart.max-headers-size` | `10KB` | Header của từng reactive part |
| `spring.webflux.multipart.max-disk-usage-per-part` | `-1B` | **Không có giới hạn disk per part theo mặc định** |
| `spring.webflux.multipart.max-parts` | `-1` | **Không giới hạn số parts theo mặc định** |
| `spring.codec.max-in-memory-size` | Không set ở Boot | Đa số codecs có default **256KiB** riêng |
| `server.netty.max-initial-line-length` | `4KB` | Riêng request initial line |

**Lưu ý đơn vị:** Spring Boot `DataSize` cho phép `KB`, `MB`, `GB` nhưng cần chú ý byte units khi so sánh. Trong bài ta dùng `64KB`, `128KB` cho properties theo Boot, còn khi kiểm tra code đọc body dùng `64 * 1024` byte. Đừng so sánh một response JSON string length (UTF-16 code units) với content length (bytes) mà không chuyển mã UTF-8.

**Đừng gán mặc định trên một server khác:** giới hạn Tomcat không tự áp dụng cho Reactor Netty, Jetty hay Undertow. Ngược lại, `spring.webflux.multipart.*` không có nghĩa Tomcat MultipartConfigElement đã được thay đổi.

## 5. Phân biệt kích thước “toàn body” với kích thước “một phần”

Một HTTP request có thể chứa các dạng body khác nhau:

```http
POST /api/objects HTTP/1.1
Content-Type: application/json

{"name":"abc","description":"..."}
```

```http
POST /api/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=abc123

--abc123
Content-Disposition: form-data; name="file"; filename="photo.jpg"
Content-Type: image/jpeg

<binary bytes>
--abc123--
```

Với multipart:
- **Total request size** gồm boundaries, part headers, các fields, các files và framing nội dung.
- **File size** là bytes của riêng file payload.
- **Per-part header size** tính headers như `Content-Disposition`, `Content-Type` bên trong một part, **khác HTTP request headers**.
- **Max parts** đếm số lượng phần tử trong request, không đo tổng dung lượng.
- **In-memory threshold** xác định thời điểm đẩy file xuống disk, không đồng nghĩa từ chối file lớn.
- **Disk quota** giới hạn dung lượng spool; nếu không cấu hình, một luồng uploads lớn có thể làm đầy disk tạm ngay cả khi heap còn trống.

Ví dụ: `max-file-size=64KB` và `max-request-size=128KB` không đồng nghĩa “2 files x 64KB luôn được phép”, vì multipart boundaries và part headers đẩy tổng request vượt 128KB. Nếu cần chắc chắn hai files, đặt tổng budget có khoảng trống phù hợp và kiểm thử với client thực tế.

**Form `application/x-www-form-urlencoded` không phải multipart**. Tomcat `server.tomcat.max-http-form-post-size` áp cho giới hạn parse form POST theo contract của container, không phải một chặn tổng JSON/XML/octet-stream đồng nhất.

## 6. HTTP request headers: giới hạn parser diễn ra trước controller

Một request có thể mang:
- `Authorization: Bearer ...` hoặc cookie lớn.
- `Cookie: ...` gồm nhiều giá trị đăng nhập/tracking.
- `X-Forwarded-*` từ reverse proxy.
- Custom tracing/baggage headers.
- Một URL/query string rất dài.
- Header tên/giá trị lặp lại hoặc framing bất thường.

Spring Boot 3.3 property:

```properties
server.max-http-request-header-size=8KB
```

**Semantics theo server không giống nhau:** tài liệu Boot nói Tomcat áp giới hạn lên **tổng request line + tất cả tên/giá trị headers**, trong khi Netty áp giới hạn riêng cho từng header. Do đó cùng `8KB` không chứng minh hai server sẽ chấp nhận hay từ chối cùng một tập headers nhiều dòng. Khi có nhiều cookies/headers, phải kiểm thử chính xác implementation/version.

Trong Netty còn có:

```properties
server.netty.max-initial-line-length=4KB
```

Property này dành cho request initial line, **không phải payload body**. HTTP/2/HTTP/3 có cách biểu diễn headers khác HTTP/1.1, nên behavior của parser và hạ tầng trung gian cũng có thể khác.

**Khi vượt giới hạn header:** embedded server có thể trả `400 Bad Request`, `431 Request Header Fields Too Large`, đóng kết nối hoặc trả behavior khác tùy server/parser. Đừng cam kết một `@ExceptionHandler` Java sẽ luôn xử lý được lỗi: request có thể bị từ chối **trước khi DispatcherServlet/DispatcherHandler nhận nó**.

**Không tăng `server.max-http-request-header-size` vô giới hạn** chỉ vì JWT/cookie đang phình. Kiểm tra có đang gửi token/claim không cần thiết, headers duplicated, proxy append nhiều lần hay quá nhiều cookies không. Một header limit lớn nhân với số concurrent connections có thể tăng áp lực memory/parser.

### 6.1. Headers gốc và multipart part headers khác nhau

```text
HTTP request headers:
  Host, Cookie, Authorization, Content-Type, ...
  giới hạn: server.max-http-request-header-size

Bên trong multipart body:
  --boundary
  Content-Disposition: form-data; name="file"; filename=...
  Content-Type: application/octet-stream
  [file payload]
  giới hạn part-header: server.tomcat.max-part-header-size
                       hoặc spring.webflux.multipart.max-headers-size
```

Với multipart malformed, filename hoặc các part headers quá dài có thể bị từ chối dù tổng HTTP headers không lớn. **Đừng nhầm xử lý lỗi ở hai tầng.**

## 7. Spring MVC/Tomcat: multipart và parser giới hạn gì?

Khi dùng `spring-boot-starter-web`, Spring Boot thường chọn MVC + embedded Tomcat. `spring.servlet.multipart.*` cấu hình Servlet `MultipartConfigElement` và resolver tương ứng; API controller phổ biến là `MultipartFile` hoặc Servlet `Part`.

Cấu hình ví dụ:

```properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB
spring.servlet.multipart.file-size-threshold=0B

server.max-http-request-header-size=8KB
server.tomcat.max-part-count=8
server.tomcat.max-part-header-size=1KB
server.tomcat.max-http-form-post-size=256KB
server.tomcat.max-swallow-size=2MB
```

**Điều từng property làm:**
- `max-file-size` từ chối file multipart vượt limit.
- `max-request-size` từ chối tổng multipart upload vượt limit.
- `file-size-threshold` điều chỉnh dùng disk tạm khi parse file.
- `max-part-count` hạn chế request có quá nhiều parts.
- `max-part-header-size` tránh part headers quá lớn.
- `max-http-form-post-size` không kiểm soát mọi JSON/byte stream.
- `max-swallow-size` chỉ kiểm soát lượng body Tomcat còn chấp nhận **nuốt/bỏ** sau khi request bị hủy/reject để xử lý kết nối/response; không làm file hợp lệ được lớn hơn.
- `server.max-http-request-header-size` giới hạn HTTP request headers trước khi controller vào chạy.

Một upload quá cỡ có thể thành `MaxUploadSizeExceededException` và được controller advice map thành HTTP **413**, **nhưng không bảo đảm mọi trường hợp đều qua advice**: container, proxy hoặc connection handling có thể từ chối trước đó. Khi client đang streaming body dài, server từ chối sớm mà không swallow hết có thể khiến client thấy connection reset thay vì JSON error body.

### 7.1. Không áp dụng cho JSON một cách tự động

Ví dụ:

```java
@PostMapping("/json")
Map<String, String> json(@RequestBody InputDto input) {
    return Map.of("received", input.message());
}
```

Nếu chỉ đặt `spring.servlet.multipart.max-file-size=64KB`, request JSON lớn vẫn **không bị property multipart này bảo vệ**. HTTP message converter có thể đã deserialize nội dung vào object trước khi vào method. Cần edge/gateway body cap, route-specific streaming quota hoặc cơ chế xử lý body đầu vào phù hợp **trước khi aggregate**.

Không cố đọc `HttpServletRequest.getInputStream()` trong một servlet filter rồi “đọc lại” `@RequestBody` mà không có wrapper đúng: bạn sẽ làm cạn stream, gây lỗi decode hoặc tạo bộ đệm vô hạn. Với một endpoint binary đơn giản, đọc có giới hạn ngay trong controller là cách minh họa rõ ràng.

## 8. Dự án chạy được A: Spring MVC với giới hạn multipart và raw body

Ví dụ Java 17 / Boot 3.3.13 có:
- `POST /api/raw`: đọc `application/octet-stream` trực tiếp từ input stream, **giới hạn 64KiB theo số byte thực đọc**, không dựa vào `Content-Length`.
- `POST /api/upload`: nhận một `MultipartFile` do Servlet parser áp giới hạn 64KB/file, 128KB/request.
- `GET /api/ping`: endpoint nhỏ để test header parser.
- `@RestControllerAdvice`: trả `ProblemDetail` HTTP 413 cho lỗi body do code phát hiện và các `MaxUploadSizeExceededException` đi qua MVC.

### 8.1. Cấu trúc project

```text
mvc-limit-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/mvclimits/MvcLimitApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/mvclimits/MvcLimitIntegrationTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8080

spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=64KB
spring.servlet.multipart.max-request-size=128KB
spring.servlet.multipart.file-size-threshold=0B

server.max-http-request-header-size=8KB
server.tomcat.max-part-count=8
server.tomcat.max-part-header-size=1KB

# Form parsing, KHÔNG là JSON body cap:
server.tomcat.max-http-form-post-size=256KB

# Swallow sau khi request bị reject; KHÔNG là max accepted body:
server.tomcat.max-swallow-size=2MB
```

**`src/main/java/com/example/mvclimits/MvcLimitApplication.java`:**

```java
package com.example.mvclimits;

import java.io.IOException;
import java.io.InputStream;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.MultipartFile;

@SpringBootApplication
public class MvcLimitApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcLimitApplication.class, args);
    }
}

@RestController
class MvcLimitController {

    private static final long MAX_RAW_BYTES = 64L * 1024;

    @GetMapping("/api/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @PostMapping(
            path = "/api/raw",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    Map<String, Long> raw(HttpServletRequest request)
            throws IOException {

        // Đọc từng chunk 8 KiB, không aggregate toàn body.
        byte[] chunk = new byte[8192];
        long total = 0;

        try (InputStream input = request.getInputStream()) {
            int n;
            while ((n = input.read(chunk)) != -1) {
                if (total > MAX_RAW_BYTES - n) {
                    throw new RawBodyTooLargeException(
                            "Raw body exceeds 64 KiB");
                }
                total += n;
            }
        }

        return Map.of("bytes", total);
    }

    @PostMapping(
            path = "/api/upload",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Map<String, Long> upload(
            @RequestParam("file") MultipartFile file) {

        // Demo chỉ kiểm tra kích thước, không lưu file.
        return Map.of("bytes", file.getSize());
    }
}

@RestControllerAdvice
class MvcLimitAdvice {

    @ExceptionHandler(RawBodyTooLargeException.class)
    ResponseEntity<ProblemDetail> rawTooLarge(
            RawBodyTooLargeException exception) {
        return response413("Raw body exceeds 64 KiB");
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ProblemDetail> multipartTooLarge(
            MaxUploadSizeExceededException exception) {
        return response413("Multipart upload exceeds configured limits");
    }

    private ResponseEntity<ProblemDetail> response413(String detail) {
        ProblemDetail problem = ProblemDetail.forStatus(413);
        problem.setTitle("Payload Too Large");
        problem.setDetail(detail);
        return ResponseEntity.status(413).body(problem);
    }
}

class RawBodyTooLargeException extends RuntimeException {
    RawBodyTooLargeException(String message) {
        super(message);
    }
}
```

**Lý do code hợp lệ và phù hợp phạm vi:**
- Một top-level `public class` trùng tên file, hai class và một exception package-private cùng package.
- Không gọi `request.getReader()` rồi lại gọi `getInputStream()`; request raw chỉ có một consumer.
- `read(chunk)` dùng đúng số byte, không dùng `String.length()`. Với `Content-Length` sai/không có (ví dụ chunked request), code vẫn dừng khi vượt 64KiB.
- Phép kiểm `total > MAX_RAW_BYTES - n` tránh cộng tràn số và phát hiện bytes vượt giới hạn trước khi tiếp tục sử dụng.
- Bộ nhớ cho raw đọc là chunk 8KiB, không tạo `byte[]` cỡ bằng toàn file. Tuy nhiên đây **không phải generic limit cho mọi @RequestBody**; nó chỉ bảo vệ route `/api/raw` được viết theo streaming.
- `MultipartFile` do Servlet multipart parser quản lý; `getSize()` lấy metadata, không gọi `getBytes()` để copy toàn bộ upload vào heap.
- `MaxUploadSizeExceededException` thường có thể được handler map thành 413, nhưng không nên kỳ vọng advice xử lý một request bị proxy/container loại trước khi vào Spring MVC.
- File parser temp thuộc framework/container; nếu ứng dụng copy sang staging file thật, phải bảo đảm cleanup on complete/error/cancel theo lifecycle riêng.

### 8.2. Lệnh chạy và curl

Có JDK 17+, Gradle tương thích Spring Boot 3.3:

```bash
gradle bootRun
```

Nếu đã có wrapper: `./gradlew bootRun` (Linux/macOS) hoặc `.\gradlew.bat bootRun` (PowerShell).

Tạo file 32KiB và 80KiB ở môi trường Linux/macOS:

```bash
head -c 32768 /dev/zero > small.bin
head -c 81920 /dev/zero > large.bin
```

**Gửi raw nhỏ, body hợp lệ:**

```bash
curl -i \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @small.bin \
  http://localhost:8080/api/raw
```

Response **mong đợi**: HTTP 200, JSON:

```json
{"bytes":32768}
```

**Gửi raw lớn, route-specific limit:**

```bash
curl -i \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @large.bin \
  http://localhost:8080/api/raw
```

Mục tiêu là HTTP **413** với `ProblemDetail`; nếu proxy/container đóng connection khi app ngừng đọc body, một client có thể thấy hiện tượng connection reset tùy cách gửi. Trên một local test có request body được gửi đầy đủ, error mapping dự kiến sẽ trả 413.

**Gửi file multipart nhỏ:**

```bash
curl -i -F 'file=@small.bin' \
  http://localhost:8080/api/upload
```

Dự kiến HTTP 200, JSON `{"bytes":32768}`. Cũng có thể tạo file 80KiB và gửi bằng `-F`; Servlet multipart giới hạn **64KB/file** sẽ từ chối dù tổng request chưa tới 128KB.

**Không dùng `-d @small.bin` để kiểm tra raw binary** nếu cần giữ bytes chính xác; `--data-binary` đúng hơn. Không truyền secrets hoặc file nhạy cảm vào dịch vụ demo.

## 9. MVC integration tests qua HTTP thật

Test giúp phân biệt hai giới hạn: **raw body quota do code đếm** và **multipart quota do Servlet parser kiểm tra**. Test dùng `java.net.http.HttpClient`, không cần thư viện MockWebServer. Với Multipart, dùng HTTP wire-format thật thay vì `MockMultipartFile`; `MockMvc` thuần không chứng minh container đã enforce limit.

**`src/test/java/com/example/mvclimits/MvcLimitIntegrationTest.java`:**

```java
package com.example.mvclimits;

import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class MvcLimitIntegrationTest {

    @LocalServerPort
    int port;

    HttpClient client = HttpClient.newHttpClient();

    String uri(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    HttpResponse<String> postRaw(byte[] body) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(uri("/api/raw")))
                .header("Content-Type", "application/octet-stream")
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    byte[] multipartBody(int fileSize) throws Exception {
        String boundary = "DemoBoundary123";
        String prefix = "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"file\"; "
                + "filename=\"file.bin\"\r\n"
                + "Content-Type: application/octet-stream\r\n\r\n";
        String suffix = "\r\n--" + boundary + "--\r\n";

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        out.write(prefix.getBytes(StandardCharsets.UTF_8));

        byte[] file = new byte[fileSize];
        Arrays.fill(file, (byte) 'a');
        out.write(file);
        out.write(suffix.getBytes(StandardCharsets.UTF_8));
        return out.toByteArray();
    }

    @Test
    void rawWithinLimit() throws Exception {
        HttpResponse<String> response = postRaw(new byte[32768]);
        assertEquals(200, response.statusCode());
        assertEquals("{\"bytes\":32768}", response.body());
    }

    @Test
    void rawOverLimit() throws Exception {
        HttpResponse<String> response = postRaw(new byte[81920]);
        assertEquals(413, response.statusCode());
    }

    @Test
    void multipartSmallFileIsAccepted() throws Exception {
        String boundary = "DemoBoundary123";
        byte[] body = multipartBody(4096);

        HttpRequest request = HttpRequest.newBuilder(
                URI.create(uri("/api/upload")))
                .header("Content-Type",
                        "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals("{\"bytes\":4096}", response.body());
    }
}
```

Chạy:

```bash
gradle test
```

**Kỳ vọng:** ba tests pass trong môi trường Boot/Tomcat đúng cấu hình. Đây là **kỳ vọng từ mã và contract, không phải kết quả Gradle đã chạy**. JSON body ở đây do Jackson serialize `Map.of("bytes", value)` một field nên dễ assert; nếu thêm fields/handlers có thể thay output và cần test schema thay vì bytes.

Test multipart lớn cần riêng:
- Khi gửi file >64KB, `MaxUploadSizeExceededException` có thể được Spring MVC map 413.
- Nhưng HTTP transport/proxy/Tomcat có thể từ chối sớm khi client còn upload, làm client thấy reset/400/413 tùy đường đi. Đừng viết test production chỉ chấp nhận một error body cho mọi server.
- Thực tế nên assert “file không được chấp nhận/không được lưu” và quan sát status/transport ở integration environment cụ thể.

## 10. Codec buffering trong WebFlux: có gì xảy ra khi đọc JSON?

Trong Spring WebFlux, HTTP input đi qua các `HttpMessageReader`/`Decoder` của `ServerCodecConfigurer`; nếu codec phải gom dữ liệu để tạo object, nó cần buffer. Spring Boot 3.3 có:

```properties
spring.codec.max-in-memory-size=32KB
```

Tài liệu Boot nhấn mạnh setting này áp cho **auto-configured WebFlux server và WebClient instances**. Nếu không set, nhiều codecs giới hạn **256KiB** theo default riêng.

**Nó không phải “toàn HTTP body tối đa 32KB”**. Ví dụ:

- `@RequestBody Mono<MyDto>`: một JSON object lớn có thể cần aggregate trong decoder và vượt cap → thường gặp `DataBufferLimitException` hoặc lỗi decode liên quan.
- `@RequestBody Mono<String>`: phải gom string → có memory cap.
- `@RequestBody Mono<byte[]>`: decoder có thể gom byte array → cần cap.
- Streaming `Flux<MyDto>` từ NDJSON: dữ liệu được decode theo từng object; cap có thể áp **mỗi object**, không phải tổng vô hạn stream.
- `@RequestBody Flux<DataBuffer>`: application tự nhận các chunks, **không bắt buộc aggregate**, vì vậy một request tổng 100MB có thể vẫn đi qua nếu không đặt tổng byte quota riêng.
- `FilePart` upload WebFlux: dùng multipart reader settings riêng, có thể spool file xuống disk; không suy từ codec cap rằng file lớn hơn 32KB bị chặn.

**Lỗi thường gặp:** nhận `DataBufferLimitException: Exceeded limit on max bytes to buffer` rồi tăng `spring.codec.max-in-memory-size=-1` cho cả app. `-1` có thể bỏ cap ở decoder hỗ trợ nó, làm request ác ý khiến heap tăng hoặc OOM. Hãy đo payload hợp lệ, tăng có kiểm soát ở đúng consumer/codec; tốt hơn là streaming khi dữ liệu thực sự lớn.

### 10.1. Không nhầm WebClient inbound decoder với WebFlux server

Cùng Boot property có thể ảnh hưởng cả WebFlux server và **WebClient builders do Boot tự cấu hình**, nên nâng `spring.codec.max-in-memory-size` toàn app cũng có thể làm HTTP **responses** từ downstream được buffer nhiều hơn. Nếu một downstream chỉ cần streaming download 1GB, dùng `Flux<DataBuffer>`/`DataBufferUtils.write` hoặc file/resource streaming thay vì `bodyToMono(byte[].class)`.

Với một WebClient cụ thể, có thể giới hạn riêng qua `WebClient.Builder.codecs(...)`, nhưng **đừng thay mọi default codecs một cách không kiểm soát**, đặc biệt khi Boot đã cung cấp JSON codecs, observation và SSL connector. Chỉ điều chỉnh đúng client cần.

## 11. WebFlux multipart: memory threshold, disk usage và số parts

Spring Boot 3.3 cung cấp các property riêng cho **reactive multipart reader**:

```properties
spring.webflux.multipart.max-in-memory-size=16KB
spring.webflux.multipart.max-disk-usage-per-part=128KB
spring.webflux.multipart.max-headers-size=2KB
spring.webflux.multipart.max-parts=3
```

**Giải thích chính xác:**
- `max-in-memory-size`: với **non-file parts** (form fields) vượt giới hạn → `DataBufferLimitException`; với **file parts**, kích thước này là ngưỡng **chuyển nội dung xuống disk**.
- `max-disk-usage-per-part`: trần disk **per file part** do reader spool; với giá trị mặc định `-1` không có limit per part. Đây không phải tổng disk quota cho mọi người dùng.
- `max-headers-size`: bộ nhớ cho **headers riêng của mỗi multipart part**, không phải HTTP request headers bên ngoài.
- `max-parts`: số lượng parts được phép, rất quan trọng để tránh hàng nghìn fields/file parts nhỏ.
- `file-storage-directory`: nơi framework dùng làm temp storage cho parts vượt memory threshold; production cần disk quota và cleanup policies.
- **PartEvent streaming** là một đường xử lý khác: khi nhận `Flux<PartEvent>`, bạn xử lý nội dung trực tiếp trong một event stream thay vì spooling giống đường `FilePart` non-streaming. Không giả định các disk/threshhold limits của non-streaming parser tự bảo vệ mọi PartEvent streaming code; phải tự đặt byte/part/headers/total quotas đúng pipeline.

Nếu file 100KB, threshold 16KB, disk per part 128KB:
- 100KB file **không bị chặn bởi threshold 16KB**; reader có thể spool tới disk.
- Nếu file vượt 128KB disk quota, parser có thể từ chối.
- Nếu có 10 file parts nhỏ, `max-parts=3` có thể từ chối.
- Nếu một form field text vượt 16KB, decoder/reader có thể từ chối **dù không có file**.

**Không coi `FilePart.transferTo(path)` là cách bỏ qua multipart parser limits.** File đã đi qua reader trước khi controller nhận `FilePart`. Khi cần stream dữ liệu rất lớn end-to-end, cân nhắc `Flux<PartEvent>` hoặc raw chunks với explicit counters, nhưng phải hiểu DataBuffer ownership/cancellation.

## 12. Dự án chạy được B: Spring WebFlux, codec và raw body quota

Project WebFlux độc lập dùng Java 17+, Boot 3.3.13, Reactor Netty. Các endpoint:
- `POST /api/json`: đọc JSON object qua decoder, minh họa `spring.codec.max-in-memory-size=32KB`.
- `POST /api/raw`: nhận `Flux<DataBuffer>`, ứng dụng tự aggregate có giới hạn **64KiB** bằng `DataBufferUtils.join(body, maxByteCount)` và trả **413** khi quá quota.
- `POST /api/upload`: nhận `FilePart`, chuyển vào file staging tạm, đo bytes, dọn staging trên success/error/cancel với `Mono.usingWhen`. Multipart reader vẫn áp `spring.webflux.multipart.*`.
- `GET /api/ping`: kiểm thử HTTP header parser.

### 12.1. Cấu trúc

```text
webflux-limit-demo/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactivelimits/ReactiveLimitApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/reactivelimits/ReactiveLimitIntegrationTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.properties`:**

```properties
server.port=8081

# HTTP headers: không phải body limit.
server.max-http-request-header-size=8KB
server.netty.max-initial-line-length=4KB

# Codec aggregate limit: không phải total body limit.
spring.codec.max-in-memory-size=32KB

# Reactive multipart parser:
spring.webflux.multipart.max-in-memory-size=16KB
spring.webflux.multipart.max-disk-usage-per-part=128KB
spring.webflux.multipart.max-headers-size=2KB
spring.webflux.multipart.max-parts=3
```

Không thêm `spring-boot-starter-web` vào project thứ hai, vì Boot thường ưu tiên Servlet/MVC server nếu có cả web và webflux starters. WebClient client là chuyện khác; muốn kiểm chứng reactive server thì cần đúng runtime.

### 12.2. Reactive controller và cleanup file staging

**`src/main/java/com/example/reactivelimits/ReactiveLimitApplication.java`:**

```java
package com.example.reactivelimits;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveLimitApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveLimitApplication.class, args);
    }
}

@RestController
class ReactiveLimitController {

    private static final int MAX_RAW_BYTES = 64 * 1024;

    @GetMapping("/api/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @PostMapping(
            path = "/api/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    Mono<Map<String, String>> json(@RequestBody Mono<Message> body) {
        // Decoder có thể cần gom một JSON object.
        return body.map(item -> Map.of("received", item.message()));
    }

    @PostMapping(
            path = "/api/raw",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    Mono<ResponseEntity<Map<String, Object>>> raw(
            @RequestBody Flux<DataBuffer> body) {

        // join giới hạn tổng bytes được aggregate.
        // Nếu vượt giới hạn, DataBufferLimitException xảy ra.
        return DataBufferUtils.join(body, MAX_RAW_BYTES)
                .map(buffer -> {
                    try {
                        int bytes = buffer.readableByteCount();
                        return ResponseEntity.ok(
                                Map.<String, Object>of("bytes", bytes));
                    } finally {
                        DataBufferUtils.release(buffer);
                    }
                })
                .onErrorResume(
                        DataBufferLimitException.class,
                        error -> Mono.just(
                                ResponseEntity.status(413).body(
                                        Map.<String, Object>of(
                                                "error", "raw body too large"))));
    }

    @PostMapping(
            path = "/api/upload",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Mono<Map<String, Long>> upload(
            @RequestPart("file") FilePart file) {

        // Tạo file staging là blocking filesystem operation.
        Mono<Path> staging = Mono.fromCallable(
                        () -> Files.createTempFile(
                                "demo-upload-", ".bin"))
                .subscribeOn(Schedulers.boundedElastic());

        return Mono.usingWhen(
                staging,
                path -> file.transferTo(path)
                        .then(Mono.fromCallable(
                                        () -> Map.of(
                                                "bytes", Files.size(path)))
                                .subscribeOn(Schedulers.boundedElastic())),
                ReactiveLimitController::deleteTemp,
                (path, error) ->
                        ReactiveLimitController.deleteTemp(path),
                ReactiveLimitController::deleteTemp);
    }

    private static Mono<Void> deleteTemp(Path path) {
        return Mono.fromCallable(() -> Files.deleteIfExists(path))
                .subscribeOn(Schedulers.boundedElastic())
                .then();
    }
}

record Message(String message) {}
```

**Các điểm quan trọng của code:**
1. `@RequestBody Mono<Message>` dùng JSON decoder WebFlux. Một JSON object vượt codec aggregate limit có thể thất bại **trước khi `body.map(...)` chạy**; HTTP status mặc định của lỗi decode không nên đoán theo type exception mà không có error policy.
2. `@RequestBody Flux<DataBuffer>` là **raw chunk stream**. Nếu không có `join(maxByteCount)` hoặc counter khác, nó không tự dừng ở tổng 32KB của `spring.codec`.
3. `DataBufferUtils.join(body, MAX_RAW_BYTES)` aggregate có **quota 64KiB**. Khi vượt limit, nó phát `DataBufferLimitException`; Spring Framework quản lý release input buffers khi join gặp error/cancel theo API contract.
4. Khi `join` thành công, combined `DataBuffer` do ứng dụng tiêu thụ và phải được release; `finally { DataBufferUtils.release(buffer); }` tránh rò rỉ pooled memory.
5. `onErrorResume(DataBufferLimitException.class, ...)` là **error mapping riêng cho raw route** nên HTTP 413 có chủ đích. Nó không tự bắt được mọi lỗi JSON/multipart ở tầng khác.
6. `Mono.usingWhen` tạo staging file, thực hiện transfer và dọn file **trên complete, error và cancel**. File temp do framework multipart parser tạo là một resource khác, do framework quản lý.
7. `Files.createTempFile`, `Files.size`, `Files.deleteIfExists` là blocking filesystem calls; chuyển sang `Schedulers.boundedElastic()` để không chặn Reactor Netty event-loop.
8. File demo **không được giữ lại** sau khi trả metadata. Production nếu cần lưu file thật phải có policy scan/validate, durable storage, rename/move atomic có điều kiện và cleanup staging trước khi commit.
9. Chỉ có một top-level public class trong file; controller và record package-private hợp lệ, cùng package để component scan.

**Lưu ý lỗi cancel:** `Mono.usingWhen` chỉ có thể cleanup sau khi resource được acquire/observed qua publisher. Với thực tế I/O/driver/filesystem, vẫn cần kiểm tra orphan files khi process crash/power loss: cleanup callback không chạy khi JVM bị kill -9 hoặc node mất nguồn. Một sweeper theo TTL/quota là lớp bảo vệ bổ sung.

### 12.3. Chạy và thử với curl

```bash
gradle bootRun
```

Hoặc `./gradlew bootRun` khi đã có Gradle Wrapper.

Dùng lại `small.bin`, `large.bin` đã tạo ở mục 8:

```bash
curl -i \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @small.bin \
  http://localhost:8081/api/raw

curl -i \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @large.bin \
  http://localhost:8081/api/raw
```

- Raw 32KiB: HTTP 200 và `{"bytes":32768}`.
- Raw 80KiB: HTTP 413 và body `{"error":"raw body too large"}` theo policy trong `onErrorResume`.

Multipart nhỏ:

```bash
curl -i -F 'file=@small.bin' \
  http://localhost:8081/api/upload
```

Vì max-in-memory-size chỉ là ngưỡng spool 16KB và disk budget 128KB, file 32KB **có thể được tiếp nhận** (đẩy disk) và route trả `{"bytes":32768}`, không phải 413 do “vượt 16KB”. File 200KB có thể bị parser reject vì vượt max disk usage per part; status/body phải được kiểm tra trên runtime và error handling thực tế.

**Tránh dùng `spring.codec.max-in-memory-size=-1` để chữa raw 80KB:** raw route có limit độc lập 64KiB nên sẽ vẫn từ chối, đúng như thiết kế.

## 13. WebFlux integration tests: 64KiB là quota do app đặt

**`src/test/java/com/example/reactivelimits/ReactiveLimitIntegrationTest.java`:**

```java
package com.example.reactivelimits;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveLimitIntegrationTest {

    @LocalServerPort
    int port;

    HttpClient client = HttpClient.newHttpClient();

    HttpResponse<String> postRaw(int size) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                URI.create(
                        "http://127.0.0.1:" + port + "/api/raw"))
                .header("Content-Type", "application/octet-stream")
                .POST(HttpRequest.BodyPublishers.ofByteArray(
                        new byte[size]))
                .build();

        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void rawBodyBelowLimitReturns200() throws Exception {
        HttpResponse<String> response = postRaw(16 * 1024);
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"bytes\":16384"));
    }

    @Test
    void rawBodyAboveLimitReturns413() throws Exception {
        HttpResponse<String> response = postRaw(80 * 1024);
        assertEquals(413, response.statusCode());
        assertTrue(response.body().contains("raw body too large"));
    }

    @Test
    void exactly64KiBBelongsToAcceptedBoundary()
            throws Exception {
        HttpResponse<String> response = postRaw(64 * 1024);
        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"bytes\":65536"));
    }
}
```

Chạy:

```bash
gradle test
```

**Kỳ vọng** ba tests pass nếu runtime và dependencies đúng; đây là kết quả **suy luận từ code, chưa được chạy trong bài**. Test qua HTTP server `RANDOM_PORT` thật, không chỉ gọi controller trực tiếp nên nó xác nhận cả pipeline `Flux<DataBuffer>` + `DataBufferUtils.join`. Những assertions dùng `contains` chỉ để tránh phụ thuộc thứ tự fields/whitespace của JSON.

Test `exactly64KiB` làm rõ boundary **max bytes cho phép là 65.536**, không phải reject khi bằng ngưỡng. Trong production cần thêm tests khi client gửi body `Transfer-Encoding: chunked`, thay đổi Content-Length, chậm từng chunk, disconnect và concurrent requests. Không dùng tốc độ mạng của CI để assert deadline chính xác tới mili-giây.

## 14. Nếu cần streaming multipart bằng Flux<PartEvent>

WebFlux hỗ trợ `@RequestBody Flux<PartEvent>`, cho phép xử lý tuần tự mỗi multipart part mà không cần trước hết chuyển toàn bộ request thành `MultiValueMap<String, Part>`.

Spring Framework docs mô tả:
- `FormPartEvent`: field form.
- `FilePartEvent`: file part, có thể có nhiều events nếu file lớn.
- `PartEvent.isLast()` báo event cuối của một part.
- `windowUntil(PartEvent::isLast)` nhóm những events theo part.
- `PartEvent.content()` trả `DataBuffer`, phải **consume, relay hoặc release**.

**Mảnh ý tưởng, không phải chương trình hoàn chỉnh:**

```java
@PostMapping(
        path = "/stream-multipart",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> stream(@RequestBody Flux<PartEvent> events) {
    return events
            .doOnNext(event -> {
                DataBuffer buffer = event.content();
                try {
                    // Chỉ là minh họa nhận thấy bytes.
                    // Production phải xử lý part boundaries và quota.
                    int count = buffer.readableByteCount();
                } finally {
                    DataBufferUtils.release(buffer);
                }
            })
            .then();
}
```

Đoạn trên chỉ minh họa **quyền sở hữu DataBuffer**; nó **không lưu file, không validate schema, không kiểm soát tổng bytes, không phân biệt loại part, không phải endpoint upload production**. Nếu dùng nó thật, phải thêm byte counter theo part và tổng request, max parts, filename policy, bounded temp storage, lifecycle cleanup và tests. Không copy ví dụ này vào project rồi giả vờ đã có upload an toàn.

**Không dùng `collectList()`, `reduce` giữ toàn bộ buffer/part events, hay `DataBufferUtils.join` không giới hạn cho file vài GB**, vì như thế bỏ lợi ích streaming. Nếu cần ghi tệp, dùng `DataBufferUtils.write(..., Path, ...)`/reactive file I/O theo đúng contract, quản lý cleanup/close/cancel và byte quotas; trên disk nên có filesystem quota và orphan sweeper.

Với `Flux<PartEvent>`, các setting spool disk của non-streaming multipart parser có thể **không áp giống nhau**, nên phải kiểm thử từng parser path và không rely vào `max-disk-usage-per-part` để giới hạn mọi custom streaming handlers.

## 15. Proxy/Ingress: chặn body sớm trước khi tốn tài nguyên JVM

Nếu public traffic đi qua NGINX, một lớp bảo vệ đơn giản là:

```nginx
# Fragment trong server/location config NGINX, không phải file chạy riêng.
server {
    listen 443 ssl;
    server_name api.example.test;

    # TLS certificate/key, routing, policies khác cần cấu hình thêm.
    client_max_body_size 256k;

    location /api/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_request_buffering on;

        # Timeout/headers chính xác phải theo topology.
        proxy_read_timeout 60s;
    }
}
```

Đây là **mảnh cấu hình**, chưa đủ thành production HTTPS server vì thiếu `ssl_certificate`/`ssl_certificate_key`, trusted proxy/header handling, authentication và network ACL. Không deploy nguyên đoạn như một config đã hoàn chỉnh.

Giải thích:
- `client_max_body_size` giới hạn body tại NGINX; request bị từ chối có thể nhận **413** ngay ở edge, trước khi Boot nhận request.
- `proxy_request_buffering on` có thể làm proxy buffer body (memory/disk tùy config). Nó bảo vệ backend theo cách nào đó nhưng chuyển áp lực disk/body temp sang NGINX; phải cấp quota/cleanup cho proxy.
- Nếu `proxy_request_buffering off`, backend có thể nhận body streaming sớm hơn; điều đó **không bỏ qua body size policy** khi NGINX có thể xác định, nhưng behavior với chunked/chậm client cần test.
- Cần giới hạn **headers/URI** ở edge theo cơ chế NGINX tương ứng và bảo đảm chúng không rộng hơn backend một cách tùy tiện.
- Nếu có CDN/gateway trước NGINX, request có thể bị chặn từ lớp trước nữa; không phải mọi 413 đều do Spring Boot.

**Khi app cần nhận file 1GB:** đừng chỉ nâng mọi limit lên 1GB. Có thể dùng direct-to-object-storage pre-signed upload, resumable/chunked upload hoặc streaming pipeline có quota, checksum, antivirus scan, timeout và cleanup. Lúc đó application có thể chỉ nhận metadata/token và giữ heap ổn định.

## 16. Content-Length có đủ để chặn request lớn không?

**Không.** `Content-Length` có thể:
- Hoàn toàn vắng mặt ở HTTP request dùng chunked framing.
- Có giá trị không tin cậy từ client trước khi server chuẩn hóa/validate.
- Bị kiểm tra/sửa/loại bởi proxy.
- Không phản ánh **số bytes sau khi giải nén**, nếu tầng application hỗ trợ compressed content.
- Có thể mâu thuẫn với `Transfer-Encoding` ở các request malformed; cần để server/proxy xử lý theo chuẩn và chặn request smuggling.

Có thể từ chối sớm dựa trên Content-Length **như tối ưu**, nhưng **bắt buộc đếm bytes thực sự đọc** đối với raw streaming nếu muốn giới hạn chắc chắn. MVC demo đếm `InputStream.read`; WebFlux demo dùng `DataBufferUtils.join(..., maxByteCount)`. Trong production streaming file nhiều GB, không nên join vào memory mà dùng counter theo `DataBuffer.readableByteCount()` + bounded writer.

**Đơn vị đo:** body wire bytes khác decoded string/JSON object size và khác upload storage size sau transform/decompression. Nếu client gửi gzip và gateway/app giải nén, cần giới hạn cả **compressed** và **decompressed** bytes để chống decompression bomb. Không giả định `Content-Length=100KB` tức app sẽ chỉ sử dụng 100KB heap.

## 17. Status code, exception và response khi bị giới hạn

| Lỗi/điều kiện | HTTP status có thể thấy | Tầng xử lý |
|---|---|---|
| App chủ động thấy raw body vượt quota | **413** nếu map có chủ đích | Controller/handler của demo |
| Spring MVC multipart quá file/request limit | Thường **413** khi `MaxUploadSizeExceededException` được xử lý | Servlet multipart + advice |
| WebFlux `DataBufferLimitException` | Phụ thuộc error handler; có thể là 4xx/5xx nếu không map | Codec/reader/handler |
| HTTP request headers quá lớn | **400/431** hoặc connection close tùy server | HTTP decoder/container |
| URI/request line quá dài | Có thể **414/400** tùy parser | HTTP decoder |
| Part count/part headers vượt giới hạn | 400/413 hoặc parser-specific error | Multipart parser |
| Gateway `client_max_body_size` vượt | **413** tại gateway | Reverse proxy |
| Không đủ disk temp | Thường 5xx nếu không map; có thể connection failure | Filesystem/parser/transfer |
| Payload có JSON sai cú pháp nhưng kích thước hợp lệ | Thường **400** với proper error handling | JSON decoder/validation |
| Body stream bị client disconnect | Có thể không còn HTTP response gửi được | Transport/cancel |

**Không thể bảo đảm mọi tình huống là JSON `ProblemDetail` từ app.** Những request bị proxy/header parser loại trước controller sẽ không chạy `@ExceptionHandler`. Với upload bị từ chối sớm, client vẫn gửi dữ liệu có thể gặp connection reset, vì container không muốn đọc một body quá lớn.

Với error response của ứng dụng, trả thông tin an toàn như:
- `type` và `title="Payload Too Large"`.
- `status=413`.
- `detail` nêu kích thước tối đa theo policy được phép công khai.
- Correlation ID an toàn nếu hệ thống có.
- Không echo filename raw có đường dẫn, authorization headers, request body hay stack trace.

Nếu cần biết chính xác lớp nào từ chối, dựa vào proxy access log + server logs/metrics với correlation. Đừng chỉ nhìn status code và khẳng định do property cụ thể.

## 18. RAM, direct memory, disk và số requests đồng thời

Giới hạn một request nhỏ **không có nghĩa tổng tài nguyên nhỏ**. Ví dụ giả định **1000 requests đồng thời**, mỗi request giữ được **256KiB** buffer, phần payload thôi đã dùng xấp xỉ **250MiB** memory, chưa gồm object graph, codecs, Netty direct buffers, TLS, thread stacks và caching. Nếu nâng codec cap lên 8MiB, 1000 requests đồng thời có thể yêu cầu khoảng **7,8GiB** chỉ riêng các buffers 8MiB.

Đây là **ước lượng toán học đơn giản**, không phải phép đo hiệu năng JVM/Netty. Luồng request có thể không giữ đủ max buffer cùng lúc; ngược lại có thể có nhiều buffers/overhead khác làm peak cao hơn.

Bài toán disk:
- Servlet `file-size-threshold=0B` có thể làm nhiều uploads dùng temp files.
- WebFlux `max-in-memory-size` là threshold spool, disk usage per part mặc định **-1 (unlimited)**; nhiều parts cùng lúc có thể đầy disk dù từng file không vượt ngưỡng business.
- Với gateway buffering, proxy cũng có temp disk riêng.
- Container/Kubernetes có `ephemeral-storage` quota và temp volume; khi full, request có thể thành 5xx hoặc pod bị evicted.
- File staging do app tự tạo phải có cleanup ở success, exception, cancellation, timeout và crash recovery (sweeper), khác với framework-owned multipart temp.

Cần vận hành cùng lúc:
1. Max payload per API/tenant/user.
2. Max concurrent uploads và in-flight bytes.
3. Bounded temporary storage + per-user quotas.
4. Rate limits, connection/request timeout, upload duration.
5. Memory/direct memory/heap metrics, disk usage, open file descriptors.
6. Cleanup orphan files và failed upload partial artifacts.
7. Alert theo error 413/431/5xx, latency, saturation, rejected requests.
8. Load testing và chaos/disconnect tests theo hạ tầng thực.

**Không tăng heap để chữa đầy disk**, cũng không đổi `spring.codec.max-in-memory-size` để chữa lỗi HTTP header parser; mỗi giới hạn thuộc tầng khác nhau.

## 19. DataBuffer ownership, cancellation và bộ nhớ bị giữ

Ở WebFlux, `DataBuffer` có thể bọc **pooled reference-counted Netty ByteBuf**. Khi code đọc trực tiếp `Flux<DataBuffer>`, cần tuân thủ quyền sở hữu và release. Spring Framework cung cấp `DataBufferUtils.release`, `DataBufferUtils.join`, `DataBufferUtils.write` và `doOnDiscard` hooks hỗ trợ xử lý.

**Mẫu của demo:** `DataBufferUtils.join(body, limit)` sẽ quản lý input buffers theo contract. Khi thành công, combined buffer đi vào `map`, application dùng `readableByteCount()` và release trong `finally`. Nếu bọc một buffer trong async callback rồi giữ sau khi adapter đã release, có thể gặp use-after-release hoặc memory leak.

**Không làm:**

```java
// Pseudocode KHÔNG NÊN DÙNG:
List<DataBuffer> cached = body.collectList().block();
byte[] all = ...;
```

Đoạn trên không có bound, `block()` trong WebFlux event-loop có thể gây thread starvation, các buffers có thể không được release, và bộ nhớ bị scale theo tổng body. Với file lớn, dùng streaming writer và giới hạn bytes/in-flight buffers.

**Nếu cần forward request body sang downstream WebClient**, phải rõ ai sở hữu/release mỗi DataBuffer sau send, cancellation propagation, retry semantics và request replayability. Một body Flux đã consumed không tự phát lại được an toàn khi retry; lưu vào RAM chỉ để retry có thể phá quota.

**Cancellation không tự rollback side effects:** khi user đóng browser, một upload có thể đã tạo staging file hoặc commit metadata. Nếu dùng async cleanup khi Publisher cancel, phải gắn đúng lifecycle; nếu process crash cleanup không chạy. Đo orphan files và đặt reconciliation job.

## 20. Lỗi phổ biến khi triển khai giới hạn

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Multipart 80KB bị từ chối dù `max-request-size=128KB` | `max-file-size=64KB` cho từng file nhỏ hơn | Nâng/giữ file cap theo business, không chỉ total cap |
| JSON 20MB vẫn vào MVC dù multipart max 1MB | Multipart properties không áp cho JSON | Giới hạn tổng body ở edge hoặc route/parser đúng |
| WebFlux JSON 1MB gây `DataBufferLimitException` | Codec phải aggregate và max-in-memory mặc định ~256KiB | Bounded codec config hoặc streaming/resize DTO |
| WebFlux file 100KB vẫn nhận khi memory threshold 16KB | Threshold làm spool xuống disk, không phải reject | Đặt `max-disk-usage-per-part` và total quota |
| Tệp upload làm đầy disk /tmp | Framework temp spool/app staging không có disk quota hoặc cleanup | Per-part + total disk quota, temp dir, sweeper |
| Header parser chặn trước controller | `server.max-http-request-header-size`/URL limit | Sửa token/cookie/proxy, kiểm tra parser, đừng chỉ thêm advice |
| HTTP header 8KB hoạt động Tomcat nhưng fail Netty hoặc ngược lại | Semantics Tomcat tổng vs Netty từng header | Test trên đúng server + protocol |
| Status 413 từ CDN nhưng Spring không log | Request bị từ chối trước JVM | Tìm gateway/CDN access log và request ID |
| Tăng `server.tomcat.max-swallow-size` mà file 100MB vẫn bị reject | Swallow không phải max upload | Dùng multipart quota/ingress policies đúng |
| File lớn bị connection reset thay vì ProblemDetail 413 | Server reject sớm khi client còn gửi body | Test upload lifecycle, swallow policy, proxy buffering |
| Part headers quá lớn | `max-part-header-size` / `max-headers-size` | Rà filename/metadata và cap per-part headers |
| Hàng nghìn multipart fields nhỏ làm chậm parser | Không giới hạn `max-parts` hoặc business field count | Đặt part count, schema validation và rate limits |
| WebFlux raw body vượt 32KB codec vẫn được nhận | Raw `Flux<DataBuffer>` không aggregate theo codec | Đặt byte counter/`join(limit)` riêng |
| POST form 500KB bị từ chối nhưng JSON 500KB hợp lệ | Tomcat form-post limit khác JSON | Hiểu parsing path và policy |
| WebClient download response lớn fail codec limit | `bodyToMono(byte[].class)` phải aggregate | Streaming content hoặc client-specific decoder cap |
| Bật codec cap -1 rồi OOM | Vô hiệu memory protection | Không bỏ giới hạn toàn app; đo payload và concurrency |
| Thấy 413 nhưng không biết tầng từ chối | Proxy/container/app có thể cùng trả 413 | Correlation logs và metrics cho từng hop |
| Có retry upload gây tạo file trùng | Không có idempotency key/commit protocol | Dedupe/transaction và temp cleanup |
| Filename có `../` hoặc absolute path | Tin filename do client gửi | Dùng server-generated ID, sanitize, không join path trực tiếp |
| Có `Content-Length` nhỏ nhưng body nhiều hơn | Framing/transfer encoding hoặc source không tin cậy | Để parser chuẩn xử lý, luôn count actual consumed bytes |
| Một kết nối chậm giữ memory lâu | Slow upload/drip attack, timeout không phù hợp | Idle/read timeout, rate/concurrency limits, early reject |

## 21. Bảng kiểm thử ranh giới cho từng tầng

| Tầng | Test boundary | Điều cần xác minh |
|---|---|---|
| Proxy body | 255KiB, 256KiB, 257KiB | Proxy áp size như cấu hình, status/correlation đúng |
| Tomcat multipart file | 64KB, 64KB+1 | File cap độc lập tổng multipart request |
| Tomcat multipart request | Tổng 128KB và >128KB | Overhead boundaries/part headers đã tính |
| Tomcat part count | 8 vs 9 parts | Parser giới hạn số parts |
| Tomcat part headers | Header file vừa đủ/vượt 1KB | Lỗi từ parser, không phải HTTP header limit |
| Raw MVC route | 65.536 vs 65.537 bytes | Bytes thực đọc; Content-Length không phải nguồn quyết định |
| JSON MVC | Large JSON so với multipart limits | Không giả định multipart cap đã bảo vệ JSON |
| WebFlux codec | 32KB object JSON và >32KB | DataBufferLimitException/error policy đúng |
| WebFlux raw route | 65.536 vs 65.537 bytes | `join(limit)` boundary và release |
| WebFlux multipart file | File 16KB, 32KB, 128KB, 128KB+ | Threshold spool vs per-part disk quota |
| WebFlux part count | 3 vs 4 parts | Reactive parser giới hạn |
| HTTP headers | Header/URI dưới và trên 8KB | Tomcat/Netty/proxy semantics theo runtime |
| Chunked upload | Không có Content-Length | Limit vẫn dựa bytes thực/edge |
| Concurrent large uploads | N clients x payload near limit | Heap/direct memory/disk/CPU không vượt SLO |
| Cancel/disconnect giữa upload | Đang gửi dở rồi đóng | Staging cleanup, không leak descriptors |
| Temp disk full | Hết quota trong lúc upload | Trả lỗi phù hợp, pod không mất kiểm soát |
| Invalid Content-Type | Body giả multipart/JSON sai | 400/415/parsing errors, không log raw secret |
| Compression | Gzip “nhỏ” giải nén lớn | Bảo vệ compressed và uncompressed quotas |
| HTTPS/HTTP2 ingress | Thay protocol/route | Header/body size vẫn được enforce |

**Đừng chỉ test trên `MockMvc`** nếu muốn chứng minh Tomcat multipart/parser/header size limits; MockMvc có thể bỏ qua network parser. Hãy dùng `@SpringBootTest(RANDOM_PORT)` với HTTP client thật như demo và một lớp test qua gateway/ingress đang chạy.

Tương tự, WebFlux `WebTestClient.bindToController(...)` không tái hiện Reactor Netty HTTP header decoder hoặc temp disk behavior. Nên có network integration tests với actual embedded server.

## 22. Tăng limit có làm ứng dụng “hỗ trợ file lớn” chưa?

Chưa. Việc nâng một limit có thể mở ra nút thắt khác:
- File-size tăng từ 1MB lên 100MB, nhưng proxy body cap còn 10MB → 413 tại proxy.
- Proxy cho phép 100MB, Servlet file threshold giữ memory → heap/disk stress.
- Multipart WebFlux 100MB spool disk, nhưng container ephemeral-storage chỉ 50MB → disk full/pod eviction.
- Codec cap 100MB cho JSON → 100 concurrent requests có thể cần GB-level memory, gây GC pauses.
- HTTP body đến trong 10 phút từ client rất chậm → connection occupancy/slowloris.
- Backend nhận file rồi gọi scanner/downstream bằng `byte[]` → thêm bản sao memory.
- Server upload thành công nhưng app không dọn temp file trên lỗi → disk usage tăng theo thời gian.

**Hướng thiết kế file lớn đáng tin hơn:**
1. Có business contract về tối đa từng file và tổng batch.
2. Dùng streaming hoặc multipart PartEvent có quotas rõ; tránh `getBytes()` cho file lớn.
3. Chỉ lưu file vào staging/quarantine, chưa public trước khi validation/scan.
4. Streaming checksum/hash và content sniffing ở mức cần thiết.
5. Server-generated file ID/path, không dùng tên file client để tạo path trực tiếp.
6. Atomic commit/move khi khả thi; cleanup khi error/cancel.
7. Upload resumable/presigned object-storage khi payload rất lớn.
8. Quotas theo tenant, concurrency limit, time budget và rate limiting.
9. Quan sát heap/direct memory, multipart temp disk, failed uploads, rejects, latency.
10. Test đường dữ liệu qua proxy, container, framework, database/object storage — không chỉ controller unit test.

**Không xem tăng size limits là cách giải quyết DoS**. Nó có thể làm bề mặt tấn công lớn hơn nếu không có quotas/validation.

## 23. Security: tài nguyên, parser và thông tin người dùng không đáng tin

Các request-size controls cũng là security boundary, không chỉ performance tuning. Có những nguy cơ:
- **Denial of service:** quá nhiều large bodies/headers/parts/cookies, memory/CPU/disk.
- **Multipart filename traversal:** client gửi `filename="../../etc/passwd"`; không nối trực tiếp vào storage path.
- **MIME spoofing:** `Content-Type: image/png` không chứng minh file là PNG an toàn; cần kiểm tra magic bytes và scanner khi có yêu cầu.
- **Decompression bomb:** dữ liệu nén nhỏ giải nén cực lớn.
- **Request smuggling:** `Content-Length`/`Transfer-Encoding` không nhất quán giữa proxy và backend; phải cấu hình HTTP parsers đúng chuẩn, không tự parse framing.
- **Disk exhaustion:** temp files/failed uploads bị sót.
- **Log injection/PII:** header values/file names/raw body có thể chứa dữ liệu nhạy cảm và control characters.
- **Tenant bypass:** user A có thể dùng toàn bộ disk nếu chỉ đặt per-file quota mà không có tenant quota.

Không tin các header `X-Forwarded-*` do client tự gửi để quyết định quota theo IP; phải thiết lập trusted proxy boundary. Authentication/authorization cho upload vẫn cần thiết; size limits không thay role/ownership checks. Nếu có public unauthenticated upload, edge rate limits, captcha/abuse prevention, malware scanning và hard quota cần cân nhắc kỹ.

Một response 413 nên không tiết lộ absolute path temp, SQL, token hoặc cấu trúc nội bộ. Log correlation có redaction; metric tags chỉ dùng endpoint template/status/reason enum hữu hạn, không đưa raw filename/request URL vào metric labels.

## 24. Observability: biết giới hạn nào bị chạm

Gợi ý thu thập:
- **Counters:** `http.request.rejected` với reason `body_size`, `multipart_file_size`, `multipart_parts`, `codec_buffer`, `header_size` (những reason app có quan sát được).
- **HTTP status distribution:** 413/400/431/5xx theo URI template, method, app/ingress.
- **Payload histograms:** body bytes/per-file bytes, không lưu payload raw.
- **Resource gauges:** heap, Netty direct memory, temporary disk usage/quota, open file descriptors, active uploads và in-flight bytes.
- **Latency:** parser time, upload time, downstream storage commit time, cleanup duration.
- **Cleanup health:** orphan temp files count, TTL-age, storage pressure and repair jobs.

Đừng gắn file name, full URI, request body, user ID tự do làm low-cardinality metric labels. 413 xảy ra ở proxy có thể không tạo `http.server.requests` metric trong JVM; phải kết hợp proxy/CDN logs/metrics. Nếu header parsing fail trước Spring, ứng dụng có thể không tạo bất kỳ observation context nào cho request.

**Chọn alerts theo SLO:** 413 tăng có thể do client thay payload schema hoặc abuse, không mặc định là lỗi server. Theo dõi tỷ lệ reject và phân phối theo endpoint/tenant (tenant đã xác thực), không đẩy mọi expected 413 vào pager như 5xx.

## 25. Checklist triển khai production

- [ ] Đã tách giới hạn **tổng body**, **mỗi file**, **multipart request**, **số parts**, **headers**, **codec memory**.
- [ ] Dùng đúng properties cho MVC Servlet hay WebFlux; không copy giữa hai stack.
- [ ] Với Tomcat hiểu `max-http-form-post-size` và `max-swallow-size` **không phải max JSON upload**.
- [ ] Với WebFlux hiểu `spring.codec.max-in-memory-size` không chặn toàn bộ streamed body.
- [ ] Có body max tại gateway/ingress hoặc counting filter/handler phù hợp cho các route lớn.
- [ ] Có size policy cho Content-Length và **đếm bytes thực**, kể cả chunked uploads.
- [ ] Có HTTP header size và URL/initial-line limits, test theo server/version.
- [ ] Multipart đặt max file, max request, max parts, per-part headers và disk quotas.
- [ ] Không bỏ cap bằng `-1` khi chưa có quota thay thế và test memory/disk.
- [ ] DataBuffer có ownership/release đúng trên complete/error/cancel.
- [ ] Các buffers/queues tạm đều có limits; không `collectList()`/`join()` vô hạn.
- [ ] Dùng file staging, cleanup và orphan reconciliation khi crash.
- [ ] Có quota theo user/tenant, max concurrent uploads, rate limiting, timeout và slow-client controls.
- [ ] Có kiểm soát security cho filename/path, MIME/content, authentication/authorization và antivirus nếu cần.
- [ ] Error mapping 413/431/400/5xx được quan sát theo đúng tầng.
- [ ] Test với HTTP client thật, qua CDN/NGINX/ingress và dưới concurrent load.
- [ ] Metrics/logging không để lộ raw headers, filenames, bodies, token hay PII.
- [ ] Đo production payload distribution trước khi tăng bất kỳ limit nào.

## 26. Câu hỏi tự kiểm tra

**1. `spring.servlet.multipart.max-file-size=1MB` có chặn JSON 5MB trong MVC không?**  
Không. Đây là multipart file limit, không phải tổng body JSON.

**2. Vì sao WebFlux FilePart 100KB vẫn hợp lệ khi `spring.webflux.multipart.max-in-memory-size=16KB`?**  
Với file parts, 16KB là threshold chuyển xuống disk; còn giới hạn disk/part và quotas khác mới quyết định có nhận file hay không.

**3. `server.tomcat.max-swallow-size=2MB` nghĩa là chấp nhận upload tối đa 2MB?**  
Không. Nó kiểm soát lượng body Tomcat đọc bỏ sau khi request bị abort/reject, có thể ảnh hưởng việc client nhận error response.

**4. `server.max-http-request-header-size=8KB` có cùng semantics ở Tomcat và Netty?**  
Không. Theo docs Boot 3.3, Tomcat xét tổng request line + headers, Netty áp theo từng header. Hãy test đúng runtime/protocol.

**5. `spring.codec.max-in-memory-size=32KB` có chặn `Flux<DataBuffer>` tổng 100MB không?**  
Không tự động. Raw streaming chưa cần aggregate; muốn total cap phải đặt counter/join bounded riêng.

**6. `DataBufferLimitException` có luôn thành HTTP 413 không?**  
Không được mặc định như vậy; error mapping tùy framework/handler. Demo raw WebFlux chủ động map 413.

**7. Tại sao nên đặt `max-parts`?**  
Vì request có thể chứa rất nhiều fields/files nhỏ, tạo overhead parser/metadata/memory/disk dù mỗi part nhỏ.

**8. Vì sao cần kiểm thử multipart qua network thay vì chỉ MockMultipartFile?**  
MockMvc không nhất thiết chạy Servlet container multipart parser thực, nên không chứng minh max-file-size/max-request-size đã được enforce.

**9. Content-Length đủ tin để chặn upload không?**  
Không. Chunked requests có thể không có Content-Length; luôn đếm bytes thực đọc và dùng parser chuẩn.

**10. Có nên đặt mọi limit thành -1 để không bị lỗi?**  
Không. Nó có thể gỡ giới hạn memory/disk, làm OOM hoặc đầy filesystem.

**11. Tại sao status 413 ở production không xuất hiện trong app logs?**  
Vì gateway/CDN/proxy hoặc parser trước Spring có thể từ chối request, chưa bao giờ tới controller/observation.

**12. Nếu muốn file 2GB thì giải pháp đúng nhất là tăng `spring.codec.max-in-memory-size=2GB`?**  
Không. Cân nhắc streaming/chunked/resumable upload hoặc presigned object storage, body/file/disk/time quotas và cleanup rõ ràng.

## 27. Tài liệu chính thức

1. **Spring Boot 3.3 — Common Application Properties**: `spring.servlet.multipart.*`, `spring.webflux.multipart.*`, `spring.codec.max-in-memory-size`, `server.max-http-request-header-size`, `server.tomcat.*`, `server.netty.*`. https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
2. **Spring Boot / Spring guide — Uploading Files**: cấu hình multipart size và file lifecycle trong MVC. https://spring.io/guides/gs/uploading-files/
3. **Spring Framework — WebFlux Reactive Core, Limits**: Decoder/HttpMessageReader `maxInMemorySize` và multipart behavior. https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
4. **Spring Framework — WebFlux Multipart Content/PartEvent**: cách stream parts và yêu cầu consume/relay/release DataBuffer. https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
5. **Spring Framework — Data Buffers and Codecs**: `DataBufferUtils.join`, reference-counting, ownership và release. https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
6. **Spring Framework 6.1 — DefaultPartHttpMessageReader JavaDoc**: `setMaxInMemorySize`, `setMaxDiskUsagePerPart`, `setMaxParts`. https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html
7. **Spring Framework 6.1 — DataBufferUtils JavaDoc**: `join(Publisher, int maxByteCount)` và release semantics. https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
8. **Apache Tomcat 10.1 — HTTP Connector**: `maxPostSize`, `maxSwallowSize`, `maxHttpRequestHeaderSize` và request parser. https://tomcat.apache.org/tomcat-10.1-doc/config/http.html
9. **NGINX HTTP Core Module — client_max_body_size**: giới hạn body trước upstream. https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size
10. **RFC 9110 — HTTP Semantics**, 413 Content Too Large và 431 Request Header Fields Too Large theo version hiện hành. https://www.rfc-editor.org/rfc/rfc9110.html

**Kết luận:** Trong Spring Boot web-runtime, **request body**, **multipart**, **HTTP headers** và **codec buffering** là bốn giới hạn thuộc các cơ chế khác nhau. Multipart Servlet do `spring.servlet.multipart.*` và container quản lý; WebFlux có reactive multipart reader và `spring.codec.max-in-memory-size` cho decoding; HTTP headers được server/proxy parse trước controller; raw streaming chỉ an toàn khi bạn tự giới hạn số byte thực đọc. Thiết kế production cần kết hợp gateway, parser, codec, disk/heap quota, concurrency, timeout, security và cleanup, không chỉ tăng một property để request lớn hết báo lỗi.