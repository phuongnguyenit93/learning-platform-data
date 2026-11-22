# Checksum, tác vụ quét và công bố tệp sau xử lý

## 1. Bài toán: đã nhận tệp chưa có nghĩa được phép tải xuống

Một API nhận tài liệu hợp đồng, ảnh người dùng hoặc báo cáo CSV dung lượng lớn. Client upload xong và nhận phản hồi thành công. Nếu ứng dụng đưa ngay tệp vào vùng công khai, người khác có thể tải một tệp **bị hỏng, giả mạo định dạng hoặc chứa mã độc** trước khi các bước kiểm tra hoàn tất. Ngược lại, nếu chờ quét virus ngay trong request HTTP, upload lớn có thể timeout, chiếm thread và làm khó việc retry.

Một thiết kế đáng tin cần tách ba lời khẳng định:

1. **Đã nhận đủ bytes:** quá trình truyền và lưu tạm hoàn thành; checksum được xác minh theo hợp đồng.
2. **Đã xử lý an toàn theo chính sách:** hệ thống đã xác định loại tệp, quét mã độc/nội dung và thu được verdict hợp lệ.
3. **Đã công bố:** metadata và đường tải xuống được mở có kiểm soát **chỉ sau khi** các bước bắt buộc thành công.

Trong chương **Tệp và dữ liệu lớn** của module **INTEGRATION_API_REST**, bài này kết nối thiết kế resource, URI, phương thức và mã trạng thái HTTP với xử lý bất đồng bộ, idempotency, bảo mật, hợp đồng dữ liệu và kiểm thử Java/Spring. Trọng tâm không phải thuật toán antivirus, mà là **giao thức REST và ranh giới tin cậy** xung quanh checksum, tác vụ quét và xuất bản.

Sau bài học, bạn sẽ biết thiết kế vòng đời tệp, phân biệt **integrity** với **safety**, triển khai lưu cách ly (*quarantine*), ghi công việc quét bền vững, đóng các cửa sổ race khi công bố, và kiểm thử việc **không tệp chưa đạt kiểm tra nào được phân phối**.

## 2. Checksum không phải chứng nhận an toàn

### 2.1. SHA-256 trả lời câu hỏi gì?

Client có thể tính **SHA-256 của đúng bytes nội dung tệp** trước khi upload, gửi giá trị kỳ vọng và để server tự tính lại từ bytes đã nhận:

~~~text
expectedSha256 (client)
         |
         v
Upload bytes ----> Quarantine riêng tư
         |                |
         +---- SHA-256 ---+-- so expected
                                |
                     khớp: tiếp tục kiểm tra
                     khác: từ chối/không công bố
~~~

Ví dụ tệp giả định có SHA-256 (dạng hex 64 ký tự):

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Đây là SHA-256 của **chuỗi bytes rỗng**; nó chỉ minh họa cú pháp. Một API tài liệu thường **không cho tệp rỗng** và phải kiểm tra kích thước độc lập. Với tệp thực, digest phụ thuộc **toàn bộ bytes**, không phụ thuộc tên tệp.

Checksum giúp phát hiện sai lệch bytes do truyền/lưu/xử lý. Nó **không chứng minh** client đáng tin, không chứng minh nội dung an toàn và **không phải chữ ký số**: kẻ tấn công có thể sửa tệp rồi cung cấp SHA-256 mới tương ứng. Muốn xác minh **nguồn phát hành** hoặc tính xác thực từ một bên tin cậy, cần chữ ký số/MAC hoặc cơ chế xác thực thích hợp **ngoài** checksum thuần túy.

### 2.2. Định nghĩa đúng dữ liệu được hash

Với `multipart/form-data`, `expectedSha256` trong bài là digest của **bytes thuộc phần file**, không phải toàn bộ multipart body có boundary và form fields. Nếu dùng `Content-Digest` (RFC 9530), phải tuân thủ ngữ nghĩa **HTTP message content**, không tự đồng nhất nó với file part. Hợp đồng cần cố định thuật toán, encoding, phạm vi bytes và cách báo lỗi.

### 2.3. Ba loại kiểm tra phục vụ ba mục đích

