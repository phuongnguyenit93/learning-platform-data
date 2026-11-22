# Xây dựng luồng nhận tệp lớn với giới hạn kích thước và dọn tài nguyên

> **Module:** Spring Boot - web-runtime · **Nhóm:** Thực hành tổng hợp. Bài này xây dựng **hai API upload file** trên **Spring Boot 4.1.2, Java 17+**: `multipart/form-data` cho browser và `application/octet-stream` cho client gửi raw bytes. Cả hai dùng chung dịch vụ đọc dữ liệu theo **buffer hữu hạn**, kiểm **số bytes thực** (không chỉ tin Content-Length), tạo SHA-256, ghi vào file staging, publish bằng atomic move và xóa file chưa hoàn tất trong `finally`. Bài giải thích chi phí Servlet multipart temporary storage, các giới hạn ở reverse proxy/Tomcat/app/disk, client disconnect, SIGKILL và janitor, bảo mật nội dung không tin cậy, JUnit real-port và kịch bản vận hành. **Demo không có authentication, antivirus hay download endpoint; không triển khai công khai.**

## 1. Mục tiêu và tiêu chí thành công

Người học hoàn thành được:

1. Phân biệt **streaming copy trong application**, **raw Servlet request-body streaming**, **Servlet multipart spool** và **buffering ở proxy**, tránh tuyên bố `MultipartFile.getInputStream()` là end-to-end streaming.
2. Đặt ngân sách **max-file-size, max-request-size, max-parts, per-part headers, actual read bytes, concurrent requests, disk quota và upload duration**, biết tầng nào thực thi từng giới hạn.
3. Không sử dụng `MultipartFile.getBytes()` hoặc `InputStream.readAllBytes()` cho file lớn; giải thích khác biệt heap pressure và temporary disk pressure.
4. Tạo **private storage stage/ready** với tên file ngẫu nhiên do server cấp, không dùng `getOriginalFilename()` làm đường dẫn.
5. Dùng `try-with-resources` cho InputStream/OutputStream, `finally` để cleanup .part và semaphore permit, kể cả lỗi khi read/write/move.
6. Từ chối body rỗng (400), vượt limit (413), writer quá tải (429), unsupported Content-Encoding (415); phân biệt lỗi trong Spring với lỗi ở edge/container có thể reset connection.
7. Dùng SHA-256 trong một vòng copy, so digest/bytes thực nhận và publish chỉ sau khi file ghi xong.
8. Chạy project Maven Java 17 gồm MVC controller, service, error advice và JUnit integration test trên random TCP port, test cURL multipart/raw/oversize.
9. Thiết kế cleanup sau **crash/SIGKILL** bằng TTL/lease/GC, tránh xóa file mà upload còn hoạt động.
10. Mở rộng đúng cách sang object storage, resumable uploads, WebFlux PartEvent, antivirus/CDR, tenant quotas và idempotency.

## 2. Data flow: tại sao có hơn một bộ đệm?

~~~text
Browser / CLI / mobile application
      |
      | POST multipart/form-data hoặc application/octet-stream
      v
CDN / WAF / API gateway / Ingress / reverse proxy
      | request size, rate, timeout, body buffering/temp storage
      v
Spring Boot embedded Tomcat :8080
      |
      +-- MULTIPART:
      |     Servlet Part parser
      |     -> max-file-size/max-request-size/parts count
      |     -> memory or servlet temporary file
      |     -> MultipartFile.getInputStream()
      |
      +-- RAW OCTET-STREAM:
            HttpServletRequest.getInputStream()
            -> read when bytes arrive via connector/proxy
      |
      v
UploadService.store()
      | semaphore -> 16 KiB copy loop -> actual byte counter
      | SHA-256 update -> private stage/<random>.part
      | validate full size/nonempty -> close output
      | ATOMIC_MOVE -> private ready/<UUID>.bin
      v
HTTP 201 JSON receipt {id,bytes,sha256}
~~~

Trong Spring MVC, `MultipartFile` có thể giữ content trong memory hoặc disk tạm. Spring Framework Javadoc ghi rõ temporary storage được cleanup cuối quá trình xử lý request; developer phải copy sang persistent storage nếu muốn dữ liệu sống lâu hơn request. Vì vậy:

- `file.getInputStream()` **tránh việc tạo thêm byte[] toàn file ở controller**.
- Nó **không bảo đảm parser chưa lưu toàn file tạm trên disk trước khi controller được gọi**.
- Một `application/octet-stream` endpoint đọc `HttpServletRequest.getInputStream()` có thể stream từ request body trong lúc nhận, nhưng proxy/connector vẫn có thể buffer.
- Nếu ingress đã nhận và buffer toàn bộ body, backend không thể giảm ingress temp pressure chỉ bằng việc dùng buffer 16 KiB.
- Streaming không đồng nghĩa zero-copy, không tự bảo vệ khỏi disk full, CPU DoS hoặc multipart header bombs.

### 2.1. Bốn vùng tệp cần ownership rõ

| Storage | Ví dụ | Ownership/cleanup |
| --- | --- | --- |
| Reverse proxy temp | Nginx request-body temp | Proxy, không phải ứng dụng |
| Servlet multipart temp | `spring.servlet.multipart.location` | Servlet container/multipart resolver, thường cuối request |
| Application staging | `app.upload.root/stage/*.part` | App `finally` và orphan janitor |
| Application ready/quarantine | `app.upload.root/ready/<id>.bin` | Business retention, ACL, delete job |

Một request multipart có thể dùng disk ở **proxy**, **Servlet** và **app** cùng thời điểm. Đặt staging ở một ổ khác không làm Servlet temp biến mất. Nếu nhận file rất lớn với nhiều requests đồng thời, kiểm cả disk bytes, inodes, quotas và các volumes thay vì chỉ đo Java heap.

### 2.2. Các trạng thái đúng của upload

~~~text
RECEIVING -> STAGING (.part, private)
                  |
                  +-- size violation ----> REJECTED -> cleanup
                  +-- client abort ------> FAILED -> cleanup
                  +-- disk I/O error ----> FAILED -> cleanup
                  +-- invalid/empty -----> REJECTED -> cleanup
                  |
                  v
              VALIDATED
                  |
                  v
         ATOMIC PUBLISH TO READY
                  |
                  v
          COMMITTED -> HTTP 201
                  |
                  v
         Retention / authorized delete
~~~

Không cho consumer đọc tệp đang được ghi dở. Nếu client bị mất response 201 sau khi server commit, dữ liệu **có thể đã được lưu thành công**; production phải có idempotency-key và receipt persistence để xử lý retry mà không tạo duplicate. Demo không lưu receipt DB nên vẫn có thể tạo hai files khi retry.

## 3. Giới hạn upload phải xuất hiện ở nhiều tầng

### 3.1. Phân loại các ngưỡng

| Ngưỡng | Quyết định | Tầng |
| --- | --- | --- |
| Max body size ở edge | Tổng request gửi qua proxy | CDN/Ingress |
| Max multipart file | Một file part | Servlet parser |
| Max multipart request | Toàn bộ multipart body gồm boundaries/fields | Servlet parser |
| Max parts/per-part headers | Header/metadata amplification | Tomcat parser |
| Max HTTP request headers | Headers của request tổng thể | Tomcat/edge |
| Max actual bytes | Bytes mà app đã đọc, kể cả unknown Content-Length | UploadService |
| Max concurrent storage copies | Số writers đang ghi stage | Semaphore trong service |
| Tenant quota | Bytes/day/object count per user/organization | DB/shared rate limiter |
| Max on-disk | Tmp, stage, ready, scan quarantine | Filesystem/volume policy |
| Upload timeout | Slow client, stalled write, network | Proxy/server/client |
| Max decoded/decompressed content | ZIP/archive/encoded request | Validator/scanner/parser |

