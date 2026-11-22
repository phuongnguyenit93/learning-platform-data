# Ghi tập tin với transferTo và quản lý đường dẫn đích trong Spring WebFlux

## 1. Mục tiêu

Trong Spring WebFlux, upload file thường đến dưới dạng request `multipart/form-data`. Server cần đọc part, kiểm tra dữ liệu rồi ghi vào vị trí lưu trữ do ứng dụng kiểm soát. Spring cung cấp `FilePart` để biểu diễn một file trong multipart request. Phương thức `transferTo(Path)` sao chép nội dung file tới đích trên filesystem và trả `Mono<Void>` báo hiệu khi thao tác hoàn tất.

**Đường dẫn đích phải do server quyết định.** Tên file gốc, Content-Type và metadata multipart đều do client gửi. Dùng trực tiếp tên file để tạo path có thể dẫn tới path traversal, ghi đè file khác hoặc lưu dữ liệu vào vị trí không mong muốn.

Bài học tập trung vào:

- Đọc file bằng `@RequestPart FilePart`.
- Ghi bằng `FilePart.transferTo(Path)` và compose completion trong reactive pipeline.
- Tạo path đích an toàn, tách khỏi tên file client.
- Quản lý storage root, staging file, move/commit và cleanup khi lỗi hoặc cancel.
- Phân biệt ngưỡng lưu trong RAM với giới hạn dung lượng upload thực tế.
- Kiểm tra định dạng, quyền truy cập, quota và nội dung độc hại.
- Xử lý upload lớn bằng `Flux<PartEvent>` khi cần streaming.
- Kiểm thử bằng `WebTestClient` hoặc service test.

Ví dụ dùng Java 17+, Spring Boot 3.x/Spring Framework 6.2+ và Reactor. API `FilePart.transferTo(Path)` có từ Spring Framework 5.1.

## 2. Multipart request và FilePart

Một request multipart có thể chứa nhiều part. Mỗi part có tên, headers và nội dung riêng:

```http
POST /api/uploads HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=----upload-boundary

------upload-boundary
Content-Disposition: form-data; name="description"

Quarterly report
------upload-boundary
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

%PDF-1.7
... file bytes ...
------upload-boundary--
```

Các kiểu thường gặp trong WebFlux:

| Kiểu | Ý nghĩa |
| --- | --- |
| `Part` | Một part tổng quát trong multipart request |
| `FilePart` | Một part biểu diễn file upload |
| `FormFieldPart` | Một part biểu diễn field dạng text |
| `PartEvent` | Event của một part trong luồng multipart streaming |
| `DataBuffer` | Vùng byte dùng trong pipeline I/O của Spring |

Controller có thể nhận một file cụ thể:

```java
@PostMapping(
        value = "/api/uploads",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<String> upload(
        @RequestPart("file") FilePart file) {

    return file.transferTo(Path.of("/srv/app/uploads/report.pdf"))
            .thenReturn("uploaded");
}
```

Đây chỉ là **đoạn minh họa API**. Đường dẫn cố định không phù hợp cho nhiều request đồng thời vì có thể ghi đè file. Phần sau thay bằng path do server tạo riêng cho từng upload.

Có thể nhận cả metadata và file:

```java
@PostMapping(
        value = "/api/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<DocumentResponse> upload(
        @RequestPart("metadata") Mono<DocumentMetadata> metadata,
        @RequestPart("file") FilePart file) {

    return metadata.flatMap(data ->
            documentService.store(data, file));
}
```

Spring đọc part metadata và deserialize thành kiểu Java; file được biểu diễn bằng FilePart. Nếu metadata cần Bean Validation, có thể dùng `@Valid @RequestPart("metadata") Mono<DocumentMetadata>` và xử lý lỗi validation trong reactive pipeline hoặc advice phù hợp.

## 3. FilePart.transferTo(Path) hoạt động như thế nào?

Chữ ký chính:

```java
Mono<Void> transferTo(Path destination)
```

Phương thức này sao chép nội dung file của part tới file đích và trả Mono hoàn tất khi transfer xong. Nó không trả byte array hay nội dung file; kết quả là tín hiệu hoàn tất.

Các điểm cần nhớ:

1. Đích là một **file path**, không phải chỉ là thư mục. Server quyết định tên file lưu trữ.
2. Nếu file đích đã tồn tại, nội dung đích sẽ bị truncate trước khi ghi. Không truyền một path có thể trỏ tới file quan trọng hoặc file của request khác.
3. Thư mục cha cần tồn tại và ứng dụng phải có quyền ghi.
4. Mono biểu diễn thao tác; hãy compose nó bằng `then`, `map` hoặc `flatMap` để bước tiếp theo chỉ chạy sau khi transfer hoàn tất.
5. Không gọi `block()` trong controller/service để chờ file được ghi.
6. Không gọi `subscribe()` bên trong controller để chạy upload tách rời HTTP request.

Ví dụ composition:

```java
return file.transferTo(destination)
        .then(Mono.just("stored"));
```

Mono.just("stored") chỉ được phát sau khi transfer hoàn tất. Nếu transfer lỗi, tín hiệu lỗi truyền xuống pipeline và phần then không chạy.

Không viết:

```java
file.transferTo(destination).subscribe();
return Mono.just("stored");
```

Cách trên tạo subscription riêng. Controller có thể trả response trước khi file ghi xong; lỗi ghi file không còn gắn với response, cancellation của client không được liên kết đúng với tác vụ và cleanup khó quản lý.

### 3.1. transferTo không làm tên file client trở nên an toàn

`FilePart.filename()` trả về tên file gốc từ filesystem của client. Tài liệu Spring cảnh báo giá trị này do client cung cấp, có thể chứa phần thư mục, `..` hoặc ký tự có thể bị lợi dụng. Không sử dụng trực tiếp nó làm path.

