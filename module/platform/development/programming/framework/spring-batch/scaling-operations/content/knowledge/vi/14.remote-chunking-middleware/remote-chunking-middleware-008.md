# Backlog của middleware trong Spring Batch Remote Chunking

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích **backlog** trong remote chunking là gì, hình thành ở đâu và vì sao queue sâu chưa chắc đồng nghĩa throughput cao.
- Phân biệt request backlog, message đang được giao cho worker, backlog retry/Dead Letter Queue (DLQ) và backlog kết quả trả về manager.
- Dùng tốc độ đưa vào (`λ`), tốc độ xử lý hữu ích (`μ`), dung lượng message và thời gian chờ để tính tốc độ tăng backlog, thời gian xả hàng đợi và nhu cầu lưu trữ.
- Chọn giới hạn số chunk đang bay, số consumer, prefetch, batch/chunk size, timeout và cơ chế backpressure dựa trên năng lực thật của DB, CPU và broker.
- Thiết kế ack, retry, idempotency và restart sao cho message bị giao lại không gây side effect trùng.
- Xây dựng dashboard, cảnh báo và bài kiểm thử tải cho Spring Batch Remote Chunking trên một hoặc nhiều máy.

## 1. Bối cảnh: manager nhanh hơn worker

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, remote chunking giúp mở rộng một bước xử lý khi **manager** đọc dữ liệu và gửi các chunk qua middleware, còn **remote worker** thực hiện phần xử lý/ghi chunk. Middleware có thể là broker như RabbitMQ hoặc Kafka, kết hợp các kênh giao tiếp do Spring Integration cấu hình.

Giả sử manager đọc dữ liệu từ DB với tốc độ 18.000 item/s. Mỗi chunk có 100 item, nên manager có thể tạo khoảng **180 chunk request/s**. Phía worker có tổng năng lực ổn định chỉ **120 chunk/s** vì writer đang bị giới hạn I/O. Chênh lệch 60 chunk/s sẽ tích lũy thành backlog nếu manager tiếp tục gửi không giới hạn.

~~~mermaid
flowchart LR
    S["Reader tại manager"] --> C["Tạo chunk request"]
    C --> Q["Middleware: request backlog"]
    Q --> W1["Worker 1: process + write"]
    Q --> W2["Worker 2: process + write"]
    Q --> WN["Worker N"]
    W1 --> R["Reply channel / result"]
    W2 --> R
    WN --> R
    R --> M["Manager: theo dõi hoàn tất"]
    Q -. "Redelivery / retry / DLQ" .-> E["Error handling"]
~~~

**Một điểm cốt lõi:** remote chunking **khác remote partitioning**. Trong remote chunking, manager sở hữu reader và gửi các **chunk đã đọc** tới worker; trong remote partitioning, manager gửi **miền dữ liệu** và worker thường sở hữu reader riêng. Vì vậy, backlog remote chunking chủ yếu là thông điệp chunk/result, không phải tự động là số partition đang chờ.

Thời điểm một message được coi là xử lý xong phụ thuộc cấu hình transport, worker transaction, acknowledgement và reply. Việc manager **gửi thành công vào broker** không đồng nghĩa chunk đã được ghi bền vững hoặc toàn bộ `StepExecution` đã hoàn tất.

## 2. Backlog chính xác gồm những gì?

Có ít nhất bốn vùng cần quan sát:

| Vùng | Định nghĩa | Điểm dễ hiểu nhầm |
| --- | --- | --- |
| **Request ready backlog** | Chunk request đã ở broker nhưng chưa được worker nhận/claim | Không tính chunk đã giao nhưng worker chưa ack |
| **In-flight / unacked** | Request đã giao tới worker nhưng chưa được xác nhận theo semantics transport | Queue “ready = 0” vẫn có thể đang kẹt rất nhiều chunk |
| **Retry / delayed / DLQ** | Request lỗi đang đợi retry hoặc bị cách ly để vận hành | DLQ không phải là “đã xử lý thành công” |
| **Reply/result backlog** | Kết quả worker đã phát nhưng manager chưa nhận/áp dụng | Writer có thể hoàn tất nhưng manager chưa biết, gây timeout hoặc job treo |

Cần phân biệt **số message** và **số đơn vị nghiệp vụ**. Một message có thể chứa 100, 1.000 hoặc số item thực tế ít hơn vào chunk cuối. `queueDepth = 200` không thể quy đổi thành chính xác `20.000 item` nếu size mỗi chunk biến động.

Một cách quan sát tổng quan hữu ích:

~~~text
Outstanding requests ≈
    queued requests chưa giao
  + requests đang xử lý/chờ ack
  + requests đang retry/delay
  + requests chưa có kết quả được manager xác nhận

Chú ý: các nhóm có thể trùng nhau trong một số middleware,
nên không được cộng số liệu từ các dashboard khác semantics
mà không định nghĩa tập đếm rõ ràng.
~~~

Để có một số **outstanding chunk duy nhất**, ứng dụng có thể theo dõi trạng thái theo `(jobExecutionId, stepExecutionId, chunkSequence)` hoặc một correlation key ổn định, chỉ đếm một lần mỗi chunk đang chờ hoàn tất. Đừng cộng raw delivery count (bao gồm redelivery) rồi cho là số chunk mới.

### Queue length không phản ánh toàn bộ độ trễ

- Request có thể nằm trong broker rất lâu mà worker không lấy được do thiếu consumer.
- Worker đã fetch/prefetch message nhưng đang chờ JDBC connection; broker ready queue giảm nhưng end-to-end latency vẫn cao.
- Worker đã commit dữ liệu nhưng reply bị chặn; request backlog có thể thấp trong khi manager vẫn chưa hoàn tất step.
- Retry nhanh khiến broker có nhiều lượt delivery nhưng số business item duy nhất hoàn tất tăng rất chậm.

