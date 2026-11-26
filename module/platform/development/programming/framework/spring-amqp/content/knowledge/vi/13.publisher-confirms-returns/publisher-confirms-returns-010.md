# Timeout hoặc mất kết nối khi chưa biết kết quả publish

Trong chương **Confirm và return** của **SPRING_AMQP**, có một tình huống đặc biệt quan trọng: producer gửi message qua **RabbitTemplate**, nhưng **timeout hoặc mất kết nối trước khi nhận publisher confirm**. Ở thời điểm này, ứng dụng không biết chắc RabbitMQ đã chấp nhận message hay chưa.

Nếu không gửi lại, sự kiện có thể bị mất. Nếu gửi lại, consumer có thể nhận cùng sự kiện hai lần. Bài này giải thích trạng thái **kết quả chưa xác định (ambiguous outcome)**, cách phân biệt **publisher confirm** với **publisher return**, cách dùng **CorrelationData** trong Spring AMQP và cách kết hợp **transactional outbox**, retry và consumer idempotent để xử lý bất đồng bộ đáng tin cậy.

> **Nguyên tắc:** Không nhận được confirm ACK không chứng minh message đã mất. Khi publisher chưa biết kết quả, hãy bảo tồn ý định gửi và **eventId**, ghi nhận trạng thái **UNKNOWN**, rồi retry an toàn theo một chính sách có kiểm soát.

## 1. Phân biệt publish, routing và xử lý nghiệp vụ

RabbitMQ dùng exchange, routing key và binding để chọn queue. Message được consumer nhận sau đó; mỗi chặng có cơ chế xác nhận riêng.

~~~mermaid
flowchart LR
    P["Producer<br/>RabbitTemplate"] -->|"basic.publish"| E{"Exchange"}
    E -->|"Binding khớp routing key"| Q[("Queue")]
    Q -->|"Delivery"| C["Consumer<br/>@RabbitListener"]
    E -.->|"Publisher confirm ACK/NACK"| P
    E -.->|"Return nếu NO_ROUTE + mandatory"| P
    C -.->|"Consumer ACK/NACK"| Q
~~~

| Tín hiệu | Nơi phát sinh | Ý nghĩa | Không bảo đảm |
|---|---|---|---|
| **Publisher confirm ACK** | Broker → publisher | Broker đã xử lý việc publish theo ngữ nghĩa queue và delivery mode liên quan | Consumer đã xử lý nghiệp vụ |
| **Publisher confirm NACK** | Broker/framework → publisher | Publish không được xác nhận thành công; có thể cần gửi lại | Mọi side effect chắc chắn chưa xảy ra |
| **Publisher return** | Broker → publisher | Message không route được trong điều kiện mandatory | Trạng thái xử lý của consumer |
| **Consumer ACK** | Consumer → broker | Một delivery đã được xử lý/xác nhận | Producer có nhận publisher confirm hay không |
| **Không nhận confirm** | Không có kết quả cuối được quan sát | Có thể broker nhận hoặc chưa nhận message | Message chắc chắn đã mất |

**ACK từ publisher không có nghĩa message đã vào queue mong đợi trong mọi cấu hình.** Nếu exchange tồn tại nhưng không có binding khớp, broker vẫn có thể trả publisher ACK vì đã xử lý publish. Khi **mandatory=true**, broker sẽ phát **basic.return** trước ACK để producer biết message không được route.

Nếu exchange dùng **alternate exchange**, một message không route ở exchange chính có thể được route qua alternate exchange. Khi alternate exchange xử lý được message, producer có thể không nhận mandatory return. Vì vậy, cần kiểm tra topology thực tế khi điều tra message đi sai đích.

## 2. Vì sao timeout tạo kết quả chưa xác định?

Giả sử Order Service phát OrderPlaced với eventId **evt-101**.

~~~mermaid
sequenceDiagram
    participant P as Order Service
    participant B as RabbitMQ
    participant Q as Queue
    P->>B: basic.publish(evt-101)
    B->>Q: Lưu message
    B--xP: Publisher confirm ACK bị mất khi mạng đứt
    Note over P: Timeout chờ confirm<br/>Kết quả UNKNOWN
    P->>B: Reconnect và gửi lại evt-101
    B->>Q: Nhận thêm bản sao
    Note over Q: Queue có thể có 2 delivery<br/>cùng eventId
~~~

Một kết nối có thể hỏng ở nhiều thời điểm:

1. **Trước khi frame publish đến broker:** RabbitMQ chưa nhận message.
2. **Sau khi broker nhận nhưng trước khi lưu bền vững:** kết quả phụ thuộc queue và trạng thái broker.
3. **Sau khi broker đã nhận và ACK nhưng ACK chưa đến client:** broker đã nhận message, producer vẫn timeout.
4. **Sau khi broker route và consumer xử lý nhưng producer vẫn chưa nhận ACK:** retry có thể tạo tác dụng phụ lặp lại nếu consumer không idempotent.