Ví dụ tên file có thể là:

- `report.pdf`
- `../../application.yml`
- `../private/secret.txt`
- Đường dẫn tuyệt đối theo hệ điều hành của client.
- Tên chứa ký tự điều khiển, dấu phân cách thư mục hoặc tên quá dài.

Không giả định browser luôn gửi basename sạch. Client có thể là script hoặc công cụ HTTP tự tạo multipart header.

**Khuyến nghị:** sinh tên lưu trữ mới bằng UUID hoặc ID do server quản lý. Nếu nghiệp vụ cần giữ tên gốc để hiển thị, lưu nó như metadata đã được làm sạch; không dùng metadata đó để quyết định vị trí ghi file.

## 4. Thiết kế thư mục lưu trữ

Trước khi viết code, xác định nơi lưu file:

- Đặt ngoài webroot/static resource directory để web server không tự động public hoặc thực thi file.
- Dùng thư mục chỉ tài khoản chạy ứng dụng mới có quyền ghi; quyền đọc cũng giới hạn theo nhu cầu.
- Nếu cần lưu lâu dài, chọn volume/disk persistent; không dùng thư mục tạm của hệ điều hành làm nơi lưu cuối cùng.
- Tách staging và thư mục đã được chấp nhận nếu có bước kiểm tra hoặc antivirus scan.
- Theo dõi dung lượng, số lượng file, tuổi file tạm và quota theo user/tenant.
- Có chính sách backup, retention và xóa file khi dữ liệu nghiệp vụ bị xóa.

Ví dụ cấu hình:

```properties
app.upload.storage-root=/var/lib/myapp/uploads
```

Trong môi trường local có thể dùng thư mục riêng của dự án. Production nên dùng path được cấu hình theo môi trường, có quyền filesystem rõ ràng và nằm ngoài thư mục public.

Không nên lưu file upload vào `src/main/resources/static`, thư mục chứa cấu hình/secrets, thư mục có thể thực thi file hoặc path do client gửi lên. Nếu ứng dụng chạy nhiều instance, filesystem local của một instance có thể không chia sẻ với instance khác. Khi đó cần shared volume hoặc object storage; database lưu metadata và storage key.

## 5. Quản lý đường dẫn đích an toàn

### 5.1. Không nối chuỗi từ filename

Mẫu nguy hiểm:

```java
Path destination = uploadRoot.resolve(file.filename());
return file.transferTo(destination);
```

Nếu filename chứa đường dẫn traversal hoặc path tuyệt đối, đích có thể nằm ngoài uploadRoot. Hai request cùng tên cũng có thể ghi đè file của nhau.

Không nên chỉ loại bỏ chuỗi `../` bằng replace hoặc regex. Path traversal có nhiều cách biểu diễn tùy hệ điều hành, URL decoding, dấu phân cách và filesystem.

### 5.2. Tạo tên server-side

Cách đơn giản:

```java
String id = UUID.randomUUID().toString();
Path destination = uploadRoot.resolve(id + ".bin");
```

Client không điều khiển ID. Có thể lưu mapping ID → tên gốc đã làm sạch trong database nếu cần hiển thị hoặc tải file.

Nếu chỉ cho phép một loại file, có thể dùng extension cố định do server quyết định sau khi xác minh nội dung, ví dụ `.pdf`. Không lấy extension trực tiếp từ tên client rồi tin rằng file thật sự là PDF.

### 5.3. Chuẩn hóa và kiểm tra path

Khi cần resolve relative path, có thể dùng:

```java
Path root = uploadRoot.toAbsolutePath().normalize();
Path candidate = root.resolve(relativeName).normalize();

if (!candidate.startsWith(root)) {
    throw new IllegalArgumentException("Invalid destination path");
}
```

`Path.startsWith(Path)` so sánh theo thành phần path, tốt hơn so sánh chuỗi bằng `String.startsWith`. `normalize()` loại bỏ thành phần `.` và `..` ở mức từ vựng.

Tuy nhiên, normalize không tự giải quyết mọi vấn đề symlink. Một thư mục con có thể là symbolic link trỏ ra ngoài root. `toRealPath()` resolve đường dẫn thực tế của các thành phần đã tồn tại, nhưng nếu user khác có quyền thay đổi thư mục trong lúc kiểm tra và ghi thì vẫn có nguy cơ race condition.

Cách dễ kiểm soát nhất cho upload là **không nhận relative path hoặc filename từ client**. Dùng root riêng, quyền filesystem chặt và path do server tạo. Nếu có thư mục theo tenant, lấy tenant ID từ principal đã xác thực, không lấy tùy ý từ form field.

### 5.4. Mỗi lần upload có một staging directory riêng

Một cách tốt là tạo thư mục tạm duy nhất bên dưới storage root:

```java
Path uploadDirectory = Files.createTempDirectory(realRoot, "upload-");
Path staging = uploadDirectory.resolve("payload.part");
Path destination = uploadDirectory.resolve("payload.pdf");
```

Mỗi lần gọi tạo directory mới. FilePart chỉ ghi vào `payload.part`. Sau khi transfer và validation thành công, server move file thành `payload.pdf` trong cùng thư mục.

Lợi ích:

- Request khác không dùng chung staging path.
- Không dựa vào filename client.
- Có thể cleanup toàn bộ thư mục nếu upload lỗi.
- Có thể promote file sau khi kiểm tra.
- Destination nằm cùng filesystem với staging, thuận lợi cho atomic move nếu filesystem hỗ trợ.

