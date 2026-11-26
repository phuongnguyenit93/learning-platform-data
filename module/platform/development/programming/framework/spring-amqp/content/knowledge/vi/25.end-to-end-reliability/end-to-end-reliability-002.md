# Xác định các cửa sổ mất thông điệp và xử lý trùng

Một ứng dụng dùng **RabbitMQ và Spring AMQP** có thể ghi đơn hàng thành công, gọi `RabbitTemplate.convertAndSend()` mà không gặp exception, rồi vẫn không có consumer nào xử lý sự kiện. Ở chiều ngược lại, một consumer có thể ghi dữ liệu thành công nhưng sau khi khởi động lại lại nhận **cùng một message lần thứ hai**. Hai tình huống này không mâu thuẫn: publish, routing, lưu trữ, delivery, cập nhật nghiệp vụ và acknowledgment là những bước **không nằm trong một giao dịch nguyên tử duy nhất**.

Trong chương **Độ tin cậy đầu cuối** của module **SPRING_AMQP**, bài học tập trung vào câu hỏi:

> Từ lúc nghiệp vụ tạo ra một sự kiện đến khi tác dụng của sự kiện được lưu bền vững, những khoảng thời gian nào có thể làm **mất thông điệp**, tạo ra **kết quả không chắc chắn** hoặc khiến ứng dụng **xử lý trùng**?

Cách giải quyết là quan sát toàn bộ vòng đời message, phối hợp đúng `RabbitTemplate`, publisher confirms/returns, durable exchange–queue–binding, `@RabbitListener`, acknowledgment, retry, dead-letter, giao dịch cơ sở dữ liệu và idempotency. Không có một cờ cấu hình RabbitMQ duy nhất bảo đảm mọi bước đầu cuối thành công đúng một lần.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Vẽ đường đi của một event từ **giao dịch ghi nghiệp vụ** qua producer, broker, consumer đến **giao dịch ghi kết quả**.
2. Xác định cửa sổ có thể mất event hoặc sinh ra bản sao khi tiến trình, broker hay mạng gặp lỗi.
3. Phân biệt **publisher confirm**, **publisher return**, **consumer ACK** và **kết quả nghiệp vụ đã commit**.
4. Giải thích tại sao bảo đảm *at-least-once delivery* thường đi kèm **duplicate delivery**, và tại sao phải xử lý idempotent.
5. Thiết kế **transactional outbox** cho phía phát sự kiện và **inbox/deduplication** cho phía xử lý.
6. Chọn thời điểm ACK, chiến lược retry/DLQ, khóa idempotency, giám sát và kịch bản kiểm thử lỗi.
7. Nhận biết giới hạn của các giải pháp khi side effect nằm ở hệ thống ngoài database.

## 2. Phân biệt ba loại “thành công”

Trong một luồng message, cần tách ít nhất ba cột mốc:

| Cột mốc | Điều có thể xác nhận | Điều chưa thể suy ra |
| --- | --- | --- |
| **Nghiệp vụ phía producer đã commit** | Thay đổi dữ liệu nguồn đã bền vững trong database nguồn | Event tương ứng đã được RabbitMQ nhận |
| **Broker xác nhận publish** | Broker xác nhận xử lý publish theo cơ chế publisher confirm | Message đã đến đúng queue nếu không kiểm tra routing; consumer đã xử lý |
| **Consumer đã commit và ACK** | Tác dụng nghiệp vụ đã commit nếu ứng dụng sắp xếp đúng thứ tự; broker có thể loại delivery sau ACK | Phía caller biết chắc không có bản sao, hoặc side effect ngoài DB chỉ xảy ra một lần |

**Publisher confirm** xác nhận thao tác publish ở phía broker; **consumer ACK** xác nhận delivery trên kênh tiêu thụ. Chúng là hai cơ chế độc lập. Ngay cả khi cả hai đều tồn tại, không nên gọi đó là bảo đảm *exactly-once business processing* nếu consumer không có cơ chế xử lý trùng.

Các thuật ngữ cần nhất quán:

- **Message loss**: một sự kiện đáng lẽ phải được xử lý nhưng không còn đường đáng tin cậy nào dẫn đến việc xử lý nó.
- **Unknown outcome**: caller không nhận được xác nhận nên **không biết** bên kia đã thực hiện hay chưa. Nếu thử lại, có thể tạo duplicate.
- **Duplicate delivery**: cùng một message hoặc cùng một event nghiệp vụ được giao lại nhiều lần.
- **Duplicate effect**: một side effect nghiệp vụ bị áp dụng nhiều lần, ví dụ trừ tồn kho hai lần. Duplicate delivery chỉ gây duplicate effect khi handler không được bảo vệ.
- **Idempotency**: áp dụng lại cùng một yêu cầu với cùng khóa vẫn cho hiệu quả nghiệp vụ như áp dụng một lần.
- **At-least-once**: trong các giả định và điều kiện vận hành phù hợp, hệ thống tiếp tục thử giao/xử lý cho đến khi thành công; bản sao có thể xuất hiện. Không có nghĩa dữ liệu được giữ mãi trong mọi chính sách TTL, purge hoặc xóa queue.

## 3. Đường đi và các cửa sổ rủi ro

Xem một hệ thống đơn hàng: dịch vụ Order ghi trạng thái `PAID` rồi phát `OrderPaid`. Dịch vụ Inventory nhận event để giảm tồn kho và ghi projection.

