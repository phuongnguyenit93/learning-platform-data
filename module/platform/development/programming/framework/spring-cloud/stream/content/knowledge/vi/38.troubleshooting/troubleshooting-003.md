# Gửi thành công cục bộ nhưng broker hoặc consumer chưa nhận dữ liệu

Một ứng dụng Spring Cloud Stream ghi log “sent successfully” hoặc gọi `StreamBridge.send(...)` trả về `true`, nhưng Kafka topic không thấy record, RabbitMQ queue vẫn rỗng hoặc Pulsar consumer không chạy. Lỗi này rất dễ gây hiểu nhầm: **“gửi thành công” tại một điểm trong ứng dụng không có nghĩa broker đã xác nhận lưu hoặc định tuyến message; broker đã nhận cũng không đồng nghĩa consumer đã xử lý thành công nghiệp vụ**.

Để chẩn đoán, cần theo dấu từng ranh giới của đường đi sự kiện: hàm tạo message, output binding, binder/producer client, broker, input binding và consumer function. Bài học xây dựng phương pháp áp dụng cho Spring Cloud Stream sử dụng `Supplier`, `Function`, `Consumer` và `StreamBridge` trên Kafka, RabbitMQ hoặc Pulsar. Các ví dụ nhấn mạnh bằng chứng quan sát, cấu hình, lệnh kiểm tra, test tái hiện và cách sửa không gây mất hoặc nhân đôi dữ liệu.

## 1. “Thành công” thuộc mốc nào?

Một luồng message có nhiều mốc xác nhận độc lập:

~~~mermaid
flowchart LR
    A["Producer: tạo Message"] --> B["Spring Integration channel / binding"]
    B --> C["Binder + client buffer"]
    C --> D["Broker ACK / publisher confirm"]
    D --> E["Topic log hoặc queue/subscription"]
    E --> F["Consumer poll / delivery"]
    F --> G["Deserialize + invoke Function"]
    G --> H["Business side effect"]
    H --> I["Commit / ACK"]
~~~

| Mốc | Bằng chứng có thể thu thập | Kết luận hợp lệ | Chưa chứng minh |
|---|---|---|---|
| 1. Hàm được gọi | Log producer, test của `Function` | Code đã đến đoạn phát message | Binding đã nhận message |
| 2. Gửi vào channel thành công | `StreamBridge.send(...) == true` hoặc không có exception khi handoff | Đường gửi cục bộ chấp nhận message theo semantics hiện tại | Broker đã ghi nhận hoặc consumer nhận |
| 3. Producer/binder gửi lên mạng | Metrics send/request, log client, callback | Producer đang giao tiếp với broker | Broker đã ACK thành công |
| 4. Broker xác nhận | Kafka `RecordMetadata`, Rabbit publisher confirm/return, Pulsar send result | Broker xác nhận theo giao thức và cấu hình | Có subscriber hoặc consumer đã xử lý |
| 5. Record tồn tại/route đúng | Kafka topic/partition/offset, Rabbit queue/routing, Pulsar topic stats | Dữ liệu ở đúng destination hoặc đường định tuyến | Consumer ứng dụng đang đọc |
| 6. Consumer nhận message | Group/subscription metrics, log tại entrypoint | Client nhận hoặc broker giao message | DTO đã chuyển đổi đúng hoặc business thành công |
| 7. Nghiệp vụ xử lý | Business log, DB transaction, idempotency record | Side effect thành công theo hợp đồng | Commit/ACK luôn hoàn thành |
| 8. Offset commit/ACK | Kafka committed offset, Rabbit ACK/queue count, Pulsar subscription cursor | Broker ghi nhận tiến độ tiêu thụ | Business side effect chắc chắn exactly-once |

**Mục tiêu chẩn đoán là tìm ranh giới đầu tiên thiếu bằng chứng.** Nếu broker đã có record đúng topic nhưng consumer không nhận, việc chỉnh producer retry thường không giải quyết được. Nếu producer chưa được broker xác nhận, việc reset Kafka consumer offset cũng không giúp ích.

### Ví dụ gửi “thành công” nhưng chưa có bằng chứng broker ACK

~~~java
boolean accepted = streamBridge.send(
        "orders-out",
        MessageBuilder.withPayload(event)
                .setHeader("event-id", event.eventId())
                .build());

log.info("orders-out accepted={}", accepted);
~~~

Giá trị `true` phản ánh đường gửi qua Spring Integration/binding đã chấp nhận lời gọi, **không phải phiếu xác nhận bền vững từ Kafka/RabbitMQ/Pulsar**. Spring Cloud Stream cho phép `StreamBridge.setAsync(true)` để gửi trên thread khác; với chế độ bất đồng bộ, thời điểm ứng dụng kết thúc lời gọi càng không nên dùng làm bằng chứng broker ACK. Cả chế độ gửi thông thường lẫn async đều cần kiểm tra kết quả producer khi yêu cầu giao nhận đáng tin cậy.

## 2. Bắt đầu bằng một event ID và một trace có thể đối chiếu

Trước khi đổi bất cứ cấu hình nào, chọn một message thử nghiệm có dấu hiệu nhận dạng ổn định:

~~~json
{
  "eventId": "diag-order-2026-11-24-001",
  "orderId": "order-101",
  "amount": 250000
}
~~~

Đặt `event-id` ở message header và payload nếu hợp đồng cho phép. Ghi nhận tối thiểu:

- Môi trường, application instance, phiên bản ứng dụng, binder type.
- `spring.cloud.function.definition` đang chạy.
- Binding name ở producer và consumer.
- Destination thực tế: Kafka topic, Rabbit exchange/queue hoặc Pulsar topic.
- Broker address, cluster, Rabbit virtual host/Pulsar namespace, consumer group hoặc subscription.
- Thời điểm UTC, event ID, correlation ID và key/routing key.
- Tình trạng producer send result, broker counters và consumer log.

Đừng tạo event ID mới cho cùng một message khi retry. Nếu cùng message được giao lại, event ID ổn định giúp phát hiện duplicate và đối chiếu các lần thử. Không ghi toàn bộ payload hoặc token trong log chẩn đoán nếu chứa dữ liệu nhạy cảm.

**Mẫu log có cấu trúc:**

~~~json
{
  "timestamp": "2026-11-24T09:00:00Z",
  "service": "order-api",
  "operation": "message.publish.accepted",
  "event_id": "diag-order-2026-11-24-001",
  "binding": "orders-out",
  "broker": "kafka",
  "destination": "orders.events",
  "accepted_locally": true,
  "broker_confirmation": "pending"
}
~~~

`broker_confirmation=pending` nghĩa là *chưa có bằng chứng xác nhận tại thời điểm log*, không có nghĩa broker đã từ chối. Nên dùng trạng thái `pending`, `confirmed`, `failed` hoặc `unknown` để phân biệt “chưa biết” và “thất bại”.

## 3. Cây quyết định chẩn đoán nhanh

~~~mermaid
flowchart TD
    A["App ghi 'gửi thành công'"] --> B{"Producer ACK / send result?"}
    B -->|"Chưa có hoặc lỗi"| C["Kiểm tra channel, binder, serialize, broker address, ACL, network, async error channel"]
    B -->|"Có"| D{"Broker có record/route?"}
    D -->|"Sai topic hoặc không route"| E["Kiểm tra destination, KafkaHeaders.TOPIC, exchange/routing key, namespace"]
    D -->|"Có"| F{"Consumer binding đang RUNNING?"}
    F -->|"Không"| G["Kiểm tra function definition, group, binder, lifecycle, subscription"]
    F -->|"Có"| H{"Broker đã giao/consumer fetch?"}
    H -->|"Chưa"| I["Kiểm tra offset/cursor, consumer lag, assignment, queue name"]
    H -->|"Đã giao"| J{"Function đã xử lý?"}
    J -->|"Không"| K["Kiểm tra contentType, Serde/schema, retry, DLT/DLQ, filter, exception"]
    J -->|"Có"| L["Đối chiếu side effect, transaction, ACK/commit và idempotency"]
