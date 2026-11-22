# Đọc, ghi theo luồng và kiểm soát bộ nhớ

## 1. Mục tiêu và bài toán thực tế

Trong module **INTEGRATION_API_REST**, ngoài resource, URI, phương thức, status HTTP và hợp đồng dữ liệu, người học cần xử lý những request/response lớn một cách **đúng, an toàn và có thể vận hành**. Chương **Tệp và dữ liệu lớn** tập trung vào đọc, ghi theo luồng để không biến mỗi upload/download thành một mảng byte khổng lồ trong JVM.

Ví dụ: dịch vụ tài liệu đa tenant nhận PDF 500 MiB, quét malware, lưu object storage rồi cho người có quyền tải về. Nếu dùng **MultipartFile.getBytes()** cho 20 upload cùng lúc, chỉ riêng payload đã có thể cần khoảng **10 GiB** RAM, chưa tính heap của ứng dụng, các bản sao buffer và garbage collection. Streaming cho phép xử lý từng đoạn nhỏ, nhưng vẫn phải kiểm soát số kết nối, thread, dung lượng đĩa, băng thông và thời gian chờ.

Sau bài học, bạn có thể:

- Phân biệt **streaming**, **buffering/spooling**, **backpressure** và **zero-copy**.
- Dùng InputStream/OutputStream, MultipartFile và StreamingResponseBody đúng vòng đời.
- Thiết kế REST contract cho upload, download, scan, lỗi kích thước và nội dung nhị phân.
- Giới hạn byte thực đọc, file/request size, concurrency, staging disk và timeout.
- Bảo vệ quyền tenant, định dạng, đường dẫn lưu, checksum, malware và signed URL.
- Mô tả OpenAPI, kiểm thử timeout/cancellation và tải đồng thời, hoàn thành bài thực hành.

**Tình huống xuyên suốt:** mỗi tổ chức được tải tài liệu lên; chỉ tài liệu ở trạng thái **READY** và có quyền mới được download.

## 2. Streaming không có nghĩa không có buffering

**Mẫu không phù hợp với tệp lớn:**

~~~java
byte[] payload = multipartFile.getBytes(); // Heap tăng theo cả file
storage.save(payload);
~~~

**Mẫu xử lý tuần tự từng khối:**

~~~java
try (InputStream in = source.open();
     OutputStream out = destination.open()) {
    byte[] buffer = new byte[64 * 1024];
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n > 0) out.write(buffer, 0, n);
    }
}
~~~

Mỗi request giữ một buffer **64 KiB**, không cần tạo array theo kích thước toàn file. Nhưng đó chỉ là buffer của vòng lặp này; HTTP server, TLS, storage SDK hoặc các thành phần khác vẫn dùng bộ nhớ riêng.

| Khái niệm | Cách hiểu |
| --- | --- |
| **Streaming** | Đọc/ghi lần lượt các đoạn dữ liệu, không giữ toàn bộ payload trong heap |
| **Buffering** | Tạm giữ dữ liệu trong RAM hoặc bộ nhớ đệm của một tầng |
| **Spooling** | Ghi dữ liệu nhận vào tệp tạm trên đĩa để xử lý sau |
| **Backpressure** | Bên tiêu thụ chậm làm hạn chế tốc độ bên tạo dữ liệu |
| **Zero-copy** | Tối ưu tránh một số lần sao chép dữ liệu, không tự có vì dùng stream |
| **Cancellation** | Giải phóng công việc/tài nguyên khi request hoặc client dừng |

~~~mermaid
flowchart LR
    C[Client] --> G[Gateway / proxy]
    G --> S[Servlet container / multipart parser]
    S --> A[Spring API]
    A --> T[Staging / scan]
    T --> O[(Object storage)]
~~~

