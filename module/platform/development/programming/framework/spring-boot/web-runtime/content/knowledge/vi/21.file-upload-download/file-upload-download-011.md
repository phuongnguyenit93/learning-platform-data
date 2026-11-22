# Tách thư mục lưu tệp người dùng khỏi mã nguồn và tài nguyên công khai

## 1. Vì sao phải tách nơi lưu upload?

Trong Spring Boot, mã nguồn Java, template HTML, static assets và tệp do người dùng tải lên là những loại dữ liệu có **nguồn gốc, mức tin cậy và vòng đời khác nhau**. Mã và resource ứng dụng được kiểm soát bằng Git, build thành JAR/WAR rồi triển khai. Upload đến từ HTTP request, có thể chứa thông tin cá nhân hoặc nội dung độc hại, phải được lưu giữ/xóa/quản lý quyền độc lập với phiên bản phần mềm.

Nếu ứng dụng ghi upload vào `src/main/resources/static/uploads`, `src/main/resources/public`, `src/main/webapp` hoặc một thư mục nằm cạnh mã nguồn, ba rủi ro thường xảy ra:

1. **Lộ file:** resource có thể được cung cấp trực tiếp qua static resource mapping hoặc reverse proxy, không kiểm tra ownership và ACL.
2. **Mất file hoặc sai bản:** resource trong JAR là đầu vào build, còn container/instance có thể bị thay thế. File ghi tại source/build output không tự được đưa vào một JAR đã chạy và có thể biến mất sau deploy.
3. **Trộn ranh giới tin cậy:** file từ client được đặt cạnh template, script và tài nguyên công khai, mở đường cho content spoofing, XSS, overwrite và sai cấu hình.

**Nguyên tắc thiết kế:** user upload là **dữ liệu runtime không đáng tin cậy**, cần một vùng storage riêng ngoài cây mã nguồn, ngoài classpath và ngoài public webroot. File private chỉ được đọc thông qua service/API đã xác thực và kiểm tra quyền; file được công bố công khai phải trải qua chính sách publish riêng.

```text
Repository / Build                              Runtime storage
-----------------------------------------       ----------------------------
src/main/java/...                               /var/lib/myapp/private-files/
src/main/resources/application.properties         245ab...uuid
src/main/resources/static/brand.svg               1902c...uuid
src/main/resources/templates/home.html            71e80...uuid
          |                                                ^
          v                                                |
       bootJar                                        Upload service
          |                                                ^
          v                                                |
     application.jar                         POST /api/files + validation
          |
          +--> GET /brand.svg = static public asset
          +--> GET /api/files/{id} --> authz --> private file
```

Sơ đồ này đặt **quyết định công khai hay riêng tư tại tầng HTTP và metadata**, không dựa vào việc người dùng có biết tên file vật lý hay không.

## 2. Phân loại thư mục và cơ chế Spring Boot phục vụ tệp

| Thư mục/path | Chức năng | Lưu upload riêng tư? |
| --- | --- | --- |
| `src/main/java/` | Mã nguồn Java | Không |
| `src/main/resources/static/` | CSS/JS/ảnh/HTML tĩnh được phục vụ qua static mapping | Không |
| `src/main/resources/public/` | Static resources khác | Không |
| `src/main/resources/META-INF/resources/` | Static location mặc định | Không |
| `src/main/resources/resources/` | Static location mặc định | Không |
| `src/main/resources/templates/` | Template Thymeleaf/FreeMarker... | Không |
| `src/main/webapp/` trong WAR | Servlet web application content | Không |
| `build/`, `target/`, `BOOT-INF/classes/` | Build outputs hoặc JAR resources | Không |
| `java.io.tmpdir`/multipart temp | Tệp trung gian của request | Không để lưu lâu dài |
| `/var/lib/myapp/private-files/` trên volume riêng | Tệp người dùng, OS permissions hạn chế | Có |
| Private object storage bucket | Data bytes do API/storage policy bảo vệ | Có |

Spring Boot MVC mặc định phục vụ static resources từ các classpath locations như `/static`, `/public`, `/resources`, `/META-INF/resources` (trong classpath). Khi file `src/main/resources/static/logo.png` được build, nó thường truy cập được tại `GET /logo.png` với cấu hình static mặc định. Nếu đặt `invoice.pdf` của khách hàng vào đó, kẻ có URL có thể yêu cầu file theo cách xử lý static chung.

Không nên xem `templates/` là nơi lưu tệp an toàn chỉ vì nó không được static mapping phục vụ trực tiếp. Template có thể được template engine render, đóng gói thành JAR và cache. User upload không được biến thành input của template engine hoặc bị overwrite khi release.

Ngoài Spring Boot, cũng cần kiểm tra **NGINX/Apache/CDN**. Một `alias` hoặc static location trên reverse proxy trỏ tới thư mục private vẫn có thể làm lộ file dù controller Spring không hề định nghĩa `/uploads`.

## 3. Classpath, filesystem và HTTP URL không đồng nghĩa

Có ba miền cần phân biệt:

