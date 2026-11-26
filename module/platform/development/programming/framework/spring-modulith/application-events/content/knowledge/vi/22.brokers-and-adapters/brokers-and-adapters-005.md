# Acknowledgement

Một event được gửi đi chưa có nghĩa là bên nhận đã lưu và xử lý thành công. Producer có thể chỉ biết broker đã nhận request; broker có thể đã lưu message nhưng consumer chưa đọc; consumer có thể đã đọc nhưng transaction nghiệp vụ chưa commit. Acknowledgement là tín hiệu xác nhận tại một ranh giới cụ thể của luồng giao sự kiện.

Khi thiết kế giao tiếp giữa các module Spring Modulith và các hệ thống bên ngoài, cần phân biệt xác nhận của producer, xác nhận của broker, xác nhận của consumer và trạng thái hoàn tất publication nội bộ. Mỗi loại xác nhận bảo vệ một khoảng lỗi khác nhau. Nếu hiểu nhầm một tín hiệu là bằng chứng hoàn tất end-to-end, hệ thống có thể mất event hoặc tạo side effect trùng khi retry.

Bài này mô tả các ranh giới acknowledgement, cách cấu hình producer và consumer theo broker, cách kết hợp acknowledgement với Event Publication Registry và transactional outbox, cùng các chiến lược retry, idempotency, quan sát và kiểm thử.

## 1. Acknowledgement xác nhận điều gì?

Một luồng event đi qua nhiều bước:

1. Ứng dụng tạo event sau một thay đổi nghiệp vụ.
2. Producer gửi message tới broker.
3. Broker xác nhận đã nhận hoặc lưu message theo cấu hình.
4. Consumer đọc message.
5. Consumer thực hiện side effect nghiệp vụ.
6. Consumer xác nhận đã xử lý để broker có thể tiến tới message tiếp theo hoặc bỏ message khỏi hàng đợi.

Không có một acknowledgement duy nhất bao phủ tất cả các bước này. Cần xác định chính xác bên nào gửi xác nhận, xác nhận cho thao tác nào và điều kiện nào được xem là thành công.

| Loại xác nhận | Bên gửi tín hiệu | Điều được xác nhận | Điều chưa được bảo đảm |
|---|---|---|---|
| Producer acknowledgement / publisher confirm | Broker trả về producer | Broker đã nhận message theo semantics của broker và cấu hình | Consumer đã đọc hoặc xử lý |
| Consumer acknowledgement | Consumer gửi tới broker | Consumer tuyên bố đã xử lý message | Side effect ngoài transaction của consumer đã hoàn tất |
| Application listener completion | Listener kết thúc thành công; framework ghi trạng thái | Listener nội bộ đã hoàn tất theo cơ chế ứng dụng | Broker bên ngoài đã nhận integration message |
| Outbox relay completion | Relay cập nhật bản ghi sau broker confirm | Relay đã nhận xác nhận gửi và ghi nhận trạng thái đã gửi | Consumer đích đã xử lý nghiệp vụ |
| Business acknowledgement | Hệ thống nghiệp vụ đích trả kết quả | Một điều kiện nghiệp vụ cụ thể đã đạt | Các bước downstream khác đã hoàn tất |

Một ví dụ: Kafka producer nhận acknowledgement từ broker không có nghĩa service kho đã giữ hàng. Consumer kho có thể chưa chạy hoặc đã gặp lỗi. Nếu nghiệp vụ cần biết việc giữ hàng thành công, phải có event hoặc response nghiệp vụ riêng như InventoryReserved.

## 2. Các ranh giới trong Spring Modulith

### 2.1. Application event nội bộ

ApplicationEventPublisher phát event trong tiến trình Spring. Lời gọi publishEvent không phải là một network acknowledgement. Với listener đồng bộ, lời gọi có thể kích hoạt listener ngay trong luồng hiện tại; với listener bất đồng bộ, công việc được thực thi theo executor và cấu hình listener.

