# Tạo mới, sử dụng, hết hạn, lưu trữ dài hạn và xóa dữ liệu

Một bản ghi NoSQL không chỉ có hai trạng thái “đang tồn tại” và “không tồn tại”. Trong suốt vòng đời, dữ liệu có thể được **tạo mới, xác thực, cập nhật, truy cập thường xuyên, trở nên ít được sử dụng, hết hạn theo chính sách, chuyển sang kho lưu trữ dài hạn, được yêu cầu xóa và cuối cùng được thu hồi ở nhiều nơi**. Những mốc đó có thể diễn ra khác nhau giữa các database, replica, cache, search index, pipeline phân tích và backup.

Ví dụ, một sự kiện IoT chỉ cần hiển thị trong 7 ngày nhưng phải phục vụ đối soát 90 ngày. Nếu đặt TTL 7 ngày rồi xóa luôn ở nguồn duy nhất, ứng dụng có thể mất khả năng điều tra. Ngược lại, giữ tất cả sự kiện trong một collection nóng suốt 90 ngày có thể làm partition lớn, index tốn kém và truy vấn mới nhất chậm hơn. Một thiết kế hợp lý có thể giữ 7 ngày ở **hot store**, chuyển lịch sử sang **archive**, và chỉ xóa archive khi đã hết thời hạn phù hợp. Nhưng khi nào được coi là đã archive an toàn? Nếu job chuyển dữ liệu thất bại một nửa thì sao? Nếu có yêu cầu xóa sớm hoặc dữ liệu nằm trong backup cũ thì sao?

Đó là nội dung của **quản lý vòng đời dữ liệu (data lifecycle management)**. Trong NoSQL, vòng đời không nên được coi là một tùy chọn TTL đơn lẻ. Nó là một **hợp đồng từ nghiệp vụ tới lưu trữ và vận hành**, quyết định dữ liệu nào được tạo, phục vụ ai, giữ trong bao lâu, đặt ở tầng nào, và cần chứng minh điều gì khi xóa.

> **Phạm vi:** Các thuật ngữ TTL, tombstone, compaction, retention policy, object storage và lifecycle job được trình bày theo nguyên lý chung. Các sản phẩm NoSQL khác nhau có cơ chế, giới hạn, thời gian thực thi và bảo đảm rất khác nhau. Những ví dụ về document, key–value, wide-column và search engine là minh họa, không phải cú pháp áp dụng nguyên xi cho mọi hệ.

## 1. Mô hình vòng đời: nhiều giai đoạn, nhiều chính sách

Một mô hình đơn giản:

~~~mermaid
flowchart LR
    A["Tạo mới"] --> B["Đang sử dụng"]
    B --> C["Ít được truy cập"]
    C --> D["Lưu trữ dài hạn"]
    B --> E["Hết hiệu lực"]
    C --> E
    D --> F["Hết hạn lưu giữ"]
    E --> G["Đánh giá xóa"]
    F --> G
    G --> H["Xóa logic / chặn truy cập"]
    H --> I["Thu hồi dữ liệu tại các nơi lưu"]
    I --> J["Đối soát và đóng vòng đời"]
~~~

Sơ đồ trên mô tả **các khả năng**, không phải mọi dữ liệu đều phải đi qua cùng một đường. Dữ liệu phiên làm việc có thể được tạo, sử dụng vài phút rồi hết TTL mà không bao giờ vào archive. Bản ghi tài chính có thể chuyển sang tầng ít truy cập nhưng vẫn phải được giữ theo một thời hạn quản lý riêng. Một yêu cầu xóa hợp lệ có thể xuất hiện **trước** ngày retention thông thường; một yêu cầu giữ bằng chứng (*legal hold*) có thể khiến việc xóa theo lịch phải được tạm dừng nếu có cơ sở và chính sách áp dụng.

### 1.1. Năm câu hỏi cần trả lời cho từng loại dữ liệu

1. **Tại sao được tạo?** Nguồn phát, mục đích nghiệp vụ, dữ kiện bắt buộc và chủ sở hữu.
2. **Ai được dùng?** Đường đọc/ghi, tenant, quyền truy cập, mục đích xử lý và độ mới cần thiết.
3. **Khi nào hết hiệu lực?** Tính từ thời điểm nào, theo sự kiện gì và dựa vào đồng hồ nào?
4. **Khi nào lưu trữ dài hạn?** Kho nào, bản nào có thẩm quyền, có thể phục hồi bằng cách nào?
5. **Khi nào và bằng cách nào xóa?** Xóa tại những hệ nào, trạng thái tạm thời ra sao, ai hoặc tác vụ nào xác nhận hoàn tất?

Nếu một nhóm chỉ nói “dữ liệu giữ 30 ngày” nhưng chưa xác định 30 ngày tính từ **lúc tạo**, **lúc nhận**, **lúc hoàn tất giao dịch** hay **lúc chấm dứt hợp đồng**, chính sách vẫn chưa đủ rõ để triển khai.

### 1.2. Phân biệt trạng thái nghiệp vụ và trạng thái lưu trữ

Một đơn hàng có thể có trạng thái nghiệp vụ `CONFIRMED`, `CANCELED` hoặc `COMPLETED`. Song song, metadata vòng đời có thể là `ACTIVE`, `ARCHIVED`, `DELETE_PENDING` hoặc `PURGED`.

Hai trục này không đồng nghĩa:

| Trục | Câu hỏi | Ví dụ |
|---|---|---|
| **Business state** | Đơn hàng đang ở trạng thái nghiệp vụ nào? | `COMPLETED` |
| **Access/lifecycle state** | Bản ghi hiện có được truy cập và lưu ở đâu? | `ARCHIVED` |
| **Retention state** | Đã đến hạn được xem xét xóa chưa? | `retentionUntil` đã qua |
| **Deletion workflow state** | Quá trình xóa đã hoàn tất ở các hệ liên quan chưa? | `DELETE_PENDING` |

Không nên chuyển trạng thái nghiệp vụ của đơn thành `DELETED` chỉ để tránh xử lý vòng đời; điều đó có thể làm mất ý nghĩa lịch sử cần giữ. Ngược lại, record đã đánh dấu `ARCHIVED` không có nghĩa nó đã không còn trong hot database.

## 2. Phân loại dữ liệu trước khi quyết định TTL và archive

Mỗi loại dữ liệu có mục đích, kích thước, tốc độ thay đổi và nghĩa vụ giữ khác nhau.

| Nhóm dữ liệu | Ví dụ | Đặc điểm | Cách tiếp cận vòng đời |
|---|---|---|---|
| Dữ liệu phiên/tạm thời | Session, OTP, lock tạm, cache | Giá trị ngắn hạn, có thể tạo lại hoặc nhanh hết hiệu lực | TTL và kiểm tra hết hạn khi dùng |
| Dữ liệu trạng thái hiện hành | Cart, hồ sơ, tồn kho | Được đọc/ghi thường xuyên, có bất biến | Quản lý theo trạng thái và quyền truy cập; không tùy tiện TTL toàn bản ghi |
| Dữ liệu sự kiện | Log thiết bị, activity event | Tăng theo thời gian, thường append | Time bucket, retention, archive, tổng hợp |
| Dữ liệu giao dịch | Order, Payment, Reservation | Có giá trị đối soát và liên kết nghiệp vụ | Thời hạn theo trạng thái nghiệp vụ, chính sách và yêu cầu áp dụng |
| Dữ liệu dẫn xuất | Search index, recommendation, projection | Có thể dựng lại từ nguồn | Xóa/đồng bộ theo nguồn và có cơ chế rebuild |
| Dữ liệu nhị phân | Ảnh, tệp, recording | Có thể lớn, truy cập không đều | Metadata NoSQL + object storage, phân tầng và xóa tham chiếu |
| Nhật ký điều tra/audit | Change history, security event | Cần tính truy vết, quyền nghiêm ngặt | Chính sách lưu riêng, bảo vệ tính toàn vẹn, xóa có kiểm soát |
| Backup/snapshot | Bản sao phục hồi | Không phục vụ truy vấn thông thường | Retention, mã hóa, phân quyền và kiểm thử restore độc lập |

Với cùng một ứng dụng, **session 15 phút**, **sự kiện truy cập 30 ngày**, **tổng hợp theo tháng 2 năm** và **bản ghi giao dịch có thời hạn quản lý riêng** không nên mặc định lưu bằng cùng một bảng và cùng TTL.

### 2.1. Tạo data inventory

Một inventory tối thiểu cần:

~~~text
Data category: device_event
Owner: telemetry service
Purpose: hiển thị và phân tích sự kiện thiết bị
Authoritative source: device_events collection
Hot access window: 7 ngày
Archive window: tới 90 ngày kể từ event time
Retention anchor: event_time được kiểm chứng
Personal data classification: theo loại payload
Replicas/derived stores: analytics, search, cache, backups
Deletion mechanism: policy job + cascade events + verification
Recovery objective: theo SLO đã thống nhất
~~~

Không nên chỉ ghi tên collection. Vòng đời phải xét cả **mọi bản sao được tạo ra từ collection đó** và những hệ thống có thể lưu thông tin tương đương.

## 3. Giai đoạn tạo mới: dữ liệu phải hợp lệ ngay từ nguồn

Ngay tại bước tạo, hệ thống cần xác định **schema, định danh, thời điểm, nguồn gốc và chính sách vòng đời**. Nếu thiếu các dữ kiện này, việc truy vấn, archive hoặc xóa chính xác về sau có thể khó hơn nhiều.

