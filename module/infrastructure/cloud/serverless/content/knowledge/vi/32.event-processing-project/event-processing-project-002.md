# Xây dựng bước tiếp nhận tệp và phát sự kiện

Bước tiếp nhận tệp là ranh giới giữa dữ liệu do client gửi lên và dữ liệu mà hệ thống có thể xử lý. Một ứng dụng web hoặc mobile có thể gửi ảnh, video, PDF, bảng tính hoặc tệp đính kèm. Backend cần xác định ai được upload, upload vào đâu, kích thước và định dạng nào được phép, tệp đã hoàn tất hay chưa, object nào là phiên bản cần xử lý và sự kiện nào được phát cho các worker tiếp theo.

Trong kiến trúc serverless, API function thường tạo upload session và cấp quyền upload có thời hạn. Client truyền nội dung trực tiếp vào object storage để tránh giữ request dài hoặc chuyển binary qua API Gateway. Storage phát notification khi object được tạo; một queue tiếp nhận notification và kích hoạt Java function. Function xác minh object với upload session, ghi nhận trạng thái và phát event nghiệp vụ ổn định như **file.received**. Worker xử lý ảnh, video hoặc tài liệu có thể subscribe event này ở bước sau.

Điểm quan trọng là notification từ storage chỉ báo có thao tác trên object. Nó chưa chứng minh tệp thuộc upload session hợp lệ, đúng tenant, đúng kích thước, đúng checksum hoặc an toàn. Bước intake phải xác minh các điều kiện đó trước khi công bố event cho downstream.

Trong module **CLOUD_SERVERLESS**, người học phát triển Java function kích hoạt bởi HTTP, message hoặc event, đồng thời xử lý trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí. Bài này hướng dẫn xây dựng bước tiếp nhận tệp và phát sự kiện với upload session, object storage, queue, Java function và transactional outbox.

## 1. Mục tiêu và phạm vi của bước intake

Bước intake chịu trách nhiệm chuyển một upload từ trạng thái do client khởi tạo sang một tham chiếu object đã được backend xác minh và có thể xử lý.

Các mục tiêu:

- Xác thực principal và kiểm tra quyền upload.
- Áp dụng quota theo user, tenant và loại tệp.
- Tạo object key không đoán được và gắn với upload session.
- Cấp quyền upload ngắn hạn, giới hạn đúng object và method.
- Nhận biết upload đã hoàn tất qua storage event hoặc API completion.
- Xác minh object thực tế bằng metadata lấy từ storage.
- Phát hiện upload trùng, object bị ghi đè hoặc event đến muộn.
- Ghi trạng thái bền vững và phát event có schema ổn định.
- Bảo đảm retry không tạo nhiều upload record hoặc business event.
- Cách ly tệp chưa xác minh; không công bố download URL quá sớm.

Bài này dừng ở việc phát event **file.received** sau khi object đã qua kiểm tra intake cơ bản. Các bước malware scanning chuyên sâu, OCR, thumbnail, transcoding và xử lý nội dung được xây dựng bởi consumer tiếp theo. Dù vậy, object vẫn nên nằm trong vùng quarantine hoặc private storage cho đến khi pipeline an toàn hoàn tất.

## 2. Kiến trúc tổng thể

~~~mermaid
flowchart TD
    C[Web / Mobile client] -->|POST create upload| API[API Gateway]
    API --> F1[Java Upload API Function]
    F1 --> IDP[Identity / Authorization]
    F1 --> DB[(Upload session database)]
    F1 -->|Presigned upload URL| C
    C -->|Direct PUT / multipart| S[(Private quarantine object storage)]
    S -->|Object created notification| Q[Ingestion queue]
    Q --> F2[Java Intake Function]
    F2 -->|HEAD / GET exact version| S
    F2 --> DB
    F2 --> OB[(Transactional outbox)]
    OB --> P[Outbox publisher]
    P --> BUS[Event bus / downstream queue]
    BUS --> W[Processing workers]
    F2 --> DLQ[Dead-letter queue]
    Q -. failure after retries .-> DLQ
    F1 --> OBS[Logs / metrics / traces]
    F2 --> OBS
    P --> OBS
~~~

Có ba luồng chính:

1. **Control flow:** client gọi API để tạo upload session, backend xác thực và cấp quyền upload.
2. **Data flow:** client upload trực tiếp bytes vào private object storage.
3. **Event flow:** storage notification được đưa vào queue; intake function xác minh object rồi phát event nghiệp vụ.

Queue giúp hấp thụ burst và tách tốc độ upload khỏi tốc độ xử lý intake. Transactional outbox giúp đồng bộ việc cập nhật database với ý định phát event. Downstream worker không cần đọc notification riêng của từng provider; chúng nhận một event contract thống nhất.

Các dịch vụ trong sơ đồ có thể là managed service tương đương của cloud provider. Cấu hình notification, queue, retry, versioning và object lock khác nhau theo nền tảng; cần kiểm tra semantics của sản phẩm thực tế.

## 3. Các thành phần và ranh giới trách nhiệm

| Thành phần | Trách nhiệm | Không nên làm |
|---|---|---|
| Web/mobile client | Xin upload session, truyền bytes, theo dõi trạng thái | Tự quyết định object key hoặc trạng thái accepted |
| API Gateway | HTTPS, route, auth integration, throttling, request limit | Giữ binary upload lớn qua function nếu có direct upload |
| Upload API function | Kiểm tra user/quota, tạo session, cấp quyền | Tin MIME type hoặc file size do client khai báo |
| Upload session database | Lưu owner, tenant, key, expiry và trạng thái | Lưu presigned URL như credential lâu dài |
| Object storage | Lưu bytes và phát notification | Public object trước khi intake hoàn tất |
| Ingestion queue | Buffer notification, retry và DLQ | Giả định message chỉ đến một lần |
| Intake function | Xác minh object, claim event, cập nhật trạng thái | Tin toàn bộ metadata trong notification |
| Outbox publisher | Phát canonical event và retry | Đánh dấu sent trước khi publish thành công |
| Event bus/queue downstream | Phân phối event cho worker | Là nguồn dữ liệu authoritative về upload session |
| Observability | Theo dõi toàn bộ flow và audit | Log URL ký trước hoặc secret |

