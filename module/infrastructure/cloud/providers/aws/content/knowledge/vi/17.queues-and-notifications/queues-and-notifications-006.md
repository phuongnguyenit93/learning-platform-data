# Batch operation, backpressure và mở rộng consumer

> **Chương:** Hàng đợi và thông báo  
> **Học phần:** `CLOUD_PROVIDERS_AWS` — khám phá hệ sinh thái AWS từ Region/AZ, IAM, VPC đến tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; thực hành chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

Trong một hệ thống xử lý đơn hàng, **producer** có thể tạo hàng nghìn sự kiện trong vài giây, nhưng **consumer** phải xác thực thanh toán, cập nhật database và gọi đối tác vận chuyển — những thao tác thường chậm hơn việc đẩy một message vào hàng đợi. Nếu xử lý đồng bộ trên đường HTTP, một đợt tăng tải dễ làm request timeout, tràn connection pool và kéo theo lỗi dây chuyền.

**Amazon Simple Queue Service (Amazon SQS)** giúp tách tốc độ tạo công việc khỏi tốc độ thực hiện công việc. Tuy nhiên, chỉ thêm một queue là chưa đủ. Hệ thống phải biết **gom message thành batch để giảm số lượt gọi API**, tạo **backpressure** để không làm quá tải consumer/downstream, và **mở rộng consumer** theo số công việc chờ lẫn năng lực xử lý thực tế.

Ba khái niệm cốt lõi:

| Khái niệm | Câu hỏi cần giải quyết | Biện pháp điển hình |
| --- | --- | --- |
| **Batch operation** | Làm sao gửi, nhận, xác nhận nhiều message hiệu quả, không làm mất message khi một phần batch lỗi? | SQS batch APIs, kiểm tra kết quả từng entry, Lambda partial batch responses |
| **Backpressure** | Khi tốc độ message đến cao hơn khả năng xử lý, ai chịu tải và cách nào ngăn downstream sụp đổ? | Hàng đợi đệm, bounded concurrency, rate limiting, retry/backoff, DLQ |
| **Consumer scaling** | Cần bao nhiêu worker, khi nào tăng/giảm và lấy chỉ số nào để scale? | CloudWatch queue metrics, backlog per task, age of oldest message, ECS Service Auto Scaling/Lambda event source scaling |

Bài học tập trung vào **SQS Standard/FIFO và những consumer phổ biến** như Lambda, ECS/Fargate hoặc EC2. Amazon SNS và EventBridge có thể đứng trước SQS để phân phối sự kiện, nhưng **không thay thế những quy tắc xử lý batch/acknowledgement của SQS**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **producer → SQS → consumer → downstream**, message lifecycle, visibility timeout, receipt handle, retention và Dead-Letter Queue (DLQ).
2. Sử dụng khái niệm **`SendMessageBatch`, `ReceiveMessage`, `DeleteMessageBatch`, `ChangeMessageVisibilityBatch`**, hiểu batch tối đa 10 entry ở các API tương ứng và tình huống kết quả thành công **một phần**.
3. Phân biệt **batch API của SQS** với **Lambda event source mapping batch**, bao gồm `batchSize`, `maximumBatchingWindowInSeconds` và `ReportBatchItemFailures`.
4. Thiết kế xử lý **at-least-once**, idempotency, FIFO ordering, retry, visibility extension và DLQ redrive.
5. Nhận diện **backpressure** khi producer nhanh hơn consumer, xử lý lỗi downstream 429/503 mà không tạo retry storm.
6. Tính nhu cầu consumer từ arrival rate, processing rate, backlog và SLO; biết khi nào autoscaling có ích hoặc gây hại.
7. Chọn **Lambda SQS trigger** hay **ECS/EC2 poller** dựa trên loại công việc, nhu cầu kiểm soát concurrency và vận hành.
8. Đọc code Java AWS SDK v2, Lambda code xử lý partial batch và AWS CLI quan sát queue, rồi thiết kế quy trình production an toàn.

## 2. Kiến trúc tổng quát

~~~mermaid
flowchart LR
    API["API / Producer\nĐặt hàng"] -->|"SendMessage / Batch"| Q["Amazon SQS\nStandard hoặc FIFO"]
    SNS["SNS / EventBridge\nnếu có fan-out"] -->|"Subscription / rule"| Q
    Q -->|"ReceiveMessage / Lambda poll"| WORK["Consumer fleet\nLambda hoặc ECS/EC2"]
    WORK -->|"Xử lý nghiệp vụ"| DB["DB / API downstream"]
    WORK -->|"Delete sau thành công"| Q
    Q -->|"Vượt maxReceiveCount"| DLQ["Dead-letter queue"]
    MON["CloudWatch + Alerts"] -.-> Q
    MON -.-> WORK
    MON -.-> DLQ
    SCALER["Scaling policy"] -.->|"Điều chỉnh consumer concurrency"| WORK
~~~

*Các mũi tên Delete biểu thị việc consumer **xóa message theo receipt handle** khi xử lý thành công, không phải trực tiếp ghi nội dung vào queue. Với Lambda event source mapping, dịch vụ Lambda chịu trách nhiệm polling và xóa message tương ứng sau khi invocation thành công.*

### 2.1. Vì sao queue giảm coupling?

Không có queue:

~~~text
HTTP request → xử lý email → gọi đối tác → ghi database → HTTP response
                   (đối tác chậm khiến toàn request chậm)
~~~

Có queue:

~~~text
HTTP request → ghi đơn hàng / outbox → gửi event vào SQS → HTTP 202/200 phù hợp
                                                        |
                                                        v
                                           Worker xử lý sau
~~~

Hệ thống có thể **hấp thụ burst trong thời gian ngắn** mà không bắt tất cả request chờ xử lý hoàn tất. Tuy nhiên, việc trả HTTP **202 Accepted** chỉ có nghĩa công việc được nhận theo contract; nếu producer không lưu công việc bền vững hoặc thiết kế outbox sai, vẫn có thể mất sự kiện.

### 2.2. Các trạng thái message trong SQS

| Trạng thái logic | Ý nghĩa |
| --- | --- |
| **Visible** | Đang có thể được consumer nhận |
| **In flight / Not visible** | Đã được nhận và đang trong thời gian visibility timeout |
| **Visible trở lại** | Visibility hết hạn nhưng message chưa được xóa; có thể được redeliver |
| **Deleted** | Consumer xác nhận hoàn thành bằng receipt handle hợp lệ |
| **Moved to DLQ** | Sau số lần nhận thất bại theo redrive policy, message có thể được chuyển tới DLQ |
| **Expired** | Message vượt quá retention period và bị hệ thống xóa, kể cả chưa xử lý thành công |

**Receive không đồng nghĩa hoàn tất.** SQS không tự biết database commit đã thành công, email đã gửi hay downstream đã trả status. Message chỉ được xóa theo cơ chế acknowledgement/deletion tương ứng sau khi công việc được xác nhận ở tầng ứng dụng.

### 2.3. SQS Standard và FIFO

| Đặc tính | **Standard queue** | **FIFO queue** |
| --- | --- | --- |
| Delivery | **At least once**; duplicates có thể xảy ra | Deduplication và ordering theo quy tắc FIFO |
| Thứ tự | Best-effort ordering, không cam kết thứ tự toàn cục | Giữ thứ tự **trong cùng message group** |
| Khả năng song song | Mở rộng tốt theo nhiều workers, chịu duplicates | Parallelism bị giới hạn bởi số message groups có thể xử lý độc lập |
| Deduplication | Ứng dụng tự thiết kế | `MessageDeduplicationId` hoặc content-based deduplication trong khoảng thời gian do dịch vụ quy định |
| Khi chọn | Task độc lập, throughput lớn, chấp nhận xử lý lặp | Workflow cần order theo entity/key và kiểm soát duplicates trên đường enqueue |

**FIFO không biến side effects thành exactly-once.** Nếu worker cập nhật database thành công nhưng bị lỗi trước khi SQS nhận Delete, message có thể được nhận lại; consumer vẫn phải idempotent. FIFO deduplication dùng cho **gửi vào queue** không thay thế idempotency khi xử lý.

## 3. Batch operation: tối ưu API nhưng không bỏ qua lỗi từng message

Các API SQS thường dùng:

| API | Vai trò | Giới hạn / lưu ý |
| --- | --- | --- |
| `SendMessage` | Gửi một message | Hỗ trợ message attributes, delay, FIFO group/dedup theo quy tắc |
| **`SendMessageBatch`** | Gửi **tối đa 10 entries** mỗi request | Mỗi entry có `Id` riêng; có thể thành công một phần |
| **`ReceiveMessage`** | Nhận **tối đa 10 messages** mỗi request | `MaxNumberOfMessages=1..10`; có thể nhận **ít hơn** giá trị yêu cầu, thậm chí không có |
| `DeleteMessage` | Xóa một message bằng receipt handle | Không dùng MessageId thay receipt handle |
| **`DeleteMessageBatch`** | Xóa **tối đa 10 entries** mỗi request | Có danh sách `Successful` và `Failed` riêng |
| `ChangeMessageVisibility` | Gia hạn/rút thời gian ẩn của một message | Cần receipt handle còn phù hợp |
| **`ChangeMessageVisibilityBatch`** | Đổi visibility của **tối đa 10 entries** | Cũng có thể thành công một phần |

**Một API response HTTP 200 không có nghĩa toàn bộ batch đã thành công.** Với batch APIs, phải kiểm tra mảng `Successful` và `Failed`, xử lý lỗi theo `Id` của từng entry. `Failed` có thể chứa `Code`, `Message` và `SenderFault`; chỉ retry những lỗi phù hợp. Những lỗi dữ liệu/cấu hình không nên bị retry vô hạn.

### 3.1. Ví dụ SendMessageBatch và xử lý partial success

Producer muốn gửi bốn công việc:

~~~json
{
  "Entries": [
    {"Id": "a1", "MessageBody": "{\"orderId\":\"o-101\"}"},
    {"Id": "a2", "MessageBody": "{\"orderId\":\"o-102\"}"},
    {"Id": "a3", "MessageBody": "{\"orderId\":\"o-103\"}"},
    {"Id": "a4", "MessageBody": "{\"orderId\":\"o-104\"}"}
  ]
}
~~~