Các trường hợp trên có thể có cùng dấu hiệu ở phía publisher: **timeout, connection reset, channel closed hoặc confirm không đến**. Vì thế, timeout chỉ chứng minh rằng **publisher chưa quan sát được kết quả cuối trong khoảng chờ**, không chứng minh broker đã hoặc chưa nhận message.

### 2.1. Vì sao không chỉ tra số message trong queue?

Việc mở RabbitMQ Management UI hoặc đọc **Ready / Unacked** không đủ để xác định một event cụ thể đã được publish thành công. Consumer có thể đã nhận và ACK nó; message có thể được dead-letter; queue còn chứa message khác; messageId không phải một khóa tra cứu lịch sử được broker tự bảo đảm duy nhất.

Nếu cần biết việc **nghiệp vụ** đã hoàn thành, phải có cơ chế trạng thái ở phía nghiệp vụ. Publisher confirm không thay thế xác nhận xử lý của consumer.

## 3. Thiết kế các trạng thái publish rõ ràng

Đừng gộp mọi tình huống thành một trạng thái FAILED.

| Kết quả quan sát | Trạng thái đề xuất | Hành động phù hợp |
|---|---|---|
| Confirm ACK và không nhận return | **CONFIRMED** | Kết thúc bước publish theo tiêu chí broker |
| Return **NO_ROUTE** (có thể đi kèm ACK) | **UNROUTABLE** | Kiểm tra exchange, binding, key và vhost |
| Confirm NACK | **NACKED** | Ghi nguyên nhân, retry có giới hạn |
| Timeout chờ confirm | **UNKNOWN** | Giữ event, lên lịch kiểm tra/gửi lại an toàn |
| Mất connection trước confirm | **UNKNOWN** nếu không có tín hiệu xác định | Giữ event và retry có kiểm soát |
| Send ném exception nhưng không chứng minh chắc chưa gửi | **UNKNOWN** | Bảo tồn ý định gửi, tránh mất dữ liệu |
| Consumer xử lý xong | **BUSINESS_COMPLETED** | Theo dõi bằng trạng thái nghiệp vụ riêng |

Có thể dùng state machine:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING: Commit outbox
    PENDING --> IN_FLIGHT: Dispatcher publish
    IN_FLIGHT --> CONFIRMED: ACK và không return
    IN_FLIGHT --> UNROUTABLE: Basic return
    IN_FLIGHT --> NACKED: NACK
    IN_FLIGHT --> UNKNOWN: Timeout / mất kết nối
    UNKNOWN --> PENDING: Lập lịch gửi lại
    NACKED --> PENDING: Retry theo chính sách
    UNROUTABLE --> PENDING: Sửa route rồi retry
    CONFIRMED --> [*]: Hoàn tất bước publish
~~~

**UNKNOWN không đồng nghĩa FAILED chắc chắn.** Trong ứng dụng thật, cần lưu thêm **attemptNo, lastAttemptId, lastError, nextRetryAt** và thời điểm cập nhật. Khi callback confirm đến muộn, phải cập nhật đúng attempt, tránh ghi đè trạng thái của lần gửi mới.

## 4. Cấu hình Spring Boot cho correlated confirms và returns

Thêm Spring AMQP starter vào dự án Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-amqp</artifactId>
</dependency>
~~~

Cấu hình ví dụ cho broker đã có user và virtual host phù hợp:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    virtual-host: app_dev
    username: learn_amqp
    password: ${RABBITMQ_PASSWORD}
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    requested-heartbeat: 30s
    connection-timeout: 10s
~~~

| Property | Tác dụng |
|---|---|
| **publisher-confirm-type: correlated** | Ghép publisher ACK/NACK với từng **CorrelationData** |
| **publisher-returns: true** | Bật nhận message bị trả lại khi không route được |
| **template.mandatory: true** | Yêu cầu broker trả message không đến queue nào |
| **requested-heartbeat** | Giúp phát hiện một số kết nối chết, **không phải thời hạn publisher confirm** |
| **connection-timeout** | Thời gian chờ mở kết nối, **không phải thời gian chờ ACK publish** |

Chỉ định confirm timeout ở tầng **code chờ kết quả**, ví dụ **CompletableFuture.get(10, TimeUnit.SECONDS)**. Giá trị 10 giây chỉ mang tính minh họa; trong production cần đo latency broker, ghi đĩa, quorum và điều kiện network trước khi chọn ngưỡng.

**Không nhầm các timeout:** connection-timeout dành cho kết nối; receive-timeout liên quan lời gọi nhận message; reply-timeout liên quan request/reply; timeout của future trong ví dụ là khoảng thời gian ứng dụng chờ **publisher confirm**.