**Bẫy thường gặp:** Spring MVC **MultipartFile.getInputStream()** không bảo đảm luồng đi thẳng từ socket tới controller. Servlet multipart parser có thể đã đệm part vào RAM hoặc **spool xuống đĩa**; gateway cũng có thể buffer request. Cần kiểm tra cấu hình ở **tất cả tầng** khi đánh giá end-to-end streaming.

**Ngân sách ví dụ:** 500 download × 64 KiB buffer ≈ **31,25 MiB chỉ cho các buffer này**. Tổng bộ nhớ thực còn có thread stack, TLS, native/direct buffers, thư viện và dữ liệu ứng dụng. Một request stream chậm còn giữ kết nối và worker dù buffer nhỏ.

## 3. REST contract cho file resource

| Mục đích | Phương thức và URI | Ngữ nghĩa |
| --- | --- | --- |
| Tạo file resource | **POST /api/v1/files** | 201 khi tạo hoàn tất, có Location |
| Xem metadata/trạng thái | **GET /api/v1/files/{id}** | 200 JSON gồm trạng thái, size, checksum khi được phép |
| Tải nội dung | **GET /api/v1/files/{id}/content** | 200 binary hoặc 206 nếu thực sự hỗ trợ Range |
| Xóa file | **DELETE /api/v1/files/{id}** | 204 sau khi thao tác hoàn thành theo hợp đồng |
| Tạo upload session | **POST /api/v1/upload-sessions** | Dành cho resumable/large uploads |

Nếu file được lưu nhưng **chưa quét malware**, resource có thể ở **PENDING_SCAN**. API có thể trả **201 Created** kèm trạng thái này khi đã tạo resource, hoặc **202 Accepted** nếu mới nhận công việc chưa hoàn tất. Không để GET content của file PENDING_SCAN trả byte chưa được duyệt.

### 3.1. Upload multipart/form-data

~~~http
POST /api/v1/files HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: multipart/form-data; boundary=abc123

--abc123
Content-Disposition: form-data; name="file"; filename="report.pdf"
Content-Type: application/pdf

[bytes của tệp]
--abc123--
~~~

Khi đã tạo file có thể tải được:

~~~http
HTTP/1.1 201 Created
Location: /api/v1/files/7f18
Content-Type: application/json
Cache-Control: no-store

{"id":"7f18","state":"READY","size":7340032}
~~~

**Filename** và **Content-Type** trong multipart do client cung cấp, không chứng minh đường dẫn hoặc loại file an toàn.

### 3.2. Download nhị phân

~~~http
GET /api/v1/files/7f18/content HTTP/1.1
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="report.pdf"
Content-Length: 7340032
Cache-Control: private, no-store
X-Content-Type-Options: nosniff

[bytes của tệp]
~~~

**Content-Length** chỉ được đặt khi biết chính xác số byte sẽ truyền. Khi chưa biết, bỏ Content-Length để HTTP stack xử lý framing. HTTP/1.1 có thể dùng chunked transfer encoding; không tự thêm **Transfer-Encoding: chunked** vào HTTP/2. Download cần xác thực, phân quyền và kiểm tra trạng thái **trước khi stream bắt đầu**.

## 4. Hạn mức kích thước ở nhiều tầng

Chỉ kiểm tra **file.getSize()** ở controller có thể quá muộn nếu container đã spool toàn request. Cần giới hạn đồng thời tại:

1. **Gateway:** body size, request timeout, concurrent uploads, rate limit.
2. **Servlet multipart parser:** max file, max request, số part và chính sách RAM/đĩa tạm.
3. **Service:** đếm **byte thực nhận**, không chỉ dựa Content-Length.
4. **Storage:** quota/tenant, staging disk, object count và cleanup.
5. **Business:** file type, quy tắc tài liệu, user/tenant được phép thao tác.

Cấu hình minh họa với Spring Boot:

~~~yaml
spring:
  servlet:
    multipart:
      max-file-size: 100MB
      max-request-size: 105MB
      file-size-threshold: 0B
~~~

