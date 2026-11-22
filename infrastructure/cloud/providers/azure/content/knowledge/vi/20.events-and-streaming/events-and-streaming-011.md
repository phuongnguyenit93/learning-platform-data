# Thiết kế backpressure, replay và xử lý sự kiện đến muộn

Một hệ thống xử lý sự kiện có thể hoạt động ổn định ở mức vài trăm sự kiện/giây nhưng bắt đầu sai lệch khi traffic tăng đột biến, consumer lỗi trong nhiều phút hoặc thiết bị ngoại tuyến gửi dữ liệu cũ về sau. Vấn đề không chỉ là “đọc đủ nhanh”: nếu cố tăng concurrency vô hạn, hệ thống có thể cạn bộ nhớ; nếu ghi checkpoint trước khi lưu kết quả, có thể mất xử lý; nếu chỉ dùng thời điểm nhận sự kiện để thống kê, số liệu nghiệp vụ có thể bị tính vào sai ngày.

Ba năng lực thiết kế quan trọng là:

- **Backpressure:** giữ cho tốc độ nhận, xử lý và ghi kết quả không vượt khả năng bền vững của những thành phần phía sau.
- **Replay:** đọc lại sự kiện đã lưu trong khoảng retention hoặc từ kho lưu trữ để tính toán lại, sửa lỗi hoặc xây dựng một nhánh tiêu thụ mới.
- **Xử lý sự kiện đến muộn:** phân biệt **event time** với **processing time**, thiết kế watermark/window và chọn cách sửa, bỏ qua hoặc bù đắp dữ liệu trễ.

Trong Microsoft Azure, tình huống này thường xuất hiện với **Azure Event Hubs**, **Azure Stream Analytics**, **Azure Functions Event Hubs trigger**, các ứng dụng **Java** đọc Event Hubs bằng SDK, cùng các hệ thống đích như Azure Data Explorer, Azure SQL Database, Azure Cosmos DB hoặc Azure Storage.

Bài học thuộc chương **Sự kiện và dữ liệu streaming** của module **CLOUD_PROVIDERS_AZURE**. Bên cạnh những kiến thức về subscription, resource group, Microsoft Entra ID, mạng, compute, lưu trữ, giám sát, bảo mật và chi phí trên Azure, người học sẽ thiết kế một đường xử lý đủ khả năng chịu tải, phục hồi và giải thích được số liệu khi sự kiện đến sai thứ tự.

> **Điểm cốt lõi:** Event Hubs là một **append-only event stream có retention**, không phải queue xóa message khi consumer nhận. Consumer checkpoint xác định **đã xử lý đến đâu**; nó không làm dữ liệu biến mất khỏi broker. Và một sự kiện được nhận lúc 10:20 có thể thuộc về cửa sổ nghiệp vụ 10:00–10:05 nếu nó thực sự xảy ra lúc 10:03.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích event stream, partition, partition key, offset, sequence number, consumer group, retention và checkpoint.
2. Phân biệt **event time**, **enqueued time**, **processing time**, **watermark** và **allowed lateness**.
3. Phân tích backlog, consumer lag và backpressure bằng công thức tốc độ vào/ra.
4. Thiết kế bounded queue, bounded concurrency, retry/backoff và kiểm soát tốc độ theo downstream.
5. Nêu giới hạn của scale-out theo số partitions và rủi ro hot partition.
6. Xây dựng consumer Java dùng **EventProcessorClient** với Blob checkpoint store và nguyên tắc checkpoint sau khi kết quả được lưu bền vững.
7. Dùng consumer group tách biệt, vị trí bắt đầu theo offset/sequence/enqueued time hoặc **Event Hubs Capture** để thực hiện replay an toàn.
8. Thiết kế idempotency, upsert/retraction, versioned output và reconciliation khi replay.
9. Chọn cửa sổ event-time, watermark, late-arrival policy và chiến lược sửa số liệu đến muộn.
10. Giám sát lag, watermark delay, throttling, failed checkpoints, downstream latency và chi phí.
11. Xử lý tình huống outage, partition skew, sự kiện sai đồng hồ, quá retention hoặc dữ liệu đến trễ hơn ngưỡng cho phép.

## 2. Tình huống xuyên suốt: đơn hàng từ nhiều chi nhánh

Một hệ thống thương mại có các sự kiện:

~~~json
{
  "eventId": "evt-9b82",
  "orderId": "order-481",
  "storeId": "hcm-07",
  "eventType": "OrderPaid",
  "eventTimeUtc": "2026-11-20T03:03:20Z",
  "schemaVersion": 1,
  "amount": 350000,
  "currency": "VND"
}
~~~

Đây là **sự kiện mẫu**, không chứa dữ liệu khách hàng thật. Thời điểm 03:03:20 UTC tương ứng 10:03:20 giờ Việt Nam cùng ngày.

Giả sử một chi nhánh mất mạng trong 15 phút:

- OrderPaid thực sự xảy ra **10:03:20**.
- Thiết bị gửi được sự kiện lên Event Hubs lúc **10:18:10**.
- Consumer xử lý lúc **10:18:13**.
- Dashboard muốn tổng hợp doanh thu theo **cửa sổ 5 phút dựa vào thời điểm thanh toán**.

Nếu nhóm dữ liệu dùng thời gian consumer đọc, khoản tiền có thể bị đưa vào cửa sổ 10:15–10:20 thay vì 10:00–10:05. Nếu window 10:00–10:05 đã đóng và kết quả đã được công bố, hệ thống cần có **late-event policy**: cập nhật lại số liệu, phát bản điều chỉnh hoặc đưa sự kiện vào nhánh kiểm tra.

Cùng lúc, lượng sự kiện tăng gấp ba và downstream database chậm ghi. Consumer cần **backpressure** để không cạn RAM; nếu phát hành một bản sửa code tính tiền, nhóm cần **replay** dữ liệu gốc để tái tính đúng.

## 3. Các mốc thời gian và vị trí trong stream

### 3.1. Event time

**Event time** là khi sự kiện xảy ra trong thế giới nghiệp vụ. Giá trị này thường do producer, thiết bị hoặc hệ thống nguồn tạo.

Ví dụ **eventTimeUtc = 03:03:20Z** trong OrderPaid cho biết thời điểm thanh toán được ghi nhận tại nguồn.

Điểm cần kiểm soát:

- Clock skew của thiết bị hoặc dịch vụ nguồn.
- Chuyển đổi timezone và daylight saving time ở các quốc gia.
- Producer cố tình hoặc vô tình gửi timestamp tương lai/quá khứ.
- Schema version và precision của timestamp.
- Thời điểm nghiệp vụ nào là nguồn sự thật: lúc khách thanh toán, lúc ngân hàng xác nhận hay lúc order được ghi vào database?

**Event time không tự đáng tin chỉ vì nằm trong JSON.** Cần validation, giới hạn sai lệch và chính sách xử lý timestamp bất thường.

### 3.2. Enqueued time

**Enqueued time** là thời điểm broker Event Hubs ghi nhận sự kiện vào partition. Đây là metadata phía dịch vụ; khác timestamp do ứng dụng gửi.

~~~text
eventTimeUtc       = 2026-11-20T03:03:20Z
enqueuedTimeUtc    = 2026-11-20T03:18:10Z
processingTimeUtc  = 2026-11-20T03:18:13Z
~~~

Sự kiện có thể đến Event Hubs trễ 14 phút 50 giây dù consumer chỉ mất 3 giây để xử lý sau khi broker nhận.

### 3.3. Processing time

**Processing time** là thời điểm processor thực thi một bước trong hệ thống. Nó chịu ảnh hưởng của:

- Backlog và throttling.
- Số workers/partitions.
- Network và độ trễ dịch vụ đích.
- Batch size, retries, GC và CPU/memory.
- Consumer restart, partition ownership rebalance.

Nếu thống kê theo processing time, số liệu mô tả **khi hệ thống xử lý**, không phải nhất thiết **khi sự kiện xảy ra**.

### 3.4. Offset và sequence number

Mỗi **Event Hubs partition** là một log có thứ tự tương đối trong partition:

~~~text
Partition 0:
  sequence 101 → 102 → 103 → 104 → ...

Partition 1:
  sequence 77  → 78  → 79  → 80  → ...
~~~

- **Sequence number** do Event Hubs gán, tăng trong từng partition.
- **Offset** là vị trí trong log của partition, dùng cho việc đọc/đặt vị trí.
- Chúng chỉ có nghĩa đầy đủ khi đi kèm **Event Hub + partition ID**.
- Không có một total order toàn cục giữa nhiều partitions.
- **Checkpoint** là dấu mốc consumer đã xử lý đến vị trí nào, thường được lưu ngoài Event Hubs.

Không dùng sequence number của partition 0 để nhận xét một sự kiện trong partition 1 đã xảy ra trước/sau.

## 4. Kiến trúc tham chiếu trên Azure

~~~mermaid
flowchart LR
    EDGE["POS / Mobile / IoT / API"] -->|"Batch, retry có giới hạn"| HUB["Azure Event Hubs<br/>N partitions + retention"]
    HUB --> GROUPA["Consumer group realtime"]
    HUB --> GROUPB["Consumer group analytics"]
    HUB --> CAP["Event Hubs Capture<br/>Blob / ADLS Gen2"]
    GROUPA --> PROC["Java EventProcessorClient<br/>bounded processing"]
    PROC --> SINK["Azure SQL / Cosmos DB / ADX"]
    PROC --> CP["Blob Storage<br/>ownership + checkpoints"]
    GROUPB --> ASA["Azure Stream Analytics / Spark"]
    ASA --> VIEW["Windowed aggregates<br/>late data policy"]
    CAP --> REPLAY["Backfill/replay pipeline"]
    REPLAY --> SINK2["Versioned outputs / reconciliation"]
    MON["Azure Monitor + app telemetry"] -. "Lag, errors, latency, cost" .-> PROC
    MON -. "Watermark delay" .-> ASA
~~~

Trong một hệ thống thực, Azure Event Hubs có thể được cấp quyền bằng **Microsoft Entra ID/managed identity**, ACR/AKS/App Service xử lý ứng dụng, Blob Storage lưu checkpoints/capture và Azure Monitor cảnh báo.

**Đừng nhầm Azure Event Hubs và Azure Service Bus:**

| Nhu cầu | Event Hubs | Service Bus |
|---|---|---|
| Telemetry/event streams thông lượng lớn | Phù hợp | Không phải mục tiêu chính |
| Nhiều nhóm consumer độc lập | Consumer groups đọc log riêng | Topic/subscriptions theo mô hình pub/sub |
| Replay trong retention | Đọc lại từ vị trí/consumer group khác | Không phải mô hình replay log tương đương |
| Message settlement per-message, DLQ | Không có Complete/Abandon/DLQ kiểu Service Bus queue | Có PeekLock, DLQ, settlement |
| Ordering | Trong từng partition | Theo cơ chế queue/session |
| Checkpoint | Consumer quản lý checkpoint đọc stream | Consumer settle message |
| Backpressure | Điều tiết producer/consumer và buffer; log giữ backlog có hạn | Prefetch, concurrency, locks, queue depth |
| Event-time windowing | Kết hợp ASA/Spark/Flink/ADX | Cần pipeline riêng tùy use case |

## 5. Azure Event Hubs: partition, consumer group và retention

### 5.1. Partition

