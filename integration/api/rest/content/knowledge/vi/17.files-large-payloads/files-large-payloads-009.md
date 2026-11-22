# Upload chia phần, tiếp tục tải và lựa chọn giao thức bổ sung

> **Module:** `INTEGRATION_API_REST` — chương **Tệp và dữ liệu lớn**. Bài học thiết kế REST API truyền tệp lớn dựa trên resource, URI, phương thức và mã trạng thái HTTP, có hợp đồng dữ liệu rõ ràng. Trọng tâm: **chia phần upload, tiếp tục sau gián đoạn, kiểm tra tính toàn vẹn, hoàn tất nguyên tử, bảo mật**, và lựa chọn giữa giao thức tự thiết kế, **tus** hoặc multipart của object storage. Ví dụ dùng Java/Spring.

## 1. Bài toán: upload 4 GiB trên đường truyền không ổn định

Một người dùng tải video 4 GiB. Nếu `POST multipart/form-data` bị ngắt ở 97%, client có thể phải gửi lại từ đầu; kết nối lâu cũng gây áp lực lên gateway và bộ nhớ tạm. **Resumable upload** phải có hợp đồng xác định part/offset đã nhận, retry không nhân đôi byte, quyền tải, thời điểm publish và cơ chế dọn session.

**Kết quả học tập:** thiết kế upload session và kiểm tra tính toàn vẹn; chọn giao thức, triển khai streaming Java/Spring, bảo mật và test retry, race, expiry.

### 1.1. Không nhầm các thao tác khác nhau

| Khả năng | Mục đích | Cơ chế thường dùng |
|---|---|---|
| **Streaming upload** | Không giữ toàn bộ tệp trong RAM của server | Đọc request body thành luồng với backpressure |
| **Chunked/resumable upload** | Gửi một phần, xác định phần đã nhận, tiếp tục từ điểm dừng | Upload session, offset hoặc manifest part |
| **Parallel multipart upload** | Nhiều phần gửi đồng thời | Part number + byte range + manifest |
| **HTTP chunked transfer coding** | Đóng khung body HTTP/1.1 khi chưa biết trước chiều dài | `Transfer-Encoding: chunked`; **không** tự tạo resumable upload |
| **Range download** | Tải tiếp phần còn thiếu của tài nguyên đã tồn tại | `Range`, `206 Partial Content`, `Content-Range` |

“Upload chia phần” **không đồng nghĩa** với HTTP/1.1 chunked transfer encoding. Việc body được chia thành nhiều frame/chunk ở tầng truyền tải không cho client biết server đã **lưu bền vững đến byte nào**.

## 2. Chọn mô hình: offset tuần tự hay các part độc lập?

### 2.1. Offset tuần tự

Server giữ một độ dài đã nhận liên tục `offset`. Client gửi byte bắt đầu **đúng offset hiện tại** và tăng offset sau khi ghi bền vững.

~~~text
Tệp 12 MiB, offset = 8 MiB:
[0..4 MiB)[4..8 MiB)[8..12 MiB)
 [đã nhận] [đã nhận] [chưa nhận]
~~~

**Ưu điểm:** logic nối byte và resume đơn giản, thuận tiện với luồng gửi tuần tự. **Nhược điểm:** một session thường không gửi các phần ngoài thứ tự hoặc song song nếu không có extension/hợp đồng riêng. Giao thức **tus** sử dụng mô hình offset cốt lõi này.

### 2.2. Các part có số thứ tự

Client cố định `partSize` (ví dụ 8 MiB) và tạo các part:

~~~text
part 1 = bytes [0, 8 MiB)
part 2 = bytes [8, 16 MiB)
part 3 = bytes [16, 24 MiB)
...
~~~

Server ghi mỗi part vào vùng tạm gắn với `uploadId` và `partNumber`. Client có thể gửi song song tối đa một số part được phép, hỏi manifest để tìm phần thiếu và chỉ gửi lại phần đó.

**Ưu điểm:** phục hồi hiệu quả, upload song song, phù hợp cơ chế multipart của object storage. **Nhược điểm:** phải lưu manifest, xác minh trùng/gap, giới hạn concurrency, xử lý commit và dọn part mồ côi.

### 2.3. Khi nào chọn cách nào?

