# Khi nào dùng stream thay cho queue tiêu thụ thông thường

Trong hệ thống dùng **RabbitMQ và Spring AMQP**, queue thông thường rất phù hợp để phân phối công việc bất đồng bộ: producer gửi message qua exchange, broker định tuyến tới queue, `@RabbitListener` nhận, xử lý rồi ACK. Nhưng có những bài toán cần giữ **lịch sử sự kiện** sau khi xử lý xong, cho nhiều ứng dụng đọc lại dữ liệu hoặc xây dựng lại bảng tổng hợp sau sự cố. Khi đó, **RabbitMQ Streams** là một lựa chọn đáng cân nhắc.

Điểm quyết định không đơn thuần là “stream nhanh hơn queue”. **Queue thông thường phục vụ việc giao công việc cần hoàn thành; stream phục vụ việc lưu và đọc lại chuỗi sự kiện theo offset.** Hai mô hình có vòng đời dữ liệu, ACK/checkpoint, cách mở rộng consumer và cách xử lý lỗi khác nhau.

Bài học thuộc chương **RabbitMQ Streams** của module **SPRING_AMQP**. Ta sẽ phân biệt classic/quorum queue với stream, xác định khi nào cần replay, retention, nhiều nhóm consumer và thứ tự sự kiện; tiếp đó liên hệ `RabbitTemplate`, `@RabbitListener`, exchange, binding và tích hợp stream-native của Spring AMQP.

## 1. Hàng đợi công việc và nhật ký sự kiện

Giả sử hệ thống thương mại tạo các sự kiện `OrderCreated`, `OrderPaid` và `OrderShipped`.

**Với queue tiêu thụ thông thường**, các instance consumer cùng đăng ký trên một queue là các **competing consumers**: mỗi message được giao cho một consumer tại một thời điểm. Khi consumer xử lý thành công và broker ghi nhận ACK, message rời hàng đợi. Nếu consumer mất kết nối trước ACK, broker có thể giao lại message. Để một nhóm nghiệp vụ khác nhận bản sao của cùng sự kiện, thường tạo queue riêng và binding vào exchange.

**Với stream**, broker lưu message như những bản ghi trong một **append-only log**. Mỗi bản ghi có vị trí gọi là **offset**. Consumer đọc theo offset, theo dõi tiến độ của riêng mình và có thể đọc lại từ một vị trí cũ khi dữ liệu còn trong thời hạn giữ lại (*retention*). Consumer đọc xong **không làm bản ghi biến mất** khỏi stream.

~~~mermaid
flowchart TB
    subgraph Q["Queue thông thường"]
        P1["Producer"] --> EX1["Exchange"]
        EX1 --> W["orders.work.q"]
        W --> WA["Worker A"]
        W --> WB["Worker B"]
        WA --> ACK["ACK: hoàn tất công việc"]
        WB --> ACK
    end
    subgraph S["RabbitMQ Stream"]
        P2["Event producer"] --> ST["Stream: offsets 0, 1, 2, 3..."]
        ST --> CA["Projection: offset 100"]
        ST --> CB["Analytics: offset 80"]
        ST --> CC["Audit: replay lịch sử"]
    end
~~~

Trong phần queue, Worker A và B **chia nhau** công việc. Trong phần stream, Projection, Analytics và Audit có **tiến độ đọc độc lập** trên cùng một nguồn dữ liệu, nên tất cả đều có thể đọc cùng một sự kiện.

### So sánh bản chất

| Câu hỏi | Classic/quorum queue | RabbitMQ stream |
|---|---|---|
| Message còn lại sau ACK thành công? | Thông thường **không** | **Có**, đến khi retention dọn dữ liệu |
| Vị trí đọc | Broker theo dõi delivery chưa ACK | Consumer theo dõi **offset/checkpoint** |
| Đọc lại message đã xử lý? | Không thể replay từ chính queue sau khi message bị xóa | Có, nếu offset vẫn nằm trong retention |
| Nhiều instance cùng một queue | Chia delivery giữa các competing consumers | Consumer độc lập có thể cùng đọc một bản ghi |
| Nhiều ứng dụng cùng nhận sự kiện | Một queue/binding cho mỗi ứng dụng | Nhiều reader cùng một stream, mỗi reader có tiến độ riêng |
| Cách quản lý dung lượng | ACK, TTL, chiều dài queue và policy phù hợp | Retention theo **thời gian và/hoặc dung lượng** |
| Retry khi lỗi | ACK/NACK, requeue, DLX và retry queue | Retry tại reader, checkpoint, cách ly record lỗi |
| Mục tiêu chính | Phân phối tác vụ, command, job | Event log, replay, nhiều reader, dữ liệu liên tục |
| API Spring AMQP thường dùng | `RabbitTemplate`, `@RabbitListener` | Có tích hợp `spring-rabbit-stream` cho Stream Protocol |

