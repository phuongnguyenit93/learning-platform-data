# Nhận MultipartFile, Part và kết hợp tệp với dữ liệu JSON trong Spring MVC

## 1. Mục tiêu và bối cảnh

Nhiều API nhận không chỉ JSON hoặc chỉ file, mà nhận **một file cùng metadata có cấu trúc** trong cùng HTTP request. Ví dụ một client muốn tạo tài liệu với thuộc tính `title`, `category` và file `note.txt`:

- `title`, `category`: dữ liệu nghiệp vụ được kiểm tra bằng Bean Validation.
- `file`: bytes tải lên, filename và Content-Type do client cung cấp.
- Server cần xử lý metadata và file cùng một thao tác, đồng thời quản lý bảo mật/giới hạn kích thước.

Trong **Spring Web MVC trên Servlet stack**, có ba kiểu tham số phổ biến:

1. `MultipartFile`: abstraction của Spring dùng để đọc metadata và nội dung file part.
2. `jakarta.servlet.http.Part`: abstraction gốc của Jakarta Servlet cho từng multipart part, không phụ thuộc kiểu `MultipartFile`.
3. `@RequestPart` với DTO Java: dùng `HttpMessageConverter` để giải mã **nội dung của một part** như JSON thành DTO.

Sau bài này, bạn có thể giải thích HTTP multipart boundaries/headers, phân biệt `@RequestParam`, `@ModelAttribute`, `@RequestPart` và `@RequestBody`, triển khai API nhận JSON + file, viết tests bằng MockMvc, chọn API lưu file an toàn, và xử lý validation/security/limits.

Ví dụ chính dùng **Java 17, Spring Boot 3.3.5, Spring Framework 6.1.x** và `spring-boot-starter-web`. Các ví dụ code Spring là Servlet MVC, không áp dụng nguyên mẫu cho WebFlux (`FilePart`/reactive stack khác).

## 2. multipart/form-data là gì?

HTTP request có thể có một body chứa **nhiều part**. Mỗi part có header `Content-Disposition`, có thể có `Content-Type` và có payload riêng. Envelope bên ngoài mang media type `multipart/form-data` và `boundary`:

```http
POST /api/uploads/mixed HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=DemoBoundary
Accept: application/json

--DemoBoundary
Content-Disposition: form-data; name="metadata"
Content-Type: application/json; charset=UTF-8

{"title":"Ghi chú","category":"notes"}
--DemoBoundary
Content-Disposition: form-data; name="file"; filename="note.txt"
Content-Type: text/plain

ABC
--DemoBoundary--
```

Đây là **biểu diễn wire format minh họa**: thực tế HTTP multipart dùng `CRLF` để phân tách headers/body và boundary, còn file bytes có thể không phải text. Khi dùng `curl -F` hoặc browser `FormData`, client tự chọn boundary, tạo headers và encode body. **Không tự ghi header `Content-Type: multipart/form-data` không có boundary** nếu thư viện client đã tự dựng multipart; header sai có thể làm server không parse được.

Phân biệt hai tầng media type:

- **Outer** `Content-Type: multipart/form-data; boundary=...` báo body là multipart.
- **Part `metadata`** có `Content-Type: application/json`; Jackson converter có thể đọc thành `UploadMetadata`.
- **Part `file`** có `Content-Type: text/plain` hoặc `application/octet-stream`; với `MultipartFile`/`Part` thường server nhận bytes và tự quyết định kiểm tra, không deserialize sang JSON DTO.
- `Content-Disposition: form-data; name="metadata"` định danh tên part. Tên phải khớp `@RequestPart("metadata")`; filename chỉ là metadata client cung cấp, không đáng tin.

Một file và metadata JSON nằm trong **một request**, nhưng không có nghĩa việc lưu file + lưu database đã là một transaction nguyên tử. Nếu bước ghi file thành công nhưng ghi database lỗi, cần cleanup/compensation hoặc workflow đáng tin để không để lại orphan file.

### Multipart không phải JSON chứa một file

Một request JSON:

```json
{"title":"Ghi chú","fileBase64":"QUJD"}
```

khác với multipart. Base64 làm payload phình ra và phải giải mã; dùng multipart phù hợp hơn khi cần truyền file bytes và text/JSON parts. Nếu API nhỏ, chỉ nhận chuỗi, JSON thuần vẫn có thể đủ. Việc chọn multipart nên dựa trên **hợp đồng HTTP** và cách client gửi dữ liệu.

## 3. Từ Servlet part đến đối số controller

Trong Spring MVC 6.x, `StandardServletMultipartResolver` tích hợp parser `jakarta.servlet.http.Part` của Servlet container vào `DispatcherServlet`. Spring Boot MVC thường tự đăng ký resolver và `MultipartConfigElement`, nên controller không tự khởi tạo multipart parser. Cơ chế này được khai thác ở đây để phân biệt **file part** với **JSON metadata part**; cấu hình resolver, bean name `multipartResolver`, eager/lazy parsing và chính sách Servlet container được giải thích chuyên sâu ở bài về `MultipartResolver` của chương.

```text
POST multipart/form-data
       |
Servlet container -> parsed Parts / temporary storage
       |
Spring MVC MultipartResolver
       |
       +-- "file"     -> MultipartFile hoặc Servlet Part
       |
       +-- "metadata" (Content-Type: application/json)
                        -> HttpMessageConverter -> UploadMetadata DTO
                        -> @Valid / Bean Validation
       |
Controller -> service -> HTTP response
```

Giá trị trả về không được bảo đảm an toàn chỉ vì parser thành công: controller vẫn cần validation, quyền truy cập và lưu file vào storage riêng. Với JSON part, **`Content-Type` của từng part**, không chỉ outer `multipart/form-data`, quyết định converter có thể đọc DTO.

### Cấu hình cần có để ví dụ chạy

Ví dụ Maven ở mục 7 có `application.properties` giới hạn multipart ngay tại Servlet configuration:

```properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=5MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.strict-servlet-compliance=true
```

