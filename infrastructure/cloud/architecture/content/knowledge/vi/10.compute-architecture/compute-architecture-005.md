# Thiết kế xử lý nền, tác vụ định kỳ và công việc theo lô

## Mục tiêu học tập

Trong kiến trúc ứng dụng đám mây (**Cloud Architecture**), không phải công việc nào cũng nên chạy trực tiếp trong request HTTP mà người dùng đang chờ. Gửi email, tạo báo cáo, đồng bộ ERP, xử lý ảnh, đối soát thanh toán và nhập hàng triệu bản ghi thường cần thời gian dài hoặc phụ thuộc hệ thống ngoài. Đưa những công việc này vào **xử lý nền** (*background processing*) giúp API phản hồi nhanh hơn, kiểm soát tải và phục hồi công việc sau sự cố.

Bài học phân biệt ba dạng chính: xử lý nền theo sự kiện/hàng đợi (*event-driven background processing*), tác vụ định kỳ (*scheduled jobs*) và công việc theo lô (*batch processing*). Các dạng này có thể phối hợp với nhau, nhưng khác về cách kích hoạt, khối lượng dữ liệu, trạng thái và cách phục hồi.

Sau bài học, bạn có thể chọn queue, worker, scheduler, managed job hoặc batch framework; thiết kế retry, timeout, idempotency, DLQ và checkpoint; ước lượng concurrency, throughput, backlog, thời gian hoàn thành và chi phí; giám sát trạng thái công việc; đồng thời đánh giá độ tin cậy, bảo mật, khả năng mở rộng và vận hành theo nguyên tắc **Well-Architected**.

## 1. Vì sao cần xử lý nền?

Một API tạo đơn hàng có thể cần gửi email, cập nhật kho, tạo hóa đơn PDF và gửi dữ liệu sang nền tảng phân tích sau khi ghi nhận đơn. Nếu thực hiện tất cả trước khi trả HTTP response, thời gian phản hồi phụ thuộc từng hệ thống ngoài. Email provider chậm có thể khiến request timeout dù đơn hàng đã lưu thành công.

Một kiến trúc phù hợp tách **đường đi đồng bộ quan trọng** (xác thực, kiểm tra tồn kho/giá, ghi nhận đơn và xác nhận kết quả) khỏi **công việc có thể hoàn tất sau** (gửi thông báo, tạo báo cáo, đồng bộ phân tích).

~~~mermaid
flowchart LR
    U["Client"] --> API["Order API"]
    API --> DB[("Order database")]
    DB --> OUTBOX["Outbox / event record"]
    OUTBOX --> Q[("Message queue")]
    Q --> W["Background workers"]
    W --> EMAIL["Email provider"]
    W --> ERP["ERP / Inventory"]
    W --> REPORT["Report storage"]
~~~

Cách phát event có thể dùng transactional outbox, CDC, managed event bus hoặc cơ chế khác. Điểm cốt lõi là trạng thái nghiệp vụ được lưu đáng tin cậy trước khi request được coi là đã tiếp nhận; phần việc tiếp theo phải có cơ chế xử lý và đối soát.

### 1.1. Khi nào không nên đưa việc sang nền?

Không phải thao tác nào cũng có thể trả lời “đã xong” trước khi công việc cốt lõi hoàn tất. Khi đặt chỗ cuối cùng còn lại, API cần đảm bảo đã giữ được chỗ theo quy tắc đồng thời. Nếu chỉ đưa lệnh giữ chỗ vào queue rồi trả về thành công mà chưa có kết quả xác nhận, người dùng có thể nhận cam kết sai.

Phân biệt ba trạng thái:

- **Đã tiếp nhận:** công việc được lưu để xử lý sau và có mã theo dõi; chưa có nghĩa nghiệp vụ hoàn tất.
- **Đã xử lý:** worker hoàn thành tác vụ theo tiêu chí.
- **Đã xác nhận nghiệp vụ:** hệ thống đạt điều kiện mà người dùng hoặc hợp đồng coi là thành công.

API có thể trả HTTP 202 Accepted cùng jobId cho công việc dài chưa hoàn tất. Với giao dịch cần xác nhận ngay, phải hoàn tất phần bất biến cốt lõi trước khi trả trạng thái thành công.

## 2. Phân biệt background, scheduled và batch

| Loại | Cách kích hoạt | Đặc điểm | Ví dụ |
| --- | --- | --- | --- |
| Background / event-driven | Event, message hoặc yêu cầu được ghi nhận | Xử lý bất đồng bộ, thường từng công việc | Gửi email khi đơn được tạo |
| Scheduled job | Theo thời điểm/lịch | Một lần hoặc lặp lại | Chốt báo cáo lúc 02:00 |
| Batch job | Theo lịch, yêu cầu người vận hành hoặc sự kiện | Xử lý tập dữ liệu lớn, chia chunk/checkpoint | Đối soát 5 triệu giao dịch |
| Stream processing | Event liên tục đến | Tính toán theo event-time/window hoặc state | Tổng hợp lượt click theo phút |

Một scheduled job hằng đêm có thể tạo batch run; batch run chia file thành nhiều chunk rồi đưa từng chunk vào queue. Batch không nhất thiết chạy trong một tiến trình duy nhất, và scheduled job cũng không nhất thiết là batch. Hãy phân loại theo cách kích hoạt, khối lượng dữ liệu, độ trễ và cách quản lý trạng thái.