**tus** phù hợp khi mobile/web cần resume tuần tự với client/server tương thích; **multipart** phù hợp nếu cần gửi song song; **direct-to-storage** giảm băng thông qua API. File nhỏ không cần resume có thể dùng `POST multipart/form-data`. Download tiếp tục dùng HTTP Range. Các ngưỡng part size, timeout và concurrency phải được đo và công bố.

## 3. Thiết kế REST contract cho multipart upload của ứng dụng

Ta chọn ví dụ: file tối đa 10 GiB; part thông thường **8 MiB**, part cuối có thể nhỏ hơn; tối đa 4 part gửi song song; session tồn tại 24 giờ. Đây là **hợp đồng riêng của ứng dụng**, không phải chuẩn resumable upload của HTTP.

Mỗi upload là một resource có định danh và vòng đời:

~~~mermaid
stateDiagram-v2
    [*] --> OPEN: POST /uploads
    OPEN --> OPEN: PUT part hợp lệ
    OPEN --> FINALIZING: POST /completions
    FINALIZING --> COMPLETED: xác minh và publish
    FINALIZING --> FAILED: lỗi kiểm tra / ghép
    OPEN --> ABORTED: DELETE /uploads/{id}
    OPEN --> EXPIRED: hết TTL
    FAILED --> ABORTED: dọn dữ liệu
    COMPLETED --> [*]
~~~

Một session `OPEN` chưa phải là resource file có thể tải. Chỉ sau khi kiểm tra đủ phần, độ dài, checksum, loại nội dung và chính sách an toàn, server mới tạo/công bố file. `FINALIZING` không nhận part mới để tránh race.

### 3.1. Khởi tạo session

~~~http
POST /v1/uploads HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: 751e6f74-431d-43d0-81d6-e47e51ed314c
Content-Type: application/json

{
  "fileName": "lesson-video.mp4",
  "contentType": "video/mp4",
  "size": 20971520,
  "sha256": "64-hex-digest-of-complete-file"
}
~~~

Trong request thực, `sha256` phải là **64 ký tự hex hợp lệ**, không phải chuỗi minh họa trên. Server chỉ coi metadata như fileName/contentType là **tuyên bố chưa đáng tin** và kiểm chứng trước khi publish.

~~~http
HTTP/1.1 201 Created
Location: https://api.example.test/v1/uploads/up_8c42
Cache-Control: no-store
Content-Type: application/json

{
  "id": "up_8c42",
  "status": "OPEN",
  "partSize": 8388608,
  "maxParallelParts": 4,
  "expiresAt": "2026-11-19T12:00:00Z",
  "links": {
    "self": "/v1/uploads/up_8c42",
    "parts": "/v1/uploads/up_8c42/parts",
    "complete": "/v1/uploads/up_8c42/completions"
  }
}
~~~

`201` ở đây nói rằng **upload session** đã được tạo, chưa phải file hoàn chỉnh. `Location` phải trỏ session đó. `Idempotency-Key` giúp client không tạo hàng loạt session khi mất response; scope, retention và fingerprint request phải được định nghĩa ở server.

### 3.2. Upload từng part

~~~http
PUT /v1/uploads/up_8c42/parts/1 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/octet-stream
Content-Length: 8388608
Content-Digest: sha-256=:BASE64_DIGEST_OF_THIS_PART:

<8388608 bytes nhị phân>
~~~

`Content-Digest` biểu diễn digest của **nội dung HTTP message** theo chuẩn trường digest; cú pháp ở đây minh họa (cần base64 thực và thư viện hỗ trợ). Nếu không hỗ trợ trường chuẩn này, có thể dùng checksum trong metadata part theo **hợp đồng ứng dụng**, nhưng phải mô tả cách tính/chữ ký rõ. Server tính digest **trong khi stream** rồi so sánh với giá trị nhận.

~~~http
HTTP/1.1 201 Created
ETag: "part-1-checksum-or-version"
Cache-Control: no-store
~~~

`PUT /parts/{number}` ghi/đặt **đúng resource part**, không phải PUT một đoạn vào file đích. Server biết `partNumber`, `partSize` và `size` nên xác định được byte range của mỗi part. Với tệp 20 MiB: part 1 = 8 MiB, part 2 = 8 MiB, part 3 = 4 MiB. Không cho một part có chiều dài tùy ý nếu manifest phải có ranh giới cố định.