~~~

Quy trình luôn so sánh **cùng môi trường, cùng cluster và cùng event ID**. Một ứng dụng trỏ tới broker phát triển trong khi người vận hành kiểm tra production là nguyên nhân khá phổ biến của tình huống “topic trống”.

## 4. Kiểm tra function và binding trước khi nhìn broker

Spring Cloud Stream ánh xạ function bean vào input/output binding. Nếu tên binding sai, ứng dụng có thể chạy bình thường nhưng message được gửi đến một output khác.

Ví dụ:

~~~java
record OrderEvent(String eventId, String orderId, long amount) {
}

interface OrderService {
    void handle(OrderEvent event);
}

@Bean
Consumer<Message<OrderEvent>> consumeOrder(OrderService orderService) {
    return message -> {
        log.info("Consumer entered event-id={}",
                message.getHeaders().get("event-id"));
        orderService.handle(message.getPayload());
    };
}
~~~

Với function `consumeOrder`, input binding mặc định là `consumeOrder-in-0`. Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: consumeOrder
    stream:
      bindings:
        consumeOrder-in-0:
          destination: orders.events
          group: order-worker
        orders-out:
          destination: orders.events
~~~

`orders-out` ở đây là tên binding dùng bởi `StreamBridge`, không phải tên function bean. Khi gửi bằng `StreamBridge.send("orders-out", message)`, cấu hình tương ứng ánh xạ sang destination `orders.events`.

### Những lỗi cấu hình đáng kiểm tra đầu tiên

| Trường hợp | Hậu quả | Cách kiểm tra |
|---|---|---|
| `spring.cloud.function.definition` không trỏ tới function nhận | Không tạo input binding mong muốn | Kiểm tra bean function và log binding lúc khởi động |
| Sai suffix `-in-0`, `-out-0` | Cấu hình binding không áp dụng lên cổng thực | Đối chiếu function name với binding name |
| `StreamBridge.send` dùng nhầm tên | Có thể tạo dynamic destination khác | Ghi log binding name và truy vấn trạng thái bindings |
| Output binding có `destination` khác dự kiến | Message đi sang topic/exchange khác | Kiểm tra cấu hình runtime, không chỉ file YAML nguồn |
| Bật `KafkaHeaders.TOPIC` override | Producer có thể ghi sang topic do header chỉ định | Kiểm tra `useTopicHeader` của Kafka binder và header thực |
| Có nhiều binder nhưng chọn nhầm | Message được gửi qua Rabbit thay vì Kafka hoặc ngược lại | Kiểm tra binder per binding hoặc đối số binderName của StreamBridge |
| Test Binder nằm trên classpath | Message chỉ đi qua channel in-JVM | Kiểm tra binder thực tế, không dựa vào test pass |
| Consumer binding dừng | Broker có dữ liệu nhưng function không chạy | Kiểm tra lifecycle binding và health |

Khi `spring.cloud.function.definition` chứa `functionA|functionB`, tên binding phụ thuộc vào function composition và có thể khác từng bean riêng. Khi dùng dấu chấm phẩy để kích hoạt nhiều function độc lập, mỗi function có binding riêng. Không tự suy tên binding; hãy xem logs startup, `/actuator/bindings` và cấu hình hiệu lực.

## 5. Xem trạng thái binding qua Actuator

Thêm Spring Boot Actuator và mở endpoint bindings cho người quản trị:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,bindings
~~~

Các truy vấn chỉ đọc:

~~~http
GET /actuator/bindings
GET /actuator/bindings/consumeOrder-in-0
GET /actuator/bindings/orders-out
GET /actuator/health
~~~

Endpoint bindings cho thấy binding đang chạy, dừng hoặc có trạng thái lifecycle tương ứng. Nếu consumer binding `STOPPED`, hãy tìm nguyên nhân ở actuator/admin/config hoặc lỗi startup; không tự động gửi lại event trước khi xác nhận đường đi.

Endpoint bindings cũng có thao tác đổi state, nhưng **đừng POST START/STOP như một bước chẩn đoán mặc định** khi đang ở production. Việc này có thể gây rebalance, thay đổi thứ tự xử lý và ảnh hưởng consumer group. Chỉ thao tác theo runbook được cấp quyền và có phương án rollback.

Đối với Kafka Streams, cần kiểm tra thêm state của KafkaStreams instance, thread và task; một process Spring Boot vẫn có thể sống khi stream thread đã lỗi. Với RabbitMQ hoặc Pulsar, quan sát kết nối listener/subscription trên broker để xác nhận binding thực sự đã đăng ký.

## 6. Dùng log và metrics đúng tầng

Nên ghi log ở bốn thời điểm riêng:

1. `publish.requested` — ứng dụng tạo message.
2. `publish.accepted_locally` — lời gọi send được chấp nhận.
3. `publish.broker_confirmed` hoặc `publish.failed` — có kết quả producer/broker.
4. `consume.received` và `consume.processed` — consumer nhận và hoàn tất nghiệp vụ.

Không ghi “delivered” ở bước 2. Nếu chưa có callback xác nhận từ binder, dùng “accepted”, “dispatched” hoặc “pending”.

Một dashboard có thể bao gồm:

| Chỉ số | Lý do |
|---|---|
| Producer local attempts/success/failure | Biết ứng dụng có thực sự phát lệnh gửi |
| Producer client request/error/retry rate | Phát hiện timeout, authorization, connection issue |
| Broker accepted/published rate | Xác minh broker có nhận tải |
| Topic/queue/subscription backlog | Xác định message tích tụ ở đâu |
| Consumer assignments, poll/delivery rate | Xác nhận consumer đang nhận |
| Conversion error, retry, DLT/DLQ rate | Phát hiện đã nhận nhưng lỗi trước business function |
| Business success/failure rate | Đối chiếu event với side effect |

Log event ID có cardinality cao, phù hợp với log hoặc trace, **không dùng làm nhãn metrics**. Metrics nên dùng application, destination, status, broker và các chiều có số giá trị được kiểm soát.

## 7. Tình huống Spring Integration Test Binder đánh lừa kết quả

Spring Cloud Stream cung cấp `spring-cloud-stream-test-binder` để kiểm thử không cần Kafka/RabbitMQ/Pulsar. Test Binder chuyển message trong JVM. Khi nó có mặt trên test classpath và được dùng trong Spring context, `OutputDestination.receive(...)` có thể nhận message dù không có broker thực nào đang chạy.

Vì vậy:

- Unit/integration test với Test Binder chỉ xác nhận luồng function và binding giả lập.
- Kiểm thử producer delivery phải khởi động binder thật và broker thật (ví dụ Testcontainers).
- Không trộn Test Binder và real middleware binder trong cùng test module nếu không có cấu hình tách biệt rõ ràng; tài liệu Spring Cloud Stream khuyến nghị dùng module test riêng.
- Trong runtime production, xác nhận loại binder và kết nối broker qua log + metrics, không suy ra từ việc application context đã khởi động.

**Dấu hiệu:** Test ghi “send true, OutputDestination received” nhưng Kafka console consumer hoặc Rabbit Management không có message. Đây không phải bằng chứng broker làm mất dữ liệu; có thể toàn bộ test chỉ diễn ra trong JVM.

## 8. Kafka: lấy bằng chứng producer đã được broker xác nhận