Event Hubs phân bố sự kiện vào nhiều **partitions**. Với partition key giống nhau, producer có thể đưa những sự kiện liên quan vào cùng partition theo cơ chế partitioning, thuận tiện khi consumer cần thứ tự theo một khóa.

Ví dụ:

~~~text
Partition key = storeId

hcm-07 → partition P1
hcm-08 → partition P0
hn-03  → partition P2
~~~

Partition key không bảo đảm một event của hcm-07 luôn đến trước mọi event của hcm-08. Và việc chọn khóa có phân phối quá lệch sẽ tạo **hot partition**.

### 5.2. Consumer group

Mỗi **consumer group** cung cấp góc nhìn tiêu thụ độc lập trên cùng một Event Hub:

~~~text
Event Hub orders-stream
    ├── cg-orders-realtime → dashboard
    ├── cg-finance-v1      → báo cáo tài chính
    └── cg-backfill-2026   → replay có kiểm soát
~~~

Consumer group không nhân bản vật lý toàn bộ dữ liệu thành một log mới. Nó cho phép các consumer quản lý tiến độ riêng và đọc cùng một nguồn trong phạm vi retention.

**Lưu ý:** trong kiến trúc dùng EventProcessorClient, progress/checkpoint thường được lưu trong Azure Blob Storage và gắn với consumer group/partition. Consumer group **không tự lưu một checkpoint durable cho mọi SDK** nếu ứng dụng không cấu hình checkpoint store.

### 5.3. Retention

Event Hubs giữ dữ liệu trong **một khoảng retention hữu hạn** theo tier và cấu hình. Consumer có thể đọc lại những sự kiện còn trong retention. Khi sự kiện đã bị broker loại bỏ theo retention, **đổi offset hoặc tạo consumer group mới không mang dữ liệu đó trở lại**.

Không hard-code con số retention mặc định hoặc tối đa trong thiết kế production: các giới hạn và lựa chọn phụ thuộc tier, namespace và phiên bản dịch vụ. Phải kiểm tra cấu hình Event Hub cụ thể trước khi cam kết RPO/replay window.

### 5.4. Capture

**Event Hubs Capture** có thể tự động lưu sự kiện sang **Azure Blob Storage hoặc Azure Data Lake Storage Gen2** theo cấu hình. Nó giúp có một kho dữ liệu lâu hơn broker retention cho audit/backfill.

Nhưng Capture không đồng nghĩa “đặt checkpoint trở lại và đọc file archive qua Event Hubs SDK”. Replay từ Capture cần **pipeline đọc file archive** rồi:

- Tính toán lại trực tiếp vào một output versioned; hoặc
- Phát lại qua Event Hub/stream mới nếu kiến trúc yêu cầu.

Cần bảo vệ định dạng schema, partition/time metadata, thứ tự, idempotency và chi phí re-ingestion.

## 6. Backpressure là gì?

**Backpressure** là tập hợp cơ chế giúp tốc độ đưa công việc vào hệ thống không vượt khả năng xử lý và lưu kết quả của hệ thống một cách bền vững.

Đặt:

- **λ (lambda)**: tốc độ sự kiện vào trung bình, events/giây.
- **μ (mu)**: tốc độ xử lý hoàn tất trung bình, events/giây.
- **B(t)**: backlog tại thời điểm t, đo bằng số events.

Với giả thiết đơn giản không có sự kiện bị loại:

~~~text
Nếu λ > μ:
    backlog tăng xấp xỉ (λ - μ) × t

Nếu λ < μ:
    consumer có thể giảm backlog,
    với tốc độ xấp xỉ (μ - λ)
~~~

Nếu dữ liệu liên tục đến nhanh hơn tốc độ phục vụ, **tăng memory buffer không giải quyết được bài toán dài hạn**. Nó chỉ kéo dài thời gian trước khi xảy ra sự cố.

### 6.1. Ví dụ tính backlog

Một Event Hub nhận **18.000 events/s**. Database chỉ cho phép consumer hoàn tất **12.000 events/s** trong thời gian 3 phút.

~~~text
λ = 18.000 events/s
μ = 12.000 events/s
t = 3 × 60 = 180 giây

Backlog tăng = (18.000 - 12.000) × 180
             = 1.080.000 events
~~~

Sau khi database phục hồi, hệ thống có thể xử lý **20.000 events/s**, còn producer tiếp tục gửi 18.000/s:

~~~text
Tốc độ giảm backlog = 20.000 - 18.000
                    = 2.000 events/s

Thời gian bắt kịp ≈ 1.080.000 / 2.000
                  = 540 giây = 9 phút
~~~

Đây là **mô hình lý tưởng**, chưa tính overhead retry, partition skew, batch latency, message size, checkpoints và khoảng thời gian nâng cấp capacity. Nếu μ vẫn nhỏ hơn λ, hệ thống **không thể bắt kịp** dù đã khởi động lại consumer.

### 6.2. Bảng tình trạng quá tải

| Tình trạng | Dấu hiệu | Phản ứng phù hợp |
|---|---|---|
| Producer nhanh hơn Event Hubs quota | Throttled requests, send latency/retry tăng | Kiểm tra capacity/tier, batch, quota, exponential backoff |
| Event Hubs nhận tốt nhưng consumer chậm | Lag theo partition tăng, checkpoint cũ | Tối ưu/scale consumer, kiểm tra downstream |
| Consumer nhanh nhưng database chậm | DB 429/timeout, pool chờ lâu | Bounded concurrency, retry có backoff, batch/upsert |
| Một partition nóng | Chỉ một partition lag lớn | Đổi partition key/distribution, tăng tốc xử lý từng partition |
| Memory trong consumer tăng | Unbounded queue, heap/GC tăng | Giới hạn buffer/in-flight, tạm giảm nhận |
| Watermark chậm tiến | Window output trễ | Kiểm tra partition idle, out-of-order tolerance và ingestion skew |
| Retention sắp hết trước khi bắt kịp | Đầu log cũ hơn vị trí checkpoint | Kích hoạt kế hoạch backfill từ Capture/nguồn gốc |

## 7. Backpressure theo từng lớp

### 7.1. Producer

Không phải lúc nào producer có thể dừng ngay lập tức. Một thiết bị IoT hoặc dịch vụ bên thứ ba có thể tiếp tục tạo dữ liệu. Vì vậy cần:

- **Batch gửi** theo giới hạn size của SDK/dịch vụ.
- **Retry có exponential backoff và jitter** cho lỗi tạm, không retry vô hạn.
- **Client-side bounded queue** để tránh cạn RAM.
- Theo dõi thời gian chờ để gửi, tỷ lệ retry và dropped events theo SLA.
- Dùng **durable local buffer hoặc outbox** khi producer bắt buộc không được mất dữ liệu.
- Nếu dữ liệu telemetry có thể lấy mẫu, **sampling/aggregation** ở nguồn theo quy tắc nghiệp vụ.
- Thực hiện **load shedding có phân loại**: chỉ bỏ những event cho phép; không tự bỏ giao dịch thanh toán/audit bắt buộc.

**Event Hubs không tự đẩy ngược tín hiệu dừng về mọi producer** khi consumer bị chậm. Nó cung cấp lớp lưu stream với capacity/retention hữu hạn; ứng dụng phải điều tiết tốc độ và lên kế hoạch nguồn dữ liệu.

### 7.2. Broker

Event Hubs hấp thụ chênh lệch tốc độ trong một thời gian bằng retention và capacity đã cấp, nhưng không phải **kho backlog vô hạn**.

Các tham số cần xem:

- Throughput units/processing units/capacity phù hợp tier.
- Partition count và phân phối partition key.
- Kích thước sự kiện trung bình và peak.
- Retention đủ dài so với worst-case outage + catch-up.
- Capture nếu cần bảo lưu ngoài retention.
- Các giới hạn incoming/outgoing throughput và throttling.

Khi nâng capacity, không phải mọi vấn đề được giải quyết: một hot partition, database chậm hoặc consumer xử lý tuần tự vẫn có thể là nút thắt.

### 7.3. Consumer

Ở consumer, backpressure thường là giới hạn:

- Số events đang xử lý đồng thời (**in-flight**).
- Số lượng event batch lấy vào bộ nhớ.
- Số kết nối/requests tới database.
- Kích thước queue nội bộ.
- Thời gian timeout và retry.
- Tần suất checkpoint và flushing.

Trong mô hình pull, consumer có thể **giảm tốc hoặc tạm dừng nhận** thay vì liên tục đưa thêm work vào queue RAM. Với SDK event processor callback, cần hiểu cách SDK dispatch sự kiện và bảo đảm việc xử lý/đưa vào buffer có giới hạn theo luồng, không gọi submit vào một executor không giới hạn.

### 7.4. Sink/downstream

Nếu database chỉ ghi ổn định **2.000 records/s**, tăng số Java worker từ 4 lên 40 có thể làm DB quá tải hơn. Cần:

- Upsert/batch writes phù hợp.
- Giới hạn số kết nối và requests đồng thời.
- Rate limit theo shared quota.
- Retry theo **Retry-After** nếu API cung cấp.
- Circuit breaker khi dependency lỗi kéo dài.
- Ghi idempotent để retry không tạo trùng.
- Tách hot read path khỏi batch/backfill sink khi cần.

### 7.5. Sơ đồ luồng điều tiết

~~~mermaid
flowchart LR
    P["Producers"] -->|"Bounded batching"| E["Event Hubs"]
    E --> C["Consumer: bounded in-flight"]
    C --> Q{"Sink latency/429?"}
    Q -->|Bình thường| W["Batch/upsert durable output"]
    Q -->|Quá tải| BK["Giảm concurrency + backoff"]
    BK --> C
    W --> CP["Checkpoint sau khi lưu bền vững"]
    CP -. "Consumer tiếp tục đọc" .-> E
~~~

**Backpressure không phải “giữ event mãi trong RAM”.** Nếu downstream chậm, Event Hubs giữ dữ liệu trong retention, consumer tiến chậm lại; cần bảo đảm có đủ retention/capacity để phục hồi.

## 8. Giới hạn scale-out: partitions và hot keys

### 8.1. Tăng pods không có nghĩa tăng throughput vô hạn

Với **EventProcessorClient** dùng checkpoint/ownership store, mỗi partition tại một thời điểm thường được một processor instance trong cùng consumer group sở hữu để điều phối việc đọc và checkpoint.

Ví dụ Event Hub có 6 partitions:

~~~text
Consumer group: realtime

Worker A: P0, P1
Worker B: P2, P3
Worker C: P4, P5

Nếu thêm Worker D/E/F:
    các partitions được cân bằng lại giữa các workers.

Nếu thêm Worker G/H/I:
    không có đủ partitions để mỗi worker sở hữu một partition.
~~~

Số instance xử lý theo partition thường có ích tối đa gần với số partitions cho **một EventProcessorClient consumer group**, dù một partition vẫn có thể dùng concurrency nội bộ với trade-off về thứ tự và checkpoint.

Không tăng số replicas AKS vô hạn chỉ vì thấy lag.

### 8.2. Hot partition

Nếu partition key là một cửa hàng rất lớn, hầu hết dữ liệu có thể dồn vào P2:

| Partition | Incoming events/s | Consumer capacity/s | Lag |
|---|---:|---:|---|
| P0 | 500 | 2.000 | Thấp |
| P1 | 700 | 2.000 | Thấp |
| P2 | 8.000 | 2.000 | Tăng nhanh |
| P3 | 600 | 2.000 | Thấp |

