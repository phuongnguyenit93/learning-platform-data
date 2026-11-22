# Xử lý yêu cầu vượt kích thước, sai định dạng hoặc ngắt giữa chừng khi tải và nhận tệp

## 1. Bối cảnh: lỗi truyền tệp khác lỗi xử lý nghiệp vụ

Một endpoint **upload** nhận dữ liệu từ HTTP client (thường `multipart/form-data` hoặc raw request body) và có thể lưu vào đĩa, object storage hay dịch vụ khác. Endpoint **download** đọc dữ liệu rồi gửi về client. Cả hai đều có thể gặp lỗi ngay trước, trong hoặc sau khi truyền nội dung:

1. **Vượt giới hạn:** body hoặc một file/part lớn hơn giới hạn được chấp nhận; tầng proxy, web server, multipart parser hay ứng dụng có thể từ chối.
2. **Sai định dạng:** HTTP `Content-Type` không đúng; multipart thiếu/sai `boundary`; thiếu part bắt buộc; tệp có nội dung không đúng kiểu được phép; checksum không hợp lệ.
3. **Ngắt giữa chừng:** client mất mạng, hủy request, hết thời gian, proxy cắt kết nối, ổ đĩa hết chỗ hoặc service lưu trữ gặp lỗi trong lúc đang đọc/ghi/trả bytes.

Ba trường hợp cần được xử lý **theo đúng thời điểm phát sinh**. Controller chỉ có thể trả response khi HTTP connection vẫn hoạt động và response chưa commit. Nếu client đã đóng socket, việc cố gửi JSON báo lỗi có thể thất bại; thay vào đó cần dọn tệp tạm, ghi nhận trạng thái và thiết kế retry/idempotency.

Ví dụ luồng upload:

~~~text
Client
  |
  | POST /files, multipart/form-data
  v
Reverse proxy / ingress / CDN [giới hạn body, timeout, WAF]
  |
  v
Embedded server Tomcat/Netty [HTTP parser, connection limits]
  |
  v
Spring MVC MultipartResolver hoặc WebFlux multipart reader
  |
  v
Controller/service [kiểu file, nội dung, giới hạn nghiệp vụ]
  |
  v
Tệp tạm/stream -> validate -> ghi bền vững -> commit metadata
  |
  v
Response 201 + fileId (nếu kết nối còn hoạt động)
~~~

Một request **bị chặn ở proxy** có thể chưa bao giờ tới Spring Boot. Một multipart request **bị lỗi lúc parse** có thể không gọi controller. Và việc upload đã commit thành công nhưng client mất response **không chứng minh** upload đã thất bại: server và client có thể nhìn hai kết quả khác nhau.

## 2. Chọn HTTP status đúng với loại lỗi

| Tình huống | Status nên cân nhắc | Ghi chú |
| --- | --- | --- |
| Request body vượt giới hạn server chấp nhận | **413 Content Too Large** | Có thể xuất hiện từ proxy/container trước ứng dụng; lý do cũ thường gọi “Payload Too Large” |
| `Content-Type` ngoài không được endpoint hỗ trợ | **415 Unsupported Media Type** | Ví dụ endpoint yêu cầu multipart nhưng client gửi `application/json` |
| Multipart thiếu `boundary`, part sai cú pháp, thiếu trường bắt buộc | **400 Bad Request** | Một số lỗi có thể làm server đóng kết nối trước khi tạo response |
| File part khai báo kiểu không được hỗ trợ | **415** hoặc **422** theo hợp đồng API | Hợp đồng phải xác định rõ chính sách theo từng loại lỗi |
| Request đúng cấu trúc nhưng nội dung file không đạt quy tắc ngữ nghĩa | **422 Unprocessable Content** | Ví dụ khai báo PDF nhưng bytes không có cấu trúc cần thiết |
| Không đủ quyền truy cập/upload/download | **401/403** | Tách xác thực/phân quyền khỏi format validation |
| File không tồn tại khi download | **404 Not Found** | Không tự trả file trống với status 200 |
| Hết dung lượng lưu trữ hoặc dependency storage lỗi | **500/503** tùy bản chất | Log nội bộ; không lộ đường dẫn/stack trace ra client |
| Timeout trước khi nhận đủ HTTP request | **408 Request Timeout** có thể gặp | Có thể chỉ thấy connection reset, tùy server/proxy |
| Gateway timeout khi gọi upstream | **504 Gateway Timeout** | Không đồng nghĩa backend chắc chắn chưa commit upload |
| Client đóng kết nối trước khi hoàn tất | **Không bảo đảm có HTTP status ở client** | Có thể thấy IOException/broken pipe hoặc log proxy `499` (không thuộc mã chuẩn IANA) |

**413 không phải cơ chế kiểm tra mọi nội dung xấu.** Dung lượng lớn là vấn đề *kích thước*; header sai là vấn đề *media type/cấu trúc*; file chứa nội dung độc hại hoặc không hợp lệ cần *kiểm tra nội dung*. Với client đã ngắt, không thể hứa “luôn trả 400/500”.

HTTP/1.1 có thể sử dụng `Content-Length` hoặc truyền theo chunked framing, trong khi HTTP/2/3 dùng frame. Không tin hoàn toàn `Content-Length` do client khai báo: request có thể bị gửi thiếu/trễ, còn parser/server cũng cần áp dụng giới hạn khi đọc bytes thực tế. Nếu server phát hiện body quá lớn, theo RFC 9110 nó có thể chấm dứt kết nối; client có thể quan sát lỗi đường truyền thay vì một JSON 413 đầy đủ.

## 3. Giới hạn dung lượng ở nhiều lớp

### 3.1. Spring Boot Servlet / Spring MVC

Với `spring-boot-starter-web`, multipart upload thường được hỗ trợ thông qua Servlet `Part` API và `MultipartResolver`. Các property chuẩn:

~~~properties
# src/main/resources/application.properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB
spring.servlet.multipart.file-size-threshold=0B
~~~

- `max-file-size`: giới hạn **mỗi file part**. Mặc định Spring Boot 3.3 là **1MB**.
- `max-request-size`: giới hạn **toàn request multipart**. Mặc định là **10MB**. Bao gồm các phần và chi phí multipart framing; không chỉ là tổng kích thước các file.
- `file-size-threshold`: ngưỡng cho việc ghi dữ liệu upload xuống đĩa tạm. Mặc định **0B**. Đây **không phải** giới hạn upload lớn nhất.
- `location`: nếu cấu hình, chọn thư mục lưu tạm cho multipart parser; thư mục phải tồn tại/có quyền thích hợp. Mặc định dùng vị trí tạm do môi trường/container lựa chọn.
- `resolve-lazily`: điều khiển khi nào thực hiện parse multipart; nó có thể ảnh hưởng **thời điểm exception** được phát sinh, không thay đổi giới hạn kích thước.

Đặt `max-request-size` lớn hơn `max-file-size` đủ cho headers/metadata và các part hợp lệ. Nếu API cho phép nhiều file, phải có **giới hạn tổng** song song với giới hạn mỗi file. Chẳng hạn file 2MB + metadata có thể vượt request limit đúng 2MB nếu cấu hình quá sát.

Một lỗi phổ biến là tăng `spring.servlet.multipart.max-file-size` lên 100MB nhưng quên `max-request-size` vẫn 10MB, khiến request nhiều hơn 10MB bị từ chối. Ngược lại, chỉ tăng `max-request-size` không cho phép một file vượt `max-file-size`.

Giới hạn trong controller (ví dụ `file.getSize()`) là **bổ sung theo nghiệp vụ**, không thay thế multipart parser: tại thời điểm controller nhận `MultipartFile`, server/parser có thể đã đọc hoặc ghi tạm request. Vì vậy nên giới hạn sớm tại ingress, container/parser và cuối cùng kiểm tra lại trong domain logic.

### 3.2. Proxy, API gateway và container

Các tầng phía trước có thể có body cap và timeout riêng (ví dụ NGINX `client_max_body_size`), nên quy tắc thực tế là **giới hạn thấp nhất trong đường đi** sẽ chặn request trước.

Ví dụ logic:

~~~text
Gateway giới hạn 5MB
Spring multipart max-request-size=20MB
Business rule max-file-size=8MB
=> Request 6MB có thể bị gateway chặn 413 trước khi tới Spring.
~~~

Nhiều hệ thống còn có giới hạn số kết nối, tốc độ, request header, thời gian đọc request body, dung lượng đĩa tạm, quota theo tài khoản. Cấu hình các tầng phải nhất quán với mục tiêu, tránh vừa tăng limit ở Spring vừa quên proxy. Khi gặp lỗi 413 nhưng không thấy controller log, hãy kiểm tra ingress/proxy access log và server access log.

### 3.3. Khi nào mới được nới giới hạn?

Không đặt “unlimited” chỉ vì file lớn. Với tệp rất lớn nên cân nhắc **upload trực tiếp tới object storage có kiểm soát**, multipart/resumable upload, chunking kèm ID và checksum, thay vì buffer toàn bộ vào JVM. Nếu phải cho phép tệp lớn, xem tổng dung lượng có thể đồng thời upload, quota, băng thông, tệp tạm và chiến lược dọn dẹp.

## 4. Sai định dạng xảy ra ở hai mức khác nhau

### 4.1. Sai cú pháp HTTP/multipart

Một request upload multipart hợp lệ (dạng logic HTTP/1.1) có cấu trúc:

~~~http
POST /files HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=abc123

--abc123
Content-Disposition: form-data; name="file"; filename="sample.pdf"
Content-Type: application/pdf

%PDF-1.4...
--abc123--
~~~

Dấu ngăn cách mỗi phần phải khớp `boundary` trong header. Nếu header khai báo `boundary=abc123` nhưng body dùng marker khác, thiếu dòng đóng, thiếu `Content-Disposition` cần thiết hoặc request bị cắt giữa chừng, multipart parser có thể báo lỗi **trước khi controller chạy**.

Đừng tự tạo multipart string bằng cách nối thủ công khi có thư viện client chuẩn. Với cURL dùng `-F "file=@sample.pdf;type=application/pdf"` để cURL tự tạo `boundary` và framing đúng; không cần tự đặt header `Content-Type: multipart/form-data` thiếu boundary.

### 4.2. Sai nội dung file nhưng multipart vẫn hợp lệ

`filename="report.pdf"` và `Content-Type: application/pdf` do client cung cấp **không chứng minh file là PDF**. Tên file có thể giả, header MIME có thể bị sửa và bytes có thể chứa nội dung khác. Phải kiểm tra theo chính sách ứng dụng, ví dụ:

- Chỉ nhận các media type được cho phép.
- Kiểm tra signature/file magic ban đầu (ví dụ PDF thường bắt đầu `%PDF-`) nhưng đừng xem 5 bytes là kiểm định định dạng toàn diện.
- Với định dạng phức tạp, dùng parser/thư viện đáng tin để xác nhận cấu trúc thực tế, giới hạn độ sâu/nội dung, loại script hoặc macro khi cần.
- Quét malware theo quy định và kiểm tra **zip bomb**, decompression ratio, số entry, recursion depth khi nhận archive nén.
- Kiểm tra hash nếu giao thức truyền tin cung cấp checksum có xác thực; checksum chỉ giúp phát hiện khác biệt, không xác định file an toàn.
- Không dùng `MultipartFile.getOriginalFilename()` làm đường dẫn đích. Giá trị này là input không tin cậy, có thể chứa path separator, Unicode gây nhầm, ký tự điều khiển hoặc `../`. Sinh ID/tên file của server.

