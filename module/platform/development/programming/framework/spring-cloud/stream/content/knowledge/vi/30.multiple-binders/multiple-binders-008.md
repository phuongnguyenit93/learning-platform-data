# Giới hạn giao dịch và bảo đảm giao nhận khi bắc cầu broker

Spring Cloud Stream cho phép một ứng dụng kết nối nhiều hệ thống messaging bằng nhiều binder. Ví dụ, một function có thể đọc đơn hàng từ Kafka rồi gửi sự kiện sang RabbitMQ; một bridge khác có thể chuyển dữ liệu từ RabbitMQ sang Pulsar. Binder giúp thống nhất cách khai báo binding và xử lý message, nhưng mỗi broker vẫn có transaction coordinator, cơ chế xác nhận và ranh giới lưu trữ riêng.

Khi bắc cầu broker, một thao tác nghiệp vụ thường gồm ít nhất hai bước độc lập: xác nhận message ở broker nguồn và publish message sang broker đích. Nếu ứng dụng commit/ack nguồn trước khi đích nhận message, sự cố có thể làm mất dữ liệu. Nếu publish sang đích trước rồi ứng dụng dừng trước khi commit/ack nguồn, message sẽ được giao lại và có thể tạo bản trùng. Đây là bài toán dual-write giữa hai hệ thống phân tán.

Không có một thuộc tính bật nhiều binder nào tự biến hai broker thành một transaction phân tán. Kafka transaction có thể kết hợp offset nguồn và output Kafka trong cùng transaction Kafka; Pulsar transaction có thể kết hợp acknowledgment và writes trong phạm vi transaction Pulsar; RabbitMQ dùng consumer acknowledgment và publisher confirm cho hai chiều độc lập. Khi chuyển giữa các broker khác loại hoặc các cluster độc lập, cần thiết kế bảo đảm giao nhận ở cấp ứng dụng, thường bằng at-least-once, event ID ổn định, idempotency và transactional outbox/inbox.

Bài học này giải thích ranh giới transaction, các cửa sổ mất/trùng message, cách chọn delivery guarantee, cấu hình multi-binder, thiết kế bridge trực tiếp và bridge có outbox, xử lý thứ tự, retry/DLQ, quan sát và kiểm thử sự cố.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Cấu hình từng binding dùng binder và broker riêng trong Spring Cloud Stream.
- Phân biệt transaction cục bộ của Kafka, RabbitMQ và Pulsar.
- Giải thích vì sao nhiều binder không tạo distributed transaction giữa các broker.
- Nhận diện hai cửa sổ lỗi gây mất hoặc nhân đôi message khi bắc cầu.
- Chọn at-most-once, at-least-once hoặc effectively-once theo yêu cầu.
- Thiết kế bridge trực tiếp với thứ tự publish đích rồi xác nhận nguồn.
- Dùng transactional outbox/inbox để giải quyết dual-write với database.
- Thiết kế event ID, deduplication, ordering và schema mapping.
- Phối hợp retry, dead-letter, quarantine và replay.
- Kiểm thử crash, timeout, broker outage và duplicate delivery.

## 1. Nhiều binder không đồng nghĩa một transaction

Binder là adapter kết nối Spring Cloud Stream binding với một hệ thống messaging. Một ứng dụng có thể đặt binder riêng cho từng input/output binding. Function vẫn xử lý payload theo programming model chung, còn binder quyết định cách kết nối, serialize, publish, consume và xác nhận message.

Ví dụ một bridge đọc Kafka và ghi RabbitMQ:

~~~yaml
spring:
  cloud:
    function:
      definition: bridgeOrder
    stream:
      bindings:
        bridgeOrder-in-0:
          binder: kafka
          destination: orders.created
          group: order-bridge
        bridgeOrder-out-0:
          binder: rabbit
          destination: orders.forwarded
~~~

Khi có nhiều binder trên classpath, Spring Cloud Stream yêu cầu chỉ rõ binder cho binding hoặc cấu hình default binder. Nếu ứng dụng kết nối nhiều broker cùng loại, có thể khai báo các binder configuration có tên riêng và môi trường kết nối riêng.

Ví dụ kết nối hai broker khác loại bằng binder configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: bridgeOrder
    stream:
      bindings:
        bridgeOrder-in-0:
          binder: kafkaSource
          destination: orders.created
          group: order-bridge
        bridgeOrder-out-0:
          binder: rabbitTarget
          destination: orders.forwarded
      binders:
        kafkaSource:
          type: kafka
          environment:
            spring:
              kafka:
                bootstrap-servers: kafka.internal:9092
        rabbitTarget:
          type: rabbit
          environment:
            spring:
              rabbitmq:
                host: rabbit.internal
                port: 5672
                username: ${RABBIT_USER}
                password: ${RABBIT_PASSWORD}
~~~

Các tên kafkaSource và rabbitTarget là tên binder configuration do ứng dụng đặt. Với explicit binder configuration, hãy khai báo đầy đủ tất cả binder cần dùng vì cơ chế tự phát hiện binder mặc định bị thay thế. Không đưa thông tin bí mật trực tiếp vào file cấu hình; dùng biến môi trường hoặc secret manager.

### 1.1. Function chỉ tạo luồng xử lý

Ví dụ function bridge:

~~~java
@Bean
Function<OrderCreated, OrderForwarded> bridgeOrder() {
    return order -> new OrderForwarded(
            order.eventId(),
            order.orderId(),
            order.customerId(),
            order.totalAmount(),
            order.createdAt(),
            1);
}
~~~

