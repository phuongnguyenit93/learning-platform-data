# Đối soát thông điệp, dữ liệu nghiệp vụ và tác vụ bị bỏ dở

## 1. Vấn đề: đã gửi message nhưng công việc có thực sự hoàn thành?

Khi tích hợp **RabbitMQ với Spring AMQP**, chúng ta dùng `RabbitTemplate` để publish, **exchange–queue–binding** để định tuyến, `@RabbitListener` để nhận và xử lý, publisher confirm để theo dõi broker nhận message, retry/DLQ để xử lý lỗi. Tuy nhiên, ngay cả khi đã cấu hình đủ các cơ chế này, một giao dịch nghiệp vụ vẫn có thể bị **bỏ dở**:

- Đơn hàng đã thanh toán nhưng sự kiện `order.paid` chưa từng được publish.
- Sự kiện đã được broker xác nhận nhưng không tới queue phù hợp vì routing sai.
- Message tới consumer; consumer tạo tác vụ rồi chết trước ACK, khiến message được giao lại.
- Consumer ACK thành công, nhưng một tác vụ bất đồng bộ được tạo ra sau đó bị kẹt ở trạng thái `RUNNING`.
- Message nằm trong DLQ nhiều giờ mà không ai xử lý; nghiệp vụ nguồn vẫn kỳ vọng kết quả.
- Dịch vụ đích hoạt động bình thường nhưng dữ liệu của nó thiếu một số tác vụ tương ứng với dữ liệu nguồn.

**Độ tin cậy đầu cuối** không chỉ là “publish thành công” hoặc “queue đã rỗng”. Nó đòi hỏi kiểm tra xem **trạng thái nghiệp vụ cần có** có thực sự xuất hiện, có đúng một hiệu ứng nghiệp vụ theo định danh logic hay không, và những công việc chưa hoàn tất có được phát hiện, khôi phục an toàn.

Trong bài này, **đối soát (reconciliation)** là quá trình định kỳ so sánh **dấu vết bền vững ở những điểm khác nhau** của luồng xử lý, xác định sai lệch và thực hiện hành động phục hồi có kiểm soát.

Sau bài học, bạn có thể:

1. Nhận diện chỗ thất bại giữa database, `RabbitTemplate`, RabbitMQ, `@RabbitListener` và tác vụ nền.
2. Thiết kế **transactional outbox**, **idempotent inbox**, trạng thái công việc và định danh tương quan để có căn cứ đối soát.
3. Phân biệt publisher confirm, publisher return, consumer ACK và xác nhận **nghiệp vụ hoàn tất**.
4. Phát hiện sự kiện chưa publish, kết quả nghiệp vụ bị thiếu, bản ghi trong DLQ và tác vụ hết lease.
5. Xây tiến trình quét, retry, redrive và cảnh báo mà không gây tác dụng phụ trùng lặp.

## 2. Xác định điều kiện hoàn thành theo nghiệp vụ

Giả sử hệ thống có hai dịch vụ:

- **Order Service** lưu trạng thái thanh toán. Khi đơn hàng `PAID`, phải phát sự kiện `order.paid`.
- **Fulfillment Service** nhận sự kiện và tạo tác vụ giao hàng tương ứng.

~~~text
                      ORDER SERVICE (DB A)
                         orders.status=PAID
                                  |
                     cùng DB transaction
                                  v
                         outbox_events
                                  |
                          outbox dispatcher
                                  |
                                  v
      RabbitTemplate --> exchange orders.events.x
                                  |
                                binding
                                  |
                                  v
                          queue fulfillment.q
                                  |
                                  v
                    @RabbitListener (DB B transaction)
                        +------------------+
                        | consumer_inbox   | <- eventId chống xử lý trùng
                        | fulfillment_task | <- mục tiêu nghiệp vụ
                        +------------------+
                                  |
                             task worker
                                  |
                         DONE / FAILED / RETRY
                                  |
                                  v
                  Reconciler kiểm tra đầu cuối
        orders + outbox + inbox + task + DLQ + metrics
~~~

Với đơn hàng đã thanh toán, tiêu chí hoàn thành có thể là **Fulfillment Service có một tác vụ giao hàng đã tạo và cuối cùng đạt trạng thái kết thúc hợp lệ**. Tiêu chí này cụ thể hơn “RabbitMQ báo confirm” hay “message không còn trong queue”.

Trước khi lập lịch đối soát, cần làm rõ:

| Khái niệm | Ví dụ | Cách dùng |
| --- | --- | --- |
| **Sự thật nguồn (source of truth)** | Đơn hàng `PAID` trong DB A. | Xác định nghiệp vụ yêu cầu hành động gì. |
| **Dấu vết giao phát** | Bản ghi outbox và trạng thái publish. | Biết thông điệp nào đã sẵn sàng/đang gửi/được broker confirm. |
| **Dấu vết tiêu thụ** | Inbox lưu `eventId` đã xử lý trong DB B. | Chống thực thi trùng khi RabbitMQ redeliver. |
| **Kết quả nghiệp vụ** | `fulfillment_task` tương ứng. | Biết yêu cầu đã thành công, đang làm hay thất bại. |
| **Ngoại lệ cần điều tra** | DLQ, task quá hạn, khoảng trống dữ liệu. | Phát hiện và điều phối phục hồi. |

Một số tác vụ cho phép **eventual consistency**: kết quả đích xuất hiện sau nguồn vài giây hoặc vài phút. Vì vậy, không đối chiếu mọi record “chưa có” tại thời điểm tạo; cần có **khoảng chờ (grace period)**, deadline và watermark thích hợp để tránh báo lỗi giả.

## 3. Những khoảng trống thường gặp trong vòng đời thông điệp

Một luồng bình thường có thể trải qua:

~~~text
T1: DB nguồn commit "PAID"
T2: Publisher lấy outbox
T3: RabbitTemplate publish
T4: Broker publisher confirm / return (nếu cấu hình)
T5: Broker route đến queue
T6: Listener nhận delivery
T7: DB đích commit inbox + task
T8: Consumer ACK delivery
T9: Worker thực thi task, ghi DONE
~~~

