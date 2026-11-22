# Phân quyền, thời hạn liên kết và dọn tệp không hoàn tất

Một khách hàng upload tệp 3 GB qua URL đã ký. Mạng mất giữa chừng, link hết hạn, client thử lại bằng phiên mới và bỏ quên các part cũ. Nếu link bị lộ hoặc API thiếu kiểm tra quyền, dữ liệu có thể bị truy cập sai phạm vi. Thiết kế an toàn phải kết hợp **phân quyền, TTL, tính nhất quán và cleanup**.

Bài thuộc chương **Tệp và dữ liệu lớn** của **INTEGRATION_API_REST**: kết hợp resource/URI/HTTP status với Java/Spring, bảo mật và kiểm thử thực tế.

## 1. Mục tiêu và ba lớp bảo vệ

Sau bài này, người học có thể:

1. Thiết kế upload session, metadata, finalize và download qua HTTP mà không giữ toàn bộ file trong bộ nhớ ứng dụng.
2. Phân biệt **quyền truy cập vào API** với **quyền sử dụng một URL đã ký**; giới hạn quyền theo user/tenant, thao tác và đối tượng.
3. Chọn thời hạn cho liên kết upload/download, hiểu cách gia hạn và những giới hạn của thu hồi sớm.
4. Xây cơ chế dọn staging object, upload multipart chưa hoàn tất và metadata mồ côi khi client bỏ dở hoặc hệ thống restart.
5. Kiểm soát race giữa finalize, retry và cleanup; chỉ công bố file sau khi kiểm chứng đầy đủ.
6. Tạo hợp đồng Spring MVC với service/repository thực thi quyền, TTL, idempotency và trạng thái bền vững.
7. Kiểm thử cross-tenant, link bị lộ, quá hạn, crash và chu kỳ dọn rác.

Ba bất biến xuyên suốt:

- **A — Access:** chỉ principal được phép mới khởi tạo, xem, hoàn tất hoặc tải file; tệp trong staging **không tự động trở thành tài nguyên công khai**.
- **B — Publish:** file được công bố ở trạng thái **READY** chỉ khi dữ liệu và kiểm tra bảo mật phù hợp, có bản ghi metadata bền vững liên kết với đúng owner/tenant.
- **C — Cleanup:** phiên không hoàn tất cuối cùng sẽ giải phóng quota và dữ liệu tạm, kể cả khi server/worker chết; cleanup **không được xóa file vừa được finalize hợp lệ**.

## 2. Chọn luồng truyền file phù hợp

| Mô hình | Luồng byte | Phù hợp | Điểm cần đánh đổi |
|---|---|---|---|
| **Upload qua API** | Client → Spring → storage | File nhỏ/vừa, cần inspection trực tiếp | Băng thông/connection pool của API chịu tải |
| **Upload trực tiếp bằng URL đã ký** | Client → object storage; API quản lý quyền/metadata | File lớn, nhiều upload đồng thời | URL là khả năng truy cập tạm, phải kiểm chứng trước publish |
| **Multipart/resumable** | Client upload nhiều part rồi complete | File rất lớn, kết nối kém | Part mồ côi, trạng thái/ETag/checksum, abort và recovery |

Ví dụ dùng **direct-to-object-storage** với staging key riêng, không trao storage credentials cho client. Chi tiết ký URL, checksum và multipart **phụ thuộc provider**.

~~~mermaid
sequenceDiagram
    autonumber
    actor C as Client
    participant A as Spring API
    participant D as Database
    participant S as Private object storage
    participant W as Verify / Cleanup worker
    C->>A: POST /v1/uploads + metadata + auth
    A->>D: Lưu session INITIATED + owner + expiry
    A-->>C: 201 + uploadId + URL PUT ngắn hạn
    C->>S: PUT bytes lên staging object
    S-->>C: 200/201 theo provider
    C->>A: POST /v1/uploads/{id}/complete
    A->>D: Chuyển sang VERIFYING có điều kiện
    W->>S: HEAD/checksum, scan, kiểm tra dữ liệu
    W->>D: Commit READY + final object reference
    C->>A: GET /v1/files/{id}
    A-->>C: Metadata hoặc link tải ngắn hạn
~~~

Storage báo ghi thành công **chưa có nghĩa file READY**; backend vẫn phải xác minh nội dung, phiên, kích thước và bảo mật.

