# JMS instrumentation trong Spring Boot

Trong chương **Messaging và task observability** của module **SPRING_BOOT_OBSERVABILITY**, JMS instrumentation quan sát các thao tác gửi và nhận message qua Java Message Service. Ứng dụng Spring Boot thường gửi message bằng JmsTemplate và xử lý message bằng listener container như @JmsListener. Khi được instrument, các thao tác này có thể tạo metrics và tracing context để nhóm vận hành biết producer gửi bao nhiêu message, consumer xử lý mất bao lâu, lỗi xuất hiện ở đâu và message đã đi qua những service nào.

JMS là API messaging; broker như ActiveMQ Artemis hoặc IBM MQ đảm nhiệm lưu/chuyển message theo cấu hình queue/topic. Micrometer Observation và tracing integration quan sát hoạt động ở phía ứng dụng. Chúng không thay thế broker monitoring: queue depth, consumer count, enqueue/dequeue rate, redelivery và broker storage vẫn cần được theo dõi từ broker.

Trong **SPRING_BOOT_OBSERVABILITY**, messaging observability bổ sung cho HTTP, database, metrics, logs và distributed tracing. Bài này tập trung vào producer/consumer instrumentation, lifecycle của message, context propagation qua JMS properties, metrics và spans, xử lý retry/DLQ, cardinality và cách kiểm chứng end-to-end.

## 1. Luồng JMS và các điểm cần quan sát

```text
orders-service (producer)
      |
      | JmsTemplate.convertAndSend(...)
      | message + trace context properties
      v
   JMS broker
      |
      | queue / topic
      v
payment-service (consumer)
      |
      | @JmsListener
      | extract context + process
      v
  database / downstream service
```

Có ít nhất hai operation cần phân biệt:

| Operation | Điểm bắt đầu/kết thúc quan sát | Câu hỏi |
| --- | --- | --- |
| Publish/send | Producer bắt đầu gửi tới khi JMS provider hoàn tất thao tác gửi | Gửi message có lỗi hoặc chậm không? |
| Process/receive | Consumer nhận message và xử lý callback | Consumer xử lý mất bao lâu, thành công hay thất bại? |

Thời gian send thành công không có nghĩa consumer đã xử lý xong. Tương tự, consumer callback hoàn tất không tự chứng minh message đã được commit/acknowledge theo semantics của transaction/session. Cần phân biệt broker acceptance, consumer processing và acknowledgement.

## 2. JMS instrumentation trong Spring Boot

Spring Boot có thể cấu hình ConnectionFactory, JmsTemplate và listener infrastructure dựa trên dependency và properties. Micrometer Observation integration của Spring JMS có thể instrument thao tác gửi và nhận khi được bật và phiên bản hỗ trợ.

Những điểm tích hợp thường gặp:

- JmsTemplate cho thao tác publish/send và request-reply.
- @JmsListener được thực thi bởi listener container do Spring quản lý.
- ObservationRegistry cung cấp registry cho observations.
- Micrometer Tracing bridge/propagator có thể đưa trace context vào message properties và khôi phục context ở consumer khi integration được cấu hình.

Không giả định mọi Spring Boot/Spring Framework version đều tự động instrument cùng cách. Kiểm tra dependency, auto-configuration, observation convention và listener container factory đang được sử dụng. Nếu tự tạo JmsTemplate hoặc container ngoài Spring configuration, các customizer/observation wiring của Boot có thể không được áp dụng.

### Dependency và cấu hình nền tảng

Ví dụ dependency cho ứng dụng Spring Boot dùng JMS:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-artemis</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Starter broker cụ thể phụ thuộc provider được triển khai. Với provider khác, dùng starter/client tương ứng. Nếu cần tracing, bổ sung Micrometer Tracing bridge và exporter theo kiến trúc observability của ứng dụng; không cài nhiều tracing bridge cùng lúc.

Ví dụ cấu hình minh họa:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://artemis:61616
    user: JMS_USER
    password: lấy từ secret management/environment
  jms:
    template:
      qos:
        delivery-mode: persistent
        priority: 4
        time-to-live: 60000
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Các property cụ thể phụ thuộc broker starter và Spring Boot version. Dùng secret management/environment injection cho credentials; không commit username/password thật vào repository hoặc logs. Cấu hình delivery mode, priority và time-to-live phải theo yêu cầu nghiệp vụ, không phải mặc định observability.

## 3. Producer: quan sát thao tác gửi bằng JmsTemplate

