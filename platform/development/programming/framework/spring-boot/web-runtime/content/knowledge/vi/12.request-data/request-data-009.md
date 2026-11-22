# Truyền dữ liệu lớn theo luồng thay vì gom toàn bộ vào bộ nhớ

## 1. Bài toán và mục tiêu

Trong Spring Boot, HTTP request body có thể là JSON vài kilobyte, nhưng cũng có thể là file CSV hàng trăm megabyte, video nhiều gigabyte, bản sao lưu, telemetry hoặc luồng các bản ghi. Nếu API đọc **toàn bộ body vào `byte[]`, `String` hoặc `List`** rồi mới xử lý, bộ nhớ tăng theo kích thước dữ liệu và số request đồng thời. Nhiều upload lớn đồng thời dễ làm tăng garbage collection, gây thiếu heap hoặc làm giảm throughput của server.

**Streaming** nghĩa là đọc một phần dữ liệu, xử lý hoặc ghi phần đó tới đích, rồi tiếp tục với phần sau. Mục tiêu là giữ bộ nhớ cần thiết cho một request ở mức có thể kiểm soát, chứ không đòi giữ nguyên toàn bộ payload trong JVM heap.

```text
Gom toàn bộ:
Client -> Web server -> byte[] rất lớn -> xử lý -> storage
                         ^ body lớn nằm trong heap

Streaming:
Client -> Web server -> buffer nhỏ -> storage
                            |
                      lặp đọc/ghi
```

Streaming không đồng nghĩa với *zero buffering*. TCP/TLS, proxy, container, codec, multipart parser, file system hoặc SDK downstream vẫn có thể buffer ở mức nào đó. Cần phân biệt **không gom toàn bộ vào heap** với **không sử dụng temp disk**.

## 2. Vì sao cần streaming khi dữ liệu lớn?

| Khía cạnh | Gom toàn bộ | Xử lý theo luồng |
|---|---|---|
| Kích thước object | Có thể ngang kích thước request | Thường chỉ giữ buffer/record hiện tại |
| Khi nào xử lý | Sau khi nhận/deserialize đủ nội dung | Trong lúc request vẫn đang truyền |
| Chi phí bộ nhớ | Tăng theo payload × concurrency | Phụ thuộc buffer, prefetch, concurrency và sink |
| I/O | Dễ lập trình nhưng có thể cần sao chép lớn | Có thể nối thẳng network tới file/storage |
| Kiểm tra size | Thường biết sau khi đã đọc hết | Có thể đếm byte và từ chối giữa chừng |
| Thao tác trên record | Có thể dùng một list lớn | Có thể xử lý từng record nếu format cho phép |
| Độ phức tạp | Nhỏ | Cần xử lý hủy, timeout, backpressure, file dang dở |

Nếu 20 request cùng tạo mảng 200 MiB, dữ liệu byte thô đã khoảng 4 GiB, chưa tính header object, GC, runtime buffers. Một vòng lặp dùng buffer 64 KiB mỗi request chỉ giữ khoảng 1,25 MiB **do chính vòng lặp quản lý** cho 20 request; không có nghĩa RAM tổng của process luôn bằng con số đó.

Streaming đặc biệt hữu ích khi cần ghi file, kiểm tra checksum incremental, chuyển tiếp sang object storage hoặc xử lý từng record. Với JSON object nhỏ, `@RequestBody Dto` vẫn thường là giải pháp đơn giản và phù hợp.

## 3. Các thao tác dễ vô tình gom body

Trong Spring MVC:

```java
@PostMapping("/raw")
public void upload(@RequestBody byte[] body) {
    // body đã được gom thành một mảng byte
}
```

```java
byte[] allBytes = multipartFile.getBytes();
```

`MultipartFile.getBytes()` tạo mảng byte của toàn file, kể cả khi multipart resolver trước đó đã lưu phần file lên đĩa tạm.

Trong WebFlux:

```java
Mono<byte[]> all = request.bodyToMono(byte[].class);
Mono<String> text = request.bodyToMono(String.class);
Mono<List<Item>> items = itemFlux.collectList();
```

Dù xuất phát từ `Flux`, `collectList()` vẫn gom toàn bộ phần tử. `DataBufferUtils.join(...)` cũng là thao tác kết hợp buffers, không phù hợp khi mục tiêu là chuyển tiếp một file lớn bằng bộ nhớ có giới hạn.

Không suy diễn rằng chữ `reactive` tự giải quyết vấn đề nếu cuối pipeline vẫn có bước aggregate.

