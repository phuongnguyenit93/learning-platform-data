# Message retention và quản lý backlog trong Google Cloud Pub/Sub

Một hệ thống bán lẻ gửi sự kiện `order.created` từ **Cloud Run** lên **Google Cloud Pub/Sub**. Các worker trên **GKE** xử lý hóa đơn và cập nhật **Cloud SQL**, một pipeline khác ghi dữ liệu phân tích vào **Cloud Storage**. Trong đợt khuyến mãi, publisher phát thông điệp nhanh hơn worker xử lý. Backlog tăng, người dùng nhận hóa đơn muộn; nếu tình trạng kéo dài quá thời gian lưu, một số thông điệp có thể không còn được giao. Đội vận hành cần trả lời: **thông điệp được giữ bao lâu, backlog đang tăng vì sao, khi nào phải scale, và nếu subscriber xử lý sai có thể phát lại không?**

Bài học thuộc chương **Pub/Sub và thông điệp** của mô-đun **CLOUD_PROVIDERS_GCP**. Nội dung kết nối kiến thức về project/IAM, Cloud Run, GKE, Compute Engine, mạng, lưu trữ và cơ sở dữ liệu với thiết kế hệ thống bất đồng bộ có khả năng phục hồi, theo dõi độ tin cậy và kiểm soát chi phí. Trọng tâm là **message retention và quản lý backlog**; các ví dụ và bài tập được viết tự chứa, cô đọng để áp dụng trong thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **topic retention**, **subscription retention**, **retain acknowledged messages**, **subscription expiration** và **ack deadline**.
2. Hiểu vì sao thông điệp quá thời hạn lưu có thể bị xóa **dù chưa ack**, và tại sao replay cần được thiết kế từ trước.
3. Đọc các metric backlog như **số thông điệp unacked**, **tuổi thông điệp unacked cũ nhất** và **delivery latency health score**.
4. Ước lượng năng lực xử lý cần thiết để backlog ngừng tăng và được giải phóng trước khi dữ liệu hết hạn.
5. Điều chỉnh **flow control, concurrency, số subscriber, retry, dead-letter topic** mà không làm Cloud SQL hoặc API đối tác quá tải.
6. Dùng **snapshot** và **seek** để replay/khôi phục có kiểm soát, đồng thời áp dụng idempotency để tránh tác dụng phụ trùng.
7. Cấu hình thử nghiệm bằng `gcloud`, phân tích lỗi và lập checklist vận hành production.

## 2. Mô hình Pub/Sub và vòng đời thông điệp

### 2.1. Topic không phải subscription

~~~mermaid
flowchart LR
    P["Publisher: Cloud Run"] --> T["Topic: orders-events"]
    T --> S1["Subscription: invoices-sub"]
    T --> S2["Subscription: analytics-sub"]
    S1 --> W["GKE invoice workers"]
    S2 --> A["Analytics processor"]
    W --> DB["Cloud SQL"]
    A --> GCS["Cloud Storage"]
~~~

- **Publisher** ghi message vào **topic**.
- Mỗi **subscription** nhận luồng thông điệp riêng từ topic theo cấu hình. Ack của `invoices-sub` **không ack hộ** `analytics-sub`.
- **Subscriber** nhận message, thực hiện xử lý nghiệp vụ rồi gửi **ack** khi công việc đã hoàn tất an toàn.
- **Backlog** là tập thông điệp chưa được xác nhận thành công trong subscription (có thể gồm message chờ được phát và message đang xử lý).

Đây là Pub/Sub chuẩn, không phải hàng đợi có một consumer duy nhất cho toàn bộ topic. Nếu hai ứng dụng cùng dùng **một subscription** để pull, chúng cùng chia công việc của subscription đó; nếu mỗi ứng dụng có **subscription riêng**, cả hai nhận bản giao theo trạng thái riêng.

### 2.2. Ba loại thời gian dễ bị nhầm

| Khái niệm | Đơn vị/thời điểm | Ý nghĩa |
| --- | --- | --- |
| **Message retention duration** | Tính theo **thời điểm message được publish**. | Thời gian Pub/Sub có thể giữ message theo policy topic/subscription. |
| **Acknowledgment deadline** | Giây sau khi một message được giao. | Thời hạn subscriber cần ack hoặc gia hạn lease; quá hạn có thể bị giao lại. |
| **Subscription expiration period** | Thời gian subscription không hoạt động. | Thời điểm subscription có thể bị xóa vì không hoạt động; **khác** message retention. |

**Ví dụ:** message được publish lúc 09:00, subscription lưu 7 ngày và ack deadline là 30 giây. Nếu worker nhận lúc 09:05 nhưng chưa ack sau 30 giây, message có thể bị giao lại; nó **không** được giữ thêm 7 ngày kể từ mỗi lần retry. Mốc retention vẫn gắn với thời điểm publish ban đầu.

## 3. Subscription retention và topic retention

### 3.1. Subscription retention: bảo vệ backlog của từng consumer

Theo tài liệu Pub/Sub hiện hành:

| Thuộc tính | Giá trị |
| --- | --- |
| Subscription retention mặc định | **7 ngày** cho thông điệp chưa ack. |
| Retention có thể cấu hình | **10 phút đến 31 ngày**. |
| Mặc định sau khi ack | Message không còn khả dụng để pull lại qua subscription. |
| `retain acknowledged messages` | Giữ cả message đã ack trong cửa sổ retention để hỗ trợ replay. |
| Subscription expiration mặc định | **31 ngày** không hoạt động; có thể cấu hình theo quy định dịch vụ. |

Một message có thể bị loại bỏ sau khi vượt thời hạn lưu **ngay cả khi chưa được ack**. Tăng retention giúp nới cửa sổ khắc phục sự cố nhưng **không làm subscriber xử lý nhanh hơn**, không bảo đảm giữ dữ liệu vô hạn và có thể phát sinh storage charges. <https://cloud.google.com/pubsub/docs/subscription-properties>