Tách upload API và intake consumer vì chúng có trigger, timeout và scaling profile khác nhau. API cần latency thấp; intake consumer có thể xử lý theo queue concurrency và cần quyền đọc object. Cả hai dùng chung domain service hoặc repository contract nếu phù hợp.

## 4. Trạng thái của một upload session

Không dùng một boolean uploaded để mô tả toàn bộ lifecycle. Một state machine rõ ràng giúp xác định request nào hợp lệ và event nào cần phát.

| Trạng thái | Ý nghĩa | Chuyển trạng thái hợp lệ |
|---|---|---|
| CREATED | Session đã tạo và cấp quyền upload, chưa xác nhận object | UPLOADING, OBJECT_REPORTED, EXPIRED, CANCELLED |
| UPLOADING | Client đang gửi bytes | OBJECT_REPORTED, EXPIRED, CANCELLED |
| OBJECT_REPORTED | Storage notification hoặc completion đã đến | VERIFYING |
| VERIFYING | Backend đang kiểm tra object/version | ACCEPTED, REJECTED, RETRY_PENDING |
| RETRY_PENDING | Lỗi tạm thời, chờ xử lý lại | VERIFYING, FAILED |
| ACCEPTED | Object được xác minh và event đã được tạo trong outbox | Terminal cho intake |
| REJECTED | Object vi phạm policy | Terminal cho intake |
| EXPIRED | Session hết hạn trước khi hoàn tất | Terminal |
| CANCELLED | Owner hoặc hệ thống hủy session | Terminal |
| FAILED | Lỗi không thể phục hồi sau retry | Terminal, cần điều tra |

Với single PUT, hệ thống có thể không nhận được tín hiệu bắt đầu upload; session có thể đi trực tiếp từ CREATED sang OBJECT_REPORTED khi storage event đến. Trạng thái UPLOADING hữu ích khi backend quản lý multipart initiation, nhận progress/completion hint hoặc có tín hiệu bắt đầu riêng. Không bắt buộc tạo một request chỉ để đổi trạng thái nếu nó không mang thêm bảo đảm.

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> UPLOADING
    CREATED --> OBJECT_REPORTED
    UPLOADING --> OBJECT_REPORTED
    OBJECT_REPORTED --> VERIFYING
    VERIFYING --> ACCEPTED
    VERIFYING --> REJECTED
    VERIFYING --> RETRY_PENDING
    RETRY_PENDING --> VERIFYING
    CREATED --> EXPIRED
    UPLOADING --> EXPIRED
    CREATED --> CANCELLED
    UPLOADING --> CANCELLED
    RETRY_PENDING --> FAILED
~~~

Trạng thái ACCEPTED nên có nghĩa cụ thể: object version đã được xác minh, metadata cần thiết đã được lưu và canonical event đã được ghi bền vững vào outbox trong cùng transaction. Publisher có thể chưa gửi event ra bus ngay lúc đó; outbox giữ trách nhiệm retry cho đến khi publish được xác nhận.

Nếu muốn phân biệt đã được xác minh với đã publish, thêm trạng thái riêng như EVENT_PENDING/EVENT_PUBLISHED hoặc giữ trạng thái upload ACCEPTED và theo dõi outbox delivery riêng. Tránh làm trạng thái upload phụ thuộc vào tình trạng tạm thời của event bus.

## 5. Thiết kế upload session

Upload session là bản ghi backend đại diện cho quyền upload một object cụ thể. Session nên có các field:

| Field | Mục đích |
|---|---|
| upload_id | ID duy nhất do server tạo |
| tenant_id | Tenant sở hữu upload |
| owner_id | Principal tạo session |
| object_bucket/container | Vùng lưu trữ đích |
| object_key | Key ngẫu nhiên do server tạo |
| expected_size | Kích thước dự kiến hoặc giới hạn tối đa |
| allowed_media_types | Loại nội dung cho phép |
| expected_checksum | Checksum client dự kiến nếu dùng |
| status | Trạng thái lifecycle |
| expires_at | Thời điểm session hết hạn |
| object_version_id | Version cụ thể đã xác minh |
| actual_size | Kích thước storage trả về |
| actual_checksum | Checksum được storage xác nhận |
| detected_media_type | Loại nội dung phát hiện từ bytes |
| idempotency_key | Chống tạo session trùng |
| correlation_id | Liên kết request, event và trace |
| created_at / updated_at | Audit lifecycle |

Không nhất thiết lưu mọi field trong một bảng. Có thể tách session, object metadata và outbox theo access pattern. Nhưng cần có unique constraint để một upload session không bị tạo hai lần khi client retry request.

### Object key

Server tạo key với cấu trúc có namespace, ví dụ:

~~~text
quarantine/{tenant-id}/{upload-id}/{random-object-id}
~~~

Không dùng tên file gốc làm key. Filename có thể chứa ký tự đặc biệt, đường dẫn giả, thông tin cá nhân hoặc tên trùng. Lưu original filename đã chuẩn hóa như metadata hiển thị nếu nghiệp vụ cần; key phải do server kiểm soát.

Dùng key ngẫu nhiên khó đoán và kiểm tra owner bằng session database. Không xem tính khó đoán của key là authorization; IAM và bucket/container policy vẫn phải giới hạn truy cập.

## 6. Tạo upload session qua HTTP API

Client gọi API để tạo session. Backend cần:

1. Xác minh access token/session.
2. Xác định tenant từ identity đã xác thực.
3. Kiểm tra user có quyền upload vào resource đích.
4. Kiểm tra quota, số upload đang mở và dung lượng còn lại.
5. Validate file size dự kiến và content type khai báo.
6. Tạo upload ID và object key ngẫu nhiên.
7. Ghi session ở trạng thái CREATED.
8. Tạo quyền upload ngắn hạn đúng object/method.
9. Trả upload ID, URL và expiry cho client.

Ví dụ request:

~~~http
POST /v1/uploads
Authorization: Bearer <access-token>
Idempotency-Key: 0d6f4a7c-...
Content-Type: application/json

{
  "fileName": "inspection-photo.jpg",
  "contentType": "image/jpeg",
  "sizeBytes": 2457600,
  "checksumSha256": "base64-checksum"
}
~~~

Ví dụ response:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Cache-Control: no-store

