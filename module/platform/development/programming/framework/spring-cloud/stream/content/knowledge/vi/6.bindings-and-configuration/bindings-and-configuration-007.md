# Thuộc tính mở rộng theo namespace Kafka, RabbitMQ và Pulsar

Spring Cloud Stream cung cấp mô hình cấu hình chung cho input và output binding. Các thuộc tính như `destination`, `group` và `content-type` mô tả luồng dữ liệu ở mức ứng dụng. Mỗi message broker còn có quy tắc riêng: Kafka làm việc với topic, partition, offset và consumer group; RabbitMQ dùng exchange, queue, acknowledgement và routing; Pulsar dùng tenant, namespace, topic và subscription.

Để biểu diễn các khả năng riêng đó, mỗi binder có một **namespace thuộc tính mở rộng**. Kafka binder dùng `spring.cloud.stream.kafka`, Rabbit binder dùng `spring.cloud.stream.rabbit`, còn Pulsar binder dùng `spring.cloud.stream.pulsar`. Trong từng namespace, ứng dụng có thể cấu hình mặc định ở cấp binder hoặc tinh chỉnh theo từng binding.

Bài này giải thích cách đọc các namespace, phân biệt thuộc tính dùng chung với thuộc tính riêng của broker, cấu hình consumer và producer, và lựa chọn đúng phạm vi khi triển khai Spring Cloud Stream.

## 1. Vì sao cần thuộc tính mở rộng?

Một binding mô tả một cổng vào hoặc cổng ra của ứng dụng. Phần cấu hình chung giúp ứng dụng khai báo destination, group, content type và các tùy chọn phổ biến mà không phụ thuộc trực tiếp vào broker.

Ví dụ một consumer:

```java
@Bean
Consumer<OrderCreated> processOrder(OrderHandler handler) {
    return handler::handle;
}
```

Cấu hình chung:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          content-type: application/json
```

Cấu hình này nói rằng input binding `processOrder-in-0` đọc destination `orders` trong group `order-processor`. Nhưng nó chưa nói rõ các lựa chọn riêng của broker như:

- Kafka: consumer đọc từ offset nào, commit offset theo cách nào, bật dead-letter topic ra sao, cấu hình số bản ghi lấy trong một lần poll thế nào.
- RabbitMQ: queue có tự bind dead-letter exchange không, prefetch bao nhiêu message, acknowledgement mode nào được dùng, routing key của producer là gì.
- Pulsar: subscription dùng kiểu `Shared` hay `Key_Shared`, receiver queue có kích thước bao nhiêu, producer có batching hay compression không.

Các lựa chọn trên được biểu diễn bằng thuộc tính mở rộng của binder tương ứng. Nhờ vậy, mã hàm nghiệp vụ vẫn tập trung vào xử lý sự kiện, còn cách giao nhận được mô tả trong cấu hình hạ tầng.

## 2. Cấu trúc namespace và phạm vi cấu hình

Có ba lớp cấu hình cần phân biệt.

| Phạm vi | Namespace điển hình | Dùng để làm gì |
|---|---|---|
| Thuộc tính chung của Spring Cloud Stream | `spring.cloud.stream.bindings.<bindingName>` | Destination, group, content type, consumer/producer properties dùng chung |
| Thuộc tính binder ở cấp ứng dụng | `spring.cloud.stream.kafka.binder`, `spring.cloud.stream.rabbit.binder`, `spring.cloud.stream.pulsar.binder` | Cấu hình mặc định hoặc chính sách chung của binder; endpoint kết nối có thể nằm ở namespace Spring Boot riêng |
| Thuộc tính mở rộng theo binding | `spring.cloud.stream.kafka.bindings.<bindingName>`, `spring.cloud.stream.rabbit.bindings.<bindingName>`, `spring.cloud.stream.pulsar.bindings.<bindingName>` | Tùy chọn riêng cho consumer hoặc producer của một binding |

`<bindingName>` là tên binding, ví dụ `processOrder-in-0` hoặc `publishOrder-out-0`. Sau namespace binding, thuộc tính thường được chia thành hai nhánh:

- `consumer`: tùy chọn dành cho input binding.
- `producer`: tùy chọn dành cho output binding.

Mẫu cấu trúc:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      kafka:
        binder:
          # Thuộc tính chung của Kafka binder
        bindings:
          processOrder-in-0:
            consumer:
              # Thuộc tính mở rộng của Kafka consumer
```

Trong cấu hình thực tế, `kafka` có thể được thay bằng `rabbit` hoặc `pulsar` để chọn namespace mở rộng tương ứng. Các nhánh `binder` và `bindings` nằm dưới `spring.cloud.stream` cùng cấp.