Chỉ nâng `max-file-size` từ 1 MB lên 50 MB **không** giải quyết số uploads đồng thời, nhiều parts, disk leak hay malware. **Giới hạn ở edge** giúp từ chối trước khi tốn tài nguyên backend, nhưng khi request đã tới ứng dụng vẫn phải kiểm byte count chính xác.

### 3.2. Properties Spring Boot 4.1.2 trên Servlet/MVC

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=50MB
spring.servlet.multipart.max-request-size=52MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.location=${UPLOAD_TMP_DIR:${java.io.tmpdir}}
spring.servlet.multipart.resolve-lazily=false
spring.servlet.multipart.strict-servlet-compliance=true
~~~

Theo Spring Boot docs, defaults là `max-file-size=1MB`, `max-request-size=10MB` và `file-size-threshold=0B`. DataSize `50MB` của Spring dùng đơn vị bội 1024 theo cấu hình; bài lab thêm ngưỡng bytes **52.428.800** tương đương 50 MiB để kiểm chính xác trong vòng đọc.

- `file-size-threshold=0B` cho phép flush các parts ra disk sớm, tránh giữ toàn bộ file trong heap, nhưng Servlet parser vẫn phải nhận multipart.
- `max-request-size` phải đủ overhead multipart (headers, boundaries, metadata) ngoài file bytes; nên chừa headroom có kiểm soát.
- `location` chỉ là **Servlet temp**, khác `app.upload.root`. Nếu cấp `UPLOAD_TMP_DIR` tùy chỉnh thì tạo directory writable trước; production dùng volume có quota rõ.
- `resolve-lazily=true` chỉ trì hoãn parse đến lần access phần dữ liệu, **không tự làm upload streaming an toàn hơn**.
- `strict-servlet-compliance=true` hỗ trợ kiểu multipart/form-data đúng Servlet semantics; nếu cần multipart/mixed phải thiết kế/test khác.
- Không set `max-file-size=-1` hoặc `max-request-size=-1` chỉ để không thấy lỗi 413.

### 3.3. Tomcat-specific hardening

~~~properties
server.tomcat.max-part-count=4
server.tomcat.max-part-header-size=1KB
server.max-http-request-header-size=8KB
~~~

`max-part-count` chặn client gửi hàng nghìn form parts dù từng part rất nhỏ; `max-part-header-size` chặn metadata headers quá dài; giới hạn HTTP header tổng không thay thế chúng. Những property `server.tomcat.*` **không có tác dụng tự động lên Jetty hoặc Reactor Netty**. Các limits parse có thể gây HTTP 400/413 hoặc connection reset tùy connector/proxy.

`server.tomcat.max-swallow-size` ảnh hưởng xử lý unread request body sau khi reject; nó giải thích vì sao oversized upload đôi khi bị reset connection thay vì client nhận JSON 413. Không set giá trị vô hạn tùy tiện để “luôn thấy 413”.

### 3.4. Content-Length: kiểm sớm, không được tin duy nhất

Client có thể gửi:

~~~http
POST /api/uploads/raw HTTP/1.1
Host: localhost:8080
Content-Type: application/octet-stream
Content-Length: 1024
~~~

Nhưng với `Transfer-Encoding: chunked` không có Content-Length cố định, và proxy/HTTP2 có cơ chế framing khác. Client cũng có thể abort giữa chừng hoặc khai sai length. Vì vậy:

~~~text
if (declaredLength > limit) -> reject early
read repeatedly into small buffer
if (newBytes > limit - bytesAlreadyRead) -> reject before write
after EOF: bytesAlreadyRead must be > 0
if declaredLength >= 0: optionally compare to actual bytes
publish only when all checks passed
~~~

Phép so `newBytes > limit - alreadyRead` giúp không tính `alreadyRead + newBytes` gây overflow long. Khi request body bị nén, Content-Length có thể chỉ là **compressed bytes**; demo từ chối raw Content-Encoding khác identity, production nhận encoded body phải bound số bytes **đã giải nén**.

### 3.5. Disk budget và semaphore không chặn parser trước controller

Giả sử service cho phép 3 writers, mỗi writer tối đa 50 MiB: riêng **app staging** có thể xấp xỉ 150 MiB. Nhưng Servlet đã có thể spool 20 multipart requests × 50 MiB trước khi chúng xin semaphore; proxy có thể buffer thêm. Vì vậy 3 permits **không đồng nghĩa tổng chỉ có 150 MiB uploads in flight**. Cần upstream concurrency/rate limit, per-tenant quotas, disk free alerts và shutdown management. Filesystem free space, inodes và IOPS có thể là bottleneck trước heap.

## 4. Bảo mật tên file và vị trí lưu

### 4.1. Không lấy originalFilename làm đường dẫn

`MultipartFile.getOriginalFilename()` có thể là `../../evil.bin`, `C:\fakepath\...`, Unicode deceptive names hoặc tên null/empty; do client gửi, không đáng tin. Không viết:

~~~java
// KHÔNG AN TOÀN: user-supplied name can traverse/overwrite.
Path p = root.resolve(file.getOriginalFilename());
file.transferTo(p);
~~~

Dùng ID ngẫu nhiên do server sinh. Trong demo, file luôn có tên `<UUID>.bin` và thư mục private:

~~~text
data/
  stage/
    incoming-<random>.part
  ready/
    <uuid>.bin
~~~

Việc `Path.normalize()` chưa giải quyết symlink-race nếu attacker có quyền ghi bên trong root. Production phải dùng root được platform/admin provision, user/ACL hạn chế, không cho untrusted local users đổi staging dirs, không phục vụ thư mục này dưới webroot. Với multi-tenant storage, phải kiểm tenant/owner trước mọi thao tác access/delete/download.

### 4.2. Content-Type, extension và SHA-256 không chứng minh file an toàn

- MIME header `MultipartFile.getContentType()` có thể do client giả mạo.
- Extension có thể sai; magic bytes chỉ là tín hiệu định dạng sơ bộ.
- JPEG/PNG/PDF/ZIP thật vẫn có thể chứa payload độc hại hoặc khai thác parser.
- SHA-256 dùng cho integrity/dedup, **không** là antivirus.
- Với PDF/Office cần malware scanning/CDR tùy policy; với ZIP phải giới hạn expanded bytes, item count và recursion/CPU (ZIP bomb).
- File cần quarantine trước khi scan, không publish dưới URL public khi chưa pass.
- Nếu download, dùng opaque ID + authorization, `Content-Disposition` an toàn, `X-Content-Type-Options: nosniff` và chặn XSS/executable content.

**Demo chỉ nhận opaque bytes, không parse nội dung và không cung cấp download endpoint.** File chưa được scan không được coi là “an toàn để người dùng khác mở”.

## 5. Cleanup và commit: phân biệt đường bình thường với crash

### 5.1. try-with-resources

InputStream từ `MultipartFile.getInputStream()` phải được đóng bởi caller; OutputStream tới stage phải đóng trước khi move. Đừng truyền MultipartFile vào background thread sau khi controller trả response vì Servlet temp có thể đã được cleanup. Nếu muốn background scanning, copy stage persistent trước, lưu metadata/job ID và worker chỉ đọc storage do ứng dụng sở hữu.

### 5.2. finally và atomic publish

Một pattern đúng:

~~~java
// Fragment, stagingDirectory và readyDirectory là private Paths.
Path stage = null;
try {
    stage = Files.createTempFile(stagingDirectory, "part-", ".tmp");
    try (OutputStream out = Files.newOutputStream(stage)) {
        // bounded streaming copy + checksum + validators
    }
    Files.move(stage, readyDirectory.resolve("opaque.bin"),
            StandardCopyOption.ATOMIC_MOVE);
    stage = null;
}
finally {
    if (stage != null) Files.deleteIfExists(stage);
}
~~~

