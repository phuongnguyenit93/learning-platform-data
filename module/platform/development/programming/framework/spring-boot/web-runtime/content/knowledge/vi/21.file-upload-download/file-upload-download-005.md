# Nhận tệp lớn theo luồng và giới hạn bộ nhớ theo web stack

> Phạm vi: Spring Boot web-runtime, Java 17+, Spring Boot 3.3 / Spring Framework 6.1. Trọng tâm là upload tệp lớn, khác biệt giữa Spring MVC trên Servlet và Spring WebFlux trên Reactor Netty, giới hạn heap/direct memory, lưu đĩa tạm và cách xác nhận upload hoàn tất.

## 1. Mục tiêu

Sau bài học, bạn có thể:

1. Giải thích tại sao upload 1 GiB không bắt buộc cần một mảng 1 GiB trong bộ nhớ ứng dụng.
2. Phân biệt streaming từ socket, streaming từ một multipart part đã được parser lưu vào đĩa tạm, và streaming qua reactive DataBuffer.
3. Phân biệt giới hạn tổng request, kích thước file, số multipart part, memory threshold, codec aggregation và disk quota.
4. Viết handler Spring MVC dùng MultipartFile và HttpServletRequest.getInputStream() mà không gọi getBytes().
5. Viết handler WebFlux dùng FilePart.transferTo(Path) và Flux<DataBuffer> để nhận tệp mà không gom tất cả bytes.
6. Giải thích khi nào phải release DataBuffer, dùng PartEvent và xử lý cancellation.
7. Thiết kế thử nghiệm quá giới hạn, client disconnect, nhiều upload đồng thời và quan sát heap, direct memory, disk, thời gian chờ.

## 2. Streaming upload khác với “đã nhận tệp hoàn chỉnh”

Một client gửi 500 MiB qua HTTP. Server có thể đọc dữ liệu theo các block khoảng 64 KiB, ghi chúng xuống file tạm, rồi khi đã nhận đủ bytes và xác thực nội dung mới chuyển file tạm thành file hợp lệ.

~~~text
client
  |
  | HTTP request body (multipart hoặc raw binary)
  v
proxy / ingress / load balancer
  |  (có thể buffer request vào RAM hoặc đĩa)
  v
HTTP server (Servlet container hoặc Reactor Netty)
  |
  +--> multipart parser, nếu là multipart
  |      (có thể giữ RAM hoặc spool ra đĩa)
  |
  v
controller / reactive pipeline
  |
  | chunks / input stream / FilePart / DataBuffer
  v
private temporary file
  |
  | nhận xong + kiểm tra size/checksum/định dạng
  v
published file / object storage / metadata
~~~

“Streaming” là chiến lược không bắt buộc tích lũy toàn bộ nội dung trong bộ nhớ tại nơi đang xử lý. Cần nói rõ **tầng nào streaming**: client tới proxy, proxy tới container, container tới handler, hay handler tới nơi lưu trữ. Một handler đọc MultipartFile.getInputStream() theo 64 KiB/lần tiết kiệm heap, nhưng file part có thể đã được container parse và lưu trước khi handler được gọi.

Ngược lại, dùng byte[] hay String làm kiểu tham số cho body lớn, gọi MultipartFile.getBytes(), DataBufferUtils.join() không giới hạn hoặc Flux<DataBuffer>.collectList() có thể tạo áp lực bộ nhớ theo kích thước file. Kích thước file càng lớn, số upload đồng thời càng cao, rủi ro OutOfMemoryError và GC càng rõ.

### Hai kiểu request thường dùng

| Kiểu | Content-Type | Payload | Lựa chọn API |
|---|---|---|---|
| Multipart form | multipart/form-data | Một hoặc nhiều file part, có boundary, headers và form fields | MVC: MultipartFile; WebFlux: FilePart hoặc Flux<PartEvent> |
| Raw binary | application/octet-stream | Toàn bộ body là bytes của một tệp | MVC: HttpServletRequest.getInputStream(); WebFlux: Flux<DataBuffer> |

Với multipart, **kích thước của một file** không nhất thiết bằng **kích thước của request**. Request còn chứa boundaries, headers, các field và có thể nhiều file. Với raw body, các thuộc tính cấu hình multipart có thể không áp dụng. Cả hai kiểu đều cần chính sách giới hạn toàn bộ traffic ở proxy và application.

## 3. Tại sao Content-Length chưa đủ để giới hạn upload?

Header Content-Length có thể giúp từ chối sớm khi biết request body dài hơn mức cho phép, nhưng không nên làm lớp bảo vệ duy nhất:

- Client có thể gửi request không có Content-Length, tùy phiên bản HTTP/framing.
- Content-Length của một multipart message đo **toàn bộ body**, không nói chính xác bytes riêng của file part.
- Proxy có thể thay đổi cách chuyển tiếp, buffer hoặc giới hạn body.
- Một client không đáng tin có thể gửi metadata không phù hợp với dữ liệu thực tế; server phải dựa trên số bytes đã parse/đọc.
- Trong phản hồi lỗi, có thể đã có nhiều bytes được ghi vào file tạm, cần cleanup.

Vì vậy áp giới hạn bằng **multipart parser và/hoặc bộ đếm byte thực nhận**. Dùng Content-Length như phép từ chối nhanh khi có, không dùng nó thay vòng đếm byte.

## 4. Spring MVC/Servlet: MultipartFile được tạo như thế nào?

Ứng dụng có spring-boot-starter-web thường chạy Spring MVC trên embedded Servlet container, phổ biến là Tomcat. Boot 3.3 cấu hình multipart bằng Servlet Part API và StandardServletMultipartResolver. Khi request là multipart/form-data, container phân tích các part để cung cấp MultipartFile / Part cho controller.