## 4. Streaming ở tầng HTTP và ứng dụng là hai chuyện khác nhau

HTTP/1.1 có thể dùng `Content-Length` hoặc `Transfer-Encoding: chunked`. HTTP/2 dùng các DATA frames và flow control riêng. Tuy nhiên:

- Client gửi chunked không bảo đảm controller nhận được từng chunk ngay; proxy, container hoặc decoder vẫn có thể buffer.
- Kích thước network chunk không nhất thiết bằng kích thước một lần `InputStream.read()` hoặc một `DataBuffer`.
- `Content-Length` có thể không tồn tại hoặc không phản ánh đầy đủ những gì server đọc trước khi kiểm tra tính hợp lệ.
- Không được tin `Content-Length` là phương tiện duy nhất để giới hạn dung lượng; phải đếm **số byte thực nhận**.
- Proxy hoặc API gateway có thể chặn request quá lớn trước khi nó tới Spring Boot.

Để giải quyết bài toán này, cần thiết kế cả **đường xử lý từ HTTP parser tới sink** chứ không chỉ đổi một header.

## 5. Cách chọn API theo loại request

| Loại dữ liệu / web stack | Cách triển khai thường phù hợp |
|---|---|
| JSON nhỏ trên MVC | `@RequestBody Dto` |
| Binary raw trên MVC | `HttpServletRequest.getInputStream()` và vòng lặp đọc/ghi |
| Multipart file trên MVC | `MultipartFile.getInputStream()` hoặc `transferTo(...)` |
| Binary raw trên WebFlux | `@RequestBody Flux<DataBuffer>` và một streaming sink |
| Multipart trên WebFlux | `@RequestPart FilePart`, `FilePart.transferTo(Path)` |
| Multipart phải xử lý ngay từng part/buffer | `@RequestBody Flux<PartEvent>` |
| Nhiều JSON records | NDJSON/JSON Lines, `Flux<Record>` nếu codec hỗ trợ |
| Chuyển dữ liệu sang object storage | SDK có streaming/multipart async và giới hạn in-flight |
| Dữ liệu cần validation toàn cục phức tạp | Có thể cần staging file trước khi commit |

**Raw body** (`application/octet-stream`) và **multipart** (`multipart/form-data`) là hai định dạng request khác nhau. Controller dùng `MultipartFile` không tự xử lý được raw body; tương tự `@RequestBody Flux<DataBuffer>` của raw upload không tự parse form field/filename.

## 6. Spring MVC/Servlet: sao chép request body bằng buffer

Ví dụ project Spring Boot 3.5, Java 17, có `spring-boot-starter-web`. File `src/main/java/com/example/streaming/RawUploadController.java`:

```java
package com.example.streaming;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class RawUploadController {

    private static final long LIMIT = 50L * 1024 * 1024;

    @PostMapping(
        path = "/api/upload/raw",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<Map<String, Object>> upload(
            HttpServletRequest request) throws IOException {

        Path directory = Path.of("uploads")
                .toAbsolutePath().normalize();
        Files.createDirectories(directory);
        Path destination = Files.createTempFile(
                directory, "raw-", ".bin");

        byte[] buffer = new byte[64 * 1024];
        long total = 0;

        try (InputStream in = request.getInputStream();
             OutputStream out = Files.newOutputStream(destination)) {

            int count;
            while ((count = in.read(buffer)) != -1) {
                if (total > LIMIT - count) {
                    throw new ResponseStatusException(
                            HttpStatus.PAYLOAD_TOO_LARGE,
                            "Request body exceeds 50 MiB");
                }
                out.write(buffer, 0, count);
                total += count;
            }
        } catch (IOException | RuntimeException failure) {
            try {
                Files.deleteIfExists(destination);
            } catch (IOException cleanupError) {
                failure.addSuppressed(cleanupError);
            }
            throw failure;
        }

        return ResponseEntity.ok(Map.of(
            "storedAs", destination.getFileName().toString(),
            "bytes", total));
    }
}
```

Phân tích:

1. Request được đọc bằng Servlet `InputStream`; không có `byte[]` chứa toàn bộ file.
2. `byte[64 * 1024]` được tái sử dụng, giúp việc copy có lượng bộ nhớ do controller giữ gần cố định.
3. Một lần `read()` có thể trả ít byte hơn buffer; chỉ ghi đúng `count`.
4. Kiểm tra `total > LIMIT - count` giới hạn **byte thực nhận** và tránh lỗi cộng tràn.
5. Đường dẫn file do server chọn qua `Files.createTempFile`, không sử dụng tên file tùy ý do client gửi.
6. Thành công được trả về sau khi đọc hết và đóng luồng ghi.
7. Nếu I/O hỏng hoặc request vượt giới hạn, file đang ghi được xóa best effort.

