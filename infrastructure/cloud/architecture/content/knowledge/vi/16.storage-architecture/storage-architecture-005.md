# Tải lên dung lượng lớn, tải tiếp và truy cập có thời hạn

Ứng dụng lưu trữ ảnh, video, tài liệu hoặc bản sao lưu thường phải nhận tệp từ hàng trăm MB tới nhiều GB. Nếu gửi toàn bộ tệp qua backend trong một request HTTP, hệ thống có thể gặp timeout, giới hạn payload, tiêu tốn bộ nhớ và khó phục hồi khi kết nối bị ngắt. Ngược lại, nếu cấp một URL cho phép tải trực tiếp lên object storage mà không kiểm soát quyền, người dùng có thể ghi nhầm vị trí, ghi đè dữ liệu hoặc chia sẻ đường dẫn lâu hơn dự kiến.

Bài học này tập trung vào ba năng lực: **tải lên dung lượng lớn**, **tải tiếp sau gián đoạn (resumable upload)** và **truy cập có thời hạn**. Trong module CLOUD_ARCHITECTURE, đây là bài toán kết hợp storage, network, compute, identity, bảo mật và vận hành. Kiến trúc tốt giúp truyền dữ liệu hiệu quả, phục hồi được, kiểm soát quyền, theo dõi vòng đời object và cân bằng chi phí với độ tin cậy.

## 1. Chọn đường truyền: qua backend hay trực tiếp tới storage?

Giả sử người dùng tải video 2 GB lên nền tảng đặt chỗ.

### Proxy upload qua backend

~~~mermaid
flowchart LR
    C["Browser / Mobile"] -->|"Upload file"| API["Application API"]
    API -->|"Stream bytes"| S[("Object storage")]
    API --> DB[("Metadata database")]
~~~

Backend nhận dữ liệu rồi chuyển tiếp storage. Mô hình này hữu ích khi cần biến đổi nội dung trong luồng, client không thể truy cập storage hoặc yêu cầu mạng bắt buộc traffic qua một điểm kiểm soát.

Đánh đổi:
- Backend tiêu thụ băng thông, connection và tài nguyên trong suốt thời gian truyền.
- Timeout của proxy, load balancer và ứng dụng phải phù hợp với kích thước/độ dài upload.
- Request dài chiếm worker; tải đột biến làm giảm khả năng phục vụ API nghiệp vụ.
- Client mất kết nối thì backend phải quản lý trạng thái, dọn dữ liệu dở và resume.
- Đường client → backend → storage có thể làm tăng phí truyền hoặc xử lý.

Nếu dùng proxy, nên stream dữ liệu thay vì đọc toàn bộ tệp vào RAM; giới hạn concurrency, tổng thời gian, tốc độ tối thiểu và kích thước tối đa.

### Upload trực tiếp bằng URL ký

~~~mermaid
sequenceDiagram
    actor U as User
    participant API as Application API
    participant DB as Metadata DB
    participant S as Object storage
    U->>API: Xin tạo upload session
    API->>API: Xác thực, quyền, quota
    API->>DB: Lưu session PENDING
    API-->>U: Signed upload URL / part instructions
    U->>S: Upload bytes trực tiếp
    S-->>U: Part receipt / result
    U->>API: Báo hoàn tất
    API->>S: Kiểm tra object, size, checksum
    API->>DB: Cập nhật trạng thái
    API-->>U: Trạng thái upload
~~~

Backend điều phối phiên và cấp pre-signed/signed URL hoặc thông tin upload theo khả năng storage. Client truyền byte trực tiếp tới object storage. Backend vẫn chịu trách nhiệm xác thực người dùng, quyết định object key, kiểm tra quota, quyền sở hữu, hoàn tất và cập nhật metadata.

Ưu điểm là backend không proxy payload, có thể tận dụng multipart/resumable và mở rộng tốt cho nhiều client. Đánh đổi là client cầm URL có quyền như một bearer capability trong thời hạn ký; cần quản lý CORS, quota, expiry, object tạm, kiểm tra nội dung và session bỏ dở.

URL ký không thay thế authorization tại bước tạo phiên và kiểm tra object sau upload.

## 2. Mô hình object và trạng thái upload

Object storage thường tổ chức dữ liệu theo bucket/container và object key. Backend nên tạo key; không cho client tự do ghi vào mọi đường dẫn.