## 3. Các thành phần trong kiến trúc xử lý nền

### 3.1. Producer, queue và consumer

- **Producer:** thành phần tạo công việc hoặc message.
- **Queue/broker:** lưu message và phân phối đến consumer.
- **Consumer/worker:** nhận và xử lý công việc.
- **Retry policy:** quy định thử lại khi lỗi tạm thời.
- **Dead-letter queue (DLQ):** giữ message vượt giới hạn xử lý hoặc không thể tiếp tục theo policy.
- **Job store/status store:** lưu trạng thái nghiệp vụ, tiến độ và kết quả dài hạn.

~~~mermaid
flowchart LR
    P["Producer"] --> Q[("Queue")]
    Q --> W1["Worker 1"]
    Q --> W2["Worker 2"]
    W1 --> S[("Job status / DB")]
    W2 --> S
    W1 -->|Lỗi vượt policy| DLQ[("DLQ")]
    W2 -->|Retry có giới hạn| Q
    DLQ --> OPS["Điều tra / Replay có kiểm soát"]
~~~

Queue tách tốc độ producer và consumer, hấp thụ burst trong giới hạn retention/dung lượng. Nhưng queue **không tự đảm bảo công việc hoàn tất đúng một lần** và không thay thế trạng thái nghiệp vụ. Message có thể được giao lại sau timeout, worker crash hoặc khi acknowledgement không đến broker.

### 3.2. Scheduler và job runner

Scheduler xác định **khi nào** công việc được kích hoạt. Nó có thể nằm trong nền tảng orchestration, managed scheduler, cron service hoặc ứng dụng riêng. Trách nhiệm gồm tính lần chạy tiếp theo, trigger job/event, kiểm soát lịch trùng, ghi nhận lần chạy và xử lý timezone, ngày lễ, DST cùng lịch nghiệp vụ.

Scheduler thường chỉ **khởi chạy job**; job runner mới đọc dữ liệu, chia chunk, xử lý, ghi kết quả và checkpoint.

Một batch runner có thể có job instance (một lần chạy logic với tập tham số), job execution (lần thực thi cụ thể), step (giai đoạn), chunk (nhóm bản ghi được commit) và checkpoint (vị trí đã xử lý thành công). Metadata cần ghi số bản ghi đọc, ghi, bỏ qua, lỗi và thời gian.

## 4. Chọn cơ chế phân phối công việc

### 4.1. Gọi đồng bộ hay queue + worker?

| Tiêu chí | Gọi đồng bộ | Queue + worker |
| --- | --- | --- |
| Phản hồi | Có kết quả ngay hoặc timeout | Thường trả xác nhận đã tiếp nhận |
| Phụ thuộc | Caller phụ thuộc availability/latency downstream | Producer và consumer tách thời gian tương đối |
| Burst traffic | Gây áp lực trực tiếp lên downstream | Hấp thụ burst trong giới hạn dung lượng |
| Retry | Caller tự kiểm soát | Worker/broker hỗ trợ mô hình retry |
| Quan sát | Request trace trên call path | Cần correlation ID, job status, queue age |
| Nhất quán | Có thể dùng transaction cùng ranh giới dữ liệu | Thường cần eventual consistency và đối soát |
| Dùng khi | Cần kết quả tức thời | Tác vụ có thể hoàn tất sau request |

Không đưa một bước bắt buộc xác nhận giao dịch sang queue rồi giả vờ đã hoàn tất. Ngược lại, gửi email hoặc tạo báo cáo thường không cần chặn request chính.

### 4.2. Queue, event bus và workflow

- **Work queue:** nhiều worker chia nhau xử lý mỗi tác vụ.
- **Pub/sub hoặc event bus:** nhiều subscriber phản ứng độc lập với cùng một sự kiện.
- **Workflow orchestration:** quản lý quy trình nhiều bước, nhánh, timeout, chờ callback hoặc bù trừ.
- **Stream processing:** xử lý dữ liệu liên tục, event-time/window và state.

Một broker có thể hỗ trợ nhiều kiểu, nhưng semantics khác nhau. So sánh retention, ordering, throughput, kích thước message, delivery guarantee, retry/DLQ, tích hợp, chi phí và năng lực vận hành.

### 4.3. Message nên gọn

Message nên chứa ID và thông tin định tuyến; dữ liệu lớn đặt trong object storage/database.

~~~json
{
  "eventId": "evt-2026-000184",
  "eventType": "report.export.requested",
  "jobId": "job-2026-0418",
  "tenantId": "tenant-42",
  "objectKey": "exports/source/2026-04-18.csv",
  "correlationId": "corr-9af2"
}
~~~

Ví dụ chỉ để minh họa. Worker phải xác minh quyền và tính hợp lệ của object/job. Không đặt token, mật khẩu, PII không cần thiết hoặc nội dung bí mật trong message.

## 5. Vòng đời công việc và trạng thái

Một job dài cần trạng thái minh bạch thay vì chỉ ghi log “started” và “finished”.

~~~mermaid
stateDiagram-v2
    [*] --> Accepted
    Accepted --> Queued
    Queued --> Running
    Running --> Succeeded
    Running --> RetryScheduled
    RetryScheduled --> Running
    Running --> Failed
    Running --> CancelRequested
    CancelRequested --> Cancelled
    Running --> PartiallySucceeded
~~~