Đây vẫn là **blocking I/O**. Một Servlet request thường cần thread xử lý trong lúc `read` hoặc `write` chờ. Streaming theo buffer giúp tránh gom RAM, **không có nghĩa** rằng Spring MVC tự biến thành event-loop non-blocking.

Ví dụ học tập này chưa có authentication, quota theo user, antivirus, checksum, quản lý staging/publish hoặc cơ chế dọn temp file khi process bị kill. Phải bổ sung khi dùng production.

## 7. Class main, chạy và kiểm tra MVC

File `src/main/java/com/example/streaming/StreamingApplication.java`:

```java
package com.example.streaming;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamingApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamingApplication.class, args);
    }
}
```

Trong `pom.xml` đã có Spring Boot parent/dependency management, dùng dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Tạo file test trên Linux/macOS:

```bash
printf 'Hello streaming\n' > sample.bin
./mvnw spring-boot:run
```

Trong terminal khác:

```bash
curl -i -H 'Content-Type: application/octet-stream' \
  --data-binary @sample.bin \
  http://localhost:8080/api/upload/raw
```

Nếu project chạy tại cổng 8080, response có status 200 và body JSON **có dạng**:

```json
{"storedAs":"raw-<random-name>.bin","bytes":16}
```

Tên file thực tế thay đổi theo mỗi request. Chuỗi `Hello streaming` có 15 byte ASCII cộng một newline, tổng 16 byte. `curl -i` còn in response headers; JSON key order có thể thay đổi.

Để test giới hạn byte, tạo file lớn hơn 50 MiB rồi gửi bằng `--data-binary`. Response theo ví dụ thường có status **413 Payload Too Large**, nhưng việc proxy/connector xử lý phần body còn lại hoặc đóng kết nối có thể ảnh hưởng thông tin client thấy trên wire.

## 8. Spring MVC multipart: MultipartFile không bắt buộc giữ trong heap

Một phương án upload form:

```java
@PostMapping(
    path = "/api/upload/form",
    consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public ResponseEntity<Map<String, String>> form(
        @RequestParam("file") MultipartFile file)
        throws IOException {

    Path dir = Path.of("uploads").toAbsolutePath();
    Files.createDirectories(dir);
    Path target = Files.createTempFile(dir, "form-", ".bin");

    try (InputStream in = file.getInputStream();
         OutputStream out = Files.newOutputStream(target)) {
        in.transferTo(out);
    }
    return ResponseEntity.ok(Map.of(
        "storedAs", target.getFileName().toString()));
}
```

Đây là một **method minh họa trong controller**, cần import `MultipartFile`, `@RequestParam`, `PostMapping`, `MediaType`, `ResponseEntity`, `Map`, `Path`, `Files`, `InputStream`, `OutputStream` và `IOException`. Cần thêm cleanup/error handling và kiểm tra size trong ứng dụng production.

`InputStream.transferTo(OutputStream)` sử dụng bộ đệm khi sao chép, không yêu cầu giữ toàn bộ file trong một `byte[]`. `MultipartFile.transferTo(Path/File)` cũng có thể phù hợp; implementation có thể copy hoặc move từ file tạm.

Với Spring Boot 3.5 Servlet multipart, ví dụ properties:

```properties
spring.servlet.multipart.max-file-size=50MB
spring.servlet.multipart.max-request-size=55MB
spring.servlet.multipart.file-size-threshold=0B
```

Default của Boot 3.5: `max-file-size` là **1MB**, `max-request-size` **10MB**, và threshold **0**. Threshold thấp khiến nội dung file part thường được ghi ra disk theo cơ chế servlet multipart thay vì giữ nguyên toàn bộ trên heap. **Tuy nhiên**, multipart resolver có thể xử lý và lưu file tạm trước khi method nhận `MultipartFile`. Vì vậy `getInputStream()` tránh tạo mảng byte lớn trong code nhưng không chứng minh socket truyền trực tiếp tới destination mà không có temp file.

Client multipart:

```bash
curl -i -F "file=@sample.bin" \
  http://localhost:8080/api/upload/form
```

## 9. WebFlux: Flux<DataBuffer> cho raw request body