Nếu `Files.move(... ATOMIC_MOVE)` được filesystem hỗ trợ trên cùng filesystem, consumers không thấy file ready nửa chừng. **Atomic rename không đồng nghĩa fsync/power-loss durability**; production có thể cần FileChannel.force(), sync directory metadata, DB receipt transaction hoặc object store commit semantics. Nếu move cross-filesystem fail, demo **không fallback âm thầm sang copy non-atomic**.

Nếu Files.deleteIfExists fail, không nói cleanup thành công; ghi alert, tăng cleanup failure metric và để janitor xử lý. Trong file storage bị local user untrusted ghi/swap symlinks, API này chưa chống hết TOCTOU; cần quyền thư mục nghiêm ngặt và secure filesystem operations.

### 5.3. SIGTERM, SIGKILL và orphan janitor

- Khi request lỗi nhưng JVM còn chạy, try/finally có cơ hội xóa .part và release permit.
- Khi client disconnect, raw InputStream có thể ném IOException, nhưng không nhất thiết phát hiện ngay nếu proxy buffer.
- Khi SIGTERM và graceful shutdown, finite uploads có thể hoàn tất trong grace nếu server/app cấu hình đúng.
- Khi SIGKILL/OOM/crash, **finally không chạy**; staged files trên persistent volume/object store có thể còn.
- Orphan janitor phải xét lease/owner/last activity, TTL, tenant, namespace và grace period; không xóa mọi .part chỉ vì filesystem mtime cũ khi upload còn đang chạy.

Thiết kế state trong DB/object store:

~~~text
upload_id | tenant_id | stage_key | state
bytes_received | lease_owner | lease_expires_at
checksum | committed_key | created_at | retention_until
~~~

Janitor chỉ xóa khi lease thực sự hết hạn, owner không active, đã qua safety delay, không được lấy path bất kỳ do client cung cấp. Với object storage multipart uploads phải AbortMultipartUpload và dùng lifecycle cleanup cho incomplete multipart uploads. Ready blobs tồn tại mà DB receipt chưa commit cần reconciliation; không được tự xóa business data đã thành công vì thấy “không có response 201”.

## 6. Dự án Spring Boot 4.1.2 / Java 17

Dự án có endpoints:

| API | Phương thức | Content-Type | Kết quả |
| --- | --- | --- | --- |
| `/api/uploads/multipart` | POST | multipart/form-data, part=file | HTTP 201 receipt |
| `/api/uploads/raw` | POST | application/octet-stream | HTTP 201 receipt |
| `/api/uploads/health` | GET | text | Smoke test |

Không có GET/DELETE file public, không có auth hay scanner. Sử dụng localhost để không tạo một upload service mở cho Internet.

### 6.1. Cấu trúc project

~~~text
large-upload-lab/
  pom.xml
  src/main/java/com/example/uploadlab/
    LargeUploadApplication.java
    UploadService.java
    UploadController.java
    UploadErrorAdvice.java
  src/main/resources/
    application.properties
  src/test/java/com/example/uploadlab/
    UploadIntegrationTest.java
  data/
    stage/   # tự tạo bởi service
    ready/
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>large-upload-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
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

Starter MVC dùng Servlet/Tomcat multipart support, Actuator cho health, MVC test starter cho JUnit và @SpringBootTest. Không cần cài thêm Apache Commons FileUpload trong demo.

### 6.3. LargeUploadApplication.java

~~~java
package com.example.uploadlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LargeUploadApplication {
    public static void main(String[] args) {
        SpringApplication.run(LargeUploadApplication.class, args);
    }
}
~~~

### 6.4. application.properties

~~~properties
spring.application.name=large-upload-lab
server.address=127.0.0.1
server.port=8080

spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=50MB
spring.servlet.multipart.max-request-size=52MB
spring.servlet.multipart.file-size-threshold=0B
spring.servlet.multipart.location=${UPLOAD_TMP_DIR:${java.io.tmpdir}}
spring.servlet.multipart.resolve-lazily=false
spring.servlet.multipart.strict-servlet-compliance=true

server.tomcat.max-part-count=4
server.tomcat.max-part-header-size=1KB
server.max-http-request-header-size=8KB

# 50 MiB exact bytes; áp cho cả multipart lẫn raw reader.
app.upload.max-bytes=52428800
app.upload.root=${APP_UPLOAD_ROOT:./data}

management.endpoints.web.exposure.include=health
~~~

Trong production, cấu hình `server.address` không được giữ 127.0.0.1 nếu Service cần kết nối qua Pod IP. Đặt Servlet temp trên volume writable có quota/metrics; app root là thư mục riêng có quyền hạn hẹp. Nếu `UPLOAD_TMP_DIR` tùy chỉnh chưa tồn tại hoặc không writable, multipart parser có thể lỗi trước controller.

### 6.5. UploadService.java — copy theo buffer + giới hạn + SHA-256 + cleanup

~~~java
package com.example.uploadlab;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;
import java.util.concurrent.Semaphore;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class UploadService {

    private final Path stageDir;
    private final Path readyDir;
    private final long maxBytes;

    // Per-instance storage writer limit; không phải cluster/tenant quota.
    private final Semaphore slots = new Semaphore(3);

    public record Receipt(String id, long bytes, String sha256) {}

    public UploadService(
            @Value("${app.upload.root}") String rootLocation,
            @Value("${app.upload.max-bytes}") long maxBytes)
            throws IOException {

        if (maxBytes <= 0) {
            throw new IllegalArgumentException("maxBytes must be positive");
        }
        this.maxBytes = maxBytes;

        Path root = Path.of(rootLocation).toAbsolutePath().normalize();
        // Demo giả định root do app/platform sở hữu, không writable
        // bởi local users không đáng tin (cần ACL ở production).
        Files.createDirectories(root);
        stageDir = Files.createDirectories(root.resolve("stage"));
        readyDir = Files.createDirectories(root.resolve("ready"));
    }

    public Receipt store(InputStream input, long claimedLength)
            throws IOException {

        if (claimedLength == 0) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "empty file");
        }
        if (claimedLength > maxBytes) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE, "declared size too large");
        }

        if (!slots.tryAcquire()) {
            throw new ResponseStatusException(
                    HttpStatus.TOO_MANY_REQUESTS,
                    "too many active storage copies");
        }

        Path stage = null;
        try {
            stage = Files.createTempFile(stageDir, "incoming-", ".part");

            MessageDigest sha256 = newSha256();
            long written = 0L;
            byte[] buffer = new byte[16 * 1024];

            try (OutputStream out = Files.newOutputStream(
                    stage, StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                int count;
                while ((count = input.read(buffer)) != -1) {
                    if (count == 0) {
                        continue;
                    }
                    if (count > maxBytes - written) {
                        throw new ResponseStatusException(
                                HttpStatus.PAYLOAD_TOO_LARGE,
                                "actual uploaded bytes exceed limit");
                    }
                    out.write(buffer, 0, count);
                    sha256.update(buffer, 0, count);
                    written += count;
                }
            }

            if (written == 0) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "empty file");
            }
            if (claimedLength >= 0 && written != claimedLength) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "declared size does not match actual bytes");
            }

            String id = UUID.randomUUID().toString();
            Path published = readyDir.resolve(id + ".bin");

            // Khi ATOMIC_MOVE unsupported, throw và cleanup stage;
            // không fallback sang copy non-atomic lên ready path.
            Files.move(stage, published,
                    StandardCopyOption.ATOMIC_MOVE);
            stage = null;

            return new Receipt(
                    id, written, HexFormat.of().formatHex(sha256.digest()));
        }
        finally {
            try {
                if (stage != null) {
                    Files.deleteIfExists(stage);
                }
            }
            finally {
                // Release permit kể cả khi cleanup xóa file bị lỗi.
                slots.release();
            }
        }
    }

    private static MessageDigest newSha256() {
        try {
            // Không dùng shared MessageDigest: instance không thread safe.
            return MessageDigest.getInstance("SHA-256");
        }
        catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(
                    "standard SHA-256 unavailable", e);
        }
    }
}
~~~