Do đó phải đo **tuổi của message cũ nhất**, latency từ lúc gửi tới lúc worker hoàn tất và latency từ lúc gửi tới khi manager **xác nhận kết quả**, ngoài queue depth.

## 3. Mô hình tốc độ vào, ra và tăng backlog

Đặt:

- `λ`: tốc độ sinh **request chunk mới** từ manager, tính bằng chunk/s.
- `μ`: tốc độ worker hoàn tất **chunk hữu ích duy nhất** ở trạng thái bền vững, tính bằng chunk/s.
- `B(t)`: số chunk hữu ích đang tồn đọng ở thời điểm `t` (theo định nghĩa đếm thống nhất).
- `Δt`: khoảng thời gian đo bằng giây.

Nếu tốc độ tương đối ổn định và chưa xét message cần retry:

~~~text
ΔB ≈ (λ − μ) × Δt                 khi λ > μ

B(t + Δt) ≈ max(0, B(t) + (λ − μ) × Δt)
~~~

Đây là mô hình lưu lượng **trung bình**. Thực tế tốc độ có thể biến động mạnh theo kích thước chunk, dữ liệu khó, DB lock và thời gian GC. Khi `λ = μ`, backlog cũ **không tự giảm**; khi `λ < μ`, hệ thống mới có năng lực xả backlog.

### Ví dụ: 180 chunk/s đi vào, chỉ 120 chunk/s ra

Trong 5 phút (`300 s`):

~~~text
λ = 180 chunk/s
μ = 120 chunk/s
Δt = 300 s

Backlog tăng thêm = (180 − 120) × 300
                  = 18.000 chunk

Nếu chunk có trung bình 100 item:
18.000 chunk ≈ 1.800.000 item đang chờ
~~~

Nếu manager **ngừng gửi** và worker vẫn xử lý được 120 chunk/s:

~~~text
T_drain = B / μ = 18.000 / 120 = 150 s = 2,5 phút
~~~

Nếu manager giảm nhưng vẫn gửi 100 chunk/s:

~~~text
T_drain = B / (μ − λ)
        = 18.000 / (120 − 100)
        = 900 s = 15 phút
~~~

Điều kiện để dùng công thức xả backlog: `μ > λ`, dữ liệu tương đối đồng nhất và không có những retry/lock làm giảm tốc độ hữu ích. Nếu tiếp tục gửi `λ >= μ`, thời gian xả backlog hữu hạn **không tồn tại** theo mô hình này.

### Dùng định luật Little khi hệ thống ổn định

Trong trạng thái ổn định, định luật Little:

~~~text
L ≈ λ_completed × W

L             = số chunk trung bình trong một giai đoạn
λ_completed   = tốc độ chunk hoàn tất hữu ích/s
W             = thời gian trung bình chunk ở giai đoạn đó
~~~

Ví dụ worker hoàn tất bền vững 120 chunk/s và tổng thời gian chờ + xử lý ở pha đang xét trung bình 8 giây, thì số chunk trung bình ở pha này khoảng `120 × 8 = 960`. Đây là **mô hình kỳ vọng**, không phải quota cứng hay đo p99. Để chọn dung lượng hàng đợi và timeout, phải quan sát burst, phân vị latency và cơ chế consumer cụ thể.

## 4. Backlog còn chiếm byte, disk và network

Một broker không chứa “chunk count” trừu tượng: nó vận chuyển message đã serialize, thường có header, metadata, payload item và thông tin correlation.

Gọi `s` là kích thước message request trung bình:

~~~text
Payload backlog bytes ≈ B_ready × s

Dung lượng thực cần dự trù còn phụ thuộc:
- Header, index, metadata, lưu trữ/replication của broker
- Retry/delay/DLQ và các bản sao message khi chuyển queue
- Persistence, compression, page cache, checkpoint/offset log
- Retention, compaction, giới hạn đĩa, quota network
~~~

Ví dụ backlog 18.000 message, mỗi message đã serialize trung bình **128 KiB**:

~~~text
18.000 × 128 KiB = 2.304.000 KiB
                  = 2.250 MiB
                  ≈ 2,20 GiB payload
~~~

Nếu broker giữ nhiều replica hoặc có retention, chi phí lưu trữ thực tế có thể cao hơn; **không nhân một hệ số cố định cho mọi middleware**. Với Kafka, dữ liệu được lưu trong log theo partition/retention và “lag” không đơn giản đồng nghĩa một bản copy mới cho mỗi consumer. Với RabbitMQ, ready/unacked và persistence có semantics khác.

### Chunk size là đánh đổi ba chiều

| Tăng chunk size | Điểm có thể cải thiện | Điểm có thể xấu đi |
| --- | --- | --- |
| Ít message hơn cho cùng số item | Giảm số lần publish/ack/serialization header | Mỗi message lớn hơn, có thể vượt max size |
| Nhiều item mỗi lần ghi | JDBC batch/commit amortization tốt hơn | Worker giữ transaction/lock/bộ nhớ lâu hơn |
| Ít request để theo dõi | Giảm overhead correlation, broker metadata | Retry một chunk lớn làm lại nhiều item hơn |
| Mỗi worker nhận “lô lớn” | Có thể nâng throughput nếu worker từng bị overhead cố định | Skew tăng nếu một lô chứa item nặng, tăng tail latency |

Chọn chunk size theo **payload thực tế p95/p99**, memory budget, transaction boundary và hiệu năng writer, không chỉ theo số item. Nếu source row biến thiên từ vài trăm byte tới vài MB, chunk 1.000 item có thể gây spike serialization/memory dù số chunk/s nhỏ.

## 5. Vì sao backlog tăng?

Một cách phân tích nên đặt nguyên nhân vào đúng tầng, không mặc định broker chậm:

| Quan sát | Giả thuyết chính | Dữ liệu cần kiểm tra |
| --- | --- | --- |
| Request ready tăng đều, worker CPU/DB đã cao | Manager sản xuất nhanh hơn capacity worker | `λ`, `μ`, CPU, DB lock/IO, writer throughput |
| Ready tăng, worker hầu như rảnh | Thiếu consumer, sai routing, subscription/chia partition | Consumer count, binding/routing, log nhận message |
| Ready thấp, unacked/in-flight cao | Worker đã nhận nhưng chậm xử lý hoặc ack không tới | Prefetch, thread dump, DB pending, transaction duration |
| Request ổn, reply queue tăng | Manager không tiêu thụ reply hoặc correlation lỗi | Reply consumer, error handler, unknown correlation key |
| Retry/DLQ tăng | Poison message, schema mismatch, dependency lỗi | Exception class, retry count, payload sample an toàn |
| Broker disk/network cao | Payload lớn, retention, replication hoặc burst | Message bytes/s, disk free, network, broker alarms |
| Lag tăng chỉ ở một Kafka partition | Phân bố key lệch, consumer kẹt hoặc partition hot | Lag/throughput từng partition, rebalance log |
| DB pool pending tăng khi thêm worker | Worker tranh một pool giới hạn hoặc cursor giữ connection | Active/idle/pending, connection acquisition wait |
| Throughput hữu ích giảm nhưng delivery/s tăng | Retry storm, redelivery lặp | Unique chunk completed/s, retry rate, DLQ rate |

Nguyên nhân cũng có thể nằm ở **cấu hình version/schema**: worker mới không deserialize được message do manager cũ gửi, hoặc kết quả reply không mang đúng correlation. Vấn đề này biểu hiện như queue tăng dù phần lớn worker vẫn “đang chạy”.

Trong mọi trường hợp, đo **thời gian hoàn tất nghiệp vụ từ nguồn tới đích** để tránh tối ưu một queue bằng cách chuyển backlog sang queue khác.

## 6. RabbitMQ và Kafka: chỉ số khác nhau

Spring Batch có thể giao tiếp qua Spring Integration với các middleware khác nhau. Cách tính backlog phải theo contract của broker, không gom mọi công nghệ thành “queue size”.

| Đối tượng | RabbitMQ (mô hình queue) | Kafka (mô hình partitioned log) |
| --- | --- | --- |
| Công việc chưa được consumer nhận | Số message `ready` trong queue | `consumer lag` = chênh lệch offset cuối và offset đã commit cho từng partition/group (tùy metric) |
| Đã giao nhưng chưa ack/commit | `unacked` theo consumer/channel | Record đã poll nhưng chưa hoàn tất/commit offset; thường cần metric app về in-flight |
| Mở rộng consumer | Thêm consumer có thể chia tải cùng queue | Một partition của cùng consumer group thường chỉ do một consumer nhận tại một thời điểm; muốn tăng song song có thể cần thêm partition |
| Retry | Nack/requeue, delayed retry qua exchange/queue phù hợp | Retry topic, backoff hoặc chiến lược xử lý lại/offset tùy thiết kế |
| DLQ | Dead-letter exchange/queue theo cấu hình | Dead-letter topic do ứng dụng/framework tổ chức |
| Lưu trữ | Queue/persistence, memory/disk alarms | Append log, retention, replica và disk quota |
| Cảnh báo cốt lõi | Ready + unacked + oldest age + publish/ack rate | Lag từng partition + record age + consumption/commit rate + rebalance |

**Không coi Kafka lag bằng 0 là mọi business effect đã commit.** Consumer có thể commit offset trước khi writer commit nếu cấu hình sai; lúc đó lag thấp nhưng dữ liệu mất. Ngược lại, worker ghi DB xong nhưng offset chưa commit có thể xử lý lại sau rebalance.

**Không coi RabbitMQ ready bằng 0 là không còn backlog.** Một consumer prefetch nhiều message vào unacked rồi đợi DB connection, khiến ready giảm nhưng nhiều chunk vẫn chưa hoàn tất.

### Giới hạn của phép đo

- Kafka lag thường là chênh lệch **offset**, không nhất thiết là số chunk nghiệp vụ còn xử lý, và record bị skip/filter vẫn chiếm offset.
- Mỗi broker có chính sách retention, retry và dead-letter khác nhau; phải dùng metric/semantics đúng client và phiên bản.
- Dashboard tổng theo mọi partition có thể che một partition nóng; vừa đo tổng vừa đo max lag/age của partition.
- Khi message được gửi lại, phải phân biệt **fresh requests/s** và **delivery attempts/s** để tính capacity đúng.

## 7. Backpressure: ngăn manager phát sinh vô hạn chunk

Một biện pháp cơ bản là đặt giới hạn số **chunk outstanding** chưa được hoàn tất, ví dụ `maxOutstandingChunks=500`. Nếu manager đã có 500 chunk đang chờ kết quả, nó cần tạm giảm/ngừng đọc và gửi thêm theo cách được cơ chế Spring Batch Integration/transport **hỗ trợ an toàn**.

~~~mermaid
flowchart TD
    R["Manager reader chuẩn bị chunk"] --> L{"Outstanding < limit?"}
    L -->|"Có"| P["Publish chunk request"]
    P --> I["Tăng outstanding đúng một lần theo chunk id"]
    I --> W["Worker process + write"]
    W --> A["Kết quả được manager xác nhận"]
    A --> D["Giảm outstanding theo chunk id, không giảm hai lần"]
    D --> L
    L -->|"Chưa"| Q["Dừng/giới hạn request mới, theo dõi queue"]
    Q --> L
~~~

Đây là **sơ đồ thiết kế**, không phải ngụ ý mọi builder remote chunking đều expose property có đúng tên `maxOutstandingChunks`. Cần kiểm tra API của phiên bản Spring Batch Integration hiện sử dụng. Nếu tự xây tầng admission control:

- Permit phải theo **chunk identity** và được giữ cho tới trạng thái hoàn tất thật, không giải phóng ngay khi broker chấp nhận publish.
- Phải xử lý timeout, retry, redelivery, reply lặp, process chết; không để đếm âm hoặc permit rò rỉ vô hạn.
- Nếu cần quota trên nhiều manager/replica, semaphore trong một JVM **không đủ**; dùng coordinator hoặc cơ chế admission chung.
- Không khóa transaction JDBC của reader/manager trong lúc chờ broker quá lâu nếu không cần; tránh connection starvation.
- Với broker đã có giới hạn memory/disk và publisher confirms, cần đo hành vi blocking/rejection và chính sách gửi lại khi lỗi.

### Phân biệt các núm điều khiển

| Núm điều khiển | Giảm cái gì? | Không tự giải quyết cái gì? |
| --- | --- | --- |
| Giới hạn outstanding tại manager | Tốc độ bơm chunk mới và độ sâu backlog | Không tăng writer throughput |
| Executor concurrency ở worker | Số chunk xử lý đồng thời trên worker | Không tăng DB/API quota; quá cao dễ contention |
| RabbitMQ prefetch / in-flight limit | Message được giao trước nhưng chưa ack mỗi consumer | Không giới hạn tổng message đang nằm ready ở queue |
| Kafka poll/batch/in-flight controls | Lượng record client lấy, queue nội bộ và thứ tự xử lý | Không tự tạo thêm Kafka partitions hay tăng khả năng DB |
| Broker queue/disk quota | Tài nguyên middleware được phép sử dụng | Chạm trần có thể gây block/reject; phải có backpressure trước |
| Chunk size | Số message trên mỗi item, payload mỗi message | Không loại bỏ xử lý lại, không chắc tăng throughput hữu ích |
| Retry backoff + jitter | Retry storm khi dependency lỗi | Không làm một poison message trở thành dữ liệu hợp lệ |

Phải thiết kế **admission control** sao cho manager có thể dừng/tiếp tục một cách phù hợp với checkpoint và restart. Không tự gọi `reader.read()` trước rồi giữ vô hạn dữ liệu chưa được ghi nhận trong memory chỉ để “đợi permit”, vì khi process chết có thể không khớp checkpoint. Đảm bảo logic pause không phá trạng thái bước xử lý.

## 8. Sizing worker theo bottleneck, không theo queue depth

Giả sử một worker thực tế xử lý bền vững `12 chunk/s` dưới workload đại diện. Nếu không có tranh chấp, `10 worker` có thể đạt khoảng `120 chunk/s`. Nhưng đây là **năng lực tối đa giả định khi cộng**, cần kiểm tra trần DB, API, CPU, memory, broker và network.

~~~text
R_workers_raw ≈ worker_count × chunk/s/worker

R_sustainable_unique ≤ min(
    R_workers_raw sau retry/rework,
    R_DB_writer,
    R_API,
    R_broker,
    R_CPU_memory
)
~~~

Nếu DB writer đã chạm trần 120 chunk/s, tăng lên 20 worker có thể làm lock wait, pending connection và rollback tăng, kéo `R_sustainable_unique` **xuống thấp hơn**. Khi đó nên tối ưu writer/SQL/index, JDBC batch, transaction và phân bố dữ liệu trước khi tăng consumer.

### Tính chi phí connection

Một worker có thể dùng connection cho writer transaction, reader/helper query, JobRepository hoặc pool khác. Với remote chunking, manager reader có thể giữ connection riêng, worker ở nhiều process có pool riêng. Tổng connection đến business DB có thể được ước lượng bằng:

~~~text
C_total_peak ≈
    C_manager_readers
  + Σ(worker_replicas × pool_max_per_replica)
  + C_other_apps
~~~

Đây là **cận trên cấu hình pool**, không phải số connection luôn mở; một số pool tạo connection theo nhu cầu. Đừng lấy pool max chia thẳng thành số worker nếu mỗi worker có thể giữ nhiều connection hoặc dùng nguồn dữ liệu khác nhau. Phải đo active/pending và DB `max_connections` thực tế.

Ví dụ 3 worker pod, mỗi pod `maximumPoolSize=20` có thể dùng tới 60 connection, chưa kể manager. Nếu DB chỉ còn ngân sách 40 session cho toàn job, tăng số pod có thể làm job không ổn định ngay cả khi queue depth giảm tạm thời.

## 9. Transaction, ack và xử lý lại: backlog phải bảo vệ dữ liệu

Middleware giúp vận chuyển chunk; nó không tự tạo một transaction chung giữa **reader manager**, **broker** và **writer worker**. Một chuỗi lỗi có thể là:

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Middleware
    participant W as Worker
    participant D as Business DB
    M->>Q: Publish chunk K
    Q->>W: Deliver K
    W->>D: Commit kết quả K
    Note over W,Q: Worker chết / ACK mất sau DB commit
    Q->>W: Redeliver K
    W->>D: Thử ghi K lần nữa
    D-->>W: UPSERT / dedup theo business key
    W-->>M: Result có correlation key K
~~~

Hành vi thực tế phụ thuộc ack mode, transaction manager và framework. Thiết kế phải chấp nhận tình huống **đã commit nhưng chưa ack/reply**.

### Thứ tự ack là một lựa chọn đánh đổi

- Ack **trước** khi tác dụng nghiệp vụ bền vững: khi worker chết, chunk có thể bị coi là đã xử lý trong broker nhưng DB chưa có kết quả.
- Ack **sau** khi commit: nếu worker chết ngay sau commit nhưng trước ack, chunk có thể được giao lại.
- Dùng broker transaction hoặc exactly-once mechanism riêng chưa chắc bao phủ JDBC writer nếu không có giao thức tích hợp thực sự.