~~~mermaid
flowchart LR
    DB1["DB Order: commit"] --> OB["Outbox của producer"]
    OB --> RELAY["Outbox relay"]
    RELAY --> PUB["RabbitTemplate publish"]
    PUB --> EX["RabbitMQ exchange"]
    EX --> Q["Durable queue"]
    Q --> L["@RabbitListener"]
    L --> DB2["DB Inventory: transaction"]
    DB2 --> ACK["Consumer ACK"]
    L -. "Lỗi quá ngưỡng" .-> DLQ["DLX / DLQ"]
~~~

Sơ đồ trên là kiến trúc mục tiêu. Nếu ứng dụng gửi trực tiếp sau khi ghi DB, hoặc ACK trước khi DB commit, những cửa sổ rủi ro xuất hiện ngay tại các cạnh nối.

### 3.1. Bảng phân tích lỗi theo thời điểm

| Cửa sổ | Sự cố có thể xảy ra | Hậu quả | Biện pháp chính |
| --- | --- | --- | --- |
| **W1 — DB nguồn commit, chưa publish** | Producer crash hoặc mất kết nối | **Mất sự kiện** dù đơn hàng đã thay đổi | Transactional outbox trong cùng DB transaction |
| **W2 — Đã gọi publish, chưa có confirm** | Mất kết nối hoặc timeout | **Không rõ** broker đã nhận hay chưa; gửi lại có thể trùng | Ghi trạng thái outbox, retry với cùng `eventId`, publisher confirms |
| **W3 — Broker nhận publish nhưng không có binding tới queue** | Exchange không route được | Message có thể bị bỏ dù publish được ACK | `mandatory=true` + publisher returns; kiểm tra topology |
| **W4 — Broker/queue chưa giữ bền vững** | Broker mất điện, cấu hình queue/message không phù hợp | Mất message chưa được bảo vệ bằng chính sách durability mong muốn | Durable queue, persistent message, xác nhận publish và chiến lược queue phù hợp |
| **W5 — Đã confirm, chưa đánh dấu outbox đã gửi** | Relay crash hoặc DB update lỗi | Outbox được phát lại; **duplicate event** | Consumer idempotent; relay có thể gửi lại an toàn |
| **W6 — Consumer đã nhận, chưa xử lý xong** | Consumer crash | Message có thể được redeliver nếu chưa ACK | ACK sau xử lý; retry hữu hạn; không dựa vào “nhận một lần” |
| **W7 — ACK trước khi kết quả nghiệp vụ commit** | DB rollback sau ACK | **Mất tác dụng nghiệp vụ** vì broker đã loại delivery | Không ACK sớm; commit trước ACK |
| **W8 — DB đích commit, chưa ACK** | Consumer crash hoặc ACK bị mất | Broker redeliver; **duplicate delivery** | Inbox/dedup cùng DB transaction với side effect |
| **W9 — Đã gọi side effect ngoài DB, chưa lưu trạng thái** | HTTP trả timeout hoặc worker crash | Không rõ bên ngoài đã thực hiện hay chưa; retry dễ gây **duplicate effect** | Khóa idempotency được hệ thống đích tôn trọng; reconciliation |
| **W10 — Retry/DLX/DLQ bị cấu hình sai** | Message hết TTL, reject, DLX thiếu binding hoặc DLQ bị xóa | Không còn đường xử lý hữu ích, hoặc vòng lặp retry | Retry budget, terminal DLQ, giám sát route và chính sách broker |

**Điểm quan trọng:** “Mất” và “trùng” thường là **hai mặt của cùng một khoảng không chắc chắn**. Ví dụ khi publisher không nhận được confirm, nếu nó **không gửi lại** thì có nguy cơ mất; nếu nó **gửi lại** thì có nguy cơ trùng. Giải pháp đáng tin cậy không cố đoán broker đã làm gì, mà thiết kế sao cho **có thể thử lại** và **xử lý trùng an toàn**.

## 4. Cửa sổ W1: ghi DB rồi mới publish

Đây là lỗi phổ biến trong kiến trúc event-driven:

~~~java
@Transactional
public void markPaid(String orderId) {
    orderRepository.markPaid(orderId);
}

public void handlePayment(String orderId) {
    markPaid(orderId);  // DB commit xong
    rabbitTemplate.convertAndSend(
            "orders.events", "order.paid", new OrderPaid(orderId));
}
~~~

Nếu ứng dụng dừng **giữa hai lệnh**, database đã lưu `PAID` nhưng không có `OrderPaid`. Một cơ chế retry cho RabbitMQ sau này không thể khôi phục một event **chưa từng được ghi lại ở nơi bền vững**.

Đổi thứ tự — publish trước rồi commit DB — cũng không giải quyết được: có thể phát event rồi DB rollback, khiến consumer xử lý một thay đổi chưa từng thành công ở nguồn.

### 4.1. Transactional outbox

Giải pháp phổ biến là ghi **dữ liệu nghiệp vụ** và **một bản ghi outbox** trong **cùng giao dịch database**:

~~~mermaid
sequenceDiagram
    participant A as Order service
    participant DB as Order database
    participant R as Outbox relay
    participant B as RabbitMQ

    A->>DB: BEGIN
    A->>DB: UPDATE orders SET status=PAID
    A->>DB: INSERT outbox_event(eventId, payload, NEW)
    A->>DB: COMMIT
    Note over A,DB: Hoặc cả hai commit, hoặc cả hai rollback
    R->>DB: Đọc outbox NEW
    R->>B: Publish eventId=E42
    B-->>R: Publisher confirm (+ không có return)
    R->>DB: Đánh dấu PUBLISHED
~~~

Lợi ích: nếu Order DB đã commit, một bản ghi outbox tương ứng vẫn tồn tại để relay có thể phát lại. Outbox **không loại bỏ hoàn toàn duplicate**: relay có thể publish thành công nhưng crash trước khi cập nhật `PUBLISHED`. Khi khởi động lại, nó sẽ publish cùng event thêm lần nữa.