Có thể dùng các trạng thái PENDING, QUEUED, RUNNING, RETRYING, SUCCEEDED, FAILED, CANCEL_REQUESTED, CANCELLED hoặc PARTIALLY_SUCCEEDED.

Cần xác định transition hợp lệ, ai được quyền cancel/retry/replay, job đang chạy xử lý ra sao khi deploy, timeout có thể xảy ra sau khi side effect thành công hay không, và kết quả được lưu bao lâu.

Với job lớn nên lưu jobId, tenantId, loại job, tham số đã chuẩn hóa, thời điểm tạo, attempt, progress, số bản ghi thành công/thất bại và thông tin kết thúc. Không lưu toàn bộ payload nhạy cảm vào bảng trạng thái nếu chỉ cần tham chiếu đến kho dữ liệu được bảo vệ.

## 6. Idempotency: an toàn khi xử lý lại

### 6.1. Duplicate xảy ra như thế nào?

Worker nhận message, gửi hóa đơn thành công rồi crash trước khi acknowledge. Broker giao lại message; worker mới có thể gửi hóa đơn lần thứ hai. Nhiều queue cung cấp delivery at-least-once hoặc có thể giao lại; cần đọc semantics của dịch vụ thực tế.

Không hứa exactly-once cho toàn bộ nghiệp vụ chỉ vì broker có chế độ delivery đặc biệt. Client retry, replay và timeout ở hệ thống ngoài vẫn có thể tạo side effect trùng.

### 6.2. Idempotent consumer

Một thao tác idempotent cho cùng khóa nghiệp vụ nhiều lần vẫn đưa trạng thái cuối về kết quả như chạy một lần.

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    message_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Trong transaction consumer:

1. Ghi consumer_name + message_id với unique constraint.
2. Nếu khóa tồn tại, coi message đã xử lý và bỏ qua tác dụng phụ lặp.
3. Nếu ghi thành công, cập nhật trạng thái nghiệp vụ hoặc tạo kết quả.
4. Commit database trước khi acknowledge theo flow broker.

Mẫu này chỉ bảo vệ side effect trong cùng transaction DB. Với thanh toán/email ngoài, cần idempotency key mà downstream hỗ trợ, bảng trạng thái gửi, outbox hoặc quy trình đối soát. Nếu hệ thống ngoài không hỗ trợ idempotency, không thể bảo đảm không có side effect trùng chỉ bằng bảng nội bộ.

### 6.3. Phân biệt các loại khóa

- **messageId:** định danh message cụ thể.
- **jobId:** định danh lần chạy công việc.
- **businessKey:** định danh tác vụ nghiệp vụ cần duy nhất, ví dụ invoice cho một order.
- **idempotencyKey:** nhận diện retry của một yêu cầu/tác vụ.

Một sự kiện có thể được phát thành nhiều message nhưng cùng mục tiêu phát hành hóa đơn cho một đơn hàng. Deduplicate bằng messageId chưa chắc chặn được duplicate nghiệp vụ; phải chọn khóa theo tác dụng phụ cần bảo vệ.

## 7. Retry, timeout, backoff và DLQ

### 7.1. Phân loại lỗi trước retry

| Loại lỗi | Ví dụ | Hành vi nên cân nhắc |
| --- | --- | --- |
| Tạm thời | Timeout mạng, HTTP 503, rate limit tạm thời | Retry với backoff, jitter và giới hạn |
| Vĩnh viễn/dữ liệu sai | Schema sai, thiếu trường, tenant không tồn tại | Failed hoặc DLQ để điều tra |
| Lỗi nghiệp vụ | Đơn đã hủy, hóa đơn đã phát hành | Không retry; trả kết quả hoặc deduplicate |
| Hết quyền | Credential hết hạn/bị revoke | Cảnh báo và khắc phục quyền, tránh retry dồn |
| Quá tải | DB pool hết, downstream throttle | Giảm concurrency, giãn retry, backpressure |

Retry vô hạn mọi lỗi tạo retry storm, backlog, phí và quá tải cho dependency đang gặp sự cố.

### 7.2. Exponential backoff và jitter

~~~text
delay(n) = min(maxDelay, baseDelay × 2^n) + randomJitter
~~~

Ví dụ baseDelay 1 giây, maxDelay 60 giây, jitter ngẫu nhiên từ 0 đến 1 giây. Giá trị phải phù hợp SLA, retention queue và thời gian phục hồi downstream. Jitter giảm nguy cơ nhiều worker retry cùng lúc.

Cần giới hạn attempts và tổng thời gian retry; sau đó chuyển DLQ hoặc trạng thái failed để người vận hành xử lý.

### 7.3. Dead-letter queue

DLQ giữ message vượt số lần thử hoặc không thể xử lý. Quy trình vận hành cần alarm khi số message/tuổi message tăng; hiển thị reason, attempt, jobId, correlationId và phiên bản consumer; che dữ liệu nhạy cảm; sửa dữ liệu/cấu hình rồi replay có kiểm soát; audit người replay và kết quả.

DLQ không phải thùng rác vô thời hạn: cần retention, phân loại dữ liệu, quyền truy cập và thời hạn điều tra.

## 8. Scheduler và tác vụ định kỳ

### 8.1. Lịch không đồng nghĩa chạy đúng một lần

Nếu có ba replica Spring Boot và mỗi replica đều bật @Scheduled cho 02:00, cả ba có thể cùng chạy job. Scale ứng dụng có thể tạo job trùng.