Ví dụ một sự kiện:

~~~json
{
  "eventId": "evt-1008",
  "tenantId": "T-10",
  "deviceId": "D-21",
  "eventType": "TEMPERATURE_READING",
  "eventTime": "2026-11-14T08:00:00Z",
  "ingestedAt": "2026-11-14T08:01:03Z",
  "schemaVersion": 2,
  "retentionPolicy": "telemetry-v3",
  "hotUntil": "2026-11-21T08:00:00Z",
  "retainUntil": "2027-02-12T08:00:00Z",
  "payload": {
    "temperatureC": 24.3
  }
}
~~~

Các thời điểm trong ví dụ minh họa một chính sách giả định tính hạn từ `eventTime`; thực tế phải xác minh `eventTime` có đáng tin và sử dụng đúng định nghĩa ngày/giờ của nghiệp vụ.

### 3.1. Định danh ổn định và idempotency

Nếu producer gửi lại sự kiện vì timeout, hệ không nên tạo bản ghi mới mỗi lần retry nếu đây là **cùng một sự kiện nghiệp vụ**.

Một thiết kế có thể dùng:

~~~text
eventId = định danh ổn định từ nguồn hoặc server
unique scope = (tenantId, eventId)

insertIfAbsent(eventId, payload, policy):
    if eventId already exists:
        return existing result
    else:
        create one record atomically
~~~

Điều kiện “nếu chưa có” cần được bảo vệ bằng unique constraint, conditional write, compare-and-set hoặc cơ chế phù hợp. Việc query trước rồi insert riêng rẽ có thể tạo trùng khi hai request tới đồng thời.

### 3.2. Tách thời điểm nghiệp vụ và thời điểm nhận

Một thiết bị có thể đo lúc 08:00 nhưng mất mạng, tới 15:00 mới gửi. Hai trường có vai trò khác nhau:

- `eventTime`: thời điểm xảy ra theo nghiệp vụ.
- `ingestedAt`: thời điểm hệ thống nhận/ghi dữ liệu.

Nếu retention yêu cầu 7 ngày **từ thời điểm phát sinh**, việc đặt TTL 7 ngày tại lúc ingest có thể giữ event lâu hơn mong muốn. Nếu chính sách tính từ lúc nhận, dùng eventTime để dọn có thể xóa quá sớm.

Vì vậy phải ghi rõ **retention anchor** và xử lý eventTime sai đồng hồ, tới muộn hoặc nằm trong tương lai.

### 3.3. Schema version và policy version

Hai phiên bản ứng dụng có thể hiểu cùng trường `expiresAt` khác nhau nếu không có contract. Ví dụ phiên bản cũ tính từ `createdAt`, phiên bản mới tính từ `completedAt`.

Khi thay quy tắc, nên xác định:

- `schemaVersion`: dạng dữ liệu có những trường và kiểu gì?
- `retentionPolicyVersion`: công thức tính hạn được áp dụng?
- `createdAt`/`eventTime`/`completedAt`: các mốc gốc.
- `hotUntil`/`retainUntil`: mốc dẫn xuất có thể được tính lại và đối soát khi policy thay đổi.

Version giúp migration theo lô mà không khiến bản ghi cũ bị hiểu nhầm.

### 3.4. Không tạo dữ liệu không cần thiết

Vòng đời dễ quản lý nhất với dữ liệu **không được tạo ra nếu không cần**. Trước khi đưa số điện thoại, địa chỉ, token hay payload đầy đủ vào event log và read model, cần hỏi mục đích và thời hạn thực sự. Dữ liệu được nhân bản đến nhiều hệ sẽ tốn công xóa và tăng rủi ro truy cập trái mục đích.

## 4. Giai đoạn sử dụng: mô hình dữ liệu theo đường truy cập

Dữ liệu **hot** thường được đọc hoặc cập nhật liên tục, nên cách tổ chức khóa và index quyết định phần lớn hiệu năng.

Ví dụ các truy vấn:

~~~text
Lấy 100 sự kiện mới nhất của một thiết bị.
Lấy trạng thái hiện tại của một đơn hàng.
Lấy 20 đơn gần nhất của khách hàng.
Tìm tất cả event theo khoảng thời gian để điều tra.
~~~

Những truy vấn này cần các đường truy cập khác nhau. Trong NoSQL, thường phải thiết kế **partition key, clustering/sort key, index hoặc read model riêng**, thay vì kỳ vọng một cấu trúc phục vụ mọi truy vấn hiệu quả.

### 4.1. Dữ liệu đang hoạt động và dữ liệu lịch sử

Một document Order có thể được sửa nhiều lần trong trạng thái `DRAFT` và `PENDING`, nhưng khi `COMPLETED` thì gần như chỉ đọc. Khi đó có thể thay đổi tầng truy cập hoặc chính sách lưu, nhưng cần cân nhắc những thao tác hợp lệ vẫn có thể xảy ra về sau như refund, điều chỉnh chứng từ hay tranh chấp.

Đừng chuyển bản ghi sang chế độ bất biến chỉ vì “đã lâu không được sửa”. Nên dùng **điều kiện nghiệp vụ có ý nghĩa** cùng thời gian cần thiết.

### 4.2. Cache và read model có vòng đời riêng

Một dữ liệu gốc có thể được nhân bản:

~~~mermaid
flowchart TD
    SRC[("Authoritative NoSQL")]
    SRC --> IDX[("Search index")]
    SRC --> CACHE[("Distributed cache")]
    SRC --> ANALYTICS[("Analytics store")]
    SRC --> ARCHIVE[("Archive")]
~~~

Khi bản gốc thay đổi hoặc hết quyền truy cập, những bản sao khác cần có cách đồng bộ. TTL của cache có thể giúp giới hạn thời gian dữ liệu cũ còn sống, nhưng **không thay thế cơ chế invalidation**, nhất là khi quyền truy cập bị thu hồi hoặc có yêu cầu xóa sớm.

### 4.3. Bảo vệ dữ liệu khi đang sử dụng

Vòng đời không chỉ nói về xóa. Trong giai đoạn sử dụng cần:

- Kiểm tra tenant isolation và phân quyền theo mục đích.
- Mã hóa trên đường truyền và nơi lưu theo chính sách.
- Giới hạn ghi nhầm vào projection hoặc archive.
- Theo dõi chất lượng, version, truy cập và thay đổi dữ liệu.
- Tránh đưa dữ liệu nhạy cảm vào log ứng dụng ngoài thời hạn cần thiết.
- Có khả năng xác định **nguồn có thẩm quyền** khi các bản sao tạm không đồng nhất.

## 5. TTL và expiration: hết hiệu lực không đồng nghĩa xóa ngay

**TTL (Time To Live)** thường biểu thị thời gian một dữ liệu còn được xem là hợp lệ trong một tầng lưu trữ. Nhiều hệ NoSQL có cơ chế TTL nhưng cách thực hiện không giống nhau:

- Key–value cache có thể hỗ trợ đặt thời hạn cho key và loại khỏi truy vấn khi hết hạn.
- Document database có thể dùng TTL index hoặc background process để xóa những document đạt mốc thời gian.
- Wide-column database theo kiểu LSM có thể xử lý expired cells và tombstone rồi thu hồi vật lý qua compaction.
- Một số dịch vụ quản lý có TTL background deletion **bất đồng bộ**, nên bản ghi đã tới hạn có thể còn đọc được trong một khoảng thời gian tùy cơ chế.

Không nên kết luận chỉ từ tên tính năng TTL rằng “đúng giây hết hạn, mọi bản sao vật lý đã bị xóa”.

### 5.1. TTL tính từ lúc ghi khác với deadline tuyệt đối

Giả sử chính sách yêu cầu sự kiện chỉ còn hợp lệ 7 ngày sau **eventTime**:

~~~text
eventTime         = 01/11 08:00
ingestedAt        = 03/11 08:00
retentionDeadline = 08/11 08:00

Nếu ghi TTL = 7 ngày tại 03/11:
  thời gian sống tới khoảng 10/11 08:00
  -> lâu hơn chính sách theo eventTime 2 ngày.
~~~

Một cách tính ở ứng dụng:

~~~text
remainingTTL = retentionDeadline - authoritativeNow

if remainingTTL <= 0:
    không đưa record vào hot store dưới dạng đang sống
else:
    ghi với TTL còn lại, theo giới hạn và quy tắc làm tròn của DB
~~~

Đây là pseudocode. Cần xử lý clock skew, timestamp từ thiết bị không đáng tin, đơn vị thời gian, giới hạn TTL và hành vi của sản phẩm. Có thể giữ thêm `expiresAt` như metadata để truy vấn và đối soát.

### 5.2. Hết hạn logic và xóa vật lý

~~~text
T0                    T1                       T2
|---------------------|------------------------|------------>
Tạo bản ghi            Hết TTL                  Thu hồi vật lý
                      / deadline               khi đủ điều kiện
~~~

Tại T1, hệ có thể:

- Trả về “không còn hiệu lực” ngay ở logic ứng dụng.
- Tự ẩn record khỏi truy vấn theo semantics TTL của database.
- Đánh dấu record cần xóa, nhưng background worker mới thực hiện về sau.

Tại T2, bytes mới được loại bỏ khỏi một hoặc nhiều cấu trúc lưu trữ. Những bản sao trong backup hoặc archive có thể có lịch riêng. Do đó, **tính đúng đắn khi đọc và mức độ hoàn tất xóa vật lý là hai thuộc tính riêng**.