### 4.2. Ví dụ bảng dữ liệu và ranh giới giao dịch

Ví dụ với PostgreSQL:

~~~sql
CREATE TABLE orders (
    order_id      VARCHAR(64) PRIMARY KEY,
    status        VARCHAR(32) NOT NULL,
    version       BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE outbox_events (
    event_id      UUID PRIMARY KEY,
    aggregate_id  VARCHAR(64) NOT NULL,
    event_type    VARCHAR(80) NOT NULL,
    payload       JSONB NOT NULL,
    state         VARCHAR(16) NOT NULL DEFAULT 'NEW',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at  TIMESTAMPTZ
);

CREATE INDEX outbox_events_state_created_idx
    ON outbox_events(state, created_at);
~~~

Ví dụ pseudo-code Java thể hiện ranh giới transactional; `orderRepository` và `outboxRepository` phải dùng **cùng database/transaction manager**:

~~~java
public record OrderPaid(
        java.util.UUID eventId,
        String orderId,
        long orderVersion) {}

@Service
public class OrderPaymentService {
    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;

    // Constructor injection được lược bớt cho gọn.

    @Transactional
    public void markPaid(String orderId) {
        long version = orderRepository.markPaidAndIncrementVersion(orderId);
        var event = new OrderPaid(
                java.util.UUID.randomUUID(), orderId, version);

        // save() ghi JSON payload, eventId và state=NEW
        // vào cùng DB transaction với UPDATE orders.
        outboxRepository.save(event);
    }
}
~~~

Việc dùng `@Transactional` có ý nghĩa khi cả hai thao tác thực sự nằm trong cùng transaction. Hai repository trỏ tới hai database khác nhau sẽ không tự động trở thành một giao dịch nguyên tử. Bản ghi outbox cần chứa **eventId ổn định** để mọi lần publish lại sử dụng **cùng định danh**.

### 4.3. Relay cần chấp nhận phát lại

Outbox relay có thể dùng polling hoặc change-data-capture. Với polling, nhiều instance cần cơ chế claim/lease và khóa phù hợp (ví dụ `FOR UPDATE SKIP LOCKED` trong PostgreSQL) để không đồng thời lấy cùng một công việc. Nhưng ngay cả khi claim tốt, cửa sổ **publish thành công → đánh dấu PUBLISHED** vẫn có thể tạo bản sao.

Một quy tắc đơn giản:

1. Đọc hoặc claim bản ghi `NEW`.
2. Publish bằng **eventId gốc**.
3. Đợi publisher confirm và kiểm tra return/routing.
4. Chỉ sau khi kết quả publish phù hợp mới cập nhật outbox thành `PUBLISHED`.
5. Nếu timeout, nack, return hoặc relay crash: giữ khả năng retry. Không tự suy diễn “chắc chắn chưa gửi”.

Outbox cần dọn dẹp bản ghi đã publish sau một thời gian lưu giữ, cảnh báo bản ghi tồn đọng và có cơ chế giải phóng lease khi worker chết.

## 5. Cửa sổ W2–W4: publish, xác nhận và định tuyến

### 5.1. `convertAndSend()` thành công có nghĩa gì?

Một lời gọi `RabbitTemplate.convertAndSend()` không ném exception **không tự chứng minh** broker đã lưu message, route được vào queue hoặc consumer đã xử lý. Lệnh có thể mới được đưa đến client library hoặc kênh mạng.

Để biết kết quả publish ở mức broker, bật **publisher confirms**. Để biết một message được publish vào exchange nhưng **không route tới queue** trong trường hợp cần return, bật **publisher returns** và gửi với cờ `mandatory`.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

- `publisher-confirm-type: correlated` giúp ghép kết quả confirm với mỗi lần publish có `CorrelationData`.
- `publisher-returns: true` cho phép ứng dụng nhận thông tin message không route được khi điều kiện return áp dụng.
- `template.mandatory: true` yêu cầu broker **return** những message không thể route vào queue theo cơ chế mandatory; nếu chỉ bật returns nhưng không dùng mandatory, ứng dụng có thể bỏ sót trường hợp không có binding.

Một publish vào **exchange tồn tại nhưng không có binding phù hợp** có thể nhận **publisher confirm ACK** và đồng thời bị **return** vì không route được. Do đó **confirm ACK không thay cho kiểm tra returned message**.

Nếu broker có alternate exchange và message được định tuyến qua tuyến thay thế, việc không thấy return cũng không tự chứng minh message đã vào **queue nghiệp vụ mong muốn**. Hãy xác minh topology và giám sát queue dự kiến.

### 5.2. Ví dụ publisher có xác nhận tương ứng với event

Đoạn mã dưới đây minh họa một lần publish từ bản ghi outbox; các lớp `OutboxRow` và `OutboxRepository` là tầng lưu trữ do ứng dụng triển khai. `RabbitTemplate` cần JSON message converter nếu muốn gửi DTO dạng JSON.

~~~java
import java.util.concurrent.TimeUnit;

import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public class ConfirmedOutboxPublisher {
    private final RabbitTemplate rabbitTemplate;
    private final OutboxRepository outboxRepository;

    public void publishOnce(OutboxRow row, OrderPaid event)
            throws Exception {

        var correlation = new CorrelationData(
                event.eventId().toString());

        rabbitTemplate.convertAndSend(
                "orders.events",
                "order.paid",
                event,
                message -> {
                    var props = message.getMessageProperties();
                    props.setMessageId(event.eventId().toString());
                    props.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                    return message;
                },
                correlation);

        // Timeout hoặc exception => kết quả không chắc chắn;
        // GIỮ event trong outbox để retry an toàn.
        var confirm = correlation.getFuture()
                .get(5, TimeUnit.SECONDS);

        if (!confirm.isAck()) {
            throw new IllegalStateException(
                    "Broker NACK: " + confirm.getReason());
        }

        if (correlation.getReturned() != null) {
            throw new IllegalStateException(
                    "Message đã publish nhưng không route được");
        }

        // Không thể thực hiện atomically cùng broker confirm.
        // Nếu crash trước/during câu lệnh này, event có thể phát lại.
        outboxRepository.markPublished(row.eventId());
    }
}
~~~

Đây là **mẫu minh họa luồng xử lý**, chưa phải lớp biên dịch độc lập: cần khai báo constructor, repository, DTO, topology, converter và xử lý retry. Trong ứng dụng tải cao, thay vì block một thread chờ từng confirm, có thể xử lý confirm bất đồng bộ và theo dõi kết quả theo `CorrelationData`; vẫn phải giữ quy tắc **chỉ mark PUBLISHED sau khi có bằng chứng publish hợp lệ**.

Lưu ý:

- `CorrelationData.id` phục vụ đối chiếu confirm phía publisher; `messageId` và `eventId` dùng để nhận diện message/nghiệp vụ. Chúng có thể trùng giá trị nhưng **không phải cùng một cơ chế**.
- `confirm.getFuture().get(...)` timeout nghĩa là **không biết kết quả cuối cùng**; không kết luận broker đã từ chối.
- Với RabbitMQ và Spring AMQP thông thường, thông tin return tương ứng được cập nhật trước khi confirm hoàn tất. Cần cấu hình `mandatory`, publisher returns và kiểm thử bằng cách bỏ binding trong môi trường thử nghiệm.
- Xác nhận broker chấp nhận message **không bảo đảm** sau đó consumer sẽ ACK, và không thay cho kiểm soát tính bền vững của queue/message.

### 5.3. Durable queue và persistent message

Một cấu hình tối thiểu cho message nghiệp vụ cần xem xét:

~~~java
@Bean
DirectExchange ordersEventsExchange() {
    return new DirectExchange("orders.events", true, false);
}

@Bean
Queue ordersPaidQueue() {
    return QueueBuilder.durable("orders.paid.queue")
            .deadLetterExchange("orders.dlx")
            .deadLetterRoutingKey("orders.paid.failed")
            .build();
}

@Bean
Binding ordersPaidBinding(
        Queue ordersPaidQueue,
        DirectExchange ordersEventsExchange) {
    return BindingBuilder.bind(ordersPaidQueue)
            .to(ordersEventsExchange)
            .with("order.paid");
}
~~~

- Exchange và queue **durable** tồn tại qua restart broker theo chính sách của loại tài nguyên.
- Message nên được publish với delivery mode **persistent** nếu yêu cầu lưu bền vững.
- Publisher confirms giúp producer biết broker đã xử lý publish theo bảo đảm của broker/loại queue.
- Cần lựa chọn loại queue, replication, chính sách dữ liệu và cách vận hành phù hợp mục tiêu khôi phục; durable + persistent **không thay thế backup hay thiết kế chịu sự cố hạ tầng**.

Message còn có thể bị loại theo TTL, giới hạn queue, purge, xóa queue, consumer reject hoặc dead-letter cấu hình sai. “Đã vào queue” chưa đồng nghĩa “chắc chắn sẽ được nghiệp vụ xử lý”; cần nhìn cả chính sách giữ và xử lý message.

## 6. Cửa sổ W6–W8: ACK trước hay sau khi commit?

RabbitMQ sẽ có thể giao lại một message khi consumer chết hoặc channel đóng **trước khi broker nhận ACK tương ứng**, miễn message vẫn còn trong queue và cơ chế giao nhận cho phép. Nhận lại không có nghĩa event mới.

### 6.1. Thứ tự sai: ACK sớm rồi mới ghi DB

~~~text
Consumer nhận E42
    ↓
basicAck(E42)                 ← broker có thể loại delivery
    ↓
UPDATE inventory              ← DB lỗi / tiến trình crash
    ↓
Không còn E42 để retry       ← mất tác dụng nghiệp vụ
~~~

Điều này dễ xảy ra khi dùng **RabbitMQ auto-ack** hoặc manual ACK không đúng vị trí. Phân biệt các acknowledgment mode của Spring AMQP:

| Mode | Ý nghĩa |
| --- | --- |
| `AcknowledgeMode.NONE` | Broker tự coi delivery đã được ACK khi giao; ứng dụng không thể dựa vào việc chưa xử lý xong để nhận lại |
| `AcknowledgeMode.AUTO` | **Spring listener container** gửi ACK khi listener xử lý thành công; lỗi được container/error handler xử lý |
| `AcknowledgeMode.MANUAL` | Code ứng dụng tự gọi `basicAck`, `basicNack` hoặc `basicReject` |

**Dễ nhầm:** `AcknowledgeMode.AUTO` của Spring AMQP **không giống** `autoAck=true` trong RabbitMQ Java client. AUTO vẫn cho container quyết định ACK theo kết quả xử lý listener.

### 6.2. Thứ tự an toàn hơn: commit DB rồi để container ACK

~~~text
Consumer nhận E42
    ↓
BEGIN DB transaction
    ↓
Áp dụng nghiệp vụ + ghi khóa đã xử lý
    ↓
COMMIT DB
    ↓
Listener trả về thành công
    ↓
Container gửi consumer ACK
~~~

Nếu tiến trình chết **sau DB commit nhưng trước ACK**, message có thể được giao lại. Vì vậy chỉ đổi thứ tự ACK vẫn **chưa đủ**; DB transaction phải có cơ chế **chặn xử lý trùng**.

Không gọi `basicAck()` ở giữa một phương thức `@Transactional` rồi giả định database đã commit: ở nhiều cấu trúc proxy, commit chỉ xảy ra **sau khi phương thức kết thúc**. Cách đơn giản trong ví dụ là listener gọi một service giao dịch, đợi service return (DB transaction đã commit), sau đó mới return để container ACK.

## 7. Inbox và idempotency: biến duplicate delivery thành kết quả an toàn

Để xử lý trùng, mỗi event nghiệp vụ cần **`eventId` ổn định** từ khi tạo ở outbox cho đến mọi lần retry, republish và redelivery. Không tạo UUID mới mỗi lần relay gửi lại cùng event. Không dùng `deliveryTag` làm định danh nghiệp vụ: delivery tag chỉ có ý nghĩa trên channel RabbitMQ.

### 7.1. Hai bảng được cập nhật trong cùng giao dịch

Ví dụ PostgreSQL cho consumer Inventory hoặc projection:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      UUID NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE order_projection (
    order_id VARCHAR(64) PRIMARY KEY,
    status   VARCHAR(32) NOT NULL,
    version  BIGINT NOT NULL
);
~~~

Khóa chính `(consumer_name, event_id)` quan trọng vì hai consumer nghiệp vụ **khác nhau** có thể đều cần xử lý cùng một event. Việc một consumer xử lý rồi không có nghĩa consumer khác được bỏ qua.

### 7.2. Xử lý trùng bằng unique constraint và transaction

Giả sử client nhận JSON DTO dạng:

~~~java
public record OrderPaid(
        java.util.UUID eventId,
        String orderId,
        long orderVersion) {}
~~~

Listener gọi một service có transaction:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPaidListener {

    private final OrderProjectionService service;

    public OrderPaidListener(OrderProjectionService service) {
        this.service = service;
    }

    @RabbitListener(
            queues = "orders.paid.queue",
            containerFactory = "reliableListenerFactory")
    public void on(OrderPaid event) {
        service.applyOnce(event);
        // Chỉ return sau khi service đã commit thành công.
        // Container AUTO ACK sau khi listener xử lý thành công.
    }
}
~~~

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyOnce(OrderPaid event) {
        int inserted = jdbc.update("""
                INSERT INTO processed_events(consumer_name, event_id)
                VALUES (?, ?)
                ON CONFLICT DO NOTHING
                """,
                "order-projection",
                event.eventId());

        if (inserted == 0) {
            // Consumer này đã commit event này trước đó.
            // Không áp dụng lại side effect.
            return;
        }

        jdbc.update("""
                INSERT INTO order_projection(order_id, status, version)
                VALUES (?, 'PAID', ?)
                ON CONFLICT (order_id) DO UPDATE
                  SET status = EXCLUDED.status,
                      version = EXCLUDED.version
                WHERE order_projection.version < EXCLUDED.version
                """,
                event.orderId(),
                event.orderVersion());
    }
}
~~~

