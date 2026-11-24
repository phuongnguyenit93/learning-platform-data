# Cầu nối tới Kafka hoặc RabbitMQ và ranh giới xác nhận thông điệp

RSocket thường là lớp giao tiếp realtime giữa ứng dụng và dịch vụ, trong khi Kafka hoặc RabbitMQ đảm nhiệm việc lưu đệm, phân phối và xử lý thông điệp giữa các hệ thống. Một cầu nối (bridge) kết hợp hai phía: nhận request hoặc stream từ RSocket rồi xuất bản thành message broker; theo chiều ngược lại, bridge tiêu thụ message từ broker và chuyển thành interaction RSocket đến dịch vụ nhận.

Điểm khó nhất không nằm ở việc gọi KafkaTemplate hay RabbitTemplate. Điểm quan trọng là xác định chính xác **ai đang xác nhận điều gì**. RSocket response, Kafka producer acknowledgement, Kafka consumer offset commit, RabbitMQ publisher confirm và RabbitMQ consumer acknowledgement là các tín hiệu ở những ranh giới khác nhau. Nếu trả ACK quá sớm, hệ thống có thể báo thành công trong khi message chưa được broker tiếp nhận hoặc nghiệp vụ chưa được xử lý.

Bài học này hướng dẫn thiết kế bridge cho cả Kafka và RabbitMQ, xác định ranh giới ACK theo từng chiều, xử lý retry và duplicate, kiểm soát backpressure, cũng như kiểm thử các tình huống lỗi giữa RSocket và broker.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả kiến trúc bridge hai chiều giữa RSocket và message broker.
- Phân biệt RSocket response với broker confirm và consumer acknowledgement.
- Trả RSocket response sau khi Kafka hoặc RabbitMQ xác nhận publish.
- Commit Kafka offset sau khi xử lý downstream thành công.
- ACK RabbitMQ delivery sau khi xử lý downstream thành công.
- Cấu hình Kafka producer idempotence, acks và consumer offset commits.
- Dùng RabbitMQ publisher confirms, returns và manual consumer acknowledgements.
- Thiết kế event envelope có event ID, key và correlation ID.
- Xử lý retry, dead-letter queue/topic và duplicate bằng idempotency.
- Hiểu giới hạn của transaction và vì sao bridge không tự có exactly-once end-to-end.
- Áp dụng backpressure, giới hạn in-flight messages và kiểm thử failure boundaries.

## 1. Vị trí của bridge trong kiến trúc

Bridge là một adapter ở ranh giới giữa giao thức realtime và hệ thống messaging. Nó chuyển đổi envelope, route, serialization và chính sách xác nhận; không nên để controller RSocket tự chứa logic quản lý broker, retry hoặc offset.

~~~mermaid
flowchart LR
    C["RSocket clients"] --> R["RSocket endpoint"]
    R --> A["Bridge application service"]
    A --> P["Kafka producer / Rabbit publisher"]
    P --> B["Kafka / RabbitMQ"]
    B --> K["Kafka listener / Rabbit consumer"]
    K --> D["Bridge application service"]
    D --> S["RSocket requester"]
    S --> X["RSocket service"]
~~~

Hai luồng chính:

1. **RSocket → broker**: client gửi command hoặc event; bridge xác thực, kiểm tra dữ liệu, xuất bản message và có thể trả receipt sau khi broker xác nhận.
2. **Broker → RSocket**: bridge nhận message; gọi RSocket service; chỉ xác nhận message broker sau khi downstream hoàn tất theo hợp đồng đã chọn.

Bridge có thể chạy trong cùng ứng dụng với RSocket server hoặc là một service riêng. Service riêng thường giúp tách tải, quyền truy cập broker và vòng đời consumer khỏi endpoint realtime.

### 1.1. Chọn interaction model RSocket

| Nhu cầu | Interaction phù hợp | Ý nghĩa response |
|---|---|---|
| Gửi một command và cần biết broker đã nhận | Request-response | Trả receipt sau broker confirm/ack |
| Gửi event best-effort, không cần receipt | Fire-and-forget | Không có response payload |
| Gửi một yêu cầu và nhận nhiều kết quả | Request-stream | Mỗi phần tử có semantics riêng |
| Gửi nhiều command và nhận nhiều kết quả | Request-channel | Hai luồng có thể chạy đồng thời |

Nếu client cần biết broker đã nhận message, dùng request-response. Fire-and-forget không có response payload để mang publisher confirmation về client. Không nên mô tả việc gửi FNF là message đã được lưu bền vững.

## 2. Ranh giới xác nhận: năm tín hiệu không thể thay thế nhau

