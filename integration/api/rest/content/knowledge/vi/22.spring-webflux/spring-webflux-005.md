# Body codec, giới hạn bộ đệm và xử lý nội dung lớn

> **Module:** `INTEGRATION_API_REST` — chương **Spring WebFlux**. Bài học thiết kế REST API với Java/Spring WebFlux theo resource, URI, HTTP method và status; đi sâu vào **đọc/ghi HTTP body bằng codec, giới hạn bộ nhớ, streaming/backpressure, upload/download dữ liệu lớn, bảo mật và kiểm thử**. Trọng tâm không phải biến mọi request thành reactive, mà là chọn cách biểu diễn và xử lý body không làm cạn RAM, ổ đĩa hoặc tài nguyên kết nối.

## 1. Tình huống: API đúng URI vẫn sập khi payload lớn

Hệ thống có hai API:

- `POST /v1/documents` nhận metadata JSON nhỏ rồi tạo resource.
- `POST /v1/uploads` nhận file 800 MiB. Một báo cáo khác có thể trả hàng triệu bản ghi.

Đoạn code tưởng tiện lợi:

~~~java
@PostMapping("/v1/uploads")
Mono<String> upload(@RequestBody Mono<byte[]> data) {
    return data.map(bytes -> "received=" + bytes.length);
}
~~~

`Mono<byte[]>` gom body trước khi xử lý, có thể gây `DataBufferLimitException`; tăng giới hạn lên 1 GiB khiến nhiều request đồng thời dễ hết RAM. Return type `Mono` **không tự tạo streaming**.

API phải quyết định **body được gom hay stream**, giới hạn byte thực, nơi lưu RAM/file/object storage và cách phản hồi khi client chậm hoặc vượt quota.

**Kết quả học tập:** chọn codec, cấu hình bộ đệm và quota, streaming upload/download, xử lý HTTP lỗi và kiểm thử WebFlux.

## 2. WebFlux xử lý body theo những lớp nào?

~~~mermaid
flowchart LR
    C["HTTP client"] --> S["Reactor Netty / HTTP server"]
    S --> M["WebFlux mapping / filters"]
    M --> R["HttpMessageReader / decoder"]
    R --> D["DataBuffer / DTO / Flux"]
    D --> L["Handler + service"]
    L --> W["HttpMessageWriter / encoder"]
    W --> C
~~~

WebFlux dựa trên Reactive Streams (`Publisher`, `Mono`/`Flux`). **Backpressure** cho consumer báo nhu cầu dữ liệu, nhưng các layer vẫn có thể buffer. Một phép gom toàn bộ phần tử làm mất ưu thế streaming.

| Thành phần | Nhiệm vụ | Cần chú ý |
|---|---|---|
| `HttpMessageReader` và decoder | Chuyển body thành object/chuỗi/luồng dữ liệu | Có codec cần gom byte để giải mã |
| `HttpMessageWriter` và encoder | Ghi object/stream thành representation HTTP | Không ép mọi stream thành JSON array lớn |
| `DataBuffer` | Một vùng byte được chuyển qua reactive pipeline | Có thể dùng bộ nhớ pooled/direct; phải quản lý vòng đời |
| `Mono<T>` | 0 hoặc 1 kết quả logic | `Mono<byte[]>` có thể chứa toàn bộ body trong RAM |
| `Flux<T>` | Nhiều phần tử theo thời gian | Không đảm bảo an toàn nếu `collectList()` |
| `DataBufferUtils` | Hỗ trợ đọc/ghi/join/giải phóng buffer | Dùng đúng overload, disposal và giới hạn |

### 2.1. Streaming và aggregation khác nhau

~~~text
BODY 800 MiB:
  bodyToMono(byte[].class)   -> gom toàn bộ bytes      -> nguy cơ RAM
  DataBufferUtils.join(...) -> gom buffer thành một    -> nguy cơ RAM
  flux.collectList()        -> giữ mọi phần tử         -> nguy cơ RAM
  Flux<DataBuffer> -> file  -> xử lý từng đoạn         -> có thể giới hạn RAM
  Flux<DTO> qua NDJSON      -> xử lý từng bản ghi       -> có giới hạn mỗi record