Các hướng xử lý: scheduler chạy riêng; distributed lock có lease và fencing phù hợp; managed scheduler trigger target; unique execution key trong DB theo jobType + businessDate + tenant; hoặc job orchestration service.

Distributed lock không phải giải pháp tuyệt đối. Worker cũ có thể tiếp tục sau khi lease hết hạn; worker mới giành lock và chạy song song. Với ghi dữ liệu quan trọng, cần fencing token, optimistic version hoặc idempotency ở transaction ghi.

### 8.2. Cron, timezone và lịch nghiệp vụ

Ví dụ cron chỉ minh họa; cú pháp thay đổi giữa Unix cron, Spring, Quartz và dịch vụ cloud:

~~~text
0 0 2 * * *    # 02:00 mỗi ngày, tùy cú pháp scheduler
0 */15 * * * * # mỗi 15 phút, tùy cú pháp scheduler
~~~

Xác định thời gian theo UTC hay timezone nghiệp vụ như Asia/Ho_Chi_Minh; quy tắc DST ở vùng có áp dụng; ngày lễ/cuối tuần; missed run có catch-up không; job overlap ra sao; và thời gian chạy dựa vào event-time hay trigger-time.

Với báo cáo “ngày hôm qua”, phải chốt ranh giới ngày theo timezone kinh doanh rồi chuyển thành thời điểm tuyệt đối nhất quán. Không dựa vào local time của từng worker nếu cấu hình có thể khác nhau.

### 8.3. Catch-up và chống bỏ lỡ kỳ chạy

Nếu scheduler dừng từ 01:50 đến 02:20, kỳ 02:00 có thể cần chạy bù. Một bảng lịch chạy kỳ vọng giúp reconciler phát hiện kỳ chưa có execution.

~~~sql
CREATE TABLE scheduled_job_runs (
    job_type VARCHAR(100) NOT NULL,
    business_date DATE NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (job_type, business_date, tenant_id)
);
~~~

Khi trigger lặp, unique constraint giúp nhận diện kỳ đã tồn tại. Cần quy định kỳ nào được chạy bù, kỳ nào đã hết ý nghĩa nghiệp vụ và ai có quyền kích hoạt thủ công.

## 9. Batch processing cho dữ liệu lớn

### 9.1. Chia dữ liệu thành chunk

Đọc toàn bộ hàng triệu bản ghi vào một danh sách có thể gây áp lực heap, GC và hết bộ nhớ. Batch job thường chia dữ liệu thành chunk, xử lý và ghi theo từng nhóm.

~~~mermaid
flowchart LR
    SOURCE[("Source")] --> READER["Reader / Paging"]
    READER --> CHUNK["Chunk buffer"]
    CHUNK --> PROCESSOR["Validate / Transform"]
    PROCESSOR --> WRITER["Writer"]
    WRITER --> TARGET[("Target")]
    WRITER --> CHECK["Checkpoint"]
    CHECK -. resume .-> READER
~~~

Ví dụ chunk 500 bản ghi chỉ là điểm xuất phát; cần benchmark. Chunk quá nhỏ tăng overhead commit/network; quá lớn tăng bộ nhớ, thời gian lock và chi phí chạy lại khi lỗi.

### 9.2. Offset, keyset và cursor

- **Offset paging:** LIMIT 500 OFFSET 1000000; dễ hiểu nhưng offset lớn có thể khiến DB đọc và bỏ qua nhiều bản ghi. Dữ liệu thay đổi khi batch chạy có thể làm tập kết quả không ổn định.
- **Keyset paging:** lấy bản ghi có khóa lớn hơn khóa cuối đã đọc, ví dụ WHERE id > lastId ORDER BY id LIMIT 500; phù hợp khi khóa ổn định và có index.
- **Cursor/streaming:** giữ con trỏ đọc; cần xem thời gian giữ transaction/connection và giới hạn database/driver.

~~~sql
SELECT id, status, amount
FROM transactions
WHERE id > :last_seen_id
  AND created_at < :cutoff
ORDER BY id
LIMIT 500;
~~~

Cần chọn tập đầu vào ổn định bằng cutoff, snapshot, watermark hoặc danh sách ID. Nếu dữ liệu có thể đến muộn, chỉ query theo điều kiện thời gian có thể bỏ sót hoặc xử lý trùng.

### 9.3. Checkpoint và resume

Checkpoint nên lưu jobRunId, tham số/snapshot/cutoff, partition/chunk hoàn thành, khóa cuối đã commit hoặc watermark, số record đọc/ghi/skip/fail, thời điểm và version.

Chỉ cập nhật checkpoint **sau khi** kết quả chunk commit thành công. Nếu checkpoint trước writer, crash có thể làm mất dữ liệu. Nếu writer commit nhưng checkpoint chưa cập nhật, chunk có thể chạy lại; writer phải idempotent hoặc upsert theo business key.

### 9.4. Partitioning và parallelism

~~~mermaid
flowchart TB
    JOB["Batch run"] --> P1["Partition 1"]
    JOB --> P2["Partition 2"]
    JOB --> P3["Partition 3"]
    P1 --> W1["Worker A"]
    P2 --> W2["Worker B"]
    P3 --> W3["Worker C"]
    W1 --> R[("Result / checkpoint")]
    W2 --> R
    W3 --> R
~~~

Mỗi bản ghi phải thuộc đúng một partition; không overlap hoặc bỏ trống; key phân bố đều; cùng aggregate không bị ghi đồng thời nếu nghiệp vụ yêu cầu thứ tự; tổng concurrency không vượt năng lực DB/API; partition lỗi có thể chạy lại độc lập.