@ApplicationModuleListener của Spring Modulith hỗ trợ listener ở ranh giới application module và xử lý sau commit theo semantics của annotation. Event Publication Registry theo dõi publication tương ứng với từng listener khi được cấu hình persistence phù hợp. Listener hoàn tất thành công thì publication có thể được đánh dấu hoàn tất; listener thất bại thì publication còn dang dở để phục hồi.

Luồng nội bộ khái quát:

~~~mermaid
sequenceDiagram
    participant S as Business service
    participant DB as Database
    participant R as Publication Registry
    participant L as Module listener

    S->>DB: Lưu thay đổi nghiệp vụ
    S->>R: Publish application event
    R->>DB: Ghi publication cùng transaction
    Note over DB,R: Commit hoặc rollback cùng nhau
    DB-->>S: Commit
    R->>L: Giao event sau commit
    L->>DB: Xử lý trong transaction listener
    L-->>R: Listener hoàn tất
    R->>DB: Đánh dấu publication hoàn tất
~~~

Bản ghi publication giúp ứng dụng biết listener nào chưa hoàn tất và hỗ trợ resubmit sau sự cố. Nó không phải publisher confirm của broker và cũng không chứng minh một hệ thống bên ngoài đã hoàn thành nghiệp vụ.

### 2.2. AFTER_COMMIT không tự tạo acknowledgement bền vững

@TransactionalEventListener(phase = AFTER_COMMIT) điều khiển thời điểm listener được gọi. Nếu ứng dụng dừng sau commit nhưng trước khi listener thực thi, việc chỉ dùng AFTER_COMMIT không tự tạo một bản ghi bền vững để phục hồi.

Khi cần theo dõi và phục hồi listener nội bộ, hãy cấu hình Event Publication Registry với implementation persistence phù hợp. Kho publication phải tham gia đúng transaction manager nếu cần commit nguyên tử với dữ liệu nghiệp vụ.

### 2.3. Listener completion là một ranh giới cụ thể

Framework chỉ có thể xem listener đã hoàn tất theo kết quả mà listener trả về và cách exception được xử lý. Nếu listener bắt exception rồi bỏ qua, framework có thể thấy phương thức kết thúc bình thường dù nghiệp vụ thực tế thất bại.

Không nuốt exception của công việc bắt buộc phải retry. Nếu lỗi đã được xử lý thành công bằng fallback, hãy ghi rõ kết quả đó; nếu chưa thành công, để lỗi truyền tới cơ chế quản lý publication hoặc đưa vào trạng thái lỗi có thể quan sát.

## 3. Producer acknowledgement và publisher confirm

Producer acknowledgement xác nhận kết quả gửi ở phía broker. Mức bảo đảm phụ thuộc broker, replication, durability, timeout và cấu hình producer.

Một lần gọi send trả về mà chưa có kết quả bất đồng bộ không có nghĩa message đã được broker lưu. Producer cần theo dõi callback/future hoặc cơ chế confirm tương ứng và xử lý cả success lẫn failure.

### 3.1. Kafka producer

Kafka producer gửi record tới topic và nhận response từ broker. Thuộc tính acks quyết định mức xác nhận:

| Cấu hình | Ý nghĩa khái quát | Đánh đổi |
|---|---|---|
| acks=0 | Producer không đợi broker acknowledgement | Độ trễ thấp, không biết broker đã nhận hay chưa |
| acks=1 | Leader xác nhận sau khi append record vào log cục bộ | Có thể mất dữ liệu nếu leader lỗi trước khi replica khác nhận |
| acks=all | Leader đợi các replica trong ISR xác nhận theo cấu hình | Bảo đảm mạnh hơn, có thể tăng độ trễ hoặc giảm khả năng ghi khi ISR thiếu |

acks=all cần được xem cùng min.insync.replicas và replication factor. Nếu cấu hình min.insync.replicas quá thấp hoặc replication factor không phù hợp, mức bảo vệ thực tế có thể thấp hơn kỳ vọng. Acknowledgement xác nhận việc ghi theo semantics replication; nó không xác nhận consumer đã xử lý.