Spring WebFlux hỗ trợ `@RequestBody` với kiểu reactive để đọc và xử lý body theo luồng. Với Spring Boot 3.5 + Java 17, project dùng `spring-boot-starter-webflux` thay vì Servlet starter.

Dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

File `src/main/java/com/example/reactive/RawReactiveUploadController.java`:

```java
package com.example.reactive;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Map;
import java.util.UUID;

import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class RawReactiveUploadController {

    private static final Path DIR = Path.of("uploads")
            .toAbsolutePath().normalize();

    @PostMapping(
        path = "/api/upload/raw",
        consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public Mono<Map<String, String>> upload(
            @RequestBody Flux<DataBuffer> body) {

        Path target = DIR.resolve(
                "reactive-" + UUID.randomUUID() + ".bin");

        return Mono.fromCallable(() -> {
                Files.createDirectories(DIR);
                return target;
            })
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap(path ->
                DataBufferUtils.write(
                    body, path, StandardOpenOption.CREATE_NEW)
                .thenReturn(Map.of(
                    "storedAs",
                    path.getFileName().toString())));
    }
}
```

Đây là class Java đầy đủ, nhưng phải chạy **trong một project Spring Boot WebFlux** đã có class main. Dùng class main `@SpringBootApplication` cùng package gốc `com.example.reactive` theo cấu trúc tương tự ví dụ MVC.

- `Flux<DataBuffer>` cung cấp các buffer nối tiếp; không có bước gom body thành một `byte[]`.
- `Files.createDirectories` là thao tác có thể blocking, được chuyển sang `boundedElastic` thay vì chạy trực tiếp trên event loop.
- `DataBufferUtils.write(Publisher<DataBuffer>, Path, OpenOption...)` ghi stream vào file qua kênh bất đồng bộ và trả `Mono<Void>` báo khi xong.
- Overload `write` nhận **Path** trong Spring Framework 6.2 sử dụng release consumer đối với những DataBuffer được nó ghi thành công. **Không nhầm** với các overload trả `Flux<DataBuffer>` để ghi vào channel/output stream: những overload đó không tự release buffer.
- `CREATE_NEW` giảm nguy cơ ghi đè tên đã tồn tại; UUID filename do server tạo.
- `.thenReturn(...)` chỉ tạo response khi file writer hoàn tất thành công.

**Quan trọng:** code này minh họa truyền raw body qua luồng nhưng **chưa đếm limit bytes, chưa dọn file dở dang khi lỗi/cancel, chưa có auth/quota**. Không dùng như API upload production nếu chưa bổ sung các chức năng đó.

Không triển khai controller MVC và WebFlux ở cùng URL trong cùng một project chỉ để thử hai cách: dùng hai project/web application type độc lập để so sánh rõ.

## 10. DataBuffer pooling và trách nhiệm giải phóng

Netty có thể dùng pooled, reference-counted buffers. Nếu một `DataBuffer` bị giữ quá lâu hoặc không được release sau khi xử lý, ứng dụng có thể bị rò rỉ **direct memory** dù heap metrics không tăng rõ rệt.

Spring Framework cung cấp các tiện ích:

- `DataBufferUtils.release(buffer)`: release nếu buffer là loại phù hợp.
- `DataBufferUtils.retain(buffer)`: tăng reference count khi cần giữ buffer qua một lifecycle khác.
- `doOnDiscard(DataBuffer.class, DataBufferUtils::release)`: giúp release khi operator Reactor bỏ buffer trước khi tiêu thụ, tùy operator và cách viết pipeline.

Không release hai lần. Nếu một writer đã nhận trách nhiệm release, không thêm `doOnNext(DataBufferUtils::release)` chỉ vì nghĩ "release càng sớm càng tốt"; buffer có thể bị giải phóng trước khi writer ghi xong.

Các operator như `filter`, `skip`, `flatMap`, `buffer`, `window` có thể tạo đường bỏ dữ liệu hoặc giữ nhiều phần tử. Khi xử lý raw buffer trực tiếp, cần xem tài liệu ownership và test cancellation, error và slow subscriber.

**Lựa chọn an toàn:** nếu chỉ cần upload file thông thường, hãy ưu tiên API cấp cao như `FilePart.transferTo` thay vì tự quản lý byte buffer bằng các operator phức tạp.

## 11. Multipart WebFlux: FilePart.transferTo

Với `multipart/form-data`, Spring WebFlux cung cấp `FilePart`:

```java
package com.example.reactive;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.UUID;

import org.springframework.http.MediaType;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class ReactiveMultipartController {

    private static final Path DIR = Path.of("uploads")
            .toAbsolutePath().normalize();

    @PostMapping(
        path = "/api/upload/file",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Mono<Map<String, String>> upload(
            @RequestPart("file") FilePart part) {

        Path target = DIR.resolve(
                "multipart-" + UUID.randomUUID() + ".bin");

        return Mono.fromCallable(() -> {
                Files.createDirectories(DIR);
                return target;
            })
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap(path -> part.transferTo(path)
                .thenReturn(Map.of(
                    "storedAs",
                    path.getFileName().toString())));
    }
}
```

Lớp này chạy được trong project WebFlux Java 17 có starter tương ứng và class main. Client test:

```bash
curl -i -F "file=@sample.bin" \
  http://localhost:8080/api/upload/file
```

`FilePart.transferTo(Path)` là API tiện lợi để chuyển file part tới đích mà controller không tự gọi `getBytes()`. Tuy nhiên multipart parser có thể sử dụng **memory threshold và temporary disk** trước bước transfer. Điều này giúp tránh giữ toàn file trong heap khi cấu hình hợp lý, không đồng nghĩa "không ghi temp disk" hoặc "zero-copy socket-to-file".

Không ghép `part.filename()` trực tiếp vào path. Tên do client cung cấp có thể chứa path traversal hoặc ký tự không an toàn; ví dụ dùng UUID phía server. Với upload lớn trong production, cần cleanup khi `transferTo` thất bại, quota, kiểm tra file type, checksum và publish sau validation.

## 12. Multipart thực sự theo sự kiện: Flux<PartEvent>

Spring Framework hỗ trợ đọc multipart sequentially qua `@RequestBody Flux<PartEvent>`. Một `FormPartEvent` đại diện một form field; file lớn tạo nhiều `FilePartEvent`, mỗi event mang `DataBuffer`, và event cuối part có `isLast() == true`.

Luồng:

```text
multipart/form-data
        |
        v
Flux<PartEvent>
    |
    +--> FormPartEvent
    +--> FilePartEvent #1 (buffer)
    +--> FilePartEvent #2 (buffer)
    +--> FilePartEvent #3 (isLast = true)
        |
        v
Xử lý tuần tự / relay / ghi xuống storage
```

Một snippet tách event theo part:

```java
Flux<PartEvent> events = ...;
Flux<Flux<PartEvent>> parts =
        events.windowUntil(PartEvent::isLast);
```

Đây **chỉ là snippet cơ chế**: `events` cần đến từ WebFlux endpoint, các part được tiêu thụ bằng một handler thực tế. Khi dùng `PartEvent`, **mọi body buffer phải được consume, relay hoặc release**; nếu bỏ qua buffer, Netty có thể bị rò rỉ bộ nhớ.

`PartEvent` phù hợp khi cần xử lý multipart thật sự theo chuỗi các sự kiện mà không materialize mỗi part thành `FilePart` lưu temp disk. Nó khó hơn `FilePart.transferTo` vì phải quản lý state giữa các part, headers, quota, file boundaries và lifecycle buffer.

## 13. Codec memory limit không phải giới hạn toàn request

Trong Spring Boot 3.5:

```properties
spring.http.codecs.max-in-memory-size=512KB
```

Property này giới hạn bytes mà codec được phép buffer khi cần aggregation trong WebFlux server và `WebClient` do Boot cấu hình. Nếu không chỉ định, mỗi codec dùng giới hạn riêng; nhiều codec thường khoảng **256 KiB**.

Điểm cần hiểu:

- Với `@RequestBody Mono<MyDto>`, decoder có thể phải gom dữ liệu để dựng object.
- Với NDJSON `Flux<MyDto>`, một decoder có thể buffer **một record**, nên record rất lớn vẫn chạm giới hạn.
- Với `Flux<DataBuffer>` chuyển dần vào file, `max-in-memory-size=512KB` **không có nghĩa** tổng raw request bị chặn ở 512KB.
- Nếu gặp `DataBufferLimitException`, hãy xem có code/codec đang gom quá nhiều không; không tăng giới hạn vô hạn chỉ để che một bước aggregation sai thiết kế.

Trong Spring MVC, `spring.http.codecs.max-in-memory-size` không phải property giới hạn file multipart của Servlet. Cần dùng nhóm `spring.servlet.multipart.*` hoặc cấu hình tương ứng của embedded server/proxy.

## 14. WebFlux multipart: giới hạn memory và temp disk

Spring Boot 3.5 hỗ trợ:

```properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=50MB
spring.webflux.multipart.max-parts=4
spring.webflux.multipart.max-headers-size=10KB
```

Ý nghĩa:

| Property | Điều kiểm soát |
|---|---|
| `max-in-memory-size` | Memory tối đa cho part; file lớn có thể chuyển sang disk tạm sau threshold |
| `max-disk-usage-per-part` | Dung lượng disk tối đa cho một part được lưu tạm |
| `max-parts` | Số part multipart tối đa trên request |
| `max-headers-size` | Bộ nhớ cho vùng headers của mỗi multipart part |

Mặc định của Boot 3.5: `max-in-memory-size` 256KB; `max-disk-usage-per-part` **-1B** và `max-parts` **-1** có ý nghĩa không áp giới hạn tương ứng. Khi server public upload endpoint, nên đặt giới hạn có chủ đích.

Những setting này không tự áp đặt quota tổng trên từng người dùng hoặc dung lượng cả disk. Với `Flux<PartEvent>` streaming trực tiếp, giới hạn liên quan file temp có thể không áp dụng theo cách của `FilePart`; cần đếm bytes và giới hạn trên pipeline thực tế.

## 15. Backpressure, blocking và concurrency

**Backpressure** cho phép subscriber downstream yêu cầu lượng dữ liệu mà nó có thể tiêu thụ, giúp nguồn reactive tránh phát quá nhiều phần tử vào pipeline. Khi sink lưu trữ chậm hơn network, một pipeline dùng backpressure đúng cách có thể giữ số buffer đang xử lý ở mức hữu hạn.

```text
Network Flux<DataBuffer>
         |
   demand/backpressure
         |
    async file writer
         |
   bounded in-flight data
```

Nhưng các mẫu sau phá mục tiêu streaming:

```java
body.collectList();  // gom toàn bộ dữ liệu
```

```java
body.flatMap(buffer -> uploadPart(buffer), 1000);
```

Đoạn `flatMap` thứ hai là **snippet minh họa**: mức concurrency quá lớn có thể tạo rất nhiều operation in-flight, làm RAM và request queue tăng. Chọn mức concurrency/prefetch hợp lý và xử lý quyền sở hữu buffer.

**Không gọi** `Thread.sleep()`, `InputStream.read()`, JDBC blocking hoặc `.block()` trực tiếp trong event loop của WebFlux. Khi bắt buộc tích hợp blocking SDK, cô lập trên `Schedulers.boundedElastic()` với giới hạn và theo dõi tải. Với Servlet MVC, I/O blocking là mô hình thường gặp nhưng cần quan sát thread usage và timeout.

## 16. Giới hạn tổng bytes và Content-Length

Để bảo vệ server, nên có nhiều lớp:

1. Reverse proxy/WAF/Ingress giới hạn request size và upload duration.
2. Embedded server giới hạn timeout, connections, headers và những body limits áp dụng.
3. Application kiểm tra authentication, quyền upload và quota tenant.
4. Streaming code **đếm bytes thực nhận**, dừng nếu vượt limit.
5. Storage có quota disk/object, staging cleanup và checksum.

`Content-Length` hữu ích để từ chối sớm, nhưng có thể thiếu hoặc không đủ tin cậy. Không được dùng nó làm **biện pháp duy nhất**. Spring MVC ví dụ mục 6 kiểm tra từng `read()` và thường trả HTTP **413 Payload Too Large** khi vượt 50 MiB.

WebFlux raw example mục 9 chưa áp tổng byte limit; muốn deploy thật phải thêm ràng buộc byte-count trước khi ghi, đảm bảo các buffer bị discard/released đúng cách, xóa file chưa hoàn thành và phản hồi status theo error contract. Không coi multipart disk threshold là body size limit tổng.

## 17. Hủy upload, lỗi I/O và file staging

Upload có thể bị hỏng giữa chừng do browser đóng, proxy timeout, disk full, upstream chậm, client cancel hoặc server restart.

Một quy trình an toàn:

```text
Input stream
    |
    v
Server-generated staging path
    |
    +---- error/cancel/quota -> delete + audit
    |
    v
Kiểm tra byte count / checksum / loại file / malware
    |
    v
Atomic move hoặc publish object
    |
    v
Commit metadata + response thành công
```

File staging không nên được public cho download trước khi hoàn tất validation. Khi thành công, có thể chuyển sang vị trí cuối bằng atomic move nếu filesystem hỗ trợ, hoặc hoàn tất object-storage multipart upload.