~~~text
tenant-42/bookings/BK-9081/uploads/up-7f3a/original
tenant-42/bookings/BK-9081/uploads/up-7f3a/preview
~~~

Đây là cấu trúc minh họa. Tránh nhúng thông tin cá nhân nhạy cảm vào key vì key có thể xuất hiện trong log, URL và metric. Có thể dùng ID ngẫu nhiên và lưu mapping trong metadata database.

Metadata record nên có uploadId, ownerId/tenantId, objectKey, tên file hiển thị, expectedSize, expectedChecksum, contentTypeClaimed, state, expiresAt, storageUploadId, createdAt và completedAt.

Các trạng thái tham khảo:
- PENDING: session được tạo, chưa truyền dữ liệu.
- UPLOADING: đang nhận part hoặc byte range.
- COMPLETING: client báo xong, server đang xác minh hoàn tất.
- QUARANTINED: object đã nhận nhưng đang chờ scan/validation.
- COMPLETE: đã qua các kiểm tra bắt buộc, được phép sử dụng.
- FAILED hoặc EXPIRED: thất bại hoặc hết hạn.

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> UPLOADING
    UPLOADING --> COMPLETING
    COMPLETING --> QUARANTINED
    COMPLETING --> FAILED
    QUARANTINED --> COMPLETE
    QUARANTINED --> FAILED
    PENDING --> EXPIRED
    UPLOADING --> EXPIRED
~~~

Tách QUARANTINED khỏi COMPLETE hữu ích khi tệp phải qua antivirus, kiểm tra định dạng hoặc kiểm duyệt. Chỉ cấp quyền đọc cho object đã qua các bước bắt buộc.

## 3. Multipart upload và resumable upload

### Multipart upload

Client chia tệp thành nhiều part. Storage giữ từng phần trong một upload session; khi các phần cần thiết đã được nhận, client/backend gửi lệnh complete để tạo object cuối.

~~~mermaid
flowchart TB
    F["File 2 GB"] --> SPLIT["Chia thành part"]
    SPLIT --> P1["Part 1"]
    SPLIT --> P2["Part 2"]
    SPLIT --> P3["Part 3"]
    SPLIT --> PN["Part N"]
    P1 --> S[("Upload session")]
    P2 --> S
    P3 --> S
    PN --> S
    S --> COMPLETE["Complete multipart"]
    COMPLETE --> OBJ[("Final object")]
~~~

Các thao tác điển hình:
1. Initiate: tạo multipart session; storage trả upload ID.
2. Upload part: gửi từng phần, thường gắn part number và checksum/ETag tùy dịch vụ.
3. List parts: lấy danh sách phần đã được storage nhận.
4. Complete: gửi danh sách part/identifier để tạo object.
5. Abort: hủy session khi không còn cần hoặc quá hạn.

Nếu part 17 lỗi, client có thể gửi lại riêng part đó. Multipart không tự động bảo đảm ứng dụng resume qua trình duyệt/thiết bị; ứng dụng phải giữ upload ID, part state và quyền tương ứng.

### Resumable upload

Resumable upload tiếp tục truyền sau khi kết nối bị gián đoạn. Nó có thể dựa trên multipart API, session URI/offset API hoặc protocol riêng.

Phiên nên lưu:
- Session ID/URI và thời hạn hiệu lực.
- Upload ID phía storage hoặc object đích.
- Tổng kích thước, chunk size và checksum dự kiến.
- Part/offset đã được server xác nhận.
- User/tenant sở hữu phiên.
- Trạng thái hoàn tất hoặc hủy.

Không chỉ lưu tiến độ trong browser rồi tin rằng server đã nhận đúng các byte đó. Khi reconnect, client cần hỏi server/storage đã nhận tới đâu bằng list parts, offset/status hoặc API tương ứng. Tiến độ local có thể sai nếu response bị mất sau khi storage đã nhận chunk.

### Chunk size và concurrency

Chunk quá nhỏ làm tăng số request, overhead HTTP/TLS và metadata. Chunk quá lớn khiến retry một lần phải gửi lại nhiều byte, tăng buffer và thời gian chờ. Upload quá nhiều part song song làm tăng throughput nhưng cũng tăng socket, CPU, băng thông và throttling.

