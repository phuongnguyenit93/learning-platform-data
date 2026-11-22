# Object storage hoặc hệ thống tệp ngoài được thay thế ở đúng ranh giới

Trong nhóm **Tích hợp bổ sung** của module **Spring Boot - testing**, một chức năng upload/download có thể lưu nội dung vào Amazon S3, một API object storage tương thích S3, Azure Blob Storage, Google Cloud Storage, hoặc một thư mục trên ổ đĩa/NFS/SMB mount. Nếu unit test phải đăng nhập cloud, tìm một bucket đã tạo trước, hoặc ghi vào thư mục chia sẻ của môi trường thật, **ranh giới kiểm thử đang đặt sai**. Ngược lại, nếu mọi test chỉ mock method `S3Client.putObject(...)` mà không bao giờ thử cấu hình bucket, key, region, credentials, streaming và response code, **tích hợp thật chưa được kiểm chứng**.

Bài học trình bày một kiến trúc dễ thay thế và một chiến lược kiểm thử nhiều tầng:

- **Business layer:** phụ thuộc interface `BlobStore` (port) thay vì AWS SDK hoặc `java.nio.file.Files`. Unit test dùng Mockito hoặc một in-memory fake; **không cần mạng/ổ đĩa**.
- **HTTP layer:** dùng `MockMvc` kiểm tra upload/download, status/header/body, mock đúng `AssetService` nếu chỉ test controller.
- **Application flow:** chạy controller + service thật trong Spring Boot, nhưng thay **duy nhất external boundary `BlobStore`** bằng test bean in-memory. Đây là test tích hợp wiring bên trong, **không giả vờ đã test S3**.
- **Filesystem adapter:** dùng JUnit `@TempDir` và I/O filesystem thật, không đụng thư mục/volume sản xuất.
- **Object storage adapter:** dùng `LocalStackContainer` với S3Client thật để kiểm tra `PutObject/GetObject`, endpoint override, bucket/key và binary round-trip. Đây là integration/contract test với môi trường mô phỏng S3, **không tương đương IAM, latency, quota hay mọi hành vi AWS S3 production**.
- **Kiểm thử trong môi trường đích:** khi cần NFS/SMB permission, network timeout, IAM, encryption, versioning hoặc pre-signed URL, dùng một môi trường staging/ephemeral có quyền truy cập phù hợp và xác định lại contract cần chứng minh.

Ví dụ dùng **Java 17+, Spring Boot 3.5.x, JUnit Jupiter, MockMvc, Mockito, AWS SDK for Java v2 và Testcontainers 1.x**. Phần Java SE nhỏ có lệnh `javac/java` và stdout xác định. Các lớp mẫu có quy ước tối giản: object key là ID ngẫu nhiên, nội dung tối đa 1 MiB và download trả `application/octet-stream`. Những giới hạn này giúp thấy ranh giới, **không phải thiết kế đầy đủ cho sản phẩm lưu trữ tệp lớn**.

## 1. “Thay đúng ranh giới” là thay cái gì?

Ứng dụng thường có luồng:

```text
HTTP POST /assets                  HTTP GET /assets/{key}
          |                                    |
          v                                    v
     AssetController                    AssetController
          |                                    |
          v                                    v
       AssetService  <--- business rules ---> AssetService
          |                                    |
          +------------ BlobStore -------------+
                             |
                    Implementation adapter
                  /                     \
                 v                       v
       DiskBlobStore                S3BlobStore
      java.nio.file.*                AWS S3Client
                 |                       |
                 v                       v
         Local/NFS/SMB                  S3 API
            filesystem               (AWS/LocalStack)
```

**Port (interface)** biểu diễn nhu cầu của ứng dụng bằng ngôn ngữ nghiệp vụ: lưu object theo key và đọc lại bytes. Adapter biến nhu cầu ấy thành calls vào Files hoặc S3 SDK. Dependency direction đi từ application service tới **port**, không từ service trực tiếp tới AWS package.

Với kiến trúc này:

1. Service unit test có thể kiểm tra validation, key generation và delegation bằng một mock `BlobStore`.
2. Disk adapter test kiểm tra `Files.move`, file nội dung, missing file và traversal protection với thư mục tạm.
3. S3 adapter test kiểm tra sự tương tác AWS SDK thật với một S3-compatible service trong container.
4. HTTP test kiểm tra status/body/headers mà không cần bucket hay credentials.
5. Application wiring test chạy qua HTTP tới service thật nhưng thay port bằng một fake; nó kiểm tra nơi **đặt seam** trong Spring context.

**Không nên** để `AssetService` gọi trực tiếp `S3Client`, tự tính `Path.resolve(...)` hoặc đọc environment variable `AWS_ACCESS_KEY_ID`. Làm vậy trộn business policy với hạ tầng, khiến test khó tách lỗi và dễ kết nối nhầm môi trường.

## 2. So sánh các lớp test

| Lớp test | Thay thế | Thứ được kiểm tra | Chưa kiểm tra |
| --- | --- | --- | --- |
| Service unit | Mock `BlobStore` | Rule, key, bytes, exception propagation | Disk/S3 protocol |
| Controller slice | Mock `AssetService` | Route, multipart binding, HTTP response/advice | Service rule và adapter |
| Spring flow | Fake `BlobStore` | Controller + service + DI/wiring thật | I/O hệ thống tệp hoặc S3 |
| Filesystem integration | Thư mục `@TempDir` **thật** | Filename/key, bytes, atomic replacement fallback, missing file | NFS/SMB/permissions production |
| S3 integration | S3 API trong LocalStack | SDK, bucket/key, PUT/GET, network, auth thử nghiệm | IAM AWS thực, bucket policy/KMS, latency cloud |
| Environment contract | Storage staging/ephemeral | Quyền, region, TLS, encryption/presigned URL/quota cần thiết | Các tình huống không được tạo trong test |

**Hai sai lệch dễ gặp:**

- Mock chính `AssetService` trong **service unit test** thì bạn không test business logic; cần real service + mock port.
- Dùng `@TempDir` để chứng minh “S3 hoạt động” thì sai: nó chỉ kiểm tra adapter filesystem. Muốn bảo vệ integration S3 phải có test chạy qua S3 API thật hoặc S3-compatible test server.

Cấp nào được chọn tùy hợp đồng. Không nhất thiết mỗi PR chạy AWS staging test; phần lớn logic kiểm tra nhanh bằng unit/adapter tests, còn CI integration job kiểm tra giao thức và wiring.

## 3. Object storage không phải filesystem có thư mục thực

S3-style object storage tổ chức object theo **bucket + key**, không có cây thư mục/rename/locking semantics giống `java.nio.file.Path`:

| Khái niệm | Filesystem | S3-style object store |
| --- | --- | --- |
| Địa chỉ | Root directory + file path | Bucket + object key |
| Ghi | File write/rename, filesystem semantics | HTTP PUT object/API |
| Đọc | File read/open stream | GET Object hoặc signed URL |
| Tên thư mục | Directory có thật | Prefix trong key, folder thường là quy ước |
| Rename | Có thao tác move/rename; atomic tùy FS | Thường copy + delete, không giống atomic rename |
| Overwrite | Phụ thuộc move/write flags/OS | PUT cùng key có thể thay object (versioning tùy bucket) |
| Liệt kê | Directory traversal | LIST objects, có pagination/permissions |
| Quyền | OS account/ACL/volume | IAM/bucket policies/credentials/KMS |
| Xóa | Delete file | Delete Object, version markers nếu versioning |
| Transaction chung với DB | Không tự có | Không tự có |

**Đừng mặc định “S3 eventual consistency nên phải sleep”**. Amazon S3 hiện cung cấp strong read-after-write consistency cho PUT/DELETE và LIST trong các điều kiện được tài liệu hóa; tuy nhiên các storage tương thích S3/NFS gateway/provider khác nhau có thể có semantics khác. Quan trọng là test **đúng provider và contract**, không gán hành vi cố định cho mọi object store.

Trong bài, port chỉ có `put(key, bytes)` và `get(key)`. Nó không cố giả làm một `java.nio.file.FileSystem` ảo đầy đủ. Những tính năng như pre-signed URL, multipart upload, streaming lớn, object tagging, ETag, retention và versioning cần **port/contract riêng**, không thêm tuỳ tiện vào một fake chỉ để test pass.

## 4. Định nghĩa hợp đồng BlobStore rõ ràng

Một port tốt cần nói rõ:

- Key do **application tạo**; không dùng tên file người dùng làm path/key trực tiếp.
- Đầu vào và đầu ra là bytes; dữ liệu có thể chứa Unicode trong UTF-8 hoặc binary tùy ý.
- `get(key)` trả `Optional.empty()` **chỉ khi object thật sự không tồn tại**.
- Permission denied, timeout, disk-full, lỗi DNS, bucket không tồn tại phải được báo là **failure**, không biến thành `Optional.empty()`.
- Storage không tự validate business policy cho size/MIME/tenant; service kiểm tra policy, adapter bảo vệ path/protocol.
- `put` khi cùng key sẽ thay nội dung ở cả hai adapters của ví dụ; đây là **overwrite contract**. Trong hệ cần immutable objects, thay đổi port để từ chối overwrite hoặc dùng conditional writes.
- Không tự hứa atomic transaction chung với database hoặc thread-safe consistency across clients; phải xác định riêng.
- Buffer memory giới hạn: demo dùng 1 MiB, dữ liệu lớn nên dùng streaming/backpressure/multipart phù hợp.

### File: BlobStore.java

Tạo `src/main/java/example/storage/BlobStore.java`:

```java
package example.storage;

import java.io.IOException;
import java.util.Optional;

public interface BlobStore {
    void put(String key, byte[] bytes) throws IOException;

    Optional<byte[]> get(String key) throws IOException;
}
```

**Tại sao interface dùng `IOException`?** Disk I/O có checked exception. S3 adapter sẽ **wrap SDK runtime failures thành IOException** để application xử lý storage unavailable nhất quán. Đây là lựa chọn minh họa; trong production có thể dùng exception riêng `StorageUnavailableException` (unchecked) phân biệt retryable, not-found, conflict, auth và provider error.

Đừng lộ `S3Exception`, `Path`, `ResponseInputStream` trong service API nếu muốn hoán đổi adapters. Khi contract đòi hỏi metadata/streaming, hãy định nghĩa typed input/output đúng ngay ở port thay vì ép mọi thứ thành bytes vô hạn.

## 5. Key validation nằm ở cổng bảo vệ I/O

Key được tạo ngẫu nhiên trong service, nhưng adapter vẫn có thể được gọi trực tiếp từ nơi khác; vì thế **cả service và adapter đều validate key**.

Tạo `src/main/java/example/storage/ObjectKeys.java`:

```java
package example.storage;

public final class ObjectKeys {
    private ObjectKeys() {
    }

    public static void requireValid(String key) {
        if (key == null
                || !key.matches("[a-z0-9-]{1,80}")) {
            throw new IllegalArgumentException(
                    "invalid object key");
        }
    }
}
```

Quy ước demo **cố ý không cho dấu chấm, dấu gạch chéo hoặc backslash**. Key kiểu UUID lowercase/hyphen hợp lệ; `../etc/passwd`, `a/b` hoặc `C:\\secret` bị từ chối. Nhờ không có path separator, filesystem adapter không phải giải quyết nested directories hoặc path traversal qua user filename.

**Điều này chỉ bảo vệ một phần:** nếu filesystem root là thư mục chia sẻ cho attacker thay symlink/hardlink hoặc đổi mount giữa lúc kiểm tra/đọc, key regex không tự bảo vệ chống race/symlink attacks. Storage root của app phải là thư mục **riêng, được quản lý quyền**, không cho user không tin cậy tạo/sửa entry. Với hệ thống file do attacker cùng quyền ghi, cần sandbox/secure directory handles và threat model mạnh hơn.

Không dùng `MultipartFile.getOriginalFilename()` hay một path từ HTTP client làm object key. Original filename chỉ là metadata **không đáng tin**.

## 6. AssetService: business logic không biết AWS SDK hoặc Files

Tạo `src/main/java/example/storage/AssetService.java`:

```java
package example.storage;

import java.io.IOException;
import java.util.Optional;
import java.util.UUID;

import org.springframework.stereotype.Service;

@Service
public class AssetService {
    public static final int MAX_BYTES = 1024 * 1024;

    private final BlobStore store;

    public AssetService(BlobStore store) {
        this.store = store;
    }

    public String save(byte[] content) throws IOException {
        if (content == null
                || content.length == 0
                || content.length > MAX_BYTES) {
            throw new IllegalArgumentException(
                    "invalid asset size");
        }

        String key = UUID.randomUUID().toString();
        store.put(key, content.clone());
        return key;
    }

    public Optional<byte[]> read(String key)
            throws IOException {
        ObjectKeys.requireValid(key);
        return store.get(key).map(data -> data.clone());
    }
}
```

Đọc file này để thấy **đúng ranh giới**:

- Service biết giới hạn kích thước, tạo key và gọi port.
- Service **không** có import `software.amazon.awssdk.*` hoặc `Files.*`, không đọc credentials hoặc absolute filesystem path.
- Dùng `UUID.randomUUID()` cho ví dụ để tránh tên object đụng nhau giữa test methods; không dùng identity này làm authorization token hoặc cấp quyền.
- `content.clone()` khi put và `data.clone()` khi read là defensive copy, tránh fake/adapter giữ chung mutable byte array làm test “thành công” sai.
- Key validation trước khi gọi adapter tránh path/key không hợp lệ đi vào hạ tầng.
- Không có database metadata, owner/tenant, MIME sniffing, malware scan hoặc transaction trong ví dụ. Nếu ứng dụng thật có metadata DB, cần test consistency/orphan compensation khi upload thành công nhưng DB commit fail.

**Business rule ≠ provider policy.** Giới hạn 1 MiB ở service là quy định của bài; Spring MVC multipart limit, proxy/server limit và provider quota là những tầng khác. Không được chỉ dựa vào service check khi request rất lớn có thể đã bị buffer trước.

## 7. FileBlobStore: adapter filesystem thật, root được kiểm soát

Tạo `src/main/java/example/storage/FileBlobStore.java`:

```java
package example.storage;

import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Optional;

public final class FileBlobStore implements BlobStore {
    private final Path root;

    public FileBlobStore(Path root) throws IOException {
        this.root = root.toAbsolutePath().normalize();
        Files.createDirectories(this.root);
    }

    private Path resolve(String key) {
        ObjectKeys.requireValid(key);
        Path target = root.resolve(key).normalize();

        if (!target.getParent().equals(root)) {
            throw new IllegalArgumentException(
                    "object outside storage root");
        }

        return target;
    }

    @Override
    public void put(String key, byte[] bytes)
            throws IOException {
        Path target = resolve(key);
        Path temp = Files.createTempFile(
                root, ".asset-", ".tmp");

        try {
            Files.write(temp, bytes);

            try {
                Files.move(
                        temp, target,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException error) {
                Files.move(
                        temp, target,
                        StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temp);
        }
    }

    @Override
    public Optional<byte[]> get(String key)
            throws IOException {
        Path target = resolve(key);

        if (Files.isSymbolicLink(target)) {
            throw new IOException(
                    "symbolic links not allowed");
        }

        try {
            return Optional.of(
                    Files.readAllBytes(target));
        } catch (NoSuchFileException missing) {
            return Optional.empty();
        }
    }
}
```

**Những gì adapter này bảo đảm trong phạm vi demo:**

- Root được chuẩn hóa và tạo khi khởi tạo; key bị validate trước khi resolve.
- Ghi vào file tạm **cùng thư mục đích**, rồi move sang key. Khi filesystem hỗ trợ `ATOMIC_MOVE`, client đọc sẽ không thấy một file target bị ghi từng phần; nếu filesystem không hỗ trợ, fallback `REPLACE_EXISTING` **không bảo đảm atomic rename**. Đây là một giới hạn được nói rõ, không gọi cả hai paths là atomic.
- `finally` xóa file tạm nếu có lỗi trong lúc write/move.
- Không có file → `Optional.empty()`; IOException khác không được biến thành missing.
- Cố ý từ chối symlink target khi đọc, nhưng **không tuyên bố chống TOCTOU hoàn toàn** nếu attacker có quyền thay đổi root.
- Adapter này đọc toàn bộ bytes vào memory; nó phù hợp với giới hạn 1 MiB của demo. Với file vài GiB cần stream, giới hạn và backpressure thay vì `readAllBytes`.

**Với NFS/SMB:** `Files.move(ATOMIC_MOVE)` có thể không được support hoặc có consistency/locking khác. `@TempDir` trên local filesystem **không chứng minh** hành vi network share thật, permissions, mount outage, oplock, latency hoặc lock cross-host. Phải có integration job riêng trên mount được cấu hình nếu đó là contract.

## 8. S3BlobStore: adapter dùng AWS SDK thật

Tạo `src/main/java/example/storage/S3BlobStore.java`:

```java
package example.storage;

import java.io.IOException;
import java.util.Optional;

import software.amazon.awssdk.core.exception.SdkException;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.NoSuchKeyException;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

public final class S3BlobStore implements BlobStore {
    private final S3Client client;
    private final String bucket;

    public S3BlobStore(S3Client client, String bucket) {
        this.client = client;
        this.bucket = bucket;
    }

    @Override
    public void put(String key, byte[] bytes)
            throws IOException {
        ObjectKeys.requireValid(key);

        try {
            client.putObject(
                    PutObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .build(),
                    RequestBody.fromBytes(bytes));
        } catch (SdkException error) {
            throw new IOException(
                    "object storage write failed", error);
        }
    }

    @Override
    public Optional<byte[]> get(String key)
            throws IOException {
        ObjectKeys.requireValid(key);

        try {
            byte[] bytes = client.getObjectAsBytes(
                    GetObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .build())
                    .asByteArray();

            return Optional.of(bytes);
        } catch (NoSuchKeyException missing) {
            return Optional.empty();
        } catch (SdkException error) {
            throw new IOException(
                    "object storage read failed", error);
        }
    }
}
```

Đây là **AWS SDK v2 adapter thật**, không phải mock:

- `putObject` sử dụng bucket + key và body bytes, không dựa trên path local.
- `getObjectAsBytes` gọi S3 API; `NoSuchKeyException` được map thành missing theo contract. Những lỗi SDK khác (như AccessDenied, lỗi mạng) được wrap thành IOException.
- Adapter **không** tự tạo bucket, xóa bucket hoặc fallback sang filesystem khi credentials lỗi; bucket ownership/deployment là chuyện của hạ tầng.
- Trong production phải kiểm soát SDK HTTP client, timeouts/retry policy, pool, region, credentials và lifecycle đóng `S3Client`. Nên cân nhắc streaming/multipart đối với nội dung lớn.
- Port minh họa không lưu content-type, checksum, encryption, object tags hoặc metadata; nếu nghiệp vụ cần, mở rộng bằng typed object request/response và **test metadata** cụ thể.
- Client permissions cần chỉ các actions và bucket/key prefix được cấp; tránh tài khoản cloud toàn quyền trong application.

**Không dùng class `S3BlobStore` trong service unit test.** Unit test thay port; S3 integration test tạo adapter thật với LocalStack.

## 9. Cấu hình Spring chọn đúng adapter, không fallback âm thầm

Tạo `src/main/java/example/storage/BlobStorageConfiguration.java`:

```java
package example.storage;

import java.io.IOException;
import java.nio.file.Path;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.services.s3.S3Client;

@Configuration(proxyBeanMethods = false)
public class BlobStorageConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "app.storage.provider",
            havingValue = "disk",
            matchIfMissing = true)
    BlobStore diskBlobStore(
            @Value("${app.storage.root:build/blob-data}")
                    String root) throws IOException {
        return new FileBlobStore(Path.of(root));
    }

    @Bean(destroyMethod = "close")
    @ConditionalOnProperty(
            name = "app.storage.provider",
            havingValue = "s3")
    S3Client s3Client() {
        return S3Client.create();
    }

    @Bean
    @ConditionalOnProperty(
            name = "app.storage.provider",
            havingValue = "s3")
    BlobStore s3BlobStore(
            S3Client client,
            @Value("${app.storage.bucket}")
                    String bucket) {
        return new S3BlobStore(client, bucket);
    }
}
```

Các giá trị `app.storage.provider`:

| Value | Bean application tạo | Điều kiện môi trường |
| --- | --- | --- |
| Không có property | `diskBlobStore` | Root mặc định `build/blob-data` |
| `disk` | `diskBlobStore` | Quyền ghi/thư mục đã định |
| `s3` | `s3Client` + `s3BlobStore` | AWS region, credential chain, bucket |
| `memory` | **Không tạo adapter production** | Chỉ test có fake bean được import mới khởi động được |

**Vì sao `memory` không fallback sang disk?** Test flow sẽ khai báo `app.storage.provider=memory` và cung cấp test-only `BlobStore`. Nếu fake không có, Spring sẽ không tìm được bean mà `AssetService` yêu cầu và **startup fail rõ ràng** thay vì tự ghi ra thư mục mặc định — hành vi an toàn, dễ phát hiện test seam bị thiếu.

Khi production chọn `s3`, `S3Client.create()` sử dụng default credential/region provider chain; region/identity phải được cấp đúng qua deployment config (ví dụ workload identity), không hardcode access key vào source. `@Bean(destroyMethod="close")` đóng SDK client khi Spring context kết thúc.

**Cảnh báo về default disk:** path `build/blob-data` là chỗ minh họa ở local project, **không phải vị trí lưu bền vững được khuyến nghị cho production container**. Với Kubernetes, filesystem trong container có thể ephemeral. Production cần cấu hình volume mount/storage root rõ và backup/permissions/quota tương ứng.

## 10. Spring Boot app và REST API có ranh giới rõ

### AssetApplication.java

Tạo `src/main/java/example/storage/AssetApplication.java`:

```java
package example.storage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AssetApplication {
    public static void main(String[] args) {
        SpringApplication.run(AssetApplication.class, args);
    }
}
```

### AssetController.java

Tạo `src/main/java/example/storage/AssetController.java`:

```java
package example.storage;

import java.io.IOException;
import java.net.URI;
import java.util.Map;
import java.util.Optional;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/assets")
public class AssetController {
    private final AssetService service;

    public AssetController(AssetService service) {
        this.service = service;
    }

    @PostMapping(
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<Map<String, String>> upload(
            @RequestPart("file") MultipartFile file)
            throws IOException {
        String key = service.save(file.getBytes());

        return ResponseEntity.created(
                URI.create("/assets/" + key))
                .body(Map.of("key", key));
    }

    @GetMapping("/{key}")
    public ResponseEntity<byte[]> download(
            @PathVariable String key)
            throws IOException {
        Optional<byte[]> result = service.read(key);

        if (result.isEmpty()) {
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok()
                .contentType(
                        MediaType.APPLICATION_OCTET_STREAM)
                .body(result.get());
    }
}
```

**Luồng request thật:**

1. Servlet multipart handling đọc file từ request; controller gọi service với bytes.
2. Service validate size, sinh key riêng và gọi port.
3. POST trả 201 Created, `Location: /assets/{key}` cùng JSON key.
4. GET từ service/port trả bytes với content-type `application/octet-stream`; missing trả 404.
5. Không có AWS SDK import hoặc `Files.*` trong controller/service.

**Không coi UUID key là quyền truy cập.** API demo chưa có authentication, tenant authorization, encryption hay kiểm tra “người gọi có quyền xem key này” — khi production phải thêm authorization **trước khi gọi storage**. Cũng không được dựa vào original filename để quyết định object key/path.

**Kích thước:** vì `MultipartFile.getBytes()` đọc bytes vào memory, cần giới hạn multipart ở reverse proxy và Servlet, ví dụ `spring.servlet.multipart.max-file-size` và `max-request-size`. Demo service từ chối byte[] lớn hơn 1 MiB, nhưng check này xảy ra **sau** khi MVC đã nhận file. Với file lớn cần streaming với budget rõ.

### BlobErrorAdvice.java

Tạo `src/main/java/example/storage/BlobErrorAdvice.java`:

```java
package example.storage;

import java.io.IOException;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class BlobErrorAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badInput() {
        return ResponseEntity.badRequest()
                .body(Map.of("error", "invalid input"));
    }

    @ExceptionHandler(IOException.class)
    public ResponseEntity<Map<String, String>> unavailable() {
        return ResponseEntity.status(
                        HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of(
                        "error", "storage unavailable"));
    }
}
```

Advice không phản chiếu raw path, secret, bucket name hoặc SDK exception message vào response. Mapping IOException → 503 là **policy minh họa**; trong production nên phân biệt auth misconfiguration (thường không retry), throttling/transient storage outage (retry), upload too large (413), invalid content type (415) và unknown internal error.

## 11. Gradle project tương thích Java 17

Cấu trúc:

```text
src/
├── main/java/example/storage/
│   ├── AssetApplication.java
│   ├── BlobStore.java
│   ├── ObjectKeys.java
│   ├── AssetService.java
│   ├── FileBlobStore.java
│   ├── S3BlobStore.java
│   ├── BlobStorageConfiguration.java
│   ├── AssetController.java
│   ├── BlobErrorAdvice.java
│   └── ObjectKeysDemo.java
└── test/java/example/storage/
    ├── AssetServiceTest.java
    ├── FileBlobStoreTest.java
    ├── AssetControllerTest.java
    ├── AssetFlowWithFakeStoreTest.java
    └── S3BlobStoreLocalStackTest.java
```

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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

    implementation platform(
            'software.amazon.awssdk:bom:2.30.36')
    implementation 'software.amazon.awssdk:s3'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:localstack'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Mục tiêu version:** Spring Boot 3.5.0, Java 17+, AWS SDK v2 theo BOM `2.30.36`, Testcontainers 1.x được Spring Boot BOM quản lý. Nếu team sử dụng phiên bản khác, phải đồng bộ dependency/imports; Testcontainers 2.x có thể đổi tọa độ artifact/module. Để chạy Gradle commands cần một Gradle wrapper tương thích hoặc Gradle đã cài; file build trên không tự tạo `gradlew`.