### 5.3. TTL không tự gọi workflow nghiệp vụ

Ví dụ reservation có TTL 15 phút. Hết TTL không đồng nghĩa một workflow đáng tin cậy đã:

~~~text
release inventory
update order status
refund payment
send compensation event
~~~

Nếu việc trả quota hay hoàn tiền là bắt buộc, cần logic nghiệp vụ có **deadline, trạng thái bền, scheduler/event, retry, idempotency và đối soát**. TTL của bản ghi phụ trợ có thể giúp dọn sau khi kết quả workflow đã ổn định, chứ không nên xóa dấu vết cần cho việc hoàn tất workflow trước thời điểm an toàn.

### 5.4. Expiration check ở lúc đọc

Với hệ có background TTL deletion bất đồng bộ, ứng dụng có thể cần bảo vệ điều kiện hết hạn khi đọc:

~~~text
session = read(sessionId)

if session == null:
    reject
else if session.expiresAt <= trustedNow:
    reject
else:
    allow according to other authorization checks
~~~

Ví dụ là mô hình tư duy; độ an toàn còn phụ thuộc chính sách clock, consistency và việc áp dụng kiểm tra tại đúng điểm thực hiện hành động. Đừng coi công việc xóa background là biện pháp duy nhất để thu hồi quyền truy cập vào một token đã hết hạn.

### 5.5. TTL và index

TTL có thể tạo thêm công việc trên index hoặc storage. Trong document database, background deletion có thể gây nhiều delete write; với hệ LSM, expired cells/tombstones có thể ảnh hưởng đường đọc và compaction. Nếu TTL của hàng triệu bản ghi trùng một thời điểm, tải dọn có thể tăng đột ngột.

Các hướng xem xét:

- Phân bố thời điểm hết hạn khi nghiệp vụ cho phép, không tùy tiện kéo dài thời hạn bảo mật.
- Dùng time buckets cho dữ liệu time-series.
- Chọn partition và compaction strategy phù hợp.
- Không tạo quá nhiều index không cần thiết trên collection sắp hết hạn.
- Theo dõi backlog, p99 read/write latency và dung lượng vật lý.

## 6. Thiết kế chính sách lưu giữ (retention policy)

**Retention** không chỉ là một số ngày. Một policy hoàn chỉnh nên xác định:

| Thành phần | Ví dụ | Câu hỏi |
|---|---|---|
| Data category | `telemetry_detail` | Loại dữ liệu nào? |
| Owner | Telemetry Service | Ai chịu trách nhiệm? |
| Start event | `eventTime` | Mốc tính từ đâu? |
| Hot window | 7 ngày | Được đọc nhanh tới khi nào? |
| Archive window | Tới 90 ngày | Lưu lạnh bao lâu? |
| Deletion deadline | Theo chính sách đã duyệt | Khi nào cần xử lý xóa? |
| Exceptions | Điều tra, hold, tranh chấp | Điều kiện nào tạm dừng/đổi hạn? |
| Copies | Search, cache, backup, export | Phải tác động lên những nơi nào? |
| Access rights | Theo tenant và mục đích | Ai được đọc từng tầng? |
| Verification | Manifest, checksum, deletion status | Bằng chứng hoàn thành là gì? |
| Policy version | `telemetry-v3` | Dữ liệu cũ theo quy tắc nào? |

### 6.1. Retention anchor là quyết định nghiệp vụ

Những cách tính khác nhau:

~~~text
Session:       từ issuedAt hoặc lastActivityAt theo contract.
Event:         từ eventTime hoặc ingestedAt theo policy.
Order:         từ completedAt, canceledAt hoặc mốc quản lý phù hợp.
Contract:      từ ngày chấm dứt hợp đồng.
Attachment:    theo vòng đời của đối tượng sở hữu và nghĩa vụ riêng.
Audit record:  theo mốc nghiệp vụ hoặc quy định nội bộ áp dụng.
~~~

Không nên áp một trường `createdAt` duy nhất cho mọi chính sách.

### 6.2. Retention và legal hold

Trong một số trường hợp, việc xóa thường lệ có thể cần tạm hoãn vì yêu cầu giữ dữ liệu hợp lệ, ví dụ quá trình điều tra, tranh chấp hoặc nghĩa vụ lưu giữ. Hệ thống cần biết:

- Ai có quyền áp dụng hoặc gỡ hold?
- Hold có hiệu lực trên những record, tenant hoặc phạm vi nào?
- Có hạn và lý do được ghi nhận không?
- Khi hold được gỡ, deadline cần được tính lại như thế nào?
- Có cần thông báo tới các archive/backup liên quan không?

Việc lưu giữ và xóa phải tuân theo chính sách, hợp đồng và quy định thực tế áp dụng; không nên coi ví dụ này là lời khuyên pháp lý hoặc giả định mọi loại dữ liệu luôn phải được giữ lâu hơn khi có bất kỳ yêu cầu nào.

### 6.3. Không để “hold” trở thành cờ bất tử

Nếu một bản ghi bị giữ không thời hạn vì cờ hold bị bỏ quên, dung lượng và rủi ro truy cập sẽ tăng. Cần audit, owner, lý do, rà soát định kỳ và quy trình giải phóng hold theo quyền được cấp.

## 7. Lưu trữ dài hạn: hot, warm, cold và archive

Một kiến trúc có thể phân tầng theo tần suất truy cập và SLA:

| Tầng | Mục tiêu | Đặc điểm thường gặp |
|---|---|---|
| **Hot** | Đọc/ghi độ trễ thấp, truy vấn thường xuyên | Index đầy đủ, tài nguyên truy cập nhanh, chi phí cao hơn |
| **Warm** | Đọc lịch sử ít thường xuyên hơn | Có thể giảm index/tài nguyên, truy vấn chậm hơn |
| **Cold / archive** | Giữ dữ liệu lâu, truy xuất không thường xuyên | Lưu theo object/segment, cần job phục hồi hoặc truy vấn batch |
| **Backup** | Khôi phục sau lỗi hoặc thảm họa | Không mặc định là archive có thể truy vấn hoặc dùng làm nguồn dữ liệu nghiệp vụ |

Đây là cách phân loại tương đối. Chi phí, thời gian khôi phục và khả năng truy vấn phụ thuộc công nghệ; **cold storage không luôn rẻ hơn nếu thường xuyên phải truy xuất hoặc phát sinh chi phí phục hồi lớn**.

### 7.1. Chuyển tầng không giống xóa

~~~text
Hot NoSQL
    |
    | Archive job copy/transform
    v
Object storage archive
    |
    | Verify durability and manifest
    v
Hot record eligible for deletion
~~~

Nếu xóa hot record trước khi archive ghi xong và được kiểm chứng, dữ liệu có thể mất vĩnh viễn. Nếu archive thành công nhưng chưa kịp xóa hot, có hai bản sao trong một thời gian; điều này thường là trạng thái trung gian chấp nhận được nếu được kiểm soát và có chính sách xóa.

### 7.2. Định dạng archive cần đọc được về sau

Archive nên có:

- **Schema version** và quy tắc giải mã dữ liệu.
- **Manifest** mô tả nhóm file, tenant, time range, số record và checksum.
- **Object IDs/key** ổn định để truy xuất và deduplicate.
- **Metadata retention**, quyền truy cập, encryption và vị trí lưu.
- Khả năng khôi phục thử nghiệm trên phiên bản phần mềm hiện tại.
- Quy tắc xử lý late events hoặc bản ghi bị sửa sau khi đã archive.

Nếu archive chỉ lưu binary blob mà không giữ schema, key hay cách khôi phục, 2 năm sau có thể không còn đọc được dù bytes vẫn nguyên vẹn.

### 7.3. Mô hình time bucket

Với telemetry:

~~~text
Hot partition:
    (tenantId, deviceId, dayBucket)

Archive object path:
    tenant=T-10/type=telemetry/day=2026-11-14/segment-0001
~~~

Lưu theo ngày/partition có thể giúp quản lý retention theo nhóm và tránh quét toàn bộ collection. Nhưng nếu một thiết bị tạo lượng event cực lớn, bucket ngày vẫn có thể nóng; cần xem xét độ hạt theo giờ hoặc shard. Việc chọn kích thước bucket ảnh hưởng đường truy vấn và tải khi xóa.

### 7.4. Compaction ở nguồn và lifecycle của archive là hai cơ chế

Compaction trong LSM database tái tổ chức/thu hồi SSTable. Lifecycle của object storage có thể chuyển object qua các storage class hoặc xóa object theo policy. Log compaction ở broker có thể rút ngắn lịch sử theo key. Chúng không thay thế nhau.

Một record đã “hết hạn” trong source không có nghĩa mọi bản archive đã bị xóa; ngược lại, một archive được xóa theo policy không tự dọn bản sao trong search index.

## 8. Quy trình archive an toàn và có thể tiếp tục sau lỗi

Xét một job chuyển sự kiện quá 7 ngày khỏi hot NoSQL sang object storage. Không có transaction toàn cục giữa database và object storage.

Một workflow thực tế có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> HOT
    HOT --> ARCHIVE_PENDING: Chọn batch đủ điều kiện
    ARCHIVE_PENDING --> COPYING: Ghi archive
    COPYING --> VERIFYING: Ghi thành công
    COPYING --> RETRY: Ghi thất bại
    RETRY --> COPYING: Thử lại
    VERIFYING --> ARCHIVED: Kiểm tra checksum/manifest
    VERIFYING --> RETRY: Không khớp
    ARCHIVED --> HOT_DELETE_PENDING: Đã đủ điều kiện xóa hot
    HOT_DELETE_PENDING --> ARCHIVE_ONLY: Xóa bản hot + xác nhận
    ARCHIVE_ONLY --> [*]