Spring Cloud Stream còn hỗ trợ giá trị mặc định để tránh lặp cấu hình. Core dùng `spring.cloud.stream.default.consumer.*` và `spring.cloud.stream.default.producer.*`. Kafka binder hỗ trợ các nhánh `spring.cloud.stream.kafka.default.consumer.*` và `spring.cloud.stream.kafka.default.producer.*`; Rabbit binder có namespace `spring.cloud.stream.rabbit.default.*`. Với Pulsar, các producer/consumer properties dùng chung có thể đặt ở `spring.cloud.stream.pulsar.binder.producer.*` và `spring.cloud.stream.pulsar.binder.consumer.*`. Chỉ đặt mặc định khi các binding thực sự có cùng yêu cầu.

### Thuộc tính chung và thuộc tính mở rộng không thay thế nhau

Một số thuộc tính có vẻ tương tự nhưng phục vụ các lớp khác nhau:

- `spring.cloud.stream.bindings.processOrder-in-0.group` xác định group logic của input binding.
- `spring.cloud.stream.kafka.bindings.processOrder-in-0.consumer.enable-dlq` yêu cầu Kafka binder áp dụng khả năng dead-letter theo cách Kafka hỗ trợ.
- `spring.cloud.stream.rabbit.bindings.processOrder-in-0.consumer.prefetch` điều chỉnh số message RabbitMQ có thể giao trước cho consumer.
- `spring.cloud.stream.pulsar.bindings.processOrder-in-0.consumer.subscription-type` chọn kiểu subscription của Pulsar.

Không nên đưa mọi thuộc tính vào `spring.cloud.stream.bindings` với suy nghĩ rằng framework sẽ tự ánh xạ chúng sang mọi broker. Thuộc tính chỉ được hiểu khi nó thuộc đúng namespace và binder đang dùng hỗ trợ nó.

## 3. Kafka binder: topic, consumer, producer và client properties

Kafka binder kết nối binding với Kafka cluster. Namespace thường dùng gồm:

- `spring.cloud.stream.kafka.binder`: cấu hình chung cho Kafka binder, như địa chỉ broker và chính sách quản lý topic.
- `spring.cloud.stream.kafka.bindings.<bindingName>.consumer`: thuộc tính mở rộng cho một input binding.
- `spring.cloud.stream.kafka.bindings.<bindingName>.producer`: thuộc tính mở rộng cho một output binding.

### Cấu hình ở cấp binder

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: localhost:9092
            auto-create-topics: true
          auto-add-partitions: false
          min-partition-count: 3
          replication-factor: 1
```

Ý nghĩa:

- `brokers` chỉ định broker hoặc danh sách broker mà binder kết nối.
- `auto-create-topics` kiểm soát việc binder tự tạo topic khi cần.
- `auto-add-partitions` kiểm soát việc binder tự bổ sung partition trong các trường hợp được hỗ trợ.
- `min-partition-count` là số partition tối thiểu binder dùng khi cấp phát topic theo cấu hình liên quan.
- `replication-factor` là replication factor mặc định cho topic do binder tạo.

Các thuộc tính cấp binder có phạm vi rộng. `min-partition-count` chỉ có tác dụng khi `auto-create-topics` hoặc `auto-add-partitions` được bật; `replication-factor` áp dụng cho topic được binder tự tạo. Nếu đặt `auto-create-topics: false`, destination chưa tồn tại phải được đội hạ tầng tạo trước. Cách này hữu ích khi production yêu cầu quản trị topic qua Infrastructure as Code. Không nên bật tự tạo topic mà không kiểm tra partition count, replication factor, retention và quyền tạo topic.

### Thuộc tính consumer theo binding

Ví dụ input binding cần commit offset và chuyển message lỗi sang dead-letter topic:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          content-type: application/json
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              ack-mode: record
              enable-dlq: true
              dlq-name: orders.errors
              configuration:
                "max.poll.records": 100
                "isolation.level": read_committed
```

Các tùy chọn trên có ý nghĩa khác nhau:

- `ack-mode` điều khiển chế độ xác nhận/commit offset theo hỗ trợ của Kafka binder. `record` là một lựa chọn thường dùng để gắn việc xác nhận với từng record.
- `enable-dlq` bật dead-letter handling của Kafka binder cho consumer binding.
- `dlq-name` chỉ định tên dead-letter topic.
- `configuration` truyền các Kafka client properties bổ sung cho consumer.
- `max.poll.records` giới hạn số record trả về trong một lần poll.
- `isolation.level` đặt mức đọc transaction của Kafka; `read_committed` chỉ đọc các record thuộc transaction đã commit.

