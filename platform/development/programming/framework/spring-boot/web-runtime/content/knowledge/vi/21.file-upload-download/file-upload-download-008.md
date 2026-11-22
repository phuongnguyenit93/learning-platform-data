# Dọn tệp tạm và giải phóng tài nguyên khi yêu cầu lỗi hoặc bị hủy

## 1. Vấn đề: file upload/download có nhiều loại tài nguyên khác nhau

Trong ứng dụng **Spring Boot web-runtime**, upload hay download không chỉ là truyền byte. Framework có thể lưu một phần multipart request trong RAM hoặc file tạm; ứng dụng có thể tạo file `.part` để nhận dữ liệu, giữ `InputStream`, file channel hoặc `DataBuffer`; client lại có thể đóng kết nối trước khi xử lý xong.

Một request thất bại có thể để lại:
- File đang ghi dở (partial upload) nhưng được người khác nhìn thấy như file hoàn chỉnh.
- File tạm chiếm đĩa dù request đã lỗi, hết hạn hoặc client bỏ đi.
- `InputStream`, `OutputStream`, file channel, file descriptor, connection hoặc pooled buffer chưa giải phóng.
- Một tác vụ nền tiếp tục ghi sau khi subscriber HTTP đã hủy.
- Một file cuối cùng đã được publish nhưng client không nhận được response, gây khó phân biệt upload thành công hay thất bại.

Vì vậy cần xử lý **hai lớp vòng đời**:

1. **Tài nguyên do framework/container sở hữu:** ví dụ multipart parsing và spool files do Servlet container hoặc WebFlux multipart reader tạo. Chúng có lifecycle riêng; phải dùng version được vá và API đúng contract.
2. **Tài nguyên do ứng dụng tạo:** ví dụ `Files.createTempFile`, stream đọc tệp, file scan, giải nén, file staging trước khi commit. Ứng dụng chịu trách nhiệm dọn chúng ở mọi đường kết thúc, kể cả ngoại lệ và cancellation.

**Nguyên tắc:** không bao giờ coi việc HTTP request kết thúc là bằng chứng rằng *mọi* file của ứng dụng đã được xóa. Phải rõ **ai tạo, ai sở hữu, khi nào publish, và ai cleanup**.

## 2. Phân biệt complete, error, cancel và crash

| Kết cục | MVC / Servlet | WebFlux / Reactor | Việc cần bảo đảm |
|---|---|---|---|
| Xử lý thành công | Method hoàn tất, response được ghi | Publisher hoàn tất (`onComplete`) | Đóng stream/channel; staging đã move hoặc xóa |
| Lỗi khi đọc/ghi | `IOException`, validation/security/storage exception | Publisher phát `onError` | Không publish file thiếu dữ liệu; xóa staging; giữ lỗi gốc |
| Client dừng giữa chừng | Có thể gặp lỗi đọc/ghi socket; sync handler có thể đã hoặc vẫn đang chạy | Framework/transport có thể cancel subscription khi phát hiện disconnect | Cleanup resource thuộc request; không tự giả định công việc ngoài đã dừng |
| Timeout | Container/Servlet async timeout hay business timeout riêng | `Mono.timeout`, network timeout, reactive timeout | Dừng tác vụ phù hợp, cleanup; không mặc định đã rollback side effect |
| Tiến trình bị kill / mất điện | `finally` không chạy | `usingWhen` cũng không chạy nếu JVM chết | Phải có chính sách quét file tạm cũ/quota/reconciliation |

**Cancel không đồng nghĩa error.** Trong Reactor, subscriber gọi `Subscription.cancel()`; upstream có thể được thông báo ngừng phát dữ liệu, nhưng không hứa việc ghi file hoặc gọi SDK blocking sẽ bị cắt ngay. `doOnError` không chạy cho mọi cancel; `doFinally` có thể quan sát `CANCEL` ở vị trí hook. Với MVC đồng bộ, không có tín hiệu Reactor cancel cho handler mặc định; try-with-resources và phát hiện `IOException` là chỗ cleanup căn bản.

Các lỗi mạng xảy ra **sau khi file đã commit** không tự đảo ngược thay đổi file. Nếu client gửi lại vì không nhận được câu trả lời, nghiệp vụ cần idempotency key, object ID, trạng thái xử lý hoặc quy trình đối soát.

## 3. Quy trình lưu file an toàn với staging và commit

Một cách thiết kế đơn giản là **chỉ công bố tên file cuối sau khi ghi thành công**:

```text
HTTP multipart upload
        │
        ├── Parse multipart (framework có thể tự spool ra temp)
        ▼
Kiểm tra metadata + giới hạn size/type
        │
        ▼
Tạo file staging riêng dưới thư mục do ứng dụng quản lý
  .incoming-<random>.part
        │
        ▼
Ghi dữ liệu vào staging
        │
        ├── Lỗi / hủy / timeout ──► dừng ghi khi có thể
        │                            └── đóng stream/channel
        │                                 └── xóa .part
        │
        ▼
Kiểm tra dung lượng, checksum, nội dung theo yêu cầu
        │
        ▼
Move/rename staging thành file cuối trong cùng filesystem
        │
        ▼
Ghi nhận file ID rồi trả response
        │
        ▼
Cleanup staging path còn sót (nếu có)
```

**Một số quyết định thiết kế quan trọng:**