Storage root phải là thư mục riêng mà chỉ ứng dụng hoặc tiến trình tin cậy có quyền tạo/xóa nội dung. Tạo path trong thư mục public hoặc writable bởi user không tin cậy có thể làm mất ý nghĩa của các kiểm tra trên.

## 6. transferTo ghi đè file đích: xử lý thế nào?

Theo Javadoc của FilePart, nếu destination đã tồn tại, transferTo sẽ truncate nội dung file đó trước khi ghi. Đây là hành vi cần chủ động tính đến.

| Chiến lược | Cách làm | Khi phù hợp |
| --- | --- | --- |
| Tên duy nhất | Tạo ID mới cho mỗi upload | Mặc định nên dùng |
| Ghi đè có kiểm soát | Kiểm tra quyền và policy rồi thay thế resource cụ thể | API cập nhật file đã tồn tại |
| Staging rồi promote | Ghi file tạm, kiểm tra, sau đó move sang tên cuối | File cần validation hoặc không muốn lộ file chưa hoàn tất |

Không dùng tên file do client gửi làm cơ chế chọn file bị ghi đè. Nếu có API thay thế file, hãy dùng ID resource do server quản lý, xác thực user có quyền sửa resource đó và kiểm tra version/concurrency nếu cần.

### 6.1. Ghi vào staging trước

Luồng xử lý:

1. Tạo thư mục upload riêng.
2. Tạo file staging do server đặt tên.
3. Gọi `file.transferTo(stagingPath)`.
4. Sau khi transfer hoàn tất, kiểm tra kích thước và định dạng.
5. Nếu hợp lệ, move staging sang destination cuối.
6. Nếu không hợp lệ hoặc có lỗi, xóa staging và thư mục tạm.
7. Chỉ công bố metadata/file ID sau khi file đã được promote.

Đừng trả file ID ở trạng thái “đã lưu” trước khi transfer hoàn tất. Nếu cần workflow nhiều bước, lưu trạng thái `UPLOADING`, `SCANNING`, `AVAILABLE` hoặc `REJECTED` trong database.

### 6.2. Atomic move

Khi staging và destination nằm trên cùng filesystem, có thể thử:

```java
Files.move(
        stagingPath,
        destinationPath,
        StandardCopyOption.ATOMIC_MOVE);
```

Nếu filesystem không hỗ trợ atomic move, Java có thể ném `AtomicMoveNotSupportedException`. Ứng dụng có thể fallback sang `Files.move(staging, destination)` nếu policy cho phép.

Atomic move giúp reader không nhìn thấy file đang ghi dở ở path cuối. Tuy nhiên, semantics khi destination đã tồn tại có thể phụ thuộc provider khi dùng ATOMIC_MOVE. Hãy tạo destination trong thư mục riêng mới, bảo đảm nó chưa tồn tại và không có tiến trình không tin cậy ghi vào thư mục đó.

Không dùng `REPLACE_EXISTING` trừ khi việc thay thế file đã được cho phép rõ ràng. Nếu fallback move không atomic, không quảng bá nó như atomic commit.

## 7. Ví dụ hoàn chỉnh: upload PDF với tên server-side

Ví dụ nhận một file PDF, ghi vào staging directory duy nhất, kiểm tra kích thước và chữ ký PDF tối thiểu, rồi promote sang tên cố định do server quyết định.

**Giới hạn của kiểm tra PDF:** kiểm tra prefix `%PDF-` chỉ là phép kiểm tra sơ bộ. Nó không chứng minh tài liệu PDF an toàn hoặc hợp lệ hoàn toàn. Production cần parser/validator phù hợp, antivirus hoặc sandbox/CDR nếu yêu cầu bảo mật.

### 7.1. Cấu hình

Tệp `src/main/resources/application.properties`:

```properties
app.upload.storage-root=/var/lib/myapp/uploads
```

Thư mục này phải nằm ngoài webroot, tồn tại được qua restart và chỉ cho tài khoản ứng dụng có quyền ghi cần thiết.

### 7.2. Multipart limits

Multipart parser có các giới hạn riêng. Có thể cấu hình reader:

```java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.http.codec.multipart.DefaultPartHttpMessageReader;
import org.springframework.http.codec.multipart.MultipartHttpMessageReader;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration(proxyBeanMethods = false)
public class MultipartUploadConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        DefaultPartHttpMessageReader partReader =
                new DefaultPartHttpMessageReader();

        partReader.setMaxInMemorySize(256 * 1024);
        partReader.setMaxDiskUsagePerPart(12L * 1024 * 1024);
        partReader.setMaxParts(5);
        partReader.setMaxHeadersSize(10 * 1024);

        configurer.defaultCodecs().multipartReader(
                new MultipartHttpMessageReader(partReader));
    }
}
```

Giải thích:

- `maxInMemorySize(256 KiB)` là ngưỡng giữ part trong RAM. File part vượt ngưỡng được ghi vào thư mục tạm; đây **không phải** giới hạn upload tối đa.
- `maxDiskUsagePerPart(12 MiB)` giới hạn dung lượng disk cho mỗi file part trong reader.
- `maxParts(5)` giới hạn tổng số part trong multipart request.
- `maxHeadersSize(10 KiB)` giới hạn phần headers của mỗi part.

Mặc định `maxInMemorySize` của DefaultPartHttpMessageReader là 256 KiB; `maxDiskUsagePerPart` và `maxParts` mặc định không giới hạn. Khi tăng memory/disk limits, phải tính tổng số request đồng thời và dung lượng temp disk.

Trong ví dụ, service chỉ chấp nhận PDF tối đa 10 MiB. Reader cho phép tối đa 12 MiB mỗi part để service có thể trả lỗi nghiệp vụ rõ ràng ở ngưỡng 10 MiB; request lớn hơn 12 MiB bị chặn ở tầng multipart parser. Gateway/reverse proxy vẫn cần giới hạn tổng request body, vì multipart có thể chứa nhiều part và overhead.

