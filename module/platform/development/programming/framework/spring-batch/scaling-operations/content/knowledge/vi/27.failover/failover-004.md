# Broker restart và redelivery

Trong một hệ thống Spring Batch phân tán, message broker có thể phải **khởi động lại** do nâng cấp, lỗi tiến trình, mất điện, chuyển leader hoặc sự cố hạ tầng. Khi broker quay trở lại, một số thông điệp có thể **được giao lại (redelivery)**, một số request vẫn nằm trong hàng đợi, một số reply đến muộn, và một số lần publish/ACK có trạng thái **chưa thể xác nhận**. Đặc biệt, worker có thể **đã commit dữ liệu nghiệp vụ** trước khi broker ngắt kết nối. Vì thế, điều quan trọng không phải là cố ngăn mọi redelivery mà là **khôi phục có kiểm soát, không mất công việc và không nhân đôi tác động nghiệp vụ**.

Bài học thuộc chương **Failover** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán phù hợp; đồng thời đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế. Ở đây, chúng ta tập trung vào **broker restart và redelivery** trong các luồng **remote chunking**, **remote partitioning** và xử lý message theo request–reply.

> **Nguyên tắc cốt lõi:** redelivery là một hành vi có thể xảy ra trong cơ chế truyền nhận đáng tin cậy, không nhất thiết là lỗi ứng dụng. **Message được giao hai lần không đồng nghĩa business effect được phép áp dụng hai lần.** Một hệ thống đúng phải chịu được việc đã xử lý nhưng chưa kịp ACK, đã commit nhưng mất reply, hoặc đã publish nhưng chưa nhận được publisher confirm.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **restart broker**, **worker crash**, **network partition**, **broker failover** và **manager restart**.
2. Giải thích trạng thái **ready**, **delivered/unacked**, **acknowledged**, **requeued** và **dead-lettered** trong mô hình queue có ACK.
3. Phân biệt **durable queue**, **persistent message**, **publisher confirm** và **consumer acknowledgment**; hiểu giới hạn của từng cơ chế.
4. Mô tả đường đi của `ChunkRequest`/`ChunkResponse` và `StepExecutionRequest`/reply khi broker gián đoạn.
5. Giải thích vì sao **DB commit và broker ACK không nguyên tử** nếu không có giao thức transaction phối hợp.
6. Thiết kế worker dùng **business key**, unique constraint, transactional outbox và idempotent processing để chống lặp.
7. Xử lý reply **trễ, trùng, thiếu hoặc thuộc JobExecution cũ** mà không ghép sai request.
8. Đặt giới hạn retry/redelivery, backoff, dead-letter/quarantine và xử lý poison message.
9. Viết kịch bản kiểm thử broker restart ở những mốc có kiểm soát và đối soát dữ liệu trước/sau sự cố.
10. Đo backlog, redelivery, unacked, oldest message age, reply timeout và thời gian recovery.

**Tình huống xuyên suốt:** manager gửi những chunk 200 giao dịch qua RabbitMQ tới bốn worker. Mỗi worker tính toán và ghi vào PostgreSQL. Broker bị restart giữa lúc còn 40 request, trong đó một vài chunk đã được worker commit nhưng chưa ACK. Sau khi broker hoạt động lại, worker có thể nhận một số chunk **thêm lần nữa**. Mục tiêu là bảo đảm đầu ra cuối cùng vẫn có đúng mỗi `(batchKey, transactionId)` với giá trị chính xác, và trạng thái Spring Batch không được báo thành công khi còn chunk chưa có outcome hợp lệ.

## 2. Restart broker không đồng nghĩa mọi message sẽ redeliver

Khi broker restart, mỗi message có thể ở một trạng thái khác nhau. Kết quả khôi phục phụ thuộc loại broker, kiểu queue/topic, độ bền dữ liệu, thời điểm publish, trạng thái ACK, retention, replication và cấu hình client.

| Trạng thái trước restart | Sau restart có thể xảy ra | Điều cần xác minh |
| --- | --- | --- |
| Chưa publish thành công | Không có message trên broker hoặc outcome không rõ | Publisher confirm, retry có dedup |
| Đã được broker chấp nhận và lưu bền vững, còn **ready** | Có thể tiếp tục được deliver sau khi phục hồi | Storage, queue durability, retention |
| Đã giao cho consumer nhưng **chưa ACK** | Có thể bị requeue/redeliver khi kết nối cũ mất | Broker ACK/recovery policy, poison handling |
| Đã ACK và broker xử lý ACK bền vững | Thường không được giao lại từ delivery ấy | ACK có thực sự đến broker trước sự cố? |
| ACK đã gửi nhưng kết nối chết, outcome chưa rõ | Có thể redeliver do broker chưa nhận ACK | Worker idempotency |
| Đã vào DLQ hoặc hết TTL | Không tự trở lại request queue như message thường | DLQ/retention/replay policy |
| Reply đã publish nhưng manager chưa nhận | Reply có thể còn, mất hoặc bị giao lại | Reply destination durability và correlation |

**Không suy ra** “broker lên lại là toàn bộ message được chạy lại” hoặc “broker lên lại là mọi message đã ACK đều chắc chắn không còn”. Cần đọc trạng thái hạ tầng và thực hiện kiểm thử trên loại broker/adapter đang dùng.

### Những sự cố thường bị gộp làm một

- **Restart có kế hoạch:** broker đóng kết nối theo quy trình, consumer/publisher reconnect.
- **Crash đột ngột:** broker chết trước khi ghi dữ liệu hoặc ACK kịp tới storage.
- **Leader failover:** node leader chết, replica trở thành leader; có thể có khoảng gián đoạn và xử lý lại theo cơ chế replication.
- **Network partition:** broker vẫn chạy, nhưng worker/manager không biết ACK/confirm đã tới nơi chưa.
- **Worker crash:** broker có thể tiếp tục chạy, nhưng delivery chưa ACK của worker bị đưa lại vào hàng chờ.
- **Manager crash:** worker có thể đã xử lý request, trong khi manager mất trạng thái đợi reply trong RAM.

Thiết kế resilience phải xét **cả mơ hồ về kết quả giao dịch** lẫn **độ bền thông điệp**.

## 3. Luồng remote chunking trong thời gian broker gián đoạn

Trong **remote chunking**, manager giữ `ItemReader`, đọc item và tạo `ChunkRequest`. Worker nhận chunk, thực hiện `ItemProcessor`/`ItemWriter`, rồi trả `ChunkResponse`. Hai đường request và reply có thể dùng hai queue/destination khác nhau.

~~~mermaid
flowchart LR
    subgraph Manager["Manager JVM"]
        RD["ItemReader"]
        MS["Remote chunk manager"]
        MI["Reply input"]
        RD --> MS
        MI --> MS
    end
    subgraph Broker["Broker"]
        RQ[("Request queue")]
        PQ[("Reply queue")]
    end
    subgraph Workers["Worker JVMs"]
        W["Processor + Writer"]
        DB[("Business DB")]
        W --> DB
    end
    MS -->|"ChunkRequest"| RQ
    RQ -->|"Delivery/redelivery"| W
    W -->|"ChunkResponse"| PQ
    PQ --> MI
~~~

Một broker restart có thể cắt cả **request path** lẫn **reply path**. Thậm chí **business DB đã commit** nhưng manager chưa nhận phản hồi. Vì thế không đủ khi chỉ kiểm tra request queue đã rỗng.