Ví dụ này giả định cả hai bảng thuộc **cùng PostgreSQL database** và `@Transactional` sử dụng transaction manager tương ứng.

**Vì sao cách này an toàn trước duplicate?**

1. Consumer A xử lý event `E42`, insert `processed_events(E42)` và cập nhật projection trong **cùng transaction**.
2. Nếu commit thành công nhưng ACK thất lạc, RabbitMQ có thể giao lại `E42`.
3. Consumer B (hoặc A sau restart) cố insert cùng khóa; `ON CONFLICT DO NOTHING` trả số dòng chèn bằng 0 nên không áp dụng hiệu ứng lần hai.
4. Nếu transaction ở bước 1 rollback, cả marker và cập nhật projection đều rollback; lần redelivery sau vẫn có thể xử lý event.

**Không dùng mẫu** “`SELECT` xem đã có chưa, nếu chưa thì `INSERT`” **mà không có ràng buộc duy nhất**. Hai consumer chạy song song có thể cùng đọc “chưa có” rồi cùng áp dụng side effect. Unique constraint là lớp bảo vệ cần thiết cho race condition.

Cột `version` xử lý **một vấn đề khác**: event có thể đến **sai thứ tự**. Event version 6 đến trước version 5 không nên bị event cũ ghi đè. Idempotency theo `eventId` chỉ ngăn **cùng event** chạy hai lần, không tự giải quyết hai event **khác nhau** đến ngược thứ tự.