Kafka producer thường hoạt động bất đồng bộ. Để biết một record đã được broker ghi nhận ở đâu, Kafka binder cung cấp `recordMetadataChannel` cho output binding.

Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out:
          destination: orders.events
          producer:
            error-channel-enabled: true
      kafka:
        bindings:
          orders-out:
            producer:
              record-metadata-channel: kafkaPublishMetadata
~~~

Đăng ký channel và listener nhận kết quả thành công:

~~~java
import org.apache.kafka.clients.producer.RecordMetadata;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.kafka.support.KafkaHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;

@Configuration(proxyBeanMethods = false)
class KafkaPublishDiagnostics {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaPublishDiagnostics.class);

    @Bean("kafkaPublishMetadata")
    MessageChannel kafkaPublishMetadata() {
        return new DirectChannel();
    }

    @ServiceActivator(inputChannel = "kafkaPublishMetadata")
    void onPublished(Message<?> message) {
        RecordMetadata metadata = message.getHeaders()
                .get(KafkaHeaders.RECORD_METADATA, RecordMetadata.class);
        if (metadata != null) {
            log.info("Broker confirmed topic={}, partition={}, offset={}",
                    metadata.topic(), metadata.partition(),
                    metadata.offset());
        }
    }
}
~~~

`KafkaHeaders.RECORD_METADATA` chứa `RecordMetadata` do Kafka client trả về khi send thành công, bao gồm topic, partition và offset. **Đây là bằng chứng mạnh hơn `StreamBridge.send() == true`.** Nếu callback không đến, kiểm tra client/binder error, timeout, callback registration và trạng thái producer; không vội kết luận record bị mất.

### Bắt lỗi gửi bất đồng bộ

Thuộc tính chung:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out:
          producer:
            error-channel-enabled: true
~~~

Với binder hỗ trợ async result, lỗi gửi có thể được chuyển tới producer error channel tương ứng. Đăng ký error handler theo tên channel của binder/version (hoặc xử lý qua global Spring Integration `errorChannel` nếu có route) và lưu loại lỗi, destination, event ID, stack trace đã lọc dữ liệu nhạy cảm. Không coi `error-channel-enabled` là cơ chế tự retry hoặc lưu an toàn message: ứng dụng phải quyết định cách cảnh báo, lưu lại, hoặc retry phù hợp.

Ví dụ lỗi cần tìm trong Kafka producer:

- `TimeoutException` khi broker không phản hồi trong giới hạn delivery.
- `SerializationException` hoặc lỗi chuyển đổi payload trước khi gửi.
- `TopicAuthorizationException`, `ClusterAuthorizationException` hoặc ACL từ chối.
- `UnknownTopicOrPartitionException` nếu topic không tồn tại và auto provision không có.
- `RecordTooLargeException` hoặc policy kích thước message không tương thích.
- `NotEnoughReplicasException` khi replica/min-ISR không đáp ứng cấu hình.

Một lỗi có thể xuất hiện đồng bộ ngay lúc send hoặc bất đồng bộ sau khi method trả về; cần theo dõi cả exception tại caller và callback/error channel.

## 9. Kafka: kiểm tra broker, topic và partition

Dùng Kafka CLI với quyền truy cập và endpoint đúng cluster. Lệnh dưới đây là ví dụ chẩn đoán chỉ đọc:

~~~bash
kafka-topics.sh \
  --bootstrap-server kafka-broker:9092 \
  --describe \
  --topic orders.events
~~~

Đối chiếu topic tồn tại, số partition, leader, replica/ISR, ACL và khả năng producer ghi vào đúng cluster. Topic cùng tên ở hai cluster không phải cùng một nguồn dữ liệu.

Đọc message bằng **consumer group chẩn đoán riêng**, không dùng group production để tránh thay đổi assignment:

~~~bash
kafka-console-consumer.sh \
  --bootstrap-server kafka-broker:9092 \
  --topic orders.events \
  --group diag-orders-001 \
  --from-beginning \
  --property print.key=true \
  --property print.partition=true \
  --property print.offset=true
~~~

`--from-beginning` có tác dụng với group chưa có committed offset (hoặc partition chưa có offset) theo điều kiện cấu hình. Với group đã có committed offset, Kafka ưu tiên offset đã lưu; đổi một flag trên console consumer không tự động reset tiến độ group. Nếu message chứa dữ liệu nhạy cảm, chỉ dùng payload thử nghiệm hoặc topic được cấp phép; không in dữ liệu cá nhân ra terminal.

Khi thấy record có key/partition/offset cụ thể, ghi lại thông tin này và chuyển sang tầng consumer. Nếu probe group không đọc được, chưa kết luận không có record: hãy kiểm tra retention, timestamp, ACL, offset, tên cluster và trạng thái broker.

### Kafka native key và topic override

Nếu dùng `KafkaHeaders.KEY`, cùng key thường được producer phân vùng ổn định theo số partition tại thời điểm gửi. Một key nóng có thể dồn record vào một partition, khiến consumer ở partition khác không có dữ liệu dù toàn topic có traffic.

Kafka binder hỗ trợ `useTopicHeader`: khi bật, header `KafkaHeaders.TOPIC` có thể ghi đè destination của output binding. Nếu ứng dụng phát message tới topic động, phải kiểm tra **topic cuối cùng từ RecordMetadata**, không chỉ tên binding trong source code.

## 10. Kafka: consumer group, offset và lag

Broker có record nhưng consumer không log gì thường do trạng thái group hoặc offset. Trước tiên kiểm tra:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server kafka-broker:9092 \
  --describe \
  --group order-worker
~~~

Đối chiếu `CURRENT-OFFSET`, `LOG-END-OFFSET` và `LAG` theo **từng partition**; xem `CONSUMER-ID`, `HOST` và `CLIENT-ID` để xác định assignment.

| Quan sát | Khả năng | Bước tiếp theo |
|---|---|---|
| Không có group | Consumer chưa được tạo, dùng sai group hoặc chưa commit | Kiểm tra function definition, binding destination/group và app logs |
| Group có members nhưng không có partition assignment phù hợp | Rebalance, nhiều consumer hơn partitions, topic không khớp | Xem metadata, subscription và số partition |
| Lag bằng 0 và group có committed offset cuối | Consumer đã đọc/commit hoặc bỏ qua trước đó | Xem consumer function, side effect, retry/DLT và offset history |
| Một partition tăng lag, các partition khác gần 0 | Hot key, xử lý chậm hoặc consumer không ổn định | Kiểm tra key skew, poll/process/commit latency |
| Lag tăng ở mọi partition | Không có consumer hoạt động, không có quyền đọc hoặc throughput quá thấp | Kiểm tra connection, ACL, group và sức chứa |
| Group mới không đọc lịch sử | Offset reset policy là latest hoặc nhóm bắt đầu sau khi record được gửi | Thử group độc lập với earliest khi thật sự cần lịch sử |

**Quan trọng:** chính sách offset khởi đầu (`startOffset` / Kafka `auto.offset.reset`) thường chỉ áp dụng khi consumer group chưa có committed offset hợp lệ. Thay property này không tự replay các record đã được commit. Spring Cloud Stream Kafka binder mặc định `startOffset=earliest` cho binding có group tường minh và `latest` cho anonymous group; hành vi thực tế còn phụ thuộc giá trị `resetOffsets`.

Ví dụ cho consumer group mới:

~~~yaml
spring:
  cloud:
    function:
      definition: consumeOrder
    stream:
      bindings:
        consumeOrder-in-0:
          destination: orders.events
          group: order-worker
      kafka:
        bindings:
          consumeOrder-in-0:
            consumer:
              start-offset: earliest
              reset-offsets: false
~~~

`reset-offsets: false` nghĩa là **không ép reset tiến độ đã commit**. Không bật `reset-offsets: true` trên group production để “thử xem có đọc được không” vì có thể gây replay hàng loạt, duplicate side effect và làm thay đổi tiến độ đã được xác nhận.

