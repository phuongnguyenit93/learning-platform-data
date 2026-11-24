# Consumer không nhận do sai destination, group hoặc routing key

Ứng dụng Spring Cloud Stream có thể khởi động, kết nối broker và báo health UP, nhưng hàm `Consumer<T>` vẫn không được gọi. Một nguyên nhân phổ biến là producer đang gửi tới **destination khác**, consumer thuộc **group/subscription không đúng**, hoặc RabbitMQ không route message từ exchange vào queue vì **routing key không khớp binding key**. Cùng một triệu chứng có thể có nhiều nguyên nhân hoàn toàn khác nhau.

Bài này cung cấp quy trình chẩn đoán theo bằng chứng cho Kafka, RabbitMQ và Pulsar. Mục tiêu là xác định message đi tới tầng nào trước khi sửa cấu hình, tránh các thao tác nguy hiểm như reset offset, đổi group production hoặc xóa queue.

## 1. Phân loại chính xác triệu chứng

| Điều quan sát được | Khả năng cao | Cần kiểm tra |
|---|---|---|
| Không có consumer listener | Function không được kích hoạt, sai tên binding | function.definition, Actuator bindings |
| Consumer STARTED nhưng không có message | Destination, broker, group/offset hoặc routing | Broker topology và trạng thái group |
| Broker đã delivery nhưng handler không thành công | Converter, Serde, schema, retry, exception | Log lỗi, DLT/DLQ, retry metrics |
| Pod A không nhận, Pod B nhận | Competing consumer/partition assignment | Members, partitions, subscription type |
| Producer báo thành công, Rabbit queue rỗng | Exchange sai hoặc routing/binding key không khớp | Exchange, queue, bindings, mandatory returns |

Một message có thể **đã được nhận và xử lý** bởi instance khác cùng group. Nó cũng có thể **đã bị xử lý lỗi và chuyển DLQ** trước khi bạn tìm được log thành công. Không đồng nhất “không thấy log của handler ở Pod này” với “broker chưa giao”.

## 2. Khoanh vùng đường đi của một event

~~~mermaid
flowchart TD
    A[Producer publish] --> B[Output binding và binder]
    B --> C[Broker / cluster / vhost / namespace]
    C --> D{Middleware}
    D --> E[Kafka topic + partition]
    D --> F[Rabbit exchange + routing key]
    D --> G[Pulsar topic + subscription]
    E --> H[Kafka group + offset/assignment]
    F --> I[Queue + binding key + consumers]
    G --> J[Subscription + cursor/type]
    H --> K[Input binding]
    I --> K
    J --> K
    K --> L[Message conversion/Serde]
    L --> M[Consumer function]
    L --> N[Error handling / DLQ]
~~~

Để tái hiện, chọn **một eventId duy nhất**, ghi lại thời điểm publish, destination nguồn và kết quả producer send. Sau đó đối chiếu đúng broker và topology. Đừng thay ba cấu hình cùng lúc rồi suy đoán nguyên nhân.

## 3. Phân biệt function, binding, destination và group

Spring Cloud Stream dùng quy ước:

- **Consumer** tên `handleOrder` → input binding `handleOrder-in-0`.
- **Supplier** tên `produceOrder` → output `produceOrder-out-0`.
- **Function** tên `enrichOrder` → input `enrichOrder-in-0`, output `enrichOrder-out-0`.

Ví dụ:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Consumer<OrderEvent> handleOrder(OrderService service) {
        return event -> service.apply(event);
    }
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
          content-type: application/json
~~~

| Giá trị | Ý nghĩa | Thường bị nhầm với |
|---|---|---|
| handleOrder | Tên bean Function/Consumer | Tên topic |
| handleOrder-in-0 | Tên **binding** đầu vào | Destination vật lý |
| orders.created | **Destination** cấu hình | Rabbit queue name |
| fulfillment-service | **Consumer group** | Function name |

Nếu bỏ **destination**, giá trị mặc định là tên binding. Khi đó consumer có thể nghe **handleOrder-in-0**, còn producer gửi **orders.created**. Hai tên đó không tự được nối với nhau.

## 4. Lỗi do function.definition hoặc alias binding

Ví dụ sai:

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        receiveOrder-in-0:
          destination: orders.created
          group: fulfillment-service
~~~

Bean thật mang tên **handleOrder**, nên input binding mặc định là **handleOrder-in-0**. Cấu hình trên dùng sai key và có thể khiến destination/group mong muốn không được áp dụng.

Nếu dùng alias:

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      function:
        bindings:
          handleOrder-in-0: orderInput
      bindings:
        orderInput:
          destination: orders.created
          group: fulfillment-service
~~~

Sau khi ánh xạ alias, các extended binding properties dành cho Kafka/Rabbit/Pulsar cũng phải dùng tên binding thực tế theo hợp đồng ánh xạ. Khi debug, lập bảng: **bean → implicit binding → alias (nếu có) → destination**.

Các lỗi cần kiểm tra trước khi chạm broker:

- Bean không được tạo vì profile/conditional annotation.
- Tên trong function.definition bị viết sai.
- Function composition tạo tên binding khác dự kiến.
- Bean có nhiều input/output nhưng dùng sai chỉ số `-in-0`, `-in-1`.
- Có nhiều binder trong classpath nhưng không chọn binder đúng.
- Spring profile hoặc biến môi trường ghi đè tên destination.