Phản hồi minh họa (rút gọn):

~~~json
{
  "Successful": [
    {"Id": "a1", "MessageId": "m-101"},
    {"Id": "a2", "MessageId": "m-102"},
    {"Id": "a4", "MessageId": "m-104"}
  ],
  "Failed": [
    {
      "Id": "a3",
      "Code": "InternalError",
      "Message": "Transient service error",
      "SenderFault": false
    }
  ]
}
~~~

Đây là **dữ liệu minh họa**, không phải log AWS thực. Nếu API trả như vậy, **không gửi lại a1, a2, a4 như thể chúng chưa thành công**. Chỉ xem xét retry a3 sau backoff. Nếu request bị timeout và client **không nhận được bất kỳ response nào**, trạng thái gửi của từng message có thể không chắc chắn; thiết kế idempotency/producer outbox là cần thiết để giảm hậu quả của việc gửi trùng.

### 3.2. SQS message size không giống batch size

Giới hạn thực tế cần phân biệt:

- **Số entry:** `SendMessageBatch` tối đa **10 messages** mỗi API request.
- **Kích thước:** mỗi message và tổng payload batch phải đáp ứng giới hạn message/payload hiện hành của SQS (ví dụ giới hạn khoảng **1 MiB** cho các hoạt động SQS hỗ trợ kích thước này, tùy request và tài liệu API).
- **Payload nghiệp vụ:** một message quá lớn nên chứa **tham chiếu tới dữ liệu S3** thay vì nhồi toàn bộ file trong body, kèm cơ chế quyền truy cập/expiry/encryption.
- **Số message thực nhận:** `ReceiveMessage(MaxNumberOfMessages=10)` **không hứa luôn trả đúng 10**.

**Gom 10 messages** giúp giảm chi phí API call trên cùng khối lượng công việc; nó không giúp một tác vụ 100 MB lọt qua giới hạn SQS.

### 3.3. Khi nào gom batch sẽ làm chậm?

Batching có đánh đổi:

- Đợi batch đủ 10 có thể làm message đầu tiên bị trễ khi traffic thấp.
- Batch size lớn khiến một Lambda invocation kéo dài hoặc xử lý nhiều message lỗi cùng lúc.
- Nếu consumer commit toàn batch chỉ ở cuối, một phần tử chậm/không hợp lệ có thể kéo dài visibility của các phần tử khác.
- Batch lớn ở downstream (ví dụ Bulk insert DB) giảm overhead nhưng tăng áp lực transaction/locks.

Thường nên dùng **batch size tối đa** và **maximum wait time** tùy backlog, latency SLO, downstream throughput, thay vì luôn chọn mức lớn nhất.

## 4. Receive, visibility timeout và cơ chế xác nhận

### 4.1. Một message có thể được nhận lại

~~~mermaid
sequenceDiagram
    participant Q as Amazon SQS
    participant W as Worker
    participant D as Database
    W->>Q: ReceiveMessage
    Q-->>W: message + receiptHandle; bắt đầu visibility timeout
    W->>D: Xử lý và commit
    D-->>W: Commit thành công
    alt Delete được xác nhận
        W->>Q: DeleteMessage(receiptHandle)
        Q-->>W: Accepted
    else Worker crash trước Delete
        Note over Q: Visibility timeout hết hạn
        Q-->>W: Có thể redeliver cùng message
    end
~~~

**Receipt handle** là token cần dùng để xóa/đổi visibility cho **lần nhận** cụ thể. Nó **khác `MessageId`**. Khi message được nhận lại, receipt handle có thể thay đổi; thao tác với receipt handle cũ có thể không còn hiệu lực như mong muốn.

### 4.2. Chọn visibility timeout

`VisibilityTimeout` là thời gian message bị ẩn sau khi receive, để worker có cơ hội xử lý và delete. Chọn quá ngắn làm message có thể được consumer khác nhận khi worker ban đầu vẫn đang xử lý; quá dài khiến retry sau crash bị chậm.

Ví dụ:

~~~text
P50 xử lý:     2 giây
P99 xử lý:    25 giây
Visibility:   60 giây (khởi đầu minh họa)
~~~

Nếu công việc đôi khi kéo dài nhiều phút, worker có thể gọi `ChangeMessageVisibility` khi còn đang tiến triển. Phải đặt **giới hạn tổng thời gian** và xử lý trường hợp thay visibility thất bại. Không kéo dài mãi một message bị treo.

### 4.3. Delete sau khi nào?

Một quy tắc thực hành:

~~~text
Receive → validate → idempotency check → side effect đã commit
        → DeleteMessage theo receipt handle
~~~

Đối với một payment notification, “side effect commit” có thể là ghi durable event/outbox vào database, **không** nhất thiết phải đợi mọi email/sms downstream hoàn tất. Nhưng contract phải rõ: nếu xóa message ngay sau khi chỉ đưa vào RAM, crash tiếp theo có thể làm mất việc.

### 4.4. Retention, delay và DLQ

- **Message retention** giới hạn message có thể nằm trong queue; SQS thông thường cho cấu hình từ **1 phút tới 14 ngày**.
- **Delivery delay** có thể trì hoãn message mới (thường tối đa **15 phút**) nhưng không thay thế một scheduler lâu dài.
- **Redrive policy** gửi message sang **DLQ** khi bị nhận nhiều lần vượt ngưỡng `maxReceiveCount` theo cơ chế SQS.
- **DLQ không thay thế quan sát:** cần cảnh báo về số message/tuổi message trong DLQ, kiểm tra lỗi rồi mới redrive.

Với Standard queue, các message có thể được nhận trùng lặp và không theo thứ tự. Đối với FIFO, xử lý failure theo **message group** để tránh cho các message sau vượt qua message lỗi.

## 5. Long polling và nhịp kéo message

Consumer tự viết thường gọi `ReceiveMessage` theo vòng lặp. Nếu queue rỗng, gọi liên tục với `WaitTimeSeconds=0` (short polling) tạo nhiều request trả rỗng.

**Long polling** cho phép SQS giữ request một khoảng thời gian chờ có message, tối đa **20 giây** theo giới hạn API phổ biến:

~~~text
ReceiveMessage:
  MaxNumberOfMessages = 10
  WaitTimeSeconds     = 20
  VisibilityTimeout   = 60
~~~

Khi queue rỗng, request có thể chờ; khi message đến sớm, request có thể hoàn thành ngay. Long polling giảm những API calls rỗng và chi phí liên quan, nhưng không tự quản concurrency của downstream.

### 5.1. Vòng lặp consumer không nên busy-spin

~~~text
KHÔNG TỐT:
  while true:
    receive(WaitTimeSeconds=0)
    nếu rỗng: tiếp tục ngay

PHÙ HỢP HƠN:
  while running và còn capacity:
    receive(MaxNumberOfMessages<=10, WaitTimeSeconds=20)
    xử lý với concurrency có giới hạn
    delete các message đã hoàn thành
    retry/backoff khi lỗi poller
~~~

Với custom poller, tránh nhận thêm 10 messages khi toàn bộ worker threads và database connections đều kín. Nhận quá mức rồi giữ các message “in flight” trong RAM có thể làm visibility timeout hết hạn trước khi chúng được xử lý.

### 5.2. Ràng buộc HTTP client timeout

HTTP client dùng cho AWS SDK phải có **request/socket timeout lớn hơn thời gian long poll dự kiến**, cộng overhead kết nối/mạng. Nếu đặt SDK HTTP timeout 5 giây nhưng `WaitTimeSeconds=20`, client có thể timeout sớm, tạo retry vô ích.

## 6. Backpressure: kiểm soát áp lực trước khi quá tải

**Backpressure** là cơ chế làm cho luồng xử lý phía trước **không đẩy công việc vào hệ thống phía sau nhanh hơn khả năng phục vụ an toàn**. Với queue:

~~~text
Producer rate = λ messages/giây
Consumer throughput = μ messages/giây

Nếu λ > μ trong một khoảng thời gian:
  backlog tăng dần, độ trễ xử lý tăng

Nếu μ > λ và còn backlog:
  backlog có thể được tiêu dần
~~~

Queue là bộ đệm, **không tạo năng lực xử lý từ hư không**. Nếu producer gửi 2.000 msg/s còn downstream tối đa 200 msg/s liên tục, backlog sẽ tăng cho đến khi cần giảm tốc, tối ưu xử lý, scale có ích hoặc điều chỉnh kiến trúc.

### 6.1. Những lớp cần backpressure

| Lớp | Dấu hiệu bị quá tải | Cách kiểm soát |
| --- | --- | --- |
| **Producer → SQS** | Lưu lượng vượt quota, message không hợp lệ, duplicate requests | Admission control, token bucket, batching, retry có jitter |
| **SQS → consumer** | Quá nhiều in-flight, CPU/memory/threads đầy | Bounded concurrency, prefetch thấp, autoscaling có giới hạn |
| **Consumer → database** | DB connection pool cạn, 429/503, lock contention | Semaphore, rate limit, connection pool cap, circuit breaker |
| **Consumer → đối tác API** | Rate limit/timeout | Retry-After khi có, exponential backoff, queue riêng cho tác vụ chậm |
| **Consumer → kết quả** | Trả chậm hoặc callback lỗi | Durable state, retry async, DLQ, cảnh báo backlog tuổi cao |

### 6.2. Bounded concurrency quan trọng hơn “mở càng nhiều càng tốt”

Giả sử database chỉ an toàn khi tối đa **40 giao dịch ghi đồng thời**. Nếu tạo 100 ECS tasks, mỗi task có 20 threads truy cập DB, có thể có tới **2.000 truy vấn cùng lúc** — vượt xa mức 40. Kết quả thường là queue ở DB, tăng latency, timeout rồi retry đồng loạt, khiến hiệu suất **giảm** dù có nhiều workers hơn.

Cách thiết kế:

- Đặt concurrency limit theo **năng lực downstream**: tổng số DB writers/token trong toàn fleet không vượt mức được benchmark.
- Dùng connection pool có giới hạn và queue nội bộ có **dung lượng hữu hạn**.
- Khi hết slot xử lý, poller ngừng receive tạm thời hoặc giảm số worker; **không nhận vô hạn message vào RAM**.
- Có cơ chế **retry có backoff + jitter** khi lỗi tạm thời; phân biệt lỗi vĩnh viễn (schema/permission).
- Nếu cần per-tenant fairness, tách queues hoặc dùng scheduling/quotas để tenant gửi nhiều không chiếm mọi worker.