### 3.2. Topic retention: giữ ở cấp nguồn sự kiện

**Topic message retention** mặc định **không bật**. Khi bật, topic giữ message sau khi publish trong cửa sổ cấu hình **10 phút đến 31 ngày**, độc lập với việc các subscriptions đã ack hay chưa. Nhờ đó, những subscription phù hợp có thể replay message đã ack hoặc message được publish trước thời điểm tạo subscription, miễn vẫn còn trong khoảng thời gian lưu. <https://cloud.google.com/pubsub/docs/topic-message-retention>

Khi **cùng có topic retention và subscription retention**, cần xét **thời hạn giữ dài hơn** theo quy tắc Pub/Sub; không giả định cứ subscription hết 7 ngày là message sẽ không bao giờ còn khả năng khôi phục khi topic đang giữ lâu hơn. Ngược lại, nếu cả hai cửa sổ đều đã trôi qua và message bị expunge thì **seek không thể tạo lại dữ liệu không còn được lưu**.

### 3.3. Chọn ở topic hay subscription?

| Yêu cầu | Phương án cân nhắc | Tác động |
| --- | --- | --- |
| Một consumer cần thêm thời gian xử lý backlog | Tăng subscription retention phù hợp. | Bảo vệ subscription đó, cần giám sát tuổi message. |
| Nhiều consumers cần replay chung lịch sử publish | Bật topic retention. | Lưu một nguồn dữ liệu cấp topic cho các subscription đủ điều kiện; topic project chịu phí tương ứng. |
| Một subscription cần phát lại message đã ack | `retain-acked-messages` hoặc topic retention. | Cho phép `seek` khi message vẫn được giữ; phát sinh chi phí storage theo tính năng. |
| Cần lưu dữ liệu nhiều tháng/nhiều năm | Thiết kế export/archival sang Cloud Storage hoặc kho bền vững khác. | Pub/Sub retention tối đa 31 ngày, **không phải hệ thống lưu trữ hồ sơ dài hạn**. |

**Đừng bật cả topic retention dài và giữ acknowledged messages dài trên nhiều subscriptions theo thói quen.** Hãy xác định yêu cầu replay thực tế và dự toán từng khoản phí.

### 3.4. Subscription expiration không phải retention

Một subscription **không có hoạt động subscriber và không được cập nhật** có thể hết hạn sau thời gian expiration, mặc định là **31 ngày**. Một subscription bị xóa rồi tạo lại **cùng tên** không tự phục hồi backlog trước đó. Với subscription phục vụ DR hoặc consumer hoạt động rất thưa, cần đặt expiration policy đúng ý định và kiểm tra cả data retention. <https://cloud.google.com/pubsub/docs/subscription-overview>

## 4. Ack deadline, retry và dead-letter là các cơ chế khác nhau

### 4.1. Ack chỉ sau khi đã commit

~~~mermaid
sequenceDiagram
    participant PS as Pub/Sub
    participant W as Subscriber
    participant DB as Cloud SQL
    PS->>W: Deliver message
    W->>DB: Ghi tác vụ bằng transaction / idempotency key
    DB-->>W: Commit thành công
    W-->>PS: Acknowledge
    Note over PS,W: Nếu không ack đúng hạn, message có thể được giao lại
~~~

Ack **trước** khi ghi xong Cloud SQL có thể khiến message bị coi là đã xử lý dù giao dịch thất bại. Ack **sau** khi commit bảo vệ kết quả hơn, nhưng nếu worker chết giữa commit và ack, message vẫn có thể được giao lại: do đó subscriber phải **idempotent**.

### 4.2. Ack deadline không tăng thời gian lưu

Ack deadline mặc định là **10 giây**, cấu hình ban đầu được hỗ trợ trong khoảng **10–600 giây**. Client libraries có thể **gia hạn ack deadline** cho message đang xử lý bằng lease management; thời gian retention tính theo publish time vẫn không đổi. Đặt ack deadline quá ngắn dễ gây duplicate delivery, quá dài có thể khiến việc phát lại message bị lỗi chậm trễ. <https://cloud.google.com/pubsub/docs/subscription-properties>

### 4.3. Retry và backoff

Khi subscriber **nack** hoặc quá ack deadline, Pub/Sub có thể giao lại message. Subscription retry policy có thể là **retry immediately** hoặc **exponential backoff**, tùy cấu hình. Với push subscription, còn có cơ chế **push backoff** ảnh hưởng nhịp redelivery.

| Loại lỗi | Cách xử lý nên cân nhắc |
| --- | --- |
| Cloud SQL tạm quá tải | Retry có backoff, jitter/giới hạn concurrency, không tạo retry storm. |
| API đối tác trả 429 | Tôn trọng rate limit, backoff và giám sát retry lag. |
| Payload JSON sai schema vĩnh viễn | Không retry vô hạn; lưu chẩn đoán và dùng dead-letter path. |
| Người dùng không có quyền thao tác | Ghi lỗi hợp lệ/idempotent, không cố retry để vượt quyền. |

**Retry không phải retention.** Một message có thể bị retry nhiều lần rồi vẫn hết thời gian lưu; việc tăng số retry không khắc phục năng lực subscriber thiếu hụt.

### 4.4. Dead-letter topic (DLQ)

**Dead-letter topic** được cấu hình ở **subscription nguồn** để chuyển message không xử lý được sang topic riêng phục vụ điều tra. `maxDeliveryAttempts` thường được đặt trong khoảng **5–100**; số lần thực tế là **best effort**, không phải bộ đếm cứng tuyệt đối. Khi cấu hình sai IAM cho Pub/Sub service agent, việc đếm/chuyển DLQ có thể không hoạt động đúng. <https://cloud.google.com/pubsub/docs/dead-letter-topics>

