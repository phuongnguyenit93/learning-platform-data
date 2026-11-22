# Xử lý tệp tải lên theo sự kiện

## 1. Bài toán kiến trúc

Trong ứng dụng đám mây, nhận tệp từ người dùng thường chỉ là bước đầu. Sau khi tệp được lưu, hệ thống có thể phải kiểm tra định dạng, quét mã độc, tạo ảnh thu nhỏ, trích xuất nội dung, phân loại tài liệu, ghi chỉ mục tìm kiếm hoặc thông báo cho các dịch vụ khác. Nếu thực hiện toàn bộ những công việc này trong một yêu cầu HTTP, người dùng phải chờ lâu, dễ gặp timeout và hệ thống khó hấp thụ các đợt tải lên đột biến.

**Xử lý tệp tải lên theo sự kiện** (*event-driven file upload processing*) tách việc **tiếp nhận tệp** khỏi việc **xử lý tệp**: kho lưu trữ đối tượng phát ra sự kiện khi có đối tượng mới; thành phần trung gian chuyển sự kiện đến hàng đợi bền vững; một hoặc nhiều worker lấy công việc từ hàng đợi và xử lý bất đồng bộ. Đây là một **mẫu kiến trúc tham chiếu**, không phải một cấu hình duy nhất áp dụng cho mọi hệ thống.

Trong phạm vi **CLOUD_ARCHITECTURE**, mẫu này minh họa cách đi từ yêu cầu nghiệp vụ đến lựa chọn **mạng, compute, dữ liệu và mô hình triển khai**; đồng thời đánh giá những đánh đổi về **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành** theo tư duy **Well-Architected**.

**Tình huống xuyên suốt:** một hệ thống quản lý chứng từ cho phép khách hàng tải PDF, ảnh hóa đơn và ảnh biên nhận. Người dùng cần biết ngay rằng tệp đã được nhận; quá trình quét an toàn, tạo bản xem trước và trích xuất thông tin có thể diễn ra sau. Một tệp lỗi không được làm chặn các tệp khác, và một sự kiện bị gửi lặp không được tạo nhiều chứng từ.

### Chuyển yêu cầu nghiệp vụ thành tiêu chí đo được

Các số dưới đây **chỉ là giả định minh họa** để thực hành thiết kế, không phải giới hạn mặc định của bất kỳ nhà cung cấp nào.

| Nhóm yêu cầu | Ví dụ yêu cầu | Hệ quả kiến trúc |
|---|---|---|
| Chức năng | Nhận PDF, PNG, JPEG tối đa 25 MB; hiển thị trạng thái từng tệp | API tạo phiên tải lên, lưu metadata và cung cấp API trạng thái |
| Trải nghiệm | Phản hồi tạo phiên tải lên dưới 500 ms ở phân vị p95 | Không đưa quét mã độc hoặc chuyển đổi tệp vào đường xử lý đồng bộ |
| Độ trễ | 95% tệp hợp lệ sẵn sàng sử dụng trong 2 phút kể từ khi tải lên hoàn tất | Hàng đợi, worker tự mở rộng, cảnh báo độ tuổi công việc |
| Tin cậy | Không bỏ sót tệp đã nhận, không tạo kết quả nghiệp vụ lặp | Hàng đợi bền vững, xử lý lặp an toàn, tác vụ đối soát |
| Bảo mật | Mỗi khách hàng chỉ truy cập tệp của mình; tệp chưa quét không được công khai | Phân quyền theo tenant, kho riêng tư, cách ly tệp thô và tệp đã kiểm duyệt |
| Dữ liệu | Lưu bản gốc 30 ngày; có nhật ký thao tác và chính sách xóa | Lifecycle policy, metadata bền vững, nhật ký kiểm toán |
| Vận hành | Phát hiện lỗi xử lý và khôi phục được công việc mắc kẹt | Metrics, tracing, dead-letter queue và quy trình replay |

Điều cần phân biệt là **thành công của thao tác upload** và **thành công của xử lý nghiệp vụ**. HTTP trả về thành công khi tệp đã được lưu không có nghĩa tệp đã được quét hoặc sẵn sàng phục vụ. Giao diện và API nên thể hiện rõ hai mốc này.

## 2. Kiến trúc tham chiếu

~~~mermaid
flowchart LR
    U["Ứng dụng người dùng"] -->|"1. Xin phiên upload"| API["API xác thực và cấp URL"]
    API -->|"Tạo phiên"| DB[("CSDL metadata")]
    API -->|"2. URL có thời hạn"| U
    U -->|"3. Upload trực tiếp"| RAW[("Object storage: vùng raw")]
    RAW -->|"4. Object created"| BUS["Sự kiện / Event bus"]
    BUS --> Q[["Hàng đợi bền vững"]]
    Q -->|"5. Nhận công việc"| W["Worker xử lý"]
    W -->|"Kiểm tra, quét, chuyển đổi"| W
    W -->|"6a. Tệp đạt yêu cầu"| SAFE[("Object storage: vùng trusted")]
    W -->|"6b. Tệp không hợp lệ"| QUAR[("Vùng quarantine")]
    W -->|"Cập nhật trạng thái"| DB
    DB --> OUT["Outbox / thông báo trạng thái"]
    OUT --> APP["Dịch vụ thông báo / tra cứu"]
    Q -.->|"Hết số lần thử"| DLQ[["Dead-letter queue"]]