Dead-letter topic là tài nguyên riêng cần có chính sách partition và quyền truy cập phù hợp. Nếu binder cần tự tạo DLQ topic, hãy kiểm tra quyền và cấu hình provisioning. Khi cấu hình DLQ partition hoặc producer cho DLQ, cần xem yêu cầu của binder phiên bản đang dùng; không giả định DLQ luôn có cùng số partition với topic gốc.

### Thuộc tính producer theo binding

Producer có thể cần nén dữ liệu, gửi đồng bộ hoặc thiết lập các Kafka producer client properties:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          content-type: application/json
      kafka:
        bindings:
          publishOrder-out-0:
            producer:
              sync: true
              configuration:
                "compression.type": snappy
                "acks": all
                "enable.idempotence": true
```

Trong ví dụ:

- `sync` yêu cầu producer chờ kết quả gửi theo cơ chế đồng bộ của binder; điều này có thể ảnh hưởng throughput và latency.
- `compression.type` chọn thuật toán nén record batch được Kafka client hỗ trợ.
- `acks` xác định mức xác nhận từ broker đối với lần gửi.
- `enable.idempotence` bật producer idempotence khi các điều kiện Kafka client tương ứng được đáp ứng.

`configuration` là điểm mở rộng quan trọng: nó cho phép truyền các Kafka client properties mà binder chưa có thuộc tính chuyên biệt tương ứng. Hãy chỉ sử dụng đúng property của Kafka client và kiểm tra nó thuộc producer hay consumer. Đặt `max.poll.records` ở producer không có tác dụng vì đây là consumer property.

### Binder configuration và client configuration

Kafka binder có thể cung cấp map `configuration` ở cấp binder để truyền các Kafka client properties chung. Khi cần một binding có cấu hình riêng, dùng map `configuration` trong nhánh consumer hoặc producer của binding đó.

Ví dụ, cluster dùng TLS hoặc SASL có thể cần cấu hình bảo mật client. Các thông số chung cho kết nối nên đặt ở cấp binder nếu mọi binding dùng cùng cluster và chính sách. Nếu có nhiều binding hoặc nhiều cluster có yêu cầu khác nhau, đặt ở đúng binder instance hoặc binding scope được hỗ trợ.

Không nhầm namespace `spring.kafka.*` của Spring for Apache Kafka với namespace mở rộng `spring.cloud.stream.kafka.*` của Kafka binder. Một ứng dụng có thể dùng cả hai thư viện, nhưng chúng có thể tạo client và lifecycle riêng. Cấu hình ở namespace này không mặc nhiên áp dụng cho client do namespace kia tạo.

## 4. Rabbit binder: exchange, queue, acknowledgement và routing

Rabbit binder kết nối Spring Cloud Stream với RabbitMQ. Namespace mở rộng gồm:

- `spring.cloud.stream.rabbit.binder`: kết nối và chính sách chung của binder.
- `spring.cloud.stream.rabbit.bindings.<bindingName>.consumer`: queue, acknowledgement, prefetch, retry và DLQ cho input.
- `spring.cloud.stream.rabbit.bindings.<bindingName>.producer`: exchange, routing key, delivery và publisher behavior cho output.

### Cấu hình cấp binder

Ví dụ:

```yaml
spring:
  rabbitmq:
    addresses: localhost:5672
    username: app-user
    password: ${RABBITMQ_PASSWORD}
    virtual-host: /orders
```

`addresses` xác định địa chỉ RabbitMQ; `virtual-host` chọn virtual host. Rabbit binder mặc định dùng Spring Boot `ConnectionFactory`, vì vậy các thuộc tính kết nối như host, port, addresses, username, password và virtual host thuộc namespace `spring.rabbitmq`. Binder có các thuộc tính riêng dưới `spring.cloud.stream.rabbit.binder`, chẳng hạn `nodes` và `adminAddresses` để định vị queue trong RabbitMQ cluster. Mật khẩu được lấy từ biến môi trường để tránh ghi bí mật vào file cấu hình được commit.

Các thiết lập cấp binder phù hợp với kết nối dùng chung. Nếu ứng dụng kết nối nhiều broker hoặc nhiều virtual host độc lập, hãy cân nhắc cấu hình nhiều binder instance và gán binder alias cho từng binding.

### Thuộc tính consumer theo binding

RabbitMQ dùng queue làm nơi lưu message cho subscriber. Nhiều consumer cùng group có thể cùng tiêu thụ queue đó. Cấu hình mở rộng thường quyết định cách queue được khai báo và cách consumer nhận message.

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              acknowledge-mode: auto
              prefetch: 20
              max-concurrency: 4
              auto-bind-dlq: true
              republish-to-dlq: true
              dlq-ttl: 60000
```