Spring AMQP còn có confirm type **simple**, phù hợp một số kiểu chờ confirms. Bài này dùng **correlated** để theo dõi từng lần gửi và kết hợp thông tin return. Không dùng AMQP transaction và publisher confirms trên cùng một channel.

## 5. Event ID và publish attempt ID là hai khóa khác nhau

Mỗi sự kiện nghiệp vụ cần định danh **ổn định qua mọi lần thử gửi**:

| Khóa | Ví dụ | Công dụng |
|---|---|---|
| **eventId** | evt-101 | Nhận diện duy nhất sự kiện nghiệp vụ, phục vụ idempotency |
| **publishAttemptId** | evt-101:2 | Ghép mỗi lần gửi với confirm/callback tương ứng |
| **correlationId** (nếu cần) | checkout-5001 | Liên kết workflow hoặc request/reply |

Ví dụ:

~~~text
Event ID không đổi: evt-101

Attempt 1: CorrelationData("evt-101:1")
Attempt 2: CorrelationData("evt-101:2")
Attempt 3: CorrelationData("evt-101:3")
~~~

**Giữ eventId cũ khi retry**, vì broker có thể đã nhận message ở attempt trước. **Tạo CorrelationData mới** theo mỗi attempt, vì confirm của attempt 1 có thể đến muộn sau khi attempt 2 được bắt đầu.

Trong Spring AMQP hiện đại, **CorrelationData.getFuture()** trả về **CompletableFuture** chứa **CorrelationData.Confirm**. Khi bật cả correlated confirms, returns và mandatory, **CorrelationData.getReturn()** cho biết message đã bị return, và được cập nhật trước khi confirm future hoàn tất với ACK liên quan.

## 6. Ví dụ Spring AMQP: publish và chờ confirm có giới hạn

### 6.1. Khai báo topology thử nghiệm

~~~java
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Declarables;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ConfirmDemoTopology {
    public static final String EXCHANGE = "orders.confirm-demo";
    public static final String ROUTING_KEY = "order.placed";
    public static final String QUEUE = "orders.confirm-demo.q";

    @Bean
    public Declarables topology() {
        DirectExchange exchange =
                new DirectExchange(EXCHANGE, true, false);
        Queue queue = QueueBuilder.durable(QUEUE).build();

        return new Declarables(
                exchange,
                queue,
                BindingBuilder.bind(queue)
                        .to(exchange)
                        .with(ROUTING_KEY)
        );
    }
}
~~~

Trong cấu hình Spring Boot thông dụng, RabbitAdmin có thể tự khai báo các resource bean này nếu tính năng auto-declaration đang bật. **Exchange và queue durable** giữ topology qua restart; để bảo vệ message còn cần persistence, confirms và đặc tính queue phù hợp.

### 6.2. Gửi byte JSON và đọc confirm/return

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.amqp.AmqpException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class ConfirmAwarePublisher {
    public enum Outcome {
        CONFIRMED, UNROUTABLE, NACKED, UNKNOWN
    }

    private final RabbitTemplate template;

    public ConfirmAwarePublisher(RabbitTemplate template) {
        this.template = template;
    }

    public Outcome sendAndWait(
            String eventId,
            String attemptId,
            byte[] jsonBytes) {
        Message message = MessageBuilder.withBody(jsonBytes)
                .setContentType(MessageProperties.CONTENT_TYPE_JSON)
                .setContentEncoding("UTF-8")
                .setMessageId(eventId)
                .setDeliveryMode(MessageDeliveryMode.PERSISTENT)
                .build();

        CorrelationData data = new CorrelationData(attemptId);

        try {
            template.send(
                    ConfirmDemoTopology.EXCHANGE,
                    ConfirmDemoTopology.ROUTING_KEY,
                    message,
                    data
            );

            CorrelationData.Confirm confirm =
                    data.getFuture().get(10, TimeUnit.SECONDS);

            if (!confirm.isAck()) {
                return Outcome.NACKED;
            }
            if (data.getReturn() != null) {
                return Outcome.UNROUTABLE;
            }
            return Outcome.CONFIRMED;

        } catch (TimeoutException ex) {
            return Outcome.UNKNOWN;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return Outcome.UNKNOWN;
        } catch (ExecutionException | AmqpException ex) {
            return Outcome.UNKNOWN;
        }
    }
}
~~~

Giải thích:

- **CONFIRMED**: Có ACK và không có return theo cấu hình đang dùng; broker xác nhận đã xử lý publish theo ngữ nghĩa của nó.
- **UNROUTABLE**: Mandatory return đã được ghi nhận; thường cần sửa binding, routing key hoặc topology.
- **NACKED**: Confirm âm, cần lưu nguyên nhân để điều tra và thử lại.
- **UNKNOWN**: Đợi quá hạn hoặc lỗi không đủ thông tin để kết luận broker chưa nhận message.