**Tác vụ nào cần Docker?** Chỉ `S3BlobStoreLocalStackTest` yêu cầu Docker/Testcontainers. Service tests, filesystem tests, MVC tests và Spring fake-flow test không cần AWS credentials/Docker. LocalStack image cũng cần được pull, nên CI cần network hoặc image cache.

**Không cần access key AWS thực trong LocalStack tests.** LocalStack test dùng credentials do container cung cấp (không có giá trị ở AWS production), endpoint override và path-style access. Không cấu hình env AWS_ACCESS_KEY_ID trỏ tới account thật cho test này.

## 12. Service unit test: mock đúng BlobStore port

Tạo `src/test/java/example/storage/AssetServiceTest.java`:

```java
package example.storage;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class AssetServiceTest {
    private final BlobStore store = mock(BlobStore.class);
    private final AssetService service =
            new AssetService(store);

    @Test
    void savesOpaqueKeyAndExactBytes() throws Exception {
        byte[] data = "Xin chào 😀".getBytes(
                StandardCharsets.UTF_8);

        String key = service.save(data);

        ObjectKeys.requireValid(key);

        ArgumentCaptor<byte[]> captured =
                ArgumentCaptor.forClass(byte[].class);

        verify(store).put(eq(key), captured.capture());

        assertArrayEquals(data, captured.getValue());
        assertNotSame(data, captured.getValue());
    }

    @Test
    void rejectsNullEmptyAndOversizedContent()
            throws Exception {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.save(null));

        assertThrows(
                IllegalArgumentException.class,
                () -> service.save(new byte[0]));

        assertThrows(
                IllegalArgumentException.class,
                () -> service.save(
                        new byte[AssetService.MAX_BYTES + 1]));

        verifyNoInteractions(store);
    }

    @Test
    void returnsMissingWhenBackendReportsMissing()
            throws Exception {
        when(store.get("absent"))
                .thenReturn(Optional.empty());

        assertFalse(service.read("absent").isPresent());
        verify(store).get("absent");
    }

    @Test
    void returnsDefensiveCopyOfStoredBytes()
            throws Exception {
        byte[] actual = {0, 1, 2, -1};
        when(store.get("valid-key"))
                .thenReturn(Optional.of(actual));

        byte[] returned = service.read(
                "valid-key").orElseThrow();

        assertArrayEquals(actual, returned);
        assertNotSame(actual, returned);
    }

    @Test
    void rejectsPathLikeKeyBeforeCallingStore()
            throws Exception {
        assertThrows(
                IllegalArgumentException.class,
                () -> service.read("../other"));

        verifyNoInteractions(store);
    }

    @Test
    void propagatesStorageOutageInsteadOfReturning404()
            throws Exception {
        doThrow(new IOException("disk offline"))
                .when(store)
                .put(anyString(), any(byte[].class));

        assertThrows(
                IOException.class,
                () -> service.save(new byte[]{1, 2}));

        verify(store).put(
                anyString(), any(byte[].class));
    }
}
```

**Sáu JUnit test methods** chứng minh business rules và port call, không kiểm tra disk/S3:

- Key hợp lệ và ngẫu nhiên, không lấy filename người dùng.
- Payload Unicode UTF-8 được truyền nguyên bytes; service clone tránh mutation.
- Null, empty, vượt giới hạn bị reject trước khi chạm storage.
- Not found trả Optional.empty, khác với failure storage.
- Key `../other` bị chặn trước khi gọi backend.
- IOException truyền tới application boundary thay vì bị biến thành 404 thành công giả.

**Vì sao không mock `S3Client` trong lớp này?** Service không nên biết S3Client. Nếu unit test viết `verify(s3Client).putObject(...)`, test đã bị ràng chặt với triển khai AWS và gây khó thay backend. Adapter test riêng mới kiểm tra mapping tới AWS SDK.

**Khi nào fake tốt hơn mock?** Nếu cần chạy nhiều thao tác cùng nhau (upload rồi download) và kiểm tra state/semantics, một `MapBlobStore` fake cho phép thao tác thật trong memory, ít stub thủ công hơn; mục 15 dùng phương án này.

## 13. Filesystem integration: @TempDir kiểm tra I/O thực

Tạo `src/test/java/example/storage/FileBlobStoreTest.java`:

```java
package example.storage;

import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class FileBlobStoreTest {
    @TempDir
    Path directory;

    @Test
    void roundTripsUnicodeBytesOnRealFilesystem()
            throws Exception {
        BlobStore store = new FileBlobStore(
                directory.resolve("objects"));

        byte[] original = "Tệp 😀".getBytes(
                StandardCharsets.UTF_8);

        store.put("unicode-key", original);

        assertArrayEquals(
                original,
                store.get("unicode-key").orElseThrow());
    }

    @Test
    void missingFileReturnsEmptyOptional()
            throws Exception {
        BlobStore store = new FileBlobStore(
                directory.resolve("objects"));

        assertFalse(
                store.get("not-present").isPresent());
    }

    @Test
    void rejectsTraversalAndSlashSeparatedKeys()
            throws Exception {
        BlobStore store = new FileBlobStore(
                directory.resolve("objects"));

        assertThrows(
                IllegalArgumentException.class,
                () -> store.put("../escape", new byte[]{1}));

        assertThrows(
                IllegalArgumentException.class,
                () -> store.get("tenant/other"));
    }

    @Test
    void overwriteReplacesPreviousContents()
            throws Exception {
        BlobStore store = new FileBlobStore(
                directory.resolve("objects"));

        store.put("same-key", new byte[]{1, 2, 3});
        store.put("same-key", new byte[]{9});

        assertArrayEquals(
                new byte[]{9},
                store.get("same-key").orElseThrow());
    }

    @Test
    void independentRootsDoNotShareObjects()
            throws Exception {
        BlobStore first = new FileBlobStore(
                directory.resolve("first"));
        BlobStore second = new FileBlobStore(
                directory.resolve("second"));

        first.put("only-first", new byte[]{1});

        assertTrue(
                first.get("only-first").isPresent());
        assertFalse(
                second.get("only-first").isPresent());
    }
}
```

**Năm integration methods** không mock `Files.*`; chúng thao tác filesystem thật nhưng trong `@TempDir` được JUnit quản lý.

**Phạm vi bằng chứng:**

- Tạo thư mục, PUT/GET bytes thật, Unicode bytes đúng, missing trả empty.
- Key validation chặn path traversal và slash.
- Overwrite và isolation giữa hai storage roots.
- Không ghi vào `/tmp` cố định toàn cục, home directory hoặc shared NFS của developer.
- Không cần `@SpringBootTest` vì adapter không phụ thuộc Spring; JUnit thuần nhanh và lỗi dễ chẩn đoán.

**Giới hạn:** đây là local filesystem test. Nó **không** kiểm tra NFS mount outage, SMB ACL, cross-host locks, remote permissions, rename atomicity thực tế của mạng share hay quota/disk-full. Khi code phụ thuộc những semantics ấy, phải có thêm test trên resource tương ứng; `@TempDir` không đủ để kết luận production filesystem sẽ giống local.

## 14. MVC slice: mock service, vì đây là HTTP boundary test

Tạo `src/test/java/example/storage/AssetControllerTest.java`:

```java
package example.storage;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebMvcTest(AssetController.class)
class AssetControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    AssetService service;

    @Test
    void multipartUploadReturnsCreatedLocationAndKey()
            throws Exception {
        byte[] bytes = "data".getBytes(
                StandardCharsets.UTF_8);

        MockMultipartFile file = new MockMultipartFile(
                "file", "ignored-name.txt",
                "text/plain", bytes);

        when(service.save(any(byte[].class)))
                .thenReturn("stored-key");

        mvc.perform(
                multipart("/assets").file(file))
                .andExpect(status().isCreated())
                .andExpect(
                        header().string(
                                "Location", "/assets/stored-key"))
                .andExpect(
                        jsonPath("$.key").value("stored-key"));

        ArgumentCaptor<byte[]> captured =
                ArgumentCaptor.forClass(byte[].class);

        verify(service).save(captured.capture());
        assertArrayEquals(bytes, captured.getValue());
    }

    @Test
    void downloadReturnsBytesAsOctetStream()
            throws Exception {
        byte[] bytes = {0, 1, 2, -1};

        when(service.read("stored-key"))
                .thenReturn(Optional.of(bytes));

        mvc.perform(get("/assets/stored-key"))
                .andExpect(status().isOk())
                .andExpect(
                        content().contentType(
                                MediaType.APPLICATION_OCTET_STREAM))
                .andExpect(content().bytes(bytes));
    }

    @Test
    void missingObjectBecomes404() throws Exception {
        when(service.read("missing"))
                .thenReturn(Optional.empty());

        mvc.perform(get("/assets/missing"))
                .andExpect(status().isNotFound());
    }

    @Test
    void invalidContentBecomes400() throws Exception {
        when(service.save(any(byte[].class)))
                .thenThrow(new IllegalArgumentException(
                        "invalid size"));

        MockMultipartFile file = new MockMultipartFile(
                "file", "empty.txt",
                "text/plain", new byte[0]);

        mvc.perform(
                multipart("/assets").file(file))
                .andExpect(status().isBadRequest())
                .andExpect(
                        jsonPath("$.error").value(
                                "invalid input"));
    }

    @Test
    void storageIOExceptionBecomes503() throws Exception {
        when(service.read("stored-key"))
                .thenThrow(new IOException(
                        "backend unavailable"));

        mvc.perform(get("/assets/stored-key"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(
                        jsonPath("$.error").value(
                                "storage unavailable"));
    }
}
```