{
  "uploadId": "upl-9001",
  "uploadUrl": "https://storage.example/signed-request",
  "method": "PUT",
  "expiresAt": "2026-11-17T10:25:30Z",
  "requiredHeaders": {
    "Content-Type": "image/jpeg"
  },
  "status": "CREATED"
}
~~~

URL trong ví dụ chỉ minh họa cấu trúc. URL ký trước là bearer capability; người có URL và header phù hợp có thể sử dụng quyền đó trong thời gian hiệu lực. Không ghi URL thật vào log, analytics hoặc error tracker. Response cần Cache-Control: no-store nếu chứa capability.

### Idempotency khi tạo session

Client mobile có thể timeout sau khi backend đã tạo session nhưng chưa nhận response. Khi retry với cùng Idempotency-Key, backend nên trả lại cùng uploadId/session và capability mới nếu policy cho phép, hoặc trả trạng thái session hiện tại. Không tạo nhiều session và chiếm quota cho cùng một thao tác người dùng.

Ràng buộc key theo principal, tenant và operation. Nếu cùng key được gửi với request body khác, trả conflict thay vì âm thầm dùng session cũ.

## 7. Cấp presigned URL hoặc upload token an toàn

Presigned URL thường cấp quyền thực hiện một thao tác storage trong khoảng thời gian giới hạn. Cần giới hạn:

- Bucket/container và object key cụ thể.
- HTTP method hoặc operation cụ thể.
- Thời gian hết hạn ngắn theo upload UX.
- Content-Type hoặc checksum header nếu provider hỗ trợ ràng buộc chữ ký.
- Kích thước tối đa nếu cơ chế upload policy hỗ trợ.
- Không cho phép list bucket, read object hoặc delete object.
- Không cấp quyền ghi vào vùng processed/public.
- Không cho phép client chọn server-side encryption key tùy ý.

Một số provider hỗ trợ presigned POST policy với điều kiện content-length-range; presigned PUT có semantics khác. Đừng giả định mọi loại signed URL đều ràng buộc được size theo cùng cách. Backend vẫn phải kiểm tra actual object size sau upload.

Nếu URL hết hạn trong lúc upload, client cần xin URL mới cho cùng session theo policy. URL mới không nên tạo object key mới hoặc làm thay đổi owner. Nếu session đã hết hạn hoặc bị cancel, từ chối cấp lại.

## 8. Upload trực tiếp và CORS

Với browser, storage bucket/container cần CORS policy chỉ cho phép origin ứng dụng, method và header cần thiết. CORS không bảo vệ storage khỏi mobile client hoặc script ngoài browser; quyền truy cập vẫn do chữ ký/IAM quyết định.

Cấu hình CORS nên tối thiểu:

- Allow origin cụ thể cho production/staging.
- Chỉ cho phép PUT/POST/HEAD cần thiết.
- Chỉ cho phép các request header cần thiết như Content-Type/checksum.
- Expose response header mà client thực sự cần, ví dụ ETag nếu flow sử dụng.
- Đặt max-age hợp lý cho preflight.
- Không wildcard origin cùng credential khi không phù hợp.

Không cho phép tất cả origin chỉ để tránh lỗi preflight. Tách CORS config theo environment và kiểm tra bằng browser thật.

## 9. Upload đơn giản, multipart và resumable

Một PUT đơn giản phù hợp với file nhỏ và mạng ổn định. Với video hoặc file lớn, multipart/resumable upload giúp chia dữ liệu thành nhiều part và tiếp tục sau khi mạng mobile bị ngắt.

| Tiêu chí | Single PUT | Multipart/resumable |
|---|---|---|
| Số lần request | Ít | Nhiều part và bước complete |
| Retry | Thường upload lại toàn bộ | Retry từng part |
| Client complexity | Thấp | Cao hơn |
| File lớn | Có giới hạn theo provider/API | Phù hợp hơn |
| Trạng thái | Một object completion | Upload ID, part list và completion |
| Cleanup | Xóa object chưa hoàn tất | Abort multipart và dọn part mồ côi |

Backend cần lưu multipart upload ID, part constraints, expiry và trạng thái. Client chỉ được upload part đã được cấp quyền. Complete multipart phải được xác thực và idempotent. Cấu hình lifecycle để abort multipart upload không hoàn tất sau thời hạn phù hợp.

Không coi ETag của multipart là MD5 của toàn bộ file. Dùng checksum API và semantics được provider tài liệu hóa.

## 10. Client báo hoàn tất và storage notification

Có hai tín hiệu thường dùng:

- Client gọi POST /v1/uploads/{id}/complete sau khi upload.
- Object storage phát notification khi object được tạo hoặc multipart upload hoàn tất.

Callback từ client hữu ích để cải thiện UX, nhưng không nên là nguồn duy nhất xác nhận object tồn tại. Client có thể gian lận, app có thể crash trước callback hoặc callback đến trước khi storage metadata nhất quán theo semantics provider.

Storage event là tín hiệu độc lập từ data plane. Tuy nhiên, event có thể duplicate, đến trễ hoặc sai thứ tự. Vì vậy, cả hai tín hiệu nên đưa session vào cùng một quy trình xác minh idempotent. Một tín hiệu chỉ đánh thức intake; backend vẫn đọc metadata object từ storage.

### Không xử lý object khi upload chưa hoàn tất

Với multipart, notification cần tương ứng với object hoàn chỉnh, không phải từng part. Kiểm tra event type và trạng thái upload. Với object storage có eventual consistency hoặc notification semantics riêng, dùng API HEAD/GET theo version để xác nhận object đã đọc được trước khi chấp nhận.

## 11. Cấu hình storage notification và ingestion queue

Đường đi thường gặp:

1. Bucket/container chỉ chứa object quarantine phát sự kiện ObjectCreated.
2. Rule chỉ nhận đúng prefix và event type cần thiết.
3. Notification được gửi đến queue hoặc event bus.
4. Queue kích hoạt Java intake function.
5. Queue có retry visibility/lease và DLQ.
6. Consumer xử lý batch, trả partial failure nếu nền tảng hỗ trợ.

Dùng prefix/suffix filter để tránh event loop. Nếu output của worker cũng nằm trong cùng bucket và cùng prefix, nó có thể kích hoạt intake lần nữa. Tách quarantine prefix/bucket với processed prefix/bucket.

### Vì sao nên có queue?