**get(10, TimeUnit.SECONDS) timeout không hủy message ở broker.** Future có thể được hoàn tất sau khi phương thức đã trả UNKNOWN. Đây là ví dụ đồng bộ dễ quan sát; không nên chờ từng confirm theo cách này trong luồng publish throughput cao.

Để log nguyên nhân, dùng **confirm.getReason()** khi NACK và **data.getReturn().getReplyText()** khi return. Với những lỗi khác, lưu exception chi tiết cùng eventId/attemptId. Đừng chỉ lưu enum rồi làm mất thông tin chẩn đoán.

### 6.3. Phương án bất đồng bộ bằng future callback

Thay vì block thread chờ confirm, một dispatcher có thể xử lý kết quả bất đồng bộ:

~~~java
CorrelationData data = new CorrelationData(attemptId);

template.send(
        ConfirmDemoTopology.EXCHANGE,
        ConfirmDemoTopology.ROUTING_KEY,
        message,
        data
);

data.getFuture().whenComplete((confirm, error) -> {
    if (error != null) {
        // Ghi UNKNOWN cho đúng attemptId.
        return;
    }
    if (!confirm.isAck()) {
        // Ghi NACKED và confirm.getReason().
        return;
    }
    if (data.getReturn() != null) {
        // Ghi UNROUTABLE và return.getReplyText().
        return;
    }
    // Ghi CONFIRMED cho đúng attemptId.
});
~~~

Đoạn trên là **mảnh mã minh họa** dùng các biến đã được khởi tạo ở luồng gửi. Trong ứng dụng thật, mỗi nhánh phải gọi một service cập nhật trạng thái outbox **có điều kiện theo attemptId** và có error handling riêng.

Chỉ nên thực hiện thao tác ngắn trong callback. Spring AMQP hỗ trợ **một ConfirmCallback và một ReturnsCallback trên mỗi RabbitTemplate**; nếu nhiều thành phần cùng set callback, callback sau có thể thay thế callback trước. CorrelationData future hữu ích khi cần xử lý theo từng event, hoặc có thể xây một callback dispatcher tập trung.

Nếu dùng return callback, tránh logic blocking kéo dài. Tài liệu Spring AMQP quy định return được xử lý trước confirm trong cơ chế correlated, với các chi tiết timing khi return callback chạy quá lâu. Đừng để một callback nặng làm chậm việc nhận confirm của nhiều message.

## 7. Vì sao publisher ACK có thể đi kèm NO_ROUTE?

Thử publish tới:

~~~text
Exchange: orders.confirm-demo
Routing key: order.unknown
Mandatory: true
Binding hiện có: order.placed -> orders.confirm-demo.q
~~~

Exchange vẫn tồn tại, nhưng không có binding khớp. RabbitMQ có thể phát:

~~~text
basic.return: 312 NO_ROUTE
basic.ack: publisher confirm
~~~

**Cả return lẫn ACK đều có thể đúng.** ACK báo broker đã xử lý publish; return báo không có queue nhận message theo định tuyến.

| Tình huống | Confirm | Return | Diễn giải |
|---|---|---|---|
| Exchange hợp lệ, key khớp queue | Thường ACK | Không | Broker chấp nhận message |
| Exchange hợp lệ, key không khớp, mandatory=true | Thường ACK | **NO_ROUTE** | Message bị return |
| Key không khớp, mandatory=false | ACK có thể có | Không | Message có thể bị loại mà producer không biết |
| Exchange không tồn tại | Lỗi channel, có thể framework NACK | Không phải NO_ROUTE thông thường | Topology sai |
| Network mất trước confirm | Không có kết quả rõ | Không chắc | UNKNOWN |
| Alternate exchange route được | Có thể ACK | Có thể không | Message đi qua đường alternate exchange |

Vì vậy, logic **chỉ kiểm tra confirm.isAck() rồi đánh dấu đã publish thành công** có thể bỏ sót message bị return. Phải đọc **return cùng confirm**.

Nếu return là NO_ROUTE, retry nguyên message ngay mà không đổi topology thường chỉ lặp lỗi. Nên dừng, kiểm tra exchange, binding, routing key, virtual host và quyền trước khi replay.

## 8. Timeout xác nhận khác timeout của HTTP và request/reply

Một ứng dụng có thể có nhiều giới hạn thời gian:

| Giới hạn | Ý nghĩa |
|---|---|
| **spring.rabbitmq.connection-timeout** | Chờ tạo kết nối |
| **spring.rabbitmq.requested-heartbeat** | Hỗ trợ phát hiện kết nối không còn hoạt động |
| **CorrelationData future.get(timeout)** | Chờ publisher confirm theo lựa chọn của ứng dụng |
| **RabbitTemplate receive-timeout** | Giới hạn một số lời gọi receive đồng bộ |
| **RabbitTemplate reply-timeout** | Chờ message trả lời trong request/reply |
| **HTTP timeout** | Client HTTP chờ phản hồi API bao lâu |

