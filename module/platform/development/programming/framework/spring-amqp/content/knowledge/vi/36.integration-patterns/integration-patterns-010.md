# Chọn queue, stream hoặc broker khác theo đặc điểm bài toán

Trong hệ thống bất đồng bộ, lựa chọn **queue**, **stream** hay một **message broker khác** ảnh hưởng trực tiếp đến cách ứng dụng giao công việc, giữ lịch sử, mở rộng consumer, xử lý lỗi và phục hồi dữ liệu. Một công cụ có throughput cao chưa chắc là lựa chọn tốt nếu nghiệp vụ chỉ cần giao một job cho một worker. Ngược lại, một queue hoạt động ổn ở hiện tại có thể không đáp ứng khi tháng sau hệ thống cần **replay** hàng triệu sự kiện để xây lại dữ liệu phân tích.

Bài học thuộc chương **Mẫu tích hợp** của module **SPRING_AMQP**, nơi ứng dụng tích hợp RabbitMQ bằng `RabbitTemplate`, `@RabbitListener`, exchange, queue và binding; thực hành routing, publisher confirms, ACK/NACK, retry, dead-letter, giao dịch và quan sát hệ thống để xây xử lý bất đồng bộ đáng tin cậy. Mục tiêu của bài không phải quảng bá một broker “tốt nhất”, mà là thiết lập **quy trình ra quyết định có thể kiểm chứng** dựa trên đặc điểm workload, mức độ tin cậy, năng lực vận hành và chi phí thay đổi.

> **Quy tắc khởi đầu:** Nếu message chủ yếu là *mệnh lệnh cần một worker thực hiện*, hãy đánh giá queue trước. Nếu message là *sự kiện cần giữ lại và đọc lại*, hãy đánh giá stream/log. Chỉ chọn broker khác khi yêu cầu kỹ thuật hoặc tổ chức vượt khỏi phương án hiện tại và lợi ích đủ bù chi phí chuyển đổi.

## 1. Phân biệt command, event, job và event log

Trước khi hỏi “RabbitMQ hay Kafka?”, phải hỏi **message là gì** và **ai sở hữu kết quả xử lý**.

| Khái niệm | Ví dụ | Ý nghĩa | Hướng thiết kế thường hợp |
|---|---|---|---|
| **Command** | `SendInvoiceEmail` | Yêu cầu một bên thực hiện hành động | Queue công việc, request/reply hoặc RPC tùy SLA |
| **Job** | `ResizeImage(imageId)` | Tác vụ có thể xử lý bởi một worker bất kỳ | Queue + competing consumers + ACK/retry |
| **Domain event** | `OrderPaid(eventId, orderId)` | Một sự kiện nghiệp vụ đã xảy ra, nhiều bên có thể quan tâm | Exchange fan-out tới nhiều queue **hoặc** stream nếu cần replay |
| **Event log** | Tập các `OrderPaid` có thứ tự theo partition | Chuỗi bản ghi cần giữ và đọc lại | Stream / distributed log |
| **State snapshot** | Tổng hợp số dư tại version 250 | Trạng thái tại một thời điểm, giúp phục hồi nhanh | Database / object storage, có thể kết hợp event log |

Ví dụ `SendInvoiceEmail` là command: sau khi gửi email thành công, message có thể rời queue. Nhưng `OrderPaid` là một fact: một hệ thống phân tích mới có thể cần đọc tất cả event cũ để dựng báo cáo theo phương pháp mới. Tên message không tự tạo semantics; cần ghi rõ hợp đồng nghiệp vụ.

### 1.1. Queue công việc: cạnh tranh để hoàn tất

~~~mermaid
flowchart LR
    P["Order API"] --> EX["billing.commands.x"]
    EX -->|"invoice.create"| Q["billing.jobs.q"]
    Q --> C1["Worker A"]
    Q --> C2["Worker B"]
    C1 --> DB["Invoice database"]
    C2 --> DB
    C1 -.-> ACK["ACK sau khi commit"]
    C2 -.-> ACK
~~~

Hai worker cùng consume một queue để **chia message**. Khi consumer ACK và broker ghi nhận, delivery được xem là hoàn tất; message không còn trong queue để một consumer mới tùy ý replay từ đầu. Nếu worker chết khi còn unacked, RabbitMQ có thể giao lại. **At-least-once** đòi hỏi consumer idempotent khi tác dụng nghiệp vụ không được phép lặp.

### 1.2. Stream: nhiều độc giả giữ tiến độ riêng

~~~mermaid
flowchart LR
    P["Orders service"] --> ST["orders.events.stream<br/>offset 100, 101, 102..."]
    ST --> A["Search projection<br/>checkpoint 102"]
    ST --> B["Analytics<br/>checkpoint 98"]
    ST --> C["Audit / replay<br/>bắt đầu từ offset 30"]
~~~

Stream là **append-only log**, record còn lại cho tới khi retention xóa dữ liệu theo chính sách. Các consumer đọc theo **offset** của chính mình; việc A đã xử lý không xóa bản ghi của B. Stream hỗ trợ replay khi record còn được lưu; **retention không chờ consumer chậm**. Nếu consumer nghỉ quá lâu, offset đã checkpoint có thể không còn và cần snapshot/archive hoặc chính sách phục hồi khác.

### 1.3. Fan-out nhiều queue không đồng nghĩa cần stream

RabbitMQ exchange có thể nhân một event tới **nhiều queue**, mỗi queue có consumer group riêng và ACK độc lập:

~~~text
orders.events.x
   |-- notification.orders.q
   |-- inventory.orders.q
   +-- billing.orders.q
~~~

Điều này giải quyết nhu cầu **nhiều dịch vụ hiện tại cùng nhận event**. Chỉ khi cần **đọc lại lịch sử đã ACK**, nhiều reader có tiến độ độc lập dài hạn hoặc một log append-only, stream mới tạo giá trị thêm đáng kể. Một ứng dụng có thể sử dụng cả hai mà không mâu thuẫn.

## 2. Tám tiêu chí quyết định trước khi chọn công nghệ

| Tiêu chí | Câu hỏi cần trả lời | Ảnh hưởng tới lựa chọn |
|---|---|---|
| **Mục đích message** | Một worker hoàn tất hay nhiều reader giữ lịch sử? | Queue vs stream/event log |
| **Replay và retention** | Cần đọc lại sau ACK? Bao lâu? Mất lịch sử có chấp nhận không? | Stream/log hoặc archive chuyên dụng |
| **Routing** | Cần direct/topic/fanout/header, request/reply hay routing theo key? | RabbitMQ exchange mạnh với routing AMQP |
| **Thứ tự** | Theo queue, theo `orderId`, hay toàn hệ thống? | Partition/shard, versioning, single consumer |
| **Độ tin cậy** | At-most-once, at-least-once, giới hạn duplicate và mất dữ liệu? | Confirm/ACK/idempotency/outbox; broker capability |
| **Tải và latency** | Message/s, byte/s, payload p99, burst, consumer lag, SLO? | Queue/stream/partition count, benchmark |
| **Vận hành và tuân thủ** | Ai quản lý broker, backup, DR, ACL, mã hóa, audit, retention? | Managed service, tự vận hành hoặc hybrid |
| **Tích hợp hiện có** | Đang dùng `RabbitTemplate`, Spring Kafka hay cloud SDK? | Chi phí migration, lock-in và kỹ năng đội ngũ |

**Không quyết định chỉ từ số message/giây.** Cùng 50.000 message/giây có thể là 50.000 lệnh gửi email (queue với số worker lớn) hoặc 50.000 event clickstream cần replay 30 ngày (stream). Chọn đúng semantics thường quan trọng hơn con số throughput quảng cáo.

### 2.1. Làm rõ SLO và điều không được phép xảy ra

Ví dụ một checklist rút gọn trong buổi thiết kế:

- Message **được phép trùng** ở broker nhưng **không được trừ tiền hai lần**?
- Nếu broker down 10 phút, producer có thể giữ event trong **outbox** để gửi sau?
- Nếu consumer nghỉ 5 ngày, có cần đọc được tất cả record từ lúc ngừng?
- Có yêu cầu thứ tự **theo aggregate ID** hay chỉ “sau cùng trạng thái đúng”?
- Có hệ thống nào bắt buộc chạy ở nhiều cloud/region, hoặc có giới hạn lưu dữ liệu địa lý?
- Sau bao lâu sẽ xóa event chứa PII? Ai được phép replay?

Các câu trả lời này thường loại bỏ nhiều ứng viên trước khi cần benchmark.

## 3. RabbitMQ classic queue, quorum queue và stream khác nhau ra sao?

RabbitMQ không có một loại queue duy nhất. Với bài toán tích hợp Spring AMQP, ba lựa chọn thường được so:

| Đặc điểm | Classic queue | Quorum queue | RabbitMQ stream |
|---|---|---|---|
| Bản chất | Queue AMQP giao việc | Queue replicated dựa trên consensus | Append-only log có offset |
| Sau ACK thành công | Message rời queue | Message rời queue | Record còn tới khi retention dọn |
| Replay đã xử lý | Không | Không | Có, nếu dữ liệu còn giữ |
| Chia việc | Competing consumers | Competing consumers | Consumer độc lập đọc offset; chia tải cần mô hình group/partition |
| Khả năng chịu lỗi | Phụ thuộc durability và node/kiến trúc | Replication/quorum theo cấu hình | Replication và retention theo topology/config |
| Retry / dead-letter | ACK/NACK/requeue/DLX | ACK/NACK/requeue/DLX, policy riêng của quorum | Reader tự xử lý offset/retry/quarantine; không áp nguyên trạng ACK queue |
| Ordering | Delivery order có điều kiện, processing order không tự bảo đảm | Tương tự mô hình queue | Thứ tự log theo stream/partition; processing cần kiểm soát |
| API Spring | `RabbitTemplate`, `@RabbitListener` | `RabbitTemplate`, `@RabbitListener` | Có thể route AMQP 0-9-1 tới stream queue; stream-native qua `spring-rabbit-stream` |
| Khi phù hợp | Job thông thường, độ phức tạp vừa | Job quan trọng, cần replication và cơ chế bền vững | Event log, replay, nhiều độc giả, xử lý theo offset |

**Quorum queue vẫn là queue**, không phải stream: replication bảo vệ tính sẵn sàng/durability của queue, nhưng không biến các message đã ACK thành lịch sử replay được. Stream có offset và retention riêng, nhưng không có nghĩa mọi listener AMQP 0-9-1 tự nhận được tất cả khả năng stream-native.

### 3.1. Chọn classic hay quorum khi đã quyết định dùng queue?

- Với tác vụ không quá khắt khe về khả năng chịu lỗi và phù hợp cấu hình vận hành, classic queue có thể đơn giản, đủ nhanh và tiết kiệm tài nguyên.
- Với tác vụ quan trọng cần queue replicated qua nhiều node, quorum queue thường đáng đánh giá. Cần hiểu **quorum availability**, chi phí replication, leader, storage và điều kiện cluster; không chỉ bật cờ là xong.
- Một queue **durable** và message **persistent** chưa đủ nếu ứng dụng bỏ qua publisher confirms hoặc quản lý consumer ACK sai. Durability, confirms, ACK và transaction nghiệp vụ giải quyết các phần khác nhau.
- Khi lựa chọn queue type, đo đúng workload: message size, consumer count, retry pattern và latency. Không coi classic/quorum là hai cấu hình tương đương về mọi đặc tính và cost.

### 3.2. Khi nào RabbitMQ Streams là lựa chọn tự nhiên?

Các dấu hiệu mạnh:

1. Sự kiện `OrderPaid`/`InventoryAdjusted` có giá trị lâu dài, nhiều dịch vụ độc lập cần đọc.
2. Có yêu cầu **rebuild projection** sau lỗi tính toán hoặc backfill cho một consumer mới.
3. Tải append/read tuần tự lớn, retention hữu hạn được tính trước.
4. Chấp nhận quản lý **offset/checkpoint**, consumer lag, retention và schema evolution.
5. Đội ngũ muốn giữ hệ sinh thái RabbitMQ thay vì vận hành thêm một broker khác.

Nếu workload là một lệnh xử lý một lần có DLQ/retry đơn giản, stream thường thêm chi phí không cần thiết. Nếu retention dài hơn nhiều so với dung lượng broker có thể giữ, cần **archive/object storage hoặc event store** riêng, không dựa vào stream vô hạn.

## 4. Khi nào nên xét một broker khác RabbitMQ?

Chuyển broker là thay đổi **hợp đồng giao nhận message**, không chỉ thay `application.yml`. Mỗi công nghệ có thuật ngữ và guarantee riêng. Bảng dưới là **định hướng lựa chọn**, không phải ma trận bảo đảm tính năng giống nhau giữa mọi version, service tier và region.

| Công nghệ | Mô hình nổi bật | Lợi thế cần kiểm chứng | Đánh đổi thường gặp | Khi nên đưa vào shortlist |
|---|---|---|---|---|
| **Apache Kafka** | Distributed partitioned log; topic, offset, consumer groups | Retention/replay, hệ sinh thái event streaming, xử lý log lớn, tích hợp dữ liệu | Vận hành partitions/replication, broker storage, schema/governance; ordering theo partition | Data/event pipelines và nhiều ứng dụng replay lịch sử ở quy mô lớn |
| **Apache Pulsar** | Topic/subscription, phân tách serving và storage theo kiến trúc Pulsar | Subscription models, retention, geo-replication và multi-tenancy | Hệ thống nhiều thành phần và yêu cầu vận hành riêng; phải đo độ trễ/chi phí | Nhiều nhóm/tenant, yêu cầu subscription linh hoạt và replication vùng |
| **NATS + JetStream** | NATS pub/sub kết hợp durable streams/consumers | Giao tiếp nhẹ, nhiều mô hình pub/sub/request-reply, JetStream persistence/replay/ACK | Retention policies và consumer semantics cần hiểu đúng; giới hạn tính năng khác Kafka/RabbitMQ | Messaging latency thấp, kiến trúc nhẹ, muốn thêm persistence có kiểm soát |
| **AWS SQS** | Managed queue (Standard hoặc FIFO) | Giảm công vận hành broker; tích hợp hệ sinh thái AWS | API/semantics khác AMQP, visibility timeout, hạn chế thứ tự/dedup theo loại queue, cloud coupling | Work queue trên AWS với ưu tiên managed operations |
| **Google Cloud Pub/Sub** | Managed topics/subscriptions | Fan-out subscription, scale managed, replay/retention và ordering keys theo cấu hình | Quota/region/retention/delivery model riêng; cloud coupling | Pub/sub/event ingestion trên Google Cloud |
| **Azure Service Bus** | Managed queues/topics/subscriptions | Enterprise messaging, sessions, DLQ, scheduling, transactions trong phạm vi hỗ trợ | Tier/quotas/feature differences, Azure coupling | Command và integration workflows trong Azure |
| **Redis Streams** | Redis log với IDs và consumer groups | Dễ tích hợp nếu đã dùng Redis, đọc theo stream ID, pending/claim | Memory/storage/retention và Redis HA phải được thiết kế; không tự có Kafka semantics | Workload gọn, retention hữu hạn, hạ tầng Redis đã được quản trị tốt |
| **Database outbox + job table** | SQL tables và poller | Cùng transaction với dữ liệu nghiệp vụ, không cần broker ban đầu | Polling/locking, contention, giới hạn scale, tự viết worker/backoff | Khối lượng nhỏ hoặc cần atomic DB state + job intent đơn giản |

Các lựa chọn khác như RabbitMQ AMQP 1.0, Redpanda, managed Kafka, cloud event bus hoặc hệ thống chuyên dụng cũng có thể phù hợp. **Không đưa một sản phẩm vào thiết kế chỉ vì quen thuộc**; chỉ giữ những ứng viên đáp ứng dữ liệu, bảo mật, SLA, cost và khả năng vận hành thực tế.

### 4.1. Kafka: chọn vì partitioned log và hệ sinh thái, không chỉ vì throughput

Apache Kafka lưu record theo **topic partitions**. Trong một partition, record có offset; consumer group quản lý assignment/offset, giúp các ứng dụng replay và xử lý các tập partition. Đây là mô hình thích hợp cho event log, CDC pipeline, data platform và các hệ thống downstream cần đọc độc lập.

**Những điểm phải thiết kế:**

- **Thứ tự:** chỉ có thứ tự bền vững **trong partition**, không có một thứ tự tổng quát giữa nhiều partitions. Muốn thứ tự theo `orderId`, dùng partition key nhất quán và event version.
- **Consumer group:** trong cùng group, một partition thường được xử lý bởi một consumer tại một thời điểm theo assignment. Tăng số consumer **vượt số partition** không tự tăng parallelism tương ứng.
- **Offset commit:** commit offset trước DB commit có thể gây mất tác dụng; DB commit xong nhưng chưa commit offset có thể xử lý lặp. Phải dùng idempotency hoặc cơ chế nhất quán thích hợp.
- **Retention và compaction:** lưu theo thời gian/dung lượng hoặc compact theo key phục vụ mục tiêu khác nhau; compacted topic **không phải lịch sử đầy đủ mọi phiên bản**.
- **Transactions/exactly-once:** Kafka có cơ chế transaction và exactly-once processing cho các đường luồng trong **phạm vi được hỗ trợ**. Nó **không tự khiến ghi PostgreSQL hay gọi HTTP ngoài Kafka xảy ra đúng một lần**.

Hệ Spring tương ứng là **Spring for Apache Kafka** (chẳng hạn `KafkaTemplate`, `@KafkaListener`), không phải `RabbitTemplate`. Cùng sử dụng Spring không có nghĩa cấu hình ACK, DLQ, serialization hay transaction có thể bê nguyên từ Spring AMQP sang.