## 3. Hợp đồng HTTP cho upload session

### 3.1. Tạo phiên

~~~http
POST /v1/uploads HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json
Idempotency-Key: upload-invoice-2026-118

{
  "fileName": "invoice-118.pdf",
  "contentType": "application/pdf",
  "sizeBytes": 7340032,
  "purpose": "INVOICE_ATTACHMENT"
}
~~~

Sau khi kiểm tra quyền, quota, loại và kích thước dự kiến, API ghi session bền vững:

~~~http
HTTP/1.1 201 Created
Location: /v1/uploads/upl-8d9
Content-Type: application/json
Cache-Control: no-store

{
  "uploadId": "upl-8d9",
  "status": "INITIATED",
  "expiresAt": "2026-11-18T11:00:00Z",
  "upload": {
    "method": "PUT",
    "url": "https://storage.example.test/staging/opaque-key?signature=REDACTED",
    "expiresAt": "2026-11-18T10:15:00Z",
    "headers": {
      "Content-Type": "application/pdf"
    }
  },
  "_links": {
    "self": "/v1/uploads/upl-8d9",
    "complete": "/v1/uploads/upl-8d9/complete"
  }
}
~~~

**Session** tồn tại tới 11:00, **URL PUT** chỉ tới 10:15. Các mốc minh họa dùng UTC và thời hạn hiệu lực do signer/provider bảo đảm.

**_links** là quy ước JSON riêng, không phải HAL chuẩn; **complete** dùng POST theo hợp đồng. URL ký là bí mật tạm thời: không ghi query chữ ký vào log/metric.

### 3.2. Truyền byte tới storage

Client dùng **method, URL và những header được ký** chính xác như hợp đồng:

~~~http
PUT /staging/opaque-key?signature=... HTTP/1.1
Host: storage.example.test
Content-Type: application/pdf
Content-Length: 7340032

<binary bytes>
~~~

Tùy nhà cung cấp, một số header (Content-Type, checksum, Content-Length hoặc điều kiện ghi) có thể nằm trong chữ ký. **Không mặc định chỉ cần đúng URL là được phép thay đổi headers**. Cũng không gửi access token ứng dụng tới host storage; chính URL đã ký và policy storage là cơ chế ủy quyền của thao tác này.

### 3.3. Finalize và kiểm tra trạng thái

~~~http
POST /v1/uploads/upl-8d9/complete HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: complete-upl-8d9

{"expectedSize":7340032,"expectedSha256":"<64 hex digits>"}
~~~

~~~http
HTTP/1.1 202 Accepted
Location: /v1/uploads/upl-8d9
Cache-Control: no-store
Content-Type: application/json

{"uploadId":"upl-8d9","status":"VERIFYING"}
~~~

Server **không tin** checksum hoặc expectedSize từ client như bằng chứng nội dung đã lưu. Nó đối chiếu metadata và nội dung theo khả năng storage, tính/kiểm chứng checksum ở một ranh giới đáng tin, rồi thực hiện scan/quy tắc domain trước khi chuyển **READY**. Với S3 multipart, **ETag không phải lúc nào cũng là MD5**; không dùng ETag làm checksum SHA-256 theo suy đoán.

~~~http
GET /v1/uploads/upl-8d9 HTTP/1.1
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{"uploadId":"upl-8d9","status":"READY","fileId":"file-2a6"}
~~~

| Thao tác | HTTP status minh họa | Ý nghĩa |
|---|---|---|
| Tạo upload session thành công | **201 Created** + Location | Session resource đã tồn tại |
| Hoàn tất đang kiểm tra | **202 Accepted** | Chưa công bố file |
| Đọc trạng thái session | **200 OK** | Body chứa INITIATED/VERIFYING/READY/EXPIRED… |
| Hủy session hợp lệ | **204 No Content** | Hủy nhận thêm dữ liệu; cleanup có thể chạy sau |
| Session đã hết hạn | **410 Gone** hoặc 404 theo contract | Không cho complete |
| Complete sai trạng thái | **409 Conflict** | Không làm hỏng phiên hợp lệ |
| File vượt giới hạn | **413 Content Too Large** | Chặn tại tầng phù hợp; có thể xác định từ metadata |
| Media type không được hỗ trợ | **415 Unsupported Media Type** hoặc lỗi validation | Phân biệt request JSON với loại file thực |
| Rate/quota hoặc sự cố tạm | **429/503** | Có Retry-After khi phù hợp |