Ví dụ producer Spring Kafka:

~~~java
@Service
@RequiredArgsConstructor
class OrderMessagePublisher {

    private final KafkaTemplate<String, OrderEvent> kafkaTemplate;

    public CompletableFuture<SendResult<String, OrderEvent>> publish(
            OrderEvent event
    ) {
        String key = event.orderId().toString();

        return kafkaTemplate.send(
                "order-events",
                key,
                event
        );
    }
}
~~~

Caller phải quan sát kết quả future, ghi nhận lỗi gửi và áp dụng retry theo chính sách. Không bỏ qua future hoặc coi việc gọi send là thành công. Cấu hình producer có thể bật idempotence để giảm duplicate do retry producer trong phạm vi semantics Kafka hỗ trợ; điều này không thay thế idempotency ở consumer và không bao trùm side effect database bên ngoài Kafka.

### 3.2. RabbitMQ publisher confirms

RabbitMQ publisher confirms cho producer biết broker đã xử lý publish theo trạng thái confirm. Với queue bền vững, message persistent và loại queue/replication phù hợp, broker có thể bảo vệ message qua restart theo cấu hình.

Publisher confirm và consumer acknowledgement là hai luồng độc lập. Confirm ACK không chứng minh consumer đã nhận message. Nếu message không được định tuyến tới queue nào, publisher confirm cũng không nhất thiết thay thế cơ chế phát hiện unroutable message. Khi cần, kết hợp mandatory publish và publisher returns để phát hiện message không được route.

Ở phía ứng dụng Spring AMQP, có thể cấu hình correlated publisher confirms và returns; tên thuộc tính và API cụ thể cần đối chiếu phiên bản Spring AMQP đang dùng. Producer phải xử lý cả confirm NACK, timeout và returned message.

### 3.3. Amazon SQS

Với SQS, producer nhận message ID khi SendMessage thành công. Điều đó xác nhận SQS đã nhận request theo semantics dịch vụ, không có nghĩa consumer đã xử lý. Standard queue có thể giao trùng; FIFO có thêm MessageGroupId và deduplication window theo cấu hình dịch vụ.

Consumer thường xóa message sau khi xử lý thành công. Nếu message không được xóa, nó có thể xuất hiện lại sau visibility timeout. Visibility timeout cần đủ dài cho thời gian xử lý hoặc được gia hạn khi xử lý lâu.

## 4. Consumer acknowledgement

Consumer acknowledgement cho broker biết consumer đã xử lý message tới một mức nào đó. Thời điểm ack quyết định rủi ro mất message và duplicate.

Nguyên tắc chung cho consumer có side effect database:

1. Đọc message.
2. Kiểm tra event ID và điều kiện idempotency.
3. Thực hiện thay đổi nghiệp vụ.
4. Commit transaction database.
5. Chỉ sau đó mới acknowledgement message hoặc commit offset theo chiến lược đã chọn.

Nếu ack trước khi transaction nghiệp vụ commit, process có thể dừng sau ack nhưng trước commit. Broker không giao lại message và thay đổi nghiệp vụ bị mất.

Nếu commit database trước ack, process có thể dừng giữa hai bước. Broker giao lại message; consumer phải dedupe để không tạo side effect lần nữa. Đây là khoảng trống phổ biến khi database và broker không cùng transaction.

### 4.1. Kafka consumer

Kafka consumer quản lý offset, không gửi một ACK độc lập cho từng record theo cùng mô hình RabbitMQ. Việc commit offset cho biết consumer group đã xử lý tới vị trí nào trong partition.

Nếu auto-commit offset xảy ra trước khi side effect database hoàn tất, message có thể bị bỏ qua sau restart. Với xử lý nghiệp vụ quan trọng, hãy cấu hình commit theo kết quả xử lý và hiểu rõ AckMode của Spring Kafka container.