### 4.2. Pulsar: subscription và multi-tenancy đáng xem xét

Apache Pulsar có mô hình topics, subscriptions với các kiểu nhận khác nhau, đồng thời cung cấp retention, backlog và các tính năng replication tùy cấu hình. Pulsar đáng được đánh giá khi cần nhiều tenants, geo-replication hoặc lựa chọn kiểu subscription linh hoạt.

Nhưng việc “có tính năng” chưa nói lên hiệu quả: cần benchmark chi phí lưu trữ, latency và throughput; vận hành các thành phần broker/storage, phân vùng, quyền truy cập, tiến độ consumer, upgrade và backup. Đừng chọn chỉ vì nghe “queue và stream trong một”.

### 4.3. NATS JetStream: phân biệt core pub/sub và persistent stream

NATS Core cung cấp messaging nhanh với semantics khác durable log. **JetStream** bổ sung streams, persistent storage, publish acknowledgments và durable/pull consumers. JetStream hỗ trợ các **retention policies** khác nhau, chẳng hạn giới hạn lưu trữ, interest hoặc work queue; chính retention policy ảnh hưởng việc record tồn tại sau ACK.

Vì vậy, câu “NATS luôn không lưu message” hoặc “JetStream luôn replay được mọi message sau ACK” đều quá đơn giản. Với policy và giới hạn phù hợp, nó có thể phục vụ job queue hay event replay; nhưng phải xác minh persistence, ACK timeout, redelivery limit, consumer lifecycle và cluster topology của triển khai.

### 4.4. Dịch vụ managed cloud: giảm vận hành nhưng cần học lại semantics

**Amazon SQS** có Standard và FIFO queues. Standard thường cho at-least-once delivery và không đảm bảo strict ordering; FIFO dùng **message group ID** và cơ chế dedup/order trong các điều kiện, phạm vi đã định. Consumer nhận message và xóa nó khi xử lý xong; **visibility timeout** không phải consumer ACK như AMQP `basicAck`. Nếu quá hạn visibility khi đang xử lý, delivery có thể xuất hiện lại; cần idempotency.

**Google Cloud Pub/Sub** có topics và subscriptions, với các khả năng ordering/replay tùy cấu hình và loại subscription. Đặt *ordering key* không tự tạo thứ tự toàn cục; replay phụ thuộc retention và các điều kiện của service. Các đảm bảo như exactly-once delivery nếu được bật cũng có **phạm vi và điều kiện**, không biến cập nhật DB ngoài Pub/Sub thành giao dịch nguyên tử.

**Azure Service Bus** hỗ trợ queues, topics/subscriptions, dead-letter subqueues và **sessions** để điều phối thứ tự/nhóm message khi cần. Lock/settlement và duplicate detection có phạm vi/cửa sổ cụ thể, không thay thế kiểm soát giao dịch nghiệp vụ.

Tất cả dịch vụ managed đều cần tính đến **service limits, region availability, auth/IAM, encryption, network egress, quota, chi phí theo request/throughput/storage và khả năng phục hồi khi service gặp sự cố**. Chi phí phải tính theo dữ liệu và region thực tế, không dùng một con số chung trong bài học.

### 4.5. Redis Streams và SQL queue: cân nhắc vì hệ thống hiện có

Redis Streams sử dụng stream IDs, `XREADGROUP`, `XACK` và pending entries cho consumer groups. Nó có thể giải quyết nhiều luồng nhỏ/medium, nhưng phải quyết định durability (AOF/RDB, HA/replication), trimming/retention, reclaim pending entries và an toàn khi failover. Việc đã dùng Redis làm cache **không tự chứng minh** Redis Streams phù hợp làm event store có yêu cầu lưu dữ liệu nghiêm ngặt.

Với throughput vừa phải, **database-backed job table** có thể là phương án kinh tế và đơn giản: bảng `jobs`, transaction SQL, worker poll với `FOR UPDATE SKIP LOCKED` hoặc claim lease. Nó giảm số hệ thống phải vận hành nhưng chuyển áp lực vào database, yêu cầu thiết kế retry/lease/dead jobs, quan sát polling và dọn dữ liệu. Không lý tưởng cho mọi trường hợp event streaming lớn.

## 5. Ma trận bài toán cụ thể

| Bài toán | Phương án khởi đầu đáng thử | Vì sao | Kiểm tra trước khi chốt |
|---|---|---|---|
| Giao job tạo PDF cho một worker | RabbitMQ classic/quorum queue, SQS, Service Bus queue | Competing consumers, retry và DLQ | Độ bền, cost, thời gian chạy/visibility/ACK |
| Gửi email sau thanh toán | Queue + outbox/idempotency | Command cần thực hiện, không cần replay lịch sử delivery | Tránh gửi email lặp, retry hữu hạn |
| `OrderPaid` cho billing/inventory/notification cùng lúc | RabbitMQ exchange + 3 queues | Fan-out và ACK độc lập | Có yêu cầu replay dài hạn không? |
| Rebuild search index theo lịch sử `OrderPaid` | RabbitMQ Streams, Kafka hoặc Pulsar | Lưu record, offset và replay | Retention, disk, consumer lag, schema evolution |
| Clickstream hàng chục/số lượng lớn event mỗi giây | Kafka/managed log, RabbitMQ Streams, Pub/Sub | Append/read tuần tự, nhiều reader | Throughput thực, byte/s, cost, partitioning |
| Telemetry thời gian thực không cần lưu lâu | NATS Core, RabbitMQ hoặc managed pub/sub phù hợp | Ưu tiên latency, routing và đơn giản | Chấp nhận mất message khi subscriber offline? |
| Fraud analytics cần chạy lại 60 ngày | Kafka/stream có retention đủ hoặc archive + replay | Đọc độc lập, dựng lại model | Capacity retention, PII, thời gian backfill |
| Một công việc mất 20 phút | Queue/managed queue với timeout/lease phù hợp | Giữ ownership công việc, retry khi worker chết | Visibility/consumer timeout và idempotency |
| Kết nối hệ thống cũ dùng AMQP 1.0 | Generic AMQP 1.0 client/compatible broker | Interoperability ở protocol | Address, settlement, auth, broker-specific features |
| Hàng triệu tenants, replication giữa vùng | Đánh giá Pulsar, Kafka và managed services | Multi-tenancy/geo/ops ảnh hưởng lớn | Region latency, failover, governance, chi phí |
| Trigger nghiệp vụ rất ít, cần atomic với SQL | Outbox + SQL worker, có thể thêm queue sau | Cùng DB transaction, ít hạ tầng | Polling latency, lock contention |
| Lưu lịch sử bất biến nhiều năm | Object storage/event archive + index, có thể kết hợp broker | Broker retention không thay compliance archive | Legal hold, deletion, backup, quyền replay |

**Đây là shortlist, không phải kết luận bắt buộc.** Một cloud-managed queue có thể là giải pháp tốt hơn self-hosted RabbitMQ cho cùng một job nếu đội không muốn vận hành cluster; ngược lại một tổ chức đã có RabbitMQ vận hành tốt có thể giữ queue mà không thu thêm hệ thống.

## 6. Cây quyết định thực tế

~~~mermaid
flowchart TD
    A["Bắt đầu: xác định message và SLO"] --> B{"Cần giữ và replay<br/>sự kiện sau xử lý?"}
    B -->|Không| C{"Một job do một worker<br/>thực hiện?"}
    C -->|Có| D["Queue: RabbitMQ / managed queue"]
    C -->|Không| E{"Nhiều subscriber<br/>nhận cùng event?"}
    E -->|Có| F["Exchange + nhiều queue<br/>hoặc managed pub/sub"]
    E -->|Không| G["Xem lại: có cần broker không?"]
    B -->|Có| H{"Khối lượng, ecosystem<br/>và số reader?"}
    H -->|"Phù hợp hạ tầng RabbitMQ"| I["RabbitMQ Streams"]
    H -->|"Data platform / log lớn"| J["Kafka / Pulsar / managed log"]
    H -->|"Workload nhỏ hoặc sẵn hạ tầng"| K["JetStream / Redis Streams<br/>hoặc giải pháp khác có benchmark"]
    D --> L["Kiểm chứng correctness, cost, operations"]
    F --> L
    G --> L
    I --> L
    J --> L
    K --> L
~~~

**Cách dùng cây này:** các nhánh là **giả thuyết kiến trúc**, không phải tính năng bắt buộc. Một stream có thể làm work queue, một managed pub/sub có thể giữ lịch sử và một RabbitMQ exchange có thể fan-out. Quyết định cuối vẫn cần kiểm chứng routing, retention, failure modes, bảo mật, benchmark và năng lực vận hành.

### 6.1. Chấm điểm có trọng số