### Các câu hỏi phải trả lời sau sự cố

1. Request nào manager đã phát thành công?
2. Request nào đã được broker lưu bền vững?
3. Worker nào đã nhận request và đã commit DB hay chưa?
4. Request nào chưa ACK, có khả năng redelivery?
5. Worker đã phát `ChunkResponse` hay chưa; reply còn ở broker không?
6. Manager đã correlate và ghi nhận response đúng execution/sequence chưa?
7. Có stale message từ JobExecution cũ khi restart hay không?

**Khác với remote partitioning:** remote partitioning chuyển trách nhiệm **đọc dữ liệu vùng partition** sang worker, thường gửi yêu cầu `StepExecution`; remote chunking gửi **items đã đọc** theo chunk. Đơn vị replay và state checkpoint khác nhau, nhưng yêu cầu idempotent business effect vẫn giống nhau.

## 4. Bốn lớp bảo đảm không được đánh đồng

| Lớp | Ý nghĩa | Không tự bảo đảm |
| --- | --- | --- |
| **Durable queue/destination** | Định nghĩa queue còn tồn tại qua broker restart theo hợp đồng broker | Mọi message trên queue đều bền vững |
| **Persistent message** | Producer yêu cầu broker lưu message bền vững khi có queue/topic hỗ trợ | Producer chắc chắn biết publish đã được lưu |
| **Publisher confirm** | Broker xác nhận publish theo chế độ đã cấu hình | Worker đã xử lý, DB đã commit hoặc manager nhận reply |
| **Consumer ACK** | Consumer báo với broker rằng delivery đã được xử lý theo policy | Business DB và reply chắc chắn đã được ghi nguyên tử |

Để bảo vệ **request** và **reply**, phải xem xét **cả topology và thuộc tính message** ở **hai chiều**. Một reply queue không durable có thể biến mất khi broker restart dù request queue vẫn còn. Message persistent trên một queue không durable cũng không tự bảo đảm queue tồn tại sau restart.

**Lưu ý:** ngay cả khi queue durable, message persistent và publisher confirms đều được cấu hình đúng, vẫn có thể xuất hiện **duplicate delivery**. Những tính năng này tăng độ tin cậy về **không mất thông điệp theo hợp đồng broker**, không tạo exactly-once business processing.

### Lựa chọn độ bền cho RabbitMQ

Trong RabbitMQ, các khái niệm thường gặp:

- **Durable queue**: định nghĩa queue được lưu, không bị mất chỉ vì broker restart thông thường.
- **Persistent delivery mode**: message được publish với yêu cầu persistence; còn phụ thuộc cách broker lưu message và queue type.
- **Publisher confirms**: producer biết broker đã xác nhận một publish.
- **Manual consumer ACK**: broker chỉ coi delivery hoàn tất sau khi nhận ACK; khi connection/channel biến mất trước ACK, message có thể được requeue.
- **Quorum queue**: kiểu queue có cơ chế replication/leader election riêng; failover và delivery-limit cần kiểm thử theo phiên bản và chính sách.

**Đừng coi `autoAck=true` là lựa chọn an toàn cho công việc quan trọng:** broker có thể coi request đã tiêu thụ ngay khi giao, trong khi worker chưa kịp commit DB.

## 5. State machine của một delivery

Với queue dùng ACK, có thể hình dung:

~~~mermaid
stateDiagram-v2
    [*] --> READY: publish accepted
    READY --> DELIVERED: broker giao cho consumer
    DELIVERED --> ACKED: broker nhận ACK
    DELIVERED --> REQUEUED: nack/reject requeue hoặc connection loss
    REQUEUED --> DELIVERED: redelivery
    DELIVERED --> DEAD_LETTERED: reject/limit policy
    READY --> EXPIRED: TTL/retention
    ACKED --> [*]
    DEAD_LETTERED --> [*]
    EXPIRED --> [*]
~~~

Đây là **mô hình khái niệm**, không phải state enum hay mọi chuyển trạng thái áp dụng cho tất cả broker. Một số hệ thống dùng **offset/consumer group** chứ không dùng ACK của từng delivery như RabbitMQ.

### Ready, unacked và redelivered không phải ba hàng đợi khác nhau

- **Ready:** message có thể giao cho consumer.
- **Unacked:** delivery đã được gửi tới consumer nhưng broker chưa ghi nhận ACK.
- **Redelivered:** broker gửi lại message sau một lần giao trước đó chưa hoàn tất theo policy.

Tổng `ready + unacked` là một chỉ báo workload đang nằm trong queue/in-flight ở thời điểm lấy mẫu. Nó **không** đại diện tất cả logical operations, vì có thể có request chưa publish, reply đang chờ, message trong DLQ hoặc dữ liệu đã commit ở DB nhưng chưa được manager ghi nhận.

**Không dựa vào một flag redelivered để quyết định có bỏ qua xử lý:** flag có thể phản ánh delivery trước đó, không cho biết transaction business có commit hay không. Ngược lại, thiếu flag không chứng minh business item chưa từng được xử lý trong một request khác.

## 6. Trình tự broker restart và redelivery điển hình

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant B as Broker
    participant A as Worker A
    participant D as Business DB
    participant C as Worker B
    M->>B: Publish chunk C42
    B->>A: Deliver C42 (unacked)
    A->>D: Commit kết quả C42
    Note over B: Broker restart / mất connection
    B--xA: ACK chưa được xác nhận
    Note over B: Khôi phục queue/message bền vững
    B->>C: Redeliver C42
    C->>D: Ghi lại theo idempotency key
    D-->>C: Đã có cùng kết quả / dedup
    C->>B: ACK theo protocol
    C->>B: Publish reply phù hợp
    B->>M: Reply C42
~~~

Sơ đồ chỉ biểu diễn **một khả năng**. Thứ tự ACK và publish reply phụ thuộc integration adapter và transaction setting; broker có thể đã nhận ACK hoặc chưa, producer có thể đã nhận confirm hoặc mất kết nối trước confirm. **Không có một transaction ACID mặc định bao trùm DB, request queue, reply queue và JobRepository.**

Vấn đề khó nhất nằm ở **khoảng thời gian không thể kết luận outcome**:

~~~text
Worker: DB COMMIT thành công
Worker: gửi ACK
Broker: restart đúng lúc ACK đang bay trên mạng
Worker: không nhận được bất kỳ tín hiệu chắc chắn nào
Broker lên lại: có thể giao lại request
~~~

Kết quả đúng là worker mới **có thể xử lý lại yêu cầu**, nhưng business effect đã được áp dụng phải được **phát hiện và không lặp sai**.

## 7. Bảng quyết định theo thời điểm sự cố