~~~

Đây là luồng **đề xuất cho tải trực tiếp từ client lên object storage**. Nếu mạng hoặc yêu cầu kiểm soát buộc tệp đi qua máy chủ ứng dụng, có thể dùng upload proxy/streaming, nhưng phải tính thêm băng thông, năng lực mở rộng và điểm lỗi của tầng API.

### Trình tự xử lý

1. **Khởi tạo phiên.** Client gọi API đã xác thực, khai báo tên tệp, kích thước và loại nội dung dự kiến. API kiểm tra quota/quyền truy cập, sinh **uploadId** và **object key** không đoán được, lưu phiên ở trạng thái **INITIATED**.
2. **Cấp quyền tải tệp ngắn hạn.** API trả URL ký sẵn hoặc thông tin upload có phạm vi hẹp. Tùy cơ chế của dịch vụ lưu trữ, có thể ràng buộc phương thức, object key, hạn sử dụng, loại nội dung hoặc giới hạn dung lượng; các ràng buộc mà nhà cung cấp không hỗ trợ phải được **kiểm tra lại phía máy chủ**.
3. **Lưu bản gốc.** Client truyền byte trực tiếp đến vùng **raw** riêng tư. Với tệp lớn, có thể dùng multipart/resumable upload; chỉ xem tệp là hoàn tất sau sự kiện hoàn thành tương ứng, không xử lý từng phần chưa ghép.
4. **Phát và chuyển sự kiện.** Object storage phát tín hiệu tạo đối tượng. Event bus có thể định tuyến theo loại sự kiện, bucket hoặc prefix; **hàng đợi bền vững** giữ công việc khi worker chậm, tạm ngừng hoặc tăng tải.
5. **Worker nhận và xác minh.** Worker kiểm tra sự kiện, lấy metadata thực tế của đối tượng, tìm phiên upload khớp, giành quyền xử lý theo cơ chế chống trùng, rồi kiểm tra chữ ký định dạng, kích thước, mã độc và nội dung theo chính sách.
6. **Ghi kết quả.** Tệp đạt yêu cầu được chuyển sang vùng **trusted** hoặc sinh các tệp phái sinh; tệp vi phạm chính sách được từ chối hoặc cách ly. Metadata chuyển sang trạng thái cuối thích hợp; sự kiện nghiệp vụ như **FileReady** chỉ phát sau khi trạng thái bền vững đã được ghi.
7. **Đọc trạng thái.** Client gọi API theo **uploadId** hoặc nhận thông báo để thấy **AVAILABLE**, **REJECTED** hay **FAILED**. URL tải xuống do backend cấp theo quyền người dùng, không mở công khai vùng raw.

**Vai trò các thành phần:** *event bus* hữu ích cho lọc/định tuyến đến nhiều đích; *queue* hữu ích cho lưu đệm, phân phối công việc và retry. Với luồng đơn giản, thông báo từ object storage có thể đi **thẳng vào queue**, không bắt buộc có cả hai lớp. Cần đối chiếu khả năng tích hợp thực tế của dịch vụ cloud được chọn.

## 3. Ranh giới dữ liệu và hợp đồng sự kiện

### Chia vùng lưu trữ

| Vùng | Vai trò | Chính sách gợi ý |
|---|---|---|
| **raw** | Nhận byte chưa được xác minh từ client | Private, mã hóa, giới hạn quyền đọc, lifecycle cho tệp bỏ dở |
| **quarantine** | Giữ tệp bị nghi ngờ để điều tra hoặc xử lý theo chính sách | Cách ly chặt, chỉ nhóm/quy trình được cấp quyền mới đọc |
| **trusted/processed** | Chứa bản đã qua kiểm tra hoặc kết quả chuyển đổi | Chỉ ứng dụng được phép phục vụ; phân quyền tải xuống theo tenant |
| **metadata DB** | Chứa uploadId, chủ sở hữu, object version, trạng thái, kết quả và thời điểm | Cập nhật có điều kiện, chỉ mục theo tenant/trạng thái, backup |

Tách bucket hoặc prefix của **raw** và **processed** giúp tránh vòng lặp kiểu “worker tạo ảnh thu nhỏ → sự kiện tạo tệp mới → lại chạy worker”. Nếu dùng chung bucket, phải lọc sự kiện theo prefix/tag đáng tin cậy và kiểm tra lại trong worker.

Một event từ kho lưu trữ chỉ nên được xem như **tín hiệu cần kiểm chứng**. Đặc biệt, không lấy tên tệp hoặc tenantId do client tự khai để quyết định quyền truy cập; worker phải đối chiếu object key với phiên đã được API cấp. Không để payload của event chứa URL truy cập dài hạn hoặc dữ liệu bí mật.

Ví dụ sự kiện **chuẩn hóa bên trong hệ thống** (không phải cấu trúc gốc cố định của AWS, Azure hoặc GCP):