~~~

### 8.1. Chọn một batch có ranh giới ổn định

Ví dụ:

~~~text
tenantId = T-10
eventType = TEMPERATURE
eventTime in [2026-11-01, 2026-11-02)
sourceVersion/highWatermark = ...
batchId = archive-T10-20261101-v1
~~~

Ranh giới giúp retry không tạo những file khác nhau tùy thời điểm. Với dữ liệu có late writes hoặc UPDATE, cần xác định snapshot/high-water mark và cách bắt kịp thay đổi phát sinh sau khi batch được chọn.

### 8.2. Ghi archive theo định danh idempotent

Một worker có thể ghi xong object rồi chết trước khi cập nhật metadata. Khi retry, nó nên nhận ra object đã tồn tại với checksum đúng, thay vì tự động tạo bản thứ hai không thể quản lý.

Một manifest ví dụ:

~~~json
{
  "archiveBatchId": "archive-T10-20261101-v1",
  "tenantId": "T-10",
  "dataType": "TEMPERATURE",
  "fromInclusive": "2026-11-01T00:00:00Z",
  "toExclusive": "2026-11-02T00:00:00Z",
  "schemaVersion": 3,
  "recordCount": 86400,
  "objectKey": "telemetry/T-10/2026-11-01/segment-0001",
  "checksumAlgorithm": "SHA-256",
  "checksum": "<digest-from-uploaded-content>",
  "state": "VERIFIED"
}
~~~

Manifest phải được tạo và lưu bền theo một protocol nhất quán; `VERIFIED` chỉ được ghi sau khi hệ thực sự xác minh nội dung theo các tiêu chí đã chọn.

### 8.3. Kiểm chứng trước khi xóa nguồn

Ít nhất cần xem:

- Số record dự kiến và số record trong archive.
- Định danh hoặc phạm vi bao phủ có thiếu/trùng không.
- Checksum để xác minh byte hoặc nội dung đã serialize.
- Schema có thể giải mã khi phục hồi không.
- Quyền truy cập, mã hóa và retention tại archive đã đúng chưa.
- Event đến muộn hoặc record thay đổi sau mốc snapshot xử lý thế nào.

Hash của một file chứng minh tính nhất quán của bytes theo phương pháp kiểm tra, **không tự chứng minh số sự kiện đã đủ** nếu quá trình chọn record bị thiếu.

### 8.4. Xóa hot sau khi xác minh

Chỉ đánh dấu record/bucket đủ điều kiện xóa khi archive đã bền và các điều kiện nghiệp vụ cho phép. Một job xóa hot nên:

~~~text
for each verified archive batch:
    verify batch still eligible and no active hold
    delete hot source within supported scope
    record deletion outcome / retry state
    reconcile source and archive coverage
~~~

Nếu có data mutation trong thời gian chuyển, xóa theo một bộ khóa/phiên bản đã chốt hoặc có cơ chế đồng bộ phần delta, thay vì xóa tùy tiện tất cả record theo date range rồi mất dữ liệu mới.

### 8.5. Restore thực tế là một phần của archive

Một archive đáng tin cần được kiểm tra bằng **restore drill**: lấy manifest, đọc đúng schema, tạo dữ liệu phục hồi hoặc truy vấn lịch sử, xác minh kết quả và quyền. Nếu chưa từng thử restore, chỉ số `archive_bytes_written` chưa đủ chứng minh có thể phục hồi.

## 9. Xóa dữ liệu: ít nhất bốn tầng cần phân biệt

**Xóa** là từ dễ gây hiểu nhầm nhất trong vòng đời NoSQL. Có thể tách:

1. **Revoke access / logical delete:** người dùng và API không còn thấy hoặc sử dụng dữ liệu.
2. **Database delete:** bản ghi bị xóa hoặc đánh dấu xóa theo semantics của nguồn dữ liệu.
3. **Physical reclamation:** file/segment/SSTable được thu hồi vật lý khi điều kiện cho phép.
4. **Whole-system lifecycle completion:** các bản sao ở cache, index, archive, export và backup được xử lý theo chính sách thích hợp.

| Hành động | Dữ liệu còn tồn tại ở đâu? | Điều không nên suy ra |
|---|---|---|
| Đặt `isDeleted=true` | Thường còn nguyên ở database | Không phải physical deletion |
| TTL hết hạn | Có thể còn bytes trong storage | Không chắc backup đã mất |
| `DELETE` document/row | Có thể còn trong replica, logs, snapshot, backup trong thời gian nhất định | Không chắc đã xóa mọi bản |
| Xóa object ở archive | Có thể còn version cũ hoặc bản sao/backup | Không chắc mọi version đã thu hồi |
| Xóa khỏi search index | Nguồn và analytics có thể còn | Không phải xóa toàn hệ thống |
| Crypto-erasure theo khóa | Ciphertext có thể còn | Chỉ phù hợp nếu khóa được quản lý đúng và không còn bản plaintext/key khác |

### 9.1. Logical delete và soft delete

Một document có thể có:

~~~json
{
  "userId": "U-42",
  "lifecycleState": "DELETE_PENDING",
  "deletedAt": "2026-11-14T09:00:00Z",
  "deletionRequestId": "del-128",
  "version": 19
}
~~~

Logical delete có ích để chặn truy cập ngay và ghi nhận tiến độ xóa qua nhiều hệ. Nhưng khi chỉ thêm cờ, bản ghi và dữ liệu nhạy cảm vẫn tồn tại. Hệ thống phải có workflow thu hồi tiếp theo.

Soft delete cũng có rủi ro: một query quên điều kiện `lifecycleState=ACTIVE` có thể trả dữ liệu đã xóa; một projection cũ có thể không nhận được cập nhật. Đối với dữ liệu cần chặn truy cập tức thời, nên bảo vệ tại một nơi cấp quyền hoặc nguồn có thẩm quyền, không chỉ dựa vào mọi query nhớ lọc cờ.

### 9.2. Tombstone trong hệ phân tán

Một số wide-column database theo kiểu LSM dùng **tombstone** để biểu diễn xóa. Khi một replica đang offline, tombstone còn tồn tại giúp ngăn bản ghi cũ từ replica đó tái xuất hiện sau khi đồng bộ.

~~~text
Replica A: tombstone @200
Replica B: tombstone @200
Replica C: data @100 (offline lúc DELETE)
~~~

Nếu thông tin xóa được giữ đủ lâu và cơ chế repair/hòa giải hoạt động đúng, C có thể nhận biết bản ghi @100 đã cũ. Nếu xóa tombstone quá sớm trong điều kiện chưa an toàn, dữ liệu cũ có thể **hồi sinh** (*zombie data*).

Vì vậy, chính sách xóa phải xét thời gian replica có thể offline, repair, compaction và bảo đảm của sản phẩm. **Không nên giảm thời gian giữ tombstone chỉ để đĩa giảm nhanh** nếu chưa hiểu hệ quả.

### 9.3. Backup và snapshot

Một thao tác xóa thành công ở database live không tự chỉnh sửa bản backup đã tạo trước đó. Backup thường có retention và quy trình riêng nhằm giữ khả năng khôi phục sau lỗi. Cần xác định:

- Bản backup nào chứa dữ liệu thuộc phạm vi yêu cầu xóa?
- Backup được mã hóa, hạn chế truy cập và giữ trong bao lâu?
- Có thể xóa hoặc làm hết hạn bản backup theo policy áp dụng không?
- Nếu restore một backup cũ, làm sao **không đưa trở lại các record đã xóa hợp lệ**?
- Cần lưu một danh sách xóa có kiểm soát hoặc replay sự kiện xóa sau restore không?

Không nên hứa “đã xóa khỏi mọi byte lập tức” khi vẫn còn bản sao trong backup chưa đến hạn. Cần mô tả chính xác mức hoàn tất, các ngoại lệ hợp lệ và quy trình ngăn dữ liệu xuất hiện lại sau phục hồi.

### 9.4. Crypto-erasure và giới hạn

Trong một kiến trúc có mã hóa dữ liệu bằng khóa được phân tách đúng theo đơn vị cần xóa, việc hủy khóa có thể khiến ciphertext trở nên không thể giải mã bằng cơ chế bình thường. Nhưng điều này chỉ đạt mục tiêu nếu:

- Không còn bản plaintext cần xử lý ở nơi khác.
- Khóa không còn trong bản sao, backup, cache hoặc key escrow ngoài phạm vi chính sách.
- Mô hình khóa không dùng một khóa chung cho nhiều dữ liệu vẫn cần giữ.
- Quy trình hủy khóa, kiểm toán và phục hồi được thiết kế phù hợp.

Do đó, crypto-erasure là **một kỹ thuật có điều kiện**, không phải một lệnh có thể dùng thay mọi quy trình xóa.

## 10. Xóa toàn hệ thống: bản đồ dữ liệu quan trọng hơn một câu lệnh DELETE

Một user có thể có dấu vết tại:

~~~mermaid
flowchart TD
    USER["User / Data subject"]
    USER --> DB[("Primary NoSQL")]
    DB --> C[("Cache")]
    DB --> S[("Search index")]
    DB --> A[("Analytics")]
    DB --> O[("Object storage")]
    DB --> B[("Backup / snapshot")]
    DB --> L[("Logs / exports")]