Nếu còn hai hoặc ba ứng viên phù hợp, sử dụng một bảng đánh giá có trọng số. Ví dụ đội ngũ cần chọn nơi giữ event 30 ngày:

| Tiêu chí | Trọng số minh họa | Cách chấm điểm 1–5 |
|---|---:|---|
| Replay đủ 30 ngày và backfill | 25% | Khả năng đáp ứng retention, offset và recovery có kiểm chứng |
| Throughput + p99 latency đạt SLO | 20% | Benchmark trên workload thật, không dùng marketing claims |
| Chi phí 12 tháng | 15% | Compute, disk, replication, request/egress và nhân sự vận hành |
| Khả năng chịu lỗi/DR | 15% | Failover, backup/restore, RPO/RTO và phạm vi region |
| Khả năng tích hợp hiện có | 10% | Thay đổi code, schema, team skills và observability |
| Bảo mật/tuân thủ | 10% | IAM/vhost/ACL, TLS, audit, retention/PII, vị trí dữ liệu |
| Độ linh hoạt tương lai | 5% | Nhiều consumer, ecosystem, portability |

Tính **điểm tổng = Σ (trọng số × điểm từng tiêu chí)**, nhưng đặt thêm các điều kiện loại trừ: nếu một ứng viên **không đáp ứng yêu cầu dữ liệu bắt buộc** (ví dụ mất event là không chấp nhận), nó không được chọn chỉ vì tổng điểm cao. Trọng số phải do nhóm sản phẩm, security, vận hành và kỹ thuật thống nhất theo trường hợp cụ thể.

**Không nhập điểm ví dụ thành số đo thật.** Sản phẩm có thể thay đổi giới hạn, cơ chế giá và độ phù hợp theo region/version; việc chấm điểm phải lưu kèm cấu hình thử nghiệm và nguồn số liệu.

## 7. Điều gì không thay đổi dù chọn broker nào?

### 7.1. Delivery guarantee không đồng nghĩa business guarantee

| Khái niệm | Mức bảo đảm | Tình huống lỗi cần nghĩ tới |
|---|---|---|
| **At-most-once** | Có thể mất, không chủ động gửi lại | Broker/consumer lỗi sau khi delivery được xem là hoàn tất |
| **At-least-once** | Có thể nhận lại, hướng đến không mất delivery trong điều kiện cấu hình | Consumer xử lý xong DB nhưng ACK/checkpoint chưa lưu |
| **Broker-level dedup/exactly-once feature** | Khử trùng/transaction trong một **phạm vi xác định** | Không bao phủ API HTTP hoặc SQL bên ngoài phạm vi đó |
| **Exactly-once business effect** | Một thay đổi nghiệp vụ chỉ áp dụng một lần | Cần idempotency, giao dịch DB, key ổn định và/hoặc workflow thích hợp |

Ví dụ: service thanh toán nhận `ChargePayment(paymentId=p100)`, DB đã commit nhưng connection mất trước consumer ACK. Broker có thể redeliver message. Việc “broker bảo đảm at-least-once” là tốt cho **khả năng không bỏ sót delivery**, nhưng listener không được trừ tiền thêm lần nữa.

**Thiết kế an toàn:**

- Producer tạo **`eventId` hoặc `commandId` ổn định**, giữ nguyên khi retry cùng nghiệp vụ.
- Consumer ghi dấu đã xử lý và tác dụng nghiệp vụ trong **cùng transaction** nếu cùng database.
- Với API ngoài (email/payment), truyền **idempotency key** hoặc thiết kế outbox/state machine riêng; transaction SQL nội bộ không rollback được HTTP call.
- ACK hoặc checkpoint chỉ sau khi tác dụng nghiệp vụ đã được ghi nhận theo hợp đồng.
- Retry phải có giới hạn/backoff; lỗi vĩnh viễn phải cách ly để không chặn toàn hệ thống.

### 7.2. Transactional outbox là mô hình xuyên broker

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as Orders DB
    participant REL as Outbox relay
    participant MQ as Broker / Stream
    participant CON as Consumer
    API->>DB: COMMIT order + outbox_event(PENDING)
    REL->>DB: Claim event chưa gửi
    DB-->>REL: eventId, payload
    REL->>MQ: Publish eventId=e42
    MQ-->>REL: Publish result/confirm
    REL->>DB: Đánh dấu SENT khi xác nhận thành công
    MQ->>CON: Delivery e42
    CON->>CON: Idempotency / xử lý nghiệp vụ
    CON-->>MQ: ACK / checkpoint sau commit
~~~

Nếu relay publish xong nhưng chết trước khi cập nhật `SENT`, event được gửi lại. **Outbox thường dẫn tới at-least-once publication**, không tự tạo exactly-once trên toàn hệ thống. Đó là lý do consumer vẫn cần dedup. Ngược lại, nếu đánh dấu `SENT` trước khi broker xác nhận rồi broker không nhận message, sự kiện có nguy cơ bị mất.

Ví dụ PostgreSQL outbox:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX outbox_ready_idx
    ON outbox_event (status, next_attempt_at, created_at);

CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Relay thật cần **claim/lease**, retry backoff, xử lý worker chết và cập nhật trạng thái không đua nhau giữa nhiều instances. Consumer cần dùng unique constraint làm quyết định idempotency; kiểm tra bằng code kiểu `SELECT EXISTS` rồi mới ghi trong hai thao tác không có transaction/khóa có thể gặp race.

### 7.3. Thứ tự chỉ có ý nghĩa trong một phạm vi rõ ràng

Giả sử có:

~~~text
OrderCreated(orderId=7, version=1)
OrderPaid(orderId=7, version=2)
OrderShipped(orderId=7, version=3)
~~~

Không phải broker nào cũng bảo đảm ba sự kiện hoàn tất theo đúng thứ tự ở consumer. Các yếu tố gây đảo thứ tự:

- Nhiều producers/channels/partitions phát cùng lúc.
- Consumer concurrency > 1, xử lý HTTP/DB có thời gian khác nhau.
- Message version 2 bị retry/DLQ, version 3 được xử lý trước.
- Đổi partition count hoặc routing strategy khi mở rộng hệ thống.

Khi cần thứ tự theo `orderId`, dùng **khóa partition/shard nhất quán**, event version và consumer kiểm tra phiên bản trước khi commit. Kafka/stream offset trong một partition hoặc một active consumer trên queue chỉ hỗ trợ **thứ tự giao/đọc ở phạm vi đó**, không tự sửa event bị phát sai version.

### 7.4. Retry và DLQ là hợp đồng ứng dụng, không phải tên tính năng

| Work queue | Stream/log |
|---|---|
| Listener lỗi → NACK/reject/requeue theo policy | Record lỗi → quyết định có tiến checkpoint hay không |
| Có thể dùng DLX, retry queue/TTL, parking queue | Có thể dừng partition, retry tại reader, ghi quarantine hoặc phát vào retry topic/queue |
| Quá nhiều requeue có thể tạo hot loop | Một poison record có thể chặn offset và khiến lag vượt retention |
| Đã ACK thì message rời queue | Checkpoint không xóa record; retention mới dọn |

Một workflow khả dụng phải quy định **lỗi nào retry, tối đa bao nhiêu lần, backoff bao lâu, khi nào cách ly, ai khôi phục và làm sao quan sát**. Không bê nguyên tên `basicNack` của RabbitMQ vào Kafka/SQS/Pub/Sub mà giả định semantics tương đương.

## 8. Các mẫu kiến trúc có thể dùng riêng hoặc phối hợp

### 8.1. Work queue + DLQ cho công việc hữu hạn

~~~mermaid
flowchart LR
    API["Order API"] --> OB["Outbox / durable intent"]
    OB --> P["RabbitTemplate"]
    P --> EX["billing.commands.x"]
    EX --> Q["billing.jobs.q"]
    Q --> W["Billing workers"]
    W -->|"ACK sau commit"| DB["Billing DB"]
    W -->|"Lỗi vĩnh viễn / quá retry"| DL["billing.parking.q"]
~~~

**Dùng khi:** các workers chia công việc, message không cần replay sau ACK, retry và parking-lot quan trọng. Có thể dùng classic/quorum queue tùy durability/quorum/SLO.

**Rủi ro chính:** command bị publish trùng; worker crash sau commit; poison message requeue không giới hạn. Cần outbox nếu event intent không được mất và idempotent consumer.

### 8.2. Event log + projection có replay

~~~mermaid
flowchart LR
    ORD["Orders DB + outbox"] --> REL["Relay"]
    REL --> LOG["Event stream / topic"]
    LOG --> SEARCH["Search projection"]
    LOG --> ANALYTICS["Analytics"]
    LOG --> AUDIT["Audit consumer"]
    SEARCH --> CP["Checkpoint / offset"]
    ANALYTICS --> CP
    AUDIT --> CP
    LOG --> ARC["Archive / snapshot nếu cần lưu dài hạn"]
~~~

