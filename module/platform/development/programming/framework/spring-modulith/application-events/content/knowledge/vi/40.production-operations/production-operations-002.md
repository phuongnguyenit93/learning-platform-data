# Cấu hình broker

Cấu hình broker quyết định ứng dụng kết nối tới đâu, publish event bằng cơ chế xác nhận nào, consumer nhận message ra sao và message được phục hồi thế nào khi có lỗi. Trong production, cấu hình này ảnh hưởng trực tiếp đến độ tin cậy, độ trễ, khả năng mở rộng và mức độ an toàn của giao tiếp giữa các module hoặc giữa các hệ thống.

Với Spring Modulith, application events biểu diễn sự kiện nghiệp vụ bên trong ứng dụng và giúp các module giao tiếp qua contract. Khi cần đưa event ra broker, ứng dụng cần một adapter tích hợp phù hợp, chẳng hạn Spring AMQP cho RabbitMQ hoặc Spring Kafka cho Kafka. Cấu hình broker phải phù hợp với adapter đó và với semantics của broker đang dùng.

Không có một bộ property chung cho mọi broker. RabbitMQ dùng exchange, queue, binding, acknowledgement và publisher confirm; Kafka dùng topic, partition, offset và consumer group. Bài này tập trung vào nguyên tắc production và minh họa cấu hình RabbitMQ bằng Spring Boot/Spring AMQP, đồng thời chỉ ra những điểm cần xem xét khi dùng Kafka.

## 1. Xác định vai trò của broker trong kiến trúc

Trước khi đặt property, hãy xác định broker đang đảm nhiệm vai trò nào:

- Phân phối application event từ một module tới consumer ở module khác.
- Externalize event từ ứng dụng Spring Modulith tới hệ thống khác.
- Tiếp nhận command hoặc message từ một hệ thống bên ngoài.
- Lưu giữ message trong thời gian consumer ngừng hoạt động.
- Hỗ trợ retry, dead-letter, replay và phân phối tải.

Một ứng dụng có thể vừa dùng Spring Modulith application events trong tiến trình, vừa dùng broker cho giao tiếp ngoài tiến trình. Hai lớp này có ranh giới riêng:

~~~mermaid
flowchart TD
    A["Module nghiệp vụ"] --> B["Spring ApplicationEvent"]
    B --> C["Module listener nội bộ"]
    B --> D["Externalization / messaging adapter"]
    D --> E["Broker"]
    E --> F["Consumer adapter"]
    F --> G["Application service"]
    G --> H["Module hoặc hệ thống nhận"]
~~~

Application event không tự động trở thành message trong broker chỉ vì được publish. Cần cấu hình externalization hoặc adapter để chuyển event thành message. Tương tự, message từ broker cần được deserialize, xác thực và chuyển vào application service hoặc event nội bộ theo contract đã thiết kế.

Không đưa logic kết nối broker vào domain model. Domain event nên mô tả điều đã xảy ra; adapter chịu trách nhiệm transport, serialization, routing, acknowledgement và lỗi kết nối.

## 2. Phân biệt Event Publication Registry và broker

Spring Modulith Event Publication Registry ghi nhận publication của application event tới các listener mà Spring Modulith quản lý. Registry hỗ trợ nhận diện publication chưa hoàn tất và phục hồi listener theo cơ chế được cấu hình.

Broker quản lý message ở ranh giới vận chuyển. Nó có thể xác nhận publish, lưu message, giao message, theo dõi offset hoặc chuyển message sang dead-letter. Hai cơ chế không thay thế nhau.