Queue hấp thụ burst upload, tách availability của storage khỏi consumer và cho phép điều chỉnh concurrency. Nếu function bị throttling hoặc database chậm, message có thể chờ trong queue thay vì mất ngay. Queue cũng hỗ trợ retry và DLQ để điều tra poison event.

Chọn queue type theo ordering và throughput. Standard queue thường có thể giao duplicate và không bảo đảm thứ tự tuyệt đối. FIFO/ordered queue có semantics khác và giới hạn throughput riêng. Intake nên idempotent dù queue có hỗ trợ ordering hay không.

## 12. Chuẩn hóa notification thành object reference

Notification provider có envelope khác nhau. Intake adapter nên parse event gốc thành một cấu trúc nội bộ:

~~~java
public record StorageObjectCreated(
        String providerEventId,
        String bucket,
        String key,
        String versionId,
        String eventType,
        Instant occurredAt,
        String sequencer,
        String correlationHint) {
}
~~~

Adapter chỉ làm nhiệm vụ parse và normalize. Nó không quyết định object có hợp lệ hay user có quyền nhận object đó. Những quyết định đó cần session database và metadata đọc trực tiếp từ storage.

Giữ lại provider event ID, request ID hoặc sequencer khi có để điều tra duplicate và thứ tự. Không giả định mọi provider đều có versionId hoặc sequencer. Nếu thiếu field, dùng chiến lược deduplication dựa trên upload ID, key, event type và object metadata phù hợp.

## 13. Không tin notification payload

Storage notification có thể chứa bucket, key, version, size, ETag và event time. Các field này hữu ích để định tuyến nhưng không nên được xem là bằng chứng đầy đủ.

Intake function cần:

1. Kiểm tra event source và event type nằm trong allowlist.
2. Decode object key đúng encoding của provider.
3. Xác định upload ID từ key hoặc metadata server-side.
4. Tải upload session theo upload ID.
5. Kiểm tra bucket/key khớp chính xác session.
6. Kiểm tra tenant/owner và trạng thái session.
7. Đọc HEAD metadata của đúng object version nếu có.
8. Kiểm tra size, checksum, encryption và metadata cần thiết.
9. Kiểm tra session chưa hết hạn/cancelled theo policy.
10. Chỉ sau đó mới chấp nhận object.

Không cho client gửi một bucket/key tùy ý rồi yêu cầu function HEAD hoặc GET. Điều này có thể tạo confused deputy hoặc truy cập object ngoài phạm vi tenant. Object reference phải khớp session do server tạo.

## 14. Xác minh object metadata

Dùng HEAD hoặc API tương đương để lấy metadata từ storage. Xác minh:

- Bucket/container đúng.
- Key đúng với session.
- Version ID đúng với event hoặc session.
- Object tồn tại và đã hoàn tất.
- Actual size không vượt quota hoặc giới hạn.
- Checksum nếu provider lưu checksum đáng tin cậy.
- Encryption setting phù hợp.
- Metadata upload ID/session marker đúng nếu đã gắn.
- Content type khai báo chỉ là hint; cần sniff bytes ở bước validation.
- Object không bị xóa hoặc bị thay thế giữa lúc event được phát và lúc consumer đọc.

### ETag và checksum

ETag là entity tag của storage, không phải lúc nào cũng là checksum cryptographic của bytes. Multipart upload, server-side encryption và implementation khác có thể làm ETag không tương đương MD5 toàn object.

Ưu tiên checksum algorithm được storage hỗ trợ và được truyền/kiểm tra rõ. Nếu cần xác minh nội dung toàn bộ, worker có thể stream object và tính SHA-256. Cân nhắc chi phí đọc lại toàn file; không tải toàn bộ file vào memory của intake function.

## 15. Object versioning và ghi đè

Presigned PUT có thể được dùng nhiều lần cho đến khi hết hạn. Nếu cùng key bị ghi lại, object hiện tại có thể khác object đã tạo event đầu tiên. Nếu consumer chỉ HEAD key hiện tại, event cũ có thể vô tình xử lý bytes mới.

Các biện pháp:

- Bật object versioning nếu provider hỗ trợ và phù hợp.
- Dùng key riêng, không tái sử dụng cho upload khác.
- Lưu versionId cụ thể vào session.
- Đọc đúng version được event tham chiếu.
- Dùng conditional write hoặc write-once policy nếu dịch vụ hỗ trợ.
- Không coi ETag là version ID.

Với storage không có versioning, thiết kế object key một lần và ngăn overwrite qua policy/credential scope nếu có thể. Nếu không thể bảo đảm write-once, cần completion protocol có khóa và xác minh metadata, đồng thời nêu rõ giới hạn race condition.

## 16. Kiểm tra nội dung và quarantine

Bước intake có thể kiểm tra các metadata cơ bản và chuyển object sang trạng thái chờ scan. Tệp vẫn phải được xem là untrusted cho đến khi các processor downstream hoàn tất.

Kiểm tra sớm:

- Kích thước thực tế.
- Extension và declared content type.
- Magic bytes/content signature nếu có thể stream một phần.
- Checksum.
- Archive/decompression limits ở processor chuyên dụng.
- File rỗng hoặc bị cắt.
- Metadata có chứa thông tin nhạy cảm.
- Tenant quota và số upload đồng thời.

Không giải nén archive hoặc chạy parser phức tạp trong API intake. Dùng worker sandbox có giới hạn CPU, memory, thời gian và network egress cho các bước đó.

## 17. Canonical event contract

Downstream không nên phụ thuộc trực tiếp vào envelope notification của từng storage provider. Intake function phát một event nội bộ có schema ổn định.

Ví dụ:

~~~json
{
  "eventId": "evt-82c1",
  "eventType": "file.received",
  "schemaVersion": 1,
  "occurredAt": "2026-11-17T10:15:30Z",
  "publishedAt": "2026-11-17T10:15:32Z",
  "source": "serverless.file-intake",
  "tenantId": "tenant-42",
  "uploadId": "upl-9001",
  "ownerId": "user-17",
  "object": {
    "bucket": "private-quarantine",
    "key": "quarantine/tenant-42/upl-9001/obj-random",
    "versionId": "v-17",
    "sizeBytes": 2457600,
    "checksumAlgorithm": "SHA256",
    "checksum": "base64-value"
  },
  "declaredContentType": "image/jpeg",
  "correlationId": "corr-31",
  "traceId": "trace-71"
}
~~~