Function này chuyển payload từ input binding sang output binding. Spring Cloud Stream không vì thế mà tự tạo transaction bao phủ cả hai broker. Việc input được commit/ack lúc nào và output được xác nhận ở mức nào vẫn phụ thuộc binder, cấu hình và producer client.

### 1.2. Ranh giới transaction

~~~text
             Spring Cloud Stream application
       +------------------------------------------+
       | Function / message handler               |
       |                                          |
       | Input binding             Output binding |
       +------|--------------------------|---------+
              v                          v
        Broker nguồn               Broker đích
        Transaction A              Transaction B
~~~

Mỗi binder quản lý kết nối và tài nguyên theo broker của nó. Một transaction manager gắn với Kafka không thể tự đưa RabbitMQ publish hoặc Pulsar acknowledgment vào transaction Kafka. Tương tự, transaction Pulsar không tự bao gồm một Kafka offset hay RabbitMQ delivery tag.

Ngay cả khi các transaction manager được đồng bộ bằng callback hoặc commit theo chuỗi, việc đó không tạo ra một giao thức commit nguyên tử chung giữa các broker. Nếu tài nguyên thứ nhất commit thành công và tài nguyên thứ hai thất bại, hệ thống vẫn có trạng thái một phần đã commit.

## 2. Hai cửa sổ lỗi của một bridge

Giả sử bridge nhận message E từ Kafka và chuyển nó sang RabbitMQ. Có hai thao tác quan trọng:

- P: publish E tới RabbitMQ và nhận xác nhận đích.
- A: commit offset Kafka để xác nhận E đã xử lý.

Không có transaction chung giữa hai broker thì thứ tự P và A tạo ra trade-off.

### 2.1. Commit nguồn trước, publish đích sau

~~~text
1. Kafka giao E
2. Bridge commit offset Kafka
3. Bridge publish E tới RabbitMQ
4. Process bị dừng trước khi RabbitMQ nhận E
~~~

Kafka sẽ không giao lại E vì offset đã được commit. RabbitMQ cũng chưa có E. Message bị mất khỏi luồng bridge.

Đây là hành vi gần với at-most-once: một message không bị xử lý lặp bởi bridge, nhưng có thể không đến đích.

### 2.2. Publish đích trước, commit nguồn sau

~~~text
1. Kafka giao E
2. Bridge publish E tới RabbitMQ
3. RabbitMQ xác nhận publish
4. Process bị dừng trước khi Kafka commit offset
5. Kafka giao lại E sau khi bridge khởi động
6. Bridge publish E lần nữa
~~~

RabbitMQ có thể nhận hai bản E. Đây là duplicate window. Tuy nhiên, message chưa bị mất: Kafka vẫn giữ trách nhiệm giao lại vì offset chưa được commit.

Đây là nền tảng của at-least-once: ưu tiên không mất message và chấp nhận khả năng nhận trùng. Muốn đạt hành vi nghiệp vụ gần exactly-once, consumer đích phải nhận diện và bỏ qua duplicate bằng event ID ổn định.

### 2.3. Bảng quyết định thứ tự

| Thứ tự | Sự cố giữa hai bước | Hệ quả |
|---|---|---|
| Commit/ack nguồn rồi publish đích | Process dừng sau commit nguồn | Có thể mất message |
| Publish đích rồi commit/ack nguồn | Process dừng sau publish đích | Có thể publish trùng khi nguồn giao lại |
| Ghi inbox/outbox bền vững rồi ack nguồn | Process dừng sau DB commit, trước source ack | Nguồn giao lại; inbox dedupe |
| Publish outbox rồi đánh dấu sent | Process dừng sau publish, trước mark sent | Relay publish lại; đích dedupe |

Khi hai hệ thống không có transaction chung, không thể loại bỏ mọi cửa sổ lỗi chỉ bằng cách đổi thứ tự hai lệnh. Thiết kế phải làm cho retry an toàn.

## 3. Ba mức bảo đảm giao nhận

Các thuật ngữ delivery guarantee cần được hiểu ở phạm vi một chặng và một side effect cụ thể.

| Guarantee | Ý nghĩa | Rủi ro chính |
|---|---|---|
| At-most-once | Message được chuyển tối đa một lần | Có thể mất nếu xác nhận nguồn quá sớm |
| At-least-once | Message được giao lại cho tới khi có xác nhận phù hợp | Có thể có duplicate |
| Exactly-once trong transaction | Các thao tác thuộc cùng transaction được commit hoặc rollback cùng nhau | Chỉ áp dụng trong phạm vi tài nguyên/transaction hỗ trợ |
| Effectively-once | Có thể giao nhiều lần nhưng side effect nghiệp vụ chỉ được áp dụng một lần nhờ idempotency/deduplication | Cần lưu event ID và trạng thái xử lý bền vững |

### 3.1. Exactly-once không phải thuộc tính toàn hệ thống

Kafka EOS có thể kết hợp đọc, xử lý và ghi output Kafka trong một Kafka transaction; offset đầu vào được gửi vào transaction. Điều này hữu ích cho consume-process-produce trong cùng phạm vi Kafka transaction. Nó không tự bao gồm một database commit, HTTP call hoặc publish tới RabbitMQ.

Transaction bảo vệ tính nguyên tử của output và offset được commit, không có nghĩa đoạn code handler chỉ chạy đúng một lần. Sau rollback, record có thể được giao lại và logic xử lý có thể chạy lại. Mọi side effect ngoài Kafka transaction vẫn cần idempotency hoặc cơ chế riêng.