**Retry part:** cùng `uploadId + partNumber` và **cùng byte/digest** nên được coi là replay idempotent theo hợp đồng, trả status tương thích mà không nhân đôi dữ liệu. Nếu part number đã tồn tại với byte khác, trả `409 Conflict`; không âm thầm ghi đè part đầu tiên. Không dựa vào ETag của object storage để khẳng định nó là SHA-256: ETag có thể có ý nghĩa riêng tùy provider và cơ chế multipart.

### 3.3. GET session để phục hồi

~~~http
GET /v1/uploads/up_8c42 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{
  "id": "up_8c42",
  "status": "OPEN",
  "partSize": 8388608,
  "receivedParts": [
    {"number":1,"size":8388608},
    {"number":3,"size":4194304}
  ],
  "missingParts": [2],
  "expiresAt": "2026-11-19T12:00:00Z"
}
~~~

Client **không suy ra part 2 đã nhận** chỉ vì request PUT trước đó được gửi. Nó đọc manifest từ nguồn trạng thái bền vững, chỉ retry part thiếu, sau đó thực hiện bước hoàn tất. Với hàng chục nghìn part, nên phân trang danh sách part hoặc trả cấu trúc tóm tắt để manifest không thành payload khổng lồ.

### 3.4. Hoàn tất: kiểm chứng rồi publish nguyên tử

~~~http
POST /v1/uploads/up_8c42/completions HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: d88bc241-14bb-4a4e-8642-a99e60921234
Content-Type: application/json

{"expectedParts":3}
~~~

Server kiểm tra: session thuộc quyền caller, trạng thái `OPEN`, số phần, không có khoảng trống/chồng lấn, tổng byte đúng `size`, checksum từng part và SHA-256 toàn bộ file (nếu contract yêu cầu), định dạng/scan bảo mật. Chỉ khi đã xác minh và lưu bền vững mới công bố file.

~~~http
HTTP/1.1 201 Created
Location: https://api.example.test/v1/files/file_73a2
Content-Type: application/json

{"id":"file_73a2","status":"AVAILABLE"}
~~~

Nếu bước ghép, quét virus hoặc xử lý media mất thời gian, server có thể trả **`202 Accepted`** và một operation monitor để theo dõi; không trả `201` file sẵn sàng khi xử lý thực tế chưa xong. Completion cần idempotency/transaction/CAS để hai request đồng thời không tạo hai file hoặc hai lần publish. Có thể khóa chuyển `OPEN → FINALIZING` nguyên tử rồi tạo file và ghi mapping kết quả.

### 3.5. Hủy và hết hạn

~~~http
DELETE /v1/uploads/up_8c42 HTTP/1.1
Authorization: Bearer <access-token>
~~~

Có thể trả `204 No Content` khi session bị đánh dấu hủy; cleanup chạy nền. Với `FINALIZING`, trả `409` hoặc xử lý theo cancellation policy. Dọn part hết TTL nhưng phải tránh race với upload/completion còn hợp lệ.

## 4. Tính nhất quán: không được tin riêng response của một part

Một state store tối thiểu chứa:

~~~text
upload_session(id, owner_id, tenant_id, size, part_size,
               expected_sha256, state, expires_at, version)
upload_part(upload_id, part_number, size, checksum,
            object_key, committed_at)
file(id, owner_id, tenant_id, object_key, state)
~~~

### 4.1. Điều kiện cần ở tầng lưu trữ

- Unique key `(upload_id, part_number)`; replay cùng byte an toàn, khác byte bị từ chối.
- Chỉ đánh dấu `COMMITTED` sau khi byte đã ghi bền vững và checksum khớp; dọn blob mồ côi nếu DB commit lỗi.
- Đóng băng manifest bằng CAS khi `OPEN → FINALIZING`; không nhận part mới hoặc để hai finalizer cùng publish. Object storage và DB không tự là một transaction ACID; cần reconciliation.

### 4.2. Tại sao không dùng `Content-Range` tùy ý trên PUT file?

Không tự định nghĩa `PUT /files/{id}` với `Content-Range: bytes 0-.../...` và cho rằng HTTP chuẩn đã quy định đó là “partial PUT”. Theo ngữ nghĩa HTTP, **PUT thông thường thay thế representation đích**, còn `Content-Range` là trường được dùng chủ yếu trong **partial content response**; origin server cho phép PUT trên target thông thường phải xử lý request PUT chứa Content-Range theo quy tắc HTTP, không âm thầm hiểu thành ghép byte.