~~~

`Flux<DataBuffer>` vẫn có thể bị gom qua `buffer(100000)`, `reduce` hoặc `toIterable()`. Kiểm tra **toàn bộ pipeline**, không chỉ kiểu trả về controller.

### 2.2. Vì sao không `block()` trong request reactive?

Event-loop có ít luồng: `block()`, `Thread.sleep()`, JDBC blocking hoặc file I/O nặng có thể làm chậm nhiều request. Cô lập tác vụ blocking bất khả tránh trên `Schedulers.boundedElastic()` có kiểm soát, hoặc dùng R2DBC/API non-blocking; scheduler không làm storage nhanh hơn.

## 3. `Content-Type`, `Accept` và chọn body codec

Codec được chọn dựa trên **media type, kiểu Java và cấu hình WebFlux**. HTTP vẫn giữ nguyên ngữ nghĩa:

~~~http
POST /v1/documents HTTP/1.1
Host: api.example.test
Authorization: Bearer <token>
Content-Type: application/json
Accept: application/json

{"title":"WebFlux guide"}
~~~

`Content-Type` mô tả body gửi lên; `Accept` mô tả định dạng client chấp nhận ở phản hồi.

| Media type | Body phổ biến | Lựa chọn phù hợp |
|---|---|---|
| `application/json` | Một JSON object nhỏ | `Mono<CreateDocumentRequest>`, Jackson decoder |
| `application/x-ndjson` | Nhiều JSON objects phân cách newline | `Flux<EventDto>`, xử lý từng record |
| `text/event-stream` | Server-Sent Events từ server | `Flux<ServerSentEvent<T>>` |
| `application/octet-stream` | Byte nhị phân | `Flux<DataBuffer>`, streaming vào storage |
| `multipart/form-data` | Metadata và file part | `FilePart`/`Part`, spool/disk tùy reader |
| `application/problem+json` | Lỗi có cấu trúc | `ProblemDetail` hoặc DTO lỗi |

Đúng JSON nhưng client gửi `Content-Type: text/plain` vào handler chỉ `consumes=application/json` có thể nhận **415 Unsupported Media Type**. `Accept: application/xml` khi server chỉ viết JSON có thể dẫn tới **406 Not Acceptable**. Đúng media type nhưng JSON hỏng thường là **400 Bad Request**. Body vượt chính sách kích thước nên được báo **413 Content Too Large** khi tầng xử lý xác định rõ nguồn lỗi.

`Transfer-Encoding: chunked` chỉ là framing HTTP/1.1, **không** hỗ trợ resume; muốn tiếp tục sau mất mạng cần session/offset/part.

## 4. `maxInMemorySize` và `DataBufferLimitException`

Một số codec phải gom body hoặc từng phần tử trước khi parse; `maxInMemorySize` giới hạn lượng byte chúng buffer. Giá trị mặc định ở nhiều cấu hình là **256 KiB**, nhưng cần kiểm tra phiên bản và custom codecs.

~~~yaml
# application.yml: ví dụ Spring Boot WebFlux
spring:
  codec:
    max-in-memory-size: 512KB
~~~

Đây là **giới hạn aggregation**, **không phải quota upload 512 KB**. Streaming có thể truyền hàng GiB qua từng `DataBuffer`, nhưng một **JSON object đơn lẻ** quá lớn vẫn bị decoder từ chối.

### 4.1. Cấu hình WebFlux bằng Java

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.WebFluxConfigurer;
import org.springframework.http.codec.ServerCodecConfigurer;

@Configuration
class ApiCodecConfiguration implements WebFluxConfigurer {
    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {
        configurer.defaultCodecs().maxInMemorySize(512 * 1024);
    }
}
~~~