**Quorum queue không phải stream.** Quorum queue là một loại queue có cơ chế replication/đồng thuận, vẫn dùng cách xử lý delivery và ACK của queue thông thường. Stream dùng nhật ký giữ bản ghi để các consumer có thể quay lại đọc.

## 2. Khi nào nên giữ queue thông thường?

Queue vẫn là lựa chọn tốt trong các trường hợp:

- **Một job cần một worker thực hiện:** tạo PDF, gửi email, xử lý ảnh hoặc gọi API đối tác.
- **Competing consumers:** nhiều instance `@RabbitListener` chia tải, sau xử lý thành công không có nhu cầu đọc lại job cũ.
- **Retry và dead-letter theo từng delivery:** NACK, requeue, DLX, retry queue với TTL và parking-lot queue là các mẫu quen thuộc.
- **Request/reply:** một yêu cầu cần một kết quả, có correlation ID và reply queue thích hợp.
- **Backlog ngắn hạn:** cần prefetch, concurrency, ACK và redelivery khi worker chết, nhưng không cần giữ lịch sử đã ACK.

Ví dụ:

~~~text
POST /orders
    |
RabbitTemplate -> billing.requests.x -> billing.jobs.q
                                           |
                                 @RabbitListener workers
                                           |
                              Tạo hóa đơn thành công -> ACK
~~~

Khi hóa đơn đã được tạo, giữ lại mọi message yêu cầu tạo hóa đơn nhiều ngày thường không có giá trị. Stream có thể tạo thêm chi phí quản lý offset và retention mà không phục vụ mục tiêu này.

Nếu **nhiều ứng dụng** muốn nhận cùng sự kiện nhưng **không cần replay**, một exchange với nhiều queue vẫn đáp ứng:

~~~text
orders.events.x
    |-- billing.events.q
    |-- inventory.events.q
    +-- notification.events.q
~~~

Mỗi queue có ACK/retry riêng. Việc có ba loại consumer **không tự động bắt buộc dùng stream**; câu hỏi là dữ liệu cũ có cần được đọc lại sau khi đã xử lý hay không.

## 3. Dấu hiệu nên chọn RabbitMQ Streams

### 3.1. Cần replay để xây dựng lại trạng thái

Ví dụ `sales_summary` được cập nhật từ các sự kiện đặt hàng. Khi phát hiện lỗi tính toán, bạn muốn sửa mã và **chạy lại sự kiện trong 30 ngày** để xây dựng bảng mới.

Với queue đã ACK, dữ liệu cũ không còn để replay từ chính queue. Với stream có retention phù hợp, một consumer mới có thể bắt đầu từ offset cũ và dựng lại projection mà không cần các producer phát lại toàn bộ lịch sử.

~~~mermaid
flowchart LR
    P["Orders service"] --> ST["orders.events.stream"]
    ST --> LIVE["Projection v1: đọc tiếp"]
    ST --> NEW["Projection v2: replay từ offset cũ"]
    ST --> AUD["Audit: truy xuất lịch sử"]
~~~

**Giới hạn:** replay chỉ có dữ liệu **còn nằm trong stream**. Nếu retention là 7 ngày thì không thể dựng lại 1 năm lịch sử đã bị xóa. Với nhu cầu audit dài hạn, thường cần thêm kho lưu trữ riêng.

### 3.2. Nhiều consumer độc lập, tiến độ khác nhau

Ví dụ: dịch vụ tìm kiếm cập nhật index nhanh; dịch vụ phân tích chạy chậm; dịch vụ phát hiện gian lận cần quét lại dữ liệu từ ngày triển khai mô hình mới. Các nhóm đó không muốn consumer nhanh xóa dữ liệu trước khi consumer chậm có cơ hội đọc. Stream phù hợp khi mỗi nhóm quản lý offset của mình và chấp nhận chính sách retention chung.

### 3.3. Sự kiện có giá trị vượt quá một lần xử lý

`OrderPaid`, `InventoryAdjusted` hoặc `AccountBalanceChanged` mô tả **sự kiện đã xảy ra**. Chúng có thể phục vụ nhiều ứng dụng hiện tại hoặc ứng dụng mới được triển khai sau này. Ngược lại, `SendEmailNow`, `GenerateReportJob` là **lệnh giao việc**, thường thích hợp hơn với queue.

### 3.4. Dữ liệu liên tục, thông lượng lớn