Canonical event nên có:

- Event ID duy nhất và ổn định qua retry publish.
- Event type và schema version.
- Thời điểm object được nhận và thời điểm event được publish.
- Source/service phát event.
- Tenant, upload và owner reference.
- Object reference gồm bucket/key/version.
- Size và checksum đã xác minh.
- Correlation/trace reference.
- Không chứa file bytes, presigned URL, access token hoặc secret.

Tên file gốc chỉ đưa vào event nếu downstream thật sự cần và privacy policy cho phép. Thường metadata hiển thị có thể được lấy từ upload record bằng uploadId.

### Event versioning

Thêm field optional thường dễ tương thích hơn thay đổi ý nghĩa field hiện có. Khi cần breaking change, tăng schemaVersion hoặc eventType version, triển khai consumer hỗ trợ trước rồi mới phát phiên bản mới. Lưu schema trong registry hoặc repository có review nếu hệ thống có nhiều producer/consumer.

## 18. Phát event đáng tin cậy bằng transactional outbox

Một lỗi phổ biến là cập nhật upload session thành ACCEPTED rồi gọi event bus. Nếu database commit thành công nhưng publish thất bại, upload được chấp nhận nhưng downstream không biết. Nếu publish thành công rồi database rollback, downstream nhận event cho trạng thái chưa commit.

Transactional outbox giải quyết khoảng trống này khi session database hỗ trợ transaction:

1. Claim event/notification trong inbox.
2. Kiểm tra object và session.
3. Cập nhật upload session thành ACCEPTED.
4. Insert canonical file.received vào outbox.
5. Commit cả hai trong cùng transaction.
6. Publisher đọc outbox chưa gửi.
7. Publish event với eventId ổn định.
8. Sau khi broker xác nhận, đánh dấu outbox record đã gửi.

~~~mermaid
sequenceDiagram
    participant Q as Ingestion Queue
    participant I as Intake Function
    participant D as Database
    participant O as Outbox Publisher
    participant B as Event Bus

    Q->>I: Storage object-created event
    I->>D: Claim inbox + load upload session
    I->>I: HEAD exact object version / validate
    I->>D: Update session + insert outbox
    D-->>I: Commit
    I-->>Q: Acknowledge source message
    O->>D: Read pending outbox record
    O->>B: Publish file.received
    B-->>O: Accepted / publish result
    O->>D: Mark outbox sent
~~~

Outbox publisher có thể crash sau khi broker nhận event nhưng trước khi đánh dấu sent. Khi chạy lại, event có thể được publish duplicate. Vì vậy eventId phải ổn định và downstream consumer phải idempotent.

Nếu database và broker có một transaction integration đặc biệt, có thể dùng cơ chế native đó, nhưng cần hiểu guarantee thật sự. Không giả định gọi API publish trong cùng Java method tạo thành distributed transaction.

## 19. Inbox và idempotency ở intake consumer

Queue/storage notification thường có at-least-once delivery hoặc retry semantics có thể tạo duplicate. Intake consumer cần một inbox/deduplication record bền vững.

Một dedupe key có thể là:

- Provider event ID nếu đảm bảo ổn định cho lần delivery lại.
- Bucket + key + versionId + event type.
- Upload ID + object version + event type.
- Sequencer hoặc generation number nếu provider cung cấp và semantics phù hợp.

Không chỉ dùng bucket + key nếu object có thể được ghi lại. Không chỉ dùng ETag vì nội dung giống nhau có thể có ETag giống nhau nhưng là các lần upload khác nhau.

Inbox record có unique constraint. Trong cùng transaction, consumer claim record, cập nhật session và ghi outbox. Nếu event đã hoàn tất, acknowledge duplicate mà không tạo event nghiệp vụ thứ hai. Nếu event đang xử lý bởi worker khác, dùng lease/conditional update để tránh hai function cùng claim.

### State transition có điều kiện

Chỉ cho phép chuyển trạng thái nếu current status phù hợp. Ví dụ, ACCEPTED không được quay lại VERIFYING vì một notification cũ đến muộn. Dùng compare-and-set hoặc optimistic version để bảo vệ cập nhật.

## 20. Java domain model cho upload intake

Một domain model tối thiểu:

~~~java
public enum UploadStatus {
    CREATED,
    UPLOADING,
    OBJECT_REPORTED,
    VERIFYING,
    RETRY_PENDING,
    ACCEPTED,
    REJECTED,
    EXPIRED,
    CANCELLED,
    FAILED
}

public record UploadSession(
        String uploadId,
        String tenantId,
        String ownerId,
        String bucket,
        String objectKey,
        long maxSizeBytes,
        Instant expiresAt,
        UploadStatus status,
        String objectVersionId,
        String checksumSha256) {
}

public record VerifiedObject(
        String bucket,
        String key,
        String versionId,
        long sizeBytes,
        String checksumSha256,
        String declaredContentType) {
}
~~~

Các record chỉ mô tả dữ liệu. Repository phải enforce tenant scope và optimistic/conditional update. Không expose toàn bộ entity nội bộ qua API response.

## 21. Java intake handler

Handler nhận message từ queue, normalize provider event rồi gọi service. Adapter queue và storage SDK phụ thuộc provider; business logic không nên bị trộn với JSON envelope của notification.

~~~java
public final class StorageEventHandler {
    private final StorageEventMapper mapper;
    private final FileIntakeService intakeService;

    public BatchResult handle(QueueBatch batch) {
        List<String> failedMessageIds = new ArrayList<>();

        for (QueueMessage message : batch.messages()) {
            try {
                StorageObjectCreated event =
                        mapper.toStorageObjectCreated(message.body());

                intakeService.accept(event);
            } catch (RetryableIntakeException ex) {
                failedMessageIds.add(message.messageId());
            } catch (PermanentIntakeException ex) {
                // Record the rejection or route to a quarantine/DLQ path.
                // Do not retry a permanently invalid event forever.
                intakeService.recordPermanentFailure(message, ex);
            }
        }

        return BatchResult.partialFailures(failedMessageIds);
    }
}
~~~