Dù tổng capacity cluster còn, **P2 vẫn lag** vì thứ tự/độc quyền xử lý và tính chất khóa.

Cân nhắc:

1. Chọn partition key phân phối đều hơn nếu yêu cầu ordering cho phép.
2. Tách workload cực nóng thành nhiều keys/shards có thể tái hợp.
3. Tối ưu throughput trong từng partition: batch, giảm I/O, async giới hạn.
4. Dùng một hub mới với số partitions/cấu hình phù hợp khi cần thay đổi lớn.
5. Xây dựng chiến lược migration và bảo đảm ordering/sequence không bị phá.

Khả năng **thay đổi partition count** phụ thuộc tier và tính năng Event Hubs tại thời điểm triển khai; không giả định có thể giảm/tăng tùy ý mà không ảnh hưởng hash-to-partition của partition key.

### 8.3. Ordering và backpressure

Nếu muốn hoàn thành xử lý **đúng thứ tự trong một partition**, không được dispatch các events của partition đó vào executor song song rồi checkpoint event có sequence cao hơn khi event trước chưa hoàn tất.

Có thể xử lý song song **giữa partitions** hoặc dùng xử lý có tracking những completed contiguous ranges; nếu không, checkpoint sai có thể làm mất công việc sau crash.

## 9. Checkpoint: hợp đồng “đã hoàn tất đến đâu”

**Checkpoint** là vị trí mà consumer ghi lại để lần khởi động tiếp đọc tiếp từ vị trí thích hợp. Với Azure EventProcessorClient, checkpoint thường nằm trong **Azure Blob Storage** cùng dữ liệu ownership/load balancing.

### 9.1. Quy trình an toàn

~~~mermaid
flowchart LR
    R["Read event N"] --> V["Validate"]
    V --> P["Process"]
    P --> S["Durable, idempotent sink commit"]
    S --> C["Checkpoint N"]
    C --> NEXT["Read tiếp"]
~~~

Nếu checkpoint được ghi **trước** khi sink xác nhận, một lần crash có thể làm event chưa được lưu nhưng consumer đã đánh dấu qua nó. Đây là **nguy cơ mất xử lý**.

### 9.2. At-least-once và khoảng crash

| Thứ tự | Khi crash | Hậu quả | Bảo vệ |
|---|---|---|---|
| Read → checkpoint → sink | Crash sau checkpoint, trước sink | Có thể bỏ qua event vĩnh viễn khi restart | **Không checkpoint trước durable output** |
| Read → sink → checkpoint | Crash sau sink, trước checkpoint | Event được đọc lại | Idempotent sink/unique key |
| Read → sink → checkpoint | Không crash | Tiến độ đúng | Giám sát và lưu checkpoint |
| Read → sink gặp lỗi | Không checkpoint | Event có thể được retry | Bounded retry, quarantine/poison policy |
| Read → async writes nhiều event → checkpoint quá xa | Một event trước chưa xong | Mất xử lý event chưa hoàn tất | Commit theo contiguous completion |

**Event Hubs không cung cấp exactly-once business effects giữa broker và database khác chỉ nhờ checkpoint.** Thiết kế thông thường là **at-least-once + idempotent sink**, hoặc cơ chế state/transaction của engine xử lý được chứng minh và vận hành đúng.

### 9.3. Chọn checkpoint interval

Checkpoint từng event giảm số event bị đọc lại sau restart nhưng tạo nhiều thao tác Blob Storage và overhead.

Checkpoint mỗi 100 events hoặc sau 30 giây giảm I/O nhưng sẽ đọc lại nhiều event hơn nếu crash. Chọn dựa vào:

- Tốc độ sự kiện.
- Chi phí Blob operations.
- Số event chấp nhận xử lý lại.
- Thời gian replay/catch-up mong muốn.
- Mức idempotency của sink.
- Workload có partition ownership rebalance thường xuyên hay không.

Không có “checkpoint mỗi N events” tối ưu cho mọi hệ thống.

### 9.4. Checkpoint store của mỗi consumer group

Một nhóm processor chia sẻ cùng consumer group có thể dùng cùng checkpoint container để điều phối ownership trong cách tổ chức được SDK hỗ trợ. Nhưng **một replay job độc lập không được tùy tiện dùng lại cùng consumer group/checkpoint store của production**, vì nó có thể tranh ownership hoặc thay đổi vị trí tiến độ.

Khuyến nghị: riêng **consumer group**, riêng **checkpoint store path/container** cho replay, và tách output để giảm nguy cơ ghi đè.

## 10. Thực hành Azure: tạo Event Hubs và consumer group

Các lệnh bên dưới minh họa trong **subscription lab do bạn được phép quản lý**. Chúng có thể tạo tài nguyên tính phí; không chạy trên production khi chưa có change plan.

### 10.1. Tạo namespace Standard và event hub

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-stream-lab"
LOCATION="southeastasia"
NS="<globally-unique-eventhubs-namespace>"
HUB="orders-stream"

az group create \
  --name "$RG" \
  --location "$LOCATION"

az eventhubs namespace create \
  --resource-group "$RG" \
  --name "$NS" \
  --location "$LOCATION" \
  --sku Standard

az eventhubs eventhub create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --name "$HUB" \
  --partition-count 4
~~~

Hãy xác minh lệnh/tùy chọn theo Azure CLI phiên bản sử dụng. Đặc biệt, cấu hình retention có thể thay đổi với tier và API; không sao chép một giá trị tùy ý trên production.

### 10.2. Tạo các consumer group độc lập

~~~bash
az eventhubs eventhub consumer-group create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --eventhub-name "$HUB" \
  --name "cg-orders-realtime"

az eventhubs eventhub consumer-group create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --eventhub-name "$HUB" \
  --name "cg-orders-replay-lab"
~~~

Kiểm tra:

~~~bash
az eventhubs eventhub show \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --name "$HUB" \
  --output json

az eventhubs eventhub consumer-group list \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --eventhub-name "$HUB" \
  --output table
~~~

### 10.3. Cấp quyền Entra ID

Với Java producer:

- **Azure Event Hubs Data Sender** tại namespace/hub scope phù hợp.

Với consumer:

- **Azure Event Hubs Data Receiver** tại namespace/hub scope phù hợp.

Với checkpoint store:

- **Storage Blob Data Contributor** (hoặc quyền data-plane tối thiểu đủ theo cơ chế checkpoint store) trên Blob container/account theo scope tổ chức.

**Không cấp Owner/Contributor toàn subscription** chỉ để một Java worker đọc Event Hubs. Quyền management plane khác quyền data plane. Role assignment mới có thể mất thời gian propagate.

### 10.4. Tạo Blob container checkpoint

Tạo Storage Account và container được phê duyệt, ví dụ **eh-checkpoints-realtime**; đặt tên hợp lệ và cấu hình quyền thích hợp. Một account production cần cân nhắc network, redundancy, retention, soft delete và các policy có thể ảnh hưởng thao tác checkpoint/ownership.

Không dùng chung một container checkpoint với tập dữ liệu nghiệp vụ cần retention/immutability khác nếu có nguy cơ chính sách storage cản cập nhật checkpoint.

## 11. Java producer: batch gửi và partition key

Khi gửi Event Hubs, SDK có **EventDataBatch** giới hạn theo kích thước cho phép. Producer nên kiểm tra kết quả **tryAdd** thay vì tự tạo một batch quá kích thước.

### 11.1. Ví dụ Java minh họa

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventData;
import com.azure.messaging.eventhubs.EventDataBatch;
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubProducerClient;
import com.azure.messaging.eventhubs.models.CreateBatchOptions;

import java.util.UUID;

public final class OrdersProducerDemo {
    public static void main(String[] args) {
        String fqdn = System.getenv("EVENTHUBS_FQDN");
        String hub = System.getenv("EVENTHUB_NAME");

        if (fqdn == null || hub == null) {
            throw new IllegalArgumentException("Missing Event Hubs config");
        }

        try (EventHubProducerClient sender =
                new EventHubClientBuilder()
                  .credential(fqdn, hub,
                      new DefaultAzureCredentialBuilder().build())
                  .buildProducerClient()) {

            String storeId = "hcm-07";
            EventDataBatch batch = sender.createBatch(
                new CreateBatchOptions().setPartitionKey(storeId));

            for (int i = 0; i < 10; i++) {
                String eventId = UUID.randomUUID().toString();
                EventData event = new EventData(
                    "{\"eventId\":\"" + eventId +
                    "\",\"storeId\":\"hcm-07\"," +
                    "\"eventType\":\"OrderPaid\"}");
                event.getProperties().put("eventId", eventId);

                if (!batch.tryAdd(event)) {
                    if (batch.getCount() == 0) {
                        throw new IllegalStateException(
                            "Single event exceeds batch size");
                    }
                    sender.send(batch);
                    batch = sender.createBatch(
                        new CreateBatchOptions()
                          .setPartitionKey(storeId));
                    if (!batch.tryAdd(event)) {
                        throw new IllegalStateException(
                            "Cannot add event to empty batch");
                    }
                }
            }

            if (batch.getCount() > 0) {
                sender.send(batch);
            }
        }
    }
}
~~~

**Lưu ý:**

- Đây là producer demo gửi payload giản lược; muốn xử lý event-time cần thêm **eventTimeUtc** đáng tin và schema rõ.
- **EventId** phải ổn định theo sự kiện nghiệp vụ khi producer retry; random ID trong vòng lặp chỉ minh họa phát sự kiện mới.
- **Partition key** giúp định tuyến theo storeId, nhưng có thể gây hot partition nếu một store tạo quá nhiều traffic.
- Một send thất bại chưa cho biết broker đã nhận hay chưa; Event Hubs không cung cấp duplicate detection kiểu Service Bus queue. Consumer cần idempotency.
- SDK tự thực hiện một số retry theo cấu hình, nhưng producer vẫn cần giới hạn retry/buffer và quan sát send latency.

### 11.2. Khi một event không vừa batch

Nếu **batch.tryAdd(event)** trả false ngay trên batch rỗng, event lớn hơn mức cho phép: không retry vô hạn. Cân nhắc:

- Nén/giảm kích thước payload theo quy tắc.
- Đưa dữ liệu lớn vào Blob Storage và chỉ gửi **reference + checksum** qua Event Hubs.
- Tách event thành các phần có schema/reassembly rõ khi thực sự cần.
- Kiểm tra giới hạn message size theo tier và cấu hình.

Không lặng lẽ bỏ qua event nếu dữ liệu là giao dịch bắt buộc.

## 12. Java consumer dùng EventProcessorClient và Blob checkpoint store

Để xử lý liên tục với load balancing, Azure SDK for Java cung cấp **EventProcessorClient** phối hợp **BlobCheckpointStore**.

### 12.1. Dependencies

Trong dự án Maven, dùng các dependency được pin phiên bản hiện hành/được tổ chức phê duyệt:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-messaging-eventhubs</artifactId>
    <version>REPLACE_WITH_APPROVED_VERSION</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-messaging-eventhubs-checkpointstore-blob</artifactId>
    <version>REPLACE_WITH_APPROVED_VERSION</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-blob</artifactId>
    <version>REPLACE_WITH_APPROVED_VERSION</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>REPLACE_WITH_APPROVED_VERSION</version>
  </dependency>