Ví dụ file 1 GiB với chunk 16 MiB cần khoảng 64 part (bỏ qua khác biệt đơn vị và giới hạn provider). Bốn part đồng thời có thể cải thiện throughput nhưng tiêu thụ nhiều connection hơn. Đây là ví dụ định lượng, không phải giá trị mặc định.

### Pseudocode điều phối

~~~text
session = POST /uploads {fileName, size, checksum}

while parts remain:
    part = next part within allowed concurrency
    response = PUT signed_part_url(part)
    if success:
        save part number and provider receipt
    else if retryable:
        retry with bounded backoff
    else:
        stop and report failure

serverParts = GET /uploads/{uploadId}/parts
reconcile local progress with serverParts
result = POST /uploads/{uploadId}/complete
verify object metadata and checksum
~~~

Nếu complete bị timeout sau khi storage đã hoàn tất object, không được giả định upload thất bại. Client/server phải truy vấn trạng thái object/session trước khi gọi complete lần nữa.

## 4. Checksum, tính toàn vẹn và ETag

Truyền đủ byte chưa chứng minh nội dung nhận được giống nội dung nguồn.

- Checksum như CRC32C hoặc SHA-256 có thể phát hiện lỗi dữ liệu theo semantics hỗ trợ.
- ETag là validator/identifier do storage trả về; không được mặc định ETag luôn là MD5 của toàn object.
- Multipart checksum có thể là checksum từng part hoặc checksum tổng hợp.
- Size validation xác minh kích thước thực.
- Content validation kiểm tra định dạng thật, không chỉ MIME type do client khai báo.

Quy trình nên tính hoặc nhận checksum kỳ vọng, gửi checksum theo API hỗ trợ, xác minh kết quả ở storage, so sánh sau complete và cách ly object khi mismatch. Checksum phát hiện thay đổi ngoài ý muốn, **không xác minh người gửi có quyền** và không chứng minh file an toàn.

## 5. Upload URL ký và quyền ghi có thời hạn

Pre-signed upload URL thường cho phép client thực hiện hành động cụ thể lên object/part trong khoảng thời gian và điều kiện được ký.

Luồng an toàn:
1. Client xác thực với Application API.
2. Backend kiểm tra quyền upload vào resource/tenant.
3. Kiểm tra quota, kích thước, loại tệp được phép.
4. Backend tạo object key khó đoán và session.
5. Backend cấp URL ký với method, key, header/constraint và expiry phù hợp.
6. Client upload trực tiếp.
7. Backend xác minh kết quả và chỉ đưa object vào trạng thái sử dụng sau kiểm tra.

**URL ký là bearer capability:** ai có URL hợp lệ có thể dùng quyền đã ký cho tới khi hết hạn hoặc credential/policy liên quan bị vô hiệu hóa theo semantics provider.

Các kiểm soát:
- Thời hạn ngắn, đúng use case.
- Chỉ một object key/part cụ thể; không cấp quyền cả bucket.
- Ràng buộc method và header quan trọng.
- Giới hạn content length/type khi provider hỗ trợ; nếu không, kiểm tra sau upload.
- Gửi qua HTTPS, tránh URL xuất hiện trong referrer, analytics và application log.
- Không để client tự chọn bucket, tenant prefix hay object key tùy ý.
- Quota và rate limit trước khi cấp URL.
- Kiểm soát overwrite/versioning để URL cũ không ghi đè dữ liệu quan trọng.

Một số dịch vụ không hỗ trợ mọi điều kiện content length hoặc one-time use theo cách mong muốn. Nếu cần giới hạn chặt hơn, có thể cần upload policy/form, gateway hoặc xác minh hậu upload. Không tuyên bố URL one-time nếu nó chỉ là quyền có thời hạn và có thể gọi lại.

## 6. Download có thời hạn và signed URL

Với object riêng tư, backend xác thực user, kiểm tra quyền file rồi cấp signed download URL. Client tải trực tiếp từ storage/CDN.

~~~mermaid
sequenceDiagram
    actor U as User
    participant API as Application API
    participant DB as Authorization DB
    participant S as Private storage
    U->>API: Xin tải fileId
    API->>DB: Kiểm tra ownership, tenant, trạng thái
    DB-->>API: Authorized + object key
    API->>S: Tạo signed GET URL ngắn hạn
    S-->>API: URL + expiry
    API-->>U: URL tạm thời
    U->>S: GET object
    S-->>U: Object bytes