~~~

Khi xử lý yêu cầu xóa được chấp nhận, cần định nghĩa rõ **phạm vi dữ liệu liên quan** và hệ nào có trách nhiệm thực hiện. Không phải mọi bản ghi có userId đều nhất thiết bị xóa cùng cách; có thể có dữ liệu phải giữ theo một căn cứ hợp lệ. Nhưng danh mục hệ và quyết định xử lý phải rõ.

### 10.1. Deletion request có định danh và trạng thái

~~~json
{
  "deletionRequestId": "del-128",
  "subjectId": "U-42",
  "scope": ["profile", "attachments", "search"],
  "requestedAt": "2026-11-14T09:00:00Z",
  "policyVersion": "erase-v2",
  "status": "IN_PROGRESS",
  "targets": {
    "primary": "DONE",
    "cache": "DONE",
    "search": "PENDING",
    "objectStorage": "PENDING",
    "backupHandling": "POLICY_DEFINED"
  }
}
~~~

Đây là ví dụ cấu trúc nội bộ; không nên công khai cho người dùng thông tin hạ tầng chi tiết không cần thiết. Trạng thái `DONE` phải gắn với một điều kiện xác nhận cụ thể, không chỉ nghĩa worker đã gửi request.

### 10.2. Quy trình xóa có thể tiếp tục sau lỗi

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> VALIDATING
    VALIDATING --> BLOCKED: Không hợp lệ / đang có ngoại lệ giữ
    VALIDATING --> ACCESS_REVOKED: Đủ điều kiện xử lý
    ACCESS_REVOKED --> DELETING: Phân phối tác vụ xóa
    DELETING --> VERIFYING: Các target đã xử lý
    DELETING --> RETRY: Một target lỗi
    RETRY --> DELETING: Thử lại idempotent
    VERIFYING --> COMPLETED: Đối soát đạt yêu cầu
    VERIFYING --> RETRY: Còn dữ liệu hoặc sai lệch
    BLOCKED --> VALIDATING: Điều kiện thay đổi
    COMPLETED --> [*]
~~~

Các trạng thái có thể được thiết kế khác theo nghiệp vụ. Điểm cốt lõi là công việc **bền vững, có idempotency, có retry và có tiêu chí hoàn tất**.

### 10.3. Dùng sự kiện xóa nhưng không mặc định exactly-once

Một luồng:

~~~text
Primary service:
  commit deletion intent / logical state
  write outbox DeletionRequested

Publisher:
  publish event to subscribers

Subscribers:
  remove or invalidate owned copies
  report completion idempotently

Coordinator:
  reconcile target status and close request
~~~

Nếu outbox và nguồn chính có thể được ghi trong một transaction hỗ trợ, mô hình này giảm nguy cơ cập nhật nguồn mà mất ý định phát event. Nhưng publisher có thể phát lặp và consumer có thể xử lý nhiều lần; cần idempotency ở từng target. **Không nên mặc định message broker đem lại xóa exactly-once trên mọi hệ ngoài**.

### 10.4. Dữ liệu tái xuất hiện từ CDC, cache fill hoặc restore

Một rủi ro khó nhận thấy:

~~~text
T1: User U-42 bị xóa ở primary.
T2: Search index nhận DeletionRequested và xóa.
T3: Một CDC consumer cũ phát lại UserUpdated từ trước T1.
T4: Search index tạo lại tài liệu U-42.
~~~

Để tránh, hệ cần cơ chế xét **thứ tự phiên bản hoặc dấu xóa có thẩm quyền**. Có thể dùng deletion ledger/tombstone/version theo subject, đảm bảo event cũ không được phép tạo lại bản ghi đã xóa. Việc áp dụng version trong từng target phải có cách kiểm tra bền và phù hợp với event ordering.

Tương tự, sau restore backup cũ, cần reapply các quyết định xóa đã có hiệu lực sau thời điểm backup, trước khi mở lại quyền đọc rộng rãi.

### 10.5. Giữ tối thiểu thông tin chứng minh xóa

Hệ có thể cần giữ metadata về yêu cầu và kết quả xóa để kiểm toán hoặc chống dữ liệu hồi sinh. Nhưng metadata này cũng có thể liên quan tới cá nhân và cần có **mục đích, giới hạn truy cập, retention riêng**. Tránh giữ toàn bộ payload đã yêu cầu xóa chỉ để “làm bằng chứng”.

## 11. Vòng đời và dữ liệu dẫn xuất: không xóa nhầm nguồn hoặc làm sai báo cáo

Một event có thể tạo nhiều kết quả:

~~~text
Raw event -> HourlySummary
          -> DailySummary
          -> SearchIndex
          -> AlertHistory
~~~

Khi raw event hết hot TTL, DailySummary có thể vẫn cần giữ. Tuy nhiên cần trả lời:

- Summary có cần truy vết tới raw event không?
- Có cần rebuild khi sửa thuật toán không?
- Dữ liệu cá nhân có thể còn trong summary hoặc nhóm nhỏ có thể tái nhận diện không?
- Khi xóa một subject, aggregate có phải tính lại hoặc xóa liên hệ không?
- Làm sao đối soát khi raw event đã bị purge?

### 11.1. Dẫn xuất không đồng nghĩa không còn dữ liệu cá nhân

Một bảng tổng hợp theo tenant, device hoặc nhóm rất nhỏ vẫn có thể tiết lộ thông tin về một đối tượng. Không nên coi mọi số liệu tổng hợp tự động là đã ẩn danh hoàn toàn. Cần đánh giá khả năng nhận diện trong ngữ cảnh thực.

### 11.2. Giữ raw data quá ngắn làm mất khả năng sửa sai

Giả sử job tính DailySummary bị lỗi trong 10 ngày, nhưng raw event chỉ giữ 7 ngày và không có archive. Một phần dữ liệu gốc có thể không còn để chạy lại. Vì vậy **retention của nguồn** phải xét nhu cầu backfill, thời gian phát hiện lỗi và khả năng phục hồi của các downstream.

### 11.3. Giữ raw data quá dài cũng có chi phí

Lưu toàn bộ sự kiện nhiều năm trong hot store làm tăng index, storage, compaction, chi phí vận hành và bề mặt truy cập dữ liệu. Cần cân bằng khả năng replay với archive, snapshot, báo cáo đã xác minh và chính sách lưu có căn cứ.

## 12. Thiết kế NoSQL theo vòng đời

Vòng đời dữ liệu tác động trực tiếp tới **partition key, index và mô hình lưu**.

### 12.1. Dữ liệu time-series nên có biên giới kích thước

Không nên nhúng toàn bộ sự kiện nhiều năm vào:

~~~json
{
  "deviceId": "D-21",
  "events": [
    {"time": "...", "value": 24.3}
  ]
}
~~~

Mảng sẽ tăng không giới hạn, khó phân trang và tạo hot document. Một cấu trúc ứng viên:

~~~text
partitionKey = (tenantId, deviceId, dayBucket)
sortKey = (eventTime, eventId)
~~~

Đường đọc 24 giờ có thể đọc một hoặc hai bucket ngày; archive hoặc retention có thể vận hành theo bucket. Nhưng nếu một device cực nóng, bucket ngày vẫn có thể quá lớn; cần đo và cân nhắc bucket giờ hoặc shard.

### 12.2. Xóa theo thời gian không nên buộc quét toàn collection

Nếu database không có TTL/index phù hợp, một job:

~~~text
scan toàn collection -> chọn createdAt cũ -> delete từng row
~~~

có thể tốn nhiều tài nguyên và ảnh hưởng đường đọc/ghi production. Một chỉ mục theo `expiresAt` hoặc cấu trúc partition/time bucket có thể giúp định vị dữ liệu cần xử lý. Cần xác minh các query condition có dùng đúng index và không gây hot key.

### 12.3. TTL nhiều mức có thể xung đột

Một document có:

~~~json
{
  "orderId": "O-1042",
  "status": "COMPLETED",
  "temporaryToken": "abc",
  "auditMetadata": {"confirmedBy": "system"}
}
~~~

`temporaryToken` có vòng đời ngắn; Order và audit metadata có thể cần giữ lâu hơn. Đặt TTL cho **toàn document** có thể xóa cả những trường chưa được phép xóa. Một số hệ hỗ trợ TTL theo field/cell; hệ khác dùng TTL ở record; vì thế có thể cần tách token ra collection/key riêng.

### 12.4. Không dựa vào TTL để cập nhật các quan hệ chéo

Nếu một token hết hạn, quyền liên quan có thể cần từ chối truy cập ngay, nhưng TTL không tự làm sạch mọi tham chiếu ở document khác. Nếu Cart hết hạn, việc giải phóng reservation hoặc tạo event `CartExpired` là hành động nghiệp vụ riêng.

### 12.5. Chiến lược xóa ảnh hưởng read performance

Trong LSM-based wide-column, DELETE/TTL có thể tạo tombstone; truy vấn phải bỏ qua marker và compaction mới thu hồi vật lý khi an toàn. Nhiều tombstone trong partition rộng có thể gây read amplification. Các hệ document xóa background có thể tạo write burst hoặc index maintenance.

Một retention policy đúng về ngày tháng nhưng khiến hệ quá tải vẫn cần được thiết kế lại ở **cấu trúc lưu và cách chạy job**, không phải bỏ qua yêu cầu nghiệp vụ.

## 13. Case study: hệ thống telemetry và dữ liệu lịch sử