</dependencies>
~~~

**REPLACE_WITH_APPROVED_VERSION là placeholder**: đoạn này **không phải POM chạy ngay**. Nên dùng Azure SDK BOM/dependency management để thống nhất version và đọc tài liệu API tương ứng. Không chọn version bằng cách sao chép ngẫu nhiên từ bài viết cũ.

### 12.2. Ví dụ EventProcessorClient

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.core.credential.TokenCredential;
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventProcessorClient;
import com.azure.messaging.eventhubs.EventProcessorClientBuilder;
import com.azure.messaging.eventhubs.checkpointstore.blob.BlobCheckpointStore;
import com.azure.storage.blob.BlobContainerClientBuilder;
import com.azure.storage.blob.BlobContainerAsyncClient;

public final class RealtimeOrdersConsumer {
    public static void main(String[] args) throws Exception {
        TokenCredential identity =
                new DefaultAzureCredentialBuilder().build();

        String fqdn = required("EVENTHUBS_FQDN");
        String hub = required("EVENTHUB_NAME");
        String blobEndpoint = required("CHECKPOINT_BLOB_ENDPOINT");
        String checkpointContainer = required("CHECKPOINT_CONTAINER");

        BlobContainerAsyncClient blobs =
                new BlobContainerClientBuilder()
                    .endpoint(blobEndpoint)
                    .containerName(checkpointContainer)
                    .credential(identity)
                    .buildAsyncClient();

        EventProcessorClient processor =
                new EventProcessorClientBuilder()
                    .credential(fqdn, hub, identity)
                    .consumerGroup("cg-orders-realtime")
                    .checkpointStore(new BlobCheckpointStore(blobs))
                    .processEvent(context -> {
                        String partition =
                                context.getPartitionContext()
                                       .getPartitionId();
                        String body =
                                context.getEventData()
                                       .getBodyAsString();

                        try {
                            // LAB: log mô phỏng xử lý.
                            // PRODUCTION: validate, write idempotently
                            // tới DB/Storage, CHỜ durable commit,
                            // sau đó mới updateCheckpoint().
                            System.out.printf(
                                "partition=%s event=%s%n",
                                partition, body);

                            context.updateCheckpoint();
                        } catch (RuntimeException error) {
                            System.err.println(
                                "Event failed: " + error.getMessage());
                            // Không checkpoint sự kiện thất bại.
                            // Thiết kế stop/retry/quarantine riêng.
                        }
                    })
                    .processError(errorContext ->
                        System.err.println(
                            "Event processor error: "
                              + errorContext.getThrowable()))
                    .buildEventProcessorClient();

        processor.start();
        try {
            Thread.sleep(60_000);
        } finally {
            processor.stop();
        }
    }

    static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing " + name);
        }
        return value;
    }
}
~~~

**Quan trọng:** ví dụ này chỉ **in log rồi checkpoint để học API**, vì thế **không an toàn cho nghiệp vụ nếu stdout là nơi duy nhất lưu kết quả**. Trong production, thay đoạn in log bằng thao tác **ghi bền vững và idempotent**, xác nhận commit thành công rồi mới checkpoint. Đoạn catch trong callback cũng **không tự bảo đảm retry cùng event ngay lập tức** nếu processor tiếp tục nhận events sau đó; cần thiết kế chiến lược error handling cụ thể, có thể stop partition processing/pipeline hoặc dùng durable poison-event handling trước khi tiến checkpoint.

### 12.3. Quyền và network của Blob checkpoint store

- Blob container phải tồn tại.
- Danh tính cần quyền đọc/ghi/lease tương ứng với checkpoint/ownership.
- Nếu storage account dùng Private Endpoint, consumer phải resolve DNS và kết nối đúng.
- Không cho hệ thống lifecycle xóa checkpoint blobs theo lịch ngắn hơn nhu cầu.
- Có kế hoạch xử lý ownership rebalance, mất kết nối Blob và rollback vị trí.
- Replay độc lập phải dùng consumer group/checkpoint namespace riêng.

### 12.4. Đặt checkpoint theo batch/thời gian

Trong production, không nhất thiết update mỗi event. Một policy có thể là **sau 100 events đã durable commit** hoặc **sau 30 giây**, miễn rằng checkpoint chỉ đánh dấu **vị trí liên tục đã hoàn tất** của partition.

Cần cẩn thận với:

- Async writes hoàn tất không theo thứ tự.
- Hai workers tranh partition trong lúc rebalance.
- Event xử lý thất bại nhưng callback vẫn cập nhật checkpoint các event sau.
- Checkpoint storage throttling/authorization failures.
- Shutdown khi còn các writes in flight.

**Một checkpoint tiến qua event N nghĩa là hệ thống chấp nhận có thể không tự đọc lại các event trước N trong đường consumer đó.** Đừng tiến checkpoint qua một lỗ hổng chưa xử lý.

## 13. Thiết kế bounded processing thực tế

### 13.1. Mô hình dùng semaphore

Với consumer dùng async I/O, có thể đặt **semaphore** giới hạn số bản ghi cùng xử lý:

~~~java
import java.util.concurrent.Semaphore;

Semaphore permits = new Semaphore(16);

// Pseudocode minh họa điều tiết:
// Trong callback nhận event:
//   permits.acquire()
//   try {
//       durableSink.writeIdempotently(event)
//       contiguousCheckpointTracker.markCommitted(event.partition, event.sequence)
//   } finally {
//       permits.release()
//   }
~~~

**Đây là pseudocode trong comment, không phải chương trình hoàn chỉnh.** Không gọi updateCheckpoint của event N chỉ vì event N đã xong khi N-1 còn chưa xong.

### 13.2. Bounded queue và worker pool

Một mô hình khác:

~~~text
EventProcessor callback
    |
    v
Bounded work queue: capacity = 5.000
    |
    v
Fixed worker pool: 16 workers
    |
    v
DB connection pool: max 20
    |
    v
Durable output + per-partition contiguous checkpoint
~~~

Nếu queue đầy:

- Giảm tốc độ dispatch/nhận tại lớp SDK phù hợp.
- Tạm hoãn accept thêm work vào queue.
- Cảnh báo backlog thay vì tăng RAM vô hạn.
- Không drop dữ liệu bắt buộc.
- Nếu phải giảm tải, áp dụng policy minh bạch theo event type/SLO.

**Queue trong RAM không phải nơi lưu bền vững.** Khi process crash, dữ liệu chưa checkpoint có thể đọc lại nếu còn retention; dữ liệu đã checkpoint dù chưa commit sẽ gặp nguy cơ mất xử lý.

### 13.3. Retry nên nằm ở tầng nào?

- **Producer retry:** transient send errors, nhưng cần eventId ổn định.
- **Broker throttling retry:** tôn trọng backoff, rate limit, capacity.
- **Consumer processing retry:** lỗi transient của database/API, có deadline và jitter.
- **Poison event:** schema lỗi hoặc giá trị bất hợp lệ; không retry vô hạn.
- **Replay/backfill:** một quy trình tách biệt, có kế hoạch output và dedup.

Event Hubs **không có DLQ per-message kiểu Service Bus**. Nếu muốn quarantine poison events, xây **poison topic/hub/Blob container hoặc failure table** và ghi metadata/correlation đủ để điều tra, sau đó quyết định checkpoint theo chính sách đã phê duyệt.

## 14. Replay là gì và khi nào cần?

**Replay** là đọc lại các event lịch sử để chạy lại logic xử lý, khôi phục state hoặc kiểm tra một thuật toán mới.

Các trường hợp:

1. Deploy code có bug tính tổng doanh thu, cần tái tính 24 giờ qua.
2. Một processor ngừng chạy 40 phút, cần bắt kịp backlog.
3. Có một sink data warehouse mới cần dữ liệu lịch sử.
4. Một business rule mới phải áp dụng lại lên các sự kiện còn trong retention.
5. Kiểm toán yêu cầu so sánh kết quả trước/sau một thay đổi.
6. Sự kiện đến muộn đã vượt watermark/window và cần backfill.

### 14.1. Replay không phải là gửi lại từ producer

Nếu dữ liệu còn trong **Event Hubs retention**, consumer mới có thể đọc lại các partitions từ vị trí trước đó mà không cần producer gửi lại. Điều đó tránh thay đổi log gốc.

Nếu dữ liệu **đã hết retention**, phải đọc từ **Capture/Blob/ADLS/source archive** nếu trước đó đã thiết kế lưu giữ. Tái phát vào một Event Hub mới là một lựa chọn, nhưng không phải lúc nào cũng cần.

### 14.2. Checkpoint và replay

Ví dụ:

~~~text
Partition P0 còn giữ sequence 1000 ... 5000

Consumer production:
    checkpoint = 4800
    → đọc tiếp sau vùng đã checkpoint

Consumer replay mới:
    start = 2000
    → đọc lại từ 2000 theo điều kiện log còn lưu

Một consumer group khác không làm checkpoint của
production tự thay đổi.
~~~

Nếu dùng **chính consumer group và checkpoint store của production** để replay, bạn có thể làm lệch tiến độ, tranh ownership hoặc đọc trùng/ghi đè output production. Hãy tách chúng.

## 15. Ba điểm bắt đầu replay: offset, sequence và enqueued time

Trong Event Hubs, consumer có thể chọn **EventPosition** theo API:

- **Earliest:** sự kiện sớm nhất **còn retention**.
- **Latest:** vị trí cuối tại thời điểm bắt đầu; phù hợp chỉ nhận sự kiện mới theo semantics của SDK.
- **Offset:** một vị trí cụ thể trong một partition.
- **Sequence number:** chọn theo số sequence và điều kiện inclusive/exclusive của API.
- **Enqueued time:** vị trí dựa vào thời điểm broker enqueued event.

### 15.1. Không nhầm event time với enqueued time

Nếu muốn “tái tính mọi thanh toán xảy ra từ 10:00 đến 11:00 theo giờ nghiệp vụ” thì seek **enqueued time** từ 10:00 không đủ. Một sự kiện xảy ra 10:05 nhưng gửi tới broker 10:25 mới được tìm thấy sau 10:25.

Do đó backfill theo **event-time interval** thường phải đọc **khoảng enqueued-time đủ rộng**, rồi filter theo eventTimeUtc và tính toán late arrivals.

### 15.2. Inclusivity và vị trí bắt đầu

Khi seek bằng sequence/offset, SDK có quy tắc chọn bao gồm hay loại trừ điểm bắt đầu. Phải kiểm tra tham số **isInclusive** và test bằng dữ liệu lab, tránh bỏ sót hoặc đọc lại một event sai mong đợi.

Khi seek bằng thời điểm, có thể có nhiều events enqueued gần như cùng lúc ở các partitions; không tự suy có một sequence number toàn cục.

### 15.3. Retention không bảo đảm lịch sử vô hạn

Một consumer nhóm mới tạo và seek earliest chỉ đọc **đầu retained range**, không phải toàn bộ dữ liệu từ khi Event Hub được tạo. Nếu muốn replay 6 tháng nhưng retention chỉ vài ngày, phải chuẩn bị Capture/archive trước.

## 16. Thực hành Java: replay có kiểm soát từ vị trí ban đầu

Với **EventHubConsumerAsyncClient**, có thể đọc một partition độc lập từ EventPosition, phù hợp cho lab và kiểm tra dữ liệu.