| Điểm lỗi | DB business có thể | Trạng thái request có thể | Recovery an toàn |
| --- | --- | --- | --- |
| Trước broker nhận publish | Chưa có kết quả | Message không tồn tại hoặc publish outcome không rõ | Publisher retry có business key ổn định |
| Broker nhận request nhưng chưa deliver | Chưa có kết quả | Ready nếu được lưu bền vững | Tiếp tục deliver sau recovery |
| Worker đã nhận, chưa bắt đầu write | Chưa commit | Unacked, có thể requeue | Redelivery và xử lý từ đầu |
| Worker đang trong DB transaction | Commit hoặc rollback tùy mốc thật | Unacked, connection có thể mất | DB kiểm tra outcome + idempotency |
| Worker đã commit, chưa ACK | **Đã có kết quả** | Có thể requeue/redeliver | Business-key dedup, trả reply phù hợp |
| Worker đã ACK, chưa gửi reply | Đã có kết quả | Request có thể không còn trong queue | Reply reliability/timeout/reconcile |
| Worker gửi reply nhưng chưa có confirm | Đã có kết quả | Reply có thể đã hoặc chưa tồn tại | Retry publish có kiểm soát, manager dedup reply |
| Reply đã lưu nhưng manager chưa nhận | Đã có kết quả | Reply có thể còn ready/unacked | Consumer reconnect, correlate đúng |
| Manager đã match reply nhưng ACK reply mất | Đã có kết quả | Reply có thể bị giao lại | Không tăng completion hai lần |

**Bảng không hứa mọi broker đều phục hồi đúng một cách duy nhất.** Nó giúp xác định chỗ cần test và loại bằng chứng cần thu thập.

## 8. RabbitMQ: ACK, NACK và redelivery sau reconnect

Với RabbitMQ/AMQP, delivery thường được gắn `deliveryTag` trên **channel cụ thể**. ACK sử dụng tag và channel đó; khi connection/channel cũ đóng do broker restart, **không dùng deliveryTag cũ trên channel mới**.

- `basicAck(deliveryTag, false)`: xác nhận delivery trên channel hiện tại.
- `basicNack(deliveryTag, false, true)`: yêu cầu requeue khi policy cho phép.
- `basicReject(deliveryTag, false)` hoặc `basicNack(..., false)`: không requeue; có thể dead-letter nếu queue/DLX được cấu hình, nếu không có thể bị loại theo broker policy.
- **Auto ACK:** broker có thể đánh dấu hoàn tất delivery ngay khi giao, làm mất cơ hội redelivery khi worker chết sau khi nhận.

Với Spring AMQP/Spring Integration, **listener container** có thể tự quản lý ACK theo transaction/acknowledge mode. **Không gọi `basicAck` thủ công trong handler** nếu container đã quản lý ACK theo cấu hình khác; làm vậy có thể gây double-ack hoặc lỗi channel.

### Không nhầm redelivery với “giữ nguyên thứ tự”

Sau requeue, broker có thể đưa message trở lại một vị trí có thể bị ảnh hưởng bởi consumer đang chạy, priority, prefetch và mức độ cạnh tranh. Với nhiều worker, **không được dựa vào thứ tự xử lý hoàn tất**. Nếu cần tuần tự theo tài khoản, hãy chọn owner/partition key có tính tuần tự hoặc dùng cơ chế serialize theo business key.

### Quorum queue và delivery-limit

Quorum queue có những cơ chế bảo vệ và delivery-count/delivery-limit riêng. Khi một message liên tục bị requeue, nó có thể **chạm giới hạn redelivery** và được dead-letter hoặc xử lý theo chính sách queue. Đặc tính mặc định và cách đánh dấu số lần giao phụ thuộc phiên bản RabbitMQ/cấu hình thực tế. Phải kiểm tra policy của deployment thay vì giả định vô hạn lần redelivery.

Đừng thay loại queue từ classic sang quorum ngay trong lúc xử lý sự cố mà chưa lập kế hoạch migration/durability; queue type không phải một thuộc tính có thể đổi tùy tiện mà không có ảnh hưởng dữ liệu.

## 9. JMS và Kafka: không áp dụng máy móc thuật ngữ AMQP

Trong các hệ messaging khác, cùng mục tiêu khôi phục nhưng cơ chế khác nhau:

| Công nghệ | Đơn vị tiến độ | Khi broker/consumer restart | Cần chú ý |
| --- | --- | --- | --- |
| RabbitMQ | Delivery ACK/NACK theo channel | Message chưa ACK có thể được giao lại theo policy | Queue durability, persistence, confirm, prefetch |
| JMS provider | ACK hoặc transacted session theo provider | Message persistent chưa hoàn tất có thể redeliver | `JMSRedelivered`, delivery count, transaction/consumer config |
| Kafka | Offset trong partition và consumer group | Record sau **committed offset** có thể được đọc lại nếu xử lý chưa commit offset hoặc commit không chắc chắn | Offset commit không nguyên tử với DB ngoài nếu không có phối hợp |

**Kafka không có `basicAck` cho từng message như RabbitMQ.** Consumer đọc record theo partition/offset; việc ghi kết quả DB và commit offset là hai hành động khác nhau khi dùng resource độc lập. Nếu DB commit thành công nhưng offset chưa commit, khi consumer restart record có thể được xử lý lại. Nếu commit offset trước khi DB ghi, có thể bỏ mất hiệu ứng nghiệp vụ.

Một số Kafka transactional API có các bảo đảm cho luồng đọc/ghi **nội bộ Kafka** theo cấu hình và hợp đồng, nhưng **không tự làm nguyên tử một transaction ở PostgreSQL bên ngoài**. Với Spring Batch remote chunking dùng Kafka bridge, phải đặc tả request/reply, partition/key và offset handling riêng; không giả định có giao thức tích hợp giống AMQP chỉ bằng việc thay tên queue.

JMS persistent delivery và transacted session cũng không tự bao phủ business DB nếu không có transaction coordination được cấu hình đúng.

## 10. Worker nên ACK vào thời điểm nào?

Không có lựa chọn ACK phù hợp cho mọi hệ thống, nhưng một nguyên tắc nghiệp vụ chung là **không xác nhận hoàn tất delivery trước khi bảo đảm tác động cần thiết đã có thể phục hồi**.

### ACK trước DB commit: nguy cơ mất công việc

~~~text
Worker nhận request R
Worker ACK R ngay
Broker xóa/ghi nhận delivery hoàn tất
Worker crash trước khi DB COMMIT

Không còn request để redeliver theo delivery ấy.
Business DB không có kết quả.
~~~

### ACK sau DB commit: nguy cơ lặp, nhưng có thể bảo vệ

~~~text
Worker nhận request R
Worker COMMIT DB
Worker gửi ACK R
ACK không đến broker do kết nối đứt
Broker redeliver R

Worker mới phát hiện business effect đã tồn tại,
không áp dụng lần hai, rồi phản hồi theo giao thức.
~~~

**ACK sau commit không phải phép màu**: trong remote chunking, manager còn cần reply. Worker có thể ACK request rồi chết trước khi publish reply. Để bảo đảm có thể phục hồi **ý định phát reply**, có thể dùng **transactional outbox**, hoặc cơ chế publish/reply/recovery được framework và adapter bảo đảm theo hợp đồng đã kiểm thử.

### Ranh giới đúng không chỉ là ACK

Phải thiết kế cả bốn phần:

1. **Business effect**: DB đã commit chưa?
2. **Request delivery**: broker còn coi message chưa ACK không?
3. **Reply intent/transport**: đã có bằng chứng bền vững để tạo và gửi phản hồi chưa?
4. **Manager state**: response có được correlate với JobExecution/StepExecution phù hợp chưa?

Nếu không có global transaction, thiết kế cần chấp nhận có **khoảng mơ hồ** và phục hồi bằng replay, idempotency, outbox và đối soát.

## 11. Định nghĩa đúng idempotency key