### 7.3. Nếu side effect nằm bên ngoài database thì sao?

Ví dụ listener ghi `processed_events` rồi gọi cổng thanh toán bên ngoài. Hai thao tác này **không tự nằm trong một database transaction nguyên tử**:

- Gọi API thành công, tiến trình crash trước khi ghi marker: retry có thể gọi API lần nữa.
- Ghi marker thành công, tiến trình crash trước khi gọi API: retry thấy marker và bỏ qua, làm mất side effect.

Để khắc phục, cần phối hợp **idempotency key được hệ thống đích hỗ trợ**, trạng thái tác vụ bền vững (outbox/workflow state machine), và cơ chế truy vấn/đối soát kết quả khi timeout. Một bảng inbox đơn thuần **không thể bảo đảm exactly-once** cho side effect ngoài DB không hỗ trợ idempotency.

## 8. Cấu hình listener ACK, retry và DLQ có điểm dừng

Ví dụ ở phần 7 dùng `containerFactory = "reliableListenerFactory"`. Với Spring AMQP, có thể cấu hình factory theo hướng: listener chỉ được coi thành công sau khi xử lý xong; lỗi được thử lại hữu hạn; nếu vẫn lỗi thì chuyển message tới terminal DLQ.

~~~java
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.config.RetryInterceptorBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.retry.RejectAndDontRequeueRecoverer;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ReliableListenerConfig {

    @Bean
    SimpleRabbitListenerContainerFactory reliableListenerFactory(
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter converter) {

        var factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(converter);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);

        factory.setAdviceChain(
                RetryInterceptorBuilder.stateless()
                        .maxAttempts(3)        // gồm lần đầu
                        .backOffOptions(500, 2.0, 2_000)
                        .recoverer(new RejectAndDontRequeueRecoverer())
                        .build());

        factory.setDefaultRequeueRejected(false);
        return factory;
    }
}
~~~