~~~

Cần phân biệt:
- URL ký có thể tiếp tục hoạt động tới expiry dù user vừa đăng xuất.
- Xóa metadata ứng dụng không nhất thiết thu hồi object hoặc URL đang hiệu lực.
- Thay policy/rotate key/xóa object có thể ảnh hưởng URL nhưng có thể tác động rộng.
- CDN có thể giữ nội dung sau khi URL hết hạn nếu cache policy cho phép.

Nếu cần thu hồi tức thời, signed URL thuần có thể không đủ vì nó là capability tự chứa với expiry. Có thể proxy download qua API/gateway để kiểm tra quyền mỗi request; dùng CDN token/cookie có cơ chế revoke; ràng buộc URL với credential/policy có thể thu hồi; hoặc chọn expiry ngắn và chấp nhận cửa sổ thu hồi hữu hạn.

Thời hạn truy cập phụ thuộc dữ liệu và use case. Link tải ảnh xem trước có thể sống lâu hơn link tải hợp đồng hoặc hồ sơ cá nhân.

## 7. Range request, streaming và download tiếp tục

HTTP Range cho phép client yêu cầu một phần byte của object, thường dùng resume hoặc tua video:

~~~http
GET /files/video.mp4 HTTP/1.1
Range: bytes=1048576-2097151
~~~

Server có thể trả 206 Partial Content, kèm Content-Range và phần byte tương ứng.

Range hữu ích cho resume download, tua video/audio, tải một đoạn file lớn hoặc tải song song các byte range. Cần dùng ETag/Last-Modified và If-Range phù hợp để không ghép các phần từ hai phiên bản object khác nhau. Nếu object thay đổi giữa các request, file ghép có thể bị hỏng.

Streaming xử lý byte theo luồng thay vì buffer toàn bộ object vào RAM. Khi proxy download, cần giới hạn concurrency, backpressure và timeout. Khi tải trực tiếp storage/CDN, cần quản lý quyền và cache.

## 8. Khác biệt giữa các dịch vụ object storage

| Nền tảng | Cơ chế upload lớn/tiếp tục | Signed access | Điểm cần xác minh |
|---|---|---|---|
| **Amazon S3** | Multipart upload, upload part, list parts, complete/abort | Pre-signed URL cho upload/download và part | Part size/count, lifecycle dọn incomplete multipart, checksum, expiry và quyền ký |
| **Azure Blob Storage** | Block blob upload bằng block ID rồi commit block list; SDK có transfer options | SAS giới hạn resource, permission và thời gian; user delegation SAS dựa trên Entra credentials khi phù hợp | Block size/count, SAS permissions/start/expiry, CORS và identity |
| **Google Cloud Storage** | Resumable upload qua session URI, gửi tiếp byte range | Signed URL cho upload/download; signed policy document cho một số form upload | Session URI là capability nhạy cảm; chunk alignment/progress, signing identity, expiry và checksum |

Không coi các cơ chế giống hệt nhau:
- S3 multipart dùng upload ID và part identifiers; incomplete upload có thể tồn tại tới abort hoặc lifecycle cleanup.
- Azure block blob gom block theo block ID rồi commit block list; cần phân biệt loại SAS và quyền/thời hạn.
- GCS resumable upload dùng session URI để tiếp tục gửi byte; session URI phải được bảo vệ như credential cho phiên upload đó.

SDK có thể tự chia part, retry hoặc resume ở một mức nhất định. Cần xác định phần nào SDK quản lý và phần nào ứng dụng phải lưu bền vững. Khi nâng SDK, kiểm tra behavior, retry và checksum.

## 9. Quản lý upload session và dọn tài nguyên bỏ dở

Session có thể bị bỏ dở vì user đóng browser, thiết bị hết pin, mạng mất lâu hoặc ứng dụng không gửi complete/abort. Các part tạm vẫn có thể chiếm storage và phát sinh phí.