**Chính sách status gợi ý:** outer `Content-Type` sai → 415; thiếu part/hỏng multipart → 400; file content vượt giới hạn → 413; file parse được nhưng không đúng loại/quy tắc chấp nhận → 422; file part MIME sai có thể chọn 415 theo hợp đồng. Không phải mọi lỗi trong multipart đều mặc nhiên là 415.

## 5. Ví dụ Spring Boot MVC: validate, ghi tạm, hoàn tất atomically

Ví dụ này minh họa **quy trình xử lý lỗi an toàn** hơn là một dịch vụ lưu trữ production hoàn chỉnh. Ứng dụng chấp nhận **một file PDF tối đa 2 MiB**, nhận qua `multipart/form-data`, kiểm tra header và signature, **ghi vào file tạm trong cùng thư mục đích**, rồi đổi tên để công bố. Nếu upload không hoàn thành, file tạm được cố gắng xóa.

### 5.1. Cấu trúc và dependency

~~~text
safe-files/
├── build.gradle
├── settings.gradle
└── src/
    ├── main/
    │   ├── java/demo/files/UploadSafetyApplication.java
    │   └── resources/application.properties
    └── test/java/demo/files/UploadSafetyHttpTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'safe-files'
~~~

`build.gradle` (ví dụ Java 17+ và Spring Boot 3.3.13):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=3MB
spring.servlet.multipart.file-size-threshold=0B
~~~

### 5.2. Java code đầy đủ

Tệp `src/main/java/demo/files/UploadSafetyApplication.java`:

~~~java
package demo.files;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.multipart.MultipartException;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class UploadSafetyApplication {
    public static void main(String[] args) {
        SpringApplication.run(UploadSafetyApplication.class, args);
    }
}

@RestController
@RequestMapping("/files")
class FileController {
    private static final long MAX_BYTES = 2L * 1024 * 1024;
    private static final byte[] PDF_MAGIC =
            "%PDF-".getBytes(StandardCharsets.US_ASCII);

    // Ví dụ dùng directory cố định do ứng dụng kiểm soát.
    private final Path root = Path.of("storage").toAbsolutePath().normalize();

    @PostMapping(
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<Receipt> upload(@RequestPart("file") MultipartFile file)
            throws IOException {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "File is empty");
        }

        // Guard nghiệp vụ, ngoài limit đã đặt ở multipart parser.
        if (file.getSize() > MAX_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE, "File exceeds 2 MiB");
        }

        // Content-Type của part chỉ là thông tin client khai báo.
        if (!MediaType.APPLICATION_PDF_VALUE.equalsIgnoreCase(
                file.getContentType())) {
            throw new ResponseStatusException(
                    HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                    "Only application/pdf is accepted");
        }

        try (InputStream in = file.getInputStream()) {
            byte[] magic = in.readNBytes(PDF_MAGIC.length);
            if (!Arrays.equals(PDF_MAGIC, magic)) {
                throw new ResponseStatusException(
                        HttpStatus.UNPROCESSABLE_ENTITY,
                        "File does not have a PDF signature");
            }
        }

        Files.createDirectories(root);
        Path temporary = Files.createTempFile(
                root, "upload-", ".part");
        boolean committed = false;

        try {
            long copied;
            try (InputStream in = file.getInputStream()) {
                copied = Files.copy(
                        in, temporary,
                        StandardCopyOption.REPLACE_EXISTING);
            }

            if (copied != file.getSize()) {
                throw new IOException("Incomplete file copy");
            }
            if (copied > MAX_BYTES) {
                throw new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE, "File exceeds 2 MiB");
            }

            // Tên final do server tạo: tránh path traversal.
            String fileName = UUID.randomUUID() + ".pdf";
            Path destination = root.resolve(fileName);

            try {
                Files.move(temporary, destination,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException unsupported) {
                // Nếu filesystem không hỗ trợ atomic rename:
                Files.move(temporary, destination);
            }

            committed = true;
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(new Receipt(fileName, copied));
        } finally {
            if (!committed) {
                Files.deleteIfExists(temporary);
            }
        }
    }

    @GetMapping(path = "/{fileName}",
            produces = MediaType.APPLICATION_PDF_VALUE)
    ResponseEntity<Resource> download(@PathVariable String fileName)
            throws IOException {

        // Chỉ nhận định dạng tên do API này sinh ra.
        if (!fileName.matches("[0-9a-f-]{36}\\.pdf")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid file ID");
        }

        Path path = root.resolve(fileName).normalize();
        if (!path.startsWith(root) || !Files.isRegularFile(path)) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "File not found");
        }

        Resource resource = new FileSystemResource(path);
        String disposition = ContentDisposition.attachment()
                .filename(fileName)
                .build().toString();

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .contentLength(Files.size(path))
                .body(resource);
    }

    record Receipt(String fileName, long bytes) {
    }
}

@RestControllerAdvice
class FileApiErrors {
    @ExceptionHandler(MaxUploadSizeExceededException.class)
    ResponseEntity<ApiError> oversized(MaxUploadSizeExceededException ex) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(new ApiError("FILE_TOO_LARGE",
                        "Upload exceeds the configured size limit"));
    }

    @ExceptionHandler(MultipartException.class)
    ResponseEntity<ApiError> malformed(MultipartException ex) {
        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_MULTIPART",
                        "Multipart request is invalid"));
    }

    record ApiError(String code, String message) {
    }
}
~~~

**Giải thích từng ranh giới lỗi:**