| Kiểm tra | Câu hỏi | Không bảo đảm |
|---|---|---|
| **SHA-256** | Bytes server có giống bytes mà request khai báo? | Nguồn đáng tin hay không, có mã độc không |
| **Kiểm tra định dạng** | Bytes có phù hợp loại tệp được phép, cấu trúc có hợp lệ? | Không tồn tại payload khai thác trong định dạng hợp lệ |
| **Malware/content scanning** | Bộ quét với phiên bản quy tắc hiện tại có phát hiện nguy cơ thuộc chính sách? | Tệp an toàn tuyệt đối trước mọi mối đe dọa mới |

Không dùng kết quả `checksumValid=true` làm điều kiện duy nhất để phát link download.

## 3. Kiến trúc: vùng cách ly, worker quét và cổng công bố

~~~mermaid
flowchart TD
    C["Client"] -->|POST multipart| API["Upload API"]
    API -->|stream + SHA-256| Q[("Private quarantine storage")]
    API -->|metadata + outbox| DB[("Database")]
    DB -->|event| W["Scanner worker"]
    W -->|đọc immutable version| Q
    W -->|quét / kiểm tra policy| V{"Verdict?"}
    V -->|Không đạt| R["REJECTED - không cấp download"]
    V -->|Không rõ/lỗi| F["SCAN_FAILED - retry/đối soát"]
    V -->|Đạt| P["Private published object"]
    P -->|ghi metadata READY| DB
    C -->|GET /files/id/content| G{"Auth + READY?"}
    G -->|Không| N["Không phát bytes hoặc URL"]
    G -->|Có| D["Đường download có kiểm soát"]
    DB --> G
~~~

**Quarantine** và **published storage** đều nên private. Worker chỉ đọc quarantine với quyền tối thiểu; API/gateway chỉ cấp tải từ published storage sau khi kiểm tra `READY` và quyền người gọi. Copy object **không tự mở public-read**.

### 3.1. Trạng thái tài nguyên tệp

~~~mermaid
stateDiagram-v2
    [*] --> QUARANTINED: Upload + checksum thành công
    QUARANTINED --> SCANNING: Worker claim
    SCANNING --> VERIFIED: Scan đạt, version cố định
    SCANNING --> REJECTED: Phát hiện nguy cơ/loại cấm
    SCANNING --> SCAN_FAILED: Scanner lỗi/chưa có verdict
    SCAN_FAILED --> SCANNING: Retry có giới hạn
    VERIFIED --> PUBLISHING: Tạo bản phát hành riêng tư
    PUBLISHING --> READY: Object + metadata nhất quán
    PUBLISHING --> SCAN_FAILED: Lỗi publish cần phục hồi
~~~

`READY` là trạng thái **duy nhất** cho phép API cấp nội dung tải xuống thông thường. `VERIFIED` mới nói bộ kiểm tra đã cho verdict đạt; nó **chưa cho phép công bố**. `SCAN_FAILED` nghĩa là **chưa thể kết luận**, không đồng nghĩa tệp chứa mã độc. `REJECTED` là kết quả từ chính sách (mã độc, loại tệp không cho phép, cấu trúc nguy hiểm...) và phải có mã lý do được lọc thông tin khi trả cho client.

Những hệ thống yêu cầu quét lại sau khi cập nhật chữ ký antivirus có thể chuyển một bản `READY` sang trạng thái hạn chế truy cập hoặc quản lý **scan-policy-version** và hạn hiệu lực kết quả. Không coi một lần quét “sạch” là cam kết vĩnh viễn.

## 4. Hợp đồng REST: upload, theo dõi, tải về

Ví dụ dùng **multipart upload qua API** để minh họa một đường đi đầy đủ. Dữ liệu lớn hơn khả năng gateway tiếp nhận có thể chuyển sang **direct-to-object-storage** (Mục 5), nhưng các bất biến về checksum, scan và công bố vẫn giữ nguyên.

### 4.1. POST nhận file vào quarantine

~~~http
POST /v1/files HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Idempotency-Key: "upload-7d8eae6e-f15a-4f94-8687-d65748c9340c"
Content-Type: multipart/form-data; boundary=uploadBoundary

--uploadBoundary
Content-Disposition: form-data; name="purpose"

INVOICE_ATTACHMENT
--uploadBoundary
Content-Disposition: form-data; name="expectedSha256"

8f9c1b...64-hex-characters...d9
--uploadBoundary
Content-Disposition: form-data; name="file"; filename="invoice.pdf"
Content-Type: application/pdf