Parallelism cao không phải lúc nào cũng nhanh hơn. Nếu nhiều worker cập nhật bảng nóng hoặc gọi ERP giới hạn 100 req/s, tăng worker chỉ làm lock contention, throttle và retry tăng.

## 10. Chọn compute cho worker

| Mô hình | Phù hợp khi | Giới hạn và vận hành |
| --- | --- | --- |
| Worker chạy lâu dài | Throughput đều, consumer loop liên tục, cần kiểm soát concurrency | Graceful shutdown, memory leak, deploy không làm mất job |
| Function/serverless | Lưu lượng không đều, job ngắn, scale theo event | Timeout, cold start, quota, concurrency, payload và chi phí invocation |
| Container job | Job dài hơn function, cần runtime/thư viện/tài nguyên xác định | Scheduler/orchestrator, retry, deadline, resource request/limit |
| Managed batch service | Tập dữ liệu lớn, job nhiều bước hoặc tài nguyên chuyên biệt | Metadata, quota, chi phí nền tảng và năng lực vận hành |

Một function timeout không chứng minh side effect chưa xảy ra; message có thể được giao lại. Local filesystem của function/container thường không nên được coi là nơi lưu trạng thái bền vững.

Nếu API và scheduler chạy chung process, nhân bản API có thể nhân bản scheduler. Có thể tách worker deployment dù vẫn dùng chung codebase để kiểm soát lifecycle và scale riêng.

### 10.1. Graceful shutdown và deploy

Khi deploy mới, worker cần ngừng nhận công việc mới, hoàn thành hoặc nhả công việc đang giữ theo policy, persist checkpoint/trạng thái và đóng kết nối. Visibility timeout/lease phải đủ dài hoặc được gia hạn đúng cách. Cần kiểm thử SIGTERM, process kill, node restart và rollout đồng thời.

Nếu job chạy nhiều giờ, lưu execution state ngoài RAM và thiết kế resume. Không dựa vào việc một pod hoặc VM tồn tại liên tục cho đến khi job xong.

## 11. Autoscaling, backlog và backpressure

Autoscaling worker không nên chỉ nhìn CPU. Các chỉ số hữu ích gồm queue depth, oldest message age, arrival rate, completion rate, processing latency, retry/DLQ rate và downstream saturation như connection pool, API quota, DB throughput.

### 11.1. Ước lượng số worker

Giả sử 12.000 công việc đang chờ; mỗi worker xử lý trung bình 4 công việc/giây; muốn hoàn thành trong 100 giây, không tính thêm công việc mới và overhead:

~~~text
worker_count = backlog / (throughput_per_worker × target_seconds)
             = 12.000 / (4 × 100)
             = 30 workers
~~~

Đây là mức lý thuyết. Nếu downstream chỉ cho phép 60 request/giây, 30 worker × 4 req/s tạo 120 req/s và quá tải. Cần concurrency cap, rate limit và tính theo **nút thắt nhỏ nhất** toàn tuyến.

### 11.2. Backpressure

Queue hấp thụ burst trong giới hạn, không tạo năng lực vô hạn. Có thể giảm tốc producer, giới hạn worker concurrency, giữ quota downstream, ưu tiên job quan trọng, trì hoãn batch ít ưu tiên hoặc từ chối yêu cầu mới khi capacity không đủ.

Phải đặt ngưỡng backlog/retention và cảnh báo trước khi queue age vượt SLO. Nếu message tích lũy lâu hơn retention, dữ liệu có thể hết hạn trước khi xử lý.

## 12. Workflow nhiều bước

Quy trình đối soát có thể gồm thu thập giao dịch, đọc dữ liệu cổng thanh toán, đối chiếu, phân loại sai lệch, tạo báo cáo và chờ phê duyệt. Khi quy trình có bước chờ nhiều giờ/ngày, nhánh điều kiện, timeout và bù trừ, workflow orchestrator/state machine có thể dễ quản lý hơn một hàm lớn.

| Mô hình | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| Một worker tự điều phối | Vài bước đơn giản, thời gian ngắn | State/retry khó phục hồi nếu code phình to |
| Queue chain | Các bước độc lập và event-driven | Theo dõi dependency, ordering, lỗi giữa chuỗi |
| Workflow orchestration | Nhiều bước, chờ lâu, nhánh, timeout, compensation | Chi phí dịch vụ, learning curve, versioning |
| Batch framework | Đọc/ghi khối lượng lớn, step/chunk/checkpoint | Metadata execution và job store |

Chọn công cụ vừa mức phức tạp; không cần workflow engine chỉ để gửi một email sau đơn hàng.

## 13. Bảo mật xử lý nền

Worker thường hoạt động không có người dùng hiện diện, vì vậy service account có thể bị cấp quyền quá rộng.

1. **Least privilege:** mỗi loại worker chỉ có quyền tới queue, bảng, bucket và API cần thiết.
2. **Tách danh tính:** notification worker không cần quyền ghi payment ledger; report worker không cần sửa user profile.
3. **Quản lý secret:** lấy credential từ secret manager, có rotation và thu hồi; không nhúng vào message hoặc image.
4. **Tenant isolation:** giữ tenant context, kiểm tra nguồn và quyền; không tin mù quáng tenantId trong payload.
5. **Bảo vệ dữ liệu:** mã hóa message/storage, hạn chế PII trong log, kiểm soát DLQ và export.
6. **Audit:** ghi ai yêu cầu, ai replay/cancel, service identity nào thực thi và dữ liệu nào thay đổi.
7. **Network controls:** chỉ mở egress/ingress cần thiết.