Ví dụ listener dùng manual acknowledgement:

~~~java
@KafkaListener(
        topics = "order-events",
        groupId = "inventory-service"
)
public void on(
        OrderEvent event,
        Acknowledgment acknowledgment
) {
    inventoryService.apply(event); // transaction phải commit thành công
    acknowledgment.acknowledge();
}
~~~

Ví dụ này giả định apply hoàn tất transaction đồng bộ trước khi trả về. Nếu method chỉ khởi chạy công việc async rồi return, offset có thể được commit trước khi side effect hoàn tất. Cần giữ xử lý đồng bộ theo partition hoặc dùng một thiết kế async có checkpoint/offset quản lý riêng.

Với Kafka, commit offset theo partition là điểm quan trọng. Không commit offset của record sau nếu record trước trong cùng partition chưa được xử lý an toàn, trừ khi ứng dụng có cơ chế quản lý offset và retry phù hợp.

### 4.2. RabbitMQ consumer

RabbitMQ hỗ trợ automatic ack và manual ack. Với manual ack, consumer gửi basicAck sau khi xử lý thành công; basicNack/basicReject có thể từ chối message, tùy lựa chọn requeue hoặc dead-letter.

Ví dụ minh họa bằng Spring AMQP:

~~~java
@RabbitListener(queues = "order-events")
public void on(
        OrderEvent event,
        Channel channel,
        Message message
) throws IOException {
    long tag = message.getMessageProperties()
            .getDeliveryTag();

    inventoryService.apply(event); // commit transaction trước
    channel.basicAck(tag, false);
}
~~~

Listener container phải được cấu hình acknowledgement mode MANUAL để ứng dụng chủ động ack. Nếu apply ném exception, không gọi basicAck. Việc requeue, reject hoặc dead-letter cần được quyết định theo loại lỗi và chính sách retry; requeue liên tục một message poison có thể tạo vòng lặp nóng.

Không ack thủ công hai lần cho cùng delivery tag. Delivery tag chỉ có ý nghĩa trong channel hiện tại; không lưu tag để ack sau khi channel đã đóng.

### 4.3. SQS consumer

SQS không có basicAck tương đương. Consumer xóa message sau khi xử lý thành công. Nếu dùng listener container, xác minh acknowledgement mode và thời điểm delete được thực hiện theo phiên bản thư viện.

Visibility timeout không phải bằng chứng message đã được xử lý. Nếu consumer vẫn chạy khi timeout hết, một consumer khác có thể nhận cùng message. Với tác vụ dài, gia hạn visibility timeout và dùng idempotency để bảo vệ side effect.

## 5. Ack, retry và duplicate

Acknowledgement quyết định message có được xem là đã hoàn tất ở broker hay không. Retry quyết định điều gì xảy ra khi xử lý thất bại. Hai chính sách này cần được thiết kế cùng nhau.

| Kết quả xử lý | Hành động thường dùng | Lưu ý |
|---|---|---|
| Thành công và transaction commit | Ack hoặc commit offset | Đánh dấu đã xử lý bền vững |
| Lỗi tạm thời | Retry có backoff | Giới hạn số lần và tốc độ |
| Lỗi dữ liệu/contract | Dead-letter hoặc quarantine | Không retry vô hạn |
| Timeout không rõ kết quả | Kiểm tra trạng thái/idempotency rồi retry | Side effect có thể đã xảy ra |
| Consumer dừng trước ack | Broker có thể giao lại | Dedupe theo event ID |

Một lần timeout không luôn có nghĩa message chưa được gửi. Ví dụ producer gửi thành công nhưng response acknowledgement bị mất trên đường về. Retry có thể tạo duplicate. Tương tự, consumer có thể commit DB thành công nhưng dừng trước ack, khiến broker giao lại.