**Năm JUnit MVC methods** xác nhận request binding, status code, Location header, content-type, binary body và lỗi API. Chúng không tạo disk file hay S3 object.

**Chọn mock đúng boundary:** với `@WebMvcTest(AssetController.class)`, controller là code thật và `AssetService` là collaborator được mock. Đó là đúng vì mục tiêu **chỉ là HTTP contract**. Nếu mục tiêu là test business rule, không mock service — dùng service unit hoặc flow test ở mục kế tiếp.

**Vì sao dùng `@MockitoBean`?** Spring Framework 6.2 / Spring Boot 3.5 cung cấp annotation này cho bean override trong Spring test context. `@MockBean` là cơ chế cũ đã được deprecate ở các nhánh Boot mới; dùng import đúng với bộ version của project. Không truyền class AWS S3 SDK vào controller slice khi không cần.

## 15. Full Spring flow với fake đặt ở external boundary

Đây là ví dụ quan trọng nhất cho câu hỏi “thay ở **đúng ranh giới**”: controller và business service **đều thật**, chỉ thay `BlobStore` bằng một implementation in-memory **thuộc test class**.

Tạo `src/test/java/example/storage/AssetFlowWithFakeStoreTest.java`:

```java
package example.storage;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.MOCK,
        properties = "app.storage.provider=memory")
@AutoConfigureMockMvc
class AssetFlowWithFakeStoreTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void uploadThenDownloadThroughRealControllerAndService()
            throws Exception {
        byte[] bytes = "Luồng thật 😀".getBytes(
                StandardCharsets.UTF_8);

        MockMultipartFile file = new MockMultipartFile(
                "file", "user/../ignored.txt",
                "text/plain", bytes);

        MvcResult response = mvc.perform(
                multipart("/assets").file(file))
                .andExpect(status().isCreated())
                .andReturn();

        String key = mapper.readTree(
                        response.getResponse()
                                .getContentAsString())
                .get("key").asText();

        ObjectKeys.requireValid(key);

        mvc.perform(get("/assets/" + key))
                .andExpect(status().isOk())
                .andExpect(content().contentType(
                        MediaType.APPLICATION_OCTET_STREAM))
                .andExpect(content().bytes(bytes));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FakeStorageConfiguration {
        @Bean
        BlobStore memoryBlobStore() {
            return new MemoryBlobStore();
        }
    }

    static class MemoryBlobStore implements BlobStore {
        private final ConcurrentMap<String, byte[]> data =
                new ConcurrentHashMap<>();

        @Override
        public void put(String key, byte[] bytes)
                throws IOException {
            ObjectKeys.requireValid(key);
            data.put(key, bytes.clone());
        }

        @Override
        public Optional<byte[]> get(String key)
                throws IOException {
            ObjectKeys.requireValid(key);
            byte[] found = data.get(key);

            return found == null
                    ? Optional.empty()
                    : Optional.of(found.clone());
        }
    }
}
```

**Một Spring integration method** kiểm tra toàn luồng HTTP → controller → service → port fake → controller. Nó chứng minh:

- Spring component scanning và constructor injection nối các beans.
- Multi-part controller gọi service thật; service sinh key hợp lệ.
- Bytes Unicode được lưu/đọc thông qua fake theo cùng contract.
- Tên file do client cố tình chứa `../` **không được dùng làm object key/path**.
- Property `app.storage.provider=memory` làm cả disk và S3 production beans không match; test-only `@Bean BlobStore` là backend duy nhất. Nếu quên fake, Spring context fail vì thiếu `BlobStore` thay vì ghi đè ra disk.
- Test không cần file permission, AWS creds, endpoint LocalStack hoặc network.

**Điều test chưa chứng minh:** file thật đã được ghi, atomic rename được support hoặc S3 request chạy thành công. Chúng thuộc adapter tests. Đây là một **integration test không I/O bên ngoài**, không phải một S3 integration test.

### Vì sao fake khác mock?

Mockito mock trả kết quả theo stub của từng call; fake `MemoryBlobStore` lưu state thật giữa `put/get`. Fake thích hợp cho **application workflow** nhiều bước, nhưng cần giữ đúng contract: missing trả Optional.empty, byte arrays cloned, key invalid bị reject, overwrite cùng key cập nhật content. Nếu fake quá “dễ” (mọi get trả bytes bất kể key), flow test có thể xanh dù production adapter có bug.

**Không tạo fake làm @Component trong src/main**. Nó chỉ nên nằm trong `src/test` (hoặc test utilities), không lộ như một production storage option vô tình được deploy.

## 16. S3 integration với LocalStack Testcontainers và AWS SDK v2

Tạo `src/test/java/example/storage/S3BlobStoreLocalStackTest.java`:

```java
package example.storage;

import java.util.Optional;
import java.util.UUID;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.localstack.LocalStackContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.model.CreateBucketRequest;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Testcontainers
class S3BlobStoreLocalStackTest {
    private static final String BUCKET =
            "lesson-storage";

    @Container
    static LocalStackContainer localstack =
            new LocalStackContainer(
                    DockerImageName.parse(
                            "localstack/localstack:3.8.1"))
                    .withServices(
                            LocalStackContainer.Service.S3);

    private static S3Client client;
    private static BlobStore store;

    @BeforeAll
    static void createBucket() {
        client = S3Client.builder()
                .endpointOverride(
                        localstack.getEndpointOverride(
                                LocalStackContainer.Service.S3))
                .credentialsProvider(
                        StaticCredentialsProvider.create(
                                AwsBasicCredentials.create(
                                        localstack.getAccessKey(),
                                        localstack.getSecretKey())))
                .region(Region.of(
                        localstack.getRegion()))
                .serviceConfiguration(
                        S3Configuration.builder()
                                .pathStyleAccessEnabled(true)
                                .build())
                .build();

        client.createBucket(
                CreateBucketRequest.builder()
                        .bucket(BUCKET)
                        .build());

        store = new S3BlobStore(client, BUCKET);
    }

    @AfterAll
    static void closeClient() {
        if (client != null) {
            client.close();
        }
    }

    @Test
    void putAndGetRoundTripWithRealS3Api()
            throws Exception {
        String key = UUID.randomUUID().toString();
        byte[] bytes = {0, 1, 2, -1};

        store.put(key, bytes);

        assertArrayEquals(
                bytes, store.get(key).orElseThrow());
    }

    @Test
    void nonexistentKeyReturnsEmpty()
            throws Exception {
        String key = UUID.randomUUID().toString();

        assertFalse(store.get(key).isPresent());
    }

    @Test
    void invalidKeyIsRejectedBeforeS3Request()
            throws Exception {
        assertThrows(
                IllegalArgumentException.class,
                () -> store.put(
                        "../bad", new byte[]{1}));
    }
}
```

**Ba integration methods** dùng một LocalStack container do JUnit Jupiter extension quản lý theo **test class**. Client được tạo sau khi container đã start, kết nối tới **endpoint override**, region và credentials của LocalStack; tạo bucket test, gọi **S3 API thật** qua SDK, đọc lại body hoặc xác nhận key không có.

**Khác biệt với unit test:**

- AWS SDK request serialization/HTTP client được sử dụng thật.
- Object key và bucket được áp dụng bởi S3-compatible server.
- Không mock `S3Client.putObject/getObjectAsBytes`; code adapter được thực thi.
- S3 client đóng trong `@AfterAll`. Container static sẽ được extension dừng sau class.
- Không hardcode `localhost:4566` vì mapped port/host có thể khác ở CI/remote Docker.
- Không cần có AWS production credentials và không kết nối AWS service public.

**Giới hạn LocalStack:** S3 emulation không thể thay thế test IAM role, bucket policy, KMS grants, endpoint TLS, network firewall, object lock, cross-region replication, S3 Event Notifications hoặc latency thật. Khi cần những contract này, chạy thêm tests tại account/bucket staging có policy và cleanup được kiểm soát. Tránh tạo hoặc xóa objects trên production bucket.