Giải thích:

- `acknowledge-mode` chọn cách consumer xác nhận message. Với chế độ `auto`, container quản lý acknowledgement theo kết quả xử lý.
- `prefetch` giới hạn số message chưa được xác nhận mà broker giao trước cho consumer.
- `max-concurrency` đặt giới hạn concurrency tối đa của consumer container khi binder hỗ trợ.
- `auto-bind-dlq` yêu cầu binder khai báo và bind dead-letter queue theo quy tắc của nó.
- `republish-to-dlq` cho phép republish message lỗi sang DLQ kèm thông tin lỗi theo khả năng binder.
- `dlq-ttl` cấu hình thời gian sống của message trong DLQ theo đơn vị mà thuộc tính binder quy định (thường là milliseconds).

Prefetch ảnh hưởng trực tiếp tới phân phối tải. Nếu prefetch quá cao, một consumer có thể giữ nhiều message chưa ack trong khi consumer khác rảnh. Nếu quá thấp, broker có thể phải chờ consumer hoàn tất từng message trước khi giao thêm, làm giảm throughput. Hãy điều chỉnh theo thời gian xử lý và năng lực downstream.

`auto-bind-dlq` có thể dẫn tới việc binder tạo thêm queue hoặc exchange. Trong production, cần kiểm tra quyền `configure` của tài khoản và chính sách tên DLQ. Nếu hạ tầng đã được khai báo trước, cần cấu hình binder để hành vi khai báo phù hợp với chính sách đó.

### Thuộc tính producer theo binding

Rabbit producer có thể cần chọn routing key hoặc thiết lập header được gửi đi:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          content-type: application/json
      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              routing-key-expression: "'orders.created'"
              delivery-mode: persistent
              declare-exchange: true
```

- `routing-key-expression` là biểu thức dùng để xác định routing key khi gửi message. Chuỗi cố định trong ví dụ được viết dưới dạng biểu thức SpEL.
- `delivery-mode` chọn chế độ giao message persistent hoặc non-persistent theo hỗ trợ binder và broker.
- `declare-exchange` điều khiển việc binder khai báo exchange theo cấu hình producer.

Nếu routing key phụ thuộc dữ liệu message, biểu thức có thể đọc header hoặc payload. Cần bảo đảm exchange type và queue binding phía consumer khớp routing key. Producer gửi thành công tới exchange không đồng nghĩa message đã được route tới queue; publisher confirms/returns và metrics định tuyến giúp phát hiện message không được route.

### Retry và dead-letter trong RabbitMQ

Rabbit binder có thể hỗ trợ auto-bind DLQ, dead-letter exchange, dead-letter routing key, TTL và các queue arguments. Các thuộc tính này tác động tới queue/exchange được tạo hoặc cách message được chuyển khi consumer lỗi.

Cần phân biệt hai việc:

1. Retry trong ứng dụng/container: message có thể được thử xử lý lại theo chính sách retry.
2. Dead-letter ở broker: message được định tuyến sang DLQ khi bị reject, hết TTL hoặc đạt điều kiện queue policy.

Không nên cấu hình retry vô hạn cho một message độc hại hoặc payload không giải mã được. Hãy giới hạn số lần thử, đặt backoff hợp lý và lưu thông tin lỗi để vận hành có thể điều tra, sửa dữ liệu hoặc phát lại có kiểm soát.

## 5. Pulsar binder: tenant, namespace và subscription

Pulsar binder dùng namespace riêng cho thuộc tính mở rộng theo binding và các mặc định producer/consumer ở cấp binder. Endpoint client và admin thường được cấu hình bằng Spring Boot properties của Spring for Apache Pulsar:

- `spring.cloud.stream.pulsar.binder`: partition count mặc định và các producer/consumer properties dùng chung; endpoint client/admin thường được cấu hình bằng Spring Boot properties dưới `spring.pulsar.*`.
- `spring.cloud.stream.pulsar.bindings.<bindingName>.consumer`: subscription type, receiver, acknowledgement và các consumer options.
- `spring.cloud.stream.pulsar.bindings.<bindingName>.producer`: batching, routing, compression, timeout và các producer options.

### Cấu hình binder

Ví dụ:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar://localhost:6650
    administration:
      service-url: http://localhost:8080
  cloud:
    stream:
      pulsar:
        binder:
          partition-count: 4
```