Nếu cần partial update, dùng resource part riêng như `PUT /uploads/{id}/parts/{n}`, hoặc giao thức định nghĩa **PATCH/offset** rõ ràng (ví dụ tus) cùng cơ chế resume. Phân biệt hẳn với `Range` trên GET phục vụ tải xuống.

## 5. Giao thức tus: resumable upload có quy ước sẵn

**tus** là giao thức resumable upload mở, sử dụng HTTP với các header và ngữ nghĩa rõ. Tính tương thích đến từ **client và server cùng triển khai tus**, không phải chỉ dùng vài tên header giống nó.

### 5.1. Khởi tạo upload và hỏi offset

Ví dụ tus 1.0.0 với creation extension:

~~~http
POST /files HTTP/1.1
Host: uploads.example.test
Authorization: Bearer <access-token>
Tus-Resumable: 1.0.0
Upload-Length: 10485760
Content-Length: 0
~~~

~~~http
HTTP/1.1 201 Created
Tus-Resumable: 1.0.0
Location: /files/u_91
~~~

Sau mất mạng, client **không đoán offset** từ số byte nó đã gửi. Nó hỏi server:

~~~http
HEAD /files/u_91 HTTP/1.1
Authorization: Bearer <access-token>
Tus-Resumable: 1.0.0
~~~

~~~http
HTTP/1.1 200 OK
Tus-Resumable: 1.0.0
Upload-Offset: 5242880
Upload-Length: 10485760
Cache-Control: no-store
~~~

Offset là số byte server đã **chấp nhận theo hợp đồng tus**, không phải số byte client đã viết ra socket. Tùy extension/cấu hình, server còn công bố `Upload-Expires` để client biết giới hạn thời gian tiếp tục.

### 5.2. Gửi tiếp bằng PATCH

~~~http
PATCH /files/u_91 HTTP/1.1
Authorization: Bearer <access-token>
Tus-Resumable: 1.0.0
Content-Type: application/offset+octet-stream
Upload-Offset: 5242880
Content-Length: 5242880

<5 MiB bytes tiếp theo>
~~~

~~~http
HTTP/1.1 204 No Content
Tus-Resumable: 1.0.0
Upload-Offset: 10485760
~~~

Nếu client gửi `Upload-Offset` khác offset hiện tại, tus dùng **`409 Conflict`** để báo xung đột; client nên HEAD lấy offset thực rồi tiếp tục. Khi response PATCH bị mất, **HEAD trước khi gửi lại**, tránh append bytes hai lần. Một số tính năng như checksum, expiration, termination hoặc concatenation thuộc **extension** cần được server và client thương lượng/hỗ trợ, không mặc định mọi triển khai tus đều có.

**Quan trọng:** `PATCH + Upload-Offset` ở trên có nghĩa theo **tus**, không phải cơ chế PATCH chung của mọi REST API. Cài thư viện tương thích hoặc tuân thủ đầy đủ wire protocol (phiên bản, status, headers, discovery, lỗi, extension), đừng xây bản “gần giống tus” rồi tuyên bố tương thích.

## 6. Lựa chọn object storage multipart và URL ký

Với lượng file lớn, luồng `client → REST API → object storage` khiến API phải nhận rồi truyền lại mọi byte. Một kiến trúc khác:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as REST API
    participant O as Private object storage
    C->>A: POST /uploads (metadata, identity)
    A->>A: Kiểm tra quyền, quota, size/type
    A->>O: Create multipart upload
    A-->>C: uploadId + signed URLs cho các part
    par Gửi part 1
        C->>O: PUT part 1 bằng signed URL
        O-->>C: Part receipt / ETag
    and Gửi part 2
        C->>O: PUT part 2 bằng signed URL
        O-->>C: Part receipt / ETag
    end
    C->>A: POST /uploads/{id}/completions
    A->>O: Xác minh part, complete multipart
    A->>A: Scan/verify và publish file metadata
    A-->>C: 201 file hoặc 202 monitor
~~~

Trong mô hình này, **control plane** của ứng dụng vẫn kiểm tra auth, quota, metadata, ownership và thời hạn; **data plane** truyền byte trực tiếp tới storage. Cách này giảm băng thông/CPU API nhưng tăng trách nhiệm quản lý signed URLs, part receipts, CORS và trạng thái phía provider.