### Commit không đồng nghĩa business success

Nếu consumer đọc message rồi code nuốt exception, log “ignored” hoặc ACK trước khi DB transaction commit, offset/cursor có thể tiến nhưng nghiệp vụ chưa hoàn thành. Ngược lại, nếu DB commit thành công nhưng consumer crash trước Kafka offset commit, message có thể được phát lại: consumer cần idempotency.

Khi log không thấy function chạy dù group offset tiến, kiểm tra các lớp trước function: deserializer, content conversion, filter, retry, DLT/handler. Không khẳng định “Kafka làm mất dữ liệu” chỉ vì offset đã tăng.

## 11. Kafka: producer config, network, bảo mật và transaction

Các bước xác minh producer:

1. Đọc **effective config** của binder: `spring.cloud.stream.kafka.binder.brokers`, security protocol, SASL/TLS, producer properties.
2. Kiểm tra producer kết nối đúng bootstrap server; metadata trả về đúng listener address có thể truy cập từ app/container.
3. Kiểm tra topic ACL: `Describe` và `Write` hoặc quyền cần thiết.
4. Quan sát broker producer request, timeouts và callback; không dựa vào log KafkaProducer init.
5. Đối chiếu `acks`, `delivery.timeout.ms`, `retries`, `enable.idempotence`, topic ISR và policy lỗi của cluster.
6. Nếu binder bật transaction, kiểm tra transaction commit/abort, transaction fencing và cấu hình consumer `isolation.level`.

**Kafka transactions:** producer có thể gửi record trong một transaction chưa commit; consumer dùng `read_committed` sẽ không thấy record chưa commit/đã abort, dù producer đã gọi send và nhận callback nội bộ cho record. “Send callback thành công” trong transaction không thay thế **transaction commit thành công**. Cần quan sát cả lifecycle transaction.

Đối với publisher đơn giản không có transaction, Kafka `acks=all` là mức xác nhận mạnh hơn `acks=1` về replica theo chính sách broker, nhưng không tự tạo exactly-once business processing. Không tự thay đổi `acks` hoặc `min.insync.replicas` khi đang điều tra nếu chưa đánh giá trade-off về độ bền dữ liệu và availability.

## 12. RabbitMQ: exchange nhận message nhưng queue rỗng

RabbitMQ publish vào **exchange**, sau đó exchange route tới queue theo binding và routing key. Nếu exchange tồn tại nhưng không có queue/binding phù hợp, message có thể không đến queue nào. Producer vẫn có thể nhận publisher confirm cho việc broker đã xử lý publish, trong khi message không được route.

~~~mermaid
flowchart LR
    A["Spring Cloud Stream Rabbit producer"] --> B["Exchange: orders.events"]
    B -->|"routing key phù hợp"| C["Queue: orders.events.order-worker"]
    B -->|"Không có matching binding"| D["Unroutable / returned nếu mandatory"]
    C --> E["Consumer group order-worker"]
~~~

**Phân biệt hai tín hiệu RabbitMQ:**

- **Publisher confirm (ACK/NACK):** broker xác nhận/xử lý lệnh publish ở phía producer theo cơ chế confirm.
- **Publisher return:** với publish có `mandatory`, broker trả về message không thể route tới queue (thay vì im lặng bỏ qua).

Publisher confirm ACK **không tự bảo đảm đã có consumer xử lý**, và cũng không bảo đảm message được route tới một queue khi không có route. Phải quan sát cả returned message và queue counters.

### Cấu hình callback và error channel

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq
    port: 5672
    publisher-confirm-type: correlated
    publisher-returns: true
  cloud:
    stream:
      bindings:
        orders-out:
          destination: orders.events
          producer:
            error-channel-enabled: true
      rabbit:
        bindings:
          orders-out:
            producer:
              confirm-ack-channel: rabbitPublishConfirms
~~~

Rabbit binder hỗ trợ `confirmAckChannel` để nhận positive publisher confirms và `useConfirmHeader` để lấy kết quả qua correlation-data future; đây là hai cơ chế thay thế nhau, **không bật cả hai**. Trong ví dụ, ứng dụng phải cấu hình channel/listener để quan sát ACK. Connection factory phải hỗ trợ correlated publisher confirms. Để phát hiện unroutable return, cần publisher returns và cấu hình mandatory/return behavior tương ứng; kiểm tra theo Spring Boot, Spring AMQP và phiên bản binder được dùng.

Rabbit binder có thể chuyển returned messages và negative publisher confirms vào error channel khi các tùy chọn được hỗ trợ/bật. Returned message có thông tin reply code/text, exchange và routing key; đây là bằng chứng mạnh cho lỗi định tuyến.

### Kiểm tra queue topology trên broker

Trong RabbitMQ Management UI hoặc HTTP API, kiểm tra:

- Vhost của producer và consumer có giống nhau không?
- Exchange `orders.events` có tồn tại và đúng type không?
- Queue thực tế tên gì? Với group, binder thường dùng tên gồm destination + group (trừ khi đổi `queueNameGroupOnly` hoặc prefix).
- Queue có được bind vào exchange đúng routing key/pattern không?
- Counters `publish`, `deliver`, `ack`, `messages_ready` và `messages_unacknowledged` đang thay đổi ra sao?
- Có alternate exchange, TTL, max-length, overflow, dead-letter exchange hoặc queue auto-delete/exclusive không?

`messages_ready=0` không chứng minh producer không gửi: consumer có thể đã nhận/ACK rất nhanh. `messages_unacknowledged>0` cho thấy message đã giao nhưng chưa được ACK. Nếu `publish` tăng mà queue không tăng và returns có `NO_ROUTE`, vấn đề nằm ở routing/topology.

## 13. RabbitMQ: có queue nhưng Consumer chưa thấy message

Sau khi chứng minh message được route tới queue, kiểm tra **consumer thực tế**, không chỉ số message còn chờ:

| Dấu hiệu ở RabbitMQ | Diễn giải có thể | Hướng xử lý |
|---|---|---|
| Queue có `messages_ready > 0`, `consumers = 0` | Chưa có consumer attach | Kiểm tra function definition, binding group, vhost, service availability |
| Queue có `messages_ready > 0`, consumers đang hoạt động | Consumer bị chặn bởi prefetch, flow control hoặc năng lực xử lý thấp | Xem unacked count, listener errors, connection và thread pool |
| `messages_unacknowledged` tăng liên tục | Message đã được giao nhưng không ACK | Kiểm tra listener bị treo, DB/API timeout, acknowledgment mode |
| Queue luôn rỗng nhưng consumer log có event | Consumer có thể xử lý quá nhanh nên queue không tích tụ | Kiểm tra business outcome và ACK |
| DLQ tăng | Consumer nhận nhưng reject/retry đã hết hoặc TTL/delivery limit | Kiểm tra DLX, error logs, retry policy và payload lỗi |
| Queue khác nhận dữ liệu | Sai tên queue/group hoặc `queueNameGroupOnly`/prefix khác | So sánh destination/group trên cả hai phía |
| Queue biến mất sau restart | Anonymous/auto-delete/exclusive/ephemeral queue | Xem durability, autoDelete, group và khai báo |

Trong Rabbit binder, consumer group tường minh thường tạo queue tên gồm destination và group. Nếu producer gửi trước khi queue/binding được tạo, message không được tự động lưu chờ consumer chỉ vì exchange đã tồn tại. Với hệ thống bắt buộc không mất message, phải provision queue/binding đủ sớm và có chính sách publisher confirms/returns, durability, persistent delivery và retry.

Ví dụ consumer group:

~~~yaml
spring:
  cloud:
    function:
      definition: consumeOrder
    stream:
      bindings:
        consumeOrder-in-0:
          destination: orders.events
          group: order-worker