Cần:
- Gắn session với user/tenant và object key cụ thể.
- Lưu createdAt, expiresAt và state.
- Hạn chế số session đồng thời trên mỗi user/tenant.
- Tự động expire/abort session không hoạt động.
- Dùng lifecycle rule của storage để dọn incomplete multipart nếu dịch vụ hỗ trợ.
- Dọn metadata tương ứng nhưng không xóa nhầm object hoàn tất.
- Ghi audit khi abort/cleanup dữ liệu quan trọng.
- Xử lý race giữa cleanup và client đang upload/complete.

Scheduler có thể tìm session PENDING/UPLOADING đã quá hạn, kiểm tra trạng thái storage, abort session và đánh dấu EXPIRED. Không chỉ dựa vào database flag nếu storage upload vẫn còn.

### Idempotency cho create/complete

Client có thể gửi lại request tạo session khi không nhận response. Nếu API tạo session mới mỗi lần, sẽ sinh nhiều upload bỏ dở. Dùng idempotency key theo user và thao tác, hoặc cho phép truy vấn session theo request ID.

Complete có thể timeout sau khi storage đã tạo object. API cần kiểm tra trạng thái session/object trước khi complete lần nữa. Cleanup cũng cần idempotent.

## 10. Kiểm tra tệp trước khi công bố

Storage xác nhận upload hoàn tất không có nghĩa nội dung đã an toàn.

1. Size: so sánh kích thước thực với quota và giới hạn nghiệp vụ.
2. Checksum: xác minh tính toàn vẹn.
3. File signature: xác minh định dạng từ bytes, không chỉ MIME do client gửi.
4. Malware scan: dùng dịch vụ/engine phù hợp.
5. Content validation: giới hạn file nén, nội dung lồng nhau, macro hoặc định dạng không được phép.
6. Data classification: xác định loại dữ liệu, retention và quyền.
7. Metadata sanitization: không tin tên file hoặc metadata do client gửi.

~~~mermaid
flowchart LR
    U["Client upload"] --> Q[("Quarantine storage")]
    Q --> V["Size / checksum / file type"]
    V --> SCAN["Malware / content scan"]
    SCAN -->|"Pass"| CLEAN[("Approved object")]
    SCAN -->|"Fail"| HOLD[("Rejected / isolated")]
    CLEAN --> DB[("Metadata = COMPLETE")]
~~~

Không phục vụ public URL cho object đang quarantine. Nếu scan bất đồng bộ, người dùng cần thấy trạng thái PROCESSING hoặc QUARANTINED; byte upload xong không đồng nghĩa tệp đã được phê duyệt.

## 11. Bảo mật URL, CORS và tenant isolation

**CORS không phải authorization.** CORS là cơ chế trình duyệt kiểm soát origin nào được phép đọc response trong một số cross-origin request. Nó không ngăn mọi client ngoài trình duyệt gọi storage endpoint.

Cần cấu hình allowed origin cụ thể, method/header cần thiết và chỉ expose các header như ETag/checksum receipt khi cần. Không dựa vào CORS để kiểm soát quyền đọc/ghi object; signed URL/SAS, IAM và bucket/container policy mới quyết định quyền storage.

Backend cần xác minh:
- User thuộc tenant sở hữu resource không?
- Có quyền upload/download tệp loại này ở trạng thái hiện tại không?
- Quota theo user/tenant còn không?
- Object có thuộc resource được phép không?
- Object đã qua scan chưa?
- Link có đúng action, key, method và expiry không?

Không nhận object key tùy ý từ client rồi ký trực tiếp. Backend nên ánh xạ fileId/uploadId do hệ thống cấp sang object key sau khi kiểm tra quyền.

URL ký có thể rò rỉ qua application/proxy/CDN log, browser history/referrer, analytics, error report, screenshot hoặc ticket. Giảm rò rỉ bằng cách redaction signature/token, HTTPS, tránh analytics không cần thiết, policy Referrer-Policy phù hợp, expiry ngắn và ghi log bằng object ID/action/issuer/expiry thay vì URL đầy đủ.

Với multi-tenant, object key có namespace riêng nhưng prefix không phải kiểm soát duy nhất. Authorization phải kiểm tra tenant ở API và storage policy; signed URL không thể truy cập object tenant khác; audit ghi principal/tenant context nhưng không lộ token. Encryption at rest/in transit và quản lý key theo phân loại dữ liệu.

## 12. Download, cache và CDN