~~~json
{
  "eventType": "object.created",
  "eventId": "evt-9f2c",
  "occurredAt": "2026-11-18T09:00:00Z",
  "bucket": "documents-raw",
  "objectKey": "tenant-42/uploads/u-123/source.pdf",
  "objectVersion": "v-008",
  "uploadId": "u-123",
  "correlationId": "trace-7a1d"
}
~~~

**objectVersion** trong ví dụ là định danh phiên bản được hệ thống lưu trữ cung cấp hoặc một định danh bất biến tương đương. Không phải dịch vụ/cấu hình nào cũng bật versioning. Nếu không có version ID, dùng **object key duy nhất cho mỗi lần upload**, ngăn ghi đè và xác minh metadata để bảo toàn danh tính đầu vào. **ETag** không luôn là checksum nội dung đáng tin cậy, đặc biệt với multipart upload hoặc cơ chế mã hóa; cần checksum chuyên dụng khi nghiệp vụ yêu cầu kiểm tra toàn vẹn.

### Metadata và trạng thái

Một bản ghi metadata có thể chứa:

~~~json
{
  "uploadId": "u-123",
  "tenantId": "tenant-42",
  "createdBy": "user-7",
  "rawKey": "tenant-42/uploads/u-123/source.pdf",
  "objectVersion": "v-008",
  "status": "PROCESSING",
  "attemptCount": 2,
  "processedKey": null,
  "errorCode": null,
  "createdAt": "2026-11-18T08:59:30Z",
  "updatedAt": "2026-11-18T09:00:08Z"
}
~~~

~~~mermaid
stateDiagram-v2
    [*] --> INITIATED
    INITIATED --> UPLOADED: Nhận tệp hoàn chỉnh
    INITIATED --> EXPIRED: Quá hạn
    UPLOADED --> PROCESSING: Claim thành công
    PROCESSING --> AVAILABLE: Xử lý xong
    PROCESSING --> REJECTED: Vi phạm chính sách
    PROCESSING --> RETRY_PENDING: Lỗi tạm thời
    RETRY_PENDING --> PROCESSING: Thử lại
    RETRY_PENDING --> FAILED: Hết khả năng phục hồi
    AVAILABLE --> [*]
    REJECTED --> [*]
    FAILED --> [*]
    EXPIRED --> [*]
~~~

Chỉ cho phép các **chuyển trạng thái hợp lệ** bằng cập nhật có điều kiện (*compare-and-set* hoặc transaction). Một sự kiện cũ đến muộn không được chuyển **AVAILABLE** về **PROCESSING**. **FAILED** là trạng thái lỗi sau khi đã hết chính sách retry; lỗi tạm thời vẫn thuộc **RETRY_PENDING**. Các trạng thái cuối chỉ mở lại bằng quy trình replay có kiểm soát, lưu lịch sử thao tác.

## 4. Bảo đảm đúng khi sự kiện trùng, chậm hoặc sai thứ tự

Nhiều cơ chế thông báo và hàng đợi trên cloud cung cấp hành vi **ít nhất một lần** (*at-least-once*): cùng một sự kiện hoặc cùng một công việc có thể được phát lại. Việc giao nhận cũng có thể không bảo đảm thứ tự. Vì vậy, kiến trúc không nên dựa vào giả định “mỗi file chính xác một event”.

### Thiết kế xử lý lặp an toàn

- **Khóa nghiệp vụ:** kết hợp **uploadId + objectVersion + loại tác vụ**, hoặc một khóa bất biến tương đương; không dùng riêng **eventId** vì hai sự kiện khác ID vẫn có thể nói về cùng đối tượng.
- **Chiếm quyền xử lý nguyên tử:** ghi một hàng công việc có unique constraint hoặc update có điều kiện. Chỉ worker đang giữ **lease** còn hạn mới được thực hiện bước xử lý chủ đạo.
- **Lease và fencing token:** khi worker treo, lease hết hạn cho phép worker khác tiếp quản; token tăng dần ngăn worker cũ ghi trạng thái cuối sau khi đã mất quyền.
- **Đầu ra ổn định:** xác định **processedKey** từ danh tính công việc để retry không tạo nhiều bản xuất khác nhau. Việc ghi đối tượng và cập nhật DB là hai hệ thống riêng; cần idempotency hoặc đối soát khi một bước thành công và bước còn lại thất bại.
- **Xác nhận message sau cùng:** chỉ ACK/xóa message khỏi queue sau khi kết quả cần thiết đã được ghi bền vững. Nếu ACK trước, worker có thể chết và mất công việc; nếu ACK sau, phải chịu được message bị giao lại.

Pseudocode sau biểu diễn ý tưởng điều phối, không ràng buộc một SDK cụ thể:

~~~text
on_object_created(event):
    session = database.find_by_upload_id(event.uploadId)
    source = object_storage.head(event.bucket, event.objectKey, event.objectVersion)
    verify_session_owner_key_and_size(session, source)

    job_key = (session.uploadId, source.version_or_immutable_key, "scan-and-transform")
    claim = database.try_claim_job(job_key, lease_with_fencing_token)
    if claim.already_completed:
        acknowledge_message()
        return
    if not claim.acquired:
        retry_later()
        return

    result = validate_scan_and_transform(source)
    write_result_to_deterministic_key(result)
    database.commit_result_if_token_current(claim.token, result)
    database.append_outbox_event_in_same_transaction("FileReady", session.uploadId)
    acknowledge_message()
~~~

Trong triển khai thật, **REJECTED** có kết quả và event riêng, còn lỗi tạm thời phải cho queue retry. Việc quét, chuyển đổi và ghi object nên có timeout, giới hạn bộ nhớ và kiểm soát tài nguyên. Nếu công việc dài hơn **visibility timeout** của queue, cần gia hạn lease/visibility hoặc thiết kế công việc thành những bước nhỏ. Cũng phải tính tình huống worker mất lease **ngay trong lúc ghi ra storage**: token bảo vệ cập nhật DB, còn tên object đầu ra bất biến hoặc cơ chế ghi có điều kiện giúp hạn chế tác dụng phụ.

### Tránh “đã ghi DB nhưng chưa gửi event”

Nếu worker cập nhật **AVAILABLE** rồi chết trước khi phát **FileReady**, các dịch vụ phụ thuộc có thể không nhận được tín hiệu. Mẫu **transactional outbox** xử lý điểm gãy này:

1. Trong **cùng transaction DB**, ghi trạng thái mới và một bản ghi outbox.
2. Một publisher riêng đọc outbox, gửi event tới broker rồi đánh dấu đã gửi.
3. Publisher có thể gửi trùng khi retry; consumer của **FileReady** cũng phải idempotent.

Không thể giả định transaction nguyên tử xuyên qua object storage, database và event bus chỉ vì từng dịch vụ riêng lẻ có transaction. Cần phối hợp các bước bằng trạng thái, đối soát và thao tác lặp an toàn.

### Khi mất sự kiện

Ngoài xử lý trực tiếp từ queue, một **reconciliation job** chạy định kỳ có thể tìm các phiên **INITIATED** đã quá hạn, các đối tượng raw chưa có job hoặc các job **PROCESSING** quá lâu; sau khi kiểm tra dữ liệu thực, nó tạo lại tác vụ hoặc đánh dấu **EXPIRED/FAILED** theo chính sách. Cơ chế này giúp phục hồi sai sót tích hợp, lỗi cấu hình thông báo hoặc sự cố hiếm gặp; cần bảo vệ để bản thân tác vụ đối soát không tạo trùng.

## 5. Xử lý lỗi, retry và dead-letter queue

Lỗi cần được phân loại theo **có thể thử lại** và **không thể thử lại**. Mọi lỗi đều retry sẽ gây tốn chi phí và tạo hàng đợi độc (*poison messages*); mọi lỗi đều từ bỏ ngay sẽ làm giảm độ tin cậy.

| Tình huống | Phân loại | Xử lý đề xuất |
|---|---|---|
| Storage/DB tạm thời trả timeout hoặc throttling | Tạm thời | Retry theo *exponential backoff* có jitter; giới hạn số lần và thời gian |
| Tệp sai định dạng thực, vượt kích thước, chứa nội dung bị cấm | Nghiệp vụ/vĩnh viễn | Ghi **REJECTED** kèm mã lỗi an toàn, xử lý quarantine/xóa theo chính sách; không retry vô hạn |
| Worker chết khi đang chạy | Tạm thời | Message xuất hiện lại sau visibility timeout; tiếp quản lease và xử lý idempotent |
| Sự kiện không có phiên upload hợp lệ | Nghi ngờ/bất thường | Không tự tin xử lý; ghi log có cấu trúc, cảnh báo nếu vượt ngưỡng, xử lý theo chính sách bảo mật |
| Công việc luôn lỗi sau số lần thử cho phép | Cần can thiệp | Chuyển **DLQ**, ghi metadata lỗi và cho phép replay có kiểm soát |
| Đã tạo bản processed nhưng chưa cập nhật DB | Trạng thái từng phần | Retry với khóa đầu ra ổn định, kiểm tra hiện trạng rồi hoàn tất transaction |
| Queue tăng nhanh do worker không đủ năng lực | Quá tải | Tăng worker theo backlog/age, giới hạn concurrency đến DB và dịch vụ phụ thuộc |

**DLQ không phải kho lưu trữ vô thời hạn.** Cần quy định retention, quyền truy cập, cảnh báo độ sâu DLQ, quy trình tìm nguyên nhân và replay an toàn. Khi replay, dùng lại khóa idempotency, lưu thông tin ai hoặc hệ thống nào thực hiện, không phát sinh bản ghi nghiệp vụ thứ hai.

## 6. Bảo mật từ đầu đến cuối

Object storage cho upload trực tiếp giảm tải máy chủ, nhưng URL ký sẵn là **quyền truy cập tạm thời**: ai sở hữu URL có thể dùng quyền mà URL đó cho phép đến khi hết hạn hoặc bị thu hồi theo khả năng của nền tảng.

**Thiết kế phòng vệ nhiều lớp:**