Một request có thể được broker giao lại nguyên message hoặc manager tạo **request mới** để xử lý lại cùng dữ liệu sau restart. Vì vậy:

- **Message ID** của broker không phải business key; publish lại có thể cấp ID khác.
- **Correlation ID** giúp ghép request với reply; request retry mới có thể có correlation khác.
- **Chunk sequence** có thể khác nếu reader/chunk boundary thay đổi khi restart.
- **JobExecution ID** có thể khác sau restart của cùng JobInstance.
- **Worker hostname** hoặc thread ID không định danh business operation.

Khóa chống lặp phải phản ánh **logical effect**, ví dụ:

~~~text
batchKey       = daily-settlement-2026-11-26
transactionId  = tx-1001
operationType  = normalize

idempotencyKey = (batchKey, transactionId, operationType)
~~~

Khi cùng `tx-1001` xuất hiện trong một request cũ redeliver hoặc một request mới do manager replay, sink vẫn nhận ra **đúng một logical operation**.

### Đừng coi “cùng key” là “cùng nội dung”

Nếu request mới cùng business key nhưng `amount`, snapshot hoặc rule version khác, im lặng `ON CONFLICT DO NOTHING` có thể che giấu bất nhất. Lưu `payloadHash`/rule version và **fail hoặc quarantine** nếu duplicate key mang giá trị không đồng nhất.

## 12. Ví dụ PostgreSQL: ghi kết quả và dedup trong cùng transaction

Giả sử mỗi giao dịch được chuẩn hóa thành một kết quả và có thể phát một event. Dùng **business operation ledger** và output:

~~~sql
CREATE TABLE applied_operation (
    batch_key      VARCHAR(100) NOT NULL,
    operation_id   VARCHAR(160) NOT NULL,
    payload_hash   VARCHAR(128) NOT NULL,
    PRIMARY KEY (batch_key, operation_id)
);

CREATE TABLE normalized_sale (
    batch_key      VARCHAR(100) NOT NULL,
    transaction_id VARCHAR(100) NOT NULL,
    net_amount     NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, transaction_id)
);

CREATE TABLE outbox_event (
    event_id       VARCHAR(200) PRIMARY KEY,
    batch_key      VARCHAR(100) NOT NULL,
    transaction_id VARCHAR(100) NOT NULL,
    payload        JSONB NOT NULL,
    state          VARCHAR(20) NOT NULL DEFAULT 'NEW'
);
~~~

Trong **cùng business DB transaction**, với mỗi item:

~~~text
1. Thử INSERT applied_operation(batch_key, operation_id, payload_hash).
2. Nếu INSERT thành công: ghi normalized_sale và outbox_event.
3. Nếu operation đã tồn tại: kiểm tra payload_hash cũ có khớp.
   - Trùng và giống: không áp dụng hiệu ứng một lần nữa.
   - Trùng nhưng khác: FAIL và điều tra dữ liệu/snapshot.
4. COMMIT cả ledger + output + outbox.
5. Chỉ sau khi có outcome commit rõ, xử lý ACK/request reply theo protocol.
~~~

Ví dụ SQL cấp operation:

~~~sql
-- Bước này chạy TRONG transaction của cùng business resource.
INSERT INTO applied_operation(batch_key, operation_id, payload_hash)
VALUES (:batchKey, :operationId, :payloadHash)
ON CONFLICT (batch_key, operation_id) DO NOTHING
RETURNING operation_id;
~~~

Nếu trả một dòng, đây là operation mới và transaction có thể tiếp tục ghi business effect; nếu không trả dòng, phải **đọc và xác nhận `payload_hash` cũ** trước khi bỏ qua. Các write nghiệp vụ cần được làm trong **cùng transaction** và rollback nếu xảy ra lỗi sau khi chèn ledger.

Unique constraint bảo vệ khi hai worker cùng nhận một operation do redelivery. Không dùng `SELECT COUNT(*)` trước khi INSERT ở một transaction độc lập: hai worker có thể đều nhìn thấy “chưa có” rồi cùng áp dụng hiệu ứng.

### Khi làm việc với một chunk

Đặt ledger và writer trong **transaction chunk** nếu đó là ranh giới nghiệp vụ mong muốn; khi lỗi một item gây rollback cả chunk, những ledger row vừa ghi cũng rollback. Nếu framework cấu hình retry/skip, phải kiểm thử tương tác với transaction và ItemStream checkpoint. Không khẳng định processor chỉ chạy một lần; một item có thể bị process lại trước hoặc sau rollback.

## 13. Transactional outbox cho reply hoặc event cần phát

Nếu worker đã commit business DB nhưng broker restart khiến **reply không gửi được**, một cách thiết kế mạnh hơn là ghi **ý định phát message** trong cùng transaction với business effect:

~~~mermaid
flowchart TD
    R["Worker nhận request"] --> T["Business DB transaction"]
    T --> B["Ghi kết quả + dedup ledger"]
    B --> O["Ghi outbox reply/event"]
    O --> C["DB COMMIT"]
    C --> P["Outbox publisher độc lập"]
    P --> Q[("Broker reply destination")]
    Q --> M["Manager correlate result"]
~~~

Outbox publisher có thể retry khi broker không sẵn sàng. Mỗi **outbox event ID** phải ổn định với **logical message** mà nó đại diện. Publisher cũng phải chịu được tình huống:

~~~text
publish reply thành công
broker nhận message
publisher crash trước khi đánh dấu outbox SENT
publisher restart và publish lại cùng reply
~~~

Kết quả là **duplicate reply có thể xuất hiện**; manager phải correlate và không ghi nhận một chunk hoàn tất hai lần. Outbox giúp giảm khoảng trống **DB commit nhưng không còn bằng chứng phải publish**, nhưng không tự bảo đảm downstream exactly-once.

### Lưu ý đặc biệt với Spring Batch Integration

`ChunkResponse` hoặc kết quả `StepExecution` có **giao thức, sequence và execution metadata** mà Spring Batch mong đợi. Nếu dùng outbox cho reply, phải bảo toàn và tái tạo **đúng message/framework protocol**, không thể thay tùy tiện bằng một JSON `{"status":"SUCCESS"}`. Có thể cần tùy biến integration flow phù hợp với đúng phiên bản thư viện; kiểm thử trong môi trường thực trước khi áp dụng.

Một request **mới** cho cùng business operations có thể cần reply với **correlation mới** sau khi ledger đã nhận biết dữ liệu hoàn tất. Dedup business effect **không được bỏ luôn việc trả lời request mới**. Nên phân biệt **operation completed** với **request reply satisfied**.

## 14. Broker restart và reply bị mất/trùng/trễ

Đường reply cũng có thể gặp broker restart. Hãy xét ba trường hợp:

### A. Reply chưa publish được

Worker đã commit nhưng reply adapter báo lỗi. Nếu ứng dụng chỉ ACK request và quên reply, manager sẽ chờ/timeout. Cần **retry publish**, outbox hoặc một cơ chế reconcile/restart bền vững.

### B. Reply publish thành công nhưng confirm không tới worker

Worker không thể kết luận broker đã lưu reply hay chưa. Nếu retry publish, manager có thể nhận **hai reply**. Không dùng số lượng reply `SUCCESS` để cộng đôi các bộ đếm hoặc đánh dấu hai request đã hoàn tất.