### 16.1. Ví dụ Java Async consumer

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.eventhubs.EventHubClientBuilder;
import com.azure.messaging.eventhubs.EventHubConsumerAsyncClient;
import com.azure.messaging.eventhubs.models.EventPosition;

import java.time.Duration;

public final class PartitionReplayDemo {
    public static void main(String[] args) {
        String fqdn = System.getenv("EVENTHUBS_FQDN");
        String hub = System.getenv("EVENTHUB_NAME");
        String partition = "0";

        EventHubConsumerAsyncClient consumer =
            new EventHubClientBuilder()
              .credential(fqdn, hub,
                  new DefaultAzureCredentialBuilder().build())
              .consumerGroup("cg-orders-replay-lab")
              .buildAsyncConsumerClient();

        try {
            consumer.receiveFromPartition(
                    partition, EventPosition.earliest())
                .take(20)
                .doOnNext(partitionEvent -> {
                    System.out.println(
                        "Replay partition=" + partition
                        + ", payload="
                        + partitionEvent.getData()
                                        .getBodyAsString());
                })
                .blockLast(Duration.ofMinutes(2));
        } finally {
            consumer.close();
        }
    }
}
~~~

Đây là **lab đọc tối đa 20 events**, in ra stdout. Không ghi vào bảng doanh thu production. Nếu partition không có đủ 20 sự kiện, thao tác **blockLast** có thể timeout; cần xử lý timeout như tình trạng bình thường của lab thay vì coi dữ liệu đã mất.

### 16.2. Replay từ thời điểm broker enqueue

~~~java
import com.azure.messaging.eventhubs.models.EventPosition;
import java.time.Instant;

// Đoạn mã chèn vào một consumer đã tạo:
Instant start = Instant.parse("2026-11-20T03:00:00Z");
EventPosition position = EventPosition.fromEnqueuedTime(start);

// consumer.receiveFromPartition(partitionId, position)
//        .take(limit)
//        .subscribe(...);
~~~

**start** ở đây là thời điểm **enqueued time**, không phải event time trong JSON payload. Cần chọn thời điểm đủ sớm để bao gồm late arrivals cần backfill.

### 16.3. Tại sao replay nên có namespace output riêng?

Một pipeline replay có thể tạo:

~~~text
Production aggregates:
    sales_5m_current

Replay output:
    sales_5m_replay_20261120
~~~

Sau khi so sánh số lượng, checksum, schema và business rules, mới quyết định **atomic switch/merge** vào dữ liệu đang phục vụ theo khả năng của database/analytics sink.

Nếu replay ghi thẳng vào production output bằng INSERT không idempotent, doanh thu có thể bị tính hai lần.

## 17. Replay qua Event Hubs Capture hoặc archive

### 17.1. Khi retention không đủ

Nếu outage 5 ngày nhưng Event Hub chỉ lưu một khoảng ngắn hơn:

1. Dừng việc tự ý đặt checkpoint về một offset đã hết retention.
2. Xác định khoảng bị thiếu bằng checkpoint cuối, enqueued time và metrics.
3. Kiểm tra kho **Capture** hoặc nguồn lưu sự kiện gốc.
4. Xác minh dữ liệu archive có đủ partitions, thời gian và schema.
5. Chạy backfill từ archive vào **output riêng**, hoặc phát qua **Event Hub replay riêng**.
6. Đối chiếu số events/IDs theo phân vùng và thời gian.
7. Chuyển kết quả sau validation; có cơ chế bảo toàn khoảng giao nhau với streaming realtime.

### 17.2. Capture file format và bố trí lưu trữ

Event Hubs Capture thường ghi dữ liệu theo partition và time window vào Blob/ADLS, với định dạng/tính năng phụ thuộc cấu hình dịch vụ. Không giả định một file Capture là một tập JSON lines đơn giản; thường cần parser theo format được hỗ trợ như Avro hoặc cấu hình capture hiện hành.

Cần lưu:

- Hub/partition và thời gian capture.
- Enqueued time/sequence/offset metadata nếu pipeline cần.
- Event body/content type/properties.
- Schema version và định nghĩa serialization.
- Checksum/content hash.
- Quyền truy cập, retention và encryption.

### 17.3. Không phát lại dữ liệu mù quáng vào hub production

Nếu republish archived events vào **cùng hub production**, các events được gán **enqueued time/offset/sequence mới** và có thể kích hoạt mọi consumer đang hoạt động, gây tác dụng phụ như gửi email hoặc tính tiền lại.

Nếu bắt buộc republish, dùng một hub/consumer path riêng, gắn **replayRunId**, **originalEventId**, **originalEventTime** và xác minh sinks theo thiết kế. Các consumers có thể phải phân biệt replay traffic với traffic nghiệp vụ thực.

### 17.4. Kiểm soát tốc độ replay

Một backfill có thể đọc rất nhanh, nhưng output DB không chịu nổi. Giới hạn throughput của replay và ưu tiên realtime theo SLO:

~~~text
Realtime sink budget: 8.000 writes/s
Replay sink budget:   2.000 writes/s
Total target:        10.000 writes/s
~~~

Đây là phân bổ minh họa, không phải giới hạn Azure. Thực tế cần dynamic throttling, quan sát latency/429 và dừng replay nếu ảnh hưởng realtime.

## 18. Event time và event đến muộn

### 18.1. Event đến muộn là gì?

Một sự kiện **đến muộn theo event-time window** nếu hệ thống nhận hoặc xử lý nó **sau watermark/điều kiện đóng cửa sổ** đã được xác định, dù **eventTime** thuộc một cửa sổ cũ.

Không đánh đồng:

- **Late ingress:** eventTime rất cũ so với enqueuedTime vì nguồn gửi trễ.
- **Consumer lag:** event enqueued đúng giờ nhưng processor đọc trễ vì backlog.
- **Out-of-order arrival:** thứ tự event time không tăng đều theo thứ tự broker/processing.
- **Clock skew:** timestamp do nguồn gắn sai.
- **Replay:** cố tình đọc lại dữ liệu cũ.

Các nguyên nhân cần giải pháp khác nhau. Ví dụ tăng Streaming Units có thể giảm consumer lag nhưng **không sửa được đồng hồ của thiết bị IoT**.

### 18.2. Ví dụ bảng thời gian

| Event | eventTime (giờ VN) | enqueuedTime | processingTime | Ghi chú |
|---|---|---|---|---|
| A | 10:01 | 10:01:02 | 10:01:03 | Gần realtime |
| B | 10:04 | 10:04:01 | 10:04:02 | Gần realtime |
| C | 10:03 | 10:05:10 | 10:05:11 | Out-of-order nhưng trễ ít |
| D | 10:02 | 10:18:10 | 10:18:13 | Trễ lớn do offline |
| E | 10:17 | 10:17:01 | 10:21:40 | Consumer lag sau ingestion |

Để tổng hợp doanh thu từ 10:00 đến 10:05, cả A/B/C/D thuộc **cùng window theo event time**, còn E thuộc window khác. Tuy nhiên, chính sách watermark có thể khiến D đến **sau khi kết quả window đã công bố**.

## 19. Watermark là gì?

**Watermark** là một mốc event time mà hệ thống dùng để ước lượng rằng các sự kiện cũ hơn mốc đó **đã phần lớn đến đủ**, qua đó có thể đóng/tiến các windows. Nó là **quy tắc/ước lượng xử lý**, không phải tuyên bố chắc chắn mọi producer đã gửi đủ dữ liệu.

Một mô hình đơn giản cho **một stream có tiến độ ổn định**:

~~~text
watermark ≈ maxObservedEventTime - allowedOutOfOrderDelay
~~~

Ví dụ:

~~~text
Max event time đã thấy: 10:20
Allowed out-of-order:   3 phút
Watermark tham khảo:   10:17
~~~

Nhưng engine streaming thực tế có thể tính watermark theo partition, dữ liệu vào, event-time policy, idle source và các cơ chế phức tạp khác. **Đừng đưa công thức trên thành chính sách đúng trong mọi engine**.

### 19.1. Window kết thúc và watermark

Một **tumbling window** có khoảng:

~~~text
Window [10:00, 10:05)
    chứa events với:
    10:00 <= eventTime < 10:05
~~~

Khi watermark tiến qua ranh giới đóng của window theo engine, kết quả có thể được phát. Nếu event **eventTime=10:03** đến sau khi window đã đóng, cách xử lý phụ thuộc **late-event policy**.

### 19.2. Watermark và idle partition

Với nhiều partitions:

- Một partition ít traffic có thể không cung cấp event time mới.
- Một partition khác có thể nhận hàng nghìn events/s.
- Nếu engine đợi quá nghiêm khắc partition idle, watermark có thể đứng yên.
- Nếu engine tiến watermark dựa trên giả định idle quá nhanh, event đến sau có thể bị xem là late.

Các engine có idle-partition handling khác nhau. Phải thử cả dữ liệu bình thường lẫn trạng thái một partition ngừng gửi lâu.

### 19.3. Allowed lateness không giống retention

- **Allowed lateness:** cách pipeline xử lý event quá cũ so với tiến độ event-time/window.
- **Event Hubs retention:** broker giữ lịch sử để đọc lại.

Tăng retention không tự làm window chờ lâu hơn. Tăng allowed lateness không khôi phục event đã mất khỏi retention.

## 20. Các chiến lược xử lý late event

Không có chính sách duy nhất đúng cho mọi hệ thống.

| Chiến lược | Hành vi | Phù hợp | Trade-off |
|---|---|---|---|
| **Drop** | Bỏ event khỏi kết quả realtime, ghi lý do | Telemetry gần realtime chấp nhận sai số | Mất dữ liệu thống kê nếu không backfill |
| **Adjust timestamp** | Điều chỉnh timestamp theo policy engine | Dashboard cần kết quả gần realtime hơn event-time chính xác | Số liệu không còn phản ánh đúng lúc nghiệp vụ xảy ra |
| **Side output/quarantine** | Gửi event trễ tới kho riêng | Audit/điều tra hoặc manual review | Cần pipeline bù đắp |
| **Update/retract** | Phát bản cập nhật/correction cho window cũ | Tài chính/đo lường cần chính xác | Sink phải hỗ trợ upsert/version/retraction |
| **Recompute/backfill** | Chạy lại window/khoảng thời gian từ archive | Dữ liệu lịch sử cần nhất quán | Tốn compute, I/O và quy trình đối soát |
| **Late grace period** | Giữ window thêm một khoảng cho sự kiện trễ | Lateness có phân bố đo được | Tăng latency, state và memory |

### 20.1. Dashboard realtime và báo cáo tài chính cần chính sách khác

**Dashboard vận hành:** có thể chấp nhận kết quả sớm, rồi hiển thị trạng thái **provisional** và cập nhật sau.

**Báo cáo doanh thu/đối soát:** cần đúng event-time và audit trail; event đến muộn có thể yêu cầu điều chỉnh window lịch sử với version/transaction.

Không sử dụng **Adjust event time sang processing time** cho nghiệp vụ tài chính mà không ghi rõ hậu quả định nghĩa dữ liệu.

### 20.2. Đánh dấu kết quả tạm và kết quả cuối

Ví dụ output:

~~~json
{
  "storeId": "hcm-07",
  "windowStartUtc": "2026-11-20T03:00:00Z",
  "windowEndUtc": "2026-11-20T03:05:00Z",
  "revenue": 12500000,
  "revision": 3,
  "isFinal": false,
  "computedAtUtc": "2026-11-20T03:07:40Z"
}
~~~

Nếu một late event thay đổi tổng sau đó, processor có thể tạo **revision=4**. Sink cần upsert theo **storeId + windowStart + windowEnd**, so sánh revision để không ghi đè một kết quả mới bằng replay cũ.

**isFinal** là một hợp đồng nghiệp vụ, không phải lời hứa tuyệt đối rằng sẽ không có correction nào về sau. Nếu cần khóa sổ kế toán, thiết kế bước reconciliation và ledger riêng.

## 21. Azure Stream Analytics: event-time windowing

**Azure Stream Analytics (ASA)** là lựa chọn managed stream processing trên Azure có hỗ trợ truy vấn SQL-like, temporal/window functions và chính sách thứ tự sự kiện. Nó có thể đọc từ Event Hubs, xử lý windows và ghi ra output được hỗ trợ.

### 21.1. Query window cơ bản

Ví dụ dữ liệu input có trường **storeId**, **eventTimeUtc**, **amount**:

~~~sql
SELECT
    storeId,
    System.Timestamp() AS windowEndUtc,
    COUNT(*) AS eventCount,
    SUM(CAST(amount AS bigint)) AS totalAmount
INTO
    output
FROM
    input TIMESTAMP BY eventTimeUtc
GROUP BY
    storeId,
    TumblingWindow(minute, 5)
~~~

Ý nghĩa:

- **TIMESTAMP BY eventTimeUtc** chọn **event time trong payload**.
- **TumblingWindow(minute, 5)** nhóm các khoảng 5 phút không chồng lên nhau.
- **System.Timestamp()** cung cấp timestamp tương ứng kết quả window theo semantics của engine.
- **COUNT/SUM** tính số sự kiện và tổng số tiền theo cửa sổ.

**Phải kiểm tra schema và kiểu timestamp** mà ASA đang nhận. Nếu **eventTimeUtc** là chuỗi JSON, cần xác nhận format/serialization và việc engine parse thời gian, không tự giả định mọi string ISO 8601 đều tương thích với toàn bộ expression.

### 21.2. Chính sách event ordering

ASA cung cấp **event ordering policies** liên quan tới:

- **Late arrival tolerance**.
- **Out-of-order tolerance**.
- Cách xử lý như **Drop** hoặc **Adjust** theo policy được cấu hình.

Đây là hai vấn đề tách biệt:

| Chính sách | Nhắm tới | Câu hỏi |
|---|---|---|
| Late arrival | Event time cách quá xa enqueued time | Sự kiện đến broker trễ đến mức nào còn hợp lệ? |
| Out-of-order | Sự kiện event time đến lệch thứ tự cho phép | Engine sẽ giữ/điều chỉnh/bỏ qua như thế nào khi event time lùi? |

Khi cấu hình, phải xem ý nghĩa và giới hạn của từng setting trong **ASA job đang triển khai**; không mặc định hai ngưỡng cộng lại thành một “allowed lateness” đơn giản áp dụng cho mọi trường hợp.

### 21.3. Drop hay Adjust?

- **Drop:** một sự kiện vi phạm chính sách có thể bị bỏ khỏi output đã định.
- **Adjust:** timestamp dùng cho xử lý được điều chỉnh theo quy tắc của engine để nó có thể đi vào luồng xử lý.

Nếu dashboard cần phản ánh event-time thật, phải giải thích rõ khi nào điều chỉnh timestamp được chấp nhận. Với dữ liệu cần kiểm toán, dùng một đường **raw archive** và reconciliation thay vì chỉ giữ kết quả đã Adjust.

### 21.4. Watermark delay

**Watermark delay** phản ánh độ chậm của tiến độ event-time/output so với thời điểm hiện tại theo semantics của engine. Độ trễ này có thể tăng khi input bị trễ, partition idle, processing bottleneck hoặc policy cho phép lệch thứ tự lớn.

Một dashboard không có output không nhất thiết là “ASA bị treo”. Có thể window chưa đủ điều kiện đóng vì watermark chưa tiến. Kiểm tra metric watermark delay, input/output events, late/out-of-order events, errors và compute utilization trong Azure Monitor theo tài nguyên/tính năng hỗ trợ.

## 22. Thiết kế watermark cho dữ liệu nhiều nguồn

### 22.1. Nguồn có SLA lateness khác nhau

Ví dụ:

| Nguồn | Lateness thường gặp | Outage dài nhất kỳ vọng | Đề xuất |
|---|---|---|---|
| API datacenter | Giây | Vài phút | Low-latency window |
| POS cửa hàng | 1–2 phút | 30 phút | Grace period, correction |
| Mobile offline | 10–60 phút | Vài giờ | Raw store + late backfill |
| Đối tác định kỳ | Hàng giờ | Hàng ngày | Batch reconciliation riêng |

Nếu gộp tất cả vào một pipeline với watermark chờ lâu nhất, dashboard realtime có thể trễ quá mức. Nếu chỉ dùng watermark 30 giây, sự kiện từ mobile có thể bị loại thường xuyên.

Một giải pháp là **hai nhánh**:

~~~mermaid
flowchart TD
    INPUT["Event Hubs: raw events"] --> FAST["Realtime stream<br/>watermark ngắn"]
    INPUT --> RAW["Capture/ADLS raw archive"]
    FAST --> DASH["Provisional dashboard"]
    RAW --> LATE["Reconciliation / backfill<br/>window lịch sử"]
    LATE --> FINAL["Corrected aggregates + audit"]
    DASH --> FINAL
~~~

### 22.2. Chọn lateness từ dữ liệu thay vì cảm giác

Ghi nhận **ingestion lateness = enqueuedTime - eventTime** theo source, store, device type và percentile.

Ví dụ sau một tuần đo được:

~~~text
p50 lateness:       2 giây
p95 lateness:      35 giây
p99 lateness:      4 phút
p99.9 lateness:   25 phút
extreme outage:    vài giờ
~~~

Nếu SLO cho dashboard là cập nhật trong 60 giây, không nên giữ mọi window mở 25 phút. Có thể chọn **fast result trong 60 giây**, rồi **late correction/reconciliation** trong thời gian dài hơn.

### 22.3. Future timestamps

Event time có thể nằm **trong tương lai** vì thiết bị đồng hồ sai. Nếu blindly lấy maxObservedEventTime để tiến watermark, một future event có thể làm các window cũ bị đóng sớm và khiến sự kiện hợp lệ thành late.

Validation nên:

- So sánh eventTime với enqueuedTime và thời gian hệ thống.
- Giới hạn future skew theo chính sách.
- Quarantine event lỗi clock nghiêm trọng.
- Theo dõi tỷ lệ timestamp sai theo source.
- Không sửa timestamp gốc mà không lưu lý do/giá trị điều chỉnh.

## 23. End-to-end idempotency và state consistency

### 23.1. Key thiết kế dữ liệu đầu ra

Với event đơn lẻ, dùng **eventId** để deduplicate.

Với aggregate 5 phút, dùng **(storeId, windowStartUtc, metricVersion)** để xác định bản ghi tính toán; quản lý **revision** hoặc generation để xử lý correction.

Ví dụ SQL giả lập:

~~~sql
-- Mô hình khái niệm; cú pháp UPSERT cụ thể phụ thuộc database.
UPSERT INTO SalesWindow(
    storeId,
    windowStartUtc,
    windowEndUtc,
    metricVersion,
    revision,
    totalAmount
)
KEY (storeId, windowStartUtc, metricVersion)
ONLY IF incoming.revision > stored.revision;
~~~

Đây là **pseudocode SQL**, không phải cú pháp T-SQL chạy trực tiếp trên Azure SQL. Production phải dùng transaction/unique index/merge pattern phù hợp engine, kiểm tra concurrency và isolation.

### 23.2. At-least-once không đồng nghĩa double-count bắt buộc

Nếu same event được đọc lại, consumer có thể kiểm tra:

~~~text
BEGIN database transaction
    IF eventId chưa nằm trong ProcessedEvents:
        INSERT ProcessedEvents(eventId)
        UPDATE totals hoặc INSERT delta ledger
COMMIT database transaction

Sau DB commit thành công:
    checkpoint Event Hubs
~~~

Khi crash sau DB commit trước checkpoint, event được đọc lại nhưng **ProcessedEvents** ngăn cộng trùng.

Đối với tổng hợp window, có thể lưu **ledger theo eventId** hoặc tính lại từ raw data thay vì cộng bừa vào một counter không có đường đảo ngược.

### 23.3. Late correction và retraction

Một window đã công bố total=100 có thể nhận late event +20 rồi thành 120.

Nếu sink hỗ trợ **upsert**:

~~~text
(storeId, windowStart, revision=1, total=100)
(storeId, windowStart, revision=2, total=120)
~~~

Nếu downstream là hệ thống append-only, có thể phát:

~~~text
Correction:
    windowKey = ...
    adjustment = +20
    correctionId = unique
    originalRevision = 1
    newRevision = 2
~~~

Consumer nhận correction phải idempotent và xử lý thứ tự version. Không có một dạng correction phù hợp cho mọi sink; financial ledger thường cần record điều chỉnh có audit trail, không overwrite im lặng.

### 23.4. Trạng thái replay không được ghi đè bản mới

Nếu backfill của phiên bản thuật toán cũ hoàn tất sau realtime algorithm v2, một bản ghi replay có thể ghi đè output đúng thành sai.

Giải pháp:

- Gắn **runId**, **algorithmVersion**, **generation/revision**.
- Dùng output staging/versioned.
- Kiểm tra source range và dữ liệu đã xử lý.
- Chuyển output bằng transaction/atomic pointer switch theo khả năng sink.
- Chỉ cho generation được phê duyệt trở thành current.
- Giữ audit record và khả năng rollback.

## 24. Khi nào backpressure biến thành data-loss risk?

Event Hubs giữ dữ liệu theo retention. Nếu consumer quá chậm trong thời gian dài, sự kiện cũ sẽ không còn trong log trước khi được đọc.

### 24.1. Retention budget

Đặt:

- **R**: retention thực tế.
- **T_outage**: thời gian pipeline ngừng.
- **T_catchup**: thời gian cần để xử lý backlog.
- **T_margin**: biên an toàn cho retries, maintenance và biến động.

Điều kiện thiết kế thô:

~~~text
R > T_outage + T_catchup + T_margin
~~~

Đây là **ràng buộc hoạch định**, không phải cam kết tuyệt đối; retention thực tế của từng event và cách dịch vụ áp dụng cần được kiểm tra. Nếu T_outage + T_catchup gần R, khả năng mất dữ liệu tăng.

### 24.2. Ví dụ rủi ro

Một pipeline ngừng **8 giờ**, sau đó cần **10 giờ** để bắt kịp. Nếu retention được cấu hình ngắn hơn tổng thời gian này, những events đầu có thể hết hạn trước khi consumer đọc tới.

Các lựa chọn:

1. Tăng throughput thực tế để rút ngắn catch-up.
2. Tăng retention **nếu tier/quota/chi phí cho phép**.
3. Bật Capture/archive trước khi gặp sự cố.
4. Xây pipeline backfill từ nguồn gốc.
5. Hạn chế bớt workload replay cạnh tranh với realtime.
6. Có cảnh báo **estimated time to retention boundary**, không chỉ CPU.