~~~

Nếu broker đang có queue `orders.events.other-worker` nhưng ứng dụng dùng `group=order-worker`, việc nhìn queue đầu tiên sẽ đưa ra kết luận sai. Đối chiếu vhost, exchange, queue, binding key và nhóm consumer hiệu lực.

### ACK, requeue và dead letter

Khi business function ném exception, Rabbit binder/listener có thể retry, reject, requeue hoặc chuyển DLQ theo cấu hình. Tùy policy, message có thể biến mất khỏi queue chính nhưng nằm trong DLQ; consumer chính có thể không tạo log thành công. Hãy kiểm tra `autoBindDlq`, `republishToDlq`, delivery limit, TTL và queue overflow trước khi kết luận mất message.

Đừng liên tục requeue một poison message không thể deserialize: nó có thể gây vòng lặp, làm nghẽn các message khác. Ghi nhận event ID, loại exception, routing key, số lần giao lại và DLQ destination.

## 14. Pulsar: producer thành công không đồng nghĩa subscription tiêu thụ

Spring Cloud Stream Pulsar binder sử dụng client và topic provisioner của Spring for Apache Pulsar. Một topic thường có dạng:

~~~text
persistent://public/default/orders.events
~~~

Các thành phần tenant, namespace, topic, persistence type và broker cluster phải khớp với môi trường cần kiểm tra. Một client có thể kết nối thành công tới Pulsar nhưng ghi sang namespace khác do default namespace hoặc destination cấu hình khác.

Các cấp bằng chứng:

1. Application đã gọi gửi qua output binding.
2. Pulsar producer client đã nhận kết quả publish (message ID hoặc send result).
3. Topic stats cho thấy producer/rate in/counter tăng.
4. Subscription được tạo và có consumer đúng tên/type.
5. Consumer stats cho thấy message được dispatch, ack hoặc redeliver.
6. Function xử lý đúng schema và side effect.

Kết quả `StreamBridge.send()` của Spring Cloud Stream không phải API chờ Pulsar `MessageId`. Khi cần quan sát publish ở cấp broker, dùng callback/metrics/cơ chế gửi được Pulsar binder và Spring Pulsar version hỗ trợ, hoặc client kiểm chứng độc lập. Đừng gắn nhãn “broker confirmed” cho một log chỉ xuất hiện ngay sau lời gọi StreamBridge.

### Kiểm tra kết nối và namespace

Các thuộc tính thường dùng:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-broker:6650
    administration:
      service-url: http://pulsar-broker:8080
  cloud:
    stream:
      bindings:
        orders-out:
          destination: persistent://public/default/orders.events
        consumeOrder-in-0:
          destination: persistent://public/default/orders.events
          group: order-worker
~~~

Pulsar broker URL (`pulsar://...`) khác admin HTTP URL. Nếu topic provisioner không có quyền hoặc admin URL trỏ sai cluster, consumer hoặc producer có thể startup lỗi dù một phần ứng dụng chạy bình thường. Không dùng URL admin để thay thế service URL của producer/consumer.

### Truy vấn topic stats

~~~bash
pulsar-admin topics stats persistent://public/default/orders.events
~~~

Các field đáng xem trong kết quả (tên và vị trí có thể thay đổi theo Pulsar version):

- `msgRateIn`, `msgInCounter` và danh sách `publishers`.
- `msgRateOut`, `msgOutCounter`.
- `subscriptions` và tên subscription.
- `msgBacklog`, `unackedMessages`, `msgRateRedeliver` theo subscription.
- `consumers`, `availablePermits`, subscription type và active consumer.

`msgRateIn > 0` chứng minh broker có nhận lưu lượng trên topic trong cửa sổ quan sát, nhưng không chứng minh chính event ID cần tìm đã được publish. Hãy kết hợp message ID, timestamps và log producer/consumer. Với topic phân vùng, kiểm tra các partition nội bộ hoặc aggregate stats tương ứng để tránh bỏ sót một partition.

## 15. Pulsar: subscription, cursor và redelivery

Pulsar không dùng Kafka consumer group offset theo cùng cách. Subscription có cursor riêng; tên subscription khác nhau có tiến độ đọc khác nhau.

| Quan sát | Khả năng | Hướng kiểm tra |
|---|---|---|
| Topic `msgRateIn` tăng nhưng không có subscription dự kiến | Consumer chưa subscribe hoặc đang dùng tên khác | Kiểm tra function/group, service URL và subscription name |
| Subscription có `msgBacklog > 0` và không có consumer | Consumer dừng, lỗi kết nối hoặc subscription chưa attach | Xem consumer instances, errors và ACL |
| `unackedMessages` cao | Broker đã dispatch nhưng consumer chưa ACK | Kiểm tra xử lý bị treo, ack timeout, listener errors |
| `msgRateRedeliver` tăng | Message được giao lại do NACK/timeout/retry | Kiểm tra exception và DLQ/retry letter |
| Subscription mới không đọc event cũ | Subscription initial position tạo sau message, hoặc retention/cursor policy | Kiểm tra thời điểm tạo subscription và initial position |
| Shared consumer khác nhận message | Nhiều consumer cùng một subscription chia traffic | Kiểm tra type `Shared`/`Key_Shared` và consumer assignment |
| Failover consumer đứng chờ | Consumer hiện tại là standby của subscription `Failover` | Xác nhận active consumer |
| Schema lỗi | Producer/consumer không thống nhất schema hoặc payload type | Xem binder native decoding, schema registry và exception |

Subscription `Exclusive` chỉ cho một consumer active; `Failover` có active/standby; `Shared` phân tán message mà không bảo đảm thứ tự; `Key_Shared` dùng key để giữ ordering theo key trong các điều kiện hỗ trợ. Không xem một consumer cụ thể không nhận message là lỗi nếu broker đang giao nó cho consumer khác theo semantics subscription.

Nếu subscription được tạo sau khi message đã publish, initial position và retention quyết định liệu event cũ có được đọc hay không. **Không reset cursor production chỉ để thử chẩn đoán**: điều đó có thể replay hoặc bỏ qua message. Dùng subscription chẩn đoán mới với cấu hình initial position rõ ràng và quyền truy cập phù hợp.

## 16. Đã tới consumer nhưng message conversion thất bại

Một message có thể đã được fetch/deliver nhưng `Consumer<T>` chưa được gọi vì lỗi xảy ra trước function, chẳng hạn:

- Byte array không chuyển thành DTO theo content type.
- Producer bật native encoding còn consumer dùng nhầm framework decoding, hoặc ngược lại.
- Kafka key/value deserializer không tương thích serializer.
- Kafka Streams `Serde` hoặc schema của state store không tương thích.
- RabbitMQ AMQP content type hoặc message converter khác kỳ vọng.
- Pulsar JSON/Avro/Protobuf schema và message type khác nhau.
- Header mapper loại bỏ event type, correlation ID, key hoặc contentType cần thiết.
- Message có payload quá lớn hoặc định dạng không hợp lệ.

Ví dụ function có target type rõ ràng:

~~~java
@Bean
Consumer<OrderEvent> consumeOrder(OrderService orderService) {
    return event -> orderService.handle(event);
}
~~~

Nếu wire payload là JSON nhưng consumer cấu hình sai `content-type` hoặc native `Deserializer`, lỗi có thể phát sinh ở binder trước khi function được gọi. Kiểm tra app log, binding error channel, retry counters và DLQ/DLT. Đừng chỉ đặt log trong body của `Consumer`: cần log hoặc metrics ở tầng binder/container để biết lỗi trước invocation.

### So sánh producer và consumer content configuration