`spring.pulsar.client.service-url` là endpoint giao thức Pulsar mà client kết nối; `spring.pulsar.administration.service-url` là endpoint quản trị mà provisioner dùng khi cần gọi Pulsar Admin API. Đây là các thuộc tính Spring Boot của Spring for Apache Pulsar. Trong namespace binder, `spring.cloud.stream.pulsar.binder.partition-count` đặt số partition mặc định cho topic được provision theo khả năng binder.

Tên topic Pulsar thường có dạng đầy đủ `persistent://<tenant>/<namespace>/<topic>`. Hãy xác định tenant và namespace trong destination hoặc cấu hình mặc định của Spring for Apache Pulsar theo phiên bản đang dùng; không giả định binder có thuộc tính `tenant` và `namespace` riêng dưới `spring.cloud.stream.pulsar.binder`.

### Thuộc tính consumer theo binding

Ví dụ consumer muốn chia tải giữa nhiều instance:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: persistent://public/orders/orders
          group: order-processor
      pulsar:
        bindings:
          processOrder-in-0:
            consumer:
              subscription-type: shared
              receiver-queue-size: 100
```

`subscription-type` xác định cách nhiều consumer cùng subscription phối hợp. `shared` cho phép nhiều consumer nhận message từ subscription; `exclusive` chỉ cho một consumer hoạt động; `failover` cho phép consumer dự phòng tiếp quản; `key-shared` phân phối theo key để giữ affinity của cùng key với một consumer theo semantics Pulsar.

`receiver-queue-size` điều chỉnh số message client có thể buffer trước khi ứng dụng xử lý. Buffer quá lớn có thể làm tăng bộ nhớ và số message đang giữ tại client; quá nhỏ có thể ảnh hưởng throughput. Tên và kiểu dữ liệu chính xác của thuộc tính phụ thuộc phiên bản binder, vì vậy hãy xác minh metadata cấu hình của phiên bản đang dùng.

Khi dùng native decoding của Pulsar, thuộc tính core `spring.cloud.stream.bindings.<bindingName>.consumer.use-native-decoding` bật giải mã ở broker/client. Schema và kiểu dữ liệu đích được khai báo trong namespace mở rộng, chẳng hạn `schema-type` và `message-type` dưới `spring.cloud.stream.pulsar.bindings.<bindingName>.consumer`. Phía producer có các thuộc tính tương ứng dưới nhánh `producer`, kết hợp với core `use-native-encoding`. Producer và consumer phải thống nhất schema; chỉ bật native conversion khi hai phía hiểu cùng định dạng.

### Thuộc tính producer theo binding

Producer có thể bật batching để gom nhiều message thành batch trước khi gửi:

```yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://public/orders/orders
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              batching-enabled: true
              batching-max-messages: 100
              batching-max-publish-delay: 10ms