**201/202 không đồng nghĩa file đã publish**. Sau timeout, retry bằng **cùng Idempotency-Key** hoặc tra session cũ; đừng tự tạo key mới.

## 4. Phân quyền: hai ranh giới, hai loại bằng chứng

**Tại Spring API**, mọi request tạo/xem/renew/complete/hủy session phải xác thực principal và kiểm tra quyền theo **tenant, chủ sở hữu, mục đích và trạng thái**. Người được thêm hóa đơn cho hợp đồng X không mặc nhiên được tải file của hợp đồng Y.

**Tại object storage**, URL ký hoạt động như **bearer capability**: ai giữ URL còn hiệu lực có thể thực hiện thao tác đã ký trong giới hạn policy của storage, **không cần access token của ứng dụng**. Vì vậy:

- Link rò qua log, browser history, analytics, chat hoặc Referer có thể bị dùng lại.
- ID khó đoán, URL khó đoán hay CORS **không thay thế phân quyền**.
- Chỉ ký đúng **method, staging object key, header/điều kiện cần thiết, thời hạn ngắn**.
- Không tạo presigned URL cho bucket public hoặc object key trực tiếp từ tên file do client cung cấp.
- Mỗi lần cấp **link mới** phải kiểm tra lại quyền, tenant, quota và trạng thái session.

Object key nên được server sinh, không chứa thông tin cá nhân, ví dụ **staging/{opaqueTenant}/{uploadId}/{attemptId}**. Tên file có thể chứa chuỗi **../../secrets.pdf**; coi đó là metadata không đáng tin, không ghép trực tiếp thành filesystem path hoặc storage key.

### 4.1. Quyền phải kiểm tra ở mỗi resource

| Resource/operation | Kiểm tra bắt buộc | Không được chỉ dựa vào |
|---|---|---|
| POST /uploads | Principal, tenant, role, mục đích, size/quota | Tên file hoặc tenantId client tự gửi |
| GET /uploads/{id} | Owner/tenant, quyền đọc trạng thái | Upload ID dạng UUID |
| POST /uploads/{id}/complete | Owner/tenant, trạng thái, deadline, phiên/phiên bản | Client đã sở hữu presigned PUT |
| POST /uploads/{id}/renew | Owner/tenant, session còn hạn, giới hạn renew | URL cũ đã hết hạn |
| GET /files/{id} | Quyền hiện tại với tài liệu nghiệp vụ | Quyền tại lúc tạo file |
| GET /files/{id}/download | Quyền hiện tại, trạng thái READY | ID khó đoán hoặc URL đã phát trước đó |

Truy vấn phải lọc **tenant_id + upload_id** và quyền trên resource nghiệp vụ. Có thể trả 404 thay 403 để che giấu sự tồn tại theo policy.

### 4.2. Content-Type và hiển thị là dữ liệu không tin cậy

Client khai báo **Content-Type: application/pdf** không chứng minh byte là PDF. Sau upload cần xác minh cấu trúc định dạng, quét malware theo chính sách, giới hạn giải nén và có thể chuyển dạng trước khi publish. Khi download:

- Cân nhắc **Content-Disposition: attachment**; sanitize/encode tên file, không phản chiếu raw filename vào header.
- Đặt **X-Content-Type-Options: nosniff** ở nơi trả byte khi phù hợp.
- Chỉ dùng Content-Type của **nội dung đã xác minh**; không tin mù metadata do client khai.
- File HTML/SVG xem trực tiếp cần origin cách ly/sandbox và CSP phù hợp để giảm XSS.

Các header bảo vệ phải được áp dụng tại **storage hoặc proxy thực sự trả byte**, không chỉ ở API trả JSON/redirect.

## 5. Thời hạn URL ký, gia hạn và thu hồi

### 5.1. URL hết hạn khác với phiên upload hết hạn

| Thành phần | TTL minh họa | Khi hết hạn |
|---|---|---|
| **Presigned PUT** | 5–15 phút | Không bắt đầu request mới với link cũ theo policy storage |
| **Upload session** | 1 giờ | Không renew/finalize; đưa vào cleanup |
| **File READY** | Theo retention của tài liệu | Không phụ thuộc TTL của signed URL |