Vì thế, nên hướng đến **at-least-once delivery + idempotent business effect**, cùng cơ chế kiểm tra/đối soát. Không tuyên bố exactly-once dựa trên việc consumer bật manual ack.

### Khóa idempotency nên đặt ở đâu?

Hai lớp thường hữu ích:

1. **Khóa chunk**: (`jobExecutionId` hoặc định danh logic ổn định, `stepExecutionId`, `chunkSequence`) giúp nhận diện reply lặp, kiểm soát outstanding và log. ID kỹ thuật có thể thay đổi khi restart, nên không dùng nó làm khóa nghiệp vụ duy nhất nếu muốn dedup xuyên attempt.
2. **Khóa nghiệp vụ**: (`businessDate`, `orderId`, `sourceVersion`) giúp DB/API tránh thực hiện cùng hiệu ứng nhiều lần khi chunk được redeliver, chia lại hoặc restart.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE imported_order (
    business_date DATE NOT NULL,
    order_id BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (business_date, order_id)
);
~~~

~~~sql
-- Ghi kết quả theo business key, không chèn dòng trùng khi replay.
-- Phiên bản cũ không được ghi đè phiên bản mới.
INSERT INTO imported_order(
    business_date, order_id, source_version, payload
)
VALUES (:businessDate, :orderId, :sourceVersion, :payload)
ON CONFLICT (business_date, order_id) DO UPDATE
SET source_version = EXCLUDED.source_version,
    payload = EXCLUDED.payload
WHERE imported_order.source_version < EXCLUDED.source_version;
~~~

SQL này minh họa **trạng thái kết quả cuối** idempotent theo version; chưa bao phủ các trigger/audit/API side effect phát sinh từ mỗi lần gọi. Nếu một input dùng phép cộng vào aggregate, `UPDATE total = total + :delta` có thể lặp sai khi redelivery; cần ledger theo operation key hoặc partial aggregate rồi merge có kiểm soát.

### Poison message và DLQ

Nếu một message không deserialize được hoặc luôn vi phạm nghiệp vụ, retry vô hạn làm backlog không bao giờ xả. Thiết lập:

- Phân loại lỗi transient và permanent; retry hữu hạn với backoff.
- DLQ/dữ liệu cách ly có kèm correlation, exception, schema version và dấu vết đủ để xử lý.
- Cảnh báo khi DLQ tăng, không âm thầm coi DLQ là chunk hoàn tất.
- Chính sách replay DLQ: sửa dữ liệu/ứng dụng trước, thử lại **cùng key** và kiểm tra side effect trước đó.
- Bảo vệ thông tin nhạy cảm trong log/payload của DLQ, giới hạn retention và quyền truy cập.

Một chunk chứa nhiều item có thể có một item lỗi. Quyết định skip/retry cần nằm trong **fault-tolerance policy của worker** và tuân thủ yêu cầu nghiệp vụ; không mặc nhiên bỏ cả chunk hoặc bỏ một item rồi tuyên bố job hoàn thành thành công.

## 10. Reply backlog và correlation: tình huống khó phát hiện

Remote chunking có hai chiều: manager gửi request và worker cần gửi **kết quả** để manager theo dõi chunk. Vì vậy có thể xảy ra:

1. Request queue gần như trống.
2. Worker đã ghi dữ liệu và gửi reply.
3. Reply channel bị nghẽn hoặc manager gặp lỗi deserialize/correlation.
4. Manager vẫn chờ và cuối cùng timeout hoặc đánh dấu thất bại.

Nếu chỉ dashboard request queue, tình huống này trông như “worker đã xong hết” trong khi `JobExecution` không hoàn tất.

Các thuộc tính cần theo dõi cho từng chunk hoặc message:

| Thuộc tính | Vai trò |
| --- | --- |
| `jobExecutionId` / `stepExecutionId` | Gắn chunk với lần thực thi và step tương ứng |
| `chunkSequence` hoặc chunk correlation ID | Ghép request và reply, phát hiện reply lặp/không rõ nguồn |
| `createdAt` / `receivedAt` / `finishedAt` | Phân biệt waiting, processing và reply delay |
| `attempt` | Phân biệt gửi lần đầu và redelivery (chỉ dùng theo contract) |
| `schemaVersion` | Phát hiện manager/worker dùng message format khác |
| `resultStatus` | Success, retryable failure, terminal failure hoặc partial result theo protocol |

Không tự giả định giao thức Spring Batch Integration dùng đúng tên header ở bảng. Đây là **các trường logic nên có trong telemetry/correlation**, còn cấu trúc thực tế phải đối chiếu implementation/serializer đang dùng. Khi bổ sung custom header, phải kiểm tra broker/Spring Integration có giữ và truyền nó qua request/reply hay không.

**Timeout không đồng nghĩa worker chưa làm việc.** Khi timeout, trước khi gửi lại hoặc rerun, xác minh các output theo business key; xử lý retry theo protocol để tránh hai worker cùng ghi trùng.

## 11. Tính toán capacity bằng Java 17

Đoạn Java dưới đây chỉ dùng JDK để hoạch định backlog; nó **không** mô phỏng Spring Batch thực tế. Các tốc độ `λ` và `μ` là giá trị đo/giả định cho **chunk mới và chunk hoàn tất duy nhất**, chưa tính retry:

~~~java
import java.util.Locale;

public final class RemoteChunkBacklogEstimate {