```

Batching có thể cải thiện throughput và giảm overhead mạng, nhưng cũng làm tăng thời gian chờ để gom đủ message. `batching-max-messages` đặt giới hạn số message trong batch; `batching-max-publish-delay` đặt thời gian chờ tối đa để gửi batch theo thuộc tính binder. Hãy cân bằng throughput, latency và kích thước message.

Với Pulsar binder hiện hành, các Spring for Apache Pulsar properties cũng có thể được đặt ở cấp ứng dụng qua `spring.pulsar.producer.*` hoặc ở cấp binder qua `spring.cloud.stream.pulsar.binder.producer.*`. Thuộc tính mở rộng theo binding có mức ưu tiên cao nhất; thứ tự áp dụng được mô tả là extended binding properties, binder properties rồi đến Spring Boot properties. Điều này cho phép đặt mặc định batching chung nhưng ghi đè riêng cho một output binding.

Pulsar producer còn có thể hỗ trợ compression, send timeout, routing mode và schema type. Chỉ bật các thuộc tính đó khi consumer tương ứng có thể giải mã và schema hai phía tương thích.

## 6. So sánh cách đặt thuộc tính giữa ba binder

Một yêu cầu nghiệp vụ giống nhau có thể được cấu hình khác nhau tùy broker. Ví dụ, muốn xử lý message lỗi và tránh làm consumer giữ quá nhiều message, ta có thể cần:

| Nhu cầu | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Chia tải consumer | Consumer group và partition assignment | Nhiều consumer cùng queue | Nhiều consumer cùng subscription |
| Giới hạn lượng dữ liệu nhận trước | Kafka client poll/fetch properties | `prefetch` | Receiver queue size |
| Chọn cơ chế xác nhận | Ack mode/offset commit | Acknowledge mode | Ack/negative ack |
| Chuyển message lỗi | Dead-letter topic | Dead-letter queue/exchange | Dead-letter policy/topic |
| Điều chỉnh producer | Kafka producer configuration | Routing, delivery mode, confirms | Batching, routing, compression |
| Cấp phát tài nguyên | Topic/partition | Exchange/queue/binding | Tenant/namespace/topic/subscription |

Không có một thuộc tính duy nhất tương đương hoàn toàn giữa ba broker. Ví dụ `prefetch` của RabbitMQ giới hạn số message unacked được giao tới consumer. `max.poll.records` của Kafka giới hạn số record trả về trong một lần poll, nhưng không đồng nghĩa với toàn bộ lượng dữ liệu đang được client fetch hoặc giữ. `receiver-queue-size` của Pulsar điều chỉnh buffer phía consumer client. Cần hiểu ngữ nghĩa broker trước khi chọn giá trị.

## 7. Cấp binder hay cấp binding?

Chọn phạm vi cấu hình dựa trên mức độ dùng chung của yêu cầu.

### Đặt ở cấp binder khi áp dụng cho cả kết nối hoặc cluster

Ví dụ:

- Kafka brokers, TLS/SASL mặc định, chính sách auto-create topic.
- RabbitMQ addresses, virtual host và connection settings.
- Pulsar client/admin endpoint qua Spring Boot properties; partition count và producer/consumer defaults qua Pulsar binder properties.

Nếu nhiều binding dùng chung một cluster và một chính sách, cấu hình ở cấp binder giúp tránh lặp lại.

### Đặt ở cấp binding khi từng luồng có yêu cầu khác nhau

Ví dụ:

- Một Kafka consumer cần `enable-dlq`, consumer khác không cần.
- Một Rabbit queue cần prefetch thấp vì xử lý nặng, queue khác có thể nhận nhiều message hơn.
- Một Pulsar subscription cần `Key_Shared` vì giữ affinity theo key, subscription khác dùng `Shared` để tối đa throughput.
- Producer của một binding cần batching, producer khác ưu tiên latency thấp.

Đặt thuộc tính quá rộng có thể khiến một binding mới vô tình nhận chính sách không phù hợp. Ngược lại, lặp cấu hình giống nhau ở mọi binding làm cấu hình khó bảo trì. Hãy chọn cấp binder cho mặc định chung, cấp binding cho khác biệt có chủ đích.

### Một ví dụ hai consumer khác chính sách

Giả sử cùng ứng dụng có hai consumer:

- `processOrder-in-0` thực hiện nghiệp vụ cập nhật đơn hàng; lỗi cần DLQ.
- `auditOrder-in-0` ghi log kiểm toán; có thể cần concurrency và batching riêng, nhưng không dùng chung chính sách DLQ với consumer nghiệp vụ.

Cấu hình core và phần mở rộng:

```yaml
spring:
  cloud:
    function:
      definition: processOrder;auditOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
        auditOrder-in-0:
          destination: orders
          group: order-audit
      kafka:
        binder:
          brokers: kafka.internal:9092
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.processor.dlq
          auditOrder-in-0:
            consumer:
              configuration:
                "max.poll.records": 500
```

Hai consumer đọc cùng topic nhưng có group độc lập. Thuộc tính mở rộng được đặt theo từng binding nên chính sách DLQ và poll size không bị áp dụng nhầm cho consumer còn lại.

## 8. Kết hợp thuộc tính chung và thuộc tính riêng

Một binding thường cần cả hai nhóm cấu hình:

1. Thuộc tính core xác định destination, group và content type.
2. Thuộc tính mở rộng xác định cách binder thực hiện giao nhận trên broker.

Ví dụ:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          content-type: application/json
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enable-dlq: true
              dlq-name: orders.dlq
```

Nếu bỏ phần core, binder có thể không biết destination hoặc group logic cần dùng. Nếu bỏ phần mở rộng, binder dùng mặc định của nó. Mặc định có thể đủ cho một luồng đơn giản, nhưng không nên dựa vào mặc định khi yêu cầu nghiệp vụ liên quan đến ordering, durability, retry, dead-letter hoặc throughput.

### Tránh cấu hình trùng và xung đột

Không đặt cùng một ý định ở nhiều nơi với giá trị khác nhau. Ví dụ, concurrency có thể được khai báo ở core consumer properties hoặc một thuộc tính mở rộng riêng của binder. Nếu cả hai cùng tác động tới consumer container, cần biết thuộc tính nào được ưu tiên trong phiên bản hiện tại.