### C. Reply của JobExecution trước đến sau khi manager restart

Ví dụ:

~~~text
JobInstance = settlement-2026-11-26
JobExecution 845: phát request R42
Broker restart; reply R42 chưa đến
Manager restart -> JobExecution 846
Reply cũ của 845 mới xuất hiện
~~~

Manager của 846 không được tự hiểu reply 845 là response hợp lệ cho request khác chỉ vì cùng `chunkSequence=42`. Cần giữ **execution/correlation metadata** và hợp đồng Spring Batch Integration. Với RPC tùy biến, validate `jobExecutionId`, `stepExecutionId`, request attempt và logical work trước khi chấp nhận.

**Không xóa toàn bộ reply queue khi recovery** nếu chưa phân loại stale/valid replies và đối soát outcome. Việc xóa có thể mất bằng chứng về request đã commit.

## 15. Remote chunking và remote partitioning khôi phục khác nhau

| Khía cạnh | Remote chunking | Remote partitioning |
| --- | --- | --- |
| Đơn vị gửi | Chunk gồm các item manager đã đọc | Yêu cầu chạy worker StepExecution/partition |
| Worker có ItemReader? | Thông thường **không** | **Có**; đọc vùng được giao |
| Chỗ lưu reader checkpoint | Thường ở manager | Ở worker StepExecution trong JobRepository |
| Broker restart dẫn tới | Chunk request/reply có thể redeliver/timeout | Partition dispatch/reply có thể bị lặp/timeout |
| Bảo vệ replay | Per-item business key, request correlation/reply handling | Stable partition mapping + checkpoint + idempotent writer |
| Nguy cơ đặc biệt | Đã commit chunk nhưng mất reply; re-chunk khi restart | Hai worker chạy cùng partition nếu leader/owner cũ chưa dừng |

### Rủi ro hai worker cùng một partition

Trong remote partitioning, manager không nên gửi lại partition P7 tới worker B trong khi worker A **có thể vẫn còn chạy** sau một network partition. Broker restart hoặc timeout không chứng minh A đã dừng. Nếu A và B cùng ghi, unique business key có thể hạn chế duplicate, nhưng vẫn có thể xảy ra **conflicting writes** hoặc side effect không idempotent.

Các biện pháp tùy kiến trúc:

1. Dùng JobRepository chung và state/identity đúng `StepExecution`.
2. Có quy tắc **ownership/lease** được kiểm chứng trước khi giao lại.
3. Dùng **fencing token/version** ở sink khi yêu cầu chặn writer cũ.
4. Worker checkpoint và nguồn snapshot phải giữ nguyên khi restart.
5. Không sửa trực tiếp JobRepository để ép `COMPLETED` hoặc chạy lại một partition chưa rõ trạng thái.

Đối với remote chunking, manager cần quản lý `ChunkRequest`/`ChunkResponse`, reader state và outcome theo protocol, không tạo một StepExecution riêng cho mỗi chunk như thể đó là remote partitioning.

## 16. Spring Batch Integration: reply và correlation phải nguyên vẹn

Khi dùng `RemoteChunkingManagerStepBuilder` và `RemoteChunkingWorkerBuilder`, framework cần nhận được **response phù hợp request**. Các channel nội bộ của Spring Integration không phải broker queue:

~~~java
@Bean
MessageChannel managerRequests() {
    return new DirectChannel();
}

@Bean
MessageChannel managerReplies() {
    return new DirectChannel();
}

@Bean
MessageChannel workerRequests() {
    return new DirectChannel();
}

@Bean
MessageChannel workerReplies() {
    return new DirectChannel();
}
~~~

Đường nối thực tế:

~~~text
MANAGER:
  RemoteChunkingManagerStepBuilder
    .outputChannel(managerRequests)
    .inputChannel(managerReplies)

  managerRequests -> broker request outbound adapter
  broker reply inbound adapter -> managerReplies

WORKER:
  broker request inbound adapter -> workerRequests
  RemoteChunkingWorkerBuilder
    .inputChannel(workerRequests)
    .outputChannel(workerReplies)
  workerReplies -> broker reply outbound adapter
~~~

**Điều cần kiểm tra khi broker restart:**

- Các inbound/outbound adapters có **reconnect/redeclare topology/resubscribe** đúng không?
- Request/reply messages có **delivery mode và queue durability** phù hợp không?
- Payload và headers cần cho `ChunkRequest`/`ChunkResponse` có qua converter nguyên vẹn không?
- Worker có gửi reply tới **đúng manager** khi nhiều JobExecution chạy không?
- Khi manager restart, stale reply có được phân loại thay vì ghép sai request không?

**Không tự thay framework payload bằng `String "SUCCESS"`**. Correlation của Spring Batch có thể dựa trên sequence/execution metadata trong payload và headers tùy version; một header `correlationId` riêng không nhất thiết thay thế toàn bộ protocol.

## 17. Broker reconnect: consumer còn sống chưa chắc đã làm việc

Sau broker restart, client có thể đã reconnect TCP nhưng chưa:

- Khai báo lại queue/exchange/binding theo đúng topology.
- Đăng ký lại consumer/subscription.
- Khôi phục publisher confirm mode.
- Dùng lại converter/header mapper tương thích.
- Gắn đúng routing key/destination reply.
- Thiết lập prefetch và ACK mode được yêu cầu.

Do đó **connection healthy** chưa đủ. Cần **readiness probe ở mức chức năng**: có thể publish một request kiểm thử hợp lệ, worker nhận, trả reply, manager correlate thành công; health check không nên làm biến đổi dữ liệu nghiệp vụ ngoài ý muốn.

Trong trường hợp reconnect làm tạo channel mới, delivery tag cũ và consumer state trên channel cũ không còn thích hợp. Không giữ một `Channel` object cũ trong singleton rồi tiếp tục dùng sau failover. Sử dụng cơ chế lifecycle/recovery của client và adapter được cấu hình cho deployment.

### Đừng để reconnect storm làm broker nghẽn thêm

Khi nhiều manager/worker cùng mất kết nối, chúng có thể reconnect và retry publish cùng lúc. Dùng **backoff có jitter**, giới hạn kết nối/consumer và giám sát connection churn. Không retry vô hạn với vòng lặp không delay trong worker thread.

## 18. Prefetch, ordering và backpressure khi backlog quay trở lại

Sau khi broker phục hồi, message ready có thể tăng nhanh, còn consumer chưa bắt kịp. Nếu cấu hình prefetch lớn, một worker có thể giữ nhiều delivery **unacked** trong bộ nhớ/lúc chờ DB, khiến worker khác rảnh nhưng không nhận được việc.

Ví dụ:

~~~text
Request backlog sau restart: 10.000 chunks
Worker consumer threads:      4
Prefetch mỗi consumer:        50
Chunk mỗi lần xử lý:          200 item

Có thể có nhiều delivery đã tới consumer nhưng chưa xử lý xong.
Không đồng nghĩa 4 * 50 chunk đang được DB commit song song.
~~~

**Prefetch** điều tiết số delivery chưa ACK ở phía consumer; **concurrency** quyết định số worker xử lý thật; **chunk size** quyết định số item trong request/transaction theo hợp đồng. Ba số này không hoán đổi cho nhau.

Sau restart:

1. Đo request queue `ready`, `unacked`, oldest age, redelivery rate.
2. Đo worker active, DB connection wait và commit latency.
3. Tránh tăng consumer/concurrency vô hạn làm DB cạn pool.
4. Giới hạn publisher inflight và retry backlog để tránh thổi phồng request.
5. Không giả định redelivery giữ thứ tự; kiểm tra ràng buộc theo business key.

**Một broker queue bền vững không thay thế backpressure**. Queue có thể tiếp tục đầy nếu manager publish nhanh hơn tổng năng lực worker ngay sau recovery.

## 19. Retry, poison message và dead-letter sau restart

Không phải mọi message redelivered đều nên retry mãi. Nếu một chunk chứa dữ liệu sai vĩnh viễn, broker có thể liên tục giao lại chính chunk đó và làm tắc hàng đợi.

| Loại lỗi | Ví dụ | Chính sách gợi ý |
| --- | --- | --- |
| Transient broker/network | Broker tạm chưa sẵn sàng, reconnect | Retry hữu hạn/backoff, không bận chờ vô hạn |
| Transient DB | Deadlock/timeout ngắn | Retry chunk theo cơ chế transaction, exponential backoff |
| Permanent data | Sai schema, thiếu business ID | Quarantine/DLQ có giám sát, không requeue vô hạn |
| Incompatible deployment | Manager/worker dùng serializer khác | Dừng consumer, sửa version; không retry storm |
| Duplicate request hợp lệ | DB đã có cùng business operation | Verify payload hash, không áp dụng effect lại, vẫn phản hồi |
| Duplicate key **khác nội dung** | Cùng transaction ID nhưng amount khác | Fail/alert, không overwrite để che lỗi |
| Unknown outcome | DB commit có thể thành công, reply/ACK mất | Idempotency + đối soát, không khẳng định chưa xử lý |

### DLQ không phải trạng thái COMPLETED

Một message bị dead-letter vì hết retry **không có nghĩa** dữ liệu tương ứng đã được xử lý thành công. Với remote chunking, manager có thể còn chờ `ChunkResponse`; khi request đã vào DLQ mà không có response, job phải báo lỗi/timeout theo hợp đồng. Với remote partitioning, manager phải phát hiện partition thiếu outcome.

Thiết lập:

- **Giới hạn số lần retry/redelivery** thích hợp với loại lỗi và SLA.
- **Backoff và jitter** để tránh tất cả worker retry cùng lúc sau broker restart.
- **DLQ/quarantine** với thông tin đủ truy vết request, job, business key nhưng không rò PII.
- **Quy trình replay** có authorization, snapshot bất biến và idempotency.
- **Cảnh báo** số message DLQ, oldest age, số lần retry và JobExecution bị ảnh hưởng.

Đừng tự `purge` request/reply/DLQ để làm sạch dashboard khi chưa biết status nghiệp vụ. Purge có thể xóa những thông điệp duy nhất còn giúp khôi phục job.

## 20. JobRepository và restart không tự giải quyết mất message

`JobRepository` lưu thông tin `JobInstance`, `JobExecution`, `StepExecution` và `ExecutionContext`. Nó cho phép Spring Batch đánh giá tiến trình/restart theo hợp đồng của step, nhưng **không tự biến broker queue thành storage của DB transaction**.

Khi manager restart sau broker restart:

1. Xác định **cùng JobInstance** hay một job mới, dựa trên identifying JobParameters.
2. Giữ **snapshot/input, partition mapping, business rule version** ổn định.
3. Kiểm tra StepExecution nào `COMPLETED`, `FAILED`, `STARTED`, `UNKNOWN`.
4. Xác định request/reply cũ còn tồn tại trên broker không, và owner hiện tại của chúng.
5. Không tạo hai worker cùng xử lý một partition nếu worker cũ có thể vẫn chạy.
6. Dùng idempotency ở sink để an toàn nếu một chunk hoặc record bị phát lại.
7. Chỉ báo job thành công sau khi **mọi outcome cần thiết** đã được framework ghi nhận và dữ liệu nghiệp vụ đối soát đúng.

### Metadata có thể “lạc hậu” so với business DB

Ví dụ worker commit business DB xong, nhưng mất kết nối trước khi cập nhật reply/JobRepository. Metadata có thể cho thấy chunk chưa hoàn tất dù output đã có. Đừng sửa tay bảng metadata thành `COMPLETED` chỉ vì đã thấy một số record. Thay vào đó, **giữ recovery protocol và đối soát** để framework có thể hoàn tất an toàn.

Nếu metadata và business DB là hai tài nguyên/giao dịch độc lập, phải kiểm thử **DB commit thành công nhưng cập nhật metadata thất bại**. Không suy ra `@Transactional` của worker bao phủ cả hai database và broker.

## 21. Đo độ đúng: đối soát business key, không chỉ queue depth

Giả sử batch dự kiến 1.000.000 transaction, khi broker lên lại request queue có 0 message. Điều đó **không chứng minh** toàn bộ đã xử lý; request có thể đã ACK trước DB commit, expired, vào DLQ hoặc bị định tuyến nhầm.

Với `staged_sale` chứa snapshot input và `normalized_sale` chứa output:

~~~sql
-- Input kỳ vọng nhưng chưa có output.
SELECT s.transaction_id
FROM staged_sale AS s
LEFT JOIN normalized_sale AS n
  ON n.batch_key = s.batch_key
 AND n.transaction_id = s.transaction_id
WHERE s.batch_key = :batchKey
  AND n.transaction_id IS NULL;

-- Output không thuộc snapshot.
SELECT n.transaction_id
FROM normalized_sale AS n
LEFT JOIN staged_sale AS s
  ON s.batch_key = n.batch_key
 AND s.transaction_id = n.transaction_id
WHERE n.batch_key = :batchKey
  AND s.transaction_id IS NULL;
~~~

Kết hợp thêm:

- So sánh **business values** theo rule version, không chỉ COUNT(*).
- Tổng hợp theo tenant, date, partition và dữ liệu được phép skip/filter.
- Kiểm tra `source_hash`/`payload_hash` để phát hiện replay khác nội dung.
- Kiểm tra DLQ/unacked/reply backlog và request đang chờ outcome.
- Kiểm tra side effects ngoài DB, outbox lag và consumer dedup.

**Nếu nghiệp vụ cho phép skip/filter**, tập output kỳ vọng phải được xác định theo quy tắc ấy, kèm audit rõ ràng. Không mặc định mọi input luôn sinh đúng một output.

## 22. Kịch bản kiểm thử broker restart có kiểm soát

Kiểm thử phải thực hiện trên môi trường test có **broker thật hoặc mô hình hạ tầng tương đương**; dùng `DirectChannel` thuần không mô phỏng được durability, ACK và redelivery.

### Chuẩn bị

1. Tạo snapshot dữ liệu bất biến với `batchKey` cố định và các unique business keys.
2. Khai báo request/reply destinations đúng durability/persistence.
3. Kết nối manager + ít nhất hai worker với consumer manual/container-managed ACK theo thiết kế.
4. Ghi nhận `JobExecutionId`, `StepExecutionId`, logical work ID, request correlation và business keys.
5. Có **latch/barrier** ở worker để dừng chính xác trước commit, sau commit hoặc trước reply publish.
6. Dùng DB và broker data volumes không bị xóa khi restart **cùng phiên kiểm thử**.

### Các lượt kiểm thử