    public static void main(String[] args) {
        double producedChunksPerSecond = 180.0;
        double completedChunksPerSecond = 120.0;
        double burstSeconds = 300.0;
        double averagePayloadKiB = 128.0;
        int averageItemsPerChunk = 100;

        if (producedChunksPerSecond < 0
                || completedChunksPerSecond <= 0
                || burstSeconds < 0
                || averagePayloadKiB < 0
                || averageItemsPerChunk <= 0) {
            throw new IllegalArgumentException("Invalid inputs");
        }

        double backlogChunks = Math.max(0,
                (producedChunksPerSecond - completedChunksPerSecond)
                        * burstSeconds);
        double backlogItems = backlogChunks * averageItemsPerChunk;
        double payloadGiB = backlogChunks * averagePayloadKiB
                / (1024.0 * 1024.0);

        double drainAfterProducerStopsSeconds =
                backlogChunks / completedChunksPerSecond;

        double reducedProducerRate = 100.0;
        double netDrainRate = completedChunksPerSecond - reducedProducerRate;
        double drainWithProducerSeconds = netDrainRate > 0
                ? backlogChunks / netDrainRate
                : Double.POSITIVE_INFINITY;

        System.out.printf(Locale.US,
                "New backlog: %.0f chunks%n", backlogChunks);
        System.out.printf(Locale.US,
                "Queued items (estimated): %.0f%n", backlogItems);
        System.out.printf(Locale.US,
                "Serialized request payload: %.2f GiB%n", payloadGiB);
        System.out.printf(Locale.US,
                "Drain with producer stopped: %.0f seconds%n",
                drainAfterProducerStopsSeconds);
        System.out.printf(Locale.US,
                "Drain with producer at %.0f chunk/s: %.0f seconds%n",
                reducedProducerRate, drainWithProducerSeconds);
    }
}
~~~

Kết quả dự kiến:

~~~text
New backlog: 18000 chunks
Queued items (estimated): 1800000
Serialized request payload: 2.20 GiB
Drain with producer stopped: 150 seconds
Drain with producer at 100 chunk/s: 900 seconds
~~~

Chương trình không tính broker metadata/replication/retention, xử lý lỗi, skew, chunk cuối và biến động của tốc độ worker. `payloadGiB` là ước lượng **payload request** cho số chunk tồn đọng, không phải dung lượng disk chính xác của RabbitMQ hay Kafka. Để sizing production, đo phân phối kích thước message và dùng tải burst đại diện, không lấy duy nhất average.

## 12. Kịch bản điều phối với rate limit và retry

Một pipeline vận hành an toàn có thể đặt các ràng buộc ở nhiều tầng:

~~~text
[Manager reader]
      |
      v
[Giới hạn outstanding chunk và tốc độ publish]
      |
      v
[Request broker: quota, monitoring, retention]
      |
      v
[Workers: bounded concurrency, bounded prefetch]
      |
      v
[Writer DB/API: transaction + idempotency + rate limit]
      |
      v
[Reply broker và manager correlation]
      |
      v
[Đối soát + hoàn tất StepExecution]
~~~

**Không có một con số “worker count tối ưu” độc lập với backend.** Một baseline thực tế:

- Đo worker `chunk/s`, `item/s` và payload bytes/s khi chỉ một worker hoạt động.
- Kiểm tra DB connection/lock/CPU, API RPS, broker disk/network và manager reader throughput.
- Tăng worker từng mức, tính **chunk hoàn tất hữu ích** và business item đã commit, không chỉ message received.
- Đặt giới hạn outstanding để backlog không tăng quá SLA/retention/capacity đã hoạch định.
- Dừng tăng worker khi throughput bão hòa hoặc retry/latency xấu đi.

### Chuỗi lỗi cần xử lý

| Sự kiện | Tác động lên backlog | Ứng xử được mong đợi |
| --- | --- | --- |
| Worker tạm thời chậm do DB lock | Ready/in-flight/age tăng | Backpressure, kiểm tra DB lock, giảm concurrency nếu cần |
| Broker disk alarm | Publish bị block/reject theo contract | Không mất chunk; giảm tốc, log và retry publish có kiểm soát |
| Worker commit xong nhưng ack lỗi | Message có thể redelivery | Writer idempotent, reply/correlation chống lặp |
| Manager restart | Outstanding/correlation đang dở có thể mất state trong memory | Khôi phục theo metadata/protocol, đối soát kết quả |
| Worker version mới không đọc được schema cũ | Retry/DLQ tăng | Versioned message schema, rolling upgrade có compatibility |
| Reply queue backlog | Manager đợi lâu dù writer xong | Kiểm tra reply consumer/routing, timeouts, không phát chunk mới vô hạn |
| Poison message | Redelivery/DLQ tăng, worker bị chiếm | Retry hữu hạn, cách ly, sửa và replay có chủ đích |

## 13. Giám sát và SLO cho backlog

Một dashboard cần ghép **middleware metrics**, **worker metrics** và **Spring Batch business metrics**:

| Metric (tên logic) | Ý nghĩa / cách dùng |
| --- | --- |
| `remote_chunk_requests_published_total` | Tổng số request mới đã publish; tách retry |
| `remote_chunk_requests_completed_total` | Chunk **duy nhất** đã hoàn tất bền vững |
| `request_ready_messages` | Request đang chờ giao |
| `request_unacked_or_inflight` | Request đã giao nhưng chưa hoàn tất/ack |
| `request_oldest_age_seconds` | Tuổi request cũ nhất chưa xử lý |
| `reply_backlog_messages` | Reply đang chờ manager |
| `chunk_end_to_end_latency_seconds` (p50/p95/p99) | Từ publish đến manager nhận kết quả |
| `worker_chunk_processing_seconds` | Thời gian processor/writer tại worker |
| `redelivery_attempts_total` / `retry_attempts_total` | Độ khuếch đại retry |
| `dlq_messages_total` | Chunk lỗi cuối, cần xử lý |
| `worker_active_tasks` / `worker_queue_depth` | Worker có thực sự bận hay đang nghẽn |
| `jdbc_connections_pending` / `db_lock_wait` | Phân biệt bottleneck DB |
| `batch_job_duration_seconds` / `step_status` | Liên hệ queue backlog với SLA job |