`max-file-size` áp dụng từng file; `max-request-size` áp dụng toàn multipart envelope, gồm metadata và các part khác. `file-size-threshold` chỉ điều khiển ngưỡng dùng bộ nhớ/đĩa tạm, không phải quota lâu dài. `strict-servlet-compliance` giới hạn resolver vào `multipart/form-data`, không xác minh nội dung file. Nếu không chủ động đặt `resolve-lazily`, thông thường parse sớm theo mặc định; bật lazy có thể đổi **thời điểm lỗi parsing**, không tăng size limit.

Giới hạn proxy, Servlet container và bộ nhớ/đĩa vẫn tác động độc lập; `MockMvc` không mô phỏng toàn bộ HTTP multipart parser thật. Các bài kiểm thử giới hạn và bảo vệ upload cần dùng server/container thực trong môi trường kiểm soát.

## 4. MultipartFile: API chính của Spring MVC

`org.springframework.web.multipart.MultipartFile` cung cấp:

| Method | Ý nghĩa |
| --- | --- |
| `getName()` | Tên form field/part, ví dụ `file` |
| `getOriginalFilename()` | Filename do client khai báo; **không đáng tin** |
| `getContentType()` | MIME type do client khai báo; có thể null hoặc giả mạo |
| `isEmpty()` | Tệp không được chọn hoặc có zero bytes, tùy request |
| `getSize()` | Kích thước nội dung theo bytes |
| `getBytes()` | Đọc toàn bộ nội dung vào `byte[]` — tránh với file lớn |
| `getInputStream()` | Đọc nội dung dạng stream; nên đóng sau khi dùng |
| `transferTo(File/Path)` | Chuyển nội dung sang file đích theo contract/implementation cụ thể |

Khi handler nhận:

```java
@PostMapping(path = "/upload",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public String upload(@RequestParam("file") MultipartFile file) {
    // ...
}
```

đây là method minh họa, cần đặt trong controller với imports. `@RequestParam` có thể dùng với `MultipartFile` và form fields. `@RequestPart("file") MultipartFile` cũng hợp lệ. Đối với tệp đơn giản, cả hai thường giải quyết cùng part file; ý nghĩa của `@RequestPart` trở nên quan trọng hơn khi **part chứa JSON cần converter đọc thành DTO**.

### Nội dung MultipartFile chỉ có thời hạn request

File bytes có thể được giữ trong RAM hoặc temporary file do container quản lý. Sau khi request kết thúc, dữ liệu tạm có thể bị xóa. Vì vậy:

- Nếu cần sử dụng sau request, chuyển nội dung vào storage do ứng dụng kiểm soát trong lúc request còn hiệu lực.
- Không giữ `MultipartFile` trong singleton field hoặc đưa object này cho async job rồi trông đợi stream vẫn còn mở.
- Đừng đồng nhất `getOriginalFilename()` với tên file lưu trên disk. Filename có thể chứa slash, backslash, dấu chấm, Unicode khác thường hoặc các chuỗi path traversal như `../../secret.txt`.
- Với file lớn, `getBytes()` có thể tạo áp lực bộ nhớ; dùng stream hoặc cơ chế streaming/upload chuyên dụng khi phù hợp.
- Không tự tin `getContentType()` phản ánh nội dung thật; đây là metadata của client.

## 5. jakarta.servlet.http.Part: API thấp hơn của Servlet

`jakarta.servlet.http.Part` là abstraction chuẩn của Servlet API. Các thao tác tiêu biểu:

```java
String name = part.getName();
String filename = part.getSubmittedFileName();
String contentType = part.getContentType();
long size = part.getSize();
try (InputStream in = part.getInputStream()) {
    // Đọc bytes cần thiết.
}
```

Đoạn này chỉ là snippet, yêu cầu import `java.io.InputStream` và tham số `Part part` có sẵn. Ngoài các method trên, `Part` có `getHeader(s)`, `write(String)` và `delete()`. `write`/`delete` tương tác với cơ chế multipart của container; chú ý quy tắc storage/location tương đối và portability.

Trong controller:

```java
@PostMapping(path = "/part",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public String inspect(@RequestPart("file") Part file) {
    return file.getName() + ":" + file.getSize();
}
```

Method chỉ minh họa, nếu ở `@RestController` thì chuỗi là response body; nếu ở `@Controller` mà không có `@ResponseBody` thì chuỗi có thể được hiểu là view name. `Part` hữu ích khi cần API chuẩn Servlet hoặc truy cập headers của part; `MultipartFile` tiện hơn khi dự án thuần Spring MVC.

### MultipartFile hay Part?

| Nhu cầu | Ưu tiên thường hợp lý |
| --- | --- |
| Đa số API upload Spring MVC | `MultipartFile` |
| Muốn API Servlet không phụ thuộc Spring multipart abstraction | `jakarta.servlet.http.Part` |
| Xem headers raw của part | `Part` hoặc request multipart headers API |
| Dữ liệu file vài MB, cần stream | Cả hai có input stream |
| Upload metadata JSON thành DTO | **`@RequestPart("metadata") UploadMetadata`** |
| Cần nhận nhiều file cùng tên field | `List<MultipartFile>` hoặc array |
| Form HTML có fields text + file | `@ModelAttribute` hoặc `@RequestParam` cho fields, `MultipartFile` cho file |

Không cần biến tất cả các `Part` thành `MultipartFile` bằng cách copy bytes sang RAM để “thống nhất”. Chọn một abstraction rõ ràng theo contract/controller.

## 6. @RequestPart để ghép JSON metadata và file

Khi request multipart có JSON part `metadata` và file part `file`:

```java
@PostMapping(path = "/mixed",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> upload(
        @Valid @RequestPart("metadata") UploadMetadata metadata,
        @RequestPart("file") MultipartFile file) {
    // ...
}
```

`@RequestPart("metadata") UploadMetadata` khác `@RequestParam String metadata`:

- `@RequestPart` cho DTO sử dụng `HttpMessageConverter` đọc **nội dung part** dựa trên **Content-Type của part**, tương tự `@RequestBody` với nguyên request body JSON.
- `@RequestParam("metadata") String` nhận text/raw parameter; để thành DTO thường phải tự parse JSON, không có đường converter chuẩn như `@RequestPart`.
- `@RequestPart("file") MultipartFile` nhận file trực tiếp. File bytes không bị Jackson tự đọc thành DTO.
- `@Valid` trên metadata khiến Spring kiểm tra các constraint sau khi converter deserialize; nếu validation fail mà không có `BindingResult` xử lý, thường nhận `400 Bad Request`.
- `consumes="multipart/form-data"` áp dụng cho **outer request**, còn JSON part phải có `Content-Type: application/json`. Một client gửi JSON string nhưng part bị gắn `text/plain` có thể gây `415 Unsupported Media Type` đối với DTO.

Đối chiếu:

| Annotation | Thường dùng để đọc | Cơ chế |
| --- | --- | --- |
| `@RequestBody Dto` | Một request có body JSON | JSON converter trên whole request |
| `@RequestPart("metadata") Dto` | Part có nội dung JSON của multipart | JSON converter **trên riêng part** |
| `@RequestPart("file") MultipartFile` | Part chứa tệp | Multipart argument handling |
| `@RequestParam("file") MultipartFile` | Form file field | Multipart argument handling |
| `@RequestParam String title` | Form field/query parameter | Conversion/binding của parameters |
| `@ModelAttribute UploadForm` | Các form fields và file properties | `WebDataBinder` property/constructor binding |

**Không đặt `@RequestBody UploadMetadata` chung với `@RequestPart MultipartFile` rồi mong JSON converter đọc được metadata từ một khối JSON riêng trong whole multipart.** Request body tổng thể là multipart envelope, không phải một JSON document. Phải dùng `@RequestPart` cho JSON part.

## 7. Ví dụ Spring Boot đầy đủ chạy được: JSON + file + Servlet Part

Ví dụ nhận một text file nhỏ và JSON metadata. Server trả JSON receipt gồm `title`, số byte đọc thực tế và SHA-256 digest (để minh họa xử lý stream, **không phải một cơ chế antivirus**). Có endpoint riêng minh họa `Part` và endpoint form đơn giản với `@RequestParam`.

### 7.1. Cây dự án Maven

```text
mvc-upload-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/upload/
    │   │   ├── UploadApplication.java
    │   │   └── UploadController.java
    │   └── resources/
    │       └── application.properties
    └── test/java/demo/upload/
        └── UploadControllerTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>mvc-upload-demo</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
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
```

**`src/main/resources/application.properties`**

```properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=5MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.strict-servlet-compliance=true
```

Với demo, tệp lớn quá 2 MB sẽ bị từ chối qua multipart limits trước hoặc trong quá trình giải tham số. HTTP status/body cụ thể của lỗi upload size có thể phụ thuộc handler/container; cần test và có exception advice cho hợp đồng production nếu muốn response thống nhất.

**`src/main/java/demo/upload/UploadApplication.java`**

```java
package demo.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UploadApplication {
    public static void main(String[] args) {
        SpringApplication.run(UploadApplication.class, args);
    }
}
```

### 7.2. Controller có ba dạng nhận dữ liệu

**`src/main/java/demo/upload/UploadController.java`**

```java
package demo.upload;

import jakarta.servlet.http.Part;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    public record UploadMetadata(
            @NotBlank @Size(max = 80) String title,
            @NotBlank String category) {}

    public record UploadReceipt(
            String title,
            String category,
            long byteCount,
            String sha256) {}

    @PostMapping(
            path = "/mixed",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<UploadReceipt> mixed(
            @Valid @RequestPart("metadata") UploadMetadata metadata,
            @RequestPart("file") MultipartFile file)
            throws IOException, NoSuchAlgorithmException {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "File is empty");
        }
        // Chỉ là demo kiểm tra declared MIME; không thay content sniffing.
        if (!MediaType.TEXT_PLAIN_VALUE.equals(file.getContentType())) {
            throw new ResponseStatusException(
                    HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                    "Only declared text/plain files are accepted");
        }

        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        long size = 0;
        try (InputStream input = file.getInputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                digest.update(buffer, 0, count);
                size += count;
            }
        }

        UploadReceipt receipt = new UploadReceipt(
                metadata.title(), metadata.category(),
                size, HexFormat.of().formatHex(digest.digest()));

        return ResponseEntity.status(HttpStatus.CREATED).body(receipt);
    }

    @PostMapping(
            path = "/part",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Long> servletPart(
            @RequestPart("file") Part part) throws IOException {

        long count;
        try (InputStream input = part.getInputStream()) {
            count = input.transferTo(OutputStream.nullOutputStream());
        }
        return Map.of("byteCount", count);
    }

    @PostMapping(
            path = "/simple",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> simple(
            @RequestParam("description") String description,
            @RequestParam("file") MultipartFile file) {

        if (description.isBlank() || file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid upload");
        }
        return Map.of(
                "description", description,
                "byteCount", file.getSize());
    }
}
```

**Kiểm tra nghĩa của từng phần:**

1. `UploadMetadata` là record Java 17; Jackson đọc JSON part có `Content-Type: application/json` thành record.
2. `@Valid` kích hoạt `@NotBlank` và `@Size` trước khi controller làm xử lý nghiệp vụ. Nếu thiếu `title` hoặc `category`, thường trả `400` do `MethodArgumentNotValidException`.
3. `MultipartFile` cung cấp stream bytes và metadata. Ví dụ chỉ chấp nhận declared `text/plain` để có tình huống `415` minh họa; kiểm tra này **không bảo vệ** chống giả mạo MIME hay nội dung độc hại.
4. `MessageDigest SHA-256` đọc file theo các khối 8192 byte và tính digest, không gọi `getBytes()`. Tuy nhiên Servlet container vẫn có cơ chế buffer/file tạm; việc đọc stream ở controller không có nghĩa request luôn end-to-end streaming.
5. `byteCount` là số byte đã đọc thực, không phải số ký tự Unicode hay `String.length()`.
6. `servletPart` nhận `jakarta.servlet.http.Part`, dùng Java `InputStream.transferTo(OutputStream.nullOutputStream())` để đếm bytes trong stream. Đó là cách minh họa Servlet Part, **không ghi dữ liệu vĩnh viễn**.
7. `simple` minh họa form field `description` và tệp `file` qua `@RequestParam`. Không cần DTO JSON part cho trường hợp text field đơn giản.
8. Controller không dùng `getOriginalFilename()` làm path, không lưu file lên server. Đây là quyết định có chủ đích để tránh ví dụ bảo mật kém; mục 11 trình bày quy tắc lưu thật.