Giả sử HTTP client gọi **POST /orders**, Order Service lưu đơn rồi publish OrderPlaced. Nếu HTTP timeout và publisher confirm timeout cùng lúc, có thể có **hai nguồn retry**:

1. Client HTTP gửi lại **POST /orders**.
2. Outbox dispatcher gửi lại **OrderPlaced** chưa được confirm.

Vì vậy, cần hai cơ chế bảo vệ:

- **Request idempotency key** để tránh tạo hai đơn hàng cho cùng một yêu cầu HTTP.
- **eventId/idempotency key** để consumer không tạo hai hóa đơn từ cùng một sự kiện bị gửi lại.

Không có timeout nào trong bảng tự giải quyết khả năng message đã tới broker nhưng confirm chưa được quan sát.

## 9. Transactional outbox: giữ ý định gửi qua crash và reconnect

### 9.1. Vấn đề khi publish trực tiếp sau DB commit

~~~text
1. INSERT order
2. COMMIT
3. RabbitTemplate.send(OrderPlaced)
4. Nhận publisher confirm
~~~

Nếu process chết sau **COMMIT** nhưng trước **send**, đơn đã được lưu nhưng event chưa được phát. Nếu process chết sau **send** nhưng trước confirm, trạng thái publish không chắc chắn.

Đặt lệnh send bên trong một Spring **@Transactional** không tự tạo distributed transaction cho database và RabbitMQ. Một giao dịch DB thông thường không thể làm broker và database commit nguyên tử chỉ bằng annotation này.

### 9.2. Lưu order và outbox trong cùng một DB transaction

~~~mermaid
flowchart TD
    R["POST /orders"] --> T["DB transaction"]
    T --> O["INSERT orders"]
    T --> E["INSERT outbox_event<br/>eventId, payload, status=PENDING"]
    O --> C["COMMIT"]
    E --> C
    C --> D["Outbox dispatcher"]
    D --> P["RabbitTemplate.send"]
    P --> A{"Confirm / return"}
    A -->|"ACK, no return"| OK["CONFIRMED"]
    A -->|"NO_ROUTE"| NR["UNROUTABLE"]
    A -->|"NACK"| NK["NACKED -> retry"]
    A -->|"Timeout/disconnect"| U["UNKNOWN -> retry"]
~~~

Dữ liệu lưu bền vững:

~~~text
outbox_event
  event_id             evt-101
  event_type           order.placed
  payload_json         {"orderId":"ord-101", ...}
  exchange_name        orders.confirm-demo
  routing_key          order.placed
  status               UNKNOWN
  attempt_no           2
  last_attempt_id      evt-101:2
  next_retry_at        2026-11-26T03:00:00Z
  last_error           confirm_timeout
~~~

Quy trình:

1. Trong một transaction DB, ghi dữ liệu nghiệp vụ **và** outbox record.
2. Dispatcher claim một số event PENDING; có **lease** hoặc kiểm soát tranh chấp nếu chạy nhiều instance.
3. Gửi message; giữ eventId ổn định trong payload hoặc messageId.
4. Ghép kết quả bằng **publishAttemptId**.
5. Chỉ đánh dấu **CONFIRMED** khi nhận publisher ACK và không có return trong cấu hình đã quy định.
6. Nếu UNKNOWN/NACKED, giữ record để retry hữu hạn với backoff.
7. Nếu UNROUTABLE, điều tra topology rồi replay.

Nếu crash trước send, outbox vẫn còn. Nếu broker đã nhận nhưng confirm bị mất, outbox còn và dispatcher sẽ gửi lại; vì thế **consumer vẫn phải idempotent**.

### 9.3. Callback đến muộn không được ghi đè attempt mới

Giả sử attempt 1 timeout; dispatcher bắt đầu attempt 2; sau đó confirm attempt 1 đến muộn. Nếu callback chỉ cập nhật theo eventId, nó có thể ghi đè trạng thái của attempt mới.

Dùng cập nhật có điều kiện, ví dụ:

~~~sql
UPDATE outbox_event
SET status = 'CONFIRMED'
WHERE event_id = :eventId
  AND last_attempt_id = :attemptId
  AND status IN ('IN_FLIGHT', 'UNKNOWN');
~~~

Nếu không có dòng nào được cập nhật, callback có thể đã quá hạn hoặc thuộc attempt cũ. Ghi log/metric phù hợp, không ghi đè vô điều kiện.

**Việc bỏ qua callback cũ không chứng minh attempt đó chưa được broker nhận.** Đây là lý do dedup phải được thực thi ở consumer. Trong hệ thống nhiều dispatcher, cần thêm version/lease để xử lý các race condition ngoài phạm vi ví dụ.

## 10. Consumer idempotent khi publisher gửi lại

