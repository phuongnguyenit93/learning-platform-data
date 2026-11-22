# Multipart, FilePart, PartEvent và xử lý tệp theo luồng trong Spring WebFlux

## 1. Mục tiêu và phạm vi

Trong Spring WebFlux, tải file lên HTTP thường sử dụng `multipart/form-data`, nhưng việc nhận một file đơn lẻ và xử lý hàng chục gigabyte theo luồng là hai bài toán khác nhau. **`FilePart`** thuận tiện khi truy cập part đã được parse theo tên và lưu vào đích, trong khi **`PartEvent`** cho phép nhận các mảnh dữ liệu multipart tuần tự bằng `Flux<PartEvent>`.

Kết thúc bài này, bạn cần hiểu:

- Cấu trúc multipart HTTP (boundary, field name, filename, media type, form fields và file).
- Phân biệt Spring WebFlux `Part`, `FilePart`, `FormFieldPart`, `PartEvent`, `FilePartEvent`, `FormPartEvent` với Servlet MVC `MultipartFile`.
- Cách dùng `@RequestPart`, `@RequestBody Mono<MultiValueMap<String, Part>>`, `ServerWebExchange.getMultipartData()`.
- Cách dùng `@RequestBody Flux<PartEvent>`, `windowUntil(PartEvent::isLast)`, `switchOnFirst`, `concatMap`, `DataBufferUtils.release`.
- Cách lưu bằng `FilePart.transferTo(Path)` hoặc `DataBufferUtils.write`, quản lý ownership của pooled buffers.
- Giới hạn `maxInMemorySize`, `maxDiskUsagePerPart`, `maxParts`, tổng dung lượng upload, timeouts và concurrent uploads.
- Cách triển khai, kiểm thử và bảo vệ endpoint upload với **Java 17+, Spring Boot 3.x, Spring Framework 6.x**, bao gồm kiểm thử HTTP multipart bằng `WebTestClient`.
- Những giới hạn của streaming/backpressure; không nhầm non-blocking với vô hạn memory, disk hay network throughput.

**Lưu ý phạm vi:** Bài tập dùng Spring WebFlux reactive stack (`spring-boot-starter-webflux`), không phải `spring-boot-starter-web`/Spring MVC. Đối với Boot 4/Framework 7, cần kiểm tra lại version API.

## 2. HTTP multipart: một body có nhiều parts

Request trình duyệt:

~~~html
<form action="/api/uploads/file" method="post" enctype="multipart/form-data">
  <input type="file" name="file" required>
  <button type="submit">Upload</button>
</form>
~~~

Một request tương đương dạng MIME được trình bày đơn giản:

~~~http
POST /api/uploads/file HTTP/1.1
Host: localhost:8080
Content-Type: multipart/form-data; boundary=DemoBoundary

--DemoBoundary
Content-Disposition: form-data; name="note"

report for Q4
--DemoBoundary
Content-Disposition: form-data; name="file"; filename="report.csv"
Content-Type: text/csv

id,name
1,Spring
--DemoBoundary--
~~~

Các boundary lines thực tế có các quy tắc CRLF riêng; snippet chỉ minh họa format, không phải dump nhị phân chính xác.

Từng part có **tên field** (`name="file"`), có thể có **filename** và `Content-Type` riêng. Filename và Content-Type **do client gửi**, không được dùng làm quyền truy cập, MIME validation hay filesystem path tin cậy.

Server chọn part qua `@RequestPart("file")`, không phải qua đuôi file. Nếu client gửi `name="attachment"` thì `@RequestPart("file")` không khớp và thường bị lỗi 4xx.

Client HTTP nên tự tạo boundary đúng qua `curl -F`, `MultipartBodyBuilder`, trình duyệt hoặc WebClient multipart writer. Đừng chỉ gán header `Content-Type: multipart/form-data` rồi gửi raw bytes mà thiếu multipart separators.

## 3. Phân biệt các abstraction và phương thức

| Kiểu | Package | Dùng cho |
| --- | --- | --- |
| `Part` | `org.springframework.http.codec.multipart` | Multipart part: `name()`, `headers()`, `content()`, `delete()` |
| `FilePart` | như trên | File đã được parse: `filename()`, `transferTo(Path)` |
| `FormFieldPart` | như trên | Field text có `value()` |
| `PartEvent` | như trên | Event chứa headers, `content()`, `isLast()` |
| `FilePartEvent` | như trên | Event thuộc file; `filename()` |
| `FormPartEvent` | như trên | Event thuộc form field; `value()` |
| `DataBuffer` | `org.springframework.core.io.buffer` | Một buffer bytes, có thể pooled/ref-counted |
| `DataBufferUtils` | như trên | Read/write/release buffers |

Trong Spring MVC Servlet, `MultipartFile` có API `getBytes()`, `getInputStream()` và `transferTo(File)` mang phong cách imperative. Trong WebFlux, `FilePart.content()` trả **`Flux<DataBuffer>`** còn `transferTo(Path)` trả **`Mono<Void>`**. Không sao chép code MVC sang WebFlux rồi coi hai type là một.

### Chọn API đúng nhiệm vụ