Xét nền tảng theo dõi thiết bị:

- 20.000 thiết bị, mỗi thiết bị gửi trung bình một event/5 giây.
- UI thường xem 24 giờ gần nhất.
- Raw event hot trong 7 ngày.
- Cần tra cứu lịch sử và điều tra tới 90 ngày.
- Summary theo ngày giữ 2 năm.
- Thiết bị có thể offline vài ngày rồi gửi bù.
- Một số event liên quan dữ liệu người dùng, có chính sách xóa riêng.

### 13.1. Ước lượng số lượng event

Một thiết bị:

~~~text
12 event/phút × 60 phút × 24 giờ
  = 17.280 event/ngày
~~~

Toàn hệ thống:

~~~text
20.000 × 17.280
  = 345.600.000 event/ngày
~~~

Trong 7 ngày có khoảng **2,4192 tỷ event logic** ở tốc độ trung bình nếu dòng dữ liệu đều đặn. Con số này chưa tính kích thước payload, replication, index, tombstone, compaction, peak traffic hoặc dữ liệu late. Không nên dùng số event sống nhân kích thước trung bình làm ước lượng đĩa cuối cùng mà không cộng overhead và headroom.

### 13.2. Một kiến trúc phân tầng

~~~mermaid
flowchart TD
    DEV["Devices"] --> ING["Ingestion + validation"]
    ING --> HOT[("Hot NoSQL: 7 days")]
    ING --> AGG["Aggregation pipeline"]
    AGG --> SUM[("Daily summaries: 2 years")]
    HOT --> ARCHJOB["Archival job"]
    ARCHJOB --> COLD[("Archive: until day 90")]
    ARCHJOB --> VERIFY["Manifest + verification"]
    VERIFY --> DELHOT["Delete eligible hot data"]
    COLD --> REPLAY["History retrieval / controlled replay"]
~~~

Sơ đồ này minh họa một phương án. Nếu raw event cần được đảm bảo tồn tại trong archive ngay từ lúc ingest, có thể chọn ghi vào một durable event log/archive sớm hơn thay vì chỉ phụ thuộc job chạy sau nhiều ngày; mỗi phương án có tradeoff riêng về commit, chi phí và phục hồi.

### 13.3. Document/record ở hot store

~~~json
{
  "tenantId": "T-10",
  "deviceId": "D-21",
  "dayBucket": "2026-11-14",
  "eventId": "evt-1008",
  "eventTime": "2026-11-14T08:00:00Z",
  "ingestedAt": "2026-11-14T08:01:03Z",
  "eventType": "TEMPERATURE",
  "value": 24.3,
  "hotUntil": "2026-11-21T08:00:00Z",
  "retainUntil": "2027-02-12T08:00:00Z",
  "policyVersion": "telemetry-v3"
}
~~~

Đường đọc dự kiến theo `(tenantId, deviceId, dayBucket)` và thứ tự `eventTime, eventId`. Có thể lập index hoặc bảng projection khác cho truy vấn chỉ theo tenant, nhưng cần đo và xác định nhu cầu thực.

### 13.4. Xử lý late event

Thiết bị gửi event có `eventTime` cách đây 5 ngày. Nếu TTL hot tính từ **ingestedAt**, event được giữ thêm đủ 7 ngày kể từ lúc nhận; nếu policy tính từ **eventTime**, nó chỉ còn khoảng 2 ngày ở hot store.

Nếu event đã quá 7 ngày nhưng chưa quá 90 ngày, có thể:

- Gửi trực tiếp vào đường archive/late-event ingest.
- Cập nhật summary hoặc phát sự kiện để job tổng hợp điều chỉnh.
- Lưu metadata để biết event đã được tiếp nhận và không bị mất.

Nếu đã quá 90 ngày, ứng dụng phải áp dụng quy tắc đã định nghĩa: từ chối, lưu metadata tối thiểu, hoặc thực hiện ngoại lệ có căn cứ. Không nên tự động gán TTL 90 ngày từ thời điểm đến rồi thay đổi chính sách.

### 13.5. Archive và dọn hot

Job chọn bucket đã đủ điều kiện, tạo archive object cùng manifest, kiểm tra số record và checksum, rồi đánh dấu đủ điều kiện xóa hot. Nếu job chết ở giữa, lần sau dùng `archiveBatchId` để retry idempotently.

Nếu ingestion vẫn có thể ghi event tới bucket cũ, cần snapshot/high-water mark hoặc cơ chế delta; không thể coi “bucket đã archive” là bằng chứng nó không còn thay đổi.

### 13.6. Xóa subject khỏi dữ liệu nhiều tầng

Khi có một yêu cầu xóa hợp lệ đối với subject liên quan, workflow cần xác định các event và bản dẫn xuất chịu ảnh hưởng trong hot, archive, search, summary và backup theo chính sách. Một số summary có thể cần tính lại; những thống kê đã được đánh giá là không còn liên quan nhận diện có thể có quy tắc khác.

Không nên chỉ xóa hồ sơ user rồi để lại một `userId` có thể liên kết với toàn bộ lịch sử ở archive mà không xét mục đích và nghĩa vụ xử lý.

## 14. Case study: đơn hàng đã hoàn tất và tệp đính kèm

Một ứng dụng giao dịch có:

~~~text
Orders (trạng thái hiện hành)
OrderEvents (lịch sử)
Attachments (metadata)
ObjectStorage (bytes của hóa đơn/chứng từ)
OrdersByCustomer (read model)
SearchIndex (tìm kiếm)
Backups (khôi phục)
~~~

Khi Order hoàn tất, có thể ít được cập nhật nhưng vẫn phải phục vụ khiếu nại hoặc đối soát. Quyết định chuyển archive cần xét:

- Từ `completedAt` hay một mốc khác?
- Refund/chargeback sau khi archive có thể xảy ra không?
- Nếu cần cập nhật Order đã archive thì nguồn có thẩm quyền nào nhận ghi?
- Chứng từ đính kèm có retention riêng không?
- Read model phục vụ lịch sử khách hàng cần dữ liệu tóm tắt bao lâu?

Một mô hình có thể tách:

- **Hot Order:** trạng thái chi tiết của đơn đang xử lý.
- **Archived Order:** dữ liệu hoàn tất ít truy cập, còn tìm theo ID bằng đường truy xuất phù hợp.
- **OrdersByCustomer:** danh sách/tóm tắt để UI phản hồi nhanh.
- **Attachment metadata + object bytes:** vòng đời và quyền có thể phụ thuộc Order nhưng thao tác lưu vật lý khác.

### 14.1. Tránh chuyển archive trước khi bất biến đã ổn định

Đơn `COMPLETED` vẫn có thể có refund hoặc điều chỉnh hợp lệ. Nếu archive được coi bất biến tuyệt đối, phải thiết kế event bổ sung hoặc bản cập nhật delta trong nguồn thích hợp, chứ không âm thầm sửa object archive rồi làm mất tính truy vết.

### 14.2. Xóa attachment không chỉ là xóa metadata

Nếu chỉ xóa record Attachments nhưng object bytes vẫn tồn tại và có thể truy cập qua URL cũ, việc xóa chưa đạt mục tiêu. Workflow cần thu hồi quyền truy cập, xóa/đặt lifecycle cho object, xử lý version và đối soát reference mồ côi.

### 14.3. Không nhầm archive với backup

Archive phục vụ truy xuất lịch sử theo nghiệp vụ. Backup phục vụ phục hồi hệ thống. Một bản backup toàn collection không mặc nhiên hỗ trợ truy vấn từng Order đúng quyền và đúng SLA; ngược lại, một archive theo tháng không đảm bảo phục hồi toàn hệ sau mất dữ liệu gần thời điểm hiện tại.

## 15. Quản lý policy khi dữ liệu thay đổi theo thời gian

Giả sử từ tháng 1, telemetry giữ 90 ngày; từ tháng 6, sản phẩm đổi thành 60 ngày. Cần quyết định:

1. Policy mới áp dụng cho **record mới**, record cũ hay cả hai?
2. Record cũ đã được archive tới 90 ngày có cần xóa sớm không?
3. Có ngoại lệ theo tenant hoặc hợp đồng không?
4. Nếu archive đã được tạo với một lifecycle rule cũ, ai cập nhật?
5. Có cần giải quyết record đang trong quá trình chuyển tầng không?

### 15.1. Version policy thay vì sửa ngầm

Một cấu trúc:

~~~json
{
  "recordId": "evt-1008",
  "policyId": "telemetry",
  "policyVersion": 3,
  "retentionAnchor": "2026-11-14T08:00:00Z",
  "hotUntil": "2026-11-21T08:00:00Z",
  "retainUntil": "2027-02-12T08:00:00Z"
}
~~~

Không nhất thiết mọi record phải chứa đầy đủ mọi mốc dẫn xuất, nhưng hệ cần cách xác định chính sách nào áp dụng. Nếu thay đổi rule làm thay đổi deadline, cần migration hoặc tính lại qua policy registry có version, không để hai service xử lý khác nhau.

### 15.2. Dual-run và đối soát policy

Trước khi thay job xóa, có thể chạy **dry-run** hoặc chế độ chỉ báo cáo:

~~~text
Policy v2: 120.000 record đủ điều kiện
Policy v3: 151.000 record đủ điều kiện
Difference: 31.000
Exceptions: 2.100
Pending archives: 900
~~~