Pulsar transaction hỗ trợ atomic writes và acknowledgments qua nhiều topic/partition trong phạm vi transaction Pulsar. Spring for Apache Pulsar có thể kết hợp listener acknowledgment với transactional PulsarTemplate. Điều đó không làm transaction Pulsar bao phủ Kafka hoặc RabbitMQ.

RabbitMQ có publisher confirms và consumer acknowledgments, nhưng hai cơ chế này độc lập với nhau. Publisher confirm chỉ xác nhận broker đích đã nhận trách nhiệm về publish; consumer ack xác nhận bridge đã xử lý delivery từ nguồn. Một confirm không commit offset Kafka và một Rabbit ack không xác nhận RabbitMQ đã nhận publish từ một binder khác.

Vì vậy, khi nói bridge có effectively-once, hãy mô tả chính xác: message có thể được chuyển nhiều lần nhưng consumer đích dùng event ID và transaction database để chỉ áp dụng side effect một lần.

## 4. Transaction scope của từng broker

### 4.1. Kafka transaction

Kafka binder hỗ trợ transaction khi cấu hình transaction ID prefix khác rỗng:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: bridge-kafka-${INSTANCE_ID}-
~~~

Trong processor application, consumer bắt đầu transaction. Các record gửi trên consumer thread tham gia transaction đó; khi listener hoàn tất bình thường, container gửi offset vào transaction rồi commit. Các producer binding transactional dùng chung producer factory được cấu hình dưới transaction.producer.

Transaction Kafka phù hợp khi:

- Input được đọc từ Kafka.
- Output được ghi tới topic trong cùng Kafka transaction scope.
- Offset nguồn và output Kafka cần commit/rollback cùng nhau.

Nếu output binding dùng Rabbit binder, Rabbit publish không tham gia Kafka transaction. Nếu hai Kafka binder kết nối hai cluster khác nhau, không mặc định có một transaction bao phủ cả hai cluster. Hãy kiểm tra binder name, producer factory và transaction manager cụ thể.

Khi Kafka transaction rollback, retry và dead-letter có cách xử lý riêng ở container. Normal binder retry/DLQ không hoạt động như luồng non-transactional vì các record retry được publish trong transaction ban đầu có thể bị rollback cùng transaction. Cần cấu hình AfterRollbackProcessor và kiểm thử.

### 4.2. RabbitMQ acknowledgment và publisher confirm

RabbitMQ có hai xác nhận độc lập:

- Consumer acknowledgment: bridge báo với queue nguồn rằng delivery đã được xử lý.
- Publisher confirm: broker đích báo với publisher rằng publish đã được broker chấp nhận theo semantics của queue.

Một bridge RabbitMQ sang Kafka có thể publish vào Kafka rồi ack delivery RabbitMQ sau khi biết kết quả publish. Nếu process dừng sau Kafka commit nhưng trước Rabbit ack, RabbitMQ có thể giao lại message và Kafka nhận duplicate.

Với RabbitMQ làm đích, publisher confirm giúp xác nhận broker đã nhận publish. Nếu message không route tới queue nào, publisher có thể dùng mandatory và xử lý basic.return; confirm không đồng nghĩa đã có consumer xử lý message.

Không bật auto-ack cho consumer bridge quan trọng nếu message chỉ được xác nhận ngay khi broker gửi qua socket. Hãy dùng manual acknowledgment hoặc binder behavior tương đương, và xác nhận message chỉ sau khi dữ liệu đích đã được nhận trách nhiệm.

### 4.3. Pulsar transaction

Pulsar native transaction có thể kết hợp:

- Publish message tới nhiều topic/partition.
- Acknowledge message được consume.
- Commit tất cả thao tác hoặc abort tất cả thao tác trong transaction.

Với Spring for Apache Pulsar, transactional listener container bắt đầu transaction; acknowledgment được enlist vào transaction; các send bằng transactional PulsarTemplate tham gia transaction đang hoạt động. Điều này hỗ trợ consume-process-produce trong Pulsar.

Pulsar transaction chỉ bao phủ những thao tác được enlist vào transaction Pulsar tương ứng. Gửi sang Kafka hoặc RabbitMQ không tự tham gia transaction đó. Nếu dùng Spring Cloud Stream Pulsar binder, hãy xác minh phiên bản binder có expose transaction behavior mong muốn; không suy ra rằng mọi cấu hình PulsarTemplate tự áp dụng cho binding của binder.

### 4.4. Ma trận phạm vi

| Nguồn | Đích | Cơ chế có thể phối hợp | Giới hạn |
|---|---|---|---|
| Kafka | Kafka cùng transaction scope | Kafka transaction: output và input offset | Không bao gồm DB/HTTP hoặc cluster khác |
| Pulsar | Pulsar trong cùng transaction | Pulsar transaction: output và input acknowledgment | Không bao gồm Kafka/Rabbit |
| RabbitMQ | RabbitMQ | Consumer ack và publisher confirm; channel transaction trong phạm vi Rabbit | Confirm và ack vẫn là hai cơ chế riêng |
| Kafka | RabbitMQ | Kafka offset commit và Rabbit publisher confirm theo thứ tự ứng dụng | Không có atomic cross-broker commit |
| RabbitMQ | Pulsar | Rabbit consumer ack và Pulsar publish/transaction | Không có atomic cross-broker commit |
| Pulsar | Kafka | Pulsar acknowledgment và Kafka producer transaction | Không có atomic cross-broker commit |

## 5. Bridge trực tiếp với at-least-once

Bridge trực tiếp là lựa chọn đơn giản khi chấp nhận duplicate và có thể làm consumer đích idempotent.