1. **Xác thực và ủy quyền tại API:** kiểm tra tenant, user, quota, số phiên đang mở; server tự sinh object key. Không nhận đường dẫn tuỳ ý do client cung cấp rồi ký.
2. **Giới hạn upload:** URL/token có thời hạn ngắn và phạm vi hẹp; kiểm soát dung lượng và loại nội dung bằng policy được storage hỗ trợ, sau đó kiểm tra lại kích thước và *magic bytes* của tệp. HTTP **Content-Type** và phần mở rộng tên tệp chỉ là dữ liệu khai báo, không đủ tin cậy.
3. **Lưu trữ riêng tư:** chặn truy cập public, mã hóa khi truyền và khi lưu, cấu hình KMS/khóa khi cần, áp dụng chính sách vòng đời và tối thiểu quyền IAM. Worker chỉ cần đọc raw, ghi processed và cập nhật metadata trong phạm vi của mình.
4. **Cách ly nội dung chưa tin cậy:** quét mã độc trước khi cho người dùng khác tải xuống; xử lý chuyển đổi tài liệu trong môi trường hạn chế quyền, bộ nhớ, CPU, thời gian chạy, mạng ra ngoài và dung lượng giải nén. Chống *zip bomb*, payload kích thước lớn và parser dễ bị khai thác.
5. **Phân quyền đầu ra:** chỉ phục vụ đối tượng vùng trusted sau khi trạng thái đủ điều kiện; cấp quyền tải xuống ngắn hạn, kiểm tra tenant ở backend; không lộ raw key nhạy cảm trong URL/log công khai.
6. **Bảo vệ dữ liệu cá nhân:** lựa chọn region theo yêu cầu lưu trú dữ liệu, thời gian giữ tệp/metadata/log và quy trình xóa; không log nội dung file, URL ký sẵn hay token. Dùng audit log để truy xuất ai đã tải, xem hoặc xóa.
7. **Xác thực nguồn event:** chỉ chấp nhận từ luồng event/queue được cấp quyền; đối chiếu object metadata và phiên upload trước mọi thao tác. Bật giám sát thay đổi cấu hình bucket và quyền truy cập.

Không nên đánh dấu tệp là **AVAILABLE** chỉ vì upload thành công. Tệp chưa quét phải nằm ngoài đường phục vụ công khai, kể cả khi CDN hoặc dịch vụ xử lý phía sau hoạt động không ổn định.

## 7. Lựa chọn network, compute và dữ liệu

### Network và đường đi của byte

- **Upload trực tiếp:** client gửi tệp qua HTTPS đến dịch vụ lưu trữ, API chỉ xử lý xác thực/metadata. Lợi ích là giảm băng thông máy chủ ứng dụng, ít cần autoscale tầng API theo kích thước tệp.
- **Upload qua API/gateway:** thích hợp khi bắt buộc kiểm tra trực tuyến, có gateway quản lý riêng hoặc yêu cầu tích hợp đặc thù. Đổi lại tăng số hop, chi phí lưu lượng và nguy cơ timeout; cần cơ chế streaming thay vì giữ cả file trong RAM.
- **Đường worker đến storage/DB:** ưu tiên private endpoint hoặc cơ chế truy cập mạng riêng khi phù hợp; hạn chế truy cập Internet ra ngoài, phân tách subnet và security policy. Không giả định rằng đưa worker vào VPC tự động làm mọi lưu lượng đi riêng tư.
- **CDN cho download:** chỉ dùng cho tệp đã được phép phục vụ, với kiểm soát truy cập, cache-control và chiến lược vô hiệu hóa cache phù hợp.

### Compute cho worker

| Cách chạy | Phù hợp | Đánh đổi |
|---|---|---|
| **Function/serverless** | Tác vụ ngắn, độc lập, lưu lượng thay đổi mạnh | Giới hạn thời gian/bộ nhớ/runtime, cold start, cần kiểm soát concurrency |
| **Container worker** | Quét/chuyển đổi dùng thư viện native, tác vụ dài, cần tài nguyên tùy chỉnh | Phải điều phối triển khai, autoscaling, vá image và quan sát runtime |
| **Workflow orchestrator** | Nhiều bước có trạng thái, nhánh xử lý, phê duyệt hoặc chờ bên ngoài | Thêm dịch vụ và chi phí điều phối; không thay thế idempotency |
| **Batch/job system** | Xử lý theo lô khối lượng lớn, ít yêu cầu realtime | Có thể tăng thời gian chờ và độ phức tạp của điều phối lô |

Compute phải được chọn theo **thời gian xử lý p95/p99, kích thước file, thư viện, nhu cầu CPU/RAM/GPU, quota, concurrency và chi phí**, không chỉ dựa trên tên dịch vụ quen thuộc. Tác vụ CPU nặng như OCR có thể tách thành queue riêng để không làm chậm tác vụ tạo thumbnail.

### Dữ liệu và điều phối

**Object storage** thích hợp cho byte của tệp vì độ bền, chi phí lưu lớn và lifecycle; **CSDL giao dịch** lưu phiên upload, owner, trạng thái và quyền truy cập; **queue** lưu công việc đang chờ. Không nên nhét cả tệp vào payload event, message queue hoặc bảng metadata.