**Dùng khi:** cùng một event có nhiều readers độc lập, cần chạy lại logic hoặc backfill. Nếu retention ngắn hơn thời gian consumer có thể ngừng hoạt động, cần archive/snapshot. Nếu consumer có thể quay lại quá khứ, code phải **tương thích schema cũ** và tránh gọi tác dụng ngoài không thể lặp (ví dụ gửi lại email chỉ vì replay analytics).

### 8.3. Kết hợp stream sự kiện với queue xử lý tác vụ

~~~mermaid
flowchart LR
    OS["Orders service"] --> EVT["orders.events.stream"]
    EVT --> PROJ["Search/analytics: replay"]
    EVT --> ADAPT["Event-to-command adapter"]
    ADAPT --> EX["notifications.commands.x"]
    EX --> JOB["email.jobs.q"]
    JOB --> EMAIL["Email workers: ACK/retry/DLQ"]
~~~

**Dùng khi:** muốn giữ event history nhưng vẫn cần job semantics cho hành động một lần. Event-to-command adapter cũng phải **idempotent**: nếu replay record `OrderPaid(e42)` mà adapter tạo nhiều command khác nhau, downstream có thể gửi email trùng.

### 8.4. Request/reply và sự đồng bộ của người dùng

Không phải yêu cầu nào cũng cần broker. Nếu người dùng nhấn nút “Xem giá hiện tại” và phải nhận kết quả trong vài trăm mili giây, HTTP/gRPC có thể đơn giản hơn request/reply qua message broker. RabbitMQ RPC/request-reply hữu ích khi hệ thống đã có messaging contract, nhưng vẫn cần timeout, correlation ID, reply routing, cancellation và nhận thức rằng **request có thể đã được xử lý dù caller timeout**.

Đừng đưa mọi thao tác qua queue rồi giả định đáp ứng được UX đồng bộ. Chọn **communication pattern** trước, rồi chọn transport phù hợp.

## 9. Ví dụ Spring AMQP: chọn RabbitMQ work queue

Đây là trường hợp **một tác vụ do một consumer thực hiện**, có retry/parking và không cần replay đã ACK. Với Spring AMQP, ta có thể khai báo direct exchange, durable queue và dead-letter topology.

~~~java
import org.springframework.amqp.core.*;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BillingQueueTopology {
    public static final String COMMAND_EXCHANGE = "billing.commands.x";
    public static final String JOB_QUEUE = "billing.jobs.q";
    public static final String JOB_KEY = "invoice.create";
    public static final String DLX = "billing.parking.x";
    public static final String PARKING_QUEUE = "billing.parking.q";
    public static final String PARKING_KEY = "invoice.failed";

    @Bean
    DirectExchange billingCommands() {
        return new DirectExchange(COMMAND_EXCHANGE, true, false);
    }

    @Bean
    DirectExchange billingParkingExchange() {
        return new DirectExchange(DLX, true, false);
    }

    @Bean
    Queue billingJobs() {
        return QueueBuilder.durable(JOB_QUEUE)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(PARKING_KEY)
                .build();
    }

    @Bean
    Queue billingParkingQueue() {
        return QueueBuilder.durable(PARKING_QUEUE).build();
    }

    @Bean
    Binding billingJobBinding(
            @Qualifier("billingJobs") Queue queue,
            @Qualifier("billingCommands") DirectExchange exchange) {
        return BindingBuilder.bind(queue).to(exchange).with(JOB_KEY);
    }

    @Bean
    Binding billingParkingBinding(
            @Qualifier("billingParkingQueue") Queue queue,
            @Qualifier("billingParkingExchange") DirectExchange exchange) {
        return BindingBuilder.bind(queue).to(exchange).with(PARKING_KEY);
    }
}
~~~

Một producer publish **command ID ổn định**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public void publishInvoiceCommand(
        RabbitTemplate template, UUID commandId, String json) throws Exception {
    MessageProperties props = new MessageProperties();
    props.setMessageId(commandId.toString());
    props.setContentType(MessageProperties.CONTENT_TYPE_JSON);
    props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);

    Message message =
            new Message(json.getBytes(StandardCharsets.UTF_8), props);
    CorrelationData attempt =
            new CorrelationData(UUID.randomUUID().toString());

    template.send(
            BillingQueueTopology.COMMAND_EXCHANGE,
            BillingQueueTopology.JOB_KEY,
            message,
            attempt);

    CorrelationData.Confirm confirm =
            attempt.getFuture().get(10, TimeUnit.SECONDS);
    if (!confirm.isAck() || attempt.getReturned() != null) {
        throw new IllegalStateException("Publish chưa được xác nhận/route");
    }
}
~~~

Cấu hình bắt buộc cho correlated confirms và mandatory returns:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    listener:
      simple:
        acknowledge-mode: auto
        concurrency: 2
        max-concurrency: 8
        prefetch: 16
        default-requeue-rejected: false
~~~

Đây là **điểm xuất phát kiểm thử**, không phải cấu hình tối ưu chung. `default-requeue-rejected: false` khiến lỗi chưa được xử lý bằng retry policy đi theo đường reject/dead-letter thay vì requeue nóng. Topology mẫu ở trên đưa message lỗi vào **parking queue**, không có retry delay tự động. Nếu nghiệp vụ cần retry tạm thời, hãy thêm cơ chế retry hữu hạn và backoff; đừng đưa mọi lỗi mạng thoáng qua vào parking vĩnh viễn.

Consumer xử lý đồng bộ, để container AUTO ACK **sau khi method trả về thành công**:

~~~java
import java.util.UUID;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
class BillingConsumer {
    private final InvoiceService invoiceService;

    BillingConsumer(InvoiceService invoiceService) {
        this.invoiceService = invoiceService;
    }

    @RabbitListener(queues = BillingQueueTopology.JOB_QUEUE)
    public void handle(Message message) {
        String id = message.getMessageProperties().getMessageId();
        UUID commandId = UUID.fromString(id);
        invoiceService.applyOnce(commandId, message.getBody());
        // Trả về sau DB commit, container mới ACK.
    }
}
~~~

`InvoiceService` là thành phần nghiệp vụ giả định; `applyOnce` phải được implement bằng transaction và unique business key/inbox. Nếu `messageId` bị thiếu/sai định dạng, listener sẽ ném lỗi và message được chuyển tới parking theo policy minh họa. Đừng nuốt exception rồi trả về “thành công” nếu DB thực sự chưa ghi.

**Điểm cần hiểu:** ví dụ cho thấy broker nhận, route và đưa message cho listener, nhưng **publisher confirm không xác nhận consumer đã tạo hóa đơn**. Muốn theo dõi hoàn tất nghiệp vụ, sử dụng trạng thái DB, event phản hồi hoặc workflow thích hợp.

## 10. Ví dụ Spring AMQP: khi quyết định lưu RabbitMQ Stream

Khi yêu cầu là **giữ event để nhiều ứng dụng replay**, ta có thể khai báo **stream queue** trong RabbitMQ:

~~~java
import org.springframework.amqp.core.*;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrdersStreamTopology {
    @Bean
    DirectExchange ordersEventsExchange() {
        return new DirectExchange("orders.events.x", true, false);
    }

    @Bean
    Queue ordersEventsStream() {
        return QueueBuilder.durable("orders.events.stream")
                .withArgument("x-queue-type", "stream")
                .withArgument("x-max-age", "7D")
                .build();
    }

    @Bean
    Binding ordersEventsBinding(
            @Qualifier("ordersEventsStream") Queue stream,
            @Qualifier("ordersEventsExchange") DirectExchange exchange) {
        return BindingBuilder.bind(stream)
                .to(exchange)
                .with("orders.paid");
    }
}
~~~

Một `RabbitTemplate` dùng AMQP 0-9-1 vẫn có thể **publish qua exchange vào stream queue** nếu broker, topology và client configuration phù hợp:

~~~java
rabbitTemplate.convertAndSend(
        "orders.events.x",
        "orders.paid",
        paidEventJson);
~~~

Tuy nhiên:

- `x-queue-type = stream` xác định loại queue tại lúc tạo; **không thể đổi một queue classic đang tồn tại sang stream chỉ bằng redeclare cùng tên**.
- `x-max-age = 7D` là cấu hình giữ dữ liệu ở ví dụ; retention thực tế còn chịu ảnh hưởng segment/limit và phiên bản broker.
- `RabbitTemplate` trên ví dụ vẫn dùng **AMQP 0-9-1**, không tự trở thành stream-native publisher.
- Muốn tận dụng offset/replay và Stream Protocol đầy đủ, đánh giá **`spring-rabbit-stream`**, `RabbitStreamTemplate`, `StreamListenerContainer` và RabbitMQ Java Stream client theo phiên bản thư viện đang dùng.
- Consumer stream phải quản lý **điểm bắt đầu, offset/checkpoint, replay, lag và idempotency**. Đừng thay mỗi kiểu queue rồi coi `@RabbitListener` thông thường tự có các semantics này.