**Mỗi cặp mốc liền nhau đều có rủi ro thất bại.** Ví dụ:

| Khoảng trống | Sự cố | Hậu quả | Cơ chế phát hiện/phục hồi |
| --- | --- | --- | --- |
| T1 → T2 | Publish trực tiếp sau DB commit nhưng tiến trình chết. | Có dữ liệu nguồn, thiếu message. | Outbox ghi cùng transaction; đối soát các sự kiện còn thiếu. |
| T2 → T4 | Producer không nhận confirm, mất kết nối. | Không biết broker đã nhận hay chưa. | Retry với cùng `eventId`; consumer idempotent. |
| T4 → T5 | Broker nhận publish nhưng message không routable. | Có confirm, queue đích có thể không nhận. | Mandatory + publisher returns; kiểm tra topology. |
| T5 → T6 | Consumer tạm dừng hoặc backlog. | Xử lý trễ, queue tăng. | Queue depth, consumer lag, deadline nghiệp vụ. |
| T7 → T8 | DB đích commit, consumer chết trước ACK. | Message có thể được giao lại. | Inbox unique `eventId`; xử lý lặp an toàn. |
| T8 → T9 | Tác vụ được tạo nhưng worker không thực thi/đang bị kẹt. | ACK đã có, nghiệp vụ chưa hoàn thành. | Bảng task, lease, timeout, đối soát trạng thái. |
| Bất kỳ bước xử lý | Message bị dead-letter. | Lỗi chưa được giải quyết. | DLQ monitoring, phân loại và redrive có kiểm soát. |

Không thể kết luận hoàn thành đầu cuối chỉ từ **publisher confirm**: confirm chủ yếu xác nhận broker đã xử lý publish theo cơ chế confirm. **Consumer ACK** chỉ xác nhận một delivery đã được consumer/container xử lý theo cấu hình ACK, không chứng minh mọi side effect ngoài consumer đã đạt trạng thái cuối. **Độ sâu queue bằng 0** cũng có thể xuất hiện khi mọi message đã được ACK nhưng tác vụ nền bị kẹt.

## 4. Xây nền tảng để đối soát: eventId và transaction outbox

### 4.1. Mỗi thay đổi nghiệp vụ quan trọng cần một dấu vết bền vững

Trong Order Service, cập nhật đơn hàng và tạo sự kiện outbox phải nằm **cùng một database transaction**. Nếu transaction rollback, cả hai biến mất; nếu commit, luôn có dấu vết có thể phát lại.

Ví dụ schema **PostgreSQL** minh họa:

~~~sql
CREATE TABLE orders (
    order_id         UUID PRIMARY KEY,
    payment_status   VARCHAR(20) NOT NULL,
    paid_at          TIMESTAMPTZ,
    paid_event_id    UUID UNIQUE
);

CREATE TABLE outbox_events (
    event_id         UUID PRIMARY KEY,
    aggregate_type   VARCHAR(50) NOT NULL,
    aggregate_id     UUID NOT NULL,
    event_type       VARCHAR(100) NOT NULL,
    payload_json     TEXT NOT NULL,
    status           VARCHAR(20) NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner      VARCHAR(100),
    lease_until      TIMESTAMPTZ,
    published_at     TIMESTAMPTZ,
    last_error       TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_outbox_status CHECK
        (status IN ('PENDING', 'SENDING', 'PUBLISHED', 'FAILED'))
);

CREATE INDEX idx_outbox_dispatch
    ON outbox_events (status, next_attempt_at, lease_until);
~~~

Ở đây `paid_event_id` gắn **một lần chuyển sang PAID** với một event riêng, hỗ trợ đối soát. Nếu nghiệp vụ có thể thanh toán lại/hoàn tiền nhiều lần, nên lưu lịch sử chuyển trạng thái hoặc payment transaction ID thay vì giả định đơn hàng chỉ có một event mãi mãi.