Khi có xung đột, đừng phỏng đoán theo thứ tự YAML. Hãy xem metadata cấu hình, tài liệu binder và log khởi tạo. Một số thuộc tính là alias hoặc được chuyển đổi sang client property; một số khác là cấu hình container và không thể ghi đè trực tiếp bằng Kafka client property.

### Tách cấu hình theo môi trường

Dùng Spring profiles hoặc biến môi trường để tách endpoint và thông số vận hành giữa local, test, staging và production.

Ví dụ:

```yaml
spring:
  config:
    activate:
      on-profile: local
  cloud:
    stream:
      kafka:
        binder:
          brokers: localhost:9092
```

Trong production, endpoint và credentials có thể được inject từ môi trường triển khai hoặc secret manager. Không commit password, SASL secret, TLS private key hoặc token vào file cấu hình. Hãy giữ cấu hình hạ tầng tách khỏi mã nguồn và giới hạn quyền truy cập.

## 9. Cách tìm đúng thuộc tính mở rộng

Khi cần một tùy chọn chưa quen thuộc, hãy tra theo thứ tự:

1. Xác định binder thực tế của binding bằng thuộc tính `binder` hoặc default binder.
2. Xác định đây là thuộc tính cấp binder, consumer hay producer.
3. Tra đúng tài liệu của binder và phiên bản dependency đang dùng.
4. Kiểm tra tên property trong configuration metadata hoặc IDE completion.
5. Xem property có phải thuộc tính của Spring Cloud Stream binder hay property của client library broker.
6. Xác nhận giá trị hợp lệ, đơn vị thời gian, kiểu dữ liệu và mặc định.
7. Viết integration test hoặc kiểm tra broker để xác minh tác động thực tế.

Không nên sao chép property từ một bài viết dùng phiên bản khác mà không kiểm tra. Spring Cloud Stream và các binder có thể thay đổi tên, kiểu, giá trị mặc định hoặc cách ánh xạ property giữa các phiên bản.

### Phân biệt property binder với property client

Một số cấu hình là abstraction do binder định nghĩa, ví dụ `enable-dlq` của Kafka binder hoặc `auto-bind-dlq` của Rabbit binder. Chúng có thể kích hoạt nhiều thao tác ở binder/provisioner, chứ không phải một thuộc tính native của client.

Một số cấu hình khác được truyền thẳng đến client, ví dụ `max.poll.records` của Kafka consumer hoặc `acks` của Kafka producer. Các thuộc tính này thường được đặt trong map `configuration` theo phạm vi client tương ứng.

Với RabbitMQ và Pulsar, nhiều thuộc tính mở rộng được binder ánh xạ sang API client hoặc cấu hình container. Không phải mọi property của Rabbit Java Client hoặc Pulsar client đều được binder cho phép truyền qua một map tổng quát. Kiểm tra đúng extension properties của binder trước khi giả định có thể truyền mọi tùy chọn.

## 10. Lỗi thường gặp khi cấu hình namespace

**Đặt property mở rộng vào namespace core.** Ví dụ đặt `enable-dlq` trực tiếp dưới `spring.cloud.stream.bindings`. Core có thể không nhận biết property này. Hãy đặt trong namespace Kafka binder và đúng nhánh consumer.

**Nhầm `binder` với `bindings`.** `binder` là cấu hình binder instance hoặc cluster; `bindings` là cấu hình mở rộng theo tên binding. Sai một cấp namespace có thể khiến property không được bind.

**Đặt consumer property vào producer.** `max.poll.records` không điều khiển producer; `routing-key-expression` không có ý nghĩa với input binding. Luôn xác định hướng của binding trước khi cấu hình.

**Dùng nhầm namespace giữa các binder.** `spring.cloud.stream.kafka.bindings` không cấu hình RabbitMQ hoặc Pulsar. Nếu binding dùng Rabbit binder, cần namespace Rabbit tương ứng.

**Dùng property client sai chỗ.** Kafka `acks` thuộc producer; `isolation.level` thuộc consumer. Đặt sai nhánh có thể khiến client không nhận property hoặc startup thất bại.

**Cho rằng tên thuộc tính giống nhau có nghĩa giống nhau.** Một property cùng tên ở hai binder có thể có đơn vị, giá trị mặc định hoặc semantics khác nhau. So sánh tài liệu và hành vi thực tế, không chỉ so sánh chuỗi tên.

**Không kiểm tra tài nguyên do auto-provision tạo ra.** Topic, queue hoặc subscription có thể được tạo với partition, retention, DLQ hoặc routing không đúng mong muốn. Kiểm tra metadata trên broker sau khi ứng dụng khởi tạo.