Đây là pseudocode. Với queue hỗ trợ partial batch response, chỉ trả failed message IDs để retry đúng record. Nếu adapter không hỗ trợ partial failure, xử lý batch phải bảo đảm record thành công không bị side effect lặp khi cả batch được giao lại. Permanent error cần được ghi nhận và acknowledge hoặc chuyển DLQ theo policy.

Không bắt mọi exception rồi trả success; điều đó có thể làm mất event. Cũng không retry vô hạn lỗi cấu hình như bucket không tồn tại hoặc IAM permission bị revoke.

## 22. Java service xác minh và ghi outbox

Ví dụ dưới đây mô tả transaction boundary. Storage HEAD call thường diễn ra ngoài database transaction để tránh giữ lock trong lúc network chậm; sau đó service mở transaction ngắn để claim và commit state/outbox. Trong triển khai thực tế cần kiểm tra session version lần nữa sau khi đọc object để tránh race.

~~~java
public void accept(StorageObjectCreated event) {
    UploadSession session =
            uploadRepository.findByObjectReference(
                    event.bucket(), event.key());

    if (session == null) {
        throw new PermanentIntakeException("Unknown upload object");
    }

    if (!session.bucket().equals(event.bucket())
            || !session.objectKey().equals(event.key())) {
        throw new PermanentIntakeException("Object/session mismatch");
    }

    if (session.status() == UploadStatus.ACCEPTED) {
        if (Objects.equals(session.objectVersionId(), event.versionId())) {
            return;
        }
        throw new PermanentIntakeException(
                "Unexpected object version for accepted upload");
    }

    VerifiedObject object =
            storageVerifier.headExactVersion(
                    event.bucket(), event.key(), event.versionId());

    validateSize(session, object);
    validateVersion(event, object);
    validateExpectedChecksum(session, object);

    transaction(() -> {
        boolean claimed = inboxRepository.insertIfAbsent(
                dedupeKey(event, object));

        if (!claimed) {
            return;
        }

        UploadSession current =
                uploadRepository.findForUpdate(session.uploadId());

        requireAcceptableState(current);
        uploadRepository.markAccepted(
                current.uploadId(), object);

        FileReceivedEvent canonical =
                FileReceivedEvent.from(current, object);

        outboxRepository.insert(canonical.eventId(), canonical);
    });
}
~~~

Đây là pseudocode; storage verifier phải đọc đúng version nếu provider có versioning. Nếu event không có versionId, adapter cần một chiến lược write-once/complete protocol rõ ràng. Không tự động dùng HEAD latest khi key có thể bị overwrite giữa event và xử lý.

Nếu claim inbox trong transaction nhưng object validation xảy ra trước transaction, event duplicate có thể cùng đọc HEAD song song; transaction unique constraint bảo đảm chỉ một bản ghi outbox được tạo. Nếu validation có chi phí lớn, có thể claim bằng lease trước rồi hoàn tất sau, nhưng lease cần expiry và recovery khi function crash.

## 23. API completion như một tín hiệu bổ sung

Một số flow cần client gọi complete endpoint để UX biết upload đã xong. Endpoint không nên tin lời client rằng object đã upload thành công.

Flow:

1. Client gọi POST /v1/uploads/{uploadId}/complete.
2. Backend xác thực owner/tenant và session.
3. Backend đọc HEAD object theo key/version.
4. Kiểm tra actual size/checksum và multipart completion.
5. Ghi nhận completion hint hoặc gọi cùng intake service.
6. Storage notification nếu đến sau sẽ trở thành duplicate hợp lệ.

Nếu object event đến trước completion API, intake vẫn có thể xác minh và chấp nhận. Completion API khi đó trả trạng thái hiện tại. Hai đường kích hoạt phải dùng chung state machine và idempotency key để tránh hai event file.received.

Không tạo một event chỉ vì client gọi complete. Event chỉ được tạo sau khi object được đọc và xác minh ở storage.

## 24. Xử lý event đến sai thứ tự hoặc đến muộn

Event có thể đến sau khi session hết hạn, bị cancel hoặc object đã bị xóa. Một upload key có thể phát nhiều event do overwrite hoặc multipart retry.

Quy tắc:

- Session terminal như EXPIRED/CANCELLED không tự chuyển sang ACCEPTED.
- Event version cũ không được ghi đè version mới đã được chọn.
- Event duplicate đã xử lý phải được acknowledge.
- Event không có session hoặc không khớp key phải bị từ chối và ghi audit.
- Event đến sau retention window cần policy riêng: reject, quarantine hoặc điều tra.
- Event cho object version đã bị xóa cần ghi trạng thái lỗi rõ.

Không xóa session ngay khi hết hạn. Giữ tombstone/metadata trong thời gian đủ để nhận biết event đến muộn và chống replay. Lifecycle cleanup có thể xóa object bytes nhưng giữ record nhỏ hơn theo retention policy.

## 25. Retry, visibility timeout và DLQ

Retry policy cần phân biệt lỗi tạm thời với lỗi vĩnh viễn.

| Loại lỗi | Hành vi |
|---|---|
| Storage timeout/throttling | Retry với backoff |
| Database transient failure | Retry transaction có giới hạn |
| Event bus unavailable | Outbox giữ pending và retry |
| Object chưa đọc được ngay | Retry ngắn theo consistency/notification semantics |
| Unknown upload ID | Permanent reject hoặc quarantine |
| Bucket/key mismatch | Security event, không retry mù |
| File vượt size limit | REJECTED, không retry |
| Checksum mismatch | REJECTED hoặc yêu cầu upload lại theo policy |
| Permission denied do cấu hình | Alert và retry sau khi khắc phục, tránh hot loop |

Visibility timeout hoặc message lease phải đủ dài cho thời gian xử lý tối đa cộng buffer. Nếu function có thể chạy lâu hơn visibility timeout, message có thể được giao cho consumer khác khi consumer đầu vẫn chạy. Dùng heartbeat/lease extension nếu dịch vụ hỗ trợ hoặc giảm thời gian xử lý mỗi batch.

DLQ giữ event không thể xử lý sau số lần thử. Cần cảnh báo DLQ ingress và oldest message age, runbook kiểm tra nguyên nhân và quy trình redrive có kiểm soát. Không redrive hàng loạt trước khi sửa lỗi gốc.

## 26. Bảo mật và IAM

Tách quyền theo vai trò:

- Upload API: tạo session và cấp signed request, không cần quyền đọc mọi object.
- Client signed URL: chỉ PUT vào một object key và thời hạn cụ thể.
- Storage notification service: gửi event đến queue/event bus.
- Intake function: đọc metadata/bytes trong quarantine, cập nhật session và ghi outbox.
- Outbox publisher: publish canonical event đến topic/bus được chỉ định.
- Downstream processor: chỉ đọc object cần xử lý và ghi output vào prefix riêng.
- Auditor/operator: đọc log và trạng thái theo quyền được cấp.

Các kiểm soát khác:

- Bucket/container private; block public access.
- Encryption at rest và TLS in transit.
- KMS key policy tối thiểu.
- Signed URL TTL ngắn, không ghi log.
- Network endpoint/private access nếu phù hợp.
- Validate tenant/owner ở backend.
- Audit thao tác cấp URL, complete, reject và redrive.
- Không cho function dùng wildcard resource nếu có thể giới hạn theo bucket/prefix.

Không cho client quyền đọc quarantine object. Download chỉ cấp sau khi pipeline xử lý và policy quyết định trạng thái object.

## 27. Quota và chống abuse

Upload có thể gây chi phí storage, scan và compute lớn. Áp quota trước khi cấp signed URL:

- Maximum file size theo loại.
- Tổng dung lượng upload đang pending theo tenant.
- Tổng dung lượng được lưu.
- Số upload session đồng thời.
- Số request tạo session mỗi user/IP.
- Giới hạn multipart part count.
- Expiry cho session chưa hoàn tất.
- Giới hạn số lần cấp lại URL.
- Giới hạn processing admission khi downstream backlog cao.

Quota phải được enforce ở backend và có transaction/conditional update để hai request đồng thời không vượt hạn mức. Nếu dùng quota counter eventual consistency, xác định overshoot có thể chấp nhận hay cần reservation chính xác.

Khi session được chấp nhận, chuyển reserved quota sang actual usage. Khi rejected, cancelled hoặc expired, giải phóng reservation và cleanup object theo policy. Tránh giữ quota mãi do session orphan.

## 28. Observability và audit

Cần correlation ID xuyên từ API create session đến object notification, intake, outbox và downstream event.

Metric quan trọng:

- Upload sessions created/completed/expired/rejected.
- Upload bytes theo tenant/file type.
- Time từ session creation đến object event.
- Queue depth và oldest message age.
- Intake processing duration và retry count.
- Unknown object/session mismatch.
- Checksum/size validation failure.
- Duplicate notification count.
- Outbox pending count và oldest pending age.
- Publish success/failure.
- DLQ ingress.
- Cost per accepted upload.

Log structured nên có uploadId, tenant-safe reference, object version, event ID, queue message ID, correlation ID và function version. Không log presigned URL, token, raw file bytes hoặc sensitive filename nếu không cần.

Audit event cần ghi ai tạo session, ai cancel, policy nào từ chối, object nào được accept/reject và operator nào redrive DLQ. Audit archive nên có quyền tách biệt và retention phù hợp.

## 29. Chi phí và tối ưu

Chi phí intake có thể gồm:

- API Gateway request và Upload API function.
- Object storage PUT/GET/HEAD và dung lượng quarantine.
- Storage notification hoặc event bus ingestion.
- Queue send/receive/delete và retention.
- Intake function duration/concurrency.
- Database writes cho session, inbox và outbox.
- KMS requests và network transfer.
- Logs, metrics, traces và DLQ storage.
- Multipart parts chưa hoàn tất và object orphan.

Tối ưu:

- Upload bytes trực tiếp vào storage thay vì proxy qua function.
- HEAD metadata thay vì tải toàn object ở intake.
- Dùng checksum/streaming verification phù hợp.
- Batch queue messages khi latency cho phép.
- Đặt lifecycle cho expired/rejected object và multipart upload.
- Hạn chế log payload lớn.
- Dọn session/object orphan bằng scheduled cleanup.
- Giới hạn concurrency theo database và downstream.
- Đo cost per accepted upload và cost per GB received.

Không bỏ bước xác minh hoặc security boundary để tiết kiệm một request. Nếu cần scan bytes, tính chi phí ở processor tương ứng và chỉ đọc/stream số lần cần thiết.

## 30. Kiểm thử

### Unit test

- Tạo object key không dùng filename client.
- Validate quota, file size và content type allowlist.
- Chuyển trạng thái hợp lệ và từ chối chuyển trạng thái sai.
- Tạo canonical event với eventId ổn định.
- Dedupe key khác nhau cho object version khác nhau.
- Mapping notification provider thành internal event.
- Reject tenant, bucket hoặc key mismatch.

### Integration test

- Tạo session và upload object vào storage test.
- Storage notification đi đến queue.
- Intake function đọc đúng object version.
- Database session chuyển ACCEPTED.
- Outbox record được tạo.
- Publisher phát event và đánh dấu sent.
- Duplicate notification không tạo event nghiệp vụ thứ hai.
- Event đến muộn sau EXPIRED/CANCELLED bị xử lý theo policy.

### Failure test

| Kịch bản | Kết quả mong đợi |
|---|---|
| Client timeout sau khi tạo session | Retry cùng key trả cùng session |
| Signed URL hết hạn | Cấp lại có kiểm soát hoặc từ chối theo session |
| Upload vượt size | Không ACCEPTED; quota được xử lý đúng |
| Object event duplicate | Chỉ một canonical event |
| Object key bị overwrite | Xử lý đúng version hoặc reject |
| HEAD storage timeout | Retry; không tạo event sớm |
| DB commit lỗi | Queue message retry; không mất event |
| Publish event bus lỗi | Outbox vẫn pending |
| Publisher crash sau publish | Duplicate publish được downstream dedupe |
| Intake function crash | Queue retry; state transition an toàn |
| Unknown upload ID | Permanent reject/quarantine và audit |
| DLQ redrive | Chỉ event đủ điều kiện được xử lý lại |

Test với object giả và dữ liệu không nhạy cảm. Kiểm tra cả trường hợp một phần batch thành công, một phần thất bại nếu queue hỗ trợ partial batch response.

## 31. Triển khai theo từng bước