Điểm cần rà soát:

- `claimedLength` là hint; với raw chunked có thể `-1` nên phải có bộ đếm bytes thực.
- `maxBytes - written` ngăn overflow và ném 413 **trước khi ghi chunk vượt giới hạn**.
- Buffer 16 KiB giúp copy có memory bounded, nhưng không bao gồm Servlet/proxy buffers.
- `MessageDigest` được tạo **mỗi request**, tránh shared mutable digest.
- Stage tạo tên random. Không gọi `getOriginalFilename()` để quyết định path.
- `OutputStream` đóng **trước khi move**, bắt lỗi ghi/close/flush.
- Move atomic khi filesystem hỗ trợ và hai thư mục trên cùng storage root; nếu không có atomic move thì phải xử lý lỗi và không public file một phần.
- `stage=null` chỉ sau khi move thành công. Finally xóa stage nếu bất cứ bước nào ném lỗi, kể cả ResponseStatusException.
- Nested finally bảo đảm `slots.release()` kể cả cleanup throw IOException.
- Nếu client không nhận response 201, blob có thể đã commit; app demo chưa có idempotency/DB receipts.
- Chưa có file type scanner, tenant authorization, upload count cap hoặc fsync; cần bổ sung trước production.

### 6.6. UploadController.java — hai đường ingest

~~~java
package com.example.uploadlab;

import java.io.IOException;
import java.io.InputStream;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {
    private final UploadService service;

    public UploadController(UploadService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public String health() {
        return "upload-demo-ready";
    }

    @PostMapping(
            path = "/multipart",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<UploadService.Receipt> multipart(
            @RequestParam("file") MultipartFile file)
            throws IOException {

        if (file.isEmpty()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "empty part");
        }

        // MultipartFile may already be spooled by Servlet parser.
        try (InputStream in = file.getInputStream()) {
            UploadService.Receipt receipt =
                    service.store(in, file.getSize());
            return ResponseEntity.status(HttpStatus.CREATED).body(receipt);
        }
    }

    @PostMapping(
            path = "/raw",
            consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<UploadService.Receipt> raw(
            HttpServletRequest request)
            throws IOException {

        String contentEncoding = request.getHeader("Content-Encoding");
        if (contentEncoding != null
                && !contentEncoding.equalsIgnoreCase("identity")) {
            throw new ResponseStatusException(
                    HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                    "encoded request body unsupported");
        }

        // May be -1 (unknown/chunked); service counts all bytes.
        try (InputStream in = request.getInputStream()) {
            UploadService.Receipt receipt =
                    service.store(in, request.getContentLengthLong());
            return ResponseEntity.status(HttpStatus.CREATED).body(receipt);
        }
    }
}
~~~

Với multipart, Servlet parser đã xử lý framing boundaries và file.getSize() chỉ báo bytes của part; đừng cố đọc `HttpServletRequest.getInputStream()` lần nữa như raw request sau multipart parsing. Với raw, Content-Length là toàn body nếu được cung cấp. Cả hai đường **không serve file** và không dựa trên filename do client gửi.

### 6.7. UploadErrorAdvice.java

~~~java
package com.example.uploadlab;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

@RestControllerAdvice
public class UploadErrorAdvice {

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<Map<String, String>> tooLarge(
            MaxUploadSizeExceededException ignored) {
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(Map.of("error", "multipart_size_limit_exceeded"));
    }
}
~~~

Nếu Spring MVC nhận `MaxUploadSizeExceededException`, advice map sang 413. Nếu gateway/Tomcat từ chối **trước DispatcherServlet** hoặc đóng connection khi còn unread body, response có thể khác hoặc client nhận reset. `ResponseStatusException` của app được Spring xử lý; error JSON shape không bảo đảm như một mẫu cứng trừ khi bạn định nghĩa contract riêng.

## 7. Chạy local và thử cURL

### 7.1. Build và chạy

~~~bash
java -version
mvn -version
mvn clean verify
mvn spring-boot:run
~~~

Hoặc chạy JAR từ lần package vừa có:

~~~bash
java -jar target/large-upload-lab-0.0.1-SNAPSHOT.jar
~~~

Không chạy cả hai lệnh start cùng lúc trên cổng 8080. Smoke test:

~~~bash
curl -i http://127.0.0.1:8080/api/uploads/health
curl -i http://127.0.0.1:8080/actuator/health
~~~

Endpoint demo có body chính xác:

~~~text
upload-demo-ready
~~~

Actuator status có thể đổi theo trạng thái service và health config; health 200 không chứng minh đĩa còn đủ dung lượng upload.

### 7.2. Tạo dữ liệu thử nghiệm

POSIX/Linux/macOS/WSL:

~~~bash
mkdir -p test-data
dd if=/dev/zero of=test-data/one-mib.bin bs=1048576 count=1
wc -c test-data/one-mib.bin
dd if=/dev/zero of=test-data/over-limit.bin bs=1048576 count=51
wc -c test-data/over-limit.bin
~~~

Tệp thứ nhất là **1.048.576 bytes (1 MiB)**, tệp thứ hai là **53.477.376 bytes (51 MiB)**. Không thử các lệnh này lên production upload endpoints. Dùng data giả để tránh lộ thông tin người dùng.

### 7.3. POST multipart thành công

~~~bash
curl -i \
  -F "file=@test-data/one-mib.bin;type=application/octet-stream" \
  http://127.0.0.1:8080/api/uploads/multipart
~~~

Khi thành công, HTTP status **201** và receipt có các field:

~~~json
{
  "id": "26d4331a-6d87-48f5-8927-f9aa594ad2a3",
  "bytes": 1048576,
  "sha256": "(64 hexadecimal characters)"
}
~~~

ID và digest ở ví dụ là **ký hiệu mô tả**, không phải phản hồi thật; UUID sinh ngẫu nhiên. File được lưu tại `data/ready/<id>.bin`. Stage không còn file của request đã hoàn thành.

~~~bash
find ./data/stage -type f
find ./data/ready -type f
sha256sum test-data/one-mib.bin
~~~

So SHA-256 của local file với receipt. Trên macOS dùng `shasum -a 256` nếu `sha256sum` không có. Hash khớp chứng minh integrity, không chứng minh file lành tính.

### 7.4. POST raw stream thành công

~~~bash
curl -i \
  -H "Content-Type: application/octet-stream" \
  --data-binary @test-data/one-mib.bin \
  http://127.0.0.1:8080/api/uploads/raw
~~~

`--data-binary` giữ bytes, không form-encode nội dung. Server xử lý qua ServletInputStream và buffer 16 KiB. Nếu cURL/proxy đã buffer body thì không phải bằng chứng streaming end-to-end; đo riêng ở connector/proxy khi cần.

### 7.5. Oversized multipart

~~~bash
curl -v \
  -F "file=@test-data/over-limit.bin" \
  http://127.0.0.1:8080/api/uploads/multipart
~~~

Với max-file-size=50MB và file 51MiB, request phải bị **reject** và không tạo ready file. Có thể nhận HTTP 413 hoặc kết nối reset khi Tomcat/edge không tiếp tục đọc body. Không hardcode mọi container sẽ trả JSON error advice.

### 7.6. Oversized raw

~~~bash
curl -v \
  -H "Content-Type: application/octet-stream" \
  --data-binary @test-data/over-limit.bin \
  http://127.0.0.1:8080/api/uploads/raw
~~~

Raw không đi qua `spring.servlet.multipart.max-file-size`; app chặn dựa trên Content-Length khi biết hoặc bytes đọc thực nếu không biết. Nếu server từ chối trước khi cURL gửi hết, client có thể báo EOF/reset; bảo đảm quan trọng là **không publish ready file vượt limit**.

### 7.7. Body rỗng và sai content-type

~~~bash
: > test-data/empty.bin
curl -i -F "file=@test-data/empty.bin" \
  http://127.0.0.1:8080/api/uploads/multipart

curl -i -H "Content-Type: application/octet-stream" \
  --data-binary @test-data/empty.bin \
  http://127.0.0.1:8080/api/uploads/raw

curl -i -X POST -H "Content-Type: text/plain" --data "abc" \
  http://127.0.0.1:8080/api/uploads/raw
~~~

Empty nhận 400; text/plain không phù hợp raw endpoint `consumes=application/octet-stream`, thường 415. Nếu định hỗ trợ text/image/PDF, cần content validation/quarantine riêng, không dùng request Content-Type như bằng chứng.

### 7.8. Giả lập client abort, không coi test hoàn toàn deterministic

~~~bash
curl --limit-rate 20k --max-time 2 \
  -H "Content-Type: application/octet-stream" \
  --data-binary @test-data/one-mib.bin \
  http://127.0.0.1:8080/api/uploads/raw
~~~

CURL có thể timeout/đứt giữa chừng, nhưng socket/proxy buffering khiến thời điểm server thấy EOF không cố định. Điều cần test bằng network fault injection là **không có ready blob một phần**, staging và Servlet temporary files được dọn sau khi request lifecycle kết thúc, không giữ semaphore permit. Không suy từ một lần cURL rằng mọi đường client abort luôn kích hoạt IOException ngay lập tức.

### 7.9. Test chunked/unknown Content-Length

Một client có thể dùng `Transfer-Encoding: chunked`; raw handler nhận `getContentLengthLong()=-1` và phải count thật. Cách tạo request chunked phụ thuộc cURL/runtime:

~~~bash
curl --http1.1 -v \
  -H "Content-Type: application/octet-stream" \
  -H "Transfer-Encoding: chunked" \
  --data-binary @test-data/one-mib.bin \
  http://127.0.0.1:8080/api/uploads/raw
~~~

Kiểm cURL verbose để biết request framing **thực tế**; nếu proxy thay đổi framing, test không còn phản ánh kết nối trực tiếp. Application counter vẫn bảo vệ bytes thực nhận dù header size không có.

## 8. JUnit integration test với embedded Tomcat thật

Test dưới đây khởi động server thật trên `RANDOM_PORT`, dùng HttpClient Java 17 gửi bytes, đặt limit app 1 MiB cho CI, và dùng storage root riêng dưới target. Test nội dung 2048 bytes, empty, vượt limit và multipart filename traversal. Lớp test xóa thư mục test khi hoàn tất. Nó **không test** proxy/temp Servlet của OS, SIGKILL, disk full hay virus scan.

### 8.1. UploadIntegrationTest.java

~~~java
package com.example.uploadlab;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.UUID;
import java.util.stream.Stream;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "app.upload.max-bytes=1048576",
        "spring.servlet.multipart.max-file-size=2MB",
        "spring.servlet.multipart.max-request-size=3MB"
    }
)
class UploadIntegrationTest {