RabbitMQ không mặc định loại bỏ các message trùng nhau theo **messageId**. Hai publish của cùng eventId có thể dẫn đến hai delivery.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant Q as Queue
    participant C as Billing consumer
    participant DB as Database
    P->>Q: evt-101 attempt 1
    P->>Q: evt-101 attempt 2
    Q->>C: Delivery 1
    C->>DB: Transaction: marker evt-101 + invoice
    C->>Q: ACK
    Q->>C: Delivery 2
    C->>DB: evt-101 đã xử lý
    C->>Q: ACK, không tạo hóa đơn mới
~~~

Phía consumer có thể dùng bảng **processed_event** với unique constraint theo eventId, hoặc theo cặp **consumerGroup + eventId** nếu một event được nhiều nhóm xử lý độc lập.

Quy trình xử lý:

1. Mở transaction.
2. Kiểm tra/ghi marker idempotency có ràng buộc duy nhất.
3. Nếu đã xử lý, bỏ qua tác dụng phụ và trả thành công để ACK.
4. Nếu chưa, thực hiện nghiệp vụ và ghi marker trong cùng transaction.
5. Commit xong mới ACK theo cơ chế container.

Ví dụ ranh giới listener:

~~~java
import java.nio.charset.StandardCharsets;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class BillingListener {
    private final BillingService billingService;

    public BillingListener(BillingService billingService) {
        this.billingService = billingService;
    }

    @RabbitListener(queues = ConfirmDemoTopology.QUEUE)
    public void onOrderPlaced(Message message) {
        if (!MessageProperties.CONTENT_TYPE_JSON.equals(
                message.getMessageProperties().getContentType())) {
            throw new IllegalArgumentException("Expected JSON payload");
        }
        // Hợp đồng của demo quy định body JSON ở UTF-8.
        String jsonPayload = new String(
                message.getBody(), StandardCharsets.UTF_8);

        // Service phải parse eventId, validate JSON
        // rồi xử lý transaction + idempotency.
        billingService.processIdempotently(jsonPayload);
    }
}
~~~

**BillingService** là service nghiệp vụ cần tự triển khai. Listener nhận raw **Message** để đọc JSON bytes theo UTF-8; nếu sử dụng JSON MessageConverter được cấu hình ở cả producer/consumer, cũng có thể cho listener nhận DTO phù hợp.

Với tác dụng phụ sang hệ thống ngoài như thanh toán, chỉ ghi marker vào DB rồi gọi HTTP không tự bảo đảm an toàn nếu crash giữa hai bước. Cần dùng idempotency key của hệ thống bên ngoài hoặc thiết kế workflow/outbox bổ sung.

## 11. Retry có giới hạn và phân loại lỗi

Không nên retry mọi trường hợp theo cùng một lịch.

| Kết quả | Hướng xử lý |
|---|---|
| **UNKNOWN** | Giữ outbox, tạo attemptId mới, retry cùng eventId |
| **NACKED** | Đọc reason, retry có giới hạn hoặc cảnh báo |
| **UNROUTABLE / NO_ROUTE** | Kiểm tra routing key, binding, exchange, virtual host, quyền; sửa rồi replay |
| **Exchange không tồn tại** | Điều tra topology và channel exception, không lặp publish vô hạn |
| **Resource alarm / broker quá tải** | Giảm số in-flight, backoff, theo dõi disk/memory/network |
| **CONFIRMED** | Đánh dấu bước publish hoàn tất; không suy ra consumer đã ACK |

Ví dụ lịch retry mang tính tham khảo:

~~~text
Attempt 1: gửi
Attempt 2: sau 5 giây + jitter
Attempt 3: sau 30 giây + jitter
Attempt 4: sau 2 phút + jitter
Sau ngưỡng: NEEDS_ATTENTION, giữ event và báo vận hành
~~~

Dùng **exponential backoff**, **jitter**, giới hạn concurrent attempts và số lần thử để tránh nhiều instance đồng loạt dồn vào broker khi hồi phục. Giữ nguyên **eventId và payload đã commit**, không sinh một event mới cho mỗi lần gửi lại.

Một số ứng dụng cần giữ event ở trạng thái cần can thiệp thay vì xóa record UNKNOWN sau vài lần thử. Quyết định retention và replay phải dựa vào yêu cầu nghiệp vụ.

## 12. Publisher confirm và độ bền dữ liệu

Mức độ bảo đảm còn phụ thuộc topology:

- **Persistent message + durable queue:** Confirm được phát theo điều kiện broker lưu bền vững thích hợp, khác với trường hợp chỉ gửi vào queue không durable.
- **Quorum queue:** Confirm phản ánh cơ chế chấp nhận/replication của quorum; producer không cần tự suy từ số consumer.
- **Message transient hoặc queue không bền vững:** Confirm không biến message thành an toàn trước mọi lần broker restart.
- **Một exchange định tuyến vào nhiều queue:** Broker cần xử lý message theo semantics của các queue được route tới trước khi xác nhận.