Nếu ứng dụng có nhu cầu tìm kiếm nội dung, worker có thể ghi sang **search index** sau xử lý; search index là projection có thể tái tạo, không phải nguồn sự thật cho trạng thái upload. Khi số lượng sự kiện và loại xử lý tăng, cân nhắc tách các consumer cho antivirus, OCR và indexing với định nghĩa rõ bước nào bắt buộc để chuyển sang **AVAILABLE**.

## 8. Khả năng mở rộng và ước lượng chi phí

Hàng đợi cho phép worker xử lý theo năng lực hiện có và hấp thụ tải tăng đột biến. Tuy nhiên, queue chỉ **đệm** tải: nếu tốc độ đến cao hơn tốc độ phục vụ trong thời gian dài, độ trễ và backlog sẽ tăng.

Ước lượng năng lực sơ bộ:

~~~text
arrival_rate = số tệp đến mỗi giây
processing_time = số giây worker bận cho một tệp (trung bình)
concurrency_tối_thiểu ≈ arrival_rate × processing_time
throughput_ước_tính ≈ số_worker_đồng_thời / processing_time
~~~

Ví dụ, đỉnh tải **1.200 tệp/phút = 20 tệp/giây** và thời gian xử lý trung bình **6 giây/tệp** đòi hỏi khoảng **120 lượt xử lý đồng thời** để theo kịp lưu lượng trung bình. Dự phòng 25% cho biến động cho khoảng **150 concurrency**, với điều kiện DB, storage, antivirus và quota đều hỗ trợ. Phép tính từ định luật Little chỉ là điểm khởi đầu; phải kiểm thử bằng phân bố kích thước tệp, thời gian xử lý thực tế, p95/p99, giới hạn tài nguyên và retry.

Với tải thô **100.000 tệp/ngày**, trung bình **8 MB/tệp**, giữ **30 ngày**, dung lượng bản gốc xấp xỉ **24 TB** theo đơn vị thập phân, chưa tính bản processed, version, bản sao, metadata và overhead. Một pipeline tưởng như “chỉ vài function” có thể phát sinh chi phí lưu trữ đáng kể.

**Các nhóm chi phí phải tính:** lưu trữ theo GB-tháng và tier, yêu cầu PUT/GET/LIST, event/queue, thời gian compute và memory/CPU, OCR/AI nếu có, DB read/write, KMS, logs/metrics, truyền dữ liệu giữa vùng/region và egress cho người dùng. Chi phí phát lại có thể tăng mạnh nếu lỗi khiến file lớn bị quét/chuyển đổi nhiều lần.

**Các đòn bẩy tối ưu:** đặt lifecycle cho raw và bản phái sinh, tránh copy không cần thiết, dùng cùng region cho các thành phần thường trao đổi byte, autoscale theo **tuổi message và backlog trên mỗi worker** (không chỉ CPU), giới hạn retry, cache output bất biến và tách queue theo loại tác vụ. Việc chọn region hoặc tier phải cân bằng chi phí với độ trễ, yêu cầu tuân thủ và khôi phục sự cố.

## 9. Quan sát hệ thống và SLO

Theo dõi đầy đủ đường đi từ phiên upload đến kết quả; mọi log, trace và metric nên có **uploadId**, **correlationId** và loại tác vụ. TenantId dùng cho audit và truy vết có kiểm soát; tránh gắn ID có cardinality cao vào mọi nhãn metric.

| Chỉ số | Ý nghĩa vận hành |
|---|---|
| **Upload completed rate** | Tỷ lệ phiên thực sự tạo được đối tượng hoàn chỉnh |
| **Time-to-available p50/p95/p99** | Thời gian từ lúc object hoàn tất đến khi sẵn sàng sử dụng |
| **Oldest message age / queue backlog** | Worker có đang tụt sau lưu lượng đến hay không |
| **Processing success/reject/failure rate** | Phân biệt lỗi hạ tầng với tệp bị từ chối hợp lệ |
| **Retry count và DLQ depth** | Phát hiện poison messages, lỗi kéo dài hoặc bug mới |
| **Worker duration, throttling, concurrency** | Xác định nghẽn compute, phụ thuộc hoặc quota |
| **Reconciliation gap/stale jobs** | Phát hiện sự kiện thiếu, phiên mắc kẹt hoặc cập nhật dở |
| **Storage volume và egress** | Theo dõi tăng trưởng dữ liệu và chi phí |

Một SLO minh họa: **99% tệp hợp lệ có trạng thái AVAILABLE trong 120 giây sau khi upload hoàn tất**, đo theo cửa sổ 30 ngày. Định nghĩa rõ tệp nào bị loại vì sai chính sách, cách đo mốc bắt đầu/kết thúc và cách tính khi phụ thuộc bên ngoài bị gián đoạn. SLO **khác** với chỉ số “API tạo URL trả về HTTP 200”.

