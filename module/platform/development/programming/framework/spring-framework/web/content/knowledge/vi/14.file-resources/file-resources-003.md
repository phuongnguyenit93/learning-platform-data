# Giới hạn dung lượng, số tệp, kiểu tệp và tên tệp không tin cậy trong Spring MVC

## 1. Mục tiêu và phạm vi

Upload không chỉ là nhận một đối tượng `MultipartFile` rồi ghi bytes xuống ổ đĩa. Client kiểm soát dữ liệu, tên tệp và nhiều HTTP headers, có thể cố tình gửi quá nhiều tệp, tệp quá lớn, định dạng giả mạo, metadata bất thường hoặc một tài liệu mà lúc giải mã phình ra hàng gigabyte. API cần nhiều tầng phòng vệ để tránh chiếm tài nguyên, ghi đè tệp, path traversal, XSS và lộ dữ liệu.

Bài này tập trung **Spring MVC (Servlet stack), Java 17+, Spring Boot 3.x/Spring Framework 6.x**, bao gồm:

- Phân biệt giới hạn **một file**, **một multipart request**, **số file/part**, quota và concurrency.
- Cấu hình `spring.servlet.multipart.max-file-size`, `max-request-size`, `file-size-threshold` và vai trò Servlet container/proxy.
- Kiểm tra `MultipartFile.isEmpty()`, `getSize()`, kiểu file, magic bytes và nội dung bằng parser tin cậy.
- Vì sao `getContentType()` và `getOriginalFilename()` là dữ liệu **không đáng tin**.
- Sinh storage key ngẫu nhiên, lưu ngoài webroot, xử lý rollback/cleanup, scan/quarantine và quyền download.
- Phân biệt lỗi HTTP 400/413/415 và nơi lỗi được phát hiện.
- Xây ví dụ Spring Boot 3 có thể chạy cùng curl, MockMvc, bảng tình huống kiểm thử và checklist production.

**Ranh giới bảo mật:** Ví dụ code chỉ nhận PNG/JPEG và kiểm tra magic bytes, không có image decoder/antivirus; **không đủ an toàn để tự động phát ảnh cho người dùng trên production**. Nếu triển khai thật, cần kiểm tra cấu trúc tệp đầy đủ, giới hạn pixel/CPU, tái mã hóa, quét malware và quyền truy cập theo rủi ro.

## 2. Đường đi của multipart upload

```text
Client: multipart/form-data
         |
         v
Reverse proxy / CDN / WAF
  [body bytes, rate limit, timeouts, connection limits]
         |
         v
Servlet container (Tomcat / Jetty / Undertow)
  [parse parts, temp space, header and part limits]
         |
         v
Spring multipart handling
  [MultipartConfigElement / StandardServletMultipartResolver]
  [spring.servlet.multipart.*]
         |
         v
Spring MVC controller
  @RequestParam("files") List<MultipartFile>
         |
         v
Application policy
  [1..3 files, no empty, <=2 MiB each]
  [allowlist type + signature + full format validation]
         |
         v
Private staging / AV / CDR / decoder / metadata
         |
         v
Private accepted storage, authorized download
         |
         v
JSON response with server-generated ID, never raw path
```

Mỗi tầng bảo vệ một vấn đề khác. `max-file-size` không thay hạn mức số multipart parts; một check `files.size()` chỉ chạy **sau khi parser đã xử lý request**; chỉ dùng antivirus cũng không thay rate limiting. Trong hệ thống thật cần limits nhất quán từ edge đến service.

### Khác biệt file và multipart part

Một `multipart/form-data` request có nhiều phần: file, chuỗi text, các field ẩn và metadata. Nhiều part không phải file vẫn khiến parser dùng RAM/CPU/disk. Vì vậy policy “tối đa ba file” **khác** “tối đa ba part”; cần kiểm soát cả số part ở container và số file ở application.

## 3. MultipartFile: những giá trị nào đáng tin?

Ví dụ controller:

```java
@PostMapping(path = "/api/uploads",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<?> upload(
        @RequestParam("files") List<MultipartFile> files) {
    // Xử lý policy ở service rồi lưu vào vùng riêng.
}
```

Đây chỉ là snippet controller; ứng dụng đầy đủ ở phần sau.

| API | Ý nghĩa | Cần lưu ý |
| --- | --- | --- |
| `getName()` | Tên parameter/part, ví dụ `files` | Không dùng làm path |
| `getOriginalFilename()` | Tên do **client** khai báo | Không tin, có thể chứa `../` hoặc backslash |
| `getContentType()` | MIME client khai báo cho **part** | Dễ giả mạo, có thể null |
| `getSize()` | Dung lượng bytes đã nhận cho file | Cần check nhưng đã qua bước parse |
| `isEmpty()` | Empty hoặc chưa chọn file | Cần policy nếu file không được rỗng |
| `getInputStream()` | Stream bytes file đã upload | Phải đóng stream; tránh đọc hết file lớn vào heap |
| `transferTo(Path/File)` | Chuyển/copy part sang nơi khác tùy implementation | Chỉ truyền path do server tạo |