- **Classpath resources:** tệp Java/Spring lấy qua `classpath:`, được đóng gói trong outputs của Gradle/Maven hoặc `BOOT-INF/classes` và dependency JAR.
- **Filesystem runtime:** ổ/volume mà process thật đang chạy có thể đọc/ghi, ví dụ `/var/lib/myapp/private-files/`. Nó nằm ngoài application JAR.
- **HTTP URL:** route được controller hoặc static handler/reverse proxy ánh xạ. URL không tự tồn tại chỉ vì trên disk có file.

```text
classpath:/static/banner.png  -> MVC static handler       -> GET /banner.png
file:/srv/data/private/abc    -> KHÔNG có public mapping   -> URL trực tiếp không có
GET /api/files/{uuid}        -> controller + authz        -> private storage
```

**Không** thêm một `ResourceHandler` phục vụ `/uploads/**` từ directory private khi nghiệp vụ phải kiểm tra user/tenant. Việc này có thể bỏ qua service authorization, trạng thái scan, retention, audit hoặc response headers riêng.

Nếu một file thực sự dành cho public marketing/gallery, hãy tạo storage/publishing flow công khai riêng. Đừng chỉ đổi quyền toàn bộ private directory sang readable hoặc mở một alias để giải quyết download nhanh.

## 4. Vì sao source path và working directory không phải nơi lưu bền?

Code sau sai về thiết kế:

```java
// Anti-pattern: ghi file tải lên trong source tree của ứng dụng.
Path destination = Path.of(
        "src/main/resources/static/uploads", "contract.pdf");
```

Đường dẫn trên là **relative path** theo `user.dir`/working directory của tiến trình. Lúc chạy IDE nó có thể trỏ vào repository, nhưng khi `java -jar` chạy từ vị trí khác nó có thể trỏ sang thư mục không tồn tại. File mới ghi vào source không tự được cập nhật vào JAR đã đóng gói: JAR chứa **snapshot resource tại thời điểm build**.

Với executable Spring Boot JAR, resource classpath nằm ở `BOOT-INF/classes`, không phải cây thư mục ghi thông thường. Không nên dùng `Resource.getFile()` cho mọi classpath resource và giả định có một path vật lý writable tương ứng khi resource nằm trong JAR.

Trong Docker/Kubernetes, container writable layer thường không bền qua việc thay thế container; ở nhiều replicas, các local disks có thể khác nhau. Upload đến instance A rồi request download đến B có thể gặp 404. Vì vậy **tách khỏi source** còn phải đi kèm **tách khỏi vòng đời deploy**, bằng persistent volume, network/shared storage hoặc object storage.

## 5. Multipart staging khác hoàn toàn permanent storage

Spring MVC hỗ trợ HTTP `multipart/form-data` thông qua Servlet multipart parsing. Controller nhận `MultipartFile`, nhưng tệp trong request được servlet container xử lý ở memory hoặc **disk tạm** trước khi service lưu.

Trong Spring Boot 3.3, các thuộc tính thường dùng:

```properties
# Spring Boot 3.3 mặc định 1MB/file và 10MB/request.
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
spring.servlet.multipart.file-size-threshold=0B

# Chỉ là nơi multipart parser có thể ghi nội dung TẠM.
# spring.servlet.multipart.location=/var/tmp/myapp-multipart
```

**`spring.servlet.multipart.location` không phải thư mục lưu file người dùng lâu dài.** Nó chỉ là vị trí trung gian của request, có lifecycle do multipart parser/container quản lý. Không giữ tham chiếu đến temp file rồi trả đường dẫn đó cho người dùng. Hãy copy/transfer sang root private của application khi request còn hợp lệ.

`MultipartFile` cung cấp `getInputStream()`, `getSize()`, `getOriginalFilename()`, `getContentType()` và `transferTo(...)`. Lưu ý:

- `getOriginalFilename()` do **client cung cấp**, có thể là `../../etc/passwd`, có dấu phân cách đường dẫn hoặc extension nguy hiểm. Javadoc khuyên không dùng trực tiếp để ghi path.
- `getContentType()` do client khai báo, **không xác minh bytes thực**.
- Không gọi `file.getBytes()` cho tệp lớn rồi giữ toàn bộ vào heap nếu có thể dùng streaming.
- `transferTo(...)` phụ thuộc implementation/container và target path; ứng dụng vẫn phải tự kiểm soát directory, quyền, key và cleanup.

Khi xử lý upload lớn, ngoài Spring multipart limits còn cần reverse proxy size limit, timeout, disk quota của thư mục tạm, concurrent requests và quota theo user/tenant. Không giải quyết nguy cơ DoS bằng việc đơn thuần tăng max-file-size thành vô hạn.

## 6. Cấu trúc lưu trữ và metadata tách biệt

Một kiến trúc nhỏ nhưng rõ trách nhiệm:

```text
POST /api/files
  -> Authentication / authorization to upload
  -> Multipart validation, size, type, scanning policy
  -> Storage service creates opaque file ID
  -> Bytes stored in private directory/bucket
  -> Metadata saved: fileId, ownerId, storageKey, size, status
  -> 201 Created + fileId

GET /api/files/{fileId}
  -> Authentication
  -> Load metadata
  -> Check owner/tenant/ACL, status, retention
  -> Resolve server-controlled storageKey
  -> Stream bytes with safe download headers
```

Mô hình metadata nên phân biệt:

| Trường | Vai trò |
| --- | --- |
| `file_id` | ID logic dùng trong API, ví dụ UUID |
| `storage_key` | Tên file/object key server tạo, **không lấy từ request** |
| `owner_id`, `tenant_id` | Ràng buộc authorization |
| `original_filename` | Tên hiển thị, phải escape/sanitize; không dùng làm path |
| `detected_media_type` | Loại nội dung được kiểm tra theo chính sách |
| `size_bytes`, `sha256` | Kích thước và toàn vẹn |
| `status` | `PENDING_SCAN`, `AVAILABLE`, `REJECTED`, `DELETING`... |
| `created_at`, `retention_until` | Audit và lifecycle |

UUID không phải password. ID khó đoán vẫn có thể bị lộ qua URL, log hoặc API khác. **Không cho tải file chỉ vì client biết UUID**; phải kiểm tra quyền trên metadata. File đã bị xóa logic hoặc chưa scan không được tải nếu policy chưa cho phép.

## 7. Cấu hình private storage bằng đường dẫn tuyệt đối

Ví dụ layout production Linux:

```text
/opt/myapp/application.jar
/etc/myapp/application-prod.yml
/var/lib/myapp/private-files/      # riêng tư, persistence độc lập
/var/log/myapp/
```

Cấu hình `application.properties`:

```properties
app.upload.root=${UPLOAD_ROOT}

spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB

# Chỉ dành cho demo cục bộ; production có cấu hình mạng + security riêng.
server.address=127.0.0.1
server.port=8080
```

`UPLOAD_ROOT` phải được operator đặt thành **absolute path nằm ngoài repository, static locations, webroot và output artifact**. Việc buộc có biến môi trường giúp ứng dụng không âm thầm ghi upload vào thư mục hiện hành.

Trên Linux có thể chuẩn bị thư mục theo service account:

```bash
sudo install -d -m 700 -o myapp -g myapp /var/lib/myapp/private-files
```

Chỉ dùng khi account `myapp` đã tồn tại và ứng dụng thực sự chạy bằng account ấy. Với Windows, chọn volume/path tuyệt đối và NTFS ACL tương ứng. Bảo đảm tiến trình chạy app có quyền ghi/đọc cần thiết; user/process không tin cậy không thể thêm symlink hoặc sửa tệp trong directory.

Nếu có nhiều app instances, địa chỉ storage phải dùng **volume có thể chia sẻ và truy cập nhất quán**, hoặc chuyển sang object storage. Đừng phụ thuộc vào tên host hoặc working directory.

## 8. Không bao giờ dùng original filename làm storage path

Tên client có thể chứa:

```text
portrait.jpg
../../application.properties
C:\Windows\system.ini
invoice.pdf.exe
<script>alert(1)</script>.html
```

Cách làm sai:

```java
// Không làm:
Path target = root.resolve(file.getOriginalFilename());
```

Kết quả có thể gây path traversal, ghi đè, tên nguy hiểm, mismatch separator giữa Windows/Linux hoặc lộ dữ liệu. `Paths.get(name).getFileName()` vẫn không giải quyết mọi rủi ro về extension, overwrite và identifier collision.

Nên sinh **storage key ngẫu nhiên do server quyết định**:

```java
UUID id = UUID.randomUUID();
Path target = privateRoot.resolve(id.toString());
```

Sử dụng `Files.newOutputStream(target, CREATE_NEW, WRITE)` thay vì ghi đè tùy tiện. Nếu cần tên gốc trong UI, lưu nó riêng vào metadata sau khi giới hạn độ dài và escape cho HTML, JSON và HTTP header contexts. Nếu cần file extension, suy ra qua allowlist/content validation; đừng xem đuôi do client khai báo là bằng chứng format.

Nếu chỉ cần download attachment, dùng filename do server đặt cũng được. Khi muốn trả original filename theo nghiệp vụ, dựng `Content-Disposition` qua API builder để xử lý escape/encoding và tránh header injection.

## 9. Ví dụ Spring Boot 3.3 chạy được: lưu private file theo UUID

Ví dụ dùng Java 21, Spring Boot 3.3.13, Gradle Wrapper. Nó phục vụ **mục đích học và chạy trên loopback**, chưa cung cấp authentication, metadata DB hay malware scanner. Khi đưa ra production, cần thêm những thành phần này và bỏ cấu hình mạng loopback một cách có kiểm soát.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
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

**`src/main/java/com/example/upload/UploadApplication.java`:**

```java
package com.example.upload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UploadApplication {
    public static void main(String[] args) {
        SpringApplication.run(UploadApplication.class, args);
    }
}
```

**`src/main/java/com/example/upload/PrivateFileStorage.java`:**