### 6.1. Điều khác nhau giữa storage provider

**S3-compatible multipart** dùng `CreateMultipartUpload`, `UploadPart`, liệt kê part, `CompleteMultipartUpload` và abort; cần đúng giới hạn part/receipt của provider. **Cloud storage resumable** thường cấp session URI/token và API hỏi phần đã nhận. **Ứng dụng + object store** tự giữ manifest và cleanup; **tus + storage backend** yêu cầu adapter bảo đảm ghi bền vững. Không dùng ETag multipart của provider như MD5/SHA-256 toàn file; kiểm tra checksum theo API chính thức của provider.

### 6.2. Signed upload URL là quyền có thời hạn

Signed URL có thể cho phép PUT mà không cần JWT của ứng dụng tại object storage. Vì vậy:

- Chỉ ký **object key thuộc upload session đã authorize**, đúng part/method, thời hạn ngắn.
- Không nhận raw `bucket`, `objectKey` hoặc target URL từ client để ký.
- Hạn chế kích thước, checksum, content type và metadata theo cơ chế provider hỗ trợ; xác minh lại khi completion.
- Không log đầy đủ URL chứa chữ ký; dùng HTTPS, kiểm soát CORS và redirect; không gửi bearer token API sang host storage.
- Nếu user bị thu hồi quyền, **chữ ký đã phát có thể còn dùng tới khi hết hạn**. Với chính sách cần thu hồi tức thời, dùng TTL rất ngắn, hủy session/provider upload hoặc proxy có recheck quyền.
- Abort multipart upload chưa hoàn tất và có job dọn dữ liệu tạm để tránh rò chi phí lưu trữ.

**Completion phải do backend có quyền thực hiện sau khi kiểm tra manifest**. Không cho client tự gửi “file đã sạch” hoặc tùy chọn public-read để bypass antivirus, classification và ACL. File mới nên mặc định ở trạng thái `QUARANTINED/PROCESSING`; chỉ đổi `AVAILABLE` sau khi các kiểm tra đã hoàn tất.

## 7. Tiếp tục **download** là bài toán HTTP Range khác upload

Tệp đã được publish và người dùng muốn tải tiếp sau khi mất kết nối ở byte thứ 1.048.576. HTTP hỗ trợ byte range trên GET:

~~~http
GET /v1/files/file_73a2/content HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Range: bytes=1048576-
If-Range: "file-73a2-v1"
~~~

Nếu server hỗ trợ ranges, file **chưa đổi** và phạm vi hợp lệ:

~~~http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 1048576-20971519/20971520
Content-Length: 19922944
ETag: "file-73a2-v1"
Content-Type: application/octet-stream

<đúng phần byte đã yêu cầu>
~~~

Client chỉ **append** bytes nếu nhận `206` với `Content-Range` và validator đúng. Nếu file thay đổi so với strong ETag trong `If-Range`, server có thể trả `200 OK` với **toàn bộ representation**; lúc đó phải ghi lại từ đầu, không nối vào file cũ. Nếu phạm vi không thỏa, `416 Range Not Satisfiable` có thể có:

~~~http
HTTP/1.1 416 Range Not Satisfiable
Content-Range: bytes */20971520
~~~

Lưu ý:

- Server không bắt buộc hỗ trợ Range cho mọi representation; có thể trả `200` toàn bộ dù request có `Range`. Client phải nhận diện.
- `If-Range` thường dùng **strong ETag** hoặc ngày sửa đổi hợp lệ theo HTTP; weak ETag không thích hợp để xác minh nối byte.
- Range là byte của **selected representation**, nên content encoding/biến thể representation phải nhất quán; không nối byte nén và không nén.
- Mỗi GET/range vẫn phải kiểm tra quyền file, tenant và expiry; signed download URL cần chính sách tương tự upload URL.
- Hạn chế nhiều range nhỏ/trùng/đảo ngược nhằm chống khuếch đại I/O; kiểm soát download concurrency.

**Phân biệt dứt khoát:** `Range`/`206`/`Content-Range` ở đây là **tải xuống**; chúng không thay thế `Upload-Offset` của tus hoặc part manifest của upload.

## 8. Java/Spring: nhận part dạng stream, không đưa toàn bộ file vào RAM