Stream được thiết kế cho thao tác append/read tuần tự, có thể phù hợp với telemetry, clickstream và event pipeline. Nhưng “thông lượng cao” **không đủ để chứng minh stream tốt hơn**: phải benchmark cùng kích thước message, độ bền, replication, số producer/consumer, băng thông, disk I/O, batching và yêu cầu độ trễ.

## 4. Offset, checkpoint và retention: bộ ba quyết định

### 4.1. Offset là vị trí trong một stream

Offset thể hiện vị trí mà broker gán cho một record. Consumer có thể bắt đầu từ đầu dữ liệu còn giữ, một vị trí chỉ định, hoặc cuối log theo cơ chế hỗ trợ của stream client.

~~~text
Stream:
    offset:     100   101   102   103   104   105
    event:       A     B     C     D     E     F

Projection: đã xử lý đến offset 103
Analytics:  đã xử lý đến offset 101

Sau restart:
    Projection tiếp tục từ 104
    Analytics tiếp tục từ 102
~~~

Offset **không phải event ID nghiệp vụ** và **không phải sequence toàn cục giữa nhiều stream**. Khi chia dữ liệu ra nhiều partition, mỗi partition có offset riêng. Thứ tự nghiệp vụ theo `orderId` vẫn cần event version được cấp ở nguồn.

### 4.2. Checkpoint phải theo sau tác dụng nghiệp vụ

Giả sử consumer cần xử lý record offset 104 và cập nhật database. Nếu nó **lưu checkpoint 104 trước khi database commit**, rồi chết giữa chừng, lần khởi động sau có thể bỏ qua 104 dù chưa ghi nghiệp vụ thành công.

~~~mermaid
sequenceDiagram
    participant S as Stream
    participant C as Consumer
    participant DB as Database
    participant O as Offset store
    S->>C: Record offset 104
    C->>DB: Ghi nghiệp vụ và dấu vết dedup
    DB-->>C: COMMIT
    C->>O: Lưu checkpoint 104
    Note over C,O: Crash trước checkpoint có thể đọc lại 104
~~~

Thứ tự thường dùng:

1. Đọc record gồm `eventId` và offset.
2. Trong database transaction, ghi tác dụng nghiệp vụ và dấu vết xử lý thành công theo `eventId`.
3. Commit database trước.
4. Sau commit, lưu offset/checkpoint để lần sau tiếp tục.

Crash sau DB commit nhưng trước checkpoint vẫn gây **đọc lại**. Vì vậy, chỉ kiểm soát offset chưa tạo *exactly-once business effect*. Cần consumer **idempotent** với unique constraint, ví dụ `(consumer_name, event_id)`.

### 4.3. Retention không chờ consumer chậm

Stream được giữ theo chính sách như **thời gian**, **dung lượng** hoặc kết hợp. Broker dọn dữ liệu theo **segment**, nên mốc thời gian/dung lượng xóa thực tế có thể không chính xác từng giây hay từng message.

**Consumer chậm có thể mất điểm đọc** nếu segment chứa offset cần thiết đã bị dọn, ngay cả khi consumer chưa xử lý xong. Khác với queue thường, retention của stream **độc lập** với tiến độ đọc.

~~~text
Stream retention: 3 ngày
Analytics ngừng hoạt động: 5 ngày

Khi chạy lại, offset đã checkpoint có thể không còn trong stream.
=> Phải phục hồi bằng snapshot, kho lưu trữ khác,
   hoặc chính sách bắt đầu lại được quyết định rõ ràng.
~~~

Đo **consumer lag**, tuổi record sớm nhất còn lưu và tốc độ sinh dữ liệu. Nếu cần replay 30 ngày, đừng chỉ khai báo retention 30 ngày rồi mặc định đủ: dung lượng, chính sách đồng thời, segment và lượng dữ liệu thực tế đều ảnh hưởng đến thời gian giữ khả dụng.

## 5. Thứ tự và mở rộng consumer

### 5.1. Thứ tự trong log không tự là thứ tự nghiệp vụ

Broker ghi record vào một stream theo thứ tự log mà consumer có thể đọc qua offset. Nhưng **nhiều producer sử dụng connection/channel khác nhau** có thể gửi event bị xen kẽ: `OrderPaid(v2)` đến trước `OrderCreated(v1)` dù nghiệp vụ tạo v1 trước. Offset là **thứ tự ghi thực tế của stream**, không chứng minh version nghiệp vụ đúng.

Ngay cả khi record được đọc theo offset, ứng dụng dùng executor bất đồng bộ có thể hoàn tất offset 102 trước 101. Nếu thật sự cần thứ tự theo `orderId`, phải dùng key partition nhất quán, version check, xử lý tuần tự trong partition phù hợp và chiến lược phục hồi khi thiếu version.