### 6.3. Rate limiter và circuit breaker

Ví dụ consumer gọi đối tác với quota 100 requests/giây:

~~~text
Consumer fleet requests/giây: 300
Partner quota:               100

Giải pháp:
  - Rate limit toàn fleet ~100 req/s hoặc thấp hơn có margin;
  - Queue giữ công việc đến lượt xử lý;
  - Khi 429, đọc Retry-After nếu được cung cấp;
  - Backoff có jitter và giới hạn số lần retry;
  - Ngắt tạm thời bằng circuit breaker khi lỗi kéo dài;
  - DLQ / retry queue cho công việc không thể xử lý.
~~~

**Lưu ý:** rate limit đặt **trong từng task** không đảm bảo giới hạn **toàn fleet** khi scale số task lên. Có thể cần token distributor, distributed limiter, service quota-aware coordination hoặc tách queue dành riêng cho API bị giới hạn.

### 6.4. Tránh retry storm

Khi downstream trả `503`:

1. Consumer có thể retry ngay trong cùng invocation.
2. Visibility timeout hết hạn khiến SQS redeliver.
3. Autoscaler tăng số consumers vì backlog tăng.
4. Nhiều workers cùng gọi downstream hỏng nhiều lần hơn.

Nếu không có giới hạn, đây là **retry storm**. Cần phân tầng retry có ngân sách và loại lỗi rõ, giới hạn concurrency, thêm jitter, sử dụng DLQ/retry scheduling phù hợp và tạm dừng/giảm consumer khi downstream đang unhealthy.

## 7. Consumer scaling: dùng chỉ số nghiệp vụ thay vì chỉ đếm CPU

Một ECS worker thường ở trạng thái **chờ queue** khi rảnh, vì thế CPU thấp không đủ nói cần bao nhiêu workers. Ngược lại, một worker có CPU 5% nhưng đang đợi đối tác API 5 giây có thể chỉ xử lý một số ít msg/s.

Các tín hiệu quan trọng:

| Metric | Nguồn | Cách hiểu |
| --- | --- | --- |
| `ApproximateNumberOfMessagesVisible` | SQS CloudWatch | Số message sẵn sàng nhận, gần đúng |
| `ApproximateNumberOfMessagesNotVisible` | SQS CloudWatch | Số message đang in-flight, gần đúng |
| `ApproximateAgeOfOldestMessage` | SQS CloudWatch | Thời gian đợi của message lâu nhất theo metric semantics |
| `NumberOfMessagesSent` | SQS CloudWatch | Tốc độ enqueue (theo số message được tính, không nhất thiết unique business jobs) |
| `NumberOfMessagesReceived` | SQS CloudWatch | Tốc độ receive; có thể gồm receives trùng |
| `NumberOfMessagesDeleted` | SQS CloudWatch | Số lần delete được ghi nhận; không nhất thiết là unique jobs đã xử lý |
| **Processing duration / success rate** | Metrics ứng dụng | Thực tế worker xử lý nhanh/chậm, lỗi hay thành công |
| **RunningTaskCount / concurrent Lambda** | ECS/CloudWatch | Năng lực đang chạy, không tự nói throughput hữu ích |
| **DLQ depth và age** | SQS CloudWatch | Work không xử lý được đang tích lũy |

Các SQS metrics có tiền tố **Approximate** là ước lượng và có độ trễ CloudWatch. Đừng dùng chúng như transaction count tuyệt đối hoặc giả định dữ liệu từng giây realtime.

### 7.1. Backlog per task

Một chỉ số autoscaling quen thuộc cho ECS:

~~~text
BacklogPerTask
  = ApproximateNumberOfMessagesVisible / RunningTaskCount

TargetBacklogPerTask
  ≈ acceptableQueueWaitSeconds
    × messagesProcessedPerSecondPerTask
~~~

Ví dụ một task xử lý bền vững **20 msg/s**, thời gian chờ trong queue cho phép **30 giây**:

~~~text
Target backlog per task ≈ 20 × 30 = 600 messages

Nếu visible backlog = 6.000 messages:
  Task count mục tiêu theo backlog ≈ 6.000 / 600 = 10 tasks
~~~

Đây là **heuristic**, không phải bảo đảm p99 latency: còn có arrival rate, concurrency downstream, network, queue semantics, deployment delay và việc chưa tính messages in-flight. Trong CloudWatch metric math, phải bảo vệ trường hợp `RunningTaskCount=0` để không chia cho 0 và cấu hình **min capacity** phù hợp.

### 7.2. Công thức throughput và thời gian tiêu backlog

Giả sử:

~~~text
Incoming rate λ = 600 msg/s
Mỗi worker xử lý μ = 40 msg/s

Số workers tối thiểu để theo kịp tải:
  ceil(600 / 40) = 15

Nếu muốn khoảng 25% headroom trên số worker tối thiểu:
  ceil(15 × 1.25) = 19 workers
~~~

Ví dụ tiêu backlog:

~~~text
Backlog hiện có B = 60.000 messages
Incoming trong lúc dọn = 400 msg/s
20 workers × 35 msg/s/worker = 700 msg/s
Tốc độ dọn ròng = 700 - 400 = 300 msg/s

Thời gian lý tưởng ≈ 60.000 / 300 = 200 giây
~~~

**200 giây là ước lượng lý tưởng** khi throughput không đổi, không có failed retries, downstream không bị nghẽn và workers đã sẵn sàng. Đối với SLO thực, cần thêm thời gian scale-out, cold start, queue polling, long-running tasks và safety margin.

### 7.3. Scale theo age hoặc backlog?

- **Backlog count** phản ánh lượng việc đang chờ, dễ dùng để phân bổ tasks.
- **Age of oldest message** phản ánh rủi ro trễ SLO, hữu ích để cảnh báo. Nhưng những đặc tính như poison message/DLQ có thể khiến số tuổi không diễn đạt đơn giản toàn bộ backlog.
- **Processing duration** quyết định throughput thực tế. Backlog 1.000 ảnh nhỏ khác hoàn toàn 1.000 video dài.
- **Downstream health** đặt trần concurrency. Nếu DB/API đang hỏng, scale lên chỉ vì backlog tăng có thể làm sự cố nặng hơn.

Một chiến lược tốt kết hợp **target tracking backlog-per-task** với **alarm theo message age/ DLQ**, minimum/maximum capacity và guardrail downstream.

## 8. Lambda consumer: event source mapping và xử lý batch

**AWS Lambda** có tích hợp Amazon SQS thông qua **event source mapping (ESM)**. Lambda service dùng pollers để lấy messages từ SQS, đóng gói vào event cho function, điều chỉnh concurrency theo cơ chế scaling của ESM và xóa những messages đã được xử lý thành công.

### 8.1. Event source mapping gồm những gì?

| Tham số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `EventSourceArn` | ARN của SQS queue | Queue và function phải thuộc phạm vi Region/tính năng tương thích |
| `BatchSize` | Số message tối đa trong một invocation | Standard có thể hỗ trợ batch lớn, FIFO bị giới hạn nhỏ hơn |
| `MaximumBatchingWindowInSeconds` | Chờ thêm một khoảng thời gian để gom batch | Tăng hiệu quả batch nhưng thêm latency |
| `FunctionResponseTypes: ReportBatchItemFailures` | Cho phép function trả ID của các message xử lý lỗi | Tránh phải retry cả batch khi chỉ một phần lỗi |
| `ScalingConfig.MaximumConcurrency` | Giới hạn concurrency do mapping này sử dụng, khi hỗ trợ | Bảo vệ database và các dependencies |
| `FilterCriteria` | Lọc message theo điều kiện được ESM hỗ trợ | Phải hiểu tác động tới message filtered out và business data |

Giới hạn phổ biến: SQS Standard mapping có thể nhận **batch lớn hơn 10** (trong những phiên bản dịch vụ hỗ trợ, tới **10.000** records), còn FIFO có **batch tối đa 10**. Khi chọn `BatchSize > 10` với Standard, cấu hình batching window theo yêu cầu dịch vụ (thường tối thiểu **1 giây**). Ngoài số lượng record còn có **giới hạn kích thước payload invocation**; một batch lớn về số message có thể kết thúc sớm hơn vì kích thước bytes.

Đây là **Lambda event batch**, không phải lời gọi `ReceiveMessage` của app Java mà bạn tự viết. Lambda ESM có thể thực hiện **nhiều SQS receive calls** để gom records theo BatchSize/window rồi giao một event; không được suy rằng SQS Receive API đơn lẻ có thể trả 1.000 records.

### 8.2. Hành vi mặc định khi một record thất bại

Giả sử invocation nhận:

~~~text
Batch: [m1, m2, m3, m4, m5]
m1 → success
m2 → success
m3 → downstream lỗi
m4 → success
m5 → success
~~~

Nếu handler **throw error cho toàn invocation** mà không có partial batch response phù hợp, cả batch có thể được coi là failed và những message đã xử lý có thể được nhận lại sau visibility timeout. **Không đặt giả thiết rằng mỗi Lambda invocation chỉ chứa một message.**

Nếu ứng dụng bắt lỗi nhưng lại luôn return success cho invocation, Lambda có thể **xóa cả các failed messages**, dẫn đến mất công việc. Vì vậy bắt lỗi và in log **chưa đủ**; cần phản hồi đúng contract để không xác nhận nhầm thành công.

### 8.3. Partial batch response

Khi bật `ReportBatchItemFailures` trên event source mapping, function có thể trả về các ID lỗi:

~~~json
{
  "batchItemFailures": [
    { "itemIdentifier": "m3" }
  ]
}
~~~

Với kết quả hợp lệ theo cơ chế partial batch, Lambda có thể xóa thành công m1, m2, m4, m5 và **giữ m3 để nhận lại** theo SQS retry/visibility. Tên `itemIdentifier` là **SQS `messageId`**, không phải receipt handle hay business order ID.