## 5. Quy trình chẩn đoán nhanh và an toàn

1. Chốt event ID, timestamp và broker producer thực sự sử dụng.
2. Đọc log publish: success/failure, topic/exchange và routing key.
3. Đọc cấu hình effective đã che secret: function definition, binding name, binder, destination, group.
4. Kiểm tra binding có được tạo và STARTED hay không.
5. Đối chiếu topology trên đúng broker: Kafka topic, Rabbit exchange/queue/binding hoặc Pulsar topic/subscription.
6. Kiểm tra offset, backlog, assignment, consumer count.
7. Publish một **event mới** có ID riêng, không phát lại toàn bộ topic.
8. Nếu broker đã giao: mới đi sâu vào deserialize, validation, retry, DLT/DLQ.
9. Sửa duy nhất một nhóm cấu hình, xác minh bằng event test và monitoring.

Không bắt đầu bằng `resetOffsets: true`, purge Rabbit queue hoặc xóa Pulsar subscription. Những thao tác đó ảnh hưởng tiến trình xử lý và có thể tạo duplicate hoặc mất dữ liệu.

## 6. Kiểm tra trạng thái binding qua Actuator

Spring Cloud Stream cung cấp bindings actuator endpoint. Khi ứng dụng có Actuator và endpoint được bảo vệ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,bindings"
~~~

~~~bash
curl -s http://localhost:8080/actuator/bindings
curl -s http://localhost:8080/actuator/bindings/handleOrder-in-0
~~~

Nếu không thấy `handleOrder-in-0`, cần điều tra function definition, bean scan, alias hoặc binder initialization. Binding STARTED có nghĩa lifecycle endpoint đã start, **không chứng minh message đã được giao**.

Endpoint có khả năng start/stop binding. Chỉ đọc trạng thái trong giai đoạn điều tra; không gửi POST STARTED/STOPPED khi chưa có quyết định vận hành. Việc stop/start có thể tạo Kafka rebalance hoặc message redelivery.

Nếu endpoint báo không tồn tại, không có nghĩa binder chưa chạy: có thể thiếu Actuator, chưa expose bindings hoặc bạn đang dùng sai management port/path.

## 7. Sai binder hoặc sai broker dù destination giống hệt

Hai cluster Kafka có thể cùng chứa topic `orders.created`. Hai RabbitMQ virtual host có thể cùng chứa exchange `orders.events`. Hai Pulsar namespace có thể cùng có topic tên cuối `orders.created`.

Vì vậy, danh tính tài nguyên thực tế gồm:

| Broker | Phải đối chiếu |
|---|---|
| Kafka | Bootstrap servers, cluster, topic, group |
| RabbitMQ | Host/port, virtual host, exchange, queue, routing |
| Pulsar | Service URL, tenant, namespace, topic, subscription |
| Multi-binder | Binder alias, environment riêng và binding selection |

Ví dụ consumer Kafka trỏ nhầm cluster:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
          binder: kafkaPayments
~~~

Producer đang ở `kafkaOrders` trong khi consumer dùng `kafkaPayments`. Cả hai application có thể báo connected và healthy nhưng không trao đổi cùng event.

Không log JAAS string, password, token hay private key khi kiểm tra effective configuration.

## 8. Kafka: destination là topic, không phải routing key

Kafka Binder ánh xạ destination vào topic; Kafka **không có AMQP routing key**. Kafka producer dùng topic để định tuyến, record key thường ảnh hưởng partition.

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
          binder: kafka
      kafka:
        binder:
          brokers: localhost:9092
~~~

Nếu producer gửi `orders.events` còn consumer nghe `orders.created`, sửa routing-key không có ý nghĩa. Hãy so sánh topic vật lý trên producer send result và input destination.

Lệnh kiểm tra topic (local hoặc môi trường được cấp quyền):

~~~bash
kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list

kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.created
~~~

Cluster có TLS/SASL cần client properties qua `--command-config`. Nếu topic không tồn tại hoặc ACL không cho Describe/Read, giải quyết provisioning/authorization, không đổi group một cách ngẫu nhiên.

## 9. Kafka: group đã ở cuối log

Kafka lưu committed offset riêng cho từng partition thuộc group. Ví dụ:

~~~text
Topic orders.created, partition 0
Log end offset:         251
Group committed offset: 251
Lag:                    0
~~~

Consumer đã theo kịp topic. Khi restart nó không đọc lại record ở offset thấp hơn 251 nếu committed offset vẫn còn hiệu lực.

- Group có tên, **chưa có committed offset**: Kafka Binder thường mặc định khởi đầu từ earliest.
- Anonymous group, **chưa có committed offset**: mặc định thường từ latest.
- Group đã commit: ưu tiên committed offset trước startOffset.
- Offset hết hạn hoặc group mới: startOffset/auto.offset.reset quyết định điểm bắt đầu.

Kiểm tra:

~~~bash
kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --group fulfillment-service
~~~