JmsTemplate là abstraction Spring dùng để gửi và nhận message. Ví dụ:

```java
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
class OrderEventPublisher {
    private final JmsTemplate jmsTemplate;

    OrderEventPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    void publish(OrderCreated event) {
        jmsTemplate.convertAndSend("orders.created", event);
    }
}
```

Khi observation integration được kết nối, thao tác send có thể tạo observation/span với metadata như destination, operation và message context tùy convention. Việc gọi convertAndSend thành công thường thể hiện provider chấp nhận thao tác gửi theo API hiện tại; nó không chứng minh consumer đã nhận hoặc hoàn tất xử lý.

Nếu tự tạo timer quanh convertAndSend, hãy xác định rõ mục tiêu là đo thời gian producer API call. Không tạo thêm timer trùng với built-in observation có cùng semantics, nếu không metrics sẽ bị đếm hai lần hoặc gây hiểu nhầm.

### Message metadata có cardinality thấp

Producer metrics thường nên phân nhóm theo destination name ổn định, operation và kết quả. Tránh dùng message ID, order ID, customer ID, correlation ID hoặc raw payload làm metric tags.

| Dimension | Ví dụ phù hợp | Tránh |
| --- | --- | --- |
| Destination | orders.created | Queue name được tạo riêng cho mỗi tenant |
| Operation | send, publish | Message ID |
| Result | success, error | Exception message |
| Broker cluster | Tên cluster ổn định | Host/header tùy request |

Destination động theo tenant hoặc request có thể tạo cardinality rất cao. Nếu ứng dụng có nhiều tenant nhưng dùng chung queue, giữ tenant metadata ở log/trace theo chính sách; không biến nó thành metric tag mặc định.

## 4. Consumer: quan sát @JmsListener và listener container

Spring JMS listener container nhận message từ broker và gọi method có @JmsListener:

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class PaymentEventListener {

    @JmsListener(destination = "orders.created")
    void onOrderCreated(OrderCreated event) {
        paymentService.startAuthorization(event);
    }
}
```

Observation ở consumer cần bao phủ thời gian xử lý message. Tùy listener container, transaction/session và integration, span/observation có thể bắt đầu khi message được dispatch vào listener và kết thúc khi callback hoàn tất. Kiểm tra chính xác behavior của version và factory được cấu hình.

Một consumer có thể nhận message rồi xử lý thành công và acknowledge/commit; ném exception khiến transaction rollback hoặc message được redeliver; bị timeout hoặc process dừng giữa chừng; hoặc gửi message sang dead-letter queue theo broker/redelivery policy.

Không gộp tất cả tình huống trên thành một metric message received. Cần tách receive/processing outcome, redelivery và broker-level queue metrics nếu hệ thống cần theo dõi đầy đủ.

## 5. Trace context propagation qua JMS

HTTP thường truyền trace context bằng traceparent/tracestate headers. JMS không truyền HTTP headers; tracing instrumentation phải inject/extract context qua message properties hoặc carrier phù hợp.

```text
Producer span
    |
    | inject trace context into JMS message properties
    v
Broker / queue
    |
    | message properties travel with message
    v
Consumer extracts context
    |
    v