| Cấu hình | Producer | Consumer |
|---|---|---|
| Framework JSON conversion | `content-type: application/json`, payload phù hợp | Target type `OrderEvent`; content type được truyền/hiểu đúng |
| Kafka native serde | `use-native-encoding: true` + serializer | `use-native-decoding: true` + deserializer |
| Kafka Streams | Producer serde/key/value đúng | Topology `Consumed.with(...)` hoặc binder serde properties đúng |
| Pulsar native schema | `schema-type` và `message-type` phù hợp | Schema/message type tương thích |
| RabbitMQ | AMQP headers và payload encoding phù hợp | Message converter hiểu encoding và target type |

Để cô lập sự cố, phát một fixture JSON nhỏ có schema tối thiểu, rồi thử trước với Test Binder để kiểm tra function conversion, sau đó kiểm tra với broker thật để xác nhận wire encoding. Một test pass bằng Test Binder không đủ để loại trừ lỗi native serializer và broker schema.

## 17. Consumer đã nhận nhưng business side effect không xuất hiện

Khi broker đã dispatch message và log consumer đã xuất hiện, không nên tiếp tục chỉnh broker address hoặc producer binding. Hãy điều tra:

1. Function có lọc event do điều kiện nghiệp vụ hoặc kiểm tra duplicate không?
2. Consumer có ném exception nhưng error handler nuốt lỗi không?
3. Retry đã diễn ra bao nhiêu lần? Message có chuyển DLT/DLQ?
4. DB transaction có rollback khi Kafka offset hoặc Rabbit/Pulsar ACK đã được ghi nhận không?
5. Consumer gọi downstream API bất đồng bộ nhưng không chờ/kiểm tra kết quả không?
6. Idempotency store có đánh dấu event “đã xử lý” trước khi side effect thực sự hoàn thành không?
7. Log “processed” có xuất hiện trước transaction commit không?

Gợi ý log theo lifecycle:

~~~text
event_id=evt-101 stage=consumer.received
event_id=evt-101 stage=deserialization.complete
event_id=evt-101 stage=business.started
event_id=evt-101 stage=business.committed outcome=success
event_id=evt-101 stage=message.acknowledged
~~~

Không nhất thiết ghi một log cho mọi bước ở mức INFO với throughput cao; có thể giữ INFO cho lỗi/chuyển trạng thái quan trọng và DEBUG cho chi tiết. Quan trọng là có thể dựng lại trình tự bằng event ID và metadata broker.

### ACK/commit và side effect là hai hệ thống riêng

Kafka offset commit, RabbitMQ ACK và Pulsar ACK là dấu mốc về **tiến độ tiêu thụ**, không phải transaction commit của database. Nếu cần bảo đảm ứng dụng không tạo side effect trùng khi retry, dùng khóa idempotency theo `event-id`, ràng buộc unique trong DB hoặc một chiến lược transaction/outbox/inbox phù hợp.

Exactly-once semantics của Kafka Streams có phạm vi cụ thể đối với Kafka state và output; nó không tự tạo atomicity cho một HTTP call hoặc database bên ngoài. Luôn giải thích ranh giới bảo đảm giao nhận theo từng thành phần.

## 18. Khi producer bị chặn bởi tài nguyên hoặc network

Không phải mọi sự cố đều do destination sai. Một ứng dụng vẫn nhận request nhưng producer không hoàn tất giao nhận khi:

- DNS/advertised listener trỏ tới địa chỉ broker không truy cập được từ container hoặc Kubernetes Pod.
- Network policy, firewall, TLS certificate hoặc SASL/ACL lỗi.
- Producer buffer đầy, quá nhiều in-flight requests hoặc timeout.
- Broker đang under-replicated, hết disk, quota/flow-control hoặc không còn partition leader.
- RabbitMQ memory/disk alarm bật flow control, publisher channel đóng.
- Pulsar broker/BookKeeper gặp backpressure, ledger write chậm hoặc topic load lỗi.
- Consumer bị giới hạn CPU/thread, DB pool chờ lâu hoặc queue unacked bị dồn.

Nên đo thời gian chờ broker ACK và tỷ lệ callback thất bại. Một log cục bộ “accepted” xuất hiện trước timeout không chứng minh network ổn định. Đối chiếu client exception với broker logs/metrics trong cùng khoảng thời gian để phân biệt lỗi producer, network và broker.

### Trạng thái không chắc chắn và retry an toàn

Nếu producer timeout, đôi khi ứng dụng không biết broker đã nhận record nhưng response bị mất hay chưa. Trạng thái này là `unknown`, không phải chắc chắn “chưa gửi”. Retry mù có thể tạo duplicate; ngược lại, bỏ qua có thể làm mất event. Chọn cơ chế phù hợp:

- Kafka idempotent producer, transaction khi cần và khi phạm vi phù hợp.
- RabbitMQ publisher confirms/returns kết hợp application idempotency.
- Pulsar producer deduplication khi cluster/producer được cấu hình hỗ trợ.
- Transactional outbox để ghi intent phát event cùng database transaction.
- Consumer idempotency theo event ID để xử lý at-least-once.

Không replay toàn bộ topic hoặc DLQ chỉ vì vài message chưa có log; trước tiên phân loại `confirmed`, `failed`, `unknown` và đối chiếu event ID.

## 19. Bốn tình huống thực tế và cách tìm nguyên nhân gốc

### Ca A — `StreamBridge.send` trả true nhưng không thấy Kafka record

**Hiện tượng:** API log `accepted=true`. Kafka topic `orders.events` trống khi đọc bằng group chẩn đoán.

**Giả thuyết:** Ứng dụng gửi vào binding động khác tên; hoặc producer trỏ tới cluster sai; hoặc lỗi gửi bất đồng bộ xuất hiện sau khi API trả kết quả.

**Các bước:**

1. Log `bindingName` và `spring.cloud.stream.bindings.<name>.destination` hiệu lực.
2. Mở `GET /actuator/bindings` để xác nhận output binding thực tế.
3. Kiểm tra binder type và Kafka bootstrap servers.
4. Bật `recordMetadataChannel` và producer error channel.
5. Nếu nhận metadata với topic khác, sửa tên binding, dynamic destination hoặc topic override.
6. Nếu không có metadata và callback lỗi, xử lý nguyên nhân từ exception.
7. Chỉ sau khi đã biết kết quả gửi, xác định sự kiện cần retry với event ID không đổi.

**Kết luận có thể xảy ra:** call local thành công nhưng dữ liệu được gửi sang `orders.event` (thiếu chữ “s”) do dynamic binding được tạo từ tên sai. Sửa cấu hình để `orders-out` trỏ tới `orders.events` và thêm integration test kiểm tra topic thực.

### Ca B — Kafka topic có record nhưng Consumer không chạy

**Hiện tượng:** Kafka producer metadata có topic `orders.events`, partition 2, offset 1842; consumer group `order-worker` không ghi log.

**Các bước:**

1. Kiểm tra `/actuator/bindings/consumeOrder-in-0`; consumer binding phải chạy.
2. Dùng `kafka-consumer-groups.sh --describe` xem group có member và assignment không.
3. Kiểm tra destination consumer có đúng `orders.events`.
4. So sánh committed offset của partition 2 với offset 1842.
5. Nếu group đã commit qua offset đó, kiểm tra lịch sử consumer và DLT thay vì ép replay.
6. Nếu lag tăng, xem thread failure, deserializer, retry và function error handler.
7. Nếu group mới nhưng không thấy lịch sử, kiểm tra `startOffset` và thời điểm tạo group.

**Kết luận có thể xảy ra:** Consumer đã đọc và đẩy message vào DLT sau lỗi schema; log chỉ nằm ở error handler, không vào business function. Sửa Serde/schema hoặc hợp đồng payload và xây cảnh báo DLT tăng.