### 24.3. Không coi lag một con số toàn hệ thống

Một partition có thể sắp vượt retention dù lag trung bình trông ổn. Cần đo:

- Max lag theo partition.
- Oldest unprocessed event age.
- Last successful checkpoint time.
- Gap giữa last enqueued và last processed sequence.
- Event time skew theo source.
- Time-to-catch-up dựa trên headroom hiện tại.

## 25. Azure Functions Event Hubs trigger và backpressure

**Azure Functions Event Hubs trigger** có cơ chế scale và checkpointing/leases theo extension và host configuration. Nó có thể phù hợp cho workloads nhỏ hoặc event-driven processing không muốn tự vận hành EventProcessorClient.

Tuy nhiên:

- Scale-out còn phụ thuộc partitions, plan và runtime.
- Invocation/concurrency, batch size, prefetch, checkpoint behavior phụ thuộc version extension.
- Nếu downstream chậm, tăng Functions instances không tự làm DB nhanh hơn.
- Function retries có thể dẫn đến xử lý trùng.
- Cần kiểm tra timeout, host restarts và checkpoint ownership.
- Event Hubs là stream; không có DLQ per event tự động giống Service Bus queue.

### 25.1. Chọn Functions hay Java worker lâu dài?

| Tiêu chí | Azure Functions trigger | Java App Service/AKS worker |
|---|---|---|
| Quản lý infrastructure | Ít tự quản hơn | Cần quản lý app/containers/scale |
| Checkpoint/trigger | Runtime và extension quản lý | Tự cấu hình EventProcessor/checkpoint store |
| Concurrency/batch | Theo host settings, extension, plan | Linh hoạt trong code nhưng phải kiểm soát |
| Network/identity | Tùy Functions hosting plan | Tùy App Service/AKS network |
| Late-event logic | Cần implement hoặc gọi engine khác | Có thể dùng Java libraries/ASA |
| Phù hợp | Event-driven workloads đơn giản | Long-running, xử lý tùy chỉnh, latency/concurrency đặc thù |

Không copy bừa **host.json** từ một extension version khác. Khi chỉnh checkpoint/batch settings phải đọc tài liệu của **Event Hubs extension** đúng phiên bản đang chạy.

## 26. Monitoring và cảnh báo

### 26.1. Các nguồn quan sát

| Thành phần | Tín hiệu | Dùng để |
|---|---|---|
| Event Hubs | Incoming/Outgoing Messages/Bytes | Đo traffic và capacity |
| Event Hubs | Throttled requests, server/user errors | Nhận biết quota/auth/network problems |
| Consumer SDK | Events processed/s, processing latency | So sánh μ với λ |
| Consumer SDK | Checkpoint age và last processed position | Phát hiện lag/crash |
| Consumer SDK | Ownership rebalance/lease errors | Tìm bất ổn load balancing |
| Blob checkpoint store | Blob API errors/latency/throttling | Phát hiện checkpoint/ownership store là nút thắt |
| Downstream DB | 429/5xx, write latency, pool saturation | Xác định sink backpressure |
| Stream Analytics | Input/Output Events, Watermark Delay | Chẩn đoán event-time latency |
| Stream Analytics | Late/Out-of-order events, conversion errors | Kiểm tra policy dữ liệu |
| Capture/Storage | Capture status, archive completeness | Khả năng replay lâu dài |
| Azure Monitor | Alerts, Log Analytics, diagnostics | Vận hành và audit |
| Cost Management | Event Hubs tier/capacity, storage, compute | Dự toán và tối ưu |

Tên metric cụ thể có thể thay đổi theo resource type/tier/phiên bản. Không giả định một metric **consumer lag** đã được Event Hubs broker đo sẵn cho **mọi consumer group**; consumer cần xuất telemetry/checkpoint progress và đối chiếu partition last-enqueued.

### 26.2. Dashboard tối thiểu

Một dashboard hữu ích cần:

~~~text
Ingress rate (events/s)
Processing completion rate (events/s)
Backlog / lag max + p95 by partition
Oldest unprocessed event age
Last successful checkpoint per partition
Consumer error and retry rate
Downstream p95/p99 write latency
Late event ratio by source
Watermark delay and window correction rate
Remaining replay/retention safety margin
Capture health / archive gap
Total cost by component
~~~

### 26.3. Alert theo hành động

Không tạo 20 alerts chung chung chỉ dựa CPU. Gắn từng cảnh báo với runbook:

| Alert | Đề xuất hành động |
|---|---|
| Lag tăng liên tục 10–15 phút | So sánh λ/μ, xác định partition nóng và sink bottleneck |
| Throttled requests tăng | Kiểm tra TU/PU, send batch, retry và quota |
| Checkpoint không tiến | Kiểm tra processor ownership, Blob storage, exceptions |
| Oldest event age gần retention | Ưu tiên tăng μ, mở backfill/retention incident |
| Watermark delay tăng | Kiểm tra event-time skew, idle partition, ASA job |
| Late events tăng từ một store | Kiểm tra kết nối/clock của store |
| Replay làm DB latency tăng | Giảm/dừng replay budget |
| Capture có khoảng thiếu | Điều tra và lưu nguồn gốc trước khi hết retention |

Số phút và threshold phải dựa trên SLO, traffic bình thường, retention và môi trường; không dùng các ngưỡng minh họa như chuẩn Azure mặc định.

## 27. Xử lý sự cố thực tế

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Consumer memory tăng liên tục | Queue/in-flight unbounded | Giới hạn buffer/concurrency và kiểm tra GC |
| Lag chỉ tăng ở một partition | Hot key, per-partition bottleneck | Kiểm tra partition distribution và processing pipeline |
| Tăng replicas nhưng lag không giảm | Quá số partitions, DB bottleneck | Kiểm tra ownership và throughput downstream |
| Checkpoint tiến nhưng dữ liệu thiếu | Checkpoint trước durable sink | Sửa thứ tự; replay từ raw/retained data để phục hồi |
| Dữ liệu bị cộng hai lần sau restart | At-least-once delivery, sink không idempotent | Dedupe eventId/unique index, correction |
| Replay không có event cũ | Hết Event Hubs retention | Đọc Capture/archive/source, không seek offset đã mất |
| Replay làm dashboard sai | Ghi thẳng production, không version | Dùng output riêng/atomic promote |
| Window 10:00–10:05 thiếu event đến 10:18 | Event-time late, window đã đóng | Late policy, correction/reconciliation |
| Watermark không tiến | Idle partition, out-of-order tolerance lớn | Kiểm tra engine watermark/partition logic |
| Timestamp tương lai gây sai window | Producer clock skew | Validate/quarantine, thiết kế future skew |
| ASA output bị trễ | Backpressure, watermark delay, SU utilization | Metrics/input partitions/sink capacity/policy |
| Producer 429/throttling | Event Hubs capacity/quota | Rate limit, backoff, capacity planning |
| Consumer 403 | Data Receiver/Storage RBAC sai | Kiểm tra identity/role/scope và propagation |
| Blob checkpoint store lỗi | Storage auth/network/lease/throttle | Check Blob role, private DNS, container |
| Capture không có file kỳ vọng | Chưa bật/điều kiện ghi, permission/network | Kiểm tra capture settings và archive paths |
| Consumer group replay ảnh hưởng realtime | Dùng chung ownership/checkpoint | Tách consumer group/checkpoint và output |

### 27.1. Debug lag trong 10 bước

1. Đo **incoming events/s** theo partition nếu có.
2. Đo **completed processing events/s**, không chỉ receive rate.
3. Xác nhận throughput sink và tỷ lệ lỗi.
4. Tìm partition lag lớn nhất.
5. Kiểm tra phân phối partition key và hot source.
6. Kiểm tra GC/memory/in-flight, bounded queues.
7. Kiểm tra Blob checkpoint success và ownership rebalance.
8. Kiểm tra throttled requests và capacity Event Hubs.
9. Ước lượng **T_catchup** và retention safety margin.
10. Thử thay đổi nhỏ trong staging, đo lại và chỉ scale theo bottleneck.

### 27.2. Debug late-event spike

1. Lấy eventTime, enqueuedTime, processingTime và source ID.
2. Tính lateness theo từng đoạn: **producer→broker**, **broker→consumer**.
3. Kiểm tra clock skew/timezone.
4. Xem source có offline/buffer/retry không.
5. Xem consumer lag hay stream processor bị chậm.
6. Kiểm tra watermark/event ordering policies.
7. Xác định window đã đóng hay có thể cập nhật.
8. Chọn late-correction/quarantine/replay theo business SLA.
9. Đo lại số liệu đúng và audit các thay đổi.
10. Thêm cảnh báo theo source thay vì chỉ cảnh báo tổng toàn hệ thống.

### 27.3. Debug replay làm tăng chi phí

1. Kiểm tra replay đang đọc broker hay Capture/ADLS.
2. Kiểm tra khoảng thời gian, số partitions và volume.
3. Kiểm tra số lần đọc lặp/consumer groups.
4. Kiểm tra sink writes/egress và retry.
5. Kiểm tra ingestion/egress giữa regions.
6. Xác nhận replay có giới hạn throughput và deadline.
7. Giảm/dừng replay khi ảnh hưởng realtime.
8. Đối chiếu Cost Management theo resource/meter khi dữ liệu cập nhật.
9. Cân nhắc recompute chỉ windows bị ảnh hưởng thay vì toàn bộ lịch sử.
10. Ghi nhận cost/run và số records corrected.

## 28. Chi phí, bảo mật và ranh giới vận hành

### 28.1. Chi phí tổng

| Thành phần | Điểm phát sinh chi phí |
|---|---|
| Event Hubs | Tier/capacity, throughput/processing units và retention theo model |
| Capture | Storage data, transactions và retention lifecycle |
| Consumer App Service/AKS/Functions | CPU/memory, instance count, execution theo mô hình |
| Blob checkpoint store | Storage và Blob transactions |
| Azure Stream Analytics | Streaming Units/compute và input/output theo cấu hình |
| Azure Data Explorer / SQL / Cosmos DB | Ingestion, storage, writes, queries hoặc throughput |
| Data egress | Khi có truyền dữ liệu giữa region/zone/Internet tùy dịch vụ |
| Azure Monitor | Log ingestion, retention, alerts |
| Replay/backfill | Compute, data scans, read/write và áp lực lên sink |

Không có đơn giá chung “một message = X” cho mọi dịch vụ/tier. Cần dùng Azure Pricing Calculator và dữ liệu Cost Management hiện hành.

### 28.2. Phân quyền

- Producer chỉ cần **Azure Event Hubs Data Sender**.
- Consumer chỉ cần **Azure Event Hubs Data Receiver**.
- Checkpoint identity có quyền Blob data phù hợp, không dùng storage account key khi có thể.
- Capture/access archive có quyền đọc/ghi riêng theo thiết kế.
- Replay operator không tự có quyền ghi dữ liệu production; dùng output staging.
- Quyền Azure resource management và data-plane không giống nhau.

### 28.3. Network

Các thành phần có thể dùng VNet/private endpoints theo tier/region và khả năng hỗ trợ:

- Event Hubs namespace.
- Storage checkpoint/Archive.
- Database/ADX/ASA outputs.
- App Service/AKS/Functions integration.
- Azure Monitor/diagnostics đường gửi logs.