Queue nguồn cần cấu hình `x-dead-letter-exchange`, `x-dead-letter-routing-key` và binding tới một **terminal DLQ**:

~~~java
@Bean
DirectExchange ordersDlx() {
    return new DirectExchange("orders.dlx", true, false);
}

@Bean
Queue ordersPaidDlq() {
    // Không định tuyến DLX ngược về queue nguồn.
    return QueueBuilder.durable("orders.paid.dlq").build();
}

@Bean
Binding ordersPaidDlqBinding(
        Queue ordersPaidDlq,
        DirectExchange ordersDlx) {
    return BindingBuilder.bind(ordersPaidDlq)
            .to(ordersDlx)
            .with("orders.paid.failed");
}
~~~

Lưu ý về retry:

- `maxAttempts(3)` gồm lần xử lý đầu và các lần thử lại **trong một chu kỳ listener**. Không thay thế bộ đếm retry bền vững xuyên nhiều lần consumer crash/requeue.
- Không nên retry mãi lỗi **không thể phục hồi** như dữ liệu sai schema hoặc thiếu trường bắt buộc. Có thể đưa sớm vào DLQ để điều tra.
- Với lỗi tạm thời kéo dài (DB outage vài phút), retry liên tục ngay trong listener có thể làm cạn thread. Cần chính sách backoff/delay queue hoặc lịch retry có giới hạn.
- **DLQ không phải bảo đảm tuyệt đối** nếu DLX/binding/queue đích bị sai hoặc gặp sự cố. Dead-letter từ classic queue có thể có cửa sổ mất dữ liệu; quorum queue hỗ trợ cơ chế dead-letter *at-least-once* trong cấu hình/điều kiện tương ứng. Kiểm tra khả năng này trên phiên bản RabbitMQ triển khai và giám sát số message thực sự đến DLQ.
- Broker xử lý ACK theo **delivery/channel**, còn idempotency xử lý theo **event nghiệp vụ**. Hai lớp đều cần thiết.

Trong ví dụ, nếu database transaction thất bại thì listener ném exception; container không ACK thành công và đưa message qua retry/reject. Khi transaction đã commit, listener return; AUTO ACK được gửi. Trường hợp crash đúng giữa commit và ACK sẽ tạo redelivery, nhưng unique constraint của `processed_events` giúp không ghi trùng.

## 9. Ma trận bảo đảm: chỉ riêng cấu hình nào là chưa đủ?

| Cơ chế | Giải quyết tốt vấn đề | Chưa giải quyết |
| --- | --- | --- |
| Durable queue + persistent message | Giảm rủi ro mất message đã được broker tiếp nhận | Event mất trước publish; lỗi routing; consumer side effect |
| Publisher confirms | Quan sát broker đã xác nhận publish hay chưa | Message có tới đúng queue không (nếu không kiểm tra return); consumer có xử lý không |
| Mandatory + publisher returns | Phát hiện message không route được trong các trường hợp return | Consumer chết sau nhận; nội dung message hợp lệ hay không |
| Transactional outbox | DB nguồn commit nhưng event chưa publish | Relay phát lại tạo duplicate; idempotency consumer |
| Consumer ACK sau DB commit | Tránh ACK sớm khi kết quả nghiệp vụ chưa lưu | Crash sau commit trước ACK gây redelivery |
| Inbox + unique constraint + cùng DB transaction | Một event không áp dụng side effect trong DB quá một lần | Side effect hệ thống ngoài; event khác đến sai thứ tự |
| Version/sequence guard | Event cũ không ghi đè trạng thái mới | Duplicate effect trong dịch vụ ngoài nếu không có idempotency |
| Retry có giới hạn + DLQ | Message lỗi có đường điều tra/replay | DLQ sai tuyến; xử lý thất bại vĩnh viễn nếu không vận hành |
| Monitoring + reconciliation | Phát hiện event mắc kẹt, mất đồng bộ và khắc phục | Không tự tạo nguyên tử xuyên nhiều hệ thống |

Vì vậy, phát biểu chính xác hơn “RabbitMQ bảo đảm xử lý đúng một lần” là:

> Hệ thống có thể hướng tới **at-least-once delivery** cho một luồng cụ thể, đồng thời thiết kế **idempotent business effects** ở nơi lưu kết quả. Bảo đảm này có các giả định về cơ chế lưu bền vững, retention, routing, retry và giới hạn lỗi được chấp nhận.

## 10. Quan sát toàn bộ đường đi của một event

Một event nên có **định danh xuyên suốt** từ lúc tạo trong outbox đến log consumer:

~~~json
{
  "eventId": "e4f84f2a-68a1-4f8c-8a65-b4d7f5d6c073",
  "eventType": "OrderPaid",
  "orderId": "ORD-1024",
  "orderVersion": 7,
  "occurredAt": "2026-11-26T02:00:00Z"
}
~~~