Nếu dùng Spring Boot, `WebFluxConfigurer` thông thường không cần kèm `@EnableWebFlux`; bỏ annotation đó để giữ các tùy chỉnh auto-configuration của Boot.

### 7.3. UploadService

Tệp `src/main/java/demo/UploadService.java`:

```java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class UploadService {

    private static final long MAX_PDF_BYTES = 10L * 1024 * 1024;

    private static final byte[] PDF_MAGIC =
            "%PDF-".getBytes(StandardCharsets.US_ASCII);

    private final Path storageRoot;

    public UploadService(Environment environment) {
        this(Path.of(environment.getRequiredProperty(
                "app.upload.storage-root")));
    }

    UploadService(Path storageRoot) {
        this.storageRoot = storageRoot.toAbsolutePath().normalize();
    }

    public Mono<StoredUpload> store(FilePart file) {
        return Mono.usingWhen(
                Mono.fromCallable(this::createPaths)
                        .subscribeOn(Schedulers.boundedElastic()),

                paths -> file.transferTo(paths.staging())
                        .then(Mono.fromCallable(
                                () -> validateAndPromote(paths))
                                .subscribeOn(Schedulers.boundedElastic())),

                paths -> Mono.empty(),

                (paths, error) -> cleanup(paths),

                this::cleanup
        );
    }

    private UploadPaths createPaths() throws IOException {
        Files.createDirectories(storageRoot);
        Path realRoot = storageRoot.toRealPath();

        Path directory = Files.createTempDirectory(
                realRoot, "upload-");

        Path staging = directory.resolve("payload.part");
        Path destination = directory.resolve("payload.pdf");

        try {
            Files.createFile(staging);
        } catch (IOException error) {
            Files.deleteIfExists(directory);
            throw error;
        }

        return new UploadPaths(
                directory,
                staging,
                destination,
                new AtomicBoolean(false));
    }

    private StoredUpload validateAndPromote(
            UploadPaths paths) throws IOException {

        long size = Files.size(paths.staging());

        if (size == 0 || size > MAX_PDF_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.PAYLOAD_TOO_LARGE,
                    "PDF must be between 1 byte and 10 MiB");
        }

        try (InputStream input =
                     Files.newInputStream(paths.staging())) {

            byte[] prefix = input.readNBytes(PDF_MAGIC.length);

            if (!Arrays.equals(prefix, PDF_MAGIC)) {
                throw new ResponseStatusException(
                        HttpStatus.UNSUPPORTED_MEDIA_TYPE,
                        "Only PDF content is accepted");
            }
        }

        try {
            Files.move(
                    paths.staging(),
                    paths.destination(),
                    StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException error) {
            Files.move(paths.staging(), paths.destination());
        }

        paths.committed().set(true);

        String id = paths.directory().getFileName().toString();
        return new StoredUpload(id, size);
    }

    private Mono<Void> cleanup(UploadPaths paths) {
        return Mono.fromCallable(() -> {
                    if (!paths.committed().get()) {
                        Files.deleteIfExists(paths.staging());
                        Files.deleteIfExists(paths.destination());
                        Files.deleteIfExists(paths.directory());
                    }
                    return Boolean.TRUE;
                })
                .subscribeOn(Schedulers.boundedElastic())
                .then();
    }

    private record UploadPaths(
            Path directory,
            Path staging,
            Path destination,
            AtomicBoolean committed) {
    }

    public record StoredUpload(String id, long size) {
    }
}
```

Điểm quan trọng:

- Constructor nhận storage root từ cấu hình, không nhận path từ request.
- `createPaths()` tạo root, resolve root thật bằng `toRealPath()` và tạo thư mục riêng bằng `createTempDirectory()`.
- FilePart chỉ ghi vào `payload.part` do server tạo.
- Sau transfer, service đọc kích thước và signature trong thao tác được schedule trên boundedElastic.
- Khi hợp lệ, staging được move thành `payload.pdf`.
- `AtomicBoolean committed` phân biệt file đã promote với file tạm cần xóa.
- `Mono.usingWhen` gọi cleanup khi pipeline lỗi hoặc bị cancel.
- Các thao tác filesystem đồng bộ như tạo thư mục, đọc signature, move và delete được cô lập trên `Schedulers.boundedElastic()`.

FilePart.transferTo trả về Mono nên được compose trực tiếp. Không bọc nó trong `Mono.fromCallable(() -> file.transferTo(...).block())`; cách đó block và phá reactive lifecycle.

**Về cleanup:** nếu ứng dụng bị kill đột ngột hoặc máy mất điện, callback reactive không thể chạy. Production nên có tác vụ định kỳ dọn các thư mục `upload-*` chưa được commit và đã quá TTL, đồng thời giữ trạng thái upload trong database nếu cần phục hồi.

### 7.4. Controller

Tệp `src/main/java/demo/UploadController.java`:

```java
package demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    private final UploadService uploadService;

    public UploadController(UploadService uploadService) {
        this.uploadService = uploadService;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<ResponseEntity<UploadResponse>> upload(
            @RequestPart("file") FilePart file) {

        return uploadService.store(file)
                .map(saved -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(new UploadResponse(
                                saved.id(), saved.size())));
    }

    public record UploadResponse(String id, long size) {
    }
}
```

Controller không tạo path từ filename, không đọc file thành byte array và không block. Nó giao FilePart cho service, rồi tạo response sau khi service phát StoredUpload.

Response body chứa ID do server sinh và kích thước file. Không phản hồi trực tiếp filename thô từ client. Nếu cần tên gốc, lưu như metadata đã làm sạch và áp dụng encoding khi hiển thị.