| Test | Mốc gây lỗi | Kết quả phải kiểm tra |
| --- | --- | --- |
| A. Restart khi request còn ready | Publish confirmed, chưa worker nhận | Message còn và được deliver theo durability contract |
| B. Restart khi consumer đang unacked | Worker nhận, chưa commit | Redelivery hoặc failure rõ, không mất effect |
| C. Restart sau DB commit trước ACK | Worker commit rồi giữ ACK | Redelivery không tạo duplicate business effect |
| D. ACK đã đến broker trước restart | Worker ACK thành công | Không mặc định reprocess delivery đó |
| E. Mất publisher confirm | Publish có thể đã lưu, confirm đứt | Retry không tạo duplicate logical effect |
| F. Restart sau publish reply trước manager receive | Reply bền vững đang ready | Manager nhận và correlate đúng |
| G. Reply duplicate/late | Worker publish lại sau confirm không rõ | Không tăng completion hai lần |
| H. Hai manager cùng hoạt động | Shared broker và sequence trùng | Reply routing không lẫn job/execution |
| I. Poison request | Worker liên tục fail dữ liệu | Bounded retry, DLQ/alert, không fake COMPLETED |
| J. Restart manager sau broker recovery | Request/reply tồn tại từ run trước | Restart cùng JobInstance và đối soát đầy đủ |

### Latch giúp tạo đúng điểm lỗi

~~~java
final class BrokerRestartProbe {
    final CountDownLatch beforeBusinessCommit =
            new CountDownLatch(1);
    final CountDownLatch allowBusinessCommit =
            new CountDownLatch(1);
    final CountDownLatch afterBusinessCommit =
            new CountDownLatch(1);
    final CountDownLatch allowReply =
            new CountDownLatch(1);