```java
package com.example.upload;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

@Service
public class PrivateFileStorage {
    private static final long MAX_BYTES = 5L * 1024 * 1024;
    private final Path root;

    public PrivateFileStorage(@Value("${app.upload.root}") String directory)
            throws IOException {
        Path configured = Path.of(directory);
        if (!configured.isAbsolute()) {
            throw new IllegalArgumentException(
                    "app.upload.root must be absolute");
        }
        Files.createDirectories(configured);
        this.root = configured.toRealPath();
    }

    public SavedFile save(MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new IllegalArgumentException("File must not be empty");
        }
        if (file.getSize() > MAX_BYTES) {
            throw new IllegalArgumentException("File exceeds 5 MiB");
        }

        UUID id = UUID.randomUUID();
        Path target = root.resolve(id.toString());
        boolean created = false;
        long copied;

        try {
            try (OutputStream out = Files.newOutputStream(
                    target,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE)) {
                created = true;
                try (InputStream in = file.getInputStream()) {
                    copied = in.transferTo(out);
                }
            }
            if (copied > MAX_BYTES) {
                throw new IllegalArgumentException("File exceeds 5 MiB");
            }
        } catch (IOException | RuntimeException error) {
            if (created) {
                try {
                    Files.deleteIfExists(target);
                } catch (IOException cleanup) {
                    error.addSuppressed(cleanup);
                }
            }
            throw error;
        }
        return new SavedFile(id, copied);
    }

    public Path find(UUID id) throws IOException {
        Path file = root.resolve(id.toString());
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) {
            throw new NoSuchFileException(id.toString());
        }
        return file;
    }

    public record SavedFile(UUID id, long bytes) {
    }
}
```

Phân tích:

- `app.upload.root` phải là absolute path. Constructor tạo thư mục và lấy `toRealPath()` của vị trí tồn tại. **Operator vẫn phải xác nhận** path không nằm dưới source/webroot và directory được khóa quyền.
- Tên file trên disk **chỉ là UUID**. Dù client gửi tên `../../application.yml`, nội dung vẫn nằm tại `root.resolve(UUID)`; không có thành phần path từ client.
- `CREATE_NEW` từ chối ghi đè path đã có. `boolean created` chỉ bật sau khi mở output thành công; nếu mở thất bại vì path đã tồn tại thì handler không xóa nhầm file trước đó.
- Input stream được đóng; `transferTo` hỗ trợ streaming; `catch` cố xóa partial file nếu copy thất bại. Kiểm tra actual copied bytes bổ sung cho `MultipartFile.getSize()` và parser limits.
- `find` chỉ nhận `UUID`, kiểm tra regular file với `NOFOLLOW_LINKS` để từ chối symlink. Tuy vậy nếu thư mục bị tiến trình khác có quyền thay đổi, vẫn tồn tại nguy cơ race condition giữa kiểm tra và đọc. Thiết lập permissions là điều kiện cần.
- Service này chưa có metadata/ACL; production phải kiểm tra quyền trước khi gọi `find`, không chỉ dựa vào UUID khó đoán.

**`src/main/java/com/example/upload/UploadController.java`:**

```java
package com.example.upload;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.CacheControl;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/files")
public class UploadController {
    private final PrivateFileStorage storage;

    public UploadController(PrivateFileStorage storage) {
        this.storage = storage;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<PrivateFileStorage.SavedFile> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(storage.save(file));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Resource> download(@PathVariable UUID id)
            throws IOException {
        // Production: check metadata + owner/tenant/ACL before this line.
        Path path = storage.find(id);
        Resource data = new FileSystemResource(path);
        String disposition = ContentDisposition.attachment()
                .filename(id + ".bin", StandardCharsets.UTF_8)
                .build().toString();

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(Files.size(path))
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition)
                .header("X-Content-Type-Options", "nosniff")
                .cacheControl(CacheControl.noStore())
                .body(data);
    }
}
```

Controller tải xuống **qua ID**, không nhận raw path. `Content-Disposition: attachment` yêu cầu browser tải về thay vì hiển thị như HTML; `application/octet-stream` không tin MIME từ client; `nosniff` bổ sung bảo vệ khỏi content sniffing; `no-store` là chính sách cache thuận tiện cho file riêng tư.

Những headers ấy **không thay thế** authentication/authorization. Vì demo không có bảo mật, chỉ chạy với `server.address=127.0.0.1`. Khi dùng thật phải có metadata lookup và authorization trước khi mở file.

**`src/main/java/com/example/upload/UploadProblemHandler.java`:**

```java
package com.example.upload;

import java.nio.file.NoSuchFileException;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class UploadProblemHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    ProblemDetail invalidFile(IllegalArgumentException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, "Invalid or oversized file");
    }

    @ExceptionHandler(NoSuchFileException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    ProblemDetail missingFile(NoSuchFileException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, "File not found");
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    @ResponseStatus(HttpStatus.PAYLOAD_TOO_LARGE)
    ProblemDetail tooLarge(MaxUploadSizeExceededException exception) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.PAYLOAD_TOO_LARGE, "Multipart limit exceeded");
    }
}
```

Lỗi HTTP không phát tán absolute file paths. Trong dự án lớn, scope exception handler riêng cho upload để `IllegalArgumentException` không liên quan ở module khác không bị biến thành thông báo tệp.

**`src/main/resources/application.properties`:**

```properties
app.upload.root=${UPLOAD_ROOT}
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
server.address=127.0.0.1
server.port=8080
```

## 10. Chạy thử và xác nhận file nằm ngoài source

Trên Linux/macOS, tạo thư mục **ngoài project** dành cho demo:

```bash
mkdir -p /tmp/myapp-upload-demo
chmod 700 /tmp/myapp-upload-demo
export UPLOAD_ROOT=/tmp/myapp-upload-demo
./gradlew bootRun
```

Thư mục `/tmp` chỉ dùng development vì không có bảo đảm lưu bền; production dùng `/var/lib/myapp/private-files` trên durable volume.

Trên Windows PowerShell:

```powershell
$env:UPLOAD_ROOT = Join-Path $env:TEMP "myapp-upload-demo"
New-Item -ItemType Directory -Force -Path $env:UPLOAD_ROOT
.\gradlew.bat bootRun
```

Tạo tệp `sample.txt` bất kỳ trong terminal khác rồi gửi:

```bash
curl -i -F "file=@sample.txt" http://127.0.0.1:8080/api/files
```

Khi upload thành công, response `201 Created` có JSON với `id` UUID và `bytes` tương ứng kích thước thực tế. **Không có stdout cố định** cho UUID vì server sinh giá trị mới mỗi lần. Sau khi lấy ID thực từ JSON, tải về:

```bash
curl -fS -o downloaded.bin \
  http://127.0.0.1:8080/api/files/REPLACE_WITH_REAL_UUID
```

Thay `REPLACE_WITH_REAL_UUID` bằng chuỗi UUID của response. File `downloaded.bin` phải có bytes giống `sample.txt`. File gốc trên server nằm trong `UPLOAD_ROOT` dưới tên UUID, **không** nằm trong `src/main/resources/static`, `public`, `templates` hoặc cạnh `UploadApplication.java`.

Thử một tên tệp được client khai báo lạ bằng curl:

```bash
curl -F 'file=@sample.txt;filename=../../index.html' \
  http://127.0.0.1:8080/api/files
```

Vì storage key do server sinh, dữ liệu vẫn không đi theo `../../`. Sau restart cùng máy với cùng `UPLOAD_ROOT`, file demo còn tồn tại nếu hệ điều hành chưa xóa folder. Sau khi chuyển sang instance khác không chia sẻ storage, điều đó không được bảo đảm.

Ví dụ chỉ phục vụ học lưu trữ cục bộ. Không đưa API chưa xác thực này ra Internet.

## 11. Authorization khi đọc file là bắt buộc

Trong production, cần một tầng metadata/ACL. Logic minh họa:

```text
Authenticated user
       |
       +--> GET /api/files/{id}
       |
       +--> Find file metadata by id
       +--> Check tenantId, ownerId, role, shared-with list
       +--> Check status == AVAILABLE, not deleted/expired
       +--> Map trusted storageKey to file/object
       +--> Stream download + audit
```

Pseudocode Java sau **không phải chương trình độc lập** vì `FileMetadata`, repository và access policy là những thành phần nghiệp vụ phải hiện thực:

```java
FileMetadata meta = metadataRepository.findById(fileId)
        .orElseThrow(FileNotFoundException::new);

if (!accessPolicy.canRead(authentication, meta)) {
    throw new AccessDeniedException("Not allowed");
}

Path file = privateStorage.find(meta.storageId());
return streamAuthorizedFile(file);
```

Ngay cả với UUID khó đoán, vẫn phải chặn người dùng B đọc tệp của A. Một số sản phẩm trả cùng mã 404 cho file không có và không được phép đọc để tránh tiết lộ sự tồn tại của file; cách này phải được áp dụng nhất quán.

Nếu dùng signed URL với S3-compatible storage, application phải kiểm tra authorization **trước khi ký**, giới hạn thời gian và quyền của URL. Không ghi signed URLs, tokens hoặc user credentials vào log có thể chia sẻ công khai.

Nếu upload gắn với tài khoản/tenant, cần kiểm soát **tạo, đọc, đổi trạng thái và xóa**. Quyền đọc không được mặc định đồng nghĩa với quyền xóa hoặc quyền công bố nội dung.

## 12. Các lớp kiểm tra file độc hại

Đặt tệp ngoài webroot là cần thiết nhưng chưa đủ. Khi nhận nội dung từ client:

1. Chọn **allowlist loại file** theo nghiệp vụ, ví dụ JPEG/PNG/PDF. Không dùng blacklist đuôi như `.exe` vì có double-extension và tên Unicode bất thường.
2. Xác minh **file signature/format thực** khi có nhu cầu. Header `Content-Type` và filename chỉ là dữ liệu do client cung cấp.
3. Đặt giới hạn kích thước ở proxy, Spring multipart và storage; với ZIP/PDF/ảnh còn xét decompression ratio, page count, image dimensions và số lượng entry.
4. Quét malware/sandbox/CDR khi loại file và threat model yêu cầu. Giữ file ở trạng thái `PENDING_SCAN`/quarantine cho đến khi đạt điều kiện.
5. Không render trực tiếp HTML/SVG/PDF không an toàn cùng origin với ứng dụng khi chưa có chính sách xử lý; có thể cần conversion, separate origin hoặc CSP.
6. Thiết lập quota theo user/tenant, rate limits, thời gian upload, concurrency và cleanup khi request ngắt.
7. Với authentication bằng cookie, bảo vệ CSRF đúng chính sách; CORS không tự ngăn CSRF.
8. Ghi audit ở mức file ID, actor, size, status; không log raw file bytes hoặc secrets.

Một file tên `image.png` có thể chứa bytes HTML hoặc content độc hại. Đừng lấy extension hoặc multipart `getContentType()` làm bằng chứng để inline-render.

Với download private, `attachment`, `octet-stream`, `nosniff` và `no-store` có ích; tuy nhiên vẫn phải kiểm tra quyền và nội dung trước khi xuất file. Browser behavior còn phụ thuộc cấu hình client, nên không dùng response header như bảo đảm an toàn tuyệt đối.