~~~text
POST multipart/form-data
   |
   v
Servlet multipart handling
   |
   +-- phần nhỏ: có thể dùng RAM
   +-- phần lớn: spool vào đĩa tạm theo threshold/container
   |
   v
@RequestParam("file") MultipartFile
   |
   +-- getSize(): size metadata
   +-- getInputStream(): đọc bytes của part
   +-- transferTo(...): chuyển nội dung vào storage đích
   |
   v
application storage
~~~

Giá trị mặc định của Spring Boot 3.3:

| Thuộc tính | Mặc định | Ý nghĩa |
|---|---|---|
| spring.servlet.multipart.enabled | true | Bật multipart handling |
| spring.servlet.multipart.max-file-size | 1MB | Giới hạn kích thước một file |
| spring.servlet.multipart.max-request-size | 10MB | Giới hạn tổng multipart request |
| spring.servlet.multipart.file-size-threshold | 0B | Ngưỡng ghi file part xuống đĩa theo container |
| spring.servlet.multipart.location | Không đặt sẵn đường cố định | Vị trí intermediate multipart storage |
| spring.servlet.multipart.resolve-lazily | false | Điều khiển thời điểm resolver parse part |

**file-size-threshold=0B không có nghĩa tổng RAM sử dụng bằng 0.** Vẫn có socket/TLS buffers, metadata, object và overhead runtime; giá trị chủ yếu chi phối vùng lưu nội dung part. Khi multipart parser đã spool part, controller đọc getInputStream() theo block giúp tránh nạp lại toàn bộ file vào heap.

### Cấu hình một demo cho file 32 MiB

File src/main/resources/application.properties của ứng dụng MVC:

~~~properties
spring.servlet.multipart.enabled=true
spring.servlet.multipart.max-file-size=32MB
spring.servlet.multipart.max-request-size=34MB
spring.servlet.multipart.file-size-threshold=0B
~~~

Mức 34MB tạo khoảng dư so với 32MB cho multipart boundaries và metadata của **demo một file**. Đây không phải công thức cho upload nhiều file. Nếu lưu trữ tạm ở một mount riêng có quota, có thể chỉ định spring.servlet.multipart.location tới thư mục tồn tại và được container cho phép ghi.

Không đặt -1 (không giới hạn) cho file size hay request size chỉ để chữa lỗi 413 khi upload file lớn. Đầu tiên hãy xác định tải dự kiến, giới hạn disk, concurrency, tốc độ và thời gian tối đa.

## 5. Ví dụ Spring MVC runnable: multipart và raw streaming

Chuẩn bị một **dự án Spring Boot 3.3 + Java 17+ riêng**, có starter-web. Phần dependency trong build.gradle (Groovy DSL):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Dự án giả định đã cấu hình Spring Boot Gradle plugin, repositories và dependency management. Tạo lớp chính tại src/main/java/example/mvcupload/MvcUploadApplication.java:

~~~java
package example.mvcupload;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class MvcUploadApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcUploadApplication.class, args);
    }

    @RestController
    public static class UploadController {
        private static final long MAX_BYTES = 32L * 1024 * 1024;
        private static final Path STORAGE =
                Path.of(System.getProperty("java.io.tmpdir"),
                        "mvc-upload-lab");

        @PostMapping(
                path = "/upload/multipart",
                consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
        @ResponseStatus(HttpStatus.CREATED)
        public Receipt multipart(
                @RequestParam("file") MultipartFile file)
                throws IOException {
            if (file.isEmpty()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Empty file");
            }
            if (file.getSize() > MAX_BYTES) {
                throw new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE, "Too large");
            }
            try (InputStream in = file.getInputStream()) {
                return save(in);
            }
        }

        @PostMapping(
                path = "/upload/raw",
                consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
        @ResponseStatus(HttpStatus.CREATED)
        public Receipt raw(HttpServletRequest request)
                throws IOException {
            try (InputStream in = request.getInputStream()) {
                return save(in);
            }
        }

        private Receipt save(InputStream input) throws IOException {
            Files.createDirectories(STORAGE);
            Path temporary = Files.createTempFile(
                    STORAGE, "partial-", ".tmp");

            try {
                byte[] block = new byte[64 * 1024];
                long total = 0;
                try (OutputStream output =
                             Files.newOutputStream(temporary)) {
                    int n;
                    while ((n = input.read(block)) != -1) {
                        if (n == 0) {
                            continue;
                        }
                        if (n > MAX_BYTES - total) {
                            throw new ResponseStatusException(
                                    HttpStatus.PAYLOAD_TOO_LARGE,
                                    "Too large");
                        }
                        output.write(block, 0, n);
                        total += n;
                    }
                }

                if (total == 0) {
                    throw new ResponseStatusException(
                            HttpStatus.BAD_REQUEST, "Empty file");
                }
                String id = UUID.randomUUID() + ".bin";
                Files.move(temporary, STORAGE.resolve(id));
                return new Receipt(id, total);
            } finally {
                Files.deleteIfExists(temporary);
            }
        }

        public record Receipt(String id, long bytes) { }
    }
}
~~~

### Giải thích từng quyết định trong mã MVC