`getOriginalFilename()` là điểm Spring Javadoc đặc biệt cảnh báo: có thể chứa đường dẫn hoặc ký tự độc hại, không dùng nguyên tên trong filesystem. Không dùng `getContentType()` làm bằng chứng rằng bytes là PNG/PDF. Header do client đặt được.

`MultipartFile` gắn với vòng đời multipart request. Không giữ object này trong background queue để đọc sau khi request kết thúc; nếu cần scan async, copy sang vùng staging riêng và chỉ truyền storage ID cho worker.

## 4. Cấu hình giới hạn ở Spring Boot 3

```properties
spring.servlet.multipart.enabled=true

# Tối đa 2 MiB/file
spring.servlet.multipart.max-file-size=2MB

# Tổng multipart request tối đa 7 MiB
spring.servlet.multipart.max-request-size=7MB

# Ngưỡng chuyển nội dung multipart ra temp disk
spring.servlet.multipart.file-size-threshold=0B

# Property tùy chỉnh của ứng dụng mẫu
app.upload.directory=./private-uploads
```

Ý nghĩa:

- `max-file-size` giới hạn từng file trong multipart, Boot 3.x mặc định thường **1MB**.
- `max-request-size` giới hạn toàn request bao gồm bytes của file, field text, boundary và headers từng part, Boot 3.x thường mặc định **10MB**.
- `file-size-threshold` quyết định thời điểm dữ liệu được ghi vào disk; **không phải** giới hạn file upload.
- `spring.servlet.multipart.location` có thể chỉ định thư mục **tạm** cho multipart parser; không nên nhầm nơi tạm với nơi lưu bền.
- `app.upload.directory` là cấu hình riêng của demo, không phải Spring Boot tự phát sinh storage service.

Nếu ba file × 2MiB = 6MiB, giới hạn request 7MiB để dành overhead là ví dụ hợp lý cho một bài học, **không đảm bảo đủ mọi multipart request hợp lệ**. Filename/field metadata và proxy overhead có thể làm thay đổi tổng bytes.

### Giới hạn ở edge và Servlet container

Reverse proxy có thể chặn body ở mức nhỏ hơn Boot config. Container có thể có chính sách riêng về số multipart parts, request parameters, kích thước headers, thời gian nhận dữ liệu và thư mục lưu tạm. Cách cấu hình khác nhau theo Tomcat/Jetty/Undertow **và từng phiên bản**; không tự bịa một property chung cho tất cả. Cần đọc đúng tài liệu server đang chạy.

App-level check `getSize()` không ngăn parser đọc request lớn trước khi service chạy. Do đó ba tầng **gateway / multipart container / ứng dụng** nên cùng có trần.

## 5. Giới hạn số lượng file và quota

Hợp đồng API ví dụ: **1–3 file cho mỗi request**. Một kiểm tra sau parse:

```java
if (files == null || files.isEmpty()) {
    throw rejected("At least one file is required");
}
if (files.size() > 3) {
    throw rejected("At most three files are allowed");
}
```

Đây là snippet trong service sẽ định nghĩa bên dưới. Việc đếm file hữu ích cho nghiệp vụ nhưng chưa chặn một request chứa hàng nghìn **text parts**. Production có thể cần thêm:

- Số multipart parts/fields, độ dài mỗi field, tổng metadata bytes.
- Số file và tổng bytes mỗi người dùng/ngày, mỗi tenant, tổng quota storage.
- Tốc độ upload và số request đồng thời; timeout cho client gửi chậm.
- Số tác vụ giải mã/quét virus chạy đồng thời; CPU/RAM/disk budget.
- Số phần tử và tổng bytes **sau giải nén**, ngăn ZIP bombs.
- Số pixel và số frame ảnh/video để ngăn file nhỏ giải mã thành dữ liệu khổng lồ.

Các hạn mức này phải đặt ở lớp thực sự nhìn thấy chúng: container không biết quota nghiệp vụ user, còn service sau parse không chặn mọi chi phí parser.

## 6. Xác thực loại file: extension, MIME, signature và decoder

| Tín hiệu | Ví dụ | Độ tin cậy |
| --- | --- | --- |
| Extension tên gốc | `avatar.png` | Thấp: client đổi được |
| `MultipartFile.getContentType()` | `image/png` | Thấp: client giả mạo được |
| Magic bytes | PNG: `89 50 4E 47 0D 0A 1A 0A` | Kiểm tra sơ bộ, vẫn giả được |
| Full decoding và validation | Parser ảnh an toàn đọc được cấu trúc | Mạnh hơn, vẫn cần giới hạn tài nguyên |
| Re-encode/scan/CDR | Tạo ảnh sạch hoặc lọc active content | Defense in depth phù hợp định dạng |

### Magic bytes không có nghĩa ảnh an toàn

PNG có 8 byte signature, JPEG thường bắt đầu `FF D8 FF`. Một file 8 byte đúng header PNG nhưng không có image data có thể qua phép check signature mà không phải ảnh thực sự. Một file có header hợp lệ vẫn có thể chứa metadata, đoạn dữ liệu hỏng hoặc payload tấn công parser.