| Thành phần | Trách nhiệm | Câu hỏi được trả lời |
|---|---|---|
| Application event | Mô tả sự kiện nghiệp vụ trong ứng dụng | Điều gì đã xảy ra? |
| Event Publication Registry | Theo dõi publication tới listener nội bộ | Listener đã hoàn tất publication chưa? |
| Messaging adapter | Chuyển đổi event thành message hoặc ngược lại | Payload và metadata được chuyển ra/vào thế nào? |
| Broker | Lưu trữ và phân phối message | Message đã được broker nhận, giao hoặc xác nhận chưa? |
| Inbox/idempotency store | Theo dõi xử lý nghiệp vụ ở consumer | Consumer đã áp dụng logical event này chưa? |
| Outbox | Ghi message cần gửi cùng transaction nghiệp vụ | Làm sao không mất yêu cầu gửi khi database commit? |

Publisher confirm của RabbitMQ hoặc acknowledgement/offset của Kafka không tự chứng minh nghiệp vụ ở consumer đã hoàn tất. Ngược lại, publication nội bộ hoàn tất cũng không chứng minh message đã được broker lưu bền vững. Hãy xác định rõ từng ranh giới và quan sát trạng thái ở đúng nơi.

## 3. Chọn topology và contract trước khi cấu hình

Với RabbitMQ, cần xác định exchange, queue, binding và routing key. Với Kafka, cần xác định topic, partition, replication factor, retention và consumer group.

Trước khi tạo topology, thống nhất:

- Tên event type và schema version.
- Producer và consumer sở hữu từng contract.
- Routing key hoặc topic tương ứng.
- Queue/topic có cần durable hay retention dài không.
- Consumer nào được phép đọc và ghi side effect.
- Retry, dead-letter và replay được thực hiện ở đâu.
- Thứ tự event có cần bảo toàn theo aggregate không.
- Dữ liệu nhạy cảm nào được phép xuất hiện trong payload.

Tên exchange, queue, topic và routing key nên ổn định, dễ phân quyền và có thể suy ra ownership. Tránh tên phụ thuộc hostname, instance ID hoặc giá trị runtime ngẫu nhiên vì sẽ khó vận hành và khó cấp quyền.

Ví dụ một luồng RabbitMQ:

~~~text
Exchange: orders.events
Routing key: order.paid
Queue: accounting.order-paid
Consumer: accounting
Dead-letter exchange: orders.dlx
Dead-letter queue: accounting.order-paid.dead
~~~

Một queue có thể nhận nhiều event type nếu consumer xử lý chung một contract. Ngược lại, một event có thể được định tuyến tới nhiều queue độc lập khi nhiều bounded context cần phản ứng.

## 4. Tách cấu hình theo môi trường

Không nên dùng cùng một cấu hình cho local, test, staging và production. Những môi trường này khác nhau về địa chỉ broker, credential, TLS, topology, concurrency và chính sách retry.

Một cấu trúc Spring Boot có thể tách phần chung và phần môi trường:

~~~text
application.yml
application-local.yml
application-test.yml
application-staging.yml
application-prod.yml
~~~

File chung chứa các giá trị mặc định an toàn và cấu hình ứng dụng không nhạy cảm. Profile môi trường cung cấp địa chỉ, vhost, TLS, số consumer và các giới hạn phù hợp. Credential được đưa vào qua environment variable hoặc secret manager.

Ví dụ cấu hình RabbitMQ cho một môi trường production:

~~~yaml
spring:
  rabbitmq:
    addresses: ${RABBITMQ_ADDRESSES}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    virtual-host: ${RABBITMQ_VHOST:/application}
    connection-timeout: 5s
    requested-heartbeat: 30s
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
    ssl:
      enabled: true
    listener:
      simple:
        acknowledge-mode: manual
        concurrency: 4
        max-concurrency: 12
        prefetch: 20
        default-requeue-rejected: false
~~~

Các property cần khớp phiên bản Spring Boot và Spring AMQP của ứng dụng. Ví dụ trên là cấu hình tham khảo cho RabbitMQ; không sao chép nguyên xi nếu ứng dụng dùng DirectMessageListenerContainer, Kafka hoặc một adapter khác.