| Nhu cầu | Lựa chọn |
| --- | --- |
| Một file hay vài named fields | `@RequestPart FilePart` |
| File cùng một JSON metadata part | `@RequestPart FilePart` và `@RequestPart Mono<Meta>` |
| Tra cứu toàn bộ parts theo tên | `@RequestBody Mono<MultiValueMap<String, Part>>` hoặc `exchange.getMultipartData()` |
| Xử lý một file theo từng chunk/event | `@RequestBody Flux<PartEvent>` |
| Streaming relay multipart sang service khác | `PartEvent` + WebClient multipart writer, kèm quản lý buffers |
| Chỉ lưu file đã được parse | `FilePart.transferTo(Path)` |
| Upload rất lớn và cần resume theo chunk | Protocol resumable chuyên dụng/object storage, không chỉ một `FilePart` |

Không có lựa chọn luôn nhanh nhất. Streaming API giảm nhu cầu giữ toàn bộ file trong memory nhưng tăng trách nhiệm quản lý DataBuffer và cancellation.

## 4. `@RequestPart`: truy cập part theo tên

Handler cơ bản:

~~~java
@PostMapping(
        path = "/api/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<Void> receive(
        @RequestPart("file") FilePart file,
        @RequestPart("metadata") Mono<DocumentMetadata> meta) {

    return meta.flatMap(m ->
            validateMetadata(m)
                    .then(file.transferTo(chooseServerPath(m))));
}
~~~

**Đây là snippet minh họa, chưa chạy độc lập** vì `DocumentMetadata`, `validateMetadata`, `chooseServerPath` chưa được định nghĩa. Ý chính: Spring WebFlux decode JSON của part `metadata` khi đúng media type/codec; file đi theo `FilePart`. `@Valid` có thể dùng với DTO metadata khi có Bean Validation dependency và constraint annotations, với cơ chế lỗi binding WebFlux tương ứng.

Khi cần tất cả parts:

~~~java
Mono<MultiValueMap<String, Part>> parts = exchange.getMultipartData();
~~~

hoặc trong controller:

~~~java
@PostMapping(consumes="multipart/form-data")
public Mono<Void> receiveAll(
        @RequestBody Mono<MultiValueMap<String, Part>> parts) {
    return parts.then();
}
~~~

Ví dụ thứ hai **chỉ minh họa binding**, không được coi là cách xử lý file an toàn trong sản phẩm: nó không lưu file và không có validation/cleanup nghiệp vụ. Với `getMultipartData()` hoặc map access, framework **parse các parts thành map** trước khi bạn truy cập, có thể buffer file nhỏ và spool file lớn ra temporary disk. Một khi raw body đã được parse/cache thành map thì không coi body là một stream có thể subscribe nhiều lần.

### Vì sao FilePart không nhất thiết là toàn bộ bytes trong heap?

`FilePart` mô tả part sau parser, không có nghĩa Spring đọc file 1 GiB thành một `byte[]`. Theo Spring 6.x default part reader, `maxInMemorySize` là threshold để file parts được spool sang disk; non-file parts bị giới hạn memory. Vậy vẫn phải theo dõi **temporary disk**, open files, cổng nhận HTTP, thời gian upload và số requests đồng thời.

## 5. `FilePart.transferTo(Path)` và tính lazy

~~~java
Mono<Void> write = filePart.transferTo(destination);
~~~

Tác vụ ghi thực hiện khi reactive Publisher được subscribe; framework sẽ subscribe khi controller trả Mono. Vì vậy **sai** nếu gọi `file.transferTo(dest)` nhưng bỏ Mono rồi return ngay `"success"`.

Đúng hơn:

~~~java
return filePart.transferTo(destination)
        .thenReturn(ResponseEntity.status(HttpStatus.CREATED)
                .body("stored"));
~~~

`thenReturn` chỉ gửi business status khi transfer thành công. Nếu transfer lỗi, pipeline phát error chứ không báo file đã lưu xong.

**Không dùng trực tiếp filename client làm đường dẫn:**

~~~java
// ANTI-PATTERN: nguy cơ path traversal và ghi đè.
Path unsafe = uploadRoot.resolve(filePart.filename());
return filePart.transferTo(unsafe);
~~~

Filename có thể là `../secret.txt`, absolute path, ký tự điều khiển, Unicode spoofing hoặc tên trùng. Chính Javadoc `FilePart.filename()` khuyến cáo không sử dụng mù quáng. Chọn storage ID do server quản lý:

~~~java
String storageKey = UUID.randomUUID() + ".bin";
Path safe = controlledRoot.resolve(storageKey);
return filePart.transferTo(safe);
~~~

`UUID` giảm xác suất collision nhưng không thay hẳn atomic `CREATE_NEW` khi threat model cần ngăn mọi ghi đè. `transferTo` có thể truncate file đích đã tồn tại. Trong production cần storage isolation, quyền OS, kiểm soát symlink/race, staging/quarantine, checksum/scanning và cleanup khi lỗi.

### Không consume FilePart hai lần vô điều kiện

Nếu đã tự đọc `filePart.content()` để xử lý/hash, không mặc định `transferTo()` sau đó sẽ đọc lại một stream repeatable. Nếu cần hash và write, dùng một pass qua source buffers hoặc staging trước rồi đọc file đã lưu theo thiết kế rõ ràng.