Trong demo, `detectSignature` chỉ đảm bảo phần đầu phù hợp format cho phép; **không** cam kết valid PNG/JPEG. Với production cần dùng decoder đầy đủ, giới hạn resolution/pixel/frames, chống decompression bombs, re-encode và quét malware theo mức rủi ro.

Không mở rộng allowlist sang SVG, PDF, DOCX, ZIP hoặc EXE chỉ bằng cách thêm vài magic bytes. Mỗi format có active content, macro, archive entry, parser và chính sách riêng.

### Content-Type của request khác MIME của file part

Request `Content-Type: multipart/form-data` mô tả envelope. `Content-Type: image/png` của từng part do client khai báo loại file. Endpoint `consumes=multipart/form-data` nhận sai envelope thì thường **415 Unsupported Media Type**; file part có bytes sai policy, nhưng multipart parse được, ứng dụng có thể trả **400 Bad Request**.

## 7. Tên file gốc không tin cậy

Các chuỗi không nên dùng làm file path:

```text
../../etc/passwd
..\..\windows\system.ini
report.pdf.exe
avatar.PNG
.htaccess
CON
photo.jpg:payload
name%2e%2e%2fsecret.png
Tên rất dài / Unicode gây nhầm lẫn / control chars
```

Rủi ro gồm path traversal, ghi đè tệp, thiết bị đặc biệt, Alternate Data Streams trên Windows, collision trên filesystem case-insensitive, tên Unicode tương đương, HTTP header injection khi dùng `Content-Disposition` và XSS khi hiện tên trên HTML.

**Chiến lược an toàn nhất:** Sinh key storage bởi server, hoàn toàn **không dùng getOriginalFilename để quyết định path**. Ví dụ `Files.createTempFile(privateRoot, "uploaded-", ".png")` sau khi server xác minh loại. Nếu muốn lưu original name để hiển thị, đặt trong metadata riêng, giới hạn bytes/ký tự theo policy, normalize Unicode, escape theo output context; không làm khóa phân quyền hay nguồn extension.

Chỉ gọi `Paths.get(originalFilename).getFileName()` không xóa hết rủi ro: tên còn có thể là device name, quá dài, trùng nhau, chứa Unicode trick và control characters. Không dùng tên client để save file ngay cả khi đã cắt đoạn `../`.

## 8. Storage an toàn và lifecycle

Tách bốn vùng logic:

1. **Temporary multipart space**: container tạo khi parse, có vòng đời tạm.
2. **Private staging/quarantine**: file đã nhận nhưng chưa kiểm tra hết.
3. **Accepted private storage**: file đã pass policy và scan, có metadata/owner/tenant.
4. **Authorized delivery**: API download nhận opaque ID, kiểm tra quyền, phát headers đúng.

Với filesystem, dùng thư mục **ngoài webroot** và không tạo public static mapping tới thư mục upload. Chỉ process ứng dụng được ghi vào vùng cần thiết, không execute; tránh filesystem path dưới sự kiểm soát người dùng. Với object storage, bucket/object mặc định private; cân nhắc presigned URL thời hạn ngắn chỉ sau authorization/scan.

Khi lỗi giữa nhiều file, cần xóa các file được tạo trong request. Nếu ứng dụng crash hoặc DB commit thất bại, cần cleanup job/orphan reconciliation vì filesystem và database không có transaction ACID chung. Upload chưa quét xong không nên được trả ra public.

## 9. API contract ví dụ

```text
POST /api/uploads
Content-Type: multipart/form-data
1..3 file parts có cùng name = "files"
Mỗi file không rỗng, tối đa 2 MiB
Chỉ cho phép PNG/JPEG theo signature sơ bộ
Khi MIME part được khai báo thì phải khớp signature
Tên file lưu do server sinh; không công khai raw path
```

Ví dụ JSON thành công, `id` và `size` chỉ là minh họa:

```json
{
  "files": [
    {
      "id": "uploaded-483927102931.png",
      "mediaType": "image/png",
      "size": 1024
    }
  ]
}
```

Demo trả HTTP `201 Created` khi file đã lưu riêng theo policy sơ bộ; `id` là storage key nội bộ, **không phải URL public**. Trong hệ thống cần scan async, có thể trả `202 Accepted` + job ID và trạng thái chờ trước khi cho tải.

## 10. Ứng dụng Spring Boot 3 Java 17+ chạy được

Cần project Maven Spring Initializr với Java 17+, `spring-boot-starter-web` và `spring-boot-starter-test` (test scope). Không cần database. Các tệp đặt trong package `com.example.demo`:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  UploadRejectedException.java
  UploadService.java
  UploadController.java
  UploadExceptionHandler.java
src/main/resources/application.properties
src/test/java/com/example/demo/UploadControllerTest.java
```

### 10.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 10.2. UploadRejectedException.java

```java
package com.example.demo;

import org.springframework.http.HttpStatus;

public class UploadRejectedException extends RuntimeException {
    private final HttpStatus status;

    public UploadRejectedException(HttpStatus status, String message) {
        super(message);
        this.status = status;
    }