### 10.1. Minh họa đúng thứ tự xử lý offset

~~~text
onStreamRecord(eventId, offset, payload):
    beginDatabaseTransaction()
    inserted = inbox.insertIfAbsent("orders-projection", eventId)
    if inserted:
        updateProjection(payload)
    commitDatabaseTransaction()

    storeCheckpoint(offset) // Sau commit, không phải trước.
~~~

Đây là **pseudocode**, không phải API Java của một phiên bản cụ thể. Nếu crash giữa DB commit và checkpoint, consumer có thể đọc lại record; inbox phải ngăn tác dụng trùng. Nếu checkpoint vượt qua record lỗi mà không có kế hoạch cách ly bền vững, có thể bỏ sót nghiệp vụ khi restart.

## 11. Khi rời RabbitMQ, adapter phải thay cả semantics

Nếu chọn Kafka, SQS hay Pub/Sub, **không chỉ thay dependency** mà vẫn giữ mọi giả định từ `RabbitTemplate`:

| Tầng ứng dụng | RabbitMQ AMQP 0-9-1 | Ví dụ cần thay khi sang nền tảng khác |
|---|---|---|
| Producer API | `RabbitTemplate.convertAndSend` | Kafka producer/`KafkaTemplate`, cloud SDK hoặc adapter |
| Consumer API | `@RabbitListener` | Kafka/managed subscription listener và acknowledgment riêng |
| Địa chỉ | Exchange + routing key + queue/binding | Topic/partition, queue URL, subscription resource, subject |
| Publish result | Publisher confirm + returns | Broker-specific publish ack, error và callback |
| Consume success | `basicAck`/AUTO ack | Offset commit, delete message, ack ID hoặc settlement |
| Retry | NACK/requeue, DLX/TTL | Retry topic, visibility timeout, redrive policy hoặc consumer retry |
| Ordering | Single consumer/shard phù hợp | Partition key, message group ID, sessions hoặc ordering key |
| Observability | Ready/unacked, confirms, redeliver | Lag, offsets, pending/visibility, subscription backlog |
| Security | RabbitMQ user/vhost/permissions, TLS | ACL/SASL, IAM, workload identity, private endpoints |

Một **interface ứng dụng** như `EventPublisher.publish(event)` giúp cô lập phần transport, nhưng không tự biến các broker thành tương đương. Interface nên thể hiện **hợp đồng nghiệp vụ**: event ID, key/thứ tự, kết quả bất đồng bộ, retryability và lỗi định tuyến. Những khả năng đặc thù như replay, subscription seek hay dead-letter có thể cần API riêng thay vì ép vào interface chung quá nghèo nàn.

### 11.1. Điều kiện trước khi đổi broker

1. Xác nhận những tính năng đang dùng: exchange/topic routing, header mapping, persistent delivery, publisher confirms, RPC, TTL, delayed retry, DLQ, transaction synchronization, batch listener.
2. Liệt kê tác vụ hoặc event cần ordering theo key; chỉ ra model tương đương trên broker mới.
3. Viết integration tests cho **kết quả nghiệp vụ**, không chỉ assertion `publish()` không ném exception.
4. Định nghĩa dữ liệu/backfill: event cũ đang ở đâu, có cần replay, offset nào là mốc cutover?
5. Có plan cho duplicate xuyên broker: cùng `eventId` có thể xuất hiện từ nguồn cũ lẫn nguồn mới.
6. Thiết lập vận hành và bảo mật: IAM/secrets/TLS, quota, metrics, alert, backup, incident playbook.

## 12. Migration từ queue sang stream hoặc sang broker khác

Thay hệ thống messaging khi đang có traffic production là một bài toán **di chuyển dữ liệu và semantics**, không chỉ là triển khai client mới. Một sơ đồ migration phổ biến:

~~~mermaid
flowchart TD
    PROD["Producer / business transaction"] --> OB["Canonical outbox"]
    OB --> ROUTE["Relay / migration adapter"]
    ROUTE --> OLD["Old queue / broker"]
    ROUTE --> NEW["New stream / broker"]
    OLD --> OC["Old consumer"]
    NEW --> NC["New consumer"]
    OC --> BIZ["Business DB / side effect"]
    NC --> BIZ
    BIZ --> DEDUP["Idempotency by eventId"]
~~~

Sơ đồ chỉ mô tả khả năng chạy song song; **không khuyến khích bật hai consumer cùng tác động lên dữ liệu production khi chưa có dedup và mốc ownership rõ ràng**.

### 12.1. Đừng dual-write mù quáng từ request thread

Ví dụ code có rủi ro:

~~~java
oldRabbitTemplate.convertAndSend(...);
newKafkaTemplate.send(...);
orderRepository.save(...);
~~~

Ba thao tác thường **không nằm trong một distributed transaction nguyên tử**. Nếu publish old broker thành công nhưng new broker lỗi, hệ thống có hai nguồn không nhất quán. Nếu DB transaction rollback sau khi một publish đã được broker nhận, consumer có thể quan sát event mà database nguồn không commit.

Hướng đáng tin cậy hơn là một **canonical outbox** được commit cùng dữ liệu nghiệp vụ; relay có thể lưu trạng thái gửi/ack **riêng cho từng destination**. Trong thời gian migration, cần xác định destination nào là nguồn phục vụ business effect và destination nào chỉ phục vụ shadow read.

### 12.2. Các bước migration gợi ý

1. **Đóng băng hợp đồng sự kiện**: event ID, aggregate ID, version, schema, timestamp, ordering key, content type và privacy classification.
2. **Kiểm kê toàn bộ topology**: exchange/queue/binding, retry/DLX, số consumers, ACL, publisher confirms, TTL, message size và các tool admin.
3. **Tạo broker/stream đích** với network/TLS/ACL, retention, partition/replication và monitoring riêng; không xóa nguồn cũ.
4. **Xây adapter/relay** từ nguồn dữ liệu canonical. Trường hợp có backfill, dùng snapshot hoặc event archive cùng watermark để tránh khoảng trống/giao trùng không kiểm soát.
5. **Shadow consume** trên đích vào một database hoặc projection cách ly; **không phát sinh side effect thật** khi chưa xác minh.
6. **So sánh kết quả**: số event ID duy nhất, missing/duplicate, latency p95/p99, thứ tự theo aggregate và schema compatibility.
7. **Canary ownership**: chuyển một tập tenant/key có kiểm soát sang consumer đích, bảo đảm mỗi business effect chỉ có một owner hoặc được idempotent bảo vệ.
8. **Cutover có mốc**: ghi lại thời điểm/sequence/watermark và trạng thái backlog của cả hai phía; giữ đường quay lại khi còn hỗ trợ.
9. **Quan sát sau cutover**: consumer lag, retry/DLQ, outbox pending, duplicate detection và tác động nghiệp vụ.
10. **Decommission**: chỉ tắt/huỷ broker cũ sau khi hết retention/buffer, đáp ứng audit và có xác nhận dữ liệu đã được chuyển/lưu đúng.

Nếu stream mới chỉ nhận message **từ thời điểm cutover**, nó không tự chứa lịch sử đã ACK của queue cũ. **Không thể backfill dữ liệu đã biến mất** trừ khi ứng dụng còn event store, outbox archive, database change history hoặc nguồn khác có thể tái tạo hợp lệ.

### 12.3. Khi cần thứ tự trong migration

Giả sử đã phát `OrderPaid(v2)` qua queue cũ, nhưng `OrderShipped(v3)` đến stream mới trước. Consumer mới có thể áp dụng v3 khi v2 chưa xuất hiện. Mốc migration cần được quản lý **theo aggregate key và version**, không chỉ theo thời gian đồng hồ của hai broker.

Các cách giảm rủi ro:

- **Migrate theo shard/key** sau khi drain những event cũ của shard đó, nếu workload cho phép.
- Giữ event version và consumer chỉ apply version kế tiếp; version thiếu thì buffer/retry/quarantine có giới hạn.
- Với backfill từ archive, dùng watermark hoặc committed offset đã được định nghĩa rõ; đừng suy ra thứ tự từ publish timestamp giữa hai broker.
- Nếu thay partition count, kiểm tra key-routing trước và sau cutover vì mapping có thể đổi.

### 12.4. Rollback phải tính tới message đã xử lý ở đích

Rollback **không chỉ đổi endpoint về RabbitMQ cũ**. Nếu new broker/consumer đã apply tác dụng nghiệp vụ, quay lại nguồn cũ có thể xử lý lần nữa.

Một rollback an toàn cần câu trả lời: những `eventId` nào đã commit ở đích, dữ liệu cũ còn giữ hay không, có offset/watermark nào, consumer cũ có thể xử lý phần còn lại mà không ghi trùng không, và các trường hợp schema mới mà consumer cũ không đọc được.