~~~mermaid
flowchart LR
    S["orders-sub"] --> W["Subscriber"]
    W -- "Thành công / ack" --> DONE["Hoàn thành"]
    W -- "Lỗi, hết hạn ack / retry" --> S
    S -- "Vượt số lần giao dự kiến" --> DLQ["orders-dlq topic"]
    DLQ --> DLS["DLQ subscription + điều tra"]
~~~

DLQ giúp **cách ly poison messages**, không tự sửa payload và không thay thế backup. Phải tạo **subscription gắn với DLQ topic** để thực sự đọc được các message được chuyển; thiết kế thời gian giữ, IAM, cảnh báo và quy trình replay riêng. Khi redrive từ DLQ, phải chống tạo trùng tác dụng phụ như với mọi retry.

## 5. Backlog là tín hiệu, không chỉ là số lượng message

### 5.1. Các metric quan trọng trong Cloud Monitoring

Google Cloud khuyến nghị sử dụng những metric Pub/Sub **theo region** khi theo dõi backlog, giúp dashboard tiếp tục có tín hiệu từ các region khác nếu một vùng gặp sự cố:

| Cloud Monitoring metric | Diễn giải | Tín hiệu |
| --- | --- | --- |
| `pubsub.googleapis.com/subscription/num_unacked_messages_by_region` | Số message unacked theo region. | Quy mô backlog đang tồn. |
| `pubsub.googleapis.com/subscription/oldest_unacked_message_age_by_region` | Tuổi (giây) của message unacked cũ nhất theo region. | Mức chậm trễ và nguy cơ chạm retention. |
| `pubsub.googleapis.com/subscription/delivery_latency_health_score` | Tình trạng các yếu tố ảnh hưởng delivery latency. | Khoanh vùng vấn đề delivery. |
| `pubsub.googleapis.com/topic/num_retained_messages` | Số message topic đang giữ khi bật retention. | Dung lượng dữ liệu topic được giữ. |

Tên và khả năng hỗ trợ metric nên được xác minh tại <https://cloud.google.com/pubsub/docs/monitoring>. Các metric có thể có **khoảng trống dữ liệu vài phút**; một điểm đo đơn lẻ không phản ánh toàn bộ trạng thái. Với các metric `by_region`, thiết lập alert theo nhãn region và quy tắc tổng hợp có chủ đích.

### 5.2. Đọc kết hợp số lượng và tuổi

| Số unacked | Tuổi message cũ nhất | Khả năng cao | Hành động |
| --- | --- | --- | --- |
| Tăng | Tăng | Publish nhanh hơn năng lực ack, subscriber lỗi hoặc nghẽn downstream. | Đo publish/ack rate, scale subscriber và kiểm tra dependencies. |
| Nhỏ, tương đối ổn định | Tăng | Một số **poison/stuck messages** không xử lý được. | Xem error logs, delivery attempts, DLQ. |
| Cao nhưng đang giảm | Giảm | Hệ thống đang giải phóng backlog. | Theo dõi drain ETA và nguy cơ retention. |
| Gần 0 | Thấp | Có thể bình thường, hoặc publisher không còn gửi. | So với publish rate và mục tiêu nghiệp vụ. |
| Bất kỳ | Gần mức retention | **Nguy cơ message hết hạn và mất dữ liệu**. | Ưu tiên xử lý incident và phương án lưu/khôi phục theo chính sách. |

**Không chỉ alert khi số message vượt một ngưỡng cố định.** Một triệu message có thể chấp nhận được với hệ thống xử lý hàng triệu message mỗi giây, nhưng nguy hiểm đối với consumer chỉ xử lý vài message/giây.

### 5.3. Hai tỷ lệ quyết định backlog

Gọi:

- \(\lambda\): tốc độ publish vào subscription (message/giây).
- \(\mu\): tốc độ **xử lý thành công và ack** bền vững (message/giây).
- \(B\): số lượng message backlog.

Trong một giai đoạn đủ ổn định, có thể ước lượng:

~~~text
Tốc độ đổi backlog ≈ lambda - mu

Nếu mu > lambda:
  Thời gian giải phóng backlog ≈ B / (mu - lambda)

Nếu mu <= lambda:
  Backlog không thể giảm bền vững chỉ bằng cách chờ.
~~~

**Ví dụ giả định:** backlog 120.000 message; publisher tiếp tục gửi 300 message/s; workers xử lý và ack được 500 message/s. Tốc độ giảm thuần là 200 message/s, nên cần khoảng **600 giây = 10 phút** để giải phóng backlog, *nếu tốc độ không đổi và không có retry/poison message đáng kể*. Thực tế phải tính độ biến thiên traffic, kích thước message, latency database, lỗi và giới hạn quota.

Để bảo vệ retention, cần so sánh **tuổi oldest unacked** với **thời gian retention còn lại**, không chỉ so drain ETA tính từ backlog tổng.

## 6. Hành động khi backlog tăng

### 6.1. Xác định nút thắt trước khi scale

~~~mermaid
flowchart TD
    A["Backlog / oldest age tăng"] --> B{"Publish tăng hay ack giảm?"}
    B -->|Publish tăng| C["Kiểm tra khả năng scale + quota"]
    B -->|Ack giảm| D["Logs, lỗi, downstream, leases"]
    C --> E["Thêm subscriber / tối ưu xử lý"]
    D --> F{"Lỗi tạm hay poison?"}
    F -->|Tạm| G["Backoff + giới hạn concurrency"]
    F -->|Poison| H["DLQ + điều tra"]
    E --> I["Đo lại ack rate, tuổi backlog, SLO"]
    G --> I
    H --> I
~~~