Một điểm kiểm tra compile: `InputStream.transferTo(OutputStream)` có từ Java 9; `OutputStream.nullOutputStream()` từ Java 11; `HexFormat` từ Java 17. Với Java 17, những API này hợp lệ.

### 7.3. Chạy project và tạo file mẫu

Ở thư mục `mvc-upload-demo` có `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Hai lệnh chạy **tuần tự**. JDK cần là 17+ và Maven hoạt động. Sau khi chạy app trên `localhost:8080`, tạo tệp test:

```bash
printf 'ABC' > note.txt
```

Lệnh này dùng shell Bash hoặc tương đương, và ghi đúng ba bytes ASCII `A`, `B`, `C` **không có newline**. Trên PowerShell, có thể tạo bằng byte array thay vì `Set-Content` (vì công cụ đó có thể đổi encoding/thêm newline).

Upload JSON + file bằng curl:

```bash
curl -i -X POST 'http://localhost:8080/api/uploads/mixed' \
  -H 'Accept: application/json' \
  -F 'metadata={"title":"Ghi chú","category":"notes"};type=application/json' \
  -F 'file=@note.txt;type=text/plain'
```

Đường curl `-F` tự tạo `multipart/form-data` và boundary; **không cần** thêm `-H 'Content-Type: multipart/form-data'` thủ công. `type=application/json` ở metadata part là chi tiết quyết định để JSON converter đọc record.

Phần response chính dự kiến:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{"title":"Ghi chú","category":"notes","byteCount":3,"sha256":"b5d4045c3f466fa91fe2cc6abe79232a1a57cdf104f7a26e716e0a1e2789df78"}
```

Đây là SHA-256 của đúng bytes ASCII `ABC`. Nếu file có newline hoặc mã hóa khác, SHA-256 và byteCount sẽ khác. Thứ tự các JSON keys và whitespace không phải hợp đồng cố định; khi test, nên so sánh JSON fields.

### 7.4. Upload bằng Servlet Part

```bash
curl -i -X POST 'http://localhost:8080/api/uploads/part' \
  -F 'file=@note.txt;type=text/plain'
```

Response body:

```json
{"byteCount":3}
```

Ở đây Spring chuyển part `file` cho `Part`; controller không cần `MultipartFile`. Nếu dùng `Part.write(String)` để lưu thật, cần đọc thêm quy tắc multipart temp location/container và không dùng raw filename client làm đường dẫn lưu.

### 7.5. Form field thông thường + file

```bash
curl -i -X POST 'http://localhost:8080/api/uploads/simple' \
  -F 'description=Meeting notes' \
  -F 'file=@note.txt;type=text/plain'
```

Response dự kiến:

```json
{"description":"Meeting notes","byteCount":3}
```

Khác với `/mixed`, field `description` là một text form field bình thường, không phải một JSON document; `@RequestParam` phù hợp hơn.

### 7.6. Trường hợp lỗi cần quan sát

**File rỗng:**

```bash
: > empty.txt
curl -i 'http://localhost:8080/api/uploads/mixed' \
  -F 'metadata={"title":"Empty","category":"notes"};type=application/json' \
  -F 'file=@empty.txt;type=text/plain'
```

Dự kiến `400 Bad Request` do `file.isEmpty()`. Mẫu `: > empty.txt` là cú pháp Bash; trên PowerShell cần dùng cách tạo file 0 bytes khác.

**Metadata không hợp lệ:**

```bash
curl -i 'http://localhost:8080/api/uploads/mixed' \
  -F 'metadata={"title":"","category":"notes"};type=application/json' \
  -F 'file=@note.txt;type=text/plain'
```

Dự kiến `400` do `@NotBlank`. Hình dạng error body phụ thuộc cấu hình Boot/MVC exception handling; demo không định nghĩa một error JSON schema cụ thể.

**JSON part không đúng media type:**

```bash
curl -i 'http://localhost:8080/api/uploads/mixed' \
  -F 'metadata={"title":"Demo","category":"notes"};type=text/plain' \
  -F 'file=@note.txt;type=text/plain'
```

Thường nhận `415 Unsupported Media Type`: outer body vẫn là multipart hợp lệ, nhưng `HttpMessageConverter` không đọc được một DTO `UploadMetadata` từ part `text/plain`. Không nhầm với file content type `text/plain`, vì file part được nhận như bytes.

**File khai MIME khác:**

```bash
curl -i 'http://localhost:8080/api/uploads/mixed' \
  -F 'metadata={"title":"Demo","category":"notes"};type=application/json' \
  -F 'file=@note.txt;type=application/octet-stream'
```

Dự kiến `415` từ kiểm tra do controller tự viết. Nếu client khai `text/plain` nhưng nội dung thật là mã độc hoặc binary, controller demo **không phát hiện** chỉ qua header; phải áp dụng chính sách xác thực nội dung và quét tệp khi hệ thống lưu/cho phép truy cập.

### 7.7. Client browser với FormData

Một HTML form cho tệp:

```html
<form method="post" action="/api/uploads/simple"
      enctype="multipart/form-data">
    <input name="description" type="text" required>
    <input name="file" type="file" required>
    <button type="submit">Upload</button>
</form>
```

Form này POST multipart tới endpoint `/simple`. Vì server trả JSON, browser sẽ hiển thị JSON response; trong sản phẩm thật có thể redirect/render view hoặc dùng JavaScript.

Với `fetch` và JSON part:

```javascript
const metadata = {title: "Ghi chú", category: "notes"};
const fileInput = document.querySelector("#file");
const file = fileInput.files[0];

const data = new FormData();
data.append(
  "metadata",
  new Blob([JSON.stringify(metadata)], {type: "application/json"})
);
data.append("file", file);

const response = await fetch("/api/uploads/mixed", {
  method: "POST",
  body: data
});

if (!response.ok) {
  throw new Error("Upload failed: HTTP " + response.status);
}
const receipt = await response.json();
console.log(receipt);
```

Đây là **đoạn JavaScript dùng trong browser** có một input `id="file"` trong DOM; không phải chương trình tự chạy độc lập nếu chưa tạo input và script context. `FormData.append("metadata", Blob application/json)` đảm bảo part JSON có media type thích hợp. **Đừng đặt thủ công outer `Content-Type` trong fetch**; browser tự sinh boundary phù hợp. Kiểm tra `file` tồn tại và kích thước ở client để cải thiện UX, nhưng server vẫn phải validate độc lập.

## 8. MockMvc kiểm thử multipart, JSON converter và Servlet Part

MockMvc có `MockMultipartFile` và `MockPart` để mô phỏng một HTTP multipart request. Đây là cách tốt để kiểm chứng behavior mà không chạy server port thật.

**`src/test/java/demo/upload/UploadControllerTest.java`**

```java
package demo.upload;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockPart;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UploadControllerTest {

    @Autowired
    MockMvc mvc;

    private MockMultipartFile metadata(String json, String mime) {
        return new MockMultipartFile(
                "metadata", "", mime,
                json.getBytes(StandardCharsets.UTF_8));
    }

    private MockMultipartFile file(String mime, byte[] content) {
        return new MockMultipartFile(
                "file", "note.txt", mime, content);
    }

    @Test
    void acceptsJsonMetadataAndTextFile() throws Exception {
        mvc.perform(multipart("/api/uploads/mixed")
                    .file(metadata(
                        "{\"title\":\"Demo\",\"category\":\"notes\"}",
                        "application/json"))
                    .file(file("text/plain",
                        "ABC".getBytes(StandardCharsets.UTF_8))))
           .andExpect(status().isCreated())
           .andExpect(jsonPath("$.title").value("Demo"))
           .andExpect(jsonPath("$.category").value("notes"))
           .andExpect(jsonPath("$.byteCount").value(3))
           .andExpect(jsonPath("$.sha256").value(
               "b5d4045c3f466fa91fe2cc6abe79232a1a57cdf104f7a26e716e0a1e2789df78"));
    }

    @Test
    void invalidJsonMetadataFailsValidation() throws Exception {
        mvc.perform(multipart("/api/uploads/mixed")
                    .file(metadata(
                        "{\"title\":\"\",\"category\":\"notes\"}",
                        "application/json"))
                    .file(file("text/plain", new byte[]{65})))
           .andExpect(status().isBadRequest());
    }

    @Test
    void nonJsonMetadataPartIsUnsupported() throws Exception {
        mvc.perform(multipart("/api/uploads/mixed")
                    .file(metadata(
                        "{\"title\":\"Demo\",\"category\":\"notes\"}",
                        "text/plain"))
                    .file(file("text/plain", new byte[]{65})))
           .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void emptyFileIsRejected() throws Exception {
        mvc.perform(multipart("/api/uploads/mixed")
                    .file(metadata(
                        "{\"title\":\"Demo\",\"category\":\"notes\"}",
                        "application/json"))
                    .file(file("text/plain", new byte[0])))
           .andExpect(status().isBadRequest());
    }

    @Test
    void servletPartIsRead() throws Exception {
        MockPart part = new MockPart(
                "file", "note.txt",
                "ABC".getBytes(StandardCharsets.UTF_8));
        part.getHeaders().setContentType(MediaType.TEXT_PLAIN);

        mvc.perform(multipart("/api/uploads/part").part(part))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.byteCount").value(3));
    }

    @Test
    void ordinaryMultipartFieldsCanUseRequestParam()
            throws Exception {
        mvc.perform(multipart("/api/uploads/simple")
                    .param("description", "notes")
                    .file(file("text/plain", new byte[]{65, 66})))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.description").value("notes"))
           .andExpect(jsonPath("$.byteCount").value(2));
    }
}
```

Chạy:

```bash
mvn test
```

Bộ test khai báo **6 test methods**. Khi chúng pass trên project đã tạo đúng file, Maven kết thúc exit code `0`; log thường có thông tin tương tự `Tests run: 6, Failures: 0, Errors: 0, Skipped: 0`. Những test này xác minh MVC argument resolution và converter; **MockMvc không đồng nhất với proxy/container thật** về mọi giới hạn upload, filesystem temp, network streaming, multipart parsing quá lớn hoặc security filters. Hãy bổ sung integration tests qua embedded server và reverse proxy cho upload production.

### Vì sao mock test cần Content-Type riêng của metadata part?

`MockMultipartFile("metadata", "", "application/json", ...)` thiết lập MIME của metadata là JSON. Nếu part được khai text/plain, `@RequestPart UploadMetadata` cần converter hiểu DTO từ text/plain và thường không có. Khi kiểm tra raw multipart, cần nhìn **part headers**, không chỉ outer `multipart/form-data`.

### Test kích thước và encoding

Lệnh `mvn test` ở trên không khẳng định upload 3MB sẽ luôn trả status cụ thể qua real Tomcat. `MockMvc` thường không đi qua cùng cơ chế kích thước parser của container. Test thực qua HTTP server nên bao gồm:

- File 0 bytes, file sát ngưỡng 2MB và file vượt ngưỡng.
- Tổng request (nhiều parts) vượt `max-request-size`.
- Filename chứa `../`, `\\`, Unicode/emoji và quá dài.
- MIME header khai sai so với magic bytes.
- JSON part thiếu `Content-Type`, sai charset, malformed JSON và DTO vi phạm constraints.
- Client dừng upload giữa chừng, network timeouts, retry, concurrent requests.
- Nội dung tệp không đáng tin chứa script, HTML, executable, archive bomb hoặc file format exploit.

## 9. Nhiều file và tên part

Nếu frontend gửi nhiều files với cùng name `files`:

```java
@PostMapping(
        path = "/batch",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public List<Long> batch(
        @RequestParam("files") List<MultipartFile> files) {
    return files.stream().map(MultipartFile::getSize).toList();
}
```

Đây là method minh họa trong `@RestController`, cần import `List`, `MultipartFile`, `RequestParam`, `PostMapping` và `MediaType`. Client có thể dùng:

```bash
curl -F 'files=@a.txt' -F 'files=@b.txt' \
  'http://localhost:8080/api/uploads/batch'
```

Nhưng endpoint `/batch` **không thuộc project runnable ở mục 7** trừ khi bạn chủ động thêm method đó vào controller; lệnh curl là hướng dẫn riêng cho biến thể minh họa. Với nhiều files, cần tổng giới hạn dung lượng, giới hạn số part, concurrency và tránh lưu tất cả byte arrays trong RAM.

Nếu một request có cả JSON metadata và nhiều files, khai báo `@Valid @RequestPart("metadata") Dto metadata` và `@RequestPart("files") List<MultipartFile> files`; xác nhận frontend dùng đúng tên và JSON part content type.

## 10. @ModelAttribute cho form field và file trên một bean

Trong HTML form truyền thống, bạn có thể bind text fields cùng `MultipartFile` vào một object:

```java
public class UploadForm {
    @NotBlank
    private String title;
    private MultipartFile file;

    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public MultipartFile getFile() { return file; }
    public void setFile(MultipartFile file) { this.file = file; }
}
```

Method trong `@Controller`:

```java
@PostMapping(path = "/forms", consumes = "multipart/form-data")
public String handle(
        @Valid @ModelAttribute("uploadForm") UploadForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "uploads/new";
    }
    // Kiểm tra file != null, !file.isEmpty() và xử lý storage.
    return "redirect:/uploads/done";
}
```

Hai đoạn này là **snippets minh họa**, chưa có imports, class controller/templates và phương án persistence đầy đủ. `@ModelAttribute` dùng `WebDataBinder` để liên kết fields `title` và `file` với DTO; `@Valid` có thể kiểm tra `title`, còn `MultipartFile` cần quy tắc kiểm tra file riêng (hoặc custom validator). `BindingResult` nên đứng ngay sau tham số được validate.

**Khi nào chọn cách nào?**

- HTML form text + file, không có JSON part: `@ModelAttribute UploadForm` hoặc nhiều `@RequestParam` thường tự nhiên nhất.
- API JSON metadata + file, muốn nested DTO và Bean Validation: `@RequestPart("metadata") Dto`.
- File raw không metadata: `@RequestParam MultipartFile`/`@RequestPart MultipartFile`.
- Kiểm soát header/container-level của part: `Part`.

Không gượng ép form text field thành một chuỗi JSON rồi parse thủ công chỉ vì muốn tái sử dụng DTO, nếu UX/API không yêu cầu JSON part.

## 11. Lưu file an toàn: thiết kế production

Ví dụ ở mục 7 **không lưu file**, chỉ xử lý stream. Khi lưu file thật, cần thiết kế nhiều lớp phòng vệ:

### 11.1. Không tin filename do client cung cấp

`getOriginalFilename()` hoặc `Part.getSubmittedFileName()` là metadata **do client gửi**. Không được dùng thẳng làm path:

```java
// PHẢN VÍ DỤ: file name có thể là "../../secrets.txt".
Path target = uploadsDir.resolve(file.getOriginalFilename());
file.transferTo(target);
```

Đây là snippet **không an toàn**, không dùng trong production. Tên có thể chứa path separators, encoding lạ, reserved names, `..`, unicode normalization; ghép path làm rủi ro path traversal hoặc ghi đè.

Thiết kế tốt hơn: sinh storage key server-side (UUID/random), giữ tên client riêng làm metadata sau khi sanitize và giới hạn độ dài/charset. Nếu buộc cho phép download dưới tên gốc, encode `Content-Disposition` an toàn; không tự nối headers bằng raw filename.

Ví dụ ý tưởng (chưa phải upload service hoàn chỉnh):

```java
String storageKey = java.util.UUID.randomUUID().toString();
Path root = Path.of("/srv/app-upload-data").toAbsolutePath();
Path target = root.resolve(storageKey).normalize();
if (!target.startsWith(root)) {
    throw new SecurityException("Invalid upload target");
}
```

Cần kiểm tra và quản lý **filesystem symlinks**, permissions, path existence/atomic create và race conditions; phép `startsWith` đơn lẻ không giải quyết mọi rủi ro. Server-owned key tránh phần lớn path injection nhưng không thay quyền filesystem. Dùng thư mục ngoài web root để nội dung upload không tự được phục vụ như static resources.

### 11.2. MIME, extension và nội dung thật

`file.getContentType()` và extension `.pdf`/`.png` không phải bằng chứng nội dung thật. Với loại file được cho phép:

1. Kiểm tra declared MIME + extension (tham khảo, không quyết định cuối).
2. Đọc magic bytes hoặc parse cấu trúc file bằng thư viện phù hợp; giới hạn parser/resource.
3. Chỉ chấp nhận allowlist formats cần cho nghiệp vụ.
4. Nếu file có thể độc hại, quét malware qua quy trình phù hợp.
5. Đặt download `Content-Type` và `Content-Disposition` đúng, hạn chế browser sniffing (ví dụ `X-Content-Type-Options: nosniff`).
6. Với ảnh/video, cân nhắc transcode/re-encode bằng pipeline an toàn để giảm rủi ro embedded payload.
7. Đừng xử lý file dữ liệu do client gửi như executable, HTML được tin cậy hoặc template phía server.

### 11.3. Size limit và resource exhaustion

Giới hạn cần tồn tại ở nhiều tầng: reverse proxy, ingress/API gateway, Servlet parser, app policy (file type/count/size), storage quota, CPU/memory của parser, thời gian upload và total concurrent uploads. Multipart parser có thể viết dữ liệu tạm ra disk; một hệ thống hết disk vì nhiều files hợp lệ về kích thước cũng bị DoS.