Một hệ thống bridge có thể có nhiều ACK liên tiếp. Mỗi ACK chỉ chứng minh một bước cụ thể đã hoàn tất:

| Tín hiệu | Bên gửi → bên nhận | Xác nhận điều gì? |
|---|---|---|
| RSocket response | Responder → requester | Handler đã trả kết quả theo hợp đồng ứng dụng |
| Kafka producer acknowledgement | Kafka broker → producer | Record được broker chấp nhận theo cấu hình acks |
| Kafka offset commit | Consumer → Kafka broker | Consumer group đã lưu vị trí đọc tiếp theo |
| RabbitMQ publisher confirm | RabbitMQ broker → publisher | Broker đã nhận trách nhiệm với publish |
| RabbitMQ consumer ACK | Consumer → RabbitMQ broker | Delivery đã được consumer xử lý và có thể được loại khỏi queue |

RabbitMQ publisher confirms và consumer acknowledgements là hai cơ chế độc lập. Publisher confirm không biết consumer đã xử lý message hay chưa; consumer ACK cũng không biết publisher đã nhận confirm hay chưa.

### 2.1. Minh họa hai chiều

~~~mermaid
sequenceDiagram
    participant C as RSocket client
    participant G as Bridge
    participant B as Broker
    participant W as Worker
    C->>G: Request publish(eventId)
    G->>B: Publish event
    B-->>G: Producer ACK / Publisher Confirm
    G-->>C: RSocket receipt
    B->>W: Deliver event
    W->>G: Process message
    G->>C: RSocket request-response
    C-->>G: Application receipt
    G-->>B: Consumer ACK / Offset commit
~~~

Sơ đồ minh họa hai ranh giới publish và consume. Trong triển khai thực tế, client RSocket ở đầu vào và service RSocket ở đầu ra có thể là hai ứng dụng khác nhau.

### 2.2. Chọn ý nghĩa của receipt

Một receipt nên nói rõ mức độ hoàn tất:

- ACCEPTED_BY_BRIDGE: bridge đã nhận request và đưa vào pipeline xử lý.
- PUBLISHED_TO_BROKER: broker đã xác nhận publish theo cấu hình.
- PROCESSED_BY_CONSUMER: consumer hoặc service đích đã hoàn tất nghiệp vụ.

Không dùng một trạng thái chung như SUCCESS cho cả ba mức. Nếu RSocket client cần biết message đã được consumer xử lý, publisher confirm là chưa đủ; cần một response hoặc event kết quả từ consumer.

## 3. Thiết kế event envelope dùng chung

Kafka và RabbitMQ có cách phân phối khác nhau, nhưng bridge nên chuẩn hóa một envelope ở tầng ứng dụng:

~~~java
public record IntegrationEvent<T>(
        String eventId,
        String eventType,
        int schemaVersion,
        String aggregateKey,
        String tenantId,
        String correlationId,
        Instant occurredAt,
        T payload) {
}
~~~

Ý nghĩa các trường:

| Trường | Mục đích |
|---|---|
| eventId | ID ổn định để deduplicate khi retry hoặc redelivery |
| eventType | Tên sự kiện nghiệp vụ |
| schemaVersion | Phiên bản schema để tương thích tiến/lùi |
| aggregateKey | Khóa giữ thứ tự theo thực thể nếu broker hỗ trợ |
| tenantId | Ranh giới dữ liệu và authorization |
| correlationId | Nối request RSocket với message và trace downstream |
| occurredAt | Thời điểm nghiệp vụ phát sinh |
| payload | Dữ liệu nghiệp vụ |

Giữ eventId qua mọi lần retry. Nếu tạo ID mới cho mỗi lần gửi lại, consumer không thể nhận ra hai message là cùng một sự kiện.

Không đưa bearer token, secret hoặc toàn bộ security context vào event. Hãy chuyển danh tính đã xác minh thành thông tin nghiệp vụ tối thiểu mà consumer được phép nhận.

## 4. Chiều RSocket → Kafka

Với Spring for Apache Kafka, KafkaTemplate.send(...) trả về CompletableFuture<SendResult<K,V>>. Future hoàn tất khi producer nhận kết quả gửi theo cấu hình Kafka producer. Có thể chuyển future thành Mono để RSocket handler chỉ trả receipt sau khi publish hoàn tất.

Ví dụ:

~~~java
@Controller
public class EventPublishController {

    private final KafkaTemplate<String, IntegrationEvent<?>> kafkaTemplate;