Quy trình:

1. Nhận message từ broker nguồn.
2. Kiểm tra schema và event ID.
3. Chuyển payload sang canonical event envelope.
4. Publish sang broker đích.
5. Chờ xác nhận publish theo cơ chế của binder/client đích.
6. Chỉ sau khi publish được xác nhận, để binder commit offset hoặc ack message nguồn.
7. Nếu publish thất bại hoặc kết quả không rõ, không xác nhận nguồn; cho phép retry.

~~~mermaid
sequenceDiagram
    participant S as Broker nguồn
    participant B as Bridge
    participant D as Broker đích
    S->>B: Giao event E
    B->>B: Validate và map envelope
    B->>D: Publish E
    D-->>B: Confirm/ack publish
    B-->>S: Commit offset / consumer ack
    Note over B,D: Crash sau confirm, trước source ack có thể tạo duplicate
~~~

### 5.1. Cần xác nhận ở mức broker

Một lệnh gửi message trả về thành công ở tầng ứng dụng không phải lúc nào cũng có nghĩa broker đích đã ghi message bền vững. Tùy binder, send có thể chỉ xác nhận channel đã nhận message để xử lý bất đồng bộ.

Với bridge cần độ tin cậy:

- Xác định API nào trả kết quả publish thực tế.
- Dùng publisher confirms/acks hoặc transaction commit của broker đích.
- Kiểm tra unroutable message và broker nack.
- Chỉ xác nhận nguồn sau khi đích đã nhận trách nhiệm.
- Đặt timeout và xử lý trạng thái kết quả không xác định như một khả năng duplicate.

Spring Cloud Stream chuẩn hóa binding, nhưng không cung cấp một kiểu confirm chung có cùng semantics cho Kafka, RabbitMQ và Pulsar. Nếu cần chờ xác nhận broker-specific, phải dùng capability của binder/client tương ứng hoặc chọn kiến trúc outbox.

### 5.2. Ví dụ function chỉ để minh họa mapping

~~~java
@Bean
Function<OrderCreated, OrderForwarded> bridgeOrder() {
    return order -> new OrderForwarded(
            order.eventId(),
            order.orderId(),
            order.customerId(),
            order.totalAmount(),
            order.occurredAt(),
            1);
}

record OrderCreated(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        Instant occurredAt) {}

record OrderForwarded(
        String eventId,
        String orderId,
        String customerId,
        BigDecimal totalAmount,
        Instant occurredAt,
        int schemaVersion) {}
~~~

Ví dụ cho thấy cách chuyển payload từ input binding sang output binding. Nó chưa tự chứng minh broker đích đã confirm trước khi nguồn commit. Với binder bất đồng bộ, cần xác minh publish result hoặc dùng outbox relay để tách việc lưu message bền vững khỏi việc ack nguồn.

## 6. Transactional outbox/inbox cho bridge tin cậy

Khi cần bảo đảm không mất event qua ranh giới broker, một lựa chọn mạnh là dùng database làm điểm lưu bền vững trung gian. Inbox lưu event đã nhận từ nguồn; outbox lưu event cần gửi sang đích. Việc ghi inbox và outbox nằm trong cùng database transaction.

~~~mermaid
flowchart LR
    A[Broker nguồn] --> B[Bridge consumer]
    B --> C[(DB transaction)]
    C --> D[Inbox: source event ID]
    C --> E[Outbox: target event]
    E --> F[Outbox relay]
    F --> G[Broker đích]
    G --> H[Consumer đích]
    H --> I[(Inbox đích / business DB)]
~~~

### 6.1. Tiếp nhận từ broker nguồn

1. Consumer nhận event E có eventId ổn định.
2. Mở database transaction.
3. Insert eventId vào bridge_inbox với unique constraint.
4. Nếu eventId đã tồn tại, không tạo outbox row lần nữa.
5. Nếu là event mới, ghi payload/canonical envelope vào bridge_outbox.
6. Commit database transaction.
7. Chỉ sau khi transaction database commit thành công, handler trả thành công để binder commit offset hoặc ack nguồn.

Nếu process dừng sau bước 6 nhưng trước bước 7, broker nguồn sẽ giao lại event. Unique constraint trong bridge_inbox nhận diện duplicate; ứng dụng không tạo thêm outbox row. Event đã được lưu bền vững nên không bị mất.

### 6.2. Schema bảng minh họa

~~~sql
CREATE TABLE bridge_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE bridge_outbox (
    outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id VARCHAR(200) NOT NULL,
    destination VARCHAR(200) NOT NULL,
    payload JSON NOT NULL,
    aggregate_id VARCHAR(200),
    aggregate_sequence BIGINT,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    UNIQUE (destination, event_id)
);
~~~

DDL trên mang tính minh họa; kiểu JSON, identity, timestamp và cú pháp unique phụ thuộc database. Nếu cần giữ thứ tự theo aggregate, lưu aggregate_id và aggregate_sequence để relay có thể publish tuần tự theo key.

Ví dụ service ghi inbox và outbox trong cùng database transaction:

~~~java
@Service
class BridgeInboxService {

    private final BridgeInboxRepository inbox;
    private final BridgeOutboxRepository outbox;

    BridgeInboxService(
            BridgeInboxRepository inbox,
            BridgeOutboxRepository outbox) {
        this.inbox = inbox;
        this.outbox = outbox;
    }

    @Transactional
    public void store(OrderCreated event) {
        boolean firstDelivery =
                inbox.insertIfAbsent("order-bridge", event.eventId());

        if (!firstDelivery) {
            return;
        }

        outbox.save(BridgeOutbox.from(event));
    }
}