Đồng bộ Boot properties và custom codecs; cấu hình này không đặt giới hạn tổng request, session song song hay quota của reverse proxy.

### 4.2. Khi vượt giới hạn

~~~text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
~~~

Nguyên nhân thường gặp: `@RequestBody Mono<LargeDto>`, `bodyToMono(String.class)`, `bodyToMono(byte[].class)`, `DataBufferUtils.join(...)` hoặc một JSON record/part bị gom vượt giới hạn. Đừng chỉ tăng giới hạn lên mức hàng trăm MiB khi chưa đo heap và concurrency.

**Phân biệt lỗi:** exception từ việc đọc request body có thể được ứng dụng **ánh xạ thành 413** theo hợp đồng; nhưng exception tương tự ở WebClient khi **đọc response downstream** có thể là lỗi tích hợp 5xx/502 hoặc chính sách riêng. Không bắt mọi `DataBufferLimitException` toàn hệ thống rồi coi đó là lỗi của client. Mặc định HTTP response thực tế phụ thuộc version, exception handler và đường codec — **phải kiểm thử**.

### 4.3. Ba ngân sách độc lập

| Giới hạn | Áp dụng ở đâu | Nếu thiếu |
|---|---|---|
| `maxInMemorySize` | Buffer mà codec dùng khi giải mã/encode | Một object/element có thể ăn quá nhiều RAM |
| **Max request body/part size** | Gateway, server, endpoint hoặc pipeline byte | Streaming nhận vô hạn, hết disk/băng thông |
| **Quota tổng/concurrency/retention** | Tenant, user, số upload, disk/object storage | Nhiều request hợp lệ vẫn gây DoS hoặc chi phí lớn |

Thay vì “cấu hình 1 GiB maxInMemorySize”, hãy giữ codec limit hợp lý, dùng **streaming** và đặt upload quotas ở layer đúng.

## 5. JSON lớn: chọn cách biểu diễn trước khi chỉnh cấu hình

Với JSON array một triệu đơn, cân nhắc:

- **Pagination** (`GET /orders?limit=100&cursor=...`) cho truy vấn resource collection.
- **NDJSON streaming** khi cần xử lý từng record trong một kết nối.
- **Asynchronous export** (`POST /exports` → `202 Location` đến operation monitor) cho file xuất lớn, kéo dài.

### 5.1. Stream NDJSON với `Flux`

~~~java
import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

record OrderLine(String id, String status, String totalAmount) {}

@RestController
@RequestMapping("/v1/exports")
class OrderStreamController {
    private final OrderQuery query;
    OrderStreamController(OrderQuery query) {
        this.query = query;
    }

    @GetMapping(path = "/orders.ndjson",
                produces = "application/x-ndjson")
    @PreAuthorize("hasAuthority('SCOPE_orders.export')")
    Flux<OrderLine> export() {
        return query.visibleOrdersForCurrentCaller();
    }
}

interface OrderQuery {
    Flux<OrderLine> visibleOrdersForCurrentCaller();
}
~~~

Mỗi `OrderLine` được encoder phát dưới dạng một JSON record theo dòng. Vì vậy client có thể đọc từng phần tử mà không cần chờ tất cả record. **Nhưng** nếu một record chứa field blob dài 100 MiB, codec vẫn có thể bị giới hạn khi xử lý **record đó**. Giá trị ghi ra cũng phụ thuộc áp lực downstream, serialization, buffering ở proxy và cách client đọc.

Ở production, service phải biết caller/tenant đáng tin cậy, áp quota số record, timeout tổng, cancellation và pagination nếu phù hợp. Không tạo `Flux.fromIterable(repository.findAll())` nếu `findAll()` đã tải toàn bộ rows vào bộ nhớ trước.

### 5.2. Khi nên dùng SSE?