Các trường này là **ví dụ dữ liệu**, không phải những header broker tự tạo. `eventId` nên là ID ổn định trong payload, đồng thời có thể đặt vào `messageId` để tiện truy vết. `orderVersion` giúp xử lý thứ tự. Với các hệ thống có nhiều consumer nghiệp vụ, mỗi consumer có namespace riêng cho khóa xử lý.

Bộ chỉ số có ích:

| Chỉ số | Tình huống phát hiện |
| --- | --- |
| `outbox_pending_total` và tuổi outbox lớn nhất | Sự kiện DB đã commit nhưng chưa được publish |
| `publish_confirm_nack_total`, `publish_confirm_timeout_total` | Broker từ chối hoặc kết quả publish chưa rõ |
| `publisher_return_total` theo exchange/routing key | Publish không route được, binding sai |
| `queue_ready`, `queue_unacked`, tốc độ publish/deliver/ACK | Backlog, consumer chậm, message đang xử lý |
| `redelivered_total` hoặc tỷ lệ redelivery | Crash, ACK trễ, vòng retry hoặc consumer instability |
| `duplicate_suppressed_total` theo consumer | Inbox đã ngăn event trùng |
| `processing_failed_total` theo loại lỗi | Lỗi tạm thời và poison message |
| `dlq_ready` và tuổi DLQ lớn nhất | Message lỗi chưa được điều tra/replay |
| `projection_lag` hoặc sai lệch giữa dữ liệu nguồn/đích | Phát hiện event thiếu bằng đối soát nghiệp vụ |

**Không chỉ quan sát độ sâu queue.** Queue rỗng có thể có nghĩa là consumer đã xử lý xong, nhưng cũng có thể do publish không route được hoặc consumer ACK sớm. Muốn xác định event cụ thể, phải có trace của **outbox → publish confirm/return → queue → handler → DB commit → ACK**.

Một đoạn log hữu ích:

~~~text
eventId=E42 orderId=ORD-1024 stage=outbox_created
eventId=E42 stage=publish_confirmed exchange=orders.events key=order.paid
eventId=E42 stage=consumer_received queue=orders.paid.queue redelivered=false
eventId=E42 stage=projection_committed consumer=order-projection
eventId=E42 stage=ack_requested
~~~

Log ứng dụng không có nghĩa broker chắc chắn đã nhận ACK; tên event/log nên phản ánh **điều vừa thực sự xảy ra**. Không ghi toàn bộ payload chứa dữ liệu nhạy cảm. Khi có nghi ngờ mất event, hệ thống nên đối soát trạng thái nghiệp vụ (ví dụ order đã PAID nhưng projection chưa thấy version tương ứng), thay vì chỉ dựa vào log.

## 11. Thử nghiệm lỗi tại đúng cửa sổ

Một thiết kế tin cậy cần được kiểm chứng bằng *failure injection*, không chỉ bằng happy path. Trên môi trường thử nghiệm, chọn mỗi lần **một điểm gây lỗi**, quan sát eventId và trạng thái DB/broker sau khôi phục.

### Kịch bản A — crash sau DB commit, trước publish

1. Gọi nghiệp vụ ghi Order và outbox trong một transaction.
2. Dừng relay trước khi nó lấy bản ghi.
3. Xác minh Order đã commit và outbox còn trạng thái `NEW`.
4. Khởi động lại relay; event phải được publish, consumer xử lý được.

**Kỳ vọng:** không mất event do W1.

### Kịch bản B — publish thành công, relay crash trước khi mark published

1. Publish event `E42` qua RabbitMQ và quan sát confirm hợp lệ.
2. Cố ý dừng relay trước khi cập nhật `PUBLISHED`.
3. Khởi động relay để publish `E42` lần thứ hai.
4. Xác minh consumer có thể nhận bản sao nhưng DB side effect chỉ áp dụng một lần.

**Kỳ vọng:** có thể duplicate delivery, **không duplicate effect**.

### Kịch bản C — publish vào exchange không có binding

1. Trên môi trường thử, tạm bỏ binding phù hợp với `order.paid`.
2. Gửi message với `mandatory=true` và bật returns.
3. Xác minh xuất hiện returned message hoặc một tín hiệu routing failure phù hợp; relay **không** đánh dấu event là `PUBLISHED`.
4. Khôi phục binding rồi retry.

**Kỳ vọng:** confirm ACK (nếu có) không che mất lỗi routing.

### Kịch bản D — consumer crash trước DB commit

1. Tiếp nhận `E42`.
2. Gây exception/rollback trong transaction xử lý.
3. Đảm bảo không có marker inbox hoặc projection bị commit nửa chừng.
4. Giao lại/retry; event vẫn có thể được xử lý thành công.

**Kỳ vọng:** không ACK như thành công cho một transaction bị rollback.

### Kịch bản E — DB commit thành công, ACK chưa tới broker

1. Để service xử lý và commit `E42`.
2. Dừng consumer trước khi container hoàn tất ACK, hoặc mô phỏng redelivery tương đương.
3. Khởi động lại.
4. Xác minh `processed_events` trả duplicate và projection không được áp dụng thêm lần nữa.

**Kỳ vọng:** event có thể redeliver nhưng side effect idempotent.

### Kịch bản F — hai consumer nhận bản sao đồng thời

1. Phát hai message có cùng `eventId`.
2. Cho hai consumer xử lý song song.
3. Kiểm tra unique constraint trong DB.
4. Xác minh đúng một transaction áp dụng side effect, transaction còn lại bỏ qua hoặc chờ rồi nhận kết quả conflict.

**Kỳ vọng:** không tồn tại race “cả hai đều thấy chưa xử lý”.

### Kịch bản G — event đến sai thứ tự

1. Publish version 7 trước version 6 cho cùng `orderId`.
2. Consumer xử lý cả hai.
3. Xác minh projection giữ version 7.