Trong reactive pipeline, cleanup với `onError`, `doFinally`, `usingWhen` cần quản lý cancellation đúng; thao tác filesystem blocking nên chạy trên scheduler được phép block. Khi process bị kill, callback dọn tài nguyên **không được bảo đảm**; cần job dọn staging file mồ côi theo TTL.

Các ví dụ học tập ở trên minh họa đường dữ liệu chính chứ không phải upload service production hoàn chỉnh; những bước safety này là yêu cầu thiết kế bổ sung.

## 18. Truyền tiếp dữ liệu vào object storage hoặc xử lý từng bản ghi

Thay vì local file, dữ liệu có thể đi thẳng tới downstream:

```text
HTTP body -> bounded buffers -> incremental checksum
          -> asynchronous multipart SDK -> object storage
```

Phải kiểm tra SDK có stream thực hay ngầm gom toàn bộ vào `byte[]`. Với multipart upload, bộ nhớ có thể bằng **part size × số phần đang upload đồng thời**, cộng overhead. Giới hạn concurrency và prefetch là yếu tố bắt buộc.

Với dữ liệu dạng nhiều record, cân nhắc **NDJSON** (JSON Lines) thay vì một mảng JSON rất lớn:

```text
{"id":1,"value":"a"}
{"id":2,"value":"b"}
{"id":3,"value":"c"}
```

Một đoạn WebFlux theo record:

```java
@PostMapping(
    path = "/events",
    consumes = "application/x-ndjson")
public Mono<Void> receive(
        @RequestBody Flux<EventDto> records) {
    return records.concatMap(eventService::save).then();
}
```

Đây là **method minh họa** bên trong controller WebFlux, cần định nghĩa `EventDto` và `eventService.save` trả reactive publisher. `concatMap` xử lý lần lượt thay vì `collectList()`; nếu `save` dùng JDBC blocking thì vẫn phải xử lý phần blocking đúng cách.

Trong streaming JSON, decoder có thể gom **một record**, nên vẫn cần giới hạn record size. Một record hàng trăm MB đi ngược mục tiêu dù toàn request được gọi là stream.

## 19. Kiểm thử: chức năng, bộ nhớ và tính toàn vẹn

Một kiểm thử đủ tốt nên bao gồm:

- **File nhỏ:** gửi 16 byte, xác nhận response và file đích có đúng 16 byte.
- **Boundary size:** request dưới, đúng bằng và vượt giới hạn.
- **Integrity:** so SHA-256 file gốc với file đã lưu.
- **Concurrency:** nhiều uploads đồng thời, đo heap, direct memory, threads, disk và throughput.
- **Client disconnect:** hủy giữa chừng, xác minh không công bố file dang dở.
- **Slow upload:** thử client gửi body rất chậm, kiểm tra timeouts và quota.
- **Disk full:** kiểm tra lỗi, cleanup và logging.
- **Proxy path:** test qua CDN/Ingress/Gateway thật vì mỗi tầng có thể buffer hoặc từ chối.
- **Reactive buffer leaks:** test error/cancel trên pipeline tùy biến `DataBuffer`.
- **Sensible response:** kiểm tra status, JSON error format và không lộ dữ liệu nhạy cảm.

Tạo file 1 MiB trên Linux/macOS:

```bash
dd if=/dev/zero of=one-mib.bin bs=1048576 count=1
```

Upload raw:

```bash
curl -i -H 'Content-Type: application/octet-stream' \
  --data-binary @one-mib.bin \
  http://localhost:8080/api/upload/raw
```

Upload multipart WebFlux:

```bash
curl -i -F "file=@one-mib.bin" \
  http://localhost:8080/api/upload/file
```

Kiểm tra checksum:

```bash
sha256sum one-mib.bin uploads/<ten-file-thuc-te>
```

Thay tên file thực tế dựa trên response; nếu file được lưu đúng nguyên bytes, hash hai file sẽ bằng nhau.

## 20. Kiểm thử MockMvc cho ví dụ Servlet

Với `spring-boot-starter-test` trong project MVC Spring Boot 3.5, file `src/test/java/com/example/streaming/RawUploadControllerTest.java`:

```java
package com.example.streaming;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RawUploadControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void countsBytesWithoutLoadingWholeFile() throws Exception {
        mvc.perform(post("/api/upload/raw")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .content("abc".getBytes(StandardCharsets.UTF_8)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.bytes").value(3));
    }
}
```

Chạy trong project:

```bash
./mvnw test
```