Khi rollback không còn an toàn, có thể cần **roll-forward**, repair có chủ đích hoặc phục hồi snapshot theo playbook. Không giả định Kafka/Pulsar/SQS có thể downgrade hay replay giống RabbitMQ queue.

## 13. Benchmark để so sánh ứng viên

Một benchmark công bằng phải giữ **ngữ nghĩa** và **khối lượng** tương đương. Nếu một hệ thống bật durable replication và confirm còn hệ khác không durable hoặc không chờ ACK, so sánh throughput không có ý nghĩa.

### 13.1. Cố định workload

| Biến | Phải ghi lại |
|---|---|
| Payload | Size trung bình/p95/p99, JSON/Avro/Protobuf, header count, compression |
| Producer | Số instance, batch size, max in-flight, confirm/ack policy, network |
| Consumer | Số group/reader, concurrency, xử lý giả lập/DB thật, max in-flight |
| Durability | Persistent/replicated settings, acks, disk flush và failure assumptions |
| Routing | Fan-out count, key distribution, number of queues/topics/partitions |
| Retention | Thời gian/dung lượng, compaction và cách xử lý consumer chậm |
| Thất bại | Broker restart, network loss, consumer crash, poison message |
| Môi trường | CPU/RAM, disk type, region, TLS, broker version, client version |

### 13.2. Đo đúng điều người dùng cảm nhận

- **End-to-end latency:** từ lúc nghiệp vụ commit ý định gửi đến lúc downstream commit tác dụng và ACK/checkpoint.
- **Publish latency:** từ lúc publish attempt bắt đầu đến khi nhận kết quả broker theo policy; phải tính timeout/in-flight.
- **Consumer lag:** backlog và tuổi message đang chờ, không chỉ số lượng raw messages.
- **Throughput nghiệp vụ:** số event IDs duy nhất được áp dụng thành công mỗi giây, không phải số delivery callbacks.
- **Duplicate/lost-event checks:** số message lặp được xử lý an toàn, số event chưa đến đích, số outbox pending.
- **Recovery:** thời gian phục hồi sau broker/client restart, thời gian bắt kịp backlog và lượng dữ liệu thiếu khi vượt retention.
- **Chi phí:** compute, disk, egress, request, license, support, engineering/on-call và disaster recovery.

### 13.3. Thí nghiệm gợi ý

| Test | Queue candidate | Stream/log candidate | Kết luận cần rút ra |
|---|---|---|---|
| Publish + consume steady state | RabbitMQ queue → worker ACK | Record append → reader checkpoint | Throughput đã commit và latency p99 |
| Fan-out 5 dịch vụ | Exchange → 5 queues | 5 reader groups/subscriptions | Chi phí và lag độc lập |
| Consumer ngừng 24 giờ | Queue backlog/TTL và storage | Offset lag/retention | Có mất khả năng bắt kịp hay không |
| Replay 7 ngày | Dữ liệu đã ACK không còn trong queue | Seek offset khi còn retention | Có đáp ứng yêu cầu rebuild không |
| Poison event | NACK/retry/DLQ | Pause/retry/quarantine/checkpoint | Có chặn toàn luồng hoặc mất thứ tự không |
| Publisher confirm mất | Retry cùng ID, có thể duplicate | Retry cùng ID, có thể duplicate | Idempotent downstream |
| Một node broker hỏng | Quorum/HA theo topology | Replication/quorum theo nền tảng | RTO, message durability và cost |
| 10× burst trong thời gian ngắn | Channel/pre-fetch/consumer scaling | Partition/producer batch/reader lag | Hệ thống backpressure ra sao |
| Backfill một năm | Cần archive/event store | Retention/archive phù hợp hoặc không đủ | Không lầm stream thành lưu trữ vô hạn |

**Chỉ chốt công nghệ sau khi có kết quả workload của chính hệ thống**, hoặc ít nhất có proof of concept đại diện. Nếu chưa có số đo, ghi nhận phương án là **giả thuyết cần kiểm chứng**, không nói “Kafka chắc chắn nhanh hơn RabbitMQ” hoặc ngược lại.

## 14. Chi phí vận hành, an ninh và dữ liệu

Một quyết định broker phải tính cả những phần không xuất hiện trong API:

### 14.1. Toàn bộ chi phí sở hữu (TCO)

~~~text
TCO ≈ Compute
    + Disk/replication/retention
    + Network egress/requests
    + Backup/DR và môi trường dự phòng
    + Security/compliance/audit
    + On-call, nâng cấp và xử lý sự cố
    + Migration, đào tạo và vận hành lâu dài
~~~

Managed service có thể tốn phí sử dụng cao hơn một cấu hình tự host nhỏ, nhưng giảm đáng kể công backup, patch, cluster operations và on-call. Ngược lại, khi throughput lớn và retention nhiều ngày, network egress hoặc storage replication có thể chi phối chi phí. **Không so phí một message độc lập với tổng chi phí vận hành cluster**.

### 14.2. Dữ liệu và quyền replay

Replay tạo thêm rủi ro:

- Nhân viên/dịch vụ có quyền đọc stream có thể truy cập **lịch sử dữ liệu**, không chỉ message mới.
- Retention dài có thể xung đột yêu cầu xóa PII hoặc thời hạn lưu trữ.
- Một consumer mới replay không nên tự gửi lại email/thu tiền nếu hợp đồng chỉ cho phép projection.
- Cần TLS, ACL/IAM, secret rotation, network isolation cho Management/API và audit khi truy cập dữ liệu nhạy cảm.

Khi chọn broker managed, xác nhận **vùng lưu dữ liệu**, encryption/KMS, audit logs, quyền IAM và khả năng private networking. Khi tự host RabbitMQ/Kafka/Pulsar, xác nhận backup/restore và cơ chế DR đã được **thử**, không chỉ có diagram.

### 14.3. Đội ngũ và nợ vận hành

Một hệ thống đã có RabbitMQ, runbook, Prometheus dashboard, alert và team chuyên trách thường có **lợi thế vận hành** so với đưa thêm Kafka/Pulsar chỉ vì một workload mới. Ngược lại, nếu tổ chức đã có data platform Kafka managed với schema registry, CDC và governance, việc dựng thêm RabbitMQ Streams cho cùng mục tiêu cũng có chi phí tích hợp.

Chọn **số nền tảng ít nhất đáp ứng đủ các hợp đồng cần thiết**; tránh “mỗi microservice chọn một broker riêng” nếu chưa có lý do và khả năng vận hành độc lập.

## 15. Ba bài toán lựa chọn mẫu

### 15.1. Dịch vụ tạo hóa đơn: chọn work queue

**Bối cảnh:** API tạo một đơn hàng, lưu trong PostgreSQL và cần tạo hóa đơn không làm chậm response. Có 4 worker, mỗi job mất 0,2–2 giây; lỗi tạm thời có thể thử lại, lỗi định dạng phải cách ly. Không có yêu cầu chạy lại toàn bộ job đã hoàn tất.

**Phương án đầu tiên:** PostgreSQL transactional outbox → RabbitMQ direct exchange → durable work queue → competing `@RabbitListener` workers, ACK sau DB commit, retry hữu hạn và parking queue.

**Quyết định queue type:** nếu có yêu cầu chịu lỗi node nghiêm ngặt và cluster được vận hành đúng, đưa **quorum queue** vào thử nghiệm cùng durability/publisher confirms; nếu workload/HA constraints khác, classic queue vẫn cần được đánh giá theo tài liệu RabbitMQ và chính sách tổ chức.

**Không chọn stream chỉ vì** tương lai có thể có analytics: nếu cần lưu lịch sử hóa đơn, database và event archive có thể đáp ứng; nếu muốn replay domain events để dựng projection, lúc đó bổ sung event stream riêng.

### 15.2. Tái dựng bảng báo cáo đơn hàng: chọn stream/log

**Bối cảnh:** một service search và hai hệ thống phân tích cần đọc cùng `OrderPaid`. Khi phát hiện bug, nhóm phải sửa code và replay ít nhất 14 ngày, kể cả khi các consumer đã chạy thành công.

**Phương án đầu tiên:** RabbitMQ Streams nếu đã vận hành RabbitMQ tốt, retention/capacity và APIs stream-native đáp ứng; hoặc Kafka/managed event log nếu hệ thống đã có data platform thích hợp.

**Điều kiện bắt buộc:** event schema versioned, `eventId` ổn định, ordering key theo `orderId`, offset/checkpoint sau DB commit, inbox dedup, retention có headroom cho downtime + reprocessing, và snapshot/archive khi yêu cầu vượt retention.

**Điểm dễ thất bại:** consumer chạy chậm 16 ngày nhưng retention chỉ 14 ngày; replay không còn đầy đủ. Cần cảnh báo **consumer lag so với khoảng dữ liệu còn giữ**, không chỉ theo message count.

### 15.3. Nền tảng tích hợp liên cloud: đánh giá managed service