## 6. `PartEvent`: xử lý streaming thay vì map access

Một file upload lớn có thể phát **nhiều `FilePartEvent`**, không phải một event duy nhất. Mỗi event có `content()` là `DataBuffer`; event cuối của part có `isLast() == true`. Form field thường có một `FormPartEvent`.

Đúng pattern:

~~~java
allEvents
    .windowUntil(PartEvent::isLast)
    .concatMap(window ->
        window.switchOnFirst((signal, events) -> {
            // signal đầu tiên giúp phân loại FormPartEvent/FilePartEvent.
            // Toàn bộ events của window vẫn phải được xử lý.
            return events;
        }));
~~~

Snippet chỉ minh họa chuỗi Reactor, **chưa phải handler hoàn chỉnh**. Giải thích:

1. `windowUntil(PartEvent::isLast)` chia stream thành từng window tương ứng một part.
2. `switchOnFirst` xem loại event đầu, nhưng không làm mất event đầu khỏi chuỗi phía sau.
3. `concatMap` xử lý windows tuần tự, giữ thứ tự multipart parts và tránh mở nhiều writes đồng thời không cần thiết.
4. Với `FilePartEvent`, lấy `events.map(PartEvent::content)` để chuyển tiếp/ghi/đếm theo streaming.
5. Với `FormPartEvent`, đọc `value()`, nhưng **nếu tự sở hữu buffer**, vẫn phải consume/release đúng.
6. **Mỗi DataBuffer nhận vào phải được consume, relay hoặc release**. Nếu lọc bỏ events mà không release buffers, pooled native memory có thể leak.

Anti-pattern:

~~~java
// KHÔNG LÀM: chỉ lấy event đầu tiên, bỏ dữ liệu cuối file.
return events.filter(e -> e instanceof FilePartEvent).next();
~~~

Nếu file chia nhiều chunks thì `next()` lấy quá ít bytes. Cancellation cũng có thể khiến những buffers chưa được downstream nhận phải được xử lý theo discard/cleanup semantics.

## 7. DataBuffer ownership, release và write

Trong Reactor Netty, `DataBuffer` có thể backed bởi pooled reference-counted buffers. Nếu framework decoder hoàn toàn xử lý bytes, nó thường quản lý lifecycle. Nhưng nếu custom code trực tiếp lấy `PartEvent.content()` thì bạn phải quản lý.

Ví dụ **đếm bytes rồi giải phóng**:

~~~java
long length;
try {
    length = buffer.readableByteCount();
} finally {
    DataBufferUtils.release(buffer);
}
~~~

Đây là snippet trong method đã có `DataBuffer buffer`. `finally` đảm bảo release khi code ném exception. Không release một buffer trước khi writer/consumer khác hoàn tất đọc; cũng không truyền buffer đã release tiếp downstream.

Spring cung cấp:

~~~java
Mono<Void> write = DataBufferUtils.write(
        sourceBuffers, destination,
        StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
~~~

Đây là overload ghi vào **`Path`**; `sourceBuffers` và `destination` cần được khai báo. **Các overload khác trả `Flux<DataBuffer>` khi ghi vào `OutputStream`/`WritableByteChannel` và không tự release buffers**; cần đọc Javadoc overload chính xác và dùng `DataBufferUtils.releaseConsumer()`/doOnNext release khi phù hợp.

Không đồng thời cho hai consumers giữ cùng một `DataBuffer` rồi cả hai release nếu không xử lý reference count có chủ đích. `doOnDiscard` hữu ích cho những operators hỗ trợ discard, nhưng không thay thế việc release trên chính nhánh xử lý thông thường; cancellation, timeout và error đều cần được kiểm thử.

**Tránh gom toàn bộ bytes:**

~~~java
// ANTI-PATTERN với file lớn
Mono<List<DataBuffer>> huge = inputBuffers.collectList();
~~~

Không giới hạn kích thước file nhưng gom buffer references có thể làm memory tăng nhanh và gây leak khi lỗi. Streaming giúp tránh bước này, miễn downstream thực sự tiêu thụ dần và không bí mật aggregate lại.

## 8. Multipart readers và các giới hạn cần biết

Theo Spring Framework 6.2:

- `MultipartHttpMessageReader` cung cấp access theo dạng `MultiValueMap<String, Part>`; nó dùng một part reader bên dưới.
- `DefaultPartHttpMessageReader` phục vụ parsed parts và có `setMaxInMemorySize`, `setMaxDiskUsagePerPart`, `setMaxParts`.
- `PartEventHttpMessageReader` đọc trực tiếp `Flux<PartEvent>` cho event-stream path.

### Bảng giới hạn

| Limit | Ý nghĩa | Điều không nên suy diễn |
| --- | --- | --- |
| `maxInMemorySize` | Giới hạn non-file fields trong memory, threshold spool file parts sang disk | Không có nghĩa file tổng bị giới hạn bằng ngưỡng đó |
| `maxDiskUsagePerPart` | Giới hạn disk per file part trên parsed reader tương ứng | Không tự giới hạn mọi file trong PartEvent path |
| `maxParts` | Giới hạn số parts trên parsed reader | Không thay per-user request quota |
| Max HTTP body | Tổng bytes tại server/gateway | Không đồng nghĩa `maxInMemorySize` |
| Idle/body timeout | Client truyền rất chậm | Không thay size quota |
| Temp disk quota | Không cho staging disk đầy | Không đạt được chỉ bằng giới hạn heap |
| Concurrent upload limit | Số clients đang upload cùng lúc | Non-blocking không có nghĩa vô hạn |

Đặt `maxInMemorySize=-1` có thể tắt giới hạn và khiến data được giữ hoàn toàn trong memory ở reader tương ứng. Không “sửa” `DataBufferLimitException` bằng giá trị -1 mà không đặt hard limits khác.

### Cấu hình cho `FilePart` path

~~~java
@Configuration
public class UploadCodecConfig implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        DefaultPartHttpMessageReader partReader =
                new DefaultPartHttpMessageReader();

        partReader.setMaxInMemorySize(64 * 1024);
        partReader.setMaxDiskUsagePerPart(10L * 1024 * 1024);
        partReader.setMaxParts(5);

        configurer.defaultCodecs().multipartReader(
                new MultipartHttpMessageReader(partReader));
    }
}
~~~