Nếu Cloud SQL đã đạt giới hạn kết nối, tăng từ 10 lên 100 workers có thể khiến **ack rate thực tế giảm** vì thêm retries. Tối ưu đúng chỗ có thể là giảm pool size, batch writes, điều chỉnh concurrency hoặc tăng năng lực database trước khi thêm subscribers.

### 6.2. Pull subscribers: flow control và lease management

Với pull/StreamingPull:

- Ưu tiên **client libraries** để xử lý connection, lease extension, batching và flow control.
- Giới hạn **outstanding messages** và **outstanding bytes** theo bộ nhớ/CPU của worker.
- Ack **sau** khi đã commit xử lý; nack hoặc để retry đối với lỗi tạm thời theo chính sách.
- Điều chỉnh số threads/streams/instances theo năng lực xử lý thật, tránh `OOM` vì kéo quá nhiều message.
- Đặt timeout và retry của Cloud SQL/Cloud Storage/HTTP client phù hợp; tăng ack deadline không tự chữa được dependency chậm.

~~~text
Publisher → Pub/Sub → StreamingPull → bounded worker pool → commit → ack
                                ↑
                max outstanding messages / bytes
~~~

**Backpressure** làm người nhận không lấy quá nhiều message vượt sức xử lý; nó giúp ổn định hệ thống nhưng có thể làm backlog tăng tạm thời. Cần kết hợp với autoscaling và cảnh báo trước ngưỡng retention.

### 6.3. Push subscribers: HTTP response và khả năng nhận tải

Với **push subscription** gửi tới Cloud Run/HTTP endpoint:

- Endpoint phản hồi mã **HTTP thành công được Pub/Sub coi là ack** theo cơ chế push, chỉ sau khi xử lý bền vững.
- Lỗi HTTP, timeout hoặc response không được chấp nhận dẫn tới redelivery theo push/retry policy.
- Cấu hình Cloud Run **concurrency/min/max instances** và downstream capacity để chịu event bursts.
- Dùng **OIDC token/service account** để xác thực Pub/Sub push tới endpoint khi triển khai bảo mật.
- Nếu xử lý dài hơn timeout yêu cầu, cân nhắc **pull worker** hoặc workflow async phù hợp thay vì giữ request HTTP quá lâu.

Không trả `2xx` ngay khi nhận request nếu ứng dụng chưa lưu message vào một nơi bền vững mà vẫn muốn Pub/Sub bảo đảm retry khi xử lý lỗi.

### 6.4. Alert gắn với retention budget

Giả sử subscription lưu 7 ngày nhưng SLO yêu cầu xử lý trong 10 phút:

1. **SLO alert sớm:** oldest unacked vượt vài phút và đang tăng, bất kể còn xa retention.
2. **Capacity alert:** \(\mu \le \lambda\) trong một cửa sổ đủ dài; các worker/ngõ ra nghẽn.
3. **Safety alert:** oldest unacked tiến gần retention; ưu tiên xử lý nguy cơ mất message, không chờ tới khi đủ 7 ngày.
4. **DLQ alert:** message xuất hiện ở DLQ hoặc tỷ lệ retry/ack deadline expiration tăng.

Ngưỡng phải lấy từ **SLO, traffic profile, retention configuration và thời gian tăng capacity thật**, không sao chép một con số cho mọi subscription.

## 7. Replay: seek và snapshot

### 7.1. `seek` theo thời điểm

`seek` thay đổi **trạng thái ack** hàng loạt trên subscription cho những message còn được giữ:

- Seek về thời điểm **trong quá khứ** có thể làm những message đã ack trở thành có thể nhận lại khi đã bật **topic retention** hoặc **retain-acked-messages**.
- Seek tới thời điểm **trong tương lai** có thể đánh dấu hàng loạt message là đã ack, tức **bỏ qua backlog**; thao tác này có rủi ro mất cơ hội xử lý dữ liệu.
- Seek không hồi sinh message đã hết retention và bị expunge.

Seek có thể mất một khoảng thời gian để có hiệu lực đối với delivery đang diễn ra; sau seek có thể còn thấy message “cũ” trong thời gian ngắn. **Không dùng seek để xóa backlog production chỉ nhằm làm dashboard đẹp hơn.** <https://cloud.google.com/pubsub/docs/replay-overview>

### 7.2. Snapshot lưu ack state, không phải bản sao vĩnh viễn

**Snapshot** ghi nhận trạng thái ack của subscription tại một thời điểm và hỗ trợ khôi phục/replay. Snapshot có tuổi thọ tối đa **7 ngày**, có thể ngắn hơn theo **tuổi message unacked cũ nhất** lúc tạo. Với backlog quá cũ, snapshot có thể không được tạo vì thời gian hữu dụng còn lại quá ngắn. <https://cloud.google.com/pubsub/docs/replay-overview>

| Cơ chế | Khi phù hợp | Giới hạn |
| --- | --- | --- |
| Seek theo timestamp | Có retention phù hợp, muốn phát lại từ thời điểm publish. | Không chính xác theo business event time; có thể redeliver nhiều message. |
| Seek theo snapshot | Muốn quay về trạng thái ack đã chụp trước rollout. | Snapshot phải được tạo trước; TTL hữu hạn; message vẫn cần idempotency. |
| Subscription mới | Thêm consumer độc lập cho tương lai hoặc replay khi topic retention cho phép. | Không tự có lịch sử không còn được giữ ở topic. |
| Export/backup | Cần lưu lâu hơn 31 ngày hoặc kiểm toán độc lập. | Cần quản lý Cloud Storage, IAM, retention, chi phí và khôi phục. |

### 7.3. Replay không phải exactly-once nghiệp vụ