Hiệu lực thực tế của URL còn có thể bị giới hạn bởi **credential dùng để ký, bucket policy hoặc quy tắc provider**. Một số storage kiểm tra hạn **khi request bắt đầu**, nên truyền tệp đã bắt đầu trước lúc URL hết hạn có thể vẫn tiếp tục. Vì vậy không dùng expiry của URL làm bằng chứng rằng không còn byte đang được ghi. Dùng thời điểm UTC tuyệt đối và tính khoảng đệm do clock skew; client không thể tự kéo dài chữ ký.

### 5.2. Renew qua API đã xác thực

~~~http
POST /v1/uploads/upl-8d9/renew HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Content-Type: application/json

{}
~~~

Server chỉ cấp URL mới nếu phiên còn **INITIATED**, còn hạn, người gọi còn quyền, và giới hạn số lần renew chưa bị vượt. URL mới chỉ cho phép thao tác trên đúng staging object/part của phiên; **không mở rộng hạn session vô hạn**. Response có thể là 200 cùng URL/expiry mới và **Cache-Control: no-store**.

Việc cấp URL mới **không tự thu hồi link cũ**. Muốn vô hiệu hóa trước hạn phải dựa trên cơ chế provider-specific như thay credential hoặc policy, với phạm vi ảnh hưởng/độ trễ cần hiểu rõ. Mặc định hãy dùng **TTL ngắn, staging riêng, kiểm tra trạng thái trước publish**, và không trao quyền PUT tới final object.

### 5.3. Chống ghi đè khi link còn hiệu lực

Presigned PUT thường có thể **được gửi lại**; nếu storage cho overwrite cùng key, client hoặc kẻ giữ URL có thể sửa staging **sau khi server HEAD/scan nhưng trước khi publish** (race kiểu TOCTOU). Cách bảo vệ:

1. Cấp key riêng cho **upload attempt**, dùng điều kiện write-once nếu provider hỗ trợ.
2. Khi finalize, xác định **object version/snapshot bất biến**, size và checksum đáng tin.
3. Scan và copy đúng version đó vào **final key riêng không cấp quyền ghi cho client**.
4. Commit READY chỉ khi bản final đã được kiểm chứng; file READY không tham chiếu staging mutable.
5. Quét dọn staging độc lập, kể cả upload muộn bằng URL cũ.

**ETag của multipart object không được mặc định xem là MD5/SHA-256**. Hãy kiểm chứng checksum theo cơ chế provider hỗ trợ hoặc tính qua một tiến trình đáng tin, có giới hạn tài nguyên.

### 5.4. Download sau khi kiểm tra quyền

~~~http
GET /v1/files/file-2a6/download HTTP/1.1
Authorization: Bearer <access-token>
~~~

~~~http
HTTP/1.1 303 See Other
Location: https://storage.example.test/private/final-object?signature=REDACTED
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Đây là một phương án redirect; API cũng có thể trả URL qua JSON hoặc proxy streaming. Signed GET phải giới hạn **object/version, method và TTL**. Người đã nhận link thường có thể dùng nó tới khi hết hiệu lực, ngay cả khi quyền trong ứng dụng thay đổi sau đó. Nếu cần thu hồi tức thời hoặc kiểm tra quyền cho **mỗi Range request**, cân nhắc download qua proxy xác thực hoặc cơ chế revocation đặc thù đã kiểm chứng.

**No-store trên 303 không lan sang response của storage**: cấu hình cache/Content-Disposition tại nơi trả byte. Download lớn có thể cần **Range/206/416**; chú ý header nào bị ràng buộc trong chữ ký.

## 6. Trạng thái bền vững và finalize an toàn

~~~mermaid
stateDiagram-v2
    [*] --> INITIATED: Tạo session
    INITIATED --> VERIFYING: Complete hợp lệ
    VERIFYING --> READY: Verify + scan + publish
    VERIFYING --> REJECTED: Nội dung không đạt
    INITIATED --> CANCELLED: Client hủy
    INITIATED --> EXPIRED: Deadline
    VERIFYING --> FAILED: Lỗi vĩnh viễn
    CANCELLED --> CLEANING
    EXPIRED --> CLEANING
    REJECTED --> CLEANING
    FAILED --> CLEANING
    CLEANING --> CLEANED: Xóa dữ liệu tạm
    READY --> [*]
    CLEANED --> [*]