CDN giảm độ trễ và egress trực tiếp từ origin, nhưng cache có thể phân phối nội dung sau khi quyền ứng dụng thay đổi nếu policy không đúng.

Cần xem:
- Cache key có bao gồm token/cookie/header cần thiết không?
- Signed URL hết hạn được edge kiểm tra ở mỗi request hay chỉ khi cache miss?
- Cache TTL có vượt thời gian cho phép chia sẻ dữ liệu không?
- Khi object bị xóa/quyền bị thu hồi, purge/invalidation mất bao lâu?
- Có thể dùng signed cookie hoặc tokenized CDN URL thay URL storage không?
- Range request và partial cache có được hỗ trợ?
- Content-Disposition có đặt tên file tải xuống an toàn không?

Object public, immutable có thể cache lâu. Object riêng tư cần cache policy gắn với authorization và mức nhạy cảm. Không đặt public max-age rộng cho nội dung người dùng chỉ để tăng tốc download.

## 13. Quota, giới hạn và chống lạm dụng

Upload có thể bị lạm dụng để tiêu tốn storage, request, băng thông hoặc tài nguyên scan. Cần giới hạn kích thước theo loại tệp, dung lượng/số object theo user và tenant, số session đồng thời, số part song song, tốc độ khởi tạo session, session/URL TTL, loại file cho phép, download rate và số lần cấp URL.

Quota cần kiểm tra trước khi cấp phiên và đối soát sau hoàn tất. Nếu chỉ trừ quota khi tạo session, upload bỏ dở giữ chỗ dung lượng; nếu chỉ tính sau upload, nhiều session đồng thời có thể vượt quota. Có thể dùng reservation/hold có expiry hoặc thao tác atomic để kiểm soát race.

## 14. Observability và xử lý sự cố

Không nên chỉ ghi “upload failed”. Theo dõi bằng uploadId/correlation ID, không log URL ký hoặc bytes nhạy cảm.

| Metric | Ý nghĩa | Phát hiện |
|---|---|---|
| Upload initiation rate | Tốc độ tạo phiên | Spike/abuse |
| Active upload sessions | Phiên đang mở | Session mồ côi |
| Upload completion rate | Tỷ lệ hoàn tất | Lỗi mạng, quota, client |
| Bytes uploaded / throughput | Lưu lượng và tốc độ | Bottleneck |
| Part retry count | Số part retry | Mạng không ổn định |
| Checksum mismatch count | Digest không khớp | Lỗi truyền/payload |
| Session age / expired count | Tuổi và phiên hết hạn | Upload bỏ dở |
| Incomplete multipart bytes | Dữ liệu tạm | Chi phí rò rỉ |
| Malware scan latency/failure | Độ trễ pipeline kiểm tra | Tắc nghẽn scan |
| Signed URL issuance/denial | Link cấp/bị từ chối | Quyền/quota bất thường |
| Download range/egress | Byte tải và tải lặp | Chi phí/hiệu năng |

Quy trình điều tra upload:
1. Xác định user/tenant, uploadId và thời gian.
2. Kiểm tra session, object key và storage upload ID.
3. Truy vấn trạng thái part/offset đã được storage xác nhận.
4. Kiểm tra error code, request ID của provider và network/browser log đã redacted.
5. Kiểm tra checksum, size và complete condition.
6. Xác minh quota, IAM/SAS, signature expiry, CORS và DNS.
7. Resume part hợp lệ; retry có backoff part lỗi tạm thời.
8. Nếu session không phục hồi được, abort/expire và tạo phiên mới theo idempotency.
9. Đối soát object đã complete chưa trước khi retry complete.
10. Ghi nguyên nhân, byte truyền lại và chi phí.

Với download 403, kiểm tra user auth → quyền file/tenant → state object → expiry/method → signature/header → IAM/storage policy → CDN/cache → DNS/network. Không kéo dài expiry máy móc mà chưa xác định nguyên nhân.

## 15. Khôi phục, versioning và vòng đời object

Object storage có thể hỗ trợ versioning, replication, retention lock và lifecycle rule. Các tính năng này hỗ trợ phục hồi nhưng cũng tăng dung lượng và yêu cầu quản trị.