**Version notes:** đoạn test dùng Testcontainers 1.x artifact `org.testcontainers:localstack` với import `org.testcontainers.containers.localstack.LocalStackContainer`. Các phiên bản Testcontainers 2.x tổ chức modules/packages khác; cập nhật theo BOM và tài liệu của version đang dùng, không trộn.

## 17. Tại sao chỉ mock AWS S3Client không đủ?

Một adapter unit test có thể viết:

```java
S3Client s3 = mock(S3Client.class);
S3BlobStore store = new S3BlobStore(
        s3, "lesson-storage");
store.put("abc", new byte[]{1});
verify(s3).putObject(
        any(PutObjectRequest.class),
        any(RequestBody.class));
```

Đây là **snippet minh họa** cần Mockito imports. Nó có giá trị nhỏ: xác nhận adapter gọi SDK method. Nhưng test **không chứng minh** request có đúng bucket/key, service nhận được body, region/path-style, permission hoặc response 404. Nếu chỉ verify method count mà không inspect request fields, ngay cả code `bucket("wrong-bucket")` cũng có thể pass.

Nếu team muốn một lớp adapter unit test để kiểm tra request construction, dùng `ArgumentCaptor<PutObjectRequest>` và assert `bucket/key/contentType`. Nhưng vẫn cần LocalStack/real S3 integration để kiểm tra giao thức.

**Không mock static `Files.readAllBytes` trong service unit test**: bạn đang kéo filesystem API vào service thay vì đặt nó sau port, làm test khó cô lập và khuyến khích thiết kế phụ thuộc I/O.

## 18. Chương trình Java SE độc lập cho key validation

Tạo `src/main/java/example/storage/ObjectKeysDemo.java`:

```java
package example.storage;

public class ObjectKeysDemo {
    public static void main(String[] args) {
        String safe = "abc-123";
        ObjectKeys.requireValid(safe);
        System.out.println("valid=" + safe);

        try {
            ObjectKeys.requireValid("../etc/passwd");
        } catch (IllegalArgumentException error) {
            System.out.println(
                    "rejected=" + error.getMessage());
        }
    }
}
```

Dùng JDK 17+ từ project root:

```bash
javac -d out src/main/java/example/storage/ObjectKeys.java src/main/java/example/storage/ObjectKeysDemo.java
java -cp out example.storage.ObjectKeysDemo
```

Stdout **chính xác**:

```text
valid=abc-123
rejected=invalid object key
```

**Giới hạn:** đây là Java SE demo kiểm tra allowlist key, không mở Spring context, không đọc filesystem và không kết nối S3. Dùng nó để hiểu vì sao raw filename/path không được đưa trực tiếp vào adapter, không lấy nó làm bằng chứng upload đã thành công.

## 19. Phân biệt mock, fake, local emulator và production contract

| Test double/môi trường | Ví dụ trong bài | Điểm mạnh | Điểm mù |
| --- | --- | --- | --- |
| Mockito mock | `mock(BlobStore.class)` | Kiểm tra calls/arguments/throw | Không tự lưu state |
| In-memory fake | `MemoryBlobStore` | Test upload→download flow thật | Không có filesystem/S3 semantics |
| Local filesystem | `FileBlobStore(@TempDir)` | I/O NIO thật, cleanup dễ | Không phải NFS/SMB thực |
| LocalStack | `S3BlobStore + S3Client` | API integration không cần AWS account | Không bao trùm toàn bộ AWS IAM/KMS/etc. |
| AWS staging bucket | Deployment-controlled test | Auth/region/behavior production-like | Chi phí, security, cleanup, flaky remote dependencies |

### “Đúng ranh giới” phụ thuộc mục tiêu assertion

- Test controller route: mock `AssetService`, không cần port.
- Test service rule: mock/fake `BlobStore`; **service thật**.
- Test application orchestration: real controller + real service, fake ở `BlobStore`.
- Test disk adapter: thật `FileBlobStore` + thật @TempDir.
- Test S3 adapter: thật `S3BlobStore` + thật S3Client + LocalStack.
- Test IAM/permission production: thật provider staging với identity hạn chế; LocalStack test không đủ.

**Anti-pattern:** cấu hình test mà vô tình dùng default disk bean trong project root khi tưởng đang test fake, vì test không đặt provider property rõ. Ví dụ flow đặt `app.storage.provider=memory` và định nghĩa test bean, vì vậy không có adapter disk/s3 production. Khi test muốn đảm bảo ứng dụng không fallback, có thể assert chính xác chỉ một `BlobStore` bean và loại implement `FileBlobStore/S3BlobStore`.

## 20. Test matrix cho thành công, lỗi và isolation

| Scenario | Service unit | MVC | Filesystem @TempDir | LocalStack S3 | Full flow fake |
| --- | --- | --- | --- | --- | --- |
| Upload hợp lệ | Có | Status 201 | Put bytes | PUT/GET | HTTP→service→fake |
| Download hiện hữu | Mock result | Bytes 200 | Read bytes | GET bytes | Có |
| Missing key | Optional.empty | 404 | Có | Có | Có thể bổ sung |
| Input null/empty/too large | Có | 400 từ service | Không tự áp business rule | Không tự áp business rule | Có thể bổ sung |
| Key traversal | Trước port | Route/input contract | Validate | Validate | Service validate |
| I/O failure | Mock IOException | 503 | Test fault injection riêng | SDK exception riêng | Fake có thể ném |
| Overwrite same key | Port contract | Không quan trọng | Có | Có thể bổ sung |
| Unicode/binary | Có | Binary | Unicode bytes | Binary | Unicode bytes |
| Credentials/permission denied | Không | 5xx policy | OS permission tùy env | LocalStack hạn chế | Không |
| Real NFS outage | Không | 5xx policy | Không | Không | Không |
| S3 IAM/KMS/presigned URL | Không | Không | Không | Chỉ khi có emulation test chuyên biệt | Không |

**Không nên đòi một test gánh toàn bộ bảng**. Mỗi lớp test có nhiệm vụ rõ ràng, giúp lỗi được khoanh vùng nhanh. Một CI hợp lý chạy unit/MVC/TempDir/fake-flow ở mọi commit, LocalStack ở integration job, còn staging provider contract theo release/nightly/permission policy.

### Hành vi not-found và unavailable khác nhau

Sai:

```java
try {
    return store.get(key);
} catch (Exception error) {
    return Optional.empty();
}
```

Đây là **anti-pattern**, không phải implementation của bài. Nó biến lỗi access denied, DNS, timeout, disk I/O, region sai thành **404**. Client có thể hiểu nhầm object đã bị xóa, gây data loss hoặc retry không đúng.

Trong ví dụ:

- Missing disk file → `NoSuchFileException` → `Optional.empty()`.
- Missing S3 key → `NoSuchKeyException` → `Optional.empty()`.
- Lỗi khác → `IOException` → API trả 503 theo sample advice.

Đó là hợp đồng đáng kiểm tra bằng fault-injection tests, không chỉ bằng happy path.

## 21. Tệp lớn, streaming và memory budget

Ví dụ demo có `MAX_BYTES=1_048_576`, nên `MultipartFile.getBytes()` và `S3Client.getObjectAsBytes()` được giới hạn gián tiếp bởi service policy khi upload. **Tuy nhiên** GET của object tồn tại từ bên ngoài service **không tự bị giới hạn** bởi upload rule: một S3 object có thể lớn hơn 1 MiB nếu được tạo từ client khác. Production cần giới hạn download hoặc streaming thay vì `getObjectAsBytes` cho object lớn.

Đối với file lớn:

- HTTP upload nên xử lý `InputStream`/streaming/multipart API với size budget, content-length và read limits.
- Port có thể định nghĩa `put(ObjectKey key, InputStream body, long length, Metadata metadata)` hoặc abstraction upload session; document ownership/closing của stream.
- AWS SDK v2 sync `RequestBody.fromInputStream(inputStream, length)` cần length chính xác; nếu không biết length, không đưa dữ liệu vô hạn vào memory chỉ để lấy byte[].
- Object storage multipart upload cần abort những upload chưa hoàn tất, tránh tích lũy chi phí.
- GET nên trả stream/resource và closing semantics rõ, có thể hỗ trợ range requests, ETag/If-None-Match và cache headers.
- Với Spring MVC, `StreamingResponseBody` hoặc resource streaming cần phù hợp thread pool và cancellation; test phải đóng stream và kiểm tra error path.
- Với reactive WebFlux, dùng reactive streams/backpressure, không gọi blocking S3/File API trực tiếp trên event-loop thread.

**Không làm một fake in-memory tự động chấp nhận stream vô hạn**. Fake phải tôn trọng các giới hạn quan trọng của port (length, cancellation, checksum hoặc metadata) nếu những điều đó là business contract.

## 22. File/object metadata và bảo mật tải xuống

Production thường cần thêm:

- `contentType`, content disposition, original filename **được sanitize**, size, checksum (SHA-256), ETag, createdAt.
- Tenant/user ownership, object retention, soft delete, audit logs.
- Virus/malware scanning, MIME sniffing, allowlisted types; không chỉ tin `MultipartFile.getContentType()`.
- Encryption at rest (SSE-S3/SSE-KMS), in transit TLS, IAM role least privilege, short-lived signed URL.
- Presigned URL expiry/permissions theo bucket/key/method, **không** dùng UUID làm authorization token.
- Protection khỏi zip bomb, polyglot files, path traversal, header injection, malicious SVG/HTML.
- Download response headers: `Content-Type`, `Content-Disposition`, `Cache-Control`, `X-Content-Type-Options` và CSP khi ứng dụng có risk cần thiết.
- Checksum và tamper detection khi bytes là dữ liệu quan trọng.

**Bài cố ý trả application/octet-stream** để tránh phục vụ content untrusted trực tiếp như HTML/JS. Điều đó chưa thay thế content security controls. Controller test kiểm tra header/body, nhưng chưa có authentication/authorization tests; không tuyên bố bảo mật production đã hoàn chỉnh.

### Nếu metadata nằm trong database

Một upload flow thường là:

```text
PUT object to S3
    |
    v
INSERT asset_metadata into PostgreSQL
    |
    +-- DB transaction fails?
          |
          +-- orphan object còn trên S3
```

Không có một local `@Transactional` bao trùm cả PostgreSQL và S3. Thiết kế có thể cần **compensation**, outbox/job recovery, pending/ready state, idempotency keys và garbage collection. Một service unit test mock `BlobStore` không chứng minh fail-recovery của distributed workflow; test các failure windows và orphan cleanup trong integration/E2E job.

**Tránh kết luận**: “file đã được PUT lên S3 thì database commit chắc chắn đã xong”, hoặc ngược lại. Hai resource có transaction/lifecycle riêng.

## 23. @TempDir không mô phỏng NFS/SMB và atomic rename tuyệt đối

Khi hệ thống lưu file qua network mount, các bug chỉ xuất hiện ở môi trường thật:

- File permission/UID/GID, SMB ACL, share modes, identity mapping.
- Mount rớt, network partition, stale file handle.
- Atomic rename và fsync/durability semantics tùy filesystem/provider.
- Concurrent writers từ nhiều hosts, lock advisory/mandatory differences.
- Case sensitivity, path length, Unicode normalization, Windows vs POSIX separators.
- Quota/disk full, inode limit, latency và recovery.
- Symlink/hardlink races nếu có actors không tin cậy cùng ghi root.
- File watchers/inotify không bao trùm mọi remote FS semantics.

**Lớp FileBlobStoreTest dùng local @TempDir chứng minh những thao tác NIO cơ bản**, không đủ để test danh sách trên. Nếu NFS/SMB là dependency chính, nên có một integration test job dùng isolated network share và fault injection đúng quyền, sau đó clean up resources theo key prefix riêng.

**Không dùng `Files.exists` để giả lập trường hợp permission denied**. `Files.exists` có thể trả false khi không xác định được sự tồn tại; nếu cần phân biệt missing/unavailable, dùng read/open thật và bắt exception đúng loại. File adapter mẫu bắt **NoSuchFileException duy nhất** cho missing.

## 24. Testcontainers lifecycle và Spring context cache

Trong ví dụ LocalStack test, `@Testcontainers` + static `@Container` là **Jupiter-owned** và không tạo Spring context; không có cached datasource/client từ Spring dùng lại sau container stop. Nhưng khi một `@SpringBootTest` khai báo `@Container` static rồi `@ServiceConnection`, phải cân nhắc:

- JUnit extension stop container sau **test class**.
- Spring TestContext có thể cache `ApplicationContext` giữa classes có cùng configuration.
- Nếu Spring context được reuse mà client vẫn giữ endpoint của container đã stop, các tests sau có thể lỗi “connection refused”.

Một phương án là quản lý container như Spring test `@Bean` (nếu framework phù hợp) để lifecycle sống theo context, hoặc chủ sở hữu shared suite rõ ràng. Trong bài này, adapter S3 dùng LocalStack **trực tiếp trong JUnit test**, không ghép lifecycle sai với cached context.

**Không dùng real AWS credential** làm fallback nếu Testcontainers chưa start. Trong integration test, client phải được cấu hình từ `localstack.getEndpointOverride(...)`, không lấy credentials chain public.

## 25. Race conditions, overwrite và contract khi concurrent upload

Một key ngẫu nhiên giảm nguy cơ collide, nhưng không chứng minh app chịu concurrent operations đúng:

- Hai writers cùng key có thể overwrite nhau; port của ví dụ **cho phép overwrite**, không có compare-and-set/ETag precondition.
- File adapter dùng move replacement; trên filesystem không hỗ trợ ATOMIC_MOVE, fallback có thể có observation window.
- S3 có conditional requests/ETag/versioning nếu muốn **no-overwrite** hoặc optimistic concurrency; cần port model hóa điều kiện đó.
- Test “hai PUT thành công” không chứng minh tải xuống sẽ luôn thấy một version cụ thể khi thứ tự completion không được quy định.
- Multipart uploads có intermediate state và cleanup riêng.
- Object listing/prefix consistency và pagination không thuộc `get(key)` contract; thêm tests nếu app có list/filter.
- Trong distributed app, service cache có thể trả stale metadata dù provider GET nhất quán.
- Nếu test dùng shared bucket, hãy tạo key/bucket prefix riêng và dọn cả khi failure; tránh xóa toàn bucket.

**Test contracts cần ghi rõ overwrite policy trước khi viết assertions**. Nếu product yêu cầu immutable event blobs, adapter nên dùng object key cố định từ content hash hoặc điều kiện `If-None-Match: *` và reject conflict; không thể lấy semantics từ fake đơn giản mà không cập nhật provider implementation.

## 26. Test resilience và lỗi nhà cung cấp

Một số error paths cần kiểm tra độc lập:

| Error | Unit/fake | Adapter integration | Production policy |
| --- | --- | --- | --- |
| Validation invalid key/size | Mockito verify no call | Adapter reject unsafe key | 400/413 |
| Object missing | Fake/Optional.empty | File/S3 missing | 404 |
| Storage access denied | Fake throws IOException | Provider staging permission test | 5xx/error classification |
| Bucket không tồn tại | Mock SDK/LocalStack case | S3 error path | Không trả 404 object |
| Network timeout | Inject failure | Proxy/container fault injection | Retry budget, idempotency |
| Disk full/quota | Fault injection/fs sandbox | Mount/quota test | Cleanup, alert |
| Partial write | Fault injection | Atomic move/stream behavior test | No corrupt final object |
| Checksum mismatch | Controlled corrupt data | Real metadata/checksum test | Reject/repair |
| Duplicate key concurrent | Reproducer/interleaving | ETag/conditional write test | Conflict/version policy |
| Large content | Service size rule | Stream/range integration | Memory/cost budget |

**Không dùng một exception message cụ thể làm API contract** vì AWS SDK/cloud provider đổi wording. Map exception **type/status/code** có kiểm soát, giữ original cause trong logs với redaction.

**Retry phải có idempotency:** PUT cùng key/bytes có thể được retry, nhưng nếu mỗi retry sinh một key mới hoặc DB metadata row mới, workflow có thể tạo orphan/duplicate objects. Nếu upload request có external side effects, nên sử dụng request idempotency key hoặc pending state/compensation.

## 27. Chạy toàn bộ bộ test

Bằng Gradle wrapper trong project:

```bash
./gradlew test --tests example.storage.AssetServiceTest
./gradlew test --tests example.storage.FileBlobStoreTest
./gradlew test --tests example.storage.AssetControllerTest
./gradlew test --tests example.storage.AssetFlowWithFakeStoreTest
./gradlew test --tests example.storage.S3BlobStoreLocalStackTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.storage.AssetServiceTest"
.\gradlew.bat test --tests "example.storage.FileBlobStoreTest"
.\gradlew.bat test --tests "example.storage.AssetControllerTest"
.\gradlew.bat test --tests "example.storage.AssetFlowWithFakeStoreTest"
.\gradlew.bat test --tests "example.storage.S3BlobStoreLocalStackTest"
```

Các nhóm:

| Test class | Methods | Resource thật |
| --- | ---: | --- |
| `AssetServiceTest` | 6 | Không; mock port |
| `FileBlobStoreTest` | 5 | @TempDir filesystem |
| `AssetControllerTest` | 5 | MockMvc + mocked service |
| `AssetFlowWithFakeStoreTest` | 1 | Spring context; in-memory fake |
| `S3BlobStoreLocalStackTest` | 3 | Docker + LocalStack S3 |
| **Tổng** | **20** | |