~~~

Trạng thái nằm trong **DB**, không chỉ RAM. Với direct upload, backend có thể không biết chính xác lúc PUT bắt đầu nên phiên vẫn **INITIATED** cho tới complete. Không tin một boolean **uploaded=true** do client gửi để chuyển thẳng READY.

Metadata cơ bản:

~~~text
uploads(
  upload_id, tenant_id, owner_id, purpose, idempotency_key,
  staging_key, multipart_upload_id, declared_size, declared_type,
  expected_hash, status, expires_at, state_version,
  lease_owner, lease_until, final_key, file_id,
  quota_reservation_id, created_at, updated_at
)
UNIQUE (tenant_id, purpose, idempotency_key)
~~~

Unique constraint chống hai POST đồng thời cùng key. Khi key đã tồn tại, so **fingerprint request chuẩn hóa** (purpose, size, type, target, checksum…) trước khi trả lại cùng session; key trùng với payload khác trả 409. Scope có thể cần thêm operation/user theo yêu cầu; không mở rộng quyền truy cập bằng một key do client đoán.

### 6.1. Race: complete và cleanup cùng tới lúc expiry

Hai bước dưới phải tranh quyền qua **cập nhật có điều kiện nguyên tử**, không dùng SELECT rồi sửa rời rạc:

~~~sql
-- Complete chỉ được chuyển khi phiên còn hạn.
UPDATE uploads
SET status = 'VERIFYING', state_version = state_version + 1
WHERE upload_id = :id AND tenant_id = :tenant
  AND status = 'INITIATED' AND expires_at > now();
~~~

~~~sql
-- Sweeper chỉ được nhận phiên chưa finalize đã hết hạn.
UPDATE uploads
SET status = 'EXPIRED', state_version = state_version + 1
WHERE upload_id = :id
  AND status = 'INITIATED' AND expires_at <= now();
~~~

Nếu số row cập nhật bằng 0, đọc lại trạng thái và xử lý theo hợp đồng. **Không delete object trước khi giành quyền cleanup**; cũng không cho worker finalize cũ ghi READY khi phiên đã đổi sang REJECTED/CLEANING. Worker cần lease/fencing token hoặc compare-and-set trên phiên bản trạng thái.

### 6.2. DB và storage không có transaction chung

Một quy trình publish bền vững:

1. Chuyển DB sang VERIFYING, ghi outbox event hoặc cho scanner phát hiện.
2. Worker kiểm tra bản staging xác định, scan và copy vào **final key bất biến**.
3. Commit metadata READY gồm file ID, owner/tenant, key/version và checksum; chỉ sau đó mới cấp download.
4. Nếu copy xong nhưng DB commit lỗi, reconciliation phát hiện **final object mồ côi**; nếu DB còn VERIFYING sau crash, worker có thể tiếp tục idempotently.

Do copy storage và commit DB **không atomic**, phải thiết kế checkpoint/trạng thái bền vững và cleanup cho cả hai chiều lỗi. Không giữ transaction database mở suốt quá trình stream gigabyte hoặc scan tệp.

## 7. Dọn file không hoàn tất: sweeper + storage lifecycle

Client có thể đóng tab, mất điện hoặc không bao giờ gọi complete. Job dọn rác định kỳ (*sweeper*) là một phần của thiết kế, không phải công việc thủ công sau khi ổ đĩa đầy.

**Quy trình đề xuất:**

1. Scanner tìm session **INITIATED đã quá expires_at**; dùng compare-and-set để chuyển **EXPIRED/CLEANING** và giành lease cho một worker.
2. Chặn renew/complete mới cho session đã bị claim. Chờ **grace period** đủ cho các PUT đã bắt đầu gần deadline, tùy SLA và đặc tính provider.
3. Liệt kê các staging object version/part thuộc session, **abort multipart upload chưa complete**, xóa staging object theo key/version đã lưu.
4. Ghi tiến độ cleanup bền vững; nếu provider timeout, **retry idempotent**, không đánh dấu CLEANED quá sớm.
5. Khi xác nhận phần dữ liệu tạm đã được giải phóng theo policy, cập nhật **CLEANED**, hoàn quota reservation và giữ metadata tombstone đủ lâu để chống retry tạo lại ngoài ý muốn.
6. Scanner độc lập quét **staging orphan** và **final object orphan** dựa trên DB/manifest để xử lý các lần crash giữa storage và DB.