Với local, có thể dùng broker container hoặc broker phát triển riêng. Không để profile local vô tình được kích hoạt ở production. Hãy xác minh profile đang hoạt động khi ứng dụng khởi động và ghi nhận broker endpoint/vhost ở mức an toàn, không ghi password.

## 5. Quản lý credential và TLS

Broker là ranh giới hạ tầng quan trọng. Tài khoản kết nối cần có quyền tối thiểu theo đúng vhost, exchange, queue và thao tác cần thiết.

Các nguyên tắc bảo mật:

- Không commit username/password production vào repository.
- Dùng secret manager hoặc hệ thống cấp secret của nền tảng triển khai.
- Tạo tài khoản riêng cho từng ứng dụng hoặc workload.
- Chỉ cấp quyền configure/write/read trên tài nguyên cần dùng.
- Xoay vòng credential có kế hoạch và kiểm tra khả năng kết nối sau khi xoay.
- Bật TLS khi kết nối qua mạng không tin cậy hoặc theo yêu cầu bảo mật của nền tảng.
- Xác minh certificate chain và hostname của broker.
- Giới hạn quyền truy cập management UI và API quản trị.

Với RabbitMQ, TLS cần được cấu hình ở cả broker và client. Chỉ bật cờ SSL phía ứng dụng không đủ nếu truststore, certificate hoặc hostname verification chưa đúng. Không tắt xác minh certificate để né lỗi kết nối production.

Nếu dùng Kafka, cấu hình tương tự ở mức nguyên tắc nhưng property và cơ chế xác thực khác, ví dụ SASL/SCRAM, SASL/OAUTHBEARER hoặc mTLS tùy nền tảng. Không dùng cấu hình RabbitMQ để suy ra cấu hình Kafka.

## 6. Cấu hình connection timeout và heartbeat

Kết nối broker có thể bị gián đoạn bởi network, load balancer, firewall hoặc broker restart. Client cần timeout và heartbeat phù hợp để phát hiện kết nối chết và phục hồi.

Các thông số cần cân nhắc:

| Tham số | Tác dụng | Điều cần tránh |
|---|---|---|
| Connection timeout | Giới hạn thời gian thiết lập kết nối | Quá dài làm startup/health check treo |
| Heartbeat | Phát hiện peer mất phản hồi | Quá thấp tạo disconnect giả khi mạng chập chờn |
| Channel/cache size | Giới hạn tài nguyên channel | Tạo quá nhiều channel ngoài nhu cầu |
| Recovery interval | Khoảng chờ kết nối lại | Retry quá dày gây áp lực lên broker |
| Socket timeout | Giới hạn thao tác mạng theo client | Quá thấp làm request bình thường thất bại |

Không đặt timeout cực thấp chỉ để fail fast nếu hệ thống downstream có độ trễ biến động. Cũng không đặt timeout quá dài khiến thread bị giữ lâu trong lúc broker đã mất kết nối.

Connection recovery cần có backoff và jitter nếu ứng dụng tự điều phối reconnect. Khi nhiều instance cùng khởi động sau một broker outage, reconnect đồng loạt có thể tạo connection storm.

## 7. Khai báo exchange, queue và binding bền vững

Với RabbitMQ, topology nên được khai báo có chủ đích và có thể tái tạo. Exchange và queue durable giúp cấu hình tồn tại qua broker restart; message persistence giúp message được lưu theo semantics của queue/exchange và broker.

Ví dụ cấu hình bằng Spring AMQP:

~~~java
@Configuration
class OrderBrokerTopology {

    @Bean
    DirectExchange ordersExchange() {
        return new DirectExchange(
            "orders.events",
            true,
            false
        );
    }

    @Bean
    Queue accountingOrderPaidQueue() {
        return QueueBuilder.durable("accounting.order-paid")
            .build();
    }

    @Bean
    Binding accountingOrderPaidBinding(
            Queue accountingOrderPaidQueue,
            DirectExchange ordersExchange) {
        return BindingBuilder
            .bind(accountingOrderPaidQueue)
            .to(ordersExchange)
            .with("order.paid");
    }
}
~~~