Pub/Sub có **exactly-once delivery** trong những điều kiện hỗ trợ cho pull subscriptions, nhưng nó không tự bảo đảm side effect trên Cloud SQL, HTTP partner hoặc Cloud Storage chỉ xảy ra một lần. Một lần commit thành công nhưng ack thất bại vẫn cần cơ chế idempotency. Seek/replay có thể chủ động khiến message được nhận lại ngay cả khi đã xử lý trước đó.

**Thiết kế thực tế:** xác định business idempotency key (`orderId` + event type + version), dùng transaction/unique constraint để ghi kết quả và chỉ ack sau khi commit.

## 8. Thực hành `gcloud pubsub` trong project lab

Các lệnh minh họa dùng **Bash**, resource IDs giả định. `create`, `update`, `publish`, `seek`, `delete` là **thao tác ghi, có thể phát sinh phí hoặc thay đổi dữ liệu**. Chỉ chạy trong project được phép; **không thử `seek` trên subscription production** để học vì nó thay đổi trạng thái giao message hàng loạt.

### 8.1. Kiểm tra context và tài nguyên hiện hữu

~~~bash
PROJECT_ID="retail-lab"
TOPIC="orders-events-lab"
SUB="invoices-sub-lab"

# READ-ONLY: principal/project đang dùng.
gcloud auth list
gcloud config get-value project

# READ-ONLY: liệt kê topic và subscription có quyền xem.
gcloud pubsub topics list --project="$PROJECT_ID"
gcloud pubsub subscriptions list --project="$PROJECT_ID"
~~~

### 8.2. Tạo topic và subscription với retention

~~~bash
# WRITE: chỉ dùng tên chưa tồn tại, project lab.
gcloud pubsub topics create "$TOPIC" \
  --project="$PROJECT_ID"

# WRITE: một subscription pull, lưu 7 ngày, ban đầu không giữ acked.
gcloud pubsub subscriptions create "$SUB" \
  --project="$PROJECT_ID" \
  --topic="$TOPIC" \
  --message-retention-duration=7d \
  --ack-deadline=30

# READ-ONLY: xác minh các thuộc tính.
gcloud pubsub subscriptions describe "$SUB" \
  --project="$PROJECT_ID" \
  --format=yaml
~~~

Nếu dự kiến nhiều người cùng dùng lab, chọn tài nguyên tên duy nhất theo chính sách. Subscription giữ thông điệp **từ khi được tạo** (trừ khi có lịch sử topic retention đủ điều kiện và thao tác replay); không tự nhận toàn bộ lịch sử của topic trước đó.

### 8.3. Bật replay theo nhu cầu

~~~bash
# WRITE: bật topic retention 14 ngày, phí lưu topic có thể tăng.
gcloud pubsub topics update "$TOPIC" \
  --project="$PROJECT_ID" \
  --message-retention-duration=14d

# WRITE: cho phép subscription giữ message đã ack theo cửa sổ của nó.
gcloud pubsub subscriptions update "$SUB" \
  --project="$PROJECT_ID" \
  --message-retention-duration=7d \
  --retain-acked-messages

# READ-ONLY: đối chiếu topic + subscription sau thay đổi.
gcloud pubsub topics describe "$TOPIC" --project="$PROJECT_ID"
gcloud pubsub subscriptions describe "$SUB" --project="$PROJECT_ID"
~~~

Trong production, không bật cả hai cơ chế một cách mặc định: chọn theo consumer cần replay, thời gian và chi phí. Thay đổi retention **không khôi phục message đã bị expunge trước đó**. Khi điều chỉnh subscription retention/expiration policy phải đảm bảo các thời hạn tương thích.

### 8.4. Publish và pull thử

~~~bash
# WRITE: tạo dữ liệu thử nghiệm.
gcloud pubsub topics publish "$TOPIC" \
  --project="$PROJECT_ID" \
  --message='{"eventType":"order.created","orderId":"O-1001"}' \
  --attribute=source=lab

# READ+ACK WRITE: --auto-ack chỉ dùng trong lab.
gcloud pubsub subscriptions pull "$SUB" \
  --project="$PROJECT_ID" \
  --limit=10 \
  --auto-ack
~~~

**`--auto-ack` đánh dấu message đã xử lý khi nhận về CLI**, không thực hiện nghiệp vụ Cloud SQL. Không dùng lệnh này để “xử lý” backlog production: message có thể bị ack mà chưa có side effect nào được commit.

### 8.5. Snapshot và seek trong lab

~~~bash
SNAPSHOT="invoices-before-release-lab"

# WRITE: ghi lại ack state, snapshot có TTL hữu hạn.
gcloud pubsub snapshots create "$SNAPSHOT" \
  --project="$PROJECT_ID" \
  --subscription="$SUB"

# READ-ONLY: xem snapshot.
gcloud pubsub snapshots describe "$SNAPSHOT" \
  --project="$PROJECT_ID"

# WRITE: khôi phục ack state từ snapshot, ảnh hưởng message delivery.
gcloud pubsub subscriptions seek "$SUB" \
  --project="$PROJECT_ID" \
  --snapshot="$SNAPSHOT"
~~~

Snapshot nên được tạo **trước** khi deploy subscriber version nhạy cảm; nếu tạo sau khi code lỗi đã ack sai hàng loạt, nó không tự quay lại trạng thái trước sự cố. `seek` theo thời điểm cũng khả dụng, ví dụ `--time=2026-11-19T00:00:00Z`, nhưng thời điểm phải nằm trong cửa sổ dữ liệu còn giữ và được chủ động phê duyệt.

### 8.6. Dead-letter cho subscription mới

Ví dụ quy trình:

~~~bash
DLQ_TOPIC="orders-dlq-lab"
DLQ_SUB="orders-dlq-reader-lab"
SOURCE_SUB="invoices-with-dlq-lab"