**Điều kiện bắt buộc:** event source mapping phải bật `ReportBatchItemFailures`. Chỉ return JSON này khi mapping chưa được bật không tạo ra behavior như mong muốn.

### 8.4. Mã Lambda Node.js minh họa cho Standard queue

~~~javascript
// Ví dụ Lambda Node.js: Standard SQS trigger.
// processDurablyIdempotent phải là nghiệp vụ do bạn triển khai
// với datastore và idempotency key bền vững.
async function processDurablyIdempotent(record) {
  // Pseudocode: validate schema, insert unique eventId,
  // commit business side effects, không bỏ lỗi.
  throw new Error("Triển khai nghiệp vụ thực trước khi sử dụng");
}

exports.handler = async (event) => {
  const failed = [];

  for (const record of event.Records) {
    try {
      await processDurablyIdempotent(record);
    } catch (error) {
      console.error("Message thất bại", {
        messageId: record.messageId,
        errorType: error.name
      });
      failed.push({ itemIdentifier: record.messageId });
    }
  }

  return { batchItemFailures: failed };
};
~~~

**Mẫu trên là fragment minh họa contract, cố ý chưa cài nghiệp vụ** và sẽ đánh dấu tất cả messages lỗi nếu chạy nguyên trạng. Điều này an toàn hơn một ví dụ giả vờ “xử lý thành công” mà chưa có durable commit. Production phải triển khai `processDurablyIdempotent` trước khi tạo trigger, cùng metric/error policy và alarms.

Với nhiều records, xử lý tuần tự có thể làm invocation dài. Có thể xử lý song song theo **bounded concurrency** cho Standard queue khi các công việc độc lập; không dùng `Promise.all` không giới hạn để gửi hàng nghìn request vào database. Khi xử lý song song, cần đảm bảo từng record có kết quả riêng chính xác.

### 8.5. FIFO: dừng ở lần lỗi đầu tiên để bảo vệ thứ tự

Với FIFO, phải giữ thứ tự trong cùng **`MessageGroupId`**. AWS khuyến nghị khi dùng `ReportBatchItemFailures` với FIFO: **dừng xử lý sau lỗi đầu tiên** và trả **cả message lỗi lẫn những message chưa xử lý** trong `batchItemFailures`, để không vượt qua message lỗi.

~~~javascript
async function processDurablyIdempotent(record) {
  throw new Error("Triển khai nghiệp vụ thực trước khi sử dụng");
}

exports.handler = async (event) => {
  for (let i = 0; i < event.Records.length; i++) {
    try {
      await processDurablyIdempotent(event.Records[i]);
    } catch (error) {
      console.error("FIFO batch dừng ở record lỗi", {
        messageId: event.Records[i].messageId
      });
      return {
        batchItemFailures: event.Records.slice(i).map((r) => ({
          itemIdentifier: r.messageId
        }))
      };
    }
  }
  return { batchItemFailures: [] };
};
~~~

Mẫu cố ý dừng toàn batch khi gặp lỗi, đơn giản để không xử lý records sau record lỗi. Production có thể nhóm theo `MessageGroupId` và tối ưu hơn nhưng **không được xử lý vượt qua phần tử chưa thành công trong cùng group**.

### 8.6. Visibility timeout cho Lambda SQS trigger

AWS khuyến nghị cấu hình queue visibility timeout **ít nhất khoảng 6 lần Lambda function timeout**, và cộng batching window nếu có, để Lambda có cơ hội retry khi invocation bị throttled/fail. Ví dụ function timeout 30 giây, batching window 5 giây có thể bắt đầu đánh giá visibility ở mức **185 giây hoặc hơn**:

~~~text
6 × 30 giây + 5 giây = 185 giây
~~~

Đây là **hướng dẫn cấu hình**, không phải bảo đảm invocation luôn dùng hết khoảng đó. Cần xem yêu cầu dịch vụ hiện hành và giới hạn visibility của SQS. Nếu visibility quá ngắn, cùng message có thể được xử lý đồng thời khi invocation ban đầu chưa xong; nếu quá dài, thời gian retry/DLQ có thể bị chậm.

### 8.7. Giới hạn concurrency của Lambda

Với Lambda, tăng concurrency khi queue lớn có thể dẫn tới:

- Database có quá nhiều connections.
- Third-party API trả **429 Too Many Requests**.
- Quota Lambda hoặc các event source mappings trong account cạn.
- Cold starts và áp lực KMS/secrets/connection setup tăng.

Hãy cân nhắc:

- `ScalingConfig.MaximumConcurrency` của mapping khi được hỗ trợ.
- `ReservedConcurrency` của function và các triggers khác cùng dùng function.
- Quota account/Region và năng lực downstream.
- Cách queue đợi backlog khi cap đã đạt; báo động khi `ApproximateAgeOfOldestMessage` tăng ngoài SLO.

Đừng đặt `MaximumConcurrency` cao hơn mức database/API thực sự chịu được chỉ vì Lambda có khả năng scale nhanh.

## 9. Custom consumer trên ECS/EC2: kiểm soát polling và parallelism

Với công việc cần chạy liên tục, xử lý lâu, sử dụng thư viện native/Java hoặc đòi quyền điều khiển thread pool chi tiết, **ECS/Fargate hoặc EC2 worker** là lựa chọn hợp lý. Bạn tự chịu trách nhiệm polling, batching, deletion, scaling, deployment và graceful shutdown.

### 9.1. Các tham số của một poller Java

~~~text
Mỗi worker container:
  Polling threads:             1..N, tùy thiết kế
  ReceiveMessage max records:  10
  WaitTimeSeconds:             20
  Local processing slots:      8
  Database max concurrency:    theo tổng fleet, không chỉ từng task
  VisibilityTimeout:           lớn hơn thời gian xử lý dự kiến
  Graceful shutdown:           ngừng nhận mới, hoàn tất/extend công việc
~~~

Nếu task nhận 10 messages nhưng chỉ có hai slots, tám messages có thể ngồi chờ trong bộ nhớ trong khi visibility timeout đã tính. Một worker khỏe phải có **backpressure từ chính poller**: chỉ receive khi có đủ chỗ xử lý hoặc bảo đảm thời gian còn lại.

### 9.2. Java AWS SDK v2: producer SendMessageBatch

Ví dụ sau là **fragment Java** sử dụng `software.amazon.awssdk:sqs`; thay queue URL và body theo dữ liệu lab.

~~~java
import java.util.List;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequestEntry;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchResponse;

String queueUrl = "https://sqs.ap-southeast-1.amazonaws.com/"
    + "123456789012/jobs-lab";

try (SqsClient sqs = SqsClient.builder()
        .region(Region.AP_SOUTHEAST_1).build()) {
    List<SendMessageBatchRequestEntry> entries = List.of(
        SendMessageBatchRequestEntry.builder()
            .id("a")
            .messageBody("{\"eventId\":\"evt-101\"}")
            .build(),
        SendMessageBatchRequestEntry.builder()
            .id("b")
            .messageBody("{\"eventId\":\"evt-102\"}")
            .build());

    SendMessageBatchResponse response = sqs.sendMessageBatch(
        SendMessageBatchRequest.builder()
            .queueUrl(queueUrl)
            .entries(entries)
            .build());

    response.successful().forEach(s ->
        System.out.println("Sent: " + s.id() + " -> " + s.messageId()));

    response.failed().forEach(f ->
        System.err.println("Failed: " + f.id() + " / "
            + f.code() + " / senderFault=" + f.senderFault()));

    // Production: retry từng entry lỗi nếu có thể retry;
    // không replay toàn batch đã thành công.
}
~~~

Đây là ví dụ minh họa thao tác **thay đổi queue**; **không chạy** vào production. SDK cần credentials được cấp qua chain phù hợp (task role/instance profile/SSO), không hardcode AWS access keys. Code dạng fragment được đặt trong phương thức Java phù hợp khi dùng thực tế.

### 9.3. Java AWS SDK v2: nhận và xóa các message đã xử lý thành công

~~~java
import java.util.ArrayList;
import java.util.List;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.*;

// Các biến sqs và queueUrl do lớp ứng dụng khởi tạo.
ReceiveMessageResponse response = sqs.receiveMessage(
    ReceiveMessageRequest.builder()
        .queueUrl(queueUrl)
        .maxNumberOfMessages(10)
        .waitTimeSeconds(20)
        .visibilityTimeout(60)
        .build());

List<DeleteMessageBatchRequestEntry> deletions = new ArrayList<>();
int nextId = 0;

for (Message m : response.messages()) {
    try {
        // Hàm nghiệp vụ PHẢI commit bền vững và idempotent,
        // có thể ném exception khi chưa hoàn tất.
        businessService.processIdempotently(m.body(), m.messageId());

        deletions.add(DeleteMessageBatchRequestEntry.builder()
            .id("del-" + nextId++)
            .receiptHandle(m.receiptHandle())
            .build());
    } catch (Exception error) {
        // Không delete message lỗi; chờ retry/DLQ theo policy.
        log.warn("Processing failed, messageId={}", m.messageId(), error);
    }
}

if (!deletions.isEmpty()) {
    DeleteMessageBatchResponse deleted = sqs.deleteMessageBatch(
        DeleteMessageBatchRequest.builder()
            .queueUrl(queueUrl)
            .entries(deletions)
            .build());
    deleted.failed().forEach(f ->
        log.error("Delete failed: {} / {}", f.id(), f.code()));
}
~~~

**Đây là fragment kiến trúc, không phải lớp Java chạy độc lập:** `sqs`, `queueUrl`, `businessService` và `log` là dependencies phải được cung cấp. Nó minh họa rằng **chỉ message đã được commit mới được đưa vào DeleteMessageBatch**.

Các nâng cấp bắt buộc trong production:

- Map `DeleteMessageBatchRequestEntry.Id` trở lại message/receipt handle để retry những delete entries bị lỗi.
- Catch và phân loại **API call-level exceptions** (timeout, throttling, IAM), không chỉ kiểm tra `deleted.failed()`.
- Sử dụng durable idempotency key từ business event, không mặc định message ID luôn là business identity chính xác ở mọi retry/re-enqueue.
- Điều phối polling khi local capacity đầy, xử lý process shutdown và visibility extension với công việc dài.
- Với FIFO, bảo vệ thứ tự theo MessageGroupId; không chạy song song hai messages cùng group khi điều đó phá semantics.