Vì thế, thiết kế đáng tin cậy cần phối hợp **queue type, durable, persistent delivery mode, publisher confirm/return, retry, consumer ACK và idempotency**.

**Publisher confirms không đảm bảo exactly-once business processing.** Mất confirm khiến publisher phải retransmit; broker có thể giao trùng. Consumer ACK cũng có thể bị mất sau khi nghiệp vụ đã commit.

## 13. Bài thực hành có thể quan sát được

### 13.1. ACK bình thường

1. Bật cấu hình confirms/returns/mandatory ở mục 4.
2. Tạo topology mục 6, publish eventId **evt-ok-1** với routing key **order.placed**.
3. Quan sát future hoàn tất bằng confirm ACK và getReturn là null.
4. Kiểm tra message đi vào queue; nếu có consumer, quan sát kết quả xử lý.
5. Ghi rõ **publisher ACK** và **consumer ACK** là hai loại kết quả khác nhau.

### 13.2. Unroutable nhưng vẫn có ACK

1. Publish vào exchange hợp lệ với key **order.unknown**.
2. Không khai báo binding cho key này.
3. Quan sát return **312 NO_ROUTE** khi mandatory=true.
4. Quan sát publisher ACK có thể đến sau return.
5. Xác minh app ghi **UNROUTABLE**, không đánh dấu CONFIRMED.

### 13.3. Exchange không tồn tại

1. Publish đến exchange **orders.missing.exchange** chưa khai báo.
2. Quan sát channel error và nguyên nhân; correlated future có thể nhận NACK/framework error.
3. Đừng nhầm với NO_ROUTE trên exchange đang tồn tại.
4. Giữ event ở outbox để sửa topology và gửi lại có kiểm soát.

### 13.4. Mất kết nối trước confirm

1. Trong môi trường test, lưu outbox eventId **evt-ambiguous-1** trước khi gửi.
2. Gián đoạn connection trong lúc publish, cố gắng tái hiện trạng thái chưa có confirm.
3. Nếu chưa quan sát được kết quả, ghi **UNKNOWN**, không khẳng định message đã mất.
4. Reconnect và gửi lại cùng eventId, với CorrelationData attempt mới.
5. Quan sát consumer có thể nhận một hoặc nhiều bản sao tùy thời điểm lỗi.
6. Kiểm tra idempotency: tác dụng phụ chỉ được áp dụng một lần.

Thử nghiệm này phụ thuộc timing. Nếu confirm đến trước khi ngắt mạng, ghi nhận kết quả đó; không suy ra cơ chế UNKNOWN bị lỗi.

### 13.5. Confirm đến chậm

1. Tạo một hàng đợi phù hợp để kiểm thử và đặt ngưỡng chờ confirm ngắn.
2. Gây độ trễ mạng/broker trong môi trường test có kiểm soát.
3. Quan sát future có thể chưa xong trong khoảng chờ rồi hoàn tất sau.
4. Đảm bảo callback cũ không ghi đè attempt mới.
5. Theo dõi confirm latency và tần suất UNKNOWN thay vì retry vô hạn.

## 14. Metrics và xử lý sự cố

| Chỉ số hoặc log | Câu hỏi cần trả lời |
|---|---|
| **publisher_confirm_ack_total** | Broker ACK bao nhiêu attempt? |
| **publisher_confirm_nack_total** | Có bao nhiêu NACK? |
| **publisher_return_total** | Bao nhiêu message NO_ROUTE? |
| **publisher_unknown_total** | Bao nhiêu attempt timeout/mất kết nối? |
| **publisher_confirm_latency** | Bao lâu mới có confirm? |
| **outbox_pending / oldest_age** | Event chưa hoàn tất đã chờ bao lâu? |
| **publish_retry_total** | Có đang retry quá nhanh? |
| **consumer_duplicate_skipped_total** | Idempotency đã bỏ qua bao nhiêu bản sao? |
| **Ready, Unacked, Consumers** | Queue có backlog hoặc worker bị kẹt? |
| **DLQ depth** | Có lỗi nghiệp vụ/định dạng kéo dài? |

Ví dụ log có cấu trúc:

~~~text
eventId=evt-101
attemptId=evt-101:2
exchange=orders.confirm-demo
routingKey=order.placed
outcome=UNKNOWN
reason=confirm_timeout
elapsedMs=10000
~~~

Log **eventId, attemptId, exchange, routing key, return reason, confirm latency**, nhưng tránh ghi nguyên payload chứa thông tin cá nhân hoặc dữ liệu nhạy cảm. Nếu UNKNOWN tăng, xem network, disk I/O, resource alarms, queue type, số message in-flight và timeout trước khi tăng tốc độ retry.

