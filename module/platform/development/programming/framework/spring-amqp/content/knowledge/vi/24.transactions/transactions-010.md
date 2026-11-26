# Chi phí hiệu năng và lựa chọn thay thế bằng outbox

Một ứng dụng dùng **Spring AMQP** thường phải làm hai việc liên quan: lưu dữ liệu nghiệp vụ trong cơ sở dữ liệu và phát sự kiện lên **RabbitMQ** bằng `RabbitTemplate` để các `@RabbitListener` khác xử lý bất đồng bộ. Ví dụ, khi đơn hàng được tạo thành công, hệ thống ghi đơn hàng vào database và phát `OrderCreated` để dịch vụ hóa đơn, kho và email cùng nhận thông tin.

Nhìn qua, bật transaction cho cả database và RabbitMQ có vẻ đủ để bảo đảm *hoặc cả hai cùng thành công, hoặc cả hai cùng thất bại*. Nhưng **RabbitMQ channel transaction không phải giao dịch phân tán XA với database**, còn việc commit từng message có chi phí đáng kể. **Transactional outbox** là một thiết kế thay thế khi mục tiêu thực sự là: *không được làm mất sự kiện tương ứng với dữ liệu nghiệp vụ đã commit*.

Bài này nằm trong chương **Giao dịch** của module **SPRING_AMQP**. Ta sẽ phân biệt chi phí của transaction, publisher confirms, đồng bộ transaction ở Spring, sau đó triển khai outbox với SQL, `@Transactional`, `RabbitTemplate`, confirm/return, retry, idempotency và quan sát vận hành. Các ví dụ tập trung vào sự an toàn của hệ thống khi có lỗi, không chỉ vào việc code chạy ở trường hợp thành công.

## 1. Ba bảo đảm khác nhau thường bị nhầm

Trước khi chọn cơ chế, phải tách ba câu hỏi:

1. **Đơn vị RabbitMQ đã chấp nhận publish chưa?** Broker có thể xác nhận publish bằng **publisher confirms**. Với message không định tuyến được, cần kết hợp `mandatory` và **publisher returns**.
2. **Thay đổi trong database đã commit chưa?** Database transaction bảo đảm tính nguyên tử của các thao tác SQL trong *cùng* database và transaction.
3. **Consumer đã thực hiện tác dụng nghiệp vụ chưa?** Publisher confirm không chứng minh consumer đã nhận, xử lý hoặc ACK message. Consumer cần logic xử lý riêng, thông thường với redelivery và idempotency.

Ví dụ:

~~~text
1. DB commit: order #123 đã được tạo.
2. RabbitMQ chưa nhận OrderCreated(#123).
3. API trả thành công cho khách hàng.

=> Trạng thái DB hợp lệ, nhưng các dịch vụ downstream không hề biết sự kiện.
~~~

Ngược lại, nếu RabbitMQ đã nhận sự kiện nhưng DB transaction bị rollback, downstream có thể nhận thông báo về đơn hàng không tồn tại. Hai hướng lỗi này là nguồn gốc của bài toán **dual write**.

## 2. RabbitMQ channel transaction tốn chi phí gì?

AMQP 0-9-1 hỗ trợ lệnh `tx.select`, `tx.commit` và `tx.rollback` trên **channel**. Trong Spring AMQP, `RabbitTemplate` có thuộc tính `channelTransacted` để sử dụng transaction trên channel khi gửi message; listener container cũng có thể được cấu hình channel transaction.

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class RabbitTransactionConfiguration {
    @Bean
    RabbitTemplate transactedRabbitTemplate(ConnectionFactory connectionFactory) {
        RabbitTemplate template = new RabbitTemplate(connectionFactory);
        template.setChannelTransacted(true);
        return template;
    }
}
~~~

Nếu không có Spring transaction bao ngoài, `RabbitTemplate` có thể tạo transaction AMQP cục bộ cho thao tác của nó. Nếu có một transaction Spring đang hoạt động, commit hoặc rollback trên AMQP channel có thể được đồng bộ với transaction đó. **Sự đồng bộ này không biến hai tài nguyên thành một giao dịch nguyên tử chung**.

### 2.1. Chi phí lệnh và network round trip

Với producer đồng bộ, một vòng transaction thường đòi hỏi broker xử lý `tx.commit` rồi trả lời; ứng dụng phải chờ để biết kết quả. Khi commit sau *mỗi* publish, độ trễ round trip và xử lý broker lặp lại nhiều lần. Trong khi đó, publisher confirms cho phép gửi **nhiều message đang chờ xác nhận cùng lúc**, rồi xử lý ACK/NACK từ broker theo correlation data. Cách này thường có thông lượng tốt hơn giao dịch commit từng message.

| Chi phí / tính chất | Channel transaction | Publisher confirms |
|---|---|---|
| Cơ chế | `tx.select` + publish + `tx.commit`/`tx.rollback` | Publish + broker gửi confirm ACK/NACK |
| Ứng dụng có phải đợi kết quả? | Thường chờ kết quả commit | Có thể theo dõi bất đồng bộ, giữ nhiều publish in-flight |
| Overhead khi một commit cho mỗi message | Cao; thêm round trip/điều phối transaction | Thường thấp hơn khi pipeline nhiều message |
| Có thể nhóm nhiều publish để giảm overhead? | Có, nhưng mở rộng phạm vi transaction và không loại bỏ điểm chờ commit | Có, theo dõi nhiều correlation data |
| Biết message *không được route đến queue*? | Không chỉ nhờ transaction | Cần `mandatory=true` + publisher returns |
| Làm DB + RabbitMQ commit nguyên tử? | **Không** | **Không** |
| Dùng cùng channel với cơ chế còn lại? | **Không**: channel ở transaction mode không dùng publisher confirms | **Không**: channel ở confirm mode không dùng transactions |

Không nên khẳng định một con số TPS/latency chung: chi phí thay đổi theo RTT, queue type, độ bền message, số binding/queue, tải broker, kích thước payload và số lần commit. Cần đo trên workload thật hoặc mô hình gần với production.

### 2.2. Kích thước transaction, ACK và độ trễ

Transaction lớn hơn giảm số lượt `tx.commit` nhưng tăng số message nằm trong phạm vi chưa commit hoặc cần xử lý lại khi xảy ra lỗi. Ở consumer, SMLC có `batchSize` ảnh hưởng việc gom ACK/transaction khi cấu hình tương ứng; DMLC không có cơ chế gom transaction bằng `batchSize`. Không nên lấy cấu hình batch acknowledgment làm bằng chứng về **giao dịch chung với database**.

Ngoài overhead trực tiếp, transaction đồng bộ có thể khiến thread gọi `RabbitTemplate` chờ broker. Khi broker gặp sự cố hoặc mạng chậm, các API/request thread, pool kết nối và các transaction DB bên ngoài có thể bị giữ lâu hơn. Nếu gọi RabbitMQ ngay trong một transaction SQL, thời gian giữ lock DB càng dài.

### 2.3. Giới hạn ngữ nghĩa

- `tx.rollback` chỉ có ý nghĩa với các thao tác trên AMQP channel trong phạm vi transaction; nó **không đảo ngược SQL commit**, HTTP call hoặc email đã gửi.
- RabbitMQ transaction không cung cấp XA/two-phase commit nguyên tử xuyên database và broker.
- Connection có thể đứt sau khi broker đã xử lý commit nhưng trước khi client nhận kết quả. Client không thể luôn suy ra chắc chắn “chưa publish” chỉ từ timeout hoặc mất kết nối.
- RabbitMQ transaction không nên được diễn giải như đầy đủ mọi bảo đảm ACID của một database quan hệ, đặc biệt khi liên quan nhiều queue, consumer và kết quả bên ngoài broker.

**Sử dụng channel transaction vẫn hợp lý** khi nghiệp vụ chỉ cần nhóm thao tác AMQP trên cùng channel, lưu lượng không lớn và bạn hiểu rõ điều kiện rollback/redelivery. Nó không giải bài toán nhất quán của **DB + RabbitMQ**.

## 3. `@Transactional` kết hợp `channelTransacted` vẫn có cửa sổ lỗi

Xét mã:

~~~java
@Transactional
public void createOrder(CreateOrderRequest request) {
    Order order = orderRepository.save(toOrder(request));
    rabbitTemplate.convertAndSend(
            "orders.events.x", "orders.created",
            new OrderCreated(order.getId()));
}
~~~

Giả sử `RabbitTemplate` đã bật `channelTransacted=true` và đang tham gia một transaction Spring có database transaction manager. Spring AMQP thường đồng bộ AMQP transaction với Spring transaction theo kiểu **best efforts one-phase commit**: database commit trước, rồi đến thao tác commit tài nguyên AMQP liên quan. Đây không phải là giao dịch phân tán nguyên tử.

~~~mermaid
sequenceDiagram
    participant A as OrderService
    participant D as Database
    participant R as RabbitMQ
    A->>D: INSERT orders
    A->>R: publish OrderCreated (AMQP tx)
    A->>D: COMMIT DB
    D-->>A: Thành công
    A->>R: COMMIT AMQP
    alt Rabbit commit thành công
        R-->>A: Commit OK
    else Rabbit commit lỗi hoặc không rõ kết quả
        R--xA: Lỗi / mất kết nối
        Note over A,D: DB đã commit, không rollback lại được
    end
~~~

**Cửa sổ lỗi cốt lõi:** database commit thành công nhưng RabbitMQ commit thất bại hoặc không có kết quả xác định. Đơn hàng tồn tại, còn sự kiện có thể đã mất hoặc không rõ đã đến broker chưa. Nếu đảo thứ tự publish/commit, vẫn có cửa sổ ngược lại: broker nhận sự kiện trong khi DB rollback.

Đây cũng là lý do không thể giải quyết dual write chỉ bằng cách đặt `@Transactional` lên method chứa cả thao tác SQL và `RabbitTemplate.convertAndSend`. `@Transactional` mặc định điều khiển transaction manager mà ứng dụng chọn, và mỗi tài nguyên có quy tắc commit riêng.

## 4. Khi chỉ cần publish đáng tin cậy: publisher confirms

Nếu không có yêu cầu cập nhật database và publish sự kiện trong **một bước nghiệp vụ**, publisher confirms thường là lựa chọn nhẹ hơn AMQP channel transaction.

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

~~~java
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

public void publish(RabbitTemplate template, byte[] body) throws Exception {
    CorrelationData correlation =
            new CorrelationData(UUID.randomUUID().toString());
    template.convertAndSend(
            "orders.events.x", "orders.created", body, correlation);

    CorrelationData.Confirm confirm =
            correlation.getFuture().get(10, TimeUnit.SECONDS);

    if (!confirm.isAck() || correlation.getReturned() != null) {
        throw new IllegalStateException("Publish không được xác nhận/định tuyến");
    }
}
~~~

Ví dụ này dùng `byte[]` để minh họa API; ứng dụng thực có thể đặt content type, message ID và persistent delivery mode qua message converter/post-processor. Bên nhận cần có durable queue, exchange/binding hợp lệ và chiến lược ACK phù hợp.

**Broker ACK không có nghĩa consumer đã xử lý.** Ngay cả khi confirm thành công, consumer vẫn có thể chết trước khi ACK và RabbitMQ giao lại message. Thiết kế end-to-end thường chấp nhận **at-least-once** và khử trùng lặp bằng event ID. Publisher confirms cũng **không giữ lại bản ghi cần gửi** nếu process bị dừng trước khi gọi publish hoặc sau khi database đã commit mà chưa tạo được message. Đây là phần outbox giải quyết.

## 5. Transactional outbox giải quyết điều gì?

**Transactional outbox** lưu **thay đổi nghiệp vụ và một bản ghi sự kiện cần phát** trong **cùng database transaction**. Một thành phần riêng gọi là *relay* hoặc *publisher worker* đọc outbox, gửi message qua RabbitMQ, chờ confirm/return rồi mới đánh dấu đã publish.

~~~mermaid
flowchart LR
    API["API / command"] --> TX["Database transaction"]
    TX --> ORD["orders table"]
    TX --> OUT["outbox_event table"]
    OUT --> REL["Outbox relay"]
    REL --> RT["RabbitTemplate + confirms/returns"]
    RT --> EX["RabbitMQ exchange"]
    EX --> Q["Durable queue"]
    Q --> CON["@RabbitListener"]
    CON --> INB["Inbox / idempotency key"]
    RT -->|"ACK + không return"| SENT["Đánh dấu SENT"]
    RT -->|"NACK, return, timeout"| RETRY["Retry sau, giữ outbox"]
~~~

Với mô hình này, trạng thái DB và ý định publish được tạo cùng lúc. Nếu transaction SQL rollback, **cả đơn hàng lẫn outbox row đều biến mất**; nếu commit, **cả hai tồn tại bền vững**. Khi RabbitMQ tạm ngừng, outbox row vẫn ở database và có thể được gửi lại.

Đổi lại, hệ thống chấp nhận **eventual consistency**: sau khi API trả thành công, có thể có khoảng chờ trước khi downstream nhận sự kiện. Relay cần được giám sát, còn consumer phải xử lý được message trùng lặp.

### Định nghĩa bảo đảm

Outbox cung cấp nền tảng cho **at-least-once publish** khi database và relay hoạt động đúng, có chính sách retry, quyền truy cập broker hợp lệ và không xóa sự kiện chưa gửi. **Nó không bảo đảm exactly-once delivery**: một sự kiện có thể được publish hơn một lần. Tính duy nhất của *tác dụng nghiệp vụ* đến từ idempotency/transaction ở consumer, không đến từ việc publisher chỉ cố gửi một lần.

## 6. Thiết kế bảng outbox

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE outbox_event (
    event_id        UUID PRIMARY KEY,
    aggregate_type  VARCHAR(80) NOT NULL,
    aggregate_id    VARCHAR(120) NOT NULL,
    event_type      VARCHAR(120) NOT NULL,
    payload_json    JSONB NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempts        INTEGER NOT NULL DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    claimed_by      VARCHAR(100),
    published_at    TIMESTAMPTZ,
    CONSTRAINT outbox_status_check
        CHECK (status IN ('PENDING', 'CLAIMED', 'SENT'))
);

CREATE INDEX outbox_due_idx
    ON outbox_event (status, next_attempt_at, created_at);

CREATE INDEX outbox_aggregate_idx
    ON outbox_event (aggregate_type, aggregate_id, created_at);
~~~

Mỗi trường phục vụ một trách nhiệm:

| Trường | Mục đích |
|---|---|
| `event_id` | ID bất biến để correlation, audit và consumer dedup |
| `aggregate_type` + `aggregate_id` | Biết sự kiện thuộc entity nào; hỗ trợ quy tắc ordering theo aggregate |
| `event_type` + `payload_json` | Hợp đồng dữ liệu được publish; cần quản lý schema version |
| `status` | `PENDING`: chưa gửi; `CLAIMED`: worker đang giữ lease; `SENT`: có confirm hợp lệ |
| `next_attempt_at` + `attempts` | Điều khiển retry có backoff; tránh gửi dồn vô hạn |
| `claimed_by` + `locked_until` | Nhiều relay không xử lý trùng một row tại cùng thời điểm; lease hết hạn để phục hồi khi worker chết |
| `created_at` + `published_at` | Đo độ trễ từ commit đến publish, hỗ trợ quan sát và dọn dữ liệu |

`payload_json` nên chứa **đủ thông tin downstream cần**, nhưng cần cân nhắc dữ liệu nhạy cảm và kích thước message. Có thể thêm `schema_version`, `trace_id` hoặc `tenant_id` nếu nghiệp vụ yêu cầu. Không cập nhật nội dung event sau khi DB đã commit; nếu dữ liệu thay đổi, hãy tạo sự kiện mới.

## 7. Ghi nghiệp vụ và outbox trong một transaction SQL

Trọng tâm của outbox là việc **không gọi RabbitMQ bên trong transaction này**. Transaction chỉ ghi dữ liệu của **một database**:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {
    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;

    public OrderApplicationService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public UUID createOrder(CreateOrderRequest request) {
        UUID orderId = UUID.randomUUID();
        orderRepository.insert(orderId, request);  // Cùng DataSource/DB.

        UUID eventId = UUID.randomUUID();
        String payload = """
            {"eventId":"%s","orderId":"%s","type":"OrderCreated"}
            """.formatted(eventId, orderId);

        outboxRepository.insertPending(
                eventId, "Order", orderId.toString(),
                "OrderCreated", payload);

        return orderId; // Commit SQL sau khi method kết thúc thành công.
    }
}
~~~

`OrderRepository` và `OutboxRepository` là interface minh họa cho thao tác SQL; việc cài đặt phải sử dụng **cùng database transaction** (cùng transaction manager/DataSource). Nếu chúng vô tình truy cập hai database độc lập, bảo đảm nguyên tử nói trên không còn đúng.

Đối với dữ liệu production, dùng JSON serializer của ứng dụng thay cho nối chuỗi thủ công, có schema version và bảo đảm escaping. `@Transactional` không cam kết việc publish đã xảy ra; API chỉ cam kết order và outbox row đã được commit cùng nhau.

## 8. Relay gửi outbox qua RabbitTemplate

### 8.1. Claim một nhóm row trong transaction ngắn

Nếu có nhiều relay workers, không nên để tất cả cùng đọc và gửi một bản ghi. Với PostgreSQL, có thể claim một nhóm row bằng `FOR UPDATE SKIP LOCKED` trong **một transaction ngắn**:

~~~sql
WITH due AS (
    SELECT event_id
    FROM outbox_event
    WHERE (status = 'PENDING' AND next_attempt_at <= now())
       OR (status = 'CLAIMED' AND locked_until < now())
    ORDER BY created_at, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT 50
)
UPDATE outbox_event AS o
SET status = 'CLAIMED',
    claimed_by = :worker_id,
    locked_until = now() + interval '60 seconds',
    attempts = o.attempts + 1
FROM due
WHERE o.event_id = due.event_id
RETURNING o.*;
~~~

Sau khi **commit transaction claim**, relay gửi message ra RabbitMQ bên ngoài DB transaction; không giữ row lock trong thời gian chờ mạng. Nếu worker chết, `locked_until` hết hạn và worker khác có thể claim lại. Lưu ý: nếu thời gian publish vượt lease, hai worker vẫn có thể phát cùng một sự kiện. Lease giảm tranh chấp, **không loại bỏ duplicate**.

`FOR UPDATE SKIP LOCKED` là cú pháp PostgreSQL; với MySQL hoặc hệ quản trị khác cần điều chỉnh SQL và xem xét mức isolation. Khi cần giữ thứ tự sự kiện theo từng aggregate, `SKIP LOCKED` cùng nhiều worker có thể gây **đảo thứ tự publish**; cần thiết kế partition/sequence và giới hạn worker cho từng aggregate.

### 8.2. Gửi, đợi confirm/return, đánh dấu SENT

Cấu hình producer:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Đoạn mã minh họa thao tác cho **một outbox row đã claim**:

~~~java
import java.util.concurrent.TimeUnit;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class OutboxPublisher {
    private final RabbitTemplate template;
    private final OutboxRepository repository;

    public OutboxPublisher(
            RabbitTemplate template, OutboxRepository repository) {
        this.template = template;
        this.repository = repository;
    }

    public void publishClaimed(OutboxEvent event, String workerId) {
        try {
            MessageProperties properties = new MessageProperties();
            properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
            properties.setDeliveryMode(MessageDeliveryMode.PERSISTENT);
            properties.setMessageId(event.eventId().toString());
            properties.setHeader("eventId", event.eventId().toString());
            properties.setHeader("eventType", event.eventType());

            Message message = new Message(
                    event.payloadJson().getBytes(java.nio.charset.StandardCharsets.UTF_8),
                    properties);

            CorrelationData correlation =
                    new CorrelationData(event.eventId().toString());
            template.send(
                    "orders.events.x",
                    "orders.created",
                    message,
                    correlation);

            CorrelationData.Confirm confirm =
                    correlation.getFuture().get(10, TimeUnit.SECONDS);

            // RabbitMQ vẫn có thể ACK một publish không route được!
            if (!confirm.isAck() || correlation.getReturned() != null) {
                throw new IllegalStateException(
                        "Broker NACK hoặc message không được định tuyến");
            }

            // SQL update riêng, có điều kiện worker còn sở hữu claim.
            repository.markSentIfClaimed(
                    event.eventId(), workerId);

        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            repository.scheduleRetryIfClaimed(
                    event.eventId(), workerId, "interrupted");
        } catch (Exception ex) {
            repository.scheduleRetryIfClaimed(
                    event.eventId(), workerId, ex.getClass().getSimpleName());
        }
    }
}
~~~

Giả định `OutboxEvent` có các accessor `eventId()`, `eventType()` và `payloadJson()`; repository cung cấp hai phương thức cập nhật có điều kiện. Ví dụ trên tập trung vào thứ tự các thao tác và xử lý lỗi, còn scheduling/claiming được triển khai ở worker riêng (ví dụ `@Scheduled`) để dễ thay đổi thời gian quét.

**Yêu cầu đối với repository:**

- `markSentIfClaimed(id, workerId)` chỉ đổi sang `SENT` nếu row vẫn ở `CLAIMED` và `claimed_by` đúng worker, đồng thời ghi `published_at`.
- `scheduleRetryIfClaimed` đặt lại `PENDING`, tính `next_attempt_at` bằng exponential backoff có jitter và lưu thông tin lỗi; nếu DB update thất bại, lease tự hết hạn để worker khác thử lại.
- Không xóa outbox row trước khi có confirm hợp lệ. Trường hợp ACK broker đến nhưng lệnh SQL `markSent` lỗi sẽ gây **publish lại**, nên consumer cần dedup.
- Nếu không có cấu hình returns + mandatory, message **không có binding đến queue** vẫn có thể được confirm ACK ở tầng broker. Chỉ dùng confirm để quyết định `SENT` sẽ là thiếu kiểm tra routing.

Các class minh họa là những phần của một thiết kế Spring Boot; ứng dụng cần cung cấp schema, repository và cấu hình executor/scheduler cụ thể. **Không bật `channelTransacted` trên publisher channel đang dùng publisher confirms**.

### 8.3. Retry, giới hạn và quarantine

Nếu broker ngừng hoạt động, outbox tích lũy thay vì khiến lệnh tạo đơn hàng liên tục phải đợi broker. Relay cần có backoff và giới hạn số lần thử theo chính sách vận hành; sau nhiều lỗi có thể chuyển trạng thái sang `FAILED` hoặc hệ thống kiểm soát lỗi tương đương và phát cảnh báo. Nếu bổ sung `FAILED`, cập nhật constraint của schema tương ứng.

Ở đầu nhận, consumer cũng có thể thất bại vì lỗi dữ liệu. Khi đó, dùng retry hữu hạn và dead-letter/quarantine queue. **Outbox retry ở phía publisher và DLQ retry ở phía consumer là hai vòng đời khác nhau**; một message được broker confirm không đồng nghĩa consumer đã ACK.

## 9. Vì sao outbox vẫn cần idempotent consumer?

Các tình huống rất phổ biến:

1. Broker nhận sự kiện, nhưng kết nối mất trước khi relay thấy confirm. Relay thử lại sau timeout.
2. Broker confirm thành công, nhưng database không ghi được `SENT`. Relay gửi lại khi lease hết hạn.
3. Broker giao message cho consumer, consumer đã ghi DB thành công nhưng chết trước ACK. RabbitMQ giao lại sau khi kết nối bị đóng.

Vì vậy, **eventId** phải giữ nguyên trong mỗi lần gửi lại cùng sự kiện. Consumer ghi “đã xử lý event ID này” trong **cùng database transaction** với tác dụng nghiệp vụ:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class OrderCreatedConsumer {
    private final ProcessedEventRepository inbox;
    private final InvoiceRepository invoices;

    public OrderCreatedConsumer(
            ProcessedEventRepository inbox, InvoiceRepository invoices) {
        this.inbox = inbox;
        this.invoices = invoices;
    }

    @Transactional
    @RabbitListener(queues = "invoices.orders-created.q")
    public void onEvent(OrderCreated event) {
        // INSERT ... ON CONFLICT DO NOTHING; trả false nếu event đã xử lý.
        if (!inbox.insertIfAbsent("invoice-service", event.eventId())) {
            return;
        }
        invoices.createForOrder(event.orderId());
    }
}
~~~

Ví dụ giả định JSON converter chuyển body thành `OrderCreated` và container mặc định dùng `AUTO` acknowledgment. Trong mô hình thông thường, Spring kết thúc DB transaction của method trước khi listener adapter đánh dấu xử lý thành công. Nếu DB rollback, exception phải tiếp tục đi ra khỏi method để broker xử lý NACK/retry theo cấu hình.

Để tránh race condition, thao tác `insertIfAbsent` dựa vào **unique constraint** trên bảng `processed_event`; thao tác ghi invoice và insert inbox phải dùng **cùng transaction DB**. Nếu cần gọi API bên ngoài, truyền `eventId` làm idempotency key nếu API hỗ trợ, hoặc thiết kế thêm outbox cho tác dụng phụ đó. DB-only dedup không tự động bảo đảm một HTTP call không bao giờ lặp.

## 10. Ma trận lỗi: điều gì được bảo đảm?

| Thời điểm lỗi | Channel transaction ghép với DB | Transactional outbox |
|---|---|---|
| Lỗi trước khi DB commit | Có thể rollback SQL; còn phụ thuộc trạng thái publish/AMQP tx | Rollback cả đơn hàng và outbox row |
| DB commit xong, RabbitMQ chưa nhận sự kiện | Có nguy cơ mất sự kiện khi AMQP commit lỗi | Outbox vẫn còn, relay sẽ thử publish |
| RabbitMQ không truy cập được vài phút | Thread/request có thể bị block hoặc fail nếu publish ngay trong request | API vẫn có thể ghi DB; backlog outbox tăng, relay retry sau |
| Broker ACK publish, SQL đánh dấu đã gửi thất bại | Không có bản ghi outbox đủ tin cậy để phát lại có kiểm soát | Có thể publish trùng; eventId ổn định cho dedup |
| Message không có queue đích | Transaction/confirm riêng lẻ chưa đủ xác nhận route | Mandatory returns phát hiện; không đánh dấu `SENT` |
| Consumer chết sau DB commit nhưng trước ACK | Vẫn có khả năng redelivery | Vẫn có khả năng redelivery; inbox/idempotency xử lý |
| Process relay chết giữa claim và publish | Không có cơ chế relay ở mô hình trực tiếp | Lease hết hạn; worker khác tiếp tục |
| Nhiều sự kiện cho cùng một aggregate | Phụ thuộc trình tự publish và commit | Phải thiết kế ordering; nhiều worker có thể làm đảo thứ tự |

Outbox không làm lỗi biến mất. Nó **chuyển một khoảng mất dữ liệu khó phục hồi thành một hàng đợi bền vững trong database**, để có thể retry, theo dõi và điều tra. Đổi lại, có chi phí database và độ trễ bất đồng bộ.

## 11. So sánh chi phí hiệu năng và vận hành

| Tiêu chí | AMQP transaction + publish trực tiếp | Publisher confirms trực tiếp | Transactional outbox + confirms |
|---|---|---|---|
| Chi phí phía request | Có thể đợi transaction commit RabbitMQ | Có thể đợi confirm, tùy synchronous/async | Thêm SQL INSERT outbox trong cùng DB transaction |
| Chi phí phía RabbitMQ | `tx.select`/`tx.commit`, độ trễ commit | Confirm cho nhiều publish in-flight | Confirm giống publisher thông thường, do relay thực hiện |
| Chi phí database | Không nhất thiết cần bảng bổ sung | Không nhất thiết cần bảng bổ sung | Thêm outbox table, index, scan/claim, update, dọn lưu trữ |
| Thời gian từ DB commit tới sự kiện | Gần tức thời nếu broker khỏe, nhưng có cửa sổ dual write | Gần tức thời nếu gửi trực tiếp, vẫn có dual write | Có lag do poll/CDC và tải relay |
| Chịu sự cố broker lúc request | Có thể làm request fail/chậm | Cần tầng lưu trữ ngoài nếu muốn retry bền vững | Event đã được commit trong DB, gửi lại khi broker phục hồi |
| Khả năng duplicate | Có | Có | **Có**, thiết kế idempotency là bắt buộc |
| Bảo đảm DB + event | Không nguyên tử xuyên hai tài nguyên | Không nguyên tử xuyên hai tài nguyên | Nguyên tử giữa DB state và **outbox row**; publish cuối cùng là at-least-once |
| Độ phức tạp hệ thống | Ít thành phần nhưng có góc lỗi khó xử lý | Ít thành phần, cần quản lý confirm | Cần relay, schema, retry, cleanup, metric và runbook |

### Polling và CDC

Có hai cách phổ biến để chuyển row outbox thành RabbitMQ message:

- **Polling relay:** một worker định kỳ claim các row `PENDING`, publish, chờ confirm rồi đánh dấu `SENT`. Dễ xây với Spring Boot/`@Scheduled` và `JdbcTemplate`/JPA, nhưng gây truy vấn lặp, cần tuning index, batch size, interval và lease.
- **Change Data Capture (CDC):** một hệ thống đọc database change log rồi đưa event đi tiếp. Có thể giảm nhu cầu poll và phản ứng nhanh, nhưng thêm hạ tầng, cấu hình connector, vận hành offset/restart và bài toán duplicate/ordering. CDC cũng phải được thiết kế để giữ event ID và bảo đảm đường publish tới RabbitMQ.

Chọn polling khi quy mô và độ trễ cho phép, cần triển khai đơn giản trong dịch vụ Spring hiện có. Xem xét CDC khi số lượng event lớn, polling gây tải DB hoặc cần xây một luồng sự kiện chung cho nhiều dịch vụ. **CDC không biến toàn bộ đường truyền thành exactly-once**.

### Giảm chi phí outbox khi tải tăng

1. Claim theo batch vừa phải, có giới hạn số event concurrent và số publish đang chờ confirm.
2. Dùng index cho trạng thái/`next_attempt_at`; không scan toàn bảng hoặc giữ transaction SQL mở trong khi đợi broker.
3. Lưu payload đủ dùng, có schema rõ ràng; có thể tách hoặc nén payload lớn nếu thực sự cần.
4. Dọn/partition các row `SENT` theo retention đã duyệt; **không dọn `PENDING` chỉ vì row quá cũ**.
5. Dùng backoff có jitter để tránh relay đồng loạt gửi bão publish ngay khi broker phục hồi.
6. Giữ `eventId` bất biến và quan sát log/traces qua database, exchange, queue và consumer.

## 12. Kiểm thử trước khi đưa vào production

| Kịch bản | Cách giả lập | Kết quả mong đợi |
|---|---|---|
| Rollback nghiệp vụ | Ném exception trước commit SQL | Không có order và không có outbox row |
| DB commit thành công | Tạo order hợp lệ | Có cả order và `PENDING` event trước khi relay gửi |
| RabbitMQ tạm ngừng | Dừng broker trước khi relay chạy | Row vẫn chưa `SENT`; không mất event |
| Publish không có binding | Cố ý cấu hình routing key sai | Publisher return; row không bị đánh dấu `SENT` |
| Broker NACK | Mô phỏng fail publish | Row được retry/backoff; có metric thất bại |
| Mất kết nối sau publish | Ngắt client khi chờ confirm | Relay có thể gửi lại; cùng `eventId`; consumer dedup |
| Lỗi SQL sau confirm | Làm `markSent` ném lỗi | Row được gửi lại khi phục hồi; không tạo tác dụng nghiệp vụ hai lần |
| Worker chết sau claim | Dừng relay khi row ở `CLAIMED` | Lease hết hạn; worker khác claim được |
| Hai relay tranh cùng row | Chạy worker song song | Claim dùng lock/lease; chấp nhận duplicate khi lease hết hạn |
| Consumer chết trước ACK | Dừng consumer sau commit DB | RabbitMQ redeliver; inbox unique key chặn duplicate effect |
| Nhiều event cùng aggregate | Publish có nhiều worker và delay | Kiểm tra thứ tự; áp dụng sequence/partition nếu cần |
| Backlog kéo dài | Dừng relay rồi khởi động lại | Outbox lag giảm, không quá tải broker, có cảnh báo backlog |

Ngoài các test chức năng, đo **p50/p95/p99 latency của API**, thời gian commit database, round trip publish/confirm, throughput broker, `outbox pending count`, tuổi của row chưa publish lâu nhất, `publish lag = published_at - created_at`, tỷ lệ retry và duplicate ở consumer. So sánh các phương án dưới cùng kích thước message, queue type, prefetch, số connection và tải database; đừng so bằng TPS thu được từ hai cấu hình môi trường khác nhau.

## 13. Chọn giải pháp theo bài toán

- **Chỉ publish message, không có cùng một nghiệp vụ cần commit DB:** dùng `RabbitTemplate` với publisher confirms/returns, durable topology và retry/idempotency phù hợp. Không nhất thiết cần outbox.
- **Cần giao dịch AMQP cục bộ trên một channel, lưu lượng vừa phải:** `channelTransacted` có thể phù hợp, nhưng phải chấp nhận độ trễ commit và giới hạn ngữ nghĩa.
- **Cập nhật DB và bắt buộc có một event tương ứng:** dùng **transactional outbox** để commit dữ liệu nghiệp vụ và ý định publish trong cùng SQL transaction; relay chịu trách nhiệm gửi tới RabbitMQ.
- **Đường xử lý từ consumer sang database:** cần xử lý duplicate bằng inbox/idempotency và bảo đảm kết thúc DB transaction trước ACK. Outbox hữu ích khi consumer còn phải phát *sự kiện tiếp theo* tương ứng với thay đổi DB vừa ghi.
- **Yêu cầu trật tự nghiêm ngặt theo entity:** thêm sequence/partition và quy tắc một luồng publish theo aggregate; bản thân outbox hoặc nhiều relay không tự đảm bảo thứ tự.

**Tổng kết:** transaction RabbitMQ giúp điều phối thao tác trên AMQP channel nhưng phải trả chi phí commit và không thể gộp nguyên tử với database chỉ bằng `@Transactional`. Publisher confirms rẻ hơn cho publish độc lập, song vẫn chưa xử lý được cửa sổ lỗi của dual write. **Transactional outbox** đổi chi phí của một bảng DB, relay và độ trễ bất đồng bộ để có trạng thái sự kiện bền vững cùng commit nghiệp vụ. Giữ publisher confirms + returns, retry hữu hạn, theo dõi backlog và consumer idempotent thì hệ thống Spring AMQP mới có thể phục hồi an toàn trước các tình huống mất kết nối, crash và giao lại message.