Consumer processing span
```

Khi context propagation đúng, consumer span có thể liên kết với trace của producer theo propagator và messaging semantic convention. Log trong consumer có thể chứa Trace ID/Span ID của context hiện hành. Metrics có thể dùng exemplar để liên kết một sample tới trace nếu registry/backend hỗ trợ.

Không tự đặt một JMS property tên traceId rồi cho rằng W3C propagation đã hoàn tất. Trace context có định dạng và semantics riêng; dùng Micrometer Tracing/OpenTelemetry propagator hoặc integration chính thức của stack.

### Parent-child hay span link?

Message có thể được xử lý bất đồng bộ, trễ lâu hoặc fan-out tới nhiều consumer. Quan hệ trace phù hợp phụ thuộc messaging semantic convention và instrumentation version:

- Một số integration biểu diễn consumer span như child của producer context.
- Với batch hoặc nhiều message parent contexts, span links có thể phù hợp hơn parent duy nhất.
- Redelivery có thể tạo nhiều lần xử lý cho cùng message; mỗi attempt cần trace/span context được biểu diễn rõ.

Không giả định mọi JMS provider/instrumentation đều dùng cùng quan hệ span. Kiểm tra trace thực tế trong backend và convention đang áp dụng.

## 6. Correlation ID, Message ID và Trace ID

| ID | Ý nghĩa | Nơi dùng |
| --- | --- | --- |
| JMS Message ID | Định danh message do provider cấp hoặc theo provider semantics | Broker diagnostics, duplicate investigation |
| Correlation ID | Theo quy ước ứng dụng, liên kết request/reply hoặc workflow | Logs và message headers |
| Trace ID | Định danh distributed trace | Tracing backend và log correlation |
| Span ID | Định danh một operation/span | Xác định bước xử lý cụ thể |
| Business ID | Ví dụ order ID/payment ID | Tra cứu nghiệp vụ có phân quyền |

Trong JMS, property JMSCorrelationID thường được dùng cho request/reply correlation theo API/provider convention. Không mặc định gán Trace ID vào JMSCorrelationID nếu điều đó xung đột với semantics request/reply của ứng dụng. Trace propagation nên dùng carrier/property mapping do instrumentation quản lý; correlation nghiệp vụ giữ riêng.

Message ID và business ID gần như duy nhất, không phù hợp làm metric tags. Có thể ghi chúng trong logs hoặc trace attributes theo privacy/retention policy nếu thực sự cần điều tra.

## 7. Metrics quan trọng cho producer và consumer

Micrometer/Spring integration và broker exporter có thể cung cấp các metrics khác nhau. Các metric concept hữu ích:

| Metric concept | Phía | Ý nghĩa |
| --- | --- | --- |
| Send count/rate | Producer | Số message được gửi theo thời gian |
| Send duration | Producer | Thời gian thao tác gửi qua JMS API |
| Send errors | Producer | Lỗi gửi message |
| Listener processing count | Consumer | Số lần callback xử lý |
| Processing duration | Consumer | Thời gian xử lý message |
| Processing errors | Consumer | Exception hoặc xử lý thất bại |
| Redelivery count | Consumer/broker | Message được giao lại |
| Queue depth | Broker | Số message đang chờ |
| Oldest message age | Broker | Tuổi của message chờ lâu nhất nếu broker cung cấp |
| Consumer count | Broker | Số consumer đang active |

Không phải tất cả metrics đều do Micrometer JMS binder cung cấp. Send/processing observations có thể nằm ở ứng dụng; queue depth, enqueue/dequeue, consumer count và broker storage thường đến từ broker management/exporter.

Tên metric cụ thể phụ thuộc version/provider. Kiểm tra Actuator metrics endpoint, Prometheus exposition và broker metrics trước khi viết dashboard.

## 8. Đo processing duration và business outcome

Một consumer callback có thể hoàn tất nhanh nhưng business workflow còn tiếp tục ở service khác. Cần định nghĩa rõ duration đang đo: thời gian listener callback; thời gian xử lý business service đồng bộ trong callback; thời gian transaction/acknowledgement; hoặc thời gian từ publish tới consumer completion (end-to-end message age).

Các khoảng thời gian này khác nhau. Listener timer không bao gồm thời gian message nằm trong queue trước khi được dispatch. Muốn đo queue delay, cần timestamp/enqueue time hoặc broker metrics phù hợp và xử lý clock skew.

Ví dụ custom observation cho business processing:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Component;

@Component
class InvoiceMessageProcessor {
    private final ObservationRegistry observationRegistry;

    InvoiceMessageProcessor(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    void process(InvoiceRequested message) {
        Observation.createNotStarted(
                    "invoice.message.process",
                    observationRegistry)
                .lowCardinalityKeyValue("message.type", "invoice-requested")
                .observe(() -> invoiceService.createInvoice(message));
    }
}
```

Ví dụ minh họa tạo observation quanh business operation. Message type phải là tập giá trị hữu hạn đã quản lý. Không thêm invoice ID vào low-cardinality values. Nếu built-in listener observation đã đo callback, custom business observation nên có tên khác và mục tiêu riêng, chẳng hạn phân biệt thời gian xử lý nghiệp vụ với overhead của listener/transaction.

## 9. Retry, redelivery và dead-letter queue

JMS consumer có thể nhận lại message khi xử lý thất bại hoặc acknowledgement/transaction không hoàn tất. Vì vậy một message có thể tạo nhiều processing attempts:

```text
Message published
      |
      v
Attempt 1: processing exception
      |
      v
Broker redelivery
      |
      v
Attempt 2: timeout
      |
      v
Broker redelivery policy
      |
      +----> Attempt 3 succeeds
      |
      +----> hoặc route sang DLQ
```