Do đó, at-least-once delivery thường yêu cầu consumer idempotent. Exactly-once processing chỉ có thể tuyên bố trong một phạm vi transaction cụ thể. Kafka có thể hỗ trợ giao dịch đọc/ghi Kafka và commit offset trong cùng Kafka transaction cho một số luồng consume-transform-produce; side effect sang database bên ngoài không tự động nằm trong transaction đó.

## 6. Idempotency ở consumer

Consumer nên lưu event ID đã xử lý với unique constraint và ghi nhận nó trong cùng transaction với side effect database.

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Ví dụ:

~~~java
@Transactional
public void apply(OrderEvent event) {
    boolean firstDelivery = processedEvents.tryRegister(
            "inventory-service",
            event.eventId()
    );

    if (!firstDelivery) {
        return;
    }

    inventory.reserveFor(event.orderId());
}
~~~

tryRegister cần dựa trên thao tác insert nguyên tử và unique constraint. Nếu hai delivery trùng chạy đồng thời, chỉ một transaction được quyền đăng ký event ID. Cập nhật inventory và ghi processed_event phải cùng transaction; nếu một bước rollback, bước còn lại cũng rollback.

Nếu consumer gọi API bên ngoài, transaction database không thể bao trọn API đó. Hãy truyền idempotency key tới dịch vụ đích nếu hỗ trợ, lưu request/response ID và có bước đối soát. Không dựa vào processed_event nội bộ để bảo đảm một API bên ngoài không bị gọi hai lần.

## 7. Kết hợp acknowledgement với transactional outbox

Transactional outbox giải quyết khoảng trống giữa commit dữ liệu nghiệp vụ và gửi message tới broker. Service nghiệp vụ ghi aggregate và outbox record trong cùng transaction. Relay gửi record ra broker rồi cập nhật trạng thái sau khi nhận confirm.

~~~mermaid
sequenceDiagram
    participant S as Business service
    participant DB as Database
    participant R as Outbox relay
    participant B as Broker

    S->>DB: Ghi Order và Outbox
    Note over S,DB: Cùng transaction
    DB-->>S: Commit
    R->>DB: Claim outbox record
    DB-->>R: PENDING record
    R->>B: Publish message
    B-->>R: Publisher confirm
    R->>DB: Mark SENT
~~~

Không đánh dấu SENT trước khi broker xác nhận. Nếu relay đánh dấu SENT rồi mới gửi, lỗi mạng có thể làm mất message vĩnh viễn.

Nếu broker đã nhận message nhưng relay dừng trước khi cập nhật SENT, relay có thể gửi lại sau khi khởi động. Đây là lý do outbox thường có semantics at-least-once và consumer cần dedupe.

Outbox relay nên phân biệt các trạng thái như PENDING, IN_FLIGHT, SENT và FAILED/NEEDS_ATTENTION. Claim bằng lease hoặc lock trong transaction ngắn; gửi broker bên ngoài transaction; cập nhật kết quả bằng transaction mới. Khi lease hết hạn, worker khác có thể tiếp tục.

Publisher confirm là điều kiện để relay ghi nhận gửi thành công, nhưng vẫn chưa phải consumer acknowledgement. Nếu nghiệp vụ cần biết consumer đã xử lý, consumer phải phát một event kết quả riêng hoặc cập nhật trạng thái qua một giao thức nghiệp vụ được định nghĩa rõ.

## 8. Dead-letter và xử lý poison message

Poison message là message liên tục thất bại do payload không hợp lệ, schema không hỗ trợ hoặc lỗi nghiệp vụ không thể tự khắc phục. Requeue ngay lập tức không giới hạn có thể gây tải cao và làm các message khác bị chậm.

Một chiến lược phổ biến:

1. Phân loại lỗi tạm thời và lỗi vĩnh viễn.
2. Retry lỗi tạm thời với backoff và giới hạn số lần.
3. Đưa message không thể xử lý vào dead-letter queue hoặc quarantine.
4. Lưu event ID, routing key, số lần thử, lỗi cuối và thời điểm.
5. Cung cấp quy trình điều tra, sửa dữ liệu hoặc schema, rồi replay có kiểm soát.