@Bean
Consumer<OrderCreated> bridgeInput(BridgeInboxService service) {
    return service::store;
}
~~~

insertIfAbsent phải được triển khai bằng unique constraint và thao tác insert nguyên tử của database; không dùng kiểu SELECT trước rồi INSERT vì hai consumer đồng thời có thể cùng vượt qua bước kiểm tra. Service phải được gọi qua Spring proxy để @Transactional thực sự mở transaction. Handler chỉ trả thành công sau khi service transaction đã commit; không đưa phần ghi inbox/outbox sang tác vụ bất đồng bộ rồi ack nguồn trước.

### 6.3. Outbox relay

Relay đọc các row chưa publish, gửi payload tới broker đích và đợi xác nhận publish. Chỉ sau khi có xác nhận phù hợp mới đánh dấu published_at.

~~~text
SELECT outbox rows
  WHERE published_at IS NULL
  ORDER BY outbox_id
  FOR UPDATE SKIP LOCKED

For each row:
  publish to destination
  wait for broker-specific confirmation
  if confirmed:
      mark published_at
  else:
      increment attempts and store error
~~~

Không giữ database transaction mở trong lúc chờ broker quá lâu nếu có thể tránh. Một mô hình phổ biến là claim row bằng trạng thái/lease trong transaction ngắn, publish bên ngoài transaction, rồi cập nhật kết quả bằng transaction mới. Lease phải có timeout để worker khác tiếp quản khi process chết.

### 6.4. Cửa sổ duplicate của outbox relay

Nếu broker đích đã nhận message nhưng relay dừng trước khi đánh dấu outbox row là published, relay sẽ gửi lại row sau khi khởi động. Đây là duplicate có chủ đích để tránh mất message.

Consumer đích cần inbox/dedup theo eventId. Khi consumer nhận message:

1. Mở database transaction.
2. Insert eventId vào bảng processed_message có unique constraint.
3. Nếu eventId đã tồn tại, bỏ qua side effect và kết thúc thành công.
4. Nếu mới, áp dụng thay đổi nghiệp vụ trong cùng transaction.
5. Commit database transaction.
6. Chỉ sau commit mới ack/commit offset message đích.

Nhờ vậy, nhiều lần giao cùng event vẫn chỉ tạo một lần thay đổi nghiệp vụ trong database đích.

### 6.5. CDC và outbox relay

Thay vì polling outbox table, có thể dùng Change Data Capture (CDC) để đọc các row đã commit rồi publish sang broker. CDC giảm polling và có thể giữ thứ tự theo log database, nhưng cần vận hành connector, schema history, offset và recovery.

Dù dùng polling hay CDC, publish vẫn có thể lặp khi relay không biết broker đã nhận message trước khi connection đứt. Consumer đích vẫn cần idempotency.

## 7. Event envelope và hợp đồng dữ liệu xuyên broker

Không nên sao chép nguyên vẹn message headers nội bộ của broker nguồn sang broker đích. Offset Kafka, Rabbit delivery tag, Pulsar MessageId, consumer group metadata và header retry của broker có ý nghĩa trong phạm vi broker cụ thể.

Hãy định nghĩa một canonical event envelope:

~~~json
{
  "eventId": "01JORDER8W4M8F6GQY2",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "source": "order-service",
  "occurredAt": "2026-11-24T08:30:00Z",
  "aggregateType": "Order",
  "aggregateId": "order-812",
  "aggregateSequence": 12,
  "correlationId": "checkout-91",
  "traceparent": "00-...",
  "payload": {
    "orderId": "order-812",
    "customerId": "customer-31",
    "totalAmount": 125000
  }
}
~~~

Các trường quan trọng:

| Trường | Mục đích |
|---|---|
| eventId | ID ổn định để dedup xuyên broker |
| eventType | Loại sự kiện nghiệp vụ |
| schemaVersion | Phiên bản schema của payload |
| source | Dịch vụ phát sinh event |
| occurredAt | Thời điểm nghiệp vụ xảy ra |
| aggregateId | Key để giữ thứ tự theo entity |
| aggregateSequence | Phát hiện duplicate, gap và out-of-order |
| correlationId | Liên kết các bước của một workflow |
| traceparent | Truyền trace context theo chuẩn tracing |
| payload | Dữ liệu nghiệp vụ đã chuẩn hóa |

### 7.1. Schema mapping

Kafka, RabbitMQ và Pulsar có thể dùng serialization, schema registry hoặc content-type khác nhau. Bridge cần:

- Đọc schema nguồn.
- Validate payload.
- Chuyển đổi sang canonical model hoặc schema đích.
- Giữ eventId và correlation metadata.
- Ghi schemaVersion mới nếu transform thay đổi cấu trúc.
- Đưa payload không hợp lệ vào quarantine thay vì retry vô hạn.

Không dùng broker offset làm eventId. Offset chỉ duy nhất trong partition/topic và có thể thay đổi khi replay hoặc migrate. EventId phải được tạo ở nguồn và giữ ổn định qua mọi lần chuyển tiếp.

### 7.2. Kích thước và giới hạn message

Broker có giới hạn message size, batch size và header. Một payload hợp lệ ở broker nguồn có thể vượt giới hạn broker đích. Bridge cần kiểm tra kích thước sau khi serialize và có chính sách cho payload lớn: nén, object storage reference hoặc quarantine.

## 8. Ordering khi chuyển broker