Theo dõi riêng số message logical được publish, số lần consumer delivery/processing attempts, số lần redelivery, số message xử lý thành công cuối cùng và số message chuyển vào dead-letter queue.

Không cộng processing attempts thành số message nghiệp vụ. Nếu một message được thử 5 lần, dashboard producer chỉ có thể ghi một lần publish trong khi consumer có 5 attempts.

DLQ cần metrics và alert riêng. Queue depth tăng, oldest message age tăng hoặc DLQ rate tăng có thể cho thấy consumer không xử lý được message. Việc message được đưa vào DLQ không nhất thiết có nghĩa broker hỏng; có thể là poison message, schema incompatibility hoặc business validation failure.

## 10. Cardinality và dữ liệu trong message

Message payload thường chứa order ID, customer ID, email, account number hoặc dữ liệu nghiệp vụ. Không đưa payload hoặc các ID này vào metric tags.

| Giá trị | Metric tag? | Nơi phù hợp hơn |
| --- | --- | --- |
| Destination cố định | Có thể | Metrics và traces |
| Message type đã chuẩn hóa | Có thể | Metrics |
| Processing outcome | Có thể | Metrics |
| Redelivery category hữu hạn | Có thể | Metrics |
| JMS Message ID | Không | Log/trace theo policy |
| JMSCorrelationID tùy request | Không | Log/trace |
| Order/customer ID | Không | Business logs/traces có kiểm soát |
| Raw payload | Không | Không log; hoặc redact/allowlist nghiêm ngặt |
| Exception message | Không | Exception type đã chuẩn hóa |

Không log toàn bộ JMS message để debug. Payload có thể chứa PII, secrets hoặc dữ liệu thanh toán. Ưu tiên message type, schema version, destination, outcome và identifiers đã được phê duyệt.

## 11. Transaction và acknowledgement semantics

JMS session/transaction quyết định khi nào message được acknowledge hoặc rollback. Observability cần phân biệt listener method trả về bình thường, transaction commit thành công, message được acknowledge và transaction rollback khiến message redeliver.

Nếu instrumentation kết thúc span ngay khi listener method return nhưng transaction commit diễn ra sau đó, span duration có thể không bao gồm toàn bộ acknowledgement/commit path tùy container. Hãy kiểm tra transaction manager, listener container configuration và observation boundary.

Với transacted session, exception có thể rollback transaction và gây redelivery. Với acknowledgement modes khác, semantics khác nhau. Không viết alert listener success chỉ dựa vào callback không ném exception nếu commit/ack có thể thất bại sau đó.

## 12. Kiểm tra instrumentation trong Spring Boot

Quy trình kiểm chứng:

1. Xác nhận Spring Boot, Spring JMS, Micrometer Observation và tracing bridge/exporter version tương thích.
2. Xác nhận JmsTemplate và listener container được Spring quản lý và đã nhận observation configuration.
3. Gửi một message test tới destination ổn định.
4. Kiểm tra producer observation/span và metric count/duration.
5. Để consumer nhận message; kiểm tra consumer observation/span và outcome.
6. Kiểm tra trace context được inject vào JMS message properties và extract ở consumer theo convention.
7. Tạo một message gây exception có kiểm soát; quan sát error, rollback/redelivery và DLQ policy.
8. Đối chiếu application metrics với broker queue depth/consumer metrics.
9. Kiểm tra metric tags không chứa message ID, business ID hoặc raw payload.
10. Kiểm tra logs có destination, message type, correlation/trace context cần thiết nhưng không lộ payload nhạy cảm.

### Ma trận kiểm thử

| Thử nghiệm | Kết quả cần xác minh |
| --- | --- |
| Publish một message hợp lệ | Producer send observation được ghi |
| Consumer xử lý thành công | Processing observation kết thúc theo semantics cấu hình |
| Consumer ném exception | Error được ghi; rollback/redelivery theo policy |
| Message đi qua nhiều service | Trace context được inject/extract hoặc link theo convention |
| Message bị redeliver | Attempt/redelivery được phân biệt |
| Message vào DLQ | DLQ metrics/logging cho biết destination và loại lỗi |
| Gửi nhiều order ID | Metric series vẫn gộp theo destination/type, không theo order ID |
| Broker tạm unavailable | Producer error/latency phản ánh lỗi kết nối |
| Consumer dừng | Broker queue depth/oldest age tăng; application processing rate giảm |
| Transaction commit lỗi | Không nhầm callback return với acknowledged success |