Đây là ví dụ Spring MVC tập trung ở HTTP boundary. Giả định backend có một `UploadService` kiểm soát tenant/owner, quota, part size, digest, trạng thái và ghi bền vững. Với binary body, sử dụng `HttpServletRequest.getInputStream()` thay vì `byte[]` hay đọc toàn bộ content vào bộ nhớ.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.io.IOException;
import java.net.URI;
import org.springframework.http.*;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/uploads")
class UploadController {
    private final UploadService service;
    UploadController(UploadService service) { this.service = service; }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @PreAuthorize("hasAuthority('SCOPE_files.write')")
    ResponseEntity<SessionView> create(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CreateUploadRequest input) {
        SessionView session = service.create(jwt.getSubject(), key, input);
        return ResponseEntity
            .created(URI.create("/v1/uploads/" + session.id()))
            .cacheControl(CacheControl.noStore())
            .body(session);
    }

    @GetMapping("/{id}")
    @PreAuthorize("hasAuthority('SCOPE_files.write')")
    ResponseEntity<SessionView> status(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable String id) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(service.visibleSession(jwt.getSubject(), id));
    }

    @PutMapping(path = "/{id}/parts/{part}",
                consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    @PreAuthorize("hasAuthority('SCOPE_files.write')")
    ResponseEntity<Void> part(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable String id,
            @PathVariable int part,
            @RequestHeader(value = "Content-Length", required = false)
                Long declaredLength,
            @RequestHeader("Content-Digest")
                String digest,
            HttpServletRequest request) throws IOException {
        if (declaredLength == null) {
            throw new LengthRequiredException(); // 411
        }
        // Đếm byte thực tế, kiểm tra digest và ghi bằng streaming
        // ở service; không tin riêng Content-Length do client khai.
        try (var input = request.getInputStream()) {
            boolean newlyStored = service.storePart(
                jwt.getSubject(), id, part, declaredLength,
                digest, input);
            return ResponseEntity.status(
                newlyStored ? HttpStatus.CREATED : HttpStatus.NO_CONTENT)
                .cacheControl(CacheControl.noStore())
                .build();
        }
    }
}

record CreateUploadRequest(
    @NotBlank String fileName,
    @NotBlank String contentType,
    @Min(1) long size,
    @NotBlank String sha256
) {}

record SessionView(
    String id, String status, int partSize,
    java.util.List<Integer> missingParts
) {}
~~~

Đoạn code là **skeleton**; `UploadService` và `LengthRequiredException` cần triển khai, exception phải được ánh xạ sang HTTP/Problem Details. Không dùng mỗi `jwt.getSubject()` làm toàn bộ phân quyền nếu còn tenant/project; service phải lấy principal/tenant đã được xác minh và áp chính sách trên **session cụ thể**. `@PreAuthorize` chỉ là lớp scope tổng quát, không thay kiểm tra object-level.

### 8.1. Những việc bắt buộc trong `storePart`

1. Kiểm tra session còn `OPEN`, chưa hết hạn, đúng owner/tenant; part number nằm trong miền hợp lệ, concurrency quota chưa vượt.
2. Tính **expected byte count** từ `partSize` và tổng size; từ chối part quá lớn trước khi dùng nhiều tài nguyên.
3. Stream vào file/blob **tạm, chưa public**; vừa ghi vừa đếm byte và tính SHA-256, giới hạn số byte thực nhận (không tin chỉ `Content-Length`).
4. Xác minh count và digest. Nếu lệch, xóa phần tạm và trả lỗi hợp đồng (ví dụ `400`/`422`), không đánh dấu đã nhận.
5. Commit part metadata cùng tính duy nhất `(uploadId, partNumber)`. Replay cùng nội dung là an toàn; khác nội dung trả `409`.
6. Nếu ghi blob thành công nhưng commit DB thất bại, để reconciliation/cleanup xử lý blob mồ côi; không đánh dấu part thành công trước durable commit.

Không lưu upload 10 GiB vào `byte[]`, `MultipartFile.getBytes()` hoặc `ByteArrayOutputStream`. Nếu dùng proxy/nginx/API gateway, xem lại body limits và buffering: một controller streaming không có ích nếu gateway vẫn buffer toàn bộ body vào RAM. Bắt buộc có hạn mức disk tạm, số request song song, timeout và cơ chế backpressure.