- MultipartFile chỉ cung cấp part đã được multipart infrastructure quản lý. getSize() có thể hỗ trợ từ chối sớm **sau parsing**, nhưng phương thức save() vẫn đếm bytes thực đọc. Khi part đã vượt giới hạn của container, handler thường không được gọi.
- Endpoint raw đọc HttpServletRequest.getInputStream(), mỗi lần tối đa 64 KiB và ghi ngay vào file tạm. Mảng 64 KiB **không lớn lên theo kích thước file**; đọc socket có thể chặn Servlet worker thread nếu client chậm.
- Điều kiện n > MAX_BYTES - total tránh cộng tràn số trong phép đếm. Upload phải đạt EOF bình thường, kích thước hợp lệ và ghi xong mới được đổi tên.
- Tệp tạm nằm trong cùng thư mục lưu cuối, để Files.move thường rẻ hơn copy xuyên filesystem. Tuy vậy, Java không bảo đảm mọi Files.move đều atomic hay đã fsync xuống disk; cần yêu cầu lưu trữ riêng nếu có cam kết bền vững.
- finally dọn temporary nếu quá limit, đọc lỗi, ghi lỗi hoặc move lỗi. Khi move thành công, đường tạm cũ đã mất nên deleteIfExists không ảnh hưởng file cuối.
- Id do server sinh bằng UUID, không lấy MultipartFile.getOriginalFilename() làm đường dẫn. Tên file client có thể nguy hiểm hoặc gây ghi đè.
- Thư mục dưới java.io.tmpdir chỉ dành cho lab. Production cần volume/object storage riêng, quyền truy cập giới hạn, quota, cleanup và scanning.

**Không dùng MultipartFile.getBytes()** trong ví dụ này. Nó sẽ tạo byte array cho toàn nội dung file. Ngay cả khi multipart part đã được spool vào disk, gọi getBytes() có thể kéo toàn file trở lại heap.

Chạy trên Linux/macOS bằng `./gradlew bootRun` hoặc Windows bằng `gradlew.bat bootRun`. Ứng dụng mặc định nhận HTTP trên port 8080 nếu chưa đổi cấu hình.

## 6. Multipart MVC không phải streaming HTTP trực tiếp tới controller

Đường đi của hai endpoint khác nhau:

~~~text
Multipart:
socket -> container multipart parser -> RAM/disk part storage
      -> MultipartFile.getInputStream() -> 64KiB buffer -> temp -> final

Raw:
socket -> HttpServletRequest.getInputStream()
      -> 64KiB buffer -> temp -> final
~~~

Ở multipart, việc gọi getInputStream() theo block là **streaming ở tầng xử lý ứng dụng**, nhưng không cam kết controller thấy bytes ngay khi từng byte từ socket đến. Trong Servlet implementation, container có thể parse trước khi cung cấp MultipartFile.

Ở raw, controller có thể đọc dần request body từ ServletInputStream, nhưng read() là blocking I/O theo mô hình Servlet truyền thống. Nếu 100 client gửi rất chậm, số worker thread, timeouts và connection limits là những tài nguyên cần quản lý. Nếu reverse proxy bật request buffering, raw request có thể cũng đã được proxy lưu trước khi app nhận.

Các giới hạn spring.servlet.multipart.* không tự áp dụng cho **raw body**; vì vậy code raw cần byte counter, còn gateway cần body-size/timeouts. Không suy luận việc max-file-size=32MB sẽ tự bảo vệ mọi endpoint nhận application/octet-stream.

## 7. Spring WebFlux: khác biệt FilePart, DataBuffer, PartEvent

Khi dùng **spring-boot-starter-webflux** và Reactor Netty, handler có thể nhận file theo các abstraction khác:

| API | Content-Type | Ý nghĩa | Cạm bẫy |
|---|---|---|---|
| FilePart | multipart/form-data | Multipart reader quản lý part và cung cấp transferTo(Path) trả Mono<Void> | Parser có thể giữ part ở RAM/đĩa; không phải direct socket API |
| Flux<DataBuffer> | application/octet-stream | Reactive stream của các buffer chứa bytes raw body | Không được collectList/join vô hạn; phải quản lý release/cancellation |
| Flux<PartEvent> | multipart/form-data | Nhận tuần tự các event của từng part, có thể chuyển tiếp từng segment | Phải phân tách part, consume/release tất cả buffers, tự thực hiện byte cap |

Reactive backpressure cho phép các stage phối hợp tốc độ theo demand, nhưng **không phải quota**. Nếu disk đầy, controller tạo hàng đợi quá lớn hoặc buffer bị giữ mà không release thì ứng dụng vẫn có thể hết tài nguyên.

### Các giới hạn WebFlux trong Boot 3.3

| Property | Giá trị mặc định | Mô tả |
|---|---|---|
| spring.webflux.multipart.max-in-memory-size | 256KB | Non-file part bị giới hạn dung lượng gom; file part vượt threshold thì spill ra disk |
| spring.webflux.multipart.max-disk-usage-per-part | -1B | Mặc định không đặt giới hạn disk trên một part đã spool |
| spring.webflux.multipart.max-parts | -1 | Mặc định không giới hạn số part |
| spring.webflux.multipart.max-headers-size | 10KB | Giới hạn multipart headers trên từng part |
| spring.webflux.multipart.file-storage-directory | Thư mục spring-multipart dưới system temp | Đường tạm của multipart reader có spool; **bỏ qua cho streaming PartEvent** |
| spring.codec.max-in-memory-size | Boot không đặt giá trị chung; nhiều codec mặc định 256KB | Giới hạn khi codec cần **aggregate** input ở WebFlux server/WebClient đã auto-config |

Ví dụ src/main/resources/application.properties trong dự án WebFlux lab:

~~~properties
spring.webflux.multipart.max-in-memory-size=256KB
spring.webflux.multipart.max-disk-usage-per-part=32MB
spring.webflux.multipart.max-parts=4
spring.webflux.multipart.max-headers-size=10KB
spring.codec.max-in-memory-size=256KB
~~~

Mức 256KB ở multipart reader **không có nghĩa** một file 5 MiB bị cấm: nội dung file có thể được ghi xuống disk. Nó cũng **không phải** giới hạn 256KB cho tổng heap của một request, vì còn HTTP buffers, metadata, JSON codecs, socket buffers và các hoạt động khác.