At-least-once có thể tạo duplicate; nhiều worker relay có thể làm đảo thứ tự. Nếu nghiệp vụ cần thứ tự, phải xác định phạm vi thứ tự cần bảo vệ.

### 8.1. Thứ tự theo aggregate

Dùng aggregateId làm key/partition key/routing key tương ứng với khả năng của broker đích. Lưu aggregateSequence để consumer phát hiện:

- Duplicate: sequence đã được xử lý.
- Out-of-order: sequence nhỏ hơn hoặc lớn hơn sequence mong đợi.
- Gap: thiếu một sequence ở giữa.

### 8.2. Nhiều outbox worker

Nếu nhiều worker claim row độc lập, event sequence 12 có thể được publish trước sequence 11. Để giữ thứ tự:

- Partition outbox theo aggregateId.
- Chỉ cho một worker xử lý một aggregate tại một thời điểm.
- Chỉ publish sequence kế tiếp sau khi sequence trước được xác nhận.
- Dùng destination partition key hoặc routing key theo aggregateId.
- Consumer đích kiểm tra sequence và có chính sách chờ/quarantine khi phát hiện gap.

Không cần giữ thứ tự toàn cục nếu nghiệp vụ chỉ yêu cầu thứ tự theo orderId hoặc accountId. Thu hẹp phạm vi thứ tự giúp tăng throughput.

## 9. Retry, dead-letter và quarantine trong bridge

Lỗi bridge nên được phân loại:

| Loại lỗi | Ví dụ | Hành động |
|---|---|---|
| Tạm thời | Broker đích mất kết nối, timeout, throttling | Retry với exponential backoff và jitter |
| Có thể phục hồi sau vận hành | Credentials hết hạn, ACL thiếu | Dừng tăng retry, cảnh báo và tiếp tục sau khi sửa |
| Dữ liệu vĩnh viễn lỗi | Schema không hợp lệ, payload vượt giới hạn | Quarantine/DLQ |
| Duplicate | EventId đã được xử lý | Ack/commit thành công sau dedup |
| Conflict thứ tự | Sequence có gap hoặc out-of-order | Retry có giới hạn hoặc cách ly theo aggregate |

### 9.1. Retry không làm mất event

Nếu bridge trực tiếp, không ack/commit nguồn khi chưa biết đích đã nhận message. Nếu dùng outbox, không xóa outbox row khi publish chưa được xác nhận. Ghi số lần thử, lỗi cuối, thời điểm retry tiếp theo và destination.

### 9.2. DLQ và quarantine

DLQ giữ message không xử lý được để điều tra. Quarantine nên giữ canonical envelope, eventId, broker nguồn, destination, lỗi và số lần thử. Không tự động replay message lỗi schema hoặc nghiệp vụ mà chưa sửa nguyên nhân.

Khi replay:

1. Giữ nguyên eventId gốc.
2. Ghi nhận người hoặc workflow thực hiện replay.
3. Chọn đúng destination và schema version.
4. Dùng idempotent consumer.
5. Theo dõi duplicate và kết quả nghiệp vụ.

### 9.3. Tránh retry storm

Nếu broker đích ngừng hoạt động, retry nhanh trên mọi message có thể làm cạn thread, connection và database. Dùng exponential backoff, jitter, bounded concurrency, circuit breaker hoặc pause/resume phù hợp. Outbox giữ backlog bền vững trong khi relay giảm tốc độ.

## 10. Transaction với database và broker

Một bridge có thể cập nhật database và gửi message. Nếu DB commit và broker publish là hai thao tác riêng, đây cũng là dual-write.

Ví dụ rủi ro:

~~~text
DB commit thành công
    |
    +-- process crash trước publish
            -> DB đã đổi, event không được gửi

Publish thành công
    |
    +-- DB rollback
            -> downstream thấy event không tương ứng với DB
~~~

Transactional outbox ghi business data và event row trong cùng database transaction. Relay đọc event row đã commit và publish sau đó. Đây là cách phổ biến để tránh dual-write DB/message.

### 10.1. Spring transaction synchronization không phải distributed atomic commit

Spring có thể đồng bộ callback giữa các transaction manager hoặc gọi nhiều transaction manager theo thứ tự. Điều này có thể giúp chọn thứ tự commit và rollback trong một số tình huống, nhưng không tự cung cấp một coordinator hai pha chung cho Kafka, RabbitMQ, Pulsar và database.

Nếu tài nguyên thứ nhất commit rồi tài nguyên thứ hai thất bại, không thể giả định tài nguyên thứ nhất tự rollback. Hãy dùng outbox/inbox hoặc saga khi cần tính nhất quán giữa nhiều dịch vụ.

### 10.2. Saga cho nghiệp vụ nhiều dịch vụ

Nếu bridge chỉ chuyển event, outbox/inbox thường đủ. Nếu workflow còn thực hiện nhiều thay đổi nghiệp vụ độc lập như giữ tồn kho, thu tiền và tạo vận đơn, hãy dùng saga:

- Mỗi service commit transaction cục bộ của nó.
- Service phát event kết quả hoặc thất bại.
- Orchestrator/choreography quyết định bước tiếp theo.
- Nếu bước sau thất bại, thực hiện compensating action.

Saga không tạo một transaction ACID toàn hệ thống; nó quản lý tính nhất quán cuối cùng qua các bước và hành động bù.

## 11. Cấu hình và vận hành nhiều binder

### 11.1. Chọn binder cho từng binding

Khai báo binder theo binding name:

~~~properties
spring.cloud.stream.bindings.bridgeOrder-in-0.binder=kafkaSource
spring.cloud.stream.bindings.bridgeOrder-out-0.binder=rabbitTarget
~~~

Nếu có nhiều broker cùng loại, khai báo từng binder configuration với type và environment riêng. Khi dùng explicit binder configuration, tất cả binder cần thiết phải được liệt kê.

### 11.2. Cấu hình transaction của Kafka không áp dụng cho Rabbit output

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          transaction:
            transaction-id-prefix: bridge-kafka-${INSTANCE_ID}-
~~~

Thuộc tính này bật transaction cho Kafka binder. Nó không làm Rabbit output binding trở thành thành viên của Kafka transaction. Nếu input là Kafka và output là Rabbit, phải dùng cơ chế bridge at-least-once/outbox đã mô tả.

### 11.3. Tách cấu hình và quyền truy cập

Mỗi binder có endpoint, credentials, TLS, truststore, retry và timeout riêng. Hãy:

- Dùng secret riêng cho từng broker.
- Giới hạn quyền consumer ở nguồn và producer ở đích.
- Cấu hình TLS/hostname verification.
- Không log credentials hoặc payload nhạy cảm.
- Đặt connection timeout và retry theo đặc tính từng broker.
- Theo dõi health của từng binder độc lập.

Một broker đích bị lỗi không nhất thiết có nghĩa broker nguồn bị lỗi. Với outbox, nguồn có thể tiếp tục nhận và lưu event trong giới hạn dung lượng DB; relay sẽ gửi lại khi đích phục hồi.

## 12. Kiểm thử bảo đảm giao nhận

Kiểm thử chỉ xác minh function trả đúng object là chưa đủ. Cần kiểm tra broker acknowledgment, offset/ack, duplicate và failure window.

### 12.1. Kiểm thử mapping và schema

- Gửi event mẫu từ broker nguồn.
- Xác minh event envelope ở broker đích.
- Kiểm tra eventId, aggregateId, schemaVersion và payload.
- Kiểm tra header broker-specific không bị dùng làm business identity.
- Kiểm tra payload lớn và schema không hợp lệ.

### 12.2. Kiểm thử crash theo từng thời điểm

Tạo các điểm dừng có kiểm soát:

1. Sau khi source giao message nhưng trước khi bridge xử lý.
2. Sau khi publish target nhưng trước khi nhận confirm.
3. Sau khi nhận confirm target nhưng trước khi commit/ack source.
4. Sau khi DB inbox/outbox commit nhưng trước source ack.
5. Sau khi target publish thành công nhưng trước khi đánh dấu outbox row đã gửi.
6. Sau khi target consumer commit DB nhưng trước khi ack message đích.

Xác minh:

- Không có message bị mất ngoài guarantee đã chọn.
- Duplicate có thể xảy ra ở các cửa sổ không xác định kết quả.
- Deduplication ngăn side effect nghiệp vụ lặp.
- Outbox row không bị xóa khi publish chưa được xác nhận.
- Message được replay sau khi broker phục hồi.

### 12.3. Kiểm thử broker outage

- Tắt hoặc làm gián đoạn broker đích.
- Xác minh source không bị ack quá sớm.
- Với outbox, xác minh event được lưu và backlog tăng có kiểm soát.
- Khôi phục broker đích và xác minh relay tiếp tục.
- Kiểm tra retry không tạo storm hoặc làm cạn pool.

### 12.4. Kiểm thử ordering và duplicate

Gửi nhiều event cùng aggregateId với sequence tăng dần. Làm relay chạy nhiều worker và tạo retry. Xác minh consumer đích chỉ áp dụng sequence đúng thứ tự hoặc phát hiện gap theo policy. Gửi lại cùng eventId nhiều lần và xác minh side effect chỉ được thực hiện một lần.

### 12.5. Test binder và integration test

Spring Cloud Stream Test Binder hữu ích để kiểm tra function và binding logic trong môi trường đơn giản. Nó không mô phỏng đầy đủ broker transaction, publisher confirm, consumer ack, partition assignment hoặc broker failure.

Hãy bổ sung integration test với broker thật hoặc Testcontainers cho từng loại binder được sử dụng. Nếu bridge nối Kafka và RabbitMQ, cần kiểm tra cả hai broker trong cùng test và xác minh trạng thái cuối cùng ở mỗi bên.

## 13. Quan sát và vận hành

Theo dõi từng chặng của bridge:

| Chỉ số | Ý nghĩa |
|---|---|
| Source consumer lag | Backlog tại broker nguồn |
| Source ack/commit latency | Thời gian xác nhận nguồn |
| Target publish confirm latency | Thời gian broker đích xác nhận |
| Target nack/return/error rate | Publish thất bại hoặc không route |
| Outbox pending count | Số event đang chờ gửi |
| Oldest outbox age | Thời gian event chờ lâu nhất |
| Outbox retry count | Số lần relay thử lại |
| Inbox duplicate count | Số event đã nhận trùng |
| Quarantine/DLQ depth | Message cần điều tra |
| End-to-end event age | Tuổi event từ occurredAt tới xử lý đích |
| Per-broker connection health | Tình trạng kết nối từng broker |

### 13.1. Cảnh báo

Cân nhắc cảnh báo khi:

- Source lag tăng trong khi target publish lỗi.
- Target confirm latency vượt SLA.
- Outbox pending hoặc oldest age tăng liên tục.
- Quarantine/DLQ có message mới bất thường.
- Duplicate rate tăng mạnh.
- Có gap aggregate sequence.
- Một binder mất kết nối kéo dài.
- Database outbox gần đạt giới hạn dung lượng.