Batch thao tác dữ liệu lớn nên có dry-run hoặc bước xác nhận trước hành động không thể hoàn tác. Giới hạn số bản ghi, tenant scope và khoảng ngày giúp giảm hậu quả khi tham số sai.

## 14. Observability: đo công việc thực sự

Request API thành công chỉ chứng minh việc tiếp nhận, không chứng minh job đã xong.

**API tiếp nhận:** tỷ lệ request hợp lệ tạo job, độ trễ enqueue/job store, lỗi validation/authorization/capacity.

**Pipeline xử lý:** queue depth, oldest age, job end-to-end duration, success/failure rate, attempts, retry và DLQ, batch records read/written/skipped/failed, checkpoint age, worker saturation, downstream latency và chi phí.

### 14.1. Correlation và audit trail

Mỗi công việc dài cần jobId; message có eventId/messageId; trace có correlationId. Nếu job phát message con, giữ quan hệ cha/con để truy vết.

Log phải trả lời: ai yêu cầu, cho tenant nào, input/version nào, attempt thứ mấy, worker/version nào thực thi, bao nhiêu bản ghi đọc/ghi/bỏ qua, lý do thất bại và ai đã replay. Không ghi toàn bộ dữ liệu nhạy cảm; dùng ID tham chiếu, retention và quyền truy cập phù hợp.

### 14.2. Cảnh báo theo tác động

- Oldest message age của queue thanh toán vượt ngưỡng.
- Batch đối soát chưa hoàn thành trước giờ chốt sổ.
- DLQ tăng bất thường.
- Job ở trạng thái RUNNING lâu hơn timeout dự kiến.
- Không có lần chạy báo cáo đúng kỳ.
- Worker bị throttle liên tục hoặc downstream vượt quota.

Một job im lặng không có nghĩa thành công. Với tác vụ định kỳ quan trọng, dùng **expected-run monitor/heartbeat** để cảnh báo khi không thấy lần chạy đúng hạn.

## 15. Kịch bản chất lượng và SLO minh họa

Các ngưỡng là ví dụ học tập, cần được nghiệp vụ xác nhận.

| Mã | Tác động / môi trường | Phản hồi kỳ vọng | Thước đo |
| --- | --- | --- | --- |
| QA-BG-01 | Đơn hàng được xác nhận | Job thông báo được tạo và xử lý bất đồng bộ | 99% job hợp lệ bắt đầu trong 60 giây; không chặn phản hồi tạo đơn |
| QA-SCH-01 | Đến 02:00 theo timezone nghiệp vụ | Báo cáo ngày trước tạo đúng kỳ, không chạy trùng | Job được tạo trong cửa sổ 5 phút; một business key có một kết quả hiệu lực |
| QA-BAT-01 | 5 triệu giao dịch cần đối soát | Chia partition/chunk, có checkpoint và resume | Hoàn thành trong 90 phút; số đọc/ghi/bỏ qua được đối soát |
| QA-REL-01 | Worker chết sau side effect nhưng trước ACK | Message giao lại không tạo side effect trùng | Không phát hành trùng hóa đơn trong bộ test retry |
| QA-COST-01 | Queue tăng gấp 5 lần | Autoscale trong giới hạn downstream | Oldest message age về dưới ngưỡng; chi phí/job trong budget |
| QA-SEC-01 | Staging hoặc tenant A yêu cầu đọc dữ liệu tenant B | Từ chối và ghi audit | 100% ca trái phép trong bộ test bị chặn, không lộ dữ liệu |

Cần định nghĩa điểm đo bắt đầu/kết thúc, tập job hợp lệ, cửa sổ quan sát và cách loại trừ. “Job bắt đầu trong 60 giây” khác “job hoàn thành trong 60 giây”. Batch cần đo tới lúc kết quả nghiệp vụ hợp lệ được ghi nhận.

## 16. TCO và ví dụ chi phí

Giả sử hệ thống có 100.000 công việc thông báo mỗi ngày. Hai lựa chọn: worker container chạy thường trực hoặc function/event-driven chỉ chạy khi có message. TCO cần gồm compute/memory/duration, queue, logging, network, retry, min capacity, cold start và nỗ lực vận hành.

Ví dụ giả định, đơn vị triệu VND/tháng:

| Hạng mục | A: Worker container | B: Event-driven function |
| --- | ---: | ---: |
| Compute/runtime | 18 | 12 |
| Queue/broker | 5 | 5 |
| Network và egress | 3 | 4 |
| Logs/metrics/tracing | 4 | 5 |
| Vận hành phân bổ | 10 | 7 |
| Retry/DLQ và lưu trạng thái | 2 | 2 |
| **Tổng** | **42** | **35** |

Đây là số liệu minh họa, không phải báo giá. Quyết định thật phải dựa trên volume, thời gian trung bình/tail, memory, concurrency, quota và giá hiện hành.

~~~text
Cost per successful job
    = Total processing cost in period
      / Number of successful business jobs

Cost per million records
    = Total batch compute + storage + network cost
      / (Successfully processed records / 1,000,000)
~~~