Đây là class mô phỏng, file đầy đủ với imports nằm trong ví dụ tiếp. **Giới hạn per-file disk và maxParts của cấu hình này thuộc parsed reader `@RequestPart`**, không được mặc định áp dụng cùng mức cho `@RequestBody Flux<PartEvent>`. Với event-based route, tự đếm bytes, áp ingress limit, timeouts và giới hạn parts ngoài application nếu cần.

Khi parser từ chối request, status có thể là 400/413 tùy exception/version/middleware. Nếu API yêu cầu luôn 413 cho size overflow, thêm exception mapping được kiểm thử end-to-end, không tự khẳng định một status mà chưa kiểm tra.

## 9. Security: upload là untrusted input

Ngay cả người dùng có tài khoản cũng có thể upload file nguy hiểm hoặc sai định dạng. Cần các lớp độc lập:

- **Authentication/authorization** per user/tenant, upload policy, allowlist định dạng, quota/retention.
- **Server-generated storage keys**, không dùng `filename()`, raw path param hoặc `getOriginalFilename` làm Path.
- **MIME sniffing/validation** dựa trên nội dung thật cùng allowlist; extension và part `Content-Type` là hint client.
- **Đếm bytes thật**; không tin `Content-Length` nếu request dùng streaming/chunked, proxy rewriting hoặc client nói dối.
- **File scanner/virus scanner**, kiểm tra archive/zip bomb nếu nghiệp vụ xử lý compressed contents.
- **Staging/quarantine** trước publish; chỉ public khi scanning, metadata DB, owner ACL đều thành công.
- **Giới hạn parts/file/disk/HTTP timeouts/concurrency**, quota per user, rate limiting và slow upload protection.
- **Filesystem isolation**, không lưu trong web root/code directory, root không writable bởi client, ngăn symlink/TOCTOU.
- **Cookie/CORS/CSRF**: CORS không thay CSRF nếu dùng cookie session; WebFlux Spring Security chain phải bảo vệ POST upload.
- **Download ACL** độc lập; tệp được nhận không mặc nhiên được public/inline.
- **Audit** bằng opaque ID, không log session cookies, bearer tokens, raw filename hoặc nội dung file nhạy cảm.
- **Cleanup** khi file ghi dở, upload hủy, scan thất bại, metadata DB lỗi, session/retry trùng.

Nếu cần tệp nhiều GiB hoặc resumable uploads, xem presigned object-storage upload / tus/chunked protocols thay vì buộc một HTTP multipart request giữ connection quá dài. `FilePart` không tự xử lý resume.

## 10. Ví dụ hoàn chỉnh Java 17+ và Spring Boot 3.x

Demo có **hai endpoints**:

- `POST /api/uploads/file` nhận `FilePart`, dùng tên opaque UUID và `transferTo` ghi file local. Trả **201 Created** khi transfer hoàn thành.
- `POST /api/uploads/events/inspect` nhận `Flux<PartEvent>`, duyệt tuần tự các parts, chỉ đếm bytes của file và release mỗi buffer; không lưu file và không tạo byte array lớn.
- Cấu hình parsed multipart reader với memory threshold 64 KiB, tối đa 10 MiB disk/file và tối đa 5 parts; event route có kiểm tra 10 MiB bytes/file trong pipeline.
- Kiểm thử HTTP bằng `WebTestClient` với multipart builder; xác minh bytes lưu và receipt.

**Giới hạn demo:** không có virus scanning, authentication/authorization, atomic publish, quota toàn request, cleanup file bị bỏ dở hoặc hard proxy limits. Không triển khai nguyên code demo lên public internet.

### 10.1. Project và dependencies

Tạo project Spring Initializr (Maven, Java 17+, Spring Boot 3.x) với:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là đoạn **trong pom.xml** do Spring Initializr tạo, không phải file Maven độc lập. Tránh thêm `spring-boot-starter-web` vì với cả MVC và WebFlux starters Boot thường ưu tiên MVC mặc định.

Cấu trúc:

~~~text
src/main/java/com/example/demo/DemoApplication.java
src/main/java/com/example/demo/UploadCodecConfig.java
src/main/java/com/example/demo/UploadController.java
src/test/java/com/example/demo/UploadControllerTest.java
~~~

### 10.2. DemoApplication.java

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.3. UploadCodecConfig.java

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.http.codec.multipart.DefaultPartHttpMessageReader;
import org.springframework.http.codec.multipart.MultipartHttpMessageReader;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class UploadCodecConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(ServerCodecConfigurer configurer) {
        DefaultPartHttpMessageReader parsed =
                new DefaultPartHttpMessageReader();
        parsed.setMaxInMemorySize(64 * 1024);
        parsed.setMaxDiskUsagePerPart(10L * 1024 * 1024);
        parsed.setMaxParts(5);
        configurer.defaultCodecs()
                .multipartReader(new MultipartHttpMessageReader(parsed));
    }
}
~~~

### 10.4. UploadController.java

~~~java
package com.example.demo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.http.codec.multipart.FilePartEvent;
import org.springframework.http.codec.multipart.PartEvent;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/uploads")
public class UploadController {

    private static final long MAX_FILE_BYTES = 10L * 1024 * 1024;
    private final Path root;

    public UploadController() throws IOException {
        // Chỉ chạy một lần khi khởi tạo application bean.
        root = Path.of("target", "demo-uploads")
                .toAbsolutePath().normalize();
        Files.createDirectories(root);
    }

    @PostMapping(
            path = "/file",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<ResponseEntity<StoredFile>> upload(
            @RequestPart("file") FilePart part) {

        // Không dùng part.filename() để chọn đường dẫn.
        String key = UUID.randomUUID() + ".bin";
        Path destination = root.resolve(key);

        return part.transferTo(destination)
                .thenReturn(ResponseEntity.status(HttpStatus.CREATED)
                        .body(new StoredFile(key, "stored")));
    }

    @PostMapping(
            path = "/events/inspect",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<List<StreamReceipt>> inspect(
            @RequestBody Flux<PartEvent> all) {

        return all.windowUntil(PartEvent::isLast)
                .concatMap(window ->
                        window.switchOnFirst((signal, events) -> {
                            if (!signal.hasValue()) {
                                return events.then(
                                        Mono.<StreamReceipt>empty());
                            }

                            PartEvent first = signal.get();

                            if (first instanceof FilePartEvent) {
                                AtomicLong bytes = new AtomicLong();

                                return events
                                        .map(PartEvent::content)
                                        .map(buffer -> {
                                            try {
                                                long total = bytes.addAndGet(
                                                        buffer.readableByteCount());
                                                if (total > MAX_FILE_BYTES) {
                                                    throw new ResponseStatusException(
                                                        HttpStatus.PAYLOAD_TOO_LARGE,
                                                        "file too large");
                                                }
                                                return total;
                                            } finally {
                                                DataBufferUtils.release(buffer);
                                            }
                                        })
                                        .then(Mono.fromSupplier(() ->
                                                new StreamReceipt(
                                                        "file", bytes.get())));
                            }

                            // Field metadata không dùng: vẫn phải release.
                            return events.doOnNext(event ->
                                    DataBufferUtils.release(event.content()))
                                    .then(Mono.<StreamReceipt>empty());
                        }))
                .collectList();
    }

    public record StoredFile(String key, String status) {}

    public record StreamReceipt(String type, long bytes) {}
}
~~~

Giải thích kỹ những quyết định:

1. Constructor tạo thư mục khi khởi động, không chạy blocking filesystem setup ở mỗi HTTP request. Thư mục chỉ để demo: production root phải được cấu hình/khóa quyền và **không** được người dùng tùy ý ghi symlink.
2. `upload` tạo key UUID, không sử dụng `FilePart.filename()`. `transferTo` được **return/compose**, Spring subscribe và trả 201 sau khi hoàn tất.
3. `inspect` đọc `Flux<PartEvent>` trực tiếp, không yêu cầu multipart map và không lưu file.
4. `windowUntil(PartEvent::isLast)` bảo đảm một file nhiều chunks được nhóm thành một window; `switchOnFirst` phân loại, `concatMap` xử lý theo thứ tự.
5. `AtomicLong` là biến **per-part**, không shared giữa requests. Giá trị được cộng từ `readableByteCount()`; nếu quá 10 MiB, phát `ResponseStatusException(PAYLOAD_TOO_LARGE)`.
6. `finally` release DataBuffer đã nhận, ngay cả khi phát lỗi giới hạn. Form-field buffers được consume/release thay vì bị filter bỏ.
7. `collectList()` chỉ gom `StreamReceipt` nhỏ, không gom bytes upload. Với request nhiều parts, ingress/reader limits và quotas phải bổ sung; đây không phải giải pháp chống mọi nguồn dữ liệu vô hạn.
8. Với cancellation/error ở upstream hoặc giữa pipeline, muốn bảo đảm mọi pooled buffer được giải phóng và file dở được xóa cần additional discard handling, integration tests và cleanup staging design. Đừng coi demo là hoàn chỉnh production.
9. Đường `upload` theo parsed reader có giới hạn disk 10 MiB/part; đường `events/inspect` không được bảo vệ tự động bởi cùng cấu hình, nên tự giới hạn bytes và cần hard request cap bên ngoài.
10. `ResponseEntity` trả key opaque, không public file path. Endpoint download riêng vẫn phải kiểm tra ACL nếu bổ sung.

### 10.5. UploadControllerTest.java

~~~java
package com.example.demo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class UploadControllerTest {

    @Autowired
    WebTestClient client;

    private static ByteArrayResource testFile(byte[] body) {
        return new ByteArrayResource(body) {
            @Override
            public String getFilename() {
                return "client-name.txt";
            }
        };
    }

    @Test
    void filePartTransferStoresExactBytes() throws Exception {
        byte[] data = "spring reactive\n"
                .getBytes(StandardCharsets.UTF_8);

        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("file", testFile(data))
                .contentType(MediaType.TEXT_PLAIN);

        UploadController.StoredFile receipt = client.post()
                .uri("/api/uploads/file")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(builder.build()))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(UploadController.StoredFile.class)
                .returnResult().getResponseBody();

        assertNotNull(receipt);
        assertTrue(receipt.key().endsWith(".bin"));
        assertTrue(!receipt.key().contains("client-name.txt"));

        Path stored = Path.of("target", "demo-uploads")
                .toAbsolutePath().normalize().resolve(receipt.key());

        try {
            assertTrue(Files.isRegularFile(stored));
            assertArrayEquals(data, Files.readAllBytes(stored));
        } finally {
            Files.deleteIfExists(stored);
        }
    }

    @Test
    void streamedPartEventsCountActualBytes() {
        byte[] data = "abcd".getBytes(StandardCharsets.UTF_8);
        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("note", "demo");
        builder.part("file", testFile(data))
                .contentType(MediaType.TEXT_PLAIN);

        client.post()
                .uri("/api/uploads/events/inspect")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(builder.build()))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$[0].type").isEqualTo("file")
                .jsonPath("$[0].bytes").isEqualTo(4);
    }