1. **Tạo storage quarantine:** private access, encryption, versioning nếu cần và lifecycle.
2. **Tạo upload session database:** schema, unique key, state và quota reservation.
3. **Triển khai Upload API:** auth, authorization, idempotency và signed URL.
4. **Thiết lập CORS:** chỉ origin, method và header cần thiết.
5. **Cấu hình storage notification:** filter đúng bucket/prefix/event type.
6. **Tạo ingestion queue:** retry, visibility timeout, retention và DLQ.
7. **Triển khai Java intake function:** parse event, verify object, update state.
8. **Tạo inbox/outbox:** unique constraint, transaction và publisher.
9. **Định nghĩa canonical event:** schema version, event ID và object reference.
10. **Kết nối downstream test consumer:** xác nhận event có thể được đọc và dedupe.
11. **Thiết lập dashboard/alert:** queue age, outbox backlog, rejection và DLQ.
12. **Chạy integration/failure test:** duplicate, overwrite, timeout và publish outage.
13. **Canary production:** giới hạn tenant/traffic và theo dõi cost/error.
14. **Mở rộng dần:** tăng concurrency và quota theo capacity thực tế.

### Kiểm tra trước khi mở traffic

- Signed URL không có quyền GET/DELETE/list.
- Quarantine không public.
- Object key do server tạo.
- Event không chứa secret hoặc signed URL.
- Function không tin metadata client.
- Outbox publisher có retry và idempotency.
- DLQ có alert và runbook.
- Lifecycle cleanup không xóa object đang xử lý.
- IAM role và KMS policy đã được kiểm tra.
- Quota không thể bị vượt bởi request đồng thời.

## 32. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Proxy toàn bộ file qua API function | Tăng latency, memory và chi phí | Direct upload vào object storage |
| Dùng filename làm object key | Collision, path manipulation và lộ thông tin | Server-generated random key |
| Tin MIME type client gửi | File giả định dạng | Sniff content và validate |
| Tin callback complete của client | Event giả hoặc session sai trạng thái | Verify object trực tiếp ở storage |
| Public bucket để client upload dễ | Rò rỉ object và abuse | Private bucket + signed URL |
| Không có upload session | Không biết owner, quota và expiry | Durable session record |
| Dùng key có thể overwrite | Event cũ có thể đọc bytes mới | Versioning hoặc write-once key |
| Tin ETag luôn là MD5 | Checksum sai | Dùng checksum semantics chính thức |
| Xử lý storage event như exactly-once | Duplicate side effect | Inbox/idempotency |
| Publish event sau DB commit không có outbox | Mất event khi broker lỗi | Transactional outbox |
| Mark outbox sent trước publish | Event bị mất | Mark sent sau broker acknowledgement |
| Cùng prefix cho quarantine và output | Event loop | Tách bucket/prefix và filter |
| Không có DLQ | Poison event retry vô hạn | Retry cap, DLQ và runbook |
| HEAD latest thay vì exact version | Xử lý nhầm object version | VersionId/immutable key |
| Không giữ tombstone session | Event đến muộn không được nhận diện | Retain session metadata theo policy |
| Không có quota reservation | Concurrent request vượt quota | Atomic reservation/conditional update |
| Log signed URL | Lộ bearer capability | Redact và không log query string |
| Cleanup object quá sớm | Worker không đọc được object | Lifecycle dựa trên trạng thái pipeline |

## 33. Checklist production

- **Upload authorization:** user/tenant được xác thực và có quyền upload vào resource.
- **Session:** có uploadId, owner, tenant, object key, quota, expiry và state.
- **Idempotency:** create session và complete operation chịu được client retry.
- **Object key:** do server tạo, không dùng filename client.
- **Signed URL:** đúng method/key, TTL ngắn, không cấp read/list/delete.
- **Storage:** private, encrypted, versioning/write-once strategy và lifecycle phù hợp.
- **CORS:** origin/method/header được giới hạn.
- **Notification:** filter đúng event/prefix; queue buffer và retry được cấu hình.
- **Verification:** HEAD đúng object/version; kiểm tra size, checksum, owner và session.
- **Content:** declared MIME được xem là hint; scan/parse ở worker sandbox.
- **State machine:** transition có điều kiện và terminal state không bị ghi đè.
- **Inbox:** duplicate notification không tạo side effect lặp.
- **Outbox:** session ACCEPTED và canonical event intent cùng transaction.
- **Publisher:** retry, stable eventId và publish acknowledgement.
- **Event contract:** schema version, object reference, tenant/upload ID và correlation ID.
- **Security:** IAM least privilege, KMS, no public access và không log signed URL.
- **Quota:** reservation, release, concurrent upload và cleanup được kiểm soát.
- **Reliability:** visibility timeout, partial batch failure, retry cap và DLQ.
- **Observability:** upload-to-event latency, queue age, outbox backlog, rejection và cost.
- **Testing:** duplicate, late event, overwrite, timeout, publish outage, DLQ redrive và security test.
- **Operations:** dashboard, alert, runbook, replay và lifecycle review có owner.

## 34. Kết luận

Bước tiếp nhận tệp cần tách quyền khởi tạo upload khỏi quyền xử lý object. Backend tạo upload session, kiểm tra identity/quota và cấp signed URL giới hạn. Client truyền bytes trực tiếp vào private quarantine storage. Storage notification đi qua queue để Java intake function xác minh object thực tế với session, version, size và checksum. Sau khi xác minh, function cập nhật trạng thái và ghi canonical file.received event vào transactional outbox.

Storage notification có thể duplicate, đến trễ hoặc sai thứ tự; client callback cũng có thể timeout hoặc bị giả mạo. Vì vậy intake phải dùng state machine, inbox/idempotency, exact object version và conditional update. Outbox bảo đảm ý định phát event được lưu cùng transaction với trạng thái ACCEPTED; publisher retry và downstream consumer tiếp tục dedupe theo eventId.

Thiết kế này tạo một hợp đồng ổn định giữa bước upload và các processor phía sau. Ảnh, video và tài liệu có thể được xử lý độc lập mà không cần phụ thuộc vào API upload hoặc envelope notification của provider. Khi thêm quota, security, lifecycle, observability và failure tests từ đầu, pipeline có thể mở rộng theo tải mà vẫn giữ được quyền sở hữu, tính toàn vẹn và khả năng truy vết của từng tệp.