### 7.5. Gọi endpoint bằng curl

Tạo một PDF thử nghiệm `sample.pdf` rồi chạy:

```bash
curl -i -X POST http://localhost:8080/api/uploads   -F "file=@sample.pdf;type=application/pdf"
```

Response thành công có status 201 và JSON tương tự:

```json
{
  "id": "upload-<generated-id>",
  "size": 842
}
```

Giá trị ID và size phụ thuộc lần upload thật. Server lưu file trong thư mục do ứng dụng quản lý, với tên nội bộ `payload.pdf`. Client không quyết định path hay tên file cuối.

Gửi file không phải PDF sẽ nhận 415 Unsupported Media Type theo ví dụ. File vượt ngưỡng 10 MiB bị service từ chối; file vượt multipart parser limit 12 MiB bị từ chối trước khi service hoàn tất. Gateway/server cũng cần giới hạn tổng request.

## 8. Kiểm thử service và đường dẫn đích

Nên kiểm tra:

- File hợp lệ được ghi vào thư mục do server sinh.
- Hai lần upload tạo ID/thư mục khác nhau.
- File sai signature bị từ chối và staging được xóa.
- File vượt kích thước bị từ chối.
- Lỗi transfer không để lại staging file.
- Cancel trong lúc upload có cleanup phù hợp.
- Không có filename/path client nào được dùng làm destination.
- Root storage không nằm trong webroot và không thể truy cập trực tiếp.

Ví dụ unit test cho service, dùng Mockito giả lập FilePart.transferTo:

Tệp `src/test/java/demo/UploadServiceTest.java`:

```java
package demo;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class UploadServiceTest {

    @TempDir
    Path tempDir;

    @Test
    void storesPdfInGeneratedDirectory() throws Exception {
        Path source = Files.writeString(
                tempDir.resolve("source.pdf"),
                "%PDF-1.7
sample content");

        Path storageRoot = tempDir.resolve("uploads");
        FilePart filePart = mock(FilePart.class);

        when(filePart.transferTo(any(Path.class)))
                .thenAnswer(invocation -> {
                    Path destination = invocation.getArgument(0);

                    return Mono.fromCallable(() ->
                                    Files.copy(
                                            source,
                                            destination,
                                            StandardCopyOption.REPLACE_EXISTING))
                            .subscribeOn(Schedulers.boundedElastic())
                            .then();
                });

        UploadService service = new UploadService(storageRoot);
        AtomicReference<UploadService.StoredUpload> saved =
                new AtomicReference<>();

        StepVerifier.create(service.store(filePart))
                .assertNext(saved::set)
                .verifyComplete();

        assertTrue(saved.get().size() > 0);

        Path storedFile = storageRoot
                .resolve(saved.get().id())
                .resolve("payload.pdf");

        assertEquals(
                "%PDF-1.7
sample content",
                Files.readString(storedFile));
    }

    @Test
    void rejectsInvalidSignatureAndCleansStaging() throws Exception {
        Path source = Files.writeString(
                tempDir.resolve("invalid.pdf"),
                "not a PDF");

        Path storageRoot = tempDir.resolve("uploads");
        FilePart filePart = mock(FilePart.class);

        when(filePart.transferTo(any(Path.class)))
                .thenAnswer(invocation -> {
                    Path destination = invocation.getArgument(0);

                    return Mono.fromCallable(() ->
                                    Files.copy(
                                            source,
                                            destination,
                                            StandardCopyOption.REPLACE_EXISTING))
                            .subscribeOn(Schedulers.boundedElastic())
                            .then();
                });

        UploadService service = new UploadService(storageRoot);

        StepVerifier.create(service.store(filePart))
                .expectError(ResponseStatusException.class)
                .verify();

        try (Stream<Path> entries = Files.list(storageRoot)) {
            assertEquals(0, entries.count());
        }
    }
}
```

Test tập trung vào service và path management. Mockito giả lập transferTo bằng cách copy một file local vào staging path do service truyền vào. Test không thay thế kiểm thử tích hợp multipart parser; endpoint thật nên có thêm WebTestClient test cho việc resolve `@RequestPart("file")`, status response và giới hạn request.

Test cần JUnit Jupiter, Mockito, reactor-test và Spring WebFlux trên test classpath. `spring-boot-starter-test` trong dự án Spring Boot thường cung cấp các thư viện test cần thiết; `reactor-test` có thể cần khai báo riêng nếu project chưa đưa vào.

## 9. Multipart parser: RAM threshold không phải upload limit

Một nhầm lẫn phổ biến là nghĩ `maxInMemorySize=256 KiB` có nghĩa file lớn hơn 256 KiB bị từ chối. Với DefaultPartHttpMessageReader:

- Non-file part vượt ngưỡng bộ nhớ có thể bị từ chối bằng DataBufferLimitException.
- File part vượt ngưỡng được ghi ra thư mục tạm trên disk.
- `maxDiskUsagePerPart` đặt giới hạn dung lượng disk cho mỗi file part.
- `maxParts` giới hạn số part trong request.
- `fileStorageDirectory` thay đổi thư mục tạm dùng để lưu part lớn.
- `setBlockingOperationScheduler(...)` có thể thay scheduler dùng cho thao tác file/directory; mặc định dùng boundedElastic.

Phân biệt các giới hạn:

| Cấu hình/biện pháp | Giới hạn |
| --- | --- |
| maxInMemorySize | Số byte một part được giữ trong RAM trước khi file part chuyển sang disk |
| maxDiskUsagePerPart | Disk usage tối đa cho mỗi file part trong reader |
| maxParts | Tổng số part của một multipart request |
| Service MAX_FILE_SIZE | Kích thước file được nghiệp vụ chấp nhận sau transfer |
| Reverse proxy/request limit | Tổng kích thước HTTP request trước khi ứng dụng xử lý |
| User quota | Tổng dung lượng hoặc số file một user/tenant được lưu |
| Concurrency/rate limit | Số upload đồng thời và tần suất upload |

Kiểm tra kích thước sau transfer giúp quyết định file có được promote hay không, nhưng **không tự ngăn việc đã tiêu tốn disk trong lúc nhận upload**. Cần giới hạn parser, gateway và quota để chống cạn tài nguyên.

Nếu muốn đổi thư mục temp multipart, cấu hình `DefaultPartHttpMessageReader.setFileStorageDirectory(Path)`. Thư mục temp nên nằm trên volume có dung lượng được giám sát, quyền truy cập hạn chế và chính sách cleanup.

## 10. Upload file lớn: khi nào dùng PartEvent?

`FilePart` thuận tiện khi cần một file đã được parser nhận diện và ghi tới path. Với upload rất lớn hoặc cần xử lý từng phần theo thứ tự, WebFlux hỗ trợ streaming multipart qua:

```java
@RequestBody Flux<PartEvent>
```

Mỗi part tạo một hoặc nhiều PartEvent. Form field thường tạo một FormPartEvent; file lớn có thể được chia thành nhiều FilePartEvent và nhiều DataBuffer. Event cuối của một part có `isLast() = true`.

Cấu trúc xử lý thường dùng:

```java
@PostMapping(
        value = "/api/stream-upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<Void> uploadStream(
        @RequestBody Flux<PartEvent> allPartEvents) {

    return allPartEvents
            .windowUntil(PartEvent::isLast)
            .concatMap(partEvents ->
                    partEvents.switchOnFirst((signal, samePart) -> {
                        if (!signal.hasValue()) {
                            return samePart.then();
                        }

                        PartEvent first = signal.get();

                        if (first instanceof FormPartEvent form) {
                            return saveField(form.name(), form.value())
                                    .then(samePart.then());
                        }

                        if (first instanceof FilePartEvent file) {
                            Flux<DataBuffer> content =
                                    samePart.map(PartEvent::content);

                            return streamToStorage(
                                    file.filename(), content);
                        }

                        return Mono.error(
                                new IllegalArgumentException(
                                        "Unsupported multipart part"));
                    }))
            .then();
}
```

Đây là **mã khung**: `saveField(...)` và `streamToStorage(...)` do ứng dụng định nghĩa. Method ghi stream phải tiêu thụ, relay hoặc release tất cả DataBuffer nhận được. Không bỏ qua buffer của part bị từ chối; nếu không có thể gây memory leak, đặc biệt trên Netty với pooled DataBuffer.

| FilePart.transferTo | Flux<PartEvent> |
| --- | --- |
| Dễ dùng cho một file part đã được resolve | Xử lý từng part/event theo luồng |
| Parser quản lý multipart part và có thể spool file part sang temp | Ứng dụng kiểm soát việc tiêu thụ từng buffer |
| Gọi transferTo để ghi file vào path | Compose sink ghi DataBuffer hoặc relay sang dịch vụ khác |
| Phù hợp phần lớn upload form thông thường | Phù hợp streaming lớn, nhiều part hoặc relay |
| Ít code quản lý buffer hơn | Cần quản lý buffer, backpressure và cleanup cẩn thận hơn |

Nếu không cần xử lý multipart theo từng event, ưu tiên FilePart. Đừng dùng PartEvent chỉ vì endpoint đang dùng WebFlux; streaming API đòi hỏi code xử lý buffer chính xác hơn.

## 11. DataBuffer ownership và cleanup

Khi sử dụng FilePart.transferTo, Spring quản lý việc đọc/ghi nội dung part thông qua implementation của FilePart và DataBuffer. Ứng dụng thường không cần tự release từng buffer.

Nếu truy cập `file.content()` hoặc xử lý PartEvent trực tiếp, cần hiểu ownership:

- Một DataBuffer có thể bọc pooled memory và reference-counted buffer.
- Buffer đã tiêu thụ cần được release đúng lúc.
- Buffer bị loại bỏ bởi filter, error hoặc cancellation cũng cần cleanup.
- Không release buffer sau khi đã chuyển ownership cho writer/sink khác.
- Không đọc buffer sau khi nó đã được release.
- Khi relay stream, bảo đảm downstream tiêu thụ toàn bộ buffer hoặc có cleanup khi lỗi/cancel.

`Part.delete()` trả về Mono để xóa storage nền của part. API này hữu ích khi ứng dụng chủ động quản lý lifecycle của Part; chỉ gọi sau khi không còn cần nội dung part. Không xóa part trước khi transfer hoặc trước khi consumer hoàn tất.

Với custom streaming code, test cả success, error và cancellation. Chỉ test happy path có thể bỏ sót leak xảy ra khi client disconnect giữa chừng.

## 12. Kiểm tra file trước khi công bố

Không tin các metadata sau:

- `FilePart.filename()`: tên do client gửi.
- `file.headers().getContentType()`: MIME type do client khai báo.
- Extension trong tên file: có thể giả mạo hoặc chứa double extension.
- Kích thước do client khai báo trong part header: không thay thế việc kiểm tra số byte thật.

Quy trình kiểm tra nhiều lớp:

1. **Authentication/authorization:** user có quyền upload vào resource/tenant này không?
2. **Filename policy:** tạo storage key mới; giới hạn và làm sạch tên hiển thị nếu cần lưu.
3. **Size policy:** giới hạn ở proxy, multipart reader, service và quota.
4. **Extension allowlist:** chỉ nhận loại file nghiệp vụ cần.
5. **Content-Type quick check:** hữu ích để báo lỗi client, nhưng không phải bằng chứng.
6. **Magic bytes/signature:** kiểm tra nội dung thực tế theo format; không dùng một mình.
7. **Parser validation:** mở/parse bằng thư viện phù hợp và có giới hạn CPU/memory.
8. **Antivirus/sandbox/CDR:** áp dụng theo mức rủi ro và loại file.
9. **Storage policy:** ngoài webroot, không thực thi file upload, quyền tối thiểu.
10. **Download policy:** truy cập qua endpoint có authorization và ID do server quản lý.

Ví dụ service kiểm tra `%PDF-` chỉ để minh họa. Signature check không chứng minh file không có payload độc hại; PDF vẫn có thể chứa JavaScript, embedded files hoặc cấu trúc khai thác parser. Dữ liệu cần công bố cho user khác nên được quét/kiểm tra trước khi chuyển sang trạng thái AVAILABLE.

Nếu file được xử lý bằng ZIP, XML, image hoặc document parser, giới hạn tài nguyên cho quá trình giải nén/parse riêng. Một file nhỏ có thể bung thành payload rất lớn (zip bomb) hoặc làm parser tốn CPU/memory.

## 13. Tránh path traversal và ghi đè

### 13.1. Ví dụ tấn công

Giả sử server dùng:

```java
Path destination = storageRoot.resolve(file.filename());
file.transferTo(destination);
```

Client có thể gửi filename chứa `../` để cố ghi file ra ngoài upload directory. Một path tuyệt đối cũng có thể làm resolve bỏ qua root. Trên Windows, dấu phân cách và drive letter có cách biểu diễn khác Linux.

Ngay cả khi dùng basename, vẫn còn rủi ro:

- Tên file có thể trùng với file đã tồn tại.
- Tên có ký tự điều khiển hoặc ký tự đặc biệt.
- Unicode normalization có thể tạo tên nhìn giống nhau.
- Case-insensitive filesystem có thể xem hai tên khác chữ hoa/thường là cùng file.
- Symbolic link trong thư mục con có thể trỏ ra ngoài root.
- Một user có thể upload file với tên có ý nghĩa đặc biệt với web server.

### 13.2. Cách phòng vệ

- Sinh ID/filename bằng UUID hoặc key storage ngẫu nhiên.
- Không cho client truyền destination path.
- Lưu storage root trong cấu hình server, không lấy từ request.
- Dùng thư mục riêng, không cho user không tin cậy ghi vào đó.
- Dùng path component checks nếu có resolve path.
- Không cho upload directory thực thi file.
- Lưu metadata gốc trong database, tách khỏi path vật lý.
- Nếu file trùng hoặc update resource, dùng business ID và policy rõ ràng.
- Không public file bằng cách nối filename vào URL filesystem.

### 13.3. Path check không thay thế quyền filesystem

`normalize()` và `startsWith(root)` hữu ích để ngăn path traversal dạng lexical. Nhưng nếu thư mục có symlink do user khác kiểm soát hoặc có race giữa check và write, vẫn có thể thoát root.

Đảm bảo root và các thư mục con chỉ được tiến trình tin cậy quản lý. Với môi trường có nhiều process/user cùng ghi, cần thiết kế quyền và atomic creation phù hợp; không dựa vào một phép kiểm tra chuỗi đơn lẻ.

## 14. Xử lý lỗi và trạng thái upload

| Tình huống | Status thường dùng | Hành động |
| --- | --- | --- |
| Thiếu part file | 400 Bad Request | Báo thiếu trường file |
| Content-Type request không phải multipart | 415 Unsupported Media Type | Client sửa request |
| File part vượt parser disk limit | Request bị từ chối ở tầng multipart | Ghi nhận lỗi upload quá lớn |
| File vượt business max size | 413 Payload Too Large | Xóa staging |
| File sai định dạng được phép | 415 hoặc 422 theo API contract | Xóa staging |
| User không có quyền upload | 403 Forbidden | Không ghi file |
| Storage disk đầy hoặc permission denied | 5xx | Log nội bộ, không trả filesystem path |
| Virus scan thất bại | 422 hoặc status theo contract | Giữ trạng thái quarantine/reject |
| Client disconnect/cancel | Không có response hoàn chỉnh | Dọn staging và theo dõi orphan files |

Không trả đường dẫn filesystem tuyệt đối hoặc stack trace cho client. Log nên ghi upload ID, user/tenant ID đã được phép, size, error code và trạng thái; không log session cookie, token hoặc toàn bộ nội dung file.

Nếu upload cần bước scan bất đồng bộ, API có thể trả 202 Accepted và job ID, sau đó client poll trạng thái. Chỉ trả 201/AVAILABLE khi file đã được ghi và qua các bước cần thiết theo contract.

## 15. Đọc và phục vụ file đã upload

Đừng public thư mục lưu trữ như static resources. Nếu user cần tải file, cung cấp endpoint theo ID:

```http
GET /api/uploads/{uploadId}
```

Server nên:

1. Xác thực user.
2. Kiểm tra quyền truy cập upload ID.
3. Lấy storage key từ database hoặc metadata tin cậy.
4. Resolve path bên trong storage root.
5. Kiểm tra file tồn tại và policy download.
6. Trả Content-Type phù hợp, Content-Disposition an toàn và cache policy đúng.

Không nhận filename tùy ý từ query rồi đọc trực tiếp file trên disk. ID công khai cũng không thay thế authorization; UUID khó đoán chỉ là một lớp giảm khả năng enumeration.

