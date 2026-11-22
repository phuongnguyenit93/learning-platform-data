# Kiểm thử multipart, CORS và yêu cầu có điều kiện trong Spring Web

## 1. Phạm vi và mục tiêu

Ba nhóm request sau rất dễ “trông có vẻ chạy” nhưng vẫn sai ở biên giao thức:

1. **Multipart:** HTTP request gồm nhiều phần (file và dữ liệu form/JSON). Test phải xác minh tên part, tên file, content type của từng part, nội dung, quy tắc validation và kết quả xử lý; đồng thời hiểu khác biệt giữa mock multipart và việc parse dữ liệu thật.
2. **CORS (Cross-Origin Resource Sharing):** browser hỏi server xem một origin khác có được truy cập tài nguyên không. Cần kiểm thử **preflight OPTIONS** và **actual request**; kết quả HTTP 200 không đủ để chứng minh trình duyệt sẽ cho JavaScript đọc response.
3. **Conditional request:** client gửi các header như `If-None-Match`, `If-Modified-Since` để tránh tải lại dữ liệu không thay đổi, hoặc `If-Match` để ngăn ghi đè một version đã cũ. Test phải phân biệt `200`, `304 Not Modified`, `412 Precondition Failed` và khi cần `428 Precondition Required`.

Bài này ưu tiên **Spring MVC (Servlet stack)** với `MockMvc`, JUnit 5 và Spring Boot 3.x / Java 17+. Cuối bài có hướng dẫn tương đương cho WebFlux / `WebTestClient` và các kiểm thử chạy trên server thật.

Nhớ ba lớp cần kiểm tra:

| Lớp | Câu hỏi |
| --- | --- |
| HTTP protocol | Method, URI, multipart boundary, status và headers có đúng không? |
| Spring handling | Controller binding, converters, validation, CORS configuration, cache condition logic có chạy đúng không? |
| Browser/container/infrastructure | Trình duyệt có chấp nhận CORS không, servlet container có parse multipart thật không, proxy/caches có xử lý headers đúng không? |

`MockMvc` rất hiệu quả cho lớp thứ hai nhưng không thay thế mọi kiểm thử ở lớp cuối cùng.

## 2. Chọn kiểu kiểm thử phù hợp

- **Unit test thuần Java:** gọi service/controller method trực tiếp để kiểm tra nghiệp vụ; không kiểm chứng request mapping, multipart argument binding, CORS handler hoặc status/headers do MVC sinh ra.
- **`MockMvc` với `@WebMvcTest`:** chạy MVC dispatching qua mock Servlet request/response, load một phần web application context; phù hợp cho request binding, controller advice, converters, validation, preflight/actual CORS và conditional responses.
- **`MockMvcBuilders.standaloneSetup(...)`:** nhanh, kiểm thử controller được chỉ định, nhưng config/filters/advice không được tự động nạp toàn bộ như app. Nếu muốn kiểm tra CORS global qua `WebMvcConfigurer` hoặc Spring Security filter chain, phải đưa đúng cấu hình vào.
- **`@SpringBootTest` + `@AutoConfigureMockMvc`:** giữ toàn bộ Spring context và phần lớn filters, hữu ích khi endpoint phụ thuộc security/DB/service khác. Vẫn dùng mock Servlet request, chưa phát HTTP socket thật.
- **`@SpringBootTest(webEnvironment=RANDOM_PORT)` + HTTP client thật:** chạy Servlet container và multipart parser, giúp phát hiện giới hạn kích thước, lỗi encoding/boundary, proxy/client behavior, networking. Dùng `TestRestTemplate` hoặc HTTP test client thích hợp; thêm browser test nếu cần xác nhận chính sách CORS của trình duyệt.

Với code bên dưới, dùng `@WebMvcTest` để chạy kiểm thử nhanh, ổn định, rồi bổ sung smoke/integration test với server thật cho các đường đi mà mock không mô phỏng.

## 3. Multipart: điều cần hiểu trước khi viết test

Một request có `Content-Type: multipart/form-data; boundary=...` chứa nhiều part. Mỗi part có thể có `Content-Disposition`, tên field, filename, `Content-Type` và nội dung riêng. Ví dụ:

~~~http
POST /api/upload HTTP/1.1
Content-Type: multipart/form-data; boundary=xyz

--xyz
Content-Disposition: form-data; name="file"; filename="notes.txt"
Content-Type: text/plain

hello
--xyz
Content-Disposition: form-data; name="tag"

quarterly
--xyz
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"description":"report"}
--xyz--
~~~

Ba kiểu binding thường gặp trong MVC:

- `@RequestPart("file") MultipartFile file`: đọc file part, lấy `getOriginalFilename()`, `getContentType()`, `getSize()`, `getBytes()` hoặc stream.
- `@RequestParam("tag") String tag`: đọc text form field.
- `@RequestPart("metadata") Metadata metadata`: đọc một **part JSON** bằng HTTP message converter; part phải có content type phù hợp, thường `application/json`.

`@RequestParam` cho text form và `@RequestPart` cho JSON object không phải hoàn toàn thay thế nhau. Nếu server kỳ vọng JSON part mà client chỉ gửi form text thường, converter có thể trả lỗi media type/binding.

### Dựng request đúng bằng MockMvc

~~~java
MockMultipartFile file = new MockMultipartFile(
        "file", "notes.txt", "text/plain",
        "hello".getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/api/upload")
        .file(file)
        .param("tag", "quarterly"))
        .andExpect(status().isOk());
~~~

`multipart(...)` tạo `MockMultipartHttpServletRequest` đã chứa parts/file do test cung cấp. **MockMvc không tự parse một luồng raw multipart có boundary**: test này chứng minh controller và binding hoạt động với mock parts đã dựng, nhưng không xác minh parser thực tế, max file size ở Servlet container hay khả năng gửi multipart từ browser/client thật.

### JSON part bên cạnh file

~~~java
MockMultipartFile file = new MockMultipartFile(
        "file", "notes.txt", MediaType.TEXT_PLAIN_VALUE,
        "hello".getBytes(StandardCharsets.UTF_8));

MockMultipartFile metadata = new MockMultipartFile(
        "metadata", "", MediaType.APPLICATION_JSON_VALUE,
        "{\"description\":\"report\"}"
            .getBytes(StandardCharsets.UTF_8));