    public HttpStatus getStatus() {
        return status;
    }
}
```

Exception này chỉ biểu diễn **input bị từ chối theo policy**. Lỗi `IOException` khi ghi disk không được tự chuyển thành HTTP 400, vì đó có thể là sự cố server.

### 10.3. UploadService.java

```java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class UploadService {

    private static final int MAX_FILES = 3;
    private static final long MAX_FILE_BYTES = 2L * 1024 * 1024;
    private static final byte[] PNG_MAGIC = {
        (byte) 0x89, 0x50, 0x4E, 0x47,
        0x0D, 0x0A, 0x1A, 0x0A
    };

    private final Path root;

    public UploadService(Environment environment) {
        String directory = environment.getProperty(
                "app.upload.directory", "./private-uploads");
        this.root = Path.of(directory).toAbsolutePath().normalize();
    }

    public List<UploadedFile> store(List<MultipartFile> files)
            throws IOException {

        if (files == null || files.isEmpty()) {
            throw rejected("At least one file is required");
        }
        if (files.size() > MAX_FILES) {
            throw rejected("At most three files are allowed");
        }

        // Xác thực toàn bộ danh sách trước khi tạo file lưu.
        List<Kind> types = new ArrayList<>();
        for (MultipartFile file : files) {
            if (file.isEmpty()) {
                throw rejected("Empty files are not allowed");
            }
            if (file.getSize() > MAX_FILE_BYTES) {
                throw new UploadRejectedException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "Each file must be at most 2 MiB");
            }

            // Không dùng getOriginalFilename() làm file path.
            Kind kind = detectSignature(file);
            String declared = file.getContentType();
            if (declared != null && !declared.isBlank()
                    && !kind.mediaType().equals(
                        declared.toLowerCase(Locale.ROOT))) {
                throw rejected(
                    "Declared type does not match detected type");
            }
            types.add(kind);
        }

        Files.createDirectories(root);
        List<Path> created = new ArrayList<>();
        List<UploadedFile> results = new ArrayList<>();

        try {
            for (int i = 0; i < files.size(); i++) {
                Kind kind = types.get(i);
                Path destination = Files.createTempFile(
                        root, "uploaded-", "." + kind.extension());
                created.add(destination);

                try (InputStream in = files.get(i).getInputStream()) {
                    Files.copy(in, destination,
                            StandardCopyOption.REPLACE_EXISTING);
                }

                results.add(new UploadedFile(
                    destination.getFileName().toString(),
                    kind.mediaType(), Files.size(destination)));
            }
            return List.copyOf(results);
        } catch (IOException | RuntimeException error) {
            for (Path path : created) {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException cleanupError) {
                    error.addSuppressed(cleanupError);
                }
            }
            throw error;
        }
    }

    private Kind detectSignature(MultipartFile file) throws IOException {
        byte[] header;
        try (InputStream in = file.getInputStream()) {
            header = in.readNBytes(8);
        }

        if (Arrays.equals(header, PNG_MAGIC)) {
            return new Kind("image/png", "png");
        }
        if (header.length >= 3
                && (header[0] & 0xFF) == 0xFF
                && (header[1] & 0xFF) == 0xD8
                && (header[2] & 0xFF) == 0xFF) {
            return new Kind("image/jpeg", "jpg");
        }
        throw rejected("Only PNG and JPEG signatures are permitted");
    }

    private UploadRejectedException rejected(String message) {
        return new UploadRejectedException(
                HttpStatus.BAD_REQUEST, message);
    }

    private record Kind(String mediaType, String extension) {}

    public record UploadedFile(
            String id, String mediaType, long size) {}
}
```

Phân tích code:

- Tối đa ba `MultipartFile` và tối đa 2MiB/file; số part toàn request cần container limit riêng.
- `getSize()` defense in depth **sau** parser; parser có cấu hình max sizes.
- `detectSignature` đọc tối đa 8 bytes đầu, xác minh sơ bộ PNG/JPEG. **Không xác minh toàn ảnh.**
- MIME part do client khai báo chỉ được check thêm, không quyết định sự an toàn.
- Không đọc original filename, không lấy extension client để tạo destination.
- `Files.createTempFile` sinh tên server, chỉ trong thư mục do cấu hình server kiểm soát.
- `Files.copy` đích là file tạm mới; `REPLACE_EXISTING` ở đây chỉ ghi vào file **do chính server vừa tạo**, không ghi đè path do client đặt.
- Nếu copy thất bại, cố xóa tất cả file đã tạo trong request; cần cleanup định kỳ khi crash hoặc DB lỗi.
- Code không đặt permission riêng hoặc chống adversarial symlink trong thư mục: production phải quản lý owner, private volume và đảm bảo user khác không sửa thư mục.
- Service có thể bị lỗi storage, khi đó không nên trả “file type invalid” mà phải log/báo lỗi hệ thống thích hợp.

**Không đưa file mẫu này lên Internet như một API public mà không có authn/authz/quota/scanner/decoder đầy đủ.** Upload trả ID không có nghĩa file đã sẵn sàng cho download.

### 10.4. UploadController.java

```java
package com.example.demo;