### 9.4. Vì sao không xoá cả batch sau khi một phần thành công?

Giả sử receive 10 messages và chỉ 7 thành công:

~~~text
10 received:
  7 committed → delete 7
  2 transient errors → để retry theo visibility/retry policy
  1 permanent validation error → xử lý policy lỗi/DLQ, không spam retry
~~~

Nếu consumer gửi DeleteMessageBatch cho cả 10, **3 công việc lỗi có nguy cơ mất**. Nếu chỉ throw và không delete gì, **7 công việc đã thành công có thể bị xử lý lặp**. Giải pháp là **acknowledge từng message** kết hợp idempotency và policy retry.

### 9.5. Shutdown đúng với ECS service

Khi ECS scale-in hoặc deploy image mới:

1. Worker nhận `SIGTERM`.
2. Ngừng bắt đầu `ReceiveMessage` mới.
3. Đợi bounded in-flight tasks hoàn tất, gia hạn visibility nếu phù hợp.
4. Delete những messages đã commit thành công.
5. Thoát trong stop timeout được cấu hình; nếu quá hạn, messages chưa Delete sẽ trở lại sau visibility timeout.

Trong hệ thống nhiều AZ, không dùng lưu state trong RAM làm bằng chứng duy nhất rằng công việc hoàn tất. Worker có thể chết bất kỳ lúc nào.

## 10. FIFO ordering, message groups và trade-off throughput

FIFO queue có mục tiêu bảo đảm **ordering trong từng message group**, không phải một hàng chờ duy nhất có thể xử lý vô hạn song song.

~~~text
FIFO queue:
  Group order#A: A1 → A2 → A3 → A4
  Group order#B: B1 → B2 → B3

Có thể xử lý A1 và B1 song song khi điều kiện cho phép.
Không xử lý A2 như đã xong trước A1 nếu order#A cần thứ tự.
~~~

### 10.1. Chọn MessageGroupId

- **Theo order ID:** các sự kiện của cùng đơn hàng tuần tự; nhiều đơn có thể song song.
- **Theo customer ID:** đảm bảo thứ tự cho một khách; khách rất hoạt động có thể trở thành hot group.
- **Một giá trị cố định “global” cho mọi message:** dễ lập trình nhưng **giới hạn concurrency** của toàn bộ queue một cách không cần thiết.

`MessageGroupId` nên thể hiện **ranh giới cần ordering thực sự**, không phải chỉ là chuỗi ngẫu nhiên để phân phối tải. Dùng quá nhiều nhóm cũng cần xem throughput quota, storage và downstream consistency.

### 10.2. Deduplication không thay thế idempotency

FIFO hỗ trợ deduplication trong cửa sổ thời gian do SQS quy định (thông dụng khoảng **5 phút**). Producer có thể gửi `MessageDeduplicationId`, hoặc dùng content-based dedup nếu đã bật và phù hợp.

Nhưng:

- Sau cửa sổ dedup hoặc khi re-enqueue một event, duplicate nghiệp vụ vẫn có thể xuất hiện.
- Nếu worker đã commit DB nhưng Delete không thành công, message vẫn có thể được giao lại.
- Nếu `MessageDeduplicationId` được đặt bằng giá trị không ổn định cho cùng business event, cơ chế dedup không giúp được.

Thiết kế idempotency bền vững ở business datastore, ví dụ unique constraint trên `eventId` hoặc conditional write trong DynamoDB, vẫn là nền tảng chính.

### 10.3. FIFO và partial failure

Trong FIFO batch:

- Đảm bảo không xử lý message sau phần tử lỗi trong cùng group.
- Với Lambda `ReportBatchItemFailures`, dừng ở lỗi đầu tiên và trả IDs của **failed + unprocessed** theo khuyến nghị AWS.
- Với ECS custom consumer, commit và delete theo thứ tự từng group; dùng một worker/partition owner có cơ chế điều phối rõ.
- DLQ có thể làm thay đổi thứ tự nghiệp vụ khi message bị đưa ra khỏi queue; nếu ordering tuyệt đối quan trọng, phải xem xét kỹ việc dùng DLQ.

Không đánh đổi integrity của đơn hàng chỉ để tăng concurrency.

## 11. Idempotency: điều kiện thiết yếu của xử lý batch

### 11.1. Tình huống side effect xảy ra hai lần

~~~mermaid
sequenceDiagram
    participant Q as SQS
    participant W as Consumer
    participant DB as Database
    W->>Q: Receive eventId=evt-101
    Q-->>W: receiptHandle H1
    W->>DB: INSERT delivery record
    DB-->>W: Commit thành công
    Note over W: Crash trước Delete
    Q-->>W: Redelivery evt-101 với receiptHandle H2
    W->>DB: Thử INSERT lại
    DB-->>W: Unique eventId đã tồn tại
    W->>Q: DeleteMessage H2
~~~

Nếu consumer không kiểm tra duplicate, hệ thống có thể tạo hai shipment hoặc gửi hai email. Với một số nghiệp vụ, email trùng chỉ khó chịu; với thanh toán, lỗi có thể rất nghiêm trọng.

### 11.2. Pattern database unique event ID

Giả sử bảng `processed_events` có unique key `event_id`:

~~~sql
BEGIN;

INSERT INTO processed_events(event_id, processed_at)
VALUES ('evt-101', CURRENT_TIMESTAMP);

-- Chỉ khi insert unique thành công:
UPDATE orders SET status = 'READY_TO_SHIP'
WHERE order_id = 'order-101';

COMMIT;
~~~

Đây là minh họa SQL, cần bổ sung logic trong ứng dụng để:

- Bắt **unique conflict** của event đã xử lý và coi đó là kết quả idempotent hợp lệ khi state tương ứng đã có.
- Thực hiện **insert marker và business update trong cùng transaction**, tránh marker được commit trước rồi business update thất bại.
- Với side effect ra **API ngoài database**, dùng outbox/idempotency key của provider hoặc state machine bền vững; một transaction local không atomic với hệ thống bên ngoài.
- Đặt retention của idempotency keys đủ dài theo cửa sổ retry/replay; không xóa marker quá sớm.

### 11.3. Hệ thống thanh toán

Với payment, hãy dùng **business-level idempotency key** như `paymentId` hoặc `eventId` đáng tin từ nguồn phát sự kiện. Không tự nhận `MessageId` làm định danh giao dịch thanh toán khi sự kiện có thể được gửi lại qua một queue khác hoặc republish với MessageId mới.

## 12. Dead-Letter Queue và xử lý poison messages

**Poison message** là message liên tục khiến consumer thất bại, ví dụ payload sai schema, ID không tồn tại hoặc dữ liệu buộc thao tác trái quyền.

~~~mermaid
flowchart LR
    Q["Source SQS queue"] --> C["Consumer"]
    C -->|"Success"| DONE["Delete message"]
    C -->|"Transient error"| WAIT["Visibility hết hạn + retry"]
    WAIT --> Q
    Q -->|"Số lần nhận vượt ngưỡng"| DLQ["SQS DLQ"]
    DLQ --> REVIEW["Điều tra root cause\nPhân loại + quyết định sửa"]
    REVIEW -->|"Redrive có kiểm soát"| Q
~~~

### 12.1. `maxReceiveCount` nên đặt bao nhiêu?

Không có một con số phù hợp mọi workload:

| Tình huống | Hướng cân nhắc |
| --- | --- |
| Lỗi network/timeout ngắn hạn | Cho phép vài lần retry với backoff |
| Đối tác API outage kéo dài | Có thể cần defer/retry queue thay vì liên tục nhận lại |
| Invalid JSON/schema | Sửa producer hoặc đưa DLQ sớm, không retry nóng vô ích |
| Lỗi IAM/permanent permission | Cảnh báo kỹ thuật và sửa chính sách; retry đơn thuần không giải quyết |

**Đừng đặt `maxReceiveCount` quá thấp** nếu hệ thống hay có lỗi tạm thời, cũng không đặt quá cao khiến poison messages chiếm chỗ lâu và làm backlog age SLO xấu.

### 12.2. DLQ không tự sửa dữ liệu

Một runbook DLQ:

1. Theo dõi số lượng và tuổi message trong DLQ.
2. Lấy **mẫu payload phù hợp với quyền dữ liệu**, đọc error context trong logs/traces.
3. Phân loại lỗi: producer schema, IAM, dependency, bug, expired business state.
4. Sửa root cause hoặc ghi nhận quyết định **không thể xử lý**.
5. Chọn **redrive** với tốc độ tối đa/giới hạn theo khả năng downstream; kiểm tra idempotency.
6. Xác nhận kết quả sau redrive và lưu audit.

SQS hỗ trợ các cơ chế **DLQ redrive** theo điều kiện/tính năng API phù hợp. Redrive quy mô lớn cũng có thể tạo burst và cần backpressure giống enqueue bình thường. Cần quyền IAM và policy cho queue nguồn/đích; không dùng quyền rộng hơn yêu cầu.

### 12.3. Thời gian giữ DLQ

Với Standard queues, cách tính message age sau khi chuyển DLQ có điểm khác FIFO. Khi chọn retention DLQ, AWS thường khuyến nghị **DLQ retention dài hơn source queue retention** để có thời gian điều tra. Không chỉ nhìn `ApproximateAgeOfOldestMessage` rồi tự kết luận toàn bộ tuổi dữ liệu; cần đối chiếu thời điểm enqueue/first received nếu workflow cần tính chính xác.

### 12.4. Khi DLQ không phải lời giải duy nhất

Nếu toàn bộ messages đều thất bại do downstream ngừng phục vụ 2 giờ, đưa tất cả vào DLQ rồi redrive có thể không tối ưu. Thay vào đó có thể **tạm giảm/tắt consumer**, giữ backlog trong source queue, hoặc dùng retry queue/delay theo loại lỗi. Quyết định phải xem message retention, SLO và mức độ cần ưu tiên công việc mới.

## 13. Mở rộng consumer với ECS/Fargate

Khi chạy worker như một **ECS service**, bạn có thể tăng/giảm số ECS tasks thông qua **Service Auto Scaling**. Với workload SQS, số lượng message chờ thường là tín hiệu hữu ích hơn CPU utilization đơn lẻ.