mockMvc.perform(multipart("/api/upload")
        .file(file)
        .file(metadata)
        .param("tag", "quarterly"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.description").value("report"));
~~~

Tên `metadata` phải trùng `@RequestPart("metadata")`; khi dùng DTO JSON, part content type phải tương thích với converter. Tránh thử JSON part chỉ bằng `.param("metadata", "...")` rồi kết luận rằng JSON deserialization đã được kiểm chứng.

### Những case multipart quan trọng

| Test | Dữ liệu vào | Kỳ vọng |
| --- | --- | --- |
| Happy path | File đúng key, content type, tag và optional JSON part | 2xx cùng các trường trả về đúng |
| Thiếu part bắt buộc | Không có `file` | Thường `400 Bad Request` nếu `@RequestPart(required=true)` |
| File rỗng | File có bytes rỗng | Status theo validation của ứng dụng, ví dụ 400 |
| Sai content type | File `application/octet-stream` khi nghiệp vụ chỉ nhận `text/plain` | 415 hoặc 400 tùy contract |
| Sai field name | Gửi `upload` thay vì `file` | Thiếu part `file` → 400 |
| JSON part không hợp lệ | `metadata` có JSON sai cú pháp hoặc kiểu | Lỗi conversion/binding, thường 400 |
| File vượt giới hạn | File thật vượt `spring.servlet.multipart.max-file-size` | Test end-to-end để đi qua multipart parser/Servlet container |
| Filename nguy hiểm | `../secret.txt`, tên rất dài, Unicode | Không tin `getOriginalFilename()`; sanitize và kiểm soát path server-side |
| Kích thước/bộ nhớ | File lớn, nhiều parts | Test integration/resource limits, không chỉ assert trên mock |

Không so sánh chuỗi raw multipart bao gồm boundary do client sinh ngẫu nhiên. Ưu tiên assert ý nghĩa từng part hoặc ghi nhận request qua HTTP server thật.

## 4. CORS: preflight khác actual request thế nào?

**Origin** = scheme + host + port. `https://ui.example` và `https://api.example` là hai origin khác nhau dù cùng dùng HTTPS. CORS là chính sách của **browser** về việc JavaScript ở origin này đọc response từ origin khác; nó không thay thế server-side authentication/authorization.

Một preflight thường là request `OPTIONS` với:

~~~http
OPTIONS /api/upload HTTP/1.1
Origin: https://ui.example
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-trace-id
~~~

Response hợp lệ có thể chứa:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://ui.example
Access-Control-Allow-Methods: GET,POST,PUT
Access-Control-Allow-Headers: content-type,x-trace-id
Access-Control-Max-Age: 3600
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
~~~

Giá trị `Access-Control-Allow-Methods` có thể thay đổi cách trình bày và phạm vi tùy Spring/config; assert các thành phần quan trọng thay vì phụ thuộc thứ tự header không có ý nghĩa nghiệp vụ.

Preflight được Spring MVC CORS processing xử lý trực tiếp trước khi gọi business controller method. Nếu preflight không được chấp nhận, browser thường **không gửi actual request**. Nhưng một công cụ như `curl` hoặc `MockMvc` vẫn có thể cố tình gửi actual request độc lập: CORS không phải hàng rào chống non-browser clients.

Actual request:

~~~http
POST /api/upload HTTP/1.1
Origin: https://ui.example
Content-Type: multipart/form-data; boundary=...
~~~

Response cần có `Access-Control-Allow-Origin` phù hợp để browser cho frontend đọc response. Với origin không được phép, Spring có thể trả `403 Invalid CORS request`, nhưng browser cũng có thể chặn khi server trả 200 mà thiếu CORS headers; **test browser behavior không thể suy ra chỉ từ status**.

### Kiểm thử CORS nên bao gồm

1. Preflight từ origin được phép, method/header được phép: status thành công và `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers` đúng.
2. Actual request từ origin được phép: business endpoint chạy và response có `Access-Control-Allow-Origin`.
3. Preflight từ origin không được phép: reject (trong MVC mặc định thường 403).
4. Method hoặc requested headers không được phép: preflight reject.
5. `Vary: Origin` để shared cache không tái sử dụng sai response giữa các origin.
6. Credentialed CORS nếu có cookie/session: chỉ phản chiếu origin đã cho phép, `Access-Control-Allow-Credentials: true`; **không dùng wildcard `*` cho `allowOrigins` cùng credentials**.
7. Khi Spring Security có mặt: CORS xử lý preflight trước auth/filter bắt login; cấu hình `http.cors(...)` và CSRF riêng cho request thay đổi trạng thái.

Ví dụ MVC annotation:

~~~java
@CrossOrigin(
    origins = "https://ui.example",
    methods = {RequestMethod.GET, RequestMethod.POST, RequestMethod.PUT},
    allowedHeaders = {"Content-Type", "X-Trace-Id", "If-Match"},
    exposedHeaders = {"ETag"},
    maxAge = 3600
)
@RestController
class ApiController {
    // Endpoints...
}
~~~

`exposedHeaders` quyết định header nào ngoài các CORS-safelisted response headers mà JavaScript được đọc (ví dụ `ETag`). `Access-Control-Allow-Headers` lại nói browser được gửi những request headers nào. Hai cấu hình này **khác mục đích**.

## 5. Conditional requests: 304, 412, 428

Một response GET có thể gắn validators:

~~~http
HTTP/1.1 200 OK
ETag: "v7"
Last-Modified: Wed, 01 Jan 2025 00:00:00 GMT
Content-Type: application/json

{"version":7,"content":"first"}
~~~

Client muốn kiểm tra cache:

~~~http
GET /api/doc HTTP/1.1
If-None-Match: "v7"
~~~

Nếu representation vẫn mang ETag `"v7"`, server trả `304 Not Modified`, thường không có response body; client tiếp tục dùng bản đã cache. Nếu giá trị khác, server trả nội dung mới, thường `200 OK`.

Header ngày tháng tương ứng:

~~~http
GET /api/doc HTTP/1.1
If-Modified-Since: Wed, 01 Jan 2025 00:00:00 GMT
~~~

Nếu tài nguyên chưa sửa kể từ ngày đó, server có thể trả 304. HTTP dates chỉ có **độ chính xác theo giây**; ETag thường phù hợp hơn cho những tài nguyên thay đổi nhiều lần trong một giây. `If-None-Match` được ưu tiên hơn `If-Modified-Since` khi cả hai cùng xuất hiện.

### ETag: strong/weak và dấu ngoặc kép

- Strong validator: `ETag: "v7"`. Dùng để so identity representation và làm precondition chống ghi đè.
- Weak validator: `ETag: W/"v7"`. Hữu ích cho cache validation theo ngữ nghĩa; **không dùng weak comparison để thỏa `If-Match`** vì `If-Match` yêu cầu strong comparison.
- Trong Spring, `ResponseEntity.ok().eTag("v7")` có thể tự thêm dấu ngoặc kép, nhưng trong test nên assert chính xác HTTP header `"v7"`.
- ETag phải thay đổi phù hợp với representation/version thực tế. Một ETag cố định cho dữ liệu thay đổi là bug của cache contract.

### Tránh lost update với If-Match

Hai client cùng đọc version 7; client A cập nhật thành version 8. Nếu B ghi đè dựa vào bản version 7, server nên từ chối:

~~~http
PUT /api/doc HTTP/1.1
If-Match: "v7"
Content-Type: application/json

{"content":"client B's edit"}
~~~

Khi ETag hiện tại đã là `"v8"`, response là `412 Precondition Failed` và không được thực hiện thay đổi. Nếu nghiệp vụ yêu cầu client **bắt buộc** dùng If-Match mà request thiếu header, có thể trả `428 Precondition Required`.

| Kịch bản | Kỳ vọng |
| --- | --- |
| GET không điều kiện | 200 + body + ETag/Last-Modified |
| GET + `If-None-Match` trùng | 304, body rỗng |
| GET + `If-None-Match` cũ | 200, body mới |
| GET + `If-Modified-Since` đủ mới | 304, body rỗng |
| PUT + `If-Match` đúng strong ETag | Ghi version mới; response theo API, ví dụ 204 |
| PUT + `If-Match` cũ/sai | 412, **không cập nhật state** |
| PUT thiếu `If-Match` mà API yêu cầu | 428, không cập nhật state |
| PUT + `If-Match: W/"v7"` | Không được chấp nhận như strong match |

Có hai phương án Spring MVC thường gặp:

- Trả `ResponseEntity.ok().eTag(...).lastModified(...).body(...)`, Spring kiểm tra conditional GET/HEAD dựa trên validators để tạo 304.
- Chủ động gọi `WebRequest.checkNotModified(etag, lastModified)` khi cần kiểm soát chi tiết luồng xử lý; phương thức có thể hỗ trợ 304 cho GET/HEAD và 412 cho request thao tác trạng thái.

Đối với cập nhật dữ liệu thật, kiểm tra `If-Match` phải **đồng bộ với thao tác ghi** (optimistic locking, compare-and-swap hoặc WHERE version = ? trong DB). Chỉ `if (currentVersion.equals(ifMatch))` rồi ghi ở hai bước tách biệt mà không có khóa/CAS vẫn có race condition.

## 6. Dự án mẫu chạy được: Spring Boot 3.x + MockMvc

Mẫu sau đưa cả ba nhóm chức năng vào một project, dùng Java 17+ và Maven. Controller sử dụng bộ nhớ nội bộ để demo, không cần database, browser hoặc mạng bên ngoài khi chạy test.

Cấu trúc:

~~~text
web-request-tests/
  pom.xml
  src/main/java/demo/WebRequestTestsApplication.java
  src/main/java/demo/ApiController.java
  src/test/java/demo/ApiControllerTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>web-request-tests</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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

Dự án dùng JUnit 5, Spring Test và AssertJ/Hamcrest thông qua `spring-boot-starter-test`; `MockMvc` đến từ Spring Test. Không thêm Spring Security trong demo để nhìn rõ CORS MVC thuần.

### 6.2. src/main/java/demo/WebRequestTestsApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebRequestTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebRequestTestsApplication.class, args);
    }
}
~~~