Quan sát TOPIC, PARTITION, CURRENT-OFFSET, LOG-END-OFFSET, LAG, CONSUMER-ID và assignment. Khi LAG=0, hãy phát **event mới**, không reset group chỉ để nhìn thấy record cũ.

## 10. Kafka: các instance dùng chung group sẽ chia partition

~~~text
Topic orders.created (3 partitions)

Group fulfillment-service
  partition 0 -> Pod A
  partition 1 -> Pod B
  partition 2 -> Pod C
~~~

Mỗi record thường được xử lý bởi một thành viên đang giữ partition đó. Pod A không nhận record của partition 2 là đúng.

Nếu fulfillment-service và analytics-service vô tình cùng dùng group `order-workers`, chúng có thể chia partition thay vì mỗi dịch vụ nhận toàn bộ record. Hai dịch vụ độc lập cần hai group khác nhau, trong khi các replica của **cùng dịch vụ** dùng chung group.

Không đổi group production mà không tính tới offset: group mới chưa có offset có thể đọc lại từ earliest, gây duplicate payment, email hoặc shipment.

## 11. Kafka: partition assignment và concurrency

Nếu topic chỉ có 2 partition nhưng group có 5 consumer instances, một số consumer không được gán partition nên không nhận message.

Kiểm tra:

- Partition count của topic.
- Số active group members và partition assignment.
- Giá trị `spring.cloud.stream.bindings.<name>.consumer.concurrency`.
- Key của record và partitioner.
- Rebalance loop khi một instance lỗi hoặc restart.

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
          consumer:
            concurrency: 3
~~~

Concurrency không tự tạo thêm Kafka partition. Nếu một key luôn route về partition 0, chỉ member giữ partition 0 nhận các record đó. Hãy dùng nhiều key hoặc kiểm tra assignment khi test load.

## 12. Kafka: startOffset không tự ghi đè committed offset

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        bindings:
          handleOrder-in-0:
            consumer:
              startOffset: earliest
              resetOffsets: false
~~~

`startOffset` chủ yếu áp dụng khi group chưa có offset. Bật `resetOffsets: true` yêu cầu seek theo startOffset ở thời điểm thích hợp, có thể dẫn tới replay.

**Không bật resetOffsets trên consumer production chỉ vì không thấy log.** Cần xác định group hiện tại, offset, số record có thể replay, idempotency và tác động downstream trước khi thao tác.

Một bài kiểm tra an toàn hơn là publish event mới với eventId duy nhất và quan sát group offset tăng.

## 13. Kafka: phân biệt Kafka Binder và Kafka Streams Binder

Ứng dụng nhận `KStream`, `KTable` và `GlobalKTable` thuộc mô hình Kafka Streams. Nó dùng **application.id**, task assignment, internal topics và state stores.

Khi Kafka Streams function không nhận:

- Xác minh đúng Kafka Streams binder, không phải Kafka message-channel binder.
- Kiểm tra source destination.
- Kiểm tra application.id được cấu hình cho processor.
- Quan sát RUNNING/REBALANCING và task assignment.
- Kiểm tra state restore/changelog lag và deserialization handler.
- Không suy ra consumer membership từ `group` của Kafka binder thông thường.

Đổi application.id để “thử” có thể tạo một ứng dụng logic mới, đọc lại state và offset theo lịch sử khác. Cần có kế hoạch migration chứ không nên làm trong lúc troubleshoot.

## 14. RabbitMQ: destination là exchange, group thường xác định queue

Rabbit Binder mặc định tạo topic exchange từ destination. Với group có tên, queue thường mang tên `destination.group`.

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.events
          group: fulfillment
          binder: rabbit
~~~

Topology mặc định thường là:

~~~text
Exchange: orders.events
Exchange type: topic
Queue: orders.events.fulfillment
Binding key: #
~~~

Producer gửi vào **exchange**, consumer đọc từ **queue**. Nếu consumer dự định đọc queue `fulfillment_queue` do hạ tầng tạo sẵn nhưng binder lại khai báo queue `orders.events.fulfillment`, việc cả hai queue đều tồn tại không giúp consumer nhận từ queue đúng.

Rabbit consumer không có group thường dùng anonymous auto-delete queue; queue có thể biến mất khi ứng dụng dừng. Không dùng anonymous consumer nếu cần giữ backlog qua restart.

## 15. RabbitMQ: routing key và binding key

~~~mermaid
flowchart LR
    P[Producer] -->|routing key order.created| E((orders.events topic exchange))
    E -->|binding order.*| Q1[Fulfillment queue]
    E -->|binding payment.*| Q2[Accounting queue]
    E -->|binding #| Q3[Audit queue]
~~~

Với topic exchange:

- `*` khớp đúng **một từ** giữa các dấu chấm.
- `#` khớp không hoặc nhiều từ.
- `order.*` khớp `order.created` nhưng không khớp `order.eu.created`.
- `order.#` khớp các nhánh sâu hơn.
- Direct exchange so khớp key **chính xác**.
- Fanout exchange không dùng routing key để lọc.
- Headers exchange định tuyến theo binding arguments/headers.

**Mặc định Rabbit Binder dùng binding key `#`** với non-partitioned topic exchange. Vì thế nếu chưa tùy chỉnh key, nên kiểm tra sai exchange, prefix hoặc queue trước khi đổ lỗi routing key.