Dashboard nên phân biệt event đã nhận ở nguồn, event đã lưu bền vững vào outbox, event đã được broker đích xác nhận và event đã được consumer đích xử lý. Bốn trạng thái này không đồng nghĩa.

## 14. Những lỗi thường gặp

1. **Cho rằng nhiều binder tạo một transaction chung**: binder chỉ chọn middleware cho binding. Hãy xác định transaction manager và broker scope của từng thao tác.
2. **Ack nguồn trước khi đích nhận message**: process crash có thể làm mất event. Hãy publish/confirm đích trước hoặc lưu outbox bền vững.
3. **Publish đích rồi ack nguồn nhưng không dedupe**: crash giữa hai bước tạo duplicate. Hãy giữ eventId và dùng inbox/unique constraint.
4. **Coi send() thành công là broker đã ghi bền vững**: channel acceptance khác publisher confirmation. Hãy xác minh semantics của binder/client.
5. **Dùng Kafka transaction cho Rabbit/Pulsar output**: output khác broker không tham gia transaction Kafka. Hãy dùng outbox hoặc bridge at-least-once.
6. **Dùng Pulsar transaction để commit Kafka offset**: Pulsar transaction không bao phủ Kafka. Hãy giới hạn kỳ vọng trong transaction scope của Pulsar.
7. **Nhầm Rabbit publisher confirm với consumer ack**: hai cơ chế độc lập và không xác nhận lẫn nhau. Hãy kiểm tra cả hai phía.
8. **Dùng @Transactional mà không chỉ rõ resource**: một transaction manager được chọn không tự quản lý tất cả binder. Hãy xác định transaction manager cụ thể.
9. **Dùng ChainedTransactionManager như 2PC**: commit theo chuỗi vẫn có thể để lại trạng thái một phần. Hãy dùng outbox/inbox cho reliability.
10. **Đánh dấu outbox sent trước publisher confirm**: crash có thể làm mất event. Hãy chỉ mark sent sau xác nhận đích.
11. **Không giữ thứ tự khi chạy nhiều relay worker**: event sau có thể đến trước event trước. Hãy partition theo aggregate và dùng sequence.
12. **Dùng offset hoặc delivery tag làm eventId**: các định danh này chỉ có ý nghĩa trong broker nguồn. Hãy dùng ID nghiệp vụ ổn định.
13. **Retry vô hạn lỗi schema**: poison message chiếm tài nguyên. Hãy phân loại lỗi và quarantine.
14. **Replay bằng eventId mới**: consumer coi replay là event mới và lặp side effect. Hãy giữ eventId gốc.
15. **Chỉ test function bằng Test Binder**: test không chứng minh broker confirm/ack hoặc failure recovery. Hãy integration test cả hai broker.

## 15. Quy trình thiết kế bridge broker

Khi triển khai một bridge bằng Spring Cloud Stream:

1. Liệt kê broker nguồn, broker đích và binder name cho từng binding.
2. Xác định transaction boundary thực tế của mỗi broker.
3. Chọn delivery guarantee cho từng chặng và nêu rõ khả năng duplicate.
4. Định nghĩa canonical event envelope với eventId ổn định.
5. Quyết định bridge trực tiếp hay dùng database inbox/outbox.
6. Nếu bridge trực tiếp, publish và chờ xác nhận đích trước source ack/commit.
7. Nếu dùng outbox, commit inbox/outbox trước source ack và chỉ mark sent sau target confirmation.
8. Làm consumer đích idempotent bằng eventId và unique constraint.
9. Thiết kế ordering theo aggregateId và sequence nếu nghiệp vụ yêu cầu.
10. Phân loại lỗi, cấu hình retry/backoff và quarantine.
11. Kiểm thử crash tại mọi cửa sổ publish/ack/commit.
12. Theo dõi lag, confirm, outbox age, duplicate và DLQ.
13. Lập runbook cho replay, broker outage, schema migration và xử lý backlog.

## Kết luận

Spring Cloud Stream cho phép một ứng dụng dùng nhiều binder để đọc và ghi qua các broker khác nhau, nhưng lựa chọn binder không tạo ra transaction phân tán. Kafka transaction chỉ bao phủ các thao tác Kafka tham gia cùng transaction; Pulsar transaction bao phủ các write/ack được enlist trong transaction Pulsar; RabbitMQ publisher confirms và consumer acknowledgments xác nhận hai chiều độc lập.

Với bridge trực tiếp, publish đích rồi mới xác nhận nguồn giúp tránh mất message nhưng có thể tạo duplicate nếu process dừng giữa hai bước. Hãy giữ eventId ổn định và làm consumer đích idempotent. Khi cần độ tin cậy cao, transactional inbox/outbox lưu event bền vững trước source ack, relay publish tới đích và chỉ đánh dấu đã gửi sau confirmation. Duplicate vẫn có thể xuất hiện sau timeout hoặc crash, vì vậy deduplication, ordering, retry, quarantine và kiểm thử failure là các phần bắt buộc của thiết kế.

## Tài liệu tham khảo

- [Spring Cloud Stream — Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html)
- [Spring Cloud Stream — Connecting to Multiple Systems](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-systems.html)
- [Spring Cloud Stream — Kafka Transactional Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/transactional.html)
- [Spring for Apache Kafka — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [Spring for Apache Pulsar — Transactions](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/transactions.html)
- [Apache Pulsar — Transactions](https://pulsar.apache.org/docs/4.2.x/txn-what/)
- [Transactional Outbox Pattern — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