    @Test
    void missingRequiredNamedPartProducesClientError() {
        MultipartBodyBuilder builder = new MultipartBodyBuilder();
        builder.part("note", "without file");

        client.post()
                .uri("/api/uploads/file")
                .contentType(MediaType.MULTIPART_FORM_DATA)
                .body(BodyInserters.fromMultipartData(builder.build()))
                .exchange()
                .expectStatus().is4xxClientError();
    }
}
~~~

**Điểm kiểm thử:**
- `WebTestClient` dùng embedded server trên random port, tạo multipart form request thực.
- `ByteArrayResource` chỉ dùng ở **client test** để có bytes/filename nhất quán, không chứng minh upload backend đọc toàn bộ file trong memory.
- Kiểm tra file được lưu dưới opaque key của server và **bytes thực tế khớp**.
- Route events bỏ qua form field và release buffer, receipt `bytes=4` cho file `abcd`.
- Thiếu `@RequestPart("file")` trả 4xx. Exact error schema/status có thể phụ thuộc auto-configuration của Boot/Framework.
- Test không đo performance, virus scan hoặc concurrency/slow clients; bổ sung integration/load/security tests trước production.

Chạy Maven:

~~~bash
./mvnw test
~~~

Trên Windows dùng `mvnw.cmd test`; nếu không có wrapper, dùng `mvn test` khi Maven đã cài.

## 11. Thử bằng curl

Chạy ứng dụng:

~~~bash
./mvnw spring-boot:run
~~~

### Lưu một file

~~~bash
curl -i -F "file=@sample.txt;type=text/plain"   http://localhost:8080/api/uploads/file
~~~

Kết quả **201 Created** với body dạng:

~~~json
{"key":"00000000-0000-0000-0000-000000000000.bin","status":"stored"}
~~~

UUID trong ví dụ là **placeholder mô tả định dạng**, kết quả thực được random, không phải giá trị cố định. File được tạo dưới thư mục `target/demo-uploads`.

### Đọc multipart như PartEvent stream

~~~bash
curl -i   -F "note=demo"   -F "file=@sample.txt;type=text/plain"   http://localhost:8080/api/uploads/events/inspect
~~~

Response có dạng:

~~~json
[{"type":"file","bytes":4}]
~~~

`4` là ví dụ nếu `sample.txt` thực chứa 4 bytes, như chữ `abcd`. Với file thực, kích thước kết quả bằng số bytes content đã đọc, **không** nhất thiết bằng số Unicode characters nhìn thấy. Kiểm tra bằng `wc -c sample.txt`.

### Field sai tên

~~~bash
curl -i -F "attachment=@sample.txt"   http://localhost:8080/api/uploads/file
~~~

Handler đòi named part `file`, vì thế request chỉ có `attachment` không phù hợp và thường trả 4xx.