Mục đích là hiểu phạm vi ảnh hưởng, kiểm tra rule ngoại lệ và phát hiện nguy cơ xóa nhầm trước khi bật đường xóa thực. Đây là khâu triển khai chính sách, không thay thế quy trình phê duyệt cần có tại tổ chức.

### 15.3. Backfill và import không được hồi sinh dữ liệu đã xóa

Khi migration hoặc import lại snapshot cũ, cần biết dữ liệu nào đã bị xóa hợp lệ. Một kỹ thuật có thể là đối chiếu với deletion ledger hoặc event sequence mới nhất tại nguồn có thẩm quyền rồi ngăn ghi bản cũ.

Thực tế việc lưu ledger, thứ tự và khóa phải được thiết kế sao cho tránh race giữa import và deletion request; việc query ledger rồi ghi độc lập có thể vẫn có cửa sổ cạnh tranh.

## 16. Capacity planning và chi phí của từng giai đoạn

Dung lượng vật lý không bằng **số record còn sống × kích thước payload**.

Một công thức tư duy:

~~~text
Total storage footprint
  ≈ hot live data
   + expired-but-not-reclaimed data
   + replica/index/metadata overhead
   + compaction or deletion temporary space
   + warm/cold archive
   + backups/snapshots
   + derived copies
~~~

Các thành phần có thể được tính phí khác nhau theo dịch vụ. Với object storage còn có yêu cầu retrieval, request, egress và minimum retention/class transition tùy sản phẩm.

### 16.1. Ước lượng theo tốc độ ingest

Giả sử một pipeline ghi trung bình **50 GB dữ liệu logic/ngày**:

~~~text
Hot 7 ngày       ≈ 50 × 7  = 350 GB logic
Archive 90 ngày  ≈ 50 × 90 = 4.500 GB logic
~~~

Nếu hot và archive chồng lấn trong 7 ngày, phải tránh đếm trùng khi tính **tổng dữ liệu logic duy nhất**, nhưng khi tính **dung lượng vật lý thực tế**, mỗi bản sao có thể cần được tính riêng. Thêm replication, compression, index và compaction làm con số khác nhiều.

Không được lấy 350 GB làm quota chắc chắn của hot store nếu TTL đã qua mà compaction/cleanup chưa kịp thu hồi. Cần có headroom cho backlog, peak ingest và phục hồi node.

### 16.2. Retention có thể làm chi phí truy vấn thay đổi

Một collection giữ lịch sử quá lâu có thể tăng index và làm truy vấn lịch sử chậm. Một archive quá lạnh lại khiến việc điều tra nhiều ngày phát sinh chi phí/độ trễ lớn. Quyết định tiering cần căn cứ vào:

- Tần suất truy cập theo tuổi dữ liệu.
- P95/P99 thời gian truy xuất yêu cầu.
- Tỷ lệ replay/backfill.
- Chi phí lưu, truy xuất và vận hành.
- Quy mô tenant nóng và chính sách riêng.

## 17. Observability: làm sao biết vòng đời đang vận hành đúng?

Không nên chỉ nhìn một chỉ số “số record đã xóa” hoặc “job chạy thành công”. Một hệ cần quan sát theo **tuổi dữ liệu, trạng thái, từng kho và từng loại job**.

| Nhóm | Chỉ số cần theo dõi |
|---|---|
| **Creation/ingest** | Số record/giây, duplicate, sai schema, late events |
| **Age distribution** | p50/p95/max tuổi dữ liệu ở hot, số record quá `hotUntil` |
| **TTL/deletion** | Record quá hạn còn tồn tại, delete backlog, retry và lỗi |
| **Archive** | Batch pending, duration, bytes, record count, checksum mismatch |
| **Storage** | Hot/warm/cold size, index size, replication, compaction backlog |
| **Read quality** | P95/p99 theo tuổi dữ liệu, tombstone scan, cache miss |
| **Derived stores** | Search/index lag, số mismatch, replay/catch-up |
| **Deletion requests** | Request theo trạng thái/tuổi, target chưa hoàn tất, ngoại lệ hold |
| **Backup/restore** | Backup age, restore success, RPO/RTO, reapply deletion |
| **Access/security** | Truy cập trái quyền/vùng, archive permission errors |

### 17.1. SLO cần phân biệt các mốc

Một hệ có thể có các mục tiêu riêng:

~~~text
Từ khi hết hạn:
  dữ liệu phải bị từ chối ở API trong giới hạn đã định nghĩa.

Từ khi có yêu cầu xóa hợp lệ:
  quyền truy cập phải được thu hồi trong thời gian X.

Từ khi archive job bắt đầu:
  dữ liệu phải được xác minh và chuyển tầng trong thời gian Y.

Từ khi đủ điều kiện xóa:
  các bản sao thuộc phạm vi mục tiêu phải hoàn tất theo policy/SLO.
~~~

`X` và `Y` cần do nghiệp vụ, vận hành và yêu cầu áp dụng quyết định, không tự gán một con số kỹ thuật chung. SLO **không nên tuyên bố xóa vật lý tức thời** khi DB, replica hoặc backup không cung cấp bảo đảm đó.

### 17.2. Cảnh báo theo backlog và tuổi lớn nhất

Nếu job xử lý 100.000 record/giờ nhưng dữ liệu quá hạn sinh thêm 200.000 record/giờ, backlog vẫn tăng dù dashboard cho thấy “xóa rất nhiều”. Nên đo:

- Số đối tượng quá hạn chưa xử lý.
- Tuổi tối đa của đối tượng chờ.
- Tốc độ đến và tốc độ hoàn tất.
- Error rate theo target.
- Số job cần thao tác thủ công.

Một hệ có throughput cao nhưng **oldest pending deletion** kéo dài có thể vẫn không đạt chính sách.

## 18. Kiểm thử vòng đời theo sự cố và cạnh tranh

Các lỗi thường không nằm ở trường hợp “một record được tạo rồi xóa thuận lợi”.

### 18.1. Clock skew và thời gian

Thử:

- Event tới trễ nhiều giờ/ngày.
- `eventTime` ở tương lai do đồng hồ thiết bị sai.
- UTC offset và giờ địa phương thay đổi do daylight saving.
- Đúng sát ranh giới `expiresAt`.
- TTL không hỗ trợ giá trị vượt phạm vi hoặc âm.

Luôn xác định rõ cách so sánh `now >= deadline`, thời điểm authoritative và đơn vị.

### 18.2. Concurrent update và delete

Trong lúc worker xóa Order cũ, một workflow refund hợp lệ cập nhật Order. Nếu xóa theo query tuổi dữ liệu không xét version/trạng thái, có thể mất thay đổi mới.

Cần điều kiện xóa hoặc khóa/version phù hợp:

~~~text
deleteIfEligible(recordId, expectedVersion, retentionPolicy):
    verify still eligible
    verify no active hold
    conditionally mark/delete
~~~

Mã giả này chưa bảo đảm nếu điều kiện và ghi không nguyên tử; phải dùng cơ chế tương ứng của hệ quản trị.

### 18.3. Archive write thành công, ACK mất

Worker ghi object xong nhưng không nhận response và thử lại. Kiểm tra idempotency qua batchId/objectKey/checksum; không tạo vô hạn bản sao không được quản lý.

### 18.4. Source thay đổi sau khi archive

Thử event đến muộn hoặc bản ghi bị sửa sau high-water mark. Kiểm tra có delta/compensation hoặc policy chặn sửa rõ ràng; không bỏ dữ liệu mới khi xóa bucket cũ.

### 18.5. Consumer bỏ lỡ deletion event

Search index hoặc analytics service tạm offline. Kiểm tra retry, replay, DLQ/quarantine và công cụ đối soát. Không đánh dấu request `COMPLETED` khi một target bắt buộc vẫn còn PENDING.

### 18.6. Restore backup cũ

Khôi phục dữ liệu ở thời điểm trước khi có deletion request rồi thử replay deletion ledger; kiểm tra record bị xóa không được mở lại cho người dùng.

### 18.7. Hold và policy migration

Đặt một record đang chuẩn bị purge vào hold, sau đó gỡ hold. Kiểm tra workflow xử lý đúng trạng thái và quyền; không xóa nhầm hoặc giữ vô hạn vì cờ lỗi.

## 19. Những sai lầm phổ biến

### “Đặt TTL là hoàn thành toàn bộ retention policy”

TTL chỉ là một cơ chế trong một tầng. Nó chưa xử lý archive, search index, backup, legal hold, tác vụ bù nghiệp vụ hoặc xóa theo yêu cầu sớm.

### “Hết TTL nghĩa là mọi byte đã được xóa đúng giây”

Một số hệ xóa background; hệ LSM có expired cells và tombstone chờ compaction. Phải phân biệt logic expiration với physical reclamation.

### “Backup là archive”

Backup nhằm khôi phục sau sự cố, còn archive nhằm giữ và tra cứu lịch sử theo nghiệp vụ. Chúng có SLA, schema, indexing và quyền khác nhau.

### “Đã copy sang archive là có thể xóa nguồn ngay”

Phải xác minh đủ record, checksum, schema đọc được, replication/quyền và xử lý các thay đổi xảy ra trong lúc copy.

### “Chỉ cần xóa ở database chính”

Dữ liệu có thể còn trong cache, search, analytics, object storage, logs, export, backup và thiết bị khác. Cần data inventory và workflow theo scope.

### “Soft delete là xóa thật”

Cờ `isDeleted` có thể chặn hiển thị nhưng record vẫn tồn tại. Các query quên lọc cờ còn có thể lộ dữ liệu.