## 15. Lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Timeout nghĩa là broker chưa nhận | Có thể gửi trùng khi retry | Dùng UNKNOWN và consumer idempotent |
| Timeout nghĩa là broker đã nhận | Có thể bỏ sót event | Giữ outbox cho đến khi xác nhận |
| ACK của publisher nghĩa là consumer đã xử lý | Nhầm phạm vi xác nhận | Tách confirm và consumer ACK |
| Chỉ kiểm tra confirm.isAck() | Bỏ qua NO_ROUTE | Kiểm tra cả CorrelationData.getReturn() |
| Không bật mandatory/returns | Unroutable có thể bị loại mà không báo | Bật returns + mandatory cùng confirms |
| Retry sinh eventId mới | Dedup không nhận ra bản sao | Giữ eventId, đổi attemptId |
| Chỉ lưu pending event trong RAM | Crash làm mất ý định gửi | Transactional outbox |
| Publish trong DB @Transactional rồi tin là atomic | DB và broker không cùng một transaction | Transactional outbox |
| Callback cũ ghi đè attempt mới | Sai trạng thái publish | Cập nhật có điều kiện theo attempt |
| Retry NO_ROUTE liên tục | Lặp lỗi cấu hình | Sửa topology trước khi replay |
| Consumer không có idempotency | Tác dụng phụ bị lặp | Unique constraint và transaction |
| Đợi confirm đồng bộ từng message khi tải cao | Throughput thấp | Async future/callback và outbox dispatcher |

## 16. Câu hỏi tự đánh giá

1. Broker đã nhận message nhưng confirm ACK bị mất. Publisher có thể xác minh chắc chắn kết quả bằng cách đọc số Ready của queue không? Vì sao?
2. Với confirm ACK và mandatory return NO_ROUTE, trạng thái đúng là CONFIRMED hay UNROUTABLE?
3. Vì sao publisher confirm và consumer ACK không thay thế được nhau?
4. Tại sao eventId cần giữ nguyên khi retry, còn CorrelationData.id nên đổi theo attempt?
5. Nếu callback confirm của attempt 1 đến sau khi attempt 2 bắt đầu, phải làm gì để tránh cập nhật sai outbox?
6. Transactional outbox giúp tránh mất event ở cửa sổ lỗi nào giữa database commit và publish?
7. Nếu consumer nhận hai delivery cùng eventId, cần thiết kế transaction và unique constraint ra sao để chỉ tạo một hóa đơn?
8. Tại sao retry khi gặp NO_ROUTE mà không thay đổi binding thường không có ích?

### Bài tập áp dụng

Hãy thiết kế dịch vụ phát **OrderPlaced** với các trường **eventId, orderId, createdAt**. Lưu order và outbox trong cùng database transaction; dispatcher gửi JSON với messageId=eventId; cập nhật trạng thái theo correlated confirm/return; retry UNKNOWN có backoff; consumer Billing dùng eventId để idempotent. Mô phỏng mất connection đúng lúc publish và ghi lại ít nhất hai khả năng hợp lệ: **message chưa đến broker** hoặc **message đã đến nhưng confirm bị mất**.

## 17. Những điều cần nhớ

- **Publisher ACK** là broker xác nhận xử lý publish, **không** chứng minh business consumer hoàn tất.
- **Mandatory return** có thể đi cùng publisher ACK; producer phải xem **cả confirm và return**.
- **Timeout hoặc mất connection trước confirm để lại kết quả có thể chưa xác định**. Không được tự kết luận chắc chắn thành công/thất bại.
- **CorrelationData** liên kết một publish attempt với confirm/return; **eventId** ổn định qua retry.
- **Transactional outbox** giúp không mất ý định phát sự kiện khi process crash hoặc mất connection.
- **Consumer idempotent** giải quyết khả năng duplicate khi producer gửi lại message chưa được xác nhận.
- Thiết kế tin cậy cần đồng thời **RabbitTemplate**, **@RabbitListener**, exchange/queue/binding, publisher confirms/returns, ACK, retry, dead-letter và quan sát.

### Tài liệu tham khảo chính thức

- [RabbitMQ — Publisher Confirms](https://www.rabbitmq.com/docs/confirms): ACK/NACK publisher và giới hạn phạm vi xác nhận.
- [RabbitMQ — Reliability Guide](https://www.rabbitmq.com/docs/reliability): mất confirm, retransmit và deduplication.
- [RabbitMQ — Publishers](https://www.rabbitmq.com/docs/publishers): xử lý lỗi mạng và confirm timeout.
- [Spring AMQP — Correlated Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html): CorrelationData, future và return.
- [RabbitMQ — Reliable Publishing with Publisher Confirms](https://www.rabbitmq.com/tutorials/tutorial-seven-java): phương án chờ confirm và xử lý bất đồng bộ.