    private static final Path ROOT = Path.of(
            "target", "upload-it-" + UUID.randomUUID());

    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    @LocalServerPort
    int port;

    @DynamicPropertySource
    static void configureRoot(DynamicPropertyRegistry registry) {
        registry.add("app.upload.root",
                () -> ROOT.toAbsolutePath().toString());
    }

    private HttpResponse<String> post(
            String endpoint, String contentType,
            HttpRequest.BodyPublisher publisher) throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + endpoint))
                .header("Content-Type", contentType)
                .POST(publisher)
                .build();

        return CLIENT.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void rawSmallFileCommitsAndCleansStage() throws Exception {
        byte[] content = new byte[2048];
        java.util.Arrays.fill(content, (byte) 'A');

        HttpResponse<String> response = post(
                "/api/uploads/raw", "application/octet-stream",
                HttpRequest.BodyPublishers.ofByteArray(content));

        assertEquals(201, response.statusCode(), response.body());
        assertTrue(response.body().contains("\"bytes\":2048"),
                response.body());
        assertEquals(0, stageCount());
        try (Stream<Path> paths = Files.list(ROOT.resolve("ready"))) {
            assertTrue(paths.anyMatch(Files::isRegularFile));
        }
    }

    @Test
    void rawOversizedIsRejectedAndHasNoStage() throws Exception {
        byte[] content = new byte[1_048_577];

        // Với server local thường trả 413. Tuy nhiên nếu container
        // đóng sớm khi còn unread body, client có thể gặp IOException;
        // test cần được đánh giá cùng connector/test transport.
        HttpResponse<String> response = post(
                "/api/uploads/raw", "application/octet-stream",
                HttpRequest.BodyPublishers.ofByteArray(content));

        assertEquals(413, response.statusCode(), response.body());
        assertEquals(0, stageCount());
    }

    @Test
    void multipartIgnoresUntrustedOriginalName() throws Exception {
        String boundary = "----test-" + UUID.randomUUID();
        byte[] file = new byte[256];

        byte[] prefix = (
                "--" + boundary + "\r\n"
                + "Content-Disposition: form-data; name=\"file\"; "
                + "filename=\"../../evil.bin\"\r\n"
                + "Content-Type: application/octet-stream\r\n\r\n"
        ).getBytes(StandardCharsets.UTF_8);

        byte[] suffix = (
                "\r\n--" + boundary + "--\r\n"
        ).getBytes(StandardCharsets.UTF_8);

        HttpRequest.BodyPublisher publisher =
                HttpRequest.BodyPublishers.concat(
                    HttpRequest.BodyPublishers.ofByteArray(prefix),
                    HttpRequest.BodyPublishers.ofByteArray(file),
                    HttpRequest.BodyPublishers.ofByteArray(suffix));

        HttpResponse<String> response = post(
                "/api/uploads/multipart",
                "multipart/form-data; boundary=" + boundary,
                publisher);

        assertEquals(201, response.statusCode(), response.body());
        assertTrue(response.body().contains("\"bytes\":256"),
                response.body());
        assertEquals(0, stageCount());
    }

    @Test
    void emptyRawRejected() throws Exception {
        HttpResponse<String> response = post(
                "/api/uploads/raw", "application/octet-stream",
                HttpRequest.BodyPublishers.noBody());

        assertEquals(400, response.statusCode());
        assertEquals(0, stageCount());
    }

    private static long stageCount() throws IOException {
        try (Stream<Path> paths = Files.list(ROOT.resolve("stage"))) {
            return paths.count();
        }
    }

    @AfterAll
    static void cleanupTestRoot() throws IOException {
        if (Files.notExists(ROOT)) return;
        try (Stream<Path> paths = Files.walk(ROOT)) {
            paths.sorted(Comparator.reverseOrder())
                    .forEach(path -> {
                        try {
                            Files.deleteIfExists(path);
                        }
                        catch (IOException e) {
                            throw new UncheckedIOException(e);
                        }
                    });
        }
    }
}
~~~

**Đối chiếu:** `@SpringBootTest(webEnvironment=RANDOM_PORT)` dùng real embedded server, không chỉ mock controller. `@DynamicPropertySource` cấu hình private root cho test. `HttpClient` **không AutoCloseable trong Java 17**, nên không dùng try-with-resources. Một request raw 1MiB+1 bị app từ chối trước khi tạo stage khi Content-Length đã biết; với một số connector tình huống từ chối sớm có thể reset TCP, nên negative test trong môi trường cụ thể cần xử lý transport errors như một dạng reject và kiểm storage không có partial file.