Tính cả retry, job thất bại, thao tác thủ công và chi phí backlog; không chỉ tính lần chạy cuối cùng thành công.

## 17. Case study: báo cáo doanh thu và thông báo đơn hàng

Một nền tảng đặt phòng dùng Spring Boot và PostgreSQL. Khi booking được xác nhận, hệ thống gửi email; mỗi ngày 02:00 giờ Việt Nam tạo báo cáo; cuối tháng đối soát nhiều triệu bản ghi.

Yêu cầu giả định: email được thử gửi trong 2 phút; báo cáo hoàn thành trước 03:00; batch tháng trong 90 phút; không gửi thông báo/hóa đơn trùng; lỗi dữ liệu được đối soát.

### 17.1. Ba luồng công việc

**A. Email theo sự kiện:** Sau transaction booking commit, event BookingConfirmed được xuất an toàn (ví dụ qua outbox). Consumer đọc queue và gửi email với khóa idempotency theo booking + loại template. Lỗi tạm thời retry; dữ liệu sai có thể đưa DLQ.

**B. Báo cáo theo lịch:** Scheduler tạo jobRunId cho kỳ businessDate. Unique key ngăn kỳ chạy trùng. Batch đọc snapshot/watermark ngày trước, tổng hợp, ghi object storage, lưu trạng thái và phát thông báo. Reconciler phát hiện missed run và tạo catch-up execution.

**C. Đối soát theo lô:** Job đọc tập bản ghi đã chốt, chia partition theo khoảng ID, xử lý chunk, commit kết quả và checkpoint. Partition lỗi chạy lại độc lập; kết quả dùng business key/upsert để tránh duplicate.

~~~mermaid
flowchart TB
  DB[("Booking DB")] --> OUTBOX["Transactional outbox"]
  OUTBOX --> Q[("Notification queue")]
  Q --> EMAIL["Email worker"]
  SCHED["Daily scheduler"] --> DAILY["Daily report job"]
  DB --> DAILY
  SCHED2["Month-end scheduler"] --> BATCH["Reconciliation batch"]
  DB --> BATCH
  BATCH --> CHUNKS["Partition / chunk workers"]
  CHUNKS --> RESULT[("Reconciliation results")]
  DAILY --> STORE[("Object storage")]
~~~

### 17.2. Vận hành và khôi phục

- Dashboard theo dõi queue age, email attempt, DLQ, báo cáo đúng hạn, chunk/partition và job duration.
- Nếu email provider lỗi 15 phút, API booking vẫn hoạt động; worker giữ message và retry.
- Nếu batch fail ở partition 8/20, tiếp tục từ checkpoint đã commit và chạy lại partition lỗi.
- Nếu scheduler dừng, expected-run monitor báo thiếu job; operator chạy catch-up có idempotency.
- Nếu dữ liệu nguồn thay đổi sau khi batch chốt, cần snapshot/reconciliation hoặc phiên bản báo cáo mới, không âm thầm ghi đè kết quả.

## 18. Quy trình thiết kế và triển khai

1. **Phân loại công việc:** event-driven, scheduled, batch hay stream; tách phần cần phản hồi đồng bộ.
2. **Định nghĩa kết quả:** accepted, running, succeeded, failed hay partially succeeded; API trả gì và client theo dõi thế nào.
3. **Chọn cơ chế:** queue, event bus, workflow engine, scheduler hoặc batch framework theo semantics.
4. **Định danh và idempotency:** job ID, event ID, business key, tenant key và deduplication.
5. **Failure handling:** timeout, retry, backoff, DLQ, cancel, replay và đối soát.
6. **Chọn compute:** worker service, container job, function/serverless hoặc managed batch.
7. **Capacity:** arrival/service rate, retention, downstream limit, backpressure và autoscaling.
8. **Lịch/batch:** timezone, missed run, overlap, chunk, partition và checkpoint.
9. **Bảo mật:** service identity, least privilege, tenant isolation, secret, encryption và audit.
10. **Kiểm thử:** duplicate delivery, crash, timeout, mất scheduler, DLQ, replay và tải lớn.
11. **Bàn giao vận hành:** runbook, dashboard, alert, owner, budget và diễn tập.

### 18.1. Mẫu định nghĩa job

~~~yaml
job_type: monthly_reconciliation
owner: finance-platform
trigger:
  type: schedule
  expression: "0 0 2 1 *"
  timezone: "Asia/Ho_Chi_Minh"
input:
  business_period: previous_month
  source_snapshot_required: true
execution:
  mode: batch
  chunk_size: 1000
  max_concurrency: 8
  checkpoint_enabled: true
reliability:
  idempotency_key: "job_type+business_period+tenant_id"
  max_attempts: 5
  backoff: exponential_with_jitter
  dead_letter_enabled: true
limits:
  timeout_minutes: 90
  downstream_requests_per_second: 50
observability:
  publish_progress: true
  alert_on_late_start: true
  alert_on_dead_letter: true
status: proposed
~~~

Đây là metadata minh họa, không phải schema cho scheduler cụ thể. Cần định nghĩa timezone, kỳ nghiệp vụ và missed run phù hợp.