Nếu cần phục vụ file lớn, dùng Resource hoặc streaming response phù hợp thay vì đọc toàn bộ vào byte array. Đặt giới hạn download và hỗ trợ range nếu nghiệp vụ cần resume.

## 16. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng filename client làm destination | Path traversal hoặc ghi đè file | Sinh UUID/storage key phía server |
| Dùng một destination cố định | Nhiều request ghi đè nhau | Tạo staging directory riêng cho từng upload |
| Nghĩ transferTo không ghi đè | File đích đã tồn tại sẽ bị truncate | Tạo file đích duy nhất và kiểm soát overwrite |
| Gọi transferTo().subscribe() rồi trả response | Response có thể hoàn tất trước khi file ghi xong | Compose Mono và return từ controller |
| Gọi block() để chờ ghi file | Chặn thread reactive | Dùng then/flatMap và để WebFlux subscribe |
| Không tạo thư mục cha | Transfer thất bại do path không hợp lệ | Tạo root/staging directory trước transfer |
| Dùng normalize như biện pháp duy nhất | Không xử lý được mọi symlink/race | Dùng root riêng, server-generated path và quyền filesystem |
| Tin Content-Type của client | File giả MIME type vẫn lọt | Kiểm tra signature/parser và allowlist |
| Chỉ kiểm tra extension | Có thể bị double extension hoặc file giả | Kiểm tra nội dung thực và scan |
| Nghĩ 256 KiB là giới hạn upload | File lớn có thể được spool ra disk | Cấu hình maxDiskUsagePerPart và request limit |
| Chỉ giới hạn service sau khi ghi | Disk đã bị dùng trước khi từ chối | Chặn ở proxy/parser và quota |
| Không cleanup khi error/cancel | File staging rác hoặc temp disk đầy | usingWhen cleanup và janitor cho crash recovery |
| Ghi file vào webroot | File có thể bị public hoặc thực thi | Lưu ngoài webroot và download qua handler có auth |
| Đọc toàn bộ file thành byte[] | Tăng heap và dễ OOM | Dùng transferTo hoặc streaming PartEvent |
| Tự đọc DataBuffer nhưng không release | Leak direct/pooled memory | Quản lý ownership và cleanup mọi path |
| Không giới hạn số part | Multipart request có thể tạo nhiều file/field | maxParts và giới hạn gateway |
| Cho user tự chọn tenant directory | Có thể ghi vào thư mục user khác | Lấy tenant từ principal đã xác thực |
| Chỉ test success | Bỏ sót cleanup/error/cancel | Test transfer fail, invalid content, size và cancellation |

## 17. Checklist triển khai upload an toàn

1. Endpoint có consumes `multipart/form-data` và nhận đúng part bằng `@RequestPart("file") FilePart`.
2. Destination được tạo từ storage root do server cấu hình.
3. Không dùng filename/path client làm destination.
4. Tạo thư mục riêng cho từng upload hoặc staging key duy nhất.
5. Tạo thư mục cha trước khi gọi transferTo.
6. Compose publisher bằng then/flatMap; không block/subscribe thủ công.
7. Không để transferTo ghi vào file quan trọng hoặc file request khác có thể chọn.
8. Kiểm tra kích thước, loại file và nội dung trước khi promote.
9. Giới hạn memory threshold, disk per part, max parts, total request size và quota.
10. Lưu file ngoài webroot, quyền filesystem tối thiểu.
11. Cleanup staging khi error/cancel và có job dọn orphan sau crash.
12. Nếu cần streaming, dùng PartEvent và tiêu thụ/relay/release tất cả DataBuffer.
13. Lưu metadata gốc tách khỏi storage key; không trả path filesystem cho client.
14. Kiểm tra authorization khi upload và khi download.
15. Test nhiều upload đồng thời, tên file trùng, path traversal, file giả MIME, file quá lớn và lỗi storage.

## 18. Tài liệu tham khảo

- [Spring Framework – Multipart Content trong WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html): FilePart, @RequestPart, multipart map và streaming PartEvent.
- [FilePart Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/FilePart.html): filename(), transferTo(File/Path), destination truncation và cảnh báo filename do client cung cấp.
- [Part Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/Part.html): content(), headers(), name() và delete().
- [DefaultPartHttpMessageReader Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html): maxInMemorySize, maxDiskUsagePerPart, maxParts, temp directory và scheduler.
- [MultipartHttpMessageReader Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/multipart/MultipartHttpMessageReader.html): đọc multipart thành MultiValueMap.
- [Spring Framework – Reactive Core / Multipart Limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): memory threshold, disk limit và multipart parts.
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html): filename, extension/content validation, storage location, upload limits và file scanning.
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): xử lý dữ liệu không tin cậy và validation nhiều lớp.

## 19. Ghi nhớ

`FilePart.transferTo(Path)` là cách tiện lợi để ghi nội dung file multipart trong WebFlux. Nó trả `Mono<Void>`, vì vậy hãy compose completion trong reactive pipeline và để WebFlux quản lý subscription. Nếu file đích đã tồn tại, transferTo sẽ truncate; do đó path đích phải là path do server tạo, duy nhất cho từng upload.

Đặt storage root ngoài webroot, tạo staging directory riêng, validate file rồi promote sang tên nội bộ. Không dùng filename hoặc path client gửi làm đường dẫn. Phân biệt ngưỡng 256 KiB giữ part trong RAM với giới hạn disk/request thực tế; cấu hình multipart parser, gateway và quota đồng bộ. Khi xử lý DataBuffer/PartEvent trực tiếp, tiêu thụ hoặc release mọi buffer trên cả success, error và cancellation. Những quy tắc này giúp upload không ghi đè dữ liệu ngoài ý muốn, không làm rò đường dẫn và không để file tạm tồn đọng khi request thất bại.