Đoạn code minh họa exchange durable, queue durable và binding direct. Tên và exchange type cần theo contract của ứng dụng. Nếu có nhiều queue cùng nhận event, khai báo binding riêng cho từng consumer.

Không nhầm durable queue với message persistent. Durable queue giữ topology qua restart; message persistence và broker confirmation quyết định thêm mức bảo đảm lưu message. Với yêu cầu production, cần xem xét cả queue type, replication, disk capacity và publisher confirm.

Trong môi trường nhiều team, topology có thể được quản lý bởi platform hoặc provisioning pipeline thay vì để từng ứng dụng tự tạo. Khi đó ứng dụng cần kiểm tra tài nguyên đã tồn tại và có quyền phù hợp; không cố khai báo lại queue với arguments khác.

## 8. Chọn queue type và mức độ sẵn sàng

RabbitMQ có classic queue và quorum queue với đặc tính khác nhau. Quorum queue dựa trên replication để tăng khả năng chịu lỗi node và thường phù hợp message quan trọng cần độ bền cao. Classic queue có các đặc tính và chi phí khác, nên cần chọn theo yêu cầu chứ không theo mặc định.

Cần quyết định:

- Queue nào cần chịu lỗi node.
- Số replica và vị trí failure domain.
- Mức throughput và latency cần đạt.
- Retention và dung lượng backlog.
- Cách xử lý khi node hoặc network partition gặp sự cố.
- Delivery limit và dead-letter policy.
- Chi phí disk, memory và replication traffic.

Quorum queue không thay thế backup, disaster recovery hoặc thiết kế consumer idempotent. Replication bảo vệ trước một số lỗi node nhưng không ngăn consumer xử lý duplicate hoặc xóa message sai do acknowledgement.

Với Kafka, durability thường được đánh giá qua replication factor, min.insync.replicas, producer acks và retention. Những property này có semantics riêng; không ánh xạ trực tiếp sang durable/quorum queue của RabbitMQ.

## 9. Publisher confirm và unroutable message

Khi publish message tới RabbitMQ, việc method gửi trả về không nhất thiết chứng minh broker đã lưu message. Publisher confirm giúp producer nhận kết quả broker xác nhận publish. Publisher return giúp phát hiện message không route được khi dùng mandatory publish.

Cấu hình tham khảo:

~~~yaml
spring:
  rabbitmq:
    publisher-confirm-type: correlated
    publisher-returns: true
    template:
      mandatory: true
~~~

Producer cần xử lý cả hai tình huống:

- Broker nack hoặc channel/connection lỗi: publish chưa được xác nhận thành công.
- Broker confirm ack nhưng message không route được: cần kiểm tra returned message nếu mandatory publish được bật.

Confirm ack chỉ cho biết broker đã nhận message theo semantics của broker và queue. Nó không chứng minh consumer đã xử lý. Nếu publisher không nhận confirm do timeout, kết quả có thể không xác định: message có thể đã được broker nhận. Khi gửi lại, cần giữ logical event ID và consumer phải idempotent.

Với Kafka, producer thường dùng acks=all và idempotence theo cấu hình client để tăng độ tin cậy khi publish. Vẫn cần xử lý retry, timeout và duplicate theo semantics của producer/consumer.

## 10. Đảm bảo không mất message giữa database và broker

Một lỗi phổ biến là cập nhật database rồi gửi message bằng hai thao tác độc lập:

1. Transaction database commit thay đổi nghiệp vụ.
2. Ứng dụng publish message tới broker.
3. Broker hoặc network lỗi sau commit.

Nếu bước 2 thất bại, dữ liệu nghiệp vụ đã thay đổi nhưng consumer không nhận được event. Nếu gửi message trước khi commit rồi transaction rollback, consumer có thể nhận event cho một thay đổi chưa tồn tại.