import java.io.IOException;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    private final UploadService service;

    public UploadController(UploadService service) {
        this.service = service;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<UploadResponse> upload(
            @RequestParam("files") List<MultipartFile> files)
            throws IOException {

        List<UploadService.UploadedFile> saved = service.store(files);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new UploadResponse(saved));
    }

    public record UploadResponse(
            List<UploadService.UploadedFile> files) {}
}
```

Controller phụ trách HTTP status và JSON, không chấp nhận user gửi storage path. Nếu hoàn toàn thiếu `files` part bắt buộc, Spring MVC có thể từ chối 400 ở argument resolution **trước khi service chạy**.

### 10.5. UploadExceptionHandler.java

```java
package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class UploadExceptionHandler {

    @ExceptionHandler(UploadRejectedException.class)
    public ResponseEntity<ApiError> rejected(
            UploadRejectedException ex) {
        return ResponseEntity.status(ex.getStatus())
                .body(new ApiError(
                    "UPLOAD_REJECTED", ex.getMessage()));
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ApiError> oversized(
            MaxUploadSizeExceededException ex) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(new ApiError(
                    "UPLOAD_TOO_LARGE",
                    "Multipart request exceeds configured limits"));
    }

    public record ApiError(String code, String message) {}
}
```

Nếu multipart parsing exception đến được MVC resolver, advice có thể trả 413. Nếu proxy hoặc container từ chối **trước DispatcherServlet**, advice không bắt được lỗi gốc: body có thể khác hoặc kết nối bị đóng. Không bắt toàn bộ `Exception` rồi trả 400; lỗi disk full/IO thuộc hạ tầng.

### 10.6. application.properties

```properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=2MB
spring.servlet.multipart.max-request-size=7MB
spring.servlet.multipart.file-size-threshold=0B
app.upload.directory=./private-uploads
```

`./private-uploads` chỉ dùng demo. Production đặt trên volume riêng bên ngoài webroot, giới hạn quyền process, có scan và cleanup.

### 10.7. Chạy ứng dụng

```bash
./mvnw spring-boot:run
```

PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Lệnh yêu cầu dự án Maven Boot có wrappers và dependencies; không chạy `javac UploadService.java` độc lập khi thiếu classpath Spring.

## 11. curl: thử upload và lỗi

### 11.1. Một tệp PNG

```bash
curl -i http://localhost:8080/api/uploads \
  -F "files=@photo.png;type=image/png"
```

Nếu `photo.png` là file nhỏ có PNG signature, app trả 201 và JSON gồm `files[0].id`, `mediaType`, `size`. Không assert id ngẫu nhiên. Demo chưa giải mã toàn ảnh.

### 11.2. Hai tệp

```bash
curl -i http://localhost:8080/api/uploads \
  -F "files=@photo.png;type=image/png" \
  -F "files=@photo.jpg;type=image/jpeg"
```

Lặp cùng tên part `files` để tạo `List<MultipartFile>`. Không tự set boundary header khi dùng `curl -F`, curl tự tạo boundary đúng.

### 11.3. Loại không hợp lệ

```bash
curl -i http://localhost:8080/api/uploads \
  -F "files=@notes.txt;type=text/plain"
```

Nếu bytes không khớp PNG/JPEG signature: `400 Bad Request` với `UPLOAD_REJECTED`. Đổi extension/MIME thành png không làm bytes của file biến thành ảnh, dù kẻ tấn công có thể giả magic bytes; đó là lý do cần decoder/scanner.

### 11.4. Bốn file trong một request

```bash
curl -i http://localhost:8080/api/uploads \
  -F "files=@photo.png;type=image/png" \
  -F "files=@photo.png;type=image/png" \
  -F "files=@photo.png;type=image/png" \
  -F "files=@photo.png;type=image/png"
```

Nếu request vẫn ở dưới multipart limits, service trả **400** vì count >3. Nếu tổng bytes vượt `max-request-size`, parser/gateway có thể từ chối sớm bằng 413. Không dựa vào thứ tự xử lý để khẳng định bốn file luôn cho 400.

### 11.5. File >2MiB

Request có file lớn có thể bị multipart parser chặn trước controller, thường HTTP **413** qua framework/container mapping tương ứng. Với `MockMultipartFile` trong MockMvc, parser limit không được mô phỏng đầy đủ; service check size vẫn có thể được test riêng.

### 11.6. Sai Content-Type request

```bash
curl -i http://localhost:8080/api/uploads \
  -H "Content-Type: application/json" \
  --data '{"files":[]}'