### Ca C — Rabbit publisher confirm ACK nhưng queue rỗng

**Hiện tượng:** Publisher confirm tích cực; queue `orders.events.order-worker` vẫn không có message và consumer không chạy.

**Các bước:**

1. Kiểm tra exchange, routing key và queue trong đúng vhost.
2. Xác nhận binding giữa exchange và queue.
3. Quan sát publisher returns; nếu thấy `NO_ROUTE` thì broker không route được.
4. Kiểm tra queue có được tạo sau khi producer phát message không.
5. Kiểm tra alternate exchange, TTL, auto-delete và DLQ.
6. Sau khi sửa binding, phát một event chẩn đoán mới; không giả định message đã bị discard có thể tự xuất hiện lại.

**Kết luận có thể xảy ra:** Producer publish trước khi queue/binding của consumer group được provision. Exchange chấp nhận lệnh publish nhưng không có queue đích. Giải pháp là provision topology trước, bật cơ chế xác nhận/return và thiết kế chính sách lưu/phát lại khi route thất bại.

### Ca D — Pulsar topic nhận message nhưng consumer không nhìn thấy

**Hiện tượng:** Topic stats `msgRateIn > 0`; subscription dự kiến không có record.

**Các bước:**

1. Xác nhận producer/consumer cùng tenant, namespace, topic và broker cluster.
2. Xem `subscriptions`, consumer list và subscription type trong topic stats.
3. Kiểm tra tên subscription được tạo từ group/config.
4. Nếu subscription được tạo sau khi record publish, xem initial position và retention.
5. Nếu `msgBacklog > 0`, xem consumer attach và `availablePermits`.
6. Nếu `unackedMessages` hoặc `msgRateRedeliver` tăng, tìm lỗi xử lý/ACK.
7. Nếu `Shared` hoặc `Key_Shared`, xác định consumer nào thực sự được broker giao message.

**Kết luận có thể xảy ra:** Producer và consumer cùng topic nhưng consumer thuộc subscription mới bắt đầu từ vị trí cuối; các event cũ không được phát lại. Chọn initial position đúng trong test hoặc thiết kế durable subscription đủ sớm, không reset cursor production tùy tiện.

## 20. Bảng triệu chứng → bằng chứng → nơi sửa

| Triệu chứng | Bằng chứng quan trọng nhất | Nhánh ưu tiên điều tra | Không nên làm ngay |
|---|---|---|---|
| Send true, không có producer ACK | Callback/error channel, broker address, timeout | Binder/producer/client | Reset consumer offset |
| Kafka RecordMetadata có offset, probe không đọc | Cluster, topic, partition, retention, probe group | Broker/topic/reader policy | Gửi lại hàng loạt |
| Kafka probe đọc, app không nhận | App binding state, group assignment, committed offset | Consumer binding/group | Thay `acks` của producer |
| Kafka group lag bằng 0 nhưng DB thiếu dữ liệu | Processing logs, exception handler, idempotency table | Business transaction/ACK | Kết luận event chưa gửi |
| Rabbit confirm ACK, không có queue message | Routing key, binding, returns, vhost | Exchange/queue routing | Chỉ tăng prefetch |
| Rabbit queue `ready` tăng nhưng consumers=0 | Consumer connections, queue name/group | Listener/binding startup | Gửi thêm message |
| Rabbit unacked tăng | Listener thread, ACK mode, downstream latency | Consumer processing | Xóa queue |
| Pulsar msgIn tăng, không có subscription | Namespace/topic và subscription list | Consumer subscription | Chỉnh Kafka offset |
| Pulsar backlog tăng, consumer active | Consumer permits, unacked, schema error | Subscription/consumer pressure | Xóa backlog |
| Consumer function không log nhưng DLQ tăng | Deserialize errors, retry/DLT headers | Conversion/error handler | Bỏ DLQ để “thử” |
| Test Binder pass nhưng broker trống | Test classpath và binder startup logs | Kiểm thử chưa dùng middleware thật | Quy trách nhiệm cho broker |

## 21. Runbook chẩn đoán ưu tiên bằng chứng, không gây thay đổi trạng thái

Một runbook hiệu quả nên giữ bước đầu là **read-only**:

1. Ghi incident ID, thời gian UTC, môi trường, event ID, application version.

2. Xác nhận producer và consumer nhìn vào cùng cluster/vhost/namespace.

3. Kiểm tra `function.definition`, tên binding, binder và destination hiệu lực.

4. Truy vấn trạng thái bindings và health, không START/STOP nếu chưa có phê duyệt.

5. Lấy bằng chứng producer callback: Kafka metadata, Rabbit confirm/return, Pulsar send result. Phân loại `confirmed`, `failed` hoặc `unknown`.

6. Kiểm tra broker tương ứng: Kafka topic/partition, Rabbit exchange/queue, Pulsar topic/subscription.

7. Xác nhận consumer được đăng ký: Kafka group assignment, Rabbit consumer count, Pulsar consumer list.

8. Xem lag/backlog/unacked và retry/DLQ; đối chiếu event ID.

9. Kiểm tra business side effect và trạng thái ACK/commit.

10. Chỉ chọn hành động sửa/replay có kiểm soát sau khi xác định được ranh giới lỗi. Ghi lại quyết định, bằng chứng và người phê duyệt.

Những hành động có thể thay đổi trạng thái như Kafka reset offsets, Pulsar reset cursor, Rabbit purge/delete queue, tăng partition, sửa group/subscription hoặc replay DLQ phải được xử lý theo runbook riêng, có đánh giá duplicate, ordering, retention và khả năng rollback.

### Mẫu biên bản sự cố

~~~text
Incident ID: INC-STREAM-2026-001
Event ID: diag-order-2026-11-24-001
Environment: staging
Producer app / instance: order-api / pod-1
Consumer app / instance: order-worker / pod-2
Binding producer -> destination: orders-out -> orders.events
Binding consumer -> destination: consumeOrder-in-0 -> orders.events
Broker and cluster: kafka / staging-kafka
Producer local accepted: true
Broker confirm: topic=orders.events, partition=2, offset=1842
Broker probe: record exists
Consumer group: order-worker
Consumer partition assignment: partition 2 -> pod-2
Lag / backlog: 0
Business side effect: missing
Observed first missing evidence: business commit
Next investigation: conversion/error handler, idempotency, DB transaction
Owner and action: assigned to consumer service team
~~~

Mẫu trên giúp tập trung điều tra consumer thay vì tiếp tục gửi thử nhiều lần vào cùng topic.

## 22. Kiểm thử để lỗi không quay lại

### Tầng 1 — Unit test

Kiểm tra logic của `Supplier`/`Function`/`Consumer`, tính ổn định của event ID, payload/headers và cách xử lý exception:

- Gửi thành công cục bộ có log `accepted_locally`, không log `broker_confirmed`.
- Khi `StreamBridge.send` trả `false` hoặc ném exception, code xử lý phù hợp.
- Khi business function ném exception, không nuốt lỗi ngoài chính sách retry.
- Idempotency ngăn duplicate side effect khi event được giao lại.

### Tầng 2 — Spring Integration Test Binder

Dùng `InputDestination`/`OutputDestination` để kiểm tra function binding, conversion, header và dynamic routing. Test Binder nhanh, nhưng không kiểm tra được Kafka broker ACK, Rabbit routing/confirm hay Pulsar subscription.

### Tầng 3 — Real binder + Testcontainers

Khởi động broker thật trong integration test để xác nhận đường đi từ producer tới consumer qua network. Một test có thể:

1. Gửi event có ID duy nhất từ `StreamBridge`.
2. Chờ kết quả broker publisher khi binder hỗ trợ callback.
3. Kiểm tra topic/queue/subscription có dấu hiệu nhận message.
4. Chờ consumer function ghi event ID vào test sink hoặc database test.
5. Assert side effect đúng một lần theo hợp đồng hoặc kiểm tra idempotency khi giao lại.
6. Chạy thêm case sai destination, thiếu route, lỗi schema, consumer restart và DLQ.

Ví dụ cấu hình Kafka test container qua `@DynamicPropertySource`:

~~~java
@Testcontainers
@SpringBootTest
class OrderDeliveryIntegrationTest {

    @Container
    static final KafkaContainer KAFKA =
            new KafkaContainer("apache/kafka-native:3.8.0");

    @DynamicPropertySource
    static void brokerProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.cloud.stream.kafka.binder.brokers",
                KAFKA::getBootstrapServers);
    }

    // Tạo event có ID duy nhất, gửi qua StreamBridge,
    // xác nhận broker record và chờ consumer business outcome.
}
~~~

Đây là skeleton, cần bổ sung imports JUnit/Testcontainers, cấu hình real Kafka binder, function beans, producer callback và assertions. Image/version chỉ minh họa; pin theo phiên bản broker tương thích dự án. **Không thêm `spring-cloud-stream-test-binder` vào module real-broker integration test** nếu binder giả lập có thể chiếm binding.

### Ma trận kiểm thử lỗi

| Kịch bản | Bằng chứng kiểm thử cần xác nhận |
|---|---|
| Sai destination | Callback/metadata nêu đúng topic thực tế; dashboard phát hiện binding mismatch |
| Broker không truy cập được | Async failure/timeout được ghi; không log broker success |
| Kafka topic thiếu ACL | Producer báo authorization error, không tạo trạng thái thành công giả |
| Kafka group đã commit | Consumer không replay trừ khi chính sách yêu cầu |
| Rabbit không có matching queue binding | Returned message/NO_ROUTE được quan sát khi mandatory/return cấu hình phù hợp |
| Rabbit queue không có consumer | Queue ready tăng và consumer count bằng 0 |
| Pulsar sai subscription | Topic msgIn tăng nhưng subscription dự kiến không nhận |
| Consumer deserialization lỗi | Lỗi/ retry/DLQ xuất hiện; business function không bị coi là thành công |
| Crash sau DB commit trước broker ACK | Redelivery được xử lý idempotent |
| Test Binder chỉ chạy in-JVM | Test phân biệt được kết quả giả lập với broker thật |

## 23. Thiết kế phòng ngừa ở môi trường production

Một số biện pháp giảm nguy cơ tái diễn:

- **Ghi log theo mốc xác nhận:** local accepted, producer confirmed/failed, consumer received, business committed và acknowledged.
- **Broker acknowledgment có thể quan sát:** Kafka record metadata, Rabbit confirms/returns và Pulsar publish result/metrics tương ứng.
- **Đặt destination/group rõ ràng:** không phụ thuộc default vô tình; rà soát binding names, binder names và environment overlays.
- **Theo dõi consumer tiến độ:** lag/backlog/unacked, retry, DLQ, binding health.
- **Chuẩn hóa schema và content type:** producer/consumer có contract tests và kiểm thử real binder.
- **Idempotent consumer:** dùng event ID làm khóa tránh side effect trùng khi retry/replay.
- **Transactional outbox/inbox khi thích hợp:** đóng khoảng cách giữa DB commit và việc gửi/nhận event.
- **Cảnh báo dựa trên độ trễ:** phát hiện producer accepted nhiều nhưng broker confirmed ít, hoặc broker nhận nhiều nhưng business completion không tăng.
- **Giới hạn retry và bảo toàn poison messages:** cấu hình DLQ, có quy trình kiểm tra/replay an toàn.
- **Quản lý quyền truy cập:** bảo vệ Actuator và công cụ đọc broker; không log payload nhạy cảm.

Không thể xây một cam kết “gửi đúng một lần tới mọi side effect” chỉ bằng một boolean trả về từ API gửi. Bảo đảm giao nhận là hợp đồng từ producer tới broker, từ broker tới consumer và từ consumer tới hệ thống lưu trữ, kèm cơ chế xử lý trạng thái không chắc chắn.

## 24. Checklist trước khi đóng incident

- [ ] Đã đối chiếu event ID, thời gian UTC và đúng environment.
- [ ] Producer, consumer dùng đúng broker cluster/vhost/namespace.
- [ ] Function definition và binding names khớp ứng dụng đang chạy.
- [ ] Đã ghi rõ trạng thái `StreamBridge.send` không phải broker ACK.
- [ ] Đã kiểm tra error channel và callback/confirm của producer.
- [ ] Nếu Kafka, đã có topic/partition/offset từ RecordMetadata hoặc probe đáng tin cậy.
- [ ] Nếu Kafka, đã kiểm tra group assignment, committed offset và lag từng partition.
- [ ] Nếu RabbitMQ, đã kiểm tra exchange, queue, routing, confirm/return và unacked.
- [ ] Nếu Pulsar, đã kiểm tra topic, publishers, subscription, backlog, redelivery.
- [ ] Đã kiểm tra conversion/schema/Serde trước khi kết luận consumer không nhận.
- [ ] Đã kiểm tra retry, DLT/DLQ, transaction và business side effect.
- [ ] Chưa có reset offset/cursor, purge queue hoặc replay mù trong lúc chẩn đoán.
- [ ] Root cause được gắn đúng tầng, có bằng chứng xác nhận.
- [ ] Đã kiểm thử lại với event chẩn đoán mới sau sửa lỗi.
- [ ] Đã đánh giá duplicate, ordering, idempotency và dữ liệu cần bù.
- [ ] Đã có alert hoặc regression test giúp phát hiện lỗi tái diễn.

## Tổng kết

Trong Spring Cloud Stream, lời gọi gửi được chấp nhận tại ứng dụng mới chỉ là **một mắt xích** trong chuỗi giao nhận. Muốn chẩn đoán “gửi thành công cục bộ nhưng broker hoặc consumer chưa nhận dữ liệu”, hãy tìm **bằng chứng đầu tiên còn thiếu**: xác nhận producer, record/queue/topic ở broker, registration và assignment của consumer, dữ liệu đã deserialize, business side effect hay commit/ACK.

Kafka cần đối chiếu `RecordMetadata`, topic/partition/offset, group và committed offset. RabbitMQ cần đối chiếu publisher confirm **và** returned message, exchange/queue binding và consumer ACK. Pulsar cần đối chiếu message publish, topic stats, subscription cursor, backlog và redelivery. Khi đặt event ID ổn định, quan sát trạng thái bất đồng bộ và dùng test với broker thật, có thể sửa đúng tầng mà không vô tình làm mất hoặc nhân đôi sự kiện.

## Tài liệu tham khảo

- [Spring Cloud Stream — Producing and Consuming Messages / StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html)
- [Spring Cloud Stream — Binding Properties and Producer Error Channel](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — Kafka Binder and Resetting Offsets](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_overview.html)
- [Spring Cloud Stream — RabbitMQ Binder Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html)
- [Spring Cloud Stream — RabbitMQ Publisher Confirms and Error Channels](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring Cloud Stream — Spring Integration Test Binder](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Apache Kafka — Consumer Configuration](https://kafka.apache.org/documentation/#consumerconfigs)
- [RabbitMQ — Publisher Confirms](https://www.rabbitmq.com/docs/confirms)
- [RabbitMQ — Exchanges and Routing](https://www.rabbitmq.com/tutorials/amqp-concepts)
- [Apache Pulsar — Topic and Subscription Statistics](https://pulsar.apache.org/docs/4.2.x/administration-stats/)
- [Spring Pulsar — Message Consumption](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html)
- [Testcontainers — Kafka Module](https://java.testcontainers.org/modules/kafka/)