## 13. Path traversal, symlink và race condition

Khi client có thể kiểm soát đường dẫn lưu, họ có thể gửi `../`, path tuyệt đối, separator Windows/Linux hoặc tên trùng để đọc/ghi đè ngoài root. Thiết kế an toàn hơn là **không nhận path từ client**.

Đối với một nghiệp vụ bắt buộc dùng relative path, cần validation, normalization, kiểm tra path nằm dưới trusted root và xử lý symbolic links. Song phép kiểm tra `path.normalize().startsWith(root)` chỉ là một tầng: nếu attacker có quyền thay đổi symlink giữa lúc check và lúc mở, vẫn có race (TOCTOU).

Ví dụ của mục 9 sử dụng UUID làm tên file, `CREATE_NEW` khi ghi và `Files.isRegularFile(..., NOFOLLOW_LINKS)` khi đọc. Dù vậy, **điều kiện môi trường** vẫn là thư mục private và ancestor paths không được ghi/sửa bởi tiến trình không tin cậy. Nếu threat model yêu cầu bảo vệ trước hostile local users, cần cơ chế open-handle/safe path resolution phù hợp OS hoặc object storage có quyền IAM chặt chẽ.

Không cho phép API delete nhận raw absolute filesystem path. Xóa theo ID và metadata đã check quyền; chỉ sử dụng storage key do server quản lý.

`Files.createDirectories(...)` không tự thiết lập toàn bộ ACL bảo mật mong muốn. Operator phải quản lý owner/group/mode trên Linux hoặc ACL trên Windows, mount options và chính sách backup.

## 14. File bytes và database metadata không cùng một transaction

`@Transactional` dùng cho JDBC/JPA không làm `Files.write`, `Files.move` hoặc S3 object upload tự rollback cùng DB. Một upload có thể gây:

- Ghi bytes thành công, DB commit lỗi → **orphan file**.
- Metadata được ghi trước, storage save lỗi → record chỉ đến file không có.
- Client timeout rồi retry → trùng file nếu không có idempotency.
- Xóa metadata thành công nhưng xóa object thất bại → file vẫn còn trên storage.
- Container chết giữa copy → partial file hoặc record trạng thái chưa hoàn tất.

Luồng production nên có **trạng thái và cleanup**:

```text
NEW/PENDING
    -> lưu bytes vào staging/quarantine
    -> validate/checksum/scan
    -> publish/mark AVAILABLE
    -> [download chỉ khi AVAILABLE]
    -> DELETING/DELETED khi hết hạn hoặc được yêu cầu
```

Lưu ý `Files.move` với `ATOMIC_MOVE` chỉ có thể atomic trong filesystem hỗ trợ và thường không có bảo đảm khi đi qua hai volumes. `AtomicMoveNotSupportedException` cần được xử lý; thao tác move không biến DB và filesystem thành distributed transaction.

Dùng scheduled reconciliation job để tìm metadata thiếu bytes, orphan files hoặc pending lâu; retry idempotent và cleanup có audit. Với object storage, thiết kế theo upload/multipart complete semantics của nhà cung cấp, không suy rằng object upload và DB insert là một bước ACID.

## 15. Dữ liệu phải sống lâu hơn container và build artifact

Khi đóng gói Docker, upload không nên nằm trong container image hoặc writable layer của container. Ví dụ Docker Compose thể hiện **volume tách riêng**:

```yaml
services:
  web:
    image: example/myapp:1.0
    environment:
      UPLOAD_ROOT: /data/private-files
    ports:
      - "8080:8080"
    volumes:
      - user_uploads:/data/private-files

volumes:
  user_uploads:
```

Đây là sơ đồ triển khai, chưa phải cấu hình production hoàn chỉnh: `server.address=127.0.0.1` trong demo phải được điều chỉnh để container có thể nhận port mapping và **API phải có security** trước khi mở ra mạng.

Docker named volume giúp giữ dữ liệu vượt vòng đời một container trên **cùng host**, nhưng không tự là shared storage cho nhiều hosts, không tự backup và không bảo đảm high availability.

Trong Kubernetes:

- Kiểm tra `PersistentVolumeClaim` và storage driver thực tế.
- Phân biệt `ReadWriteOnce` và `ReadWriteMany` khi có nhiều pods/nodes.
- Xác định UID/GID, volume permissions, mount path và node-affinity.
- Không mặc nhiên cho rằng mỗi pod đọc cùng filesystem.
- Cấu hình backup/restore và kế hoạch mất volume.
- Khi cần quy mô lớn, dùng private object storage và object keys trong metadata, IAM và signed-download policy rõ ràng.

Một kiểm thử triển khai tốt: upload một file trước release, thay image/container, sau đó tải cùng file ID. Nếu file biến mất, cần xem lại storage persistence và metadata, không sửa controller để đọc từ `static`.

## 16. Cách xử lý file công khai thật sự

Có những tệp người dùng **được phép công khai** (ảnh sản phẩm đã duyệt, banner, brochure). Khi đó nên tách pipeline:

```text
Private original uploads
  -> validate content
  -> scan/moderate
  -> transform (thumbnail, image conversion, safe document)
  -> publish approved derivative to public storage/CDN
```