**Không kiểm tra property theo phiên bản.** Một property có thể mới xuất hiện, bị deprecated hoặc đổi kiểu. Đồng bộ phiên bản Spring Cloud release train, Spring Cloud Stream và binder dependency trước khi áp dụng.

## 11. Kiểm thử và xác minh cấu hình

Một file YAML được parse thành công chưa chứng minh binder đã áp dụng property. Kiểm thử nên xác minh cả binding metadata lẫn hành vi broker.

### Kiểm tra cấu hình đã bind

Có thể dùng Spring Boot Actuator configuration properties hoặc condition/configuration diagnostics trong môi trường an toàn để kiểm tra property đã được nạp. Cẩn thận không công khai endpoint hoặc giá trị chứa secret. Log khởi tạo của binder thường cho biết destination, group và một phần thông tin kết nối; tránh bật log quá chi tiết trong production nếu nó có thể lộ credentials.

### Kiểm thử với broker thật

Với Kafka, kiểm tra topic, partition, consumer group, committed offset và dead-letter topic. Phát một message lỗi có chủ đích để xác minh DLQ được dùng theo cấu hình; sau đó kiểm tra message gốc và metadata lỗi.

Với RabbitMQ, kiểm tra exchange, queue, binding, routing key, consumer count, unacked count và dead-letter queue. Thử ngắt consumer khi đang xử lý để xác minh acknowledgement và redelivery.

Với Pulsar, kiểm tra tenant, namespace, topic, subscription type, backlog và trạng thái acknowledgement. Khởi chạy nhiều consumer trong cùng subscription để xác minh cách chia tải của subscription type đã chọn.

### Ma trận xác minh gợi ý

| Thay đổi cấu hình | Điều cần quan sát |
|---|---|
| Đổi Kafka `max.poll.records` | Số record được trả về mỗi lần poll và ảnh hưởng tới xử lý |
| Bật Kafka DLQ | Topic lỗi được tạo/định tuyến và nhận record thất bại |
| Đổi Rabbit `prefetch` | Số message unacked tối đa được giao trước cho consumer |
| Bật Rabbit auto-bind DLQ | Queue/exchange dead-letter và routing key được tạo đúng |
| Đổi Pulsar subscription type | Số consumer hoạt động và cách message được phân phối |
| Bật Pulsar batching | Throughput, batch size và độ trễ publish |
| Đổi binder-level endpoint | Binding kết nối đúng cluster hoặc namespace |
| Thay đổi binding-level property | Chỉ binding được chỉ định nhận chính sách đó |

Test binder của Spring Cloud Stream hữu ích cho logic hàm và luồng binding ở mức framework, nhưng không thay thế integration test khi cần xác minh offset, queue, subscription, DLQ, acknowledgement hoặc client configuration thật.

## 12. Quy trình lựa chọn thuộc tính mở rộng

Khi cần điều chỉnh một binding, hãy trả lời lần lượt:

1. Binding đang dùng Kafka, RabbitMQ hay Pulsar? Xác nhận binder alias và dependency.
2. Thuộc tính thuộc cấu hình kết nối chung, consumer hay producer?
3. Chính sách có áp dụng cho toàn cluster/binder hay chỉ một binding?
4. Có thuộc tính core đáp ứng yêu cầu không, hay cần property mở rộng?
5. Property thuộc binder hay client library? Đặt đúng namespace và đúng nhánh.
6. Giá trị, đơn vị, mặc định và tương thích phiên bản là gì?
7. Tài nguyên broker có cần được tạo hoặc thay đổi không?
8. Kiểm thử nào chứng minh binder đã áp dụng cấu hình?
9. Metrics hoặc broker UI nào sẽ xác nhận hành vi sau triển khai?

Một cấu hình tốt thể hiện rõ ranh giới: thuộc tính chung mô tả destination và group; namespace mở rộng mô tả cách binder hiện thực giao nhận; broker client properties điều chỉnh chi tiết khi binder cho phép. Khi nắm được ba lớp này, bạn có thể tinh chỉnh Kafka, RabbitMQ và Pulsar mà vẫn giữ cho phần xử lý sự kiện của ứng dụng dễ đọc, kiểm thử và bảo trì.

## Tài liệu tham khảo

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html)
- [Spring Cloud Stream — RabbitMQ Binder Reference Guide](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream — Binder for Apache Pulsar](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Spring for Apache Pulsar — Reference Documentation](https://docs.spring.io/spring-pulsar/reference/)