Cần xác định:
- Object có được ghi đè hay mỗi upload tạo version mới?
- Có giữ bản cũ để rollback/audit không?
- Delete marker có khác xóa vật lý không?
- Retention compliance có ngăn xóa không?
- Replication sao chép object version và metadata nào?
- Backup/restore có giữ ACL, tags, encryption key reference và ownership không?
- Cleanup multipart dở đã được cấu hình riêng chưa?

Signed URL có thể trỏ tới object key hoặc version cụ thể tùy provider. Nếu key bị ghi đè, link cũ có thể trả nội dung mới theo semantics; cân nhắc key immutable/versioned cho dữ liệu quan trọng.

## 16. Đánh đổi theo Well-Architected

| Khía cạnh | Lợi ích | Rủi ro/chi phí | Bằng chứng |
|---|---|---|---|
| **Độ tin cậy** | Multipart/resume, checksum, retry từng phần | Session hỏng, complete timeout, part mất hoặc URL hết hạn | Resume test, checksum, recovery drill |
| **Bảo mật** | Signed URL scope hẹp, private storage, quarantine | URL rò rỉ, overwrite, file độc hại | IAM review, redaction, malware scan, negative test |
| **Hiệu năng** | Direct upload, streaming, parallel part và CDN | Nhiều connection, chunk không phù hợp, throttling | Throughput, p95 completion, retry |
| **Chi phí** | Không proxy byte không cần thiết; dọn incomplete upload | Egress, CDN, request, scan và version storage | Storage inventory, abandoned bytes, cost/GB |
| **Vận hành** | Session state, owner, alert và runbook | Session mồ côi, khó đối soát sau timeout | Session dashboard, request IDs, runbook drill |
| **Bền vững** | Retry theo phần giảm truyền lại toàn file; lifecycle dọn dữ liệu tạm | Lưu nhiều bản và scan quá mức | Object age, retention, lifecycle metrics |

Các đánh đổi:
- Proxy upload kiểm soát tập trung nhưng tiêu thụ compute/network backend.
- Direct upload mở rộng tốt nhưng URL capability và object lifecycle cần quản lý.
- Chunk nhỏ giảm lượng retry nhưng tăng request/metadata.
- Nhiều part song song tăng throughput nhưng có thể gây congestion.
- Expiry ngắn giảm cửa sổ rò rỉ nhưng có thể làm upload mạng chậm thất bại.
- Versioning hỗ trợ phục hồi nhưng tăng storage cost.
- Scan trước công bố tăng an toàn nhưng tạo độ trễ.

Không có chunk size, expiry hoặc retention phù hợp mọi hệ thống. Đo theo kích thước file, mạng client, Region, SDK và SLO thực tế.

## 17. Quy trình thiết kế và ADR

Quy trình tham khảo:
1. Xác định kích thước file, số upload đồng thời, mạng client, loại dữ liệu và SLA.
2. Chọn proxy streaming hay direct-to-object-storage.
3. Chọn multipart/resumable protocol theo SDK/provider.
4. Thiết kế bucket/container, key, metadata, versioning và quarantine.
5. Thiết kế authorization, signed URL/SAS, expiry, method, key, tenant và quota.
6. Thiết kế session persistence, part reconciliation, idempotency, retry và abort.
7. Thiết kế checksum, file validation và malware scan.
8. Thiết kế download, Range, CDN/cache và phương án revoke.
9. Thiết kế cleanup, retention, versioning và deletion.
10. Thiết kế metric, log redaction, alert, runbook và owner.
11. Kiểm thử file lớn, mạng gián đoạn, URL hết hạn, quota, duplicate complete và access chéo tenant.

### ADR minh họa — Direct multipart upload

> **Bối cảnh:** Người dùng tải hồ sơ lên tới 5 GB. Backend đang proxy byte và timeout khi tải cao.
>
> **Phương án A:** Tiếp tục proxy streaming và tăng timeout/compute. Dễ giữ luồng qua backend nhưng tốn compute/network và khó mở rộng tải đồng thời.
>
> **Phương án B:** Cấp multipart upload có thời hạn tới object storage. Backend giữ metadata/session và xác minh object khi complete. Client retry từng part.
>
> **Quyết định minh họa:** Chọn B vì workload chủ yếu truyền byte và storage hỗ trợ multipart. Backend làm control plane cho quyền, quota, session và state.
>
> **Đánh đổi:** Phải quản lý session, URL bearer capability, incomplete part cleanup, CORS, checksum và quarantine.
>
> **Kiểm chứng:** Upload qua mạng bị ngắt, resume sau reload, gửi complete hai lần, checksum sai, URL hết hạn, user khác thử dùng URL và upload vượt quota.
>
> **Điều kiện xem xét lại:** Nếu phải biến đổi nội dung trong luồng hoặc compliance yêu cầu mọi byte qua gateway, đánh giá proxy/processing pipeline.