Với RabbitMQ, dead-letter exchange/queue có thể nhận message bị reject hoặc hết TTL theo cấu hình. Với Kafka, dead-letter topic thường được triển khai ở tầng consumer ứng dụng. Với SQS, redrive policy có thể chuyển message sang dead-letter queue sau maxReceiveCount.

Không xóa message lỗi chỉ để làm sạch backlog. Cần giữ dữ liệu đủ để tái hiện lỗi và xác định liệu side effect đã xảy ra hay chưa.

## 9. Timeout và thời điểm acknowledgement

Timeout quá ngắn làm tăng retry và duplicate; timeout quá dài làm chậm phục hồi khi consumer thực sự chết.

Producer cần timeout phù hợp với độ trễ broker, replication và mạng. Khi timeout, kết quả có thể không xác định: broker có thể đã ghi message nhưng acknowledgement bị mất. Hãy retry bằng cùng event ID và cùng partition key.

Consumer timeout phải bao gồm thời gian xử lý bình thường, thời gian chờ dependency và khoảng dự phòng. Với SQS, visibility timeout phải đủ dài hoặc được gia hạn. Với RabbitMQ, consumer timeout và heartbeat/channel lifecycle cần phù hợp. Với Kafka, thời gian xử lý phải tương thích với max.poll.interval.ms và cấu hình poll của consumer; xử lý quá lâu có thể khiến consumer bị xem là không hoạt động và gây rebalance.

Không tăng timeout để che một consumer bị treo. Theo dõi latency percentile, thời gian transaction, dependency timeout và số lần redelivery để chọn ngưỡng phù hợp.

## 10. Quan sát acknowledgement end-to-end

Mỗi event nên có eventId ổn định, aggregateId, eventType, schemaVersion, correlationId và routing/partition key. Log các mốc quan trọng với cùng định danh để dựng lại luồng.

Các chỉ số cần theo dõi:

**Producer và relay:**

- Số message gửi thành công, confirm NACK và timeout.
- Thời gian từ lúc publish tới broker confirm.
- Số outbox record PENDING/IN_FLIGHT và tuổi record lâu nhất.
- Số lần retry, record SENT và lỗi cần can thiệp.

**Broker:**

- Queue depth hoặc consumer lag.
- Số message redelivery, unacked và dead-letter.
- Partition lag, ISR health hoặc queue availability theo broker.
- Tỷ lệ publish/consume và độ trễ acknowledgement.

**Consumer:**

- Số message nhận, xử lý thành công, ack, retry và dedupe.
- Thời gian từ receive tới commit nghiệp vụ và ack.
- Tỷ lệ lỗi theo event type và consumer.
- Số event bị quarantine hoặc không tương thích schema.

Không log payload nhạy cảm chỉ để điều tra acknowledgement. Dùng event ID, correlation ID và metadata cần thiết để truy vết. Nếu một event đã broker confirm nhưng consumer lag tăng, lỗi nằm ở đường tiêu thụ; nếu producer confirm timeout tăng, hãy điều tra đường gửi và broker.

## 11. Kiểm thử acknowledgement và failure window

Unit test có thể xác minh producer xử lý callback và listener gọi ack sau khi service hoàn tất. Tuy nhiên, cần integration test với broker để kiểm tra semantics thật của confirm, redelivery, offset và dead-letter.

| Kịch bản | Điều cần xác minh |
|---|---|
| Producer gửi thành công | Broker confirm được quan sát và outbox chuyển SENT |
| Producer timeout nhưng broker đã nhận | Retry không tạo side effect trùng ở consumer |
| Broker NACK hoặc không route message | Producer ghi nhận lỗi và không đánh dấu SENT |
| Consumer commit DB rồi dừng trước ack | Message có thể giao lại và dedupe ngăn side effect lặp |
| Consumer ack trước commit | Test chứng minh đây là cấu hình không được phép cho luồng quan trọng |
| Listener nội bộ ném exception | Publication registry giữ publication chưa hoàn tất |
| Listener hoàn tất thành công | Publication tương ứng được đánh dấu hoàn tất |
| Poison message | Được retry có giới hạn rồi chuyển dead-letter/quarantine |
| SQS visibility timeout hết | Message có thể giao lại nhưng consumer idempotent |
| Kafka consumer restart | Offset chỉ tiến qua các record đã xử lý an toàn |
| Relay dừng sau broker confirm, trước mark SENT | Message có thể gửi trùng và consumer dedupe được |
| Consumer xử lý async | Ack/offset không tiến trước khi side effect hoàn tất |