**Lưu ý shell:** các dấu nối dòng `\` ở trên dành cho Linux/macOS/Git Bash. Trên Windows PowerShell dùng `curl.exe` trên một dòng, hoặc syntax line continuation của PowerShell. Không ghi password/API token vào lệnh hoặc logs public.

## 12. Bổ sung WebClient multipart và PartEvent outbound

Khi ứng dụng cần gửi file đến upstream, Spring WebFlux WebClient hỗ trợ `MultipartBodyBuilder`:

~~~java
MultipartBodyBuilder builder = new MultipartBodyBuilder();
builder.part("description", "demo");
builder.part("file", new FileSystemResource("/safe/path/data.bin"));

Mono<String> result = webClient.post()
        .uri("/ingest")
        .body(BodyInserters.fromMultipartData(builder.build()))
        .retrieve()
        .bodyToMono(String.class);
~~~

Đây là snippet trong service với `webClient` được cấu hình và storage file đã được server cho phép. Với remote domain, kiểm tra host allowlist, HTTPS, authentication, timeouts, retries, outbound quotas và việc có truyền nhầm untrusted headers/filenames hay không.

Có thể gửi multipart bằng **PartEvent**:

~~~java
Flux<PartEvent> outgoing = Flux.concat(
        FormPartEvent.create("description", "demo"),
        FilePartEvent.create("file", resource));

return webClient.post()
        .uri("/ingest")
        .body(outgoing, PartEvent.class)
        .retrieve()
        .bodyToMono(Void.class);
~~~

Đây là snippet minh họa có `resource` và `webClient` cần khai báo. `FilePartEvent.create` có thể tạo nhiều events cho file lớn. Không gọi `collectList()` toàn bộ events rồi tạo multipart request khác nếu mục tiêu là streaming.

### Relay inbound đến outbound mà không gom cả file

Một endpoint nhận `Flux<PartEvent>` có thể relay cho WebClient outbound, nhưng phải kiểm soát:
1. Headers and filenames có thể chứa input không tin cậy.
2. Pooled buffers: xác định ai là consumer cuối và ownership/release.
3. Nếu upstream lỗi hoặc client disconnect, cancel inbound đúng cách.
4. Limit bytes, parts, rate, connections và timeout ở cả hai đầu.
5. Không tự gọi `.subscribe()` trong controller rồi return 200 trước khi upload upstream hoàn thành.
6. Không gọi `.block()` trên Reactor Netty event loop.
7. Nếu phản hồi upstream không thành công, dịch status và cleanup staging/metadata theo contract.

## 13. Vòng đời upload production: staging → scan → publish

Một hệ thống có thể cần workflow:

~~~text
Client
  |
  v
Ingress/WAF: authentication, maximum body size, timeout, rate limit
  |
  v
Spring WebFlux: validate named parts + metadata, quota
  |
  v
Staging file/object (opaque key, isolated storage)
  |
  +-- stream bytes, count, compute hash, enforce hard limit
  |
  +-- file format and malware scanning
  |
  v
Atomic publish / object-store versioning
  |
  v
Database metadata: owner, tenant, ID, size, hash, MIME, state
  |
  v
201 Created / async job status
~~~

**Dọn dẹp khi lỗi là trách nhiệm bắt buộc:** file có thể đã được ghi nhưng DB metadata insert thất bại; hoặc DB commit trước rồi object publish bị lỗi. Tạo transaction/compensation/garbage-collection workflow, như trạng thái `PENDING`, `SCANNING`, `READY`, `FAILED`. Filesystem rename atomic chỉ hoạt động theo điều kiện filesystem; object-storage copy/move không phải transaction POSIX.

Nếu có concurrent uploads, kiểm tra collision, symlink, path traversal, race và partition/quota theo tenant. Với dữ liệu lớn và yêu cầu resume, cân nhắc tus hoặc presigned chunked uploads với checksum/version/idempotency key. Không mặc định một HTTP multipart POST là resumable.

### Timeout và status

- `400`: multipart malformed, part name không hợp lệ, metadata sai theo contract.
- `401/403`: thiếu authentication/quyền.
- `413`: request hoặc file vượt quota được ứng dụng quy định.
- `415`: content type không được hỗ trợ.
- `422`: file định dạng hợp lệ về HTTP nhưng không đạt validation nghiệp vụ (tùy API).
- `429`: vượt rate limit/concurrency.
- `503`: backend/storage đang quá tải.

Mã cụ thể cho parser overflow phụ thuộc framework/container; cần **test thực tế**, không bịa rằng mọi exception từ multipart reader đều tự map 413. Khi response đã commit, server có thể không thay sang JSON lỗi được; client phải phát hiện incomplete response/connection failure.

## 14. Lỗi thường gặp và hướng xử lý

| Vấn đề | Sai ở đâu | Cách làm đúng |
| --- | --- | --- |
| Dùng `MultipartFile` trong WebFlux | Servlet/MVC API khác | `FilePart` hoặc `PartEvent` |
| Bỏ Mono của `transferTo` | Pipeline không thực thi | Return/compose Mono |
| Dùng `filename()` làm path | Path traversal/overwrite | Server-generated opaque key |
| Tin `Content-Type` client | Fake MIME/extension | Magic-byte/decoder scan |
| Chỉ đọc event đầu | File bị cắt khi nhiều chunks | `windowUntil(isLast)`, đọc cả window |
| `filter` bỏ buffer mà không release | Netty pooled memory leak | Consume/release/relay |
| Release buffer trước khi write hoàn tất | Use-after-release | Ownership rõ và đúng overload |
| `collectList()` file buffers | Memory giữ tỷ lệ file size | Stream/write từng buffer |
| Mở `maxInMemorySize=-1` | Heap bị dùng không giới hạn | Threshold và disk quotas |
| Chỉ set memory threshold | Temp disk vẫn có thể đầy | maxDiskUsagePerPart, quotas |
| Coi maxParts parsed reader áp cho PartEvent | Event route dùng reader khác | Tự hard-limit events/bytes + ingress |
| Dùng `Files.readAllBytes` trong event loop | Blocking + memory | API async/chọn scheduler hoặc stream |
| Client không gửi cookie/auth với CORS | Preflight/SameSite/CSRF mismatch | Security/CORS config đúng |
| Test raw bytes thay multipart | Missing boundary/part | `curl -F`/MultipartBodyBuilder |
| Không dọn partial files | Disk orphan | Staging + doFinally/error cleanup |
| Response 201 trước khi storage hoàn tất | Publisher không được compose | `transferTo(...).thenReturn(...)` |
| “Non-blocking” là unlimited uploads | Pool/IO/disk vẫn hữu hạn | Concurrency budgets, timeouts |
| Cho file được truy cập công khai sau upload | Thiếu scanning/download ACL | Publish theo state và owner |

## 15. Câu hỏi ôn tập

**1. `FilePart` khác `MultipartFile` như thế nào?**  
`FilePart` là API reactive của WebFlux; `transferTo` trả `Mono<Void>`. `MultipartFile` là API thường dùng ở MVC Servlet.

**2. Khi gọi `file.transferTo(path)` nhưng không return/subscribe Mono, chuyện gì xảy ra?**  
Việc chuyển file không được đảm bảo chạy; cần đưa Mono vào pipeline mà WebFlux subscribe.

**3. Vì sao `PartEvent::isLast` quan trọng?**  
Một file có thể gồm nhiều FilePartEvents; `isLast` đánh dấu event cuối của mỗi part.

**4. `switchOnFirst` giúp gì?**  
Nhìn event đầu để chọn xử lý form/file mà vẫn giữ toàn bộ events cho consumer.

**5. Vì sao phải release DataBuffer?**  
Pooled buffers có reference count; thiếu release có thể làm rò bộ nhớ ngoài heap.

**6. Nếu đặt `maxInMemorySize=64KiB` thì có nghĩa file 65KiB bị từ chối không?**  
Không: với default parsed file reader đây thường là ngưỡng spool disk; cần maxDiskUsagePerPart và request-size limit riêng.

**7. Có nên dùng filename gốc để resolve filesystem path?**  
Không. Nó do client kiểm soát; dùng storage key server-generated.

**8. Event streaming có tự bị chặn bởi maxParts của DefaultPartHttpMessageReader không?**  
Không nên suy luận như vậy. PartEvent reader và parsed multipart reader khác nhau; cần giới hạn tương ứng.

**9. Vì sao test receipt bytes phải so số byte thay vì ký tự?**  
Vì UTF-8/nhị phân có độ dài bytes khác số ký tự Unicode.

**10. PartEvent luôn nhanh hơn FilePart?**  
Không. Nó đổi cách truy cập và thêm quản lý buffer; cần benchmark đầy đủ latency, memory, disk I/O và concurrency.

## 16. Checklist trước khi đưa lên production

1. Chọn API đúng: named parts → `@RequestPart FilePart`; streaming tuần tự → `Flux<PartEvent>`.
2. Giữ publisher trong return chain; không tự subscribe/block trên event loop.
3. Generate storage ID ở server, tránh raw filename, phân quyền filesystem và chống symlink/race.
4. Đọc/ghi DataBuffers có ownership rõ, release trên success, error/cancel/discard.
5. Kiểm tra hạn mức bytes/file, parts/request, memory/disk, temp storage, request duration, max concurrency.
6. Không cho input có `Content-Type`/filename giả bypass MIME/scan rules.
7. Staging/quarantine trước scan/publish, cleanup partial/orphan files và quản lý idempotency.
8. Với outbound WebClient relay, đặt timeout, connection pool limits, trusted target, authentication/headers.
9. Với download, kiểm tra ACL và Content-Disposition/Range/cache policy riêng.
10. Đo p95/p99 upload latency, HTTP status/error rates, disk usage, memory/Netty buffers, cleanup failures, proxy size rejection.
11. Test HTTP multipart với WebTestClient/curl, nhiều chunks, file rỗng, malformed multipart, metadata JSON, missing parts, oversized uploads và disconnects.
12. Không coi ví dụ demo hai endpoint là bộ upload security hoàn chỉnh.

## Tài liệu chính thức

- [Spring Framework 6.2 — Multipart Content / annotated controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework 6.2 — WebFlux Reactive Core và Multipart Limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — FilePart API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/multipart/FilePart.html)
- [Spring Framework 6.2 — PartEvent API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/multipart/PartEvent.html)
- [Spring Framework 6.2 — DefaultPartHttpMessageReader](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/codec/multipart/DefaultPartHttpMessageReader.html)
- [Spring Framework 6.2 — DataBufferUtils](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html)
- [Spring Framework 6.2 — WebClient Multipart request](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-body.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [RFC 7578 — multipart/form-data](https://www.rfc-editor.org/rfc/rfc7578)
- [OWASP — File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