`text/event-stream` và `Flux<ServerSentEvent<T>>` phù hợp cập nhật tiến độ/nhiều sự kiện theo thời gian. SSE không phải giao thức tải file nhị phân hoặc cách thay thế pagination. Phải quản lý kết nối lâu, heartbeat, reconnect, auth và số subscriber; một client đọc chậm cần giới hạn hàng đợi và chính sách drop/disconnect hợp lý.

## 6. Raw binary upload: `Flux<DataBuffer>` và giới hạn byte thật

Giả sử `POST /v1/uploads/raw` nhận `application/octet-stream`, tối đa **100 MiB**. Body có thể không mang `Content-Length` (ví dụ truyền streaming); do đó chỉ kiểm tra header **không đủ**. Server phải đếm **byte thực nhận**, lưu vào vùng staging riêng tư rồi mới xác minh và publish.

~~~http
POST /v1/uploads/raw HTTP/1.1
Host: api.example.test
Authorization: Bearer <token>
Content-Type: application/octet-stream
Content-Length: 10485760

<10 MiB bytes>
~~~

### 6.1. Ví dụ controller streaming

~~~java
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/v1/uploads")
class RawUploadController {
    private static final long MAX_BYTES = 100L * 1024 * 1024;
    private final UploadService service;

    RawUploadController(UploadService service) {
        this.service = service;
    }

    @PostMapping(path = "/raw",
                 consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<ResponseEntity<UploadView>> upload(
            @AuthenticationPrincipal Jwt principal,
            @RequestHeader(value = "Content-Length",
                           required = false) Long declared,
            @RequestBody Flux<DataBuffer> body) {
        if (declared != null && declared > MAX_BYTES) {
            return Mono.error(new UploadTooLargeException());
        }
        return service.reserveAuthorized(principal.getSubject())
            .flatMap(session -> {
                AtomicLong received = new AtomicLong();
                Flux<DataBuffer> limited = body
                    .handle((buffer, sink) -> {
                        long next = received.addAndGet(
                            buffer.readableByteCount());
                        if (next > MAX_BYTES) {
                            DataBufferUtils.release(buffer);
                            sink.error(new UploadTooLargeException());
                        } else {
                            sink.next(buffer);
                        }
                    })
                    .doOnDiscard(DataBuffer.class,
                        DataBufferUtils::release);

                return DataBufferUtils.write(
                        limited, session.tempPath(),
                        StandardOpenOption.WRITE,
                        StandardOpenOption.CREATE_NEW)
                    .then(Mono.defer(() -> {
                        if (declared != null
                                && received.get() != declared) {
                            return Mono.error(
                                new UploadLengthMismatchException());
                        }
                        return service.verifyAndPublish(
                            session, received.get());
                    }))
                    .map(view -> ResponseEntity
                        .created(view.resourceUri())
                        .body(view))
                    .onErrorResume(error -> service
                        .discardStaging(session)
                        .then(Mono.error(error)));
            });
    }
}

record UploadView(String id, java.net.URI resourceUri) {}

interface UploadService {
    Mono<UploadSession> reserveAuthorized(String principal);
    Mono<UploadView> verifyAndPublish(
        UploadSession session, long bytes);
    Mono<Void> discardStaging(UploadSession session);
}

record UploadSession(String id, Path tempPath) {}
class UploadTooLargeException extends RuntimeException {}
class UploadLengthMismatchException extends RuntimeException {}
~~~

**Ý nghĩa:** không `collectList`/`join`; kiểm `Content-Length` sớm nếu có nhưng vẫn đếm byte thực. `DataBufferUtils.write(..., Path, ...)` ghi file mà không gom RAM; phải test release/discard pooled buffers. `tempPath` do server cấp. `verifyAndPublish` kiểm tra quyền, checksum và virus trước công bố; cô lập file I/O blocking khỏi event-loop. `discardStaging` cần idempotent; **cancellation không chạy qua `onErrorResume`**, nên bổ sung cleanup khi cancel và sweeper TTL.

Đây là skeleton; còn phải xử lý DB–storage commit, quota tổng, concurrent cancellation và retry. Muốn resume cần session/offset/part idempotent, không retry POST tạo file mới tùy tiện.

## 7. Multipart: `FilePart` không có nghĩa upload đã được giới hạn

Với `POST /v1/attachments`, client gửi `Content-Type: multipart/form-data; boundary=...` và part file có `Content-Disposition: form-data; name="file"; filename="report.pdf"`.

WebFlux có thể chuyển part lớn sang **disk tạm** theo cấu hình multipart reader. Vì vậy codec `maxInMemorySize` không thể được coi là quota tổng của mỗi file, và một ứng dụng vẫn có thể cạn **disk** dù heap ổn định.

~~~java
import org.springframework.http.*;
import org.springframework.http.codec.multipart.FilePart;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
class AttachmentController {
    private final AttachmentService service;
    AttachmentController(AttachmentService service) {
        this.service = service;
    }