### “Dữ liệu đã xóa không thể trở lại”

Replica offline, CDC event cũ, cache refill hoặc restore backup có thể đưa dữ liệu cũ trở lại nếu thiếu cơ chế version/tombstone/deletion ledger phù hợp.

### “Dùng TTL để giải phóng tồn kho hoặc hoàn tiền”

TTL không phải một workflow nghiệp vụ đáng tin cậy. Cần timeout, điều phối, idempotency và đối soát.

### “Dữ liệu dẫn xuất không cần quan tâm khi xóa subject”

Search index, analytics hoặc summary có thể chứa thông tin nhận diện trực tiếp hoặc gián tiếp. Cần đánh giá phạm vi xử lý theo mục đích và chính sách.

### “Chuyển sang cold store luôn rẻ hơn”

Lưu lạnh có thể giảm chi phí lưu tại một số workload nhưng tăng chi phí retrieval, egress, phục hồi và vận hành. Cần đo mẫu truy cập.

### “Thay chính sách 90 ngày thành 60 ngày chỉ cần đổi hằng số”

Record cũ, archive, index và các job có thể vẫn theo policy trước; cần version và migration, xử lý collision/trạng thái trung gian và dry-run.

### “Xóa nhiều record cùng lúc không ảnh hưởng performance”

Bulk deletion có thể tạo load trên index, replica, compaction hoặc network. Phải thiết kế batch, rate limit và theo dõi backlog.

### “Một job thành công nghĩa là xóa đã hoàn tất ở mọi nơi”

Job có thể chỉ gửi message hoặc đánh dấu metadata. Trạng thái hoàn tất phải dựa trên kết quả được xác minh từ các target bắt buộc.

## 20. Quy trình ra quyết định cho một collection mới

Trước khi đưa loại dữ liệu mới vào NoSQL:

1. **Đặt tên data category và owner:** ai có trách nhiệm về retention và xóa?
2. **Mô tả mục đích:** ai tạo, ai dùng, truy vấn chính, mức mới của dữ liệu.
3. **Xác định anchor:** createdAt, eventTime, completedAt hay mốc khác.
4. **Chọn hot window:** phải truy cập nhanh trong bao lâu, theo SLO nào?
5. **Chọn archive window:** giữ bao lâu, vì sao, có cần replay/restore không?
6. **Định nghĩa deletion eligibility:** điều kiện trạng thái, quyền, hold, ngoại lệ.
7. **Chọn cấu trúc lưu:** key, partition, time bucket, index, TTL, compaction.
8. **Thiết kế các bản sao:** search, cache, analytics, object storage, backup.
9. **Thiết kế job bền vững:** batch IDs, state, idempotency, retries và đối soát.
10. **Bảo vệ cạnh tranh:** dữ liệu thay đổi trong lúc archive/delete, version và nguồn có thẩm quyền.
11. **Tạo metric/SLO:** backlog, tuổi chờ, kết quả kiểm chứng, read/write latency.
12. **Kiểm tra restore và xóa:** dữ liệu cũ có thể xuất hiện lại không?
13. **Version policy:** thay đổi thời hạn cần migration và kiểm tra ảnh hưởng.

Một bản ghi quyết định mẫu:

~~~text
Data category: telemetry_detail
Owner: Telemetry Service
Source of truth: device_events hot store until archived
Identity: (tenantId, deviceId, eventId)
Primary query: device + time range
Partition: (tenantId, deviceId, dayBucket)

Retention:
  anchor = validated eventTime
  hotUntil = anchor + 7 days
  retainUntil = anchor + 90 days
  policyVersion = telemetry-v3
  lateEventRule = store in proper tier or reject by deadline

Archive:
  object partitioned by tenant and day
  manifest with schema, count, checksum, source boundary
  retry by deterministic archiveBatchId
  remove hot only after verification and policy check

Deletion:
  revoke access when required
  coordinate primary, cache, index, archive and copies
  hold/exception reviewed according to policy
  restore pipeline reapplies valid deletion decisions

Monitoring:
  oldest expired hot record
  pending archive and delete jobs
  checksum mismatches, target failures
  compaction and disk headroom
~~~

Mẫu trên chỉ là một lựa chọn kiến trúc. Với dữ liệu nghiệp vụ, sự kiện giao dịch hoặc nghĩa vụ lưu giữ khác, retention và thao tác xóa phải được xác định lại từ yêu cầu thực.

## 21. Bài tập thực hành

### Bài 1 — TTL và event đến muộn

Một thiết bị tạo event lúc 08:00 ngày 1, nhưng tới 08:00 ngày 4 mới gửi. Chính sách yêu cầu hot 7 ngày và archive tới ngày 90, tính từ **eventTime**.

Hãy:

1. Tính deadline hot và deadline archive.
2. Giải thích vì sao ghi TTL 7 ngày kể từ ngày 4 làm sai chính sách.
3. Đề xuất cách xử lý event đã vượt hot deadline nhưng chưa vượt archive deadline.
4. Mô tả cách kiểm tra eventTime từ thiết bị không đáng tin.

### Bài 2 — Chọn mô hình hot và archive

Hệ thống nhận 100 triệu sự kiện mỗi ngày; UI chỉ cần 24 giờ gần nhất, đội vận hành cần điều tra tới 180 ngày.

Hãy đề xuất partition/time bucket, hot window, archive format, manifest, cách truy xuất lịch sử và phương pháp đo chi phí so với việc giữ tất cả ở hot NoSQL.

### Bài 3 — Lỗi giữa quá trình archive

Worker ghi xong file archive nhưng chết trước khi đánh dấu `VERIFIED`. Khi chạy lại, nó nhận cùng batch.

Hãy thiết kế batchId, objectKey, checksum, trạng thái và cách retry idempotent. Khi nào được phép xóa dữ liệu hot?

### Bài 4 — Xóa một tài khoản

Một user có profile trong document DB, avatar ở object storage, search record, cache, analytics và backup.

Hãy lập bản đồ target, đề xuất deletion request state machine, xác định điều kiện hoàn tất và mô tả cách ngăn restore backup hồi sinh profile cũ.

### Bài 5 — Soft delete và security

Một user bị khóa truy cập nhưng background deletion cần vài giờ. Một API đọc trực tiếp collection và một API khác đọc search index.

Hãy giải thích tại sao chỉ đặt `isDeleted=true` ở primary có thể chưa đủ và đề xuất phương án chặn truy cập có thẩm quyền, invalidation và đối soát.

### Bài 6 — Reservation hết hạn

Hệ thống giữ 3 đơn vị tồn kho cho một đơn trong 15 phút. Bản ghi reservation có TTL 900 giây, nhưng job timeout đôi khi chạy lặp hoặc mất kết nối.

Hãy thiết kế luồng release idempotent, cách lưu trạng thái, phương pháp ngăn cộng lại kho hai lần và lý do không thể chỉ dựa vào TTL.

### Bài 7 — Đổi retention policy

Policy cũ giữ telemetry 120 ngày, policy mới giữ 60 ngày. Hệ có archive object theo tháng và các tenant có hợp đồng khác nhau.

Hãy xác định phạm vi migration, cách tính deadline theo policy version, dry-run phát hiện khác biệt, và cách tránh xóa nhầm dữ liệu đang chịu ngoại lệ hợp lệ.

### Bài 8 — Restore và deletion ledger

Ngày 10 một user bị xóa hợp lệ. Ngày 12 hệ phải restore backup từ ngày 8. Một CDC worker còn sự kiện UserUpdated từ ngày 9.

Hãy giải thích các đường có thể làm user xuất hiện lại và đề xuất version/ledger/reconciliation để ngăn replay sự kiện cũ hồi sinh dữ liệu.

### Bài 9 — Dung lượng và TTL

Một pipeline ingest 50 GB dữ liệu logic/ngày, giữ hot 7 ngày, archive tới 90 ngày. Hot có replication factor 3; archive có định dạng nén và có phí retrieval.

Hãy ước lượng dung lượng logic hot và archive trước overhead, chỉ ra các thành phần vật lý chưa được tính, và nêu vì sao số byte hot không nhất thiết giảm ngay khi TTL hết hạn.

### Bài 10 — Dữ liệu dẫn xuất

Raw event giữ 7 ngày, DailySummary giữ 2 năm. Job tổng hợp bị lỗi 10 ngày, không có archive.

Hãy phân tích khả năng backfill, thời điểm phát hiện lỗi ảnh hưởng kết quả thế nào, và đề xuất lại retention của raw data hoặc phương án archive/replay.

---

**Kết luận:** Quản lý vòng đời dữ liệu trong NoSQL là quá trình **thiết kế từ lúc ghi đầu tiên cho tới khi dữ liệu không còn được truy cập hoặc được thu hồi đúng phạm vi**. TTL giúp diễn đạt một hạn sử dụng ở một tầng nhưng không thay thế retention policy, archive, transaction nghiệp vụ, xóa trên nhiều bản sao hay kiểm thử restore. Một thiết kế đáng tin phải nêu rõ **mốc thời gian, nguồn có thẩm quyền, những nơi dữ liệu được sao chép, điều kiện chuyển tầng và điều kiện xác nhận xóa**. Khi kết hợp ranh giới dữ liệu theo thời gian, workflow idempotent, version hóa policy, kiểm soát quyền và đối soát vận hành, hệ thống vừa phục vụ tốt truy vấn hiện tại vừa giữ được khả năng khôi phục và xóa dữ liệu theo mục đích đã xác định.