Cảnh báo có ích khi gắn với hậu quả: **oldest message age** gần vượt ngân sách độ trễ; **DLQ depth** tăng không ngừng; worker bị throttling; số phiên **PROCESSING** quá thời hạn; tỷ lệ lỗi hạ tầng tăng. Dashboard nên cho phép đi từ triệu chứng toàn hệ thống đến một **uploadId** cụ thể để điều tra.

## 10. Ánh xạ sang các nền tảng cloud

Tên dưới đây chỉ mang tính định hướng để lựa chọn dịch vụ; cách cấu hình nguồn sự kiện, quota, ordering, retry, mạng riêng và chính sách ký URL **phải đối chiếu tài liệu của nền tảng đang triển khai**.

| Vai trò | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| Lưu byte tệp | Amazon S3 | Azure Blob Storage | Cloud Storage |
| Định tuyến event | S3 Event Notifications / EventBridge | Event Grid | Eventarc / Pub/Sub |
| Hàng đợi bền vững | Amazon SQS | Azure Service Bus / Storage Queue | Pub/Sub |
| Worker | AWS Lambda / ECS Fargate | Azure Functions / Container Apps | Cloud Run / Cloud Run functions |
| Điều phối nhiều bước | AWS Step Functions | Durable Functions | Workflows |
| Metadata | DynamoDB / RDS | Cosmos DB / Azure SQL | Firestore / Cloud SQL |
| Quan sát | CloudWatch / X-Ray | Azure Monitor / Application Insights | Cloud Monitoring / Cloud Trace |

Ví dụ, **S3 → SQS → Lambda** có thể phù hợp cho pipeline ngắn trên AWS; nếu phần OCR dài hoặc cần binary chuyên dụng, có thể dùng container worker. Trên Azure, **Blob Storage → Event Grid → Service Bus → Function/Container Apps** là một biến thể; trên GCP, **Cloud Storage → Pub/Sub/Eventarc → Cloud Run** là một biến thể khác. Chọn thành phần theo chức năng và bảo đảm cần thiết, không cố ghép mọi dịch vụ vào cùng một đường đi.

## 11. Đánh giá theo sáu trụ cột Well-Architected

| Trụ cột | Câu hỏi đánh giá | Biện pháp thường thấy |
|---|---|---|
| **Operational Excellence – Vận hành xuất sắc** | Có thể lần theo một upload, xử lý DLQ và triển khai/rollback an toàn không? | Structured logs, tracing, runbook, IaC, replay và dashboard |
| **Security – Bảo mật** | Tệp chưa kiểm duyệt có thể bị đọc công khai hay vượt ranh giới tenant không? | IAM tối thiểu, bucket private, quét mã độc, mã hóa, kiểm tra quyền |
| **Reliability – Tin cậy** | Worker chết, event lặp hoặc mất event sẽ ảnh hưởng thế nào? | Durable queue, idempotency, retries, DLQ, reconciliation, backup/restore |
| **Performance Efficiency – Hiệu quả hiệu năng** | Pipeline đáp ứng p95 khi tăng gấp nhiều lần lưu lượng không? | Autoscaling theo backlog, chia queue, giới hạn concurrency, benchmark |
| **Cost Optimization – Tối ưu chi phí** | Những byte, lần xử lý hoặc retry nào tạo chi phí không cần thiết? | Lifecycle, tối ưu chuyển vùng, giới hạn retry, phân tầng lưu trữ |
| **Sustainability – Bền vững** | Có sử dụng tài nguyên phù hợp với công việc hay giữ dữ liệu quá lâu không? | Rightsizing, xử lý theo nhu cầu, xóa dữ liệu hết hạn, tránh làm lại vô ích |

Không có một đáp án tối ưu tuyệt đối. Ví dụ, lưu thêm bản sao processed giúp phục vụ nhanh và tách dữ liệu tin cậy, nhưng tăng chi phí lưu trữ; quét đồng bộ trước phản hồi có thể giảm thời gian tồn tại của tệp chưa quét nhưng khiến trải nghiệm tải lên kém và tăng rủi ro timeout. Cần ưu tiên bằng **SLO và rủi ro nghiệp vụ đã thống nhất**.

## 12. Những thiết kế dễ mắc lỗi

| Thiết kế dễ mắc | Hậu quả | Cải thiện |
|---|---|---|
| API chờ OCR và quét hoàn thành mới trả kết quả | Timeout, khó mở rộng, upload thất bại dây chuyền | Trả phiên upload, xử lý bất đồng bộ và theo dõi trạng thái |
| Xem event là duy nhất và luôn đúng thứ tự | Duplicate documents, kết quả bị ghi đè bởi event cũ | Khóa idempotency + chuyển trạng thái có điều kiện |
| Dùng event bus nhưng không có buffer/queue cho worker dễ nghẽn | Mất khả năng hấp thụ đợt tăng tải | Queue bền vững và scale theo backlog |
| Đặt tệp raw và tệp processed cùng trigger không lọc | Vòng lặp event, tăng chi phí | Vùng riêng hoặc lọc sự kiện rõ ràng |
| Tin tên file và Content-Type người dùng gửi | Bỏ lọt tệp độc hại hoặc sai loại | Kiểm tra byte thực, antivirus, sandbox |
| ACK queue trước khi ghi DB/đầu ra | Có thể mất công việc khi worker chết | ACK sau khi trạng thái bền vững; hỗ trợ xử lý lặp |
| Retry vô hạn mọi loại lỗi | DLQ không được xử lý, chi phí không kiểm soát | Phân loại lỗi, backoff+jitter, hạn mức và runbook |
| Chỉ theo dõi lỗi 5xx của API upload | Không thấy file mắc kẹt trong pipeline | Đo end-to-end SLO, queue age, DLQ và reconciliation |