```

Thông thường **415** vì endpoint chỉ chấp nhận `multipart/form-data`. Không nhầm envelope media type với `image/png` của từng part.

## 12. Kiểm thử MockMvc

Tạo `src/test/java/com/example/demo/UploadControllerTest.java` trong dự án có `spring-boot-starter-test`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "app.upload.directory=./target/test-private-uploads",
    "spring.servlet.multipart.max-file-size=2MB",
    "spring.servlet.multipart.max-request-size=7MB"
})
@AutoConfigureMockMvc
class UploadControllerTest {

    @Autowired MockMvc mvc;

    private static final byte[] PNG_HEADER = {
        (byte) 0x89, 0x50, 0x4E, 0x47,
        0x0D, 0x0A, 0x1A, 0x0A
    };

    private MockMultipartFile png(String filename) {
        return new MockMultipartFile(
            "files", filename, "image/png", PNG_HEADER);
    }

    @Test
    void serverNameDoesNotUseClientPath() throws Exception {
        mvc.perform(multipart("/api/uploads")
                .file(png("../../client-name.png")))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.files[0].mediaType")
                .value("image/png"))
            .andExpect(jsonPath("$.files[0].id",
                not(containsString("client-name"))));
    }

    @Test
    void rejectsFourFiles() throws Exception {
        mvc.perform(multipart("/api/uploads")
                .file(png("a.png"))
                .file(png("b.png"))
                .file(png("c.png"))
                .file(png("d.png")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("UPLOAD_REJECTED"));
    }

    @Test
    void rejectsSpoofedMime() throws Exception {
        MockMultipartFile fake = new MockMultipartFile(
            "files", "photo.png", "image/png",
            "not a PNG".getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/api/uploads").file(fake))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsEmptyFile() throws Exception {
        MockMultipartFile empty = new MockMultipartFile(
            "files", "empty.png", "image/png", new byte[0]);

        mvc.perform(multipart("/api/uploads").file(empty))
            .andExpect(status().isBadRequest());
    }

    @Test
    void applicationRejectsOverTwoMiB() throws Exception {
        MockMultipartFile huge = new MockMultipartFile(
            "files", "large.png", "image/png",
            new byte[2 * 1024 * 1024 + 1]);

        mvc.perform(multipart("/api/uploads").file(huge))
            .andExpect(status().isPayloadTooLarge());
    }
}
```

Chạy:

```bash
./mvnw test
```

PowerShell:

```powershell
.\mvnw.cmd test
```

**Giới hạn test:** `PNG_HEADER` chỉ có 8 bytes, không phải một ảnh PNG hoàn chỉnh. Test này chứng minh **logic chính sách sơ bộ** (không phải file format security). Khi thêm decoder, hãy dùng fixture ảnh hợp lệ và tệp hỏng trong test. MockMvc không thay thế container multipart limits; test app-layer oversized khác với test parser/proxy 413.

File thử nghiệm được lưu dưới `target/test-private-uploads`; Maven `clean` có thể dọn thư mục target, hoặc dùng volume/temporary folder riêng trong CI. Với Spring Security, cần thêm mock identity và CSRF token phù hợp: HTTP 403 có thể xảy ra trước controller.

## 13. Phải kiểm thử HTTP thực ở đâu?

Một HTTP integration test qua embedded Tomcat/Jetty hoặc staging ingress cần bao phủ:

- Multipart boundary sai hoặc thiếu; request ngắt giữa chừng.
- `max-file-size` và `max-request-size` tại parser (không chỉ service).
- Tổng multipart parts rất lớn dù số file ít.
- Proxy body limit, timeout và client upload chậm.
- Temp disk hết chỗ; thư mục không có quyền ghi.
- Header lạ/quá dài, filename có control chars/Unicode.
- Upload concurrent vượt rate/quota.
- Scanner/decoder fail hoặc timeout.
- Behavior trả lỗi trước khi `@RestControllerAdvice` có thể chạy.

Có thể dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client thực, hoặc khởi động app rồi `curl` từ test harness. Khi reverse proxy tồn tại, cần test qua **đúng ingress production**; chỉ gọi loopback bỏ qua nhiều policy.

## 14. Khi phục vụ file đã upload

Upload vào private storage chưa có nghĩa đã an toàn để phát file. Khi thêm download/preview API:

1. Ánh xạ một opaque ID tới server-side metadata và path; không lấy tên do client gửi để tạo path.
2. Xác thực user và **kiểm tra quyền trên chính file/tenant** khi tải.
3. Không public directory chứa file upload qua static resource mapping.
4. Chỉ cho phép download khi file đã pass validation/scan policy; có trạng thái quarantine.
5. Đặt `Content-Type` theo loại **đã được xác minh**, không tin MIME của upload request.
6. Dùng `Content-Disposition: attachment` cho format có active content; encode filename header đúng và không chèn raw control chars.
7. Cân nhắc `X-Content-Type-Options: nosniff` và CSP/isolated origin.
8. Với ảnh muốn render inline, ưu tiên decode/re-encode trước khi phát.
9. Thiết kế cache policy phù hợp dữ liệu cá nhân, không dùng cache public tùy tiện.
10. Có cleanup/retention và báo cáo abuse.

Một filename ngẫu nhiên không thay thế authorization. ID có thể rò qua log, browser history hoặc đường dẫn chia sẻ; tài nguyên riêng tư vẫn phải kiểm tra quyền trên mỗi request.

## 15. Tình huống tấn công và lớp phòng vệ