Một phương thức cập nhật nguồn có thể sử dụng `@Transactional`:

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentApplicationService {
    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;

    public PaymentApplicationService(OrderRepository orderRepository,
                                     OutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional
    public void markPaid(UUID orderId) {
        // Repository nghiệp vụ phải kiểm tra chuyển trạng thái hợp lệ
        // và tránh tạo event mới nếu đơn đã PAID.
        if (!orderRepository.markPaidOnce(orderId)) {
            return;
        }

        UUID eventId = UUID.randomUUID();
        orderRepository.setPaidEventId(orderId, eventId);
        outboxRepository.insertOrderPaid(
                eventId, orderId, Instant.now());
    }
}
~~~

**OrderRepository** và **OutboxRepository** là lớp ứng dụng cần triển khai, không phải thành phần có sẵn của Spring AMQP. Chúng phải dùng **cùng DataSource/transaction manager** để cả cập nhật order và insert outbox commit/rollback nguyên tử. Phương thức `markPaidOnce` cần kiểm tra trạng thái bằng một thao tác update có điều kiện hoặc khóa phù hợp để tránh hai luồng cùng phát sự kiện.

**Không publish vào RabbitMQ ngay giữa transaction rồi coi đó là commit nguyên tử**: RabbitMQ và database thường không nằm trong một distributed transaction. Transactional outbox tách việc ghi dấu vết bền vững khỏi thời điểm phát message.

### 4.2. Không coi một lần publish là một trạng thái cuối đáng tin cậy

Outbox có thể chuyển trạng thái như sau:

~~~text
PENDING --claim lease--> SENDING --confirm ACK, routable--> PUBLISHED
                            |
                            +-- NACK / returned / timeout --> PENDING (retry)
                            |
                            +-- lease hết hạn sau crash ------> reclaim
                            |
                            +-- lỗi không thể tự hồi phục ----> FAILED + alert
~~~

Để nhiều dispatcher chạy song song, nên **claim batch bằng thao tác DB nguyên tử**, có `lease_owner`/`lease_until`, thay vì mọi instance đều đọc cùng các row `PENDING` rồi gửi trùng. Ví dụ SQL PostgreSQL:

~~~sql
WITH candidates AS (
    SELECT event_id
      FROM outbox_events
     WHERE (status = 'PENDING' AND next_attempt_at <= now())
        OR (status = 'SENDING' AND lease_until < now())
     ORDER BY created_at
     FOR UPDATE SKIP LOCKED
     LIMIT 100
)
UPDATE outbox_events o
   SET status = 'SENDING',
       lease_owner = :worker_token,
       lease_until = now() + interval '30 seconds',
       attempts = attempts + 1
  FROM candidates c
 WHERE o.event_id = c.event_id
RETURNING o.*;
~~~

Phải commit claim transaction **trước khi gửi mạng**; không giữ khóa database trong lúc chờ publisher confirm. `:worker_token` là định danh **duy nhất cho lần claim** (không chỉ hostname), để một callback đến muộn không cập nhật row đã được worker khác claim lại. Khi sửa trạng thái, dùng điều kiện `event_id = ? AND lease_owner = ? AND status = 'SENDING'`. Query trên là ví dụ dành cho PostgreSQL; hệ DB khác có cú pháp locking khác.

**Lease hết hạn không chứng minh message chưa được publish.** Nó chỉ nói worker cũ không còn sở hữu hợp đồng xử lý hợp lệ; nếu publish đã thành công nhưng không ghi kịp `PUBLISHED`, retry có thể tạo message trùng. Do đó phải giữ `eventId` bất biến xuyên suốt mọi lần thử.

## 5. Spring AMQP publisher confirm, return và giới hạn bằng chứng

Muốn biết publish xảy ra ở bước nào, Spring Boot có thể bật:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Để minh họa đường đi của message, khai báo **exchange, queue, binding** và dead-letter queue bằng Spring AMQP. Queue dead-letter chỉ nhận message khi cơ chế reject/TTL/dead-letter thực sự kích hoạt; riêng việc khai báo DLX không tự giới hạn retry vô hạn của listener.

~~~java
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderEventTopology {
    @Bean
    DirectExchange ordersEventsExchange() {
        return new DirectExchange("orders.events.x", true, false);
    }

    @Bean
    Queue fulfillmentQueue() {
        return QueueBuilder.durable("fulfillment.q")
                .deadLetterExchange("fulfillment.dead.x")
                .deadLetterRoutingKey("order.paid.failed")
                .build();
    }

    @Bean
    Binding fulfillmentBinding(Queue fulfillmentQueue,
                               DirectExchange ordersEventsExchange) {
        return BindingBuilder.bind(fulfillmentQueue)
                .to(ordersEventsExchange)
                .with("order.paid");
    }

    @Bean
    DirectExchange fulfillmentDeadExchange() {
        return new DirectExchange("fulfillment.dead.x", true, false);
    }

    @Bean
    Queue fulfillmentDeadQueue() {
        return QueueBuilder.durable("fulfillment.dead.q").build();
    }

    @Bean
    Binding fulfillmentDeadBinding(Queue fulfillmentDeadQueue,
                                   DirectExchange fulfillmentDeadExchange) {
        return BindingBuilder.bind(fulfillmentDeadQueue)
                .to(fulfillmentDeadExchange)
                .with("order.paid.failed");
    }
}
~~~

Một dispatcher minh họa gắn cùng `eventId` vào **CorrelationData** và message:

~~~java
import org.springframework.amqp.core.MessageDeliveryMode;
import org.springframework.amqp.rabbit.connection.CorrelationData;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class OutboxMessagePublisher {
    private final RabbitTemplate rabbitTemplate;
    private final OutboxStatusService statusService;

    public OutboxMessagePublisher(RabbitTemplate rabbitTemplate,
                                  OutboxStatusService statusService) {
        this.rabbitTemplate = rabbitTemplate;
        this.statusService = statusService;
    }

    public void publish(ClaimedEvent event) {
        CorrelationData correlation = new CorrelationData(event.eventId());

        try {
            rabbitTemplate.convertAndSend(
                    "orders.events.x", "order.paid", event.payloadJson(),
                    message -> {
                        message.getMessageProperties()
                                .setMessageId(event.eventId());
                        message.getMessageProperties()
                                .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
                        return message;
                    },
                    correlation
            );
        } catch (RuntimeException error) {
            statusService.scheduleRetryIfLeaseMatches(
                    event.eventId(), event.leaseToken(),
                    "Publish failed before confirm");
            return;
        }

        correlation.getFuture().whenComplete((confirm, error) -> {
            if (error != null || confirm == null || !confirm.isAck()
                    || correlation.getReturned() != null) {
                statusService.scheduleRetryIfLeaseMatches(
                        event.eventId(), event.leaseToken(),
                        "Broker NACK, unroutable or confirm failure");
            } else {
                statusService.markPublishedIfLeaseMatches(
                        event.eventId(), event.leaseToken());
            }
        });
    }
}
~~~

**ClaimedEvent** là DTO chứa `eventId`, `payloadJson`, `leaseToken`; **OutboxStatusService** là service do ứng dụng triển khai. Các phương thức thay đổi trạng thái phải mở **transaction DB riêng** và có điều kiện kiểm tra lease. Ví dụ rút gọn cho dễ học; production cần log nguyên nhân thật, giữ `next_attempt_at` với backoff, kiểm soát số publish đang chờ confirm và xử lý trường hợp callback không xuất hiện trước khi lease hết hạn.

Các điểm then chốt:

- **Confirm ACK** nói broker đã chấp nhận/xử lý publish theo publisher confirms, **không** nói worker đã xử lý nghiệp vụ.
- **Return** cho biết một publish bị coi là không định tuyến được khi dùng `mandatory=true` và publisher returns; một publish có thể được **confirm ACK nhưng vẫn bị return**. Cần kiểm tra cả hai.
- `CorrelationData.getReturned()` phản ánh returned message khi callback return/correlation được cấu hình phù hợp. Không tự động xem `confirm.isAck()` là thành công nếu chưa xét trường hợp return.
- `MessageDeliveryMode.PERSISTENT`, exchange/queue durable và publisher confirm góp phần tăng độ tin cậy; vẫn cần kiểm thử broker crash, failover và loại queue được chọn.
- Nếu callback thành công nhưng cập nhật outbox thất bại, dispatcher có thể publish lại. **Inbox idempotent** là hàng phòng vệ ở phía nhận.

Publisher confirm chưa bao phủ việc message bị reject vì payload lỗi **sau khi** đã tới queue. Lúc này cần quan sát consumer, DLQ và trạng thái nghiệp vụ.

## 6. Consumer lưu inbox và tạo kết quả trong cùng transaction

Trong Fulfillment Service, thiết kế DB riêng như sau:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name  VARCHAR(100) NOT NULL,
    event_id       UUID NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE fulfillment_task (
    task_id          UUID PRIMARY KEY,
    source_event_id  UUID NOT NULL UNIQUE,
    order_id         UUID NOT NULL UNIQUE,
    status           VARCHAR(20) NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner      VARCHAR(100),
    lease_until      TIMESTAMPTZ,
    last_error       TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_fulfillment_status CHECK
        (status IN ('READY', 'RUNNING', 'DONE', 'FAILED'))
);
~~~

`source_event_id` và `order_id` cần unique phù hợp với quy tắc nghiệp vụ. Nếu đơn hàng được phép có nhiều lần tạo task hợp lệ, phải đổi khóa unique thành **business operation ID** chính xác, tránh vô tình chặn một công việc hợp lệ.

Mẫu xử lý:

~~~java
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class FulfillmentApplicationService {
    private final InboxRepository inboxRepository;
    private final FulfillmentTaskRepository taskRepository;

    public FulfillmentApplicationService(InboxRepository inboxRepository,
                                         FulfillmentTaskRepository taskRepository) {
        this.inboxRepository = inboxRepository;
        this.taskRepository = taskRepository;
    }

    @Transactional
    public void acceptOrderPaid(UUID eventId, UUID orderId) {
        // INSERT ... ON CONFLICT DO NOTHING tại DB PostgreSQL.
        // Chỉ luồng INSERT thành công mới tạo task.
        if (!inboxRepository.insertIfAbsent("fulfillment", eventId)) {
            return;
        }
        taskRepository.insertReadyIfAbsent(eventId, orderId);
    }
}
~~~

Ở mức RabbitMQ:

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPaidListener {
    private final FulfillmentApplicationService fulfillment;
    private final OrderPaidPayloadDecoder decoder;

    public OrderPaidListener(FulfillmentApplicationService fulfillment,
                             OrderPaidPayloadDecoder decoder) {
        this.fulfillment = fulfillment;
        this.decoder = decoder;
    }

    @RabbitListener(queues = "fulfillment.q")
    public void handle(String payloadJson) {
        OrderPaidPayload event = decoder.decode(payloadJson);
        fulfillment.acceptOrderPaid(
                event.eventId(), event.orderId());
    }
}
~~~

**OrderPaidPayload**, **OrderPaidPayloadDecoder** và hai repository là thành phần minh họa cần triển khai theo schema/JSON converter của ứng dụng. Không có các class này trong thư viện Spring AMQP. Ví dụ giả định listener container dùng **AUTO ACK** mặc định, việc gọi service kết thúc thành công sau khi transaction DB commit thì container mới xác nhận message.

Đường lỗi có hai trường hợp:

1. **DB rollback trước khi ACK:** message có thể được retry/redeliver, inbox insert cũng rollback, do đó vẫn có cơ hội tạo task.
2. **DB commit rồi tiến trình chết trước ACK:** message được giao lại, inbox phát hiện `eventId` đã tồn tại và trả về không tạo task trùng.

**Không tự ACK trước khi transaction DB hoàn tất** nếu muốn dựa vào redelivery để phục hồi lỗi ghi DB. Dù vậy, không có giao dịch nguyên tử xuyên DB và RabbitMQ chỉ bằng `@Transactional`; outbox/inbox xử lý các khoảng trống theo kiểu **at-least-once** và idempotency.

Nếu consumer throw exception vì dữ liệu hỏng, default requeue vô hạn có thể tạo poison loop. Cần thiết lập retry giới hạn và **DLX/DLQ** với quy tắc loại lỗi rõ ràng. Không coi việc một message đã vào inbox là bằng chứng tác vụ đã chạy xong: inbox chỉ đánh dấu **bước tiếp nhận thành công**, còn bảng task là nơi theo dõi xử lý dài hơn.

## 7. Đối soát ba nhóm sai lệch

Một bộ đối soát nên chia theo **nguyên nhân và bước xử lý thiếu**, không chỉ nhìn số lượng message.

### 7.1. Sự kiện nguồn bị thiếu hoặc chưa publish

Trường hợp: đơn hàng có `payment_status='PAID'`, nhưng `paid_event_id` trống hoặc không tìm thấy event ở outbox.

~~~sql
-- PostgreSQL; grace period 2 phút chỉ là giá trị minh họa.
SELECT o.order_id, o.paid_event_id, o.paid_at
  FROM orders o
  LEFT JOIN outbox_events e
    ON e.event_id = o.paid_event_id
 WHERE o.payment_status = 'PAID'
   AND o.paid_at < now() - interval '2 minutes'
   AND (o.paid_event_id IS NULL OR e.event_id IS NULL);
~~~

Với thiết kế outbox nguyên tử đúng, truy vấn này **thường trả về 0 dòng**. Nếu có kết quả, nguyên nhân có thể là dữ liệu legacy, migration lỗi, công việc viết sai transaction, sửa dữ liệu thủ công hoặc bug. Không tự phát một event mới nếu chưa xác định **định danh thao tác nguồn và tính hợp lệ hiện tại**.

Trường hợp tiếp theo: outbox vẫn `PENDING` quá lâu, `SENDING` quá lease, hoặc `FAILED`. Query nhóm này dễ hơn:

~~~sql
SELECT event_id, aggregate_id, status,
       attempts, created_at, lease_until, last_error
  FROM outbox_events
 WHERE (status = 'PENDING'
           AND next_attempt_at < now() - interval '5 minutes')
    OR (status = 'SENDING' AND lease_until < now())
    OR status = 'FAILED'
 ORDER BY created_at
 LIMIT 200;
~~~

Chú ý: `next_attempt_at` có thể cố ý đặt trong tương lai vì backoff. Đừng cảnh báo “quá hạn” nếu lịch retry vẫn hợp lệ; cần đối chiếu cả **business deadline** và **attempt policy**.

### 7.2. Broker nhận nhưng dịch vụ đích thiếu kết quả

Đây là khoảng trống **không thể kết luận chỉ bằng trạng thái `PUBLISHED`**. Cần so sánh các bản ghi nguồn đã đủ thời gian xử lý với **inbox/task trong DB đích**, qua batch API, báo cáo xuất dữ liệu hoặc một bảng snapshot được cập nhật bởi tiến trình đối soát.

Ví dụ:

~~~text
Order Service (source facts)       Fulfillment Service (derived state)
order_id=O-101, PAID              task(O-101)=DONE           -> khớp
order_id=O-102, PAID              task(O-102)=READY          -> đang chờ, chưa phải lỗi
order_id=O-103, PAID              không có task(O-103)      -> thiếu sau grace
order_id=O-104, PAID              task(O-104)=RUNNING lâu   -> quá lease/deadline
~~~

Nếu hai bên dùng **database riêng**, ví dụ `LEFT JOIN` trực tiếp giữa hai bảng thuộc hai database không mặc nhiên khả thi. Quy trình an toàn là:

1. Chốt một **watermark thời gian** hoặc khoảng eventId cần kiểm tra; loại các cập nhật còn đang diễn ra.
2. Lấy danh sách **business operation ID** từ hệ thống nguồn.
3. Truy vấn trạng thái tương ứng từ dịch vụ đích theo batch hoặc qua snapshot đối soát.
4. Phân loại: **chưa đến hạn**, **thiếu task**, **task đang chờ hợp lệ**, **task quá hạn**, **DONE**, **FAILED**, **xung đột dữ liệu**.
5. Ghi vào bảng/sổ **reconciliation findings**, có mã lỗi, bằng chứng, thời điểm phát hiện và hành động khôi phục.

Trạng thái `PUBLISHED` có thể đúng dù consumer chưa chạy; ngược lại, có thể consumer đã xử lý nhưng outbox chưa ghi `PUBLISHED` do mất callback. **Phải tra cứu kết quả ở dịch vụ đích trước khi quyết định phát lại tác vụ có tác dụng phụ**.

### 7.3. Message lỗi, DLQ và tác vụ bị bỏ dở

**DLQ** chỉ là một nguồn bằng chứng. Một message vào DLQ vì hết retry, reject không requeue, TTL hoặc các trường hợp dead-letter khác. Cần đọc nguyên nhân, `eventId`, payload/version và trạng thái nghiệp vụ trước khi replay. Việc DLQ rỗng không nói rằng không còn công việc bỏ dở.

Với task có trạng thái `RUNNING`, phải có **lease** để nhận biết worker đã không còn heartbeat:

~~~sql
SELECT task_id, order_id, source_event_id,
       attempts, lease_owner, lease_until, updated_at
  FROM fulfillment_task
 WHERE status = 'RUNNING'
   AND lease_until < now()
 ORDER BY lease_until;
~~~

Một task hết lease là **ứng viên để điều tra/phục hồi**, không phải bằng chứng worker cũ chưa thực hiện side effect. Ví dụ worker đã gọi thành công dịch vụ vận chuyển nhưng chết trước khi lưu `DONE`; tạo vận đơn lần nữa có thể gây trùng.

## 8. Thiết kế worker có lease để khôi phục tác vụ bị bỏ dở

### 8.1. Trạng thái và quyền sở hữu

~~~text
READY --claim--> RUNNING --business success--> DONE
                    |
                    +--transient error--> READY (next_attempt_at + backoff)
                    |
                    +--permanent error / max attempts--> FAILED
                    |
                    +--lease expired--> eligible for reclaim and verification
~~~

Worker cần nhận **lease token duy nhất** mỗi lần claim. Khi heartbeat hoặc đánh dấu `DONE`, chỉ update nếu token vẫn khớp; callback của worker cũ không được phép ghi đè công việc đã được instance khác sở hữu.

Ví dụ claim một lô task với PostgreSQL:

~~~sql
WITH candidates AS (
    SELECT task_id
      FROM fulfillment_task
     WHERE (status = 'READY' AND next_attempt_at <= now())
        OR (status = 'RUNNING' AND lease_until < now())
     ORDER BY next_attempt_at, updated_at
     FOR UPDATE SKIP LOCKED
     LIMIT 50
)
UPDATE fulfillment_task t
   SET status = 'RUNNING',
       lease_owner = :claim_token,
       lease_until = now() + interval '60 seconds',
       attempts = attempts + 1,
       updated_at = now()
  FROM candidates c
 WHERE t.task_id = c.task_id
RETURNING t.*;
~~~

Khi kết thúc:

~~~sql
UPDATE fulfillment_task
   SET status = 'DONE',
       lease_owner = NULL,
       lease_until = NULL,
       updated_at = now()
 WHERE task_id = :task_id
   AND status = 'RUNNING'
   AND lease_owner = :claim_token;
~~~

Nếu số row update bằng 0, worker đã **mất quyền sở hữu**, cần ghi nhận lỗi concurrency. Kỹ thuật này thường được gọi là **fencing** ở tầng database. Nó ngăn update cũ trong database nhưng **không tự ngăn tác dụng phụ trên hệ thống ngoài**; các dịch vụ ngoài cần hỗ trợ idempotency key, kiểm tra trạng thái theo operation ID hoặc một quy trình bù trừ phù hợp.

Đối với công việc dài, cần heartbeat gia hạn lease theo token; lease phải dài hơn khoảng xử lý bình thường nhưng đủ ngắn để phát hiện worker chết. Dùng đồng hồ database khi so thời gian; tránh phụ thuộc clock của từng instance có sai lệch.

### 8.2. Phục hồi an toàn

Giả sử task giao hàng của đơn `O-104` hết lease:

1. Đối soát task, đọc `source_event_id`, `order_id`, lần xử lý, lịch sử gọi dịch vụ vận chuyển.
2. Truy vấn dịch vụ vận chuyển bằng **idempotency key** hoặc mã request đã dùng để xem vận đơn có được tạo chưa.
3. Nếu đã tạo, cập nhật task thành `DONE` hoặc trạng thái chờ bước kế tiếp theo dữ kiện thật; không gọi tạo lần nữa.
4. Nếu chắc chắn chưa tạo và vẫn trong hạn retry, cho task trở về `READY` với backoff và token mới.
5. Nếu kết quả bên ngoài không xác định, đánh dấu `NEEDS_REVIEW` trong hệ thống điều phối (nếu dùng trạng thái này thì mở rộng schema phù hợp); tránh retry mù quáng.

Trạng thái nghiệp vụ có thể thay đổi trong lúc retry. Ví dụ đơn đã hủy thì không được tiếp tục tạo vận đơn chỉ vì một event cũ được giao lại. Worker phải **kiểm tra điều kiện nghiệp vụ hiện tại**, không chỉ tin vào payload cũ.

## 9. Reconciler trong Spring Boot: quét, phân loại, sửa có kiểm soát

Đối soát có thể chạy theo lịch bằng Spring Scheduling. Ví dụ:

~~~java
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableScheduling
public class ReconciliationSchedulingConfig {
}
~~~

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ReliabilityReconciler {
    private final ReconciliationService service;

    public ReliabilityReconciler(ReconciliationService service) {
        this.service = service;
    }

    @Scheduled(fixedDelayString = "${reconciliation.interval-ms:60000}")
    public void reconcile() {
        // Mỗi phương thức xử lý theo batch và transaction nhỏ.
        // ReconciliationService do ứng dụng triển khai.
        service.inspectOutboxStale();
        service.inspectUnmatchedBusinessFacts();
        service.inspectExpiredTaskLeases();
        service.inspectDeadLetters();
    }
}
~~~

`fixedDelay` tính thời gian chờ kể từ khi lần chạy trước hoàn thành **trên instance tương ứng**; nếu nhiều replica của ứng dụng cùng chạy scheduler, chúng có thể quét chồng nhau. Để tránh tác động trùng, cần **leader election**, distributed lock có lease hoặc bảo đảm mọi hành động sửa đều **idempotent, có claim bằng database**. Việc scan có thể chạy đồng thời; chính khâu thay đổi trạng thái phải chịu được concurrency.

Không nên gom hàng triệu record vào một transaction dài. Hãy:

- Quét theo batch và watermark, dùng index trên trạng thái/thời gian.
- Tách **detector** (phát hiện), **classifier** (phân loại) và **repair executor** (thực thi phục hồi).
- Lưu phát hiện theo **fingerprint** cố định, tránh mở trùng cảnh báo sau mỗi phút.
- Ghi `first_seen_at`, `last_seen_at`, `severity`, `decision`, `resolved_at` và bằng chứng đủ để audit.
- Giới hạn ngân sách retry/redrive theo phút và theo dịch vụ; không khuếch đại sự cố broker/DB khi đang quá tải.
- Đặt giới hạn `max_attempts`, deadline nghiệp vụ và một nhánh can thiệp thủ công khi không rõ kết quả.

### Cơ chế sửa chữa theo từng loại sai lệch

| Phát hiện | Hành động đầu tiên | Điều kiện để tự sửa | Khi nào cần người kiểm tra |
| --- | --- | --- | --- |
| Outbox `PENDING` quá hạn | Kiểm tra dispatcher và lịch retry. | Đủ hạn, chưa vượt số lần và topology đúng. | Nhiều publish NACK/return, dữ liệu nguồn bất nhất. |
| Outbox `SENDING` hết lease | Xác minh quyền sở hữu; cho claim lại. | EventId ổn định và consumer idempotent. | Publish có side effect không idempotent. |
| Nguồn `PAID` nhưng không có outbox | Đọc lịch sử chuyển trạng thái và event ID. | Có thể phục hồi cùng business operation ID chắc chắn. | Không truy ra ID gốc hoặc state đã đổi phức tạp. |
| Nguồn có event, dịch vụ đích thiếu task | Kiểm tra grace, backlog, DLQ và inbox. | Có đường phát lại an toàn bằng cùng eventId. | Đích có tác dụng phụ không thể kiểm tra idempotency. |
| Task `RUNNING` hết lease | Kiểm tra hiệu ứng bên ngoài. | Chứng minh chưa thực thi hoặc có idempotency key. | Kết quả bên ngoài mơ hồ. |
| Message trong DLQ | Phân loại lỗi/version/schema. | Đã sửa nguyên nhân, có giới hạn redrive và dedupe. | Poison message, lỗi dữ liệu hoặc nguy cơ tạo trùng. |

## 10. RabbitMQ observability: cần đo gì?

RabbitMQ management metrics cung cấp thông tin quan trọng như số message trong queue, tốc độ publish/consume/ACK, số consumer, unacked message và tình trạng connection. Nhưng đó là **thước đo hạ tầng**, chưa thay thế được điều kiện hoàn thành nghiệp vụ.

| Chỉ số | Cách hiểu đúng | Khi cần cảnh báo |
| --- | --- | --- |
| `outbox_pending_age_seconds` | Tuổi của event chưa publish thành công. | Vượt SLA publish. |
| `outbox_sending_lease_expired_total` | Event bị bỏ dở giữa quá trình gửi. | Tăng bất thường, claim lặp nhiều lần. |
| `publisher_confirm_nack_total` | Broker không xác nhận publish thành công. | Có NACK liên tiếp hoặc tỷ lệ tăng. |
| `publisher_return_total` | Publish không routable với mandatory/return. | Thường cần điều tra sớm vì topology có thể sai. |
| `queue_ready` / `queue_unacked` | Backlog và delivery đang chờ ACK. | Tăng bền vững, vượt khả năng xử lý. |
| `dlq_messages` / `dlq_oldest_age` | Lỗi chưa được xử lý. | Có message ưu tiên cao bị treo quá hạn. |
| `business_missing_task_total` | Số facts nguồn chưa có kết quả đích sau grace. | Vượt ngưỡng nghiệp vụ hoặc xuất hiện đồng loạt. |
| `task_lease_expired_total` | Task mất heartbeat/quyền xử lý. | Tăng hoặc tồn tại quá lâu. |
| `business_completion_latency_seconds` | Thời gian từ nguồn commit đến kết quả nghiệp vụ. | P95/P99 vượt SLA, dù queue không đầy. |
| `reconciliation_unresolved_age_seconds` | Sai lệch tồn tại bao lâu chưa giải quyết. | Tăng qua nhiều đợt quét. |

**Không đặt nhãn metrics theo `eventId` hoặc `orderId`** vì cardinality rất cao. Giữ các ID trong log/tracing/audit store, còn metrics dùng nhãn có số giá trị hạn chế như loại sự kiện, dịch vụ, nguyên nhân lỗi và mức ưu tiên.

Nên ghi log có cấu trúc theo chuỗi:

~~~json
{
  "eventId": "e1111111-1111-4111-8111-111111111111",
  "orderId": "o-example",
  "eventType": "order.paid",
  "stage": "FULFILLMENT_TASK",
  "taskStatus": "RUNNING",
  "attempt": 3,
  "leaseExpired": true,
  "reconciliationDecision": "VERIFY_EXTERNAL_SIDE_EFFECT"
}
~~~

Đây là ví dụ log; không dùng `orderId` minh họa ở trên làm UUID thực trong code. Dữ liệu nhạy cảm trong payload phải được lọc, hạn chế quyền truy cập và tuân thủ thời gian lưu log/audit của hệ thống.

## 11. Dead-letter, retry và redrive không gây vòng lặp

Khi listener ném lỗi, Spring AMQP có thể requeue theo mặc định của container. Nếu message luôn lỗi, requeue tức thời tạo **poison loop**. Để xử lý có kiểm soát:

1. Phân loại lỗi **tạm thời** (DB bận, timeout mạng) và **vĩnh viễn** (schema sai, thiếu dữ liệu bắt buộc).
2. Dùng retry có **giới hạn** và backoff phù hợp. Sau ngưỡng, reject không requeue để broker chuyển vào **DLX/DLQ** nếu đã cấu hình.
3. Với DLQ, lấy `eventId`, loại lỗi và trạng thái nghiệp vụ hiện tại; không giả định DLQ luôn chứa một message chưa từng được xử lý.
4. Khi đã sửa nguyên nhân, **redrive có kiểm soát** vào exchange/routing key hợp lệ, giữ nguyên **business event ID** để consumer dedupe.
5. Ghi `redrive_attempt`, người/tiến trình kích hoạt, lý do và kết quả; có thể chặn redrive hàng loạt khi tỷ lệ lỗi cao.

Lưu ý: header `x-death` có thể hữu ích cho các lần dead-letter, nhưng không phải bộ đếm tổng số lần mọi loại requeue; ứng dụng cần cơ chế attempt tracking phù hợp. Khi replay, không mù quáng giữ toàn bộ header/TTL của message cũ, vì có thể vô tình đưa lại vào vòng DLQ.

**Phát lại một thông điệp** và **chạy lại một tác vụ nghiệp vụ** là hai hành động khác nhau. Nếu inbox đã ghi nhận eventId và có task đang `RUNNING` bị kẹt, publish lại cùng eventId sẽ bị inbox bỏ qua; hành động đúng là phục hồi **task**, không phải ép tạo một event mới để vượt dedupe.

## 12. Ví dụ đối soát một sự cố có thật về mặt logic

Hãy xem trình tự minh họa sau:

~~~text
09:00:00  Order O-105 chuyển PAID, outbox E-105 được commit.
09:00:01  Publisher gửi E-105; broker confirm ACK.
09:00:02  Listener nhận E-105, ghi inbox và tạo task T-105.
09:00:03  Listener ACK thành công.
09:00:04  Worker claim T-105, trạng thái RUNNING, lease 60 giây.
09:00:05  Worker gửi lệnh tạo vận đơn tới đối tác.
09:00:06  Đối tác tạo vận đơn, nhưng worker bị kill trước khi ghi DONE.
09:01:05  Lease T-105 hết hạn.
09:02:00  Reconciler phát hiện RUNNING quá lease.
~~~

Đến thời điểm 09:02, có thể quan sát **outbox = PUBLISHED**, **inbox đã có event**, **RabbitMQ queue depth = 0**, nhưng **task vẫn RUNNING**. Đó là lý do đối soát phải nhìn tới kết quả nghiệp vụ.

Nếu reconciler lập tức gọi tạo vận đơn mới, có thể tạo trùng. Cách đúng là hỏi hệ thống đối tác theo **idempotency key** của tác vụ `T-105`:

- Đối tác trả “đã tạo vận đơn”: lưu ID vận đơn và hoàn tất task.
- Đối tác xác nhận chưa tạo: thực hiện lại với **cùng idempotency key**.
- Đối tác không xác định hoặc không hỗ trợ tra cứu: đưa vào luồng kiểm tra/chờ xác minh theo mức độ rủi ro.

Không có RabbitMQ transaction hay publisher confirm nào thay thế được bước xác minh này.

## 13. Checklist kiểm thử tích hợp và diễn tập phục hồi

Các tình huống nên kiểm thử trên RabbitMQ và database thật trong môi trường test:

| Tình huống cố tình gây lỗi | Điều cần quan sát | Kết quả an toàn kỳ vọng |
| --- | --- | --- |
| Kill Order Service sau DB commit, trước publish | Outbox còn `PENDING`. | Dispatcher sau restart phát cùng eventId. |
| Broker nhận publish nhưng producer chết trước cập nhật outbox | Outbox chưa `PUBLISHED`, có thể publish lại. | Inbox ngăn tạo task trùng. |
| Routing key sai, không có binding | Publisher return (khi mandatory bật), consumer không nhận. | Outbox chưa đánh dấu publish thành công theo tiêu chí routable; có alert. |
| Kill consumer sau commit DB, trước ACK | Message redeliver. | Inbox unique chống tạo task trùng. |
| Listener lỗi với payload sai | Retry giới hạn rồi DLQ. | Không có hot loop, có dấu vết điều tra. |
| Kill task worker sau side effect, trước `DONE` | Task hết lease. | Reconciler kiểm tra kết quả bên ngoài trước retry. |
| Tạo nhiều instance dispatcher/reconciler | Có thể claim/tranh chấp cùng record. | Claim token, conditional update và idempotency chống ghi chồng. |
| Dịch vụ đích offline dài hơn grace | Nhiều missing task tạm thời, backlog. | Phân loại đúng là chậm/không khả dụng; tránh phát trùng vô hạn. |
| Chạy lại DLQ cũ sau thay đổi schema | Payload cũ không tương thích. | Có versioning/migration, chỉ redrive khi đã thử. |

Trong test, nên đo **event ID trùng được nhận bao nhiêu lần** và **tác dụng phụ thật tạo bao nhiêu lần**. Mục tiêu là một tác dụng phụ hợp lệ theo business operation, dù việc giao message có thể diễn ra nhiều lần. Không tuyên bố “exactly-once delivery” chỉ vì integration test không thấy duplicate.

## 14. Bài thực hành

**Bối cảnh:** Hệ thống có Order Service phát sự kiện `order.paid`, Fulfillment Service tạo tác vụ giao hàng và một worker gọi dịch vụ bên ngoài. SLA minh họa: sự kiện phải đến dịch vụ đích trong 2 phút; tác vụ phải hoàn tất trong 15 phút.

**Yêu cầu thực hiện:**

1. Tạo bảng `orders` và `outbox_events`; cập nhật đơn sang `PAID` và ghi event vào outbox trong một transaction.
2. Viết dispatcher dùng `RabbitTemplate`, publisher confirm, publisher returns và `CorrelationData(eventId)`. Chỉ đánh dấu `PUBLISHED` khi điều kiện confirm/routing phù hợp; thử shutdown giữa publish và cập nhật trạng thái.
3. Tạo inbox và task tại Fulfillment Service. `@RabbitListener` phải xử lý eventId trùng mà không tạo hai task.
4. Thêm worker có `lease_owner`, `lease_until`, `attempts`, `next_attempt_at`; bảo đảm một task không được hai worker cùng xác nhận kết quả trong database.
5. Tạo reconciler theo lịch, quét outbox quá hạn, missing task sau grace, lease hết hạn và DLQ. Mỗi phát hiện cần có **mã**, **bằng chứng** và **quyết định phục hồi**.
6. Giả lập các ca mất confirm, consumer chết trước ACK, worker chết sau side effect. Chứng minh hệ thống có thể phục hồi mà không tạo tác dụng phụ trùng.
7. Xây dashboard cho tuổi outbox, độ trễ hoàn thành đầu cuối, task quá lease, DLQ và số vấn đề đối soát còn mở; phân biệt metric hạ tầng với metric nghiệp vụ.

### Câu hỏi tự kiểm tra

**Câu 1.** RabbitMQ queue đã rỗng và publisher đã nhận confirm ACK. Có thể tuyên bố mọi đơn hàng `PAID` đã được giao vận không?

**Đáp án:** Không. Queue rỗng chỉ thể hiện trạng thái hiện tại của queue; confirm chỉ nói về publish. Cần đối chiếu nguồn `PAID` với trạng thái task/kết quả giao hàng tại Fulfillment Service.

**Câu 2.** Outbox event đang `SENDING`, lease hết hạn. Có nên tạo `eventId` mới trước khi publish lại?

**Đáp án:** Không. Publish trước đó có thể đã thành công. Cần giữ `eventId` gốc và dùng idempotency ở consumer để loại bỏ hiệu ứng trùng.

**Câu 3.** Inbox đã chứa eventId nên listener bỏ qua message redeliver, nhưng task chưa `DONE`. Có nên sửa inbox để cho listener tạo lại task mới?

**Đáp án:** Không tự động. Inbox thể hiện sự kiện đã được nhận/ghi vào database; task có vòng đời riêng. Cần đối soát và phục hồi task đó, kiểm tra side effect ngoài hệ thống, thay vì phá khóa chống trùng.

**Câu 4.** Một task hết lease có chứng minh worker cũ chưa gửi dữ liệu đến hệ thống ngoài không?

**Đáp án:** Không. Worker có thể đã gọi thành công rồi chết trước khi ghi nhận. Cần xác minh kết quả bằng business operation ID hoặc idempotency key trước khi thử lại.

## 15. Ghi nhớ

Trong hệ thống **Spring AMQP và RabbitMQ**, độ tin cậy đầu cuối đòi hỏi dữ liệu **nguồn**, dấu vết **outbox/publish**, dữ liệu **inbox/consumer**, trạng thái **tác vụ nghiệp vụ** và các trường hợp **retry/DLQ** có thể đối chiếu với nhau. **Publisher confirm**, **publisher return**, **consumer ACK** và **hoàn thành nghiệp vụ** là những bằng chứng ở **các tầng khác nhau**. Dùng **transactional outbox**, **idempotent inbox**, **lease và fencing**, **reconciliation theo lịch**, metric/cảnh báo và quy trình phục hồi có kiểm soát để phát hiện, điều tra và sửa các tác vụ bị bỏ dở.

### Tham khảo

- [Spring AMQP Reference – Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html).
- [Spring AMQP Reference – Resilience, recovering from errors and broker failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html).
- [RabbitMQ – Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms).
- [RabbitMQ – Dead Letter Exchanges](https://www.rabbitmq.com/docs/dlx).