## 13. Bài tập thực hành thiết kế

**Đề bài:** một nền tảng thương mại điện tử cho nhà bán hàng tải ảnh sản phẩm tối đa 15 MB. Hệ thống cần quét mã độc, chuyển ba kích thước ảnh và chỉ công khai ảnh sau khi hoàn tất. Trong một chiến dịch, số lượt tải tăng gấp mười lần trong 15 phút. Yêu cầu dữ liệu ảnh phải lưu ở region được phép và nhà bán hàng chỉ thấy ảnh của mình.

**Hãy thiết kế** sơ đồ thành phần và trả lời:

1. Client tải byte qua API hay trực tiếp lên storage? Vì sao?
2. Dùng sự kiện, hàng đợi và worker ở đâu? Tự mở rộng theo tín hiệu nào?
3. Với hai event trùng và một worker chết sau khi ghi thumbnail, làm sao bảo đảm không tạo hai sản phẩm?
4. Khi tệp bị nhiễm mã độc, trạng thái và quyền truy cập phải thay đổi thế nào?
5. Cần đo chỉ số nào để biết chiến dịch làm vi phạm SLO? Sau chiến dịch xử lý backlog ra sao?

### Phương án tham khảo

Chọn **API cấp URL ngắn hạn → vùng raw private → object-created event → durable queue → worker quét và resize → vùng trusted → DB status và outbox → API/CDN được phân quyền**. API lưu **uploadId, merchantId, rawKey**; worker xác minh chúng với object thực trước khi xử lý. Không cho CDN phục vụ raw.

Với mỗi ảnh, khóa xử lý là **uploadId + objectVersion**; một thao tác DB có điều kiện giành lease. Thumbnail được lưu dưới ba key đầu ra xác định từ khóa đó. Worker sau khi chạy lại sẽ kiểm tra các đầu ra đã có và hoàn tất cập nhật DB, thay vì tạo bản ghi ảnh sản phẩm thứ hai. Event **ImageReady** phát từ outbox; consumer tiếp tục xử lý idempotent.

Worker autoscale theo **backlog/oldest message age**, có giới hạn concurrency để DB và bộ quét không quá tải. Khi không kịp xử lý, queue hấp thụ đỉnh; tính số worker dựa trên tốc độ đến, thời gian resize/scan và ngân sách độ trễ. Tệp bị phát hiện nguy hiểm chuyển **REJECTED**, được cách ly/xóa theo chính sách và không cấp URL công khai. Dashboard theo dõi **time-to-available p95**, số message chờ lâu, DLQ, lỗi scan, chi phí và số phiên chưa kết thúc. Sau đỉnh tải, worker tiếp tục rút backlog đến ngưỡng bình thường rồi giảm quy mô.

**Điểm cần tự kiểm tra:** giải pháp có giải quyết cả *độ đúng* (upload không bị mất/trùng), *độ an toàn* (không lộ tệp chưa kiểm duyệt), *độ trễ* (SLO dưới tải đột biến), *chi phí* (lưu trữ/compute/egress) và *khả năng vận hành* (phát hiện và phục hồi sự cố) hay chưa?

## 14. Checklist trước khi đưa vào vận hành

- [ ] Định nghĩa rõ **upload thành công**, **xử lý thành công**, các trạng thái và SLO.
- [ ] Có quota, URL giới hạn quyền/thời gian và kiểm tra lại kích thước, định dạng thực của đối tượng.
- [ ] Tệp thô riêng tư; quét/cách ly trước khi cấp quyền sử dụng.
- [ ] Object key bất biến hoặc bật versioning; lựa chọn khóa idempotency rõ ràng.
- [ ] Chịu được sự kiện lặp, sai thứ tự, worker chết, message được giao lại.
- [ ] Đặt retry, backoff, DLQ, replay và reconciliation có người chịu trách nhiệm.
- [ ] Xác minh timeout, lease, concurrency và quota của từng thành phần bằng kiểm thử tải.
- [ ] Theo dõi end-to-end latency, backlog age, DLQ, trạng thái mắc kẹt và chi phí.
- [ ] Có backup/restore metadata, lifecycle dữ liệu, IaC và runbook sự cố.
- [ ] Đánh giá kiến trúc theo sáu trụ cột Well-Architected, ghi nhận đánh đổi so với yêu cầu thực.

Khi các điều kiện này được thiết kế rõ, xử lý upload theo sự kiện không chỉ giúp ứng dụng phản hồi nhanh hơn mà còn tạo một pipeline có thể mở rộng, phục hồi, kiểm toán và cải tiến độc lập với luồng tương tác người dùng.