# WRITE: tạo nơi giữ message lỗi và một consumer để đọc DLQ.
gcloud pubsub topics create "$DLQ_TOPIC" --project="$PROJECT_ID"
gcloud pubsub subscriptions create "$DLQ_SUB" \
  --project="$PROJECT_ID" --topic="$DLQ_TOPIC"

# WRITE: subscription có dead-letter topic và số lần thử.
gcloud pubsub subscriptions create "$SOURCE_SUB" \
  --project="$PROJECT_ID" \
  --topic="$TOPIC" \
  --dead-letter-topic="$DLQ_TOPIC" \
  --max-delivery-attempts=10
~~~

**Chưa đủ để DLQ chạy production:** phải cấp các quyền cần thiết cho **Pub/Sub service agent** của project subscription trên DLQ topic và source subscription theo tài liệu; kiểm tra IAM với cross-project DLQ. Không cấp `roles/pubsub.admin` rộng chỉ để sửa DLQ. Theo dõi DLQ subscription riêng, retention và runbook redrive/idempotency.

## 9. Ví dụ consumer idempotent: Java và Cloud SQL

Giả sử mỗi message có `eventType=order.created`, `eventId`, `orderId`. Worker Java có thể dùng Pub/Sub client library với StreamingPull và **bounded executor**; pseudo-code dưới đây mô tả thứ tự nghiệp vụ, không phải source code có thể biên dịch ngay:

~~~java
void onMessage(Message m, AckReply ack) {
    try {
        String eventId = required(m.attributes(), "eventId");
        String orderId = parseAndValidateOrder(m.data());

        database.transaction(tx -> {
            // Bảng processed_events có UNIQUE(event_id).
            if (tx.insertProcessedEventIfAbsent(eventId)) {
                tx.createInvoiceIfAbsent(orderId);
            }
        });

        // Chỉ ack khi DB commit thành công.
        ack.ack();
    } catch (InvalidPayloadException permanent) {
        // Ghi log có redaction và cho DLQ/quy trình xử lý lỗi cố định;
        // không trả ACK thành công nếu chưa lưu kết quả lỗi bền vững.
        ack.nack();
    } catch (TransientException temporary) {
        ack.nack(); // Pub/Sub retry/backoff; không spin vô hạn.
    }
}
~~~

**Lưu ý kỹ thuật:** một retry sau DB commit có thể gặp lại cùng `eventId`. Unique constraint làm thao tác ghi tác dụng phụ không bị lặp; nhưng nếu workflow còn **gọi đối tác ngoài transaction**, cần outbox/unique delivery key hoặc cơ chế idempotency ở API đối tác. Không đồng nhất `messageId` với business ID khi publisher có thể phát **hai message khác nhau** cho cùng sự kiện nghiệp vụ.

## 10. Tình huống tổng hợp: backlog trong giờ cao điểm

### 10.1. Bối cảnh

Pipeline nhận sự kiện đơn hàng:

~~~mermaid
flowchart TB
    RUN["Cloud Run: orders API"] --> TOPIC["Topic: orders-events"]
    TOPIC --> INV["Subscription: invoices"]
    TOPIC --> ANA["Subscription: analytics"]
    INV --> GKE["GKE invoice workers"]
    GKE --> SQL["Cloud SQL"]
    ANA --> STORE["Analytics → Cloud Storage"]
    DL["DLQ: invoice-poison-events"] -. "Thông điệp lỗi không xử lý được" .-> INV
    MON["Cloud Monitoring"] -. "Backlog/oldest age/retries/DB" .-> INV
~~~

Trong 15 phút cao điểm (số giả định):

| Tín hiệu | Giá trị giả định | Nhận định |
| --- | ---: | --- |
| Publish rate | 400 msg/s | Tăng mạnh so với ban ngày. |
| Ack rate | 250 msg/s | Worker không theo kịp; backlog tăng ~150 msg/s. |
| Backlog sau 15 phút nếu tốc độ không đổi | 135.000 message | `150 × 900` message mới chưa xử lý. |
| Subscription retention | 7 ngày | Còn xa giới hạn mất dữ liệu, nhưng SLO vẫn có thể bị vi phạm. |
| SLO hóa đơn | 5 phút | Cần xử lý năng lực ngay, không chờ đến ngày thứ bảy. |

### 10.2. Cách phản ứng đúng

1. **Xác định:** ack rate giảm do Cloud SQL kết nối/lock/latency hay do số worker thiếu?
2. **Ổn định:** giới hạn outstanding messages, tránh retry storm, kiểm soát DB pool và error handling.
3. **Tăng throughput bền vững:** scale worker theo backlog và resource metrics, đồng thời kiểm tra quota/Cloud SQL capacity.
4. **Theo dõi:** oldest unacked age phải giảm về ngưỡng SLO; số unacked giảm không đủ nếu vẫn tồn tại poison message cũ.
5. **Phục hồi:** nếu một bản deploy đã ack sai, dùng snapshot/seek khi có retention phù hợp và đảm bảo idempotency; nếu đã hết thời gian lưu, dựa vào nguồn dữ liệu bền vững/backup đã thiết kế.
6. **Rà soát chi phí:** retention, storage, DLQ, Cloud SQL, network, worker compute và log volume.

Đừng chọn “tăng retention lên 31 ngày” làm giải pháp đầu tiên cho một subscriber có lỗi code nghiêm trọng: retention chỉ **mua thêm thời gian**; nếu không sửa nguyên nhân, backlog vẫn lớn và chi phí tăng.

### 10.3. Runbook khi sắp chạm retention