Nếu dùng `file.getBytes()`, toàn nội dung nạp vào heap. Nếu dùng stream, giảm một loại memory copy nhưng request multipart vẫn có thể được buffer tạm; không đồng nghĩa với upload streaming từ network đến object storage. Với file hàng GB, cân nhắc resumable/chunked upload hoặc direct-to-object-storage có URL upload ngắn hạn và policy bảo mật rõ ràng.

### 11.4. Dữ liệu JSON metadata cũng phải validate và authorize

Chỉ cho client gửi những fields được phép. Đừng bind metadata vào JPA entity có `ownerId`, `role`, `tenantId`, `approved` rồi tin những giá trị đó. Lấy identity/tenant từ authentication context và kiểm tra quyền truy cập trước khi gắn file vào resource.

Nếu metadata ghi `ownerId` do client cung cấp, backend vẫn phải xác minh user được phép thao tác trên owner đó. `@Valid` và converter bảo đảm cú pháp/constraints, **không thay authorization**.

### 11.5. Storage + database không tự atomic

Một workflow robust có thể là:

```text
1. Validate authentication, authorization và metadata
2. Kiểm tra file count/size/type
3. Ghi file vào vùng staging/quarantine bằng key do server sinh
4. Scan/parse theo policy
5. Ghi DB metadata + trạng thái PENDING/READY theo transaction
6. Công bố file chỉ khi trạng thái READY
7. Nếu lỗi: cleanup/compensation, retry có kiểm soát
```

Đây là sequence kiến trúc, không phải lời hứa tính atomic của filesystem + SQL. Nếu DB commit lỗi sau khi file đã ghi, cần cleanup; nếu file thất bại sau khi DB đã tạo record, cần trạng thái/tái thử hoặc compensation. Đừng công bố download URL trước khi file được chấp nhận.

### 11.6. Security context và CSRF

Với app web dựa vào session/cookie có Spring Security, multipart form POST thường cần CSRF protection; file upload không phải ngoại lệ. API dùng bearer tokens và không dựa vào cookie có chính sách khác. Ví dụ Boot demo không thêm Spring Security, vì vậy không chứng minh chiến lược CSRF production.

Nếu cho phép upload từ browser domain khác, phải thiết kế CORS có giới hạn origins/methods/headers; CORS không tự xác thực người gửi hoặc chống CSRF.

## 12. Exception handling và HTTP status

| Lỗi | Nguồn thường gặp | Status điển hình |
| --- | --- | --- |
| Thiếu part bắt buộc | `@RequestPart("file")` hoặc `metadata` không được gửi | `400 Bad Request` |
| JSON part sai cú pháp | Jackson converter không đọc được metadata | `400 Bad Request` |
| JSON part bị khai `text/plain` | Không có converter đọc DTO cho media type đó | `415 Unsupported Media Type` |
| `@Valid` metadata không đạt | `MethodArgumentNotValidException` | `400 Bad Request` |
| File rỗng theo policy demo | Controller ném `ResponseStatusException(BAD_REQUEST)` | `400` |
| File có declared MIME không được phép | Controller policy trong demo | `415` |
| File vượt size limit | Multipart resolver/container, `MaxUploadSizeExceededException` tùy cấu hình | Thường `413 Payload Too Large` khi được map phù hợp; kiểm tra môi trường |
| Outer Content-Type không phải multipart | `consumes=multipart/form-data` không khớp | `415` |
| Disk đầy, I/O hoặc scanner lỗi | Storage/server | `5xx`; không lộ server path/stack |
| File/metadata thuộc tenant khác | Authorization ở service | `403` hoặc `404` theo security policy |

**Đừng hứa một status duy nhất cho mọi môi trường multipart**: lỗi size-limit có thể xảy ra tại reverse proxy/container trước khi đi vào controller/advice, và khi response đã commit không thể đổi status. Nếu API yêu cầu một error contract ổn định, cần kiểm thử end-to-end và cấu hình error responses ở đúng tầng.

Một handler minh họa cho size limit trong MVC, **không bắt buộc** để chạy demo:

```java
@RestControllerAdvice
public class UploadErrorAdvice {
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ProblemDetail> tooLarge(
            MaxUploadSizeExceededException exception) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.PAYLOAD_TOO_LARGE,
                "Uploaded content exceeds the configured limit.");
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE).body(p);
    }
}
```

Đây là snippet trong file riêng, cần imports `RestControllerAdvice`, `ExceptionHandler`, `ResponseEntity`, `ProblemDetail`, `HttpStatus` và `MaxUploadSizeExceededException`. Đường xử lý này chỉ áp dụng nếu exception tới MVC resolver; reverse proxy chặn trước sẽ không đi vào advice. `ProblemDetail` thuộc Spring 6.x hỗ trợ RFC 9457.

## 13. Lỗi thường gặp khi kết hợp JSON với file

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `@RequestPart Dto` nhận 415 dù body nhìn giống JSON | JSON part có Content-Type text/plain/missing, converter không hỗ trợ | Gửi `metadata` part với `application/json` |
| `MissingServletRequestPartException` | Tên part sai hoặc không gửi | Kiểm tra `name="metadata"` và `@RequestPart("metadata")` |
| Outer multipart request không parse được | Header boundary thiếu/sai, client tự đặt Content-Type | Để browser/curl tạo boundary tự động |
| `@RequestBody Dto` không parse được request multipart | Đang đọc whole multipart như JSON | Dùng `@RequestPart` cho JSON part |
| File luôn có size 0 | File rỗng hoặc client gửi sai field | Kiểm tra `file.isEmpty()`, raw part bytes và tên |
| ByteCount khác độ dài String | Unicode charset / newline / binary | Đếm bytes từ input stream, không dùng `String.length()` |
| Validation JSON không chạy | Quên `@Valid` hoặc validator dependency | Thêm `@Valid` và starter-validation |
| Metadata đúng nhưng chưa bảo vệ file | Chỉ validate DTO, không kiểm tra content/policy | Xác thực quyền, size, MIME/magic, scanner |
| Upload hiện HTML error, client mong JSON | Exception xảy ra ngoài controller/advice | Thống nhất error handling ở MVC + proxy/container |
| Upload lớn làm tăng RAM | Dùng `file.getBytes()` hoặc buffer toàn bộ | Giới hạn kích thước, dùng stream/appropriate storage pipeline |
| Trùng filename làm ghi đè file cũ | Tin `getOriginalFilename()` | Sinh UUID/storage key server-side |
| File có `Content-Type: image/png` nhưng là script | Trust header client | Kiểm tra bytes và parser, không execute tệp |
| Bắt `Part` không thành công | Servlet multipart config/resolver/container khác nhau | Xác nhận Boot multipart enabled, Servlet API và part name |
| File biến mất trong async job | Multipart temp cleanup sau request | Di chuyển vào durable storage trước khi trả/queue |
| Metadata/DB đã lưu nhưng file thất bại | Không có workflow compensation | Dùng staging + transaction state + cleanup |
| 413 không vào ControllerAdvice | Proxy/container reject từ sớm | Test giới hạn ở từng tầng; cấu hình error policy |