    void pauseBeforeCommit() throws InterruptedException {
        beforeBusinessCommit.countDown();
        if (!allowBusinessCommit.await(20, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout before commit");
        }
    }

    void pauseBeforeReplyAfterVerifiedCommit()
            throws InterruptedException {
        // Chỉ gọi SAU khi business transaction thật sự COMMIT.
        afterBusinessCommit.countDown();
        if (!allowReply.await(20, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout before reply");
        }
    }
}
~~~

Test harness chờ `afterBusinessCommit`, xác minh DB đã commit, rồi cho broker restart hoặc cắt network tại thời điểm mong muốn. **Không gọi `afterBusinessCommit.countDown()` ngay sau `writer.write()` trong transaction vẫn mở**; nó không chứng minh đã commit.

Lưu ý về test broker: **restart process/container trên cùng storage** khác với **xóa rồi tạo broker mới**. Nếu test harness xóa luôn volume, mất message là kết quả của việc hủy storage, không phải chứng minh durability restart thất bại.

## 23. Test tích hợp Spring Batch sau khi broker sống lại

Một integration test có tính thuyết phục cần kiểm tra cả **metadata** và **output**:

1. Chạy remote chunking với nhiều chunk, giữ một chunk sau DB commit.
2. Restart broker trong khi worker chưa xác nhận ACK/reply theo điểm kiểm thử.
3. Cho broker và adapters reconnect; không thay đổi `batchKey` hoặc snapshot.
4. Quan sát redelivery và reply correlation (không khẳng định số lần giao lại cố định ở mọi setup).
5. Xác minh business output có đúng mỗi business key, đúng giá trị và không có side effect lặp.
6. Kiểm tra JobExecution/StepExecution báo kết quả chính xác; nếu chưa thể hoàn tất thì phải **FAILED/timeout hoặc trạng thái cần xử lý** theo contract, không fake success.
7. Nếu cần restart manager, dùng đúng JobInstance và metadata bền vững.
8. Kiểm tra không có orphan message chưa giải quyết trong reply/DLQ liên quan đến batch.

**Unit test ID dedup không thay thế integration test broker**, và integration test chỉ dùng mock ACK không thay thế **crash test process**. Với môi trường production quan trọng, nên có cả test restart broker có kế hoạch, broker SIGKILL, network cut và leader failover (nếu cluster hỗ trợ).

### Vì sao `Thread.sleep` là không đủ?

Một test dùng `Thread.sleep(500)` rồi restart broker không bảo đảm request đã vào trạng thái **unacked** hay DB đã commit. Dùng `CountDownLatch`, instrumentation sau transaction, metrics và xác nhận state ở broker trước khi injection. Đó mới là cách tái hiện chính xác vùng mơ hồ.

## 24. Monitoring và cảnh báo sau broker restart

| Metric/tín hiệu | Nó cho biết gì | Khi bất thường |
| --- | --- | --- |
| Broker uptime/leader changes | Broker có restart/failover không? | Nhiều lần trong thời gian ngắn |
| Connection/channel churn | Client có reconnect ổn định? | Reconnect storm, consumer mất subscription |
| Request queue ready | Message chưa giao | Tăng kéo dài sau recovery |
| Request queue unacked | Delivery chưa ACK | Tăng và không giảm, worker treo/DB chậm |
| Redelivery count/rate | Request được giao lại | Spike sau restart, retry storm |
| Reply queue depth/oldest age | Manager có đang nhận kịp reply? | Reply cũ không được tiêu thụ |
| Publisher confirm latency/timeouts | Producer có nhận được xác nhận? | Nhiều publish outcome mơ hồ |
| DLQ depth/oldest age | Message lỗi cần can thiệp | Bất kỳ poison message mới |
| In-flight chunks/partitions | Manager còn đợi bao nhiêu outcome? | Tăng liên tục hoặc kẹt lâu |
| StepExecution status | Partition nào FAILED/UNKNOWN/STARTED? | Restart không tiến hoặc trạng thái kéo dài |
| DB commit/rollback/duplicate count | Worker xử lý lại có an toàn không? | Duplicate khác giá trị, rollback tăng |
| Business reconciliation mismatch | Input/output có thiếu/trùng/sai? | Không được publish kết quả chưa đúng |

**Không gắn correlation ID của từng message vào metric tag** khi có hàng triệu request; dùng nó trong tracing/log có retention và quyền truy cập phù hợp, metric tổng hợp theo job, step, loại lỗi và hạ tầng.

Một mục tiêu recovery hữu ích là đo:

~~~text
recovery_time =
    thời điểm hệ thống có thể xử lý và đối soát ổn định
    - thời điểm broker bắt đầu gián đoạn
~~~

**Broker healthy** không đồng nghĩa **batch recovered**. Đo cả thời gian broker lên, thời gian consumer reconnect, backlog drain, thời gian manager nhận đủ reply và thời gian đối soát business output.

## 25. Runbook khi broker vừa khởi động lại

Khi nhận cảnh báo broker restart hoặc request redelivery tăng:

1. **Khoanh vùng:** thời điểm broker ngừng/khôi phục, cluster/node, queue/topic, deployment manager/worker chịu ảnh hưởng.
2. **Xác minh broker durability:** topology tồn tại, storage/replica khỏe, request và reply destinations đúng, không có queue bị đổi type hoặc TTL.
3. **Xác minh kết nối:** client reconnect/re-subscribe, consumer count, publisher confirms, routing key và converter/header mapping.
4. **Đo backlog:** ready/unacked, oldest age, redelivery rate, DLQ, reply latency và manager in-flight.
5. **Xem JobRepository:** JobExecution/StepExecution nào đang RUNNING, FAILED, UNKNOWN; có partition/worker nào còn active thực không?
6. **Xác định outcome mơ hồ:** request nào có thể đã commit DB nhưng chưa ACK/reply, request nào chưa có dấu hiệu được xử lý.
7. **Đối soát business DB:** business keys, giá trị, source snapshot và outbox/side effects; không chỉ dựa vào queue depth.
8. **Điều tiết replay:** giới hạn consumer, prefetch, publish retry và DB pool; tránh retry storm khi broker vừa sống lại.
9. **Khôi phục theo protocol:** sửa routing/adapter hoặc lỗi dữ liệu, xử lý DLQ có kiểm soát, restart đúng JobInstance nếu phù hợp, không dispatch trùng worker chưa dừng.
10. **Xác nhận hoàn tất:** metadata Spring Batch đạt trạng thái đúng, dữ liệu nghiệp vụ khớp và không còn orphan/stale messages cần can thiệp.
11. **Đóng incident:** ghi nguyên nhân, thời gian recovery, metric, bản kiểm thử đã tái hiện và thay đổi vận hành.

**Không tự purge queue/DLQ, không xóa dữ liệu kết quả đã commit, không sửa trực tiếp StepExecution thành `COMPLETED`** để làm hết cảnh báo. Những hành động đó có thể che dấu nguồn gốc dữ liệu thiếu hoặc làm side effect bị thực hiện hai lần.

## 26. Các lỗi thiết kế phổ biến

| Triệu chứng | Nguyên nhân điển hình | Cách sửa |
| --- | --- | --- |
| Restart broker làm mất request | Queue non-durable, message non-persistent, publish không confirm | Thiết kế lại durability/publisher confirm, kiểm thử |
| Worker đã commit nhưng request chạy lần nữa | ACK mất, consumer reconnect hoặc broker redelivery | Business-key idempotency, đừng coi là lỗi logic mặc định |
| Duplicate dữ liệu sau restart | Writer dùng additive update hoặc key sai | Dedup ledger + transaction, unique constraint |
| Reply queue rỗng nhưng manager còn chờ | Reply mất, sai route, bị consumer khác ACK | Kiểm tra reply destination/correlation, reconcile |
| Broker nhận reply hai lần | Publisher mất confirm rồi retry | Manager dedup reply theo protocol |
| Worker không reconnect dù broker healthy | Listener subscription/adapter lifecycle lỗi | Health/readiness end-to-end, recovery config |
| Message liên tục redeliver | Poison payload hoặc worker luôn rollback | Bounded retry, DLQ và alert |
| Queue ready giảm nhưng output thiếu | Auto ACK sớm, TTL/expiry hoặc sai writer | ACK policy, đối soát DB, kiểm tra DLQ |
| Queue unacked rất cao | Prefetch rộng, DB/worker quá chậm | Giảm prefetch/concurrency, tối ưu bottleneck |
| Hai worker cùng chạy một partition | Retry dispatch khi owner cũ còn sống | Lease/fencing/ownership + JobRepository |
| Restart manager làm phản hồi cũ match nhầm | Chỉ dựa chunk sequence, thiếu execution identity | Bảo toàn protocol/correlation, kiểm tra stale reply |
| Kafka consumer replay sau restart | DB commit trước offset commit | Idempotent sink, offset/transaction policy phù hợp |
| Job COMPLETED nhưng payment hai lần | Side effect không có idempotency | Operation key tại external API, outbox/dedup |
| Không biết outcome sau broker failover | Thiếu logs, confirm, ledger, correlation | Tracing, publish/reply metrics, reconciliation |

## 27. Bài thực hành cuối bài

**Bài thực hành:** triển khai Spring Batch remote chunking với manager đọc 20.000 record từ snapshot bất biến, chunk size 200, hai worker và một RabbitMQ broker có request/reply destinations. Writer sử dụng khóa `(batchKey, transactionId)` cùng cơ chế phát hiện conflict khác nội dung.

Thực hiện theo thứ tự:

1. **Baseline:** chạy bình thường, xác minh đủ output và reply hợp lệ.
2. **Durability:** publish request rồi restart broker trước khi worker nhận; so sánh queue/persistent/confirm setup.
3. **Unacked redelivery:** giữ một worker sau khi nhận nhưng trước commit, restart broker và kiểm tra recover.
4. **Commit–ACK gap:** giữ sau DB commit nhưng trước ACK/reply, restart broker; replay không làm tăng số business effects.
5. **Reply gap:** worker commit và reply bị chặn; kiểm tra manager timeout/restart và phục hồi hợp lệ.
6. **Poison message:** thêm một item lỗi schema; kiểm tra retry có giới hạn, DLQ, status job và runbook.
7. **Multiple consumers:** tăng worker từ 2 lên 4, kiểm tra prefetch, redelivery, ordering và concurrency.
8. **Manager restart:** restart cùng JobInstance trong lúc còn in-flight requests; bảo toàn snapshot và idempotency.
9. **Test sai có chủ đích:** bật auto ACK và kill worker trước DB commit để thấy rủi ro mất công việc.
10. **Load test:** đo thời gian broker hồi phục, queue drain, DB pool, reply latency và tổng thời gian hoàn tất job.

### Checklist triển khai production

- [ ] Đã phân biệt broker restart, broker failover, worker crash, manager crash và network partition.
- [ ] Request **và reply** có durability/persistence phù hợp SLA, được xác nhận bằng integration test.
- [ ] Producer sử dụng publisher confirm và xử lý trạng thái publish không chắc chắn bằng retry an toàn.
- [ ] Consumer ACK/transaction policy không xác nhận work trước khi có bằng chứng outcome bền vững.
- [ ] Không giả định DB commit, request ACK, reply publish và manager match là một transaction.
- [ ] Worker idempotent theo business key ổn định, phát hiện duplicate khác nội dung.
- [ ] Nếu cần, có outbox cho reply/event và manager chịu được duplicate reply.
- [ ] Correlation/sequence/JobExecution metadata của Spring Batch Integration được giữ nguyên qua converter/adapters.
- [ ] Có giới hạn retry, backoff/jitter, DLQ, quarantine và chính sách replay rõ ràng.
- [ ] Có readiness kiểm tra end-to-end sau broker reconnect, không chỉ health TCP.
- [ ] Có giới hạn prefetch, worker concurrency, in-flight và DB/API capacity.
- [ ] Có test restart tại các mốc ready, unacked, sau commit, trước reply và manager restart.
- [ ] Có đối soát input/output và kiểm tra JobRepository/side effects trước khi xác nhận job thành công.
- [ ] Có runbook và dashboard cho redelivery, ACK, publisher confirm, backlog, reply timeout và recovery time.

**Ghi nhớ:** khi broker restart, **redelivery là một khả năng khôi phục bình thường**, không phải bằng chứng rằng worker đã hoặc chưa commit. Spring Batch phân tán cần bảo vệ toàn bộ chuỗi **publish → durable transport → worker transaction → ACK/reply → manager correlation → JobRepository**. Bền vững ở broker giúp giảm nguy cơ mất message; **idempotent business effects, dữ liệu nguồn bất biến, retry/restart đúng protocol và đối soát** mới giúp kết quả cuối cùng đáng tin cậy khi các thành phần lỗi ở những thời điểm khác nhau.