- Sinh **UUID/token server-side** cho tên file; `MultipartFile.getOriginalFilename()` và `FilePart.filename()` do client cung cấp, có thể chứa `../` hoặc nội dung không đáng tin. Không nối trực tiếp tên file client vào đường dẫn ghi.
- Để staging và file cuối **cùng filesystem** nếu muốn dùng `Files.move(..., ATOMIC_MOVE)`. Atomic move có thể không được hỗ trợ trên mọi hệ thống; nếu fallback sang move thường, phải hiểu atomicity không còn được bảo đảm tuyệt đối.
- Nếu một upload gồm nhiều file hoặc vừa ghi database vừa ghi file, một `Files.move` chỉ bảo đảm thao tác trên **một path** theo contract filesystem; nó không tự tạo transaction phân tán.
- Chỉ xem file là hoàn tất sau khi copy/transfer và các bước kiểm tra cần thiết hoàn tất. File đang nhận dở không nằm trong danh sách file cho phép download.
- Đối với file lớn, không gọi `MultipartFile.getBytes()` hoặc `DataBufferUtils.join(...)` không giới hạn rồi giữ cả file trong RAM.
- Đặt giới hạn số lượng upload đồng thời, dung lượng từng file, tổng request, quota disk, và thời gian lưu staging; nếu đĩa đầy phải trả lỗi phù hợp và cleanup.

Các ví dụ bên dưới sử dụng **Spring Boot 3.3.x + Java 17+** để minh họa API. Hai project MVC và WebFlux là **độc lập**; mỗi project tự tạo thư mục lưu `data/uploads` tại working directory của nó.

## 4. Spring MVC: file multipart do container quản lý và file staging do app quản lý

Với `spring-boot-starter-web`, Boot thường tự cấu hình Servlet multipart. Controller có thể nhận `@RequestParam("file") MultipartFile`. Nội dung một part có thể nằm trong memory hoặc temp storage của Servlet container; `MultipartFile` chỉ là giao diện truy cập, **không nên giữ reference để đọc sau khi request đã kết thúc**.

Một số properties liên quan:

```properties
spring.servlet.multipart.max-file-size=8MB
spring.servlet.multipart.max-request-size=10MB
spring.servlet.multipart.file-size-threshold=1MB
# Chỉ định vị trí *multipart staging của Servlet container* nếu cần:
# spring.servlet.multipart.location=/var/app/multipart-inbox
```

Đường dẫn của `spring.servlet.multipart.location` phải tồn tại/có quyền phù hợp trong deployment nếu bật. Nó **khác** thư mục `data/uploads` và các file `.part` do ví dụ tự tạo. Container/framework thực hiện cleanup tài nguyên multipart theo vòng đời request thông thường, nhưng đường xử lý async, bug hoặc bản framework cũ có thể ảnh hưởng; không nên xóa bừa mọi file ở thư mục temp của container.

Khi dùng `MultipartFile.transferTo(File)`, provider có thể move file temp, copy nó hoặc xử lý nội dung đang nằm trong RAM; API không hứa mọi lần đều là thao tác move atomic. Trong ví dụ, ta dùng `InputStream` và một staging file do chính ứng dụng sở hữu để quy trình ghi/xóa rõ ràng, test được.

## 5. Ví dụ A — Spring Boot MVC: try-with-resources dọn staging trên mọi lỗi

### 5.1. Cấu trúc và cấu hình

```text
mvc-file-cleanup/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/mvcfiles/MvcFilesApplication.java
    │   └── resources/application.properties
    └── test/java/com/example/mvcfiles/FileStoreTest.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

`src/main/resources/application.properties`:

```properties
server.port=8080
spring.servlet.multipart.max-file-size=8MB
spring.servlet.multipart.max-request-size=10MB
spring.servlet.multipart.file-size-threshold=1MB
```

### 5.2. Controller, storage và lifecycle

`src/main/java/com/example/mvcfiles/MvcFilesApplication.java`:

```java
package com.example.mvcfiles;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Map;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

@SpringBootApplication
public class MvcFilesApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcFilesApplication.class, args);
    }
}

@RestController
@RequestMapping("/files")
class FilesController {
    private final FileStore store;

    FilesController(FileStore store) {
        this.store = store;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<Map<String, String>> upload(
            @RequestParam("file") MultipartFile file) throws IOException {
        if (file.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Empty file is not accepted");
        }

        // FileStore sở hữu stream từ đây, sẽ đóng trong try-with-resources.
        String id = store.save(file.getInputStream());
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("id", id));
    }

    @GetMapping("/{id}")
    ResponseEntity<StreamingResponseBody> download(
            @PathVariable("id") String id) throws IOException {

        Path path = store.find(id);
        StreamingResponseBody responseBody = output -> {
            // Đóng input dù client ngắt kết nối khi đang ghi response.
            try (InputStream input = Files.newInputStream(path)) {
                input.transferTo(output);
            }
            // Không tự close output: servlet container sở hữu HTTP output.
        };

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"download.bin\"")
                .body(responseBody);
    }
}

@Service
class FileStore {
    private final Path root;

    FileStore() {
        this(Path.of("data", "uploads"));
    }

    // Constructor này phục vụ test bằng thư mục riêng.
    FileStore(Path root) {
        this.root = root.toAbsolutePath().normalize();
    }