## 16. Cấu hình RabbitMQ routing key ở cả producer và consumer

Consumer nhận `order.*`:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.events
          group: fulfillment
          binder: rabbit
      rabbit:
        bindings:
          handleOrder-in-0:
            consumer:
              exchangeType: topic
              bindingRoutingKey: "order.*"
~~~

Producer phát `order.created` (giả định output binding tên `publishOrder-out-0`):

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.events
          binder: rabbit
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              routingKey: "order.created"
~~~

Nếu consumer dùng `bindingRoutingKey: "payment.*"`, message `order.created` không route vào queue đó dù producer gửi thành công.

Cần phân biệt:

| Producer | Consumer | Chức năng |
|---|---|---|
| routingKey | bindingRoutingKey | Key publish và pattern của queue |
| routingKeyExpression | bindingRoutingKey | SpEL để tính routing key và pattern của queue |
| destination | destination | Exchange vật lý phải tương thích |
| requiredGroups | group | Có thể provision queue/group trước consumer |

Đối với expression, xem key **đã được tính và publish**, không chỉ tên header kỳ vọng. Nếu key không khớp do header sai tên, sửa producer expression/header contract.

## 17. RabbitMQ: existing queue và queueNameGroupOnly

Giả sử tài nguyên đã có:

~~~text
Exchange: orders.events
Queue: fulfillment_queue
Binding: order.*
~~~

Mặc định Rabbit Binder ghép queue name thành `orders.events.fulfillment_queue` khi group là `fulfillment_queue`. Để dùng queue có sẵn đã được bind:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.events
          group: fulfillment_queue
          binder: rabbit
      rabbit:
        bindings:
          handleOrder-in-0:
            consumer:
              queueNameGroupOnly: true
              bindQueue: false
              declareExchange: false
~~~

- queueNameGroupOnly: lấy group làm tên queue.
- bindQueue=false: không tự declare/bind queue.
- declareExchange=false: không tự declare exchange.
- Phải đảm bảo exchange, queue, binding key và quyền truy cập **đã được provision** trước.

Nếu chưa tạo queue nhưng lại tắt provisioning, listener có thể log missing queue hoặc lặp retry. Thay routing key không sửa được queue chưa tồn tại.

## 18. RabbitMQ: gửi thành công nhưng không route đến queue

Publisher confirm thể hiện broker chấp nhận publish theo semantics của RabbitMQ, không đồng nghĩa có consumer đã nhận hoặc một queue đã được định tuyến.

Kịch bản:

~~~text
Exchange: orders.events (topic)
Queue: orders.events.fulfillment
Binding key: payment.*
Published routing key: order.created
Result: không route tới queue fulfillment
~~~

Hãy kiểm tra:

1. Exchange tồn tại ở **đúng virtual host**.
2. Exchange type là topic/direct/fanout như kỳ vọng.
3. Queue và binding đang tồn tại.
4. Routing key thực tế trùng pattern.
5. Return/unroutable behavior khi không có queue matching.
6. Publish, deliver, ack và reject rates.
7. Có consumer khác đang lấy message khỏi queue hay không.

`messages_ready=0` không tự chứng minh không có delivery: consumer có thể nhận và ack rất nhanh.

## 19. RabbitMQ: lệnh kiểm tra topology

Trên broker test hoặc môi trường được cấp quyền:

~~~bash
rabbitmqctl list_vhosts

rabbitmqctl -p /orders list_exchanges name type durable

rabbitmqctl -p /orders list_queues \
  name messages_ready messages_unacknowledged consumers

rabbitmqctl -p /orders list_bindings \
  source_name destination_name destination_kind routing_key
~~~

Trong RabbitMQ Management UI, chọn đúng **vhost**, sau đó xem exchange, queue binding, consumer count và message rates.

Đừng purge queue, delete queue hoặc xóa binding chỉ để thử. Dùng một message test có eventId riêng và routing key biết trước, sau đó quan sát exchange/queue counters.

## 20. RabbitMQ: prefix, exchangeType và partition

Rabbit Binder có cấu hình prefix để thêm vào tên exchange/queue. Nếu producer dùng prefix `prod.` nhưng consumer không dùng, cả hai có thể viết destination logic `orders.events` nhưng kết nối tới **hai exchange khác nhau**.

Khi dùng `exchangeType: direct`, wildcard như `order.*` không có cùng semantics của topic exchange. Nếu exchange đã tồn tại với type khác, declare lại có thể gây precondition failure.

Khi partitioned binding được bật, routing/binding key có thể được thêm hậu tố partition hoặc instance index như:

~~~text
orders.events-0
orders.events-1
~~~

Đối chiếu:

- `partition-count` producer và partition key/selector.
- `partitioned`, `instance-count`, `instance-index` consumer.
- Routing key sau khi binder tính toán.
- Binding key thực tế trên Rabbit exchange.
- Queue tương ứng và consumer instance được cấu hình.

Không tăng concurrency để chữa routing mismatch do partition suffix sai.

## 21. Pulsar: destination là topic, không phải Rabbit routing key

Pulsar dùng topic và subscription. Một tên topic đầy đủ thường có dạng:

~~~text
persistent://<tenant>/<namespace>/<topic>
~~~

Ví dụ:

~~~text
persistent://sales/events/orders.created
~~~

Nếu producer gửi tới namespace `sales/events` nhưng consumer đang subscribe `public/default`, tên cuối giống nhau không có nghĩa chúng là cùng một topic.

Ví dụ Spring Cloud Stream Pulsar consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: persistent://sales/events/orders.created
          group: fulfillment
          binder: pulsar
  pulsar:
    client:
      service-url: pulsar://localhost:6650
    administration:
      service-url: http://localhost:8080
~~~

Ở Spring Cloud Stream, `group` mô tả nhóm consumer logic. Pulsar Binder dùng subscription mechanism của Pulsar và các thuộc tính consumer được Spring Pulsar hỗ trợ. **Xác minh subscription name thực tế** của ứng dụng và mọi giá trị override thay vì mặc định nó luôn giống Kafka group ID.

Để giảm nhầm lẫn, dùng fully qualified topic khi triển khai trên nhiều tenant/namespace. Kiểm tra quyền của principal trong cả tenant, namespace và topic.

## 22. Pulsar: subscription type có thể khiến instance “im lặng”

| Subscription type | Phân phối |
|---|---|
| Exclusive | Một consumer hoạt động trên subscription; consumer khác có thể bị từ chối |
| Failover | Một consumer active, các consumer khác standby cho phần dữ liệu tương ứng |
| Shared | Consumer chia message, không giữ thứ tự toàn cục như một consumer duy nhất |
| Key_Shared | Phân phối theo key, hỗ trợ yêu cầu thứ tự theo key trong điều kiện phù hợp |

Nếu hai Pod dùng cùng subscription Failover, Pod standby có thể không nhận message trong khi Pod active còn khỏe. Đây là chính sách hợp lệ, không phải lỗi routing.

Kiểm tra subscription name, type, consumer count, active/standby state, backlog và unacknowledged messages. Với Key_Shared, ghi lại message key: việc chỉ một consumer nhận những record của cùng key có thể là hành vi đúng.

Đừng đổi subscription type hoặc xóa subscription ở production khi chưa đánh giá ordering, backlog, replay và acknowledgment semantics.

## 23. Pulsar: quan sát topic và subscription

Pulsar Admin CLI/API hỗ trợ liệt kê topic, subscription và stats. Ví dụ local:

~~~bash
pulsar-admin topics list sales/events

pulsar-admin topics stats \
  persistent://sales/events/orders.created

pulsar-admin topics subscriptions \
  persistent://sales/events/orders.created
~~~

Các phiên bản Pulsar có thể khác nhau về tên field và quyền truy cập Admin API. Hãy kiểm tra:

- Topic đúng tenant và namespace.
- Subscription đúng tên đang tồn tại.
- Consumer có kết nối, active hay standby.
- `msgBacklog` và unacknowledged count.
- Publish rate so với dispatch/ack rate.
- Subscription cursor và initial position.
- Redelivery, retry topic hoặc dead-letter topic.
- Authentication/TLS/ACL có ngăn consumer subscribe không.

Nếu topic có record mới nhưng subscription không có consumer, quay lại kiểm tra function activation, binding và URL. Nếu subscription có backlog tăng mà consumer connected, kiểm tra handler error, schema và acknowledgement.

## 24. Multi-binder: upstream gửi sang broker khác

Ứng dụng bridge có thể đọc Kafka rồi phát RabbitMQ:

~~~yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: orders.created
          group: enrichment
          binder: kafka
        enrichOrder-out-0:
          destination: orders.fulfillment
          binder: rabbit
~~~

Nếu output vô tình trỏ tới Kafka, downstream Rabbit consumer không có message dù input và function hoàn toàn đúng.

Đối chiếu từng binding độc lập:

1. Input đang dùng binder nào?
2. Output đang dùng binder nào?
3. Tên destination ở broker đích là gì?
4. Connection settings của named binder có trỏ đúng cluster/vhost không?
5. Producer có xác nhận publish và routing không?
6. Downstream consumer có đúng exchange/topic và group không?

Không dùng `spring.cloud.stream.default-binder` để giải thích tất cả binding nếu chúng đã khai báo binder tường minh.

## 25. Message đã được broker giao nhưng conversion thất bại

Ví dụ message:

~~~json
{
  "eventId": "evt-test-004",
  "orderId": "order-104",
  "total": 250000
}
~~~

Consumer function:

~~~java
public record OrderEvent(
    String eventId,
    String orderId,
    long total
) {}

@Bean
Consumer<OrderEvent> handleOrder(OrderService service) {
    return event -> service.apply(event);
}
~~~

Có thể message đã tới binding nhưng converter không tạo được `OrderEvent` do:

- Header content type không tương thích.
- Payload không phải JSON hợp lệ.
- Native decoding bật nhưng consumer Serde sai.
- Schema Avro/Protobuf khác producer.
- Kiểu field thay đổi hoặc không thể chuyển.
- Missing header, null payload hoặc tombstone không được xử lý.

Log nên chứa exception class và metadata như topic/partition/offset hoặc queue, nhưng không tiết lộ payload nhạy cảm. Với Kafka Streams, deserialization handler chạy trước topology; với Pulsar, schema layer cũng có thể từ chối record trước function.