Không tin rằng DELETE đã gửi đi nghĩa là object chắc chắn biến mất: lệnh có thể timeout sau khi xóa hoặc trước khi xóa. **Lặp delete cùng key/version** thường là thao tác an toàn nếu provider/hợp đồng hỗ trợ; đừng dọn key chỉ dựa trên prefix rộng khiến xóa cả file đang READY.

### 7.1. Hai biện pháp dọn rác bổ sung cho nhau

| Cơ chế | Vai trò | Giới hạn |
|---|---|---|
| **Application sweeper** | Hiểu owner, session status, quota, uploadId, lease; quyết định theo nghiệp vụ | Có thể tạm ngừng khi DB/worker lỗi |
| **Object storage lifecycle** | Xóa staging object cũ, abort multipart upload chưa hoàn tất theo age | Không hiểu hoàn toàn các transaction/status nghiệp vụ |
| **Reconciliation job** | So sánh manifest DB với object/part thực tế, phát hiện orphan | Cần bảo vệ quyền list/delete và quản lý chi phí scan |

Đặt lifecycle storage **sau thời gian phiên hợp lệ + buffer/grace** để không xóa part của người đang upload. Provider có thể đo tuổi multipart từ lúc **initiate upload**, khác thời điểm refresh signed URL; cấu hình lifecycle phải xét thời gian tuyệt đối của toàn session, không chỉ TTL từng link.

### 7.2. Chống race giữa cleanup và client PUT muộn

Ngay cả khi sweeper đã xóa staging key, một request PUT bắt đầu trước lúc URL hết hạn có thể hoàn thành **sau khi cleanup chạy** và làm object xuất hiện lại. Không chỉ xóa một lần rồi giả định staging sạch:

- **READY không được trỏ vào staging**; final key chỉ do backend kiểm soát.
- Giữ tombstone session và **lặp sweeper/lifecycle** sau cửa sổ có thể có upload muộn.
- Nếu provider hỗ trợ, dùng điều kiện ghi/versioning/policy để giảm khả năng ghi muộn.
- Tách prefix staging với final, giới hạn quyền DeleteObject của cleanup worker theo prefix và identity thích hợp.

Metric cần có: **orphan bytes, số multipart upload mở, tuổi job chưa hoàn tất, cleanup error/retry, quota chưa giải phóng**. Mục tiêu không chỉ là “xóa cho hết”, mà là **không xóa nhầm và dọn được sau restart**.

## 8. Multipart/resumable: phần chưa hoàn tất phải được quản lý riêng

Với file vài GB, provider có thể hỗ trợ multipart:

~~~text
POST /v1/uploads (metadata, auth, idempotency key)
  -> server tạo session và multipart upload ID tại storage
  -> cấp signed URLs cho từng partNumber cụ thể
PUT part 1, PUT part 2, ... qua storage
POST /v1/uploads/{id}/complete (client báo parts đã gửi)
  -> server đối chiếu part list/size/checksum
  -> provider complete multipart; server verify/scan/publish
~~~

**Multipart upload ID của storage** cũng cần được lưu bền vững trong metadata. Nếu client đã upload 20/30 phần rồi mất mạng, server có thể cấp lại URL cho phần thiếu sau khi kiểm tra quyền và session còn hạn. Không lập một multipart upload mới cho cùng logical session mỗi lần client refresh.

Nếu client hủy giữa chừng, gọi **abort multipart upload** theo API của provider và chạy cleanup lặp theo policy. Một số provider có thể còn các phần đang upload *in-flight* khi abort, nên dọn lại/lifecycle là lớp bảo vệ bổ sung. **Part ETag** thường có vai trò trong complete multipart nhưng không thay cho checksum toàn file có ý nghĩa bảo mật.

Không nhận tin tuyệt đối vào danh sách parts từ client: server kiểm tra **part number, checksum, thứ tự, tổng size, tính đầy đủ và trạng thái session** trước khi gọi complete. Quy trình provider complete có thể timeout sau khi đã ghép object; hãy **HEAD/query trạng thái** để đối soát trước khi tạo thêm một upload khác.