<bytes của PDF>
--uploadBoundary--
~~~

Chuỗi `expectedSha256` trong ví dụ **viết rút gọn để dễ đọc**, không phải giá trị hợp lệ; request thực phải chứa **đúng 64 ký tự hex**. Server kiểm tra `purpose`, giới hạn kích thước, checksum và quyền upload, sau đó lưu một object bất biến ở quarantine; chỉ khi metadata và yêu cầu quét được ghi bền vững, nó trả:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/files/file-102
Retry-After: 3
Cache-Control: no-store
Content-Type: application/json

{
  "id": "file-102",
  "status": "QUARANTINED",
  "sizeBytes": 428190,
  "sha256": "<64-hex-digest>",
  "scan": {"status": "PENDING"},
  "downloadAvailable": false
}
~~~

**202 nghĩa là đã tiếp nhận để xử lý bất đồng bộ**, không có nghĩa file đã an toàn. Nếu API chọn cách tạo một file resource ngay khi đã lưu quarantine, `201 Created` cũng có thể hợp lệ về mặt resource, nhưng cần công bố rõ `status=QUARANTINED`; bài chọn 202 để nhấn mạnh pipeline chưa kết thúc.

Client nên xem `Location` như URI để **GET trạng thái**, không tự suy ra URI object storage từ `file-102`.

### 4.2. GET trạng thái sau khi worker chạy

~~~http
GET /v1/files/file-102 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Cache-Control: no-store
Content-Type: application/json

{
  "id": "file-102",
  "status": "READY",
  "sizeBytes": 428190,
  "sha256": "<64-hex-digest>",
  "scan": {
    "status": "PASSED",
    "policyVersion": "policy-2026-11"
  },
  "downloadAvailable": true,
  "links": {
    "self": "/v1/files/file-102",
    "content": "/v1/files/file-102/content"
  }
}
~~~

Không đưa vào response thông tin nội bộ về chữ ký quét, đường lưu trữ thật, quyền truy cập bucket hoặc tên file riêng tư của tenant khác. Nếu job đang `SCAN_FAILED`, response nên mô tả **chưa có verdict** và trạng thái xử lý; không tự động trả `READY` sau khi hết timeout quét.

### 4.3. Chỉ cấp download khi READY và được phép

Client gọi:

~~~http
GET /v1/files/file-102/content HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 302 Found
Location: https://objects.example.net/<short-lived-signed-reference>
Cache-Control: no-store
~~~

Đây là **một phương án**: API xác thực và phân quyền, kiểm tra `status=READY`, rồi phát URL tải **thời hạn ngắn** tới object đã công bố. Có thể thay bằng stream `200 OK` từ backend hoặc content gateway. Nếu URL đã ký là *bearer capability*, ai có URL trong thời hạn hiệu lực có thể truy cập; phải cân nhắc TTL, log/referrer, phạm vi và thu hồi quyền.

Khi file chưa READY, API có thể trả `409 Conflict` với lỗi `FILE_NOT_READY`, không gửi object bytes hoặc signed URL. Khi file bị `REJECTED`, trả mã phù hợp với chính sách và **không cấp nội dung**; nếu principal không có quyền biết file tồn tại, trả **404 trung tính** trước khi tiết lộ trạng thái.

### 4.4. Mã trạng thái và lỗi rõ nghĩa

| Tình huống | HTTP status gợi ý | Hành vi |
|---|---|---|
| Upload đã lưu quarantine và queue quét | **202 Accepted** | `Location` để theo dõi |
| GET metadata của file được phép xem | **200 OK** | Trạng thái và metadata an toàn |
| Kích thước vượt giới hạn | **413 Content Too Large** | Từ chối; không để object tải được |
| Media type/format không được hỗ trợ | **415 Unsupported Media Type** hoặc **422** theo hợp đồng | Không xếp hàng quét như file hợp lệ |
| SHA-256 khai báo không khớp bytes | **422 Unprocessable Content** | Xóa/đánh dấu bản tạm không được công bố |
| Body sai cấu trúc, digest sai cú pháp | **400 Bad Request** | Problem Details rõ trường sai |
| Download khi `QUARANTINED/SCANNING` | **409 Conflict** | `FILE_NOT_READY`; không phát link |
| File bị chính sách quét loại | **200** metadata `REJECTED`; download bị chặn | Không đồng nhất malware với lỗi hệ thống |
| Thiếu credential hợp lệ | **401 Unauthorized** | Challenge phù hợp |
| Có tài khoản nhưng không đủ quyền | **403 Forbidden**, hoặc **404** khi cần che giấu | Không lộ object key/tenant |
| Scanner/storage tạm thời ngừng hoạt động | **503 Service Unavailable** cho thao tác không thể nhận/xử lý | Retry an toàn có giới hạn, không fail-open |
| Client gọi quá nhiều | **429 Too Many Requests** | `Retry-After` nếu thích hợp |