- Xác nhận `messageRetentionDuration` thực tế của topic/subscription và **oldest publish age**, không dùng mặc định trong tài liệu làm số đo production.
- Bật cảnh báo sự cố, ghi lại thời gian bắt đầu, số unacked, rate và error traces.
- Đánh giá khả năng xử lý trong thời gian còn lại, scale có kiểm soát và tránh làm downstream sập.
- Nếu cần lưu dữ liệu lâu hơn, triển khai **kênh lưu/khôi phục đã chuẩn bị trước**; đừng hứa Pub/Sub có thể xuất các message đã hết hạn.
- Không chạy seek-to-future hay xóa subscription trong lúc incident nếu chưa có phê duyệt bảo toàn dữ liệu.

## 11. IAM, bảo mật dữ liệu và chi phí

### 11.1. Phân quyền tối thiểu

| Principal | Quyền điển hình | Không nên cấp mặc định |
| --- | --- | --- |
| Cloud Run publisher | `roles/pubsub.publisher` trên topic cần ghi. | Pub/Sub Admin toàn project. |
| GKE invoice subscriber | `roles/pubsub.subscriber` trên subscription cần pull/ack. | Quyền quản trị tất cả topics/subscriptions. |
| Pub/Sub service agent cho DLQ | Các quyền cần để đọc subscription nguồn/chuyển message sang DLQ. | Owner trên topic project. |
| SRE/operator | Monitoring viewer, quyền mô tả và quyền thay cấu hình theo phê duyệt. | Tự do `seek`/xóa mọi subscription mà không kiểm soát. |

Với **push subscription**, cần xác thực endpoint Cloud Run bằng OIDC/service account và quyền invoke tương ứng. **IAM Pub/Sub không thay thế IAM Cloud SQL hoặc quyền đọc Cloud Storage**.

### 11.2. Message payload và thời gian lưu

Retained messages, logs và DLQ có thể chứa thông tin cá nhân hoặc dữ liệu giao dịch. Không đặt secrets trực tiếp trong message payload; dùng reference/token ngắn hạn theo kiến trúc khi phù hợp. Thiết lập retention đủ ngắn theo chính sách dữ liệu nhưng đủ dài để xử lý outage thực tế. Pub/Sub mã hóa dữ liệu theo dịch vụ; nếu cần CMEK hoặc yêu cầu khu vực lưu riêng, phải xem hỗ trợ và cấu hình tài nguyên cụ thể.

### 11.3. Chi phí thường bị bỏ quên

~~~text
Tổng chi phí ≈
  publish/delivery và throughput theo bảng giá
  + topic/subscription retention storage
  + lưu message unacked lâu (các khoản phí theo quy tắc)
  + lưu acknowledged messages khi bật tính năng
  + snapshot/DLQ và thao tác replay
  + Compute Engine/GKE/Cloud Run subscriber compute
  + Cloud SQL/Cloud Storage, Logging/Monitoring và network
~~~

Theo tài liệu Pub/Sub, **unacknowledged messages bị giữ trong subscription quá 24 giờ** có thể phát sinh **phí lưu trữ bổ sung**. Giữ acknowledged messages và topic retention cũng có cách tính phí riêng. Ước lượng theo **khối lượng byte, số subscriptions, thời gian giữ, rate** và giá vùng/điều kiện thực tế, không chỉ theo số message. <https://cloud.google.com/pubsub/pricing>

## 12. Troubleshooting: nhìn đúng tầng lỗi

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
| --- | --- | --- |
| Backlog và tuổi tăng cùng nhau | Ack throughput thấp, subscriber crash/CPU/DB nghẽn. | Publish/ack rates, worker logs, DB metrics. |
| Ít unacked nhưng oldest age tăng | Poison/stuck message. | Retry/error logs, delivery attempts và DLQ. |
| Message bị giao lại dù đã chạy code | Ack deadline hết, ack thất bại hoặc process chết sau commit. | Lease management, ack metrics, idempotency table. |
| Sau nhiều lần retry vẫn không thấy ở DLQ | DLQ service agent thiếu IAM, cấu hình DLQ sai, attempts best effort. | Dead-letter policy, IAM, source subscription. |
| `seek` không phát lại message cũ | Retention chưa bật trước đó hoặc message đã bị expunge. | Topic/subscription retention và publish timestamp. |
| Snapshot không tạo được | Backlog có message unacked quá cũ khiến snapshot TTL quá ngắn. | Tuổi oldest unacked và snapshot constraints. |
| Subscription tự biến mất | Subscription expiration vì không hoạt động. | Expiration policy và audit logs. |
| `--auto-ack` pull làm giảm backlog nhưng không có hóa đơn | Message bị ack bởi CLI trước khi nghiệp vụ xử lý. | Audit thao tác thử nghiệm, khôi phục nếu còn retention. |
| Cloud Run push trả 403 | Pub/Sub push identity thiếu quyền invoke/token sai audience. | Push SA, OIDC, Cloud Run IAM và logs. |
| Tăng workers nhưng ack rate giảm | Cloud SQL/quota/thread contention, retry storm. | DB connections/locks, flow control và 5xx. |
| Retention tăng mà dữ liệu cũ vẫn mất | Thay đổi policy không khôi phục message đã bị xóa. | Thời điểm thay đổi, topic retention và backup. |

**Quy trình ngắn:** xác định đúng project/topic/subscription → đọc retention/expiration/retry/DLQ settings → quan sát hai metric backlog theo region → so sánh publish/ack rates → kiểm tra worker, lease và downstream → đánh giá nguy cơ hết hạn → sửa có kiểm soát và xác nhận SLO phục hồi.

## 13. Bài tập

### Bài 1 — Phân biệt năm cơ chế

Một subscription có message retention 7 ngày, ack deadline 20 giây và expiration period 31 ngày. Message A được publish 6 ngày trước và chưa ack. Worker nhận A rồi dừng sau 20 giây. Điều gì có thể xảy ra sau 20 giây? Nếu A vẫn chưa ack khi vượt retention, có còn chắc chắn nhận lại không?

### Bài 2 — Topic so với subscription