Đặc biệt cần kiểm thử hai failure window:

- Broker đã nhận nhưng producer không nhận được confirm.
- Consumer đã commit nghiệp vụ nhưng broker chưa nhận acknowledgement.

Đây là hai điểm thường tạo duplicate. Hệ thống nên xử lý duplicate như một tình huống bình thường của delivery at-least-once.

## 12. Lỗi thiết kế thường gặp

**Coi lời gọi send là acknowledgement.** Gửi bất đồng bộ cần theo dõi kết quả confirm/future. Không đánh dấu outbox SENT chỉ vì API send đã trả về.

**Coi publisher confirm là consumer completion.** Broker đã nhận message không có nghĩa consumer đã xử lý. Nếu cần xác nhận nghiệp vụ, dùng response event hoặc trạng thái riêng.

**Ack trước khi commit database.** Process dừng sau ack có thể làm mất side effect. Commit nghiệp vụ trước, rồi mới ack/commit offset.

**Nuốt exception trong listener.** Framework có thể xem listener hoàn tất dù nghiệp vụ thất bại. Chỉ bắt lỗi khi đã xử lý thành công hoặc chuyển sang trạng thái lỗi được theo dõi.

**Requeue poison message vô hạn.** Tạo vòng lặp nóng và làm tắc queue. Dùng backoff, giới hạn retry và dead-letter.

**Cho rằng broker durable là đủ.** Durability phụ thuộc replication, persistent message, queue/topic configuration và acknowledgement mode. Kiểm tra cả cấu hình producer lẫn broker.

**Cho rằng exactly-once bao trùm database ngoài broker.** Transaction broker không tự bao gồm side effect ở hệ thống khác. Dùng outbox/inbox và idempotency ở ranh giới tương ứng.

**Ack async trước khi công việc async hoàn tất.** Offset hoặc message có thể được xác nhận quá sớm. Quản lý completion và checkpoint theo kết quả thực tế.

## 13. Quy trình thiết kế acknowledgement

Khi thêm một broker adapter hoặc consumer mới, hãy xác định:

1. Producer cần mức bảo đảm nào và broker confirm nghĩa là gì?
2. Message có được lưu bền vững qua restart theo cấu hình hiện tại không?
3. Consumer ack hoặc commit offset ở thời điểm nào so với transaction nghiệp vụ?
4. Nếu process dừng giữa commit và ack, consumer có idempotent không?
5. Lỗi tạm thời và lỗi vĩnh viễn được retry, dead-letter hoặc xử lý ra sao?
6. Outbox relay chỉ mark SENT sau confirm như thế nào?
7. Nếu cần xác nhận nghiệp vụ, hệ thống đích phát response/event nào?
8. Metric và audit nào giúp phân biệt lỗi producer, broker và consumer?

Với Spring Modulith, Event Publication Registry theo dõi việc giao event tới listener nội bộ. Với broker bên ngoài, publisher confirm và consumer acknowledgement bảo vệ các ranh giới vận chuyển riêng. Transactional outbox nối transaction nghiệp vụ với việc gửi message bền vững; inbox/idempotency bảo vệ side effect của consumer. Khi mỗi acknowledgement có ý nghĩa rõ ràng và được kiểm thử tại failure window tương ứng, hệ thống có thể retry an toàn và quan sát được trạng thái giao event từ đầu tới cuối.