    @PostMapping(path = "/v1/attachments",
                 consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Mono<ResponseEntity<AttachmentView>> create(
            @AuthenticationPrincipal Jwt caller,
            @RequestPart("file") FilePart part) {
        return service.reserve(caller.getSubject())
            .flatMap(slot -> part.transferTo(slot.tempPath())
                .then(service.scanAndPublish(slot, part))
                .map(view -> ResponseEntity
                    .created(view.uri()).body(view))
                .onErrorResume(error -> service
                    .discard(slot).then(Mono.error(error))));
    }
}
~~~

Các abstraction service/view/slot cần hiện thực; đo byte thật và giữ file trong staging cho tới khi scan/commit. Không dùng `part.filename()` làm path lưu trữ.

**Giới hạn multipart:** kiểm tra disk/part, số part, staging quota và cleanup theo phiên bản reader. `PartEvent` có thể stream trực tiếp từng part trong các phiên bản hỗ trợ, nhưng phải consume/release `DataBuffer` và phân nhóm part đúng.

## 8. Download lớn: stream `Resource`, không tạo `byte[]`

Khi file đã được kiểm tra và publish, endpoint có thể trả `Resource`. Đây là ví dụ với **file trên disk** để minh họa; ứng dụng object storage có thể dùng streaming SDK/HTTP client phù hợp.

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.*;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/v1/files")
class DownloadController {
    private final FileAccessService files;
    DownloadController(FileAccessService files) {
        this.files = files;
    }