| Tình huống | Nguy cơ | Kiểm tra |
| --- | --- | --- |
| File 20MB tới API max2MB | Hết băng thông/temp | Parser và edge size limits |
| 500 file 1KB | Quá nhiều file | App file count + container part count |
| 1 file và 10.000 field text | Quá nhiều multipart parts | Container/parameter limits |
| `avatar.png.exe` | Double extension | Ignore raw name, allowlist |
| `../../secret` | Path traversal | Server-generated key, private root |
| `image/png` nhưng bytes là text | MIME spoofing | Signature + decoder |
| PNG magic đúng nhưng body sai | Header spoofing | Full image decoding/re-encode |
| 100KB ZIP giải nén 10GB | Decompression bomb | Uncompressed bytes, entry/depth limits |
| 5KB ảnh khai báo 100000×100000 pixels | Image bomb | Pixel cap và CPU/memory budget |
| File PDF chứa JavaScript | Active content | Restrict format, sanitize/CDR/sandbox |
| Tên file cực dài/Unicode trick | Metadata/FS confusion | Ignore in path, validate metadata |
| Cùng tên 100 lần | Overwrite | Random unique generated path |
| Upload cùng lúc từ nhiều client | Resource exhaustion | Rate, quota, concurrency |
| DB insert lỗi sau khi lưu | Orphan file | Compensating cleanup |
| Upload bị ngắt | Temp leftovers | Lifecycle expiry/cleanup |
| File được trả public ngay khi nhận | Malware/XSS | Private quarantine + approval |
| Unauthorized download | Data exposure | Ownership/tenant checks |

Không có một check “file extension hợp lệ” nào thay thế defense in depth.

## 16. Kiến trúc kiểm định file production

Có thể chia thành các chốt:

**Chốt trước multipart parsing:** gateway/container giới hạn bytes, thời gian, số parts, rate và connections.

**Chốt sau parse:** service giới hạn số file/empty/size/type/metadata và quota user; không sử dụng filename client làm path.

**Chốt quarantine:** file đi vào private staging, full decode, pixel/resource cap, malware scanner, CDR/re-encode và timeout. Scanner lỗi thì không nên mặc định allow file.

**Chốt publish:** chỉ file đạt policy mới chuyển sang accepted/private storage, có owner, scan status, checksum và retention. Nếu database và filesystem cập nhật thất bại từng phần thì cần cleanup/reconcile.

**Chốt download:** xác thực, authorize, chọn headers/content disposition, rate và cache policy.

Nếu scan bất đồng bộ, response có thể dùng HTTP `202 Accepted` với job ID và trạng thái pending, không ngụ ý đã được phép download. Queue chỉ mang storage key và metadata cần, không giữ `MultipartFile`/ServletRequest qua vòng đời HTTP.

## 17. Vì sao số byte upload chưa đủ kiểm soát tài nguyên?

Một file nhỏ có thể trở nên cực lớn hoặc cực tốn CPU sau khi phân tích:

- ZIP nén chặt, nhiều cấp thư mục, nested archives.
- Ảnh có pixel dimensions bất thường hoặc metadata chunk lớn.
- PDF phức tạp, font/vector/embedded objects làm parser tốn RAM.
- Video codec/cấu trúc dữ liệu gây decode cực tốn CPU.
- HTML/SVG/script có active content, rủi ro browser nếu render inline.

Đặt budget **sau giải nén/giải mã** và giới hạn concurrency của parser/AV. Không sử dụng `MultipartFile.getBytes()` trên file lớn trong nhiều request đồng thời khi có thể streaming. Tính quota theo cả bytes lưu và chi phí xử lý.

## 18. Lỗi HTTP và ngoại lệ

| Lỗi | Status thường gặp | Nơi phát hiện |
| --- | --- | --- |
| Thiếu file part | 400 | MVC argument binding |
| File rỗng/quá số file | 400 | Service policy |
| Không được phép loại file | 400 theo demo | Service policy |
| File vượt size tại service | 413 | Service policy |
| Multipart request quá lớn | Thường 413 | Parser/exception resolver |
| Proxy từ chối body | Có thể 413/connection close | Edge |
| Sai envelope Content-Type | 415 | MVC request mapping |
| Thiếu xác thực/quyền | 401/403 | Security filters |
| Disk full/staging lỗi | 500 hoặc status server đã thiết kế | Storage/infrastructure |
| Scan async chưa xong | 202 (nếu thiết kế) | Workflow |
| Multipart syntax lỗi | Thường 400, tùy parser | Container/framework |

Một request có thể vi phạm nhiều điều kiện. Không dự đoán “file count luôn được kiểm tra trước file size”: parser/edge có thể dừng trước service. Body JSON lỗi mặc định cũng không đồng nhất giữa Tomcat/Boot/advice/proxy.

## 19. Anti-pattern thường gặp