Đừng sửa destination để chữa lỗi converter. Cần xác minh đã delivery và sửa đúng serialization/schema contract.

## 26. Retry và DLQ khiến consumer trông như không nhận

Một handler ném exception có thể được binder retry, rồi record chuyển DLT/DLQ hoặc bị xử lý theo error policy.

| Broker | Bằng chứng cần tìm |
|---|---|
| Kafka | Lỗi handler/deserialization, committed offset, DLT như error.topic.group |
| RabbitMQ | Deliver/reject/ack rate, queue ready/unacked và DLQ depth |
| Pulsar | Retry/redelivery, dead-letter topic, subscription backlog/cursor |

Nếu broker đã giao và DLQ có event ID đó, **vấn đề không phải routing đầu vào**. Cần điều tra exception gốc, retry policy và việc recover/replay.

Đặc biệt, một Rabbit message **không được route vào queue** khác với một message **được consumer nhận rồi dead-letter**. Hai lỗi cần cách kiểm tra khác nhau.

## 27. autoStartup, STOPPED, PAUSED và health

Common consumer property `autoStartup` mặc định true:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
          consumer:
            autoStartup: true
~~~

Nếu cấu hình false hoặc binding đã bị stop bằng `BindingsLifecycleController`/Actuator, ứng dụng vẫn có thể chạy nhưng consumer không nhận.

Kiểm tra state bằng `/actuator/bindings`, lịch sử lệnh vận hành và application lifecycle. STARTED không chứng minh throughput; STOPPED cho thấy cần tìm nguyên nhân ai đã dừng. PAUSED/RESUMED không hỗ trợ đồng đều trên mọi binder.

Lưu ý Kubernetes Pod NotReady không tự pause broker consumer. Readiness kiểm soát traffic qua Kubernetes Service, không nhất thiết can thiệp Kafka poll hoặc Rabbit/Pulsar subscriptions.

## 28. Ma trận chỉ số xác định đúng tầng lỗi

| Metric/tín hiệu | Gợi ý |
|---|---|
| Producer send confirmation | Broker nhận publish hay có lỗi |
| Kafka topic end offset | Topic có record mới hay không |
| Kafka group LAG=0 | Group đã theo kịp hoặc không có record mới |
| Kafka group LAG tăng | Consumer đang chậm, dừng hoặc lỗi |
| Kafka assigned partitions=0 | Instance idle, chưa được assign hoặc rebalance |
| Rabbit exchange publish tăng, queue deliver=0 | Routing/binding hoặc không có consumer |
| Rabbit queue ready tăng | Đã route tới queue, chưa được giao |
| Rabbit unacked tăng | Consumer đã nhận nhưng chưa ack |
| Rabbit DLQ depth tăng | Lỗi trong quá trình xử lý/queue policy |
| Pulsar msgBacklog tăng | Subscription đang tồn message chưa xử lý |
| Pulsar active consumers=0 | Không có consumer thực sự attach |
| Function invocation count tăng | Code được gọi; kiểm tra side effect |
| Binder health UP | Kết nối/lifecycle có thể ổn; chưa chứng minh message flow |

Không dựa một metric đơn lẻ để xác định lỗi. Ví dụ Rabbit queue ready=0 có thể do consumer xử lý rất nhanh hoặc do không có message nào được route. Phải kết hợp publish, deliver, ack, binding topology và event ID.

## 29. Tình huống 1: Kafka dùng sai tên input binding

**Code:**

~~~java
@Bean
Consumer<OrderEvent> handleOrder(OrderService service) {
    return event -> service.apply(event);
}
~~~

**Cấu hình sai:**

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        receiveOrder-in-0:
          destination: orders.created
          group: fulfillment-service
~~~

Function tạo `handleOrder-in-0`, không phải `receiveOrder-in-0`. Vì thế cấu hình có thể bị áp dụng cho binding không liên quan.

**Cấu hình sửa:**

~~~yaml
spring:
  cloud:
    function:
      definition: handleOrder
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
~~~

Sau sửa, kiểm tra /actuator/bindings và group trên broker. Không reset offset chỉ vì đã sửa tên key config.

## 30. Tình huống 2: hai dịch vụ Kafka vô tình dùng chung group

~~~text
fulfillment-service -> group orders-workers
analytics-service   -> group orders-workers
~~~

Cả hai cùng đọc `orders.created`, nhưng mỗi service phải xử lý toàn bộ sự kiện. Vì cùng group, Kafka chia partition cho các member thay vì broadcast một bản sao cho mỗi service.

Sửa bằng cách cấp group riêng cho từng service:

~~~yaml
# application.yml của fulfillment
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: orders.created
          group: fulfillment-service
~~~

Analytics có thể dùng group `order-analytics`. Cần kiểm tra committed offsets của group mới trước deploy; nó có thể bắt đầu đọc từ earliest và tái xử lý lịch sử.

## 31. Tình huống 3: Rabbit exchange có nhưng binding key sai

~~~text
Exchange: orders.events (topic)
Queue: orders.events.fulfillment
Binding key: payment.*
Published routing key: order.created
~~~