## 18. Bài tập thực hành: nền tảng tải video hồ sơ

Một nền tảng đặt chỗ cho phép chủ tài sản tải video tối đa 3 GB. Người dùng truy cập từ mạng di động không ổn định. Backend Java đang nhận file qua REST rồi chuyển tới object storage. Request thường timeout sau 20 phút và người dùng phải bắt đầu lại. Link download được lưu trong database và tồn tại lâu dài. Tệp mới được hiển thị ngay mà không quét.

**Yêu cầu:**
1. Xác định bottleneck và rủi ro trong proxy upload hiện tại.
2. Đề xuất direct multipart hoặc resumable upload.
3. Thiết kế API create session, cấp URL, list parts/status, complete và abort.
4. Mô tả resume sau khi browser restart mà không tin tiến độ local.
5. Xác định checksum, file validation và quarantine state.
6. Thay link download dài hạn bằng cơ chế truy cập có thời hạn; nêu cách revoke tức thời.
7. Thiết kế quota, expiry và cleanup session bỏ dở.
8. Xây dựng metric, alert và test cho lỗi mạng, URL hết hạn, duplicate complete, checksum mismatch và access chéo tenant.

### Hướng giải quyết

- Tách backend khỏi đường truyền byte; API tạo session và cấp URL có quyền hẹp tới object key do server quyết định.
- Dùng multipart/resumable API; lưu upload ID, part number, checksum và expiry.
- Khi browser khởi động lại, gọi API lấy trạng thái authoritative từ storage rồi tiếp tục các part chưa được xác nhận.
- Complete phải idempotent; nếu response timeout, truy vấn trạng thái object/session trước khi gửi lại.
- Upload vào quarantine; kiểm tra size, checksum, file signature và malware trước khi chuyển sang trạng thái cho phép download.
- Backend xác thực user/quyền file rồi cấp signed download URL ngắn hạn. Nếu cần thu hồi tức thời, cân nhắc proxy/authorized gateway hoặc tokenized CDN có revoke; URL thuần không nhất thiết thu hồi được từng link.
- Giới hạn session, dung lượng hold, concurrency, part size và expiry; cấu hình lifecycle abort incomplete uploads.
- Quan sát completion rate, bytes, part retry, oldest session age, incomplete bytes, checksum mismatch, scan latency và URL denial.
- Kiểm thử cả trường hợp object đã complete nhưng client không nhận response; tránh tạo object duplicate hoặc chạy workflow hai lần.

### Câu hỏi tự kiểm tra

1. Vì sao direct upload giảm tải backend nhưng không loại bỏ trách nhiệm authorization?
2. Multipart upload khác gì resumable ở cấp ứng dụng?
3. Vì sao phải đối chiếu server/storage progress sau reconnect?
4. ETag có luôn là MD5 của object hoàn chỉnh không?
5. Signed URL có phải one-time URL không? Khi nào có thể revoke?
6. Vì sao CORS không phải authorization?
7. Vì sao phải quarantine object trước khi công bố?
8. Range request giúp tiếp tục download thế nào và vì sao cần validator khi object thay đổi?
9. Incomplete multipart gây chi phí gì và cleanup nên đặt ở lớp nào?
10. Nếu complete timeout sau khi storage đã tạo object, client/server cần làm gì?

Một kiến trúc truyền tệp lớn đáng tin cậy kết hợp **upload protocol có thể tiếp tục, xác minh tính toàn vẹn, quyền ghi/đọc giới hạn theo thời gian và quy trình vòng đời object rõ ràng**. Multipart/resumable giúp phục hồi theo từng phần; signed URL giảm tải backend nhưng phải được coi là capability cần bảo vệ; checksum, quarantine, idempotency, cleanup và observability biến luồng truyền byte thành quy trình lưu trữ an toàn có thể vận hành.