**Các test không phải LocalStack có thể chạy không cần Docker.** `@WebMvcTest` và `@SpringBootTest` khởi động các Spring contexts tương ứng nhưng không cần kết nối S3. Nếu lỗi Docker/image/daemon, chỉ test S3 integration mới nên fail vì dependency ấy; không đánh đổi bằng cách tự bật S3 live credentials.

Bộ code được đưa ra để người học **chạy và kiểm tra trong project phù hợp**; không tuyên bố đã chạy Docker/AWS trong môi trường người đọc. Gradle/JUnit output thay đổi theo môi trường và runner; không cung cấp một stdout cố định cho test suite. Chỉ demo Java SE mục 18 có stdout chính xác.

### CI phân tầng hợp lý

- Job **fast tests**: service unit, MVC slice, filesystem @TempDir, fake-flow.
- Job **storage integration**: LocalStack Testcontainers, image version/health readiness và log diagnostics.
- Job **staging contract** nếu cần IAM, NFS/SMB, encryption, pre-signed URL, signed credentials hoặc async notifications.
- Báo số test đã chạy/skip; nếu storage integration là yêu cầu bắt buộc, **đừng skip im lặng** khi Docker không khả dụng.
- Dùng bucket, path prefix và credentials test được cấp quyền tối thiểu; có cleanup trong teardown và TTL/garbage collection cho failure.
- Không để static cache/test fake dùng chung qua classes hoặc project khác ngoài ý muốn.

## 28. Anti-patterns thường gặp

**1. Service gọi `S3Client` trực tiếp.** Unit test service bị ràng buộc SDK, khó thay adapter; dùng port.

**2. Unit test dùng real AWS bucket.** Chậm, tốn tiền, lỗi mạng/IAM và nguy cơ đụng data; fake/mock đúng boundary.

**3. Mock `AssetService` khi muốn kiểm tra business rule.** Bạn chỉ test controller/delegation, không test validation/ID behavior.

**4. Mock `Files.*` trong service.** Dấu hiệu logic ứng dụng đang giữ path/I/O trực tiếp thay vì qua adapter.

**5. Dùng @TempDir và gọi đó là “S3 integration”.** Test local filesystem, không có AWS SDK protocol.

**6. Mock `S3Client.putObject` rồi kết luận bucket policy/routing/permission đúng.** SDK mock không mở network.

**7. Fake có semantics quá dễ.** Ví dụ get trả bytes dù key chưa từng put, khiến flow pass sai.

**8. Không validate key và dùng original filename làm path.** Có thể gây path traversal, overwrite tên người khác, cross-tenant access.

**9. Bắt mọi lỗi thành Optional.empty.** AccessDenied/network fail thành 404 giả và khó sửa.

**10. Log raw payload, credentials, presigned URL hoặc path thật khi exception.** Rò thông tin nhạy cảm; dùng redaction.

**11. Coi UUID là authorization token.** ID ngẫu nhiên không thay owner/tenant ACL.

**12. Không có multipart/request body limit.** App có thể nạp file khổng lồ vào RAM trước khi service check.

**13. Dùng getObjectAsBytes cho mọi file lớn.** Có nguy cơ OOM và không hỗ trợ streaming/range đúng.

**14. Tự fallback từ S3 sang disk khi IAM/endpoint lỗi.** Dữ liệu lưu sai backend mà test vẫn xanh; production nên fail có kiểm soát.

**15. Dùng @SpringBootTest cho mọi test method.** Chậm và che ranh giới; unit/adapter tests nhiều trường hợp chỉ cần JUnit thuần.

**16. Chỉ test status 200 mà không kiểm tra bytes.** Có thể trả body rỗng/corrupt/nhầm key; dùng assertArrayEquals/content().bytes.

**17. Coi LocalStack giống AWS 100%.** Không chứng minh IAM/KMS, quotas, cross-region, data durability hoặc network production.

**18. Dùng root public writable và nghĩ regex key chống mọi symlink race.** Phải có OS isolation/permissions thật.

**19. Giả định ATOMIC_MOVE luôn được support.** Với network FS có thể không; fallback của ví dụ mất bảo đảm atomic.

**20. Cho rằng NFS/SMB behaves như local @TempDir.** Phải test remote mount permission/locking/outage riêng.

**21. Không đóng S3Client hoặc stream khi test fail.** Rò connection; dùng @AfterAll/try-with-resources/lifecycle bean.

**22. Dùng production credentials/bucket trong CI tests.** Rủi ro dữ liệu/chi phí; dùng isolated credentials/bucket prefix.

**23. Test pass qua fake rồi tuyên bố real S3 đã hoạt động.** Cần adapter contract integration riêng.

**24. Ghi metadata database và object storage trong @Transactional rồi tin atomic.** Không có single JDBC+S3 transaction; cần recovery/compensation.

**25. Không test missing và unavailable riêng.** 404 vs 503 là application contract khác nhau.

**26. Dựa vào order/timing các tests và một bucket chung.** State leakage; tạo keys duy nhất và cleanup.

**27. Không xác định overwrite/versioning policy.** Một fake có thể chấp nhận overwrite nhưng cloud thực yêu cầu conditional request.

**28. Xóa toàn bucket/thư mục để dọn test.** Rất nguy hiểm nếu cấu hình nhầm environment; cleanup theo namespace/test-owned key.

## 29. Checklist QA cuối bài

**Thiết kế boundary:**

- Service chỉ phụ thuộc `BlobStore` port, không import AWS SDK/Files?
- Port xác định put/get, missing/error và overwrite semantics?
- Có tạo key server-side; client filename không thành path/key?
- Adapter bảo vệ key/path và không fallback âm thầm?
- Business validation, authorization, metadata và provider transport được tách đúng layer?

**Unit + HTTP tests:**

- Service unit test dùng real service + mock port, verify bytes/key/errors?
- MockMVC controller test có status 201/200/400/404/503, Location, content-type/body?
- Negative size/key có verify không gọi backend?
- Fake memory có clone data, missing behavior và isolation?
- Full Spring flow dùng controller/service thật và chỉ fake BlobStore?
- Test property `app.storage.provider=memory` có tránh tạo disk/S3 adapter thật?

**Adapter integration:**

- Disk test dùng `@TempDir`, đọc/ghi bytes thật, missing/overwrite/traversal?
- Filesystem root có được phân quyền riêng, không cho attacker sửa symlink?
- LocalStack test dùng S3Client thật, endpoint override, bucket riêng, path-style/region/credentials test?
- Có kiểm tra binary roundtrip + missing key/invalid key?
- Có phân biệt SDK 404 NoSuchKey với permission/network errors?
- Có đóng S3 client và dọn resource lifecycle?
- Test S3 staging bổ sung cho IAM/KMS/presigned URL khi cần?
- Nếu external FS là NFS/SMB, có mount contract test trên resource thật không?

**Tính bền vững + bảo mật:**

- Multipart/body memory/size budget phù hợp? Với file lớn có streaming?
- Có policy MIME, virus scan, filename sanitization, ETag/checksum, metadata?
- Owner/tenant authorization trước GET/PUT, không coi UUID là secret?
- Có timeout/retry/metrics/logging an toàn và phân loại 404/5xx?
- Có idempotency/compensation cho upload + DB metadata?
- Có cleanup theo test-owned keys/prefix, không xóa toàn bucket?
- CI không tự dùng production credentials hoặc ghi sang disk ngoài scope?
- Full suite không bị state leakage, Spring context cache hay parallel tests làm thay đổi kết luận?

**Kết luận:** thay storage ở đúng ranh giới nghĩa là **business/service dùng một port**, unit test chỉ mock/fake port, còn adapter tests kiểm tra **filesystem hoặc S3 API thực** với tài nguyên cô lập. `@TempDir` bảo vệ filesystem test; LocalStack bảo vệ đường SDK/bucket/key; staging contract bảo vệ những hành vi mà emulator không thể đại diện. Không được lấy một màu xanh ở unit/fake test làm bằng chứng cho IAM, network, atomicity hoặc data durability của hệ thống lưu trữ ngoài.

## 30. Tài liệu tham khảo

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slices và MockMvc.
- [Spring Framework — MockitoBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): bean override trong Spring test context.
- [JUnit 5 — @TempDir](https://junit.org/junit5/docs/current/user-guide/#writing-tests-built-in-extensions-TempDirectory): temp directory lifecycle và cleanup.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `Files.move`, `ATOMIC_MOVE`, file reads và IO exceptions.
- [AWS SDK for Java v2 — S3 Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_s3_code_examples.html): PutObject/GetObject và client configuration.
- [Testcontainers Java — LocalStack](https://java.testcontainers.org/modules/localstack/): container S3-compatible, endpointOverride/credentials/region và Testcontainers module.
- [AWS S3 — Consistency Model](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html#ConsistencyModel): consistency behavior không nên suy đoán bằng sleep.
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): validation, filename, malware và access controls.