Consumer không nhận vì `payment.*` không khớp `order.created`. Nếu nghiệp vụ phải nhận order:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          handleOrder-in-0:
            consumer:
              bindingRoutingKey: "order.*"
~~~

**Sau deploy, phải xác minh broker thật có binding mới.** Nếu `bindQueue=false` hoặc queue/exchange do IaC quản lý, sửa property không thay được topology đã provision bên ngoài. Đưa thay đổi vào IaC/management workflow thích hợp.

Không mở rộng key thành `#` tùy tiện vì có thể khiến queue nhận nhiều event không mong muốn.

## 32. Tình huống 4: Rabbit existing queue được đặt tên khác

Topology hiện có:

~~~text
Exchange: orders.events
Queue: fulfillment_queue
Binding key: order.*
~~~

Ứng dụng chỉ đặt `group: fulfillment_queue` sẽ mặc định nhắm `orders.events.fulfillment_queue`, là queue khác.

Cấu hình khi IaC đã tạo đủ resource:

~~~yaml
spring:
  cloud:
    stream:
      rabbit:
        bindings:
          handleOrder-in-0:
            consumer:
              queueNameGroupOnly: true
              bindQueue: false
              declareExchange: false
~~~

Kết hợp với `destination: orders.events`, `group: fulfillment_queue`. Xác minh queue đang bind đúng exchange và user có quyền consume.

## 33. Tình huống 5: Pulsar cùng tên topic cuối nhưng khác namespace

~~~text
Producer: persistent://sales/events/orders.created
Consumer: persistent://public/default/orders.created
~~~

Đây là hai topic khác nhau. Sửa destination consumer thành topic fully qualified mà producer sử dụng:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        handleOrder-in-0:
          destination: persistent://sales/events/orders.created
          group: fulfillment
~~~

Sau sửa, kiểm tra subscription thực tế và quyền truy cập `sales/events`. Không xóa subscription cũ nếu còn backlog cần giữ hoặc migration.

## 34. Tình huống 6: broker đã delivery nhưng handler thất bại

Rabbit deliver rate tăng hoặc Kafka offset/group state thay đổi, nhưng không có log “order processed”. Hãy kiểm tra:

1. Instance nào đang sở hữu partition hoặc queue consumer?
2. Function có được invoke không?
3. Exception nào đầu tiên trong retry chain?
4. Event có vào DLQ/DLT không?
5. Có transaction rollback hoặc idempotency skip không?
6. Các log có filter hoặc đang nằm trên Pod khác không?

Khi broker đã delivery, hướng điều tra phải chuyển sang handler/conversion và error policy. Thay routing key không giải quyết được business exception.

## 35. Kiểm thử bằng Testcontainers sau khi sửa

Unit test function chỉ chứng minh business logic, không chứng minh broker topology. Integration test nên:

1. Khởi chạy broker thật bằng Testcontainers.
2. Khởi tạo Spring context với binder thật và endpoint động.
3. Tạo topic/exchange/queue/subscription theo hợp đồng.
4. Publish eventId duy nhất.
5. Assert handler nhận đúng event với timeout hữu hạn.
6. Kafka: test group riêng, committed offset và assignment.
7. Rabbit: test một routing key matching và một non-matching.
8. Pulsar: test fully qualified topic và subscription name/type.
9. Test sai content type/Serde và kiểm tra error path.
10. Restart consumer, xác minh backlog và redelivery/idempotency.
11. Tránh Spring Integration Test Binder trong cùng test runtime nếu mục tiêu là kiểm tra broker thật.

Ví dụ pseudo-Java (test helper do dự án tự tạo):

~~~java
OrderEvent event =
    new OrderEvent("evt-it-101", "order-it-101", 1000L);

brokerTestClient.publish("orders.created", event);

await()
    .atMost(Duration.ofSeconds(15))
    .untilAsserted(() ->
        assertThat(processedEvents.existsById(event.eventId()))
            .isTrue()
    );
~~~

Với RabbitMQ, helper phải publish vào **exchange với routing key cụ thể**, không publish trực tiếp tới queue để né phần routing cần kiểm tra. Với Pulsar cần đúng tenant/namespace; với Kafka cần đúng topic/partition assignment.

## 36. Runbook production: quan sát rồi mới thay đổi

~~~mermaid
flowchart TD
    A[Không thấy message] --> B{Binding STARTED?}
    B -->|Không| C[Function definition / alias / lifecycle]
    B -->|Có| D{Binder + broker + destination đúng?}
    D -->|Không| E[Sửa binding/endpoint]
    D -->|Có| F{Message có trên destination?}
    F -->|Không| G[Kiểm tra producer confirmation]
    F -->|Có| H{Group/queue/subscription có nhận?}
    H -->|Không| I[Offset, assignment, routing, subscription type]
    H -->|Có| J[Conversion, handler, retry, DLQ]
~~~

Trước khi sửa production:

- Ghi lại cấu hình effective nhưng loại bỏ secret.
- Ghi topic/queue/subscription, partition, committed offset, backlog và cursor.
- Đánh giá side effects: payment, shipment, email, database.
- Không reset group, purge queue hoặc delete subscription khi chưa có kế hoạch.
- Nếu mở rộng Rabbit binding pattern, bảo đảm consumer không nhận nhầm event từ tenant khác.
- Nếu chuyển destination, xác minh backlog ở destination cũ.
- Sau sửa, publish một event test an toàn, xác minh ack/commit và lưu bằng chứng.
- Theo dõi lag, queue depth, DLT và retry trong giai đoạn sau deploy.

Một lỗi cấu hình nhỏ không nên được “sửa” bằng một thao tác gây replay dữ liệu quy mô lớn.

## 37. Bảng lỗi nhanh theo nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Bằng chứng | Cách sửa |
|---|---|---|---|
| Không có binding | Function/alias sai | Actuator bindings | Sửa definition/key |
| Binding đọc destination lạ | Thiếu destination | Effective config | Khai báo destination |
| Kafka group lag=0 | Đã ở cuối topic | consumer-groups describe | Publish event mới để thử |
| Một Pod Kafka không nhận | Không được assign partition | Group member assignment | Kiểm tra partition/concurrency |
| Hai dịch vụ chia dữ liệu | Dùng chung group | Member list | Tách group, lập kế hoạch offset |
| Kafka Streams im lặng | Application ID, task/Serde | Thread/restore/error logs | Sửa theo Streams semantics |
| Rabbit queue không tồn tại | Sai group/prefix/provision | list_queues | Sửa naming/IaC |
| Rabbit queue không có message | Binding key không khớp | list_bindings/publish key | Sửa routing |
| Rabbit existing queue bị bỏ qua | queueNameGroupOnly=false | Queue names | Chỉnh property |
| Rabbit vhost sai | Kết nối khác vhost | Connections/UI | Đồng bộ vhost |
| Pulsar topic “đúng tên” | Sai namespace | Topic full name | Đồng bộ tenant/namespace |
| Pulsar standby idle | Failover/Exclusive subscription | Subscription stats | Kiểm tra semantics |
| Message đã vào DLQ | Handler/Serde lỗi | DLT/DLQ, exception | Sửa conversion/processing |
| Consumer bị STOPPED | autoStartup hoặc operator | Binding state | Start theo runbook |
| Lỗi chỉ trên production | Profile/env override | Config diff | Sửa nguồn cấu hình |

## 38. Checklist cuối cùng

- [ ] Tên bean, function.definition và input binding đúng.
- [ ] Có destination tường minh, không vô tình dùng tên binding làm topic.
- [ ] Đúng binder alias, cluster, Rabbit vhost hoặc Pulsar namespace.
- [ ] Kafka: topic, group, offset, partition assignment được xác minh.
- [ ] Kafka Streams: application.id, task state và Serde được xác minh.
- [ ] Rabbit: exchange type, queue, group, prefix, binding key và publish routing key khớp.
- [ ] Rabbit: existing queue dùng queueNameGroupOnly và provisioning flags phù hợp.
- [ ] Pulsar: topic đầy đủ, subscription name/type và cursor đúng.
- [ ] Binding đang STARTED, không bị pause hoặc stop.
- [ ] Content type, serialization, retries và DLQ được kiểm tra.
- [ ] Dùng một event mới với ID duy nhất để theo dõi end-to-end.
- [ ] Không reset offset hoặc xóa queue/subscription để thử.
- [ ] Có integration test với broker thật ngăn lỗi tái diễn.

## 39. Tài liệu tham khảo

- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html), quy ước tên function input/output và alias.
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html), destination, group, binder, autoStartup, concurrency.
- [Spring Cloud Stream — Consumer Groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html), competing consumer và anonymous group.
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html), bindings Actuator và lifecycle.
- [Spring Cloud Stream — Kafka Binder Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html), Kafka consumer properties.
- [Spring Cloud Stream — Resetting Kafka Offsets](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/reset-offsets.html), startOffset, resetOffsets, committed offsets.
- [Spring Cloud Stream — RabbitMQ Existing Queues/Exchanges](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/existing-destinations.html), quy tắc tên exchange/queue và dùng queue có sẵn.
- [Spring Cloud Stream — RabbitMQ Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/rabbitmq-consumer-properties.html), bindingRoutingKey, queueNameGroupOnly, bindQueue.
- [Spring Cloud Stream — RabbitMQ Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html), routingKey và routingKeyExpression.
- [RabbitMQ — Exchanges](https://www.rabbitmq.com/docs/exchanges), direct/topic/fanout và routing.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html), topic destination, schema và binder properties.
- [Spring for Apache Pulsar — Message Consumption](https://docs.spring.io/spring-pulsar/reference/reference/pulsar/message-consumption.html), subscription name/type, listener và concurrency.

**Kết luận:** Khi Consumer không nhận, hãy khoanh vùng theo thứ tự **function/binding → binder/broker → destination → group/queue/subscription → offset/routing → conversion/handler**. Kafka chủ yếu cần kiểm tra topic, group, offset và partition assignment; RabbitMQ phải đối chiếu exchange, queue, routing key và binding key; Pulsar phải xác minh topic fully qualified và subscription. Chỉ thay cấu hình sau khi chứng minh event đã đi tới đâu; tránh biến một lỗi định tuyến thành sự cố mất dữ liệu hoặc replay ngoài ý muốn.