## 13. Dashboard và cảnh báo messaging

Một dashboard nên kết hợp application và broker metrics:

| Panel | Nguồn | Ý nghĩa |
| --- | --- | --- |
| Publish rate/error rate | Producer observations | Producer có gửi được không? |
| Send duration p95/p99 | Producer observations | Broker/API call có chậm không? |
| Processing rate/duration | Consumer observations | Consumer xử lý nhanh/chậm thế nào? |
| Processing error rate | Consumer observations | Consumer đang lỗi bao nhiêu? |
| Queue depth | Broker metrics | Message backlog có tăng không? |
| Oldest message age | Broker metrics | Message bị chờ quá lâu không? |
| Consumer count | Broker metrics | Có đủ consumer hoạt động không? |
| Redelivery/DLQ rate | Broker + application | Có poison message hoặc lỗi lặp không? |

Một số tín hiệu kết hợp:

- Queue depth và oldest message age cùng tăng: throughput consumer không theo kịp producer.
- Queue depth tăng nhưng consumer count bằng 0: listener/container hoặc kết nối broker có thể bị gián đoạn.
- Processing duration tăng, queue depth tăng: consumer xử lý chậm hoặc dependency downstream đang nghẽn.
- Redelivery và DLQ tăng: message processing đang thất bại lặp lại.
- Producer send errors tăng: kiểm tra broker availability, credentials, network và destination policy.

Không alert chỉ theo queue depth tuyệt đối nếu queue có traffic nền lớn. Dùng baseline, tốc độ tăng, message age và SLA xử lý của từng destination.

## 14. Bài tập tình huống

orders-service publish 1.000 message mỗi phút tới queue orders.created. payment-service chỉ xử lý được 700 message mỗi phút. Sau 20 phút, queue depth tăng liên tục; processing error rate tăng và một nhóm message bị redeliver nhiều lần rồi vào DLQ.

**Câu hỏi:**

1. Vì sao chỉ xem producer send success không đủ đánh giá hệ thống?
2. Metrics nào cho thấy consumer không theo kịp producer?
3. Vì sao redelivery attempts không được tính như số message logical mới?
4. Cần kiểm tra trace/log context ở những ranh giới nào?
5. Những nguyên nhân nào có thể làm message chuyển vào DLQ?

**Gợi ý phân tích:**

- Producer gửi thành công chỉ cho biết broker nhận thao tác send; nó không chứng minh consumer đã xử lý.
- So sánh publish rate với processing rate, queue depth, oldest message age, consumer count, processing duration và error rate.
- Một message có thể được giao nhiều lần; theo dõi logical publish count riêng với delivery/attempt count.
- Kiểm tra producer inject context vào message properties, broker giữ properties và consumer extract context trước khi xử lý; đối chiếu Correlation ID/Message ID riêng.
- Poison message, schema incompatibility, validation error, dependency timeout hoặc redelivery limit có thể dẫn tới DLQ tùy broker policy.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| JMS flow | Phân biệt producer, broker và consumer |
| JmsTemplate | Quan sát send/publish |
| @JmsListener | Quan sát consumer processing |
| Observation | Hiểu registry, convention và lifecycle |
| Trace propagation | Inject/extract context qua JMS properties |
| Correlation IDs | Phân biệt Message ID, JMSCorrelationID, Trace ID và business ID |
| Metrics | Tách send, processing, retry và broker queue metrics |
| Cardinality | Không dùng message/business IDs hoặc payload làm metric tags |
| Retry/redelivery | Phân biệt logical message và delivery attempts |
| DLQ | Theo dõi poison message và failure routing |
| Transactions | Phân biệt callback return, commit và acknowledgement |
| End-to-end | Xác minh producer, broker, consumer, traces, logs và metrics |

**Ghi nhớ:** JMS instrumentation quan sát cả thao tác publish của producer và processing của consumer. JmsTemplate send thành công không có nghĩa consumer đã xử lý; listener callback return cũng cần được phân biệt với transaction commit/acknowledgement. Dùng Micrometer Observation và tracing integration phù hợp để ghi metrics/spans, inject/extract trace context qua JMS properties, đồng thời giữ Message ID, JMSCorrelationID, Trace ID và Business ID đúng semantics. Theo dõi application send/process metrics cùng broker queue depth, oldest message age, redelivery và DLQ; giữ tags ở cardinality thấp và không đưa raw payload vào logs/metrics.