## 9. Java/Spring Boot: API quản lý phiên, không truyền toàn bộ byte

Ví dụ dùng **Spring Boot 3 / Java 17**, với interface độc lập provider. Controller thể hiện HTTP contract; transaction, storage signer, scanner, lease và authorization phải được hiện thực ở tầng service.

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import java.net.URI;
import java.time.Instant;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

record NewUpload(
        @NotBlank String fileName,
        @NotBlank String contentType,
        @Positive long sizeBytes,
        @NotBlank String purpose) {}
record PutLink(URI url, Instant expiresAt,
        Map<String, String> requiredHeaders) {}
record UploadView(String uploadId, String status,
        Instant expiresAt, PutLink uploadLink, String fileId) {}
record CompleteUpload(@NotBlank String expectedSha256) {}

interface UploadWorkflow {
    UploadView create(Authentication user, String key, NewUpload request);
    UploadView get(Authentication user, String uploadId);
    PutLink renew(Authentication user, String uploadId);
    UploadView complete(Authentication user, String uploadId,
            CompleteUpload request);
    void cancel(Authentication user, String uploadId);
    URI issueSignedDownload(Authentication user, String fileId);
}

@RestController
@RequestMapping("/v1")
class UploadController {
    private final UploadWorkflow workflow;

    UploadController(UploadWorkflow workflow) {
        this.workflow = workflow;
    }

    @PostMapping("/uploads")
    ResponseEntity<UploadView> create(
            @Valid @RequestBody NewUpload request,
            @RequestHeader("Idempotency-Key") String key,
            Authentication user) {
        UploadView view = workflow.create(user, key, request);
        return ResponseEntity.created(
                URI.create("/v1/uploads/" + view.uploadId()))
                .cacheControl(CacheControl.noStore()).body(view);
    }

    @GetMapping("/uploads/{id}")
    ResponseEntity<UploadView> get(
            @PathVariable String id, Authentication user) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(workflow.get(user, id));
    }

    @PostMapping("/uploads/{id}/renew")
    ResponseEntity<PutLink> renew(
            @PathVariable String id, Authentication user) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .body(workflow.renew(user, id));
    }

    @PostMapping("/uploads/{id}/complete")
    ResponseEntity<UploadView> complete(
            @PathVariable String id,
            @Valid @RequestBody CompleteUpload request,
            Authentication user) {
        UploadView view = workflow.complete(user, id, request);
        HttpStatus code = "READY".equals(view.status())
                ? HttpStatus.OK : HttpStatus.ACCEPTED;
        return ResponseEntity.status(code)
                .location(URI.create("/v1/uploads/" + id))
                .cacheControl(CacheControl.noStore()).body(view);
    }

    @DeleteMapping("/uploads/{id}")
    ResponseEntity<Void> cancel(
            @PathVariable String id, Authentication user) {
        workflow.cancel(user, id);
        return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore()).build();
    }

    @GetMapping("/files/{id}/download")
    ResponseEntity<Void> download(
            @PathVariable String id, Authentication user) {
        URI signedGet = workflow.issueSignedDownload(user, id);
        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(signedGet)
                .cacheControl(CacheControl.noStore())
                .header("Referrer-Policy", "no-referrer").build();
    }
}
~~~

**Các điều kiện mà UploadWorkflow phải thực hiện:**

- **create:** kiểm tra quyền/quota; fingerprint payload, UNIQUE key và DB transaction. Retry cùng key/payload trả **cùng uploadId**. Controller minh họa luôn trả 201, kể cả replay; API cũng có thể trả 200 nếu hợp đồng quy định.
- **get/renew/complete/cancel:** lấy tenant từ Authentication, truy vấn trong scope quyền; không cấp URL mới cho session READY/CANCELLED/EXPIRED.
- **complete:** dùng compare-and-set; verify/scan/publish bất đồng bộ; lặp request không tạo một file READY thứ hai.
- **issueSignedDownload:** kiểm tra quyền hiện tại, trạng thái READY, object/version, TTL; không log URL chứa chữ ký.
- **Worker:** transaction DB ngắn; storage copy/scan được checkpoint riêng, có retry và khôi phục khi crash.