1. `spring.servlet.multipart.*` cho phép container/parser chặn request lớn trước khi chạy `upload`. `MaxUploadSizeExceededException` là một subclass của `MultipartException`; handler cụ thể cho size có ưu tiên để trả 413 trong những trường hợp exception đi vào Spring MVC exception resolver.
2. `@PostMapping(consumes = "multipart/form-data")` biểu thị kiểu body của endpoint; request sai outer media type thường trả 415. `@RequestPart("file")` yêu cầu part tên `file`; thiếu part thường trả 400.
3. Guard `file.getSize()` bảo vệ business policy nếu parser limit bị đổi, hoặc khi unit test bỏ qua giới hạn container.
4. Kiểm tra MIME của part và 5 byte magic chỉ là **lớp minh họa**. Một file độc hại vẫn có thể bắt đầu `%PDF-`. Trong production phải bổ sung parser validation, malware scanning và policy lưu trữ.
5. Thư mục `storage` chỉ để demo, không thuộc `src/main/resources/static`; nó không tự public qua Spring Boot. Ứng dụng thực tế cần chính sách phân quyền download và nơi lưu có độ bền phù hợp; **tên UUID không thay thế authorization**.
6. `Files.createTempFile` tạo file riêng; `Files.copy` ghi dữ liệu; `Files.move` đưa file sang tên final **sau khi copy thành công**. Dùng rename atomic khi filesystem hỗ trợ; fallback có thể không bảo đảm atomic trên mọi nền tảng. Không coi thao tác move thành một transaction xuyên database/object storage.
7. `finally` cố xóa file `.part` nếu xảy ra IOException hoặc validation ném lỗi **sau khi tạo temp**. Nếu JVM/process bị kill hoặc máy mất điện, finally không chạy; cần job cleanup file tạm quá hạn.
8. `ResponseEntity<Resource>` trong download trả body bằng resource, không gọi `Files.readAllBytes` đưa cả file vào heap. Nếu client dừng đọc lúc response đang stream, lỗi có thể xảy ra **sau khi method trả về**.
9. Không có handler `@ExceptionHandler(IOException.class)` chung: lỗi lưu trữ cần được phân loại/log nội bộ phù hợp; lỗi socket do client đóng không nên bị báo như validation failure. Trong demo, IOException không xử lý sẽ đi theo cơ chế lỗi server mặc định khi còn có thể trả response.

### 5.3. Cách chạy và quan sát kết quả

Với Gradle wrapper đã có trong dự án:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Tạo file PDF chữ ký tối thiểu cho **kiểm thử luồng** (nội dung này chưa là PDF hoàn chỉnh, nhưng qua được guard 5 byte của demo):

~~~bash
printf '%s\n' '%PDF-1.4' 'demo bytes' > tiny.pdf
curl -i -F "file=@tiny.pdf;type=application/pdf" \
  http://localhost:8080/files
~~~

**Kết quả dự kiến của API demo:** HTTP **201 Created**, JSON dạng:

~~~json
{
  "fileName": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.pdf",
  "bytes": 20
}
~~~

`fileName` là **ví dụ định dạng UUID**, khác nhau mỗi lần. `bytes` bằng đúng số byte của file mà lệnh trên tạo trong môi trường thực tế; không nên hard-code số 20 vào test vì cách tạo file/newline có thể khác. Với API production kiểm định PDF đầy đủ, file `tiny.pdf` minh họa sẽ bị từ chối vì chưa phải tài liệu PDF hợp lệ.

Dùng `fileName` trả về thực tế để gọi:

~~~bash
curl -i -o received.pdf \
  "http://localhost:8080/files/<fileName-thuc-te>"
~~~

Trong lệnh thật thay `<fileName-thuc-te>` bằng tên UUID từ JSON, bỏ dấu ngoặc nhọn/dấu `<>`. Khi download, status thành công là 200, header `Content-Type: application/pdf` và `Content-Disposition: attachment; filename="..."`; body được stream tới `received.pdf`.

**Điểm quan trọng về `curl -i -o`:** `-i` thêm HTTP headers vào output. Để lưu file PDF nguyên bytes, dùng `curl -fL -o received.pdf "URL"` và xem headers bằng `curl -I "URL"` riêng. Không dùng file tạo bởi `curl -i -o` để so checksum với file gốc.

Ví dụ lỗi MIME part:

~~~bash
curl -i -F "file=@tiny.pdf;type=text/plain" \
  http://localhost:8080/files
~~~

Kỳ vọng status **415**, do demo từ chối part khai báo `text/plain`. Request vẫn là multipart hợp lệ; đây là chính sách **inner part type**.

Ví dụ file giả PDF:

~~~bash
printf 'not a PDF\n' > fake.pdf
curl -i -F "file=@fake.pdf;type=application/pdf" \
  http://localhost:8080/files
~~~

Kỳ vọng status **422** do `%PDF-` không khớp. File `fake.pdf` không được công bố trong thư mục lưu final.

Ví dụ outer `Content-Type` sai:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -d '{"file":"hello"}' \
  http://localhost:8080/files
~~~

Kỳ vọng **415**, do endpoint yêu cầu `multipart/form-data`.

Ví dụ vượt size (Linux/macOS, cần `dd`):

~~~bash
dd if=/dev/zero of=huge.pdf bs=1M count=3
curl -i -F "file=@huge.pdf;type=application/pdf" \
  http://localhost:8080/files
~~~

Với file 3 MiB và `max-file-size=2MB`, kỳ vọng bị từ chối vì **quá giới hạn**. Có thể thấy 413 hoặc lỗi connection do parser/container/proxy chặn sớm; JSON custom của `FileApiErrors` chỉ hiện nếu exception đi qua resolver còn gửi response được.

## 6. Java test: kiểm thử chính sách định dạng và kích thước

Thêm JUnit 5 test (dependency `spring-boot-starter-test` đã có). Tệp `src/test/java/demo/files/UploadSafetyHttpTest.java`:

~~~java
package demo.files;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UploadSafetyHttpTest {
    @Autowired
    MockMvc mvc;

    @Test
    void acceptsDemoPdfSignature() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "ok.pdf", "application/pdf",
                "%PDF-1.4\n".getBytes(StandardCharsets.US_ASCII));

        mvc.perform(multipart("/files").file(file))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.fileName").exists());
    }

    @Test
    void rejectsWrongPartMediaType() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "ok.txt", "text/plain",
                "text".getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/files").file(file))
                .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void rejectsInvalidSignature() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "fake.pdf", "application/pdf",
                "not-pdf".getBytes(StandardCharsets.US_ASCII));

        mvc.perform(multipart("/files").file(file))
                .andExpect(status().isUnprocessableEntity());
    }

    @Test
    void rejectsBusinessSizeLimit() throws Exception {
        byte[] bytes = new byte[2 * 1024 * 1024 + 1];
        MockMultipartFile file = new MockMultipartFile(
                "file", "huge.pdf", "application/pdf", bytes);

        mvc.perform(multipart("/files").file(file))
                .andExpect(status().isPayloadTooLarge());
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.files.UploadSafetyHttpTest
~~~

Test `MockMvc` có thể tạo request multipart mô phỏng mà không đi qua đúng đường parser/limit của **Tomcat HTTP thật**. Vì vậy test file 2MiB+1 ở đây xác nhận **guard nghiệp vụ** trong controller. Muốn kiểm tra thực sự `spring.servlet.multipart.max-file-size`, gateway 413, timeout, HTTP framing và kết nối ngắt phải có **integration test mở server thật**, tốt nhất với cấu hình proxy/container như môi trường deploy.

Test tạo file `storage/*.pdf` bên trong working directory khi case success chạy. Trong demo có thể dọn môi trường test riêng bằng temp directory; production cần vùng lưu do ứng dụng quản lý và chính sách retention. Không chạy integration test ghi file production thật.

## 7. Yêu cầu bị ngắt giữa chừng: điều gì thực sự xảy ra?

### 7.1. Client ngắt khi đang upload

Ví dụ browser đóng tab, người dùng hủy upload, client timeout hoặc mạng đứt khi mới gửi một phần body:

~~~text
Client                 Server / multipart parser       Storage
  | POST multipart body ... |
  |------------------------->| tạm nhận bytes              |
  |----- gửi một phần ------>|                               |
  X client disconnect        | socket read EOF/reset         |
                             | parser thất bại hoặc          |
                             | subscription bị cancel        |
                             | cleanup temporary files       |
                             | không thể bảo đảm response    |
~~~

Nếu parser chưa hoàn tất, **controller có thể chưa được gọi**. Một số server trả 400/408; trường hợp khác đóng socket, ghi exception hoặc access log. Không có một status code duy nhất cho mọi client disconnect. NGINX thường dùng **499 Client Closed Request** trong access log, nhưng 499 **không phải mã HTTP chuẩn do ứng dụng nhất thiết trả cho client**.

Một request upload có `Content-Length` 10 MiB nhưng chỉ gửi được 2 MiB rồi mất kết nối là **request chưa hoàn chỉnh**, không nên xem như file 2 MiB hợp lệ để commit. Nếu dùng streaming API, chỉ commit sau khi nhận được completion thật và kiểm tra length/checksum/thành phần cuối theo hợp đồng.

**Không được cố “resume” một `POST multipart/form-data` thường bằng cách phát lại phần bytes còn thiếu** nếu server chưa triển khai giao thức resume. Mỗi POST thường là một request riêng. Để resumable upload, cần ID phiên upload, offset, validation chunk, checksum, expiry, xử lý commit/abort và giao thức rõ ràng như tus hoặc multipart upload của object storage.

### 7.2. Client ngắt khi đang download

Ở chiều download, controller có thể đã trả response headers `200 OK`, sau đó đang stream dữ liệu thì client ngắt. Khi response **đã commit**, Spring không thể đổi nó thành JSON `500` hay sửa status header. Server thường nhìn thấy IOException, “broken pipe”, “connection reset” hoặc tín hiệu cancellation; client nhận file thiếu và cần kiểm tra độ dài/hash.

Đối với file download cỡ lớn, `Content-Length` cho phép client phát hiện thiếu bytes nếu có thể; kiểm tra checksum (do server công bố qua kênh đáng tin) bảo vệ tốt hơn trường hợp dữ liệu hỏng. Để tải tiếp, server phải hỗ trợ **HTTP Range**/`Accept-Ranges`, trả `206 Partial Content` cho phạm vi hợp lệ, `416 Range Not Satisfiable` cho phạm vi không hợp lệ, dùng `ETag`/`If-Range` khi cần tránh ghép chunk từ hai phiên bản file khác nhau. **Spring không tự biến mọi response tùy chỉnh thành resumable download** chỉ vì header `Content-Length` được thiết lập.

### 7.3. Thành công ở server nhưng thất bại ở client

Có thể xảy ra:

~~~text
Server lưu file và commit metadata thành công
        |
        v
Server bắt đầu gửi HTTP 201
        |
        X kết nối bị cắt trước khi client nhận body
        |
        v
Client: “không biết upload thành công chưa”
Server: có thể đã có file hoàn chỉnh
~~~

Nếu client cứ retry POST mà mỗi lần sinh file mới, có thể tạo **bản sao không mong muốn**. Thiết kế production nên có `Idempotency-Key` hoặc một `uploadId` ổn định gắn với user/quyền truy cập và checksum. Client có thể hỏi trạng thái bằng GET có xác thực, tránh gửi lại file đã commit. Không dựa vào HTTP status mà client *không nhận được* để khẳng định kết quả nghiệp vụ.

## 8. Tệp tạm, cleanup và commit an toàn

Một quy trình phổ biến:

~~~text
RECEIVING
   |
   v
TEMPORARY file (chưa public)
   |
   +--> validate size, type, checksum, security
   |
   v
READY TO COMMIT
   |
   v
MOVE / object-storage finalize + metadata commit
   |
   v
COMPLETED (file được công bố)
~~~

Khi **thất bại**, phải có chuyển trạng thái rõ:

~~~text
RECEIVING / VALIDATING -> FAILED / ABORTED
                            |
                            v
                   cleanup tệp tạm/quota
                            |
                            v
                  ghi trạng thái để retry
~~~

Những điểm cần làm rõ trong thiết kế:

- **File tạm riêng cho request:** không để nhiều request ghi cùng tên người dùng cung cấp; dùng UUID, ID có tính duy nhất hoặc primitive tạo tệp tạm an toàn.
- **Lưu ở vị trí ngoài static roots:** không đưa tệp chưa kiểm tra vào `src/main/resources/static` hoặc thư mục public trực tiếp.
- **Atomic rename nếu hỗ trợ:** trên cùng filesystem, chuyển tên temp sang final bằng `Files.move(..., ATOMIC_MOVE)` khi phù hợp; fallback không có cùng bảo đảm. Object storage thường có mô hình hoàn tất upload riêng, không có file rename giống filesystem.
- **Xóa khi exception/cancel:** `try/finally` hoặc resource cleanup của framework; với reactive dùng cancellation-aware resource lifecycle. Nhưng cleanup trong process không bao phủ kill -9, JVM crash, mất điện: có scheduled cleanup/quota cho file `.part` hết hạn.
- **Commit DB và file không mặc nhiên cùng transaction:** có thể xảy ra file thành công nhưng DB thất bại hoặc ngược lại; dùng state machine, compensation/repair job và idempotency.
- **Kiểm tra storage errors:** `ENOSPC`/disk full, permission denied, quota exceeded, hash mismatch, antivirus failure phải có mã lỗi rõ và không trả 201.
- **Tài nguyên bị chiếm dụng:** mỗi multipart parser có thể dùng disk/memory ngay trước khi controller thấy file. Quota cần tính cho file temp, file final, concurrent uploads và container ephemeral storage.
- **Cleanup đúng khi tải về bị hủy:** download thường không tạo file tạm server, nhưng phải đóng stream và dọn tài nguyên đọc; nếu có tệp kết xuất động/temp archive cần quản lý riêng.

Một `finally` của controller không nhất thiết chạy khi client ngắt **trước khi multipart parser hoàn tất**; parser/container có lifecycle cleanup riêng. Cũng không chắc controller được gọi khi proxy chặn request ngay đầu.

## 9. Spring WebFlux: giới hạn và cancellation khác Servlet MVC

Ứng dụng sử dụng `spring-boot-starter-webflux` có mô hình xử lý reactive: controller có thể nhận `FilePart` (multipart file), dữ liệu có thể được xử lý qua `Mono`/`Flux` và connection cancellation lan theo reactive subscription. **Không dùng `MultipartFile` và property `spring.servlet.multipart.*` như thể chúng điều khiển WebFlux thuần.**

Ví dụ cấu hình Spring Boot WebFlux:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=5MB
spring.webflux.multipart.max-parts=4
~~~

**Ý nghĩa khác Servlet:**

- `max-in-memory-size` với **non-file part** giới hạn lượng lưu trong bộ nhớ; với **file part**, nó là ngưỡng để chuyển sang lưu đĩa. **Không phải** “tất cả file upload đều bị giới hạn đúng 256KB”.
- `max-disk-usage-per-part` giới hạn dung lượng lưu trên đĩa **mỗi part** khi multipart reader dùng kiểu lưu đĩa.
- `max-parts` giới hạn số part trong request, giúp tránh yêu cầu với số phần cực lớn.
- `spring.codec.max-in-memory-size` liên quan tới codec buffer (ví dụ đọc body thành một đối tượng), **không thay thế toàn bộ** các giới hạn multipart riêng.
- Với đường xử lý streaming PartEvent, cần hiểu các giới hạn nào áp dụng hoặc bị bỏ qua; đặt quota và đếm byte ở tầng nhận dữ liệu khi không dùng cơ chế aggregate mặc định.

Ví dụ **đoạn minh họa** của WebFlux `FilePart`, không phải một controller độc lập:

~~~java
@PostMapping(
        path = "/reactive-files",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> upload(@RequestPart("file") FilePart file) {
    Path destination = /* đường dẫn tạm an toàn do server tạo */;
    return file.transferTo(destination);
}
~~~

Snippet cố tình chưa triển khai validation, tên file, cleanup, size quota và commit: **không sử dụng nguyên trạng trong production**. Mục đích là nhận ra `FilePart.transferTo(Path)` trả `Mono<Void>`, nên phải **return/compose** publisher để WebFlux subscribe và xử lý completion/error/cancellation; không gọi `.block()` trên event-loop, không tự `subscribe()` rồi trả response 201 ngay.

Nếu tự xử lý `Flux<DataBuffer>` để stream nội dung, phải tuân thủ quản lý buffer **reference-counted**: giải phóng buffer (`DataBufferUtils.release`) khi sở hữu chúng, tránh bỏ qua buffer trên đường error/cancel. Nhiều API helper của Spring đã quản lý phần này; không tự release khi API đã chuyển quyền sở hữu, vì double-release cũng sai.

### Cancellation và cleanup trong WebFlux

Khi browser hủy upload, subscription có thể nhận tín hiệu **cancel**; nó khác `onError`. Do đó chỉ dùng `doOnError(...)` để xóa temp sẽ bỏ sót cancel. Sử dụng lifecycle cleanup như `usingWhen(...)` với các nhánh complete/error/cancel khi tài nguyên thuộc trách nhiệm ứng dụng, hoặc xử lý `doFinally(SignalType)` cẩn thận. **Không thực hiện thao tác filesystem blocking trực tiếp trong event-loop**; dùng scheduler thích hợp nếu bắt buộc. Sau completion, cần kiểm tra size/hash/format trước khi trả 201.

Trong Spring WebFlux, việc exception mapping thường thông qua `@RestControllerAdvice`/`@ExceptionHandler` reactive và các WebExceptionHandler; kiểu exception cụ thể cho quota/parser có thể khác với Servlet `MaxUploadSizeExceededException`, chẳng hạn `DataBufferLimitException` hoặc multipart parsing exceptions. **Không copy handler MVC `MaxUploadSizeExceededException` rồi kỳ vọng bắt được mọi lỗi WebFlux.** Đọc exception thật từ phiên bản Spring và thiết lập mapping status hợp đồng thích hợp.

## 10. Kiểm thử ngắt giữa chừng và lỗi thực tế

### 10.1. Kiểm thử manual có kiểm soát

Để mô phỏng client dừng giữa upload, gửi một file **nhỏ hơn giới hạn server**, cố tình giảm tốc độ truyền rồi cho cURL timeout; làm trong môi trường test, không chạy với dữ liệu thật.

Ví dụ Linux/macOS:

~~~bash
dd if=/dev/zero of=slow.pdf bs=1024 count=1500
printf '%s' '%PDF-' | dd of=slow.pdf conv=notrunc status=none
curl --limit-rate 1024 --max-time 2 \
  -F "file=@slow.pdf;type=application/pdf" \
  http://localhost:8080/files
~~~

Tùy hệ điều hành/cURL và đường truyền localhost, kết quả **có thể** là lỗi timeout của cURL, 413 nếu tầng khác có limit thấp hơn, hoặc dạng lỗi khác. Đây là thao tác gợi tình huống; để kiểm thử tự động ổn định cần fault injection/test proxy kiểm soát socket close.

Điều quan trọng để quan sát: nếu request không hoàn tất, ứng dụng không được có file final nửa vời; tệp `.part` phải được dọn theo lifecycle hoặc bằng job cleanup. Không yêu cầu client phải nhận được JSON khi socket đã đóng.

### 10.2. Phân biệt ba lớp test

| Lớp test | Xác minh được | Chưa chứng minh |
| --- | --- | --- |
| Unit test guard/validator | Check MIME/signature, size, tên file và lỗi 422/415 | Parser HTTP thật hoặc proxy |
| `MockMvc` test | Mapping controller, handler, response contract, app-level guard | Giới hạn real socket/container, cancel/upload streaming |
| Test HTTP thật với embedded server | Multipart parser + networking + Spring handler | Chính sách proxy/ingress của production nếu test không có proxy |
| End-to-end qua reverse proxy | 413/timeout thực tế, quy tắc upload và dọn dẹp dưới deployment | Không tự bảo đảm mọi điều kiện rơi mạng; cần fault injection và tải đồng thời |

Các case nên có trong test suite triển khai thực tế:

1. File 0B; file 1 byte dưới giới hạn; file đúng giới hạn; file lớn hơn 1 byte.
2. Tổng request (nhiều part/metadata) vượt `max-request-size` mặc dù từng file hợp lệ.
3. Missing file part, sai field name, thiếu boundary, malformed multipart, outer content-type sai.
4. MIME khai báo sai; đuôi giả; signature sai; file PDF thực bị hỏng; file nén có expansion ratio quá lớn.
5. Hai uploads đồng thời; giới hạn quota theo user; cùng idempotency key retry.
6. Client disconnect trước parser hoàn thành, đang ghi file tạm, sau commit nhưng trước khi nhận 201.
7. Server disk full, permission denied, timeout object storage; xác nhận không còn bản final không hợp lệ.
8. Download ngắt giữa stream; xác nhận client phát hiện thiếu bytes, server đóng resource và download lại đúng.
9. Proxy gửi 413 sớm; xác nhận client hiểu lỗi dù ứng dụng không hề ghi log controller.
10. Restart process giữa upload; cleanup tệp .part quá hạn không xóa nhầm upload đang hoạt động.

## 11. Observability: ghi nhận đúng nguyên nhân, không log nhầm 5xx

Các thông tin có ích trong log và metrics:

- `requestId`/traceId do hệ thống sinh hoặc xác thực chính sách; user/tenant ID đã xác thực nếu có.
- Endpoint, phương thức, status, **tầng chặn** (proxy/container/parser/app/storage).
- Loại lỗi: `SIZE_LIMIT`, `INVALID_MULTIPART`, `UNSUPPORTED_TYPE`, `CONTENT_VALIDATION`, `CLIENT_DISCONNECT`, `STORAGE_FAILURE`.
- Byte nhận/gửi thực tế khi có thể đo chính xác; bytes client *khai báo* chỉ là metadata chưa đáng tin.
- Thời gian upload/download, số upload đang chạy, dung lượng temporary files/quota, số cleanup thất bại.
- Trạng thái nghiệp vụ `RECEIVING`, `VALIDATING`, `COMMITTED`, `FAILED`, `ABORTED` để xử lý retry, thay vì suy diễn chỉ từ HTTP status.

Không log raw file bytes, bearer token, toàn bộ multipart body, tên file người dùng gửi chưa làm sạch hoặc đường dẫn nhạy cảm. Một `broken pipe` từ client đóng tab không nhất thiết là lỗi business 500 cần báo động. Ngược lại, số lượng client abort tăng đột biến có thể báo vấn đề mạng, timeout hoặc phản hồi server quá chậm.

Cẩn thận với request correlation: proxy có thể từ chối request **trước khi có log trong app**, nên cần đối chiếu ingress access log với server/application metrics.

## 12. Quyết định về retry và resumability

**Retry toàn bộ request** đơn giản nhưng chỉ an toàn khi operation có cơ chế ngăn bản sao, ví dụ:

- Client gửi `Idempotency-Key` hoặc upload token ổn định, được ràng buộc với danh tính và mục đích upload.
- Server lưu trạng thái theo key: `IN_PROGRESS`, `COMPLETED`, `FAILED`, có TTL và policy đồng thời.
- Nếu request cũ đã commit, retry trả **cùng kết quả đã lưu** hoặc trạng thái; không ghi một file khác.
- Có checksum/object metadata để phân biệt hai request dùng chung key nhưng dữ liệu khác nhau.
- Upload lớn dùng protocol chunk/resume cụ thể: offset chính xác, chunk checksum, verify file tổng, commit marker, cleanup chunks orphaned.

Đối với download, retry đơn giản từ đầu có thể đủ cho file nhỏ; file lớn cần download range/resume và kiểm tra nội dung không đổi giữa các đoạn. **Không tự đặt header `Range` trong POST upload** với kỳ vọng Spring Boot tự hiểu resumable upload.

## 13. Checklist thiết kế API tải/nhận tệp

1. Có xác định rõ **giới hạn mỗi file, tổng request, số part, quota/tốc độ và timeout** ở proxy, container, Spring và business không?
2. Có phân biệt **outer media type**, **part media type**, file signature và kiểm tra cấu trúc thực sự không?
3. Có tránh đường dẫn từ `getOriginalFilename()` và không công khai file đang upload chưa hoàn tất không?
4. Có dùng tệp tạm/commit theo trạng thái rõ và cleanup trên exception, cancel, crash không?
5. Khi client mất response, có API tra cứu trạng thái và idempotency key để tránh duplicate không?
6. API download có `Content-Length`, `Content-Type`, `Content-Disposition` phù hợp, kiểm tra quyền và checksum/range khi cần không?
7. Có xử lý lỗi storage/antivirus/quota mà không trả 201 sớm không?
8. Handler có phân biệt lỗi 413/400/415/422, và có biết lỗi từ proxy không chạy qua controller không?
9. Test có đi qua networking/proxy thật cho case limit/abort, không chỉ dựa vào `MockMvc` không?
10. Log/metrics có ghi loại lỗi và giai đoạn mà không lộ nội dung file hoặc nhầm client abort thành lỗi server không?

## 14. Câu hỏi tự kiểm tra

**Tình huống A:** Spring `max-file-size=20MB` nhưng ingress giới hạn 5MB, upload 7MB bị lỗi. Thay đổi controller có sửa được không?

**Đáp án:** Không. Proxy có thể chặn 413 trước khi request tới controller. Cần điều chỉnh **giới hạn ingress** nếu chính sách cho phép, đồng thời đối chiếu các limit ở Spring.

**Tình huống B:** Multipart body hợp lệ, file tên `invoice.pdf`, header part khai báo `application/pdf` nhưng bytes bắt đầu `NOTPDF`. Có nên lưu?

**Đáp án:** Không. Tên file và MIME do client khai báo không phải bằng chứng; ví dụ validator sẽ trả 422 vì signature không đạt. Với production dùng parser/scan sâu hơn.

**Tình huống C:** Client đã gửi gần đủ file, đột ngột mất mạng; server chưa nhận completion. Có nên đổi tên tệp tạm thành final và trả 201?

**Đáp án:** Không. File chưa được xác minh hoàn chỉnh; nên hủy/cleanup hoặc giữ phần dữ liệu trong một **giao thức resume** có trạng thái rõ. Connection đã ngắt thì không thể bảo đảm trả 201/400.

**Tình huống D:** Server đã commit file rồi client không nhận được 201, client retry cùng nội dung. Làm sao tránh duplicate?

**Đáp án:** Idempotency key/upload ID + trạng thái có thể truy vấn. Server phải quyết định outcome theo key và checksum, không phụ thuộc việc client có nhận response hay không.

**Tình huống E:** Endpoint `@RequestPart MultipartFile` chạy trên MVC; bạn chuyển sang WebFlux và cấu hình `spring.servlet.multipart.max-file-size`. Có đủ không?

**Đáp án:** Không. WebFlux dùng `FilePart`, multipart reader và properties riêng. Cần giới hạn memory/disk/parts, quota business và cancellation-safe cleanup.

**Tình huống F:** Download 200 OK đã gửi headers, giữa chừng client đóng kết nối. Có đổi response thành 500 JSON được không?

**Đáp án:** Không. Khi response đã commit, status/header không thể đổi; client có thể chỉ thấy file thiếu hoặc socket error, server cần dọn resource đọc và ghi nhận disconnect.

## 15. Tài liệu chính thức

- [Spring Boot — Uploading Files](https://spring.io/guides/gs/uploading-files/): tích hợp Spring MVC multipart và `spring.servlet.multipart.max-file-size`, `max-request-size`.
- [Spring Boot 3.3 — MultipartProperties](https://docs.spring.io/spring-boot/docs/3.3.0-SNAPSHOT/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html): default 1MB/file, 10MB/request, vị trí/threshold.
- [Spring Framework 6.1 — MaxUploadSizeExceededException](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/multipart/MaxUploadSizeExceededException.html): exception size trong MVC.
- [Spring Framework — WebFlux Multipart](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): multipart reader, resource limits, `DataBuffer` và cancellation.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html): cấu hình Servlet/WebFlux multipart và codec.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): ý nghĩa 413, 415, 422, timeout và giới hạn response đã gửi.
- [Spring Framework — Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): xử lý multipart ở Spring MVC.

**Ghi nhớ:** xử lý upload/download vững chắc phải đặt giới hạn sớm, kiểm tra kiểu nội dung thật, lưu tạm rồi commit sau khi thành công, cleanup cho lỗi và ngắt kết nối, thiết kế retry có idempotency. Không thể giả định mọi lỗi đều đi qua controller hoặc mọi request bị ngắt đều nhận được HTTP error response.