### 8.2. API hoàn tất và lỗi nhất quán

Service hoàn tất có thể dùng:

~~~text
POST /v1/uploads/{id}/completions
  -> xác thực + quyền trên upload
  -> CAS OPEN -> FINALIZING
  -> kiểm tra manifest, ghép object, checksum whole-file
  -> scan/kiểm tra type và policy
  -> publish file, COMPLETED
  -> 201 Location /v1/files/{fileId}
~~~

Nếu xử lý nền, trả `202` cùng operation monitor; client **poll monitor** chứ không tạo session mới. Lỗi `409` khi thiếu part/trạng thái xung đột, `413 Content Too Large` khi vượt giới hạn payload, `411` khi yêu cầu chiều dài mà không có, `429` khi vượt quota, `401/403/404` khi thiếu quyền hoặc không thấy resource. `422` có thể dùng cho checksum/validation theo policy đã tài liệu hóa. Tên mã lỗi Problem Details ổn định giúp client biết phần cần gửi lại.

**OpenAPI 3.1:** mô tả JSON khi tạo session, `Idempotency-Key`, binary request body và `Content-Digest` của part, schema manifest, các mã `201/204/409/413` và `201 Location` hoặc `202` lúc complete. OpenAPI không tự thực thi quota, ACL, checksum hay idempotency: phải có kiểm thử runtime.

## 9. Bảo mật upload và download

### 9.1. Không biến upload thành ghi file tùy ý

- **Authentication/authorization:** kiểm tra quyền tạo session, ghi part, xem manifest, complete, abort và tải file **trên đúng owner/tenant/project**. ID ngẫu nhiên khó đoán không phải ACL.
- **Đường dẫn:** không dùng `fileName` của client làm đường dẫn lưu trữ; tự tạo object key ngẫu nhiên. Loại bỏ traversal (`../`), path tuyệt đối, ký tự điều khiển và tên file độc hại khi tạo `Content-Disposition`.
- **Quota:** giới hạn tổng byte đã đặt chỗ, file size, số part, active sessions, dung lượng staging, upload đồng thời theo tenant và tỷ lệ request. Giải phóng quota sau abort/expiry.
- **Kiểm tra nội dung:** `Content-Type` và phần mở rộng không đáng tin. Kiểm tra magic bytes/định dạng, scan malware, chống decompression bomb nếu giải nén, giới hạn chiều sâu archive và các bước chuyển đổi media.
- **Xuất bản có kiểm soát:** file mới lưu private/quarantine; không phục vụ file trước khi hoàn tất checksum và kiểm tra. Với download, đặt `Content-Type`, `Content-Disposition`, `X-Content-Type-Options: nosniff` hợp lý.
- **Tài nguyên hạ tầng:** giới hạn kích thước từng request ở gateway, timeout, số stream, disk staging, băng thông, CPU cho hashing/scan. Không đưa bytes lớn vào log hoặc tracing.
- **Link ký:** scope theo object, method, TTL và chính sách thu hồi; không gửi token API tới origin bên ngoài. Cẩn thận URL ký bị lộ trong log/referrer.

### 9.2. Truy cập song song và race

Hai PUT cùng part hoặc completion giữa lúc ghi phải được đồng bộ bằng unique constraint/CAS; **không** dùng lock chỉ trong một API instance. Signed URL đã cấp có thể còn hợp lệ sau thu hồi quyền; cần TTL ngắn hoặc download/upload proxy nếu phải thu hồi tức thời.

## 10. Kiểm thử hợp đồng và lỗi mạng