Đây là **tên gợi ý** cho instrumentation; không bảo đảm Spring Batch, RabbitMQ/Kafka hay Micrometer xuất sẵn đúng các metric này. Nên dùng tên/đơn vị của middleware đang triển khai rồi ánh xạ lên dashboard, tránh label có độ phân biệt vô hạn như `orderId` hoặc `chunkId` cho từng time series.

### Cảnh báo nên dựa trên cả tốc độ và tuổi

Ví dụ các quy tắc khởi đầu (cần hiệu chỉnh qua load test):

1. `λ > μ` liên tục 3–5 phút và backlog tăng dương: nguy cơ mất ổn định.
2. Tuổi request cũ nhất > thời gian chờ kỳ vọng hoặc SLA của chunk.
3. Reply backlog tăng khi request backlog giảm: nghi vấn nghẽn chiều trả về.
4. Retry/redelivery rate tăng đột ngột hoặc DLQ có item bắt buộc xử lý.
5. Dung lượng broker/disk hoặc DB pool pending tiến gần ngưỡng tài nguyên.
6. Dự báo **thời gian xả backlog** vượt thời gian còn đến deadline job.

Ví dụ nếu còn 10 phút trước SLA nhưng tồn 18.000 chunk, `μ_unique=120/s` và manager không phát chunk mới, thời gian xả lý tưởng 150 giây. Nếu manager còn phát 100 chunk/s, thời gian xả 900 giây, **vượt 10 phút**. Cảnh báo theo drain-time thường hành động được hơn ngưỡng queue depth cố định.

## 14. Runbook xử lý backlog trong production

Khi queue dài bất thường, tránh phản xạ “thêm consumer ngay”. Làm theo trình tự:

1. **Đặt phạm vi:** backlog ở request ready, in-flight, retry/DLQ hay reply? Gắn đúng job/business window và middleware.
2. **Kiểm tra tốc độ:** đo `λ_new`, `μ_unique`, retry attempts và oldest age; ước lượng backlog có còn tăng không.
3. **Kiểm tra sức khỏe:** worker có nhận được message? DB pool, lock, CPU, memory, API throttling, broker disk/network ra sao?
4. **Giảm nguồn phát khi cần:** kích hoạt backpressure hoặc tạm dừng admission theo cơ chế hỗ trợ, tránh gây thêm queue buildup.
5. **Tăng worker có kiểm soát chỉ khi backend còn dư:** theo dõi throughput hữu ích, connection pending, lock wait và p95 latency sau thay đổi.
6. **Xử lý lỗi cố định:** phân loại poison message, retry có hạn, cách ly DLQ và lập quy trình replay an toàn.
7. **Kiểm tra reply/correlation:** worker có thể đã commit nhưng manager chưa xác nhận; cần đối soát kết quả trước rerun.
8. **Phục hồi job theo metadata:** xác nhận worker cũ đã dừng/không còn ghi, giữ business keys/partition state ổn định, rồi restart đúng `JobInstance` nếu thích hợp.
9. **Đối soát đầu ra:** unique key, count/checksum, missing/duplicate side effects và event bắt buộc, không chỉ nhìn queue đã về 0.
10. **Phân tích nguyên nhân gốc:** điều chỉnh quota, worker/chunk size, SQL/index, retry policy, retention và cảnh báo.

Không xóa queue hoặc DLQ để “làm sạch” backlog khi chưa biết message nào đã commit và message nào chưa; thao tác đó có thể bỏ mất công việc nghiệp vụ. Tương tự, một lệnh xóa thẳng dữ liệu metadata `BATCH_*` để mở khóa job sẽ làm hỏng restart.

## 15. Kiểm thử backlog trước khi đưa vào vận hành

### Kịch bản A — Producer vượt consumer

Cho manager phát `180 chunk/s` trong 5 phút và cố định worker capacity quanh `120 chunk/s`. Kiểm tra:

- Backlog tăng gần 18.000 chunk dưới giả định không mất message và tốc độ ổn định.
- Queue age, disk/network và manager memory không vượt ngưỡng kiểm soát.
- Khi giảm hoặc dừng manager, backlog thực sự xả và kết quả nghiệp vụ đủ.

### Kịch bản B — Worker đã nhận nhưng bị treo

Cho worker prefetch/receive một số chunk, sau đó chặn ở DB lock hoặc connection acquisition. Kiểm tra ready queue có thể thấp nhưng unacked/in-flight/age cao. Việc mở thêm consumer có gây thêm DB contention hay không?

### Kịch bản C — Commit thành công, reply/ack mất

Sau khi worker commit DB, mô phỏng mất ack hoặc reply. Cho transport redeliver theo cơ chế thực tế, xác minh business key không bị ghi trùng và manager cuối cùng nhận trạng thái đúng. Nếu framework không tự xử lý tình huống, cần bổ sung recovery protocol rõ ràng.

### Kịch bản D — Poison message

Gửi chunk có một item sai schema hoặc lỗi nghiệp vụ vĩnh viễn. Kiểm tra retry không vô hạn, DLQ nhận được đủ metadata và job không bị đánh dấu thành công khi còn item bắt buộc chưa xử lý.

### Kịch bản E — Manager restart / worker scale

Cho manager chết khi có nhiều outstanding chunk, sau đó restart theo chính sách Spring Batch. Đồng thời scale worker từ 4 lên 8 và đo DB pool/lock. Xác minh chunk cũ/đã commit không gây duplicate và correlation sau phục hồi đúng.

### Kịch bản F — Broker backpressure

Giới hạn disk/quota hoặc giả lập publish rejection. Kiểm tra manager phát hiện lỗi, không âm thầm bỏ item đã đọc, không giữ connection/heap vô hạn và có thể tiếp tục từ trạng thái hợp lệ.

### Kịch bản G — So sánh chunk size

Chạy cùng snapshot với chunk 50, 100, 500 item; đo:

| Yếu tố | Điều cần quan sát |
| --- | --- |
| Messages/s | Giảm khi chunk lớn, nếu thông lượng item không đổi |
| Payload p95/p99 | Có vượt broker max message size/heap không? |
| Transaction/commit latency | Chunk lớn có giữ lock quá lâu? |
| Retry amplification | Một chunk lỗi làm lại bao nhiêu item? |
| Thời gian end-to-end | Tăng throughput item hữu ích hay chỉ tăng tốc publish? |
| Độ lệch worker | Có worker bị mắc chunk nặng trong khi worker khác rảnh không? |

Phải đối chiếu **đúng tập business key đầu ra** giữa các cấu hình trước khi kết luận cách nào nhanh hơn.

## 16. Chọn mô hình scale khi backlog lớn

| Tín hiệu | Cách tiếp cận hợp lý | Điều kiện |
| --- | --- | --- |
| Manager reader là nút thắt, worker rảnh | Tối ưu reader, nguồn SQL; cân nhắc remote partitioning nếu dữ liệu chia được | Partition đủ và không chồng lấn; worker tự đọc từng miền |
| Worker CPU là nút thắt, DB còn dư | Thêm worker pod/concurrency có giới hạn | Processor stateless/thread-safe, đo tổng CPU và memory |
| Worker writer DB đã chạm trần | Tối ưu batch write/index/transaction, giảm lock | Thêm worker không tự tăng DB throughput |
| Broker disk/network đã căng | Giảm payload, chunk size hợp lý, backpressure, tăng broker capacity | Tôn trọng retention/replication và SLA |
| Reply manager bị nghẽn | Tối ưu reply channel, correlation/handler và giới hạn outstanding | Đảm bảo không mất kết quả đã commit |
| Backlog chủ yếu là retry/DLQ | Sửa nguyên nhân lỗi, backoff, replay có chủ đích | Idempotent side effects và đối soát |
| Nhiều job cùng dùng middleware/DB | Admission control, quota công bằng, tránh job overlap không cần thiết | Không làm một job chiếm hết năng lực chung |

Nếu throughput nghiệp vụ đã chạm **trần DB writer**, remote chunking chỉ di chuyển khối lượng tính toán; nó không khắc phục DB. Nếu reader ở manager đã bão hòa, remote partitioning có thể giúp phân tán việc đọc **khi nguồn và thuật toán phân chia cho phép**. Quyết định phụ thuộc đường găng, transaction/restart và mức năng lực thực, không dựa duy nhất vào số message đợi.

## 17. Bài tập tự đánh giá

Một pipeline remote chunking có:

- Chunk size = 200 item, payload request trung bình 64 KiB.
- Manager phát 75 chunk/s trong 10 phút.
- Worker tổng cộng commit thành công 50 chunk/s.
- Sau đó manager giảm còn 40 chunk/s, năng lực worker không đổi.
- Broker có giới hạn 1 GiB dành cho payload đang chờ, **chưa tính metadata/replication**.

**Câu hỏi:**

1. Sau 10 phút, backlog tăng thêm bao nhiêu chunk và tương đương bao nhiêu item?
2. Kích thước payload backlog gần bao nhiêu MiB?
3. Khi manager giảm còn 40 chunk/s, cần bao lâu để xả backlog lý tưởng?
4. Nếu có 5% chunk bị xử lý lại, phải thay đổi phép đo throughput như thế nào?
5. Nếu request queue về 0 nhưng reply queue còn tăng, đã có thể tuyên bố job hoàn tất không?

**Gợi ý giải:**

~~~text
ΔB = (75 − 50) × (10 × 60)
   = 15.000 chunk

Số item trong backlog ≈ 15.000 × 200 = 3.000.000 item

Payload ≈ 15.000 × 64 KiB
        = 960.000 KiB
        = 937,5 MiB

Net drain = 50 − 40 = 10 chunk/s
T_drain = 15.000 / 10 = 1.500 s = 25 phút
~~~

Mô hình payload 937,5 MiB chưa cộng disk overhead/retention/replication nên **gần sát ngân sách 1 GiB** và rủi ro cao. Câu 4: phải đo `μ_unique` tách khỏi delivery attempts, không dùng tốc độ nhận thô thay cho thành công duy nhất. Câu 5: chưa; cần xác nhận manager đã nhận reply hợp lệ, step/job đạt trạng thái đúng và dữ liệu nghiệp vụ đã được đối soát.

## Tài liệu tham khảo

- [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): khái niệm mở rộng xử lý, remote chunking/partitioning.
- [Spring Batch Reference – Spring Batch Integration](https://docs.spring.io/spring-batch/reference/spring-batch-integration.html): kết nối manager/worker qua middleware; đối chiếu API theo phiên bản đang sử dụng.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/): message channels, handlers và kết nối middleware.
- [RabbitMQ – Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch): ranh giới số message giao mà chưa ack.
- [RabbitMQ – Queues](https://www.rabbitmq.com/docs/queues): queue semantics, giới hạn và vận hành.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/): consumer groups, offsets, partitions và delivery semantics.

## Ghi nhớ

**Backlog middleware trong remote chunking là chênh lệch giữa công việc manager tạo ra và năng lực worker hoàn tất, được biểu hiện ở nhiều trạng thái chứ không chỉ độ sâu ready queue.** Hãy đo request, in-flight, retry/DLQ, reply, message age và throughput **chunk nghiệp vụ duy nhất đã commit**. Dùng chênh lệch `λ − μ` để ước lượng tốc độ tăng backlog; khi `μ > λ`, thời gian xả backlog lý tưởng là `B/(μ − λ)`. Tính cả số byte và giới hạn DB/API/broker, rồi đặt backpressure trước khi queue vượt sức chứa. Mọi retry, redelivery và restart phải được bảo vệ bằng business key idempotent, correlation đáng tin cậy và đối soát kết quả; chỉ khi đó việc thêm worker mới thực sự mở rộng Spring Batch an toàn.