Tệp gốc và tệp public có **quyền/lifecycle khác nhau**. Không public toàn bộ root uploads chỉ vì một số ảnh cần hiển thị công khai. Public file có thể cần content sanitization, giới hạn MIME, CSP và origin riêng để hạn chế XSS.

Khi xóa quyền công khai hoặc xóa file gốc theo policy, nhớ kiểm tra cả derived files, cache/CDN và retention trong backup. Không tuyên bố xóa hoàn toàn nếu còn bản sao đang giữ theo lịch retention.

## 17. Kiểm thử: tên tệp từ client không làm thay đổi đường dẫn

Với dependency `spring-boot-starter-test`, có thể chạy JUnit 5 và `MockMultipartFile`. Test này **dùng filesystem tạm độc lập**, không phụ thuộc server hay root production.

**`src/test/java/com/example/upload/PrivateFileStorageTest.java`:**

```java
package com.example.upload;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

class PrivateFileStorageTest {
    @TempDir
    Path tempDir;

    @Test
    void neverUsesOriginalFilenameAsStoragePath() throws Exception {
        Path root = tempDir.resolve("private").toAbsolutePath();
        PrivateFileStorage storage = new PrivateFileStorage(root.toString());

        MockMultipartFile uploaded = new MockMultipartFile(
                "file",
                "../../index.html",
                "text/html",
                "hello".getBytes(StandardCharsets.UTF_8));

        PrivateFileStorage.SavedFile saved = storage.save(uploaded);
        Path stored = storage.find(saved.id());

        assertThat(Files.readString(stored)).isEqualTo("hello");
        assertThat(stored.getFileName().toString())
                .isEqualTo(saved.id().toString());
        assertThat(stored.startsWith(root.toRealPath())).isTrue();
        assertThat(Files.exists(tempDir.resolve("index.html"))).isFalse();
    }
}
```

Chạy từ thư mục dự án:

```bash
./gradlew test
```

Nếu môi trường có quyền tạo file và source khớp ví dụ, test **PASS**, không có stdout UUID cố định. Kiểm thử này chứng minh original filename không được dùng làm path, chưa chứng minh authorization, malware scanning hoặc persistence.

Những kiểm thử tích hợp quan trọng thêm khi triển khai thật: User A upload, User B đọc cùng ID bị từ chối; quá giới hạn kích thước không tạo file; `PENDING_SCAN` không tải được; file symlink bị từ chối; restart/redeploy không làm mất dữ liệu trên durable volume; download qua `/uploads/...` không bypass policy; đồng thời nhiều upload không ghi đè nhau; partial files được cleanup.

## 18. Chẩn đoán khi upload hoặc download gặp lỗi

| Hiện tượng | Nguyên nhân nghi ngờ | Hướng kiểm tra |
| --- | --- | --- |
| Upload 201 nhưng không thấy tệp trong source/static | Có thể **đúng thiết kế** | Xem `UPLOAD_ROOT` và storage key thực |
| File mất sau deploy container | Lưu trong writable layer không có volume | Kiểm tra mount, PVC, object store |
| Upload instance A, download B báo 404 | Storage cục bộ khác nhau | Chọn shared/object storage |
| File đang có trên disk nhưng API trả 403 | Authz hoặc OS permissions | So sánh user/tenant/ACL và service UID |
| Upload 413 | Multipart/proxy request limit | Xem Spring và ingress limits |
| `AccessDeniedException` khi ghi | Directory/volume ACL/UID không phù hợp | Kiểm tra account chạy app, mode, mount |
| `NoSuchFileException` khi tải | Root sai, metadata sai hoặc file hết hạn | Xem root tuyệt đối, key và retention |
| File private đọc được từ `/uploads/...` | Có static handler/proxy alias/public bucket | Gỡ mapping public, kiểm tra webroot/IAM |
| File HTML chạy inline thay vì download | Content-Type/Content-Disposition không phù hợp | Ưu tiên attachment + octet + nosniff |
| Có metadata mà bytes bị thiếu | Lỗi phối hợp DB/file hoặc cleanup | Xem status, audit và reconciliation |
| Disk đầy trong khi root private còn trống | Multipart **temp staging** có thể dùng disk khác | Kiểm tra `spring.servlet.multipart.location`, `java.io.tmpdir` |
| Code chạy trong IDE nhưng fail trong JAR | Dùng relative path hoặc resource trong JAR | Kiểm tra absolute root, working dir, artifact |
| Image/container mới hiển thị bản file cũ | Local cache, node khác hoặc metadata/replica không nhất quán | Xác định instance và storage key, cache policy |

Theo một ID cụ thể từ `POST` → metadata → storage key → disk/object → authorization → `GET`. Không sửa bằng việc public toàn bộ directory hoặc tăng quyền filesystem thành đọc/ghi cho tất cả người dùng.

## 19. Phân biệt WebFlux và Servlet ở lớp nhận upload

Với Spring MVC/Servlet, controller thường dùng `MultipartFile` và nhóm thuộc tính `spring.servlet.multipart.*`. Với Spring WebFlux, API reactive thường dùng `FilePart`, `Part` hoặc `PartEvent` và cấu hình `spring.webflux.multipart.*`.