| Trường hợp | Kết quả cần xác minh |
|---|---|
| Tạo session hợp lệ | `201` + Location session, cấu hình partSize/expiry đúng |
| POST tạo session timeout rồi retry cùng key/body | Không sinh hai session |
| Gửi đủ ba part và complete | Một file công bố, đúng thứ tự byte và SHA-256 |
| Response PUT part 2 mất nhưng bytes đã commit | GET manifest thấy part 2; retry cùng bytes không nhân đôi |
| Retry part 2 với bytes khác | `409`, part cũ không bị thay |
| Gửi sai size/checksum hoặc phần cuối sai ranh giới | Từ chối, không đánh dấu committed |
| Complete khi thiếu part 2 | Conflict, không phát file tải được |
| Hai completion đồng thời | Tối đa một file logic, replay trả kết quả theo contract |
| Upload sau abort/expiry | Từ chối; không tái mở session |
| Owner ngoài tenant gửi part hoặc GET file | `403/404` theo chính sách, không đọc/ghi |
| Tệp mang đuôi .png nhưng nội dung thực thi | Không tự publish theo extension |
| Tus HEAD khi response PATCH mất | Nhận đúng offset; PATCH sai offset bị `409` |
| Tải `Range` với cùng strong ETag | `206` và byte chính xác |
| `If-Range` dùng validator cũ | Không nối bytes của bản mới với bản cũ |
| URI ký bị hết hạn, đổi method/object | Bị từ chối tại storage |
| Đầy disk staging, thiếu kết nối, scan lỗi | Không thành file AVAILABLE; dọn blob mồ côi |

### Test Java/Spring minh họa

~~~java
// Cần @WebMvcTest/MockMvc, mock UploadService, JWT test identity,
// exception handler và dữ liệu part fixture.
mockMvc.perform(put("/v1/uploads/up_8c42/parts/2")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_files.write")))
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .content(partTwoBytes)
        .header("Content-Digest", expectedDigest))
    .andExpect(status().isCreated());

mockMvc.perform(get("/v1/uploads/up_other_tenant")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_files.write"))))
    .andExpect(status().isNotFound());
~~~

Đây là **assertion minh họa**, chưa phải test chạy độc lập. Với MockMvc, container test có thể tự thiết lập `Content-Length` từ `.content(...)`; cần dựng JWT có subject/tenant phù hợp và service enforce object-level ACL. Integration test nên dùng storage giả lập hoặc staging thật, **làm rớt response sau khi bytes đã ghi**, chạy hai PUT/completion song song, restart server rồi đối chiếu manifest và hash tệp hoàn chỉnh. Test tải với nhiều session để đo bộ nhớ ổn định, throughput và cleanup sau expiry.

## 11. Bài thực hành: tải video 1 GiB qua mạng chập chờn

**Đề bài:** Một ứng dụng Java/Spring cho phép nhân viên của từng tenant tải video ≤ 1 GiB. Người dùng có thể đóng trình duyệt rồi mở lại, upload song song ba phần và sau cùng phát video qua HTTP Range. Video chỉ được xem sau khi quét an toàn.

Thực hiện:

1. Chọn **tus offset** hay **part-number multipart**; giải thích nhu cầu song song, resume và hạ tầng storage.
2. Thiết kế `POST /uploads`, gửi part, `GET manifest`, completion và abort. Nêu status, `Location`, request schema, quyền và retention.
3. Chọn `partSize=8 MiB`. Với file 20 MiB, xác định 3 part và kích thước part cuối; mô tả client phục hồi khi part 1 và 3 đã nhận.
4. Giải thích cách kiểm SHA-256 của mỗi part và file đầy đủ; xử lý replay, mismatch, completion đồng thời.
5. Viết pseudocode `storePart` có giới hạn stream size, unique constraint và quyền tenant/owner; không dùng `getBytes()`.
6. Thiết kế `GET /files/{id}/content` với `Range`, strong `ETag`, `206`/`416` và `If-Range`.
7. Lập ít nhất tám test gồm mất response, restart, sai offset, quyền chéo tenant, checksum, malware, quá quota và signed URL hết hạn.

**Gợi ý:** part 1 và 2 dài 8 MiB, part 3 dài 4 MiB. Sau reconnect, **hỏi manifest** rồi gửi lại chỉ part 2, không gửi lại các part đã commit. Cấm complete nếu file chưa qua scan; nếu scan chạy nền, dùng `202` + monitor và chỉ phát file `AVAILABLE` khi hoàn thành.

## 12. Ghi nhớ

**Kết luận:** Chia phần giúp **khôi phục upload**, nhưng chỉ trở nên đáng tin khi có hợp đồng về **phần đã nhận, retry, kiểm tra tính toàn vẹn, phân quyền và hoàn tất**. Dùng tus khi muốn một giao thức offset có client/server tương thích, dùng object-storage multipart khi cần throughput và giảm tải REST API, và dùng HTTP Range cho **download tiếp tục**. Dù lựa chọn nào, tính đúng đắn phải được kiểm chứng tại cả API, metadata store và nơi lưu byte.