Ví dụ checksum sai:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.com/problems/checksum-mismatch",
  "title": "Unprocessable Content",
  "status": 422,
  "code": "CHECKSUM_MISMATCH",
  "detail": "Checksum của tệp nhận được khác giá trị đã khai báo."
}
~~~

Không trả 500 vì “quét phát hiện malware”: đó là **kết quả chính sách**. Ngược lại, scanner timeout là **lỗi vận hành** chưa có kết luận, không được coi mặc định là tệp sạch hoặc bị nhiễm.

## 5. Tệp rất lớn và direct-to-object-storage

Đưa mọi file vài GB qua một instance ứng dụng có thể tốn băng thông, disk tạm và thời gian giữ kết nối. Một kiến trúc khác:

1. **POST /v1/upload-sessions**: xác thực, quota và quyền; phát session ID cùng thông tin upload tạm thời vào **quarantine private**, giới hạn size/type/key/TTL.
2. Client upload từng phần bằng cơ chế của object storage, dùng retry có kiểm soát và checksum **cho từng phần hoặc toàn object** theo hợp đồng provider.
3. **POST /v1/upload-sessions/{id}/completions**: client báo hoàn tất; server **xác minh trên storage** kích thước, object version và digest toàn object từ bytes tin cậy hoặc checksum đã được provider xác thực. Không tin riêng lời khai của client.
4. Server khóa object/version bất biến, lưu metadata và outbox; worker quét trước khi công bố như pipeline ở trên.

Nếu dùng multipart upload của object storage, **ETag của object không nhất thiết là MD5 của toàn file** (nhất là upload nhiều part hoặc có mã hóa). Không dùng ETag của storage làm SHA-256 dự kiến trừ khi provider và chế độ upload thực sự định nghĩa như vậy. Thống nhất thuật toán và xác minh bằng cơ chế checksum được provider hỗ trợ hoặc stream đọc lại bytes khi cần.

Một lần client gửi “complete” lặp lại do timeout **không được tạo hai file resource**. Gắn session/operation với idempotency key, unique constraint và phiên bản object được xác minh; chỉ một lần chuyển trạng thái vào pipeline quét. Khi session hết hạn hoặc upload thất bại, dọn các phần dở dang bằng job riêng và không phát signed download URL.

## 6. Tác vụ quét: không được tin tên file, MIME hay một lần retry

### 6.1. Những bước nên thực hiện

Một pipeline tùy loại tệp có thể kết hợp:

- **Kiểm tra kích thước và quota:** trên bytes thực, không chỉ `Content-Length` do client khai; giới hạn theo principal/tenant và loại tài liệu.
- **Xác định định dạng từ nội dung:** kiểm tra magic bytes, cấu trúc parser an toàn, extension và MIME do client khai. `Content-Type: application/pdf` hoặc tên `invoice.pdf` không chứng minh nội dung là PDF.
- **Malware scanning:** engine chạy cô lập với quyền tối thiểu, chữ ký/cấu hình có version; có timeout, giới hạn CPU/RAM và trạng thái kết quả được lưu.
- **Đánh giá nội dung theo policy:** khi cần, kiểm tra nội dung nhạy cảm, file thực thi, macro, script nhúng hoặc dùng *content disarm and reconstruction* (CDR) cho định dạng thích hợp.
- **Quản lý archive:** giới hạn số mục, độ sâu lồng nhau, kích thước sau giải nén, tổng bytes, tỉ lệ nén để tránh zip bomb; xử lý path traversal và symlink bên trong archive.

Không nên tự chạy hoặc preview tệp chưa tin cậy trong process chính. Các parser/decoder cũng có thể có lỗ hổng; đặt worker trong sandbox, dùng user không đặc quyền, file system tạm an toàn và chặn kết nối mạng không cần thiết.