Transactional outbox giải quyết khoảng trống này bằng cách ghi business state và bản ghi outbox trong cùng database transaction. Một publisher riêng đọc outbox, gửi message và đánh dấu trạng thái theo confirm.

~~~mermaid
flowchart TD
    A["BEGIN database transaction"] --> B["Update business state"]
    B --> C["Insert outbox record"]
    C --> D["COMMIT"]
    D --> E["Outbox publisher"]
    E --> F["Publish to broker"]
    F --> G{"Broker confirm"}
    G -->|ACK| H["Mark outbox sent"]
    G -->|NACK / timeout| I["Retry later"]
~~~

Outbox thường cung cấp at-least-once publishing: message có thể được gửi lại nếu publisher không chắc lần trước đã thành công. Consumer vẫn cần inbox/idempotency để chống side effect trùng.

Event Publication Registry của Spring Modulith có thể theo dõi publication nội bộ và hỗ trợ phục hồi listener. Khi cần bảo đảm atomicity giữa database và broker, hãy chọn cơ chế externalization/outbox phù hợp và xác minh semantics thực tế; không giả định registry tự tạo transaction phân tán với broker.

## 11. Cấu hình acknowledgement cho consumer

Consumer acknowledgement xác nhận broker có thể loại message khỏi trạng thái đang giao. Với RabbitMQ, ack nên xảy ra sau khi consumer hoàn thành công việc bền vững theo thiết kế.

Các chế độ thường gặp:

| Chế độ | Hành vi | Phù hợp khi |
|---|---|---|
| AUTO | Container ack khi listener hoàn tất bình thường và xử lý exception theo cấu hình | Listener đơn giản, retry container rõ ràng |
| MANUAL | Listener hoặc code tích hợp quyết định ack/nack/reject | Cần điều khiển acknowledgement chi tiết |
| NONE | Broker không chờ acknowledgement | Chỉ dùng khi chấp nhận semantics và rủi ro phù hợp |

Với manual ack, chỉ ack sau khi transaction nghiệp vụ đã commit hoặc công việc đã được ghi vào một work queue bền vững. Nếu ack trước rồi mới ghi database, process crash có thể làm mất message mà không có cách giao lại.

Nếu database commit thành công nhưng ack thất bại, broker có thể giao lại message. Đây là lý do inbox/idempotency cần tồn tại ở consumer. Acknowledgement không thay thế deduplication.

Ví dụ listener manual ack cần xử lý exception và channel theo đúng container configuration. Không bắt lỗi rồi ack message như thành công khi nghiệp vụ chưa hoàn tất.

## 12. Prefetch và concurrency

Prefetch giới hạn số message broker giao cho consumer chưa được ack. Concurrency quyết định số consumer worker xử lý đồng thời. Hai thông số này ảnh hưởng throughput, memory, fairness và thứ tự.

Ví dụ:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        concurrency: 4
        max-concurrency: 12
        prefetch: 20
~~~

Cấu hình trên là điểm khởi đầu minh họa, không phải giá trị khuyến nghị cho mọi hệ thống. Prefetch lớn có thể tăng throughput nhưng giữ nhiều message chưa xử lý trên một consumer, làm consumer khác đói message và tăng bộ nhớ. Prefetch nhỏ cải thiện phân phối nhưng có thể giảm hiệu suất khi round-trip broker cao.

Concurrency cao làm tăng tải lên database và downstream. Hãy chọn dựa trên số CPU, connection pool, giới hạn database, thời gian handler, throughput mục tiêu và khả năng xử lý song song của nghiệp vụ.

Nếu event của cùng aggregate phải giữ thứ tự, tăng concurrency có thể khiến các event xử lý chồng lấn. Cần partitioning theo key, serialization theo aggregate hoặc optimistic locking. Không giả định một queue với nhiều consumer tự bảo đảm thứ tự xử lý hoàn tất.

## 13. Retry, requeue và dead-letter