    @GetMapping("/{id}/content")
    Mono<ResponseEntity<Resource>> download(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt caller) {
        return files.authorizedFile(caller.getSubject(), id)
            .map(meta -> ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                    ContentDisposition.attachment()
                        .filename(meta.safeName(),
                            StandardCharsets.UTF_8)
                        .build().toString())
                .cacheControl(CacheControl.noStore())
                .body(new FileSystemResource(meta.path())));
    }
}
~~~

`FileAccessService` phải kiểm tra owner/tenant, expiry và tình trạng file trước khi trả metadata/path. `FileSystemResource` cho phép WebFlux dùng resource writer để truyền nội dung, thay vì ép toàn file vào byte array. Nếu mục tiêu hỗ trợ resume download, thêm/kiểm thử chính sách HTTP **`Range`, `206 Partial Content`, `Content-Range`, `If-Range`, strong ETag và `416`**; không tự khẳng định mọi kiểu resource/proxy luôn có cùng xử lý range. Giới hạn đồng thời, tốc độ và băng thông cho từng caller.

Không truyền đường dẫn file do client gửi vào `FileSystemResource`. Nếu dùng signed URL tải trực tiếp qua object storage, nó là **bearer capability** có TTL/permission scope riêng, không phải quyền truy cập vô hạn.

## 9. WebClient cũng có giới hạn body codec độc lập

Ứng dụng có thể cấu hình server WebFlux ổn định nhưng vẫn lỗi khi gọi **downstream**:

~~~java
import org.springframework.web.reactive.function.client.WebClient;

WebClient client = WebClient.builder()
    .baseUrl("https://internal-api.example.test")
    .codecs(configurer ->
        configurer.defaultCodecs()
            .maxInMemorySize(512 * 1024))
    .build();
~~~

`client.get().retrieve().bodyToMono(String.class)` hoặc `bodyToMono(byte[].class)` có thể gom toàn bộ response. Nếu downstream trả 50 MiB, hãy chọn `bodyToFlux(DataBuffer.class)` rồi ghi từng phần vào file, hoặc `bodyToFlux(Dto.class)` với NDJSON có giới hạn mỗi record.

~~~java
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.MediaType;
import reactor.core.publisher.Mono;

Mono<Void> downloadToFile(WebClient client, Path target) {
    return client.get().uri("/v1/exports/latest")
        .accept(MediaType.APPLICATION_OCTET_STREAM)
        .exchangeToMono(response -> {
            if (!response.statusCode().is2xxSuccessful()) {
                // Không aggregate body lỗi có kích thước tùy ý.
                return response.releaseBody()
                    .then(Mono.error(
                        new IllegalStateException(
                            "Downstream export failed")));
            }
            return DataBufferUtils.write(
                response.bodyToFlux(
                    org.springframework.core.io.buffer.DataBuffer.class),
                target, StandardOpenOption.WRITE,
                StandardOpenOption.CREATE_NEW);
        });
}
~~~

`target` phải là path do ứng dụng kiểm soát, không lấy từ URL không tin cậy. Bổ sung giới hạn byte theo phép đếm, deadline, cleanup file chưa hoàn tất khi lỗi/cancel và validate checksum. Tránh gọi `bodyToMono(byte[].class)` chỉ để lấy `Content-Length`; header có thể thiếu hoặc không đáng tin. Một số `retrieve()`/`createException()` path còn có thể buffer **error body**, nên cần test cả response thành công và thất bại lớn.

**Backpressure không chặn SSRF:** URL ngoài cần allowlist host/scheme, kiểm soát DNS, redirect, timeout và credential forwarding.

## 10. HTTP lỗi và phản hồi khi payload quá lớn

| Nguyên nhân | Status thường phù hợp | Điều kiện |
|---|---|---|
| Media type body không hỗ trợ | `415 Unsupported Media Type` | Ví dụ gửi `text/plain` vào handler octet-stream |
| `Accept` không khớp output | `406 Not Acceptable` | API không thể tạo representation được chấp nhận |
| JSON malformed / length không khớp contract | `400 Bad Request` | Body không hợp lệ |
| Body vượt **giới hạn endpoint/request** | `413 Content Too Large` | Có thể từ chối sớm hoặc đang stream |
| Lỗi business file type/checksum | `422 Unprocessable Content` theo contract | Đã nhận bytes nhưng nội dung không chấp nhận |
| File ngoài quyền tenant | `403` hoặc `404` theo chính sách | Không được lộ sự tồn tại trái quyền |
| Quá nhiều upload đồng thời | `429 Too Many Requests` | Có thể kèm `Retry-After` |
| Disk/storage tạm không khả dụng | `503/500` tùy loại | Lỗi hạ tầng, không đổ lỗi cho client |

Ví dụ ứng dụng đã **chủ động phát hiện** vượt `MAX_BYTES`, advice chuyển domain exception thành 413:

~~~java
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
class UploadProblemAdvice {
    @ExceptionHandler(UploadTooLargeException.class)
    ResponseEntity<ProblemDetail> overLimit() {
        ProblemDetail p = ProblemDetail.forStatus(
            HttpStatus.PAYLOAD_TOO_LARGE);
        p.setTitle("Content too large");
        p.setProperty("code", "UPLOAD_LIMIT_EXCEEDED");
        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
            .contentType(MediaType.parseMediaType(
                "application/problem+json"))
            .cacheControl(CacheControl.noStore())
            .body(p);
    }
}
~~~

Không map vô điều kiện mọi `DataBufferLimitException` thành 413: nếu ứng dụng **đọc response từ downstream** hoặc buffer ở encoder thì lỗi không nhất thiết do request của caller. Khi request vượt giới hạn, server/gateway có thể đóng kết nối trước khi client đọc được body lỗi; client cần xử lý cả trường hợp connection reset. Đừng retry ngay cùng tệp không đổi khi đã biết giới hạn kích thước.

## 11. Bảo mật và vận hành khi streaming

- **Bảo vệ trước khi tiêu thụ body lớn:** xác thực/ủy quyền, kiểm tra quota, media type và `Content-Length` khi có; sau đó tiếp tục giới hạn byte thực nhận. Phải chống slow upload và nhiều kết nối mở cùng lúc.
- **Quyền object-level:** session/file phải thuộc đúng owner/tenant; path/key lưu trữ do server cấp, không dùng `filename` hoặc URI do client gửi.
- **Chống payload độc hại:** kiểm tra MIME thực tế, virus/malware, archive/zip bomb, checksum và file size; giữ ở vùng quarantine đến khi được publish.
- **Quản lý pooled buffers:** sử dụng các API `DataBufferUtils` đúng contract release của từng overload; xử lý discard, error và cancellation. Một luồng không được consume có thể gây rò bộ nhớ native.
- **Backpressure và quota:** giới hạn tốc độ/concurrency, số kết nối, disk staging, dung lượng theo tenant; theo dõi event-loop latency, heap/direct memory và thời gian storage write.
- **Hủy và cleanup:** request cancel có thể xảy ra giữa lúc ghi file; cần cơ chế dọn staging idempotent và sweeper TTL, không để file tạm mồ côi.
- **Truy vết:** metric lưu byte nhận/trả, throughput, `413`, `DataBufferLimitException`, cancellation, thời gian upload và disk usage; log theo route template/tenant đã ẩn danh, không ghi body hoặc token.

Thiết kế reactive không biến API thành không giới hạn tài nguyên. **Giới hạn bộ nhớ codec, giới hạn bytes, thời gian và concurrency** là bốn ranh giới riêng phải được cấu hình, quan sát và kiểm thử.

## 12. Kiểm thử `WebTestClient`, Reactor và áp lực tài nguyên

`WebTestClient` phù hợp kiểm thử API WebFlux. Những assertion dưới đây giả định có app/test slice được cấu hình, test principal hợp lệ và các service dependency được mock:

~~~java
// Giả định WebTestClient client đã được inject và có identity.
client.post().uri("/v1/uploads/raw")
    .contentType(MediaType.TEXT_PLAIN)
    .bodyValue("not-binary")
    .exchange()
    .expectStatus().isEqualTo(415);

client.post().uri("/v1/documents")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue("{invalid-json")
    .exchange()
    .expectStatus().isBadRequest();
~~~

Để test 413 mà **không tạo mảng 100 MiB trong test**, đưa `MAX_BYTES` thành configuration inject được và dùng ngưỡng nhỏ trong profile test. Gửi body thành nhiều `DataBuffer` nhỏ để kiểm tra **tổng byte** vượt ngưỡng dù từng buffer vẫn nhỏ. Xác nhận service **không publish file**, staging được dọn và lỗi có mã `UPLOAD_LIMIT_EXCEEDED`. Đối với decoder `maxInMemorySize`, gửi một JSON record quá ngưỡng rồi assert **status đúng theo cấu hình exception handler thực**, không mặc định framework tự trả 413.

Ma trận kiểm thử quan trọng:

| Tình huống | Kỳ vọng |
|---|---|
| JSON nhỏ hợp lệ | Đọc thành DTO, response `201/200` theo contract |
| JSON object quá codec limit | Bị chặn; không OOM, status theo policy |
| NDJSON nhiều dòng nhỏ | Decode từng record, không gom toàn file |
| Một NDJSON record khổng lồ | Bị giới hạn theo khả năng decoder |
| Raw upload thiếu `Content-Length` | Vẫn giới hạn byte thật |
| Header length nhỏ nhưng thực tế nhiều byte | Bị từ chối, không publish |
| Multipart file lớn, disk gần đầy | Trả lỗi an toàn, cleanup staging |
| Hai upload cùng tenant vượt quota | Admission control/throttling hoạt động |
| Client hủy giữa chừng | Subscription dừng, buffer/file tạm được giải phóng |
| Download có `Range` và ETag | `206/416` và byte đúng nếu API hỗ trợ |
| WebClient downstream error body lớn | Không buffer vô hạn/không làm sập caller |
| Caller ngoài tenant yêu cầu file | Không lộ dữ liệu hoặc đường dẫn |

Với Reactor `StepVerifier`, kiểm tra sequence, completion/error và cancellation; với load test, đo **heap lẫn direct memory**, thời gian event loop và số file tạm khi 100 kết nối chậm. Một unit test `Flux.just(...)` đi qua được không chứng minh gateway, object storage hoặc Netty không buffer trong production.

## 13. OpenAPI và bài thực hành

Ví dụ mô tả binary request và các response cần thiết:

~~~yaml
openapi: 3.1.0
info: {title: File API, version: 1.0.0}
paths:
  /v1/uploads/raw:
    post:
      summary: Upload tệp nhị phân có giới hạn byte
      security: [{bearerAuth: []}]
      requestBody:
        required: true
        content:
          application/octet-stream:
            schema: {type: string, format: binary}
      responses:
        '201':
          description: File đã được xác minh và tạo
          headers:
            Location: {schema: {type: string, format: uri-reference}}
        '400': {description: Body không hợp lệ}
        '413': {description: Vượt giới hạn byte}
        '415': {description: Media type không hỗ trợ}
        '429': {description: Vượt quota/concurrency}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
~~~

### Đề bài

Một API WebFlux nhận file tối đa **200 MiB**, trả NDJSON cho một báo cáo có 500.000 records và gọi downstream để lưu bản export. Hãy:

1. Chọn `maxInMemorySize` phù hợp cho JSON metadata nhỏ; giải thích tại sao không đặt 200 MiB.
2. Thiết kế `POST /uploads` nhận `application/octet-stream` hoặc multipart, giới hạn byte thực, staging và quyền tenant.
3. Viết pseudocode luồng `Flux<DataBuffer>` → file/object storage có backpressure, checksum, cleanup khi error/cancel.
4. Thiết kế endpoint NDJSON dùng `Flux<DTO>` và giới hạn mỗi record; so với pagination và async export.
5. Cấu hình `WebClient` để tải response 200 MiB không gọi `bodyToMono(byte[].class)`.
6. Nêu HTTP status cho sai media type, JSON malformed, vượt quota byte, vượt số kết nối và lỗi disk.
7. Viết tối thiểu tám test gồm codec limit, byte count, cross-tenant, cancellation, cleanup, backpressure và downstream error.

**Gợi ý:** codec limit vừa phải, stream vào staging, đếm byte và scan trước publish. NDJSON cho đọc từng record; tác vụ dài cần async export + URI kết quả có quyền.

## 14. Ghi nhớ

Trong Spring WebFlux, **`Mono`/`Flux` không tự bảo đảm streaming an toàn**. Phải biết codec nào gom body, giới hạn `maxInMemorySize` cho từng phần tử được giải mã và đặt quota byte/đĩa/concurrency riêng. Với file lớn, dùng `DataBuffer` hoặc `FilePart` và đường ghi có backpressure, cleanup khi lỗi hoặc hủy; với dữ liệu nhiều record dùng NDJSON/pagination/async export theo mục đích.

Một API đáng tin còn cần **HTTP status đúng, xác thực và quyền trên resource, cách xử lý buffer đúng vòng đời, kiểm thử ở cả server và WebClient**, cùng metric cho RAM/direct memory và staging disk. Chỉ tăng codec buffer khi gặp `DataBufferLimitException` là giải pháp dễ gây sự cố nhất.