### 5.2. Consumer độc lập không giống nhóm competing consumers

Với queue, thêm worker vào một queue chia delivery và tăng parallelism. Với stream, mở thêm consumer **độc lập** có thể khiến mỗi consumer đều đọc toàn bộ record. Nếu muốn nhiều worker **chia nhau** dữ liệu theo khóa, cần mô hình phân vùng và assignment phù hợp.

**Super streams** là cơ chế RabbitMQ tổ chức luồng dữ liệu thành nhiều stream/partition để scale. Producer route theo key; consumer có thể được gán các partition theo cơ chế phía client/ứng dụng. Khi đó có thể giữ thứ tự *trong một partition* và xử lý song song giữa nhiều partition.

~~~mermaid
flowchart TB
    P["Nhiều producers"] --> HASH["partition theo orderId"]
    HASH --> S0["events.partition.0"]
    HASH --> S1["events.partition.1"]
    HASH --> S2["events.partition.2"]
    S0 --> C0["Worker phụ trách P0"]
    S1 --> C1["Worker phụ trách P1"]
    S2 --> C2["Worker phụ trách P2"]
    C0 --> DB["Projection database"]
    C1 --> DB
    C2 --> DB
~~~

Đừng xem `concurrency=8` của một listener AMQP thường là tương đương “8 workers chia stream”. Khi scale cần kiểm tra số partition, khóa định tuyến, cơ chế gán consumer, checkpoint và khả năng một record lỗi chặn partition. Thay đổi số partition cũng có thể làm đổi tuyến của key và ảnh hưởng thứ tự.

## 6. Spring AMQP: chọn đúng giao thức và API

RabbitMQ có thể cung cấp stream qua **AMQP 0-9-1** ở dạng stream queue; đồng thời có **RabbitMQ Stream Protocol** riêng để khai thác khả năng stream-native. Cùng một tài nguyên stream nhưng API và cách theo dõi offset không giống nhau.

| Phương án | API trong Java/Spring | Phù hợp | Lưu ý |
|---|---|---|---|
| Classic/quorum queue | `RabbitTemplate`, `@RabbitListener`, SMLC/DMLC | Job/command, retry, DLQ | ACK/NACK, prefetch, concurrency |
| Stream queue qua AMQP 0-9-1 | `RabbitTemplate` publish, AMQP consumer với arguments thích hợp | Tích hợp AMQP hiện có, dùng một phần tính năng stream | Chọn vị trí đọc và prefetch theo yêu cầu stream queue |
| Stream Protocol | RabbitMQ Java Stream client, module `spring-rabbit-stream` | Replay, stream producer/consumer, offset | Environment, `RabbitStreamTemplate`, `StreamListenerContainer`, checkpoint |

**`RabbitTemplate` không tự chuyển sang Stream Protocol** chỉ vì routing key đi đến stream queue. Nó tiếp tục publish bằng AMQP 0-9-1. Tương tự, `@RabbitListener` thông thường không tự có mô hình offset/checkpoint của stream-native client. Khi dùng Stream Protocol, cần thư viện và listener container tương ứng của Spring AMQP.

### 6.1. Khai báo một stream queue với Spring AMQP

Ví dụ khai báo stream queue, exchange và binding:

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AuditStreamTopology {
    @Bean
    DirectExchange auditEventsExchange() {
        return new DirectExchange("audit.events.x", true, false);
    }

    @Bean
    Queue auditEventsStream() {
        return QueueBuilder.durable("audit.events.stream")
                .withArgument("x-queue-type", "stream")
                .withArgument("x-max-age", "7D")
                .build();
    }

    @Bean
    Binding auditEventsBinding(
            @Qualifier("auditEventsStream") Queue stream,
            @Qualifier("auditEventsExchange") DirectExchange exchange) {
        return BindingBuilder.bind(stream)
                .to(exchange)
                .with("audit.created");
    }
}
~~~

Publisher AMQP có thể tiếp tục gửi qua exchange:

~~~java
// RabbitTemplate dùng AMQP 0-9-1 và có thể route tới stream queue.
rabbitTemplate.convertAndSend(
        "audit.events.x",
        "audit.created",
        new AuditCreated(eventId, aggregateId, payload));
~~~

Ví dụ giả định ứng dụng đã cấu hình `MessageConverter` cho `AuditCreated`. Broker cần hỗ trợ stream, phân quyền và topology phù hợp. Với Stream Protocol, cổng listener phổ biến là **5552**, tùy cấu hình triển khai.