Không phải mọi lỗi đều nên requeue ngay. Retry tức thời có thể tạo vòng lặp nóng, tăng tải và làm nghẽn queue nếu dependency đang hỏng.

Một chính sách thường chia thành:

- Lỗi tạm thời: retry với backoff và giới hạn số lần.
- Lỗi dữ liệu/contract: reject hoặc chuyển dead-letter để điều tra.
- Lỗi nghiệp vụ hợp lệ: ghi nhận kết quả nghiệp vụ và kết thúc message theo contract.
- Lỗi không xác định: giữ trạng thái để đối soát trước khi thực hiện lại side effect.

Với RabbitMQ, có thể dùng retry queue với TTL và dead-letter exchange để tạo khoảng chờ giữa các lần thử. Khi hết số lần retry, message được chuyển sang DLQ cuối cùng. Cần xác định rõ requeue, retry queue và dead-letter queue là các trạng thái khác nhau.

Nếu dùng Spring AMQP retry interceptor, hãy cấu hình số lần thử, backoff, exception classification và hành vi sau khi hết retry. Nếu listener container tự động requeue exception, message có thể quay lại liên tục. Kiểm tra default-requeue-rejected và dead-letter topology để tránh vòng lặp vô hạn.

## 14. Serialization và schema version

Broker chuyển byte hoặc record; producer và consumer cần thống nhất serializer, content type, encoding và schema. Không nên serialize trực tiếp entity persistence hoặc object có quan hệ nội bộ không thuộc contract.

Payload nên có metadata cần thiết:

~~~json
{
  "eventId": "7d6b0d85-8a2e-4d2c-9c2d-2c4b7b1a9120",
  "eventType": "order.paid",
  "schemaVersion": 2,
  "occurredAt": "2026-11-25T10:15:30Z",
  "correlationId": "checkout-42",
  "data": {
    "orderId": "ORD-42",
    "amount": "125000.50",
    "currency": "VND"
  }
}
~~~

Schema version giúp consumer quyết định cách deserialize và hỗ trợ payload cũ trong giai đoạn migration. Event ID giữ ổn định qua retry và redrive để consumer idempotent. Correlation ID hỗ trợ theo dõi một luồng nghiệp vụ nhưng không nên dùng làm idempotency key nếu một luồng chứa nhiều event.

Khi thay đổi schema, hãy đánh giá backward/forward compatibility và thời gian lưu message. Consumer mới có thể phải đọc message cũ đang nằm trong queue hoặc topic. Không xóa field hay đổi kiểu dữ liệu chỉ vì producer đã được deploy trước consumer.

## 15. Cấu hình consumer group khi dùng Kafka

Nếu ứng dụng dùng Kafka thay cho RabbitMQ, cấu hình producer và consumer theo semantics Kafka. Ví dụ các property thường được xem xét:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    producer:
      acks: all
      properties:
        enable.idempotence: true
    consumer:
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        isolation.level: read_committed
~~~

Ví dụ này minh họa một số lựa chọn phổ biến. Cần cấu hình serializer/deserializer, security protocol, group ID, transaction ID prefix, retry/DLT và offset commit phù hợp với ứng dụng.

Consumer group xác định cách các instance chia partition. Tăng instance vượt quá số partition không làm tăng số consumer đang active cho cùng topic. Offset commit quá sớm có thể làm mất message sau crash; commit sau xử lý có thể khiến message được đọc lại nếu crash ở khoảng giữa. Vì vậy, consumer vẫn cần idempotency.

Kafka ordering được bảo đảm trong partition, không phải trên toàn topic. Nếu cần thứ tự theo aggregate, producer nên chọn key ổn định như aggregate ID để các event của cùng aggregate đi vào cùng partition.

## 16. Giới hạn tài nguyên và bảo vệ broker

Broker là hạ tầng dùng chung. Một producer hoặc consumer không kiểm soát có thể làm ảnh hưởng nhiều ứng dụng khác.

Cần cấu hình và theo dõi:

- Connection và channel limit.
- Consumer concurrency và prefetch.
- Message size và payload size limit.
- Queue length, disk watermark và memory watermark.
- Producer rate và consumer throughput.
- Retry/backoff khi broker quá tải.
- Timeout và circuit breaker cho downstream.
- Rate limit hoặc quota theo vhost, tenant hay client nếu nền tảng hỗ trợ.

Không đưa file lớn hoặc dữ liệu nhị phân lớn vào event nếu có thể lưu object ở storage và chỉ gửi reference. Payload quá lớn làm tăng network, disk, memory và thời gian serialization.

Khi broker quá tải, ứng dụng cần backpressure thay vì tăng concurrency vô hạn. Giới hạn số worker, tạm dừng intake hoặc giảm tốc độ publish có thể bảo vệ toàn hệ thống tốt hơn.

## 17. Observability và health check

Cấu hình broker production cần được quan sát. Một kết nối đang mở không có nghĩa message được route, consumer xử lý hoặc backlog đang giảm.

Các metric nên theo dõi:

- Số connection/channel và reconnect.
- Publish confirm ack/nack và returned message.
- Message ready, unacknowledged và queue depth.
- Consumer count, throughput và processing latency.
- Retry, requeue, dead-letter và redrive.
- Consumer lag/offset khi dùng Kafka.
- Handler error rate và event age.
- Outbox backlog hoặc publication incomplete.

Health check nên phân biệt liveness và readiness. Liveness cho biết process còn sống; readiness cho biết ứng dụng có đủ khả năng nhận traffic hoặc message theo chính sách. Nếu broker tạm thời mất kết nối, không nhất thiết restart liên tục toàn bộ ứng dụng; có thể để client recovery và readiness phản ánh tình trạng phụ thuộc.

Log có cấu trúc nên chứa event ID, event type, source, destination, routing key/topic, consumer, attempt và correlation ID. Không ghi password, token hoặc toàn bộ payload nhạy cảm. Metric tag cần cardinality thấp; ID cụ thể nên ở log hoặc trace.

## 18. Thay đổi cấu hình và triển khai an toàn

Thay đổi broker config có thể ảnh hưởng toàn bộ consumer. Cần triển khai theo thứ tự có kiểm soát:

1. Tạo hoặc cập nhật exchange, queue, binding, topic, policy và quyền ở broker.
2. Xác minh topology và credential từ môi trường ứng dụng.
3. Deploy consumer có khả năng đọc schema hiện tại và schema mới nếu migration yêu cầu.
4. Deploy producer hoặc adapter với routing/serializer mới.
5. Theo dõi confirm, routing, backlog, retry và error rate.
6. Chuyển traffic theo batch hoặc feature flag nếu cần.
7. Giữ phương án rollback và checkpoint.
8. Gỡ tài nguyên cũ sau khi hết cửa sổ replay/rollback.

Không đổi routing key, queue arguments hoặc schema đồng thời nếu chưa có kế hoạch tương thích. Một số thay đổi queue arguments yêu cầu xóa/tạo lại queue và có thể làm mất message nếu thao tác không đúng. Với production, dùng policy hoặc migration procedure đã được kiểm chứng khi broker hỗ trợ.

Nếu đổi credential, có thể triển khai credential mới song song, xác minh kết nối rồi thu hồi credential cũ. Tránh đổi secret và restart toàn bộ consumer cùng lúc nếu điều đó tạo connection storm hoặc backlog lớn.

## 19. Kiểm thử cấu hình broker trước production

Kiểm thử cần bao phủ cấu hình client và hành vi broker thật, không chỉ kiểm tra file YAML.