### 13.1. Luồng autoscaling

~~~mermaid
flowchart LR
    Q["SQS queue\nvisible backlog"] --> METRIC["CloudWatch metric\nbacklog per running task"]
    RUN["ECS running tasks\ncurrent capacity"] --> METRIC
    METRIC --> POLICY["Application Auto Scaling\ntarget tracking/custom policy"]
    POLICY --> ECS["ECS Service\nDesiredCount"]
    ECS --> WORK["Worker tasks\nbounded concurrency"]
    WORK --> DB["Database / APIs\ncapacity guardrails"]
    WORK -->|"Delete on success"| Q
~~~

Một cấu hình vận hành có thể:

- Duy trì **min desired count** để xử lý nhanh và tránh metric chia cho 0 khi queue có message.
- Đặt **max desired count** theo quota ECS/Fargate, IP capacity trong VPC, giới hạn DB/API và ngân sách.
- Đẩy **custom CloudWatch metric** backlog-per-running-task hoặc dùng metric math được hỗ trợ để tính tỉ lệ.
- Dùng target tracking theo mục tiêu số message/task; thiết lập **scale-in/scale-out cooldown** phù hợp thời gian task khởi động và thời lượng xử lý.
- Giữ worker có cơ chế **graceful shutdown** và bounded in-flight tasks, tránh scale-in làm nhiều messages trở lại queue cùng lúc.

### 13.2. Ví dụ chính sách theo SLO

Giả sử:

~~~text
SLO: message phải bắt đầu xử lý trong 30 giây (phần queue wait)
1 worker xử lý bền vững: 25 msg/s
Target backlog per worker: 25 × 30 = 750 visible messages

Max worker capacity theo downstream: 30 tasks
Desired count target:
  ceil(VisibleBacklog / 750), giới hạn [minTasks, 30]
~~~

Nếu visible backlog tăng tới 45.000, kết quả lý tưởng là `ceil(45000/750)=60` tasks, **nhưng maxTasks=30** vì downstream không chịu được thêm. Hệ thống không thể vừa bảo đảm queue wait dưới 30 giây vừa giữ nguyên giới hạn downstream trong đợt quá tải này; cần **đưa ra quyết định nghiệp vụ**: chấp nhận chậm, hạn chế producer, tối ưu downstream hoặc tăng công suất downstream trước.

**Autoscaling không phải cơ chế bỏ qua backpressure.** Trần concurrency dựa trên năng lực thật quan trọng hơn việc làm đẹp metric backlog.

### 13.3. Scale-in và in-flight work

Khi backlog giảm, autoscaler có thể giảm task count. Nhưng một task vẫn đang xử lý batch:

~~~text
ECS service gửi SIGTERM
→ worker dừng ReceiveMessage mới
→ xử lý/commit các message đang giữ
→ xóa những message thành công
→ thả các message chưa xong để retry sau visibility
→ exit
~~~

Thiết kế stop timeout, visibility extension và idempotency giúp tránh downtime khi rollout hoặc scale-in. Đừng cấu hình `minTasks=0` nếu chưa có cơ chế bảo đảm scale từ zero hoạt động khi có backlog (metric, alarms, target tracking, startup delay).

### 13.4. Autoscaling không giải quyết queue priority

Nếu queue trộn:

- Notification thường: 100.000 messages.
- Hoàn tiền khẩn cấp: 20 messages.

Các worker có thể phải xử lý rất nhiều notification trước khi đến công việc khẩn. SQS Standard **không cung cấp một priority queue tổng quát** chỉ bằng một trường `priority` trong body. Có thể thiết kế **hai queues** (urgent/normal) với pools/capacity allocation khác nhau, hoặc scheduler kiểm soát công bằng. Đừng tự tin rằng scale thêm worker sẽ đảm bảo ưu tiên đúng.

## 14. Liên kết SNS, EventBridge và SQS

### 14.1. Fan-out qua SNS

Một sự kiện `order.placed` có thể cần được xử lý bởi:

- Inventory service.
- Email notification service.
- Fraud screening service.

Thay vì producer tự gửi ba messages vào ba queues, có thể dùng **SNS topic → nhiều SQS subscriptions**:

~~~mermaid
flowchart TB
    P["Order Service"] --> SNS["Amazon SNS Topic\norder-events"]
    SNS --> Q1["SQS queue: inventory"]
    SNS --> Q2["SQS queue: email"]
    SNS --> Q3["SQS queue: fraud-check"]
    Q1 --> W1["Inventory consumer"]
    Q2 --> W2["Email consumer"]
    Q3 --> W3["Fraud consumer"]
~~~

**Lợi ích:** mỗi nhóm có queue riêng, backlog/retry/DLQ và capacity scaling riêng. Nếu Email provider trả 429, có thể giảm email consumers mà không làm chậm Fraud worker.

### 14.2. SNS filter policies và message envelope

SNS subscription filter policies có thể giảm thông báo không liên quan được đẩy tới một queue. Khi SNS gửi tới SQS, body có thể chứa **SNS notification envelope** hoặc chỉ payload nguyên gốc tùy **raw message delivery** được bật. Consumer phải parse đúng format đã cấu hình; không lấy JSON schema của producer làm chuẩn duy nhất nếu đi qua SNS.

### 14.3. Queue policy cho SNS

Ví dụ **SQS queue resource policy** chỉ cho một SNS topic gửi vào queue:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOnlyOrderEventsTopic",
      "Effect": "Allow",
      "Principal": { "Service": "sns.amazonaws.com" },
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:123456789012:inventory-queue",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:123456789012:order-events"
        }
      }
    }
  ]
}
~~~

Chỉ là minh họa: cần thiết lập IAM/KMS permissions nếu queue được mã hóa bằng SSE-KMS và kiểm tra source account/organizational conditions theo chính sách. Không dùng Principal `"*"` và resource rộng khi không cần. Nếu nguồn là EventBridge thì principal/conditions và integration khác SNS.

### 14.4. EventBridge làm gì?

**EventBridge** hữu ích khi cần rules lọc/định tuyến event theo nguồn, loại sự kiện và cấu trúc payload; một rule có thể target SQS queue theo cơ chế được hỗ trợ. EventBridge không thay thế consumer retry/acknowledgement semantics sau khi sự kiện nằm trong SQS.

Khi chọn SNS hoặc EventBridge, xem xét:

- Event schema, filtering và routing nhu cầu.
- Ordering/deduplication được yêu cầu và dịch vụ/target hỗ trợ.
- Failure handling, DLQ cho **event delivery tới queue** và DLQ cho **consumer xử lý sau khi queue nhận** — hai chặng lỗi khác nhau.
- IAM/resource policy, phí message/requests và latency.

## 15. An toàn, IAM và bảo vệ dữ liệu

### 15.1. Principal nào cần quyền nào?