### 6.3. src/main/java/demo/ApiController.java

~~~java
package demo;

import java.time.Instant;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@CrossOrigin(
    origins = "https://ui.example",
    methods = {RequestMethod.GET, RequestMethod.POST, RequestMethod.PUT},
    allowedHeaders = {"Content-Type", "X-Trace-Id", "If-Match"},
    exposedHeaders = {"ETag"},
    maxAge = 3600
)
public class ApiController {
    private static final long INITIAL_TIME =
            Instant.parse("2025-01-01T00:00:00Z").toEpochMilli();

    private final AtomicReference<State> document =
            new AtomicReference<>(new State(7, "first", INITIAL_TIME));

    record State(long version, String content, long modifiedAt) {
        String etag() {
            return "\"v" + version + "\"";
        }
    }

    public record Metadata(String description) {}
    public record UploadReceipt(
            String filename, long bytes, String tag, String description) {}
    public record DocResponse(long version, String content) {}
    public record UpdateRequest(String content) {}

    // Giúp test độc lập thứ tự: mỗi test khởi động từ version 7.
    void reset() {
        document.set(new State(7, "first", INITIAL_TIME));
    }

    @PostMapping(
        path = "/api/upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<UploadReceipt> upload(
            @RequestPart("file") MultipartFile file,
            @RequestParam("tag") String tag,
            @RequestPart(value = "metadata", required = false)
                    Metadata metadata) {

        if (file.isEmpty() || tag.isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        if (!MediaType.TEXT_PLAIN_VALUE.equals(file.getContentType())) {
            return ResponseEntity.status(
                    HttpStatus.UNSUPPORTED_MEDIA_TYPE).build();
        }

        return ResponseEntity.ok(new UploadReceipt(
                file.getOriginalFilename(),
                file.getSize(),
                tag,
                metadata == null ? null : metadata.description()));
    }

    @GetMapping(
        path = "/api/doc",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<DocResponse> getDocument() {
        State current = document.get();

        return ResponseEntity.ok()
                .eTag(current.etag())
                .lastModified(current.modifiedAt())
                .body(new DocResponse(
                        current.version(), current.content()));
    }

    @PutMapping(
        path = "/api/doc",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Void> updateDocument(
            @RequestHeader(value = HttpHeaders.IF_MATCH, required = false)
                    String ifMatch,
            @RequestBody UpdateRequest request) {

        if (request == null || request.content() == null
                || request.content().isBlank()) {
            return ResponseEntity.badRequest().build();
        }
        if (ifMatch == null) {
            return ResponseEntity.status(
                    HttpStatus.PRECONDITION_REQUIRED).build();
        }

        while (true) {
            State current = document.get();

            // Chỉ strong ETag chính xác mới được cập nhật.
            if (!current.etag().equals(ifMatch)) {
                return ResponseEntity.status(
                        HttpStatus.PRECONDITION_FAILED).build();
            }

            State next = new State(
                    current.version() + 1,
                    request.content(),
                    Instant.now().toEpochMilli());

            // CAS bảo đảm version không bị ghi đè qua hai request đua nhau.
            if (document.compareAndSet(current, next)) {
                return ResponseEntity.noContent().build();
            }
        }
    }
}
~~~

**Vì sao logic này dễ test?**

- File upload không cần ghi filesystem; có thể kiểm tra file name, size, tag, JSON part và status. Trong sản phẩm thật, phải sanitize filename, kiểm tra MIME bằng nội dung nếu cần và áp dụng giới hạn kích thước/storage.
- `@CrossOrigin` giới hạn chính xác origin demo; các request đến từ browser khác phải qua CORS processing.
- GET có strong `ETag` và `Last-Modified`; Spring MVC xử lý conditional requests khi trả `ResponseEntity`.
- PUT bắt buộc `If-Match`, dùng CAS thay vì check-and-set không nguyên tử; test có thể xác nhận state giữ nguyên sau 412.
- `reset()` chỉ hỗ trợ demo test in-memory. App production nên quản lý dữ liệu/version bằng persistence có optimistic locking.

### 6.4. src/test/java/demo/ApiControllerTest.java

~~~java
package demo;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(ApiController.class)
class ApiControllerTest {
    @Autowired MockMvc mvc;
    @Autowired ApiController controller;

    private static final String ALLOWED = "https://ui.example";
    private static final String DENIED = "https://evil.example";

    @BeforeEach
    void resetState() {
        controller.reset();
    }

    private MockMultipartFile textFile() {
        return new MockMultipartFile(
                "file", "notes.txt", MediaType.TEXT_PLAIN_VALUE,
                "hello".getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void multipartFileAndFormField() throws Exception {
        mvc.perform(multipart("/api/upload")
                .file(textFile())
                .param("tag", "quarterly"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.filename").value("notes.txt"))
            .andExpect(jsonPath("$.bytes").value(5))
            .andExpect(jsonPath("$.tag").value("quarterly"))
            .andExpect(jsonPath("$.description").doesNotExist());
    }

    @Test
    void multipartWithJsonPart() throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata", "", MediaType.APPLICATION_JSON_VALUE,
                "{\"description\":\"report\"}"
                        .getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/upload")
                .file(textFile())
                .file(metadata)
                .param("tag", "quarterly"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.description").value("report"));
    }

    @Test
    void missingFileReturns400() throws Exception {
        mvc.perform(multipart("/api/upload")
                .param("tag", "quarterly"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void emptyFileReturns400() throws Exception {
        MockMultipartFile empty = new MockMultipartFile(
                "file", "empty.txt", MediaType.TEXT_PLAIN_VALUE,
                new byte[0]);

        mvc.perform(multipart("/api/upload")
                .file(empty)
                .param("tag", "quarterly"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void wrongPartContentTypeReturns415() throws Exception {
        MockMultipartFile binary = new MockMultipartFile(
                "file", "raw.bin", "application/octet-stream",
                new byte[]{1, 2, 3});

        mvc.perform(multipart("/api/upload")
                .file(binary)
                .param("tag", "quarterly"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void corsPreflightAllowed() throws Exception {
        mvc.perform(options("/api/upload")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "content-type,x-trace-id"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                    containsString("POST")))
            .andExpect(header().exists(HttpHeaders.VARY));
    }

    @Test
    void corsPreflightDeniedOrigin() throws Exception {
        mvc.perform(options("/api/upload")
                .header(HttpHeaders.ORIGIN, DENIED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
            .andExpect(status().isForbidden());
    }

    @Test
    void corsPreflightDeniedHeader() throws Exception {
        mvc.perform(options("/api/upload")
                .header(HttpHeaders.ORIGIN, ALLOWED)
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
                .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                        "x-not-allowed"))
            .andExpect(status().isForbidden());
    }

    @Test
    void actualCorsRequestCarriesAllowOrigin() throws Exception {
        mvc.perform(get("/api/doc")
                .header(HttpHeaders.ORIGIN, ALLOWED))
            .andExpect(status().isOk())
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, ALLOWED))
            .andExpect(header().string(
                    HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS, "ETag"));
    }

    @Test
    void actualCorsRequestDeniedOrigin() throws Exception {
        mvc.perform(get("/api/doc")
                .header(HttpHeaders.ORIGIN, DENIED))
            .andExpect(status().isForbidden());
    }

    @Test
    void unconditionalGetReturnsValidators() throws Exception {
        mvc.perform(get("/api/doc"))
            .andExpect(status().isOk())
            .andExpect(header().string(HttpHeaders.ETAG, "\"v7\""))
            .andExpect(header().exists(HttpHeaders.LAST_MODIFIED))
            .andExpect(jsonPath("$.version").value(7))
            .andExpect(jsonPath("$.content").value("first"));
    }

    @Test
    void matchingIfNoneMatchReturns304WithoutBody() throws Exception {
        mvc.perform(get("/api/doc")
                .header(HttpHeaders.IF_NONE_MATCH, "\"v7\""))
            .andExpect(status().isNotModified())
            .andExpect(header().string(HttpHeaders.ETAG, "\"v7\""))
            .andExpect(content().string(""));
    }

    @Test
    void staleIfNoneMatchReturns200WithBody() throws Exception {
        mvc.perform(get("/api/doc")
                .header(HttpHeaders.IF_NONE_MATCH, "\"v6\""))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void ifModifiedSinceCanReturn304() throws Exception {
        mvc.perform(get("/api/doc")
                .header(HttpHeaders.IF_MODIFIED_SINCE,
                        "Wed, 01 Jan 2025 00:00:00 GMT"))
            .andExpect(status().isNotModified())
            .andExpect(content().string(""));
    }

    @Test
    void missingIfMatchReturns428() throws Exception {
        mvc.perform(put("/api/doc")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"edited\"}"))
            .andExpect(status().isPreconditionRequired());

        mvc.perform(get("/api/doc"))
            .andExpect(jsonPath("$.version").value(7));
    }

    @Test
    void staleIfMatchReturns412WithoutMutation() throws Exception {
        mvc.perform(put("/api/doc")
                .header(HttpHeaders.IF_MATCH, "\"v6\"")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"edited\"}"))
            .andExpect(status().isPreconditionFailed());

        mvc.perform(get("/api/doc"))
            .andExpect(jsonPath("$.content").value("first"))
            .andExpect(header().string(HttpHeaders.ETAG, "\"v7\""));
    }

    @Test
    void weakIfMatchDoesNotPassStrongComparison() throws Exception {
        mvc.perform(put("/api/doc")
                .header(HttpHeaders.IF_MATCH, "W/\"v7\"")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"edited\"}"))
            .andExpect(status().isPreconditionFailed());
    }

    @Test
    void matchingIfMatchUpdatesVersion() throws Exception {
        mvc.perform(put("/api/doc")
                .header(HttpHeaders.IF_MATCH, "\"v7\"")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"content\":\"edited\"}"))
            .andExpect(status().isNoContent());

        mvc.perform(get("/api/doc"))
            .andExpect(status().isOk())
            .andExpect(header().string(HttpHeaders.ETAG, "\"v8\""))
            .andExpect(jsonPath("$.version").value(8))
            .andExpect(jsonPath("$.content").value("edited"));
    }
}
~~~

Từng test chạy độc lập với version 7 nhờ `@BeforeEach`. Tests không dùng thứ tự phương thức và không cần sleep/clock giả để so trạng thái ngày giờ.

**Lưu ý về 428:** `MockMvcResultMatchers.status().isPreconditionRequired()` có sẵn trong các phiên bản Spring Test tương ứng với HTTP status 428; nếu dùng bản Spring khác, có thể thay bằng `status().is(428)`. Trong demo Spring Boot 3.5, API status này được Spring Test hỗ trợ.

### 6.5. Chạy test

Ở thư mục dự án, với JDK 17+ và Maven:

~~~bash
mvn test
~~~

Điều kiện pass: các method test nhận status và headers đúng như assertions; Maven hoàn tất với `BUILD SUCCESS` và failures/errors bằng 0. Kết quả số lượng test phụ thuộc file test bạn lưu; ví dụ trên có 18 phương thức `@Test`. Đây là **kết quả kỳ vọng khi code được cấu hình như mô tả**, không phải bản ghi log đã chạy thực tế.

Để kiểm tra thông điệp lỗi khi test hỏng, xem `target/surefire-reports`, output MVC `MockMvcResultHandlers.print()` trong test cần debug hoặc kiểm tra test stack trace. Không sửa assert theo giá trị tình cờ chỉ để làm test xanh; xác minh API contract trước.

## 7. Những khác biệt khiến test xanh giả

### 7.1. Mock multipart không kiểm tra boundary/parser

Bộ dựng `MockMultipartFile` tạo file part in-memory trực tiếp, không kiểm chứng quá trình HTTP parser tách bytes từ boundary. Vì vậy test unit/slice có thể pass dù upload thật thất bại vì:

- Multipart resolver/container không được bật hoặc cấu hình khác.
- `max-file-size`/`max-request-size` bị vượt.
- Boundary sai hoặc không có, content type tổng thể sai.
- Filename encoding và binary payload ngoài các trường hợp thông thường.

Cách bù: thêm ít nhất một integration test dùng HTTP client thật tới `RANDOM_PORT`, gửi multipart thực và assert response; thêm case vượt giới hạn để xác nhận HTTP status/exception mapping. Các giới hạn parser có thể được áp trước khi controller chạy.

### 7.2. CORS là browser enforcement

`MockMvc` có thể khẳng định Spring đã phát `Access-Control-Allow-Origin` hoặc từ chối preflight; nó **không phải browser**. Cần test trên trình duyệt hoặc automation thực nếu tích hợp cookie, redirect, domain/cổng khác, SameSite, `credentials: "include"`, Service Worker, proxies hoặc security filters. Một request gửi bằng `curl` từ origin cấm vẫn có thể gửi được ở cấp HTTP; browser mới thực thi CORS để ngăn JS truy cập.

### 7.3. @WebMvcTest có phạm vi hẹp

Nếu CORS được cấu hình bằng `WebMvcConfigurer` hoặc `CorsFilter` bên ngoài controller slice, test `@WebMvcTest(ApiController.class)` cần import đúng config. Nếu có Spring Security, filters có thể từ chối preflight trước khi đến MVC; dùng `@Import(SecurityConfig.class)` khi phù hợp hoặc `@SpringBootTest + @AutoConfigureMockMvc`. Với security-enabled tests, setup CSRF và user mocks chỉ khi đúng contract. Đừng dùng `@AutoConfigureMockMvc(addFilters=false)` để đánh giá hành vi CORS/security production rồi kết luận là đủ.

### 7.4. Conditional GET không giống kiểm tra cạnh tranh ghi

`GET If-None-Match` tạo 304 giúp tiết kiệm băng thông nhưng không chứng minh xử lý `PUT If-Match` đúng dưới concurrent writes. Với DB, tích hợp optimistic locking version column và test hai cập nhật cạnh tranh; bảo đảm request thua không làm đổi state. ETag cần được thay khi representation thay đổi, và cache-private/public cần phù hợp dữ liệu người dùng.

### 7.5. Không kiểm tra toàn bộ headers/body

Test chỉ `status().isOk()` không đủ cho protocol semantics. Cần kiểm tra CORS response headers, ETag/Last-Modified, empty body 304, JSON part binding và state không thay đổi sau 412/428. Status 200 cho multipart không chứng minh filename/MIME/data chính xác.

## 8. Kiểm thử thêm: method, headers và cache behavior

### Multipart bằng HTTP method khác

Theo mặc định `multipart("/api/upload")` tạo POST. Nếu endpoint chấp nhận PUT/PATCH multipart, chọn method tường minh và xác minh request mapping:

~~~java
mvc.perform(multipart("/api/upload")
        .file(textFile())
        .with(request -> {
            request.setMethod("PUT");
            return request;
        }))
    .andExpect(status().isMethodNotAllowed());
~~~

Với controller demo chỉ khai báo `@PostMapping`, `PUT` hợp lệ về mặt cú pháp request mock nhưng đường dẫn không có method PUT, nên kỳ vọng 405. Nếu nghiệp vụ cho phép PUT multipart, viết `@PutMapping` tương ứng và đổi expected status. Việc parser của container có hỗ trợ PUT multipart thật hay không vẫn phải kiểm tra end-to-end theo cấu hình Servlet/framework.

### CORS preflight và custom headers

Nếu frontend gửi `X-Trace-Id`, preflight phải liệt kê `x-trace-id` trong `Access-Control-Request-Headers`. Server chỉ phản hồi `Access-Control-Allow-Headers` cho những header được phép. Với `@CrossOrigin(allowedHeaders=...)`, test nên kiểm tra cả header được chấp nhận và header bị từ chối.

Nếu cần đọc `ETag` qua JavaScript:

~~~javascript
const response = await fetch("https://api.example/api/doc", {
    mode: "cors"
});
const etag = response.headers.get("ETag");
console.log(etag);
~~~

Trong demo `@CrossOrigin(exposedHeaders={"ETag"})` cho phép browser JS đọc ETag khi frontend chạy từ origin `https://ui.example`. Không có exposed header thì JS có thể không đọc được ETag dù DevTools vẫn nhìn thấy response header.

### Conditional headers kết hợp

Ưu tiên test `If-None-Match` khi gửi cả ETag và date. Theo HTTP semantics, `If-None-Match` có precedence hơn `If-Modified-Since`; đừng kết luận server sai khi nó bỏ qua date trong trường hợp có ETag. Thêm các case header yếu, malformed dates, HEAD, clock precision và proxy caching nếu API của bạn phụ thuộc.

### ETag được định dạng như thế nào?

`ETag: "v7"` là một header bao gồm dấu ngoặc kép; `If-None-Match: v7` thiếu quotes không tương đương một entity-tag hợp lệ. Nên khởi đầu test bằng giá trị header thật được HTTP client nhận từ GET, rồi dùng chính giá trị đó ở request kế tiếp.

## 9. Hướng kiểm thử với Spring WebFlux và WebTestClient

Nếu endpoint thuộc **Spring WebFlux** thay vì Spring MVC, dùng `@WebFluxTest` hoặc `WebTestClient` với mock/server binding phù hợp:

~~~java
webTestClient.get()
        .uri("/api/doc")
        .header(HttpHeaders.IF_NONE_MATCH, "\"v7\"")
        .exchange()
        .expectStatus().isNotModified()
        .expectBody().isEmpty();
~~~

Kiểm thử CORS preflight vẫn là `OPTIONS` với `Origin`, `Access-Control-Request-Method` và `Access-Control-Request-Headers`:

~~~java
webTestClient.options()
        .uri("/api/upload")
        .header(HttpHeaders.ORIGIN, "https://ui.example")
        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://ui.example");
~~~

Đây là **snippets tích hợp**: `webTestClient` phải là bean/test fixture trỏ tới một WebFlux controller có cấu hình tương ứng. CORS và conditional behavior về nguyên tắc tương tự, nhưng server exchange/buffering/multipart abstractions khác MVC.

Để tạo multipart request WebTestClient, dùng `MultipartBodyBuilder`:

~~~java
MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("tag", "quarterly");
builder.part("file", new ByteArrayResource(
        "hello".getBytes(StandardCharsets.UTF_8)) {
    @Override
    public String getFilename() {
        return "notes.txt";
    }
}).contentType(MediaType.TEXT_PLAIN);

webTestClient.post()
        .uri("/api/upload")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(BodyInserters.fromMultipartData(builder.build()))
        .exchange()
        .expectStatus().isOk();
~~~

Snippet này cần `org.springframework.util.MultiValueMap` qua builder, `org.springframework.core.io.ByteArrayResource` và `BodyInserters`, cùng endpoint thật phù hợp. Khi test WebFlux handler, đối tượng inbound file có thể là `FilePart` thay vì Servlet `MultipartFile`. Không copy nguyên controller Servlet `MultipartFile` sang WebFlux rồi giả định đúng.

## 10. Checklist kiểm thử trước khi release

| Nhóm | Trường hợp tối thiểu | Chứng cứ |
| --- | --- | --- |
| Multipart | File đúng tên/type/content, form field và JSON part | Status + các field binding/processed đúng |
| Multipart errors | Thiếu file, rỗng, sai MIME, JSON part hỏng | 400/415 theo API |
| Multipart integration | Boundary, parser, file vượt size, Unicode filename, storage | HTTP test qua server thật |
| CORS preflight | Origin/method/header được phép | OPTIONS + CORS response headers |
| CORS rejection | Origin/header/method bị từ chối | OPTIONS rejected, không vô tình mở wildcard |
| CORS actual | GET/POST từ origin được phép | Business response + Allow-Origin |
| Credentials/Security | Cookie/session/CSRF/auth filters | Filter chain và browser integration |
| Conditional GET | Không header, ETag trùng/cũ, Last-Modified | 200 / 304 + ETag + body đúng |
| Conditional mutation | If-Match đúng/cũ/thiếu/weak | 204 / 412 / 428, state/version chuẩn |
| Concurrency | Hai request cập nhật cùng version | Chỉ một cập nhật thành công |
| Cache/proxy | Vary, Cache-Control, CDN/shared cache | Không trả dữ liệu của origin/user khác |

**Quy tắc:** test **request** (method/headers/parts), test **response** (status/headers/body), và test **state** sau request. Với multipart, thêm parser integration; với CORS, thêm browser/security validation; với conditional write, thêm atomic version/concurrency validation.

## 11. Tài liệu tham khảo

- Spring Framework — MockMvc: https://docs.spring.io/spring-framework/reference/testing/mockmvc.html
- Spring Framework — Performing Requests, Multipart: https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/hamcrest/requests.html
- Spring Framework — Defining Expectations: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/expectations.html
- Spring Framework — CORS (MVC): https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Framework — HTTP Caching (MVC): https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — WebFlux HTTP Caching: https://docs.spring.io/spring-framework/reference/web/webflux/caching.html
- RFC 9110 — HTTP Semantics, conditional requests: https://www.rfc-editor.org/rfc/rfc9110.html