**Không đổi một classic queue thành stream tại chỗ bằng cách đổi `x-queue-type` rồi redeclare cùng tên**. Kiểu queue là thuộc tính bất biến; cần lên kế hoạch tạo tài nguyên mới, chuyển producer/consumer và xử lý message đang còn ở queue cũ. Những arguments khác về retention cũng cần quản lý bằng phương thức phù hợp để tránh khai báo queue mâu thuẫn.

### 6.2. Tích hợp stream-native qua Spring

Với Stream Protocol, module `spring-rabbit-stream` của Spring AMQP cung cấp các thành phần tích hợp trên RabbitMQ Java Stream client:

- `com.rabbitmq.stream.Environment`: kết nối, cấu hình stream client.
- `RabbitStreamTemplate`: gửi record tới stream.
- `StreamListenerContainer` và listener adapter/factory tương ứng: nhận record stream.
- Cơ chế offset của stream client: chọn vị trí đọc, theo dõi checkpoint và khôi phục consumer.

Ví dụ khai báo environment và producer template:

~~~java
import com.rabbitmq.stream.Environment;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.rabbit.stream.producer.RabbitStreamTemplate;

@Configuration
public class NativeStreamConfiguration {
    @Bean(destroyMethod = "close")
    Environment streamEnvironment() {
        return Environment.builder()
                .host("localhost")
                .port(5552)
                .build();
    }

    @Bean
    RabbitStreamTemplate auditStreamTemplate(Environment environment) {
        return new RabbitStreamTemplate(environment, "audit.events.stream");
    }
}
~~~

Đây là minh họa cấu hình producer, không bao gồm workflow triển khai stream hoặc consumer. Thư viện `spring-rabbit-stream`, RabbitMQ Stream Java client và Spring AMQP cần phiên bản tương thích; production nên cấu hình endpoint/TLS/credentials ngoài mã nguồn. API publish và tracking offset cụ thể phải theo đúng phiên bản thư viện mà ứng dụng đang dùng.

Với consumer, nguyên tắc an toàn có thể diễn đạt bằng **pseudocode**:

~~~text
consumer = openStreamConsumer(
    stream = "audit.events.stream",
    consumerName = "audit-projection-v2",
    startOffset = checkpointOrFirstAvailable()
)

onRecord(record, offset):
    beginDbTransaction()
    if not inbox.exists(record.eventId):
        applyBusinessEffect(record)
        inbox.insert(record.eventId)
    commitDbTransaction()

    storeCheckpoint(offset)  // Chỉ sau DB commit.
~~~

Khi triển khai thật, phải xử lý đồng thời việc checkpoint lỗi, event trùng, offset bị retention xóa và nhiều worker cùng xử lý một partition. Consumer mới có thể bắt đầu từ offset đầu còn tồn tại; consumer thường xuyên chạy nên phục hồi từ tiến độ đã lưu.

## 7. Publisher confirms và at-least-once vẫn cần thiết

Đối với queue thường, Spring AMQP hỗ trợ publisher confirms và returns để theo dõi publish đã được broker xử lý hay chưa và có được định tuyến đến queue hay không. Producer stream-native cũng có cơ chế **xác nhận publish** riêng. Cả hai đều phải xử lý tình huống kết nối mất khi chưa nhận được kết quả.

~~~text
T1  Producer gửi eventId=e102
T2  Broker ghi record e102 vào stream ở offset 500
T3  Broker gửi publish confirmation
T4  Kết nối đứt trước khi producer nhận confirmation
T5  Producer retry e102
T6  Stream có thể chứa thêm một record e102
~~~

**Không nhận được confirm không chứng minh broker chưa ghi record.** RabbitMQ Streams có thể hỗ trợ deduplication phía publisher theo producer name và publishing ID khi sử dụng đúng khả năng/configuration của Stream Protocol, nhưng đó không phải cam kết mọi tác dụng nghiệp vụ downstream đều xảy ra đúng một lần. Giữ `eventId` ổn định xuyên retry và chống trùng ở consumer vẫn rất quan trọng.

Đặc biệt, nếu ứng dụng **ghi database rồi phát sự kiện**, dùng **transactional outbox** để giữ ý định gửi một cách bền vững:

~~~mermaid
flowchart LR
    API["Order service"] --> TX["DB transaction"]
    TX --> ORD["orders"]
    TX --> OB["outbox_events"]
    OB --> REL["Publisher relay"]
    REL --> ST["RabbitMQ Stream"]
    ST --> P["Projection consumer"]
    ST --> A["Analytics consumer"]
    REL -->|"Publish xác nhận"| SENT["Đánh dấu outbox SENT"]
    REL -->|"Không rõ kết quả"| RETRY["Giữ event, retry"]
~~~