    public EventPublishController(
            KafkaTemplate<String, IntegrationEvent<?>> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    @MessageMapping("events.publish")
    public Mono<PublishReceipt> publish(
            IntegrationEvent<?> event) {

        ProducerRecord<String, IntegrationEvent<?>> record =
                new ProducerRecord<>(
                        "integration.events",
                        event.aggregateKey(),
                        event);

        return Mono.defer(() ->
                Mono.fromFuture(kafkaTemplate.send(record)))
                .map(result -> new PublishReceipt(
                        event.eventId(),
                        result.getRecordMetadata().topic(),
                        result.getRecordMetadata().partition(),
                        result.getRecordMetadata().offset(),
                        "PUBLISHED_TO_BROKER"));
    }
}
~~~

Mono.defer trì hoãn lệnh gửi cho đến khi có subscription. Nếu producer future hoàn tất lỗi, Mono phát lỗi và RSocket handler không trả receipt thành công.

Receipt trên chỉ chứng minh Kafka producer nhận xác nhận publish. Nó không chứng minh consumer đã xử lý record. Nếu cần xác nhận nghiệp vụ cuối cùng, hãy thiết kế một reply topic, một request/reply correlation flow hoặc một RSocket callback riêng.

### 4.1. Producer durability và idempotence

Ví dụ cấu hình producer:

~~~yaml
spring:
  kafka:
    producer:
      acks: all
      properties:
        enable.idempotence: true
~~~

acks quyết định producer chờ mức xác nhận nào:

| Giá trị | Hành vi |
|---|---|
| 0 | Không chờ broker ACK; không biết chắc broker đã nhận record |
| 1 | Chờ leader ghi record vào local log |
| all | Chờ các replica in-sync theo cấu hình broker xác nhận |

enable.idempotence=true giúp Kafka producer tránh ghi lặp do retry ở tầng producer. Idempotence yêu cầu acks=all, retries lớn hơn 0 và giới hạn max.in.flight.requests.per.connection phù hợp. Kafka hiện bật idempotence mặc định nếu không có cấu hình xung đột, nhưng khai báo tường minh giúp chính sách dễ đọc hơn.

Idempotent producer không thay thế eventId của ứng dụng. Nếu client timeout sau khi broker đã ghi record rồi gửi lại request bằng một producer operation mới, bridge cần deduplicate theo event ID hoặc dùng cơ chế idempotency ở consumer.

### 4.2. Fire-and-forget có phù hợp không?

Nếu RSocket client gửi fire-and-forget, handler có thể nhận payload và xuất bản message. Tuy nhiên, requester không nhận response payload để biết publisher future thành công hay thất bại. Nếu broker acknowledgement là một phần của hợp đồng nghiệp vụ, request-response phù hợp hơn.

Fire-and-forget có thể dùng cho telemetry best-effort, metric hoặc event mà caller không cần biết kết quả publish. Khi đó cần theo dõi lỗi publish qua log, metric và retry nội bộ; không báo cho caller rằng broker đã lưu message.

## 5. Chiều RSocket → RabbitMQ

RabbitMQ cung cấp publisher confirms để publisher biết broker đã nhận trách nhiệm với message. Với Spring AMQP, RabbitTemplate hỗ trợ CorrelationData chứa future cho kết quả confirm.

Để nhận cả confirm và thông báo message không định tuyến được, cấu hình:

~~~java
CachingConnectionFactory connectionFactory =
        new CachingConnectionFactory("localhost");

connectionFactory.setPublisherConfirmType(
        ConfirmType.CORRELATED);
connectionFactory.setPublisherReturns(true);

RabbitTemplate rabbitTemplate =
        new RabbitTemplate(connectionFactory);

rabbitTemplate.setMandatory(true);
~~~

mandatory=true cho phép broker trả lại message không tìm được queue đích. publisherReturns=true bật returns ở connection factory; ConfirmType.CORRELATED bật publisher confirms có correlation.

Ví dụ chuyển confirm thành Mono:

~~~java
public Mono<PublishReceipt> publish(
        IntegrationEvent<?> event) {

    return Mono.defer(() -> {
        CorrelationData correlation =
                new CorrelationData(event.eventId());

        rabbitTemplate.convertAndSend(
                "integration.exchange",
                "events." + event.eventType(),
                event,
                correlation);

        return Mono.fromFuture(correlation.getFuture())
                .flatMap(confirm -> {
                    if (!confirm.isAck()) {
                        return Mono.error(
                                new BrokerPublishException(
                                        confirm.getReason()));
                    }

                    ReturnedMessage returned =
                            correlation.getReturned();
                    if (returned != null) {
                        return Mono.error(
                                new UnroutableMessageException(
                                        returned.getReplyText()));
                    }

                    return Mono.just(new PublishReceipt(
                            event.eventId(),
                            "PUBLISHED_TO_BROKER"));
                });
    });
}
~~~

Ví dụ dùng CorrelationData.getFuture() để chờ confirm mà không block thread. Khi bật cả confirms và returns, Spring AMQP bảo đảm thông tin returned message được đặt trước khi future confirm hoàn tất. Vì vậy, hãy kiểm tra cả confirm.isAck() và correlation.getReturned().

Publisher confirm ACK không chứng minh message đã được consumer xử lý. Nó chỉ xác nhận phía broker đã nhận trách nhiệm publish theo semantics của RabbitMQ. Nếu message không định tuyến được và mandatory được bật, publisher cần xử lý return riêng.

### 5.1. Xử lý publish timeout

Nếu bridge không nhận confirm trước timeout, kết quả có thể không xác định: broker có thể đã nhận message nhưng confirm bị mất trên đường về. Retry có thể tạo duplicate. Hãy giữ event ID ổn định, lưu correlation ID và làm consumer idempotent.

Không coi timeout là bằng chứng chắc chắn rằng broker chưa nhận message. Đây là trạng thái UNKNOWN cần retry an toàn hoặc truy vấn trạng thái theo event ID.

## 6. Chiều Kafka → RSocket và ranh giới offset commit

Kafka consumer quản lý vị trí đọc theo partition. Offset được commit là vị trí tiếp theo consumer sẽ đọc khi khởi động lại. Nếu commit trước khi downstream xử lý xong, process có thể mất message khi crash. Nếu commit sau khi downstream hoàn tất nhưng crash trước khi commit, record có thể được gửi lại.

Với Spring Kafka từ phiên bản 3.2, @KafkaListener hỗ trợ return type bất đồng bộ như Mono<?> và CompletableFuture<?>. Container tự chuyển sang manual ack semantics cho async return và xác nhận record khi async result hoàn tất thành công.

Ví dụ bridge consumer gọi RSocket request-response:

~~~java
@Component
public class KafkaToRSocketBridge {