    String save(InputStream supplied) throws IOException {
        Files.createDirectories(root);

        // Nếu có lỗi ở bất kỳ bước nào, try-with-resources
        // vẫn cố gắng đóng input rồi xóa staging.
        try (InputStream input = supplied;
             TempLease stage = new TempLease(
                     Files.createTempFile(root, ".incoming-", ".part"))) {

            Files.copy(input, stage.path(), StandardCopyOption.REPLACE_EXISTING);

            String id = UUID.randomUUID() + ".bin";
            Path published = root.resolve(id);

            try {
                Files.move(stage.path(), published,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException unsupported) {
                // Fallback này không đảm bảo tính atomic trên mọi FS.
                Files.move(stage.path(), published);
            }
            return id;
        }
    }

    Path find(String id) {
        // Không dùng tên file client làm đường dẫn truy cập tùy ý.
        if (!id.matches("[0-9a-fA-F-]{36}\\.bin")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Invalid file id");
        }
        Path path = root.resolve(id).normalize();
        if (!Files.isRegularFile(path)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "File not found");
        }
        return path;
    }

    private record TempLease(Path path) implements AutoCloseable {
        @Override
        public void close() throws IOException {
            Files.deleteIfExists(path);
        }
    }
}
```

**Vì sao code dọn được file tạm?**

- `Files.createTempFile(root, ".incoming-", ".part")` tạo path ngẫu nhiên do app kiểm soát, không liên quan tên file người dùng.
- `try (InputStream input = supplied; TempLease stage = ...)` đóng stream và gọi `stage.close()` khi hoàn tất **hoặc** khi ném ngoại lệ. Java try-with-resources cũng giữ các lỗi cleanup làm *suppressed exception* nếu trước đó đã có exception chính.
- Khi ghi thành công, move staging sang `UUID.bin`; cuối block, `Files.deleteIfExists(stage.path())` không còn file staging để xóa và an toàn khi gọi.
- Nếu `Files.copy` hoặc `Files.move` lỗi trước commit, `TempLease.close` xóa file `.part` đang dở. Lỗi xóa file cũng được báo, không bị nuốt im lặng.
- Endpoint download dùng `StreamingResponseBody` để tránh nạp cả file vào memory; `InputStream` được đóng cả khi `output.write`/`transferTo` ném `IOException` do client bỏ giữa chừng.
- Ở path download, file tồn tại khi chọn nhưng có thể bị xóa trước khi stream mở; khi đó async write có thể lỗi. Đây là race cần quản lý theo retention policy nếu file có thể bị dọn đồng thời.

Giới hạn ví dụ: sync upload có thể tiếp tục chạy cho tới khi phát hiện read error; khi client dừng sau khi dữ liệu đã được lưu hoàn chỉnh, file đã commit có thể vẫn tồn tại. Đây là lựa chọn hợp lệ cho nhiều API; để ngăn retry tạo bản trùng cần dùng idempotency key.

### 5.3. Chạy và kiểm tra HTTP

Với JDK 17+ và Gradle tương thích Spring Boot 3.3:

```bash
gradle bootRun
```

Nếu project có Gradle Wrapper, dùng `./gradlew bootRun` (Linux/macOS) hoặc `.\gradlew.bat bootRun` (Windows PowerShell).

Tạo file mẫu `sample.txt` chứa một dòng "hello" rồi upload:

```bash
curl -i -F "file=@sample.txt" http://localhost:8080/files
```

Kết quả dự kiến: HTTP **201 Created**, JSON có dạng:

```json
{"id":"<UUID-mới>.bin"}
```

Đây là **định dạng minh họa**, chuỗi `<UUID-mới>` không phải output cố định hay JSON thực tế có thể copy nguyên văn. ID được sinh ngẫu nhiên khi commit.

Dùng giá trị `id` thật vừa nhận để tải file:

```bash
curl -OJ "http://localhost:8080/files/<ID-thật>"
```

Với ví dụ, response có `Content-Type: application/octet-stream` và header `Content-Disposition: attachment; filename="download.bin"`. Cờ `-OJ` cho curl lưu file theo tên gợi ý từ server; cần thay placeholder bằng file ID thật.

**Không kiểm tra thành công chỉ bằng HTTP 201.** Xác nhận nội dung tải xuống đúng bytes, không có file `.incoming-*.part` còn sót sau khi xử lý xong và chỉ một file `UUID.bin` xuất hiện.

## 6. Kiểm thử lỗi giữa chừng để chứng minh cleanup MVC

Một test đáng giá là mô phỏng source stream đọc được vài byte rồi ném `IOException`, kiểm tra thư mục không còn file tạm hay file cuối.

`src/test/java/com/example/mvcfiles/FileStoreTest.java`:

```java
package com.example.mvcfiles;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class FileStoreTest {
    @TempDir
    Path temp;

    @Test
    void brokenInputDoesNotLeavePartialFile() throws IOException {
        Path root = temp.resolve("uploads");
        FileStore store = new FileStore(root);

        InputStream broken = new InputStream() {
            int reads;

            @Override
            public int read() throws IOException {
                if (++reads > 4) {
                    throw new IOException("simulated input failure");
                }
                return 'a';
            }
        };

        assertThrows(IOException.class, () -> store.save(broken));

        try (Stream<Path> items = Files.list(root)) {
            assertEquals(0L, items.count());
        }
    }
}
```

Chạy `gradle test`. Test không cần chạy server, không có mạng và xác minh **thật** nhánh lỗi đọc: staging bị xóa trước khi method kết thúc. Tên method/class/path phù hợp với ví dụ A. Trong production, còn phải test permission denied/disk full, lỗi commit, exception khi delete, và lỗi trả response sau commit.

## 7. Khi request MVC dùng xử lý bất đồng bộ

`try-with-resources` thích hợp khi toàn bộ resource nằm trong scope method/callback chạy thực tế. Với `StreamingResponseBody`, resource phải được mở và đóng **bên trong lambda streaming**, bởi controller method trả về trước khi stream chạy.

Với Servlet async/`DeferredResult`/`Callable` hoặc công việc do app tự tạo, controller có thể trả sớm trong khi task vẫn tiếp tục. Không tạo `Path temp` trong method rồi đóng nó ngay trong `finally` của method nếu task còn đang ghi: có thể xóa trước khi writer kết thúc.

Các hook cần cân nhắc theo cơ chế thực tế:
- Servlet async `AsyncListener.onTimeout` / `onError` / `onComplete` để quan sát vòng đời request async.
- `DeferredResult.onTimeout`, `DeferredResult.onError` và `onCompletion` để quản lý response async ở cấp MVC.
- `Future.cancel` / custom cancellation token nếu tác vụ của ứng dụng hỗ trợ hủy.
- Resource lease có owner và trạng thái rõ ràng, đóng đúng một lần sau khi task thực sự dừng.

**Callback HTTP hoàn tất không đồng nghĩa writer tùy biến đã ngừng.** Nếu có nền ghi file, trước tiên phối hợp dừng writer rồi mới delete staging; nếu task không hủy ngay, đánh dấu staging để tiến trình quét dọn lại sau. Tránh gọi delete đồng thời với thread vẫn đang ghi trên Windows/Linux vì kết quả phụ thuộc filesystem.

## 8. Spring WebFlux: FilePart, cancellation và tài nguyên bất đồng bộ

Với `spring-boot-starter-webflux`, controller thường nhận:

```java
@PostMapping(path = "/files", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<ResponseEntity<Receipt>> upload(
        @RequestPart("file") FilePart file) {
    return storage.save(file)
            .map(id -> ResponseEntity.status(HttpStatus.CREATED)
                    .body(new Receipt(id)));
}
```

Đây là method minh họa, cần các class/import/bean `storage` và `Receipt`; ví dụ đầy đủ ở mục 9. `org.springframework.http.codec.multipart.FilePart` có `transferTo(Path)` trả `Mono<Void>`: **chỉ khi Mono được subscribe mới thực hiện transfer**.

Dòng lifecycle:

```text
Multipart parser → FilePart
                       │
                       ▼
       Mono.usingWhen(acquire staging Path)
                       │
                       ▼
             file.transferTo(staging)
                       │
          ┌────────────┼────────────┐
          │            │            │
       complete      onError      cancel
          │            │            │
      commit file      │            │
          │            │            │
          └────────────┴────────────┘
                       │
          async cleanup staging path
                       │
                       ▼
              HTTP response / error
```

**Phải phân biệt hai loại temp:** reader multipart WebFlux có thể spool body thành file tạm riêng *trước* khi controller có `FilePart`; còn `Files.createTempFile` trong ví dụ tạo staging file do app quản lý. Cleanup của loại thứ hai do `usingWhen` của app thực hiện. Không khẳng định mọi thư viện/framework phiên bản cũ đều dọn spool files hoàn hảo trên mọi lỗi; cần kiểm tra security updates và disk metrics.

Nếu client đóng kết nối sau khi framework đã nhận đủ multipart body nhưng trước khi response ghi xong, backend có thể đã commit. Phải quyết định chính sách: đã commit thì trả cùng file ID khi retry có cùng idempotency key, hoặc có trạng thái "processing" để đối soát.

## 9. Ví dụ B — WebFlux: Mono.usingWhen dọn staging khi complete/error/cancel

### 9.1. Project độc lập

```text
webflux-file-cleanup/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactivefiles/ReactiveFilesApplication.java
    │   └── resources/application.properties
    └── test/java/com/example/reactivefiles/LeaseCleanupTest.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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

`src/main/resources/application.properties`:

```properties
server.port=8081
# Với WebFlux, multipart reader/codec có cấu hình riêng với Servlet.
# Không dùng spring.servlet.multipart.* để điều khiển reactive upload.
```

### 9.2. Code chạy được

`src/main/java/com/example/reactivefiles/ReactiveFilesApplication.java`:

```java
package com.example.reactivefiles;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.UUID;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveFilesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveFilesApplication.class, args);
    }
}

@RestController
@RequestMapping("/files")
class ReactiveFilesController {
    private final ReactiveFileStore store;

    ReactiveFilesController(ReactiveFileStore store) {
        this.store = store;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Mono<ResponseEntity<UploadReceipt>> upload(
            @RequestPart("file") FilePart file) {

        return store.save(file)
                .map(id -> ResponseEntity.status(HttpStatus.CREATED)
                        .body(new UploadReceipt(id)));
    }
}

record UploadReceipt(String id) {}

@Service
class ReactiveFileStore {
    private final Path root = Path.of("data", "uploads")
            .toAbsolutePath().normalize();

    Mono<String> save(FilePart file) {
        return Mono.usingWhen(
                Mono.fromCallable(() -> {
                    Files.createDirectories(root);
                    return Files.createTempFile(
                            root, ".incoming-", ".part");
                }).subscribeOn(Schedulers.boundedElastic()),

                staging -> file.transferTo(staging)
                        .then(Mono.fromCallable(() -> publish(staging))
                                .subscribeOn(Schedulers.boundedElastic())),

                this::deleteStaging,
                (staging, error) -> deleteStaging(staging),
                this::deleteStaging
        );
    }

    private String publish(Path staging) throws IOException {
        String id = UUID.randomUUID() + ".bin";
        Path finalPath = root.resolve(id);
        try {
            Files.move(staging, finalPath,
                    StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException unsupported) {
            Files.move(staging, finalPath);
        }
        return id;
    }

    private Mono<Void> deleteStaging(Path staging) {
        // java.nio.file.Files là blocking I/O: chuyển off event-loop.
        return Mono.fromRunnable(() -> {
            try {
                Files.deleteIfExists(staging);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        }).subscribeOn(Schedulers.boundedElastic()).then();
    }
}
```

**Cơ chế hoạt động:**

1. `Mono.fromCallable` chỉ tạo staging path **khi được subscribe**, trên `boundedElastic` vì `Files.createDirectories/createTempFile` là filesystem operations blocking.
2. `usingWhen` sở hữu một staging `Path` cho mỗi subscription. `file.transferTo(staging)` xử lý body theo API của WebFlux; mã ví dụ không tự `subscribe()`.
3. Chỉ sau khi `transferTo` phát complete, `publish` mới move staging thành `UUID.bin`; `publish` là thao tác filesystem blocking nên đặt trên `boundedElastic`.
4. `asyncComplete`, `asyncError` và `asyncCancel` đều gọi `deleteStaging`. Trong đường thành công, staging đã move nên delete là no-op; trong đường lỗi/cancel, cleanup cố xóa file đang dở.
5. `Mono.usingWhen` đợi publisher cleanup trước khi phát complete/giá trị cho downstream ở đường kết thúc bình thường. **Lỗi trong cleanup có thể đổi tín hiệu cuối thành error**, vì vậy cần log/metrics và xử lý lỗi cleanup có chủ đích.
6. Nếu cancel xảy ra sát thời điểm một thao tác filesystem đang chạy, không thể bảo đảm `Files.move`/write blocking bị interrupt tức thời. Tại ranh giới commit có thể xảy ra race; cần thiết kế idempotency và tiến trình dọn orphan staging, đặc biệt khi có writer của bên thứ ba.

**Thận trọng:** Bản demo giải phóng file staging bằng reactive resource scope và tách blocking filesystem calls khỏi event-loop. Nó không tạo ra transaction giữa file storage và network response, và không bảo đảm mọi tình huống crash/cancellation cấp OS đều xóa kịp. Production phải chọn cơ chế upload có cancellation contract phù hợp với driver/filesystem và giám sát những file quá hạn.

### 9.3. Chạy và quan sát

```bash
gradle bootRun
```

Trong thư mục project, dùng JDK 17+ và Gradle tương thích Boot 3.3; Gradle Wrapper nếu có: `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên Windows PowerShell.

```bash
curl -i -F "file=@sample.txt" http://localhost:8081/files
```

Kết quả dự kiến là **HTTP 201** với JSON chứa `id` ngẫu nhiên, ví dụ cấu trúc:

```json
{"id":"<UUID-mới>.bin"}
```

Đây là minh họa định dạng, không phải ID thực. Sau upload hoàn tất, kiểm tra `data/uploads`: phải có file `UUID.bin` và không còn `.incoming-*.part` của request đó.

Thử hủy giữa chừng khi upload file lớn có thể dùng curl giới hạn tốc độ và dừng tiến trình, nhưng **không có bảo đảm** method controller đã bắt đầu xử lý. Multipart parser có thể chưa tạo `FilePart`/chưa chuyển quyền cho app; khi ấy không có staging app để xóa và cần quan sát riêng multipart temp của framework. Kiểm tra cancellation cần test có thể điều khiển timing theo mục kế tiếp.

## 10. Test cancellation của reactive resource scope

Dùng `StepVerifier` để chủ động cancel một publisher không bao giờ hoàn tất và chờ callback cleanup. Test này kiểm tra **hợp đồng `usingWhen`**, không giả vờ kiểm thử đầy đủ filesystem hay HTTP client disconnect.

`src/test/java/com/example/reactivefiles/LeaseCleanupTest.java`:

```java
package com.example.reactivefiles;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

class LeaseCleanupTest {

    @Test
    void cancellationTriggersAsyncCleanup() throws InterruptedException {
        CountDownLatch cleaned = new CountDownLatch(1);

        Mono<String> pipeline = Mono.usingWhen(
                Mono.just("lease"),
                lease -> Mono.<String>never(),
                lease -> Mono.empty(),
                (lease, failure) -> Mono.empty(),
                lease -> Mono.fromRunnable(cleaned::countDown)
        );

        StepVerifier.create(pipeline)
                .expectSubscription()
                .thenCancel()
                .verify();

        assertTrue(cleaned.await(2, TimeUnit.SECONDS));
    }
}
```

Chạy `gradle test`. Test pass khi callback nhánh `asyncCancel` được thực thi, thể hiện bằng latch trở về 0 trong vòng hai giây. **Đây không phải test tạo file thật**; để kiểm chứng hoàn chỉnh upload, nên có integration test với file lớn, một implementation `FilePart` kiểm soát được hành vi transfer lỗi/cancel, assert staging không còn, cùng test thật ở môi trường container/OS.

Với file thật, hãy kiểm tra cả nhánh đọc dữ liệu thành công, lỗi disk full, lỗi permission, việc cleanup thất bại và race giữa cancel/commit. Đối với test async cleanup, đừng chỉ kiểm tra HTTP status; cần assert số file còn sót, file handle, pool usage và log lỗi.

## 11. Buffer và low-level multipart stream: tránh memory leak

Trong WebFlux, `FilePart.transferTo(Path)` là API cấp cao thuận tiện. Khi tự làm việc với `Part.content()` hoặc `Flux<PartEvent>`, dữ liệu được phát dưới dạng `DataBuffer`, một số buffer có thể được pool và **reference-counted**.

Nguyên tắc ownership:

- Nếu app **tự lấy và tiêu thụ trực tiếp** `DataBuffer`, phải làm đúng contract release sau khi dùng hoặc khi bị discard/cancel.
- `DataBufferUtils.release(buffer)` giải phóng buffer nếu nó thuộc loại cần release, nhưng không nên gọi khi framework/codec đã nhận ownership và sẽ release giúp.
- `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` dùng khi các operator ở phía trên có hỗ trợ discard đối với buffer đã giữ/prefetch; đặt đúng vị trí và tránh double release.
- `DataBufferUtils.write(source, OutputStream/Channel)` dạng trả `Flux<DataBuffer>` **không tự đóng stream/channel và không tự release tất cả buffer cho caller**; phải xử lý lifecycle nguồn và các buffer theo API. Đừng nhầm nó với overload ghi ra `Path` trả `Mono<Void>` có contract riêng.
- Với streaming multipart `Flux<PartEvent>`, mỗi phần dữ liệu phải được **tiêu thụ, chuyển tiếp hoặc release**. Bỏ qua event/buffer mà không cleanup có thể làm rò rỉ pooled memory.

Nếu chỉ cần lưu một `FilePart` nhận qua multipart và không có yêu cầu can thiệp từng chunk, ưu tiên `transferTo` để tránh tự quản lý `DataBuffer` ở tầng thấp.

Giao diện `Part` của WebFlux còn có `delete(): Mono<Void>` để yêu cầu xóa underlying storage của part theo implementation. Đây là **API về tài nguyên của part**, khác file staging do app tạo. Không tự gọi `delete` đồng thời với `transferTo` đang chạy hoặc tự xóa path nội bộ của parser; phải thực hiện trong chuỗi Publisher đúng contract. Framework có cơ chế cleanup của nó nhưng bản framework có bug hoặc đường request bất thường vẫn cần được vá.

## 12. Tải file từ server và đóng tài nguyên khi client bỏ kết nối

Ở **MVC**, `StreamingResponseBody` mở `InputStream` bên trong callback và try-with-resources như ví dụ A. Việc `OutputStream.write` ném `IOException` do client ngắt kết nối sẽ thoát callback và đóng input. Không tự đóng servlet response stream do container sở hữu.

Ở **WebFlux**, có thể trả `Resource` hoặc `Mono<Resource>` cho file trong một endpoint; các response writers của framework có cơ chế quản lý việc đọc/ghi body, resource lifecycle tương ứng. Ví dụ về ý tưởng:

```java
@GetMapping(path = "/download", produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
Mono<ResponseEntity<Resource>> download() {
    return Mono.fromCallable(() -> {
        Path file = findExistingFile(); // API minh họa của ứng dụng.
        return ResponseEntity.ok().body(new FileSystemResource(file));
    }).subscribeOn(Schedulers.boundedElastic());
}
```

Đoạn này **không phải class độc lập**; cần import `Resource`, `FileSystemResource`, `ResponseEntity`, `Mono`, `Schedulers` và phương thức `findExistingFile()`. Nếu muốn tự tạo `Flux<DataBuffer>` từ `DataBufferUtils.read(...)`, phải đảm bảo publisher đọc file được liên kết với response writer và không tự `subscribe()`, đồng thời hiểu callback release buffer của codec/framework.

Với file tạm được tạo **riêng cho một lượt download** (ví dụ ZIP/export động), không xóa file ngay khi controller trả một `Resource`: HTTP encoder vẫn có thể chưa đọc. Cần giữ resource lease tới khi writer kết thúc hoặc cancel, rồi cleanup. Với Reactor, có thể dùng `Flux.usingWhen`/`Mono.usingWhen` và để response write nằm **bên trong resource closure**; trả `ResponseEntity<Resource>` đơn thuần có thể tách thời điểm Spring đọc resource khỏi thời điểm callback hoàn tất. Đối với MVC async, cleanup trong `StreamingResponseBody` hoặc callback kết thúc thực của tác vụ. Khi cần download tạm trong production, chọn API streaming/file provider có lifecycle rõ ràng.

## 13. Error handling, cleanup failure và idempotency

Không phải mọi lỗi upload đều có thể ánh xạ thành cùng status:

| Tình huống | Cách xử lý | HTTP điển hình |
|---|---|---|
| File quá lớn / request multipart quá lớn | Từ chối sớm, giới hạn size và cleanup theo framework | 413 Payload Too Large nếu được ánh xạ/cấu hình |
| Thiếu part hoặc metadata không hợp lệ | Validate request; không mở staging vô ích | 400 |
| Storage đầy / permission denied | Hủy ghi, xóa file partial nếu có, ghi log lỗi storage | 5xx, thường 500 hoặc 507 theo chính sách |
| Virus scan hoặc content validation không đạt | Không publish, cleanup staging | 400/422 tùy hợp đồng |
| Client dừng khi upload | Dừng task được nếu có thể, cleanup | Client có thể không nhận bất kỳ response nào |
| Fail khi xóa staging | Ghi lỗi cleanup, cho job đối soát xử lý lại | Có thể 5xx; nếu đã cancel thì không còn client nhận lỗi |
| Commit đã xong nhưng mất response | Không tự coi là file chưa tồn tại | Retry phải idempotent hoặc trả trạng thái theo ID |

**Lỗi cleanup phải quan sát được:** metric `temp_cleanup_failures`, log chỉ lưu ID/request correlation, tránh log nguyên thông tin cá nhân/byte nội dung. Với Java `try-with-resources`, exception trong `close` được gắn suppressed vào exception chính; với Reactor `usingWhen`, cleanup error có thể thay đổi tín hiệu xuống dưới. Đừng dùng `onErrorResume(e -> Mono.empty())` vô điều kiện trên cleanup chỉ để "cho qua" vì sẽ che dấu rò rỉ tài nguyên.

**Side effect không tự rollback:** một file đã move thành công trước khi client bỏ kết nối có thể vẫn tồn tại. Mọi ứng dụng yêu cầu semantics exactly-once cần ID do server sinh, idempotency key, check trùng hoặc metadata transaction có chủ đích. Atomic move chỉ tránh publish file đang ghi dở trong phạm vi filesystem; nó không là transaction HTTP, DB hay object storage.

## 14. Tự dọn file orphan khi tiến trình chết

Không có `finally`, `doFinally` hay `usingWhen` nào bảo đảm chạy khi JVM bị `kill -9`, máy mất điện hoặc container bị xóa đột ngột. Để tránh đầy đĩa, production cần **reaper/sweeper**:

1. Chỉ quét trong **thư mục staging do ứng dụng sở hữu**; không duyệt/xóa bừa `java.io.tmpdir` hay thư mục do container/framework quản lý.
2. Chỉ xét file có pattern riêng như `.incoming-*.part` và nằm trong root đã xác định (không đi theo symlink đến vị trí tùy ý).
3. Chọn ngưỡng tuổi lớn hơn thời gian upload tối đa hợp lệ; so sánh timestamp + trạng thái phiên upload/lease nếu có.
4. Phân biệt file **đang được ghi** với file orphan: nhiều instance có thể dùng cùng storage; cần owner/heartbeat/lease hoặc storage isolation để tránh xóa nhầm.
5. Dùng retry bounded và backoff cho lỗi tạm thời; ghi metrics số lượng, dung lượng, tuổi staging và lỗi delete.
6. Có quota/alert về disk usage và cleanup riêng cho staging; tránh để upload độc hại làm cạn filesystem.

Ví dụ code **minh họa** cho chương trình một instance, trước khi xây dựng reaper thật:

```java
try (Stream<Path> paths = Files.list(stagingDirectory)) {
    paths.filter(path -> {
        String name = path.getFileName().toString();
        return name.startsWith(".incoming-") && name.endsWith(".part");
    }).filter(path -> Files.isRegularFile(path))
      .filter(path -> isExpired(path)) // Phải triển khai theo lease/tuổi.
      .forEach(path -> safeDelete(path)); // Phải log/retry đúng policy.
}
```

Đoạn trên **không chạy độc lập**; `stagingDirectory`, `isExpired` và `safeDelete` là API phải định nghĩa. Nếu không có cơ chế chắc chắn biết file không còn active, đừng chạy job này một cách phá hoại trên staging dùng chung.

## 15. Theo dõi lỗi thực tế và giới hạn bảo mật

Các chỉ số hữu ích:
- `upload_staging_files` và `upload_staging_bytes`: số lượng/dung lượng staging đang tồn tại.
- `upload_cleanup_errors_total`, `upload_cancel_total`: lần cleanup thất bại và cancel (phân biệt timeout vs disconnect nếu quan sát được).
- `upload_commit_success_total`, `upload_commit_failures_total`.
- Số file orphan lớn hơn TTL; disk free/inode free; số file descriptor và pooled direct memory; 4xx/5xx liên quan multipart.

Bảo vệ upload: giới hạn dung lượng/part count, content type chỉ là gợi ý (không tin tuyệt đối), kiểm tra định dạng thật nếu cần, chống path traversal và symbolic link traversal, kiểm tra malware nếu threat model yêu cầu, không phục vụ file người dùng từ đường dẫn có thể thực thi script. Với ZIP/extraction, chống zip-slip và zip bomb, giới hạn tổng số file và tổng byte sau giải nén; các phần dữ liệu trích xuất cũng phải theo staging và cleanup.

**Lưu ý version & bản vá:** Spring công bố **CVE-2026-22740** (17/04/2026) về các file temp multipart WebFlux có thể còn sót trong một số trường hợp. Advisory liệt kê các nhánh Spring Framework bị ảnh hưởng, có phiên bản sửa cụ thể (ví dụ 6.2.18 và 7.0.7 cho nhánh tương ứng; 6.1.27 thuộc kênh thương mại). Vì thế **đừng mặc định chỉ dùng WebFlux là hệ thống tự hết rò rỉ**; xác minh framework version thật của deployment, trạng thái hỗ trợ/cập nhật bản vá và hành vi temp multipart. Ví dụ Spring Boot 3.3.x ở trên dùng để học API 6.1, không phải cam kết mọi dependency cũ đều còn nhận bản vá bảo mật.

## 16. Lỗi hay gặp

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Có file `.part` sau upload lỗi | Cleanup chỉ chạy khi success; writer có thể còn active | Dùng try-with-resources / usingWhen, test error/cancel, theo dõi lease |
| Xóa file trước khi download xong | Cleanup ở lúc controller trả view/ResponseEntity, không đợi writer | Đặt cleanup ở callback stream/writer lifecycle |
| `onErrorResume` không bắt được cancel | Cancel không phải `onError` | Dùng cleanup scope và `doFinally` để quan sát `CANCEL` |
| Temp parser tăng dù app đã xóa staging | Framework có multipart spool riêng | Kiểm tra version, multipart settings, advisory và thư mục spool |
| Netty direct memory tăng | Pooled `DataBuffer` không release/discard | Audit owner, `DataBufferUtils.release`, `doOnDiscard`, leak detection |
| Disk đầy dù không còn request | Process crash; orphan staging không được quét | Job reaper + TTL + quota + cảnh báo |
| Client hủy nhưng server vẫn ghi | Blocking I/O/external driver không cancellable; cancel đến muộn | Kiểm tra thread và transfer lifecycle, cleanup sau writer stop |
| Cùng file bị tạo hai lần | Client retry sau mất response dù commit đã xong | Idempotency key/metadata để đối soát |
| File có tên `../../...` | Đã tin client filename | Dùng ID server-generated, kiểm tra root/normalization |
| IOException khi xóa staging | Permission/lock, race hoặc filesystem issue | Ghi lỗi cleanup, retry an toàn và job reconciliation |

## 17. Tự kiểm tra kiến thức

**Câu 1:** Vì sao không thể chỉ gọi `Files.deleteIfExists` trong `catch(IOException)`?  
**Đáp án:** Cleanup còn phải chạy khi complete, lỗi khác loại, cancel và khi stream đóng; chọn try-with-resources (MVC) hoặc `usingWhen` (WebFlux). Crash cần reaper riêng.

**Câu 2:** File temp của Servlet/WebFlux parser và file `.incoming-...part` do app tạo có cùng owner?  
**Đáp án:** Không. Parser/framework quản lý storage của nó; app phải cleanup staging riêng. Không xóa indiscriminately thư mục temp dùng chung.

**Câu 3:** Vì sao không trả HTTP 504 như response cố định sau khi client disconnect?  
**Đáp án:** Client đã đóng kết nối, có thể không nhận response; nếu headers/body đã committed cũng không thể tùy ý đổi status.

**Câu 4:** Tại sao `FilePart.transferTo(Path)` không đủ để bảo đảm file đã commit và không còn orphan?  
**Đáp án:** Nó chỉ báo hoàn tất transfer theo contract của part; ứng dụng vẫn phải validate/commit, cleanup staging khi lỗi/cancel, quản lý race và crash.

**Câu 5:** Khi nào `DataBufferUtils.release` cần và khi nào không?  
**Đáp án:** Khi ứng dụng sở hữu pooled buffer phải dispose theo contract. Nếu WebFlux/framework encoder/decoder hoặc helper đã nhận ownership và tự release, gọi lại có thể thành double release.

**Câu 6:** Nếu upload đã move staging thành file cuối và sau đó response bị mất, có nên xóa file không?  
**Đáp án:** Phụ thuộc hợp đồng nghiệp vụ và idempotency; không coi mất response đồng nghĩa commit chưa xảy ra.

## 18. Tài liệu chính thức

- Spring Framework — Multipart Resolver ở MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html
- Spring Boot 3.3 — Common Application Properties, các property `spring.servlet.multipart.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Framework 6.1 — `MultipartFile`, storage tạm và `transferTo`: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/web/multipart/MultipartFile.html
- Spring Framework — WebFlux Multipart Content, `FilePart` / `PartEvent`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework 6.1 — `FilePart` và `Part.delete` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/codec/multipart/FilePart.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework 6.1 — `DataBufferUtils` overloads: https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
- Reactor — `Mono.usingWhen` cleanup complete/error/cancel: https://projectreactor.io/docs/core/3.6.17/api/reactor/core/publisher/Mono.html
- Spring Security Advisory CVE-2026-22740, temp files trong WebFlux multipart: https://spring.io/security/cve-2026-22740

**Ghi nhớ:** muốn xử lý file an toàn phải xác định **ownership**, ghi qua **staging**, chỉ **commit khi đã hoàn tất**, và cleanup trên **success/error/cancel**. `finally`/`usingWhen` xử lý vòng đời trong tiến trình; **job dọn orphan** và việc dùng dependency đã vá bảo vệ cả các tình huống crash hoặc lỗi của multipart parser.