| Thành phần | Quyền AWS liên quan | Tại sao |
| --- | --- | --- |
| **Producer** | `sqs:SendMessage` | Đẩy một message vào queue |
| **Producer gửi batch** | `sqs:SendMessage` (quyền dùng cho API `SendMessageBatch`) | Gửi nhiều messages theo API batch |
| **Custom consumer** | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility`, `sqs:GetQueueAttributes` | Poll, ack, gia hạn visibility và đọc queue attributes |
| **Lambda SQS event source** | Execution role có các quyền SQS polling/deleting phù hợp | Cho Lambda pollers lấy và xác nhận messages |
| **DLQ operator** | Quyền đọc/điều tra/redrive queues theo IAM và redrive policies | Khôi phục có kiểm soát |
| **SNS/EventBridge publisher** | `sqs:SendMessage` trong queue resource policy từ nguồn được tin cậy | Cho phép service gửi tới queue mục tiêu |
| **KMS** | `kms:GenerateDataKey`, `kms:Decrypt` hoặc quyền tương ứng khi dùng customer-managed key | Producer/consumer sử dụng queue SSE-KMS theo policy |

**Phân biệt tên API và tên quyền IAM:** `SendMessageBatch` sử dụng quyền `sqs:SendMessage`; tương tự, `DeleteMessageBatch` cần `sqs:DeleteMessage` và `ChangeMessageVisibilityBatch` cần `sqs:ChangeMessageVisibility`. Đừng tự suy rằng mọi tên batch API đều là một IAM action riêng. Trước khi áp dụng policy, đối chiếu **AWS Service Authorization Reference** theo phiên bản hiện hành. Cấp quyền vào **queue ARN cụ thể**, không mặc định `sqs:*` trên mọi queue.

### 15.2. Producer và consumer nên tách IAM role

Ví dụ với ECS/Fargate:

- **Producer task role** chỉ gửi message tới `jobs-queue`.
- **Consumer task role** nhận/xóa/đổi visibility từ queue ấy và gọi đúng downstream.
- **Task execution role** cho ECR/logging/secrets của ECS không nên bị dùng thay mọi quyền nghiệp vụ.

Với Lambda consumer, execution role phải có permissions tương ứng và, nếu queue mã hóa SSE-KMS bằng customer-managed key, có quyền KMS cần thiết. Thiếu quyền có thể làm poller không nhận được messages mà producer vẫn gửi thành công.

### 15.3. Chính sách dữ liệu trong message

SQS body/attributes có thể chứa dữ liệu nhạy cảm; không coi SQS là khu vực công khai chỉ vì nó là “queue”:

- **Không lưu mật khẩu, token dài hạn hoặc thông tin thẻ** trong message nếu không cần.
- Dùng IDs và tra cứu dữ liệu qua API có IAM/authorization nếu thông tin nhạy cảm.
- Bật **server-side encryption** phù hợp và quản lý KMS keys.
- Thiết lập VPC endpoint policies, IAM, CloudTrail và queue policies theo nhu cầu.
- Log `messageId`, `eventId` và status, tránh log toàn body chứa PII.
- Quy định **retention** và xóa thông tin theo nghĩa vụ pháp lý.

### 15.4. Chống dữ liệu do client giả mạo

Producer có thể gửi:

~~~json
{
  "eventId": "evt-99",
  "orderId": "order-777",
  "status": "PAID"
}
~~~

Consumer không nên coi body đó tự động là bằng chứng thanh toán hợp lệ. Cần xác thực nguồn hoặc trạng thái từ system of record, validate schema, kiểm tra quyền và dùng idempotency. Queue là phương tiện truyền công việc **không tự biến message thành dữ liệu đáng tin**.

## 16. Quan sát production và cảnh báo theo SLO

Hãy xác định riêng:

1. **Ingress SLO:** producer enqueue được message hay không?
2. **Queue wait SLO:** message chờ bao lâu mới được consumer nhận?
3. **Processing SLO:** sau khi bắt đầu, xử lý xong mất bao lâu?
4. **End-to-end SLO:** từ event nghiệp vụ được commit tới side effect hoàn tất mất bao lâu?
5. **Failure/recovery:** bao nhiêu messages cần retry, đã vào DLQ hoặc hết retention?

### 16.1. Dashboard gợi ý

| Panel | Metric/nguồn | Cách dùng |
| --- | --- | --- |
| Visible backlog | `ApproximateNumberOfMessagesVisible` | Theo dõi lượng việc còn chờ |
| In-flight messages | `ApproximateNumberOfMessagesNotVisible` | Theo dõi tài nguyên đang xử lý/có thể bị giữ quá mức |
| Oldest message age | `ApproximateAgeOfOldestMessage` | Cảnh báo vi phạm queue wait SLA |
| Sent/received/deleted | `NumberOfMessagesSent/Received/Deleted` | Xem xu hướng ingress/processing, có thể gồm duplicates |
| DLQ visible backlog | Queue metrics của DLQ | Phát hiện poison messages |
| Lambda errors/duration/throttles | CloudWatch Lambda | Theo dõi trigger xử lý và concurrency |
| ECS running/desired tasks | ECS Service/Container Insights | Xem capacity thực tế vs mục tiêu |
| DB pool, 429, latency | Custom metrics/APM | Tìm đúng bottleneck downstream |
| Cost | AWS Cost Explorer/Budgets | Kiểm soát API requests, Lambda/ECS, logs, KMS |

Khi metrics queue giảm nhưng lỗi nghiệp vụ tăng, có thể consumer đang **delete nhầm failed messages**. Vì vậy phải theo dõi **business success counter** từ ứng dụng, không kết luận chỉ vì queue đã trống.

### 16.2. Alert thresholds theo ý nghĩa

Ví dụ nhóm đặt SLO: 99% notification phải xử lý trong 2 phút.

~~~text
Warning:
  ApproximateAgeOfOldestMessage > 60 giây liên tục

Critical:
  ApproximateAgeOfOldestMessage > 120 giây liên tục
  hoặc DLQ có messages không mong muốn

Scale signal:
  BacklogPerRunningTask vượt target backlog
  với cooldown và max capacity theo DB/API
~~~

Các ngưỡng chỉ minh họa, phải kiểm định theo **độ trễ metrics**, pattern burst, FIFO group blocking và loại workload. Nên bổ sung synthetic event hoặc trace timestamps để đo latency end-to-end chính xác hơn.

### 16.3. Không đọc lầm metrics SQS

- `NumberOfMessagesReceived` có thể bao gồm cùng message được nhận nhiều lần.
- `NumberOfMessagesDeleted` là số lần delete request được ghi nhận theo metric semantics, không nhất thiết số unique business transactions.
- `ApproximateNumberOfMessagesVisible` có độ trễ/ước lượng, không phải transaction count.
- `ApproximateAgeOfOldestMessage` có semantics riêng khi messages bị retry/redrive; không suy diễn thành p99 latency.
- Một queue FIFO với **một MessageGroupId bị kẹt** có thể còn nhiều messages nhưng tăng consumer count **không giúp** group đó chạy song song.

## 17. Runbook xử lý backlog tăng đột ngột

Giả sử dashboard báo:

~~~text
Visible backlog: 150.000 messages, đang tăng
Oldest age: 9 phút
Consumer count: 20 ECS tasks
DB p99 latency: 5 giây, kết nối gần giới hạn
DLQ: chưa có message
~~~

**Không lập tức scale từ 20 lên 200 tasks.** DB đang bị giới hạn. Runbook:

1. **Xác nhận dữ liệu:** queue đúng Region/account, backlog có thật, messages in-flight và arrival rate đang là bao nhiêu?
2. **Phân biệt lỗi:** producer burst, consumer crash, IAM, throttling hay DB latency? Xem ECS/Lambda logs và APM.
3. **Ổn định downstream:** giới hạn DB concurrency, tăng capacity DB nếu có thể và an toàn; khắc phục lỗi lock/query.
4. **Giảm áp lực:** tạm giới hạn producer không quan trọng, ưu tiên queue nghiệp vụ khẩn, bật circuit breaker/retry backoff có giới hạn.
5. **Đo throughput an toàn:** khi DB hồi phục, xác định mỗi task xử lý bao nhiêu msg/s bền vững.
6. **Scale có trần:** tăng tasks trong phạm vi DB/IP/quota, theo dõi tuổi message và DB p99.
7. **Kiểm tra duplicates/DLQ:** sau sự cố, kiểm tra failed/retried jobs và bảo vệ idempotency.
8. **Hậu kiểm:** bổ sung alarms, capacity runbook, load test và quyết định về tách queues.

### 17.1. Khi nào giảm producer?

Nếu producer rate vẫn vượt total safe throughput trong thời gian dài, thêm worker mà không tăng downstream capacity **không tiêu được backlog**. Có thể:

- Dùng admission control hoặc trả HTTP `429`/`503` theo contract cho yêu cầu có thể retry.
- Giới hạn ingress theo tenant hoặc loại công việc.
- Gộp/coalesce events ít quan trọng (ví dụ chỉ cần trạng thái cuối cùng của một dashboard) khi nghiệp vụ cho phép.
- Tách các luồng urgent/non-urgent thành queues riêng.
- Tạo service degradation mode tạm thời thay vì để mọi request timeout.

Việc **drop message** phải là chính sách nghiệp vụ rõ ràng, không phải hậu quả ngẫu nhiên vì queue hết retention.

## 18. Ví dụ cấu hình CloudFormation: SQS + DLQ + Lambda mapping

Đoạn sau minh họa mối quan hệ giữa SQS source queue, DLQ và event source mapping; **không bao gồm Lambda function/IAM role triển khai thực**. Các placeholders phải thay bằng ARN/function thật trong môi trường lab đã được cấp phép.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: SQS worker batching and partial failures (learning fragment)

Parameters:
  WorkerFunctionArn:
    Type: String

Resources:
  JobsDLQ:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: jobs-lab-dlq
      MessageRetentionPeriod: 1209600  # 14 ngày

  JobsQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: jobs-lab
      VisibilityTimeout: 185
      MessageRetentionPeriod: 345600  # 4 ngày
      ReceiveMessageWaitTimeSeconds: 20
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt JobsDLQ.Arn
        maxReceiveCount: 5

  JobsEventSourceMapping:
    Type: AWS::Lambda::EventSourceMapping
    Properties:
      EventSourceArn: !GetAtt JobsQueue.Arn
      FunctionName: !Ref WorkerFunctionArn
      Enabled: true
      BatchSize: 10
      MaximumBatchingWindowInSeconds: 5
      FunctionResponseTypes:
        - ReportBatchItemFailures
      ScalingConfig:
        MaximumConcurrency: 20
~~~

**Giới hạn của fragment:**

- Không tạo function; chưa cấp execution role `ReceiveMessage`/`DeleteMessage`/`GetQueueAttributes` và quyền KMS nếu dùng SSE-KMS customer key.
- `VisibilityTimeout=185` chỉ phù hợp với ví dụ function timeout/ batching window tương ứng; phải tính lại theo function thật và khuyến nghị AWS.
- Mã Lambda **phải return batchItemFailures đúng hợp đồng**; chỉ bật config không tự tạo partial handling.
- `MaximumConcurrency=20` là minh họa guardrail, **không phải mức tối ưu** cho mọi downstream.
- Queue Standard được dùng; muốn FIFO phải tạo FIFO queue/DLQ, thêm `FifoQueue: true` và các quy tắc message group/dedup phù hợp.
- CloudFormation tạo tài nguyên có thể tính phí; cần plan, rollback và dọn lab sau khi học.

## 19. AWS CLI chỉ đọc: quan sát queue, DLQ và mapping

Thay account ID/queue name/API IDs và Region theo tài nguyên **mà bạn có quyền xem**. Các lệnh sau chỉ đọc; không gọi ReceiveMessage vì nhận message có thể **thay visibility và receive count**, ảnh hưởng consumer production.

### 19.1. Xem danh tính và các queue

~~~bash
aws sts get-caller-identity

aws sqs list-queues \
  --region ap-southeast-1 \
  --queue-name-prefix jobs-lab

aws sqs get-queue-attributes \
  --region ap-southeast-1 \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/123456789012/jobs-lab \
  --attribute-names All
~~~

Đọc các attributes như `VisibilityTimeout`, `ReceiveMessageWaitTimeSeconds`, `RedrivePolicy`, `MessageRetentionPeriod`, `ApproximateNumberOfMessages` và `ApproximateNumberOfMessagesNotVisible`. Các số lượng messages là **gần đúng**, không phải kiểm kê giao dịch chính xác.

### 19.2. Quan sát mapping Lambda → SQS

~~~bash
aws lambda list-event-source-mappings \
  --region ap-southeast-1 \
  --event-source-arn arn:aws:sqs:ap-southeast-1:123456789012:jobs-lab \
  --query "EventSourceMappings[].{UUID:UUID,State:State,BatchSize:BatchSize,Window:MaximumBatchingWindowInSeconds,ResponseTypes:FunctionResponseTypes,Scaling:ScalingConfig}" \
  --output json
~~~

Xem function ARN, trạng thái mapping, batch size, batching window và `FunctionResponseTypes`. Nếu function code trả `batchItemFailures` nhưng `FunctionResponseTypes` không có `ReportBatchItemFailures`, partial response chưa được kích hoạt.

### 19.3. Xem CloudWatch queue metrics

~~~bash
aws cloudwatch list-metrics \
  --region ap-southeast-1 \
  --namespace AWS/SQS \
  --metric-name ApproximateAgeOfOldestMessage

aws cloudwatch list-alarms \
  --region ap-southeast-1 \
  --alarm-name-prefix jobs-lab
~~~

`list-metrics` chỉ liệt kê series metadata và có thể bỏ qua series không có dữ liệu gần đây; không trả một time series để phân tích. Để xem datapoints, dùng `get-metric-data`/`get-metric-statistics` hoặc CloudWatch Console với dimensions/time range phù hợp.

### 19.4. Xem ECS consumer service nếu dùng ECS

~~~bash
aws ecs describe-services \
  --region ap-southeast-1 \
  --cluster shop-workers \
  --services notification-worker \
  --query "services[].{Name:serviceName,Desired:desiredCount,Running:runningCount,Pending:pendingCount,Events:events[0:5].message}" \
  --output json
~~~

Nếu service không tồn tại, đó chỉ cho thấy mô hình ECS không được triển khai ở tên/Region đang xem. Không suy đoán rằng queue chưa có consumer; có thể đang dùng Lambda hoặc một application khác.

## 20. Bài tập củng cố

### Bài tập 1 — Partial success của SendMessageBatch

Một batch gửi 10 messages trả `Successful=8` và `Failed=2`. Producer định gửi lại cả 10.

**Gợi ý:** không nên gửi lại tám messages đã được xác nhận thành công; retry hai entries lỗi nếu lỗi có thể retry, và duy trì business idempotency nếu có request timeout/uncertain acknowledgement.

### Bài tập 2 — Receive 10 nhưng chỉ được 3

Consumer gọi `ReceiveMessage(MaxNumberOfMessages=10, WaitTimeSeconds=20)`, nhưng nhận ba messages dù queue còn nhiều.

**Gợi ý:** `MaxNumberOfMessages` là **giới hạn trên**, không phải cam kết đủ batch. Đừng coi đây là lỗi cần retry ngay; long polling và thiết kế concurrency là quan trọng hơn.

### Bài tập 3 — Lambda partial failure

Một invocation có năm records, record thứ ba lỗi, bốn records khác commit thành công. Mapping chưa bật `ReportBatchItemFailures` nhưng code return:

~~~json
{"batchItemFailures":[{"itemIdentifier":"m3"}]}
~~~

**Gợi ý:** phải bật `FunctionResponseTypes: ReportBatchItemFailures` trên mapping. Nếu không, cơ chế xử lý không nhất thiết dùng partial failure response như dự định; nguy cơ xóa nhầm/ retry sai cần được tránh.

### Bài tập 4 — FIFO message group

Một FIFO queue có 50.000 messages nhưng **tất cả** dùng `MessageGroupId=global`. Worker count tăng từ 2 lên 100 mà throughput vẫn không tăng đáng kể.

**Gợi ý:** một message group cần ordering tuần tự, nên không có 100 nhóm độc lập để tận dụng 100 workers. Thiết kế group theo ranh giới thứ tự nghiệp vụ như order ID khi có thể, không phá ordering chỉ để tăng tốc.

### Bài tập 5 — Backpressure database

Database cho phép an toàn 50 requests đồng thời, nhưng 20 ECS tasks × 10 threads/task có thể gửi 200 requests đồng thời. Backlog tăng và DB p99 tăng mạnh.

**Gợi ý:** tăng worker count sẽ làm tình hình xấu hơn. Giới hạn concurrency toàn fleet theo DB, giảm local threads hoặc dùng distributed semaphore, sau đó tối ưu DB/throughput hoặc chấp nhận backlog.

### Bài tập 6 — Capacity planning

SQS nhận 450 msg/s, mỗi worker xử lý bền vững 30 msg/s. Bỏ qua headroom, cần tối thiểu bao nhiêu workers để theo kịp tốc độ tới?

**Gợi ý:** `ceil(450/30)=15 workers`. Trong thực tế cần margin cho lỗi/retry, gián đoạn AZ và quota downstream.

### Bài tập 7 — Ack sau commit

Worker đã ghi dữ liệu thành công, nhưng crash trước `DeleteMessage`. Message được redeliver.

**Gợi ý:** đảm bảo idempotency bằng business event ID duy nhất/conditional write và chỉ delete sau durable commit. Việc nhận lại là tình huống dự kiến với at-least-once.

### Bài tập 8 — DLQ redrive

Sau outage của đối tác, DLQ có 40.000 notifications. Đội vận hành muốn redrive tất cả cùng lúc mà chưa xác minh đối tác đã hồi phục.

**Gợi ý:** cần xác định root cause, xác nhận endpoint hồi phục, giới hạn redrive rate, kiểm tra duplicates, metric backlog/429 và có kế hoạch dừng nếu gây quá tải lại.

### Bài tập 9 — Backlog tuổi thấp nhưng lỗi nghiệp vụ cao

CloudWatch cho thấy queue hầu như trống, nhưng khách hàng báo thiếu email. Worker code bắt mọi exception và luôn xóa message.

**Gợi ý:** không dùng queue depth làm chỉ số duy nhất; consumer đang **acknowledge thất bại như thành công**. Sửa per-message result handling, test retry/DLQ và thêm business success metrics.

### Bài tập 10 — Tách SNS fan-out

Order Service gửi event cho Inventory, Email và Fraud. Email API có quota nhỏ và thường trả 429.

**Gợi ý:** SNS/EventBridge route sự kiện vào **queues độc lập**, mỗi queue có consumer capacity/retry/DLQ riêng. Không để email retry storm chặn inventory/fraud.

## 21. Checklist triển khai production

- [ ] Phân loại Standard hay FIFO; message groups/order requirements và deduplication được xác định.
- [ ] Producer dùng batch có kiểm tra `Successful/Failed` từng entry, retry có giới hạn và idempotency/outbox khi cần.
- [ ] Consumer nhận tối đa batch SQS cho phép, long polling đúng timeout; không over-prefetch khi worker đầy.
- [ ] Side effect commit bền vững trước Delete; receipt handle và duplicate handling được kiểm thử.
- [ ] Visibility timeout phù hợp P99 runtime, gia hạn có giới hạn; Lambda mapping phù hợp function timeout/window.
- [ ] Lambda ESM bật `ReportBatchItemFailures` nếu cần partial response; FIFO không xử lý vượt message lỗi cùng group.
- [ ] Bounded concurrency, downstream rate limiter, retry/backoff + jitter và circuit breaker đã thiết kế.
- [ ] Autoscaling dùng backlog, oldest age và throughput; max concurrency không vượt DB/API capacity.
- [ ] DLQ/redrive policy, retention và quyền operator được thiết kế; đã thử poison message và controlled redrive.
- [ ] IAM roles producer/consumer tách biệt; queue policies, SNS/EventBridge sources và SSE-KMS được kiểm tra.
- [ ] Có metrics về queue depth, age, in-flight, retries, processing errors, DLQ, business success và chi phí.
- [ ] Graceful shutdown và scale-in của ECS workers không làm mất công việc hoặc tràn in-flight.
- [ ] Capacity khi một AZ lỗi, limits/quota và chi phí Lambda/ECS/SQS/KMS/logs đã được đánh giá.
- [ ] Có runbook cho burst, outage downstream, duplicate messages và điều tra dead letters.
- [ ] Môi trường lab/staging đã kiểm thử partial failure, concurrency cap và graceful recovery trước production.

## 22. Ghi nhớ

Một hệ thống queue chịu tải tốt cần phối hợp **batching, backpressure và consumer scaling**:

1. **Batch operation** giảm overhead request, nhưng SQS batch APIs có **partial success**; muốn không mất dữ liệu phải theo dõi kết quả **từng message**.
2. **Visibility timeout, Delete và at-least-once** khiến message có thể xuất hiện lại. **Idempotency** ở business datastore là lớp bảo vệ quan trọng.
3. **Backpressure** không phải “càng nhiều worker càng tốt”: giới hạn concurrency theo khả năng DB/API và dùng retry có backoff để tránh cascading failures.
4. **Consumer scaling** phải dựa trên backlog, tuổi message và throughput **thực tế**, có trần capacity và phương án khi downstream đang hỏng.
5. **Lambda SQS event source mapping** cho batching/partial failures/controlled concurrency; **ECS/EC2 workers** cho phép tự thiết kế poll loop và bounded thread pools.
6. **FIFO ordering, DLQ và SNS fan-out** thêm những ràng buộc phải hiểu; không công cụ nào tự tạo exactly-once processing end-to-end.

Mục tiêu cuối cùng không chỉ là **queue hết message**, mà là mỗi công việc nghiệp vụ được xử lý **đúng, kịp thời, có thể retry/khôi phục và trong giới hạn chi phí/khả dụng đã phê duyệt**.

### Tài liệu AWS chính thức để đọc thêm

- [Amazon SQS Developer Guide](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html) — khái niệm, API và vận hành SQS.
- [Using SendMessageBatch with SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-batch-api-actions.html) — batch API và xử lý partial failures.
- [Amazon SQS short and long polling](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-short-and-long-polling.html) — lựa chọn polling và WaitTimeSeconds.
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html) — in-flight, redelivery và extension.
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html) — maxReceiveCount, retention và redrive.
- [Amazon SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-fifo-queues.html) — message group, ordering và deduplication.
- [Configuring Lambda to use Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html) — batching window, timeout, permissions và scaling.
- [Handling errors for an SQS event source in Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html) — retry và partial batch responses.
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html) — polling, invocation, failure semantics.
- [Using maximum concurrency for Amazon SQS event sources](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-scaling.html) — scaling behavior và guardrails.
- [Amazon ECS Service Auto Scaling](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service-auto-scaling.html) — ECS task count scaling policies.
- [SQS available CloudWatch metrics](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html) — backlog, age, sent/received/deleted.
- [SQS IAM and security](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-authentication-and-access-control.html) — quyền truy cập queue và resource policy.
- [Amazon SNS fanout to SQS queues](https://docs.aws.amazon.com/sns/latest/dg/sns-sqs-as-subscriber.html) — phân phối sự kiện tới nhiều queues.
- [AWS SDK for Java 2.x: SQS examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_sqs_code_examples.html) — Java SDK send, receive và delete.
- [Amazon SQS pricing](https://aws.amazon.com/sqs/pricing/) — API requests và cost structure.