Quy trình debug:

1. Kiểm tra HTTP request **outer Content-Type** và boundary trước.
2. Xem từng part: `Content-Disposition name`, filename, **part Content-Type**, byte count.
3. Đối chiếu names với `@RequestPart` / `@RequestParam`.
4. Nếu DTO không deserialize, xác định converter và lỗi 400/415; nếu DTO hợp lệ mà file sai, kiểm tra upload policy.
5. Xem multipart limits ở proxy, Servlet/container và Boot.
6. Với production, kiểm tra storage state, cleanup, scanner và authorization; không log raw file bytes, token hay PII.

## 14. Nên chọn thiết kế API nào?

| Trường hợp | Cách nên làm |
| --- | --- |
| Upload đơn file không metadata | `@RequestParam("file") MultipartFile` hoặc `@RequestPart` |
| Upload file + vài form text fields | `@RequestParam` hoặc `@ModelAttribute UploadForm` |
| Upload file + metadata JSON lồng nhau | `@Valid @RequestPart("metadata") Dto` + `@RequestPart("file") MultipartFile` |
| Cần Servlet-native access | `jakarta.servlet.http.Part` |
| Nhiều tệp cùng một field | `List<MultipartFile>` và giới hạn số lượng |
| Ứng dụng WebFlux | `FilePart` và reactive codecs, không dùng MVC `MultipartFile` |
| Tệp rất lớn | Streaming/resumable/direct-to-storage architecture, không `getBytes()` |
| API cần upload + transaction nghiệp vụ | Staging, state machine, compensation, idempotency |
| Cần kiểm tra format thực | File signature/parser/sandbox scanning, không chỉ client MIME |
| Client dùng browser `fetch` | `FormData` + JSON `Blob` với application/json; để browser tạo boundary |

## 15. Bài tập tự kiểm tra

1. Multipart outer request và JSON part có hai `Content-Type` khác nhau như thế nào?
2. Vì sao `@RequestPart("metadata") UploadMetadata` có thể deserialize JSON còn `@RequestParam("metadata") String` không tự thành DTO?
3. Khi nào dùng `MultipartFile`, khi nào dùng Servlet `Part`?
4. Tại sao `@RequestBody UploadMetadata` không thay thế được `@RequestPart` trong request multipart?
5. File có `filename="../../etc/passwd"` hoặc Content-Type `image/png` có đáng tin không?
6. Vì sao upload service không nên giữ `MultipartFile` để đọc stream sau request đã kết thúc?
7. Khi dùng `curl -F` hoặc `fetch(FormData)`, tại sao không nên tự đặt outer Content-Type không có boundary?
8. `@Valid` có phát hiện malware hoặc path traversal trong tên file không?
9. Lý do gì khiến `MockMvc` size test không thay cho kiểm thử thật qua Servlet container?
10. Tại sao upload file thành công nhưng insert database thất bại không được giải quyết bởi một SQL transaction đơn thuần?
11. Vì sao return byteCount bằng cách đọc `InputStream` an toàn hơn `String.length()` cho binary?
12. Nếu metadata part gửi `text/plain` nhưng nội dung là `{"title":"..."}`, Spring dựa vào thông tin nào để chọn converter?

**Gợi ý:** (1) Outer multipart/form-data có boundary; part JSON là application/json. (2) RequestPart dùng HttpMessageConverter trên part; RequestParam String lấy text. (3) Spring convenience so với Servlet-native API. (4) Whole body không phải JSON mà là multipart envelope. (5) Không, cả filename và MIME đều do client gửi. (6) Temp content có thể bị dọn sau request. (7) Boundary của payload phải khớp header. (8) Không, đây là policy/security độc lập. (9) Container/proxy và temporary disk handling khác mock. (10) Filesystem/object storage không nằm trong cùng DB transaction. (11) Byte count không phụ thuộc encoding. (12) Part Content-Type và converter cho Java target type.

## 16. Tài liệu chính thức

- [Spring Framework 6.1 — Multipart Resolver](https://docs.spring.io/spring-framework/reference/6.1/web/webmvc/mvc-servlet/multipart.html)
- [Spring Framework — Multipart Forms và @RequestPart](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.1 — MultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/multipart/MultipartFile.html)
- [Spring Framework 6.1 — RequestPart Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/bind/annotation/RequestPart.html)
- [Spring Framework 6.1 — RequestPartMethodArgumentResolver](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestPartMethodArgumentResolver.html)
- [Spring Boot 3.3 — Common Application Properties, Multipart](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)
- [Jakarta Servlet — Part API](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/part)
- [RFC 7578 — Returning Values from Forms: multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578)
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)

**Kết luận:** Với multipart/form-data, Spring MVC đưa file parts vào `MultipartFile` hoặc `Part`, còn JSON part có thể được giải mã bằng `@RequestPart Dto` qua `HttpMessageConverter`. Một API upload dùng được ngoài thực tế phải có hợp đồng MIME và part names rõ ràng, validation DTO, kiểm tra bytes/size/quyền truy cập, lưu trữ an toàn và kế hoạch xử lý lỗi/cleanup; upload là một bài toán HTTP, dữ liệu và bảo mật, không chỉ là gọi `getBytes()`.