1. Chỉ kiểm `getSize` trong controller; quá muộn với các chi phí parser trước đó.
2. Không có app file-count limit và container part-count limit.
3. Coi max-request-size = max-file-size × số file chính xác; quên multipart overhead.
4. Coi `Content-Type` client khai báo là bằng chứng thực sự.
5. Tin extension gốc `.png`, bỏ qua magic và decoder.
6. Chỉ check magic, cho scan bypass; file hỏng vẫn có header hợp lệ.
7. Dùng `getOriginalFilename` để tạo directory/path.
8. Chỉ sanitize dấu `../` rồi tin mọi filename còn lại.
9. Đặt upload trong webroot hoặc mở execute permission.
10. Dùng raw filename trong response headers mà không escape.
11. Cho tải file trước khi quét xong.
12. Không giới hạn quota, concurrency hoặc CPU time cho parser.
13. Không kiểm uncompressed bytes/pixel dimensions của tệp.
14. Log raw multipart body, token và filename nhạy cảm.
15. Coi một request không có Content-Length là an toàn.
16. Dùng `MultipartFile.getBytes()` với nhiều file lớn, gây pressure heap.
17. Không cleanup file tạm/orphan sau lỗi/crash.
18. Không authorize download vì đã sinh tên file ngẫu nhiên.
19. Bắt tất cả exception thành 400, che lỗi disk full/IO.
20. Dựa MockMvc làm bằng chứng parser/gateway size limit.
21. Dùng callback async để đọc `MultipartFile` sau request lifecycle.
22. Không có scan state/versioning policy cho định dạng file mới.

## 20. Checklist trước production

### HTTP và hệ thống

- [ ] `consumes=multipart/form-data` và endpoint có xác thực/phân quyền.
- [ ] Max file bytes, max multipart request bytes, số parts và field limits được định nghĩa ở gateway/container/app.
- [ ] Quota user/tenant, rate và concurrency giới hạn.
- [ ] Temp disk riêng, đủ quota, timeout, cleanup, permission chặt.
- [ ] Test HTTP integration cho size limits, malformed boundary, 413/415 và edge policy.

### Content và metadata

- [ ] File count, empty, per-file size và business conditions được validate.
- [ ] Allowlist format theo nhu cầu; không tin extension/MIME client.
- [ ] Magic bytes **và** full decoder/parser/scan theo risk profile.
- [ ] Giới hạn pixels, frames, uncompressed bytes, CPU/memory/time.
- [ ] Không dùng `getOriginalFilename()` làm path/storage key.
- [ ] Metadata tên gốc nếu lưu được normalize, giới hạn và escape.
- [ ] Có malware scanning/quarantine/CDR hoặc tái mã hóa khi cần.

### Storage và download

- [ ] Storage riêng, không public webroot, không execute permission.
- [ ] Server-generated object ID, collision-safe và không overwrite.
- [ ] Có owner/tenant/status/expiry, transaction cleanup và orphan sweeper.
- [ ] Download luôn authorize và đặt Content-Type/Disposition/nosniff phù hợp.
- [ ] Không public nội dung khi scan chưa hoàn thành.
- [ ] Logging và error response không lộ path, exception hay dữ liệu nhạy cảm.
- [ ] Test abuse, traversal, malformed content, multi-tenant access.

## 21. Bài tập tự kiểm tra

**1.** `max-file-size` khác `max-request-size` thế nào?

**Đáp án:** Một cái giới hạn từng file, một cái toàn multipart request gồm bytes và overhead. Không thay thế nhau.

**2.** `files.size() <= 3` có giới hạn mọi multipart part không?

**Đáp án:** Không; các text part khác vẫn có thể rất nhiều. Cần hạn mức container/parser.

**3.** MIME của `MultipartFile.getContentType()` đáng tin không?

**Đáp án:** Không. Do client gửi; cần allowlist, signature và kiểm nội dung thực.

**4.** Đầu file có 8 byte PNG magic có đủ chứng nhận an toàn không?

**Đáp án:** Không. Có thể fake/hỏng/độc; cần full decoding và resource limits.

**5.** Khi filename là `../../secret`, nên làm gì?

**Đáp án:** Không dùng tên gốc làm đường dẫn. Sinh key do server quyết định trong private storage; nếu lưu tên gốc như metadata thì kiểm soát riêng.

**6.** Khi upload bốn file nhỏ, vì sao có thể thấy 413 thay vì 400?

**Đáp án:** Parser hoặc gateway có thể từ chối request vì tổng bytes trước khi controller đếm file.

**7.** MockMultipartFile lớn có test được max-file-size của Tomcat không?

**Đáp án:** Không đầy đủ. Nó test app check; phải kiểm thử HTTP thật để xác nhận parser/container.

**8.** Disk full có nên map thành 400 không?

**Đáp án:** Không; đó là lỗi hệ thống, cần báo lỗi server và cleanup/telemetry.

**9.** Tên file ngẫu nhiên có đủ bảo vệ API download không?

**Đáp án:** Không. Vẫn phải kiểm tra user/tenant, trạng thái scan và quyền đọc.

**10.** Nếu scanner chạy nền, API nên trả gì?

**Đáp án:** Có thể trả 202 + job ID/pending state theo contract, không cho client tải file trước khi pass.

## 22. Tài liệu tham khảo

- Spring Boot 3 MultipartProperties: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html
- Spring Framework 6.2 MultipartFile Javadoc: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/web/multipart/MultipartFile.html
- Spring Framework Multipart Resolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html
- Spring Framework multipart form arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Spring Framework MVC error responses: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- OWASP Unrestricted File Upload: https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload
- RFC 7578 multipart/form-data: https://www.rfc-editor.org/rfc/rfc7578.html
- Jakarta Servlet specification: https://jakarta.ee/specifications/servlet/