    private final RSocketRequester requester;

    public KafkaToRSocketBridge(RSocketRequester requester) {
        this.requester = requester;
    }

    @KafkaListener(
            topics = "integration.events",
            groupId = "rsocket-bridge")
    public Mono<Void> forward(
            IntegrationEvent<?> event) {

        return requester
                .route("events.ingest")
                .data(event)
                .retrieveMono(DeliveryReceipt.class)
                .then();
    }
}
~~~

Khi RSocket service trả response thành công, Mono hoàn tất và Spring Kafka có thể ACK/commit offset. Nếu RSocket request lỗi hoặc timeout, Mono phát lỗi; container error handler quyết định retry hoặc recover. Không nuốt lỗi bằng onErrorResume(error -> Mono.empty()) nếu điều đó sẽ khiến container coi message đã xử lý thành công.

Hợp đồng của DeliveryReceipt phải được định nghĩa rõ. Nếu service đích chỉ trả response ngay sau khi nhận request, offset commit chỉ chứng minh service đã nhận. Nếu service trả receipt sau khi ghi bền vững hoặc hoàn tất nghiệp vụ, offset commit có ý nghĩa mạnh hơn.

### 6.1. Chọn AckMode và error handler

Spring Kafka hỗ trợ nhiều chế độ commit:

| AckMode | Thời điểm commit |
|---|---|
| RECORD | Sau khi listener xử lý xong từng record |
| BATCH | Sau khi xử lý hết records trong một poll |
| TIME / COUNT | Khi đạt điều kiện thời gian hoặc số lượng |
| MANUAL | Listener yêu cầu acknowledge; container áp dụng semantics batch |
| MANUAL_IMMEDIATE | Commit ngay khi acknowledge được gọi trên consumer thread |

Với async listener trả về Mono hoặc CompletableFuture, Spring Kafka tự dùng manual acknowledgement semantics và hoàn tất ACK theo async result. Khi async result lỗi, retry/recovery phụ thuộc container error handler.

DefaultErrorHandler có thể retry với backoff và gửi record lỗi sang dead-letter topic bằng DeadLetterPublishingRecoverer. Cần chọn chính sách cho poison message: retry hữu hạn, DLT, cảnh báo và quy trình replay. Retry vô hạn có thể chặn partition và gây backlog.

Nếu dùng async listener, lưu ý xử lý bất đồng bộ có thể làm side effect của các record trong cùng partition hoàn tất khác thứ tự. Nếu nghiệp vụ phụ thuộc thứ tự theo key, hãy giới hạn concurrency hoặc dùng listener xử lý tuần tự phù hợp.

## 7. Chiều RabbitMQ → RSocket và consumer ACK

RabbitMQ consumer acknowledgement xác nhận delivery đã được xử lý. Khi dùng manual ACK, message chưa được ACK có thể được requeue nếu channel hoặc connection đóng. Vì vậy, consumer phải chấp nhận redelivery và xử lý idempotent.

Spring AMQP cho phép @RabbitListener trả về Mono<?> hoặc CompletableFuture<?>. Khi dùng async return type, listener container phải dùng AcknowledgeMode.MANUAL; container ACK khi async result hoàn tất thành công và NACK khi hoàn tất lỗi theo error policy.

Ví dụ:

~~~java
@RabbitListener(
        queues = "integration.events",
        ackMode = "MANUAL")
public Mono<Void> forward(
        IntegrationEvent<?> event) {

    return requester
            .route("events.ingest")
            .data(event)
            .retrieveMono(DeliveryReceipt.class)
            .then();
}
~~~

Nếu RSocket service trả response thành công, Mono hoàn tất và container ACK delivery. Nếu request lỗi, container xử lý NACK/requeue hoặc dead-letter theo exception, defaultRequeueRejected và error handler.

Không tự ACK ngay sau khi nhận message nếu công việc downstream vẫn đang chạy. Nếu ACK trước khi RSocket call hoàn tất rồi process crash, message đã bị loại khỏi queue và không còn cơ chế redelivery.

### 7.1. Prefetch và giới hạn công việc đang chạy

RabbitMQ prefetch giới hạn số delivery chưa được ACK mà broker có thể gửi đến consumer. Prefetch quá lớn làm tăng số message đang giữ trong bộ nhớ và số công việc in-flight. Prefetch quá thấp có thể giảm throughput.

Chọn prefetch dựa trên:

- Thời gian xử lý RSocket trung bình và p95/p99.
- Số request đồng thời mà downstream chịu được.
- Kích thước payload.
- Số consumer và concurrency.
- Mức độ cần giữ thứ tự message.

Với message lớn hoặc cần xử lý tuần tự, giảm prefetch. Không dùng auto-ack cho bridge cần bảo đảm delivery; chế độ này đánh đổi an toàn để tăng throughput.

## 8. Đặt ranh giới ACK đúng trong hai chiều

Các quy tắc thiết kế quan trọng:

| Luồng | Khi nào trả ACK? | ACK chứng minh |
|---|---|---|
| RSocket → Kafka | Sau khi Kafka producer future thành công | Broker đã xác nhận record |
| RSocket → RabbitMQ | Sau publisher confirm và kiểm tra return | Broker xác nhận publish, message không bị return |
| Kafka → RSocket | Sau khi RSocket request-response hoàn tất thành công | Downstream đã hoàn tất theo hợp đồng receipt |
| RabbitMQ → RSocket | Sau khi RSocket request-response hoàn tất thành công | Downstream đã hoàn tất theo hợp đồng receipt |

Nếu RSocket client chỉ cần bridge nhận command, có thể trả ACCEPTED_BY_BRIDGE trước khi broker publish xong, nhưng phải lưu trạng thái và cung cấp cách tra cứu kết quả. Không gắn nhãn đó là PUBLISHED_TO_BROKER.

Nếu RSocket response bị mất sau khi broker đã xác nhận publish, client có thể gửi lại. Bridge cần idempotency key để tránh tạo hai event nghiệp vụ giống nhau.

## 9. Idempotency, duplicate và Inbox pattern

At-least-once delivery là lựa chọn phổ biến trong hệ thống messaging đáng tin cậy. Điều đó có nghĩa message có thể được giao lại khi consumer crash hoặc ACK/offset commit bị mất. Consumer phải có khả năng nhận duplicate an toàn.

Inbox pattern lưu eventId đã xử lý trong cùng transaction với thay đổi nghiệp vụ:

~~~text
BEGIN TRANSACTION
  INSERT INTO processed_messages(event_id)
    -- unique constraint trên event_id
  APPLY business state change
COMMIT
ACK broker / commit offset
~~~

Nếu eventId đã tồn tại, consumer bỏ qua side effect trùng lặp nhưng vẫn hoàn tất delivery theo chính sách. Việc ghi inbox và cập nhật trạng thái nghiệp vụ phải cùng transaction của database nếu cần bảo đảm không có một bên thành công còn bên kia thất bại.

Idempotency cần áp dụng ở cả hai chiều:

- RSocket client retry command sau timeout.
- Bridge retry publish do không nhận confirm.
- Kafka hoặc RabbitMQ redeliver message.
- RSocket service xử lý thành công nhưng bridge crash trước khi commit offset/ACK.

## 10. Outbox pattern khi phát sinh event từ database

Một lỗi phổ biến là cập nhật database rồi publish broker trong cùng method nhưng không có transaction chung. Nếu database commit thành công và publish thất bại, dữ liệu đã đổi nhưng event bị mất. Nếu publish thành công rồi database rollback, broker có event cho thay đổi chưa xảy ra.

Outbox pattern ghi thay đổi nghiệp vụ và event vào cùng database transaction:

~~~mermaid
flowchart TD
    A["Business command"] --> T["DB transaction"]
    T --> D["Update business tables"]
    T --> O["Insert outbox event"]
    T --> C["Commit"]
    C --> P["Outbox publisher"]
    P --> B["Kafka / RabbitMQ"]
    B --> M["Mark outbox row published"]
~~~

Publisher đọc các outbox row chưa gửi, xuất bản message và đánh dấu đã gửi sau khi broker confirm. Nếu publisher crash sau khi broker nhận message nhưng trước khi đánh dấu row, nó sẽ publish lại; consumer vẫn cần idempotency.

Kafka transaction có thể bảo đảm atomicity giữa các record Kafka và offset Kafka trong một consume-transform-produce workflow. Nó không tự tạo transaction phân tán bao trùm RSocket, RabbitMQ hoặc database ngoài Kafka.

## 11. Kafka transaction và giới hạn exactly-once

Spring Kafka hỗ trợ KafkaTransactionManager, transactional listener container và local transaction của KafkaTemplate. Có thể cấu hình transactionIdPrefix để producer factory tạo transactional producer.

Transaction phù hợp khi:

- Consumer đọc record từ Kafka.
- Ứng dụng xử lý và ghi một hoặc nhiều record mới vào Kafka.
- Offset input được đưa vào cùng Kafka transaction.
- Khi transaction commit, output records và input offsets được commit cùng nhau.

Transaction không bao trùm một RSocket call bên ngoài Kafka. Nếu consumer gọi RSocket service thành công rồi Kafka transaction abort, record có thể được đọc lại và RSocket service có thể nhận request lần nữa. Dùng idempotency key hoặc inbox ở service đích.

Không tuyên bố bridge có exactly-once end-to-end chỉ vì Kafka producer bật idempotence hoặc transaction. Exactly-once luôn có phạm vi cụ thể và phải được mô tả cùng hệ thống tham gia.

## 12. Retry, dead-letter và lỗi không thể khôi phục

Không phải lỗi nào cũng nên retry giống nhau:

| Nhóm lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Lỗi tạm thời | Broker unavailable, network timeout, rate limit | Retry với exponential backoff và jitter |
| Lỗi validation | Schema sai, thiếu trường bắt buộc | Không retry vô hạn; đưa DLT/DLQ |
| Lỗi authorization | Token hết hạn, tenant không được phép | Từ chối và ghi nhận an toàn; không retry mù |
| Lỗi downstream | RSocket service tạm thời không sẵn sàng | Retry hữu hạn, circuit breaker và backoff |
| Kết quả không xác định | Timeout sau khi request có thể đã được xử lý | Retry với cùng event ID và idempotency |

Với Kafka, có thể dùng DefaultErrorHandler và DeadLetterPublishingRecoverer hoặc non-blocking retry topics. Với RabbitMQ, cấu hình dead-letter exchange/queue, TTL hoặc retry queue theo topology. Tránh requeue ngay lập tức không giới hạn vì poison message có thể tạo vòng lặp nóng.

DLT/DLQ cần giữ metadata gốc như event ID, correlation ID, nguồn topic/queue, số lần retry và nguyên nhân lỗi. Cần có quy trình replay có kiểm soát và tránh replay message đã gây side effect một phần.

## 13. Backpressure và giới hạn in-flight

RSocket hỗ trợ Reactive Streams demand qua mạng cho request-stream và channel. Kafka và RabbitMQ có cơ chế điều tiết riêng, nhưng không nên giả định broker tự hiểu demand của RSocket.

Bridge cần nối hai cơ chế bằng giới hạn concurrency:

- Kafka: điều chỉnh listener concurrency, số record mỗi poll, async processing và commit strategy.
- RabbitMQ: điều chỉnh prefetch, consumer concurrency và manual ACK.
- RSocket: dùng request-stream/channel, giới hạn số request đang chờ và timeout.
- Ứng dụng: dùng flatMap với concurrency hữu hạn hoặc concatMap nếu cần thứ tự.

Ví dụ xử lý batch có concurrency giới hạn:

~~~java
Flux<DeliveryReceipt> forwardBatch(
        Flux<IntegrationEvent<?>> events) {

    return events.flatMap(
            event -> requester
                    .route("events.ingest")
                    .data(event)
                    .retrieveMono(DeliveryReceipt.class),
            16);
}
~~~

flatMap(..., 16) cho phép tối đa 16 request downstream đồng thời trong pipeline này. Nếu cần giữ thứ tự, dùng concatMap hoặc phân vùng theo aggregate key. Không tăng concurrency vô hạn để cố bắt kịp broker vì điều đó chỉ chuyển backlog từ broker vào heap của bridge hoặc service đích.

## 14. Ordering và partition/routing key

Kafka bảo đảm thứ tự trong một partition. Dùng aggregateKey làm record key để các event của cùng một thực thể đi vào cùng partition. RabbitMQ có ordering phụ thuộc queue, consumer concurrency, prefetch, redelivery và cách xử lý; không giả định nhiều consumer vẫn giữ thứ tự xử lý nghiệp vụ.

RSocket channel cũng có thể xử lý đồng thời nếu handler dùng flatMap. Nếu nghiệp vụ cần thứ tự:

- Giữ cùng aggregate key hoặc routing key.
- Giới hạn một luồng xử lý cho cùng key.
- Dùng concatMap hoặc partitioned executor theo key.
- Tránh async retry làm event sau hoàn tất trước event trước.
- Thiết kế sequence number để phát hiện event đến trễ hoặc bị thiếu.

## 15. Schema, metadata và tracing

Broker message cần mang đủ metadata để trace xuyên qua bridge:

- eventId: định danh bất biến của message.
- correlationId: nối với RSocket request ban đầu.
- causationId: event hoặc command đã gây ra event hiện tại.
- traceparent: W3C trace context nếu hệ thống dùng distributed tracing.
- contentType và schemaVersion: cách giải mã payload.
- tenantId: phạm vi dữ liệu đã được xác thực.

Không dùng broker header để thay thế schema contract. Hãy quản lý schema tương thích, quy tắc evolution và cách xử lý consumer đọc phiên bản mới hơn hoặc cũ hơn.

Khi ghi log, dùng event ID, topic/queue, partition/offset hoặc routing key, correlation ID và kết quả ACK. Không log toàn bộ payload nhạy cảm hoặc credential.

## 16. Kiểm thử ranh giới xác nhận

Kiểm thử happy path là chưa đủ. Cần mô phỏng crash hoặc timeout tại từng ranh giới:

1. RSocket request đến bridge nhưng bridge dừng trước khi publish.
2. Broker nhận message nhưng producer confirm/ACK bị mất.
3. Producer confirm thành công nhưng RSocket response bị mất.
4. Consumer nhận message nhưng dừng trước khi gọi RSocket.
5. RSocket service xử lý thành công nhưng response bị mất.
6. Downstream trả lỗi và broker cần retry.
7. Retry vượt ngưỡng và message được đưa vào DLT/DLQ.
8. Consumer ACK hoặc Kafka offset commit thất bại.
9. Message được redeliver và inbox nhận ra event ID đã xử lý.
10. Nhiều event cùng aggregate key vẫn giữ thứ tự yêu cầu.
11. Tốc độ broker cao hơn downstream và bridge vẫn giữ giới hạn in-flight.

### 16.1. Kiểm thử Kafka listener bất đồng bộ

Spring Kafka cho phép listener trả về Mono. Có thể kiểm tra:

- Khi Mono hoàn tất, offset được acknowledge theo container semantics.
- Khi Mono phát lỗi, error handler thực hiện retry hoặc recovery.
- Khi container dừng, các async result đang chạy được quản lý theo shutdown timeout.
- Side effect downstream là idempotent vì record có thể được giao lại.

### 16.2. Kiểm thử RabbitMQ publisher và consumer

Kiểm tra publisher:

- Confirm ACK khi broker nhận message.
- Confirm NACK hoặc channel error được truyền thành lỗi.
- Message không định tuyến được được trả về khi mandatory và returns được bật.

Kiểm tra consumer:

- ACK chỉ sau khi downstream RSocket hoàn tất theo hợp đồng.
- Lỗi tạm thời dẫn đến requeue/retry theo policy.
- Poison message được dead-letter sau số lần thử cho phép.
- Channel đóng khi delivery chưa ACK dẫn đến redelivery.

## 17. Các lỗi thường gặp

### Trả RSocket response ngay sau khi gọi send

Lệnh publish thường bất đồng bộ. Trả receipt trước khi producer future hoặc publisher confirm hoàn tất sẽ báo thành công quá sớm.

### Dùng fire-and-forget nhưng yêu cầu broker ACK

FNF không trả response payload. Dùng request-response nếu client cần biết broker đã xác nhận publish.

### Nhầm publisher confirm với consumer ACK

Publisher confirm chỉ xác nhận broker nhận publish. Consumer ACK mới xác nhận delivery đã được xử lý ở phía consumer.

### Commit Kafka offset trước khi downstream hoàn tất

Nếu process crash sau commit nhưng trước RSocket xử lý, record có thể bị mất khỏi luồng xử lý. Chỉ commit sau khi hoàn tất theo hợp đồng.

### ACK RabbitMQ ngay khi nhận delivery

Nếu ACK trước khi side effect hoàn tất, lỗi downstream có thể làm message bị mất. Dùng manual ACK hoặc async listener completion.

### Nuốt exception rồi trả Mono.empty()

Container có thể coi xử lý thành công và commit/ACK message. Hãy để lỗi đi đến error handler khi cần retry hoặc dead-letter.

### Retry với event ID mới

Consumer không thể nhận ra duplicate. Giữ event ID ổn định qua tất cả lần retry.

### Dựa vào exactly-once của một broker cho toàn bộ bridge

Transaction của Kafka không bao trùm RabbitMQ, database hoặc RSocket service. Dùng outbox/inbox và idempotent consumer ở ranh giới ngoài transaction.

### Buffer không giới hạn

Bridge có thể trở thành điểm tích tụ message khi downstream chậm. Đặt giới hạn concurrency, prefetch, timeout và queue capacity.

## 18. Checklist thiết kế bridge

Trước khi triển khai production, hãy xác nhận:

1. Event envelope có event ID ổn định, key, correlation ID và schema version.
2. Hợp đồng RSocket phân biệt ACCEPTED_BY_BRIDGE, PUBLISHED_TO_BROKER và PROCESSED_BY_CONSUMER.
3. RSocket request-response chỉ trả broker receipt sau khi producer confirm/ack hoàn tất.
4. FNF chỉ dùng khi caller không cần receipt.
5. Kafka producer dùng acks và idempotence phù hợp với durability cần thiết.
6. Kafka consumer chỉ commit offset sau khi downstream hoàn tất theo hợp đồng.
7. RabbitMQ publisher confirms và returns được bật khi cần kiểm tra publish.
8. RabbitMQ consumer dùng manual/async ACK sau khi xử lý thành công.
9. Retry có backoff, giới hạn số lần và DLT/DLQ.
10. Consumer idempotent để chịu redelivery và kết quả không xác định.
11. Outbox/inbox được dùng khi cần phối hợp database với broker.
12. Không tuyên bố exactly-once end-to-end nếu transaction không bao trùm mọi hệ thống.
13. Backpressure và in-flight concurrency có giới hạn.
14. Ordering theo key được giữ khi nghiệp vụ yêu cầu.
15. Có kiểm thử crash, timeout, confirm loss, duplicate và retry.
16. Metrics theo dõi publish confirm latency, consumer lag, unacked deliveries, retry và DLT/DLQ.

## 19. Tổng kết

Bridge giữa RSocket và Kafka/RabbitMQ phải xác định rõ ranh giới xác nhận ở từng bước. Với chiều RSocket sang broker, chỉ trả receipt PUBLISHED_TO_BROKER sau khi Kafka producer hoặc RabbitMQ publisher xác nhận publish. Với chiều broker sang RSocket, chỉ commit Kafka offset hoặc ACK RabbitMQ delivery sau khi downstream hoàn tất theo hợp đồng đã chọn.

Kafka producer ACK, Kafka consumer offset commit, RabbitMQ publisher confirm, RabbitMQ consumer ACK và RSocket response đều có ý nghĩa riêng. Chúng không tạo thành một transaction end-to-end. Để chịu timeout, crash và redelivery, hãy giữ event ID ổn định, xây dựng consumer idempotent, cân nhắc outbox/inbox, giới hạn concurrency và kiểm thử từng failure boundary. Thiết kế như vậy giúp bridge duy trì độ tin cậy mà vẫn tận dụng được giao tiếp realtime của RSocket và khả năng phân phối thông điệp của broker.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring for Apache Kafka — Message Listener Containers and Offset Commits](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html)
- [Spring for Apache Kafka — Asynchronous @KafkaListener Return Types](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/async-returns.html)
- [Apache Kafka — Producer Configs](https://kafka.apache.org/44/configuration/producer-configs/)
- [Spring for Apache Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html)
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [Spring AMQP — Correlated Publisher Confirms and Returns](https://docs.spring.io/spring-amqp/reference/amqp/template.html)
- [Spring AMQP — Asynchronous @RabbitListener Return Types](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-returns.html)