Nếu muốn CI luôn deterministic ở mọi HTTP connector, thay test reject sớm bằng **server-side unit test store()** với InputStream khai size -1 và dữ liệu 1MiB+1; như vậy application buộc đọc đủ tới ngưỡng rồi throw 413 trong cùng JVM, không phụ thuộc client handling unread body. Đối với build Maven/Spring test đơn giản, class này minh họa cả kết quả HTTP-level.

Chạy:

~~~bash
mvn test
~~~

Expected: JUnit tests pass khi runtime/connector phù hợp và thư mục target writable; output text của Surefire tùy version. **Ví dụ được rà soát về logic nhưng chưa được thực thi Maven trong quá trình soạn bài.**

## 9. Java 17 độc lập: copy với số bytes có giới hạn

Tạo `BoundedCopyDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class BoundedCopyDemo {

    static long copy(InputStream in, OutputStream out, long max)
            throws IOException {

        byte[] buffer = new byte[4];
        long total = 0;
        int n;

        while ((n = in.read(buffer)) != -1) {
            if (n > max - total) {
                throw new IOException("limit exceeded");
            }
            out.write(buffer, 0, n);
            total += n;
        }
        return total;
    }

    public static void main(String[] args) throws Exception {
        byte[] data = "abcdefghij".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream ok = new ByteArrayOutputStream();
        System.out.println("copied=" +
                copy(new ByteArrayInputStream(data), ok, 10));
        System.out.println("exact=" + ok.toString("UTF-8"));

        ByteArrayOutputStream limited = new ByteArrayOutputStream();
        try {
            copy(new ByteArrayInputStream(data), limited, 8);
        }
        catch (IOException expected) {
            System.out.println(expected.getMessage());
        }
        System.out.println("partial-bytes=" + limited.size());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 BoundedCopyDemo.java
java BoundedCopyDemo
~~~

Stdout đúng:

~~~text
copied=10
exact=abcdefghij
limit exceeded
partial-bytes=8
~~~

Với 10 bytes và buffer 4 bytes, InputStream trả lần lượt 4+4+2. Ở limit 8, chunk cuối bị reject **trước khi ghi**, nên output chứa 8 bytes; application thật phải xóa file stage partial trong finally. Đây là ví dụ chạy độc lập với Java 17, không sử dụng Spring.

## 10. Failure modes: HTTP, file và process lifecycle

| Sự cố | Nơi phát hiện | Hành vi đúng |
| --- | --- | --- |
| Multipart > file cap | Servlet parser/proxy | Reject, không tạo ready; 413 hoặc reset |
| Raw > max bytes | UploadService | 413 (hoặc transport abort), cleanup stage |
| Empty upload | Controller/service | 400, không publish |
| Content-Type không hỗ trợ | Spring mapping | 415 |
| Request Content-Encoding gzip | Raw controller | 415; không giải nén âm thầm |
| Ba writers bận | Semaphore | 429; lưu lượng upstream vẫn cần bound |
| Client dừng TCP giữa upload | ServletInputStream/connector | IOException/EOF, stage cleanup |
| File write ném IOException/disk full | OutputStream | Không trả 201, cleanup/alert |
| Atomic move không được support | Files.move | Không expose partial, cleanup |
| SIGTERM/graceful | JVM + Boot + platform | Hết request hữu hạn trong budget |
| SIGKILL/OOM | Kernel/orchestrator | finally không chạy; janitor/retention |
| Response 201 bị mất | Client retry | Idempotency receipt contract |
| K8s Pod bị xóa | Platform | File local ephemeral không bền |
| Multi-pod request tới node khác | Storage architecture | Dùng shared/object storage |
| Nhiều file trong một multipart | Parser/route contract | Giới hạn parts và business count |
| ZIP bomb / PDF exploit | Content scanner | Validation/quarantine trước ready |
| Symlink/path traversal | Filesystem/storage layer | Random IDs, trusted root, ACL |
| Metadata DB ghi fail sau blob move | Business transaction | Reconciliation/compensation |
| Cleanup delete fail | Filesystem | Error metric, orphan janitor |

### 10.1. Client ngắt kết nối

Nếu client dừng trước khi multipart parser xử lý xong, controller có thể không được gọi; container dọn Servlet-owned temp theo request lifecycle. Nếu raw đọc dở, `read()` có thể throw; service.finally dọn app stage. Nhưng proxy đã buffer xong body thì backend vẫn có thể commit dù client disconnect — cần idempotency và receipt lookup, không giả định cứ client abort là storage rollback.

### 10.2. Disk full và permission errors

Nếu `out.write()`, `out.close()` hoặc `Files.move` throw IOException, code không trả 201. Finally cố delete stage; nếu delete cũng fail, cần alert và janitor. Disk của proxy/Servlet temp có thể đầy **trước khi vào service**, cần metrics riêng. Trong container `readOnlyRootFilesystem=true`, phải mount writable temp và storage volumes với permissions đúng UID; không chuyển JVM sang root user chỉ để workaround.

### 10.3. Thời hạn shutdown

Spring Boot graceful shutdown cần SIGTERM tới đúng Java process. Request lớn hơn grace budget phải được drain/cancel/replicated theo policy; staged file có thể xóa nếu finally được chạy. SIGKILL không chạy finally; nếu Pod volume ephemeral, file có thể biến mất cùng pod, nếu persistent volume/object store thì orphan tồn tại. Dùng leases/TTL và reconciliation để cleanup có cơ sở, không xóa file ngay khi nhìn thấy .part.

### 10.4. Atomicity và durability khác nhau

Atomic move giữa stage/ready trong cùng filesystem giúp consumer nhìn thấy **toàn bộ blob hoặc không có blob** nếu rename thành công. Không bảo đảm fsync/cross-process metadata transaction hoặc survive power loss. Với object store, dùng temporary object/UploadId, complete multipart upload sau kiểm đủ parts/checksum, rồi mới update business metadata. Với strict durability cần thiết kế commit order và fault injection.

## 11. Thiết kế production: content security và quota

### 11.1. File type và quyền truy cập

Một endpoint upload public phải kiểm:

- AuthN/AuthZ, tenant ID từ principal chứ không tin request field.
- CSRF nếu browser gửi session cookie, Origin/CORS policy đúng model.
- Rate limits, total bytes/day, active upload sessions và object count.
- Allowlist loại file và parser-specific validation (MIME/extension/magic chỉ một phần).
- Malware scanning/CDR, quarantine, file decomposition limits cho ZIP/XML/Office.
- Private storage ngoài webroot, non-executable permissions, safe download headers.
- Random opaque identifiers, không chứa user filename/path trong storage keys.
- Quét lại file khi scanner/signatures cập nhật nếu threat model yêu cầu.
- Không log raw file body, Auth header, cookie hoặc PII trong original filename.
- Retention, legal holds, user delete, GDPR/data handling theo chính sách.

### 11.2. Upload state, retry và idempotency

Production có thể dùng:

~~~text
upload_id | tenant_id | idempotency_key_hash | state
stage_key | ready_key | bytes_expected | bytes_actual
sha256 | validated_type | scan_status
created_at | lease_expires_at | retention_until
~~~

State: RECEIVING → STAGED → SCANNING → READY hoặc FAILED/ABORTED. Nếu client retry cùng Idempotency-Key, ứng dụng phải trả receipt cũ khi đã commit, không ghi file trùng. Nếu đã có in-progress upload thì trả 202/409 theo contract. Phải scope key theo tenant, validate quyền và TTL; hash nội dung **không thay thế** idempotency key.

Nếu DB metadata commit fail sau file move, reconciliation job xử lý ready blob mồ côi hoặc compensation theo policy; không tự xem operation atomic xuyên DB/filesystem.

### 11.3. Object storage và resumable uploads

Với file vài GiB, cân nhắc client upload trực tiếp tới object store bằng presigned URLs:

~~~text
Client -> app: create upload session (auth/quota)
App -> S3/object store: initiate multipart upload, scoped URLs
Client -> object store: upload parts with checksums
Client -> app: finalize with part ETags
App -> object store: verify + CompleteMultipartUpload
Scanner -> quarantine -> ready
Orphan janitor -> AbortMultipartUpload when TTL expires
~~~

Khác biệt cần nhớ: S3 multipart ETag **không được mặc định xem là MD5 của toàn file**. Phải dùng checksums theo contract của provider, validate object size và quyền. Incomplete multipart uploads có thể bị tính phí storage cho tới khi abort/lifecycle cleanup. Dùng tus/resumable upload protocol nếu cần resume theo offset; tránh thiết kế append-only không có transaction/idempotency.

## 12. WebFlux/reactive có semantics khác Servlet MVC

Ở WebFlux, có `FilePart`, `Flux<PartEvent>` và `DataBuffer`. Những config multipart khác:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=50MB
spring.webflux.multipart.max-headers-size=10KB
spring.webflux.multipart.max-parts=4
~~~

Chúng **không điều khiển Servlet MultipartFile/Tomcat parser**. Với `Flux<PartEvent>`, Spring WebFlux docs nhấn mạnh DataBuffers phải **được consume, relay hoặc release** để tránh leak; cần backpressure, bounded queues và cancellation cleanup. Không `collectList()` toàn bộ file hoặc gọi blocking file I/O trên Netty event loop.

Ví dụ **chỉ mô tả API, không phải code upload đầy đủ**:

~~~java
// Fragment giả định một WebFlux handler:
@PostMapping(value = "/reactive-upload",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
Mono<Void> reactive(@RequestBody Flux<PartEvent> events) {
    // windowUntil(PartEvent::isLast), chọn FilePartEvent,
    // consume DataBuffers theo bounded pipeline, release on cancel,
    // count bytes, write staging, verify, atomic publish.
    return Mono.empty();
}
~~~

Đoạn trên **không thực sự consume dữ liệu**, chỉ là skeleton để chỉ sự khác biệt; không đưa lên production. Bản thực phải ghép publishers với DataBufferUtils và cleanup hooks, xử lý late cancellation/part boundaries và per-part limits. “Reactive” không tự giải quyết disk quota hay malware.

## 13. Quan sát, vận hành và capacity budget

| Metric/alert | Ý nghĩa |
| --- | --- |
| `uploads_started_total` | Tổng yêu cầu upload |
| `uploads_committed_total` | Số commits thành công |
| `uploads_rejected_total{reason}` | size/parts/type/auth/concurrency |
| `upload_bytes_received_total` | Bytes thực đọc, không chỉ header |
| `upload_duration_seconds` | Latency và throughput |
| `upload_active_storage_copies` | Số permits đang dùng |
| `upload_staged_bytes` | Application temp storage pressure |
| `upload_orphan_count/age` | Crash cleanup debt |
| `upload_cleanup_failures_total` | Lỗi Files.deleteIfExists/AbortMultipartUpload |
| `upload_storage_move_errors_total` | Atomic move/quota/permissions |
| `servlet_temp_disk_bytes` | Disk parser, bên ngoài app stage |
| `edge_request_body_temp_bytes` | Reverse proxy buffer pressure |
| `disk_free_bytes/inodes` | Capacity trước khi đầy |
| `http.server.requests` | HTTP latency/error aggregate |
| `upload_scanner_queue_lag` | Backlog kiểm malware |

Không phải tất cả metric trên đã được Actuator tự động instrument. Cần custom Micrometer gauges/counters, platform volume metrics và safe logging. **Không tag upload ID, filename, user ID hoặc raw URL vào metric labels**: cardinality/PII có thể bùng. Có alert khi staged bytes hoặc oldest incomplete upload vượt TTL, file-system free thấp, 413/429 tăng và janitor fail.

### 13.1. Tính capacity minh họa

Ví dụ 3 writers × 50 MiB = tối đa ~150 MiB app stage, nhưng cần cộng Servlet parser temp, proxy buffering, ready storage, orphan files, rolling deployment và disk/inodes headroom. Nếu có 10 connections multipart × 50 MiB đến Tomcat, Servlet temp có thể chiếm nhiều hơn 150 MiB trước khi controller xin permit. Giải pháp: gateway rate/concurrency limits, temp volume quotas, per-tenant budgets và xét large object direct-to-storage.

### 13.2. Log ở mức metadata

Một dòng log an toàn dạng minh họa:

~~~text
upload_committed id=opaque bytes=1048576 duration_ms=87
~~~

Không log file bytes, raw multipart body, bearer token, nguyên tên file do client gửi hoặc secret storage path. SHA-256 full nếu cần lưu trong DB, không bắt buộc xuất vào logs. Audit stream quan trọng phải có durability, không trông hoàn toàn vào stdout của Pod đang restart.

## 14. Ma trận kiểm thử bắt buộc trước production

| Test | Điều kiện | Kết quả |
| --- | --- | --- |
| Multipart nhỏ | File 1KiB | 201, đúng bytes/hash, stage sạch |
| Raw nhỏ | 1MiB | 201, đúng bytes/hash, stage sạch |
| File rỗng | 0 bytes | 400, không ready |
| Vừa đúng max | 50MiB | 201 nếu disk/other policies cho phép |
| Multipart > cap | 51MiB | Reject 413 hoặc reset, không ready |
| Raw > cap length known | Content-Length > limit | Từ chối sớm, không ready |
| Raw > cap length unknown | Chunked > limit | Đếm vượt rồi reject, cleanup |
| Request nhiều parts | > max-part-count | Parser reject, không ready |
| Long part header | > max-part-header-size | Reject ở connector |
| Client abort | TCP reset giữa body | Partial staging không thành ready |
| Slow client | 1KiB/s | Timeout/quota, không giữ worker vô hạn |
| 4 uploads đồng thời | 3 permits | Không có >3 storage writers |
| Disk full | Write throw IOException | Cleanup + alert, không 201 |
| Move failed | Cross filesystem/unsupported | Không expose partial ready |
| Filename ../ | Untrusted originalFilename | File chỉ trong private root |
| SIGTERM | Request đang diễn ra | Dừng trong grace/handoff |
| SIGKILL | Process bị kill | Orphan janitor/lease phục hồi |
| Duplicate retry | Lost 201 response | Existing receipt/idempotency |
| ZIP bomb/malware | Malicious payload | Quarantine/reject sau scanning |
| Multi-pod failover | Upload/lookup qua pod khác | Durable shared storage |
| App vs proxy limit | Proxy thấp hơn app | Reject đúng tầng, tracing rõ |

Không tuyên bố toàn ma trận đã chạy vì `mvn test` pass. Các test fault injection/network/K8s/security scanning cần môi trường riêng. Với HTTP 413/reset, kiểm **không có file ready trái phép** quan trọng hơn hardcode mọi connector trả cùng status.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| 413 ngay với file >1MB | Boot multipart default 1MB/file | Điều chỉnh cap đúng yêu cầu |
| Vẫn 413 khi app max=50MB | Edge/Ingress cap thấp hơn | Kiểm config từng hop |
| /tmp đầy dù controller streaming | Servlet multipart spool | Temp volume/quota/edge limits |
| Heap OOM khi upload lớn | getBytes()/readAllBytes()/logs body | Bounded stream |
| Raw chunked vượt cap | Chỉ tin Content-Length | Count actual bytes |
| Multipart nhiều parts làm CPU cao | Không giới hạn part count/header | Tomcat parser limits |
| .part còn sau exception | Không finally hoặc delete fail | Cleanup + metric/janitor |
| .part còn sau SIGKILL | Finally không chạy | Lease-based orphan GC |
| Ready file chứa một phần | Ghi thẳng ready | Stage + atomic publish |
| Files.move ATOMIC_MOVE fail | Cross-filesystem/provider | Same FS hoặc object-store commit |
| Filename traversal | Dùng originalFilename | Server-generated UUID |
| MIME giả | Tin Content-Type | Validator/strict decoder/scanner |
| ZIP nhỏ làm OOM khi extract | Không bound expanded size | Decompression limits |
| Socket reset thay vì 413 | Tomcat max-swallow-size/proxy behavior | Treat as reject, inspect layer |
| Quá nhiều 429 | Semaphore saturated | Shared quotas/edge concurrency |
| Cùng file upload hai lần | 201 lost, retry no idempotency | Durable receipt key |
| File biến mất khi pod restart | Pod-local ephemeral stage/ready | Durable storage |
| WebFlux DataBuffer leak | Không release canceled buffers | Consume/release, bounded flow |
| Bị disk full dù app stage ít | Proxy/Servlet/ready nhiều bytes | Volume-level metrics |
| Mọi file có URL public | Truyền file ngoài webroot sai | Private storage+ACL |
| Response 201 nhưng DB chưa commit | Commit ordering | Reconciliation/saga |

## 16. Checklist production

### Input/HTTP
- [ ] Multipart file/request/part/header limits hợp lệ và edge cap phối hợp?
- [ ] Raw body đếm bytes thực, xử lý Content-Length unknown/chunked?
- [ ] Có connection/read timeout, rate limit, per-tenant quotas, max concurrent?
- [ ] Servlet/proxy temporary locations có dung lượng/quota/metrics và quyền file đúng?
- [ ] Không nạp cả file lên heap, không log raw file?

### Storage/cleanup
- [ ] Tên file do server tạo, root private, không cho user chọn path?
- [ ] Stage/ready cùng FS hoặc có object-store transactional commit?
- [ ] Input/output đóng, stage dọn trong finally, permit luôn release?
- [ ] No partial ready on error; move/disk errors được alert?
- [ ] Có lease/TTL janitor cho SIGKILL và incomplete multipart uploads?
- [ ] Có retention/delete và durable idempotency receipt?
- [ ] Multi-pod dùng shared durable storage thay vì Pod-local?
- [ ] Không coi SHA-256 là antivirus hoặc atomic rename là durable commit tuyệt đối?

### Security
- [ ] AuthN/AuthZ, CSRF policy, tenant ownership và quotas?
- [ ] MIME/extension/magic/decoder validation + antivirus/CDR nếu cần?
- [ ] Chống ZIP bomb, XML bombs và parser resource exhaustion?
- [ ] Private quarantine, no arbitrary upload file execution, safe download?
- [ ] Không tin original filename/content-type/forwarded headers?
- [ ] Logs không lộ PII, tokens, file bytes; metrics labels bounded?

### QA/operations
- [ ] JUnit real-port kiểm 201, 400, 413, staging cleanup?
- [ ] Curl kiểm raw/multipart/boundaries/chunked client abort?
- [ ] Test disk full, slow clients, SIGTERM/SIGKILL và orphan GC?
- [ ] Metrics staged bytes/oldest orphan/temp free/cleanup errors?
- [ ] Có rollback/runbook khi proxy limit, disk quota, scanner downtime?
- [ ] Code/docs đánh dấu rõ demo không có production scanning/auth?

## 17. Câu hỏi tự kiểm tra kèm đáp án

**1.** `MultipartFile.getInputStream()` có tránh Servlet temp disk không?

**Đáp án:** Không; nó tránh `getBytes()` copy toàn bộ file vào app heap, nhưng Servlet multipart parser có thể spool vào temp trước controller.

**2.** Spring Boot Servlet multipart mặc định file/request max bao nhiêu?

**Đáp án:** Theo docs là **1MB/file, 10MB/request**; raw application/octet-stream không chịu các properties đó.

**3.** Vì sao chỉ kiểm Content-Length là sai?

**Đáp án:** Có chunked/unknown length, proxy transformation/abort, client untrusted; phải đếm bytes thực.

**4.** Khi body 50MiB đang ghi, tại sao không ghi trực tiếp vào ready path?

**Đáp án:** Consumer có thể thấy partial file; dùng staging rồi atomic publish khi đủ bytes/validated.

**5.** Vì sao `Files.move(...ATOMIC_MOVE)` không chứng minh dữ liệu survive power loss?

**Đáp án:** Atomic namespace rename không tự fsync file/metadata hoặc commit transaction DB.

**6.** Khi SIGKILL, finally có xóa .part không?

**Đáp án:** Không. Cần janitor theo lease/TTL, không xóa nhầm active uploads.

**7.** UploadService semaphore=3 có giới hạn ba request multipart đang được Tomcat parse không?

**Đáp án:** Không hoàn toàn; parser có thể spool trước khi handler gọi service. Cần edge/connector budgets.

**8.** SHA-256 khớp có chứng minh file không có malware không?

**Đáp án:** Không, hash kiểm integrity, còn format/antivirus/CDR phải kiểm riêng.

**9.** Tại sao `getOriginalFilename()` không được dùng làm đường dẫn?

**Đáp án:** Dữ liệu do client kiểm soát có path traversal/Unicode/confusable và overwrite risks; server phải cấp opaque ID.

**10.** Vì sao client có thể thấy connection reset chứ không thấy 413?

**Đáp án:** Tomcat/proxy có thể không nuốt hết body khi từ chối; HTTP response có thể không đến client.

**11.** Client retry khi mất response 201 có nên tự tạo file mới?

**Đáp án:** Production nên dùng tenant-scoped idempotency receipt và trả kết quả đã commit nếu cùng request/key.

**12.** Vì sao 50MiB file có thể cần lớn hơn 50MiB disk budget?

**Đáp án:** Có proxy body temp, Servlet temp, app stage, ready, concurrency, orphan files và disk headroom.

**13.** WebFlux PartEvent có tự release DataBuffers khi handler bỏ qua stream không?

**Đáp án:** Không nên giả định; cần consume/relay/release buffers và cleanup cancel path đúng contract.

**14.** Để hỗ trợ files vài GiB, có nên chỉ đặt max-file-size=-1?

**Đáp án:** Không; cân nhắc direct-to-object-storage multipart/resumable upload, quotas, checksums, abort, scanner và durable state.

## 18. Tài liệu chính thức

- [Spring Boot — Handling Multipart File Uploads](https://docs.spring.io/spring-boot/how-to/spring-mvc.html).
- [Spring Boot 4.1 — Common Application Properties](https://docs.spring.io/spring-boot/4.1/appendix/application-properties/index.html).
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/).
- [Spring Framework — Multipart Resolver and Servlet Part](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html).
- [Spring Framework — MultipartFile Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/multipart/MultipartFile.html).
- [Spring Framework — MVC Multipart Controller](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html).
- [Spring Framework — WebFlux Multipart and PartEvent](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html).
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html).
- [JDK 17 — Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html).
- [JDK 17 — StandardCopyOption](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardCopyOption.html).
- [JDK 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html).
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
- [OWASP — Unrestricted File Upload](https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload).
- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578).
- [RFC 9110 — HTTP Semantics/413](https://www.rfc-editor.org/rfc/rfc9110).
- [Amazon S3 — Multipart Upload](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html).
- [Kubernetes — Ephemeral Volumes](https://kubernetes.io/docs/concepts/storage/ephemeral-volumes/).

**Kết luận:** Upload file lớn đúng cách không phải “tăng multipart size”. Cần bound request ở **edge, Servlet, app và storage**, count bytes thực theo stream, tránh mảng toàn file, tách **temporary vs staging vs ready**, chỉ publish sau khi hoàn tất, giải phóng tài nguyên trong finally và có janitor cho crash/SIGKILL. File upload là dữ liệu không tin cậy: lưu private, validate/scanning, auth/tenant quotas, idempotency, retention và load/chaos tests trước production.