### 6.2. Bằng chứng verdict phải gắn với đúng object

Một bản ghi kết quả quét nên chứa ít nhất:

~~~json
{
  "fileId": "file-102",
  "objectVersion": "immutable-object-generation-7",
  "sha256": "<64-hex-digest>",
  "scannerPolicyVersion": "policy-2026-11",
  "scannerRunId": "run-8b1",
  "verdict": "PASSED",
  "checkedAt": "2026-11-18T12:00:00Z"
}
~~~

Verdict chỉ hợp lệ với **fileId + object version + digest** đã quét. Không cho ghi đè object quarantine: mỗi upload dùng key/version bất biến; nếu bytes thay đổi phải quét lại.

### 6.3. Queue giao trùng và worker chạy lại

Message broker/outbox có thể giao lại event sau timeout. Hai worker cũng có thể nhận cùng job khi lease hết hạn. Dùng **claim có điều kiện** tại database, lease và generation/fencing để một scanner run cũ không ghi verdict đè run mới:

~~~sql
-- Ví dụ PostgreSQL: chỉ claim job đang chờ quét.
UPDATE files
SET status = 'SCANNING',
    scan_generation = scan_generation + 1
WHERE id = :fileId
  AND status IN ('QUARANTINED', 'SCAN_FAILED')
RETURNING scan_generation, quarantine_key, object_version, sha256;
~~~

Sau khi quét:

~~~sql
UPDATE files
SET status = :newStatus,
    scan_policy_version = :policyVersion
WHERE id = :fileId
  AND status = 'SCANNING'
  AND scan_generation = :claimedGeneration
  AND object_version = :scannedObjectVersion;
~~~

Nếu UPDATE cuối trả **0 hàng**, kết quả quét đã cũ hoặc job đã chuyển trạng thái: không tự công bố. Việc claim nên có lease/heartbeat và quy trình phục hồi khi worker chết; không chuyển `SCANNING` thành `READY` chỉ vì đã quá thời gian chờ.

### 6.4. Fail closed nhưng vẫn có đường phục hồi

Scanner lỗi/timeout phải trả **SCAN_FAILED / NEEDS_REVIEW**, không phải `PASSED`. Retry giới hạn với backoff, theo dõi dead-letter và job kẹt; malware verdict thật dẫn tới `REJECTED`. **Fail closed** nghĩa là không phát nội dung khi chưa đạt kiểm tra, nhưng vẫn có thể lưu cách ly theo chính sách. Không cho sửa tay `READY` mà thiếu verdict/audit hợp lệ.

## 7. Công bố tệp: đóng cửa sổ race giữa scan và download

Không thể atomically commit **copy object storage** và **transaction database** bằng một transaction thông thường. Vì vậy cần chọn **điểm mở quyền tải** thật rõ.

### 7.1. Quy trình an toàn

1. Worker quét **phiên bản object cố định** từ quarantine, ghi verdict `PASSED` gắn với SHA-256 và scan-generation.
2. Chuyển metadata `VERIFIED → PUBLISHING` bằng CAS, kiểm tra verdict vẫn phù hợp phiên bản hiện tại.
3. Copy/transform object sang **vùng published vẫn private** bằng key mới, bất biến; nếu transform làm thay đổi bytes, tính **digest đầu ra riêng** và quét lại nếu policy yêu cầu.
4. Kiểm tra object đã tồn tại bền vững, kích thước và digest của **bytes sẽ phục vụ cho download**.
5. Trong transaction, cập nhật metadata `READY` cùng `publishedKey/version/digest` bằng điều kiện `status=PUBLISHING`, `scanGeneration` và `objectVersion` còn khớp.
6. Download endpoint chỉ cấp nội dung khi `READY` và caller có quyền; mọi trạng thái khác bị chặn.

~~~mermaid
sequenceDiagram
    participant W as Publish worker
    participant S as Private storage
    participant DB as Metadata DB
    participant C as Client
    W->>DB: CAS VERIFIED -> PUBLISHING
    W->>S: Copy/verify đúng object version
    S-->>W: Published key + digest
    W->>DB: CAS PUBLISHING -> READY, save published key
    C->>DB: GET /files/id/content, auth + READY?
    DB-->>C: READY + được phép
    C->>S: Tải bằng quyền/URL có hạn