Ngưỡng là **ví dụ**, cần chọn theo sản phẩm và kiểm tra phiên bản container. **file-size-threshold: 0B** thường hướng nội dung multipart file sang vùng tạm thay vì lưu nhiều vào RAM, nhưng **không** bảo đảm không tầng nào khác buffer.

**Content-Length là gợi ý từ request**, có thể vắng mặt hoặc không đúng với dữ liệu thực; luôn đếm byte trong lúc đọc. Với file ZIP/ảnh/tệp nén, phải kiểm tra cả **kích thước sau giải nén**, số entry, độ sâu và thời gian xử lý. File nén nhỏ có thể gây tiêu tốn tài nguyên rất lớn.

### 4.1. Trường hợp từ chối

| Lý do | Mã HTTP gợi ý |
| --- | --- |
| Request body vượt hạn mức | **413 Content Too Large** |
| Media type không được hỗ trợ | **415 Unsupported Media Type** |
| Nội dung vi phạm schema/quy tắc nghiệp vụ | **400 hoặc 422**, theo hợp đồng |
| Chưa xác thực | **401** với challenge phù hợp |
| Không có quyền hoặc không được phép thấy file | **403/404** theo chính sách |
| Vượt rate limit | **429 Too Many Requests** |
| Storage tạm không sẵn sàng | **503 Service Unavailable** khi phù hợp |

Gateway có thể trả 413 **trước khi controller chạy**. Nếu API công bố Problem Details, cần chuẩn hóa lỗi cả ở gateway, không chỉ @RestControllerAdvice.

## 5. Spring Boot: upload theo luồng có giới hạn

Ví dụ Java 17+, Spring MVC, file được **stream từ MultipartFile sang staging riêng tư**, tính SHA-256 từng khối rồi scan trước khi tạo file READY.

### 5.1. Controller

~~~java
@RestController
@RequestMapping("/api/v1/files")
public class FileController {
    private final UploadService uploads;

    public FileController(UploadService uploads) {
        this.uploads = uploads;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<FileReceipt> upload(
            @RequestPart("file") MultipartFile file,
            Authentication authentication) throws IOException {

        FileReceipt receipt = uploads.accept(file, authentication);
        return ResponseEntity
                .created(URI.create("/api/v1/files/" + receipt.id()))
                .body(receipt);
    }
}

public record FileReceipt(UUID id, String state, long size, String sha256) {}
~~~

### 5.2. Service đọc từng khối, kiểm soát số byte

~~~java
@Service
public class UploadService {
    private static final long MAX_BYTES = 100L * 1024 * 1024;
    private static final int BUFFER_SIZE = 64 * 1024;

    private final Path stagingDirectory;
    private final UploadAuthorization acl;
    private final MalwareScanner scanner;
    private final FileStorage storage;

    // Các dependency được inject qua constructor trong ứng dụng thật.