Outbox bảo đảm dữ liệu nghiệp vụ và **ý định phát event** được commit cùng transaction SQL. Relay publish tới stream rồi đánh dấu đã gửi sau xác nhận. Nếu relay chết sau publish nhưng trước khi cập nhật outbox, record có thể được publish lại. Consumer phải dùng idempotency theo `eventId`.

Spring `RabbitTemplate` với AMQP 0-9-1 và `RabbitStreamTemplate` với Stream Protocol có API gửi và xác nhận khác nhau. Khi chuyển đổi, hãy viết lại cách theo dõi publisher results dựa trên protocol thực tế; đừng giả định callback của hai API là một.

## 8. Retry, poison event và checkpoint khác NACK của queue

Với queue thông thường, mẫu thất bại quen thuộc là:

~~~text
@RabbitListener lỗi
  -> NACK/reject
  -> DLX + retry queue có TTL
  -> quay lại work queue
  -> quá số lần: parking-lot queue
~~~

Với stream, record vẫn còn trên log dù consumer đã đọc. Thay vì “NACK để đẩy message quay về queue”, reader phải quyết định **xử lý lại record, dừng tiến độ hay cách ly rồi tiến checkpoint**.

| Chính sách | Cách làm | Lợi ích | Rủi ro |
|---|---|---|---|
| Dừng tại record lỗi | Không tiến checkpoint, retry có backoff | Bảo toàn thứ tự nghiêm ngặt của partition | Một poison event chặn các record sau |
| Retry hữu hạn trong reader | Xử lý lại lỗi tạm thời một số lần | Đơn giản khi lỗi nhanh hồi phục | Tăng lag, không giải quyết lỗi vĩnh viễn |
| Cách ly lỗi rồi checkpoint | Lưu lỗi vào nơi bền vững, chờ xác nhận, sau đó cho tiến độ đi tiếp | Không chặn toàn luồng | Có thể mất thứ tự nghiệp vụ; cần kế hoạch replay |
| Ghi record lỗi vào DB và có worker riêng | Lưu payload/metadata và trạng thái xử lý để sửa | Audit, truy vết rõ ràng | Thêm hạ tầng, code và công cụ vận hành |

**Không lưu checkpoint vượt qua một record chưa xử lý hoặc chưa được cách ly bền vững**, trừ khi đây là quyết định nghiệp vụ được ghi nhận rõ. Nếu record offset 100 lỗi nhưng bạn checkpoint đến 120, restart có thể bỏ qua 100–119 mà không có cơ chế tự phục hồi chúng.

Ví dụ flow cách ly:

~~~mermaid
flowchart TB
    R["Đọc offset 200"] --> OK{"Xử lý thành công?"}
    OK -->|Có| TX["Commit DB"]
    TX --> CP["Checkpoint offset 200"]
    OK -->|Không| RET{"Còn lượt retry?"}
    RET -->|Có| DELAY["Backoff rồi xử lý lại offset 200"]
    DELAY --> OK
    RET -->|Hết lượt| PARK["Publish/quy lưu quarantine bền vững"]
    PARK --> CONF{"Đã xác nhận lưu?"}
    CONF -->|Có và policy cho phép skip| CP
    CONF -->|Không| HOLD["Giữ tiến độ, cảnh báo"]
~~~

Với hệ thống phải xử lý chính xác **mọi version của một aggregate**, việc cách ly offset 200 rồi tiếp tục 201 có thể vi phạm thứ tự nghiệp vụ. Cần version guard hoặc cơ chế pause/buffer theo khóa. Nếu dừng quá lâu, retention có thể xóa record trước khi được xử lý; phải có cảnh báo gần ngưỡng hết hạn.

**Dead-letter exchange của queue thông thường không tự thay thế cơ chế xử lý record lỗi của stream-native consumer.** Muốn đưa record sang một parking queue, ứng dụng chủ động publish bằng `RabbitTemplate` hoặc API thích hợp, chờ xác nhận rồi mới chuyển checkpoint.

## 9. Chi phí và giới hạn vận hành của RabbitMQ Streams

Stream cung cấp replay và nhiều reader, nhưng thêm các chi phí:

1. **Dung lượng lưu trữ:** record tồn tại đến khi retention dọn, kể cả sau khi mọi consumer đã xử lý. Dự trù dung lượng dựa trên events/giây × bytes/event × thời gian giữ × mức replication, cộng overhead và dung lượng dự phòng.
2. **Consumer lag:** một reader chậm có thể mất khả năng replay vì retention. Đo khoảng cách giữa offset mới và checkpoint, cùng tuổi của record cũ nhất còn giữ.
3. **Checkpoint:** cần tên consumer ổn định, chính sách restart, đặt lại offset có kiểm soát, và khôi phục khi offset đã bị xóa.
4. **Replication và phục hồi:** cân nhắc khả năng chịu lỗi node, disk I/O, topology và disaster recovery. Stream không tự thay thế backup.
5. **Scale và thứ tự:** super streams/partitioning tăng parallelism nhưng cần route theo key ổn định, quản lý assignment, ordering và retry.
6. **Poison event:** một record lỗi có thể chặn cả partition. Cần backoff, quarantine và runbook can thiệp.
7. **Schema evolution:** replay có thể đưa bản ghi do các phiên bản ứng dụng rất cũ phát ra. Consumer phải có versioning và backward compatibility phù hợp.
8. **Bảo mật và retention:** lưu lịch sử lâu hơn nghĩa là dữ liệu nhạy cảm tồn tại lâu hơn; phân quyền đọc, che dữ liệu và đặt retention theo chính sách.

Stream không phải kho lưu trữ vô hạn. Nếu cần giữ lịch sử nhiều năm hoặc tìm kiếm tùy ý theo thuộc tính, nên cân nhắc thêm data lake/object storage/database truy vấn chuyên dụng thay vì đặt toàn bộ gánh nặng lên stream broker.

## 10. Ma trận quyết định: queue hay stream?

| Tình huống | Lựa chọn khởi đầu | Lý do |
|---|---|---|
| Giao một job tạo PDF cho một worker | **Classic/quorum queue** | Competing consumers, ACK và DLQ tự nhiên |
| Lệnh gửi email với retry có delay | **Queue thông thường** | Retry/backoff và parking-lot thuận tiện |
| `OrderPaid` cần replay để dựng projection mới | **Stream** | Có thể đọc lại khi còn trong retention |
| Nhiều dịch vụ nhận event nhưng không cần replay | **Exchange + nhiều queues** vẫn hợp lý | Fan-out và ACK độc lập mà không cần log chung |
| Nhiều nhóm phân tích tiến độ độc lập | **Stream** | Mỗi nhóm đọc theo offset riêng |
| Telemetry liên tục, throughput cao | **Cân nhắc stream, benchmark** | Phù hợp append/read liên tục, cần đo thực tế |
| Muốn tác dụng DB chỉ xuất hiện một lần | **Cả hai cần idempotency** | Replay/redelivery/duplicate vẫn xảy ra |
| Cần thứ tự theo `accountId` cùng khả năng mở rộng | **Stream phân vùng hoặc queue shard** | Cả hai phải route theo key và kiểm version |
| Lịch sử bất biến bắt buộc lưu nhiều năm | **Kho lưu trữ dài hạn chuyên dụng** | Retention stream không tự là lưu trữ pháp lý vô hạn |
| Có cả event history và tác vụ cần ACK/retry | **Kết hợp queue + stream** | Mỗi loại dữ liệu cần semantics phù hợp |

### Có thể kết hợp queue và stream

~~~mermaid
flowchart LR
    API["Order API"] --> DB["Orders DB + outbox"]
    DB --> REL["Outbox relay"]
    REL --> ST["orders.events.stream"]
    ST --> ANA["Analytics / replay"]
    ST --> PROJ["Projection / replay"]
    ST --> ADAPT["Event-to-job adapter"]
    ADAPT --> EX["jobs.exchange"]
    EX --> Q["emails.jobs.q"]
    Q --> WORK["Email workers + ACK / DLQ"]
~~~

Lịch sử event nằm trên stream, còn command gửi email đi qua queue. Thành phần chuyển event thành job cần giữ `eventId`/idempotency key nhất quán; nếu nó replay một record cũ mà tạo lại job mới vô điều kiện, người dùng có thể nhận nhiều email.

## 11. Thực hành kiểm chứng khác biệt

Dùng RabbitMQ thật ở môi trường tích hợp, một queue thường và một stream queue. Ghi `eventId`, offset, thời gian nhận và kết quả xử lý vào log.

### Thí nghiệm A: ACK và replay

1. Publish `e1`, `e2`, `e3` vào queue thường và stream.
2. Consumer queue nhận ba message, xử lý và ACK. Xác minh message đã hoàn tất rời queue.
3. Consumer stream đọc ba record và lưu checkpoint.
4. Khởi động consumer stream **mới** từ offset đầu còn tồn tại. Xác minh vẫn đọc được ba record nếu retention chưa xóa.

### Thí nghiệm B: Hai reader độc lập

1. Tạo hai stream consumer với danh tính/progress riêng.
2. Cho A đọc nhanh; B đọc chậm hoặc tạm dừng.
3. Quan sát A tiến xa hơn B mà B vẫn đọc được record cũ trong retention.
4. Trong môi trường thử nghiệm, giảm retention và kiểm tra hành vi khi offset của B không còn.