**Bối cảnh:** nhiều teams triển khai trên cloud, mục tiêu giảm on-call broker và cần IAM/private network, hỗ trợ region cùng quota rõ ràng.

**Phương án cần POC:** managed queue/pub-sub như SQS, Pub/Sub, Service Bus hoặc managed Kafka theo cloud và tính chất event; không áp sẵn RabbitMQ topology nếu cloud-native service giải quyết tốt hơn.

**Câu hỏi quyết định:** độ trễ liên vùng, chi phí request/egress, vị trí dữ liệu, lock/visibility, retry redrive, thứ tự theo key/session, replay/retention, quyền IAM, SDK Java tương thích, và kế hoạch thoát khỏi vendor.

**Kết luận mẫu:** nếu ứng dụng chỉ giao tác vụ một lần trong AWS, SQS có thể giảm công vận hành. Nếu cùng tổ chức cần replay và xử lý event lớn xuyên nhiều nhóm, nên đánh giá managed log. Không có kết luận chung nếu chưa có SLA và số đo.

## 16. Những nhận định sai cần tránh

| Nhận định sai | Cách hiểu chính xác |
|---|---|
| “Kafka luôn tốt hơn RabbitMQ vì throughput cao hơn” | Cần benchmark theo durability, routing, partitioning, workload và cost thật |
| “RabbitMQ chỉ hỗ trợ queue, không có stream” | RabbitMQ hỗ trợ stream queue/Stream Protocol và super streams |
| “Quorum queue là event log replicated nên có replay” | Quorum queue vẫn xóa message theo ACK, không lưu lịch sử đã ACK để replay tự do |
| “Nhiều dịch vụ nhận event thì bắt buộc dùng Kafka” | RabbitMQ exchange + nhiều queues có thể fan-out và ACK độc lập |
| “Dùng stream thì xử lý được mọi lỗi bằng ACK/NACK giống queue” | Stream-native cần offset/checkpoint, retry/quarantine và retention riêng |
| “Cứ tăng consumer count là xử lý nhanh hơn” | Queue/partition distribution và DB/API capacity có thể là giới hạn |
| “Partitioned log bảo đảm thứ tự toàn hệ thống” | Thứ tự theo partition/key; processing concurrency vẫn có thể đảo completion |
| “Exactly-once của broker nghĩa là DB không thể bị cập nhật hai lần” | Phạm vi broker transaction khác external DB/HTTP; cần idempotency |
| “Publisher confirm ACK chứng minh consumer đã xử lý” | Confirm và consumer ACK/checkpoint là hai giai đoạn riêng |
| “Một queue durable không thể mất message” | Cần hiểu persistent delivery, confirms, topology, replication và failure window |
| “Outbox khiến publish exactly once” | Outbox giữ ý định gửi bền vững, relay có thể publish trùng khi result chưa rõ |
| “Stream giữ dữ liệu cho tới khi mọi consumer đọc xong” | Retention có thể dọn data dù reader chưa bắt kịp |
| “SQS FIFO tự bảo đảm mọi tác dụng nghiệp vụ đúng một lần” | FIFO ordering/dedup có phạm vi, application side effects vẫn cần kiểm soát |
| “Managed broker không cần vận hành” | Vẫn cần IAM, quota, monitoring, cost, retry, incident response và lifecycle |
| “Đổi `RabbitTemplate` sang `KafkaTemplate` là đủ để migration” | Phải chuyển routing/offset/retry/ordering, dữ liệu cũ và operations |
| “Chạy dual-write tới hai broker luôn an toàn” | Hai publish và DB commit thường không nguyên tử; cần canonical outbox/relay và dedup |
| “Một hệ thống chỉ nên có đúng một broker cho mọi message” | Có thể kết hợp queue + stream nếu mục đích rõ, nhưng phải giới hạn phức tạp |

## 17. Checklist và mẫu Architecture Decision Record (ADR)

### 17.1. Checklist bắt buộc

1. **Message contract:** command/job hay domain event? Key định danh, schema version, payload size và ownership đã rõ?
2. **Người nhận:** một worker, một nhóm competing consumers hay nhiều reader độc lập? Có người nhận mới trong tương lai?
3. **Replay:** có cần đọc lại sau ACK không, trong bao lâu, từ nguồn nào nếu quá retention?
4. **Durability:** publisher confirm/ack policy, replication/quorum, backup và RPO/RTO đã được chứng minh?
5. **Ordering:** cần thứ tự theo aggregate nào? Routing/partition key và xử lý version thiếu ra sao?
6. **Idempotency:** event ID ổn định, inbox/unique key và xử lý side effects ngoài DB đã được thiết kế?
7. **Failure:** retry hữu hạn, backoff, poison message, DLQ/quarantine, timeout và khôi phục checkpoint?
8. **Scaling:** producer count, partitions/queues, consumers, prefetch/in-flight, CPU/DB pool và backlog?
9. **Security:** TLS, IAM/vhost/ACL, secret, private network, quyền replay và dữ liệu PII?
10. **Operations:** ai chịu trách nhiệm upgrade, incident, observability, retention, backup/restore và DR?
11. **Cost:** compute/disk/egress/requests/support và engineering hours đã ước lượng tại peak + retention?
12. **Migration:** nếu thay broker, có kế hoạch backfill, shadow read, canary, cutover/rollback và dedup xuyên nguồn?
13. **POC:** có benchmark với workload thật, tác dụng DB thực, broker restart, mất kết nối và consumer chậm?
14. **SLO:** có định nghĩa p95/p99 end-to-end latency, throughput commit, duplicate rate, recovery time và lag threshold?

### 17.2. Mẫu ADR để ghi lại quyết định

~~~markdown
# ADR: Chọn công nghệ messaging cho <tên luồng>

## Context
- Kiểu message, số producer/consumer, throughput, payload
- Routing, replay/retention, ordering và failure assumptions

## Non-negotiable requirements
- RPO/RTO, delivery guarantee, dữ liệu nhạy cảm, region, budget

## Candidates
- Phương án A: RabbitMQ queue (classic/quorum)
- Phương án B: RabbitMQ Streams
- Phương án C: broker hoặc managed service khác

## Evidence
- POC configuration, metrics p95/p99, load, recovery, cost
- Compatibility với hệ thống hiện tại và migration effort

## Decision
- Chọn gì và vì sao; trade-off được chấp nhận

## Consequences
- Runbook, monitoring, schema, idempotency, DLQ/replay
- Kế hoạch thực hiện, rollback, ngày đánh giá lại
~~~

Một ADR tốt **không chỉ ghi tên broker đã chọn**. Nó phải nói rõ các phương án đã bỏ qua, những giả định nếu thay đổi sẽ buộc xem lại quyết định (ví dụ yêu cầu replay từ 7 ngày tăng lên 1 năm) và cách đo sau triển khai.

### Tài liệu chính thức để đối chiếu theo phiên bản

- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/): `RabbitTemplate`, `@RabbitListener`, confirms, listener container và Stream integration.
- [RabbitMQ Queues](https://www.rabbitmq.com/docs/queues), [Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues), [Streams](https://www.rabbitmq.com/docs/streams): loại queue, replication, retention và replay.
- [RabbitMQ Reliability Guide](https://www.rabbitmq.com/docs/reliability): publisher confirms, consumer ACK và failure modes.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/), [Spring for Apache Kafka](https://docs.spring.io/spring-kafka/reference/): topic/partition, offsets, transactions và APIs Spring.
- [Apache Pulsar Documentation](https://pulsar.apache.org/docs/): topics, subscriptions, retention, replication và vận hành.
- [NATS JetStream](https://docs.nats.io/nats-concepts/jetstream): persistent streams, retention policies và consumers.
- [Amazon SQS Developer Guide](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html): Standard/FIFO, visibility timeout và redrive.
- [Google Cloud Pub/Sub](https://cloud.google.com/pubsub/docs/overview): topics/subscriptions, ordering, retention và replay.
- [Azure Service Bus Messaging](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview): queues, topics/subscriptions, sessions và dead-letter.
- [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/): stream IDs, consumer groups và pending messages.

**Kết luận:** Hãy chọn **queue** khi ưu tiên *giao và hoàn tất tác vụ* với competing consumers, ACK/retry/DLQ; chọn **stream/log** khi cần *giữ sự kiện, replay và nhiều nhóm đọc độc lập*; và đánh giá **broker khác hoặc dịch vụ managed** khi yêu cầu về quy mô, cloud, multi-tenancy, bảo mật, hệ sinh thái hoặc chi phí vận hành thật sự tạo lợi thế. Trong mọi trường hợp, thiết kế **event ID, publisher outcomes, ACK/checkpoint, idempotency, retry hữu hạn, observability và phương án khôi phục** trước khi tối ưu throughput. Công cụ phù hợp nhất là công cụ đáp ứng hợp đồng nghiệp vụ với **độ phức tạp có thể vận hành và kiểm chứng được**, không phải công cụ có danh sách tính năng dài nhất.