| Nhóm | Scenario | Kỳ vọng |
|---|---|---|
| Kết nối | Broker không khả dụng lúc startup | Timeout/recovery đúng chính sách |
| Bảo mật | Credential sai hoặc TLS certificate không hợp lệ | Kết nối bị từ chối và có log rõ |
| Topology | Exchange/queue/binding thiếu | Phát hiện lỗi cấu hình, không mất message âm thầm |
| Routing | Publish routing key không có binding | Return hoặc cảnh báo theo mandatory policy |
| Durability | Broker restart | Topology và message bền vững theo cấu hình |
| Confirm | Broker ack/nack hoặc timeout | Producer ghi nhận đúng trạng thái |
| Consumer ack | Consumer crash trước ack | Message được giao lại theo semantics |
| Retry | Dependency lỗi tạm thời | Retry có giới hạn và backoff |
| Dead-letter | Payload không hợp lệ | Message tới đúng DLQ |
| Idempotency | Message được giao lại | Không tạo side effect trùng |
| Ordering | Event cùng aggregate | Tuân thủ partition/serialization policy |
| Capacity | Backlog tăng | Backpressure và cảnh báo hoạt động |

Dùng Testcontainers hoặc môi trường broker tương thích cho integration test cần xác minh exchange, queue, TTL, dead-letter, headers, acknowledgement hoặc partition. Mock chỉ phù hợp cho unit test logic mapping và xử lý lỗi.

Không dùng broker production để chạy test phá hủy topology. Test cần queue/topic riêng, vhost hoặc namespace riêng và cleanup có giới hạn. Với test asynchronous, chờ điều kiện theo timeout thay vì sleep cố định.

## 20. Các lỗi cấu hình thường gặp

**Đưa credential vào file cấu hình được commit.** Secret có thể bị lộ qua git history hoặc artifact. Hãy dùng secret manager/environment injection.

**Chỉ bật TLS phía client.** Certificate hoặc hostname verification có thể chưa đúng. Hãy kiểm tra trust chain và cấu hình broker/client đồng bộ.

**Nhầm publisher confirm với consumer completion.** Confirm chỉ xác nhận broker nhận publish theo semantics của broker. Hãy theo dõi consumer acknowledgement và business processing riêng.

**Dùng requeue ngay cho mọi exception.** Message có thể tạo vòng lặp nóng. Hãy phân loại lỗi và dùng retry có backoff/DLQ.

**Tăng prefetch và concurrency quá cao.** Database hoặc downstream có thể bị quá tải. Hãy điều chỉnh theo throughput và capacity thực tế.

**Không bật mandatory publish hoặc không xử lý return.** Message có thể không route tới queue nào mà producer không phát hiện. Hãy cấu hình routing failure rõ ràng.

**Coi durable queue là đủ để không mất message.** Cần xem cả message persistence, publisher confirm, queue type, replication và consumer ack.

**Để nhiều instance cùng tạo topology không nhất quán.** Queue declaration với arguments khác có thể thất bại. Hãy quản lý topology tập trung hoặc khai báo đồng nhất.

**Không version hóa payload.** Consumer có thể không đọc được message tồn từ phiên bản cũ. Hãy giữ contract tương thích và kiểm thử schema evolution.

**Cho rằng Event Publication Registry thay broker outbox.** Registry quản lý publication nội bộ; tính nguyên tử giữa database và broker cần cơ chế phù hợp như transactional outbox hoặc integration đã xác minh.

## Kết luận

Cấu hình broker production cần được thiết kế từ contract và yêu cầu độ tin cậy: topology, bảo mật, connection recovery, publisher confirm, acknowledgement, concurrency, retry, dead-letter, serialization và observability. Mỗi property cần gắn với một hành vi có thể kiểm thử và một người chịu trách nhiệm vận hành.

Trong Spring Modulith, giữ application event và business rule độc lập với broker. Dùng adapter để externalize hoặc nhận message, cấu hình broker theo semantics của transport, và phối hợp Event Publication Registry với outbox/inbox khi cần phục hồi bền vững. Khi topology được quản lý nhất quán, consumer idempotent và metric phản ánh đúng từng ranh giới, hệ thống có thể triển khai thay đổi broker mà vẫn giữ giao tiếp sự kiện đáng tin cậy.