**Kỳ vọng:** idempotency kết hợp version guard tránh cả xử lý trùng lẫn ghi đè bởi sự kiện cũ.

### Kịch bản H — DLQ và replay

1. Publish một message lỗi có thể tái hiện.
2. Cho retry hết ngân sách.
3. Xác minh message đến đúng terminal DLQ qua exchange, routing key và binding.
4. Sau khi sửa nguyên nhân, replay có giới hạn với **eventId cũ** và theo dõi duplicate suppression.

**Kỳ vọng:** không có vòng retry vô hạn và không mất khả năng điều tra.

## 12. Quy trình điều tra khi một event bị “mất” hoặc “chạy hai lần”

Thực hiện lần lượt các câu hỏi dưới đây, luôn dùng **eventId**:

1. **Có bản ghi nghiệp vụ đã commit không?** Nếu có nhưng không có outbox, xem lại phạm vi transaction hoặc code tạo sự kiện.
2. **Outbox đang ở trạng thái gì?** `NEW` tồn lâu có thể do relay hỏng; `PUBLISHED` chỉ phản ánh kết quả publish đã xác minh theo chính sách.
3. **Broker đã confirm hay chưa?** Nếu timeout, trạng thái là **unknown**, cần phép thử lại an toàn.
4. **Có publisher return không?** Kiểm tra exchange, routing key, binding, vhost, alternate exchange và quyền truy cập.
5. **Message tới đúng queue không?** Đọc số liệu queue, DLQ, delivery/redelivery; kiểm tra TTL, max length và routing dead-letter.
6. **Listener có bắt đầu xử lý không?** Đối chiếu consumer log theo eventId; phân biệt không được giao với được giao nhưng lỗi.
7. **DB đích đã commit chưa?** Kiểm tra cả marker dedup và business row trong cùng transaction. Nếu marker tồn tại nhưng side effect thiếu, xem lại transaction boundary hoặc tác động bên ngoài DB.
8. **ACK có thể đã thất lạc không?** Nếu message redeliver sau commit, đây là tình huống idempotency phải xử lý được.
9. **Dữ liệu có bị cập nhật sai thứ tự không?** So sánh aggregate version, timestamp nghiệp vụ và quy tắc áp dụng event.
10. **Có cần đối soát/replay không?** Chỉ replay từ nguồn bền vững với cùng eventId và kiểm soát tốc độ; đừng tăng số bản sao khi chưa sửa nguyên nhân gốc.

Một phương pháp điều tra tốt phải phân biệt được **chưa publish**, **đã publish nhưng không route**, **đã vào queue nhưng chưa xử lý**, **đã xử lý nhưng chưa ACK**, và **đã xử lý trùng nhưng được chặn**. Chỉ nhìn trạng thái ACK hoặc một exception đơn lẻ thường không đủ.

## 13. Checklist thiết kế trước production

- [ ] Thay đổi nghiệp vụ và outbox ghi **cùng một DB transaction**, hoặc có cơ chế tương đương đã được xác minh.
- [ ] Mỗi event có `eventId` ổn định qua mọi lần retry, relay và replay.
- [ ] Exchange, queue, binding, routing key đã kiểm thử; queue và message có cấu hình durability thích hợp.
- [ ] Publisher confirms và returns được bật phù hợp; mandatory routing và alternate exchange được hiểu rõ.
- [ ] Relay giữ trạng thái `unknown` khi timeout và chỉ mark published sau xác nhận; nhiều relay không claim trùng vô kiểm soát.
- [ ] Listener dùng acknowledgment mode phù hợp và chỉ thành công khi DB transaction đã commit.
- [ ] Consumer có marker inbox với unique constraint, nằm trong **cùng transaction** với cập nhật nghiệp vụ.
- [ ] Có version/sequence guard nếu nhiều event của cùng aggregate có thể đến sai thứ tự.
- [ ] Side effect ngoài database sử dụng idempotency key thực sự được bên nhận tôn trọng và có cơ chế reconciliation.
- [ ] Retry có giới hạn, lỗi vĩnh viễn có terminal DLQ, đường dead-letter đã thử nghiệm.
- [ ] Có chỉ số độ tuổi outbox, timeout/return, redelivery, dedup, DLQ và độ trễ đồng bộ dữ liệu.
- [ ] Đã thử các cửa sổ crash trước/sau publish, trước/sau DB commit và trước/sau ACK.

## 14. Tổng kết

Trong hệ thống **SPRING_AMQP**, hai rủi ro thường đi cùng nhau: **mất message khi một bước đã commit nhưng bước kế tiếp chưa kịp thực hiện**, và **xử lý trùng khi bước đã thành công nhưng xác nhận thành công chưa kịp đến bên yêu cầu**.

Mẫu kiến trúc đáng tin cậy là **transactional outbox → publish với confirms/returns → RabbitMQ topology bền vững → listener xử lý bằng DB transaction và inbox/idempotency → ACK sau khi commit → retry/DLQ có giới hạn → giám sát và đối soát**. Không có giả định “message chỉ đến một lần”; thay vào đó, mọi ranh giới không chắc chắn được xử lý bằng **lưu bền vững, thử lại an toàn và chống tác dụng phụ trùng lặp**.

Bài học quan trọng nhất: phải xác định **chính xác cửa sổ lỗi và kết quả có thể xảy ra ở từng ranh giới**, rồi kiểm chứng bằng việc chủ động gây crash, timeout, mất binding và redelivery. Khi đó độ tin cậy đầu cuối không còn là lời khẳng định chung về RabbitMQ, mà là một thuộc tính có thể giải thích, đo lường và kiểm thử trên luồng nghiệp vụ thực tế.