Dù stack khác, các nguyên tắc storage giống nhau: lưu ngoài source/static/webroot, server-generated key, authz, quota, scan, metadata, durability, cleanup. WebFlux không tự biến bytes nguy hiểm thành nội dung an toàn.

Trong WebFlux, tránh thực hiện blocking `Files.copy`, `Files.newOutputStream`, JDBC/JPA trực tiếp trên Netty event-loop. Dùng `FilePart.transferTo(Path)` với root/key do server kiểm soát hoặc storage client phù hợp, xử lý lỗi và cleanup partial files; khi gọi blocking APIs cần scheduler được thiết kế cho blocking I/O.

Nếu cả MVC và WebFlux có trên classpath, Spring Boot thường mặc định chọn **Servlet** khi suy luận web application type. Trước khi sửa cấu hình multipart, xác định stack đang chạy.

## 20. Những hiểu nhầm thường gặp

**“`spring.servlet.multipart.location` là thư mục lưu lâu dài.”** Không; đó là vùng tạm của multipart processing.

**“Tệp nằm trong `static/` nhưng URL khó đoán nên an toàn.”** Không; URL/filename không phải ACL. Static handler có thể phục vụ trực tiếp khi biết path.

**“`templates/` không public thì dùng làm private uploads.”** Không; template là resource của build/engine, không phải storage dành cho dữ liệu người dùng.

**“Có `.gitignore` thì không sao nếu upload nằm trong project.”** Không; Git ignore không ngăn static serving, build copying, loss after deployment hoặc Docker cleanup.

**“Dùng `MultipartFile.getOriginalFilename()` rồi normalize là đủ.”** Không; rủi ro overwrite, extension lạ, Unicode, path semantics còn tồn tại. Dùng opaque ID do server sinh.

**“UUID là bảo mật.”** Không; UUID là ID, phải kiểm tra owner/tenant/ACL trước khi trả bytes.

**“`@Transactional` rollback DB thì filesystem tự rollback.”** Không; cần trạng thái, cleanup/reconciliation và idempotency.

**“Lưu ngoài source có nghĩa dữ liệu luôn bền.”** Chỉ đúng nếu storage được mount/backup/replicate theo nhu cầu và không thuộc writable layer tạm.

**“Header `attachment` thay thế quyền đọc.”** Không; nó chỉ ảnh hưởng cách browser xử lý response. Authorization là quyết định ứng dụng.

**“Upload dùng WebFlux thì không cần kiểm tra content.”** Không; mọi upload từ client đều không đáng tin cậy.

## 21. Checklist vận hành và tự đánh giá

Trước khi phát hành chức năng upload/download, kiểm tra các điểm thiết yếu:

1. Storage path nằm **ngoài** `src/`, `build/`, static locations, public webroot và JAR.
2. `UPLOAD_ROOT` được operator cấp bằng absolute path, có ACL phù hợp và mount bền vững.
3. Client **không quyết định** full path hoặc key lưu file; filename server-generated là duy nhất và tạo bằng `CREATE_NEW`/object precondition.
4. Size, MIME/format, scan/quarantine, quota/rate limit/CSRF đúng threat model.
5. Download tra metadata và thực hiện authn/authz theo owner/tenant/ACL/trạng thái trước khi mở tệp.
6. Endpoint private không bị public trực tiếp bởi Spring `ResourceHandler`, reverse proxy, CDN hay bucket ACL.
7. Response file nhạy cảm dùng header chống inline interpretation và cache phù hợp.
8. Có phương án xử lý partial/orphan files, xóa/retention, idempotency và consistency với database.
9. Có backup, khôi phục, kiểm tra data sau restart/redeploy, hành vi nhiều instances.
10. Có test traversal, ownership, giới hạn multipart, lỗi ghi và chính sách download.

**Câu hỏi tự kiểm tra:**

- Vì sao không nên đặt hóa đơn người dùng dưới `src/main/resources/static/uploads`, ngay cả khi chỉ người đã đăng nhập được phép upload?
- `spring.servlet.multipart.location` khác `app.upload.root` ở điểm nào?
- Tại sao `server.address=127.0.0.1` chỉ phù hợp cho ví dụ local và không giải quyết authorization của production?
- Nếu hai pods có filesystem riêng, tại sao upload ở A có thể 404 ở B dù cùng một JAR?
- Tại sao không được chuyển raw original filename thành `Path` rồi ghi vào root?
- File bytes đã copy xong nhưng metadata database rollback: cần xử lý tình huống đó ra sao?
- Nếu asset thực sự public, làm thế nào để publish một bản được duyệt mà không mở nguyên kho private?
- Vì sao `Content-Disposition: attachment` và `X-Content-Type-Options: nosniff` không thay thế quyền đọc?

**Ghi nhớ:** tệp người dùng là dữ liệu runtime có quyền và vòng đời riêng. Hãy lưu ngoài source/classpath/public resources, gọi storage qua ID do server tạo, kiểm soát quyền tải về và triển khai storage bền vững độc lập với application artifact.

### Tài liệu tham khảo

- Spring Boot 3.3 — Servlet Web Applications, Static Resources: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Common Application Properties (multipart): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework — Multipart Forms: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Spring Framework 6.1 — `MultipartFile` JavaDoc: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/multipart/MultipartFile.html
- OWASP — File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- Java 17 — `Files` API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html