Hai subscriptions dùng chung một topic. Nhóm analytics muốn replay toàn bộ thông điệp trong 14 ngày, trong khi nhóm invoices chỉ cần 2 ngày. Hãy chọn topic retention và subscription retention phù hợp, chỉ rõ nơi nào chịu phí và vì sao không nhất thiết bật retain-acked trên mọi subscription.

### Bài 3 — Tính backlog drain time

Backlog hiện có 90.000 message. Publisher gửi tiếp 200 msg/s, subscriber ack được 350 msg/s. Ước lượng thời gian giải phóng nếu tốc độ không đổi. Nếu ack rate tụt còn 180 msg/s, kết luận gì? Nêu ít nhất hai giả định có thể làm sai phép tính.

**Gợi ý:** với net drain 150 msg/s, khoảng 600 giây. Khi \(\mu < \lambda\), backlog tiếp tục tăng.

### Bài 4 — Tìm poison message

Metric số unacked ổn định khoảng 60 nhưng tuổi message cũ nhất tăng liên tục. Bạn có tăng 50 workers ngay không? Hãy nêu thứ tự đọc error logs, retry attempts, schema, idempotency và DLQ.

### Bài 5 — Ack, commit và exactly-once

Một worker đã ghi hóa đơn vào Cloud SQL nhưng bị kill trước khi ack. Pub/Sub gửi lại event. Thiết kế unique key/transaction để không tạo hóa đơn trùng. Giải thích vì sao exactly-once delivery không tự bảo đảm exactly-once side effects.

### Bài 6 — Snapshot/seek

Trước deploy phiên bản consumer mới, đội SRE tạo snapshot. Sau deploy, consumer ack nhầm nhiều message. Mô tả cách seek về snapshot, những rủi ro khi phát lại và vì sao snapshot không phải backup nhiều tháng. Nếu snapshot chưa được tạo trước lỗi, có lựa chọn nào khi topic retention đã bật?

### Bài 7 — Phát hiện sát hạn lưu

Một subscription có retention 1 ngày, oldest unacked age đã 21 giờ, ack rate thấp hơn publish rate. Xây cảnh báo và runbook có ưu tiên tránh mất dữ liệu; giải thích tại sao chỉ tăng retention mà không sửa worker là chưa đủ.

### Bài 8 — Pub/Sub push vào Cloud Run

Cloud Run endpoint có ingress được bảo vệ; Pub/Sub push subscription liên tục nhận 401/403. Hãy phân biệt token/audience, service account quyền invoke, routing/ingress và lỗi ứng dụng. Nếu endpoint trả 2xx trước khi transaction hoàn tất, điều gì có thể xảy ra?

### Bài 9 — Dự toán chi phí

Một topic nhận hàng triệu sự kiện/ngày; ba subscriptions đều giữ acknowledged messages 31 ngày, topic cũng bật retention 31 ngày. Hãy liệt kê các khoản phí và đề xuất một thiết kế giữ khả năng replay nhưng tránh lưu trùng không cần thiết.

## 14. Checklist production và tài liệu chính thức

| Hạng mục | Điều cần kiểm chứng |
| --- | --- |
| **Retention scope** | Topic retention, subscription retention và retain-acked được chọn theo từng nhu cầu replay. |
| **Subscription lifetime** | Expiration policy phù hợp consumer ít hoạt động/DR; không nhầm với message retention. |
| **Ack/retry** | Ack sau commit; deadline, lease extensions, exponential backoff và retry budget được đo. |
| **DLQ** | Topic/subscription DLQ, service agent IAM, delivery attempts, redrive và alert hoạt động. |
| **Backlog** | Có `num_unacked_messages_by_region`, `oldest_unacked_message_age_by_region` và ngưỡng theo SLO/retention. |
| **Capacity** | Publisher rate, subscriber ack throughput, flow control, instance scaling và downstream limits được thử. |
| **Replay** | Có thủ tục tạo snapshot trước thay đổi/seek có phê duyệt; idempotency được kiểm thử. |
| **Security** | Publisher/subscriber/push service accounts theo least privilege; dữ liệu/PII không lộ trong logs/DLQ. |
| **Cost** | Ước lượng retained bytes/age, số subscriptions, topic retention, DLQ, compute và monitoring. |
| **Recovery** | Backup/archival riêng nếu cần trên 31 ngày; diễn tập xử lý outage và mất dữ liệu. |

Nguồn chính thức để xác minh giới hạn, khả năng hỗ trợ và giá trước khi triển khai:

- [Pub/Sub subscription properties](https://cloud.google.com/pubsub/docs/subscription-properties)
- [Subscription message retention](https://cloud.google.com/pubsub/docs/subscription-message-retention)
- [Topic message retention](https://cloud.google.com/pubsub/docs/topic-message-retention)
- [Replay and purge messages with seek](https://cloud.google.com/pubsub/docs/replay-overview)
- [Dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics)
- [Exactly-once delivery](https://cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Flow control for subscribers](https://cloud.google.com/pubsub/docs/flow-control-messages)
- [Monitor Pub/Sub in Cloud Monitoring](https://cloud.google.com/pubsub/docs/monitoring)
- [Subscription overview and expiration](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Pub/Sub pricing](https://cloud.google.com/pubsub/pricing)
- [gcloud pubsub reference](https://cloud.google.com/sdk/gcloud/reference/pubsub)

**Ghi nhớ:** **retention** xác định cửa sổ mà Pub/Sub có thể giữ message; **ack deadline** điều khiển nhịp giao lại; **backlog metrics** chỉ ra consumer có theo kịp hay không; **seek/snapshot** giúp replay trong giới hạn dữ liệu còn giữ. Vận hành tốt không chỉ là backlog về 0, mà là **message được xử lý chính xác, đúng SLO, không chạm hạn lưu và chi phí được kiểm soát**.