max-disk-usage-per-part áp dụng trên file parts được parser lưu vào disk, không phải một global request cap. Với raw Flux<DataBuffer> và streaming PartEvent, cần đếm số byte do ứng dụng nhận. Không đặt max-in-memory-size=-1 chỉ để nhận file lớn, bởi cấu hình đó có thể dẫn đến giữ toàn bộ part trong RAM.

## 8. Ví dụ Spring WebFlux runnable: hai cách nhận file lớn

Tạo một dự án **riêng**, dùng Java 17+, Spring Boot 3.3 và duy nhất starter WebFlux:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Nếu dự án có cả starter-web và starter-webflux, Boot thường chọn MVC/Servlet theo mặc định; ví dụ dưới đây cần chạy WebFlux server để hành vi đúng như mô tả.

Tạo tệp src/main/java/example/reactiveupload/ReactiveUploadApplication.java:

~~~java
package example.reactiveupload;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Function;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveUploadApplication {
    public static void main(String[] args) throws IOException {
        Files.createDirectories(UploadController.STORAGE);
        SpringApplication.run(ReactiveUploadApplication.class, args);
    }

    @RestController
    public static class UploadController {
        private static final long MAX_BYTES = 32L * 1024 * 1024;
        private static final Path STORAGE =
                Path.of(System.getProperty("java.io.tmpdir"),
                        "webflux-upload-lab");

        @PostMapping(
                path = "/upload/part",
                consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
        public Mono<ResponseEntity<Receipt>> part(
                @RequestPart("file") FilePart file) {
            return save(file::transferTo);
        }

        @PostMapping(
                path = "/upload/raw",
                consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
        public Mono<ResponseEntity<Receipt>> raw(
                @RequestBody Flux<DataBuffer> requestBody) {
            AtomicLong count = new AtomicLong();

            Flux<DataBuffer> checked = requestBody
                    .<DataBuffer>handle((buffer, sink) -> {
                        int size = buffer.readableByteCount();
                        if (size > MAX_BYTES - count.get()) {
                            DataBufferUtils.release(buffer);
                            sink.error(new ResponseStatusException(
                                    HttpStatus.PAYLOAD_TOO_LARGE,
                                    "Too large"));
                        } else {
                            count.addAndGet(size);
                            sink.next(buffer);
                        }
                    })
                    .doOnDiscard(DataBuffer.class,
                            DataBufferUtils::release);

            return save(path ->
                    DataBufferUtils.write(checked, path));
        }

        private Mono<ResponseEntity<Receipt>> save(
                Function<Path, Mono<Void>> writeToFile) {
            return Mono.usingWhen(
                    Mono.fromCallable(() ->
                            Files.createTempFile(
                                    STORAGE, "partial-", ".tmp"))
                        .subscribeOn(Schedulers.boundedElastic()),

                    temp -> writeToFile.apply(temp)
                            .then(Mono.fromCallable(() -> publish(temp))
                                    .subscribeOn(
                                            Schedulers.boundedElastic()))
                            .map(receipt -> ResponseEntity
                                    .status(HttpStatus.CREATED)
                                    .body(receipt)),

                    this::removeTemp
            );
        }

        private Receipt publish(Path temp) throws IOException {
            long size = Files.size(temp);
            if (size == 0) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Empty file");
            }
            if (size > MAX_BYTES) {
                throw new ResponseStatusException(
                        HttpStatus.PAYLOAD_TOO_LARGE, "Too large");
            }

            String id = UUID.randomUUID() + ".bin";
            Files.move(temp, STORAGE.resolve(id));
            return new Receipt(id, size);
        }

        private Mono<Void> removeTemp(Path temp) {
            return Mono.fromRunnable(() -> {
                        try {
                            Files.deleteIfExists(temp);
                        } catch (IOException ex) {
                            throw new UncheckedIOException(ex);
                        }
                    })
                    .subscribeOn(Schedulers.boundedElastic())
                    .then();
        }

        public record Receipt(String id, long bytes) { }
    }
}
~~~

### Vì sao code WebFlux có hai đường tách biệt?

**/upload/part** nhận FilePart. Multipart reader quyết định giữ part trong RAM/đĩa tạm dựa trên các thuộc tính multipart. FilePart.transferTo(Path) trả Mono<Void> để xử lý hoàn tất mà không cần block() trong controller. Sau transfer, ứng dụng còn xác minh kích thước thực và xuất bản file.

**/upload/raw** nhận một Flux<DataBuffer>. Mỗi DataBuffer chứa một đoạn bytes. Toán tử handle tăng bộ đếm AtomicLong theo các buffer đã chấp nhận. Nếu vượt 32 MiB, buffer vừa nhận được release ngay và pipeline phát lỗi. Các buffer đã chuyển cho DataBufferUtils.write(Path) được API Path-overload ghi và quản lý release. doOnDiscard giải phóng DataBuffer bị bỏ khi cancel/error trong các operator hỗ trợ discard.

**Đừng nhầm các overload của DataBufferUtils.write:** overload ghi tới Path trả Mono<Void> có cơ chế hoàn tất/giải phóng khác với overload nhận OutputStream hoặc WritableByteChannel trả Flux<DataBuffer>, vốn **không tự release** buffer nguồn; code dùng các overload sau phải tự bảo đảm giải phóng.

**Mono.usingWhen** quản lý tài nguyên file tạm ở mức reactive: cung cấp path, thực thi writer, gọi cleanup ở các terminal path (success, error, cancel). Các thao tác Files.createTempFile, Files.size, Files.move, Files.deleteIfExists là I/O đồng bộ được đưa qua boundedElastic thay vì chạy trên Netty event loop. FilePart.transferTo có thể còn dùng internal file storage hoặc worker riêng; không được giả định toàn bộ đường ghi là “zero-copy”.

**Receipt chỉ được tạo sau khi writer complete và publish thành công.** FilePart max-disk-usage-per-part vẫn có vai trò bảo vệ parser trước khi controller nhận FilePart. Đường raw dùng bộ đếm riêng và không nhận được bảo vệ đó. Client hủy, lỗi đĩa hoặc process crash có thể làm còn file tạm; cần giám sát và dọn rác định kỳ ngoài request lifecycle.

**Giới hạn demo:** storage dưới java.io.tmpdir chỉ phù hợp local lab. Chưa tích hợp authentication, virus scan, checksum, quota per user, transaction metadata, filesystem durability hay direct-to-object-storage. Đừng công khai các endpoint như một dịch vụ production chỉ bằng mã demo này.

Chạy dự án bằng `./gradlew bootRun` (Unix) hoặc `gradlew.bat bootRun` (Windows).

## 9. Khi nào dùng PartEvent thay vì FilePart?

Ở WebFlux, @RequestBody Flux<PartEvent> là API streaming multipart ở mức các sự kiện part. Một file part có thể tạo nhiều FilePartEvent; FormPartEvent thể hiện form field. Thuộc tính PartEvent.isLast() đánh dấu event cuối **của part hiện tại**. Vì vậy có thể dùng windowUntil để chia event theo part, switchOnFirst để biết đó là loại part nào, rồi xử lý các DataBuffer nối tiếp.

Mẫu cấu trúc để nhận biết API (không phải handler lưu file hoàn chỉnh):

~~~java
// Trong một WebFlux controller có biến Flux<PartEvent> events:
events.windowUntil(PartEvent::isLast)
      .concatMap(partEvents ->
          partEvents.switchOnFirst((signal, window) -> {
              if (signal.hasValue()) {
                  PartEvent first = signal.get();
                  // Kiểm tra FormPartEvent hoặc FilePartEvent.
                  // Consume/relay/release toàn bộ window.
              }
              return window;
          }));
~~~

Đoạn trên chỉ minh họa cấu trúc phân đoạn; cần import đúng PartEvent, xử lý error/cancel và cài đặt phần lưu thực tế trước khi dùng. **Không** sao chép vào endpoint rồi tuyên bố file đã được lưu. Việc bỏ qua một event mà không giải phóng content() có thể rò rỉ direct memory khi Netty dùng pooled DataBuffer.

Lưu ý đặc biệt: spring.webflux.multipart.file-storage-directory áp dụng với multipart parsing có spooling, nhưng **không áp dụng cho PartEvent streaming** theo tài liệu Boot 3.3. Streaming PartEvent yêu cầu tự giới hạn số part, bytes, header/form metadata, thời gian nhận và tài nguyên lưu trữ; đừng suy ra max-disk-usage-per-part tự bảo vệ toàn bộ upload.

Đối với form thông thường chỉ cần lưu file, FilePart.transferTo thường đủ rõ ràng. PartEvent phù hợp hơn khi cần đọc/xử lý/relay từng segment ngay khi tới và sẵn sàng chịu thêm trách nhiệm buffer lifecycle.

## 10. Vì sao raw Flux<DataBuffer> cần quan tâm release?

Spring WebFlux DataBuffer có thể bọc Netty ByteBuf dùng pooled direct memory với reference counting. Nếu code giữ buffer trong list hoặc bỏ qua mà không release đúng quy tắc, memory/native allocation có thể không trở lại pool; heap graph đôi khi không nói lên đầy đủ.

Phân biệt:

- FilePart.transferTo(Path): để framework API ghi file và quản lý resource theo hợp đồng của method.
- DataBufferUtils.write(Publisher<DataBuffer>, Path): API làm việc với stream buffer và báo hoàn tất; cần kiểm tra contract chính xác cho overload bạn gọi.
- Tự consume DataBuffer trong map/subscribe: phải release khi đã đọc xong; nếu dùng filter/skip/flatMap có discard/cancel, thêm doOnDiscard phù hợp.
- DataBufferUtils.join() có thể tổng hợp buffers: **không dùng vô giới hạn** để xử lý hàng GiB; bản thân nó có phiên bản nhận maxByteCount, nhưng giới hạn đó khác việc streaming trực tiếp.
- Chuyển cho WebClient / ServerHttpResponse: xác định quyền sở hữu buffer và ai sẽ release sau khi relay; không retain/release thêm tùy tiện.

Nếu thấy direct memory tăng sau nhiều upload hủy ngang, kiểm tra pooled buffers và cleanup; không chỉ tăng JVM -Xmx. Bật Netty leak detection phù hợp trong test có thể hỗ trợ tìm buffer bị giữ, nhưng có overhead và không thay thế test tải/ngắt kết nối.

## 11. Memory budget và throughput cần tính theo concurrency

Giả sử MVC raw upload dùng byte[64 KiB] cho mỗi request đang đọc. Với 200 request đồng thời, **chỉ riêng mảng trong controller** chiếm:

~~~text
200 x 64 KiB = 12.800 KiB = 12,5 MiB
~~~

Điều này **không nói rằng** tổng bộ nhớ của 200 upload bằng 12,5 MiB: còn thread stack (MVC), socket buffers, TLS, multipart parser, JVM, OS page cache, object metadata, DB connection, direct/native memory và các thư viện trung gian.

Nếu đổi sang MultipartFile.getBytes() cho file 100 MiB với 200 upload đồng thời, chỉ một bản copy toàn file mỗi request đã cần:

~~~text
200 x 100 MiB = 20.000 MiB, gần 19,5 GiB
~~~

Chưa tính copy khác và GC. Streaming giảm một nguồn tăng bộ nhớ lớn, nhưng không loại mọi bottleneck.

**Disk bandwidth** cũng là giới hạn: nếu storage chỉ thực sự ghi được 100 MiB/s và mỗi file 20 MiB, thông lượng lý tưởng do disk write là khoảng 5 file/s trước khi tính overhead. Với multipart parser spool ra tệp tạm rồi ứng dụng copy sang storage cuối, có thể có nhiều lượt đọc/ghi cho cùng payload. Files.move trên cùng filesystem thường rẻ, nhưng move qua filesystem khác có thể không atomic và có thể thất bại/không được hỗ trợ.

Đối với WebFlux, phải quan sát cả heap **và** direct memory, số DataBuffer outstanding, event-loop lag, queue, số kết nối, file handles, temp disk, pending writes và bandwidth. Backpressure không đảm bảo finite storage nếu application tiếp tục chấp nhận upload mới vượt khả năng hệ thống.

## 12. Upload tệp lớn cần một chu trình trạng thái rõ ràng

Một chu trình thực dụng:

~~~text
RECEIVED REQUEST
   |
   v
authenticate + authorize + quota
   |
   v
allocate private temp / upload session ID
   |
   v
stream bytes + count + optional incremental checksum
   |
   +---- size exceeded / timeout / I/O error / cancel
   |             |
   |             v
   |        close + release + cleanup
   |
   v
stream complete
   |
   v
verify actual size, checksum, type, malware scan
   |
   v
publish file / object key
   |
   v
commit metadata and ownership
   |
   v
201 Created / confirmed upload
~~~

Từ request được chấp nhận đến file được publish là hai mốc khác nhau. Nếu client mất kết nối sau khi server ghi 90% body, không nên để file dở dang xuất hiện dưới tên final. File tạm giúp phân biệt trạng thái. Một ứng dụng có database và object storage cần thiết kế **compensation/outbox/idempotency** nếu publish file và commit metadata không cùng một transaction.

- **Timeout:** deadline tổng, idle timeout, tốc độ tối thiểu và giới hạn concurrent uploads. Client gửi 1 byte mỗi vài giây có thể giữ kết nối rất lâu.
- **Cancellation:** trong MVC, lần đọc tiếp theo có thể ném IOException; trong WebFlux có tín hiệu cancel. Không bảo đảm phát hiện client disconnect ngay tức thì.
- **Disk full:** ghi fail; cleanup có thể fail thêm. Log lỗi, cảnh báo dung lượng còn lại và có job dọn phần còn sót.
- **Process crash:** finally hoặc Mono.usingWhen không chạy nếu process bị kill đột ngột; cần scheduled cleanup dựa trên tuổi file tạm/session.
- **Retry:** không để retry tạo vô hạn bản sao. Cân nhắc idempotency key và thiết kế resumable/chunked upload khi file nhiều GiB.
- **Checksum:** có thể tính SHA-256 theo từng block trong quá trình stream hoặc sau khi lưu, so với checksum do client cung cấp theo trust model của ứng dụng.
- **Malware/type check:** Content-Type và extension client khai báo không đáng tin; kiểm tra magic bytes và quét nội dung trong vùng cách ly nếu nghiệp vụ yêu cầu.

Không chuyển nguyên file vào heap chỉ để kiểm checksum hoặc inspect MIME. Có thể đọc theo stream nhiều lần hoặc dùng một pipeline digest/validator có giới hạn bộ nhớ.

## 13. Thực hành qua curl

Tạo file mẫu 5 MiB trên Linux/macOS:

~~~bash
dd if=/dev/zero of=sample.bin bs=1048576 count=5
~~~

Trên Windows PowerShell:

~~~powershell
$bytes = New-Object byte[] (5 * 1024 * 1024)
[System.IO.File]::WriteAllBytes('sample.bin', $bytes)
~~~

Lệnh PowerShell cấp phát 5 MiB **ở máy tạo fixture**, không phải trong API upload. File tạo ra có đúng 5 x 1.048.576 = **5.242.880 byte**.

Chạy lần lượt **một** trong hai ứng dụng; chúng đều dùng port 8080 mặc định.

Đối với ứng dụng MVC:

~~~bash
curl -i -F "file=@sample.bin" http://localhost:8080/upload/multipart

curl -i -H "Content-Type: application/octet-stream" --data-binary @sample.bin http://localhost:8080/upload/raw
~~~

Đối với ứng dụng WebFlux:

~~~bash
curl -i -F "file=@sample.bin" http://localhost:8080/upload/part

curl -i -H "Content-Type: application/octet-stream" --data-binary @sample.bin http://localhost:8080/upload/raw
~~~

Trên Windows PowerShell, nếu curl là alias, hãy dùng curl.exe. Ở endpoint multipart, -F tự tạo Content-Type multipart và boundary; endpoint raw dùng --data-binary giữ nguyên bytes.

Response thành công phải có **HTTP 201 Created** và body JSON gồm id ngẫu nhiên cùng bytes = 5242880, ví dụ:

~~~json
{"id":"550e8400-e29b-41d4-a716-446655440000.bin","bytes":5242880}
~~~

UUID ở đây **chỉ là ví dụ minh họa**, không phải chuỗi chắc chắn trả ra. Hãy kiểm tra file có tồn tại, kích thước và checksum thật, không chỉ dựa vào status.

### Thử các trường hợp sai

- Gửi file rỗng: handler từ chối HTTP 400 trong code demo khi nó tới được handler.
- Gửi file 40 MiB: vượt mức 32 MiB, cần xác minh server từ chối theo lớp tương ứng (proxy, parser hoặc counter).
- Gửi file vừa dưới và đúng ngưỡng, cũng như file lớn hơn ngưỡng một byte: phân biệt phép so sánh đúng/sai.
- Gửi hai file parts khi controller chỉ nhận một; kiểm tra max-parts và total request-size.
- Gửi multipart field cực dài; kiểm tra header limit và non-file part aggregation.
- Hủy curl giữa upload; xác minh file .tmp không còn nếu lifecycle cleanup đã chạy và có job xử lý nếu process dừng đột ngột.
- Chạy qua ingress/reverse proxy; so thời gian byte đầu và disk usage với gọi thẳng server để tìm request buffering.

**Không khẳng định mọi lỗi vượt giới hạn đều trả cùng mã 413.** Tùy container, multipart parser, handler exception, proxy và cấu hình, lỗi có thể được ánh xạ khác nhau. Nếu hợp đồng API yêu cầu 413, bổ sung ExceptionHandler/ProblemDetail phù hợp và integration test cụ thể.

## 14. Load test upload: đo bytes/s và số phiên đồng thời

Upload khác JSON API thông thường. 100 request/s có thể là 100 file 1 KiB hoặc 100 file 1 GiB; RPS một mình không phản ánh khối lượng.

Trong mỗi phép thử, ghi:

- Kích thước/tỷ lệ file (p50, p95 size), raw vs multipart, tốc độ client upload, concurrent sessions.
- Offered requests/s, completed uploads/s, accepted bytes/s, written bytes/s, error/timeout/cancel rate.
- p50/p95/p99 thời gian hoàn tất upload và nếu cần thời gian nhận byte đầu/điểm bắt đầu xử lý.
- JVM heap, GC pauses, Netty direct memory, number of DataBuffer references, Servlet workers, queue/boundedElastic.
- Disk write throughput, free space, inodes, temp files, object storage latency, proxy buffering.
- Giai đoạn warm-up, steady-state, stress vượt ngưỡng và hồi phục sau khi giảm tải.

Một bài test 30 giây với một client nhanh không chứng minh system chịu được nhiều client chậm cùng lúc. Hãy kiểm tra **slow uploads**, **cancellation** và **soak** (duy trì nhiều giờ trong môi trường thử nghiệm khi phù hợp) để tìm memory/file leaks. Giới hạn rate và số connection để không làm cạn tài nguyên shared environment.

### Thước đo thành công

Năng lực chịu upload bền vững ở cấu hình cụ thể là mức offered upload rate / số upload đồng thời đạt mục tiêu completion time và error rate trong thời gian đủ dài, với disk/heap/native memory/queue ổn định, không tích lũy file tạm bất thường. Không gọi mức đỉnh vài giây là “maximum sustainable throughput”.

## 15. Rủi ro bảo mật và vận hành

**Không tin tên file của client.** MultipartFile.getOriginalFilename() hay FilePart.filename() có thể chứa path fragment, ký tự đặc biệt hoặc tên trùng. Nếu cần lưu tên gốc như metadata, chuẩn hóa và hiển thị an toàn; **path lưu thật** nên được server tạo, ở thư mục có quyền giới hạn.

**Không dùng phần mở rộng/MIME như bằng chứng nội dung.** Tệp upload có thể chứa script, malware, zip bomb, ảnh độc hại hoặc định dạng polyglot. Quét, validate và cô lập theo yêu cầu nghiệp vụ, đặc biệt trước khi cung cấp lại qua đường public.

**Phân quyền trước khi nhận hoặc publish.** Với file lớn, xác thực user, quota theo user, rate limit và hạn mức dự kiến nên được kiểm tra sớm. Sau upload phải kiểm ownership khi đọc/xóa; không để ID dự đoán là cơ chế bảo mật.

**Storage và cleanup là một phần API.** Đặt temp và final storage có quota/retention, thu dọn khi lỗi và khi process crash; cân nhắc file descriptor limits, symlink/hardlink race, quyền thư mục, object store và backup. Tải multipart nhiều part nhỏ cũng có thể gây DoS dù mỗi file không lớn.

**Không tắt giới hạn vì muốn “streaming”.** Streaming giảm nhu cầu giữ payload ở heap, nhưng không giới hạn disk, network, số request hoặc thời gian. Quota, content-length fast reject, actual byte counting và concurrency controls vẫn cần thiết.

## 16. Bảng phân biệt các lỗi phổ biến

| Triệu chứng | Khả năng nguyên nhân | Hành động cụ thể |
|---|---|---|
| Multipart file trên 1MB bị từ chối trong MVC | Default max-file-size=1MB | Đặt max-file-size và max-request-size có kiểm soát; kiểm tra proxy |
| Upload multipart 20MB lỗi dù max-file-size=32MB | max-request-size hoặc gateway limit thấp hơn; request có overhead hoặc nhiều part | Đọc actual exception và kiểm tra từng tầng |
| File 5MiB trong WebFlux có lỗi DataBufferLimitException | Body đang bị aggregate vào decoder/byte[]/String, hoặc non-file part quá ngưỡng | Dùng FilePart/Flux<DataBuffer> phù hợp; không tăng codec limit vô hạn |
| WebFlux multipart làm đầy disk tạm | max-disk-usage-per-part=-1, không có quota/cleanup | Đặt max-disk-usage-per-part, max-parts, storage quota |
| Raw upload vượt size nhưng vẫn ghi | Chỉ cấu hình spring.servlet.multipart.* | Thêm byte counter raw và gateway body cap |
| Heap tăng theo kích thước file | getBytes(), collectList(), join hoặc copy toàn body | Chuyển sang InputStream/transferTo/DataBuffer streaming |
| Direct memory tăng sau cancel | DataBuffer chưa release/không có doOnDiscard | Kiểm tra buffer lifecycle, leak detection và cancellation |
| Thời gian upload tăng, CPU thấp | Chờ client/disk/connection pool/thread | Đo I/O throughput, worker queues và slow client |
| Event loop WebFlux bị nghẽn | Files.* blocking hoặc SDK sync chạy trong reactive callback | Offload blocking operations khỏi event loop |
| Tệp bị lỗi sau client hủy | Ghi thẳng vào final file, không cleanup | Temp + publish after completion + cancel cleanup |
| Ghi đè file cũ | Dùng filename từ client hoặc ID tái sử dụng | Sinh UUID/ID server-side, kiểm tra ownership và collision |
| Upload qua proxy chậm hơn gọi trực tiếp | Proxy body buffering, timeout, TLS hoặc network | So cấu hình ingress và quan sát data path end-to-end |

## 17. Quy tắc chọn hướng triển khai

**Spring MVC có multipart form thông thường:** dùng MultipartFile, cấu hình kích thước/threshold, đọc getInputStream theo block hoặc transferTo khi hợp lý. Không gọi getBytes() với file lớn. Đo Servlet worker threads và multipart temp storage.

**Spring MVC cần raw body:** đọc HttpServletRequest.getInputStream() bằng buffer hữu hạn, đếm bytes, lưu vào temp. Nó tiết kiệm heap nhưng vẫn là blocking I/O, nên bảo vệ concurrency/timeout.

**Spring WebFlux multipart:** dùng FilePart.transferTo(Path), multipart memory/disk/parts limits và xử lý Mono completion/error. Metadata filesystem blocking cần offload nếu gọi trong pipeline.

**Spring WebFlux raw:** dùng @RequestBody Flux<DataBuffer> và writer phù hợp, tự đếm bytes, bảo đảm buffer release/discard/cancel. Không biến reactive stream thành List<DataBuffer> đầy đủ.

**Streaming multipart theo từng event:** Flux<PartEvent> khi cần relay/xử lý ngay, với trách nhiệm quản lý per-part limits, content buffers, cleanup và errors.

**Tệp nhiều GiB và object storage:** xem xét protocol resumable/multipart upload, pre-signed upload URL phù hợp mô hình bảo mật và nghiệp vụ, scan/checksum sau nhận, abort incomplete sessions. Không bắt buộc mọi byte đi qua JVM nếu server không cần inspect.

## 18. Câu hỏi ôn tập

**Câu 1.** Dùng MultipartFile.getInputStream() trong Spring MVC có chắc không dùng đĩa tạm không?  
**Trả lời:** Không. Servlet container có thể đã spool file part. Việc đọc stream chỉ tránh gom toàn bộ nội dung trong heap của controller.

**Câu 2.** file-size-threshold=0B nghĩa là không có byte nào trong RAM?  
**Trả lời:** Không. Đây là ngưỡng lưu part, không xóa các HTTP/TLS/metadata buffers hoặc overhead runtime.

**Câu 3.** Đặt spring.codec.max-in-memory-size=2GB có phải cách chuẩn cho upload file 2GB?  
**Trả lời:** Không. Đó là giới hạn aggregation của codec; thiết kế streaming và hard cap ở các tầng là phù hợp hơn.

**Câu 4.** max-disk-usage-per-part=32MB trong WebFlux có tự cấm raw upload 40MB?  
**Trả lời:** Không. Raw Flux<DataBuffer> không qua multipart file-part spooling; cần giới hạn bytes thực trong pipeline.

**Câu 5.** FilePart.transferTo trả Mono<Void> có nghĩa file đã được quét virus chưa?  
**Trả lời:** Không. Mono báo hoàn tất/lỗi của thao tác chuyển file. Validation, scanning, publish và metadata là bước nghiệp vụ riêng.

**Câu 6.** Vì sao phải cleanup khi cancel?  
**Trả lời:** Một phần payload có thể đã được ghi xuống disk; bỏ dở làm đầy temp storage hoặc khiến ứng dụng nhìn thấy dữ liệu chưa hoàn chỉnh.

**Câu 7.** Nếu code MVC chỉ cấp phát một mảng 64 KiB, tổng bộ nhớ upload có chắc bị giới hạn 64 KiB/request?  
**Trả lời:** Không. Còn container, socket, proxy, thread stacks, TLS, multipart parser và các tầng khác.

**Câu 8.** Backpressure trong WebFlux có tự giới hạn tổng byte mỗi upload?  
**Trả lời:** Không. Backpressure điều tiết tốc độ tiêu thụ; bytes cap/quota phải được thiết kế độc lập.

**Câu 9.** Có thể dùng Content-Length làm biện pháp hạn chế duy nhất không?  
**Trả lời:** Không. Có thể thiếu header hoặc thay đổi framing; parser và application phải đếm/giới hạn dữ liệu thực.

**Câu 10.** Kết quả 100 RPS upload 1KiB có chứng minh hệ chịu được 100 RPS upload 1GiB không?  
**Trả lời:** Không. Phải ghi file size distribution, bytes/s, concurrency, disk speed, memory và error SLO.

## 19. Tài liệu chính thức

- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): các giới hạn Servlet multipart, WebFlux multipart và codec.
- [Spring Boot – Handling Multipart File Uploads](https://docs.spring.io/spring-boot/how-to/spring-mvc.html): auto-configuration Servlet Part và file/request limits.
- [Spring Framework – Servlet Multipart Resolver](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html): StandardServletMultipartResolver và container parsing.
- [Spring Framework – WebFlux Multipart Content](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/multipart-forms.html): FilePart, PartEvent và streaming multipart.
- [Spring Framework – WebFlux Request Body](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html): reactive request-body streaming.
- [Spring Framework – Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): pooled DataBuffer và trách nhiệm release.
- [Spring Framework 6.1 DataBufferUtils API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): các overload write, join và release.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): request body, Content-Length và đặc điểm HTTP message.