Đây là mẫu code, **chưa chạy độc lập**: cần implementation service, DB, storage SDK, Spring Security/Validation và error handler. Một REST API production nên trả lỗi theo **Problem Details** với mã ứng dụng ổn định. Nếu chọn truyền file qua Spring bằng **MultipartFile**, phải giới hạn kích thước, timeout và sử dụng streaming, không đọc toàn bộ file lớn vào heap.

## 10. Ma trận kiểm thử và fault injection

| Tình huống | Bằng chứng PASS |
|---|---|
| Hai POST cùng key/payload đồng thời | Chỉ một session/quota reservation |
| Key cũ, payload khác | 409, session cũ không đổi |
| Tenant B đoán uploadId/fileId của A | Không đọc, renew, complete hoặc tải được |
| Lộ presigned PUT trong thời gian còn hạn | Chỉ ghi được staging key/method đã ký, không đọc final |
| Signed URL hết hạn | Không tạo PUT mới; renew chỉ qua API đã xác thực |
| PUT cuối đến sau cancel/expiry | Không được publish; sweeper dọn được object muộn |
| Complete và sweeper chạy đồng thời | Chỉ một state transition thắng |
| Worker crash sau copy trước commit READY | Reconcile không publish sai hoặc bỏ lại final orphan |
| Multipart chưa complete, storage/broker restart | Resume/abort đúng upload ID, part orphan được dọn |
| Tệp giả PDF/chứa malware hoặc size lệch | REJECTED, không có download READY |
| Quyền bị thu hồi sau khi cấp signed GET | API không cấp link mới; link cũ chỉ sống trong TTL đã công bố |
| Cleanup timeout hoặc gọi hai lần | Có thể retry, không xóa nhầm file READY, giải phóng quota |

Kiểm thử Spring MockMvc xác minh status/Location/ủy quyền; nhưng **không chứng minh** crash recovery nếu chưa dùng storage giả lập có fault injection hoặc môi trường staging thực. Đặc biệt phải cắt kết nối **sau khi PUT thành công** và cho worker chết **giữa copy và DB commit**.

## 11. Bài tập thực hành

Một hệ thống lưu hồ sơ tuyển dụng nhận tệp tối đa **5 GB**, có **300 phiên upload đồng thời**. Phiên tồn tại 2 giờ, link PUT sống 10 phút, file chỉ được tải khi quét xong. Một client mất mạng ở part 8/12 và có thể retry sau khi ứng dụng restart.

Hãy thiết kế **(1)** hợp đồng POST/GET/renew/complete/download; **(2)** bảng trạng thái và unique key chống trùng; **(3)** permission theo user/tenant; **(4)** lease cleanup và storage lifecycle; **(5)** quy trình scan/publish không bị overwrite; **(6)** sáu test lỗi quan trọng.

**Gợi ý:** giữ multipartUploadId và danh sách part/checksum trong nguồn bền vững, ký lại URL cho part thiếu khi session còn hạn, không dùng signed URL làm bằng chứng quyền sở hữu. Tại complete, kiểm chứng snapshot rồi chuyển VERIFYING; chỉ READY sau scan. Sweeper đánh dấu hết hạn bằng compare-and-set trước khi abort part; thêm lifecycle phòng orphan.

## 12. Checklist và tham khảo

- [ ] Auth/tenant/owner được kiểm tra ở mọi metadata operation và trước khi phát link.
- [ ] Signed URL giới hạn method/key/TTL; staging tách final; không log chữ ký.
- [ ] Finalize xác minh size/checksum/scan trên object version ổn định.
- [ ] Session, multipart ID, lease, quota và kết quả được lưu bền vững.
- [ ] Complete/cleanup cạnh tranh nguyên tử; có sweeper, lifecycle và reconciliation.
- [ ] Có test cross-tenant, expired link, race, restart và upload muộn.

Tham khảo: **RFC 9110 HTTP Semantics** (201/202/303, Range), https://www.rfc-editor.org/rfc/rfc9110.html; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html; **OWASP File Upload Cheat Sheet**, https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html; **Spring MVC Multipart**, https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/multipart.html; tài liệu ký URL và abort multipart của **provider object storage đang sử dụng**.

**Kết luận:** signed URL không đủ để bảo vệ file lớn. Cần kiểm tra quyền trước khi cấp link, tách TTL của link và session, verify trước publish, dọn upload dang dở sau crash. **Quyền, trạng thái bền vững và cleanup chống race** quyết định tính đúng của REST API quản lý tệp.