    public FileReceipt accept(
            MultipartFile file, Authentication principal) throws IOException {

        UploadScope scope = acl.requireCanUpload(principal);
        Path staged = Files.createTempFile(
                stagingDirectory, "upload-", ".part");

        try {
            MessageDigest digest;
            try {
                digest = MessageDigest.getInstance("SHA-256");
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException("SHA-256 unavailable", ex);
            }

            long total = 0;
            try (InputStream in = file.getInputStream();
                 OutputStream out = Files.newOutputStream(
                         staged, StandardOpenOption.TRUNCATE_EXISTING)) {

                byte[] buffer = new byte[BUFFER_SIZE];
                int n;
                while ((n = in.read(buffer)) != -1) {
                    if (n == 0) continue;
                    if (n > MAX_BYTES - total) {
                        throw new FileTooLargeException();
                    }
                    out.write(buffer, 0, n);
                    digest.update(buffer, 0, n);
                    total += n;
                }
            }

            scanner.requireSafe(staged);
            String sha256 = HexFormat.of().formatHex(digest.digest());
            return storage.persistStaged(
                    staged, scope.tenantId(), total, sha256);
        } finally {
            Files.deleteIfExists(staged);
        }
    }
}
~~~

**Ý nghĩa:** buffer cố định; byte-count limit; try-with-resources; tên tạm do server tạo; tính checksum tăng dần; dọn staging ở cả nhánh lỗi. **Không dùng MultipartFile.getBytes() hoặc InputStream.readAllBytes()**.

**Những phần cần bổ sung trước production:**

- Cấu hình staging directory có quyền filesystem tối thiểu, quota và dọn orphan sau process crash.
- **UploadAuthorization**, **MalwareScanner**, **FileStorage** và **FileTooLargeException** là abstraction cần triển khai. Exception quá hạn mức nên map 413.
- Scanner không đáp ứng phải khiến file tiếp tục **quarantine/failed**, không mặc nhiên READY; kiểm soát timeout và định dạng được phép.
- **persistStaged** phải quản lý object storage và metadata nhất quán. Hai hệ này thường không có chung transaction: cần trạng thái bền vững, reconciliation và xóa object mồ côi nếu DB commit lỗi.
- Không dùng **getOriginalFilename()** làm path/object key; tên download nếu lưu cần chuẩn hóa.
- Kiểm soát tổng multipart request, số part, concurrency và quota ngoài giới hạn 100 MiB.
- SHA-256 chỉ kiểm tra **toàn vẹn**, không chứng minh file vô hại.

Code được rút gọn để giảng giải; các import, constructor và exception mapping chưa đầy đủ để chạy như một project độc lập.

## 6. Vòng đời lưu trữ và phát hành

~~~mermaid
flowchart TD
    A[Upload theo luồng] --> B[Staging / quarantine]
    B --> C[Validate + hash + malware scan]
    C --> D{Đạt điều kiện?}
    D -- Không --> E[REJECTED / cleanup]
    D -- Có --> F[Persist object + metadata]
    F --> G[READY và cho phép download]
~~~

Gợi ý state machine: **UPLOADING → PENDING_SCAN → READY**, hoặc **FAILED/REJECTED**. Không phát hành signed download URL, cache hoặc metadata READY trước khi object thật sự an toàn và quyền được kiểm tra.

**Object storage và DB không nguyên tử như một giao dịch SQL duy nhất.** Khi một bước thất bại, dùng trạng thái trung gian, cleanup job, retry có giới hạn và kiểm tra đối soát. Với quy trình bất đồng bộ, có thể dùng outbox/event ID để worker retry không gây tác dụng trùng.

Tệp đã scan phải được bảo vệ khỏi bị thay thế âm thầm trước lúc download: gắn scan result với **object key/generation/checksum** của đúng bytes. Nếu object được ghi đè sau scan, phải scan lại hoặc dùng immutable object version.

## 7. Download theo luồng bằng StreamingResponseBody

Spring MVC cung cấp **StreamingResponseBody** để ghi ra OutputStream mà không cần tạo một **byte[]** chứa toàn file.

~~~java
@GetMapping(value = "/{id}/content",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
public ResponseEntity<StreamingResponseBody> download(
        @PathVariable UUID id,
        Authentication authentication) {

    StoredFile file = fileService.requireReadable(id, authentication);
    // Đã kiểm tra tenant, quyền, trạng thái READY và metadata.

    StreamingResponseBody body = output -> {
        try (InputStream in = storage.open(file.objectKey())) {
            byte[] buffer = new byte[64 * 1024];
            int n;
            while ((n = in.read(buffer)) != -1) {
                if (n > 0) output.write(buffer, 0, n);
            }
        }
    };

    ContentDisposition attachment = ContentDisposition.attachment()
            .filename(file.safeDownloadName(), StandardCharsets.UTF_8)
            .build();

    return ResponseEntity.ok()
            .contentType(MediaType.APPLICATION_OCTET_STREAM)
            .contentLength(file.size())
            .header(HttpHeaders.CONTENT_DISPOSITION, attachment.toString())
            .header(HttpHeaders.CACHE_CONTROL, "private, no-store")
            .header("X-Content-Type-Options", "nosniff")
            .body(body);
}
~~~

Các đối tượng **fileService, storage, StoredFile** là abstraction. Cần có **AsyncTaskExecutor giới hạn thread/queue** cho MVC streaming. Luồng dữ liệu nhỏ không giúp ích nếu hàng nghìn client chậm đều giữ thread và socket lâu.

**Client hủy kết nối:** write có thể ném IOException. Try-with-resources đóng InputStream; ghi metric/correlation ID, kết thúc công việc, tránh retry toàn bộ ở server. Sau khi response **200 đã gửi headers/body**, không thể đổi thành JSON 500/Problem Details mới. Client cần xác minh Content-Length/checksum để phát hiện tệp không hoàn chỉnh.

**Context async:** security context/MDC/tracing không mặc định được truyền sang thread worker. Phân quyền trước khi stream, dùng metadata đáng tin và cơ chế truyền context có kiểm soát. Quy định rõ chính sách nếu quyền bị thu hồi trong một download dài.

### 7.1. HEAD, Range và resume download

Ví dụ chỉ hỗ trợ **GET toàn bộ file**. Nếu công bố **Range**, phải xử lý chính xác:

~~~http
GET /api/v1/files/7f18/content HTTP/1.1
Range: bytes=0-1048575
~~~

~~~http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 0-1048575/7340032
Content-Length: 1048576
Content-Type: application/octet-stream

[1 MiB đầu]
~~~

Cần hỗ trợ semantics của **206**, **416 Range Not Satisfiable**, **If-Range**, validator và có thể nhiều ranges theo hợp đồng. **Không thêm Accept-Ranges: bytes cho code StreamingResponseBody ở trên**, vì mẫu chưa có xử lý Range. Nếu cần video/resume với file lớn, ưu tiên object storage/CDN có hỗ trợ Range đã kiểm thử. **HEAD** có thể trả metadata của cùng representation nhưng không có body.

## 8. Backpressure, concurrency và tài nguyên

Khi client nhận chậm, ghi OutputStream có thể **block** và làm vòng đọc tiếp theo chậm lại: một dạng backpressure trong pipeline blocking. Tuy nhiên nó vẫn giữ thread/connection. Phải giới hạn:

| Nguồn tài nguyên | Biện pháp |
| --- | --- |
| Heap và native buffers | Buffer cố định, không gom toàn payload |
| Thread/queue | Executor bounded, bulkhead và timeout |
| Socket/băng thông | Concurrent stream limit, idle timeout, rate limit |
| Staging disk | Quota, dung lượng dự phòng, dọn orphan |
| Multipart parser | File/request limits, spool config |
| Storage SDK | Connection pool, retry/backoff có giới hạn |
| CSDL | Metadata transactions ngắn, không giữ lock suốt stream |

**Spring WebFlux** có thể sử dụng **Flux<DataBuffer>** và reactive backpressure khi các component đều hỗ trợ. Nhưng dùng WebFlux không tự ngăn OOM nếu gom toàn bộ DataBuffer không giới hạn, không release buffer, hoặc storage client vẫn block. **Zero-copy/sendfile** là tối ưu tùy server, TLS và nguồn dữ liệu; không phải yêu cầu để xử lý stream đúng.

### 8.1. Streaming không giải quyết mọi tải lớn

Một câu lệnh ghi stream từ object storage 64 KiB/chu kỳ có thể vẫn tồn tại hàng phút do client chậm. Cần đo **active streams**, p95 thời gian, throughput, queue depth, GC, số file descriptor, lỗi socket và dung lượng staging. Một hệ thống có cache hit ratio cao hoặc tốc độ truyền lớn nhưng không kiểm soát download chậm vẫn có thể quá tải.

## 9. Bảo mật upload/download

Upload là **đầu vào không tin cậy**. Những quy tắc quan trọng:

1. **Quyền theo resource/tenant:** kiểm tra upload/download/scan status từ principal được xác thực; không tin tenantId từ query/header do client điền.
2. **Kiểm tra định dạng:** Content-Type và phần mở rộng client có thể giả; kiểm tra signature/magic bytes, parser có giới hạn và allowlist.
3. **Malware scan/quarantine:** không phát bytes chưa scan hoặc scan thất bại; quy định timeout và cơ chế retry.
4. **Path traversal:** không dùng filename người dùng ghép path; server tự tạo UUID/object key, chuẩn hóa tên hiển thị.
5. **Archive bomb:** giới hạn byte sau giải nén, số entry, nesting, CPU/time; chặn symlink/path traversal khi extract.
6. **Stored XSS/content sniffing:** với file không tin cậy ưu tiên attachment, octet-stream, nosniff và Content-Disposition encode đúng.
7. **Encryption/quota:** HTTPS, mã hóa tại rest, ACL storage tối thiểu, quota cả dữ liệu đang upload.
8. **Audit:** actor, tenant, ID, size, kết quả, request ID; không log token, binary content hoặc presigned URL.
9. **SSRF:** khi API cho nhập URL để server tải file, hạn chế đích IP/DNS, redirect và network egress; streaming không chống SSRF.
10. **Checksum:** hash đúng bytes được lưu/phát; đối chiếu nguồn tin cậy khi cần, không xem hash là malware scanner.

**Không chỉ ẩn nội dung từ danh sách JSON:** nếu object store có URL công khai hoặc link cũ chưa thu hồi, file vẫn có thể bị tải trực tiếp. Phân quyền phải áp vào **đường cấp byte thực tế**, kể cả signed URL.

## 10. Tệp rất lớn: upload session và object storage

Với file vài GiB, không nhất thiết cho toàn bộ byte đi qua ứng dụng. Một kiến trúc thường dùng:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant O as Object Storage
    participant W as Scan Worker
    C->>A: POST /upload-sessions
    A-->>C: Session + scoped upload URL
    C->>O: PUT parts / bytes
    O-->>C: Part receipts
    C->>A: Complete session
    A->>O: Verify size/checksum/object generation
    A->>W: Request scan
    W-->>A: Scan result
    A-->>C: READY khi đã đạt yêu cầu
~~~

**Pre-signed URL** là bearer capability có thời hạn: ai cầm URL có thể dùng trong phạm vi đã ký. Giới hạn method, object key, TTL, điều kiện upload và không ghi URL vào log. Chỉ cấp signed **download** cho file đã READY và quyền còn hợp lệ.

Một **resumable upload** cần uploadSessionId, part ID/offset, checksum từng part, TTL, cách commit/abort và xử lý part gửi lặp. Không thể tự resume một request multipart HTTP đơn thông thường nếu giao thức không hỗ trợ.

~~~http
POST /api/v1/upload-sessions HTTP/1.1
Content-Type: application/json

{"filename":"archive.zip","expectedSize":1073741824}
~~~

~~~http
HTTP/1.1 201 Created
Location: /api/v1/upload-sessions/us-91
Content-Type: application/json

{"id":"us-91","state":"UPLOADING","maxPartSize":8388608}
~~~

Đây là **hợp đồng minh họa**, không phải một protocol resumable chuẩn. Quota phải tính cả upload **đang diễn ra** để client không vượt quota bằng nhiều session song song.

### 10.1. Retry và idempotency

**POST upload không tự idempotent**. Nếu client timeout sau khi server đã lưu object, gửi POST mới có thể tạo bản trùng. Có thể dùng **Idempotency-Key** với fingerprint/scope tenant/TTL và trạng thái operation; với multipart dùng uploadSessionId + partId/offset + checksum để deduplicate.

Đừng coi 504/connection reset là “chưa commit”. Client cần truy vấn upload session hoặc file metadata trước khi gửi lại ý định mới. Retry với backoff và hạn mức, không tạo vòng lặp vô hạn.

## 11. OpenAPI 3.1 mô tả binary contract

~~~yaml
openapi: 3.1.0
info:
  title: File Streaming API
  version: 1.0.0
paths:
  /api/v1/files:
    post:
      operationId: uploadFile
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          multipart/form-data:
            schema:
              type: object
              required: [file]
              properties:
                file:
                  type: string
                  format: binary
      responses:
        '201':
          description: Đã tạo resource file
          headers:
            Location:
              schema:
                type: string
        '202':
          description: Đã chấp nhận xử lý bất đồng bộ
        '413':
          description: Payload vượt hạn mức
        '415':
          description: Loại nội dung không hỗ trợ
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền
  /api/v1/files/{id}/content:
    get:
      operationId: downloadFile
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: id
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Stream tệp đầy đủ
          headers:
            Content-Length:
              schema:
                type: integer
            Content-Disposition:
              schema:
                type: string
            Cache-Control:
              schema:
                type: string
          content:
            application/octet-stream:
              schema:
                type: string
                format: binary
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền
        '404':
          description: Không tìm thấy hoặc không được công bố
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

**OpenAPI không tự thực thi streaming**. Nếu API hỗ trợ Range, phải mô tả riêng 206/416, Content-Range và điều kiện. Với lỗi, nên bổ sung **RFC 9457 Problem Details** phù hợp từng nguồn lỗi (gateway, servlet, application).

## 12. Ma trận kiểm thử chức năng và tải

| Test | Chuẩn bị/hành động | Kết quả cần chứng minh |
| --- | --- | --- |
| File nhỏ hợp lệ | Upload PDF test | 201, Location, metadata đúng, bytes khớp |
| Đúng ngưỡng | Upload MAX_BYTES | Không bị từ chối sai |
| Vượt một byte | Upload MAX_BYTES+1 | 413, không READY, staging được dọn |
| Thiếu Content-Length | Stream không biết trước kích thước | Giới hạn byte đọc vẫn có hiệu lực |
| Multipart nhiều part | Gửi nhiều field/file | Total size, part count, quota có giới hạn |
| MIME giả / malware | Gửi file không đúng định dạng | Quarantine/REJECTED, không được tải |
| Filename độc hại | ../, CRLF, ký tự đặc biệt | Không path traversal hoặc header injection |
| Tenant B truy cập file A | Dùng token tenant B | 403/404, không phát byte/metadata |
| Client hủy download | Đóng socket giữa chừng | InputStream đóng, thread/connection giải phóng |
| Storage hỏng giữa stream | Ném IOException sau một phần bytes | Không chèn JSON giữa body binary |
| Upload timeout sau commit | Retry cùng key/session | Không tạo file/part trùng ngoài chủ đích |
| Scan/DB lỗi | Crash giữa các bước | Không READY giả, cleanup hoặc reconciliation |
| Client chậm | Đọc response từng byte chậm | Bounded concurrency/timeout hiệu lực |
| Tải đồng thời | Nhiều upload/download lớn | Heap, GC, disk, pool, queue ổn định |
| Range/If-Range | Khi API hỗ trợ | 206/416, Content-Range chính xác |

**Unit test bộ nhớ:** dùng một **InputStream giả sinh dữ liệu từng khối** đến MAX_BYTES+1 thay vì tạo file lớn trong RAM; kiểm tra service ném FileTooLargeException và dọn tệp tạm. Test này chứng minh byte-count limit không phụ thuộc Content-Length.

**End-to-end test:** phải đi qua gateway/multipart parser và storage gần production; unit test riêng của service không cho biết proxy có buffer, áp 413 hoặc timeout đúng chưa. Đo heap/native memory, active streams, p95/p99, disk staging, file descriptors, cancellation, checksum mismatch và throughput.

## 13. Bài thực hành: upload 2 GiB cho SaaS đa tenant

**Bối cảnh:** nền tảng có 200 tenant, quota lưu trữ riêng. Khách hàng upload tối đa **2 GiB**, kết nối có thể ngắt, file chỉ tải được khi scanner xác nhận an toàn. API chạy Spring Boot sau gateway và lưu trên cloud object storage.

### Nhiệm vụ (100 điểm)

1. **REST contract – 25 điểm:** thiết kế upload session, upload part, complete, metadata/status và download; phân biệt 201/202/413/409/422, expiry và retry.
2. **Tài nguyên – 25 điểm:** chọn buffer/chunk, concurrency, RAM/disk quota, upload timeout, xử lý client chậm. Phân biệt streaming của ứng dụng với gateway/container buffering.
3. **Bảo mật/nhất quán – 25 điểm:** tenant ACL, scoped signed URL, staging/quarantine, scan, checksum, generated object key, cleanup/reconciliation và điều kiện READY.
4. **Kiểm thử – 25 điểm:** viết ít nhất tám test, bắt buộc có vượt một byte, thiếu Content-Length, cross-tenant, ZIP bomb, retry part, client cancel, storage lỗi và scan thất bại. Nêu bốn metric vận hành.

**Hướng giải:** tạo upload session sau khi kiểm tra quyền/quota; client upload trực tiếp các part lên storage theo capability có TTL; API chỉ xác nhận complete sau khi kiểm tra object generation/size/checksum. Worker chuyển **PENDING_SCAN → READY** khi scan pass; chưa READY thì không cấp download URL. Part có định danh/checksum cho retry an toàn; session hết hạn được dọn. Quan sát active sessions, staging usage, scan queue lag và tỷ lệ upload failure.

## 14. Checklist tổng kết

- [ ] Không dùng **getBytes/readAllBytes/byte[]** cho tệp không giới hạn.
- [ ] Phân biệt streaming ứng dụng và buffering ở gateway/servlet.
- [ ] Có buffer cố định, byte-count limit và try-with-resources.
- [ ] Có giới hạn file/request/part, timeout, concurrency, quota và staging disk.
- [ ] File phải được phân quyền, kiểm tra định dạng, scan trước khi READY.
- [ ] Không tin filename, MIME, Content-Length hoặc tenant do client khai.
- [ ] Download có kiểm soát cache, Content-Disposition và nosniff.
- [ ] Hiểu lỗi sau khi gửi một phần body không thể đổi thành JSON 500.
- [ ] Không công bố Range nếu chưa hỗ trợ 206/416 đúng.
- [ ] Có retry/idempotency và reconciliation khi storage/DB không đồng bộ.
- [ ] Có OpenAPI, kiểm thử HTTP/gateway, thử tải và đo tài nguyên.

**Ghi nhớ:** streaming giúp **bộ nhớ không tăng theo kích thước tệp**, nhưng không tự bảo vệ hệ thống khỏi hết thread, đĩa, kết nối hay rò rỉ dữ liệu. Một REST API xử lý tệp lớn đáng tin phải kết hợp **hợp đồng HTTP, giới hạn đa tầng, phân quyền, scan, consistency, backpressure và kiểm thử dưới tải**.

### Tài liệu chuẩn để tra cứu

- **RFC 9110 – HTTP Semantics:** HTTP Range, Content-Length, 206/413/415/416 và headers.
- **RFC 7578 – multipart/form-data:** định dạng tải lên multipart.
- **RFC 9111 – HTTP Caching:** lưu trữ dữ liệu nhạy cảm và cache control.
- **RFC 9457 – Problem Details for HTTP APIs:** lỗi JSON thống nhất.
- **OpenAPI Specification 3.1:** request/response nhị phân.
- **Spring Framework / Spring Boot:** MultipartFile, StreamingResponseBody, async MVC và multipart config.