~~~

**Điểm công bố là commit READY**, không phải lúc copy object. Crash trước commit tạo orphan private để reconciler dọn/hoàn tất; object mất sau commit cần cảnh báo và khôi phục, không cấp link tải hỏng.

### 7.2. TOCTOU: quét file A, lại phục vụ file B

Sai:

~~~text
scan("quarantine/user-a/file.pdf") -> PASSED
client ghi đè cùng key bằng bytes khác
publish("quarantine/user-a/file.pdf") -> READY
~~~

Đúng: gắn scan verdict với **object version hoặc immutable key**, có checksum xác nhận, copy đúng version đó và cấm thay thế. Một `ETag` do object storage cấp có thể được dùng để kiểm tra điều kiện khi provider hỗ trợ, nhưng **không thay thế checksum SHA-256 đã được định nghĩa**. Khi storage hỗ trợ version ID, ưu tiên khóa theo version rõ ràng.

### 7.3. Giới hạn của signed download URL

URL tải đã ký có thể **còn hiệu lực đến hết TTL** sau khi DB đánh dấu `REVOKED`. Khi cần thu hồi tức thì, dùng gateway kiểm tra mỗi lần tải hoặc cơ chế thu hồi của provider. Khi phục vụ file, đặt `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff` và Content-Type đúng; đây là lớp bổ sung, không thay scan.

## 8. Java/Spring Boot: nhận file, tính checksum và xếp hàng quét

Ví dụ **Java 17+, Spring Boot 3/Spring MVC** dùng `MultipartFile`, lưu tạm riêng tư rồi đưa vào quarantine. Đoạn mã tập trung vào logic cốt lõi, chưa phải ứng dụng chạy độc lập: `PrivateObjectStorage`, `FileMetadataService`, `ActorFactory`, validator/exception và lớp DTO cần được hiện thực.

~~~java
record UploadAccepted(String id, String status) {}

@RestController
@RequestMapping("/v1/files")
class FileUploadController {
    private final FileIngestionService ingestion;
    private final ActorFactory actors;

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<UploadAccepted> upload(
            @RequestPart("file") MultipartFile file,
            @RequestPart("expectedSha256") String expectedSha256,
            @RequestPart("purpose") String purpose,
            @RequestHeader("Idempotency-Key") String key,
            @AuthenticationPrincipal Jwt jwt) throws IOException {

        Actor actor = actors.fromVerifiedJwt(jwt);
        UploadAccepted result = ingestion.accept(
            actor, file, expectedSha256, purpose, key);
        return ResponseEntity.accepted()
            .location(URI.create("/v1/files/" + result.id()))
            .cacheControl(CacheControl.noStore())
            .body(result);
    }
}
~~~

### 8.1. Stream bytes với giới hạn cứng

~~~java
@Service
class FileIngestionService {
    private static final long MAX_BYTES = 50L * 1024 * 1024;
    private final PrivateObjectStorage storage;
    private final FileMetadataService metadata;
    private final FilePolicy policy;