Kiểm tra TLS, DNS, routing, firewall, AMQP/TCP hoặc WebSockets khi phù hợp. Không mở public access cho toàn bộ namespace/storage chỉ để xử lý một lỗi kết nối chưa được chẩn đoán.

### 28.4. Dữ liệu và compliance

- Ghi rõ event schema và retention classification.
- Không đưa thông tin cá nhân nhạy cảm vào partition key, MessageId hoặc logs nếu không cần.
- Có chính sách xóa/archive và access tới dữ liệu lịch sử.
- Replay có thể tái áp dụng dữ liệu đã được yêu cầu xóa; cần cơ chế xử lý privacy compliance theo tổ chức.
- Ngăn replay kích hoạt tác dụng phụ không mong muốn như thanh toán, email.
- Dùng encryption, Azure RBAC, audit và kiểm soát nguồn image/code.
- Có owner phê duyệt replay của dữ liệu production.

## 29. Checklist thiết kế production

- [ ] Đã phân biệt event time, enqueued time và processing time trong schema/telemetry.
- [ ] Partition key phân phối đủ đều và bảo đảm mức ordering nghiệp vụ cần thiết.
- [ ] Đã xác nhận số partitions, tier, capacity và retention thực tế của Event Hub.
- [ ] Có dự toán peak ingest λ và sustained processing μ.
- [ ] Backpressure có bounded queues, in-flight limits, retry/backoff và circuit breaker.
- [ ] Không tăng concurrency vô hạn khi sink bị throttling.
- [ ] Có metrics lag theo partition, checkpoint age và oldest unprocessed event.
- [ ] Checkpoint chỉ được cập nhật sau durable, idempotent output.
- [ ] Không checkpoint vượt một event thất bại chưa được xử lý/quarantine đúng policy.
- [ ] Có quy trình phân biệt poison events với transient errors.
- [ ] Consumer groups và Blob checkpoint stores được tách theo mục đích.
- [ ] Replay có runId, time range, isolated output, rate limit và validation.
- [ ] Có Capture/archive hoặc cơ chế source replay nếu cần dữ liệu ngoài retention.
- [ ] Có kiểm tra eventId và upsert/retraction để replay không double-count.
- [ ] Có chính sách allowed lateness, watermark và late-event handling theo dữ liệu đo.
- [ ] Có cách xử lý timestamp sai, future clock skew và idle partition.
- [ ] ASA hoặc engine khác được cấu hình event ordering policies đúng nhu cầu.
- [ ] Aggregate có window key, algorithm version/revision và audit trail.
- [ ] Có alert retention risk, watermark delay, hot partition, checkpoint failures.
- [ ] Có least privilege và network/DNS riêng cho Event Hubs/Storage/sink.
- [ ] Có runbook khôi phục khi consumer outage, replay failure và downstream outage.
- [ ] Có ước tính chi phí cho Event Hubs capacity, Capture, compute, logs và replay.
- [ ] Đã diễn tập crash **sau sink commit nhưng trước checkpoint**.
- [ ] Đã kiểm thử dữ liệu đến muộn sau window close và phát hành correction.

## 30. Bài tập thực hành

### Bài 1: Tính backpressure

Event Hubs nhận 10.000 events/s. Một sink chỉ xử lý 6.000/s trong 15 phút.

1. Tính backlog tăng.
2. Nếu sink tăng lên 14.000/s và tốc độ vào giữ 10.000/s, cần bao lâu để catch up theo mô hình lý tưởng?
3. Vì sao một partition nóng có thể khiến dự toán sai?
4. Nếu retention ngắn hơn outage + catch-up, kế hoạch phục hồi là gì?

### Bài 2: Thiết kế Java consumer

Với EventProcessorClient:

1. Định nghĩa consumer group và Blob checkpoint store.
2. Ghi rõ identity và quyền Event Hubs/Blob cần thiết.
3. Giới hạn tối đa 16 requests đồng thời tới database.
4. Ghi output idempotent theo eventId.
5. Chỉ checkpoint sau durable commit.
6. Cho biết cách xử lý event N thất bại nhưng N+1 xử lý xong.
7. Mô phỏng crash sau DB commit trước checkpoint.

### Bài 3: Hot partition

Dữ liệu theo storeId, một cửa hàng lớn phát 60% traffic. Cluster có 12 pods nhưng Event Hub chỉ có 4 partitions.

- Vì sao scale-out thêm pods chưa chắc giúp?
- Làm sao đo hot partition?
- Có thể đổi partition key như thế nào nếu vẫn cần ordering theo orderId?
- Tại sao phải thử migration ở consumer/output?

### Bài 4: Replay sự kiện lịch sử

Một bug khiến consumer tính doanh thu gấp đôi trong 3 giờ gần nhất.

1. Xác định data range theo event time và enqueued time.
2. Tạo consumer group/checkpoint store riêng.
3. Replay từ Event Hubs nếu còn retention.
4. Ghi output vào bảng versioned.
5. So sánh checksum/counts và khóa version.
6. Áp dụng correction vào production mà không gửi email/thanh toán lại.

### Bài 5: Dữ liệu vượt retention

Consumer ngừng 2 ngày nhưng retention thực tế không bao phủ đủ khoảng này.

- Dữ liệu nào có thể đã mất khỏi broker?
- Đọc Capture như thế nào?
- Vì sao không chỉ đặt offset lại?
- Nếu republish, cần gì để tránh kích hoạt consumers production?
- Làm sao đối soát khoảng trùng giữa realtime và backfill?

### Bài 6: Watermark và event-time

Một window 10:00–10:05 có các events:

~~~text
Event A: eventTime 10:01, xử lý 10:01
Event B: eventTime 10:04, xử lý 10:05
Event C: eventTime 10:03, xử lý 10:06
Event D: eventTime 10:02, xử lý 10:18
~~~

1. Event nào thuộc window nếu xét event time?
2. Vì sao C có thể hợp lệ với out-of-order tolerance nhưng D bị xem là late?
3. Với dashboard realtime, chọn output provisional/correction ra sao?
4. Với báo cáo tài chính, làm sao sửa tổng đúng mà vẫn giữ audit?
5. Nếu đồng hồ thiết bị nhảy tới 11:00 trong khi giờ thật là 10:00, watermark có thể bị ảnh hưởng thế nào?

### Bài 7: So sánh Azure Stream Analytics với consumer Java

Thiết kế cùng một tumbling window 5 phút:

- ASA dùng TIMESTAMP BY, event ordering policies và output adapter.
- Java tự quản window state, watermark, checkpoint và idempotent sink.

So sánh gánh nặng vận hành, kiểm soát logic, khả năng correction, monitoring và chi phí. Trong trường hợp nào nên chọn Spark/ADX hoặc batch reconciliation thêm?

### Bài 8: Thiết kế FinOps cho replay

Một đợt backfill 7 ngày cần đọc 500 triệu events từ archive.

- Ước lượng khối lượng dữ liệu từ average event size.
- Tách phí read, compute, sink writes, log, network.
- Đặt replay budget không ảnh hưởng realtime.
- Làm sao dừng và tiếp tục backfill theo runId/chunk checkpoint?
- Những KPI nào chứng minh đã hoàn thành đúng và không double-count?

### Câu hỏi tự kiểm tra

1. Event Hubs có xóa event khi consumer đọc không?
2. Checkpoint được dùng để làm gì?
3. Offset/sequence number có thứ tự toàn cục giữa partitions không?
4. Nếu λ > μ trong thời gian dài, tăng buffer vô hạn giải quyết vấn đề không?
5. Vì sao cần đo lag theo partition thay vì chỉ đo tổng?
6. Scale nhiều workers hơn partitions có luôn cải thiện throughput không?
7. Khi DB write 429, nên tăng consumer concurrency hay giới hạn nó?
8. Vì sao checkpoint trước durable sink có thể gây mất xử lý?
9. Tại sao checkpoint sau durable sink có thể tạo xử lý trùng?
10. Event Hubs có DLQ/settlement per-message như Service Bus không?
11. Consumer group mới có đọc được event đã vượt retention không?
12. Replay nên dùng chung checkpoint store với realtime không?
13. EventPosition theo enqueued time có giống filter theo event time không?
14. Capture có giúp lưu dữ liệu lịch sử dài hơn retention không?
15. Replay archived events vào hub production có rủi ro gì?
16. Watermark có bảo đảm chắc chắn không còn event cũ không?
17. Allowed lateness có giống retention không?
18. Future timestamp ảnh hưởng watermark ra sao?
19. Vì sao một partition idle có thể làm window output trễ?
20. Late event sau khi window đã công bố phải được xử lý theo những chiến lược nào?
21. ASA late arrival policy và out-of-order policy có hoàn toàn giống nhau không?
22. Vì sao upsert theo window revision giúp tránh dữ liệu cũ ghi đè bản mới?
23. Làm sao thiết kế sink idempotent để replay không double-count?
24. Khi nào nên dùng Data Lake backfill thay vì Event Hubs replay?
25. Nếu dashboard phải trả kết quả trong 60 giây nhưng mobile events có thể trễ 1 giờ, nên tách hai nhánh xử lý thế nào?

## 31. Tài liệu tham khảo

- [Azure Event Hubs overview — Microsoft Learn](https://learn.microsoft.com/azure/event-hubs/event-hubs-about)
- [Event Hubs features and terminology](https://learn.microsoft.com/azure/event-hubs/event-hubs-features)
- [Event Hubs event processors and checkpointing](https://learn.microsoft.com/azure/event-hubs/event-processor-balance-partition-load)
- [Event Hubs availability and consistency](https://learn.microsoft.com/azure/event-hubs/event-hubs-availability-and-consistency)
- [Event Hubs Capture](https://learn.microsoft.com/azure/event-hubs/event-hubs-capture-overview)
- [Event Hubs quotas and limits](https://learn.microsoft.com/azure/event-hubs/event-hubs-quotas)
- [Azure SDK for Java — Event Hubs client library](https://learn.microsoft.com/java/api/overview/azure/messaging-eventhubs-readme)
- [EventProcessorClient Java API](https://learn.microsoft.com/java/api/com.azure.messaging.eventhubs.eventprocessorclient)
- [BlobCheckpointStore Java API](https://learn.microsoft.com/java/api/com.azure.messaging.eventhubs.checkpointstore.blob.blobcheckpointstore)
- [Azure Stream Analytics introduction](https://learn.microsoft.com/azure/stream-analytics/stream-analytics-introduction)
- [Azure Stream Analytics event ordering policies](https://learn.microsoft.com/azure/stream-analytics/event-ordering-policies)
- [Azure Stream Analytics time handling](https://learn.microsoft.com/azure/stream-analytics/stream-analytics-time-handling)
- [Azure Stream Analytics TIMESTAMP BY](https://learn.microsoft.com/stream-analytics-query/timestamp-by-azure-stream-analytics)
- [Azure Stream Analytics window functions](https://learn.microsoft.com/stream-analytics-query/windowing-azure-stream-analytics)
- [Azure Functions Event Hubs trigger](https://learn.microsoft.com/azure/azure-functions/functions-bindings-event-hubs-trigger)
- [Azure Event Hubs pricing](https://azure.microsoft.com/pricing/details/event-hubs/)
- [Azure Stream Analytics pricing](https://azure.microsoft.com/pricing/details/stream-analytics/)