Test kiểm tra status và số byte; **không** khẳng định chắc chắn cách mạng truyền chunks hoặc memory profile. Do example lưu file local, test suite thực tế nên cách ly storage vào temp directory, dọn file test và kiểm tra checksum. Với WebFlux, dùng `WebTestClient` thay vì `MockMvc`; muốn kiểm tra backpressure hoặc cancellation phải có test phù hợp với reactive pipeline.

## 21. Các lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân | Cách điều tra |
|---|---|---|
| Heap tăng theo kích thước file | `getBytes()`, `byte[]`, `collectList()`, `join()` | Dò bước aggregation, chuyển sang buffer/record stream |
| `DataBufferLimitException` | Codec cần gom nội dung quá giới hạn | Kiểm tra kiểu body, codec, record size; không tăng vô hạn |
| Temp disk đầy | Multipart parser lưu các part ra disk | Cấu hình giới hạn disk/part, quota, cleanup |
| WebFlux bị nghẽn event loop | Filesystem/JDBC/SDK blocking chạy sai scheduler | Dùng async API hoặc boundedElastic có giới hạn |
| Direct memory tăng | Pooled `DataBuffer` bị giữ hoặc không release | Kiểm tra lifecycle, cancellation và leak detector |
| Upload chậm dù heap ổn | Sink storage/network chậm | Đo từng hop, throughput, concurrency |
| Có file dở dang | Không xử lý cancel/lỗi hoặc process kill | Staging, cleanup và background sweeper |
| 413 khi backend cho phép | Proxy/CDN/WAF có limit thấp hơn | Kiểm tra giới hạn toàn chuỗi |
| Multipart file lỗi trước controller | Multipart resolver vượt max-file/request-size | Xem properties và container logs |
| Kết quả upload sai hash | Copy sai số byte, ghi dở, logic retry | Kiểm tra file size, checksum, atomic publish |

**Không khắc phục tất cả những triệu chứng này bằng cách tăng memory limit.** Việc tăng `spring.http.codecs.max-in-memory-size` có thể khiến aggregation giữ nhiều bộ nhớ hơn, chính là điều cần tránh khi payload lớn.

## 22. Bảo mật và vận hành

Upload là đầu vào không tin cậy; cần:

1. Authentication/authorization, quota và rate limit theo user/tenant.
2. Không dùng original filename để xác định disk path; chọn tên phía server và sanitize metadata.
3. Không tin MIME type do client gửi; xác minh magic bytes/loại nội dung khi cần.
4. Hạn chế disk, inode, total in-flight uploads, timeouts và request lifetime.
5. Chỉ publish sau khi checksum, malware scanning và validation cần thiết hoàn tất.
6. Không log raw body, tokens hoặc dữ liệu cá nhân; log request ID, byte count và thời gian xử lý.
7. Đặt chính sách TTL và dọn file staging bị bỏ lại.
8. Khi dùng object storage, áp least privilege cho SDK credentials và ký URL có thời hạn.
9. Xác thực hash khi relay dữ liệu sang upstream để phát hiện bị cắt giữa chừng.
10. Theo dõi heap, direct memory, disk, network, connection pool và event-loop saturation.

Với upload nhiều gigabyte, có thể cân nhắc **pre-signed URL** cho client upload trực tiếp lên object storage rồi backend xác nhận metadata. Cách đó giảm lượng dữ liệu phải đi xuyên Spring Boot, nhưng phải kiểm soát quyền, loại nội dung, dung lượng và vòng đời của URL được ký.

## 23. Ghi nhớ và tài liệu tham khảo

**Ghi nhớ:** Streaming nghĩa là **không cần nắm giữ toàn bộ request body trong RAM**. Trong MVC, dùng `InputStream`/buffer hoặc multipart transfer; trong WebFlux, dùng `Flux<DataBuffer>`, `FilePart.transferTo` hoặc `Flux<PartEvent>` khi cần xử lý multipart sát từng buffer. Bộ nhớ vẫn cần giới hạn, và giải pháp production phải có byte-count, backpressure, quota, cleanup và kiểm tra integrity.

- Spring Framework — WebFlux reactive, limits, DataBuffer: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework — WebFlux @RequestBody: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework — Multipart WebFlux, FilePart, PartEvent: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Framework — DataBufferUtils Javadoc: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html
- Spring Framework — MVC @RequestBody: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — MVC Multipart: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/multipart-forms.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 — MultipartProperties: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/MultipartProperties.html
- Spring Boot 3.5 — ReactiveMultipartProperties: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/reactive/ReactiveMultipartProperties.html