### Thí nghiệm C: Crash trước checkpoint

1. Reader lấy record `e101` và commit nghiệp vụ vào DB.
2. Dừng reader **trước khi ghi checkpoint**.
3. Restart; record có thể được đọc lại.
4. Kiểm tra unique key `(consumer_name, event_id)` ngăn ghi nghiệp vụ lần hai.

### Thí nghiệm D: Poison event và thứ tự

1. Publish version 1, 2, 3 cho cùng `orderId`.
2. Làm version 2 thất bại liên tục, quan sát reader dừng/retry/cách ly theo policy.
3. Xác minh version 3 không được áp dụng trái quy tắc thứ tự.
4. Khôi phục version 2, kiểm tra checkpoint và tiến độ đọc tiếp.

| Điều cần đo | Queue thông thường | Stream |
|---|---|---|
| Backlog | `ready`, `unacked` và DLQ | Offset lag, checkpoint và segments còn giữ |
| Tiến độ | ACK/redelivery | Offset/checkpoint theo consumer |
| Độ trễ | Publish tới consumer ACK | Append tới xử lý và checkpoint |
| Lỗi | NACK/requeue, DLX/parking | Retry của reader, checkpoint bị chặn, quarantine |
| Trùng lặp | Redelivery khi chưa ACK | Replay hoặc publish trùng |
| Dung lượng | Độ sâu queue và message chờ | Retention, disk usage, replication |

## 12. Hiểu lầm cần tránh

| Nhận định sai | Điều đúng |
|---|---|
| “Stream là queue nhưng nhanh hơn” | Stream có mô hình retention, log và offset khác queue |
| “Consumer đọc xong stream sẽ xóa record” | Record tồn tại đến khi retention dọn |
| “Stream đảm bảo exactly-once” | Publish/consume có thể trùng; cần idempotency |
| “Stream thì không cần quarantine” | Poison event vẫn phải xử lý có kiểm soát |
| “Thêm nhiều reader là tự chia việc” | Reader độc lập có thể cùng đọc mọi record; cần phân vùng/assignment |
| “Retention giữ record cho mọi consumer chậm” | Retention có thể dọn record chưa được consumer đọc |
| “Offset là sequence nghiệp vụ toàn cục” | Offset theo stream/partition, không thay version của aggregate |
| “`RabbitTemplate` tự dùng stream protocol” | `RabbitTemplate` vẫn dùng AMQP 0-9-1; stream-native có API riêng |
| “Queue thường không hỗ trợ fan-out” | Exchange có thể route tới nhiều queue |
| “Stream thay thế đầy đủ event store/database” | Stream không tự có mọi kiểu truy vấn, retention dài hạn và transaction nghiệp vụ |

## 13. Checklist trước khi chuyển từ queue sang stream

1. **Có thực sự cần replay?** Cần đọc lại trong bao lâu và ai sẽ đọc?
2. **Message là command hay sự kiện đã xảy ra?** Job một lần thường phù hợp hơn với queue.
3. **Có mấy nhóm reader độc lập?** Mỗi nhóm có checkpoint và chính sách phục hồi riêng?
4. **Thứ tự cần đến mức nào?** Theo toàn log, theo `orderId` hay không quan trọng?
5. **Xử lý lỗi và tiến checkpoint ra sao?** Retry hữu hạn, dừng partition hay quarantine?
6. **Có chấp nhận xử lý trùng?** Thiết kế event ID, publisher confirms và inbox idempotency.
7. **Đã tính retention/dung lượng?** Đo lượng record, lag và độ tuổi dữ liệu còn giữ.
8. **API nào phù hợp?** AMQP 0-9-1 ở mức giới hạn hay `spring-rabbit-stream` với Stream Protocol?
9. **Có cần lưu trữ lâu hơn retention?** Bổ sung archive/snapshot hoặc data warehouse khi cần.
10. **Đã benchmark đúng workload?** So thông lượng, latency, replication, disk và mức độ phức tạp vận hành.

**Kết luận:** Chọn **queue thông thường** khi mục tiêu là giao một tác vụ cho worker, ACK sau khi hoàn tất và bỏ message khỏi hàng đợi. Chọn **RabbitMQ Streams** khi bản ghi sự kiện có giá trị lâu hơn một lần xử lý và cần **retention, replay, offset và nhiều reader độc lập**. Dù chọn mô hình nào, vẫn phải thiết kế routing, xác nhận publish, xử lý lỗi và idempotency. Với Spring AMQP, hãy chọn đúng API AMQP hoặc stream-native và coi **checkpoint + retention** là một phần của hợp đồng dữ liệu, không chỉ là thông số cấu hình.