## 19. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Trả “đã hoàn tất” khi mới enqueue | Cam kết sai với người dùng | Phân biệt accepted và completed |
| Coi queue bảo đảm exactly-once | Duplicate side effect khi crash/retry | Idempotency theo business key |
| Retry vô hạn | Retry storm, backlog và chi phí | Phân loại lỗi, backoff, giới hạn attempt, DLQ |
| Mỗi replica chạy cron độc lập | Job định kỳ chạy trùng | Scheduler riêng, unique run key hoặc lock |
| Chỉ lưu tiến độ trong RAM | Restart mất checkpoint | Persist state/checkpoint |
| Batch đọc tất cả vào memory | OOM và GC | Chunk/keyset/cursor |
| Scale worker không giới hạn | Downstream quá tải | Concurrency cap và backpressure |
| Replay DLQ toàn bộ ngay | Spike và side effect lặp | Replay theo nhóm, audit và throttle |
| Không lưu timezone | Chốt sai ngày, bỏ lỡ kỳ | Ghi timezone và business date |
| Không kiểm tra missed schedule | Báo cáo thiếu âm thầm | Expected-run monitor và catch-up |
| Không kiểm soát tenant ở worker | Rò rỉ dữ liệu | Authorization và kiểm tra scope |

## 20. Bài tập thực hành

Một hệ thống thương mại điện tử Java/Spring Boot cần gửi email, cập nhật kho và tạo dữ liệu phân tích sau khi thanh toán; mỗi ngày 01:30 tổng hợp doanh thu; cuối tháng đối soát 8 triệu giao dịch. Đội vận hành có 6 người. Email được thử gửi trong 2 phút, báo cáo ngày hoàn thành trước 02:30, batch tháng trong 90 phút và không xử lý trùng.

1. Phân loại các luồng thành synchronous/background/scheduled/batch/stream.
2. Vẽ kiến trúc API, transaction DB, outbox/queue, worker, scheduler, batch partition và kho báo cáo.
3. Thiết kế trạng thái job và API trả 202 Accepted/endpoint theo dõi.
4. Chọn messageId và businessKey cho phát hành hóa đơn; chống duplicate khi crash trước ACK.
5. Đề xuất retry/backoff/DLQ cho timeout, schema sai, rate limit và credential hết hạn.
6. Tính worker lý thuyết nếu backlog 240.000 bản ghi, mỗi worker 20 bản ghi/giây, cần hoàn thành 10 phút; sau đó xét database giới hạn 300 record/giây.
7. Thiết kế chunk/partition/checkpoint và resume mà không ghi kết quả trùng.
8. Lên lịch 01:30 theo Asia/Ho_Chi_Minh; chống overlap và catch-up sau scheduler downtime.
9. Xây dashboard và ít nhất bốn cảnh báo cho queue age, DLQ, job duration, batch progress và missed schedule.
10. Lập TCO giả định cho worker container và serverless.

**Gợi ý tự đánh giá:** Bài làm đạt khi mô tả trạng thái nghiệp vụ, delivery semantics, chống trùng, phục hồi, giới hạn tài nguyên và bằng chứng hoàn thành; chỉ nêu tên công nghệ là chưa đủ.

## 21. Checklist trước production

- [ ] Tách phần cần phản hồi ngay khỏi công việc có thể xử lý sau.
- [ ] API phân biệt tiếp nhận và hoàn thành nghiệp vụ.
- [ ] Mỗi job/message có định danh, business key và tenant scope.
- [ ] Consumer an toàn khi nhận message lặp; side effect ngoài có idempotency/đối soát.
- [ ] Retry có timeout, backoff/jitter, giới hạn attempt và DLQ.
- [ ] Có dashboard/runbook cho DLQ, retry, replay, cancel và job stuck.
- [ ] Scheduled job có timezone, unique execution key, overlap policy và catch-up.
- [ ] Batch có chunk/partition/checkpoint; checkpoint chỉ tiến sau commit.
- [ ] Concurrency/autoscaling không vượt capacity của database/API phụ thuộc.
- [ ] Có backpressure và giới hạn backlog/retention.
- [ ] Worker dùng least privilege, quản lý secret, tenant isolation và audit.
- [ ] Có job status, correlation ID, logs/metrics/traces và expected-run monitor.
- [ ] Đã thử crash, timeout, restart, duplicate delivery, missed schedule và replay.
- [ ] TCO tính retry, storage, network, quan sát và nhân lực.

## 22. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi thiết kế xử lý nền |
| --- | --- |
| **Operational Excellence** | Job có owner, runbook, dashboard, replay/cancel và expected-run alert không? |
| **Security** | Worker có quyền tối thiểu, tenant isolation, secret management và audit không? |
| **Reliability** | Retry, idempotency, checkpoint, DLQ, catch-up và phục hồi đã được thử chưa? |
| **Performance Efficiency** | Chunk, partition, concurrency và autoscaling phù hợp tải thực và downstream không? |
| **Cost Optimization** | Compute luôn bật hay event-driven phù hợp hơn; chi phí/job và mỗi triệu bản ghi là bao nhiêu? |
| **Sustainability** | Có tránh xử lý lặp, quét dữ liệu không cần thiết và giữ worker nhàn rỗi quá mức không? |

**Kết luận:** Xử lý nền, scheduled jobs và batch giúp tách công việc dài khỏi request path, kiểm soát tải và phục hồi sau lỗi. Nhưng queue, scheduler hay batch engine không tự giải quyết tính đúng đắn: hệ thống vẫn cần trạng thái bền vững, idempotency, retry có giới hạn, checkpoint, quan sát và đối soát. Hãy chọn mô hình theo yêu cầu nghiệp vụ và đánh đổi đo được về độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tinh thần Well-Architected.