    UploadAccepted accept(Actor actor, MultipartFile part,
            String expectedHex, String purpose, String key)
            throws IOException {
        policy.requireUploadPermissionAndQuota(actor, purpose);
        if (expectedHex == null
                || !expectedHex.matches("[0-9a-f]{64}")) {
            throw new InvalidChecksumException(); // 400
        }
        if (part.isEmpty() || part.getSize() > MAX_BYTES) {
            throw new InvalidUploadSizeException(); // 413/422
        }

        Path temp = Files.createTempFile("incoming-", ".bin");
        try {
            MessageDigest sha = MessageDigest.getInstance("SHA-256");
            long actualSize = 0;
            byte[] buffer = new byte[64 * 1024];
            try (InputStream in = part.getInputStream();
                 OutputStream out = Files.newOutputStream(temp)) {
                int n;
                while ((n = in.read(buffer)) != -1) {
                    actualSize += n;
                    if (actualSize > MAX_BYTES) {
                        throw new UploadTooLargeException(); // 413
                    }
                    sha.update(buffer, 0, n);
                    out.write(buffer, 0, n);
                }
            }
            if (actualSize == 0) {
                throw new InvalidUploadSizeException();
            }
            byte[] expected = HexFormat.of().parseHex(expectedHex);
            byte[] actual = sha.digest();
            if (!MessageDigest.isEqual(expected, actual)) {
                throw new ChecksumMismatchException(); // 422
            }

            policy.validateContentTypeFromBytes(temp, purpose);
            String objectKey = "quarantine/" + UUID.randomUUID();
            storage.putPrivateImmutable(objectKey, temp);
            // Transaction DB riêng: file metadata + outbox scan event.
            return metadata.createQuarantinedAndEnqueue(
                actor, purpose, key, objectKey, actualSize,
                HexFormat.of().formatHex(actual));
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
~~~

**Khi triển khai:** xử lý checked exception của `MessageDigest.getInstance`; giới hạn size tại proxy/servlet, disk quota và số upload đồng thời. `MultipartFile` có thể đã spool lên memory/disk nên đây **chưa phải streaming end-to-end**. Temp phải private/no-execute, có cleanup; không dùng filename client làm đường dẫn. `putPrivateImmutable` chỉ ghi quarantine; DB transaction ghi metadata+outbox nguyên tử, ledger chống replay, reconciler dọn orphan private object khi commit lỗi.

### 8.2. Worker quét có điều kiện

~~~java
@Component
class ScanWorker {
    private final FileWorkflow workflow;
    private final MalwareScanner scanner;

    void onScanRequested(UUID fileId) {
        Optional<ScanClaim> claim = workflow.tryClaim(fileId);
        if (claim.isEmpty()) return;  // Event lặp hoặc job đã xử lý.

        ScanClaim c = claim.get();
        ScanVerdict verdict;
        try (InputStream in = workflow.openExactQuarantineVersion(c)) {
            verdict = scanner.scanWithLimits(in, c.policyVersion());
        } catch (Exception ex) {
            workflow.markScanFailedIfCurrent(c); // Không READY.
            return;
        }

        if (verdict == ScanVerdict.PASSED) {
            workflow.markVerifiedIfCurrent(c);
            workflow.publishPrivateThenMarkReady(c);
        } else if (verdict == ScanVerdict.BLOCKED) {
            workflow.markRejectedIfCurrent(c);
        } else {
            workflow.markScanFailedIfCurrent(c);
        }
    }
}
~~~

`FileWorkflow` phải kiểm tra object version/digest, lease-generation và CAS **ở mọi bước chuyển trạng thái**; `publishPrivateThenMarkReady` thực hiện quy trình Mục 7 chứ không đơn giản set `READY`. Không dùng `@Async` trong memory làm nguồn duy nhất cho tác vụ: khi pod restart có thể mất job. Outbox/queue bền vững, retry giới hạn và reconciliation là thành phần cần thiết.

## 9. Bảo mật truy cập và vận hành

**Quyền upload, đọc metadata, xem kết quả quét và tải nội dung là các quyền khác nhau.** Kiểm tra tenant/owner/ACL trên mọi request, kể cả khi client đã biết `fileId`, nhận `Location` hay có idempotency key. Áp quota, rate limit và chặn dò ID. Worker dùng credential riêng chỉ đọc quarantine và ghi verdict; không cần quyền public-read hoặc quyền xem dữ liệu tenant ngoài phạm vi xử lý.

Các response trạng thái có thể bị cache sai: với file riêng tư dùng `Cache-Control: no-store` hoặc thiết kế private cache rõ ràng. Không log toàn bộ file, access token, signed URL hoặc chi tiết scanner tiết lộ đường lưu trữ. Theo dõi tỷ lệ checksum mismatch, thời gian chờ quét, số job `SCAN_FAILED`, kích thước quarantine, object mồ côi và số lần từ chối tải khi chưa READY. Tạo alert cho backlog và cảnh báo phiên bản chữ ký scanner quá cũ.

## 10. Kiểm thử theo trạng thái và lỗi

| Test | Tình huống | Kỳ vọng |
|---|---|---|
| F01 | File và SHA-256 đúng | `202`, metadata `QUARANTINED`, chưa có download |
| F02 | Thay một byte nhưng giữ checksum cũ | `422 CHECKSUM_MISMATCH`, không enqueue/publish |
| F03 | File vượt max thực tế dù header khai thấp | `413`, không lưu file phát hành |
| F04 | Đổi tên thành .pdf nhưng bytes là executable | Bị từ chối theo chính sách loại tệp |
| F05 | Scanner `PASSED` trên đúng immutable version | `VERIFIED → PUBLISHING → READY` |
| F06 | Scanner `BLOCKED` hoặc hết hạn | `REJECTED` hoặc `SCAN_FAILED`, không cấp link |
| F07 | Hai worker quét cùng file/queue giao lặp | Stale generation không ghi đè verdict |
| F08 | Worker crash sau copy, trước READY commit | Object private mồ côi; download vẫn bị chặn |
| F09 | Object bị thay sau quét | Không công bố vì version/digest không khớp |
| F10 | Tenant khác GET file hoặc content URI | 404 trung tính hoặc chính sách 403; không lộ key |
| F11 | Retry upload/complete với cùng key | Một file resource và một pipeline logic |
| F12 | Archive giải nén phình quá quota | Scanner dừng có giới hạn; fail closed |

### MockMvc: checksum sai phải dừng trước khi xếp hàng

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class FileUploadContractTest {
    @Autowired MockMvc mvc;

    @Test
    void wrongChecksumNeverAcceptsFile() throws Exception {
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
        MockMultipartFile file = new MockMultipartFile(
            "file", "invoice.pdf", "application/pdf", bytes);
        MockMultipartFile hash = new MockMultipartFile(
            "expectedSha256", "", "text/plain",
            "0".repeat(64).getBytes(StandardCharsets.UTF_8));
        MockMultipartFile purpose = new MockMultipartFile(
            "purpose", "", "text/plain",
            "INVOICE_ATTACHMENT".getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/v1/files")
                .file(file).file(hash).file(purpose)
                .header("Idempotency-Key", "\"test-upload-1\"")
                .with(jwt()))
            .andExpect(status().isUnprocessableEntity());
        // Assert qua fake storage/repository: không file READY,
        // không outbox scan và không signed URL.
    }
}
~~~

Test minh họa cần fixture actor có quyền upload và Problem Details mapper. `jwt()` của Spring Security Test **không kiểm tra chữ ký token thực**. Ngoài MockMvc, phải test tích hợp trên database/object storage giả lập có version, queue giao lặp và scanner fake điều khiển `PASSED/BLOCKED/TIMEOUT`. Dùng barrier để tái hiện race; không chỉ assert HTTP status mà còn assert **không có bytes/signed URL nào được phát trước READY**.

## 11. Bài tập và checklist triển khai

**Bài tập:** một file PDF được upload, client gửi SHA-256 đúng, scanner quét `PASSED`. Trong lúc worker copy sang vùng phát hành, nó crash. Đồng thời, một request khác ghi đè object quarantine cùng key; người dùng gọi download. Bạn sẽ xử lý thế nào?

**Đáp án tham khảo:** không cho ghi đè key/version quarantine; verdict gắn với phiên bản bất biến. Bản copy sau crash vẫn private, metadata chưa `READY` nên download trả `409 FILE_NOT_READY`. Reconciler dọn hoặc hoàn tất copy sau khi xác minh đúng digest và generation, rồi commit `READY` bằng CAS. Nếu source version đã thay đổi, bắt buộc quét lại hoặc từ chối công bố; checksum đúng **không thay** verdict scan.

**Checklist:** xác định bytes được hash và thuật toán; giới hạn kích thước thực và quota; không tin tên/MIME do client gửi; lưu quarantine private; metadata/outbox bền vững; quét trong sandbox có giới hạn; verdict gắn version+digest; fail closed khi scanner lỗi; publish private trước rồi mới commit `READY`; download kiểm tra quyền+trạng thái; retry/idempotency và orphan cleanup; kiểm thử race, timeout, cross-tenant và quyền thu hồi.

**Đọc thêm:** [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110); [RFC 9530 — Digest Fields](https://www.rfc-editor.org/rfc/rfc9530); [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457); [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

**Kết luận:** checksum xác nhận **bytes**, scanner cung cấp **verdict theo chính sách**, còn trạng thái `READY` đánh dấu **quyền công bố**. Chỉ khi ba lớp này gắn với **đúng object bất biến** và được bảo vệ bằng transaction/CAS, API mới có thể cho phép tải file lớn an toàn trước retry, lỗi worker và thay đổi đồng thời.
